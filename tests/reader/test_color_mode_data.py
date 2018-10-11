from io import BytesIO
from psd_tools.reader.color_mode_data import read, write


def test_read_write():
    data = b'xxxxxxxxxxxxxxxx'
    with BytesIO() as f:
        write(f, data)
        f.flush()
        f.seek(0)
        data2 = read(f)
    assert data == data2
