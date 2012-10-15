# -*- coding: utf-8 -*-
from __future__ import absolute_import

from . import image_resources

def decode(parse_result):

    parse_result = parse_result._replace(
        image_resource_blocks = image_resources.decode(parse_result.image_resource_blocks)
    )

    return parse_result
