# -*- coding: utf-8 -*-
"""
EngineData structure.

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
from __future__ import absolute_import, unicode_literals
import attr
from collections import OrderedDict
import codecs
import io
import logging
import re
from enum import Enum
from psd_tools.psd.base import (
    BooleanElement, DictElement, IntegerElement, ListElement, NumericElement,
    ValueElement
)
from psd_tools.utils import new_registry, trimmed_repr, write_bytes


logger = logging.getLogger(__name__)


TOKEN_CLASSES, register = new_registry()


def compile_re(pattern):
    return re.compile(pattern.encode('macroman'), re.S)


class EngineToken(Enum):
    ARRAY_END = compile_re(r'^\]$')
    ARRAY_START = compile_re(r'^\[$')
    BOOLEAN = compile_re(r'^(true|false)$')
    DICT_END = compile_re(r'^>>(\x00)*$')  # Buggy one?
    DICT_START = compile_re(r'^<<$')
    NOOP = compile_re(r'^$')
    NUMBER = compile_re(r'^-?\d+$')
    NUMBER_WITH_DECIMAL = compile_re(r'^-?\d*\.\d+$')
    PROPERTY = compile_re(r'^\/[a-zA-Z0-9]+$')
    STRING = compile_re(r'^\((\xfe\xff([^\)]|\\\))*)\)$')
    # Unknown tags: b'(hwid)', b'(fwid)', b'(aalt)'
    UNKNOWN_TAG = compile_re(r'^\([a-zA-Z0-9]+\)$')


class Tokenizer(object):
    """
    Tokenize engine data.

    Example::

        tokenizer = Tokenizer(data)
        for token, token_type in tokenizer:
            print('%s: %r' % (token_type.name, token))
    """
    DIVIDER = compile_re(r'[ \n\t]+')
    UTF16_START = b'(\xfe\xff'
    UTF16_END = compile_re(r'[^\\]\)')

    def __init__(self, data):
        self.data = data
        self.index = 0

    def __iter__(self):
        return self

    def __len__(self):
        return len(self.data) - self.index

    def next(self):
        return self.__next__()

    def __next__(self):
        if len(self) == 0:
            raise StopIteration

        index = self.index
        if self.data[index:].startswith(self.UTF16_START):
            match = self.UTF16_END.search(self.data[index:])
            if match is None:
                raise ValueError('Invalid token: %r' % (self.data[index:]))
            token = self.data[index:index + match.end()]
            self.index += match.end()
        else:
            match = self.DIVIDER.search(self.data[index:])
            if match is None:
                token = self.data[index:]
                self.index = len(self.data)
            else:
                token = self.data[index:index + match.start()]
                self.index += match.end()
                if token == b'':
                    return self.__next__()

        for token_type in EngineToken:
            if token_type.value.search(token):
                return token, token_type

        raise ValueError("Unknown token: %r" % (token))


@register(EngineToken.DICT_START)
class Dict(DictElement):
    """
    Dict-like element.
    """
    @classmethod
    def read(cls, fp, **kwargs):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data, **kwargs):
        tokenizer = data if isinstance(data, Tokenizer) else Tokenizer(data)
        self = cls()
        for k_token, k_token_type in tokenizer:
            if k_token_type == EngineToken.PROPERTY:
                key = Property.frombytes(k_token)
                v_token, v_token_type = next(tokenizer)
                kls = TOKEN_CLASSES.get(v_token_type)
                if v_token_type in (EngineToken.ARRAY_START,
                                    EngineToken.DICT_START):
                    value = kls.frombytes(tokenizer)
                elif kls:
                    value = kls.frombytes(v_token)
                else:
                    raise ValueError('Invalid token: %r' % (v_token))
                self[key] = value
            elif k_token_type == EngineToken.DICT_END:
                return self
        return self

    def write(self, fp, indent=0, write_container=True):
        inner_indent = indent if indent is None else indent + 1
        written = 0
        if write_container:
            if indent == 0:
                written += self._write_newline(fp, indent)
            written += self._write_newline(fp, indent)
            written += self._write_indent(fp, indent)
            written += write_bytes(fp, b'<<')
            written += self._write_newline(fp, indent)

        for key in self:
            written += self._write_indent(fp, inner_indent)
            written += key.write(fp)
            value = self[key]
            if isinstance(value, Dict):
                written += value.write(fp, indent=inner_indent)
            else:
                written += write_bytes(fp, b' ')
                if isinstance(value, List):
                    if len(value) > 0 and isinstance(value[0], Dict):
                        written += value.write(fp, indent=inner_indent)
                    else:
                        written += value.write(fp, indent=None)
                else:
                    written += value.write(fp)
            written += self._write_newline(fp, indent)

        if write_container:
            written += self._write_indent(fp, indent)
            written += write_bytes(fp, b'>>')
        return written

    def _write_indent(self, fp, indent, default=b' '):
        if indent is None:
            return write_bytes(fp, default)
        return write_bytes(fp, b'\t' * (indent))

    def _write_newline(self, fp, indent):
        if indent is None:
            return 0
        return write_bytes(fp, b'\n')

    def __getitem__(self, key):
        key = key if isinstance(key, Property) else Property(key)
        return super(Dict, self).__getitem__(key)

    def __setitem__(self, key, value):
        key = key if isinstance(key, Property) else Property(key)
        super(Dict, self).__setitem__(key, value)

    def __detitem__(self, key):
        key = key if isinstance(key, Property) else Property(key)
        super(Dict, self).__delitem__(key)

    def __contains__(self, key):
        key = key if isinstance(key, Property) else Property(key)
        return self._items.__contains__(key)

    def get(self, key, *args):
        key = key if isinstance(key, Property) else Property(key)
        return super(Dict, self).get(key, *args)


class EngineData(Dict):
    """
    Dict-like element.

    TYPE_TOOL_OBJECT_SETTING tagged block contains this object in its
    descriptor.
    """
    pass


class EngineData2(Dict):
    """
    Dict-like element.

    TEXT_ENGINE_DATA tagged block has this object.
    """
    def write(self, fp, indent=None, write_container=False, **kwargs):
        return super(EngineData2, self).write(
            fp, indent=indent, write_container=write_container
        )


@register(EngineToken.ARRAY_START)
class List(ListElement):
    """
    List-like element.
    """
    @classmethod
    def read(cls, fp):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data):
        tokenizer = data if isinstance(data, Tokenizer) else Tokenizer(data)
        self = cls()
        for token, token_type in tokenizer:
            if token_type == EngineToken.ARRAY_END:
                return self

            kls = TOKEN_CLASSES.get(token_type)
            if token_type in (EngineToken.ARRAY_START,
                              EngineToken.DICT_START):
                value = kls.frombytes(tokenizer)
            else:
                value = kls.frombytes(token)
            self.append(value)

        return self

    def write(self, fp, indent=None):
        written = write_bytes(fp, b'[')
        if indent is None:
            for item in self:
                if isinstance(item, Dict):
                    written += item.write(fp, indent=None)
                else:
                    written += write_bytes(fp, b' ')
                    written += item.write(fp)
            written += write_bytes(fp, b' ')
        else:
            for item in self:
                written += item.write(fp, indent=indent)
            written += self._write_newline(fp, indent)
            written += self._write_indent(fp, indent)
        written += write_bytes(fp, b']')
        return written

    def _write_indent(self, fp, indent):
        if indent is None:
            return write_bytes(fp, b' ')
        return write_bytes(fp, b'\t' * (indent))

    def _write_newline(self, fp, indent):
        if indent is None:
            return 0
        return write_bytes(fp, b'\n')


@register(EngineToken.STRING)
class String(ValueElement):
    """
    String element.
    """
    _ESCAPED_CHARS = (b'\\', b'(', b')')

    @classmethod
    def read(cls, fp):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data):
        value = data[1:-1]
        for c in cls._ESCAPED_CHARS:
            value = value.replace(b'\\' + c, c)
        return cls(value.decode('utf-16'))

    def write(self, fp):
        value = self.value.encode('utf-16-be')
        for c in self._ESCAPED_CHARS:
            value = value.replace(c, b'\\' + c)
        return write_bytes(fp, b'(' + codecs.BOM_UTF16_BE + value + b')')


@register(EngineToken.BOOLEAN)
class Bool(BooleanElement):
    """
    Bool element.
    """
    @classmethod
    def read(cls, fp):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data):
        return cls(data == b'true')

    def write(self, fp, indent=0):
        return write_bytes(fp, b'true' if self.value else b'false')


@register(EngineToken.NUMBER)
class Integer(IntegerElement):
    """
    Integer element.
    """
    @classmethod
    def read(cls, fp):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data):
        return cls(int(data))

    def write(self, fp, indent=0):
        return write_bytes(fp, b'%d' % (self.value))


@register(EngineToken.NUMBER_WITH_DECIMAL)
class Float(NumericElement):
    """
    Float element.
    """
    @classmethod
    def read(cls, fp):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data):
        return cls(float(data))

    def write(self, fp):
        value = b'%.8f' % (self.value)
        value = value.rstrip(b'0')
        value = value + b'0' if value.endswith(b'.') else value
        if 0.0 < abs(self.value) and abs(self.value) < 1.0:
            value = value.replace(b'0.', b'.')
        return write_bytes(fp, value)


@register(EngineToken.PROPERTY)
@attr.s(repr=False, frozen=True, cmp=False)
class Property(ValueElement):
    """
    Property element.
    """
    @classmethod
    def read(cls, fp):
        return cls.frombytes(fp.read())

    @classmethod
    def frombytes(cls, data):
        return cls(data.replace(b'/', b'').decode('macroman'))

    def write(self, fp):
        return write_bytes(fp, b'/' + self.value.encode('macroman'))


@register(EngineToken.UNKNOWN_TAG)
class Tag(ValueElement):
    """
    Tag element.
    """
    @classmethod
    def read(cls, fp):
        return cls(fp.read())

    def write(self, fp):
        return write_bytes(fp, self.value)
