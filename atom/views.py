import urllib
from math import ceil, sqrt

from django.contrib.gis.gdal import OGRGeometry
from django.contrib.gis.geos import GEOSGeometry, Polygon, MultiPolygon
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from MrMap.responses import DefaultContext
from MrMap.sub_settings.dev_settings import GENERIC_NAMESPACE_TEMPLATE
from atom.settings import DEFAULT_IMAGE_RESOLUTION, DEFAULT_MAX_WIDTH, DEFAULT_MAX_HEIGHT, \
    CONVERSION_FACTOR_INCH_TO_METER, METER_BASED_CRS, WGS_84_CRS, MAXIMUM_FEATURE_COUNT
from service.helper import xml_helper
from service.helper.common_connector import CommonConnector
from service.helper.enums import MetadataEnum, SpatialResolutionTypesEnum, OGCServiceVersionEnum, OGCOperationEnum, \
    OGCServiceEnum
from service.helper.ogc.wfs import OGCWebFeatureServiceFactory
from service.models import Metadata, Service


def index(request: HttpRequest):
    """ Renders the GUI of our Atom-Feed client

    Args:
        request: The incoming request
    Returns:
        A rendered view
    """

    return None


def _get_crs_systems(service: Service, dataset: Metadata):
    """ Builds up a dict with informations about the crs.version, crs.code, crs.name and returns it.

    Args:
        service: The service for that we iterate all available crs's
        dataset: the dataset for from that we get the crs
    Returns:
        dict: list of crs
    """
    crs_list = []
    for geom in service.metadata.reference_system.all():
        # workaround to get the crs name... # ToDo: maybe we could parse the name from the xml's and save them in our ReferenceSystem model
        point = GEOSGeometry(
            f'SRID={dataset.bounding_geometry.srid};POINT({dataset.bounding_geometry.convex_hull.coords[0][0][0]} {dataset.bounding_geometry.convex_hull.coords[0][0][1]})').transform(
            ct=geom.code, clone=True)
        crs_list.append({"version": "9.6.1", "code": geom.code, "name": point.crs.name})
    return crs_list


def create_service_entries_for_wms(service: Service):
    """ Checks all child layers recursive for datasets and build up a list of entries for service feed.
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
            child_entries = create_service_entries_for_wms(service=child_service)
            if len(child_entries) > 0:
                for child_entry in child_entries:
                    entries.append(child_entry)
    datasets = service.metadata.related_metadata.all().filter(metadata_to__metadata_type=MetadataEnum.DATASET.value, )
    if datasets:
        # there are datasets for this group layer. We can create a dataset entry for this group layer.
        for dataset in datasets:
            crs_list = _get_crs_systems(service=service, dataset=dataset.metadata_to)

            entries.append({
                "dataset_for": service.metadata,
                "dataset": dataset.metadata_to,
                "is_group_layer": is_group_layer,
                "crs_list": crs_list,
            })

    return entries


def create_service_entries_for_wfs(service: Service):
    """ Builds the entry list for service feed with all featuretypes of the root service.
    Args:
        service: The service from that we get all featuretypes
    Returns:
        A list of entries
    """
    entries = []

    featuretypes = service.subelements
    for featuretype in featuretypes:
        datasets_of_featuretype = featuretype.metadata.related_metadata.all().filter(
            metadata_to__metadata_type=MetadataEnum.DATASET.value, )
        for dataset in datasets_of_featuretype:
            crs_list = _get_crs_systems(service=service, dataset=dataset.metadata_to)

            entries.append({
                "dataset_for": featuretype.metadata,
                "dataset": dataset.metadata_to,
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
        entries = create_service_entries_for_wms(resource_metadata.service)
    if resource_metadata.service.is_wfs:
        entries = create_service_entries_for_wfs(resource_metadata.service)

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


class ConvexHullMetricInfo:
    """
    This class hold's the transformed metric system based info's of the given geometry
    """
    def __init__(self, geometry: GEOSGeometry):
        # transforms the convex_hull coords to epsg:3857 to measure the distances in meter
        # X/Y Coordinate system:
        # |max_y-------------
        # |------------------
        # |------------------
        # |min_x_y------max_x
        self.point_min_x_y = GEOSGeometry(
            f'SRID={geometry.srid};POINT({geometry.convex_hull.coords[0][0][0]} {geometry.convex_hull.coords[0][0][1]})').transform(
            ct=METER_BASED_CRS, clone=True)
        self.point_max_y = GEOSGeometry(
            f'SRID={geometry.srid};POINT({geometry.convex_hull.coords[0][1][0]} {geometry.convex_hull.coords[0][1][1]})').transform(
            ct=METER_BASED_CRS, clone=True)
        self.point_max_x = GEOSGeometry(
            f'SRID={geometry.srid};POINT({geometry.convex_hull.coords[0][3][0]} {geometry.convex_hull.coords[0][3][1]})').transform(
            ct=METER_BASED_CRS, clone=True)
        self.distance_x = self.point_min_x_y.distance(self.point_max_x)  # result is in meter to calculate columns
        self.distance_y = self.point_min_x_y.distance(self.point_max_y)  # result is in meter to calculate rows


def _calculate_tiles_for_wms(dataset: Metadata):
    x_y_infos = ConvexHullMetricInfo(geometry=dataset.bounding_box)

    # transform the dataset polygon also to epsg:3857 to check if the calculated tiles intersects the dataset_polyon
    dataset_polygon = dataset.bounding_geometry.transform(ct=METER_BASED_CRS, clone=True)

    if dataset.spatial_res_type == SpatialResolutionTypesEnum.SCALE_DENOMINATOR.value:
        # the groud_resolution is given in scale denominator. We must convert it to 'real' groud resolution
        # pixel / meter (meter in reality)
        ground_resolution = (DEFAULT_IMAGE_RESOLUTION / CONVERSION_FACTOR_INCH_TO_METER) / float(
            dataset.spatial_res_value)  # 0.0254 converting factor from inch to meter
    else:
        ground_resolution = float(dataset.spatial_res_value)

    # ToDo: get the maxPixel from the capabilities document
    # get meter step for tile calculation based on the default width and height
    meter_step_x = DEFAULT_MAX_WIDTH / ground_resolution  # pixel / pixel per meter = meter
    meter_step_y = DEFAULT_MAX_HEIGHT / ground_resolution  # pixel / pixel per meter = meter

    # calculate how much tiles we need to get the complete dataset by the constraints of maximum image width and height and the ground resolution
    columns = ceil(x_y_infos.distance_x * ground_resolution / DEFAULT_MAX_WIDTH)
    rows = ceil(x_y_infos.distance_y * ground_resolution / DEFAULT_MAX_HEIGHT)

    tiles = []
    for row_counter in range(rows):
        for col_counter in range(columns):
            point_1_x = x_y_infos.point_min_x_y.convex_hull.coords[0] + col_counter * meter_step_x
            point_1_y = x_y_infos.point_min_x_y.convex_hull.coords[1] + row_counter * meter_step_y
            point_2_x = x_y_infos.point_min_x_y.convex_hull.coords[0] + (col_counter + 1) * meter_step_x
            point_2_y = x_y_infos.point_min_x_y.convex_hull.coords[1] + (row_counter + 1) * meter_step_y

            tile_polygon = Polygon.from_bbox(bbox=(point_1_x, point_1_y, point_2_x, point_2_y))

            if tile_polygon.intersects(dataset_polygon):
                # if we got an intersection, we have content in this tile.
                # If not we would have an empty tile which we don't need
                tiles.append(
                    f"{point_1_x} {point_1_y}, {point_1_x} {point_2_y}, {point_2_x} {point_2_y}, {point_2_x} {point_1_y}, {point_1_x} {point_1_y}")
    return tiles


def _calculate_tiles_for_wfs(featuretype_metadata: Metadata, dataset: Metadata):
    # Todo: move this code to the OGCWebFeatureServiceFactory to have simple get hits function, maybe we need this again
    """
       wfs_service = OGCWebFeatureServiceFactory.get_ogc_wfs(version=featuretype_metadata.get_service_version(),
                                                          service_connect_url=service.metadata.get_current_operations_url(),
                                                          external_auth=featuretype_metadata.get_external_authentication_object())

    """
    service = featuretype_metadata.featuretype.parent_service
    service_version = featuretype_metadata.get_service_version().value
    if service_version != OGCServiceVersionEnum.V_1_0_0.value:
        # this wfs supports counting features in a spatial extent. wfs v.1.0.0 doesn't support this.
        if service_version == OGCServiceVersionEnum.V_2_0_2.value or \
           service_version == OGCServiceVersionEnum.V_2_0_0.value:
            types_param = "typeNames"
        else:
            types_param = "typeName"

        request_url = f"{service.metadata.get_current_operations_url()}SERVICE=WFS&REQUEST=GetFeature&VERSION={service_version}&" \
                      f"{types_param}={featuretype_metadata.identifier}&resultType=hits"

        c = CommonConnector(url=request_url, external_auth=featuretype_metadata.get_external_authentication_object())
        c.load()

        xml_response = xml_helper.parse_xml(xml=c.content)

        hits = xml_helper.try_get_attribute_from_xml_element(
            xml_elem=xml_response,
            elem="//" + GENERIC_NAMESPACE_TEMPLATE.format("FeatureCollection"),
            attribute="numberOfFeatures" if service_version == OGCServiceVersionEnum.V_1_1_0.value else "numberMatched",
        )

        try:
            hits = int(hits)
        except:
            hits = 0

        # ToDo: get the maxFeatures from the capabilities document
        # we assume, that the features of the requested featuretype are evenly distributed on the ground.
        # So that's why we call it 'features per tile'
        features_per_tile = ceil(hits / MAXIMUM_FEATURE_COUNT if hits > 0 else MAXIMUM_FEATURE_COUNT / MAXIMUM_FEATURE_COUNT)

        x_y_infos = ConvexHullMetricInfo(geometry=dataset.bounding_box)

        # transform the dataset polygon also to epsg:3857 to check if the calculated tiles intersects the dataset_polyon
        dataset_polygon = dataset.bounding_geometry.transform(ct=METER_BASED_CRS, clone=True)

        tile_square_size = sqrt((x_y_infos.distance_x * x_y_infos.distance_y) / features_per_tile)
        rows = ceil(x_y_infos.distance_y / tile_square_size)
        columns = ceil(x_y_infos.distance_x / tile_square_size)

        tiles = []
        for row_counter in range(rows):
            for col_counter in range(columns):
                point_1_x = x_y_infos.point_min_x_y.convex_hull.coords[0] + col_counter * tile_square_size
                point_1_y = x_y_infos.point_min_x_y.convex_hull.coords[1] + row_counter * tile_square_size
                point_2_x = x_y_infos.point_min_x_y.convex_hull.coords[0] + (col_counter + 1) * tile_square_size
                point_2_y = x_y_infos.point_min_x_y.convex_hull.coords[1] + (row_counter + 1) * tile_square_size

                tile_polygon = Polygon.from_bbox(bbox=(point_1_x, point_1_y, point_2_x, point_2_y))

                if tile_polygon.intersects(dataset_polygon):
                    # if we got an intersection, we have content in this tile.
                    # If not we would have an empty tile which we don't need
                    tiles.append(f"{point_1_x} {point_1_y}, {point_1_x} {point_2_y}, {point_2_x} {point_2_y}, {point_2_x} {point_1_y}, {point_1_x} {point_1_y}")

        return tiles


def create_dataset_entries(resource_metadata: Metadata, dataset: Metadata):
    """ Checks all child layers recursive for datasets
        Args:
            resource_metadata: metadata for that the dataset feed is requested
            dataset: the metadata of the dataset
        Returns:
            A list of entries
    """
    entries = []
    is_group_layer = None
    if resource_metadata.get_service_type() == OGCServiceEnum.WMS.value:
        image_tiff_format = resource_metadata.get_formats({"mime_type__icontains": "tiff"})

        if not dataset.spatial_res_value or not image_tiff_format:
            # we can't create downloadlinks without any informations about the resolution of the dataset
            # if there are no image/tiff format, we also can't do it, cause only tiff has geo reference metadatas with it
            return entries
        # set mime type to tiff
        request_format = image_tiff_format.first()

        # check up if the requested resource is a group layer
        is_group_layer = False if Service.objects.filter(
            parent_service=resource_metadata.service).count() == 0 else True

        tiles = _calculate_tiles_for_wms(dataset=dataset)

        reference_systems = resource_metadata.reference_system.all()
    elif resource_metadata.get_service_type() == OGCServiceEnum.WFS.value:
        request_format = resource_metadata.get_formats().first()

        tiles = _calculate_tiles_for_wfs(featuretype_metadata=resource_metadata, dataset=dataset)

        if resource_metadata.reference_system.all().count() == 0:
            crs = resource_metadata.featuretype.default_srs
            crs.name = crs.prefix + crs.code
            reference_systems = [resource_metadata.featuretype.default_srs]
        else:
            reference_systems = resource_metadata.reference_system.all()
    else:
        tiles = []
        reference_systems = []

    for crs in reference_systems:
        download_links = []
        for tile in tiles:
            # the tile is based on the meter based crs epsg:3857.
            # Cause on this fact we need to transform it to the posible requestable crs.
            bbox = GEOSGeometry(f'SRID={METER_BASED_CRS};POLYGON(({tile}))').transform(ct=crs.code, clone=True)

            if bbox.srid != WGS_84_CRS:
                # To specify the bbox attribute of the generated downloadlink we need to transform the bbox to WGS 84,
                # cause this is required by georss.
                bbox_wgs_84 = GEOSGeometry(bbox).transform(ct=WGS_84_CRS,
                                                           clone=True) if bbox.crs.srid != WGS_84_CRS else bbox
            else:
                bbox_wgs_84 = bbox

            if resource_metadata.get_service_type() == OGCServiceEnum.WMS.value:
                download_links.append({"href": f"{resource_metadata.get_current_operations_url()}REQUEST=GetMap&"
                                               f"SERVICE={resource_metadata.service.service_type.name}&"
                                               f"VERSION={resource_metadata.service.service_type.version}&"
                                               f"LAYERS={resource_metadata.identifier}&"
                                               f"SRS={crs.prefix}{crs.code}&"
                                               f"TRANSPARENT=TRUE&"
                                               f"FORMAT={request_format}&"
                                               f"BBOX={bbox.extent[0]},{bbox.extent[1]},{bbox.extent[2]},{bbox.extent[3]}&"
                                               f"WIDTH={DEFAULT_MAX_WIDTH}&"
                                               f"HEIGHT={DEFAULT_MAX_HEIGHT}",
                                       "type": request_format,
                                       "bbox": "".join(
                                           [f"{tup[1]} {tup[0]} " for tup in bbox_wgs_84.convex_hull.coords[0]]),
                                       })
            elif resource_metadata.get_service_type() == OGCServiceEnum.WFS.value:
                service_version = resource_metadata.get_service_version().value
                if service_version == OGCServiceVersionEnum.V_2_0_2.value or \
                   service_version == OGCServiceVersionEnum.V_2_0_0.value:
                    types_param = "typeNames"
                    bbox_filter = f'<fes:Filter xmlns:fes="http://www.opengis.net/fes/2.0">'\
                                  f'<fes:Not>' \
                                  f'<fes:Disjoint>'\
                                  f'<fes:ValueReference>{resource_metadata.identifier}</fes:PropertyName>' \
                                  f'{OGRGeometry(bbox.wkt).gml}' \
                                  f'</fes:Disjoint>' \
                                  f'</fes:Not>'\
                                  f'</fes:Filter>'
                else:
                    types_param = "typeName"
                    bbox_filter = f'<ogc:Filter xmlns:ogc="http://www.opengis.net/ogc"><ogc:BBOX>'\
                                  f'<ogc:PropertyName>{resource_metadata.identifier}</ogc:PropertyName>'\
                                  f'<gml:Box xmlns:gml="http://www.opengis.net/gml" srsName="{crs.prefix}{crs.code}">'\
                                  f'<gml:coordinates decimal="." cs="," ts=" ">'\
                                  f'{bbox.extent[0]},{bbox.extent[1]} {bbox.extent[2]},{bbox.extent[3]}'\
                                  f'</gml:coordinates></gml:Box></ogc:BBOX></ogc:Filter>'

                download_links.append({"href": f"{resource_metadata.featuretype.parent_service.metadata.get_current_operations_url()}REQUEST=GetFeature&"
                                               f"SERVICE={resource_metadata.featuretype.parent_service.service_type.name}&"
                                               f"VERSION={resource_metadata.featuretype.parent_service.service_type.version}&"
                                               f"SRSNAME={crs.prefix}{crs.code}&"
                                               f"{types_param}={resource_metadata.identifier}&"
                                               f"BBOX={bbox.extent[0]},{bbox.extent[1]},{bbox.extent[2]},{bbox.extent[3]}&"
                                               f"outputFormat={request_format}",
                                       "type": request_format,
                                       "bbox": "".join(
                                           [f"{tup[1]} {tup[0]} " for tup in bbox_wgs_84.convex_hull.coords[0]]),
                                       })

        if dataset.bounding_box.srid != WGS_84_CRS:
            # the polygon for georss needs to be in wgs 84 lat-lon
            polygon_wgs_84 = GEOSGeometry(dataset.bounding_box).transform(ct=WGS_84_CRS, clone=True)
        else:
            polygon_wgs_84 = dataset.bounding_box

        entries.append({"dataset_for": resource_metadata,
                        "dataset": dataset,
                        "is_group_layer": is_group_layer,
                        "download_links": download_links,
                        "crs_list": [
                            {"version": crs.version, "code": crs.code, "name": crs.name, "prefix": crs.prefix}, ],
                        "format": request_format,
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
                                          id=metadata_id, )

    dataset = get_object_or_404(klass=Metadata,
                                spatial_dataset_identifier_code=request.GET.get('spatial_dataset_identifier_code',
                                                                                None),
                                spatial_dataset_identifier_namespace=request.GET.get(
                                    'spatial_dataset_identifier_namespace', None),
                                metadata_type=MetadataEnum.DATASET.value, )

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
                                     id=spatial_dataset_identifier_code, )

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

        return HttpResponseBadRequest(content=content, )


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
