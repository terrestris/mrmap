# Generated by Django 3.1.5 on 2021-01-27 15:49

import MrMap.validators
import django.contrib.gis.db.models.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('service', '0007_auto_20210127_1608'),
    ]

    operations = [
        migrations.AlterField(
            model_name='allowedoperation',
            name='allowed_area',
            field=django.contrib.gis.db.models.fields.GeometryCollectionField(blank=True, null=True, srid=4326, validators=[MrMap.validators.geometry_is_empty]),
        ),
    ]
