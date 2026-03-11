---
name: memory
description: Two-layer memory system with semantic search and daily logs.
always: true
---

# Memory

## Structure

- `memory/MEMORY.md` — Long-term facts (preferences, project context, relationships). Always loaded into your context.
- `memory/YYYY-MM-DD.md` — Daily logs, one file per day. Today and yesterday are auto-loaded into context. Each entry starts with `[HH:MM]`.

## Search Past Events

Use the `memory_search` tool for semantic recall:

```
memory_search(query="meeting with Alice", max_results=5)
```

This performs hybrid search (BM25 full-text + vector similarity) across all memory files with temporal decay and diversity re-ranking.

## Read Specific Memory

Use the `memory_get` tool to read a specific file:

```
memory_get(path="memory/2026-03-10.md")
memory_get(path="memory/MEMORY.md", start_line=10, num_lines=20)
```

Only files under `memory/` and `MEMORY.md` are accessible.

## When to Update MEMORY.md

Write important facts immediately using `edit_file` or `write_file`:
- User preferences ("I prefer dark mode")
- Project context ("The API uses OAuth2")
- Relationships ("Alice is the project lead")

## Daily Logs

Day-to-day events, conversations, and notes are written to `memory/YYYY-MM-DD.md`. These are managed automatically during consolidation, but you can also write to today's log directly.

## Auto-consolidation

When the session grows large, old conversations are automatically summarized:
- Key events and decisions → today's daily log (`memory/YYYY-MM-DD.md`)
- Long-term facts → `memory/MEMORY.md`
- A pre-compaction flush may trigger before consolidation to save important context.
