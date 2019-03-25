1.8.12 (2019-03-25)
-------------------

- add apply_icc option in pil io.

1.8.11 (2019-03-14)
-------------------

- introduce terminology module;
- reduce memory use in read;
- add main testing.

1.8.10 (2019-02-27)
-------------------

- fix PSB extn key size bug.

1.8.9 (2019-02-21)
------------------

- documentation updates;
- introduce `Artboard` class.

1.8.8 (2019-02-20)
------------------

- revert package name to `psd_tools`;
- prepare merging to the main repo.

1.8.7 (2019-02-15)
------------------

- minor bugfix.

1.8.6 (2019-02-14)
------------------

- change _psd pointer in PSDImage;
- add version property;
- support fill effects in composer.

1.8.5 (2019-02-05)
------------------

- change tagged block/image resource singleton accessor in user API;
- add documentation on iterator order;
- fix export setting 1 big key config;
- fix computer info big key config.

1.8.3 (2019-02-01)
------------------

- add channel size checking in topil;
- add mlst metadata decoding;
- fix key collision issue in descriptor;
- performance improvement for packbit encoding/decoding;
- drop cython dependency in travis config;
- implement thumbnail, is_group, and parent methods in PSDImage.

1.8.0 (2019-01-24)
------------------

- major API changes;
- package name changed to `psd_tools2`;
- completely rewritten decoding subpackage `psd_tools2.psd`;
- improved composer functionality;
- file write support;
- drop cython compression module and makes the package pure-python;
- drop pymaging support.

1.7.30 (2019-01-15)
-------------------

- composer alpha blending fix;
- documentation fix.

1.7.28 (2019-01-09)
-------------------

- support cinf tagged block.

1.7.27 (2018-12-06)
-------------------

- add missing extra image resource block signatures.

1.7.26 (2018-12-03)
-------------------

- move psd_tools tests under tests/psd_tools.

1.7.25 (2018-11-27)
-------------------

- fix alpha channel visibility of composed image.

1.7.24 (2018-11-21)
-------------------

- fix unit rectangle drawing size.


1.7.23 (2018-11-20)
-------------------

- fix ignored visibility in bbox calculation.

1.7.22 (2018-10-12)
-------------------

- drop py34 support;
- fix tobytes deprecation warning.

1.7.21 (2018-10-10)
-------------------

- fix gradient descriptor bug.

1.7.20 (2018-10-09)
-------------------

- fix coloroverlay bug;
- fix gradient angle bug;
- fix curves decoder bug.

1.7.19 (2018-10-02)
-------------------

- fix descriptor decoder.

1.7.18 (2018-09-26)
-------------------

- add shape rendering in `compose()`;
- add grayscale support.

1.7.17 (2018-09-21)
-------------------

- fix `has_pixel()` condition.

1.7.16 (2018-08-29)
-------------------

- fix fill opacity in `compose()`;
- workaround for broken `PrintFlags`.

1.7.15 (2018-08-28)
-------------------

- fix color overlay issue in `compose()`.

1.7.14 (2018-08-24)
-------------------

- fix `verbose` arg for python 3.7 compatibility.

1.7.13 (2018-08-10)
-------------------

- fix `has_pixel()` for partial channels;
- support color overlay in `compose()`.

1.7.12 (2018-06-25)
-------------------

- fix mask rendering in compose (Thanks @andrey-hider and @nkato).

1.7.11 (2018-06-11)
-------------------

- unicode bugfixes.

1.7.10 (2018-06-06)
-------------------

- fix descriptor decoding errors;
- minor bugfixes.

1.7.9 (2018-06-05)
------------------

- fix UnicodeError in exif;
- workaround for irregular descriptor name;
- add undocumented `extn` tagged block decoding;
- move duplicated icc module to subpackage;
- support PIL rendering with extra alpha channels.

1.7.8 (2018-05-29)
------------------

- update documentation;
- fix PEP8 compliance;
- rename merge_layers to compose.

1.7.7 (2018-05-02)
------------------

- fix white background issue in `as_PIL()`.

1.7.6 (2018-04-27)
------------------

- add quality testing;
- fix disabled mask.

1.7.5 (2018-04-25)
------------------

- fix `has_mask()` condition;
- add mask composition in `merge_layers()`;
- fix mask display.

1.7.4 (2018-03-06)
------------------

- fix infinity loop in `print_tree()`.

1.7.3 (2018-02-27)
------------------

- add vector origination API;
- fix shape and vector mask identification;
- change enum name conversion;
- update docs.

1.7.2 (2018-02-14)
------------------

- add adjustments API;
- add mask API;
- bugfix for tagged_blocks decoders.

1.7.1 (2018-02-08)
------------------

- add mask user API;
- add layer coordinate user API;
- add vector mask and vector stroke API;
- cleanup user API;
- add automatic descriptor conversion.


1.7.0 (2018-01-25)
------------------

- cleanup user API organization;
- remove json encoder api;
- make cli a package main.

1.6.7 (2018-01-17)
------------------

- workaround for anaconda 2.7 pillow;
- bbox existence checkf.

1.6.6 (2018-01-10)
------------------

- experimental clipping support in `merge_layer()`;
- revert `as_PIL()` in `AdjustmentLayer`.

1.6.5 (2017-12-22)
------------------

- Small fix for erroneous unicode path name

1.6.4 (2017-12-20)
------------------

- Add `all_layers()` method;
- Add `_image_resource_blocks` property;
- Add `thumbnail()` method.

1.6.3 (2017-09-27)
------------------

- documentation updates;
- github repository renamed to psd-tools2;
- AdjustmentLayer fix.

1.6.2 (2017-09-13)
------------------

- layer class structure reorganization;
- add Effects API;
- add TypeLayer API methods.

1.6 (2017-09-08)
----------------

- PSDImage user API update;
- user API adds distinct layer types;
- Sphinx documentation.

1.5 (2017-07-13)
----------------

- implemented many decodings of image resources and tagged blocks;
- implemented EngineData text information;
- user API for getting mask and patterns;
- user API to calculate bbox for shape layers;

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
