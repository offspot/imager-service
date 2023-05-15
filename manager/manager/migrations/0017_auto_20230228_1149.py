# Generated by Django 2.2.17 on 2023-02-28 11:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('manager', '0016_auto_20211129_1019'),
    ]

    operations = [
        migrations.AddField(
            model_name='configuration',
            name='content_africatikmd',
            field=models.BooleanField(default=False, help_text='Applications éducatives adaptées au contexte culturel africain (version Maisons digitales)', verbose_name='Africatik Maisons digitales'),
        ),
        migrations.AlterField(
            model_name='configuration',
            name='content_africatik',
            field=models.BooleanField(default=False, help_text='Applications éducatives adaptées au contexte culturel africain (version Écoles numériques)', verbose_name='Africatik Écoles'),
        ),
    ]