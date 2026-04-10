Contributing
============

Development happens at github: `bug tracker <https://github.com/psd-tools/psd-tools/issues>`__.
Feel free to submit `bug reports <https://github.com/psd-tools/psd-tools/issues/new>`_
or pull requests. Attaching an erroneous PSD file makes the debugging process
faster. Such PSD file might be added to the test suite.

The license is MIT.

Package design
--------------

The package consists of four major subpackages:

1) :py:mod:`psd_tools.psd`: subpackage that reads/writes low-level binary
    structure of the PSD/PSB file. The core data structures are built around
    attrs_ classes that all implement `read` and `write` methods. Each data
    object tries to resemble the structure described in the specification_.
    Although documented, the specification_ is far from complete and some are
    even inaccurate. When `psd-tools` finds unknown data structure, the package
    keeps such data as `bytes` in the parsed result.

.. _attrs: https://www.attrs.org/en/stable/index.html#
.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/

2) :py:mod:`psd_tools.api`: User-facing API that implements various
    easy-to-use methods that manipulate low-level :py:mod:`psd_tools.psd` data
    structures. This is the primary interface for most users.

3) :py:mod:`psd_tools.composite`: Rendering engine for layer compositing and
    blending. This subpackage implements blend modes, layer effects (drop
    shadows, strokes, etc.), and vector shape rasterization. It uses NumPy
    arrays for efficient pixel manipulation and includes optional dependencies
    (`scipy`, `scikit-image`, `aggdraw`) that must be installed via the
    ``composite`` extra.

4) :py:mod:`psd_tools.compression`: Image compression codecs for raw data,
    RLE (Run-Length Encoding), and ZIP compression. The RLE codec includes a
    Cython-optimized implementation (`_rle.pyx`) that falls back to pure Python
    if not compiled, providing significant performance improvements for large
    files.

In the future, it might be good to implement the `Photoshop API`_ on top of the existing `psd-tools` API.

.. _Photoshop API: https://developer.adobe.com/photoshop/uxp/2022/ps_reference/

Testing
-------

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support. For example, on Ubuntu, install the following packages::

    apt-get install liblcms2-dev libjpeg-dev libfreetype6-dev zlib1g-dev

Then install `psd-tools` with development dependencies::

    uv sync --group dev --extra composite

Finally, run tests::

    uv run pytest

Documentation
-------------

Install documentation dependencies::

    uv sync --group docs

Once installed, use `Makefile`::

    make docs

Release Process
---------------

Releases are automated via GitHub Actions. Only maintainers with appropriate
repository permissions can trigger releases. The following repository secrets
must be configured:

- ``RELEASE_WORKFLOW_TOKEN``: a fine-grained PAT with ``contents: write``,
  required so that the tag pushed by ``auto-tag.yml`` triggers the downstream
  ``release.yml`` workflow (the default ``GITHUB_TOKEN`` cannot do this).
- ``PYPI_USERNAME`` / ``PYPI_PASSWORD``: PyPI credentials for publishing.

1. **Decide the version number** following `PEP 440 <https://peps.python.org/pep-0440/>`_
   based on the changes since the last release (e.g. ``v1.2.3`` or
   ``v1.2.3.post1`` for post-releases).

2. **Update the changelog**: Review ``git log`` since the last tag and
   summarize changes in ``docs/changelog.rst`` under the new version heading.

3. **Create a release PR**: Create a branch named exactly ``release/vX.Y.Z``
   (e.g. ``release/v1.15.0``), commit the changelog update (and any version
   bumps), and open a PR against ``main``. Merge it once approved. The branch
   name is how the auto-tag workflow identifies the version to tag.

4. **Automated tagging and publishing**: Merging the release PR triggers the
   ``auto-tag`` workflow, which tags the exact merge commit that landed on
   ``main`` (using ``merge_commit_sha``) and pushes the tag. This in turn
   triggers the ``release`` workflow, which:

   - Builds wheels for all supported platforms (Linux, Windows, macOS including ARM)
   - Generates release notes from git commits since the previous tag
   - Creates a GitHub release with the auto-generated changelog
   - Publishes the package to PyPI

5. **Verify the release**:

   - Check the `Actions tab <https://github.com/psd-tools/psd-tools/actions>`_ for workflow status
   - Verify the `release on GitHub <https://github.com/psd-tools/psd-tools/releases>`_
   - Confirm the package is available on `PyPI <https://pypi.org/project/psd-tools/>`_

Acknowledgments
---------------

Great thanks to `all the contributors <https://github.com/psd-tools/psd-tools/graphs/contributors>`_.
