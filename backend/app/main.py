"""Semantic Image Finder - HTTP API."""
import io
import logging
import os
import shlex
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
import psycopg
from fastapi import Body, FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from PIL import Image

from . import config, db, embedder, indexer

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s %(message)s")
log = logging.getLogger("semantic-image-finder")

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Create the database, extension, tables and index if they are missing."""
    ok, err = db.check_connection()
    if ok:
        result = db.initialize()
        log.info(
            "Database '%s' ready%s", result["database"],
            " (created just now)" if result["created"] else "",
        )
    else:
        log.error("Cannot reach PostgreSQL: %s", err)
        log.error("Start it with:  brew services start postgresql@18")
    config.THUMB_DIR.mkdir(exist_ok=True)
    yield


app = FastAPI(title="Semantic Image Finder", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # local-only tool; the API binds to 127.0.0.1
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Path safety - only files under a browse root or an indexed folder are served.
# --------------------------------------------------------------------------
def _indexed_roots() -> list[Path]:
    with db.cursor() as cur:
        cur.execute("SELECT path FROM folders")
        return [Path(r["path"]) for r in cur.fetchall()]


def _is_within(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (ValueError, OSError):
            continue
    return False


def safe_path(raw: str, *, must_exist: bool = True) -> Path:
    path = Path(os.path.expanduser(raw.strip()))
    if not path.is_absolute():
        raise HTTPException(400, "Please give a full path, e.g. /Users/you/Pictures")
    if must_exist and not path.exists():
        raise HTTPException(404, f"Not found: {path}")
    if not _is_within(path, config.BROWSE_ROOTS + _indexed_roots()):
        raise HTTPException(403, "That location is outside your home folder and /Volumes")
    return path


# --------------------------------------------------------------------------
# Status
# --------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/status")
def status() -> dict:
    connected, err = db.check_connection()
    payload = {
        "postgres_connected": connected,
        "postgres_error": None if connected else err,
        "database": config.PGDATABASE,
        "host": f"{config.PGHOST}:{config.PGPORT}",
        "user": config.PGUSER,
        "model": embedder.info(),
        "active_job": indexer.active_job(),
        "images": 0,
        "folders": 0,
    }
    if connected:
        try:
            with db.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM images")
                payload["images"] = cur.fetchone()["n"]
                cur.execute("SELECT count(*) AS n FROM folders")
                payload["folders"] = cur.fetchone()["n"]
        except Exception as exc:  # noqa: BLE001 - schema may not exist yet
            payload["postgres_error"] = str(exc)
    return payload


# --------------------------------------------------------------------------
# Folder browser (the browser itself cannot hand us a real directory path)
# --------------------------------------------------------------------------
@app.get("/api/browse")
def browse(path: str = Query(default="")) -> dict:
    target = Path.home() if not path else safe_path(path)
    if not target.is_dir():
        raise HTTPException(400, "Not a folder")
    entries = []
    try:
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if child.name.startswith(".") or not child.is_dir():
                continue
            if child.name in config.SKIP_DIRS:
                continue
            entries.append({"name": child.name, "path": str(child)})
    except PermissionError:
        raise HTTPException(403, "macOS blocked access to that folder. Grant Full Disk "
                                 "Access to Terminal in System Settings > Privacy & Security.")
    parent = str(target.parent) if _is_within(target.parent, config.BROWSE_ROOTS) else None
    return {"path": str(target), "parent": parent, "entries": entries}


# --------------------------------------------------------------------------
# Folders / indexing
# --------------------------------------------------------------------------
@app.get("/api/folders")
def list_folders() -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            """SELECT f.id, f.path, f.date_added, f.last_scanned_at,
                      count(i.id) AS image_count
                 FROM folders f
            LEFT JOIN images i ON i.folder_id = f.id
             GROUP BY f.id
             ORDER BY f.date_added DESC"""
        )
        rows = cur.fetchall()
    for row in rows:
        row["exists"] = os.path.isdir(row["path"])
    return rows


@app.post("/api/folders")
def add_folder(payload: dict = Body(...)) -> dict:
    if indexer.active_job():
        raise HTTPException(409, "An indexing job is already running. Wait for it to finish.")
    root = safe_path(payload.get("path", ""))
    if not root.is_dir():
        raise HTTPException(400, "That path is a file, not a folder.")

    # Overlapping roots would make one folder steal the other's images, because a
    # given file can only belong to one folder row.
    for existing in _indexed_roots():
        if existing == root:
            continue
        if _is_within(root, [existing]):
            raise HTTPException(
                409, f"That folder is already covered by {existing}. "
                     "Use 'Scan for new' on it instead."
            )
        if _is_within(existing, [root]):
            raise HTTPException(
                409, f"{existing} is already indexed and sits inside this folder. "
                     "Remove it first, then add this one."
            )

    job = indexer.start(root, kind="index", force=bool(payload.get("force")))
    return job.as_dict()


@app.post("/api/folders/{folder_id}/rescan")
def rescan(folder_id: int, force: bool = Query(default=False)) -> dict:
    if indexer.active_job():
        raise HTTPException(409, "An indexing job is already running.")
    with db.cursor() as cur:
        cur.execute("SELECT path FROM folders WHERE id = %s", (folder_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Folder not found")
    root = Path(row["path"])
    if not root.is_dir():
        raise HTTPException(404, f"Folder no longer exists on disk: {root}")
    return indexer.start(root, kind="rescan", force=force).as_dict()


@app.delete("/api/folders/{folder_id}")
def remove_folder(folder_id: int) -> dict:
    """Removes the folder and its vectors from the index. Never touches your files."""
    with db.cursor() as cur:
        cur.execute("DELETE FROM images WHERE folder_id = %s", (folder_id,))
        removed = cur.rowcount
        cur.execute("DELETE FROM folders WHERE id = %s", (folder_id,))
    return {"removed_images": removed}


@app.get("/api/jobs")
def jobs() -> list[dict]:
    return indexer.list_jobs()


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    found = indexer.get_job(job_id)
    if not found:
        raise HTTPException(404, "Job not found")
    return found.as_dict()


@app.post("/api/jobs/{job_id}/cancel")
def cancel(job_id: str) -> dict:
    return {"cancelled": indexer.cancel_job(job_id)}


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------
def _search(vector: np.ndarray, top_k: int, folder_id: int | None,
            exclude_path: str | None = None) -> list[dict]:
    clauses, params = [], [vector]
    if folder_id:
        clauses.append("folder_id = %s")
        params.append(folder_id)
    if exclude_path:
        clauses.append("path <> %s")
        params.append(exclude_path)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params.append(top_k)
    with db.cursor() as cur:
        cur.execute(
            f"""SELECT id, path, file_name, width, height, file_size, date_added,
                       1 - (embedding <=> %s) AS similarity
                  FROM images {where}
              ORDER BY similarity DESC
                 LIMIT %s""",
            params,
        )
        rows = cur.fetchall()
    for row in rows:
        row["similarity"] = round(float(row["similarity"]), 4)
    return rows


def _clamp(top_k: int) -> int:
    return max(1, min(int(top_k), 200))


@app.post("/api/search/image")
async def search_by_image(
    file: UploadFile = File(...),
    top_k: int = Query(default=10),
    folder_id: int | None = Query(default=None),
) -> dict:
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
    except Exception:
        raise HTTPException(400, "That file is not a readable image.")
    vector = embedder.embed_images([image])[0]
    return {"query": file.filename, "results": _search(vector, _clamp(top_k), folder_id)}


@app.post("/api/search/text")
def search_by_text(payload: dict = Body(...)) -> dict:
    text = (payload.get("query") or "").strip()
    if not text:
        raise HTTPException(400, "Type something to search for.")
    vector = embedder.embed_text(text)
    return {
        "query": text,
        "results": _search(vector, _clamp(payload.get("top_k", 10)), payload.get("folder_id")),
    }


@app.post("/api/search/similar/{image_id}")
def search_similar(image_id: int, payload: dict = Body(default={})) -> dict:
    """Find images like one that is already in the index."""
    with db.cursor() as cur:
        cur.execute("SELECT path, embedding FROM images WHERE id = %s", (image_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Image not in the index")
    return {
        "query": row["path"],
        "results": _search(row["embedding"], _clamp(payload.get("top_k", 10)),
                           payload.get("folder_id"), exclude_path=row["path"]),
    }


@app.get("/api/images")
def recent_images(limit: int = Query(default=60), offset: int = Query(default=0)) -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            """SELECT id, path, file_name, width, height, file_size, date_added
                 FROM images ORDER BY date_added DESC, id DESC LIMIT %s OFFSET %s""",
            (max(1, min(limit, 500)), max(0, offset)),
        )
        return cur.fetchall()


# --------------------------------------------------------------------------
# Serving the actual picture files
# --------------------------------------------------------------------------
@app.get("/api/file")
def original_file(path: str) -> FileResponse:
    target = safe_path(path)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target)


@app.get("/api/thumb")
def thumbnail(path: str, size: int = Query(default=320)) -> Response:
    target = safe_path(path)
    size = max(64, min(size, 1024))
    try:
        with Image.open(target) as img:
            img = img.convert("RGB")
            img.thumbnail((size, size), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82)
    except Exception:
        raise HTTPException(415, "Could not render a preview for this file.")
    return Response(
        buf.getvalue(),
        media_type="image/jpeg",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/api/reveal")
def reveal(payload: dict = Body(...)) -> dict:
    """Open the file in Finder - the single most useful thing after a search."""
    target = safe_path(payload.get("path", ""))
    os.system(f"open -R {shlex.quote(str(target))}")
    return {"revealed": str(target)}


# --------------------------------------------------------------------------
# One-click database actions
# --------------------------------------------------------------------------
@app.get("/api/admin/stats")
def admin_stats() -> dict:
    with db.cursor() as cur:
        cur.execute("SELECT count(*) AS n, coalesce(sum(file_size), 0) AS bytes FROM images")
        totals = cur.fetchone()
        cur.execute("SELECT pg_size_pretty(pg_database_size(current_database())) AS size")
        db_size = cur.fetchone()["size"]
        cur.execute(
            """SELECT f.path, count(i.id) AS n
                 FROM folders f LEFT JOIN images i ON i.folder_id = f.id
             GROUP BY f.path ORDER BY n DESC"""
        )
        per_folder = cur.fetchall()
        cur.execute("SELECT min(date_added) AS oldest, max(date_added) AS newest FROM images")
        span = cur.fetchone()
    return {
        "images": totals["n"],
        "indexed_bytes": int(totals["bytes"]),
        "database_size": db_size,
        "per_folder": per_folder,
        "oldest": span["oldest"],
        "newest": span["newest"],
        "vector_dimensions": config.EMBED_DIM,
    }


@app.post("/api/admin/prune")
def admin_prune() -> dict:
    """Drop index entries for files that were deleted or moved on disk."""
    return {"pruned": indexer.prune_missing()}


@app.post("/api/admin/clear")
def admin_clear(payload: dict = Body(default={})) -> dict:
    """Wipe every vector. Your image files are not touched."""
    if payload.get("confirm") != "DELETE":
        raise HTTPException(400, "Confirmation required")
    keep_folders = bool(payload.get("keep_folders", True))
    with db.cursor() as cur:
        cur.execute("DELETE FROM images")
        removed = cur.rowcount
        if not keep_folders:
            cur.execute("DELETE FROM folders")
    return {"removed": removed}


@app.post("/api/admin/vacuum")
def admin_vacuum() -> dict:
    """Reclaim disk space and refresh query planner statistics."""
    with psycopg.connect(config.dsn(), autocommit=True) as conn:
        conn.execute("VACUUM ANALYZE images")
    return {"ok": True}


@app.post("/api/admin/reindex")
def admin_reindex() -> dict:
    """Re-embed every registered folder from scratch, in one job."""
    if indexer.active_job():
        raise HTTPException(409, "An indexing job is already running.")
    with db.cursor() as cur:
        cur.execute("SELECT path FROM folders ORDER BY id")
        folders = [Path(r["path"]) for r in cur.fetchall() if os.path.isdir(r["path"])]
    if not folders:
        raise HTTPException(400, "No folders have been added yet.")
    return indexer.start(folders, kind="reindex", force=True).as_dict()


@app.post("/api/admin/rescan-all")
def admin_rescan_all() -> dict:
    """Pick up new or changed files in every registered folder."""
    if indexer.active_job():
        raise HTTPException(409, "An indexing job is already running.")
    with db.cursor() as cur:
        cur.execute("SELECT path FROM folders ORDER BY id")
        folders = [Path(r["path"]) for r in cur.fetchall() if os.path.isdir(r["path"])]
    if not folders:
        raise HTTPException(400, "No folders have been added yet.")
    return indexer.start(folders, kind="rescan", force=False).as_dict()


@app.post("/api/admin/thumbs/clear")
def admin_clear_thumbs() -> dict:
    if config.THUMB_DIR.exists():
        shutil.rmtree(config.THUMB_DIR)
    config.THUMB_DIR.mkdir(exist_ok=True)
    return {"ok": True}
