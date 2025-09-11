#!/usr/bin/env python
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup

extensions = [
    Extension(
        "psd_tools.compression._rle",
        ["src/psd_tools/compression/_rle.pyx"],
        extra_compile_args=["/d2FH4-"] if sys.platform == "win32" else [],
        define_macros=[("Py_LIMITED_API", 0x03130000)]
        if sys.version_info >= (3, 13)
        else [],
        py_limited_api=True if sys.version_info >= (3, 13) else False,
    )
]


setup(ext_modules=cythonize(extensions))
