1.10.11 (2025-09-24)
--------------------

- [tests] Drop python2 compatibility code (#494)
- [api] Fix clip layer handling (#493)
- [psd] Workaround CAI tagged block reconstruction (#492)

1.10.10 (2025-09-18)
--------------------

- [api] Fix clipping with stroke composite (#489)
- [ci] Fix documentation build (#486, #487)
- [ci] Introduce ABI3 wheels (#483, #485)
- [api] Fix PyCMSError in composite (#484)
- [api] Fix ImageMath deprecation warning (#482)

1.10.9 (2025-08-07)
-------------------

- [psd] Allow linked layer version 8 (#476)

1.10.8 (2025-06-06)
-------------------

- [ci] Update CI configuration (#471)
- [psd] Workaround levels adjustment layer parsing (#470)
- [psd] Support CAI, GenI, OCIO tagged blocks (#469)

1.10.7 (2025-02-25)
-------------------

- [psd] Fix missing gradient method (#465)

1.10.6 (2025-02-18)
-------------------

- [security] Update pillow dependency (#462)

1.10.5 (2025-02-18)
-------------------

- [security] Update pillow dependency (#461)

1.10.4 (2024-11-25)
-------------------

- [api] Allow Path objects for PSDImage open (#452)

1.10.3 (2024-11-20)
-------------------

- [psd] Fix data corruption by irregular OSType (#449)
- [api] Add type annotation to the high-level APIs (#448)


1.10.2 (2024-10-23)
-------------------

- [api] Add channel info via DisplayInfo (#443)
- [api] Support layer locking (#442)


1.10.1 (2024-10-10)
-------------------

- [api] Fix artboard creation (#438)
- [api] Fix layer conversion issue (#435)

1.10.0 (2024-09-26)
-------------------

- [api] Support basic layer structure editing (#428)
- [api] Drop deprecated compose module (#432)

1.9.34 (2024-07-01)
-------------------

- [api] Support text type property (#419)
- [psd] Improve RLE decoding error handling (#417)

1.9.33 (2024-06-14)
-------------------

- [psd] Raise IO error instead of assertion (#413)
- [api] Add a new property to SmartObject: transform_box (#412)
- [ci] Migrate code formatter to ruff (#408)

1.9.32 (2024-05-01)
-------------------

- [psd] Fix incorrect group divider handling (#399)

1.9.31 (2024-02-26)
-------------------

- [psd] Reworked packbits/rle algorithms (#392)

1.9.30 (2024-01-06)
-------------------

- [ci] Fix missing pyx file in sdist (#386)

1.9.29 (2024-01-04)
-------------------

- [ci] Update CI configuration (#383)
- [dev] Migrate the builder to pyproject.toml
- [dev] Update linter and formatter to pysen
- [dev] Deprecate tox
- [psd] Add new color sheet (#380)
- [psd] Fix transparency check (#370)

1.9.28 (2023-07-04)
-------------------

- [psd] Add alternate 8ELE signiture for 8BIM tagged block (#367)

1.9.27 (2023-06-27)
-------------------

- [composite] Fix regression by #361 (#364)

1.9.26 (2023-06-21)
-------------------

- [composite] Read HSB colors in RGB and CMYK color modes (#361)
- [ci] Update CI configuration (#362)

1.9.25 (2023-06-19)
-------------------

- [composite] Fix hue, sat, and vivid light (#359)

1.9.24 (2023-01-17)
-------------------

- [psd] Support float RGB values (#350)
- [psd] Workaround stroke class ID (#346)
- [ci] Update CI configuration (#347)
- [composite] Fix group clipping (#336)

1.9.23 (2022-09-26)
-------------------

- [api] Add bbox invalidation when toggling layer visibility (#334)

1.9.22 (2022-09-09)
-------------------

- [psd] Add support for v3 gradient map adjustment layer (#330)


1.9.21 (2022-06-18)
-------------------

- [api] Fix incorrect has_effects behavior (#322)
- [composite] Improve blending numerical stability (#321)
- [composite] Improve non-RGB modes and transparency (#319, @Etienne-Gautier)
- [psd] Workaround assertion error in broken file (#320)

1.9.20 (2022-05-16)
-------------------

- [ci] Update CI configuration (#313 #314)
- [composite] Fix composite errors (#312)
- [psd] Suppress vowv tagged blocks (#306)

1.9.19 (2022-04-15)
-------------------

- [composite] Fix rasterized shape composite (#301 #302)

1.9.18 (2021-08-20)
-------------------

- [api] Fix missing effect attributes (#284)
- [package] Support additional platforms (i686, aarch64, universal2, win32)
- [package] Drop py36 support

1.9.17 (2021-01-15)
-------------------

- [api] Fix incorrect fill layer parse (fix #254)

1.9.16 (2020-09-24)
-------------------

- [package] Drop py27 and py35 support
- [psd] Workaround Enum bug (fix #241)
- [composite] Fix transparency issue (fix #242)
- [composite] Fix mask disable flag (fix #243)
- [api] Add workaround for creating PSB (fix #246)
- [api] Fix incorrect adjustment parse (fix #247)

1.9.15 (2020-07-17)
-------------------

- [composite] Fix ignored clip layers for groups.
- [composite] Fix out-of-viewport stroke effect.

1.9.14 (2020-07-10)
-------------------

- [api] Bugfix for PSDImage composite layer_filter option.
- [api] Bugfix for transparency and alpha distinction.
- [psd] Rename COMPOSITOR_INFO.
- [composite] Fix stroke effect target shape.

1.9.13 (2020-05-25)
-------------------

- [api] Bugfix for PSDImage init internal.

1.9.12 (2020-05-20)
-------------------

- [psd] Bugfix for CurvesExtraMarker read.

1.9.11 (2020-05-01)
-------------------

- [composite] Fix layer check.

1.9.10 (2020-04-21)
-------------------

- [psd] Fix engine data parser.

1.9.9 (2020-03-30)
------------------

- [composite] Fix stroke effect argument.

1.9.8 (2020-03-18)
------------------

- [composite] Fix incorrect fill opacity handling in compositing.
- [composite] Fix incorrect alpha for patterns.

1.9.7 (2020-03-17)
------------------

- [composite] Fix path operation for merged components.
- [composite] Fix vector mask compositing condition.

1.9.6 (2020-03-16)
------------------

- [composite] Fix incorrect alpha channel handling in composite.

1.9.5 (2020-03-11)
------------------

- [api] Add ignore_preview option to `PSDImage.composite`.
- [composite] Improve stroke effect composition for vector masks.
- [composite] Avoid crash when there is an erroneous subpath.
- [composite] Workaround possible divide-by-zero warn in stroke composition.
- [composite] Fix incorrect pattern transparency handling.
- [composite] Fix ignored effects in direct group composition.
- [composite] Fix incorrect opacity handling for clip layers.

1.9.4 (2020-03-11)
------------------

- [compression] Security fix, affected versions are 1.8.37 - 1.9.3.

1.9.3 (2020-03-10)
------------------

- [composite] Fix memory corruption crash for pattern data in PSB files.
- [psd] Add image data pretty printing.

1.9.2 (2020-03-03)
------------------

- [psd] Add missing resource ID.
- [psd] Fix pretty printing regression.
- [psd] Fix big tag key for linked layers.
- [psd] Support frgb tag.
- [psd] Support sgrp metadata key.
- [psd] Support patt tag.
- [psd] Workaround unknown engine data.

1.9.1 (2020-02-28)
------------------

- [psd] Minor bugfix.

1.9.0 (2020-02-26)
------------------

- [composite] Implement NumPy-based compositing functionality.
- [composite] Support blending modes other than dissolve.
- [composite] Support blending in RGB, CMYK, Grayscale.
- [api] Introduce NumPy array export method.
- [api] Drop deprecated methods from v1.7.x such as `as_PIL`.
- [api] Deprecate `compose` method.
- [compression] Rename packbits to rle.
- [compression] Improve RLE decode efficiency.
- [tests] Additional compositing tests.

1.8.38 (2020-02-12)
-------------------

- [composer] fix crash when gradient fill is in stroke.

1.8.37 (2020-02-07)
-------------------

- [compression] Remove packbits dependency and introduce cython implementation.
- [deploy] Move CI provider from Travis-CI to Github Actions.
- [deploy] Start distributing binary wheels.

1.8.36 (2019-12-26)
-------------------

- [psd] add safeguard for malformed global layer mask info parser.

1.8.35 (2019-12-26)
-------------------

- [api] remove duplicate `has_mask()` definition.
- [composer] fix empty effects check.

1.8.34 (2019-11-28)
-------------------

- [api] fix `compose()` arguments.
- [psd] fix attrs version dependency.

1.8.33 (2019-11-28)
-------------------

- [api] add `include_invisible` option to `Group.extract_bbox`.
- [psd] fix deprecated attrs api.


1.8.32 (2019-11-28)
-------------------

- [psd] fix 16/32 bit file parsing bug introduced in 1.8.17.

1.8.31 (2019-11-27)
-------------------

- [psd] bugfix reading psb.
- [psd] bugfix reading slices resource.
- [security] update dependency to pillow >= 6.2.0.

1.8.30 (2019-09-24)
-------------------

- [psd] workaround for reading less-than-4-byte int in malformed psd files.

1.8.29 (2019-09-10)
-------------------

- [composer] fix vector mask bbox in composition.

1.8.28 (2019-09-09)
-------------------

- [api] fix `Effects.__repr__()` when data is empty.

1.8.27 (2019-08-29)
-------------------

- [api] accept encoding param in `PSDImage.open` and `PSDImage.save`.
- [deploy] bugfix travis deployment condition.


1.8.26 (2019-08-28)
-------------------

- [composer] support group mask.

1.8.25 (2019-08-07)
-------------------

- [api] change return type of `PSDImage.color_mode` to enum.
- [api] support reading of bitmap color mode.
- [api] support channel option in `topil()` method.

1.8.24 (2019-07-25)
-------------------

- [composer] experimental support of commutative blending modes.

1.8.23 (2019-06-24)
-------------------

- [composer] fix clipping on alpha-less image;
- [composer] fix stroke effect for flat plane;
- [composer] workaround for insufficient knots;
- [composer] fix for custom color space.

1.8.22 (2019-06-19)
-------------------

- fix pass-through composing bug;
- fix alpha blending in effect;
- fix vector mask composition;
- experimental support for shape stroke;
- experimental support for stroke effect.

1.8.21 (2019-06-18)
-------------------

- change effect property return type from str to enum;
- improve gradient quality;
- support fill opacity and layer opacity;
- add tmln key in metadata setting.

1.8.20 (2019-06-13)
-------------------

- support gradient styles.

1.8.19 (2019-06-11)
-------------------

- fix broken `psd_tools.composer.vector` module in 1.8.17;
- experimental support for color noise gradient;
- bugfix for clip masks;
- bugfix for CMYK composing.

1.8.17 (2019-06-05)
-------------------

- move `psd_tools.api.composer` module to `psd_tools.composer` package;
- support 19 blending modes in composer;
- support fill opacity;
- fix image size when composing with masks;
- rename `TaggedBlockID` to `Tag`;
- rename `ImageResourceID` to `Resource`;
- add `bytes` mixin to `Enum` constants;
- replace `Enum` keys with raw values in `psd_tools.psd.base.Dict` classes.

1.8.16 (2019-05-24)
-------------------

- fix broken group compose in 1.8.15;
- fix missing pattern / gradient composition in vector stroke content.

1.8.15 (2019-05-23)
-------------------

- coding style fix;
- fix `compose()` bbox option.

1.8.14 (2019-04-12)
-------------------

- add dependency to aggdraw;
- support bezier curves in vector masks;
- support path operations;
- fix `compose(force=True)` behavior;
- fix default background color in composer;
- improve pattern overlay parameters support;
- fix gradient map generation for a single stop.

1.8.13 (2019-04-05)
-------------------

- fix engine_data unknown tag format;
- fix compose for extra alpha channels;
- workaround for pillow 6.0.0 bug.

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
- fixed synchronization in case of ``8B64`` signatures (thanks Evgeny Kopylov);
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
