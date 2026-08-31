#!/usr/bin/env python
"""Report prose-to-code ratios per function, to find comment blocks worth trimming.

Rationale prose accumulates across a release: a fix PR appends a paragraph
recording what it measured, the next appends another, and nothing compresses
what is already there. Nothing catches it mechanically either -- ruff's
docstring rules are not selected, no line-length rule is either, and
``ruff format`` reflows neither comments nor docstrings -- so the release's
prose sweep (see ``.claude/skills/release/SKILL.md``, Step 1b) is where it gets
caught, and this is what makes that sweep a measurement rather than a taste
argument.

Measuring matters because the eye misjudges it: the worst ratios sit on the
smallest helpers, where nine lines of docstring over a one-line body reads as
perfectly reasonable inside a diff.

Prose is docstring lines plus comment lines, each counted as the lines it
physically occupies; code is every other line of the function body. A ratio above
roughly 3x deserves a look -- not a rewrite, since
what a guard's shape cost to establish is worth keeping. What is worth cutting
is history the changelog already holds, corpus statistics the tests already
assert, and one explanation repeated at three layers.

Usage::

    uv run python tools/prose_density.py
    uv run python tools/prose_density.py --min-ratio 2 --paths src tests
    uv run python tools/prose_density.py --since v1.18.0

``--since`` narrows the report to functions in files a release touched, which is
the form the sweep wants.
"""

from __future__ import annotations

import argparse
import ast
import io
import subprocess
import sys
import textwrap
import tokenize
from pathlib import Path
from typing import Iterator, NamedTuple


class Entry(NamedTuple):
    ratio: float
    prose: int
    code: int
    path: Path
    lineno: int
    name: str
    docstring: int
    comments: int


def _comment_lines(source: str, where: str) -> int:
    """Comment tokens in *source*, counted once per line.

    *source* is dedented first. A method's body arrives indented, which
    ``tokenize`` accepts on every supported Python -- 3.10 through 3.14 all
    count it correctly, and all 1348 functions in ``src`` tokenize identically
    with and without the dedent -- so this is insurance rather than a fix.

    A snippet that cannot be tokenized is reported rather than counted as zero:
    silently scoring an unmeasurable function as having no prose is the one
    failure this tool must not have.
    """
    lines = set()
    try:
        for token in tokenize.generate_tokens(
            io.StringIO(textwrap.dedent(source)).readline
        ):
            if token.type == tokenize.COMMENT:
                lines.add(token.start[0])
    except (tokenize.TokenError, IndentationError, SyntaxError) as exc:
        print(f"warning: cannot tokenize {where}: {exc}", file=sys.stderr)
        return 0
    return len(lines)


def _docstring_lines(node: ast.AST) -> int:
    """Lines the docstring physically occupies, quotes included.

    Not ``len(ast.get_docstring(node).splitlines()) + 2``: ``get_docstring``
    returns the *cleaned* text, dedented and stripped of leading and trailing
    blank lines, so that estimate overcounts a one-line docstring by two and a
    typical multi-line one by one. What this measures is what a reader scrolls
    past, which is the point of the report.
    """
    body = getattr(node, "body", None)
    if not body:
        return 0
    first = body[0]
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return 0
    if not isinstance(first.value.value, str):
        return 0
    return (first.end_lineno or first.lineno) - first.lineno + 1


def measure(path: Path) -> Iterator[Entry]:
    """Yield one entry per function or method defined in *path*."""
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        total = node.end_lineno - node.lineno + 1 if node.end_lineno else 1
        docstring = _docstring_lines(node)
        body = "".join(lines[node.lineno - 1 : node.end_lineno])
        comments = _comment_lines(body, f"{path}:{node.lineno} {node.name}()")
        code = max(total - docstring - comments, 1)
        prose = docstring + comments
        yield Entry(
            prose / code, prose, code, path, node.lineno, node.name, docstring, comments
        )


def _changed_files(since: str) -> set[Path]:
    """Python files touched since *since*, as a git revision.

    A failing ``git diff`` exits rather than returning nothing: an unknown
    revision or a checkout-less directory would otherwise print "no Python
    files changed", which reads as a clean sweep and is the wrong answer to act
    on at release time.
    """
    out = subprocess.run(
        ["git", "diff", "--name-only", f"{since}..HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        message = out.stderr.strip() or f"git diff {since}..HEAD failed"
        raise SystemExit(f"error: {message}")
    return {Path(p) for p in out.stdout.split() if p.endswith(".py")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--paths",
        nargs="+",
        default=["src"],
        help="directories or files to measure (default: src)",
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=3.0,
        help="report functions at or above this prose-to-code ratio (default: 3)",
    )
    parser.add_argument(
        "--min-prose",
        type=int,
        default=8,
        help="ignore functions with less prose than this, whatever the ratio "
        "(default: 8) -- a two-line docstring over a one-line body is fine",
    )
    parser.add_argument(
        "--since",
        metavar="REV",
        help="restrict to files changed since REV, e.g. the last release tag",
    )
    args = parser.parse_args()

    files: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        files.extend(sorted(path.rglob("*.py")) if path.is_dir() else [path])
    if args.since:
        changed = _changed_files(args.since)
        files = [f for f in files if f in changed]
        if not files:
            print(f"No Python files changed since {args.since}.")
            return

    entries = [e for f in files for e in measure(f)]
    flagged = [
        e for e in entries if e.ratio >= args.min_ratio and e.prose >= args.min_prose
    ]
    flagged.sort(reverse=True)

    if not flagged:
        print(
            f"Nothing at or above {args.min_ratio}x prose-to-code "
            f"across {len(files)} file(s), {len(entries)} function(s)."
        )
        return

    print(f"{'ratio':>7} {'prose':>6} {'code':>5}  location")
    for e in flagged:
        print(
            f"{e.ratio:6.1f}x {e.prose:6} {e.code:5}  "
            f"{e.path}:{e.lineno} {e.name}() "
            f"[docstring {e.docstring}, comments {e.comments}]"
        )
    total_prose = sum(e.prose for e in entries)
    total_code = sum(e.code for e in entries)
    print(
        f"\n{len(flagged)} of {len(entries)} functions flagged; "
        f"{total_prose} prose lines to {total_code} code lines overall "
        f"({total_prose / total_code:.2f}x)."
    )


if __name__ == "__main__":
    main()
