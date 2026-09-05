# dhi -- ask questions about your own documents

`dhi` lets you keep a folder of your documents (PDFs, Word docs, slides,
spreadsheets, notes) in Google Drive, organized into topics, and then just
ask questions about them in plain English. It only answers from what's
actually in your documents -- if the answer isn't there, it tells you so
instead of guessing.

**Your documents never leave Google Drive.** `dhi` reads them live from
Drive each time it indexes and never saves a copy on your computer -- the
only thing that ends up on your machine is a small search index (which
document/page mentions what), not the documents themselves.

This guide assumes you know nothing technical. Every step below is something
you type into a chat window, not a programming task.

## Before you start

You need three things already set up:

1. **Claude Code** -- the app/tool you're reading this inside of, or will
   install to use `dhi`. If you don't have it yet, ask whoever gave you this
   guide, or search "install Claude Code" to get it running first.
2. **Google Drive connected to Claude** -- `dhi` reads your documents through
   Claude's Google Drive connection, so this needs to be turned on once. If
   you're not sure whether it is, just ask Claude: "Is my Google Drive
   connected?" and follow what it tells you.
3. **Python**, version 3.12 or newer -- this is free software `dhi` needs to
   run on your machine. You don't need to know what it is. Just open Claude
   Code and paste this:
   > Do I have Python 3.12 or newer installed? If not, please install it for me.

   Claude Code will check and install it for you if it's missing.

Once all three are in place, pick **one** of the two install methods below.

## Method A -- if you're comfortable pasting two commands

Open Claude Code and paste these one at a time:
```
/plugin marketplace add rugupta2024/skills
/plugin install dhi@skills
```
Then type:
```
/dhi install
```
Claude Code will ask which Google Drive folder holds your documents (you
can paste a Drive folder link, or just describe it by name) and take it
from there. The first-time setup takes a minute or two.

## Method B -- no commands, just plain sentences

If someone sent you a `dhi` folder (as a zip file) directly instead of
pointing you to GitHub:

1. Double-click the zip file to unzip it (this creates a normal folder
   named `dhi`, wherever you saved the zip -- usually your Downloads folder).
2. Open Claude Code and paste this, adjusting the folder location if needed:
   > I have a folder called dhi in my Downloads folder. Please move it to
   > ~/.claude/skills/dhi on my computer, creating that location if it
   > doesn't already exist. Then run /dhi install for me.
3. Claude Code will do the file moving and setup itself, and will ask which
   Google Drive folder holds your documents.

Note: Method B doesn't get automatic updates later -- if you want a newer
version, you'd need a new zip. Method A updates whenever the skill is
updated, via `/plugin update dhi@skills`.

## Using it day to day

- **Organize your documents**: inside the Drive folder you chose during
  install, make a subfolder per topic (e.g. `Finance`, `Health`, `Recipes`)
  and put your files in the matching subfolder, right in Drive -- no need to
  do anything through Claude. Anything you drop directly in the main folder
  without sorting it still works -- it just gets grouped under
  "Uncategorized" until you move it.
- **Add new documents any time** -- just drop files into the right Drive
  subfolder. `dhi` doesn't watch Drive in the background (there's no way for
  it to, without your Claude session running); run `/dhi index` again
  whenever you've added or changed files and want them searchable, or just
  ask a question -- `dhi` will mention if the index looks old and offer to
  refresh it first.
- **Ask questions**: type things like:
  ```
  /dhi ask "What is my engineering team budget for Q3?"
  ```
  or just describe what you want in plain English -- Claude Code will
  recognize it's a `dhi` question. Every answer tells you exactly which
  document (and page or section) it came from.
- **Check what's indexed**: `/dhi status` shows how many documents/topics
  you have and when it last checked for updates.
- **Adjust settings**: `/dhi config` shows current settings; e.g.
  `/dhi config frequency_days 3` changes how often it checks for updates.

## If something goes wrong

Just describe the problem to Claude Code in plain English -- e.g. "dhi says
it can't find my documents" or "run /dhi install again." You don't need to
know why it broke; Claude Code can read the error and fix it or explain it.
