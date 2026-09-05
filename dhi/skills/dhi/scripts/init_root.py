"""/dhi install: point dhi at a root folder (plain local, or a path inside a
Google-Drive-desktop-mounted folder -- both are just filesystem paths here)."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as db_module  # noqa: E402
from config import DEFAULTS, save_config  # noqa: E402
from manifest import save_manifest, set_active_root  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()

    root.mkdir(parents=True, exist_ok=True)
    dhi_dir = root / ".dhi"
    dhi_dir.mkdir(exist_ok=True)
    (dhi_dir / "images").mkdir(exist_ok=True)

    config = dict(DEFAULTS)
    config["root"] = str(root)
    save_config(root, config)
    save_manifest(root, {"files": {}, "last_full_index_ts": None})
    db_module.init_db(dhi_dir / "index.sqlite3")
    set_active_root(root)

    print(json.dumps({"status": "initialized", "root": str(root)}))


if __name__ == "__main__":
    main()
