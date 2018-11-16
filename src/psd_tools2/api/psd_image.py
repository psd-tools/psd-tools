"""
PSD Image module.
"""
from __future__ import absolute_import, unicode_literals
import logging

from psd_tools2.constants import SectionDivider, Clipping
from psd_tools2.psd import PSD
from psd_tools2.api.layers import (
    AdjustmentLayer, Group, PixelLayer, ShapeLayer, SmartObjectLayer,
    TypeLayer
)


class PSDImage(Group):
    def __init__(self):
        super(PSDImage, self).__init__(None, None, None)
        self._psd = None

    @classmethod
    def new(cls, mode, size, color=0, **kwargs):
        """
        Create a new PSD document.

        :param mode: The color mode to use for the new image.
        :param size: A tuple containing (width, height) in pixels.
        :param color: What color to use for the image. Default is black.
        :return: A :py:class:`~psd_tools2.api.psd_image.PSDImage` object.
        """
        self = cls()
        self._psd = PSD.new(mode, size, color=color, **kwargs)
        return self

    @classmethod
    def open(cls, fp):
        """
        Open a PSD document.

        :param fp: filename or file-like object.
        :return: A :py:class:`~psd_tools2.api.psd_image.PSDImage` object.
        """
        self = cls()
        if hasattr(fp, 'read'):
            self._psd = PSD.read(fp)
        else:
            with open(fp, 'rb') as f:
                self._psd = PSD.read(f)
        self._init()
        return self

    def _init(self):
        group_stack = [self]
        clip_stack = []

        for record, channels in reversed(list(self._psd._iter_layers())):
            current_group = group_stack[-1]

            blocks = record.tagged_blocks
            divider = blocks.get('SECTION_DIVIDER_SETTING', None)
            divider = blocks.get('NESTED_SECTION_DIVIDER_SETTING', divider)
            if divider is not None:
                if divider.kind in (SectionDivider.OPEN_FOLDER,
                                    SectionDivider.CLOSED_FOLDER):
                    layer = Group(record, channels, current_group)
                    group_stack.append(layer)
                elif divider.kind == SectionDivider.BOUNDING_SECTION_DIVIDER:
                    layer = group_stack.pop()
                    assert layer is not self
                    continue
            elif 'TYPE_TOOL_OBJECT_SETTING' in blocks:
                layer = TypeLayer(record, channels, current_group)
            elif (
                record.flags.pixel_data_irrelevant and (
                    'VECTOR_ORIGINATION_DATA' in blocks or
                    'VECTOR_MASK_SETTING1' in blocks or
                    'VECTOR_MASK_SETTING2' in blocks or
                    'VECTOR_STROKE_DATA' in blocks or
                    'VECTOR_STROKE_CONTENT_DATA' in blocks
                )
            ):
                layer = ShapeLayer(record, channels, current_group)
            elif (
                'SMART_OBJECT_PLACED_LAYER_DATA' in blocks or
                'PLACED_LAYER_OBSOLETE2' in blocks or
                'PLACED_LAYER_DATA' in blocks
            ):
                layer = SmartObjectLayer(record, channels, current_group)
            elif (
                'BLACK_AND_WHITE' in blocks or
                'GRADIENT_FILL_SETTING' in blocks or
                'INVERT' in blocks or
                'PATTERN_FILL_SETTING' in blocks or
                'POSTERIZE' in blocks or
                'SOLID_COLOR_SHEET_SETTING' in blocks or
                'THRESHOLD' in blocks or
                'VIBRANCE' in blocks or
                'BRIGHTNESS_AND_CONTRAST' in blocks or
                'COLOR_BALANCE' in blocks or
                'COLOR_LOOKUP' in blocks or
                'CHANNEL_MIXER' in blocks or
                'CURVES' in blocks or
                'GRADIENT_MAP' in blocks or
                'EXPOSURE' in blocks or
                'HUE_SATURATION_V4' in blocks or
                'HUE_SATURATION' in blocks or
                'LEVELS' in blocks or
                'PHOTO_FILTER' in blocks or
                'SELECTIVE_COLOR' in blocks
            ):
                layer = AdjustmentLayer(record, channels, current_group)
            else:
                layer = PixelLayer(record, channels, current_group)

            if record.clipping == Clipping.NON_BASE:
                clip_stack.append(layer)
            else:
                layer._clip_layers = clip_stack
                clip_stack = []
                current_group._layers.append(layer)
