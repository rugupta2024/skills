"""Cheap gate run before every /dhi command except install/config: pure
os.stat comparisons against the manifest, no file content read, no hashing,
no embedding -- so this stays fast even with a few thousand files."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402
from manifest import iter_documents, load_manifest, resolve_root  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    args = ap.parse_args()
    root = resolve_root(args.root)

    config = load_config(root)
    frequency_days = config["frequency_days"]

    manifest = load_manifest(root)
    files_manifest = manifest.get("files", {})
    last_full_index_ts = manifest.get("last_full_index_ts")

    days_since = None
    stale_by_time = True
    if last_full_index_ts:
        last_dt = datetime.fromisoformat(last_full_index_ts)
        days_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400
        stale_by_time = days_since >= frequency_days

    seen = set()
    changed_count = 0
    for _topic, rel_path, abs_path in iter_documents(root):
        seen.add(rel_path)
        st = abs_path.stat()
        prev = files_manifest.get(rel_path)
        if prev is None or prev["size"] != st.st_size or prev["mtime"] != st.st_mtime:
            changed_count += 1

    changed_count += sum(1 for rel_path in files_manifest if rel_path not in seen)

    print(json.dumps({
        "stale_by_time": stale_by_time,
        "days_since_index": round(days_since, 1) if days_since is not None else None,
        "stale_by_changes": changed_count > 0,
        "changed_file_count": changed_count,
    }))


if __name__ == "__main__":
    main()
