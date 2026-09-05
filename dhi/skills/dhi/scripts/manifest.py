"""Shared helpers: which files count as documents, and the fast on-disk
manifest snapshot used for cheap staleness checks (path -> size/mtime)."""

import json
from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".xlsx", ".txt", ".md", ".csv", ".rtf"}

MANIFEST_NAME = "manifest.json"


def resolve_root(root_arg: str | None) -> Path:
    """--root wins if given; otherwise fall back to the last root /dhi install recorded."""
    if root_arg:
        return Path(root_arg).expanduser().resolve()
    pointer = Path(__file__).resolve().parent / "active_root.txt"
    if pointer.exists():
        return Path(pointer.read_text().strip())
    raise SystemExit("No root configured yet. Run /dhi install first.")


def set_active_root(root: Path) -> None:
    pointer = Path(__file__).resolve().parent / "active_root.txt"
    pointer.write_text(str(root))


def manifest_path(root: Path) -> Path:
    return root / ".dhi" / MANIFEST_NAME


def load_manifest(root: Path) -> dict:
    p = manifest_path(root)
    if not p.exists():
        return {"files": {}, "last_full_index_ts": None}
    return json.loads(p.read_text())


def save_manifest(root: Path, manifest: dict) -> None:
    p = manifest_path(root)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    tmp.replace(p)


def iter_documents(root: Path):
    """Yield (topic, rel_path, abs_path) for every supported document under root.

    Immediate subfolders of root are topics. Loose files directly under root
    (not in any topic folder) are grouped under "Uncategorized" rather than
    ignored, since a user may drop a file in before sorting it.
    """
    for entry in sorted(root.iterdir()):
        if entry.name.startswith(".") or entry.name == ".dhi":
            continue
        if entry.is_dir():
            topic = entry.name
            for path in sorted(entry.rglob("*")):
                if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in SUPPORTED_EXTENSIONS:
                    yield topic, str(path.relative_to(root)), path
        elif entry.is_file() and entry.suffix.lower() in SUPPORTED_EXTENSIONS:
            yield "Uncategorized", entry.name, entry
