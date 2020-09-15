from math import ceil

from django.contrib.gis.geos import GEOSGeometry
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from MrMap.responses import DefaultContext
from service.helper.enums import MetadataEnum, OGCServiceEnum, SpatialResolutionTypesEnum
from service.models import Metadata, Service


def index(request: HttpRequest):
    """ Renders the GUI of our Atom-Feed client

    Args:
        request: The incoming request
    Returns:
        A rendered view
    """

    return None


def create_service_entries_recursive(service: Service):
    """ Checks all child layers recursive for datasets
    Args:
        service: The service we will check for datasets for all child layers
    Returns:
        A list of entries
    """

    entries = []
    child_services = Service.objects.filter(parent_service=service)
    is_group_layer = False
    if child_services:
        # there are some sublayers... this is a group layer
        is_group_layer = True
        for child_service in child_services:
            child_entries = create_service_entries_recursive(service=child_service)
            if len(child_entries) > 0:
                for child_entry in child_entries:
                    entries.append(child_entry)
    datasets = service.metadata.related_metadata.all().filter(metadata_to__metadata_type=MetadataEnum.DATASET.value,)
    if datasets:
        # the are datasets for this group layer. We can create a dataset entry for this group layer.
        for dataset in datasets:
            crs_list = []
            for geom in service.metadata.reference_system.all():
                # workaround to get the crs name... # ToDo: maybe we could parse the name from the xml's and save them in our ReferenceSystem model
                point = GEOSGeometry(
                    f'SRID={dataset.metadata_to.bounding_geometry.srid};POINT({dataset.metadata_to.bounding_geometry.convex_hull.coords[0][0][0]} {dataset.metadata_to.bounding_geometry.convex_hull.coords[0][0][1]})').transform(
                    ct=geom.code, clone=True)
                crs_list.append({"version": "9.6.1", "code": geom.code, "name": point.crs.name})

            entries.append({
                "dataset_for": service.metadata,
                "dataset": dataset.metadata_to,
                "is_group_layer": is_group_layer,
                "crs_list": crs_list,
            })

    return entries


def get_service_feed(request: HttpRequest, metadata_id):
    """ This function generates the 'Service Feed'.
        It contains the description of the download service it self.
        All information's about the downloadable resource/s are served and it
        contains the links and descriptions to the 'Dataset Feed' entry's,
        which are created by the get_spatial_dataset function.
        INSPIRE function: Get download service metadata

        For now this will only work as pre-defined atom feed for dataset metadata's

    Args:
        request: The incoming request
        metadata_id: The metadata id
    Returns:
        A http response from type application/atom+xml
    """
    resource_metadata = get_object_or_404(klass=Metadata,
                                          id=metadata_id, )
    entries = []

    if resource_metadata.service.is_wms:
        #  this is a wms.. we need to collect all child_services
        entries = create_service_entries_recursive(resource_metadata.service)

    # Todo: implement language parameter and logic to switch language
    language = request.GET.get('language', None)

    context = {
        "resource_metadata": resource_metadata,
        "entries": entries,
        "is_service_feed": True,
    }
    default_context = DefaultContext(request=request,
                                     context=context)
    content = render_to_string(template_name="atom_feed.xml",
                               context=default_context.get_context(), )

    return HttpResponse(content=content,
                        content_type="application/atom+xml")


def create_dataset_entries(resource_metadata: Metadata, dataset: Metadata):
    """ Checks all child layers recursive for datasets
        Args:
            resource_metadata: metadata for that the dataset feed is requested
            dataset: the metadata of the dataset
        Returns:
            A list of entries
    """
    entries = []
    if not dataset.spatial_res_value:
        # Todo: we can't create downloadlinks without any informations about the resolution of the dataset
        pass

    # check up if the requested resource is a group layer
    child_services = Service.objects.filter(parent_service=resource_metadata.service)
    is_group_layer = False
    if child_services:
        # there are some sublayers... this is a group layer
        is_group_layer = True

    # Todo: if there are no image/tiff format, we don't can do it
    image_tiff_format = resource_metadata.get_formats({"mime_type__icontains": "tiff"}).first()

    image_resolution = 300  # dpi ToDo: move this parameter to settings.py
    max_width = 1024  # pixel ToDo: move this parameter to settings.py
    max_height = 1024  # pixel ToDo: move this parameter to settings.py

    if dataset.spatial_res_type == SpatialResolutionTypesEnum.SCALE_DENOMINATOR.value:
        # the groud_resolution is given in scale denominator. We must convert it to real groud resolution
        ground_resolution = float(dataset.spatial_res_value) / (0.0254 * image_resolution)  # 0.0254 converting factor from inch to meter
    else:
        ground_resolution = float(dataset.spatial_res_value)

    convex_hull = dataset.bounding_geometry.convex_hull

    from django.contrib.gis.geos import GEOSGeometry
    min_x_y = GEOSGeometry(f'SRID={convex_hull.srid};POINT({convex_hull.coords[0][0][0]} {convex_hull.coords[0][0][1]})').transform(ct=3857, clone=True)
    max_y = GEOSGeometry(f'SRID={convex_hull.srid};POINT({convex_hull.coords[0][1][0]} {convex_hull.coords[0][1][1]})').transform(ct=3857, clone=True)
    max_x = GEOSGeometry(f'SRID={convex_hull.srid};POINT({convex_hull.coords[0][3][0]} {convex_hull.coords[0][3][1]})').transform(ct=3857, clone=True)
    diff_x = min_x_y.distance(max_x)  # result is in meter
    diff_y = min_x_y.distance(max_y)  # result is in meter

    columns = ceil(diff_x / ground_resolution / max_width)
    rows = ceil(diff_y / ground_resolution / max_height)

    if columns > 1 or rows > 1:
        # we can't get the dataset with one request by the given constraints.
        pass
    else:
        # nothing to to else. We can get the dataset by one request.
        for crs in resource_metadata.reference_system.all():
            # ToDo: dynamic bbox, width and height settings

            extent_x = GEOSGeometry(f'SRID={convex_hull.srid};POINT({convex_hull.extent[0]} {convex_hull.extent[1]})').transform(ct=crs.code, clone=True)
            extent_y = GEOSGeometry(f'SRID={convex_hull.srid};POINT({convex_hull.extent[2]} {convex_hull.extent[3]})').transform(ct=crs.code, clone=True)

            get_url = f"{resource_metadata.online_resource}REQUEST=GetMap&" \
                      f"SERVICE={resource_metadata.service.service_type.name}&" \
                      f"VERSION={resource_metadata.service.service_type.version}&" \
                      f"LAYERS={resource_metadata.identifier}&" \
                      f"SRS={crs.prefix}{crs.code}&" \
                      f"TRANSPARENT=TRUE&" \
                      f"FORMAT={image_tiff_format}&" \
                      f"BBOX={extent_x.extent[0]},{extent_x.extent[1]},{extent_y.extent[2]},{extent_y.extent[3]}&" \
                      f"WIDTH={max_width}&" \
                      f"HEIGHT={max_height}"

            link = {"href": get_url,
                    "type": image_tiff_format,
                    }

            if dataset.bounding_geometry.srid != 4326:
                # the polygon for georss needs to be in wgs 84 lat-lon
                polygon_wgs_84 = GEOSGeometry(dataset.bounding_geometry).transform(ct=4326, clone=True)
            else:
                polygon_wgs_84 = dataset.bounding_geometry

            entries.append({"dataset_for": resource_metadata,
                            "dataset": dataset,
                            "is_group_layer": is_group_layer,
                            "download_links": [link, ],
                            "crs_list": [{"version": crs.version, "code": crs.code, "name": extent_x.crs.name, "prefix": crs.prefix}, ],
                            "format": image_tiff_format,
                            "polygon": "".join([f"{tup[1]} {tup[0]} " for tup in polygon_wgs_84.convex_hull.coords[0]]),
                            })

    return entries


def get_dataset_feed(request: HttpRequest, metadata_id):
    """ This function generates the 'Dataset Feed'.
        It contains the description of the downloadable data with all download links.
        This atom feed is linked in the 'Service Feed' which
        is created by the get_download_service_metadata function.
        This feed contains also entry elements, which describes the variants
        of the downloadable geodatasets.
        INSPIRE function: Describe spatial dataset

    Args:
        request: The incoming request
        metadata_id: The metadata id
    Returns:
        A http response from type application/atom+xml
    """
    resource_metadata = get_object_or_404(klass=Metadata,
                                          id=metadata_id,)

    dataset = get_object_or_404(klass=Metadata,
                                spatial_dataset_identifier_code=request.GET.get('spatial_dataset_identifier_code', None),
                                spatial_dataset_identifier_namespace=request.GET.get('spatial_dataset_identifier_namespace', None),
                                metadata_type=MetadataEnum.DATASET.value,)

    # Todo: implement language parameter and logic to switch language
    language = request.GET.get('language', None)

    entries = create_dataset_entries(resource_metadata=resource_metadata, dataset=dataset)

    context = {
        "resource_metadata": resource_metadata,
        "entries": entries,
        "is_service_feed": False,
    }
    default_context = DefaultContext(request=request,
                                     context=context)
    content = render_to_string(template_name="atom_feed.xml",
                               context=default_context.get_context(), )
    return HttpResponse(content=content,
                        content_type="application/atom+xml")


def get_service_feed_metadata(request: HttpRequest, metadata_id):
    """ This function generates the iso 19139 metadata to describe the atom service feed

    Args:
        request: The incoming request
        metadata_id: The metadata id
    Returns:
        A http response from type application/xml
    """
    metadata = get_object_or_404(klass=Metadata,
                                 id=metadata_id)

    return None


def get_dataset_feed_metadata(request: HttpRequest, metadata_id):
    """ This function generates the iso 19139 metadata to describe the atom dataset feed
    Args:
        request: The incoming request
        metadata_id: The metadata id
    Returns:
        A http response from type application/xml
    """
    metadata = get_object_or_404(klass=Metadata,
                                 id=metadata_id)

    return None


def open_search(request: HttpRequest):
    """ This function generates opensearch description xml file
    Args:
        request: The incoming request
        metadata_id: The metadata id
    Returns:
        A http response from type application/opensearchdescription+xml
    """
    # mandatory queryparams for this search engine
    spatial_dataset_identifier_code = request.GET.get('spatial_dataset_identifier_code', None)
    spatial_dataset_identifier_namespace = request.GET.get('spatial_dataset_identifier_namespace', None)
    language = request.GET.get('language', 'en')  # only ISO 639-1 language codes are supported. * is any flag
    q = request.GET.get('q', None)  # this are the search terms
    accept_format = request.META.get('HTTP_ACCEPT', None)

    if accept_format == 'application/atom+xml':
        # return the Dataset-Feed by the given spatial dataset identifier
        return get_dataset_feed(request, spatial_dataset_identifier_code)
    elif accept_format == 'application/opensearchdescription+xml':
        # return the opensearch description xml
        metadata = get_object_or_404(klass=Metadata,
                                     id=spatial_dataset_identifier_code,)

        if metadata.metadata_type == MetadataEnum.DATASET.value:
            datasets = [metadata, ]
        else:
            datasets = Metadata.objects.filter(
                related_metadata__metadata_to=metadata,
                metadata_type=MetadataEnum.DATASET.value,
            ).prefetch_related(
                "related_metadata"
            )

        context = {
            "metadata": metadata,
            "dataset_result_count": len(datasets)
        }

        default_context = DefaultContext(request=request,
                                         context=context)
        content = render_to_string(template_name="open_search_description.xml",
                                   context=default_context.get_context(), )
        return HttpResponse(content=content,
                            content_type="application/opensearchdescription+xml")
    else:
        content = ''
        if not accept_format or accept_format == '*/*':
            content += 'No HTTP_ACCEPT Header was provided'

        return HttpResponseBadRequest(content=content,)


def get_dataset(request: HttpRequest, metadata_id):
    """ This function serves the resource as downloadable file
        Inspire function: Get Spatial Dataset

    Query Parameters:
        spatial_dataset_identifier_code: Datasetidentifier
        spatial_dataset_identifier_namespace: Namespace of the datasetidentifier
        crs: coordinate reference system of the geodataset
        language: language of the geodataset

    Args:
        request: The incoming request
        metadata_id: The metadata id
    Returns:
        A http response from type application/opensearchdescription+xml
    """
    # mandatory parameters
    metadata = get_object_or_404(klass=Metadata,
                                 id=metadata_id)
    language = request.GET.get('language', None)
    crs = request.GET.get('crs', None)


    return None



