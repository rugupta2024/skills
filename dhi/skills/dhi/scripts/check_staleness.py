"""Cheap, local-only staleness gate run before /dhi ask and /dhi status: just
a time-since-last-index comparison against the manifest, no Drive calls.

Change-detection (has anything actually changed on Drive since last index)
now requires a live Drive listing, which only Claude's own connector calls
can do -- a plain script has no way to authenticate to Drive. That
enumeration happens as part of /dhi index itself, not as a pre-check before
every command, to avoid an expensive Drive round-trip before every question.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import load_config  # noqa: E402
from manifest import load_manifest  # noqa: E402


def main():
    config = load_config()
    frequency_days = config["frequency_days"]

    manifest = load_manifest()
    last_full_index_ts = manifest.get("last_full_index_ts")

    days_since = None
    stale_by_time = True
    if last_full_index_ts:
        last_dt = datetime.fromisoformat(last_full_index_ts)
        days_since = (datetime.now(timezone.utc) - last_dt).total_seconds() / 86400
        stale_by_time = days_since >= frequency_days

    print(json.dumps({
        "stale_by_time": stale_by_time,
        "days_since_index": round(days_since, 1) if days_since is not None else None,
    }))


if __name__ == "__main__":
    main()
