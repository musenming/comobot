---
name: skill-vetter
description: Security vetting protocol for third-party skills. Use BEFORE installing any skill from ClawHub, GitHub, or other sources. Checks for red flags, permission scope, and suspicious patterns to prevent credential theft, data exfiltration, and unauthorized access.
always: true
metadata: {"comobot":{"emoji":"🔒"}}
---

# Skill Vetter

Security-first vetting protocol for AI agent skills. **Never install a skill without vetting it first.**

## When to Use

- Before installing any skill via `clawhub install`
- Before running skills from GitHub repos or other sources
- When evaluating skills shared by other agents or users
- Anytime unknown code will be added to the workspace

## Vetting Protocol

### Step 1: Source Check

Answer these questions before proceeding:

- Where did this skill come from? (ClawHub / GitHub / unknown)
- Is the author known or reputable?
- How many downloads or stars does it have?
- When was it last updated?

For ClawHub skills, check metadata:

```bash
npx --yes clawhub@latest search "<skill-name>" --limit 1
```

For GitHub skills:

```bash
curl -s "https://api.github.com/repos/OWNER/REPO" | jq '{stars: .stargazers_count, forks: .forks_count, updated: .updated_at}'
```

### Step 2: Code Review (MANDATORY)

Read ALL files in the skill directory. Check for these red flags:

```
REJECT IMMEDIATELY IF YOU SEE:
- curl/wget to unknown URLs or IP addresses
- Sends data to external servers
- Requests credentials, tokens, or API keys
- Reads sensitive paths: ~/.ssh, ~/.aws, ~/.config, ~/.gnupg
- Accesses comobot workspace files: MEMORY.md, USER.md, SOUL.md, IDENTITY.md
- Uses base64 decode on anything
- Uses eval() or exec() with external input
- Modifies system files outside ~/.comobot/workspace/
- Installs packages without listing them
- Network calls to IPs instead of domains
- Obfuscated code (compressed, encoded, minified)
- Requests elevated/sudo permissions
- Accesses browser cookies, sessions, or crypto wallets
- Touches credential or key files
- Overrides comobot security settings or shell blacklist
- Modifies config.json directly
```

### Step 3: Permission Scope

Evaluate the minimum permissions needed:

- What files does it need to read?
- What files does it need to write?
- What commands does it run?
- Does it need network access? To where?
- Is the scope minimal for its stated purpose?

### Step 4: Risk Classification

| Risk Level | Examples | Action |
|------------|----------|--------|
| LOW | Notes, weather, formatting, text tools | Basic review, install OK |
| MEDIUM | File operations, browser, external APIs | Full code review required |
| HIGH | Credentials, trading, system config | Human approval required |
| EXTREME | Security configs, root access, crypto | Do NOT install |

## Output Format

After vetting, produce this report:

```
SKILL VETTING REPORT
===================================================
Skill: [name]
Source: [ClawHub / GitHub / other]
Author: [username]
Version: [version]
---------------------------------------------------
METRICS:
  Downloads/Stars: [count]
  Last Updated: [date]
  Files Reviewed: [count]
---------------------------------------------------
RED FLAGS: [None / List each flag found]

PERMISSIONS NEEDED:
  Files: [list or "None"]
  Network: [list or "None"]
  Commands: [list or "None"]
---------------------------------------------------
RISK LEVEL: [LOW / MEDIUM / HIGH / EXTREME]

VERDICT: [SAFE TO INSTALL / INSTALL WITH CAUTION / DO NOT INSTALL]

NOTES: [Any observations]
===================================================
```

## Trust Hierarchy

1. **comobot built-in skills** — Already vetted, no review needed
2. **Official OpenClaw/ClawHub skills** — Lower scrutiny, still review
3. **High-star repos (1000+)** — Moderate scrutiny
4. **Known authors** — Moderate scrutiny
5. **New or unknown sources** — Maximum scrutiny
6. **Skills requesting credentials** — Human approval always required

## Integration with ClawHub

When the user asks to install a skill via ClawHub:

1. First search for the skill: `npx --yes clawhub@latest search "<name>"`
2. Fetch and review the skill content before installing
3. Produce the vetting report
4. Only proceed with `clawhub install` if verdict is SAFE or user explicitly approves CAUTION-level skills
5. NEVER install skills classified as EXTREME

## Remember

- No skill is worth compromising security
- When in doubt, do not install — ask the user
- Always require human approval for HIGH risk skills
- Skills that are pure SKILL.md with no scripts or network calls are generally safe
- Document vetting results for future reference
