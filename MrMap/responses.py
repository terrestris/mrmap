"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 15.04.19

"""
from collections import OrderedDict

from django.http import JsonResponse, HttpRequest
from django.urls import resolve, Resolver404, get_resolver, ResolverMatch, URLResolver

from MrMap.settings import ROOT_URL, GIT_REPO_URI, GIT_GRAPH_URI
from structure.models import MrMapUser
from MrMap.utils import get_theme
from django.utils.translation import gettext as _


def check_path_exists(path):
    try:
        match = resolve(path=path)
        return match
    except Resolver404:
        return None


class BreadCrumbItem:
    def __init__(self, path: str,
                 resolver_match: ResolverMatch = None,
                 is_representative: bool = True,
                 is_specific: bool = False,
                 is_active_path: bool = False):
        self.path = path
        self.resolver_match = resolver_match
        self.is_representative = is_representative
        self.is_specific = is_specific
        self.is_active_path = is_active_path

        self.verbose_name = None
        if self.resolver_match:
            url_name = self.resolver_match.url_name
            self.verbose_name = _(url_name.split('_')[-1])


class BreadCrumbBuilder:
    breadcrumb = None

    def __init__(self, path: str):
        self.path = path
        self.build_breadcrumb()

    def build_breadcrumb(self):
        path_items = self.path.split("/")
        path_items.pop(0)
        path_tmp = ""

        self.breadcrumb = OrderedDict()
        for path_item in path_items:
            path_tmp += "/" + path_item
            match = check_path_exists(path_tmp)
            if match:
                is_specific = True if 'pk' in match.kwargs and 'pk' in match.route.split("/")[-1] else False
                is_active_path = True if self.path == path_tmp else False
                breadcrumb_item = BreadCrumbItem(is_representative=True,
                                                 resolver_match=match,
                                                 path=path_tmp,
                                                 is_specific=is_specific,
                                                 is_active_path=is_active_path)
                self.breadcrumb[path_item] = breadcrumb_item
            else:
                self.breadcrumb[path_item] = BreadCrumbItem(is_representative=False,
                                                            path=path_tmp)
        return self.breadcrumb


class DefaultContext:
    """ Contains the default values that have to be set on every rendering process!

    """

    def __init__(self, request: HttpRequest, context: dict, user: MrMapUser = None):
        if user is not None and not user.is_anonymous:
            permissions = user.get_permissions()
        else:
            permissions = []

        breadcrumb_builder = BreadCrumbBuilder(path=request.path)

        self.context = {
            "ROOT_URL": ROOT_URL,
            "PATH": request.path.split("/")[1],
            "FULL_PATH": request.path,
            "LANGUAGE_CODE": request.LANGUAGE_CODE,
            "user_permissions": permissions,  # user_helper.get_permissions(user)
            "user": user,
            "GIT_REPO_URI": GIT_REPO_URI,
            "GIT_GRAPH_URI": GIT_GRAPH_URI,
            "THEME": get_theme(user),
            "BREADCRUMB_CONFIG": breadcrumb_builder.breadcrumb,
        }
        self.add_context(context)

    def get_context(self):
        """ Returns the context dict

        Returns:
             The context dict
        """
        return self.context

    def add_context(self, context: dict):
        """ Adds a complete dict to the default configuration

        Args:
            context (dict): The context dict
        Returns:
        """
        for key, val in context.items():
            self.context[key] = val


class APIResponse:
    def __init__(self):
        self.data = {
            "success": False,
            "msg": "",
        }


class BackendAjaxResponse:
    """ Generic JsonResponse wrapper for Backend->Frontend(AJAX) communication

    Use for AJAX responses.
    There are three default values for the response: 'html', 'response' and 'url'.
    'Html' contains prerendered html content, that will be pasted by Javascript into an html element.

    IMPORTANT:
    Always(!) use this object instead of a direct JsonResponse() object.

    """

    def __init__(self, html, **kwargs: dict):
        self.context = {
            "html": html,
            "ROOT_URL": ROOT_URL,
        }
        # add optional parameters
        for arg_key, arg_val in kwargs.items():
            self.context[arg_key] = arg_val

    def get_response(self):
        """ Return the JsonResponse

        Returns:
             The JsonResponse
        """
        return JsonResponse(self.context)
