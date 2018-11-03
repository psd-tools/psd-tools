"""
Color structure and conversion methods.
"""
from __future__ import absolute_import, unicode_literals
import attr
import logging

from psd_tools2.decoder.base import BaseElement
from psd_tools2.constants import ColorSpaceID
from psd_tools2.validators import in_
from psd_tools2.utils import read_fmt, write_fmt

logger = logging.getLogger(__name__)


@attr.s
class Color(BaseElement):
    """
    Color structure.

    .. py:attribute:: id

        See :py:class:`~psd_tools2.constants.ColorSpaceID`.

    .. py:attribute:: values

        List of int values.
    """
    id = attr.ib(default=ColorSpaceID.RGB, converter=ColorSpaceID,
                 validator=in_(ColorSpaceID))
    values = attr.ib(factory=lambda: (0, 0, 0, 0))

    @classmethod
    def read(cls, fp, **kwargs):
        id = ColorSpaceID(read_fmt('H', fp)[0])
        if id == ColorSpaceID.LAB:
            values = read_fmt('4h', fp)
        else:
            values = read_fmt('4H', fp)
        return cls(id, values)

    def write(self, fp, **kwargs):
        written = write_fmt(fp, 'H', self.id.value)
        if self.id == ColorSpaceID.LAB:
            written += write_fmt(fp, '4h', *self.values)
        else:
            written += write_fmt(fp, '4H', *self.values)
        return written

    def _repr_pretty_(self, p, cycle):
        if cycle:
            return "{name}(...)".format(name=self.__class__.__name__)

        with p.group(2, '{name}('.format(name=self.id.name), ')'):
            p.breakable('')
            for idx, value in enumerate(self.values):
                if idx:
                    p.text(',')
                    p.breakable()
                p.pretty(value)
            p.breakable('')
