# Generated by Django 5.1.7 on 2025-07-05 18:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='atbat',
            name='actual_player',
            field=models.CharField(max_length=20),
        ),
        migrations.AlterField(
            model_name='atbat',
            name='original_player',
            field=models.CharField(max_length=20, null=True),
        ),
    ]
