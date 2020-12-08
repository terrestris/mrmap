"""
Author: Markus Schneider
Organization: terrestris GmbH & Co. KG
Contact: schneider@terrestris.de
Created on: 30.11.20

"""
import json

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, Http404, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.urls import resolve, reverse
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from MrMap.decorator import check_permission
from service.mapcontext.helper import map_context, get_resource_folder, check_folder_exists
from service.mapcontext.models import MapResourceFolder
from service.mapcontext.wizard import NewMapContextWizard, NEW_MAPCONTEXT_WIZARD_FORMS
from structure.permissionEnums import PermissionEnum
from .forms import MapContextWmsLayerForm, MapContextForm
from .models import MapContext


def wmsresource(request, context_id, folder_path):
    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = MapContextWmsLayerForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # ...
            # redirect to a new URL:
            return HttpResponseRedirect('/thanks/')
    # if a GET (or any other method) we'll create a blank form
    else:
        form = MapContextWmsLayerForm(request.GET)
    rendered_wizard = render_to_string(request=request,
                                       template_name='mapcontext/wmsresource.html',
                                       context={'form': form})
    view_function = resolve(reverse("home"))
    return view_function.func(request=request, update_params={'rendered_modal': rendered_wizard})


@login_required
@check_permission(
    PermissionEnum.CAN_REGISTER_RESOURCE
)
def mapcontext(request: HttpRequest):

    mapcontext = None
    if request.method == 'POST':
        form = MapContextForm(request.POST)
        if form.is_valid():
            ## MapContext updaten?
            return HttpResponseRedirect(reverse("home"), status=303)
    else:
        form = MapContextForm(request.GET)
        mapcontext = MapContext.objects.create()
        MapResourceFolder.objects.create(name='root', context=mapcontext)

    folders = MapResourceFolder.objects.filter(context=mapcontext).prefetch_related('mapresource_set')
    rendered_wizard = render_to_string(request=request,
                                       template_name='mapcontext/mapcontext.html',
                                       context={'form': form,
                                                'nodes': folders,
                                                'context_id': mapcontext.id})
    view_function = resolve(reverse("home"))
    return view_function.func(request=request, update_params={'rendered_modal': rendered_wizard})


@login_required
@check_permission(
    PermissionEnum.CAN_REGISTER_RESOURCE
)
def add_mapcontext_old(request: HttpRequest):
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
    # return HttpResponse(atom, content_type="application/atom+xml")
    return HttpResponse(atom, content_type="application/xml")


def get_mapcontext_json(request: HttpRequest, context_id):
    context = MapContext.objects.get(id=context_id)
    owc_context = map_context(context)
    json = owc_context.to_json()
    return HttpResponse(json, content_type="application/geo+json")


def show_mapcontext_folders(request, context_id):
    folders = MapResourceFolder.objects.filter(context__id=context_id).prefetch_related('mapresource_set')
    return render(request, "mapcontext/folders.html", {'nodes': folders})


@method_decorator(csrf_exempt, name='dispatch')
class FoldersView(View):

    def delete(self, request, context_id, folder_path=None):
        folder = self.__get_folder(context_id, folder_path)
        if not folder.is_root_node():
            folder.delete()
        return HttpResponse(status=204)

    def post(self, request, context_id, folder_path=None):
        folder = self.__get_folder(context_id, folder_path)
        context = get_object_or_404(MapContext, id=context_id)
        received_json_data = json.loads(request.body.decode("utf-8"))
        name = received_json_data.get("name")
        position = received_json_data.get("position", "last-child")
        folder = self.__get_folder(context_id, folder_path)
        if check_folder_exists(folder, position, name):
            return HttpResponse('Folder already exists', status=409)
        new_folder = MapResourceFolder(name=name, context=context)
        new_folder.insert_at(folder, position, True)
        return HttpResponse(status=201)

    def put(self, request, context_id, folder_path=None):
        context = get_object_or_404(MapContext, id=context_id)
        folder = self.__get_folder(context_id, folder_path)
        if folder.is_root_node():
            return HttpResponse(status=405)
        received_json_data = json.loads(request.body.decode("utf-8"))
        name = received_json_data.get("name")
        position = received_json_data.get("position", "last-child")
        if name:
            # rename folder
            if check_folder_exists(folder, 'right', name):
                return HttpResponse('Folder already exists', status=409)
            folder.name = name
            folder.save()
        elif received_json_data.get("target"):
            # move folder
            target_folder = get_resource_folder(context, received_json_data.get("target"))
            existing_folder = check_folder_exists(target_folder, position, folder.name)
            print(received_json_data.get("target") + ", " + position)
            if existing_folder and folder.id != existing_folder.id:
                return HttpResponse('Folder already exists', status=409)
            folder.move_to(target_folder, position)
        return HttpResponse(status=204)

    def __get_folder(self, context_id, folder_path):
        context = get_object_or_404(MapContext, id=context_id)
        folder = get_resource_folder(context, folder_path)
        if not folder:
            raise Http404
        return folder
