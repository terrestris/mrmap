# Generated by Django 3.1.8 on 2021-04-15 14:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('service', '0004_auto_20210415_1539'),
    ]

    operations = [
        migrations.AlterField(
            model_name='genericurl',
            name='url',
            field=models.URLField(max_length=4096),
        ),
    ]
