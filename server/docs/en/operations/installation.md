# Installation

This guide takes you from a freshly installed Ubuntu Server to a running
Rentalars with HTTPS. You don't need any programming skills for it, but you
do need access to the server with `sudo`. A Raspberry Pi 4 or 5
works instead of a server too; what is different there is in the section
["Raspberry Pi"](#raspberry-pi).

The short version for those in a hurry:

```sh
tar -xzf rentalars-1.0.0.tar.gz
cd rentalars-1.0.0
sudo ./deploy/install.sh
```

The script asks for the name of the server, for the certificate, where the
database should live and whether to encrypt. Then it sets everything up and
gives you an address at the end. You open it in the browser, enter the
company and the administrator – done.

## 1. What you need

### Server

| | Minimum | Recommended (reference system) |
|---|---|---|
| Operating system | Ubuntu Server 24.04 LTS or 26.04 LTS, freshly installed; on a Raspberry Pi also Raspberry Pi OS (section ["Raspberry Pi"](#raspberry-pi)) | |
| Processor | 2 cores | 4 cores |
| Memory | 4 GB | 8 GB |
| Disk space | 20 GB free, SSD | 40 GB SSD |

On the reference system – 4 cores, 8 GB – everything runs smoothly together
for a small company with up to two people working at the same time; the
promised response times (NFA-038, NFA-039) apply to this size. In
operation, Rentalars together with the database and NGINX takes about
0.5 GB of memory, so far less than half (NFA-040); the rest is left for
backups, PDF generation and imports. The measured times are in
[operation.md](operation.md), section "Performance".

If more than about ten people work at the same time on a regular basis,
plan for 8 cores and 16 GB and raise the number of worker processes (see
[operation.md](operation.md), "More simultaneous users").

### Which Ubuntu version? (NFA-063)

Both work: **Ubuntu Server 24.04 LTS** and **26.04 LTS**. The script,
updating, backup and restore have been tried on both. For a new server,
take the newer one; it gets security fixes for longer.

| | Ubuntu 24.04 LTS | Ubuntu 26.04 LTS |
|---|---|---|
| Python | 3.12 | 3.14 |
| NGINX | 1.24 | 1.28 |
| MariaDB | 10.11 | 11.8 |

You don't need to worry about the differences: Rentalars runs with both
Python versions, and the script writes the NGINX configuration the way the
version it finds understands it.

- On an **older Ubuntu** (22.04 and earlier) the script stops before it
  changes anything – its Python is too old.
- On a **different, newer version** (an interim release such as 25.10 or a
  future one) the script runs, but says before the start that this version
  has not been tried.
- **Upgrading Ubuntu from 24.04 to 26.04 later** works with an existing
  installation too; one command is needed afterwards. See
  [updating.md](updating.md), "Keeping Ubuntu and Python up to date".
- **On a Raspberry Pi 4 or 5** (64-bit, at least 4 GB),
  Ubuntu Server 24.04 LTS or 26.04 LTS in the edition for the Pi works,
  and so does Raspberry Pi OS based on Debian 13. Everything about it is in
  the section ["Raspberry Pi"](#raspberry-pi).
- On **any other system** – Debian on an ordinary server, Fedora, a 32-bit
  system – the script stops before it changes anything.

Rentalars is meant for **one company per installation**. Several companies
don't share an installation; each runs its own with its own database
(NFA-045).

### Disk space: how much, and what makes it grow (NFA-043)

Use an SSD. The database reads and writes many small pieces; on a
conventional hard disk every page gets noticeably slower.

| What | Size |
|---|---|
| Operating system, NGINX, MariaDB, Python | about 5 GB |
| Rentalars itself | about 170 MB per version; there are always two side by side (the running one and the previous one) |
| Database | small: about 30 MB with 20,000 items and 1,000 projects |
| Uploaded files | company logo, project files (also show files), hall plans, receipts of expenses and the attachments of project mails |
| Backups | each backup about as large as the database plus the files, compressed; 14 of them are kept |

Over time, most of the space goes to the **attachments** – stage plans,
riders, contracts and the attachments of project mails – and with them the
**backups**, because every backup contains all files. 14 backups of 5 GB of
attachments are 70 GB. With 40 GB you are generously equipped to start
with; keep an eye on the free space with `sudo rentalars status` or in the
self-check (Settings → Self-check), which warns from 2 GB of free
space. How long project mails are kept is set under Settings →
E-mail; the default is "unlimited". Backups made in the browser stay in the
data folder until the retention period for background tasks runs out
(seven days by default).

### Name and certificate

Rentalars can only be reached over HTTPS. For that the server needs

- a **name** under which the users call it up, for example
  `rentalars.example.de`, and a DNS record that points to the server;
- a **certificate** for that name. The script can get it in three ways –
  which one fits depends on how the server can be reached (section 3).

Even if the server can only be reached over VPN during the test phase:
Rentalars is secured from the start so that it can go on the internet
without any rework (NFA-048). The script always writes
`url = https://NAME`; a production server with an `http://`
address only starts if the configuration explicitly says
`allow_http = yes` (NFA-073). If there is another server in front of
Rentalars that does the encryption (reverse proxy, load balancer), `url`
stays at `https://…`, and that server has to pass on the header
`X-Forwarded-Proto: https` ([operation.md](operation.md), "HTTPS and
servers in front").

Name and certificate can be changed later without installing
again: an administrator prepares the change under Settings → Server
address and certificate, and you apply it with
`sudo rentalars address apply …` ([operation.md](operation.md), "Changing
the server address and certificate").

### Browser

To work with Rentalars, a current browser is all you need: Chrome,
Firefox, Safari or Edge in their current version (NFA-023), on the
computer as well as on the phone. Nobody has to install a program.

### E-mail (can come later)

Rentalars needs e-mail in two places, both through mailboxes with a
provider of your choice – it doesn't run a mail server of its own:

- **System mails** – invitations, "Forgot your password?", notifications –
  go through a mailbox that you enter in the configuration file after the
  installation (section 6). Without one, everything else works; the
  invitation links are then in the log of the service.
- The **project mailbox** – Rentalars fetches the mails with the project
  tag in the subject from it, and you write from the project through it –
  is set up in the browser (Settings → E-mail). See the
  [user manual](../user-manual.md), "Correspondence".

Both may be the same mailbox.

### Calendars of the people (can come later)

People can get their deployments into their own calendar and
link a calendar with their busy times (PER-022, PER-023). For the
installation this means:

- For a **subscription link** – the calendar app fetches the deployments
  itself – the app must reach Rentalars at `https://NAME/calendar-feed/…`,
  so as a rule from the internet; Google Calendar, for example, fetches
  such links from its own servers. If the server can only be reached
  internally or over VPN, use a **CalDAV calendar** instead (Nextcloud,
  iCloud, mailbox.org, Posteo …), into which Rentalars writes the
  deployments.
- For a CalDAV calendar and for a linked calendar, the server must be
  allowed to open **outgoing** connections over HTTPS – to the calendar
  services, and with your own Nextcloud also into the internal network.
  Rentalars only reaches a target in the internal network
  (Nextcloud, NAS) if it is allowed in the configuration file under
  `[network] allow_internal` ([operation.md](operation.md), "Connections
  into the internal network").

Nothing needs to be set up on the server for this; more in
[operation.md](operation.md), "Calendars of the people".

### Webhooks and accounting (can come later)

Rentalars can tell other systems what happens through
**webhooks**, and hand invoices over to **Lexware Office**. Both need
**outgoing connections**: to the receiving systems over HTTP or HTTPS –
into the internal network only when allowed under `[network]
allow_internal` –, and to `api.lexware.io` over HTTPS. If the server needs
a proxy for this, Rentalars takes it from the environment of the service.
The **DATEV export** needs no connection. Nothing needs to be set up on the
server; more in [operation.md](operation.md), "Webhooks" and
"Accounting".

### Maps (can come later)

Rentalars shows addresses on a map from OpenStreetMap and links
routes to Google Maps. A map only appears after a click on "Show map";
then **the server** asks the map search `nominatim.openstreetmap.org` over
HTTPS where the address is, and **the browsers** load the map images from
`tile.openstreetmap.org`. As the rules of OpenStreetMap require, the
browser sends the address of the installation as the referer, and the map
search names it in the user agent. Rentalars takes a proxy
from the environment of the service. Nothing needs to be set up; if you
don't want maps or run your own map servers, enter that in the `[maps]`
section of the configuration file ([operation.md](operation.md), "Maps").

### Local AI (can come later)

Rentalars can summarise the correspondence of a project with an
AI on this server – the mails do not leave the server. For this you set up
a small language model as a service after the installation, with
`sudo rentalars ai install`; without it everything else works the same.
It needs at least 1.5 GB of memory (the larger model, which
takes up to 5 GB, only from 6 GB, four physical cores and a processor
with AVX2 and FMA, otherwise the smaller Qwen3 1.7B), 1.5 to 4 GB of space
under `/opt/rentalars` and, for the download, access to `huggingface.co`,
on Ubuntu 24.04 and Raspberry Pi OS also to `github.com`. In a virtual
machine (under Proxmox, say) set the processor type to "host" first,
otherwise AVX2 and FMA are missing and the AI is many times slower.
Further with `sudo rentalars ai status`, `register` and `remove`; after
updates `ai refresh` takes over the settings by itself; everything in
[operation.md](operation.md), "AI".

### Where the database lives

By default the script sets up MariaDB **on the same server**. That is the
right choice for almost every company: nothing more to do, nothing more to
back up.

If the company already has a **MariaDB server**, for example because IT
runs and backs up its databases in one place, Rentalars can use it
(NFA-066). What has to be prepared for that is in section 3, "Existing
database server".

### Encryption

If you want, Rentalars stores the database and backups encrypted
(NFA-067). There is then a **recovery key** that you must write down and
keep apart from the server. Everything about it:
[encryption.md](encryption.md). It can also be switched on later.

## 2. Getting the package onto the server

Copy `rentalars-1.0.0.tar.gz` to the server, for example with `scp`:

```sh
scp rentalars-1.0.0.tar.gz du@rentalars.example.de:
```

On the server:

```sh
tar -xzf rentalars-1.0.0.tar.gz
cd rentalars-1.0.0
```

## 3. Installing

```sh
sudo ./deploy/install.sh
```

The script speaks English – or German if the locale of the server is
German (`LANG` or `LC_ALL` beginning with `de`); with `C.UTF-8`, as many
freshly installed servers have it, it speaks English. `RENTALARS_LANG=en`
or `RENTALARS_LANG=de` decides instead, for example
`sudo RENTALARS_LANG=en ./deploy/install.sh`. The same holds
for all other server scripts and the command `rentalars`. It asks:

1. **Host name** – the name from section 1, without `https://`.
2. **Where does the certificate for HTTPS come from?**

   | Choice | When | What you need |
   |---|---|---|
   | 1 – Let's Encrypt | The server can be reached from the internet on port 80. | an e-mail address for notices from Let's Encrypt |
   | 2 – Let's Encrypt with a DNS record | The server can only be reached internally or over VPN. | access to the DNS records of your domain |
   | 3 – Your own certificate | You already have one, e.g. from your own certificate authority. | certificate with its chain and private key as PEM files on the server |
   | 4 – Self-signed | Only for trying things out. | nothing; browsers show a warning |

3. **Where is the database?** 1 – on this server (default), 2 – on
   an existing MariaDB server. With 2 it asks for host, port, database,
   user, password and TLS; see below.
4. **Encrypt?** The default is no (`[y/N]`). With yes, the script shows the
   recovery key at the end ([encryption.md](encryption.md)).
5. **Start the installation?** (`[Y/n]`) Before that the script shows what
   it is going to do. Up to this question nothing has been changed.

Then it works through nine steps and says what it is doing at each one. The
longest is the fourth: that's where the Python libraries are fetched.

In the sixth step – before Rentalars or NGINX answer a single request – the
script creates the one-time key for the first-run setup (NFA-064). Without
this key the first-run setup cannot be reached, not even for a moment
during the installation.

At the end you see – with encryption, after the box with the recovery key:

```
==> Rentalars 1.0.0 is installed.

    Now open this address in the browser and set up company and administrator:

        https://rentalars.example.de/setup/?token=…
```

### The certificates in detail

**Let's Encrypt (choice 1).** Let's Encrypt calls the server on port 80 to
check that the name belongs to you. So ports 80 and 443 must be reachable
from the internet. After that the certificate renews itself.

**Let's Encrypt with a DNS record (choice 2).** The server doesn't have to
be reachable. Instead you create a TXT record with your DNS provider, which
the script tells you, and confirm with Enter. **Watch out:** this way the
certificate does not renew itself; it is valid for 90 days (renewing:
[operation.md](operation.md), "Certificate"). If your DNS provider has an
API, it also works without manual work and with automatic renewal:

```sh
sudo ./deploy/install.sh --domain rentalars.example.de --email du@example.de \
    --tls dns --dns-plugin cloudflare --dns-credentials /root/cloudflare.ini
```

Which providers there are and what the file with the credentials looks like
is in the certbot documentation ("DNS plugins").

**Your own certificate (choice 3).** The script copies both files to
`/etc/rentalars/tls/`. When the certificate expires, you replace the files
there and reload NGINX (`sudo systemctl reload nginx`).

### Existing database server

Rentalars creates nothing on a database server that isn't its own: you
prepare the database and the user there. On the database server, as its
administrator:

```sql
CREATE DATABASE rentalars CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'rentalars'@'192.0.2.10' IDENTIFIED BY 'ein-langes-zufälliges-passwort';
GRANT ALL PRIVILEGES ON rentalars.* TO 'rentalars'@'192.0.2.10';
```

`192.0.2.10` is the address of the Rentalars server; `'%'` would work too,
but is more open than necessary. The database must be empty.

Then on the Rentalars server:

```sh
sudo ./deploy/install.sh --domain rentalars.example.de --email du@example.de     --db-host db.example.de --db-name rentalars --db-user rentalars     --db-password-file /root/db-passwort.txt --db-tls-ca /root/db-ca.pem
```

or without options, answering the questions. The password is on the first
line of the file; as an option it would show up in the process list of the
server.

**What the script checks before it changes anything:**

- The connection works, and the database is empty.
- **Never root.** The user `root` is refused before a connection is even
  opened.
- **All rights on exactly this database, and no others.** Refused is a user
  with rights on the whole server (`GRANT … ON *.*`), on further databases,
  with rights through a role that grants that, or with the right to log in
  as another user (`PROXY`). The script names each reason separately, so
  that the database administrator knows what to change.
- The character set is `utf8mb4`; otherwise the script switches it for the
  empty database.

Rentalars needs full rights on its database, because every new version
adjusts its tables itself. It doesn't need more – and otherwise an account
with more rights would sit in the configuration file of every Rentalars
server.

**Encrypted connection.** If the database is on another machine, Rentalars
connects over TLS (default). With `--db-tls-ca` it also checks the
certificate of the database server and its name – then nobody can get in
between. Without it, the connection is only encrypted. `--db-no-tls`
switches TLS off; that is only acceptable in a closed network, and the
self-check reminds you of it.

**Backup and encryption.** The daily backup fetches the data from the
other server too and stores it on the Rentalars server as usual. Here,
`--encrypt` encrypts the backups; whether the database files are encrypted
is up to the database server.

**Switching later.** With `sudo rentalars move-database` the data moves
into another database – onto another server or back onto this one. See
[operation.md](operation.md), "Moving the database".

### Without questions

All details can be passed as options, for example for an automated setup.
`sudo ./deploy/install.sh --help` shows them all.

```sh
sudo ./deploy/install.sh --domain rentalars.example.de --email du@example.de --yes
```

## 4. First-run setup in the browser

Open the address the script gave you. It works exactly once and contains
the setup key, so that nobody else is quicker and makes themselves
administrator. Anyone who calls up the page without the key or with a
wrong one only gets the notice that the one-time address is needed; after
the first-run setup the address leads to the start page. Lost it?
`sudo rentalars prepare_setup` gives you a new address; the old one is no
longer valid then.

> **If you install without the script,** run `rentalars prepare_setup`
> **before** you start the web server. As long as no key has been created,
> the first-run setup stays closed – so nobody can get in first, but you
> too only get in with the address the command gives you.

You enter:

- **"Your company"** – name and address; they appear on the packing list. With
  **"Language"** you choose the language of the documents to customers and
  of the start data (roles, units, categories …): "English" or "Deutsch".
  The language of your browser is preselected. Each user chooses the
  language of the interface; the first administrator gets the one chosen
  here.
- **"First administrator"** – username, name, e-mail address, password.
  Like every account, it then also appears under personnel (every login
  is a person).
- **"Number ranges"** – which number projects, customers and material IDs
  start with, and the **"Prefix of project numbers"**, by default
  `{year}-`: `{year}` is replaced by the current year, so the first project
  is called `2026-0001`. If you take over the Excel list, the import
  automatically sets the next material ID after the highest existing one.
- **"Standard tax rate in percent"** – 19 % by default.
- **"Create sample data"** – a few products, material, customers and
  projects to try things out. For real operation, leave the box unticked.

With the first-run setup, apart from the master data – categories including
C "Customer material" for material belonging to customers and N "Incidental
costs", units, rental scale, the storage location "Main warehouse", eight
job functions with their service products, still without a price, and the
document types including "Show file" for the show files of
consoles – Rentalars also creates the project template **"Dry Hire (rental
without crew)"**, for rentals where the customer collects the material
themselves – also the three automations for service cases.
These are the names of an installation in English; in German
they are "Fremdmaterial", "Nebenkosten", "Hauptlager", "Showfile" and "Dry
Hire (Vermietung ohne Personal)". If you don't need the template, you delete
it under Projects → Templates; it won't come back. The surcharges for
nights, Sundays and public holidays (Settings → Surcharges) are set to the
rates of § 3b EStG, but are switched off until you switch them on; "make
invoices in Rentalars" is on.

After that you are logged in. How to go on is in the
[user manual](../user-manual.md), chapter "First steps".

## 5. What is on the server now

| What | Where |
|---|---|
| Program and Python libraries | `/opt/rentalars/` |
| Configuration | `/etc/rentalars/rentalars.conf` – the only file with settings and credentials |
| Database | MariaDB, database `rentalars` – or the database on the existing server |
| Recovery key (only with encryption) | `/etc/rentalars/recovery-key`, readable only by root |
| Uploaded files | `/var/lib/rentalars/` |
| Backups | `/var/backups/rentalars/`, every night at 2:30 |
| Command for everything else | `rentalars` (e.g. `sudo rentalars status`) |
| These guides | `/opt/rentalars/app/docs/en/` – the German originals in `/opt/rentalars/app/docs/` |
| Route service (only after `sudo rentalars route install`; after `route register` only `route-local.conf`) | `/opt/rentalars/routes/`, `/etc/rentalars/route-local.conf`, package `routino` |
| Local AI (only after `sudo rentalars ai install`) | `/opt/rentalars/ai/`, `/etc/rentalars/ai-local.conf` and `ai-local.env`, service `rentalars-ai` (`rentalars-ai-refresh.timer` and `.service` are always set up, but only run with a local AI) |
| Backups before a change of the address (only after `sudo rentalars address apply`) | `/etc/rentalars/address-backup/` |

Exactly three services run: NGINX, MariaDB and Rentalars itself
(`rentalars.service`); with an existing database server only two. On top
of that there are five timers: one for the daily backup, one for small
clean-up jobs and the nightly checks (due inspections, minimum stock), one
that fetches the project mailbox, and one that catches up on
background tasks that could not start straight away, and which also syncs the calendars of the people, also delivers
the webhooks, sends notifications about due follow-ups, catches up on waiting automations and reports shortages
at the time set. The fifth, `rentalars-ai-refresh.timer`,
starts `rentalars-ai-refresh.service` about a minute after every start of
the server, which takes over the settings of the local AI; without a
local AI (`/etc/rentalars/ai-local.env`) it does not run at all. Rentalars needs no further
services – for queues or caches, say: a background task is a process of
its own of the Rentalars service, which ends with it. Only if you set up
the local AI is there a fourth service, `rentalars-ai`
([operation.md](operation.md), "AI").

Rentalars runs under its own service account without login (`rentalars`)
and may only write to its data directory. A database on this server can
only be reached from the server itself. Rentalars doesn't send any data to
third parties of its own accord: fonts and scripts come from your own
server, there are no statistics and no check for new versions (NFA-050).
Only when a person sets it up under "My personnel data" does Rentalars
read their linked calendar or write their deployments into their CalDAV
calendar; only when you set it up under Settings does it report
events to webhooks or hand invoices over to Lexware Office. An address
only goes to the map search of OpenStreetMap when someone opens its map
(above, "Maps"), and to Google Maps only when someone clicks on "Route in
Google Maps". For calendars, webhooks and mailboxes Rentalars
connects into your own network and to this server itself only where that
is allowed under `[network] allow_internal`
([operation.md](operation.md), "Connections into the internal network").

**Firewall.** From outside, only ports 443 (HTTPS) and 80 (redirect to
HTTPS, certificate renewal) need to be reachable, plus your SSH access.
Subscription links for calendar apps also go over port 443. With Ubuntu's
firewall:

```sh
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable
```

## 6. Setting up system mails

Open the configuration file:

```sh
sudo nano /etc/rentalars/rentalars.conf
```

In the `[email]` section the lines are already there, with `#` in front.
Remove the `#` and enter the details of your mailbox:

```ini
[email]
host = smtp.example.de
port = 587
user = rentalars@example.de
password = …
from_address = rentalars@example.de
```

Then restart the service and try it:

```sh
sudo systemctl restart rentalars
sudo rentalars sendtestemail du@example.de
```

Or in the browser: Settings → Self-check → "Send a test mail to me".
The mail log (Settings → Mail log) also shows whether a
mail went out. Every mail that Rentalars sends of its own
accord ends with "This message was sent automatically by Rentalars for …:",
the company name from the first-run setup and the address from `url` under
`[rentalars]` – check in the test mail that the address is right
([operation.md](operation.md), "Mailboxes").

After that you set up the **project mailbox** in the browser
(Settings → E-mail): IMAP and SMTP of the mailbox your customers
write to; by default Rentalars sends with the user and password used for
fetching. That is also where you create the signature for everyone.
Rentalars fetches it at the set interval – every two minutes by default –
and only touches mails with a project tag.

## 7. Don't forget

- **Get the backups off the server.** A backup on the same disk doesn't
  survive that disk failing. How to do it: [backup.md](backup.md).
- **Practise a restore once**, before you need it.
- **Write down the recovery key** and keep it apart from the server, if you
  encrypted.
- **Two-factor login for the settings,** at the latest before the
  server can be reached from the internet: Settings → Company data
  and settings → "two-factor login required for administrators"
  (NFA-049). The self-check points it out as long as it isn't switched on.
- **Keep Ubuntu up to date.** `sudo apt update && sudo apt upgrade` – or
  switch on Ubuntu's automatic security updates
  (`sudo dpkg-reconfigure unattended-upgrades`).

## 8. If something goes wrong

The script stops at the first error and says what caused it. Common
messages:

| Message | Cause and remedy |
|---|---|
| "This script is made for Ubuntu Server" / "… is too old" | A different or older system. You need Ubuntu Server 24.04 LTS or 26.04 LTS – on a Raspberry Pi also Raspberry Pi OS based on Debian 13. |
| "Rentalars needs a 64-bit system" | The Raspberry Pi runs a 32-bit system, even though the Pi itself can do 64 bits. Flash "Raspberry Pi OS Lite (64-bit)" or Ubuntu Server for the Pi again (section "Raspberry Pi"). |
| "… Debian only as Raspberry Pi OS on a Raspberry Pi" | Debian is only intended on a Raspberry Pi. On an ordinary server: Ubuntu Server. |
| "Warning: … on the SD card" (before the start) | Not an error, but a risk: the database or the backups would be on the SD card. Better to boot from an SSD (section "Raspberry Pi"). |
| "System: … – not tried" (in the overview before the start) | Not an error: Rentalars has not been tried on this Ubuntu version yet. The installation runs anyway; please report whether everything worked. |
| "Only … MB are free on /" | Too little space; at least 3 GB must be free. |
| "Let's Encrypt could not issue a certificate" | The name doesn't point to the server (yet), or port 80 can't be reached from outside. Check the DNS record and the firewall – or take the route via the DNS record (choice 2). |
| "Rentalars is installed here already" | The script doesn't change an existing installation. New version: [updating.md](updating.md). |
| "The user root is not stored" | On purpose (NFA-066). Create a user of its own on the database server, as described under "Existing database server". |
| "Rentalars cannot use this database", above it lines with "Refused:" | Each line names a reason, for example "… has rights on the whole database server: …" or "… also has rights on other databases: …". The user may only have rights on the one database: take away the others (`REVOKE`) or create a new user. Then simply start the script again. |
| "No connection to the database" | Host, port, password or firewall. Try it by hand: `mariadb -h HOST -P PORT -u USER -p DATABASE`. With TLS also: does the server offer TLS? |
| "The database … is not empty" | Rentalars only installs into an empty database. You restore an existing backup after the installation ([backup.md](backup.md)). |
| "MariaDB does not encrypt" | MariaDB's key management could not be loaded. `sudo journalctl -u mariadb` shows why. |
| "The application does not answer" | `sudo journalctl -u rentalars -n 50` shows the messages of the service. |

If the script stopped in the first two steps, simply start it again once
you have fixed the cause. From step 3 on, the program is already set up,
and the script refuses to touch an existing installation. Then remove the
half-finished installation as in section 9 and start again – there is no
data yet, after all.

## 9. Removing Rentalars again

If you only tried Rentalars out. **This deletes all data**; get a backup
(`sudo rentalars backup`) off the server first if you want to keep it.

```sh
sudo systemctl disable --now rentalars rentalars-backup.timer rentalars-maintenance.timer rentalars-mail.timer rentalars-jobs.timer rentalars-ai-refresh.timer
sudo rm -f /etc/systemd/system/rentalars*.service /etc/systemd/system/rentalars*.timer
sudo systemctl daemon-reload
sudo rm -f /etc/nginx/sites-enabled/rentalars /etc/nginx/sites-available/rentalars \
           /etc/nginx/snippets/rentalars-proxy.conf
sudo systemctl reload nginx
sudo mariadb -e "DROP DATABASE rentalars; DROP USER 'rentalars'@'localhost';"
sudo rm -f /etc/mysql/mariadb.conf.d/60-rentalars.cnf /etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf
# Only with encryption, and only AFTER deleting the database – otherwise MariaDB
# can no longer read its files:
sudo rm -rf /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf /etc/mysql/rentalars-encryption
sudo systemctl restart mariadb
sudo rm -rf /opt/rentalars /etc/rentalars /var/lib/rentalars /var/backups/rentalars \
            /usr/local/bin/rentalars /var/www/rentalars-acme
sudo gpasswd -d www-data rentalars
sudo userdel rentalars
```

NGINX, MariaDB and Python stay installed; they belong to the operating
system. With an existing database server, the line with `DROP DATABASE` is
left out; its administrator removes the database and the user there.

## Raspberry Pi

Rentalars also runs on a **Raspberry Pi 4 or 5** (NFA-070) –
for a small company that doesn't want to set up a server of its own.
Installing, updating, backing up and everything else work as on a server,
with the same commands; what is different is described here.

### What you need

| | Minimum | Recommended |
|---|---|---|
| Device | Raspberry Pi 4 (also Pi 400, Compute Module 4) | Raspberry Pi 5 (also Pi 500, Compute Module 5) |
| Memory | 4 GB | 8 GB |
| Storage | an SD card works, but is not recommended | an **SSD** with 64 GB or more: over USB 3 (blue socket), on the Pi 5 also NVMe through an M.2 add-on board |
| System, always 64-bit | Ubuntu Server 24.04 LTS or 26.04 LTS for the Raspberry Pi, or Raspberry Pi OS Lite (64-bit) based on Debian 13 "trixie" | |
| Power | the official power supply of the model; an SSD on USB draws from it too | plus a small UPS against power cuts |
| Cooling | heat sink | on the Pi 5 the active cooler ("Active Cooler") |
| Network | network cable; Wi-Fi only for trying things out | |

**Why an SSD?** The database writes many small pieces every time something
is saved. SD cards are made for photos: they wear out doing this and
eventually fail without warning – and with them the database, the files and
the backups, if they are on the same card. An SSD can take it and is much
faster as well. The installation script warns before the start if the
database or the backups would be on the SD card; afterwards
`sudo rentalars status` and the self-check (Settings → Self-check,
"SD card") show it, and every update reminds you of it.

**Less than 4 GB?** The script warns, but carries on, and Rentalars adapts
to it: with 2 GB, 3 instead of 5 worker processes run, and MariaDB gets
512 MB instead of 1 GB of cache; with 1 GB it is 2 processes and 256 MB.
That is enough for one person working at a time; PDF generation, imports
and backups take longer, and several people at once wait for each other.
From 4 GB the same applies as on the reference system (NFA-042). Every
update sets the values again according to the memory; they are in
`/etc/systemd/system/rentalars.service` (`--workers`) and in
`/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf`.

**Not intended** are older models (Raspberry Pi 3, Zero 2 W): the script
runs there with the notice "not tried", but 1 GB of memory or less is too
little for Rentalars. The script refuses a **32-bit** system – including
the 32-bit Raspberry Pi OS on a Pi 4 –, and likewise Raspberry Pi OS based
on Debian 12 ("bookworm", also "Legacy"): its Python is too old.

### Which system?

Both work; the script recognises by itself which one it is dealing with.

| | Ubuntu Server for the Raspberry Pi | Raspberry Pi OS Lite (64-bit) |
|---|---|---|
| Version | 24.04 LTS or 26.04 LTS | based on Debian 13 "trixie" |
| Python | 3.12 or 3.14 | 3.13 |
| NGINX | 1.24 or 1.28 | 1.26 |
| MariaDB | 10.11 or 11.8 | 11.8 |
| Security fixes | five years per LTS version (until 2029 or 2031) | as long as Debian 13 gets them (until about 2028, with Debian LTS until 2030) |
| Fits if … | you already run servers with Ubuntu – everything is as there | you know Raspberry Pi OS; the Pi's tools (`raspi-config`, firmware updates) are included |

The packages have the same names on both systems, and Rentalars runs with
all three Python versions. The Python libraries come from PyPI as on the
server; they are available ready-made for the Pi (64-bit ARM, "arm64") –
except for the connector to MariaDB (`mysqlclient`), which the script
builds on the Pi itself with `libmariadb-dev`, as on the server. Step 4 of
the installation therefore takes a little longer.

### Preparing

1. Install the **Raspberry Pi Imager** on your computer
   (raspberrypi.com/software).
2. In the Imager, choose the model, then the system: **"Raspberry Pi OS
   Lite (64-bit)"** or **"Ubuntu Server 24.04 LTS (64-bit)"** or 26.04
   (under other systems, Ubuntu). No system with a desktop – the Pi works
   as a server.
3. As the target, choose the **SSD**, connected to your computer with a USB
   adapter – not the SD card.
4. In the settings of the Imager: name of the device (hostname), user and
   password, **switch on SSH**, time zone Europe/Berlin.
5. Connect the SSD to the Pi and switch it on **without an SD card**. A
   Raspberry Pi 5 and a Pi 4 with firmware from 2020 or later then boot
   from the SSD. If an older Pi 4 doesn't boot: boot Raspberry Pi OS from
   an SD card once, run `sudo rpi-eeprom-update -a`, reboot, and in
   `sudo raspi-config` under "Advanced Options" → "Boot Order" choose
   booting from USB.
6. Log in over SSH and bring the system up to date:

   ```sh
   sudo apt update && sudo apt full-upgrade
   sudo reboot
   ```

7. In the router, give the Pi a **fixed address**. Name and certificate as
   for the server (section 1, "Name and certificate"): for Let's Encrypt
   the router forwards ports 80 and 443 to the Pi, otherwise take the route
   via the DNS record.
8. **Check the clock.** The Pi 4 has no battery-backed clock and gets the
   time from the network at boot; the Pi 5 only keeps it with an extra
   battery. `timedatectl` must show "System clock synchronized: yes" –
   otherwise the certificate, two-factor codes and schedules won't be
   right.

### Installing

Exactly as in sections 2 and 3: copy the package onto the Pi, unpack it,
`sudo ./deploy/install.sh`. Before the start the script also names the
device:

```
    System:       Debian GNU/Linux 13 (trixie)
    Device:       Raspberry Pi 5 Model B Rev 1.0, 7.9 GB of memory, arm64
```

If the Pi has less than 4 GB, or if the database or the backups would be
on the SD card, a warning with "Warning:" appears directly below – before
the question "Start the installation? [Y/n]". Up to then nothing has been
changed.

### What is different afterwards

- **Firewall.** Ubuntu comes with `ufw`; on Raspberry Pi OS first
  `sudo apt install ufw`, then go on as in section 5.
- **Security updates.** On Raspberry Pi OS first
  `sudo apt install unattended-upgrades`, then as in section 7.
- **Getting the backups off the device** ([backup.md](backup.md), "Fetching
  the backups from the server") – on a Pi even more important than on a
  server.
- **`sudo rentalars status`** also shows the device and what is on the SD
  card, the self-check shows the device under "Server" and a notice under
  "Storage" if something is on the SD card.
- **Speed.** The promised response times (NFA-039) apply to the reference
  system with 4 cores, 8 GB and an SSD. A Pi is slower – by how much has
  not been measured. Try it before real operation: on a test installation
  `sudo rentalars measure_performance --create-test-data`
  ([operation.md](operation.md), "Performance"), then set the Pi up afresh.
- **Moving from the SD card to an SSD later:** write a backup, set up the
  SSD as above, install Rentalars on it and restore the backup – as when
  moving to a new server ([backup.md](backup.md), "Moving to a new
  server").
- **Updating** works with the same command as on the server
  ([updating.md](updating.md)).

### What of this has been tried

To be honest: there is no Raspberry Pi in the environment in which
Rentalars is built. **Tried:**

- All Python libraries are available ready-made on PyPI for arm64, for
  Python 3.12, 3.13 and 3.14 – except `mysqlclient`, which is built on
  every Linux; the script installs the packages for that.
- How the script recognises the system and the device, which packages it
  chooses, how it sizes worker processes and memory and recognises the SD
  card – as an automated test with simulated systems: Ubuntu 24.04 and
  26.04 on Pi 4 and 5, Raspberry Pi OS on Debian 12, 13 and 14, 32-bit, a
  Pi 3, other boards, encrypted drives.
- On a server with an x86-64 processor, the script does exactly the same as
  before – down to the list of packages.

**Not tried:** the installation on a real Raspberry Pi, neither with Ubuntu
nor with Raspberry Pi OS; the packages of Debian 13 – their names and
versions were looked up, not installed; the response times on the Pi.
Please report how it went for you.

## Testing

What was tried before the release – and what wasn't.

**The two test environments**

| | Ubuntu 24.04 LTS | Ubuntu 26.04 LTS |
|---|---|---|
| Python | 3.12 (see below) | 3.14.4 |
| NGINX | 1.24.0 | 1.28.3 |
| MariaDB | 10.11.14 | 11.8.6 |
| OpenSSL | 3.0 | 3.5.5 |
| `sudo` | the traditional one | sudo-rs 0.2.13 |
| Basic commands (`install`, `ln`, `date`, `mktemp` …) | GNU coreutils | rust-coreutils 0.8.0 |
| systemd (reads the unit files) | 255 | 259 |

The Ubuntu 26.04 was a complete system made from Ubuntu's packages, run in
a closed environment on the same machine as the 24.04. In both, **systemd
was not running as the service manager**; see below. On the 24.04 machine
an additional Python 3.13 was the default; for the final test the script
was run there with the Python 3.12 that comes with Ubuntu 24.04.

**Fresh installation, update and backup from the browser:**

- **Fresh installation** (Ubuntu 24.04, twice): 75 and 81 seconds; then
  first-run setup, the full data volume and the measurement from
  [operation.md](operation.md) without findings.
- **Update**, the way back and updating again on both Ubuntu
  versions ([updating.md](updating.md), "Testing"), with pages in the
  browser over HTTPS, subscription link through NGINX, an ICS link and a
  CalDAV server (Radicale) in the test environment.
- **Encrypted installation** (Ubuntu 26.04): a backup written from the
  browser – encrypted with its own key – and restored with
  `sudo rentalars restore FILE --key-file KEYFILE`: what had been created
  after the backup was gone afterwards, everything else was there. A wrong key is refused.
  The nightly backup afterwards did not contain the backup from the browser.

**Fresh installation, update and HTTPS on the server:**

- **Fresh installation** (Ubuntu 24.04, four times): 66 to 71 seconds; the
  four schedules run, among them the new one for background tasks.
- **Update** on both systems, the way back and updating again
  (see [updating.md](updating.md)).
- **On the server, over HTTPS and NGINX** (Ubuntu 26.04): invoice with
  XRechnung and crew schedule created – the PDF files are made with the
  fonts and libraries from Ubuntu's packages; data export and import in the
  background, each as a process of its own of the service; the API with
  `ETag`, `X-RateLimit-…` and `Idempotency-Key` (the same request twice
  resulted in one execution and `Idempotent-Replayed: true`), an import
  through the API in the background (response 202).
- **In the browser over HTTPS** (Ubuntu 24.04, with the full data volume):
  packing list, documents and price overview of a project; an import of
  customers with a trial run and import in the background up to the
  report. No error message in the browser, no response with an error
  status.
- Response times with the full data volume, including the pages of stage 5
  (Ubuntu 24.04, see [operation.md](operation.md)).
- The automated tests: all 1,461 with SQLite and against MariaDB 10.11,
  with Python 3.13; among them the check of all main pages with axe-core
  (WCAG 2.1 AA) in the browser.

**Encryption:**

- **Fresh installation with `--encrypt`** (Ubuntu 24.04 with the finished
  package, 26.04 with a state shortly before): 74 seconds. MariaDB encrypts
  all 61 tables; the first backup is made right during the installation,
  encrypted (`.tar.gz.enc`); `rentalars status`,
  `rentalars encryption status` and the self-check show it as described in
  [encryption.md](encryption.md) and [operation.md](operation.md). A
  backup could be decrypted on another machine with the recovery key and
  `openssl` alone.
- **Existing database server:** `root` is refused before anything happens;
  a user with rights on the whole server likewise – only Ubuntu's packages
  had already been installed at that point. Accepted: a user with rights
  only on its database, once with TLS and a checked certificate (24.04,
  backups encrypted), once without TLS and without encryption (26.04).
  Also refused against MariaDB 10.11: a user who gets rights on the whole
  server through a role, one with rights on a second database, one that may
  only read and insert (when creating tables on trial), and a database that
  already holds a Rentalars.
- **`rentalars move-database`** from the existing server to MariaDB on this
  server and back to another existing one, with TLS; 46 tables compared
  each time, the previous database stayed unchanged.
- **`rentalars encryption enable`** on an installation without encryption
  – once fresh, once after the update (26.04): 61 tables and 867
  rows compared before and after encrypting, three existing backups
  encrypted, Rentalars kept running afterwards.
- **Update** on both systems, the way back, taking over the
  NGINX template (see [updating.md](updating.md)). Afterwards NGINX no
  longer answered to unknown names: the bare IP address on port 80 got no
  answer, an unknown name on port 443 no TLS handshake.
- The schedule for fetching mail runs after installation and update and
  is gone again after the way back.
- Response times with the full data volume, including the pages of stage 4,
  and ten people recording times at the same time (Ubuntu 24.04, see
  [operation.md](operation.md)).
- The automated tests: all 1,286 with SQLite and against MariaDB 10.11,
  with Python 3.13; among them the browser tests for the pages of stage 4
  and for a mail with a script and a tracking pixel (the script did not
  run, the pixel was not loaded).

**Tried – on both, with the same package:**

- Installation from the package with `sudo ./deploy/install.sh`,
  self-signed certificate, without questions: 31 seconds under 24.04, 33
  under 26.04 (Ubuntu's packages were already there). The script ran
  through without errors and without warnings; `nginx -t` found nothing.
- **The setup key (NFA-064):** the page of the first-run setup without the
  key and with a wrong one only showed the notice about the one-time
  address; with the key from the output of the script, the form; after
  the setup the same address led to the start page. That the key is created
  before the application (step 7) and NGINX (step 9) start is also checked
  by an automated test of the script.
- Rights and owners of all created files and directories: the same on
  both systems.
- First-run setup in the browser, with and without sample data; uploading
  the logo, delivery only to logged-in users.
- **All pages of stage 3 in a real browser, over HTTPS and NGINX**, on the
  desktop and at 360 pixels wide: Personnel, Job functions, Availability,
  My times, Approve, Report, deployment and access of a project. Time
  recorded through the dialog, with the stopwatch and with start and end;
  an overlapping time was refused with a notice. CSV and timesheet (PDF)
  downloaded. No error message in the browser, no failed request.
- The stylesheet is delivered with a version tag in the address
  (`app.css?v=…`), so that a browser loads the new one after an update
  (NFA-065).
- Update, the way back, aborting a faulty update (see
  [updating.md](updating.md)); backup and restore (see
  [backup.md](backup.md)).
- Response times with the full data volume including personnel and times,
  and ten people recording times at the same time (see
  [operation.md](operation.md)).
- The automated tests: on 24.04 all 1076 against MariaDB 10.11 and with
  SQLite (there without the four that need MariaDB), plus, without the 31
  browser tests, with Python 3.12 and 3.14; on 26.04 the 1045 without a
  browser, with Python 3.14 against MariaDB 11.8. Among the tests that need
  MariaDB are those that let two time entries arriving at the same time
  compete against each other.
- The unit files and timers have been unchanged; systemd's
  checking program read them back then (`systemd-analyze verify`, versions
  255 and 259): no complaints.

**Only tried on 26.04:**

- Installation on a minimal system on which NGINX, MariaDB and
  the build tools were still missing (92 seconds including downloading the
  packages), and the state after a switch from Ubuntu 24.04 to 26.04,
  simulated (see [updating.md](updating.md)).

**Not tried**, because the test environment didn't allow it:

- **A real mailbox.** Fetching and sending mails are tested against a
  simulated IMAP mailbox and intercepted SMTP sending, not against a real
  mail server. Please try out the project mailbox with a test mailbox
  first (E-mail → Mailbox, then "Fetch now"; an error then shows on the
  same page and in the self-check).
- **The pages of stage 4 in the browser over HTTPS and NGINX** on the two
  test systems; they were checked in the browser on the development
  server.

- **The installation on a truly fresh server with a stopwatch**, from the
  SSH login to the logged-in administrator. The promise "under 30 minutes
  following the guide" (acceptance scenario 10) is plausible given the
  times above, but not measured.
- **The certificates from Let's Encrypt** (choices 1 and 2). That needs a
  server with a public name. The commands follow the certbot
  documentation; the `certbot` package exists in both Ubuntu versions (2.9
  and 4.0).
- **Starting through systemd.** The services were started by hand with the
  same command lines that are in the supplied unit files. systemd read the
  files and found nothing to complain about (see above), but has not yet
  started a service from them – so the protective settings of the unit
  file have not been tried in operation.
- **The real switch of the Ubuntu version** with `do-release-upgrade`. Only
  what it means for Rentalars has been simulated.

Please report what went differently at your first installation from what is
described here.
