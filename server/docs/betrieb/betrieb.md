# Betrieb

Was im Alltag auf dem Server zu tun ist – das meiste erledigt sich von
selbst –, wo die Einstellungen sind und wo du nachsiehst, wenn etwas hakt.

Alle Befehle laufen über das eine Kommando `rentalars`:

| Befehl | Zweck |
|---|---|
| `sudo rentalars status` | Läuft alles? Letzte Sicherung, freier Platz |
| `sudo rentalars backup` | Jetzt eine Sicherung schreiben ([sicherung.md](sicherung.md)) |
| `sudo rentalars restore DATEI` | Eine Sicherung zurückspielen; eine verschlüsselte aus dem Browser mit `--key-file SCHLÜSSELDATEI` ([sicherung.md](sicherung.md)) |
| `sudo rentalars update PAKET` | Neue Version einspielen ([aktualisierung.md](aktualisierung.md)) |
| `sudo rentalars rollback` | Zurück zur Version vor der letzten Aktualisierung |
| `sudo rentalars import_material DATEI` | Materialliste übernehmen ([import.md](import.md)) |
| `sudo rentalars import_data ART DATEI` | Produkte, Kunden oder Personal aus einer Datei übernehmen; `ART` ist `products`, `customers`, `people` (oder `material`). Ohne `--commit` nur ein Probelauf; dazu `--map FELD=SPALTE` und `--sheet NAME` ([import.md](import.md)) |
| `sudo rentalars export_data ZIEL.zip` | Alle Daten und Dateien in eine ZIP-Datei schreiben – der „Lesbare Export aller Daten“ (unten, „Vollständiger Datenexport“) |
| `sudo rentalars run_jobs` | Wartende Aufgaben im Hintergrund jetzt ausführen, danach die Kalender abgleichen, fällige Webhooks zustellen, über fällige Wiedervorlagen benachrichtigen und wartende Automationen ausführen (unten, „Aufgaben im Hintergrund“) |
| `sudo rentalars prepare_setup` | Neue Adresse für die Ersteinrichtung |
| `sudo rentalars selfcheck` | Selbstprüfung der Installation (unten, „Selbstprüfung“) |
| `sudo rentalars gateway connect\|status\|pair\|devices\|revoke\|disconnect` | Die Apps über das Rentalars Gateway aus dem Internet erreichbar machen ([gateway.md](gateway.md)) |
| `sudo rentalars encryption status` | Was ist verschlüsselt? Auch `enable`, `show-key`, `decrypt-backup` ([verschluesselung.md](verschluesselung.md)) |
| `sudo rentalars move-database …` | Die Daten in eine andere Datenbank umziehen (unten) |
| `sudo rentalars nginx-site` | Die NGINX-Konfiguration aus der Vorlage der installierten Version neu schreiben (unten, „Die NGINX-Konfiguration“) |
| `sudo rentalars address apply TOKEN` | Eine neue Adresse samt Zertifikat übernehmen, wie sie in den Einstellungen vorbereitet ist; mit `--dry-run` nur den Plan zeigen (unten, „Serveradresse und Zertifikat ändern“) |
| `sudo rentalars ai install` | Die lokale KI einrichten; auch `status`, `register`, `remove` (unten, „KI“) |
| `sudo rentalars route install` | Den Routendienst für Kilometervorschläge einrichten – freiwillig; auch `update`, `register`, `remove`, `status` (unten, „Routendienst“) |
| `sudo rentalars fetch_mail --now` | Die Postfächer der Korrespondenz jetzt abrufen, eine Zeile je Postfach (unten, „Postfächer“) |
| `sudo rentalars sync_calendars` | Die Kalender der Personen jetzt lesen und schreiben, was fällig ist; `--person ID` für eine Person, ob fällig oder nicht (unten, „Kalender der Personen“) |
| `sudo rentalars ldap_sync` | Die Konten mit dem Verzeichnis (LDAP) vergleichen: ohne Zusatz nur ein Probelauf, `--apply` schreibt, `--force` übergeht die Schutzgrenze (unten, „Anmeldung mit dem Verzeichnis (LDAP)“) |
| `sudo rentalars ai_summaries` | Die automatischen KI-Zusammenfassungen jetzt laufen lassen; `--dry-run` zeigt nur, `--project N`, `--limit N`, `--only-in-window` (unten, „Automatische KI-Zusammenfassungen“) |
| `sudo rentalars reset_two_factor NAME` | Zwei-Faktor-Anmeldung eines Nutzers abschalten, der Telefon und Codes verloren hat |
| `sudo rentalars measure_performance` | Antwortzeiten messen, auf einer Testinstallation; mit `--create-test-data` legt er vorher das Mengengerüst an (unten, „Leistung“) |
| `sudo rentalars uninstall` | Rentalars vom Server entfernen: `--dry-run` zeigt nur, `--keep-data` erhält die Daten, `--purge` löscht nach ausdrücklicher Bestätigung auch Datenbank, Backups und Konfiguration (unten, „Rentalars entfernen“) |
| `sudo rentalars help` | Alle weiteren Befehle |

## Läuft alles?

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
    letzte Sicherung             /var/backups/rentalars/rentalars-2026-10-12_023000.tar.gz.enc
    Verschlüsselung              Datenbank und Sicherungen verschlüsselt (rentalars encryption status)
    freier Speicher (Daten)      31G
```

Mit einem vorhandenen Datenbankserver steht statt `mariadb` eine Zeile, ob
er erreichbar ist. Auf einem Raspberry Pi kommen zwei Zeilen
dazu: **„Gerät“** mit Modell und Arbeitsspeicher und **„auf der
SD-Karte“** – was von Rentalars dort liegt (Datenbank, Datenordner,
Sicherungen) mit dem Rat „eine SSD wäre sicherer“, oder „nichts von
Rentalars“ ([installation.md](installation.md), „Raspberry Pi“). Ist die
lokale KI eingerichtet (unten „KI“), steht auch
`rentalars-ai` in der Liste.

Der Befehl und alle Skripte auf dem Server sprechen Deutsch,
wenn die Spracheinstellung des Servers mit `de` beginnt (`LANG`,
`LC_MESSAGES` oder `LC_ALL`), sonst Englisch – auch bei `C.UTF-8`, wie es
auf vielen Servern eingestellt ist. `RENTALARS_LANG=de` oder
`RENTALARS_LANG=en` entscheidet ausdrücklich, etwa
`sudo RENTALARS_LANG=de rentalars status`.

Steht irgendwo nicht `active`, hilft der Abschnitt „Wenn etwas hakt“ weiter
unten. Wirf ab und zu einen Blick auf die letzte Sicherung: Sie sollte von
heute Nacht sein.

Nach einem Neustart des Servers starten alle Dienste von selbst.

## Was von selbst geschieht

| Wann | Was |
|---|---|
| jede Nacht um 2:30 Uhr | Sicherung von Datenbank und Dateien; Sicherungen, die älter als 14 Tage sind, werden gelöscht |
| jede Nacht um 4:15 Uhr | Aufräumen: abgelaufene Anmeldungen und alte Einträge der Anmeldeversuche; nach Ablauf ihrer Aufbewahrungsfrist (unten, „Aufbewahrungsfristen“) Einträge des Sicherheitsprotokolls, des Änderungsprotokolls, des Zugriffsprotokolls und des Mail-Protokolls, Benachrichtigungen, Ergebnisse von Aufgaben im Hintergrund samt ihren Dateien (auch Sicherungen aus dem Browser) und Projektmails; Zustellungen von Webhooks nach 30 Tagen; Ausführungen von Automationen nach einem Jahr und gemerkte Kartenpositionen von Anschriften, die kein Datensatz mehr nennt; Dateien abgebrochener Importe nach zwei Tagen; Rechnungen, die für „Kauf einpflegen“ hochgeladen, aber nach zwei Tagen nicht gespeichert wurden (`/var/lib/rentalars/purchase-invoices/`, unten „Hochgeladene Einkaufsrechnungen“); Videos für den Chat, die nach zwei Tagen noch in `/var/lib/rentalars/chat-videos/` liegen, ohne dass ein Video darauf wartet – etwa nach einem Absturz (unten „Fotos und Videos im Chat“); die Zähler der API-Aufrufe nach einer Stunde und gespeicherte Antworten wiederholter API-Aufrufe nach einem Tag. Befristete Konten, deren Frist abgelaufen ist, werden deaktiviert (sie können sich schon vorher nicht mehr anmelden). Wenn „Konten jede Nacht abgleichen“ eingeschaltet ist, der Abgleich der Konten mit dem Verzeichnis (unten, „Anmeldung mit dem Verzeichnis (LDAP)“); auch das Zwischenlager der Altprojekt-PDFs verwirft sich nach 14 Tagen von selbst, aber beim Hochladen und Öffnen der Seite, nicht hier (unten, „Altprojekte importieren“). Das GoBD-Archiv: neue Belege eintragen und einen Teil der Dateien gegen ihre Prüfsummen prüfen (ein Befund macht den Selbsttest rot; Einstellungen → Buchhaltung). Dann die Prüfungen, die jemandem etwas melden: Produkte unter ihrem Mindestbestand und fällig gewordene Prüfungen von Material (an das Lager), Qualifikationen, die in den nächsten 60 Tagen ablaufen oder abgelaufen sind (an die Personaldisposition und die Person), und Probleme des Selbsttests (an die Administratoren). Mindestbestände, Prüfungen und Qualifikationen werden je Fall nur einmal gemeldet. Fehlbestände prüft der Minuten-Zeitgeber (unten). |
| jede Minute | Abruf der Postfächer der Korrespondenz, eines nach dem anderen – jedes, sobald seit seinem letzten Abruf der eingestellte Abstand (Voreinstellung zwei Minuten) um ist und es eingeschaltet ist (unten, „Postfächer“); dabei werden auch die Antworten der Crew auf Einsatzanfragen eingetragen |
| jede Minute | Aufgaben im Hintergrund, die noch warten oder durch einen Neustart unterbrochen wurden, werden ausgeführt (unten, „Aufgaben im Hintergrund“) |
| jede Minute, mit demselben Zeitgeber | Kalender der Personen: verknüpfte Kalender werden alle 30 Minuten gelesen; Einsätze werden binnen einer Minute nach einer Änderung in CalDAV-Kalender geschrieben und sonst alle 30 Minuten abgeglichen (unten, „Kalender der Personen“) |
| jede Minute, mit demselben Zeitgeber | Webhooks: fällige Zustellungen gehen an die empfangenden Systeme, fehlgeschlagene werden wiederholt (unten, „Webhooks“) |
| jede Minute, mit demselben Zeitgeber | Wiedervorlagen: Ist der Tag einer Wiedervorlage gekommen, bekommt die Person, für die sie ist, ab 6 Uhr Ortszeit einmal eine Benachrichtigung – in Rentalars und, wie sie es eingestellt hat, per Mail; war der Server zu der Zeit aus, sofort beim nächsten Lauf. Ist die Person deaktiviert, geht sie an die Projektleitung. Eine fällige Wiedervorlage löst auch Automationen mit diesem Auslöser aus |
| jede Minute, mit demselben Zeitgeber | Automationen: Ausführungen, die noch warten – etwa weil Rentalars gerade neu startete –, werden nachgeholt (unten, „Automationen“) |
| jede Minute, mit demselben Zeitgeber | Fehlbestände: zu Uhrzeit und Rhythmus von Einstellungen → Benachrichtigungen (voreingestellt jeden Tag um 4:15 Uhr, vier Wochen voraus) bekommt die Projektleitung neue Fehlbestände gemeldet – nur, wer das Sonderrecht „Verfügbarkeit von Material sehen“ hat; voreingestellt außerdem eine Erinnerung je Projekt an die schon gemeldeten („Weiterhin Fehlbestände in …“); war der Server aus, wird die Prüfung einmal nachgeholt. Eine Minute ohne fällige Prüfung kostet eine Datenbankabfrage |
| jede Minute, mit demselben Zeitgeber | Zeiten zur Freigabe: zur Uhrzeit von Einstellungen → Benachrichtigungen, Kasten „Zeiten zur Freigabe“ (voreingestellt eingeschaltet, täglich um 8:00 Uhr, erste Erinnerung einen Tag nach dem Einreichen, dann jeden Tag), wird jeder, der Zeiten freigeben darf, an die eingereichten Zeiten und Spesen erinnert, die er freigeben darf – nicht an eigene; war der Server aus, wird die Prüfung einmal nachgeholt |
| jede Minute, mit demselben Zeitgeber | Automatische KI-Zusammenfassungen: **nur wenn ein Administrator sie eingeschaltet hat** – in der Nacht (voreingestellt 1:00 bis 5:00 Uhr) startet der Zeitgeber einmal die Aufgabe `ai_auto_summaries`; sonst kostet eine Minute eine Datenbankabfrage (unten, „Automatische KI-Zusammenfassungen“) |
| etwa eine Minute nach jedem Start des Servers | Lokale KI: `rentalars-ai-refresh.timer` übernimmt die Einstellungen der installierten Version (unten, „KI“); ohne lokale KI geschieht nichts |
| zweimal täglich (certbot) | Erneuerung des Zertifikats von Let's Encrypt, sobald es fällig ist |

War der Server zur vorgesehenen Zeit aus, wird die Aufgabe beim nächsten
Start nachgeholt. Einen eigenen Dienst für solche Aufgaben gibt es nicht; das
übernehmen Zeitgeber des Betriebssystems (`systemctl list-timers 'rentalars*'`).

**Mehr Systemmails.** Drei neue Arten von Benachrichtigungen
gehen voreingestellt auch per E-Mail hinaus: **„Änderung meines
Einsatzes“** (eine Person wurde fest eingeplant, ihr Einsatz geändert oder
sie wurde ausgeplant – je Person und Aktion eine Nachricht), **„Meine
Zeiten freigegeben, korrigiert oder zurückgegeben“** und **„Zeiten warten
auf meine Freigabe“** (die Erinnerung oben). Jede Person kann sie unter
Mein Konto → Benachrichtigungen abschalten oder auf „In Rentalars“
beschränken; die Erinnerung an Freigaben schaltet ein Administrator unter
Einstellungen → Benachrichtigungen für alle ab. Ohne Mailserver (unten,
„Ohne Mailserver“) bleiben sie in Rentalars.

**Mehr Erinnerungen** (VFG-036, DOK-015). Zwei Einstellungen der Firma unter
Einstellungen → Benachrichtigungen sind voreingestellt an:
**„bekannte Fehlbestände bei jeder Prüfung erneut melden“** –
jede Prüfung der Fehlbestände (voreingestellt 4:15 Uhr) erinnert je
Projekt einmal an alle schon gemeldeten, neue oder gewachsene kommen weiter
einzeln – und **„auch Servicefälle“** – die Erinnerung an noch zu
schreibende Rechnungen (voreingestellt 9:00 Uhr) gilt auch für erledigte
Servicefälle mit Zeiten oder Spesen, und zwar für die, die nach dem
Einschalten erledigt wurden: Der Zeitpunkt wird gemerkt
(`invoice_cases_since`), früher erledigte Fälle stehen nur in den Listen.
Meldungen über Fehlbestände kommen voreingestellt auch per E-Mail. Wer das nicht
will, schaltet die beiden dort aus; jede
Person kann außerdem jede Art unter Mein Konto → Benachrichtigungen für
sich abstellen – ausnahmslos jede.

## Aufgaben im Hintergrund

Was länger dauert als ein Seitenaufruf – ein Import und sein Probelauf,
mehr als 240 Etiketten auf einmal, der vollständige Datenexport, eine
Sicherung aus dem Browser, die Übergabe einer Rechnung an
Lexware Office (Art `lexware`), die Zusammenfassung der
Korrespondenz und der Antwortentwurf der KI (Arten `ai_summary` und
`ai_draft`, unten „KI“), das Lesen einer Rechnung durch die KI
in „Kauf einpflegen“ (Art `ai_invoice`), das Verkleinern eines
Videos für den Chat (Art `chat_video`, unten „Fotos und Videos im Chat“),
 das Lesen einer Eingangsrechnung durch die KI (Art
`ai_incoming_invoice`), das Lesen alter Rechnungen beim Import von
Altprojekten (Art `legacy_invoices`) und der nächtliche Lauf der
automatischen KI-Zusammenfassungen (Art `ai_auto_summaries`, ohne Nutzer, unten
„Automatische KI-Zusammenfassungen“) –, läuft als Aufgabe im Hintergrund
(NFA-041).
Rentalars startet dafür sofort einen eigenen Prozess
(`manage.py run_jobs --job N`); die Seite zeigt, wie weit er ist, und man
kann währenddessen weiterarbeiten. Wer die Aufgabe gestartet
hat, bekommt eine Benachrichtigung, wenn sie fertig oder fehlgeschlagen ist,
und findet sie unter **Mein Konto → Aufgaben im Hintergrund**, samt dem
Ergebnis zum Herunterladen. **Nur wer eine Aufgabe gestartet hat, sieht sie
und ihr Ergebnis** – auch Administratoren nicht die anderer; ein
Datenexport enthält schließlich die Daten aller.

Dazu gibt es einen eigenen Zeitgeber, `rentalars-jobs.timer`, der jede
Minute `manage.py run_jobs` startet (Dienst `rentalars-jobs.service`, mit
niedriger Priorität und bis zu sechs Stunden Laufzeit). Er führt aus, was
nicht gleich starten konnte – die Aufgabe dauert dann nur eine Minute
länger –, und er bemerkt eine Aufgabe, deren Prozess verschwunden ist, etwa
weil Rentalars mittendrin neu gestartet wurde: Jede laufende Aufgabe
vermerkt, welcher Prozess sie ausführt. Eine so unterbrochene Aufgabe
startet er **einmal neu**; wird sie ein zweites Mal unterbrochen, wird sie
als fehlgeschlagen vermerkt („Die Aufgabe wurde unterbrochen.“). Alle
Aufgaben vertragen das: Ein Import schreibt alles oder nichts, Etiketten
und Export entstehen neu. Von Hand:

```sh
sudo rentalars run_jobs
```

Aufgaben laufen nebeneinander, jede in ihrem Prozess – bis auf eine Art:
Ein Server verkleinert **immer nur ein Video für den Chat
zugleich** (Art `chat_video`, Sperrdatei
`/var/lib/rentalars/chat-videos.lock`). Der Prozess, der die Sperre hat,
arbeitet die wartenden Videos nacheinander ab; die übrigen bleiben
stehen, bis er oder der Zeitgeber sie aufnimmt (unten, „Fotos und Videos
im Chat“).

Derselbe Lauf gleicht nach den Aufgaben auch die Kalender der
Personen ab (unten, „Kalender der Personen“), stellt er danach
die fälligen Zustellungen der Webhooks zu (unten, „Webhooks“),
benachrichtigt er über fällige Wiedervorlagen von Projekten (höchstens 500
je Lauf, der Rest in der nächsten Minute), und führt er zuletzt
die Ausführungen von Automationen aus, die noch warten (unten,
„Automationen“); ein Fehler dort hält die Aufgaben nicht auf. Eine lange
Aufgabe im selben Lauf verzögert Kalender, Webhooks, Wiedervorlagen und
Automationen entsprechend.

Schlägt eine Aufgabe fehl, steht der Grund an der Aufgabe und in der
Benachrichtigung; der Fehler wird außerdem wie jeder andere unter „Fehler
der Anwendung“ gezählt (unten). Was eine Aufgabe ausgibt, steht im
Protokoll des Dienstes, der sie gestartet hat: `rentalars` für Aufgaben, die
eine Seite gestartet hat, `rentalars-jobs` für die des Zeitgebers.

Die Ergebnisse – die Berichte der Importe in der Datenbank, die Dateien der
Etiketten, Datenexporte und Sicherungen aus dem Browser im Datenordner unter
`/var/lib/rentalars/media/jobs/` – werden nach der eingestellten Frist
gelöscht, voreingestellt nach 7 Tagen (unten, „Aufbewahrungsfristen“). Bis
dahin stecken die Dateien auch in den nächtlichen Sicherungen – außer den
Sicherungen aus dem Browser (`media/jobs/backups/`): Die lässt die
nächtliche Sicherung aus, sonst würde jede Sicherung die vorige mitschleppen
([sicherung.md](sicherung.md), „Sicherung aus dem Browser“).

## Einstellungen

Es gibt zwei Orte.

**Im Browser**, unter „Einstellungen“ (die Adressen beginnen mit `/administration/`), für
alles Fachliche: Firmendaten und Logo samt Bankverbindung, Registerangaben
und Zahlungsziel für die Dokumente, Pufferzeiten und die üblichen
Projektzeiten (12 bis 12 Uhr), Regeln für Passwörter und
Anmeldesperre, Aufbewahrungsfristen, die Grenze für API-Aufrufe,
„Bei geänderten Zeiten neu anfragen“ (ob Personal nach geänderten
Zeiten von selbst eine neue Einsatzanfrage bekommt; voreingestellt an),
 auch „Antwort auf Einsatzanfragen“ (vorher unter E-Mail),
 die „Anschrift des Lagers“ (Start der Fahrten), „Karten sofort
laden“, „Rentalars als Buchhaltungsprogramm verwenden“, die Grenzen der Hinweise bei
auffälligen Zeiten und die Fahrtkosten je Kilometer, dazu die eigenen
Seiten **Zuschläge** (Nacht, Sonn- und Feiertage; Bundesland) und
**Automationen** (unten), die größte hochladbare Datei (unten,
„Größere Dateien“),
der Standard-Lagerort für neue Exemplare (Lagerorte),
Nummernkreise (die Projekte: `2026-0001`; die der Dokumente: `AN-2026-0001` für Angebote,
`AB-…` für Auftragsbestätigungen, `LS-…` für Lieferscheine, `RE-…` für
Rechnungen und Stornorechnungen, `CD-…` für Crew-Dispositionen, jedes Jahr
neu), Nutzer und Rollen, Kategorien, Steuerarten, Staffeln, Prüfarten,
Qualifikationsarten, Dokumentvorlagen und Textbausteine, Postfächer
und Signatur, die Buchhaltung (Lexware Office, DATEV) und die
Webhooks, die „Sprache der Dokumente“ (Firmendaten), die Sprache
jedes Kontos (Nutzer), die KI und die Seite „Serveradresse und
Zertifikat“ (unten), unter Benachrichtigungen die Erinnerung an
„Zeiten zur Freigabe“ und unter KI der Anwendungsfall „Rechnungen lesen“
(unten, „KI“), die Seiten **Audits** (Audit-Intervall in
Monaten, voreingestellt 24, 0 = aus; Schnellauswahl für To-Dos, höchstens
12), **Eigene Felder** und **Feldsätze** und unter „Postfächer und
Signatur“ das **Schloss neuer Nachrichten** (in Projekten voreingestellt
mit Schloss, in Servicefällen offen). Das beschreibt das
[Benutzerhandbuch](../handbuch/benutzerhandbuch.md).

**In der Konfigurationsdatei** `/etc/rentalars/rentalars.conf` für alles, was
die Umgebung des Servers betrifft – und nur dort (NFA-032):

| Abschnitt | Inhalt |
|---|---|
| `[rentalars]` | Adresse, unter der Rentalars erreichbar ist (`url` – sie steht in den Links der Mails und am Ende jeder automatischen Mail; sie muss mit `https://` beginnen, außer `allow_http = yes`, unten „HTTPS und vorgeschaltete Server“; `rentalars address apply` ändert sie); weitere Namen oder IP-Adressen, unter denen Rentalars geöffnet werden darf (`allowed_hosts`, kommagetrennt,; dazu `allow_own_addresses`, unten „Neue IP-Adresse des Servers“); geheimer Schlüssel; Sprache (`language`: `de` oder `en` – die Sprache für Konten ohne eigene Wahl, für die Anmeldeseite, wenn der Browser weder Deutsch noch Englisch verlangt, und für Dokumente und Startdaten einer neuen Installation) und Zeitzone |
| `[database]` | Zugang zur Datenbank (schreibt das Installationsskript); bei einem vorhandenen Server auch Host, Port und TLS |
| `[email]` | Mailserver für die Systemmails (Einladungen, Benachrichtigungen), solange kein Postfach im Browser die Rolle „Systemmails“ hat; ohne `host` und ohne ein solches Postfach verschickt Rentalars keine Systemmails (unten, „Ohne Mailserver“) |
| `[backup]` | Wohin gesichert wird, wie lange Sicherungen bleiben, ob sie verschlüsselt werden |
| `[maps]` (freiwillig) | Kartenserver und Kartensuche: ohne den Abschnitt die von OpenStreetMap; leer schaltet die Karten ab (unten, „Karten“) |
| `[network]` (freiwillig) | `allow_internal`: interne Netze, Adressen und Hostnamen, die Kalender, Webhooks und Mailserver von Postfächern trotzdem erreichen dürfen (unten, „Verbindungen ins interne Netz“) |

Die **Postfächer**, aus denen Rentalars die Projektmails holt und über die
es sie versendet, stehen nicht hier, sondern im Browser unter
Einstellungen → E-Mail („Postfächer und Signatur“, unten „Postfächer“);
ihre Passwörter liegen verschlüsselt in der Datenbank. Dort kann
auch ein Postfach die Systemmails übernehmen; dann gilt `[email]` nur
noch, solange die Datenbank nicht erreichbar ist.

Jede Einstellung ist in der Datei selbst erklärt; eine auskommentierte Zeile
zeigt den Wert, der ohne sie gilt. Nach einer Änderung:

```sh
sudo systemctl restart rentalars
```

Die Datei enthält das Datenbankpasswort und den geheimen Schlüssel. Sie ist
nur für `root` und das Dienstkonto lesbar; das soll so bleiben.

### HTTPS und vorgeschaltete Server

Ein Produktionsserver (NFA-073, aus einer Code-Prüfung) startet
nur, wenn `url` unter `[rentalars]` mit `https://` beginnt. Mit einer
`http://`-Adresse bricht der Start mit einer Fehlermeldung ab
(`journalctl -u rentalars`) – auch eine Aktualisierung, die dann von selbst
zurückgeht. `install.sh` schreibt immer `url = https://<Name>`; betroffen
ist nur eine von Hand geänderte Datei.

- **Mit der NGINX-Konfiguration der Installation** ändert sich nichts:
  NGINX verschlüsselt und sagt Rentalars mit der Kopfzeile
  `X-Forwarded-Proto: https`, dass die Anfrage verschlüsselt kam.
- **Hinter einem anderen Server, der verschlüsselt** (Reverse Proxy,
  Load Balancer, Firewall): `url` bleibt `https://…` – die Adresse, die
  die Nutzer im Browser sehen –, und dieser Server muss die Kopfzeile
  `X-Forwarded-Proto: https` an Rentalars weitergeben (bzw. an das NGINX
  der Installation, das sie durchreicht). Fehlt sie, leitet Rentalars
  jede Anfrage auf https um, und der Browser landet in einer Schleife.
  **Dazu gehört die Adresse des Besuchers:** Hinter so einem Server
  sieht Rentalars bei jeder Anfrage dessen Adresse, und zwanzig falsche
  Anmeldungen irgendeines Besuchers sperren die Anmeldung für alle. Trag
  deshalb unter `[rentalars]` `trusted_proxies = 10.0.0.5` ein (eine Adresse
  oder ein Netz wie `10.0.0.0/8`, mehrere mit Komma) und führe
  `sudo rentalars nginx-site` aus (das nächste Aktualisieren tut es auch). NGINX
  glaubt `X-Forwarded-For` dann nur bei Anfragen von diesen Adressen (Datei
  `/etc/nginx/snippets/rentalars-realip.conf`, wird bei jedem Aktualisieren
  neu geschrieben; Änderungen darin gehen verloren). Dieser Server muss
  die Adresse des Besuchers in `X-Forwarded-For` mitschicken. Ohne den Eintrag
  bleibt alles, wie es war.
- **Bewusst ohne Verschlüsselung** – etwa in einem abgeschlossenen Netz
  ohne Zertifikat –: unter `[rentalars]` `allow_http = yes` eintragen und
  `sudo systemctl restart rentalars`. Passwörter und Sitzungen gehen dann
  im Klartext durchs Netz; der Selbsttest warnt unter „Sicherheit →
  HTTPS“ dauerhaft. Für den Betrieb aus dem Internet ist das nie richtig.

### Neue IP-Adresse des Servers

Rentalars antwortet nur auf Namen, die es kennt: den aus `url`, `localhost`
und `127.0.0.1`. Wer es unter einem anderen Namen öffnet, bekommt statt
einer Fehlerseite des Servers eine Seite, die sagt, unter
welchem Namen er gekommen ist, welche Adresse eingetragen ist und was zu
tun ist. Sie erscheint nach einem Wechsel der IP-Adresse (neue
DHCP-Zuweisung, verschobene virtuelle Maschine), wenn Leute noch die alte
oder schon die neue Adresse benutzen.

- **Die IP-Adressen des Servers selbst** brauchen keinen
  Eintrag: Rentalars liest sie vom System (Linux) und antwortet auf jede
  davon, auch gleich nach einem Wechsel. Das ist ungefährlich – eine
  Adresse, die zu diesem Rechner gehört, kann ein Angreifer nicht für sich
  einsetzen; die Links in Mails kommen immer aus `url`. Die Adressen werden
  alle 30 Sekunden neu gelesen: eine Adresse, die der Server nicht mehr hat,
  wird nach kurzer Zeit nicht mehr beantwortet. Es zählt nur die
  gebräuchliche Schreibweise einer Adresse (`[::1]`, nicht `[0::1]`). Die
  erste Antwort auf eine neue Adresse steht als Hinweis im Dienstprotokoll
  (`journalctl -u rentalars`). Eine Folge: wer von außen Anfragen mit
  erfundenen Adressen schickt, erkennt an der Antwort, welche
  IP-Adressen der Server hat. Wer das nicht will, trägt unter `[rentalars]`
  `allow_own_addresses = no` ein und die Adressen, die gelten sollen,
  als `allowed_hosts`.
- **Andere Namen oder Adressen** – ein zweiter Rechnername, eine Adresse
  hinter einer Weiterleitung – trägst du unter `[rentalars]` ein:
  `allowed_hosts = 192.168.1.50, rentalars.lan`, kommagetrennt, ohne
  `http://`, ohne Port, ohne Pfad; `.example.de` erlaubt alle Namen unterhalb
  von `example.de`. Ein `*` (jeder Name) nimmt Rentalars nicht an und
  bricht den Start mit einer Meldung ab. Danach
  `sudo systemctl restart rentalars`.
- **Ändert sich der Name in `url`** (und mit ihm das Zertifikat), nimm
  `sudo rentalars address` (oben, „Adresse und Zertifikat“), nicht
  `allowed_hosts`.

Eine Anfrage an einen unbekannten Namen steht nicht als Fehler im
Fehlerprotokoll und löst keine Meldung an die Betreiber aus; sie steht als
Warnung im Dienstprotokoll.

### Verbindungen ins interne Netz

Kalender (ICS-Links und CalDAV), Webhooks, die IMAP- und SMTP-Server
der Postfächer und die Server des Verzeichnisses (LDAP) und die
Schnittstellen der KI trägt jemand im Browser ein, und der Server verbindet sich
dann dorthin. Damit niemand so Systeme im eigenen Netz erreicht, die dafür
nicht gedacht sind, lehnt Rentalars (NFA-071, aus einer
Code-Prüfung) jedes Ziel ab, das **intern** ist:

- dieser Rechner (`127.0.0.0/8`, `::1`, `localhost`) und alle Adressen des
  Servers selbst – seiner Schnittstellen, seines Rechnernamens und der
  Adresse aus `url`;
- private Netze (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`,
  `fc00::/7`), Link-local (`169.254.0.0/16`, `fe80::/10`), das Netz der
  Provider (CGNAT, `100.64.0.0/10`), Multicast, reservierte und
  unbestimmte Adressen und alles andere, was nicht weltweit erreichbar
  ist, auch eine IPv4-Adresse in einer IPv6-Adresse.

Rentalars löst den Namen auf, behält nur erlaubte Adressen der Antwort und
verbindet sich mit genau der geprüften Adresse – ohne zweites Nachschlagen,
damit eine geänderte DNS-Antwort nichts umgeht; das Zertifikat wird
weiterhin gegen den Namen geprüft. Weiterleitungen eines Kalenderservers
folgt es nur Schritt für Schritt, jede neu geprüft (höchstens fünf);
Webhooks folgen keiner Weiterleitung. Eine IP-Adresse oder `localhost`
lehnen schon die Formulare und die API ab; ein Name scheitert beim
Verbinden mit „Die Adresse führt in ein internes Netz. …“. Die
aufgelöste Adresse nennen die Meldungen im Browser nicht, nur der
Selbsttest.

**Gewollte interne Ziele freigeben** – das NAS mit dem Firmenkalender, die
eigene Nextcloud, das ERP, das Webhooks empfängt, der Mailserver im Haus:

```ini
[network]
allow_internal = 192.168.1.0/24, nas.local
```

Durch Kommas getrennt: Netze, einzelne Adressen oder Hostnamen. Ein
Hostname gibt Verbindungen zu genau diesem Namen frei, gleich in welche
Adresse er sich auflöst – nicht aber dieselbe Adresse unter einem anderen
Namen; dafür nimmt man die Adresse oder das Netz. Ein Eintrag,
der nichts davon ist, verhindert den Start mit einer Meldung. Danach
`sudo systemctl restart rentalars`.

**Nicht betroffen** ist, was der Betreiber selbst in dieser Datei
einträgt: `[email]`, `[maps]`, die Datenbank – und Lexware Office mit
seiner festen Adresse.

**CalDAV-Anmeldedaten** (NFA-072) gehen nur an genau den Server – Schema,
Host und Port –, für den sie eingetragen sind, auch bei einer
Weiterleitung; eine Adresse auf einem anderen Host, die der Server in
seiner Antwort nennt, ruft Rentalars nicht auf. Einzige Ausnahme ist
iCloud: `caldav.icloud.com` darf an `pNN-caldav.icloud.com` (https,
Port 443) weitergeben. Leitet ein anderer Anbieter auf einen anderen Host
um, trägt die Person dort die direkte Adresse ihres Kalenders ein.

**Proxy aus der Umgebung:** Gilt `https_proxy` oder `http_proxy` für eine
Adresse, geht die Verbindung weiter über den Proxy. Rentalars prüft den
Namen vorher, der Proxy löst ihn aber selbst noch einmal auf – gegen eine
geänderte DNS-Antwort schützt dann nur der Proxy. Der Selbsttest warnt
deshalb unter „Verbindungen zu anderen Servern → Proxy“, sobald die
Umgebung des Dienstes einen Proxy nennt. Dann interne Ziele auch im Proxy
sperren – oder den Proxy für diese Ziele weglassen (`no_proxy`), damit
Rentalars selbst mit der geprüften Adresse verbindet.

**Was schon eingetragen ist**, bleibt stehen, auch wenn es jetzt ins
interne Netz führt: Rentalars löscht nichts, die Verbindung scheitert
nur. Der Selbsttest nennt solche Einstellungen in der Gruppe
„Verbindungen zu anderen Servern“ (unten, „Selbstprüfung“).

### Aufbewahrungsfristen

Wie lange Rentalars Protokolle und Ergebnisse aufhebt, steht unter
**Einstellungen → Firmendaten und Grundeinstellungen** (NFA-011). Die
tägliche Wartung um 4:15 Uhr löscht, was älter ist:

| Was | Voreinstellung | einstellbar |
|---|---|---|
| Sicherheitsprotokoll (Anmeldungen, Fehlversuche, Änderungen an Nutzern und Rollen) | 365 Tage | 30 bis 3.650 Tage |
| Änderungsprotokoll (wer hat was wann geändert) | dauerhaft (0) | 0 = dauerhaft, sonst bis 36.500 Tage |
| Benachrichtigungen, gelesen oder nicht | 180 Tage | 7 bis 3.650 Tage |
| Ergebnisse von Aufgaben im Hintergrund, mit ihren Dateien – auch Sicherungen aus dem Browser | 7 Tage | 1 bis 365 Tage |
| Zugriffsprotokoll (wer Kunden, Personen, Projekte, Exporte und Sicherungen geöffnet oder heruntergeladen hat) | 180 Tage | 30 bis 3.650 Tage |

Die Frist für die **Projektmails** steht nicht hier, sondern bei den
Regeln für alle Postfächer (Einstellungen → E-Mail, „Mails aufbewahren
für … Tage“); voreingestellt werden sie nie gelöscht. Nach ihr richtet sich
 auch das **Mail-Protokoll**: Seine Einträge bleiben so lange wie
die Mails, und 365 Tage, wenn die Mails nie gelöscht werden. Die
**Zustellungen der Webhooks** bleiben fest 30 Tage, die
**Ausführungen von Automationen** fest ein Jahr; diese Fristen
lassen sich nicht einstellen. Gelöschte Einträge stecken noch in den
Sicherungen, bis diese selbst gelöscht werden ([sicherung.md](sicherung.md)).

### Die Adresse ändert sich

Ein Administrator bereitet die neue Adresse samt Zertifikat im
Browser vor, und du übernimmst sie mit einem Befehl – unten, „Serveradresse
und Zertifikat ändern“. Von Hand geht es weiterhin: `url` in `[rentalars]`
ändern, ein Zertifikat für den neuen Namen besorgen, `server_name` sowie
die Pfade des Zertifikats in `/etc/nginx/sites-available/rentalars`
anpassen, dann `sudo nginx -t && sudo systemctl reload nginx` und
`sudo systemctl restart rentalars`. Haben Personen ihre Einsätze als
Kalender abonniert, zeigt ihr Abo-Link (`/calendar-feed/…`) noch auf die
alte Adresse; er funktioniert, solange die alte Adresse weiterleitet, sonst
abonnieren sie ihn mit der neuen Adresse neu (unter „Meine
Personaldaten“). Automatische Mails nennen nach dem Neustart die neue
Adresse (unten, „Postfächer“). Auch die Rentalars-App auf den Telefonen
braucht dann die neue Adresse (unten, „Die Rentalars-App für Android“).

### Die NGINX-Konfiguration

`/etc/nginx/sites-available/rentalars` schreibt die Installation aus der
Vorlage `deploy/nginx/rentalars.conf`. Eine Aktualisierung lässt die Datei,
wie sie ist – du hast sie vielleicht angepasst –, und ändert nur, was das
installierte NGINX verlangt (die Schreibweise von HTTP/2). Neue Einstellungen
einer späteren Vorlage kommen deshalb nicht von selbst an; der Selbsttest
nennt die fehlenden.

Übernehmen lassen sie sich mit

```sh
sudo rentalars nginx-site
```

Der Befehl füllt die Vorlage der installierten Version mit dem Namen aus
der Konfigurationsdatei und dem Zertifikat, das NGINX jetzt benutzt, zeigt
die Unterschiede und fragt nach. Eigene Änderungen an der Datei gehen dabei
verloren; die bisherige Datei bleibt als
`/etc/rentalars/nginx-site.before-…` liegen. NGINX wird nur neu geladen,
wenn es die neue Datei annimmt – sonst gilt die bisherige weiter.
`--show` zeigt nur die Unterschiede.

### Größere Dateien

Wie groß eine hochgeladene Datei sein darf – Projektdatei, Hallenplan,
Beleg von Spesen, Anhang einer gesendeten Mail –, steht unter
Einstellungen → Firmendaten und Grundeinstellungen, **„größte hochladbare
Datei (MB)“**: voreingestellt 50, höchstens 500. Rentalars nimmt
auch **Showfiles** von Licht-, Medien- und Tonpulten an (an ihrer
Endung; eine Show, die ein Ordner ist, als ZIP) – eine Show mit Videos
oder Samples ist schnell größer als 50 MB. Dann den Wert erhöhen; NGINX
nimmt aus der Vorlage bis 510 MB an (`client_max_body_size 510m`), mehr
muss dort nicht eingestellt werden. Denk an den Platz: Jede Datei liegt im
Datenordner und steckt in jeder der 14 nächtlichen Sicherungen
([installation.md](installation.md), „Speicherplatz“). Fotos und Videos im
Chat haben eigene, feste Grenzen (unten, „Fotos und Videos im
Chat“).

### Hochgeladene Einkaufsrechnungen

In der Materialverwaltung lässt sich ein Kauf mit seiner
Rechnung einpflegen („Kauf einpflegen“; [Benutzerhandbuch](../handbuch/benutzerhandbuch.md),
Abschnitt 4). Bis der Kauf gespeichert ist, liegt die hochgeladene
Rechnung im Datenordner unter `/var/lib/rentalars/purchase-invoices/` –
unter einem zufälligen Namen, nur für den Nutzer, der sie hochgeladen hat,
und höchstens zwei Tage. Beim Speichern wird sie einmal unter `media/`
abgelegt und an jedes neue Exemplar gehängt; dann steckt sie wie jede
Datei in der Sicherung. Rechnungen von Käufen, die nie gespeichert wurden,
löscht das nächtliche Aufräumen nach zwei Tagen (oben, „Was von selbst
geschieht“), ebenso das nächste Hochladen. Der Ordner ist ein
Zwischenlager: Er steckt **nicht** in der Sicherung und muss es auch nicht
([sicherung.md](sicherung.md)). Es gilt dieselbe Größengrenze wie für
alle hochgeladenen Dateien (oben). Gelesen werden PDFs mit Text mit der
Bibliothek **pypdf** (BSD-Lizenz), die mit Rentalars
installiert wird – die Aktualisierung holt sie mit den übrigen
Bibliotheken; eine Texterkennung für Scans gibt es nicht.

### Eingangsrechnungen und ihre Dateien

Unter **Buchhaltung → Eingangsrechnungen** gibt es das Verzeichnis
der Rechnungen von Lieferanten (DOK-023, DOK-024; Benutzerhandbuch,
Buchhaltung). Für den Betrieb zählen vier Dinge.

- **Wo die Dateien liegen:** unter `media/incoming/<Jahr>/` im Datenordner,
  mit einem zufälligen Namen; heruntergeladen werden sie nur über Rentalars
  und nur von Nutzern mit Material und dem Recht auf Einkaufspreise.
  Erlaubt sind PDF, PNG, JPEG und WEBP bis zur allgemeinen Größengrenze
  („Größere Dateien“, oben). Im Gegensatz zu den „Hochgeladenen
  Einkaufsrechnungen“ ist das **kein Zwischenlager**: Die Dateien bleiben,
  solange die Rechnung in Rentalars steht, und stecken **in der nächtlichen
  Sicherung** ([sicherung.md](sicherung.md)). Der Speicherbedarf wächst mit
  jeder Rechnung; plane ihn bei der Sicherung mit ein
  ([installation.md](installation.md), „Speicherplatz“).
- **Was gelesen wird:** Aus dem Text eines PDFs liest Rentalars Nummer,
  Datum, Fälligkeit, bekannten Lieferanten und Summen mit der Bibliothek
  pypdf – ohne KI, ohne dass etwas den Server verlässt. Ist die KI für
  „Rechnungen lesen“ eingeschaltet (Einstellungen → KI), geht der **Text**
  zusätzlich an den dort gewählten Anbieter (Art `ai_incoming_invoice`, als
  Aufgabe im Hintergrund, im KI-Protokoll ohne Inhalt) und liefert die
  Positionen; mit einem Anbieter im Internet verlässt der Rechnungstext
  euer Haus – wie bei „Kauf einpflegen“ (oben, „KI“). **Scans und Bilder
  werden aufbewahrt, aber nicht gelesen**; eine Texterkennung gibt es nicht.
- **Rechte:** Ansehen braucht Material (lesen) und das Recht auf
  Einkaufspreise; Hochladen, Bearbeiten und Einpflegen Material (schreiben);
  Löschen Material (löschen), und nur wenn nichts eingepflegt wurde. Die
  Einstellungen (GWG-Grenze, Nutzungsdauer, Erinnerungswert: **Einstellungen →
  Eingangsrechnungen**) braucht das Modul Administration.
- **Gelöscht wird nichts von selbst.** Die gesetzlichen Aufbewahrungsfristen
  für Rechnungen einzuhalten ist Sache des Betriebs; Rentalars räumt
  Eingangsrechnungen nicht ab. Wer eine Rechnung löscht, löscht auch die
  Datei.

### Altprojekte importieren: Zwischenlager und Aufbewahrung

Unter **Buchhaltung → Altprojekte importieren** (PRJ-130; Recht: Preise sehen
und Projekte schreiben, Benutzerhandbuch) übernimmt Rentalars alte
Ausgangsrechnungen als abgeschlossene Projekte mit historischer Rechnung.

- **Zwischenlager:** Hochgeladene PDFs liegen in
  `/var/lib/rentalars/legacy-invoices/`, bis sie übernommen, übersprungen
  oder verworfen sind, **höchstens 14 Tage**. Der Ordner ist **nicht in der
  Sicherung** und muss es nicht sein (wie `purchase-invoices/`,
  [sicherung.md](sicherung.md)). Nach 14 Tagen werden nicht übernommene
  Rechnungen beim nächsten Hochladen oder Öffnen der Seite verworfen, nicht
  vom nächtlichen Aufräumen. Übernommen hängt das Original-PDF an der
  historischen Rechnung unter `media/` und ist gesichert.
- **Grenzen:** bis zu 30 PDFs je Stapel, je höchstens 10 MB, zusammen
  höchstens 120 MB. Gelesen wird als Aufgabe im Hintergrund (Art
  `legacy_invoices`).
- **KI oder Muster:** Ist die KI für „Rechnungen lesen“ eingeschaltet, geht
  **nur Text** an den dort gewählten Anbieter; sonst – und wenn die KI
  ausfällt – liest Rentalars nach Mustern. Mit einem Anbieter im Internet
  verlassen die Texte alter Rechnungen mit Kundennamen und Anschriften euer
  Haus (Auftragsverarbeitung, siehe „Datenschutz“ unter „Automatische
  KI-Zusammenfassungen“).
  Für den Anfang: wenige PDFs, die Vorschau kritisch lesen. **Wie gut die
  KI echte Fremdrechnungen liest, ist nicht geprüft.**
- **Stiller Betrieb:** Die Übernahme sendet keine Mails und legt keine
  Aufgaben, Reservierungen, Verfügbarkeiten, Automationen oder Webhooks an;
  die laufende Rechnungsnummer bleibt unberührt, die Projekte tragen eine
  eigene Nummer `ALT-<Jahr>-<nnnn>`. Historische Belege stehen **nicht** im
  DATEV-Export, außer die Option „historische Belege einschließen“ ist an
  (API `include_historic`); sie sind nicht buchbar und nicht stornierbar
  und stehen nicht in der Fehlerliste für Lexware.
- **Rückgängig** geht binnen 7 Tagen, wenn an dem Übernommenen nichts mehr
  geändert wurde. Danach löscht man ein Projekt, wie man es immer tut.
- **Aufwand:** Gemessen wurden 4,6 Sekunden für das Lesen von 30 PDFs, 2,3
  Sekunden und 369 Abfragen für die Seite eines Stapels und 5,0 Sekunden für
  das Bestätigen von 30 Rechnungen.

### Scannen und die Kamera

Etiketten und Barcodes lassen sich in der Materialliste, beim
Packen und bei den Planungswünschen scannen (MAT-027, UIX-006, PCK-010,
PCK-011; Benutzerhandbuch).

- **Das Feld „ID scannen oder eintippen“ geht immer.** Ein USB- oder
  Bluetooth-Scanner „tippt“ in das Feld wie eine Tastatur; dafür braucht es
  nichts auf dem Server.
- **Die Kamera des Telefons oder Tablets ist ein Zusatz** und braucht zwei
  Dinge. Erstens **HTTPS**: Browser geben die Kamera nur einer Seite mit
  sicherer Verbindung frei (`https://…`; `localhost` zählt auch). Rentalars
  wird immer mit HTTPS eingerichtet ([installation.md](installation.md),
  „Name und Zertifikat“); hinter einem eigenen Server davor muss auch
  dessen Adresse `https://` sein. Ob ein Browser die Kamera bei einem
  selbst ausgestellten Zertifikat erlaubt, dem das Gerät nicht traut, ist
  nicht geprüft – ein Zertifikat von Let's Encrypt oder eure
  Zertifizierungsstelle auf dem Gerät ist der sichere Weg. Wer Rentalars über
  `http://` aufruft, kann die Kamera nicht nutzen und tippt oder nimmt den
  USB-Scanner. Zweitens **einen Browser mit `BarcodeDetector`**: Chrome, Edge
  und Browser auf Android. Firefox und Safari haben ihn nicht; dort bleiben
  Tippen und USB-Scanner. Einen Rückfall mit einer Bibliothek im Browser
  (jsQR) gibt es nicht.
- **Der Header `Permissions-Policy: camera=(self), microphone=(), geolocation=(), payment=()`**
  erlaubt die Kamera nur den Seiten von Rentalars selbst und keiner Seite, die
  darin eingebettet ist; Mikrofon, Standort und Zahlung sind für alle gesperrt. Rentalars setzt ihn bei jeder Antwort selbst (nicht NGINX; die
  mitgelieferte NGINX-Vorlage ändert ihn nicht). Steht ein weiterer Server
  oder Proxy vor Rentalars, darf er den Header nicht entfernen und nicht durch
  `camera=()` ersetzen, sonst fragt der Browser nicht nach der Kamera. Prüfen:

  ```sh
  curl -sI https://rentalars.example.de/ | grep -i permissions-policy
  ```

- **Datenschutz:** Kein Kamerabild verlässt den Browser; erkannt wird auf
  dem Gerät, an den Server geht nur der gelesene Text (die ID).
- **Die QR-Codes der Etiketten** zeigen auf `{RENTALARS_URL}/m/<ID>` (`url`
  der Konfigurationsdatei); wer das Ziel ändern will, trägt es unter
  Einstellungen → Etiketten-Einstellungen bei „QR-Code führt zu“ ein (eine
  Adresse mit `{id}`, API-Feld `qr_target`). Wer ein Etikett abscannt,
  braucht die Rechte am Material; ohne Recht antwortet Rentalars wie bei
  „nicht gefunden“.
- **Nicht echt getestet:** Kamera, BarcodeDetector, gedruckte Etiketten und
  Scanner-Hardware – die Tests benutzen nachgestellte Eingaben.

### Preisangebote freier Kräfte

Eine freie Kraft kann auf eine Einsatzanfrage mit einem
eigenen Preis antworten (PER-038). Die Funktion ist **aus**: Eine Anfrage wird mit
„zusagen“ oder „absagen“ beantwortet, bis ein Administrator unter **Einstellungen → Preisangebote freier Kräfte**
(`/administration/price-offers/`) den Schalter „Freie Kräfte dürfen einen
eigenen Preis anbieten“ einschaltet. Dort stehen außerdem „auch Aushilfen“
(sonst nur Freie), das niedrigste und das höchste Angebot in Prozent des
hinterlegten Satzes (leer = keine Grenze) und die Zahl der Vorschläge je
Anfrage (voreingestellt 4, 1 bis 10; Angebote und Gegenangebote zusammen).

- Die Mail zur Anfrage bekommt, solange die Funktion an ist, eine Zeile mit
  Link: „Du möchtest deinen eigenen Preis nennen? Das geht in Rentalars:“.
  Ausschalten nimmt sie wieder heraus; frühere Angebote bleiben sichtbar.
- Beträge sind Personalkosten: Die Kraft sieht nur ihre eigenen Angebote und
  den hinterlegten Satz nur mit dem Recht auf Personalkosten oder wenn
  „Personen dürfen ihre eigenen Stundensätze sehen“ gilt. Ohne das Recht auf
  Personalkosten zeigt die Planung nichts von Angeboten, und die
  Benachrichtigungen gehen nur an Nutzer mit diesem Recht, die das Projekt
  lesen dürfen.
- Eine Annahme setzt den Kostensatz **genau dieser** Zeile; der Kundenpreis
  ändert sich nicht. Sie endet, wenn jemand den Satz von Hand ändert oder
  Person oder Funktion wechseln.
- Grenzen: 30 Angebotsaktionen je Nutzer und Stunde, zwei Nachkommastellen,
  nur Euro.
- In der Companion-App sind die neuen Arten der Benachrichtigung
  **nicht** voreingestellt an; wer sie dort will, schaltet sie in Mein Konto
  → Benachrichtigungen ein.

### Fotos und Videos im Chat

Eine Chatnachricht (UIX-049, NFA-076) kann Fotos und Videos
tragen ([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 7,
„Chat im Projekt“). Der Server behält nur eine verkleinerte Fassung.

**ffmpeg ist ein Pflichtpaket.** Videos verkleinert Rentalars mit
`ffmpeg` und prüft sie vorher mit `ffprobe`; beides kommt mit dem
Ubuntu-Paket **ffmpeg**. `install.sh` installiert es mit den übrigen
Paketen. Die Aktualisierung richtet es ebenfalls ein
(die neue `ai.sh refresh`, die sie
nach dem Umschalten aufruft, holt fehlende Pakete der neuen Version nach),
und wartet dafür bis zu zwei Minuten auf eine laufende Paketverwaltung –
etwa die automatischen Sicherheitsupdates. Misslingt es, läuft die
Aktualisierung mit einer Warnung durch; dann von Hand:

```sh
sudo apt install ffmpeg
```

oder `sudo rentalars ai refresh`. Ohne ffmpeg läuft Rentalars weiter;
nur Videos werden abgelehnt – das Formular sagt es den Nutzern, Fotos gehen
(sie verkleinert Pillow im Programm selbst).

**Der Selbsttest warnt** (unten, „Selbstprüfung“):

- Gruppe „Versionen“, Zeile **„ffmpeg“**: die Version, oder die Warnung
  „ffmpeg ist nicht installiert: Videos im Chat werden abgelehnt, Fotos
  gehen. Installieren mit: sudo apt install ffmpeg“;
- Gruppe „Sicherheit“, Zeile **„NGINX: Größe beim Hochladen“**: wenn
  `client_max_body_size` der NGINX-Site kleiner ist als ein Video im Chat
  (200 MB und 1 MB für das Formular). Die Vorlage nimmt 510 MB an (oben,
  „Größere Dateien“); eine von Hand verkleinerte Site übernimmt
  die Vorlage wieder mit `sudo rentalars nginx-site` (oben, „Die
  NGINX-Konfiguration“).

**Grenzen** (fest im Programm, nicht einstellbar und unabhängig von „größte
hochladbare Datei“): bis 10 Dateien je Nachricht, Fotos bis 25 MB, Videos
bis 200 MB und 20 Minuten, zusammen bis 500 MB.
Geprüft wird der Inhalt, nicht die Endung: Ein Foto muss sich mit Pillow
öffnen lassen (JPEG, PNG, GIF, WebP), ein Video muss am Anfang der Datei als
MP4/QuickTime, Matroska/WebM oder AVI erkennbar sein und `ffprobe` mit
genau diesem Format und nur dem Dateiprotokoll bestehen.

Damit eine kleine Datei den Server nicht lange beschäftigt oder seinen
Speicher füllt, gilt außerdem:

- **Fotos:** Zuerst die Größe in Bytes, dann Format und Pixelzahl aus dem
  Kopf der Datei – bevor irgendetwas entpackt wird. Ein Foto als PNG, GIF
  oder WebP entpackt Pillow ganz; es darf deshalb höchstens
  **16 Megapixel** haben (das sind 64 MB im Speicher). Ein größeres wird
  abgelehnt, mit dem Hinweis, es als JPEG zu schicken. Ein JPEG darf bis **150 Megapixel**
  haben: Rentalars entpackt es gleich verkleinert (auf die Hälfte, ein
  Viertel oder ein Achtel, so dass die lange Seite noch 2048 Pixel hat).
- **Videos:** abgelehnt, wenn das Bild an einer Seite mehr als
  **4096 Pixel** hat, wenn es mehr als **240 Bilder pro Sekunde** sind
  oder mehr als **72.000 Einzelbilder** (20 Minuten bei 60 Bildern pro
  Sekunde). Für die 20 Minuten zählt die längste Angabe von Datei und
  Videospur – die Angabe der Datei allein könnte für eine Stunde Video
  wenige Sekunden behaupten –, und ffmpeg rechnet ohnehin höchstens
  20 Minuten um.

**Was gespeichert wird:**

- **Fotos** werden gleich beim Hochladen aufrecht gedreht, auf höchstens
  2048 Pixel an der langen Seite verkleinert und als JPEG **ohne
  Metadaten** gespeichert: der **Standort** (GPS) bleibt, Gerät,
  Aufnahmezeit und Kommentar entfallen; dazu eine Vorschau mit 640 Pixeln
  ohne Standort. Ebenso Fotos an Defektmeldungen, Spesenbelegen und
  Material.
- **Videos** werden als Aufgabe im Hintergrund (Art `chat_video`, oben
  „Aufgaben im Hintergrund“) mit ffmpeg auf höchstens 720p, 30 Bilder je
  Sekunde, H.264/AAC in MP4 umgerechnet, ohne Metadaten, dazu ein
  Standbild. ffmpeg läuft mit niedriger Priorität (`nice -n 10`) und
  höchstens eine Stunde je Video. Die Aufgabe hat keinen Starter, der eine Benachrichtigung
  „fertig“ bekäme; misslingt das Verkleinern, wird das Video verworfen, die
  Nachricht sagt es, und wer es geschickt hat, bekommt eine
  Benachrichtigung.
- **Ein Video nach dem anderen.** Jedes Umrechnen braucht ein oder zwei
  Kerne und viel Speicher, bis zu einer Stunde lang; zehn Videos auf
  einmal würden den Server lahmlegen. Deshalb rechnet auf einem Server
  immer nur ein Prozess um: Er hält die Sperrdatei
  `/var/lib/rentalars/chat-videos.lock` (`DATA_DIR/chat-videos.lock`,
  `flock`) und arbeitet danach die wartenden Videos der Reihe nach ab;
  ein Video, das die Sperre nicht bekommt, bleibt als Aufgabe stehen, und
  die Nachricht zeigt entsprechend länger „Video wird verkleinert …“.
  Endet der Prozess – auch durch einen Absturz –, gibt das System die
  Sperre frei, und der Minuten-Zeitgeber (oben, „Aufgaben im
  Hintergrund“) nimmt die übrigen auf.
- **Wann ein Video als misslungen gilt:** Zeigt es nach drei Stunden noch
  „wird verkleinert“ und gibt es keine wartende oder laufende Aufgabe mehr
  dafür – etwa nach einem Neustart mitten in der Aufgabe –, gilt es als
  misslungen. Wartet seine Aufgabe noch in der Reihe oder läuft sie, erst
  nach 24 Stunden.

**Wo es liegt:**

| Was | Wo | In der Sicherung |
|---|---|---|
| Verkleinerte Fotos und Videos samt Vorschau | `/var/lib/rentalars/media/chat/<Projekt>/` (`MEDIA_ROOT/chat/…`), unter zufälligen Namen | ja, wie jede gespeicherte Datei; ebenso im lesbaren Export |
| Hochgeladene Videos, die auf das Verkleinern warten, und die Zwischendateien von ffmpeg | `/var/lib/rentalars/chat-videos/` (`DATA_DIR/chat-videos`) | nein |
| Sperrdatei: nur ein Video wird zugleich verkleinert | `/var/lib/rentalars/chat-videos.lock` (`DATA_DIR/chat-videos.lock`), leer | nein |

Das Original eines Videos löscht Rentalars, sobald die kleine Fassung
gespeichert ist oder das Verkleinern misslang. Was im Ordner
`chat-videos/` liegen bleibt, weil kein Video mehr darauf wartet – etwa
nach einem Absturz –, löscht Rentalars nach zwei Tagen, und zwar das
nächtliche Aufräumen (`run_daily_maintenance`, oben „Was von selbst
passiert“) und ebenso das nächste Hochladen eines Videos. Die leere
Sperrdatei bleibt liegen. Gelöschte Nachrichten nehmen ihre Dateien mit, auch wenn ein
ganzes Projekt gelöscht wird. Ausgeliefert werden die Dateien nur über
Rentalars, nachdem es geprüft hat, dass der Nutzer den Chat lesen darf.

**Platz und Rechenzeit.** Ein umgerechnetes Video hat höchstens rund
3 Mbit/s, also etwa 23 MB je Minute; während des Verkleinerns liegen
Original und Zwischendatei zusätzlich im Datenordner. Das Umrechnen kostet
Rechenzeit – auf einem Raspberry Pi braucht ein langes Video entsprechend
länger –; die niedrige Priorität hält die Seiten dabei schnell. Die Fotos
und Videos stecken in jeder nächtlichen Sicherung
([installation.md](installation.md), „Speicherplatz“).

### Schrift der Etiketten

Die Etiketten für Etikettendrucker druckt Rentalars in
**Liberation Sans** (Version 2.1.5, SIL Open Font License 1.1) – maßgleich
mit Arial, der Schrift der P-touch-Vorlagen. Die Schrift liegt Rentalars
bei (`static/fonts/LiberationSans-Regular.ttf` mit der Lizenz
`LiberationSans-OFL.txt`; aufgeführt in `THIRD-PARTY.md`); auf dem Server
muss dafür nichts installiert werden, und Browser wie PDF benutzen dieselbe
Datei – im Browser gedruckt und als PDF sehen die Etiketten gleich aus.

## Zertifikat

**Let's Encrypt über Port 80** (Auswahl 1 bei der Installation) und **mit
DNS-Zugangsdaten** (`--dns-plugin`): Es erneuert sich von selbst. Prüfen:

```sh
sudo certbot certificates          # zeigt das Ablaufdatum
sudo certbot renew --dry-run       # probt die Erneuerung
```

**Let's Encrypt mit von Hand angelegtem DNS-Eintrag** (Auswahl 2 ohne
`--dns-plugin`): Es gilt 90 Tage und erneuert sich **nicht** von selbst.
Trag dir einen Termin nach etwa 60 Tagen ein und wiederhole dann:

```sh
sudo certbot certonly --manual --preferred-challenges dns -d rentalars.example.de
sudo systemctl reload nginx
```

**Eigenes Zertifikat**: Ersetze `/etc/rentalars/tls/certificate.pem` und
`/etc/rentalars/tls/private-key.pem` und lade NGINX neu. Das geht
auch über Einstellungen → Serveradresse und Zertifikat: denselben
Hostnamen eintragen, „Eigenes Zertifikat“ wählen, das neue Zertifikat und
den Schlüssel hochladen und den angezeigten Befehl ausführen (unten). So
wechselst du auch die Art, etwa vom selbst erstellten Zertifikat zu Let's
Encrypt. Welches Zertifikat NGINX gerade zeigt und bis wann es gilt, steht
auf derselben Seite.

## Serveradresse und Zertifikat ändern

Ein Administrator bereitet eine neue Adresse im Browser vor –
**Einstellungen → Serveradresse und Zertifikat**, beschrieben im
[Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 16 –, und du
übernimmst sie auf dem Server mit genau dem einen Befehl, den die Seite
zeigt. Rentalars selbst bekommt dafür nie Root-Rechte und speichert keine
Zugangsdaten für root; was root braucht, tut dieser Befehl, den du per SSH
ausführst.

```sh
sudo rentalars address apply 3f2a9c…   --dry-run   # nur prüfen und den Plan zeigen
sudo rentalars address apply 3f2a9c…               # zeigen, nachfragen [j/N], übernehmen
sudo rentalars address apply 3f2a9c…   --yes       # ohne Nachfrage
```

**Was der Befehl tut,** in dieser Reihenfolge, und er sagt bei jedem
Schritt, was geschieht:

1. **Lesen und noch einmal prüfen.** Er holt die vorbereitete Änderung über
   `manage.py address_change export`, ausgeführt als Dienstkonto, und
   prüft alles selbst: Token, Schreibweise des Hostnamens, Art des
   Zertifikats, E-Mail-Adresse; bei einem eigenen Zertifikat mit openssl,
   ob der Schlüssel passt, jedes Glied der Kette, den Namen und die
   Gültigkeit zum jetzigen Zeitpunkt. Steht der alte Name nicht in der
   NGINX-Site, hört er hier auf, bevor er etwas ändert.
2. **Sichern** – Konfigurationsdatei, NGINX-Site und `/etc/rentalars/tls`
   nach `/etc/rentalars/address-backup/<Zeit>-<Token>/`.
3. **Das Zertifikat besorgen:** Let's Encrypt über certbot mit Prüfung über
   Port 80 (certbot wird installiert, wenn es fehlt), ein selbst
   erstelltes mit openssl (825 Tage, wie bei der Installation) oder das
   hochgeladene. Neue Zertifikate kommen nach
   `/etc/rentalars/tls/<Name>/`, der Schlüssel nur für root lesbar; alte
   Dateien werden nie überschrieben. Bei „Ein Server davor verschlüsselt“
   bleiben die Zertifikate, wie sie sind.
4. **Schreiben:** in der NGINX-Site nur die Zeilen `server_name`, die den
   alten Namen nennen, und die Zeilen des Zertifikats; in der
   Konfigurationsdatei `url` unter `[rentalars]` – daraus nimmt Rentalars
   auch die Namen, auf die es antwortet. Mit „Alte Adresse auf die neue
   weiterleiten“ kommt ans Ende der Site je alter Name ein Block, der
   weiterleitet: über HTTP immer (der Pfad für Let's Encrypt bleibt
   erreichbar, ein altes Zertifikat von Let's Encrypt erneuert sich also
   weiter), über HTTPS, solange das alte Zertifikat für den alten Namen
   gilt. Spätere Änderungen leiten alle früheren Namen auf den neuesten;
   kehrst du zu einem alten Namen zurück, fällt sein Block weg.
5. **Prüfen und neu starten:** `nginx -t`, NGINX neu laden, Rentalars neu
   starten; dann prüft er, dass Rentalars antwortet und dass `/login/`
   unter dem neuen Namen über HTTPS mit dem neuen Zertifikat antwortet.
6. **Zurück bei jedem Fehler:** Jede Datei kommt zurück, NGINX wird neu
   geladen, Rentalars neu gestartet, und er sagt, was schiefging.

Das Ergebnis vermerkt er über `manage.py address_change record`; die Seite
zeigt danach „Angewendet am … von …“ mit dem Namen aus `SUDO_USER` – oder
den Fehler. Eine fehlgeschlagene Änderung lässt sich nach dem Beheben noch
einmal ausführen. `--dry-run` zeigt den Plan samt den Unterschieden in der
NGINX-Site und vermerkt nichts. Läuft kein systemd (in einem Container oder
einer chroot-Umgebung), schreibt der Befehl die Dateien und prüft mit
`nginx -t`, lädt aber nichts neu und prüft nicht über HTTPS – und sagt das.

**Warum root nur liest, was das Dienstkonto ausgibt:** Der Befehl öffnet
keine Datei in den Ordnern des Dienstkontos; die vorbereitete Änderung
erreicht ihn nur als Ausgabe von `manage.py address_change export`. Ein
untergeschobener Verweis im Datenordner kann ihn so nicht auf andere
Dateien lenken. Hochgeladene Zertifikate und Schlüssel liegen bis dahin in
`<Datenordner>/address/<Token>/` (Ordner 0700, Dateien 0600, der
Schlüssel zusätzlich verschlüsselt wie andere gespeicherte Geheimnisse);
nach dem erfolgreichen Übernehmen oder wenn eine neuere Vorbereitung die
vorige ersetzt, werden sie gelöscht. Das Token gilt nur für diese eine
Änderung und fehlt im vollständigen Datenexport.

**Danach:** Jeder meldet sich unter der neuen Adresse neu an; Links in
neuen Mails nennen die neue Adresse. Kalender-Abos, gedruckte QR-Codes und
die Rentalars-App auf den Telefonen (unten, „Die Rentalars-App für
Android“) zeigen auf die alte, solange niemand sie ändert – sie
funktionieren, solange die alte Adresse weiterleitet. Für Let's Encrypt
muss Port 80 aus dem Internet erreichbar sein, wie bei der Installation.

**Was der Befehl nicht kann:**

- **Let's Encrypt mit DNS-Eintrag** (`install.sh --tls dns`) und ein anderer
  Port als 443 lassen sich im Browser nicht vorbereiten. Dafür geht der
  Weg von Hand (oben, „Die Adresse ändert sich“).
- **Eine Weiterleitung entfernen:** Den Block des alten Namens am Ende der
  NGINX-Site löschst du von Hand, dann `sudo nginx -t && sudo systemctl
  reload nginx`; ein altes Zertifikat von Let's Encrypt mit
  `sudo certbot delete --cert-name ALTER-NAME`.
- **`sudo rentalars nginx-site`** schreibt die Site aus der Vorlage neu und
  lässt dabei die Blöcke der Weiterleitung weg; es zeigt die Unterschiede,
  bevor es etwas tut.
- NGINX 1.24 kann beim Prüfen „protocol options redefined“ melden, weil
  die Blöcke der Weiterleitung `http2` nicht wiederholen. Das ist nur ein
  Hinweis; eine spätere Aktualisierung ergänzt es.

## KI

Rentalars fasst auf Wunsch die Korrespondenz eines Projekts
zusammen – mit einer **lokalen KI**: ein kleines Sprachmodell, das als
eigener Dienst auf diesem Server läuft. Die Mails verlassen den Server
nicht, und es kostet nichts je Aufruf, nur Arbeitsspeicher und Strom. Ob
Rentalars sie nutzt, schalten Administratoren unter **Einstellungen → KI**
ein; dort stehen auch die Schnittstellen zu anderen Sprachmodellen, die im
Browser eingetragen werden ([Benutzerhandbuch](../handbuch/benutzerhandbuch.md),
Abschnitt 16, „KI“). Ohne KI zeigt Rentalars einen Kurzüberblick der
Korrespondenz; nichts davon braucht den Server.

Die KI kann außerdem **Rechnungen lesen**: In „Kauf
einpflegen“ geht der Text einer hochgeladenen Einkaufsrechnung (nur PDFs
mit Text) an das Sprachmodell, das unter Einstellungen → KI für
„Rechnungen lesen“ gewählt ist – voreingestellt aus. Es schlägt Händler,
Rechnungsnummer, Datum und Positionen vor; die Antwort prüft Rentalars
streng (höchstens 100 Positionen, nur erwartete Felder) und legt nichts
an, bevor jemand jede Zeile bestätigt hat. Das Lesen läuft als Aufgabe im
Hintergrund (Art `ai_invoice`) und steht ohne Inhalt im Protokoll der
KI-Aufrufe. Mit der lokalen KI verlässt die Rechnung den Server nicht;
wählt jemand eine Schnittstelle im Internet, warnt die Seite rot, dass der
Text der Rechnung – Preise, eure Kundennummer, Anschriften – beim Lesen das
Unternehmen verlässt. Ohne KI nimmt Rentalars aus dem Text nur
Rechnungsnummer, Datum, einen bekannten Händler und die Summen
der Rechnung.

Die **Anfrage an die KI ist länger**: Sie nennt zusätzlich die
Kategorien, die ein gekauftes Modell bekommen kann (bis zu 150), und bis
zu 40 eigene Produkte – kein Kundenmaterial; bei mehr Produkten die, deren
Namen Wörter mit der Rechnung teilen –, als eigenen Datenblock, damit die
KI Kategorie und Produkt vorschlagen kann; außerdem fragt sie nach
Seriennummern und Summen. Die **Antwort darf bis 3.500 Token** lang sein.
Die beiden Listen nehmen höchstens ein Drittel des
Platzes, den der Kontext der KI nach Anweisung und Antwort lässt, der Text
der Rechnung den Rest. Bei der lokalen KI mit ihren 8.192 Token Kontext
(unten, „Modell und Ressourcen“) bleibt dadurch weniger Platz für eine
lange Rechnung; passt ihr Ende nicht mehr hinein, sagt der Vorschlag es
(„Die Rechnung ist zu lang: Ihr Ende wurde nicht gelesen. Trag die letzten
Positionen von Hand ein.“). Über eine Schnittstelle im Internet
gehen mit der Rechnung auch die Namen der Kategorien und dieser Produkte
hinaus. Beträge schreibt die KI so ab, wie sie auf der Rechnung stehen;
Rentalars liest sie selbst und gleicht sie mit dem Text der Rechnung ab.

Die Einstellung „Rechnungen lesen“ gilt auch für die
**Eingangsrechnungen** und den **Import von Altprojekten** (unten, „Eingangsrechnungen
und ihre Dateien“ und „Altprojekte importieren“), und die KI kann Projekte
und Servicefälle **nachts von selbst zusammenfassen** (unten, „Automatische
KI-Zusammenfassungen“, mit Hinweisen zum Datenschutz und zur
Informationssicherheit).

### Einrichten

```sh
sudo rentalars ai install --dry-run    # zeigen, was geschähe – auch ohne root
sudo rentalars ai install              # einrichten
```

Dann im Browser: Einstellungen → KI → „Zusammenfassungen mit lokaler KI
einschalten“, und mit „Geschwindigkeit messen“ prüfen, wie schnell sie
antwortet. Ein Neustart von Rentalars ist nicht nötig.

Der Befehl

1. prüft das System (Ubuntu 24.04 oder 26.04, Raspberry Pi OS auf Basis von
   Debian 13; 64 Bit), den Arbeitsspeicher und den freien Platz;
2. prüft den Prozessor: physische und logische Kerne und – auf
   x86-64 – ob **AVX2** und **FMA** da sind (unten, „Prozessor und
   virtuelle Maschinen“);
3. wählt das Modell nach Arbeitsspeicher, physischen Kernen und Prozessor
   (unten);
4. installiert `llama-server` aus llama.cpp – auf Ubuntu 26.04 aus dem
   Paket `llama.cpp-tools`, auf Ubuntu 24.04 und Raspberry Pi OS aus dem
   Quelltext: Er holt genau die Version b8681, prüft ihren Commit und baut
   sie mit cmake (dafür installiert er `git`, `cmake` und
   `build-essential`; auf einem Raspberry Pi dauert das 15 bis 40 Minuten).
   Ein schon gebauter `llama-server` bleibt; `--rebuild` baut ihn neu;
5. lädt das Modell herunter und prüft seine SHA-256-Prüfsumme; ein vorher
   genutztes Modell löscht er, sobald das neue antwortet;
6. startet es als Dienst `rentalars-ai`, nur auf 127.0.0.1 erreichbar
   (Port 8093), mit **einem Thread je physischem Kern** und abgeschaltetem
   Nachdenken des Modells (`--reasoning off --reasoning-budget 0`, wenn
   `llama-server --help` sie nennt);
7. schreibt nach `/etc/rentalars/ai-local.conf`, wo die lokale KI zu
   erreichen ist, und schickt eine Testfrage, die Lese- und
   Schreibgeschwindigkeit misst. Rentalars liest die Datei bei jeder
   Nutzung.

Optionen: `--model qwen3-1.7b`, `--model qwen3-4b`, `--model qwen2.5-1.5b`
(das kleine Modell) oder `--model DATEI.gguf` (ein Modell, das
schon auf dem Server liegt – etwa ohne Internet; dazu auf Wunsch `--sha256
PRÜFSUMME`), `--port N`, `--threads N`, `--keep-model` (das bisherige
Modell nach einem Wechsel behalten), `--rebuild` (llama.cpp neu bauen,
etwa nachdem der Prozessortyp einer virtuellen Maschine auf „host“ gestellt
wurde; nur, wo er aus dem Quelltext gebaut ist).

**Modell wechseln:** `sudo rentalars ai install --model qwen3-1.7b` (oder
`qwen3-4b`). Ein schon gebauter `llama-server` wird dabei nicht neu gebaut;
das bisherige Modell wird gelöscht, sobald das neue antwortet, außer mit
`--keep-model`. Danach im Browser „Geschwindigkeit messen“.

**Ein eigener Server** wie Ollama oder LM Studio, der schon auf diesem
Rechner läuft, wird mit `sudo rentalars ai register --url
http://127.0.0.1:PORT/v1 --model NAME` zur lokalen KI; die Adresse muss auf
diesem Rechner liegen.

```sh
sudo rentalars ai status               # Modell, Server, Prozessor, Threads, Optionen, ob er antwortet
sudo rentalars ai refresh              # Einstellungen der neuen Version übernehmen (macht das Update selbst)
sudo rentalars ai remove               # Dienst, Programm, Modelle entfernen
sudo rentalars ai remove --keep-model  # die Modelle behalten
```

`remove` hält den Dienst an, entfernt seine Dateien und die Pakete, die
`install` selbst installiert hat; die Werkzeuge zum Bauen bleiben.
Rentalars fasst danach nicht mehr mit der lokalen KI zusammen, der
Kurzüberblick bleibt.

### Nach einem Update: `ai refresh`

Das Update übernimmt die Einstellungen der lokalen KI selbst (`sudo
rentalars ai refresh`; zusätzlich etwa eine Minute nach jedem Start des
Servers). Neu installieren musst du sie nach einem Update nicht.

- **Was `refresh` tut:** Nur für eine lokale KI, die `ai install` hier
  eingerichtet hat (bei `ai register` oder ohne KI tut es nichts). Es liest
  den Prozessor neu und schreibt `ai-local.env` und die Grenzen des
  Dienstes neu: Threads je physischem Kern, die Optionen, die `llama-server
  --help` nennt (`--reasoning off --reasoning-budget 0 --jinja
  --no-webui`), `MemoryMax` des Modells; in `ai-local.conf` ergänzt es
  `server_kind`, `physical_cores` und `threads`. `rentalars-ai` startet es
  nur neu, wenn sich etwas geändert hat, und wartet bis zu 120 Sekunden auf
  die Antwort. Es meldet eine Zeile – „Lokale KI: Einstellungen übernommen
  (Nachdenken aus, 4 Threads).“ oder „Lokale KI: unverändert.“ –;
  `--dry-run` zeigt nur, was es täte.
- **Was es nie tut:** herunterladen, bauen, Pakete installieren oder das
  Modell wechseln. Das Modell wechselt nie von allein (große Datei);
  passt ein anderes besser, nennt `refresh` nur den Befehl (`sudo rentalars
  ai install --model …`). Ohne AVX2/FMA nennt es den Hinweis auf den
  Prozessortyp „host“; hat ein selbst gebauter `llama-server` kein AVX2,
  das der Prozessor hat, den Hinweis `sudo rentalars ai install
  --rebuild`.
- **Fehler** brechen das Update nie ab: `refresh` warnt und endet mit 0.
  Eine Sperre verhindert, dass Update und Zeitgeber es gleichzeitig
  ausführen.
- **Wer es startet:** `rentalars update` nach jedem erfolgreichen Update
  (nicht beim Zurückgehen), und `rentalars-ai-refresh.timer` etwa eine
  Minute nach jedem Start des Servers und nachdem ein Update die Zeitgeber
  der neuen Version eingeschaltet hat. So greift es auch,
  nachdem der Prozessortyp einer virtuellen Maschine geändert wurde. Der
  Dienst `rentalars-ai-refresh.service` läuft wie die Sicherung als root
  und nur, wenn `/etc/rentalars/ai-local.env` existiert; er führt
  `deploy/ai.sh refresh` aus dem Programmverzeichnis aus. Rentalars selbst
  bekommt dabei keine Root-Rechte.
- **llama-server selbst:** Auf Ubuntu 26.04 kommt er aus dem Ubuntu-Paket
  und wird mit den normalen Systemupdates aktualisiert; auf 24.04 und
  Raspberry Pi OS wird er nur neu gebaut, wenn du es sagst (`sudo
  rentalars ai install --rebuild`, z. B. nachdem der Prozessortyp einer
  virtuellen Maschine auf „host“ gestellt wurde).

### Modell und Ressourcen

Alle Modelle sind von Qwen (Alibaba Cloud), Lizenz Apache 2.0, die auch
die gewerbliche Nutzung erlaubt, und können Deutsch und Englisch. Sie sind
auf vier Bit verkleinert (Q4_K_M) und verstehen bis zu 8.192 Token auf
einmal; längere Korrespondenz fasst Rentalars in Teilen zusammen und dann
die Teile. Qwen3 1.7B ist die Umwandlung des llama.cpp-Projekts
(ggml-org), weil Qwen selbst diese Größe nur als Q8_0 anbietet.

`ai install` wählt das Modell nach Arbeitsspeicher, physischen
Kernen und Prozessor:

| Server | Modell (Datei) | Speichergrenze des Dienstes (`MemoryMax`) |
|---|---|---|
| unter 1,5 GB Arbeitsspeicher | – der Befehl lehnt ab | – |
| ab 6 GB, mindestens vier physische Kerne und AVX2/FMA (oder ein 64-Bit-ARM-Server, der kein Raspberry Pi ist) | Qwen3 4B (2,4 GB) | 5 GB |
| alle anderen – etwa jeder Raspberry Pi, eine virtuelle Maschine ohne AVX2/FMA | Qwen3 1.7B (1,3 GB) | 3 GB |
| nur auf Wunsch (`--model qwen2.5-1.5b`, das kleine Modell) | Qwen2.5 1.5B Instruct (1,1 GB) | 2 GB |

Eine bestehende Installation behält ihr Modell; wechseln geht mit
`--model` (oben).

- **Prozessor:** Der Dienst nutzt **einen Thread je physischem
  Kern** (höchstens 16; ein zweiter Thread auf demselben Kern macht ihn
  nicht schneller) und
  ist mit `CPUQuota` darauf begrenzt. Er läuft mit niedrigerer Priorität
  (`Nice=10`, geringes Gewicht für Prozessor und Platte); Rentalars und die
  Datenbank gehen vor. Während einer Zusammenfassung sind die Kerne
  trotzdem gut ausgelastet, und auf einem Raspberry Pi reagieren die
  Seiten dann etwas langsamer.
- **Prozessor und virtuelle Maschinen:** Auf x86-64 ist das Modell nur mit
  den Befehlen **AVX2** und **FMA** schnell; ohne sie läuft es um ein
  Vielfaches langsamer. Eine virtuelle Maschine verbirgt sie oft: Proxmox
  gibt neuen Maschinen den Prozessortyp „x86-64-v2-AES“ (früher „kvm64“),
  der keines von beiden hat. Abhilfe: in Proxmox unter Hardware →
  Prozessoren den Typ **„host“** wählen – oder **„x86-64-v3“**, wenn die
  Maschine zwischen Rechnern eines Clusters wandern soll – und die
  Maschine in Proxmox **herunterfahren und wieder starten** (ein Neustart
  in der Maschine reicht nicht). Prüfen in der Maschine:
  `grep -o -w 'avx2\|fma' /proc/cpuinfo | sort | uniq -c` – je ein
  Treffer pro Kern der Maschine; kommt nichts, fehlen sie. `ai install`,
  `ai status` und Einstellungen → KI warnen, wenn sie fehlen.
- **Arbeitsspeicher:** Der Dienst hält das Modell im Speicher, solange er
  läuft. `MemoryMax` steht in
  `/etc/systemd/system/rentalars-ai.service.d/` und begrenzt ihn; für ein
  eigenes Modell setzt der Befehl das Doppelte der Datei plus 2 GB.
  Rechne mit dem Rest für Rentalars, MariaDB und das System: Auf einem Pi
  mit 4 GB bleiben etwa 2 GB, auf einem mit 8 GB etwa 3 GB. Wird es eng,
  nimm ein kleineres Modell (`--model qwen3-1.7b`, zur Not
  `--model qwen2.5-1.5b`).
- **Platte:** das Modell plus 300 MB, beim Bauen aus dem Quelltext plus
  1,5 GB, unter `/opt/rentalars/ai`.
- **Geschwindigkeit:** „Geschwindigkeit messen“ unter Einstellungen → KI
  misst getrennt, wie schnell die KI liest (die Mails) und
  schreibt (die Antwort), in Token je Sekunde; jeder spätere Aufruf hält
  die Werte aktuell. Daraus schätzt Rentalars vor jeder Zusammenfassung die
  Dauer und warnt ab fünf Minuten. Unter 6 Token je Sekunde beim Schreiben
  oder 30 beim Lesen – oder ohne AVX2/FMA – empfiehlt die Seite das
  kleinere Modell Qwen3 1.7B mit dem Befehl zum Kopieren. Die Antworten
  kommen gestreamt: Abgebrochen wird erst nach 180 Sekunden ohne ein Wort
  (vor dem ersten Wort nach der dreifachen geschätzten Lesezeit plus 60
  Sekunden, ohne Messung nach 30 Minuten); die ganze Aufgabe endet
  spätestens beim Dreifachen ihrer Schätzung (mindestens 10 Minuten, ohne
  Messung 3 Stunden). Auf einem Raspberry Pi dauert eine Zusammenfassung
  einige Minuten, auf einem Server mit x86 und AVX2 deutlich weniger
  (siehe [aktualisierung.md](aktualisierung.md), „Erprobung“).

### Automatische KI-Zusammenfassungen

Rentalars kann (EML-056) die Korrespondenz von Projekten und
Servicefällen nachts von selbst zusammenfassen, damit am Morgen die
Zusammenfassung zu den neuen Mails schon da ist. Die Funktion ist **aus**,
bis ein Administrator unter **Einstellungen → KI → Automatische
Zusammenfassungen → Öffnen** (`/administration/ai/automatic/`) zustimmt. Sie nutzt denselben Weg und denselben
Anbieter wie der Knopf „Zusammenfassen“ am Projekt (Einstellungen → KI,
Anwendungsfall „Zusammenfassung“).

**Wie sie läuft**

- Der Zeitgeber, der jede Minute `run_jobs` startet (`rentalars-jobs.timer`),
  prüft, ob es Nacht im Zeitfenster ist (voreingestellt 01:00 bis 05:00 Uhr,
  Ortszeit), ob diese Nacht schon gelaufen ist und ob die Funktion an ist; eine
  Minute ohne fälligen Lauf kostet eine Datenbankabfrage. Ist alles erfüllt, startet er
  die Aufgabe `ai_auto_summaries` (Art, wie in „Aufgaben im Hintergrund“) als
  eigenen Prozess; ein Schloss in der Datenbank sorgt dafür, dass nie zwei Läufe zugleich
  arbeiten. **Es gibt keinen neuen Zeitgeber und keinen neuen Dienst.**
- Zusammengefasst wird ein Projekt oder Servicefall, dessen lesbare
  Korrespondenz (Mails, Notizen, und wenn erlaubt der Chat) sich seit der
  letzten Zusammenfassung **geändert** hat. Verglichen wird eine Prüfsumme
  der Eingabe, keine Uhrzeit: Ohne Änderung gibt es keinen Aufruf des Modells,
  also keine Kosten. Eine von Hand erstellte Zusammenfassung überschreibt
  der Lauf nie unmarkiert; frühere Fassungen bleiben (voreingestellt 5).
- Die Zusammenfassung trägt „automatisch erstellt“, Modell, Anbieter und
  Zeitpunkt. Am Projekt steht außerdem ein Hinweis, wenn danach neue Mails
  kamen, und „Erneut zusammenfassen“. Sie ist für alle sichtbar, die alle
  Nachrichten des Projekts lesen dürfen.
- Fehler halten den Lauf nicht an: Scheitert eine einzelne Zusammenfassung,
  kommt das Projekt in der nächsten Nacht wieder an die Reihe. Ist der
  Anbieter gar nicht erreichbar (oder scheitert jede Zusammenfassung),
  versucht es der Zeitgeber nach 20 Minuten noch einmal, höchstens dreimal
  in der Nacht. Administratoren sehen die Läufe und Fehler auf der Seite der
  automatischen Zusammenfassungen; Benachrichtigungen gibt es dafür nicht.

**Einstellungen** (Einstellungen → KI → Automatische Zusammenfassungen):

| Einstellung | Voreinstellung |
|---|---|
| Automatische Zusammenfassungen | aus; die Zustimmung gilt für den **Server**, an den die Texte gehen (die lokale KI, oder Schema, Host und Port des Anbieters) – wechselt er, muss ein Administrator neu zustimmen; ein anderer Modell- oder Anzeigename ändert nichts |
| Zeitfenster | 01:00 bis 05:00 Uhr |
| Höchstens Zusammenfassungen je Nacht | 20 |
| **Token-Budget je Nacht** (gelesene und geschriebene Token; 0 = unbegrenzt) | 200.000 – der Lauf hört auf, wenn es erreicht ist |
| Status der Projekte | offene: Anfrage, Option, bestätigt (offen), bestätigt, draußen, zurück |
| Status der Servicefälle | offen, in Arbeit, wartet, Abschluss |
| Mindestabstand zwischen zwei Zusammenfassungen | 20 Stunden |
| Mindestzahl Mails | 2 |
| Frühere Fassungen aufbewahren | 5 |
| Einbeziehen: Notizen / Chat / Nachrichten mit Sperre | Notizen **an**, Chat **aus**, Nachrichten mit Sperre **an** (`auto_include_locked`) |
| Ausschluss | je Projekt und je Kunde: Knöpfe „Keine automatischen Zusammenfassungen für dieses Projekt“ und „… für kein Projekt dieses Kunden“ unter der Zusammenfassung |
| „Zeigen, was zusammengefasst würde“ | Trockenlauf: keine Anfrage an das Modell, nichts gespeichert |

Der Lauf arbeitet unter dem Dienstkonto `system:ai-summaries` mit dem
kleinsten nötigen Umfang: Mails und Notizen; Chat und Preise nur nach
Freigabe. Nachrichten mit Sperre (dem Schloss der Korrespondenz, EML-055) liest er
voreingestellt mit, weil in Projekten jede Nachricht mit Schloss beginnt und der Lauf sonst fast nichts
läse; die Zusammenfassung sehen nur die, die alle Nachrichten lesen dürfen.
Wer das nicht will, schaltet den Schalter aus.

**Von Hand und zum Ausprobieren**

```sh
sudo rentalars ai_summaries --dry-run        # listet, was zusammengefasst würde; ruft kein Modell auf
sudo rentalars ai_summaries --project 42     # nur dieses Projekt (Nummer)
sudo rentalars ai_summaries --limit 5        # höchstens fünf
sudo rentalars ai_summaries                  # jetzt laufen lassen (die Zustimmung wird gebraucht)
sudo rentalars ai_summaries --only-in-window # nichts tun außerhalb des Zeitfensters
```

Ohne Zustimmung und bei einem Lauf, der schon läuft, sagt der Befehl „Nothing
done: the automatic summaries are off, or another run is under way.“ Auf
der Seite gibt es denselben Lauf als „Jetzt ausführen“. Das Ergebnis jedes
Laufs steht auf der Seite und, als Aufgabe im Hintergrund, im Protokoll
(`sudo journalctl -u rentalars-jobs -n 30`).

**Kosten und Dauer.** Mit der lokalen KI kostet ein Lauf nur Rechenzeit, und
die ist je nach Rechner groß (Einstellungen → KI → „Geschwindigkeit messen“
zeigt, wie schnell sie ist). Setze Fenster und Höchstzahl so, dass der Lauf
vor Arbeitsbeginn fertig ist. Mit einem Anbieter im Internet bestimmt das
Token-Budget die Kosten je Nacht – rechne mit dem Preis des Anbieters nach.
Auf der Projektseite braucht die Anzeige 2 bis 3 Abfragen mehr.

#### Datenschutz und Auftragsverarbeitung

- **Mit der lokalen KI** (`sudo rentalars ai install`) verlässt nichts den
  Server.
- **Mit einem Anbieter im Internet** gehen Mails und Notizen des Projekts
  an ein anderes Unternehmen. Das sind personenbezogene Daten Dritter
  (Kunden, Ansprechpartner, Crew). Dafür braucht ihr in der Regel einen
  **Vertrag zur Auftragsverarbeitung** nach Art. 28 DSGVO mit dem
  Anbieter, die Klärung, **wo** er verarbeitet (Drittlandübermittlung) und
  ob er die Daten zum Training verwendet, einen Eintrag im Verzeichnis der
  Verarbeitungstätigkeiten und gegebenenfalls einen Hinweis in der
  Datenschutzerklärung. Das klärt ihr selbst, am besten mit eurer
  Datenschutzbeauftragten oder eurem Datenschutzbeauftragten – Rentalars
  ersetzt das nicht, und dieser Abschnitt ist keine Rechtsberatung.
- **Was vor dem Senden entfernt wird** (Einstellungen → KI, „aus den Texten
  entfernt“, je Datenklasse): IBAN, Kartennummern, Zugangsdaten und Schlüssel
  (z. B. Passwörter, Token), E-Mail-Adressen und Telefonnummern. Das ist
  voreingestellt an. **Was nicht entfernt wird:** Namen und Anschriften im
  Fließtext – sie lassen sich nicht zuverlässig erkennen und gehen mit, wenn
  ein Anbieter im Internet eingeschaltet ist. Die Namen angehängter Dateien
  gehen auf Wunsch mit („Namen angehängter Dateien“, voreingestellt an).
- **Zustimmung:** Der Administrator bestätigt beim Einschalten, an welchen
  Server welche Daten gehen. Wechselt der Server (lokal, oder Schema, Host und
  Port des Anbieters), endet die Zustimmung, bis sie erneuert ist.
- **Kunden und Projekte ausnehmen:** Einzelne Projekte oder Kunden lassen
  sich ausschließen (z. B. besonders vertrauliche).
- **Auskunft und Löschung:** Der Export der Daten eines Kunden und seine
  Anonymisierung erfassen die Zusammenfassungen und ihre früheren Fassungen.
  Das Protokoll der KI-Aufrufe enthält nie Inhalte, nur Anwendungsfall,
  Modell, Dauer, Umfang und Zählwerte; die Einträge bleiben 365 Tage.

#### Informationssicherheit

Der Weg zum KI-Anbieter wurde geprüft (NFA-079). **Behoben und eingebaut:**

- **Datensparsamkeit:** Datenklassen werden vor dem Senden entfernt (oben) –
  auf allen Wegen: Zusammenfassung von Hand, nachts und Antwortentwurf.
- **Dienstkonto mit kleinstem Umfang:** Der Nachtlauf liest Mails und Notizen;
  Chat und Preise nur, wenn ein Administrator es freigibt.
- **Eingeschleuste Anweisungen** (Prompt-Injection): Texte aus Mails sind nicht
  vertrauenswürdig. Begrenzer, Sondertoken und unsichtbare Zeichen werden
  entschärft, die Anweisung an das Modell bleibt vom Text getrennt, und die
  Antwort des Modells löst nie eine Handlung aus (sie ist nur Text).
- **Die Antwort** wird zu reinem Text bereinigt und beim Anzeigen maskiert:
  kein HTML, keine Bilder, keine Links.
- **Grenzen:** Handaufrufe sind je Nutzer und Stunde begrenzt (Einstellung
  „Zusammenfassungen von Hand je Nutzer und Stunde“, voreingestellt 30), der
  Nachtlauf hat das Token-Budget und die Höchstzahl; die Länge der Eingabe
  (150.000 Zeichen, die ältesten Mails entfallen) und der Antwort ist
  begrenzt.
- **Verbindung:** Anbieter im Internet nur mit `https://` (`http://` wird
  beim Speichern abgelehnt), keine Weiterleitungen, kein Zugriff auf Adressen
  im eigenen Netz ohne `[network] allow_internal` (oben, „Verbindungen ins
  interne Netz“). Der API-Schlüssel steht verschlüsselt in der Datenbank und
  weder in einem Protokoll noch in einer Fehlerseite.
- **Nachvollziehbar:** Wer was ausgelöst hat, steht im Protokoll – mit
  Zählwerten statt Inhalten; Antwortentwürfe nutzen dieselben gefilterten
  Texte.

**Offene Punkte – so lange tragt ihr sie mit:**

- **Keine Positivliste der Anbieter-Server je Betreiber.** Ein Administrator
  kann eine beliebige `https://`-Adresse als Anbieter eintragen. Dagegen
  hilft nur die Firewall des Servers: Erlaube ausgehend nur die Adresse des
  Anbieters, den ihr gewählt habt. (Eine Einstellung `[ai] allowed_hosts`
  gibt es nicht.)
- **Namen und Anschriften im Fließtext** gehen an den Anbieter, wenn er
  eingeschaltet ist (nicht lösbar).
- **Bearbeitete oder gelöschte Chatnachrichten** machen eine Zusammenfassung
  nicht „veraltet“. (Ist der Chat einbezogen, tut es eine neue Chatnachricht.)
- **Fehler und Erfindungen der Modelle** sind nicht ausschließbar. Die
  Oberfläche weist darauf hin; eine Zusammenfassung ersetzt nicht das Lesen
  der Mails.
- **Fehlertexte des Anbieters** können in den Fehlermeldungen des Auftrags
  stehen (`journalctl`), nicht im Protokoll der KI-Aufrufe.
- **Nachrichten mit Sperre (Schloss)** liest der Nachtlauf voreingestellt mit (oben).
- **Nicht geprüft:** ein echter Anbieter im Internet, die Sperrspalte der
  Läufe unter MariaDB und der Zeitgeber von systemd; getestet ist mit einem
  nachgestellten Modell.

### Was wo liegt

| Was | Wo |
|---|---|
| Programm, Modelle, Quelltext | `/opt/rentalars/ai/` (`bin/`, `models/`, `src/`) |
| Für Rentalars: Adresse, Modell, Art des Servers, physische Kerne, Threads, womit `llama-server` gebaut ist (`built_with`) | `/etc/rentalars/ai-local.conf` (root, lesbar für alle; nur Adressen auf diesem Rechner werden angenommen) |
| Für den Dienst: Modell, Port, Threads, Optionen | `/etc/rentalars/ai-local.env` |
| Der Dienst | `rentalars-ai.service`, Grenzen in `rentalars-ai.service.d/` |
| Einstellungen nach Update und Start übernehmen | `rentalars-ai-refresh.service` und `rentalars-ai-refresh.timer` |
| Protokoll des Dienstes | `sudo journalctl -u rentalars-ai -n 50`, für `refresh`: `sudo journalctl -u rentalars-ai-refresh` |

Die Dienstdatei kommt mit jeder Version; ohne `ai-local.env` und ohne
`llama-server` startet der Dienst nicht. Er läuft unter einem eigenen
Benutzer ohne Rechte (`DynamicUser`), liest das Modell nur, schreibt nirgends
hin und erreicht nichts außer diesem Rechner.

**Sicherung:** Programm und Modelle stecken **nicht** in der Sicherung,
ebenso wenig `ai-local.conf` und `ai-local.env` ([sicherung.md](sicherung.md)).
Was im Browser eingestellt ist – eingeschaltet oder nicht, die
Schnittstellen samt verschlüsseltem API-Schlüssel, Zusammenfassungen und
Protokoll –, liegt in der Datenbank und kommt mit ihr zurück. Nach dem
Wiederherstellen auf einem neuen Server richtest du die lokale KI mit
`sudo rentalars ai install` neu ein.

**Schnittstellen aus dem Browser** (OpenAI-kompatibel, etwa Ollama im
Firmennetz oder ein Cloud-Dienst) prüft Rentalars wie Kalender und
Webhooks: Eine Adresse im internen Netz – auch eine auf diesem Rechner –
geht nur mit Freigabe unter `[network] allow_internal` (oben,
„Verbindungen ins interne Netz“); Weiterleitungen folgt es nicht. Für eine
Schnittstelle im Internet nimmt Rentalars nur eine
Adresse mit `https://` an: `http://` lehnt schon das Speichern ab, weil Mails
und Schlüssel sonst unverschlüsselt hinausgingen. Nur die
lokale KI aus `ai-local.conf` braucht keine Freigabe, weil der Betreiber
sie eingerichtet hat. Bei einem Cloud-Dienst gehen Mails – und, wenn
„Rechnungen lesen“ ihn nutzt, der Text von Einkaufsrechnungen – an dessen
Anbieter; die Seite warnt davor. Jeder Aufruf steht im Protokoll der
KI-Aufrufe (Einstellungen → KI) – mit Anwendungsfall, Modell, Dauer und
Umfang, nie mit Inhalt; die Einträge bleiben 365 Tage.

## Anmeldung mit dem Verzeichnis (LDAP)

Nutzer können sich (AUT-029) mit Name und Passwort ihres
Verzeichnisses anmelden – Active Directory oder ein LDAP-Server wie
OpenLDAP. Rentalars fragt das Verzeichnis bei jeder Anmeldung; das Passwort
des Verzeichnisses wird in Rentalars nie gespeichert. Die Funktion ist
**aus**, bis ein Administrator sie unter **Einstellungen → Verzeichnis
(LDAP)** (`/administration/ldap/`) einschaltet; bis dahin ändert sich
nichts. Konten, die das Verzeichnis anlegt, bekommen ihre Rollen aus den
Gruppen des Verzeichnisses (Benutzerhandbuch, Abschnitt zum Verzeichnis).

**Erprobt ist** die Anmeldung mit einem nachgestellten Verzeichnis (der
`MOCK_SYNC`-Betrieb der Bibliothek ldap3) und mit einem echten, lokal
laufenden OpenLDAP (`slapd`; der Test ist wahlfrei, `RENTALARS_SLAPD=1`).
**Nicht erprobt** ist sie gegen ein Active Directory – die Beispiele dafür
unten sind aus der Dokumentation von AD zusammengestellt. Probiere sie mit
„Anmeldung für einen Nutzer testen“ aus, ehe du die Funktion einschaltest.

### Was der Server braucht

- **Die Bibliotheken `ldap3` und `pyasn1`** kommen mit der Installation und
  mit jeder Aktualisierung; du installierst nichts.
- **Eine Verbindung** vom Rentalars-Server zum Verzeichnis: Port 636 (`ldaps://`)
  oder 389 (`ldap://`, mit StartTLS). `ldap://` **ohne** StartTLS schickt
  Passwörter im Klartext: Seite, API und Verbindungstest warnen davor. Die
  Firewall dazwischen muss sie zulassen. Prüfe sie vom Server aus, ehe du im Browser einträgst:

  ```sh
  openssl s_client -connect dc1.example.com:636 -servername dc1.example.com </dev/null | head -20
  ldapsearch -x -H ldaps://dc1.example.com -D "CN=svc-rentalars,OU=Service,DC=example,DC=com" -W \
      -b "OU=Staff,DC=example,DC=com" "(sAMAccountName=anna)" dn memberOf
  ```

  (`ldapsearch` steckt im Paket `ldap-utils`; Rentalars braucht es nicht.)
- **Den Server mit seinem Namen, nicht mit der IP-Adresse.** Die
  Bibliothek vergleicht den Namen des Zertifikats nur mit dessen
  DNS-Einträgen; gegen eine IP-Adresse scheitert die Prüfung des Zertifikats
  („TLS“, unten). Trage deshalb `ldaps://dc1.example.com` ein, nie
  `ldaps://10.0.0.5`.
- **Interne Server freigeben.** Das Verzeichnis liegt fast immer im
  eigenen Netz. Wie Kalender, Webhooks und Mailserver verbindet sich
  Rentalars nicht mit Adressen im internen Netz, solange der Betreiber sie
  nicht freigibt (oben, „Verbindungen ins interne Netz“). In
  `/etc/rentalars/rentalars.conf`:

  ```ini
  [network]
  allow_internal = dc1.example.com, dc2.example.com
  ```

  Ein Hostname gibt Verbindungen zu genau diesem Namen frei, in welche
  Adresse er sich auch auflöst; ein Netz (`10.0.0.0/24`) gibt alle Adressen
  darin frei. Danach `sudo systemctl restart rentalars`. Ohne die
  Freigabe lehnt schon das Formular die Adresse ab oder die Verbindung
  scheitert mit „blocked“.
- **Ein Suchkonto** im Verzeichnis, das Nutzer und ihre Gruppen lesen darf
  (kein Administrator nötig). Sein Passwort speichert Rentalars verschlüsselt
  mit dem `secret_key` der Konfigurationsdatei und zeigt es nie wieder; ein
  anderer `secret_key` macht es unlesbar (dann neu eingeben). Ändern sich
  Server oder DN des Suchkontos, verwirft Rentalars das Passwort.
- **Das Zertifikat des Verzeichnisses:** Liegt die Zertifizierungsstelle
  eurer Firma nicht im System, trägst du den Pfad der Datei auf dem Server
  ein (`/etc/ssl/certs/firma-ca.pem`) oder fügst das Zertifikat (PEM) im
  Formular ein. **Der Pfad (`ca_certificate_path`) muss absolut sein und eine
  lesbare Datei im PEM-Format nennen**, die der Dienst `rentalars` lesen darf;
  sonst lehnt die Seite ihn ab („Diese Datei gibt es auf dem Server nicht“,
  „Das ist keine Datei, die Rentalars lesen kann“, „Die Datei enthält kein
  Zertifikat im PEM-Format“). Ein eingefügtes Zertifikat muss ebenfalls PEM
  sein. Die Prüfung des Zertifikats ist eingeschaltet; schalte sie nur für
  einen Test aus.

### Einrichten

1. **Zuerst den Notzugang:** Öffne einen Administrator unter Einstellungen →
   Nutzer und setze „lokales (Notfall-)Konto“. Dieses Konto meldet sich
   immer mit seinem Passwort von Rentalars an, das Verzeichnis fragt es nie
   und ändert nichts an ihm. Es ist der Weg hinein, wenn das Verzeichnis
   ausfällt oder die Einstellungen falsch sind. Rentalars lässt die lokale
   Anmeldung nur abschalten, wenn es ein solches Konto gibt.
2. **Einstellungen → Verzeichnis (LDAP):** Server (ein Eintrag je Zeile;
   mehrere werden nacheinander versucht), StartTLS, Zertifikat, Suchkonto
   (DN und Passwort), Suchbasis und Filter für Nutzer, die Attribute, die
   Gruppensuche, Zeitgrenze (voreingestellt 8 Sekunden). **„Bestehende Konten
   über den Namen verknüpfen“ lässt du aus** (siehe „Was dann geschieht“).
   Noch nicht einschalten.
3. **„Verbindung testen“.** Es meldet, ob der Server antwortet, die
   Verschlüsselung klappt und das Suchkonto sich anmelden kann.
4. **Gruppen und Rollen:** Ordne in der Tabelle der Gruppe (DN) eine oder
   mehrere Rollen zu, mit Priorität; „letzter Treffer“ beendet die Auswertung
   bei dieser Zeile. **Nimm den vollständigen DN** der Gruppe, höchstens **480
   Zeichen** (länger lehnt die Seite ab; die Grenze gilt für den verglichenen
   Schlüssel mit seinem Präfix, damit er in die Spalte passt, die MariaDB
   eindeutig halten muss). Ein bloßer Name (`admins`) passt auf eine Gruppe
   dieses Namens **irgendwo** im Verzeichnis, auch dort, wo andere schreiben
   dürfen; die Seite warnt (in der API `name_only` und `warning`). Bestehende
   Zuordnungen mit Namen laufen weiter.
5. **„Anmeldung für einen Nutzer testen“** (ein Probelauf ohne Wirkung): Du
   gibst einen Anmeldenamen ein (und, wenn du sie prüfen willst, das
   Passwort) und siehst den gefundenen DN, die gelesenen Attribute, die
   Gruppen und die Rollen, die daraus entstünden. Das ist das Werkzeug gegen
   „ich komme nicht hinein“.
6. **Einschalten.** Wer sich nun anmeldet, wird zuerst im Verzeichnis
   gefragt. Lass die „Anmeldung mit lokalem Passwort“ zunächst erlaubt;
   schalte sie erst ab, wenn alle über das Verzeichnis hineinkommen.

### Was dann geschieht

- **Rollen** aus mehreren Gruppen werden vereinigt und folgen den Gruppen
  bei **jeder Anmeldung**. Eine Rolle, die das Verzeichnis gibt, lässt sich
  in Rentalars nicht von Hand entfernen; Rollen, die jemand von Hand
  bekommen hat, bleiben.
- **Neue Konten** entstehen bei der ersten Anmeldung – aber nur, wenn die
  Gruppen des Nutzers mindestens eine Rolle ergeben. Wer in keiner
  zugeordneten Gruppe ist, bekommt kein Konto.
- **Bestehende Konten (`link_existing_accounts`, Standard aus).** Ein
  Verzeichnis-Nutzer, dessen Name dem eines Kontos in Rentalars gleicht, das noch
  nicht mit dem Verzeichnis verknüpft ist, wird **abgewiesen**: Ein Name im
  Verzeichnis ist kein Beweis, dass es dieselbe Person ist, und wer dort einen
  Namen frei wählen kann, könnte sonst ein Konto übernehmen. **Folge für den
  Betrieb:** Bestehende Konten werden nicht automatisch verknüpft. Wer
  sie ins Verzeichnis holen will, schaltet den Schalter an (die Seite warnt in
  Rot, solange er an ist), lässt die Betroffenen sich einmal anmelden und
  schaltet ihn wieder aus; verknüpfte Konten melden sich weiter an. Dem Nutzer
  sagt die Anmeldeseite nur allgemein, dass es nicht geklappt hat; der Grund
  steht im Sicherheitsprotokoll und im Test. Lokale Notfallkonten und Konten
  mit „Hat alle Rechte“ nimmt das Verzeichnis nie, auch nicht über den DN, und
  der Abgleich lässt sie aus; die Verknüpfung wird geleert, sobald ein Konto
  lokal wird oder alle Rechte bekommt.
- **Verschobene Einträge:** Ändert sich der DN eines Nutzers im Verzeichnis,
  wird er abgewiesen, denn sein Konto hängt am alten Eintrag. Im Test der
  Anmeldung steht dann „Neuen Eintrag übernehmen“ (API `POST /ldap/adopt-dn`);
  es verknüpft das Konto neu – nur, wenn der alte Eintrag im Verzeichnis
  nicht mehr existiert – und steht im Verlauf des Kontos.
- **Nach dem Abschalten von LDAP** sind Konten, die nur im Verzeichnis
  existierten, nicht gestrandet: Eine Administratorin kann sie einladen oder
  ihnen ein Passwort setzen.
- **Deaktivieren:** Verlässt jemand die zugeordneten Gruppen, wird sein Konto
  bei der nächsten Anmeldung deaktiviert – nur wenn das Verzeichnis es
  aktiviert hatte; was ein Administrator in Rentalars deaktiviert hat, bleibt
  deaktiviert. Der letzte Administrator, der die Einstellungen ändern darf,
  wird nie deaktiviert oder seiner Rollen beraubt.
- **Kein Passwort in Rentalars:** Verzeichnis-Konten ändern, setzen und
  erneuern ihr Passwort im Verzeichnis; „Passwort vergessen“, Einladung und
  Passwortwechsel gibt es für sie nicht. Mit Zwei-Faktor-Anmeldung kommt
  zuerst das Passwort des Verzeichnisses, dann der Code von Rentalars.
- **Schutz:** Der eingegebene Name wird maskiert und normalisiert, ehe er in
  den Filter kommt; ein leeres Passwort erreicht das Verzeichnis nie (viele
  Server würden es als anonyme Anmeldung annehmen); Passwörter stehen in
  keinem Protokoll; die Begrenzung der Versuche und die Sperre gelten wie
  bei der lokalen Anmeldung. Auch „Anmeldung für einen Nutzer testen“ zählt
  dazu (API: Antwort 429) und steht als `ldap_test` im Sicherheitsprotokoll; für
  geschützte Namen läuft ein Schein-Bind, damit die Antwortzeit nichts
  verrät. Das Sicherheitsprotokoll (Einstellungen →
  Sicherheitsprotokoll) kennt sechs neue Arten: „Verzeichnis-Anmeldung
  abgelehnt“, „Verzeichnis nicht erreichbar“, „Konto vom Verzeichnis
  angelegt oder geändert“, „Rollen vom Verzeichnis geändert“, „Konten mit
  dem Verzeichnis abgeglichen“ und „Verzeichnis-Anmeldung von einem
  Administrator ausprobiert“. Das Bind-Passwort des Suchkontos steht auch
  nicht im vollständigen Datenexport.

### Beispiele

**OpenLDAP** (`inetOrgPerson`, Gruppen als `groupOfNames`):

| Feld | Wert |
|---|---|
| Server | `ldaps://ldap.example.com` |
| Suchkonto | `cn=rentalars,ou=service,dc=example,dc=com` |
| Suchbasis Nutzer | `ou=people,dc=example,dc=com` |
| Filter Nutzer | `(&(objectClass=inetOrgPerson)(uid={username}))` |
| Attribute | Anmeldename `uid`, E-Mail `mail`, Vorname `givenName`, Nachname `sn` |
| Gruppen | „In den Gruppen suchen“, Basis `ou=groups,dc=example,dc=com`, Filter `(&(objectClass=groupOfNames)(member={user_dn}))` |
| Zuordnung | `cn=rentalars-admin,ou=groups,dc=example,dc=com` → Administrator |

Mit `posixGroup` heißt der Gruppenfilter
`(&(objectClass=posixGroup)(memberUid={username}))`. Hat der Server das
Overlay `memberof`, genügt statt der Suche das Attribut `memberOf`.

**Active Directory:**

| Feld | Wert |
|---|---|
| Server | `ldaps://dc1.example.com` (zweiter Eintrag: `ldaps://dc2.example.com`) |
| Suchkonto | `CN=svc-rentalars,OU=Service,DC=example,DC=com` |
| Suchbasis Nutzer | `OU=Staff,DC=example,DC=com` (oder `DC=example,DC=com`) |
| Filter Nutzer | `(&(objectClass=person)(sAMAccountName={username}))` (Voreinstellung) |
| Attribute | `sAMAccountName`, `mail`, `givenName`, `sn` (Voreinstellung) |
| Gruppen | „Attribut des Nutzers (memberOf)“, Attribut `memberOf` (Voreinstellung) |
| Zuordnung | `CN=Rentalars-Admins,OU=Groups,DC=example,DC=com` → Administrator |

Der Anmeldename ist der Name ohne Domäne (`anna`, nicht `EXAMPLE\anna` und
nicht die Mail-Adresse). Zwei Hinweise aus der Dokumentation von AD, die
**nicht geprüft** sind: `objectClass=person` trifft auch Computerkonten;
ein Filter wie `(&(objectCategory=person)(objectClass=user)(sAMAccountName={username}))`
ist enger. Und `memberOf` nennt nur Gruppen, in denen der Nutzer
**unmittelbar** Mitglied ist. Für **geschachtelte Gruppen** nimm die
Gruppensuche mit der Regel für verkettete Mitgliedschaft
(`LDAP_MATCHING_RULE_IN_CHAIN`), Basis `DC=example,DC=com`, Filter
`(&(objectClass=group)(member:1.2.840.113556.1.4.1941:={user_dn}))`.

### Abgleich und tägliche Wartung: `ldap_sync`

Ohne Abgleich ändern sich Rollen und Aktivierung erst bei der nächsten
Anmeldung der Person. Der Befehl vergleicht alle Konten, die das
Verzeichnis führt:

```sh
sudo rentalars ldap_sync               # Probelauf: zeigt nur, was sich änderte
sudo rentalars ldap_sync --apply       # schreibt die Unterschiede
sudo rentalars ldap_sync --apply --force   # auch wenn mehr als die Hälfte deaktiviert würde
```

Eine Zeile je Konto, das sich unterscheidet („anna: update … Rollen A -> B“,
„karl: deactivate (nicht mehr im Verzeichnis)“), zuletzt die Summe. Namen,
E-Mail-Adresse und Rollen werden angeglichen; wer aus dem Verzeichnis
verschwunden oder in keiner zugeordneten Gruppe ist, wird deaktiviert (und
wieder aktiviert, wenn das Verzeichnis ihn deaktiviert hatte und er
zurückkehrt). Konten werden hier **nie angelegt** (das geschieht bei der
Anmeldung); lokale Konten, Konten mit „Hat alle Rechte“ und der letzte
Administrator bleiben unberührt.
**Schutzgrenze:** Würden mehr als drei Konten und mehr als die Hälfte
deaktiviert, schreibt der Befehl nichts und endet mit einer Meldung – das
sieht nach einem falschen Filter oder einem Verzeichnis ohne Antwort aus.
Erst Einstellungen prüfen, dann nötigenfalls `--force`. Die Seite hat
dieselbe Funktion: „Unterschiede anzeigen“ und „Diese Änderungen
anwenden“.

**Jede Nacht:** Mit der Einstellung **„Konten jede Nacht abgleichen“**
(voreingestellt aus) macht die tägliche Wartung um 4:15 Uhr dasselbe mit
`--apply`, aber ohne `--force`. Ihre Zeile steht im Protokoll:

```sh
sudo journalctl -u rentalars-maintenance -n 30 | grep -i ldap
```

Der Zeitpunkt und die Summe des letzten Abgleichs stehen auch auf der Seite
der Einstellungen. Ist das Verzeichnis nachts nicht erreichbar, steht
„comparison failed (unreachable)“ im Protokoll, ein Eintrag „Verzeichnis
nicht erreichbar“ im Sicherheitsprotokoll, und nichts wird verändert. Auch ein
anderer, unerwarteter Fehler beendet nur den Abgleich: Er steht mit der
Fehlermeldung im Protokoll („comparison failed (unexpected error, see the
log)“), und der Rest der täglichen Wartung läuft weiter.

### Wenn die Anmeldung nicht klappt

„Verbindung testen“ und „Anmeldung für einen Nutzer testen“ nennen den
Grund mit einem dieser Kennzeichen; Administratoren sehen sie auch im
Sicherheitsprotokoll. Nutzern zeigt die Anmeldeseite nur einen allgemeinen
Text.

| Kennzeichen | Bedeutung | Prüfe |
|---|---|---|
| `unreachable` | Der Server antwortet nicht oder der Name ist unbekannt | Adresse und Port, Firewall, DNS vom Rentalars-Server aus (`getent hosts dc1.example.com`), `openssl s_client` wie oben |
| `blocked` | Die Adresse führt in ein internes Netz | `[network] allow_internal` mit dem **Namen** des Servers, danach `sudo systemctl restart rentalars` |
| `tls` | Verschlüsselung oder Zertifikat abgelehnt | CA-Zertifikat (Pfad oder PEM); der Name im Zertifikat muss der eingetragene Name sein, **keine IP-Adresse**; Zertifikat abgelaufen; `ldaps://` mit Port 636, `ldap://` mit StartTLS und Port 389 – nicht mischen |
| `service_bind` | Das Suchkonto kann sich nicht anmelden | DN und Passwort; Passwort eingetragen? Nach einem Wechsel des `secret_key` neu eingeben; Konto gesperrt oder abgelaufen |
| `search` | Die Suche scheitert | Suchbasis vorhanden (`The search base … does not exist`)? Darf das Suchkonto dort lesen? Filter mit Klammern richtig? |
| `ambiguous` | Der Filter findet mehr als einen Eintrag | Filter enger fassen, Suchbasis kleiner wählen |
| `entry` | Der Eintrag ist nicht brauchbar | das Attribut für den Anmeldenamen fehlt, oder der Name ist zu lang (er wird abgelehnt, nicht gekürzt) |
| „abgelehnt trotz richtigen Passworts“ | Der Nutzer wurde gefunden, hat aber keine Rolle | „Anmeldung für einen Nutzer testen“ zeigt die Gruppen und die Rollen: Ist die Gruppe in der Tabelle? Stimmt der DN der Gruppe (Schreibweise, Groß-/Kleinschreibung der Teile spielt keine Rolle)? Bei AD und verschachtelten Gruppen siehe oben |
| „nicht verknüpft“ (`not_linked`) | Es gibt in Rentalars ein Konto dieses Namens, das nicht mit dem Verzeichnis verknüpft ist | gewollt, solange „Bestehende Konten über den Namen verknüpfen“ aus ist; sonst den Schalter an, einmal anmelden lassen, wieder aus |
| „verschoben“ (`moved`) | Das Konto hängt an einem anderen Eintrag (DN geändert) | im Test „Neuen Eintrag übernehmen“, wenn der alte Eintrag nicht mehr existiert |
| „geschützt“ (`protected`) | Lokales Notfallkonto oder „Hat alle Rechte“ | gewollt: Diese Konten melden sich nur mit dem Passwort in Rentalars an |
| „Konto deaktiviert“ | Das Verzeichnis hat es deaktiviert (nicht mehr in einer zugeordneten Gruppe) oder ein Administrator in Rentalars | Gruppen prüfen; ein Administrator aktiviert das Konto wieder, falls er es deaktiviert hatte |

**Alle Anmeldungen scheitern, und die lokale ist abgeschaltet:** Melde dich
mit dem lokalen Notfall-Konto an (Schritt 1 oben) und schalte unter
Einstellungen → Verzeichnis (LDAP) die „Anmeldung mit lokalem Passwort“ wieder
ein oder das Verzeichnis ab. Hat das Notfall-Konto sein Passwort vergessen,
setzt du es auf dem Server neu: `sudo rentalars changepassword NAME` (oben,
„Wenn etwas hakt“). Ein Konto, das das Verzeichnis führt, hat kein Passwort
in Rentalars und ist dafür der falsche Weg: Lege ein Notfall-Konto an,
solange das Verzeichnis noch antwortet.

## Protokolle

| Was | Befehl |
|---|---|
| Meldungen von Rentalars (Fehler, Zugriffe, nicht versandte E-Mails) | `sudo journalctl -u rentalars -n 100` |
| laufend mitlesen | `sudo journalctl -u rentalars -f` |
| die nächtliche Sicherung | `sudo journalctl -u rentalars-backup -n 30` |
| der Abruf der Postfächer (eine Zeile je Postfach und Lauf) | `sudo journalctl -u rentalars-mail -n 30` |
| Aufgaben im Hintergrund, die der Zeitgeber ausgeführt oder neu gestartet hat (die von einer Seite gestarteten – auch Übergaben an Lexware Office – stehen bei `rentalars`), und Programmfehler beim Abgleich der Kalender, beim Zustellen der Webhooks und beim Nachholen von Automationen | `sudo journalctl -u rentalars-jobs -n 30` |
| die tägliche Wartung (was gelöscht und gemeldet wurde) | `sudo journalctl -u rentalars-maintenance -n 30` |
| die lokale KI (nur wenn eingerichtet) | `sudo journalctl -u rentalars-ai -n 50` |
| NGINX | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| langsame Datenbankabfragen (über 1 Sekunde) | `/var/log/mysql/rentalars-slow.log` |

Wer was wann an den Daten geändert hat, steht nicht hier, sondern im
Programm: „Einstellungen → Änderungsprotokoll“. Anmeldungen, Fehlversuche,
Zwei-Faktor-Anmeldung, beendete Sitzungen und festgelegte
Einmal-Passwörter stehen unter „Einstellungen → Sicherheitsprotokoll“
(AUT-022). Es gibt zwei weitere Protokolle im Browser, beide mit
Filtern und als CSV:

- **Einstellungen → Mail-Protokoll** (EML-039): jede Mail, die
  hereinkam oder hinausging – Projektmails wie Systemmails (Einladungen,
  Links zum Passwort, Benachrichtigungen, die Testmail) –, mit Zeitpunkt,
  Absender, Empfängern, Betreff, Projekt und Ergebnis, bei einem Fehler mit
  der Meldung des Mailservers; auch mit dem **Postfach**, über
  das die Mail kam oder ging (leer bei Systemmails über `[email]`), und dem
  Ergebnis „Anfrage“ für Mails ohne Kennung; dazu das Ergebnis
  „Antwort auf Einsatzanfrage“ (Zusage oder Absage, gelb mit Grund, wenn
  nicht übernommen) für Antworten der Crew per Mail (unten, „Postfächer“).
  Jeder Eintrag merkt sich den Namen des Postfachs; ist es
  gelöscht, steht es mit „(gelöscht)“ da. Eine Systemmail,
  die mangels Mailserver nicht hinausging, steht mit dem Ergebnis „nicht
  versendet – kein Mailserver eingerichtet“ da, nicht als „gesendet“
  (unten, „Ohne Mailserver“). Den Text der Mails hält es nicht
  fest. Das ist die erste Stelle, wenn
  jemand sagt „die Einladung kam nie an“ – oder „meine Zusage kam nicht
  an“.
- **Einstellungen → Zugriffsprotokoll** (AUT-028): wer Kunden, Personen
  und Projekte samt ihren Mails, Dateien und Dokumenten geöffnet, wer Listen
  als CSV, den vollständigen Export oder eine Sicherung heruntergeladen hat
  – im Browser wie über die API, mit Zeitpunkt und IP-Adresse. Derselbe
  Zugriff derselben Person innerhalb von fünf Minuten zählt einmal; was
  jemand über sich selbst ansieht, steht nicht darin, ebenso wenig, was
  Befehle auf dem Server lesen.

Wie lange beide bleiben, steht oben unter „Aufbewahrungsfristen“.

## Selbstprüfung

Im Browser unter **Einstellungen → Selbsttest**, auf dem Server mit

```sh
sudo rentalars selfcheck
```

prüft Rentalars den Zustand der Installation (NFA-037) und sagt bei jedem
Punkt „in Ordnung“, „Hinweis“, „Warnung“ oder „Fehler“:

| Gruppe | Was geprüft wird |
|---|---|
| Versionen | Rentalars, Python, Django, Ubuntu, NGINX; ffmpeg (Warnung, wenn es fehlt – dann werden nur Videos im Chat abgelehnt; oben, „Fotos und Videos im Chat“) |
| Server | Prozessoren und Last der letzten 1, 5 und 15 Minuten (Warnung, wenn die Last über 5 Minuten mehr als das Doppelte der Kerne beträgt – dann warten Anfragen auf einen Prozessor), Arbeitsspeicher (Warnung, wenn weniger als ein Zehntel frei ist), Speicher von Rentalars (alle Arbeitsprozesse zusammen), Rechnername, Netzwerk je Schnittstelle mit Adressen und Datenmenge seit dem Start, Laufzeit seit dem letzten Neustart; auf einem Raspberry Pi die Zeile „Gerät“ mit dem Modell – ein Hinweis, wenn er weniger als 4 GB hat. Gelesen aus `/proc`; was dort fehlt, lässt der Selbsttest weg |
| Datenbank | Verbindung; fehlende Änderungen an den Tabellen; bei einem vorhandenen Server: Rechte des Benutzers (nur diese Datenbank), verschlüsselte Verbindung; ob der Server seine Dateien verschlüsselt |
| Dateien | Rechte der Konfigurationsdatei, des Datenordners und des Wiederherstellungsschlüssels |
| E-Mail | Systemmails: über welches Postfach oder welchen Mailserver aus `[email]` sie gehen (Warnung, wenn keiner eingerichtet ist – mit dem Text „Kein Mailserver eingerichtet: Einladungen, Passwort-Links und Benachrichtigungen werden nicht versendet.“ und dem Weg zu einem Postfach für Systemmails oder zu `[email]`); je aktivem Postfach der Korrespondenz eine Zeile „Postfach „Name““ mit dem letzten erfolgreichen Abruf (Warnung, wenn er länger als fünf Abstände, mindestens 15 Minuten, her ist) oder dem letzten Fehler; ohne solches Postfach der Hinweis „Postfächer: nicht eingerichtet“ oder, wenn es nur ausgeschaltete gibt, „Postfächer: keines eingeschaltet“ |
| Gateway | Ist ein Gateway verbunden (`rentalars gateway connect`): die Adresse, ob es antwortet (Fehler, wenn die letzte Antwort älter als 90 Sekunden ist – dann läuft der Dienst `rentalars-gateway-link` nicht; Warnung, solange noch keine Antwort kam), der letzte Fehler, die Zahl der gekoppelten und gesperrten Apps und ein angekündigter Umzug. Ohne Gateway eine Zeile „keine – die Apps erreichen den Server direkt“. Die Prüfung liest nur die Datenbank und ruft das Gateway nicht auf; den Ablauf des Zertifikats des Gateways prüft sie nicht (`rentalars gateway status` fragt das Gateway) |
| Sicherung | Alter der letzten Sicherung (Warnung ab 25 Stunden, Fehler ab 50), verschlüsselt, freier Platz |
| Speicherplatz | freier Platz für die Daten (Warnung unter 2 GB, Fehler unter 300 MB); auf einem Raspberry Pi der Hinweis „SD-Karte“, wenn Datenbank, Datenordner oder Sicherungen auf der SD-Karte (oder dem eMMC eines Compute Module) liegen – ein Hinweis, keine Warnung, damit ein bewusst so eingerichteter Pi nicht dauerhaft gelb steht |
| Sicherheit | Debug-Modus aus, „HTTPS“ – die Adresse mit https (eine Warnung, wenn `allow_http = yes` unverschlüsseltes HTTP erlaubt; oben, „HTTPS und vorgeschaltete Server“), geheimer Schlüssel lang genug, Zwei-Faktor-Anmeldung für Administratoren, Abmeldung nach Inaktivität, die sicheren Einstellungen der NGINX-Vorlage; „NGINX: Größe beim Hochladen“ – Warnung, wenn NGINX kleinere Anfragen annimmt als die größte hochladbare Datei und, als ein Video im Chat (200 MB) |
| Verbindungen zu anderen Servern | „Interne Adressen“: jede Einstellung aus dem Browser – verknüpfter Kalender, CalDAV-Kalender, aktiver Webhook (genannt mit Beschreibung oder Host, nie mit dem Pfad), IMAP- und SMTP-Server eines aktiven Postfachs, jede Schnittstelle der KI („KI-Schnittstelle Name“) –, die ins interne Netz führt, mit der aufgelösten Adresse und der Art des Netzes (Warnung; höchstens zehn genannt, dann „… und n weitere“); „Erlaubte interne Adressen“: was unter `[network] allow_internal` steht (oben, „Verbindungen ins interne Netz“) |
| Fehler der Anwendung | was in den letzten sieben Tagen schiefging, mit Anzahl |

Der Befehl endet bei einem Fehler mit dem Rückgabewert 1 – ein Werkzeug zur
Überwachung kann ihn also regelmäßig aufrufen. Dasselbe liefert die API
unter `/api/v1/self-check`, mit den Werten des Servers unter
`resources`.

Im Browser verschickt „Testmail an mich senden“ eine Mail an die eigene
Adresse – so lässt sich der Versand prüfen, ohne auf den Server zu müssen.
Ohne Mailserver meldet die Seite „Nicht versendet – kein
Mailserver eingerichtet.“ statt eines Erfolgs.

### Ohne Mailserver

Hat kein aktives Postfach die Rolle „Systemmails“ und steht unter
`[email]` kein `host`, schreibt Rentalars Systemmails nur in das Protokoll
des Dienstes (`sudo journalctl -u rentalars -n 100`) – als Absender mit
`rentalars@localhost`, der Vorgabe von `from_address`. Ankommen kann so
nichts. Dabei gilt (EML-048):

- Das Mail-Protokoll nennt sie „nicht versendet – kein Mailserver
  eingerichtet“; sie zählt nicht als gesendet, und eine Benachrichtigung
  gilt nicht als per Mail verschickt.
- Wer im Browser etwas versendet – Testmail, Einladung, neuer Link zum
  Passwort, Einsatzanfrage –, bekommt die Warnung mit einem Link zu
  Einstellungen → Postfächer und Signatur; die Seite der Postfächer und das
  Mail-Protokoll zeigen sie oben.
- Die API sagt es ebenso: `POST /api/v1/users/{id}/send-invitation`
  antwortet dann 200 mit `{"sent": false, "reason": …}` statt 204, `POST
  /api/v1/users` nennt `invitation`, die Einsatzanfrage `mail_sent` und
  `mail_reason`.
- Der Selbsttest warnt (oben).

Als „kein Mailserver“ gilt: kein aktives, vollständiges Postfach mit der
Rolle „Systemmails“ und in Django ein Versandweg, der nur protokolliert
(ohne `host` unter `[email]`). Ein Postfach der Korrespondenz mit eigenem
SMTP-Server sendet Projektmails davon unberührt. Abhilfe: einem Postfach im
Browser die Rolle „Systemmails“ geben, oder `[email]` in der
Konfigurationsdatei ausfüllen und `sudo systemctl restart rentalars`.

## Fehler der Anwendung

Läuft in Rentalars etwas schief – ein Programmfehler, ein Mailserver, der
nicht antwortet –, steht das im Protokoll
(`sudo journalctl -u rentalars`). Zusätzlich zählt Rentalars jeden Fehler in
der Datenbank und **benachrichtigt die Administratoren** (NFA-018): beim
ersten Auftreten in der Anwendung und, sofern sie es nicht abgeschaltet
haben, per E-Mail. Tritt derselbe Fehler wieder auf, wird nur gezählt; eine
neue Nachricht gibt es erst nach 24 Stunden. Die Liste steht im Selbsttest.

## Postfächer

Rentalars holt die Projektmails selbst ab (EML-005) und versendet die in
Projekten geschriebenen Mails selbst. Es arbeitet dafür mit
beliebig vielen vorhandenen Postfächern, etwa `projekte@eure-firma.example` und
`info@eure-firma.example` (EML-041, EML-042). Eingerichtet werden sie im Browser
unter **Einstellungen → E-Mail → „Postfächer und Signatur“**, eine Seite je
Postfach („Postfach hinzufügen“, „Bearbeiten“). Anlegen und ändern darf,
wer das Modul E-Mail bearbeiten darf; löschen, wer darin löschen darf
(voreingestellt nur die Rolle Administrator). In der Konfigurationsdatei
steht kein Postfach.

Jedes Postfach hat einen Namen (er steht in der Liste, im Mail-Protokoll
und bei den Anfragen), seine Adresse, „aktiv“ – ausgeschaltet wird es
weder abgerufen noch zum Senden benutzt – und seine **Rollen**:

| Rolle | Bedeutung | wie viele |
|---|---|---|
| Korrespondenz | wird abgerufen; Mails mit Projektkürzel im Betreff kommen ins Projekt; Antworten der Crew auf Einsatzanfragen werden erkannt | beliebig viele |
| Postausgang der Korrespondenz | in Projekten geschriebene Mails gehen hierüber hinaus, mit seiner Adresse als Absender | genau eines der aktiven Postfächer der Korrespondenz |
| Systemmails | Einladungen, Links zum Passwort, Benachrichtigungen, Einsatzanfragen, die Testmail | höchstens eines |

Ein Postfach darf mehrere Rollen haben, etwa Korrespondenz, Postausgang und
Systemmails zugleich. Gibst du einem Postfach den Postausgang oder die
Systemmails, gibt das bisherige die Rolle ab; die Seite sagt es. Ohne
Postfach für Systemmails gehen diese über den Mailserver aus
`[email]` der Konfigurationsdatei – ebenso, wenn die Datenbank nicht
erreichbar ist. Mit einem solchen Postfach behalten sie den Absendernamen
aus `[email]` und bekommen die Adresse des Postfachs.

**Der Hinweis am Ende der Systemmails** (EML-045). Jede Mail,
die Rentalars von selbst verschickt – Benachrichtigungen, Einladungen,
Links zum Passwort, Einsatzanfragen und die Rückmeldungen auf Antworten
per Mail, Meldungen über Fehler und Aufgaben im Hintergrund, die Testmail
des Selbsttests, auch die Antworten von Automationen (unten) –,
endet mit

```
-- 
Diese Nachricht wurde automatisch von Rentalars für Muster Veranstaltungstechnik versendet: https://rentalars.example.de
```

Der Firmenname kommt aus Einstellungen → Firmendaten und
Grundeinstellungen (fehlt er, steht der Satz ohne „für …“), die Adresse
aus `url` unter `[rentalars]` der Konfigurationsdatei – dieselbe Adresse,
die in den Links der Mails steht. Eine eigene Umgebungsvariable dafür gibt
es nicht (`RENTALARS_URL` heißt der Wert nur intern, in den Einstellungen
von Django); nach einer Änderung an der Datei `sudo systemctl restart
rentalars`. Der Satz kommt im Versandweg an die Mail, den alle
Systemmails durchlaufen (dem Mail-Backend von Rentalars), ob sie über ein
Postfach „Systemmails“ oder über `[email]` hinausgehen: im Text hinter der
üblichen Trennzeile
`-- `, in einer HTML-Mail als letzter Absatz, mit der Adresse als Link,
und je Mail nur einmal. In Projekten geschriebene Mails (Postausgang der
Korrespondenz) bekommen ihn nicht; sie tragen die Signatur.

Je Postfach der Korrespondenz stellst du außerdem ein:

- **„Mails ohne Projektkennung übernehmen“** (voreingestellt aus).
  Eingeschaltet erscheinen Mails ohne Kürzel als **Anfragen** unter
  Projekte → Anfragen; auch sie bleiben im Posteingang, bis jemand sie in
  ein Projekt übernimmt. Ausgeschaltet fasst Rentalars sie nicht an.
  Das gilt (EML-049) nur ab einem Zeitpunkt:
  **„übernehmen ab“** wird beim Einschalten auf diesen Moment gesetzt und
  lässt sich ändern; **„nur ungelesene Mails“** übernimmt nur Mails ohne
  `\Seen`. Maßgeblich ist, wann die Mail im Postfach ankam (IMAP
  `INTERNALDATE`, ohne sie die Kopfzeile `Date`); eine Mail ganz ohne Datum
  bleibt liegen, solange ein Zeitpunkt gesetzt ist. Die Angaben holt der
  Abruf mit den Kopfzeilen (`FLAGS INTERNALDATE`), ohne zusätzliche
  Anfrage. Was so liegen bleibt, steht im Mail-Protokoll als „im Posteingang
  gelassen“ mit dem Grund. Dasselbe gibt es je weiterer Adresse.
- **„Zugeordnete Mails im Postfach“**: als gelesen markieren und in einen
  Ordner verschieben (voreingestellt „Rentalars“; er wird angelegt, wenn er
  fehlt), nur als gelesen markieren (die Mail bleibt im
  Posteingang – außer der Antwort auf eine Einsatzanfrage, die
  auch dann in den Ordner kommt), löschen – nur, wenn Rentalars der einzige Ort ist, an dem die
  Mails aufbewahrt werden – oder unverändert im Posteingang lassen, nicht
  einmal als gelesen markiert.
- **Empfangen (IMAP)** mit dem Ordner Posteingang und **Senden (SMTP)**,
  wahlweise mit Benutzer und Passwort des Empfangs (voreingestellt).

Was für alle gilt, steht auf derselben Seite unter **„Regeln für alle
Postfächer“**: abrufen alle … Minuten (voreingestellt 2), größte Mail (MB)
und Mails aufbewahren für … Tage. Darunter steht, wie Einsatzanfragen
beantwortet werden und an welches Postfach Antworten per Mail gehen;
eingestellt wird das unter Einstellungen → Firmendaten und
Grundeinstellungen (unten, „Einsatzanfragen per Antwort-Mail“).
Passwörter werden verschlüsselt gespeichert und nie wieder angezeigt.
Liegt ein IMAP- oder SMTP-Server im internen Netz (der Mailserver im
Haus), braucht er die Freigabe unter `[network]
allow_internal` (oben, „Verbindungen ins interne Netz“) – das gilt auch
für das Postfach „Systemmails“, nicht aber für `[email]`. Beim Eintragen
prüft das Formular den Namen nicht; „Verbindung prüfen“ zeigt die
Ablehnung.

**Der Abruf.** Der Zeitgeber `rentalars-mail.timer` startet jede Minute
`fetch_mail`. Der ruft jedes aktive Postfach der Korrespondenz ab, eines
nach dem anderen, sobald seit dessen letztem Abruf der Abstand um ist. Was
dabei geschieht, steht im [Benutzerhandbuch](../handbuch/benutzerhandbuch.md),
„Korrespondenz“; kurz: Rentalars sieht zuerst nach, ob eine
Mail eine **Antwort auf eine Einsatzanfrage** ist (unten); solche Mails
nimmt es aus jedem Postfach, das es abruft. Mails mit einem Projektkürzel
im Betreff und Antworten auf übernommene Mails kommen ins Projekt und
werden dann – wie die Antworten auf Einsatzanfragen – behandelt, wie das
Postfach es sagt. Mails mit einem unbekannten Kürzel –
und, wo eingeschaltet, Mails ohne Kürzel – warten unter Projekte →
Anfragen. Alles andere bleibt im Posteingang, wie es ist. Liegt dieselbe
Mail in zwei Postfächern, wird sie einmal übernommen und steht einmal in
der Liste. Ein Postfach kann (EML-047) **weitere Adressen**
(Aliasse) mit eigener Regel für Mails ohne Kürzel haben; welche Adresse
gemeint war, liest der Abruf aus `Delivered-To`, `X-Original-To`, `To` und
`Cc`. Eine solche Mail kann gleich einen Servicefall anlegen. Eingerichtet
wird das im Browser (Benutzerhandbuch, „Weitere Adressen eines
Postfachs“).

**Stand und Fehler.** Jedes Postfach hat seinen eigenen Stand. Die Liste
unter „Postfächer und Signatur“ zeigt je Postfach Rollen, aktiv oder aus,
den letzten erfolgreichen Abruf und den letzten Fehler. **„Verbindung
prüfen“** meldet sich bei IMAP und SMTP an, ohne etwas zu ändern oder zu
senden; **„Jetzt abrufen“** ruft alle Postfächer der Korrespondenz sofort
ab. Klemmt ein Postfach – falsches Passwort, Server nicht erreichbar –,
werden die anderen weiter abgerufen. Der Fehler steht mit dem Namen des
Postfachs in der Liste, auf der Startseite und im Selbsttest, und die
Administratoren bekommen je Postfach **eine** Benachrichtigung („Mails von
Projekte können nicht abgerufen werden: …“), nicht bei jedem Versuch eine
neue. Welche Mails über welches Postfach kamen und gingen, zeigt das
Mail-Protokoll (oben, „Protokolle“). Den Abruf von Hand anstoßen und je
Postfach eine Zeile sehen:

```sh
sudo rentalars fetch_mail --now
```

```
Projekte: 3 neue Mails angesehen; 2 zugeordnet, 0 mit unbekannter Kennung, 0 Anfragen.
1 Antwort auf eine Einsatzanfrage per Mail.
Info: 5 neue Mails angesehen; 0 zugeordnet, 0 mit unbekannter Kennung, 4 Anfragen.
```

Die Zeile mit den Antworten auf Einsatzanfragen steht nur, wenn welche
kamen. Konnte ein Postfach nicht abgerufen werden, steht der Fehler
darunter, und der Befehl endet mit dem Rückgabewert 1. „Jetzt abrufen“ im
Browser nennt die Antworten ebenso.

**Löschen** (EML-046). Jedes Postfach lässt sich löschen,
auch wenn schon Mails darüber kamen oder gingen. „Postfach löschen“ führt
zu einer Seite, die vorher sagt, was folgt; dort lässt es sich stattdessen
auch nur ausschalten. Beim Löschen

- bleiben die Projektmails und die Einträge im Mail-Protokoll und nennen
  das Postfach weiter beim Namen – den Namen tragen sie selbst, im
  Protokoll mit „(gelöscht)“;
- verschwinden Anfragen und Mails mit unbekannter Kennung, die in dem
  Postfach warten, aus Projekte → Anfragen; auf dem Mailserver bleiben
  sie;
- hat danach kein Postfach mehr seine Rollen: Mails darin ruft Rentalars
  nicht mehr ab, und ohne anderes Postfach für Systemmails gehen diese
  über `[email]` der Konfigurationsdatei. Antworten auf Einsatzanfragen,
  die an dieses Postfach gingen, kommen nicht mehr an;
- übernimmt beim Postausgang der Korrespondenz ein anderes Postfach der
  Korrespondenz, das senden kann: Gibt es nur eines, geschieht das von
  selbst, gibt es mehrere, wählt man es auf der Seite (in der API mit
  `?successor=<id>`). Kann keines senden, lehnt Rentalars das Löschen mit
  dem Grund ab.

**Einsatzanfragen per Antwort-Mail** (PER-032). Die Crew kann
eine Einsatzanfrage per Mail beantworten statt über den Link in
Rentalars. Dafür muss Rentalars **nicht aus dem Internet erreichbar**
sein: Die Anfrage enthält die Knöpfe „Zusagen“ und „Absagen“ – Links, die
eine fertige Mail mit einem Code im Betreff öffnen, etwa `[RA-E-…-JA]` –,
und Rentalars holt die Antwort beim Abruf selbst ab, per IMAP von innen
nach außen wie jede Projektmail. Der Code ist zufällig (120 Bit), gilt für
genau eine Anfrage an genau eine Person und wird mit ihr gespeichert. Wie
geantwortet wird, steht unter Einstellungen → Firmendaten und
Grundeinstellungen → **„Antwort auf Einsatzanfragen“** (ändern darf es, wer die
Einstellungen bearbeiten darf):

| Einstellung | die Anfrage enthält |
|---|---|
| über den Link im Browser | nur den Link zu Rentalars |
| per Antwort-Mail | nur die Knöpfe – richtig, wenn Rentalars nur im eigenen Netz oder per VPN erreichbar ist; der Link führte dort von außen ins Leere |
| beides (voreingestellt) | Knöpfe und Link |

- **Das Postfach für die Antworten** ist das für die Systemmails, wenn es
  zugleich ein aktives Postfach der Korrespondenz mit Adresse ist, sonst
  der Postausgang der Korrespondenz. Die Seite nennt es unter der
  Einstellung. Gibt es keines, enthalten die Anfragen nur den Link, gleich
  was eingestellt ist; mit einem solchen Postfach kommen die Knöpfe von
  selbst dazu.
- **Die Anfrage-Mail** geht den Weg der Systemmails (Postfach
  „Systemmails“ oder `[email]`), als Text und HTML, mit dem Postfach für
  die Antworten als `Reply-To` – eine frei formulierte Antwort landet so
  in einem Postfach, das jemand liest – und mit `Auto-Submitted:
  auto-generated`. Sie geht an jede aktive Person mit E-Mail-Adresse, auch an
  Personen, die sich nicht anmelden können; wer die Mails zu
  Einsatzanfragen abgeschaltet hat, bekommt keine.
- **Beim Abruf** erkennt Rentalars die Antworten in **jedem** Postfach,
  das es abruft – gleich, ob es Mails ohne Projektkennung übernimmt –,
  trägt Zusage oder Absage samt Anmerkung (bis 250 Zeichen) ein, als
  hätte die Person im Browser geantwortet, und behandelt die Mail danach
  wie eine zugeordnete: verschieben, löschen oder liegen lassen. Im
  Projekt erscheint sie nicht als Mail. Frei formulierte Antworten („Ja“)
  wertet Rentalars nicht aus. Ist die Anfrage schon beantwortet, vorbei,
  zurückgenommen oder durch eine neuere ersetzt, oder ist das Projekt
  abgesagt oder abgeschlossen, ändert sich nichts.
- **Rückmeldung:** Die Person bekommt eine Bestätigung oder den Grund,
  warum nichts übernommen wurde – immer an ihre gespeicherte Adresse, nie
  an einen fremden Absender, ohne Code und mit `Auto-Submitted`. Eine
  Abwesenheitsnotiz, die den Code zitiert, gilt nicht als Antwort; so
  entsteht keine Schleife.
- **Nachvollziehen:** Das Mail-Protokoll führt jede Antwort als „Antwort
  auf Einsatzanfrage“, der Verlauf des Projekts „Antwort von … kam per
  Antwort-Mail“.
- **Absender:** Der Code genügt nicht. Die Anfrage merkt sich
  die Adresse, an die sie ging (`CrewRequestMail.sent_to`), und nur eine Mail
  von genau dieser Adresse (ohne Beachtung der Groß- und Kleinschreibung)
  zählt. So kann niemand eine weitergeleitete Anfrage im Namen des
  ursprünglichen Empfängers beantworten. Eine Antwort von einer anderen
  Adresse ändert nichts: Das Mail-Protokoll führt sie mit dem Grund
  „nicht von der Adresse, an die die Anfrage ging“, die Person bekommt an
  ihre gespeicherte Adresse eine Mail. **Gefälschte Absender:** Die Adresse
  im `From` lässt sich fälschen, Rentalars kann sie nicht selbst prüfen
  (keine eigene SPF-/DKIM-Auswertung). Es liest aber die Kopfzeile
  `Authentication-Results`, die der Mailserver eures Anbieters beim Empfang
  einträgt, und übernimmt eine Antwort mit `dmarc=fail` nicht (Grund „die
  Prüfung des Absenders schlug fehl“; auch bei `p=none`). Eine Mail mit
  mehr als einer `From`-Zeile wird nicht übernommen, die Warnmail an die
  Person geht je Anfrage und Grund höchstens einmal pro Stunde hinaus. Wie sicher das ist, hängt davon ab,
  ob euer Postfach diese Kopfzeile schreibt und ob die Domain der Crew-
  Adressen DMARC eingerichtet hat – bei privaten Adressen großer Anbieter
  ist das üblich. Wer das nicht verlassen möchte, stellt die Antwort auf
  „über den Link im Browser“. **Das lässt sich verschärfen:**
  Unter Einstellungen → Postfächer trägst du bei „Name deines Mailservers in
  den Prüfergebnissen“ den Namen ein, mit dem dein Mailserver die Kopfzeile
  `Authentication-Results` beginnt (der Teil vor dem ersten Semikolon,
  etwa `mx.example.com`; steht in jeder empfangenen Mail). Dann zählt eine
  Antwort nur, wenn genau dieser Server `dmarc=pass` oder `dkim=pass` für die
  Domain des Absenders schrieb (bei `dmarc=pass` muss auch `header.from` die
  Domain des Absenders sein). Es zählt die oberste Kopfzeile mit diesem Namen,
  denn ein Server setzt seine über alle anderen; gleichnamige Kopfzeilen, die
  ein Absender selbst in die Mail schreibt, stehen darunter und zählen nie.
  Auch ein Wert in einer Kopfzeile, den der Absender beeinflusst (ein Kommentar,
  die Absenderadresse im Umschlag), kann kein eigenes Ergebnis beginnen.
  **Bestätigt wird die Domain, nicht die Person:** Wer von derselben Domain
  senden darf, kann in ihrem Namen antworten. Ein Mailserver, der seinen
  Namen nicht an den Anfang der Kopfzeile setzt (Exchange Online beginnt mit
  `spf=pass`), lässt sich nicht eintragen; dort bleibt der Weg über den
  Link. Der Selbsttest weist darauf hin, solange nichts eingetragen ist. Wer nicht bestätigt ist, bekommt
  eine Mail mit dem Link zur Antwort im Browser. **Ohne den Eintrag ist eine
  Antwortmail kein Beweis, wer sie schrieb:** Dann wird nur die Adresse in der
  `From`-Zeile verglichen, und die kennt womöglich jemand. Verglichen wird
  die Adresse der strukturierten `From`-Zeile, nicht ein Text darin.
- **Netz:** nur die Verbindungen zu IMAP und SMTP eures
  Mailanbieters, die der Abruf ohnehin braucht. Die Codes stehen nicht im
  vollständigen Export (unten).
- **Neue Zeiten, neue Anfrage** (PER-033, PER-034). Ändern
  sich Beginn oder Ende einer angefragten oder zugesagten
  Personalposition – im Browser, beim Verschieben einer Phase mit ihrem
  Personal oder über die API –, schickt Rentalars von selbst eine neue
  Anfrage („Einsatzanfrage mit neuen Zeiten: …“, mit „Neue Zeiten: …
  (vorher: …)“) auf demselben Weg wie jede Anfrage, mit neuem Code; eine
  Antwort mit dem Code der älteren Anfrage wird nicht mehr übernommen
  („neuere Anfrage“). Abgesagte Positionen, stornierte Projekte und
  deaktivierte Personen fragt Rentalars nicht von selbst an. Abschalten
  lässt sich das im Browser unter Einstellungen → Firmendaten und
  Grundeinstellungen → **„Bei geänderten Zeiten neu anfragen“**
  (voreingestellt an). Wer viele Zeiten auf
  einmal verschiebt, verschickt so viele Mails; ausgeschaltet bietet die
  Planung stattdessen „erneut anfragen“ an.

Ein Postfach, aus dem Mails verschoben oder gelöscht werden, muss **IMAP
mit MOVE oder UIDPLUS** können, damit Rentalars eine einzelne Mail sicher
verschieben oder löschen kann. Das können alle gängigen Anbieter.

Wurde in der Konfiguration der **geheime Schlüssel geändert**, kann
Rentalars die gespeicherten Passwörter der Postfächer nicht mehr lesen.
Die Seite „Postfächer und Signatur“ nennt jedes betroffene Postfach; trage
sein Passwort dann neu ein. Dasselbe gilt
für die Zwei-Faktor-Anmeldung: Sie muss danach neu eingerichtet werden
(`sudo rentalars reset_two_factor NAME` für jeden, der sie nutzt) – und
 für die Geheimnisse der Webhooks und den API-Schlüssel von
Lexware Office (unten, „Webhooks“ und „Buchhaltung“).

## Automationen

Rentalars tut auf Wunsch von selbst etwas, wenn etwas geschieht
(ADM-013): eine Anfrage ohne Projektkennung mit einer Eingangsbestätigung
beantworten, jemanden benachrichtigen, einen offenen Punkt notieren.
Eingerichtet werden die Regeln im Browser unter **Einstellungen →
Automationen** (Modul Einstellungen: lesen zum Ansehen, bearbeiten zum
Ändern und Löschen) oder über `/api/v1/automations`; das beschreibt das
[Benutzerhandbuch](../handbuch/benutzerhandbuch.md). Ohne Regel tut
Rentalars nichts Neues. Für den Betrieb zählt:

- **Wann sie laufen:** Eine Ausführung wird zusammen mit dem Ereignis in
  der Datenbank vorgemerkt und gleich danach ausgeführt, dort, wo das
  Ereignis geschieht: beim Abruf der Postfächer (Dienst `rentalars-mail`)
  für Anfragen und Antworten der Crew per Mail, im Browser oder in der API
  (Dienst `rentalars`) für einen neuen Status und Antworten im Browser,
  mit den Wiedervorlagen (Dienst `rentalars-jobs`) für fällige
  Wiedervorlagen. Was dabei liegen bleibt, etwa weil Rentalars
  gerade neu startete, holt `rentalars-jobs.timer` in der nächsten Minute
  nach. Eine Ausführung, die mittendrin abbricht, wird als
  „fehlgeschlagen“ vermerkt und **nie wiederholt** – lieber keine Antwort
  als zwei.
- **Antworten per Mail** gehen über das Postfach, in dem die Anfrage lag,
  sonst über das, das die Korrespondenz versendet; es braucht SMTP und
  eine Adresse, sonst schlägt die Ausführung fehl („Kein Postfach kann
  senden …“). Empfänger ist `Reply-To` der Mail, sonst der Absender. Die
  Antwort trägt `Auto-Submitted: auto-replied` und
  `X-Auto-Response-Suppress: All` – damit antworten andere Systeme nicht
  zurück –, `In-Reply-To` und `References` und den Hinweis am Ende der
  Systemmails (oben). Im Mail-Protokoll steht sie mit der Art
  „automatische Antwort“. Ausgelöst werden nur Mails in Postfächern, die
  „Mails ohne Projektkennung übernehmen“.
- **Schutz vor Antwortschleifen:** Rentalars beantwortet nie eine Mail, die
  als automatisch gekennzeichnet ist (`Auto-Submitted` außer `no`,
  `Precedence: bulk`, `junk`, `list` oder `auto_reply`, `List-Id`,
  `List-Unsubscribe`, `X-Autoreply`, `X-Autorespond`,
  `X-Auto-Response-Suppress`, ein leerer `Return-Path`, ein
  Zustellbericht), nie Absender wie mailer-daemon, postmaster, no-reply
  oder bounce, nie eigene Adressen (Postfächer, Absender der Systemmails,
  Adresse der Firma) und jeden Absender höchstens einmal je Regel und
  Kalendertag. Für diese Prüfung liest der Abruf einige
  Kopfzeilen mehr. Damit weicht Rentalars bewusst von der Regel ab, auf
  Mails nicht von selbst zu antworten (EML-030) – nur für Regeln, die ihr
  anlegt.
- **Protokoll:** Jede Ausführung steht unter Einstellungen → Automationen,
  „Ausführungen“, mit Ergebnis und Grund, ein Jahr lang – auch nach dem
  Löschen ihrer Regel, mit deren Namen. Wird eine Person anonymisiert,
  verschwindet ihr Name auch dort. Wird ein Postfach gelöscht, schalten
  sich die Regeln aus, die nur für dieses Postfach galten. Programmfehler
  stehen im Protokoll des Dienstes, der die Ausführung gestartet hat
  (oben, „Protokolle“).
- **Die mitgelieferten Regeln** (drei für Servicefälle, „Defektmeldung → Servicefall“): Sie lassen sich (ADM-019)
  bearbeiten und löschen wie eigene und tragen einen festen Schlüssel
  (`default_key`). **Keine Aktualisierung und
  kein Start von Rentalars legt eine gelöschte wieder an oder überschreibt
  eine geänderte.** Zurück holt sie nur „Standard-Automationen
  wiederherstellen“ unter Einstellungen → Automationen oder
  `POST /api/v1/automations/restore-defaults` – beides legt nur die
  fehlenden an, wie sie kamen, eingeschaltet, mit dem Recht, die
  Einstellungen zu bearbeiten.

## Kalender der Personen

Rentalars tauscht mit den Kalendern der Personen aus, was sie
unter „Meine Personaldaten“ eingerichtet haben (PER-022, PER-023). Was die
Personen dort tun, steht im
[Benutzerhandbuch](../handbuch/benutzerhandbuch.md); für den Betrieb zählt:

- **Verknüpfter Kalender:** Rentalars liest den privaten ICS-Link eines
  Google-, Outlook- oder iCloud-Kalenders **alle 30 Minuten**, für den
  vergangenen Monat und das kommende halbe Jahr, und übernimmt nur, wann
  die Person belegt ist – keine Titel.
- **CalDAV-Kalender:** Rentalars schreibt die Einsätze einer Person in ihren
  Kalender bei Nextcloud, iCloud, mailbox.org, Posteo und ähnlichen –
  **binnen einer Minute** nach einer Änderung an einer Personalposition und
  sonst **alle 30 Minuten**. Google Kalender lässt sich so nicht
  beschreiben; dafür taugt der Abo-Link.
- **Abo-Link** (`https://rentalars.example.de/calendar-feed/…`): Kalender-Apps
  holen die Einsätze dort selbst ab, **ohne Anmeldung** – den Link schützt
  der geheime Schlüssel darin. Das klappt nur, wenn Rentalars aus dem Netz
  der Kalender-App erreichbar ist, in der Regel also aus dem Internet;
  Google Kalender etwa holt solche Links von seinen eigenen Servern. Läuft
  Rentalars nur intern oder per VPN, nehmt den CalDAV-Kalender. Der Kalender
  nennt sein Aktualisierungsintervall (`X-PUBLISHED-TTL`) als
  Dauer, `PT30M`.

**Kalender-Links von Produkten, Modellen und Exemplaren** (VFG-040).
Nach demselben Muster kann jedes Produkt, Materialmodell und Exemplar
einen geheimen Kalender-Link bekommen, unter
`https://rentalars.example.de/calendar-feed/<art>/<id>/<schlüssel>.ics`
(`<art>` ist `product`, `model` oder `item`); im Standard hat keines einen,
und erstellt, ersetzt und deaktiviert wird er auf der Seite des
Datensatzes oder über `/api/v1/products|material-models|material-items/{id}/calendar-link`
([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 4,
„Kalender-Link“). Für den Betrieb zählt:

- **Ohne Anmeldung, unter der Adresse aus der Konfigurationsdatei**
  (`url`): Kalenderprogramme müssen sie erreichen wie den Abo-Link einer
  Person. Ändert sich die Adresse des Servers, ändern sich die Adressen der
  Kalender-Links mit; die Abonnenten tragen am besten die neue ein.
- **Der Schlüssel** hat 256 Zufallsbits und wird in konstanter Zeit
  verglichen. Er steht in der Datenbank (und damit in der Sicherung), nie
  im Änderungsprotokoll und nicht im lesbaren Export aller Daten (unten,
  „Vollständiger Datenexport“). Die Adresse zeigen Seite und API nur, wer
  den Link ändern darf. Wer sie kennt, sieht Projektnummern und -namen mit
  Status und Zeitraum – keine Preise, Kunden oder Kontaktdaten.
- **Bremse und Zwischenspeicher wie beim Abo-Link:** Falsche Adressen
  zählen je Client zusammen mit denen der Abo-Links (dann „429“, unten), ein
  Link, der viel öfter abgerufen wird als von einem Kalenderprogramm,
  wartet ebenso; ein unveränderter Kalender antwortet `304 Not Modified`.
  Die NGINX-Begrenzung für `/calendar-feed/` (unten) gilt auch für sie.
- **Gerechnet wird beim Abruf**, 90 Tage zurück und zwei Jahre voraus, mit
  einer festen Zahl von Datenbankabfragen; Kalenderprogramme werden
  gebeten, alle 30 Minuten zu fragen. Einen Zeitgeber und keine
  Verbindung nach außen braucht das nicht.
- Ein deaktiviertes Produkt und ein ausgemustertes, verkauftes oder
  verlorenes Exemplar verlieren ihren Link endgültig; ein gelöschter
  Datensatz nimmt ihn mit.

Einen eigenen Zeitgeber gibt es für die Kalender der Personen nicht: Der Lauf von
`rentalars-jobs.timer` gleicht jede Minute ab, was fällig ist, nach den
Aufgaben im Hintergrund. Nach 40 Sekunden fängt er nichts Neues mehr an;
was dann noch offen ist, kommt in der nächsten Minute dran. Von Hand, etwa zum
Prüfen einer Einrichtung oder nach einem längeren Ausfall:

```sh
sudo rentalars sync_calendars               # alles, was fällig ist
sudo rentalars sync_calendars --person 17   # eine Person, fällig oder nicht; zeigt das Ergebnis
```

Für beides muss der Server **Verbindungen nach außen** aufbauen dürfen:
per HTTPS zu den Kalenderdiensten, bei einer eigenen Nextcloud auch ins
interne Netz – das nur mit Freigabe unter `[network]
allow_internal` (oben, „Verbindungen ins interne Netz“). Die Anmeldedaten
eines CalDAV-Kalenders gehen nur an genau den eingetragenen Server, außer
bei iCloud (ebenda). Klappt das Lesen oder Schreiben nicht, steht der Grund bei
der Person unter „Meine Personaldaten“ (ohne die Adresse, die geheim sein
kann); nach sechs Fehlschlägen in Folge – etwa drei Stunden – bekommt die
Person **eine** Benachrichtigung, voreingestellt auch per E-Mail.
Programmfehler beim Abgleich stehen im Protokoll von `rentalars-jobs`.

**Den Abo-Link begrenzen.** Rentalars bremst selbst, wer viele falsche
Links probiert oder einen Link viel öfter abruft als eine Kalender-App.
Es zählt die falschen Links je Client-Adresse, wie die
Anmeldung sie liest – hinter NGINX aus `X-Forwarded-For` –, und ohne
bekannte Adresse gar nicht.
Die NGINX-Vorlage begrenzt die Anfragen an `/calendar-feed/`
zusätzlich wie die an die Anmeldung (30 je Minute und Absender) – also auch die an die Kalender-Links von Produkten, Modellen und
Exemplaren. Eine
bestehende Installation bekommt das erst mit `sudo rentalars nginx-site`
(oben, „Die NGINX-Konfiguration“); der Selbsttest meldet das Fehlen
nicht.

Die Passwörter der CalDAV-Kalender liegen verschlüsselt in der Datenbank,
wie die der Postfächer. Wurde der geheime Schlüssel der
Konfiguration geändert, trägt jede Person ihr Passwort neu ein; bis dahin
steht bei ihr „Das gespeicherte Passwort lässt sich nicht mehr lesen“.

## Webhooks

Rentalars meldet anderen Systemen – ERP, Chat, n8n –, wenn
etwas geschieht: ein Projekt wird angelegt oder ändert seinen Status,
Material geht raus, wird übergeben oder kommt zurück, Zeiten werden
freigegeben, ein Dokument entsteht (API-012). Eingerichtet werden die
Webhooks im Browser unter **Einstellungen → Webhooks** oder über
`/api/v1/webhooks`; das beschreibt das
[Benutzerhandbuch](../handbuch/benutzerhandbuch.md). Für den Betrieb zählt:

- **Zeitgeber:** nichts Neues einzurichten. Ein Ereignis wird mit der
  Änderung zusammen in der Datenbank vorgemerkt; zugestellt wird jede
  Minute vom vorhandenen `rentalars-jobs.timer` (`run_jobs`), nach den
  Aufgaben im Hintergrund und den Kalendern – höchstens 30 Sekunden oder
  200 Zustellungen je Lauf, der Rest in der nächsten Minute. Eine lange
  Aufgabe im selben Lauf verzögert die Webhooks wie die Kalender.
- **Wiederholungen:** Nur eine Antwort 2xx gilt als zugestellt. Sonst
  versucht Rentalars es nach 1 Minute, 5 Minuten, 30 Minuten, 2 Stunden
  und 12 Stunden erneut – sechs Versuche in etwa 15 Stunden. Je Versuch
  wartet es höchstens 10 Sekunden auf jeden Schritt, 20 insgesamt.
  Weiterleitungen (3xx) folgt es nicht.
- **Abschalten:** Scheitern 10 Zustellungen in Folge endgültig, schaltet
  Rentalars den Webhook ab und benachrichtigt alle, die die Einstellungen
  ändern dürfen, als „Fehler der Anwendung“, voreingestellt auch per
  E-Mail. Das Abschalten steht im Änderungsprotokoll (`system:jobs`).
  Wartende Zustellungen bleiben und gehen raus, sobald der Webhook wieder
  eingeschaltet ist.
- **Aufbewahrung:** Zustellungen bleiben 30 Tage, mit dem Anfang (1.000
  Zeichen) jeder Antwort des empfangenden Systems; dann löscht sie die
  tägliche Wartung. Die Frist ist fest.
- **Netz:** Der Dienst `rentalars-jobs` – und für „Test senden“ und
  „Erneut senden“, die sofort im Browser laufen, auch der Dienst
  `rentalars` – muss die empfangenden Systeme per HTTP oder HTTPS
  erreichen dürfen. Ein empfangendes System im internen Netz erreicht
  Rentalars nur mit Freigabe unter `[network] allow_internal`
  (oben, „Verbindungen ins interne Netz“); bis dahin scheitert jede
  Zustellung, und nach zehn endgültig gescheiterten schaltet sich der
  Webhook ab. Einen Proxy nimmt Rentalars aus der Umgebung des
  Dienstes (`https_proxy`, `http_proxy`), außer für Adressen auf diesem
  Server. Zertifikate werden gegen die Zertifizierungsstellen des Systems
  geprüft; ein internes, selbst signiertes Zertifikat scheitert mit
  „Zertifikat“.
- **Geheimnisse:** Das Geheimnis, mit dem jede Nachricht signiert wird,
  liegt mit dem `secret_key` der Konfiguration verschlüsselt in der
  Datenbank. Wird der `secret_key` geändert, lässt es sich nicht mehr
  lesen: Zustellungen scheitern mit dem Hinweis, ein neues zu erzeugen
  („Geheimnis neu erzeugen“, dann ins empfangende System übernehmen).

Von Hand stellt `sudo rentalars run_jobs` sofort zu, was fällig ist.

## Karten

Anschriften haben einen Link „Route in Google Maps“ und eine
zoombare Karte von OpenStreetMap; die Fahrten eines Projekts stehen mit
ihren Routen in Zeitplanung und Überblick (UIX-033, UIX-034, PRJ-097). Das
Benutzerhandbuch beschreibt die Bedienung. Für den Betrieb zählt, **was
das Haus verlässt** (NFA-050):

| Was | Wer fragt | Wohin | Wann |
|---|---|---|---|
| Wo eine Anschrift liegt | **der Server** (Dienst `rentalars`) | Kartensuche, voreingestellt Nominatim `https://nominatim.openstreetmap.org/search` | erst, wenn jemand „Karte anzeigen“ drückt – mit „Karten sofort laden“ schon beim Öffnen der Seite –, und je Anschrift nur einmal |
| Die Kartenbilder | **der Browser** der Person, mit der Adresse der Installation (Schema und Host) als Referer | Kartenserver, voreingestellt `https://tile.openstreetmap.org/…` | mit der Karte |
| Eine Route | **der Browser** der Person | `https://www.google.com/maps/dir/…` mit Zwischenhalten und Ziel; ohne Start – Google Maps beginnt am Standort der Person | nur beim Klick auf „Route in Google Maps“, in einem neuen Tab |

Vorher geht keine Anschrift und keine Anfrage an einen fremden Server; der
Schalter „Karten sofort laden“ (Einstellungen → Firmendaten und
Grundeinstellungen) ist aus. Entfernungen und Routen berechnet Rentalars
nur, wenn auf diesem Server der freiwillige Routendienst eingerichtet ist
(unten, „Routendienst“) – sonst nicht.

- **Die Kartensuche** schickt nur den Text der Anschrift (`q`), kein
  Projekt und keinen Namen. Ihr User-Agent nennt die
  Installation, wie es die Regeln von Nominatim verlangen:
  `Rentalars/1.0.0 (maps; +https://rentalars.example.de)` – nur Schema und
  Host aus `url`, nie ein Pfad oder Zugangsdaten (ohne brauchbare `url`
  nur `Rentalars/1.0.0 (maps)`). Sie folgt keinen Weiterleitungen.
  Sie hält sich an die Regeln des öffentlichen Nominatim: höchstens eine
  Anfrage je Sekunde für die ganze Installation (alle Arbeitsprozesse
  teilen sich dafür die Sperrdatei `geocoder.lock` im Datenordner),
  höchstens fünf neue Anschriften je geöffneter Karte – der Rest beim
  nächsten Öffnen –, und keine Vorschläge beim Tippen. Jede Antwort wird
  gemerkt, auch „nicht gefunden“; Netzfehler zeigt die Karte an und merkt
  sie sich nicht. Die Positionen gelten je Anschrift für alle Datensätze
  mit derselben Anschrift; von Hand korrigierte stehen im Verlauf des
  Datensatzes. Positionen von Anschriften, die niemand mehr nennt, löscht
  die tägliche Wartung, die eines anonymisierten Kunden sofort.
- **Netz:** Der Dienst `rentalars` muss die Kartensuche per HTTPS
  erreichen; einen Proxy nimmt er wie bei den Webhooks aus der Umgebung des
  Dienstes. Die Browser der Nutzer brauchen den Kartenserver. Ist er nicht
  erreichbar, bleibt die Karte grau, die Liste der Orte darunter steht
  trotzdem; ist die Kartensuche nicht erreichbar, sagt die Karte es („Die
  Kartensuche ist nicht erreichbar.“), und die Positionen lassen sich von
  Hand setzen.
- **Sicherheit der Seiten:** Leaflet, das die Karte zeichnet, liegt auf dem
  eigenen Server (`static/vendor/leaflet`, BSD-2-Clause) und wird erst mit
  der ersten Karte geladen. Nur Seiten, die eine Karte zeigen können,
  erlauben dem Browser Bilder vom eingestellten Kartenserver
  (Content-Security-Policy); alle anderen bleiben, wie sie waren.
- **Die Regeln von OpenStreetMap für Kartenbilder** (Tile Usage Policy)
  verlangen, dass jede Anfrage sagt, von welcher Seite sie kommt. Rentalars
  schickt sonst überall `Referrer-Policy: same-origin`, sodass der Browser
  den Kartenbildern keinen Referer mitgäbe – OpenStreetMap
  würde dann mit „Access blocked 403 … App is not following the tile
  usage policy“ antworten. Deshalb (UIX-034) fragt die Karte ihre Bilder mit
  `referrerPolicy: strict-origin-when-cross-origin` an: Der Kartenserver
  erfährt die Adresse der Installation (Schema, Host, Port), keinen Pfad
  und kein Projekt; die Seiten selbst behalten `same-origin`. Der Rest der
  Regeln ist eingehalten: Namensnennung „© OpenStreetMap-Mitwirkende“ mit
  Link auf `/copyright`, Bilder erst nach „Karte anzeigen“, kein
  Vorausladen und kein Massenabruf, normales Zwischenspeichern im Browser
  (kein Service Worker, keine Kopfzeilen gegen den Cache). Wer den
  Referer nicht hinausgeben will oder viele Karten öffnet, trägt einen
  eigenen Kartenserver ein (unten). Steht nach der Aktualisierung noch
  „Access blocked“ da, hilft meist ein Neuladen ohne Cache; sonst kann ein
  Browser-Zusatz den Referer unterdrücken.

**Der Abschnitt `[maps]`** in `/etc/rentalars/rentalars.conf` ist
freiwillig; ohne ihn gelten die Server von OpenStreetMap:

```ini
[maps]
# tile_url = https://tile.openstreetmap.org/{z}/{x}/{y}.png
# geocoder_url = https://nominatim.openstreetmap.org/search
# attribution =
# attribution_url = https://www.openstreetmap.org/copyright
# max_zoom = 19
```

- `tile_url` – die Kartenbilder mit `{z}`, `{x}`, `{y}` (und, wenn der
  Server es braucht, `{s}`). **Leer schaltet die Karten ganz ab:** kein
  „Karte anzeigen“, keine Kartensuche; die Links „Route in Google Maps“ und
  die Fahrten bleiben.
- `geocoder_url` – eine Suche, die wie Nominatim antwortet
  (`?q=…&format=jsonv2`), etwa ein eigener Nominatim-Server. Leer: keine
  Suche; Positionen setzt man auf der Karte von Hand.
- `attribution` und `attribution_url` – wem die Kartenbilder eines anderen
  Anbieters zu verdanken sind; leer steht „© OpenStreetMap-Mitwirkende“
  mit dem Link zum Copyright von OpenStreetMap.
- `max_zoom` – wie weit sich hineinzoomen lässt (1 bis 22).

Adressen müssen mit `https://` oder `http://` beginnen, sonst startet
Rentalars nicht und nennt den Fehler. Nach einer Änderung `sudo systemctl
restart rentalars`. Wer viele Karten öffnet oder keine Daten an
OpenStreetMap geben will, betreibt eine eigene Kartensuche und einen
eigenen Kartenserver und trägt sie hier ein; die Regeln der öffentlichen
Server von OpenStreetMap erlauben nur maßvollen Gebrauch.

## Routendienst

Rentalars plant Fahrzeuge und Anhänger auf den Fahrten eines
Projekts, abgerechnet nach Kilometern (LOG-001 ff., im Benutzerhandbuch
unter „Logistik“). Die geplanten Kilometer einer Fahrt trägt man von Hand
ein. Wer mag, richtet zusätzlich einen **Routendienst** ein (LOG-017):
Dann bietet der Dialog eines Fahrzeugs auf einer Fahrt „Geplante km aus
der Route vorschlagen“ – ein Vorschlag, der sich immer ändern lässt. Der
Routendienst ist freiwillig, lässt sich jederzeit nachinstallieren und
wieder entfernen; ohne ihn fehlt nur der Knopf.

Die Positionen der Orte gehen dabei an keinen fremden Dienst (NFA-050): Der
Routendienst ist das Programm **Routino** auf diesem Server, mit der Karte
von OpenStreetMap für Deutschland oder ein Bundesland – oder ein
OSRM-Server, den du selbst betreibst oder der in Deutschland steht. Wo die
Orte liegen, ermittelt Rentalars wie für die Karten (oben, „Karten“) und
merkt es sich; eine von Hand gesetzte Position zählt.

### Einrichten

```sh
sudo rentalars route install --region bayern --dry-run   # zeigen, was geschähe – auch ohne root
sudo rentalars route install --region bayern             # einrichten, mit der Karte eines Bundeslands
sudo rentalars route install                             # ganz Deutschland (ab 4 GB Arbeitsspeicher)
```

Regionen: `germany` oder ein Bundesland – `baden-wuerttemberg`, `bayern`,
`berlin`, `brandenburg`, `bremen`, `hamburg`, `hessen`,
`mecklenburg-vorpommern`, `niedersachsen`, `nordrhein-westfalen`,
`rheinland-pfalz`, `saarland`, `sachsen`, `sachsen-anhalt`,
`schleswig-holstein`, `thueringen`. Für Fahrten über die Landesgrenze
hinaus braucht es die Karte von ganz Deutschland. Ein Neustart von
Rentalars ist nicht nötig.

Der Befehl

1. prüft das System (Ubuntu 24.04 oder 26.04, Raspberry Pi OS auf Basis von
   Debian 13), den Arbeitsspeicher und den freien Platz. Mit weniger als
   4 GB Arbeitsspeicher verlangt er ein Bundesland oder ausdrücklich
   `--region germany` und rechnet im sparsamen Modus von Routino;
2. installiert das Paket `routino` der Distribution (Ubuntu: universe);
3. lädt die Karte von Geofabrik (`download.geofabrik.de`) und prüft sie
   gegen die dort veröffentlichte MD5-Prüfsumme – oder nimmt mit `--file
   DATEI.osm.pbf` eine Datei, die schon auf dem Server liegt (ohne
   Internet; ein Dateiname von Geofabrik behält seine Region);
4. bereitet sie für Kraftfahrzeuge auf (`planetsplitter`, Fortschritt in
   `/opt/rentalars/routes/planetsplitter.log`);
5. löscht den Download (außer mit `--keep-file`), fährt als Benutzer des
   Dienstes eine Testroute zwischen zwei Städten der Region und schreibt
   erst dann `/etc/rentalars/route-local.conf`. Rentalars liest die Datei
   bei jeder Nutzung.

**Wie groß, wie lange** – geschätzt, nicht gemessen; der Befehl nennt vor
dem Start, wie viel Platz er braucht:

| Karte | Download | Freier Platz währenddessen | Aufbereiten |
|---|---|---|---|
| Deutschland | etwa 4,5 GB | etwa 23 GB | etwa 1 bis 3 Stunden, auf einem Raspberry Pi länger |
| Bayern | etwa 800 MB | etwa 4,5 GB | etwa 10 bis 45 Minuten |
| Berlin | etwa 90 MB | unter 1 GB | wenige Minuten |

Nach dem Aufbereiten bleibt nur die aufbereitete Karte; sie ist deutlich
kleiner als der Platz währenddessen.

**Ein eigener Routing-Server** (OSRM oder kompatibel) statt Routino:
`sudo rentalars route register --url https://routing.example.de`. Die
Adresse muss mit `https://` beginnen – `http://` nur auf diesem Rechner.
Der Befehl prüft eine Route von Frankfurt nach Würzburg. Rentalars schickt
dem Server die Positionen der Orte einer Fahrt, sonst nichts, und folgt
keinen Weiterleitungen.

```sh
rentalars route status                 # Art, Region, Alter und Größe der Karte, Version, Testroute
sudo rentalars route update            # dieselbe Region neu laden und aufbereiten
sudo rentalars route remove            # entfernen; danach wieder von Hand
sudo rentalars route remove --keep-data   # Karte und Paket behalten
```

**Aktualisieren:** Straßen ändern sich. `status` und die Einstellungen
zeigen, wie alt die Karte ist, und raten nach 180 Tagen zu `route update`.
Das Update bereitet die neue Karte in einem eigenen Ordner auf und
wechselt erst, wenn sie ihre Testroute gefahren ist – bricht es ab, bleibt
die bisherige Karte in Betrieb. Für eine Karte aus `--file` lädt `update`
nichts; dann `route install --file` mit einer neueren Datei. Einen Zeitplan
für automatische Updates gibt es nicht.

**Im Browser:** Einstellungen → Firmendaten und Grundeinstellungen zeigt
Administratoren den Kasten „Routendienst“ – eingerichtet oder nicht, Art,
Region, Stand der Karte und die Befehle. Ist die Datei kaputt oder fehlt
die Karte, verschwindet der Knopf im Dialog, und der Kasten nennt den
Grund.

### Was wo liegt

| Was | Wo |
|---|---|
| Aufbereitete Karte, Protokoll des Aufbereitens | `/opt/rentalars/routes/` (nur root ändert, lesbar für alle – die Karte ist öffentlich) |
| Für Rentalars: Art, Region, Stand der Karte, Programm, Ordner oder Adresse | `/etc/rentalars/route-local.conf` (root, lesbar für alle) |

**Sicherung:** Die Karte und `route-local.conf` stecken nicht in der
Sicherung ([sicherung.md](sicherung.md)); auf einem neuen Server richtest
du den Routendienst mit `sudo rentalars route install` neu ein. Die
Kilometer der Fahrten liegen in der Datenbank und kommen mit ihr zurück.

## Buchhaltung: Lexware Office und DATEV

Rechnungen und Stornorechnungen gehen an **Lexware Office**,
und die Rechnungen eines Zeitraums lassen sich als **DATEV-Buchungsstapel**
für die Steuerberatung herunterladen (DOK-011, DOK-012). Eingerichtet wird
beides im Browser unter **Einstellungen → Buchhaltung**
([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 16). Für
den Betrieb zählt:

- **Lexware Office braucht den Weg nach außen:** HTTPS zu
  `api.lexware.io`, vom Dienst `rentalars` (die Übergabe startet aus einer
  Seite oder beim Erstellen einer Rechnung) und vom Dienst
  `rentalars-jobs` (der Zeitgeber holt nach, was nicht gleich starten
  konnte). Ein Proxy aus der Umgebung des Dienstes wird benutzt.
- **Jede Übergabe ist eine Aufgabe im Hintergrund** der Art `lexware`. Sie
  steht unter „Mein Konto → Aufgaben im Hintergrund“ dessen, der sie von
  Hand gestartet hat; ihre Ausgabe im Protokoll von `rentalars` bzw.
  `rentalars-jobs`. Auf der Seite Buchhaltung stehen alle Übergaben, die
  warten oder fehlgeschlagen sind, mit dem Grund. Lexware Office nimmt
  höchstens zwei Anfragen je Sekunde an; Rentalars hält sich daran.
- **Der API-Schlüssel** von Lexware Office liegt mit dem `secret_key`
  verschlüsselt in der Datenbank und wird nie wieder angezeigt. Wird der
  `secret_key` geändert, sagt die Seite Buchhaltung, dass er sich nicht
  mehr lesen lässt; trag ihn dann neu ein. Im vollständigen Export und im
  Änderungsprotokoll steht er nicht.
- **DATEV** braucht keine Verbindung: Die Dateien (CSV im DATEV-Format,
  Windows-1252) lädt man im Browser herunter oder über
  `/api/v1/accounting/datev/bookings` und `…/debitors`. Jeder Download
  steht im Zugriffsprotokoll.
- **Rechte:** Die Seite Buchhaltung und der DATEV-Export brauchen
  Lesezugriff auf die Einstellungen **und** das Recht, Preise zu sehen;
  Ändern braucht Schreibzugriff auf die Einstellungen. Die mitgelieferte
  Rolle **„Nur-Lesen“** – gedacht unter anderem für die Buchhaltung – hat
  keinen Zugriff auf die Einstellungen: Gib ihr unter Einstellungen →
  Rollen bei „Einstellungen“ die Stufe „lesen“, oder lege eine eigene Rolle
  „Buchhaltung“ an.

Es gibt außerdem den Menüpunkt **Buchhaltung** mit den
**Ausgangsbelegen** – allen Belegen an Kunden mit ihren Summen – und der
Monatsabrechnung der Servicefälle
(ihre Adressen beginnen mit `/accounting/monthly/`). Die Ausgangsbelege sieht, wer Preise sehen und alle Projekte lesen
darf – ohne Zugriff auf die Einstellungen; über die API
`/api/v1/accounting/documents` und `…/totals`. DATEV-Export und Übergabe
an Lexware Office bleiben unter Einstellungen → Buchhaltung.

Die Formate von Lexware Office und DATEV sind nach deren veröffentlichten
Beschreibungen gebaut; die erste Übergabe und den ersten Import in DATEV
prüft ihr am besten zusammen mit der Steuerberatung.

## Vollständiger Datenexport

Alle Daten in offenen Formaten, in einer ZIP-Datei (IMP-006) – zum Lesen
in anderen Programmen und für das eigene Archiv. Im Browser
unter **Einstellungen → Sicherung**, Abschnitt **„Lesbarer Export aller
Daten“**, Knopf **„Vollständigen Export erstellen“**; das darf nur, wer in den
Einstellungen löschen darf, also die Administratoren. Der Export läuft
als Aufgabe im Hintergrund; ist er fertig, bietet die Seite der Aufgabe die
Datei zum Herunterladen an (bis zum Ablauf der Frist für Ergebnisse,
voreingestellt 7 Tage) – nur dem, der ihn gestartet hat. Über die API:
`POST /api/v1/exports/full`, danach `/api/v1/jobs/{id}` und
`/api/v1/jobs/{id}/result`. Jeder Export steht im
Änderungsprotokoll, auch der auf dem Server; das Herunterladen im Browser
oder über die API steht außerdem im Zugriffsprotokoll.

Auf dem Server schreibt derselbe Export

```sh
sudo rentalars export_data /var/lib/rentalars/rentalars-export.zip
```

Der Befehl läuft – wie alle Befehle der Anwendung – unter dem Dienstkonto;
das Ziel muss also in einem Ordner liegen, in den das Dienstkonto schreiben
darf, etwa `/var/lib/rentalars`, und darf noch nicht vorhanden sein. Am Ende
sagt er, wie viele Tabellen, Zeilen und Dateien er geschrieben hat. Hol die
Datei danach dort weg.

Was in der ZIP-Datei steht:

| Ordner | Inhalt |
|---|---|
| `json/` | jede Tabelle als JSON-Datei im Format von Django, z. B. `json/customers.customer.json` |
| `csv/` | dieselben Tabellen als CSV (Semikolon, UTF-8), eine Spalte je Feld; Verweise auf andere Tabellen stehen als ID |
| `dateien/` | alle gespeicherten Dateien – Projektdateien, Mailanhänge, Dokumente, Fotos, Prüfprotokolle, Nachweise, Fotos und Videos aus dem Chat – unter dem Namen, den die Tabellen nennen |
| `LIESMICH.txt` | was enthalten ist und was nicht |

**Nicht** enthalten sind Geheimnisse, die außerhalb dieser Installation
nichts nützen: die Prüfwerte der Passwörter und der API-Token, die
Geheimnisse der Zwei-Faktor-Anmeldung, die Passwörter der Postfächer, das
Einrichtungs-Token, der API-Schlüssel von Lexware Office, die Codes der Einsatzanfragen per Mail (wer einen hat, kann die
Anfrage beantworten; die Tabelle steht mit leerem Code darin),
die Schlüssel der Kalender-Links von Produkten, Modellen und Exemplaren
(die Tabelle steht ohne sie darin – wer einen hat, sieht den Kalender
ohne Anmeldung), das verschlüsselte Passwort des Suchkontos des
Verzeichnisses (LDAP).
Ebenso nicht: Sitzungen, Anmeldeversuche, die Aufgaben im Hintergrund und
ihre Ergebnisse (also auch keine früheren Exporte), und die
Webhooks samt Zustellungen – die Adresse eines Webhooks kann selbst ein
geheimer Link sein.

**Der Export enthält die personenbezogenen Daten aller Kunden, Personen und
Nutzer** und ist nie verschlüsselt, auch wenn die Sicherungen es sind.
Behandle ihn so vertraulich wie eine Sicherung und lösche ihn, wenn er
nicht mehr gebraucht wird. Eine Sicherung ersetzt er nicht: Rentalars lässt
sich aus ihm nicht wiederherstellen ([sicherung.md](sicherung.md), „Der
lesbare Export ist keine Sicherung“).

**Export im Importformat** (IMP-017). Davon zu unterscheiden
ist der Export einer einzelnen Liste im Format ihres Imports – Material,
Produkte, Kunden, Personal – unter Einstellungen → Import und Export, im
Browser und über `GET /api/v1/imports/{art}/export`: eine CSV-Datei im
Klartext, die sich wieder importieren lässt ([import.md](import.md),
„Export im Importformat“). Er wird beim Senden geschrieben, in Teilen zu
2.000 Datensätzen, und belegt keine Aufgabe im Hintergrund.

## Die API: Grenzen und Schutz

Programme, die mit Rentalars über die API sprechen (`/api/v1/`), merken
davon nichts, solange sie sich vernünftig verhalten. Drei Regeln schützen
den Betrieb (API-010, API-011):

- **Höchstens 600 Aufrufe je Token und Minute.** Die Zahl steht unter
  Einstellungen → Firmendaten und Grundeinstellungen („API-Aufrufe je Token
  und Minute“); 0 schaltet die Grenze ab. Wer darüber kommt, bekommt bis zum
  Ende der Minute die Antwort 429 `throttled` mit `Retry-After` (Sekunden
  bis zur nächsten Minute). Jede gezählte Antwort trägt `X-RateLimit-Limit`
  und `X-RateLimit-Remaining`. Gezählt werden nur Aufrufe mit einem Token,
  nicht die des Browsers.
- **Kein doppeltes Ausführen.** Ein schreibender Aufruf mit dem Kopf
  `Idempotency-Key` wird einmal ausgeführt; kommt derselbe Aufruf mit
  demselben Schlüssel noch einmal – etwa weil die Verbindung abriss –,
  bekommt er die gespeicherte Antwort mit `Idempotent-Replayed: true`. Die
  Antworten werden einen Tag lang aufgehoben. Ein Schlüssel gehört (aus einer
  Code-Prüfung) zum Aufrufer – Token bzw. Sitzung –
  und zum Aufruf (Methode, Adresse, Inhalt). Die gespeicherte Antwort kommt
  erst nach denselben Prüfungen wie ein neuer Aufruf: Anmeldung, Rechte am
  Modul, Grenze der Aufrufe und Zugriff auf den Datensatz. Ein anderer
  Aufrufer mit demselben Schlüssel bekommt sie nie; derselbe Aufrufer mit
  anderem Inhalt bekommt 409 `idempotency_key_reused`.
- **Kein Überschreiben fremder Änderungen.** Jede JSON-Antwort auf ein GET
  trägt ein `ETag`. Schickt ein Programm es beim Ändern als `If-Match` mit
  und hat inzwischen jemand anderes den Datensatz geändert, lehnt Rentalars
  mit 412 `precondition_failed` ab. Mit `If-None-Match` antwortet ein GET
  mit 304, wenn sich nichts geändert hat. Rentalars vergleicht und
  schreibt in einem Zug unter einer Sperre (Tabelle
  `api_writelock`, auf MariaDB zusätzlich die Zeile des Datensatzes), so
  dass zwei gleichzeitige Änderungen derselben Fassung nicht beide
  durchkommen; im Browser gilt weiter: wer zuletzt speichert, gewinnt.

Zähler und gespeicherte Antworten liegen in der Datenbank – so gelten sie
für alle Arbeitsprozesse zugleich – und werden von der täglichen Wartung
aufgeräumt. Bremst die Grenze ein Programm, das wirklich mehr braucht,
erhöhe die Zahl.

**Tokens erstellen andere Tokens nur in Grenzen** (AUT-021).
Ein Token kann über `POST /api/v1/tokens` weitere Tokens erstellen, aber
nie mehr öffnen, als es selbst hat:

- Ein auf Module beschränktes Token – etwa das der Rentalars-App –
  erstellt keine Tokens (403) und sieht und widerruft unter
  `/api/v1/tokens` nur sich selbst, nicht die übrigen Tokens seines
  Nutzers.
- Ein Token mit Ablaufdatum erstellt nur Tokens, die spätestens mit ihm
  ablaufen; `expires_at` ist dann Pflicht (sonst 400).
- Ein Token „nur lesen“ ändert nichts: Es erstellt keine Tokens
  (403), widerruft keine, beendet keine Sitzungen und ändert weder
  die Benachrichtigungen seines Nutzers noch Verfügbarkeiten oder Kalender.

Im Browser (Mein Konto → API-Token) legt jeder Nutzer Tokens an.

## Die Rentalars-App für Android

Die Begleit-App (Rentalars-App 1.0, Android 8 oder neuer) bringt
Packlisten und Zeiterfassung aufs Telefon, auch ohne Netz
([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 2). Sie
ist **nicht Teil des Pakets** von Rentalars und wird eigens ausgeliefert –
als signierte APK, die ihr direkt oder über eine Geräteverwaltung auf die
Telefone bringt. Der Server-Teil steckt in Rentalars; einzurichten
ist auf dem Server nichts. Für den Betrieb zählt:

- **Erreichbarkeit:** Die Telefone sprechen Rentalars über die API an,
  unter derselben Adresse wie der Browser (`url` unter `[rentalars]`). Die
  App nimmt **nur https mit einem Zertifikat, dem Android von Haus aus
  vertraut** – Let's Encrypt oder ein gekauftes Zertifikat; ein selbst
  signiertes oder eines eurer eigenen Zertifizierungsstelle genügt nicht.
  Weiterleitungen folgt sie nicht; unter `/api/v1` leitet Rentalars nicht
  weiter. Ist Rentalars nur im eigenen Netz erreichbar, gleicht die App
  ab, sobald das Telefon dort (WLAN oder VPN) ist; dazwischen arbeitet sie
  ohne Netz.
- **Uhrzeit des Servers:** Die App rechnet mit der Zeit des Servers, die
  jede Antwort im Kopf `Date` trägt. NGINX setzt ihn; ein weiterer Proxy
  davor muss ihn durchlassen. Die Uhr des Servers sollte stimmen (NTP, bei
  Ubuntu voreingestellt).
- **Anmeldung und Token:** Die App meldet sich einmal mit Name, Passwort
  und gegebenenfalls dem Code der Zwei-Faktor-Anmeldung an
  (`/api/v1/auth/login`) und erstellt sich ein eigenes Token, beschränkt
  auf `packing`, `projects` und `time_tracking` – auch
  `email` (Chat, Mails, Preisübersicht, `/mail/unknown`) –, gültig
  30, 90 oder 180 Tage. Es steht beim Nutzer unter Mein Konto → API-Token;
  widerrufen dort oder durch Abmelden in der App. Es zählt gegen die Grenze
  von 600 Aufrufen je Minute wie jedes Token; ein Abgleich mit bis zu 400
  Änderungen ist ein Aufruf. Die Rechte sind die des Nutzers: Wer
  Packlisten nur lesen darf – die mitgelieferte Rolle Freie Kraft –, sieht
  sie in der App nur und kann dort nicht abhaken. Die Rolle Crew packt
 in ihren Projekten, trägt aber kein Material nach
  ([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 10,
  „Packen mit der Rolle Crew“).
- **Packlisten ohne Netz** (PCK-026): `GET /api/v1/offline/packlists`
  liefert die Projekte im Status „Bestätigt – Einzelheiten offen“, „Bestätigt“
  und „Unterwegs“, deren Packliste der Aufrufer lesen darf – mit Nummer,
  Name, Status, Zeitraum, Ort, Kunde (leer, wer nur die Einsatzsicht hat –
  den Überblick und die Packliste), ob er abhaken darf, den Packlisten und
  der Zeit des Servers. Dieser Abruf legt nichts an: Ein
  Projekt bekommt seine Hauptpackliste, sobald es in einen dieser Status
  kommt; ein
  Projekt ohne Packliste steht mit `packlists: []` da.
- **Abgleich** (PCK-027): `POST /api/v1/projects/{p}/packlists/{id}/sync`
  nimmt höchstens 1.000 Änderungen auf einmal – je Zeile die gepackte oder
  die zurück abgehakte Menge mit dem Zeitpunkt, zu dem sie auf dem
  Telefon gemacht wurde. Jede Zeile merkt sich, wann sich jede der beiden
  Mengen zuletzt geändert hat, auf welchem Weg auch immer; eine Änderung
  vom Telefon gilt nur, wenn sie **später** ist (gleich spät: der Server
  gewinnt; ein Zeitpunkt in der Zukunft zählt als jetzt). Rentalars nimmt
  die Änderungen in der Reihenfolge ihrer Zeitpunkte, in einem Zug und
  mit gesperrten Zeilen, und mit denselben Grenzen wie im Browser; was
  sie verletzt, lehnt es mit Grund ab, statt es zu kürzen. Die Antwort
  nennt je Änderung `applied`, `older` oder `refused` und die ganze
  Packliste. Ungültige Eingaben – auch ein Zeitpunkt ohne Zeitzone oder
  vor dem Jahr 2000 – beantwortet es mit 400. Der Abgleich **gibt nie
  aus und bucht keine Rücknahme**; das bleibt ein Schritt im Browser.
  Abgehakte Rücknahmen aus der App lösen den Webhook `packing.returned`
  aus wie im Browser – nur, wenn eine zurück abgehakte Menge
  steigt, einmal je Abgleich.
- **Versionen und Uhrregel** (aus einer Code-Prüfung). Jede
  Packlistenzeile hat eine `version`, die jede Änderung der gepackten oder
  zurück abgehakten Menge um eins erhöht – im Browser, über die API und im
  Abgleich. Eine Änderung darf `base_version` (die Version beim Laden)
  und eine `change_id` (höchstens 64 Zeichen, etwa eine UUID) mitbringen:
  - Mit `base_version` entscheidet die Version: weicht sie ab, ist das
    Ergebnis `conflict`, der Stand des Servers bleibt und steht in der
    Antwort (`server`); steht dort schon die gewünschte Menge, ist es
    `applied`.
  - Ohne `base_version` gilt die Zeitregel von oben,
    eindeutig: Der Server liest seine Uhr erst nach dem Sperren; ein
    Zeitpunkt in der Zukunft zählt als jetzt, die Änderungen bleiben aber
    in ihrer Reihenfolge (Zeitpunkt, dann ursprünglicher Zeitpunkt, dann
    Reihenfolge im Aufruf); gegen den Server zählt nur ein echt späterer
    Zeitpunkt; der gemerkte Zeitpunkt geht nie zurück.
  - Eine `change_id` wird je Nutzer 30 Tage gemerkt; kommt dieselbe
    Änderung noch einmal, antwortet Rentalars mit dem ersten Ergebnis und
    `replayed` – samt seinem `reason`. Dieselbe Kennung für eine
    andere Änderung wird abgelehnt.

  Eine offene Packliste im Browser lädt sich nach einem Abgleich neu.
- **Material nachtragen** braucht Schreibrecht auf das Projekt
  oder Packen für alle Projekte. Eine gepackte Menge über der Packliste
  lehnt der Abgleich ab, mit `reason` `needs_project_write` (wer
  nachtragen darf, steht in der Meldung) oder `above_packing_list`; die
  übrigen Änderungen gelten. `/offline/packlists` nennt je Projekt
  `can_add_material`; `add-material` ohne dieses Recht gibt 403 mit
  `needs_project_write`. `DELETE` an Packlisten, Übergaben und Entnahmen
  braucht wie im Browser „bearbeiten“.
- **Projekte und Servicefälle ohne Netz.** Projekte und
  Servicefälle tragen `field_changed_at` (je Feld der Zeitpunkt der
  letzten Änderung, gleich auf welchem Weg); `PATCH`, Status und
  Wiedervorlage nehmen `changed_at` und übernehmen ein Feld nur, wenn es
  später ist – dieselbe Uhrregel wie beim Abgleich der Packlisten, unter
  derselben Sperre wie `If-Match`. Die Antwort nennt `applied`; ein nicht
  mehr erlaubter Statuswechsel gibt 409 mit dem Projekt.
- **Eigene Daten.** `GET`/`PATCH /api/v1/people/me/profile`,
  `/people/me/absences` und `/people/me/deployments` brauchen kein Recht am
  Modul Personal; `GET /me` nennt `server_version`. Die E-Mail-Adresse –
  zugleich die Anmeldeadresse – ändert dort nur ein Token ohne
  Modulbeschränkung oder mit dem Modul „E-Mail“ (das Token der App); andere Tokens bekommen 403 `token_scope`.
- **Zeiten** schickt die App als fertige Einträge an `POST
  /api/v1/time-entries` mit `Idempotency-Key` (oben); es gelten die Regeln
  des Servers.
- **Verloren gegangenes Telefon:** das Token des Nutzers im Browser
  widerrufen (oder als Administrator das Konto deaktivieren). Was auf dem
  Telefon noch nicht abgeglichen war, lässt sich dann nicht mehr
  abgleichen; gespeichert ist es dort verschlüsselt.

## Die Datenbank umziehen

Mit einem Befehl ziehen alle Daten in eine **neue, leere Datenbank** um
(NFA-068) – auf einen vorhandenen MariaDB-Server, auf einen anderen, oder
zurück auf diesen Server. Gründe: Der Betrieb will seine Datenbanken
zentral führen; ein Datenbankserver, der seine Dateien verschlüsselt;
ein Wechsel des Datenbankbenutzers.

Zu einem anderen Server – Datenbank und Benutzer dort vorbereitet wie in
[installation.md](installation.md), „Vorhandener Datenbankserver“:

```sh
sudo rentalars move-database --host db.example.de --name rentalars --user rentalars     --password-file /root/db-passwort.txt --tls-ca /root/db-ca.pem
```

Zurück auf diesen Server (MariaDB wird bei Bedarf installiert, Datenbank und
Benutzer legt der Befehl an):

```sh
sudo rentalars move-database --local
```

Was geschieht:

1. Die neue Datenbank wird **geprüft, bevor sich irgendetwas ändert**: Sie
   muss leer sein; ihr Benutzer darf nicht root sein und nur Rechte auf
   diese eine Datenbank haben (wie bei der Installation).
2. Eine **Sicherung** des jetzigen Stands entsteht (wird nie automatisch
   gelöscht).
3. Rentalars wird **angehalten**, und alle Daten werden kopiert.
4. **Jede Tabelle wird verglichen** – Zahl der Zeilen und eine Prüfsumme
   über alle Werte. Nur wenn nicht ein Wert abweicht, wird die
   Konfiguration auf die neue Datenbank umgestellt und Rentalars wieder
   gestartet.
5. Geht unterwegs etwas schief, startet Rentalars wieder mit der alten
   Datenbank, als wäre nichts gewesen.

Rentalars ist für die Dauer der Schritte 3 und 4 nicht erreichbar; bei
einer üblichen Datenbank sind das Sekunden bis wenige Minuten.

**Die alte Datenbank bleibt stehen**, so wie sie im Augenblick des Umzugs
war – als Rückweg. Läuft alles ein paar Tage, entfernst du sie von Hand. Lag
sie auf diesem Server:

```sh
sudo mariadb -e "DROP DATABASE rentalars; DROP USER 'rentalars'@'localhost';"
```

(Welche Datenbank die bisherige war, sagt der Befehl am Ende; ihren
Benutzer nennt die Konfiguration von vorher, die er unter
`/etc/rentalars/rentalars.conf.before-move-…` aufhebt.) Lag sie auf einem
anderen Server, entfernt sie dessen Administrator. Wird MariaDB auf
diesem Server danach gar nicht mehr gebraucht, kann es mit
`sudo apt remove mariadb-server` gehen – vorher prüfen, dass `sudo rentalars
status` die neue Datenbank als erreichbar meldet.

## Rentalars entfernen

`sudo rentalars uninstall` entfernt Rentalars von diesem Server
(NFA-078) – in drei Arten, die man ausdrücklich wählen muss. Ohne Angabe
zeigt der Befehl nur diese Übersicht und tut nichts (Exit-Code 2).

| Angabe | Wirkung |
|---|---|
| `--dry-run` | Zeigt, was entfernt würde, und ändert nichts. Allein gegeben zeigt er die Wirkung von `--keep-data`; mit `--purge` die der vollständigen Löschung. |
| `--keep-data` | Entfernt die Anwendung, **erhält aber die Daten**. |
| `--purge` | Entfernt **nach ausdrücklicher Bestätigung auch Datenbank, Backups und Konfiguration**. |

`--keep-data` und `--purge` zusammen sind ein Fehler. Der Befehl braucht
root. Ohne Terminal (in einem Skript) verlangt `--keep-data` zusätzlich
`--yes`.

**Die Bestätigung bei `--purge`:** Am Terminal tippt man den Rechnernamen aus
der Adresse in der Konfiguration ein (gibt es keinen, das Wort `PURGE`),
genau so. Ohne Terminal genügt nur `--yes-i-really-want-to-delete-everything`
– `--yes` zählt hier nicht. Vorher fragt der Befehl nach einem **letzten
Backup** in einen Ordner (am Terminal voreingestellt `/root`, sonst
`--backup-to ORDNER`; `--no-final-backup` verzichtet darauf). Ein relativer
Ordner wird sofort in einen absoluten Pfad umgesetzt, und jede Meldung nennt
den absoluten Pfad. Ein Ordner, der selbst gelöscht würde, wird abgelehnt.
**Ohne Terminal** verlangt `--yes-i-really-want-to-delete-everything`
zusätzlich eine der beiden Angaben (`--backup-to` oder `--no-final-backup`);
fehlen beide, endet der Befehl mit Exit-Code 2, ohne etwas zu ändern – was mit
dem letzten Backup geschieht, wird nie stillschweigend entschieden. Sind die
Backups verschlüsselt, warnt der Plan, dass der Wiederherstellungsschlüssel
mitgelöscht wird.

### Was entfernt wird, was bleibt

| | `--keep-data` | `--purge` |
|---|---|---|
| Zeitgeber und Dienste `rentalars*` (angehalten, abgeschaltet, samt `.service.d`) | entfernt | entfernt |
| NGINX-Seite `rentalars`, `snippets/rentalars-proxy.conf`, `/var/www/rentalars-acme` (NGINX wird nur neu geladen, wenn `nginx -t` besteht) | entfernt | entfernt |
| `/opt/rentalars` (Versionen, Programm, virtuelle Umgebung, lokale KI mit Modellen, Karten des Routendienstes) | entfernt | entfernt |
| Befehl `/usr/local/bin/rentalars`, Sperrdateien `/run/rentalars-*.lock` | entfernt | entfernt |
| Datenbank und ihr Benutzer | bleiben | lokal: `DROP DATABASE` und `DROP USER` (der Benutzer nur, wenn seine Rechte nur diese Datenbank betreffen); entfernte Datenbank: nur die Tabellen und Sichten – Datenbank und Konto gehören deren Administrator |
| `/var/lib/rentalars` (Dateien, Fotos, Anhänge) | bleibt | entfernt |
| `/var/backups/rentalars` | bleibt | entfernt |
| `/etc/rentalars` (Konfiguration, Wiederherstellungsschlüssel, eigene Zertifikate, KI- und Routen-Einstellungen) | bleibt | entfernt |
| Zertifikat von Let's Encrypt | bleibt | `certbot delete` – außer eine andere NGINX-Datei nutzt es |
| Protokolle von NGINX `rentalars.*` | bleiben | entfernt |
| MariaDB-Einstellungen `60-rentalars.cnf`, `62-rentalars-memory.cnf` und das Protokoll langsamer Abfragen `rentalars-slow.log*` | bleiben | entfernt, wenn keine andere Datenbank auf diesem MariaDB liegt – nur dann auch das Protokoll, denn MariaDB schreibt weiter in eine gelöschte Datei, solange die Einstellungen bleiben; wirksam wird das Entfernen der Einstellungen erst nach einem Neustart von MariaDB (`sudo systemctl restart mariadb`), den das Skript nicht selbst auslöst |
| Systembenutzer und Gruppe `rentalars` | bleiben | entfernt (`www-data` verlässt die Gruppe `rentalars` vorher; nur wenn Benutzer `nologin` hat und sein Home `/var/lib/rentalars` ist) |

**Nie entfernt**, in keiner Art: installierte Pakete (NGINX, MariaDB,
certbot, llama.cpp-tools, routino …), der Schlüssel einer verschlüsselten
MariaDB (`/etc/mysql/rentalars-encryption`, `61-rentalars-encryption.cnf` –
MariaDB könnte ohne ihn nicht starten), andere Datenbanken (der Plan nennt
sie, auch eine alte, die `move-database` stehen ließ) und das Journal von
systemd. Die Standardseite von NGINX wird nicht wieder eingeschaltet.

**Sicherheitsvorkehrungen:** Jeder Pfad stammt aus den Konstanten der
Installation (`deploy/lib.sh`); ein Pfad zum Entfernen muss „rentalars“
enthalten und darf keine oberste Ebene sein; Verknüpfungen werden entfernt,
nicht verfolgt; `rm -rf` bleibt auf einem Dateisystem. Ein Daten- oder
Backup-Ordner, der nicht dem Standard der Installation entspricht, wird
genannt, aber nicht entfernt. Liegt ein Ordner, der bleiben soll (in
`--keep-data` beide, bei `--purge` ein nicht dem Standard entsprechender), in
einem Pfad, der entfernt wird – etwa `[backup] directory = /opt/rentalars/backups`
oder ein Link dorthin –, endet der Lauf mit Exit-Code 1, **bevor sich etwas
ändert**; auch der Probelauf zeigt das. Ist ein Standardordner ein Link
(`/var/lib/rentalars` auf ein anderes Laufwerk), entfernt der Befehl nur den
Link; das Ziel mit den Daten bleibt, und die Zusammenfassung sagt es mit dem
Pfad des Ziels, statt zu melden, die Daten seien entfernt. Auffällige Werte in
der Konfiguration stoppen den Lauf, bevor sich etwas ändert. Lässt sich die
Konfigurationsdatei nicht lesen (doppelter Schlüssel, fehlende
Abschnittsüberschrift), rechnet `--dry-run`/`--keep-data` mit den
Standardwerten und warnt (die Datenbank wird dann nicht angefasst); `--purge`
verweigert mit lesbarer Meldung und Exit-Code 1, ohne etwas zu ändern. Eine
Datenbank mit `host` auf 127.0.0.1 oder `::1` und einem anderen Port als 3306
(ein Tunnel zu einem anderen Server) gilt als entfernte Datenbank: nur ihre
Tabellen werden gelöscht. Die Reihenfolge: Dienste und Zeitpläne **anhalten**
(danach prüft der Befehl mit `systemctl is-active`, dass sie stehen – läuft
eine Einheit noch, bricht `--purge` ab, bevor etwas entfernt wird; bei
`--keep-data` wird es als Problem gemeldet), dann die Datenbank, erst danach
**abschalten** der Einheiten. Schlägt der Datenbankschritt fehl, sind die
Dienste angehalten, aber noch eingeschaltet, die Konfiguration, die Dateien und
die Backups unberührt; die Meldung nennt den Zustand und den Befehl zum
Wiederstarten. Bei einer entfernten Datenbank bricht `mariadb` beim ersten
fehlgeschlagenen Befehl ab, frühere Tabellen können schon gelöscht sein; die
Meldung sagt das und nennt das letzte Backup (oder die vorhandenen
Backups) zum Einspielen. Ab der Bestätigung ignoriert der Befehl das Signal
SIGHUP (ein schließendes Terminal bricht ihn nicht mitten im
`DROP DATABASE` ab); bei Strg+C oder SIGTERM endet er sofort mit der Meldung
„Abgebrochen mitten in der Entfernung – starte den Befehl erneut“ und
Exit-Code 1. Erneutes Starten ist ungefährlich: der Plan entsteht aus dem,
was noch da ist.

**Wieder installieren:** `install.sh` bricht ab, solange die
Konfigurationsdatei `/etc/rentalars/rentalars.conf` **oder** `/opt/rentalars/app`
existiert (geprüft wird nur die Datei, nicht der ganze Ordner). Nach
`--keep-data` ist `/opt/rentalars` weg, die Konfiguration aber noch da. Auf
behaltenen Daten lässt sich also nicht von selbst neu installieren; die
Ausgabe von `--keep-data` nennt die Schritte: `/etc/rentalars` beiseite legen
(damit auch die Datei), `install.sh` ausführen, bei Bedarf `sudo rentalars restore`
mit einem Backup, den alten `secret_key` zurückkopieren und danach
`sudo rentalars encryption enable`. Nach `--keep-data` gibt es den Befehl
`rentalars` nicht mehr; eine spätere vollständige Löschung läuft aus dem
entpackten Paket: `sudo ./deploy/uninstall.sh --purge`. Solange die NGINX-Seite
fehlt, schlägt die Erneuerung des Zertifikats fehl. Die Einstellungen von
KI und Routendienst bleiben in `/etc/rentalars`; nach einer Neuinstallation
`rentalars ai install` und `rentalars route install` erneut ausführen.

**Getestet** ist der Ablauf mit Attrappen für `systemctl`, `mariadb`,
`nginx`, `certbot`, `getent`, `userdel`, `groupdel` und `gpasswd` in einem
Wegwerfverzeichnis (`tests/deploy/test_uninstall.sh`, mehrere hundert Fälle, Teil von
`scripts/check.sh`), **nicht auf einem echten Server**. Wer es zum ersten Mal
einsetzt, beginnt mit `--dry-run`.

## Leistung

### Was zugesagt ist

Auf dem Referenzsystem (4 Kerne, 8 GB), mit zwei gleichzeitig arbeitenden
Personen und dem Mengengerüst aus dem Anforderungskatalog – 100 Konten,
20.000 Exemplare, 1.000 Projekte:

- übliche Seiten und API-Aufrufe in unter einer Sekunde (NFA-012),
- ein Projekt mit 500 Positionen in 20 Teilgruppen öffnet in unter einer
  Sekunde und bleibt flüssig bedienbar (NFA-014),
- das Hinzufügen einer Position samt Verfügbarkeitsprüfung antwortet in
  unter einer halben Sekunde (NFA-013).

Und seit Stufe 3: Erfassen bis zu zehn Personen kurz nacheinander ihre
Zeiten – nach einem Einsatz die ganze Crew –, bleibt Rentalars bedienbar
(NFA-051); als Maß gilt, dass jede Antwort in unter zwei Sekunden kommt.

### Was gemessen wurde

Gemessen am 16. Oktober 2026 (Ubuntu 24.04, volles Mengengerüst, drei Läufe). Alles blieb unter seiner Grenze (höchstens
659 ms, Stundenauswertung des letzten Monats als CSV); der Befehl brauchte höchstens 164 MB Speicher. Die Messung ist nicht für
jeden späteren Stand wiederholt worden; wie du selbst misst, steht unten.

| Vorgang | Grenze | Gemessen |
|---|---|---|
| Projekt mit 500 Positionen öffnen | 1000 ms | 574–604 ms |
| dasselbe Projekt über die API lesen | 1000 ms | 292–364 ms |
| Position hinzufügen im Browser | 500 ms | 207–230 ms |
| Packliste des Projekts mit 500 Positionen | 1000 ms | 489–530 ms |
| Stundenauswertung des letzten Monats, alle Personen | 1000 ms | 513–638 ms |
| Kalender des Monats | 1000 ms | 98–115 ms |
| Zeitstrahl von zwei Tagen in Stunden | 1000 ms | 30–47 ms |

### Selbst messen

Auf einer **Testinstallation** – nie in der echten, der Befehl weigert sich
dort auch – und nach der Ersteinrichtung im Browser (vorher führt jede Seite
zur Einrichtung, und es gäbe nichts zu messen):

```sh
sudo rentalars measure_performance --create-test-data
```

Das ist ein Schritt für die eigene Hardware (NFA-044): Fehlt das
Mengengerüst, legt der Befehl es zuerst an (100 Konten, 20.000 Exemplare
mit Lagerorten, 8.000 davon mit Prüfungen, 1.000 Projekte), dann misst er und sagt bei jedem Vorgang „ok“ oder „TOO
SLOW“; ist eine Grenze überschritten, endet er mit einem Fehler. Dasselbe in
zwei Schritten:

```sh
sudo rentalars create_load_test_data     # legt das Mengengerüst an, dauert etwa 10 Sekunden
sudo rentalars measure_performance       # misst und sagt bei jedem Vorgang „ok“ oder „TOO SLOW“
```

Zehn Personen, die gleichzeitig Zeiten erfassen (NFA-051), misst ein
eigener Befehl – über HTTPS durch NGINX, also so, wie die Telefone der Crew
zugreifen:

```sh
sudo rentalars measure_concurrency              # zehn Personen, je fünf Einträge
sudo rentalars measure_concurrency --users 20   # mehr Personen
sudo rentalars measure_concurrency --insecure   # bei selbst erstelltem Zertifikat
```

Er legt dafür eigene Testkonten, Personen und ein internes Projekt an und
löscht sie danach wieder. Spuren bleiben im Änderungsprotokoll (unter
Namen, die mit `lasttest-` beginnen), und das interne Projekt verbraucht
eine Projektnummer. Auch dieser Befehl gehört deshalb auf eine
Testinstallation.

### Mehr gleichzeitige Nutzer

Die mitgelieferten Einstellungen sind auf das Referenzsystem abgestimmt
(NFA-042): fünf Arbeitsprozesse für Rentalars, von denen jeder eine Anfrage
zur Zeit beantwortet, und 1 GB Zwischenspeicher für MariaDB. Das reicht für
zwei bis zehn Personen, die gleichzeitig arbeiten.

Für dauerhaft mehr: einen Server mit 8 Kernen und 16 GB, und in
`/etc/systemd/system/rentalars.service` die Zahl hinter `--workers` auf die
Zahl der Kerne plus eins setzen (Faustregel; je Prozess etwa 90 MB), in
`/etc/mysql/mariadb.conf.d/60-rentalars.cnf` den Wert
`innodb_buffer_pool_size` auf ein Viertel des Arbeitsspeichers. Danach:

```sh
sudo systemctl daemon-reload
sudo systemctl restart mariadb rentalars
```

Eine Aktualisierung von Rentalars schreibt die Dienstdatei neu; trage die
Zahl danach wieder ein. Auf einem Raspberry Pi mit weniger als 4 GB setzt
Rentalars selbst kleinere Werte ([installation.md](installation.md),
„Raspberry Pi“).

## Wenn etwas hakt

**Die Seite zeigt „502 Bad Gateway“.** NGINX läuft, Rentalars nicht.

```sh
sudo systemctl status rentalars
sudo journalctl -u rentalars -n 50
sudo systemctl restart rentalars
```

Steht im Protokoll etwas von der Konfigurationsdatei, ist dort ein Tippfehler;
die Meldung nennt die Zeile. Rentalars startet auch nicht, wenn
`url` mit `http://` beginnt und `allow_http = yes` fehlt, oder wenn ein
Eintrag unter `[network] allow_internal` weder Netz noch Adresse noch
Hostname ist (oben, „HTTPS und vorgeschaltete Server“ und „Verbindungen
ins interne Netz“).

**Der Browser meldet „zu viele Weiterleitungen“.** Ein vorgeschalteter
Server verschlüsselt, gibt aber `X-Forwarded-Proto: https` nicht weiter;
Rentalars hält jede Anfrage für unverschlüsselt und leitet auf https um.
Den Kopf im vorgeschalteten Server setzen (oben, „HTTPS und
vorgeschaltete Server“).

**„Die Adresse führt in ein internes Netz“** an einem Kalender, Webhook
oder Postfach: Das Ziel liegt im eigenen Netz oder auf diesem Server.
Gewollt? Unter `[network] allow_internal` freigeben und neu starten. Der
Selbsttest nennt unter „Verbindungen zu anderen Servern“ alle betroffenen
Einstellungen mit der aufgelösten Adresse.

**Videos im Chat werden abgelehnt** („Videos gehen gerade nicht: Auf dem
Server fehlt ffmpeg.“). Das Paket ffmpeg fehlt – etwa weil die
Paketverwaltung bei der Aktualisierung belegt war: `sudo apt install
ffmpeg`, ein Neustart ist nicht nötig. Scheitert das Hochladen großer
Videos mit „413 Request Entity Too Large“, nimmt die NGINX-Site weniger an
als die Vorlage: `sudo rentalars nginx-site`. Hängt ein Video lange auf
„Video wird verkleinert …“: Videos werden eines nach dem anderen
verkleinert, es kann also auf andere warten. `sudo rentalars run_jobs`
führt Wartendes aus, `sudo journalctl -u rentalars-jobs -n 50` zeigt, was
der Zeitgeber zuletzt getan hat. Ohne
wartende oder laufende Aufgabe gilt es nach drei Stunden als misslungen,
sonst nach 24 Stunden (oben, „Fotos und Videos im Chat“).

**Eine Seite bricht nach zwei Minuten mit „Internal Server Error“ ab.**
Länger darf eine einzelne Anfrage nicht laufen; Rentalars beendet sie und
nimmt zurück, was sie bis dahin geschrieben hat. Im gewöhnlichen Betrieb
kommt das nicht vor: Was lange dauert – Importe, viele Etiketten, der
Datenexport –, läuft im Hintergrund (oben), und ein Import über die API
innerhalb einer Anfrage ist auf 5.000 Zeilen begrenzt (siehe
[import.md](import.md)). Bleiben sehr große PDF-Dateien. Geschieht es doch,
steht in `sudo journalctl -u rentalars` eine Zeile mit „WORKER TIMEOUT“;
bitte melde, welche Seite es war.

**Eine Aufgabe im Hintergrund bleibt auf „wartet“.** Der Prozess ließ sich
nicht starten; der Zeitgeber holt sie binnen einer Minute nach. Läuft er
(`systemctl status rentalars-jobs.timer`)? Was er zuletzt tat, zeigt
`sudo journalctl -u rentalars-jobs -n 30`; `sudo rentalars run_jobs` führt
wartende Aufgaben sofort aus. Steht eine Aufgabe lange auf „läuft“, arbeitet
ihr Prozess noch – ein großer Export braucht Zeit; was er ausgibt, steht im
Protokoll (`sudo journalctl -u rentalars` bzw. `-u rentalars-jobs`). Ist der
Prozess weg, setzt der Zeitgeber die Aufgabe binnen einer Minute neu an,
beim zweiten Mal vermerkt er sie als fehlgeschlagen.

**Die Seite lädt gar nicht.** Läuft NGINX (`sudo systemctl status nginx`)?
Ist das Zertifikat abgelaufen (`sudo certbot certificates`)? Sind die Ports
80 und 443 in der Firewall offen?

**„Zu viele Anmeldeversuche“.** Nach fünf falschen Passwörtern ist der Name
für 15 Minuten gesperrt (beides einstellbar unter „Einstellungen →
Firmendaten und Grundeinstellungen“). Die Sperre endet von selbst.

**Jemand kann sich nicht anmelden, obwohl er im Personal steht.** Jede
Person hat ein Konto, aber ein neues Konto hat noch kein
Passwort. Unter Einstellungen → Nutzer lädt ein Administrator die Person
ein oder legt ein **Einmal-Passwort** fest und gibt es ihr persönlich; bei
der nächsten Anmeldung wählt sie zuerst ein eigenes. Den Benutzernamen
(etwa `anna.becker`) zeigt die Seite der Person unter „Anmeldung“.

**Der Administrator hat sein Passwort vergessen** und der E-Mail-Versand ist
nicht eingerichtet: Ein anderer Administrator legt ihm im Browser ein
Einmal-Passwort fest – oder, wenn es keinen zweiten gibt, auf dem Server:

```sh
sudo rentalars changepassword BENUTZERNAME
```

**Der Administrator hat Telefon und Wiederherstellungscodes verloren**
(Zwei-Faktor-Anmeldung) und es gibt keinen zweiten, der sie im Browser
zurücksetzt:

```sh
sudo rentalars reset_two_factor BENUTZERNAME
```

Danach meldet er sich mit dem Passwort an und richtet die Anmeldung neu ein.

**Projektmails kommen nicht an.** Einstellungen → E-Mail → „Postfächer und
Signatur“: Steht beim Postfach ein Fehler, ist es aus, oder hat es die
Rolle Korrespondenz gar nicht? „Verbindung prüfen“ zeigt, ob die Anmeldung
klappt. Steht die Mail unter Projekte → Anfragen, weil das Kürzel einen
Tippfehler hat? Fehlt das Kürzel ganz, lässt Rentalars die Mail mit Absicht
liegen – es sei denn, das Postfach übernimmt Mails ohne Projektkennung;
dann steht sie dort als Anfrage. Das Mail-Protokoll zeigt, was mit jeder
abgerufenen Mail in welchem Postfach geschah;
`sudo rentalars fetch_mail --now` zeigt, was beim Abruf passiert.

**Antworten der Crew per Mail kommen nicht an.** Unter Einstellungen →
Firmendaten und Grundeinstellungen nennt „Antwort auf Einsatzanfragen“
das Postfach für die Antworten (unter E-Mail → „Postfächer und Signatur“
steht es ebenfalls); steht dort, dass keines sie annehmen kann, enthalten
die Anfragen nur den Link (oben, „Postfächer“). Wurde das Postfach für die
Antworten gelöscht, kommen Antworten auf die davor verschickten Anfragen
nicht mehr an. Wird das
Postfach abgerufen, ohne Fehler? Hat die Person den Betreff geändert, wird
die Antwort nicht erkannt; eine frei formulierte Antwort liegt dann im
Postfach. Was mit einer erkannten Antwort geschah – übernommen oder mit
welchem Grund nicht –, zeigt das Mail-Protokoll unter „Antwort auf
Einsatzanfrage“.

**Aus einem Projekt lässt sich keine Mail schreiben.** Es braucht ein
aktives Postfach der Korrespondenz mit der Rolle „Postausgang der
Korrespondenz“, mit SMTP-Server und Adresse. Fehlt es, sagt die Seite
„Der Versand ist nicht eingerichtet“.

**Nutzer werden „zu früh“ abgemeldet.** Nach 240 Minuten ohne Aktivität
endet eine Sitzung; einstellbar unter Einstellungen → Firmendaten und
Grundeinstellungen.

**Eine Einladung kommt nicht an.** Ob und mit welchem Ergebnis sie
hinausging und über welches Postfach, zeigt das Mail-Protokoll
(Einstellungen → Mail-Protokoll). Systemmails gehen über das Postfach mit
der Rolle „Systemmails“, sonst über den Mailserver aus `[email]`. Ist
beides nicht eingerichtet, verschickt Rentalars nichts – das
Mail-Protokoll sagt „nicht versendet – kein Mailserver
eingerichtet“ (oben, „Ohne Mailserver“); der Text der
E-Mail samt Link steht dann im Protokoll
(`sudo journalctl -u rentalars -n 100`). Sonst zeigt
`sudo rentalars sendtestemail du@example.de` die Fehlermeldung des
Mailservers, über denselben Weg. Ohne E-Mail geht es mit einem Einmal-Passwort (oben). Auch
eingeladenen Konten, die noch kein Passwort haben, schickt „Passwort
vergessen?“ auf der Anmeldeseite einen neuen Link.

**Ein Kalender wird nicht gelesen oder beschrieben.** Was der letzte
Versuch ergab, steht bei der Person unter „Meine Personaldaten“;
`sudo rentalars sync_calendars --person ID` versucht es sofort und zeigt
das Ergebnis. Häufige Ursachen: Der Server darf nicht nach außen, der
private Link wurde beim Kalenderdienst erneuert, das Passwort des
CalDAV-Kontos ist geändert (bei iCloud braucht es ein App-Passwort). Läuft
der Zeitgeber (`systemctl status rentalars-jobs.timer`)?

**Ein Webhook stellt nicht zu oder wurde abgeschaltet.** Die Seite des
Webhooks (Einstellungen → Webhooks) zeigt unter „Zustellungen“ jeden
Versuch mit Fehler und dem Anfang der Antwort. Häufige Ursachen: Der
Server darf nicht nach außen oder braucht einen Proxy (oben, „Webhooks“),
das empfangende System leitet um (Weiterleitungen werden nicht verfolgt –
die endgültige Adresse eintragen), es hat ein selbst signiertes
Zertifikat, oder es kennt das Geheimnis nicht (mehr) und lehnt die
Signatur ab. „Test senden“ zeigt die Antwort sofort. Läuft der Zeitgeber
(`systemctl status rentalars-jobs.timer`)?

**Eine Rechnung kommt nicht in Lexware Office an.** Der Grund steht an der
Rechnung im Reiter „Dokumente“ und auf der Seite Einstellungen →
Buchhaltung. „API-Schlüssel abgelehnt“: Schlüssel in Lexware Office prüfen
und neu eintragen; „nicht erreichbar“: Verbindung nach außen zu
`api.lexware.io` prüfen; „lässt sich nicht mehr lesen“: der `secret_key`
wurde geändert, Schlüssel neu eintragen. Danach „Erneut übergeben“ – es
wird nur nachgeholt, was fehlt.

**Die Platte ist voll.** Meist sind es Sicherungen. Sieh nach
(`sudo du -sh /var/backups/rentalars`), lösche alte von Hand oder verkürze
die Aufbewahrung in der Konfigurationsdatei (`[backup] keep_days`). Die
Sicherungen mit `-keep` im Namen – eine vor jeder Aktualisierung – werden nie
von selbst gelöscht.

**Alles ist langsam.** `top` zeigt, ob Prozessor oder Arbeitsspeicher am
Ende sind; `/var/log/mysql/rentalars-slow.log` nennt Abfragen, die länger
als eine Sekunde brauchten. Beides bitte mit der Fehlermeldung mitschicken.

## Sicherheit im Betrieb

- Rentalars antwortet nur über HTTPS; Anfragen über HTTP werden umgeleitet.
  Ein Produktionsserver mit einer `http://`-Adresse startet
  nur mit `allow_http = yes`, und der Selbsttest warnt dann (oben, „HTTPS
  und vorgeschaltete Server“).
- Die Anmeldeseite nimmt je Absender höchstens 30 Anfragen pro Minute an,
  die API je Token höchstens 600 Aufrufe pro Minute (einstellbar, oben „Die
  API: Grenzen und Schutz“). Der Abo-Link für Kalender (`/calendar-feed/…`)
  funktioniert ohne Anmeldung; er zeigt die Einsätze einer Person, ohne
  Kunden und Preise. Ihn schützt ein langer geheimer Schlüssel, und er wird
  gebremst (oben, „Kalender der Personen“).
- Passwörter werden nicht gespeichert, nur ihr Prüfwert; ebenso die
  API-Token. Ein Token öffnet nie mehr als sein Nutzer, und ein auf Module
  beschränktes Token – etwa das der Rentalars-App auf einem Telefon –
  erstellt keine weiteren Tokens und sieht die übrigen seines Nutzers
  nicht (oben, „Die API: Grenzen und Schutz“).
- Den vollständigen Datenexport mit allen personenbezogenen Daten können
  nur Administratoren erstellen, und herunterladen kann ihn nur, wer ihn
  erstellt hat; Passwörter und andere Geheimnisse enthält er nicht. Eine
  Sicherung aus dem Browser erstellen ebenso nur Administratoren, und nur
  wer sie erstellt hat, lädt sie herunter; sie enthält – anders als der
  Export – alles, auch die Konfigurationsdatei mit ihren Zugangsdaten
  ([sicherung.md](sicherung.md)).
- Wer Kunden, Personen und Projekte geöffnet, Listen exportiert oder
  Export und Sicherungen heruntergeladen hat, hält das Zugriffsprotokoll
  fest (AUT-028).
- Hochgeladene Dateien liefert NGINX nur aus, nachdem Rentalars geprüft hat,
  dass die Person angemeldet ist.
- **Bibliotheken**: Die Versionen in `requirements.txt` sind
  festgelegt; wer Rentalars selbst baut oder weitergibt, führt
  `scripts/check.sh` aus, das mit `pip-audit` nach bekannten Schwachstellen
  fragt (Netz nötig). Im
  Quell-Repository lässt `.github/dependabot.yml` GitHub
  Aktualisierungen vorschlagen. Hochgeladene Bilder öffnet Rentalars nur
  als die Formate, die die Stelle erwartet; Pillow kennt beim Start nur
  JPEG, PNG, GIF und WebP.
- **Der geheime Schlüssel** (`secret_key`) darf nicht der Platzhalter der
  Beispieldatei sein: Ein Produktionsserver startet dann nicht.
  Der Schlüssel verschlüsselt die gespeicherten Passwörter; wer ihn ändert,
  gibt sie neu ein.
- **Der Webserver und die Dateien des Dienstes:** Die Konfigurationsdatei kann
  `www-data` nicht lesen. `www-data` bleibt aber in der Gruppe des
  Dienstkontos, weil NGINX sonst den Socket der Anwendung nicht erreicht; was im
  Datenordner für die Gruppe lesbar ist (hochgeladene Dateien, Sicherungen aus
  dem Browser), kann der Webserver-Benutzer lesen. Das ist offen; es zu
  schließen verlangt ACLs oder eine eigene Gruppe. Ein Fehler im Webserver oder
  in einem Modul von NGINX ist der Weg dahin, nicht die Anwendung. Verschlüssle
  Sicherungen.
- **Sicherung und Wiederherstellung** laufen als root, folgen aber keinem Link
  im Datenordner des Dienstkontos: Die Wiederherstellung
  entpackt im Ordner der Sicherungen, der root gehört.
- Die **Karte eines Lieferanten** und die Vorschläge im Lieferantenfeld sehen
  nur, wer Material oder die Verwaltung lesen oder Projekte ändern darf, nicht
  „Crew“ und „Freie Kraft“.
- Die Datenbank nimmt nur Verbindungen vom Server selbst an; ein
  vorhandener Datenbankserver wird über TLS angesprochen, mit einem Benutzer,
  der nur diese eine Datenbank erreicht (NFA-066).
- Wer sich eine Zeit lang nicht rührt, wird abgemeldet (AUT-008). Jeder
  sieht unter „Mein Konto → Sitzungen“, wo er angemeldet ist, und kann jede
  Sitzung beenden.
- Zwei-Faktor-Anmeldung mit einer Authenticator-App (AUT-006): je Nutzer
  einschaltbar, je Rolle vorschreibbar, und für alle mit Rechten auf die
  Einstellungen über eine Einstellung (NFA-049).
- Ein Einmal-Passwort (AUT-027) taugt nur für eine Anmeldung: Danach führt
  jede Seite zum Wählen eines eigenen Passworts, und die API antwortet bis
  dahin mit 403.
- NGINX antwortet nur auf den eingerichteten Namen; Anfragen an die bloße
  Adresse des Servers oder einen fremden Namen beendet es ohne Antwort. Wer
  die mitgelieferte Konfiguration verändert hat, erfährt im Selbsttest, ob
  eine der sicheren Einstellungen fehlt.
- Mails aus der Korrespondenz werden bereinigt angezeigt, in einem
  abgeschotteten Rahmen ohne Skripte; Bilder von fremden Servern lädt
  Rentalars erst auf Knopfdruck (EML-027).
- **Webhooks, Kalender und Postfächer** sprechen (NFA-071, aus
  einer Code-Prüfung) Adressen im internen Netz und auf diesem Server nur
  an, wenn sie unter `[network] allow_internal` freigegeben sind. Wer
  Webhooks einrichten darf, kann Rentalars Anfragen an freigegebene
  interne Ziele schicken lassen und sieht den Anfang der Antworten; gib
  deshalb nur frei, was gemeint ist, und vergib Schreibzugriff auf die
  Einstellungen sparsam. CalDAV-Anmeldedaten gehen nur an genau den
  eingetragenen Server (NFA-072; oben, „Verbindungen ins interne Netz“).
  Den Anfang der Antworten eines Webhooks sieht, wer die Einstellungen lesen
  darf. Nachrichten enthalten nie Preise oder Kosten, sind mit einem
  Geheimnis signiert und folgen keiner Weiterleitung; Benutzername und
  Passwort in der Adresse lehnt Rentalars ab. Das Zustellprotokoll enthält
  30 Tage lang Namen von Personen (aus freigegebenen Zeiten); das
  Anonymisieren einer Person entfernt sie dort nicht.
- Die **Geheimnisse der Webhooks** und der **API-Schlüssel von Lexware
  Office** liegen mit dem `secret_key` verschlüsselt in der Datenbank, wie
  die Passwörter der Postfächer und der CalDAV-Kalender; im vollständigen
  Export stehen sie nicht.
- **Karten**: Eine Anschrift geht erst nach einem Klick auf
  „Karte anzeigen“ an die Kartensuche, und nur ihr Text; die Kartenbilder
  lädt der Browser – mit der Adresse der Installation als
  Referer, wie OpenStreetMap es verlangt –, Routen öffnet Google Maps im
  Browser nach einem Klick, ab dem Standort der Person (oben, „Karten“).
  Wer das nicht will, schaltet die Karten in `[maps]` ab oder trägt eigene
  Server ein.
- **Automationen** antworten nur auf Mails ohne
  Projektkennung, nie auf automatische Mails, Mailsysteme oder eigene
  Adressen und jedem Absender höchstens einmal am Tag je Regel (oben,
  „Automationen“).
- Der **Chat** eines Projekts ist für alle lesbar, die das Projekt öffnen
  können, auch für die eingeplante Crew; die Seite sagt es. Er steht nicht
  im Änderungsprotokoll; beim Anonymisieren einer Person verschwindet ihr
  Name auch an ihren Nachrichten.
- **Root bleibt beim Betreiber** (auch für die Adresse und die
  KI): Rentalars läuft ohne Root-Rechte und speichert keine Zugangsdaten
  für root. Was root braucht – eine neue Adresse samt Zertifikat, die
  lokale KI –, bereitet die Oberfläche höchstens vor; ausführen tust du es
  per SSH (`sudo rentalars address apply …`, `sudo rentalars ai …`). Der
  Befehl für die Adresse liest die Vorbereitung nur aus der Ausgabe eines
  Befehls, der als Dienstkonto läuft, und prüft alles selbst (oben,
  „Serveradresse und Zertifikat ändern“).
- **KI:** Die lokale KI ist nur auf 127.0.0.1 erreichbar, läuft unter
  einem eigenen Benutzer ohne Rechte und erreicht nichts außer diesem
  Rechner. Schnittstellen zu anderen Sprachmodellen sind anfangs aus; ihre
  API-Schlüssel liegen mit dem `secret_key` verschlüsselt in der Datenbank
  und stehen nicht im Export. Mails gehen nur an die Schnittstelle, die für
  den Anwendungsfall gewählt ist; das Protokoll der KI-Aufrufe hält jeden
  Aufruf fest, nie seinen Inhalt (oben, „KI“). Vor dem
  Senden gehen IBAN, Karten, Zugangsdaten, E-Mail-Adressen und Telefonnummern
  nicht mit; Namen und Anschriften im Fließtext gehen mit. Die
  automatischen Zusammenfassungen sind aus, bis ein Administrator für einen
  Anbieter zustimmt; die offenen Punkte nennt der Abschnitt „Automatische
  KI-Zusammenfassungen“ (oben).
- **Anmeldung über das Verzeichnis** (aus bis zum Einschalten):
  Der eingegebene Name wird maskiert, ehe er in den Filter kommt; ein leeres
  Passwort erreicht das Verzeichnis nie; das Passwort des Suchkontos liegt mit
  dem `secret_key` verschlüsselt in der Datenbank; mindestens ein lokales
  Notfall-Konto bleibt (oben, „Anmeldung mit dem Verzeichnis (LDAP)“).
- **Eingangsrechnungen** sind Dateien mit Preisen und
  Lieferanten: Sie liegen unter `media/incoming/`, sind in der Sicherung und
  lassen sich nur über Rentalars mit dem Recht auf Einkaufspreise
  herunterladen (oben, „Eingangsrechnungen und ihre Dateien“).

Was du beitragen musst: Ubuntu aktuell halten, den SSH-Zugang absichern
(Schlüssel statt Passwort), Sicherungen vom Server holen, und Rentalars
aktualisieren, wenn eine neue Version erscheint – einen Hinweis darauf gibt
das Programm bewusst nicht von selbst, weil es dafür „nach Hause
telefonieren“ müsste (NFA-050).

Wird der Server aus dem Internet erreichbar, schalte vorher die
Zwei-Faktor-Anmeldung für Administratoren ein und sieh in den Selbsttest:
Er nennt, was dann noch fehlt.
