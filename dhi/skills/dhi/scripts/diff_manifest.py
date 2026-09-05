"""Diff a live Drive file listing (enumerated by Claude via the Drive
connector, passed in as JSON on stdin) against the local manifest. Pure
comparison -- no Drive access, no file content read -- so this is cheap even
for a large listing. Used by /dhi index to decide what actually needs
downloading.

Stdin shape: a JSON list of {"file_id", "title", "topic", "ext",
"modified_time"} for every supported file currently found under the Drive
root. Pass --full to force every file into to_process regardless of whether
its modified_time changed."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest import SUPPORTED_EXTENSIONS, load_manifest  # noqa: E402


def main():
    full = "--full" in sys.argv
    listing = json.loads(sys.stdin.read())
    listing = [f for f in listing if f.get("ext", "").lower().lstrip(".") in SUPPORTED_EXTENSIONS]

    manifest = load_manifest()
    files_manifest = manifest.get("files", {})

    current_ids = {f["file_id"] for f in listing}
    to_process = []
    for f in listing:
        prev = files_manifest.get(f["file_id"])
        if full or prev is None or prev.get("modified_time") != f["modified_time"]:
            to_process.append(f)

    removed_file_ids = [fid for fid in files_manifest if fid not in current_ids]

    print(json.dumps({
        "to_process": to_process,
        "removed_file_ids": removed_file_ids,
        "unchanged": len(listing) - len(to_process),
    }))


if __name__ == "__main__":
    main()
