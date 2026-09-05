"""Incremental indexing: diff against the manifest, extract + chunk + embed
changed files, and hand any embedded images back to Claude for captioning
via a two-pass split (--diff-only, then --ingest-captions)."""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk as chunk_module  # noqa: E402
import db as db_module  # noqa: E402
import extract  # noqa: E402
from embedding import embed_documents  # noqa: E402
from manifest import iter_documents, load_manifest, resolve_root, save_manifest  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def insert_chunks(conn, doc_id: int, chunk_dicts: list[dict], chunk_type: str) -> None:
    if not chunk_dicts:
        return
    vectors = embed_documents([c["text"] for c in chunk_dicts])
    for c, vec in zip(chunk_dicts, vectors):
        cur = conn.execute(
            "INSERT INTO chunks (doc_id, chunk_type, page_number, section_label, seq_in_page, text, image_ref, token_count) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (doc_id, chunk_type, c.get("page_number"), c.get("section_label"), c.get("seq_in_page", 0),
             c["text"], c.get("image_ref"), len(c["text"].split())),
        )
        conn.execute(
            "INSERT INTO embeddings (chunk_id, model_name, dim, vector) VALUES (?,?,?,?)",
            (cur.lastrowid, "BAAI/bge-small-en-v1.5", vec.shape[0], vec.tobytes()),
        )


def process_root(root: Path, full: bool) -> dict:
    dhi_dir = root / ".dhi"
    db_path = dhi_dir / "index.sqlite3"
    db_module.init_db(db_path)
    conn = db_module.connect(db_path)

    manifest = load_manifest(root)
    files_manifest = manifest.get("files", {})

    current = {rel_path: (topic, abs_path) for topic, rel_path, abs_path in iter_documents(root)}
    existing_docs = {
        row[1]: row for row in conn.execute("SELECT doc_id, rel_path, content_hash FROM documents").fetchall()
    }

    image_dir = dhi_dir / "images"
    added = updated = 0
    pending_images = []

    for rel_path, (topic, abs_path) in current.items():
        st = abs_path.stat()
        prev_stat = files_manifest.get(rel_path)
        looks_changed = full or prev_stat is None or prev_stat["size"] != st.st_size or prev_stat["mtime"] != st.st_mtime
        if not looks_changed:
            continue

        content_hash = sha256_file(abs_path)
        prev_row = existing_docs.get(rel_path)
        if prev_row and prev_row[2] == content_hash and not full:
            files_manifest[rel_path] = {"size": st.st_size, "mtime": st.st_mtime}
            continue

        doc_image_dir = image_dir / hashlib.md5(rel_path.encode()).hexdigest()[:12]
        units, images = extract.extract(abs_path, doc_image_dir)
        chunks = chunk_module.chunk_units(units)
        file_type = abs_path.suffix.lower().lstrip(".")

        if prev_row:
            doc_id = prev_row[0]
            conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            conn.execute(
                "UPDATE documents SET topic=?, file_type=?, content_hash=?, mtime=?, file_size=?, last_indexed=? WHERE doc_id=?",
                (topic, file_type, content_hash, st.st_mtime, st.st_size, now_iso(), doc_id),
            )
            updated += 1
        else:
            cur = conn.execute(
                "INSERT INTO documents (topic, rel_path, file_type, content_hash, mtime, file_size, last_indexed) "
                "VALUES (?,?,?,?,?,?,?)",
                (topic, rel_path, file_type, content_hash, st.st_mtime, st.st_size, now_iso()),
            )
            doc_id = cur.lastrowid
            added += 1

        insert_chunks(conn, doc_id, chunks, "text")

        for img in images:
            pending_images.append({
                "doc_id": doc_id,
                "rel_path": rel_path,
                "topic": topic,
                "page_number": img["page_number"],
                "section_label": img["section_label"],
                "image_path": str(img["image_path"]),
            })

        files_manifest[rel_path] = {"size": st.st_size, "mtime": st.st_mtime}

    removed = 0
    for rel_path, row in existing_docs.items():
        if rel_path not in current:
            conn.execute("DELETE FROM documents WHERE doc_id=?", (row[0],))
            files_manifest.pop(rel_path, None)
            removed += 1

    conn.commit()
    conn.close()

    manifest["files"] = files_manifest
    pending_path = dhi_dir / "pending_captions.json"
    if pending_images:
        pending_path.write_text(json.dumps(pending_images, indent=2))
    else:
        pending_path.unlink(missing_ok=True)
        manifest["last_full_index_ts"] = now_iso()
    save_manifest(root, manifest)

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "pending_images": len(pending_images),
        "pending_captions_file": str(pending_path) if pending_images else None,
    }


def ingest_captions(root: Path, captions_path: Path) -> dict:
    dhi_dir = root / ".dhi"
    conn = db_module.connect(dhi_dir / "index.sqlite3")
    items = json.loads(captions_path.read_text())

    by_doc: dict[int, list[dict]] = {}
    for item in items:
        by_doc.setdefault(item["doc_id"], []).append(item)

    count = 0
    for doc_id, doc_items in by_doc.items():
        chunk_dicts = [
            {
                "page_number": item["page_number"],
                "section_label": item["section_label"],
                "seq_in_page": 1000 + i,  # ordered after this page's text chunks
                "text": item["caption"],
                "image_ref": item["image_path"],
            }
            for i, item in enumerate(doc_items)
        ]
        insert_chunks(conn, doc_id, chunk_dicts, "image_caption")
        count += len(chunk_dicts)

    conn.commit()
    conn.close()

    manifest = load_manifest(root)
    manifest["last_full_index_ts"] = now_iso()
    save_manifest(root, manifest)
    captions_path.unlink(missing_ok=True)
    return {"status": "captions_ingested", "count": count}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    ap.add_argument("--full", action="store_true", help="Reprocess every file, ignoring the manifest")
    ap.add_argument("--ingest-captions", help="Path to a JSON file of {doc_id, ..., caption} entries")
    args = ap.parse_args()
    root = resolve_root(args.root)

    if args.ingest_captions:
        print(json.dumps(ingest_captions(root, Path(args.ingest_captions))))
        return

    print(json.dumps(process_root(root, full=args.full)))


if __name__ == "__main__":
    main()
