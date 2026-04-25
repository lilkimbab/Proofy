from __future__ import annotations

from collections import defaultdict

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.services.content_generation import ContentGenerationRequest, StrongLLMContentGenerator
from app.services.auth_service import auth_service
from app.services.demo_service import service


class SessionHub:
    def __init__(self) -> None:
        self.connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, session_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self.connections[session_id].append(websocket)

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        if websocket in self.connections.get(session_id, []):
            self.connections[session_id].remove(websocket)

    async def broadcast(self, session_id: str, payload: dict) -> None:
        stale: list[WebSocket] = []
        for connection in self.connections.get(session_id, []):
            try:
                await connection.send_json(payload)
            except Exception:
                stale.append(connection)
        for connection in stale:
            self.disconnect(session_id, connection)


hub = SessionHub()
app = FastAPI(title="Proofy API", version="0.1.0")
generator = StrongLLMContentGenerator()
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_origin_regex=settings.allowed_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _current_user_id(request: Request) -> str:
    header_user = request.headers.get("x-user-id")
    query_user = request.query_params.get("user_id")
    return header_user or query_user or settings.demo_user_id


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> dict:
    return {
        "name": "Proofy API",
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/api/bootstrap")
async def bootstrap(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.bootstrap(user_id)


@app.post("/api/auth/signup")
async def signup(request: Request) -> dict:
    payload = await request.json()
    try:
        return auth_service.signup(
            str(payload.get("email", "")),
            str(payload.get("password", "")),
            str(payload.get("displayName", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/auth/login")
async def login(request: Request) -> dict:
    payload = await request.json()
    try:
        return auth_service.login(
            str(payload.get("email", "")),
            str(payload.get("password", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/auth/me")
async def auth_me(request: Request) -> dict:
    return auth_service.session(_current_user_id(request))


@app.get("/api/content/catalog")
async def content_catalog() -> dict:
    return service.content_catalog()


@app.post("/api/content/activate")
async def activate_content(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    return service.activate_content_selection(
        user_id,
        bundle_id=str(payload["bundleId"]),
        lesson_id=str(payload["lessonId"]),
        problem_set_id=str(payload["problemSetId"]),
        problem_id=str(payload["problemId"]) if payload.get("problemId") else None,
    )


@app.post("/api/admin/content/generation-job")
async def generation_job(request: Request) -> dict:
    payload = await request.json()
    spec = ContentGenerationRequest(
        bundle_id=str(payload["bundleId"]),
        title=str(payload["title"]),
        unit_title=str(payload["unitTitle"]),
        concepts=list(payload.get("concepts", [])),
        target_exam=str(payload.get("targetExam", "2028학년도 수능")),
        lesson_count=int(payload.get("lessonCount", 1)),
        problem_count=int(payload.get("problemCount", 6)),
        focus=str(payload.get("focus", "개념 흐름과 오답 회복이 분명한 수능 대비형")),
    )
    return generator.generate_or_prepare_job(spec)


@app.post("/api/admin/content/import")
async def import_content_bundle(request: Request) -> dict:
    payload = await request.json()
    return service.import_content_bundle(payload)


@app.delete("/api/admin/content/{bundle_id}")
async def delete_content_bundle(bundle_id: str) -> dict:
    return service.delete_content_bundle(bundle_id)


@app.post("/api/admin/content/review-generated")
async def review_generated_content_bundle(request: Request) -> dict:
    payload = await request.json()
    return service.review_generated_content_bundle(
        payload.get("bundle", payload),
        source_provider=str(payload.get("sourceProvider", "gemini")),
        import_approved=bool(payload.get("importApproved", False)),
    )


@app.get("/api/admin/content/reviews")
async def list_content_reviews() -> dict:
    return service.list_review_reports()


@app.get("/api/admin/content/reviews/{review_job_id}")
async def get_content_review(review_job_id: str) -> dict:
    response = service.get_review_report(review_job_id)
    if response.get("empty"):
        raise HTTPException(status_code=404, detail="review not found")
    return response


@app.post("/api/admin/strategy/run")
async def run_strategy_jobs(request: Request) -> dict:
    payload = await request.json() if request.headers.get("content-length") else {}
    return service.process_strategy_jobs(
        user_id=str(payload.get("userId")) if payload.get("userId") else None,
        limit=int(payload.get("limit") or 10),
    )


@app.get("/api/dashboard")
async def dashboard(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.dashboard(user_id)


@app.post("/api/profile")
async def update_profile(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    try:
        return service.update_profile(user_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/diagnostic/progress")
async def save_diagnostic_progress(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    try:
        return service.save_diagnostic_progress(user_id, payload.get("answers", {}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/diagnostic/submit")
async def submit_diagnostic(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    try:
        return service.submit_diagnostic(user_id, payload.get("answers", {}))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/lesson/session")
async def lesson_session(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.lesson_session(user_id)


@app.post("/api/lesson/question")
async def lesson_question(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    return service.answer_question(
        user_id,
        str(payload.get("question", "")),
        str(payload.get("sceneId")) if payload.get("sceneId") else None,
        str(payload.get("selectedObjectId")) if payload.get("selectedObjectId") else None,
        list(payload.get("runtimeSceneIds", [])) if isinstance(payload.get("runtimeSceneIds"), list) else None,
    )


@app.post("/api/lesson/complete")
async def complete_lesson(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.complete_lesson(user_id)


@app.post("/api/practice/submit")
async def submit_practice(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    return service.submit_practice(user_id, payload)


@app.post("/api/practice/next")
async def advance_practice(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.advance_practice(user_id)


@app.get("/api/review/latest")
async def review_latest(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.review_latest(user_id)


@app.get("/api/mistake-notes")
async def mistake_notes(request: Request) -> dict:
    user_id = _current_user_id(request)
    return service.mistake_notes(user_id)


@app.post("/api/gamification/theme")
async def set_theme(request: Request) -> dict:
    user_id = _current_user_id(request)
    payload = await request.json()
    return service.set_active_theme(user_id, str(payload.get("themeId", "")))


@app.websocket("/ws/sessions/{session_id}")
async def session_events(websocket: WebSocket, session_id: str, participant: str = "viewer") -> None:
    await hub.connect(session_id, websocket)
    await websocket.send_json(
        {
            "type": "session.connected",
            "actor": "system",
            "payload": {"participant": participant, "sessionId": session_id},
        }
    )
    for event in service.list_session_events(session_id):
        await websocket.send_json(event)
    try:
        while True:
            payload = await websocket.receive_json()
            event = service.register_session_event(session_id, participant, payload)
            await hub.broadcast(session_id, event)
    except WebSocketDisconnect:
        hub.disconnect(session_id, websocket)
