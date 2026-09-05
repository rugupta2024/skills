---
name: dhi
description: Personal document Q&A over a local folder (or a folder inside the user's Google-Drive-desktop-mounted directory) organized into topic subfolders. Semantically indexes PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, and RTF files -- including describing/transcribing embedded images via vision -- into a local SQLite index, and answers questions strictly from that indexed content, always citing document + page/section + topic, saying "I don't know" when the documents don't cover it. Trigger on "/dhi install", "/dhi index", "/dhi ask", "/dhi status", "/dhi config", or natural-language requests to set up, index, or query a personal document library.
argument-hint: install | index [--full] | ask "<question>" | status | config [key] [value]
allowed-tools: Bash, Read, Glob
---

# dhi -- personal document Q&A

`dhi` is a single-user tool: you organize documents into topic subfolders
under one root folder, `dhi` indexes them locally (no cloud embedding
service, no paid API), and answers questions using **only** what's in those
documents. It never falls back to general knowledge -- if the retrieval step
finds nothing relevant, say so plainly rather than guessing.

This skill can be installed three ways, so resolve its own directory
dynamically rather than assuming one fixed path -- run this first, in every
subcommand, before anything else:

```
if [ -n "$CLAUDE_PLUGIN_ROOT" ]; then
  SKILL_DIR="$CLAUDE_PLUGIN_ROOT/skills/dhi"        # installed as a plugin
elif [ -d "./.claude/skills/dhi" ]; then
  SKILL_DIR="$(pwd)/.claude/skills/dhi"             # project-level dev copy
else
  SKILL_DIR="$HOME/.claude/skills/dhi"              # plain user-level skill
fi
PY="$SKILL_DIR/.venv/bin/python"
```

All Bash commands below use `$SKILL_DIR` and `$PY` from this resolution --
always call the venv's Python explicitly, never a bare `python`/`python3`.

## Before any subcommand except `install` or `config`: staleness check

Run:
```
"$PY" "$SKILL_DIR/scripts/check_staleness.py"
```
This is deliberately cheap (file stat comparisons only, no hashing, no
embedding) so it doesn't slow down every question. It returns JSON like:
```
{"stale_by_time": true, "days_since_index": 9.2, "stale_by_changes": true, "changed_file_count": 3}
```
If `stale_by_time` or `stale_by_changes` is true, tell the user plainly, e.g.
"3 files changed since the last index (9 days ago) -- update now?" and wait
for yes/no before continuing to the subcommand they actually asked for:
- **Yes** -> run the `/dhi index` flow below first, then proceed.
- **No** -> proceed with the existing index as-is (note in your `ask` answer
  that results may be slightly out of date).

If `$SKILL_DIR/.venv` doesn't exist yet, or `check_staleness.py` errors
because no root is configured, tell the user to run `/dhi install` first --
don't try to work around it.

## `/dhi install`

1. Ask the user for the root folder to use -- a plain local path, or a path
   inside their Google-Drive-desktop-mounted folder (e.g. under
   `~/Library/CloudStorage/GoogleDrive-.../My Drive/...`). Both are treated
   identically; this tool only ever does plain filesystem I/O, never the
   Drive API/connector, so there is nothing special to configure either way.
2. Run:
   ```
   python3 "$SKILL_DIR/scripts/init_root.py" --root "<chosen path>"
   ```
   This creates the folder if needed, sets up `<root>/.dhi/` (config,
   manifest, empty SQLite index), and records this as the active root.
3. Run:
   ```
   python3 "$SKILL_DIR/scripts/setup_venv.py"
   ```
   First run takes ~1-2 minutes (creates `.venv`, installs dependencies,
   downloads the ~130MB local embedding model once) -- tell the user this
   upfront so it doesn't look hung. Subsequent installs are near-instant
   (idempotent) unless `--force` is passed to rebuild from scratch.
4. Tell the user their topic subfolders are just directories under the root
   (e.g. `Finance/`, `Health/`) -- anything dropped directly in the root
   itself gets grouped under "Uncategorized". Ask if they'd like to run an
   initial `/dhi index` now.

## `/dhi index`

Two passes, because embedded-image captioning needs Claude's vision, which a
plain script can't do:

**Pass 1 -- deterministic extraction/embedding (script):**
```
"$PY" "$SKILL_DIR/scripts/embed_index.py" [--full]
```
(`--full` forces a complete rebuild; omit it for the normal incremental diff
against the manifest.) This adds/updates/removes documents and their text
chunks, and returns JSON like:
```
{"added": 2, "updated": 1, "removed": 0, "pending_images": 4, "pending_captions_file": "/path/to/pending_captions.json"}
```

**Pass 2 -- vision captioning (Claude), only if `pending_images > 0`:**
1. Read the file at `pending_captions_file` (a JSON list of
   `{doc_id, rel_path, topic, page_number, section_label, image_path}`).
2. For each entry, follow `references/image_captioning_prompt.md` exactly to
   produce one combined description+transcription string.
3. Write a JSON file with each entry plus a `"caption"` field added, then run:
   ```
   "$PY" "$SKILL_DIR/scripts/embed_index.py" --ingest-captions "<path to that file>"
   ```
   This embeds and stores the captions and marks the index fresh.

Report a short summary to the user: documents added/updated/removed, images
captioned, and roughly how long it took.

## `/dhi ask "<question>"`

1. Run:
   ```
   "$PY" "$SKILL_DIR/scripts/search.py" --query "<question>"
   ```
   This searches across **all topics** unconditionally -- there is no
   topic-filter option, by design, so a wrong topic guess can never hide the
   real answer. It returns a JSON list of matching chunks (each with `text`,
   `doc_rel_path`, `topic`, `page_number`/`section_label`, `chunk_type`,
   `score`), already filtered by the configured similarity threshold.
2. **If the list is empty**, respond with exactly this and stop -- do not
   answer from general knowledge:
   > I don't know -- this isn't covered in your indexed documents.
3. **The similarity threshold is a cheap pre-filter, not proof of relevance**
   -- with a small library or an unusual question, a chunk can clear the
   threshold while still being unrelated to what was actually asked (e.g. a
   revenue-chart caption scoring above threshold for a vitamin D question,
   just because both are short factual snippets). Before answering, read the
   returned chunks yourself and judge whether any of them actually address
   the question. If none genuinely do, treat it the same as an empty list --
   respond with the "I don't know" line above, don't stretch an unrelated
   chunk into an answer just because it was retrieved.
4. **If the list is non-empty and genuinely relevant**, answer using *only*
   the text in those chunks. Every claim must cite its source inline, e.g.:
   `(Document: taxes-2025.pdf, Page: 3, Topic: Finance)` -- use `Section:`
   instead of `Page:` for chunks where `page_number` is null (DOCX/TXT/MD/
   CSV/RTF use section labels; XLSX uses sheet names as the section). If a
   chunk's `chunk_type` is `image_caption`, make clear the information came
   from an image, e.g. "(from an image on Page 4 of ...)".
5. If retrieved chunks only partially cover the question, answer the covered
   part and explicitly say which part isn't covered by the documents --
   never fill the gap with outside knowledge.

## `/dhi status`

Report: active root path, config values (`frequency_days`,
`similarity_threshold`), and the result of running `check_staleness.py`.
For document/topic/chunk counts, run a quick read-only query, e.g.:
```
"$PY" -c "
import sys; sys.path.insert(0, '$SKILL_DIR/scripts')
from manifest import resolve_root
import db
conn = db.connect(resolve_root(None) / '.dhi' / 'index.sqlite3')
print(conn.execute('SELECT topic, COUNT(*) FROM documents GROUP BY topic').fetchall())
print(conn.execute('SELECT COUNT(*) FROM chunks').fetchone())
"
```
Present this as a readable summary, not raw output.

## `/dhi config [key] [value]`

```
"$PY" "$SKILL_DIR/scripts/config.py" [key] [value]
```
- No args -> prints current config.
- `key` only -> prints that value.
- `key value` -> updates it (allowed keys: `frequency_days` (int, days
  between scheduled checks), `similarity_threshold` (float 0-1, how closely a
  chunk must match a question to be used -- lower finds more but risks noise,
  higher is stricter and more likely to say "I don't know")).

## Error handling

- Root folder missing/unmounted (e.g. Drive not currently mounted): surface
  the actual error, don't crash or silently reindex from empty -- tell the
  user to check the path or remount Drive.
- `.venv` missing: tell the user to run `/dhi install`.
- Never invoke a bare `python`/`python3` for anything except `init_root.py`
  and `setup_venv.py` themselves (which must run before the venv exists) --
  every other script call must go through `$PY`.
