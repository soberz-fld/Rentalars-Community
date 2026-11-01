# Architecture

Rentalars is one Django application. It is served by gunicorn behind NGINX
and stores everything in one MariaDB database. There is no second service:
no job queue, no cache server, no search server. A small business installs
it on one machine and has nothing else to look after (NFA-028).

Work that takes longer than a request – a large import, many labels, the
full export – runs as a *task in the background*: Django stores it as a row
and starts `manage.py run_jobs --job N` as a process of its own
(`core/jobs.py`, NFA-041). What could not be started, or was interrupted
by a restart, is picked up by a systemd timer of its own,
`rentalars-jobs.timer`, every minute. Timers, not services, also run the
mail fetch, the daily maintenance and the backup. The minute
timer of the tasks also reads the calendars people linked and writes their
deployments into their CalDAV calendars (`personnel/calendars.py`,
PER-022, PER-023), it sends what webhooks have to tell
other systems (`api/webhooks.py`, API-012), it tells
people whose follow-up of a project is due (`projects/follow_up.py`,
PRJ-105), and it carries out the runs of automations that are
still waiting (`automations/engine.py`, ADM-013) – normally they run right
after the change that started them is committed. Handing an invoice to Lexware
Office is a task in the background of its own kind (`documents/lexware.py`,
DOK-011).
The minute timer also starts the **night's automatic AI
summaries** (`ai/auto.py`, command `ai_summaries`, a task of its own kind,
`ai_auto_summaries`, inside the window set in Einstellungen → KI), and the
daily maintenance compares the accounts with the company directory when
that is switched on (`accounts/ldap_sync.sync_nightly`, AUT-029). Reading an
incoming invoice (`ai_incoming_invoice`) and the old invoices of an
import (`legacy_invoices`) are tasks in the background as well.

```
 Browser ──HTTPS──▶ NGINX ──socket──▶ gunicorn ──▶ Django (rentalars) ──▶ MariaDB
 API client ─────▶   │                                   │
 calendar app ───▶   │  /calendar-feed/…   a secret token instead of a login (PER-023;
                     │                     also products, models, items, VFG-040)
 Android app ────▶   │  /api/v1/…          packlists without network, sync (PCK-026)
                     ├─ /static/        files of the package (CSS, scripts, fonts)
                     └─ /protected-media/  uploaded files, only after Django said yes

 Django ──starts──▶ manage.py run_jobs --job N        a task in the background
 systemd timers ──▶ manage.py fetch_mail              every minute (rentalars-mail.timer),
                                                      each correspondence mailbox when due
                    manage.py run_jobs                every minute (rentalars-jobs.timer),
                                                      also the calendars of the people,
                                                      the webhook deliveries, the
                                                      follow-ups that are due and the
                                                      waiting runs of automations
                    manage.py run_daily_maintenance   every night
                    deploy/backup.sh                  every night

 Django ──HTTP(S)──▶ webhook receivers (API-012), api.lexware.io (DOK-011),
                     calendar servers (PER-022, PER-023),
                     the geocoder, Nominatim (UIX-034, after "Karte anzeigen"),
                     AI interfaces typed in the settings (ADM-017, off at first)   going out
 Django ──HTTP─────▶ 127.0.0.1:8093 llama-server, service rentalars-ai
                     (EML-040, only if the operator installed it)
 operator via SSH ─▶ sudo rentalars address apply / ai install   root, never Django
                     (ADM-016, EML-040; "Commands that need root", below)
 Django ──IMAP/SMTP─▶ the mailboxes of the settings (EML-041)     going out
 Browser ──HTTPS───▶ the tile server of the map (UIX-034, after the click),
                     Google Maps (UIX-033, only by following a route link)
```

This page explains how the code is cut and why. For the tables see
[data-model.md](data-model.md); for what happens inside the most important
calculations see [core-flows.md](core-flows.md).

## The modules

Each business area is a package below `rentalars/` (NFA-021). Rights,
navigation and API follow the same cut: a role grants access per module, the
navigation shows one entry per module, the API has one group of addresses per
module.

| Package | Answers the question | Catalogue |
|---|---|---|
| `core` | Who changed what? Who looked at what? Which number comes next? Who are we? And the shared machinery: lists with chosen columns and filters that fold away, imports, tasks in the background, the full export, the backup from the browser, readable addresses (also with a former project number), pages that follow changes; route links and maps at addresses with the positions found once, the holidays per federal state and the settings of the surcharges, the list of show-file endings; the surcharge rules and own holidays (`surcharges.py`, `surcharge_presets.py`), grouping in every table, the pages that never show "Zurück"; the guard for every address the server calls on a user's behalf (`network.py`), sorting every column (`tables.py`), shared helpers of tabular data (`tabular.fold`), form errors on any form (`forms.add_validation_error`); German and English (`i18n.py`, `formats/`, `templatetags/local_dates.py`, `start_data.py`), the manual page (`manual.py`), the server address and certificate (`server_address.py`, `address_models.py`, `address_views.py`, `address_api.py`, `management/commands/address_change.py`), grouping by every shown column (`tables.py`); the notification settings of the company (`notification_settings.py`) and the minute timer checking shortages (`management/commands/run_jobs.py`); the rows of an import preview (`import_rows.py`) and the optional route service (`routing.py`); the settings of the reminders of times to approve (`notification_settings.py`, `approval_*`), the minute timer calling them (`run_jobs`) and the daily maintenance removing unsaved purchase invoices (`run_daily_maintenance`); the check of the database that refuses one older than 0.9.0 before `migrate` (`checks.py`), the export in the format of each import (`import_exports.py`, `import_views.import_format_export`, `import_api.ImportExportView`), entries per page per user and list (`listing.page_size_choice`, `TableState.paginate`, `PageSizeMiddleware`), columns a table gets from the database (`TableDefinition.add_column_source`), plain text of stored HTML in tables (`tables.plain_text`), the readable export as a part of the backup page (`settings_views.full_export`) and the self-check of ffmpeg and of the NGINX upload limit for videos (`selfcheck.py`), a gate per kind of background task (`jobs.register(…, gate=)`, one chat video at a time) and the daily maintenance removing chat videos left waiting (`run_daily_maintenance`); the template filter `css_string` for the page margins of PDFs, the help texts at the ID Django's `aria-describedby` names (`_field.html`) and the tokens of calendar links among the secret fields of the full export; the manual in chapters (`manual.py`), the change key `stock:<pk>` (`changes.py`) and the header `Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=()` (`middleware.py`) | ADM, UIX, IMP-001 ff., NFA-041, AUT-028, UIX-033, UIX-034, PER-009, PER-040, UIX-040, UIX-041, NFA-071 to NFA-073, UIX-015, EML-024, UIX-029, ADM-016, UIX-044, VFG-036, IMP-011, LOG-017, ZEI-029, IMP-006, IMP-017, UIX-005, UIX-050, UIX-051, NFA-076, NFA-077, UIX-057, UIX-056, UIX-006 |
| `accounts` | Who may log in, and what may they do? Every account is a person (AUT-026); one-time passwords; the notice when e-mail address or password change (`notices.py`); the project scope "overview without planning" (`ProjectScope.DEPLOYMENT`, `Rights.level_of_planning`, `reads_planning`), the special right "availability", the right to work on one's service cases (`Rights.case_work`) and the data-access columns of the people and users (`data_access.py`); the login with a company directory (LDAP / Active Directory): `ldap_client.py` (all that touches `ldap3`), `ldap_sync.py` (one rule set for the login, the dry run and the nightly comparison), `ldap_backend.py` (the second authentication backend), `ldap_views.py`, `ldap_forms.py`, `ldap_api.py`, the command `ldap_sync`; the models `LdapSettings`, `LdapGroupMapping`, `LdapRoleAssignment` | AUT, AUT-031 to AUT-034, AUT-029 |
| `masterdata` | Categories, units, tax rates, manufacturers, suppliers (with e-mail and phone, with an address), storage locations (with a default), rental scales, document types ("Showfile") | MAT-007 ff., PRD-015 |
| `material` | What do we own? Models and items, what is installed in what, inspections, blocked periods, defects, files, labels, the material import; new items with start ID and serial numbers, a product from a model; the fleet – vehicle data of an item, the tab "Fuhrpark", its utilization, taking a model into the fleet (`fleet.py`, `fleet_views.py`, `fleet_tables.py`, `vehicle_api.py`); entering a purchase with its invoice (`purchases.py`, `purchase_forms.py`, `purchase_views.py`, `purchase_api.py`), gross purchase prices (`forms.PriceEntryMixin`), a new supplier in a dialog (`views.supplier_create`), the item ID field (`views.item_jump`), duplicating models and items, and the labels laid out inside the printable area with the bundled font (`label_layouts.py`, `labels.py`, `label_views.item_labels`); audits and to-dos with their settings, the audit mode and the tab "Offene Punkte" (`audit_models.py`, `audits.py`, `audit_views.py`, `audit_tables.py`, `audit_api.py`), the material list in the format of its import (`import_export.py`) and storage locations by path in the import (`importer._Writer.storage_location`); the protection class and the electrical inspection with its limits, live check and test report (`dguv.py`, `inspection_report.py`, `item_views.inspection_check`), the sums and the amounts of "Kauf einpflegen" (`purchase_forms.purchase_sums`, `purchases.parse_amount`), the master data in the audit mode (`audits.master_data`), the open points total (`templatetags/material_tags.py`) and the fleet only for vehicle categories (`fleet.is_vehicle_category`); assets and their book value (`asset_models.py`, `assets.py`, `depreciation.py`, `book_values.py`, `asset_forms.py`, `asset_tables.py`, `asset_views.py`, `asset_api.py`), the used sale from stock (`sale_models.py`, `sales.py`), quantity material built into an item (`installed_models.py`, `installations.py`, `installed_views.py`, `installed_api.py`), dates known to the year or month only (`partial_dates.py`) and the scan resolver (`scan.py`, `scan_views.py`, `scan_api.py`, `static/js/scan.js`) | MAT, IMP, LOG-002 to LOG-004, LOG-013 to LOG-016, LOG-018, MAT-059 to MAT-066, MAT-067 to MAT-070, IMP-017, MAT-074 to MAT-079, LOG-020, MAT-027, MAT-040, MAT-086 to MAT-088 |
| `customfields` | Which details does each single item have of its own? Custom fields, fieldsets, the fieldset of a material model and the values per item (`models.py`), their forms and pages under Einstellungen (`forms.py`, `views.py`, `tables.py`), storing, checking and showing values (`services.py`), search and filters (`filters.py`), the history lines (`history.py`), the columns of the material import (`importing.py`) and the API (`api.py`); the check of patterns against catastrophic backtracking (`patterns.py`) | MAT-071 to MAT-073 |
| `products` | What do we plan and sell? Products, kits, prices, minimum stock; customer material with its owner; services one-to-one with their job function, Nebenkosten, hour tiers; the kind "vehicle" with rates per km and day; one price per product (`Product._check_prices`), duplicating a product (`services.duplicate_values`, `save_duplicate`), the article number following the category of an existing product and the availability on the product page that follows the period, with its link to the utilization; the products in the format of their import (`import_export.py`); accessories and replacements (`relation_models.py`, `relation_views.py`, `suggestions.py`, `suggestion_views.py`, `suggestions_api.py`) | PRD, LOG-005, PRD-047 to PRD-051, IMP-017, PRD-023, VFG-015, PRD-046 |
| `customers` | Whom do we work for, and where? Customers, their addresses, contacts, venues; the customers in the format of their import (`import_export.py`) | KND, IMP-017 |
| `personnel` | Who works for us, as what, at which rate, with which qualifications, and when are they free? The own availability calendar, linked calendars, deployments in the calendar; the job functions of the start data and rates from the limit; the distance to work and marking time ranges in the week; one's own data, absences and deployments over the API without a module right (`own_api.py`) and the change times of the contact fields; the availability of all people, also those without a job function (`availability.py`); "available" entered for an accepted deployment (`marks.mark_available_for_deployment`) and the people in the format of their import (`import_export.py`); price offers of freelancers (`offer_models.py`, `offers.py`, `offer_forms.py`, `offer_views.py`, `offer_api.py`, the template tag `price_offers`) | PER, VFG-009 f., PER-039, ZEI-027, API-015, VFG-038, PER-042, IMP-017, PER-038 |
| `projects` | What is planned for whom, when, at what price – material and crew? Who may see which project? Templates, lighting plots; whole projects with subprojects, material taken over between them, nested groups; customer material in a project, numbers of today and former ones; requests after new times; phases beyond the rental period; hour tiers per day, subrentals per supplier, follow-ups; dividing a project afterwards, service cases, show files, the trips of a project, surcharges for night, Sunday and holidays; people taking part in a service case, a project from an inquiry, the time of a follow-up; trips changed by hand (`trip_changes.py` services, `trip_forms.py`, `trip_views.py`), the own deployments as a table (`my_deployments.py`), changing the crew of a phase from Zeitplanung, the customer required on a service case; when each field last changed and "the younger change wins" for the companion app (`field_changes.py`); the logistics – vehicle bookings, vehicles on trips, drivers, their prices and warnings (`logistics.py`, `logistics_forms.py`, `logistics_views.py`, `logistics_api.py`), and the revenue of a material model (`profitability.py`); several crew lines at once (`crew_bulk.py`, `crew_bulk_forms.py`, `crew_api.py`), planning firmly and telling the person of changes of their deployment (`crew_changes.py`), working on a service case as the person responsible or taking part (`case_work.py`) and the first guess of a new phase (`course.first_guess`); related projects and service cases (`relations.py`, `relation_views.py`, `relation_api.py`, `templatetags/project_relations.py`), staffing a phase by job function and places (`staffing.py`, `staffing_forms.py`, `staffing_views.py`, `staffing_api.py`), the tab "Wer Zugriff hat" (`access_rows.py`, `access.access_of_users`) and "available" for an accepted line (`crew.mark_available_for`); the import of old projects from their invoices (`legacy_models.py`, `legacy_import.py`, `legacy_draft.py`, `legacy_text.py`, `legacy_quiet.py`, `legacy_views.py`, `legacy_api.py`), the overall discount by a target amount (`overall_target.py`), the stock stamp that lets an open planning follow the stock (`stock_watch.py`) and several wished items per line | PRJ, AUT-016 ff., ADM-012, ADM-014, PER-033 to PER-036, PRD-044, PER-009, PRJ-107 to PRJ-111, UIX-043, PRJ-113, PRJ-114, LOG-001, LOG-005 to LOG-012, LOG-019, MAT-058, PRJ-116 to PRJ-118, PER-041, AUT-033, AUT-035, PRJ-119, PRJ-120, PER-042, PRJ-130, PRJ-123, UIX-056, PRJ-064 |
| `timetracking` | Who worked how long on what, and was it approved? Hints at conspicuous times, expenses with receipts; a period divided into job functions, times on any open service case, the pay and the clipboard text in Meine Zeiten (`display.py`), the way to work deducted from trips; a flat rate once per deployment in Meine Zeiten; the reminders of times waiting for approval (`reminders.py`), correcting and approving in one step (`services.correct_and_approve`) and telling the person of approval, correction and sending back | ZEI, ZEI-028, ZEI-029 to ZEI-031 |
| `availability` | What is free when? What is missing? | VFG |
| `packing` | What goes on which truck, what came back? Several packlists per project, contents taken out; the packlist of a whole project, handovers between subprojects; partial return per piece and the packlists of the Android app (offline list, sync); versions and change IDs in the sync, the main packlist on confirmation; who may add material while packing (`services.may_add_material`) and the reason codes of the sync; packing and taking back by scanning labels (`scan.py`) | PCK, MAT-037, MAT-042, PRJ-048, PRJ-060, PCK-010, PCK-011, PCK-016, PCK-022 |
| `documents` | What do we send the customer and the crew? Offer, order confirmation, delivery note, invoice with XRechnung, crew disposition – stored for good; invoices to Lexware Office and as DATEV export; invoices can be switched off; the menu entry "Buchhaltung" with the outgoing documents (`outgoing.py`, `outgoing_tables.py`, `outgoing_views.py`, `outgoing_api.py`) and the monthly statement moved there; the tables of the price-overview PDF by hierarchy, and historic invoices (`Document.is_historic`) which DATEV leaves out unless asked | DOK, DOK-019, DOK-020, DOK-025, PRJ-130 |
| `incoming` | Which invoices did suppliers send us, and what did they cost per piece? The register with upload, reading and correction (`models.py`, `services.py`, `reading.py`, `views.py`, `forms.py`, `tables.py`, `filters.py`, `api.py`), the spreading of ancillary costs over the goods (`costing.py`) and the booking in as items or quantities of bulk material (`booking.py`, which calls `material.purchases.create_purchase`) | DOK-023, DOK-024 |
| `mail` | Which mails belong to which project? The mailboxes and their roles, fetching, inquiries, sending, showing, the signature, the mail log; answers to deployment requests by reply mail; the footer of every system mail; deleting any mailbox, mails of a supplier of subrentals; recognising automatic mails; further addresses of a mailbox (`aliases.py`), telling that no mail server is set up (`server.py`), inquiries turned into projects (`inquiries.py`); untagged mails only from a point in time, optionally only unread (`aliases.untagged_skip`); the senders a user may choose (`senders.py`), a signature per mailbox (`signature.py`) and inquiries noted by hand (`inquiries.py`); messages with a lock and who reads what (`locks.py`, `templatetags/mail_locks.py`), the subjects of mails and notes in the project history only for their readers (`history.py`) | EML, PER-032, PRJ-106, PRJ-107, EML-049, EML-052, EML-026, EML-053, EML-055 |
| `schedule` | What happens when, across all projects? Calendar (week, month), timeline, material utilization ("Materialauslastung"), personnel plan; the timeline of one product, item or person; the timeline of one project on its tab "Zeitplanung"; moving appointments by dragging; dragging deployments in the personnel plan and every follow-up as a table (`follow_ups.py`); the crew of the project timeline like the personnel plan (`course_timeline.py`); kits in the material utilization and a move that tells each planned person once (`moves.apply_move`); people dragged on the project timeline with what follows them (`moves.followers_of`, `Followers`, `course_timeline.py`) and phases and follow-ups in the calendar (`views.calendar_options`, `calendars.py`); its first table, the calendar links of products, models and items with their feed without login (`models.py`, `calendar_links.py`, `calendar_link_views.py`, `calendar_link_api.py`, `templatetags/calendar_links.py`) and the events of an item shared by its timeline and its calendar (`timelines.item_events`) | PRJ-028, PRJ-067, VFG-012 ff., VFG-019, PER-020, PRJ-103, VFG-026, VFG-031 to VFG-035, VFG-037, PRJ-118, PRJ-121, VFG-039, VFG-040 |
| `chat` | What does the team of a project say to each other? The chat of a project, mentions, unread messages; photos and videos, made smaller on the server (`media.py`, background job `chat_video`, one at a time behind the gate `conversion_slot`) | UIX-010, UIX-049, NFA-076 |
| `automations` | What should happen by itself? Rules "Wenn … dann …", their runs, answers that cannot loop; the rules that come with Rentalars by a fixed key, "changed" and restoring the missing ones (`defaults.py`) | ADM-013, ADM-019 |
| `ai` | What does the correspondence say, in short? The short overview without AI (`overview.py`), the summary by a language model as a background job (`summary.py`, `correspondence.py`), the reply draft (`drafts.py`), the local AI the operator installed (`local.py`), the OpenAI-compatible client (`client.py`), settings, interfaces and the call log; streaming with a silence limit (`client.py`), the processor (`cpu.py`) and the measured speed with estimate and recommendation (`speed.py`); reading an uploaded invoice for "Kauf einpflegen" (`invoices.py`, background job `ai_invoice`); summary and reply draft only for who reads every message of the correspondence (`mail.locks`); the invoice read with serial numbers, a category and a product from the lists in the prompt (`invoices.catalogue`) and amounts as printed, read by `material.purchases`; the nightly summaries (`auto.py`), the filters in both directions (`privacy.py`), reading incoming invoices and old invoices (`invoices.register_proposal`, `legacy_invoices.py`) and https only for providers on the internet | EML-040, EML-044, ADM-017, MAT-062, EML-055, MAT-076, EML-056, NFA-079, DOK-023, PRJ-130 |
| `notifications` | Who should know about what? The bell, the mails it sends, preferences; the categories of the kinds (`categories.py`) and the choice "In der App"; when shortages are checked (`schedule.py`) and the page Einstellungen → Benachrichtigungen; the kinds `deployment_change`, `times_to_approve` and `time_decision`, the box "Zeiten zur Freigabe" and `ApprovalNotice`; shortages only to those with the special right "availability"; the text of a notification as plain text in the list – tags removed, entities turned back, `<…>` that is no tag kept (`list_tables.py`, `core.tables.plain_text`); every kind switchable unless listed in `models.ALWAYS_SENT` (empty), the longer names in the settings (`SETTING_LABELS`) and known shortages as one reminder per project (`services._remind_of_shortages`); the kinds `price_offer` and `price_offer_answer` | UIX-005, UIX-039, VFG-036, PRJ-118, ZEI-029, ZEI-031, UIX-052, PER-038 |
| `api` | The shared plumbing of the HTTP API, and its protection against too many, repeated and overwriting calls (bound to the caller and race-free, `WriteLock`); webhooks that tell other systems what happened | API |

The **tables** depend on each other in one direction only. A table refers
to tables further to the right, never the other way round:

```
ai ──────────▶ mail ───┐
automations ──▶ mail ──┤
chat ──────────────────┤
timetracking ──────────┤
notifications ─────────┼─▶ projects ──▶ customers
documents ─────────────┘   ▲   │  │
packing ───────────────────┘   │  └──▶ personnel ──┐
   │                           ▼                   ▼
material ──────────────────▶ products ──▶ masterdata ──▶ accounts ──▶ core
                                                            ▲
                                              api ──────────┘
```

`customfields` lies on top of `material`: its tables point to
`MaterialModel` and `MaterialItem`, never the other way round. Material
reaches it only through a hook for columns that come from the database
(`TableDefinition.add_column_source`, registered in
`customfields/apps.py`) and small calls inside functions – in the item
forms, the history, the search, the import and the export in the import
format.
`chat.ChatAttachment` points to its message, `projects.ProjectRelation`
twice to `Project`, `material.ItemAudit` and `ItemTodo` to the item.

`incoming` lies **beside** `material`, not under or over it:
`InvoicePosition` points to `material.MaterialModel` and `masterdata`, and
`material.MaterialItem.source_position` points back to the position (a string
reference, `SET_NULL`). It is the one circle between two apps; the migrations
are ordered (`incoming 0001` after `material 0009`, `material 0010` after
`incoming 0001`); in code `incoming` imports `material`, and `material` imports
of `incoming` only the rights helper `incoming.access` (the asset pages and
API) – the item's field is the only link between the tables. `projects` gets the legacy tables
(`LegacyImportItem.document` points to `documents.Document`, the other way
round the flag `Document.is_historic` reads the reverse link), `products` the
relations, `accounts` the LDAP tables (`LdapGroupMapping` points to `Role`).

`schedule` has a table of its own, `CalendarLink`, which
points to `products.Product`, `material.MaterialModel` or
`material.MaterialItem` (and to the user who created it), never the other
way round: `schedule` lies on top of `material` and `products`. The
products and items reach it only through a `post_save` signal connected
by `schedule/apps.py` (a deactivated product or an archived item ends its
link) and through the template tag that their pages include.

A document (`documents.Document`) points to its project, to the user who
made it and, for a cancellation, to the invoice it cancels – to no product,
customer or line: what it shows is copied into the document when it is
made. A packlist points to the project; since 0.5 a `LineAssignment`
points to a material line and an `Extraction` to a project and a material
item. `api` has two tables of its own (call counts and stored answers),
which point to the API token of `accounts`, and two more, the
webhooks and their deliveries (`Webhook`, `WebhookDelivery`), which point
to the user who made a webhook. Where `core` keeps something
per user – the change log, the column choices, the tasks in the background
– it refers to the user model through `settings.AUTH_USER_MODEL`, as Django
intends.

A crew line (`projects.CrewLine`) points to a person and a job function of
`personnel`; a time entry (`timetracking.TimeEntry`) points to a project, a
person, a job function and – where there is one – a crew line. `personnel`
knows nothing about projects in its tables. Where its *pages* need them
("where is this person planned?"), the import sits inside the function,
like everywhere else. The one place where `projects` needs time entries –
approved hours per crew line – looks the model up by name
(`apps.get_model("timetracking", "TimeEntry")` in `projects/crew.py`), so
that `projects` does not import the module that builds on it.

Every person is an account and every account a person
(AUT-026): `personnel.Person.user` is a one-to-one link that is never
empty, and the two keep each other in step – `Person.save` updates the
account, `User.save` the person. `accounts` lies below `personnel`, so
`User.save` imports `Person` inside the function. `personnel` hears of
changed crew lines through a signal connected by the model's name
(`"projects.CrewLine"`, `personnel/calendars.py`), so it still imports
nothing of `projects`. The new tables point the usual way: availability
marks and CalDAV bookkeeping to the person, `projects.ProjectTemplate` to
the user who made it, `products.FixtureTypeMapping` to a product,
`mail.MailLogEntry` to a project, a mail and a user, `core.AccessLogEntry`
to the user.

Other links stay inside their modules or point the usual way: a
project to its whole project (`Project.parent`), a material line to the
line it takes over from, a group to its parent group – all within
`projects`; `packing.Handover` to the two `PackEntry` rows it connects,
and an `Allocation` to the handover it came with; `documents.LexwareTransfer`
to a document. `documents.AccountingSettings` is a single row, and the
contact in Lexware Office is a plain text on `customers.Customer`. The
webhooks in `api` must hear of events in modules above them. They hear of
projects and documents through `post_save` signals connected by the
model's name (`"projects.Project"`, `"documents.Document"`, in
`api/apps.py`), so `api` imports neither; `packing` and `timetracking`
call `api.webhooks.record` from their services, which is an import
downwards.

Further links point the usual way too: `products.Product.owner` to
`customers.Customer` (customer material, PRD-043) – `customers` refers to
nothing of `products`, and the customer's page reads the material through
`products.services.customer_material`, imported inside the view; and
`mail.CrewRequestMail` to a crew line of `projects` and a person of
`personnel` (PER-032) – `mail` sits above both already. The other way,
`projects.crew.request_deployment` calls `mail.crew_answers` with the
import inside the function, as for notifications.

Further links point the usual way as well: `personnel.JobFunction`
to its service product, now one-to-one (`related_name="job_function"`,
PRD-044); `projects.ProjectFile.supplier` and `mail.ProjectMail.supplier`
to `masterdata.Supplier` (PRJ-106); `projects.Project.follow_up_user` to
the user (PRJ-105). `ProjectMail.mailbox` and `MailLogEntry.mailbox` lost
their `PROTECT` for `SET_NULL` and keep the mailbox's name (EML-046). One
call goes upwards: a service product saved in `products` gives itself its
job function (`products.services.check_service_function`,
`link_service_function`), importing `personnel.models` inside the
function; the product reads its function through the reverse relation
(`Product.service_job_function`), which needs no import.

Further links point the usual way: `chat.ChatMessage` and
`ChatReadMark` to a project and users; `automations.Automation` to a
mailbox (`SET_NULL`) and a user, `AutomationRun` to its rule and a project
(both `SET_NULL`); `timetracking.Expense` to a person and a project
(`PROTECT`), like a time entry; `core.AddressPosition` only to the user who
set a position (`SET_NULL`) – it belongs to an address text, not to a
record of `customers` or `masterdata`, so `core` stays at the bottom. The
new fields stay in their tables (data-model). Where the new modules must
hear of others they listen or are called with the import inside the
function: `automations` hears of project statuses and crew answers through
`post_save` signals connected by the model's name (`"projects.Project"`,
`"projects.CrewLine"`, `automations/signals.py`) and of deleted mailboxes
through `pre_delete`; `mail.fetching` and `projects.follow_up` call
`automations.engine` – a call upwards, imported inside the function, as
for notifications. `core/changes.py` asks `chat.services.stamp` inside the
function. `core/maps.py` reads venues, customers, suppliers and projects
inside its functions; `projects/trips.py` builds on `core.maps` – an
import downwards. `projects.time_surcharges` uses `core.holidays`;
`projects/pricing.py` reads the approved expenses of `timetracking`
inside the function (`timetracking.expenses.approved_expense_sums`), as it
reads time entries.

`availability` has no tables of its own. It reads material (the stock and
the blocked periods), projects (the reservations) and packing (which items
are already out, which contents were taken out for a project) and
calculates; nothing about availability is stored (see
[core-flows.md](core-flows.md)). `schedule` stores nothing it shows: it asks
projects, personnel and availability and draws – also the timeline of a
single product, model, item or person (`schedule/timelines.py`, VFG-019,
PER-020), which adds blocked periods, inspections due and expiring
qualifications to the bars. Its only table, is
`CalendarLink` – the secret address of a product's, model's or item's
calendar, whose appointments are computed like the timeline when the
calendar is read (VFG-040). `schedule/course_timeline.py`
draws the timeline of one project for the tab "Zeitplanung" of `projects`
(PRJ-103) from rows the project's page passes in – `projects/course_views.py`
imports it, a page reaching sideways like the others below.

`notifications` sits on top, but everybody tells it things – a defect in
`material`, a new mail in `mail`, a request in `projects`, an error in
`core`. They call `notifications.services.notify()` from inside the
function that has the news, with the import inside the function, so that
no module below has to know the table. A notification by mail is sent
after the transaction commits (`transaction.on_commit`): an aborted change
tells nobody.

The **pages** are less strict, because a page shows what belongs together
for the person looking at it: the page of a product lists its material items
and answers "is it free next week?", the history of an item names the
projects it went out with, and a project asks the availability calculation
about every line. Where a module reaches "upwards" for that – products into
material, material into packing, projects and availability into each other –
the import is in a view, a history or a service, not in `models.py`. In the
few places where even that would make two modules import each other while
loading, the import happens inside the function, with a comment saying why.

`core` holds two kinds of things: at the bottom what every module needs
(change log, number ranges, list helpers, the table framework, the import
machinery, tasks in the background), and on top what spans all modules
(start page, global search, sample data, the full export). The machinery
below knows nothing about the modules: they **register** with it when
Django starts, in the `ready()` method of their `AppConfig` – their import
(`core.imports.register`), their kinds of background task
(`core.jobs.register`) – and their list definitions register themselves
when `tables.py` is imported. So the machinery needs no import of the
modules that use it (see "Shared machinery in `core`" below).

`documents` is a package of its own, but without a
module of its own in the rights: documents belong to a project, so the
module "projects" decides (reading needs read access to the project,
making and cancelling needs edit access), and the special right "see
prices" decides about order confirmations, invoices and cancellations.
The page Settings → Accounting belongs to the module
"administration" and needs the price right on top (DOK-011, DOK-012).
The reports of profitability live in `projects`
(`profitability.py`, PRJ-115) and need the module "projects" for every
project and the price right; a package of their own may follow. Roles can already carry rights
for them (`FUTURE_MODULES` in `accounts/rights.py`), so no role has to be
reworked when they arrive.

`projects` is the largest package and is cut by topic inside:

| File | Contents |
|---|---|
| `services.py`, `views.py` | projects, groups, material lines; the refusal of a service as a material line (`plannable_as_material`, `check_plannable_as_material`, PRD-044) and the status "offen" of a new subrental (PRJ-101) |
| `crew.py`, `crew_views.py` | crew lines, their price and cost (per hour, flat, per day), warnings, moving with their phase (`move_with_phase`), the personnel by phase and job function (`breakdown_by_phase`, PRJ-088); deployment view – the tab "Überblick" – and members; requests that remember the period asked for and the automatic new request after new times (`request_deployment`, `ask_again_for_new_times`, `period_text`, `new_times_text`, PER-033, PER-034); the values of a new line from the service product, billed by effort (`defaults_from_job_function`, PRD-044, PER-036), and the hour tiers in `price_crew_line` with the approved entries per day (`approved_times`, `ApprovedTimes`, PER-035); planning firmly (`firm` in `add_crew_lines` and `update_crew_line`, PER-041) |
| `crew_bulk.py`, `crew_bulk_forms.py`, `crew_api.py` | several crew lines at once – `change_crew_lines` with the actions `edit`, `firm`, `ask`, `delete`, each line through the single-line service, refused ones named with their reason (`CrewBulkResult`); the dialog "Werte setzen …" and `POST /projects/{id}/crew-lines/bulk` (PRJ-117) |
| `crew_changes.py` | what the planned person is told – planned firmly, a change of times, meeting point, note, phase, job function or vehicle with the value before, taken off (`snapshot`, `note_update`, `note_removed`, `note_firm`); `one_notice_per_person()` collects the notices of one action so each person gets one notification of kind `deployment_change`; never to the actor, not for declined lines, past deployments, cancelled projects or inactive accounts (PRJ-118) |
| `case_work.py` | the person responsible for a service case and the people taking part work on it whatever their roles – `works_on`, `case_work_required` (pages), `CaseWorkPermission` (API); project correspondence stays behind the special rights (AUT-033) |
| `hour_tiers.py` | the hours of a crew line per calendar day and their split at the limit – `planned_hours_per_day`, `approved_hours_per_day`, `split_at_limit`, `HourSplit`, `actual_cost_with_limit`; plain arithmetic, no query (PER-035) |
| `subrentals.py`, `subrental_views.py`, `subrental_forms.py`, `subrental_api.py` | the supplier field of a subrental with suggestions and "create" in a dialog (`SupplierTypeahead`, `supplier_suggestions`, `create_supplier`, PRJ-101); the page "Zumietung bei …" per project and supplier – lines, documents, correspondence (`build_page`, `update_lines`, `add_document`, `suppliers_of`), the supplier of a mail by hand, and their API (PRJ-106) |
| `follow_up.py`, `follow_up_views.py` | the follow-up of a project – `set_follow_up`, `clear_follow_up`, `filter_projects`, `due_for`, `notify_due_follow_ups` (run by the minute timer; it also starts the automations of a due follow-up) and the dialog (PRJ-105) |
| `split.py`, `split_views.py` | dividing a project afterwards – `split_plan` (`SplitPlan`, `GroupOption`), `split_into_subprojects`, `SPLITTABLE_STATUSES`; the page "In Teilprojekte gliedern" (PRJ-050) |
| `service_cases.py`, `case_views.py`, `case_forms.py`, `case_api.py`, `templatetags/service_cases.py` | service cases – `create_case`, `update_case`, `set_case_status`, `convert_to_project`, `create_from_inquiry`, `case_list`, `without_cases`; their pages and `/service-cases`; `case_api.py` also holds the API of dividing (`SplitView`) (PRJ-090, PRJ-050) |
| `showfiles.py` | show files as project files – `prepare_upload`, `mark_current`, `clean_show_fields`, the select marking show-file types (PRJ-089); the endings are in `core/showfiles.py` |
| `trips.py`, `trip_api.py`, `templatetags/trips.py` | the trips of a project from its phases, with route links – `trips_of`, `places_of`, `trip_document`, `GET /projects/{id}/trips` (PRJ-097) |
| `time_surcharges.py` | the surcharges for night, Sunday and holidays – `SurchargeRules`, `current_rules`, `time_pieces`, `planned_pieces`, `entry_pieces`, `applying`, `surcharge_parts`; plain arithmetic, the settings read once (PER-009) |
| `deployment.py` | the deployment view as data, shared by the tab, its PDF and the mail attachment; `neutral()` is the view of any colleague (PRJ-081, PER-019) |
| `access.py` | who may see and change which project (see "Rights" below) |
| `pricing.py` | all sums of a project, crew included |
| `wishes.py` | the wish for a certain model or item on a line (PRJ-064) |
| `planning.py` | everything the planning page shows, calculated once |
| `course.py`, `course_views.py`, `course_api.py` | the course of a project – the tab "Zeitplanung": phases with their crew (`crew_by_phase`, `update_phase(move_crew=…)`, PRJ-080), open items (PRJ-006, PRJ-059); the upload of project files (`files_page`, whose GET leads to the tab "Dokumente"); the dialog for a new phase over the crew planning (`phase_dialog`, PRJ-094); the question after a phase beyond the rental period (`rental_period_suggestion`, `extend_rental_period`, view `phase_extend_period`, PRJ-100) and the open shortages among the open items (`open_items_overview`, PRJ-098); the timeline of the project on the tab (from `schedule.course_timeline`, PRJ-103) instead of the box "Veranstaltungsort" (PRJ-102); the first guess of a new phase (`first_guess`, used by `phase_dialog` and `phase_edit`: a typed period unless it is the rental period, else after the latest phase; over several days one hour on the first day, PRJ-116) |
| `customer_material.py` | the rules of a line of customer material – `may_plan`, `refusal`, `clean_line`, called from `MaterialLine.clean` (PRJ-096) |
| `numbers.py` | numbers of today and former ones (those with "P-") – `project_by_number`, `numbers_of_today`, `matching`, `may_be_former` (ADM-012, ADM-014) |
| `templatetags/period_marks.py` | `{% project_period_marks project %}` and `{% form_period_marks %}`, the periods hatched in the calendars of the pickers (PRJ-099) |
| `defaults.py` | start data of the module – the project template "Dry Hire" (`install_dry_hire_template`, PRJ-095) |
| `files.py` | project files, what the crew may see of them (PRJ-007); a file can name a supplier and the kind of its document (PRJ-106) |
| `list_sums.py` | the sum columns of the project list – hours, revenue, costs, profit – computed only when shown, with a fixed number of queries (`attach_sums`, `with_sums`, PRJ-085) |
| `templatetags/project_actions.py` | the head of every project tab – `{% project_actions project %}`, `NEXT_DOCUMENT`, `suggested_document`; no query (PRJ-078) |
| `duplicate.py` | copying a project to another date (PRJ-029) |
| `summary.py`, `price_pdf.py` | the price overview for the customer, also as PDF; groups shown without lines summarise their contents (PRJ-066) |
| `tables.py` | the columns of the project list (UIX-015); the customer columns only for those who may see them (AUT-023) |
| `lines.py`, `line_views.py`, `line_api.py` | single lines of the planning: duplicating (PRJ-075), taking over new prices (PRJ-072); several lines at once (`change_lines`, `BulkAction`, `lines_bulk`, `BulkLinesView`, PRJ-082) and the alternative dialog (PRJ-083) |
| `price_updates.py` | lines whose product price changed since they took it over (PRJ-072) |
| `discounts.py` | the maximum discount of a job function (PER-026) |
| `project_templates.py`, `template_views.py` | project templates: save, manage, apply (PRJ-076) |
| `mvr.py`, `mvr_views.py`, `mvr_api.py` | taking over a lighting plot from an MVR file (PRJ-077); the file is kept in the project's files with a time prefix (`keep_file`, `kept_file_name`, PRJ-086) |
| `family.py`, `family_views.py` | whole projects and their parts: the rules in the module text, the tab "Teilprojekte" with the figures of every part and the shortages between them, adding a part, taking over a line of another part (PRJ-031, PRJ-044 to PRJ-047, PRJ-060) |
| `family_prices.py` | the prices of a whole project with its parts and their sum, shared by the price overview and the priced documents (PRJ-045, PRJ-046) |
| `family_labels.py`, `templatetags/subprojects.py` | the one way a part is named everywhere – "Teil von 2026-0042 Stadtfest", "2026-0042-1 Bühne Marktplatz (Stadtfest)" |
| `grouptree.py`, `group_views.py` | nested groups: the tree of a project's groups without a query, moving a group on the planning page (PRJ-037) |

`material` is cut the same way: `item_views.py` and
`item_api.py` hold the sub-pages of an item beyond its data (timeline,
inspections, files, defects, blocked periods) and their API,
`inspections.py` calculates when which item is due (MAT-030 ff.),
`labels.py` and `label_views.py` make labels with QR code or barcode
(MAT-026) – also the three labels of the operator's templates
(`label_layouts.py`, `label_settings.py`, MAT-056).

`personnel` is cut the same way: `marks.py` is the own
availability calendar (PER-021), `calendars.py` reads linked calendars and
writes the deployments into calendars (PER-022, PER-023), with
`calendar_client.py` for talking to calendar servers, and
`calendar_views.py` and `calendar_api.py` are its pages and API;
`availability.py` takes the marks into "who is free". `mail` got
`signature.py` (EML-034), `addresses.py` (EML-037), and `log.py` with
`backends.py` – the mail log and the e-mail backend that writes system
mails into it (EML-039). `schedule/calendars.py` lays out month and week of
the calendar (VFG-020, VFG-021).

Besides the files of `projects` above:
`packing/subprojects.py` – the packlist of a whole project, the handover
of taken-over pieces from one part to the next and taking it back
(PRJ-048, PRJ-060); in `api` the webhooks – `webhook_events.py` (the
events, what each sends, an example of each), `webhooks.py` (recording,
signing, sending, retrying, switching off, keeping), `webhook_api.py` and
`webhook_views.py` with `webhook_urls.py` (API and the pages under
Settings, API-012); in `documents` the accounting – `lexware.py` (DOK-011),
`datev.py` (DOK-012), and `accounting_views.py`, `accounting_forms.py`,
`accounting_api.py` for the page Settings → Accounting and its API.

Besides the files of `projects` above:

- `mail/mailboxes.py` – the mailboxes and their roles (EML-041): the
  lookups `correspondence_mailboxes`, `outgoing_mailbox`,
  `can_send_correspondence`, `system_mailbox`, `own_addresses`,
  `legacy_mailbox`; `save_mailbox` and `delete_mailbox` with the role
  rules; `smtp_session`, `check_connection`; `smtp_backend_options` and
  `system_sender` for system mails. `fetching.py` fetches every
  correspondence mailbox, `sending.py` sends through the outgoing one,
  `backends.py` through the system mailbox, `imap.py` files mails away as
  each mailbox is set. The new table `mail.Mailbox` points nowhere;
  `ProjectMail`, `UnknownTagMail` and `MailLogEntry` point to it.
- `personnel/availability_week.py` – the week of the availability calendar
  (PER-030), two queries; `personnel.CalendarFeed` – several linked
  calendars per person (PER-031), pointing to the person, with
  `AvailabilityMark.feed` pointing to it.
- `documents/deployment.py` – the PDF "Einsatzübersicht" (PRJ-081), built
  from `projects/deployment.py`; route `documents:deployment_pdf`. An
  import upwards (`documents` → `projects`), as for the other documents.
- In `schedule/services.py` the days view (1 to 10 days,
  `hours_per_column`) and exact bars (`Bar.lead`, `Bar.trail`, `Bar.style`)
  of VFG-024; `HOUR_ZOOMS`, `ZOOM_LABELS` and `zoom_choices()` are gone.
- In `packing/models.py` `material_out()`, the "material of this project is
  out" check that `availability/engine.py`, the start page and the status
  guard use (PCK-025). `availability` asks it inside its existing query,
  with the import inside the function (packing builds on the engine).
- `personnel/services.py` grew the rate lookup `applicable_row`, `Rate`,
  `RateBook`, `rate_for` (PER-029); `projects/crew.py` and
  `timetracking/services.py` call `rate_for` – an import downwards.
- In the new tables everything points the usual way: `CrewLine.phase` to a
  phase of the same project, `MaterialLine.alternative_to` and
  `Group.alternative_to` within `projects`.

Besides the files of `projects` above:

- `mail/crew_answers.py` – answers to deployment requests by reply mail
  (PER-032): the tag `[RA-E-<token>-JA|NEIN]`, the answer mailbox, the
  request mail with its `mailto:` buttons, `take_answer` for the fetch and
  the reply to the person; templates `mail/email/crew_request.txt` and
  `.html`; the table `mail.CrewRequestMail`. `fetching._handle` calls
  `take_answer` first; `projects/crew.py` calls `mailbox_for_request` and
  `send_request_mail`; `notifications.services.notify` got `email=` so the
  request mail can replace the plain notification mail.
- `core/middleware.py` `FormerNumberRedirectMiddleware` and, in
  `core/converters.py`, the former number in `ProjectNumberConverter`
  (`_former`, `former_numbers_in_address`) – ADM-012, see "A request, step
  by step" and "Readable addresses".
- `core/templatetags/rentalars.py` the block tag `{% filterpanel "key" %}`
  (`FilterPanelNode`, template `core/_filter_panel.html`, UIX-030);
  `core/_credit.html` (UIX-031); in `core/context_processors.py` the keys
  `company_name` and `rentalars_credit` (UIX-031, UIX-032), see "The user
  interface".
- `schedule/services.py` `projects_or_phases_in` – a project whose phase
  touches the span, for the timeline and the API `/calendar` (PRJ-092).
- `projects/defaults.py` is installed by the first-run setup
  (`core.setup.complete_setup`), not after `migrate` like the start data of
  the other modules: `install_defaults` also runs on every test database,
  and a template the company deleted must stay deleted. Installations set
  up earlier get it from the migration `projects/0013`.
- `products/services.py` `presets_for_owner` ("Material hinzufügen" on the
  customer's page) and `customer_material` (the customer's material with
  stock and storage locations, a fixed number of queries); the owner in the
  product form, list, import and API (PRD-043).

Besides the files of `projects` above:

- `packing/offline.py` (PCK-026, PCK-027) – `offline_projects` (what an app
  may take along) and `apply_changes` (the sync with its conflict rule,
  locking and limits); its API views `OfflinePacklistsView` and
  `PacklistSyncView` are in `packing/api.py`. In `packing/services.py`
  `take_back`, `return_limits`, `_book_ticked_returns` and `_back_from`
  (PCK-028), `ProgressBar` and `BarSegment` (PCK-029); in
  `packing/models.py` `taken_back_of()` and the change times in
  `PackEntry.save`; in `packing/views.py` `packlist_tabs` (PCK-030);
  templates `packing/_bar.html` and `_tabs.html`.
- `availability/engine.py` frees pieces taken back early from their
  booking on, reading them with the query it runs anyway
  (`packing.models.taken_back_of`, import inside the function as for
  `material_out`). `availability/services.py` `utilization_in_periods` –
  the utilization per hour column (VFG-029).
- `accounts/api.py` `ApiTokenViewSet` – the limits of a token that creates
  tokens (AUT-021).
- `mail/footer.py` (EML-045) – `add_footer`, called by
  `mail/backends.LoggingEmailBackend` for every system mail.
- `core/changes.py` – the stamp `<newest>.<newest by others>` (PER-033);
  `core/templatetags/rentalars.py` `required_condition`, `condition_holds`,
  `marks_required` and `core/forms.mark_required` (UIX-035), with the
  templates `core/_required_mark.html` and `_required_note.html`.
- `schedule/services.py` `crew_bar_css` (VFG-027), `LoadRun` and
  `utilization_rows` (VFG-029), `DEFAULT_DAYS` = 4; `schedule/views.py`
  the session key `schedule_span` and `DEFAULT_CALENDAR_VIEW` = "week"
  (VFG-028).
- New tables: none. New fields point nowhere new: `PackEntry` got four
  columns, `CrewLine` two, `SystemSettings` one (data-model).

Besides the files of `projects` above:

- `personnel/defaults.py` – the eight job functions of the start data with
  their service products (PER-037), called by `core.defaults.install_defaults`
  after the master data; `personnel/services.py` `service_category`,
  `create_service_product`, `save_job_function`, `delete_job_function`
  (PRD-044) and the rate from the limit in `RateBook.rate` (`Rate.above_limit`,
  PER-035). `products/services.py` `check_service_function`,
  `link_service_function` (PRD-044) and `presets_for_kind` (PRD-046);
  `products/models.py` `ProductKind.INCIDENTAL`, `CREW_ONLY_KINDS`.
- `schedule/course_timeline.py` with `templates/schedule/_course_timeline.html`
  – the timeline of one project (`course_scale`, `course_rows`,
  `crew_legend`, PRJ-103); `schedule/services.py` `people_in_plan`, which
  replaced `plannable_people` (VFG-023).
- `mail/suppliers.py` – which supplier a mail of a project belongs to
  (`supplier_for`, `mails_with`, `set_supplier`, `supplier_from`, PRJ-106),
  called by `fetching.py`, `sending.py` and the compose view;
  `mail/mailboxes.py` `deletion_of`, `delete_mailbox(…, successor=…)`,
  `switch_off_mailbox` and `_keep_name`, `mail/models.py`
  `keep_mailbox_name` and `mailbox_label` (EML-046); the confirmation page
  `templates/mail/mailbox_delete.html`.
- `material/services.py` `following_free_numbers`, `check_serial_numbers`,
  `manufacturer_named`, `supplier_named` (MAT-048, MAT-050),
  `create_product_from_model` (MAT-051), `assign_model_to_product`
  (PRD-046) – imports downwards into `products`; the suggestion views
  `manufacturer_suggest`, `supplier_suggest`, `product_suggest`,
  `model_suggest` and `model_create_product`, `model_assign`;
  `masterdata/models.py` `StorageLocation.get_default` (MAT-052) and
  `is_power_field` (MAT-049).
- `core/listing.py` `query_date` and `query_datetime` – a date from the
  address that may be impossible (UIX-004); `core/forms.py`
  `SystemSettingsForm.crew_answers` (ADM-015); `core/views.py` the start
  page's follow-ups; `core/management/commands/run_jobs.py`
  `_notify_due_follow_ups`.
- `notifications/models.py` `Kind.FOLLOW_UP`, by e-mail by default.
- New tables: none. New fields: `Product` two, `JobFunction` and
  `PersonJobFunction` one each, `CrewLine` three, `Supplier` two,
  `ProjectFile` two, `ProjectMail` two, `MailLogEntry` one, `StorageLocation`
  one, `MaterialModel` and `MaterialItem` one each, `Project` four
  (data-model). The new foreign keys point downwards; `JobFunction.service_product`
  became one-to-one.

Besides the files of `projects` above:

- Two packages. `chat` (UIX-010): `models.py` (`ChatMessage`,
  `ChatReadMark`), `services.py` (`readers_of`, `mentioned_in`,
  `post_message`, `edit_message`, `delete_message`, `messages_of`,
  `mark_read`, `unread_count`, `stamp`, `forget_author`), `views.py` and
  `urls.py` (the tab "Chat", `chat:project`, `chat:messages`, `chat:edit`,
  `chat:delete`), `api.py` (its `urlpatterns` are spliced into
  `api/urls.py`), `templatetags/chat_tags.py` (the message text with its
  mentions). `automations` (ADM-013): `models.py` (`Automation`,
  `AutomationRun`, `Trigger`, `Action`, `Recipient`), `engine.py` (events,
  `fire`, `run_pending`, the actions, the protection against loops,
  `PLACEHOLDERS`, `delete_old_runs`, `forget_name`), `signals.py`,
  `forms.py`, `views.py` and `urls.py` (below `/administration/automations/`,
  module administration), `api.py`.
- `core`: `maps.py` (route links, `MapPage`, `Place`, `map_for`, `locate`,
  `set_position`, `forget_position`, `delete_unused_positions`,
  `tile_origin`), `geocoding.py` (Nominatim: `look_up`, `_wait_turn`,
  `_send`), `map_views.py`, `map_api.py`, `templatetags/maps.py`
  (`route_link`, `map_box`, `address_line`); `holidays.py` (`holidays_of`,
  `is_holiday`, `STATE_CHOICES`); `surcharge_views.py`, `surcharge_api.py`
  (Einstellungen → Zuschläge, `/settings/surcharges`, `/holidays`);
  `showfiles.py` (`SHOW_SYSTEMS`, `is_showfile_name`, `guess_system`);
  `uploads.py` lets show files through; `middleware.py` widens `img-src`
  on map pages; `changes.py` the key `chat:<pk>`; `config.py` the section
  `[maps]` (`MapsConfig`, `settings.RENTALARS_MAPS`); `selfcheck.py` the
  device and the SD card on a Raspberry Pi (NFA-070).
- `timetracking`: `hints.py` (ZEI-018: `hints_for`, `attach_hints`,
  `working_days`, `HintLimits`), `expenses.py`, `expense_views.py`,
  `expense_api.py` (ZEI-019); `models.py` `Expense`, `ExpenseKind`.
- `schedule`: `moves.py` (`MoveRequest`, `apply_move`, `preview_move`,
  `perform_move`, `movable_project_ids`), `move_views.py`, `move_api.py`
  (VFG-026); `services.py` `Bar.move` and `project_timeline(movable=…)`.
- `documents/services.py` `invoices_enabled`, `check_invoices_enabled`,
  `makeable_kinds`, `INVOICE_KINDS` (DOK-014), called by `views.py`,
  `api.py`, `lexware.py`, `datev.py`, `accounting_views.py` and the head of
  a project; `MAKEABLE` stays importable from `documents.views`.
- `documents/bookkeeping.py` (DOK-055): `PAGES`, `API`, `is_bookkeeping`, `bookkeeping_on` and
  `BookkeepingMiddleware`; `core/navigation.py` `Section.bookkeeping`; `core/forms.py` `AccountingSwitchForm`.
- `mail/parsing.py` `Headers.reply_to`, `Headers.automatic`,
  `automatic_reason`; `mail/imap.py` fetches the header fields these need.
- `projects/crew.py` and `pricing.py`: the surcharges in `price_crew_line`
  (`CrewPrice.time_surcharges`, `cost_time_surcharges`,
  `actual_cost_time_surcharges`), `surcharge_rules_for`,
  `PriceLookups.time_surcharges`, `ProjectPrices.personnel_time_surcharges`
  and `expenses_cost`; `hour_tiers._local_days` became `local_days`.
- `deploy/lib.sh`: the section "The system and the device" (NFA-070, see
  "Where things are stored" and core-flows section 28);
  `tests/deploy/test_system.sh`.
- `static/vendor/leaflet/` – Leaflet 1.9.4 (BSD-2-Clause), loaded only by
  a map; `scripts/check_licenses.py` checks files in sub-folders.
- New tables: `ChatMessage`, `ChatReadMark`, `Automation`,
  `AutomationRun`, `Expense`, `AddressPosition`, `TimeSurchargeSettings`.
  New fields: `Project` three, `ProjectFile` three, `MaterialLine` one,
  `CrewLine` two, `Product` one, `Supplier` four, `DocumentType` one,
  `CompanyProfile` one, `SystemSettings` nine; new choices of
  `MailLogEntry.kind` and of the notification kinds (data-model).

Further files and changes:

- `core/network.py` (NFA-071, NFA-072) – the guard for user-entered
  addresses ("Outbound connections to user-entered addresses" below);
  `config.py` the section `[network]` (`NetworkConfig`) and `allow_http`
  (NFA-073); `selfcheck.py` the HTTPS state and `_network` ("Verbindungen
  zu anderen Servern").
- `core/forms.py` `add_validation_error(form, error)` and `routed_errors`
  (EML-024): an error on any form, plain or model, through
  `error_field_map` and Django's public `add_error`; the private
  `_update_errors` is not called from views. `core/tabular.py`
  `fold()`.
- `core/tables.py` (UIX-015): `Column.unsortable`, `Column.sort_prepare`,
  `PYTHON_SORT_MAX_ROWS`, `TableState.sort_notice`, `_order_in_python`,
  sorting by query expressions, `natural_key`, `first_value`;
  `core/admin_tables.py` `tree_path_order`; sorts in the table
  definitions of every module; `templates/admin/filter.html` (UIX-038).
- `core/maps.py` (UIX-033, UIX-034): **`route_url(destination, *,
  waypoints=())`**;
  `TILE_REFERRER_POLICY`, `map_data["referrerPolicy"]`.
  `core/templatetags/maps.py`: **`{% route_link destination label %}`**.
  `core/geocoding.py` `user_agent()`. `projects/trips.py`: `Trip.route_url`
  uses only the waypoints; `Trip.origin` is for display, API and map.
- `projects`: `trip_changes.py` (PRJ-111: `find_trip`, `change_trip`,
  `add_trip`, `remove_trip`, `reset_trip`, `_lock`; the stop limit is
  `core.maps.MAX_WAYPOINTS` = 9), `trip_forms.py`,
  `trip_views.py` (`trip_add`, `trip_edit`, `trip_remove`, `trip_reset`),
  `trip_api.py` (`ProjectTripView`, `ProjectTripResetView`),
  `models.TripAdjustment`; `my_deployments.py` (UIX-043, the table and
  view at `/me/deployments/`); `crew_views.py` `?from=course` (PRJ-110);
  `service_cases.require_customer`, `create_case(customer_required=…)`,
  `update_case` (PRJ-090); `core/navigation.py` and `core/trail.py` (Mein
  Bereich opens on Meine Einsätze).
- `schedule/course_timeline.py` and `templates/schedule/_course_bars.html`
  (VFG-035): the crew rows of the project timeline with the personnel
  plan's states, conflicts and hatching.
- `packing`: `offline.py` rewritten (PCK-027 – versions, clock rule,
  change IDs, `ensure_packlist_on_confirmation`), `models.PackEntry.version`,
  `models.SyncReceipt`, `services._LockedEntries` and `PackRow.version`,
  `api.py` (`base_version`, `change_id`, outcome `conflict`), `apps.py`
  connects the signal. `core/changes.py` the key `packing:<pk>`.
- `chat`: `models.ChatMessage.revision`; `services.edit_message`,
  `mark_read`, `stamp`; `api.ChatReadSerializer` (UIX-010).
- `mail` (EML-049): `models` `untagged_since`, `untagged_unread_only`,
  `LEFT_REASONS`; `aliases.untagged_skip`, `stamp_untagged_since`;
  `imap.HeaderInfo.seen`/`.received`, `parse_internaldate`, FETCH with
  `FLAGS INTERNALDATE`; `fetching._handle` applies the rule;
  `templates/mail/_untagged_since.html`. Removed dead code (NFA-062):
  `fetching.known_message`, `suppliers.link_by_address` and helpers in
  `accounts.rights`, `availability.services`, `projects.grouptree`,
  `products.services`, `products.scale_tables`, `personnel.models`;
  `templates/core/confirm.html`.
- `api`: `safeguards.py` (from "Repeated calls" on), `models.WriteLock`,
  `validate_webhook_url` with `check_entered_host`; `webhooks.py` through
  `network.open_url`.
- New tables: `WriteLock`, `SyncReceipt`, `TripAdjustment`. New fields:
  `PackEntry.version`, `ChatMessage.revision`, `Mailbox` and
  `MailboxAddress` two each (data-model).

Further files and changes:

- `documents/invoice_reminders.py` (DOK-015) – when a project counts as
  invoiced (`state_of`, `InvoiceState`, `gets_invoice`, `open_condition`,
  `open_projects`), "Rechnung gestellt" and "Keine Rechnung"
  (`set_invoice_status`, `projects.models.InvoiceMark`), which projects are
  due (`due_projects` – closed since `invoice_reminders_since`, net total
  above 0 through `projects.list_sums._prices_of`), who is told
  (`recipients_of`, price right) and the daily run on the minute timer
  (`run_due_invoice_reminders`, called by `run_jobs` like the shortage
  check; `latest_slot`, `next_run`); `documents/templatetags/invoices.py`
  (`{% invoice_state project %}` in the head of a project and on the tab
  "Dokumente"), `documents.views.invoice_mark`; the bookkeeping of a
  project's reminders is `notifications.InvoiceNotice`, the settings are in
  `core.NotificationSettings` (its `BOOKKEEPING_FIELDS` are written by the
  run alone).
- `projects/profitability.py` (PRJ-115, MAT-053) – nothing stored: the
  figures of many projects at once (`figures_of`, `project_report`), what
  each line earned after discounts and group shares (`line_contributions`,
  `kit_shares`, `line_revenues`), what each item earned – assigned when
  packing or shared out (`revenues_of_items`, `item_revenue`) – and per
  product (`product_report`); `report_views.py` (the pages under
  "Auswertungen", CSV) and `report_api.py`; the navigation entry
  "Reports" (`core/navigation.py`, special right "prices", all projects).
- `projects/defect_cases.py` (MAT-057) – a service case of a defect report
  (`create_from_defect`, `suggestions`, `values_of`, `case_of`,
  `inquiry_of`); `Project.source_defect`; `service_cases.CASE_FIELDS` with
  `is_internal` and `require_customer` for internal cases; the
  automations' trigger `defect` and actions `create_case` and
  `create_inquiry` (`automations/engine.py` `defect_reported`,
  `_create_case`, `_create_inquiry`; `automations/signals.py` listens to
  `material.DefectReport` by name); the default rule in
  `automations 0001_squashed_0003_defects_085`; `mail.UnknownTagMail.defect_report` – an
  entry under Anfragen that `assign_unknown` refuses and
  `create_from_inquiry` turns into a case.
- `mail/notes.py` (EML-051) – notes in the correspondence
  (`add_note`, `update_note`, `may_change`): a `ProjectMail` with
  `direction` "note" (`Direction.NOTE`; the mail log keeps
  `LOG_DIRECTIONS`); `views.note_create`, `note_edit`, `_note_page`,
  `mail_delete` for the writer; `api.ProjectMailNoteView`, `PATCH` on
  `ProjectMailDetailView`; `ai/correspondence.py`, `ai/summary.py` and
  `ai/overview.py` read notes as notes; `automations.signals._mail_saved`
  leaves them out.
- `material/label_settings.py`, `label_layouts.py`, `label_api.py`
  (MAT-056) – `LabelSettings` (a singleton, imported at the end of
  `material/models.py`), the three layouts of the P-touch templates in
  points (`SMALL`, `LARGE`, `CABLE`, `lay_out`, `fit_size` and `fit_block`
  with the metrics of Liberation
  Sans through fontTools, see below); `labels.py`
  `render_layout_html`, `layout_texts`, `default_format`, `all_formats`;
  `label_views.labels_print` (the page that opens the print dialog,
  `static/js/label-print.js`) and `label_settings_page`;
  `core.views.media_file` serves `labels/`.
- `material` (MAT-054, IMP-014 to IMP-016): `MaterialItem.purchase_price_in`
  with `_clean_purchase_set` and `purchase_set`; `services.create_items(…,
  price_for_set=…)`; `importer.py` `gross_factor`, `_SET_REFERENCE`,
  `_resolve_purchase_sets`, `run_import(options)`; `core.imports.ImportOption`
  and `ImportKind.options` (the options of an import kind, shown by
  `import_views` and taken by `import_api`); `numbering.parse_inventory_number`
  takes "#0802".
- `core`: `SetupForm` asks price and costs per hour, `setup._set_personnel_rates`
  (ADM-018); `templates/core/administration.html` in themed boxes (UIX-046);
  `templates/base.html` the foot of the sidebar (UIX-047); `static/js/app.js`
  `[data-bulk-bar]` (UIX-048).
- Addresses (NFA-074): Projekte → Anfragen moved from `/mail/` to
  `/projects/inquiries/`, the rental scales from `/products/scales/` to
  `/administration/scales/`, the mail log to `/administration/mail/log/`,
  "fetch now" to `/administration/mail/fetch/`, the address suggestions to
  `/projects/mail-addresses/`; the redirect `mail:settings_old` is gone;
  `notifications 0010_addresses_085` moved stored links (squashed). Paths that were
  written into Python code (`f"/material/items/{pk}/"` …) are made with
  `reverse()` now. The API paths did not change.
- New tables: `LabelSettings`, `InvoiceNotice`. New fields:
  `Project.invoice_status`, `Project.source_defect`,
  `MaterialItem.purchase_price_in`, `UnknownTagMail.defect_report`, seven on
  `NotificationSettings`; `ProjectMail.direction` four characters long
  (data-model). Two new links between tables, both in the usual direction:
  `projects.Project` → `material.DefectReport` and `mail.UnknownTagMail` →
  `material.DefectReport`.

Further additions and changes:

- `material/purchases.py`, `purchase_forms.py`, `purchase_views.py`,
  `purchase_api.py` (MAT-061, MAT-062) – "Kauf einpflegen": the purchase
  head and the positions (`Position`, `NewModel`, `check_positions`,
  `create_purchase` – every item in one transaction with consecutive IDs,
  new models once even if two rows name them), the invoice stored once and
  listed with each item (`attach_invoice`; `services.delete_file` keeps the
  shared file until its last row), the uploaded invoice kept for its user
  (`keep_invoice`, `pending_invoice`, `delete_old_invoices`, signed
  tokens, `DATA_DIR/purchase-invoices/`), the text of a PDF with pypdf
  (`invoice_text`, no scans), the head without AI (`head_from_text`), the
  matching of suppliers and models (`match_supplier`, `model_candidates`,
  certain matches only) and the proposal (`build_proposal`); the pages
  `material:purchase`, `purchase_reading`, `purchase_done`,
  `purchase_model_suggest`; `ai/invoices.py` reads the positions with AI
  (job `ai_invoice`). pypdf is a runtime library since this version
  (`requirements.txt`, `THIRD-PARTY.md`).
- `material` (MAT-059, MAT-060, MAT-063, MAT-064): `forms.PriceEntryMixin`
  (net or gross with the tax rate it includes, remembered per session by
  `views.remember_price_entry`; the API takes `prices` and
  `price_tax_rate`); `views.supplier_create` with `forms.SupplierDialogForm`
  and `templates/material/_supplier_dialog.html` – the suggestion "neuer
  Händler" of a supplier field carries a `create_url`, the answer 204 with
  the event `supplierCreated` fills the field (`static/js/app.js`);
  `views.item_jump` and `_item_jump.html` in the head of every tab of the
  material management and of the product list; `views.model_copy`,
  `services.copy_name`, `copy_inspection_types` and
  `forms.item_copy_initial` for duplicating (prefilled forms, no API).
- Labels (MAT-065, MAT-066): `label_layouts.py` rewritten – the printable
  area of the Brother QL printers (`printable_area`, `usable_area`,
  `FEED_SAFETY_DOTS`, also `SIDE_SAFETY_DOTS` at the left side of the cable label), the QR code over the full printable height in whole
  printer dots (`qr_part`), the font Liberation Sans from `static/fonts`
  (`FONT_FILE`, metrics through fontTools), the logo in 1-bit at 300 dpi
  (`print_logo`), the blank lead-in of the cable label (`LEAD_IN_PT`,
  shortened only on a short label); `label_views.item_labels` (the dialog
  "Etikett" of an item, a page of its own without scripts) and the button
  "Etiketten" of a model (`?model=`); the settings preview draws the
  printable area dashed.
- `products` (PRD-047 to PRD-051): `Product._check_prices` (one price),
  `projects.services.defaults_from_product` (no new sale of a rental
  product), `products 0009_one_price_091`; `services.duplicate_values`,
  `save_duplicate`, `POST /products/{id}/duplicate`; `views.article_number_field`
  (htmx, the field of an existing product's form) and
  `services.article_number_for`; the availability box of the product page
  loads with htmx after 0.4 s, with the link to the utilization.
- `schedule` (VFG-037, PRJ-118): kits in the utilization (`UtilizationRow`
  with `is_kit`, `parts`, `per_kit`; the API's `free`, `components`,
  `per_kit`), unfolded without scripts; `moves.apply_move` runs inside
  `crew_changes.one_notice_per_person()` and passes the people told
  (`crew_told`) to `notifications.services.project_changed`, so "new
  period" reaches only crew who got no change message.
- `accounts` (AUT-031, AUT-032, AUT-034): `ProjectScope.DEPLOYMENT`,
  `Rights.level_of_planning`, `reads_planning`, `case_work`;
  `SpecialRight.AVAILABILITY` and every place it gates;
  `data_access.py` (the columns "Finanzen", "Personaldaten",
  "Kundendaten" of `accounts/tables.py` and `personnel` tables, the
  legend `_data_access_legend.html`, `data_access` in `/users` and
  `/people`; "kein Zugang" for an account `can_log_in` refuses – also one past its "gültig bis"); `accounts 0008_roles_091`.
- `timetracking` (ZEI-029 to ZEI-031): `reminders.py`
  (`run_due_approval_reminders`, called by `run_jobs`; who is reminded of
  what, `notifications.ApprovalNotice`), `services.correct_and_approve`
  with `CorrectionForm`, `templates/timetracking/_entry_correct.html` and
  `POST /time-entries/{id}/correct`; the notification `time_decision`
  once per person and action.
- `personnel/availability.py` (VFG-038): "Alle Personen, unabhängig von der
  Funktion" includes people without job function.
- `documents` (DOK-019, DOK-020): `outgoing*.py` (see "Documents"), the
  navigation entry "Buchhaltung" between Materialverwaltung and Kunden
  (`core/navigation.py`, icon `invoice`; `core/trail.py` knows
  `documents:outgoing` as a start page), the monthly statement under
  `/accounting/monthly/`.
- `projects/course.py` `first_guess` (PRJ-116); the planning keeps a gap
  above the totals and lost the hints "in keiner Teilgruppe" of personnel
  and logistics (UIX).
- Addresses (NFA-074): the monthly statement moved from
  `/projects/service-cases/monthly/` to `/accounting/monthly/` (same URL
  names, no redirect); new `/accounting/documents/`,
  `/material/purchase/…`, `/material/suppliers/new/`,
  `/material/items/jump/`, `/material/items/<pk>/labels/`,
  `/products/<pk>/article-number/`. The API
  paths of existing operations did not change.
- New tables: `ApprovalNotice`. New fields: four `approval_*` (and three
  bookkeeping ones) on `NotificationSettings`, `AISettings.invoice_source`
  and `invoice_provider`; new choices `RequestStatus.FIRM`,
  `ProjectScope.DEPLOYMENT`, `SpecialRight.AVAILABILITY`, three
  notification kinds, `Use.INVOICE` (data-model).

Further additions and changes:

- `material/dguv.py` (MAT-077, MAT-078) – the electrical inspection after
  DGUV V3 / DIN VDE 0701-0702: the limits as data in one place (`LIMITS`,
  with the sections of the standard), which measurement applies to which
  protection class (`MEASUREMENTS`), `pe_resistance_limit` (the R_PE limit
  by cord length), what each class needs measured (`REQUIRED`),
  `evaluate`/`Evaluation`/`ValueCheck` (every value against its limit,
  the suggested result and its reasons), `clean_values`
  (the rules of recording) and `cord_length_of` (the category field
  "Länge"/"Length" in m, cm or mm). Page, live check, API and report all
  call it; nothing else knows a limit. `forms.InspectionForm` gained the
  fields (`electrical_values`, `evaluation`, `measurement_rows`),
  `services.record_inspection` the argument `electrical`,
  `item_views.inspection_check` (htmx, `POST
  /material/items/<pk>/inspections/check/`, answers
  `material/_dguv_check.html` with out-of-band limits – no new
  JavaScript) and `inspection_report`;
  `item_api.ItemInspectionCheckView`, `InspectionReportView`,
  `ElectricalValuesSerializer`.
- `material/inspection_report.py` (MAT-078) – the test report: the HTML
  template `material/inspection_report_pdf.html` made into a PDF by
  WeasyPrint like the documents, in the language of the documents
  (`for_documents`), fonts and logo from the installation; file name
  `Pruefprotokoll-<ID>-<date>.pdf` (`pgettext("file name", …)`).
- The protection class (MAT-077): `models.ProtectionClass`, the model
  field and the item override (data-model), the column
  in `tables.py` (items sorted by `Coalesce(NullIf(override), model)`),
  `templates/material/_protection_class_fact.html`, the copy of a model
  (`views.model_copy` values), the import (`importer._parse_protection_class`,
  `_Writer._take_protection_class`, `model_classes`) and the export in the
  import format (`import_export.py`), `core.tabular` the English heading.
- `material` (MAT-074, MAT-075, MAT-076): "Kauf einpflegen" with one row
  (`purchase_forms.EMPTY_ROWS` 1, `SPARE_ROWS` 3), `AmountField`,
  `purchase_sums`/`PurchaseSums` and `templates/material/_purchase_sum.html`
  (the page script recomputes it: `static/js/app.js`, "purchase sums");
  `purchases.parse_amount`, `invoice_numbers`/`InvoiceNumbers`,
  `totals_in_text`, `purchase_categories`, `match_category`,
  `purchase_products`, `match_product`, `without_prices`; the button on
  the product list (`templates/products/list.html`).
  `ai/invoices.py`: `catalogue` and `prompt_for` (categories and up to 40
  products in a data block of the prompt, at most a third of its room),
  `parse_answer(…, invoice_text=…)` with `NumberLiteral`,
  `_serial_numbers`, `INVOICE_TOKENS` 3,500.
- `material` (MAT-058, MAT-070, MAT-079; LOG-020):
  `audits.master_data`/`MasterDataRow` and
  `templates/material/_audit_master_data.html`, `item_edit` with `?next=`
  (`item_views.safe_next`); `templatetags/material_tags.py`
  (`open_points_total`, the counts once per request); the folded table
  of `_model_revenue.html` (`<details>`); `fleet.is_vehicle_category`,
  asked by `transition_problem` (page, dialog and API alike).
- `schedule` (VFG-040) – its first table: `models.py` (`CalendarLink`),
  `calendar_links.py` (rights `may_see`/`may_manage`, `create_link`,
  `deactivate_link`, `link_for_token` in constant time, the signal
  `subject_archived` connected in `apps.py`, the appointments and
  `calendar_of` with its ETag), `calendar_link_views.py`
  (`calendar_link_change`, `calendar_link_feed` under `/calendar-feed/`,
  the rate limits shared with `personnel.calendar_views`),
  `calendar_link_api.py`, `templatetags/calendar_links.py`
  (`calendar_link_box`, so the three pages' views know nothing of it) and
  `templates/schedule/_calendar_link.html`; `timelines.item_events`/
  `ItemEvent`, split out of `item_bars` and used by both.
- `automations` (ADM-019): `defaults.py` (`DEFAULTS`, `BY_KEY`,
  `is_changed`, `missing`, `restore`), `Automation.default_key`,
  `is_default`, `default_changed`; `views.automation_restore_defaults`
  (`/administration/automations/restore-defaults/`), the action
  `restore-defaults` of the API viewset; `list_tables` with the marks, the
  column "Herkunft" and the `cell-buttons` row.
- `notifications` (UIX-052, VFG-036): `models.SETTING_LABELS` and
  `ALWAYS_SENT` (empty), `services.switchable_kinds`, `setting_label`,
  `notify` refusing an unknown kind, `_remind_of_shortages` (one reminder
  per project and check); `categories.py` with `job_finished` first under
  "System"; the API's `label` and `category_label`.
  `documents/templatetags/invoices.py` `_may_open` (DOK-015: the number of
  a monthly invoice only for whoever may open it).
- `core`: the template filter `css_string` (`templatetags/rentalars.py` –
  CSS escapes for the page margins of the packing list, family packing
  list and timesheet PDFs, where `escapejs` wrote "u0026");
  `export.SECRET_FIELDS` with `schedule.calendarlink.token`;
  `history.EVENT_TEXTS` with the four calendar link events;
  `templates/core/_field.html` with the help text at `<id>_helptext`
  (NFA-025; likewise the hand-written fields of other templates, and
  `masterdata.admin._HelpInHeadField` for the tabular category fields);
  `core 0024_notification_defaults_093`.
- `personnel/calendars.py`: `X-PUBLISHED-TTL` as a duration (`PT30M`).
- Addresses: new `/material/items/<pk>/inspections/check/`,
  `/material/inspection-records/<pk>/report/`,
  `/schedule/calendar-links/<kind>/<pk>/`,
  `/calendar-feed/<kind>/<pk>/<token>.ics`,
  `/administration/automations/restore-defaults/`; in the API
  `POST /automations/restore-defaults`,
  `POST /material-items/{id}/inspections/check`,
  `GET /inspections/{id}/report` and
  `/products|material-models|material-items/{id}/calendar-link`. The paths
  of existing operations did not change.
- New tables: `CalendarLink`. New fields: `MaterialModel.protection_class`,
  `MaterialItem.protection_class_override`,
  `InspectionType.is_electrical`, nine on `Inspection`,
  `Automation.default_key`, `NotificationSettings.invoice_cases_since`;
  new defaults of two `NotificationSettings` fields (data-model).

### Spots, roles and mail answers

- `material` (MAT-080 to MAT-083): `spots.py` (`normalise_spot`),
  `MaterialItem.storage_spot`; the mass inspection – view
  `views.inspection_batch` (`/material/inspections/batch/`), forms
  `BatchInspectionForm` and `BatchRowForm`, `services.record_inspections`,
  `dguv.cord_length_of(fields_by_category=)` against N+1 queries and the API
  route `POST /material-items/inspections/batch` (`item_api.BatchInspectionView`);
  the link to the inspection types in the tab "Prüfungen".
- `projects` (PRJ-122, PRJ-123): `pricing.overall_discount_of`,
  `services.set_overall_discount`, the fields `overall_discount_*`; the
  customer name for every role.
- `accounts` (AUT-036): `defaults.py` and migration 0009.
- `mail` (PER-043): `imap.effective_action(answer=)`.
- New fields and migrations: data-model. No existing API
  path changed.

### Uninstall, free documents and years

- `deploy` (NFA-078): `uninstall.sh`, the dispatcher entry in `rentalars`,
  shared constants in `lib.sh`; `tests/deploy/test_uninstall.sh` is step 7 of
  `scripts/check.sh`.
- `projects` (PRJ-124 to PRJ-128, PER-044): `course.first_guess` (8 hours),
  the Überblick as landing page (`projects:overview`, `views.project_overview`),
  `period_warnings.py`, discount warnings in `discounts.py` and the line
  views and API, `MaterialLine.is_text`, the link of the product number and
  the `?project=` preset of the availability box.
- `products`/`availability`/`packing` (PRD-052): `Product.pieces_per_product`
  and its use in `stock.py`, `engine.py`, `packing/services.py`.
- `material` (MAT-084, MAT-085): `serials.py` (warnings), `label_layouts.py`
  (the label geometry like the originals).
- `customers` (KND-011): `names.py`, `greetings.py`, the contact form and
  the endpoint `/customers/contacts/greeting/`.
- `documents` (DOK-021, DOK-022): `free.py`, `free_forms.py`, `free_views.py`,
  `free_mail.py`, `free_api.py`; `Document.project` nullable.
- `core` (UIX-054, UIX-055): `years.py`, `trail.follow_referer`.
- New fields and migrations: data-model. New API paths:
  `accounting/drafts…` and `accounting/documents/<id>/send`; existing paths
  gained fields (`warnings`, `is_text`, `pieces_per_product`, …).

### Incoming invoices and further additions

- **New app `incoming`** (DOK-023, DOK-024): `models.py` (`IncomingInvoice`,
  `InvoicePosition`), `services.py` (upload, head, positions, status,
  duplicates, delete), `reading.py` (text and patterns, `apply_proposal`),
  `costing.py` (`costing_of`, `spread`, `even_slice_cents`), `booking.py`
  (`plan`, `book`), `access.py` (rights), the pages under
  `accounting/incoming/…` and `administration/incoming-invoices/`, 12 API
  paths with 17 operations (`incoming-invoices…`, `incoming-settings`).
- **`material`** (MAT-086 to MAT-088, MAT-040, MAT-027, UIX-006): assets and
  book value (`depreciation.py` – pure functions –, `book_values.py`,
  `assets.py`, `asset_*.py`), sale from stock (`sales.py`, `sale_models.py`),
  `installed_*.py` and `installations.py`, `partial_dates.py`, `scan*.py`.
  Pages: `/accounting/assets/`, `/accounting/assets/sales/`,
  `/material/items/<id>/sell/`, `/material/scan/`.
- **`products`** (PRD-023, VFG-015): `relation_models.py`, `suggestions.py` and
  the views; **`packing`** (PCK-010 and others): `scan.py`.
- **`projects`** (PRJ-130, PRJ-123, UIX-056, PRJ-064): the legacy import
  (`legacy_*.py`, the task `legacy_invoices`, `ai/legacy_invoices.py`),
  `overall_target.py`, `stock_watch.py` and the view
  `planning_availability`, `MaterialLine.further_preferred_items`, the
  "subgroup scroll" block of `static/js/app.js`.
- **`accounts`** (AUT-029): `ldap_*.py`, `LdapBackend` as the second backend
  (`settings.AUTHENTICATION_BACKENDS`), `management/commands/ldap_sync.py`,
  `User.ldap_dn`/`local_account`, five security-event kinds; the daily
  maintenance runs `sync_nightly`.
- **`ai`** (EML-056, NFA-079): `auto.py`, `privacy.py`,
  `management/commands/ai_summaries.py`, changes in `client.py`, `summary.py`,
  `drafts.py`; `customers/services.py` exports and erases summaries.
- **`personnel`** (PER-038): `offer_models.py`, `offers.py` and the views;
  small additive hooks in `projects/crew.py`, `personnel/privacy.py`,
  `notifications` and `mail/crew_answers.py`.
- **`core`** (UIX-057): `manual.py` with chapters; `changes.py` (`stock:<pk>`);
  `middleware.py` (`Permissions-Policy`); `history.py` (event texts).
- **New commands:** `ldap_sync [--apply] [--force]`, `ai_summaries [--dry-run]
  [--project N] [--limit N]`. **New tasks in the background:**
  `ai_incoming_invoice`, `ai_auto_summaries`, `legacy_invoices`.
- **New dependencies:** `ldap3 2.9.1` (LGPL-3.0) and `pyasn1 0.6.4` (BSD) in
  `requirements.txt` and `THIRD-PARTY.md`; the update runs
  `pip install -r requirements.txt`.
- **Request flows** of the new parts: [core-flows.md](core-flows.md), the
  sections 42 to 48. New fields, tables and migrations: data-model.


## Inside a module

Every module has the same files. Knowing one, you know where to look in all:

| File | Contents |
|---|---|
| `models.py` | Tables and the rules that hold for a single record (`clean()`). |
| `services.py` | Business logic: everything that needs more than one record, or rights, or a transaction. |
| `views.py`, `forms.py`, `urls.py` | The browser pages. |
| `api.py` | The API: serializers and views. Addresses are registered in `rentalars/api/urls.py`. |
| `tables.py` | The lists of the module as `TableDefinition`s: which columns they can show, how they sort and export (`core/tables.py`). |
| `importer.py` | The import of the module's list (material, products, customers, people), registered in `apps.py`. |
| `apps.py` | The `AppConfig`; its `ready()` registers imports and kinds of background task with `core`. |
| `defaults.py` | Start data of a fresh installation, installed after `migrate`; the template "Dry Hire" of `projects/defaults.py` by the first-run setup instead. `personnel/defaults.py` brings the job functions, after the master data, whose categories and tax rates their service products need. The exception is `automations/defaults.py`: the definitions of the rules that came with Rentalars, created again only by "Standard-Automationen wiederherstellen", never installed by itself. |
| `management/commands/` | Commands for the command line. |
| `migrations/` | Changes of the tables, generated by Django. |

Templates are in `templates/<module>/`, styles and scripts in `static/`.

### One logic, two doors (API-002)

The rule that shapes the code most: **browser pages and API do the same
things, so they must run the same code.** Neither a view nor an API class
contains business logic. Both call a service:

```
 browser form ─▶ projects/views.py ──┐
                                     ├─▶ projects/services.py add_line() ─▶ models, availability
 POST /api/v1/… ─▶ projects/api.py ──┘
```

`add_line` checks the rights, fills in the defaults from the product, takes
the lock, saves, judges the availability. Whoever calls it gets the same
result. A rule added there holds for both doors – and for the import and for
the commands, which call services as well.

Consequences you will see everywhere:

- Services take the caller's `rights` as an argument instead of a request.
  They work the same from a view, an API call, a command or a test.
- Services raise `django.core.exceptions.ValidationError` with a message
  for people. A view shows it as a message on the page; the API turns it
  into its uniform error format (`api/errors.py`).
- Every business function has a test that goes through the API
  (`tests/api`). The test run fails if an API operation was never called
  (`rentalars/testing.py`, API-014).

### What a model may do

Rules that concern one record live in the model's `clean()`: an archived
container must be empty, an article number must start with the code of its
category. Django does not run `clean()` on `save()` by itself. It is run by
whoever saves: the services call `full_clean()` before `save()`, the browser
forms do it as part of their validation, and the API serializers inherit
from `CleanModelSerializer` (`api/serializers.py`), which does the same.
New code that saves a record follows that pattern.

Everything else is a service.

## A request, step by step

`rentalars/settings.py` lists the middleware in order. For a page request:

1. **RequestCacheMiddleware** – system settings, mail settings and
   company profile are read once per request and kept until it ends
   (`core/middleware.py`, NFA-012).
2. **SecurityMiddleware** – redirect to HTTPS, security headers.
3. **ContentSecurityPolicyMiddleware** – tells the browser to load scripts,
   styles and fonts only from this server (NFA-050, NFA-048). A
   page that can show a map also allows images from the tile server of the
   configuration file (`request.csp_image_sources`, set by `{% map_box %}`;
   UIX-034) – no other page does.
4. **Session, Common, CSRF, Authentication** – Django's own.
5. **MessageMiddleware** – Django's own; it comes this early because the
   next one may leave a message for the login page.
6. **SessionActivityMiddleware** – ends a session after the configured time
   without a request and keeps `UserSession` up to date, so a user can see
   and end their logins (`accounts/sessions.py`, AUT-008).
7. **CurrentActorMiddleware** – remembers who is acting, for the change log.
8. **SetupRequiredMiddleware** – until the first-run setup is done, every
   address leads to it (NFA-033).
9. **LoginRequiredMiddleware** – every page needs a login unless it is on
   the short list of public ones (login, password reset, setup, and the
   calendar subscription link `/calendar-feed/`, which carries a secret of
   its own – also the calendar links of products, models and
   items below it). A new page is protected without anyone having to
   remember it.
10. **PasswordChangeRequiredMiddleware** – after a one-time password, every
    page leads to `/account/new-password/`, and the API answers 403
    `password_change_required` (`accounts/twofactor.py`, AUT-027).
11. **TwoFactorRequiredMiddleware** – somebody whose role or the system
    settings require the second factor, and who has not set it up, is led to
    the setup page and nowhere else (`accounts/twofactor.py`, AUT-006).
12. **FormerNumberRedirectMiddleware** – an address with a
    former project number – the one with "P-"
    (`/projects/P-2026-0042/prices/`) – gets a permanent redirect to
    today's (`/projects/2026-0042/prices/`), query string kept; only GET
    and HEAD, a POST is served at the old address (`core/middleware.py`,
    ADM-012, ADM-014). It works in `process_view`, after the
    URL converter noted the former number. After the login and two-factor
    middleware, so that nobody learns a number before logging in; before
    the trail, which then only sees today's address.
13. **TrailMiddleware** – works out where "Back" leads from this page and
    keeps the way in a cookie (`core/trail.py`, UIX-011).
14. **AccessLogMiddleware** – after the view answered, notes who read which
    customer, person or project, file or export (`core/access_log.py`,
    AUT-028; see "The access log" below).
15. **PageSizeMiddleware** – remembers the number of entries per page a user
    chose in a list (`core/listing.py`, UIX-012).
16. **XFrameOptionsMiddleware** – Django's own.
17. **ApiSafeguardMiddleware** – only for addresses below `/api/`:
    `Idempotency-Key`, `ETag`, `If-Match`, `If-None-Match` and the headers of
    the rate limit (`api/safeguards.py`, API-010, API-011; see "The API"
    below). It comes last, so that for an `If-Match` it can ask the view
    directly what a GET of the same address delivers now.
18. The view. It is decorated with `@module_required(Module.X, Level.Y)`.

A login with the second factor switched on is two steps in the browser:
the password leads to a page that asks for the code; only then is the user
logged in. The API login (`POST /auth/login`) takes the code in the same
request (`code`), answers `code_required` without it, and refuses an
account that must have the second factor but has not set it up
(`two_factor_setup_required`) – there is no page in the API for that.
Personal API tokens are not affected; they are created by a user who is
logged in already.

API requests take the same path; DRF then authenticates by token or session
(`accounts/authentication.py`), `ModulePermission` checks the module level
that fits the HTTP method – reading needs "read", `POST`/`PATCH` "write",
`DELETE` "delete" – and `TokenRateThrottle` counts the call against the
token's limit per minute (`api/safeguards.py`, API-011).

## Rights (AUT-013 ff.)

`accounts/rights.py` is the single place that decides what a user may do.

- A **role** grants a level per module (none, read, write, delete) and any
  number of **special rights** (see prices, see purchase prices, reopen
  closed projects …). Special rights are deliberately separate from the
  module levels (AUT-019): warehouse staff edit material without seeing
  prices.
- A user's rights are the highest level per module and the union of the
  special rights over all roles: `rights_of(user)` returns a `Rights` object.
- An API token can narrow the rights of its user (read-only, certain
  modules), never widen them (AUT-021).

Prices are a good example of how this reaches the output. Whether a user
sees prices is decided once (`rights.has(SpecialRight.PRICES)`); templates
get `can_see_prices`, serializers drop the price fields, the change log
hides old and new values of price fields (`audit_sensitive` on the model).
A model may hide more of a single entry
(`audit_hidden(entry, rights)`, asked by `core.history.visible_changes`):
`customfields.CustomFieldValue` hides both value columns of every entry of
a field that is sensitive now, so values logged before the field was
marked sensitive do not show either (MAT-071).

**Availability of material** is a special right
(`SpecialRight.AVAILABILITY`, AUT-032): templates ask
`can.special.availability`, views compute the availability only then, the
planning and line API return `availability` and `shortage_total` as
`null` without it, and `/availability`, `/shortages`, `/utilization`,
`/products/{id}/availability` and the timelines answer 403. Shortage
notifications go only to recipients with the right who read the
planning. The stock of a product and the fleet are not gated.

### Rights in a single project (AUT-016 to AUT-018, AUT-025)

Module rights say what a user may do with projects *in general*. For roles
whose project scope is "assigned projects only" (AUT-017), a second question
is asked for every single project: is the user assigned to it, and at which
level? `projects/access.py` answers it, and nothing else does.

- `Rights.level(module)` is the highest level the user has anywhere;
  `Rights.level_everywhere(module)` is the level that holds in every
  project. They differ only for the project-bound modules (projects,
  packing) and only for roles with the scope "assigned".
- A user is **assigned** through a `ProjectMembership` (explicit, with a
  level: deployment, read, edit – in a subproject also "no access") or
  through a crew line of the person linked to the account (automatic,
  deployment view only – AUT-018).
- `access_level(rights, user, project)` combines both:
  `max(everywhere, min(role level, assignment))`. A membership therefore
  never gives more than the role allows.
- **Role limit** (AUT-031): the role level is `role_limit(rights)`, taken
  from `Rights.level_of_planning()`: for the project scope
  `deployment` ("assigned projects only, overview without planning", the
  start role Crew) it is the deployment view, whatever a membership names
  – overview with the phases, packing list and chat; planning, schedule,
  access, history, documents and subprojects answer 403 or lead to the
  overview. `Rights.reads_planning` hides "Offene Punkte" and the
  shortages from such a user everywhere (tab, page, start page, API).
- **Service cases** (AUT-033): the person responsible for a service case and
  the people taking part get *read* in it whatever their roles say
  (`works_on_case`, `Rights.case_work`), and may change it where a page or
  endpoint allows it: the case pages and endpoints load it with
  `project_for(..., case_work=True)` and check at the door with
  `case_work.case_work_required` (pages) and `CaseWorkPermission` (API)
  instead of the plain module check. Correspondence of projects still
  needs the special rights.
- **Correspondence** (EML-055): the correspondence has a reach of its own,
  answered by `mail/locks.py` (`correspondence_for`, `correspondence_of`
  for a request): the *basis* is read access and
  "read correspondence", or working on the service case; with it a user
  reads open messages, and messages with a lock only with "See prices and
  calculation" too; without it a user with at least the deployment view
  whose person has a confirmed crew line in the project – accepted or
  planned firmly (`locks.CONFIRMED_REQUESTS`, `planned_in`) – reads the
  open messages (`Reach.OPEN`, read only). Every page, endpoint, the search,
  the subrental pages and the notifications filter by
  `Correspondence.readable` (a queryset) or `Correspondence.may_read`; a
  message the user may not read answers 404.
  The tab "Korrespondenz" asks the template tag `reads_correspondence`.
  The history of a project (page and API) names a mail or note by its
  subject only to a reader of that message (`mail/history.py`,
  `hide_unreadable`, applied when shown); automations never take the
  subject of a locked mail into a run ("Mail von … (mit Schloss)"); an
  answer to a locked message starts locked (`locks.answer_lock`), an
  incoming reply to one is stored locked (`locks.answers_locked`). See
  core-flows, section 8.
- **Access list** (AUT-035): the tab "Zugriff" lists every assigned user
  with the access that really holds: `projects/access_rows.py` asks
  `access.access_of_users` – the rules of `access_level` for many users at
  once, three queries in all; a test compares both for every row. An
  account that cannot log in (`accounts.data_access.can_log_in`: inactive,
  without a usable password, or past its `valid_until` before the nightly
  job deactivated it – `User.has_expired`) has no access there, "kein
  Zugang – kann sich nicht anmelden", as in the data-access columns
  (AUT-034).
- **Every** browser view and API endpoint that shows something of a project
  loads it with `project_for(request, pk, minimum)` – or, for the packlist,
  `packlist_project_for`. A project the user may not see answers 404, the
  same as one that does not exist; a project the user sees but may not do
  this with answers 403. Lists use `visible_projects()` or
  `readable_projects()`. Nested API resources check in
  `ProjectChildViewSet.initial()`, before any operation runs, so that no
  operation can forget it.

**Subprojects** (PRJ-049). A membership of a whole project
holds in each of its parts. A membership of a part replaces it there –
for more or for less, down to the level "no access"
(`ProjectAccessLevel.NONE`, offered only on parts). A membership of a part
alone opens neither the whole project nor the other parts, and a crew
line gives the deployment view of its own project, also against "no
access". Roles for all projects are not affected. `assignment_of` decides
it for one project; `assigned_filter` and `readable_projects` express the
same rule with subqueries, so a list still asks nothing per row, and
`access_of_many` needs one query more, for the parents. `project_for`
loads the answer to "has parts?" together with the project
(`with_parts_flag`). Whoever may read a whole project but not all its
parts sees its tab "Teilprojekte", its price overview and its packlist
without those parts, and cannot make its priced documents (see
[decisions.md](decisions.md), Part 10).

`tests/ui/test_crew_pages.py::NoPageForgetsToAskTests` walks every address
below a project as a user with a strong role but no assignment, by `GET` and
by `POST`, and expects 404 everywhere. The addresses are read from the URL
table, so a page added later is walked too.

None of the levels includes prices, costs or correspondence; those come
only through the special rights of the role (AUT-019, AUT-025).

### Personnel and time data (NFA-010)

- Hourly rates and personnel costs need the special right
  `PERSONNEL_COSTS` – in pages, API fields, CSV, PDF and the change log
  (`audit_sensitive`). A person may see their own rates unless the setting
  "people may see their own hourly rates" is switched off (PER-010).
- Time entries: everybody sees and records their own. Seeing those of
  others, recording for others, approving and rejecting need the special
  right `APPROVE_TIMES`, and then only for projects the user may see
  (`timetracking.services.visible_entries`).
- Contact data of colleagues in the deployment view follow the person's own
  release (`share_phone`, `share_email`, PER-019).

## The change log (ADM-005)

Every model that inherits from `core.audit.AuditedModel` writes a row to
`AuditLogEntry` when a record is created, changed or deleted, with the old
and new value of every changed field. *Who* did it is not passed around: the
middleware (or `with acting_as("system:import")` in commands) keeps the
current actor in a context variable. No code path can forget to log.

The known trap is written at the top of `core/audit.py`:
`QuerySet.update()` and `bulk_create()` bypass `save()` and therefore the
log. Business code uses them only where that is wanted.

The history shown at a project or an item (`core/history.py`,
`material/history.py`) is this log, filtered and put into words. A field
that is a reference is stored as the ID and looked up for display
(`core.history._Lookup`). A stored value that is not an ID –
for example "D-001 …" for service products – is shown as
text instead of breaking the page (ADM-005); data migrations log IDs.

Since 0.5 the log can be limited in time (`retention_change_log_days`,
NFA-011; 0, the default, keeps it for good); the daily maintenance removes
older rows (`core.audit.delete_old_entries`).

## Shared machinery in `core`

There are four things every module uses in the same way, and
four more (from "Readable addresses" on). Each lives in `core` and
knows the modules only through what they register or what their addresses
are called.

### Lists as tables (`core/tables.py`, UIX-015, IMP-005)

A list page describes its table once, in the `tables.py` of its module: a
`TableDefinition` with `Column`s – key, heading, how the cell looks, what
goes into the CSV file, which model fields it sorts by, whether it is
shown by default, and `visible_if` for columns that need a right (prices,
personnel costs). The rest is shared:

- **Which columns** a request shows: `?cols=` in the address, else the
  user's saved choice (`core.TablePreference`), else the defaults. Fixed
  columns (the ID of an item, the number of a project) are always there.
  The column chooser posts to `core:table_columns`; "Default columns"
  forgets the choice.
- **Sorting** by `?sort=name` or `?sort=-name`; an unknown key falls back
  to the default sort. (UIX-015, UIX-040) **every column
  sorts**: `Column.sort` is model fields, lookups or query expressions
  (`F`, `Subquery`, annotations – volume L×W×H, the first value of a
  multi-valued column via `first_value`, an item's effective product);
  `Column.sort_prepare` adds the annotation a sort needs; a value that
  exists only in Python sorts in Python (`TableState._order_in_python`,
  with `natural_key` so "5 m" comes before "10 m") for at most
  `PYTHON_SORT_MAX_ROWS` (2,000) rows – a longer list keeps the default
  order and sets `TableState.sort_notice`, shown above the table
  (`core/_table.html`). Only a column of buttons or tick boxes may say
  `Column.unsortable = "<reason>"`; `tests/unit/test_082_cleanup.py` walks
  every `TableDefinition` and fails on a column that neither sorts nor
  names a reason. The CSV follows the chosen sort.
- **CSV** with `?format=csv` (the shown columns) or `?format=csv&cols=all`
  (every column the user may see), all rows of the filtered view up to
  `CSV_MAX_ROWS` (100,000), semicolon and decimal comma, with a byte order
  mark for spreadsheet programs. Text that a spreadsheet would run as a
  formula gets a leading apostrophe (CSV injection).
- **Groups** (UIX-040) with `?group=<key>`, only by a column
  that declares `group` – a model field or lookup path for a queryset
  (`"status"`, `"customer"`, `"date__date"`), or a function for a table
  over computed rows; `group_value` and `group_label` adapt a transform
  and name the heading. Grouped, the rows are sorted by the group first
  (fixed-choice fields in the order of their choices, links by name), then
  by the chosen column; the first row of each group – and of each page –
  carries a `GroupHeading` with the count of the group in the whole
  filtered list (one extra aggregate query). The CSV is never grouped, and
  columns with `export=False` (buttons, tick boxes) are left out of it.
  Nothing is stored per user: like sorting, grouping lives in the address,
  and the "Gruppieren nach" form repeats the page address as hidden
  fields. Several tables on one page take a prefix (`param()`), e.g.
  `runs_` on Automationen.
- **Entries per page** (UIX-050): `TableState.paginate` (or
  `core.listing.paginate` for a list without `TableDefinition`) takes
  `?per_page=` – 25, 50, 100, 200 or any whole number from 5 to 1,000 –,
  else the number remembered in `TablePreference.page_size` under
  `listing.list_key` (the URL name of the page, plus the table prefix),
  else the list's default (50). A number accepted from a `GET` is
  remembered; one out of bounds is refused with a message next to the
  field and the list keeps its length. `core/_pagination.html` shows the
  links and the field "Eigene Anzahl" as a GET form that repeats the
  other parameters. `PageSizeMiddleware` deletes the former cookie.
  `tests/unit/test_092_ui.py` walks every user of `core/_table.html`;
  tables that are a form or a sum as a whole are listed exceptions.
- **Columns from the database** (MAT-073):
  `TableDefinition.add_column_source(source, prepare=…)` adds columns
  known only when a page is shown – the custom fields marked "in lists"
  of the item list (`customfields/tables.py`, registered in
  `customfields/apps.py`); `all_columns()` returns the table's own columns
  and then theirs.
- **Plain text of stored texts** (UIX-005): `plain_text(value)`
  takes the tags out first and turns entities back (`&amp;` → `&`)
  afterwards – never the other way round, which would take an escaped
  `&lt;max@example.org&gt;` for a tag. A safe string (markup made by
  Rentalars) goes through `strip_tags`; a stored text such as the body of
  a notification loses only real tags (`_MARKUP`: a known HTML element
  whose attributes all have a value, and comments), so
  `Max <max@example.org>` or `a<b und c>d` stay.
  `text_lines` makes cell content of it with its line breaks (the list of
  notifications, the descriptions of project templates).
- **Every shown column groups** (UIX-044):
  `Column.groupable` is true unless the column says `ungroupable` or
  `unsortable` (buttons, tick boxes); `TableDefinition(ungroupable=…)`
  takes "Gruppieren nach" off a whole table with a reason (time approval,
  the sums of the hours report). A column without `group` groups in Python
  by the value it shows (`_shown_value`: its `text`, or the cell without
  markup) – `_group_in_python`, with `_in_order_of` and `_order_queryset`
  keeping the group where its first row stands in that column's sort (one
  extra `pk` query for database-sorted columns) – for at most
  `PYTHON_SORT_MAX_ROWS` rows; a longer list stays ungrouped and gets a
  notice in the same `sort_notice` slot (`_add_notice`). Moments group by
  their local day (`grouped_by_day(path)`), periods by their first day.
  `group_choices()` offers the shown columns in their order, plus a chosen
  column hidden since. `core/admin_tables.py` does the same for the Django
  master-data lists: a field groups by itself, a computed column by its
  `admin_order_field`, annotated as `table_group_value`; headings use
  `display_for_field`. `tests/unit/test_083_tables.py` walks every
  `TableDefinition` and fails on a shown column that neither groups nor
  names a reason. The AI call log is a plain paginated table on purpose.

Nearly every list page is such a table; the new definitions
sit in modules of their own where `tables.py` was taken:
`projects/case_list_table.py` (Servicefälle), `projects/case_tables.py`
(Mein Bereich → Servicefälle), `projects/template_tables.py`,
`projects/open_item_tables.py`, `timetracking/expense_list_tables.py`
(Spesen, Meine Spesen; sorted and grouped in Python),
`automations/list_tables.py` (rules and runs), `api/webhook_tables.py`,
`material/inspection_tables.py`, `notifications/list_tables.py`,
`availability/shortage_tables.py` (three tables), `core/job_tables.py`,
`schedule/follow_ups.py` (Wiedervorlagen) and the roles and security log
in `accounts/tables.py`; the Anfragen in `mail/tables.py` use their own row
template. Not tables: Meine Zeiten, Freigeben, Auswertung, the change log,
rental scales, Personal → Verfügbarkeit, small lists and tables inside a
detail page.

A cell is HTML made with `format_html`, never by gluing strings. A column
the user may not see is neither shown nor exported nor offered.

Also `projects/my_deployments.py` (Mein Bereich → Meine
Einsätze, UIX-043; its "Stand" column sorts by the view's annotation
`deployment_state`; it
groups in Python like every computed column).

**Filters** (`core/_filter_panel.html`, block UIX-030/038 of `app.js`) are
folded on every page load at every width (UIX-038): the open
state remembered in `localStorage` is ignored and deleted; a
filter with an error still opens; folded, the button reads "Filter (n
aktiv)" (`data-filter-active`) and chips name the active filters. The
Django master-data admin uses `templates/admin/filter.html`, which renames
the attribute `admin/js/filters.js` looks for, so Django does not reopen
them, and shows the chosen value in the folded heading.

### Imports (`core/tabular.py`, `core/imports.py`, `core/import_views.py`, `core/import_api.py`)

Material, products, customers and people are imported the same way
(IMP-001 to IMP-004):

| File | Contents |
|---|---|
| `tabular.py` | reading an XLSX or CSV file into a `Table`; `ImportField` (key, label, required, aliases) and the column mapping by heading; `ImportReport` and `ImportIssue`; parsing of dates, numbers, yes/no and choices; `fold()` (case- and accent-folding of a heading or name) |
| `imports.py` | the registry of `ImportKind`s (key, title, module whose write right is needed, fields, `run` function); the upload folder `DATA_DIR/imports`; starting a dry run or an import as a task in the background |
| `import_views.py` | the one import page for all four kinds (`/import/<kind>/`, material also at `/material/import/`): upload, mapping, dry run, import; the page asks every two seconds while the task runs |
| `import_api.py` | `/api/v1/imports/{kind}`: `GET` lists fields and recognised headings, `POST` imports in the request (at most `MAX_IMPORT_ROWS_PER_REQUEST` = 5,000 rows) or, with `background`, as a task without limit |

A module brings only its `importer.py` – the fields and the function that
checks and writes the rows – and registers it in `AppConfig.ready()`:

```python
imports.register(imports.ImportKind(key="customers", title=importer.TITLE,
    module=Module.CUSTOMERS, fields=importer.IMPORT_FIELDS, run=importer.run_import, …))
```

Every importer follows the same rules: all rows are checked and written in
one transaction, which is rolled back on any error and always for a dry
run (IMP-009); the prices of products, the discounts of customers and the
hourly rates of people are refused without the right to see them; the
change log names the importing user, or `system:import` on the command
line, and records a completed import as one event with its counts –
`import.material`, or `import.records` with the kind for products,
customers and people. The command `import_data` uses the same registry;
`import_material` stays for the material list.

**The export in the import format** (IMP-017,
`core/import_exports.py`). Each module describes the export of its import
in its `import_export.py` – an `ImportFormatExport` with an `ExportColumn`
per key of the import's fields and a function yielding chunks of rows –
and registers it in `ready()`; `register_columns` lets another module add
columns, as `customfields` does with a column per custom field (one
counted by its heading). `import_format_export` (`/import/<kind>/export/`)
and `ImportExportView` (`GET /api/v1/imports/{kind}/export`) need read
access to the import's module; a column whose `right` the user lacks is
left out. `stream()` writes the heading row and then one piece per chunk
of `CHUNK_ROWS` (2,000) records under `translation.override("de")`, as a
`StreamingHttpResponse` – a fixed number of queries per chunk. `cell()`
writes dates `31.12.2027`, decimal commas without thousands separator,
"ja"/"nein", and an apostrophe before text that would start a formula;
`core.tabular.cell_text` takes that apostrophe away on import, and
`core.tabular.choice_of` accepts the German label in every language, so
that the round trip changes nothing (tested per kind in
`tests/unit/test_092_exports.py`).

### Tasks in the background (`core/jobs.py`, NFA-041)

```python
jobs.register("labels", "rentalars.material.labels:run_job")  # in AppConfig.ready()
job = jobs.start_job("labels", params, user=request.user, title="…")
```

`start_job` stores a `core.BackgroundJob` and, once the transaction has
committed, starts `manage.py run_jobs --job N` as a detached process. Its
output goes where the output of the starting process goes – the journal of
`rentalars.service` for a task started from a page. The process notes host
and PID in `params["worker"]` and runs the runner, which gets the job, may
call `report_progress(job, percent)` and returns

- `(bytes, file name)` for a download,
- `(Path, file name)` for a large result it wrote to a temporary file –
  the file is moved into place, not read into memory (the full export),
- or a text for the result message;

and it may set `job.result` to keep data, such as the report of an import.
An exception marks the job as failed with the error as message. The one
who started it is notified either way (`Kind.JOB_FINISHED`).

`run_jobs` without `--job` first calls `recover_interrupted_jobs()`, then
runs everything still waiting. `rentalars-jobs.timer` starts it every
minute (`rentalars-jobs.service`: oneshot, `Nice=10`, up to six hours), so
a process that could not be started costs a minute, not the task. A
"running" job whose process is gone – checked by PID on the same host; on
another host a job counts as lost after `STALE_AFTER`, two hours – is
queued once more; the second time it is marked failed ("The task was
interrupted."). Every kind can run twice safely: an import writes all or
nothing, labels and export make their file anew. In tests
(`JOBS_RUN_INLINE`) a job runs at once, inside the request. Finished jobs
are removed with their files after `retention_jobs_days`.

**A gate per kind** (NFA-076):
`jobs.register(kind, runner, gate="module:function")` names a context
manager that yields whether a task of the kind may run now. `run_job`
claims the job and, for a kind with a gate, calls `_run_gated`: without
the gate the job goes back to `queued` (`started_at` emptied) and the
process ends; with it, the process runs the job and then the other
waiting jobs of the kind, oldest first (`_claim_next`), before it lets go
– and tries once more for a job queued while it let go. Only `chat_video`
has one (`chat.media.conversion_slot`, a non-blocking `flock` on
`DATA_DIR/chat-videos.lock`): one conversion at a time per server. The
kernel releases the lock when the process dies, so after a crash the
minute timer (`run_waiting_jobs`) runs what is left. Kinds without a gate
run side by side as before.

Only the user who started a task sees it and fetches its result, in the
browser and through `/api/v1/jobs/{id}` (`_own_job` in `core/views.py` and
`core/api.py`); administrators do not see the tasks of others. A result
can hold the data of everybody.

Registered kinds: `import`, `export` and `backup` (`core`), `labels`
(`material`), and `lexware` (`documents`: one invoice or
cancellation to Lexware Office, DOK-011), `ai_summary` and
`ai_draft`, `ai_invoice` (`ai`), `chat_video`
(`chat`: one video made smaller; started without a user, a failure is told
to the sender by `chat.media`, not as a failed task; behind a gate, one at
a time). The same minute timer also runs
the calendars of the people (`personnel.calendars.run_due`, PER-022,
PER-023) after the waiting tasks, and then, the webhook
deliveries that are due (`api.webhooks.run_due`, API-012: at most 30
seconds or 200 deliveries per run); a failure in either never stops the
tasks. It tells the people whose follow-up is due,
it carries out runs of automations still waiting (`_run_pending_automations`
→ `automations.engine.run_pending`, ADM-013), at most 100 per run. Runs are
normally carried out at once, by `transaction.on_commit` after the change
that recorded them; the timer is the net for a restart in between. The
daily maintenance also deletes runs of automations after 365 days and the
map positions of addresses no record uses any more (UIX-034).

### The full export (`core/export.py`, IMP-006)

Every table as JSON (Django's serialization format) and as CSV, every
stored file and a `LIESMICH.txt`, in one ZIP file. Left out are the secret
fields (`SECRET_FIELDS`: password and token hashes, two-factor secrets,
mail passwords, the setup token, the calendar links and CalDAV passwords
of people, the API key of Lexware Office, the
token of a deployment request sent by mail – whoever has it can answer the
request –, the token of the calendar link of a product, model
or item) and technical tables
(`EXCLUDED_MODELS`: sessions, login attempts, background jobs and Django's
bookkeeping, and the webhooks with their deliveries – an
address may itself be a secret link), and the folder `jobs/` of task
results. It runs as a background task of kind
`export` (only for the administration with delete right; the result only
for the one who started it) or with the command `export_data`; both record
the event `export.full`. `LIESMICH.txt` explains how to load the JSON files
into a freshly installed Rentalars of the same version
(`rentalars loaddata json/*.json`, files from `dateien/` into the media
folder). (IMP-006) the button is a section of the page
"Sicherung" (`core:backup`, `#export`), which says how the export differs
from a backup; the view is `settings_views.full_export` at
`/administration/backup/export/`, and the former address,
`/administration/export/`, redirects there permanently. The chat media
below `media/chat/` are in it like every stored file.

### Readable addresses (`core/converters.py`, UIX-024)

Projects and products are addressed by their number: `/projects/2026-0042/`,
`/products/L-010/`. URL patterns write `<project:pk>` and `<product:pk>`;
the converters turn the number in the address into the primary key, so
views and services keep working with keys, and turn whatever `reverse`
gets – the object, its key or its number – into the number. A bare key
(`/projects/42/`, older links) is still accepted. The numbers
found are kept for the request, and after three single lookups all are
read at once, so a list page does not ask once per row (NFA-012). A number
with characters that are not safe in a path is written as the key. The
API keeps its keys. (ADM-012) the project converter also
accepts a former number (ADM-014), the one with "P-"
(`/projects/P-2026-0042/`): after today's numbers and before the bare key
– `0042` of an installation with an empty prefix is a number, not a key –
it looks for a project with that `former_number`, case ignored, only for
a value that can be one (`projects.numbers.may_be_former`: letter-free, or
"P-" plus letter-free), and notes the pair for the request
(`former_numbers_in_address`); `FormerNumberRedirectMiddleware` then
redirects a page request to today's address.

### Pages that follow changes (`core/changes.py`, UIX-020)

`base.html` names what a page shows as keys (`data-watch`, from
`changes.watch_keys`): always `notifications`, plus `project:<pk>` on every
page of a project, or `mail:unknown` on the list of inquiries and unknown
tags (Projects → Inquiries).
`app.js` asks `GET /changes/?keys=…` every 20 seconds and when the page
becomes visible again; the answer is a stamp per key – for a project the
newest change-log entry of the project or with the project as parent – and
the number of unread notifications for the bell. A changed stamp reloads
the page at the same scroll position, unless the user is typing (or typed
in the last 15 seconds), has a dialog or the menu open, or has selected
text; then a note offers to reload. After the page's own changing
requests the stamps are taken over, so one's own saving never reloads the
page. The question costs one or two indexed queries.

(PER-033) the stamp of a project reads `<newest change>.<newest
change by somebody else>` (e.g. `123.120`; both `Max` over the same rows,
the second filtered by `actor_id`, one query). After its own change the
script (`app.js`, UIX-020 block, `othersPart`) compares only the second
part and reloads if it moved – so an answer to a crew request that came in
seconds before is not swallowed –, and compares the whole stamp at the
regular question, so a change by the same user in another tab or the app
still reloads.

(UIX-010) every page of a project also watches `chat:<pk>`
(`PROJECT_NAMESPACES` includes `chat`). Its stamp is `<content>~<unread>`
(`chat.services.stamp`, one aggregate query, empty for a user who cannot
open the project). `pollChanges` never reloads a page for a `chat:` key; the
block UIX-010 of `app.js` listens to the event `rentalars:stamps`, puts the
unread part into the badge of the tab "Chat" and, on the chat page, fetches
the messages in place when the content part moved. So the chat needs no
websocket and no faster polling.

(UIX-010, UIX-020) the chat's content part is
`<newest>-<count>-<sum of revisions>` (`ChatMessage.revision` counts
edits), so two edits within one second – or an edit of an older message –
move it. The other stamps (project:
newest change-log ID; `mail:unknown`: newest ID plus count;
notifications: count) never depended on time. And packlist pages watch
**`packing:<pk>`** (`core/changes.py`, only there, so the planning page does
not reload every 20 seconds while the warehouse packs): the sum of
`PackEntry.version` and the row count, without a "." part, so one's own
tick does not reload while a colleague's or the app's does.

### The access log (`core/access_log.py`, AUT-028)

`AccessLogMiddleware` looks at every successful `GET` after the view
answered, at the name of the address and its arguments: projects through
the converter `<project:pk>`, everything else through a table of address
names (`NAMED`); any other answer that is a CSV file counts as the export
of a list; downloads of the full export and of a backup are recognised by
the kind of their task. Not logged: static files, htmx requests,
failed requests, lists without export, a person's own data, and commands on
the server. The same user reading the same record the same way within
five minutes is one entry (`DEDUPLICATE_WITHIN`); the first read costs
one query and one insert, a repeat nothing, thanks to a small cache in the
process. Entries (`core.AccessLogEntry`) carry the project as parent for
mails, attachments, files and documents, and are removed after
`retention_access_log_days` (180).

### A backup from the browser (`core/backup.py`, ADM-009, ADM-010)

"Sicherung jetzt erstellen" starts a task of kind `backup` that writes the
same archive as `deploy/backup.sh` – `database.sql`, `rentalars.conf`,
`VERSION`, `media/` – so that `rentalars restore` takes it. It runs under
the service account without any right of root: `mariadb-dump` with the
access data of the configuration through an option file of mode 600, on
SQLite the backup API. The archive is written next to the data, read back
completely and only then moved to `media/jobs/backups/`, where it is
delivered to whoever made it and deleted with the results of tasks;
`backup.sh` leaves that folder out. With `[backup] encrypt = true` the
archive is encrypted while it is written, with a key of its own made for
it (the recovery key belongs to root), in the format of `openssl enc` that
`backup.sh` uses (`OpenSSLWriter`); the key is stored encrypted with the
task and shown to its maker only, as long as the backup is kept.
`encryption_state()` collects for the same page what the application can
see of the encryption (database, new backups, last nightly backup,
recovery key); switching it on stays `rentalars encryption enable` on the
server.

## Logistics (LOG)

Vehicles and trailers are **material**: items of material models whose
product has the kind "vehicle" (LOG-002). So inspections (HU, UVV as
inspection types), blocked periods, defects, files, labels and the timeline
of an item apply to them unchanged; `material.Vehicle` adds what only a
vehicle has. They are **not stock** for the availability engine
(`ProductKind.MATERIAL_KINDS` leaves them out) and never a material line:
`projects.services` refuses a vehicle product as a line and points to
"Logistik". Their availability is the overlap of bookings
(`logistics.overlapping_ids`, `material.fleet.bookings_for`), as the crew's
is the overlap of deployments – a hint, nothing is blocked (LOG-004).

| File | Contents |
|---|---|
| `projects/logistics.py` | the services (book, change, delete; put a vehicle on a trip, with or without trailer), the prices (`price_logistics` → one `VehiclePrice` per booking), the warnings (`logistics_warnings`: booked elsewhere, blocked or not fit for use, inspection due, seats, licence class, towing capacity, trip gone), following phase and project (`move_with_phase`, `follow_project_period`), the rights per field (`PRICE_FIELDS`, `COST_FIELDS`, `TRIP_PRICE_FIELDS`) |
| `projects/logistics_forms.py`, `logistics_views.py` | the block "Logistik" of the planning: the add row, the dialogs of a booking and of a vehicle on a trip, answering with the refreshed blocks "Personal" and "Logistik" and the totals like the crew (UIX-009); `trip_route` asks the route service |
| `projects/logistics_api.py` | the same over the API (API-002): `/projects/{id}/logistics`, `/projects/{id}/trips/{key}/vehicles`, `/projects/{id}/trip-vehicles/{id}`, `/projects/{id}/trips/{key}/route` |
| `material/fleet.py`, `fleet_views.py`, `fleet_tables.py`, `vehicle_api.py` | the fleet: vehicle data of an item, the list "Fuhrpark", the utilization (the schedule's `Scale` and `Bar`), taking a model kept as material into the fleet (LOG-016), `/vehicles` |
| `core/routing.py`, `deploy/route.sh` | the optional route service (LOG-017): Routino on the server or an OSRM server, named in `/etc/rentalars/route-local.conf`; without it the kilometres are typed in |

**Prices.** `price_logistics` is called by `projects.pricing` next to the
crew, so the logistics is part of every figure that comes from there: net
total, the base of whole-project surcharges, discounts, the capped count,
margin, tax lines – and therefore the price overview, the documents
(section "Logistik" in `documents.content`, the XRechnung), the project
list's sums and the profitability. A motor vehicle is charged per trip:
kilometres (driven, planned, or a flat price – `TripVehicle.billing`) ×
(price per km + trailer surcharge when a trailer is pulled on that trip,
LOG-006). A trailer is charged per km of the trips it is pulled on, or per
day – rental days and scale as a material line, or with `only_trip_days`
the days with trips. The costs (LOG-010): cost per km and day of own
vehicles, the supplier's cost of a subrented one.

**Trips** are not stored: `projects.trips` derives them from the phases and
the venue, plus those changed or added by hand (PRJ-097, PRJ-111). A vehicle
on a trip names the trip by its key, so a copied project maps
`to_venue-<phase>` to its copied phase (`duplicate._copy_logistics`), and a
trip that disappears leaves its rows with a warning instead of losing them.

## Documents (DOK)

The package `documents` makes offers (DOK-010), order
confirmations, delivery notes, invoices, cancellations and crew
dispositions and keeps them for good (DOK-003 to DOK-008). It is cut like
this:

| File | Contents |
|---|---|
| `content.py` | puts together what a document shows, as plain data (`DocumentContent`: company, recipient, positions in sections, taxes per rate, texts); amounts come from `projects.pricing` – an offer and an order confirmation show optional and alternative groups and lines (PRJ-075) marked and without adding them up, an invoice leaves them out (`priced_sections(with_optional=False)`) –, the service period is the reservation period of the project; the delivery note comes from the packlists, the crew disposition from the crew lines; a crew line's details name its surcharges for night, Sunday and holidays ("inkl. Zuschläge …", PER-009) |
| `pdf.py` | the PDF, made with WeasyPrint from `templates/documents/document_pdf.html`; letterhead and address window after DIN 5008, fonts and logo from the installation |
| `xrechnung.py` | the invoice as XRechnung 3.0 in UBL 2.1 syntax (EN 16931); `missing_data()` names what the company profile or the customer lacks before an invoice is made; the customer's Leitweg-ID or buyer reference goes into `BuyerReference` (BT-10), else the project number; a cancellation is a corrected invoice (type 384) with negated amounts |
| `services.py` | making (`create_document`), previewing, cancelling, noting that a document was sent, verifying the checksum; a part refuses priced documents (`part_problem`), a whole project's need sight of all its parts (`check_parts_readable`); invoices and cancellations only while "Rentalars als Buchhaltungsprogramm verwenden" is on (`invoices_enabled`, `check_invoices_enabled`, `makeable_kinds`, DOK-014) |
| `views.py`, `api.py` | the tab "Documents" of a project and the API; the tab also holds the project's files (`render_document_list`, PRJ-079), and the offer form takes "Umfang" and the validity in days (DOK-013) |
| `deployment.py` | the deployment view as PDF "Einsatzübersicht" – not stored, no number; the viewer's view from the tab, the neutral one as mail attachment (PRJ-081) |
| `admin.py` | templates and text blocks in the administration |
| `lexware.py` | an invoice or cancellation to Lexware Office as a voucher with its PDF – the HTTP client, the bodies of voucher and contact, the transfer and its task in the background `lexware` (DOK-011) |
| `datev.py` | the invoices of a period as DATEV Buchungsstapel, and their customers as Debitoren (DOK-012) |
| `accounting_views.py`, `accounting_forms.py`, `accounting_api.py` | the page Settings → Accounting and its API: settings, checking the connection, the list of hand-overs, the DATEV export |
| `statements.py`, `statement_views.py`, `statement_api.py` | the monthly statement of service cases (DOK-016) – collecting a customer's cases of a month with their times (priced per job function as crew lines are), expenses and activity texts, the draft, the invoice made of it (one section per case, `Document.billed_projects`), marking as invoiced elsewhere; cancelling the invoice makes the statement a draft again; under Buchhaltung (`/accounting/monthly/…`) |
| `outgoing.py`, `outgoing_tables.py`, `outgoing_views.py`, `outgoing_api.py` | "Buchhaltung → Ausgangsbelege" (DOK-020) – every document a customer got (offer, order confirmation, delivery note, invoice, cancellation; no crew disposition) as a table of `core/tables.py` with 17 columns (9 shown at first), the filters kind (also `bookable`, `monthly`), state, Lexware, customer, project, period and text, and the sums of all filtered documents per kind with "Rechnungen und Stornorechnungen zusammen" – always the amounts stored with the document (DOK-007). For whoever sees prices and reads every project (`outgoing.may_see`); the tabs of the menu entry "Buchhaltung" (`documents/_accounting_tabs.html`, `outgoing.tabs`) show what the user may see (DOK-019) |

The content is built **once**: the same `DocumentContent` is stored with
the document as JSON and rendered into the PDF and, for an invoice, into
the XRechnung, so the two files cannot disagree. A cancellation is built
from the stored content of its invoice (`content.from_json`, `negated`),
not from the project as it is now. The model refuses every later change
(see [data-model.md](data-model.md), "Documents"); how a document is made
is in [core-flows.md](core-flows.md), section 10.

**A whole project is billed as one** (PRJ-045, PRJ-046).
`content.build_priced` takes the plannings of the whole project and of
every part that is not cancelled from `projects.family_prices` and puts
each part into a block of its own; the sum adds the net per tax rate of
all of them. The **accounting** reads the stored content, never the
project: Lexware Office and DATEV get the amounts per tax rate of the
stored document, so they agree with the PDF and the XRechnung to the
cent. Making an invoice or cancellation starts its hand-over to Lexware
Office when the settings say so (`services._to_accounting`), as a task in
the background that never stops the document ([core-flows.md](core-flows.md),
section 13).

## The user interface (UIX)

Pages are rendered by the server from Django templates; there is no
JavaScript application. Three small tools make the pages feel direct:

- **htmx** sends small requests and puts the returned HTML into the page.
  The planning page of a project works this way: adding a line posts a
  form and gets back the parts of the planning that changed
  (`projects/views.py`, `_planning_response`).
- **SortableJS** for dragging lines into another order or group, and
 groups into other groups (PRJ-037).
- `static/js/app.js`, about 4,000 lines: the dialog, the
  type-ahead search fields – which can also offer to create a customer or
  venue in the dialog (PRJ-070) –, the confirmation before deleting, the
  running stopwatch, ticking many rows at once (MAT-029) and sorting small
  tables without pages in the browser (UIX-015); also the
  questions in a dialog of the page and short messages instead of `alert`
  (UIX-018), periods whose end follows the start and a calendar to pick
  them (UIX-025), pages that follow changes (UIX-020, above), the people
  of the chosen job function (PER-025), the address suggestions and the
  signature editor of the mail (EML-034, EML-037), the week grid and the
  hour columns of the planning (VFG-021, VFG-022) and the choice of
  products for a lighting plot (PRJ-077); also moving groups
  by dragging or with the arrow keys of their handle and folding their
  subgroups (PRJ-037); the selection of several lines and its
  bar (PRJ-082), choosing a phase that fills "Von"/"Bis" (PRJ-080), date
  and days of an offer kept in step (DOK-013), the buttons "Crew/Kunde
  hinzufügen" (EML-043), the status form of the project head and small
  menus (`<details class="menu">`) that close on a click elsewhere or
  Escape (PRJ-078), and combobox roles on every type-ahead field
  (VFG-025); the entry "Neue Phase …" in the phase lists of
  the crew forms with its own stacked dialog `#phase-dialog` and the event
  `phaseCreated` (PRJ-094), and the filters that fold away (UIX-030);
  the block "UIX-036 … PRJ-099" at the end – one picker for
  every `date`, `datetime-local` and `time` field (the field wrapped in
  `.dt-wrap` with a button `.dt-btn`, a dialog with the calendar and a
  clock face as `role="slider"`), arrow keys in every calendar, the
  hatched periods with their legend read from `[data-calendar-marks]`, and
  `window.Rentalars.calendar` / `window.Rentalars.enhancePickers`, which
  the UIX-025 range picker uses for the same marks and its time fields –,
  in the PRJ-094 block `keepDialog` (the dialog stays open for the
  question of PRJ-100) and the event `rentalPeriodChanged`, conditions
  with `&` and `;` in `conditionHolds` (UIX-035), and the project stamp
  compared in parts in the UIX-020 block (`othersPart`, PER-033); the block for material – one serial number field per new
  item (`[data-serial-numbers]`, MAT-050) and the reload of a new
  product's form with kind and category (`data-reload-fields`, PRD-046) –,
  the block PRJ-101 – the "create" form of a type-ahead inside a dialog
  opens in a second dialog `#create-dialog` on top (event
  `typeaheadCreate`, dispatched by `choose()` of the type-ahead; saving
  closes only that dialog) –, and in the UIX-030 block filters that start
  folded on every width (UIX-038); two lines in `pollChanges`
  (the event `rentalars:stamps`, `chat:` keys never reload) and five blocks
  at the end: "UIX-010 … ADM-013" – the chat (unread badge, messages
  fetched in place, the list of names after "@" as a listbox, Ctrl+Enter)
  and the form of an automation (`data-show-when`, `data-actions-of`,
  `data-recipients-of`) –, "UIX-034, PRJ-097" – "Karte anzeigen" loads
  Leaflet the first time and draws the places; "Position korrigieren" by
  click, dragging the marker or the typed fields –, "PRJ-089" – the type
  and console of a show file picked from its ending
  (`data-show-endings`) –, the ZEI-019 reload after an expense
  (`data-reload-after-expenses`), and "VFG-026" – dragging bars of the
  timelines in hour columns, the keyboard moves, the dialog of the move. The
  texts of the pickers come from `data-text-*` attributes on `<body>`
  (`templates/base.html`). Everything
  is merged into `app.js` and `app.css`; a page loads no further file – with
  one exception: a map loads `static/vendor/leaflet/leaflet.js`
  and `leaflet.css` from this server the first time it is shown. Blocks
  added by a release carry a comment header with their requirement ID.

**Choices kept for the session** (not with the account): the calendar's
week or month (`calendar_view`; week by default), the number
of days of the timeline, utilization and personnel plan (`schedule_days`)
and, whether days or weeks were chosen last (`schedule_span`,
VFG-028) – both written only when they change –, the view of a person's
availability (`availability_view`), of the mails (`mail_view`), and of
the packlist (`packlist_order`, `packlist_contents`,
`packlist_family_view`). A choice per list in the browser – the folded
filters – is in `localStorage` (UIX-030); without one a list starts folded
on every width (UIX-038). The timeline on the tab
"Zeitplanung" keeps nothing in the session: it opens on the project's
rental period (PRJ-103).

**Required fields** (UIX-035) are marked from the form, not
by hand: `core/_field.html` (and the type-ahead field, and hand-written
forms through `core/_required_mark.html`) asks the filter
`required_condition` – required form field, `aria-required` set by
`core.forms.mark_required`, or a condition from `mark_required(field,
when=…)` (`data-require-if`) –, and `core/_form_errors.html` adds the note
"* Pflichtfeld" once per form (`_required_note.html`, `marks_required`).
A new form gets the marks by itself when its fields come through
`_field.html`; a field the model requires although the form field is
optional needs `mark_required` (core-flows, section 18).

**What every page knows** comes from one context processor,
`core.context_processors.application`: the version, the rights (the same
`Rights` object the views check, AUT-020) with the prepared answers
`can.read.<module>` and so on, the navigation and "Back", the own person,
the unread notifications, the watch keys (UIX-020) – and
`rentalars_credit` (`CREDIT_NAME`, `CREDIT_URL` from `rentalars/__init__.py`,
UIX-031; also on the pages without login, which get only version and
credit) and `company_name` (UIX-032). The company name must not cost a
query on every page: `accounts.backends.EmailOrUsernameBackend.get_user`
annotates the session user with it in the query that already brings the
person; only a user object from elsewhere reads `CompanyProfile` lazily
(core-flows, section 17).

**Filter bars** (UIX-030) are written with the block tag
`{% filterpanel "<key>" %} … {% endfilterpanel %}` of
`core/templatetags/rentalars.py` around the filters of a list form, the
search field left in front. It renders `core/_filter_panel.html` – the
button with `aria-controls` and `aria-describedby`, the summary, the panel
– and the key names the list for the IDs and for the choice remembered in
the browser. A new list with filters uses it (core-flows, section 17).

Pages that wait for a task in the background ask for its state every two
seconds with htmx (`hx-trigger="every 2s"`) and show the result when it is
done; nothing else in the page needs a script for it.

The **quick entry of time tracking** (ZEI-003) shows how far that goes
without more script: every page carries a link "record time" that loads
`timetracking/_quick.html` into the dialog. All requests inside it replace
the block itself (`hx-target="#quick-entry"`), so the same markup also works
on a page of its own (`/times/quick/`) – which is what a browser without
scripts, or a bookmark on a phone, gets.

**Colours** are defined once, as tokens at the top of `static/css/app.css`:
a dark table (`:root`, the house colours of UIX-008), a light one
(`:root[data-theme="light"]` – prepared, not yet selectable) and the light
values again for print. No rule below the tokens uses a literal colour.
`tests/unit/test_theme.py` checks that, and the contrast of every pair of
text and background (NFA-023). The frames of the timeline bars
(VFG-030) use existing tokens – `--ink-soft` for grey, `--yellow-ink` for
yellow – to reach 3:1 against the panel. **Static files** are delivered under an
address that contains a fingerprint of their content
(`core/staticfiles.py`), so that browsers never show yesterday's stylesheet
after an update (NFA-065).

All three are part of the package; nothing is loaded from other servers.
(Leaflet is part of the package too, but the pictures of
a map come from the tile server of the configuration file – after the click
on "Karte anzeigen", and allowed by the content security policy only on
pages with a map; see "Services outside Rentalars" below.)
The pages work from 360 pixels width (NFA-022); the packing page is built
for a phone and for fingers in gloves (NFA-024).

**The logo** lies in `static/img/` as PNG in 64, 128 and 256 pixels, as
`favicon-32.png` and `apple-touch-icon.png`; `favicon.svg` embeds the
64-pixel PNG (UIX-016). The company name stands under
"Rentalars" in the menu (UIX-032), "von fld-vt.de" under the version and in
the footer of the pages without login (UIX-031), and those pages
(`base_public.html`) centre logo, box and footer in one column
(`div.public-column`). In the German interface the area below
`/administration/` is called "Einstellungen" (UIX-023);
addresses and the module `ADMINISTRATION` keep their names. The sections of
the navigation and the tabs of "Planung" are start pages without "Back"
(`START_PAGES` in `core/trail.py`, UIX-022). That is a rule
with a test (UIX-041): `tests/ui/test_back_and_page_size.py`
(`NoBackFromTheNavigationTests`) walks every link of the layout around the
page (sidebar entries, "Zeit erfassen", search, top-bar buttons, sidebar
foot) and every tab it finds on those pages and fails on a "Zurück"
link – so a new tab must be added to `START_PAGES`. The back icon of the
phone's top bar (UIX-027) stays; it goes back in the browser history.

**The menu as a drawer on the phone** (UIX-045,; block
"UIX-045 " in `app.js` and `app.css`). Only while
`matchMedia("(max-width: 900px)")` matches – the existing breakpoint where
the top bar with the menu button appears – the sidebar (`#sidebar`)
slides in from the right over the whole page, width min(300 px, 86vw),
over the backdrop `div.nav-scrim` (black at 55 % × progress) in
`templates/base.html`, which also gained `aria-expanded` on the menu
button and a close button (`.nav-close`, "Close menu") in the drawer's
head. `body.nav-open` stays the one switch, so the menu button, the
magnifier and the "/" key work unchanged ("/" now also opens a hidden
menu). While open:

- **focus trap:** every element outside the drawer gets `inert`, Tab wraps
  round inside it, focus goes to the close button and back to the opener
  on closing;
- **history entry:** `history.pushState({rentalarsNav: true})` – Back
  closes the menu and the page stays; a link or the search form inside
  replaces that entry (`location.replace`), so Back from the next page
  returns here once; a leftover entry is replaced on load; logout (a POST
  form) is not handled;
- **swipe:** touch listeners only up to 900 px; the drawer follows the
  finger after 10 px sideways and decides on release by speed (≥ 0.4
  px/ms) or by being more than half open; never on elements that scroll
  sideways, have their own touch handling (maps), sliders, drag handles,
  timeline bars, the availability week, or while a dialog is open;
- 220 ms, easing out, shortened after a swipe; no animation with
  `prefers-reduced-motion`; growing past 900 px closes it at once.

**Hour lines in the day views** (VFG-033; block "VFG-033 " in
`app.css`). Tiles of a background
(`background-size: 100% / n`) are not used for the lines: Chromium sizes a tile in 1/64 px and the
rounding adds up over up to 840 hour tiles (up to 5 px off between about
1236 and 1920 px). Each row draws its day, column and hour
lines as three `repeating-linear-gradient`s over the whole row
(`calc(100% / var(--days))`, `… / var(--cols)`, `… / (var(--days) * 24)`),
and the hour head draws its lines as one `::after` layer over its second
grid row, with the labels above it and the cell borders as column lines.
Within 0.5 px at 1236–1920 px; the 8 px threshold stays.
`tests/browser/test_084_ui_in_browser.py` measures it.

**Date and time fields** show only Rentalars' picker button (UIX-036,
UIX-042): the browser's own indicator is hidden in Chromium
(`::-webkit-calendar-picker-indicator`, `!important`); Firefox cannot
hide it from a page, so the button is drawn over it in the field's
colour. Typing into the field stays possible.

What only a browser can show – an answer landing in the wrong place, a
dialog that does not close – is covered by `tests/browser`.

**Accessibility** (NFA-025, WCAG 2.1 level AA) is checked twice.
`tests/ui/test_accessibility.py` runs with every test run, without a
browser: it reads the HTML of every main page and fails on a missing
language, a field, button, link or progress bar without a name, an image
without a text alternative, or an ID used twice.
`tests/browser/test_accessibility_in_browser.py` runs axe-core in a real
browser over the main pages, colour contrast included; axe-core is not
part of Rentalars, and the test is skipped unless `RENTALARS_AXE` points to
it or it lies in `node_modules/axe-core/` (see
[getting-started.md](getting-started.md)). Every page starts with a link
"Zum Inhalt springen" for keyboard users (`templates/base.html`).
(NFA-025) the help text of a field carries the ID that
Django's `aria-describedby` names, `<id>_helptext` (`core/_field.html` and
the fields written by hand in other templates); the tabular inline of the
category fields, whose help stands in the column head, gives each field
an `aria-description` instead (`masterdata.admin._HelpInHeadField`).
`tests/unit/test_093_aria.py` opens every page and dialog of an
administrator and fails on an `aria-describedby` or `aria-labelledby` that
points to no element.

**Texts** are written in English in code and templates and translated in
`locale/de/LC_MESSAGES/django.po` (NFA-026). German is complete; another
language is another file. A test (`tests/unit/test_translations.py`) fails
when a text is missing.

## German and English (`core/i18n.py`, UIX-029)

**The msgids are the English interface.** Code, templates and JavaScript
(`data-text-*` attributes) carry finished British English; German comes
from `locale/de/LC_MESSAGES/django.po`. Nothing in the interface is German
in the code any more, except names a user sees as data (start data,
document start texts) and the import's column headings.

**Which language holds where:**

| What | Language | How |
|---|---|---|
| Pages, htmx partials, messages, PDFs a user downloads for himself (time sheet …) | the user's: `User.language`, empty = the installation's `language` | `LanguageMiddleware` (after `AuthenticationMiddleware`) activates it per request; `Content-Language` and `Vary: Accept-Language` on every response |
| Pages without login (login, password reset, setup) | the browser's `Accept-Language` (de/en), else the installation's | `browser_language` |
| API answers and errors | the user's choice, else `Accept-Language`, else the installation's | `api_language`; token authentication activates it once the user is known (`accounts.authentication`) |
| Mails and notifications to a person | the recipient's | `for_user(user)`; notifications are stored as `LocalText` – a msgid with values, some of them `LazyCall`s (a period with weekdays) – and rendered in each reader's language (`written_for`) |
| Documents, packing lists, crew sheets, mails to customers, the placeholder values and run texts of automations | the company's `document_language` | `for_documents()`, `automations.engine._language`; text the company typed stays as typed |
| Calendar feeds, CalDAV, webhooks, audit history, the names of the default automations (at creation) | the installation's | – |
| Demo data | German | – |

**Formats.** `FORMAT_MODULE_PATH = ["rentalars.core.formats"]`: English is
British – `d/m/Y`, 24 hours, decimal point, thousands comma, money
"€1,234.50" (`core/money.py`); German keeps Django's `de`. Templates keep
their German patterns (`|date:"d.m.Y"`); the built-in library
`core/templatetags/local_dates.py` replaces `date` and `time` in every
template and maps the pattern with `local_pattern` while English is
active. `parse_decimal` reads the format shown; `file_name()` gives
downloads a name in the active language.

**Start data per language.** `core/start_data.py` `localise(language)`
renames start records that still carry their start name – roles, units,
categories (codes stay), "Main warehouse", "Standard scale", document
types, job functions with their service products, Dry Hire and its phases,
the internal project, the default automations, document templates,
surcharge rules – after `core.defaults` installed them, when the
installation's `language` or the language chosen in the first-run setup is
English. A record the company renamed is never touched; existing
installations are not localised by the update. `role_names()` gives code
that looks up a start role both names.

**Placeholders.** Automation and signature texts accept German and English
names (`automations.engine.ENGLISH_PLACEHOLDERS`); `shown_token` offers the
names of the active language.

**The manual page** (`core/manual.py`, `/manual/`, link "Handbuch"/"Manual"
in the sidebar foot): reads `docs/handbuch/benutzerhandbuch.md` or
`docs/en/user-manual.md` from the package, renders it with Python-Markdown
(tables, fenced code, `toc` with `github_slug` anchors so the manual's own
contents and cross-references work), cleans the HTML with nh3 (formatting,
tables, links and heading anchors only), shows links to other files as
plain text and puts the table of contents beside it; without the English
file it shows the German one with a note (`manual_for`). A start page: no
"Zurück".

**The server scripts** follow the operator's locale (above, "Where things
are stored").

## The AI (`ai/`, EML-040, EML-044, ADM-017)

- **Short overview** (`ai/overview.py`, EML-044): computed on every view of
  the correspondence from the mails (`ai/correspondence.py` cuts each to
  its new text) – participants, counts, first/last date, last writer,
  dates and euro amounts (newest 200 mails), questions (newest 3),
  attachments. No model, nothing stored.
- **Summary** (`ai/summary.py`, EML-040): "Zusammenfassen" starts the
  background job `ai_summary` (`core/jobs.py`); the job packs the mails
  (and, if asked, the chat) into parts that fit the model's context,
  summarises them and the summaries again (up to 6 levels), and stores one
  `AISummary` per project with the newest mail it covers. The page polls
  the job like other background tasks; the starter gets the usual
  notification. A whole project's summary records the parts it covers and
  is hidden from readers who cannot read all of them.
- **Client** (`ai/client.py`, ADM-017): one OpenAI-compatible
  `chat/completions` call with timeout; every call – success or not –
  writes an `AICall` (no content). The local AI's address comes from
  `/etc/rentalars/ai-local.conf` (`ai/local.py`, loopback only, read at
  every use); a typed `AIProvider` goes through `core.network.open_url`
  (NFA-071), never follows redirects, and is called a cloud provider when
  its host is not internal, not allowed and not `.local/.lan/.internal`.
- **Uses** (`AISettings`): summary and reply draft each "off", "local" or
  one provider; both off at first. The reply draft (`ai/drafts.py`) is job
  `ai_draft`; only its starter sees the result (`/jobs/{id}`).
- **Rights:** the correspondence's read right for overview and summary, its
  write right for a draft, the Administration module for the settings.
- **API** (`ai/api.py`): `…/correspondence-summary`, `…/mails/reply-draft`,
  `/ai/settings`, `/ai/local/speed-test`, `/ai/providers`, `/ai/calls`;
  `ai_unavailable` (409) when the chosen source cannot answer.
- **Streaming client** (EML-040): summaries and drafts call
  `chat/completions` with `stream: true` and read server-sent events; the
  timeout is a **silence** – 180 s without a token for the local AI
  (`LOCAL_SILENCE_SECONDS`), the provider's `timeout_seconds` otherwise –
  and before the first token `first_token_seconds` (3 × the estimated
  reading time + 60 s, 30 minutes unmeasured). `Progress` reports "reads
  the mails … %" (llama-server `prompt_progress`) and "writes … N words"
  to the job at most every 2 s; `max_tokens` is bounded (700 final, 450
  per part, 500 draft). Thinking stays out of the text: `enable_thinking:
  false` and "/no_think" for the local AI and Qwen models,
  `reasoning_effort: "none"` for a registered server, `<think>…</think>`
  and `reasoning_content` stripped; a server answering 400 to these extras
  gets the request once more without them. The whole job stops at 3 × its
  upper estimate (at least 10 minutes, 3 hours unmeasured).
- **Processor and speed** (ADM-017): `ai/cpu.py` parses
  `/proc/cpuinfo` (physical cores from `physical id`/`core id`, logical
  CPUs, AVX2/FMA on x86-64, the hypervisor flag) for Einstellungen → KI and
  the API (`local.cpu`, `local.threads`, `local.advice`); `ai/speed.py`
  keeps reading and writing speed apart, estimates a summary
  (`estimate`, long above 300 s), and recommends the smaller model below
  6 tokens/s writing or 30 reading or without AVX2/FMA, with the operator
  command to copy. The model itself is changed only by `sudo rentalars ai
  install --model …`.
- **Reading invoices** (MAT-062; `ai/invoices.py`): the use
  "invoice" (`AISettings.invoice_source`/`invoice_provider`, off at
  first). "Rechnung lesen" in "Kauf einpflegen" starts the job
  `ai_invoice`; `material.purchases.invoice_text` takes the text of the
  PDF with pypdf (first 20 pages, 60,000 characters; no scans), the model
  is asked for one JSON object (supplier, number, date, prices net or
  gross, positions) with the invoice text marked as data, not
  instructions. The answer is checked strictly (`parse_answer`: expected
  keys and types only, lengths cut, control characters removed, numbers
  parsed by Rentalars, at most 100 positions) and matched against the
  existing suppliers and models (`purchases.build_proposal` – a model only
  on a certain match); the proposal stays in the job's result for its
  starter. An unusable answer falls back to the patterns used without AI
  (`purchases.head_from_text`: number, date, a known supplier). Nothing is
  created – every row from the invoice is ticked "Geprüft" before the
  purchase is saved. A cloud provider gets the warning on the settings
  page.
  (MAT-075, MAT-076) the prompt also lists, in a data block of
  their own, the categories a bought model may get
  (`purchases.purchase_categories`, at most 150) and at most 40 of the
  company's products – never customer material – (all if there are few,
  else those sharing words with the invoice; `invoices.catalogue`); the
  lists take at most a third of the room (`CATALOGUE_SHARE`, the most
  relevant lines when they do not fit; at least `MIN_ROOM` 3,000
  characters for lists and text together), the invoice text the rest
  (`prompt_for`); a text cut to fit sets `text_cut`, and the proposal
  says that the end was not read (`purchases.end_not_read_note`).
  `max_tokens` is 3,500 (`INVOICE_TOKENS`, was 2,500). The model is asked for amounts as strings
  exactly as printed, for the totals, the currency and per position the
  serial numbers, a category and a product. `parse_answer` reads JSON
  numbers as `purchases.NumberLiteral`, decides the style of the amounts
  with `purchases.invoice_numbers` (the answer's own written amounts, then
  those of the invoice text, its currency, its language) and checks each
  amount against the amounts of the text (`InvoiceNumbers.amount`);
  serial numbers not in the text are dropped and counted. `build_proposal`
  fills in category and product of a new model only on an exact or
  unambiguous match (`match_category`, `match_product`), otherwise
  `hints`; without the purchase-price right `without_prices` removes
  prices and totals, also from the fallback.

**Automatic summaries and security (EML-056, NFA-079).**

- **The night job** (`ai/auto.py`, command `ai_summaries`): started by the
  minute timer once a night inside the window; `AutoSummaryRun` with a unique
  `lock` and a heartbeat keeps two runs from overlapping. It chooses the
  candidates (`verdict`: statuses, exclusions, minimum number of mails,
  minimum interval, marks of the correspondence compared with the stored
  summary), builds and hashes the texts and **calls the model only if the hash
  differs**, within a token budget and a count per night, and stops after
  three failures in a row. It acts as the principal `system:ai-summaries`
  through the same `ai/summary.py` functions as the button. Consent is bound
  to the server (`consent_key`).
- **Filters in both directions** (`ai/privacy.py`): out – `prepare` removes
  IBAN (check digits), card numbers (Luhn), secrets, e-mail addresses and
  phone numbers per data class and `neutralise` takes delimiters and role
  tokens apart and strips invisible characters; in – `clean_output` makes
  the answer plain text (no tags, images, links) before it is stored or
  shown. Summaries by hand, nightly summaries and reply drafts use the same
  functions.
- **The provider layer** (`ai/client.py`): an address on the internet must be
  https (saving http is refused), redirects are never followed, the key is
  hidden in `repr`, answers are capped, `manual_per_hour` limits the calls by
  hand.
- **Reading invoices** is now used by three doors: "Kauf einpflegen"
  (`ai_invoice`), the register of incoming invoices (`ai_incoming_invoice`,
  `invoices.register_proposal`) and the import of old projects
  (`ai/legacy_invoices.py`, `Use.INVOICE`, only the text goes out). All three
  read the answer strictly and let Rentalars do the matching.

## The API (API-001 ff.)

Everything under `/api/v1`. The description (OpenAPI 3) is generated from the
code and served at `/api/v1/schema`, readable at `/api/v1/docs/`.

- **Authentication:** `Authorization: Bearer rl_…` with a personal token, or
  the session of a logged-in browser.
- **Lists** are paged the same way everywhere (`api/pagination.py`),
  filtered with `django-filter`, searched with `?search=`.
- **Errors** always have the same shape (`api/errors.py`):
  `{"error": {"code": "validation_error", "message": "…", "fields": {…}}}`.
- **Numbers** that are amounts or quantities are sent as strings
  (`"12.50"`), so no client rounds them through a floating point number
  (`api/renderers.py`).
- **Versioning:** the `v1` in the address. Incompatible changes get a `v2`
  next to it.
- **Long work** – imports with `background`, the full export, many labels –
  answers 202 with a task; `/jobs/{id}` tells how far it got and holds the
  result (`result`, or a file at `/jobs/{id}/result`).

Since 0.5 `api/safeguards.py` protects the API in three ways (API-010,
API-011). All three keep their state in the database (`api.models`), so
they hold across all worker processes:

- **Rate limit.** `TokenRateThrottle`, DRF's default throttle, counts the
  calls of each token per minute in `ApiCallCount` and refuses calls above
  `SystemSettings.api_requests_per_minute` (600; 0 switches it off) with
  429 `throttled` and `Retry-After`. Calls with a browser session are not
  counted. The middleware adds `X-RateLimit-Limit` and
  `X-RateLimit-Remaining` to the answer.
- **Repeated calls.** A changing call (`POST`, `PUT`, `PATCH`, `DELETE`)
  with an `Idempotency-Key` header is carried out once; its answer is
  stored in `IdempotentCall` for a day, per token (a hash of the
  `Authorization` header) or session user. The same call with the same key
  gets the stored answer and `Idempotent-Replayed: true`; the same key with
  another call 422 `idempotency_key_reused`; a second call while the first
  still runs 409. Answers of 500 and above are not stored, so the client
  may try again.
- **Overwriting.** Every JSON answer 200 to a `GET` carries an `ETag` (a
  SHA-256 of the body); `If-None-Match` turns an unchanged answer into 304.
  A changing call with `If-Match` is checked first: the middleware asks the
  same address by `GET` and refuses with 412 `precondition_failed` if the
  tag no longer matches.

**Both (API-010, from a code review):**

- **Order of a call with `Idempotency-Key`:** authenticate first (a call
  that does not log in is handled as without key); then look up the stored
  call by `IdempotentCall.scope` – `token:<pk>` or `user:<pk>`
  (`safeguards._scope`) – and key; then run
  every check of a new call (login, module rights, rate limit, access to
  the record the path names – a record that is gone does not refuse, so a
  repeated `DELETE` still gets its 204); only then 409 "in progress", 409
  `idempotency_key_reused` (same caller, another method/path/body hash) or the stored answer. Another caller never matches. A call with both
  a key and `If-Match` gets its stored answer when repeated.
- **`If-Match` is atomic:** the comparison and the write run in one
  `transaction.atomic`, which first takes a row of `api.WriteLock` (key the
  SHA-256 of `record:<app.model>:<pk>`, or `path:<address>` where the path
  names no record); on MariaDB the record's own row is also locked with
  `SELECT … FOR UPDATE`, so a browser write waits too. A 5xx answer rolls
  the transaction back. Lock rows older than a day go with the daily
  maintenance. The web forms have no version check (last write wins), so
  there is nothing to make race-free there. The two-thread test
  (`SimultaneousVersionCheckTests`) runs only on MariaDB.

The API also **talks first** (API-012). A webhook names an
address of another system and the events it wants; when one happens,
Rentalars sends it a signed `POST`. `api/webhook_events.py` is the
catalogue of events – what each sends, with an example that the API
description shows under "webhooks"; `api/webhooks.py` records a delivery
in the transaction of the change, and the minute timer sends, retries and
switches off (see [core-flows.md](core-flows.md), section 12). Webhooks
are managed under Settings → Webhooks (`api/webhook_views.py`, module
"administration") and through `/api/v1/webhooks` (`api/webhook_api.py`),
with the same rights.

The API is also the server of the **Android app**
(catalogue 5.16; core-flows, section 4, "Packlists on the phone"). Added
or changed in `api/urls.py`:

| Route | What |
|---|---|
| `GET offline/packlists` | the packlists to take along (`OfflinePacklistsView`, module packing, PCK-026) |
| `POST projects/{p}/packlists/{id}/sync` | the ticks of the phone (`PacklistSyncView`, PCK-027). **Registered before `projects/{p}/packlists/{id}/{action}`**, whose `<slug:action>` would otherwise take "sync" for a packing step and answer "Unknown packing step." |
| `POST projects/{p}/packlists/{id}/take-back` | an action of `PacklistActionView`: book what is ticked as back (PCK-028); `return-all` only ticks now, `complete-return` books the ticks first |
| `GET docs` | the documentation also without the slash – the mobile app needs no redirects under `/api/v1` |

The packlist document adds per row `taken_back`, `ready_to_take_back`,
`still_out`, `packed_changed_at`, `returned_changed_at`, per packlist
`ready_to_take_back`, `taken_back`, `still_out` and `bar` (PCK-029); every
quantity is text with two decimals. A phase adds `outside_rental_period`
and `rental_period_suggestion` (PRJ-100), a crew line the request fields
with `requested_start`, `requested_end` and `times_changed_since_request`
(PER-033), the system settings `ask_again_on_new_times` (PER-034). Under
`/tokens` a token limited to modules sees only itself and creates no
tokens, and a token with an expiry creates none that outlive it (AUT-021).
The `Date` header of every answer comes from gunicorn in production; the
application does not add one (a second header would follow).

Further additions and changes in `api/urls.py` and the documents:

| Route or field | What |
|---|---|
| `GET projects/{p}/subrentals`, `GET`/`PATCH projects/{p}/subrentals/{supplier}` | the subrentals of a project per supplier, status and purchase prices of several lines at once (`projects/subrental_api.py`, PRJ-106) |
| `POST projects/{p}/mails/{id}/supplier` | the supplier of subrentals a mail belongs to, or none (PRJ-106) |
| `PUT`/`DELETE projects/{p}/follow-up` | set or remove the follow-up; `follow_up_on`, `follow_up_note`, `follow_up_user`, `follow_up_user_name`, `follow_up_is_due` are read-only in the project; filter `?follow_up=due\|mine\|any` (PRJ-105) |
| `POST material-models/{id}/create-product` | a product of the model's name (MAT-051) |
| `POST material-models/{id}/items` | takes `start_number` and `serial_numbers` (MAT-050); items have `invoice_number`, models `power_w` (MAT-049) |
| `DELETE mail/mailboxes/{id}` | always deletes, answers 204, takes `?successor=` (EML-046); mail-log entries have `mailbox_name`, `mailbox_deleted` |
| products, job functions, rates, crew lines | `kind` `incidental` (PRD-045); a product's `hours_limit`, `price_above_limit`, `job_function`; a function's `service_product` read-only, `price` only when creating, `guide_cost_rate_above_limit`; a rate's `hourly_rate_above_limit`; a crew line's `service_product_article_number`, `hours_limit`, `unit_price_above_limit`, `normal_hours`, `hours_above_limit` and, with the right for personnel costs, `hourly_rate_above_limit`, `cost_hours_above_limit`, `cost_rate_above_limit` (PRD-044, PER-035) |
| suppliers, files, mails, storage locations | `email`, `phone` on `/suppliers`; `supplier`, `supplier_document_kind` on files; `supplier` when sending a mail; `?supplier=` on mails and files; `is_default` on storage locations |

A service is refused as a material line (400, PRD-044), a subrental status
other than "open" without supplier too (PRJ-101); a new subrental starts
"open", a new crew line of a product by the hour "effort" (PER-036). The
personnel plan `GET personnel-plan` lists every active person unless
`busy=1` (VFG-023). `/mail/settings` keeps `crew_answers` (ADM-015).

Further additions and changes in `api/urls.py` and the documents (each new
operation reached by a test, API-014):

| Route or field | What |
|---|---|
| `GET`/`POST projects/{p}/split` | what dividing would do; turn the groups named into subprojects, `crew` mapping crew lines to groups (`projects/case_api.py` `SplitView`, PRJ-050) |
| `service-cases` (list, create – with `inquiry` from Projekte → Anfragen –, read, `PUT`/`PATCH`, `DELETE`), `POST service-cases/{id}/convert` | service cases (`ServiceCaseViewSet`, PRJ-090); `GET projects` lists none unless `?kind=` is given; webhook payloads of projects carry `kind` |
| `GET`/`POST projects/{p}/chat` (`?before=`, `?limit=` up to 500), `GET`/`PUT`/`PATCH`/`DELETE projects/{p}/chat/{id}`, `GET`/`POST …/chat/read`, `GET …/chat/readers` | the chat of a project (`chat/api.py`, UIX-010); writing needs read access to projects, a read-only token only reads |
| `automations` (list, create), `automations/{id}` (read, `PUT`/`PATCH`, `DELETE`), `GET automations/runs` (`?automation=`, `?status=`) | rules and runs (`automations/api.py`, ADM-013), module administration; `runs` registered before `{id}` |
| `GET maps/{target}/{id}`, `PUT`/`DELETE maps/{target}/{id}/positions/{key}` | the places of a map with route links and positions – missing positions are looked up now –, a position set by hand or forgotten (`core/map_api.py`, UIX-033, UIX-034) |
| `GET projects/{p}/trips` | the trips of a project with route links and problems (`projects/trip_api.py`, PRJ-097), deployment view |
| `GET`/`PATCH settings/surcharges`, `GET holidays?year=&state=` | the settings of the surcharges (module administration) and the computed holidays (anyone logged in) (`core/surcharge_api.py`, PER-009) |
| `expenses` (list, create, read, `PUT`/`PATCH`, `DELETE`), `GET expenses/{id}/receipt`, `POST expenses/submit`, `…/approve`, `…/reject`, `…/reimburse`, `POST expenses/{id}/reopen`, `…/take-back-reimbursement`; `GET reports/expenses`, `…/csv` | expenses and their report (`timetracking/expense_api.py`, ZEI-019) |
| `POST projects/{p}/reschedule/preview`, `POST projects/{p}/reschedule` | what moving the rental period, the event or a phase would do – changing nothing –, and doing it (`schedule/move_api.py`, VFG-026) |
| `settings` | `company.warehouse_address`; `system.maps_load_at_once`, `invoices_enabled`, `time_hint_*`, `expense_km_rate` |
| time entries, crew lines, project totals, products | `hints` on every time entry (ZEI-018); on a crew line `time_surcharges_on_price` and `time_surcharges` with the price right, `time_surcharges_on_cost`, `cost_time_surcharges`, `actual_cost_time_surcharges` with the right for personnel costs; totals `personnel_time_surcharges` and `expenses_cost`; `time_surcharges` on products (price right) (PER-009, ZEI-019) |
| addresses, suppliers, lines, files | `route_url` on venues, customers, their addresses and suppliers; `street`, `postal_code`, `city`, `country` on suppliers; `picked_up_at_supplier` on material lines and in the subrentals of a project; `show_system`, `show_version`, `is_current_show` on project files and in the deployment view |

With invoices switched off, making an invoice, a draft of one, a
cancellation, a hand-over to Lexware Office and the DATEV export answer 400
(DOK-014). The API names the enum of the federal states `FederalStateEnum`
and keeps `StateEnum` for the availability (`SPECTACULAR_SETTINGS`).

Further additions and changes in `api/urls.py` and the documents (each new
operation reached by a test, API-014):

| Route or field | What |
|---|---|
| `GET`/`POST mail/mailbox-addresses`, `GET`/`PUT`/`PATCH`/`DELETE mail/mailbox-addresses/{id}`; `addresses` on `mail/mailboxes` | further addresses of a mailbox (`mail/api.py`, EML-047) |
| `POST mail/unknown/dismiss` (`{"ids": [...]}`); `inquiry` on `POST projects` | take several mails off Projekte → Anfragen; a project from an inquiry (PRJ-107) |
| `POST users/{id}/send-invitation`, `POST users`, `POST projects/{p}/crew-lines/{id}/request` | 204 as before when sent, else 200 `{"sent": false, "reason"}`; `invitation` on a created user; `mail_sent`, `mail_reason` on a request (`mail.server.mail_state`, EML-048) |
| `GET`/`POST service-cases/{id}/participants`, `PATCH`/`DELETE …/participants/{pid}`; `participants`, `?taking_part=true` on service cases | people taking part (`projects/case_api.py`, PRJ-108); a repeated `POST` answers 200; removing needs write, not delete |
| `follow_up_at` on projects and service cases and in `PUT projects/{p}/follow-up` | the time of a follow-up (PRJ-109) |
| `time-entries`: `period`, `period_hours`, `parts`, `crew_line`; `timer/start`: `crew_line`; `time-entries/choices`: `crew_lines` (with `label`), `suggested_crew_line`, `is_service_case`, `takes_part`, open service cases | divided periods and service cases (`timetracking/api.py`, ZEI-025, ZEI-024); an entry without `parts` behaves as before, so the companion app keeps working |
| `commute_km` on people and expenses; CSV column "Arbeitsweg (km)" | the way to work (ZEI-027) |
| `notifications`: `category`, `companion`, `?category=` (400 if unknown), `?companion=1`; `notifications/preferences`: `category`, `category_label`, `companion` (kept when left out) | categories and "In der App" (UIX-039); the companion token (packing, projects, times) reaches every notification endpoint |
| `reschedule`, `reschedule/preview`: `what=crew` with `crew_line`; answer `planned_hours_before`, `planned_hours_after` | dragging deployments in the personnel plan (`schedule/move_api.py`, VFG-031) |
| `settings/surcharges`: `rules`, `own_holidays` (a sent list replaces the stored one; errors `rules.N.field`); `POST settings/surcharges/section-3b`; `holidays`: own holidays (`key` "own", `own`, `german_holidays`); `rule` in the surcharge parts of crew lines, `label` = the rule's name, `kind` `custom` for hand-made rules | surcharge rules (`core/surcharge_api.py`, PER-040) |
| `settings`: `system.time_hints_enabled`, `system.expense_deduct_commute`; `hints: []` with the hints off | ZEI-018, ZEI-027 |

Further additions and changes in `api/urls.py` and the documents (each new
or changed operation reached by a test, API-014). Everything the Companion
app uses only gained keys:

| Route or field | What |
|---|---|
| every changing call with `Idempotency-Key` | bound to the caller and request; 409 `idempotency_key_reused` instead of 422; checks before the stored answer; `If-Match` atomic (`api/safeguards.py`, API-010) |
| `GET projects/{p}/packlists/{id}`, the sync's packlist, the family view | `version` per row (PCK-027) |
| `POST projects/{p}/packlists/{id}/sync` | per change optional `base_version` and `change_id` (≤ 64); per result `change_id`, `replayed`, `version`, `server{quantity, changed_at}`; `OutcomeEnum` gains `conflict` (only with `base_version`) (`packing/api.py`, PCK-027) |
| `GET offline/packlists` | creates nothing any more; a project without packlist has `packlists: []` (PCK-027) |
| `GET`/`POST projects/{p}/chat/read` | `up_to` lowered to the newest message of the chat; not a whole number ≥ 0 → 400 (`ChatReadSerializer`, UIX-010) |
| `GET projects/{p}/trips` (`?removed=true` for editors), `POST projects/{p}/trips`, `PATCH`/`DELETE projects/{p}/trips/{key}`, `POST …/trips/{key}/reset` | trips with `key`, `note`, `is_changed`, `is_removed`, kind `own`; changed, removed, reset, added by hand (`projects/trip_api.py`, PRJ-111); removing needs write, not delete; a closed project 400 |
| `POST service-cases`, `PUT`/`PATCH service-cases/{id}` | `customer` required on create, cannot be set to `null` (400 `customer`, PRJ-090) |
| `mail/mailboxes`, `mail/mailbox-addresses` | `untagged_since` (`null` while switched off; set to now when switched on without a value), `untagged_unread_only` (EML-049) |
| `route_url` on venues, customers, addresses, suppliers, subrentals, trips | without `origin` – Google Maps starts at the viewer's location (UIX-033) |
| `webhooks`, calendar feeds | an internal IP address or `localhost` without allowance → 400 when entered; a host name is checked when used (NFA-071) |
| `GET self-check` | the group "Verbindungen zu anderen Servern"; "HTTPS" a warning with `allow_http` (NFA-071, NFA-073) |

Further additions and changes in `api/urls.py` and the documents (each new
or changed operation reached by a test, API-014). Everything the Companion
app uses only gained keys, except the meaning of `unread`
with a filter; the app's token (packing, projects, time_tracking, email)
reaches all new endpoints but `settings/notifications`:

| Route or field | What |
|---|---|
| `GET projects`, `projects/{id}`, `service-cases` | `field_changed_at` (key → moment; the deployment view only for the fields it shows), `manager_name`, `venue_label` (also with access "deployment"); on service cases `case_status_changed_at` (= `field_changed_at.case_status`) (`projects/api.py`, `projects/case_api.py`, PRJ-113, PRJ-114, API-016) |
| `PATCH projects/{id}`, `POST projects/{id}/status`, `PUT`/`DELETE projects/{id}/follow-up`, `PATCH service-cases/{id}` | optional `changed_at` (ISO 8601 with zone; for DELETE also in the query); `case_status_changed_at` on cases; answer the record as it is now plus `applied` (only when a time was sent); a status no longer allowed 409 with `error.code` `status_not_allowed` and the project; the rule in `projects/field_changes.py` (PRJ-113, PRJ-114) |
| `GET`/`PATCH people/me/profile`, `GET`/`POST people/me/absences`, `DELETE people/me/absences/{id}`, `GET people/me/deployments` | one's own data without a module right, registered before the router (`me` is no ID) (`personnel/own_api.py`, API-015) |
| `GET me`, login answer | `server_version` (API-016) |
| `GET notifications` | `unread` counts within `category`/`companion`; `unread_total` (API-016) |
| `time-entries` | `pay_kind` (`hourly`, `daily`, `flat`) and `in_day_rate` where rates are visible (`timetracking/display.py`, API-016); `time-entries/choices` never empty (ZEI-007) |
| `GET`/`PATCH settings/notifications` | the shortage schedule, flat fields plus `shortage_next_check`; module Administration (`notifications/api.py`, VFG-036) |
| `POST projects/{p}/packlists/{id}/add-material` | 403 `needs_project_write` without `may_add_material` (PCK-013) |
| `POST projects/{p}/packlists/{id}/sync` | `reason` `needs_project_write` or `above_packing_list` on a refused quantity above the list; kept for a replay (`SyncReceipt.reason`) (PCK-027) |
| `GET offline/packlists` | `can_add_material` per project (PCK-013) |
| `DELETE` packlist, handover, extraction | write on packing suffices (`PacklistView.action_levels`), as in the browser (PCK-013) |
| products | `time_surcharges: null` for every kind but a service; a sent value is ignored (PER-009) |
| `…/correspondence-summary`, `ai/settings`, `ai/local/speed-test`, `ai/calls` | `estimate`; `local.cpu`, `local.threads`, `local.typical_summary`, `local.advice`, `speed_test.prompt_tokens_per_second`; `prompt_tokens_per_second`; `prompt_per_second`, `generation_per_second` (EML-040, ADM-017) |

Further additions and changes in `api/urls.py` and the documents (each new
or changed operation reached by a test, API-014). Three changes refuse what
was accepted before (products with two prices, sales of rental products)
or answer differently without the new special right; everything else only
gained routes and keys:

| Route or field | What |
|---|---|
| `POST purchases`, `POST purchases/invoices` | enter a purchase – head and positions, all items in one step with consecutive IDs, the kept invoice (`invoice_upload`) attached to each –; upload an invoice (multipart `file`), kept two days for its user (`upload`), read unless `read` is false: the head proposal at once, with AI a `job` whose result (`/jobs/{id}`) holds the positions (`material/purchase_api.py`, MAT-061, MAT-062) |
| `POST material-models/{id}/items`, `POST material-items`, `PATCH material-items/{id}` | `prices` (`net`/`gross`) and `price_tax_rate`; a gross price is stored net, rounded to cents (MAT-059) |
| `POST products/{id}/duplicate` | a new product from this one, the next free article number of its category, prices and costs as the rights allow, kit components copied; the body overrides fields; 201 (`products/api.py`, PRD-048) |
| `GET products/suggest-article-number` | `?product=` for a product moving to the `category`: its own article number is kept while it fits the category, else the next free one (PRD-049) |
| products, material lines | one price (PRD-047): `sale_price` on a product that is not a sale product, `price` on a sale product, `is_sale` on a new line of a rental product → 400 |
| `POST projects/{p}/crew-lines/bulk` | `action` `edit` (with `values`), `firm`, `ask` or `delete` for `crew_lines`; every line through the single-line service, `skipped` with reasons (`projects/crew_api.py`, PRJ-117) |
| crew lines | `firm` on create and `PATCH` (`request_status` `firm`, PER-041) |
| `POST time-entries/{id}/correct` | correct a submitted time and approve it (`timetracking/api.py`, ZEI-030) |
| `GET`/`PATCH settings/notifications` | `approval_reminders`, `approval_time`, `approval_first_days`, `approval_every_days`, `approval_next_check`, `approval_checked_at`, `approval_reminded` (ZEI-029) |
| `GET people/availability` | without `job_function` every active person, also those without a job function (VFG-038) |
| `GET utilization` | kits: per day `free`, entries `components` with `per_kit` (VFG-037) |
| `GET accounting/documents`, `GET accounting/documents/totals` | the outgoing documents with the filters of the page and their sums per kind (`documents/outgoing_api.py`, DOK-020) |
| `users`, `people` | `data_access` (`finances`, `personnel_data`, `customer_data`; AUT-034) |
| `permissions`, `roles` | project scope `deployment`, special right `availability` (AUT-031, AUT-032) |
| planning, material lines, `availability`, `shortages`, `projects/{p}/shortages`, `products/{id}/availability`, `utilization`, timelines | without the special right `availability`: `availability` and `shortage_total` are `null`, the others 403 (AUT-032) |
| `projects/{p}/planning`, `…/history`, `…/members`, lines, `open-items` | 403 for a role with the scope `deployment` (AUT-031) |
| `service-cases` (list, read, `PATCH`, `participants`), their chat and correspondence | open to the person responsible and those taking part, whatever their roles (`projects/case_work.py` `CaseWorkPermission`, AUT-033) |
| `ai/settings` | `invoice` (`off`, `local` or `p<id>`; MAT-062) |

## Outbound connections to user-entered addresses (`core/network.py`, NFA-071, NFA-072)

Every address a user types and the server then calls – calendar
feeds and CalDAV (`personnel/calendar_client.py`), webhooks
(`api/webhooks.py`), IMAP (`mail/imap.py` `open()`, `GuardedIMAP4`,
`GuardedIMAP4SSL`) and SMTP of mailboxes (`mail/mailboxes.py`
`smtp_session`, `guarded_smtp_class`) including the system mailbox
(`mail/backends.py` → `GuardedSmtpBackend`) – goes through one guard:

- `checked_addresses(host, port)` resolves the name and keeps only answers
  `refusal()` lets through; `kind_of()` names loopback, private,
  link-local, shared (CGNAT), multicast, reserved, unspecified and
  anything else not globally reachable, also IPv4 inside IPv6 (mapped,
  NAT64, `_effective`); `own_addresses()` adds the server's interfaces
  (`/proc`), host name and the address of `RENTALARS_URL`.
- `create_connection()` and the `Guarded*` classes connect to exactly the
  checked address – no second lookup, against DNS rebinding – while TLS
  still verifies the certificate against the name. `open_url()` sends a
  `urllib` request through the guarded handlers; redirects come back to the
  caller (`_KeepRedirects` in the calendar client, at most `MAX_REDIRECTS`
  = 5, each target checked again; `_NoRedirects` for webhooks).
- The operator's exceptions: `settings.RENTALARS_NETWORK_ALLOW_INTERNAL`
  from `[network] allow_internal` (`config.NetworkConfig`, validated at
  start), parsed by `parse_allowance()` into networks and host names; a
  host name is allowed whatever it resolves to. Under `manage.py test` the
  default is `127.0.0.0/8` and `::1`, so the suite's local receivers keep
  working; the guard's tests switch it off.
- `check_entered_host()` refuses an IP address or `localhost` already in
  forms and serializers (calendar, CalDAV, `validate_webhook_url`);
  mailbox hosts are not checked when typed. Error texts never show the
  resolved address (`BlockedAddressError`); the self-check does.
- With `https_proxy`/`http_proxy` applying (`_proxy_applies`), the
  request goes through the proxy after the name was checked; the proxy
  resolves it again, so pinning then depends on it.
- Credentials (NFA-072): the calendar client sends them only to exactly
  the same scheme, host and port; `CREDENTIAL_PARTNERS` names the one
  exception, iCloud (`caldav.icloud.com` → `pNN-caldav.icloud.com`,
  https, 443). Addresses on another host in a server's answer are not
  contacted; the calendar found is checked before it is stored.
- Exempt, because the operator sets them: `[email]`, `[maps]`, the
  database, Lexware's fixed address.

**HTTPS only (NFA-073).** `config.load_config` raises `ConfigurationError`
for a production configuration whose `url` is not https unless
`allow_http = yes` (`settings.RENTALARS_ALLOW_HTTP`).
`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` and the
redirect, HSTS and secure cookies apply when `url` is https; behind a TLS
proxy `url` stays https and the proxy sends `X-Forwarded-Proto`. The
self-check (`core/selfcheck.py` `_security`, `_network`) reports both.

## Services outside Rentalars

What leaves the server or the browser, and when (NFA-050):

| Service | Who talks to it | When | Settings |
|---|---|---|---|
| IMAP/SMTP of the mailboxes | the server | fetching every minute, sending | the mailboxes (EML-041); internal hosts only with `[network] allow_internal` |
| Lexware Office | the server | a hand-over (DOK-011) | Einstellungen → Buchhaltung |
| calendar servers | the server | every 30 minutes for linked calendars, on change for CalDAV (PER-022, PER-023) | per person; internal hosts only with `[network] allow_internal` |
| webhook receivers | the server | after a change (API-012) | Einstellungen → Webhooks; internal hosts only with `[network] allow_internal` |
| Nominatim (OpenStreetMap's search) | the server, | after "Karte anzeigen" (or with "Karten sofort laden"), once per address, at most one request per second for the installation (UIX-034); with the User-Agent `Rentalars/<version> (maps; +<scheme>://<host>)` (`core.geocoding.user_agent`), no redirects | `[maps] geocoder_url`; empty: positions by hand only |
| the tile server of OpenStreetMap | the browser, | after the click, for the map pictures; `img-src` of the content security policy names it on pages with a map only. The tile layer has `referrerPolicy: "strict-origin-when-cross-origin"` (`core.maps.TILE_REFERRER_POLICY`, handed to the page in `map_data["referrerPolicy"]`, the same value as fallback in `app.js`), so the OSM tile policy sees the installation's origin; the pages keep `Referrer-Policy: same-origin` | `[maps] tile_url`, `attribution`, `attribution_url`, `max_zoom`; empty `tile_url`: no maps |
| Google Maps | the browser, | only when somebody follows "Route in Google Maps" (a link with `noreferrer`, UIX-033); without `origin`, so it starts at the viewer's location | – |
| the local AI (`llama-server`, 127.0.0.1) | the server, | "Zusammenfassen", "Entwurf vorschlagen", "Geschwindigkeit messen", "Rechnung lesen" in "Kauf einpflegen" (the text of the invoice, MAT-062) – only for the uses set to "local" (EML-040) | installed by the operator (`sudo rentalars ai install`); address in `/etc/rentalars/ai-local.conf`, loopback only |
| AI interfaces (OpenAI-compatible: Ollama, LM Studio, vLLM, cloud services) | the server, | only for a use assigned to the interface; off at first (ADM-017); every call logged without content | Einstellungen → KI; internal hosts only with `[network] allow_internal`, no redirects; a cloud host shows a warning |
| the company directory (LDAP / Active Directory) | the server, | at a login with a name that is not a local account, the test buttons and the nightly comparison (AUT-029); name and password of the user and the groups; `ldaps://` or StartTLS, certificate checked against the **name** of the server | Administration → "Verzeichnis (LDAP)"; internal servers only with `[network] allow_internal` |
| huggingface.co, github.com, the Ubuntu archive | the operator's command, not Rentalars | `sudo rentalars ai install` downloads the model (checksum checked), on Ubuntu 24.04 and Debian 13 the llama.cpp source (commit checked), on 26.04 the package `llama.cpp-tools` | – |
| Geofabrik (`download.geofabrik.de`), the Ubuntu archive | the operator's command, not Rentalars, | `sudo rentalars route install` downloads the OpenStreetMap extract (MD5 checked) and the package `routino` | – |
| an OSRM server | the server, | "Geplante km aus der Route vorschlagen" in the dialog of a vehicle on a trip (LOG-017): the positions of the places of the trip, no redirects | `sudo rentalars route register --url https://…` (https, or http on loopback); `/etc/rentalars/route-local.conf` |
| Let's Encrypt | certbot, run by `sudo rentalars address apply` and the renewal timer | a new address with "Let's Encrypt" (ADM-016) | Einstellungen → Serveradresse und Zertifikat |

Tests reach none of them: `tests/mailbox.py`, `tests/lexware_fake.py` and,
, `tests/geocoder_fake.py` stand in, and the browser tests of
the maps take their tiles from the test server itself
(`tests/browser/test_080_maps_in_browser.py`); `tests/ai_fake.py`
is an OpenAI-compatible server on 127.0.0.1, and
`tests/address_certificates.py` a small certificate authority for the
address tests.

## Where things are stored

| What | Where (on a server) |
|---|---|
| Program and Python libraries | `/opt/rentalars/releases/<version>-<time>/`; `/opt/rentalars/app` and `/opt/rentalars/venv` point to the active one |
| Configuration | `/etc/rentalars/rentalars.conf` – the only file with settings and secrets (NFA-032) |
| Database | MariaDB, database `rentalars` – on this server, or on another one (NFA-066) |
| Uploaded files, project files, mail attachments, documents, material files, results of background tasks, collected static files | `/var/lib/rentalars/` (stored files below `media/`, task results below `media/jobs/`, backups made in the browser below `media/jobs/backups/` – left out of the nightly backup; receipts of expenses below `media/receipts/<person>/`, and `geocoder.lock`, the time of the last request to the geocoder) |
| Import files between upload and import | `/var/lib/rentalars/imports/`, removed after the import or by the daily maintenance after two days |
| Photos and videos of the chat | the smaller versions and previews below `media/chat/<project>/` (random names, delivered only by `chat.views.media_file` after the chat's read check; in the backup); uploaded videos waiting for ffmpeg and its temporary files in `/var/lib/rentalars/chat-videos/` (`DATA_DIR`, not in the backup), the original removed once converted or failed, leftovers older than two days by the next video upload and by the daily maintenance (`media.delete_old_sources`); next to it the empty lock file `/var/lib/rentalars/chat-videos.lock` that lets one conversion run at a time (`media.conversion_slot`) |
| Purchase invoices between upload and saving the purchase | `/var/lib/rentalars/purchase-invoices/` (random names, a signed token per user, `purchases.PENDING_DAYS` = 2), removed by the next upload or by the daily maintenance after two days; not in the backup. Saved, the invoice is one file below `media/` shared by the `MaterialFile` rows of all items of the purchase (MAT-061) |
| The font of the labels | `static/fonts/LiberationSans-Regular.ttf` with `LiberationSans-OFL.txt` (SIL OFL 1.1, `THIRD-PARTY.md`), used by the print pages and the PDF of the labels alike (MAT-065) |
| Backups | `/var/backups/rentalars/` (`*.tar.gz`, or `*.tar.gz.enc` with encryption) |
| Recovery key of the encryption | `/etc/rentalars/recovery-key`, root only (NFA-067) |
| A prepared address change: uploaded certificate and key | `<data_dir>/address/<token>/` (0700/0600, the key Fernet-encrypted), deleted after apply or when superseded (ADM-016) |
| Backups made by `rentalars address apply`, new certificates | `/etc/rentalars/address-backup/<time>-<token>/`, `/etc/rentalars/tls/<name>/` (ADM-016) |
| The route service (only if installed) | `/opt/rentalars/routes/` (the processed map in `data-YYYYMMDD-XXXX`, `planetsplitter.log`, the packages `install` added), `/etc/rentalars/route-local.conf` (read by Rentalars at every use: kind, region, data date, router, data folder or OSRM address) – none of it in the backup (LOG-017). A folder only root can change, as the AI's: the service user can write to `/var/lib/rentalars`, where planted symlinks could redirect what root downloads and deletes |
| The local AI (only if installed) | `/opt/rentalars/ai/` (binary, models, source), `/etc/rentalars/ai-local.conf` (read by Rentalars; also `server_kind`, `physical_cores`, `threads`, `built_with`), `/etc/rentalars/ai-local.env` and `rentalars-ai.service.d/` (read by systemd), the refresh lock `/run/rentalars-ai-refresh.lock` (in `/run`, which only root may write to) – none of it in the backup (EML-040). Root runs `llama-server --help`/`--version` and writes these files only if the program and every folder above it belong to root alone (`root_only` in `deploy/ai.sh`) |
| Incoming invoices | the files below `media/incoming/<year>/` (random names, delivered only by `incoming.views.invoice_file` after the rights check); in the backup |
| Invoices of an import of old projects | `/var/lib/rentalars/legacy-invoices/` (random names) until they are taken over or dropped after `legacy_import.PENDING_DAYS` = 14 – dropped when the overview is opened or a file is uploaded, not by the nightly job; a taken-over invoice is attached to its `Document` below `media/`; back it up if open batches matter (the packages carry no data of it) |
| The manuals shown on `/manual/` | `docs/handbuch/benutzerhandbuch.md`, `docs/en/user-manual.md` in the package (UIX-029) |

Settings a person changes in the browser (company data, buffer times,
password rules, retention periods, the API limit, number ranges, document
templates, the mailboxes – any number, with their roles –, the
rules for all mailboxes and the signature, the accounting and
the webhooks, the surcharges and the automations,
the further addresses of mailboxes, the surcharge rules and own holidays)
are in the database (`core.SystemSettings`,
`core.CompanyProfile`, `core.NumberRange`, `documents.DocumentTemplate`,
`mail.Mailbox`, `mail.MailboxAddress`, `mail.MailSettings`,
`documents.AccountingSettings`, `api.Webhook`,
`core.TimeSurchargeSettings`, `core.TimeSurchargeRule`, `core.OwnHoliday`,
`automations.Automation`; `accounts.User.language`,
`CompanyProfile.document_language`, `core.AddressChange`, `ai.AISettings`,
`ai.AIProvider`; `core.NotificationSettings`, with
the reminders of times to approve, and `AISettings` with the use "reading
invoices"); the secrets among them – mail and CalDAV passwords, the
signing secrets of webhooks, the API key of Lexware Office, the API keys of
AI interfaces, the private key of a prepared address change – are encrypted
with a key derived from `secret_key` (`core/crypto.py`). Settings
that describe the surroundings (address, database, the mail server for
system mails while no mailbox has that role, the map servers
in `[maps]`) are in the configuration file. `rentalars/config.py` reads the file; `settings.py` turns it into
Django settings.

The server scripts are in `deploy/` and explained in `docs/betrieb/`
(German) and `docs/en/operations/` (English). An update
installs the new version next to the running one and switches a symlink;
that is what makes going back possible.

**The scripts speak German or English** (UIX-029).
`deploy/lib.sh` `operator_language` is `de` when `RENTALARS_LANG`, else
`LC_ALL`, `LC_MESSAGES` or `LANG`, starts with "de", and `en` otherwise
(so `C.UTF-8` is English); `t "Deutsch" "English"` prints the text for it,
`fail`/`warn` say "Fehler:"/"Error:", and `manage` passes
`RENTALARS_LANG` on, so a management command run by a script answers in
the same language (`core.i18n` reads it for commands). `deploy/address.py`
has the same rule in Python (`operator_language()`, `t(de, en)`). Tests
that read German output pin `RENTALARS_LANG=de`.

**Commands that need root** (ADM-016, EML-040; the rule of
stage 4: the application never gets root and never stores root
credentials). The interface prepares; the operator runs one command via
SSH:

- `sudo rentalars address apply TOKEN [--dry-run] [--yes]` –
  `deploy/rentalars` runs `python3 -I deploy/address.py` (the system's
  Python, isolated; standard library and openssl only). It never reads the
  application's files: it runs `manage.py address_change export TOKEN` as
  the service user (`runuser`) and parses its stdout – so a symlink the
  service user planted cannot make root read or write elsewhere –, checks
  everything again (host syntax, kind, e-mail, size; with openssl key,
  chain, name, validity), backs up, writes targeted changes to the NGINX
  site and `url`, gets the certificate (certbot, openssl or the uploaded
  one), runs `nginx -t`, reloads, restarts, checks over HTTPS and rolls
  back on any failure; the result goes back through
  `manage.py address_change record` as the service user. The token is
  the only link and is in `SECRET_FIELDS`.
- `sudo rentalars ai install|status|register|remove` – `deploy/ai.sh`
  (bash, `lib.sh`). It installs `llama-server` (package or a source build
  checked against a fixed commit), downloads the model with its SHA-256,
  writes `/etc/rentalars/ai-local.env` for systemd and
  `/etc/rentalars/ai-local.conf` for Rentalars, and enables
  `rentalars-ai.service` (shipped in `deploy/systemd/`, conditional on
  those files; hardened: `DynamicUser`, `IPAddressAllow=localhost`,
  `ProtectSystem=strict`, `Nice=10`, `MemoryMax`/`CPUQuota` in a drop-in).
  Rentalars only reads `ai-local.conf` and accepts loopback addresses
  from it. `install` reads the processor (`--threads` = physical
  cores, at most 16; `--reasoning off --reasoning-budget 0` and the other
  options `llama-server --help` lists), chooses the model by memory, cores
  and AVX2/FMA, keeps a llama-server already built (`--rebuild` builds
  again; `built_with` records the build's vector flags), and deletes the
  previous model once the new one answers (`--keep-model` keeps it).
- `sudo rentalars ai refresh [--dry-run]` (EML-040) –
  `ai.sh` rewrites `ai-local.env`, the limits drop-in and the lines
  of `ai-local.conf` for the installed version (threads per physical core,
  options, `MemoryMax`), restarts `rentalars-ai` only on a change, and only
  hints at a better model, the "host" processor type or `--rebuild`. It
  never downloads, builds, installs packages or changes the model, takes a
  lock, and never fails its caller (warn, exit 0). Two callers:
  `deploy/update.sh` (`bash "${APP_DIR}/deploy/ai.sh" refresh || true`
  after a successful update, not on rollback) and
  **`rentalars-ai-refresh.timer`** (`OnActiveSec=1min`), which starts
  **`rentalars-ai-refresh.service`** about a minute after it is switched
  on – at every boot and when an update enables the new version's timers. The service runs `/bin/bash /opt/rentalars/app/deploy/ai.sh
  refresh` as root from the application directory, as the backup service
  runs its script, with `ConditionPathExists=/etc/rentalars/ai-local.env`;
  the root-run script comes from the installed package, never from the
  network, and Rentalars itself still never gets root.

Both commands have `--dry-run`, which changes nothing; `ai.sh` allows it
without root. Without systemd (a chroot, a container) `address.py` writes
the files and runs `nginx -t` but reloads, restarts and checks nothing,
and says so.

**The scripts do not rely on the execute bit** (NFA-069). A
package unpacked on another computer or copied through a share can lose
it. Therefore:

- `deploy/lib.sh` `install_cli` writes `/usr/local/bin/rentalars` as a
  small script of its own (mode 755), not a symlink:
  `exec /bin/bash /opt/rentalars/app/deploy/rentalars "$@"`. It is written
  through a temporary file and `mv -f`, which replaces an old link as well,
  by `install.sh` and by `refresh_server_configuration` on every update
  and rollback, so the command always runs the active release. An update
  runs the updater of the *installed* release, so an update
  leaves the old link; `deploy/rentalars` therefore replaces a link at
  `/usr/local/bin/rentalars` by the wrapper whenever it runs as root.
- Every script calls the others as `bash script` (`deploy/rentalars`,
  `update.sh`, `install.sh`, `encryption.sh`, `move-database.sh`), and
  `rentalars-backup.service` runs `ExecStart=/bin/bash …/backup.sh`.
- `make_scripts_executable APP_DIR` (in `lib.sh`) sets mode 755 on
  `deploy/*.sh` and `deploy/rentalars`: `build_release` for the new
  release, `update.sh` for the running release before the backup, and
  `go_back` for the previous release before it is switched on again. After
  a rollback the old release's own `rentalars update` runs its own
  `update.sh`, which calls the scripts directly; without this a release
  that had lost its execute bits failed again there (seen in the chroot
  test).

Tested in `tests/acceptance/test_scenario_10_installation.py`.

**The system and the device** (NFA-063, NFA-070). `deploy/lib.sh`
decides in one place on which system the scripts run (`check_system`,
called by `install.sh` before anything is installed), which packages they
install (`system_packages`) and – only on a Raspberry Pi – how many
gunicorn workers and how much MariaDB memory fit (`sizing_for_memory`,
`adapt_workers`, `write_database_memory_settings`, writing
`/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf`) and what lies on the
SD card (`installation_places_on_sd_card`). Each function takes the files
it reads – `/etc/os-release`, `/proc/device-tree/model`, `/proc/meminfo`,
`/sys/dev/block` – as arguments, so `tests/deploy/test_system.sh` runs
them with made-up ones; on an x86 server the scripts do what they did before
(core-flows, section 28).

## Performance: where the care went (NFA-012 to NFA-014)

A project with 500 lines must open in under a second and take a new line in
under half a second, on a small server. Five habits keep it that way; break
one and a test in `tests/acceptance/test_scenario_11_performance.py` fails.

1. **No query per row.** Lists and the planning load what they show for all
   rows at once. The tests count queries: 500 lines need as many as 100.
   This also holds for the numbers in addresses (all read at
   once after three single lookups, `core/converters.py`) and for the
   access log (one lookup and one insert on the first read of a record,
   nothing for a repeat within five minutes). The question
   "has this project parts?" comes with the project itself (an `Exists`
   annotation, `with_parts_flag`), the lines know whether they hand pieces
   on to another part from the same query, the tree of nested groups is
   built without a query (`grouptree.py`), and parts are named with
   `select_related("parent")`. The company name in the menu
   comes with the session user (a subquery in `get_user`), a project
   number of today costs no lookup of former numbers (the converter asks for a former
   number only when today's is not found, and `project_by_number` sorts
   today's first in one query), and the timeline finds projects by their
   phases with one `Exists`. The open items are prefetched and
   the open shortages among them are calculated once for all projects
   (PRJ-098), the utilization in hour columns needs the queries of the day
   view, joining equal neighbouring columns into one cell (VFG-029), taken
   back pieces come with the availability's own query (one more only for
   kits taken back early), the list of packlists for the app needs a
   handful of queries for any number of projects, and the timeline writes
   the session only when a choice changes. The hour tiers are
   arithmetic on what is loaded – the approved entries come with their day
   in the one query per project (`crew.approved_times`), also for the sum
   columns of the project list –, the timeline on the Zeitplanung uses the
   phases and crew lines the page loads anyway, the person of a follow-up
   comes with the project (`project_for`), the mail log sorts and searches
   by the stored mailbox name without a join, and new items find free IDs
   in windows, not one query per number. The unread count of
   the chat comes with the change polling every page asks anyway (one
   aggregate query, none on page load), the surcharge settings are read
   only when a crew line has surcharges, and then once per calculation,
   the approved expenses of the planning page come with the project
   (a subquery annotation) and those of the project list in one query for
   all rows, the hints at times read the entries around the shown ones in
   one query, the readers of a chat take four queries for all users, the
   timeline asks at most one query to know which bars may be dragged, and
   a map reads the positions of all its addresses at once. New measured
   pages of `loadtest.py`: the chat of the big project (300 messages), its
   change question with the chat key, the chat API, the service cases,
   the expense report, the list of expenses in the API, one's own expenses
   and the expense dialog. The surcharge rules cost three
   queries instead of one (settings, rules, own holidays – the last only
   when a rule needs holidays), once per request
   (`core.surcharges.load_rule_set`); the crew lines and participations
   that decide who sees a service case are read in one query; a grouped
   table adds one aggregate query for the group counts. New measured pages
   of `loadtest.py`: Planung → Wiedervorlagen (every tenth load-test
   project has a follow-up) and Mein Bereich → Servicefälle.
2. **Ask the database questions it can answer from an index.** "The product
   of an item is the one named on it, otherwise that of its model" is
   written as two indexed conditions, not as one computed column
   (`material/models.py`, `availability/stock.py`).
3. **Find the rows of a page first, load their details second**
   (`core/listing.py`, `LeanPaginator`).
4. **Send back only what changed, and judge only what is sent.** After a
   line was added, the browser gets the touched groups and the totals, not
   the whole planning; the availability is calculated for those groups only
   (`projects/planning.py`, `build_patch`). What needs all lines – the
   hints above the planning – follows in a second request.
5. **Load once per server, not once per process.** URL table, language file
   and templates are read before the application server splits into its
   workers (`core/warmup.py`).

Measured values and how to repeat the measurement are in
[docs/betrieb/betrieb.md](../betrieb/betrieb.md).
