Contributing
============

Development happens at github: `bug tracker <https://github.com/psd-tools/psd-tools/issues>`__.
Feel free to submit `bug reports <https://github.com/psd-tools/psd-tools/issues/new>`_
or pull requests. Attaching an erroneous PSD file makes the debugging process
faster. Such PSD file might be added to the test suite.

The license is MIT.

Package design
--------------

See :doc:`architecture` for the package layout and the contracts a change
must preserve.

Testing
-------

In order to run tests, make sure PIL/Pillow is built with LittleCMS
or LittleCMS2 support. For example, on Ubuntu, install the following packages::

    apt-get install liblcms2-dev libjpeg-dev libfreetype6-dev zlib1g-dev

Then install `psd-tools` with development dependencies::

    uv sync --group dev --extra composite

Finally, run tests::

    uv run pytest

Things to know when writing compositor tests:

- ``check_composite_quality()`` defaults to ``force=False``. A regression in
  the drawing path shows only under ``force=True``, so run both.
- Assert pixel values, not only the PIL mode of the result.
- ``_mse`` in ``tests/psd_tools/composite/test_composite.py`` scores colour
  where alpha is 0, so split alpha from RGB before reading a change as a
  regression.
- A fixture whose layer runs past the canvas measures the viewport clip, not
  the feature under test. Compare ``layer.bbox`` with ``psd.size`` first.
- CI runs several Python versions, and behaviour differs between them. Check
  type annotations and lock bumps on the newest one.

Documentation
-------------

Install documentation dependencies::

    uv sync --group docs

Once installed, use `Makefile`::

    make docs

The default build does not report dead cross-references; only
``sphinx-build -n`` does. There is no intersphinx mapping, so third-party
types in annotations always count as dead. Compare the
``not found: psd_tools.`` entries rather than the total.

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
   based on the changes since the last release. The auto-tag workflow
   recognises these forms:

   - ``v1.2.3`` — standard release
   - ``v1.2.3a1``, ``v1.2.3b1``, ``v1.2.3rc1`` — pre-releases (alpha, beta, release candidate)
   - ``v1.2.3.post1`` — post-release

2. **Update the changelog**: Review ``git log`` since the last tag and
   summarize changes in ``docs/changelog.rst`` under the new version heading.

3. **Create a release PR**: Create a branch named ``release/<version>``,
   where ``<version>`` is one of the supported version forms listed above
   (e.g. ``release/v1.15.0``, ``release/v1.15.0rc1``, or
   ``release/v1.15.0.post1``), commit the changelog update (and any version
   bumps), and open a PR against ``main``. Merge it once approved. The branch
   name is how the auto-tag workflow identifies the version to tag.

4. **Automated tagging and publishing**: Merging the release PR triggers the
   ``auto-tag`` workflow, which tags the exact merge commit that landed on
   ``main`` (using ``merge_commit_sha``), pushes the tag, and closes the
   matching release milestone if one is open. The tag push in turn triggers
   the ``release`` workflow, which:

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
