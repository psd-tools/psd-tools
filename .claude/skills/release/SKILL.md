---
name: release
description: Prepare a psd-tools release: update changelog, open release PR. Use when the user wants to cut a new version.
allowed-tools: Bash(git:*), Bash(gh:*), Bash(date:*)
---

## Step 0 — Determine target version

**Provided version**: $ARGUMENTS

### If a version was provided (above is non-empty)

Validate it as a PEP 440 string (e.g. `1.2.3`, `1.2.3a1`, `1.2.3rc1`, `1.2.3.post1`).
Note: PEP 440 versions must **not** start with `v` — that prefix belongs on the git tag, not
the version string.
Stop and ask the user to correct it if invalid. Store it as **VERSION** for all subsequent steps.

### If no version was provided (above is empty)

Analyze the commits listed in Step 1 to recommend the correct next version.
The last tag shown in Step 1 uses a `v` prefix (e.g. `v1.14.3`); strip it when computing
the next version so the result is a bare PEP 440 string (e.g. `1.14.4`, not `v1.14.4`).

Apply these semver rules:

- **Major bump** (`X+1.0.0`) — any commit that breaks a public API or documented behaviour
- **Minor bump** (`X.Y+1.0`) — any new public feature or API addition, no breaking changes
- **Patch bump** (`X.Y.Z+1`) — bug fixes, security patches, chores, docs, or refactoring only

Show your reasoning and proposed version to the user, then ask them to confirm or override it.
Store the confirmed version as **VERSION** for all subsequent steps.

## Step 1 — Review commits since the last release

Fetch tags and list commits since the last release:

!`git fetch --tags -q || echo "Warning: failed to fetch tags — check network/auth and consider retrying."`

Last tag: !`git describe --tags --abbrev=0 2>/dev/null || echo "(none)"`

Today's date: !`date +%Y-%m-%d`

Using the last tag shown above, run `git log <LAST_TAG>..HEAD --oneline` to list commits since that tag. If there is no last tag, run `git log --oneline` to list all commits.

## Step 2 — Draft changelog entry

Read `docs/changelog.rst` to understand the current format, then draft a new entry for **VERSION**
using this RST format:

```
VERSION (YYYY-MM-DD)
--------------------

- [category] Description (#PR)
```

**Important**: The `-` underline must be at least as long as the title line (RST requirement).
Count the exact characters in `VERSION (YYYY-MM-DD)` and use that many dashes.

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

Prepend the approved changelog entry directly after the `Changelog` header block and the
following blank line, leaving a blank line between the header and the new entry.

## Step 4 — Create release branch and commit

```bash
git checkout -b release/vVERSION
git add docs/changelog.rst
git commit -m "docs: release vVERSION"
git push -u origin release/vVERSION
```

Replace `VERSION` with the actual version string (e.g. `1.14.4`).

## Step 5 — Open a pull request

Run `gh pr create` with `--title "Release vVERSION"` and a `--body` containing:

- A `## Release vVERSION` heading
- A `### Changelog` section with the approved entry from Step 2 pasted in
- A `### Release checklist` section with these items:
  - `[ ] Changelog entry reviewed and accurate`
  - `[ ] Version follows PEP 440`
- A closing note: "After this PR is merged, the `auto-tag` workflow will tag the merge commit
  as `vVERSION` and the `release` workflow will build wheels and publish to PyPI automatically."

Replace `VERSION` with the actual version string throughout.

## Step 6 — Done

Print the PR URL. Remind the user:

> After the PR is approved and merged, the `auto-tag` GitHub Actions workflow tags the merge
> commit as `vVERSION` automatically. That tag push triggers the `release` workflow to build
> wheels for all platforms and publish to PyPI. No manual tagging or publishing is needed.

Replace `VERSION` with the actual version string.
