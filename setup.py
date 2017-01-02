#!/usr/bin/env python
from setuptools import setup
from setuptools.extension import Extension
from setuptools.command.build_ext import build_ext
from distutils import errors

import os
import sys

def get_version():
    curdir = os.path.dirname(__file__)
    filename = os.path.join(curdir, 'src', 'psd_tools', 'version.py')
    with open(filename, 'rb') as fp:
        return fp.read().decode('utf8').split('=')[1].strip(" \n'")

setup_args = dict(
    name='psd-tools',
    version=get_version(),
    author='Mikhail Korobov',
    author_email='kmike84@gmail.com',
    url='https://github.com/kmike/psd-tools',

    description='Python package for working with Adobe Photoshop PSD files',
    long_description=open('README.rst').read() + "\n\n" + open('CHANGES.rst').read(),
    license='MIT License',
    requires=['docopt (>= 0.5)', 'Pillow'],
    install_requires=['docopt >= 0.5'],
    keywords="pymaging psd imaging pil pillow",
    zip_safe=False,

    package_dir={'': 'src'},
    packages=['psd_tools', 'psd_tools.reader', 'psd_tools.decoder',
              'psd_tools.user_api'],
    package_data={'psd_tools': ['icc_profiles/*.icc']},
    scripts=['bin/psd-tools.py'],

    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
        'Topic :: Multimedia :: Graphics',
        'Topic :: Multimedia :: Graphics :: Viewers',
        'Topic :: Multimedia :: Graphics :: Graphics Conversion',
        'Topic :: Software Development :: Libraries :: Python Modules',
    ],
)

# ========== make extension optional (copied from coverage.py) =========

# A replacement for the build_ext command which raises a single exception
# if the build fails, so we can fallback nicely.

ext_errors = (
    errors.CCompilerError,
    errors.DistutilsExecError,
    errors.DistutilsPlatformError,
)
if sys.platform == 'win32' and sys.version_info > (2, 6):
    # 2.6's distutils.msvc9compiler can raise an IOError when failing to
    # find the compiler
    ext_errors += (IOError,)

class BuildFailed(Exception):
    """Raise this to indicate the C extension wouldn't build."""
    def __init__(self):
        Exception.__init__(self)
        self.cause = sys.exc_info()[1] # work around py 2/3 different syntax

class ve_build_ext(build_ext):
    """Build C extensions, but fail with a straightforward exception."""

    def run(self):
        """Wrap `run` with `BuildFailed`."""
        try:
            build_ext.run(self)
        except errors.DistutilsPlatformError:
            raise BuildFailed()

    def build_extension(self, ext):
        """Wrap `build_extension` with `BuildFailed`."""
        try:
            # Uncomment to test compile failures:
            #   raise errors.CCompilerError("OOPS")
            build_ext.build_extension(self, ext)
        except ext_errors:
            raise BuildFailed()
        except ValueError:
            # this can happen on Windows 64 bit, see Python issue 7511
            if "'path'" in str(sys.exc_info()[1]): # works with both py 2/3
                raise BuildFailed()
            raise

# There are a few reasons we might not be able to compile the C extension.
# Figure out if we should attempt the C extension or not.

compile_extension = True

if sys.platform.startswith('java'):
    # Jython can't compile C extensions
    compile_extension = False

if '__pypy__' in sys.builtin_module_names:
    # Cython extensions are slow under PyPy
    compile_extension = False

if compile_extension:
    setup_args.update(dict(
        ext_modules = [
            Extension("psd_tools._compression", sources=["src/psd_tools/_compression.c"])
        ],
        cmdclass = {'build_ext': ve_build_ext},
    ))

def main():
    """Actually invoke setup() with the arguments we built above."""
    # For a variety of reasons, it might not be possible to install the C
    # extension.  Try it with, and if it fails, try it without.
    try:
        setup(**setup_args)
    except BuildFailed:
        msg = "Couldn't install with extension module, trying without it..."
        exc = sys.exc_info()[1]
        exc_msg = "%s: %s" % (exc.__class__.__name__, exc.cause)
        print("**\n** %s\n** %s\n**" % (msg, exc_msg))

        del setup_args['ext_modules']
        setup(**setup_args)

if __name__ == '__main__':
    main()
