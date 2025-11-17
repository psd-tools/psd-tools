# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Setup

```bash
# Install dependencies
uv sync

# Install with composite support (required for rendering/compositing)
uv sync --extra composite

# Install with development dependencies using uv
uv sync --group dev

# Install with docs dependencies using uv
uv sync --group docs

# Install with all groups (dev and docs) and composite extra
uv sync --all-groups --extra composite
```

**Note**: The `composite` extra includes `aggdraw`, `scipy`, and `scikit-image` dependencies
required for layer compositing (rendering). These are optional since they may not be available
on all platforms (notably Python 3.14 on Windows).

### Testing

```bash
# Run all tests with coverage
uv run pytest

# Run specific test file
uv run pytest tests/psd_tools/api/test_layers.py

# Run specific test
uv run pytest tests/psd_tools/api/test_layers.py::test_layer_name

# Run tests without coverage
uv run pytest --no-cov
```

### Linting and Type Checking

```bash
# Run ruff linter
uv run ruff check src/

# Run mypy type checker
uv run mypy src/psd_tools

# Format with ruff
uv run ruff format src/
```

### Documentation

```bash
# Build HTML documentation
cd docs
make html
# Output in docs/_build/html/
```

### Building

```bash
# Build wheel
uv build --wheel
```

## Architecture Overview

### Two-Layer Design

psd-tools has a clear separation between low-level binary parsing and high-level user API:

**Low-Level Layer (`psd_tools.psd`)**: Reads/writes raw PSD binary format following Adobe's specification. All classes use `attrs` and implement `read(fp)` and `write(fp)` methods for binary serialization.

**High-Level API (`psd_tools.api`)**: Provides Pythonic interfaces for users. The `PSDImage` class wraps the low-level `PSD` structure and reconstructs the layer tree from the flat layer record list.

### Key Subpackages

- **`psd_tools.psd`**: Binary structure parsing (header, layer records, tagged blocks, descriptors, image resources)
- **`psd_tools.api`**: User-facing API (`PSDImage`, layer types, effects, masks)
- **`psd_tools.composite`**: Rendering engine (blend modes, effects, vector rasterization)
- **`psd_tools.compression`**: Compression codecs (Raw, RLE, ZIP). Includes Cython-optimized RLE in `_rle.pyx`

### File Format Structure

PSD files consist of five sequential sections:

1. **File Header** (26 bytes): Signature, version, dimensions, color mode
2. **Color Mode Data**: Palette data for indexed color mode
3. **Image Resources**: Document metadata (color profiles, guides, thumbnails)
4. **Layer and Mask Information**: Layer records + channel image data + tagged blocks
5. **Image Data**: Flattened composite image

### Layer Tree Reconstruction

PSD stores layers as a **flat list** with implicit hierarchy. The `SectionDivider` tagged block marks group boundaries:

```text
Record 0: "Background" (normal layer)
Record 1: "Group" (BOUNDING_SECTION_DIVIDER = group start)
Record 2:   "Child 1" (inside group)
Record 3:   "Child 2" (inside group)
Record 4: (END_SECTION_DIVIDER = group end)
```

`PSDImage` reconstructs this into a tree structure with parent-child relationships.

### BaseElement Pattern

All binary structures inherit from `BaseElement` and implement:

```python
@classmethod
def read(cls, fp: BinaryIO, **kwargs) -> Self:
    """Read from file pointer"""

def write(self, fp: BinaryIO, **kwargs) -> int:
    """Write to file pointer, return bytes written"""
```

This enables recursive composition of complex structures from simple primitives.

### Attrs-Based Classes

The codebase uses `attrs` for all data classes:

```python
from attrs import define, field

@define(repr=False)
class FileHeader(BaseElement):
    signature: bytes = field(default=b"8BPS")
    version: int = field(default=1)
    channels: int = field(default=4)
    # ...
```

Benefits: automatic `__init__`, validation, type hints, easy tuple conversion with `astuple()`.

### Tagged Blocks System

PSD uses an extensible "tagged blocks" system for metadata. Each block has a 4-byte `Tag` key and associated data:

```python
# Check if tag exists
if Tag.UNICODE_LAYER_NAME in layer._record.tagged_blocks:
    name = layer._record.tagged_blocks.get_data(Tag.UNICODE_LAYER_NAME)
```

Registry pattern maps tags to handler classes using `@register(Tag.FOO)`.

### Performance Optimizations

1. **Cython RLE Codec** (`compression/_rle.pyx`): C++ implementation for fast RLE compression/decompression. Falls back to pure Python if not compiled.

2. **Lazy Loading**: API layer only parses data on access (masks, effects, channel data).

3. **NumPy Vectorization**: Compositing engine uses NumPy arrays for efficient blend mode calculations.

## Important Files

- **`src/psd_tools/psd/__init__.py`**: Main `PSD` class representing the complete file
- **`src/psd_tools/api/psd_image.py`**: `PSDImage` user-facing API
- **`src/psd_tools/api/layers.py`**: Layer type hierarchy
- **`src/psd_tools/psd/layer_and_mask.py`**: Layer records and channel data
- **`src/psd_tools/psd/tagged_blocks.py`**: Tagged block registry and handlers
- **`src/psd_tools/psd/descriptor.py`**: Adobe's descriptor format (key-value serialization)
- **`src/psd_tools/composite/__init__.py`**: `Compositor` class
- **`src/psd_tools/constants.py`**: Enums for color modes, blend modes, tags, etc.
- **`src/psd_tools/terminology.py`**: Adobe's 4-byte identifier mappings

## Common Patterns

### Reading a PSD File

```python
from psd_tools import PSDImage

psd = PSDImage.open('example.psd')
for layer in psd:
    print(layer.name, layer.kind)
```

### Accessing Low-Level Structure

```python
# Get the raw PSD object
raw_psd = psd._record  # type: psd_tools.psd.PSD

# Access header
header = raw_psd.header  # FileHeader

# Access layer records (flat list)
layer_records = raw_psd.layer_and_mask_information.layer_info.layer_records
```

### Modifying Layers

```python
layer.name = "New Name"
layer.opacity = 128
layer.blend_mode = BlendMode.MULTIPLY
psd.save('modified.psd')  # Automatically marks as dirty
```

### Compositing

**Note**: Compositing requires optional dependencies. Install with `pip install 'psd-tools[composite]'`

```python
# Composite entire document
image = psd.composite()  # Returns PIL Image
image.save('output.png')

# Composite specific layer
layer_image = layer.composite()
```

If composite dependencies are not installed, calling `.composite()` will raise an `ImportError`
with instructions on how to install the required packages.

## Testing Conventions

- Tests are organized to mirror the package structure: `tests/psd_tools/psd/` for low-level, `tests/psd_tools/api/` for high-level
- Fixture PSD files are in `tests/psd_files/`
- Tests often use parametrization over multiple fixture files
- Round-trip validation is common: read → modify → write → read → verify

## Type Annotations

Recent work has added comprehensive type annotations throughout the codebase. When adding new code:

- Use proper type hints for all function signatures
- Use `typing_extensions.Self` for methods returning instances of the same class
- Use `typing.Optional` for nullable fields
- Attrs validators should match type hints

## Known Limitations

- **Type layers**: Cannot render text (no font engine)
- **Adjustment layers**: Limited compositing support
- **Layer effects**: Only basic effects supported (drop shadow, stroke)
- **Smart objects**: Can extract/embed but not edit contents
- **Unknown data**: Preserved as bytes during round-trip but not interpreted

## Dependencies

**Core**: `attrs`, `Pillow`, `numpy`

**Optional (composite extra)**: `scipy`, `scikit-image`, `aggdraw` - Required for layer compositing/rendering

**Dev**: `pytest`, `pytest-cov`, `ruff`, `mypy`, plus composite dependencies for testing

**Build-time optional**: `Cython` (for RLE optimization)
