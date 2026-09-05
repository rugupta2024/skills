# skills

A personal collection of Claude Code skills, published as a Claude Code
plugin marketplace. Each skill lives in its own folder as an independently
installable plugin.

## Available skills

| Skill | What it does |
|---|---|
| [`dhi`](dhi/skills/dhi/README.md) | Personal document Q&A -- organize documents into topic folders, `dhi` indexes them locally and answers questions strictly from that content, with citations. |

## Installing a skill (for Claude Code users)

In any Claude Code session, run:
```
/plugin marketplace add rugupta2024/skills
/plugin install dhi@skills
```
Then just talk to it -- e.g. type `/dhi install` and follow the prompts.

If you're not comfortable with the commands above, or don't have a way to
run them, see the plain-language guide for `dhi` instead:
[`dhi/skills/dhi/README.md`](dhi/skills/dhi/README.md) -- it covers both this
method and a no-terminal, zip-file alternative.

## Repo layout

```
skills/
├── .claude-plugin/
│   └── marketplace.json     # lists every plugin in this repo
├── dhi/                      # one plugin per skill
│   ├── .claude-plugin/
│   │   └── plugin.json
│   └── skills/dhi/            # the actual skill (SKILL.md + code)
└── ...                        # future skills follow the same pattern
```
