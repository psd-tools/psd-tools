#!/usr/bin/env python
from setuptools import setup, find_packages
from distutils.extension import Extension
import logging
import os
import sys

try:
    from Cython.Build import cythonize
    extension = cythonize(
        [
            Extension(
                'psd_tools.compression._packbits',
                ['src/psd_tools/compression/_packbits.pyx']
            )
        ],
        language_level=sys.version_info[0],
    )
except ImportError:
    logging.error('Cython not found, no extension will be built.')
    extension = []


def get_version():
    """
    Get package version.
    """
    curdir = os.path.dirname(__file__)
    filename = os.path.join(curdir, 'src', 'psd_tools', 'version.py')
    with open(filename, 'r') as fp:
        return fp.read().split('=')[1].strip(" \r\n'")


setup(
    name='psd-tools',
    version=get_version(),
    author='Kota Yamaguchi',
    author_email='KotaYamaguchi1984@gmail.com',
    url='https://github.com/psd-tools/psd-tools',
    description='Python package for working with Adobe Photoshop PSD files',
    long_description=(
        open('README.rst').read() + "\n\n" + open('CHANGES.rst').read()
    ),
    license='MIT License',
    install_requires=[
        'docopt>=0.5',
        'attrs>=19.2.0',
        'Pillow>=6.2.0',
        'enum34;python_version<"3.4"',
        'aggdraw',
    ],
    keywords="photoshop psd pil pillow",
    package_dir={'': 'src'},
    packages=find_packages('src'),
    ext_modules=extension,
    entry_points={'console_scripts': ['psd-tools=psd_tools.__main__:main']},
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Multimedia :: Graphics :: Viewers',
        'Topic :: Multimedia :: Graphics :: Graphics Conversion',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)
