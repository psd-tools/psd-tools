Overview
========

``psd-tools2`` is a package for reading Adobe Photoshop PSD files as described
in specification_ to Python data structures. ``psd-tools2`` is a fork of
psd-tools_ that adds a couple of enhancements to the original version.

.. _specification: https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/PhotoshopFileFormats.htm

.. _psd-tools: https://github.com/psd-tools/psd-tools


Getting started
---------------

Check out the :doc:`usage` documentation.

:doc:`development` page describes the package design and development utilities.

Features
--------

Supported:

* reading of RGB, RGBA, CMYK, CMYKA and Grayscale images;
* 8bit, 16bit and 32bit channels;
* all PSD compression methods are supported (not only the most
  common RAW and RLE);
* image ICC profile is taken into account;
* many image resource types and tagged block types are decoded;
* layer effects information is decoded;
* Descriptor structures are decoded;
* there is an optional Cython extension to make the parsing fast;
* very basic & experimental layer merging;
* support both PSD and PSB file formats;
* EngineData structure is decoded;
* EXIF data is taken into account.

Not implemented:

* reading of Duotone, LAB, etc. images;
* some image resource types and tagged blocks are not decoded
  (they are attached to the result as raw bytes);
* some of the raw Descriptor values are not decoded;
* this library can't reliably blend layers together: it is possible to export
  a single layer and to export a final image, but rendering of
  e.g. layer group may produce incorrect results;
* the writing of PSD images is not implemented;
* Pymaging_ support is limited: it only supports 8bit RGB/RGBA
  images, ICC profiles are not applied, layer merging doesn't work, etc.

If you need some of unimplemented features then please file an issue
or implement it yourself (pull requests are welcome in this case).

.. _Pymaging: https://github.com/ojii/pymaging
