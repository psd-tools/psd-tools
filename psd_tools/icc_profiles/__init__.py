# -*- coding: utf-8 -*-
from __future__ import absolute_import
import os
from PyBundle import bundle_dir

GRAY_PATH = os.path.join(bundle_dir(), 'Gray-CIE_L.icc')

try:
    from PIL import ImageCms
    gray = ImageCms.ImageCmsProfile(GRAY_PATH)
    sRGB = ImageCms.createProfile('sRGB')
except ImportError:
    gray = None
    sRGB = None
