"""Get/set <root>/.dhi/config.json values. Run directly for the /dhi config subcommand."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest import resolve_root  # noqa: E402

DEFAULTS = {"frequency_days": 7, "similarity_threshold": 0.5}
ALLOWED_KEYS = {"frequency_days": int, "similarity_threshold": float}


def config_path(root: Path) -> Path:
    return root / ".dhi" / "config.json"


def load_config(root: Path) -> dict:
    p = config_path(root)
    if not p.exists():
        return dict(DEFAULTS)
    merged = dict(DEFAULTS)
    merged.update(json.loads(p.read_text()))
    return merged


def save_config(root: Path, config: dict) -> None:
    p = config_path(root)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(config, indent=2))
    tmp.replace(p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root")
    ap.add_argument("key", nargs="?")
    ap.add_argument("value", nargs="?")
    args = ap.parse_args()
    root = resolve_root(args.root)
    config = load_config(root)

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

    save_config(root, config)
    print(json.dumps({args.key: config[args.key], "status": "updated"}))


if __name__ == "__main__":
    main()
