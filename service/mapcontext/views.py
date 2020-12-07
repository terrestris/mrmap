"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from MrMap.decorator import check_permission
from service.mapcontext.helper import map_context
from service.mapcontext.wizard import NewMapContextWizard, NEW_MAPCONTEXT_WIZARD_FORMS
from service.models import MapContext
from structure.permissionEnums import PermissionEnum


@login_required
@check_permission(
    PermissionEnum.CAN_REGISTER_RESOURCE
)
def add_mapcontext(request: HttpRequest):
    """ Renders wizard page configuration for map context registration

        Args:
            request (HttpRequest): The incoming request
            user (User): The performing user
        Returns:
             params (dict): The rendering parameter
    """
    return NewMapContextWizard.as_view(
        form_list=NEW_MAPCONTEXT_WIZARD_FORMS,
        current_view=request.GET.get('current-view'),
        # TODO translate me
        title=_(format_html('<b>Add New Map Context</b>')),
        id_wizard='add_new_mapcontext_wizard',
    )(request=request)


def get_mapcontext_atom(request: HttpRequest, context_id):
    context = MapContext.objects.get(id=context_id)
    owc_context = map_context(context)
    atom = owc_context.to_atomxml()
    #return HttpResponse(atom, content_type="application/atom+xml")
    return HttpResponse(atom, content_type="application/xml")


def get_mapcontext_json(request: HttpRequest, context_id):
    context = MapContext.objects.get(id=context_id)
    owc_context = map_context(context)
    json = owc_context.to_json()
    return HttpResponse(json, content_type="application/geo+json")
