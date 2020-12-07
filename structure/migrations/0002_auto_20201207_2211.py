# Generated by Django 3.1.2 on 2020-12-07 21:11

import MrMap.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('structure', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='pendingtask',
            name='type',
            field=models.CharField(blank=True, choices=[(None, '---'), ('harvest', 'harvest'), ('register', 'register'), ('validate', 'validate')], max_length=500, null=True, validators=[MrMap.validators.validate_pending_task_enum_choices]),
        ),
        migrations.AlterField(
            model_name='permission',
            name='name',
            field=models.CharField(choices=[(None, '---'), ('can_create_organization', 'can_create_organization'), ('can_edit_organization', 'can_edit_organization'), ('can_delete_organization', 'can_delete_organization'), ('can_create_group', 'can_create_group'), ('can_delete_group', 'can_delete_group'), ('can_edit_group', 'can_edit_group'), ('can_add_user_to_group', 'can_add_user_to_group'), ('can_remove_user_from_group', 'can_remove_user_from_group'), ('can_edit_group_role', 'can_edit_group_role'), ('can_edit_metadata', 'can_edit_metadata'), ('can_activate_resource', 'can_activate_resource'), ('can_update_resource', 'can_update_resource'), ('can_register_resource', 'can_register_resource'), ('can_remove_resource', 'can_remove_resource'), ('can_add_dataset_metadata', 'can_add_dataset_metadata'), ('can_remove_dataset_metadata', 'can_remove_dataset_metadata'), ('can_toggle_publish_requests', 'can_toggle_publish_requests'), ('can_remove_publisher', 'can_remove_publisher'), ('can_request_to_become_publisher', 'can_request_to_become_publisher'), ('can_generate_api_token', 'can_generate_api_token'), ('can_harvest', 'can_harvest'), ('can_access_logs', 'can_access_logs'), ('can_download_logs', 'can_download_logs'), ('can_run_monitoring', 'can_run_monitoring'), ('can_run_validation', 'can_run_validation')], max_length=500, unique=True),
        ),
    ]
