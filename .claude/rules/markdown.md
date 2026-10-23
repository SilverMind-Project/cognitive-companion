---
paths: ["**/*.md"]
---

# Markdown

- No em-dashes (U+2014): use a colon, comma, semicolon, or parentheses. `make check-md`, the
  pre-commit hook, and CI refuse one; a line that must quote one verbatim carries
  `<!-- em-dash-ok -->`.
- Tables: a header row and a separator row; keep cells short and move detail into prose.
- An instruction file (CLAUDE.md, AGENTS.md, a skill, a rule) names only files that exist:
  `make docs-check` fails on a dead reference.
