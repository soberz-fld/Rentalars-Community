# Backup and restore

Rentalars backs itself up every night. What you have to add is little, but
important: **fetch the backups from the server** and **practise restoring
once**.

## What is backed up

Every night at 2:30 a file is made:

```
/var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz
```

or, if the backups are encrypted (below), the same file encrypted:

```
/var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz.enc
```

It contains everything that makes up Rentalars:

| Content | |
|---|---|
| `database.sql` (`database.sql.enc` in encrypted backups) | the whole database: material, products, customers, projects, documents, users, change log |
| `media/` | stored files: company logo, project files, hall plans, attachments of the project mails, the documents made (PDF and XRechnung), images and files attached to material, photos of defects, inspection records, proofs of qualifications, the smaller photos and videos from the chat (`media/chat/<project>/`), the incoming invoices (`media/incoming/<year>/`) and the original PDFs of taken-over old invoices, results of tasks in the background (until their period expires) – **without** the backups from the browser (`media/jobs/backups/`, below) |
| `rentalars.conf` | the configuration file |
| `VERSION` | the version of Rentalars that made the backup |

With this one file **all the data** of Rentalars can be brought back to a
freshly installed server – database, stored files and configuration. A
**fully running server** is not back with it: what belongs to installing the
server rather than to the data is not in the backup. The list follows below
("What a restore does not bring back").

**Database and files match** (NFA-015). The backup runs while
people work, so database and files cannot be read at the same instant. So
that no file the database points to is missing after a restore, Rentalars
does not delete files at once: a deleted file stays **7 days** under
`media/.deleted/<date>/` and is then removed by the nightly maintenance. It
is therefore still in a backup whose database needs it. Data protection:
deleted files (photos, invoices, proofs too) stay on the server and in the
backups of these days for up to 7 days; backups are kept 14 days anyway
(below).

**The database dump is never on the disk unencrypted** when backups are
encrypted: it is encrypted as it is written
(`database.sql.enc` in the backup, which is encrypted once more). When
restoring and when moving the database (`move-database.sh`) it is only passed
through, not stored.

### What a restore does not bring back

| What | Why | What you do |
|---|---|---|
| Certificates (`/etc/rentalars/tls`) and the NGINX site | belong to the server, not to the data | set up when installing the new server (`--tls …`, [installation.md](installation.md)); same address as before |
| Secret key (`secret_key`) | `rentalars.conf` is **not** replaced on restoring – the server keeps its own | take it over if logins, mailbox, CalDAV, Lexware and AI passwords, two-factor and webhooks are to stay valid (moving, step 4) |
| Local AI (`/opt/rentalars/ai`, `ai-local.conf`) | program and models are large and can be downloaded again | `sudo rentalars ai install`; then "Measure speed" |
| Route service (`/opt/rentalars/routes`, `route-local.conf`) | processed map, can be downloaded again | `sudo rentalars route install` |
| Uploaded, not yet saved files (`/var/lib/rentalars/purchase-invoices`, `chat-videos`, `legacy-invoices`) | wait only a short time | upload again after the restore |
| Services of the operating system (systemd timers, firewall, DNS) | belong to the server | `sudo rentalars status` shows what is missing |
| Access to the database server with an outsourced database | `[database]` of the configuration belongs to the server | do not take it over from the old configuration |

At the end of the restore `sudo rentalars restore` shows these points
itself – for the local AI and the route service only if they are missing on
this server.

**The local AI is not in the backup**: program and models
under `/opt/rentalars/ai`, `/etc/rentalars/ai-local.conf` and
`ai-local.env`. The models are large and can be downloaded again at any
time. What is set in the browser under Settings → AI, the summaries and the
log of the AI calls are in the database and are backed up. Nor is the
route service: the processed map under
`/opt/rentalars/routes` and `/etc/rentalars/route-local.conf` – set it up
again on a new server with `sudo rentalars route install`. Nor are the
certificates under `/etc/rentalars/tls` and the NGINX site backed up – as
before; the backups made before a change of the address are under
`/etc/rentalars/address-backup/`. The folder
`/var/lib/rentalars/purchase-invoices/` is not in the backup
either, and need not be: invoices uploaded for "Enter a purchase" but not
saved yet wait there for two days at most. Once saved, the invoice hangs
on the new items under `media/` and is backed up with them
([operation.md](operation.md), "Uploaded purchase invoices"). Nor is the
folder `/var/lib/rentalars/chat-videos/`: uploaded videos
wait there until they are made smaller for the chat, with the temporary
files of ffmpeg. The small version then lies under `media/chat/` and is
backed up; a video still being made smaller at the time of the backup is
missing from it ([operation.md](operation.md), "Photos and videos in the
chat"). Nor is the folder `/var/lib/rentalars/legacy-invoices/`:
PDFs uploaded for the import of old projects but not yet taken over
wait there, 14 days at most. Once taken over, the original hangs on the
historic invoice under `media/` and is backed up
([operation.md](operation.md), "Importing old projects"). The **incoming
invoices**, on the other hand, lie permanently under `media/incoming/` and are
in every backup – they grow with every invoice ([operation.md](operation.md),
"Incoming invoices and their files"). The settings of the directory (LDAP)
are in the database; the password of the search account is encrypted with the
`secret_key` of the configuration file, which is in the backup too.

The installation script already writes the first backup, right at the end –
so it is proven from the start that backing up works on this server.

The backup runs while people work; nobody is locked out. It captures the
state of the database of a single moment, and the files that go with it are
still there (above, "Database and files match"). If the database is on another server (NFA-066),
the backup fetches it from there and still stores the file here.

The nightly backup leaves out the folder `media/jobs/backups/`,
where the backups from the browser wait to be downloaded: otherwise every
backup would contain the previous one, and they would keep growing.

## Encrypted backups

If encryption is switched on (during installation or with
`sudo rentalars encryption enable`), Rentalars writes every backup encrypted
straight away – an unencrypted version is not on the disk even for a
moment. Nothing changes for you: `rentalars restore` decrypts by itself,
with the key of the server. Exception: a backup from the browser has its own
key (next section).

On **another server** – say, after a total failure – you pass the recovery
key along:

```sh
sudo rentalars restore rentalars-2026-10-11_023000.tar.gz.enc --key-file key.txt
```

And entirely without Rentalars, with openssl:

```sh
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -pass file:key.txt \
    -in rentalars-2026-10-11_023000.tar.gz.enc -out rentalars-2026-10-11_023000.tar.gz
```

`key.txt` contains the key exactly as it was written down, with
hyphens, on one line. More on this, including what happens without the key:
[encryption.md](encryption.md).

**Encrypted backups are worthless without the key.** Whoever fetches them
from the server should therefore also know where the key is.

**Retention.** Daily backups are kept for 14 days and then deleted. Backups
with `-keep` in their name are kept for ever: they are made before every
update and before every restore. Delete them by hand when you no longer need
them. You change the period in `/etc/rentalars/rentalars.conf`:

```ini
[backup]
keep_days = 30
```

**Backing up by hand** – before a larger change, an import, a move:

```sh
sudo rentalars backup            # cleaned up after 14 days
sudo rentalars backup --keep     # is kept
```

The command prints the name of the file it wrote.

## Backup from the browser

It also works without access to the server (ADM-010): under
**Settings → Backup and encryption**, **"Back up now"** writes a
backup to download, for instance before a larger change. The
same page has the readable export of all data – which is no backup (below,
"The readable export is not a backup"). Everyone who may
delete in the settings may do this, that is, the administrators; via the
API it works with `POST /api/v1/backups`.

- **The same file as at night.** It has the same structure as the files of
  `sudo rentalars backup` – `database.sql`, `rentalars.conf`, `VERSION`,
  `media/` – and is called something like
  `rentalars-2026-10-13_101500-web.tar.gz`. So it contains the personal data
  of everybody, the access data of the database and the secret key; keep an
  unencrypted one as safe as the server itself.
- **In the background.** The backup is made as a task in the background
  ([operation.md](operation.md), "Tasks in the background"); it appears under
  "Your backups from the browser" as soon as it is ready. Before Rentalars
  offers it, it reads it back completely once.
- **Only for you.** Only the person who made it can download it – not even
  other administrators. The download is recorded in the access log.
- **Not for long.** After the period for results of tasks in the background
  (7 days by default, [operation.md](operation.md), "Retention periods")
  Rentalars deletes it. It is not contained in the nightly backup (above).
  So download it and keep it yourself.

**If the backups are encrypted** (`[backup] encrypt = true`), this one is
encrypted too (`….tar.gz.enc`) – but not with the recovery key: only root
may read that, and Rentalars runs without these rights on purpose. Every
backup from the browser therefore gets **a key of its own**, in the same
form as the recovery key. It is shown with the finished backup ("Key of this
backup – click to copy"), only to the person who made it, and only as long
as the backup exists on the server. **Keep it separate from the file**:
without it the backup cannot be opened, by anybody, and the recovery key of
the server does not fit.

**Restoring it** – copy the file to the server, then:

```sh
sudo rentalars restore rentalars-2026-10-13_101500-web.tar.gz
```

an encrypted one with its key in a file (exactly as it was shown, on one
line):

```sh
sudo rentalars restore rentalars-2026-10-13_101500-web.tar.gz.enc --key-file key.txt
```

Without `--key-file` the command first tries the key of the server and then
asks for the key of the backup (three attempts). `sudo rentalars encryption
decrypt-backup FILE --key-file key.txt` and the `openssl` command
above open it with this key, too. Otherwise everything under "Restoring"
below applies – including that a backup only fits the same or a newer
version of Rentalars.

## Fetching the backups from the server

**A backup that is on the same disk as the data is not a backup.** If the
disk fails, the server is stolen or an attacker encrypts everything, it is
gone too. So copy the backups regularly to another device in another place.

The files are readable only by `root`, because they contain all the data of
the business including the database password and the secret key. **Treat
every unencrypted copy as confidentially as the server itself.** If the
backups are to go into other hands – to a storage provider, onto a disk that
leaves the office –, switch encryption on.

A simple way: another machine – the office computer, a NAS – fetches the
files at night.

```sh
# on the other machine, e.g. daily at 04:00 via cron:
rsync -a --ignore-existing backup@rentalars.example.de:/var/backups/rentalars/ /path/to/backups/rentalars/
```

For this the fetching user needs read access to the directory on the server.
The cleanest is a user of its own that may do nothing else; how you set that
up depends on your environment. Just as good are a backup program such as
restic or borg or the backup service of your hosting provider – as long as
the directory `/var/backups/rentalars` regularly ends up somewhere else.

Check now and then whether files from yesterday really are on the other
device.

## Restoring

```sh
sudo rentalars restore /var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz
```

The command shows what it is going to do and asks:

```
==> Restore
    Backup:               /var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz
    written by:           Rentalars 1.0.0
    installed is:         Rentalars 1.0.0
    Database:             rentalars is replaced completely
    Files:                /var/lib/rentalars/media is replaced completely
    Restore now? Everything entered since the backup is lost. [yes/NO]
```

Type `yes`. Then it

1. backs up the current state (as a `-keep` backup – if you picked the wrong
   file, this gets you back),
2. stops Rentalars,
3. replaces database and files with the state of the backup,
4. brings the database up to the state of the installed program,
5. starts Rentalars again.

This takes seconds to a few minutes, depending on the amount of data. For
this the backup is unpacked next to the data (in `/var/lib/rentalars`);
there must be as much free space there as the backup takes up unpacked.

**The configuration file is not replaced.** The server keeps its address and
its access data. The file is in the backup so that a new server can be set
up from it (next section).

**The local AI stays as it is**: restoring changes nothing in
`/opt/rentalars/ai` or the service `rentalars-ai`. If "Summaries with local
AI" is on in the backup but the local AI is not set up on this server,
"Summarise" says so until you run `sudo rentalars ai install`.

### Versions

- Backup **older** than the installed program: no problem. Step 4 brings it up to date.
- Backup **newer** than the installed program: does not work. First install
  the matching version of Rentalars (`sudo rentalars update …`), then the
  backup.

### If the current database is damaged

Then step 1 fails, because the current state can no longer be backed up.
Skip it:

```sh
sudo rentalars restore FILE.tar.gz --no-safety-backup
```

## Moving to a new server

This is also the way after a total failure.

1. **On the old server** (if it is still running): `sudo rentalars backup
   --keep` and copy the file off it. Otherwise take the most recent backup
   you have outside the server.
2. **On the new server** install Rentalars as in
   [installation.md](installation.md) – in the same version that wrote the
   backup, or a newer one. Skip the first setup in the browser.
3. Copy the backup to the new server and restore it:

   ```sh
   sudo rentalars restore rentalars-2026-10-11_023000-keep.tar.gz
   ```

   An encrypted backup needs the recovery key of the old server:
   `--key-file key.txt`. If the new server is to encrypt as well,
   choose that during its installation; it gets a key of its own.

4. **Take over the secret key** if current logins and invitation links
   already sent are to stay valid. It is in the backup:

   ```sh
   tar -xzOf rentalars-2026-10-11_023000-keep.tar.gz rentalars.conf | grep secret_key
   ```

   (With an encrypted backup, decrypt it first, see above.) The secret key
   is also needed so that the stored password of the project mailbox, the
   passwords of the CalDAV calendars, the two-factor logins and
   the secrets of the webhooks and the API key of Lexware Office,
 also the API keys of the AI interfaces, stay valid. Without it you enter the password of the mailbox again
   (Settings → E-mail), every person with a CalDAV calendar enters
   their password under "My personnel data", whoever uses the two-factor
   login sets it up again (`sudo rentalars reset_two_factor NAME`), every
   webhook gets a new secret ("Create a new secret", then take it over into
   the receiving system), the API key of Lexware Office is entered again
   under Settings → Accounting and that of an AI interface under Settings →
   AI.

   Enter the line in `/etc/rentalars/rentalars.conf` of the new server
   (section `[rentalars]`) and restart: `sudo systemctl restart rentalars`.
   Without this step everybody has to log in again. You can also take over
   the settings for sending e-mail (`[email]`) from there. Do **not** take
   over the section `[database]` – the new server has its own database
   password – nor `encrypt` in `[backup]`, which belongs to the installation
   of the new server.
5. Point the DNS entry to the new server.
6. **Set the local AI up again** if you had it on the old server:
   `sudo rentalars ai install`. It is not in the backup; the
   settings in the browser come back with the database
   ([operation.md](operation.md), "AI"). The command chooses
   the model by the memory, cores and processor of the new server; the
   measured speed in the database is still that of the old one – afterwards
   use "Measure the speed" under Settings → AI, so that the estimate before
   a summary is right.

## The readable export is not a backup

There is the full data export (IMP-006): all tables as JSON and
CSV and all files in one ZIP file. It is in the browser on the
same page as the backup, under **Settings → Backup → "Readable export of
all data"**, on the server still with `sudo rentalars export_data`
([operation.md](operation.md), "Full data export"). The page says how the
two differ:

| | Backup | Readable export of all data |
|---|---|---|
| what for | **restoring** Rentalars – after a failure, on a new server | **reading** – in other programs, for your own archive |
| what | the whole database (`database.sql`) with all secrets, `rentalars.conf`, `VERSION`, all stored files under `media/` | every table as JSON and CSV, all stored files under `dateien/`, `LIESMICH.txt` |
| secrets | all: check values of the passwords, keys of the two-factor login, passwords of the mailboxes, secret key, database password | none – passwords, keys, tokens and the webhooks are left out |
| IDs | as in the database | the internal IDs, also in the references of the CSV files |
| encrypted | yes, if encryption is switched on (above) | never |
| putting back | `sudo rentalars restore FILE` – as a whole, replacing the current state | not possible |
| when | every night by itself, before every update, at the push of a button | only at the push of a button |

An **export in the import format** (IMP-017) is a third thing
again: per import – material, products, customers, people – one CSV file in
plain text, without internal IDs, that can be imported again (Settings →
Import and export; [import.md](import.md), "Export in the import format").

So the readable export is **not there to restore Rentalars**:

- `rentalars restore` only takes backups; putting an export back into a
  running installation with data of its own does not work. The
  `LIESMICH.txt` in the archive does describe how to load the JSON files
  into a **freshly installed** Rentalars of the same version (in the
  unpacked folder `sudo rentalars loaddata json/*.json`, then the files
  from `dateien/` to `/var/lib/rentalars/media/`; the folder must be
  readable for the service account; tried on the export of the
  sample data). But that gives no restored installation, rather a fresh
  start with the data:
- It deliberately lacks what a restore needs: the check values of the
  passwords and of the API tokens, the secrets of the two-factor login, the
  passwords of the mailbox, the API key of Lexware Office and the
  webhooks entirely, the keys of the AI interfaces, the
  configuration file with the secret key. After loading, everybody sets a
  new password, the mailbox and the keys are entered again and the webhooks
  are created again.
- It is only made at the push of a button, not every night. Rentalars
  deletes the file the browser offers for download after the period for
  results of tasks in the background (7 days by default).

For an emergency, the backup as described above remains. Like a backup, an
export contains the personal data of all customers, people and users – but
unencrypted, even if the backups are encrypted. Pass it on only as data
protection allows, and delete it when it is no longer needed.

## Practising the restore

A backup whose restore has never been tried is a hope. Practise it once,
ideally right after the installation and then about once a year:

1. Set up a second, small server somewhere (a virtual machine is enough) and
   install Rentalars with a self-made certificate:
   `sudo ./deploy/install.sh --domain test.example.de --tls selfsigned`
2. Restore a backup of the real server there.
3. Log in and look: are yesterday's projects there? Is the material list
   right? Can a packing list be opened as a PDF?

If so, you know that your backups are good – and how long you need in an
emergency.

## If the backup does not run

`sudo rentalars status` shows the most recent backup. If it is older than a
day:

```sh
sudo systemctl status rentalars-backup.timer     # is the timer running?
sudo journalctl -u rentalars-backup -n 30        # what does the last run say?
sudo rentalars backup                            # by hand; shows the error message
```

Most common cause: the disk is full ("Only … MB are free on …").
Rentalars does not store a backup that could not be written
completely in the first place – there are never half files in the directory.

**Rentalars reports by itself.** Every night at 4:15 – after the backup at
2:30 – it checks whether a backup was made that night (the most recent one
may be at most 25 hours old), and otherwise notifies the administrators, in
the application and by e-mail (NFA-018). Likewise when the space for backups
runs short. The self-check shows the same at any time (Settings →
Self-check); when the last nightly backup was made and whether it was
encrypted is also shown under Settings → Backup and encryption.

## Testing

The **backup from the browser** – so far on the development
machine, not in the two test environments: the file passes the checks and
the unpacking of `restore.sh`; an encrypted one can be opened with the steps
of `restore.sh`, also with a key in capital letters and with spaces, and
with the `openssl` command above; a wrong key fails. Against MariaDB 10.11,
with a user who only has rights on its own database, the database could be
backed up and loaded into an empty database the way `restore.sh` does it.
Then end to end in the test environment with Ubuntu 26.04 and an encrypted
installation: backup from the browser written (encrypted with its own key),
restored with `sudo rentalars restore FILE --key-file KEYFILE` –
what had been created after the backup was gone, everything else there –, a
wrong key rejected, and the nightly backup afterwards without the folder of
the browser backups. Not tried yet: the backup under the protection settings
of systemd (the test environment has no systemd), the download via NGINX,
the restore of an unencrypted browser backup and a typed-in key.

In the two test environments from
[installation.md](installation.md):

- **Encrypted backups:** the first backup is made during installation,
  encrypted with `--encrypt`. Such a backup restored on the same
  installation (Ubuntu 26.04, database encrypted) and – with `--key-file`
  and the key of the other server – on an installation with an existing
  database server (Ubuntu 24.04): both times the state of the backup was
  back. On a third machine a backup could be decrypted with the recovery key
  and the `openssl` command above alone.
- `rentalars encryption enable` encrypts the existing backups in the folder
  and checks each before the unencrypted one is deleted; afterwards the
  self-check shows "Encrypted: yes".

Tried in the two test environments –
Ubuntu 24.04 with MariaDB 10.11 and Ubuntu 26.04 with
MariaDB 11.8:

- Backup during operation; content of the file checked (database, files,
  configuration, version).
- Data changed, backup restored: the state of the backup was back, including
  the uploaded logo; the backup of the intermediate state was next to it.
  With the full volume of data (20,000 items, 1,000 projects) the backup
  was 0.5 MB in size, and the restore took 5 to 8 seconds. With
  an additional 100 people, 3,020 crew lines and 20,000 time
  entries (Ubuntu 26.04): backup in 1 second, 0.9 MB; restore in 5 seconds,
  all people and times back in the state of the backup.
- Restore as part of `rentalars rollback` and in the automatic way back of a
  failed update (see
  [updating.md](updating.md)).
- **Move from Ubuntu 24.04 to Ubuntu 26.04:** a backup written under Ubuntu
  24.04 with MariaDB 10.11, restored into a fresh installation under Ubuntu
  26.04 with MariaDB 11.8 (steps 2 and 3 of "Moving to a new server"). All
  data was there – 20,115 items, 1,004 projects –, the check of the tables by
  MariaDB found nothing, the pages opened.

Not tried: step 4 of the move, taking over the secret key, and the change of
the DNS entry.
