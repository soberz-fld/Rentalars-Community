# Software von Dritten in Rentalars

Rentalars steht unter der GNU General Public License, Version 3 oder später
([LICENSE](LICENSE)). Es baut auf den folgenden freien Bibliotheken auf. Jede
von ihnen steht unter einer Lizenz, die sich mit der GPL v3 verträgt; das
prüft `scripts/check_licenses.py` bei jeder Änderung am Code automatisch
(NFA-053). Code aus Projekten unter der AGPL ist nicht enthalten.

Die beiden Tabellen werden von `python scripts/check_licenses.py --markdown`
erzeugt. Die Prüfung schlägt fehl, wenn diese Datei nicht mehr zum Stand der
Bibliotheken passt.

## Python-Bibliotheken

Sie werden bei der Installation aus dem Python-Paketverzeichnis (PyPI) geholt
und liegen dann unter `/opt/rentalars/venv`. Die genauen Versionen legt
`requirements.txt` fest.

| Library | Version | Licence |
|---|---|---|
| Django | 5.2.18 | BSD |
| djangorestframework | 3.18.3 | BSD |
| django-filter | 26.2 | BSD |
| drf-spectacular | 0.30.0 | BSD |
| drf-spectacular-sidecar | 2026.10.1 | BSD |
| mysqlclient | 2.3.0 | GPL-2.0-or-later |
| gunicorn | 26.2.0 | MIT |
| weasyprint | 70.0 | BSD |
| openpyxl | 3.1.5 | MIT |
| pillow | 13.0.0 | MIT, MIT-CMU (HPND) |
| cryptography | 50.0.2 | Apache-2.0, BSD |
| nh3 | 0.3.7 | MIT |
| segno | 1.6.6 | BSD |
| icalendar | 7.3.0 | BSD |
| recurring-ical-events | 3.8.2 | LGPL |
| Markdown | 3.11.1 | BSD |
| pypdf | 6.21.2 | BSD |
| ldap3 | 2.9.1 | LGPL |
| asgiref | 3.12.1 | BSD |
| attrs | 26.1.0 | MIT |
| brotli | 1.2.1 | MIT |
| cffi | 2.1.1 | MIT, MIT-0 |
| click | 8.5.0 | BSD |
| cssselect2 | 0.10.1 | BSD |
| et_xmlfile | 2.0.0 | MIT |
| fonttools | 4.66.1 | MIT |
| inflection | 0.5.1 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| jsonschema | 4.26.0 | MIT |
| pyasn1 | 0.6.4 | BSD |
| pycparser | 3.11 | BSD |
| pydyf | 0.12.1 | BSD |
| pyphen | 0.18.1 | GPL-2.0-or-later, MPL |
| python-dateutil | 2.9.0.post0 | Apache-2.0, BSD |
| PyYAML | 6.0.3 | MIT |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.9.1 | MIT |
| six | 1.17.0 | MIT |
| sqlparse | 0.6.0 | BSD |
| tinycss2 | 1.5.1 | BSD |
| tinyhtml5 | 2.1.0 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |
| tzdata | 2026.5 | Apache-2.0 |
| uritemplate | 4.2.0 | Apache-2.0, BSD |
| webencodings | 0.6.1 | BSD |
| x-wr-timezone | 2.0.1 | LGPL |
| zopfli | 0.4.3 | Apache-2.0 |

Hinweise zu einzelnen Lizenzen:

- **mysqlclient** und **pyphen** stehen unter der GPL, Version 2 *oder
  später*; sie werden hier unter Version 3 genutzt.
- **recurring-ical-events** und **x-wr-timezone** stehen unter der LGPL,
  Version 3 *oder später*; Rentalars nutzt sie als Bibliotheken für das
  Lesen verknüpfter Kalender.
- **drf-spectacular-sidecar** bringt für die Seite „API-Dokumentation“ die
  Oberfläche Swagger UI (Apache-2.0) mit, die im Browser läuft. Sie wird vom
  eigenen Server geladen, nicht aus dem Internet. Das Paket enthält außerdem
  ReDoc (MIT); Rentalars nutzt es nicht.

## Mitgelieferte Dateien für den Browser

Diese Dateien liegen im Paket selbst (`static/`), damit die Oberfläche nichts
von fremden Servern lädt (NFA-050). Der Lizenztext liegt jeweils daneben.

| Bundled file | Path | Licence |
|---|---|---|
| htmx | `static/vendor/htmx.min.js` | 0BSD |
| SortableJS | `static/vendor/sortable.min.js` | MIT |
| Leaflet | `static/vendor/leaflet/**/*.*` | BSD-2-Clause |
| Barlow (font family) | `static/fonts/*.woff2` | OFL-1.1 |
| Liberation Sans (font) | `static/fonts/LiberationSans-Regular.ttf` | OFL-1.1 |


- **htmx** (`static/vendor/htmx.LICENSE`) lädt Teile einer Seite nach, ohne
  die ganze Seite neu aufzubauen.
- **SortableJS** (`static/vendor/sortable.LICENSE`) sortiert Positionen durch
  Ziehen mit der Maus oder dem Finger.
- **Leaflet** 1.9.4 (`static/vendor/leaflet/LICENSE`, BSD-2-Clause, aus dem
  npm-Paket `leaflet`) zeigt die zoombaren Karten an Adressen. Es wird erst
  geladen, wenn eine Karte angezeigt wird; die Kartenbilder kommen vom
  Kartenserver der Konfigurationsdatei (OpenStreetMap), nicht aus dem Paket.
- **Barlow** (`static/fonts/OFL.txt`) ist die Schrift der Oberfläche und der
  Packliste; sie steht unter der SIL Open Font License 1.1.
- **Liberation Sans** 2.1.5 (`static/fonts/LiberationSans-OFL.txt`, SIL Open
  Font License 1.1, unverändert aus dem Projekt liberationfonts) ist die Schrift
  der drei Etiketten klein, groß und Kabel. Sie hat die Maße von Arial, der
  Schrift der P-touch-Vorlagen, und druckt auf dem Thermodrucker kräftiger als
  Barlow.

## Programme des Betriebssystems

Das Installationsskript richtet außerdem Programme aus den Paketquellen von
Ubuntu ein. Sie gehören nicht zu Rentalars und werden mit dem
Betriebssystem gepflegt: Python, NGINX, MariaDB, die Schriftsatz-Bibliothek
Pango (für die PDF-Erzeugung) und – je nach Art des Zertifikats – certbot.
Auf Wunsch kommen dazu, ebenfalls aus den Paketquellen und als eigene Prozesse
(nicht Teil von Rentalars, nicht mit ihm verbunden außer über Aufruf und
Dateien): **ffmpeg** (für Videos im Chat,; Lizenz je nach Bauart
des Pakets LGPL oder GPL) und – bei `sudo rentalars route install` –
**Routino** (AGPL-3.0; das Installationsskript nennt das ebenfalls). Rentalars
ruft Routino als eigenes Programm auf; Code aus Routino ist nicht enthalten.
Die dafür geladenen **Kartendaten** stammen von OpenStreetMap (© Mitwirkende
von OpenStreetMap, Open Database License 1.0) in der Form der Auszüge von
Geofabrik; die Karte im Browser lädt Kacheln erst nach einem Klick vom
eingestellten Kartendienst.

## Lokale KI (nur auf Wunsch)

Nur wenn der Betreiber `sudo rentalars ai install` ausführt, kommen hinzu:

- **llama.cpp** (`llama-server`), MIT-Lizenz – aus dem Paket der Distribution
  (Ubuntu 26.04: `llama.cpp-tools`) oder aus dem Quelltext der Version b8681
  gebaut;
- ein **Sprachmodell von Qwen** (Alibaba Cloud) im GGUF-Format (Q4_K_M), je
  nach Arbeitsspeicher, Kernen und Prozessor „Qwen3 1.7B“ (in der Umwandlung
  des llama.cpp-Projekts, ggml-org) oder „Qwen3 4B“, auf Wunsch „Qwen2.5 1.5B
  Instruct“ – alle unter der Apache-Lizenz 2.0, die auch die gewerbliche
  Nutzung erlaubt.

Beides wird nicht mit Rentalars ausgeliefert, läuft als eigener Dienst
(`rentalars-ai`) und ist mit Rentalars nur über HTTP auf 127.0.0.1 verbunden.
