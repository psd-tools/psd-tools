---
name: release
description: Prepare a psd-tools release: update changelog, open release PR. Use when the user wants to cut a new version.
allowed-tools: Bash(git:*), Bash(gh:*), Bash(uv:*), Bash(date:*), Read, Edit
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

Apply the project's rule, which is not plain semver:

- **Minor bump** (`X.Y+1.0`) — any new public feature or API addition, **or** any change
  that breaks a public API or documented behaviour. Pre-2.0 a minor bump may break; what
  the project asks of such a change is not a major bump but that the entry says so
  explicitly, which the **Changelog** section of `CLAUDE.md` already requires.
- **Patch bump** (`X.Y.Z+1`) — bug fixes, security patches, chores, docs or refactoring
  only, with nothing backwards-incompatible.

Never infer a **major bump** from the presence of breaking changes. `2.0.0` is a
deliberate decision by the maintainer about the project's direction; propose it only if
they have already said they want one.

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

## Step 1c — Reconcile the release milestone

Release scope is also tracked in a milestone, titled bare without the `v` prefix
(`1.20.0`, not `v1.20.0`). It is maintained by hand during triage, so it and the changelog
can disagree about the same release. Settle that before Step 2 drafts the changelog, since
the answer changes what gets written.

The two drift in both directions, and one query cannot see both.

**The milestone over-promises** — it holds an item whose fix never landed:

```bash
gh issue list --milestone "VERSION" --state all --limit 100 \
  --json number,title,state,closedAt
```

An empty result is fine; a release cut outside the milestone scheme is not an error.

**The milestone under-reports** — an item was fixed but is milestoned for a *later*
release, so it stands closed against a release it did not ship in. It is not in
**VERSION**, so the query above cannot show it. List what closed since the last tag
instead, substituting that tag's commit timestamp, which
`git log -1 --format=%cI <LAST_TAG>` prints in full:

```bash
gh issue list --state closed --limit 200 \
  --search "closed:>=YYYY-MM-DDTHH:MM:SS+HH:MM" \
  --json number,title,closedAt,milestone
```

Pass the whole timestamp, not just the date. A release tagged partway through a day
leaves issues closed before it on the same date, and those belong to the release that
just shipped; a date-only bound sweeps them into this one.

Of those, only the ones carrying a different version are drift. An item with **no**
milestone is not — the milestone records planned scope, not everything that shipped — so
give its count in one line and leave it alone unless the user asks.

Put both lists to the user and ask; do not change anything first. Whether an open item
blocks the release is the call a human is here to make.

- **Open items in VERSION**: move to the next milestone, or hold the release for them.
  Closing a milestone does not close its issues, so one left open stands attached to a
  release it did not ship in.
- **Closed items milestoned later**: move into **VERSION**, or leave them.

Once the user has decided, apply it with `gh issue edit <N> --milestone "<title>"`.

Do not close the milestone here. `auto-tag.yml` closes it after the merge (see Step 6).

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

The categories, and the rule for picking between them, are documented in the
**Changelog** section of the repo-root `CLAUDE.md`, which loads as project
instructions — use that list. It is deliberately not restated here: the second copy
is what drifted (#791).

Group related changes. Omit purely internal churn that users won't care about. Reference PR numbers where available.

Show the draft to the user and ask for approval or edits before continuing.

## Step 3 — Update docs/changelog.rst

Prepend the approved changelog entry directly after the `Changelog` header block and the
following blank line, leaving a blank line between the header and the new entry.

## Step 4 — Create release branch and commit

The branch name is the only thing `auto-tag` reads the version from, and it matches
`^release/(vX.Y.Z...)$` anchored at both ends, so the name has to be exactly
`release/vVERSION`. A prefixed variant is not a cosmetic difference: the extract step
yields an empty version, the `tag` job is skipped on `version != ''`, and the run
still reports success — so nothing is tagged and nothing says so.

Create it once, by whichever of these two routes applies.

If the project's instructions ask for a worktree, create the worktree and rename its
branch from inside it. `EnterWorktree` names the branch after the worktree rather than
the name it was given, prefixing `worktree-` and replacing slashes: asking for
`release/v1.20.0` produced `worktree-release+v1.20.0`.

```bash
git branch -m release/vVERSION
```

Otherwise create the branch directly:

```bash
git checkout -b release/vVERSION
```

Either way, confirm it before going on — `git branch --show-current` has to print
`release/vVERSION` exactly.

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
  - `[ ] Milestone reconciled both ways (Step 1c)`
- A closing note: "After this PR is merged, the `auto-tag` workflow will tag the merge commit
  as `vVERSION` and the `release` workflow will build wheels and publish to PyPI automatically."

Replace `VERSION` with the actual version string throughout.

## Step 6 — Done

Print the PR URL. Remind the user:

> After the PR is approved and merged, the `auto-tag` GitHub Actions workflow tags the merge
> commit as `vVERSION` automatically. That tag push triggers the `release` workflow to build
> wheels for all platforms and publish to PyPI. No manual tagging or publishing is needed.
> The same workflow closes the `VERSION` milestone if one is open; that step is bookkeeping
> and is allowed to fail without affecting the release.

Replace `VERSION` with the actual version string.
