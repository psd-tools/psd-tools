
1.4 (2017-01-02)
----------------

- Fixed reading of layer mask data (thanks Evgeny Kopylov);
- Python 2.6 support is dropped;
- Python 3.6 support is added (thanks Leendert Brouwer);
- extension is rebuilt with Cython 0.25.2.

1.3 (2016-01-25)
----------------

- fixed references decoding (thanks Josh Drake);
- fixed PIL support for CMYK files (thanks Michael Wu);
- optional C extension is rebuilt with Cython 0.23.4;
- Python 3.2 support is dropped; the package still works in Python 3.2,
  but the compatibility is no longer checked by tests, and so it can break
  in future.
- declare Python 3.5 as supported.

1.2 (2015-01-27)
----------------

- implemented extraction of embedded files (embedded smart objects) -
  thanks Volker Braun;
- optional C extension is rebuilt with Cython 0.21.2.
- hg mirror on bitbucket is dropped, sorry!

1.1 (2014-11-17)
----------------

- improved METADATA_SETTING decoding (thanks Evgeny Kopylov);
- layer comps decoding (thanks Evgeny Kopylov);
- improved smart objects decoding (thanks Joey Gentry);
- user API for getting layer transforms and placed layer size
  (thanks Joey Gentry);
- IPython import is deferred to speedup ``psd-tools.py`` command-line utility;
- ``_RootGroup.__repr__`` is fixed;
- warning message building is more robust;
- optional C extension is rebuilt with Cython 0.21.1.

1.0 (2014-07-24)
----------------

- Fixed reading of images with layer masks (thanks Evgeny Kopylov);
- improved mask data decoding (thanks Evgeny Kopylov);
- fixed syncronization in case of ``8B64`` signatures (thanks Evgeny Kopylov);
- fixed reading of layers with zero length (thanks Evgeny Kopylov);
- fixed Descriptor parsing (thanks Evgeny Kopylov);
- some of the descriptor structures and tagged block constants are renamed (thanks Evgeny Kopylov);
- PATH_SELECTION_STATE decoding (thanks Evgeny Kopylov);
- the library is switched to setuptools; docopt is now installed automatically.

0.10 (2014-06-15)
-----------------

- Layer effects parsing (thanks Evgeny Kopylov);
- trailing null bytes are stripped from descriptor strings
  (thanks Evgeny Kopylov);
- "Reference" and "List" descriptor parsing is fixed
  (thanks Evgeny Kopylov);
- scalar descriptor values (doubles, floats, booleans) are now returned
  as scalars, not as lists of size 1 (thanks Evgeny Kopylov);
- fixed reading of EngineData past declared length
  (thanks Carlton P. Taylor);
- "background color" Image Resource parsing (thanks Evgeny Kopylov);
- `psd_tools.decoder.actions.Enum.enum` field is renamed to
  `psd_tools.decoder.actions.Enum.value` (thanks Evgeny Kopylov);
- code simplification - constants are now bytestrings as they should be
  (thanks Evgeny Kopylov);
- Python 3.4 is supported.

0.9.1 (2014-03-26)
------------------

- Improved merging of transparent layers (thanks Vladimir Timofeev);
- fixed layer merging and bounding box calculations for empty layers
  (thanks Vladimir Timofeev);
- C extension is rebuilt with Cython 0.20.1.

0.9 (2013-12-03)
----------------

- `psd-tools.py` command-line interface is changed, 'debug' command is added;
- pretty-printing of internal structures;
- pymaging support is fixed;
- allow 'MeSa' to be a signature for image resource blocks
  (thanks Alexey Buzanov);
- `psd_tools.debug.debug_view` utility function is fixed;
- Photoshop CC constants are added;
- Photoshop CC vector origination data is decoded;
- binary data is preserved if descriptor parsing fails;
- more verbose logging for PSD reader;
- channel data reader became more robust - now it doesn't read past
  declared channel length;
- `psd-tools.py --version` command is fixed;
- `lsdk` tagged blocks parsing: this fixes some issues with layer grouping
  (thanks Ivan Maradzhyiski for the bug report and the patch);
- CMYK images support is added (thanks Alexey Buzanov, Guillermo Rauch and
  https://github.com/a-e-m for the help);
- Grayscale images support is added (thanks https://github.com/a-e-m);
- LittleCMS is now optional (but it is still required to get proper colors).

0.8.4 (2013-06-12)
------------------

- Point and Millimeter types are added to UnitFloatType (thanks Doug Ellwanger).

0.8.3 (2013-06-01)
------------------

- Some issues with descriptor parsing are fixed (thanks Luke Petre).

0.8.2 (2013-04-12)
------------------

- Python 2.x: reading data from file-like objects is fixed
  (thanks Pavel Zinovkin).

0.8.1 (2013-03-02)
------------------

- Fixed parsing of layer groups without explicit OPEN_FOLDER mark;
- Cython extension is rebuilt with Cython 0.18.

0.8 (2013-02-26)
----------------

- Descriptor parsing (thanks Oliver Zheng);
- text (as string) is extracted from text layers (thanks Oliver Zheng);
- improved support for optional building of Cython extension.

0.7.1 (2012-12-27)
------------------

- Typo is fixed: ``LayerRecord.cilpping`` should be ``LayerRecord.clipping``.
  Thanks Oliver Zheng.

0.7 (2012-11-08)
----------------

- Highly experimental: basic layer merging is implemented
  (e.g. it is now possible to export layer group to a PIL image);
- ``Layer.visible`` no longer takes group visibility in account;
- ``Layer.visible_global`` is the old ``Layer.visible``;
- ``psd_tools.user_api.combined_bbox`` made public;
- ``Layer.width`` and ``Layer.height`` are removed (use ``layer.bbox.width``
  and ``layer.bbox.height`` instead);
- ``pil_support.composite_image_to_PIL`` is renamed to ``pil_support.extract_composite_image`` and
  ``pil_support.layer_to_PIL`` is renamed to ``pil_support.extract_layer_image``
  in order to have the same API for ``pil_support`` and ``pymaging_support``.

0.6 (2012-11-06)
----------------

- ``psd.composite_image()`` is renamed to ``psd.as_PIL()``;
- Pymaging support: ``psd.as_pymaging()`` and ``layer.as_pymaging()`` methods.


0.5 (2012-11-05)
----------------

- Support for zip and zip-with-prediction compression methods is added;
- support for 16/32bit layers is added;
- optional Cython extension for faster zip-with-prediction decompression;
- other speed improvements.

0.2 (2012-11-04)
----------------

- Initial support for 16bit and 32bit PSD files: ``psd-tools`` v0.2 can
  read composite (merged) images for such files and extract information
  (names, dimensions, hierarchy, etc.) about layers and groups of 16/32bit PSD;
  extracting image data for distinct layers in 16/32bit PSD files is not
  suported yet;
- better ``Layer.__repr__``;
- ``bbox`` property for ``Group``.

0.1.4 (2012-11-01)
------------------

Packaging is fixed in this release.

0.1.3 (2012-11-01)
------------------

- Better support for 32bit images (still incomplete);
- reader is able to handle "global" tagged layer info blocks that
  was previously discarded.

0.1.2 (2012-10-30)
------------------

- warn about 32bit images;
- transparency support for composite images.

0.1.1 (2012-10-29)
------------------

Initial release (v0.1 had packaging issues).
