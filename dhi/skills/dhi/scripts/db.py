"""SQLite schema and connection helper for the dhi index."""

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    doc_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    topic         TEXT NOT NULL,
    rel_path      TEXT NOT NULL UNIQUE,
    file_type     TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    mtime         REAL NOT NULL,
    file_size     INTEGER NOT NULL,
    last_indexed  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id        INTEGER NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
    chunk_type    TEXT NOT NULL,
    page_number   INTEGER,
    section_label TEXT,
    seq_in_page   INTEGER NOT NULL,
    text          TEXT NOT NULL,
    image_ref     TEXT,
    token_count   INTEGER
);

CREATE TABLE IF NOT EXISTS embeddings (
    chunk_id      INTEGER PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    model_name    TEXT NOT NULL,
    dim           INTEGER NOT NULL,
    vector        BLOB NOT NULL
);

CREATE TABLE IF NOT EXISTS manifest_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_id ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_documents_topic ON documents(topic);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
