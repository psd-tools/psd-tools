#!/usr/bin/env python
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup

extensions = [
    Extension(
        "psd_tools.compression._rle",
        ["src/psd_tools/compression/_rle.pyx"],
        extra_compile_args=["/d2FH4-"] if sys.platform == "win32" else [],
    )
]


setup(ext_modules=cythonize(extensions))
