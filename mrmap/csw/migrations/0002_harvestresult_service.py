# Generated by Django 3.1.8 on 2021-04-13 07:35

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('service', '0001_initial'),
        ('csw', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='harvestresult',
            name='service',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='service.service'),
        ),
    ]
