# CLAUDE.md

See also [the contributor documentation](docs/contributing.rst) for setup, test, lint and docs commands.

## Development Notes

- Use `uv run python` / `uv run pytest` to use the development runtime.
- Rendering and compositing need the optional `composite` extra: `uv sync --extra composite`
  (`aggdraw`, `scipy`, `scikit-image`). It is optional because it is unavailable on some
  platforms (notably Python 3.14 on Windows). Tests needing it carry the `composite` marker.
- `uv run pytest --no-cov` skips coverage; `uv run pytest path::test_name` runs one test.
- Changes land via PR; `main` is protected.

## Architecture Overview

### Two-Layer Design

**Low-level (`psd_tools.psd`)**: reads/writes raw PSD binary structures following Adobe's
specification. All classes use `attrs` and implement `read(fp)` and `write(fp)`.

**High-level (`psd_tools.api`)**: Pythonic interfaces. `PSDImage` wraps the low-level `PSD`
and reconstructs the layer tree from the flat layer record list.

Other subpackages: `psd_tools.composite` (rendering: blend modes, effects, vector
rasterization) and `psd_tools.compression` (Raw, RLE, ZIP; `_rle.pyx` is a Cython RLE codec
with a pure-Python fallback).

Import convention: internal code imports from the defining module
(`from psd_tools.psd.document import PSD`); public API uses the package
(`from psd_tools.psd import PSD`).

### Contracts

- **Read-only by design.** Mutating low-level structures under the API is out of contract.
  A stale cache after a *high-level* edit (`layer.name = ...`) is a real bug.
- **Unknown data round-trips.** Unrecognised tagged blocks and fields are preserved as bytes
  on write. Do not drop or reinterpret them.
- **Lazy loading.** The API layer parses masks, effects and channel data only on access.

### Layer Tree Reconstruction

PSD stores layers as a **flat list** with implicit hierarchy. The `SectionDivider` tagged
block marks group boundaries:

```text
Record 0: "Background" (normal layer)
Record 1: "Group" (BOUNDING_SECTION_DIVIDER = group start)
Record 2:   "Child 1" (inside group)
Record 3:   "Child 2" (inside group)
Record 4: (END_SECTION_DIVIDER = group end)
```

### BaseElement and attrs

All binary structures inherit from `BaseElement` and implement
`read(cls, fp, **kwargs) -> Self` and `write(self, fp, **kwargs) -> int`, so complex
structures compose recursively from simple ones. Data classes use `attrs`
(`@define(repr=False)`, `field(default=...)`); validators must match type hints.

### Tagged Blocks

Metadata lives in tagged blocks keyed by a 4-byte `Tag`; a registry maps tags to handler
classes via `@register(Tag.FOO)`.

```python
if Tag.UNICODE_LAYER_NAME in layer._record.tagged_blocks:
    name = layer._record.tagged_blocks.get_data(Tag.UNICODE_LAYER_NAME)
```

### Accessing Layer Records

Where the document has an `Lr16`/`Lr32` tagged block -- Photoshop writes one for 16- and
32-bit files -- the records live there and `layer_info` is empty, so go through the accessor:

```python
layer_records = psd._record._get_layer_info().layer_records
```

### Key Files

- `src/psd_tools/psd/document.py`: the `PSD` class (re-exported from `psd_tools.psd`).
- `src/psd_tools/psd/tagged_blocks.py`: tagged block registry and handlers.
- `src/psd_tools/psd/descriptor.py`: Adobe's descriptor format (key-value serialization).
- `src/psd_tools/terminology.py`: Adobe's 4-byte identifier mappings.

## Testing Conventions

- Tests mirror the package structure: `tests/psd_tools/psd/` for low-level,
  `tests/psd_tools/api/` for high-level. Fixture PSDs are in `tests/psd_files/`.
- Tests often parametrize over fixture files.
- Round-trip validation is common: read → modify → write → read → verify.

## Type Annotations

New code uses type hints on all signatures and `typing_extensions.Self` for methods
returning their own class.

`psd_tools.api` property getters:

- A property annotated `int`, `float`, `bool` or `str` returns that primitive,
  not the descriptor wrapper (`Integer`, `UnitFloat`, ...), which does not
  subclass it and fails `isinstance` and `json.dumps`. Cast at the getter.
  `tests/psd_tools/api/test_annotations.py` enforces this over the fixture corpus.
- A missing key returns a documented Photoshop default only when the format
  defines one; otherwise annotate `T | None` and return `None`. Never invent a
  default to satisfy the annotation, and do not raise (#788).
- Do not annotate `Any` for a value whose type the low-level declaration knows.

## Code Comments and Docstrings

Keep them short, and document **current behavior only**. A comment earns its
length by explaining something the code cannot say itself — a non-obvious
constraint, a format quirk, why an obvious approach is wrong. Three things do
not belong in one:

- **History.** "used to", "was expected to fail at", "before #854". The
  before/after belongs in the PR body, the commit message and the issue.
- **Measured figures.** MSE bounds, corpus statistics, error counts. They drift
  under the next change and leave a comment that reads as fact. A bound keeps
  its *reason* ("an aggdraw pen is not bit-stable across versions"), never its
  value.
- **The same explanation at three layers.** Say it once, where it belongs.

What stays: bare issue refs like `(#854)`, which point *into* that history;
fixture geometry such as "a 100x100 path", which is a property of the file; and
anything a test asserts.

To keep a number, name it in code rather than recite it in prose:

```python
stroke_color = 0.129  # PANTONE Black 3 C, red channel
assert color[row, column] == pytest.approx(share * stroke_color, abs=0.002)
```

That is checked on every run; the same number in a docstring rots silently.

Existing long comment blocks are the tree's current state, not a precedent to
match — see #891. Measure with `uv run python tools/prose_density.py`. This is
the [Changelog](#changelog) policy applied to source.

## Changelog

`docs/changelog.rst` is **maintained by hand** and is **not** generated by any
workflow. Do not skip it on the assumption that it is automated.

The `release` workflow does generate release notes from `git log`, but those go
into the **GitHub Release body** only — that is a separate artifact and never
touches `docs/changelog.rst`.

**A PR that changes user-visible behaviour adds its own entry**, in the same PR
as the change. Add it under a `X.Y.Z (unreleased)` heading at the top of the
file, creating that heading if it does not exist yet; the release PR later
replaces `(unreleased)` with the release date.

```rst
Changelog
=========

1.19.0 (unreleased)
-------------------

- [fix] Short description of the user-visible change (#123, #456)
```

Prefix each entry with its category, and reference the issue and PR numbers:

- `[fix]` — a bug fix that leaves the public surface unchanged, wherever it
  lives: parsing, rendering, compression
- `[api]` — a change to the public surface: a new or renamed symbol, a new
  parameter, a corrected annotation
- `[security]` — security fixes
- `[docs]` — documentation only
- `[ci]` — CI, packaging and release engineering
- `[refactor]` — internal restructuring a user can still observe, such as a
  moved public module
- `[chore]` — tooling and housekeeping; the release PR also writes one `[chore]`
  line summarising that release's dependency bumps

Pick the most specific one that applies. A category names the **kind** of change,
not the subpackage it touches — a low-level parsing fix is `[fix]`, not `[psd]`.
Only these seven are current: released sections still carry `[psd]`,
`[composite]`, `[packaging]`, `[dev]` and the rest of a long tail, all retired,
and that history stays as written. This list is the only one — anything else that
needs the categories, the release skill included, points here rather than
restating them (#791).

Flag any backwards-incompatible change explicitly in the entry text.

**Budget: aim for four lines, and treat six as the ceiling** — one line of
summary, plus a short "does this affect me" clause where the answer is not
obvious, plus the refs. Spend the extra lines on a backwards-incompatibility
warning or a migration instruction, never on mechanism.
An entry's job is to let a reader decide whether they are affected and then
hand them the link; it is not the place to explain the mechanism. That
explanation is already published in three linked places — the PR body, the
commit message, and the GitHub Release body — so a longer entry duplicates
them and dates faster than they do. Corpus statistics, measured error figures,
and the history of what earlier PRs got wrong all belong in the PR, not here.

Entries are for user-visible change, with `[ci]` and `[chore]` as the standing
exception — the changelog carries the release-engineering record too. Skip
test-only changes, and dependabot bumps, which the release PR summarises in bulk.
Internal restructuring earns an entry only when a user can observe it, which is
what `[refactor]` is for.

## Releases

Run the `/release` skill (`.claude/skills/release/SKILL.md`); the pipeline is described in
[the contributor documentation](docs/contributing.rst). One hard constraint: the release PR's
branch must be named exactly `release/vX.Y.Z` (PEP 440 forms such as `v1.2.3rc1` are
accepted), because the `auto-tag` workflow reads the version from it.
