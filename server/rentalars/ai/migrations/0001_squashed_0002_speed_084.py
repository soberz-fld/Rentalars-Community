# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``ai`` from 0001_initial to 0002_speed_084 in one.

Squashed: a new database is built from here, and a database that has applied the replaced
migrations counts it as applied (``replaces``). Data steps that only converted the data of older
versions are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('ai', '0001_initial'), ('ai', '0002_speed_084')]

    initial = True

    dependencies = [
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='AIProvider',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True, verbose_name='name')),
                ('base_url', models.CharField(help_text='The address the interface answers at, ending in /v1 for most servers.', max_length=300, verbose_name='base URL')),
                ('model', models.CharField(help_text='The name of the model as the server knows it.', max_length=200, verbose_name='model')),
                ('api_key_encrypted', models.TextField(blank=True, editable=False, verbose_name='API key')),
                ('timeout_seconds', models.PositiveSmallIntegerField(default=120, help_text='How long Rentalars waits when the server sends nothing – the answer itself may take longer.', validators=[django.core.validators.MinValueValidator(5), django.core.validators.MaxValueValidator(900)], verbose_name='timeout in seconds')),
                ('context_tokens', models.PositiveIntegerField(default=8192, help_text='How much text the model takes at once; long correspondence is summarised in parts.', validators=[django.core.validators.MinValueValidator(2048), django.core.validators.MaxValueValidator(2000000)], verbose_name='context size in tokens')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
            ],
            options={
                'verbose_name': 'AI provider',
                'verbose_name_plural': 'AI providers',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AICall',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='time')),
                ('use', models.CharField(choices=[('summary', 'Summary of the correspondence'), ('draft', 'Reply draft for mails'), ('test', 'Test')], max_length=10, verbose_name='use')),
                ('provider_label', models.CharField(max_length=120, verbose_name='provider')),
                ('is_local', models.BooleanField(default=False, verbose_name='local AI')),
                ('model', models.CharField(blank=True, max_length=200, verbose_name='model')),
                ('duration_ms', models.PositiveIntegerField(default=0, verbose_name='duration in ms')),
                ('request_chars', models.PositiveIntegerField(default=0, verbose_name='characters sent')),
                ('response_chars', models.PositiveIntegerField(default=0, verbose_name='characters received')),
                ('prompt_tokens', models.PositiveIntegerField(blank=True, null=True, verbose_name='tokens sent')),
                ('completion_tokens', models.PositiveIntegerField(blank=True, null=True, verbose_name='tokens received')),
                ('ok', models.BooleanField(default=True, verbose_name='successful')),
                ('error', models.CharField(blank=True, max_length=300, verbose_name='error')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='projects.project', verbose_name='project')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='user')),
                ('generation_per_second', models.FloatField(blank=True, null=True, verbose_name='written per second')),
                ('prompt_per_second', models.FloatField(blank=True, null=True, verbose_name='read per second')),
            ],
            options={
                'verbose_name': 'AI call',
                'verbose_name_plural': 'AI calls',
                'ordering': ['-timestamp', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AISettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('summary_source', models.CharField(choices=[('off', 'Off'), ('local', 'Local AI'), ('provider', 'Provider')], default='off', max_length=10, verbose_name='summary of the correspondence')),
                ('draft_source', models.CharField(choices=[('off', 'Off'), ('local', 'Local AI'), ('provider', 'Provider')], default='off', max_length=10, verbose_name='reply draft')),
                ('local_test_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('local_test_tokens_per_second', models.FloatField(blank=True, editable=False, null=True)),
                ('local_test_seconds', models.FloatField(blank=True, editable=False, null=True)),
                ('local_test_model', models.CharField(blank=True, editable=False, max_length=200)),
                ('draft_provider', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ai.aiprovider', verbose_name='provider of the reply drafts')),
                ('summary_provider', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ai.aiprovider', verbose_name='provider of the summaries')),
                ('local_test_prompt_per_second', models.FloatField(blank=True, editable=False, null=True)),
            ],
            options={
                'verbose_name': 'AI settings',
                'verbose_name_plural': 'AI settings',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='AISummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('text', models.TextField(verbose_name='summary')),
                ('model', models.CharField(max_length=200, verbose_name='model')),
                ('provider_label', models.CharField(max_length=120, verbose_name='provider')),
                ('is_local', models.BooleanField(default=True, verbose_name='local AI')),
                ('language', models.CharField(default='de', max_length=10, verbose_name='language')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('mail_count', models.PositiveIntegerField(default=0, verbose_name='number of mails')),
                ('newest_mail_id', models.PositiveIntegerField(default=0)),
                ('newest_mail_date', models.DateTimeField(blank=True, null=True)),
                ('include_chat', models.BooleanField(default=False, verbose_name='with the chat')),
                ('newest_chat_id', models.PositiveIntegerField(default=0)),
                ('covered_projects', models.JSONField(default=list)),
                ('parts', models.PositiveSmallIntegerField(default=1)),
                ('duration_seconds', models.FloatField(default=0)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
                ('project', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='ai_summary', to='projects.project', verbose_name='project')),
            ],
            options={
                'verbose_name': 'AI summary',
                'verbose_name_plural': 'AI summaries',
                'indexes': [],
                'constraints': [],
            },
        ),
    ]
