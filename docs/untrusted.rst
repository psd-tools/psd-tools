Handling untrusted files
========================

A PSD file can declare far more pixels than it contains, so a small file can
ask for gigabytes when it is rendered. Structural parsing has read and object
limits; rendering checks the estimated size of
the allocations listed below against an *allocation budget* before making
them. One over the budget raises :class:`ValueError`, or skips the layer effect
that needed it.

Parsing limits
--------------

:py:class:`~psd_tools.ParseLimits` limits an individual read to 256 MiB,
cumulative parsed bytes to 1 GiB, and parsed objects to 1,000,000 by default.
Descriptor and text-engine container parsing defaults to 64 active levels.
Set limits when opening a document::

    from psd_tools import ParseLimits, PSDImage

    psd = PSDImage.open('untrusted.psd', parse_limits=ParseLimits(
        max_read_bytes=64 * 1024**2,
        max_total_bytes=256 * 1024**2,
        max_objects=100_000,
        max_nesting_depth=32,
    ))

Each setting is a positive integer; ``None`` disables that limit.
``parse_limits=None`` uses the defaults. Limits also apply to low-level
``PSD.read()`` and ``frombytes()`` entry points. Recursive descriptor and
text-engine ``read()`` calls also establish a budget; other component
``read()`` calls use limits only within a budgeted parse.

Nested parsers share the root budget. Read bytes and inputs to ``frombytes()``
count cumulatively, including bytes copied or parsed again. Objects count
low-level element instances, unpacked scalar values, and array entries.
Peeking at available bytes does not consume the budget. Exceeding a limit
raises :py:class:`~psd_tools.ParseLimitError`; recovery does not suppress it.
Nesting counts active descriptor bodies, descriptor lists, and text-engine
dictionary/list parsers, including containers parsed from embedded bytes.
These counters bound parsing work, not total process memory,
tokenizer runtime, or later pixel decompression. Rendering uses its separate
allocation budget below.

The allocation budget
---------------------

The budget is a byte ceiling on each estimated allocation. It is not a cap on
the memory of the process. The default is 4 GiB
(``psd_tools.api.utils.DEFAULT_MAX_ALLOC_BYTES``).

Set it per document, when opening or at any time afterwards::

    psd = PSDImage.open('untrusted.psd', max_alloc_bytes=512 * 1024**2)
    psd.max_alloc_bytes = 256 * 1024**2

or for the whole process, through the environment or the module::

    export PSD_TOOLS_MAX_ALLOC_BYTES=536870912

    import psd_tools.api.utils
    psd_tools.api.utils.MAX_ALLOC_BYTES = 512 * 1024**2

A setting is a positive integer, or ``"unlimited"`` to disable the budget;
``None`` in ``MAX_ALLOC_BYTES`` also disables it, and the environment variable
accepts ``unlimited`` in any case. The document's setting wins. A document whose setting is ``None``, the default,
uses ``psd_tools.api.utils.MAX_ALLOC_BYTES`` as it is when each check
runs, so changing it affects documents that are already open. That variable is
read from ``$PSD_TOOLS_MAX_ALLOC_BYTES`` at import, and is the built-in default
when the variable is unset. An invalid environment or ``MAX_ALLOC_BYTES`` value
warns and gives the built-in default. An invalid API value raises :class:`TypeError` or
:class:`ValueError`, and :py:meth:`~psd_tools.api.psd_image.PSDImage.open`
checks it before reading the file.

What it bounds
--------------

- :py:meth:`~psd_tools.api.psd_image.PSDImage.numpy` and
  :py:meth:`~psd_tools.api.psd_image.PSDImage.topil`. The estimate is the
  peak of the call, including its intermediates, so it depends on the colour
  mode, depth and compression and is larger than the array returned.
- :py:meth:`~psd_tools.api.psd_image.PSDImage.thumbnail`, at the size of the
  decoded image; the JPEG decoder's own intermediates are not counted.
- Each layer's ``numpy()`` and ``topil()``, at the layer's own size, including
  the reads that :py:meth:`~psd_tools.api.psd_image.PSDImage.composite` makes.
- The canvas that ``composite()`` builds, and each canvas that a stroke size,
  vector stroke width or pattern scale grows. A layer effect over the budget is
  skipped; a vector stroke or fill layer over it raises.

What it does not bound
----------------------

- Parsing, which uses the separate limits above.
- The total of a composite. Each allocation is checked on its own, and
  compositing holds several at once, in numbers that grow with the layer count.
- Solid and gradient fills drawn at a layer's own box.

Other limits
------------

These apply whatever the budget:

- Each image axis is limited to 30,000 px
  (``psd_tools.api.utils.MAX_DIMENSION_PSD``), for PSB files too.
- A canvas grown from a descriptor value, such as a stroke width or a pattern
  scale, may not grow far out of proportion to what it grows from.

Recommendations
---------------

For files from an untrusted source, keep a finite budget, and process each
file in a separate process with an operating-system memory limit and a
timeout, since the budgets do not cap total process memory or CPU time.
On Linux, for example::

    import resource

    limit = 4 * 1024**3
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))

A container's memory limit serves the same purpose.
