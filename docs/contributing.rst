Contributing
============

Development happens at github: `bug tracker <https://github.com/psd-tools/psd-tools/issues>`__.
Feel free to submit `bug reports <https://github.com/psd-tools/psd-tools/issues/new>`_
or pull requests. Attaching an erroneous PSD file makes the debugging process
faster. Such PSD file might be added to the test suite.

The license is MIT.

Package design
--------------

The package consists of two major subpackages:

1) :py:mod:`psd_tools.psd`: subpackage that reads/writes low-level binary
    structure
    of the PSD/PSB file. The core data structures are built around attrs_
    class that all implement `read` and `write` methods. Each data object
    tries to resemble the structure described in the specification_. Although
    documented, the specification_ is far from complete and some are even
    inaccurate. When `psd-tools` finds unknown data structure, the package
    keeps such data as `bytes` in the parsed result.

.. _attrs: https://www.attrs.org/en/stable/index.html#
.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/

2) :py:mod:`psd_tools.api`: User-facing API that implements various
    easy-to-use methods that manipulate low-level :py:mod:`psd_tools.psd` data
    structures.

Testing
-------

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support, install `tox <http://tox.testrun.org>`_ and type::

    tox

from the source checkout. Or, it is a good idea to install and run
`detox <https://github.com/tox-dev/detox>`_ for parallel execution::

    detox

Documentation
-------------

Install Sphinx to generate documents::

    pip install sphinx sphinx_rtd_theme

Once installed, use `Makefile`::

    make docs

Acknowledgments
---------------

Great thanks to `all the contributors <https://github.com/psd-tools/psd-tools/graphs/contributors>`_.
