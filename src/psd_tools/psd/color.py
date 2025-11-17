"""
Color structure and conversion methods.
"""

import logging
from typing import Any, BinaryIO, TypeVar

from attrs import define, field

from psd_tools.constants import ColorSpaceID
from psd_tools.psd.base import BaseElement
from psd_tools.psd.bin_utils import read_fmt, write_fmt

logger = logging.getLogger(__name__)

T = TypeVar("T", bound="Color")


@define(repr=False)
class Color(BaseElement):
    """
    Color structure.

    .. py:attribute:: id

        See :py:class:`~psd_tools.constants.ColorSpaceID`.

    .. py:attribute:: values

        List of `int` values.
    """

    id: ColorSpaceID = ColorSpaceID.RGB
    values: list = field(factory=lambda: [0, 0, 0, 0])

    @classmethod
    def read(cls: type[T], fp: BinaryIO, **kwargs: Any) -> T:
        id = read_fmt("H", fp)[0]
        try:
            id = ColorSpaceID(id)
        except ValueError:
            logger.info("Custom color space found: %d" % (id))
        if id == ColorSpaceID.LAB:
            values = read_fmt("4h", fp)
        else:
            values = read_fmt("4H", fp)
        return cls(id, list(values))

    def write(self, fp: BinaryIO, **kwargs: Any) -> int:
        id = getattr(self.id, "value", self.id)
        written = write_fmt(fp, "H", id)
        if self.id == ColorSpaceID.LAB:
            written += write_fmt(fp, "4h", *self.values)
        else:
            written += write_fmt(fp, "4H", *self.values)
        return written

    def _repr_pretty_(self, p: Any, cycle: bool) -> None:
        if cycle:
            p.text("{name}(...)".format(name=self.__class__.__name__))
            return

        name = getattr(self.id, "name", self.id)
        with p.group(2, "{name}(".format(name=name), ")"):
            p.breakable("")
            for idx, value in enumerate(self.values):
                if idx:
                    p.text(",")
                    p.breakable()
                p.pretty(value)
            p.breakable("")
