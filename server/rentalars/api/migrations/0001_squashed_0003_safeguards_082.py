# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``api`` from 0001_initial to 0003_safeguards_082 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.db.models.deletion
import django.utils.timezone
import rentalars.api.models
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('api', '0001_initial'), ('api', '0002_webhooks'), ('api', '0003_safeguards_082')]

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotentCall',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(max_length=80)),
                ('key', models.CharField(max_length=100)),
                ('fingerprint', models.CharField(max_length=64)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('status_code', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('content_type', models.CharField(blank=True, max_length=100)),
                ('location', models.CharField(blank=True, max_length=500)),
                ('body', models.BinaryField(blank=True)),
                ('project_access', models.JSONField(blank=True, default=dict)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('scope', 'key'), name='idempotent_call_per_key')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='ApiCallCount',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('minute', models.DateTimeField()),
                ('count', models.PositiveIntegerField(default=0)),
                ('token', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='call_counts', to='accounts.apitoken')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('token', 'minute'), name='api_call_count_per_minute')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='Webhook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('url', models.CharField(help_text='Where the events are sent to, beginning with https:// or http://. Internal addresses only if the operator allows them in the configuration file.', max_length=500, validators=[rentalars.api.models.validate_webhook_url], verbose_name='address')),
                ('description', models.CharField(blank=True, max_length=200, verbose_name='description')),
                ('events', models.JSONField(default=list, verbose_name='events')),
                ('is_active', models.BooleanField(default=True, verbose_name='active')),
                ('secret_encrypted', models.TextField(blank=True, editable=False, verbose_name='secret (encrypted)')),
                ('secret_created_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='secret created')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='created')),
                ('failures_in_a_row', models.PositiveIntegerField(default=0, editable=False, verbose_name='failed deliveries in a row')),
                ('switched_off_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='switched off automatically')),
                ('created_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='created by')),
            ],
            options={
                'verbose_name': 'webhook',
                'verbose_name_plural': 'webhooks',
                'ordering': ['url', 'id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='WebhookDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('uuid', models.UUIDField(default=uuid.uuid4, editable=False, unique=True, verbose_name='delivery ID')),
                ('event', models.CharField(max_length=60, verbose_name='event')),
                ('data', models.JSONField(default=dict, verbose_name='content')),
                ('status', models.CharField(choices=[('pending', 'waiting'), ('delivered', 'delivered'), ('failed', 'failed')], default='pending', max_length=10, verbose_name='status')),
                ('attempts', models.PositiveSmallIntegerField(default=0, verbose_name='attempts')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('next_attempt_at', models.DateTimeField(blank=True, null=True, verbose_name='next attempt')),
                ('last_attempt_at', models.DateTimeField(blank=True, null=True, verbose_name='last attempt')),
                ('last_status_code', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='last answer')),
                ('last_error', models.CharField(blank=True, max_length=300, verbose_name='last error')),
                ('last_response', models.TextField(blank=True, verbose_name='beginning of the last answer')),
                ('last_duration_ms', models.PositiveIntegerField(blank=True, null=True, verbose_name='duration (ms)')),
                ('delivered_at', models.DateTimeField(blank=True, null=True, verbose_name='delivered')),
                ('webhook', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='api.webhook', verbose_name='webhook')),
            ],
            options={
                'verbose_name': 'webhook delivery',
                'verbose_name_plural': 'webhook deliveries',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['status', 'next_attempt_at'], name='webhook_delivery_due_idx'), models.Index(fields=['webhook', '-created_at'], name='webhook_delivery_list_idx'), models.Index(fields=['created_at'], name='webhook_delivery_age_idx')],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='WriteLock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('key', models.CharField(max_length=64, unique=True)),
                ('taken_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={
                'indexes': [],
                'constraints': [],
            },
        ),
    ]
