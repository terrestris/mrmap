"""
Author: Jonas Kiefer
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: jonas.kiefer@vermkv.rlp.de
Created on: 13.02.2020


This file holds all global constants
"""
from MapSkinner.utils import get_theme


DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE = "sceletons/django_tables2_bootstrap4_custom.html"


SERVICE_INDEX = "service:index"
SERVICE_DETAIL = "service:detail"

STRUCTURE_DETAIL_GROUP = "structure:detail-group"
STRUCTURE_INDEX_GROUP = "structure:groups-index"

APP_XML = "application/xml"

URL_PATTERN = "<a class={} href='{}'>{}</a>"
URL_PATTERN_BTN_DANGER = "<a class='btn btn-sm " + get_theme()["TABLE"]["BTN_DANGER_COLOR"] + "' href='{}'>{}</a>"
URL_PATTERN_BTN_INFO = "<a class='btn btn-sm " + get_theme()["TABLE"]["BTN_INFO_COLOR"] + "' href='{}'>{}</a>"
URL_PATTERN_BTN_WARNING = "<a class='btn btn-sm " + get_theme()["TABLE"]["BTN_WARNING_COLOR"] + "' href='{}'>{}</a>"


