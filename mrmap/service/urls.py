from django.urls import path

from editor.views import EditMetadata, RestoreMetadata, DatasetDelete
from editor.wizards import ACCESS_EDITOR_WIZARD_FORMS, AccessEditorWizard, EditDatasetWizard, DATASET_WIZARD_FORMS
from service.autocompletes import MetadataAutocomplete, MetadataServiceAutocomplete, MetadataLayerAutocomplete, \
    MetadataFeaturetypeAutocomplete, MetadataCatalougeAutocomplete
from service.views import *
from service.wizards import NewResourceWizard, NEW_RESOURCE_WIZARD_FORMS

app_name = 'resource'
urlpatterns = [
    # index views
    path('wms/', WmsIndexView.as_view(), name='wms-index'),
    path('wfs/', WfsIndexView.as_view(), name='wfs-index'),
    path('csw/', CswIndexView.as_view(), name='csw-index'),
    path('datasets/', DatasetIndexView.as_view(), name='datasets-index'),
    path('logs/', LogsIndexView.as_view(), name='logs-view'),

    # PendingTasks
    path('pending-tasks/', PendingTaskView.as_view(), name="pending-tasks"),

    # actions
    path('add', NewResourceWizard.as_view(form_list=NEW_RESOURCE_WIZARD_FORMS,), name='add'),
    path('<pk>/remove', ResourceDeleteView.as_view(), name='remove'),
    path('<pk>/remove-dataset', DatasetDelete.as_view(), name='remove-dataset-metadata'),
    path('<pk>/edit-metadata', EditMetadata.as_view(), name='edit'),
    path('<pk>/edit-dataset-metadata', EditDatasetWizard.as_view(form_list=DATASET_WIZARD_FORMS, ignore_uncomitted_forms=True), name="dataset-metadata-wizard-instance"),
    path('<pk>/restore', RestoreMetadata.as_view(), name='restore'),
    path('<pk>/activate', ResourceActivateDeactivateView.as_view(), name='activate'),
    path('<pk>/access-edit', AccessEditorWizard.as_view(form_list=ACCESS_EDITOR_WIZARD_FORMS), name='access-editor-wizard'),
    # todo: refactor as generic view
    path('metadata/<metadata_id>/subscribe', metadata_subscription_new, name='subscription-new'),

    # todo: refactoring this as a generic view
    path('new-update/<metadata_id>', new_pending_update_service, name='new-pending-update'),
    path('pending-update/<metadata_id>', pending_update_service, name='pending-update'),
    path('dismiss-pending-update/<metadata_id>', dismiss_pending_update_service, name='dismiss-pending-update'),
    path('run-update/<metadata_id>', run_update_service, name='run-update'),

    # serivce urls
    # todo: refactoring this as a generic view
    path('metadata/<metadata_id>', get_service_metadata, name='get-service-metadata'),
    path('metadata/dataset/<pk>', DatasetMetadataXmlView.as_view(), name='get-dataset-metadata'),
    path('metadata/<metadata_id>/operation', get_operation_result, name='metadata-proxy-operation'),
    path('metadata/<metadata_id>/legend/<int:style_id>', get_metadata_legend, name='metadata-proxy-legend'),

    # detail view
    # todo: implement detail view for csw
    path('<pk>', ResourceTreeView.as_view(), name='detail'),
    path('<pk>/table', ResourceDetailTableView.as_view(), name='detail-table'),
    path('<pk>/related-datasets', ResourceRelatedDatasetView.as_view(), name='detail-related-datasets'),

    # html metadata detail view
    # todo: refactoring as class based detailview. Maybe we could use the ResourceTreeView
    path('metadata/html/<pk>', MetadataHtml.as_view(), name='get-metadata-html'),
    path('preview/<metadata_id>', get_service_preview, name='get-service-metadata-preview'),

    # autocompletes
    path('autocompletes/metadatas', MetadataAutocomplete.as_view(), name='autocomplete_metadata'),
    path('autocompletes/service-metadatas', MetadataServiceAutocomplete.as_view(), name='autocomplete_metadata_service'),
    path('autocompletes/layer-metadatas', MetadataLayerAutocomplete.as_view(), name='autocomplete_metadata_layer'),
    path('autocompletes/featuretype-metadatas', MetadataFeaturetypeAutocomplete.as_view(), name='autocomplete_metadata_featuretype'),
    path('autocompletes/catalouge-metadatas', MetadataCatalougeAutocomplete.as_view(), name='autocomplete_metadata_catalouge'),
]

