---
name: clawhub
description: Search and install agent skills from ClawHub, the public skill registry.
homepage: https://clawhub.ai
metadata: {"comobot":{"emoji":"🦞"}}
---

# ClawHub

Public skill registry for AI agents. Search by natural language (vector search).

## When to use

Use this skill when the user asks any of:
- "find a skill for …"
- "search for skills"
- "install a skill"
- "what skills are available?"
- "update my skills"

## Search

```bash
npx --yes clawhub@latest search "web scraping" --limit 5
```

## Install (Security-First Workflow)

**IMPORTANT: Always run the Skill Vetter protocol before installing any skill.**

### Step 1: Search and preview

```bash
npx --yes clawhub@latest search "<query>" --limit 5
```

### Step 2: Vet the skill (MANDATORY)

Before installing, review the skill content using the **skill-vetter** protocol:

1. Fetch the skill's SKILL.md and all files for review
2. Follow the full vetting protocol (Source Check → Code Review → Permission Scope → Risk Classification)
3. Produce a vetting report
4. Only proceed to install if the verdict is **SAFE TO INSTALL** or the user explicitly approves a **INSTALL WITH CAUTION** verdict

If the skill is classified as **EXTREME** risk, refuse to install and explain why.

### Step 3: Install (only after vetting passes)

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.comobot/workspace
```

Replace `<slug>` with the skill name from search results. This places the skill into `~/.comobot/workspace/skills/`, where comobot loads workspace skills from. Always include `--workdir`.

## Update

```bash
npx --yes clawhub@latest update --all --workdir ~/.comobot/workspace
```

When updating skills, re-vet any skill whose content has changed significantly.

## List installed

```bash
npx --yes clawhub@latest list --workdir ~/.comobot/workspace
```

## Notes

- Requires Node.js (`npx` comes with it).
- No API key needed for search and install.
- Login (`npx --yes clawhub@latest login`) is only required for publishing.
- `--workdir ~/.comobot/workspace` is critical — without it, skills install to the current directory instead of the comobot workspace.
- After install, remind the user to start a new session to load the skill.
