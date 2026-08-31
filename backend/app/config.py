"""Central configuration, loaded from .env with sensible macOS defaults."""
import getpass
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _clean(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


PGHOST = _clean("PGHOST", "localhost")
PGPORT = int(_clean("PGPORT", "5432"))
# Homebrew Postgres creates a superuser named after the macOS account.
PGUSER = _clean("PGUSER") or getpass.getuser()
PGPASSWORD = _clean("PGPASSWORD")
PGDATABASE = _clean("PGDATABASE", "semantic_images")
# Maintenance database used only to issue "CREATE DATABASE".
PGADMINDB = _clean("PGADMINDB", "postgres")

API_HOST = _clean("API_HOST", "127.0.0.1")
API_PORT = int(_clean("API_PORT", "8000"))

CLIP_MODEL = _clean("CLIP_MODEL", "openai/clip-vit-base-patch32")
EMBED_DIM = 512  # ViT-B/32 projection size

# Image files we try to index.
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
    ".tif", ".tiff", ".heic", ".heif", ".avif",
}

# Directory names that are never worth walking into.
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".cache",
    "Library", ".Trash", ".DS_Store", "site-packages", ".next", "dist",
}

# Roots the folder-browser and image server are allowed to touch.
BROWSE_ROOTS = [Path.home(), Path("/Volumes")]

THUMB_DIR = BASE_DIR / ".thumbnails"
BATCH_SIZE = 16


def dsn(database: str | None = None) -> str:
    """Build a libpq connection string."""
    parts = [
        f"host={PGHOST}",
        f"port={PGPORT}",
        f"user={PGUSER}",
        f"dbname={database or PGDATABASE}",
    ]
    if PGPASSWORD:
        parts.append(f"password={PGPASSWORD}")
    return " ".join(parts)
