from enum import Enum

from django.utils.html import format_html
from django.utils.safestring import SafeString

from MrMap.enums import EnumChoice


class IconEnum(EnumChoice):
    POWER_OFF = "fas fa-power-off"
    PROXY = "fas fa-archway"
    LOGGING = "fas fa-file-signature"
    WFS = "fas fa-draw-polygon"
    FEATURETYPE = "fas fa-draw-polygon"
    WMS = "far fa-map"
    LAYER = "fas fa-layer-group"
    CSW = "fas fa-book"
    DATASET = "fas fa-clipboard-list"
    PASSWORD = "fas fa-lock"
    HEARTBEAT = "fas fa-heartbeat"
    PENDING_TASKS = "fas fa-tasks"
    INFO = "fas fa-info"
    CAPABILITIES = "fas fa-file-code"
    NEWSPAPER = "far fa-newspaper"
    METADATA = "fas fa-file-alt"
    ERROR = "fas fa-exclamation-circle"
    PLAY = "fas fa-play"
    LOGS = "fas fa-stethoscope"
    DOWNLOAD = "fas fa-download"
    PUBLIC = "fas fa-globe"
    EDIT = "fas fa-edit"
    ACCESS = "fas fa-key"
    SUBSCRIPTION = "fas fa-bullhorn"
    DELETE = "fas fa-trash"
    GROUP = "fas fa-users"
    SIGNOUT = "fas fa-sign-out-alt"
    PUBLISHERS = "fas fa-address-card"
    ADD = "fas fa-plus-circle"
    OK = "fas fa-check"
    NOK = "fas fa-times"
    ORGANIZATION = "fas fa-building"
    USER = "fas fa-user"
    USER_ADD = "fa fa-user-plus"
    USER_REMOVE = "fa fa-user-times"
    MONITORING = "fas fa-binoculars"
    MONITORING_RUN = "fas fa-running"
    MONITORING_RESULTS = "fas fa-poll-h"
    WARNING = 'fas fa-exclamation-triangle'
    CRITICAL = 'fas fa-bolt'


def get_icon(enum: IconEnum) -> SafeString:
    pattern = "<i class=\'{}\'></i>"
    return format_html(pattern, enum.value)


def get_all_icons() -> dict:
    icons = {}
    for enum in IconEnum:
        icons.update({enum.name: get_icon(enum)})
    return icons
