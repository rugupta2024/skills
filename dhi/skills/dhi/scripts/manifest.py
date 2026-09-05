"""Local record of what's currently indexed from Drive: file_id -> modified
time/topic/title, used to diff against a live Drive listing. This module
never talks to Drive itself -- enumeration only happens via Claude's own
Drive-connector tool calls (a plain script has no way to authenticate to
Drive), so this just tracks state and computes diffs against what Claude
found."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import MANIFEST_PATH  # noqa: E402

SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "xlsx", "txt", "md", "csv", "rtf"}


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"files": {}, "last_full_index_ts": None}
    return json.loads(MANIFEST_PATH.read_text())


def save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = MANIFEST_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.replace(MANIFEST_PATH)
