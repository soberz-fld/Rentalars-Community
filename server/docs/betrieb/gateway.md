# Rentalars Gateway: die Apps aus dem Internet erreichbar machen

Die Apps (Android, iOS) sprechen mit Rentalars auf **zwei Wegen**:

| Weg | Wann | Wer dazwischen sitzt |
|---|---|---|
| **direkt** | im Firmennetz, per VPN, oder wenn du den Server selbst ins Internet stellst | niemand – die App spricht HTTPS mit dem Server |
| **über das Gateway** | unterwegs, aus dem Internet, ohne dass der Server von außen erreichbar ist | das **Rentalars Gateway** auf einem Rechner in der DMZ oder im Netz eines Hosters |

Beide Wege laufen **nebeneinander**. Wer den
Server direkt erreicht, braucht kein Gateway. Die Apps wählen den Weg **bei
der Anmeldung**: „Direkt“ oder „Über Gateway“. Jede Installation der App
nutzt einen der beiden Wege und wechselt ihn nie stillschweigend; wer
zwischen Firmennetz und Internet wechselt, meldet sich mit dem passenden Weg
an (beide Anmeldungen können nebeneinander auf verschiedenen Telefonen
bestehen).

## Wie es zusammenpasst

```
App ──HTTPS──▶ Gateway (DMZ) ◀──HTTPS── Verbindungsdienst ──▶ Rentalars (gunicorn-Socket)
```

- Das Gateway **baut nie selbst eine Verbindung** zum Server auf. Der
  Verbindungsdienst (`rentalars-gateway-link`) auf dem Server fragt das
  Gateway ständig nach neuen Anfragen („Long-Poll“). In der Firewall des
  internen Netzes ist deshalb **keine eingehende Freigabe** nötig.
- Der Inhalt jeder Anfrage ist **Ende-zu-Ende verschlüsselt** zwischen App
  und Server (Protokoll RGW1, ECDH P-256 + AES-256-GCM). Das Gateway sieht
  nur, **welches Gerät** anfragt und **wie viel** – nie, was.
- Jedes Gerät hat einen eigenen Schlüssel und wird einzeln **gekoppelt** und
  bei Bedarf **gesperrt**. Unbekannte Geräte kommen am Gateway nicht weiter.
- Über das Gateway ist nur die **API** (`/api/v1/…`) erreichbar. Weder die
  Weboberfläche noch die Verwaltung (`/admin/`) noch statische Dateien gehen
  durch.

Das Gateway selbst (Installation, Betrieb, Protokoll) ist ein eigenes
Programm; seine Dokumentation liegt in dessen Ordner (`docs/`).

## Einrichten

1. **Gateway installieren und starten** (siehe dessen Dokumentation). Es
   gibt am Ende einen **Verbindungstext** aus, der mit `RGWL1:` beginnt.
2. **Auf dem Rentalars-Server verbinden:**

   ```
   sudo rentalars gateway connect 'RGWL1:…'
   ```

   Das legt die Schlüssel dieser Installation an (sie liegen verschlüsselt in
   der Datenbank und damit in jeder Sicherung), meldet den Server beim
   Gateway an und schaltet den Dienst `rentalars-gateway-link` ein.
3. **Prüfen:**

   ```
   sudo rentalars gateway status
   ```

   Das zeigt Adresse und Fingerabdruck des Gateways, ob der letzte Abruf
   geklappt hat und wie viele Geräte gekoppelt sind.

Das Gateway braucht einen erreichbaren HTTPS-Port. Hat es ein
selbstgemachtes Zertifikat, trägt der Verbindungstext dessen Fingerabdruck:
Die Installation vertraut dann genau diesem Zertifikat.

## Ein Gerät koppeln

Pro Gerät und Benutzerkonto gibt es einen **einmaligen Kopplungscode**, zehn
Minuten gültig. Ein Administrator macht ihn **im Browser**, ohne
SSH: **Einstellungen → Gateway → „App koppeln“**. Konto wählen (die App hat
dessen Rechte), auf Wunsch einen Namen für das Gerät und die Gültigkeit
(1, 5 oder 10 Minuten), dann „Kopplungscode erzeugen“. Die Seite zeigt den
QR-Code und denselben Inhalt als Text; beim Verlassen der Seite ist er weg.
Das Koppeln und das Sperren verlangt in den Einstellungen das Recht zu
löschen und steht im Änderungsprotokoll. Auf dem Server geht es weiter mit

```
sudo rentalars gateway pair anna --name "Annas Telefon"
```

Beide Wege zeigen einen QR-Code und denselben Inhalt als Text (`RGW1:…`).
In der App am Anmeldebildschirm **„Über Gateway“** wählen und den Code
eingeben: iOS scannt den QR-Code mit der Kamera („Mit Gateway koppeln“),
Android hat keinen eigenen Scanner – dort den Text aus einer Scanner-App
oder aus der Mail kopieren und einfügen. Die Adresse des Servers steht im
Code. Danach meldet sich die App wie gewohnt mit Benutzername, Passwort und
gegebenenfalls Authenticator-Code an. Die Kopplung gehört zu Telefon und
Server und bleibt beim Abmelden erhalten.

Wichtig:

- Ein Gerät gehört zu **einem Konto**. Über dieses Gerät kann man sich nur
  mit diesem Konto anmelden; ein anderer Benutzername wird abgelehnt.
- Ein **API-Token**, das über ein Gerät angelegt wurde, **gilt nur über
  dieses Gerät**. Auf dem direkten Weg ist es wertlos. Tokens, die auf dem
  direkten Weg angelegt wurden, bleiben unberührt.
- Wird ein Konto deaktiviert, sind seine Geräte sofort gesperrt.

## Geräte verwalten

**Einstellungen → Gateway** zeigt die gekoppelten Geräte (Konto, Name, gekoppelt am, zuletzt benutzt) und sperrt eines mit „Sperren“; gesperrte stehen darunter. `rekey`, `disconnect` und `connect` bleiben Befehle auf dem Server.

| Befehl | Wirkung |
|---|---|
| `sudo rentalars gateway devices` | gekoppelte Geräte (mit `--all` auch gesperrte) |
| `sudo rentalars gateway revoke KENNUNG` | ein Gerät sperren (die ersten Zeichen der Kennung genügen); das Gateway weiß es sofort |
| `sudo rentalars gateway rekey --yes` | neuer Schlüssel der Installation: **alle** Kopplungen sind ungültig, alle über Geräte angelegten Tokens werden widerrufen, alle Geräte müssen neu gekoppelt werden |
| `sudo rentalars gateway disconnect` | Verbindungsdienst abschalten und Gateway vergessen; Schlüssel und Geräte bleiben, damit ein späteres `connect` dieselben Kopplungen weiterverwendet |

## Das Gateway umziehen

Zieht das Gateway auf eine andere Adresse oder bekommt es ein neues
Zertifikat, kündigst du das vorher an – die Apps übernehmen es mit der
nächsten Antwort selbst:

```
sudo rentalars gateway announce-move --url https://neu.example.de:8799 --fingerprint AB:CD:… [--next FINGERABDRUCK]
sudo rentalars gateway announce-clear     # wenn alle Geräte umgestellt sind
```

## Einstellungen

Alles Nötige steht in der Datenbank. Optional gibt es in
`/etc/rentalars/rentalars.conf` den Abschnitt `[gateway]` (siehe
`rentalars.conf.example`): `local` (wo der Verbindungsdienst die Anfragen
ausführt – auf dem Server der gunicorn-Socket), `workers`, `time_window`,
`max_response_mib`, `call_timeout`.

## Grenzen

- Über das Gateway gehen nur API-Aufrufe. Funktionen, die in der App eine
  Webseite des Servers öffnen (PDF, XML, Dokumente im Browser), gehen dort
  nicht; die App weist darauf hin (im Firmennetz oder per VPN öffnet sie die
  Adresse trotzdem).
- Antworten sind auf 12 MiB begrenzt; größere Dateien lädt man auf dem
  direkten Weg.
- Die Uhr des Geräts darf höchstens drei Minuten abweichen; die App
  korrigiert sich nach der Uhrzeit des Servers, die jede Antwort mitträgt.

## Wenn etwas nicht geht

| Beobachtung | Ursache und Abhilfe |
|---|---|
| `gateway status`: „Server nicht verbunden“ | Der Dienst läuft nicht: `systemctl status rentalars-gateway-link`, Protokoll mit `journalctl -u rentalars-gateway-link` |
| Selbsttest, Gruppe „Gateway“, Fehler „Nicht verbunden“ | Wie `gateway status`: Der Dienst `rentalars-gateway-link` läuft nicht oder erreicht das Gateway nicht; der letzte Fehler steht darunter |
| Kopplung scheitert mit „abgelaufen“ | Der Code gilt zehn Minuten und genau einmal; neu erzeugen |
| App meldet „Gerät nicht mehr gekoppelt“ | Das Gerät wurde gesperrt oder `rekey` lief; neu koppeln |
| App meldet „Uhrzeit weicht ab“ | Die Uhr des Geräts stellen (automatische Zeit einschalten) |
