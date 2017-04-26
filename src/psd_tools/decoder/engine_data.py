# -*- coding: utf-8 -*-
"""
EngineData decoder.

PSD file embeds text formatting data in its own markup language referred
EngineData. The format looks like the following.

    <<
      /EngineDict
      <<
        /Editor
        <<
          /Text (˛ˇMake a change and save.)
        >>
      >>
      /Font
      <<
        /Name (˛ˇHelveticaNeue-Light)
        /FillColor
        <<
          /Type 1
          /Values [ 1.0 0.0 0.0 0.0 ]
        >>
        /StyleSheetSet [
        <<
          /Name (˛ˇNormal RGB)
        >>
        ]
      >>
    >>

"""

from __future__ import absolute_import
import re
import warnings
from psd_tools.decoder import decoders
from psd_tools.constants import Enum


class InvalidTokenError(ValueError):
    pass


class EngineToken(Enum):
    BOOLEAN = re.compile(b'^(true|false)$')
    DICT_END = re.compile(b'^>>$')
    DICT_START = re.compile(b'^<<$')
    MULTI_ARRAY_END = re.compile(b'^\]$')
    MULTI_ARRAY_START = re.compile(b'^\/(\w+) \[$')
    NOOP = re.compile(b'^$')
    NUMBER = re.compile(b'^(-?\d+)$')
    NUMBER_WITH_DECIMAL = re.compile(b'^(-?\d*)\.(\d+)$')
    PROPERTY = re.compile(b'^\/([a-zA-Z0-9]+)$')
    PROPERTY_WITH_DATA = re.compile(b'^\/([a-zA-Z0-9]+) (.*)$')
    SINGLE_LINE_ARRAY = re.compile(b'^\[(.*)\]$')
    STRING = re.compile(b'^\(\xfe\xff(.*)\)$')


class EngineDataDecoder(object):
    """
    Engine data decoder.
    """
    _decoders, register = decoders.new_registry()

    def __init__(self, data):
        self.node_stack = [{}]
        self.prop_stack = [b'Root']
        self.data = data
        self.prev_token = None

    def parse(self):
        # Actually split() is not perfect for non-ascii tokenization.
        tokens = list(map(lambda x: x.replace(b"\t", b""),
                          self.data.split(b"\n")))
        while len(tokens) > 0:
            token = tokens.pop(0)
            try:
                self._parse_token(token)
            except InvalidTokenError:
                if len(tokens) == 0:
                    raise ValueError('Unknown token: {}'.format(token))
                token += tokens.pop(0)
                self._parse_token(token, err=ValueError)
        return self.node_stack[0][b'Root']

    def _parse_token(self, token, err=InvalidTokenError):
        patterns = EngineToken._values_dict()
        for pattern in patterns:
            match = pattern.match(token)
            if match:
                return self._decoders[pattern](self, match)
        raise InvalidTokenError("Unknown token: {}".format(token))

    @register(EngineToken.BOOLEAN)
    def _decode_boolean(self, match):
        return True if match.group(1) == b'true' else False

    @register(EngineToken.DICT_END)
    def _decode_dict_end(self, match):
        self.prop_stack.pop()
        self.node_stack[-1][self.prop_stack[-1]] = self.node_stack.pop()

    @register(EngineToken.DICT_START)
    def _decode_dict_start(self, match):
        self.prop_stack.append(None)
        self.node_stack.append({})

    @register(EngineToken.MULTI_ARRAY_END)
    def _decode_multi_array_end(self, match):
        pass

    @register(EngineToken.MULTI_ARRAY_START)
    def _decode_multi_array_start(self, match):
        self.prop_stack[-1] = match.group(1)
        self.node_stack[-1][self.prop_stack[-1]] = []

    @register(EngineToken.NOOP)
    def _decode_noop(self, match):
        pass

    @register(EngineToken.NUMBER)
    def _decode_number(self, match):
        return int(match.group(1))

    @register(EngineToken.NUMBER_WITH_DECIMAL)
    def _decode_number_with_decimal(self, match):
        return float(match.group(0))

    @register(EngineToken.PROPERTY)
    def _decode_property(self, match):
        if isinstance(self.node_stack[-1], list):
            self.node_stack[-1].append(match.group(1))
        else:
            self.prop_stack[-1] = match.group(1)
            self.node_stack[-1][self.prop_stack[-1]] = None

    @register(EngineToken.PROPERTY_WITH_DATA)
    def _decode_property_with_data(self, match):
        if isinstance(self.node_stack[-1], list):
            self.node_stack[-1].append(self._parse_token(match.group(2)))
        else:
            self.prop_stack[-1] = match.group(1)
            self.node_stack[-1][self.prop_stack[-1]] = self._parse_token(
                match.group(2))

    @register(EngineToken.SINGLE_LINE_ARRAY)
    def _decode_single_line_array(self, match):
        items = []
        for token in match.group(1).split(b' '):
            items.append(self._parse_token(token))
        self.node_stack[-1][self.prop_stack[-1]] = items

    @register(EngineToken.STRING)
    def _decode_string(self, match):
        return match.group(1).decode('utf-16-be', 'ignore')


def decode(data):
    """
    Decode EngineData.
    """
    decoder = EngineDataDecoder(data)
    return decoder.parse()
