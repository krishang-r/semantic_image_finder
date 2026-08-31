"""Database bootstrap and connection pooling.

Everything in here is idempotent: the app can create the database, the
pgvector extension, the tables and the index on every start-up without
harming an existing installation.
"""
import logging
import threading
from contextlib import contextmanager

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from . import config

log = logging.getLogger(__name__)

_local = threading.local()

SCHEMA = f"""
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS folders (
    id              BIGSERIAL PRIMARY KEY,
    path            TEXT UNIQUE NOT NULL,
    date_added      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_scanned_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS images (
    id          BIGSERIAL PRIMARY KEY,
    folder_id   BIGINT REFERENCES folders(id) ON DELETE CASCADE,
    path        TEXT UNIQUE NOT NULL,
    file_name   TEXT NOT NULL,
    file_size   BIGINT NOT NULL,
    file_mtime  DOUBLE PRECISION NOT NULL,
    width       INTEGER,
    height      INTEGER,
    embedding   VECTOR({config.EMBED_DIM}) NOT NULL,
    date_added  TIMESTAMPTZ NOT NULL DEFAULT now(),
    indexed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS images_folder_idx ON images (folder_id);
CREATE INDEX IF NOT EXISTS images_date_idx   ON images (date_added DESC);
"""

# Built separately: HNSW build is slower, and we want it after the table exists.
VECTOR_INDEX = """
CREATE INDEX IF NOT EXISTS images_embedding_idx
    ON images USING hnsw (embedding vector_cosine_ops);
"""


def ensure_database() -> bool:
    """Create the target database if it does not exist. Returns True if created."""
    with psycopg.connect(config.dsn(config.PGADMINDB), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (config.PGDATABASE,)
        ).fetchone()
        if exists:
            return False
        # Identifiers cannot be parameterised; the name comes from our own config.
        conn.execute(f'CREATE DATABASE "{config.PGDATABASE}"')
        log.info("Created database %s", config.PGDATABASE)
        return True


def ensure_schema() -> None:
    with psycopg.connect(config.dsn(), autocommit=True) as conn:
        conn.execute(SCHEMA)
        conn.execute(VECTOR_INDEX)


def initialize() -> dict:
    """Full bootstrap. Safe to call on every start-up."""
    created = ensure_database()
    ensure_schema()
    return {"database": config.PGDATABASE, "created": created}


def _connection() -> psycopg.Connection:
    """One long-lived connection per thread, reconnected if it died."""
    conn = getattr(_local, "conn", None)
    if conn is None or conn.closed:
        conn = psycopg.connect(config.dsn(), autocommit=True, row_factory=dict_row)
        register_vector(conn)
        _local.conn = conn
    return conn


@contextmanager
def cursor():
    conn = _connection()
    try:
        with conn.cursor() as cur:
            yield cur
    except psycopg.OperationalError:
        # Connection went stale (e.g. Postgres restarted) - drop it and retry once.
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None
        conn = _connection()
        with conn.cursor() as cur:
            yield cur


def check_connection() -> tuple[bool, str]:
    try:
        with psycopg.connect(config.dsn(config.PGADMINDB), connect_timeout=3):
            return True, "ok"
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the UI
        return False, str(exc).strip().splitlines()[0] if str(exc) else repr(exc)
