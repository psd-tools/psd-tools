"""Tests for ``tools/prose_density.py``.

The tool exists to make the release's prose sweep a measurement rather than an
argument, so a wrong count is worse than no tool: the first version overstated
every single-expression function by roughly 2x, because it derived the docstring
size from ``ast.get_docstring()`` -- the *cleaned* text -- and added a flat two
for the quote lines. That inflated the prose count and, since code is the
remainder, deflated the divisor at the same time. It put
``get_color_channels()`` at 40:1 where the file says 19.5:1, and those numbers
were quoted in a PR and an issue before anyone checked them.
"""

import importlib.util
import subprocess
from pathlib import Path
from typing import Any

import pytest

_TOOL = Path(__file__).resolve().parents[1] / "tools" / "prose_density.py"
_spec = importlib.util.spec_from_file_location("prose_density", _TOOL)
assert _spec is not None and _spec.loader is not None
prose_density = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prose_density)


def _measure(tmp_path: Path, source: str) -> dict[str, Any]:
    path = tmp_path / "sample.py"
    path.write_text(source)
    return {e.name: e for e in prose_density.measure(path)}


def test_one_line_docstring_counts_one_line(tmp_path: Path) -> None:
    """``\"\"\"x\"\"\"`` occupies one line, not three."""
    entries = _measure(tmp_path, 'def f():\n    """x"""\n    return 1\n')
    assert entries["f"].docstring == 1
    assert entries["f"].code == 2  # the def line and the return


def test_multiline_docstring_counts_its_physical_span(tmp_path: Path) -> None:
    """Including the quote lines, and including blank lines inside it."""
    source = 'def f():\n    """Summary.\n\n    Body.\n    """\n    return 1\n'
    assert _measure(tmp_path, source)["f"].docstring == 4


def test_trailing_blank_lines_in_a_docstring_are_counted(tmp_path: Path) -> None:
    """``get_docstring()`` strips these; a reader still scrolls past them."""
    source = 'def f():\n    """Summary.\n\n\n    """\n    return 1\n'
    assert _measure(tmp_path, source)["f"].docstring == 4


def test_function_without_a_docstring_counts_none(tmp_path: Path) -> None:
    entries = _measure(tmp_path, "def f():\n    return 1\n")
    assert entries["f"].docstring == 0
    assert entries["f"].prose == 0


def test_a_string_expression_that_is_not_a_docstring_is_not_counted(
    tmp_path: Path,
) -> None:
    """Only the *first* statement is a docstring."""
    source = 'def f():\n    x = 1\n    "not a docstring"\n    return x\n'
    assert _measure(tmp_path, source)["f"].docstring == 0


def test_comments_in_an_indented_method_are_counted(tmp_path: Path) -> None:
    """A method body arrives indented; the count must survive that.

    ``tokenize`` accepts a leading-indented snippet on every supported Python
    (3.10 through 3.14 all count it correctly, and all 1348 functions in ``src``
    tokenize identically with and without a dedent), but the tool dedents first
    so the result cannot depend on that.
    """
    source = (
        "class C:\n"
        "    def m(self):\n"
        '        """Doc."""\n'
        "        # one\n"
        "        # two\n"
        "        return 1  # trailing, same line as code\n"
    )
    entry = _measure(tmp_path, source)["m"]
    assert entry.comments == 3
    assert entry.docstring == 1


def test_multiple_comment_tokens_on_one_line_count_once(tmp_path: Path) -> None:
    """The unit is lines a reader scrolls past, not tokens."""
    source = "def f():\n    return 1  # a\n"
    assert _measure(tmp_path, source)["f"].comments == 1


def test_ratio_uses_the_remaining_lines_as_code(tmp_path: Path) -> None:
    source = 'def f():\n    """x"""\n    # c\n    return 1\n'
    entry = _measure(tmp_path, source)
    assert entry["f"].prose == 2  # one docstring line, one comment
    assert entry["f"].code == 2  # def and return
    assert entry["f"].ratio == 1.0


def test_unparsable_file_yields_nothing(tmp_path: Path) -> None:
    """A syntax error is skipped rather than crashing a release-time sweep."""
    path = tmp_path / "broken.py"
    path.write_text("def f(:\n")
    assert list(prose_density.measure(path)) == []


def test_untokenizable_body_warns_instead_of_scoring_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Silently counting an unmeasurable function as prose-free is the one
    failure this tool must not have."""

    def boom(readline: Any) -> Any:
        raise SyntaxError("synthetic")

    monkeypatch.setattr(prose_density.tokenize, "generate_tokens", boom)
    assert prose_density._comment_lines("# c\n", "somewhere.py:1 f()") == 0
    assert "cannot tokenize somewhere.py:1 f()" in capsys.readouterr().err


def test_since_with_a_bad_revision_exits(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failing ``git diff`` must not read as "nothing changed"."""

    def fail(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(args, 128, "", "fatal: unknown revision")

    monkeypatch.setattr(prose_density.subprocess, "run", fail)
    with pytest.raises(SystemExit, match="fatal: unknown revision"):
        prose_density._changed_files("no-such-rev")


def test_the_tool_measures_itself(tmp_path: Path) -> None:
    """An end-to-end sanity check against a real file with real docstrings."""
    entries = {e.name: e for e in prose_density.measure(_TOOL)}
    assert entries  # the module defines functions
    assert all(e.code >= 1 for e in entries.values())
    assert entries["_docstring_lines"].docstring > 5
