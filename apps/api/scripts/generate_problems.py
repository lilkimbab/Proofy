"""Generate hard problems (approved or discarded automatically) and export them.

Run from apps/api:

  .venv/bin/python -m scripts.generate_problems generate --unit calc1-diff --want 3 --count 10
  .venv/bin/python -m scripts.generate_problems generate --unit calc1-diff --model gemini:gemini-3.6-flash
  .venv/bin/python -m scripts.generate_problems list
  .venv/bin/python -m scripts.generate_problems show <id>
  .venv/bin/python -m scripts.generate_problems export
  .venv/bin/python -m scripts.generate_problems review <id> --reject --note "..."   # optional manual override
  .venv/bin/python -m scripts.generate_problems solve --file problem.txt --answer 13

`solve` runs both solvers on a problem you paste in (for example a real past
#22) so the difficulty signals can be compared against known problems.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]


def _load_dotenv() -> None:
    """Read the root .env like scripts/start-api.sh does (existing env wins)."""
    path = ROOT_DIR / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()

from app.content.problem_archetypes import BLUEPRINTS  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.services.problem_factory import (  # noqa: E402
    SOLVER_SYSTEM,
    SOLVER_TEMPLATE,
    FactoryConfig,
    GeneratorUnavailable,
    ProblemFactory,
    ProblemStore,
    export_approved,
    set_review,
)
from app.services.llm_client import LLMClient, LLMError  # noqa: E402


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def cmd_generate(args: argparse.Namespace) -> int:
    models = args.model or [f"gemini:{settings.gemini_model}"]
    config = FactoryConfig(
        generator_models=models,
        strong_solver=args.solver,
        weak_solver=args.weak_solver,
        weak_reasoning=args.weak_reasoning,
        max_repairs=args.max_repairs,
        max_hardens=args.max_hardens,
        extra_solvers=args.extra_solver or [],
        busy_retries=args.busy_retries,
        busy_wait_seconds=args.busy_wait,
        refuter=None if args.refuter == "none" else args.refuter,
    )
    factory = ProblemFactory(config, log=_log)
    made = approved = 0
    for index in range(args.count):
        _log(f"\n=== {index + 1}/{args.count} (승인 {approved}/{args.want or '-'}) ===")
        try:
            record = factory.run(args.unit, target=args.target, archetype_id=args.archetype)
        except GeneratorUnavailable as exc:
            _log(f"출제 모델을 쓸 수 없어 중단합니다: {exc}")
            break
        made += 1
        approved += record["review"]["state"] == "approved"
        _print_summary(record)
        if args.want and approved >= args.want:
            break
    _log(f"\n출제 {made}개 중 자동 승인 {approved}개")
    _log(f"LLM 호출 {len(factory.calls)}회: " + ", ".join(f"{item['kind']}({item['model'].split(':')[-1]})" for item in factory.calls))
    return 0 if made else 1


def _print_summary(record: dict) -> None:
    difficulty = record["difficulty"]
    print(
        f"{record['id']}  {record['status']:<9} 난이도:{difficulty['verdict']:<9} "
        f"강한풀이 생각토큰:{difficulty.get('strongReasoningTokens')}  어렵게:{difficulty.get('hardenRounds')}회  "
        f"판정:{record['review']['state']}({record['review'].get('by', '-')})  [{record['archetype']}]"
    )


def cmd_list(args: argparse.Namespace) -> int:
    store = ProblemStore()
    for record in store.all(args.unit):
        if args.status and record.get("status") != args.status:
            continue
        if args.review and record.get("review", {}).get("state") != args.review:
            continue
        _print_summary(record)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    record = ProblemStore().get(args.id)
    if record is None:
        _log(f"없음: {args.id}")
        return 1
    if args.json:
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    problem = record["problem"]
    _print_summary(record)
    print(f"\n[문제]\n{problem['statement']}\n\n[정답] {problem['answer']}")
    print("\n[풀이]")
    for step in problem.get("solution", []):
        print(f"- {step}")
    if problem.get("cases"):
        print("\n[케이스]")
        for case in problem["cases"]:
            print(f"- {case}")
    print(f"\n[함정] {problem.get('trap', '')}\n[난이도 근거] {problem.get('whyHard', '')}")
    review = record.get("review", {})
    print(f"\n[판정] {review.get('state')} ({review.get('by', '-')})")
    for reason in review.get("reasons", []):
        print(f"- {reason}")
    if review.get("note"):
        print(f"- 메모: {review['note']}")
    print("\n[SymPy 검산]")
    for check in record["verification"].get("checks", []):
        print(f"- {'통과' if check['ok'] else '실패'} {check['condition']}: {check['expr']}  {check.get('error') or ''}")
    for line in record["verification"].get("errors", []):
        print(f"- 오류: {line}")
    print("\n[풀이 모델]")
    for solve in record.get("solves", []):
        if solve.get("error"):
            print(f"- {solve['role']}: 실패 {solve['error'][:120]}")
            continue
        print(
            f"- 라운드{solve.get('round')} {solve['role']:<6} {solve['model']}: 답 {solve.get('answer')} "
            f"({'맞음' if solve.get('correct') else '틀림'}) 생각토큰 {solve.get('reasoningTokens')}  "
            f"{('결함 지적: ' + solve['issue']) if solve.get('issue') else ''}"
        )
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    if args.approve == args.reject:
        _log("--approve 또는 --reject 중 하나를 고르세요")
        return 1
    try:
        record = set_review(ProblemStore(), args.id, approve=args.approve, note=args.note)
    except (KeyError, ValueError) as exc:
        _log(str(exc))
        return 1
    _print_summary(record)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    written = export_approved(ProblemStore(), args.unit)
    if not written:
        _log("승인된 문항이 없습니다")
        return 1
    for unit, path in written.items():
        print(f"{unit}: {path}")
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    statement = Path(args.file).read_text(encoding="utf-8").strip()
    client = LLMClient(log=_log)
    for role, model, reasoning in (("strong", args.solver, "high"), ("weak", args.weak_solver, args.weak_reasoning)):
        try:
            result = client.complete_json(model, SOLVER_SYSTEM, SOLVER_TEMPLATE.format(statement=statement), temperature=0.2, reasoning=reasoning, timeout=420)
        except LLMError as exc:
            print(f"{role} {model}: 실패 {exc}")
            continue
        data = result.data or {}
        verdict = "" if args.answer is None else ("맞음" if str(data.get("answer")) == str(args.answer) else "틀림")
        print(f"{role:<6} {model}: 답 {data.get('answer')} {verdict} 생각토큰 {result.reasoning_tokens} {result.elapsed:.0f}초 결함:{data.get('issue') or '-'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Hard problem generation pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate", help="새 문항 출제")
    generate.add_argument("--unit", required=True, choices=sorted(BLUEPRINTS))
    generate.add_argument("--count", type=int, default=1, help="최대 출제 횟수")
    generate.add_argument("--want", type=int, default=0, help="자동 승인이 이만큼 나오면 멈춤")
    generate.add_argument("--target", default="22", choices=["22", "4"])
    generate.add_argument("--archetype", help="출제 틀 id (없으면 가장 적게 쓴 틀)")
    generate.add_argument("--model", action="append", help="출제 모델, 여러 번 주면 앞에서부터 시도 (기본: gemini:APP_GEMINI_MODEL)")
    generate.add_argument("--solver", default="groq:openai/gpt-oss-120b")
    generate.add_argument("--weak-solver", default="groq:openai/gpt-oss-20b")
    generate.add_argument("--weak-reasoning", default="low", choices=["low", "medium", "high"])
    generate.add_argument("--max-repairs", type=int, default=2)
    generate.add_argument("--max-hardens", type=int, default=2)
    generate.add_argument("--extra-solver", action="append", help="정답을 함께 확인할 풀이 모델 (여러 번 줄 수 있음, 모두 맞혀야 승인)")
    generate.add_argument("--refuter", default="groq:openai/gpt-oss-120b", help="놓친 경우(반례)를 찾는 모델, 끄려면 none")
    generate.add_argument("--busy-retries", type=int, default=2, help="모든 출제 모델이 503일 때 다시 시도할 횟수")
    generate.add_argument("--busy-wait", type=int, default=90, help="다시 시도하기 전 기다릴 초")
    generate.set_defaults(func=cmd_generate)

    listing = sub.add_parser("list", help="출제한 문항 목록")
    listing.add_argument("--unit")
    listing.add_argument("--status", choices=["verified", "disputed", "rejected"])
    listing.add_argument("--review", choices=["pending", "approved", "rejected"])
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="문항 하나 자세히")
    show.add_argument("id")
    show.add_argument("--json", action="store_true")
    show.set_defaults(func=cmd_show)

    review = sub.add_parser("review", help="자동 판정을 손으로 뒤집기 (선택)")
    review.add_argument("id")
    review.add_argument("--approve", action="store_true")
    review.add_argument("--reject", action="store_true")
    review.add_argument("--note", default="")
    review.set_defaults(func=cmd_review)

    export = sub.add_parser("export", help="승인된 문항을 앱 문제 형식으로 내보내기")
    export.add_argument("--unit")
    export.set_defaults(func=cmd_export)

    solve = sub.add_parser("solve", help="기준 문항(예: 기출 22번)으로 풀이 모델 신호 확인")
    solve.add_argument("--file", required=True)
    solve.add_argument("--answer")
    solve.add_argument("--solver", default="groq:openai/gpt-oss-120b")
    solve.add_argument("--weak-solver", default="groq:openai/gpt-oss-20b")
    solve.add_argument("--weak-reasoning", default="low", choices=["low", "medium", "high"])
    solve.set_defaults(func=cmd_solve)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
