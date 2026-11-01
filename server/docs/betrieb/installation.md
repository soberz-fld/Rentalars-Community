# Installation

Diese Anleitung führt von einem frisch installierten Ubuntu Server zu einem
laufenden Rentalars mit HTTPS. Du brauchst dafür keine Programmierkenntnisse,
aber einen Zugang zum Server mit `sudo`. Statt eines Servers geht
auch ein Raspberry Pi 4 oder 5; was dort anders ist, steht im Abschnitt
[„Raspberry Pi“](#raspberry-pi).

Kurzfassung für Eilige:

```sh
tar -xzf rentalars-1.0.0.tar.gz
cd rentalars-1.0.0
sudo ./deploy/install.sh
```

Das Skript fragt nach dem Namen des Servers, nach dem Zertifikat, wo die
Datenbank liegen soll und ob verschlüsselt wird. Dann richtet es alles ein
und nennt am Ende eine Adresse. Die öffnest du im Browser, trägst Firma und
Administrator ein – fertig.

## 1. Was du brauchst

### Server

| | Mindestens | Empfohlen (Referenzsystem) |
|---|---|---|
| Betriebssystem | Ubuntu Server 24.04 LTS oder 26.04 LTS, frisch installiert; auf einem Raspberry Pi auch Raspberry Pi OS (Abschnitt [„Raspberry Pi“](#raspberry-pi)) | |
| Prozessor | 2 Kerne | 4 Kerne |
| Arbeitsspeicher | 4 GB | 8 GB |
| Speicherplatz | 20 GB frei, SSD | 40 GB SSD |

Auf dem Referenzsystem – 4 Kerne, 8 GB – läuft alles zusammen flüssig für
einen kleinen Betrieb mit bis zu zwei Personen, die gleichzeitig arbeiten;
für diese Größe gelten die zugesagten Antwortzeiten (NFA-038, NFA-039). Im
Betrieb belegt Rentalars samt Datenbank und NGINX rund 0,5 GB
Arbeitsspeicher, also weit weniger als die Hälfte (NFA-040); der Rest bleibt
für Sicherung, PDF-Erzeugung und Import. Die gemessenen Zeiten stehen in
[betrieb.md](betrieb.md), Abschnitt „Leistung“.

Arbeiten dauerhaft mehr als etwa zehn Personen gleichzeitig, plane 8 Kerne
und 16 GB ein und erhöhe die Zahl der Arbeitsprozesse (siehe
[betrieb.md](betrieb.md), „Mehr gleichzeitige Nutzer“).

### Welche Ubuntu-Version? (NFA-063)

Beide gehen: **Ubuntu Server 24.04 LTS** und **26.04 LTS**. Skript,
Aktualisierung, Sicherung und Wiederherstellung sind auf beiden erprobt.
Nimm für einen neuen Server die neuere; sie bekommt länger
Sicherheitskorrekturen.

| | Ubuntu 24.04 LTS | Ubuntu 26.04 LTS |
|---|---|---|
| Python | 3.12 | 3.14 |
| NGINX | 1.24 | 1.28 |
| MariaDB | 10.11 | 11.8 |

Du musst dich um die Unterschiede nicht kümmern: Rentalars läuft mit beiden
Python-Versionen, und das Skript schreibt die Konfiguration von NGINX so,
wie die vorgefundene Version sie versteht.

- Auf einem **älteren Ubuntu** (22.04 und davor) bricht das Skript ab, bevor
  es etwas ändert – dessen Python ist zu alt.
- Auf einer **anderen neueren Version** (einer Zwischenversion wie 25.10
  oder einer künftigen) läuft das Skript, sagt aber vor dem Start, dass
  diese Version nicht erprobt ist.
- **Ubuntu später von 24.04 auf 26.04 heben** geht auch mit einer
  bestehenden Installation; danach ist ein Befehl nötig. Siehe
  [aktualisierung.md](aktualisierung.md), „Ubuntu und Python aktuell halten“.
- **Auf einem Raspberry Pi 4 oder 5** (64 Bit, mindestens 4 GB) geht Ubuntu Server 24.04 LTS oder 26.04 LTS in der Fassung für den Pi
  und ebenso Raspberry Pi OS auf Basis von Debian 13. Alles dazu im
  Abschnitt [„Raspberry Pi“](#raspberry-pi).
- Auf einem **anderen System** – Debian auf einem gewöhnlichen Server,
  Fedora, ein System mit 32 Bit – bricht das Skript ab, bevor es etwas
  ändert.

Rentalars ist für **einen Betrieb je Installation** gedacht. Mehrere Betriebe
teilen sich keine Installation; jeder betreibt seine eigene mit eigener
Datenbank (NFA-045).

### Speicherplatz: Wie viel, und wodurch er wächst (NFA-043)

Nimm eine SSD. Die Datenbank liest und schreibt viele kleine Stücke; auf
einer herkömmlichen Festplatte wird jede Seite spürbar langsamer.

| Was | Größe |
|---|---|
| Betriebssystem, NGINX, MariaDB, Python | etwa 5 GB |
| Rentalars selbst | etwa 170 MB je Version; es liegen immer zwei nebeneinander (die laufende und die vorige) |
| Datenbank | klein: mit 20.000 Exemplaren und 1.000 Projekten etwa 30 MB |
| Hochgeladene Dateien | Firmenlogo, Projektdateien (auch Showfiles), Hallenpläne, Belege von Spesen und die Anhänge der Projektmails |
| Sicherungen | je Sicherung etwa so groß wie Datenbank plus Dateien, gepackt; 14 Stück werden aufbewahrt |

Den größten Teil machen mit der Zeit die **Anhänge** aus – Bühnenpläne,
Rider, Verträge und die Anlagen der Projektmails – und mit ihnen die
**Sicherungen**, weil jede Sicherung alle Dateien enthält. 14 Sicherungen
von 5 GB Anhängen sind 70 GB. Mit 40 GB bist du für den Anfang großzügig
ausgestattet; beobachte den freien Platz mit `sudo rentalars status` oder im
Selbsttest (Einstellungen → Selbsttest), der ab 2 GB freiem Platz warnt. Wie
lange Projektmails aufbewahrt werden, stellst du unter Einstellungen →
E-Mail ein; voreingestellt ist „unbegrenzt“. Sicherungen, die im Browser
entstehen, liegen bis zum Ablauf der Frist für Aufgaben im Hintergrund
(voreingestellt sieben Tage) im Datenordner.

### Name und Zertifikat

Rentalars ist nur über HTTPS erreichbar. Dafür braucht der Server

- einen **Namen**, unter dem ihn die Nutzer aufrufen, etwa
  `rentalars.example.de`, und einen DNS-Eintrag, der auf den Server zeigt;
- ein **Zertifikat** für diesen Namen. Das Skript kann es auf drei Wegen
  besorgen – welcher passt, hängt davon ab, wie der Server erreichbar ist
  (Abschnitt 3).

Auch wenn der Server in der Testphase nur über VPN erreichbar ist: Rentalars
ist von Beginn an so abgesichert, dass es ohne Umbau ans Internet kann
(NFA-048). Das Skript schreibt immer `url = https://NAME`; ein
Produktionsserver mit einer `http://`-Adresse startet nur, wenn die
Konfiguration ausdrücklich `allow_http = yes` sagt (NFA-073). Steht vor
Rentalars ein weiterer Server, der verschlüsselt (Reverse Proxy, Load
Balancer), bleibt `url` bei `https://…`, und dieser Server muss den Kopf
`X-Forwarded-Proto: https` weitergeben ([betrieb.md](betrieb.md), „HTTPS
und vorgeschaltete Server“).

Name und Zertifikat lassen sich später ändern, ohne neu zu
installieren: Ein Administrator bereitet die Änderung unter Einstellungen →
Serveradresse und Zertifikat vor, du übernimmst sie mit
`sudo rentalars address apply …` ([betrieb.md](betrieb.md), „Serveradresse
und Zertifikat ändern“).

### Browser

Für die Arbeit mit Rentalars genügt ein aktueller Browser: Chrome, Firefox,
Safari oder Edge in ihrer aktuellen Version (NFA-023), am Rechner wie am
Telefon. Ein Programm muss niemand installieren.

### E-Mail (kann später kommen)

Rentalars braucht E-Mail an zwei Stellen, beide über Postfächer bei einem
Anbieter deiner Wahl – einen eigenen Mailserver betreibt es nicht:

- **Systemmails** – Einladungen, „Passwort vergessen“, Benachrichtigungen –
  gehen über ein Postfach, das du nach der Installation in der
  Konfigurationsdatei einträgst (Abschnitt 6). Ohne funktioniert alles
  andere; die Einladungslinks stehen dann im Protokoll des Dienstes.
- Das **Projektpostfach** – aus ihm holt Rentalars die Mails mit dem
  Projektkürzel im Betreff, und über es schreibst du aus dem Projekt –
  richtest du im Browser ein (Einstellungen → E-Mail). Siehe
  [Benutzerhandbuch](../handbuch/benutzerhandbuch.md), „Korrespondenz“.

Beides darf dasselbe Postfach sein.

### Kalender der Personen (kann später kommen)

Personen können ihre Einsätze in ihren eigenen Kalender holen
und einen Kalender mit ihren belegten Zeiten verknüpfen (PER-022, PER-023).
Für die Installation heißt das:

- Für einen **Abo-Link** – die Kalender-App holt die Einsätze selbst ab –
  muss die App Rentalars unter `https://NAME/calendar-feed/…` erreichen,
  in der Regel also aus dem Internet; Google Kalender etwa holt solche
  Links von seinen eigenen Servern. Ist der Server nur intern oder per VPN
  erreichbar, nehmt stattdessen einen **CalDAV-Kalender** (Nextcloud,
  iCloud, mailbox.org, Posteo …), in den Rentalars die Einsätze schreibt.
- Für einen CalDAV-Kalender und für einen verknüpften Kalender muss der
  Server **nach außen** Verbindungen per HTTPS aufbauen dürfen – zu den
  Kalenderdiensten, bei einer eigenen Nextcloud auch ins interne Netz.
  Ein Ziel im internen Netz (Nextcloud, NAS) erreicht Rentalars
  nur, wenn es in der Konfigurationsdatei unter `[network]
  allow_internal` freigegeben ist ([betrieb.md](betrieb.md), „Verbindungen
  ins interne Netz“).

Einzurichten ist auf dem Server dafür nichts; mehr in
[betrieb.md](betrieb.md), „Kalender der Personen“.

### Webhooks und Buchhaltung (kann später kommen)

Rentalars kann anderen Systemen über **Webhooks** melden, was
geschieht, und Rechnungen an **Lexware Office** übergeben. Beides braucht
**Verbindungen nach außen**: zu den empfangenden Systemen per HTTP oder
HTTPS – ins interne Netz nur mit Freigabe unter `[network]
allow_internal` –, und zu `api.lexware.io` per HTTPS. Braucht
der Server dafür einen Proxy, nimmt Rentalars ihn aus der Umgebung des
Dienstes. Der **DATEV-Export** braucht keine Verbindung. Einzurichten ist
auf dem Server nichts; mehr in [betrieb.md](betrieb.md), „Webhooks“ und
„Buchhaltung“.

### Karten (kann später kommen)

Rentalars zeigt Anschriften auf einer Karte von OpenStreetMap
und verlinkt Routen zu Google Maps. Eine Karte erscheint erst nach einem
Klick auf „Karte anzeigen“; dann fragt **der Server** per HTTPS die
Kartensuche `nominatim.openstreetmap.org`, wo die Anschrift liegt, und
**die Browser** laden die Kartenbilder von `tile.openstreetmap.org`. Wie
es die Regeln von OpenStreetMap verlangen, sendet der Browser dabei die
Adresse der Installation als Referer, und die Kartensuche nennt sie im
User-Agent. Einen
Proxy nimmt Rentalars aus der Umgebung des Dienstes. Einzurichten ist
nichts; wer keine Karten will oder eigene Kartenserver betreibt, trägt das
im Abschnitt `[maps]` der Konfigurationsdatei ein ([betrieb.md](betrieb.md),
„Karten“).

### Lokale KI (kann später kommen)

Rentalars fasst auf Wunsch die Korrespondenz eines Projekts mit
einer KI auf diesem Server zusammen – die Mails verlassen den Server
nicht. Dafür richtest du nach der Installation mit
`sudo rentalars ai install` ein kleines Sprachmodell als Dienst ein; ohne
das läuft alles andere genauso. Es braucht mindestens 1,5 GB
Arbeitsspeicher (das größere Modell, das bis zu 5 GB belegt,
nur ab 6 GB, vier physischen Kernen und einem Prozessor mit AVX2 und FMA,
sonst das kleinere Qwen3 1.7B), 1,5 bis 4 GB Platz unter `/opt/rentalars`
und für den Download Zugang zu `huggingface.co`, auf Ubuntu 24.04 und
Raspberry Pi OS auch zu `github.com`. In einer virtuellen Maschine (etwa
unter Proxmox) vorher den Prozessortyp auf „host“ stellen, sonst fehlen
AVX2 und FMA und die KI ist um ein Vielfaches langsamer. Weiter mit
`sudo rentalars ai status`, `register` und `remove`; nach Updates
übernimmt `ai refresh` die Einstellungen selbst; alles in
[betrieb.md](betrieb.md), „KI“.

### Wo die Datenbank liegt

Voreingestellt richtet das Skript MariaDB **auf demselben Server** ein. Das
ist für fast alle Betriebe das Richtige: nichts weiter zu tun, nichts weiter
zu sichern.

Gibt es im Betrieb schon einen **MariaDB-Server**, etwa weil die IT ihre
Datenbanken an einer Stelle betreibt und sichert, kann Rentalars ihn nutzen
(NFA-066). Was dafür vorbereitet sein muss, steht in Abschnitt 3,
„Vorhandener Datenbankserver“.

### Verschlüsselung

Auf Wunsch legt Rentalars Datenbank und Sicherungen verschlüsselt ab
(NFA-067). Dann gibt es einen **Wiederherstellungsschlüssel**, den du
aufschreiben und getrennt vom Server aufbewahren musst. Alles dazu:
[verschluesselung.md](verschluesselung.md). Das lässt sich auch später noch
einschalten.

## 2. Paket auf den Server bringen

Kopiere `rentalars-1.0.0.tar.gz` auf den Server, zum Beispiel mit `scp`:

```sh
scp rentalars-1.0.0.tar.gz du@rentalars.example.de:
```

Auf dem Server:

```sh
tar -xzf rentalars-1.0.0.tar.gz
cd rentalars-1.0.0
```

## 3. Installieren

```sh
sudo ./deploy/install.sh
```

Das Skript spricht Deutsch, wenn die Spracheinstellung des Servers Deutsch
ist (`LANG` oder `LC_ALL` beginnt mit `de`), sonst Englisch – auch bei
`C.UTF-8`, wie es auf vielen frisch installierten Servern eingestellt ist.
`RENTALARS_LANG=de` oder `RENTALARS_LANG=en` entscheidet ausdrücklich, etwa
`sudo RENTALARS_LANG=de ./deploy/install.sh`. Dasselbe gilt für
alle anderen Skripte und den Befehl `rentalars`. Es fragt:

1. **Hostname** – der Name aus Abschnitt 1, ohne `https://`.
2. **Woher kommt das Zertifikat?**

   | Auswahl | Wann | Was du brauchst |
   |---|---|---|
   | 1 – Let's Encrypt | Der Server ist aus dem Internet auf Port 80 erreichbar. | eine E-Mail-Adresse für Hinweise von Let's Encrypt |
   | 2 – Let's Encrypt mit DNS-Eintrag | Der Server ist nur intern oder per VPN erreichbar. | Zugriff auf die DNS-Einträge deiner Domain |
   | 3 – Eigenes Zertifikat | Du hast schon eines, z. B. von einer eigenen Zertifizierungsstelle. | Zertifikat samt Kette und privater Schlüssel als PEM-Dateien auf dem Server |
   | 4 – Selbst erstellt | Nur zum Ausprobieren. | nichts; Browser zeigen eine Warnung |

3. **Wo liegt die Datenbank?** 1 – auf diesem Server (Voreinstellung), 2 –
   auf einem vorhandenen MariaDB-Server. Bei 2 fragt es nach Host, Port,
   Datenbank, Benutzer, Passwort und TLS; siehe unten.
4. **Verschlüsseln?** Voreingestellt ist Nein. Bei Ja zeigt das Skript am
   Ende den Wiederherstellungsschlüssel ([verschluesselung.md](verschluesselung.md)).
5. **Installation starten?** Vorher zeigt das Skript, was es vorhat. Bis zu
   dieser Frage wurde nichts verändert.

Dann arbeitet es neun Schritte ab und sagt bei jedem, was es tut. Der längste
ist der vierte: Dort werden die Python-Bibliotheken geholt.

Im sechsten Schritt – noch bevor Rentalars oder NGINX eine einzige Anfrage
beantworten – legt das Skript den einmaligen Schlüssel für die
Ersteinrichtung an (NFA-064). Ohne diesen Schlüssel ist die Ersteinrichtung
nicht erreichbar, auch nicht für einen Augenblick während der Installation.

Am Ende steht – mit Verschlüsselung nach dem Kasten mit dem
Wiederherstellungsschlüssel:

```
==> Rentalars 1.0.0 ist installiert.

    Öffne jetzt diese Adresse im Browser und richte Firma und Administrator ein:

        https://rentalars.example.de/setup/?token=…
```

### Zu den Zertifikaten im Einzelnen

**Let's Encrypt (Auswahl 1).** Let's Encrypt ruft den Server über Port 80
auf, um zu prüfen, dass dir der Name gehört. Port 80 und 443 müssen also aus
dem Internet erreichbar sein. Das Zertifikat erneuert sich danach von selbst.

**Let's Encrypt mit DNS-Eintrag (Auswahl 2).** Der Server muss nicht
erreichbar sein. Stattdessen legst du bei deinem DNS-Anbieter einen
TXT-Eintrag an, den das Skript dir nennt, und bestätigst mit Enter.
**Achtung:** Auf diesem Weg erneuert sich das Zertifikat nicht von selbst;
es gilt 90 Tage (Erneuern: [betrieb.md](betrieb.md), „Zertifikat“). Wenn dein
DNS-Anbieter eine Schnittstelle hat, geht es auch ohne Handarbeit und mit
automatischer Erneuerung:

```sh
sudo ./deploy/install.sh --domain rentalars.example.de --email du@example.de \
    --tls dns --dns-plugin cloudflare --dns-credentials /root/cloudflare.ini
```

Welche Anbieter es gibt und wie die Datei mit den Zugangsdaten aussieht,
steht in der Dokumentation von certbot („DNS plugins“).

**Eigenes Zertifikat (Auswahl 3).** Das Skript kopiert beide Dateien nach
`/etc/rentalars/tls/`. Läuft das Zertifikat ab, ersetzt du die Dateien dort
und lädst NGINX neu (`sudo systemctl reload nginx`).

### Vorhandener Datenbankserver

Rentalars legt auf einem fremden Datenbankserver nichts an: Datenbank und
Benutzer bereitest du dort vor. Auf dem Datenbankserver, als dessen
Administrator:

```sql
CREATE DATABASE rentalars CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'rentalars'@'192.0.2.10' IDENTIFIED BY 'ein-langes-zufälliges-passwort';
GRANT ALL PRIVILEGES ON rentalars.* TO 'rentalars'@'192.0.2.10';
```

`192.0.2.10` ist die Adresse des Rentalars-Servers; `'%'` ginge auch, ist
aber offener als nötig. Die Datenbank muss leer sein.

Dann auf dem Rentalars-Server:

```sh
sudo ./deploy/install.sh --domain rentalars.example.de --email du@example.de     --db-host db.example.de --db-name rentalars --db-user rentalars     --db-password-file /root/db-passwort.txt --db-tls-ca /root/db-ca.pem
```

oder ohne Optionen und die Fragen beantworten. Das Passwort steht in der
ersten Zeile der Datei; als Option würde es in der Prozessliste des Servers
auftauchen.

**Was das Skript prüft, bevor es etwas ändert:**

- Die Verbindung klappt, und die Datenbank ist leer.
- **Nie root.** Der Benutzer `root` wird abgelehnt, ehe überhaupt eine
  Verbindung aufgebaut wird.
- **Alle Rechte auf genau diese Datenbank, und keine anderen.** Abgelehnt
  wird ein Benutzer mit Rechten auf den ganzen Server (`GRANT … ON *.*`),
  auf weitere Datenbanken, mit Rechten über eine Rolle, die das hergibt,
  oder mit dem Recht, sich als ein anderer Benutzer anzumelden (`PROXY`). Das
  Skript nennt jeden Grund einzeln, damit der Datenbankadministrator weiß,
  was zu ändern ist.
- Der Zeichensatz ist `utf8mb4`; sonst stellt das Skript ihn für die leere
  Datenbank um.

Rentalars braucht die vollen Rechte auf seine Datenbank, weil jede neue
Version ihre Tabellen selbst anpasst. Mehr braucht es nicht – und ein
Zugang mit mehr Rechten läge sonst in der Konfigurationsdatei jedes
Rentalars-Servers.

**Verschlüsselte Verbindung.** Liegt die Datenbank auf einem anderen
Rechner, verbindet Rentalars sich über TLS (Voreinstellung). Mit
`--db-tls-ca` prüft es zusätzlich das Zertifikat des Datenbankservers und
dessen Namen – dann kann sich niemand dazwischenschalten. Ohne wird nur
verschlüsselt. `--db-no-tls` schaltet TLS ab; das ist nur in einem
abgeschlossenen Netz vertretbar, und die Selbstprüfung erinnert daran.

**Sicherung und Verschlüsselung.** Die tägliche Sicherung holt die Daten
auch vom fremden Server und legt sie wie gewohnt auf dem Rentalars-Server
ab. `--encrypt` verschlüsselt hier die Sicherungen; ob die Dateien der
Datenbank verschlüsselt sind, entscheidet der Datenbankserver.

**Später wechseln.** Mit `sudo rentalars move-database` ziehen die Daten in
eine andere Datenbank um – auf einen anderen Server oder zurück auf diesen.
Siehe [betrieb.md](betrieb.md), „Die Datenbank umziehen“.

### Ohne Rückfragen

Alle Angaben lassen sich als Optionen mitgeben, etwa für eine automatisierte
Einrichtung. `sudo ./deploy/install.sh --help` zeigt alle.

```sh
sudo ./deploy/install.sh --domain rentalars.example.de --email du@example.de --yes
```

## 4. Ersteinrichtung im Browser

Öffne die Adresse, die das Skript genannt hat. Sie gilt genau einmal und
enthält den Einrichtungsschlüssel, damit nicht jemand anderes schneller ist
und sich zum Administrator macht. Wer die Seite ohne den Schlüssel oder mit
einem falschen aufruft, bekommt nur den Hinweis, dass es die einmalige
Adresse braucht; nach der Ersteinrichtung führt die Adresse zur Startseite.
Verloren? `sudo rentalars prepare_setup` nennt eine neue Adresse; die alte
gilt dann nicht mehr.

> **Wer ohne das Skript installiert,** führt `rentalars prepare_setup` aus,
> **bevor** er den Webserver startet. Solange kein Schlüssel angelegt ist,
> bleibt die Ersteinrichtung geschlossen – es kann also niemand
> zuvorkommen, aber auch du kommst erst mit der Adresse hinein, die der
> Befehl nennt.

Du trägst ein:

- **Firma** – Name und Anschrift; sie erscheinen auf der Packliste. Mit
  **„Sprache“** wählst du die Sprache der Dokumente für Kunden und der
  Startdaten (Rollen, Einheiten, Kategorien …): „Deutsch“ oder „English“.
  Vorgewählt ist die Sprache deines Browsers. Die Sprache der Oberfläche
  wählt jede Person selbst; der erste Administrator bekommt die hier
  gewählte.
- **Erster Administrator** – Benutzername, Name, E-Mail-Adresse, Passwort.
  Wie jedes Konto steht er danach auch im Personal (jede
  Anmeldung ist eine Person).
- **Nummernkreise** – mit welcher Nummer Projekte, Kunden und Material-IDs
  beginnen, und das **Präfix der Projektnummern**, voreingestellt
  `{year}-`: `{year}` wird durch das laufende Jahr ersetzt, das erste
  Projekt heißt also `2026-0001`. Wenn du die Excel-Liste übernimmst,
  setzt der Import die nächste Material-ID von selbst hinter die höchste
  vorhandene.
- **Steuersatz** – voreingestellt 19 %.
- **Beispieldaten** – ein paar Produkte, Material, Kunden und Projekte zum
  Ausprobieren. Für den echten Betrieb lässt du das Häkchen weg.

Mit der Ersteinrichtung legt Rentalars außer den Stammdaten – Kategorien
samt C „Fremdmaterial“ für das Material von Kunden und N „Nebenkosten“,
Einheiten, Staffel, der Lagerort „Hauptlager“, acht Funktionen mit
ihren Dienstleistungsprodukten, noch ohne Preis, und die Dokumentarten
samt „Showfile“ für die Showfiles von Pulten –
auch die Projektvorlage **„Dry Hire (Vermietung ohne Personal)“** an, für
Vermietungen, bei denen der Kunde selbst abholt – auch die drei
Automationen für Servicefälle. Das sind die Namen einer Installation auf
Deutsch; wählst du „English“, heißen sie „Customer material“, „Incidental
costs“, „Main warehouse“, „Show file“ und „Dry Hire (rental without
crew)“. Brauchst du die Vorlage nicht,
löschst du sie unter Projekte → Vorlagen; sie kommt nicht wieder. Die
Zuschläge für Nacht, Sonn- und Feiertage (Einstellungen → Zuschläge)
stehen auf den Sätzen nach § 3b EStG, sind aber ausgeschaltet, bis ihr sie
einschaltet; „Rentalars als Buchhaltungsprogramm verwenden“ ist an.

Danach bist du angemeldet. Wie es weitergeht, steht im
[Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Kapitel „Die ersten
Schritte“.

## 5. Was jetzt auf dem Server ist

| Was | Wo |
|---|---|
| Programm und Python-Bibliotheken | `/opt/rentalars/` |
| Konfiguration | `/etc/rentalars/rentalars.conf` – die einzige Datei mit Einstellungen und Zugangsdaten |
| Datenbank | MariaDB, Datenbank `rentalars` – oder die Datenbank auf dem vorhandenen Server |
| Wiederherstellungsschlüssel (nur mit Verschlüsselung) | `/etc/rentalars/recovery-key`, lesbar nur für root |
| Hochgeladene Dateien | `/var/lib/rentalars/` |
| Sicherungen | `/var/backups/rentalars/`, jede Nacht um 2:30 Uhr |
| Befehl für alles Weitere | `rentalars` (z. B. `sudo rentalars status`) |
| Diese Anleitungen | `/opt/rentalars/app/docs/` – auf Deutsch, unter `docs/en/` auf Englisch |
| Routendienst (nur nach `sudo rentalars route install`; nach `route register` nur `route-local.conf`) | `/opt/rentalars/routes/`, `/etc/rentalars/route-local.conf`, Paket `routino` |
| Lokale KI (nur nach `sudo rentalars ai install`) | `/opt/rentalars/ai/`, `/etc/rentalars/ai-local.conf` und `ai-local.env`, Dienst `rentalars-ai` (`rentalars-ai-refresh.timer` und `.service` sind immer eingerichtet, laufen aber nur mit lokaler KI) |
| Sicherungen vor einer Änderung der Adresse (nur nach `sudo rentalars address apply`) | `/etc/rentalars/address-backup/` |

Als Dienste laufen genau drei: NGINX, MariaDB und Rentalars selbst
(`rentalars.service`); mit einem vorhandenen Datenbankserver nur zwei. Dazu
kommen fünf Zeitgeber: einer für die tägliche Sicherung, einer für kleine
Aufräumarbeiten und die nächtlichen Prüfungen (fällige Prüfungen,
Mindestbestände), einer, der das Projektpostfach abruft, und
einer, der Aufgaben im Hintergrund nachholt, die nicht gleich starten
konnten, und auch die Kalender der Personen abgleicht, auch die Webhooks zustellt, über fällige Wiedervorlagen
benachrichtigt, wartende Automationen nachholt und
zur eingestellten Zeit Fehlbestände meldet. Der fünfte,
`rentalars-ai-refresh.timer`, startet etwa eine Minute nach
jedem Start des Servers `rentalars-ai-refresh.service`, das die
Einstellungen der lokalen KI übernimmt; ohne lokale KI
(`/etc/rentalars/ai-local.env`) läuft es gar nicht an. Weitere
Dienste – etwa für Warteschlangen oder Zwischenspeicher –
braucht Rentalars nicht: Eine Aufgabe im Hintergrund ist ein eigener
Prozess des Rentalars-Dienstes, der mit ihr endet. Nur wer die lokale KI
einrichtet, bekommt einen vierten Dienst, `rentalars-ai`
([betrieb.md](betrieb.md), „KI“).

Rentalars läuft unter einem eigenen Dienstkonto ohne Anmeldemöglichkeit
(`rentalars`) und darf nur in sein Datenverzeichnis schreiben. Eine
Datenbank auf diesem Server ist nur vom Server selbst erreichbar. Von sich aus überträgt Rentalars
keine Daten an Dritte: Schriften und Skripte kommen vom eigenen Server, es
gibt keine Statistik und keine Prüfung auf neue Versionen (NFA-050). Nur
wenn eine Person es unter „Meine Personaldaten“ einrichtet, liest Rentalars
ihren verknüpften Kalender oder schreibt ihre Einsätze in ihren
CalDAV-Kalender; nur wenn ihr es unter Einstellungen einrichtet, meldet es
Ereignisse an Webhooks oder übergibt Rechnungen an Lexware Office. Eine
Anschrift geht nur dann an die Kartensuche von OpenStreetMap, wenn jemand
ihre Karte öffnet (oben, „Karten“), und an Google Maps nur, wenn jemand
auf „Route in Google Maps“ klickt. Ins eigene Netz und zu diesem Server
selbst verbindet sich Rentalars für Kalender, Webhooks und Postfächer nur, was unter `[network] allow_internal` freigegeben ist
([betrieb.md](betrieb.md), „Verbindungen ins interne Netz“).

**Firewall.** Von außen müssen nur die Ports 443 (HTTPS) und 80 (Weiterleitung
auf HTTPS, Erneuerung des Zertifikats) erreichbar sein, dazu dein Zugang per
SSH. Abo-Links für Kalender-Apps gehen ebenfalls über Port 443. Mit Ubuntus
Firewall:

```sh
sudo ufw allow OpenSSH
sudo ufw allow "Nginx Full"
sudo ufw enable
```

## 6. Systemmails einrichten

Öffne die Konfigurationsdatei:

```sh
sudo nano /etc/rentalars/rentalars.conf
```

Im Abschnitt `[email]` stehen die Zeilen schon, mit `#` davor. Entferne das
`#` und trage die Daten deines Postfachs ein:

```ini
[email]
host = smtp.example.de
port = 587
user = rentalars@example.de
password = …
from_address = rentalars@example.de
```

Dann den Dienst neu starten und probieren:

```sh
sudo systemctl restart rentalars
sudo rentalars sendtestemail du@example.de
```

Oder im Browser: Einstellungen → Selbsttest → „Testmail an mich senden“.
Ob eine Mail hinausging, zeigt auch das Mail-Protokoll
(Einstellungen → Mail-Protokoll). Jede Mail, die
Rentalars von selbst verschickt, endet mit „Diese Nachricht wurde automatisch
von Rentalars für … versendet:“, dem Firmennamen aus der Ersteinrichtung
und der Adresse aus `url` unter `[rentalars]` – sieh in der Testmail
nach, ob die Adresse stimmt ([betrieb.md](betrieb.md), „Postfächer“).

Das **Projektpostfach** richtest du danach im Browser ein (Einstellungen →
E-Mail): IMAP und SMTP des Postfachs, in das deine Kunden schreiben;
voreingestellt versendet Rentalars mit Benutzer und Passwort des Abrufs.
Dort legst du auch die Signatur für alle an.
Rentalars ruft es im eingestellten Abstand ab – voreingestellt alle zwei
Minuten – und fasst dabei nur Mails mit einem Projektkürzel an.

## 7. Nicht vergessen

- **Sicherungen vom Server holen.** Eine Sicherung auf derselben Platte
  übersteht deren Ausfall nicht. Wie das geht: [sicherung.md](sicherung.md).
- **Wiederherstellung einmal üben**, bevor du sie brauchst.
- **Den Wiederherstellungsschlüssel** aufschreiben und getrennt vom Server
  aufbewahren, wenn du verschlüsselt hast.
- **Zwei-Faktor-Anmeldung für die Einstellungen,** spätestens bevor der
  Server aus dem Internet erreichbar ist: Einstellungen → Firmendaten und
  Grundeinstellungen → „Zwei-Faktor-Anmeldung für Administratoren
  vorschreiben“ (NFA-049). Der
  Selbsttest weist darauf hin, solange es nicht eingeschaltet ist.
- **Ubuntu aktuell halten.** `sudo apt update && sudo apt upgrade` –
  oder die automatischen Sicherheitsaktualisierungen von Ubuntu einschalten
  (`sudo dpkg-reconfigure unattended-upgrades`).

## 8. Wenn etwas nicht klappt

Das Skript bricht beim ersten Fehler ab und sagt, woran es lag. Häufig:

| Meldung | Ursache und Abhilfe |
|---|---|
| „Dieses Skript ist für Ubuntu Server gemacht“ / „… ist zu alt“ | Anderes oder älteres System. Gebraucht wird Ubuntu Server 24.04 LTS oder 26.04 LTS – auf einem Raspberry Pi auch Raspberry Pi OS auf Basis von Debian 13. |
| „Rentalars braucht ein 64-Bit-System“ | Auf dem Raspberry Pi läuft ein System mit 32 Bit, auch wenn der Pi selbst 64 Bit kann. Spiel „Raspberry Pi OS Lite (64-bit)“ oder Ubuntu Server für den Pi neu auf (Abschnitt „Raspberry Pi“). |
| „Debian nur als Raspberry Pi OS auf einem Raspberry Pi“ | Debian ist nur auf einem Raspberry Pi vorgesehen. Auf einem gewöhnlichen Server: Ubuntu Server. |
| „Achtung: … auf der SD-Karte“ (vor dem Start) | Kein Fehler, aber ein Risiko: Datenbank oder Sicherungen lägen auf der SD-Karte. Besser von einer SSD starten (Abschnitt „Raspberry Pi“). |
| „System: … – nicht erprobt“ (in der Übersicht vor dem Start) | Kein Fehler: Auf dieser Ubuntu-Version wurde Rentalars noch nicht ausprobiert. Die Installation läuft trotzdem; bitte melde, ob alles geklappt hat. |
| „Auf / sind nur … MB frei“ | Zu wenig Platz; mindestens 3 GB müssen frei sein. |
| „Let's Encrypt konnte kein Zertifikat ausstellen“ | Der Name zeigt (noch) nicht auf den Server, oder Port 80 ist von außen nicht erreichbar. Prüfe den DNS-Eintrag und die Firewall – oder nimm den Weg über den DNS-Eintrag (Auswahl 2). |
| „Rentalars ist hier schon installiert“ | Das Skript verändert keine bestehende Installation. Neue Version: [aktualisierung.md](aktualisierung.md). |
| „Der Benutzer root wird nicht hinterlegt“ | Mit Absicht (NFA-066). Lege auf dem Datenbankserver einen eigenen Benutzer an, wie unter „Vorhandener Datenbankserver“ beschrieben. |
| „Diese Datenbank kann Rentalars nicht verwenden“, darüber Zeilen mit „Abgelehnt:“ | Jede Zeile nennt einen Grund, etwa „… hat Rechte auf den ganzen Datenbankserver: …“ oder „… hat auch Rechte auf andere Datenbanken: …“. Der Benutzer darf nur Rechte auf die eine Datenbank haben: Entziehe die übrigen (`REVOKE`) oder lege einen neuen Benutzer an. Dann das Skript einfach noch einmal starten. |
| „Keine Verbindung zur Datenbank“ | Host, Port, Passwort oder Firewall. Probe von Hand: `mariadb -h HOST -P PORT -u BENUTZER -p DATENBANK`. Mit TLS auch: Bietet der Server TLS an? |
| „Die Datenbank … ist nicht leer“ | Rentalars installiert nur in eine leere Datenbank. Eine vorhandene Sicherung spielst du nach der Installation ein ([sicherung.md](sicherung.md)). |
| „MariaDB verschlüsselt nicht“ | Die Schlüsselverwaltung von MariaDB ließ sich nicht laden. `sudo journalctl -u mariadb` zeigt, warum. |
| „Die Anwendung antwortet nicht“ | `sudo journalctl -u rentalars -n 50` zeigt die Meldungen des Dienstes. |

Ist das Skript in den ersten beiden Schritten abgebrochen, starte es nach
Beheben der Ursache einfach noch einmal. Ab Schritt 3 ist das Programm schon
eingerichtet, und das Skript weigert sich, eine bestehende Installation
anzufassen. Entferne dann die halbe Installation wie in Abschnitt 9 und
beginne neu – es sind ja noch keine Daten da.

## 9. Rentalars wieder entfernen

Wenn du Rentalars nur ausprobiert hast. **Damit sind alle Daten weg**; hol
dir vorher eine Sicherung (`sudo rentalars backup`) vom Server, falls du sie
behalten willst.

```sh
sudo systemctl disable --now rentalars rentalars-backup.timer rentalars-maintenance.timer rentalars-mail.timer rentalars-jobs.timer rentalars-ai-refresh.timer
sudo rm -f /etc/systemd/system/rentalars*.service /etc/systemd/system/rentalars*.timer
sudo systemctl daemon-reload
sudo rm -f /etc/nginx/sites-enabled/rentalars /etc/nginx/sites-available/rentalars \
           /etc/nginx/snippets/rentalars-proxy.conf
sudo systemctl reload nginx
sudo mariadb -e "DROP DATABASE rentalars; DROP USER 'rentalars'@'localhost';"
sudo rm -f /etc/mysql/mariadb.conf.d/60-rentalars.cnf /etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf
# Nur mit Verschlüsselung, und erst NACH dem Löschen der Datenbank – sonst kann MariaDB
# seine Dateien nicht mehr lesen:
sudo rm -rf /etc/mysql/mariadb.conf.d/61-rentalars-encryption.cnf /etc/mysql/rentalars-encryption
sudo systemctl restart mariadb
sudo rm -rf /opt/rentalars /etc/rentalars /var/lib/rentalars /var/backups/rentalars \
            /usr/local/bin/rentalars /var/www/rentalars-acme
sudo gpasswd -d www-data rentalars
sudo userdel rentalars
```

NGINX, MariaDB und Python bleiben installiert; sie gehören zum
Betriebssystem. Mit einem vorhandenen Datenbankserver fällt die Zeile mit
`DROP DATABASE` weg; Datenbank und Benutzer dort entfernt dessen
Administrator.

## Raspberry Pi

Rentalars läuft auch auf einem **Raspberry Pi 4 oder 5**
(NFA-070) – für einen kleinen Betrieb, der keinen eigenen Server aufstellen
will. Installieren, Aktualisieren, Sichern und alles Weitere gehen wie auf
einem Server, mit denselben Befehlen; was anders ist, steht hier.

### Was du brauchst

| | Mindestens | Empfohlen |
|---|---|---|
| Gerät | Raspberry Pi 4 (auch Pi 400, Compute Module 4) | Raspberry Pi 5 (auch Pi 500, Compute Module 5) |
| Arbeitsspeicher | 4 GB | 8 GB |
| Speicher | eine SD-Karte geht, ist aber nicht zu empfehlen | eine **SSD** mit 64 GB oder mehr: per USB 3 (blaue Buchse), beim Pi 5 auch NVMe über einen M.2-Aufsatz |
| System, immer 64 Bit | Ubuntu Server 24.04 LTS oder 26.04 LTS für den Raspberry Pi, oder Raspberry Pi OS Lite (64-bit) auf Basis von Debian 13 „trixie“ | |
| Strom | das offizielle Netzteil des Modells; eine SSD am USB braucht mit | dazu eine kleine USV gegen Stromausfall |
| Kühlung | Kühlkörper | beim Pi 5 der aktive Kühler („Active Cooler“) |
| Netz | Netzwerkkabel; WLAN nur zum Ausprobieren | |

**Warum eine SSD?** Die Datenbank schreibt bei jedem Speichern viele kleine
Stücke. SD-Karten sind für Fotos gemacht: Sie nutzen sich dabei ab und
fallen irgendwann ohne Vorwarnung aus – und mit ihnen Datenbank, Dateien
und die Sicherungen, wenn sie auf derselben Karte liegen. Eine SSD hält das
aus und ist außerdem viel schneller. Das Installationsskript warnt vor dem
Start, wenn Datenbank oder Sicherungen auf der SD-Karte lägen; danach zeigen
es `sudo rentalars status` und der Selbsttest (Einstellungen → Selbsttest,
„SD-Karte“), und jede Aktualisierung erinnert daran.

**Weniger als 4 GB?** Das Skript warnt, macht aber weiter, und Rentalars
stellt sich darauf ein: Mit 2 GB laufen 3 statt 5 Arbeitsprozesse, und
MariaDB bekommt 512 MB statt 1 GB Zwischenspeicher; mit 1 GB sind es 2
Prozesse und 256 MB. Das reicht für eine Person, die gerade arbeitet;
PDF-Erzeugung, Import und Sicherung dauern länger, und mehrere Personen
gleichzeitig warten aufeinander. Ab 4 GB gilt dasselbe wie auf dem
Referenzsystem (NFA-042). Jede Aktualisierung richtet die Werte neu nach dem
Arbeitsspeicher aus; sie stehen in `/etc/systemd/system/rentalars.service`
(`--workers`) und in `/etc/mysql/mariadb.conf.d/62-rentalars-memory.cnf`.

**Nicht vorgesehen** sind ältere Modelle (Raspberry Pi 3, Zero 2 W): Das
Skript läuft dort mit dem Hinweis „nicht erprobt“, aber 1 GB oder weniger
Arbeitsspeicher sind für Rentalars zu knapp. Ein System mit **32 Bit** –
auch das 32-Bit-Raspberry-Pi-OS auf einem Pi 4 – lehnt das Skript ab, ebenso
Raspberry Pi OS auf Basis von Debian 12 („bookworm“, auch „Legacy“): Dessen
Python ist zu alt.

### Welches System?

Beide gehen; das Skript erkennt selbst, welches es vor sich hat.

| | Ubuntu Server für den Raspberry Pi | Raspberry Pi OS Lite (64-bit) |
|---|---|---|
| Version | 24.04 LTS oder 26.04 LTS | auf Basis von Debian 13 „trixie“ |
| Python | 3.12 bzw. 3.14 | 3.13 |
| NGINX | 1.24 bzw. 1.28 | 1.26 |
| MariaDB | 10.11 bzw. 11.8 | 11.8 |
| Sicherheitskorrekturen | fünf Jahre je LTS-Version (bis 2029 bzw. 2031) | solange Debian 13 sie bekommt (bis etwa 2028, mit Debian LTS bis 2030) |
| Passt, wenn … | du schon Server mit Ubuntu betreibst – alles ist wie dort | du Raspberry Pi OS kennst; die Werkzeuge des Pi (`raspi-config`, Aktualisierung der Firmware) sind dabei |

Die Pakete heißen auf beiden Systemen gleich, und Rentalars läuft mit allen
drei Python-Versionen. Die Python-Bibliotheken kommen wie auf dem Server von
PyPI; für den Pi (64-Bit-ARM, „arm64“) gibt es sie fertig – bis auf den
Anschluss an MariaDB (`mysqlclient`), den das Skript wie auf dem Server mit
`libmariadb-dev` auf dem Pi selbst baut. Schritt 4 der Installation dauert
deshalb etwas länger.

### Vorbereiten

1. Auf deinem Rechner den **Raspberry Pi Imager** installieren
   (raspberrypi.com/software).
2. Im Imager das Modell wählen, dann das System: **„Raspberry Pi OS Lite
   (64-bit)“** oder **„Ubuntu Server 24.04 LTS (64-bit)“** bzw. 26.04 (bei
   den anderen Systemen unter Ubuntu). Kein System mit Schreibtisch – der Pi
   arbeitet als Server.
3. Als Ziel die **SSD** wählen, per USB-Adapter an deinem Rechner – nicht
   die SD-Karte.
4. In den Einstellungen des Imagers: Name des Geräts (Hostname), Benutzer
   und Passwort, **SSH einschalten**, Zeitzone Europe/Berlin.
5. SSD an den Pi, **ohne SD-Karte** einschalten. Ein Raspberry Pi 5 und ein
   Pi 4 mit Firmware ab 2020 starten dann von der SSD. Startet ein älterer
   Pi 4 nicht: einmal Raspberry Pi OS von einer SD-Karte starten,
   `sudo rpi-eeprom-update -a`, neu starten, und in `sudo raspi-config`
   unter „Advanced Options“ → „Boot Order“ den Start von USB wählen.
6. Per SSH anmelden und das System auf den neuesten Stand bringen:

   ```sh
   sudo apt update && sudo apt full-upgrade
   sudo reboot
   ```

7. Im Router dem Pi eine **feste Adresse** geben. Name und Zertifikat wie
   beim Server (Abschnitt 1, „Name und Zertifikat“): Für Let's Encrypt
   leitet der Router die Ports 80 und 443 an den Pi weiter, sonst nimm den
   Weg über den DNS-Eintrag.
8. **Die Uhr prüfen.** Der Pi 4 hat keine Uhr mit Batterie und holt sich
   die Zeit beim Start aus dem Netz; der Pi 5 hält sie nur mit einer
   zusätzlichen Batterie. `timedatectl` muss „System clock synchronized:
   yes“ zeigen – sonst stimmen Zertifikat, Zwei-Faktor-Codes und Zeitpläne
   nicht.

### Installieren

Genau wie in den Abschnitten 2 und 3: Paket auf den Pi kopieren, entpacken,
`sudo ./deploy/install.sh`. Vor dem Start nennt das Skript zusätzlich das
Gerät:

```
    System:       Debian GNU/Linux 13 (trixie)
    Gerät:        Raspberry Pi 5 Model B Rev 1.0, 7,9 GB Arbeitsspeicher, arm64
```

Hat der Pi weniger als 4 GB, oder lägen Datenbank oder Sicherungen auf der
SD-Karte, steht direkt darunter eine Warnung mit „Achtung:“ – vor der Frage
„Installation starten?“. Bis dahin ist nichts verändert.

### Was danach anders ist

- **Firewall.** Ubuntu bringt `ufw` mit; auf Raspberry Pi OS erst
  `sudo apt install ufw`, dann weiter wie in Abschnitt 5.
- **Sicherheitsaktualisierungen.** Auf Raspberry Pi OS zuerst
  `sudo apt install unattended-upgrades`, dann wie in Abschnitt 7.
- **Sicherungen vom Gerät holen** ([sicherung.md](sicherung.md), „Die
  Sicherungen vom Server holen“) – auf einem Pi noch wichtiger als auf
  einem Server.
- **`sudo rentalars status`** zeigt zusätzlich das Gerät und was auf der
  SD-Karte liegt, der Selbsttest unter „Server“ das Gerät und unter
  „Speicherplatz“ einen Hinweis, wenn etwas auf der SD-Karte liegt.
- **Geschwindigkeit.** Die zugesagten Antwortzeiten (NFA-039) gelten für das
  Referenzsystem mit 4 Kernen, 8 GB und SSD. Ein Pi ist langsamer – wie viel,
  ist nicht gemessen. Probier es vor dem echten Betrieb aus: auf einer
  Testinstallation `sudo rentalars measure_performance --create-test-data`
  ([betrieb.md](betrieb.md), „Leistung“), danach den Pi neu aufsetzen.
- **Später von der SD-Karte auf eine SSD:** Sicherung schreiben, die SSD wie
  oben einrichten, Rentalars darauf installieren und die Sicherung
  einspielen – wie beim Umzug auf einen neuen Server
  ([sicherung.md](sicherung.md), „Umzug auf einen neuen Server“).
- **Aktualisieren** geht mit demselben Befehl wie auf dem Server
  ([aktualisierung.md](aktualisierung.md)).

### Was davon erprobt ist

Ehrlich gesagt: In der Umgebung, in der Rentalars gebaut wird, gibt es
keinen Raspberry Pi. **Ausprobiert** ist:

- Alle Python-Bibliotheken gibt es auf PyPI fertig für arm64, für Python
  3.12, 3.13 und 3.14 – bis auf `mysqlclient`, das auf jedem Linux gebaut
  wird; die Pakete dafür installiert das Skript.
- Wie das Skript System und Gerät erkennt, welche Pakete es wählt, wie es
  Arbeitsprozesse und Speicher bemisst und die SD-Karte erkennt – als
  automatischer Test mit nachgebildeten Systemen: Ubuntu 24.04 und 26.04
  auf Pi 4 und 5, Raspberry Pi OS auf Debian 12, 13 und 14, 32 Bit, ein
  Pi 3, andere Platinen, verschlüsselte Laufwerke.

**Nicht ausprobiert:** die Installation auf einem echten Raspberry Pi, weder
mit Ubuntu noch mit Raspberry Pi OS; die Pakete von Debian 13 – ihre Namen
und Versionen sind nachgeschlagen, nicht installiert; die Antwortzeiten auf
dem Pi. Bitte melde, wie es bei dir lief.

## Erprobung

Was ausprobiert wurde – und was nicht. Was zwischen den Prüfungen nicht
geändert wurde, wurde nicht jedes Mal wiederholt.

**Die beiden Testumgebungen**

| | Ubuntu 24.04 LTS | Ubuntu 26.04 LTS |
|---|---|---|
| Python | 3.12 (siehe unten) | 3.14.4 |
| NGINX | 1.24.0 | 1.28.3 |
| MariaDB | 10.11.14 | 11.8.6 |
| OpenSSL | 3.0 | 3.5.5 |
| `sudo` | das herkömmliche | sudo-rs 0.2.13 |
| Grundbefehle (`install`, `ln`, `date`, `mktemp` …) | GNU coreutils | rust-coreutils 0.8.0 |
| systemd (liest die Dienstdateien) | 255 | 259 |

Das Ubuntu 26.04 war ein vollständiges System aus den Paketen von Ubuntu,
betrieben in einer abgeschlossenen Umgebung auf derselben Maschine wie das
24.04. In beiden lief **kein systemd als Dienstverwalter**; siehe unten.
Auf der 24.04-Maschine war ein zusätzliches Python 3.13 voreingestellt; für
die Schlussprobe wurde das Skript dort mit dem Python 3.12 ausgeführt, das
Ubuntu 24.04 mitbringt.

**Zuletzt ausprobiert:**

- **Frische Installation** (Ubuntu 24.04, zweimal): 75 und 81 Sekunden;
  danach Ersteinrichtung, volles Mengengerüst und die Messung aus
  [betrieb.md](betrieb.md) ohne Befund.
- **Aktualisierung von der Vorversion**, Rückweg und erneute Aktualisierung auf
  beiden Ubuntu-Versionen ([aktualisierung.md](aktualisierung.md),
  „Erprobung“), mit Seiten im Browser über HTTPS, Abo-Link über NGINX,
  einem ICS-Link und einem CalDAV-Server (Radicale) in der Testumgebung.
- **Verschlüsselte Installation** (Ubuntu 26.04): eine Sicherung aus dem
  Browser geschrieben – verschlüsselt mit ihrem eigenen Schlüssel – und
  mit `sudo rentalars restore DATEI --key-file SCHLÜSSELDATEI` wieder
  eingespielt: Was nach der Sicherung angelegt war, war danach fort, alles
  andere da. Ein falscher Schlüssel wird abgewiesen. Die nächtliche
  Sicherung danach enthielt die Sicherung aus dem Browser nicht.

**Davor ausprobiert:**

- **Frische Installation** (Ubuntu 24.04, viermal): 66 bis 71 Sekunden; die
  vier Zeitpläne laufen, darunter der neue für Aufgaben im Hintergrund.
- **Aktualisierung von der Vorversion** auf beiden Systemen, Rückweg und erneute
  Aktualisierung (siehe [aktualisierung.md](aktualisierung.md)).
- **Auf dem Server, über HTTPS und NGINX** (Ubuntu 26.04): Rechnung mit
  XRechnung und Crew-Disposition erstellt – die PDF-Dateien entstehen mit
  den Schriften und Bibliotheken aus den Paketen von Ubuntu; Datenexport und
  Import im Hintergrund, jeweils als eigener Prozess des Dienstes; die API
  mit `ETag`, `X-RateLimit-…` und `Idempotency-Key` (dieselbe Anfrage zweimal
  ergab eine Ausführung und `Idempotent-Replayed: true`), ein Import über
  die API im Hintergrund (Antwort 202).
- **Im Browser über HTTPS** (Ubuntu 24.04, mit dem vollen Mengengerüst):
  Packliste, Dokumente und Preisübersicht eines Projekts; ein Import von
  Kunden mit Probelauf und Import im Hintergrund bis zum Bericht. Keine
  Fehlermeldung im Browser, keine Antwort mit Fehlerstatus.
- Antwortzeiten mit dem vollen Mengengerüst, samt den Seiten der Stufe 5
  (Ubuntu 24.04, siehe [betrieb.md](betrieb.md)).
- Die automatischen Tests: alle 1.461 mit SQLite und gegen MariaDB 10.11,
  mit Python 3.13; darunter die Prüfung aller Hauptseiten mit axe-core
  (WCAG 2.1 AA) im Browser.

**Ebenfalls ausprobiert:**

- **Frische Installation mit `--encrypt`** (Ubuntu 24.04 mit dem fertigen
  Paket, 26.04 mit einem Stand kurz davor): 74 Sekunden. MariaDB
  verschlüsselt alle 61 Tabellen; die erste Sicherung entsteht gleich bei
  der Installation, verschlüsselt (`.tar.gz.enc`); `rentalars status`,
  `rentalars encryption status` und der Selbsttest zeigen es so, wie es in
  [verschluesselung.md](verschluesselung.md) und [betrieb.md](betrieb.md)
  steht. Eine Sicherung ließ sich auf einem anderen Rechner mit dem
  Wiederherstellungsschlüssel und `openssl` allein entschlüsseln.
- **Vorhandener Datenbankserver:** `root` wird abgelehnt, bevor irgendetwas
  geschieht; ein Benutzer mit Rechten auf den ganzen Server ebenso – nur die
  Pakete von Ubuntu waren da schon installiert. Angenommen: ein Benutzer mit
  Rechten nur auf seine Datenbank, einmal mit TLS und geprüftem Zertifikat
  (24.04, Sicherungen verschlüsselt), einmal ohne TLS und ohne
  Verschlüsselung (26.04). Gegen MariaDB 10.11 außerdem abgelehnt: ein
  Benutzer, der Rechte auf den ganzen Server über eine Rolle bekommt, einer
  mit Rechten auf eine zweite Datenbank, einer, der nur lesen und einfügen
  darf (beim Probeanlegen von Tabellen), und eine Datenbank, in der schon
  ein Rentalars liegt.
- **`rentalars move-database`** vom vorhandenen Server auf MariaDB dieses
  Servers und zurück auf einen anderen vorhandenen, mit TLS; je 46 Tabellen
  verglichen, die bisherige Datenbank blieb unverändert.
- **`rentalars encryption enable`** auf einer Installation ohne
  Verschlüsselung – einmal frisch, einmal nach einer Aktualisierung
  (26.04): 61 Tabellen und 867 Zeilen vor und nach dem Verschlüsseln
  verglichen, drei vorhandene Sicherungen verschlüsselt, Rentalars lief
  danach weiter.
- **Aktualisierung** auf beiden Systemen, Rückweg, NGINX-Vorlage
  übernehmen (siehe [aktualisierung.md](aktualisierung.md)). Danach
  antwortete NGINX auf fremde Namen nicht mehr: Die bloße IP-Adresse auf
  Port 80 bekam keine Antwort, ein fremder Name auf Port 443 keinen
  TLS-Handschlag.
- Der Zeitplan für den Mailabruf läuft nach Installation und Aktualisierung
  und ist nach
  dem Rückweg wieder fort.
- Antwortzeiten mit dem vollen Mengengerüst
  und zehn Personen, die gleichzeitig Zeiten erfassen (Ubuntu 24.04, siehe
  [betrieb.md](betrieb.md)).
- Die automatischen Tests: alle 1.286 mit SQLite und gegen MariaDB 10.11,
  mit Python 3.13; darunter die Browsertests für die Seiten der Stufe 4 und
  für eine Mail mit Skript und Zählpixel (das Skript lief nicht, das Pixel
  wurde nicht geladen).

**Ausprobiert – auf beiden, mit demselben Paket:**

- Installation aus dem Paket mit `sudo ./deploy/install.sh`, selbst
  erstelltes Zertifikat, ohne Rückfragen: 31 Sekunden unter 24.04, 33 unter
  26.04 (die Pakete von Ubuntu waren schon da). Das Skript lief ohne Fehler
  und ohne Warnung durch; `nginx -t` fand nichts.
- **Der Einrichtungsschlüssel (NFA-064):** Die Seite der Ersteinrichtung
  ohne Schlüssel und mit einem falschen zeigte nur den Hinweis auf die
  einmalige Adresse; mit dem Schlüssel aus der Ausgabe des Skripts das
  Formular; nach der Einrichtung führte dieselbe Adresse zur Startseite.
  Dass der Schlüssel entsteht, bevor die Anwendung (Schritt 7) und NGINX
  (Schritt 9) starten, prüft zusätzlich ein automatischer Test am Skript.
- Rechte und Besitzer aller angelegten Dateien und Verzeichnisse:
  auf beiden Systemen gleich.
- Ersteinrichtung im Browser, mit und ohne Beispieldaten; Hochladen des
  Logos, Auslieferung nur an angemeldete Nutzer.
- **Alle Seiten der Stufe 3 im echten Browser, über HTTPS und NGINX**, am
  Schreibtisch und in 360 Pixel Breite: Personal, Funktionen,
  Verfügbarkeit, Meine Zeiten, Freigeben, Auswertung, Einsatz und Zugriff
  eines Projekts. Zeit erfasst über den Dialog, mit der Stoppuhr und mit
  Beginn und Ende; eine überschneidende Zeit wurde mit Hinweis abgelehnt.
  CSV und Stundenzettel (PDF) heruntergeladen. Keine Fehlermeldung im
  Browser, keine fehlgeschlagene Anfrage.
- Die Gestaltungsdatei wird mit Versionskennung in der Adresse ausgeliefert
  (`app.css?v=…`), sodass ein Browser nach einer Aktualisierung die neue
  lädt (NFA-065).
- Aktualisierung, Rückweg, Abbruch einer fehlerhaften
  Aktualisierung (siehe [aktualisierung.md](aktualisierung.md)); Sicherung
  und Wiederherstellung (siehe [sicherung.md](sicherung.md)).
- Antwortzeiten mit dem vollen Mengengerüst samt Personal und Zeiten, und
  zehn Personen, die gleichzeitig Zeiten erfassen (siehe
  [betrieb.md](betrieb.md)).
- Die automatischen Tests: auf 24.04 alle 1076 gegen MariaDB 10.11 und
  mit SQLite (dort ohne die vier, die MariaDB brauchen), dazu ohne die
  31 Browsertests mit Python 3.12 und 3.14; auf 26.04 die 1045 ohne Browser,
  mit Python 3.14 gegen MariaDB 11.8. Unter den Tests, die MariaDB brauchen,
  sind die, die zwei gleichzeitig ankommende Zeiteinträge gegeneinander
  antreten lassen.
- Die Dienstdateien und Zeitgeber hat das
  Prüfprogramm von systemd gelesen
  (`systemd-analyze verify`, Version 255 und 259): keine Beanstandung.

**Nur auf 26.04 ausprobiert:**

- Installation auf einem Minimalsystem, auf dem NGINX, MariaDB
  und die Werkzeuge zum Bauen noch fehlten (92 Sekunden einschließlich
  Herunterladen der Pakete), und der Zustand nach einem Wechsel von Ubuntu
  24.04 auf 26.04, nachgestellt (siehe [aktualisierung.md](aktualisierung.md)).

**Nicht ausprobiert**, weil die Testumgebung es nicht hergab:

- **Ein echtes Postfach.** Abruf und Versand von Mails sind gegen ein
  nachgebildetes IMAP-Postfach und einen abgefangenen SMTP-Versand getestet,
  nicht gegen einen wirklichen Mailserver. Bitte das Projektpostfach zuerst
  mit einem Testpostfach ausprobieren (E-Mail → Postfach, dann „Jetzt
  abrufen“; ein Fehler steht danach auf derselben Seite und im
  Selbsttest).
- **Die Seiten der Stufe 4 im Browser über HTTPS und NGINX** auf den
  beiden Testsystemen; im Browser geprüft wurden sie am Entwicklungsserver.

- **Die Installation auf einem wirklich frischen Server mit Stoppuhr**,
  von der Anmeldung per SSH bis zum angemeldeten Administrator. Die Zusage
  „unter 30 Minuten nach Anleitung“ (Abnahmeszenario 10) ist nach den
  Zeiten oben plausibel, aber nicht gemessen.
- **Die Zertifikate von Let's Encrypt** (Auswahl 1 und 2). Dafür braucht es
  einen Server mit öffentlichem Namen. Die Befehle folgen der Dokumentation
  von certbot; das Paket `certbot` gibt es in beiden Ubuntu-Versionen
  (2.9 und 4.0).
- **Der Start durch systemd.** Die Dienste wurden mit denselben
  Befehlszeilen von Hand gestartet, die in den mitgelieferten Dienstdateien
  stehen. systemd hat die Dateien gelesen und nichts beanstandet (siehe
  oben), aber noch keinen Dienst daraus gestartet – die Schutzeinstellungen
  der Dienstdatei sind damit nicht im Betrieb erprobt.
- **Der wirkliche Wechsel der Ubuntu-Version** mit `do-release-upgrade`.
  Nachgestellt ist nur, was er für Rentalars bedeutet.

Bitte melde, was bei deiner ersten Installation anders lief als hier
beschrieben.
