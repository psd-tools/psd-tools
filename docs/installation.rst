Installation
============

Use ``pip`` to install the package.

::

    pip install psd-tools2

Pillow_ should be installed if you want work with PSD image and layer data:
export images to PNG, process them. PIL_ library should also work.

::

   pip install Pillow

.. note::

    In order to extract images from 32bit PSD files PIL/Pillow must be built
    with LITTLECMS or LITTLECMS2 support.

psd-tools2 also has a rudimentary support for Pymaging_.
`Pymaging installation instructions`_ are available in pymaging docs.

.. _PIL: http://www.pythonware.com/products/pil/
.. _Pillow: https://github.com/python-imaging/Pillow
.. _packbits: http://pypi.python.org/pypi/packbits/
.. _Pymaging: https://github.com/ojii/pymaging
.. _Pymaging installation instructions: http://pymaging.readthedocs.org/en/latest/usr/installation.html
.. _exifread: https://github.com/ianare/exif-py
