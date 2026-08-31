"""Recursive folder scanning and incremental indexing, run as background jobs."""
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

from PIL import Image

from . import config, db, embedder

log = logging.getLogger(__name__)


@dataclass
class Job:
    id: str
    kind: str                      # "index" | "rescan" | "reindex"
    folder: str
    status: str = "queued"         # queued | scanning | running | done | error | cancelled
    total: int = 0
    processed: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    current: str = ""
    message: str = ""
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancel: bool = False

    def as_dict(self) -> dict:
        data = asdict(self)
        data.pop("cancel", None)
        data["elapsed"] = round((self.finished_at or time.time()) - self.started_at, 1)
        data["percent"] = round(100 * self.processed / self.total, 1) if self.total else 0.0
        return data


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()
# Only one indexing job at a time - the model is the bottleneck anyway.
_run_lock = threading.Lock()


def get_job(job_id: str) -> Job | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def list_jobs(limit: int = 20) -> list[dict]:
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)
    return [j.as_dict() for j in jobs[:limit]]


def active_job() -> dict | None:
    with _jobs_lock:
        for job in _jobs.values():
            if job.status in ("queued", "scanning", "running"):
                return job.as_dict()
    return None


def cancel_job(job_id: str) -> bool:
    job = get_job(job_id)
    if not job or job.status in ("done", "error", "cancelled"):
        return False
    job.cancel = True
    return True


def walk_images(root: Path) -> list[Path]:
    """Every image file under root, at any nesting depth."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune noisy/system directories in place so os.walk skips them entirely.
        dirnames[:] = [
            d for d in dirnames
            if d not in config.SKIP_DIRS and not d.startswith(".")
            and not d.endswith((".photoslibrary", ".app", ".bundle"))
        ]
        for name in filenames:
            if Path(name).suffix.lower() in config.IMAGE_EXTENSIONS:
                found.append(Path(dirpath) / name)
    return found


def upsert_folder(path: Path) -> int:
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO folders (path) VALUES (%s)
               ON CONFLICT (path) DO UPDATE SET path = EXCLUDED.path
               RETURNING id""",
            (str(path),),
        )
        return cur.fetchone()["id"]


def _existing_fingerprints(folder_id: int) -> dict[str, tuple[int, float]]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT path, file_size, file_mtime FROM images WHERE folder_id = %s",
            (folder_id,),
        )
        return {r["path"]: (r["file_size"], r["file_mtime"]) for r in cur.fetchall()}


def _store_batch(folder_id: int, batch: list[tuple[Path, os.stat_result, Image.Image]], job: Job) -> None:
    vectors = embedder.embed_images([item[2] for item in batch])
    with db.cursor() as cur:
        for (path, st, img), vec in zip(batch, vectors):
            cur.execute(
                """INSERT INTO images
                     (folder_id, path, file_name, file_size, file_mtime,
                      width, height, embedding)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (path) DO UPDATE SET
                     folder_id  = EXCLUDED.folder_id,
                     file_size  = EXCLUDED.file_size,
                     file_mtime = EXCLUDED.file_mtime,
                     width      = EXCLUDED.width,
                     height     = EXCLUDED.height,
                     embedding  = EXCLUDED.embedding,
                     indexed_at = now()
                   RETURNING (xmax = 0) AS inserted""",
                (folder_id, str(path), path.name, st.st_size, st.st_mtime,
                 img.width, img.height, vec),
            )
            if cur.fetchone()["inserted"]:
                job.added += 1
            else:
                job.updated += 1
    for _, _, img in batch:
        img.close()


def _run(job: Job, roots: list[Path], force: bool) -> None:
    """Index every image under each root. Runs on a background thread."""
    with _run_lock:
        batch: list[tuple[Path, os.stat_result, Image.Image]] = []
        try:
            embedder.load()
            job.status = "scanning"
            job.message = "Looking for images..."

            # Resolve every folder up front so the progress total is accurate.
            plan: list[tuple[int, list[Path]]] = []
            for root in roots:
                plan.append((upsert_folder(root), walk_images(root)))
            job.total = sum(len(group) for _, group in plan)

            if job.total == 0:
                job.status = "done"
                job.message = "No images found in that folder."
                return

            job.status = "running"
            job.message = f"Indexing {job.total} images"

            for folder_id, group in plan:
                if job.cancel:
                    break
                known = {} if force else _existing_fingerprints(folder_id)

                for path in group:
                    if job.cancel:
                        break
                    job.current = path.name
                    try:
                        st = path.stat()
                        prior = known.get(str(path))
                        # Same size and mtime means the stored vector is still valid.
                        if prior and prior[0] == st.st_size and abs(prior[1] - st.st_mtime) < 1e-6:
                            job.skipped += 1
                            job.processed += 1
                            continue
                        img = Image.open(path)
                        img.load()
                        batch.append((path, st, img))
                    except Exception as exc:  # noqa: BLE001 - one bad file must not stop the run
                        job.failed += 1
                        job.processed += 1
                        log.warning("Skipping %s: %s", path, exc)
                        continue

                    if len(batch) >= config.BATCH_SIZE:
                        _store_batch(folder_id, batch, job)
                        job.processed += len(batch)
                        batch = []

                # Flush the tail of this folder before moving to the next one.
                if batch and not job.cancel:
                    _store_batch(folder_id, batch, job)
                    job.processed += len(batch)
                    batch = []

                if not job.cancel:
                    with db.cursor() as cur:
                        cur.execute(
                            "UPDATE folders SET last_scanned_at = now() WHERE id = %s",
                            (folder_id,),
                        )

            job.current = ""
            job.status = "cancelled" if job.cancel else "done"
            job.message = (
                f"{job.added} added, {job.updated} updated, "
                f"{job.skipped} unchanged, {job.failed} failed"
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("Indexing failed")
            job.status = "error"
            job.message = str(exc)
        finally:
            for _, _, img in batch:
                try:
                    img.close()
                except Exception:
                    pass
            job.finished_at = time.time()


def start(roots: Path | list[Path], kind: str = "index", force: bool = False) -> Job:
    """Queue a background indexing job for one or more folders."""
    root_list = [roots] if isinstance(roots, Path) else list(roots)
    label = str(root_list[0]) if len(root_list) == 1 else f"{len(root_list)} folders"
    job = Job(id=uuid.uuid4().hex[:12], kind=kind, folder=label)
    with _jobs_lock:
        _jobs[job.id] = job
        # Keep the job list from growing forever.
        if len(_jobs) > 50:
            for old in sorted(_jobs.values(), key=lambda j: j.started_at)[:10]:
                if old.status in ("done", "error", "cancelled"):
                    _jobs.pop(old.id, None)
    threading.Thread(target=_run, args=(job, root_list, force), daemon=True).start()
    return job


def prune_missing() -> int:
    """Delete rows whose file no longer exists on disk."""
    with db.cursor() as cur:
        cur.execute("SELECT id, path FROM images")
        gone = [r["id"] for r in cur.fetchall() if not os.path.exists(r["path"])]
        for i in range(0, len(gone), 500):
            cur.execute("DELETE FROM images WHERE id = ANY(%s)", (gone[i:i + 500],))
    return len(gone)
