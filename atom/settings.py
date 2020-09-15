"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 15.09.20

"""

import logging


atom_logger = logging.getLogger('MrMap.service')


DEFAULT_IMAGE_RESOLUTION = 300  # the value is representing dpi
DEFAULT_MAX_WIDTH = 2048  # the value is representing pixel
DEFAULT_MAX_HEIGHT = 2048  # the value is representing pixel
CONVERSION_FACTOR_INCH_TO_METER = 0.0254
METER_BASED_CRS = 3857
