# Generated by Django 2.1.5 on 2019-03-10 03:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('collector', '0004_sailingdetailrun'),
    ]

    operations = [
        migrations.AddField(
            model_name='run',
            name='info',
            field=models.TextField(blank=True, null=True),
        ),
    ]
