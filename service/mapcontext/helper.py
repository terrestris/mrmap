"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
from owslib.owscontext.core import OwcContext, OwcResource, OwcOffering, OwcOperation

from .models import MapContext, MapResource, WmsOffering
from .models import MapResourceFolder


def get_resource_folder(context, folder_path):
    path_segments = []
    if folder_path:
        path_segments = filter(None, folder_path.split("/"))
    roots = MapResourceFolder.objects.filter(context=context).get_cached_trees()
    node = None
    if roots:
        # we expect a single tree from the above query
        node = roots[0]
        for path_segment in path_segments:
            node = get_subfolder_with_name(node, path_segment)
            if not node:
                return None
    return node


def get_subfolder_with_name(folder, name):
    for child in folder.get_children():
        if child.name == name:
            return child
    return None


def check_folder_exists(target_folder, position, name):
    parent_folder = target_folder
    if position in ('left', 'right'):
        parent_folder = target_folder.parent
    return get_subfolder_with_name(parent_folder, name)


def map_context(context: MapContext):
    roots = MapResourceFolder.objects.filter(context__id=context.id) \
        .prefetch_related('mapresource_set',
                          'mapresource_set__wmsoffering_set',
                          'mapresource_set__wmsoffering_set__layer',
                          'mapresource_set__wmsoffering_set__layer__parent_service') \
        .get_cached_trees()
    resources = []
    if roots:
        # we expect a single tree from the above query
        for child in roots[0].get_children():
            collect_resources(child, "", resources)
    return OwcContext(id=context.id.hex, update_date=context.last_modified, title=context.title, resources=resources)


def collect_resources(folder, folder_path, resources):
    if folder.is_leaf_node():
        for resource in folder.mapresource_set.all():
            resources.append(map_resource(resource, folder_path, folder.name))
    else:
        for child in folder.get_children():
            collect_resources(child, folder_path + "/" + folder.name, resources)


def map_resource(resource: MapResource, folder_path, title):
    offerings = []
    for offering in resource.wmsoffering_set.all():
        offerings.append(map_wms_offering(offering))
    return OwcResource(id=f"{resource.pk}",
                       title=title,
                       folder=folder_path,
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
