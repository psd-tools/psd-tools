from io import BytesIO
from psd_tools.reader.header import PsdHeader, read, write
from psd_tools.constants import ColorMode


def test_read_write():
    header = PsdHeader(1, 3, 120, 180, 8, ColorMode.RGB)
    with BytesIO() as f:
        write(f, header)
        f.flush()
        f.seek(0)
        header2 = read(f)
    for i in range(len(header)):
        assert header[i] == header2[i]
