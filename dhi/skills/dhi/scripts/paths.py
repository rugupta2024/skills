"""Fixed local locations for dhi's own state. Single-user, single-root tool --
everything dhi keeps on disk lives here, and nothing else. Source documents
live on Google Drive and are never written to disk except a transient temp
directory used during embedded-image captioning, deleted immediately after."""

from pathlib import Path

DHI_HOME = Path.home() / ".dhi"
CONFIG_PATH = DHI_HOME / "config.json"
MANIFEST_PATH = DHI_HOME / "manifest.json"
DB_PATH = DHI_HOME / "index.sqlite3"
