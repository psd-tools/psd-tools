# -*- coding: utf-8 -*-
"""
Assorted debug utilities
"""
from __future__ import absolute_import, print_function
import sys
from collections import namedtuple


def pprint(*args, **kwargs):
    """
    Pretty-print a Python object using ``IPython.lib.pretty.pprint``.
    Fallback to ``pprint.pprint`` if IPython is not available.
    """
    try:
        from IPython.lib.pretty import pprint
    except ImportError:
        from pprint import pprint
    pprint(*args, **kwargs)


def debug_view(fp, txt="", max_back=20):
    """
    Print file contents around current position for file pointer ``fp``
    """
    max_back = min(max_back, fp.tell())
    fp.seek(-max_back, 1)
    pre = fp.read(max_back)
    post = fp.read(100)
    fp.seek(-100, 1)
    print(txt, repr(pre), "--->.<---", repr(post))


def pretty_namedtuple(typename, field_names, verbose=False):
    """
    Return a namedtuple class that knows how to pretty-print itself
    using IPython.lib.pretty library.
    """
    cls = namedtuple(typename, field_names, verbose=verbose)
    PrettyMixin = _get_pretty_mixin(typename)
    cls = type(str(typename), (PrettyMixin, cls), {})

    # For pickling to work, the __module__ variable needs to be set to the frame
    # where the named tuple is created.  Bypass this step in enviroments where
    # sys._getframe is not defined (Jython for example) or sys._getframe is not
    # defined for arguments greater than 0 (IronPython).
    try:
        cls.__module__ = sys._getframe(1).f_globals.get('__name__', '__main__')
    except (AttributeError, ValueError):
        pass

    return cls


def _get_pretty_mixin(typename):
    """
    Return a mixin class for multiline pretty-printing
    of namedtuple objects.
    """
    class _PrettyNamedtupleMixin(object):
        def _repr_pretty_(self, p, cycle):
            if cycle:
                return "{typename}(...)".format(name=typename)

            with p.group(1, '{name}('.format(name=typename), ')'):
                p.breakable()
                for idx, field in enumerate(self._fields):
                    if idx:
                        p.text(',')
                        p.breakable()
                    p.text('{field}='.format(field=field))
                    p.pretty(getattr(self, field))

    return _PrettyNamedtupleMixin
