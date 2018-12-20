# Generated by Django 2.1.3 on 2018-12-20 20:43

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('data', '0015_sailing_sailing_created'),
    ]

    operations = [
        migrations.CreateModel(
            name='CancelledEvent',
            fields=[
                ('sailingevent_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='data.SailingEvent')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('data.sailingevent',),
        ),
    ]