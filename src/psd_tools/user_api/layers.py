# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals, print_function, division
import warnings

from psd_tools.constants import TaggedBlock, SectionDivider
from psd_tools.engineData import getFontAndColorDic

def group_layers(decoded_data):
    """
    Returns a nested dict with PSD layer group information.
    """
    layer_records = decoded_data.layer_and_mask_data.layers.layer_records

    root = dict(layers = [])
    group_stack = [root]
    font_sizeTuple = None
    text_data = {}
     propDict = {'FontSet':'', 'Text':'', 'FontType':'', 'FontTypeA':'', 'FontSize':'', 'A':'', 'R':'', 'G':'', 'B':''}

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
                    layers = [],
                    closed = divider.type == SectionDivider.CLOSED_FOLDER,

                    blend_mode = blend_mode,
                    visible = visible,
                    opacity = opacity,
                            type_tool_object_setting = blocks.get(TaggedBlock.TYPE_TOOL_OBJECT_SETTING)
        
        
            
        
                    if (type_tool_object_setting != None):
                        textDataList = type_tool_object_setting.text_data.items
                        textDataTuple = [tup[1] for tup in textDataList]
                        
                        # text key
                        textKey = textDataTuple[0].value
                        
                        # to get the dict with font name and size
                        textDataTuplekey = [tup[1] for tup in textDataList]
                        textDataTuple.reverse()
                        TextDataTupleValue = textDataTuple[0].value
                        fontDetails = getFontAndColorDict(propDict, TextDataTupleValue)
                        propDict = {'FontSet':'', 'Text':'', 'FontType':'', 'FontTypeA':'', 'FontSize':'', 'A':'', 'R':'', 'G':'', 'B':''}
                        
                        textData = {'TextKey' : textKey,
                        			'textStyle' : fontDetails,
                        			}
                    else:
                        textData = None
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

            current_group['layers'].append(dict(
                id = layer_id,
                index = index,
                name = name,

                top = layer.top,
                left = layer.left,
                bottom = layer.bottom,
                right = layer.right,

                blend_mode = blend_mode,
                visible = visible,
                opacity = opacity,
                textData = textData,
            ))

    return root['layers']
