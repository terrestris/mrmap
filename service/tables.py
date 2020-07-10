import csv

import django_tables2 as tables
from django.db.models.functions import Length
from django.utils.html import format_html
from django.urls import reverse
import json
from MrMap.celery_app import app
from celery.result import AsyncResult

from MrMap.columns import MrMapColumn
from MrMap.tables import MrMapTable
from MrMap.utils import get_theme, get_ok_nok_icon
from MrMap.consts import construct_url
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from service.helper.enums import ResourceOriginEnum
from structure.models import Permission


def _get_action_btns_for_service_table(table, record):
    btns = ''
    btns += table.get_btn(
        href=reverse('service:activate', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_WARNING_COLOR" if record.is_active else "BTN_SUCCESS_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]["NOK" if record.is_active else 'OK'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"{'Deactivate' if record.is_active else 'Activate'} service <strong>{record.title} [{record.id}]</strong>"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('service:new-pending-update', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_INFO_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['UPDATE'],
        permission=Permission(can_update_service=True),
        tooltip=format_html(_(f"Update service: <strong>{record.title} [{record.id}]</strong>"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('editor:edit', args=(record.id,)) + f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_WARNING_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['EDIT'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"Edit metadata of <strong>{record.title} [{record.id}]</strong>"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('editor:edit_access', args=(record.id,)),
        btn_color=get_theme(table.user)["TABLE"]["BTN_WARNING_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['EDIT'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"Edit access of <strong>{record.title} [{record.id}]</strong> service"), ),
        tooltip_placement='left', )

    btns += table.get_btn(
        href=reverse('editor:restore', args=(record.id, ))+f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_DANGER_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['UNDO'],
        permission=Permission(can_edit_metadata_service=True),
        tooltip=format_html(_(f"Restore <strong>{record.title} [{record.id}]</strong> metadata"), ),
        tooltip_placement='left',
    )

    btns += table.get_btn(
        href=reverse('service:remove', args=(record.id,)) + f"?current-view={table.current_view}",
        btn_color=get_theme(table.user)["TABLE"]["BTN_DANGER_COLOR"],
        btn_value=get_theme(table.user)["ICONS"]['REMOVE'],
        permission=Permission(can_remove_service=True),
        tooltip=format_html(_(f"Remove <strong>{record.title} [{record.id}]</strong> metadata"), ),
        tooltip_placement='left',
    )
    return format_html(btns)


class WmsServiceTable(MrMapTable):

    attrs = {
        "th": {
            "class": "align-middle",
        }
    }
    wms_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        empty_values=[],
        attrs=attrs,
        tooltip=_('The title of the service'),)
    wms_active = MrMapColumn(
        accessor='is_active',
        verbose_name=_('Active'),
        attrs=attrs,
        tooltip=_('The state of the service. If the service is deactivated, the service is not provided to external by Mr. Map.'))
    wms_secured_access = MrMapColumn(
        accessor='is_secured',
        verbose_name=_('Secured access'),
        attrs=attrs,
        tooltip=_('If the service is secured, Mr. Map provides it only if the right credentials are provided by the requesting user.'),)
    wms_secured_externally = MrMapColumn(
        accessor='external_authentication',
        verbose_name=_('Secured externally'),
        empty_values=[False, ],
        attrs=attrs,
        tooltip=_('Shows if the service is secured by the external MapServer. Mr. Map can also secure the endpoint. See secured access for that.'),)
    wms_version = MrMapColumn(
        accessor='service.service_type.version',
        verbose_name=_('Version'),
        attrs=attrs,
        tooltip=_('The version of the service'),)
    wms_data_provider = MrMapColumn(
        accessor='contact.organization_name',
        verbose_name=_('Data provider'),
        attrs=attrs,
        tooltip=_('The organization which is liable for the service.'),)
    wms_registered_by_group = MrMapColumn(
        accessor='service.created_by',
        verbose_name=_('Registered by group'),
        attrs=attrs,
        tooltip=_('The group which has registered the service'),)
    wms_registered_for = MrMapColumn(
        accessor='service.published_for',
        verbose_name=_('Registered for'),
        attrs=attrs,
        tooltip=_('The organization for that the service is registered.'),)
    wms_created_on = MrMapColumn(
        accessor='created',
        verbose_name=_('Created on'),
        attrs=attrs,
        tooltip=_('The date of creation of this service in our Mr. Map system.'),)
    wms_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=_('Actions you can perform'),
        attrs={"td": {"style": "white-space:nowrap;"}})

    def render_wms_title(self, value, record):
        url = reverse('service:detail', args=(record.id,))
        tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip, )

    @staticmethod
    def render_wms_active(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wms_secured_access(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wms_secured_externally(value):
        return get_ok_nok_icon(value)

    def render_wms_data_provider(self, value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip, )

    def render_wms_registered_by_group(self, value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip, )

    def render_wms_registered_for(self, value, record):
        if record.service.published_for is not None:
            url = reverse('structure:detail-organization', args=(record.service.published_for.id,))
            tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
            return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                                 href=url,
                                 content=value,
                                 tooltip=tooltip, )
        else:
            return value

    def render_wms_actions(self, record):
        return _get_action_btns_for_service_table(self, record)


class WmsTableWms(WmsServiceTable):
    caption = _("Shows all WMS which are configured in your Mr. Map environment.")

    attrs = {
        "th": {
            "class": "align-middle",
        }
    }
    wms_layers = tables.Column(verbose_name=_('Layers'), empty_values=[], attrs=attrs)

    class Meta:
        sequence = ("wms_title", "wms_layers", "...")
        row_attrs = {
            "class": "text-center"
        }

    @staticmethod
    def render_wms_layers(record):
        count = record.service.child_service.count()
        return str(count)

    @staticmethod
    def order_wms_layers(queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__child_service")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True


class WmsLayerTableWms(WmsServiceTable):
    wms_parent_service = MrMapColumn(
        verbose_name=_('Parent service'),
        empty_values=[],
        tooltip=_('The root service of this layer'), )

    caption = _("Shows all WMS sublayers which are configured in your Mr. Map environment.")

    class Meta:
        sequence = ("wms_title", "wms_parent_service", "...")
        row_attrs = {
            "class": "text-center"
        }

    def render_wms_parent_service(self, record):
        url = reverse('service:detail', args=(record.service.parent_service.metadata.id,))
        tooltip = _(f'Click to open the detail view of <strong>{record.service.parent_service.metadata.title}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=record.service.parent_service.metadata.title,
                             tooltip=tooltip, )

    @staticmethod
    def order_wms_parent_service(queryset, is_descending):
        queryset = queryset.annotate(
            title_length=Length("service__parent_service__metadata__title")
        ).order_by(("-" if is_descending else "") + "title_length")
        return queryset, True


class WfsServiceTable(MrMapTable):
    caption = _("Shows all WFS which are configured in your Mr. Map environment.")

    class Meta:
        row_attrs = {
            "class": "text-center"
        }

    wfs_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        tooltip=_('The title of the service'),)
    wfs_featuretypes = MrMapColumn(
        verbose_name=_('Featuretypes'),
        empty_values=[], )
    wfs_active = MrMapColumn(
        accessor='is_active',
        verbose_name=_('Active'),
        tooltip=_('The state of the service. If the service is deactivated, the service is not provided to external by Mr. Map.'),)
    wfs_secured_access = MrMapColumn(
        accessor='is_secured',
        verbose_name=_('Secured access'),
        tooltip=_('If the service is secured, Mr. Map provides it only if the right credentials are provided by the requesting user.'),)
    wfs_secured_externally = MrMapColumn(
        accessor='external_authentication',
        verbose_name=_('Secured externally'),
        empty_values=[False, ],
        tooltip=_('Shows if the service is secured by the external MapServer. Mr. Map can also secure the endpoint. See secured access for that.'),)
    wfs_version = MrMapColumn(
        accessor='service.service_type.version',
        verbose_name=_('Version'),
        tooltip=_('The version of the service'),)
    wfs_data_provider = MrMapColumn(
        accessor='contact.organization_name',
        verbose_name=_('Data provider'),
        tooltip=_('The organization which is liable for the service.'),)
    wfs_registered_by_group = MrMapColumn(
        accessor='service.created_by',
        verbose_name=_('Registered by group'),
        tooltip=_('The group which has registered the service'),)
    wfs_registered_for = MrMapColumn(
        accessor='service.published_for',
        verbose_name=_('Registered for'),
        tooltip=_('The organization for that the service is registered.'),)
    wfs_created_on = MrMapColumn(
        accessor='created',
        verbose_name=_('Created on'),
        tooltip=_('The date of creation of this service in our Mr. Map system.'),)
    wfs_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=_('Actions you can perform'),
        attrs={"td": {"style": "white-space:nowrap;"}})

    def render_wfs_title(self, value, record):
        url = reverse('service:detail', args=(record.id,))
        tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip, )

    @staticmethod
    def render_wfs_featuretypes(record):
        count = record.service.featuretypes.count()
        return str(count)

    @staticmethod
    def render_wfs_active(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wfs_active(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wfs_secured_access(value):
        return get_ok_nok_icon(value)

    @staticmethod
    def render_wfs_secured_externally(value):
        return get_ok_nok_icon(value)

    def render_wfs_data_provider(self, value, record):
        url = reverse('structure:detail-organization', args=(record.contact.id,))
        tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip, )

    def render_wfs_registered_by_group(self, value, record):
        url = reverse('structure:detail-group', args=(record.service.created_by.id,))
        tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip, )

    def render_wfs_registered_for(self, value, record):
        if record.service.published_for is not None:
            url = reverse('structure:detail-organization', args=(record.service.published_for.id,))
            tooltip = _(f'Click to open the detail view of <strong>{value}</strong>.')
            return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                                 href=url,
                                 content=value,
                                 tooltip=tooltip, )
        else:
            return value

    def render_wfs_actions(self, record):
        return _get_action_btns_for_service_table(self, record)

    @staticmethod
    def order_wfs_featuretypes(queryset, is_descending):
        queryset = queryset.annotate(
            count=Count("service__featuretypes")
        ).order_by(("-" if is_descending else "") + "count")
        return queryset, True


class PendingTasksTable(MrMapTable):
    caption = _("Shows all currently running pending tasks.")
    pt_status = tables.Column(verbose_name=_('Status'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-1"}})
    pt_service = tables.Column(verbose_name=_('Service'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-3"}})
    pt_phase = tables.Column(verbose_name=_('Phase'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-4"}})
    pt_progress = tables.Column(verbose_name=_('Progress'), empty_values=[], orderable=False, attrs={"th": {"class": "col-sm-3"}})
    pt_actions = tables.Column(verbose_name=_('Cancle task'), empty_values=[], orderable=False, attrs={"td": {"style": "white-space:nowrap;"}, "th": {"class": "col-sm-1"}})

    def render_pt_actions(self, record):
        btns = ''
        btns += self.get_btn(href=reverse('structure:remove-task', args=(record.id,)),
                             permission=Permission(),
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['WINDOW_CLOSE'], )
        return format_html(btns)

    @staticmethod
    def render_pt_status():
        return format_html('<div class="spinner-border spinner-border-sm" role="status">'
                           '<span class="sr-only">Loading...</span>'
                           '</div>')

    @staticmethod
    def render_pt_service(record):
        # TODO: remove this sticky json
        return str(json.loads(record.description)['service']) if 'service' in json.loads(record.description) else _('unknown')

    @staticmethod
    def render_pt_phase(record):
        # TODO: remove this sticky json
        return str(json.loads(record.description)['phase']) if 'phase' in json.loads(record.description) else _('unknown')

    @staticmethod
    def render_pt_progress(record):
        task = AsyncResult(record.task_id, app=app)
        try:
            info_dict = task.info

            if info_dict is not None:
                if task.info['current'] is None:
                    progress_value = '1'  # 1 % to show something ¯\_(ツ)_/¯
                else:
                    progress_value = str(int(task.info['current']))
            else:
                progress_value = '1' # 1 % to show something ¯\_(ツ)_/¯

            return format_html('<div class="progress">' \
                               '<div class="progress-bar progress-bar-striped progress-bar-animated" role="progressbar" ' \
                               'aria-valuenow="' + progress_value + '" aria-valuemin="0" aria-valuemax="100" ' \
                                                                    'style="width: ' + progress_value + '%">'+ progress_value + \
                                                                                                        ' %</div>' \
                                                                                                        '</div>')
        except Exception as e:
            return str(e)


class ChildLayerTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    child_layer_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all child layer of current WMS.")

    @staticmethod
    def render_child_layer_title(record):
        url = reverse('service:get-metadata-html', args=(record['id'],))

        if record['sublayers_count'] > 0:
            return format_html("<a href='{}'>{} <span class='badge badge-secondary'>{}</span></a>",
                               url,
                               record['title'],
                               record['sublayers_count'])
        else:
            return format_html("<a href='{}'>{}</a>",
                               url,
                               record['title'], )


class FeatureTypeTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    featuretype_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all featuretypes of current WFS.")

    @staticmethod
    def render_featuretype_title(record):
        url = reverse('service:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class CoupledMetadataTable(MrMapTable):
    id = tables.Column(visible=False)
    title = tables.Column(visible=False)
    coupled_metadata_title = tables.Column(empty_values=[], order_by='title', )

    caption = _("Shows all coupled metadata of current service.")

    @staticmethod
    def render_coupled_metadata_title(record):
        url = reverse('service:get-metadata-html', args=(record['id'],))

        return format_html("<a href='{}'>{}</a>",
                           url,
                           record['title'], )


class UpdateServiceElements(MrMapTable):
    title = tables.Column(empty_values=[],)
    identifier = tables.Column(empty_values=[],)


class ProxyLogTable(MrMapTable):
    caption = _("Shows all logs for a service.")

    class Meta:
        row_attrs = {
            "class": "text-center"
        }

    id = MrMapColumn(accessor='id',
                     verbose_name=_('Log ID'),
                     tooltip=_("The id of the ProxyLog"))
    metadata_title = MrMapColumn(accessor='metadata.title',
                                 verbose_name=_('Service Title'),
                                 tooltip=_("The title of the related service"))
    user_name = MrMapColumn(accessor='user',
                            verbose_name=_('User'),
                            tooltip=_("Name of the user which produced this log entry"))
    timestamp = MrMapColumn(accessor='timestamp',
                            verbose_name=_('Timestamp'),
                            tooltip=_("Timestamp when the entry was produced"))
    operation = MrMapColumn(accessor='operation',
                            tooltip=_("Operation param of the request"),
                            verbose_name=_('Operation'), )

    @staticmethod
    def render_metadata_title(record):
        return "{} #{}".format(record.metadata.title, record.metadata.id)

    def fill_csv_response(self, stream):
        csv_writer = csv.writer(stream)
        csv_writer.writerow([
            _("ID"),
            _("Title"),
            _("User"),
            _("Operation"),
            _("Delivered Features (WFS)"),
            _("Delivered Megapixel (WMS)"),
            _("Timestamp"),
        ])
        for log in self.data.data:
            csv_writer.writerow(
                [
                    log.id,
                    log.metadata.title,
                    log.user,
                    log.operation,
                    log.response_wfs_num_features,
                    log.response_wms_megapixel,
                    log.timestamp,
                ]
            )
        return stream.getvalue()


class DatasetTable(MrMapTable):
    caption = _("Shows all datasets which are configured in your Mr. Map environment. You can Edit them if you want.")

    dataset_title = MrMapColumn(
        accessor='title',
        verbose_name=_('Title'),
        tooltip=_('The title of the dataset'),)
    dataset_related_objects = MrMapColumn(
        verbose_name=_('Related objects'),
        empty_values=[],
        tooltip=_('The related service from which this dataset is referenced'),)
    dataset_origins = MrMapColumn(
        verbose_name=_('Origins'),
        empty_values=[],
        tooltip=_('Tells us where the information\'s comes from. One item from column Related objects is referenced to one item in this column.'))
    dataset_actions = MrMapColumn(
        verbose_name=_('Actions'),
        empty_values=[],
        orderable=False,
        tooltip=_('Actions you can perform'),
        attrs={"td": {"style": "white-space:nowrap;"}})

    def render_dataset_title(self, value, record):
        url = reverse('service:get-metadata-html', args=(record.id,))
        tooltip = _(f'Click to open the html view of dataset <strong>{value}</strong>')
        return construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                             href=url,
                             content=value,
                             tooltip=tooltip,
                             new_tab=True)

    def render_dataset_related_objects(self, record):
        relations = record.related_metadata.all()
        link_list = []
        for relation in relations:
            url = reverse('service:detail', args=(relation.metadata_from.id,))
            tooltip = _(f'Click to open the detail view of related service <strong>{relation.metadata_from.title} [{relation.metadata_from.id}]"</strong>')
            link = construct_url(classes=get_theme(self.user)["TABLE"]["LINK_COLOR"],
                                 href=url,
                                 content=f"{relation.metadata_from.title} [{relation.metadata_from.id}]",
                                 tooltip=tooltip, )
            link_list.append(link, )
        return format_html(', '.join(link_list))

    def render_dataset_origins(self, record):
        relations = record.related_metadata.all()
        origin_list = []
        for relation in relations:
            origin_list.append(f"{relation.origin} [{relation.metadata_from.id}]")
        return format_html(', '.join(origin_list))

    def render_dataset_actions(self, record):
        relations = record.related_metadata.all()
        is_mr_map_origin = True
        for relation in relations:
            if relation.origin != ResourceOriginEnum.EDITOR:
                is_mr_map_origin = False
                break

        btns = ''
        btns += self.get_btn(href=reverse('editor:dataset-metadata-wizard-instance', args=(record.id,))+f"?current-view={self.current_view}",
                             permission=Permission(can_edit_dataset_metadata=True),
                             tooltip=format_html(_(f"Edit <strong>{record.title} [{record.id}]</strong> dataset")),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_WARNING_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['EDIT'],)

        btns += self.get_btn(href=reverse('editor:restore-dataset-metadata', args=(record.id,))+f"?current-view={self.current_view}",
                             permission=Permission(can_restore_dataset_metadata=True),
                             tooltip=format_html(_(f"Restore <strong>{record.title} [{record.id}]</strong> dataset")),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['UNDO'],
                             ) if not is_mr_map_origin else ''

        btns += self.get_btn(href=reverse('editor:remove-dataset-metadata', args=(record.id,))+f"?current-view={self.current_view}",
                             permission=Permission(can_remove_dataset_metadata=True),
                             tooltip=format_html(_(f"Remove <strong>{record.title} [{record.id}]</strong> dataset"), ),
                             tooltip_placement='left',
                             btn_color=get_theme(self.user)["TABLE"]["BTN_DANGER_COLOR"],
                             btn_value=get_theme(self.user)["ICONS"]['REMOVE'],
                             ) if is_mr_map_origin else ''

        return format_html(btns)