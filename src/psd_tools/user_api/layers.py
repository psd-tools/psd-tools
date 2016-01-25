# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function, division
import warnings

from psd_tools.constants import TaggedBlock, SectionDivider


def group_layers(decoded_data):
    """
    Returns a nested dict with PSD layer group information.
    """
    layer_records = decoded_data.layer_and_mask_data.layers.layer_records

    root = dict(layers = [])
    group_stack = [root]

    for index, layer in reversed(list(enumerate(layer_records))):
        current_group = group_stack[-1]

        blocks = dict(layer.tagged_blocks)

        name = blocks.get(TaggedBlock.UNICODE_LAYER_NAME, layer.name)
        layer_id = blocks.get(TaggedBlock.LAYER_ID)
        divider = blocks.get(
            TaggedBlock.SECTION_DIVIDER_SETTING,
            blocks.get(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING)
        )
        blend_mode = layer.blend_mode
        opacity = layer.opacity
        visible = layer.flags.visible

        if divider is not None:
            # group information
            if divider.type in (SectionDivider.CLOSED_FOLDER, SectionDivider.OPEN_FOLDER):
                # group begins
                if divider.blend_mode is not None:
                    blend_mode = divider.blend_mode

                group = dict(
                    index = index,
                    id = layer_id,
                    name = name,

                    blend_mode = blend_mode,
                    opacity = opacity,
                    visible = visible,

                    closed = divider.type == SectionDivider.CLOSED_FOLDER,
                    layers = []
                )
                group_stack.append(group)
                current_group['layers'].append(group)

            elif divider.type == SectionDivider.BOUNDING_SECTION_DIVIDER:
                # group ends
                if len(group_stack) == 1:
                    # This means that there is a BOUNDING_SECTION_DIVIDER
                    # without an OPEN_FOLDER before it. Create a new group
                    # and move layers to this new group in this case.

                    # Assume the first layer is a group
                    # and convert it to a group:
                    layers = group_stack[0]['layers']
                    group = layers[0]

                    # group doesn't have coords and fill:
                    for key in ('top', 'left', 'bottom', 'right', 'fill'):
                        if key in group:
                            del group[key]

                    group['closed'] = False
                    group['layers'] = layers[1:]

                    # replace moved layers with newly created group:
                    group_stack[0]['layers'] = [group]

                else:
                    finished_group = group_stack.pop()
                    assert finished_group is not root

            else:
                warnings.warn("invalid state")
        else:
            # layer with image
            fill = blocks.get(TaggedBlock.FILL_OPACITY, 255)

            current_group['layers'].append(dict(
                index = index,
                id = layer_id,
                name = name,

                blend_mode = blend_mode,
                opacity = opacity,
                fill = fill,
                visible = visible,

                left = layer.left,
                top = layer.top,
                right = layer.right,
                bottom = layer.bottom
            ))

    return root['layers']
