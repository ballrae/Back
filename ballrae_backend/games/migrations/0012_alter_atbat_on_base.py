# Generated by Django 5.1.7 on 2025-07-09 08:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('games', '0011_atbat_out_atbat_score'),
    ]

    operations = [
        migrations.AlterField(
            model_name='atbat',
            name='on_base',
            field=models.CharField(max_length=50, null=True),
        ),
    ]
