---
name: release
description: Prepare a psd-tools release: update changelog, open release PR. Use when the user wants to cut a new version.
allowed-tools: Bash(git:*), Bash(gh:*), Bash(date:*)
---

Prepare a release for version **$ARGUMENTS**.

If `$ARGUMENTS` is empty, ask the user for the target version before proceeding.

Validate that `$ARGUMENTS` is a valid PEP 440 version string (e.g. `1.2.3`, `1.2.3a1`, `1.2.3rc1`, `1.2.3.post1`). If it is not, stop and ask the user to provide a valid version.

## Step 1 — Review commits since the last release

Fetch tags and list commits since the last release:

!`git fetch --tags -q 2>/dev/null && echo ""`

Here are the commits since the last tag:

!`git log "$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)"..HEAD --oneline`

Last tag: !`git describe --tags --abbrev=0 2>/dev/null || echo "(none)"`

Today's date: !`date +%Y-%m-%d`

## Step 2 — Draft changelog entry

Read `docs/changelog.rst` to understand the current format, then draft a new entry for version `$ARGUMENTS` using this RST format:

```
$ARGUMENTS (YYYY-MM-DD)
-----------------------

- [category] Description (#PR)
```

**Important**: The `-` underline must be at least as long as the title line (RST requirement).
Count the exact characters in `$ARGUMENTS (YYYY-MM-DD)` and use that many dashes.

Use these categories (pick the most specific one per bullet):

- `api` — public API additions or changes
- `psd` — low-level PSD parsing/writing
- `fix` — bug fixes
- `refactor` — internal restructuring, no behaviour change
- `docs` — documentation only
- `ci` — CI/CD, GitHub Actions
- `chore` — dependency bumps, tooling, housekeeping
- `security` — security fixes

Group related changes. Omit purely internal churn that users won't care about. Reference PR numbers where available.

Show the draft to the user and ask for approval or edits before continuing.

## Step 3 — Update docs/changelog.rst

Prepend the approved changelog entry directly after the `Changelog\n=========` header (line 3 of the file), leaving a blank line between the header and the new entry.

## Step 4 — Create release branch and commit

```bash
git checkout -b release/v$ARGUMENTS
git add docs/changelog.rst
git commit -m "docs: release v$ARGUMENTS"
git push -u origin release/v$ARGUMENTS
```

## Step 5 — Open a pull request

Run `gh pr create` with `--title "Release v$ARGUMENTS"` and a `--body` containing:

- A `## Release v$ARGUMENTS` heading
- A `### Changelog` section with the approved entry from Step 2 pasted in
- A `### Release checklist` section with these items:
  - `[ ] Changelog entry reviewed and accurate`
  - `[ ] Version follows PEP 440`
- A closing note: "After this PR is merged, the `auto-tag` workflow will tag the merge commit as `v$ARGUMENTS` and the `release` workflow will build wheels and publish to PyPI automatically."

## Step 6 — Done

Print the PR URL. Remind the user:

> After the PR is approved and merged, the `auto-tag` GitHub Actions workflow tags the merge commit automatically. That tag push triggers the `release` workflow to build wheels for all platforms and publish to PyPI. No manual tagging or publishing is needed.
