# Generated by Django 2.1.7 on 2019-03-01 05:20

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('collector', '0003_rawhtml_data'),
    ]

    operations = [
        migrations.CreateModel(
            name='SailingDetailRun',
            fields=[
                ('run_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='collector.Run')),
            ],
            options={
                'abstract': False,
                'base_manager_name': 'objects',
            },
            bases=('collector.run',),
        ),
    ]
