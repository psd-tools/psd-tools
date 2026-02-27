# psd-tools

`psd-tools` is a Python package for working with Adobe Photoshop PSD files
as described in [specification](https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/).

[![PyPI Version](https://img.shields.io/pypi/v/psd-tools.svg)](https://pypi.python.org/pypi/psd-tools)
[![Tests](https://github.com/psd-tools/psd-tools/actions/workflows/test.yml/badge.svg)](https://github.com/psd-tools/psd-tools/actions/workflows/test.yml)
[![Document Status](https://readthedocs.org/projects/psd-tools/badge/)](http://psd-tools.readthedocs.io/en/latest/)

## Features

### Supported

- Read and write of the low-level PSD/PSB file structure
- Raw layer image export in NumPy and PIL format

### Limited support

- Composition of basic pixel-based layers
- Composition of fill layer effects
- Vector masks
- Editing of some layer attributes such as layer name
- Basic editing of pixel layers and groups, such as adding or removing a layer
- Blending modes except for dissolve
- Drawing of bezier curves

### Not supported

- Editing of various layers such as type layers, shape layers, smart objects, etc.
- Editing of texts in type layers
- Composition of adjustment layers
- Composition of many layer effects
- Font rendering

## Installation

Use `pip` to install the package:

```bash
pip install psd-tools
```

For advanced layer compositing features, install with the `composite` extra:

```bash
pip install 'psd-tools[composite]'
```

The composite extra provides optional dependencies (`aggdraw`, `scipy`, `scikit-image`)
for advanced rendering features:

- Vector shape and stroke rendering
- Gradient and pattern fills
- Layer effects rendering

Basic compositing works without these dependencies using cached previews or simple
pixel-based operations. Note that the composite extra may not be available on all
platforms (notably Python 3.14 on Windows).

## Getting started

```python
from psd_tools import PSDImage

psd = PSDImage.open('example.psd')
psd.composite().save('example.png')

for layer in psd:
    print(layer)
    layer_image = layer.composite()
    layer_image.save('%s.png' % layer.name)
```

Check out the [documentation](https://psd-tools.readthedocs.io/) for features and details.

## Contributing

See [contributing](https://github.com/psd-tools/psd-tools/blob/main/docs/contributing.rst) page.

> **Note**
>
> PSD [specification](https://www.adobe.com/devnet-apps/photoshop/fileformatashtml/) is far from complete. If you cannot find a desired
> information in the [documentation](https://psd-tools.readthedocs.io/), you should inspect the low-level
> data structure.
