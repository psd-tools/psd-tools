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

In the future, it might be good to implement the `Photoshop API`_ on top of the existing `psd-tools` API.

.. _Photoshop API: https://developer.adobe.com/photoshop/uxp/2022/ps_reference/

Testing
-------

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support. For example, on Ubuntu, install the following packages::

    apt-get install liblcms2-dev libjpeg-dev libfreetype6-dev zlib1g-dev

Then install `psd-tools` with the following command::

    pip install -e .[dev]

Finally, run tests with `pytest`::

    pytest

Documentation
-------------

Install Sphinx to generate documents::

    pip install sphinx sphinx_rtd_theme

Once installed, use `Makefile`::

    make docs

Release Process
---------------

Releases are automated via GitHub Actions. To create a new release:

1. **Ensure all changes are committed and pushed to main**::

    git checkout main
    git pull origin main

2. **Create and push a version tag**::

    git tag v1.x.x
    git push origin v1.x.x

3. **Automated workflow**:

   Once the tag is pushed, the release workflow automatically:

   - Builds wheels for all supported platforms (Linux, Windows, macOS including ARM)
   - Generates release notes from git commits since the previous tag
   - Creates a GitHub release with the auto-generated changelog
   - Publishes the package to PyPI

4. **Verify the release**:

   - Check the `Actions tab <https://github.com/psd-tools/psd-tools/actions>`_ for workflow status
   - Verify the `release on GitHub <https://github.com/psd-tools/psd-tools/releases>`_
   - Confirm the package is available on `PyPI <https://pypi.org/project/psd-tools/>`_

**Note**: Only maintainers with appropriate repository permissions can push tags
and trigger releases. PyPI credentials are stored as repository secrets.

Acknowledgments
---------------

Great thanks to `all the contributors <https://github.com/psd-tools/psd-tools/graphs/contributors>`_.
