# Generated by Django 5.2 on 2025-04-24 15:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('nodes', '0007_alter_devicemetrics_logged_time_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='nodeapikey',
            name='created_by',
        ),
    ]
