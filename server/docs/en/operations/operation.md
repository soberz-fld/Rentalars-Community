# Operation

What there is to do on the server day to day – most of it takes care of
itself –, where the settings are and where you look when something is
stuck.

All commands go through the one command `rentalars`:

| Command | Purpose |
|---|---|
| `sudo rentalars status` | Is everything running? Last backup, free space |
| `sudo rentalars backup` | Write a backup now ([backup.md](backup.md)) |
| `sudo rentalars restore FILE` | Restore a backup; an encrypted one from the browser with `--key-file KEYFILE` ([backup.md](backup.md)) |
| `sudo rentalars update PACKAGE` | Install a new version ([updating.md](updating.md)) |
| `sudo rentalars rollback` | Back to the version before the last update |
| `sudo rentalars import_material FILE` | Take over a material list ([import.md](import.md)) |
| `sudo rentalars import_data KIND FILE` | Take over products, customers or personnel from a file; `KIND` is `products`, `customers`, `people` (or `material`). Without `--commit` only a trial run; also `--map FIELD=COLUMN` and `--sheet NAME` ([import.md](import.md)) |
| `sudo rentalars export_data TARGET.zip` | Write all data and files into a ZIP file – the "Readable export of all data" (below, "Full data export") |
| `sudo rentalars run_jobs` | Run waiting background tasks now, then sync the calendars, deliver due webhooks, send notifications about due follow-ups and run waiting automations (below, "Tasks in the background") |
| `sudo rentalars prepare_setup` | New address for the first-run setup |
| `sudo rentalars selfcheck` | Self-check of the installation (below, "Self-check") |
| `sudo rentalars gateway connect\|status\|pair\|devices\|revoke\|disconnect` | Make the apps reachable from the internet through the Rentalars Gateway ([gateway.md](gateway.md)) |
| `sudo rentalars encryption status` | What is encrypted? Also `enable`, `show-key`, `decrypt-backup` ([encryption.md](encryption.md)) |
| `sudo rentalars move-database …` | Move the data into another database (below) |
| `sudo rentalars nginx-site` | Rewrite the NGINX configuration from the template of the installed version (below, "The NGINX configuration") |
| `sudo rentalars address apply TOKEN` | Apply a new address with its certificate as prepared in the settings; with `--dry-run` only show the plan (below, "Changing the server address and certificate") |
| `sudo rentalars ai install` | Set up the local AI; also `status`, `register`, `remove` (below, "AI") |
| `sudo rentalars route install` | Set up the route service for kilometre suggestions – optional; also `update`, `register`, `remove`, `status` (below, "Route service") |
| `sudo rentalars fetch_mail --now` | Fetch the mailboxes of the correspondence now, one line per mailbox (below, "Mailboxes") |
| `sudo rentalars sync_calendars` | Read and write the calendars of the people now, as far as due; `--person ID` for one person, due or not (below, "Calendars of the people") |
| `sudo rentalars ldap_sync` | Compare the accounts with the directory (LDAP): without an option only a dry run, `--apply` writes, `--force` passes the protection limit (below, "Signing in with the directory (LDAP)") |
| `sudo rentalars ai_summaries` | Run the automatic AI summaries now; `--dry-run` only shows, `--project N`, `--limit N`, `--only-in-window` (below, "Automatic AI summaries") |
| `sudo rentalars reset_two_factor NAME` | Switch off the two-factor login of a user who has lost their phone and codes |
| `sudo rentalars measure_performance` | Measure response times, on a test installation; with `--create-test-data` it creates the data volume first (below, "Performance") |
| `sudo rentalars uninstall` | Remove Rentalars from the server: `--dry-run` only shows, `--keep-data` keeps the data, `--purge` also deletes database, backups and configuration after explicit confirmation (below, "Removing Rentalars") |
| `sudo rentalars help` | All other commands |

## Is everything running?

```sh
sudo rentalars status
```

```
==> Rentalars 1.0.0
    rentalars                    active
    nginx                        active
    mariadb                      active
    rentalars-backup.timer       active
    rentalars-jobs.timer         active
    rentalars-mail.timer         active
    rentalars-maintenance.timer  active
    last backup                  /var/backups/rentalars/rentalars-2026-10-12_023000.tar.gz.enc
    Encryption                   database and backups encrypted (rentalars encryption status)
    free space (data)            31G
```

With an existing database server there is a line saying whether it can be
reached ("answers" or "DOES NOT ANSWER") instead of `mariadb`. On a
Raspberry Pi two lines are added: **"Device"** with the model
and the memory, and **"on the SD card"** – what of Rentalars is there
(database, data folder, backups) with the advice "– an SSD would be safer",
or "nothing of Rentalars" ([installation.md](installation.md), "Raspberry
Pi"). If the local AI is set up (below "AI"), `rentalars-ai`
is in the list too.

The command and all scripts on the server speak German if the
locale of the server begins with `de` (`LANG`, `LC_MESSAGES` or `LC_ALL`),
and English otherwise – also with `C.UTF-8`, as many servers are set up.
`RENTALARS_LANG=de` or `RENTALARS_LANG=en` decides explicitly, for example
`sudo RENTALARS_LANG=en rentalars status` ([installation.md](installation.md),
"Installing").

If anything does not say `active`, the section "When something is stuck"
further down helps. Glance at the last backup now and then: it should be
from last night.

After a restart of the server, all services start by themselves.

## What happens by itself

| When | What |
|---|---|
| every night at 2:30 | Backup of the database and the files; backups older than 14 days are deleted |
| every night at 4:15 | Clean-up: expired logins and old entries of the login attempts; once their retention period has run out (below, "Retention periods") entries of the security log, the change log, the access log and the mail log, notifications, results of background tasks with their files (including backups from the browser) and project mails; webhook deliveries after 30 days; runs of automations after one year and remembered map positions of addresses that no record names any more; files of aborted imports after two days; invoices uploaded for "Enter a purchase" but not saved after two days (`/var/lib/rentalars/purchase-invoices/`, below "Uploaded purchase invoices"); videos for the chat still lying in `/var/lib/rentalars/chat-videos/` after two days with no video waiting for them – for example after a crash (below "Photos and videos in the chat"); the counters of API calls after one hour and stored responses of repeated API calls after one day. Time-limited accounts whose period has run out are deactivated (they can no longer log in even before that). If "compare the accounts every night" is on, the comparison of the accounts with the directory (below, "Signing in with the directory (LDAP)"); the temporary store of the old-project PDFs also drops them by itself after 14 days, but when uploading and opening the page, not here (below, "Importing old projects"). The GoBD archive: enter new vouchers and check a part of the files against their checksums (a finding turns the self-check red; Settings → Accounting). Then the checks that report something to someone: products below their minimum stock and inspections of material that have become due (to the warehouse), qualifications that expire in the next 60 days or have expired (to the personnel planners and the person), and problems of the self-check (to the administrators). Minimum stock, inspections and qualifications are reported only once per case. Shortages are checked by the minute timer (below). |
| every minute | Fetching the mailboxes of the correspondence, one after the other – each one as soon as the set interval (default two minutes) has passed since its last fetch and it is switched on (below, "Mailboxes"); the answers of the crew to deployment requests are entered as well |
| every minute | Background tasks that are still waiting or were interrupted by a restart are run (below, "Tasks in the background") |
| every minute, with the same timer | Calendars of the people: linked calendars are read every 30 minutes; deployments are written into CalDAV calendars within one minute of a change and otherwise synced every 30 minutes (below, "Calendars of the people") |
| every minute, with the same timer | Webhooks: due deliveries go to the receiving systems, failed ones are retried (below, "Webhooks") |
| every minute, with the same timer | Follow-ups: when the day of a follow-up has come, the person it is for gets a notification once, from 6:00 local time – in Rentalars and, as they have set it, by mail; if the server was off at that time, straight away at the next run. If the person is deactivated, it goes to the project manager. A due follow-up also triggers automations with this trigger |
| every minute, with the same timer | Automations: runs that are still waiting – for example because Rentalars was just restarting – are caught up on (below, "Automations") |
| every minute, with the same timer | Shortages: at the time and rhythm of Settings → Notifications (by default every day at 4:15, four weeks ahead) the project manager is told about new shortages – only whoever has the special right "See availability of material"; by default also one reminder per project of those already reported ("Still shortages in …"); if the server was off, the check is caught up on once. A minute without a due check costs one database query |
| every minute, with the same timer | Times to approve: at the time set under Settings → Notifications, box "Times to approve" (on by default, daily at 8:00, first reminder one day after handing in, then every day), everyone who may approve times is reminded of the submitted times and expenses they may approve – not of their own; if the server was off, the check is caught up on once |
| every minute, with the same timer | Automatic AI summaries: **only if an administrator has switched them on** – at night (default 1:00 to 5:00) the timer starts the task `ai_auto_summaries` once; otherwise a minute costs one database query (below, "Automatic AI summaries") |
| about a minute after every start of the server | Local AI: `rentalars-ai-refresh.timer` takes over the settings of the installed version (below, "AI"); without a local AI nothing happens |
| twice a day (certbot) | Renewal of the Let's Encrypt certificate as soon as it is due |

If the server was off at the planned time, the task is caught up on at the
next start. There is no separate service for such tasks; timers of the
operating system take care of that (`systemctl list-timers 'rentalars*'`).

**More system mails.** Three new kinds of notification also go
out by e-mail by default: **"Change of my deployment"** (a person was
planned firmly, their deployment changed or they were taken off – one
message per person and action), **"My times approved, corrected or sent
back"** and **"Times waiting for my approval"** (the reminder above). Each
person can switch them off or limit them to "In Rentalars" under My
account → Notifications; an administrator switches the reminder of
approvals off for everyone under Settings → Notifications. Without a mail
server (below, "Without a mail server") they stay in Rentalars.

**More reminders** (VFG-036, DOK-015). Two company settings under Settings →
Notifications are on by default: **"report known shortages again at every
check"** – every shortage check (by default 4:15) reminds once per project
of all shortages already reported, new or grown ones still come one by one
– and **"service cases too"** – the reminder of invoices still to be
written (by default 9:00) also covers done service cases with times or
expenses, namely those done after it was switched on: the moment is noted
(`invoice_cases_since`), cases done earlier only show in the lists. Each
person can also switch off any kind for themselves under My account →
Notifications – every single kind.

## Tasks in the background

Whatever takes longer than a page request – an import and its trial run,
more than 240 labels at once, the full data export, a backup from the
browser, handing an invoice over to Lexware Office (kind
`lexware`), the summary of the correspondence and the reply
draft by the AI (kinds `ai_summary` and `ai_draft`, below "AI"), the AI reading an invoice in "Enter a purchase" (kind `ai_invoice`),
 making a video for the chat smaller (kind `chat_video`, below
"Photos and videos in the chat"), the AI reading an incoming
invoice (kind `ai_incoming_invoice`), reading old invoices in the import of
old projects (kind `legacy_invoices`) and the nightly run of the automatic AI
summaries (kind `ai_auto_summaries`, without a user, below "Automatic AI
summaries") – runs as a background task (NFA-041).
For this Rentalars immediately starts a process of its own
(`manage.py run_jobs --job N`); the page shows how far it has got, and you
can carry on working in the meantime. Whoever started the task gets a
notification when it is finished or has failed, and finds it under
**My account → Tasks in the background**, together with the result to
download. **Only the person who started a task sees it and its result** –
administrators don't see other people's either; a data export contains
everyone's data, after all.

For this there is a timer of its own, `rentalars-jobs.timer`, which starts
`manage.py run_jobs` every minute (service `rentalars-jobs.service`, with
low priority and up to six hours of running time). It runs what could not
start straight away – the task then takes just one minute longer –, and it
notices a task whose process has disappeared, for example because
Rentalars was restarted in the middle of it: every running task records
which process is running it. It restarts a task interrupted like this
**once**; if it is interrupted a second time, it is recorded as failed
("The task was interrupted."). All tasks can cope with that: an import
writes everything or nothing, labels and exports are made afresh. By hand:

```sh
sudo rentalars run_jobs
```

Tasks run side by side, each in its own process – except one kind: a server makes **only one video for the chat smaller at a time**
(kind `chat_video`, lock file `/var/lib/rentalars/chat-videos.lock`). The
process holding the lock works off the waiting videos one after the
other; the others stay waiting until it or the timer picks them up (below,
"Photos and videos in the chat").

The same run also syncs the calendars of the people after the
tasks (below, "Calendars of the people"), it then delivers the
due webhook deliveries (below, "Webhooks"), it sends
notifications about due follow-ups of projects (at most 500 per run, the
rest in the next minute), and it finally runs the waiting runs
of automations (below, "Automations"); an error there doesn't hold up the
tasks. A long task in the same run delays calendars, webhooks, follow-ups
and automations accordingly.

If a task fails, the reason is shown with the task and in the
notification; the error is also counted like any other under "Errors of
the application" (below). What a task outputs is in the log of the service
that started it: `rentalars` for tasks started by a page, `rentalars-jobs`
for those of the timer.

The results – the reports of imports in the database, the files of labels,
data exports and backups from the browser in the data folder under
`/var/lib/rentalars/media/jobs/` – are deleted after the set period, by
default after 7 days (below, "Retention periods"). Until then the files are
also in the nightly backups – except the backups from the browser
(`media/jobs/backups/`): the nightly backup leaves those out, otherwise
every backup would drag the previous one along with it
([backup.md](backup.md), "Backup from the browser").

## Settings

There are two places.

**In the browser**, under "Settings" (the addresses begin with
`/administration/`), for everything to do with the business: company data
and logo with bank details, register details and payment terms for the
documents, buffer times and the usual project times (12:00 to
12:00), rules for passwords and login lockout, retention periods, the
limit for API calls, "ask again when the times change"
(whether personnel automatically get a new deployment request after times
have changed; on by default), also "answer to deployment
requests", the "address of the
warehouse" (start of the trips), "load maps at once", "make invoices in
Rentalars", the limits of the hints at conspicuous times and the travel
costs per kilometre, plus the pages of their own **Surcharges** (nights,
Sundays and public holidays; federal state) and **Automations** (below),
the "largest file to upload (MB)" (below, "Larger files"),
the default storage location for new items (Storage locations),
number ranges (the projects: `2026-0001`; those of the documents: `AN-2026-0001` for quotes,
`AB-…` for order confirmations, `LS-…` for delivery notes, `RE-…` for
invoices and cancellation invoices, `CD-…` for crew schedules, starting
afresh every year), users and roles, categories, tax rates, rental scales,
inspection types, qualification types, document templates and text
blocks, mailboxes and signature, the accounting (Lexware
Office, DATEV) and the webhooks, the "language of documents"
(company data), the language of each account (users), the AI and the page
"Server address and certificate" (below), under Notifications
the reminder of "Times to approve" and under AI the use "Reading invoices"
(below, "AI"), the pages **Audits** (audit interval in months,
24 by default, 0 = off; quick picks for to-dos, at most 12), **Custom
fields** and **Fieldsets**, and under "Mailboxes and signature" the **lock
of new messages** (with lock in projects by default, open in service
cases). This is described in the [user manual](../user-manual.md).

**In the configuration file** `/etc/rentalars/rentalars.conf` for
everything that concerns the environment of the server – and only there
(NFA-032):

| Section | Content |
|---|---|
| `[rentalars]` | Address under which Rentalars can be reached (`url` – it appears in the links of the mails and at the end of every automatic mail; it must begin with `https://`, unless `allow_http = yes`, below "HTTPS and servers in front"; `rentalars address apply` changes it); further names or IP addresses under which Rentalars may be opened (`allowed_hosts`, comma-separated,; also `allow_own_addresses`, below "New IP address of the server"); secret key; language (`language`: `de` or `en` – the language for accounts without a choice of their own, for the login page when the browser asks for neither German nor English, and for the documents and start data of a new installation) and time zone |
| `[database]` | Access to the database (written by the installation script); with an existing server also host, port and TLS |
| `[email]` | Mail server for the system mails (invitations, notifications), as long as no mailbox in the browser has the role "system mails"; without `host` and without such a mailbox Rentalars sends no system mails (below, "Without a mail server") |
| `[backup]` | Where backups go, how long they are kept, whether they are encrypted |
| `[maps]` (optional) | Map server and map search: without the section, those of OpenStreetMap; empty switches the maps off (below, "Maps") |
| `[network]` (optional) | `allow_internal`: internal networks, addresses and hostnames that calendars, webhooks and mail servers of mailboxes may reach nonetheless (below, "Connections into the internal network") |

The **mailboxes** from which Rentalars fetches the project mails and
through which it sends them are not here, but in the browser under
Settings → E-mail ("Mailboxes and signature", below "Mailboxes");
their passwords are stored encrypted in the database. A
mailbox there can also take over the system mails; `[email]` then only
applies while the database cannot be reached.

Every setting is explained in the file itself; a commented-out line shows
the value that applies without it. After a change:

```sh
sudo systemctl restart rentalars
```

The file contains the database password and the secret key. It can only be
read by `root` and the service account; keep it that way.

### HTTPS and servers in front

(NFA-073, from a code review) a production server only starts
if `url` under `[rentalars]` begins with `https://`. With an `http://`
address the start stops with an error message (`journalctl -u rentalars`) –
and so does an update, which then goes back by itself. `install.sh` always
writes `url = https://<Name>`; only a file changed by hand is affected.

- **With the NGINX configuration of the installation** nothing changes:
  NGINX encrypts and tells Rentalars with the header
  `X-Forwarded-Proto: https` that the request came encrypted.
- **Behind another server that does the encryption** (reverse proxy, load
  balancer, firewall): `url` stays `https://…` – the address the users see
  in the browser –, and that server must pass the header
  `X-Forwarded-Proto: https` on to Rentalars (or to the NGINX of the
  installation, which passes it through). If it is missing, Rentalars
  redirects every request to https, and the browser ends up in a loop.
  **The address of the visitor belongs to it:** behind such a
  server Rentalars sees the address of that server with every request, and
  twenty wrong logins of any visitor lock the login for everybody. So enter
  `trusted_proxies = 10.0.0.5` under `[rentalars]` (an address or a network
  such as `10.0.0.0/8`, several separated by commas) and run
  `sudo rentalars nginx-site` (the next update does it as well). NGINX then believes
  `X-Forwarded-For` only for requests from these addresses (file
  `/etc/nginx/snippets/rentalars-realip.conf`, rewritten at every update;
  changes in it are lost). That server must send the address of the visitor
  in `X-Forwarded-For`. Without the entry everything stays as it was.
- **Deliberately without encryption** – for example in a closed network
  without a certificate –: enter `allow_http = yes` under `[rentalars]` and
  run `sudo systemctl restart rentalars`. Passwords and sessions then travel
  through the network in plain text; the self-check warns permanently under
  "Security → HTTPS". For operation from the internet this is never right.

### New IP address of the server

Rentalars answers only to names it knows: the one in `url`, `localhost` and
`127.0.0.1`. Whoever opens it under another name gets
instead of an error page of the server a page that says which name they came
under, which address is entered and what to do. It appears after the IP
address changed (a new DHCP lease, a moved virtual machine) while people
still use the old address or already the new one.

- **The IP addresses of the server itself** need no entry:
  Rentalars reads them from the system (Linux) and answers to each of them,
  also right after a change. That is harmless – an address that belongs to
  this machine cannot be used by an attacker for their own purposes; the
  links in mails always come from `url`. The addresses are read again every
  30 seconds: an address the server no longer has is not answered to after a
  short time. Only the usual spelling of an address counts (`[::1]`, not
  `[0::1]`). The first answer to a new address appears as a note in the
  service log (`journalctl -u rentalars`). One consequence: whoever sends
  requests with made-up addresses from outside can tell from the answer which
  IP addresses the server has. Whoever does not want that enters
  `allow_own_addresses = no` under `[rentalars]` and the addresses that
  should count as `allowed_hosts`.
- **Other names or addresses** – a second host name, an address behind a
  forwarding – you enter under `[rentalars]`:
  `allowed_hosts = 192.168.1.50, rentalars.lan`, comma-separated, without
  `http://`, without port, without path; `.example.de` allows all names below
  `example.de`. A `*` (every name) is not accepted by Rentalars and stops the
  start with a message. Then `sudo systemctl restart rentalars`.
- **If the name in `url` changes** (and with it the certificate), use
  `sudo rentalars address` (above, "Address and certificate"), not
  `allowed_hosts`.

A request to an unknown name is not an error in the error log and sends
no message to the operators; it is a warning in the service log.

### Connections into the internal network

Calendars (ICS links and CalDAV), webhooks, the IMAP and SMTP servers of
the mailboxes and, the servers of the directory (LDAP) and the
interfaces of the AI are entered by someone in the browser, and the server then
connects there. So that nobody can reach systems in your own network this
way that are not meant for it, (NFA-071, from a code review)
Rentalars refuses every target that is **internal**:

- this machine (`127.0.0.0/8`, `::1`, `localhost`) and all addresses of the
  server itself – of its interfaces, its host name and the address from
  `url`;
- private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
  `fc00::/7`), link-local (`169.254.0.0/16`, `fe80::/10`), the providers'
  network (CGNAT, `100.64.0.0/10`), multicast, reserved and unspecified
  addresses and everything else that cannot be reached worldwide, including
  an IPv4 address inside an IPv6 address.

Rentalars resolves the name, keeps only allowed addresses from the answer
and connects to exactly the address it checked – without looking it up a
second time, so that a changed DNS answer gets around nothing; the
certificate is still checked against the name. It follows redirects of a
calendar server only step by step, checking each one anew (at most five);
webhooks follow no redirect. An IP address or `localhost` is already
refused by the forms and the API; a name fails when connecting with "The
address leads into an internal network. …". The messages in the browser
don't name the resolved address, only the self-check does.

**Allowing intended internal targets** – the NAS with the company calendar,
your own Nextcloud, the ERP that receives webhooks, the in-house mail
server:

```ini
[network]
allow_internal = 192.168.1.0/24, nas.local
```

Separated by commas: networks, single addresses or hostnames. A hostname
allows connections to exactly this name, whatever address it resolves to –
but not the same address under another name; for that, use the address or
the network. An entry that is none of these prevents the start with a
message. Afterwards `sudo systemctl restart rentalars`.

**Not affected** is what the operator enters in this file themselves:
`[email]`, `[maps]`, the database – and Lexware Office with its fixed
address.

**CalDAV credentials** (NFA-072) only go to exactly the server – scheme,
host and port – for which they are entered, even with a redirect; Rentalars
does not call up an address on another host that the server names in its
answer. The only exception is iCloud: `caldav.icloud.com` may hand over to
`pNN-caldav.icloud.com` (https, port 443). If another provider redirects to
another host, the person enters the direct address of their calendar there.

**Proxy from the environment:** if `https_proxy` or `http_proxy` applies to
an address, the connection still goes through the proxy. Rentalars checks
the name beforehand, but the proxy resolves it once more itself – against a
changed DNS answer only the proxy protects then. That is why the self-check
warns under "Connections to other servers → Proxy" as soon as the
environment of the service names a proxy. Then block internal targets in
the proxy as well – or leave the proxy out for these targets (`no_proxy`),
so that Rentalars itself connects with the checked address.

**What is already entered** stays, even if it now leads into the internal
network: Rentalars deletes nothing, only the connection fails. The
self-check names such settings in the group "Connections to other servers"
(below, "Self-check").

### Retention periods

How long Rentalars keeps logs and results is set under **Settings →
Company data and settings** (NFA-011). The daily maintenance at 4:15
deletes whatever is older:

| What | Default | adjustable |
|---|---|---|
| Security log (logins, failed attempts, changes to users and roles) | 365 days | 30 to 3,650 days |
| Change log (who changed what when) | permanently (0) | 0 = permanently, otherwise up to 36,500 days |
| Notifications, read or not | 180 days | 7 to 3,650 days |
| Results of background tasks, with their files – including backups from the browser | 7 days | 1 to 365 days |
| Access log (who opened or downloaded customers, people, projects, exports and backups) | 180 days | 30 to 3,650 days |

The period for **project mails** is not here, but with the rules for all
mailboxes (Settings → E-mail, "keep mails for … days"); by default
they are never deleted. The **mail log** also follows it: its
entries stay as long as the mails, and 365 days if the mails are never
deleted. The **webhook deliveries** stay for a fixed 30
days, the **runs of automations** for a fixed year; these
periods cannot be set. Deleted entries are still in the backups until those
are deleted themselves ([backup.md](backup.md)).

### The address changes

An administrator prepares the new address with its certificate
in the browser, and you apply it with one command – below, "Changing the
server address and certificate". By hand it still works: change `url` in
`[rentalars]`, get a certificate for the new name, adjust `server_name`
and the paths of the certificate in `/etc/nginx/sites-available/rentalars`,
then `sudo nginx -t && sudo systemctl reload nginx` and
`sudo systemctl restart rentalars`. If people have subscribed to their
deployments as a calendar, their subscription link (`/calendar-feed/…`)
still points to the old address; it works as long as the old address
redirects, otherwise they subscribe again with the new address (under "My
personnel data"). After the restart, automatic mails name the new address
(below, "Mailboxes"). The Rentalars app on the phones then needs the new
address too (below, "The Rentalars app for Android").

### The NGINX configuration

The installation writes `/etc/nginx/sites-available/rentalars` from the
template `deploy/nginx/rentalars.conf`. An update leaves the file as it is
– you may have adjusted it – and only changes what the installed NGINX
requires (the way HTTP/2 is written). New settings of a later template
therefore don't arrive by themselves; the self-check names the missing
ones.

They can be taken over with

```sh
sudo rentalars nginx-site
```

The command fills the template of the installed version with the name from
the configuration file and the certificate NGINX is using now, shows the
differences and asks. Your own changes to the file are lost in the
process; the previous file is kept as
`/etc/rentalars/nginx-site.before-…`. NGINX is only reloaded if it accepts
the new file – otherwise the previous one stays in force.
`--show` only shows the differences.

### Larger files

How large an uploaded file may be – project file, hall plan, receipt of
expenses, attachment of a sent mail – is set under Settings →
Company data and settings, **"largest file to upload (MB)"**: 50 by
default, at most 500. Rentalars also accepts **show files** of
lighting, media and sound consoles (by their file extension; a show that is
a folder, as a ZIP) – a show with videos or samples is quickly larger than
50 MB. Then raise the value; NGINX accepts up to 510 MB from the template
(`client_max_body_size 510m`), nothing more needs to be set there. Think of
the space: every file is in the data folder and in each of the 14 nightly
backups ([installation.md](installation.md), "Disk space"). Photos and
videos in the chat have limits of their own, fixed in the
program (below, "Photos and videos in the chat").

### Uploaded purchase invoices

A purchase can be entered with its invoice in the material
management ("Enter a purchase"; [user manual](../user-manual.md), section
4). Until the purchase is saved, the uploaded invoice lies in the data
folder under `/var/lib/rentalars/purchase-invoices/` – under a random
name, only for the user who uploaded it, and for two days at most. When
saving, it is stored once under `media/` and attached to every new item;
from then on it is in the backup like any file. Invoices of purchases that
were never saved are deleted by the nightly clean-up after two days
(above, "What happens by itself"), and by the next upload too. The folder
is a temporary store: it is **not** in the backup and need not be
([backup.md](backup.md)). The same size limit applies as for all uploaded
files (above). PDFs with text are read with the library **pypdf** (BSD
licence), which is installed with Rentalars – the update
fetches it with the other libraries; there is no text recognition for
scans.

### Incoming invoices and their files

There is, under **Accounting → Incoming invoices**, the register
of the invoices from suppliers (DOK-023, DOK-024; user manual, Accounting).
Four things matter for operation.

- **Where the files lie:** under `media/incoming/<year>/` in the data folder,
  under a random name; they are downloaded only through Rentalars and only
  by users with material and the right to purchase prices. PDF, PNG, JPEG
  and WEBP are accepted, up to the general size limit ("Larger files",
  above). Unlike the "Uploaded purchase invoices" this is **not a temporary
  store**: the files stay as long as the invoice is in Rentalars, and they
  are **in the nightly backup** ([backup.md](backup.md)). The space needed
  grows with every invoice; take it into account for the backup
  ([installation.md](installation.md), "Disk space").
- **What is read:** from the text of a PDF Rentalars reads number, date, due
  date, a known supplier and the totals with the library pypdf – without AI,
  without anything leaving the server. If the AI is switched on for "Reading
  invoices" (Settings → AI), the **text** also goes to the provider chosen
  there (kind `ai_incoming_invoice`, as a background task, in the AI log
  without content) and returns the positions; with a provider on the
  internet the invoice text leaves your house – as with "Enter a purchase"
  (above, "AI"). **Scans and images are kept but not read**; there is no text
  recognition.
- **Rights:** viewing needs material (read) and the right to purchase prices;
  uploading, editing and booking in need material (write); deleting needs
  material (delete), and only if nothing was booked in. The settings (GWG
  limit, useful life, memory value: **Settings → Incoming invoices**) need
  the Administration module.
- **Nothing is deleted by itself.** Keeping to the legal retention periods for
  invoices is the company's business; Rentalars does not clear incoming
  invoices away. Whoever deletes an invoice deletes the file too.

### Importing old projects: temporary store and retention

Under **Accounting → Import old projects** (PRJ-130; right: see prices and
write projects, user manual) Rentalars takes over old outgoing invoices as
closed projects with a historic invoice.

- **Temporary store:** uploaded PDFs lie in
  `/var/lib/rentalars/legacy-invoices/` until they are taken over, skipped or
  dropped, **14 days at most**. The folder is **not in the backup** and need
  not be (like `purchase-invoices/`, [backup.md](backup.md)). After 14 days
  invoices not taken over are dropped at the next upload or when the page is
  opened, not by the nightly clean-up. Once taken over, the original PDF
  hangs on the historic invoice under `media/` and is backed up.
- **Limits:** up to 30 PDFs per batch, 10 MB each, 120 MB together. Reading
  runs as a background task (kind `legacy_invoices`).
- **AI or patterns:** if the AI is switched on for "Reading invoices", **only
  text** goes to the provider chosen there; otherwise – and if the AI fails –
  Rentalars reads by patterns. With a provider on the internet the texts of
  old invoices with customer names and addresses leave your house (data
  processing agreement, see "Data protection" under "Automatic AI
  summaries"). To start with: a few PDFs, and read the preview critically.
  **How well the AI reads real invoices from other systems has not been
  verified.**
- **Quiet operation:** taking over sends no mails and creates no tasks,
  reservations, availability, automations or webhooks; the running invoice
  number is untouched, the projects get a number of their own,
  `ALT-<year>-<nnnn>`. Historic documents are **not** in the DATEV export
  unless the option "include historic documents" is on (API
  `include_historic`); they cannot be booked or cancelled and are not in
  the error list for Lexware.
- **Undo** works within 7 days if nothing was changed on what was taken
  over. After that a project is deleted as always.
- **Cost:** 4.6 seconds were measured for reading 30 PDFs, 2.3 seconds and
  369 queries for the page of a batch, and 5.0 seconds for confirming 30
  invoices.

### Scanning and the camera

Labels and barcodes can be scanned in the material list, when
packing and with the planning wishes (MAT-027, UIX-006, PCK-010, PCK-011; user
manual).

- **The field "Scan or type an ID" always works.** A USB or Bluetooth scanner
  "types" into the field like a keyboard; nothing is needed on the server.
- **The camera of the phone or tablet is an extra** and needs two things.
  First **HTTPS**: browsers release the camera only to a page with a secure
  connection (`https://…`; `localhost` counts too). Rentalars is always set
  up with HTTPS ([installation.md](installation.md), "Name and
  certificate"); behind a server of your own in front, its address must be
  `https://` too. Whether a browser allows the camera with a self-issued
  certificate that the device does not trust has not been verified – a
  certificate from Let's Encrypt, or your certificate authority on the
  device, is the safe way. Whoever opens Rentalars over `http://` cannot use
  the camera and types or uses the USB scanner. Second **a browser with
  `BarcodeDetector`**: Chrome, Edge and browsers on Android. Firefox and
  Safari do not have it; typing and the USB scanner remain there. There is no
  fallback with a library in the browser (jsQR).
- **The header `Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=()`**
  allows the camera only to the pages of Rentalars itself and to no page
  embedded in them; microphone, location and payment are blocked for all.
  Rentalars sets it on every response itself (not NGINX; the supplied NGINX
  template does not change it). If another server or proxy stands in front
  of Rentalars, it must not remove the header or replace it with
  `camera=()`, otherwise the browser does not ask for the camera. Check:

  ```sh
  curl -sI https://rentalars.example.de/ | grep -i permissions-policy
  ```

- **Data protection:** no camera image leaves the browser; recognition is on
  the device, only the text read (the ID) goes to the server.
- **The QR codes of the labels** point to `{RENTALARS_URL}/m/<ID>` (`url` of
  the configuration file); to change the target, enter it under Settings →
  Label settings at "QR code leads to" (an address with `{id}`, API field
  `qr_target`). Whoever scans a label needs the rights to the material;
  without the right Rentalars answers as for "not found".
- **Not really tested:** camera, BarcodeDetector, printed labels and scanner
  hardware – the tests use simulated input.

### Price offers of freelancers

(PER-038) a freelancer can answer a deployment request with a
price of their own. The function is **off**: a request is answered with
"accept" or "decline" as before, and nothing changes until an administrator
switches on "Freelancers may offer their own price" under **Settings → Price
offers of freelancers** (`/administration/price-offers/`). There are also
"temporary staff too" (otherwise freelancers only), the lowest and the
highest offer in percent of the stored rate (empty = no limit) and the
number of proposals per request (default 4, 1 to 10; offers and
counter-offers together).

- While the function is on, the mail for the request gets a line with a
  link: "Want to name your own price? You can make an offer in Rentalars:".
  Switching off removes it; earlier offers stay visible.
- Amounts are personnel costs: the freelancer sees only their own offers, and
  the stored rate only with the right to personnel costs or if "people may
  see their own hourly rates" applies. Without the right to personnel costs
  the planning shows nothing of offers, and notifications go only to users
  with that right who may read the project.
- An acceptance sets the cost rate of **exactly this** line; the customer
  price does not change. It ends when someone changes the rate by hand or
  person or function change.
- Limits: 30 offer actions per user and hour, two decimal places, euros only.
- In the companion app the new kinds of notification are **not** on by
  default; whoever wants them there switches them on under My account →
  Notifications.

### Photos and videos in the chat

(UIX-049, NFA-076) a chat message can carry photos and videos
([user manual](../user-manual.md), section 7, "Chat in the project"). The
server keeps only a smaller version.

**ffmpeg is a required package.** Rentalars makes videos smaller with
`ffmpeg` and checks them with `ffprobe` first; both come with the Ubuntu
package **ffmpeg**. `install.sh` installs it with the other packages. The
update sets it up as well (the old `update.sh` does not
know it; the new `ai.sh refresh`, which it calls after switching over,
installs missing packages of the new version), and waits up to two minutes
for a running package manager for this – such as the automatic security
updates. If that fails, the update completes with a warning; then by hand:

```sh
sudo apt install ffmpeg
```

or `sudo rentalars ai refresh`. Without ffmpeg Rentalars keeps running;
only videos are refused – the form tells the users so, photos work (Pillow
makes them smaller inside the program). Details on the update:
[updating.md](updating.md).

**The self-check warns** (below, "Self-check"):

- group "Versions", row **"ffmpeg"**: the version, or the warning "ffmpeg
  is not installed: videos in the chat are refused, photos work. Install it
  with: sudo apt install ffmpeg";
- group "Security", row **"NGINX upload limit"**: if `client_max_body_size`
  of the NGINX site is smaller than a video in the chat (200 MB plus 1 MB
  for the form). The template accepts 510 MB (above, "Larger files"); a
  site made smaller by hand takes the template over again with
  `sudo rentalars nginx-site` (above, "The NGINX configuration").

**Limits** (fixed in the program, not adjustable and independent of
"largest file to upload"): up to 10 files per message, photos up to 25 MB,
videos up to 200 MB and 20 minutes, together up to 500 MB. The content is
checked, not the extension: a photo must open with Pillow (JPEG, PNG, GIF,
WebP), a video must be recognisable at the start of the file as
MP4/QuickTime, Matroska/WebM or AVI and pass `ffprobe` with exactly this
format and only the file protocol.

So that a small file cannot keep the server busy for long or fill its
memory, the following holds as well:

- **Photos:** first the size in bytes, then format and pixel count from
  the header of the file – before anything is decoded. A photo in PNG, GIF
  or WebP is decoded whole by Pillow; it may therefore have at most
  **16 megapixels** (that is 64 MB in memory). A larger one is refused,
  with the advice to send it as JPEG. A JPEG may have up to
  **150 megapixels**: Rentalars decodes it reduced straight away (to a
  half, a quarter or an eighth, so that the long side still has 2048
  pixels).
- **Videos:** refused if the picture has more than **4096 pixels** on one
  side, more than **240 frames per second** or more than **72,000
  frames** (20 minutes at 60 frames per second). For the 20 minutes the
  longest of the durations of the file and the video stream counts – the
  file alone could claim a few seconds for an hour of video –, and ffmpeg
  converts at most 20 minutes anyway.

**What is stored:**

- **Photos** are turned upright straight away on upload, reduced to at most
  2048 pixels on the long side and stored as JPEG **with the place
  only** (the GPS position stays; device, time and comment are removed), plus a
  preview of 640 pixels without the place. The same for the photos of defect
  reports, expense receipts and material.
- **Videos** are converted as a background task (kind `chat_video`, above
  "Tasks in the background") with ffmpeg to at most 720p, 30 frames per second,
  H.264/AAC in MP4, without metadata, plus a poster frame. ffmpeg runs with
  a lower priority (`nice -n 10`) and for at most one hour per video. The
  task has no starter who would get a "ready" notification; if making it
  smaller fails, the video is discarded, the message says so, and whoever
  sent it gets a notification.
- **One video after the other.** Every conversion takes one or two cores
  and a lot of memory, for up to an hour; ten videos at once would bring
  the server to a halt. So on a server only one process converts at a
  time: it holds the lock file `/var/lib/rentalars/chat-videos.lock`
  (`DATA_DIR/chat-videos.lock`, `flock`) and then works off the waiting
  videos one after the other; a video that does not get the lock stays
  as a waiting task, and its message shows "Video is being made smaller …"
  correspondingly longer. When the process ends – also by a crash – the
  system releases the lock, and the minute timer (above, "Tasks in the
  background") picks up the rest.
- **When a video counts as failed:** if it still shows "being made
  smaller" after three hours and there is no waiting or running task for
  it any more – for example after a restart in the middle of the task –,
  it counts as failed. If its task still waits in line or runs, only
  after 24 hours.

**Where it is:**

| What | Where | In the backup |
|---|---|---|
| Smaller photos and videos with their previews | `/var/lib/rentalars/media/chat/<project>/` (`MEDIA_ROOT/chat/…`), under random names | yes, like every stored file; also in the readable export |
| Uploaded videos waiting to be made smaller, and the temporary files of ffmpeg | `/var/lib/rentalars/chat-videos/` (`DATA_DIR/chat-videos`) | no |
| Lock file: only one video is made smaller at a time | `/var/lib/rentalars/chat-videos.lock` (`DATA_DIR/chat-videos.lock`), empty | no |

Rentalars deletes the original of a video as soon as the small version is
stored or making it smaller has failed. What is left in the folder
`chat-videos/` because no video waits for it any more – for example after a
crash – is deleted by Rentalars after two days, namely by the nightly
clean-up (`run_daily_maintenance`, above "What happens by itself") and
likewise by the next upload of a video. The empty lock file stays. Deleted messages
take their files with them, also when a whole project is deleted. The files
leave the server only through Rentalars, after it has checked that the
user may read the chat.

**Space and computing time.** A converted video has at most about
3 Mbit/s, i.e. roughly 23 MB per minute; while it is being made smaller,
the original and the temporary file are in the data folder as well.
Converting costs computing time – on a Raspberry Pi a long video takes
correspondingly longer –; the lower priority keeps the pages fast. The
photos and videos are in every nightly backup
([installation.md](installation.md), "Disk space").

### Font of the labels

Rentalars prints the labels for label printers in
**Liberation Sans** (version 2.1.5, SIL Open Font License 1.1) –
metrically the same as Arial, the font of the P-touch templates. The font
comes with Rentalars (`static/fonts/LiberationSans-Regular.ttf` with the
licence `LiberationSans-OFL.txt`; listed in `THIRD-PARTY.md`); nothing
needs to be installed on the server for it, and browser and PDF use the
same file – printed from the browser and as a PDF the labels look the
same.

## Certificate

**Let's Encrypt over port 80** (choice 1 at installation) and **with DNS
credentials** (`--dns-plugin`): it renews itself. To check:

```sh
sudo certbot certificates          # shows the expiry date
sudo certbot renew --dry-run       # tries out the renewal
```

**Let's Encrypt with a DNS record created by hand** (choice 2 without
`--dns-plugin`): it is valid for 90 days and does **not** renew itself.
Put a reminder in your calendar for about 60 days later and then repeat:

```sh
sudo certbot certonly --manual --preferred-challenges dns -d rentalars.example.de
sudo systemctl reload nginx
```

**Your own certificate**: replace `/etc/rentalars/tls/certificate.pem` and
`/etc/rentalars/tls/private-key.pem` and reload NGINX. This
also works through Settings → Server address and certificate: enter the
same host name, choose "Own certificate", upload the new certificate and
key and run the command shown (below). This is also how you switch the
kind, say from a self-signed certificate to Let's Encrypt. Which
certificate NGINX presents now and how long it is valid is shown on the
same page.

## Changing the server address and certificate

An administrator prepares a new address in the browser –
**Settings → Server address and certificate**, described in the
[user manual](../user-manual.md), section 16 – and you apply it on the
server with exactly the one command the page shows. Rentalars itself never
gets root rights for this and never stores access data for root; what
needs root is done by this command, which you run via SSH.

```sh
sudo rentalars address apply 3f2a9c…   --dry-run   # only check and show the plan
sudo rentalars address apply 3f2a9c…               # show, ask [y/N], apply
sudo rentalars address apply 3f2a9c…   --yes       # without asking
```

**What the command does,** in this order, saying at each step what is
happening:

1. **Read and check again.** It fetches the prepared change through
   `manage.py address_change export`, run as the service account, and
   checks everything itself: token, spelling of the host name, kind of
   certificate, e-mail address; for your own certificate, with openssl,
   whether the key matches, every link of the chain, the name and the
   validity at the present moment. If the old name is not in the NGINX
   site, it stops here, before changing anything.
2. **Back up** the configuration file, the NGINX site and
   `/etc/rentalars/tls` to `/etc/rentalars/address-backup/<time>-<token>/`.
3. **Get the certificate:** Let's Encrypt through certbot with the check
   over port 80 (certbot is installed if it is missing), a self-signed one
   with openssl (825 days, as at installation) or the uploaded one. New
   certificates go to `/etc/rentalars/tls/<name>/`, the key readable by
   root only; old files are never overwritten. With "A server in front
   encrypts" the certificates stay as they are.
4. **Write:** in the NGINX site only the `server_name` lines that name the
   old name and the lines of the certificate; in the configuration file
   `url` under `[rentalars]` – Rentalars also takes from it the names it
   answers to. With "Redirect the old address to the new one", a block per
   old name that redirects is added at the end of the site: over HTTP
   always (the path for Let's Encrypt stays reachable, so an old Let's
   Encrypt certificate keeps renewing), over HTTPS as long as the old
   certificate is valid for the old name. Later changes redirect all
   earlier names to the newest; if you go back to an old name, its block
   is removed.
5. **Check and restart:** `nginx -t`, reload NGINX, restart Rentalars;
   then it checks that Rentalars answers and that `/login/` answers under
   the new name over HTTPS with the new certificate.
6. **Back on any error:** every file is put back, NGINX reloaded,
   Rentalars restarted, and it says what went wrong.

It records the result through `manage.py address_change record`; the page
then shows "Applied on … by …" with the name from `SUDO_USER` – or the
error. A failed change can be run again once the cause is fixed.
`--dry-run` shows the plan with the differences in the NGINX site and
records nothing. Without systemd (in a container or a chroot), the command
writes the files and checks with `nginx -t`, but reloads nothing and does
not check over HTTPS – and says so.

**Why root only reads what the service account prints:** the command opens
no file in the service account's folders; the prepared change reaches it
only as the output of `manage.py address_change export`. A link planted in
the data folder cannot steer it to other files that way. Uploaded
certificates and keys wait in `<data folder>/address/<token>/` (folder
0700, files 0600, the key additionally encrypted like other stored
secrets); they are deleted after a successful apply or when a newer
preparation replaces the previous one. The token is valid only for this
one change and is left out of the full data export.

**Afterwards:** everybody logs in again at the new address; links in new
mails name the new address. Calendar subscriptions, printed QR codes and
the Rentalars app on the phones (below, "The Rentalars app for Android")
point to the old one until someone changes them – they work as long as the
old address redirects. For Let's Encrypt, port 80 must be reachable from
the internet, as at installation.

**What the command cannot do:**

- **Let's Encrypt with a DNS record** (`install.sh --tls dns`) and a port
  other than 443 cannot be prepared in the browser. For those, take the
  way by hand (above, "The address changes").
- **Removing a redirect:** delete the block of the old name at the end of
  the NGINX site by hand, then `sudo nginx -t && sudo systemctl reload
  nginx`; an old Let's Encrypt certificate with
  `sudo certbot delete --cert-name OLD-NAME`.
- **`sudo rentalars nginx-site`** rewrites the site from the template and
  leaves out the redirect blocks; it shows the differences before doing
  anything.
- NGINX 1.24 may report "protocol options redefined" when checking,
  because the redirect blocks do not repeat `http2`. That is only a
  warning; a later update adds it.

## AI

Rentalars can summarise the correspondence of a project – with
a **local AI**: a small language model running as a service of its own on
this server. The mails do not leave the server, and it costs nothing per
use, only memory and electricity. Whether Rentalars uses it is switched on
by administrators under **Settings → AI**; that is also where the
interfaces to other language models are entered in the browser
([user manual](../user-manual.md), section 16, "AI"). Without AI,
Rentalars shows a short overview of the correspondence; none of this needs
the server.

The AI can also **read invoices**: in "Enter a purchase" the
text of an uploaded purchase invoice (PDFs with text only) goes to the
language model chosen under Settings → AI for "Reading invoices" – off by
default. It suggests supplier, invoice number, date and positions;
Rentalars checks the answer strictly (at most 100 positions, expected
fields only) and creates nothing before someone has confirmed every row.
The reading runs as a background task (kind `ai_invoice`) and is in the
log of the AI calls without content. With the local AI the invoice does
not leave the server; if someone chooses an interface on the internet,
the page warns in red that the text of the invoice – prices, your
customer number, addresses – leaves the company when it is read. Without
AI, Rentalars takes only the invoice number, the date, a known supplier
and the totals of the invoice from the text.

The **request to the AI is longer**: it also names the
categories a bought model can get (up to 150) and up to 40 own products –
no customer material; with more products those whose names share words
with the invoice –, as a data block of their own, so that the AI can
suggest category and product; it also asks for serial numbers and
totals. The **answer may be up to 3,500 tokens** long. The two lists take at most a third of the room the AI's context
leaves after instructions and answer, the text of the invoice the rest.
With the local AI and its context of 8,192 tokens (below, "Model and
resources") this leaves less room for a long invoice; if its end does not
fit, the proposal says so ("The invoice is too long: its end was not
read. Enter the last positions by hand."). Through an interface on the
internet the names of the categories and of these products go out along
with the invoice. The
AI copies amounts as the invoice prints them; Rentalars reads them itself
and checks them against the text of the invoice.

The setting "Reading invoices" also applies to **incoming
invoices** and to the **import of old projects** (below, "Incoming invoices
and their files" and "Importing old projects"), and the AI can **summarise
projects and service cases by itself at night** (below, "Automatic AI
summaries", with notes on data protection and information security).

### Setting it up

```sh
sudo rentalars ai install --dry-run    # show what would happen – also without root
sudo rentalars ai install              # set it up
```

Then in the browser: Settings → AI → "Switch summaries with local AI on",
and check with "Measure the speed" how fast it answers. Rentalars does not
need a restart.

The command

1. checks the system (Ubuntu 24.04 or 26.04, Raspberry Pi OS based on
   Debian 13; 64 bit), the memory and the free space;
2. checks the processor: physical and logical cores and – on
   x86-64 – whether **AVX2** and **FMA** are there (below, "Processor and
   virtual machines");
3. chooses the model by memory, physical cores and processor (below);
4. installs `llama-server` from llama.cpp – on Ubuntu 26.04 from the
   package `llama.cpp-tools`, on Ubuntu 24.04 and Raspberry Pi OS from
   source: it fetches exactly release b8681, checks its commit and builds
   it with cmake (for this it installs `git`, `cmake` and
   `build-essential`; on a Raspberry Pi that takes 15 to 40 minutes). A
   `llama-server` built before is kept; `--rebuild` builds it again;
5. downloads the model and checks its SHA-256 checksum; it deletes a model
   used before as soon as the new one answers;
6. starts it as the service `rentalars-ai`, reachable only on 127.0.0.1
   (port 8093), with **one thread per physical core** and the model's
   thinking switched off (`--reasoning off --reasoning-budget 0`, if
   `llama-server --help` lists them);
7. writes to `/etc/rentalars/ai-local.conf` where the local AI can be
   reached, and sends a test question that measures reading and writing
   speed. Rentalars reads the file at every use.

Options: `--model qwen3-1.7b`, `--model qwen3-4b`, `--model qwen2.5-1.5b`
(the small model) or `--model FILE.gguf` (a model that is already
on the server – for example without internet; with `--sha256 CHECKSUM` if
you like), `--port N`, `--threads N`, `--keep-model` (keep the previous
model after a change), `--rebuild` (build llama.cpp again, for example
after the processor type of a virtual machine was set to "host"; only
where it is built from source).

**Changing the model:** `sudo rentalars ai install --model qwen3-1.7b` (or
`qwen3-4b`). A `llama-server` built before is not built again; the
previous model is deleted as soon as the new one answers, unless you give
`--keep-model`. Then use "Measure the speed" in the browser.

**A server of your own** such as Ollama or LM Studio that already runs on
this machine becomes the local AI with `sudo rentalars ai register --url
http://127.0.0.1:PORT/v1 --model NAME`; the address must be on this
machine.

```sh
sudo rentalars ai status               # model, server, processor, threads, options, whether it answers
sudo rentalars ai refresh              # take over the settings of the new version (the update does it itself)
sudo rentalars ai remove               # remove service, program, models
sudo rentalars ai remove --keep-model  # keep the models
```

`remove` stops the service, removes its files and the packages `install`
installed itself; the build tools stay. Rentalars then no longer
summarises with the local AI; the short overview stays.

### After an update: `ai refresh`

The update takes over the settings of the local AI by itself (`sudo
rentalars ai refresh`; also about a minute after every start of the
server). You do not have to install it again after an update.

- **What `refresh` does:** only for a local AI that `ai install` set up
  here (with `ai register` or without an AI it does nothing). It reads the
  processor again and rewrites `ai-local.env` and the limits of the
  service: threads per physical core, the options `llama-server --help`
  lists (`--reasoning off --reasoning-budget 0 --jinja --no-webui`),
  `MemoryMax` of the model; in `ai-local.conf` it adds `server_kind`,
  `physical_cores` and `threads`. It restarts `rentalars-ai` only if
  something changed, and waits up to 120 seconds for it to answer. It
  reports one line – "Local AI: settings taken over (thinking off, 4
  threads)." or "Local AI: unchanged." –; `--dry-run` only shows what it
  would do.
- **What it never does:** download, build, install packages or change the
  model. The model never changes by itself (a large file); if another one
  suits the machine better, `refresh` only names the command (`sudo
  rentalars ai install --model …`). Without AVX2/FMA it gives the hint
  about the processor type "host"; if a `llama-server` built here lacks
  AVX2 that the processor now has, the hint `sudo rentalars ai install
  --rebuild`.
- **Errors** never stop the update: `refresh` warns and exits with 0. A
  lock keeps the update and the timer from running it at the same time.
- **Who starts it:** `rentalars update` after every successful update (not
  when going back), and `rentalars-ai-refresh.timer` about a minute after
  every start of the server and after an update has switched on the
  timers of the new version. So it also applies after the
  processor type of a virtual machine was changed. The service
  `rentalars-ai-refresh.service` runs as root, like the backup, and only
  if `/etc/rentalars/ai-local.env` exists; it runs `deploy/ai.sh refresh`
  from the application directory. Rentalars itself never gets root rights
  from this.
- **llama-server itself:** on Ubuntu 26.04 it comes from the Ubuntu
  package and is updated with the normal system updates; on 24.04 and
  Raspberry Pi OS it is built again only when you say so (`sudo rentalars
  ai install --rebuild`, e.g. after the processor type of a virtual
  machine was set to "host"). For older builds it is unknown what
  they were built with ("built with: unknown" in `ai status`); if you have
  changed the processor type since, run `--rebuild` once.

### Model and resources

All models are from Qwen (Alibaba Cloud), licence Apache 2.0, which also
allows commercial use, and handle English and German. They are reduced to
four bits (Q4_K_M) and take up to 8,192 tokens at once; Rentalars
summarises longer correspondence in parts and then the parts. Qwen3 1.7B
is the conversion by the llama.cpp project (ggml-org), because Qwen itself
offers this size only as Q8_0.

`ai install` chooses the model by memory, physical cores and
processor:

| Server | Model (file) | Memory limit of the service (`MemoryMax`) |
|---|---|---|
| below 1.5 GB of memory | – the command refuses | – |
| from 6 GB, at least four physical cores and AVX2/FMA (or a 64-bit ARM server that is not a Raspberry Pi) | Qwen3 4B (2.4 GB) | 5 GB |
| all others – such as every Raspberry Pi, a virtual machine without AVX2/FMA | Qwen3 1.7B (1.3 GB) | 3 GB |
| only on request (`--model qwen2.5-1.5b`, the small model) | Qwen2.5 1.5B Instruct (1.1 GB) | 2 GB |

An existing installation keeps its model; you change it with `--model`
(above).

- **Processor:** the service uses **one thread per physical
  core** (at most 16; a second thread on the same core does not make it
  faster) and is limited to them
  with `CPUQuota`. It runs with lower priority (`Nice=10`, low weight for
  processor and disk); Rentalars and the database come first. During a
  summary the cores are still busy, and on a Raspberry Pi the pages then
  react a little more slowly.
- **Processor and virtual machines:** on x86-64 the model is fast only
  with the instructions **AVX2** and **FMA**; without them it runs many
  times slower. A virtual machine often hides them: Proxmox gives new
  machines the processor type "x86-64-v2-AES" (earlier "kvm64"), which has
  neither. Remedy: in Proxmox under Hardware → Processors choose the type
  **"host"** – or **"x86-64-v3"** if the machine is to move between the
  hosts of a cluster – and **shut the machine down in Proxmox and start it
  again** (a restart inside the machine is not enough). To check inside
  the machine: `grep -o -w 'avx2\|fma' /proc/cpuinfo | sort | uniq -c` –
  one hit per core of the machine; if nothing appears, they are missing.
  `ai install`, `ai status` and Settings → AI warn when they are missing.
- **Memory:** the service keeps the model in memory as long as it runs.
  `MemoryMax` is in `/etc/systemd/system/rentalars-ai.service.d/` and
  limits it; for a model of your own the command sets twice the file plus
  2 GB. Count on the rest for Rentalars, MariaDB and the system: on a Pi
  with 4 GB about 2 GB remain, on one with 8 GB about 3 GB. If it gets
  tight, take a smaller model (`--model qwen3-1.7b`, at a pinch
  `--model qwen2.5-1.5b`).
- **Disk:** the model plus 300 MB, when building from source plus 1.5 GB,
  under `/opt/rentalars/ai`.
- **Speed:** "Measure the speed" under Settings → AI measures
  separately how fast the AI reads (the mails) and writes (the answer), in
  tokens per second; every later call keeps the values up to date. From
  them Rentalars estimates the duration before every summary and warns
  from five minutes. Below 6 tokens per second writing or 30 reading – or
  without AVX2/FMA – the page recommends the smaller model Qwen3 1.7B with
  the command to copy. Answers stream in: the AI is only stopped after 180
  seconds without a word (before the first word after three times the
  estimated reading time plus 60 seconds, without a measurement after 30
  minutes); the whole task ends at the latest at three times its estimate
  (at least 10 minutes, without a measurement 3 hours). On a Raspberry Pi
  a summary takes a few minutes, on an x86 server with AVX2 much less (see
  [updating.md](updating.md), "Testing").

### Automatic AI summaries

(EML-056) Rentalars can summarise the correspondence of
projects and service cases by itself at night, so that in the morning the
summary of the new mails is already there. The function is **off** until an
administrator agrees under **Settings → AI → Automatic summaries → Open**
(`/administration/ai/automatic/`). It uses the same path and the same
provider as the button "Summarise" on the project (Settings → AI, use
"summary").

**How it runs**

- The timer that starts `run_jobs` every minute (`rentalars-jobs.timer`)
  checks whether it is night within the window (default 01:00 to 05:00,
  local time), whether tonight has already run and whether the function is
  on; a minute without a due run costs one database query. If everything
  holds, it starts the task `ai_auto_summaries` (kind, as in "Tasks in the
  background") as a process of its own; a lock in the database makes sure
  two runs never work at the same time. **There is no new timer and no new
  service.**
- A project or service case is summarised if its readable correspondence
  (mails, notes, and if allowed the chat) has **changed** since the last
  summary. What is compared is a checksum of the input, not a time: without
  a change there is no call of the model, so no cost. A summary made by hand
  is never overwritten unmarked by the run; earlier versions stay (default 5).
- The summary carries "created automatically", model, provider and time. On
  the project a note says if newer mails arrived since, and there is
  "Summarise again". It is visible to everyone who may read all messages of
  the project.
- Errors do not stop the run: if a single summary fails, the project is
  tried again the next night. If the provider cannot be reached at all (or
  every summary fails), the timer tries again after 20 minutes, three times
  a night at most. Administrators see the runs and errors on the page of
  the automatic summaries; there are no notifications for them.

**Settings** (Settings → AI → Automatic summaries):

| Setting | Default |
|---|---|
| Automatic summaries | off; the consent applies to the **server** the texts go to (the local AI, or scheme, host and port of the provider) – if it changes, an administrator must agree again; another model or display name changes nothing |
| Window | 01:00 to 05:00 |
| Most summaries per night | 20 |
| **Token budget per night** (tokens read and written; 0 = unlimited) | 200,000 – the run stops when it is reached |
| Statuses of projects | open ones: inquiry, option, confirmed (open), confirmed, out, returned |
| Statuses of service cases | open, in progress, waiting, closing |
| Least time between two summaries | 20 hours |
| Least number of mails | 2 |
| Earlier summaries kept | 5 |
| Include: notes / chat / messages with lock | notes **on**, chat **off**, messages with lock **on** (`auto_include_locked`) |
| Exclusion | per project and per customer: buttons "No automatic summaries for this project" and "… for any project of this customer" under the summary |
| "Show what would be summarised" | dry run: no request to the model, nothing stored |

The run works as the service account `system:ai-summaries` with the
smallest scope needed: mails and notes; chat and prices only after release.
It reads messages with lock (the lock of the correspondence, EML-055) by
default, because in projects every message starts with the lock and the run
would otherwise read almost nothing; the summary is shown only to those who
may read all messages. Whoever does not want this switches the setting off.

**By hand and to try it out**

```sh
sudo rentalars ai_summaries --dry-run        # lists what would be summarised; calls no model
sudo rentalars ai_summaries --project 42     # only this project (number)
sudo rentalars ai_summaries --limit 5        # at most five
sudo rentalars ai_summaries                  # run now (the consent is needed)
sudo rentalars ai_summaries --only-in-window # do nothing outside the window
```

Without consent, and when a run is already under way, the command says
"Nothing done: the automatic summaries are off, or another run is under way."
On the page the same run is "Run now". The result of every run is on the
page and, as a background task, in the log (`sudo journalctl -u
rentalars-jobs -n 30`).

**Cost and duration.** With the local AI a run costs only computing time,
and that is large or small depending on the machine (Settings → AI →
"Measure the speed" shows how fast it is). Set window and maximum so that
the run is finished before work starts. With a provider on the internet the
token budget decides the cost per night – work it out with the provider's
price. On the project page the display needs 2 to 3 queries more.

#### Data protection and data processing agreement

- **With the local AI** (`sudo rentalars ai install`) nothing leaves the
  server.
- **With a provider on the internet** mails and notes of the project go to
  another company. That is personal data of third parties (customers,
  contacts, crew). For this you usually need a **data processing agreement**
  under Art. 28 GDPR with the provider, clarification of **where** it
  processes (transfer to a third country) and whether it uses the data for
  training, an entry in your record of processing activities and possibly a
  note in your privacy statement. You clarify this yourselves, best with your
  data protection officer – Rentalars does not replace that, and this
  section is not legal advice.
- **What is removed before sending** (Settings → AI, "taken out of the
  texts", per data class): IBAN, card numbers, credentials and keys (e.g.
  passwords, tokens), e-mail addresses and telephone numbers. This is on by
  default. **What is not removed:** names and addresses in the running text –
  they cannot be recognised reliably and go along when a provider on the
  internet is switched on. The names of attached files go along on request
  ("names of attached files", on by default).
- **Consent:** when switching on, the administrator confirms which data go
  to which server. If the server changes (local, or scheme, host and port of
  the provider), the consent ends until it is renewed.
- **Excluding customers and projects:** single projects or customers can be
  excluded (for example especially confidential ones).
- **Information and deletion:** the export of a customer's data and their
  anonymisation cover the summaries and their earlier versions. The log of
  the AI calls never contains content, only use, model, duration, size and
  counters; the entries are kept for 365 days.

#### Information security

The path to the AI provider was reviewed (NFA-079). **Fixed and built in:**

- **Data minimisation:** data classes are removed before sending (above) –
  on all paths: summary by hand, at night and reply draft.
- **Service account with the smallest scope:** the night run reads mails and
  notes; chat and prices only if an administrator releases them.
- **Injected instructions** (prompt injection): texts from mails are not
  trustworthy. Delimiters, special tokens and invisible characters are
  defused, the instruction to the model stays separate from the text, and
  the answer of the model never triggers an action (it is only text).
- **The answer** is cleaned to plain text and escaped when shown: no HTML, no
  images, no links.
- **Limits:** calls by hand are limited per user and hour (setting
  "summaries by hand per user and hour", default 30), the night run has the
  token budget and the maximum; the length of the input (150,000 characters,
  the oldest mails drop out) and of the answer is limited.
- **Connection:** providers on the internet only with `https://` (`http://`
  is refused when saving), no redirects, no access to addresses in your own
  network without `[network] allow_internal` (above, "Connections into the
  internal network"). The API key is stored encrypted in the database and
  appears in no log and no error page.
- **Traceable:** who triggered what is in the log – with counters instead of
  content; reply drafts use the same filtered texts.

**Open points – you carry them until they are solved:**

- **No allow-list of provider hosts per operator.** An administrator can
  enter any `https://` address as a provider. Only the firewall of the server
  helps against that: allow outbound traffic only to the address of the
  provider you chose. (A setting `[ai] allowed_hosts` does not exist.)
- **Names and addresses in the running text** go to the provider when it is
  switched on (not solvable).
- **Edited or deleted chat messages** do not make a summary "out of date".
  (If the chat is included, a new chat message does.)
- **Errors and inventions of the models** cannot be ruled out. The interface
  points it out; a summary does not replace reading the mails.
- **Error texts of the provider** may appear in the error messages of the
  task (`journalctl`), not in the log of the AI calls.
- **Messages with lock (the lock)** are read by the night run by default
  (above).
- **Not verified:** a real provider on the internet, the lock column of the
  runs under MariaDB and the systemd timer; testing was done with a
  simulated model.

### What lives where

| What | Where |
|---|---|
| Program, models, source | `/opt/rentalars/ai/` (`bin/`, `models/`, `src/`) |
| For Rentalars: address, model, kind of server, physical cores, threads, what `llama-server` was built with (`built_with`) | `/etc/rentalars/ai-local.conf` (root, readable by all; only addresses on this machine are accepted) |
| For the service: model, port, threads, options | `/etc/rentalars/ai-local.env` |
| The service | `rentalars-ai.service`, limits in `rentalars-ai.service.d/` |
| Taking over the settings after an update and a start | `rentalars-ai-refresh.service` and `rentalars-ai-refresh.timer` |
| Log of the service | `sudo journalctl -u rentalars-ai -n 50`, for `refresh`: `sudo journalctl -u rentalars-ai-refresh` |

The service file comes with every version; without `ai-local.env` and
without `llama-server` the service does not start. It runs under a user of
its own without rights (`DynamicUser`), only reads the model, writes
nowhere and reaches nothing but this machine.

**Backup:** program and models are **not** in the backup, nor are
`ai-local.conf` and `ai-local.env` ([backup.md](backup.md)). What is set
in the browser – switched on or not, the interfaces with their encrypted
API keys, summaries and log – is in the database and comes back with it.
After restoring on a new server, set the local AI up again with
`sudo rentalars ai install`.

**Interfaces from the browser** (OpenAI-compatible, such as Ollama in the
company network or a cloud service) are checked by Rentalars like
calendars and webhooks: an address in the internal network – even one on
this machine – only works if allowed under `[network] allow_internal`
(above, "Connections into the internal network"); redirects are not
followed. Rentalars accepts only an address with `https://` for
an interface on the internet: `http://` is already refused when saving,
because mails and key would otherwise go out unencrypted. Only the local AI
from `ai-local.conf` needs no allowance,
because the operator set it up. With a cloud service, mails – and, if
"Reading invoices" uses it, the text of purchase invoices – go to its
provider; the page warns about it. Every call is in the log of the AI
calls (Settings → AI) – with use, model, duration and size, never the
content; the entries are kept for 365 days.

## Signing in with the directory (LDAP)

(AUT-029) users can sign in with the name and password of
their directory – Active Directory or an LDAP server such as OpenLDAP.
Rentalars asks the directory at every login; the password of the directory
is never stored in Rentalars. The function is **off** until an
administrator switches it on under **Settings → Directory (LDAP)**
(`/administration/ldap/`); until then nothing changes. Accounts the
directory creates get their roles from the groups of the directory (user
manual, the section on the directory).

**Tried** are logins against a simulated directory (the `MOCK_SYNC` mode of
the library ldap3) and against a real, locally running OpenLDAP (`slapd`;
the test is optional, `RENTALARS_SLAPD=1`). **Not tried** is it against an
Active Directory – the examples for it below are put together from the
documentation of AD. Try them with "Test login for a user" before you
switch the function on.

### What the server needs

- **The libraries `ldap3` and `pyasn1`** come with the installation and with
  every update ([updating.md](updating.md)); you
  install nothing.
- **A connection** from the Rentalars server to the directory: port 636
  (`ldaps://`) or 389 (`ldap://`, with StartTLS). `ldap://` **without** StartTLS
  sends passwords in the clear: the page, the API and the connection test warn
  about it. The firewall in between must allow it. Check it from the server before you enter anything in the
  browser:

  ```sh
  openssl s_client -connect dc1.example.com:636 -servername dc1.example.com </dev/null | head -20
  ldapsearch -x -H ldaps://dc1.example.com -D "CN=svc-rentalars,OU=Service,DC=example,DC=com" -W \
      -b "OU=Staff,DC=example,DC=com" "(sAMAccountName=anna)" dn memberOf
  ```

  (`ldapsearch` is in the package `ldap-utils`; Rentalars does not need it.)
- **The server by its name, not by IP address.** The library compares the
  name of the certificate only with its DNS entries; against an IP address
  the check of the certificate fails ("TLS", below). So enter
  `ldaps://dc1.example.com`, never `ldaps://10.0.0.5`.
- **Allow internal servers.** The directory is almost always in your own
  network. Like calendars, webhooks and mail servers, Rentalars does not
  connect to addresses in the internal network unless the operator allows
  them (above, "Connections into the internal network"). In
  `/etc/rentalars/rentalars.conf`:

  ```ini
  [network]
  allow_internal = dc1.example.com, dc2.example.com
  ```

  A host name allows connections to exactly this name, whatever address it
  resolves to; a network (`10.0.0.0/24`) allows all addresses in it. Then
  `sudo systemctl restart rentalars`. Without the allowance the form
  already refuses the address, or the connection fails with "blocked".
- **A search account** in the directory that may read users and their
  groups (it need not be an administrator). Rentalars stores its password
  encrypted with the `secret_key` of the configuration file and never shows
  it again; another `secret_key` makes it unreadable (then enter it again).
  If the servers or the DN of the search account change, Rentalars discards
  the password.
- **The certificate of the directory:** if your company's certificate
  authority is not in the system, enter the path of the file on the server
  (`/etc/ssl/certs/company-ca.pem`) or paste the certificate (PEM) into the
  form. **The path (`ca_certificate_path`) must be absolute and name a
  readable file in PEM format** that the service `rentalars` may read;
  otherwise the page refuses it ("There is no such file on the server.", "This
  is not a file that Rentalars can read.", "The file holds no certificate in PEM
  format."). A pasted certificate must be PEM as well. The check of the
  certificate is on; switch it off only for a test.

### Setting it up

1. **The emergency access first:** open an administrator under Settings →
   Users and set "local (emergency) account". This account always signs in
   with its own Rentalars password; the directory never asks about it and
   never changes it. It is the way in when the directory fails or the
   settings are wrong. Rentalars lets you switch the local login off only if
   such an account exists.
2. **Settings → Directory (LDAP):** servers (one entry per line; several are
   tried one after the other), StartTLS, certificate, search account (DN and
   password), search base and filter for users, the attributes, the group
   search, time limit (default 8 seconds). **Leave "link existing accounts by
   name" off** (see "What happens then"). Do not switch it on yet.
3. **"Test connection".** It reports whether the server answers, the
   encryption works and the search account can log in.
4. **Groups and roles:** in the table assign one or several roles to a group
   (DN), with a priority; "last match" ends the evaluation at this row. **Use
   the full DN** of the group, at most **480 characters** (longer is refused;
   the limit applies to the compared key with its prefix so that it fits the
   column MariaDB has to keep unique). A bare name (`admins`) matches a group
   of that name *anywhere* in the directory, also where others can write; the
   page warns (in the API `name_only` and `warning`). Existing assignments by
   name keep working.
5. **"Test login for a user"** (a dry run without effect): you enter a login
   name (and, if you want it checked, the password) and see the DN found,
   the attributes read, the groups and the roles that would result. This is
   the tool against "I cannot get in".
6. **Switch it on.** Whoever signs in now is asked in the directory first.
   Keep "Allow login with a local password" on at first; switch it off only
   when everyone gets in through the directory.

### What happens then

- **Roles** from several groups are united and follow the groups at **every
  login**. A role the directory gives cannot be removed by hand in
  Rentalars; roles someone was given by hand stay.
- **New accounts** are created at the first login – but only if the groups of
  the user result in at least one role. Whoever is in no assigned group gets
  no account.
- **Existing accounts (`link_existing_accounts`, default off).** A user of the
  directory whose name equals an account of Rentalars that is not linked to the
  directory yet is **refused**, because a name in the directory is no proof
  that it is the same person, and whoever can choose a name there freely could
  take over an account. To bring such accounts into the directory, switch the
  setting on (the page warns in red while it is on), let the people sign in
  once, and switch it off again; linked accounts keep signing in. The login
  page tells the user only that it did not work; the reason is in the security
  log and in the test. The
  directory never takes local emergency accounts or accounts with "has all
  rights", not even through the DN, and the comparison leaves them out; the link
  is cleared as soon as an account becomes local or gets all rights.
- **Moved entries:** if the DN of a user changes in the directory, the user is
  refused, because their account hangs on the old entry. The login test then
  offers "Adopt the new entry" (API `POST /ldap/adopt-dn`); it links the
  account anew – only if the old entry no longer exists in the directory – and is
  noted in the history of the account.
- **After switching LDAP off,** accounts that existed only in the directory are
  not stranded: an administrator can invite them or set a password for them.
- **Deactivating:** if someone leaves the assigned groups, their account is
  deactivated at the next login – only if the directory had activated it;
  what an administrator deactivated in Rentalars stays deactivated. The last
  administrator who may change the settings is never deactivated or stripped
  of roles.
- **No password in Rentalars:** directory accounts change, set and renew their
  password in the directory; "forgot password", invitation and password
  change do not exist for them. With two-factor login the password of the
  directory comes first, then the code of Rentalars.
- **Protection:** the typed name is escaped and normalised before it goes
  into the filter; an empty password never reaches the directory (many
  servers would accept it as an anonymous login); passwords are in no log; the
  limit on attempts and the lock apply as with the local login. "Test login
  for a user" counts as well (API: answer 429) and is entered in the security
  log as `ldap_test`; for protected names a dummy bind runs so that the time of
  the answer gives nothing away. The security log (Settings → Security log) has
  six new kinds: "directory login refused", "directory not reachable", "account
  created or changed by the directory", "roles changed by the directory",
  "accounts compared with the directory" and "directory login tried by an
  administrator". The bind password of the search account is not in the full
  data export either.

### Examples

**OpenLDAP** (`inetOrgPerson`, groups as `groupOfNames`):

| Field | Value |
|---|---|
| Server | `ldaps://ldap.example.com` |
| Search account | `cn=rentalars,ou=service,dc=example,dc=com` |
| Search base for users | `ou=people,dc=example,dc=com` |
| Filter for users | `(&(objectClass=inetOrgPerson)(uid={username}))` |
| Attributes | login name `uid`, e-mail `mail`, first name `givenName`, last name `sn` |
| Groups | "Search in the groups", base `ou=groups,dc=example,dc=com`, filter `(&(objectClass=groupOfNames)(member={user_dn}))` |
| Assignment | `cn=rentalars-admin,ou=groups,dc=example,dc=com` → Administrator |

With `posixGroup` the group filter is
`(&(objectClass=posixGroup)(memberUid={username}))`. If the server has the
overlay `memberof`, the attribute `memberOf` is enough instead of the search.

**Active Directory:**

| Field | Value |
|---|---|
| Server | `ldaps://dc1.example.com` (second entry: `ldaps://dc2.example.com`) |
| Search account | `CN=svc-rentalars,OU=Service,DC=example,DC=com` |
| Search base for users | `OU=Staff,DC=example,DC=com` (or `DC=example,DC=com`) |
| Filter for users | `(&(objectClass=person)(sAMAccountName={username}))` (default) |
| Attributes | `sAMAccountName`, `mail`, `givenName`, `sn` (defaults) |
| Groups | "Attribute of the user (memberOf)", attribute `memberOf` (default) |
| Assignment | `CN=Rentalars-Admins,OU=Groups,DC=example,DC=com` → Administrator |

The login name is the name without the domain (`anna`, not
`EXAMPLE\anna` and not the e-mail address). Two hints from the AD
documentation that are **not verified**: `objectClass=person` also matches
computer accounts; a filter such as
`(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))` is
narrower. And `memberOf` lists only groups the user is a **direct** member
of. For **nested groups** use the group search with the rule for chained
membership (`LDAP_MATCHING_RULE_IN_CHAIN`), base `DC=example,DC=com`, filter
`(&(objectClass=group)(member:1.2.840.113556.1.4.1941:={user_dn}))`.

### Comparison and daily maintenance: `ldap_sync`

Without a comparison, roles and activation change only at the person's next
login. The command compares all accounts the directory keeps:

```sh
sudo rentalars ldap_sync               # dry run: only shows what would change
sudo rentalars ldap_sync --apply       # writes the differences
sudo rentalars ldap_sync --apply --force   # even if more than half would be deactivated
```

One line per account that differs ("anna: update … roles A -> B", "karl:
deactivate (no longer in the directory)"), the total last. Names, e-mail
address and roles are brought into line; whoever has disappeared from the
directory or is in no assigned group is deactivated (and activated again if
the directory had deactivated them and they return). Accounts are **never
created** here (that happens at login); local accounts, accounts with
"has all rights" and the last administrator are left alone. **Protection limit:** if more than three
accounts and more than half of them would be deactivated, the command
writes nothing and ends with a message – that looks like a wrong filter or a
directory that does not answer. Check the settings first, then use `--force`
if need be. The page has the same function: "Show the differences" and
"Apply these changes".

**Every night:** with the setting **"Compare the accounts every night"**
(off by default) the daily maintenance does the same at 4:15 with `--apply`
but without `--force`. Its line is in the log:

```sh
sudo journalctl -u rentalars-maintenance -n 30 | grep -i ldap
```

The time and total of the last comparison are also on the settings page. If
the directory cannot be reached at night, the log says "comparison failed
(unreachable)", the security log has an entry "directory not reachable", and
nothing is changed. Any other, unexpected error ends only the comparison: it is
in the log with its traceback ("comparison failed (unexpected error, see the
log)"), and the rest of the daily maintenance goes on.

### If logging in does not work

"Test connection" and "Test login for a user" name the reason with one of
these identifiers; administrators also see them in the security log. Users
see only a general text on the login page.

| Identifier | Meaning | Check |
|---|---|---|
| `unreachable` | the server does not answer or the name is unknown | address and port, firewall, DNS from the Rentalars server (`getent hosts dc1.example.com`), `openssl s_client` as above |
| `blocked` | the address leads into an internal network | `[network] allow_internal` with the **name** of the server, then `sudo systemctl restart rentalars` |
| `tls` | encryption or certificate refused | CA certificate (path or PEM); the name in the certificate must be the name entered, **not an IP address**; certificate expired; `ldaps://` with port 636, `ldap://` with StartTLS and port 389 – do not mix |
| `service_bind` | the search account cannot log in | DN and password; is a password entered? Enter it again after a change of the `secret_key`; account locked or expired |
| `search` | the search fails | does the search base exist ("The search base … does not exist")? May the search account read there? Brackets of the filter right? |
| `ambiguous` | the filter finds more than one entry | narrow the filter, choose a smaller search base |
| `entry` | the entry is not usable | the attribute for the login name is missing, or the name is too long (it is refused, not cut) |
| "refused despite the right password" | the user was found but has no role | "Test login for a user" shows the groups and the roles: is the group in the table? Is the DN of the group right (the case of the parts does not matter)? For AD and nested groups see above |
| "not linked" (`not_linked`) | an account of this name exists in Rentalars that is not linked to the directory | intended while "link existing accounts by name" is off; otherwise switch it on, let the person sign in once, switch it off again |
| "moved" (`moved`) | the account hangs on another entry (DN changed) | in the test "Adopt the new entry", if the old entry no longer exists |
| "protected" (`protected`) | local emergency account or "has all rights" | intended: these accounts sign in only with their Rentalars password |
| "account deactivated" | the directory deactivated it (no longer in an assigned group) or an administrator did in Rentalars | check the groups; an administrator activates the account again if they had deactivated it |

**All logins fail and the local one is switched off:** sign in with the
local emergency account (step 1 above) and switch "Allow login with a local
password" back on under Settings → Directory (LDAP), or switch the directory
off. If the emergency account has forgotten its password, set it anew on the
server: `sudo rentalars changepassword NAME` (above, "When something is
stuck"). An account the directory keeps has no password in Rentalars and is
the wrong way for this: create an emergency account while the directory
still answers.

## Logs

| What | Command |
|---|---|
| Messages of Rentalars (errors, requests, e-mails not sent) | `sudo journalctl -u rentalars -n 100` |
| follow as it happens | `sudo journalctl -u rentalars -f` |
| the nightly backup | `sudo journalctl -u rentalars-backup -n 30` |
| fetching the mailboxes (one line per mailbox and run) | `sudo journalctl -u rentalars-mail -n 30` |
| background tasks that the timer ran or restarted (those started by a page – including handovers to Lexware Office – are with `rentalars`), and program errors when syncing the calendars, delivering the webhooks and catching up on automations | `sudo journalctl -u rentalars-jobs -n 30` |
| the daily maintenance (what was deleted and reported) | `sudo journalctl -u rentalars-maintenance -n 30` |
| the local AI (only if set up) | `sudo journalctl -u rentalars-ai -n 50` |
| NGINX | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| slow database queries (over 1 second) | `/var/log/mysql/rentalars-slow.log` |

Who changed what in the data and when is not here, but in the program:
"Settings → Change log". Logins, failed attempts, two-factor login,
ended sessions and one-time passwords that were set are under
"Settings → Security log" (AUT-022). There are two more
logs in the browser, both with filters and as CSV:

- **Settings → Mail log** (EML-039): every mail that came in or went
  out – project mails as well as system mails (invitations, password links,
  notifications, the test mail) –, with the time, sender, recipients,
  subject, project and result, and in case of an error with the message of
  the mail server; also with the **mailbox** through which the
  mail came or went (empty for system mails through `[email]`), and the
  result "inquiry" for mails without a tag; with the result
  "answer to a deployment request" (accepted or declined, yellow with a
  reason if not taken over) for answers of the crew by mail (below,
  "Mailboxes"). Every entry remembers the name of the mailbox;
  if it is deleted, it shows with "(deleted)". A system mail
  that did not go out for lack of a mail server shows with the result "not
  sent – no mail server set up" (below, "Without a
  mail server"). It does not keep the text of the mails. This is the first
  place to look when someone says "the invitation never arrived" – or "my
  acceptance didn't arrive".
- **Settings → Access log** (AUT-028): who opened customers, people
  and projects with their mails, files and documents, who downloaded lists
  as CSV, the full export or a backup – in the browser as well as through
  the API, with the time and the IP address. The same access by the same
  person within five minutes counts once; what someone looks at about
  themselves is not in it, nor is what commands on the server read.

How long both are kept is above under "Retention periods".

## Self-check

In the browser under **Settings → Self-check**, on the server with

```sh
sudo rentalars selfcheck
```

Rentalars checks the state of the installation (NFA-037) and says "ok",
"note", "warning" or "error" for each point:

| Group | What is checked |
|---|---|
| Versions | Rentalars, Python, Django, Ubuntu, NGINX, ffmpeg (a warning if it is missing – then only videos in the chat are refused; above, "Photos and videos in the chat") |
| Server | Processors and load over the last 1, 5 and 15 minutes (warning if the load over 5 minutes is more than twice the number of cores – then requests are waiting for a processor), memory (warning if less than a tenth is free), memory of Rentalars (all worker processes together), host name, network per interface with addresses and amount of data since the start, running time since the last restart; on a Raspberry Pi the line "Device" with the model – a note if it has less than 4 GB. Read from `/proc`; whatever is missing there, the self-check leaves out |
| Database | Connection; missing changes to the tables; with an existing server: rights of the user (only this database), encrypted connection; whether the server encrypts its files |
| Files | Rights of the configuration file, the data folder and the recovery key |
| E-mail | System mails: through which mailbox or which mail server from `[email]` they go (warning if none is set up – with the text "No mail server set up: invitations, password links and notifications are not sent." and the way to a mailbox for system mails or to `[email]`); per active mailbox of the correspondence a line "Mailbox "Name"" with the last successful fetch (warning if it was more than five intervals, at least 15 minutes, ago) or the last error; without such a mailbox the note "Mailboxes: not set up" or, if there are only switched-off ones, "Mailboxes: none switched on" |
| Gateway | If a gateway is connected (`rentalars gateway connect`): its address, whether it answers (error if the last answer is older than 90 seconds – the service `rentalars-gateway-link` is not running; warning while no answer has come yet), the last error, the number of paired and revoked apps and an announced move. Without a gateway one line "none – the apps reach the server directly". The check reads the database only and does not call the gateway; it does not check when the certificate of the gateway expires (`rentalars gateway status` asks the gateway) |
| Backup | Age of the last backup (warning from 25 hours, error from 50), encrypted, free space |
| Storage | free space for the data (warning below 2 GB, error below 300 MB); on a Raspberry Pi the note "SD card" if the database, the data folder or the backups are on the SD card (or the eMMC of a Compute Module) – a note, not a warning, so that a Pi deliberately set up like that doesn't stay yellow for good |
| Security | Debug mode off, "HTTPS" – the address with https (a warning if `allow_http = yes` allows unencrypted HTTP; above, "HTTPS and servers in front"), secret key long enough, two-factor login for administrators, logout after inactivity, the secure settings of the NGINX template; "NGINX upload limit" – a warning if NGINX accepts smaller requests than the largest file to upload and, than a video in the chat (200 MB) |
| Connections to other servers | "Internal addresses": every setting from the browser – linked calendar, CalDAV calendar, active webhook (named with its description or host, never with the path), IMAP and SMTP server of an active mailbox, every interface of the AI ("AI interface Name") – that leads into the internal network, with the resolved address and the kind of network (warning; at most ten named, then "… and n more"); "Allowed internal addresses": what is under `[network] allow_internal` (above, "Connections into the internal network") |
| Errors of the application | what went wrong in the last seven days, with a count |

The command ends with exit code 1 on an error – so a monitoring tool can
call it regularly. The API returns the same under `/api/v1/self-check`,
 with the values of the server under `resources`.

In the browser, "Send a test mail to me" sends a mail to your own address –
that way you can check the sending without having to go onto the server.
Without a mail server the page says "Not sent – no mail server set
up." instead of reporting success.

### Without a mail server

If no active mailbox has the role "system mails" and there is no `host`
under `[email]`, Rentalars only writes system mails into the log of the
service (`sudo journalctl -u rentalars -n 100`) – with
`rentalars@localhost` as the sender, the default of `from_address`. So
nothing can arrive. (EML-048):

- The mail log calls it "not sent – no mail server set up"; it doesn't
  count as sent, and a notification doesn't count as sent by mail.
- Whoever sends something in the browser – test mail, invitation, new
  password link, deployment request – gets the warning with a link to
  Settings → Mailboxes and signature; the mailboxes page and the mail
  log show it at the top.
- The API says so too: `POST /api/v1/users/{id}/send-invitation` then
  answers 200 with `{"sent": false, "reason": …}` instead of 204, `POST
  /api/v1/users` names `invitation`, the deployment request `mail_sent` and
  `mail_reason`.
- The self-check warns (above).

"No mail server" means: no active, complete mailbox with the role "system
mails", and in Django a sending route that only logs (without `host` under
`[email]`). A mailbox of the correspondence with its own SMTP server sends
project mails regardless. Remedy: give a mailbox in the browser the role
"system mails", or fill in `[email]` in the configuration file and run
`sudo systemctl restart rentalars`.

## Errors of the application

If something goes wrong in Rentalars – a program error, a mail server that
doesn't answer –, that is in the log as before
(`sudo journalctl -u rentalars`). In addition, Rentalars counts every error
in the database and **notifies the administrators** (NFA-018): the first
time it occurs, in the application and, unless they have switched it off,
by e-mail. If the same error occurs again, it is only counted; there is a
new message only after 24 hours. The list is in the self-check.

## Mailboxes

Rentalars fetches the project mails itself (EML-005) and sends the mails
written in projects itself. It works with any number of
existing mailboxes for this, for example `projekte@eure-firma.example` and
`info@eure-firma.example` (EML-041, EML-042). They are set up in the browser
under **Settings → E-mail → "Mailboxes and signature"**, one page per
mailbox ("Add mailbox", "Edit"). Whoever may edit the E-mail module may
create and change them; whoever may delete in it may delete them (by
default only the role Administrator). No mailbox is in the configuration
file.

Every mailbox has a name (it appears in the list, in the mail log and with
the inquiries), its address, "active" – switched off, it is neither fetched
nor used for sending – and its **roles**:

| Role | Meaning | how many |
|---|---|---|
| Correspondence | is fetched; mails with a project tag in the subject go into the project; answers of the crew to deployment requests are recognised | any number |
| Sends the correspondence | mails written in projects go out through it, with its address as the sender | exactly one of the active mailboxes of the correspondence |
| System mails | invitations, password links, notifications, deployment requests, the test mail | at most one |

A mailbox may have several roles, for example correspondence, sending and
system mails at once. If you give a mailbox the sending role or the system
mails, the previous one gives up that role; the page says so. Without a
mailbox for system mails, these go through the mail server from `[email]`
of the configuration file – likewise when the database
cannot be reached. With such a mailbox they keep the sender name from
`[email]` and get the address of the mailbox.

**The note at the end of the system mails** (EML-045). Every
mail that Rentalars sends of its own accord – notifications, invitations,
password links, deployment requests and the replies to answers by mail,
messages about errors and background tasks, the test mail of the
self-check, also the answers of automations (below) –, ends
with

```
-- 
This message was sent automatically by Rentalars for Muster Veranstaltungstechnik: https://rentalars.example.de
```

The company name comes from Settings → Company data and settings (if
it is missing, the sentence appears without "for …"), the address from
`url` under `[rentalars]` of the configuration file – the same address that
is in the links of the mails. There is no environment variable of its own
for it (the value is called `RENTALARS_URL` only internally, in the Django
settings); after a change to the file, `sudo systemctl restart
rentalars`. The sentence is added to the mail in the sending route that all
system mails pass through (the mail backend of Rentalars), whether they go
out through a mailbox "system mails" or through `[email]`: in the text
after the usual separator line `-- `, in an HTML mail as the last
paragraph, with the address as a link, and only once per mail. Mails
written in projects (sent through the mailbox that sends the
correspondence) don't get it; they carry the signature.

For each mailbox of the correspondence you also set:

- **"take in mails without project tag"** (off by default). Switched on,
  mails without a tag appear as **inquiries** under Projects → Inquiries;
  they too stay in the inbox until someone takes them over into a project.
  Switched off, Rentalars doesn't touch them. (EML-049) this only applies from a point in time: **"taken in from"** is
  set to that moment when switching on and can be changed; **"only unread
  mails"** only takes in mails without `\Seen`. What counts is when the
  mail arrived in the mailbox (IMAP `INTERNALDATE`, without it the `Date`
  header); a mail without any date stays where it is as long as a point in
  time is set. Fetching gets this information along with the headers
  (`FLAGS INTERNALDATE`), without an extra request. What stays behind this
  way is listed in the mail log as "left in the inbox" with the reason. The
  same is available for each further address.
- **"assigned mails in the mailbox"**: mark as read and move into a folder
  (by default "Rentalars"; it is created if it is missing),
  only mark as read (the mail stays in the inbox – except the reply to a
  deployment request, which is moved to the folder as well), delete – only if
  Rentalars is the only place where the mails are kept – or leave them
  unchanged in the inbox, not even marked as read.
- **"Receiving (IMAP)"** with the inbox folder and **"Sending (SMTP)"**,
  optionally with the user and password of receiving (default).

What applies to all is on the same page under **"Rules for all
mailboxes"**: "fetch every … minutes" (default 2), "largest mail (MB)" and
"keep mails for … days". Below it, it says how deployment requests are
answered and to which mailbox answers by mail go; this is set
under Settings → Company data and settings (below, "Deployment
requests by reply mail").
Passwords are stored encrypted and never shown again.
If an IMAP or SMTP server is in the internal network (the in-house mail
server), it needs to be allowed under `[network]
allow_internal` (above, "Connections into the internal network") – this
also applies to the mailbox "system mails", but not to `[email]`. When the
details are entered, the form doesn't check the name; "Check connection"
shows the refusal.

**Fetching.** The timer `rentalars-mail.timer` starts `fetch_mail` every
minute. It fetches every active mailbox of the correspondence, one after
the other, as soon as the interval has passed since its last fetch. What
happens then is in the [user manual](../user-manual.md), "Correspondence";
in short: Rentalars first looks whether a mail is an **answer
to a deployment request** (below); it takes such mails from every mailbox
it fetches. Mails with a project tag in the subject and answers to mails
that were taken over go into the project and are then handled – like the
answers to deployment requests – as the mailbox says. Mails with an unknown
tag – and, where switched on, mails without a tag – wait under Projects →
Inquiries. Everything else stays in the inbox as it is. If the same mail is
in two mailboxes, it is taken over once and appears once in the list.
(EML-047) a mailbox can have **further addresses** (aliases)
with their own rule for mails without a tag; fetching reads which address
was meant from `Delivered-To`, `X-Original-To`, `To` and `Cc`. Such a mail
can create a service case straight away. This is set up in the browser
(user manual, "Further addresses of a mailbox").

**Status and errors.** Every mailbox has its own status. The list under
"Mailboxes and signature" shows for each mailbox its roles, active or off,
the last successful fetch and the last error. **"Check connection"** logs
in to IMAP and SMTP without changing or sending anything; **"Fetch now"**
fetches all mailboxes of the correspondence immediately. If a mailbox is stuck –
wrong password, server not reachable –, the others are still fetched. The
error appears with the name of the mailbox in the list, on the start page
and in the self-check, and the administrators get **one** notification
per mailbox ("Mails of Projekte cannot be fetched: …"), not a new one for
every attempt. The mail log shows which mails came and went through which
mailbox (above, "Logs"). To trigger fetching by hand and see one line per
mailbox:

```sh
sudo rentalars fetch_mail --now
```

```
Projekte: 3 new mails looked at; 2 assigned, 0 with an unknown tag, 0 inquiries.
1 answer to a deployment request by mail.
Info: 5 new mails looked at; 0 assigned, 0 with an unknown tag, 4 inquiries.
```

The line with the answers to deployment requests only appears if there
were any. If a mailbox could not be fetched, the error appears below it,
and the command ends with exit code 1. "Fetch now" in the browser names the
answers too.

**Deleting** (EML-046). Every mailbox can be deleted, even if
mails have already come or gone through it. "Delete mailbox" leads to a
page that says beforehand what will follow; there you can also just switch
it off instead. When it is deleted

- the project mails and the entries in the mail log stay and keep naming
  the mailbox by its name – they carry the name themselves, in the log with
  "(deleted)";
- inquiries and mails with an unknown tag waiting in that mailbox disappear
  from Projects → Inquiries; they stay on the mail server;
- no mailbox has its roles any more: Rentalars no longer fetches mails in
  it, and without another mailbox for system mails these go through
  `[email]` of the configuration file. Answers to deployment requests that
  went to this mailbox no longer arrive;
- for sending the correspondence, another mailbox of the correspondence
  that can send takes over: if there is only one, that happens by itself;
  if there are several, you choose it on the page (in the API with
  `?successor=<id>`). If none can send, Rentalars refuses the deletion with
  the reason.

A mailbox that was only switched off on deletion stays in the
list switched off and can now be deleted.

**Deployment requests by reply mail** (PER-032). The crew can
answer a deployment request by mail instead of through the link in
Rentalars. For this Rentalars does **not need to be reachable from the
internet**: the request contains the buttons "Accept" and "Decline" – links
that open a prepared mail with a code in the subject, for example
`[RA-E-…-JA]` –, and Rentalars fetches the answer itself when fetching, by
IMAP from the inside out like every project mail. The code is random (120
bits), applies to exactly one request to exactly one person and is stored
with it. How answers are given is set under Settings → Company data
and settings → **"answer to deployment requests"** (whoever may edit the settings may
change it):

| Setting | the request contains |
|---|---|
| "by the link in the browser" | only the link to Rentalars |
| "by reply mail" | only the buttons – right if Rentalars can only be reached in your own network or over VPN; there the link would lead nowhere from outside |
| "both" (default) | buttons and link |

- **The mailbox for the answers** is the one for the system mails if it is
  at the same time an active mailbox of the correspondence with an address,
  otherwise the one that sends the correspondence. The page names it below
  the setting. If there is none, the requests only contain the link,
  whatever is set; with such a mailbox the buttons are added by themselves.
- **The request mail** goes the route of the system mails (mailbox "system
  mails" or `[email]`), as text and HTML, with the mailbox for the answers
  as `Reply-To` – that way a freely worded answer lands in a mailbox that
  someone reads – and with `Auto-Submitted: auto-generated`. It replaces
  the previous notification mail about the request and goes to every active
  person with an e-mail address, including people who cannot log in;
  whoever has switched off the mails about deployment requests gets none.
- **When fetching**, Rentalars recognises the answers in **every** mailbox
  it fetches – whether it takes in mails without a project tag or not –,
  enters the acceptance or refusal together with a remark (up to 250
  characters), as if the person had answered in the browser, and then
  handles the mail like an assigned one: move, delete or leave it. It does
  not appear in the project as a mail. Rentalars doesn't evaluate freely
  worded answers ("Yes"). If the request has already been answered, is
  over, withdrawn or replaced by a newer one, or if the project is
  cancelled or closed, nothing changes.
- **Reply:** the person gets a confirmation or the reason why nothing was
  taken over – always to their stored address, never to a foreign sender,
  without the code and with `Auto-Submitted`. An out-of-office reply that
  quotes the code doesn't count as an answer; that way no loop arises.
- **Tracing:** the mail log lists every answer as "answer to a deployment
  request", the history of the project "Answer of … came by reply mail".
- **Sender:** The code is not enough. The request stores the
  address it was sent to (`CrewRequestMail.sent_to`; for older requests the person's current
  address applies), and only a mail from exactly
  that address (case does not matter) counts. So nobody can answer a forwarded
  request in the name of the original recipient. An answer from another
  address changes nothing: the mail log lists it with the reason "not from the
  address the request was sent to", and the person gets a mail at their stored
  address. **Forged senders:** the address in `From` can be forged and
  Rentalars cannot check it itself (no SPF/DKIM evaluation of its own). It does
  read the header `Authentication-Results` that the mail server of your
  provider writes on receipt, and does not take over an answer with
  `dmarc=fail` (reason "the check of the sender failed"; also with `p=none`). A mail with more than one `From` line is not taken over, and the warning mail to the person goes out at most once an hour per request and reason. How safe that is
  depends on whether your mailbox writes this header and whether the domain of
  the crew addresses has DMARC set up – usual for private addresses of large
  providers. Whoever does not want to rely on that sets the answer to "by the
  link in the browser". **This can be tightened:** under
  Settings → Mailboxes enter at "Name of your mail server in the check
  results" the name your mail server starts the header
  `Authentication-Results` with (the part before the first semicolon, such as
  `mx.example.com`; it is in every mail received). Then an answer counts only
  if exactly this server wrote `dmarc=pass` or `dkim=pass` for the domain of
  the sender (with `dmarc=pass`, `header.from` must be the domain of the
  sender, too). The topmost header with that name counts, as a server puts its
  own above all others; headers of the same name that a sender writes into
  the mail stand below it and never count. A value in a header that the
  sender influences (a comment, the envelope address) cannot start a result of
  its own either. **The domain is confirmed, not the person:** whoever may send
  from the same domain can answer in its name. A mail server that does not put
  its name at the start of the header (Exchange Online starts with `spf=pass`)
  cannot be entered; there the way of the link remains. The self-check points
  this out as long as nothing is entered. Whoever is not confirmed gets a mail with the link to answer in
  the browser. **Without the entry a reply mail is no proof of who wrote
  it:** only the address in the `From` line is compared, and somebody may know
  it. The address of the structured `From` line is compared, not a text in it.
- **Network:** only the connections to IMAP and SMTP of your
  mail provider, which fetching needs anyway. The codes are not in the full
  export (below).
- **New times, new request** (PER-033, PER-034). If the start
  or end of a crew line that was requested or accepted changes – in the
  browser, when moving a phase with its personnel or through the API –,
  Rentalars sends a new request by itself ("Deployment request with new
  times: …", with "New times: … (before: …)") in the same way as every
  request, with a new code; an answer with the code of the older request is
  no longer taken over ("not taken over: a newer request was sent").
  Rentalars doesn't send requests by itself for declined lines, cancelled
  projects and deactivated people. This can be switched off in the browser
  under Settings → Company data and settings → **"ask again when the
  times change"** (on by default). Whoever moves
  many times at once sends that many mails; switched off, the planning
  offers "ask again" instead.
The system mails continue to go through `[email]` until you set it
differently.

A mailbox from which mails are moved or deleted must support **IMAP with
MOVE or UIDPLUS**, so that Rentalars can move or delete a single mail
safely. All common providers support it.

If the **secret key was changed** in the configuration, Rentalars can no
longer read the stored passwords of the mailboxes. The page "Mailboxes and
signature" names every affected mailbox; enter its password again then.
The same applies to the two-factor login: it has to be set up again
afterwards (`sudo rentalars reset_two_factor NAME` for everyone who uses
it) – and to the secrets of the webhooks and the API key of
Lexware Office (below, "Webhooks" and "Accounting").

## Automations

If you want, Rentalars does something by itself when something
happens (ADM-013): answer an inquiry without a project tag with a
confirmation of receipt, notify someone, note an open item. The rules are
set up in the browser under **Settings → Automations** (module
Settings: read to look at them, edit to change and delete them) or
through `/api/v1/automations`; this is described in the
[user manual](../user-manual.md). Without a rule Rentalars does nothing
new. What counts for operation:

- **When they run:** a run is recorded in the database together with the
  event and carried out right after it, where the event happens: when
  fetching the mailboxes (service `rentalars-mail`) for inquiries and
  answers of the crew by mail, in the browser or in the API (service
  `rentalars`) for a new status and answers in the browser, with the
  follow-ups (service `rentalars-jobs`) for due follow-ups. Whatever is
  left over, for example because Rentalars was just restarting, is caught
  up on by `rentalars-jobs.timer` in the next minute. A run that breaks off
  halfway is recorded as "failed" and **never repeated** – better no
  answer than two.
- **Answers by mail** go through the mailbox in which the inquiry was,
  otherwise through the one that sends the correspondence; it needs SMTP
  and an address, otherwise the run fails ("No mailbox can send …"). The
  recipient is the `Reply-To` of the mail, otherwise the sender. The answer
  carries `Auto-Submitted: auto-replied` and
  `X-Auto-Response-Suppress: All` – so that other systems don't answer
  back –, `In-Reply-To` and `References` and the note at the end of the
  system mails (above). In the mail log it appears with the kind "automatic
  reply". Only mails in mailboxes that "take in mails without project tag"
  trigger it.
- **Protection against answer loops:** Rentalars never answers a mail that
  is marked as automatic (`Auto-Submitted` other than `no`,
  `Precedence: bulk`, `junk`, `list` or `auto_reply`, `List-Id`,
  `List-Unsubscribe`, `X-Autoreply`, `X-Autorespond`,
  `X-Auto-Response-Suppress`, an empty `Return-Path`, a delivery report),
  never senders such as mailer-daemon, postmaster, no-reply or bounce,
  never its own addresses (mailboxes, sender of the system mails, address
  of the company), and every sender at most once per rule and calendar
  day. For this check, fetching has read a few more headers.
  In this way Rentalars deliberately departs from the rule of not
  answering mails by itself (EML-030) – only for rules that you create.
- **Log:** every run is listed under Settings → Automations, "Runs",
  with the result and the reason, for one year – even after its rule has
  been deleted, with the rule's name. If a person is anonymised, their name
  disappears there too. If a mailbox is deleted, the rules that applied
  only to this mailbox switch themselves off. Program errors are in the log
  of the service that started the run (above, "Logs").
- **The rules that come with Rentalars** (three for service
  cases, "Defect report → service case"; ADM-019):
  they can
  be edited and deleted like your own and carry a fixed key
  (`default_key`). **No update and no start of Rentalars
  creates a deleted one again or overwrites a changed one.** Only "Restore
  default automations" under Settings → Automations or
  `POST /api/v1/automations/restore-defaults` brings them back – both
  create only the missing ones, as they came, switched on, with the right
  to edit the settings.

## Calendars of the people

Rentalars exchanges with the calendars of the people what they
have set up under "My personnel data" (PER-022, PER-023). What the people do
there is in the [user manual](../user-manual.md); what counts for
operation:

- **Linked calendar:** Rentalars reads the private ICS link of a Google,
  Outlook or iCloud calendar **every 30 minutes**, for the past month and
  the coming half year, and only takes over when the person is busy – no
  titles.
- **CalDAV calendar:** Rentalars writes the deployments of a person into
  their calendar at Nextcloud, iCloud, mailbox.org, Posteo and similar –
  **within one minute** of a change to a crew line and otherwise **every
  30 minutes**. Google Calendar cannot be written to this way; the
  subscription link is the one for that.
- **Subscription link** (`https://rentalars.example.de/calendar-feed/…`):
  calendar apps fetch the deployments there themselves, **without
  logging in** – the link is protected by the secret key in it. That only
  works if Rentalars can be reached from the network of the calendar app,
  so as a rule from the internet; Google Calendar, for example, fetches such
  links from its own servers. If Rentalars only runs internally or over
  VPN, use the CalDAV calendar. The calendar states its
  refresh interval (`X-PUBLISHED-TTL`) as a duration, `PT30M`.

**Calendar links of products, models and items** (VFG-040).
Following
the same pattern, every product, material model and item can get a secret
calendar link, at
`https://rentalars.example.de/calendar-feed/<kind>/<id>/<key>.ics`
(`<kind>` is `product`, `model` or `item`); by default none has one, and
it is created, replaced and deactivated on the record's page or through
`/api/v1/products|material-models|material-items/{id}/calendar-link`
([user manual](../user-manual.md), section 4, "Calendar link"). What
counts for operation:

- **Without login, at the address of the configuration file** (`url`):
  calendar programs must reach it like a person's subscription link. If
  the server's address changes, the addresses of the calendar links change
  with it; subscribers had best enter the new one.
- **The key** has 256 random bits and is compared in constant time. It is
  in the database (and so in the backup), never in the change log and not
  in the readable export of all data (below, "Full data export"). Page and
  API show the address only to whoever may change the link. Whoever knows
  it sees project numbers and names with status and period – no prices,
  customers or contact data.
- **Slowed down and cached like the subscription link:** wrong addresses
  count per client together with those of the subscription links (then
  "429", below), a link fetched far more often than by a calendar program waits
  as well; an unchanged calendar answers `304 Not Modified`. The NGINX
  limit for `/calendar-feed/` (below) applies to them too.
- **Computed when fetched**, 90 days back and two years ahead, with a fixed
  number of database queries; calendar programs are asked to fetch every
  30 minutes. It needs no timer and no outgoing connection.
- A deactivated product and a retired, sold or lost item lose their link
  for good; a deleted record takes it along. After going back to the previous version
  (`sudo rentalars rollback`) none of the links created works any more.

There is no timer of its own for the calendars of the people: the run of
`rentalars-jobs.timer`
syncs what is due every minute, after the background tasks. After 40
seconds it starts nothing new; whatever is still open then gets its turn in
the next minute. By hand, for example to check a setup or after a longer
outage:

```sh
sudo rentalars sync_calendars               # everything that is due
sudo rentalars sync_calendars --person 17   # one person, due or not; shows the result
```

For both, the server must be allowed to open **outgoing connections**: over
HTTPS to the calendar services, and with your own Nextcloud also into the
internal network – only when allowed under `[network]
allow_internal` (above, "Connections into the internal network"). The
credentials of a CalDAV calendar only go to exactly the server entered,
except with iCloud (same section). If reading or writing doesn't work, the
reason is shown with the person under "My personnel data" (without the
address, which may be secret); after six failures in a row – about three
hours – the person gets **one** notification, by default also by e-mail.
Program errors while syncing are in the log of `rentalars-jobs`.

**Limiting the subscription link.** Rentalars itself slows down anyone who
tries many wrong links or fetches a link far more often than a calendar app
would. It counts the wrong links per client address, as the
login reads it – behind NGINX from `X-Forwarded-For` –, and not at all
without a known address. The NGINX template
additionally limits the requests to
`/calendar-feed/` like those to the login (30 per minute and sender) –
thus also those to the calendar links of products, models and
items. An
existing installation only gets this with `sudo rentalars nginx-site`
(above, "The NGINX configuration"); the self-check doesn't report it as
missing.

The passwords of the CalDAV calendars are stored encrypted in the database,
like those of the mailboxes. If the secret key of the configuration was
changed, every person enters their password again; until then they see
"The stored password cannot be read any more".

## Webhooks

Rentalars tells other systems – ERP, chat, n8n – when something
happens: a project is created or changes its status, material goes out, is
handed over or comes back, times are approved, a document is created
(API-012). The webhooks are set up in the browser under **Settings →
Webhooks** or through `/api/v1/webhooks`; this is described in the
[user manual](../user-manual.md). What counts for operation:

- **Timer:** nothing new to set up. An event is recorded in the database
  together with the change; deliveries are made every minute by the
  existing `rentalars-jobs.timer` (`run_jobs`), after the background tasks
  and the calendars – at most 30 seconds or 200 deliveries per run, the
  rest in the next minute. A long task in the same run delays the webhooks
  like the calendars.
- **Retries:** only a 2xx response counts as delivered. Otherwise Rentalars
  tries again after 1 minute, 5 minutes, 30 minutes, 2 hours and 12 hours
  – six attempts in about 15 hours. Per attempt it waits at most 10 seconds
  for each step, 20 in total. It doesn't follow redirects (3xx).
- **Switching off:** if 10 deliveries in a row fail for good, Rentalars
  switches the webhook off and notifies everyone who may change the
  settings, as an "Error of the application", by default also by e-mail.
  The switching off is in the change log (`system:jobs`). Waiting
  deliveries stay and go out as soon as the webhook is switched on again.
- **Retention:** deliveries are kept for 30 days, with the beginning (1,000
  characters) of every response of the receiving system; then the daily
  maintenance deletes them. The period is fixed.
- **Network:** the service `rentalars-jobs` – and, for "Send test" and
  "Send again", which run immediately in the browser, the service
  `rentalars` too – must be allowed to reach the receiving systems over HTTP
  or HTTPS. Rentalars only reaches a receiving system in the
  internal network when allowed under `[network] allow_internal` (above,
  "Connections into the internal network"); until then every delivery
  fails, and after ten that have failed for good the webhook switches
  itself off. Rentalars takes a proxy from the environment of the service
  (`https_proxy`, `http_proxy`), except for addresses on this server.
  Certificates are checked against the certificate authorities of the
  system; an internal, self-signed certificate fails with "certificate".
- **Secrets:** the secret with which every message is signed is stored in
  the database, encrypted with the `secret_key` of the configuration. If
  the `secret_key` is changed, it can no longer be read: deliveries fail
  with the hint to create a new one ("Create a new secret", then take it
  over into the receiving system).

By hand, `sudo rentalars run_jobs` delivers what is due straight away.

## Maps

Addresses have a link "Route in Google Maps" and a zoomable map
from OpenStreetMap; the trips of a project are shown with their routes in
Schedule and Overview (UIX-033, UIX-034, PRJ-097). The user manual describes
how to use them. What counts for operation is **what leaves the house**
(NFA-050):

| What | Who asks | Where to | When |
|---|---|---|---|
| Where an address is | **the server** (service `rentalars`) | map search, by default Nominatim `https://nominatim.openstreetmap.org/search` | only when someone presses "Show map" – with "load maps at once" already when the page opens –, and only once per address |
| The map images | **the browser** of the person, with the address of the installation (scheme and host) as the referer | map server, by default `https://tile.openstreetmap.org/…` | with the map |
| A route | **the browser** of the person | `https://www.google.com/maps/dir/…` with stops and destination, without a start – Google Maps begins at the person's location | only on a click on "Route in Google Maps", in a new tab |

Before that, no address and no request goes to a foreign server; the switch
"load maps at once" (Settings → Company data and settings) is off.
Rentalars calculates distances and routes only when the optional route
service is set up on this server (below, "Route service") –
otherwise not.

- **The map search** only sends the text of the address (`q`), no project
  and no name. Its user agent names the installation, as the
  rules of Nominatim require:
  `Rentalars/1.0.0 (maps; +https://rentalars.example.de)` – only scheme and
  host from `url`, never a path or credentials (without a usable `url` just
  `Rentalars/1.0.0 (maps)`). It follows no redirects.
  It keeps to the rules of the public Nominatim: at most one request per
  second for the whole installation (all worker processes share the lock
  file `geocoder.lock` in the data folder for this), at most five new
  addresses per opened map – the rest the next time it is opened –, and no
  suggestions while typing. Every answer is remembered, including "not
  found"; network errors are shown on the map and not remembered. The
  positions apply per address to all records with the same address; ones
  corrected by hand are in the history of the record. The daily
  maintenance deletes positions of addresses that nobody names any more,
  those of an anonymised customer straight away.
- **Network:** the service `rentalars` must reach the map search over
  HTTPS; it takes a proxy from the environment of the service, as with the
  webhooks. The users' browsers need the map server. If it can't be reached,
  the map stays grey, but the list of places below it is still shown; if
  the map search can't be reached, the map says so ("The map search cannot
  be reached."), and the positions can be set by hand.
- **Security of the pages:** Leaflet, which draws the map, is on your own
  server (`static/vendor/leaflet`, BSD-2-Clause) and is only loaded with the
  first map. Only pages that can show a map allow the browser images from
  the configured map server (Content-Security-Policy); all others stay as
  they were.
- **The rules of OpenStreetMap for map images** (Tile Usage Policy)
  require every request to say which page it comes from. Everywhere else
  Rentalars sends `Referrer-Policy: same-origin`, so the browser
  would send no referer with the map images – OpenStreetMap would then answer with
  "Access blocked 403 … App is not following the tile usage policy". The map therefore requests its images (UIX-034) with
  `referrerPolicy: strict-origin-when-cross-origin`: the map server learns
  the address of the installation (scheme, host, port), no path and no
  project; the pages themselves keep `same-origin`. The rest of the rules
  is kept: attribution "© OpenStreetMap contributors" with a link to
  `/copyright`, images only after "Show map", no preloading and no bulk
  downloading, normal caching in the browser (no service worker, no headers
  against the cache). If you don't want to give out the referer or open
  many maps, enter your own map server (below). If "Access blocked" still
  shows, a reload without the cache usually helps;
  otherwise a browser add-on may be suppressing the referer.

**The `[maps]` section** in `/etc/rentalars/rentalars.conf` is optional;
without it the servers of OpenStreetMap apply:

```ini
[maps]
# tile_url = https://tile.openstreetmap.org/{z}/{x}/{y}.png
# geocoder_url = https://nominatim.openstreetmap.org/search
# attribution =
# attribution_url = https://www.openstreetmap.org/copyright
# max_zoom = 19
```

- `tile_url` – the map images with `{z}`, `{x}`, `{y}` (and, if the server
  needs it, `{s}`). **Empty switches the maps off completely:** no "Show
  map", no map search; the links "Route in Google Maps" and the trips stay.
- `geocoder_url` – a search that answers like Nominatim
  (`?q=…&format=jsonv2`), for example your own Nominatim server. Empty: no
  search; you set positions on the map by hand.
- `attribution` and `attribution_url` – whom the map images of another
  provider are owed to; empty shows "© OpenStreetMap contributors" with the
  link to the copyright of OpenStreetMap.
- `max_zoom` – how far you can zoom in (1 to 22).

Addresses must begin with `https://` or `http://`, otherwise Rentalars
doesn't start and names the error. After a change `sudo systemctl
restart rentalars`. If you open many maps or don't want to give data to
OpenStreetMap, run your own map search and your own map server and enter
them here; the rules of the public servers of OpenStreetMap only allow
moderate use.

## Route service

Rentalars plans vehicles and trailers on the trips of a
project, billed by the kilometre (LOG-001 ff., in the user manual under
"Logistics"). The planned kilometres of a trip are typed in by hand. If
you like, you can also set up a **route service** (LOG-017): the dialog of
a vehicle on a trip then offers "Suggest planned km from the route" – a
suggestion that can always be changed. The route service is optional, can
be installed at any time later and removed again; without it only the
button is missing.

The positions of the places go to no outside service (NFA-050): the route
service is the program **Routino** on this server, with the OpenStreetMap
map of Germany or one Bundesland – or an OSRM server you run yourself or
that is hosted in Germany. Where the places lie is found as for the maps
(above, "Maps") and remembered; a position set by hand counts.

### Setting it up

```sh
sudo rentalars route install --region bayern --dry-run   # show what would happen – also without root
sudo rentalars route install --region bayern             # set up, with the map of one Bundesland
sudo rentalars route install                             # all of Germany (from 4 GB of memory)
```

Regions: `germany` or a Bundesland – `baden-wuerttemberg`, `bayern`,
`berlin`, `brandenburg`, `bremen`, `hamburg`, `hessen`,
`mecklenburg-vorpommern`, `niedersachsen`, `nordrhein-westfalen`,
`rheinland-pfalz`, `saarland`, `sachsen`, `sachsen-anhalt`,
`schleswig-holstein`, `thueringen`. Trips across the border of a
Bundesland need the map of all of Germany. Rentalars need not be
restarted.

The command

1. checks the system (Ubuntu 24.04 or 26.04, Raspberry Pi OS based on
   Debian 13), the memory and the free space. With less than 4 GB of memory
   it asks for a Bundesland or an explicit `--region germany` and processes
   in Routino's slim mode;
2. installs the distribution's package `routino` (Ubuntu: universe);
3. downloads the map from Geofabrik (`download.geofabrik.de`) and checks it
   against the MD5 checksum published there – or, with `--file
   FILE.osm.pbf`, takes a file already on the server (no internet needed; a
   Geofabrik file name keeps its region);
4. processes it for motor vehicles (`planetsplitter`, progress in
   `/opt/rentalars/routes/planetsplitter.log`);
5. deletes the download (unless `--keep-file`), drives a test route between
   two towns of the region as the service user and only then writes
   `/etc/rentalars/route-local.conf`. Rentalars reads that file at every
   use.

**How big, how long** – estimated, not measured; the command says how much
space it needs before it starts:

| Map | Download | Free space meanwhile | Processing |
|---|---|---|---|
| Germany | about 4.5 GB | about 23 GB | about 1 to 3 hours, longer on a Raspberry Pi |
| Bayern | about 800 MB | about 4.5 GB | about 10 to 45 minutes |
| Berlin | about 90 MB | under 1 GB | a few minutes |

After processing only the processed map remains; it is much smaller than
the space needed meanwhile.

**A routing server of your own** (OSRM or compatible) instead of Routino:
`sudo rentalars route register --url https://routing.example.de`. The
address must start with `https://` – `http://` only on this machine. The
command checks a route from Frankfurt to Würzburg. Rentalars sends the
server the positions of the places of a trip, nothing else, and follows no
redirects.

```sh
rentalars route status                 # kind, region, age and size of the map, version, test route
sudo rentalars route update            # download and process the same region again
sudo rentalars route remove            # remove; afterwards by hand again
sudo rentalars route remove --keep-data   # keep the map and the package
```

**Updating:** roads change. `status` and the settings show how old the map
is and suggest `route update` after 180 days. The update processes the new
map into a folder of its own and switches only when it has driven its test
route – if it fails, the previous map stays in use. For a map from
`--file`, `update` downloads nothing; use `route install --file` with a
newer file. There is no timer for automatic updates.

**In the browser:** Settings → Company data and settings shows
administrators the box "Route service" – set up or not, kind, region, date
of the map and the commands. If the file is broken or the map missing, the
button in the dialog disappears and the box names the reason.

### What lives where

| What | Where |
|---|---|
| Processed map, log of the processing | `/opt/rentalars/routes/` (only root changes it, readable by all – the map is public) |
| For Rentalars: kind, region, date of the map, program, folder or address | `/etc/rentalars/route-local.conf` (root, readable by all) |

**Backup:** the map and `route-local.conf` are not in the backup
([backup.md](backup.md)); on a new server you set the route service up
again with `sudo rentalars route install`. The kilometres of the trips are
in the database and come back with it.

## Accounting: Lexware Office and DATEV

Invoices and cancellation invoices go to **Lexware Office**,
and the invoices of a period can be downloaded as a **DATEV booking batch**
for the tax adviser (DOK-011, DOK-012). Both are set up in the browser
under **Settings → Accounting**
([user manual](../user-manual.md), section 16). What counts for operation:

- **Lexware Office needs the way out:** HTTPS to `api.lexware.io`, from the
  service `rentalars` (the handover starts from a page or when an invoice
  is made) and from the service `rentalars-jobs` (the timer catches up on
  what could not start straight away). A proxy from the environment of the
  service is used.
- **Every handover is a background task** of the kind `lexware`. It is
  listed under "My account → Tasks in the background" of whoever started it
  by hand; its output is in the log of `rentalars` or `rentalars-jobs`. The
  Accounting page lists all handovers that are waiting or have failed, with
  the reason. Lexware Office accepts at most two requests per second;
  Rentalars keeps to that.
- **The API key** of Lexware Office is stored in the database, encrypted
  with the `secret_key`, and is never shown again. If the `secret_key` is
  changed, the Accounting page says that it can no longer be read; then
  enter it again. It is not in the full export or the change log.
- **DATEV** needs no connection: the files (CSV in the DATEV format,
  Windows-1252) are downloaded in the browser or through
  `/api/v1/accounting/datev/bookings` and `…/debitors`. Every download is
  in the access log.
- **Rights:** the Accounting page and the DATEV export need read access to
  the settings **and** the right to see prices; changing needs write access
  to the settings. The supplied role **"Read only"** ("Nur-Lesen" on a
  German installation) – meant, among others, for the accounting department
  – has no access to the settings: under Settings → Roles give it the level
  "read" for "Settings", or create a role of your own "Accounting".

There is also the menu entry **Accounting** with the
**outgoing documents** – every document a customer got, with their sums –
and the monthly statement of the service cases (its addresses begin with
`/accounting/monthly/`). The outgoing documents can be seen by whoever may
see prices and read every project – without access to the settings; via
the API `/api/v1/accounting/documents` and `…/totals`. The DATEV export and
the handover to Lexware Office stay under Settings → Accounting.

The formats of Lexware Office and DATEV are built according to their
published descriptions; it is best to check the first handover and the
first import into DATEV together with your tax adviser.

## Full data export

All data in open formats, in one ZIP file (IMP-006) – for reading in other
programs and for your own archive. In the browser under
**Settings → Backup**, section **"Readable export of all data"**, button
**"Make a full export"**; only those who may delete in the
settings can do this, that is the administrators. The export runs as a
background task; when it is finished, the page of the task offers the file
for download (until the period for results runs out, 7 days by default) –
only to whoever started it. Through
the API: `POST /api/v1/exports/full`, then `/api/v1/jobs/{id}` and
`/api/v1/jobs/{id}/result`. Every export is in the change log, including
the one on the server; downloading in the browser or through
the API is also in the access log.

On the server the same export is written by

```sh
sudo rentalars export_data /var/lib/rentalars/rentalars-export.zip
```

The command runs – like all commands of the application – under the
service account; so the target must be in a folder that the service account
may write to, for example `/var/lib/rentalars`, and must not exist yet. At
the end it says how many tables, rows and files it has written. Take the
file away from there afterwards.

What is in the ZIP file:

| Folder | Content |
|---|---|
| `json/` | every table as a JSON file in Django's format, e.g. `json/customers.customer.json` |
| `csv/` | the same tables as CSV (semicolon, UTF-8), one column per field; references to other tables are given as IDs |
| `dateien/` | all stored files – project files, mail attachments, documents, photos, inspection reports, certificates, photos and videos from the chat – under the name the tables give |
| `LIESMICH.txt` | what is included and what is not (a read-me) |

**Not** included are secrets that are of no use outside this installation:
the hashes of the passwords and the API tokens, the secrets of the
two-factor login, the passwords of the mailboxes, the setup token, the API key of Lexware Office, the codes of the deployment
requests by mail (whoever has one can answer the request; the table is
included with an empty code), the keys of the calendar links
of products, models and items (the table is included without them –
whoever has one sees the calendar without a login), the encrypted
password of the search account of the directory (LDAP).
Also not included: sessions, login attempts, the background tasks and their
results (so no earlier exports either), and the webhooks with
their deliveries – the address of a webhook can itself be a secret link.

**The export contains the personal data of all customers, people and
users** and is never encrypted, even if the backups are. Treat it as
confidentially as a backup and delete it when it is no longer needed. It
doesn't replace a backup: Rentalars cannot be restored from it
([backup.md](backup.md), "The readable export is not a backup").

**Export in the import format** (IMP-017). To be told apart
from this is the export of a single list in the format of its import –
material, products, customers, people – under Settings → Import and export,
in the browser and through `GET /api/v1/imports/{kind}/export`: a CSV file
in plain text that can be imported again ([import.md](import.md), "Export
in the import format"). It is written while it is sent, in chunks of 2,000
records, and takes no background task.

## The API: limits and protection

Programs that talk to Rentalars through the API (`/api/v1/`) notice none of
this as long as they behave sensibly. Three rules protect operation
(API-010, API-011):

- **At most 600 calls per token and minute.** The number is set under
  Settings → Company data and settings ("API calls per token and
  minute"); 0 switches the limit off. Whoever goes over it gets the
  response 429 `throttled` with `Retry-After` (seconds to the next minute)
  until the end of the minute. Every counted response carries
  `X-RateLimit-Limit` and `X-RateLimit-Remaining`. Only calls with a token
  are counted, not those of the browser.
- **No double execution.** A writing call with the header
  `Idempotency-Key` is carried out once; if the same call comes again with
  the same key – for example because the connection broke off –, it gets
  the stored response with `Idempotent-Replayed: true`. The responses are
  kept for one day. (from a code review) a key belongs to the
  caller – token or session – and to the call (method, address, content).
  The stored response only comes after the same checks as a new call:
  login, rights on the module, limit of calls and access to the record. A
  different caller with the same key never gets it; the same caller with
  different content gets 409 `idempotency_key_reused`.
- **No overwriting of other people's changes.** Every JSON response to a
  GET carries an `ETag`. If a program sends it as `If-Match` when changing
  something and someone else has changed the record in the meantime,
  Rentalars refuses with 412 `precondition_failed`. With `If-None-Match` a
  GET answers with 304 if nothing has changed. Rentalars
  compares and writes in one go under a lock (table `api_writelock`, on
  MariaDB also the row of the record), so that two simultaneous changes of
  the same version don't both get through; in the browser the rule is still:
  whoever saves last wins.

Counters and stored responses are kept in the database – so they apply to
all worker processes at once – and are cleaned up by the daily
maintenance. If the limit slows down a program that really needs more,
raise the number.

**Tokens create other tokens only within limits** (AUT-021).
A token can create further tokens through `POST /api/v1/tokens`, but never
open up more than it has itself:

- A token restricted to modules – such as that of the Rentalars app –
  creates no tokens (403) and under `/api/v1/tokens` sees and revokes only
  itself, not the other tokens of its user.
- A token with an expiry date only creates tokens that expire with it at
  the latest; `expires_at` is then required (otherwise 400).
- A "read-only" token changes nothing: it creates no tokens
  (403, before: 400), revokes none, ends no sessions and changes neither the
  notifications of its user nor availabilities or calendars.

In the browser (My account → API tokens) every user creates tokens as
before.

## The Rentalars app for Android

The companion app (Rentalars app 1.0, Android 8 or newer) brings packing lists
and time recording onto the phone, even without a network
([user manual](../user-manual.md), section 2). It is **not part of the
Rentalars package** and is delivered separately – as a signed APK that you
put onto the phones directly or through device management. The server part
has been in Rentalars; nothing needs to be set up on the
server. What counts for operation:

- **Reachability:** the phones talk to Rentalars through the API, at the
  same address as the browser (`url` under `[rentalars]`). The app accepts
  **only https with a certificate that Android trusts out of the box** –
  Let's Encrypt or a bought certificate; a self-signed one or one from your
  own certificate authority is not enough. It doesn't follow redirects;
  under `/api/v1` Rentalars doesn't redirect. If Rentalars can only be
  reached in your own network, the app syncs as soon as the phone is there
  (Wi-Fi or VPN); in between it works without a network.
- **Time of the server:** the app works with the time of the server, which
  every response carries in the `Date` header. NGINX sets it; another proxy
  in front must let it through. The server's clock should be right (NTP,
  the default on Ubuntu).
- **Login and token:** the app logs in once with name, password and, if
  needed, the code of the two-factor login (`/api/v1/auth/login`) and
  creates a token of its own, restricted to `packing`, `projects`,
  `time_tracking` and `email` (chat, mails, price
  overview, `/mail/unknown`), valid for 30, 90 or 180 days. It is listed
  with the user under My account → API tokens; revoke it there or by
  logging out in the app. It counts against the limit of 600 calls per
  minute like every token; a sync with up to 400 changes is one call. The
  rights are those of the user: whoever may only read packing lists – the
  supplied role Freelancer (Freie Kraft) – only sees them in the app and
  cannot tick anything off there. The role Crew packs in its
  own projects but does not add material ([user
  manual](../user-manual.md), section 10, "Packing with the Crew role").
- **Packing lists without a network** (PCK-026): `GET /api/v1/offline/packlists`
  returns the projects in the status "Confirmed – details open",
  "Confirmed" and "Out" whose packing list the caller may read – with number,
  name, status, period, place, customer (empty for whoever only has the
  deployment view – the overview and the packing list), whether they may tick
  off, the packing lists and the time of the server. This request
  creates nothing: a project gets its main packing list as soon as
  it reaches one of these statuses; a project without a packing list is listed with `packlists: []`.
- **Sync** (PCK-027): `POST /api/v1/projects/{p}/packlists/{id}/sync`
  accepts at most 1,000 changes at once – per line the packed or the
  returned quantity ticked off, with the time at which it was done on the
  phone. Every line remembers when each of the two quantities last changed,
  by whatever route; a change from the phone only counts if it is **later**
  (equally late: the server wins; a time in the future counts as now).
  Rentalars takes the changes in the order of their times, in one go and
  with locked rows, and with the same limits as in the browser; whatever
  violates them, it refuses with a reason instead of cutting it down. The
  response names `applied`, `older` or `refused` per change, and the whole
  packing list. It answers invalid input – including a time without a time zone
  or before the year 2000 – with 400. The sync **never issues anything and
  books no take-back**; that remains a step in the browser. Returns ticked
  off in the app trigger the webhook `packing.returned` as in the browser –
  only when a returned quantity ticked off goes up, once per sync.
- **Versions and clock rule** (from a code review). Every
  packing list line has a `version`, which every change of the packed or
  returned quantity ticked off raises by one – in the browser, through the
  API and in the sync. A change may bring along `base_version` (the version
  when loading) and a `change_id` (at most 64 characters, for example a
  UUID):
  - With `base_version` the version decides: if it differs, the result is
    `conflict`, the state of the server stays and is in the response
    (`server`); if the desired quantity is already there, it is `applied`.
  - Without `base_version` (older companion apps) the time rule from above
    applies, now unambiguously: the server only reads its clock after
    locking; a time in the future counts as now, but the changes keep their
    order (time, then original time, then order in the call); against the
    server only a genuinely later time counts; the remembered time never
    goes back.
  - A `change_id` is remembered per user for 30 days; if the same change
    comes again, Rentalars answers with the first result and `replayed` –
    including its `reason`. The same ID for a different change
    is refused.

  An open packing list in the browser reloads itself after a sync.
- **Adding material** needs write on the project or packing
  for all projects. The sync refuses a packed quantity above the packing
  list with `reason` `needs_project_write` (the message names who may add
  material) or `above_packing_list`; the other changes apply.
  `/offline/packlists` gives `can_add_material` per project; `add-material`
  without this right gives 403 with `needs_project_write`. `DELETE` on
  packing lists, handovers and extractions needs write, as in the browser.
- **Projects and service cases without a network.** Projects
  and service cases carry `field_changed_at` (per field the time of its
  last change, by whatever route); `PATCH`, status and follow-up take
  `changed_at` and take a field only if it is later – the same clock rule
  as the sync of the packing lists, under the same lock as `If-Match`. The
  response names `applied`; a status change no longer allowed gives 409
  with the project.
- **Own data.** `GET`/`PATCH /api/v1/people/me/profile`,
  `/people/me/absences` and `/people/me/deployments` need no right on the
  Personnel module; `GET /me` gives `server_version`. The e-mail address –
  which is also the login address – can be changed there only by a token
  without module limits or one that includes the E-mail module (the app's
  token); other tokens get 403 `token_scope`.
- **Times** are sent by the app as finished entries to `POST
  /api/v1/time-entries` with `Idempotency-Key` (above); the rules of the
  server apply.
- **Lost phone:** revoke the user's token in the browser (or, as an
  administrator, deactivate the account). Whatever had not yet been synced
  on the phone can then no longer be synced; it is stored there encrypted.

## Moving the database

With one command all data moves into a **new, empty database** (NFA-068) –
onto an existing MariaDB server, onto another one, or back onto this
server. Reasons: the company wants to manage its databases centrally; a
database server that encrypts its files; a change of the database user.

To another server – database and user prepared there as in
[installation.md](installation.md), "Existing database server":

```sh
sudo rentalars move-database --host db.example.de --name rentalars --user rentalars     --password-file /root/db-passwort.txt --tls-ca /root/db-ca.pem
```

Back onto this server (MariaDB is installed if needed, the command creates
the database and the user):

```sh
sudo rentalars move-database --local
```

What happens:

1. The new database is **checked before anything changes**: it must be
   empty; its user must not be root and may only have rights on this one
   database (as with the installation).
2. A **backup** of the current state is made (it is never deleted
   automatically).
3. Rentalars is **stopped**, and all data is copied.
4. **Every table is compared** – number of rows and a checksum over all
   values. Only if not a single value differs is the configuration switched
   to the new database and Rentalars started again.
5. If anything goes wrong along the way, Rentalars starts again with the
   old database, as if nothing had happened.

Rentalars cannot be reached for the duration of steps 3 and 4; with a
typical database that is seconds to a few minutes.

**The old database stays**, as it was at the moment of the move – as a way
back. If everything runs for a few days, you remove it by hand. If it was
on this server:

```sh
sudo mariadb -e "DROP DATABASE rentalars; DROP USER 'rentalars'@'localhost';"
```

(The command says at the end which database was the previous one; its user
is named in the previous configuration, which it keeps under
`/etc/rentalars/rentalars.conf.before-move-…`.) If it was on another
server, that server's administrator removes it. If MariaDB is no longer
needed on this server at all afterwards, it can go with
`sudo apt remove mariadb-server` – check beforehand that `sudo rentalars
status` reports the new database as reachable.

## Removing Rentalars

`sudo rentalars uninstall` removes Rentalars from this server
(NFA-078), in three ways that you have to choose explicitly. With no option
the command only shows this overview and does nothing (exit code 2).

| Option | Effect |
|---|---|
| `--dry-run` | Shows what would be removed and changes nothing. Given alone it shows the effect of `--keep-data`; with `--purge` it shows the full deletion. |
| `--keep-data` | Removes the application but **keeps the data**. |
| `--purge` | Removes **after explicit confirmation also the database, backups and configuration**. |

`--keep-data` and `--purge` together are an error. The command needs root.
Without a terminal (in a script) `--keep-data` also needs `--yes`.

**The confirmation for `--purge`:** at a terminal you type the host name from
the address in the configuration exactly (the word `PURGE` if there is none).
Without a terminal only `--yes-i-really-want-to-delete-everything` is
accepted – `--yes` does not count here. Beforehand the command asks for a
**last backup** into a folder (at a terminal `/root` is suggested, otherwise
`--backup-to FOLDER`; `--no-final-backup` skips it). A relative folder is
made absolute at once, and every message names the absolute path. A folder
that is itself about to be deleted is refused. **Without a terminal**,
`--yes-i-really-want-to-delete-everything` additionally needs one of the two
options (`--backup-to` or `--no-final-backup`); if both are missing the
command ends with exit code 2 without changing anything – what happens to the
last backup is never decided silently. If the backups are encrypted, the plan
warns that the recovery key is deleted as well.

### What is removed, what stays

| | `--keep-data` | `--purge` |
|---|---|---|
| Timers and services `rentalars*` (stopped, disabled, incl. `.service.d`) | removed | removed |
| NGINX site `rentalars`, `snippets/rentalars-proxy.conf`, `/var/www/rentalars-acme` (NGINX is reloaded only if `nginx -t` passes) | removed | removed |
| `/opt/rentalars` (releases, program, virtual environment, local AI with models, route-service maps) | removed | removed |
| Command `/usr/local/bin/rentalars`, lock files `/run/rentalars-*.lock` | removed | removed |
| Database and its user | kept | local: `DROP DATABASE` and `DROP USER` (the user only if its grants cover just this database); remote database: only tables and views – the database and account belong to its administrator |
| `/var/lib/rentalars` (files, photos, attachments) | kept | removed |
| `/var/backups/rentalars` | kept | removed |
| `/etc/rentalars` (configuration, recovery key, own certificates, AI and route settings) | kept | removed |
| Let's Encrypt certificate | kept | `certbot delete` – unless another NGINX file uses it |
| NGINX logs `rentalars.*` | kept | removed |
| MariaDB settings `60-rentalars.cnf`, `62-rentalars-memory.cnf` and the slow-query log `rentalars-slow.log*` | kept | removed if no other database lives on this MariaDB – and only then the log too, because MariaDB keeps writing to a deleted file while the settings stay; removing the settings takes effect only after MariaDB is restarted (`sudo systemctl restart mariadb`), which the script does not do itself |
| System user and group `rentalars` | kept | removed (`www-data` leaves the group `rentalars` first; only if the user has `nologin` and its home is `/var/lib/rentalars`) |

**Never removed**, in either mode: installed packages (NGINX, MariaDB,
certbot, llama.cpp-tools, routino …), the key of an encrypted MariaDB
(`/etc/mysql/rentalars-encryption`, `61-rentalars-encryption.cnf` – MariaDB
could not start without it), other databases (the plan names them, also an old
one left behind by `move-database`) and the systemd journal. The default NGINX
site is not re-enabled.

**Safeguards:** every path comes from the installer's constants
(`deploy/lib.sh`); a path to remove must contain "rentalars" and not be a
top-level folder; links are removed, not followed; `rm -rf` stays on one file
system. A data or backup folder that differs from the installer's default is
named but not removed. If a folder that is meant to stay (both with
`--keep-data`, with `--purge` one that is not the installer's default) lies
inside a path that is removed – for instance `[backup] directory =
/opt/rentalars/backups`, or a link into it – the run ends with exit code 1
**before anything changes**; the dry run shows this too. If a default folder is
a link (`/var/lib/rentalars` pointing to another drive), the command removes
only the link; the target with the data stays, and the summary says so,
naming the target, instead of reporting that the data was removed. Suspicious
values in the configuration stop the run before anything changes. If the
configuration file cannot be read (a duplicate key, a missing section
header), `--dry-run`/`--keep-data` go on with the defaults and warn (the
database is then not touched); `--purge` refuses with a readable message and
exit code 1, changing nothing. A database whose `host` is 127.0.0.1 or `::1`
with a port other than 3306 (a tunnel to another server) counts as a remote
database: only its tables are dropped. The order: **stop** services and timers
(afterwards the command checks with `systemctl is-active` that they stand
still – if a unit still runs, `--purge` aborts before anything is removed;
with `--keep-data` it is reported as a problem), then the database, and only
then **disable** the units. If the database step fails, the services are
stopped but still enabled, and the configuration, files and backups are
untouched; the message names that state and the command to start again. With
a remote database `mariadb` stops at the first failing statement, so earlier
tables may already be dropped; the message says so and names the last backup
(or the existing backups) to restore from. From the confirmation on the
command ignores SIGHUP (a closing terminal does not kill it in the middle of
`DROP DATABASE`); on Ctrl+C or SIGTERM it ends at once with "Cancelled in the
middle of the removal – start the command again" and exit code 1. Starting it
again is safe: the plan is made from what is still there.

**Installing again:** `install.sh` refuses while the configuration file
`/etc/rentalars/rentalars.conf` **or** `/opt/rentalars/app` exists (only the
file is checked, not the whole folder). After `--keep-data` `/opt/rentalars`
is gone, but the configuration is still there, so reinstalling on kept data
is a manual procedure; the output of `--keep-data` lists the steps: move
`/etc/rentalars` aside (with the file in it), run `install.sh`, optionally
`sudo rentalars restore` with a backup, copy the old `secret_key` back, then
`sudo rentalars encryption enable`. After `--keep-data` the `rentalars`
command is gone; a later full deletion runs from the unpacked package:
`sudo ./deploy/uninstall.sh --purge`. While the NGINX site is missing,
certificate renewal fails. The AI and route-service settings stay in
`/etc/rentalars`; after a reinstall run `rentalars ai install` and
`rentalars route install` again.

**Tested** with stand-ins for `systemctl`, `mariadb`, `nginx`, `certbot`,
`getent`, `userdel`, `groupdel` and `gpasswd` in a throw-away directory
(`tests/deploy/test_uninstall.sh`, several hundred cases, part of `scripts/check.sh`),
**not on a real server**. Start with `--dry-run` the first time.

## Performance

### What is promised

On the reference system (4 cores, 8 GB), with two people working at the
same time and the data volume from the requirements catalogue – 100
accounts, 20,000 items, 1,000 projects:

- usual pages and API calls in under one second (NFA-012),
- a project with 500 lines in 20 groups opens in under one second and
  stays smooth to use (NFA-014),
- adding a line including the availability check answers in under half a
  second (NFA-013).

And since stage 3: if up to ten people record their times shortly after
one another – the whole crew after a deployment –, Rentalars stays usable
(NFA-051); the measure is that every response comes in under two seconds.

### What was measured

Measured on 16 October 2026 (Ubuntu 24.04, full data volume, three runs). Everything stayed below its limit (at most 659 ms,
the hours report of the last month as CSV); the command needed at most 164 MB of memory. The measurement has not been repeated
for every later state; how to measure yourself is described below.

| Operation | Limit | Measured |
|---|---|---|
| Open the project with 500 lines | 1000 ms | 574–604 ms |
| Read the same project through the API | 1000 ms | 292–364 ms |
| Add a line in the browser | 500 ms | 207–230 ms |
| Packing list of the project with 500 lines | 1000 ms | 489–530 ms |
| Hours report of the last month, all people | 1000 ms | 513–638 ms |
| Calendar of the month | 1000 ms | 98–115 ms |
| Timeline of two days in hours | 1000 ms | 30–47 ms |

### Measuring it yourself

On a **test installation** – never in the real one, the command refuses
there anyway – and after the first-run setup in the browser (before that
every page leads to the setup, and there would be nothing to measure):

```sh
sudo rentalars measure_performance --create-test-data
```

This is a step for your own hardware (NFA-044): if the data volume is
missing, the command creates it first (100 accounts, 20,000 items with
storage locations, 8,000 of them with inspections, 1,000 projects), then
it measures and says "ok" or "TOO SLOW" for each operation; if a limit is
exceeded, it ends with an error. The same in two steps:

```sh
sudo rentalars create_load_test_data     # creates the data volume, takes about 10 seconds
sudo rentalars measure_performance       # measures and says "ok" or "TOO SLOW" for each operation
```

Ten people recording times at the same time (NFA-051) are measured by a
command of its own – over HTTPS through NGINX, that is, the way the crew's
phones access it:

```sh
sudo rentalars measure_concurrency              # ten people, five entries each
sudo rentalars measure_concurrency --users 20   # more people
sudo rentalars measure_concurrency --insecure   # with a self-signed certificate
```

For this it creates test accounts, people and an internal project of its
own and deletes them again afterwards. Traces remain in the change log
(under names beginning with `lasttest-`), and the internal project uses up a
project number. This command too therefore belongs on a test installation.

### More simultaneous users

The supplied settings are tuned to the reference system (NFA-042): five
worker processes for Rentalars, each of which answers one request at a
time, and 1 GB of cache for MariaDB. That is enough for two to ten people
working at the same time.

For permanently more: a server with 8 cores and 16 GB, and in
`/etc/systemd/system/rentalars.service` set the number after `--workers`
to the number of cores plus one (rule of thumb; about 90 MB per process),
in `/etc/mysql/mariadb.conf.d/60-rentalars.cnf` the value
`innodb_buffer_pool_size` to a quarter of the memory. Then:

```sh
sudo systemctl daemon-reload
sudo systemctl restart mariadb rentalars
```

An update of Rentalars rewrites the unit file; enter the number again
afterwards. On a Raspberry Pi with less than 4 GB, Rentalars sets smaller
values itself ([installation.md](installation.md), "Raspberry Pi").

## When something is stuck

**The page shows "502 Bad Gateway".** NGINX is running, Rentalars isn't.

```sh
sudo systemctl status rentalars
sudo journalctl -u rentalars -n 50
sudo systemctl restart rentalars
```

If the log says something about the configuration file, there is a typo in
it; the message names the line. Rentalars also doesn't start if
`url` begins with `http://` and `allow_http = yes` is missing, or if an
entry under `[network] allow_internal` is neither a network nor an address
nor a hostname (above, "HTTPS and servers in front" and "Connections into
the internal network").

**The browser reports "too many redirects".** A server in front does the
encryption, but doesn't pass on `X-Forwarded-Proto: https`; Rentalars
takes every request for unencrypted and redirects to https. Set the header
in the server in front (above, "HTTPS and servers in front").

**"The address leads into an internal network"** with a calendar, webhook
or mailbox: the target is in your own network or on this server. Intended?
Allow it under `[network] allow_internal` and restart. The self-check
names all affected settings with the resolved address under "Connections to
other servers".

**Videos in the chat are refused** ("Videos are not possible at the moment:
the server lacks ffmpeg."). The package ffmpeg is missing – for example
because the package manager was busy during the update: `sudo apt install
ffmpeg`, no restart needed. If uploading large videos fails with "413
Request Entity Too Large", the NGINX site accepts less than the template:
`sudo rentalars nginx-site`. If a video hangs on "Video is being made
smaller …" for long: videos are made smaller one after the other, so it
may be waiting for others. `sudo rentalars run_jobs` runs what is
waiting, `sudo journalctl -u rentalars-jobs -n 50` shows what the timer
did last. Without a waiting or running task it counts as failed after
three hours, otherwise after 24 hours (above, "Photos and videos in the
chat").

**A page breaks off after two minutes with "Internal Server Error".** A
single request may not run longer than that; Rentalars ends it and takes
back what it has written up to then. In ordinary operation this doesn't
happen: what takes a long time – imports, many labels, the data export –
runs in the background (above), and an import through the API within one
request is limited to 5,000 rows (see [import.md](import.md)). That leaves
very large PDF files. If it does happen, there is a line with "WORKER
TIMEOUT" in `sudo journalctl -u rentalars`; please report which page it
was.

**A background task stays at "waiting".** The process could not be
started; the timer catches up on it within a minute. Is it running
(`systemctl status rentalars-jobs.timer`)? What it last did is shown by
`sudo journalctl -u rentalars-jobs -n 30`; `sudo rentalars run_jobs` runs
waiting tasks immediately. If a task stays at "running" for a long time,
its process is still working – a large export takes time; what it outputs
is in the log (`sudo journalctl -u rentalars` or `-u rentalars-jobs`). If
the process is gone, the timer restarts the task within a minute, and the
second time it records it as failed.

**The page doesn't load at all.** Is NGINX running
(`sudo systemctl status nginx`)? Has the certificate expired
(`sudo certbot certificates`)? Are ports 80 and 443 open in the firewall?

**"Too many failed attempts".** After five wrong passwords the name is
locked for 15 minutes (both adjustable under "Settings → Company data
and settings"). The lock ends by itself.

**Someone can't log in although they are in the personnel.** Every
person has an account, but a new account has no password yet. Under
Settings → Users an administrator invites the person or sets a
**one-time password** and gives it to them in person; at the next login
they first choose one of their own. The page of the person shows the
username (for example `anna.becker`) under "Login".

**The administrator has forgotten their password** and e-mail sending is
not set up: another administrator sets a one-time password for them in the
browser – or, if there is no second one, on the server:

```sh
sudo rentalars changepassword BENUTZERNAME
```

(`BENUTZERNAME` is the username.)

**The administrator has lost their phone and recovery codes** (two-factor
login) and there is no second one who could reset it in the browser:

```sh
sudo rentalars reset_two_factor BENUTZERNAME
```

Afterwards they log in with the password and set up the login again.

**Project mails don't arrive.** Settings → E-mail → "Mailboxes and
signature": is there an error with the mailbox, is it off, or doesn't it
have the role correspondence at all? "Check connection" shows whether the
login works. Is the mail under Projects → Inquiries because the tag has a
typo? If the tag is missing completely, Rentalars leaves the mail where it
is on purpose – unless the mailbox takes in mails without a project tag;
then it is there as an inquiry. The mail log shows what happened to each
fetched mail in which mailbox; `sudo rentalars fetch_mail --now` shows what
happens when fetching.

**Answers of the crew by mail don't arrive.** Under Settings →
Company data and settings, "answer to deployment requests" names the
mailbox for the answers (it is also shown under E-mail → "Mailboxes and
signature"); if it says that none can take them, the requests only contain
the link (above, "Mailboxes"). If the mailbox for the answers was deleted,
answers to the requests sent before that no longer arrive. Is the mailbox
being fetched, without errors? If the person changed the subject, the
answer is not recognised; a freely worded answer then sits in the mailbox.
What happened to a recognised answer – taken over, or with what reason not
– is shown in the mail log under "answer to a deployment request".

**No mail can be written from a project.** It needs an active mailbox of
the correspondence with the role "sends the correspondence", with an SMTP
server and an address. If it is missing, the page says "Sending is not set
up".

**Users are logged out "too early".** After 240 minutes without activity a
session ends; adjustable under Settings → Company data and settings.

**An invitation doesn't arrive.** Whether it went out, with what result and
through which mailbox, is shown in the mail log (Settings → Mail
log). System mails go through the mailbox with the role "system mails",
otherwise through the mail server from `[email]`. If neither is set up,
Rentalars sends nothing – the mail log says "not sent – no mail
server set up" (above, "Without a mail server"); the text of the e-mail
including the link is then in the log
(`sudo journalctl -u rentalars -n 100`). Otherwise
`sudo rentalars sendtestemail du@example.de` shows the error message of the
mail server, through the same route. Without e-mail, a one-time password
does the job (above). "Forgot your password?" on the login page
also sends a new link to invited accounts that have no password yet.

**A calendar is not read or written.** What the last attempt resulted in is
shown with the person under "My personnel data";
`sudo rentalars sync_calendars --person ID` tries immediately and shows the
result. Common causes: the server is not allowed to go out, the private
link was renewed at the calendar service, the password of the CalDAV
account has been changed (iCloud needs an app-specific password). Is the
timer running (`systemctl status rentalars-jobs.timer`)?

**A webhook doesn't deliver or was switched off.** The page of the webhook
(Settings → Webhooks) shows every attempt with the error and the
beginning of the response under "Deliveries". Common causes: the server is
not allowed to go out or needs a proxy (above, "Webhooks"), the receiving
system redirects (redirects are not followed – enter the final address), it
has a self-signed certificate, or it doesn't know the secret (any more) and
rejects the signature. "Send test" shows the response immediately. Is the
timer running (`systemctl status rentalars-jobs.timer`)?

**An invoice doesn't arrive in Lexware Office.** The reason is shown with
the invoice in the "Documents" tab and on the page Settings →
Accounting. "Lexware Office refused the API key": check the key in Lexware
Office and enter it again; "cannot be reached": check the outgoing
connection to `api.lexware.io`; "cannot be read any more": the
`secret_key` was changed, enter the key again. Then "Hand over again" –
only what is missing is caught up on.

**The disk is full.** Usually it's the backups. Take a look
(`sudo du -sh /var/backups/rentalars`), delete old ones by hand or shorten
the retention in the configuration file (`[backup] keep_days`). The
backups with `-keep` in the name – one before every update – are never
deleted by themselves.

**Everything is slow.** `top` shows whether the processor or the memory is
at its limit; `/var/log/mysql/rentalars-slow.log` names queries that took
longer than one second. Please send both along with the error report.

## Security in operation

- Rentalars only answers over HTTPS; requests over HTTP are redirected.
  A production server with an `http://` address only starts
  with `allow_http = yes`, and the self-check then warns (above, "HTTPS and
  servers in front").
- The login page accepts at most 30 requests per minute per sender, the API
  at most 600 calls per minute per token (adjustable, above "The API:
  limits and protection"). The subscription link for calendars
  (`/calendar-feed/…`) works without logging in; it shows the deployments
  of a person, without customers and prices. It is protected by a long
  secret key, and it is slowed down (above, "Calendars of the people").
- Passwords are not stored, only their hash; the same goes for API tokens.
  A token never opens up more than its user, and a token restricted to
  modules – such as that of the Rentalars app on a phone – creates no
  further tokens and doesn't see the others of its user (above, "The API: limits and protection").
- Only administrators can make the full data export with all personal data,
  and only whoever made it can download it; it contains no passwords or
  other secrets. Likewise only administrators make a backup from the
  browser, and only whoever made it downloads it; unlike the export, it
  contains everything, including the configuration file with its
  credentials ([backup.md](backup.md)).
- The access log records who opened customers, people and projects,
  exported lists or downloaded the export and backups (AUT-028).
- NGINX only delivers uploaded files after Rentalars has checked that the
  person is logged in.
- **Libraries**: the versions in `requirements.txt` are fixed;
  whoever builds or passes on Rentalars runs `scripts/check.sh`, which asks
  `pip-audit` for known vulnerabilities (needs network). In the
  source repository `.github/dependabot.yml` lets GitHub propose updates. Rentalars opens
  uploaded images only as the formats the place expects; Pillow knows only
  JPEG, PNG, GIF and WebP after the start.
- **The secret key** (`secret_key`) must not be the placeholder of the
  example file: a production server does not start with it. The
  key encrypts the stored passwords; whoever changes it enters them again.
- **The web server and the files of the service:** `www-data` cannot read the
  configuration file. `www-data` does stay in the group of the
  service account, because NGINX would not reach the socket of the application
  otherwise; what is readable for the group in the data folder (uploaded files,
  backups made in the browser) the web server user can read. That is open;
  closing it needs ACLs or a group of its own. A flaw in the web server or in a
  module of NGINX is the way there, not the application. Encrypt backups.
- **Backup and restore** run as root but follow no link in the data folder of
  the service account: the restore unpacks in the folder of the
  backups, which belongs to root.
- The **map of a supplier** and the suggestions in the supplier field are seen
  only by those who may read Material or the administration or change
  projects, not "Crew" and "Freie Kraft".
- The database only accepts connections from the server itself; an
  existing database server is addressed over TLS, with a user that can only
  reach this one database (NFA-066).
- Whoever doesn't do anything for a while is logged out (AUT-008). Everyone
  sees under "My account → Sessions" where they are logged in, and can end
  any session.
- Two-factor login with an authenticator app (AUT-006): can be switched on
  per user, required per role, and for everyone with rights on the
  settings with one switch (NFA-049).
- A one-time password (AUT-027) is only good for one login: after that
  every page leads to choosing a password of your own, and until then the
  API answers with 403.
- NGINX only answers to the configured name; it ends requests to the bare
  address of the server or to an unknown name without an answer. If you
  have changed the supplied configuration, the self-check tells you whether
  one of the secure settings is missing.
- Mails from the correspondence are shown cleaned up, in a sealed-off frame
  without scripts; Rentalars only loads images from foreign servers at the
  press of a button (EML-027).
- (NFA-071, from a code review) **webhooks, calendars and
  mailboxes** only address addresses in the internal network and on this
  server if they are allowed under `[network] allow_internal`.
  Whoever may set up webhooks can have Rentalars send requests to allowed
  internal targets and sees the beginning of the responses; so only allow
  what is meant, and be sparing with write access to the settings.
  CalDAV credentials only go to exactly the server entered (NFA-072; above,
  "Connections into the internal network").
  Whoever may read the settings sees the beginning of the responses
  of a webhook. Messages never contain prices or costs, are signed with a
  secret and follow no redirect; Rentalars refuses a username and password
  in the address. For 30 days the delivery log contains names of people
  (from approved times); anonymising a person doesn't remove them there.
- The **secrets of the webhooks** and the **API key of Lexware Office** are
  stored in the database, encrypted with the `secret_key`, like the
  passwords of the mailboxes and the CalDAV calendars; they are not in the
  full export.
- **Maps**: an address only goes to the map search after a
  click on "Show map", and only its text; the browser loads the map images
  – with the address of the installation as the referer, as
  OpenStreetMap requires –, Google Maps opens routes in the browser after a
  click, starting from the person's location (above, "Maps"). If you don't
  want that, switch the maps off in `[maps]` or enter your own servers.
- **Automations** only answer mails without a project tag,
  never automatic mails, mail systems or your own addresses, and every
  sender at most once a day per rule (above, "Automations").
- The **chat** of a project can be read by everyone who can open the
  project, including the crew planned in it; the page says so. It is not in
  the change log; when a person is anonymised, their name disappears from
  their messages too.
- **Root stays with the operator** (also for the address and
  the AI): Rentalars runs without root rights and never stores access data
  for root. What needs root – a new address with its certificate, the
  local AI – the interface at most prepares; you run it via SSH
  (`sudo rentalars address apply …`, `sudo rentalars ai …`). The command
  for the address reads the preparation only from the output of a command
  running as the service account, and checks everything itself (above,
  "Changing the server address and certificate").
- **AI:** the local AI can only be reached on 127.0.0.1, runs under a user
  of its own without rights and reaches nothing but this machine.
  Interfaces to other language models are off at first; their API keys are
  stored encrypted with the `secret_key` in the database and are not in the
  export. Mails only go to the interface chosen for the use; the log of the
  AI calls records every call, never its content (above, "AI"). IBAN, cards, credentials, e-mail addresses and telephone numbers do
  not go along when sending; names and addresses in the running text do. The
  automatic summaries are off until an administrator agrees for a provider;
  the open points are named in the section "Automatic AI summaries" (above).
- **Signing in with the directory** (off until switched on):
  the typed name is escaped before it goes into the filter; an empty
  password never reaches the directory; the password of the search account
  is stored encrypted with the `secret_key` in the database; at least one
  local emergency account remains (above, "Signing in with the directory
  (LDAP)").
- **Incoming invoices** are files with prices and suppliers:
  they lie under `media/incoming/`, are in the backup and can be downloaded
  only through Rentalars with the right to purchase prices (above, "Incoming
  invoices and their files").

What you have to contribute: keep Ubuntu up to date, secure the SSH access
(keys instead of passwords), get the backups off the server, and update
Rentalars when a new version comes out – the program deliberately doesn't
tell you about that of its own accord, because for that it would have to
"phone home" (NFA-050).

If the server becomes reachable from the internet, switch on the two-factor
login for administrators beforehand and look at the self-check: it names
what is still missing then.
