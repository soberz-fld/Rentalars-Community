# Encryption of database and backups

Rentalars can store its data encrypted (NFA-067): the files of the database
on the disk and every backup. Anyone who removes the disk, copies an image
of the virtual machine or gets hold of a backup can read nothing with it.

This page explains what is encrypted, where the key is kept, how you use it
in an emergency – even entirely without Rentalars – and how you switch
encryption on later.

## In short

- A single secret opens everything: the **recovery key**.
  It looks like this: `3f9a-07c2-91be-5d40-e8a1-6c2f-0b7d-44e9-a915-c03e`.
- The installation shows it **once**. Write it down or print it out and keep
  it **separate from the server** – in the safe, in the password manager of
  the management.
- On the server it is kept in `/etc/rentalars/recovery-key`, readable only by
  root. `sudo rentalars encryption show-key` shows it again at any time.
- As long as the server is running, nobody notices the encryption:
  Rentalars, the backup and the restore work as always.
- Without the key, encrypted backups are **lost**. That is the point – and
  the reason to write it down.
- One exception: a **backup from the browser** has its own key,
  because Rentalars may not read the recovery key ([backup.md](backup.md),
  "Backup from the browser").

## What is encrypted – and what is not

| | encrypted |
|---|---|
| Tables of the database on the disk | yes – MariaDB encrypts every page before it is written |
| Log files and temporary files of MariaDB | yes (redo log, temporary tables, sort files, binary log) |
| Backups in `/var/backups/rentalars/` | yes – extension `.tar.gz.enc` |
| Backups from the browser (until they are deleted, in `/var/lib/rentalars/media/jobs/backups/`) | yes – with a key of its own for each file ([backup.md](backup.md)) |
| Uploaded files in `/var/lib/rentalars/` | no, but contained in every backup, encrypted |
| The connection between browser and server | always, via HTTPS – regardless of this setting |
| Whatever is in the memory of a running server | no – no encryption of the disk can do that |

So the encryption protects **data at rest**: a stolen disk, a copied image,
a backup on a lost USB stick. It does not protect against someone who logs
in as root on the running server – they simply read the key as well.

The passwords of the project mailbox and the keys of the two-factor login
are stored encrypted in the database in any case (EML-002, AUT-006), even
without this setting; so are the passwords of the people's CalDAV
calendars (PER-023) and the keys of the backups from the browser.

### With an existing database server

If the database is on another server (installation with `--db-host`, see
[installation.md](installation.md)), Rentalars encrypts **the backups**.
Whether the files of the database are encrypted is decided by whoever runs
that server. `sudo rentalars encryption status` and the self-check
(Settings → Self-check) show what they find there.

## How it works

```
Recovery key  /etc/rentalars/recovery-key   (root only)
   │
   ├── encrypts every backup       (openssl, AES-256)
   │
   └── unlocks the key of MariaDB
          /etc/mysql/rentalars-encryption/filekey   = the recovery key
          /etc/mysql/rentalars-encryption/keys.enc  = the actual database key,
                                                       encrypted with the recovery key
          /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf
                                                     = tells MariaDB to encrypt
```

MariaDB encrypts with its built-in key management (`file_key_management`) –
a part of every MariaDB, nothing extra. At start-up MariaDB reads the
database key from `keys.enc` and decrypts it with `filekey`.

> **Never delete** the folder `/etc/mysql/rentalars-encryption` or the file
> `61-rentalars-encryption.cnf` while the database contains data. MariaDB
> could then no longer read its own files.

## Encryption during installation

The installation script asks:

```
Encrypt database and backups? Then the script shows a recovery key at the end,
which has to be written down.
Encrypt? [y/N]
```

Without questions: `--encrypt`. At the end the key is shown in a box, and the
script waits until you confirm that it has been written down.

## Encrypting later

An existing installation can be encrypted at any time (NFA-068) – on the
server, as root; there is deliberately no button for it in the browser
(below, "Viewing the state"):

```sh
sudo rentalars encryption enable
```

What happens:

1. A **backup** of the current state is made. It is never deleted
   automatically (`…-keep.tar.gz`).
2. Rentalars is **stopped**. For every table a **fingerprint** is taken: the
   number of rows and a checksum over all values.
3. MariaDB gets its key and restarts. Then it encrypts all tables in the
   background – page by page, with the same crash-safe bookkeeping it uses
   to write any other change. For a small database this takes seconds.
4. As soon as every table is encrypted, the fingerprint is taken once more
   and compared. **Only if not a single value differs** does Rentalars start
   again. Otherwise it stays stopped, and the script tells you what to do –
   the backup from step 1 is ready.
5. The existing backups are encrypted, and so are all future ones.

Rentalars cannot be reached for the duration of steps 2 to 4. At the end the
script shows the recovery key – write it down.

If doing this in place feels too risky, move to a new database instead that
is encrypted from the start – on another database server that encrypts, or
on this one: see [operation.md](operation.md), "Moving the database". There,
too, the switch happens only when the comparison of all tables is right, and
the old database stays in place as a way back.

## Viewing the state

```sh
sudo rentalars encryption status
```

```
==> Encryption
    Database                     encrypted (61 of 61 tables)
    new backups                  encrypted
    backups in the folder        3 encrypted, 0 not encrypted
    recovery key                 /etc/rentalars/recovery-key (root only)
```

**In the browser**,, **Settings → Backup and encryption**
(ADM-009) shows the same to everyone who may see the settings: whether the
database is encrypted, whether new backups are encrypted, whether the last
nightly one was, and whether there is a recovery key – but not the key
itself. If the database is on another server, the page says that that server
decides on the encryption of its files.

**There is deliberately no button there to switch it on.** Switching on
changes the settings of MariaDB, restarts the database and stores a key that
only root may read. Rentalars itself runs without these rights on purpose –
so even someone who took over an administrator account could neither change
the database server nor read the key. Instead, the page explains the command
`sudo rentalars encryption enable` (above, "Encrypting later"); if
encryption is already switched on, it names
`sudo rentalars encryption show-key`.

## In an emergency

### The server is running, I want to get at the data

Nothing to do: the running server decrypts everything itself. You get an
unencrypted copy of the database – say, for a move to another program – with

```sh
sudo mariadb-dump --single-transaction rentalars > rentalars.sql
```

### The server is gone, I have a backup and the key

Put the key into a file – exactly as written down, with the hyphens, on one
line:

```sh
printf '%s\n' '3f9a-07c2-91be-5d40-e8a1-6c2f-0b7d-44e9-a915-c03e' > key.txt
chmod 600 key.txt
```

**With Rentalars:** install Rentalars on a new server and restore the
backup:

```sh
sudo rentalars restore rentalars-2026-10-10_023000.tar.gz.enc --key-file key.txt
```

**Without Rentalars, with openssl only** – on any Linux, macOS or Windows
with openssl 1.1.1 or newer:

```sh
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
    -pass file:key.txt \
    -in rentalars-2026-10-10_023000.tar.gz.enc -out rentalars-2026-10-10_023000.tar.gz
tar -xzf rentalars-2026-10-10_023000.tar.gz
```

Inside are:

| File | Content |
|---|---|
| `database.sql` (`database.sql.enc` in encrypted backups, encrypted with the same key) | the whole database as SQL – readable with any text editor, loadable into any MariaDB: `mariadb rentalars < database.sql` |
| `media/` | the uploaded files (logo, project files, mail attachments, hall plans) |
| `rentalars.conf` | the configuration including access data |
| `VERSION` | which version of Rentalars wrote the backup |

If the file is called `database.sql.enc` (the database dump of an
encrypted backup is never in it in plain text), decrypt it with the same key:
`openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -pass file:key.txt -in database.sql.enc -out database.sql`.

The same decryption as a command on a server with Rentalars:
`sudo rentalars encryption decrypt-backup FILE --key-file key.txt`
(`FILE` being the backup file).

### Only the server's disk is left

The files of MariaDB (`/var/lib/mysql`) can be read with another MariaDB if
it gets the same key management:

1. On the new machine, install MariaDB of the same major version and stop
   it.
2. Copy the folder `/var/lib/mysql` from the old disk to the same place
   (owner `mysql`).
3. Copy the folder `/etc/mysql/rentalars-encryption` and the file
   `/etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf` from the old
   disk. Without `keys.enc` from this folder the files of the database
   cannot be read; then only a backup helps (previous section).
4. The file `filekey` contains the recovery key. If it is missing, write the
   key into it – without a line ending:
   `printf '%s' 'KEY' > /etc/mysql/rentalars-encryption/filekey`
   (with your key in place of `KEY`).
5. Start MariaDB and take an unencrypted copy with `mariadb-dump`.

To check that a key fits, this command decrypts the database key (it shows
a line `1;` and 64 characters):

```sh
sudo openssl enc -d -aes-256-cbc -md sha1 \
    -pass file:/etc/mysql/rentalars-encryption/filekey \
    -in /etc/mysql/rentalars-encryption/keys.enc
```

(`-md sha1` is not a mistake: that is the older format MariaDB requires for
this file. The actual key is a random number of 256 bits.)

### The key is lost, the server is still running

Then nothing is lost yet: the running server knows it.
`sudo rentalars encryption show-key` shows it – write it down, properly this
time. Only when the server **and** the key are gone can the encrypted
backups no longer be opened.

## Questions

**Does Rentalars get slower?** Hardly noticeably. MariaDB encrypts and
decrypts only what it reads from or writes to the disk; most data is in
memory anyway. The backup takes a few seconds longer.

**Can I switch encryption off again?** Not with a command. The way is a move
to an unencrypted database (`rentalars move-database`, see
[operation.md](operation.md)) and `[backup] encrypt = false` in the
configuration.

**Can I change the key?** Not in this version. If you think the key has
fallen into the wrong hands, move to a new database on a newly set-up
server.

**And the backups on another machine?** They are encrypted, no matter where
you copy them. That is a good reason to switch encryption on when backups
end up in other hands – with a storage provider, on a disk in the office.
