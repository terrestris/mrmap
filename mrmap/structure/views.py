from celery import states
from celery.worker.control import revoke
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ValidationError
from django.db.models import Case, When, Q
from django.http import HttpResponseRedirect
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _l
from django.utils.translation import gettext as _
from django.views.generic import DeleteView, DetailView, UpdateView, CreateView
from django.views.generic.base import ContextMixin
from django_bootstrap_swt.components import Tag, Badge
from django_bootstrap_swt.enums import BadgeColorEnum
from django_celery_results.models import TaskResult
from django_filters.views import FilterView
from MrMap.icons import IconEnum
from MrMap.messages import GROUP_SUCCESSFULLY_DELETED, GROUP_SUCCESSFULLY_CREATED, PUBLISH_REQUEST_DENIED, \
    PUBLISH_REQUEST_ACCEPTED, \
    ORGANIZATION_SUCCESSFULLY_CREATED, ORGANIZATION_SUCCESSFULLY_DELETED, PUBLISH_REQUEST_SENT, \
    GROUP_SUCCESSFULLY_EDITED, GROUP_INVITATION_CREATED, ORGANIZATION_SUCCESSFULLY_EDITED, NO_PERMISSION
from MrMap.views import InitFormMixin, GenericViewContextMixin, CustomSingleTableMixin, DependingListView, \
    SuccessMessageDeleteMixin
from structure.permissionEnums import PermissionEnum
from structure.forms import GroupForm, OrganizationForm
from structure.models import MrMapGroup, Organization, PublishRequest, GroupInvitationRequest
from structure.models import MrMapUser
from structure.tables import GroupTable, OrganizationTable, PublishesForTable, GroupDetailTable, \
    OrganizationDetailTable, PublishersTable, OrganizationMemberTable, MrMapUserTable, \
    PublishesRequestTable, GroupInvitationRequestTable
from django.urls import reverse_lazy
from structure.tables import GroupMemberTable


class GroupDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.members_view_uri,
                    'title': _('Members ').__str__() + Badge(content=str(self.object.user_set.count()),
                                                            color=BadgeColorEnum.SECONDARY)},
                   {'url': self.object.publish_rights_for_uri,
                    'title': _('Publish rights for ').__str__() +
                             Badge(content=str(self.object.publish_for_organizations.count()),
                                   color=BadgeColorEnum.SECONDARY)},
                   ]

        context.update({"object": self.object,
                        'actions': self.object.get_actions(self.request),
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(group=self.object).count()})
        return context


class OrganizationDetailContextMixin(ContextMixin):
    object = None

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        tab_nav = [{'url': self.object.get_absolute_url,
                    'title': _('Details')},
                   {'url': self.object.members_view_uri,
                    'title': _('Members ').__str__() + Badge(content=str(self.object.primary_users.count()),
                                                             color=BadgeColorEnum.SECONDARY)},
                   {'url': self.object.publishers_uri,
                    'title': _('Publishers ').__str__() +
                             Badge(content=str(self.object.publishers.count()),
                                   color=BadgeColorEnum.SECONDARY)},
                   ]
        context.update({"object": self.object,
                        'actions': self.object.get_actions(),
                        'tab_nav': tab_nav,
                        'publisher_requests_count': PublishRequest.objects.filter(organization=self.object).count()})
        return context


@method_decorator(login_required, name='dispatch')
class GroupTableView(CustomSingleTableMixin, FilterView):
    model = MrMapGroup
    table_class = GroupTable
    filterset_fields = {'name': ['icontains'],
                        'description': ['icontains'],
                        'organization__organization_name': ['icontains']}
    is_public_group = Q(is_public_group=True)
    is_no_permission_group = Q(is_permission_group=False)
    queryset = MrMapGroup.objects.filter(is_no_permission_group | is_public_group)


@method_decorator(login_required, name='dispatch')
class OrganizationTableView(CustomSingleTableMixin, FilterView):
    model = Organization
    table_class = OrganizationTable
    filterset_fields = {'organization_name': ['icontains'],
                        'parent__organization_name': ['icontains'],
                        'is_auto_generated': ['exact']}

    def get_queryset(self):
        queryset = super().get_queryset()
        queryset = queryset.order_by(
            Case(When(id=self.request.user.organization.id if self.request.user.organization is not None else 0, then=0), default=1),
            'organization_name')
        return queryset


@method_decorator(login_required, name='dispatch')
class OrganizationNewView(PermissionRequiredMixin, InitFormMixin, GenericViewContextMixin, SuccessMessageMixin, CreateView):
    model = Organization
    form_class = OrganizationForm
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New organization')
    success_message = ORGANIZATION_SUCCESSFULLY_CREATED
    permission_required = PermissionEnum.CAN_CREATE_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class OrganizationDetailView(GenericViewContextMixin, OrganizationDetailContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = Organization
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = Organization.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = OrganizationDetailTable(data=[self.object, ], request=self.request)
        context.update({'table': details_table})
        return context


@method_decorator(login_required, name='dispatch')
class OrganizationEditView(PermissionRequiredMixin, InitFormMixin, GenericViewContextMixin, SuccessMessageMixin, UpdateView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = ORGANIZATION_SUCCESSFULLY_EDITED
    model = Organization
    form_class = OrganizationForm
    title = _('Edit organization')
    permission_required = PermissionEnum.CAN_EDIT_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class OrganizationDeleteView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageDeleteMixin, DeleteView):
    model = Organization
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:organization_overview')
    success_message = ORGANIZATION_SUCCESSFULLY_DELETED
    queryset = Organization.objects.filter(is_auto_generated=False)
    title = _('Delete organization')
    permission_required = PermissionEnum.CAN_DELETE_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_msg_dict(self):
        return {'organization_name': self.get_object().organization_name}


@method_decorator(login_required, name='dispatch')
class OrganizationMembersTableView(DependingListView, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = MrMapUser
    depending_model = Organization
    table_class = OrganizationMemberTable
    filterset_fields = {'username': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')

    def get_queryset(self):
        return self.object.primary_users.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


@method_decorator(login_required, name='dispatch')
class OrganizationPublishersTableView(DependingListView, OrganizationDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = MrMapGroup
    depending_model = Organization
    table_class = PublishersTable
    filterset_fields = {'name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Publish for list')

    def get_queryset(self):
        return self.object.publishers.all()

    def get_table_kwargs(self):
        return {'organization': self.object}


@method_decorator(login_required, name='dispatch')
class GroupDetailView(GenericViewContextMixin, GroupDetailContextMixin, DetailView):
    class Meta:
        verbose_name = _('Details')

    model = MrMapGroup
    template_name = 'MrMap/detail_views/table_tab.html'
    queryset = MrMapGroup.objects.all()
    title = _('Details')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        details_table = GroupDetailTable(data=[self.object, ],
                                         request=self.request)
        context.update({'table': details_table})
        return context


@method_decorator(login_required, name='dispatch')
class GroupMembersTableView(DependingListView, GroupDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = MrMapUser
    depending_model = MrMapGroup
    table_class = GroupMemberTable
    filterset_fields = {'username': ['icontains'],
                        'organization__organization_name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PENDING_TASKS.value]}) + _(' Members')

    def get_queryset(self):
        return self.object.user_set.all()

    def get_table_kwargs(self):
        return {'group': self.object}


@method_decorator(login_required, name='dispatch')
class PendingTaskDelete(SuccessMessageMixin, DetailView):
    model = TaskResult
    success_url = reverse_lazy('resource:pending-tasks')
    template_name = 'generic_views/base_extended/delete.html'
    success_message = _('Task canceled.')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "action_url": self.object.remove_view_uri,
            "action": _l("Delete"),
            "msg": _l("Are you sure you want to delete " + self.object.__str__()) + "?"
        })
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        revoke(task_id=self.object.task_id, state=states.REVOKED, terminate=True)
        return HttpResponseRedirect(self.success_url)


@method_decorator(login_required, name='dispatch')
class ErrorReportDetailView(DetailView):
    model = TaskResult
    content_type = "text/plain"
    template_name = "structure/views/error-reports/error.txt"

    def dispatch(self, request, *args, **kwargs):
        response = super().dispatch(request, *args, **kwargs)
        response['Content-Disposition'] = f'attachment; filename="MrMap_error_report_{self.object.task_id}.txt"'
        return response


@method_decorator(login_required, name='dispatch')
class GroupNewView(PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = MrMapGroup
    form_class = GroupForm
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('New group')
    success_message = GROUP_SUCCESSFULLY_CREATED
    permission_required = PermissionEnum.CAN_CREATE_GROUP.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class GroupPublishRightsForTableView(DependingListView, GroupDetailContextMixin, CustomSingleTableMixin, FilterView):
    model = Organization
    depending_model = MrMapGroup
    table_class = PublishesForTable
    filterset_fields = {'organization_name': ['icontains']}
    template_name = 'MrMap/detail_views/table_tab.html'
    object = None
    title = Tag(tag='i', attrs={"class": [IconEnum.PUBLISHERS.value]}) + _(' Publish for list')

    def get_queryset(self):
        return self.object.publish_for_organizations.all()


@method_decorator(login_required, name='dispatch')
class PublishRequestNewView(PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = PublishRequest
    fields = ('group', 'organization', 'message')
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('Publish request')
    success_message = PUBLISH_REQUEST_SENT
    permission_required = PermissionEnum.CAN_REQUEST_TO_BECOME_PUBLISHER.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def form_valid(self, form):
        group = form.cleaned_data['group']
        organization = form.cleaned_data['organization']
        if group.publish_for_organizations.filter(id=organization.id).exists():
            form.add_error(None, _(f'{group} can already publish for Organization.'))
            return self.form_invalid(form)
        else:
            return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class PublishRequestTableView(CustomSingleTableMixin, FilterView):
    model = PublishRequest
    table_class = PublishesRequestTable
    filterset_fields = ['group', 'organization', 'message']

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            # show only requests for groups or organization where the user is member of
            # superuser can see all pending requests
            queryset.filter(Q(group__in=self.request.user.groups.all()) |
                            Q(organization=self.request.user.organization))
        return queryset


@method_decorator(login_required, name='dispatch')
class PublishRequestAcceptView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageMixin, InitFormMixin, UpdateView):
    model = PublishRequest
    template_name = "MrMap/detail_views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted', )
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept request')
    permission_required = PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ValidationError as e:
            messages.error(self.request, e.message)
            response = HttpResponseRedirect(self.get_success_url())
        return response


@method_decorator(login_required, name='dispatch')
class PublishRequestRemoveView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageMixin, DeleteView):
    model = PublishRequest
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:index')
    success_message = PUBLISH_REQUEST_DENIED
    title = _('Deny request')
    permission_required = PermissionEnum.CAN_TOGGLE_PUBLISH_REQUESTS.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION


@method_decorator(login_required, name='dispatch')
class GroupDeleteView(PermissionRequiredMixin, GenericViewContextMixin, SuccessMessageDeleteMixin, DeleteView):
    model = MrMapGroup
    template_name = "MrMap/detail_views/delete.html"
    success_url = reverse_lazy('structure:group_overview')
    success_message = GROUP_SUCCESSFULLY_DELETED
    queryset = MrMapGroup.objects.filter(is_permission_group=False, is_public_group=False)
    title = _('Delete group')
    permission_required = PermissionEnum.CAN_DELETE_GROUP.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_msg_dict(self):
        return {'name': self.get_object().name}


@method_decorator(login_required, name='dispatch')
class GroupEditView(PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, UpdateView):
    template_name = 'MrMap/detail_views/generic_form.html'
    success_message = GROUP_SUCCESSFULLY_EDITED
    model = MrMapGroup
    form_class = GroupForm
    queryset = MrMapGroup.objects.filter(is_permission_group=False)
    title = _('Edit group')
    permission_required = PermissionEnum.CAN_EDIT_GROUP.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"request": self.request})
        return kwargs


@method_decorator(login_required, name='dispatch')
class UserTableView(CustomSingleTableMixin, FilterView):
    model = MrMapUser
    table_class = MrMapUserTable
    filterset_fields = {'username': ['icontains'],
                        'organization__organization_name': ['icontains'],
                        'groups__name': ['icontains']}


@method_decorator(login_required, name='dispatch')
class GroupInvitationRequestTableView(CustomSingleTableMixin, FilterView):
    model = GroupInvitationRequest
    table_class = GroupInvitationRequestTable
    filterset_fields = ['user', 'group', 'message']

    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.user.is_superuser:
            # show only requests for groups where the user is member of or the user is the requesting user
            # superuser can see all pending requests
            queryset.filter(Q(group__in=self.request.user.groups.all()) |
                            Q(user=self.request.user))
        return queryset


@method_decorator(login_required, name='dispatch')
class GroupInvitationRequestNewView(PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, CreateView):
    model = GroupInvitationRequest
    fields = ('user', 'group', 'message')
    template_name = 'MrMap/detail_views/generic_form.html'
    title = _('Group invitation request ')
    success_message = GROUP_INVITATION_CREATED
    permission_required = PermissionEnum.CAN_ADD_USER_TO_GROUP.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION

    def form_valid(self, form):
        group = form.cleaned_data['group']
        user = form.cleaned_data['user']

        if group in user.groups.all():
            form.add_error(None, _(f'{user} is already member of this group.'))
            return self.form_invalid(form)
        else:
            return super().form_valid(form)


@method_decorator(login_required, name='dispatch')
class GroupInvitationRequestAcceptView(PermissionRequiredMixin, GenericViewContextMixin, InitFormMixin, SuccessMessageMixin, UpdateView):
    model = GroupInvitationRequest
    template_name = "MrMap/detail_views/generic_form.html"
    success_url = reverse_lazy('structure:publish_request_overview')
    fields = ('is_accepted',)
    success_message = PUBLISH_REQUEST_ACCEPTED
    title = _('Accept invitation request')
    permission_required = PermissionEnum.CAN_EDIT_ORGANIZATION.value
    raise_exception = True
    permission_denied_message = NO_PERMISSION
