import django_tables2 as tables
from django.utils.html import format_html
from django_bootstrap_swt.components import Link, Tag, Badge, LinkButton
from django_bootstrap_swt.enums import ButtonColorEnum, TooltipPlacementEnum
from django_bootstrap_swt.utils import RenderHelper
from MrMap.icons import IconEnum
from MrMap.tables import ActionTableMixin
from MrMap.utils import get_ok_nok_icon, signal_last
from django.utils.translation import gettext_lazy as _
from structure.models import MrMapGroup, Organization, PublishRequest, MrMapUser


class PublishesForTable(tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-for-table'

    def render_organization_name(self, record, value):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)


class PublishersTable(ActionTableMixin, tables.Table):
    class Meta:
        model = MrMapGroup
        fields = ('name', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-table'

    def __init__(self, organization, *args, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_name(self, record, value):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)

    def render_actions(self, record):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
        st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                           content=remove_icon + _(' Remove').__str__()).render()

        publishers_querystring = "publishers"
        publishers_excluded_record = self.organization.publishers.exclude(pk=record.pk)
        if publishers_excluded_record:
            publishers_querystring = ""
            for is_last_element, publisher in signal_last(publishers_excluded_record):
                if is_last_element:
                    publishers_querystring += f"publishers={publisher.pk}"
                else:
                    publishers_querystring += f"publishers={publisher.pk}&"

        btns = [
            LinkButton(url=f"{self.organization.edit_view_uri}?{publishers_querystring}",
                       content=st_edit_text + gt_edit_text,
                       color=ButtonColorEnum.DANGER,
                       tooltip=_(f"Remove <strong>{record}</strong> from <strong>{self.organization}</strong>"),
                       tooltip_placement=TooltipPlacementEnum.LEFT)
        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))


class PendingRequestTable(ActionTableMixin, tables.Table):
    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_group(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_actions(self, record):
        ok_icon = Tag(tag='i', attrs={"class": [IconEnum.OK.value]}).render()
        st_ok_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=ok_icon).render()
        gt_ok_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                         content=ok_icon + _(' accept').__str__()).render()
        nok_icon = Tag(tag='i', attrs={"class": [IconEnum.NOK.value]}).render()
        st_nok_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=nok_icon).render()
        gt_nok_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                          content=nok_icon + _(' deny').__str__()).render()

        actions = [
            LinkButton(url=f"{record.accept_request_uri}?is_accepted=True",
                       content=st_ok_text+gt_ok_text,
                       color=ButtonColorEnum.SUCCESS),
            LinkButton(url=f"{record.accept_request_uri}",
                       content=st_nok_text + gt_nok_text,
                       color=ButtonColorEnum.DANGER)

        ]
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        rendered_items = format_html(self.render_helper.render_list_coherent(items=actions))
        self.render_helper.update_attrs = None
        return rendered_items


class PublishesRequestTable(PendingRequestTable):
    class Meta:
        model = PublishRequest
        fields = ('group', 'organization', 'message')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'publishers-for-table'


class GroupInvitationRequestTable(tables.Table):
    class Meta:
        model = PublishRequest
        fields = ('user', 'group', 'message')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'group-invitation-table'


class GroupTable(ActionTableMixin, tables.Table):
    class Meta:
        model = MrMapGroup
        fields = ('name', 'description', 'organization', 'actions')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'group-table'

    caption = _("Shows all groups which are configured in your Mr. Map environment.")

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_name(self, record, value):
        content = Tag(tag='i', attrs={"class": [IconEnum.PUBLIC.value]}) + ' ' + value if record.is_public_group else value
        return Link(url=record.detail_view_uri,
                    content=content,
                    tooltip=_('Click to open the detail view of <strong>{}</strong>').format(value)).render(safe=True)

    def render_organization(self, value):
        return Link(url=value.detail_view_uri,
                    content=value,
                    tooltip=_('Click to open the detail view of the organization')).render(safe=True)

    def render_actions(self, record):
        self.render_helper.update_attrs = {"class": ["btn-sm", "mr-1"]}
        renderd_actions = self.render_helper.render_list_coherent(items=record.get_actions(self.request))
        self.render_helper.update_attrs = None
        return format_html(renderd_actions)


class GroupDetailTable(tables.Table):
    inherited_permissions = tables.Column(verbose_name=_('Inherited Permissions'))

    class Meta:
        model = MrMapGroup
        fields = ('name', 'description', 'organization', 'permissions', 'inherited_permissions')
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'mrmapgroup-detail-table'
        orderable = False

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_permissions(self, record):
        perms = []
        for perm in record.permissions.all():
            perms.append(Badge(content=perm if perm else _('None'), pill=True))

        self.render_helper.update_attrs = {"class": ["mr-1"]}
        renderd_perms = self.render_helper.render_list_coherent(items=perms)
        self.render_helper.update_attrs = None
        return format_html(renderd_perms)

    def render_inherited_permissions(self, record):
        inherited_permission = []
        parent = record.parent_group
        while parent is not None:
            permissions = parent.permissions.all()
            perm_dict = {
                "group": parent,
                "permissions": permissions,
            }
            inherited_permission.append(perm_dict)
            parent = parent.parent_group

        perms = []
        for perm in inherited_permission:
            perms.append(Badge(content=perm if perm else _('None'), pill=True))

        self.render_helper.update_attrs = {"class": ["mr-1"]}
        renderd_perms = self.render_helper.render_list_coherent(items=perms)
        self.render_helper.update_attrs = None
        return format_html(renderd_perms)


class OrganizationDetailTable(tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name',
                  'parent',
                  'is_auto_generated',
                  'person_name',
                  'email',
                  'phone',
                  'facsimile',
                  'city',
                  'postal_code',
                  'address',
                  'state_or_province',
                  'country')
        template_name = "skeletons/django_tables2_vertical_table.html"
        prefix = 'organization-detail-table'
        orderable = False


class OrganizationTable(ActionTableMixin, tables.Table):
    class Meta:
        model = Organization
        fields = ('organization_name', 'description', 'is_auto_generated', 'parent')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"
        prefix = 'organizations-table'

    caption = _("Shows all organizations which are configured in your Mr. Map environment.")

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization_name(self, value, record):
        return Link(url=record.detail_view_uri, content=value).render(safe=True)

    @staticmethod
    def render_is_auto_generated(value):
        """ Preprocessing for rendering of is_auto_generated value.

        Due to semantic reasons, we invert this value.

        Args:
            value: The value
        Returns:

        """
        return get_ok_nok_icon(value)

    def render_actions(self, record):
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        rendered = self.render_helper.render_list_coherent(items=record.get_actions())
        self.render_helper.update_attrs = None
        return format_html(rendered)


class GroupMemberTable(ActionTableMixin, tables.Table):
    class Meta:
        model = MrMapUser
        fields = ('username', 'organization')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def __init__(self, group: MrMapGroup, *args, **kwargs):
        self.group = group
        super().__init__(*args, **kwargs)

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_actions(self, record):
        btns = []
        if self.group.user_set.count() > 1:
            remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
            st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
            gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                               content=remove_icon + _(' Remove').__str__()).render()

            members_querystring = "user_set"
            members_excluded_record = self.group.user_set.exclude(pk=record.pk)
            if members_excluded_record:
                members_querystring = ""
                for is_last_element, user in signal_last(members_excluded_record):
                    if is_last_element:
                        members_querystring += f"user_set={user.pk}"
                    else:
                        members_querystring += f"user_set={user.pk}&"

            btns.append(
                LinkButton(url=f"{self.group.edit_view_uri}?{members_querystring}",
                           content=st_edit_text + gt_edit_text,
                           color=ButtonColorEnum.DANGER,
                           tooltip=_(f"Remove <strong>{record}</strong> from <strong>{self.group}</strong>"),
                           tooltip_placement=TooltipPlacementEnum.LEFT)
            )
        return format_html(self.render_helper.render_list_coherent(items=btns))


class OrganizationMemberTable(ActionTableMixin, tables.Table):
    class Meta:
        model = MrMapUser
        fields = ('username', )
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def __init__(self, organization: Organization, *args, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_actions(self):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.DELETE.value]}).render()
        st_edit_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_edit_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                           content=remove_icon + _(' Remove').__str__()).render()
        btns = [

        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))


class MrMapUserTable(ActionTableMixin, tables.Table):
    class Meta:
        model = MrMapUser
        fields = ('username', 'organization', 'groups')
        template_name = "skeletons/django_tables2_bootstrap4_custom.html"

    def before_render(self, request):
        self.render_helper = RenderHelper(user_permissions=list(filter(None, request.user.get_all_permissions())))

    def render_organization(self, value):
        return Link(url=value.detail_view_uri, content=value).render(safe=True)

    def render_groups(self, record, value):
        links = []
        for group in value.all():
            link = Link(url=group.mrmapgroup.detail_view_uri, content=group.mrmapgroup)
            link_with_seperator = Tag(tag='span', content=link + ',')
            links.append(link_with_seperator)
        self.render_helper.update_attrs = {"class": ["mr-1"]}
        renderd_actions = self.render_helper.render_list_coherent(items=links)
        self.render_helper.update_attrs = None
        return format_html(renderd_actions)

    def render_actions(self, record):
        remove_icon = Tag(tag='i', attrs={"class": [IconEnum.ADD.value]}).render()
        st_invite_text = Tag(tag='div', attrs={"class": ['d-lg-none']}, content=remove_icon).render()
        gt_invite_text = Tag(tag='div', attrs={"class": ['d-none', 'd-lg-block']},
                             content=remove_icon + _(' Invite').__str__()).render()
        btns = [
            LinkButton(url=f"{record.invite_to_group_url}",
                       content=st_invite_text + gt_invite_text,
                       color=ButtonColorEnum.SUCCESS,
                       tooltip=_(f"Invite <strong>{record}</strong>"),
                       tooltip_placement=TooltipPlacementEnum.LEFT)
        ]
        return format_html(self.render_helper.render_list_coherent(items=btns))
