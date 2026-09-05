"""Embed a question and return the best-matching chunks across ALL topics,
filtered by a similarity threshold. An empty result is the structural signal
for "I don't know" -- callers must not fall back to general knowledge."""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as db_module  # noqa: E402
from config import load_config  # noqa: E402
from embedding import embed_query  # noqa: E402
from paths import DB_PATH  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=8)
    ap.add_argument("--threshold", type=float, default=None)
    args = ap.parse_args()

    config = load_config()
    threshold = args.threshold if args.threshold is not None else config["similarity_threshold"]

    conn = db_module.connect(DB_PATH)
    rows = conn.execute(
        """
        SELECT c.text, c.page_number, c.section_label, c.chunk_type,
               d.title, d.topic, e.vector
        FROM chunks c
        JOIN documents d ON d.doc_id = c.doc_id
        JOIN embeddings e ON e.chunk_id = c.chunk_id
        """
    ).fetchall()
    conn.close()

    if not rows:
        print(json.dumps([]))
        return

    qvec = embed_query(args.query)
    qvec = qvec / (np.linalg.norm(qvec) + 1e-9)

    matrix = np.stack([np.frombuffer(r[6], dtype=np.float32) for r in rows])
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1e-9
    matrix = matrix / norms

    scores = matrix @ qvec

    results = [
        {
            "score": float(score),
            "document": row[4],
            "topic": row[5],
            "page_number": row[1],
            "section_label": row[2],
            "chunk_type": row[3],
            "text": row[0],
        }
        for row, score in zip(rows, scores)
        if score >= threshold
    ]
    results.sort(key=lambda r: r["score"], reverse=True)
    print(json.dumps(results[: args.top_k]))


if __name__ == "__main__":
    main()
