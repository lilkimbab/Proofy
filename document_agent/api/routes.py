import glob
import logging
import os
import tempfile

import os as _os

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

_MATERIALS_DIR = _os.getenv("MATERIALS_DIR") or _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), "..", "generated_materials"
)
from fastapi.responses import FileResponse, HTMLResponse

from api.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    StudyMaterialSchema,
    TaskStatusSchema,
    UploadResponse,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_MEDIA_TYPES = {
    ".pdf":  "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".txt":  "text/plain; charset=utf-8",
}


def get_manager(request: Request):
    manager = request.app.state.manager
    if manager is None:
        raise HTTPException(503, "서비스 초기화 중입니다. 잠시 후 다시 시도하세요.")
    return manager


def _source_path(doc_id: str) -> str | None:
    matches = glob.glob(os.path.join(_MATERIALS_DIR, doc_id, "source.*"))
    return matches[0] if matches else None


@router.get("/tasks/{task_id}", response_model=TaskStatusSchema)
async def get_task_status(task_id: str, mgr=Depends(get_manager)):
    task = mgr.get_task(task_id)
    if task is None:
        raise HTTPException(404, f"task_id '{task_id}'를 찾을 수 없습니다")
    return task


@router.get("/study/{doc_id}", response_model=StudyMaterialSchema)
async def get_study_material(doc_id: str, mgr=Depends(get_manager)):
    material = mgr.get_material(doc_id)
    if material is None:
        raise HTTPException(404, f"doc_id '{doc_id}'의 자료를 찾을 수 없습니다")
    return material


@router.post("/upload", response_model=UploadResponse, status_code=202)
async def upload_file(
    file: UploadFile = File(...),
    title: str = Form(...),
    mgr=Depends(get_manager),
):
    suffix = os.path.splitext(file.filename or "upload")[1] or ".pdf"
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        content = await file.read()
        with os.fdopen(fd, "wb") as f:
            f.write(content)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise HTTPException(500, "파일 저장 실패")

    try:
        task_id, doc_id, job_id = await mgr.submit_upload(tmp_path, title)
    except RuntimeError as e:
        raise HTTPException(502, str(e))

    return UploadResponse(task_id=task_id, doc_id=doc_id, job_id=job_id)


@router.get("/view/{doc_id}/image/{chunk_id}")
async def serve_section_image(doc_id: str, chunk_id: str):
    img_path = os.path.join(_MATERIALS_DIR, doc_id, "images", f"{chunk_id}.png")
    if not os.path.exists(img_path):
        raise HTTPException(404, "이미지가 없습니다")
    return FileResponse(img_path, media_type="image/png")


@router.get("/view/{doc_id}/source")
async def serve_source_file(doc_id: str):
    path = _source_path(doc_id)
    if path is None:
        raise HTTPException(404, "원본 파일이 없습니다")
    ext = os.path.splitext(path)[1].lower()
    media_type = _MEDIA_TYPES.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media_type)


@router.get("/view/{doc_id}", response_class=HTMLResponse)
async def view_comparison(doc_id: str, mgr=Depends(get_manager)):
    material = mgr.get_material(doc_id)
    if material is None:
        raise HTTPException(404, f"doc_id '{doc_id}'의 자료를 찾을 수 없습니다")
    has_source = _source_path(doc_id) is not None
    return HTMLResponse(_render_compare_html(material, doc_id, has_source))


def _render_compare_html(material: dict, doc_id: str, has_source: bool) -> str:
    import json

    def _safe_json(obj) -> str:
        return json.dumps(obj, ensure_ascii=False).replace('</script>', '<\\/script>')

    sections_json = _safe_json(material.get("sections", []))
    flow_json = _safe_json(material.get("learning_flow", []))
    image_map_json = _safe_json(material.get("image_map", {}))
    exec_summary_json = _safe_json(material.get("exec_summary", {}))
    title = material.get("title", "")
    source_url = f"/view/{doc_id}/source" if has_source else ""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — 비교 학습</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/contrib/auto-render.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/marked@9.1.6/marked.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({{ startOnLoad: false, theme: 'neutral' }});
  window._mermaid = mermaid;
</script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; color: #222; overflow: hidden; height: 100vh; display: flex; flex-direction: column; }}

  header {{ background: #1a1a2e; color: #fff; padding: 14px 24px; flex-shrink: 0; }}
  header h1 {{ font-size: 1.2rem; font-weight: 700; }}
  header p  {{ font-size: 0.8rem; opacity: 0.65; margin-top: 2px; }}

  .flow {{ display: flex; gap: 6px; padding: 10px 24px; background: #fff;
           border-bottom: 1px solid #ddd; flex-wrap: wrap; flex-shrink: 0; }}
  .flow-step {{ display: flex; align-items: center; gap: 5px; font-size: 0.78rem;
                background: #f0f4ff; border-radius: 20px; padding: 3px 10px;
                color: #3a3aaa; cursor: pointer; transition: background .15s; }}
  .flow-step:hover {{ background: #dde5ff; }}
  .flow-step .num {{ background: #3a3aaa; color: #fff; border-radius: 50%;
                     width: 16px; height: 16px; display: flex; align-items: center;
                     justify-content: center; font-size: 0.65rem; flex-shrink: 0; }}

  .workspace {{ display: flex; flex: 1; overflow: hidden; }}

  /* ── 왼쪽: PDF.js 렌더 패널 ── */
  .pdf-pane {{ width: 48%; border-right: 2px solid #ddd; display: flex; flex-direction: column; flex-shrink: 0; background: #525659; }}
  .pdf-nav {{ display: flex; align-items: center; gap: 8px; padding: 6px 14px;
              background: #3d4043; flex-shrink: 0; }}
  .pdf-nav button {{ padding: 3px 12px; border: none; border-radius: 4px;
                     background: #5f6368; color: #fff; cursor: pointer; font-size: 0.82rem; }}
  .pdf-nav button:hover {{ background: #80868b; }}
  .pdf-nav input[type=number] {{ width: 48px; padding: 2px 6px; border: none; border-radius: 4px;
                                 text-align: center; font-size: 0.82rem; background: #5f6368; color: #fff; }}
  .pdf-nav .page-info {{ color: #bdc1c6; font-size: 0.8rem; }}
  .pdf-canvas-wrap {{ flex: 1; overflow-y: auto; display: flex; justify-content: center;
                      align-items: flex-start; padding: 12px; }}
  #pdfCanvas {{ box-shadow: 0 2px 12px rgba(0,0,0,.5); display: block; max-width: 100%; }}
  .pdf-loading {{ color: #bdc1c6; font-size: 0.85rem; padding: 20px; text-align: center; }}

  /* ── 오른쪽: 섹션 패널 ── */
  .sections-pane {{ flex: 1; overflow-y: auto; padding: 20px; background: #f5f6fa; }}
  .section-card {{ background: #fff; border-radius: 10px; box-shadow: 0 2px 6px rgba(0,0,0,.07);
                   overflow: hidden; margin-bottom: 20px; }}
  .sec-header {{ padding: 12px 18px; border-bottom: 1px solid #eee;
                 display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }}
  .sec-header h2 {{ font-size: 1rem; font-weight: 700; flex: 1; }}
  .badge {{ font-size: 0.68rem; padding: 2px 8px; border-radius: 10px; font-weight: 700; white-space: nowrap; }}
  .badge-definition {{ background: #e8f4fd; color: #0077cc; }}
  .badge-example     {{ background: #e8fdf4; color: #007744; }}
  .badge-comparison  {{ background: #fdf4e8; color: #cc7700; }}
  .badge-exercise    {{ background: #fde8f4; color: #cc0077; }}
  .badge-default     {{ background: #efefef; color: #555; }}
  .focus-bar {{ font-size: 0.8rem; color: #555; background: #f8f9ff;
                padding: 7px 18px; border-bottom: 1px solid #eee; }}
  .focus-bar strong {{ color: #3a3aaa; }}
  .page-chips {{ display: flex; gap: 6px; padding: 8px 18px; border-bottom: 1px solid #eee; flex-wrap: wrap; }}
  .page-chip {{ font-size: 0.72rem; padding: 2px 9px; border: 1px solid #c0c8e8;
                border-radius: 12px; background: #f0f4ff; color: #3a3aaa;
                cursor: pointer; transition: background .12s; }}
  .page-chip:hover {{ background: #dde5ff; }}
  .ai-col {{ padding: 16px 20px; font-size: 0.875rem; line-height: 1.75; }}
  .ai-col h1, .ai-col h2, .ai-col h3 {{ margin: 12px 0 5px; }}
  .ai-col h2 {{ font-size: 1rem; }} .ai-col h3 {{ font-size: 0.95rem; }}
  .ai-col p  {{ margin-bottom: 8px; }}
  .ai-col ul, .ai-col ol {{ padding-left: 18px; margin-bottom: 8px; }}
  .ai-col li {{ margin-bottom: 3px; }}
  .ai-col code {{ background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 0.82rem; }}
  .ai-col pre  {{ background: #f4f4f4; padding: 10px; border-radius: 6px; overflow-x: auto; margin-bottom: 8px; }}
  .ai-col blockquote {{ border-left: 3px solid #ccc; padding-left: 12px; color: #666; margin-bottom: 8px; }}
  .ai-col table {{ border-collapse: collapse; width: 100%; margin-bottom: 8px; }}
  .ai-col td, .ai-col th {{ border: 1px solid #ddd; padding: 5px 9px; font-size: 0.82rem; }}

  /* ── grounding warning ── */
  .grounding-warn {{ background: #fff8e1; border-bottom: 1px solid #ffca28; padding: 8px 18px; }}
  .grounding-warn summary {{ font-size: 0.78rem; font-weight: 700; color: #7b5800; cursor: pointer; user-select: none; }}
  .grounding-warn ul {{ margin: 6px 0 0 16px; font-size: 0.78rem; color: #7b5800; }}
  .grounding-warn li {{ margin-bottom: 3px; }}

  /* ── 참고자료 chips ── */
  .ref-section {{ padding: 8px 18px; border-bottom: 1px solid #eee; background: #fafafa; }}
  .ref-chips {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }}
  .ref-label {{ font-size: 0.72rem; color: #888; font-weight: 600; }}
  .ref-chip {{ position: relative; font-size: 0.72rem; padding: 3px 10px;
               border: 1px solid #c0c8e8; border-radius: 12px; background: #f0f4ff;
               color: #3a3aaa; cursor: pointer; user-select: none; transition: background .12s; }}
  .ref-chip:hover {{ background: #dde5ff; }}
  .ref-preview {{ position: absolute; top: calc(100% + 8px); left: 0; z-index: 200;
                  background: #fff; border: 1px solid #ddd; border-radius: 8px;
                  box-shadow: 0 4px 20px rgba(0,0,0,.18); padding: 6px;
                  display: none; pointer-events: none; }}
  .ref-chip:hover .ref-preview {{ display: block; }}
  .ref-preview img {{ max-width: 260px; border-radius: 4px; display: block; }}
  .ref-expand {{ display: none; margin-top: 8px; }}
  .ref-expand.open {{ display: block; }}
  .ref-expand img {{ max-width: 100%; border-radius: 6px;
                     box-shadow: 0 1px 6px rgba(0,0,0,.12); display: block; }}

  /* ── executive summary ── */
  .exec-summary {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
                   color: #fff; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px; }}
  .exec-summary h3 {{ font-size: 0.8rem; font-weight: 700; letter-spacing: .06em;
                      text-transform: uppercase; opacity: .6; margin-bottom: 14px; }}
  .exec-topics {{ display: flex; gap: 7px; flex-wrap: wrap; margin-bottom: 16px; }}
  .exec-topic {{ font-size: 0.78rem; padding: 3px 11px; border-radius: 14px;
                 background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.2); }}
  .exec-section-label {{ font-size: 0.72rem; opacity: .55; font-weight: 600;
                          letter-spacing: .05em; text-transform: uppercase; margin-bottom: 5px; }}
  .exec-objectives {{ list-style: none; margin-bottom: 16px; }}
  .exec-objectives li {{ font-size: 0.82rem; opacity: .9; padding: 3px 0; }}
  .exec-objectives li::before {{ content: '✓ '; color: #7eb8f7; font-weight: 700; }}
  .exec-flow {{ font-size: 0.82rem; line-height: 1.7; opacity: .85;
                border-top: 1px solid rgba(255,255,255,.12); padding-top: 12px; margin-top: 4px; }}

  /* ── 💡 더 알아보기 collapsible ── */
  .supplement {{ border-top: 1px solid #eee; margin-top: 8px; }}
  .supplement summary {{
    font-size: 0.85rem; font-weight: 700; color: #3a3aaa;
    cursor: pointer; padding: 10px 0; display: flex; align-items: center; gap: 6px;
    list-style: none; user-select: none;
  }}
  .supplement summary::-webkit-details-marker {{ display: none; }}
  .supplement summary::before {{ content: '▶'; font-size: 0.65rem; transition: transform .2s; display: inline-block; }}
  details[open].supplement summary::before {{ transform: rotate(90deg); }}
  .supplement-body {{ padding: 4px 0 8px; font-size: 0.875rem; line-height: 1.75; }}
  .supplement-body p {{ margin-bottom: 8px; }}

  /* ── flashcards ── */
  .flashcard-section {{ padding: 12px 20px; border-top: 1px solid #eee; background: #fafbff; }}
  .flashcard-toggle {{ font-size: 0.78rem; font-weight: 700; color: #3a3aaa; cursor: pointer;
                       background: none; border: none; padding: 0; margin-bottom: 8px; display: flex; align-items: center; gap: 4px; }}
  .flashcard-list {{ display: none; }}
  .flashcard-list.open {{ display: block; }}
  .flashcard {{ border: 1px solid #c0c8e8; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;
                cursor: pointer; background: #fff; transition: background .12s; user-select: none; }}
  .flashcard:hover {{ background: #f0f4ff; }}
  .flashcard-q {{ font-size: 0.84rem; font-weight: 600; color: #222; }}
  .flashcard-status {{ font-size: 0.7rem; color: #aaa; margin-top: 4px; }}
  .flashcard-hint {{ font-size: 0.8rem; color: #555; margin-top: 6px; padding-top: 6px;
                     border-top: 1px dashed #ccc; display: none; }}
  .flashcard-answer {{ font-size: 0.82rem; color: #1a6b1a; margin-top: 6px; padding-top: 6px;
                       border-top: 1px dashed #9ecf9e; display: none; }}
  .flashcard[data-state="hint"] .flashcard-hint {{ display: block; }}
  .flashcard[data-state="answer"] .flashcard-hint {{ display: block; }}
  .flashcard[data-state="answer"] .flashcard-answer {{ display: block; }}
  .flashcard-q::before {{ content: 'Q. '; color: #3a3aaa; }}
  .flashcard-hint::before {{ content: '💡 힌트: '; font-weight: 600; color: #3a3aaa; }}
  .flashcard-answer::before {{ content: '✅ 정답: '; font-weight: 600; color: #1a6b1a; }}
</style>
</head>
<body>

<header>
  <h1>{title} — 비교 학습</h1>
  <p>원본 PDF와 AI 설명을 나란히 비교합니다 · 페이지 번호를 클릭하면 PDF가 해당 페이지로 이동합니다</p>
</header>

<div class="flow" id="flow"></div>

<div class="workspace">
  <div class="pdf-pane" id="pdfPane" {"" if has_source else 'style="display:none"'}>
    <div class="pdf-nav">
      <button onclick="goPage(-1)">◀</button>
      <input type="number" id="pageInput" value="1" min="1" onchange="jumpToPage(+this.value)">
      <span class="page-info">/ <span id="pageCount">—</span></span>
      <button onclick="goPage(1)">▶</button>
    </div>
    <div class="pdf-canvas-wrap">
      <div class="pdf-loading" id="pdfLoading">PDF 로딩 중…</div>
      <canvas id="pdfCanvas" style="display:none"></canvas>
    </div>
  </div>

  <div class="sections-pane" id="sections" {"" if has_source else 'style="width:100%"'}></div>
</div>

<script>
const SOURCE_URL  = "{source_url}";
const DOC_ID      = "{doc_id}";
const sections    = {sections_json};
const flowItems   = {flow_json};
const imageMap    = {image_map_json};
const execSummary = {exec_summary_json};

let pdfDoc = null;
let currentPage = 1;
let rendering = false;
let renderPending = null;

async function initPDF() {{
  if (!SOURCE_URL) return;
  try {{
    if (typeof pdfjsLib === 'undefined') throw new Error('PDF.js 라이브러리를 불러오지 못했습니다');
    pdfjsLib.GlobalWorkerOptions.workerSrc =
      'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
    pdfDoc = await pdfjsLib.getDocument(SOURCE_URL).promise;
    document.getElementById('pageCount').textContent = pdfDoc.numPages;
    document.getElementById('pdfLoading').style.display = 'none';
    document.getElementById('pdfCanvas').style.display = 'block';
    await renderPage(1);
  }} catch(e) {{
    document.getElementById('pdfLoading').textContent = 'PDF 로드 실패: ' + e.message;
  }}
}}

async function renderPage(n) {{
  if (!pdfDoc) return;
  n = Math.max(1, Math.min(n, pdfDoc.numPages));
  currentPage = n;
  document.getElementById('pageInput').value = n;

  if (rendering) {{
    renderPending = n;
    return;
  }}
  rendering = true;

  const page = await pdfDoc.getPage(n);
  const wrap = document.querySelector('.pdf-canvas-wrap');
  const scale = (wrap.clientWidth - 24) / page.getViewport({{ scale: 1 }}).width;
  const viewport = page.getViewport({{ scale }});
  const canvas = document.getElementById('pdfCanvas');
  canvas.width  = viewport.width;
  canvas.height = viewport.height;
  await page.render({{ canvasContext: canvas.getContext('2d'), viewport }}).promise;
  wrap.scrollTop = 0;

  rendering = false;
  if (renderPending !== null && renderPending !== n) {{
    const next = renderPending;
    renderPending = null;
    await renderPage(next);
  }} else {{
    renderPending = null;
  }}
}}

function jumpToPage(n) {{ renderPage(+n); }}
function goPage(delta) {{ jumpToPage(currentPage + delta); }}

/* ── marked.js 안전 래퍼 ── */
function renderMd(text) {{
  if (!text) return '';
  // CommonMark 엣지 케이스 우회: 닫는 ** 앞이 )등 구두점이고 뒤가 한국어 조사이면
  // marked가 bold를 인식 못함 → marked에 넘기기 전에 먼저 **...** 를 <strong>으로 변환.
  const preProcessed = text.replace(/[*][*](.+?)[*][*]/g, '<strong>$1</strong>');
  if (typeof marked !== 'undefined' && marked.parse) {{
    try {{ return marked.parse(preProcessed); }} catch(e) {{}}
  }}
  // marked 로드 실패 시 최소 폴백 (신뢰할 수 있는 LLM 생성 콘텐츠이므로 단순 처리)
  return preProcessed
    .replace(/[*](.+?)[*]/g,'<em>$1</em>')
    .replace(/\\n/g,'<br>');
}}

/* ── 참고자료 inline expand toggle ── */
function toggleRefExpand(id) {{
  document.getElementById(id)?.classList.toggle('open');
}}

/* ── flashcard 3-state cycle: blank → hint → answer → blank ── */
function cycleFlashcard(el) {{
  const states = ['', 'hint', 'answer'];
  const cur = el.dataset.state || '';
  const next = states[(states.indexOf(cur) + 1) % states.length];
  el.dataset.state = next;
  const status = el.querySelector('.flashcard-status');
  if (next === '') status.textContent = '클릭하여 힌트 보기';
  else if (next === 'hint') status.textContent = '클릭하여 정답 보기';
  else status.textContent = '클릭하여 초기화';
}}

/* ── badge ── */
const BADGE = {{
  definition:'badge-definition', example:'badge-example',
  comparison:'badge-comparison', exercise:'badge-exercise',
}};
function badge(intent) {{
  return (intent||'').split('|').map(i=>{{
    const t=i.trim();
    return `<span class="badge ${{BADGE[t]||'badge-default'}}">${{t}}</span>`;
  }}).join(' ');
}}

/* ── learning flow bar ── */
const flowEl = document.getElementById('flow');
flowItems.forEach(item => {{
  const el = document.createElement('div');
  el.className = 'flow-step';
  el.title = item.focus;
  el.innerHTML = `<span class="num">${{item.step}}</span><span>${{item.title}}</span>`;
  el.onclick = () => document.getElementById('sec-'+(item.step-1))?.scrollIntoView({{behavior:'smooth'}});
  flowEl.appendChild(el);
}});

/* ── executive summary card ── */
const container = document.getElementById('sections');
if (execSummary && (execSummary.key_topics?.length || execSummary.learning_objectives?.length || execSummary.conceptual_flow)) {{
  const topicsHtml = (execSummary.key_topics || [])
    .map(t => `<span class="exec-topic">${{t}}</span>`).join('');
  const objHtml = (execSummary.learning_objectives || [])
    .map(o => `<li>${{renderMd(o).replace(/<p>|<[/]p>/g,'')}}</li>`).join('');
  const flowHtml = execSummary.conceptual_flow
    ? `<div class="exec-section-label">전체 흐름</div>
       <div class="exec-flow">${{renderMd(execSummary.conceptual_flow)}}</div>` : '';

  const card = document.createElement('div');
  card.className = 'exec-summary';
  card.innerHTML = `
    <h3>📋 Executive Summary</h3>
    ${{topicsHtml ? `<div class="exec-section-label">핵심 주제</div><div class="exec-topics">${{topicsHtml}}</div>` : ''}}
    ${{objHtml ? `<div class="exec-section-label">학습 목표</div><ul class="exec-objectives">${{objHtml}}</ul>` : ''}}
    ${{flowHtml}}`;
  container.appendChild(card);
}}

/* ── section cards ── */
sections.forEach((sec, idx) => {{
  const pages = [...new Set((sec.source_chunks||[]).map(c=>c.page))].sort((a,b)=>a-b);
  const chips = pages.map(p=>`<span class="page-chip" onclick="jumpToPage(${{p}})">p.${{p}}</span>`).join('');

  // 참고자료 chips (hover → preview, click → inline expand)
  const imgChunks = (sec.source_chunks||[]).filter(c => imageMap[c.chunk_id]?.has_image);
  const srcImagesHtml = imgChunks.length
    ? `<div class="ref-section">
        <div class="ref-chips">
          <span class="ref-label">📎 참고자료</span>
          ${{imgChunks.map((c, ci) => {{
            const pg = imageMap[c.chunk_id]?.page;
            const imgSrc = `/view/${{DOC_ID}}/image/${{c.chunk_id}}`;
            return `<div class="ref-chip" onclick="toggleRefExpand('ref-${{idx}}-${{ci}}')">
              📄 이미지 p.${{pg}}
              <div class="ref-preview"><img src="${{imgSrc}}" loading="lazy" alt="p.${{pg}}"></div>
            </div>`;
          }}).join('')}}
        </div>
        ${{imgChunks.map((c, ci) => {{
          const pg = imageMap[c.chunk_id]?.page;
          return `<div class="ref-expand" id="ref-${{idx}}-${{ci}}">
            <img src="/view/${{DOC_ID}}/image/${{c.chunk_id}}" alt="p.${{pg}}">
          </div>`;
        }}).join('')}}
       </div>`
    : '';

  // grounding warning block
  let groundingHtml = '';
  if (sec.grounding_issues && sec.grounding_issues.length >= 2) {{
    const items = sec.grounding_issues.map(g=>`<li>${{g}}</li>`).join('');
    groundingHtml = `<div class="grounding-warn">
      <details>
        <summary>⚠ 원본 미확인 내용 ${{sec.grounding_issues.length}}건 (클릭하여 확인)</summary>
        <ul>${{items}}</ul>
      </details>
    </div>`;
  }}

  // flashcard block
  let flashHtml = '';
  if (sec.flashcards && sec.flashcards.length > 0) {{
    const cardId = `fc-${{idx}}`;
    const cardItems = sec.flashcards.map((fc, fi) => `
      <div class="flashcard" data-state="" onclick="cycleFlashcard(this)">
        <div class="flashcard-q">${{fc.question}}</div>
        <div class="flashcard-status">클릭하여 힌트 보기</div>
        <div class="flashcard-hint">${{fc.answer_hint}}</div>
        <div class="flashcard-answer">${{fc.answer || ''}}</div>
      </div>`).join('');
    flashHtml = `<div class="flashcard-section">
      <button class="flashcard-toggle" onclick="document.getElementById('${{cardId}}').classList.toggle('open')">
        🃏 플래시카드 ${{sec.flashcards.length}}장 (클릭하여 펼치기)
      </button>
      <div class="flashcard-list" id="${{cardId}}">${{cardItems}}</div>
    </div>`;
  }}

  // 💡 더 알아보기 분리
  const SUPP_MARKER = '### 💡 더 알아보기';
  const rawContent = sec.content || '';
  const suppIdx = rawContent.indexOf(SUPP_MARKER);
  const mainMd   = suppIdx >= 0 ? rawContent.slice(0, suppIdx).replace(/[\\n\\r]*-{{3}}[ \\t]*$/, '') : rawContent;
  const suppMd   = suppIdx >= 0 ? rawContent.slice(suppIdx + SUPP_MARKER.length) : null;
  const suppHtml = suppMd !== null
    ? `<details class="supplement">
        <summary>💡 더 알아보기</summary>
        <div class="supplement-body">${{renderMd(suppMd)}}</div>
       </details>`
    : '';

  const card = document.createElement('div');
  card.className = 'section-card';
  card.id = 'sec-' + idx;
  card.innerHTML = `
    <div class="sec-header">
      <h2>${{idx+1}}. ${{sec.title}}</h2>${{badge(sec.intent)}}
      ${{(sec.grounding_issues&&sec.grounding_issues.length>=2)?'<span class="badge" style="background:#fff3cd;color:#856404">⚠ 미확인</span>':''}}
    </div>
    <div class="focus-bar"><strong>학습 포커스:</strong> ${{sec.focus}}</div>
    ${{chips ? `<div class="page-chips">${{chips}}</div>` : ''}}
    ${{srcImagesHtml}}
    ${{groundingHtml}}
    <div class="ai-col">${{renderMd(mainMd)}}</div>
    ${{suppHtml}}
    ${{flashHtml}}`;
  container.appendChild(card);
}});

initPDF();

/* ── KaTeX 수식 렌더링 ── */
renderMathInElement(container, {{
  delimiters: [
    {{ left: '$$', right: '$$', display: true }},
    {{ left: '$',  right: '$',  display: false }},
  ],
  throwOnError: false,
}});

/* ── Mermaid 다이어그램 렌더링 ── */
(async () => {{
  const mermaid = window._mermaid;
  if (!mermaid) return;
  container.querySelectorAll('pre code.language-mermaid').forEach(el => {{
    const div = document.createElement('div');
    div.className = 'mermaid';
    div.textContent = el.textContent;
    el.closest('pre').replaceWith(div);
  }});
  await mermaid.run({{ nodes: container.querySelectorAll('.mermaid') }});
}})();
</script>
</body>
</html>"""


@router.post("/feedback", response_model=FeedbackResponse)
async def record_feedback(req: FeedbackRequest):
    from core import rag_client
    try:
        await rag_client.send_feedback(req.user_id, req.title, req.chunk_id)
    except Exception as e:
        logger.warning(f"피드백 전달 실패: {e}")
        raise HTTPException(502, "RAG 서버에 피드백을 전달하지 못했습니다")
    return FeedbackResponse(status="ok")
