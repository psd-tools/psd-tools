from __future__ import print_function, unicode_literals

import logging
import sys

import pytest

from psd_tools.__main__ import main

from .utils import full_name

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(
    "argv",
    [
        [
            "export",
            full_name("layers/pixel-layer.psd"),
        ],
        [
            "export",
            full_name("layers/pixel-layer.psd[0]"),
            "--verbose",
        ],
        [
            "show",
            full_name("layers/pixel-layer.psd"),
        ],
        [
            "debug",
            full_name("layers/pixel-layer.psd"),
        ],
        [
            "-h",
        ],
        [
            "--version",
        ],
    ],
)
def test_main(argv, tmpdir):
    if argv[0] == "export":
        argv.append(tmpdir.join("output.png").strpath)

    with pytest.raises(SystemExit):
        main(argv)
        sys.exit()
