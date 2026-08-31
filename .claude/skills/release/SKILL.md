---
name: release
description: Prepare a psd-tools release: update changelog, open release PR. Use when the user wants to cut a new version.
allowed-tools: Bash(git:*), Bash(gh:*), Bash(date:*), Edit
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

Fetch tags:

!`git fetch --tags -q || echo "Warning: failed to fetch tags — check network/auth and consider retrying."`

Last tag: !`git describe --tags --abbrev=0 2>/dev/null || echo "(none)"`

Today's date: !`date +%Y-%m-%d`

Now list the commits since the last release by running one of these commands:

- If "Last tag" above is `(none)`: run `git log --oneline`
- Otherwise: run `git log <LAST_TAG>..HEAD --oneline` (substituting the actual tag)

You must run this command and review the output before proceeding to Step 0 or Step 2.

## Step 1b — Prose sweep

Rationale docstrings and comments accumulate across a release: each fix PR appends a
paragraph explaining what it measured, and none compresses what is already there. Trim
them now, while the release is the unit of review — nothing enforces this mechanically
(ruff's docstring rules are off, `ruff format` does not reflow comments or docstrings,
and no line-length rule is selected), so this step is the only thing that catches it.

Measure rather than eyeball — the worst ratios sit on the smallest helpers, which read
as fine in a diff:

```bash
uv run python tools/prose_density.py
```

Anything above roughly 3x prose-to-code deserves a look. Keep what cost real
measurement, and what stops a future reader undoing a fix: why a bound is shaped the
way it is, why a guard cannot be tighter, what an experiment ruled out. Cut history the
changelog already holds, corpus statistics the tests already assert, and the same
explanation repeated at three layers.

Trimming is a separate commit from the release commit, and touches comments and
docstrings only. If any line of code moves, stop and treat it as a code change.

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
```

Then update `src/psd_tools/version.py` using the Edit tool — replace the existing
`__version__` line with:

```python
__version__ = "VERSION"
```

`VERSION` is the bare PEP 440 string **without** the `v` prefix (e.g. `1.15.0`, not `v1.15.0`).

Then stage both changed files and commit:

```bash
git add docs/changelog.rst src/psd_tools/version.py
git commit -m "docs: release vVERSION"
git push -u origin release/vVERSION
```

Replace `VERSION` with the actual version string (e.g. `1.15.0`).

## Step 5 — Open a pull request

Run `gh pr create` with `--title "Release vVERSION"` and a `--body` containing:

- A `## Release vVERSION` heading
- A `### Changelog` section with the approved entry from Step 2 pasted in
- A `### Release checklist` section with these items:
  - `[ ] Changelog entry reviewed and accurate`
  - `[ ] Version follows PEP 440`
  - `[ ] Prose sweep done (Step 1b), or explicitly skipped`
- A closing note: "After this PR is merged, the `auto-tag` workflow will tag the merge commit
  as `vVERSION` and the `release` workflow will build wheels and publish to PyPI automatically."

Replace `VERSION` with the actual version string throughout.

## Step 6 — Done

Print the PR URL. Remind the user:

> After the PR is approved and merged, the `auto-tag` GitHub Actions workflow tags the merge
> commit as `vVERSION` automatically. That tag push triggers the `release` workflow to build
> wheels for all platforms and publish to PyPI. No manual tagging or publishing is needed.

Replace `VERSION` with the actual version string.
