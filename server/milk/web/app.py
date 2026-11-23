"""Dashboard and API: the hub.

The counter posts results here, from this server or from a GPU machine through CloudFront,
always with the internal token. The hub stores frames and results with the server's own
IAM role, so counting workers never hold AWS keys. Browsers long-poll /api/live. State lives
in memory, so run exactly one process.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from .. import config
from ..cvoutput import CAPTURE_LOG_COLUMNS, CV_OUTPUT_COLUMNS, to_csv
from ..store import Persistence

log = logging.getLogger("milk.web")
settings = config.load()
PERSIST: Persistence | None = None
if settings.bucket and settings.table:
    PERSIST = Persistence(settings.region, settings.bucket, settings.table)
    PERSIST.start()
ORIGIN_SECRET = os.environ.get("MILK_ORIGIN_SECRET", "")
STATIC = Path(__file__).parent / "static"
SKUS = json.loads((Path(__file__).resolve().parents[1] / "skus.json").read_text("utf-8"))
SESSION_COOKIE = "milk_session"
SESSION_HOURS = 12
LOCAL_HOSTS = {"127.0.0.1", "::1"}
NO_STORE = {"Cache-Control": "no-store"}

app = FastAPI(title="Milk shelf counter", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class CameraState:
    def __init__(self) -> None:
        self.seq = 0
        self.meta: dict | None = None
        self.jpeg = b""
        self.status: dict = {}
        self.status_at = 0.0
        self.cond = asyncio.Condition()
        self.history: deque[dict] = deque(maxlen=3600)
        self.flags: deque[dict] = deque(maxlen=300)


STATE: dict[str, CameraState] = {}


def state_for(camera: str | None) -> CameraState:
    return STATE.setdefault(camera or settings.camera_id, CameraState())


# --- access control -------------------------------------------------------------------


@app.middleware("http")
async def guard(request: Request, call_next):
    client = request.client.host if request.client else ""
    local = client in LOCAL_HOSTS
    # Only CloudFront knows the origin secret; anything else reaching the server directly is refused.
    if (
        not local
        and ORIGIN_SECRET
        and not hmac.compare_digest(request.headers.get("x-origin-verify", ""), ORIGIN_SECRET)
    ):
        return Response(status_code=403)
    # Counting workers, local or remote, must present the internal token.
    if request.url.path.startswith("/internal/") and not (
        settings.internal_token
        and hmac.compare_digest(request.headers.get("x-internal-token", ""), settings.internal_token)
    ):
        return Response(status_code=403)
    return await call_next(request)


def _sign(expires: int) -> str:
    mac = hmac.new(settings.web_secret.encode(), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{mac}"


def _authed(request: Request) -> bool:
    token = request.cookies.get(SESSION_COOKIE, "")
    expires, _, _ = token.partition(".")
    if not settings.web_secret or not expires.isdigit() or int(expires) < time.time():
        return False
    return hmac.compare_digest(_sign(int(expires)), token)


def _require(request: Request) -> None:
    if not _authed(request):
        raise HTTPException(status_code=401, detail="login required")


@app.get("/healthz")
async def healthz():
    # The pipeline's smoke test reads the version to know which build answers.
    return {"ok": True, "environment": settings.environment, "version": settings.version}


@app.get("/")
async def index(request: Request):
    if not _authed(request):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(STATIC / "index.html", headers=NO_STORE)


@app.get("/login")
async def login_page():
    return FileResponse(STATIC / "login.html", headers=NO_STORE)


@app.post("/api/login")
async def login(request: Request):
    if not settings.web_password or not settings.web_secret:
        raise HTTPException(status_code=503, detail="password not configured")
    try:
        password = str((await request.json()).get("password", ""))
    except Exception:  # noqa: BLE001
        password = ""
    if not hmac.compare_digest(password.encode(), settings.web_password.encode()):
        await asyncio.sleep(1.0)
        raise HTTPException(status_code=401, detail="Sai mật khẩu")
    expires = int(time.time()) + SESSION_HOURS * 3600
    response = JSONResponse({"ok": True})
    response.set_cookie(
        SESSION_COOKIE,
        _sign(expires),
        max_age=SESSION_HOURS * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return response


@app.post("/api/logout")
async def logout():
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response


# --- from the counter (localhost only) -------------------------------------------------


@app.post("/internal/result")
async def internal_result(request: Request):
    payload = await request.json()
    meta = payload["meta"]
    jpeg = base64.b64decode(payload["jpeg_b64"])
    st = state_for(meta["camera_id"])
    async with st.cond:
        st.seq += 1
        meta["seq"] = st.seq
        st.meta, st.jpeg = meta, jpeg
        st.history.append(
            {"t": meta["received_at"], "total": sum(meta["smoothed"].values()), "smoothed": meta["smoothed"]}
        )
        for row in meta.get("flagged", []):
            st.flags.appendleft(
                {**row, "capture_id": meta["capture_id"], "capture_timestamp": meta["capture_timestamp"]}
            )
        st.cond.notify_all()
    return {"ok": True, "seq": st.seq}


@app.post("/internal/status")
async def internal_status(request: Request):
    payload = await request.json()
    st = state_for(payload.get("camera_id"))
    st.status, st.status_at = payload, time.time()
    return {"ok": True}


@app.post("/internal/persist")
async def internal_persist(request: Request):
    if PERSIST is None:
        raise HTTPException(status_code=503, detail="storage not configured")
    payload = await request.json()
    jpeg = base64.b64decode(payload["jpeg_b64"]) if payload.get("jpeg_b64") else None
    PERSIST.submit(payload["record"], jpeg)
    return JSONResponse({"ok": True}, status_code=202)


# --- dashboard API ---------------------------------------------------------------------


def _status_view(st: CameraState) -> dict:
    age = time.time() - st.status_at if st.status_at else None
    storage = (
        None
        if PERSIST is None
        else {
            "saved": PERSIST.saved,
            "dropped": PERSIST.dropped,
            "last_error": PERSIST.last_error,
        }
    )
    return {
        "worker_ok": age is not None and age < 10,
        "worker": st.status,
        "storage": storage,
        "frame_age_s": None if st.meta is None else round(time.time() - st.meta["received_at"], 1),
    }


@app.get("/api/live")
async def live(request: Request, camera: str | None = None, after: int = 0):
    _require(request)
    st = state_for(camera)
    async with st.cond:
        if after == st.seq:  # nothing new yet: wait for the next result (a reset server has seq < after)
            try:
                await asyncio.wait_for(st.cond.wait_for(lambda: st.seq != after), timeout=20)
            except TimeoutError:
                pass
        meta = st.meta if st.seq != after else None
    return JSONResponse({"seq": st.seq, "meta": meta, "status": _status_view(st)}, headers=NO_STORE)


@app.get("/api/frame")
async def frame(request: Request, camera: str | None = None):
    _require(request)
    st = state_for(camera)
    if not st.jpeg:
        raise HTTPException(status_code=404, detail="no frame yet")
    return Response(st.jpeg, media_type="image/jpeg", headers=NO_STORE)


@app.get("/api/history")
async def history(request: Request, camera: str | None = None, minutes: float = 10):
    _require(request)
    since = time.time() - minutes * 60
    return JSONResponse([h for h in state_for(camera).history if h["t"] >= since], headers=NO_STORE)


@app.get("/api/flags")
async def flags(request: Request, camera: str | None = None, limit: int = 50):
    _require(request)
    return JSONResponse(list(state_for(camera).flags)[: max(1, min(limit, 300))], headers=NO_STORE)


@app.get("/api/skus")
async def skus(request: Request):
    _require(request)
    return SKUS


def _mediamtx_path(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"{settings.mediamtx_api}/v3/paths/get/{path}", timeout=2) as response:
            info = json.load(response)
        return {
            "ready": bool(info.get("ready")),
            "tracks": info.get("tracks"),
            "source": (info.get("source") or {}).get("type"),
            "bytes_received": info.get("bytesReceived"),
            "ready_time": info.get("readyTime"),
        }
    except urllib.error.HTTPError as exc:
        return {"ready": False, "error": "no publisher" if exc.code == 404 else f"HTTP {exc.code}"}
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "error": f"{type(exc).__name__}: {exc}"}


@app.get("/api/status")
async def status(request: Request, camera: str | None = None):
    _require(request)
    st = state_for(camera)
    ingest = await asyncio.to_thread(_mediamtx_path, settings.camera_path)
    return JSONResponse(
        {
            **_status_view(st),
            "ingest": ingest,
            "camera_id": camera or settings.camera_id,
            "store_id": settings.store_id,
        },
        headers=NO_STORE,
    )


# --- exports in Datagent's format ------------------------------------------------------

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _day(value: str | None) -> str:
    if value is None:
        return datetime.now(timezone(timedelta(hours=settings.utc_offset_hours))).strftime("%Y-%m-%d")
    if not DATE_RE.match(value):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return value


def _query_day(camera: str, day: str) -> list[dict]:
    import boto3
    from boto3.dynamodb.conditions import Key

    table = boto3.resource("dynamodb", region_name=settings.region).Table(settings.table)
    prefix = f"CAP-{settings.store_code}-{day.replace('-', '')}"
    kwargs = {"KeyConditionExpression": Key("camera_id").eq(camera) & Key("capture_id").begins_with(prefix)}
    items: list[dict] = []
    while True:
        page = table.query(**kwargs)
        items += page["Items"]
        if "LastEvaluatedKey" not in page:
            return items
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]


async def _export(
    request: Request, camera: str | None, date: str | None, field: str, columns: list[str], name: str
) -> Response:
    _require(request)
    if not settings.table:
        raise HTTPException(status_code=503, detail="storage not configured")
    camera, day = camera or settings.camera_id, _day(date)
    items = await asyncio.to_thread(_query_day, camera, day)
    records: list[dict] = []
    for item in items:
        value = json.loads(item[field])
        records += value if isinstance(value, list) else [value]
    body = to_csv(records, columns).encode("utf-8")
    filename = f"{name}_{camera}_{day}.csv"
    return Response(
        body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"', **NO_STORE},
    )


@app.get("/api/export/cv-output.csv")
async def export_cv_output(request: Request, camera: str | None = None, date: str | None = None):
    return await _export(request, camera, date, "rows_json", CV_OUTPUT_COLUMNS, "CV_Output")


@app.get("/api/export/capture-log.csv")
async def export_capture_log(request: Request, camera: str | None = None, date: str | None = None):
    return await _export(request, camera, date, "log_json", CAPTURE_LOG_COLUMNS, "Capture_Log")
