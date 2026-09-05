"""Builds/repairs the skill's own .venv and pre-downloads the embedding model.
Run with the system python3 (the venv doesn't exist yet) -- never imports
project dependencies itself, only stdlib + subprocess."""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
VENV_DIR = SKILL_DIR / ".venv"
PYPROJECT = SKILL_DIR / "pyproject.toml"
CANDIDATE_PYTHONS = ["python3.14", "python3.13", "python3.12", "python3"]


def find_python() -> str:
    for name in CANDIDATE_PYTHONS:
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit("No suitable Python 3.12+ interpreter found on PATH.")


def load_dependencies() -> list[str]:
    data = tomllib.loads(PYPROJECT.read_text())
    return data["project"]["dependencies"]


def main():
    force = "--force" in sys.argv

    if VENV_DIR.exists() and (VENV_DIR / "READY").exists() and not force:
        print(json.dumps({"status": "already_installed", "venv": str(VENV_DIR)}))
        return

    if force and VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)

    interpreter = find_python()
    print(f"Creating virtual environment with {interpreter}...", file=sys.stderr)
    subprocess.run([interpreter, "-m", "venv", str(VENV_DIR)], check=True)

    pip = str(VENV_DIR / "bin" / "pip")
    subprocess.run([pip, "install", "--upgrade", "-q", "pip"], check=True)

    print("Installing dependencies (fastembed, pypdf, python-docx, python-pptx, openpyxl, striprtf)...", file=sys.stderr)
    subprocess.run([pip, "install", "-q", *load_dependencies()], check=True)

    print("Downloading embedding model (~130MB, one-time)...", file=sys.stderr)
    venv_python = str(VENV_DIR / "bin" / "python")
    subprocess.run(
        [venv_python, "-c", "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"],
        check=True,
    )

    (VENV_DIR / "PYTHON_USED.txt").write_text(interpreter)
    (VENV_DIR / "READY").write_text("ok")
    print(json.dumps({"status": "installed", "venv": str(VENV_DIR), "python": interpreter}))


if __name__ == "__main__":
    main()
