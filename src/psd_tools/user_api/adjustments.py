# -*- coding: utf-8 -*-
"""Adjustment API."""
from __future__ import absolute_import
import inspect
import logging
from psd_tools.constants import TaggedBlock
from psd_tools.decoder.actions import UnitFloat
import psd_tools.user_api.actions

logger = logging.getLogger(__name__)


class _Descriptor(object):
    """Base class for effect."""
    def __init__(self, descriptor):
        self._descriptor = descriptor

    def get(self, key, default=None):
        """Get attribute in the low-level structure.

        :param key: property key
        :type key: bytes
        :param default: default value to return
        """
        return self._descriptor.get(key, default)

    def dict(self):
        """Convert to dict."""
        return {k: getattr(self, k) for k in self.properties()}

    def __repr__(self):
        return "<%s>" % (self.__class__.__name__.lower(),)



class BrightnessContrast(_Descriptor):
    """Brightness and contrast adjustment."""

    @property
    def brightness(self):
        return self.get(b'Brgh', 0)

    @property
    def contrast(self):
        return self.get(b'Cntr', 0)

    @property
    def mean(self):
        return self.get(b'means', 0)

    @property
    def lab(self):
        return self.get(b'Lab ', False)

    @property
    def use_legacy(self):
        return self.get(b'useLegacy', False)

    @property
    def vrsn(self):
        return self.get(b'Vrsn', 1)

    @property
    def automatic(self):
        return self.get(b'auto', False)


class Levels(object):
    """
    Levels adjustment.

    Levels contain a list of
    :py:class:`~psd_tools.decoder.tagged_blocks.LevelRecord`.
    """
    def __init__(self, levels):
        self._levels = levels

    @property
    def __len__(self):
        return len(self._levels.data)

    @property
    def data(self):
        """
        List of level records. The first record is the master.

        :rtype: list
        """
        return self._levels.data

    @property
    def master(self):
        """Master record.

        :rtype: psd_tools.decoder.tagged_blocks.LevelRecord
        """
        return self._levels.data[0]


class Vibrance(_Descriptor):
    """Vibrance adjustment."""

    @property
    def vibrance(self):
        return self.get(b'vibrance', 0)

    @property
    def automatic(self):
        return self.get(b'auto', False)
