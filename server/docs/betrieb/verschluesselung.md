# Verschlüsselung von Datenbank und Sicherungen

Rentalars kann seine Daten verschlüsselt ablegen (NFA-067): die Dateien der
Datenbank auf der Platte und jede Sicherung. Wer die Platte ausbaut, ein
Abbild der virtuellen Maschine kopiert oder eine Sicherung in die Hände
bekommt, liest damit nichts.

Diese Seite erklärt, was verschlüsselt wird, wo der Schlüssel liegt, wie du
ihn im Notfall benutzt – auch ganz ohne Rentalars – und wie du die
Verschlüsselung nachträglich einschaltest.

## Kurz gesagt

- Ein einziges Geheimnis öffnet alles: der **Wiederherstellungsschlüssel**.
  Er sieht so aus: `3f9a-07c2-91be-5d40-e8a1-6c2f-0b7d-44e9-a915-c03e`.
- Die Installation zeigt ihn **einmal** an. Schreib ihn auf oder druck ihn
  aus und bewahre ihn **getrennt vom Server** auf – im Tresor, im
  Passwortmanager der Geschäftsführung.
- Auf dem Server liegt er in `/etc/rentalars/recovery-key`, lesbar nur für
  root. `sudo rentalars encryption show-key` zeigt ihn jederzeit wieder.
- Solange der Server läuft, merkt niemand etwas von der Verschlüsselung:
  Rentalars, die Sicherung und die Wiederherstellung arbeiten wie immer.
- Ohne den Schlüssel sind verschlüsselte Sicherungen **verloren**. Das ist
  der Sinn der Sache – und der Grund, ihn aufzuschreiben.
- Eine Ausnahme: Eine **Sicherung aus dem Browser** hat ihren
  eigenen Schlüssel, weil Rentalars den Wiederherstellungsschlüssel nicht
  lesen darf ([sicherung.md](sicherung.md), „Sicherung aus dem Browser“).

## Was verschlüsselt wird – und was nicht

| | verschlüsselt |
|---|---|
| Tabellen der Datenbank auf der Platte | ja – MariaDB verschlüsselt jede Seite, bevor sie geschrieben wird |
| Protokolldateien und Zwischendateien von MariaDB | ja (Redo-Log, temporäre Tabellen, Sortierdateien, Binärlog) |
| Sicherungen in `/var/backups/rentalars/` | ja – Endung `.tar.gz.enc` |
| Sicherungen aus dem Browser (bis zum Löschen in `/var/lib/rentalars/media/jobs/backups/`) | ja – mit einem eigenen Schlüssel je Datei ([sicherung.md](sicherung.md)) |
| Hochgeladene Dateien in `/var/lib/rentalars/` | nein, aber in jeder Sicherung verschlüsselt enthalten |
| Die Verbindung zwischen Browser und Server | immer, über HTTPS – unabhängig von dieser Einstellung |
| Was im Arbeitsspeicher eines laufenden Servers liegt | nein – das kann keine Verschlüsselung der Platte leisten |

Die Verschlüsselung schützt also **ruhende Daten**: eine gestohlene Platte,
ein kopiertes Abbild, eine Sicherung auf einem verlorenen USB-Stick. Gegen
jemanden, der sich als root auf dem laufenden Server anmeldet, schützt sie
nicht – der liest den Schlüssel einfach mit.

Die Passwörter des Projektpostfachs und die Schlüssel der
Zwei-Faktor-Anmeldung stehen in jedem Fall verschlüsselt in der Datenbank
(EML-002, AUT-006), auch ohne diese Einstellung; ebenso die
Passwörter der CalDAV-Kalender der Personen (PER-023) und die Schlüssel
der Sicherungen aus dem Browser.

### Mit einem vorhandenen Datenbankserver

Liegt die Datenbank auf einem anderen Server (Installation mit
`--db-host`, siehe [installation.md](installation.md)), verschlüsselt
Rentalars **die Sicherungen**. Ob die Dateien der Datenbank verschlüsselt
sind, entscheidet, wer jenen Server betreibt. `sudo rentalars encryption
status` und die Selbstprüfung (Einstellungen → Selbsttest) zeigen, was sie
dort vorfinden.

## Wie es funktioniert

```
Wiederherstellungsschlüssel  /etc/rentalars/recovery-key   (nur root)
   │
   ├── verschlüsselt jede Sicherung       (openssl, AES-256)
   │
   └── schließt den Schlüssel von MariaDB auf
          /etc/mysql/rentalars-encryption/filekey   = der Wiederherstellungsschlüssel
          /etc/mysql/rentalars-encryption/keys.enc  = der eigentliche Datenbankschlüssel,
                                                       mit dem Wiederherstellungsschlüssel verschlüsselt
          /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf
                                                     = sagt MariaDB, dass es verschlüsseln soll
```

MariaDB verschlüsselt mit seiner eingebauten Schlüsselverwaltung
(`file_key_management`) – einem Bestandteil jeder MariaDB, nichts
Zusätzliches. Beim Start liest MariaDB den Datenbankschlüssel aus
`keys.enc` und entschlüsselt ihn mit `filekey`.

> **Lösche nie** den Ordner `/etc/mysql/rentalars-encryption` oder die
> Datei `61-rentalars-encryption.cnf`, solange die Datenbank Daten enthält.
> MariaDB könnte seine eigenen Dateien dann nicht mehr lesen.

## Verschlüsselung bei der Installation

Das Installationsskript fragt:

```
Datenbank und Sicherungen verschlüsseln? Dann zeigt das Skript am Ende einen
Wiederherstellungsschlüssel, der aufgeschrieben werden muss.
Verschlüsseln? [j/N]
```

Ohne Rückfragen: `--encrypt`. Am Ende steht der Schlüssel in einem Kasten,
und das Skript wartet, bis du bestätigst, dass er aufgeschrieben ist.

## Nachträglich verschlüsseln

Eine bestehende Installation lässt sich jederzeit verschlüsseln (NFA-068) –
auf dem Server, als root; einen Knopf im Browser gibt es dafür bewusst
nicht (unten, „Den Zustand ansehen“):

```sh
sudo rentalars encryption enable
```

Was dabei geschieht:

1. Eine **Sicherung** des jetzigen Stands entsteht. Sie wird nie
   automatisch gelöscht (`…-keep.tar.gz`).
2. Rentalars wird **angehalten**. Für jede Tabelle wird ein
   **Fingerabdruck** genommen: die Zahl der Zeilen und eine Prüfsumme über
   alle Werte.
3. MariaDB bekommt seinen Schlüssel und startet neu. Dann verschlüsselt es
   alle Tabellen im Hintergrund – Seite für Seite, mit derselben
   absturzsicheren Buchführung, mit der es jede andere Änderung schreibt.
   Bei einer kleinen Datenbank dauert das Sekunden.
4. Sobald jede Tabelle verschlüsselt ist, wird der Fingerabdruck noch einmal
   genommen und verglichen. **Nur wenn nicht ein Wert abweicht**, startet
   Rentalars wieder. Sonst bleibt es angehalten, und das Skript sagt, was zu
   tun ist – die Sicherung aus Schritt 1 liegt bereit.
5. Die schon vorhandenen Sicherungen werden verschlüsselt, alle künftigen
   ebenso.

Rentalars ist dabei für die Dauer der Schritte 2 bis 4 nicht erreichbar.
Am Ende zeigt das Skript den Wiederherstellungsschlüssel – aufschreiben.

Wem das an Ort und Stelle zu heikel ist, der zieht stattdessen in eine neue
Datenbank um, die von Anfang an verschlüsselt ist – auf einem anderen
Datenbankserver, der verschlüsselt, oder auf diesem: siehe
[betrieb.md](betrieb.md), „Die Datenbank umziehen“. Auch dort wird erst
umgestellt, wenn der Vergleich aller Tabellen stimmt, und die alte Datenbank
bleibt als Rückweg stehen.

## Den Zustand ansehen

```sh
sudo rentalars encryption status
```

```
==> Verschlüsselung
    Datenbank                    verschlüsselt (61 von 61 Tabellen)
    neue Sicherungen             verschlüsselt
    Sicherungen im Ordner        3 verschlüsselt, 0 unverschlüsselt
    Wiederherstellungsschlüssel  /etc/rentalars/recovery-key (nur root)
```

**Im Browser** zeigt **Einstellungen → Sicherung und
Verschlüsselung** (ADM-009) dasselbe für alle, die die Einstellungen sehen
dürfen: ob die Datenbank verschlüsselt ist, ob neue Sicherungen
verschlüsselt werden, ob es die letzte nächtliche war und ob es einen
Wiederherstellungsschlüssel gibt – den Schlüssel selbst nicht. Liegt die
Datenbank auf einem anderen Server, sagt die Seite, dass jener über die
Verschlüsselung ihrer Dateien entscheidet.

Einen **Knopf zum Einschalten gibt es dort mit Absicht nicht.** Das
Einschalten ändert die Einstellungen von MariaDB, startet die Datenbank neu
und legt einen Schlüssel ab, den nur root lesen darf. Rentalars selbst
läuft absichtlich ohne diese Rechte – so könnte selbst jemand, der ein
Administratorkonto übernimmt, weder den Datenbankserver ändern noch den
Schlüssel lesen. Die Seite erklärt stattdessen den Befehl
`sudo rentalars encryption enable` (oben, „Nachträglich verschlüsseln“);
ist die Verschlüsselung schon eingeschaltet, nennt sie
`sudo rentalars encryption show-key`.

## Im Notfall

### Der Server läuft, ich will an die Daten

Nichts zu tun: Der laufende Server entschlüsselt alles selbst. Eine
unverschlüsselte Kopie der Datenbank – etwa für einen Wechsel zu einem
anderen Programm – bekommst du mit

```sh
sudo mariadb-dump --single-transaction rentalars > rentalars.sql
```

### Der Server ist weg, ich habe eine Sicherung und den Schlüssel

Lege den Schlüssel in eine Datei – genau wie aufgeschrieben, mit den
Bindestrichen, in einer Zeile:

```sh
printf '%s\n' '3f9a-07c2-91be-5d40-e8a1-6c2f-0b7d-44e9-a915-c03e' > schluessel.txt
chmod 600 schluessel.txt
```

**Mit Rentalars:** Installiere Rentalars auf einem neuen Server und spiele
die Sicherung ein:

```sh
sudo rentalars restore rentalars-2026-10-10_023000.tar.gz.enc --key-file schluessel.txt
```

**Ohne Rentalars, nur mit openssl** – auf jedem Linux, macOS oder Windows mit
openssl 1.1.1 oder neuer:

```sh
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 \
    -pass file:schluessel.txt \
    -in rentalars-2026-10-10_023000.tar.gz.enc -out rentalars-2026-10-10_023000.tar.gz
tar -xzf rentalars-2026-10-10_023000.tar.gz
```

Darin liegen:

| Datei | Inhalt |
|---|---|
| `database.sql` (bei verschlüsselten Sicherungen `database.sql.enc`, mit demselben Schlüssel verschlüsselt) | die ganze Datenbank als SQL – lesbar mit jedem Texteditor, einspielbar in jede MariaDB: `mariadb rentalars < database.sql` |
| `media/` | die hochgeladenen Dateien (Logo, Projektdateien, Mailanhänge, Hallenpläne) |
| `rentalars.conf` | die Konfiguration samt Zugangsdaten |
| `VERSION` | welche Version von Rentalars die Sicherung geschrieben hat |

Heißt die Datei `database.sql.enc` (der Datenbankauszug
einer verschlüsselten Sicherung liegt nie im Klartext darin), entschlüsselst du sie
mit demselben Schlüssel:
`openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -pass file:schluessel.txt -in database.sql.enc -out database.sql`.

Dieselbe Entschlüsselung als Befehl auf einem Server mit Rentalars:
`sudo rentalars encryption decrypt-backup DATEI --key-file schluessel.txt`.

### Nur die Platte des Servers ist noch da

Die Dateien von MariaDB (`/var/lib/mysql`) lassen sich mit einer anderen
MariaDB lesen, wenn sie dieselbe Schlüsselverwaltung bekommt:

1. Auf dem neuen Rechner MariaDB derselben Hauptversion installieren und
   anhalten.
2. Den Ordner `/var/lib/mysql` von der alten Platte an dieselbe Stelle
   kopieren (Besitzer `mysql`).
3. Den Ordner `/etc/mysql/rentalars-encryption` und die Datei
   `/etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf` von der alten
   Platte kopieren. Ohne `keys.enc` aus diesem Ordner sind die Dateien der
   Datenbank nicht zu lesen; dann hilft nur eine Sicherung (vorheriger
   Abschnitt).
4. Die Datei `filekey` enthält den Wiederherstellungsschlüssel. Fehlt sie,
   schreib ihn – ohne Zeilenende – hinein:
   `printf '%s' 'SCHLÜSSEL' > /etc/mysql/rentalars-encryption/filekey`.
5. MariaDB starten und mit `mariadb-dump` eine unverschlüsselte Kopie
   ziehen.

Zur Kontrolle, dass ein Schlüssel passt, entschlüsselt dieser Befehl den
Datenbankschlüssel (er zeigt eine Zeile `1;` und 64 Zeichen):

```sh
sudo openssl enc -d -aes-256-cbc -md sha1 \
    -pass file:/etc/mysql/rentalars-encryption/filekey \
    -in /etc/mysql/rentalars-encryption/keys.enc
```

(`-md sha1` ist kein Versehen: Das ist das ältere Format, das MariaDB für
diese Datei verlangt. Der eigentliche Schlüssel ist eine Zufallszahl mit
256 Bit.)

### Der Schlüssel ist verloren, der Server läuft noch

Dann ist noch nichts verloren: Der laufende Server kennt ihn.
`sudo rentalars encryption show-key` zeigt ihn – aufschreiben, diesmal
richtig. Nur wenn Server **und** Schlüssel weg sind, sind die verschlüsselten
Sicherungen nicht mehr zu öffnen.

## Fragen

**Wird Rentalars langsamer?** Kaum merklich. MariaDB ver- und entschlüsselt
nur, was es von der Platte liest oder darauf schreibt; die meisten Daten
liegen ohnehin im Arbeitsspeicher. Die Sicherung dauert ein paar Sekunden
länger.

**Kann ich die Verschlüsselung wieder ausschalten?** Nicht mit einem Befehl.
Der Weg führt über einen Umzug in eine unverschlüsselte Datenbank
(`rentalars move-database`, siehe [betrieb.md](betrieb.md)) und
`[backup] encrypt = false` in der Konfiguration.

**Kann ich den Schlüssel wechseln?** In dieser Version nicht. Wer meint, der
Schlüssel sei in falsche Hände geraten, zieht in eine neue Datenbank auf einem
neu eingerichteten Server um.

**Und die Sicherungen auf einem anderen Rechner?** Sind verschlüsselt, ganz
gleich, wohin du sie kopierst. Das ist ein guter Grund, die Verschlüsselung
einzuschalten, wenn Sicherungen in fremde Hände kommen – zu einem
Speicheranbieter, auf eine Platte im Büro.
