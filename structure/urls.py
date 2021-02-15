from django.urls import path
from structure.views import *

app_name = 'structure'
urlpatterns = [

    # PendingTask
    path('tasks/<pk>/remove', PendingTaskDelete.as_view(), name='remove-task'),
    path('report/error/<report_id>', generate_error_report, name='generate-error-report'),

    path('', index, name='index'),

    # MrMapGroup
    path('groups', MrMapGroupTableView.as_view(), name='group_overview'),
    path('groups/new', NewMrMapGroup.as_view(), name='group_new'),
    path('groups/<pk>', MrMapGroupDetailView.as_view(), name='group_details'),
    path('groups/<pk>/members', MrMapGroupMembersTableView.as_view(), name='group_members'),
    path('groups/<pk>/members/remove/<user_id>', RemoveUserFromGroupView.as_view(), name='group_members_remove'),
    path('groups/<pk>/edit', EditGroupView.as_view(), name='group_edit'),
    path('groups/<pk>/remove', DeleteMrMapGroupView.as_view(), name='group_remove'),
    path('groups/<pk>/publishers', MrMapGroupPublishersTableView.as_view(), name='group_publisher_overview'),

    # Publishers
    path('publish-requests', PublishRequestTableView.as_view(), name='publish_request_overview'),
    path('publish-requests/new', PublishRequestNewView.as_view(), name='publish_request_new'),
    path('publish-requests/<pk>/accept', PublishRequestAcceptView.as_view(), name='publish_request_accept'),

    # Organization
    path('organizations', OrganizationTableView.as_view(), name='organization_overview'),
    path('organizations/new', OrganizationNew.as_view(), name='organizations_new'),
    path('organizations/<pk>', OrganizationDetailView.as_view(), name='organization_details'),
    # path('organizations/<pk>/edit'),
    # path('organizations/<pk>/remove'),
    # path('organizations/<pk>/publishers', MrMapGroupPublishersTableView.as_view(), name='organization_publisher_overview'),

    path('organizations/edit/<object_id>', edit_org, name='edit-organization'),
    path('organizations/delete/<object_id>', remove_org, name='delete-organization'),
    # path('organizations/create-publish-request/<org_id>/', publish_request, name='publish-request'),
    path('organizations/<org_id>/remove-publisher/<group_id>/', remove_publisher, name='remove-publisher'),
    # path('organizations/new/register-form/', new_org, name='organizations_new'),



    path('users/', users_index, name='users-index'),
    path('users/<object_id>/group-invitation/', user_group_invitation, name='invite-user-to-group'),
    path('group-invitation/<object_id>/', toggle_group_invitation, name='toggle-user-to-group'),
]

