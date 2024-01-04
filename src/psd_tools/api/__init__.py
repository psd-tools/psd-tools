from __future__ import absolute_import, unicode_literals

import functools
import warnings


def deprecated(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        warnings.simplefilter("always", DeprecationWarning)
        warnings.warn(
            "%r is deprecated" % (func.__name__),
            category=DeprecationWarning,
            stacklevel=2,
        )
        warnings.simplefilter("default", DeprecationWarning)
        return func(*args, **kwargs)

    return wrapper
