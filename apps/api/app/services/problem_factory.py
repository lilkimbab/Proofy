"""Generate hard 수능 problems one at a time, verify them, and queue them for review.

Why it is built this way (see the 2026-11-23 probe):
- The old bundle generator asked for lessons, scenes and problems in one call
  and required an explicit f(x) and point for every problem, so it could only
  produce 1-2 point drills, and 3 of 4 answers were wrong.
- Asked for one problem at a time with room to think, Gemini Flash produced
  correct 4-point problems; Groq gpt-oss-120b produced correct but 2-3 point
  ones even when asked for #22.
- A second model solving blind agreed 3 of 4 times and wrongly rejected a
  valid problem once, so SymPy, not another model, decides correctness.

Pipeline per problem:
  generate -> SymPy check (repair on failure) -> strong blind solve
  -> weak blind solve (if the weak model solves it, it is not a #22: harden)
  -> save with status, difficulty signals and full history for human review.
"""
from __future__ import annotations

import json
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from app.content.problem_archetypes import Archetype, UnitBlueprint, archetype_for, blueprint_for
from app.domain.problem_verifier import HELPER_GUIDE, VerificationReport, verify_problem
from app.services.llm_client import LLMClient, LLMError, LLMResult, ModelUnavailable

API_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE_ROOT = API_ROOT / "data" / "generated"

TARGETS = {
    "22": "수능 공통 22번 (마지막 단답형, 정답률 한 자릿수 %)",
    "4": "수능 4점 (20~21번 수준)",
}

GENERATOR_SYSTEM = """너는 평가원 수능 수학 출제위원이다. 새 문항을 한국어로 출제한다.

어려운 문항(특히 22번)이 어려운 이유:
1. 함수를 직접 주지 않는다. '최고차항의 계수가 1인 삼차함수 f(x)'처럼 미지의 함수와, 그것으로 정의한 g(x), h(t) 같은 새 함수가 나온다.
2. 조건 하나만으로는 후보가 여러 개 남는다. 다른 조건으로 케이스를 하나씩 지워야 f가 하나로 정해진다.
3. 케이스 분기가 두 단계 이상이다 (예: 중근의 위치 × 상수의 부호). 대부분이 모순으로 탈락하는데, 그 모순이 눈에 잘 띄지 않는다.
4. 숨은 조건이 있다: 연속에서 나오는 등식, 정수 조건, '모든 실수 t에 대하여', 최솟값이 존재한다는 사실 자체 등.
5. f를 구한 뒤에도 마지막 계산이 한 번 더 남아 있다.
6. 그래도 교육과정 범위 안이고, 손으로 풀 수 있으며, 정답은 1 이상 999 이하의 자연수 하나다.

출제 순서:
1. 정답이 될 함수 f를 먼저 정한다 (계수는 정수나 간단한 분수).
2. 지정된 메커니즘으로 조건을 설계한다.
3. 조건만 보고 처음부터 풀면서, 처음에 가능한 경우를 전부 적고 각각이 어떤 조건에서 왜 탈락하는지 확인한다.
4. f가 정확히 하나로 정해지는지 확인한다. 두 개 이상이거나 하나도 없으면 조건을 고친다.
5. 너무 쉬우면 조건을 간접적으로 바꾼다 (값 대신 개수·불연속·미분가능성으로 주기).

이미 쓴 문제를 베끼거나 숫자만 바꾸지 말 것. 실제 기출 문항을 그대로 쓰지 말 것."""

FORMAT_RULES = """본문 표기 규칙 (앱 화면은 LaTeX를 그리지 못한다)
- LaTeX, $, 백슬래시를 쓰지 않는다.
- 거듭제곱 x^3, 아래첨자 a_n, 도함수 f'(x), 절댓값 |f(x)|, 분수 a/b (복잡하면 (x+1)/(x-2)), 루트 √3, 부등호 ≤ ≥ ≠.
- 정적분은 ∫_a^b f(x)dx, 극한은 lim_(x→a) 로 쓴다.
- 구간별 함수는 g(x) = { f(x) (x < 1), |f(x) - k| (x ≥ 1) } 처럼 한 줄로 쓴다.
- 조건은 줄을 바꿔 (가) ..., (나) ... 로 쓴다.
- 마지막 문장은 '...의 값을 구하시오.'로 끝낸다."""

OUTPUT_SCHEMA = """출력은 JSON 하나만:
{
  "statement": "문제 본문",
  "answer": 정수,
  "solution": ["풀이 단계. 케이스를 나누는 곳에서는 각 케이스와 탈락 이유를 적는다", "..."],
  "cases": ["가능한 구조 1 (위치는 일반적으로 둔 채): ... → (나)에서 탈락하는 이유", "..."],
  "trap": "중상위권 학생이 실제로 틀리는 지점 한 줄",
  "whyHard": "이 문항이 목표 난이도인 이유 한두 줄",
  "verify": {
    "f": "조건으로 정해지는 f(x)를 SymPy 식으로 (예: x**3 - 6*x**2 + 9*x)",
    "define": [["k", "2"], ["g", "Abs(f - at(f, 1))"]],
    "checks": [{"condition": "(가)", "expr": "len(nondiff_points(g)) == 1"}],
    "answer": "at(f, 6)"
  }
}

cases 작성 규칙
- 미지의 함수가 가질 수 있는 구조를 빠짐없이 나눈다. 삼차식이면 서로 다른 세 실근 / 단근+중근 / 삼중근 / 실근 하나+허근 둘, 그리고 각 근이 기준점의 어느 쪽에 있는지까지.
- 근의 위치를 특정 값(예: x = 1)으로 미리 정하지 않는다. 삼중근 (x - t)^3 이면 t가 아무 값일 때를 따진다.
- 출제 후 검토위원이 놓친 경우를 찾아 SymPy로 확인한다. 답이 둘 이상이면 문항은 버려진다.

verify 작성 규칙
- checks에는 문제의 조건을 하나도 빠짐없이, 약하게 만들지 않고 옮긴다. ('미분 불가능한 점이 1개'를 '미분 불가능한 점이 있다'로 옮기면 안 된다.)
- 조건은 가능하면 helper 하나로 옮긴다: 극값은 local_max_values(g), 미분가능성은 is_differentiable(g), 실근 개수는 root_count. 이계도함수 판정이나 구간을 직접 나누는 논리를 새로 짜지 않는다 (다른 함수에도 그대로 맞아야 한다).
- '모든 실수 t에 대하여'처럼 무한히 많은 경우를 말하는 조건은 helper(level_jumps 등)로 정확히 옮기거나, 경계값과 그 양옆 값을 모두 확인한다.
- 문제에 나오는 상수(k, a 등)는 define으로 그 값을 정한다.
- 분수는 Rational(p, q)로 쓴다. 비교는 == 대신 same(u, v)를 쓴다.
- answer는 f와 define한 이름으로 정답을 계산하는 식이다."""

SOLVER_SYSTEM = "너는 수능 수학 만점자다. 풀이를 꼼꼼히 검토한 뒤 답한다."

SOLVER_TEMPLATE = """다음 문제를 풀어라. 조건을 만족하는 함수가 여러 개이거나 하나도 없으면 그렇다고 말하라.

{statement}

JSON 하나만 출력:
{{"answer": 정수 또는 null, "unique": true 또는 false, "issue": "문제에 결함이 있으면 한 줄, 없으면 빈 문자열", "keyStep": "결정적인 한 단계"}}"""

REFUTER_SYSTEM = "너는 수능 출제 검토위원이다. 출제자가 놓친 경우를 찾아내는 것이 네 일이다."

REFUTER_TEMPLATE = """다음 문항은 조건을 만족하는 함수가 하나뿐이고 정답이 {answer}이라고 한다.

[문제]
{statement}

[출제자 풀이]
{solution}

할 일
1. 미지의 함수와 상수를 일반적인 꼴로 둔다. 근의 위치나 상수를 출제자처럼 특정 값으로 미리 고정하지 않는다.
2. 가능한 구조를 빠짐없이 나눈다 (삼차식이면 서로 다른 세 실근 / 단근+중근 / 삼중근 / 실근 하나+허근 둘, 각 근의 위치까지). 출제자 풀이가 다루지 않은 경우를 특히 확인한다.
3. 출제자와 다른 함수가 모든 조건을 만족하면 그 함수와 상수를 정확한 값으로 적는다 (무리수면 sqrt, Rational, 거듭제곱근은 3**Rational(1, 4) 꼴).
4. 문제 문장이 수학적으로 성립하지 않으면 (예: 삼차함수의 최솟값, 정의되지 않는 값) 그것도 적는다.
찾지 못했으면 지어내지 말고 null로 둔다.

JSON 하나만:
{{"counterexample": null 또는 {{"f": "SymPy 식", "define": [["상수 이름", "값"]], "note": "어떤 경우인지 한 줄"}}, "statementIssue": "문장 결함이 있으면 한 줄, 없으면 빈 문자열"}}"""


# ----------------------------------------------------------------------------
# prompts
# ----------------------------------------------------------------------------


def generation_prompt(blueprint: UnitBlueprint, archetype: Archetype, target: str, avoid: list[str]) -> str:
    avoid_block = "\n".join(f"- {item}" for item in avoid) if avoid else "- (없음)"
    return f"""{blueprint.course} '{blueprint.domain}' 단원에서 {TARGETS[target]} 문항 한 개를 새로 출제하라.

범위: {blueprint.scope}

메커니즘: {archetype.name}
- 구조: {archetype.mechanism}
- 실제로 갈리는 지점: {archetype.traps}
- 더 어렵게 만드는 방법: {archetype.levers}

이 단원에서 이미 만든 문제 (비슷하게 만들지 말 것):
{avoid_block}

{FORMAT_RULES}

{OUTPUT_SCHEMA}

{HELPER_GUIDE}"""


def repair_prompt(draft: dict[str, Any], failures: list[str]) -> str:
    failure_block = "\n".join(f"- {line}" for line in failures)
    return f"""아래는 네가 출제한 문항이다. SymPy로 검산했더니 다음이 실패했다.

{failure_block}

원인을 찾아 고쳐라. 문제의 조건이나 정답이 틀렸으면 문제를 고치고, verify로 옮기는 과정이 틀렸으면 verify만 고친다.
고친 뒤 처음부터 다시 풀어 f가 하나로 정해지는지 확인하라. 출력 형식은 처음과 같다.

[이전 출력]
{json.dumps(draft, ensure_ascii=False, indent=2)}

{FORMAT_RULES}

{OUTPUT_SCHEMA}

{HELPER_GUIDE}"""


def harden_prompt(draft: dict[str, Any], weak_solve: dict[str, Any], target: str, archetype: Archetype) -> str:
    return f"""아래 문항은 {TARGETS[target]}로 쓰기에는 쉽다. 약한 풀이 모델도 정답 {weak_solve.get('answer')}을(를) 맞혔다.
그 모델이 짚은 결정적 단계: {weak_solve.get('keyStep') or '(없음)'}

같은 메커니즘({archetype.name})을 유지하면서, 다음 중 두 가지 이상을 적용해 새로 출제하라.
- 값을 직접 주는 조건을 개수·불연속·미분가능성 같은 간접 조건으로 바꾼다.
- 케이스 분기를 한 단계 더 만든다. 새로 생긴 케이스는 다른 조건과 맞물려야만 탈락하게 한다.
- 숨은 조건(연속성, 정수, '모든 실수 t에 대하여')을 하나 넣는다.
- f를 구한 뒤 마지막 계산을 한 단계 더 꼰다.
- {archetype.levers}

정답은 여전히 1 이상 999 이하의 자연수이고, f는 정확히 하나로 정해져야 한다.

[이전 문항]
{json.dumps({key: draft.get(key) for key in ("statement", "answer", "solution", "cases")}, ensure_ascii=False, indent=2)}

{FORMAT_RULES}

{OUTPUT_SCHEMA}

{HELPER_GUIDE}"""


# ----------------------------------------------------------------------------
# statement clean-up
# ----------------------------------------------------------------------------

_LATEX_REPLACEMENTS = [
    (r"\\left|\\right", ""),
    (r"\\leq?(?![a-zA-Z])", "≤"),
    (r"\\geq?(?![a-zA-Z])", "≥"),
    (r"\\neq?(?![a-zA-Z])", "≠"),
    (r"\\cdot", "·"),
    (r"\\times", "×"),
    (r"\\infty", "∞"),
    (r"\\int(?![a-zA-Z])", "∫"),
    (r"\\lim(?![a-zA-Z])", "lim"),
    (r"\\to(?![a-zA-Z])", "→"),
    (r"\\rightarrow", "→"),
    (r"\\pi(?![a-zA-Z])", "π"),
    (r"\\alpha", "α"),
    (r"\\beta", "β"),
    (r"\\gamma", "γ"),
    (r"\\[,;:! ]|\\quad|\\qquad", " "),
    (r"\\\{", "{"),
    (r"\\\}", "}"),
    (r"\\mid|\\lvert|\\rvert|\\vert", "|"),
    (r"\\text\{([^{}]*)\}", r"\1"),
    (r"\\mathrm\{([^{}]*)\}", r"\1"),
]


def to_app_notation(text: str) -> tuple[str, list[str]]:
    """Turn stray LaTeX into the plain notation MathText renders; report what is left."""
    value = (text or "").replace("$$", "").replace("$", "")
    value = re.sub(
        r"\\begin\{cases\}(.*?)\\end\{cases\}",
        lambda match: "{ " + ", ".join(
            re.sub(r"\s+", " ", part.replace("&", " ")).strip()
            for part in match.group(1).split("\\\\")
            if part.strip()
        ) + " }",
        value,
        flags=re.S,
    )
    for _ in range(3):
        value = re.sub(r"\\[dt]?frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", value)
        value = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", value)
    for pattern, replacement in _LATEX_REPLACEMENTS:
        value = re.sub(pattern, replacement, value)
    value = re.sub(r"\^\{([^{}]*)\}", lambda m: "^" + m.group(1) if len(m.group(1)) == 1 else "^{" + m.group(1) + "}", value)
    value = re.sub(r"_\{([^{}]*)\}", lambda m: "_" + m.group(1) if len(m.group(1)) == 1 else "_{" + m.group(1) + "}", value)
    value = re.sub(r"\((\w+)\)/\((\w+)\)", r"\1/\2", value)
    value = re.sub(r"√\((\w+)\)", r"√\1", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = "\n".join(line.strip() for line in value.splitlines()).strip()
    issues: list[str] = []
    if "\\" in value:
        leftover = sorted(set(re.findall(r"\\[a-zA-Z]+", value)))
        issues.append(f"LaTeX가 남아 있음: {', '.join(leftover) or '백슬래시'}")
    return value, issues


REQUIRED_FIELDS = ("statement", "answer", "solution", "verify")


def draft_problems(draft: dict[str, Any] | None) -> list[str]:
    if not isinstance(draft, dict):
        return ["JSON 객체가 아님"]
    issues = [f"'{name}' 항목이 없음" for name in REQUIRED_FIELDS if not draft.get(name)]
    verify = draft.get("verify")
    if verify is not None and not isinstance(verify, dict):
        issues.append("verify가 객체가 아님")
    answer = draft.get("answer")
    if answer is not None and _as_int(answer) is None:
        issues.append(f"answer가 정수가 아님: {answer!r}")
    return issues


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
        return int(value)
    return None


# ----------------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------------


class ProblemStore:
    def __init__(self, root: Path = DEFAULT_STORE_ROOT) -> None:
        self.root = Path(root)

    def _unit_dir(self, unit_id: str) -> Path:
        return self.root / "problems" / unit_id

    def save(self, record: dict[str, Any]) -> Path:
        directory = self._unit_dir(record["unitId"])
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{record['id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return path

    def all(self, unit_id: str | None = None) -> list[dict[str, Any]]:
        base = self.root / "problems"
        if not base.exists():
            return []
        pattern = f"{unit_id}/*.json" if unit_id else "*/*.json"
        records = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(base.glob(pattern))]
        return sorted(records, key=lambda item: item.get("createdAt", ""))

    def get(self, record_id: str) -> dict[str, Any] | None:
        for path in (self.root / "problems").glob(f"*/{record_id}.json"):
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def recent_statements(self, unit_id: str, limit: int = 8) -> list[str]:
        records = [item for item in self.all(unit_id) if item.get("status") != "rejected"]
        lines = []
        for record in records[-limit:]:
            statement = re.sub(r"\s+", " ", record.get("problem", {}).get("statement", ""))
            lines.append(f"[{record.get('archetype')}] {statement[:140]}")
        return lines

    def least_used_archetype(self, blueprint: UnitBlueprint) -> Archetype:
        counts = {archetype.id: 0 for archetype in blueprint.archetypes}
        for record in self.all(blueprint.unit_id):
            if record.get("archetype") in counts and record.get("status") != "rejected":
                counts[record["archetype"]] += 1
        return min(blueprint.archetypes, key=lambda archetype: counts[archetype.id])


# ----------------------------------------------------------------------------
# pipeline
# ----------------------------------------------------------------------------


@dataclass
class FactoryConfig:
    generator_models: list[str]
    strong_solver: str = "groq:openai/gpt-oss-120b"
    weak_solver: str = "groq:openai/gpt-oss-20b"
    weak_reasoning: str = "low"
    max_repairs: int = 2
    max_hardens: int = 2
    second_opinion: bool = True
    refuter: str | None = "groq:openai/gpt-oss-120b"
    verify_timeout: int = 60
    busy_retries: int = 2
    busy_wait_seconds: int = 90


class GeneratorUnavailable(RuntimeError):
    pass


@dataclass
class _Attempt:
    draft: dict[str, Any]
    report: VerificationReport
    format_issues: list[str] = field(default_factory=list)
    refuter: dict[str, Any] = field(default_factory=dict)

    def flags(self) -> list[str]:
        """Doubts a reviewer should see even though SymPy passed."""
        found: list[str] = []
        if self.refuter.get("statementIssue"):
            found.append(f"문장 결함 지적: {self.refuter['statementIssue']}")
        counter = self.refuter.get("counterexample")
        if isinstance(counter, dict) and counter.get("f") and not self.refuter.get("confirmed"):
            found.append(f"확인되지 않은 반례 주장: f(x) = {counter['f']} ({counter.get('note', '')})")
        if self.refuter.get("error"):
            found.append(f"반례 검토를 못 함: {self.refuter['error'][:120]}")
        return found


def counterexample_spec(verify: dict[str, Any], counter: dict[str, Any]) -> dict[str, Any]:
    """The problem's own checks, applied to the refuter's alternative f and constants."""
    overrides: dict[str, str] = {}
    for item in counter.get("define") or []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            overrides[str(item[0])] = str(item[1])
    define: list[list[str]] = []
    for item in verify.get("define") or []:
        name, source = str(item[0]), str(item[1])
        define.append([name, overrides.pop(name, source)])
    return {**verify, "f": str(counter["f"]), "define": [[name, source] for name, source in overrides.items()] + define}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _solve_summary(role: str, result: LLMResult | None, expected: int, error_text: str = "") -> dict[str, Any]:
    if result is None:
        return {"role": role, "model": "", "error": error_text, "correct": None}
    data = result.data or {}
    answer = _as_int(data.get("answer"))
    return {
        "role": role,
        "model": result.model,
        "answer": answer,
        "correct": answer == expected,
        "unique": data.get("unique"),
        "issue": data.get("issue", ""),
        "keyStep": data.get("keyStep", ""),
        "reasoningTokens": result.reasoning_tokens,
        "outputTokens": result.output_tokens,
        "elapsed": round(result.elapsed, 1),
    }


class ProblemFactory:
    def __init__(
        self,
        config: FactoryConfig,
        *,
        client: LLMClient | None = None,
        store: ProblemStore | None = None,
        verifier: Callable[..., VerificationReport] = verify_problem,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.log = log or (lambda message: None)
        self.client = client or LLMClient(log=self.log)
        self.store = store or ProblemStore()
        self.verifier = verifier
        self.sleep = time.sleep
        self.calls: list[dict[str, Any]] = []

    # -- llm helpers -------------------------------------------------------
    def _generate(self, prompt: str, kind: str) -> tuple[dict[str, Any] | None, LLMResult]:
        last_error = ""
        for attempt in range(self.config.busy_retries + 1):
            if attempt:
                self.log(f"  [{kind}] 모든 출제 모델이 바쁨 → {self.config.busy_wait_seconds}초 뒤 다시 시도 ({attempt}/{self.config.busy_retries})")
                self.sleep(self.config.busy_wait_seconds)
            busy = False
            for model in self.config.generator_models:
                try:
                    self.log(f"  [{kind}] {model} 출제 중...")
                    result = self.client.complete_json(model, GENERATOR_SYSTEM, prompt, temperature=0.9, reasoning="high", timeout=420)
                except LLMError as exc:
                    busy = busy or isinstance(exc, ModelUnavailable)
                    last_error = str(exc)
                    self.log(f"  [{kind}] {model} 사용 불가: {last_error.splitlines()[0][:160]}")
                    continue
                self.calls.append({"kind": kind, "model": model, "elapsed": round(result.elapsed, 1), "reasoningTokens": result.reasoning_tokens})
                return result.data, result
            if not busy:
                break  # waiting will not fix a rejected request (e.g. too large)
        raise GeneratorUnavailable(last_error or "no generator model configured")

    def _solve(self, model: str, statement: str, expected: int, role: str, reasoning: str = "high") -> dict[str, Any]:
        try:
            self.log(f"  [{role}] {model} 풀이 중...")
            result = self.client.complete_json(model, SOLVER_SYSTEM, SOLVER_TEMPLATE.format(statement=statement), temperature=0.2, reasoning=reasoning, timeout=420)
        except LLMError as exc:
            self.log(f"  [{role}] {model} 실패: {exc}")
            return _solve_summary(role, None, expected, str(exc))
        self.calls.append({"kind": f"solve-{role}", "model": model, "elapsed": round(result.elapsed, 1), "reasoningTokens": result.reasoning_tokens})
        summary = _solve_summary(role, result, expected)
        self.log(f"  [{role}] 답 {summary['answer']} (출제 답 {expected}) 생각 토큰 {summary['reasoningTokens']}")
        return summary

    # -- one draft through checks -------------------------------------------
    def _check(self, draft: dict[str, Any] | None) -> _Attempt:
        issues = draft_problems(draft)
        if issues:
            return _Attempt(draft=draft if isinstance(draft, dict) else {}, report=VerificationReport(ok=False, errors=issues))
        draft = dict(draft)
        draft["statement"], format_issues = to_app_notation(str(draft["statement"]))
        report = self.verifier(draft["verify"], _as_int(draft["answer"]), timeout_seconds=self.config.verify_timeout)
        if format_issues:
            report.ok = False
            report.errors.extend(format_issues)
        refuter: dict[str, Any] = {}
        if report.ok:
            refuter = self._refute(draft)
            if refuter.get("confirmed"):
                counter = refuter["counterexample"]
                report.ok = False
                report.errors.append(
                    f"답이 하나로 정해지지 않음: f(x) = {counter['f']} ({counter.get('note', '')}) 도 모든 조건을 만족하고 "
                    f"이때 답은 {refuter.get('alternativeAnswer')}. 이 경우가 빠지도록 조건을 고쳐라."
                )
        return _Attempt(draft=draft, report=report, format_issues=format_issues, refuter=refuter)

    def _refute(self, draft: dict[str, Any]) -> dict[str, Any]:
        model = self.config.refuter
        if not model:
            return {}
        prompt = REFUTER_TEMPLATE.format(
            answer=draft["answer"],
            statement=draft["statement"],
            solution="\n".join(f"- {step}" for step in draft.get("solution") or []),
        )
        try:
            self.log(f"  [refute] {model} 놓친 경우 찾는 중...")
            result = self.client.complete_json(model, REFUTER_SYSTEM, prompt, temperature=0.3, reasoning="high", timeout=420)
        except LLMError as exc:
            self.log(f"  [refute] 실패: {str(exc)[:120]}")
            return {"model": model, "error": str(exc)}
        self.calls.append({"kind": "refute", "model": model, "elapsed": round(result.elapsed, 1), "reasoningTokens": result.reasoning_tokens})
        data = result.data or {}
        counter = data.get("counterexample")
        outcome: dict[str, Any] = {
            "model": model,
            "statementIssue": str(data.get("statementIssue") or ""),
            "counterexample": counter if isinstance(counter, dict) and counter.get("f") else None,
            "confirmed": False,
            "reasoningTokens": result.reasoning_tokens,
        }
        if outcome["counterexample"]:
            alternative = self.verifier(
                counterexample_spec(draft["verify"], counter), _as_int(draft["answer"]), timeout_seconds=self.config.verify_timeout
            )
            holds = not alternative.errors and bool(alternative.checks) and all(check.ok for check in alternative.checks)
            outcome["alternativeAnswer"] = alternative.answer_value
            outcome["alternativeChecks"] = [check.ok for check in alternative.checks]
            outcome["alternativeErrors"] = alternative.errors[:3]
            outcome["confirmed"] = holds and not alternative.answer_matches
            self.log(
                f"  [refute] 반례 주장 → SymPy {'확인: 답이 둘 이상' if outcome['confirmed'] else '확인 안 됨'} "
                f"(조건 {outcome['alternativeChecks']}, 그때 답 {str(alternative.answer_value)[:40]})"
            )
        elif outcome["statementIssue"]:
            self.log(f"  [refute] 문장 결함 지적: {outcome['statementIssue'][:120]}")
        return outcome

    def _verified_draft(self, prompt: str, kind: str, rounds: list[dict[str, Any]]) -> _Attempt:
        data, result = self._generate(prompt, kind)
        attempt = self._check(data)
        rounds.append(self._round(kind, result, attempt))
        repairs = 0
        while not attempt.report.ok and repairs < self.config.max_repairs:
            repairs += 1
            failures = attempt.report.failure_summary()
            self.log(f"  검산 실패 → 수정 요청 {repairs}/{self.config.max_repairs}: {' / '.join(failures)[:200]}")
            try:
                data, result = self._generate(repair_prompt(attempt.draft, failures), "repair")
            except GeneratorUnavailable as exc:
                self.log(f"  수정 요청 중단: {str(exc).splitlines()[0][:160]}")
                break
            attempt = self._check(data)
            rounds.append(self._round("repair", result, attempt))
        return attempt

    @staticmethod
    def _round(kind: str, result: LLMResult, attempt: _Attempt) -> dict[str, Any]:
        return {
            "kind": kind,
            "model": result.model,
            "elapsed": round(result.elapsed, 1),
            "reasoningTokens": result.reasoning_tokens,
            "outputTokens": result.output_tokens,
            "verificationOk": attempt.report.ok,
            "failures": attempt.report.failure_summary(),
            "refuter": attempt.refuter,
            "draft": attempt.draft,
        }

    # -- public ------------------------------------------------------------
    def run(self, unit_id: str, *, target: str = "22", archetype_id: str | None = None) -> dict[str, Any]:
        if target not in TARGETS:
            raise ValueError(f"target must be one of {sorted(TARGETS)}")
        blueprint = blueprint_for(unit_id)
        archetype = archetype_for(blueprint, archetype_id) if archetype_id else self.store.least_used_archetype(blueprint)
        self.log(f"{blueprint.course} {blueprint.domain} · {archetype.name} · 목표 {TARGETS[target]}")
        rounds: list[dict[str, Any]] = []
        solves: list[dict[str, Any]] = []

        attempt = self._verified_draft(
            generation_prompt(blueprint, archetype, target, self.store.recent_statements(unit_id)), "generate", rounds
        )
        best: tuple[_Attempt, list[dict[str, Any]]] | None = None
        hardens = 0
        while attempt.report.ok:
            expected = _as_int(attempt.draft["answer"])
            statement = attempt.draft["statement"]
            round_solves = [self._solve(self.config.strong_solver, statement, expected, "strong")]
            if not round_solves[0]["correct"] and self.config.second_opinion:
                for second_model in self.config.generator_models:
                    second = self._solve(second_model, statement, expected, "second")
                    if not second.get("error"):
                        round_solves.append(second)
                        break
            weak = self._solve(self.config.weak_solver, statement, expected, "weak", reasoning=self.config.weak_reasoning)
            round_solves.append(weak)
            solves.extend({**item, "round": len(rounds)} for item in round_solves)
            best = (attempt, round_solves)
            if not (target == "22" and weak["correct"] and hardens < self.config.max_hardens):
                break
            hardens += 1
            self.log(f"  약한 모델이 풀었음 → 더 어렵게 {hardens}/{self.config.max_hardens}")
            try:
                attempt = self._verified_draft(harden_prompt(attempt.draft, weak, target, archetype), "harden", rounds)
            except GeneratorUnavailable as exc:
                self.log(f"  더 어렵게 만들기 중단: {exc}")
                break
            if not attempt.report.ok:
                self.log("  어렵게 바꾼 문항이 검산을 통과하지 못해 이전 문항을 남김")

        record = self._record(blueprint, archetype, target, best, attempt, rounds, solves)
        path = self.store.save(record)
        self.log(f"저장: {path} · 상태 {record['status']} · 난이도 판정 {record['difficulty']['verdict']}")
        return record

    def _record(
        self,
        blueprint: UnitBlueprint,
        archetype: Archetype,
        target: str,
        best: tuple[_Attempt, list[dict[str, Any]]] | None,
        last: _Attempt,
        rounds: list[dict[str, Any]],
        solves: list[dict[str, Any]],
    ) -> dict[str, Any]:
        final = best[0] if best else last
        final_solves = best[1] if best else []
        strong = next((item for item in final_solves if item["role"] == "strong"), None)
        second = next((item for item in final_solves if item["role"] == "second"), None)
        weak = next((item for item in final_solves if item["role"] == "weak"), None)
        flags = final.flags() if final.report.ok else []
        if not final.report.ok:
            status = "rejected"
        elif ((strong and strong.get("correct")) or (second and second.get("correct"))) and not flags:
            status = "verified"
        else:
            status = "disputed"
        if status == "rejected" or weak is None or weak.get("correct") is None:
            verdict = "unknown"
        elif weak["correct"]:
            verdict = "too-easy"
        else:
            verdict = "hard"
        draft = final.draft
        return {
            "id": f"gen-{blueprint.unit_id}-{datetime.now(UTC):%Y%m%d}-{secrets.token_hex(3)}",
            "unitId": blueprint.unit_id,
            "course": blueprint.course,
            "domain": blueprint.domain,
            "archetype": archetype.id,
            "archetypeName": archetype.name,
            "target": target,
            "createdAt": _now(),
            "status": status,
            "flags": flags,
            "difficulty": {
                "verdict": verdict,
                "weakSolver": weak.get("model") if weak else None,
                "weakSolved": weak.get("correct") if weak else None,
                "strongReasoningTokens": strong.get("reasoningTokens") if strong else None,
                "hardenRounds": sum(1 for item in rounds if item["kind"] == "harden"),
            },
            "review": {"state": "pending", "note": "", "reviewedAt": None},
            "problem": {
                "statement": draft.get("statement", ""),
                "answer": _as_int(draft.get("answer")),
                "solution": draft.get("solution", []),
                "cases": draft.get("cases", []),
                "trap": draft.get("trap", ""),
                "whyHard": draft.get("whyHard", ""),
                "verify": draft.get("verify", {}),
            },
            "verification": final.report.to_dict(),
            "refuter": final.refuter,
            "solves": solves,
            "rounds": rounds,
        }


# ----------------------------------------------------------------------------
# review helpers and export to the app's problem format
# ----------------------------------------------------------------------------


def set_review(store: ProblemStore, record_id: str, *, approve: bool, note: str = "") -> dict[str, Any]:
    record = store.get(record_id)
    if record is None:
        raise KeyError(record_id)
    if approve and record.get("status") == "rejected":
        raise ValueError("SymPy 검산을 통과하지 못한 문항은 승인할 수 없습니다")
    record["review"] = {"state": "approved" if approve else "rejected", "note": note, "reviewedAt": _now()}
    store.save(record)
    return record


def to_app_problem(record: dict[str, Any]) -> dict[str, Any]:
    from app.content.curriculum_seed import PDF_SOURCE_PATH, UNIT_SPECS

    unit = next((item for item in UNIT_SPECS if item["id"] == record["unitId"]), None)
    problem = record["problem"]
    answer = str(problem["answer"])
    return {
        "id": record["id"],
        "title": record.get("archetypeName", ""),
        "statement": problem["statement"],
        "coachHint": problem.get("trap", ""),
        "expectedOutline": list(problem.get("solution", [])),
        "functionSpec": {},
        "evaluationType": "structured-generic",
        "stepGuide": [],
        "finalPrompt": "정답 (자연수)",
        "difficulty": "apex" if record.get("target") == "22" else "killer",
        "problemType": record.get("archetypeName", ""),
        "isKiller": True,
        "gradingSpec": {
            "steps": [],
            "final": {
                "label": "최종 답",
                "mode": "numeric",
                "expected": [answer],
                "hint": "조건을 하나씩 다시 대입해 보세요.",
                "successReason": "정답입니다.",
                "errorType": "arithmetic",
                "expectedDisplay": answer,
            },
        },
        "curriculumLinks": {
            "courseTitle": record.get("course", ""),
            "unitTitle": f"{record.get('course', '')} - {record.get('domain', '')}",
            "achievementCodes": unit["achievementCodes"] if unit else [],
            "sourcePdf": PDF_SOURCE_PATH,
        },
        "solution": list(problem.get("solution", [])),
        "generation": {
            "archetype": record.get("archetype"),
            "target": record.get("target"),
            "status": record.get("status"),
            "difficultyVerdict": record.get("difficulty", {}).get("verdict"),
            "reviewedAt": record.get("review", {}).get("reviewedAt"),
        },
    }


def export_approved(store: ProblemStore, unit_id: str | None = None) -> dict[str, Path]:
    by_unit: dict[str, list[dict[str, Any]]] = {}
    for record in store.all(unit_id):
        if record.get("review", {}).get("state") == "approved" and record.get("status") != "rejected":
            by_unit.setdefault(record["unitId"], []).append(to_app_problem(record))
    written: dict[str, Path] = {}
    out_dir = store.root / "approved"
    out_dir.mkdir(parents=True, exist_ok=True)
    for unit, problems in by_unit.items():
        path = out_dir / f"{unit}.json"
        path.write_text(json.dumps(problems, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written[unit] = path
    return written
