#!/usr/bin/env python
from setuptools import setup, find_packages
import logging
import os

logger = logging.getLogger(__name__)


def get_version():
    """
    Get package version.
    """
    curdir = os.path.dirname(__file__)
    filename = os.path.join(curdir, 'src', 'psd_tools', 'version.py')
    with open(filename, 'rb') as fp:
        return fp.read().decode('utf8').split('=')[1].strip(" \n'")


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
        'docopt >= 0.5',
        'packbits',
        'attrs',
        'Pillow',
        'enum34;python_version<"3.4"',
    ],
    keywords="photoshop psd pil pillow",
    package_dir={'': 'src'},
    packages=find_packages('src'),
    entry_points={
        'console_scripts': ['psd-tools=psd_tools.__main__:main']
    },
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
