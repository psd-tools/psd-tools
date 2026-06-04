---
name: investigate-issue
description: Investigate a GitHub issue and post structured findings as a comment. Use when the user wants to analyze a bug report, reproduce it, and share findings on the issue thread.
allowed-tools: Bash(git:*), Bash(gh:*), Bash(uv:*), Bash(grep:*), Bash(find:*), Read, WebFetch(domain:github.com)
---

## Step 0 — Identify the issue

**Provided issue**: $ARGUMENTS

If an issue number was provided, continue to Step 1.
If no issue number was provided, ask the user which issue to investigate.

## Step 1 — Fetch the issue

```bash
gh issue view ISSUE_NUMBER --repo psd-tools/psd-tools --comments
```

Read the full issue body, title, and all comments. Understand:
- What behavior the reporter expected
- What behavior they observed
- Any reproduction steps or sample files mentioned
- The version of psd-tools they used

## Step 2 — Reproduce or locate the root cause

Based on the issue description, investigate the codebase:

1. Search for relevant code using `grep` or `find` in `src/psd_tools/`
2. If the issue has a code snippet, try to reproduce it:
   ```bash
   uv run python -c "..."
   ```
3. If the issue mentions a specific PSD feature, trace the code path:
   - High-level API: `src/psd_tools/api/`
   - Low-level parsing: `src/psd_tools/psd/`
   - Compositing: `src/psd_tools/composite/`
4. Look for related tests in `tests/` that may already cover (or fail to cover) the case

Classify the issue into one of these categories before writing the comment:

| Classification | When it applies |
| -------------- | --------------- |
| **Bug (parsing)** | Wrong data read from the PSD binary |
| **Bug (API)** | Wrong value exposed to the user |
| **Missing feature** | Behavior not implemented |
| **Already fixed** | The bug no longer reproduces on `main` |
| **Unreproducible** | Cannot reproduce without a sample file or more detail |
| **By design / known limitation** | Documented or intentional constraint (see Known Limitations in CLAUDE.md) |
| **Needs composite deps** | Only affects users without `psd-tools[composite]` installed |
| **Documentation** | User misunderstood the API |
| **Duplicate** | Same root cause as an existing issue |

## Step 3 — Draft investigation findings

Write a clear, structured comment in Markdown. Tailor the content to the classification:

```markdown
## Investigation findings

**Classification**: [one of the categories above]

### Analysis

[2–4 paragraphs: what you found, where in the code the issue originates, and why it happens.
For "Already fixed", note the commit/PR that fixed it.
For "Unreproducible", list what you tried and what additional info is needed (sample PSD file, version, Python version, etc.).
For "By design / known limitation", cite the relevant Known Limitations entry.
For "Needs composite deps", explain which optional packages are required and how to install them.]

### Relevant code

[Point to specific files and line numbers, e.g. `src/psd_tools/psd/smart_object.py:123`.
Omit if not applicable.]

### Reproduction

[Minimal code that reproduces the bug. If unreproducible, omit this section.]

### Suggested fix

[Brief description of the approach to fix it.
Omit for "By design", "Already fixed", "Duplicate", and "Unreproducible" — use the Analysis section instead.]
```

Omit sections that are not applicable. Keep the tone neutral and technical.

## Step 4 — Ask before posting

Show the user the draft comment and ask: "Ready to post this as a comment on issue #NUMBER?"

Do NOT post without explicit user confirmation.

## Step 5 — Post the comment

Once the user confirms, write the comment body to a temp file and post via `--body-file` to
safely handle multiline Markdown, backticks, and special characters:

```bash
cat > /tmp/issue_comment.md << 'EOF'
COMMENT_BODY
EOF
gh issue comment ISSUE_NUMBER --repo psd-tools/psd-tools --body-file /tmp/issue_comment.md
```

Print the URL of the posted comment.
