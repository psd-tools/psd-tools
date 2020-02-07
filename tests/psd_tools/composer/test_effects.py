from __future__ import absolute_import, unicode_literals
import pytest
import logging

from psd_tools import PSDImage

from ..utils import full_name
from .test_composer import _calculate_hash_error

logger = logging.getLogger(__name__)


@pytest.mark.parametrize(("filename", ), [
    ('effects/stroke-effects.psd', ),
])
def test_stroke_effects(filename):
    psd = PSDImage.open(full_name(filename))
    preview = psd.topil().convert('RGB')
    rendered = psd.compose(force=True).convert('RGB')
    assert _calculate_hash_error(preview, rendered) <= 0.1
