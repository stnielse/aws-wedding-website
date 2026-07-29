import django.db.models.deletion
from django.db import migrations, models


MEAL_CHOICES = [
    ('short_rib', 'Braised short rib'),
    ('trout', 'Trout, almondine'),
    ('farrotto', 'Wild mushroom farrotto'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('rsvp', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Party',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200)),
                ('lookup_code', models.CharField(max_length=20, unique=True)),
                ('notes', models.TextField(blank=True)),
            ],
            options={
                'verbose_name_plural': 'parties',
            },
        ),
        migrations.RemoveField(
            model_name='guest',
            name='lookup_code',
        ),
        # Guest table is empty at this point (Session 5's admin verification
        # created and cleaned up its test row; no real data has landed yet), so
        # the sentinel default of 1 is never applied to an existing row.
        # preserve_default=False keeps the temporary default out of the model.
        migrations.AddField(
            model_name='guest',
            name='party',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='guests',
                to='rsvp.party',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='rsvp',
            name='meal_choice',
            field=models.CharField(blank=True, choices=MEAL_CHOICES, max_length=100),
        ),
        migrations.AlterField(
            model_name='rsvp',
            name='plus_one_meal',
            field=models.CharField(blank=True, choices=MEAL_CHOICES, max_length=100),
        ),
    ]
