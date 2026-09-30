"""
Typesetting module for structured access to text layer data.

This module provides high-level, read-only access to typographic data
from :py:class:`~psd_tools.api.layers.TypeLayer` objects. It wraps the
raw ``engine_dict`` and ``resource_dict`` structures in typed Python
classes with documented properties.

The main entry point is :py:class:`TypeSetting`, obtained via
:py:attr:`TypeLayer.typesetting <psd_tools.api.layers.TypeLayer.typesetting>`.

Example::

    from psd_tools import PSDImage

    psd = PSDImage.open('design.psd')
    for layer in psd.descendants():
        if layer.kind == 'type':
            for paragraph in layer.typesetting:
                print(paragraph.style.justification)
                for run in paragraph:
                    s = run.style
                    print(f"'{run.text}': {s.font_name} {s.font_size}pt")
"""

from __future__ import annotations

import bisect
import logging
from itertools import groupby
from typing import Any, Iterator, TypeVar, overload

from enum import IntEnum

from psd_tools.api._descriptor import coerce_scalar, get_scalar
from psd_tools.constants import FontBaseline, FontCaps, Justification, WritingDirection
from psd_tools.psd import engine_data

logger = logging.getLogger(__name__)


_S = TypeVar("_S", int, float, bool, str)
_Style = engine_data.Dict | dict[str, Any] | None


def _safe_enum(
    enum_cls: type[IntEnum], value: int, default: IntEnum | None = None
) -> Any:
    """Convert a value to an IntEnum member, returning *default* on failure."""
    try:
        return enum_cls(value)
    except (ValueError, KeyError):
        logger.debug("Unknown %s value: %r", enum_cls.__name__, value)
        return default


def _raw(data: _Style, default: _Style, key: str) -> Any:
    """The first non-None entry for *key* in the run data, then the default style."""
    for layer in (data, default):
        value = layer.get(key) if layer else None
        if value is not None:
            return value
    return None


@overload
def _scalar(
    data: _Style, default: _Style, key: str, type_: type[_S], fallback: None
) -> _S | None: ...
@overload
def _scalar(
    data: _Style, default: _Style, key: str, type_: type[_S], fallback: _S
) -> _S: ...
def _scalar(
    data: _Style, default: _Style, key: str, type_: type[_S], fallback: _S | None
) -> _S | None:
    """Read *key* as a plain *type_*, from the run data and then the default style."""
    for layer in (data, default):
        value = get_scalar(layer, key, type_, None)
        if value is not None:
            return value
    return fallback


def _triple(
    raw: Any, default: tuple[float, float, float]
) -> tuple[float, float, float]:
    """Read a (min, desired, max) list, each missing or unreadable part defaulting."""
    try:
        items = list(raw)
    except TypeError:
        return default
    items += [None] * (3 - len(items))
    return (
        coerce_scalar(items[0], float, default[0]),
        coerce_scalar(items[1], float, default[1]),
        coerce_scalar(items[2], float, default[2]),
    )


def _color_tuple(color_data: Any) -> tuple[float, ...] | None:
    """Extract color values from an engine_data color dict.

    Returns an ARGB tuple of floats, or None if color_data is None.
    """
    if color_data is None:
        return None
    values = color_data.get("Values")
    if values is None:
        return None
    parts = tuple(coerce_scalar(v, float, None, "Values") for v in values)
    if None in parts:
        return None
    return parts  # type: ignore[return-value]


class FontInfo:
    """
    Information about a font used in a text layer.

    Wraps an entry from the engine data ``FontSet`` array.

    Example::

        for font in layer.typesetting.fonts:
            print(font.postscript_name, font.family, font.style)
    """

    def __init__(self, index: int, data: engine_data.Dict) -> None:
        self._index = index
        self._data = data

    @property
    def index(self) -> int:
        """Index in the font set."""
        return self._index

    @property
    def postscript_name(self) -> str:
        """PostScript name of the font."""
        return get_scalar(self._data, "Name", str, "")

    @property
    def family(self) -> str:
        """Font family name, or empty string if unavailable."""
        return get_scalar(self._data, "FontFamily", str, "")

    @property
    def style(self) -> str:
        """Font style (e.g. 'Bold', 'Italic'), or empty string."""
        return get_scalar(self._data, "FontStyle", str, "")

    @property
    def font_type(self) -> int:
        """Font type identifier."""
        return get_scalar(self._data, "FontType", int, 0)

    @property
    def synthetic(self) -> bool:
        """Whether the font is synthetic."""
        return get_scalar(self._data, "Synthetic", bool, False)

    def __repr__(self) -> str:
        return (
            f"FontInfo(index={self._index}, postscript_name={self.postscript_name!r})"
        )


class CharacterStyle:
    """
    Character-level styling properties for a text run.

    Properties correspond to Photoshop's character panel settings.
    Values are merged with the layer's default style; run-specific
    values override defaults.
    """

    def __init__(
        self,
        data: engine_data.Dict | dict[str, Any],
        fonts: tuple[FontInfo, ...],
        default: engine_data.Dict | dict[str, Any] | None = None,
    ) -> None:
        self._data = data
        self._fonts = fonts
        self._default = default

    @property
    def font(self) -> FontInfo | None:
        """The :py:class:`FontInfo` object for this run's font."""
        idx = _scalar(self._data, self._default, "Font", int, None)
        if idx is not None and 0 <= idx < len(self._fonts):
            return self._fonts[idx]
        return None

    @property
    def font_name(self) -> str:
        """PostScript name of the font. Shortcut for ``font.postscript_name``."""
        f = self.font
        return f.postscript_name if f else ""

    @property
    def font_size(self) -> float:
        """Font size in points."""
        return _scalar(self._data, self._default, "FontSize", float, 12.0)

    @property
    def fill_color(self) -> tuple[float, ...] | None:
        """Fill color as an ARGB tuple of floats (values 0-1).

        Returns None if no fill color is set.
        """
        color = self._data.get("FillColor") if self._data else None
        if color is None and self._default:
            color = self._default.get("FillColor")
        return _color_tuple(color)

    @property
    def stroke_color(self) -> tuple[float, ...] | None:
        """Stroke color as an ARGB tuple of floats (values 0-1).

        Returns None if no stroke color is set.
        """
        color = self._data.get("StrokeColor") if self._data else None
        if color is None and self._default:
            color = self._default.get("StrokeColor")
        return _color_tuple(color)

    @property
    def fill_flag(self) -> bool:
        """Whether fill is enabled."""
        return _scalar(self._data, self._default, "FillFlag", bool, True)

    @property
    def stroke_flag(self) -> bool:
        """Whether stroke is enabled."""
        return _scalar(self._data, self._default, "StrokeFlag", bool, False)

    @property
    def faux_bold(self) -> bool:
        """Whether faux bold is enabled."""
        return _scalar(self._data, self._default, "FauxBold", bool, False)

    @property
    def faux_italic(self) -> bool:
        """Whether faux italic is enabled."""
        return _scalar(self._data, self._default, "FauxItalic", bool, False)

    @property
    def underline(self) -> bool:
        """Whether underline is enabled."""
        return _scalar(self._data, self._default, "Underline", bool, False)

    @property
    def strikethrough(self) -> bool:
        """Whether strikethrough is enabled."""
        return _scalar(self._data, self._default, "Strikethrough", bool, False)

    @property
    def ligatures(self) -> bool:
        """Whether ligatures are enabled."""
        return _scalar(self._data, self._default, "Ligatures", bool, True)

    @property
    def font_caps(self) -> FontCaps:
        """Font capitalization style."""
        return _safe_enum(
            FontCaps,
            _scalar(self._data, self._default, "FontCaps", int, 0),
            FontCaps.NORMAL,
        )

    @property
    def font_baseline(self) -> FontBaseline:
        """Font baseline position."""
        return _safe_enum(
            FontBaseline,
            _scalar(self._data, self._default, "FontBaseline", int, 0),
            FontBaseline.NORMAL,
        )

    @property
    def tracking(self) -> int:
        """Tracking (letter spacing adjustment)."""
        return _scalar(self._data, self._default, "Tracking", int, 0)

    @property
    def auto_kerning(self) -> bool:
        """Whether auto kerning is enabled."""
        return _scalar(self._data, self._default, "AutoKern", bool, True)

    @property
    def kerning(self) -> int:
        """Manual kerning value."""
        return _scalar(self._data, self._default, "Kerning", int, 0)

    @property
    def baseline_shift(self) -> float:
        """Baseline shift in points."""
        return _scalar(self._data, self._default, "BaselineShift", float, 0.0)

    @property
    def horizontal_scale(self) -> float:
        """Horizontal scale (1.0 = 100%)."""
        return _scalar(self._data, self._default, "HorizontalScale", float, 1.0)

    @property
    def vertical_scale(self) -> float:
        """Vertical scale (1.0 = 100%)."""
        return _scalar(self._data, self._default, "VerticalScale", float, 1.0)

    @property
    def auto_leading(self) -> bool:
        """Whether auto leading is enabled."""
        return _scalar(self._data, self._default, "AutoLeading", bool, True)

    @property
    def leading(self) -> float:
        """Leading (line spacing) value."""
        return _scalar(self._data, self._default, "Leading", float, 0.0)

    @property
    def no_break(self) -> bool:
        """Whether no-break is enabled."""
        return _scalar(self._data, self._default, "NoBreak", bool, False)

    @property
    def tsume(self) -> float:
        """Tsume value for CJK character tightening (0.0-1.0)."""
        return _scalar(self._data, self._default, "Tsume", float, 0.0)

    @property
    def language(self) -> int:
        """Language identifier."""
        return _scalar(self._data, self._default, "Language", int, 0)

    def __repr__(self) -> str:
        return (
            f"CharacterStyle(font_name={self.font_name!r}, font_size={self.font_size})"
        )


class ParagraphStyle:
    """
    Paragraph-level styling properties.

    Properties correspond to Photoshop's paragraph panel settings.
    Values are merged with the layer's default paragraph style.
    """

    def __init__(
        self,
        data: engine_data.Dict | dict[str, Any],
        default: engine_data.Dict | dict[str, Any] | None = None,
    ) -> None:
        self._data = data
        self._default = default

    @property
    def justification(self) -> Justification:
        """Text justification / alignment."""
        return _safe_enum(
            Justification,
            _scalar(self._data, self._default, "Justification", int, 0),
            Justification.LEFT,
        )

    @property
    def first_line_indent(self) -> float:
        """First line indent in points."""
        return _scalar(self._data, self._default, "FirstLineIndent", float, 0.0)

    @property
    def start_indent(self) -> float:
        """Start (left) indent in points."""
        return _scalar(self._data, self._default, "StartIndent", float, 0.0)

    @property
    def end_indent(self) -> float:
        """End (right) indent in points."""
        return _scalar(self._data, self._default, "EndIndent", float, 0.0)

    @property
    def space_before(self) -> float:
        """Space before paragraph in points."""
        return _scalar(self._data, self._default, "SpaceBefore", float, 0.0)

    @property
    def space_after(self) -> float:
        """Space after paragraph in points."""
        return _scalar(self._data, self._default, "SpaceAfter", float, 0.0)

    @property
    def auto_hyphenate(self) -> bool:
        """Whether auto-hyphenation is enabled."""
        return _scalar(self._data, self._default, "AutoHyphenate", bool, False)

    @property
    def auto_leading(self) -> float:
        """Auto leading scale (typically 1.2)."""
        return _scalar(self._data, self._default, "AutoLeading", float, 1.2)

    @property
    def leading_type(self) -> int:
        """Leading type identifier."""
        return _scalar(self._data, self._default, "LeadingType", int, 0)

    @property
    def word_spacing(self) -> tuple[float, float, float]:
        """Word spacing as (min, desired, max)."""
        return _triple(_raw(self._data, self._default, "WordSpacing"), (1.0, 1.0, 2.0))

    @property
    def letter_spacing(self) -> tuple[float, float, float]:
        """Letter spacing as (min, desired, max)."""
        return _triple(
            _raw(self._data, self._default, "LetterSpacing"), (0.0, 0.0, 0.05)
        )

    @property
    def glyph_spacing(self) -> tuple[float, float, float]:
        """Glyph spacing as (min, desired, max)."""
        return _triple(_raw(self._data, self._default, "GlyphSpacing"), (1.0, 1.0, 1.0))

    @property
    def every_line_composer(self) -> bool:
        """Whether Adobe multi-line composer is enabled."""
        return _scalar(self._data, self._default, "EveryLineComposer", bool, False)

    def __repr__(self) -> str:
        return f"ParagraphStyle(justification={self.justification.name})"


class TextRun:
    """
    A contiguous range of text with uniform character styling.

    Example::

        for run in layer.typesetting.runs:
            print(f"'{run.text}': {run.style.font_name} {run.style.font_size}pt")
    """

    def __init__(
        self,
        text: str,
        start: int,
        end: int,
        style: CharacterStyle,
    ) -> None:
        self._text = text
        self._start = start
        self._end = end
        self._style = style

    @property
    def text(self) -> str:
        """The text content of this run."""
        return self._text

    @property
    def start(self) -> int:
        """Start character index (inclusive)."""
        return self._start

    @property
    def end(self) -> int:
        """End character index (exclusive)."""
        return self._end

    @property
    def length(self) -> int:
        """Number of characters in this run."""
        return self._end - self._start

    @property
    def style(self) -> CharacterStyle:
        """Character styling for this run."""
        return self._style

    def __repr__(self) -> str:
        return f"TextRun({self._text!r}, {self._style!r})"


class Paragraph:
    r"""
    A paragraph of text containing one or more styled runs.

    Paragraphs are delimited by carriage return characters (``\r``)
    in Photoshop's text model.

    Example::

        for paragraph in layer.typesetting:
            print(paragraph.style.justification.name)
            for run in paragraph:
                print(f"  '{run.text}' in {run.style.font_name}")
    """

    def __init__(
        self,
        text: str,
        start: int,
        end: int,
        style: ParagraphStyle,
        runs: tuple[TextRun, ...],
    ) -> None:
        self._text = text
        self._start = start
        self._end = end
        self._style = style
        self._runs = runs

    @property
    def text(self) -> str:
        """The full text of this paragraph."""
        return self._text

    @property
    def start(self) -> int:
        """Start character index."""
        return self._start

    @property
    def end(self) -> int:
        """End character index."""
        return self._end

    @property
    def style(self) -> ParagraphStyle:
        """Paragraph-level style."""
        return self._style

    @property
    def runs(self) -> tuple[TextRun, ...]:
        """The styled text runs in this paragraph."""
        return self._runs

    def __iter__(self) -> Iterator[TextRun]:
        return iter(self._runs)

    def __len__(self) -> int:
        return len(self._runs)

    def __repr__(self) -> str:
        return f"Paragraph({self._text!r}, runs={len(self._runs)})"


class _RunLengthIndex:
    """Map character indices to run indices using a run length array.

    Example::

        rli = _RunLengthIndex([4, 2, 5])
        rli(0)  # -> 0
        rli(3)  # -> 0
        rli(4)  # -> 1
        rli(6)  # -> 2
    """

    def __init__(self, run_length_array: list[Any]) -> None:
        self._boundaries: list[int] = []
        cumulative = 0
        for length in run_length_array:
            cumulative += coerce_scalar(length, int, 0, "RunLengthArray")
            self._boundaries.append(cumulative)

    @property
    def boundaries(self) -> list[int]:
        """Cumulative boundary positions."""
        return self._boundaries

    def __call__(self, index: int) -> int:
        """Get the run index for the given character index."""
        i = bisect.bisect_right(self._boundaries, index)
        return min(i, max(0, len(self._boundaries) - 1))


class TypeSetting:
    """
    Structured typographic data for a text layer.

    Provides access to paragraphs, style runs, font information,
    and default styles without navigating raw engine data dicts.

    Obtain via :py:attr:`TypeLayer.typesetting
    <psd_tools.api.layers.TypeLayer.typesetting>`.

    Example::

        ts = layer.typesetting

        # Iterate paragraphs and their styled runs
        for paragraph in ts:
            print(paragraph.style.justification)
            for run in paragraph.runs:
                print(run.text, run.style.font_name, run.style.font_size)

        # Get all fonts used
        for font in ts.fonts:
            print(font.postscript_name, font.family)
    """

    def __init__(
        self,
        text: str,
        engine_dict: engine_data.Dict,
        resource_dict: engine_data.Dict,
    ) -> None:
        self._text = text
        self._engine_dict = engine_dict
        self._resource_dict = resource_dict
        self._build()
        del self._engine_dict, self._resource_dict

    def _build(self) -> None:
        self._fonts = self._build_fonts()
        default_char_data, default_para_data = self._build_default_styles()
        self._runs = self._build_runs(default_char_data)
        self._paragraphs = self._build_paragraphs(default_char_data, default_para_data)
        self._used_fonts = self._collect_used_fonts()
        self._writing_direction = self._parse_writing_direction()

    def _build_fonts(self) -> tuple[FontInfo, ...]:
        font_set_data = self._resource_dict.get("FontSet")
        if not font_set_data:
            return ()
        return tuple(FontInfo(i, font_set_data[i]) for i in range(len(font_set_data)))

    def _build_default_styles(
        self,
    ) -> tuple[engine_data.Dict | dict[str, Any], engine_data.Dict | dict[str, Any]]:
        """Build default character and paragraph styles.

        Returns (default_char_data, default_para_data) for use by run builders.
        """
        # Character default: resolve via StyleSheetSet + TheNormalStyleSheet index
        style_sheet_set = self._resource_dict.get("StyleSheetSet")
        normal_ss_index = self._resource_dict.get("TheNormalStyleSheet")
        idx = coerce_scalar(normal_ss_index, int, None, "TheNormalStyleSheet")
        if style_sheet_set and idx is not None:
            if 0 <= idx < len(style_sheet_set):
                default_char_data = style_sheet_set[idx].get("StyleSheetData", {})
            else:
                default_char_data = {}
        else:
            default_char_data = {}
        self._default_style = CharacterStyle(default_char_data, self._fonts)

        # Paragraph default: resolve via ParagraphSheetSet + TheNormalParagraphSheet
        para_sheet_set = self._resource_dict.get("ParagraphSheetSet")
        normal_ps_index = self._resource_dict.get("TheNormalParagraphSheet")
        idx = coerce_scalar(normal_ps_index, int, None, "TheNormalParagraphSheet")
        if para_sheet_set and idx is not None:
            if 0 <= idx < len(para_sheet_set):
                default_para_data = para_sheet_set[idx].get("Properties", {})
            else:
                default_para_data = {}
        else:
            default_para_data = {}
        self._default_paragraph_style = ParagraphStyle(default_para_data)

        return default_char_data, default_para_data

    def _build_runs(
        self, default_char_data: engine_data.Dict | dict[str, Any]
    ) -> tuple[TextRun, ...]:
        text = self._text
        style_run = self._engine_dict.get("StyleRun", {})
        run_lengths = style_run.get("RunLengthArray", [])
        run_array = style_run.get("RunArray", [])

        if not run_lengths:
            # No style run data; synthesize a single run with default style
            if not text:
                return ()
            style = CharacterStyle({}, self._fonts, default_char_data)
            return (TextRun(text, 0, len(text), style),)

        runs: list[TextRun] = []
        pos = 0
        for i in range(len(run_lengths)):
            length = coerce_scalar(run_lengths[i], int, 0, "RunLengthArray")
            end = pos + length
            if pos >= len(text):
                break
            end = min(end, len(text))
            run_data = run_array[i] if i < len(run_array) else {}
            ss = run_data.get("StyleSheet", {}) if run_data else {}
            ss_data = ss.get("StyleSheetData", {}) if ss else {}
            style = CharacterStyle(ss_data, self._fonts, default_char_data)
            runs.append(TextRun(text[pos:end], pos, end, style))
            pos = end
        return tuple(runs)

    def _build_paragraphs(
        self,
        default_char_data: engine_data.Dict | dict[str, Any],
        default_para_data: engine_data.Dict | dict[str, Any],
    ) -> tuple[Paragraph, ...]:
        text = self._text
        style_run = self._engine_dict.get("StyleRun", {})
        run_lengths = style_run.get("RunLengthArray", [])
        run_array = style_run.get("RunArray", [])

        para_run = self._engine_dict.get("ParagraphRun", {})
        para_lengths = para_run.get("RunLengthArray", [])
        para_array = para_run.get("RunArray", [])

        if not (para_lengths and para_array):
            if not text:
                return ()
            return (
                Paragraph(
                    text,
                    0,
                    len(text),
                    self._default_paragraph_style,
                    self._runs,
                ),
            )

        # Use RunLengthIndex approach to group style runs into paragraphs
        para_index = _RunLengthIndex(para_lengths)
        style_index = (
            _RunLengthIndex(run_lengths)
            if run_lengths
            else _RunLengthIndex([len(text)])
        )

        stops = sorted(set(para_index.boundaries) | set(style_index.boundaries))
        stops = sorted(
            {min(s, len(text)) for s in stops if s > 0}
            | ({len(text)} if text else set())
        )

        paragraphs: list[Paragraph] = []
        pairs = list(zip([0] + stops, stops))

        for idx, group in groupby(pairs, key=lambda pair: para_index(pair[0])):
            group_list = list(group)
            para_start = group_list[0][0]
            para_end = group_list[-1][1]

            # Get paragraph style with default merging
            pd = para_array[idx] if idx < len(para_array) else {}
            ps = pd.get("ParagraphSheet", {}) if pd else {}
            ps_props = ps.get("Properties", {}) if ps else {}
            para_style = ParagraphStyle(ps_props, default_para_data)

            # Collect style runs for this paragraph
            para_runs: list[TextRun] = []
            for start, stop in group_list:
                if start >= len(text):
                    break
                stop = min(stop, len(text))
                si = style_index(start)
                rd = run_array[si] if si < len(run_array) else {}
                ss = rd.get("StyleSheet", {}) if rd else {}
                ss_data = ss.get("StyleSheetData", {}) if ss else {}
                cs = CharacterStyle(ss_data, self._fonts, default_char_data)
                para_runs.append(TextRun(text[start:stop], start, stop, cs))

            paragraphs.append(
                Paragraph(
                    text[para_start:para_end],
                    para_start,
                    para_end,
                    para_style,
                    tuple(para_runs),
                )
            )
        return tuple(paragraphs)

    def _collect_used_fonts(self) -> tuple[FontInfo, ...]:
        used_indices: set[int] = set()
        for run in self._runs:
            font = run.style.font
            if font is not None:
                used_indices.add(font.index)
        return tuple(f for f in self._fonts if f.index in used_indices)

    def _parse_writing_direction(self) -> WritingDirection | None:
        rendered = self._engine_dict.get("Rendered", {})
        shapes = rendered.get("Shapes", {}) if rendered else {}
        wd = get_scalar(shapes, "WritingDirection", int, None)
        return None if wd is None else _safe_enum(WritingDirection, wd, None)

    @property
    def text(self) -> str:
        """Full text content."""
        return self._text

    @property
    def fonts(self) -> tuple[FontInfo, ...]:
        """Fonts actually used by text runs in this layer.

        To access the full font set (including unused entries like
        ``AdobeInvisFont``), use :py:attr:`all_fonts`.
        """
        return self._used_fonts

    @property
    def all_fonts(self) -> tuple[FontInfo, ...]:
        """All fonts in the font set, including unused entries."""
        return self._fonts

    @property
    def default_style(self) -> CharacterStyle:
        """The default character style sheet."""
        return self._default_style

    @property
    def default_paragraph_style(self) -> ParagraphStyle:
        """The default paragraph style sheet."""
        return self._default_paragraph_style

    @property
    def paragraphs(self) -> tuple[Paragraph, ...]:
        """All paragraphs with their runs."""
        return self._paragraphs

    @property
    def runs(self) -> tuple[TextRun, ...]:
        """All styled text runs (flat, across paragraphs)."""
        return self._runs

    @property
    def writing_direction(self) -> WritingDirection | None:
        """Writing direction, or None if unavailable."""
        return self._writing_direction

    def __iter__(self) -> Iterator[Paragraph]:
        return iter(self._paragraphs)

    def __len__(self) -> int:
        return len(self._paragraphs)

    def __getitem__(self, index: int) -> Paragraph:
        return self._paragraphs[index]

    def __repr__(self) -> str:
        return (
            f"TypeSetting(text={self._text!r}, "
            f"paragraphs={len(self._paragraphs)}, "
            f"fonts={len(self._fonts)})"
        )
