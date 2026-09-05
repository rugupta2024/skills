"""/dhi install: record the chosen Google Drive folder as dhi's root and set
up its local state directory (~/.dhi/: config, empty manifest, empty SQLite
index). This script never talks to Drive -- Claude resolves the folder's id
and display name via the Drive connector before calling this."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db as db_module  # noqa: E402
from config import DEFAULTS, save_config  # noqa: E402
from manifest import save_manifest  # noqa: E402
from paths import DB_PATH, DHI_HOME  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root-id", required=True, help="Google Drive folder ID to use as the root")
    ap.add_argument("--root-name", required=True, help="Display name of that folder, for status/messages")
    args = ap.parse_args()

    DHI_HOME.mkdir(parents=True, exist_ok=True)

    config = dict(DEFAULTS)
    config["drive_root_id"] = args.root_id
    config["drive_root_name"] = args.root_name
    save_config(config)
    save_manifest({"files": {}, "last_full_index_ts": None})
    db_module.init_db(DB_PATH)

    print(json.dumps({"status": "initialized", "drive_root_id": args.root_id, "drive_root_name": args.root_name}))


if __name__ == "__main__":
    main()
