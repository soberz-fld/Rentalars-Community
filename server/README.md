# Rentalars

Projekt-, Material- und Crewverwaltung für Betriebe der Veranstaltungstechnik.
Rentalars läuft im Browser auf einem eigenen Server, ist freie Software
(GPL-3.0-or-later) und kostet nichts.

**Version 1.0.0.** Der [Anforderungskatalog](docs/anforderungen/Rentalars_Anforderungskatalog.md) beschreibt 822 Anforderungen;
umgesetzt sind alle MUSS- und SOLL-Anforderungen (801), die 21 übrigen sind als KANN vorgemerkt. Welche Anforderung wo
umgesetzt und getestet ist, zeigt [docs/dev/traceability.md](docs/dev/traceability.md). Was Rentalars nicht kann,
steht im Benutzerhandbuch in Kapitel 17 („Was diese Version noch nicht kann“).

- **Für wen:** Betriebe der Veranstaltungstechnik – Verleih, Produktion, Servicewerkstatt –, die Material, Projekte, Crew, Zeiten
  und Rechnungen an einem Ort führen wollen.
- **Ausprobieren:** `python manage.py create_demo_data` legt Beispieldaten an (siehe „For developers“ unten); eine
  Installation auf einem Server steht unter „Installieren“.
- **Mitmachen:** [CONTRIBUTING.md](CONTRIBUTING.md). Die Änderungen jeder Version stehen im [CHANGELOG](CHANGELOG.md).

## Das kann Rentalars

- **Sprachen und Konten:** Deutsch und Englisch – die Oberfläche je Konto, die Dokumente für Kunden je Firma, das Handbuch in
  beiden Sprachen auch direkt in Rentalars. Rollen und Rechte je Modul mit getrennten Rechten für Preise, Einkaufspreise,
  Personalkosten und Verfügbarkeit, Rechte je Projekt (die Crew sieht nur Überblick, Packliste, Chat und die offenen Nachrichten),
  befristete Konten, Zwei-Faktor-Anmeldung, auf Wunsch Anmeldung mit dem Konto des Verzeichnisses (LDAP, Active Directory),
  Sitzungen und Sicherheitsprotokoll.
- **Material:** Modelle und Exemplare, verbaute und lose enthaltene Teile, Hersteller, Produkt und Händler, Lagerorte, Etiketten
  mit QR-Code (auch direkt aus dem Browser auf den Etikettendrucker), Scannen mit der Kamera oder dem USB-Scanner, Prüfungen mit
  Fälligkeit und die elektrische Prüfung nach DGUV V3 mit Protokoll, Audits, eigene Felder, Fotos, Defektmeldung, Kaufsets,
  Mengenmaterial, Anlagevermögen mit Abschreibung, „Kauf einpflegen“ aus einer Rechnung, Kalender-Links (.ics).
- **Fuhrpark und Logistik:** Fahrzeuge und Anhänger als Exemplare mit Fristen (HU, UVV), Auslastung als Zeitstrahl, Fahrten im
  Projekt mit Abrechnung nach Kilometern oder pauschal, Hinweise zu Doppelbuchung, Sitzplätzen, Führerschein und Anhängelast,
  auf Wunsch Kilometer aus einem Routendienst auf dem eigenen Server.
- **Produkte, Kunden, Orte:** Produkte mit Artikelnummern, Sets, Zubehör und Ersatzprodukten, Verbrauchsmaterial, Nebenkosten,
  Dienstleistungsprodukte; Kunden mit Ansprechpartnern und Adressen; Veranstaltungsorte mit Zufahrt, Strom und Plänen; Karten
  und Routen erst nach einem Klick.
- **Projekte:** Positionen in geschachtelten Teilgruppen, optional oder als Alternative, Summen, Gewinn und Preisübersicht;
  Zeitplanung mit Phasen, Zeitstrahl und Personal je Phase; Teilprojekte; Projektvorlagen; Chat mit Fotos und Videos;
  Abrechnung nach Tagesmiete, pauschal, nach Stunden oder Aufwand mit Staffeln, Aufpreisen und Rabatten; Verfügbarkeit mit
  Ampel, Pufferzeiten und Fehlbeständen; Zumietung bei Fehlmengen.
- **Servicefälle:** schnelle Fälle für Störung, Frage oder Reparatur, mit Korrespondenz, Status, Wiedervorlage und Beteiligten, aus
  einer Mail oder einer Defektmeldung, auf Wunsch in ein Projekt umwandelbar; Monatsrechnung je Kunde.
- **Packen:** Packlisten am Bildschirm und als PDF, Ausgabe und Rücknahme je Stück; die Rentalars-App packt auch ohne Netz.
- **Dokumente und Buchhaltung:** Angebot, Auftragsbestätigung, Lieferschein, Rechnung (XRechnung, ZUGFeRD), Stornorechnung,
  Crew-Disposition; Anzahlungs-, Teil- und Schlussrechnungen; Übergabe an Lexware Office oder als DATEV-Buchungsstapel;
  Buchhaltung mit offenen Posten, Zahlungen und Einnahmenüberschussrechnung; Eingangsrechnungen lesen und einpflegen;
  Auswertungen zur Profitabilität.
- **Personal und Zeiten:** Funktionen, Qualifikationen mit Ablaufdatum, Abwesenheiten, „Mein Bereich“, Einsatzanfragen mit
  Zusage und Absage (im Browser oder per Antwort-Mail), Preisangebote freier Kräfte, Zuschläge als Regeln je Land,
  Zeiterfassung mit Stoppuhr und Hinweisen zu Ruhezeiten, Freigabe, Stundenzettel, Spesen und Fahrtkosten mit Belegfoto.
- **Mail und KI:** mehrere Postfächer, Zuordnung zu Projekten über das Kürzel im Betreff, Antworten aus dem Projekt mit
  Dokumenten im Anhang, Notizen; Zusammenfassungen der Korrespondenz durch eine lokale KI (llama.cpp) auf dem eigenen Server
  oder durch einen eigens eingerichteten Dienst; Automationen „Wenn … dann …“ mit Protokoll.
- **Planung und Überblick:** Kalender, Zeitstrahl aller Projekte, Personalplan, Startseite mit dem, was ansteht,
  Benachrichtigungen nach Kategorien in der Anwendung, per Mail und in der App.
- **Daten rein und raus:** Import aus Excel-Listen mit Vorschau (Material, Produkte, Kunden, Personal), Export im Importformat,
  CSV aus jeder Liste, programmierbare Schnittstelle (API) für alle Fachfunktionen, Webhooks.
- **Betrieb:** Installations-, Aktualisierungs- und Sicherungsskripte, Sicherung auch aus dem Browser, Datenbank auf diesem oder
  einem vorhandenen Server, auf Wunsch verschlüsselt; Betrieb auch auf einem Raspberry Pi 4 oder 5; Adresse und Zertifikat
  in den Einstellungen; das [Rentalars Gateway](docs/betrieb/gateway.md), über das Apps den Server aus dem Internet erreichen,
  lässt sich in den Einstellungen koppeln; Selbsttest; nur HTTPS; Rentalars selbst bekommt nie Root-Rechte.

Rentalars sendet von sich aus keine Daten an Dritte: keine Schriften, Skripte oder Statistiken von fremden Servern, keine Prüfung
auf neue Versionen. Eine Adresse geht nur dann an OpenStreetMap oder Google Maps, wenn jemand die Karte oder Route öffnet; die
Karten lassen sich ganz abschalten.

## Installieren

Auf einem frisch installierten Ubuntu Server 24.04 LTS oder 26.04 LTS – oder auf einem Raspberry Pi 4 oder 5 mit Ubuntu Server
oder Raspberry Pi OS auf Basis von Debian 13 –, als Nutzer mit `sudo`:

```sh
tar -xzf rentalars-1.0.0.tar.gz
cd rentalars-1.0.0
sudo ./deploy/install.sh
```

Das Skript fragt nach dem Namen des Servers, der Art des Zertifikats, wo die Datenbank liegen soll und ob sie verschlüsselt wird,
richtet alles ein – auch die nötigen Systempakete – und nennt am Ende die Adresse für die Ersteinrichtung im Browser. Es spricht
Deutsch, wenn die Spracheinstellung des Servers Deutsch ist, sonst Englisch (`RENTALARS_LANG=de` erzwingt Deutsch). Die
ausführliche Anleitung: [docs/betrieb/installation.md](docs/betrieb/installation.md); zum Aktualisieren siehe
[docs/betrieb/aktualisierung.md](docs/betrieb/aktualisierung.md).

## Anleitungen

Für den Betrieb (deutsch):

| Thema | Datei |
|-------|-------|
| Installation, HTTPS, Systemanforderungen | [docs/betrieb/installation.md](docs/betrieb/installation.md) |
| Täglicher Betrieb, Einstellungen, Fehlersuche | [docs/betrieb/betrieb.md](docs/betrieb/betrieb.md) |
| Aktualisierung und Rückweg | [docs/betrieb/aktualisierung.md](docs/betrieb/aktualisierung.md) |
| Sicherung und Wiederherstellung | [docs/betrieb/sicherung.md](docs/betrieb/sicherung.md) |
| Apps über das Rentalars Gateway aus dem Internet erreichen | [docs/betrieb/gateway.md](docs/betrieb/gateway.md) |
| Verschlüsselung von Datenbank und Sicherungen | [docs/betrieb/verschluesselung.md](docs/betrieb/verschluesselung.md) |
| Import: Excel-Liste, Produkte, Kunden, Personal | [docs/betrieb/import.md](docs/betrieb/import.md) |
| Benutzerhandbuch | [docs/handbuch/benutzerhandbuch.md](docs/handbuch/benutzerhandbuch.md) |

Handbuch und Anleitungen auf Englisch: [docs/en/README.md](docs/en/README.md).

## For developers

Code, comments and developer documentation are in English; the user
interface and the manuals are German and English (the English texts of the
interface are the message IDs, German comes from `locale/de`).

| Topic | File |
|-------|------|
| Setting up a development environment, running the checks | [docs/dev/getting-started.md](docs/dev/getting-started.md) |
| Structure and modules | [docs/dev/architecture.md](docs/dev/architecture.md) |
| Data model with diagram | [docs/dev/data-model.md](docs/dev/data-model.md) |
| How availability, prices, packing, crew planning, time entry, the import, mail assignment, invoices and encryption work | [docs/dev/core-flows.md](docs/dev/core-flows.md) |
| Accessibility: what is checked and how | [docs/dev/accessibility.md](docs/dev/accessibility.md) |
| Decisions and their reasons | [docs/dev/decisions.md](docs/dev/decisions.md) |
| Requirement → code → test | [docs/dev/traceability.md](docs/dev/traceability.md) |

Quick start:

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate && python manage.py create_demo_data
python manage.py runserver        # http://localhost:8000, first-run setup in the browser
python manage.py test             # all tests
scripts/check.sh                  # everything the continuous integration checks
```

The API describes itself: with the development server running, open
<http://localhost:8000/api/v1/docs/>.

## Lizenz

Rentalars steht unter der GNU General Public License, Version 3 oder später
(GPL-3.0-or-later); der Text liegt in [LICENSE](LICENSE). Dazu gilt eine
Bestimmung nach Abschnitt 7 b der GPL: Wer Rentalars
weitergibt, muss den Urhebervermerk „von fld-vt.de“ in der Oberfläche
erhalten ([ADDITIONAL-TERMS.md](ADDITIONAL-TERMS.md)). Mitgelieferte
Schriften und verwendete Bibliotheken mit ihren Lizenzen nennt
[THIRD-PARTY.md](THIRD-PARTY.md).

Copyright © 2026 Lars Wilting, fld-vt.de.

**Entstehung mit KI.** Große Teile von Rentalars – Programmcode, Tests und Dokumentation – wurden mit Hilfe von
KI-Assistenten geschrieben, vor allem mit Claude (Anthropic, über Claude Code). Die Anforderungen, die Entscheidungen und die
Abnahme liegen bei Lars Wilting. Commits, an denen ein KI-Assistent beteiligt ist, nennen diesen mit einer Zeile
`Co-Authored-By: Claude <noreply@anthropic.com>` (mit dem jeweiligen Modellnamen), sodass GitHub Claude am Commit als Mit-Autor
zeigt. Ob und wie weit an solchem Code Urheberrechte bestehen, ist rechtlich nicht abschließend geklärt; die Lizenz oben gilt für
alles, was daran Schutz genießt.

> This program is free software: you can redistribute it and/or modify it
> under the terms of the GNU General Public License as published by the Free
> Software Foundation, either version 3 of the License, or (at your option)
> any later version. This program is distributed in the hope that it will be
> useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
> MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General
> Public License for more details.

Auf Deutsch: Das Programm darf frei genutzt, weitergegeben und verändert
werden, solange Weitergaben wieder unter derselben Lizenz stehen. Es gibt
keinerlei Gewährleistung.

Rentalars ist für jeden Betrieb kostenlos und selbst installierbar. Jeder
Betrieb betreibt seine eigene Instanz mit eigener Datenbank; mehrere Betriebe
in einer Installation sind nicht vorgesehen.
