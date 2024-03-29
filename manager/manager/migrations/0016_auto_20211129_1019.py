# Generated by Django 2.2.17 on 2021-11-29 10:19
# ruff: noqa

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("manager", "0015_auto_20210917_0931"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuration",
            name="content_wikifundi_es",
            field=models.BooleanField(
                default=False,
                help_text="Wikipedia-like Editing Platform (Spanish)",
                verbose_name="WikiFundi ES",
            ),
        ),
        migrations.AlterField(
            model_name="configuration",
            name="content_nomad",
            field=models.BooleanField(
                default=False,
                help_text="Révisions du CP à la 3è",
                verbose_name="Nomad android apps",
            ),
        ),
    ]
