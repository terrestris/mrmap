from django.http import HttpRequest, HttpResponse, HttpResponseNotFound, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string

from MrMap.responses import DefaultContext
from service.helper.enums import MetadataEnum, OGCServiceEnum
from service.models import Metadata, Service


def index(request: HttpRequest):
    """ Renders the GUI of our Atom-Feed client

    Args:
        request: The incoming request
    Returns:
        A rendered view
    """

    return None


def create_entries_recursive(service: Service):
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
            child_entries = create_entries_recursive(service=child_service)
            if len(child_entries) > 0:
                for child_entry in child_entries:
                    entries.append(child_entry)
    datasets = service.metadata.related_metadata.all().filter(metadata_to__metadata_type=MetadataEnum.DATASET.value,)
    if datasets:
        # the are datasets for this group layer. We can create a dataset entry for this group layer.
        for dataset in datasets:
            entries.append({
                "dataset_for": service.metadata,
                "dataset": dataset.metadata_to,
                "is_group_layer": is_group_layer,
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
        entries = create_entries_recursive(resource_metadata.service)

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
    dataset = get_object_or_404(klass=Metadata,
                                id=metadata_id,
                                metadata_type=MetadataEnum.DATASET.value)

    language = request.GET.get('language', None)

    context = {
        "metadata": dataset,
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



