"""
Effects layer structure.

Note the structures in this module is obsolete and object-based layer effects
are stored in tagged blocks.
"""

import logging
from typing import Any, BinaryIO, Optional, TypeVar

from attrs import define, field, astuple

from psd_tools.constants import BlendMode, EffectOSType
from psd_tools.psd.base import BaseElement, DictElement
from psd_tools.psd.color import Color
from psd_tools.psd.bin_utils import (
    read_fmt,
    read_length_block,
    write_fmt,
    write_length_block,
    write_padding,
)
from psd_tools.validators import in_

logger = logging.getLogger(__name__)

T_CommonStateInfo = TypeVar("T_CommonStateInfo", bound="CommonStateInfo")
T_ShadowInfo = TypeVar("T_ShadowInfo", bound="ShadowInfo")
T_OuterGlowInfo = TypeVar("T_OuterGlowInfo", bound="OuterGlowInfo")
T_InnerGlowInfo = TypeVar("T_InnerGlowInfo", bound="InnerGlowInfo")
T_BevelInfo = TypeVar("T_BevelInfo", bound="BevelInfo")
T_SolidFillInfo = TypeVar("T_SolidFillInfo", bound="SolidFillInfo")
T_EffectsLayer = TypeVar("T_EffectsLayer", bound="EffectsLayer")


@define(repr=False)
class CommonStateInfo(BaseElement):
    """
    Effects layer common state info.

    .. py:attribute:: version
    .. py:attribute:: visible
    """

    version: int = 0
    visible: int = 1

    @classmethod
    def read(
        cls: type[T_CommonStateInfo], fp: BinaryIO, **kwargs: Any
    ) -> T_CommonStateInfo:
        return cls(*read_fmt("IB2x", fp))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        return write_fmt(fp, "IB2x", *astuple(self))


@define(repr=False)
class ShadowInfo(BaseElement):
    """
    Effects layer shadow info.

    .. py:attribute:: version
    .. py:attribute:: blur
    .. py:attribute:: intensity
    .. py:attribute:: angle
    .. py:attribute:: distance
    .. py:attribute:: color
    .. py:attribute:: blend_mode
    .. py:attribute:: enabled
    .. py:attribute:: use_global_angle
    .. py:attribute:: opacity
    .. py:attribute:: native_color
    """

    version: int = 0
    blur: int = 0
    intensity: int = 0
    angle: int = 0
    distance: int = 0
    color: Color = field(factory=Color)
    blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    enabled: int = 0
    use_global_angle: int = 0
    opacity: int = 0
    native_color: Color = field(factory=Color)

    @classmethod
    def read(cls: type[T_ShadowInfo], fp: BinaryIO, **kwargs: Any) -> T_ShadowInfo:
        # TODO: Check 4-byte = 2-byte int + 2-byte fraction?
        version, blur, intensity, angle, distance = read_fmt("IIIiI", fp)
        color = Color.read(fp)
        signature = read_fmt("4s", fp)[0]
        assert signature == b"8BIM", "Invalid signature %r" % (signature)
        blend_mode = BlendMode(read_fmt("4s", fp)[0])
        enabled, use_global_angle, opacity = read_fmt("3B", fp)
        native_color = Color.read(fp)
        return cls(
            version=version,
            blur=blur,
            intensity=intensity,
            angle=angle,
            distance=distance,
            color=color,
            blend_mode=blend_mode,
            enabled=enabled,
            use_global_angle=use_global_angle,
            opacity=opacity,
            native_color=native_color,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(
            fp,
            "IIIiI",
            self.version,
            self.blur,
            self.intensity,
            self.angle,
            self.distance,
        )
        written += self.color.write(fp)
        written += write_fmt(
            fp,
            "4s4s3B",
            b"8BIM",
            self.blend_mode.value,
            self.enabled,
            self.use_global_angle,
            self.opacity,
        )
        written += self.native_color.write(fp)
        return written


class _GlowInfo:
    # Type hints for mixin attributes (defined in subclasses)
    version: int
    blur: int
    intensity: int
    color: Color
    blend_mode: BlendMode
    enabled: int
    opacity: int

    @classmethod
    def _read_body(
        cls, fp: BinaryIO
    ) -> tuple[int, int, int, Color, BlendMode, int, int]:
        # TODO: Check 4-byte = 2-byte int + 2-byte fraction?
        version, blur, intensity = read_fmt("III", fp)
        color = Color.read(fp)
        signature = read_fmt("4s", fp)[0]
        assert signature == b"8BIM", "Invalid signature %r" % (signature)
        blend_mode = BlendMode(read_fmt("4s", fp)[0])
        enabled, opacity = read_fmt("2B", fp)
        return version, blur, intensity, color, blend_mode, enabled, opacity

    def _write_body(self, fp: BinaryIO) -> int:
        written = write_fmt(fp, "III", self.version, self.blur, self.intensity)
        written += self.color.write(fp)
        written += write_fmt(
            fp, "4s4s2B", b"8BIM", self.blend_mode.value, self.enabled, self.opacity
        )
        return written


@define(repr=False)
class OuterGlowInfo(BaseElement, _GlowInfo):
    """
    Effects layer outer glow info.

    .. py:attribute:: version
    .. py:attribute:: blur
    .. py:attribute:: intensity
    .. py:attribute:: color
    .. py:attribute:: blend_mode
    .. py:attribute:: enabled
    .. py:attribute:: opacity
    .. py:attribute:: native_color
    """

    version: int = 0
    blur: int = 0
    intensity: int = 0
    color: Color = field(factory=Color)
    blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    enabled: int = 0
    opacity: int = 0
    native_color: object = None

    @classmethod
    def read(
        cls: type[T_OuterGlowInfo], fp: BinaryIO, **kwargs: Any
    ) -> T_OuterGlowInfo:
        version, blur, intensity, color, blend_mode, enabled, opacity = cls._read_body(
            fp
        )
        native_color = None
        if version >= 2:
            native_color = Color.read(fp)
        return cls(
            version=version,
            blur=blur,
            intensity=intensity,
            color=color,
            blend_mode=blend_mode,
            enabled=enabled,
            opacity=opacity,
            native_color=native_color,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = self._write_body(fp)
        if self.native_color and hasattr(self.native_color, "write"):
            written += self.native_color.write(fp)  # type: ignore[attr-defined]
        return written


@define(repr=False)
class InnerGlowInfo(BaseElement, _GlowInfo):
    """
    Effects layer inner glow info.

    .. py:attribute:: version
    .. py:attribute:: blur
    .. py:attribute:: intensity
    .. py:attribute:: color
    .. py:attribute:: blend_mode
    .. py:attribute:: enabled
    .. py:attribute:: opacity
    .. py:attribute:: invert
    .. py:attribute:: native_color
    """

    version: int = 0
    blur: int = 0
    intensity: int = 0
    color: Color = field(factory=Color)
    blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    enabled: int = 0
    opacity: int = 0
    invert: Optional[int] = None
    native_color: Optional[object] = None

    @classmethod
    def read(
        cls: type[T_InnerGlowInfo], fp: BinaryIO, **kwargs: Any
    ) -> T_InnerGlowInfo:
        version, blur, intensity, color, blend_mode, enabled, opacity = cls._read_body(
            fp
        )
        invert, native_color = None, None
        if version >= 2:
            invert = read_fmt("B", fp)[0]
            native_color = Color.read(fp)
        return cls(
            version=version,
            blur=blur,
            intensity=intensity,
            color=color,
            blend_mode=blend_mode,
            enabled=enabled,
            opacity=opacity,
            invert=invert,
            native_color=native_color,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = self._write_body(fp)
        if self.version >= 2:
            written += write_fmt(fp, "B", self.invert)
            if hasattr(self.native_color, "write"):
                written += self.native_color.write(fp)  # type: ignore[attr-defined]
        return written


@define(repr=False)
class BevelInfo(BaseElement):
    """
    Effects layer bevel info.

    .. py:attribute:: version
    .. py:attribute:: angle
    .. py:attribute:: depth
    .. py:attribute:: blur
    .. py:attribute:: highlight_blend_mode
    .. py:attribute:: shadow_blend_mode
    .. py:attribute:: highlight_color
    .. py:attribute:: shadow_color
    .. py:attribute:: highlight_opacity
    .. py:attribute:: shadow_opacity
    .. py:attribute:: enabled
    .. py:attribute:: use_global_angle
    .. py:attribute:: direction
    .. py:attribute:: real_hightlight_color
    .. py:attribute:: real_shadow_color
    """

    version: int = 0
    angle: int = 0
    depth: int = 0
    blur: int = 0
    highlight_blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    shadow_blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    highlight_color: Color = field(factory=Color)
    shadow_color: Color = field(factory=Color)
    bevel_style: int = 0
    highlight_opacity: int = 0
    shadow_opacity: int = 0
    enabled: int = 0
    use_global_angle: int = 0
    direction: int = 0
    real_highlight_color: object = None
    real_shadow_color: object = None

    @classmethod
    def read(cls: type[T_BevelInfo], fp: BinaryIO, **kwargs: Any) -> T_BevelInfo:
        # TODO: Check 4-byte = 2-byte int + 2-byte fraction?
        version, angle, depth, blur = read_fmt("Ii2I", fp)
        signature, highlight_blend_mode = read_fmt("4s4s", fp)
        assert signature == b"8BIM", "Invalid signature %r" % (signature)
        signature, shadow_blend_mode = read_fmt("4s4s", fp)
        assert signature == b"8BIM", "Invalid signature %r" % (signature)
        highlight_color = Color.read(fp)
        shadow_color = Color.read(fp)
        bevel_style, highlight_opacity, shadow_opacity = read_fmt("3B", fp)
        enabled, use_global_angle, direction = read_fmt("3B", fp)
        real_highlight_color, real_shadow_color = None, None
        if version == 2:
            real_highlight_color = Color.read(fp)
            real_shadow_color = Color.read(fp)
        return cls(
            version=version,
            angle=angle,
            depth=depth,
            blur=blur,
            highlight_blend_mode=highlight_blend_mode,
            shadow_blend_mode=shadow_blend_mode,
            highlight_color=highlight_color,
            shadow_color=shadow_color,
            bevel_style=bevel_style,
            highlight_opacity=highlight_opacity,
            shadow_opacity=shadow_opacity,
            enabled=enabled,
            use_global_angle=use_global_angle,
            direction=direction,
            real_highlight_color=real_highlight_color,
            real_shadow_color=real_shadow_color,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "Ii2I", self.version, self.angle, self.depth, self.blur)
        written += write_fmt(
            fp,
            "4s4s4s4s",
            b"8BIM",
            self.highlight_blend_mode.value,
            b"8BIM",
            self.shadow_blend_mode.value,
        )
        written += self.highlight_color.write(fp)
        written += self.shadow_color.write(fp)
        written += write_fmt(
            fp,
            "6B",
            self.bevel_style,
            self.highlight_opacity,
            self.shadow_opacity,
            self.enabled,
            self.use_global_angle,
            self.direction,
        )
        if self.version >= 2:
            written += self.highlight_color.write(fp)
            written += self.shadow_color.write(fp)
        return written


@define(repr=False)
class SolidFillInfo(BaseElement):
    """
    Effects layer inner glow info.

    .. py:attribute:: version
    .. py:attribute:: blend_mode
    .. py:attribute:: color
    .. py:attribute:: opacity
    .. py:attribute:: enabled
    .. py:attribute:: native_color
    """

    version: int = 2
    blend_mode: BlendMode = field(
        default=BlendMode.NORMAL, converter=BlendMode, validator=in_(BlendMode)
    )
    color: Color = field(factory=Color)
    opacity: int = 0
    enabled: int = 0
    native_color: Color = field(factory=Color)

    @classmethod
    def read(
        cls: type[T_SolidFillInfo], fp: BinaryIO, **kwargs: Any
    ) -> T_SolidFillInfo:
        version = read_fmt("I", fp)[0]
        signature, blend_mode = read_fmt("4s4s", fp)
        assert signature == b"8BIM", "Invalid signature %r" % (signature)
        color = Color.read(fp)
        opacity, enabled = read_fmt("2B", fp)
        native_color = Color.read(fp)
        return cls(
            version=version,
            blend_mode=blend_mode,
            color=color,
            opacity=opacity,
            enabled=enabled,
            native_color=native_color,
        )

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "I4s4s", self.version, b"8BIM", self.blend_mode.value)
        written += self.color.write(fp)
        written += write_fmt(fp, "2B", self.opacity, self.enabled)
        written += self.native_color.write(fp)
        return written


@define(repr=False)
class EffectsLayer(DictElement):
    """
    Dict-like EffectsLayer structure. See
    :py:class:`psd_tools.constants.EffectOSType` for available keys.

    .. py:attribute:: version
    """

    version: int = 0

    EFFECT_TYPES = {
        EffectOSType.COMMON_STATE: CommonStateInfo,
        EffectOSType.DROP_SHADOW: ShadowInfo,
        EffectOSType.INNER_SHADOW: ShadowInfo,
        EffectOSType.OUTER_GLOW: OuterGlowInfo,
        EffectOSType.INNER_GLOW: InnerGlowInfo,
        EffectOSType.BEVEL: BevelInfo,
        EffectOSType.SOLID_FILL: SolidFillInfo,
    }

    @classmethod
    def read(cls: type[T_EffectsLayer], fp: BinaryIO, **kwargs: Any) -> T_EffectsLayer:
        version, count = read_fmt("2H", fp)
        items = []
        for _ in range(count):
            signature = read_fmt("4s", fp)[0]
            assert signature == b"8BIM", "Invalid signature %r" % (signature)
            ostype = EffectOSType(read_fmt("4s", fp)[0])
            kls = cls.EFFECT_TYPES.get(ostype)
            assert kls is not None
            items.append((ostype, kls.frombytes(read_length_block(fp))))  # type: ignore[attr-defined]
        return cls(version=version, items=items)  # type: ignore[arg-type]

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        written = write_fmt(fp, "2H", self.version, len(self))
        for key in self:
            written += write_fmt(fp, "4s4s", b"8BIM", key.value)
            written += write_length_block(fp, self[key].write)
        written += write_padding(fp, written, 4)
        return written
