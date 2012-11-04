
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
