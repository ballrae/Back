# Generated by Django 5.1.7 on 2025-07-09 09:14

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0012_alter_atbat_on_base'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='player',
            name='player_code',
        ),
    ]
