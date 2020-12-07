"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
from owslib.owscontext.core import OwcContext, OwcResource, OwcOffering, OwcOperation

from service.models import MapContext, MapResource, WmsOffering


def map_context(context: MapContext):
    resources = []
    for resource in context.mapresource_set.all():
        resources.append(map_resource(resource))
    return OwcContext(id=context.id.hex, update_date=context.last_modified, title=context.title, resources=resources)


def map_resource(resource: MapResource):
    offerings = []
    for offering in resource.wmsoffering_set.all():
        offerings.append(map_wms_offering(offering))
    return OwcResource(id=f"{resource.pk}",
                       title=resource.title,
                       subtitle=resource.abstract,
                       update_date=resource.update_date,
                       offerings=offerings)


def map_wms_offering(wms_offering: WmsOffering):
    wms_layer = wms_offering.layer
    # TODO use public id?
    service_id = wms_layer.parent_service.metadata_id
    wms_url = f"http://localhost:8000/resource/metadata/{service_id}/operation"
    # TODO for GetCapabilities, always use proxied (MrMap) URL
    get_capabilities_url = f"{wms_url}?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetCapabilities"
    # TODO for GetMap, check when to use proxied and when to use external URL
    # TODO use configured BBOX
    # TODO style
    # TODO what to do with width & height?
    get_map_url = f"{wms_url}?SERVICE=WMS&VERSION=1.1.1&request=GetMap"
    operations = [OwcOperation(operations_code="GetCapabilities", http_method="GET", request_url=get_capabilities_url),
                  OwcOperation(operations_code="GetMap", http_method="GET", request_url=get_map_url)]
    return OwcOffering(offering_code="http://www.opengis.net/spec/owc/1.0/req/wms", operations=operations)
