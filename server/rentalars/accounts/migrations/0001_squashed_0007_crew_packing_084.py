# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``accounts`` from 0001_initial to 0007_crew_packing_084 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.contrib.auth.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.accounts.models
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    replaces = [('accounts', '0001_initial'), ('accounts', '0002_account_expiry_and_time_rights'), ('accounts', '0003_two_factor_sessions_security_log'), ('accounts', '0004_account_email_optional'), ('accounts', '0005_security_event_one_time_password'), ('accounts', '0006_language_083'), ('accounts', '0007_crew_packing_084')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
    ]

    operations = [
        migrations.CreateModel(
            name='User',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('password', models.CharField(max_length=128, verbose_name='password')),
                ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                ('username', models.CharField(max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                ('email', models.EmailField(blank=True, max_length=254, null=True, unique=True, verbose_name='e-mail address')),
                ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                ('is_active', models.BooleanField(default=True, help_text='Deactivated users cannot log in; their data and history are kept.', verbose_name='active')),
                ('is_superuser', models.BooleanField(default=False, help_text='Emergency access that does not depend on roles. Use sparingly.', verbose_name='has all rights')),
                ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
            ],
            options={
                'verbose_name': 'user',
                'verbose_name_plural': 'users',
                'ordering': ['last_name', 'first_name', 'username'],
            },
            managers=[
                ('objects', rentalars.accounts.models.UserManager()),
            ],
        ),
        migrations.CreateModel(
            name='LoginAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('identifier', models.CharField(db_index=True, max_length=254)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('successful', models.BooleanField(default=False)),
            ],
            options={
                'verbose_name': 'login attempt',
                'verbose_name_plural': 'login attempts',
                'ordering': ['-timestamp'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80, unique=True, verbose_name='name')),
                ('description', models.CharField(blank=True, max_length=250, verbose_name='description')),
                ('module_levels', models.JSONField(blank=True, default=dict, verbose_name='module rights')),
                ('special_rights', models.JSONField(blank=True, default=list, verbose_name='special rights')),
                ('project_scope', models.CharField(choices=[('all', 'all projects'), ('assigned', 'assigned projects only')], default='all', help_text='“Assigned projects only”: the rights on projects and packing lists hold only in projects the user is a member of or is scheduled for as crew.', max_length=10, verbose_name='project access')),
                ('requires_two_factor', models.BooleanField(default=False, help_text='Users with this role must set up a second factor before they can work.', verbose_name='two-factor login required')),
            ],
            options={
                'verbose_name': 'role',
                'verbose_name_plural': 'roles',
                'ordering': ['name'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='ApiToken',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='What the token is used for.', max_length=80, verbose_name='name')),
                ('key_prefix', models.CharField(max_length=12, verbose_name='beginning of the key')),
                ('key_hash', models.CharField(max_length=64, unique=True)),
                ('read_only', models.BooleanField(default=False, verbose_name='read-only')),
                ('allowed_modules', models.JSONField(blank=True, default=list, help_text='Empty means: all modules the user may access.', verbose_name='limited to modules')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('expires_at', models.DateTimeField(blank=True, null=True, verbose_name='valid until')),
                ('last_used_at', models.DateTimeField(blank=True, null=True, verbose_name='last used')),
                ('revoked_at', models.DateTimeField(blank=True, null=True, verbose_name='revoked')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='api_tokens', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'API token',
                'verbose_name_plural': 'API tokens',
                'ordering': ['-created_at'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='SecurityEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('login', 'logged in'), ('login_failed', 'login failed'), ('logout', 'logged out'), ('timeout', 'logged out after inactivity'), ('2fa_failed', 'wrong second factor'), ('2fa_enabled', 'two-factor login set up'), ('2fa_disabled', 'two-factor login switched off'), ('recovery_code', 'recovery code used'), ('session_ended', 'session ended'), ('password_changed', 'password changed'), ('one_time_password', 'one-time password set')], max_length=20, verbose_name='event')),
                ('identifier', models.CharField(blank=True, max_length=254, verbose_name='entered name')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP address')),
                ('user_agent', models.CharField(blank=True, max_length=300, verbose_name='browser')),
                ('detail', models.CharField(blank=True, max_length=250, verbose_name='detail')),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='time')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'security event',
                'verbose_name_plural': 'security log',
                'ordering': ['-timestamp', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='UserSession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(max_length=40, unique=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='logged in')),
                ('last_activity', models.DateTimeField(default=django.utils.timezone.now, verbose_name='last active')),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True, verbose_name='IP address')),
                ('user_agent', models.CharField(blank=True, max_length=300, verbose_name='browser')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='browser_sessions', to=settings.AUTH_USER_MODEL, verbose_name='user')),
            ],
            options={
                'verbose_name': 'session',
                'verbose_name_plural': 'sessions',
                'ordering': ['-last_activity'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.AddField(
            model_name='user',
            name='roles',
            field=models.ManyToManyField(blank=True, related_name='users', to='accounts.role', verbose_name='roles'),
        ),
        migrations.AddField(
            model_name='user',
            name='valid_until',
            field=models.DateField(blank=True, help_text='For temporary staff: after this day the account is deactivated automatically. Empty: no limit.', null=True, verbose_name='valid until'),
        ),
        migrations.AddField(
            model_name='user',
            name='recovery_code_hashes',
            field=models.JSONField(blank=True, default=list, editable=False),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_enabled_at',
            field=models.DateTimeField(blank=True, editable=False, null=True, verbose_name='two-factor login since'),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_last_step',
            field=models.BigIntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name='user',
            name='totp_secret_encrypted',
            field=models.TextField(blank=True, editable=False),
        ),
        migrations.AddField(
            model_name='user',
            name='must_change_password',
            field=models.BooleanField(default=False, editable=False, help_text="Set with a one-time password; the next login asks for a password of the user's own.", verbose_name='must choose a new password'),
        ),
        migrations.AddField(
            model_name='user',
            name='language',
            field=models.CharField(blank=True, choices=[('de', 'Deutsch'), ('en', 'English')], db_default='', default='', help_text='The language of the pages, mails and notifications for this user.', max_length=5, verbose_name='language'),
        ),
    ]
