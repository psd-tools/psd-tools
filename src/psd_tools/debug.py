# -*- coding: utf-8 -*-
"""
Assorted debug utilities
"""
from __future__ import absolute_import, print_function
import sys
from collections import namedtuple


def register_formatters():

    def _repr_pretty_tuple(self, p, cycle):
        # checking for a subclass...
        if type(self) != tuple:
            _repr_tuple_old(self, p, cycle)
        else:
            if cycle:
                p.text(repr(self))
            else:
                with p.group(0, '(', ')'):
                    for idx, item in enumerate(self):
                        if idx:
                            p.text(', ')
                        p.pretty(item)

    def _repr_pretty_list(self, p, cycle):
        # checking for a subclass...
        if type(self) != list:
            _repr_list_old(self, p, cycle)
        else:
            if cycle:
                p.text(repr(self))
            else:
                p.begin_group(2, '[')
                p.begin_group(0)

                for idx, item in enumerate(self):
                    if idx:
                        p.text(',')
                    p.break_()
                    p.pretty(item)

                p.end_group(2)
                p.break_()
                p.end_group(0, ']')

    def _repr_pretty_dict(self, p, cycle):
        # checking for a subclass...
        if type(self) != dict:
            _repr_dict_old(self, p, cycle)
        else:
            if cycle:
                p.text(repr(self))
            else:
                p.begin_group(2, '{')
                p.begin_group(0)

                for idx, key in enumerate(sorted(self)):
                    if idx:
                        p.text(',')
                    p.break_()
                    p.text("'%s': " % key)
                    p.pretty(self[key])

                p.end_group(2)
                p.break_()
                p.end_group(0, '}')

    try:
        from IPython.lib import pretty as text_formatter

        _repr_tuple_old = text_formatter.for_type(tuple, _repr_pretty_tuple)
        _repr_list_old = text_formatter.for_type(list, _repr_pretty_list)
        _repr_dict_old = text_formatter.for_type(dict, _repr_pretty_dict)
    except ImportError:
        pass


def pprint(*args, **kwargs):
    """
    Pretty-print a Python object using ``IPython.lib.pretty.pprint``.
    Fallback to ``pprint.pprint`` if IPython is not available.
    """
    global pprint

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
    cls = namedtuple(typename, field_names, verbose)
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
                p.text(repr(self))
            else:
                p.begin_group(2, "%s(" % typename)
                p.begin_group(0)

                for idx, field in enumerate(self._fields):
                    if idx:
                        p.text(',')
                    p.break_()
                    p.text("%s = " % field)
                    p.pretty(getattr(self, field))

                p.end_group(2)
                p.break_()
                p.end_group(0, ')')

    return _PrettyNamedtupleMixin
