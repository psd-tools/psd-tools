# -*- coding: utf-8 -*-
"""
EngineData decoder.

PSD file embeds text formatting data in its own markup language referred
EngineData. The format looks like the following::

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
    ARRAY_END = re.compile(b'^\]$')
    ARRAY_START = re.compile(b'^\[$')
    BOOLEAN = re.compile(b'^(true|false)$')
    DICT_END = re.compile(b'^>>(\x00+)?$')
    DICT_START = re.compile(b'^<<$')
    NOOP = re.compile(b'^$')
    NUMBER = re.compile(b'^(-?\d+)$')
    NUMBER_WITH_DECIMAL = re.compile(b'^(-?\d*)\.(\d+)$')
    PROPERTY = re.compile(b'^\/([a-zA-Z0-9]+)$')
    STRING = re.compile(r'^\((\xfe\xff([^\)]|\\\)|\x00\))*)\)$'.encode(
        'utf-8'), re.M | re.DOTALL)
    # Unknown tags: b'(hwid)', b'(fwid)', b'(aalt)'
    UNKNOWN_TAG = re.compile(b'^\([a-zA-Z0-9]+\)$')


class EngineTokenizer(object):
    """
    Engine data tokenizer.
    """
    def __init__(self, divider):
        self.divider = re.compile(divider, re.M | re.DOTALL)

    def tokenize(self, data):
        current_token = None
        while len(data) > 0:
            match = self.divider.search(data)
            if match is None:
                token, data = data, b''
            elif data.startswith(b'(\xfe\xff'):
                for index in range(len(data)):
                    if data[index:index+1] != b')':
                        continue
                    if index > 0 and (
                            data[index-1:index+1] == b'\\)' or
                            data[index-1:index+1] == b'\x00)'):
                        continue
                    break
                token, data = data[:index+1], data[index+1:]
            else:
                token, data = data[:match.start()], data[match.end():]

            yield token


class EngineDataDecoder(object):
    """
    Engine data decoder.
    """
    _decoders, register = decoders.new_registry()

    def __init__(self, data, divider=b'[ \n\t]+'):
        self.node_stack = [{}]
        self.prop_stack = [b'Root']
        self.data = data
        self.tokenizer = EngineTokenizer(divider=divider)

    def parse(self):
        for token in self.tokenizer.tokenize(self.data):
            value = self._parse_token(token)

            if value is not None:
                if isinstance(self.node_stack[-1], list):
                    self.node_stack[-1].append(value)
                else:
                    self.node_stack[-1][self.prop_stack[-1]] = value

        return self.node_stack[0].get(b'Root', self.node_stack[0])

    def _parse_token(self, token):
        patterns = EngineToken._values_dict()
        for pattern in patterns:
            match = pattern.search(token)
            if match:
                return self._decoders[pattern](self, match)
        raise InvalidTokenError("Unknown token: {}".format(token))

    @register(EngineToken.ARRAY_END)
    def _decode_array_end(self, match):
        return self.node_stack.pop()

    @register(EngineToken.ARRAY_START)
    def _decode_array_start(self, match):
        self.node_stack.append([])

    @register(EngineToken.BOOLEAN)
    def _decode_boolean(self, match):
        return True if match.group(1) == b'true' else False

    @register(EngineToken.DICT_END)
    def _decode_dict_end(self, match):
        self.prop_stack.pop()
        return self.node_stack.pop()

    @register(EngineToken.DICT_START)
    def _decode_dict_start(self, match):
        self.prop_stack.append(None)
        self.node_stack.append({})

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
        self.prop_stack[-1] = match.group(1)

    @register(EngineToken.STRING)
    def _decode_string(self, match):
        # UTF-16 is backslash-escaped here.
        return re.sub(b'\\\\(.)', b'\\1', match.group(1)).decode(
            'utf-16', 'replace')

    @register(EngineToken.UNKNOWN_TAG)
    def _decode_unknown_tag(self, match):
        return match


def decode(data, **kwargs):
    """
    Decode EngineData.

    :param data: EngineData encoded in `bytes`
    :rtype: `dict`
    """
    try:
        decoder = EngineDataDecoder(data, **kwargs)
        return decoder.parse()
    except InvalidTokenError as e:
        warnings.warn("Failed to parse EngineData: %s" % e)
        return data
