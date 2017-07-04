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
            blocks.get(TaggedBlock.NESTED_SECTION_DIVIDER_SETTING),
        )
        visible = layer.flags.visible
        opacity = layer.opacity
        blend_mode = layer.blend_mode

        if divider is not None:
            # group information
            if divider.type in [SectionDivider.CLOSED_FOLDER, SectionDivider.OPEN_FOLDER]:
                # group begins
                group = dict(
                    id = layer_id,
                    index = index,
                    name = name,
                    type = 'group',
                    layers = [],
                    closed = divider.type == SectionDivider.CLOSED_FOLDER,

                    blend_mode = blend_mode,
                    visible = visible,
                    opacity = opacity,
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

                    # group doesn't have coords:
                    for key in 'top', 'left', 'bottom', 'right':
                        if key in group:
                            del group[key]

                    group['layers'] = layers[1:]
                    group['closed'] = False

                    # replace moved layers with newly created group:
                    group_stack[0]['layers'] = [group]

                else:
                    finished_group = group_stack.pop()
                    assert finished_group is not root

            else:
                warnings.warn("invalid state")
        else:
            # layer with image
            sizeless = (layer.bottom - layer.top == 0) and (layer.right - layer.left == 0)
            if blocks.get(TaggedBlock.TYPE_TOOL_OBJECT_SETTING):
                layer_type = 'type'
            elif sizeless and blocks.get(TaggedBlock.VECTOR_ORIGINATION_DATA) and (
                    blocks.get(TaggedBlock.VECTOR_MASK_SETTING1,
                               blocks.get(TaggedBlock.VECTOR_MASK_SETTING2))):
                layer_type = 'shape'
            elif sizeless and any([TaggedBlock.is_adjustment_key(key) for key in blocks.keys()]):
                layer_type = 'adjustment'
            else:
                layer_type = 'pixel'

            current_group['layers'].append(dict(
                id = layer_id,
                index = index,
                name = name,
                type = layer_type,

                top = layer.top,
                left = layer.left,
                bottom = layer.bottom,
                right = layer.right,

                blend_mode = blend_mode,
                visible = visible,
                opacity = opacity,
            ))

    return root['layers']
