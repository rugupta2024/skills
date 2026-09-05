"""Get/set dhi's config (~/.dhi/config.json). Run directly for /dhi config.

Holds both user-tunable keys (frequency_days, similarity_threshold) and
install-time keys set by init_root.py (drive_root_id, drive_root_name) --
the latter aren't in ALLOWED_KEYS since they're not meant to be hand-edited
via /dhi config.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paths import CONFIG_PATH, DHI_HOME  # noqa: E402

DEFAULTS = {"frequency_days": 7, "similarity_threshold": 0.5}
ALLOWED_KEYS = {"frequency_days": int, "similarity_threshold": float}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise SystemExit("dhi is not installed yet. Run /dhi install first.")
    merged = dict(DEFAULTS)
    merged.update(json.loads(CONFIG_PATH.read_text()))
    return merged


def save_config(config: dict) -> None:
    DHI_HOME.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2))
    tmp.replace(CONFIG_PATH)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key", nargs="?")
    ap.add_argument("value", nargs="?")
    args = ap.parse_args()
    config = load_config()

    if args.key is None:
        print(json.dumps(config, indent=2))
        return

    if args.key not in ALLOWED_KEYS:
        print(json.dumps({"error": f"unknown key '{args.key}', allowed: {sorted(ALLOWED_KEYS)}"}))
        sys.exit(1)

    if args.value is None:
        print(json.dumps({args.key: config.get(args.key)}))
        return

    caster = ALLOWED_KEYS[args.key]
    try:
        config[args.key] = caster(args.value)
    except ValueError:
        print(json.dumps({"error": f"invalid value for {args.key}, expected {caster.__name__}"}))
        sys.exit(1)

    save_config(config)
    print(json.dumps({args.key: config[args.key], "status": "updated"}))


if __name__ == "__main__":
    main()
