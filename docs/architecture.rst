Architecture
============

This page describes how the code is organized and the contracts a change must
preserve. For setup, tests and releases see :doc:`contributing`.

Package layout
--------------

The package has two layers and two supporting subpackages.

:py:mod:`psd_tools.psd`
    Reads and writes the raw binary structure of a PSD/PSB file. Each data
    object is an attrs_ class that mirrors the specification_ and implements
    ``read(fp)`` and ``write(fp)``. The specification is incomplete and
    sometimes inaccurate, so unknown structures are kept as ``bytes`` and
    written back unchanged.

:py:mod:`psd_tools.api`
    The user-facing interface. :py:class:`~psd_tools.PSDImage` wraps the
    low-level ``PSD`` and exposes layers, masks, effects and pixel access.
    Parsing happens when the file is opened; decompression and pixel
    materialization are deferred until first access.

:py:mod:`psd_tools.composite`
    The rendering engine: blend modes, layer effects and vector rasterization
    on NumPy arrays. It needs the optional ``composite`` extra.

:py:mod:`psd_tools.compression`
    Raw, RLE and ZIP codecs. RLE has a Cython implementation (``_rle.pyx``)
    with a pure Python fallback.

.. _attrs: https://www.attrs.org/en/stable/index.html#
.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/

Layer tree
----------

A PSD stores layers as a flat record list; groups are implied by
``SectionDivider`` tagged blocks. ``PSDImage`` rebuilds the tree from them:

.. code-block:: text

    Record 0: "Background"    normal layer
    Record 1: (divider)       BOUNDING_SECTION_DIVIDER: opens the group
    Record 2: "Child 1"
    Record 3: "Child 2"
    Record 4: "Group"         OPEN_FOLDER or CLOSED_FOLDER: closes the group
                              and carries its name and attributes

In a 16- or 32-bit document the records can live in an ``Lr16``/``Lr32``
tagged block rather than ``layer_info``, so read them through
``PSD._get_layer_info()``.

Mutation contract
-----------------

psd-tools was a read-only parser before it gained editing, and much of the API
still assumes it.

- Editing through the high-level API (``append()``, ``visible = False``,
  ``name = ...``) must leave every cached property consistent. A stale cache
  after such an edit is a bug.
- Mutating the low-level :py:mod:`psd_tools.psd` structures underneath the API
  (``layer._record``, ``layer.tagged_blocks``) and then reading a cached
  property is outside the contract.
- ``tagged_blocks.set_data()`` rebuilds the top level of the descriptor it is
  given and shares the nested values. Re-fetch with ``get_data()`` before
  mutating the stored block.

Property getters
----------------

A property annotated ``int``, ``float``, ``bool`` or ``str`` returns that
primitive, not the descriptor wrapper, which does not subclass it and fails
``isinstance`` and ``json.dumps``. A missing key returns a Photoshop default
only when the format defines one; otherwise the annotation is ``T | None`` and
the getter returns ``None`` rather than raising.
``tests/psd_tools/api/test_annotations.py`` checks this over the fixture
corpus.

Compositing
-----------

Preview versus drawing
^^^^^^^^^^^^^^^^^^^^^^

``PSDImage.composite()`` returns the stored preview when the document has one,
has not been edited, and none of ``ignore_preview``, ``force`` or
``layer_filter`` is given. Those arguments are how a test reaches the
renderer. Otherwise it renders layers. Within a render,
``force=True`` draws vector shapes with aggdraw instead of reading the layer's
stored channel, which carries Photoshop's own rasterization. A change to the
drawing code is invisible to the default mode, so verify both.

Viewport
^^^^^^^^

``Compositor`` pastes each layer's arrays onto its viewport, padding coverage
with zeros. Code that needs coverage outside the viewport, such as a stroke
effect traced past the canvas edge, cannot recover it by cropping; it must read
the layer again on the larger box. A group has no stored coverage to re-read,
so its contents are composited again on that box.

Artboards
^^^^^^^^^

``Artboard`` subclasses ``Group`` but its ``bbox`` is the artboard rectangle,
not the union of its children. For a group that is not pass-through,
intersecting the viewport with that box is how the artboard clips its contents
(``_get_group()``), so any change that widens a group's viewport must carve
artboards out. A pass-through artboard receives the parent's viewport
unclipped.

Allocation budget
^^^^^^^^^^^^^^^^^

Pixel reads and renders are checked against ``max_alloc_bytes`` before
allocating; structural parsing and low-level decompression have their own
limits (``ParseLimits``, ``max_output_bytes``). See :doc:`untrusted`. The check
compares the modelled peak of the operation, not the size of the returned
array, so a budget must be sized from the peak.
