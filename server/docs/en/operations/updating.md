# Updating

You install a new version of Rentalars with one command. It backs up
everything beforehand, and if the new version does not run, it restores the
old state by itself.

```sh
sudo rentalars update rentalars-1.0.0.tar.gz
```

Users notice an interruption of usually well under a minute. Still, pick a
quiet time: whatever someone is saving at that very moment may be lost.

## Before

1. **Read what changes.** The package contains `CHANGELOG.md`. It lists for
   each version what is new – and, under "Beim Aktualisieren beachten"
   (notes on updating), whether you have to do something.
2. **Get the package onto the server**, for example
   `scp rentalars-1.0.0.tar.gz du@rentalars.example.de:`
3. **Let your colleagues know.**

Skipping a version is fine: the database is brought up to date step by step,
from any version.

## What the command does

In this order, and it says at every step what is happening:

1. **Check the requirements.** Does the server's Python version fit the new
   version? Is there enough free space (1 GB for the program, 500 MB for the
   backup)? Is the database running – or, if it is on another server, does
   it answer? If something is missing, it stops here – **nothing has been
   changed then**.
2. **Back up.** Database and files go into a backup with `-keep` in its
   name. It is never deleted by itself. If encryption is switched on, this
   backup is encrypted too (`.tar.gz.enc`).
3. **Put the new version next to the running one.** Program and Python
   libraries go into a directory of their own. Rentalars keeps running in
   the meantime. If this step fails (for example because the server cannot
   download libraries just now), nothing has happened.
4. **Switch over.** Stop Rentalars, point to the new version, bring the
   database up to its state, adapt the configuration of NGINX to the
   installed NGINX version, rewrite the command `rentalars`,
   start, switch on the schedules that come
   with the new version, check
   whether Rentalars answers. On a Raspberry Pi this step has also, aligned the worker processes and the memory of MariaDB with the
   available memory.
5. **Back, if step 4 fails.** The command then switches back to the old
   version by itself and restores the backup from step 2. It ends with an
   error message; Rentalars runs again as before, no data is lost.
6. **Local AI**: after a successful update, `rentalars ai
   refresh` takes over the settings of the local AI that the new version
   sets – without downloading anything and without changing the model;
   without a local AI nothing happens ([operation.md](operation.md),
   "After an update: `ai refresh`"). An error here does not stop the
   update.

At the end it says:

```
==> Done. Rentalars 1.0.0 is running.
    Backup from before:    /var/backups/rentalars/rentalars-2026-11-02_191503-keep.tar.gz
    Back to the old version, if need be:  sudo rentalars rollback
```

Afterwards, log in and click through once: open a project, a packing list, the
material list.

## The way back

The new version runs, but something is not right – a function is missing,
something calculates differently from what you need. Then you go back:

```sh
sudo rentalars rollback
```

The command shows where it is going back to and asks. Then it

1. backs up the current state (so that this step can be undone too),
2. switches to the program of the previous version,
3. restores the backup that was written before the update.

**Everything entered since the update is gone afterwards.** So: the sooner,
the better. After a day of work with the new version it is usually wiser to
report the error and wait for the correction.

The way back leads exactly one step back – to the version before the last
update. For this, Rentalars always keeps two versions: the running one and
the previous one.

### Why not simply start the old program?

A new version often changes the structure of the database. The old program
cannot cope with the changed database. That is why program and data belong
together, and the way back restores both.

## If the update stops

| Message | Meaning |
|---|---|
| "Python … or newer is needed" | The new version requires a newer Python than your Ubuntu brings. First raise Ubuntu to the next LTS version, then update Rentalars. Nothing has been changed. |
| "Only … MB are free on …" | Make room (old backups), then try again. Nothing has been changed. |
| "MariaDB is not running" | `sudo systemctl start mariadb`, then try again. |
| "The database on … does not answer" | The database is on another server, and that cannot be reached. You sort that out with whoever runs it; `sudo rentalars status` shows what Rentalars sees. Nothing has been changed. |
| `sudo: rentalars: command not found` | The command is missing on the server. Update once with the script from the new package, `sudo bash /path/to/rentalars-X.Y.Z/deploy/update.sh /path/to/rentalars-X.Y.Z.tar.gz`; afterwards it is there. |
| "…/deploy/backup.sh: Permission denied" | The scripts of the installed version have lost their execute permission; the update then stops while backing up. Nothing has been changed. Update directly to the new version as in the row above. |
| "The update failed and was taken back" | Step 4 failed; the old state is running again. The actual error message is further up in the output and in `sudo journalctl -u rentalars`. Please report it. |

## Keeping Ubuntu and Python up to date

Rentalars uses the Python of your Ubuntu and builds on Django in a long-term
support version; both get security fixes for years (NFA-054). Supported are
Ubuntu Server 24.04 LTS and 26.04 LTS (NFA-063), on a Raspberry Pi 4 or 5
also Raspberry Pi OS based on Debian 13 (NFA-070;
[installation.md](installation.md), "Which Ubuntu version?" and "Raspberry
Pi"). On Raspberry Pi OS, read "Debian" instead of "Ubuntu" here: security
updates work the same way with `apt`.

- **Ubuntu:** install security updates continuously
  (`sudo apt update && sudo apt upgrade`, or automatically).
- **Rentalars:** every new version brings the libraries to the state it was
  tested with. Whoever updates also has the security fixes of Django.

### Switching from Ubuntu 24.04 to 26.04

Ubuntu 26.04 brings a new Python (3.14 instead of 3.12), a new NGINX and a
new MariaDB. The data stays where it is. But the Python libraries of
Rentalars are set up for the old Python – **so after the switch Rentalars
does not start until you have updated it once.** Plan a quiet hour for this.

1. Bring Rentalars to the newest version and leave the
   package on the server.
2. `sudo rentalars backup --keep` – and **fetch the file from the server**.
3. Upgrade Ubuntu: `sudo do-release-upgrade`. You answer the program's
   questions about changed configuration files of NGINX and MariaDB with
   "keep" ("beibehalten" on a German system; that is the default).
4. After the restart the browser shows "502 Bad Gateway". That is expected.
5. Update once, with the same package as in step 1:

   ```sh
   sudo rentalars update rentalars-1.0.0.tar.gz
   ```

   The command reports "Note: Rentalars is not running at the moment",
   backs up, sets up the libraries for the new
   Python, writes the configuration of NGINX in the form the new NGINX
   expects, and starts Rentalars.
6. Log in and click through as after every update.

`sudo rentalars rollback` does **not** lead back after this step: the
previous version of Rentalars belongs to the old Python, which no longer
exists. The way back is the backup from step 2 on a server with the old
Ubuntu.
