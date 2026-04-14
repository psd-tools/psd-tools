#!/usr/bin/env python
import sys
import sysconfig

from Cython.Build import cythonize
from setuptools import Extension, setup

# Free-threaded Python (cp314t) does not support the Limited API / stable ABI.
# Each cp314t version needs its own version-specific wheel.
_py_gil_disabled = sysconfig.get_config_var("Py_GIL_DISABLED")
try:
    is_free_threaded = int(_py_gil_disabled or 0) != 0
except (TypeError, ValueError):
    is_free_threaded = False
use_limited_api = sys.version_info >= (3, 13) and not is_free_threaded

extensions = [
    Extension(
        "psd_tools.compression._rle",
        ["src/psd_tools/compression/_rle.pyx"],
        extra_compile_args=["/d2FH4-"] if sys.platform == "win32" else [],
        define_macros=[("Py_LIMITED_API", 0x030D0000)] if use_limited_api else [],
        py_limited_api=use_limited_api,
    )
]


setup(ext_modules=cythonize(extensions))
