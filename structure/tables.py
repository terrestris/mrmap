import django_tables2 as tables
from django.utils.html import format_html
from django.urls import reverse
from MapSkinner.utils import get_theme, get_ok_nok_icon
from MapSkinner.consts import URL_PATTERN

class PublisherTable(tables.Table):
    publisher_group = tables.Column(accessor='group', verbose_name='Group')
    publisher_org = tables.Column(accessor='group.organization', verbose_name='Group organization')
    publisher_action = tables.Column(verbose_name='Action', orderable=False)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_publisher_group(self, value, record):
        """ Renders publisher_group as link to detail view of group

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_publisher_org(self, value, record):
        """ Renders publisher_org as link to detail view of organization

        Args:
            value:
            record:
        Returns:

        """
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

class PublisherRequestTable(PublisherTable):
    class Meta:
        sequence = ("...", "publisher_action")

    message = tables.Column(accessor='message', verbose_name='Message')
    activation_until = tables.Column(accessor='activation_until', verbose_name='Activation until')
    publisher_action = tables.Column(verbose_name='Action', orderable=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class GroupTable(tables.Table):
    groups_name = tables.Column(accessor='name', verbose_name='Name', )
    groups_description = tables.Column(accessor='description', verbose_name='Description', )
    groups_organization = tables.Column(accessor='organization', verbose_name='Organization', )

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_groups_name(self, value, record):
        url = reverse('structure:detail-group', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    def render_groups_organization(self, value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )


class OrganizationTable(tables.Table):
    orgs_organization_name = tables.Column(accessor='organization_name', verbose_name='Name', )
    orgs_description = tables.Column(accessor='description', verbose_name='Description', )
    orgs_is_auto_generated = tables.Column(accessor='is_auto_generated', verbose_name='Real organization', )
    orgs_parent = tables.Column(accessor='parent', verbose_name='Parent',)

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)

    def render_orgs_organization_name(self, value, record):
        url = reverse('structure:detail-organization', args=(record.id,))
        return format_html(URL_PATTERN, get_theme(self.user)["TABLE"]["LINK_COLOR"], url, value, )

    @staticmethod
    def render_orgs_is_auto_generated(value):
        """ Preprocessing for rendering of is_auto_generated value.

        Due to semantic reasons, we invert this value.

        Args:
            value: The value
        Returns:

        """
        val = not value
        return get_ok_nok_icon(val)
