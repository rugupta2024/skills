---
name: dhi
description: Personal document Q&A over a Google Drive folder (accessed live via the Drive connector, never synced to local disk) organized into topic subfolders. Semantically indexes PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, and RTF files -- including describing/transcribing embedded images via vision -- into a local SQLite index, and answers questions strictly from that indexed content, always citing document + page/section + topic, saying "I don't know" when the documents don't cover it. Trigger on "/dhi install", "/dhi index", "/dhi ask", "/dhi status", "/dhi config", or natural-language requests to set up, index, or query a personal document library.
argument-hint: install | index [--full] | ask "<question>" | status | config [key] [value]
allowed-tools: Bash, Read, Glob, mcp__claude_ai_Google_Drive__search_files, mcp__claude_ai_Google_Drive__get_file_metadata, mcp__claude_ai_Google_Drive__download_file_content, mcp__claude_ai_Google_Drive__list_recent_files
---

# dhi -- personal document Q&A

`dhi` is a single-user tool: you point it at one Google Drive folder,
organized into topic subfolders, and it answers questions using **only**
what's in those documents. It never falls back to general knowledge -- if
the retrieval step finds nothing relevant, say so plainly rather than
guessing.

**Documents are never copied to local disk.** Drive access only happens
through your own Drive-connector tool calls (`mcp__claude_ai_Google_Drive__*`)
-- the Python scripts have no network access and never talk to Drive
themselves. At index time you download each file's content via the
connector and hand it to a script over stdin, which processes it **entirely
in memory** (extraction, chunking, embedding) and never writes the source
document to disk. The one narrow exception: an embedded image is written to
a transient temp file just long enough for you to view and caption it, then
deleted immediately after. The only things `dhi` keeps on disk, ever, are
under `~/.dhi/`: the derived SQLite index (chunks + embeddings), a manifest
of `{file_id: modified_time}`, and config -- never the documents themselves.

**Cost trade-off, worth knowing:** because indexing routes document content
through your own context (there's no way for a background script to
authenticate to Drive on its own), indexing runs cost real tokens/time
roughly proportional to total document size. This is the deliberate price
of never storing the user's documents locally. For a personal library
(dozens to low hundreds of documents) this is fine; don't index reflexively
-- only when the user asks or confirms it's worth it.

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

If the `mcp__claude_ai_Google_Drive__*` tools aren't available in this
session, stop and tell the user to connect their Google Drive account
first -- nothing here works without it.

## Before `/dhi ask` or `/dhi status`: staleness check

Run:
```
"$PY" "$SKILL_DIR/scripts/check_staleness.py"
```
This is a cheap, purely local time check (no Drive calls) -- it returns JSON
like `{"stale_by_time": true, "days_since_index": 9.2}`. It can no longer
tell you whether files actually changed on Drive (that requires a live
listing, which only happens during `/dhi index` itself). If `stale_by_time`
is true, mention it plainly, e.g. "the index is 9 days old -- want me to
refresh it first?" and wait for yes/no:
- **Yes** -> run the `/dhi index` flow below first, then proceed.
- **No** -> proceed with the existing index as-is, noting in your `ask`
  answer that results may be out of date.

If `$SKILL_DIR/.venv` doesn't exist yet, or `check_staleness.py` errors
because dhi isn't installed, tell the user to run `/dhi install` first --
don't try to work around it.

## `/dhi install`

1. Confirm the Drive connector tools are available (see above). If not,
   stop here.
2. Ask the user which Google Drive folder to use as the root. They can:
   - Paste a Drive folder link, e.g.
     `https://drive.google.com/drive/u/0/folders/<ID>` -- extract `<ID>`
     directly from the URL.
   - Describe it by name -- use `search_files` with
     `title contains '<name>' and mimeType = 'application/vnd.google-apps.folder'`
     to find it, and confirm the match with the user if more than one
     result comes back.
3. Call `get_file_metadata` on the resolved folder ID to confirm it's a
   folder and get its display name.
4. Run:
   ```
   "$PY" "$SKILL_DIR/scripts/init_root.py" --root-id "<id>" --root-name "<name>"
   ```
   This sets up `~/.dhi/` (config, empty manifest, empty SQLite index) and
   records the Drive folder as the active root. It never touches Drive.
5. Run:
   ```
   python3 "$SKILL_DIR/scripts/setup_venv.py"
   ```
   First run takes ~1-2 minutes (creates `.venv`, installs dependencies,
   downloads the ~130MB local embedding model once) -- tell the user this
   upfront so it doesn't look hung. Subsequent installs are near-instant
   (idempotent) unless `--force` is passed to rebuild from scratch.
6. Explain: each immediate subfolder of the root folder in Drive is a topic
   (any nesting inside a topic folder still counts as that same topic);
   files placed directly in the root itself are grouped under
   "Uncategorized". Only PDF, DOCX, PPTX, XLSX, TXT, MD, CSV, and RTF files
   are indexed in this version -- native Google Docs/Sheets/Slides aren't
   supported yet. Ask if they'd like to run an initial `/dhi index` now.

## `/dhi index`

Four stages. Drive access only happens in Stages 1 and 3 (you, via the
connector) -- the scripts (Stages 2 and part of 3/4) never touch Drive.

**Stage 1 -- enumerate the Drive folder (you):**
1. Get the active root: `"$PY" "$SKILL_DIR/scripts/config.py"` and read
   `drive_root_id`.
2. List immediate children: `search_files` with
   `parentId = '<drive_root_id>'`. Subfolders become topics (their
   `title`); files found directly in the root become topic "Uncategorized".
3. For each topic subfolder, recursively list every descendant file
   (repeat `search_files` with `parentId = '<subfolder_id>'` for any nested
   subfolders you find), tagging every file anywhere under that branch with
   the top-level topic name.
4. Keep only files whose extension is one of: pdf, docx, pptx, xlsx, txt,
   md, csv, rtf. Note how many files were skipped (native Google
   Docs/Sheets/Slides or anything else unsupported) for the final summary.
5. Build a JSON list of `{"file_id", "title", "topic", "ext",
   "modified_time"}` (Drive's `modifiedTime` field) for every kept file.

**Stage 2 -- diff against the local manifest (script, no Drive access):**
```
echo '<JSON list from Stage 1>' | "$PY" "$SKILL_DIR/scripts/diff_manifest.py" [--full]
```
Returns `{"to_process": [...], "removed_file_ids": [...], "unchanged": N}`.
Only `to_process` entries need downloading -- this is what keeps re-indexing
incremental. (`--full` forces every file into `to_process`, ignoring
`modified_time`.)

Note: moving a file between topic folders in Drive without editing its
content does not change `modified_time`, so a pure reorganization won't be
picked up incrementally -- rerun with `--full` after reorganizing topics.

**Stage 3 -- download + process each file needing (re)indexing (you + script):**
If `to_process` is empty, skip to the summary. Otherwise, batch a handful of
files at a time (e.g. 5-10) to limit how many `Bash` calls this takes:
1. For each file in the batch, call `download_file_content` with its
   `fileId` to get its content as base64.
2. Assemble one JSON payload per batch:
   ```json
   {"items": [{"file_id":"...", "title":"...", "topic":"...", "ext":"...",
                "modified_time":"...", "content_b64":"..."}, ...],
    "removed_file_ids": ["..."]}
   ```
   Include `removed_file_ids` (from Stage 2) in only one batch call so
   deletions happen exactly once.
3. Pipe it in:
   ```
   echo '<payload JSON>' | "$PY" "$SKILL_DIR/scripts/index_batch.py"
   ```
   This decodes each file **in memory**, extracts text, chunks, embeds, and
   stores it -- the source file is never written to disk. Embedded images
   are the one exception: each is written into a transient temp directory
   (`image_temp_dir` in the response), purely so you can view it in Stage 4;
   that directory must be deleted once Stage 4 finishes (the script does
   this automatically when you call `--ingest-captions`).
   Returns `{"added", "updated", "removed", "pending_images",
   "pending_captions_file", "image_temp_dir"}` per batch -- accumulate these
   across batches for the final summary.

**Stage 4 -- vision captioning (you), only where `pending_images > 0`:**
1. Read the file at `pending_captions_file` (a JSON list of `{doc_id,
   title, topic, page_number, section_label, image_path}` -- `image_path`
   points into the transient temp directory from Stage 3).
2. For each entry, Read the image at `image_path` and follow
   `references/image_captioning_prompt.md` exactly to produce one combined
   description+transcription string.
3. Write a JSON file with each entry plus a `"caption"` field added, then
   run:
   ```
   "$PY" "$SKILL_DIR/scripts/index_batch.py" --ingest-captions "<path to that file>"
   ```
   This embeds and stores the captions, marks the index fresh, deletes the
   captions file, and deletes the transient image temp directory -- nothing
   from this indexing run is left on disk afterward.

Report a short summary: documents added/updated/removed, files skipped
(unsupported type), images captioned, and how many were already up to date.

## `/dhi ask "<question>"`

1. Run:
   ```
   "$PY" "$SKILL_DIR/scripts/search.py" --query "<question>"
   ```
   This searches across **all topics** unconditionally -- there is no
   topic-filter option, by design, so a wrong topic guess can never hide the
   real answer. It returns a JSON list of matching chunks (each with `text`,
   `document`, `topic`, `page_number`/`section_label`, `chunk_type`,
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
   `(Document: Access Control Policy.txt, Page: 3, Topic: Policy Management)`
   -- use `Section:` instead of `Page:` for chunks where `page_number` is
   null (DOCX/TXT/MD/CSV/RTF use section labels; XLSX uses sheet names as
   the section). If a chunk's `chunk_type` is `image_caption`, make clear
   the information came from an image, e.g. "(from an image on Page 4 of
   ...)".
5. If retrieved chunks only partially cover the question, answer the covered
   part and explicitly say which part isn't covered by the documents --
   never fill the gap with outside knowledge.

## `/dhi status`

Report: the active Drive root (`drive_root_name` / `drive_root_id` from
config), config values (`frequency_days`, `similarity_threshold`), and the
result of `check_staleness.py`. Note explicitly that the staleness check is
time-based only -- it can't see whether files actually changed on Drive
without running `/dhi index`. For document/topic/chunk counts, run a quick
read-only query, e.g.:
```
"$PY" -c "
import sys; sys.path.insert(0, '$SKILL_DIR/scripts')
from paths import DB_PATH
import db
conn = db.connect(DB_PATH)
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
  between staleness reminders), `similarity_threshold` (float 0-1, how
  closely a chunk must match a question to be used -- lower finds more but
  risks noise, higher is stricter and more likely to say "I don't know")).

## Error handling

- Drive connector unavailable, or the root folder can't be found/accessed:
  surface the actual error -- don't crash or silently reindex from empty.
- `.venv` missing: tell the user to run `/dhi install`.
- If `/dhi index` is interrupted after Stage 3 but before Stage 4 finishes,
  a temp image directory may be left behind -- clean it up with
  `rm -rf "<image_temp_dir>"` using the path from the last Stage 3 response.
- Never invoke a bare `python`/`python3` for anything except `init_root.py`
  and `setup_venv.py` themselves (which must run before the venv exists) --
  every other script call must go through `$PY`.
