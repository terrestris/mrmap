"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
from django.http import HttpRequest, HttpResponse

from service.mapcontext.helper import map_context
from service.models import MapContext


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
