import datetime
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from MapSkinner.decorator import check_access
from MapSkinner.responses import BackendAjaxResponse, DefaultContext
from MapSkinner.settings import ROOT_URL
from service.models import Service
from structure.config import PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW
from structure.forms import GroupForm, OrganizationForm, PublisherForOrganization
from structure.models import Group, Role, Permission, Organization, PublishRequest
from .helper import user_helper
from structure.models import User
from MapSkinner import utils


@check_access
def index(request: HttpRequest, user: User):
    """ Renders an overview of all groups and organizations

    Args:
        request (HttpRequest): The incoming request
        user (User): The current user
    Returns:
         A view
    """
    template = "index_structure.html"
    user_groups = user.groups.all()
    all_orgs = Organization.objects.all().order_by('organization_name')
    user_orgs = {
        "primary": user.organization,
    }
    groups = []
    for user_group in user_groups:
        groups.append(user_group)
        groups.extend(Group.objects.filter(
            parent=user_group
        ))
    # check for notifications like publishing requests
    # publish requests
    pub_requests_count = PublishRequest.objects.filter(organization=user.organization).count()

    params = {
        "permissions": user_helper.get_permissions(user=user),
        "groups": groups,
        "all_organizations": all_orgs,
        "user_organizations": user_orgs,
        "pub_requests_count": pub_requests_count,
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@check_access
def groups(request: HttpRequest, user: User):
    """ Renders an overview of all groups

    Args:
        request (HttpRequest): The incoming request
        user (User): The current user
    Returns:
         A view
    """
    template = "index_groups_extends.html"
    user_groups = user.groups.all()
    groups = []
    for user_group in user_groups:
        groups.append(user_group)
        groups.extend(Group.objects.filter(
            parent=user_group
        ))
    params = {
        "permissions": user_helper.get_permissions(user=user),
        "groups": groups,
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@check_access
def organizations(request: HttpRequest, user: User):
    """ Renders an overview of all organizations

    Args:
        request (HttpRequest): The incoming request
        user (User): The current user
    Returns:
         A view
    """
    template = "index_organizations_extended.html"
    all_orgs = Organization.objects.all()
    # check for notifications like publishing requests
    # publish requests
    pub_requests_count = PublishRequest.objects.filter(organization=user.organization).count()
    orgs = {
        "primary": user.organization,
        #"secondary": user.secondary_organization,
    }
    params = {
        "permissions": user_helper.get_permissions(user=user),
        "user_organizations": orgs,
        "all_organizations": all_orgs,
        "pub_requests_count": pub_requests_count,
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())

@check_access
def detail_organizations(request:HttpRequest, id: int, user:User):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        id: The id of the requested group
        user: The user object
    Returns:
         A rendered view
    """
    org = Organization.objects.get(id=id)
    members = User.objects.filter(organization=org)
    sub_orgs = Organization.objects.filter(parent=org)
    services = Service.objects.filter(metadata__contact=org, is_root=True)
    template = "organization_detail.html"
    params = {
        "organization": org,
        "permissions": user_helper.get_permissions(user=user),
        "members": members,
        "sub_organizations": sub_orgs,
        "services": services,
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@check_access
def edit_org(request: HttpRequest, id: int, user: User):
    """ The edit view for changing organization values

    Args:
        request:
        id:
        user:
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    template = "form.html"
    org = Organization.objects.get(id=id)
    form = OrganizationForm(request.POST or None, instance=org)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            org = form.save(commit=False)
            if org.parent == org:
                messages.add_message(request=request, level=messages.ERROR, message=_("A group can not be parent to itself!"))
            else:
                org.save()
        return redirect("structure:detail-organization", org.id)

    else:
        params = {
            "organization": org,
            "form": form,
            "article": _("You are editing the organization") + " " + org.organization_name,
            "action_url": ROOT_URL + "/structure/organizations/edit/" + str(org.id)
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()


@check_access
def new_org(request: HttpRequest, user: User):
    """ Renders the new organization form and saves the input

    Args:
        request: The incoming request
        user: The user object
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    if not user_helper.has_permission(user=user, permission_needed=Permission(can_create_organization=True)):
        messages.add_message(request, messages.ERROR, _("You do not have permissions for this!"))
        return redirect("structure:index")

    orgs = list(Organization.objects.values_list("organization_name", flat=True))
    if None in orgs:
        orgs.pop(orgs.index(None))
    template = "form.html"
    form = OrganizationForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            org = form.save(commit=False)
            if org.parent == org:
                messages.add_message(request=request, level=messages.ERROR, message=_("A group can not be parent to itself!"))
            else:
                org.created_by = user
                org.save()
            return redirect("structure:index")
    else:
        params = {
            "organizations": orgs,
            "form": form,
            "article": _("You are creating a new organization. Please make sure the organization does not exist yet to avoid duplicates! You can see if a similar named organization already exists by typing the organization name in the related field."),
            "action_url": ROOT_URL + "/structure/organizations/new/register-form/"
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()


@check_access
def list_publish_request(request: HttpRequest, id: int, user: User):
    """ Index for all publishers and publish requests

    :param request:
    :param id:
    :param user:
    :return:
    """
    template = "index_publish_requests.html"
    pub_requests = PublishRequest.objects.filter(organization=id)
    all_publishing_groups = Group.objects.filter(publish_for_organizations__id=id)
    organization = Organization.objects.get(id=id)
    params = {
        "pub_requests": pub_requests,
        "all_publisher": all_publishing_groups,
        "organization": organization,
    }
    context = DefaultContext(request, params)
    return render(request, template, context.get_context())


@check_access
def toggle_publish_request(request: HttpRequest, id: int, user: User):
    # activate or remove publish request/ publisher
    post_params = request.POST
    is_accepted = utils.resolve_boolean_attribute_val(post_params.get("accept"))
    organization = Organization.objects.get(id=post_params.get("organizationId"))
    pub_request = PublishRequest.objects.get(id=id)
    now = timezone.now()
    if is_accepted and pub_request.activation_until >= now:
        # add organization to group_publisher manager
        pub_request.group.publish_for_organizations.add(organization)
    pub_request.delete()
    return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure/organizations/list-publish-request/" + str(organization.id)).get_response()


@check_access
def remove_publisher(request: HttpRequest, id: int, user: User):
    post_params = request.POST
    group_id = post_params.get("publishingGroupId")
    org = Organization.objects.get(id=id)
    group = Group.objects.get(id=group_id, publish_for_organizations=org)
    group.publish_for_organizations.remove(org)

    return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure/organizations/list-publish-request/" + str(id)).get_response()

@check_access
def publish_request(request: HttpRequest, id: int, user: User):
    """ Performs creation of a publishing request between a user/group and an organization

    Args:
        request (HttpRequest): The incoming HttpRequest
        id (int): The organization id
        user (User): The performing user object
    Returns:
         A rendered view
    """
    template = "request_publish_permission.html"
    org = Organization.objects.get(id=id)
    # check if user is already a publisher
    for group in user.groups.all():
        if org in group.publish_for_organizations.all():
            messages.add_message(request, messages.INFO, _("You already are a publisher for this organization!"))
            return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure/organizations/detail/" + str(id)).get_response()

    request_form = PublisherForOrganization(request.POST or None)
    request_form.fields["organization_name"].initial = org.organization_name
    groups = user.groups.all().values_list('id', 'name')
    request_form.fields["group"].choices = groups
    params = {}
    if request.method == 'POST':
        if request_form.is_valid():
            msg = request_form.cleaned_data["request_msg"]
            group = Group.objects.get(id=request_form.cleaned_data["group"])
            publish_request_obj = PublishRequest()
            publish_request_obj.organization = org
            publish_request_obj.message = msg
            publish_request_obj.group = group
            publish_request_obj.activation_until = timezone.now() + datetime.timedelta(hours=PUBLISH_REQUEST_ACTIVATION_TIME_WINDOW)
            publish_request_obj.save()
            # create pending publish request for organization!
            messages.add_message(request, messages.SUCCESS, _("Publish request has been sent to the organization!"))
        else:
            messages.add_message(request, messages.ERROR, _("The input was not valid"))
        return redirect("structure:detail-organization", id)

    else:
        params = {
            "form": request_form,
            "organization": org,
            "user": user,
            "button_text": _("Send"),
            "article": _("You need to ask for permission to become a publisher. Please select your group for which you want to have publishing permissions and explain why you need them."),
            "action_url": ROOT_URL + "/structure/organizations/publish-request/" + str(id),
        }

    html = render_to_string(template_name=template, context=params, request=request)
    return BackendAjaxResponse(html=html).get_response()


@check_access
def detail_group(request: HttpRequest, id: int, user: User):
    """ Renders an overview of a group's details.

    Args:
        request: The incoming request
        id: The id of the requested group
        user: The user object
    Returns:
         A rendered view
    """
    group = Group.objects.get(id=id)
    members = group.users.all()
    template = "group_detail.html"
    params = {
        "group": group,
        "permissions": user_helper.get_permissions(user=user),
        "group_permissions": user_helper.get_permissions(group=group),
        "members": members
    }
    context = DefaultContext(request, params)
    return render(request=request, template_name=template, context=context.get_context())


@check_access
def new_group(request: HttpRequest, user: User):
    """ Renders the new group form and saves the input

    Args:
        request: The incoming request
        user: The user object
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    if not user_helper.has_permission(user=user, permission_needed=Permission(can_create_group=True)):
        messages.add_message(request, messages.ERROR, _("You do not have permissions for this!"))
        return redirect("structure:index")

    template = "form.html"
    form = GroupForm(request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            if group.parent == group:
                messages.add_message(request=request, level=messages.ERROR, message=_("A group can not be parent to itself!"))
            else:
                group.created_by = user
                group.role = Role.objects.get(name="_default_")
                group.save()
                user.groups.add(group)
            return redirect("structure:index")
    else:
        params = {
            "form": form,
            "article": _("You are creating a new group."),
            "action_url": ROOT_URL + "/structure/groups/new/register-form/"
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()



@check_access
def remove(request: HttpRequest, user: User):
    """ Renders the remove form for a service

    Args:
        request(HttpRequest): The used request
    Returns:
        A rendered view
    """
    template = "remove_group_confirmation.html"
    service_id = request.GET.dict().get("id")
    confirmed = request.GET.dict().get("confirmed")
    group = get_object_or_404(Group, id=service_id)
    permission = group.role.permission
    if confirmed == 'false':
        params = {
            "group": group,
            "permissions": permission,
        }
        html = render_to_string(template_name=template, context=params, request=request)
        return BackendAjaxResponse(html=html).get_response()
    else:
        # remove group and all of the related content
        group.delete()
        return BackendAjaxResponse(html="", redirect=ROOT_URL + "/structure").get_response()


@check_access
def edit_group(request: HttpRequest, user: User, id: int):
    """ The edit view for changing group values

    Args:
        request:
        id:
        user:
    Returns:
         A BackendAjaxResponse for Ajax calls or a redirect for a successful editing
    """
    template = "form.html"
    group = Group.objects.get(id=id)
    form = GroupForm(request.POST or None, instance=group)
    if request.method == "POST":
        form.fields.get('role').disabled = True
        if form.is_valid():
            # save changes of group
            group = form.save(commit=False)
            if group.parent == group:
                messages.add_message(request=request, level=messages.ERROR, message=_("A group can not be parent to itself!"))
            else:
                group.save()
        return redirect("structure:detail-group", group.id)

    else:
        user_perm = user_helper.get_permissions(user=user)
        if not 'can_change_group_role' in user_perm and form.fields.get('role', None) is not None:
            form.fields.get('role').disabled = True
        params = {
            "group": group,
            "form": form,
            "article": _("You are editing the group") + " " + group.name,
            "action_url": ROOT_URL + "/structure/groups/edit/" + str(group.id)
        }
        html = render_to_string(template_name=template, request=request, context=params)
        return BackendAjaxResponse(html=html).get_response()
