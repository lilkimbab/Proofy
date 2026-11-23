import os
import tempfile
import uuid
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile, Form

from api.schemas import (
    AddAcceptedResponse, JobStatusResponse,
    SearchRequest, SearchResponse,
    FetchRequest, FetchResponse,
    FeedbackRequest, FeedbackResponse, ReloadResponse,
    FilesResponse, StatusResponse, TitlesResponse,
    ParseParent,
)
from vector_db.manager import ReembedInProgressError, _encode_image

router = APIRouter()


def get_db(request: Request):
    db = request.app.state.db
    if db is None:
        raise HTTPException(status_code=503, detail="DB not initialized")
    return db


def get_job_registry(request: Request) -> dict:
    return request.app.state.job_registry


# ---------------------------------------------------------------------------
# 헬퍼: 업로드 임시 저장 / 백그라운드 인제스트 실행
# ---------------------------------------------------------------------------

async def _save_upload_to_tmp(file: UploadFile) -> tuple[str, str, str]:
    """업로드 파일을 임시 디렉터리에 저장. 실패 시 정리 후 예외 재발생.

    file.filename 의 경로 구분자/상위 참조는 basename 으로 차단해
    tmp_dir 밖으로 나가는 임의 위치 쓰기를 방지한다.

    Returns: (tmp_path, tmp_dir, original_name)
    """
    raw_name = file.filename or "upload"
    original_name = os.path.basename(raw_name) or "upload"
    tmp_dir = tempfile.mkdtemp()
    tmp_path = os.path.join(tmp_dir, original_name)
    try:
        content = await file.read()
        with open(tmp_path, "wb") as f:
            f.write(content)
    except Exception:
        _cleanup_tmp(tmp_path, tmp_dir)
        raise
    return tmp_path, tmp_dir, original_name


def _cleanup_tmp(tmp_path: str, tmp_dir: str) -> None:
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)
    try:
        os.rmdir(tmp_dir)
    except OSError:
        pass


def _run_ingest(
    work_fn: Callable[[Callable[[int, int, int], None]], dict],
    tmp_path: str,
    tmp_dir: str,
    job_id: str,
    job_registry: dict,
) -> None:
    """work_fn 을 실행하며 job_registry 를 갱신하고 finally 에서 tmp 를 정리한다."""
    try:
        job_registry[job_id]["status"] = "running"

        def on_batch(batch_num: int, total_batches: int, chunks_added: int) -> None:
            job_registry[job_id].update({
                "batch": batch_num,
                "total_batches": total_batches,
                "chunks_added": chunks_added,
            })

        result = work_fn(on_batch)
        job_registry[job_id].update({
            "status": "done",
            "chunks_added": result["chunks_added"],
        })
    except Exception as e:
        job_registry[job_id].update({"status": "failed", "error": str(e)})
    finally:
        _cleanup_tmp(tmp_path, tmp_dir)


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, db=Depends(get_db)):
    try:
        hits = db.search(
            query=req.query, title=req.title,
            top_k=req.top_k, filter=req.filter,
            user_id=req.user_id,
        )
    except ReembedInProgressError:
        raise HTTPException(
            status_code=503,
            detail="재임베딩 진행 중입니다. 잠시 후 다시 시도해주세요.",
            headers={"Retry-After": "30"},
        )
    return SearchResponse(results=hits)


@router.post("/fetch", response_model=FetchResponse)
async def fetch_chunks(req: FetchRequest, db=Depends(get_db)):
    """
    의미 검색 없이 filter 조건(page, file_name 등)만으로 chunks를 전부 조회한다.
    "315페이지의 모든 내용" 같은 구조적 쿼리에 사용한다.
    """
    hits = db.fetch(title=req.title, filter=req.filter, limit=req.limit)
    return FetchResponse(results=hits, count=len(hits))


@router.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest, db=Depends(get_db)):
    db.record_feedback(
        user_id=req.user_id, title=req.title,
        chunk_id=req.chunk_id, kind=req.kind,
    )
    return FeedbackResponse(status="ok")


@router.post("/reload", response_model=ReloadResponse)
async def reload_config(db=Depends(get_db)):
    cfg = db.reload_config()
    return ReloadResponse(status="ok", config=cfg)


@router.post("/add", response_model=AddAcceptedResponse)
async def add_document(
    background_tasks: BackgroundTasks,
    file: UploadFile,
    title: str = Form(..., min_length=1),
    db=Depends(get_db),
    job_registry: dict = Depends(get_job_registry),
):
    """
    파일을 파싱·청킹하여 parents 전문을 즉시 반환하고,
    백그라운드에서 임베딩·저장을 시작한다.
    인제스트 진행은 GET /jobs/{job_id} 로 추적할 수 있다.
    """
    tmp_path, tmp_dir, original_name = await _save_upload_to_tmp(file)

    # parse 실패 시 BackgroundTask 가 등록되지 않아 finally 가 돌지 않으므로 직접 정리한다.
    try:
        result = db.parse_document(tmp_path)
    except Exception as e:
        _cleanup_tmp(tmp_path, tmp_dir)
        raise HTTPException(status_code=400, detail=f"parse failed: {e}")

    chunks = result["chunks"]
    parents = result["parents"]
    page_images = result.get("page_images", [])

    # page → [image_path, ...] 맵 (페이지당 여러 크롭 가능)
    page_img_map: dict[int, list[str]] = {}
    for pi in page_images:
        page_img_map.setdefault(pi["page"], []).append(pi["image_path"])
    encoded_cache: dict[str, str | None] = {}

    def _parent_image(p: dict) -> str | None:
        for pg in range(p["page_start"], p["page_end"] + 1):
            paths = page_img_map.get(pg, [])
            if paths:
                img_path = paths[0]
                if img_path not in encoded_cache:
                    encoded_cache[img_path] = _encode_image(img_path)
                return encoded_cache[img_path]
        return None

    job_id = str(uuid.uuid4())
    job_registry[job_id] = {
        "status": "pending",
        "title": title,
        "file_name": original_name,
        "chunks_added": 0,
        "batch": 0,
        "total_batches": 0,
        "error": None,
    }

    # 빈 파일: embed 할 것이 없으므로 job 을 즉시 done 으로 처리하고 tmp 를 정리한다.
    if not chunks:
        job_registry[job_id]["status"] = "done"
        _cleanup_tmp(tmp_path, tmp_dir)
    else:
        background_tasks.add_task(
            _run_ingest,
            lambda on_batch: db._embed_and_store(
                title=title, chunks=chunks, parents=parents,
                on_batch=on_batch, page_images=page_images,
            ),
            tmp_path, tmp_dir, job_id, job_registry,
        )

    return AddAcceptedResponse(
        status="accepted",
        job_id=job_id,
        title=title,
        file_name=original_name,
        parents=[
            ParseParent(
                parent_id=p["parent_id"],
                text=p["text"],
                source=p["file_name"],
                page_start=p["page_start"],
                page_end=p["page_end"],
                heading_path=p.get("heading_path"),
                source_type=p.get("source_type"),
                image=_parent_image(p),
            )
            for p in parents
        ],
    )


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def job_status(job_id: str, job_registry: dict = Depends(get_job_registry)):
    """인제스트 작업 진행 상태를 조회한다."""
    job = job_registry.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(job_id=job_id, **job)


@router.get("/titles", response_model=TitlesResponse)
async def list_titles(db=Depends(get_db)):
    return TitlesResponse(titles=db.list_titles())


@router.get("/files/{title}", response_model=FilesResponse)
async def list_files(title: str, db=Depends(get_db)):
    return FilesResponse(title=title, files=db.list_files(title))


@router.delete("/files/{title}/{file_name}", response_model=StatusResponse)
async def delete_file(title: str, file_name: str, db=Depends(get_db)):
    db.delete_file(title=title, file_name=file_name)
    return StatusResponse(status="ok")


@router.delete("/titles/{title}", response_model=StatusResponse)
async def delete_title(title: str, db=Depends(get_db)):
    db.delete_title(title=title)
    return StatusResponse(status="ok")
