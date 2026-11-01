# Sicherung und Wiederherstellung

Rentalars sichert sich jede Nacht selbst. Was du dazutun musst, ist wenig,
aber wichtig: **die Sicherungen vom Server holen** und **das Zurückspielen
einmal üben**.

## Was gesichert wird

Jede Nacht um 2:30 Uhr entsteht eine Datei:

```
/var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz
```

oder, wenn die Sicherungen verschlüsselt werden (unten), dieselbe Datei
verschlüsselt:

```
/var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz.enc
```

Sie enthält alles, was Rentalars ausmacht:

| Inhalt | |
|---|---|
| `database.sql` (bei verschlüsselten Sicherungen `database.sql.enc`) | die gesamte Datenbank: Material, Produkte, Kunden, Projekte, Dokumente, Nutzer, Änderungsprotokoll |
| `media/` | gespeicherte Dateien: Firmenlogo, Projektdateien, Hallenpläne, Anhänge der Projektmails, die erstellten Dokumente (PDF und XRechnung), Bilder und Dateien an Material, Defektfotos, Prüfprotokolle, Nachweise der Qualifikationen, die verkleinerten Fotos und Videos aus dem Chat (`media/chat/<Projekt>/`), die Eingangsrechnungen (`media/incoming/<Jahr>/`) und die Original-PDFs übernommener Altrechnungen, Ergebnisse von Aufgaben im Hintergrund (bis zum Ablauf ihrer Frist) – **ohne** die Sicherungen aus dem Browser (`media/jobs/backups/`, unten) |
| `rentalars.conf` | die Konfigurationsdatei |
| `VERSION` | die Version von Rentalars, die gesichert hat |

Mit dieser einen Datei lassen sich **alle Daten** von Rentalars auf einem
frisch installierten Server zurückholen – Datenbank, gespeicherte Dateien
und Konfiguration. Ein **fertig laufender Server** ist damit noch nicht
zurück: Was zur Installation des Servers gehört und nicht zu den Daten,
steht nicht in der Sicherung. Die Liste dazu steht gleich unten
(„Was eine Wiederherstellung nicht zurückbringt“).

**Datenbank und Dateien passen zusammen** (NFA-015). Die
Sicherung läuft, während gearbeitet wird; Datenbank und Dateien können
deshalb nicht im selben Augenblick gelesen werden. Damit nach dem
Zurückspielen keine Datei fehlt, auf die die Datenbank verweist, löscht
Rentalars Dateien nicht sofort: Eine gelöschte Datei liegt noch **7 Tage**
unter `media/.deleted/<Datum>/` und wird dann von der nächtlichen Pflege
entfernt. Sie ist also noch in einer Sicherung, deren Datenbank sie
braucht. Datenschutz: Gelöschte Dateien (auch Fotos, Rechnungen, Nachweise)
bleiben damit bis zu 7 Tage auf dem Server und in den Sicherungen dieser
Tage; Sicherungen werden ohnehin 14 Tage aufbewahrt (unten).

**Der Datenbankauszug liegt nie unverschlüsselt auf der Platte**, wenn die
Sicherungen verschlüsselt werden: Er wird beim Schreiben
verschlüsselt (`database.sql.enc` in der Sicherung, die selbst noch einmal
verschlüsselt ist). Auch beim Zurückspielen und beim Umzug der Datenbank
(`move-database.sh`) wird er nur durchgereicht, nicht abgelegt.

### Was eine Wiederherstellung nicht zurückbringt

| Was | Warum | Was du tust |
|---|---|---|
| Zertifikate (`/etc/rentalars/tls`) und die NGINX-Site | gehören zum Server, nicht zu den Daten | beim neuen Server bei der Installation einrichten (`--tls …`, [installation.md](installation.md)); Adresse wie vorher |
| Geheimer Schlüssel (`secret_key`) | `rentalars.conf` wird beim Zurückspielen **nicht** ersetzt – der Server behält seinen | übernehmen, wenn Anmeldungen, Postfach-, CalDAV-, Lexware- und KI-Passwörter, Zwei-Faktor und Webhooks weiter gelten sollen (Umzug, Schritt 4) |
| Lokale KI (`/opt/rentalars/ai`, `ai-local.conf`) | Programm und Modelle sind groß und neu zu laden | `sudo rentalars ai install`; danach „Geschwindigkeit messen“ |
| Routendienst (`/opt/rentalars/routes`, `route-local.conf`) | aufbereitete Karte, neu zu laden | `sudo rentalars route install` |
| Hochgeladene, noch nicht gespeicherte Dateien (`/var/lib/rentalars/purchase-invoices`, `chat-videos`, `legacy-invoices`) | warten nur kurz | nach der Wiederherstellung erneut hochladen |
| Dienste des Betriebssystems (systemd-Zeitgeber, Firewall, DNS) | gehören zum Server | `sudo rentalars status` zeigt, was fehlt |
| Zugang zum Datenbankserver bei ausgelagerter Datenbank | `[database]` der Konfiguration gehört zum Server | nicht aus der alten Konfiguration übernehmen |

Am Ende der Wiederherstellung zeigt `sudo rentalars restore` diese Punkte
selbst an – für die lokale KI und den Routendienst nur dann, wenn sie auf
diesem Server fehlen.

**Nicht in der Sicherung ist die lokale KI**: Programm und
Modelle unter `/opt/rentalars/ai`, `/etc/rentalars/ai-local.conf` und
`ai-local.env`. Die Modelle sind groß und jederzeit neu zu laden. Was im
Browser unter Einstellungen → KI eingestellt ist, die Zusammenfassungen
und das Protokoll der KI-Aufrufe liegen in der Datenbank und sind
gesichert. Ebenso wenig der Routendienst: die aufbereitete
Karte unter `/opt/rentalars/routes` und `/etc/rentalars/route-local.conf`
– auf einem neuen Server mit `sudo rentalars route install` neu
einrichten. Ebenso wenig gesichert sind die Zertifikate unter
`/etc/rentalars/tls` und die NGINX-Site; die Sicherungen vor
einer Änderung der Adresse liegen unter `/etc/rentalars/address-backup/`.
Auch der Ordner `/var/lib/rentalars/purchase-invoices/` steckt
nicht in der Sicherung und muss es nicht: Dort warten Rechnungen, die für
„Kauf einpflegen“ hochgeladen, aber noch nicht gespeichert sind, höchstens
zwei Tage lang. Gespeichert hängt die Rechnung an den neuen Exemplaren
unter `media/` und ist damit gesichert
([betrieb.md](betrieb.md), „Hochgeladene Einkaufsrechnungen“). Ebenso
wenig der Ordner `/var/lib/rentalars/chat-videos/`: Dort
warten hochgeladene Videos, bis sie für den Chat verkleinert sind, samt den
Zwischendateien von ffmpeg. Die verkleinerte Fassung liegt danach unter
`media/chat/` und ist gesichert; ein Video, das zum Zeitpunkt der
Sicherung noch verkleinert wird, fehlt in ihr
([betrieb.md](betrieb.md), „Fotos und Videos im Chat“). Ebenso wenig der
Ordner `/var/lib/rentalars/legacy-invoices/`: Dort warten
PDFs, die für den Import von Altprojekten hochgeladen, aber noch nicht
übernommen sind, höchstens 14 Tage lang. Übernommen hängt das Original an
der historischen Rechnung unter `media/` und ist gesichert
([betrieb.md](betrieb.md), „Altprojekte importieren“). Die
**Eingangsrechnungen** dagegen liegen dauerhaft unter `media/incoming/` und
sind in jeder Sicherung – sie wachsen mit jeder Rechnung mit
([betrieb.md](betrieb.md), „Eingangsrechnungen und ihre Dateien“). Die
Einstellungen des Verzeichnisses (LDAP) stehen in der Datenbank; das
Passwort des Suchkontos ist mit dem `secret_key` der Konfigurationsdatei
verschlüsselt, die ebenfalls in der Sicherung ist.

Die erste Sicherung schreibt schon das
Installationsskript, gleich am Ende – so ist von Anfang an erwiesen, dass
das Sichern auf diesem Server klappt.

Die Sicherung läuft, während gearbeitet wird; niemand wird ausgesperrt. Sie
hält den Stand der Datenbank eines einzigen Augenblicks fest, und die Dateien
dazu sind noch da (oben, „Datenbank und Dateien passen zusammen“). Liegt die Datenbank auf einem
anderen Server (NFA-066), holt die Sicherung sie von dort und legt die Datei
trotzdem hier ab.

Die nächtliche Sicherung lässt den Ordner `media/jobs/backups/`
aus, in dem die Sicherungen aus dem Browser auf ihr Herunterladen warten:
Sonst steckte in jeder Sicherung die vorige, und sie würden immer größer.

## Verschlüsselte Sicherungen

Ist die Verschlüsselung eingeschaltet (bei der Installation oder mit
`sudo rentalars encryption enable`), schreibt Rentalars jede Sicherung
gleich verschlüsselt – eine unverschlüsselte Fassung liegt nicht einmal für
einen Augenblick auf der Platte. Für dich ändert sich nichts: `rentalars
restore` entschlüsselt selbst, mit dem Schlüssel des Servers. Ausnahme:
Eine Sicherung aus dem Browser hat ihren eigenen Schlüssel (nächster
Abschnitt).

Auf einem **anderen Server** – etwa nach einem Totalausfall – gibst du den
Wiederherstellungsschlüssel mit:

```sh
sudo rentalars restore rentalars-2026-10-11_023000.tar.gz.enc --key-file schluessel.txt
```

Und ganz ohne Rentalars, mit openssl:

```sh
openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -md sha256 -pass file:schluessel.txt \
    -in rentalars-2026-10-11_023000.tar.gz.enc -out rentalars-2026-10-11_023000.tar.gz
```

`schluessel.txt` enthält den Schlüssel genau so, wie er aufgeschrieben ist,
mit Bindestrichen, in einer Zeile. Mehr dazu, auch was ohne den Schlüssel
geschieht: [verschluesselung.md](verschluesselung.md).

**Verschlüsselte Sicherungen sind ohne den Schlüssel wertlos.** Wer sie vom
Server holt, sollte also auch wissen, wo der Schlüssel liegt.

**Aufbewahrung.** Tägliche Sicherungen bleiben 14 Tage und werden dann
gelöscht. Sicherungen mit `-keep` im Namen bleiben für immer: Sie entstehen
vor jeder Aktualisierung und vor jedem Zurückspielen. Lösche sie von Hand,
wenn du sie nicht mehr brauchst. Die Dauer änderst du in
`/etc/rentalars/rentalars.conf`:

```ini
[backup]
keep_days = 30
```

**Von Hand sichern** – vor einer größeren Änderung, einem Import, einem
Umzug:

```sh
sudo rentalars backup            # wird nach 14 Tagen aufgeräumt
sudo rentalars backup --keep     # bleibt
```

Der Befehl gibt den Namen der geschriebenen Datei aus.

## Sicherung aus dem Browser

Es geht auch ohne Zugang zum Server (ADM-010): Unter
**Einstellungen → Sicherung und Verschlüsselung** schreibt **„Sicherung
jetzt erstellen“** eine Sicherung zum Herunterladen, etwa vor einer
größeren Änderung. Auf derselben Seite steht der lesbare Export
aller Daten – keine Sicherung (unten, „Der lesbare Export ist keine
Sicherung“). Das dürfen alle, die in den Einstellungen löschen
dürfen, also die Administratoren; über die API geht es mit
`POST /api/v1/backups`.

- **Dieselbe Datei wie nachts.** Sie hat denselben Aufbau wie die Dateien
  von `sudo rentalars backup` – `database.sql`, `rentalars.conf`, `VERSION`,
  `media/` – und heißt etwa `rentalars-2026-10-13_101500-web.tar.gz`. Sie
  enthält also die personenbezogenen Daten aller, die Zugangsdaten der
  Datenbank und den geheimen Schlüssel; heb eine unverschlüsselte so sicher
  auf wie den Server selbst.
- **Im Hintergrund.** Die Sicherung entsteht als Aufgabe im Hintergrund
  ([betrieb.md](betrieb.md), „Aufgaben im Hintergrund“); unter „Deine
  Sicherungen aus dem Browser“ erscheint sie, sobald sie fertig ist. Bevor
  Rentalars sie anbietet, liest es sie einmal ganz zurück.
- **Nur für dich.** Herunterladen kann sie nur, wer sie erstellt hat – auch
  andere Administratoren nicht. Das Herunterladen steht im
  Zugriffsprotokoll.
- **Nicht für lange.** Nach der Frist für Ergebnisse von Aufgaben im
  Hintergrund (voreingestellt 7 Tage, [betrieb.md](betrieb.md),
  „Aufbewahrungsfristen“) löscht Rentalars sie. In der nächtlichen
  Sicherung steckt sie nicht (oben). Hol sie also herunter und bewahre sie
  selbst auf.

**Wenn die Sicherungen verschlüsselt werden** (`[backup] encrypt = true`),
ist auch diese verschlüsselt (`….tar.gz.enc`) – aber nicht mit dem
Wiederherstellungsschlüssel: Den darf nur root lesen, und Rentalars läuft
mit Absicht ohne diese Rechte. Jede Sicherung aus dem Browser bekommt
deshalb **einen eigenen Schlüssel**, in derselben Form wie der
Wiederherstellungsschlüssel. Er steht bei der fertigen Sicherung
(„Schlüssel dieser Sicherung – zum Kopieren anklicken“), nur für den, der
sie erstellt hat, und nur, solange es die Sicherung auf dem Server gibt.
**Bewahre ihn getrennt von der Datei auf**: Ohne ihn lässt sich die
Sicherung nicht öffnen, von niemandem, und der Wiederherstellungsschlüssel
des Servers passt nicht.

**Einspielen** – die Datei auf den Server kopieren, dann:

```sh
sudo rentalars restore rentalars-2026-10-13_101500-web.tar.gz
```

eine verschlüsselte mit ihrem Schlüssel in einer Datei (genau so, wie er
angezeigt wurde, in einer Zeile):

```sh
sudo rentalars restore rentalars-2026-10-13_101500-web.tar.gz.enc --key-file schluessel.txt
```

Ohne `--key-file` probiert der Befehl erst den Schlüssel des Servers und
fragt dann nach dem Schlüssel der Sicherung (drei Versuche). Auch
`sudo rentalars encryption decrypt-backup DATEI --key-file schluessel.txt`
und der `openssl`-Befehl oben öffnen sie mit diesem Schlüssel. Sonst gilt
alles, was unten unter „Wiederherstellen“ steht – auch, dass eine
Sicherung nur in dieselbe oder eine neuere Version von Rentalars passt.

## Die Sicherungen vom Server holen

**Eine Sicherung, die auf derselben Platte liegt wie die Daten, ist keine.**
Fällt die Platte aus, wird der Server gestohlen oder verschlüsselt ein
Angreifer alles, ist sie mit weg. Kopiere die Sicherungen deshalb regelmäßig
auf ein anderes Gerät an einem anderen Ort.

Die Dateien sind nur für `root` lesbar, denn sie enthalten alle Daten des
Betriebs samt Datenbankpasswort und geheimem Schlüssel. **Behandle jede
unverschlüsselte Kopie so vertraulich wie den Server selbst.** Sollen die
Sicherungen in fremde Hände – zu einem Speicheranbieter, auf eine Platte,
die das Büro verlässt –, schalte die Verschlüsselung ein.

Ein einfacher Weg: Ein anderer Rechner – der Bürorechner, ein NAS – holt
sich nachts die Dateien ab.

```sh
# auf dem anderen Rechner, z. B. täglich um 4 Uhr per cron:
rsync -a --ignore-existing sicherung@rentalars.example.de:/var/backups/rentalars/ /pfad/zu/sicherungen/rentalars/
```

Dafür braucht der abholende Nutzer auf dem Server Leserecht auf das
Verzeichnis. Am saubersten ist ein eigener Nutzer, der nichts anderes darf;
wie du das einrichtest, hängt von eurer Umgebung ab. Genauso gut sind ein
Sicherungsprogramm wie restic oder borg oder der Sicherungsdienst eures
Hosters – Hauptsache, das Verzeichnis `/var/backups/rentalars` landet
regelmäßig woanders.

Prüfe gelegentlich, ob auf dem anderen Gerät wirklich Dateien von gestern
liegen.

## Wiederherstellen

```sh
sudo rentalars restore /var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz
```

Der Befehl zeigt, was er vorhat, und fragt nach:

```
==> Wiederherstellung
    Sicherung:            /var/backups/rentalars/rentalars-2026-10-11_023000.tar.gz
    geschrieben mit:      Rentalars 1.0.0
    installiert ist:      Rentalars 1.0.0
    Datenbank:            rentalars wird vollständig ersetzt
    Dateien:              /var/lib/rentalars/media wird vollständig ersetzt
    Jetzt wiederherstellen? Alles seit der Sicherung Eingegebene geht verloren. [ja/NEIN]
```

Tippe `ja`. Dann

1. sichert er den jetzigen Stand (als `-keep`-Sicherung – falls du dich in
   der Datei geirrt hast, kommst du damit zurück),
2. hält Rentalars an,
3. ersetzt Datenbank und Dateien durch den Stand der Sicherung,
4. bringt die Datenbank auf den Stand des installierten Programms,
5. startet Rentalars wieder.

Das dauert Sekunden bis wenige Minuten, je nach Datenmenge. Die Sicherung
wird dafür neben den Daten ausgepackt (in `/var/lib/rentalars`); dort muss
so viel Platz frei sein, wie die Sicherung ausgepackt groß ist.

**Die Konfigurationsdatei wird nicht ersetzt.** Der Server behält seine
Adresse und seine Zugangsdaten. Die Datei steckt in der Sicherung, damit ein
neuer Server daraus eingerichtet werden kann (nächster Abschnitt).

**Die lokale KI bleibt, wie sie ist**: Das Zurückspielen
ändert nichts an `/opt/rentalars/ai` und am Dienst `rentalars-ai`. Steht in
der Sicherung „Zusammenfassungen mit lokaler KI“ auf an, auf diesem Server
ist sie aber nicht eingerichtet, sagt „Zusammenfassen“ das, bis du
`sudo rentalars ai install` ausführst.

### Versionen

- Sicherung **älter** als das installierte Programm: kein Problem. Schritt 4 bringt sie auf den neuen
  Stand.
- Sicherung **neuer** als das installierte Programm: geht nicht. Spiele erst
  die passende Version von Rentalars ein (`sudo rentalars update …`), dann
  die Sicherung.

### Wenn die jetzige Datenbank beschädigt ist

Dann schlägt Schritt 1 fehl, weil sich der jetzige Stand nicht mehr sichern
lässt. Überspringe ihn:

```sh
sudo rentalars restore DATEI.tar.gz --no-safety-backup
```

## Umzug auf einen neuen Server

Auch der Weg nach einem Totalausfall.

1. **Auf dem alten Server** (falls er noch läuft): `sudo rentalars backup --keep`
   und die Datei herunterkopieren. Sonst nimm die jüngste Sicherung, die du
   außerhalb des Servers hast.
2. **Auf dem neuen Server** Rentalars installieren wie in
   [installation.md](installation.md) – in derselben Version, mit der die
   Sicherung geschrieben wurde, oder einer neueren. Die Ersteinrichtung im
   Browser überspringst du.
3. Die Sicherung auf den neuen Server kopieren und einspielen:

   ```sh
   sudo rentalars restore rentalars-2026-10-11_023000-keep.tar.gz
   ```

   Eine verschlüsselte Sicherung braucht den Wiederherstellungsschlüssel des
   alten Servers: `--key-file schluessel.txt`. Soll auch der neue Server
   verschlüsseln, wähle das bei seiner Installation; er bekommt dabei einen
   eigenen Schlüssel.

4. **Den geheimen Schlüssel übernehmen**, wenn laufende Anmeldungen und schon
   verschickte Einladungslinks gültig bleiben sollen. Er steht in der
   Sicherung:

   ```sh
   tar -xzOf rentalars-2026-10-11_023000-keep.tar.gz rentalars.conf | grep secret_key
   ```

   (Bei einer verschlüsselten Sicherung zuerst entschlüsseln, siehe oben.)
   Der geheime Schlüssel ist auch nötig, damit das gespeicherte Passwort des
   Projektpostfachs, die Passwörter der CalDAV-Kalender, die
   Zwei-Faktor-Anmeldungen und die Geheimnisse der Webhooks
   und der API-Schlüssel von Lexware Office, auch die
   API-Schlüssel der KI-Schnittstellen weiter gelten. Ohne ihn trägst
   du das Passwort des Postfachs neu ein (Einstellungen → E-Mail), jede
   Person mit CalDAV-Kalender ihr Passwort unter „Meine Personaldaten“, wer
   die Zwei-Faktor-Anmeldung nutzt, richtet sie neu ein
   (`sudo rentalars reset_two_factor NAME`), jeder Webhook bekommt ein neues
   Geheimnis („Geheimnis neu erzeugen“, dann ins empfangende System
   übernehmen), der API-Schlüssel von Lexware Office wird unter
   Einstellungen → Buchhaltung neu eingetragen und der einer
   KI-Schnittstelle unter Einstellungen → KI.

   Trage die Zeile in `/etc/rentalars/rentalars.conf` des neuen Servers ein
   (Abschnitt `[rentalars]`) und starte neu: `sudo systemctl restart rentalars`.
   Ohne diesen Schritt müssen sich alle neu anmelden. Auch die Angaben
   zum E-Mail-Versand (`[email]`) kannst du von dort übernehmen. **Nicht**
   übernehmen: den Abschnitt `[database]` – der neue Server hat sein eigenes
   Datenbankpasswort – und `encrypt` in `[backup]`, das zur Installation des
   neuen Servers gehört.
5. Den DNS-Eintrag auf den neuen Server zeigen lassen.
6. **Die lokale KI neu einrichten**, wenn ihr sie auf dem alten Server
   hattet: `sudo rentalars ai install`. Sie steckt nicht in
   der Sicherung; die Einstellungen im Browser kommen mit der Datenbank
   zurück ([betrieb.md](betrieb.md), „KI“). Der Befehl wählt das
   Modell nach Speicher, Kernen und Prozessor des neuen Servers; die
   gemessene Geschwindigkeit in der Datenbank ist noch die des alten –
   danach unter Einstellungen → KI „Geschwindigkeit messen“, damit die
   Schätzung vor einer Zusammenfassung stimmt.

## Der lesbare Export ist keine Sicherung

Es gibt den vollständigen Datenexport (IMP-006): alle Tabellen
als JSON und CSV und alle Dateien in einer ZIP-Datei. Er steht
im Browser auf derselben Seite wie die Sicherung, unter **Einstellungen →
Sicherung → „Lesbarer Export aller Daten“**, auf dem Server mit
`sudo rentalars export_data` ([betrieb.md](betrieb.md), „Vollständiger
Datenexport“). Die Seite sagt, worin sich beide unterscheiden:

| | Sicherung | Lesbarer Export aller Daten |
|---|---|---|
| wozu | Rentalars **wiederherstellen** – nach einem Ausfall, auf einem neuen Server | **lesen** – in anderen Programmen, für das eigene Archiv |
| was | die ganze Datenbank (`database.sql`) mit allen Geheimnissen, `rentalars.conf`, `VERSION`, alle gespeicherten Dateien unter `media/` | jede Tabelle als JSON und CSV, alle gespeicherten Dateien unter `dateien/`, `LIESMICH.txt` |
| Geheimnisse | alle: Prüfwerte der Passwörter, Schlüssel der Zwei-Faktor-Anmeldung, Passwörter der Postfächer, geheimer Schlüssel, Datenbankpasswort | keine – Passwörter, Schlüssel, Token und die Webhooks fehlen |
| IDs | wie in der Datenbank | die internen IDs, auch in den Verweisen der CSV-Dateien |
| verschlüsselt | ja, wenn die Verschlüsselung eingeschaltet ist (oben) | nie |
| zurückspielen | `sudo rentalars restore DATEI` – als Ganzes, an die Stelle des jetzigen Stands | nicht möglich |
| wann | jede Nacht von selbst, vor jeder Aktualisierung, auf Knopfdruck | nur auf Knopfdruck |

Ein **Export im Importformat** (IMP-017) ist noch etwas
Drittes: je Import – Material, Produkte, Kunden, Personal – eine CSV-Datei
im Klartext, ohne interne IDs, die sich wieder importieren lässt
(Einstellungen → Import und Export; [import.md](import.md), „Export im
Importformat“).

Der lesbare Export ist also **nicht dafür da, Rentalars
wiederherzustellen**:

- `rentalars restore` nimmt nur Sicherungen; einen Export in eine
  laufende Installation mit eigenen Daten zurückzuspielen, geht nicht. Die
  `LIESMICH.txt` im Archiv beschreibt zwar, wie sich die JSON-Dateien in
  ein **frisch installiertes** Rentalars derselben Version laden lassen
  (im ausgepackten Ordner `sudo rentalars loaddata json/*.json`, danach
  die Dateien aus `dateien/` nach `/var/lib/rentalars/media/`; der Ordner
  muss für das Dienstkonto lesbar sein; erprobt am Export der
  Beispieldaten). Das ergibt aber keine wiederhergestellte Installation,
  sondern einen Neuanfang mit den Daten:
- Ihm fehlt mit Absicht, was eine Wiederherstellung braucht: die Prüfwerte
  der Passwörter und der API-Token, die Geheimnisse der
  Zwei-Faktor-Anmeldung, die Passwörter des Postfachs, der
  API-Schlüssel von Lexware Office und die Webhooks ganz, die
  Schlüssel der KI-Schnittstellen, die Konfigurationsdatei mit dem
  geheimen Schlüssel. Nach einem Laden setzt jeder ein neues Passwort, das
  Postfach und die Schlüssel werden neu eingetragen, die Webhooks neu
  angelegt.
- Er entsteht nur auf Knopfdruck, nicht jede Nacht. Die Datei, die der
  Browser zum Herunterladen anbietet, löscht Rentalars nach der Frist für
  Ergebnisse von Aufgaben im Hintergrund (voreingestellt 7 Tage).

Für den Ernstfall bleibt die Sicherung, wie oben beschrieben. Ein Export
enthält wie eine Sicherung die personenbezogenen Daten
aller Kunden, Personen und Nutzer – aber unverschlüsselt, auch wenn die
Sicherungen verschlüsselt werden. Gib ihn nur weiter, wie es der
Datenschutz erlaubt, und lösche ihn, wenn er nicht mehr gebraucht wird.

## Die Wiederherstellung üben

Eine Sicherung, deren Zurückspielen nie versucht wurde, ist eine Hoffnung.
Übe es einmal, am besten gleich nach der Installation und danach etwa
einmal im Jahr:

1. Richte irgendwo einen zweiten, kleinen Server ein (eine virtuelle
   Maschine genügt) und installiere Rentalars mit selbst erstelltem
   Zertifikat: `sudo ./deploy/install.sh --domain test.example.de --tls selfsigned`
2. Spiele dort eine Sicherung des echten Servers ein.
3. Melde dich an und sieh nach: Sind die Projekte von gestern da? Stimmt
   die Materialliste? Lässt sich eine Packliste als PDF öffnen?

Wenn ja, weißt du, dass eure Sicherungen taugen – und wie lange ihr im
Ernstfall braucht.

## Wenn die Sicherung nicht läuft

`sudo rentalars status` zeigt die jüngste Sicherung. Ist sie älter als einen
Tag:

```sh
sudo systemctl status rentalars-backup.timer     # läuft der Zeitgeber?
sudo journalctl -u rentalars-backup -n 30        # was sagt der letzte Lauf?
sudo rentalars backup                            # von Hand; zeigt die Fehlermeldung
```

Häufigste Ursache: die Platte ist voll („Auf … sind nur … MB frei“). Eine
Sicherung, die nicht vollständig geschrieben werden konnte, legt Rentalars
gar nicht erst ab – es liegen nie halbe Dateien im Verzeichnis.

**Rentalars meldet sich selbst.** Jede Nacht um 4:15 Uhr – nach der
Sicherung um 2:30 Uhr – prüft es, ob in dieser Nacht eine Sicherung
entstanden ist (die jüngste darf höchstens 25 Stunden alt sein), und
benachrichtigt sonst die Administratoren, in der Anwendung und per E-Mail
(NFA-018). Ebenso, wenn der Platz für Sicherungen knapp wird. Dasselbe zeigt
jederzeit der Selbsttest (Einstellungen → Selbsttest); wann die letzte
nächtliche Sicherung entstand und ob sie verschlüsselt war, steht auch unter
Einstellungen → Sicherung und Verschlüsselung.

## Erprobung

Ausprobiert wurde die **Sicherung aus dem Browser** – auf dem
Entwicklungsrechner, nicht in den beiden Testumgebungen: Die Datei besteht
die Prüfungen und das Auspacken von `restore.sh`; eine verschlüsselte lässt
sich mit den Schritten von `restore.sh` öffnen, auch mit einem Schlüssel in
Großbuchstaben und mit Leerzeichen, und mit dem `openssl`-Befehl oben; ein
falscher Schlüssel scheitert. Gegen MariaDB 10.11, mit einem Benutzer, der
nur Rechte auf seine Datenbank hat, ließ sich die Datenbank sichern und in
eine leere Datenbank so laden, wie `restore.sh` es tut. In der
Testumgebung mit Ubuntu 26.04 und verschlüsselter Installation dann von
Anfang bis Ende: Sicherung aus dem Browser geschrieben (verschlüsselt mit
ihrem eigenen Schlüssel), mit `sudo rentalars restore DATEI --key-file
SCHLÜSSELDATEI` eingespielt – was nach der Sicherung angelegt war, war fort,
alles andere da –, ein falscher Schlüssel abgewiesen, und die nächtliche
Sicherung danach ohne den Ordner der Browser-Sicherungen. Noch nicht
ausprobiert: die Sicherung unter den Schutzeinstellungen von systemd (die
Testumgebung hat kein systemd), das Herunterladen über NGINX, das
Einspielen einer unverschlüsselten Browser-Sicherung und ein eingetippter
Schlüssel.

In den beiden Testumgebungen aus
[installation.md](installation.md) ausprobiert:

- **Verschlüsselte Sicherungen:** Die erste Sicherung entsteht bei der
  Installation, mit `--encrypt` verschlüsselt. Eine solche Sicherung
  zurückgespielt auf derselben Installation (Ubuntu 26.04, Datenbank
  verschlüsselt) und – mit `--key-file` und dem Schlüssel des anderen
  Servers – auf einer Installation mit vorhandenem Datenbankserver (Ubuntu
  24.04): beide Male der Stand der Sicherung wieder da. Auf einem dritten
  Rechner ließ sich eine Sicherung mit dem Wiederherstellungsschlüssel und
  dem `openssl`-Befehl oben allein entschlüsseln.
- `rentalars encryption enable` verschlüsselt die vorhandenen Sicherungen
  im Ordner und prüft jede, bevor die unverschlüsselte gelöscht wird; der
  Selbsttest zeigt danach „Verschlüsselt: ja“.

Ausprobiert in den beiden Testumgebungen – Ubuntu 24.04 mit MariaDB 10.11 und Ubuntu 26.04
mit MariaDB 11.8:

- Sicherung im laufenden Betrieb; Inhalt der Datei geprüft (Datenbank,
  Dateien, Konfiguration, Version).
- Daten verändert, Sicherung zurückgespielt: Der Stand der Sicherung war
  wieder da, einschließlich des hochgeladenen Logos; die Sicherung des
  Zwischenstands lag daneben. Mit dem vollen Mengengerüst (20.000
  Exemplare, 1.000 Projekte) war die Sicherung 0,5 MB groß,
  und das Zurückspielen dauerte 5 bis 8 Sekunden. Mit
  zusätzlich 100 Personen, 3.020 Personalpositionen und 20.000
  Zeiteinträgen (Ubuntu 26.04): Sicherung in 1 Sekunde, 0,9 MB;
  Zurückspielen in 5 Sekunden, alle Personen und Zeiten wieder im Stand
  der Sicherung.
- Zurückspielen als Teil von `rentalars rollback` und beim selbsttätigen
  Rückweg einer fehlgeschlagenen Aktualisierung (siehe [aktualisierung.md](aktualisierung.md)).
- **Umzug von Ubuntu 24.04 auf Ubuntu 26.04:** Eine Sicherung, geschrieben
  unter Ubuntu 24.04 mit MariaDB 10.11, in eine frische Installation unter
  Ubuntu 26.04 mit MariaDB 11.8 eingespielt (Schritte 2 und 3 von „Umzug
  auf einen neuen Server“). Alle Daten waren da – 20.115 Exemplare,
  1.004 Projekte –, die Prüfung der Tabellen durch MariaDB fand nichts, die
  Seiten öffneten sich.

Nicht ausprobiert: Schritt 4 des Umzugs, das Übernehmen des geheimen
Schlüssels, und der Wechsel des DNS-Eintrags.
