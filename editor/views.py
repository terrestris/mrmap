import json

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render, redirect

# Create your views here.
from django.template.loader import render_to_string
from django_tables2 import RequestConfig

from MapSkinner import utils
from MapSkinner.consts import DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE
from MapSkinner.decorator import check_session, check_permission
from MapSkinner.messages import FORM_INPUT_INVALID, METADATA_RESTORING_SUCCESS, METADATA_EDITING_SUCCESS, \
    METADATA_IS_ORIGINAL, SERVICE_MD_RESTORED, SERVICE_MD_EDITED, NO_PERMISSION, EDITOR_ACCESS_RESTRICTED, \
    METADATA_PROXY_NOT_POSSIBLE_DUE_TO_SECURED, SECURITY_PROXY_WARNING_ONLY_FOR_ROOT
from MapSkinner.responses import DefaultContext, BackendAjaxResponse
from MapSkinner.settings import ROOT_URL, HTTP_OR_SSL, HOST_NAME, PAGE_DEFAULT, PAGE_SIZE_DEFAULT
from MapSkinner.utils import prepare_table_pagination_settings
from editor.forms import MetadataEditorForm, FeatureTypeEditorForm
from editor.settings import WMS_SECURED_OPERATIONS, WFS_SECURED_OPERATIONS
from service.helper.enums import OGCServiceEnum, MetadataEnum
from service.models import Metadata, Keyword, Category, FeatureType, Layer, RequestOperation, SecuredOperation, Document
from django.utils.translation import gettext_lazy as _
from structure.models import MrMapUser, Permission, MrMapGroup
from users.helper import user_helper
from editor.helper import editor_helper
from editor.tables import *
from editor.filters import *


def _prepare_wms_table(request: HttpRequest, user: MrMapUser, ):
    # get all services that are registered by the user
    wms_services = user.get_services_as_qs(OGCServiceEnum.WMS)
    wms_table_filtered = WmsServiceFilter(request.GET, queryset=wms_services)
    wms_table = WmsServiceTable(wms_table_filtered.qs,
                                template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, user=user,)
    wms_table.filter = wms_table_filtered
    RequestConfig(request).configure(wms_table)
    # TODO: since parameters could be changed directly in the uri, we need to make sure to avoid problems
    # TODO: move pagination as function to ExtendedTable
    wms_table.pagination = prepare_table_pagination_settings(request, wms_table, 'wms-t')
    wms_table.page_field = wms_table.pagination.get('page_name')
    wms_table.paginate(page=request.GET.get(wms_table.pagination.get('page_name'), PAGE_DEFAULT),
                       per_page=request.GET.get(wms_table.pagination.get('page_size_param'), PAGE_SIZE_DEFAULT))

    return wms_table


def _prepare_wfs_table(request: HttpRequest, user: MrMapUser, ):
    wfs_services = user.get_services_as_qs(OGCServiceEnum.WFS)
    wfs_table_filtered = WfsServiceFilter(request.GET, queryset=wfs_services)
    wfs_table = WfsServiceTable(wfs_table_filtered.qs,
                                template_name=DJANGO_TABLES2_BOOTSTRAP4_CUSTOM_TEMPLATE, user=user, )
    wfs_table.filter = wfs_table_filtered
    RequestConfig(request).configure(wfs_table)
    # TODO: # since parameters could be changed directly in the uri, we need to make sure to avoid problems
    # TODO: move pagination as function to ExtendedTable
    wfs_table.pagination = prepare_table_pagination_settings(request, wfs_table, 'wfs-t')
    wfs_table.page_field = wfs_table.pagination.get('page_name')
    wfs_table.paginate(page=request.GET.get(wfs_table.pagination.get('page_name'), PAGE_DEFAULT),
                       per_page=request.GET.get(wfs_table.pagination.get('page_size_param'), PAGE_SIZE_DEFAULT))

    return wfs_table


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def index(request: HttpRequest):
    """ The index view of the editor app.

    Lists all services with information of custom set metadata.

    Args:
        request: The incoming request
    Returns:
    """
    user = user_helper.get_user(request)
    template = "views/editor_service_table_index.html"

    params = {
        "wms_table": _prepare_wms_table(request, user),
        "wfs_table": _prepare_wfs_table(request, user),
    }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def index_wms(request: HttpRequest):
    """ The index view of the editor app.

    Lists all services with information of custom set metadata.

    Args:
        request: The incoming request
    Returns:
    """
    user = user_helper.get_user(request)

    template = "views/editor_service_table_index_wms.html"

    params = {
        "wms_table": _prepare_wms_table(request, user),
    }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def index_wfs(request: HttpRequest):
    """ The index view of the editor app.

    Lists all services with information of custom set metadata.

    Args:
        request: The incoming request
    Returns:
    """
    user = user_helper.get_user(request)

    template = "views/editor_service_table_index_wfs.html"

    params = {
        "wfs_table": _prepare_wfs_table(request, user),
    }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit(request: HttpRequest, id: int):
    """ The edit view for metadata

    Provides editing functions for all elements which are described by Metadata objects

    Args:
        request: The incoming request
        id: The metadata id
    Returns:
        A rendered view
    """
    user = user_helper.get_user(request)

    metadata = Metadata.objects.get(id=id)

    # check if user owns this service by group-relation
    if metadata.created_by not in user.groups.all():
        messages.error(request, message=NO_PERMISSION)
        return redirect("editor:index")

    editor_form = MetadataEditorForm(request.POST or None)

    if request.method == 'POST':

        if editor_form.is_valid():

            custom_md = editor_form.save(commit=False)

            if not metadata.is_root():
                # this is for the case that we are working on a non root element which is not allowed to change the
                # inheritance setting for the whole service -> we act like it didn't change
                custom_md.use_proxy_uri = metadata.use_proxy_uri

                # Furthermore we remove a possibly existing current_capability_document for this element, since the metadata
                # might have changed!
                metadata.clear_cached_documents()

            editor_helper.resolve_iso_metadata_links(request, metadata, editor_form)
            editor_helper.overwrite_metadata(metadata, custom_md, editor_form)
            messages.add_message(request, messages.SUCCESS, METADATA_EDITING_SUCCESS)
            _type = metadata.get_service_type()

            if _type == 'wms':
                if metadata.is_root():
                    parent_service = metadata.service
                else:
                    parent_service = metadata.service.parent_service

            elif _type == 'wfs':
                if metadata.is_root():
                    parent_service = metadata.service
                else:
                    parent_service = metadata.featuretype.parent_service

            user_helper.create_group_activity(metadata.created_by, user, SERVICE_MD_EDITED, "{}: {}".format(parent_service.metadata.title, metadata.title))
            return redirect("service:detail", id)

        else:
            messages.add_message(request, messages.ERROR, FORM_INPUT_INVALID)
            return redirect("editor:edit", id)
    else:

        template = "views/editor_metadata_index.html"
        editor_form = MetadataEditorForm(instance=metadata)
        editor_form.action_url = reverse("editor:edit", args=(id,))

        params = {
            "service_metadata": metadata,
            "form": editor_form,
        }
    context = DefaultContext(request, params, user)
    return render(request, template, context.get_context())


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def edit_access(request: HttpRequest, id: int):
    """ The edit view for the operations access

    Provides a form to set the access permissions for a metadata-related object.
    Processes the form input afterwards

    Args:
        request (HttpRequest): The incoming request
        id (int): The metadata id
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)

    md = Metadata.objects.get(id=id)
    md_type = md.metadata_type.type
    template = "views/editor_edit_access_index.html"
    post_params = request.POST

    if request.method == "POST":
        # process form input
        try:
            editor_helper.process_secure_operations_form(post_params, md)
        except Exception as e:
            messages.error(request, message=e)
            return redirect("editor:edit_access", md.id)
        messages.success(request, EDITOR_ACCESS_RESTRICTED.format(md.title))
        md.save()
        if md_type == MetadataEnum.FEATURETYPE.value:
            redirect_id = md.featuretype.parent_service.metadata.id
        else:
            if md.service.is_root:
                redirect_id = md.id
            else:
                redirect_id = md.service.parent_service.metadata.id
        return redirect("service:detail", redirect_id)

    else:
        # render form
        metadata_type = md.metadata_type.type
        if metadata_type == MetadataEnum.FEATURETYPE.value:
            _type = OGCServiceEnum.WFS.value
        else:
            _type = md.service.servicetype.name
        secured_operations = []
        if _type == OGCServiceEnum.WMS.value:
            secured_operations = WMS_SECURED_OPERATIONS
        elif _type == OGCServiceEnum.WFS.value:
            secured_operations = WFS_SECURED_OPERATIONS

        operations = RequestOperation.objects.filter(
            operation_name__in=secured_operations
        )
        sec_ops = SecuredOperation.objects.filter(
            secured_metadata=md
        )
        all_groups = MrMapGroup.objects.all()
        tmp = editor_helper.prepare_secured_operations_groups(operations, sec_ops, all_groups, md)

        spatial_restrictable_operations = [
            "GetMap",  # WMS
            "GetFeature"  # WFS
        ]

        params = {
            "service_metadata": md,
            "has_ext_auth": md.has_external_authentication(),
            "operations": tmp,
            "spatial_restrictable_operations": spatial_restrictable_operations,
        }

    context = DefaultContext(request, params, user).get_context()
    return render(request, template, context)


#@check_session
def access_geometry_form(request: HttpRequest, id: int):
    """ Renders the geometry form for the access editing

    Args:
        request (HttpRequest): The incoming request
        id (int): The id of the metadata object, which will be edited
    Returns:
         BackendAjaxResponse
    """

    user = user_helper.get_user(request)
    template = "views/access_geometry_form.html"

    GET_params = request.GET
    operation = GET_params.get("operation", None)
    group_id = GET_params.get("groupId", None)
    polygons = utils.resolve_none_string(GET_params.get("polygons", 'None'))

    if polygons is not None:
        polygons = json.loads(polygons)
        if not isinstance(polygons, list):
            polygons = [polygons]

    md = Metadata.objects.get(id=id)

    if not md.is_root():
        messages.info(request, message=SECURITY_PROXY_WARNING_ONLY_FOR_ROOT)
        return BackendAjaxResponse(html="", redirect=reverse('edit_access',  args=(md.id,))).get_response()

    service_bounding_geometry = md.find_max_bounding_box()

    params = {
        "action_url": reverse('editor:access_geometry_form', args=(md.id, )),
        "bbox": service_bounding_geometry,
        "group_id": group_id,
        "operation": operation,
        "polygons": polygons,
    }
    context = DefaultContext(request, params, user).get_context()
    html = render_to_string(template_name=template, request=request, context=context)
    return BackendAjaxResponse(html=html).get_response()


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def restore(request: HttpRequest, id: int):
    """ Drops custom metadata and load original metadata from capabilities and ISO metadata

    Args,
        request: The incoming request
        id: The metadata id
    Returns:
         Redirects back to edit view
    """
    user = user_helper.get_user(request)

    metadata = Metadata.objects.get(id=id)

    ext_auth = metadata.get_external_authentication_object()

    # check if user owns this service by group-relation
    if metadata.created_by not in user.groups.all():
        messages.error(request, message=NO_PERMISSION)
        return redirect("editor:index")

    service_type = metadata.get_service_type()
    if service_type == 'wms':
        children_md = Metadata.objects.filter(service__parent_service__metadata=metadata, is_custom=True)
    elif service_type == 'wfs':
        children_md = Metadata.objects.filter(featuretype__parent_service__metadata=metadata, is_custom=True)

    if not metadata.is_custom and len(children_md) == 0:
        messages.add_message(request, messages.INFO, METADATA_IS_ORIGINAL)
        return redirect(request.META.get("HTTP_REFERER"))

    if metadata.is_custom:
        metadata.restore(metadata.identifier, external_auth=ext_auth)
        metadata.save()

    for md in children_md:
        md.restore(md.identifier)
        md.save()
    messages.add_message(request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
    if not metadata.is_root():
        if service_type == 'wms':
            parent_metadata = metadata.service.parent_service.metadata
        elif service_type == 'wfs':
            parent_metadata = metadata.featuretype.parent_service.metadata
        else:
            # This case is not important now
            pass
    else:
        parent_metadata = metadata
    user_helper.create_group_activity(metadata.created_by, user, SERVICE_MD_RESTORED, "{}: {}".format(parent_metadata.title, metadata.title))
    return redirect("editor:index")


#@check_session
@check_permission(Permission(can_edit_metadata_service=True))
def restore_featuretype(request: HttpRequest, id: int):
    """ Drops custom featuretype data and load original from capabilities and ISO metadata

    Args:
        request: The incoming request
        id: The featuretype id
    Returns:
         A rendered view
    """
    user = user_helper.get_user(request)

    feature_type = FeatureType.objects.get(id=id)

    # check if user owns this service by group-relation
    if feature_type.created_by not in user.groups.all():
        messages.error(request, message=NO_PERMISSION)
        return redirect("editor:index")

    if not feature_type.is_custom:
        messages.add_message(request, messages.INFO, METADATA_IS_ORIGINAL)
        return redirect(request.META.get("HTTP_REFERER"))
    feature_type.restore()
    feature_type.save()
    messages.add_message(request, messages.SUCCESS, METADATA_RESTORING_SUCCESS)
    return redirect("editor:index")
