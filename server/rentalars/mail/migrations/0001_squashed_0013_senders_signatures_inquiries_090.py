# SPDX-License-Identifier: GPL-3.0-or-later
"""The migrations of ``mail`` from 0001_initial to 0013_senders_signatures_inquiries_090 in one.

Squashed: a new database is built from here, and a database that has applied
the replaced migrations already (``replaces``) continues from here.
Data steps that only converted older data are gone; the steps
below create what a new database needs before its start data (``core.defaults``).
"""

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
import rentalars.mail.models
from django.conf import settings
from django.db import migrations, models


def create_row(apps, schema_editor):
    """The one row of the mail settings, so that reading a page never has to write it (mail 0002)."""
    MailSettings = apps.get_model("mail", "MailSettings")
    MailSettings.objects.get_or_create(pk=1)



class Migration(migrations.Migration):

    replaces = [('mail', '0001_initial'), ('mail', '0002_mailbox_row'), ('mail', '0003_wishes_051'), ('mail', '0004_mailboxes_062'), ('mail', '0005_crew_answers_063'), ('mail', '0006_subrentals_071'), ('mail', '0007_mailboxes_071'), ('mail', '0008_automations_080'), ('mail', '0009_aliases_081'), ('mail', '0010_cutoff_082'), ('mail', '0011_defects_085'), ('mail', '0012_notes_085'), ('mail', '0013_senders_signatures_inquiries_090')]

    initial = True

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('customers', '0001_squashed_0007_maps_080'),
        ('masterdata', '0001_squashed_0012_fleet_090'),
        ('material', '0001_squashed_0006_vehicles_090'),
        ('personnel', '0001_squashed_0014_licence_classes_090'),
        ('projects', '0001_squashed_0003_internal_projects_and_crew_lines'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='MailSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('sender_name', models.CharField(blank=True, help_text='Only for mails without a known writer; otherwise the sender is “name | company”.', max_length=120, verbose_name='sender name')),
                ('interval_minutes', models.PositiveSmallIntegerField(default=2, validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(60)], verbose_name='fetch every … minutes')),
                ('max_message_mb', models.PositiveSmallIntegerField(default=25, help_text='Attachments of larger mails are left in the mailbox.', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(200)], verbose_name='largest mail (MB)')),
                ('retention_days', models.PositiveIntegerField(default=0, help_text='0: keep. Otherwise older mails are deleted from Rentalars every night.', verbose_name='keep mails for … days')),
                ('signature_html', models.TextField(blank=True, verbose_name='signature')),
                ('crew_answers', models.CharField(choices=[('link', 'by the link in the browser'), ('mail', 'by reply mail'), ('both', 'both')], default='both', help_text='By reply mail, the request carries the buttons “Accept” and “Decline”. They open a prepared mail to a mailbox that Rentalars fetches – the answer needs no access to Rentalars. Choose it when the server cannot be reached from the internet: then the link in the request leads nowhere outside. Without a mailbox that is fetched, the request carries only the link.', max_length=8, verbose_name='answer to deployment requests')),
            ],
            options={
                'verbose_name': 'mail settings',
                'verbose_name_plural': 'mail settings',
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='UnknownTagMail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message_key', models.CharField(max_length=64, unique=True)),
                ('message_id', models.TextField(blank=True)),
                ('uid', models.BigIntegerField(default=0)),
                ('subject', models.CharField(blank=True, max_length=500, verbose_name='subject')),
                ('sender', models.CharField(blank=True, max_length=300, verbose_name='sender')),
                ('date', models.DateTimeField(blank=True, null=True, verbose_name='date')),
                ('tag', models.CharField(blank=True, max_length=120, verbose_name='tag')),
                ('first_seen_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='found')),
                ('resolved_at', models.DateTimeField(blank=True, null=True, verbose_name='dealt with')),
            ],
            options={
                'verbose_name': 'inquiry or mail with unknown tag',
                'verbose_name_plural': 'inquiries and mails with unknown tag',
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='ProjectMail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('direction', models.CharField(choices=[('in', 'received'), ('out', 'sent'), ('note', 'note')], default='in', max_length=4, verbose_name='direction')),
                ('kind', models.CharField(blank=True, choices=[('', 'mail'), ('auto_reply', 'automatic reply'), ('bounce', 'delivery failure')], default='', max_length=12, verbose_name='kind')),
                ('message_key', models.CharField(editable=False, max_length=64, unique=True)),
                ('message_id', models.TextField(editable=False, verbose_name='Message-ID')),
                ('in_reply_to', models.TextField(blank=True, editable=False)),
                ('references', models.TextField(blank=True, editable=False)),
                ('subject', models.CharField(blank=True, max_length=500, verbose_name='subject')),
                ('sender_name', models.CharField(blank=True, max_length=200, verbose_name='sender')),
                ('sender_address', models.CharField(blank=True, max_length=254, verbose_name='sender address')),
                ('to_addresses', models.TextField(blank=True, verbose_name='to')),
                ('cc_addresses', models.TextField(blank=True, verbose_name='copy to')),
                ('date', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date')),
                ('text_body', models.TextField(blank=True, verbose_name='text')),
                ('html_body', models.TextField(blank=True, verbose_name='text as HTML')),
                ('assigned_by', models.CharField(choices=[('tag', 'by the tag in the subject'), ('reference', 'as a reply to an assigned mail'), ('manual', 'by hand'), ('sent', 'sent from the project'), ('note', 'written as a note'), ('new_case', 'as a new service case')], default='tag', max_length=10, verbose_name='assigned')),
                ('imported_at', models.DateTimeField(default=django.utils.timezone.now, editable=False, verbose_name='taken over')),
                ('project_was_finished', models.BooleanField(default=False, editable=False, help_text='The project was finished or cancelled when the mail arrived.', verbose_name='arrived for a finished project')),
                ('attachments_note', models.TextField(blank=True, verbose_name='attachments left out')),
                ('size', models.PositiveIntegerField(default=0, verbose_name='size')),
                ('project', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='mails', to='projects.project', verbose_name='project')),
                ('sent_by', models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='sent by')),
                ('bcc_addresses', models.TextField(blank=True, verbose_name='blind copy to')),
            ],
            options={
                'verbose_name': 'project mail',
                'verbose_name_plural': 'project mails',
                'ordering': ['-date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='MailAttachment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('file', models.FileField(max_length=200, upload_to=rentalars.mail.models.attachment_path, verbose_name='file')),
                ('filename', models.CharField(max_length=255, verbose_name='file name')),
                ('content_type', models.CharField(blank=True, max_length=120, verbose_name='type')),
                ('size', models.PositiveBigIntegerField(default=0, verbose_name='size')),
                ('content_id', models.CharField(blank=True, help_text='For pictures shown inside the text.', max_length=255)),
                ('is_inline', models.BooleanField(default=False)),
                ('mail', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='mail.projectmail', verbose_name='mail')),
            ],
            options={
                'verbose_name': 'attachment',
                'verbose_name_plural': 'attachments',
                'ordering': ['id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='MailLogEntry',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('timestamp', models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name='time')),
                ('direction', models.CharField(choices=[('in', 'received'), ('out', 'sent')], max_length=3, verbose_name='direction')),
                ('kind', models.CharField(choices=[('project', 'project mail'), ('system', 'system mail'), ('automatic', 'automatic answer')], max_length=10, verbose_name='kind')),
                ('result', models.CharField(choices=[('assigned', 'assigned'), ('unknown_tag', 'unknown tag'), ('inquiry', 'inquiry'), ('left', 'left in the inbox'), ('sent', 'sent'), ('failed', 'failed'), ('not_sent', 'not sent – no mail server set up'), ('crew_answer', 'answer to a deployment request')], max_length=12, verbose_name='result')),
                ('sender', models.CharField(blank=True, max_length=300, verbose_name='sender')),
                ('recipients', models.TextField(blank=True, verbose_name='recipients')),
                ('subject', models.CharField(blank=True, max_length=500, verbose_name='subject')),
                ('message_key', models.CharField(blank=True, db_index=True, max_length=64)),
                ('detail', models.TextField(blank=True, help_text='The error, or a note such as the unknown tag.', verbose_name='detail')),
                ('mail', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='mail.projectmail', verbose_name='mail')),
                ('project', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='projects.project', verbose_name='project')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='sent by')),
            ],
            options={
                'verbose_name': 'mail log entry',
                'verbose_name_plural': 'mail log',
                'ordering': ['-timestamp', '-id'],
            },
        ),
        migrations.CreateModel(
            name='Mailbox',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Shown in the list, in the mail log and with the inquiries.', max_length=120, verbose_name='name')),
                ('address', models.EmailField(blank=True, help_text='The sender of mails sent through this mailbox.', max_length=254, verbose_name='address of the mailbox')),
                ('is_active', models.BooleanField(default=True, help_text='Switched off, the mailbox is neither fetched nor used for sending.', verbose_name='active')),
                ('for_correspondence', models.BooleanField(default=False, help_text='New mails are fetched and assigned to their project by the tag in the subject.', verbose_name='correspondence')),
                ('is_outgoing', models.BooleanField(default=False, help_text='Mails written in a project go out through this mailbox, with its address as sender.', verbose_name='sends the correspondence')),
                ('for_system', models.BooleanField(default=False, help_text='Invitations, password links and notifications go out through this mailbox. Without such a mailbox they go through the configuration of the server.', verbose_name='system mails')),
                ('imap_host', models.CharField(blank=True, max_length=200, verbose_name='IMAP server')),
                ('imap_port', models.PositiveIntegerField(default=993, validators=[django.core.validators.MaxValueValidator(65535)], verbose_name='IMAP port')),
                ('imap_security', models.CharField(choices=[('ssl', 'SSL/TLS (port 993 or 465)'), ('starttls', 'STARTTLS (port 143 or 587)')], default='ssl', max_length=10, verbose_name='IMAP encryption')),
                ('imap_user', models.CharField(blank=True, max_length=200, verbose_name='IMAP user')),
                ('imap_password_encrypted', models.TextField(blank=True, editable=False, verbose_name='IMAP password')),
                ('smtp_host', models.CharField(blank=True, max_length=200, verbose_name='SMTP server')),
                ('smtp_port', models.PositiveIntegerField(default=587, validators=[django.core.validators.MaxValueValidator(65535)], verbose_name='SMTP port')),
                ('smtp_security', models.CharField(choices=[('ssl', 'SSL/TLS (port 993 or 465)'), ('starttls', 'STARTTLS (port 143 or 587)')], default='starttls', max_length=10, verbose_name='SMTP encryption')),
                ('smtp_same_login', models.BooleanField(default=True, help_text='Usual with most providers. Switch it off if sending needs access data of its own.', verbose_name='same user and password as for receiving (IMAP)')),
                ('smtp_user', models.CharField(blank=True, help_text='Empty: send without logging in.', max_length=200, verbose_name='SMTP user')),
                ('smtp_password_encrypted', models.TextField(blank=True, editable=False, verbose_name='SMTP password')),
                ('inbox_folder', models.CharField(default='INBOX', max_length=120, verbose_name='inbox folder')),
                ('process_untagged', models.BooleanField(default=False, help_text='They appear as inquiries under Projects and can be taken over into a project. Switched off, they stay in the inbox untouched. Holds for the address of the mailbox and every address not listed under “Further addresses”.', verbose_name='take in mails without project tag')),
                ('after_assignment', models.CharField(choices=[('move', 'mark as read and move into a folder'), ('read', 'only mark as read'), ('delete', 'delete'), ('keep', 'leave unchanged in the inbox')], default='move', help_text='Delete only when Rentalars is the only place where the mails are kept.', max_length=10, verbose_name='assigned mails in the mailbox')),
                ('done_folder', models.CharField(blank=True, default='Rentalars', help_text='Created if it does not exist.', max_length=120, verbose_name='folder for assigned mails')),
                ('last_fetch_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='last fetch')),
                ('last_success_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='last successful fetch')),
                ('last_error', models.TextField(blank=True, editable=False, verbose_name='last error')),
                ('last_error_at', models.DateTimeField(blank=True, editable=False, null=True, verbose_name='last error at')),
                ('error_reported', models.BooleanField(default=False, editable=False)),
                ('uid_validity', models.BigIntegerField(default=0, editable=False)),
                ('last_uid', models.BigIntegerField(default=0, editable=False)),
                ('untagged_since', models.DateTimeField(blank=True, help_text='Only mails that arrived in the mailbox from this moment on are taken in; older ones stay in the inbox untouched. Set to the moment of switching on; empty means now.', null=True, verbose_name='taken in from')),
                ('untagged_unread_only', models.BooleanField(default=False, help_text='Mails already read in the mailbox stay in the inbox untouched.', verbose_name='only unread mails')),
                ('sender_roles', models.ManyToManyField(blank=True, help_text='Members of these roles may choose the address of this mailbox as sender of a mail written in a project. The mailbox that sends the correspondence is open to everybody who may write correspondence; superusers may use every address.', related_name='+', to='accounts.role', verbose_name='may send from this address')),
                ('signature_html', models.TextField(blank=True, verbose_name='signature of the mailbox')),
            ],
            options={
                'verbose_name': 'mailbox',
                'verbose_name_plural': 'mailboxes',
                'ordering': ['name', 'id'],
                'constraints': [models.CheckConstraint(condition=models.Q(('is_outgoing', False), ('for_correspondence', True), _connector='OR'), name='mail_outgoing_is_correspondence')],
                'indexes': [],
            },
        ),
        migrations.CreateModel(
            name='CrewRequestMail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(editable=False, max_length=32, unique=True)),
                ('requested_at', models.DateTimeField(verbose_name='asked at')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now, verbose_name='created')),
                ('answered_at', models.DateTimeField(blank=True, null=True, verbose_name='answered at')),
                ('line', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='projects.crewline', verbose_name='crew line')),
                ('person', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='personnel.person', verbose_name='person')),
            ],
            options={
                'verbose_name': 'deployment request by mail',
                'verbose_name_plural': 'deployment requests by mail',
                'ordering': ['-created_at', '-id'],
                'indexes': [],
                'constraints': [],
            },
        ),
        migrations.CreateModel(
            name='MailboxAddress',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('address', models.EmailField(max_length=254, verbose_name='address')),
                ('untagged', models.CharField(choices=[('ignore', 'do not take in'), ('inquiry', 'as an inquiry'), ('service_case', 'create a service case at once')], default='inquiry', help_text='Mails with a project tag and replies to assigned mails go to their project in any case.', max_length=12, verbose_name='mails without project tag')),
                ('for_service_cases', models.BooleanField(default=False, help_text='Mails written in a service case go out with this address as sender. Only one address can have this role.', verbose_name='only for service cases')),
                ('case_manager', models.ForeignKey(blank=True, help_text='Gets the service cases made from mails to this address, and a notification.', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='responsible for new service cases')),
                ('mailbox', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='aliases', to='mail.mailbox', verbose_name='mailbox')),
                ('untagged_since', models.DateTimeField(blank=True, help_text='Only mails that arrived in the mailbox from this moment on are taken in; older ones stay in the inbox untouched. Set to the moment of switching on; empty means now.', null=True, verbose_name='taken in from')),
                ('untagged_unread_only', models.BooleanField(default=False, help_text='Mails already read in the mailbox stay in the inbox untouched.', verbose_name='only unread mails')),
                ('sender_roles', models.ManyToManyField(blank=True, help_text='Members of these roles may choose this address as sender of a mail written in a project. Superusers may use every address.', related_name='+', to='accounts.role', verbose_name='may send from this address')),
            ],
            options={
                'verbose_name': 'address of a mailbox',
                'verbose_name_plural': 'addresses of mailboxes',
                'ordering': ['address', 'id'],
                'constraints': [models.UniqueConstraint(fields=('mailbox', 'address'), name='mail_alias_unique_address')],
                'indexes': [],
            },
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='mailbox',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='waiting_mails', to='mail.mailbox', verbose_name='mailbox'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='address',
            field=models.CharField(blank=True, max_length=254, verbose_name='to address'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='defect_report',
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='inquiry', to='material.defectreport', verbose_name='defect report'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='contact_email',
            field=models.EmailField(blank=True, max_length=254, verbose_name='e-mail address'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='contact_name',
            field=models.CharField(blank=True, max_length=200, verbose_name='who'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL, verbose_name='noted by'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='customers.customer', verbose_name='customer'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='note',
            field=models.TextField(blank=True, verbose_name='note'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='phone',
            field=models.CharField(blank=True, max_length=60, verbose_name='phone'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='source',
            field=models.CharField(blank=True, choices=[('', 'taken in by Rentalars'), ('manual', 'noted by hand')], default='', max_length=10, verbose_name='source'),
        ),
        migrations.AddField(
            model_name='unknowntagmail',
            name='version',
            field=models.PositiveIntegerField(default=0, editable=False),
        ),
        migrations.AddField(
            model_name='projectmail',
            name='mailbox',
            field=models.ForeignKey(blank=True, editable=False, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mails', to='mail.mailbox', verbose_name='mailbox'),
        ),
        migrations.AddField(
            model_name='projectmail',
            name='supplier',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mails', to='masterdata.supplier', verbose_name='supplier'),
        ),
        migrations.AddField(
            model_name='projectmail',
            name='mailbox_name',
            field=models.CharField(blank=True, editable=False, max_length=120, verbose_name='name of the mailbox'),
        ),
        migrations.AddIndex(
            model_name='projectmail',
            index=models.Index(fields=['project', 'date'], name='mail_project_date_idx'),
        ),
        migrations.AddField(
            model_name='maillogentry',
            name='mailbox',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='log_entries', to='mail.mailbox', verbose_name='mailbox'),
        ),
        migrations.AddField(
            model_name='maillogentry',
            name='mailbox_name',
            field=models.CharField(blank=True, max_length=120, verbose_name='name of the mailbox'),
        ),
        migrations.RunPython(create_row, migrations.RunPython.noop),
    ]
