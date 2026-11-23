from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from core.analyzer import analyze
from core.data_collector import DataCollector
from core.planner import Planner
from core.scheduler import get_due_today, sm2_update, SM2Record

from .schemas import (
    GenerateRequest,
    ProgressUpdateRequest,
    ReviewUpdateRequest,
    RoadmapSchema,
    TodayPlanResponse,
)

router = APIRouter()

_collector = DataCollector()
_planner = Planner()


@router.post("/roadmap/generate", response_model=RoadmapSchema)
async def generate_roadmap(req: GenerateRequest):
    data = await _collector.collect(req.user_id, req.doc_id)
    if not data.sections:
        raise HTTPException(status_code=404, detail=f"doc_id '{req.doc_id}'의 material.json을 찾을 수 없습니다. document_agent에서 먼저 자료를 생성하세요.")
    analysis = analyze(data)
    roadmap = await _planner.generate(req.user_id, req.doc_id, data, analysis)
    return roadmap


@router.get("/roadmap/{user_id}/{doc_id}", response_model=RoadmapSchema)
async def get_roadmap(user_id: str, doc_id: str):
    roadmap = _planner.load(user_id, doc_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다. /roadmap/generate로 먼저 생성하세요.")
    return roadmap


@router.get("/roadmap/{user_id}/{doc_id}/today", response_model=TodayPlanResponse)
async def get_today_plan(user_id: str, doc_id: str):
    roadmap = _planner.load(user_id, doc_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다")
    today = date.today().isoformat()
    study_items = [p for p in roadmap.get("daily_plan", []) if p.get("date") == today]
    sm2_records = [SM2Record.from_dict(r) for r in roadmap.get("review_schedule", [])]
    due = get_due_today(sm2_records)
    review_concepts = [r.concept for r in due]
    estimated = sum(p.get("estimated_minutes", 0) for p in study_items)
    return {
        "date": today,
        "study_items": study_items,
        "review_concepts": review_concepts,
        "estimated_minutes": estimated,
    }


@router.get("/roadmap/{user_id}/{doc_id}/schedule")
async def get_review_schedule(user_id: str, doc_id: str):
    roadmap = _planner.load(user_id, doc_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다")
    return roadmap.get("review_schedule", [])


@router.patch("/roadmap/{user_id}/{doc_id}/progress")
async def update_progress(user_id: str, doc_id: str, req: ProgressUpdateRequest):
    roadmap = _planner.load(user_id, doc_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다")

    matched = False
    for item in roadmap.get("daily_plan", []):
        # section_id 직접 매칭 (신규 필드) 또는 section_titles 폴백
        if item.get("section_id") == req.section_id or req.section_id in item.get("section_titles", []):
            item["status"] = "완료" if req.completed else "예정"
            matched = True
            break

    if not matched:
        raise HTTPException(status_code=404, detail=f"section_id '{req.section_id}'에 해당하는 학습 항목이 없습니다")

    _planner._save(user_id, doc_id, roadmap)
    return {"message": "진도가 업데이트되었습니다"}


@router.post("/roadmap/{user_id}/{doc_id}/review")
async def update_review_result(user_id: str, doc_id: str, req: ReviewUpdateRequest):
    """
    퀴즈/복습 결과를 SM-2 알고리즘에 반영한다.
    quality 0-2: 오답 → 간격 초기화, ease_factor 감소
    quality 3-5: 정답 → 간격 연장, ease_factor 증가
    """
    roadmap = _planner.load(user_id, doc_id)
    if not roadmap:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다")

    records = [SM2Record.from_dict(r) for r in roadmap.get("review_schedule", [])]
    updated_record: SM2Record | None = None
    for record in records:
        if record.concept == req.concept:
            sm2_update(record, req.quality)
            updated_record = record
            break

    if updated_record is None:
        raise HTTPException(status_code=404, detail=f"개념 '{req.concept}'이 복습 일정에 없습니다")

    roadmap["review_schedule"] = [r.to_dict() for r in records]
    _planner._save(user_id, doc_id, roadmap)
    return {
        "message": "복습 결과가 기록되었습니다",
        "concept": updated_record.concept,
        "next_review": updated_record.next_review,
        "interval_days": updated_record.interval_days,
        "ease_factor": round(updated_record.ease_factor, 3),
    }


@router.delete("/roadmap/{user_id}/{doc_id}")
async def delete_roadmap(user_id: str, doc_id: str):
    deleted = _planner.delete(user_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="저장된 로드맵이 없습니다")
    return {"message": "로드맵이 삭제되었습니다"}


@router.get("/roadmap/{user_id}/{doc_id}/view", response_class=HTMLResponse)
async def view_roadmap(user_id: str, doc_id: str):
    roadmap = _planner.load(user_id, doc_id)
    if not roadmap:
        return HTMLResponse(
            "<html><body><h1>로드맵 없음</h1><p>/roadmap/generate로 먼저 생성하세요.</p></body></html>",
            status_code=404,
        )
    return HTMLResponse(_render_html(_safe_json(roadmap)))


def _safe_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False).replace("</script>", "<\\/script>")


def _render_html(data_json: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>학습 로드맵</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f8fafc;color:#1e293b;line-height:1.6}}
.wrap{{max-width:860px;margin:0 auto;padding:24px 16px}}
h1{{font-size:1.5rem;font-weight:700}}
h2{{font-size:1rem;font-weight:600;color:#334155;margin-bottom:12px}}
.card{{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.today{{border:2px solid #4f46e5;background:#f5f3ff}}
.stat-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:16px}}
.stat-box{{background:#fff;border-radius:10px;padding:14px;text-align:center;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
.stat-val{{font-size:1.4rem;font-weight:700;color:#4f46e5}}
.stat-lbl{{font-size:.75rem;color:#64748b;margin-top:2px}}
.badge{{display:inline-block;padding:2px 9px;border-radius:999px;font-size:.72rem;font-weight:600}}
.b-study{{background:#d1fae5;color:#065f46}}
.b-review{{background:#fef3c7;color:#92400e}}
.b-assess{{background:#ede9fe;color:#5b21b6}}
.b-rest{{background:#f1f5f9;color:#475569}}
.b-done{{background:#d1fae5;color:#065f46}}
.b-pending{{background:#f1f5f9;color:#475569}}
.b-ip{{background:#dbeafe;color:#1e40af}}
.b-miss{{background:#fee2e2;color:#991b1b}}
.prog-bar{{background:#e2e8f0;border-radius:999px;height:8px;overflow:hidden;margin:10px 0 4px}}
.prog-fill{{background:#4f46e5;height:100%;border-radius:999px}}
.tag{{display:inline-block;background:#f1f5f9;color:#475569;border-radius:6px;padding:2px 8px;font-size:.72rem;margin:2px}}
.weak-tag{{background:#fee2e2;color:#991b1b}}
.tags{{display:flex;flex-wrap:wrap;gap:2px;margin-top:6px}}
.plan-row{{display:grid;grid-template-columns:48px 96px 52px 1fr 64px;gap:8px;align-items:start;padding:10px 0;border-bottom:1px solid #f1f5f9}}
.plan-row:last-child{{border-bottom:none}}
.hl{{background:#f5f3ff;border-radius:8px;padding:10px;margin:2px 0}}
.rev-row{{display:grid;grid-template-columns:1fr 100px 52px 56px;gap:8px;align-items:center;padding:8px 0;border-bottom:1px solid #f1f5f9;font-size:.85rem}}
.rev-row:last-child{{border-bottom:none}}
.ms-item{{padding:10px 0;border-bottom:1px solid #f1f5f9}}
.ms-item:last-child{{border-bottom:none}}
.rec-item{{padding:6px 0;border-bottom:1px solid #f1f5f9;font-size:.9rem}}
.rec-item:last-child{{border-bottom:none}}
.rec-item::before{{content:'• ';color:#4f46e5;font-weight:700}}
.empty{{color:#94a3b8;font-size:.85rem;padding:6px 0}}
.day-n{{font-weight:700;color:#4f46e5;font-size:.9rem}}
@media(max-width:600px){{
  .stat-grid{{grid-template-columns:repeat(2,1fr)}}
  .plan-row{{grid-template-columns:40px 1fr;grid-template-rows:auto auto}}
  .rev-row{{grid-template-columns:1fr 80px}}
}}
</style>
</head>
<body>
<div class="wrap" id="app"></div>
<script>
const R = {data_json};
const TODAY = new Date().toISOString().split('T')[0];

const TYPE_CLS = {{학습:'b-study',복습:'b-review',평가:'b-assess',휴식:'b-rest'}};
const ST_CLS = {{완료:'b-done',예정:'b-pending','진행 중':'b-ip',미완료:'b-miss'}};

const badge = (cls, txt) => `<span class="badge ${{cls}}">${{txt}}</span>`;
const typeBadge = t => badge(TYPE_CLS[t]||'b-pending', t);
const stBadge = s => badge(ST_CLS[s]||'b-pending', s);
const pct = v => Math.round((v||0)*100);

function render() {{
  const todayItems = (R.daily_plan||[]).filter(p => p.date === TODAY);
  const dueCards = (R.review_schedule||[]).filter(r => r.next_review === TODAY);
  const upcoming = (R.review_schedule||[])
    .filter(r => r.next_review >= TODAY)
    .sort((a,b) => a.next_review.localeCompare(b.next_review))
    .slice(0, 12);
  const progress = pct(R.overall_progress);

  let h = '';

  // 복습 카드 배너
  if (dueCards.length) {{
    h += `<div class="card" style="background:#fef9c3;border:1px solid #facc15;display:flex;align-items:center;gap:12px">
  <span style="font-size:1.5rem">📚</span>
  <div>
    <strong>오늘의 복습 카드 ${{dueCards.length}}장이 도착했습니다!</strong>
    <p style="font-size:.82rem;color:#713f12;margin-top:2px">${{dueCards.slice(0,3).map(r=>r.concept).join(' · ')}}${{dueCards.length>3?' 외 '+(dueCards.length-3)+'개':''}}</p>
  </div>
</div>`;
  }}

  // 헤더
  h += `<div class="card">
  <h1>${{R.document_title||R.doc_id}}</h1>
  ${{R.goal ? `<p style="color:#64748b;margin-top:4px;font-size:.95rem">${{R.goal}}</p>` : ''}}
  ${{R.deadline ? `<p style="font-size:.8rem;color:#94a3b8;margin-top:4px">마감일: ${{R.deadline}}</p>` : ''}}
  <div class="prog-bar"><div class="prog-fill" style="width:${{progress}}%"></div></div>
  <p style="font-size:.8rem;color:#64748b">전체 진도 ${{progress}}%</p>
</div>`;

  // 통계
  h += `<div class="stat-grid">
  <div class="stat-box"><div class="stat-val">${{R.estimated_total_days||0}}</div><div class="stat-lbl">예상 학습일</div></div>
  <div class="stat-box"><div class="stat-val">${{R.learning_pace||'-'}}</div><div class="stat-lbl">학습 속도</div></div>
  <div class="stat-box"><div class="stat-val">${{(R.daily_plan||[]).length}}</div><div class="stat-lbl">계획된 날수</div></div>
  <div class="stat-box"><div class="stat-val">${{(R.weak_concepts||[]).length}}</div><div class="stat-lbl">약점 개념</div></div>
</div>`;

  // 오늘의 학습
  h += `<div class="card ${{todayItems.length ? 'today' : ''}}">
  <h2>📅 오늘의 학습 (${{TODAY}})</h2>`;
  if (todayItems.length) {{
    todayItems.forEach(p => {{
      h += `<div style="margin-bottom:10px">
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:6px">
      ${{typeBadge(p.type)}}
      <strong style="font-size:.95rem">${{p.title}}</strong>
      <span style="color:#94a3b8;font-size:.8rem">${{p.estimated_minutes}}분</span>
    </div>
    ${{p.concepts_to_study?.length ? `<div class="tags">${{p.concepts_to_study.map(c=>`<span class="tag">${{c}}</span>`).join('')}}</div>` : ''}}
    ${{p.flashcard_count ? `<p style="font-size:.78rem;color:#64748b;margin-top:4px">플래시카드 ${{p.flashcard_count}}개 도전</p>` : ''}}
    ${{p.concepts_to_review?.length ? `<p style="font-size:.78rem;color:#92400e;margin-top:4px">오늘 복습: ${{p.concepts_to_review.join(' · ')}}</p>` : ''}}
  </div>`;
    }});
  }} else {{
    h += `<p class="empty">오늘 예정된 학습이 없습니다.</p>`;
  }}
  h += `</div>`;

  // 전체 일정
  h += `<div class="card"><h2>전체 학습 계획</h2>
  <div style="font-size:.75rem;color:#94a3b8;display:grid;grid-template-columns:48px 96px 52px 1fr 64px;gap:8px;padding:0 0 6px;border-bottom:1px solid #e2e8f0">
    <span>Day</span><span>날짜</span><span>유형</span><span>내용</span><span>상태</span>
  </div>`;
  (R.daily_plan||[]).forEach(p => {{
    const hl = p.date === TODAY;
    h += `<div class="plan-row${{hl?' hl':''}}">
    <div class="day-n">${{p.day}}</div>
    <div style="font-size:.78rem;color:#64748b">${{p.date}}</div>
    <div>${{typeBadge(p.type)}}</div>
    <div>
      <div style="font-size:.85rem;font-weight:500">${{p.title}}</div>
      ${{p.concepts_to_study?.length ? `<div class="tags">${{p.concepts_to_study.slice(0,2).map(c=>`<span class="tag" style="font-size:.68rem">${{c}}</span>`).join('')}}${{p.concepts_to_study.length>2?`<span class="tag" style="font-size:.68rem">+${{p.concepts_to_study.length-2}}</span>`:''}}</div>` : ''}}
    </div>
    <div>${{stBadge(p.status)}}</div>
  </div>`;
  }});
  h += `</div>`;

  // 마일스톤
  if ((R.milestones||[]).length) {{
    const planLen = (R.daily_plan||[]).length;
    const msUnit = planLen <= 7 ? 'Day' : planLen <= 21 ? 'Phase' : 'Week';
    h += `<div class="card"><h2>마일스톤</h2>`;
    R.milestones.forEach(m => {{
      h += `<div class="ms-item">
    <div style="display:flex;justify-content:space-between">
      <strong>${{msUnit}} ${{m.week}}</strong>
      <span style="font-size:.8rem;color:#64748b">목표 ${{Math.round(m.completion_target*100)}}%</span>
    </div>
    <p style="font-size:.9rem;margin-top:3px">${{m.goal}}</p>
    ${{m.target_concepts?.length ? `<div class="tags">${{m.target_concepts.map(c=>`<span class="tag">${{c}}</span>`).join('')}}</div>` : ''}}
  </div>`;
    }});
    h += `</div>`;
  }}

  // 복습 일정
  h += `<div class="card"><h2>복습 일정 (SM-2)</h2>
  <div style="font-size:.75rem;color:#94a3b8;display:grid;grid-template-columns:1fr 100px 52px 56px;gap:8px;padding:0 0 6px;border-bottom:1px solid #e2e8f0">
    <span>개념</span><span>다음 복습</span><span>간격</span><span>반복</span>
  </div>`;
  if (upcoming.length) {{
    upcoming.forEach(r => {{
      const isToday = r.next_review === TODAY;
      h += `<div class="rev-row">
    <span style="${{r.is_weak?'color:#dc2626':''}}">
      ${{r.is_weak ? '⚠ ' : ''}}<span style="font-size:.85rem">${{r.concept}}</span>
    </span>
    <span style="font-size:.82rem;color:${{isToday?'#4f46e5':'#475569'}};font-weight:${{isToday?700:400}}">${{r.next_review}}</span>
    <span style="color:#64748b">${{r.interval_days}}일</span>
    <span style="color:#64748b">${{r.repetitions}}회</span>
  </div>`;
    }});
  }} else {{
    h += `<p class="empty">복습 일정이 없습니다.</p>`;
  }}
  h += `</div>`;

  // 전략 & 추천
  if (R.review_strategy || (R.recommendations||[]).length) {{
    h += `<div class="card"><h2>학습 전략 & 추천</h2>`;
    if (R.review_strategy) {{
      h += `<p style="font-size:.9rem;color:#334155;margin-bottom:12px;line-height:1.7">${{R.review_strategy}}</p>`;
    }}
    (R.recommendations||[]).forEach(rec => {{
      h += `<div class="rec-item">${{rec}}</div>`;
    }});
    h += `</div>`;
  }}

  // 약점 개념
  if ((R.weak_concepts||[]).length) {{
    h += `<div class="card"><h2>약점 개념</h2><div class="tags">`;
    R.weak_concepts.forEach(c => {{ h += `<span class="tag weak-tag">${{c}}</span>`; }});
    h += `</div></div>`;
  }}

  document.getElementById('app').innerHTML = h;
}}
render();
</script>
</body>
</html>"""
