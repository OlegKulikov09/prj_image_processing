"""FastAPI backend for the video retrieval system.

Serves the search API, the keyframe images and proxy videos, the frontend,
and proxies submissions to DRES.

Run:  python -m uvicorn backend.app:app --reload   (from project root)
  or: python backend/app.py
"""
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config
from common import connect_db
from backend.dres import DresClient, DresError
from backend.search import SearchIndex

app = FastAPI(title="V3C Video Retrieval")

index = SearchIndex()                       # loads embeddings into memory
dres = DresClient(config.DRES_BASE_URL)     # session filled in on /api/dres/login
dres_state = {"evaluation_id": None, "evaluation_name": None, "user": None}

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
def warmup():
    """Load the SigLIP model now so the first real query is instant."""
    index.search_text("warmup", k=1)


# --------------------------------------------------------------------------
# Result enrichment: shot_id + score -> full record with URLs
# --------------------------------------------------------------------------
def enrich(pairs: list[tuple[int, float]]) -> list[dict]:
    if not pairs:
        return []
    scores = {sid: sc for sid, sc in pairs}
    placeholders = ",".join("?" * len(scores))
    conn = connect_db()
    rows = conn.execute(
        f"SELECT s.shot_id, s.video_id, s.shot_idx, s.start_frame, s.end_frame, "
        f"s.mid_frame, s.start_ms, s.end_ms, v.fps, v.duration, v.description "
        f"FROM shots s JOIN videos v ON v.video_id = s.video_id "
        f"WHERE s.shot_id IN ({placeholders})",
        list(scores.keys()),
    ).fetchall()
    conn.close()

    by_id = {}
    for r in rows:
        d = dict(r)
        d["score"] = round(scores[d["shot_id"]], 4)
        d["keyframe_url"] = f"/keyframes/{d['video_id']}/{d['shot_idx']:04d}.jpg"
        d["video_url"] = f"/media/{d['video_id']}.mp4"
        by_id[d["shot_id"]] = d
    # preserve ranking order
    return [by_id[sid] for sid, _ in pairs if sid in by_id]


# --------------------------------------------------------------------------
# Search API
# --------------------------------------------------------------------------
@app.get("/api/search")
def search(q: str, k: int = 60):
    return {"query": q, "results": enrich(index.search_text(q, k))}


@app.get("/api/similar")
def similar(shot_id: int, k: int = 60):
    return {"shot_id": shot_id, "results": enrich(index.search_similar(shot_id, k))}


@app.get("/api/video/{video_id}/shots")
def video_shots(video_id: str):
    """All shots of one video, in order — for browsing / temporal context."""
    conn = connect_db()
    rows = conn.execute(
        "SELECT shot_id FROM shots WHERE video_id = ? ORDER BY shot_idx", (video_id,)
    ).fetchall()
    conn.close()
    pairs = [(r["shot_id"], 0.0) for r in rows]
    results = enrich(pairs)
    results.sort(key=lambda d: d["shot_idx"])
    return {"video_id": video_id, "results": results}


# --------------------------------------------------------------------------
# DRES API
# --------------------------------------------------------------------------
class LoginBody(BaseModel):
    username: str
    password: str


class SubmitBody(BaseModel):
    shot_id: int | None = None
    video_id: str | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    text: str | None = None


def resolve_evaluation():
    """One network call: list the currently *running* evaluations, pick ours
    (by name, else the first one), and remember it. DRES only lists a task while
    it is running, so this yields None whenever no task is active right now.
    Returns (chosen_or_None, all_running_evaluations).
    """
    try:
        evals = dres.list_evaluations()
    except DresError:
        evals = []
    chosen = None
    for e in evals:
        if e.get("name") == config.DRES_EVALUATION_NAME:
            chosen = e
            break
    if chosen is None and evals:
        chosen = evals[0]
    dres_state["evaluation_id"] = chosen["id"] if chosen else None
    dres_state["evaluation_name"] = chosen.get("name") if chosen else None
    return chosen, evals


@app.post("/api/dres/login")
def dres_login(body: LoginBody):
    # Authentication is the only thing that can fail here. Finding the active
    # task is best-effort: it may not be running yet (that's not a login error).
    try:
        dres.login(body.username, body.password)
    except DresError as e:
        raise HTTPException(status_code=400, detail=str(e))
    dres_state["user"] = body.username
    _, evals = resolve_evaluation()
    return {
        "ok": True,
        "logged_in": True,
        "evaluation_id": dres_state["evaluation_id"],
        "evaluation_name": dres_state["evaluation_name"],
        "available": [e.get("name") for e in evals],
    }


@app.get("/api/dres/status")
def dres_status():
    # If logged in but not yet locked onto a task, re-check — it may have just
    # started. Once resolved, this returns the cached value with no network call.
    if dres.session_id is not None and dres_state["evaluation_id"] is None:
        resolve_evaluation()
    return {
        "logged_in": dres.session_id is not None,
        "evaluation_id": dres_state["evaluation_id"],
        "evaluation_name": dres_state["evaluation_name"],
        "user": dres_state["user"],
    }


@app.post("/api/dres/logout")
def dres_logout():
    dres.logout()
    dres_state.update(evaluation_id=None, evaluation_name=None, user=None)
    return {"ok": True, "logged_in": False}


@app.post("/api/dres/submit")
def dres_submit(body: SubmitBody):
    if dres.session_id is None:
        raise HTTPException(status_code=400, detail="not logged in to DRES")
    # The task may have started after login — try to lock onto it now.
    if dres_state["evaluation_id"] is None:
        resolve_evaluation()
    if dres_state["evaluation_id"] is None:
        raise HTTPException(
            status_code=400,
            detail="no active evaluation task is running on DRES yet — wait for "
                   "the instructor to start the task, then submit again",
        )

    video_id, start_ms, end_ms = body.video_id, body.start_ms, body.end_ms
    # If a shot_id was given, fill in its video and time range from the DB.
    if body.shot_id is not None:
        conn = connect_db()
        row = conn.execute(
            "SELECT video_id, start_ms, end_ms FROM shots WHERE shot_id = ?",
            (body.shot_id,),
        ).fetchone()
        conn.close()
        if row is None:
            raise HTTPException(status_code=404, detail="shot not found")
        video_id = video_id or row["video_id"]
        start_ms = start_ms if start_ms is not None else row["start_ms"]
        end_ms = end_ms if end_ms is not None else row["end_ms"]

    if video_id is None or start_ms is None or end_ms is None:
        raise HTTPException(status_code=400, detail="need shot_id or video_id+start_ms+end_ms")

    result = dres.submit(
        evaluation_id=dres_state["evaluation_id"],
        media_item_name=video_id,
        start_ms=int(start_ms),
        end_ms=int(end_ms),
        collection=config.DRES_COLLECTION,
        text=body.text,
    )
    return {"submitted": {"video_id": video_id, "start_ms": start_ms,
                          "end_ms": end_ms, "text": body.text}, "dres": result}


# --------------------------------------------------------------------------
# Static files: keyframes, proxy videos, frontend
# --------------------------------------------------------------------------
app.mount("/keyframes", StaticFiles(directory=config.KEYFRAME_DIR), name="keyframes")
app.mount("/media", StaticFiles(directory=config.PROXY_DIR), name="media")


@app.get("/")
def home():
    return FileResponse(FRONTEND_DIR / "index.html")


# frontend assets (app.js, style.css, ...) served from /static
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
