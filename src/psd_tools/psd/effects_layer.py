"""
Effects layer structure.

Note the structures in this module is obsolete and object-based layer effects
are stored in tagged blocks.
"""
from __future__ import absolute_import, unicode_literals
import attr
import io
import logging
from collections import OrderedDict

from psd_tools.constants import BlendMode, EffectOSType
from psd_tools.psd.base import BaseElement, DictElement
from psd_tools.psd.color import Color
from psd_tools.validators import in_
from psd_tools.utils import (
    read_fmt, write_fmt, read_length_block, write_length_block, write_bytes,
    write_padding,
)

logger = logging.getLogger(__name__)


@attr.s(slots=True)
class CommonStateInfo(BaseElement):
    """
    Effects layer common state info.

    .. py:attribute:: version
    .. py:attribute:: visible
    """
    version = attr.ib(default=0, type=int)
    visible = attr.ib(default=1, type=int)

    @classmethod
    def read(cls, fp):
        return cls(*read_fmt('IB2x', fp))

    def write(self, fp):
        return write_fmt(fp, 'IB2x', *attr.astuple(self))


@attr.s(slots=True)
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
    version = attr.ib(default=0, type=int)
    blur = attr.ib(default=0, type=int)
    intensity = attr.ib(default=0, type=int)
    angle = attr.ib(default=0, type=int)
    distance = attr.ib(default=0, type=int)
    color = attr.ib(factory=Color)
    blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                         validator=in_(BlendMode))
    enabled = attr.ib(default=0, type=int)
    use_global_angle = attr.ib(default=0, type=int)
    opacity = attr.ib(default=0, type=int)
    native_color = attr.ib(factory=Color)

    @classmethod
    def read(cls, fp):
        # TODO: Check 4-byte = 2-byte int + 2-byte fraction?
        version, blur, intensity, angle, distance = read_fmt(
            'IIIiI', fp
        )
        color = Color.read(fp)
        signature = read_fmt('4s', fp)[0]
        assert signature == b'8BIM', 'Invalid signature %r' % (signature)
        blend_mode = BlendMode(read_fmt('4s', fp)[0])
        enabled, use_global_angle, opacity = read_fmt('3B', fp)
        native_color = Color.read(fp)
        return cls(
            version, blur, intensity, angle, distance, color, blend_mode,
            enabled, use_global_angle, opacity, native_color
        )

    def write(self, fp):
        written = write_fmt(
            fp, 'IIIiI', self.version, self.blur, self.intensity,
            self.angle, self.distance
        )
        written += self.color.write(fp)
        written += write_fmt(
            fp, '4s4s3B', b'8BIM', self.blend_mode.value, self.enabled,
            self.use_global_angle, self.opacity
        )
        written += self.native_color.write(fp)
        return written


class _GlowInfo(object):

    @classmethod
    def _read_body(cls, fp):
        # TODO: Check 4-byte = 2-byte int + 2-byte fraction?
        version, blur, intensity = read_fmt('III', fp)
        color = Color.read(fp)
        signature = read_fmt('4s', fp)[0]
        assert signature == b'8BIM', 'Invalid signature %r' % (signature)
        blend_mode = BlendMode(read_fmt('4s', fp)[0])
        enabled, opacity = read_fmt('2B', fp)
        return version, blur, intensity, color, blend_mode, enabled, opacity

    def _write_body(self, fp):
        written = write_fmt(fp, 'III', self.version, self.blur,
                            self.intensity)
        written += self.color.write(fp)
        written += write_fmt(
            fp, '4s4s2B', b'8BIM', self.blend_mode.value, self.enabled,
            self.opacity
        )
        return written


@attr.s(slots=True)
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
    version = attr.ib(default=0, type=int)
    blur = attr.ib(default=0, type=int)
    intensity = attr.ib(default=0, type=int)
    color = attr.ib(factory=Color)
    blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                         validator=in_(BlendMode))
    enabled = attr.ib(default=0, type=int)
    opacity = attr.ib(default=0, type=int)
    native_color = attr.ib(default=None)

    @classmethod
    def read(cls, fp):
        version, blur, intensity, color, blend_mode, enabled, opacity = (
            cls._read_body(fp)
        )
        native_color = None
        if version >= 2:
            native_color = Color.read(fp)
        return cls(
            version, blur, intensity, color, blend_mode, enabled, opacity,
            native_color
        )

    def write(self, fp):
        written = self._write_body(fp)
        if self.native_color:
            written += self.native_color.write(fp)
        return written


@attr.s(slots=True)
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
    version = attr.ib(default=0, type=int)
    blur = attr.ib(default=0, type=int)
    intensity = attr.ib(default=0, type=int)
    color = attr.ib(factory=Color)
    blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                         validator=in_(BlendMode))
    enabled = attr.ib(default=0, type=int)
    opacity = attr.ib(default=0, type=int)
    invert = attr.ib(default=None)
    native_color = attr.ib(default=None)

    @classmethod
    def read(cls, fp):
        version, blur, intensity, color, blend_mode, enabled, opacity = (
            cls._read_body(fp)
        )
        invert, native_color = None, None
        if version >= 2:
            invert = read_fmt('B', fp)[0]
            native_color = Color.read(fp)
        return cls(
            version, blur, intensity, color, blend_mode, enabled, opacity,
            invert, native_color
        )

    def write(self, fp):
        written = self._write_body(fp)
        if self.version >= 2:
            written += write_fmt(fp, 'B', self.invert)
            written += self.native_color.write(fp)
        return written


@attr.s(slots=True)
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
    version = attr.ib(default=0, type=int)
    angle = attr.ib(default=0, type=int)
    depth = attr.ib(default=0, type=int)
    blur = attr.ib(default=0, type=int)
    highlight_blend_mode = attr.ib(default=BlendMode.NORMAL,
                                   converter=BlendMode,
                                   validator=in_(BlendMode))
    shadow_blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                                validator=in_(BlendMode))
    highlight_color = attr.ib(factory=Color)
    shadow_color = attr.ib(factory=Color)
    bevel_style = attr.ib(default=0, type=int)
    highlight_opacity = attr.ib(default=0, type=int)
    shadow_opacity = attr.ib(default=0, type=int)
    enabled = attr.ib(default=0, type=int)
    use_global_angle = attr.ib(default=0, type=int)
    direction = attr.ib(default=0, type=int)
    real_highlight_color = attr.ib(default=None)
    real_shadow_color = attr.ib(default=None)

    @classmethod
    def read(cls, fp):
        # TODO: Check 4-byte = 2-byte int + 2-byte fraction?
        version, angle, depth, blur = read_fmt('Ii2I', fp)
        signature, highlight_blend_mode = read_fmt('4s4s', fp)
        assert signature == b'8BIM', 'Invalid signature %r' % (signature)
        signature, shadow_blend_mode = read_fmt('4s4s', fp)
        assert signature == b'8BIM', 'Invalid signature %r' % (signature)
        highlight_color = Color.read(fp)
        shadow_color = Color.read(fp)
        bevel_style, highlight_opacity, shadow_opacity = read_fmt('3B', fp)
        enabled, use_global_angle, direction = read_fmt('3B', fp)
        real_highlight_color, real_shadow_color = None, None
        if version == 2:
            real_highlight_color = Color.read(fp)
            real_shadow_color = Color.read(fp)
        return cls(
            version, angle, depth, blur, highlight_blend_mode,
            shadow_blend_mode, highlight_color, shadow_color, bevel_style,
            highlight_opacity, shadow_opacity, enabled, use_global_angle,
            direction, real_highlight_color, real_shadow_color
        )

    def write(self, fp):
        written = write_fmt(
            fp, 'Ii2I', self.version, self.angle, self.depth, self.blur
        )
        written += write_fmt(
            fp, '4s4s4s4s', b'8BIM', self.highlight_blend_mode.value, b'8BIM',
            self.shadow_blend_mode.value
        )
        written += self.highlight_color.write(fp)
        written += self.shadow_color.write(fp)
        written += write_fmt(
            fp, '6B', self.bevel_style, self.highlight_opacity,
            self.shadow_opacity, self.enabled, self.use_global_angle,
            self.direction
        )
        if self.version >= 2:
            written += self.highlight_color.write(fp)
            written += self.shadow_color.write(fp)
        return written


@attr.s(slots=True)
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
    version = attr.ib(default=2, type=int)
    blend_mode = attr.ib(default=BlendMode.NORMAL, converter=BlendMode,
                         validator=in_(BlendMode))
    color = attr.ib(factory=Color)
    opacity = attr.ib(default=0, type=int)
    enabled = attr.ib(default=0, type=int)
    native_color = attr.ib(factory=Color)

    @classmethod
    def read(cls, fp):
        version = read_fmt('I', fp)[0]
        signature, blend_mode = read_fmt('4s4s', fp)
        assert signature == b'8BIM', 'Invalid signature %r' % (signature)
        color = Color.read(fp)
        opacity, enabled = read_fmt('2B', fp)
        native_color = Color.read(fp)
        return cls(version, blend_mode, color, opacity, enabled, native_color)

    def write(self, fp):
        written = write_fmt(fp, 'I4s4s', self.version, b'8BIM',
                            self.blend_mode.value)
        written += self.color.write(fp)
        written += write_fmt(fp, '2B', self.opacity, self.enabled)
        written += self.native_color.write(fp)
        return written


@attr.s(slots=True)
class EffectsLayer(DictElement):
    """
    Dict-like EffectsLayer structure. See
    :py:class:`psd_tools.constants.EffectOSType` for available keys.

    .. py:attribute:: version
    """
    version = attr.ib(default=0, type=int)

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
    def read(cls, fp, **kwargs):
        version, count = read_fmt('2H', fp)
        items = []
        for _ in range(count):
            signature = read_fmt('4s', fp)[0]
            assert signature == b'8BIM', 'Invalid signature %r' % (signature)
            ostype = EffectOSType(read_fmt('4s', fp)[0])
            kls = cls.EFFECT_TYPES.get(ostype)
            items.append((ostype, kls.frombytes(read_length_block(fp))))
        return cls(version=version, items=items)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, '2H', self.version, len(self))
        for key in self:
            written += write_fmt(fp, '4s4s', b'8BIM', key.value)
            written += write_length_block(
                fp, lambda f: self[key].write(f)
            )
        written += write_padding(fp, written, 4)
        return written
