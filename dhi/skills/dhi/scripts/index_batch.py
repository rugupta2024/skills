"""Process a batch of Drive-file contents that Claude has already downloaded
via the Drive connector. Everything happens in memory except embedded
images, which are written to a transient temp directory just long enough for
Claude's vision to caption them in a second pass -- that directory (and the
pending-captions file) is deleted once ingest-captions runs. The source
document bytes themselves are never written to disk at any point.

Normal mode (no args): reads a JSON object from stdin:
  {"items": [{"file_id","title","topic","ext","modified_time","content_b64"}, ...],
   "removed_file_ids": [...]}
and returns a summary, including a pending_captions_file path if any
embedded images need captioning.

--ingest-captions <path>: second pass -- embeds the captions Claude wrote for
each pending image, stores them, and cleans up the transient temp files.
"""

import argparse
import base64
import json
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chunk as chunk_module  # noqa: E402
import db as db_module  # noqa: E402
import extract  # noqa: E402
from embedding import embed_documents  # noqa: E402
from manifest import load_manifest, save_manifest  # noqa: E402
from paths import DB_PATH  # noqa: E402


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def process_batch(items: list[dict], removed_file_ids: list[str]) -> dict:
    db_module.init_db(DB_PATH)
    conn = db_module.connect(DB_PATH)
    manifest = load_manifest()
    files_manifest = manifest.get("files", {})

    added = updated = 0
    pending_images = []
    temp_root = None

    for item in items:
        file_id = item["file_id"]
        title, topic, ext, modified_time = item["title"], item["topic"], item["ext"], item["modified_time"]
        data = base64.b64decode(item["content_b64"])

        if temp_root is None:
            temp_root = Path(tempfile.mkdtemp(prefix="dhi_index_"))
        doc_image_dir = temp_root / file_id
        units, images = extract.extract_bytes(ext, data, doc_image_dir)
        chunks = chunk_module.chunk_units(units)

        row = conn.execute("SELECT doc_id FROM documents WHERE file_id=?", (file_id,)).fetchone()
        if row:
            doc_id = row[0]
            conn.execute("DELETE FROM chunks WHERE doc_id=?", (doc_id,))
            conn.execute(
                "UPDATE documents SET topic=?, title=?, file_type=?, modified_time=?, last_indexed=? WHERE doc_id=?",
                (topic, title, ext, modified_time, now_iso(), doc_id),
            )
            updated += 1
        else:
            cur = conn.execute(
                "INSERT INTO documents (file_id, topic, title, file_type, modified_time, last_indexed) "
                "VALUES (?,?,?,?,?,?)",
                (file_id, topic, title, ext, modified_time, now_iso()),
            )
            doc_id = cur.lastrowid
            added += 1

        insert_chunks(conn, doc_id, chunks, "text")

        for img in images:
            pending_images.append({
                "doc_id": doc_id,
                "title": title,
                "topic": topic,
                "page_number": img["page_number"],
                "section_label": img["section_label"],
                "image_path": str(img["image_path"]),
            })

        files_manifest[file_id] = {"modified_time": modified_time, "topic": topic, "title": title}

    removed = 0
    for file_id in removed_file_ids:
        row = conn.execute("SELECT doc_id FROM documents WHERE file_id=?", (file_id,)).fetchone()
        if row:
            conn.execute("DELETE FROM documents WHERE doc_id=?", (row[0],))
            removed += 1
        files_manifest.pop(file_id, None)

    conn.commit()
    conn.close()

    manifest["files"] = files_manifest
    pending_path = None
    if pending_images:
        pending_path = DB_PATH.parent / "pending_captions.json"
        pending_path.write_text(json.dumps(pending_images, indent=2))
    else:
        manifest["last_full_index_ts"] = now_iso()
        if temp_root is not None:
            shutil.rmtree(temp_root, ignore_errors=True)
            temp_root = None
    save_manifest(manifest)

    return {
        "added": added,
        "updated": updated,
        "removed": removed,
        "pending_images": len(pending_images),
        "pending_captions_file": str(pending_path) if pending_path else None,
        "image_temp_dir": str(temp_root) if temp_root else None,
    }


def ingest_captions(captions_path: Path) -> dict:
    conn = db_module.connect(DB_PATH)
    items = json.loads(captions_path.read_text())

    by_doc: dict[int, list[dict]] = {}
    image_temp_dirs = set()
    for item in items:
        by_doc.setdefault(item["doc_id"], []).append(item)
        image_temp_dirs.add(Path(item["image_path"]).parent.parent)

    count = 0
    for doc_id, doc_items in by_doc.items():
        chunk_dicts = [
            {
                "page_number": item["page_number"],
                "section_label": item["section_label"],
                "seq_in_page": 1000 + i,  # ordered after this document's text chunks
                "text": item["caption"],
                "image_ref": item["image_path"],
            }
            for i, item in enumerate(doc_items)
        ]
        insert_chunks(conn, doc_id, chunk_dicts, "image_caption")
        count += len(chunk_dicts)

    conn.commit()
    conn.close()

    manifest = load_manifest()
    manifest["last_full_index_ts"] = now_iso()
    save_manifest(manifest)

    captions_path.unlink(missing_ok=True)
    for d in image_temp_dirs:
        shutil.rmtree(d, ignore_errors=True)

    return {"status": "captions_ingested", "count": count}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ingest-captions", help="Path to a JSON file of {doc_id, ..., caption} entries")
    args = ap.parse_args()

    if args.ingest_captions:
        print(json.dumps(ingest_captions(Path(args.ingest_captions))))
        return

    payload = json.loads(sys.stdin.read())
    print(json.dumps(process_batch(payload.get("items", []), payload.get("removed_file_ids", []))))


if __name__ == "__main__":
    main()
