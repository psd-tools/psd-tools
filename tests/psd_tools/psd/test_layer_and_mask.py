from typing import Any, Dict, Tuple
import io
import logging
import struct

import pytest

from psd_tools.constants import ChannelID, Compression, Tag
from psd_tools.psd.layer_and_mask import (
    ChannelData,
    ChannelDataList,
    ChannelImageData,
    ChannelInfo,
    GlobalLayerMaskInfo,
    LayerAndMaskInformation,
    LayerBlendingRanges,
    LayerFlags,
    LayerInfo,
    LayerRecord,
    LayerRecords,
    MaskData,
    MaskFlags,
    MaskParameters,
)
from psd_tools.psd.tagged_blocks import IntegerElement, TaggedBlock, TaggedBlocks

from ..utils import check_read_write, check_write_read

logger = logging.getLogger(__name__)


def test_layer_and_mask_information() -> None:
    check_write_read(LayerAndMaskInformation())


def test_layer_info() -> None:
    check_write_read(LayerInfo())

    layer_records = LayerRecords(
        [
            LayerRecord(  # type: ignore[list-item]
                channel_info=[
                    ChannelInfo(id=0, length=18),
                    ChannelInfo(id=-1, length=18),
                ]
            )
        ]
    )
    channel_image_data = ChannelImageData(
        [
            ChannelDataList(  # type: ignore[list-item]
                [
                    ChannelData(0, b"\xff" * 16),  # type: ignore[list-item]
                    ChannelData(0, b"\xff" * 16),  # type: ignore[list-item]
                ]
            )
        ]
    )

    check_write_read(LayerInfo(1, layer_records, channel_image_data))


def test_channel_info() -> None:
    check_write_read(ChannelInfo(id=0, length=1), version=1)
    check_write_read(ChannelInfo(id=0, length=1), version=2)


@pytest.mark.parametrize(
    ["args"],
    [
        ((False, False, False, False, False),),
        ((True, True, True, True, True),),
    ],
)
def test_layer_flags_wr(args: Tuple[bool, ...]) -> None:
    check_write_read(LayerFlags(*args))


@pytest.mark.parametrize(
    ["fixture"],
    [
        (b"(",),
        (b"\t",),
    ],
)
def test_layer_flags_rw(fixture: bytes) -> None:
    check_read_write(LayerFlags, fixture)


def test_layer_blending_ranges() -> None:
    check_write_read(LayerBlendingRanges())
    check_write_read(
        LayerBlendingRanges(
            [(0, 1), (0, 1)],
            [
                [(0, 1), (0, 1)],
                [(0, 1), (0, 1)],
                [(0, 1), (0, 1)],
            ],
        )
    )


def test_layer_record() -> None:
    tagged_blocks = TaggedBlocks(
        [  # type: ignore[arg-type]
            (
                Tag.LAYER_VERSION,
                TaggedBlock(key=Tag.LAYER_VERSION, data=IntegerElement(0)),  # type: ignore[arg-type]
            ),
        ]
    )
    check_write_read(LayerRecord())
    check_write_read(LayerRecord(name="foo", tagged_blocks=tagged_blocks))
    check_write_read(LayerRecord(tagged_blocks=tagged_blocks), version=2)


def test_layer_record_channel_sizes() -> None:
    layer_record = LayerRecord(
        left=0,
        top=0,
        right=100,
        bottom=120,
        channel_info=[
            ChannelInfo(id=ChannelID.CHANNEL_0),
            ChannelInfo(id=ChannelID.USER_LAYER_MASK),
            ChannelInfo(id=ChannelID.REAL_USER_LAYER_MASK),
        ],
        mask_data=MaskData(
            left=20,
            top=20,
            right=80,
            bottom=90,
            real_left=10,
            real_top=10,
            real_right=90,
            real_bottom=100,
        ),
    )
    channel_sizes = layer_record.channel_sizes
    assert len(channel_sizes) == 3
    assert channel_sizes[0] == (100, 120)
    assert channel_sizes[1] == (60, 70)
    assert channel_sizes[2] == (80, 90)


def test_mask_flags_wr() -> None:
    check_write_read(MaskFlags())
    check_write_read(MaskFlags(True, True, True, True, True))


@pytest.mark.parametrize(
    ["fixture"],
    [
        (b"(",),
        (b"\t",),
    ],
)
def test_mask_flags_rw(fixture: bytes) -> None:
    check_read_write(MaskFlags, fixture)


@pytest.mark.parametrize(
    ["args"],
    [
        (dict(),),
        (
            dict(
                flags=MaskFlags(parameters_applied=True),
                parameters=MaskParameters(255, 1.0, None, None),
            ),
        ),
        (
            dict(
                real_flags=MaskFlags(True, True, True, True, True),
                real_background_color=255,
                real_top=0,
                real_left=0,
                real_bottom=100,
                real_right=100,
            ),
        ),
        (
            dict(
                flags=MaskFlags(parameters_applied=True),
                parameters=MaskParameters(None, 1.0, None, 1.0),
                real_flags=MaskFlags(True, True, True, True, True),
                real_background_color=255,
                real_top=0,
                real_left=0,
                real_bottom=100,
                real_right=100,
            ),
        ),
    ],
)
def test_mask_data(args: Tuple[Any, ...]) -> None:
    check_write_read(MaskData(**args))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ["fixture"],
    [
        (
            b"\x00\x00\x00\x14\x00\x00\x00\x11\x00\x00\x00\x0c\x00\x00\x00\xb3"
            b"\x00\x00\x00D\x00\x18\x04\xcc",
        ),
    ],
)
def test_mask_data_rw(fixture: bytes) -> None:
    check_read_write(MaskData, fixture)


def test_mask_data_truncated_parameters(caplog: pytest.LogCaptureFixture) -> None:
    """Regression test: MaskData with truncated MaskParameters should not crash.

    Some third-party PSD writers (e.g. game asset exporters on Windows) write a
    MaskData block with parameters_applied=True but only a partial MaskParameters
    payload, filling the remainder with uninitialized memory (MSVC debug patterns
    0xCC/0xCD). psd-tools should tolerate this rather than raising OSError.
    """
    fixture = (
        b"\x00\x00\x00\x26"
        b"\x00\x00\x03\x8b\x00\x00\x00\xdb\x00\x00\x03\xad\x00\x00\x02\x8c"
        b"\x00\x18\x0f\xff\x00\x00\x00\x00\x00\x00\x00\x00\xff\x40\x36\xcc"
        b"\xcc\xcc\xcc\xcc\xcd\x00"
    )
    with caplog.at_level(logging.WARNING):
        with io.BytesIO(fixture) as f:
            mask_data = MaskData.read(f)
    assert mask_data is not None
    assert mask_data.flags.parameters_applied
    assert mask_data.parameters is not None
    assert mask_data.parameters.user_mask_density == 0
    assert mask_data.parameters.vector_mask_density is None
    assert "Truncated MaskParameters" in caplog.text


PARAMETER_FIELDS = (
    "user_mask_density",
    "user_mask_feather",
    "vector_mask_density",
    "vector_mask_feather",
)

PARAMETER_VALUES: Dict[str, Any] = {
    "user_mask_density": 200,
    "user_mask_feather": 3.5,
    "vector_mask_density": 100,
    "vector_mask_feather": 7.25,
}


def _build_mask_data_body(has_real_mask: bool, parameter_bits: int) -> bytes:
    """Synthesize a MaskData body following the PSD byte layout."""
    body = struct.pack(">4iB", 100, 100, 500, 500, 255)
    body += struct.pack(">B", 0x10 if parameter_bits else 0x00)  # parameters_applied
    if has_real_mask:
        body += struct.pack(">BB4i", 0x00, 255, 90, 90, 510, 510)
    if parameter_bits:
        body += struct.pack(">B", parameter_bits)
        if parameter_bits & 1:
            body += struct.pack(">B", PARAMETER_VALUES["user_mask_density"])
        if parameter_bits & 2:
            body += struct.pack(">d", PARAMETER_VALUES["user_mask_feather"])
        if parameter_bits & 4:
            body += struct.pack(">B", PARAMETER_VALUES["vector_mask_density"])
        if parameter_bits & 8:
            body += struct.pack(">d", PARAMETER_VALUES["vector_mask_feather"])
    return body + b"\x00" * (-len(body) % 4)


@pytest.mark.parametrize("has_real_mask", [False, True])
@pytest.mark.parametrize("parameter_bits", [0b1010, 0b1011, 0b1110, 0b1111])
def test_mask_data_real_mask_detection(
    has_real_mask: bool, parameter_bits: int
) -> None:
    """Real mask header presence follows the channel list, not the block length.

    These are the parameter combinations whose block reaches 36 bytes or more
    without a REAL_USER_LAYER_MASK channel, so the old ``length >= 36``
    heuristic read the MaskParameters payload as a real mask header (#693).
    """
    body = _build_mask_data_body(has_real_mask, parameter_bits)
    assert len(body) >= 36  # otherwise the case under test is not exercised

    with io.BytesIO(body) as f:
        mask_data = MaskData._read_body(f, len(body), has_real_mask=has_real_mask)

    assert (mask_data.real_flags is not None) is has_real_mask
    assert mask_data.parameters is not None
    for i, key in enumerate(PARAMETER_FIELDS):
        expected = PARAMETER_VALUES[key] if parameter_bits & (1 << i) else None
        assert getattr(mask_data.parameters, key) == expected


def test_mask_data_parameters_without_real_mask() -> None:
    """Mask data captured from the real-world file reported in #693.

    A layer with both a pixel mask and a vector mask carrying custom density
    and feather, but no REAL_USER_LAYER_MASK channel. The block is 40 bytes,
    so the old heuristic silently returned None for every parameter.
    """
    body = bytes.fromhex(
        "00000a600000074100000d8500000b5bff100fe6"
        "4014000000000000804024000000000000000000"
    )
    with io.BytesIO(body) as f:
        mask_data = MaskData._read_body(f, len(body), has_real_mask=False)

    assert mask_data.real_flags is None
    assert mask_data.parameters == MaskParameters(230, 5.0, 128, 10.0)


def test_mask_data_rw_parameters_without_real_mask() -> None:
    mask_data = MaskData(
        top=100,
        left=100,
        bottom=500,
        right=500,
        background_color=255,
        flags=MaskFlags(parameters_applied=True),
        parameters=MaskParameters(200, 3.5, 100, 7.25),
    )
    with io.BytesIO() as f:
        mask_data.write(f)
        data = f.getvalue()
    with io.BytesIO(data) as f:
        assert MaskData.read(f, has_real_mask=False) == mask_data


def test_layer_record_rw_parameters_without_real_mask() -> None:
    """LayerRecord must derive the real mask flag from its own channel list."""
    parameters = MaskParameters(200, 3.5, 100, 7.25)
    record = LayerRecord(
        top=100,
        left=100,
        bottom=500,
        right=500,
        channel_info=[
            ChannelInfo(id=ChannelID.CHANNEL_0, length=2),
            ChannelInfo(id=ChannelID.USER_LAYER_MASK, length=2),
        ],
        mask_data=MaskData(
            top=100,
            left=100,
            bottom=500,
            right=500,
            background_color=255,
            flags=MaskFlags(parameters_applied=True),
            parameters=parameters,
        ),
        name="mask parameters",
    )
    with io.BytesIO() as f:
        record.write(f)
        data = f.getvalue()
    with io.BytesIO(data) as f:
        parsed = LayerRecord.read(f)

    assert isinstance(parsed.mask_data, MaskData)
    assert parsed.mask_data.real_flags is None
    assert parsed.mask_data.parameters == parameters


def test_mask_parameters() -> None:
    check_write_read(MaskParameters())
    check_write_read(MaskParameters(None, None, None, 1.0))
    check_write_read(MaskParameters(255, None, None, 1.0))
    check_write_read(MaskParameters(None, 1.0, None, 1.0))
    check_write_read(MaskParameters(255, 1.0, 255, None))
    assert MaskParameters().tobytes() == b"\x00"
    assert len(MaskParameters(255, 1.0, 255, 1.0).tobytes()) == 19


def test_mask_parameters_truncated_flag_byte(caplog: pytest.LogCaptureFixture) -> None:
    """The truncation guard must also cover the parameter flag byte itself."""
    with caplog.at_level(logging.WARNING):
        with io.BytesIO(b"") as f:
            parameters = MaskParameters.read(f)
    assert parameters == MaskParameters()
    assert "Truncated MaskParameters" in caplog.text


def test_channel_image_data() -> None:
    check_write_read(ChannelImageData(), layer_records=LayerRecords())

    layer_records = LayerRecords(
        [
            LayerRecord(  # type: ignore[list-item]
                channel_info=[
                    ChannelInfo(id=0, length=18),
                    ChannelInfo(id=-1, length=18),
                ]
            )
        ]
    )
    channel_data_list = ChannelDataList(
        [
            ChannelData(0, b"\xff" * 16),  # type: ignore[list-item]
            ChannelData(0, b"\xff" * 16),  # type: ignore[list-item]
        ]
    )
    check_write_read(ChannelImageData([channel_data_list]), layer_records=layer_records)  # type: ignore[list-item]


def test_channel_data_list() -> None:
    channel_info = [
        ChannelInfo(id=0, length=20),
        ChannelInfo(id=1, length=20),
        ChannelInfo(id=2, length=20),
        ChannelInfo(id=-1, length=20),
    ]
    channel_items = [
        ChannelData(0, b"\x00" * 18),
        ChannelData(0, b"\x00" * 18),
        ChannelData(0, b"\x00" * 18),
        ChannelData(0, b"\x00" * 18),
    ]
    check_write_read(ChannelDataList(channel_items), channel_info=channel_info)  # type: ignore[arg-type]


def test_channel_data() -> None:
    check_write_read(ChannelData(data=b""), length=0)
    check_write_read(ChannelData(data=b"\xff" * 8), length=8)


def test_channel_data_list_zero_length_channel() -> None:
    """Zero-length channel must not advance the file pointer (issue #398).

    Channels with length=0 store their pixel data in a tagged block rather
    than the standard channel image data section.  The parser must skip them
    without reading any bytes so subsequent channels are parsed correctly.
    """
    # Build a stream containing two normal channels (RAW, 2 bytes each)
    # preceded by one zero-length channel.  The zero-length entry must be
    # skipped entirely; if even 1 byte is consumed the stream goes out of
    # sync and the subsequent reads will fail or return wrong data.
    normal_data = b"\x00\x00"  # Compression=RAW (0x0000), no payload
    stream = io.BytesIO(normal_data + normal_data)

    channel_info = [
        ChannelInfo(id=0, length=0),  # zero-length: no bytes in stream
        ChannelInfo(id=1, length=2),  # normal: 2 bytes (compression only)
        ChannelInfo(id=2, length=2),  # normal: 2 bytes (compression only)
    ]
    result = ChannelDataList.read(stream, channel_info)

    assert len(result) == 3  # type: ignore[arg-type]
    assert stream.read() == b"", "file pointer should be at end of stream"
    # The zero-length channel produces a default ChannelData
    assert result[0].data == b""  # type: ignore[index]
    # Subsequent channels were parsed without desync
    assert result[1].compression == Compression.RAW  # type: ignore[index]
    assert result[2].compression == Compression.RAW  # type: ignore[index]


RAW_IMAGE_3x3_8bit = b"\x00\x01\x02\x01\x01\x01\x01\x00\x00"
RAW_IMAGE_2x2_16bit = b"\x00\x01\x00\x02\x00\x03\x00\x04"


@pytest.mark.parametrize(
    "compression, data, width, height, depth, version",
    [
        (Compression.RAW, RAW_IMAGE_3x3_8bit, 3, 3, 8, 1),
        (Compression.RLE, RAW_IMAGE_3x3_8bit, 3, 3, 8, 1),
        (Compression.ZIP, RAW_IMAGE_3x3_8bit, 3, 3, 8, 1),
        (Compression.RAW, RAW_IMAGE_3x3_8bit, 3, 3, 8, 2),
        (Compression.RLE, RAW_IMAGE_3x3_8bit, 3, 3, 8, 2),
        (Compression.ZIP, RAW_IMAGE_3x3_8bit, 3, 3, 8, 2),
        (Compression.RAW, RAW_IMAGE_2x2_16bit, 2, 2, 16, 1),
        (Compression.RLE, RAW_IMAGE_2x2_16bit, 2, 2, 16, 1),
        (Compression.ZIP, RAW_IMAGE_2x2_16bit, 2, 2, 16, 1),
        (Compression.RAW, RAW_IMAGE_2x2_16bit, 2, 2, 16, 2),
        (Compression.RLE, RAW_IMAGE_2x2_16bit, 2, 2, 16, 2),
        (Compression.ZIP, RAW_IMAGE_2x2_16bit, 2, 2, 16, 2),
    ],
)
def test_channel_data_data(
    compression: int, data: bytes, width: int, height: int, depth: int, version: int
) -> None:
    channel = ChannelData(compression)
    channel.set_data(data, width, height, depth, version)
    output = channel.get_data(width, height, depth, version)
    assert output == data, "output=%r, expected=%r" % (output, data)


def test_global_layer_mask_info() -> None:
    check_write_read(GlobalLayerMaskInfo())
