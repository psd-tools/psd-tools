"""Tests for the typesetting module."""

import pytest

from psd_tools.api.layers import TypeLayer
from psd_tools.api.psd_image import PSDImage
from psd_tools.api.typesetting import (
    CharacterStyle,
    FontInfo,
    Paragraph,
    ParagraphStyle,
    TextRun,
    TypeSetting,
)
from psd_tools.constants import FontBaseline, FontCaps, Justification


def full_name(name: str) -> str:
    return f"tests/psd_files/{name}"


@pytest.fixture
def type_layer() -> TypeLayer:
    return PSDImage.open(full_name("layers/type-layer.psd"))[0]  # type: ignore[return-value]


@pytest.fixture
def text_layer() -> TypeLayer:
    """Multi-paragraph text layer."""
    psd = PSDImage.open(full_name("text.psd"))
    for layer in psd.descendants():
        if layer.kind == "type":
            return layer  # type: ignore[return-value]
    raise RuntimeError("No type layer found in text.psd")


class TestTypeSetting:
    def test_construction(self, type_layer: TypeLayer) -> None:
        ts = type_layer.typesetting
        assert isinstance(ts, TypeSetting)

    def test_text(self, type_layer: TypeLayer) -> None:
        assert type_layer.typesetting.text == "A"

    def test_fonts(self, type_layer: TypeLayer) -> None:
        fonts = type_layer.typesetting.fonts
        assert len(fonts) > 0
        assert all(isinstance(f, FontInfo) for f in fonts)

    def test_fonts_excludes_unused(self, type_layer: TypeLayer) -> None:
        ts = type_layer.typesetting
        used_names = {f.postscript_name for f in ts.fonts}
        all_names = {f.postscript_name for f in ts.all_fonts}
        assert "AdobeInvisFont" not in used_names
        assert "AdobeInvisFont" in all_names
        assert len(ts.fonts) < len(ts.all_fonts)

    def test_all_fonts(self, type_layer: TypeLayer) -> None:
        all_fonts = type_layer.typesetting.all_fonts
        assert len(all_fonts) >= 2
        assert all(isinstance(f, FontInfo) for f in all_fonts)

    def test_font_postscript_name(self, type_layer: TypeLayer) -> None:
        fonts = type_layer.typesetting.fonts
        assert fonts[0].postscript_name == "ArialMT"

    def test_font_info_properties(self, type_layer: TypeLayer) -> None:
        font = type_layer.typesetting.fonts[0]
        assert font.index == 0
        assert isinstance(font.font_type, int)
        assert isinstance(font.synthetic, bool)
        assert isinstance(font.family, str)
        assert isinstance(font.style, str)

    def test_default_style(self, type_layer: TypeLayer) -> None:
        ds = type_layer.typesetting.default_style
        assert isinstance(ds, CharacterStyle)
        assert ds.font_size > 0

    def test_default_paragraph_style(self, type_layer: TypeLayer) -> None:
        dps = type_layer.typesetting.default_paragraph_style
        assert isinstance(dps, ParagraphStyle)
        assert isinstance(dps.justification, Justification)

    def test_runs(self, type_layer: TypeLayer) -> None:
        runs = type_layer.typesetting.runs
        assert len(runs) >= 1
        assert all(isinstance(r, TextRun) for r in runs)
        assert runs[0].text == "A"

    def test_paragraphs(self, type_layer: TypeLayer) -> None:
        paragraphs = type_layer.typesetting.paragraphs
        assert len(paragraphs) >= 1
        assert all(isinstance(p, Paragraph) for p in paragraphs)

    def test_iter(self, type_layer: TypeLayer) -> None:
        ts = type_layer.typesetting
        paragraphs = list(ts)
        assert len(paragraphs) == len(ts)

    def test_len(self, type_layer: TypeLayer) -> None:
        assert len(type_layer.typesetting) >= 1

    def test_getitem(self, type_layer: TypeLayer) -> None:
        ts = type_layer.typesetting
        assert ts[0] is ts.paragraphs[0]

    def test_writing_direction(self, type_layer: TypeLayer) -> None:
        # May or may not be available
        wd = type_layer.typesetting.writing_direction
        assert wd is None or hasattr(wd, "value")

    def test_repr(self, type_layer: TypeLayer) -> None:
        r = repr(type_layer.typesetting)
        assert "TypeSetting" in r


class TestMultiParagraph:
    def test_paragraph_count(self, text_layer: TypeLayer) -> None:
        ts = text_layer.typesetting
        assert len(ts.paragraphs) == 3

    def test_paragraph_text(self, text_layer: TypeLayer) -> None:
        ts = text_layer.typesetting
        texts = [p.text for p in ts]
        assert texts[0] == "Line 1\r"
        assert texts[1] == "Line 2\r"
        assert texts[2] == "Line 3 and text"

    def test_paragraph_runs(self, text_layer: TypeLayer) -> None:
        for paragraph in text_layer.typesetting:
            assert len(paragraph.runs) >= 1
            assert len(paragraph) == len(paragraph.runs)

    def test_paragraph_iter(self, text_layer: TypeLayer) -> None:
        for paragraph in text_layer.typesetting:
            runs = list(paragraph)
            assert len(runs) == len(paragraph.runs)

    def test_paragraph_positions(self, text_layer: TypeLayer) -> None:
        ts = text_layer.typesetting
        for paragraph in ts:
            assert paragraph.start >= 0
            assert paragraph.end > paragraph.start
            assert paragraph.text == ts.text[paragraph.start : paragraph.end]


class TestCharacterStyle:
    def test_font_size(self, type_layer: TypeLayer) -> None:
        run = type_layer.typesetting.runs[0]
        assert run.style.font_size == 30.0

    def test_font_name(self, type_layer: TypeLayer) -> None:
        run = type_layer.typesetting.runs[0]
        assert run.style.font_name == "ArialMT"

    def test_font(self, type_layer: TypeLayer) -> None:
        run = type_layer.typesetting.runs[0]
        font = run.style.font
        assert font is not None
        assert isinstance(font, FontInfo)
        assert font.postscript_name == "ArialMT"

    def test_fill_color(self, type_layer: TypeLayer) -> None:
        run = type_layer.typesetting.runs[0]
        color = run.style.fill_color
        assert color is not None
        assert len(color) == 4  # ARGB

    def test_boolean_properties(self, type_layer: TypeLayer) -> None:
        style = type_layer.typesetting.runs[0].style
        assert isinstance(style.faux_bold, bool)
        assert isinstance(style.faux_italic, bool)
        assert isinstance(style.underline, bool)
        assert isinstance(style.strikethrough, bool)
        assert isinstance(style.ligatures, bool)
        assert isinstance(style.no_break, bool)

    def test_enum_properties(self, type_layer: TypeLayer) -> None:
        style = type_layer.typesetting.runs[0].style
        assert isinstance(style.font_caps, FontCaps)
        assert isinstance(style.font_baseline, FontBaseline)

    def test_numeric_properties(self, type_layer: TypeLayer) -> None:
        style = type_layer.typesetting.runs[0].style
        assert isinstance(style.tracking, int)
        assert isinstance(style.kerning, int)
        assert isinstance(style.baseline_shift, float)
        assert isinstance(style.horizontal_scale, float)
        assert isinstance(style.vertical_scale, float)
        assert isinstance(style.tsume, float)
        assert isinstance(style.leading, float)

    def test_repr(self, type_layer: TypeLayer) -> None:
        r = repr(type_layer.typesetting.runs[0].style)
        assert "CharacterStyle" in r


class TestParagraphStyle:
    def test_justification(self, text_layer: TypeLayer) -> None:
        for paragraph in text_layer.typesetting:
            assert isinstance(paragraph.style.justification, Justification)

    def test_indent_properties(self, text_layer: TypeLayer) -> None:
        style = text_layer.typesetting.paragraphs[0].style
        assert isinstance(style.first_line_indent, float)
        assert isinstance(style.start_indent, float)
        assert isinstance(style.end_indent, float)

    def test_spacing_properties(self, text_layer: TypeLayer) -> None:
        style = text_layer.typesetting.paragraphs[0].style
        assert isinstance(style.space_before, float)
        assert isinstance(style.space_after, float)
        assert isinstance(style.auto_leading, float)

    def test_word_spacing(self, text_layer: TypeLayer) -> None:
        ws = text_layer.typesetting.paragraphs[0].style.word_spacing
        assert len(ws) == 3

    def test_letter_spacing(self, text_layer: TypeLayer) -> None:
        ls = text_layer.typesetting.paragraphs[0].style.letter_spacing
        assert len(ls) == 3

    def test_glyph_spacing(self, text_layer: TypeLayer) -> None:
        gs = text_layer.typesetting.paragraphs[0].style.glyph_spacing
        assert len(gs) == 3

    def test_repr(self, text_layer: TypeLayer) -> None:
        r = repr(text_layer.typesetting.paragraphs[0].style)
        assert "ParagraphStyle" in r


class TestTextRun:
    def test_properties(self, type_layer: TypeLayer) -> None:
        run = type_layer.typesetting.runs[0]
        assert run.text == "A"
        assert run.start == 0
        assert run.end == 1
        assert run.length == 1
        assert isinstance(run.style, CharacterStyle)

    def test_repr(self, type_layer: TypeLayer) -> None:
        r = repr(type_layer.typesetting.runs[0])
        assert "TextRun" in r


class TestTypeLayerIntegration:
    def test_font_names(self, type_layer: TypeLayer) -> None:
        names = type_layer.font_names
        assert "ArialMT" in names

    def test_typesetting_cached(self, type_layer: TypeLayer) -> None:
        ts1 = type_layer.typesetting
        ts2 = type_layer.typesetting
        assert ts1 is ts2

    def test_engine_dict_still_works(self, type_layer: TypeLayer) -> None:
        """Ensure existing API is not broken."""
        assert type_layer.engine_dict
        assert type_layer.resource_dict
        assert type_layer.document_resources
        assert type_layer.text == "A"
