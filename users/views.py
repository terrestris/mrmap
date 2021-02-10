"""
Author: Michel Peltriaux
Organization: Spatial data infrastructure Rhineland-Palatinate, Germany
Contact: michel.peltriaux@vermkv.rlp.de
Created on: 28.05.19

"""

from collections import OrderedDict
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView, PasswordResetView
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, gettext
from django.views.generic import DetailView, ListView, TemplateView
from django.views.generic.edit import UpdateView, CreateView, DeleteView
from django_bootstrap_swt.components import Tag
from django_tables2 import SingleTableMixin
from MrMap.icons import IconEnum
from MrMap.messages import ACTIVATION_LINK_INVALID, ACTIVATION_LINK_SENT, ACTIVATION_LINK_EXPIRED, \
    SUBSCRIPTION_SUCCESSFULLY_DELETED, SUBSCRIPTION_EDITING_SUCCESSFULL, SUBSCRIPTION_SUCCESSFULLY_CREATED, \
    PASSWORD_CHANGE_SUCCESS
from MrMap.responses import DefaultContext
from MrMap.settings import LAST_ACTIVITY_DATE_RANGE
from service.models import Metadata
from structure.forms import RegistrationForm
from structure.models import MrMapUser, UserActivation, GroupActivity, Organization, \
    PublishRequest, GroupInvitationRequest
from users.forms import SubscriptionForm
from users.helper import user_helper
from users.models import Subscription
from users.settings import users_logger
from users.tables import SubscriptionTable


class MrMapLoginView(SuccessMessageMixin, LoginView):
    template_name = "users/views/logged_out/login.html"
    redirect_authenticated_user = True
    success_message = _('Successfully signed in.')

    def form_invalid(self, form):
        users_logger.info(f'User {form.cleaned_data["username"]} trial to login, but the following error occurs. '
                          f'{form.errors}')
        return super().form_invalid(form=form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            "login_article_title": _("Sign in for Mr. Map"),
            "login_article": _(
                "Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. Lorem ipsum dolor sit amet, consetetur sadipscing elitr, sed diam nonumy eirmod tempor invidunt ut labore et dolore magna aliquyam erat, sed diam voluptua. At vero eos et accusam et justo duo dolores et ea rebum. Stet clita kasd gubergren, no sea takimata sanctus est Lorem ipsum dolor sit amet. "),
        })
        context = DefaultContext(request=self.request, context=context, user=self.request.user).context
        return context


@method_decorator(login_required, name='dispatch')
class HomeView(TemplateView):
    template_name = "users/views/home/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user_groups = self.request.user.get_groups()
        user_services_wms = Metadata.objects.filter(
            service__service_type__name="wms",
            service__is_root=True,
            created_by__in=user_groups,
            service__is_deleted=False,
        ).count()
        user_services_wfs = Metadata.objects.filter(
            service__service_type__name="wfs",
            service__is_root=True,
            created_by__in=user_groups,
            service__is_deleted=False,
        ).count()

        datasets_count = self.request.user.get_datasets_as_qs(count=True)

        activities_since = timezone.now() - timezone.timedelta(days=LAST_ACTIVITY_DATE_RANGE)
        group_activities = GroupActivity.objects.filter(group__in=user_groups,
                                                        created_on__gte=activities_since).order_by("-created_on")

        pending_requests = PublishRequest.objects.filter(organization=self.request.user.organization)
        group_invitation_requests = GroupInvitationRequest.objects.filter(invited_user=self.request.user)
        context.update({
            "wms_count": user_services_wms,
            "wfs_count": user_services_wfs,
            "datasets_count": datasets_count,
            "all_count": user_services_wms + user_services_wfs + datasets_count,
            "publishing_requests": pending_requests,
            "group_invitation_requests": group_invitation_requests,
            "no_requests": not group_invitation_requests.exists() and not pending_requests.exists(),
            "group_activities": group_activities,
            "groups": user_groups,
            "organizations": Organization.objects.filter(is_auto_generated=False),
            "current_view": "home",
        })
        context = DefaultContext(self.request, context, self.request.user).get_context()
        return context


@method_decorator(login_required, name='dispatch')
class ProfileView(DetailView):
    template_name = "users/views/profile/profile.html"
    model = MrMapUser
    slug_field = "username"

    def get_object(self, queryset=None):
        return get_object_or_404(MrMapUser, username=self.request.user.username)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'subscriptions_count': Subscription.objects.filter(user=self.request.user).count()})
        breadcrumb_config = OrderedDict()
        breadcrumb_config['accounts'] = False
        breadcrumb_config['profile'] = True
        context.update({'breadcrumb_config': breadcrumb_config})
        return context


class MrMapPasswordChangeView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'users/views/profile/password_change.html'
    success_message = PASSWORD_CHANGE_SUCCESS

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        return context


class MrMapPasswordResetView(SuccessMessageMixin, PasswordResetView):
    template_name = 'users/views/logged_out/password_reset_or_confirm.html'
    success_message = ACTIVATION_LINK_SENT

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        return context


class EditProfileView(SuccessMessageMixin, UpdateView):
    template_name = 'users/views/profile/password_change.html'
    success_message = _('Profile successfully edited.')
    model = MrMapUser
    fields = [
        "first_name",
        "last_name",
        "email",
        "confirmed_newsletter",
        "confirmed_survey",
        "theme",
    ]

    def get_object(self, queryset=None):
        return get_object_or_404(MrMapUser, username=self.request.user.username)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Edit profile')})
        return context


class ActivateUser(DetailView):
    template_name = "views/user_activation.html"
    model = UserActivation

    @transaction.atomic
    def dispatch(self, request, *args, **kwargs):
        if self.object.activation_until < timezone.now():
            # The activation was confirmed too late!
            messages.add_message(request, messages.ERROR, ACTIVATION_LINK_EXPIRED)
            # Remove the inactive user object
            self.object.user_activation.user.delete()
            return redirect("login")

        self.object.user.is_active = True
        self.object.user.save()
        self.object.delete()
        return super().dispatch(request=request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'user': self.object.user})
        return context


class SignUpView(SuccessMessageMixin, CreateView):
    template_name = 'users/views/logged_out/sign_up.html'
    success_url = reverse_lazy('login')
    model = MrMapUser
    form_class = RegistrationForm
    success_message = "Your profile was created successfully"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Edit profile')})
        return context


@method_decorator(login_required, name='dispatch')
class SubscriptionTableView(SingleTableMixin, ListView):
    model = Subscription
    table_class = SubscriptionTable
    template_name = 'users/views/profile/manage_subscriptions.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user)

    def get_table(self, **kwargs):
        # set some custom attributes for template rendering
        table = super(SubscriptionTableView, self).get_table(**kwargs)
        table.title = Tag(tag='i', attrs={"class": [IconEnum.SUBSCRIPTION.value]}) + gettext(' Subscriptions')
        return table

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Edit profile')})
        return context

    def dispatch(self, request, *args, **kwargs):
        # configure table_pagination dynamically to support per_page switching
        self.table_pagination = {"per_page": self.request.GET.get('per_page', 5), }
        return super(SubscriptionTableView, self).dispatch(request, *args, **kwargs)


@method_decorator(login_required, name='dispatch')
class AddSubscriptionView(SuccessMessageMixin, CreateView):
    model = Subscription
    template_name = "users/views/profile/add_update_subscription.html"
    form_class = SubscriptionForm
    success_message = SUBSCRIPTION_SUCCESSFULLY_CREATED

    def get_initial(self):
        initial = super().get_initial()
        initial.update({'user': self.request.user})
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Add subscription')})
        return context


@method_decorator(login_required, name='dispatch')
class UpdateSubscriptionView(SuccessMessageMixin, UpdateView):
    model = Subscription
    template_name = "users/views/profile/add_update_subscription.html"
    form_class = SubscriptionForm
    success_message = SUBSCRIPTION_EDITING_SUCCESSFULL

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': format_html(_(f'Update subscription for <strong>{self.object.metadata}</strong>'))})
        return context


@method_decorator(login_required, name='dispatch')
class DeleteSubscriptionView(SuccessMessageMixin, DeleteView):
    model = Subscription
    template_name = "users/views/profile/delete_subscription.html"
    success_url = reverse_lazy('manage_subscriptions')
    success_message = SUBSCRIPTION_SUCCESSFULLY_DELETED

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context = DefaultContext(request=self.request, context=context).get_context()
        context.update({'title': _('Delete subscription')})
        return context
