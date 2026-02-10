---
description: Search your media catalog by tags or description
argument-hint: [search-query]
allowed-tools:
  - Bash(python3:*)
  - Bash(python:*)
  - Read
---

Search the media catalog database for assets matching: $ARGUMENTS

Use the catalog_db.py search command to find matching assets:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog_db.py search <path-to-catalog.db> "$ARGUMENTS"
```

The default catalog location is `media_catalog.db` in the media folder that was previously ingested. If the catalog path is not obvious, check recent ingest output or ask the user.

Present results in a readable format showing:
- Filename and file type
- Description (truncated to 2 sentences)
- Top tags
- File path

If no results are found, suggest broader search terms or show catalog stats:
```bash
python3 ${CLAUDE_PLUGIN_ROOT}/scripts/catalog_db.py stats <path-to-catalog.db>
```
