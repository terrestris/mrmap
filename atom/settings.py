"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 15.09.20

"""

import logging

# Logger for this app
atom_logger = logging.getLogger('MrMap.service')

# General settings
WGS_84_CRS = 4326  # epsg:4326 reference system

#  WMS based settings
DEFAULT_IMAGE_RESOLUTION = 300  # the value is representing dpi
DEFAULT_MAX_WIDTH = 2048  # the value is representing pixel
DEFAULT_MAX_HEIGHT = 2048  # the value is representing pixel
CONVERSION_FACTOR_INCH_TO_METER = 0.0254
METER_BASED_CRS = 3857  # epsg:3857 reference system

# WFS based settings
MAXIMUM_FEATURE_COUNT = 100  # the value is representing the count of features we will maximum requesting a wfs
