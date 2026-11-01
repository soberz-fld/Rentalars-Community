# Rentalars – Anforderungskatalog

Version 1.0 · Stand: 01.11.2026

Webanwendung zur Projekt-, Material- und Personalverwaltung in der Veranstaltungstechnik.


Inhalt

    0. Zu diesem Dokument
    1. Projektüberblick
    2. Glossar
    3. Rahmenbedingungen
    4. Nutzerrollen
    5. Funktionale Anforderungen
    6. Nicht-funktionale Anforderungen (NFA)
    7. Datenmodell (Entwurf)
    8. API-Ressourcen (Entwurf)
    9. Technische Grundlage
    10. Ausbaustufen
    11. Abnahmeszenarien (Auszug)
    12. Entscheidungen und offene Punkte
    13. Quellen


## 0. Zu diesem Dokument

### 0.1 Zweck

Dieser Katalog beschreibt, was Rentalars können soll. Er dient als Grundlage für
Architekturentscheidungen, Aufwandsschätzung, Umsetzung und spätere Abnahme.
Er beschreibt bewusst das WAS, nicht das WIE – Ausnahmen sind die fest
vorgegebenen technischen Rahmenbedingungen (Kapitel 3).

### 0.2 Lesehinweise

Jede Anforderung hat eine eindeutige ID, eine Priorität, eine Herkunft und
eine Ausbaustufe:

    MAT-012 [MUSS · V · S1]  Text der Anforderung

Priorität – sie gilt innerhalb der genannten Stufe
- MUSS – ohne diese Anforderung ist die Stufe nicht fertig
- SOLL – gehört zur Stufe, darf aber nachgezogen werden
- KANN – wünschenswert, optional

Herkunft
- V – Vorgabe oder Entscheidung des Auftraggebers
- A – abgeleitet oder Vorschlag; ergibt sich aus einer Vorgabe oder ist in der
      Branche üblich. Einzelne Annahmen innerhalb einer Vorgabe tragen [A].

Stufe
- S1 bis S10 – Ausbaustufe, in der die Anforderung umgesetzt wird
  (Kapitel 10; S9 ist die Logistik und S10 die weiteren Erweiterungen; zu S9
  gehören auch die Wünsche und die Erfahrungen aus der Benutzung; zu S10
  gehört die Anbindung des Rentalars Gateway, und S11 hält Vorgemerktes
  fest). Was
  nicht S1 ist, wird für den ersten einsetzbaren Stand nicht gebraucht.

IDs sind stabil: Sie werden nie neu vergeben oder umnummeriert. Die
Reihenfolge im Text folgt dem Thema, nicht der Nummer.

Getroffene Entscheidungen stehen in Kapitel 12.1, noch zu bestätigende
Annahmen in 12.2, der Änderungsverlauf in Anhang A.

### 0.3 ID-Präfixe

| Präfix | Bereich                                   |
|--------|-------------------------------------------|
| AUT    | Anmeldung, Nutzer, Rechte                 |
| MAT    | Materialverwaltung                        |
| PRD    | Produktverwaltung                         |
| KND    | Kundenverwaltung                          |
| PER    | Personalverwaltung                        |
| PRJ    | Projektverwaltung                         |
| VFG    | Verfügbarkeit und Disposition             |
| PCK    | Packlisten, Ausgabe, Rücknahme            |
| ZEI    | Zeiterfassung                             |
| DOK    | Dokumente und Vorlagen                    |
| UIX    | Oberfläche, Suche, Dashboard              |
| IMP    | Import und Export                         |
| API    | Programmierschnittstelle                  |
| ADM    | Administration und Stammdaten             |
| EML    | E-Mail-Zuordnung zu Projekten             |
| APP    | Begleit-App für Android                   |
| LOG    | Logistik und Fuhrpark |
| GWL    | Anbindung an das Rentalars Gateway |
| NFA    | Nicht-funktionale Anforderungen           |

## 1. Projektüberblick

### 1.1 Vision

Rentalars ist eine vollumfängliche Projektverwaltung für
Veranstaltungstechnik-Betriebe. Ein Projekt (Veranstaltung, Vermietung,
Produktion) bündelt Kunde, benötigtes Material und eingesetztes Personal über
einen Zeitraum. Das System beantwortet jederzeit drei Fragen:

1. Was haben wir? (Material mit Modellen und einzelnen Exemplaren)
2. Was ist wann frei? (Verfügbarkeit von Material und Personal)
3. Was geht wann mit wem wohin? (Projekt, Packliste, Crew, Zeiten)

### 1.2 Einordnung

Rentalars ist eine Eigenentwicklung (Entscheidung in Kapitel 9). Es verbindet
Materialverwaltung, Projekt-, Material- und Personaldisposition mit der
Zuordnung eingehender E-Mails über eine Kennung im Betreff (Kapitel 5.15).

### 1.3 Zielgruppe

Kleine bis mittlere Betriebe der Veranstaltungstechnik (Ton, Licht, Video,
Bühne, Rigging, Strom) mit eigenem Materialbestand, festen Mitarbeitenden und
freien Kräften.

### 1.4 Leitprinzipien

- API-first: Jede Funktion ist über die API erreichbar. Oberfläche und API
  greifen auf dieselbe Fachlogik zu.
- Verständlich: Der Code erklärt, was er tut und warum; wer Grundkenntnisse
  hat, soll ihn nachvollziehen und pflegen können.
- Responsive: Vollständig nutzbar am Desktop, im Lager auf dem Tablet und
  unterwegs auf dem Smartphone.
- Produkt vor Exemplar: Geplant wird mit Produkten und Mengen ("6x XLR 5 m"),
  nicht mit einzelnen Geräten. Welches konkrete Exemplar mitgeht, entscheidet
  sich beim Packen; ein Scan ist dafür nie Voraussetzung.
- Schnell erfassbar: Häufige Vorgänge (Zeit buchen, Position hinzufügen,
  Material ausgeben) brauchen möglichst wenige Schritte.
- Getrennte Rechte: Finanzielle Angaben und Kundenkorrespondenz sind stets
  eigens berechtigt.
- Nachvollziehbar: Änderungen an Material, Projekten und Zeiten sind
  protokolliert.

### 1.5 Abgrenzung (nicht Bestandteil der ersten Ausbaustufen)

- Finanzbuchhaltung, Mahnwesen, Zahlungsabgleich
- Lohn- und Gehaltsabrechnung; Zuschläge und Spesen (PER-009, ZEI-019)
  gehen nur in Preis und Kosten des Projekts ein
- Online-Shop bzw. Kundenportal zur Selbstbuchung
- Fahrzeug- und Tourenplanung; ein Projekt nennt seine
  Fahrten mit Routenlinks, ohne Entfernungen zu berechnen (PRJ-097). Die
  Logistik – Fuhrpark, Fahrzeuge und Anhänger je Fahrt,
  Abrechnung nach Kilometern oder Tagen – ist Stufe 9
  (Kapitel 5.17); eine Tourenplanung über mehrere Projekte bleibt
  ausgenommen. Kilometer schlägt ein optional
  nachinstallierter Routendienst vor (LOG-017 KANN); ohne ihn werden sie von
  Hand eingetragen
- Werkstatt-/Reparaturauftragsverwaltung über einfache Statusmeldungen hinaus
- Native Apps (die responsive Webanwendung deckt mobile Nutzung ab). Ausnahme:
  eine Begleit-App für Android zum Packen und zur
  Zeiterfassung ohne Netz (Kapitel 5.16)
- Vollwertiges E-Mail-Programm oder eigener Mailserver: Rentalars ruft ein
  bestehendes Postfach ab und ordnet Mails Projekten zu (Kapitel 5.15)
- Arbeitsrechtlicher Arbeitszeitnachweis: Die Zeiterfassung dient nur der
  Projektabrechnung und Nachkalkulation; die Hinweise auf auffällige Zeiten
  (ZEI-018) ändern daran nichts
- Mandantenfähigkeit: Jeder Betrieb betreibt seine eigene Instanz

Auftragsbestätigung, Lieferschein und Rechnung sind für spätere Ausbaustufen
vorgesehen (DOK-003, DOK-006), ebenso die Übergabe an eine Buchhaltung.

Angebote werden außerhalb von Rentalars erstellt. Rentalars liefert dafür die
Preisgrundlage je Teilgruppe (PRJ-033 ff.), zunächst als Ansicht im Browser
zur händischen Übertragung; ein eigenes Angebotsdokument ist nur optional
vorgesehen (DOK-002). Das Angebot gibt es als Dokument
(DOK-010).


## 2. Glossar

| Begriff            | Bedeutung                                                                 |
|--------------------|---------------------------------------------------------------------------|
| Kategorie          | Gemeinsame Gliederung für Material und Produkte; liefert das Kürzel        |
| Materialmodell     | Ein konkreter Artikeltyp eines Herstellers (z. B. "Cordial CPM 5 FM")      |
| Materialinstanz    | Ein einzelnes physisches Exemplar eines Modells, ggf. mit Seriennummer     |
| Mengenmaterial     | Material, das nicht einzeln, sondern nur als Stückzahl geführt wird        |
| Produkt            | Das, was geplant, vermietet oder verkauft wird (z. B. "XLR-Kabel 5 m")     |
| Set                | Produkt aus mehreren anderen Produkten; Material bleibt einzeln mietbar    |
| Nebenkosten        | Produktart ohne Bestand für Transport, Reisekosten u. Ä. (PRD-045)         |
| Verbaut in         | Verweis eines Exemplars auf den Behälter, in dem es verbaut ist oder liegt |
| Behälter           | Case, Rack oder Road-Case, der anderes Material enthält; "Gerät" nur für Elektrogeräte und Fixtures (UIX-063) |
| Crew               | Die Personen, die in einem Projekt eingeplant sind; "Personal" ist das Modul und die Kostenart (UIX-063) |
| Projekt            | Veranstaltung/Auftrag mit Kunde, Material, Personal und Zeitraum           |
| Materialposition   | Zeile im Projekt: Produkt + Menge + Zeitraum                               |
| Teilgruppe         | Benannte Gliederung der Positionen in einem Projekt mit eigener Preissumme |
| Teilprojekt        | Eigenständiger Teil eines Projekts mit eigenem Zeitraum, Ort und Personal  |
| Funktion           | Rolle einer Person im Einsatz (z. B. Tontechniker, Stagehand, Fahrer)      |
| Dienstleistungsprodukt | Preis der Crew einer Funktion, Produkt der Kategorie D; 1:1 (PRD-044)  |
| Personalposition   | Zeile im Projekt: Funktion + Person + Zeitraum                             |
| Disposition        | Planung, welches Material und Personal wann in welchem Projekt gebunden ist|
| Packliste          | Liste des für ein Projekt zu packenden Materials                           |
| Zeiteintrag        | Erfasste Arbeitszeit einer Person zu Projekt und Funktion                  |
| Abrechnungsart     | Wie ein Preis gerechnet wird: Tagesmiete, pauschal, nach Stunden, Aufwand  |
| Miettage           | Berechnete Tage für die Tagesmiete; unabhängig vom Dispositionszeitraum    |
| Staffel            | Tabelle: Zahl der Miettage → Faktor auf den Tagesmietpreis                 |
| Zumietung          | Material eines Lieferanten, geplant über Produkte der Kategorie E          |
| Kundenmaterial     | Material eines Kunden im eigenen Lager, Kategorie C; ohne Preis            |
| Projektkürzel      | Kennung im E-Mail-Betreff, die eine Mail einem Projekt zuordnet            |
| Korrespondenz      | Die einem Projekt zugeordneten E-Mails samt Anhängen                       |
| Modul              | Fachlicher Bereich der Anwendung, auf den Rechte vergeben werden           |
| Wiedervorlage      | Tag, an dem ein Projekt mit Notiz einer Person wieder vorgelegt wird       |
| Überblick          | Projekt-Reiter: wann, wo, als was, mit wem; als PDF "Einsatzübersicht"     |
| Servicefall        | Projekt einer eigenen Art für einen Servicefall, ohne Planung (PRJ-090)   |
| Zuschlag           | Prozent auf Preis und Kosten für Nacht, Sonn- und Feiertag (PER-009);     |
|                    | Regeln, die in jedem Land passen (PER-040)                                |
| Kaufset            | Exemplare, die zusammen zu einem Preis gekauft wurden; der Preis steht am |
|                    | ersten, die übrigen verweisen darauf (MAT-054)         |
| Rechnung gestellt  | Vermerk am Projekt, wenn die Rechnung in einem anderen Programm entstand  |
|                    | (DOK-015)                                              |
| Notiz (Korrespondenz) | Telefonat oder Gespräch mit Zeitpunkt, in der Chronologie der Mails    |
|                    | (EML-051)                                              |
| Fuhrpark           | Die eigenen Fahrzeuge und Anhänger, verwaltet in der Materialverwaltung   |
|                    | (LOG-002, Stufe 9)                                                        |
| Zugfahrzeug        | Fahrzeug, das auf einer Fahrt einen Anhänger zieht (LOG-006)              |
| Anhängerzuschlag   | Betrag je Kilometer, um den der Satz eines Fahrzeugs mit Anhänger steigt  |
|                    | (LOG-006)                                                                 |
| Fahrzeugbuchung    | Ein Fahrzeug oder Anhänger im Block "Logistik" eines Projekts, mit        |
|                    | Zeitraum und Sätzen (LOG-001)                          |
| Fahrteinsatz       | Ein KFZ auf einer Fahrt des Projekts, mit Anhänger und Kilometern         |
|                    | (LOG-007)                                              |
| Monatsabrechnung   | Sammelrechnung der Servicefälle eines Kunden und Monats (DOK-016)         |
| Routendienst       | Optional installierter Dienst, der Kilometer einer Fahrt vorschlägt       |
|                    | (LOG-017)                                              |
| Kauf einpflegen    | Ein Kauf mit Händler, Rechnung und vielen Exemplaren in einem Schritt     |
|                    | (MAT-061)                                              |
| Fest eingeplant    | Eine Person ohne Anfrage eingeplant; zählt wie eine Zusage (PER-041)      |
| Ausgangsbelege     | Alle Belege an Kunden, unter Buchhaltung (DOK-020)     |
| Audit              | Kurze Kontrolle eines Exemplars, fällig nach dem Audit-Intervall          |
|                    | (MAT-067, MAT-068)                                     |
| To-Do              | Kleinigkeit an einem Exemplar ("Label fehlt"), offen bis erledigt         |
|                    | (MAT-069)                                              |
| Eigenes Feld,      | Feld mit eigenem Wert je Exemplar; Feldsatz: die eigenen Felder eines     |
| Feldsatz           | Materialmodells (MAT-071, MAT-072)                     |
| Schloss            | Eine Nachricht mit Schloss lesen nur Berechtigte mit Preisrecht, eine     |
|                    | offene auch die Crew (EML-055)                         |
| Verwandt           | Projekte und Servicefälle, die miteinander zu tun haben (PRJ-119)         |
| Schutzklasse       | I, II oder III eines Elektrogeräts; bestimmt die Messungen und Grenzwerte |
|                    | der elektrischen Prüfung (MAT-077, MAT-078)            |
| Kalender-Link      | Geheime Adresse eines Kalenders (.ics) mit den Buchungen eines Produkts,  |
|                    | Modells oder Exemplars (VFG-040)                       |
| Lagerplatz         | Kurzer Platz eines Exemplars innerhalb seines Lagerorts, z. B. 03-A-2     |
|                    | (MAT-080)                                              |
| Gesamtrabatt       | Rabatt auf die Netto-Summe eines Projekts, in Prozent oder Euro           |
|                    | (PRJ-123)                                              |
| Textposition       | Position einer Planung, die nur einen Text trägt (PRJ-128, seit Version   |
| Ausgangsbeleg ohne | Angebot oder Rechnung ohne Projekt, mit eigenen Zeilen (DOK-022)          |
| Projekt            |                                                                           |
| Stück je Produkt   | Wie viele Exemplare des Materials ein Produkt ausmachen (PRD-052)         |
| Eingangsrechnung   | Rechnung eines Lieferanten im Register der Buchhaltung (DOK-023)          |
| Anschaffungs-      | Fracht, Verpackung, Zoll …, aufgeteilt auf die Ware (DOK-024)             |
| nebenkosten        |                                                                           |
| Anlagenspiegel     | Anschaffungskosten, Abschreibung und Restbuchwert je Exemplar (MAT-086)   |
| Massenprüfung      | Eine Prüfung mehrerer gewählter Exemplare in einem Zug (MAT-082)          |

Beziehung Material und Produkt am Beispiel:

    Produkt   K-005  "XLR-Kabel 5 m"                (wird geplant: 6 Stück)
       |
       +-- Modell "Cordial CPM 5 FM"                (Hersteller A)
       |      +-- Instanz 0101
       |      +-- Instanz 0102
       |      +-- Instanz 0103
       |      +-- Instanz 0104
       |
       +-- Modell "Sommer Cable Stage 22 5 m"       (Hersteller B)
              +-- Instanz 0201
              +-- ...
              +-- Instanz 0205

    Bestand des Produkts K-005 = 4 + 5 = 9 Stück

Abgrenzung Teilgruppe und Teilprojekt:

    Projekt "Stadtfest 2027"                         (Gesamtproduktion)
       |
       +-- Teilprojekt "Hauptbühne"                  (eigener Zeitraum, Ort, Crew)
       |      +-- Teilgruppe "Licht Front-Traverse"  (Positionen + Zwischensumme)
       |      +-- Teilgruppe "Licht Rear-Traverse"   (Positionen + Zwischensumme)
       |      +-- Teilgruppe "Ton FOH"
       |
       +-- Teilprojekt "Nebenbühne"
              +-- Teilgruppe "Licht"
              +-- Teilgruppe "Ton"

Teilgruppen gliedern die Positionen eines Projekts und liefern Preise je
Abschnitt. Teilprojekte teilen eine Produktion in getrennt planbare Einheiten;
sie sind für eine spätere Ausbaustufe vorgesehen.

Abgrenzung Set und "verbaut in":

    Set T-100 "Aktivbox-Set"                 (Produktebene: wird beim Packen
       = 1x T-010 Aktivbox                    aus beliebigen freien Exemplaren
       + 1x S-020 Boxenstativ                 gebildet; die Bestandteile
       + 1x K-010 XLR-Kabel 10 m              bleiben einzeln mietbar)

    Exemplar 0500 Funkrack                   (Exemplarebene: dauerhaft)
       +-- Exemplar 0310 Funkempfänger        verbaut in 0500
       +-- Exemplar 0742 Rackblende 1 HE      verbaut in 0500


### 2.1 Übersetzungsliste für den Code

Im Code ist alles englisch (NFA-061). Damit dieselbe Sache überall gleich
heißt, gilt diese Liste für Bezeichner, Kommentare und API-Pfade. Sie ist ein
Vorschlag [A] und wird mit dem Datenmodell fortgeschrieben.

| Deutsch (Katalog)              | Englisch (Code)                                                          |
|--------------------------------|--------------------------------------------------------------------------|
| Kategorie                      | category                                                                 |
| Hersteller                     | manufacturer                                                             |
| Händler                        | supplier                                                                 |
| Materialmodell                 | material model                                                           |
| Materialinstanz, Exemplar      | material item                                                            |
| Mengenmaterial                 | bulk material                                                            |
| verbaut in                     | installed in                                                             |
| fest verbaut / lose enthalten  | fixed / loose                                                            |
| Lagerort                       | storage location                                                         |
| Produkt                        | product                                                                  |
| Dienstleistungsprodukt         | service product                                                          |
| Nebenkosten                    | incidental costs (Produktart "incidental")                               |
| Set                            | kit (nicht "set": das ist in Python ein eigener Datentyp)                |
| Bestandteil eines Sets         | component                                                                |
| Abrechnungsart                 | billing mode                                                             |
| Miettage                       | rental days                                                              |
| Staffel                        | rental scale                                                             |
| Aufpreis                       | surcharge                                                                |
| Steuerart                      | tax rate                                                                 |
| Kunde                          | customer                                                                 |
| Ansprechpartner                | contact                                                                  |
| Veranstaltungsort              | venue                                                                    |
| Person                         | person                                                                   |
| Funktion                       | job function (nicht "function" und nicht "role", siehe unten)            |
| Rolle (Rechte)                 | role                                                                     |
| Stundensatz                    | hourly rate                                                              |
| Tagessatz                      | daily rate                                                               |
| Pauschale                      | flat rate                                                                |
| Abwesenheit                    | absence                                                                  |
| Projekt                        | project                                                                  |
| Wiedervorlage                  | follow-up                                                                |
| Überblick (Projekt-Reiter)     | deployment view                                                          |
| Teilprojekt                    | subproject                                                               |
| Teilgruppe                     | group                                                                    |
| Materialposition               | material line                                                            |
| Personalposition               | crew line                                                                |
| Dispositionszeitraum           | reservation period                                                       |
| Pufferzeit                     | buffer time                                                              |
| Verfügbarkeit                  | availability                                                             |
| Fehlmenge, Fehlbestand         | shortage                                                                 |
| Zumietung                      | subrental                                                                |
| Kundenmaterial                 | customer material                                                        |
| Eigentümer (Produkt)           | owner                                                                    |
| Packliste                      | packlist                                                                 |
| als zurück abgehakt            | returned (ticked as back)                                                |
| zurückgenommen (gebucht)       | taken back                                                               |
| Zeiteintrag                    | time entry                                                               |
| Freigabe (von Zeiten)          | approval                                                                 |
| Postfach                       | mailbox                                                                  |
| Projektkürzel                  | project tag                                                              |
| Korrespondenz                  | correspondence                                                           |
| Nummernkreis                   | number range                                                             |
| frühere Projektnummer          | former number                                                            |
| Kaufset, Preis enthalten in    | purchase set, purchase_price_in                             |
| Rechnung gestellt, keine Rechnung | invoice issued, no invoice (invoice_status)               |
| Notiz (in der Korrespondenz)   | note (direction "note",)                                      |
| Etiketten-Einstellungen        | label settings                                              |
| Fuhrpark, Fahrzeug, Anhänger   | fleet, vehicle, trailer (Stufe 9)                                        |
| Anhängerzuschlag               | trailer surcharge (Stufe 9)                                              |
| Fahrzeugbuchung, Fahrteinsatz  | vehicle booking (VehicleLine), vehicle on a trip (TripVehicle)            |
| Monatsabrechnung               | monthly statement (Stufe 9)                                              |
| Routendienst                   | route service (Stufe 9)                                                  |
| Kauf einpflegen                | purchase entry                                              |
| fest eingeplant                | firm (request status)                                        |
| Buchhaltung, Ausgangsbelege    | accounting, outgoing documents                              |
| Überblick ohne Planung         | project scope "deployment"                                  |
| Audit, To-Do, Offene Punkte    | audit, to-do, open items (Materialverwaltung)                |
| Eigenes Feld, Feldsatz         | custom field, fieldset                                      |
| mit Schloss, offen             | locked, open                                                |
| verwandt                       | related                                                     |
| Export im Importformat         | export in the import format                                 |
| Schutzklasse                   | protection class                                            |
| elektrische Prüfung            | electrical inspection                                       |
| Kalender-Link                  | calendar link                                               |
| Lagerplatz                     | storage spot                                                |
| Gesamtrabatt                   | overall discount                                            |
| Textposition                   | text line                                                   |
| Stück je Produkt               | pieces per product                                          |
| Eingangsrechnung               | incoming invoice                                           |
| Anschaffungsnebenkosten        | ancillary acquisition cost                                 |
| Anlagenspiegel                 | fixed asset register                                       |

"Funktion" wird zu "job function": "function" würde mit Programmfunktionen
verwechselt, "role" bezeichnet bereits die Nutzerrolle der Rechteverwaltung.


## 3. Rahmenbedingungen

### 3.1 Technische Vorgaben

- Webanwendung, responsive [V]
- API-first [V]
- Datenbank: MariaDB [V]
- Anmeldung und Nutzerverwaltung mit abgestuften Rechten [V]
- Einfache Installation mit wenig Aufwand, beispielsweise unter Ubuntu Server
  mit NGINX [V]; auch auf einem Raspberry Pi mit Ubuntu
  Server für den Raspberry Pi oder Raspberry Pi OS (Debian 13) [V, NFA-070]
- Ausreichende Leistung auf 4 Kernen und 8 GB RAM für einen kleinen Betrieb
  mit höchstens zwei gleichzeitigen Nutzern [V]
- Eigenentwicklung, nicht auf einem fremden System aufgebaut [V, Kapitel 9]
- Eine Instanz je Betrieb, nicht mandantenfähig; kostenlos für jeden Betrieb
  zur eigenen Installation verfügbar [V]
- Betrieb auf eigenem Server mit Zertifikat; in der Testphase nur per VPN
  erreichbar, später auch aus dem Internet [V]
- Technikstack: Python mit Django hinter NGINX, MariaDB [V, Kapitel 9]
- KI: Wahlweise fasst eine lokale KI
  die Korrespondenz zusammen – ein Inferenzserver mit einem kleinen
  mehrsprachigen Modell auf demselben Server, den der Betreiber per Befehl
  über SSH installiert; das gilt für jede Installation, nicht nur für den
  Raspberry Pi [V, EML-040]. Andere Verwendungen gehen über eine
  OpenAI-kompatible Schnittstelle, die anfangs ausgeschaltet ist [V,
  ADM-017].
- Nachvollziehbar dokumentierter Code: was geschieht und warum [V]
- Lizenz: GNU General Public License v3.0 oder später [V]

### 3.2 Annahmen

- Je Betrieb eine eigene Instanz auf einem einzelnen eigenen Server, auf dem
  Webserver, Anwendung und Datenbank gemeinsam laufen [V].
- Oberflächensprache Deutsch, Übersetzbarkeit ist vorgesehen. Englisch gibt es
  vollständig: Deutsch oder britisches Englisch je Person,
  ohne Anmeldung nach der Sprache des Browsers; die Dokumente für Kunden in
  der Sprache, die der Betrieb einstellt; das Handbuch in beiden Sprachen,
  in der Anwendung in der Sprache der Person (UIX-029).
- Währung Euro, Zeitzone Europe/Berlin, Preise werden netto gepflegt. Die
  Feiertage gelten für ein einstellbares Bundesland
  (PER-009); eigene Feiertage kommen hinzu, und die
  Zuschläge sind Regeln, die auch außerhalb Deutschlands passen (PER-040).
- Steuer: 19 % als Voreinstellung, daneben steuerfrei [V].
- Mengengerüst: höchstens zwei gleichzeitig arbeitende Nutzer auf dem
  Referenzsystem [V]; bis 100 Nutzerkonten, mehr als 10.000 Materialinstanzen
  und mehrere Hundert Projekte pro Jahr [V]. Ausgelegt und getestet wird auf
  100 Konten, 20.000 Instanzen und 1.000 Projekte pro Jahr [A].

### 3.3 Rechtliche Rahmenbedingungen (zu prüfen)

- DSGVO: Kunden-, Personal- und Zeiterfassungsdaten sind personenbezogen.
- Externe Dienste: Rentalars überträgt von sich aus keine Daten an Dritte
  (NFA-050). Adressen gehen auf einen Klick an Google Maps
  (Routenlink, UIX-033) und an OpenStreetMap: die Kartenkacheln lädt der
  Browser, die Koordinaten fragt der Server bei Nominatim ab (UIX-034). Beide
  Dienste lassen sich durch einen eigenen Server ersetzen; die Nutzungsregeln
  von OpenStreetMap und Nominatim sind zu beachten. Die
  Nutzungsregeln des Kachelservers von OpenStreetMap verlangen einen Referer;
  ohne ihn antwortet er mit "Access blocked" (403). Der Browser fragt die
  Kacheln deshalb mit der Herkunft der Installation (Schema und Adresse, ohne
  Pfad) als Referer an – erst nach "Karte anzeigen" (UIX-034).
  Namensnennung, keine Massenabrufe und eine gültige Kennung des Servers bei
  Nominatim gehören ebenso zu diesen Regeln.
- Verbindungen des Servers: Adressen, die jemand in der Oberfläche oder über
  die API einträgt und die der Server dann aufruft – Kalender, Webhooks,
  Mailserver –, erreichen keine internen Ziele, außer der
  Betreiber gibt sie in der Konfigurationsdatei frei (NFA-071); Zugangsdaten
  gehen nur an denselben Server (NFA-072). Die
  lokale KI, die der Betreiber selbst installiert, gilt als seine Sache und ist
  erlaubt (NFA-071).
- KI: Für die Zusammenfassung der Korrespondenz ist die
  lokale KI vorgesehen; dafür verlässt keine Mail das Haus (EML-040). Die
  Schnittstelle für weitere Verwendungen (ADM-017) ist anfangs
  ausgeschaltet. Wer dort einen Dienst in der Cloud einträgt, überträgt
  Mailinhalte an diesen Anbieter; Rentalars warnt deutlich davor, und ob
  dafür ein Vertrag zur Auftragsverarbeitung (DSGVO) nötig ist, prüft der
  Betrieb. Rentalars protokolliert jeden Aufruf einer KI ohne den Inhalt.
- Arbeitszeit: Die Zeiterfassung dient nur der Projektabrechnung und
  Nachkalkulation [V]. Sie ist kein arbeitsrechtlicher Arbeitszeitnachweis;
  eine dafür nötige Aufzeichnung erfolgt außerhalb von Rentalars. Die
  Hinweise auf lange Schichten, fehlende Pausen und kurze Ruhezeiten
  (ZEI-018) helfen nur beim Prüfen und halten nichts auf.
- Zuschläge: Die Voreinstellungen folgen den steuerfreien Sätzen von § 3b
  EStG (PER-009). Ob ein Zuschlag steuerfrei ist, entscheidet die
  Lohnabrechnung außerhalb von Rentalars. Die
  Zuschläge sind Regeln, die in jedem Land passen; der Knopf "Nach § 3b EStG
  einstellen" stellt die deutschen Sätze ein (PER-040).
- Prüfpflichten für elektrische Betriebsmittel (z. B. nach DGUV Vorschrift 3)
  sind in der Branche üblich und sollten abbildbar sein (MAT-030 ff.).
- Falls Rechnungen erzeugt werden: Anforderungen an ordnungsgemäße Rechnungen
  und an elektronische Rechnungen im B2B-Bereich beachten.


## 4. Nutzerrollen

Die Rollen sind Vorschläge für eine Erstausstattung. Rollen und ihre Rechte
sind frei konfigurierbar (AUT-010).

| Rolle              | Typische Aufgaben                                                        |
|--------------------|--------------------------------------------------------------------------|
| Administrator      | Nutzer, Rechte, Stammdaten, Systemeinstellungen                          |
| Projektleitung     | Projekte anlegen, Material und Personal disponieren, kalkulieren         |
| Lager              | Material pflegen, Packlisten abarbeiten, Ausgabe und Rücknahme, Defekte  |
| Personaldisposition| Personen, Funktionen, Stundensätze, Verfügbarkeiten, Zeiten freigeben    |
| Crew               | Eigene Einsätze sehen, eigene Zeiten erfassen, Packliste 1:1 abarbeiten  |
| Freie Kraft        | Nur das Wichtigste: eigene Einsätze, Stunden, keine Projektinfos         |
| Nur-Lesen          | Einsicht ohne Änderungsrechte (z. B. Buchhaltung, Geschäftsführung)      |

Die Crew packt
(Entscheidung des Auftraggebers, 12.1) in ihren
eigenen Projekten, im Browser und in der Begleit-App, auch ohne Netz:
alles, was schreiben heißt, aber keine finanzielle Wirkung hat. Material
nachtragen darf sie nicht (PCK-013); sie hält sich 1:1 an die Packliste.

Vier Rollen starten mit anderen
Rechten (AUT-036): die Freie Kraft ohne Verfügbarkeit des Materials und nur ihren
Projekten zugeordnet, ohne Planung; die Crew liest die Korrespondenz; das
Lager legt Material an und bearbeitet es, ohne es zu löschen, und liest die
Korrespondenz; die Projektleitung liest Produkte und legt Projekte an und
bearbeitet sie, ohne sie zu löschen.


## 5. Funktionale Anforderungen

### 5.1 Anmeldung, Nutzer- und Rechteverwaltung (AUT)

Anmeldung

- AUT-001 [MUSS · V · S1] Die Anwendung ist nur nach Anmeldung nutzbar.
- AUT-002 [MUSS · A · S1] Anmeldung mit E-Mail-Adresse oder Benutzername und
  Passwort.
- AUT-003 [MUSS · A · S1] Passwörter werden ausschließlich als Hash mit einem
  aktuellen Verfahren gespeichert; es gilt eine konfigurierbare
  Passwortrichtlinie (Mindestlänge).
- AUT-004 [MUSS · A · S1] Passwort zurücksetzen per E-Mail-Link mit begrenzter
  Gültigkeit.
- AUT-005 [MUSS · A · S1] Schutz vor Durchprobieren von Passwörtern (Sperre
  bzw. Verzögerung nach Fehlversuchen).
  Falsche Codes der Zwei-Faktor-Anmeldung zählen wie falsche Passwörter, im Browser und in der API
  (/auth/login); ein richtiges Passwort löscht die Zählung nicht, solange der Code fehlt. Die Sperre gilt für den
  Namen des Kontos, gleich wie er getippt wurde.
- AUT-006 [SOLL · A · S4] Zwei-Faktor-Anmeldung per TOTP, je Nutzer aktivierbar
  und je Rolle erzwingbar.
- AUT-007 [KANN · A · S10] Anmeldung über externen Identitätsdienst (OIDC oder
  SAML). Die Anbindung an LDAP ist eigens beschrieben (AUT-029, Stufe 10).
- AUT-008 [SOLL · A · S4] Automatische Abmeldung nach konfigurierbarer
  Inaktivität; Nutzer können ihre aktiven Sitzungen einsehen und beenden.

Nutzerverwaltung

- AUT-009 [MUSS · V · S1] Nutzer anlegen, bearbeiten, deaktivieren.
  Deaktivierte Nutzer können sich nicht anmelden; ihre Daten und Historie
  bleiben erhalten.
Die API hält dieselben Regeln ein wie die Seite: Das eigene Konto und das des letzten
  Admins lassen sich auch über die Personen-API nicht deaktivieren (400).
- AUT-010 [MUSS · V · S1] Rollen mit Rechten sind frei definierbar. Ein Nutzer
  kann eine oder mehrere Rollen haben. Vier der
  vorgeschlagenen Rollen haben eigene Standardrechte (AUT-036).
- AUT-011 [MUSS · A · S1] Einladung neuer Nutzer per E-Mail; der Nutzer setzt
  sein Passwort selbst.
- AUT-012 [MUSS · A · S3] Ein Nutzerkonto kann mit genau einer Person aus der
  Personalverwaltung verknüpft werden (Voraussetzung für Zeiterfassung und
  "meine Einsätze"). Jede Person ist ein Konto und jedes
  Konto eine Person (AUT-026).

Rechte auf Module

- AUT-013 [MUSS · V · S1] Rechte werden je Modul vergeben. Mindestens:
  Materialverwaltung, Personalverwaltung, Projektverwaltung.
- AUT-014 [MUSS · A · S1] Weitere Module mit eigenen Rechten: Produkte, Kunden,
  Zeiterfassung, E-Mail, Auswertungen, Administration. Die Auswertungen der
  Profitabilität (PRJ-115, MAT-053) hängen am Modul Auswertungen.
- AUT-015 [MUSS · A · S1] Je Modul gibt es die Stufen: kein Zugriff, lesen,
  anlegen/bearbeiten, löschen. Module ohne Zugriff erscheinen nicht in der
  Navigation.

Rechte auf Projekte

- AUT-016 [MUSS · V · S3] Rechte können auf einzelne Projekte beschränkt
  werden: Ein Nutzer sieht und bearbeitet nur Projekte, denen er zugeordnet
  ist.
- AUT-017 [MUSS · A · S3] Je Rolle ist einstellbar, ob der Projektzugriff "alle
  Projekte" oder "nur zugeordnete Projekte" umfasst.
- AUT-018 [MUSS · A · S3] Zuordnung eines Nutzers zu einem Projekt entsteht
  entweder ausdrücklich (Projektmitglied) oder automatisch über eine
  Personalposition der verknüpften Person. Die automatische Zuordnung gewährt
  nur die Einsatzsicht (AUT-025).
- AUT-019 [MUSS · V · S1] Finanzielle Angaben und Kundenkorrespondenz haben
  stets eigene Rechte, unabhängig von Modul- und Projektzugriff. Getrennt
  vergeben werden mindestens: Preise und Kalkulation (Miet- und
  Verkaufspreise, Rabatte, Summen, Gewinn aus dem Projekt), Einkaufs- und
  Kaufpreise, Stundensätze und Personalkosten sowie das Lesen und das
  Schreiben von Korrespondenz. Ohne das jeweilige Recht liefern weder
  Oberfläche noch API diese Angaben aus.
- AUT-025 [MUSS · A · S3] Der Projektzugriff ist gestuft: Einsatzsicht (Zeit,
  Ort, Funktion, Packliste, eigene Zeiten), Lesen, Bearbeiten. Keine dieser
  Stufen schließt die Rechte aus AUT-019 ein; sie kommen nur über die Rolle
  hinzu.

Durchsetzung und Nachvollziehbarkeit

- AUT-020 [MUSS · A · S1] Alle Rechte werden serverseitig in der API geprüft.
  Das Ausblenden in der Oberfläche allein genügt nicht.
- AUT-021 [MUSS · A · S1] Persönliche API-Token je Nutzer, widerrufbar, mit
  den Rechten des Nutzers oder eingeschränkt darauf. Ein
  auf Module beschränktes Token erstellt keine Tokens und sieht und widerruft
  unter den Tokens nur sich selbst; ein Token mit Ablaufdatum erstellt nur
  Tokens, die spätestens mit ihm ablaufen. Ein
  beschränktes Token, das ein Token erstellen will, wird abgewiesen (403); ein Token mit
  Ablaufdatum muss für das neue eines angeben, das nicht später liegt (sonst
  400); ein Token nur zum Lesen erstellt keine Tokens.
  Die Tabelle der Token in "Mein Konto" bleibt auch auf dem Telefon im
  Kästchen.
  Ein Token nur zum Lesen ändert nichts: Es widerruft keine Tokens, beendet keine
  Sitzungen, ändert keine Benachrichtigungseinstellungen und veröffentlicht keine Preisstaffel (403); ein solches Token, das ein
  Token erstellen will, bekommt 403 statt 400.
- AUT-022 [SOLL · A · S4] Protokoll über Anmeldungen, fehlgeschlagene
  Anmeldungen sowie Änderungen an Nutzern, Rollen und Rechten.

Eingeschränkte Konten

- AUT-023 [MUSS · V · S3] Freie Kräfte erhalten ein eigenes, eingeschränktes
  Nutzerkonto. Sie sehen nur Projekte, in denen sie eingeplant sind, und darin
  die Einsatzdaten (Zeit, Ort, Funktion, Ansprechpartner vor Ort), die
  Packliste, die Namen der Kollegen im selben Einsatz und deren Kontaktdaten,
  soweit diese sie freigegeben haben (PER-019), sowie ihre eigenen Zeiten und
  ihren eigenen Stundensatz. Preise, Kalkulation, Kundendaten (bis auf den
  Namen), Korrespondenz und die Sätze anderer bleiben verborgen. Sie
  lesen und schreiben auch im Chat ihrer Projekte (UIX-010). Sie
  sehen auch den Namen des Kunden ihrer Projekte (PRJ-122),
  ohne Link, ohne Ansprechpartner und ohne Seite des Kunden; sie
  sind nur ihren Projekten zugeordnet (AUT-036) und sehen dort den
  Überblick ohne Planung (AUT-031).
- AUT-024 [SOLL · A · S3] Ein Konto lässt sich befristen und wird nach Ablauf
  automatisch deaktiviert (z. B. für einmalig gebuchte Aushilfen).

Weitere Anforderungen

- AUT-026 [MUSS · V · S5] Personal und Nutzer sind eins: Jede Person hat eine
  Anmeldung, und jedes Konto ist eine Person. Eine neu angelegte Person
  bekommt ihr Konto mit der Rolle Crew, eine freie Kraft mit der Rolle Freie
  Kraft [A]; ein in den Einstellungen angelegtes Konto erscheint im Personal.
  Name, E-Mail-Adresse und "aktiv" werden gemeinsam geführt. Rollen und
  Rechte bleiben in den Einstellungen. Die E-Mail-Adresse ist freiwillig
  [A]; wer keine hat, bekommt ein Einmal-Passwort (AUT-027). Personen ohne
  Anmeldung gibt es nicht.
- AUT-027 [MUSS · V · S5] "Passwort vergessen" funktioniert auch für
  eingeladene Konten, die noch kein Passwort haben. Wer die Nutzer
  verwaltet, kann außerdem ein Einmal-Passwort vergeben: Es wird einmal
  angezeigt, und nach der nächsten Anmeldung ist erst ein eigenes Passwort
  zu wählen; bis dahin ist nichts anderes erreichbar, auch die API nicht
  [A]. Das Vergeben steht im Sicherheitsprotokoll.
- AUT-028 [SOLL · V · S5] Zugriffsprotokoll für die Kontrolle des
  Datenschutzes: Neben Änderungen wird festgehalten, wer Kunden, Personen und
  Projekte samt Mails, Dateien und Dokumenten geöffnet, heruntergeladen oder
  als CSV exportiert hat, ebenso den vollständigen Export und Sicherungen –
  auch über die API. Wiederholte Zugriffe derselben Person auf denselben
  Datensatz innerhalb von fünf Minuten zählen einmal [A]. Das Protokoll ist
  in den Einstellungen mit Filtern und als CSV einsehbar und wird 180 Tage
  aufbewahrt (einstellbar, mindestens 30) [A].
- AUT-029 [SOLL · V · S10] Anmeldung über LDAP bzw. Active Directory: Bedienende melden sich mit ihrem Konto aus dem
  Firmenverzeichnis an; das Passwort bleibt im Verzeichnis. Einstellungen
  unter Administration → Verzeichnis (LDAP): Server (ldap/ldaps, StartTLS,
  eigene Zertifizierungsstelle, Prüfung an), Suchkonto (das Passwort
  verschlüsselt gespeichert), Suchbasis und -filter, Zuordnung der Attribute,
  Gruppensuche. Eine Tabelle ordnet Gruppen Rollen zu (Vereinigung, Priorität,
  "letzter Treffer"); die Rollen aus dem Verzeichnis folgen bei jeder
  Anmeldung den Gruppen und sind von Hand nicht entziehbar, manuell vergebene
  bleiben. Ein Konto wird beim ersten Anmelden angelegt, wenn es mindestens
  eine Rolle bekommt; wer keiner zugeordneten Gruppe mehr angehört, wird beim
  Anmeldeversuch deaktiviert, aber nur, wenn das Verzeichnis ihn aktiviert
  hatte. Der letzte Administrator wird nie ausgesperrt; Konten, die als
  "lokal" gelten (und Superuser), werden nie im Verzeichnis gefragt und
  bleiben der Notzugang – auch nicht über den DN, nicht im Abgleich (der
  nächtliche Abgleich kann keinen Superuser deaktivieren), und ihre
  Verknüpfung (ldap_dn) wird geleert, sobald ein Konto lokal wird oder alle
  Rechte bekommt; die lokale Anmeldung lässt sich nur abschalten, wenn
  ein solcher Administrator existiert. Ein bestehendes, noch nicht
  verknüpftes Konto desselben Namens übernimmt der Verzeichnisnutzer nur,
  wenn der Schalter "bestehende Konten über den Namen verknüpfen" an ist
  (Standard aus; die Seite warnt, solange er an ist; ein Name ist kein Beweis
  für dieselbe Person); sonst wird die Anmeldung abgewiesen, dem Nutzer
  allgemein, im Protokoll und im Test mit dem Grund. Zuordnungen von Gruppen
  nehmen standardmäßig den vollständigen DN (höchstens 480 Zeichen); ein
  bloßer Name passt auf eine Gruppe dieses Namens in jedem Teil des
  Verzeichnisses und wird auf der Seite und in der API gewarnt; ldap:// ohne
  StartTLS wird gewarnt; der Pfad des CA-Zertifikats muss eine lesbare
  PEM-Datei nennen. Für einen im Verzeichnis verschobenen Eintrag gibt es die
  Verwaltungsaktion "Neuen Eintrag übernehmen", nur wenn der alte Eintrag nicht
  mehr existiert. Der Test der Anmeldung steht im Protokoll und zählt zur
  Sperre; das Bind-Passwort des Suchkontos steht nicht im Datenexport. Benutzername und Platzhalter werden
  gegen Einschleusen in Filter geschützt, ein leeres Passwort erreicht das
  Verzeichnis nie, Sperre und Begrenzung wie bei der lokalen Anmeldung
  (AUT-005), Zwei-Faktor danach wie üblich (AUT-006); Anmeldungen, Anlage,
  Rollen- und Kontenänderungen und Abgleich stehen im Protokoll (AUT-022).
  "Verbindung testen" und "Anmeldung für einen Nutzer testen" zeigen Eintrag,
  Attribute, Gruppen und Rollen, ohne etwas zu ändern. manage.py ldap_sync
  gleicht Konten ab (Standard Probelauf, --apply schreibt, eine Schutzgrenze
  bricht ab, --force übergeht sie); der nächtliche Abgleich ist eine
  Einstellung. API: ldap/settings, ldap/mappings, test-connection, test-login,
  sync, in den Nutzern local_account, ldap_dn und directory_roles. Bibliothek
  ldap3 (LGPL-3.0). Server müssen mit Namen eingetragen sein (die
  Zertifikatsprüfung vergleicht DNS-Einträge); getestet gegen ein
  Modell-Verzeichnis und einen OpenLDAP, nicht gegen Active Directory.


Ausbaustufe 9: Weitere Anforderungen

- AUT-030 [SOLL · V · S9] Hinweis an den Inhaber eines Kontos, wenn seine
  Anmeldedaten geändert werden: Ändert
  sich die E-Mail-Adresse eines Kontos – im eigenen Profil, durch die
  Verwaltung, über die API oder den Import der Personen –, geht eine Mail
  an die bisherige Adresse; ändert sich das Passwort – selbst, nach einem
  Einmalpasswort, über den Link "Passwort vergessen" oder durch die
  Verwaltung –, an die aktuelle. Sie nennt, was sich wann geändert hat, wer
  es tat (wenn nicht der Inhaber) und was zu tun ist, wenn man es nicht
  war. Keine Mail bei einem neuen Konto, dem ersten Passwort, einem
  inaktiven oder abgelaufenen Konto und der Anonymisierung; keine
  Bestätigung an die neue Adresse. Der Versand steht im
  Änderungsprotokoll des Kontos; ein Fehler beim Versand macht die
  Änderung nicht rückgängig.

Ausbaustufe 9: Weitere Anforderungen

- AUT-031 [SOLL · V · S9] Projektzugriff "Überblick ohne Planung": Der Projektzugriff einer Rolle (AUT-025)
  kann "nur zugeordnete Projekte, Überblick ohne Planung" sein. Er ist eine
  Obergrenze: In ihren Projekten öffnen solche Nutzer nur den Überblick mit
  den Phasen, die Packliste (zum Packen) und den Chat – gleich, welche
  Stufe eine Mitgliedschaft unter "Zugriff" nennt. Planung, Zeitplanung,
  Zugriff, Verlauf, Dokumente und Teilprojekte bleiben verschlossen, ebenso
  "Offene Punkte" und die Fehlbestände, auf den Seiten und im API (AUT-020).
  Der Rolleneditor bietet die Stufe an. Die Startrolle "Crew" hat sie.
- AUT-032 [SOLL · V · S9] Sonderrecht "Verfügbarkeit von Material sehen" (im Standard hat die Crew es nicht): Es
  schaltet frei, was die Verfügbarkeit des Materials zeigt – Ampeln und
  Fehlmengen in der Planung und im Dialog einer Position, Verfügbarkeit und
  Zeitleiste auf der Seite eines Produkts, die Zeitleisten von Modell und
  Exemplar, Planung → Materialauslastung, die Fehlbestände (Seite, Startseite,
  Benachrichtigung) und die zugehörigen Endpunkte des API; ohne das Recht
  liefern Planung und Positionen im API die Verfügbarkeit als null. Alle
  Startrollen außer "Crew" haben es; das Update gibt es allen bestehenden
  Rollen außer einer unveränderten "Crew", für deren Nutzer sich also nichts
  ändert. Die Verfügbarkeit der Fahrzeuge (LOG-004) gehört nicht dazu.
- AUT-033 [SOLL · V · S9] Mitarbeit am Servicefall: Wer für
  einen Servicefall zuständig oder an ihm beteiligt ist (PRJ-108), öffnet und
  bearbeitet ihn unabhängig von seiner Rolle: Status mit Wiedervorlage,
  Angaben einschließlich "Zuständig", Beteiligte, offene Punkte, Chat und die
  Korrespondenz des Falls mit Notizen – auf den Seiten, im API und in der
  Begleit-App. Nicht freigegeben sind Umwandeln in ein Projekt, Löschen,
  andere Fälle und Preise ohne Preisrecht; die Korrespondenz von Projekten
  bleibt vertraulich. Kunde, Ansprechpartner und "Gemeldet von" sieht und
  ändert nur, wer Kunden sehen darf (AUT-023); sonst fehlen sie auf Seite und
  im Formular des Falls und bleiben im API leer. "Mein Bereich → Servicefälle"
  und die Startseite zeigen die eigenen Fälle auch ohne das Modul "Projekte".
  Ein nur lesendes Token liest nur.
- AUT-034 [SOLL · V · S9] Datenzugriff in den Listen: Beide Listen
  haben die wählbaren Spalten "Finanzen" (Preise, Einkaufspreise),
  "Personaldaten" (Personen, Stundensätze) und "Kundendaten" (lesen, ändern),
  aus den Rollen berechnet und unter der Tabelle erklärt; ein Konto, mit dem
  sich niemand anmelden kann (deaktiviert, ohne Passwort, Einladung nicht
  angenommen), zeigt "kein Zugang". Sortier- und gruppierbar, im CSV; das API
  liefert sie als data_access bei /users und /people. Die Vorschläge für
  Kunden (Suche im Projektformular) bekommt nur, wer Kunden lesen, Projekte
  ändern oder die Kunden aller Projekte sehen darf – nicht, wer nur
  zugeordnete Projekte liest.

Ausbaustufe 9: Weitere Anforderungen

- AUT-035 [SOLL · V · S9] Wer Zugriff hat: Der Reiter
  "Zugriff" eines Projekts listet in einer Tabelle "Wer Zugriff hat" alle, die
  dem Projekt zugeordnet sind – Mitglieder, Mitglieder des Gesamtprojekts,
  eingeplante Crew mit Konto ("eingeplant als Tontechnik"), Zuständige und
  Beteiligte eines Servicefalls – mit dem tatsächlich geltenden Zugriff,
  berechnet wie auf den Seiten (AUT-025, AUT-031), und dem Grund; ein Konto
  ohne Anmeldung zeigt "kein Zugang". Ändern lassen sich dort nur
  Mitgliedschaften; die übrigen Zeilen folgen der Planung. Wer über seine
  Rolle alle Projekte sieht, braucht keine Zuordnung und steht nur dort, wenn
  er zugeordnet ist; die Rolle ist dann als Grund genannt, wo sie mehr gibt.
  Die Seite fragt die Datenbank nicht je Zeile. API: GET
  /projects/{id}/access.

Ausbaustufe 9: Weitere Anforderungen

- AUT-036 [SOLL · V · S9] Standardrechte der Rollen: Die
  vorgeschlagenen Rollen (AUT-010) starten so: Freie Kraft mit Projekte und
  Packliste lesen, Zeiten schreiben, ohne Sonderrechte (auch ohne
  Verfügbarkeit des Materials, AUT-032) und mit dem Projektzugriff "nur
  zugeordnete Projekte, Überblick ohne Planung" (AUT-031); Crew zusätzlich mit
  "Korrespondenz lesen"; Lager mit Material und Packliste schreiben (nicht
  löschen) und "Korrespondenz lesen"; Projektleitung mit Projekten schreiben
  (nicht löschen) und Produkte lesen. Eine
  freie Kraft kommt über eine Mitgliedschaft nicht in die Planung eines
  Projekts (AUT-025).


### 5.2 Materialverwaltung (MAT)

Struktur

- MAT-001 [MUSS · V · S1] Material wird als Modell mit beliebig vielen
  Instanzen geführt. Das Modell beschreibt den Artikeltyp, die Instanz das
  einzelne Exemplar.
- MAT-002 [MUSS · V · S1] Eine Instanz kann eine Seriennummer haben; die Angabe
  ist optional.
- MAT-003 [MUSS · V · S1] Jede Instanz hat eine systemweit eindeutige ID
  (Inventarnummer): eine fortlaufende Zahl, mindestens vierstellig mit
  führenden Nullen (0001, 0002, ...). Bestehende IDs werden übernommen (derzeit
  0001 bis 1650), neue automatisch fortlaufend vergeben. Nach 9999 wird
  fünfstellig weitergezählt (10000); sortiert wird nach dem Zahlenwert.
- MAT-004 [MUSS · A · S1] Seriennummern sind innerhalb eines Modells
  eindeutig; bei Dubletten warnt das System. Jede
  Eingabe fragt vor dem Speichern nach (MAT-084).
- MAT-005 [MUSS · V · S1] Mengenmaterial: Für Kleinteile ohne Einzelverfolgung
  (z. B. Kabelbinder, Spanngurte, einfache Adapter) kann ein Modell statt
  einzelner Instanzen einen Bestand als Stückzahl führen.
- MAT-006 [SOLL · A · S1] Mehrere Instanzen eines Modells lassen sich in einem
  Schritt anlegen (Anzahl angeben, IDs fortlaufend, Kaufdaten gemeinsam).
  Mit einer Seriennummer je Exemplar und einer Start-ID
  (MAT-050).

Kategorien

- MAT-007 [MUSS · V · S1] Jedes Material gehört zu einer Kategorie. Material
  und Produkte nutzen dieselbe Kategoriegliederung (PRD-009).
- MAT-008 [SOLL · A · S1] Kategorien sind hierarchisch (z. B. Ton > Mikrofone >
  Funkstrecken).
- MAT-009 [MUSS · V · S1] Je Kategorie gibt es eine kategoriespezifische Angabe
  (z. B. Länge bei Kabeln, Kanalzahl bei Pulten). Die Leistung in Watt ist
  ein Feld jedes Modells (MAT-049) und keine kategoriespezifische
  Angabe.
- MAT-010 [SOLL · V · S5] Die kategoriespezifische Angabe ist erweiterbar: Je
  Kategorie lassen sich weitere Felder mit Typ (Text, Zahl mit Einheit,
  Auswahl, Ja/Nein) ergänzen. Die Angabe aus MAT-009 ist das erste dieser
  Felder; das Datenmodell sieht die Erweiterung von Beginn an vor.

Pflichtfelder laut Vorgabe

- MAT-011 [MUSS · V · S1] Je Material sind mindestens die folgenden Angaben
  gespeichert. Die Aufteilung auf Modell und Instanz in der Spalte "Ebene" ist
  bestätigt. In der Oberfläche heißt Nr. 4 "Beschreibung"
  (MAT-049) und Nr. 9 "Rechnungsdatum"; dazu kommt die Rechnungsnummer
  (MAT-050).

| Nr | Feld (laut Vorgabe)          | Ebene   | Typ / Regel                                  | Pflicht |
|----|------------------------------|---------|----------------------------------------------|---------|
| 1  | ID                           | Instanz | eindeutig, automatisch vergeben              | ja      |
| 2  | Artikelname (evtl. gekürzt)  | Modell  | Text; zusätzlich Kurzname für Listen/Etikett | ja      |
| 3  | Kategorie                    | Modell  | Auswahl aus Kategorien                       | ja      |
| 4  | Spezifikation                | Modell  | Text (technische Kurzbeschreibung)           | nein    |
| 5  | Kategoriespezifische Angabe  | Modell  | Typ je Kategorie definiert (MAT-009)         | nein    |
| 6  | Einsatz/Verbindung           | Instanz | ID der Instanz, in der verbaut (MAT-033)     | nein    |
| 7  | Seriennummer                 | Instanz | Text, optional                               | nein    |
| 8  | Notiz                        | Instanz | mehrzeiliger Text                            | nein    |
| 9  | Tag des Kaufs                | Instanz | Datum                                        | nein    |
| 10 | Kaufnotiz                    | Instanz | Text                                         | nein    |
| 11 | Kaufpreis                    | Instanz | Betrag netto in Euro                         | nein    |
| 12 | Gekauft (Händler)            | Instanz | Verweis auf Händler-Stammdaten               | nein    |
| 13 | Artikelnummer beim Händler   | Instanz | Text                                         | nein    |

- MAT-012 [MUSS · A · S1] In Listenansicht, Import und Export erscheinen alle
  13 Felder in einer Zeile je Instanz – so wie in einer Tabellenkalkulation.
- MAT-013 [SOLL · A · S5] Felder der Modell-Ebene können an einer einzelnen
  Instanz abweichend überschrieben werden (z. B. abweichende Spezifikation nach
  Umbau).
- MAT-014 [SOLL · A · S5] Beim Anlegen einer Instanz werden Händler und
  Händler-Artikelnummer aus der zuletzt angelegten Instanz desselben Modells
  vorgeschlagen.

Weitere Angaben

- MAT-015 [SOLL · A · S1] Hersteller als eigenes Feld am Modell (Stammdatum).
  Ein Textfeld mit Vorschlägen; ein neuer Hersteller
  entsteht gleich dort (MAT-048).
- MAT-016 [SOLL · A · S5] Gewicht und Maße am Modell, als Grundlage für
  Gewichts- und Volumensummen auf Packlisten. Sie stehen mit
  der Leistung im Formular "Neues Materialmodell" (MAT-049).
- MAT-017 [SOLL · A · S5] Bild sowie Dateianhänge (Handbuch, Rechnung,
  Prüfprotokoll) an Modell und Instanz.
Fotos haben ihren eigenen Kasten auf der Seite des Modells und des Exemplars (MAT-090)
  und werden neu gerendert (NFA-084); der Reiter Dateien nimmt Handbücher, Rechnungen, Prüfprotokolle und Sonstiges.
- MAT-018 [SOLL · A · S5] Lagerort je Instanz (Lager, Regal, Fach, Case) aus
  einer pflegbaren Lagerortstruktur. Ein Lagerort ist die
  Voreinstellung für neue Exemplare, anfangs "Hauptlager" (MAT-052).
- MAT-019 [SOLL · A · S1] Händler sind Stammdaten mit Name, Kontakt,
  Kundennummer beim Händler und Notiz. Mit E-Mail-Adresse,
  Telefon und Ansprechpartner, auch als Lieferanten von Zumietungen
  (PRJ-106).

Status und Lebenszyklus

- MAT-020 [MUSS · A · S1] Jede Instanz hat einen Status. Mindestens: verfügbar,
  im Einsatz, defekt, in Reparatur, ausgemustert. Dazu
  gibt es "Fehler Import": Ihn setzt nur der Import (IMP-010) bei
  einem Exemplar, dessen Angaben nicht alle übernommen werden konnten; ein
  Exemplar in diesem Status steht nicht zur Vermietung bereit, bis jemand die
  Felder ausgefüllt und einen anderen Status gewählt hat. Von Hand oder über
  die API lässt er sich nicht wählen.
- MAT-021 [MUSS · A · S1] Nur Instanzen mit einsatzfähigem Status zählen zum
  verfügbaren Bestand eines Produkts ("Fehler Import" ist nicht einsatzfähig).
- MAT-022 [MUSS · A · S1] Ausgemusterte, verkaufte oder verlorene Instanzen
  werden nicht gelöscht, sondern archiviert; ihre Historie bleibt erhalten.
- MAT-023 [SOLL · A · S5] Defektmeldung mit Beschreibung und Foto, auch mobil
  und direkt bei der Rücknahme; setzt den Status und benachrichtigt das Lager.
  Eine Defektmeldung
  ist ein Auslöser der Automationen: voreingestellt entsteht ein Servicefall,
  wahlweise ein Eintrag unter Projekte → Anfragen (MAT-057, ADM-013).
Das Foto einer Defektmeldung wird neu gerendert (JPEG, höchstens 2048 Pixel, mit
  Standort; NFA-084), auch über die API und die Packliste.
- MAT-024 [SOLL · A · S5] Sperrzeitraum je Instanz (z. B. Reparatur bis Datum),
  der die Verfügbarkeit im Zeitraum reduziert.
- MAT-025 [MUSS · A · S1] Historie je Instanz: Statuswechsel, Feldänderungen
  und – soweit das Exemplar einem Einsatz zugeordnet war (PCK-021, PCK-022) –
  Projekteinsätze, jeweils mit Zeitpunkt und Nutzer.
- MAT-044 [MUSS · V · S1] Bei jeder Statusänderung wird ein Grund abgefragt.
  Für den Status "defekt" ist er Pflicht, sonst freiwillig. Der Grund steht am
  Exemplar, solange der Status gilt, und bleibt in der Historie (MAT-025).
- MAT-045 [MUSS · V · S1] Aus dem Status "defekt" führen nur drei Wege: "in
  Reparatur", "ausgemustert" oder "verkauft". Ein defektes Exemplar lässt
  sich nicht unmittelbar wieder auf "verfügbar" setzen; das geht erst aus der
  Reparatur heraus [A].

Kennzeichnung

- MAT-026 [SOLL · A · S5] Etiketten mit ID, Kurzname und Barcode oder QR-Code
  erzeugen und drucken, einzeln und als Stapel.
  Es gibt die drei Etiketten klein, groß und Kabel im Layout der Vorlagen des Betreibers, direkt aus dem Browser
  gedruckt (MAT-056).
- MAT-027 [SOLL · V · S10] Aufruf einer Instanz durch Scannen des Codes mit
  der Gerätekamera oder einem Handscanner: Das Feld
  "Scannen oder ID eintippen" findet Exemplare, Produkte (nach GTIN mit 8, 12,
  13 oder 14 Stellen), Lagerplätze und Standorte; es steht im
  Materialverzeichnis, beim Packen und bei der Rücknahme (PCK-010, PCK-016)
  und in der Planung. Das Tippen und der USB-Scanner (er tippt in das Feld)
  gehen immer; die Kamera ist eine Zusatzfunktion und braucht HTTPS und einen
  Browser mit BarcodeDetector (Chrome, Edge, Android); kein Kamerabild
  verlässt den Browser, nur der erkannte Text geht an den Server. Eine
  Auflösung für Seite und API (GET /scan/resolve): Ein Code ohne Recht
  antwortet wie "nicht gefunden". Verstanden werden die Codes der Etiketten
  (MAT-056, MAT-065) und die Adresse /m/ID, auch mit fremden Präfixen. Der
  Header Permissions-Policy erlaubt die Kamera nur der eigenen Seite.

Bedienung

- MAT-028 [MUSS · A · S1] Suche und Filter über Name, ID, Seriennummer,
  Kategorie, Status, Händler, Lagerort und Produktzuordnung.
- MAT-029 [SOLL · A · S5] Massenbearbeitung ausgewählter Instanzen (Status,
  Lagerort, Produktzuordnung). Auch der Lagerplatz
  (MAT-080).

Prüfungen und Wartung

- MAT-030 [SOLL · A · S5] Je Kategorie oder Modell lassen sich Prüfarten mit
  Intervall hinterlegen (z. B. elektrische Prüfung alle 12 Monate).
- MAT-031 [SOLL · A · S5] Je Instanz werden Prüfungen mit Datum, Prüfer,
  Ergebnis und Protokoll-Anhang erfasst; das nächste Fälligkeitsdatum wird
  berechnet. Datum (heute) und Prüfer (der angemeldete
  Nutzer) sind vorbelegt, die Sichtprüfung ist ein Kontrollkästchen (MAT-081).
Eine nachgetragene Prüfung ändert den Status des Exemplars nur, wenn sie die jüngste
  ihrer Art ist.
- MAT-032 [SOLL · A · S5] Übersicht fälliger und überfälliger Prüfungen. Die
  Packliste weist darauf hin, wenn zu einem Produkt Exemplare mit überfälliger
  Prüfung im Bestand sind; ist ein Exemplar zugeordnet, warnt das System
  gezielt bei dessen Ausgabe. Exemplare der
  Übersicht lassen sich wählen und gemeinsam prüfen (MAT-082); oben führt "Prüfarten" zu
  deren Verwaltung (MAT-083).

Verbaute Exemplare (Feld "Einsatz/Verbindung")

- MAT-033 [MUSS · V · S1] Das Feld "Einsatz/Verbindung" gibt an, ob ein
  Exemplar in einem anderen Gerät verbaut ist (Beispiel: Rackblende in einem
  Rack). Der Wert ist stets die ID einer anderen Materialinstanz; leer bedeutet
  "nicht verbaut".
- MAT-034 [MUSS · A · S1] Eingabe über die Suche nach der Ziel-ID. Wählbar sind
  nur vorhandene, nicht ausgemusterte Instanzen. Ein Exemplar kann weder in
  sich selbst noch im Kreis verbaut sein.
- MAT-035 [MUSS · A · S1] Die Ansicht eines Exemplars zeigt, worin es verbaut
  ist, und umgekehrt alle darin verbauten Exemplare – auch über mehrere Ebenen
  (Modul in Gerät in Rack).
- MAT-046 [MUSS · V · S1] Die Verbindung lässt sich von beiden Seiten pflegen:
  am Exemplar über "Verbaut in" und am umgebenden Gerät über "Enthält" –
  dort werden Exemplare hinzugefügt und wieder herausgenommen. Beides ist
  dieselbe Angabe. Kreise sind auf beiden Wegen ausgeschlossen (MAT-034); ein
  Exemplar, das schon woanders verbaut ist, wird nicht stillschweigend
  umgehängt, sondern abgewiesen [A].
- MAT-036 [MUSS · V · S1] Es gibt zwei Arten der Verbindung, festgelegt je
  Exemplar: "fest verbaut" (z. B. Rackblende, eingebauter Empfänger) und "lose
  enthalten" (z. B. Zubehör, das im Case liegt). Fest verbaute Exemplare gehen
  immer mit dem umgebenden Gerät mit, sind nicht einzeln planbar und zählen
  nicht zum freien Bestand ihres eigenen Produkts. Lose enthaltene Exemplare
  gelten als mit verplant, sobald das umgebende Gerät verplant ist; außerhalb
  dieser Zeiträume sind sie einzeln planbar und zählen zum freien Bestand.
- MAT-037 [SOLL · A · S5] Wird das umgebende Gerät ausgegeben oder
  zurückgenommen, gelten fest verbaute und nicht herausgelöste lose Exemplare
  als mit ausgegeben bzw. zurück. Das setzt voraus, dass das Gerät als Exemplar
  zugeordnet ist; bei Einzelstücken geschieht das von selbst (PCK-021). Die
  Packliste führt den Inhalt auf Wunsch eingerückt unter dem Gerät auf.
- MAT-038 [SOLL · A · S5] Der Lagerort folgt dem umgebenden Gerät. Ist ein
  verbautes Exemplar defekt oder seine Prüfung überfällig, wird das am
  umgebenden Gerät angezeigt.
- MAT-039 [SOLL · A · S5] Ein- und Ausbau werden mit Zeitpunkt und Nutzer in
  der Historie beider Exemplare festgehalten.
- MAT-040 [SOLL · V · S10] Mengenmaterial kann mit Stückzahl als verbaut
  geführt werden, z. B. 4 Blindplatten in Rack 0500, 10 m Kabel
  und vier Stecker in einem Case; es kann selbst nicht Ziel einer Verbauung
  sein. Die verbaute Menge fehlt im freien Bestand, steht auf der
  Exemplarseite ("Verbaut in" und "enthält") mit Wer und Wann und als
  "enthält"-Zeile auf der Packliste, ohne doppelt zu zählen; Einbau und
  Ausbau, auch teilweise, stehen im Verlauf beider Exemplare. Ein leeres
  Mengenfeld beim Ausbau nimmt alles heraus. Ein Exemplar mit Einbauten lässt
  sich nicht verkaufen (MAT-087).
Die API löscht ein Exemplar mit eingebautem Mengenmaterial oder ein eingebautes Exemplar
  so wenig wie die Seite (400); verkauftes Mengenmaterial zählt nicht als mit Projekten unterwegs.
- MAT-041 [MUSS · V · S1] Die Planbarkeit lässt sich je Verbindung abweichend
  setzen: Ein fest verbautes Exemplar kann als einzeln vermietbar
  gekennzeichnet werden (z. B. ein Funkempfänger, der bei Bedarf aus dem Rack
  genommen wird). Es verhält sich dann wie ein lose enthaltenes Exemplar.
- MAT-042 [SOLL · V · S5] Herauslösen von Hand: Für ein Projekt lässt sich ein
  lose enthaltenes Exemplar aus seinem Gerät herauslösen. Es gilt dann für
  diesen Zeitraum nicht als mit verplant und zählt zum freien Bestand; die
  Packliste des Geräts weist den fehlenden Inhalt aus. Beim Packen nennt das
  System, in welchem Gerät das Exemplar liegt.
- MAT-043 [SOLL · A · S5] Entnehmen und Zurücklegen lose enthaltener Exemplare
  ist in einem Schritt möglich (auch mobil) und wird in der Historie
  festgehalten.

Weitere Anforderungen

- MAT-047 [SOLL · V · S5] Die Seite eines Exemplars ist einheitlich: "Status
  ändern" steht über "Verbaut in / Enthält", und das Einbauen in ein anderes
  Exemplar geht direkt auf der Seite – wie "Exemplar hinzufügen" auf der
  Seite des Behälters. Der Verlauf ist zunächst
  eingeklappt; das PDF der Etiketten öffnet sich in einem neuen Tab.

Ausbaustufe 7: Weitere Anforderungen

- MAT-048 [SOLL · V · S7] Im Formular eines Materialmodells sind "Hersteller"
  und "Produkt" Textfelder mit Vorschlägen beim Tippen.
  Ein Hersteller, den es noch nicht gibt, entsteht gleich dort aus dem
  eingetippten Namen.
- MAT-049 [SOLL · V · S7] Das Formular "Neues Materialmodell" und das
  Bearbeiten eines Modells fragen Gewicht, Maße bzw. Volumen und Leistung in
  Watt ab (MAT-016). Die Leistung ist ein Feld jedes Modells; eine
  kategoriespezifische Angabe "Leistung" in Watt gibt es nicht, damit derselbe
  Wert nicht an zwei Stellen steht. Die "Spezifikation" heißt überall, wo sie
  gezeigt wird, "Beschreibung".
- MAT-050 [SOLL · V · S7] Das Formular "Neue Exemplare" fragt "Gekauft bei"
  als Textfeld mit Suche über die Händler ab – ein neuer wird angelegt –, dazu
  die Rechnungsnummer und das "Rechnungsdatum". Je
  Exemplar gibt es ein Feld für die Seriennummer, so viele wie die Anzahl:
  Wird sie erhöht oder verringert, kommen Felder hinzu oder fallen weg; ohne
  JavaScript nimmt ein Textfeld eine Seriennummer je Zeile. Es gibt
  eine "Start-ID": Das erste Exemplar
  bekommt sie, die folgenden jeweils die nächste freie ID danach (MAT-003).
  Das Rechnungsdatum darf Tag und Monat offen lassen
  (MAT-088).
- MAT-051 [SOLL · V · S7] Ein Modell, das noch keinem Produkt zugeordnet ist,
  hat den Knopf "Als Produkt anlegen". Er legt ein Produkt mit dem Namen des
  Modells an – Mietprodukt oder Verkaufsware, wie es die Kategorie vorgibt –,
  ordnet ihm das Modell zu und öffnet es.
- MAT-052 [SOLL · V · S7] Ein Lagerort ist die Voreinstellung; das Formular
  "Neue Exemplare" schlägt ihn vor (MAT-018). Neue Installationen bekommen den
  Lagerort "Hauptlager" als Voreinstellung; in den Einstellungen bei den
  Lagerorten lässt sie sich wählen. Bei einem Update wird ein
  Lagerort "Hauptlager" der obersten Ebene zur Voreinstellung; gibt es gar
  keinen Lagerort, legt Rentalars "Hauptlager" an; sonst gibt es keine
  Voreinstellung, bis jemand eine wählt.


Ausbaustufe 8: Weitere Anforderungen

- MAT-053 [SOLL · V · S8] Ertrag je Exemplar: Die Seite eines
  Exemplars zeigt im Kasten "Ertrag", was es eingebracht hat und welchen
  Anteil seines Kaufpreises das ist. Eingebracht hat ein Exemplar den Anteil
  eines Stücks an den Positionen seines Produkts in den Projekten, mit denen
  es rausging – nach den Rabatten der Position und ihrer Teilgruppen,
  Pauschalpreise wie in der Kalkulation verteilt (PRJ-025); die Position
  eines Sets nach den Preisen seiner Bestandteile auf diese verteilt.
  Zählt, für welche Projekte es beim Packen gewählt wurde (PCK-021,
  "zugeordnet"); Stücke, die ohne gewähltes Exemplar rausgingen – beim
  Kabel die Regel, ein Scan ist nie Pflicht (PCK-020) –, werden gleichmäßig
  auf die Exemplare verteilt, die das Produkt damals hatte ("geschätzt").
  Es zählen nur Projekte, deren Material rausging (Unterwegs, Wieder im
  Lager, Abgeschlossen); optionale und alternative Positionen,
  Kundenmaterial und übernommene Positionen eines anderen Teilprojekts
  bringen nichts. Ein Exemplar aus einem Kaufset (MAT-054) wird mit seinem
  Set verglichen: was alle Exemplare des Sets eingebracht haben gegen den
  Preis des Sets. Den Ertrag sieht, wer die Auswertungen sehen darf
  (PRJ-115) – er rechnet über die Projekte aller Kunden –, den Anteil am
  Kaufpreis, wer zudem Einkaufspreise sehen darf (AUT-019). Gespeichert wird
  nichts; die Zahlen kommen aus der Kalkulation der Planung. Unter
  Auswertungen → Material steht dasselbe je Produkt (PRJ-115). Die API
  liefert es unter /material-items/{id}/revenue.
- MAT-054 [SOLL · V · S8] Kaufsets: Ein Exemplar kann auf das Exemplar verweisen, in dessen
  Kaufpreis es enthalten ist ("Preis enthalten in", die ID). Es hat dann
  keinen eigenen Kaufpreis; das genannte Exemplar trägt den Preis des
  ganzen Sets, verweist selbst auf kein weiteres (keine Ketten, keine
  Kreise) und muss einen Kaufpreis haben. Die Seite eines Exemplars zeigt
  "Im Preis von 0851 enthalten" und unter "Als Set gekauft" alle
  Exemplare des Sets, das mit dem Preis zuerst; die Liste der Exemplare
  zeigt in der Spalte Kaufpreis "#0851". Werden mehrere Exemplare auf
  einmal angelegt, gilt der Preis auf Wunsch für alle zusammen ("Der Preis
  gilt für alle diese Exemplare zusammen (ein Set)"): das erste bekommt
  ihn, die übrigen verweisen darauf. Der Import liest eine Preiszelle
  "#0851" so (IMP-016). Auswertungen verteilen den Preis eines Sets
  gleichmäßig auf seine Exemplare (MAT-053, PRJ-115). Die API kennt das
  Feld purchase_price_in.
- MAT-055 [SOLL · V · S8] Modell in der Ansicht eines Exemplars: Die Seite eines Exemplars nennt zu Kategorie, Hersteller,
  Produkt und Seriennummer auch das Materialmodell, mit einem Link zu
  dessen Seite.
- MAT-056 [SOLL · V · S8] Drei Etiketten, aus dem Browser druckbar: Neben den Bögen und der Rolle
  (MAT-026) gibt es drei Etiketten im Layout der P-touch-Vorlagen des Betreibers – klein 17 × 54 mm (Brother DK-11204), groß 29 × 90 mm
  (DK-11201) und das Kabeletikett auf der 29-mm-Endlosrolle (DK-22210),
  dessen Text um das Kabel sich wiederholt und dessen Länge einstellbar ist
  (60 bis 200 mm, voreingestellt 90). Klein und groß tragen Logo, Name,
  QR-Code, Telefonnummer, Webadresse, ID und den Text für Finder; das
  Kabeletikett einen kürzeren Namen, die Telefonnummer, die ID und den
  Text um das Kabel. Was darauf steht, legt Einstellungen → Etiketten fest:
  ein eigenes Logo für Etiketten (Schwarz-Weiß druckt am besten), der Name
  neben dem Logo und der Name auf dem Kabeletikett, Telefonnummer und
  Webadresse mit den Worten davor, der Text für Finder, der Text um das
  Kabel und das Ziel des QR-Codes als Webadresse mit {id} – leer die Seite
  des Exemplars in Rentalars; leere Felder nehmen die Daten der Firma
  (ADM-001). Das vorgeschlagene Etikett ist ebenfalls eine Einstellung
  (zuerst das kleine). Eine Vorschau zeigt die drei Etiketten am Beispiel
  0427. Gedruckt wird direkt aus dem Browser: eine Seite je Etikett in
  seiner genauen Größe, die den Druckdialog selbst öffnet, mit dem Hinweis
  auf Papier und Maßstab 100 %; bis 240 Etiketten auf einmal, mehr als PDF
  im Hintergrund. Die Texte werden in ihre Felder eingepasst, wie die
  Vorlage es tut. Die API liefert die drei als PDF (/labels mit format
  small, large oder cable) und kennt die Einstellungen (/label-settings);
  das Logo wird wie das der Firma im Browser hochgeladen.
- MAT-057 [SOLL · V · S8] Aus einer Defektmeldung ein Servicefall: Eine Defektmeldung (MAT-023) – auf
  der Seite des Exemplars, bei der Rücknahme oder über die API – ist ein
  Auslöser der Automationen (ADM-013) mit den Aktionen "Servicefall
  anlegen", "unter Projekte → Anfragen stellen" und "Person
  benachrichtigen". Neue und bestehende Installationen haben die Regel
  "Defektmeldung → Servicefall", aktiv, bearbeit- und abschaltbar. Der
  Servicefall ist intern – eigenes Material, ohne Kunde (PRJ-090) – oder
  bei Kundenmaterial (PRD-043) der des Eigentümers; Titel "Defekt 0042
  SM58" und als Beschreibung, was defekt ist, das Exemplar, wo und von wem
  es wann gefunden wurde und die Adresse des Exemplars, oder die Texte der
  Regel mit Platzhaltern ({id}, {kurzname}, {modell}, {produkt},
  {seriennummer}, {beschreibung}, {gefunden}, {gemeldet_von},
  {gemeldet_am}, {link}); "gemeldet von" ist, wer meldete; zuständig, wen
  die Regel nennt. Das Foto der Meldung kommt in die Dateien des Falls.
  Aus einer Meldung entsteht höchstens ein Servicefall. Die Aktion "unter
  Anfragen stellen" listet die Meldung unter Projekte → Anfragen
  (gekennzeichnet "Defektmeldung"), wo sie "Als Servicefall" wird oder von
  der Liste geht – nie als Projekt, nie "übernommen" wie eine Mail. Auf der
  Seite eines Exemplars steht bei jeder Meldung ihr Servicefall oder "Als
  Servicefall".


Ausbaustufe 9: Weitere Anforderungen

- MAT-058 [SOLL · V · S9] Ertrag je Modell: Die Seite eines Materialmodells
  zeigt den Kasten "Ertrag" wie ein Exemplar (MAT-053), zusammengezählt über
  seine Exemplare – eingenommen, davon zugeordnet und geschätzt, in wie vielen
  Projekten –, mit den Kaufpreisen zusammen und dem Anteil, darunter je
  Exemplar Ertrag, Projekte, Kaufpreis und Anteil. Ein Exemplar aus einem
  Kaufset (MAT-054) zählt mit seinem Teil des Setpreises. Rechte wie bei
  MAT-053; API GET /material-models/{id}/revenue. Die Summen bleiben sichtbar, die Tabelle je
  Exemplar ist eingeklappt ("Ertrag je Exemplar (n Exemplare)") und öffnet
  sich per Klick, auch ohne JavaScript.

Ausbaustufe 9: Weitere Anforderungen

- MAT-059 [SOLL · V · S9] Bruttopreis bei neuen Exemplaren: Beim Anlegen eines oder mehrerer Exemplare
  und beim Bearbeiten eines Exemplars wird der Einkaufspreis wahlweise netto
  oder brutto eingegeben; bei brutto wählt man den enthaltenen Steuersatz
  (vorbelegt der Standardsatz). Gespeichert wird netto, kaufmännisch auf Cent
  gerundet (wie IMP-014). Die Wahl gibt es nur mit dem Recht für
  Einkaufspreise, Rentalars merkt sie sich je Nutzer. Das API nimmt prices und
  price_tax_rate an.
- MAT-060 [SOLL · V · S9] Neuer Händler im Dialog: Wählt man
  im Feld "Gekauft bei" den Vorschlag "neuer Händler", öffnet sich ein Dialog
  mit den Stammdaten des Händlers (MAT-019: Name, Ansprechpartner, unsere
  Kundennummer dort, E-Mail, Telefon, Anschrift, Notiz), der Name vorbelegt.
  Gespeichert ist der Händler angelegt und im Feld; das Formular behält alle
  Eingaben. Ein Name, den es schon gibt, wird abgelehnt. Recht: Schreiben im
  Material oder in der Verwaltung. Ohne JavaScript legt ein neuer Name den
  Händler beim Speichern mit dem Namen an.
- MAT-061 [SOLL · V · S9] Kauf einpflegen: In der Materialverwaltung
  wird ein Kauf in einem Schritt erfasst – Händler (vorhanden oder neu,
  MAT-060), Rechnungsnummer, Rechnungsdatum, Preise netto oder brutto mit
  Steuersatz (MAT-059), wahlweise Start-ID und die Rechnung – und darunter
  eine Liste von Positionen: Modell (vorhanden oder neu mit Kategorie,
  Hersteller und Produkt), Anzahl, Kaufpreis je Stück, Seriennummern,
  Lagerort, Artikelnummer des Händlers und "als Set gekauft" (MAT-054).
  Speichern legt alle Exemplare in einem Vorgang mit fortlaufenden IDs an und
  hängt die Rechnung an jedes als Datei der Art "Rechnung"; danach lassen sich
  ihre Etiketten drucken. Recht: Schreiben im Material, Preise nur mit dem
  Recht für Einkaufspreise. API: POST /purchases. Auch
  die Eingangsrechnung pflegt Exemplare ein (DOK-024).
- MAT-062 [SOLL · V · S9] Rechnung lesen: Eine hochgeladene Rechnung – ein PDF mit Text, Scans werden
  nicht gelesen – füllt in "Kauf einpflegen" die leeren Felder vor: ohne KI
  Rechnungsnummer, Datum und einen bekannten Händler aus dem Text, mit KI
  (Einstellungen → KI, Verwendung "Rechnungen lesen", lokal oder über die
  Schnittstelle, ADM-017) auch die Positionen. Die Antwort der KI wird streng
  geprüft, Händler und Modelle mit den vorhandenen abgeglichen; ein Modell
  wird nur bei sicherem Treffer eingesetzt, sonst vorgeschlagen. Nichts wird
  von selbst angelegt: Jede Zeile aus der Rechnung muss als "Geprüft"
  bestätigt werden. Gelesen wird nur bis zu einer festen Menge Inhalt (256 KB,
  gut zehn übliche Seiten); was darüber liegt, bleibt ungelesen, und der
  Vorschlag sagt es – eine Datei kann den Server so nicht lange beschäftigen.
  Die Rechnung wartet bis zu zwei Tage auf das Speichern, dann löscht sie die
  tägliche Wartung. Die KI wird im Protokoll der KI-Aufrufe ohne Inhalt
  verzeichnet. API: POST /purchases/invoices. Sie liest
  Seriennummern, Kategorie, Produkt und Beträge (MAT-076). Dieselbe KI
  liest auch im Register der Eingangsrechnungen (DOK-023).
- MAT-063 [SOLL · V · S9] ID-Feld in jedem Reiter: Im Kopf jedes Reiters der
  Materialverwaltung steht das Feld "Exemplar-ID"; 0427, 427 oder #0427 öffnet
  das Exemplar (IMP-015), auch ein ausgemustertes. Eine unbekannte ID führt
  mit Hinweis zur Liste der Exemplare, nach der Eingabe gefiltert. Recht:
  Lesen im Material.
- MAT-064 [SOLL · V · S9] Modell und Exemplar duplizieren: "Duplizieren" an einem Modell öffnet "Neues
  Materialmodell" mit den Werten des Originals (Name mit "(Kopie)", Kategorie
  samt ihrer eigenen Felder, Hersteller, Produkt, Beschreibung, Maße, Gewicht,
  Leistung); auf Wunsch gelten die ihm zugeordneten Prüfarten auch für die
  Kopie, Exemplare und Dateien bleiben beim Original. An einem Exemplar öffnet
  es "Neue Exemplare" mit Kaufdaten, Händler und Lagerort, Status "verfügbar",
  ohne ID und Seriennummer, den Kaufpreis nur mit Recht. Gespeichert wird erst
  mit dem Formular; Recht wie beim Anlegen. Für Produkte PRD-048.
- MAT-065 [SOLL · V · S9] Lesbare Etiketten im druckbaren Bereich: Die drei Etiketten (MAT-056) werden in Liberation Sans
  gedruckt, maßgleich mit dem Arial der P-touch-Vorlagen, in deren
  Schriftgrößen und in reinem Schwarz; ein Text wird nur verkleinert, wenn er
  nicht passt, das Logo schwarz-weiß in Druckerauflösung. Alles liegt im
  druckbaren Bereich der Brother-QL-Drucker, an den Enden mit
  Sicherheitsabstand. Der QR-Code nutzt die volle druckbare Höhe (klein etwa
  14 mm, groß und Kabel etwa 25 mm), jedes Modul ganze Druckerpunkte, mit
  gültiger Ruhezone. Das Kabeletikett behält den freien Anfang der Vorlage (18
  mm, die erste Wicklung) und wiederholt den Text um das Kabel wie eingegeben,
  höchstens 14 mm auseinander; ist es zu kurz, wird der freie Anfang gekürzt,
  und die Vorschau sagt es. Die Vorschau in den Einstellungen zeigt den
  druckbaren Bereich gestrichelt. Das Design folgt den
  Originalen, der QR-Code nimmt ihren Platz ein (MAT-085).
- MAT-066 [SOLL · V · S9] Etiketten an Modell und Exemplar: Auf der Seite eines Materialmodells führt "Etiketten" zur
  Etikettenseite mit allen nicht archivierten Exemplaren des Modells. Auf der
  Seite eines Exemplars öffnet "Etikett" ein kleines Fenster mit den Etiketten
  (das vorgeschlagene zuerst), den Bögen und der Rolle; die Wahl öffnet sofort
  die Druckseite genau dieses Etiketts mit dem Druckdialog. Ohne JavaScript
  ist die Auswahl eine eigene Seite.

Ausbaustufe 9: Weitere Anforderungen

- MAT-067 [SOLL · V · S9] Audits und ihre Fälligkeit: Unter Einstellungen → Audits stehen
  das Audit-Intervall in Monaten (Vorgabe 24; 0 = aus) und eine Schnellauswahl
  für To-Dos (höchstens 12, Vorgabe "Label fehlt", "Klett fehlt",
  "Beschädigt", "Reinigen", "Teile fehlen"; ein englisches Unternehmen erhält
  sie auf Englisch). Ein Audit ist fällig ein Intervall nach dem letzten; ein
  nie geprüftes Exemplar ein Intervall nach seiner Anlage in Rentalars, damit
  eine neue Installation nicht überflutet wird. Archivierte Exemplare und
  Mengenmaterial werden nie fällig, können aber geprüft werden.
- MAT-068 [SOLL · V · S9] Audit-Modus (entschieden):
  Unter Materialverwaltung → Audit werden IDs nacheinander getippt oder
  gescannt (0427, 427, #0427 oder die Adresse des QR-Codes). Je Exemplar "In
  Ordnung" oder To-Dos per Schnellauswahl und Freitext, dann "Audit
  speichern"; Enter im Feld "In Ordnung – nächste ID" erfasst das gezeigte
  Exemplar als in Ordnung und öffnet das nächste. "In dieser Runde geprüft"
  listet die Runde. Ohne JavaScript bedienbar, auch am Handy. Recht: Schreiben
  im Material.
- MAT-069 [SOLL · V · S9] To-Dos am Exemplar: Die Seite eines Exemplars hat den
  Kasten "Audit und To-Dos" mit letztem und nächstem Audit, offenen To-Dos zum
  Abhaken ("erledigt"), "To-Do notieren" (Text oder Schnellauswahl) und den
  bisherigen Audits; im Kopf jedes Reiters stehen "Audit fällig" und "N
  To-Dos". Ein offenes To-Do gleichen Textes wird nicht doppelt notiert.
  Audits und To-Dos stehen im Verlauf. API: Audits und To-Dos je Exemplar,
  offene To-Dos, fällige Audits, Einstellungen; Exemplare mit last_audit,
  next_audit, audit_due, open_todos.
- MAT-070 [SOLL · V · S9] Offene Punkte der Materialverwaltung: Der Reiter "Offene Punkte"
  (/material/open-points/) hat die Unterreiter "Material ohne Produkt" (die
  Exemplare ohne Produkt), "Material mit To-Do" (eine Zeile je
  offenem To-Do, Tabelle nach UIX-040, mehrere auf einmal erledigen) und
  "Audit fällig" (älteste zuerst, je Zeile der Weg in den Audit-Modus); die
  Unterreiter zählen ihre Einträge. Der Reiter "Offene Punkte" zeigt auf allen Reitern der
  Materialverwaltung die Summe seiner Unterreiter, nur für Nutzer mit
  Leserecht auf das Material.
- MAT-071 [SOLL · V · S9] Eigene Felder: Unter
  Einstellungen → Eigene Felder werden Felder angelegt, die jedes Exemplar mit
  eigenem Wert hat – Text, langer Text, Zahl mit Einheit, Datum, Ja/Nein,
  Auswahlliste, Web- und E-Mail-Adresse, mit optionalem Prüfmuster (regulärer
  Ausdruck ohne verschachtelte Wiederholungen, die den Server aufhalten
  könnten) und Hilfetext. Ein Feld kann "in Listen als Spalte wählbar",
  "eindeutig" und "vertraulich" (nur mit dem Recht für Einkaufspreise
  sichtbar, auch in Suche, Verlauf und Import – auch frühere Werte, wenn ein
  Feld nachträglich vertraulich wird) sein. Änderungen müssen zu den
  gespeicherten Werten passen; ein Feld mit Werten wird nur nach Bestätigung
  samt Werten gelöscht. Anders als die kategoriespezifischen Felder (MAT-009,
  MAT-010), deren Wert für das ganze Modell gilt.
- MAT-072 [SOLL · V · S9] Feldsätze (siehe MAT-071): Ein
  Feldsatz fasst eigene Felder in einer Reihenfolge zusammen, jedes als
  Pflichtfeld oder freiwillig. Ein Materialmodell bekommt höchstens einen
  Feldsatz (im Formular des Modells, auch beim Duplizieren). Ein Feldsatz, den
  ein Modell hat, kann nicht gelöscht werden. Rechte für Felder und Feldsätze
  wie für Kategorien.
- MAT-073 [SOLL · V · S9] Werte der eigenen Felder (siehe MAT-071): "Neue
  Exemplare" und "Exemplar bearbeiten" fragen die Felder des Feldsatzes ab;
  die Seite des Exemplars zeigt sie, der Verlauf jede Änderung. Pflichtfelder
  brauchen beim Bearbeiten und beim Anlegen eines Exemplars einen Wert; beim
  Anlegen mehrerer Exemplare und bei "Kauf einpflegen" dürfen sie leer
  bleiben, fehlende Pflichtangaben werden genannt. Duplizieren übernimmt alle
  Werte außer eindeutigen. Felder "in Listen" sind wählbare, sortier- und
  filterbare Spalten der Exemplarliste und stehen im CSV; die Suche findet die
  Werte, vertrauliche ausgenommen. Der Materialimport liest Spalten mit dem
  Namen eines Feldes, der Export im Importformat (IMP-017) schreibt sie. API:
  /custom-fields, /custom-fieldsets, fieldset an Materialmodellen,
  custom_fields (Name → Wert) an Exemplaren.

Ausbaustufe 9: Weitere Anforderungen

- MAT-074 [SOLL · V · S9] Kauf einpflegen im Reiter Produkte: Der Reiter "Produkte" der
  Materialverwaltung zeigt "Kauf einpflegen" (MAT-061) wie die Reiter
  "Modelle" und "Exemplare", für alle, die Material schreiben dürfen; den
  Knopf "Import" hat er nicht – Produkte werden unter Einstellungen →
  Import und Export (oder im Reiter "Import") importiert.
- MAT-075 [SOLL · V · S9] Kauf einpflegen übersichtlicher: Das Formular
  beginnt mit einer Position; "Weitere Position" fügt je eine hinzu (ohne
  JavaScript durch Absenden, alle Eingaben und die gewählte Rechnung bleiben),
  das Lesen der Rechnung legt je Position eine Zeile an. Unter den Positionen
  stehen die Summen netto und brutto (Preis × Anzahl, ein Setpreis einmal,
  netto oder brutto eingegeben, MAT-059), beim Tippen und nach jedem Absenden
  berechnet; Positionen ohne Preis zählen mit 0 und werden genannt. Ist die
  Summe der gelesenen Rechnung bekannt, stehen sie und die Differenz daneben –
  alles nur mit dem Recht für Einkaufspreise. Nach dem Lesen zeigt Rentalars,
  was gefunden wurde (Positionen, Rechnungsnummer, Summe); der Knopf heißt
  "KI-Vorschlag eintragen", daneben steht, dass er nur das Formular füllt und
  erst "Exemplare anlegen" speichert.
- MAT-076 [SOLL · V · S9] Rechnung lesen genauer: Die KI trägt je Position die Seriennummern
  ein, die auf der Rechnung stehen. Für ein neues Modell schlägt sie Kategorie
  und Produkt aus den vorhandenen vor – nie Kundenmaterial, und die Listen
  nehmen höchstens ein Drittel der Anfrage ein, als Daten gekennzeichnet;
  übernommen wird nur ein genauer oder eindeutiger Treffer, sonst bleibt das
  Feld leer und die Zeile nennt den Vorschlag. Beträge liest Rentalars selbst,
  wie sie auf der Rechnung stehen ("1.072,50", "1,072.50", "1.072,-");
  Mehrdeutiges ("1.072") entscheiden die übrigen Beträge, der Text der
  Rechnung, die Währung und die Sprache, und jeder Betrag wird mit den
  Beträgen im Text der Rechnung abgeglichen. Dasselbe gilt beim Lesen ohne KI,
  das auch die Summen der Rechnung findet. Passt das Ende einer langen
  Rechnung nicht mehr in die Anfrage, sagt der Vorschlag es. Ein Kauf fügt nie
  Exemplare zu Kundenmaterial hinzu. API: total_net, total_gross, currency und
  je Position serial_numbers, category, product, hints.
- MAT-077 [SOLL · V · S9] Schutzklasse: Ein Materialmodell hat eine Schutzklasse (I,
  II, III oder keine), die für seine Exemplare gilt; ein Exemplar kann eine
  eigene haben. Sie steht auf den Seiten von Modell und Exemplar, als wählbare
  Spalte der Listen, beim Duplizieren, in der API (protection_class,
  protection_class_override, effective_protection_class) und als Spalte
  "Schutzklasse" im Materialimport und im Export im Importformat (IMP-017).
- MAT-078 [SOLL · V · S9] Elektrische Prüfung nach DGUV V3 (siehe MAT-077):
  Eine Prüfart (MAT-030) kann als "elektrische Prüfung (DGUV V3 / DIN VDE
  0701-0702)" markiert werden. Beim Erfassen einer solchen Prüfung fragt
  Rentalars Schutzklasse und Leitungslänge (vorbelegt aus Exemplar, Modell und
  der kategoriespezifischen Länge), Prüfgerät (vorbelegt mit dem zuletzt vom
  selben Nutzer genutzten), Sichtprüfung, Schutzleiterwiderstand R_PE,
  Isolationswiderstand R_ISO, Schutzleiterstrom I_PE, Berührungsstrom I_B und
  Funktionsprüfung ab; was bei der Schutzklasse entfällt, bleibt leer. Neben
  jedem Feld steht der Grenzwert nach DIN VDE 0701-0702 (R_PE ≤ 0,3 Ω bis 5 m,
  je weitere angefangene 7,5 m 0,1 Ω mehr, höchstens 1 Ω; R_ISO ≥ 1 / 2 / 0,25
  MΩ bei Schutzklasse I / II / III; I_PE ≤ 3,5 mA; I_B ≤ 0,5 mA). Je
  Schutzklasse sind Messungen Pflicht (Schutzklasse I: R_PE und eine
  Isolationsprüfung – R_ISO, I_PE oder I_B –, Schutzklasse II: R_ISO oder I_B,
  Schutzklasse III: nur die Sichtprüfung); eine fehlende ist ein Grund für
  "fehlgeschlagen". Werte außerhalb werden markiert, und ein Ergebnis wird mit
  Begründung vorgeschlagen – beim Tippen und beim Absenden; "bestanden" gegen
  den Vorschlag braucht eine Begründung in der Notiz. Messwerte mit Grenzwert
  und Bewertung stehen in der Prüfliste des Exemplars und in der API; zu jeder
  elektrischen Prüfung gibt es ein Prüfprotokoll als PDF. API: is_electrical
  an Prüfarten, die Messwerte an Prüfungen, POST …/inspections/check, GET
  /inspections/{id}/report. Die Sichtprüfung ist ein
  Kontrollkästchen (MAT-081), und mehrere Exemplare lassen sich in einem Zug
  prüfen (MAT-082).
- MAT-079 [SOLL · V · S9] Stammdaten im Audit: Der
  Audit-Modus (MAT-068) zeigt zum Exemplar kompakt ID, Modell, Hersteller,
  Kategorie, Seriennummer, Rechnungsdatum, Händler, Kaufpreis (nur mit dem
  Recht für Einkaufspreise), Lagerort, Status, Schutzklasse, die
  kategoriespezifischen Angaben und die eigenen Felder (vertrauliche nur mit
  diesem Recht); fehlende Angaben stehen als rotes "–", ein leeres Pflichtfeld
  als "Pflichtangabe fehlt". "Exemplar bearbeiten" führt nach dem Speichern
  zurück ins Audit desselben Exemplars.

Ausbaustufe 9: Weitere Anforderungen

- MAT-080 [SOLL · V · S9] Lagerplatz im Lagerort:
  Ein Exemplar hat ein kurzes Textfeld "Lagerplatz" (bis 12 Zeichen) innerhalb
  seines Lagerorts. Die Form "03-A-2" (zweistellige Zahl, Buchstabe, Ziffer)
  ergänzt Rentalars selbst: "3a2", "3 A 2" und "03.a.2" werden zu "03-A-2";
  anderer kurzer Text bleibt, wie er ist. Das Feld steht im Formular des
  Exemplars und beim Anlegen, auf seiner Seite, in der Liste hinter dem
  Lagerort ("Halle 1 03-A-2", sortierbar), in der Suche, im Audit (MAT-079),
  in der Massenbearbeitung (MAT-029), beim Duplizieren, in Import und Export
  (Spalte "Lagerplatz", IMP-017) und in der API (storage_spot; read-only
  effective_storage_spot). Ein verbautes Exemplar zeigt den Platz dessen,
  worin es verbaut ist. Wird ein Exemplar in der Massenbearbeitung in einen
  anderen Lagerort gelegt, entfällt sein alter Platz, wenn kein neuer genannt
  wird. Auf der Packliste steht der Platz neben dem gewählten, noch nicht
  ausgegebenen Exemplar. Gewählt wurde ein Textfeld statt einer
  Platzverwaltung mit eigenen Datensätzen: ein Feld, keine Pflege einer
  Platzliste, und die Suche und der Import brauchen nichts weiter.
- MAT-081 [SOLL · V · S9] Prüfung erfassen übersichtlicher: Die Sichtprüfung einer elektrischen
  Prüfung (MAT-078) ist ein Kontrollkästchen "Sichtprüfung bestanden"; nicht
  angehakt heißt "nicht bestanden" (dann braucht "bestanden" eine Begründung
  in der Notiz). Das Datum ist mit heute vorbelegt, der Prüfer mit dem Namen
  des angemeldeten Nutzers; beides lässt sich ändern. Die API nimmt weiter
  true oder false.
- MAT-082 [SOLL · V · S9] Massenprüfung: In der Liste
  der fälligen Prüfungen wählt man Exemplare an (alle auf der Seite mit einem
  Haken) und startet mit "Gewählte Exemplare prüfen" – nur mit dem Recht,
  Material zu schreiben. Die Seite fragt Prüfart (nur Prüfarten, die für alle
  gewählten Exemplare gelten; die der Liste ist vorgewählt), Datum (heute),
  Prüfer (der Nutzer) und bei elektrischen Prüfarten das Prüfgerät (das
  zuletzt genutzte) einmal für alle; je Exemplar eine Zeile mit Ergebnis,
  Notiz und bei elektrischen Prüfarten Sichtprüfung, Schutzklasse,
  Leitungslänge, den Messwerten und der Funktionsprüfung. Das Ergebnis "nach
  den Messwerten" nimmt, was die Grenzwerte vorschlagen (MAT-078). Alles oder
  nichts: Verletzt ein Exemplar eine Regel der einzelnen Prüfung, wird nichts
  erfasst, die Seite behält alle Eingaben und nennt das Exemplar und das Feld.
  Höchstens so viele Exemplare wie die Massenbearbeitung (MAT-029). API: POST
  /material-items/inspections/batch (JSON; je Eintrag item, result, note und
  die Messwerte; Schutzklasse und Leitungslänge aus dem Exemplar, wo sie
  fehlen; Fehler je Eintrag als items[n].feld).
- MAT-083 [SOLL · V · S9] Link zu den Prüfarten: Der Reiter "Prüfungen" der
  Materialverwaltung hat oben die Schaltfläche "Prüfarten" zur Verwaltung der
  Prüfarten (MAT-030) – für alle, die die Administration lesen dürfen.

Ausbaustufe 9: Weitere Anforderungen

- MAT-084 [SOLL · V · S9] Warnung bei vorhandener Seriennummer: Hat ein anderes Exemplar die Seriennummer schon
  – gleich welches Modell, auch ausgemustert oder verkauft, ohne Groß- und
  Kleinschreibung und Leerzeichen am Rand –, ist das eine Warnung, kein Fehler
  (MAT-004). "Neue Exemplare", "Kauf einpflegen" und das Ändern der
  Seriennummer am Exemplar nennen das vorhandene Exemplar und fragen mit
  "Trotzdem anlegen" bzw. "Trotzdem speichern"; dieselbe Nummer mehrfach in
  einer Eingabe warnt ebenso, beim selben Modell mit deutlicherem Wortlaut.
  Die API und die Vorschau des Imports nennen die Warnung (warnings).
  Eindeutig muss nichts sein.
- MAT-085 [SOLL · V · S9] Etiketten wie die Originale: Die drei Etiketten (MAT-056) folgen den
  Vorlagen der Originale: der Titel in Vorlagengröße über die ganze Breite,
  der Text für Finder in der Box der Vorlage, das Kabeletikett mit QR unten
  links und der Textspalte daneben. Der QR-Code steht an der Stelle der
  Vorlage und füllt den freien Platz dort aus; er ist nie kleiner als in der
  Vorlage und bleibt im druckbaren Bereich (MAT-065). Titel und Texte werden
  so gedruckt, wie sie in den Einstellungen stehen (Reihenfolge, Groß- und
  Kleinschreibung); eine lange ID wird kleiner gesetzt, nicht abgeschnitten.

Ausbaustufe 10: Weitere Anforderungen

- MAT-086 [SOLL · V · S10] Anlagevermögen, Abschreibung und Restbuchwert (entschieden): Ein Exemplar kann als Handelsware, GWG
  oder Anlagegut erfasst sein (DOK-024); ältere Exemplare erfasst man selbst
  in der Karte "Anlagevermögen" auf der Exemplarseite (Art, Nutzungsdauer,
  Nebenkosten, Anschaffungskosten), nur mit dem Recht Einkaufspreise.
  Anlagegüter werden linear nach Monaten abgeschrieben, der Kaufmonat zählt
  voll (ist nur das Jahr bekannt, beginnt es im Januar; MAT-088); die
  aufgelaufene Abschreibung wird gerundet, der letzte Monat gleicht aus. GWG
  sind am 31.12. des Kaufjahres voll abgeschrieben, Ware bleibt zu
  Anschaffungskosten; ein Erinnerungswert von 1 € ist eine Einstellung
  (Standard aus). Fehlen Kosten, Datum oder Nutzungsdauer, hat das Exemplar
  keinen Restbuchwert; ein Kaufdatum in der Zukunft heißt "noch nicht
  angeschafft". Buchhaltung → Anlagenspiegel zeigt je Exemplar
  Anschaffungskosten, Abschreibung und Restbuchwert zum Stichtag oder
  Bilanzjahr, mit Filtern (Art, Lagerort, Modell, Suche, auch Ausgeschiedene),
  Summen und CSV – ausdrücklich ohne DATEV-Export. Vereinfachte
  Standardregeln, keine Steuerberatung; nicht vorgesehen: degressive
  Abschreibung, Sonderabschreibung, Halbjahresregel, Sammelposten.
  Die Grenze für geringwertige Wirtschaftsgüter (GWG) wird geprüft: Über der Grenze je Stück wird
  "Anlagegut" gewählt, auch beim Einpflegen eines Kaufs und bei Mengenmaterial (Anschaffung je Stück).
- MAT-087 [SOLL · V · S10] Gebrauchtverkauf aus dem Bestand: Auf der
  Exemplarseite führt "Gebrauchtverkauf aus Bestand" zu einer Vorschau –
  Käufer (Kunde oder freier Text), Datum, Nettopreis, Steuersatz, Notiz –, die
  den Restbuchwert am Verkaufstag und den Gewinn oder Verlust zeigt (MAT-086);
  nicht erfasste Exemplare gehen mit Restbuchwert 0 € ein, die Vorschau sagt
  es. Mit der Bestätigung verlässt das Exemplar den Bestand (Status
  "verkauft", wie die Aussonderung MAT-022); es gibt einen Verlaufseintrag
  ohne Beträge. Gesperrt ist der Verkauf eines Exemplars, das für ein Projekt
  gewählt, gepackt, unterwegs oder eingebaut ist oder Einbauten enthält; ein
  Wunsch der Planung oder eine Sperrzeit fragt nur nach einer Bestätigung.
  Beim Mengenmaterial wird ein Teil verkauft. Ein Storno mit Begründung ist
  möglich, solange das Exemplar "verkauft" ist, und stellt Menge und Kosten
  wieder her. "Verkäufe aus Bestand" listet alle mit Gewinn und Verlust je
  Jahr; "Rechnung dazu erstellen" legt über die freien Belege (DOK-022) einen
  Entwurf an, für einen Käufer aus den Kunden. Verkaufen darf, wer Material
  schreiben darf und Einkaufspreise sehen darf. Die Anonymisierung eines
  Kunden entfernt seinen Namen aus den Verkäufen. Kein DATEV-Export. Der
  Entwurf ist mit dem Verkauf verknüpft und
  gegen eine zweite Rechnung geschützt, ein Verkauf mit gültiger Rechnung lässt
  sich nicht rückgängig machen (DOK-037).
- MAT-088 [SOLL · V · S10] Kaufdatum mit unbekanntem Tag oder Monat: Das Rechnungsdatum eines Exemplars (MAT-050) darf 00.00.2015
  (nur das Jahr) oder 00.05.2015 (Monat und Jahr) sein; verstanden werden auch
  2015 und 05.2015, in der API 2015-05-00 und 2015-00-00. Ein vollständiges
  Datum bleibt genau erhalten. Gezeigt wird "2015", "05.2015" oder das volle
  Datum – in Listen, Exemplar, Modell, CSV, Prüfbericht und API (dort mit dem
  lesbaren Feld purchase_date_precision). Gespeichert wird der erste Tag des
  bekannten Zeitraums mit der Genauigkeit (Tag, Monat, Jahr); danach rechnet
  die Abschreibung (MAT-086), und die Sortierung bleibt sinnvoll. Migration
  mit Rückweg; bestehende Exemplare gelten als tagesgenau.
- MAT-089 [SOLL · V · S10] Kabel-Etikett mit vollständigem QR-Code (aus dem Scan eines
  gedruckten Etiketts: dem QR-Code fehlten links die ersten Module): Der Drucker druckt am
  linken Rand des Kabel-Etiketts etwa 9 Punkte (0,8 mm) weniger, als die Etikettentabelle
  sagt. QR-Code und Logo beginnen deshalb 12 Druckpunkte (1,0 mm) weiter innen
  (SIDE_SAFETY_DOTS), die Spalte der Texte daneben ebenso; der QR-Code behält seine Größe
  (mindestens 1,8 Druckpunkte je Modul), die Telefonnummer wird dafür schmaler gesetzt
  (6,5 statt 6,9 Punkt). Das kleine und das große Etikett bleiben unverändert (MAT-070).
- MAT-090 [SOLL · V · S10] Fotos an Modell und Exemplar: Die Seite eines Modells und die eines Exemplars haben einen Kasten
  "Fotos" mit einem Upload für mehrere Fotos auf einmal (bis 20), einem Raster aus Vorschaubildern, die das ganze Foto öffnen,
  und "entfernen" mit Rückfrage. Das erste Foto steht im Kopf der Seite; ein Exemplar zeigt sein eigenes, sonst das seines
  Modells, und führt die Fotos seines Modells unter den eigenen auf. Ein Foto wird beim Hochladen nach NFA-084 neu gerendert
  und bekommt eine Vorschau von 640 Pixel (ohne Standort und Gerät). Die ältesten Fotos stehen zuerst; das erste steht im Kopf. Wer das Material nur lesen darf, sieht die Fotos und ändert sie
  nicht. Ältere Bilder, die im Reiter Dateien lagen, bleiben und stehen im Kasten (ohne Vorschau). API: Dateien der Art
  picture mit thumbnail_url; GET /material-files/{id}/thumbnail liefert die Vorschau. Der
  Kasten steht schmal rechts neben den Daten (auf einem schmalen Fenster darunter), mit kleineren
  Vorschaubildern: Er ist nicht das Wichtigste der Seite.


### 5.3 Produktverwaltung (PRD)

Grundlagen

- PRD-001 [MUSS · V · S1] Produkte sind die Einheiten, die Projekten zugewiesen
  werden. Material wird Produkten zugeordnet.
- PRD-002 [MUSS · V · S1] Einem Produkt können Materialien verschiedener
  Hersteller und Modelle zugeordnet sein (Beispiel: "XLR-Kabel 5 m" mit Kabeln
  mehrerer Hersteller).
- PRD-003 [MUSS · A · S1] Die Zuordnung erfolgt am Modell (gilt für alle
  Instanzen) und kann an einer einzelnen Instanz abweichend gesetzt werden.
- PRD-004 [MUSS · V · S1] Eine Instanz gehört zu höchstens einem Einzelprodukt.
  Dieses Produkt kann zusätzlich Bestandteil beliebig vieler Sets sein
  (PRD-022): Dasselbe Kabel ist einzeln und als Teil eines Sets mietbar. Die
  Verfügbarkeit bleibt eindeutig, weil Sets auf den Bestand ihrer Bestandteile
  zugreifen.
- PRD-005 [MUSS · A · S1] Material ohne Produktzuordnung ist zulässig, aber
  nicht planbar; eine Liste "Material ohne Produkt" macht Lücken sichtbar.
- PRD-006 [MUSS · A · S1] Der Bestand eines Produkts ergibt sich automatisch
  aus den zugeordneten einsatzfähigen Instanzen zuzüglich Mengenbestand. Er
  zählt aus mehreren Stück in
  Produkten (PRD-052).

Artikelnummer

- PRD-007 [MUSS · V · S1] Jedes Produkt hat eine interne Artikelnummer im
  Format: mindestens ein Buchstabe (Kürzel der Kategorie), Bindestrich,
  mindestens drei Ziffern. Beispiele: K-005, L-0142, D-001.
- PRD-008 [MUSS · A · S1] Die Artikelnummer ist eindeutig und wird gegen das
  Muster `^[A-Z]+-[0-9]{3,}$` geprüft. Der Buchstabenteil muss dem Kürzel einer
  vorhandenen Kategorie entsprechen.
- PRD-009 [MUSS · V · S1] Material und Produkte nutzen dieselbe
  Kategoriegliederung. Jede Hauptkategorie hat ein eindeutiges
  Buchstabenkürzel, das den Buchstabenteil der Artikelnummer bildet;
  Unterkategorien (MAT-008) übernehmen das Kürzel ihrer Hauptkategorie.
  Startbelegung: PRD-027.
- PRD-010 [SOLL · A · S1] Beim Anlegen schlägt das System die nächste freie
  Nummer der gewählten Kategorie vor; der Vorschlag ist überschreibbar.
- PRD-011 [SOLL · A · S2] Eine einmal in Projekten verwendete Artikelnummer
  kann nur mit Sonderrecht geändert werden.

Pflichtfelder laut Vorgabe

- PRD-012 [MUSS · V · S1] Je Produkt sind mindestens die folgenden Angaben
  gespeichert:

| Nr | Feld (laut Vorgabe)   | Typ / Regel                                             | Pflicht |
|----|-----------------------|---------------------------------------------------------|---------|
| 1  | Artikelnummer (intern)| siehe PRD-007                                           | ja      |
| 2  | GTIN/EAN              | 8, 12, 13 oder 14 Ziffern, Prüfziffer wird validiert    | nein    |
| 3  | Bezeichnung           | Text, erscheint auf Dokumenten                          | ja      |
| 4  | Beschreibung          | mehrzeiliger Text, optional auf Dokumenten              | nein    |
| 5  | Notiz                 | interner Text, nie auf Kundendokumenten                 | nein    |
| 6  | Einheit               | Auswahl (Stück, Meter, Tag, Stunde, km, Pauschal ...)   | ja      |
| 7  | Steuerart             | 19 % (Voreinstellung) oder steuerfrei; erweiterbar      | ja      |
| 8  | VK (Netto)            | netto; Miet- und/oder Verkaufspreis (PRD-013)           | ja      |
| 9  | Kalkulationsnotiz     | interner Text zur Preisfindung                          | nein    |

Preise

- PRD-013 [MUSS · V · S1] Ein Produkt hat einen Mietpreis, einen Verkaufspreis
  oder beides. Der Mietpreis ist ein Tagesmietpreis. Hat ein Produkt beide
  Preise, wird in der Position gewählt, ob vermietet oder verkauft wird; ein
  Verkauf mindert den Bestand dauerhaft. Ein
  Produkt hat genau einen Preis (PRD-047): ein Verkaufsprodukt den Verkaufspreis, jedes
  andere den Preis; verkauft wird ein Verkaufsprodukt.
- PRD-014 [MUSS · V · S2] Die Abrechnungsart ist je Produkt wählbar: Tagesmiete
  je Stück, Tagesmiete je Set, pauschal, nach Stunden oder nach Aufwand;
  weitere Arten sind ergänzbar. Voreinstellung für Mietprodukte ist die
  Tagesmiete je Stück.
- PRD-015 [MUSS · V · S2] Staffelfaktoren für die Mietdauer: Eine Tabelle
  ordnet der Zahl der Miettage einen Faktor auf den Tagesmietpreis zu.
  Mitgeliefert wird eine Tabelle, die mit 1 Tag = 1,0 und 2 Tage = 1,5 beginnt.
  Nutzer mit entsprechendem Recht passen sie in der Oberfläche an: Zeilen
  ergänzen, ändern, löschen.
- PRD-016 [MUSS · V · S1] Steuerarten sind Stammdaten mit Bezeichnung, Satz und
  Gültigkeitsbeginn. Startbelegung: 19 % (Voreinstellung für neue Produkte) und
  steuerfrei.
- PRD-017 [MUSS · V · S2] Ein Produkt kann zugleich einen Miet- und einen
  Verkaufspreis haben, unabhängig von seiner Kategorie (PRD-013). Entfallen:
  ein Preis je Produkt (PRD-047).
- PRD-018 [KANN · A · S10] Kundenspezifische Preise oder Preisgruppen.
- PRD-033 [MUSS · A · S2] Berechnung je Abrechnungsart: Tagesmiete = Menge ×
  Tagesmietpreis × Staffelfaktor der Miettage; pauschal = Menge × Preis; nach
  Stunden = Menge × Stunden × Preis; nach Aufwand = Preis je Einheit, wobei die
  Menge zunächst geschätzt und nach dem Einsatz durch den tatsächlichen Aufwand
  ersetzt wird.
- PRD-034 [SOLL · V · S2] Die Staffel gilt als Voreinstellung für alle Produkte
  mit Tagesmiete. Je Kategorie kann eine abweichende Staffel hinterlegt werden.
  Je Produkt ist zusätzlich eine abweichende Staffel oder "keine Staffel"
  möglich [A].
  Bei "keine Staffel" zählt jeder Tag voll (Faktor = Miettage), wie im Handbuch und bei den
  Fahrzeugen.
- PRD-035 [MUSS · V · S2] Der Staffelfaktor wird im Positionspreis
  eingerechnet. Die Position weist Miettage, Faktor und Ergebnis
  nachvollziehbar aus; eine eigene Aufpreiszeile für die Staffel gibt es nicht.
- PRD-036 [MUSS · V · S2] Welche Staffel gilt, bestimmt die genaueste Angabe:
  Produkt vor Kategorie vor Voreinstellung. Der Faktor folgt den Miettagen der
  Position und wird bei jeder Änderung der Miettage neu ermittelt. Er lässt
  sich an der Position von Hand überschreiben.
- PRD-037 [MUSS · A · S2] Änderungen an einer Staffeltabelle wirken auf neue
  Positionen. Bestehende Positionen rechnen mit dem Stand der Tabelle bei ihrer
  Anlage weiter und lassen sich je Projekt gezielt auf den neuen Stand
  umstellen.
- PRD-038 [SOLL · V · S2] Für Miettage, die in der Tabelle nicht einzeln
  aufgeführt sind, gilt eine einstellbare Regel: der Faktor der nächstkleineren
  Zeile, oberhalb der letzten Zeile zuzüglich eines festen Zuschlags je
  weiterem Tag.

Produktarten

- PRD-019 [MUSS · A · S1] Mietprodukt: kehrt nach dem Projekt in den Bestand
  zurück.
- PRD-020 [SOLL · A · S5] Verkaufs- und Verbrauchsprodukt (Kategorie V, z. B.
  Gaffa-Tape, Batterien): reduziert bei Ausgabe den Bestand dauerhaft; ein
  Mindestbestand löst eine Warnung aus.
- PRD-021 [MUSS · V · S2] Dienstleistungsprodukt ohne Bestand:
  Personalleistungen (Kategorie D, z. B. "Tontechniker, Stunde"), Fahrt und
  Transport (Kategorie F) sowie weitere Leistungen. Es dient der Preis- und
  Personalkostenberechnung im Projekt (PRJ-051). Ein
  Dienstleistungsprodukt ist nur die Leistung der Crew: genau eins je
  Funktion, geplant nur in der Personalplanung (PRD-044). Fahrt, Transport
  und andere Leistungen ohne Crew sind "Nebenkosten" (PRD-045).
- PRD-022 [MUSS · V · S1] Set: Ein Produkt besteht aus anderen Produkten mit
  Mengen (z. B. "Aktivbox-Set" = 1 Box + 1 Stativ + 1 Kaltgerätekabel + 1 XLR
  10 m). Die Bestandteile bleiben zugleich einzeln mietbar. Die Verfügbarkeit
  eines Sets ergibt sich aus seinen Bestandteilen (VFG-008).
- PRD-023 [SOLL · V · S10] Zubehörvorschläge (Ersatz- und Zubehörvorschläge): Ein Produkt hat
  Zubehör (empfohlen oder nötig, Menge je Stück, Reihenfolge, Hinweis) und
  Ersatzprodukte, gepflegt in der Produktseite; die Modellseite zeigt sie
  lesend. Beim Hinzufügen eines Produkts zeigt die Planung die noch nicht
  geplanten Zubehörteile an: ein Klick fügt sie mit sinnvoller Menge hinzu,
  ein Hinweis lässt sich im Projekt ablehnen und wieder einblenden; höchstens
  12 Vorschläge je Planung. Nennen mehrere Produkte der Planung dasselbe
  Zubehör, wird die Menge über alle Beziehungen summiert und einmal
  aufgerundet ("nötig", sobald eine es ist); ist das Zubehör zu klein geplant,
  wird es für den Rest wieder vorgeschlagen, und "Hinzufügen" nimmt dieselbe
  Summe. Ein zweites Hinzufügen wird abgelehnt ("ist schon in der Planung"),
  übernommener Ersatz wird nicht mehr vorgeschlagen. Im Angebotsschritt gibt
  es nur den Hinweis. API: products/{id}/relations und
  projects/{id}/suggestions.

Es gibt die Produktart "Fahrzeug" (KFZ oder Anhänger) für
den Fuhrpark; sie ist bei der Logistik beschrieben (LOG-002, LOG-005).

Bedienung

- PRD-024 [MUSS · A · S1] Produkte können deaktiviert werden; sie bleiben in
  alten Projekten sichtbar, sind aber nicht mehr neu zuweisbar.
- PRD-025 [MUSS · A · S1] Suche über Artikelnummer, Bezeichnung, GTIN und
  Kategorie.
- PRD-026 [MUSS · A · S1] Die Produktansicht zeigt zugeordnete Modelle und
  Instanzen, den Gesamtbestand und die aktuelle Auslastung.

Kategorien und Kürzel

- PRD-027 [MUSS · V · S1] Startbelegung der Hauptkategorien. Die beiden
  rechten Spalten sind Vorschläge [A]. Neue
  Installationen bekommen die Hauptkategorien aus ADM-011; S, A und F gehören dort
  nicht dazu. C "Fremdmaterial" für
  Kundenmaterial kommt hinzu (PRD-043), ebenso N "Nebenkosten" für
  Transport, Reisekosten und Ähnliches (PRD-045).

| Kürzel | Kategorie                              | Eigener Bestand | Typische Verwendung                |
|--------|----------------------------------------|-----------------|------------------------------------|
| L      | Licht                                  | ja              | Mietmaterial                       |
| T      | Ton                                    | ja              | Mietmaterial                       |
| R      | Rigging                                | ja              | Mietmaterial                       |
| K      | Kabel                                  | ja              | Mietmaterial                       |
| S      | Sonstiges                              | ja              | Mietmaterial                       |
| E      | Externe (zugemietete) Materialien      | nein            | Zumietung (PRJ-018)                |
| A      | Aufpreise                              | nein            | Zuschläge (PRD-031)                |
| V      | Verkauf                                | ja              | Verkaufs-/Verbrauchsware (PRD-020) |
| D      | Veranstaltungstechnik-Dienstleistungen | nein            | Personalleistungen (PRJ-051)       |
| F      | Fahrt/Transport                        | nein            | Fahrt und Transport (PRJ-053)      |

- PRD-028 [MUSS · V · S1] Die Liste ist erweiterbar: Weitere Hauptkategorien
  mit eigenem Kürzel lassen sich jederzeit anlegen (z. B. P für
  3D-Druck-Artikel und -Dienstleistungen, I für IT-Dienstleistungen).
- PRD-029 [MUSS · A · S1] Kürzel sind eindeutig und bestehen aus
  Großbuchstaben. Ein Kürzel, zu dem Artikelnummern bestehen, kann nicht mehr
  geändert werden; die Kategorie lässt sich dann nur deaktivieren, nicht
  löschen.
- PRD-030 [SOLL · A · S2] Je Kategorie lassen sich Voreinstellungen für neue
  Produkte hinterlegen: Produktart, Preisart, Einheit, Steuerart und ob ein
  eigener Bestand geführt wird. Produkte ohne eigenen Bestand (E, A, D, F)
  durchlaufen keine Verfügbarkeitsprüfung, ebenso
  Nebenkosten (PRD-045).
- PRD-031 [MUSS · V · S2] Aufpreise (Kategorie A) gibt es als festen Betrag und
  als Prozentsatz. Ein prozentualer Aufpreis bezieht sich wahlweise auf eine
  oder mehrere Positionen, eine oder mehrere Teilgruppen, das Personal oder das
  gesamte Projekt (z. B. Nacht- oder Expresszuschlag). Die Staffel für die
  Mietdauer ist kein Aufpreis (PRD-035).
- PRD-032 [SOLL · A · S5] Das System weist darauf hin, wenn Material einem
  Produkt einer anderen Hauptkategorie zugeordnet wird.
- PRD-039 [MUSS · A · S2] Ein prozentualer Aufpreis zeigt, worauf er sich
  bezieht und auf welchen Betrag er rechnet, und wird neu berechnet, sobald
  sich dieser Betrag ändert. Er rechnet auf die Beträge nach Rabatt und vor
  anderen Aufpreisen; mehrere Aufpreise auf denselben Bezug werden
  nebeneinander berechnet, nicht aufeinander.
- PRD-040 [MUSS · V · S2] Kategorie E ist die Sammelkategorie für alles, was
  von extern kommt, gleich in welches Gewerk der Artikel sonst gehörte; sie
  wird nicht weiter untergliedert. Ein allgemeines Produkt "Zumietung" genügt,
  bei dem Bezeichnung, Lieferant und Preise je Position gesetzt werden. Für
  wiederkehrende Artikel lassen sich eigene E-Produkte anlegen [A].

Weitere Anforderungen

- PRD-041 [SOLL · V · S6] Wie an einer Funktion (PER-026) lässt sich an jedem
  Produkt ein höchster Rabatt in Prozent festlegen; 0 % heißt "nicht
  rabattierbar", leer "keine Grenze". Er begrenzt jede Position des Produkts:
  ihren eigenen Rabatt, den Standardrabatt des Kunden und ihren Anteil am
  Rabatt oder Pauschalpreis der Teilgruppe. Gelten Grenzen von Produkt und
  Funktion, zählt die strengere; die Position nennt sie ("höchstens 5 %
  (Produkt)"). Personalpositionen begrenzt weiterhin nur ihre Funktion. Der
  Wert steht im Formular und auf der Seite des Produkts, als Spalte
  "Höchstrabatt" in der Liste, im Export und Import und in der API – sichtbar
  und änderbar nur mit dem Recht, Preise zu sehen (AUT-019). Die Planung
  warnt bei einem Rabatt über dem Höchstsatz (PER-044).
- PRD-042 [KANN · V · S10] Die Funktionen (PER-004) stehen bei den Produkten
  statt unter "Personal", weil sie selten geändert werden; dabei werden die
  Produkte in "Produkte" und "Services" (Dienstleistungen) getrennt.
  Funktion und Dienstleistungsprodukt gehören 1:1 zusammen und
  verweisen aufeinander (PRD-044); wo die Funktionen stehen, bleibt offen.

Weitere Anforderungen

- PRD-043 [SOLL · V · S6] Kundenmaterial: Material, das einem Kunden gehört
  und im eigenen Lager liegt – etwa Mischpult und Multicores einer Band, die
  zu ihren Auftritten mitgenommen werden –, wird wie eigenes Material
  geführt: als Produkt mit Modell, Gewicht, Maßen und Lagerort, als
  Mengenmaterial oder mit Exemplaren, IDs und Etiketten. Es steht in einer
  Hauptkategorie mit eigenem Bestand, die als "Kundenmaterial" markiert ist;
  neue und bestehende Installationen bekommen dafür C "Fremdmaterial"
  (ADM-011). Ein solches Produkt hat den Kunden als Eigentümer, ist ein
  Mietprodukt oder ein Set aus Produkten desselben Kunden und hat nie einen
  Preis, Rabatt oder eine Staffel; das Formular fragt den Eigentümer statt
  der Preise. Modell und Exemplar zeigen "Eigentum von …", ebenso die
  Etiketten; die Seite des Kunden zeigt "Material des Kunden im Lager" mit
  Bestand, Lagerort und "Material hinzufügen". Die Produktliste filtert nach
  dem Eigentümer (eigenes Material, Kundenmaterial, ein Kunde) und zeigt ihn
  als Spalte, auch in Export und Import (Kundennummer oder Name). Geplant
  wird Kundenmaterial nur in Projekten seines Eigentümers (PRJ-096); einen
  Kunden mit Material im Lager kann man nicht löschen, nur deaktivieren
  (KND-010).

Ausbaustufe 7: Weitere Anforderungen

- PRD-044 [SOLL · V · S7] Dienstleistungsprodukte gehören 1:1
  zu den Funktionen: Ein Dienstleistungsprodukt gehört zu genau einer
  Funktion, und jede Funktion hat genau ein Dienstleistungsprodukt (PER-008).
  Wird eines von beiden angelegt, entsteht das andere mit demselben Namen, wo
  es fehlt; das Formular der Funktion und das ihres Dienstleistungsprodukts
  verweisen aufeinander. Geplant werden Dienstleistungsprodukte nur in der
  Personalplanung: Die Materialplanung bietet sie nicht an – weder in der
  Produktsuche noch beim Hinzufügen einer Position, über die API, im
  MVR-Import oder aus Vorlagen –, und der Versuch, eines hinzuzufügen, wird
  mit Grund abgewiesen. Vorhandene Materialpositionen mit einem
  Dienstleistungsprodukt bleiben, wie sie sind (auch auf Dokumenten), und
  tragen einen Hinweis. Wird Personal geplant, zeigt die Personalposition ihr
  Dienstleistungsprodukt – in der Planung, in der Preisübersicht und, soweit
  sinnvoll, auf den Dokumenten – und übernimmt von ihm Preis, Steuerart,
  Abrechnungsweise und die Stundengrenze (PER-035); ein eigenes Hinzufügen des
  Produkts unter dem Material ist nicht nötig.
- PRD-045 [SOLL · V · S7] Produktart "Nebenkosten" für Transport,
  Reisekosten und andere Leistungen ohne Crew, etwa "Transport Sprinter"
  pauschal: ohne Bestand, nicht auf der Packliste, nie Vorschlag des
  MVR-Imports, in der Planung wählbar wie Material ohne Bestand und
  voreingestellt pauschal abgerechnet. Es gibt
  die Hauptkategorie N "Nebenkosten" (Produktart
  Nebenkosten, Einheit Pauschal). Neue Produkte
  in Kategorien wie "Fahrt/Transport" sind voreingestellt Nebenkosten. In den
  Beispieldaten ist der Transport Nebenkosten.
- PRD-046 [SOLL · V · S7] Das Produktformular fragt erst die Produktart, dann
  die Kategorie; Kategorien, deren Voreinstellung (PRD-030) zur gewählten Art
  passt, stehen vorn. Unter "Zugeordnetes Material" gibt es neben "Neues
  Materialmodell" auch "Vorhandenes Modell zuordnen": ein Textfeld mit
  Vorschlägen über die Modelle ohne Produkt. Das Feld findet
  auch freie Modelle über Name, Hersteller und Kategorie (mehrere Wörter),
  schlägt schon beim Betreten des Feldes vor, nennt Modelle, die schon zu
  einem Produkt gehören, und sagt "Kein Modell gefunden".

Ausbaustufe 9: Weitere Anforderungen

- PRD-047 [SOLL · V · S9] Ein Preis je Produkt:
  Ein Verkaufsprodukt hat seinen Verkaufspreis, jedes andere Produkt seinen
  Preis; was verkauft wird, ist ein Verkaufsprodukt.
  Positionen, die ein Mietprodukt verkauft haben, behalten ihren Preis
  (PRJ-015) und bleiben bearbeitbar; neu verkauft wird ein Mietprodukt nicht
  mehr, auch nicht über das API. Der Import liest "Preis" bei
  Verkaufsprodukten als Verkaufspreis und übergeht einen Verkaufspreis anderer
  Produkte mit Hinweis.
- PRD-048 [SOLL · V · S9] Produkt duplizieren (siehe MAT-064):
  "Duplizieren" auf der Seite eines Produkts öffnet das
  Formular eines neuen Produkts mit dessen Angaben und der nächsten freien
  Artikelnummer seiner Kategorie, Preise nur mit Preisrecht, interne Kosten
  nur mit dem Recht für Einkaufspreise; nicht übernommen werden GTIN, Material
  und "deaktiviert". Gespeichert wird erst mit "Produkt speichern"; ein Set
  bringt seine Bestandteile mit. API: POST /products/{id}/duplicate.
- PRD-049 [SOLL · V · S9] Artikelnummer folgt der Kategorie: Auch im Formular eines
  bestehenden Produkts – etwa nach "Als Produkt anlegen" (MAT-051) – setzt die
  Wahl einer Kategorie die nächste freie Artikelnummer ein (PRD-010); passt
  die eigene Nummer wieder zur Kategorie, kommt sie zurück. Eine Nummer, die
  in Projekten steht, ändert weiter nur, wer das Recht dazu hat.
- PRD-050 [SOLL · V · S9] Verfügbarkeit folgt dem Zeitraum: Auf der
  Seite eines Produkts zeigt die Verfügbarkeit sofort den Zeitraum, der in den
  Feldern oder im Kalender (UIX-025) gewählt ist; die Adresse folgt ihm.
  "Zeitraum prüfen" gibt es nur noch ohne JavaScript.
- PRD-051 [SOLL · V · S9] Von der Verfügbarkeit zur Auslastung: Die Verfügbarkeit auf der Seite
  eines Produkts mit Bestand oder eines Sets verlinkt "In der
  Materialauslastung zeigen" mit diesem Produkt und Zeitraum – bis zehn Tage
  in Stunden, sonst in Wochen; nur für Nutzer, die die Auslastung öffnen
  dürfen (AUT-032).

Ausbaustufe 9: Weitere Anforderungen

- PRD-052 [SOLL · V · S9] Produkt aus mehreren Stück: Ein Produkt der Art Vermietung oder
  Verkauf hat die Angabe "Stück je Produkt" (Standard 1). Ein Exemplar des
  Produkts besteht dann aus so vielen Exemplaren des Materials dahinter.
  Bestand, Verfügbarkeit, Projektzeilen und Packliste zählen in Produkten: 105
  einsatzfähige Kabel sind 10 Produkte, "3 × K-005" nimmt 30 Kabel (ändert
  PRD-006); ein defektes Exemplar nimmt nur ein Stück weg. Auf der Packliste
  werden je Produkt so viele Exemplare gewählt und ausgegeben (PCK-021,
  PCK-022), die Zeile zeigt, wie viele von den nötigen gewählt sind. Der
  Ertrag je Exemplar (MAT-053) teilt den Zeilenbetrag durch Menge mal Stück.
  Die Zahl lässt sich nicht ändern, solange Exemplare des Produkts gewählt
  oder ausgegeben sind. Die Produktseite nennt, woraus ein Exemplar besteht,
  die Modellseite, zu welchem Produkt es gehört; Import und Export der
  Produkte im Importformat kennen die Spalte "Stück je Produkt". Nicht
  vorgesehen: Behälter mit mehr als einem Stück. Wunschexemplare
  zählen je Stück (PRJ-064).


### 5.4 Kundenverwaltung (KND)

- KND-001 [MUSS · V · S1] Kunden anlegen, bearbeiten, deaktivieren.
- KND-002 [MUSS · A · S1] Kundenarten: Firma/Organisation und Privatperson.
- KND-003 [MUSS · A · S1] Stammdaten: Kundennummer (automatisch), Name bzw.
  Firma, Rechnungsanschrift, E-Mail, Telefon, Notiz.
- KND-004 [SOLL · A · S1] Mehrere Ansprechpartner je Kunde mit Funktion,
  E-Mail und Telefon; einer ist Hauptansprechpartner. Mit
  Vorname, Nachname und der Anrede in E-Mails (KND-011).
- KND-005 [SOLL · A · S5] Mehrere Adressen je Kunde (Rechnung, Lieferung).
- KND-006 [SOLL · A · S5] Kaufmännische Angaben: USt-IdNr., Zahlungsziel,
  Standardrabatt.
- KND-007 [MUSS · A · S1] Kundenansicht mit allen zugehörigen Projekten.
- KND-008 [SOLL · A · S5] Dublettenwarnung beim Anlegen (Name, E-Mail).
- KND-009 [SOLL · A · S4] Veranstaltungsorte als eigene Stammdaten mit Adresse,
  Ansprechpartner und Hinweisen (Ladeweg, Strom, Lageplan/Hallenplan).
- KND-010 [MUSS · A · S1] Kunden mit Projekten können nicht gelöscht, nur
  deaktiviert werden. Für die Löschung personenbezogener Daten gibt es eine
  Anonymisierungsfunktion. Das gilt auch für Kunden, deren
  Material im Lager liegt (PRD-043).

Ausbaustufe 9: Weitere Anforderungen

- KND-011 [SOLL · V · S9] Ansprechpartner mit Vor- und Nachname, Anrede in
  E-Mails: Ein
  Ansprechpartner hat Vorname (freiwillig) und Nachname (Pflicht); der volle
  Name wird daraus gebildet und bleibt überall der Name (Listen, Suche,
  Exporte, Dokumente, Empfänger). Ein Name, der nur als ein Wort vorliegt
  (Altdaten, Import, API), wird getrennt: das letzte Wort ist der Nachname,
  "Berg, Anna" ebenso, Namenszusätze wie von, van, de gehören zum Nachnamen;
  das Update teilt die vorhandenen Namen, ohne den angezeigten Namen zu
  ändern. Zusätzlich hat jeder Ansprechpartner eine Anrede in E-Mails:
  förmlich ("Sehr geehrte Frau Berg,", nach der Anrede Frau oder Herr; ohne
  erkennbares Geschlecht "Guten Tag Dr. Berg,"), persönlich ("Hallo Anna,")
  oder eine eigene Zeile; deutsch und englisch, mit Vorschau im Formular.
  Mails an genau einen Ansprechpartner des Projektkunden beginnen damit
  (EML-024), ebenso der Antwortentwurf der KI (ADM-017); in Dokumenttexten und
  automatischen Antworten auf Anfragen stehen die Platzhalter {greeting} und
  {anrede} (DOK-005, EML-041). Import und Export im Importformat kennen die
  Spalten "Ansprechperson Vorname" und "Ansprechperson Nachname" (IMP-013,
  IMP-017); die API nimmt weiter "name" an und kennt first_name, last_name,
  greeting_style, greeting_text und greeting.


### 5.5 Personalverwaltung (PER)

Personen

- PER-001 [MUSS · V · S3] Personen anlegen, bearbeiten, deaktivieren.
- PER-002 [MUSS · A · S3] Stammdaten: Name, E-Mail, Telefon, Art (fest
  angestellt, Aushilfe, freie Kraft), Notiz.
- PER-003 [SOLL · A · S3] Für freie Kräfte zusätzlich: Firma, Anschrift,
  Steuernummer bzw. USt-IdNr.

Funktionen und Stundensätze

- PER-004 [MUSS · V · S3] Funktionen sind Stammdaten (z. B. Projektleitung,
  Tontechnik, Lichttechnik, Videotechnik, Rigging, Stagehand, Fahrer, Lager).
  Neue Installationen bringen acht Funktionen mit (PER-037).
- PER-005 [MUSS · V · S3] Einer Person werden eine oder mehrere Funktionen
  zugeordnet. Je Person und Funktion gilt ein eigener Stundensatz.
  Er ist freiwillig; ohne eigenen Satz gilt der Richtwert der
  Funktion (PER-029).
- PER-006 [MUSS · A · S3] Eine Person kann nur in Funktionen disponiert werden,
  die ihr zugeordnet sind; mit Sonderrecht ist eine Abweichung möglich.
- PER-007 [SOLL · A · S3] Stundensätze haben ein Gültig-ab-Datum. Änderungen
  wirken nur auf neue Zuordnungen und Zeiteinträge, nicht rückwirkend.
  Das Datum ist freiwillig; ohne Datum gilt ein Satz immer
  (PER-029).
- PER-008 [MUSS · V · S3] Der Preis gegenüber dem Kunden kommt aus einem
  Dienstleistungsprodukt der Kategorie D, das der Funktion zugeordnet ist (z.
  B. Funktion Tontechnik → D-001 "Tontechniker, Stunde"). Er ist getrennt vom
  Stundensatz der Person (PER-005), der als interner Kostensatz gilt.
  Funktion und Dienstleistungsprodukt gehören 1:1 zusammen, und
  die Personalposition nimmt Preis, Steuerart, Abrechnungsweise und
  Stundengrenze aus dem Produkt (PRD-044, PER-035). Die
  Funktionen weisen darauf hin, dass ihr Satz der Stundenlohn des Personals ist
  und der Kundenpreis unter Materialverwaltung steht (PER-045).
- PER-009 [SOLL · V · S8] Zuschläge für Nacht, Sonn- und Feiertag gelten für
  Personalpositionen, die nach Stunden abgerechnet werden – für den Preis
  gegenüber dem Kunden und für die Personalkosten, wie der höhere Satz ab
  einer Stundengrenze (PER-035). Die Einstellungen nennen je Zuschlag einen
  Prozentsatz für den Preis und einen für die Kosten, dazu das Zeitfenster
  der Nacht. Voreingestellt sind die steuerfreien Sätze nach § 3b EStG: Nacht
  (20 bis 6 Uhr) 25 %, Sonntag 50 %, gesetzliche Feiertage und 31.12. ab
  14 Uhr 125 %, 24.12. ab 14 Uhr, 25. und 26.12. und 1.5. 150 %; jeder Wert
  ist änderbar. Der Nachtzuschlag kommt zu Sonn- und Feiertag hinzu; von
  Sonntag und Feiertag zählt der höhere. Die Feiertage gelten für das
  eingestellte Bundesland; Rentalars berechnet sie ohne Netz, auch die
  beweglichen. Ein Dienstleistungsprodukt lässt sich von den Zuschlägen
  ausnehmen. Gezählt wird je Zeitabschnitt: "nach Plan" im geplanten
  Zeitraum, "nach Aufwand" in den freigegebenen Zeiten; ab der Stundengrenze
  gilt der Zuschlag auf den Satz, der für diese Stunde gilt (PER-035).
  Planung, Preisübersicht, Dokumente und API weisen die Zuschläge getrennt
  aus. Tagessätze gibt es (PER-029); Überstunden deckt
  die Stundengrenze (PER-035) [A]. Die
  festen Sätze sind eine Liste von Regeln, die in jedem Land passt (PER-040);
  die Sätze oben sind der deutsche Satz, den der Knopf "Nach § 3b EStG
  einstellen" vorgibt. PER-009 bleibt die Grundlage: wofür Zuschläge gelten
  und wie sie gezählt und ausgewiesen werden. Ausdrücklich: Zuschläge gelten nur für
  Personalpositionen. Keine Stelle – Einstellungen, Ausnahme eines Produkts,
  Preisübersicht, Dokumente, API – wendet sie auf andere Positionen an oder
  bietet sie dafür an, und Einstellungen und Hilfetexte sagen es deutlich.
  Die Berechnung gilt nur für
  Personalpositionen nach Stunden; den Schalter zum Ausnehmen hat nur
  ein Dienstleistungsprodukt, bei anderen Produkten nennt die API
  time_surcharges als null und übergeht einen gesendeten Wert.
- PER-010 [MUSS · A · S3] Stundensätze sind nur mit entsprechendem Recht
  sichtbar (AUT-019). Jede Person darf ihre eigenen Sätze sehen, sofern nicht
  abgeschaltet.

Verfügbarkeit

- PER-011 [MUSS · V · S3] Die Verfügbarkeit von Personal wird gepflegt:
  Abwesenheiten (Urlaub, Krankheit, nicht verfügbar) mit Zeitraum.
- PER-012 [SOLL · A · S3] Personen mit Nutzerkonto können eigene
  Nichtverfügbarkeit selbst eintragen.
- PER-013 [MUSS · A · S3] Übersicht je Person: geplante Einsätze,
  Abwesenheiten, erfasste Zeiten.

Qualifikationen

- PER-014 [SOLL · A · S5] Qualifikationen und Nachweise je Person mit
  Ablaufdatum und Anhang (z. B. Führerscheinklassen, Hubarbeitsbühne,
  Rigging-Nachweis, Ersthelfer).
- PER-020 [SOLL · V · S5] Jede Person hat einen eigenen Zeitstrahl über
  wählbare Wochen mit Einsätzen, Abwesenheiten und dem Ablauf ihrer
  Qualifikationen, damit ihre Verfügbarkeit in Zeiträumen direkt zu sehen ist.
  Er zeigt die geltende Verfügbarkeit wie der Personalplan
  (PER-027) – eigene Einträge, belegte Zeiten der verknüpften Kalender und
  Abwesenheiten.
  verfügbar" eingetragen hatte, wirkte dort frei.
- PER-015 [KANN · A · S10] Funktionen können Qualifikationen voraussetzen; das
  System warnt bei fehlendem oder abgelaufenem Nachweis.

Kommunikation

- PER-016 [SOLL · A · S4] Anfrage-Ablauf für Einsätze: angefragt, zugesagt,
  abgesagt. Personen mit Nutzerkonto antworten in der Anwendung, auch per Antwort-Mail, ohne Anmeldung und ohne dass der Server aus dem
  Internet erreichbar ist (PER-032). Die Anfrage merkt sich
  die angefragten Zeiten: Nach einer Antwort wird erst wieder angefragt, wenn
  sich die Zeiten geändert haben (PER-033), und neue Zeiten fragen von selbst
  neu an (PER-034). Die Mails zur Anfrage nennen vor der
  Zeile "Projekt" eine Zeile "Firma:" mit dem Firmennamen aus den Stammdaten
  (ebenso andere Mails mit diesem Block); mit eingeschalteten Preisangeboten
  steht ein Hinweis darauf in der Anfrage (PER-038).
- PER-017 [SOLL · A · S5] Persönlicher Kalender-Feed (iCal) der eigenen
  Einsätze. Ausgeführt in PER-023.

Pauschalen

- PER-018 [MUSS · V · S3] Für einen Einsatz kann statt der Abrechnung nach
  Stunden eine Pauschale vereinbart werden. Sie gilt wahlweise für die internen
  Kosten (je Person und Einsatz), für den Preis gegenüber dem Kunden (über ein
  Dienstleistungsprodukt mit der Abrechnungsart "pauschal") oder für beides;
  beide Seiten sind unabhängig voneinander.

Sichtbarkeit von Kontaktdaten

- PER-019 [MUSS · V · S3] Jede Person legt in ihrem Profil fest, welche ihrer
  Kontaktdaten (z. B. Telefon, E-Mail) Kollegen im selben Einsatz sehen dürfen.
  Der Name ist immer sichtbar; für alles Weitere gilt als Voreinstellung "nicht
  sichtbar" [A]. Projektleitung und Personaldisposition sehen die Kontaktdaten
  unabhängig davon.

Weitere Anforderungen

- PER-021 [SOLL · V · S5] Jede Person führt einen eigenen
  Verfügbarkeitskalender: Zeiträume werden grün (verfügbar), gelb
  (eingeschränkt, mit Hinweis) oder rot (nicht verfügbar) markiert. Die
  Personaldisposition sieht die Farben bei "Wer ist frei" und im
  Personalplan; wer in einem roten Zeitraum eingeplant wird, löst eine
  Warnung aus.
- PER-022 [SOLL · V · S5] Eine Person kann einen Kalender als ICS-Link
  hinterlegen, etwa den privaten Link eines Google- oder Outlook-Kalenders.
  Rentalars liest ihn regelmäßig; belegte Termine gelten als nicht
  verfügbar. Titel und Inhalte der Termine werden nicht übernommen [A].
- PER-023 [SOLL · V · S5] Die eigenen Einsätze gibt es als Kalender: als
  .ics-Datei, als abonnierbaren HTTPS-Link mit geheimem Schlüssel und – für
  Server, die aus dem Internet nicht erreichbar sind – durch Schreiben in
  einen CalDAV-Kalender (etwa Nextcloud, iCloud, mailbox.org). Ein Eintrag
  zeigt nur, was die Person ohnehin sieht (AUT-023). Google Kalender liest
  den Abo-Link; das Schreiben per CalDAV verlangt dort OAuth und ist nicht
  vorgesehen [A].
- PER-024 [SOLL · V · S5] Zu jeder Person wird ihre Position im Unternehmen
  geführt, etwa "Leitung Licht"; sie steht auch in der E-Mail-Signatur
  (EML-034).
- PER-025 [MUSS · V · S5] Eine Person wird erst zur Planung angeboten, wenn
  ihr eine Funktion zugeordnet ist – in Auswahllisten, bei "Wer ist frei" und
  im Personalplan. Zur gewählten Funktion zeigt die Auswahl nur, wer sie
  hat; wer außerhalb der Funktionen planen darf (PER-006), sieht die übrigen
  gekennzeichnet dahinter. Reine Büro-Konten erscheinen dort nicht. Ohne
  den Haken bei "Nur Personen mit
  Einsätzen oder Abwesenheiten" zeigt der Personalplan alle aktiven Personen (VFG-023).
- PER-026 [SOLL · V · S5] Je Funktion lässt sich ein höchster Rabatt
  festlegen; 0 % heißt "nicht rabattierbar", leer "keine Grenze". Er begrenzt
  den Rabatt einer Personalposition, ihren Anteil am Rabatt der Teilgruppe und
  den Standardrabatt des Kunden auf die Dienstleistung der Funktion. Die
  Planung warnt bei einem Rabatt über dem Höchstsatz
  (PER-044).

Weitere Anforderungen

- PER-027 [SOLL · V · S6] Zu jedem Zeitpunkt gilt für eine Person genau eine
  Verfügbarkeit. Eigene Einträge überschneiden sich nie: Ein neuer Eintrag
  ersetzt, was für diese Zeit eingetragen war. Die Termine aus dem
  verknüpften Kalender (PER-022) bleiben eine eigene Ebene, die bei jedem
  Lesen ersetzt wird. Wo sich beide treffen, gilt die neuere Angabe – beim
  eigenen Eintrag der Zeitpunkt des Eintragens, beim Termin sein
  Änderungsdatum im Kalender; nennt der Kalender keins, gilt die strengere.
  Überlappende und aneinandergrenzende Termine erscheinen als ein Block.
- PER-028 [SOLL · V · S6] Jede Person trägt ihre Verfügbarkeit selbst ein,
  auch als Serie: täglich, wöchentlich an gewählten
  Wochentagen, alle n Wochen oder monatlich, bis zu einem Datum oder n-mal,
  höchstens ein Jahr voraus. Eine Serie lässt sich ab einem Tag ändern und
  ganz oder ab einem Tag entfernen; die Personaldisposition kann dasselbe
  für eine Person.

Weitere Anforderungen

- PER-029 [SOLL · V · S6] Einer Person lässt sich eine Funktion ohne Satz
  zuordnen: Stundensatz, Tagessatz und "gültig ab" sind freiwillig. Ohne
  eigenen Satz gilt der Richtwert der Funktion, ohne Datum gilt eine Zeile
  immer; je Person und Funktion gibt es höchstens eine Zeile ohne Datum. Neben
  dem Stundensatz gibt es je Person und Funktion einen Tagessatz und je
  Funktion einen Richtwert für die internen Kosten je Tag. Eine
  Personalposition lässt sich "je Tag" abrechnen (PRJ-061): Preis = Tage ×
  Preis je Tag; Kosten = Tage × Tagessatz der Person, der beim Zuweisen wie
  der Stundensatz an der Position festgeschrieben wird (PRJ-021), sonst ×
  Richtwert je Tag, ohne beides Stunden × Stundensatz. Die Tage sind die
  Kalendertage, die der Zeitraum berührt (Montag 08:00 bis Dienstag
  20:00 = 2 Tage), und an der Position überschreibbar; Angebot,
  Auftragsbestätigung und Rechnung nennen sie mit der Einheit "Tag". Ein
  Dienstleistungsprodukt mit Tagesmiete macht neue Personalpositionen zu "je
  Tag". Tagessätze sieht nur, wer Stundensätze sehen darf (AUT-019); der
  Personalimport liest "Tontechnik: 35,00/280,00" als Stunden- und Tagessatz.
  Eine Funktion ohne Sätze ordnet zu, wer das Personal bearbeiten darf;
  Sätze eintragen und eine Funktion mit eigenen Sätzen entfernen nur, wer
  Stundensätze sehen darf.
- PER-030 [SOLL · V · S6] Der Verfügbarkeitskalender (PER-021) zeigt wahlweise
  den Monat oder eine Woche, unter "Mein Bereich" wie im Reiter
  "Verfügbarkeit" einer Person; die Wahl bleibt für die Sitzung erhalten. Die
  Woche hat eine Spalte je Tag mit Stunden wie der Wochenkalender der Planung:
  die Verfügbarkeit als Farbe über ihren Stunden, die belegten Zeiten der
  verknüpften Kalender schraffiert, daneben die Einsätze; ein Einsatz in einer
  roten Zeit ist rot umrandet. Die Köpfe der Tage tragen die Farbe aus dem
  Monat; eingetragen wird wie im Monat, auch durch Tippen auf den ersten und
  den letzten Tag. Auf dem Smartphone lässt sich die Woche verschieben.
- PER-031 [SOLL · V · S6] Eine Person kann mehrere Kalender als ICS-Link
  verknüpfen (PER-022), bis zu zehn, jeden mit einem Namen wie "Band" und
  eigenem Stand ("zuletzt gelesen" oder "Problem"). Ihre belegten Zeiten sind
  zusammen eine Ebene "belegt im verknüpften Kalender" (PER-027): Überlappende
  und aneinandergrenzende Termine erscheinen als ein Block, auch aus
  verschiedenen Kalendern. Ein Kalender, der sich nicht lesen lässt, behält
  seine zuletzt gelesenen Zeiten und hält die anderen nicht auf; die Person
  erfährt es einmal, mit seinem Namen. Die Personaldisposition kann Kalender
  für eine Person verknüpfen, lesen und entfernen und sieht dabei nur Namen
  und Server, nie den Link.

Weitere Anforderungen

- PER-032 [SOLL · V · S6] Eine Einsatzanfrage (PER-016) lässt sich per
  Antwort-Mail beantworten, ohne dass der Server aus dem Internet erreichbar
  sein muss: Die Anfrage-Mail enthält die Knöpfe "Zusagen" und "Absagen", die
  eine fertige Mail an ein Postfach öffnen, das Rentalars abruft. Ihr Betreff
  trägt einen nicht erratbaren Code je Anfrage; hinter "Anmerkung:" lässt sich
  etwas für die Planung schreiben. Beim Abruf trägt Rentalars die Antwort samt
  Anmerkung ein wie eine Antwort im Browser und bestätigt sie der Person per
  Mail. Ist die Anfrage schon beantwortet, vorbei, zurückgenommen oder durch
  eine neuere ersetzt, ändert sich nichts, und die Person erfährt es per Mail.
  Erkannt werden Antworten in jedem abgerufenen Postfach; danach werden sie
  wie zugeordnete Mails behandelt (EML-041). Das Mail-Protokoll nennt sie
  "Antwort auf Einsatzanfrage" mit Zusage oder Absage, der Verlauf des
  Projekts "kam per Antwort-Mail". Unter Einstellungen → E-Mail ist wählbar,
  ob über den Link im Browser, per Antwort-Mail oder auf beiden Wegen
  (Voreinstellung) geantwortet wird; die Seite nennt das Postfach für die
  Antworten. Ohne ein aktives, abgerufenes Postfach der Korrespondenz mit
  Adresse enthält die Anfrage nur den Link. Freie Antworten wie "Ja" oder
  "Nein" wertet Rentalars nicht aus. Eine Anfrage nach
  geänderten Zeiten nennt die neuen und die bisherigen (PER-034); eine Antwort auf
  die ältere Anfrage-Mail ändert dann nichts. Die Wahl
  des Antwortwegs steht unter Einstellungen → Firmendaten und Grundeinstellungen
  (ADM-015). Eine Antwort zählt nur von
  der Adresse, an die die Anfrage ging (PER-046).

Ausbaustufe 7: Weitere Anforderungen

- PER-033 [SOLL · V · S7] Eine Antwort auf eine Einsatzanfrage erscheint in
  der offenen Planung von selbst, spätestens nach 20 Sekunden (UIX-020) – per
  Antwort-Mail, sobald Rentalars das Postfach abgerufen hat –, auch wenn die
  planende Person in der Zwischenzeit selbst etwas gespeichert hat.
  Die Anfrage merkt sich die angefragten Zeiten. "Erneut anfragen" gibt es
  nach einer Zusage oder Absage erst, wenn sich Beginn oder Ende seither
  geändert haben; die Position nennt dann etwa "Zeiten geändert seit der
  Zusage – angefragt war: Mi 10.03. 08:00 – Mi 10.03. 18:00". Für dieselben
  Zeiten fragt Rentalars nicht noch einmal an, auch nicht über die API; eine
  Anfrage, die noch auf Antwort wartet, lässt sich erneut senden.
- PER-034 [SOLL · V · S7] Ändern sich Beginn oder Ende einer angefragten oder
  zugesagten Personalposition – im Dialog, mit
  "Personal dieser Phase mitverschieben" (PRJ-080) oder über die API –, fragt
  Rentalars die Person von selbst neu an, damit sie den neuen Zeiten zustimmen
  kann. Die Anfrage nennt "Neue Zeiten: … (vorher: …)", die Position steht bis
  zur Antwort wieder auf "angefragt", und eine Antwort auf die ältere
  Anfrage-Mail ändert nichts mehr (PER-032). Stunden, Funktion, Treffpunkt,
  Notiz und eine Phase ohne neue Zeiten lösen keine Anfrage aus. Abgesagte
  Positionen, stornierte Projekte und deaktivierte Personen fragt Rentalars
  nicht von selbst an. Abschalten lässt sich das unter Einstellungen →
  Firmendaten und Grundeinstellungen mit "Bei geänderten Zeiten neu anfragen"
  (voreingestellt an).

Ausbaustufe 7: Weitere Anforderungen

- PER-035 [SOLL · V · S7] Ab einer Grenze von Stunden je Tag gilt ein höherer
  Satz, für Preis und Kosten – etwa ab der 11. Stunde eines Tages ein höherer
  Preis je Stunde. Das Dienstleistungsprodukt hat dafür die Grenze (Stunden je
  Tag) und den Preis je Stunde ab der Grenze; die Person hat je Funktion einen
  Kostensatz ab der Grenze, die Funktion einen Richtwert dafür. Gezählt wird
  je Kalendertag: bei "nach Plan" die geplanten Stunden jedes Kalendertags,
  bei "nach Aufwand" die freigegebenen bzw. erfassten Zeiten jedes Tages
  (ZEI-021). Das gilt nur für die Abrechnung nach Stunden, nicht für pauschal
  oder je Tag (PER-029). Preisübersicht, Dokumente und API weisen die Stunden
  getrennt aus: normale Stunden und Stunden ab der Grenze.
- PER-036 [SOLL · V · S7] Neue Personalpositionen werden voreingestellt "nach
  Aufwand" abgerechnet (PRJ-061), wo ihr Dienstleistungsprodukt nach Stunden
  rechnet; ein pauschales bleibt pauschal, eines mit Tagesmiete "je Tag"
  (PER-029). Vorhandene Positionen behalten ihre Abrechnungsweise.
- PER-037 [SOLL · V · S7] Neue Installationen bringen die Funktionen
  Techniker, Lichttechniker, Tontechniker, Medientechniker, Stagehand, Lager,
  Projektplanung und Sonstiges mit, jede mit ihrem Dienstleistungsprodukt
  (Kategorie D, Einheit Stunde, ohne Preis; PRD-044). Eine bestehende
  Installation bekommt sie mit dem Update nur, wenn sie noch gar keine
  Funktion hat. In der Liste der Funktionen führt das Dienstleistungsprodukt
  mit einem Klick zu seiner Seite.
- PER-038 [SOLL · V · S10] Preisangebote freier Kräfte (optional und im Standard aus;
  Preisangebote freier Kräfte sind ein optionaler Teil der Einsatzplanung): Ist die
  Funktion unter Einstellungen → Preisangebote eingeschaltet, kann eine freie
  Kraft (auf Wunsch auch eine Aushilfe) auf eine Einsatzanfrage (PER-016)
  statt mit Zusage oder Absage mit einem Preis antworten: Betrag je Stunde, je
  Tag (bei Positionen nach Tag) oder gesamt, Meldung, "gültig bis". Die Firma
  legt Grenzen in Prozent des hinterlegten Satzes und die höchste Zahl der
  Runden fest (Standard 4). Sie sieht das Angebot in der Planung neben dem
  hinterlegten Satz und unter Personal → Preisangebote, nimmt es an, lehnt es
  ab oder kontert; die freie Kraft antwortet auf Gegenangebote und kann
  zurückziehen. Ein neues Anfragen beginnt eine neue Verhandlung. Die Annahme
  beantwortet die Anfrage mit "zugesagt" und setzt den Kostensatz genau dieser
  Personalposition (Marker in der Planung, Verlaufseintrag, alte Werte bleiben
  am Angebot); der Preis für den Kunden ändert sich nicht. Das Angebot endet,
  wenn der Satz von Hand geändert oder die Person getauscht wird; ein
  Gesamtbetrag auch bei neuen Zeiten. Angebote sind Personalkosten: Sie sehen
  nur die freie Kraft selbst und wer Stundensätze und Personalkosten sehen
  darf; Benachrichtigungen folgen den Einstellungen der Nutzer, höchstens 30
  Angebotsschritte je Nutzer und Stunde, nur EUR. Ein eigenes Angebot statt
  eines vorgegebenen Satzes gilt als ein Anzeichen selbstständiger Tätigkeit;
  eine rechtliche Bewertung ist das nicht. API: crew-lines/{id}/offers
  (annehmen, ablehnen, kontern, zurückziehen), price-offers, people/me/offers,
  settings/price-offers.

Ausbaustufe 8: Weitere Anforderungen

- PER-039 [SOLL · V · S8] Unter Mein Bereich → Verfügbarkeit lassen sich in
  der Wochenansicht (PER-030) Zeitbereiche markieren, um für sie die
  Verfügbarkeit einzutragen: mit der Maus einen Bereich ziehen – wo die
  Ansicht es erlaubt, auch über mehrere Tage –, dann "verfügbar",
  "eingeschränkt verfügbar" oder "nicht verfügbar" wählen, mit Notiz
  (PER-021, PER-027). Auf dem Smartphone geht es durch Tippen auf Beginn und
  Ende; ohne Maus gibt es einen Weg mit der Tastatur oder einem Formular.
- PER-040 [SOLL · V · S8] Zuschläge für jedes Land: Die Zuschläge (PER-009)
  sind eine Liste von Regeln. Eine Regel hat eine Art – Tageszeit
  (ein Zeitfenster), Wochentag oder Wochentage, Feiertag, ein bestimmter Tag
  im Jahr ab einer Uhrzeit (etwa 24.12. ab 14 Uhr) – und je einen
  Prozentsatz für den Preis und für die Kosten. Von den Regeln, die einen
  Tag betreffen, zählt nur die höchste; die Regeln der Tageszeit kommen
  hinzu – die Logik von § 3b EStG, allgemein gefasst. Feiertage sind die der
  deutschen Bundesländer, von Rentalars selbst ohne Netz
  berechnet, und eigene: ein festes Datum jedes Jahr, ein einzelnes Datum
  oder Tage relativ zum Ostersonntag. Der Knopf "Nach § 3b EStG einstellen"
  ersetzt die Regeln durch den deutschen Satz, samt der
  Nachtarbeit, die vor Mitternacht begonnen hat.
  Einstellungen → Zuschläge zeigt die Regeln als bearbeitbare Liste
  (hinzufügen, entfernen, Reihenfolge) und die Feiertage (Bundesland und
  eigene). Im Änderungsprotokoll sieht die Prozentsätze für den Preis nur,
  wer Preise sehen darf, die für die Kosten nur, wer Personalkosten sehen
  darf (AUT-019). Die API kennt Regeln und eigene Feiertage.
  Einstellungen → Zuschläge sagt, dass
  die Regeln nur für Personalpositionen gelten (PER-009).

Ausbaustufe 9: Weitere Anforderungen

- PER-041 [SOLL · V · S9] Fest einplanen ohne Anfrage: Eine Person lässt sich "fest einplanen" – beim
  Einplanen, im Dialog einer Position, in der Zeile und für mehrere Positionen
  (PRJ-117), auch über das API. Das zählt wie eine Zusage (PER-016) in "Meine
  Einsätze", Kalendern und Plänen. Eine fest eingeplante Position wird nicht
  angefragt und bei neuen Zeiten nicht erneut (PER-034): Die Person wird
  benachrichtigt (PRJ-118). Im Dialog lässt sich "fest eingeplant"
  zurücknehmen; die Position ist dann nicht angefragt.

Ausbaustufe 9: Weitere Anforderungen

- PER-042 [SOLL · V · S9] Zusage trägt "verfügbar" ein: Sagt eine Person eine
  Anfrage zu – im Browser, per Antwort-Mail, über API oder App, oder trägt die
  Planung ihre Zusage ein – und zeigt ihr eigener Verfügbarkeitskalender
  (PER-021) in dieser Zeit "nicht verfügbar", wird für genau die Zeit der
  Position "verfügbar" eingetragen ("Zugesagt: Nummer Projekt – Funktion");
  überlappende Einträge werden gekürzt oder geteilt, auch in Serien. Die
  Bestätigung nennt es. Verknüpfte Kalender (PER-022) bleiben unverändert;
  festes Einplanen (PER-041) trägt nichts ein. Die
  Antwort-Mail, die die Zusage trägt, wird im Postfach in den Ordner für
  zugeordnete Mails gelegt (PER-043).

Ausbaustufe 9: Weitere Anforderungen

- PER-043 [SOLL · V · S9] Zusagen mit Kennung auch im Postfach abgelegt: Die Antwort auf
  eine Einsatzanfrage (PER-032) wird im Postfach wie jede zugeordnete Mail
  abgelegt: bei "verschieben" und "löschen" wie eingestellt, bei "nur als
  gelesen markieren" (EML-006) aber in den Ordner für zugeordnete Mails
  verschoben – im Posteingang bleiben die Mails, die jemand lesen muss. Gibt
  es keinen anderen Ordner als den Posteingang, bleibt sie dort, gelesen
  markiert; bei "unverändert lassen" ändert sich nichts. Alle anderen
  zugeordneten Mails folgen unverändert der Einstellung.

Ausbaustufe 9: Weitere Anforderungen

- PER-044 [SOLL · V · S9] Warnung bei einem Rabatt über dem Höchstsatz: Übersteigt ein eingegebener
  Rabatt den Höchstsatz der Position (PER-026, PRD-041), warnt die Planung mit
  dem eingegebenen und dem angerechneten Satz; abgerechnet wird der Höchstsatz.
  Das gilt für Positionen, Gruppen, Rabatt als Betrag und
  Pauschalpreis, Personal und Fahrzeuge, einzeln und bei Sammeländerungen; im
  Dialog erscheint der Hinweis schon beim Tippen. Die API antwortet mit
  Erfolg und nennt die Warnung in warnings. Der Gesamtrabatt (PRJ-123) hat
  keinen Höchstsatz.
- PER-045 [SOLL · V · S9] Hinweise bei den Funktionen: Bei den
  Richtwerten einer Funktion steht, dass es der Stundenlohn bzw. die
  Tageskosten des eingeplanten Personals sind (interne Kosten, PER-008), nicht
  der Preis für den Kunden. Liste und Formular der Funktionen nennen, dass der
  Preis gegenüber dem Kunden unter Materialverwaltung → Produkte steht
  (Dienstleistungsprodukt der Funktion), mit Link für den, der Produkte lesen
  darf; ebenso die Seite der Person, wo die Sätze eingetragen werden.
- PER-046 [SOLL · V · S10] Antwort auf eine Einsatzanfrage nur von der angeschriebenen Adresse:
  Der Code im Betreff allein ist kein Nachweis. Die Anfrage merkt sich die Adresse, an die sie ging, und eine Antwort per Mail
  zählt nur, wenn sie von genau dieser Adresse kommt (Groß- und Kleinschreibung gleich). Eine Antwort von einer anderen
  Adresse ändert nichts; das Mail-Protokoll führt sie mit dem Grund, und die Person bekommt an ihre gespeicherte Adresse eine
  Mail, dass eine Antwort von einer anderen Adresse kam (höchstens einmal pro Stunde, Anfrage und Grund; genannt wird nur
  eine einfache Adresse). Internationale Domains gelten in Unicode- und in ASCII-Schreibweise als gleich; eine Mail mit mehr
  als einer From-Zeile wird nicht übernommen. Schreibt der empfangende Mailserver ein Prüfergebnis
  (Authentication-Results) und meldet er "dmarc=fail", wird die Antwort ebenfalls nicht übernommen. Für ältere Anfragen
  gilt die heutige Adresse der Person. Es gibt keine weiteren Codes in Mails: Einladungen und Passwort-Links
  führen über einen Link im Browser, nicht über eine Antwort-Mail.
  Der Vergleich der Domains kennt keine Zeichen in Vollbreite oder anderer Schreibweise, die nach
  Normalisierung zu einer fremden Domain würden ("ｇｍａｉｌ.com" ist nicht "gmail.com"); verglichen wird die
  Punycode-Form der Domain.
  Verglichen wird die Adresse der strukturierten From-Zeile, nicht das Ergebnis eines
  Parsers über den Text; mit dem eingetragenen Mailserver zählt nur eine bestätigte Antwort (EML-057).


### 5.6 Projektverwaltung (PRJ)

Stammdaten

- PRJ-001 [MUSS · V · S1] Projekte anlegen, bearbeiten, abschließen.
- PRJ-002 [MUSS · V · S1] Jedes Projekt ist einem Kunden zugeordnet.
- PRJ-003 [MUSS · A · S1] Stammdaten: Projektnummer (automatisch;
  Voreinstellung Jahr und laufende Nummer, z. B. 2026-0042, ADM-014;
  Nummernkreis konfigurierbar), Name, Kunde, Ansprechpartner,
  Veranstaltungsort, Projektleitung, Status, Notizen.
- PRJ-004 [MUSS · A · S1] Projektzeitraum mit Beginn und Ende (Datum und
  Uhrzeit).
- PRJ-005 [MUSS · A · S2] Unterscheidung zweier Angaben: Dispositionszeitraum
  (Material verlässt das Lager, bis es zurück ist) und Miettage (berechnete
  Tage für Tagesmiete und Staffel, PRD-015). Die Miettage werden aus dem
  Veranstaltungszeitraum vorgeschlagen und sind je Projekt, Teilprojekt,
  Teilgruppe und Position überschreibbar; es gilt jeweils die genaueste
  Angabe. Rentalars warnt, wenn die Veranstaltung nach
  "Material zurück bis" endet (PRJ-127).
  Maßgeblich sind die Stunden der Uhr in Ortszeit, nicht die vergangene Zeit. Samstag 10 Uhr bis
  Sonntag 10 Uhr ist auch in der Nacht der Zeitumstellung ein Miettag; Vorschau und gespeicherter Wert stimmen
  überein.
- PRJ-062 [MUSS · V · S2] Hat eine Position einen eigenen Zeitraum, der vom
  Projektzeitraum abweicht (PRJ-011), ergeben sich ihre Miettage aus diesem
  Zeitraum: jede angefangenen 24 Stunden zählen als ein Tag. Wer den Zeitraum
  einer Position ändert, muss die Miettage nicht nachtragen. Von Hand an der
  Position eingetragene Miettage gehen weiterhin vor; danach folgen der
  eigene Zeitraum, die Teilgruppe und das Projekt [A]. Die Ansicht nennt,
  woher die Miettage einer Position stammen.
- PRJ-063 [SOLL · V · S2] Miettage und Staffelfaktor werden getrennt
  benannt ("2 Tage", darunter "Faktor 1,5") und nie als Rechnung "2 × 1,5"
  dargestellt, die einen Faktor 3 nahelegt.
- PRJ-006 [SOLL · A · S4] Phasen bzw. Termine im Projekt, in dieser
  Reihenfolge: Planungen und Besprechungen, Packen, Anfahrt, Aufbau, Probe,
  Veranstaltung, Abbau, Rückfahrt, Nachbereitung, Reinigung (PRJ-071) und
  Sonstiges – je mit Zeitraum und Ort, auf Wunsch mit eigener Bezeichnung
  (PRJ-092). Rentalars schlägt vor, den Mietzeitraum zu erweitern, wenn eine Phase über ihn
  hinausgeht (PRJ-100).
- PRJ-007 [SOLL · A · S4] Dateianhänge am Projekt (Pläne, Rider, Verträge).

Status

- PRJ-008 [MUSS · V · S1] Projekte durchlaufen acht Status. "Bestätigt" ist
  zweigeteilt: mit offenen Punkten oder vollständig geklärt (PRJ-059). Der
  Status "Wieder im Lager" (PRJ-093) steht am Ende. Die
  Wirkung auf die Verfügbarkeit ist ein Vorschlag [A]:
Der Status "Bestätigt – Einzelheiten offen" heißt in der deutschen Oberfläche "Bestätigt
  – Preise und Einzelheiten offen" (der Wert in der API bleibt confirmed_open); die Gruppen von Status ("fest", "Auftrag",
  "verdient", "nicht vollständig bestätigt") sind an einer Stelle im Programm festgelegt.

| Status                    | Bedeutung                                            | Wirkung auf Verfügbarkeit      |
|---------------------------|------------------------------------------------------|--------------------------------|
| Anfrage                   | Entwurf, unverbindlich                               | keine                          |
| Option                    | Angebot abgegeben, vorgemerkt                        | weiche Reservierung (sichtbar) |
| Bestätigt – Einzelheiten offen | Auftrag erteilt, Angaben fehlen (z. B. Aufbauzeiten) | feste Reservierung             |
| Bestätigt                 | Auftrag erteilt, alle Angaben liegen vor             | feste Reservierung             |
| Unterwegs                 | Material vollständig ausgegeben (PCK-025)            | feste Reservierung             |
| Wieder im Lager           | Material vollständig zurück                          | keine (Zeitraum beendet)       |
| Abgeschlossen             | nachbereitet, Zeiten freigegeben                     | keine                          |
| Storniert                 | abgesagt                                             | keine                          |

- PRJ-009 [MUSS · A · S1] Statuswechsel sind protokolliert. Abgeschlossene
  Projekte sind gegen Änderungen gesperrt; Wiederöffnen erfordert ein
  Sonderrecht.
- PRJ-059 [SOLL · A · S4] Im Status "Bestätigt – Einzelheiten offen" werden die
  fehlenden Angaben als offene Punkte festgehalten (z. B. Aufbauzeiten,
  Ansprechpartner vor Ort). Eine Übersicht zeigt alle Projekte mit offenen
  Punkten; sind alle erledigt, schlägt das System den Wechsel auf "Bestätigt"
  vor. Die Übersicht nennt auch die offenen Fehlbestände
  (PRJ-098).

Materialzuordnung

- PRJ-010 [MUSS · V · S1] Einem Projekt werden Produkte mit Menge und Zeitraum
  zugeordnet (Materialposition). Die Produktnummer führt zum
  Produkt (PRJ-126).
- PRJ-011 [MUSS · A · S1] Der Zeitraum einer Materialposition ist mit dem
  Projektzeitraum vorbelegt und je Position überschreibbar.
- PRJ-064 [SOLL · V · S1] An einer Materialposition lässt sich als interner
  Hinweis ein bestimmtes Modell oder ein bestimmtes Exemplar des Produkts
  festhalten ("Wunsch"). Der Wunsch ändert weder Preis noch Verfügbarkeit des
  Produkts und erscheint nie in der Preisübersicht. Das System warnt, wenn das
  gewünschte Exemplar nicht einsatzfähig, fest verbaut oder im selben Zeitraum
  anderswo gewünscht ist, oder wenn von einem Modell mehr Stück gewünscht
  sind, als einsatzfähig vorhanden [A]. Bei
  einer Position mit mehreren Stück je Produkt (PRD-052) lassen sich mehrere bestimmte
  Exemplare wünschen: Jedes gewünschte Exemplar deckt ein Stück ab, der Rest
  kommt aus beliebigen Exemplaren, mehr Wünsche als Stück sind nicht möglich.
  Menge und Preis der Position ändern sich nicht; die Planung nennt den Anteil
  ("1 von 10 Stück") und warnt je Exemplar, die Packliste (Seite, PDF, API)
  nennt genau diese Exemplare mit Lagerplatz, und die Ausgabe vermerkt sie
  zuerst.
- PRJ-065 [SOLL · V · S1] Die Produktsuche beim Hinzufügen einer Position
  findet auch Modelle (über Name und Hersteller) und Exemplare (über ID und
  Seriennummer). Die Auswahl eines solchen Treffers legt die Position für das
  zugehörige Produkt an und trägt Modell oder Exemplar als Wunsch ein
  (PRJ-064).
- PRJ-012 [MUSS · A · S1] Beim Hinzufügen und Ändern einer Position wird die
  Verfügbarkeit im Zeitraum sofort angezeigt (verfügbar / knapp / überbucht mit
  Fehlmenge).
- PRJ-013 [MUSS · V · S1] Überbuchung wird nicht verhindert, sondern deutlich
  gewarnt: Die Position lässt sich trotz Fehlmenge speichern, damit weiter
  geplant werden kann. Sie bleibt als Fehlbestand markiert, bis die Fehlmenge
  gedeckt ist, etwa durch Zumietung (PRJ-054).
- PRJ-014 [MUSS · V · S1] Positionen lassen sich in frei benennbare Teilgruppen
  gliedern (z. B. "Licht Front-Traverse", "Licht Rear-Traverse", "Ton FOH") und
  per Ziehen sortieren und verschieben. Preise je Teilgruppe: PRJ-033 ff.
- PRJ-015 [MUSS · A · S1] Je Position: Einzelpreis (aus Produkt vorbelegt,
  überschreibbar), Rabatt, Notiz. Preisänderungen am Produkt wirken nicht auf
  bestehende Positionen; was ein Projekt
  tun soll, solange es nicht bestätigt ist, regeln PRJ-072 und PRJ-137 bis PRJ-139.
- PRJ-016 [SOLL · A · S1] Sets werden als eine Position mit aufklappbaren
  Bestandteilen dargestellt.
- PRJ-017 [SOLL · A · S2] Freie Positionen ohne Produkt (Text, Menge, Preis)
  für Sonderleistungen. Es gibt die Textposition, die nur
  einen Text trägt (PRJ-128).
- PRJ-018 [MUSS · V · S2] Zumietung: Material eines Lieferanten wird über
  Produkte der Kategorie E geplant, die keinen eigenen Bestand haben. Die
  Position trägt zusätzlich Lieferant und Einkaufspreis und erscheint
  gekennzeichnet auf der Packliste.

Personalzuordnung

- PRJ-019 [MUSS · V · S3] Einem Projekt wird Personal mit Funktion und Zeitraum
  zugeordnet (Personalposition).
- PRJ-020 [SOLL · A · S3] Personalbedarf kann zunächst ohne Person geplant
  werden (z. B. "2x Stagehand, Samstag 08–14 Uhr") und später besetzt werden.
- PRJ-021 [MUSS · A · S3] Beim Zuordnen einer Person wird der Stundensatz aus
  Person und Funktion übernommen und an der Position festgeschrieben; er ist
  mit Recht überschreibbar.
- PRJ-022 [MUSS · A · S3] Das System warnt bei Doppelbuchung einer Person, bei
  Überschneidung mit einer Abwesenheit und bei nicht zugeordneter Funktion.
- PRJ-023 [SOLL · A · S3] Je Personalposition: geplante Stunden, Treffpunkt,
  Hinweis, Rückmeldestatus (PER-016).

Kalkulation

- PRJ-024 [MUSS · A · S1] Projektsummen: Material netto, Personal (geplant),
  Rabatt, Summe netto, Steuer je Steuerart, Summe brutto.
- PRJ-025 [SOLL · A · S2] Gegenüberstellung Erlöse und interne Kosten
  (Personalkosten aus Stunden- und Tagessätzen, Zumietung) mit dem Gewinn aus
  dem Projekt (PRJ-087).
- PRJ-026 [SOLL · A · S3] Soll-Ist-Vergleich: geplante gegen erfasste Stunden
  je Funktion und Person.

Arbeiten mit Projekten

- PRJ-027 [MUSS · A · S1] Projektliste mit Suche und Filtern (Status, Zeitraum,
  Kunde, Projektleitung). Auch mit der Wiedervorlage
  (PRJ-105).
- PRJ-028 [SOLL · A · S4] Kalender- und Zeitstrahlansicht aller Projekte.
- PRJ-067 [SOLL · V · S5] Der Kalender (PRJ-028) lässt sich wahlweise als
  Monat oder als Woche zeigen. Die Woche nennt je Tag die Projekte mit Uhrzeit
  und ihren Phasen; die Wahl bleibt für die Sitzung erhalten [A]. Seit Version
  0.19 öffnet er mit der Woche (VFG-028).
- PRJ-029 [SOLL · A · S4] Projekt duplizieren, wahlweise mit Material und
  Personalbedarf, mit neuem Zeitraum.
- PRJ-030 [SOLL · A · S5] Projektvorlagen für wiederkehrende
  Veranstaltungsformate. Ausgeführt in
  PRJ-076.
- PRJ-031 [SOLL · V · S6] Ein Projekt kann Teilprojekte haben (Beispiel:
  gesamte Produktion mit mehreren Bühnen). Einzelheiten PRJ-043 ff.
- PRJ-032 [MUSS · A · S1] Änderungshistorie je Projekt (wer hat wann was
  geändert).

Teilgruppen mit Preisen

- PRJ-033 [MUSS · V · S1] Die Projektplanung zeigt je Teilgruppe die Preise an:
  Einzelpreis und Positionssumme je Zeile sowie eine Zwischensumme netto je
  Teilgruppe.
- PRJ-034 [MUSS · A · S1] Die Projektsumme ergibt sich aus den Zwischensummen
  aller Teilgruppen, den Positionen ohne Teilgruppe, dem Personal (PRJ-038) und
  den projektweiten Aufpreisen (PRJ-058); die Blöcke werden getrennt
  ausgewiesen.
- PRJ-035 [MUSS · V · S1] Die Teilgruppenübersicht mit Preisen dient als
  Grundlage für die externe Angebotserstellung. Zunächst genügt die Ansicht im
  Browser, aus der die Werte von Hand übertragen werden; Beträge und Texte
  lassen sich dort einzeln kopieren. Druck (PDF), Tabellenexport (CSV) und
  Abruf über die API folgen später (DOK-009).
- PRJ-036 [SOLL · A · S1] Die Ansicht ist umschaltbar zwischen "nur Teilgruppen
  mit Summen" und "Teilgruppen mit allen Positionen", damit je nach
  Angebotsstil die passende Detailtiefe übernommen werden kann.
- PRJ-066 [SOLL · V · S1] In der Ansicht ohne Positionen fasst jede Teilgruppe
  in einer Zeile zusammen, was sie enthält ("8 × LED-Scheinwerfer RGBW, 6 ×
  Traverse 4-Punkt 2 m"), damit der Kunde grob weiß, wofür der Betrag steht.
  Gleiche Produkte werden zusammengezählt; Zumietungen, die nur eine Fehlmenge
  decken, erscheinen nicht. Genannt werden höchstens sechs Dinge – die
  wertvollsten, in der Reihenfolge der Planung –, der Rest als "und 4 weitere
  Positionen" [A].
- PRJ-037 [SOLL · V · S6] Teilgruppen sind schachtelbar (z. B. Licht >
  Front-Traverse), bis zu drei Ebenen; die Hierarchie wird per Ziehen und
  Ablegen geordnet. Obergruppen summieren ihre Untergruppen. Das Datenmodell
  sieht die Schachtelung von Beginn an vor.
- PRJ-038 [MUSS · V · S3] Personal wird nicht auf Teilgruppen
  heruntergebrochen: Personalpositionen stehen auf Ebene des Projekts (künftig
  des Teilprojekts) in einem eigenen Block "Personal" mit eigener
  Zwischensumme. Freie Positionen sowie Aufpreise und Fahrt/Transport (PRJ-053)
  können Teilgruppen zugeordnet werden.
- PRJ-039 [MUSS · V · S2] Je Teilgruppe: Beschreibungstext, Rabatt (Prozent
  oder Betrag) oder Pauschalpreis, der die Summe der Positionen ersetzt.
- PRJ-040 [MUSS · V · S2] Teilgruppen können als "optional" oder "Alternative"
  gekennzeichnet werden; sie werden mit Preis gezeigt, zählen aber nicht zur
  Projektsumme und reservieren kein Material fest.
- PRJ-041 [SOLL · A · S2] Teilgruppen samt Positionen lassen sich kopieren,
  sowohl innerhalb des Projekts als auch aus einem anderen Projekt.
- PRJ-042 [MUSS · A · S1] Dasselbe Produkt darf in mehreren Teilgruppen
  vorkommen. Die Verfügbarkeit wird je Produkt über alle Teilgruppen des
  Projekts hinweg geprüft; Preise in Teilgruppen unterliegen dem Preisrecht
  (AUT-019).
- PRJ-058 [MUSS · A · S2] Aufpreise, die sich auf mehrere Teilgruppen, das
  Personal oder das gesamte Projekt beziehen, stehen auf Projektebene in einem
  eigenen Block "Aufpreise". Aufpreise auf Positionen einer einzigen Teilgruppe
  stehen in dieser Teilgruppe.

Leistungen als Produkte

- PRJ-051 [MUSS · V · S3] Personalpositionen werden gegenüber dem Kunden über
  das Dienstleistungsprodukt ihrer Funktion bepreist (PER-008): Preis = Menge
  (Stunden oder Tage) × VK des Produkts. Welche Menge zählt, bestimmt die
  Abrechnungsweise (PRJ-061). Der Preis ist an der Position überschreibbar. Die
  internen Kosten ergeben sich aus dem Stundensatz der eingeplanten Person
  (PRJ-021). Die Position zeigt ihr Dienstleistungsprodukt
  (PRD-044), und ab einer Grenze von Stunden je Tag gelten ein höherer Preis
  und ein höherer Kostensatz (PER-035).
- PRJ-052 [SOLL · A · S3] Solange eine Personalposition noch nicht besetzt ist
  (PRJ-020), zeigt die Kalkulation den Preis aus dem Dienstleistungsprodukt und
  als Kosten einen Richtwert je Funktion.
- PRJ-053 [SOLL · A · S2] Fahrt- und Transportleistungen (Kategorie F) und
  Aufpreise (Kategorie A) sind Positionen ohne Verfügbarkeitsprüfung und können
  wie Material Teilgruppen zugeordnet werden. Fahrt und
  Transport sind keine Dienstleistung, sondern Nebenkosten (PRD-045).
- PRJ-061 [MUSS · V · S3] Abrechnungsweise je Personalposition: nach Plan
  (geplante Stunden), pauschal (PER-018) oder nach Aufwand. Nach Aufwand gilt:
  Preis = freigegebene Stunden × VK des Dienstleistungsprodukts. Bis zur
  Freigabe steht die geplante Menge als gekennzeichneter Schätzwert in
  Projektsumme und Preisübersicht. Auch je Tag (PER-029).
  "Nach Aufwand" ist die Voreinstellung für neue Positionen,
  die nach Stunden abgerechnet werden (PER-036).

Fehlmengen und Zumietung

- PRJ-054 [MUSS · V · S2] Zumietvorschlag: Entsteht eine Fehlmenge, schlägt das
  System die Zumietung vor und legt auf Bestätigung eine Zumietposition
  (Kategorie E) über die fehlende Menge und den Zeitraum an, verknüpft mit der
  ursprünglichen Position. Die Bezeichnung wird vom fehlenden Produkt
  übernommen (PRD-040).
- PRJ-055 [MUSS · A · S2] Eine Zumietung zur Deckung einer Fehlmenge erhöht den
  Preis gegenüber dem Kunden nicht: Berechnet wird die ursprüngliche Position;
  die Zumietung erscheint mit ihrem Einkaufspreis in den Kosten und auf der
  Packliste. Eigenständige Zumietpositionen (Material, das der Betrieb gar
  nicht führt) haben dagegen Verkaufs- und Einkaufspreis.
- PRJ-056 [SOLL · A · S2] Entfällt die Fehlmenge nachträglich (Menge
  verringert, anderes Projekt storniert), weist das System darauf hin, dass die
  Zumietung nicht mehr nötig ist.
- PRJ-057 [SOLL · A · S2] Übersicht aller offenen Fehlbestände und aller
  Zumietungen mit Lieferant, Zeitraum und Status (angefragt, bestellt,
  erhalten, zurück); vgl. VFG-013. Davor steht der Status
  "offen", der erste und voreingestellte; angefragt, bestellt, erhalten und
  zurück brauchen einen Lieferanten (PRJ-101). Von der Übersicht führt eine
  Zumietung zur Seite ihres Lieferanten im Projekt (PRJ-106).

Teilprojekte (künftige Ausbaustufe)

- PRJ-043 [MUSS · A · S1] Datenmodell, API und Rechtekonzept werden von Beginn
  an so angelegt, dass Teilprojekte später ergänzt werden können, ohne
  bestehende Projekte umzubauen (ein Projekt kann auf ein übergeordnetes
  Projekt verweisen).
- PRJ-044 [SOLL · V · S6] Es gibt genau eine Ebene von Teilprojekten. Ein
  Teilprojekt hat eigenen Namen, Ort bzw. Bühne, Projektleitung und Status,
  einen eigenen Zeitraum und eigene Miettage (eine Bühne muss z. B. einen Tag
  früher fertig sein) sowie eigene Materialpositionen mit Teilgruppen und
  eigene Personalpositionen.
- PRJ-045 [SOLL · V · S6] Ein Teilprojekt erbt Kunde und Rechnungsdaten stets
  vom Gesamtprojekt; am Teilprojekt sind sie nicht änderbar. Ansprechpartner,
  Ort und weitere Voreinstellungen werden übernommen und sind überschreibbar.
- PRJ-046 [SOLL · A · S6] Das Gesamtprojekt zeigt die Summen aller Teilprojekte
  (Preise, Material, Personal, Stunden), aufgeschlüsselt je Teilprojekt.
  Gemeinsame Positionen (z. B. zentrale Stromversorgung, Produktionsleitung)
  können direkt am Gesamtprojekt geführt werden.
- PRJ-047 [SOLL · A · S6] Positionen der Teilprojekte zählen bei der
  Verfügbarkeit wie eigenständige Reservierungen mit ihrem jeweiligen Zeitraum.
  Engpässe zwischen Teilprojekten desselben Gesamtprojekts werden angezeigt.
- PRJ-048 [SOLL · A · S6] Packlisten sind je Teilprojekt und für das
  Gesamtprojekt erzeugbar; Personaleinsätze und Zeiteinträge beziehen sich auf
  das Teilprojekt.
- PRJ-049 [SOLL · A · S6] Projektrechte gelten vom Gesamtprojekt aus für alle
  Teilprojekte und können je Teilprojekt eingeschränkt werden.
- PRJ-050 [SOLL · A · S8] Ein bestehendes Projekt, das weder Gesamt- noch
  Teilprojekt ist, lässt sich nachträglich in Teilprojekte gliedern ("In
  Teilprojekte gliedern"): Es wird zum Gesamtprojekt, und gewählte
  Teilgruppen der obersten Ebene werden je ein Teilprojekt mit ihren
  Positionen und den Zeiträumen des Projekts, nummeriert wie neue
  Teilprojekte (2026-0042-1, 2026-0042-2; PRJ-044). Was nicht gewählt ist,
  bleibt am Gesamtprojekt (PRJ-046). An einem Gesamtprojekt macht
  "Teilgruppen in Teilprojekte umwandeln" Teilgruppen zu Teilprojekten.
  Was dabei erlaubt ist – etwa nicht mehr, sobald Material ausgegeben ist –
  und was mit Dokumenten und Personal geschieht, steht in 12.2 (24 a). Das
  Änderungsprotokoll hält es fest; die API kann beides.
- PRJ-060 [SOLL · V · S6] Material kann zwischen Teilprojekten wechseln:
  Dieselben Stücke lassen sich nacheinander in mehreren Teilprojekten eines
  Gesamtprojekts einplanen. Überschneiden sich die Zeiträume nicht, entsteht
  keine Fehlmenge. Eine solche Position kann als Übernahme aus einem anderen
  Teilprojekt gekennzeichnet werden; sie erscheint dann auf den Packlisten
  beider Teilprojekte, wird aber nur einmal berechnet [A].

Weitere Anforderungen

- PRJ-068 [SOLL · V · S5] Übliche Projektzeiten sind 12:00 Uhr bis 12:00 Uhr am
  Folgetag; neue Projekte schlagen sie vor. Die Uhrzeiten sind in den
  Grundeinstellungen änderbar.
- PRJ-069 [SOLL · V · S5] Die beiden Zeiträume eines Projekts (PRJ-005) heißen
  im Formular nach dem, was sie entscheiden: "Mietzeitraum: Material ist außer
  Haus" (Verfügbarkeit, Zeitraum der Positionen) und "Veranstaltung – für die
  berechneten Miettage" (schlägt nur die Miettage vor). Die Tage einer
  mehrteiligen Veranstaltung stehen als Phasen in der Zeitplanung; eigene
  Mietzeiträume je Teil bringen die Teilprojekte (PRJ-031). Beide
  Kästen sind gleich aufgebaut (PRJ-099).
- PRJ-070 [MUSS · V · S5] Kunde und Veranstaltungsort werden im
  Projektformular durch Tippen mit Vorschlägen gewählt statt aus einer
  langen Liste. Gibt es den Kunden noch nicht, legt ihn der letzte Vorschlag
  "… als neuen Kunden anlegen" in einem Dialog an – mit denselben Angaben und
  derselben Dublettenwarnung wie in der Kundenverwaltung (KND-008). Ebenso
  ein neuer Veranstaltungsort.
- PRJ-071 [SOLL · V · S5] Phasenart "Reinigung" am Ende der Zeitplanung: nach
  "Nachbereitung" (PRJ-092), gefolgt nur noch von "Sonstiges".
- PRJ-072 [SOLL · V · S5] Ändert sich der Preis eines Produkts, zeigt die
  Planung einer Anfrage, einer Option oder von "Bestätigt – Einzelheiten offen" die Positionen mit altem Preis und
  bietet an, die neuen Preise zu übernehmen. Von Hand gesetzte Preise werden
  einzeln übernommen oder behalten; bestätigte Projekte behalten ihre
  Preise. Nach dem Umstellen auf die aktuelle Staffel zeigt die Planung
  sofort wieder alles, ohne neu zu laden. Dasselbe
  gilt für Name, Einheit, Steuersatz und Abrechnungsart: Jede Position
  merkt sich, was sie vom Produkt übernommen hat, und die Planung listet jede
  Abweichung mit alt und neu (PRJ-137). Preise nur für den, der Preise sehen darf.
- PRJ-073 [SOLL · V · S5] Die vorgeschlagenen Stunden einer Personalposition
  sind die ganze Dauer ihres Zeitraums, Ende minus Beginn, auf Viertelstunden
  gerundet: Montag 08:00 bis Dienstag 20:00 sind 36 Stunden, Freitag 10:00 bis
  Sonntag 18:00 sind 56. Wird nicht durchgearbeitet, werden die wirklichen
  Stunden von Hand eingetragen. Wird je Tag abgerechnet (PER-029), zählen
  statt der Stunden die Kalendertage, die der Zeitraum berührt: Montag 08:00
  bis Dienstag 20:00 sind 2 Tage.
  Stunden je angefangenem Tag.
- PRJ-074 [SOLL · V · S5] Der Reiter "Dokumente" steht im Projekt direkt nach
  der Preisübersicht.
- PRJ-075 [SOLL · V · S5] Eine Position lässt sich duplizieren; die Kopie
  steht direkt darunter. Eine Position lässt sich als optional oder als
  Alternative kennzeichnen: Sie zeigt ihren Preis, zählt aber weder zur
  Summe noch zu Rechnung und Packliste und reserviert nur wie eine Option.
- PRJ-076 [SOLL · V · S5] Projektvorlagen (PRJ-030): Ein Projekt lässt sich
  als Vorlage speichern – Teilgruppen und Positionen mit ihren Mengen,
  Personalpositionen ohne Personen, Phasen und offene Punkte, mit Zeiten
  relativ zum Beginn. Ein neues Projekt kann mit einer Vorlage beginnen.
  Kunde, Veranstaltungsort und Personen werden nicht übernommen; es gelten
  die Preise des Tages und der Rabatt des Kunden [A]. Ein Eintrag mit eigenem Zeitraum kann
  stattdessen am Ende des Projekts hängen
  ("anchor": "end"): Seine Zeiten zählen dann vom Ende an, sodass er bei
  jeder Dauer am Ende liegt. "Als Vorlage speichern" setzt das nie; die
  Vorlage "Dry Hire" nutzt es (PRJ-095).
- PRJ-077 [SOLL · V · S5] Import eines Lichtplots als MVR-Datei (etwa aus
  Vectorworks, grandMA3, Capture oder WYSIWYG): Rentalars zählt die Geräte
  je Gerätetyp und Modus, schlägt zu jedem Typ ein Produkt vor und merkt sich
  die Zuordnung für den nächsten Plot. Die Positionen entstehen mit der
  gezählten Menge in einer neuen oder vorhandenen Teilgruppe.

Weitere Anforderungen

- PRJ-078 [SOLL · V · S6] Der Kopf eines Projekts zeigt auf jedem Reiter
  dieselben Aktionen in dieser Reihenfolge: "Projekt bearbeiten", den Status
  als Auswahlliste mit "Status ändern" statt einer Reihe von Knöpfen,
  "Dokument erstellen" mit dem Vorschlag für das nächste Dokument und den
  übrigen hinter einem Pfeil, dann "Duplizieren", "Als Vorlage speichern" und
  "Teilprojekt anlegen". Vorgeschlagen wird bei Anfrage und Option das
  Angebot, bei "Bestätigt" (auch mit offener Klärung) die Auftragsbestätigung,
  bei "Unterwegs" der Lieferschein, bei "Wieder im Lager" und "Abgeschlossen"
  die Rechnung. Der Knopf öffnet den Reiter "Dokumente" mit dem gewählten
  Dokument; erstellt wird es dort. Die Liste bietet nur die Status, die vom
  jetzigen aus möglich sind; wer den Status ändert, bleibt auf seinem Reiter,
  und vor "Storniert" fragt Rentalars nach.
- PRJ-079 [SOLL · V · S6] Der Reiter "Dokumente" zeigt die erstellten Dokumente,
  daneben den Kasten "Dokument erstellen" und darunter die Dateien des
  Projekts mit "Datei hochladen". Der Kasten bleibt neben dem Knopf im Kopf
  (PRJ-078).
- PRJ-080 [SOLL · V · S6] Personal je Phase: Eine Personalposition kann zu
  einer Phase des Projekts (PRJ-006) gehören und übernimmt dann deren
  Zeitraum; an der Position steht "Phase: Aufbau". Der Reiter "Zeitplanung"
  zeigt unter jeder Phase ihr Personal – Funktion,
  Person oder "offen", Stunden und einen abweichenden Zeitraum –, darunter
  "Personal ohne Phase"; "+ Personal für diese Phase" plant direkt für die
  Phase. Wird eine Phase verschoben, wandert ihr Personal mit ("Personal
  dieser Phase mitverschieben", vorgewählt): Eine Position mit genau dem
  Zeitraum der Phase bekommt den neuen, jede andere verschiebt sich so weit
  wie der Beginn der Phase und behält ihre Länge; eine Doppelbuchung meldet
  Rentalars sofort. Entfällt die Phase, bleibt ihr Personal mit seinem
  Zeitraum, nur ohne Phase. Kopien und Vorlagen behalten die Phase. Die
  Zeitplanung zeigt einen Zeitstrahl des Projekts (PRJ-103),
  aber den Kasten "Veranstaltungsort" nicht (PRJ-102).
- PRJ-081 [SOLL · V · S6] Die Einsatzansicht ist druckbar: "Drucken / PDF"
  liefert sie als PDF "Einsatzübersicht" mit Briefkopf, mit "Stand" samt
  Uhrzeit und mit allem, was die Person im Reiter sieht – nie mit Preisen,
  Stundensätzen oder Kunde. Sie wird nicht abgelegt und hat keine Nummer;
  abgelegt mit Nummer bleibt die Crew-Disposition (DOK-004). Beim Schreiben
  einer Mail steht sie unter den Anhängen, nicht vorgewählt; angehängt ist sie
  die Sicht eines beliebigen Kollegen, ohne "Mein Einsatz" und mit
  Kontaktdaten nur, soweit freigegeben (PER-019). Der
  Reiter der Einsatzansicht heißt "Überblick" (PRJ-104); das PDF heißt
  "Einsatzübersicht".
- PRJ-082 [SOLL · V · S6] Mehrere Positionen der Planung lassen sich auf
  einmal ändern: Jede Position hat ein Kästchen, das Kästchen im Kopf einer
  Teilgruppe wählt alle ihre Positionen. Für die Auswahl gibt es: optional,
  "Nicht mehr optional", als Alternative zu einer Position, in eine Teilgruppe
  oder nach "ohne Teilgruppe" verschieben, Rabatt (mit dem Recht für Preise)
  und löschen (nach Rückfrage). Jede Position wird einzeln geändert und steht
  im Verlauf; wo es nicht geht, bleibt sie unverändert, und Rentalars nennt
  sie mit dem Grund – etwa ausgegebenes Material oder eine Zumietung, die zu
  einer anderen Position gehört.
- PRJ-083 [SOLL · V · S6] Am Ende jeder Position und jeder Teilgruppe stehen
  neben Stift, Kopieren und Mülleimer die Symbole "optional" und
  "Alternative". "Optional" schaltet um und zeigt, ob die Position optional
  ist. "Alternative" fragt, wozu sie eine Alternative ist; die Angabe ist
  Pflicht – eine Position zu einer Position, eine Teilgruppe zu einer
  Teilgruppe desselben Projekts, die selbst keine Alternative ist. Planung und
  Preisübersicht nennen das Ziel mit Menge und Bezeichnung ("Alternative zu
  8 × LED-Scheinwerfer"), Angebot und Auftragsbestätigung mit seiner Nummer
  ("Alternative zu Pos. 3"). Fällt das Ziel weg, wird die Alternative
  optional. Eine Zumietung zu einer Fehlmenge, eine Position mit ausgegebenem
  Material und eine, aus der andere Teilprojekte übernehmen, werden weder
  optional noch Alternative.
- PRJ-084 [SOLL · V · S6] Eine Zumietung, die eine Fehlmenge deckt (PRJ-054,
  PRJ-055), steht als eingerückte Teilzeile direkt unter ihrer Position
  ("davon 4 zugemietet bei Verleih Nord · bestellt"), ohne eigenen Betrag, und
  wandert mit, wenn die Position verschoben wird. Beim Anlegen fragt ein
  Dialog Menge, Lieferant, Status und Einkaufspreis ab, den Einkaufspreis nur
  mit dem Recht dafür; einen Mietpreis gibt es nicht, denn der Kunde zahlt den
  Preis der Position. Der Lieferant wird dort durch Tippen
  gewählt oder neu angelegt, und der Status beginnt mit "offen" (PRJ-101);
  die Teilzeile führt zur Seite der Zumietung bei ihrem Lieferanten
  (PRJ-106).
- PRJ-085 [SOLL · V · S6] Die Projektliste bietet in der Spaltenwahl (UIX-015)
  Summen an, voreingestellt ausgeblendet: geplante Mannstunden,
  Material-Einnahme, Personal-Einnahme, Summe netto, Summe brutto,
  Material-Kosten (die Zumietungen), Personal-Kosten und Gewinn. Ein
  Gesamtprojekt zeigt die Summen mit seinen nicht stornierten Teilprojekten,
  ein Teilprojekt seine eigenen. Jede Spalte braucht dieselben Rechte wie in
  der Planung (AUT-019), der Gewinn alle drei; Projekte, deren Planung jemand
  nicht lesen darf, bleiben leer. Nach diesen Spalten wird nicht sortiert; der
  CSV-Export enthält sie, wenn sie gezeigt sind.
- PRJ-086 [SOLL · V · S6] Der Import eines Lichtplots heißt "MVR-Datei
  importieren" (PRJ-077). Die hochgeladene Datei legt Rentalars in den Dateien
  des Projekts ab, mit Datum und Uhrzeit vor dem Namen (yyyymmdd-hhmmss_,
  z. B. "20261013-221530_Rig.mvr"); wird eine andere Datei gewählt, entfällt
  die erste wieder, und eine Datei über der Grenze für Projektdateien wird
  nicht abgelegt. MVR-Dateien lassen sich auch von Hand hochladen. Was sich
  außer Produkten hinzufügen lässt, steht geordnet in einer Zeile direkt unter
  "Ohne Teilgruppe": neue Teilgruppe, "Position ohne Produkt" (in
  Teilprojekten auch "Aus anderem Teilprojekt übernehmen") und "MVR-Datei
  importieren".
- PRJ-087 [SOLL · V · S6] Der "Deckungsbeitrag" heißt "Gewinn aus dem
  Projekt": Summe netto minus die Kosten der Zumietungen und des Personals
  (PRJ-025). Eine einzelne Zeile und die Spalte der Projektliste (PRJ-085)
  heißen "Gewinn".
- PRJ-088 [SOLL · V · S6] Die Preisübersicht schlüsselt das Personal auf
  Wunsch je Phase und Funktion auf ("Personal je Phase und Funktion"): je
  Phase eine Zeile je Funktion mit Plätzen, Stunden oder Tagen und Betrag,
  darunter die Zwischensumme der Phase; Personal ohne Phase steht zuletzt. Wer
  Personalkosten sehen darf, sieht in dieser Ansicht auch Kosten und Gewinn je
  Zeile. PDF und CSV übernehmen die Ansicht, aber ohne Kosten, denn sie gehen
  an Kunden.
- PRJ-089 [SOLL · V · S8] Showfiles lassen sich als Projektdateien hochladen:
  Die Dateien gängiger Lichtpulte, Medienserver und Tonsysteme sind
  zugelassen, etwa von ETC Eos, Hog, ChamSys, grandMA2 und grandMA3,
  Avolites, Resolume, QLab, L-Acoustics Network Manager, d&b R1, Yamaha DM3
  und DM7, Midas M32 und DiGiCo; Shows, die aus einem Ordner bestehen, als
  ZIP-Datei. Die Prüfung beim Hochladen (NFA-007) lässt sie nach ihrer
  Endung zu; Ausführbares bleibt ausgeschlossen. Ein Showfile hat die
  Unterlagenart "Showfile" und nennt Pult bzw. Software und Version; das
  aktuelle ist markiert. Die eingeplante Crew sieht es. Ob die Grenze für
  die Größe von Projektdateien für übliche Showfiles reicht, wird dabei
  geprüft. Der Hinweis eines leeren Reiters
  "Dokumente" – im Projekt wie im Servicefall – nennt neben Bühnenplänen, Ridern
  und Verträgen auch die Showfiles.
- PRJ-090 [SOLL · V · S8] Servicefälle: Auf einen Servicefall lässt sich schnell reagieren, ohne
  ein Projekt zu planen, und die Korrespondenz liegt trotzdem geordnet an
  einer Stelle. Ein Servicefall ist eine eigene Art von Projekt mit wenigen
  Feldern – Name, Kunde, Ansprechpartner,
  Beschreibung –,
  neu angelegt oder aus einer Mail ohne Kennung unter Projekte → Anfragen
  (EML-042). Seine Mails laufen wie bei jedem Projekt über das
  Projektkürzel. Er hat eine verantwortliche Person und eigene Status
  (offen, in Arbeit, erledigt), steht in einer eigenen Liste bzw. unter
  einem eigenen Filter und zählt nicht in Verfügbarkeit, Kalender,
  Zeitstrahl und Fehlbeständen. Seine Nummer kommt aus dem Nummernkreis der
  Projekte; er lässt sich in ein normales Projekt umwandeln. Seit Version
  0.22 hat ein Servicefall Beteiligte (PRJ-108); auf einen offenen
  Servicefall erfasst jeder mit Zeiterfassung spontan Zeiten, auch ohne
  eingeplant zu sein (ZEI-024); und eine Adresse eines Postfachs kann die
  Rolle "nur für Servicefälle" haben – sie ist dann der Absender seiner
  Mails (EML-047). Ein Servicefall braucht wie ein Projekt
  einen Kunden: Im Formular ist er Pflicht,
  über die API fehlt er mit 400. Wird ein Fall aus einer Anfrage angelegt,
  schlägt Rentalars den Kunden vor. Vorhandene Servicefälle ohne
  Kunden bleiben gültig, bis jemand sie bearbeitet; dann fragt das Formular
  nach dem Kunden. Die Beschreibung bleibt freiwillig. Ein Servicefall
  hat diese Status: offen,
  in Arbeit, wartet (auf Rückmeldung, Aktion oder Materiallieferung),
  wartet auf Schließen, Rückstand, erledigt (PRJ-112); Automationen setzen
  sie nach Regeln (ADM-013). Der erste Reiter eines Servicefalls heißt
  "Überblick", und sein Reiter "Korrespondenz" ist der eines Projekts
  (EML-050); der Zeitpunkt der letzten Statusänderung gleicht die
  Begleit-App ab (PRJ-114).
  Ein Servicefall kann
  intern sein – eigenes Material, ohne Kunde –, etwa die Reparatur eines
  gemeldeten Defekts (MAT-057); er nennt dann die Defektmeldung, aus der er
  entstand.
- PRJ-091 [KANN · V · S10] Eine eingebaute KI schlägt aus mehreren ähnlichen
  Projekten neue Projektvorlagen (PRJ-076) vor. Einstellungen → KI nennt
  diese Verwendung als "später" (ADM-017); sie bleibt
  KANN, nur festgehalten.

Weitere Anforderungen

- PRJ-092 [SOLL · V · S6] Die Phasen eines Projekts (PRJ-006) beginnen mit
  "Planungen und Besprechungen" – für Ortstermine und Technikbesprechungen,
  auch Wochen vor dem Mietzeitraum. "Verladen" heißt "Packen"; der
  Verladetermin einer Packliste heißt weiter "Verladen". Nach der Rückfahrt
  folgt "Nachbereitung": Material vom Transport auspacken, Eingangskontrolle,
  einlagern; danach "Reinigung" (PRJ-071) und zuletzt "Sonstiges".
  Vorhandene Phasen behalten ihre Art. Eine Phase außerhalb des
  Mietzeitraums steht im Kalender und im Zeitstrahl an ihrem Tag, im
  Zeitstrahl in der Zeile ihres Projekts.
- PRJ-093 [SOLL · V · S6] Der Status "Zurück" (PRJ-008) heißt "Wieder im
  Lager", damit er nicht mit dem Knopf "Zurück" (UIX-011) verwechselt wird –
  überall, wo Rentalars den Status nennt. Seine Bedeutung bleibt, ebenso der
  Wert in der API (returned). Packlisten und Zumietungen behalten ihren Stand
  "zurück".
- PRJ-094 [SOLL · V · S6] In der Personalplanung bietet die Auswahl der
  Phase – im Formular unter dem Personal und im Dialog "Personalposition
  bearbeiten" – am Ende "Neue Phase …". Wie ein neuer Kunde im
  Projektformular (PRJ-070) entsteht die Phase in einem Dialog: Phase,
  Bezeichnung, Von, Bis, Veranstaltungsort und Ort, vorbelegt mit dem schon
  eingetragenen Zeitraum, sonst dem des Projekts. "Phase speichern" legt sie
  in der Zeitplanung an, nimmt sie in jede Phasenauswahl des Projekts auf und
  wählt sie aus; Funktion, Person und Plätze bleiben, Von und Bis übernehmen
  den Zeitraum der Phase (PRJ-080). "Abbrechen" oder Esc schließt nur diesen
  Dialog. Den Eintrag bekommt nur, wer das Projekt bearbeiten darf, solange
  es nicht abgeschlossen ist; mit der Tastatur öffnen Enter oder Leertaste
  den Dialog.
- PRJ-095 [SOLL · V · S6] Neue Installationen bei der Ersteinrichtung und
  bestehende mit dem Update bekommen die Projektvorlage (PRJ-076)
  "Dry Hire (Vermietung ohne Personal)" für Mieten, bei denen der Kunde das
  Material im Lager abholt und selbst zurückbringt. Sie hat keine Positionen
  und kein Personal, aber eine Projektnotiz und die Phasen Packen (die ersten
  zwei Stunden des Mietzeitraums), "Übergabe an den Kunden (Abholung)" (die
  Stunde danach), Rücknahme (drei bis zwei Stunden vor dem Ende) und
  Nachbereitung (die letzten zwei Stunden), jeweils mit Ort "Lager".
  Rücknahme und Nachbereitung richten sich nach dem Ende des Mietzeitraums
  und passen so zu jeder Mietdauer. Gibt es schon eine Vorlage dieses
  Namens, bleibt sie, wie sie ist; die Vorlage lässt sich umbenennen,
  ersetzen oder löschen, und gelöscht kommt sie nicht wieder.
- PRJ-096 [SOLL · V · S6] Kundenmaterial (PRD-043) ist nur in Projekten
  seines Eigentümers und deren Teilprojekten einplanbar; nur dort bietet die
  Produktsuche es an, mit dem Hinweis "Kundenmaterial". Die Position trägt
  "Kundenmaterial – wird mitgeführt", hat keinen Preis ("nicht berechnet")
  und keinen Rabatt, ist weder Verkauf noch optional oder Alternative und
  zählt in keine Summe, keine Steuer und nicht zur Material-Einnahme.
  Angebot und Auftragsbestätigung nennen sie an ihrer Stelle mit Menge, ohne
  Preis, mit "Kundeneigenes Material – wird mitgeführt, ohne Berechnung" –
  ein Angebot "nur Teilgruppen" (DOK-013) unter ihrer Teilgruppe –, der
  Lieferschein mit "Kundeneigenes Material – wird mitgeführt"; Rechnung und
  E-Rechnung lassen sie weg. Die Packliste führt sie mit Gewicht, Volumen,
  Lagerort und dem Hinweis "Kundenmaterial – wird mitgeführt". Die
  Verfügbarkeit wird wie bei eigenem Material geprüft, eine Fehlmenge aber
  ohne Zumietung (PRJ-054). Solange Kundenmaterial geplant ist, lässt sich
  der Kunde des Projekts nicht wechseln.
- PRJ-097 [SOLL · V · S8] Rentalars ermittelt die Fahrten eines Projekts aus
  seinen Phasen und Adressen: bei "Aufbau" und "Abbau" vom Lager zum
  Veranstaltungsort und zurück, bei "Packen" und "Nachbereitung" die
  Abholung bzw. Rückgabe bei den Lieferanten von Zumietungen, die im
  Projekt als "wird beim Lieferanten abgeholt" gekennzeichnet sind. Jede
  Fahrt hat einen Routenlink zu Google Maps mit Start, Ziel und
  Zwischenzielen (UIX-033). Die Adresse des Lagers ist eine Einstellung,
  voreingestellt die Anschrift der Firma (ADM-001). Die Fahrten stehen dort,
  wo Planung und Fahrer sie sehen, in der Zeitplanung und im Überblick [A].
  Entfernungen berechnet Rentalars nicht, und einen Routendienst nutzt es
  nicht; entschieden mit UIX-033 und UIX-034 (NFA-050).
  Die Fahrten eines Projekts lassen sich anpassen und
  entfernen (PRJ-111), und ihr Routenlink beginnt am aktuellen Standort
  (UIX-033).

Ausbaustufe 7: Weitere Anforderungen

- PRJ-098 [SOLL · V · S7] Die Übersicht der offenen Punkte (PRJ-059) zeigt je
  Projekt auch die Fehlbestände, die noch nicht gelöst sind, als weitere
  Stichpunkte neben den notierten Punkten – etwa "Fehlbestand:
  4 × LED-Scheinwerfer (2 zugemietet, 2 offen)". Ein Klick führt in die
  Planung des Projekts zu der betroffenen Position. Es sind die Fehlbestände
  der Seite "Fehlbestände" (VFG-013); ein Projekt, dem Material fehlt,
  erscheint auch ohne offene Punkte. Gezeigt werden nur Projekte, deren
  Planung man sehen darf. Sonst bleibt die Übersicht, wie sie ist.
- PRJ-099 [SOLL · V · S7] In "Zeitraum im Kalender wählen" (UIX-025) ist der
  jeweils andere Zeitraum des Projekts schraffiert eingezeichnet, sobald er
  eingetragen ist: beim Mietzeitraum die Veranstaltung, bei der Veranstaltung
  der Mietzeitraum (PRJ-069). Beim Anlegen und Ändern einer Phase sind beide
  schraffiert, der Mietzeitraum grau, die Veranstaltung grün, mit einer
  Legende, die ihre Zeiten nennt. Im Projektformular sind die Kästen
  "Mietzeitraum: Material ist außer Haus" und "Veranstaltung – für die
  berechneten Miettage" gleich aufgebaut: Von, Bis und
  "Zeitraum im Kalender wählen" in einer Zeile, der Knopf so hoch wie die
  Felder, darunter die Miettage. Auf schmalen
  Bildschirmen rückt der Knopf unter die Felder.
- PRJ-100 [SOLL · V · S7] Liegt eine Phase ganz oder teilweise außerhalb des
  Mietzeitraums, wird sie gespeichert, und Rentalars fragt, ob der
  Mietzeitraum erweitert werden soll ("Mietzeitraum auf Fr 23.10. 14:00 –
  Di 27.10. 18:00 erweitern?") – in der Zeitplanung wie im Dialog "Neue Phase"
  der Personalplanung (PRJ-094). Vorgeschlagen wird der bisherige
  Mietzeitraum, so weit erweitert, wie die Phase es braucht. Erst "Erweitern"
  ändert ihn, wie im Projektformular: Positionen mit dem bisherigen
  Mietzeitraum übernehmen den neuen, alle im Projekt Eingeplanten werden
  benachrichtigt, und entstehen dadurch mehr Fehlbestände, weist Rentalars
  darauf hin. "Nicht erweitern" lässt alles, wie es ist. Phasen der Art
  "Planungen und Besprechungen" (PRJ-092) fragen nie, damit ein Ortstermin
  Wochen vorher kein Material bindet. Bei einem Teilprojekt muss der neue
  Zeitraum im Gesamtprojekt liegen (PRJ-045); sonst sagt Rentalars das, statt
  zu erweitern. Die API meldet die Lage der Phase und den Vorschlag, erweitert
  aber nie von selbst.

Ausbaustufe 7: Weitere Anforderungen

- PRJ-101 [SOLL · V · S7] In Formular und Dialog einer Zumietung (PRJ-084)
  wird der Lieferant durch Tippen mit Vorschlägen gewählt; gibt es ihn noch
  nicht, legt ihn der letzte Vorschlag "… als neuen Lieferanten anlegen" in
  einem Dialog an, wie einen neuen Kunden im Projektformular (PRJ-070).
  Der "Status" hat als ersten Wert und
  Voreinstellung "offen". Jeder andere Status – angefragt, bestellt, erhalten,
  zurück (PRJ-057) – braucht einen Lieferanten, im Formular wie über die API;
  "angefragt" ohne Lieferant gibt es nicht.
- PRJ-102 [SOLL · V · S7] Der Reiter "Zeitplanung" zeigt den Kasten
  "Veranstaltungsort" nicht; der Veranstaltungsort steht im Kopf und im
  Formular des Projekts.
- PRJ-103 [SOLL · V · S7] Der Reiter "Zeitplanung" zeigt einen Zeitstrahl des
  Projekts wie Planung → Zeitstrahl: Mietzeitraum, Veranstaltung, die Phasen
  und das Personal je Person – die Balken ihrer Personalpositionen in den
  Farben der Anfrage wie im Personalplan (VFG-027) –, in der Ansicht mit
  Tagen und Stunden (VFG-024).
- PRJ-104 [SOLL · V · S7] Die Reiter eines Projekts stehen in der Reihenfolge
  Überblick, Planung, (Teilprojekte), Preisübersicht, Dokumente, Zeitplanung,
  Packliste, Korrespondenz, Zugriff, Verlauf – "Packliste" steht also vor
  "Korrespondenz". Der Titel der Seite des Reiters "Überblick" und die Links
  dorthin heißen ebenso; das PDF heißt "Einsatzübersicht"
  (PRJ-081). "Überblick" steht an erster Stelle, wie bei
  Servicefällen, und ein Projekt öffnet auf ihm (PRJ-125).
- PRJ-105 [SOLL · V · S6] Wiedervorlage: Ein Projekt – in jedem Status,
  meist eine Anfrage oder Option – lässt sich auf Wiedervorlage legen, mit
  Datum, Notiz und der Person, für die sie ist (voreingestellt, wer sie
  setzt). An dem Tag bekommt diese Person eine Benachrichtigung, in der
  Anwendung und per Mail nach ihren Einstellungen (UIX-005). Die Startseite
  zeigt die fälligen Wiedervorlagen, die Projektliste zeigt sie und filtert
  danach, und der Kopf des Projekts nennt sie. "Erledigt" bzw. Entfernen hebt
  sie auf. Die API kennt die Felder. Eine
  Wiedervorlage hat eine freiwillige Uhrzeit, ab der die Erinnerung kommt
  (PRJ-109), und alle Wiedervorlagen stehen als Tabelle unter Planung →
  Wiedervorlagen (VFG-034). Die Status "wartet", "wartet auf Schließen" und
  "Rückstand" eines Servicefalls verlangen eine Wiedervorlage; bei "Rückstand" fehlt
  der Fall bis zu ihrer Fälligkeit auf der Startseite, unter Planung →
  Wiedervorlagen und in den Benachrichtigungen (PRJ-112).
- PRJ-106 [SOLL · V · S7] Je Projekt und Lieferant gibt es eine Seite
  "Zumietung bei <Lieferant>": die Zumietungen mit Status und
  Einkaufspreisen; die Dokumente des Lieferanten, hochgeladen mit einer Art –
  Angebot, Auftragsbestätigung, Lieferschein, Rechnung, Sonstiges –, die auch
  bei den Dateien des Projekts stehen; und die Korrespondenz mit dem
  Lieferanten: Von dort lässt sich eine Mail mit dem Projektkürzel schreiben,
  und Mails des Projekts von oder an die Adresse des Lieferanten erscheinen
  dort. Dafür hat der Lieferant in den Stammdaten E-Mail-Adresse, Telefon und
  Ansprechpartner (MAT-019). Erreichbar ist die Seite aus der Planung (an der
  Zumietung), aus der Übersicht der Fehlbestände und Zumietungen unter
  Planung → Fehlbestände (PRJ-057) und vom Lieferanten aus. Die API kennt die
  Dokumente und die Verbindung der Mails.

Ausbaustufe 8: Weitere Anforderungen

- PRJ-107 [SOLL · V · S8] Unter Projekte → Anfragen (EML-042) gibt es neben
  "Als Servicefall anlegen" auch "Als Projekt anlegen": Es legt ein neues
  Projekt an, mit Kunde und Ansprechpartner aus dem Absender, soweit
  Rentalars sie beim Servicefall ermittelt, und ordnet ihm die Mail zu. Das
  Feld "Projektnummer", mit dem eine Mail in ein vorhandenes Projekt
  übernommen wird, schlägt beim Tippen passende Projekte mit Nummer und Namen
  vor, auch für Tastatur und vorlesende Programme bedienbar. "Von der Liste
  nehmen" ist ein kleiner Knopf mit Papierkorb-Symbol; seine Beschriftung
  erscheint beim Fokus und für vorlesende Programme. Mit Kästchen lassen
  sich mehrere Anfragen wählen und nach einer Rückfrage mit "Ausgewählte von
  der Liste nehmen" auf einmal entfernen.
- PRJ-108 [SOLL · V · S8] Beteiligte eines Servicefalls: Einem Servicefall
  (PRJ-090) lassen sich Personen hinzufügen, ähnlich der Crew eines
  Projekts – je Person mit einer freiwilligen Funktion und einer Notiz. Die
  Beteiligten sehen den Fall unter "Mein Bereich" und werden benachrichtigt,
  wenn sie hinzukommen (UIX-005). Das ist keine Personalplanung: keine
  Prüfung der Verfügbarkeit, keine Einsatzanfrage, keine Kosten aus dem
  Plan. Bei der Zeiterfassung stehen Fälle, an denen man beteiligt ist,
  vorn (ZEI-024). Änderungsprotokoll und API kennen die Beteiligten.
- PRJ-109 [SOLL · V · S8] Eine Wiedervorlage (PRJ-105) hat eine freiwillige
  Uhrzeit, etwa "um 14:30". Die Erinnerung – die Benachrichtigung und der
  Auslöser "Wiedervorlage fällig" der Automationen (ADM-013) – kommt ab
  dieser Uhrzeit. Die Uhrzeit lässt sich überall
  setzen, wo die Wiedervorlage gesetzt wird, und steht überall, wo sie
  gezeigt wird; die API kennt sie. Die Uhrzeit ist beim Status
  "wartet auf Schließen" eines
  Servicefalls Pflicht: Zu diesem Zeitpunkt wird er geschlossen (PRJ-112).

Ausbaustufe 8: Weitere Anforderungen

- PRJ-110 [SOLL · V · S8] Unter Zeitplanung → Phasen lässt sich das
  Personal einer Phase nicht nur hinzufügen, sondern auch ändern: die Person
  – auch ein offener Platz ("offen/unbesetzt") lässt sich mit einer Person
  besetzen, mit der Prüfung der Verfügbarkeit und dem Ablauf der
  Einsatzanfrage wie im Dialog der Personalplanung –, die Funktion und die
  Zeiten; eine Personalposition lässt sich dort auch entfernen. Es gelten
  dieselben Regeln wie in der Personalplanung (PRJ-080, PER-033, PER-034).
- PRJ-111 [SOLL · V · S8] Die Fahrten eines Projekts (PRJ-097) lassen sich
  anpassen: Eine ermittelte Fahrt lässt sich entfernen – sie bleibt
  entfernt, auch wenn Rentalars die Fahrten neu ermittelt – oder ändern
  (Start, Ziel, Zwischenziele, Zeit, Notiz), und eigene Fahrten kommen
  hinzu. Die Anpassungen gelten je Projekt; ohne sie bleiben die ermittelten
  Fahrten. "Zurücksetzen" stellt die ermittelten Fahrten wieder
  her. Die Routenlinks folgen den Anpassungen (UIX-033). Anpassen kann, wer
  das Projekt bearbeiten darf [A]; die API kennt die Anpassungen.

Ausbaustufe 8: Weitere Anforderungen

- PRJ-112 [SOLL · V · S8] Weitere Status eines Servicefalls:
  Neben "offen", "in Arbeit" und "erledigt" (PRJ-090)
  gibt es drei Status, die je eine Wiedervorlage (PRJ-105) brauchen.
  "Wartet" – auf Rückmeldung, Aktion oder Materiallieferung, mit diesem
  Grund –: Die Wahl öffnet den vorhandenen Dialog "Wiedervorlage", und
  gespeichert wird der Status nur zusammen mit der Wiedervorlage (Tag
  Pflicht, Uhrzeit freiwillig). "Wartet auf Schließen" verlangt Tag und
  Uhrzeit (PRJ-109): Ändert sich bis dahin im Fall nichts, wird er
  geschlossen ("erledigt"); kommt vorher neue Kommunikation hinzu, wird er
  wieder "offen" (ADM-013).
  "Rückstand" verlangt ebenfalls eine Wiedervorlage; bis sie fällig ist,
  steht der Fall in keinem Dashboard – nicht in den Kästen der Startseite,
  nicht unter "Meine Servicefälle", nicht in der Voreinstellung von Mein
  Bereich → Servicefälle und Planung → Wiedervorlagen, ohne
  Benachrichtigung –, sondern nur in der Liste unter Projekte →
  Servicefälle, auch mit dem Filter nach Status; ist sie fällig, wird er
  "offen" (ADM-013). Liste, Filter, Farben der Status, Verlauf und API
  kennen diese Status; ohne die nötige Wiedervorlage weist die API den
  Status mit 400 ab.

Ausbaustufe 8: Weitere Anforderungen

- PRJ-113 [MUSS · V · S8] Änderungszeit je Feld eines Projekts für die
  Begleit-App (Anforderung der mobilen App;
  Entscheidung des Auftraggebers): Rentalars merkt sich je änderbarem Feld eines Projekts, wann
  es zuletzt geändert wurde – mindestens Name, Veranstaltungsort, Beginn und
  Ende, Beginn und Ende der Veranstaltung, Notizen, Status und Wiedervorlage
  (PRJ-105) –, bei jeder Änderung, auf welchem Weg auch immer: Formulare,
  API, Automationen, Importe, Statuswechsel, der Dialog der Wiedervorlage.
  GET /projects und /projects/{id} nennen diese Zeiten im Objekt
  field_changed_at. PATCH /projects/{id} nimmt freiwillig changed_at an
  (ISO 8601 mit Zeitzone): Jedes gesendete Feld gilt nur, wenn dieser
  Zeitpunkt später liegt als der gespeicherte des Feldes; bei Gleichstand
  gilt der Server, ein Zeitpunkt in der Zukunft zählt als jetzt (Regel für
  die Uhren, PCK-027). Vergleich und Schreiben geschehen gesperrt in einem
  Schritt (API-010). Dasselbe gilt für POST /projects/{id}/status und für
  PUT und DELETE /projects/{id}/follow-up; ein Statuswechsel, der beim
  Eintreffen nicht mehr erlaubt ist, wird mit 409 und dem aktuellen Projekt
  abgewiesen. Die Antwort ist immer das Projekt, wie es jetzt ist, mit
  applied, der Liste der übernommenen Felder. Ohne changed_at gilt
  If-Match (API-010). Je Feld gilt als Zeitpunkt
  der letzte Eintrag
  im Änderungsprotokoll, der es wirklich geändert hat, sonst die Anlage des
  Projekts – für Projekte und Servicefälle gleich. Die App erkennt die
  Unterstützung an field_changed_at; bis dahin ändert sie Projekt, Status
  und Wiedervorlage nur online. Servicefälle sind Projekte: Für sie gilt
  derselbe Mechanismus (PRJ-114). In der App MUSS:
  Die Zeiten setzt das Speichern des Projekts an einer Stelle, für
  jeden Weg; follow_up steht für Tag, Uhrzeit, Notiz und Person der
  Wiedervorlage, und auch die übrigen Felder, die PATCH ändern kann, haben
  eine Zeit. Die Einsatzsicht nennt die Zeiten nur der Felder, die sie
  zeigt.
- PRJ-114 [MUSS · V · S8] Status eines Servicefalls mit Änderungszeit (aus
  den Anforderungen der mobilen App; Entscheidung des Auftraggebers: die jüngere Änderung gewinnt): Ein Servicefall (PRJ-090)
  merkt sich, wann sein Status zuletzt geändert wurde, bei jeder Änderung,
  im Browser, über die API und durch Automationen (ADM-013). GET
  /service-cases und /service-cases/{id} nennen den Zeitpunkt als
  case_status_changed_at. PATCH /service-cases/{id} nimmt ihn freiwillig an
  (ISO 8601 mit Zeitzone): Der Status gilt dann nur, wenn dieser Zeitpunkt
  später liegt als der gespeicherte; Gleichstand, Zeitpunkte in der Zukunft
  und die Sperre wie bei PRJ-113. Die Antwort ist immer der Fall, wie er
  jetzt ist. Es ist der Mechanismus
  von PRJ-113 für das Feld des Status, unter dem Namen, den die App
  erwartet; field_changed_at gibt es auch am Servicefall. Der Startwert
  ist der von PRJ-113. Die App erkennt die Unterstützung am
  Feld; bis dahin ändert sie den Status nur online. In der App MUSS:
  case_status_changed_at beurteilt Status, Grund des
  Wartens und die Wiedervorlage dazu als Einheit, sodass ein Status, der
  eine Wiedervorlage verlangt (PRJ-112), nie halb übernommen wird; ein 409
  gibt es beim Servicefall nicht, weil jede Folge der Status erlaubt ist.


Ausbaustufe 8: Weitere Anforderungen

- PRJ-115 [SOLL · V · S8] Profitabilität im Blick: Der
  Eintrag "Auswertungen" der Navigation zeigt unter "Profitabilität"
  Umsatz netto (Material und Personal), die Kosten der Zumietungen und des
  Personals, die freigegebenen Spesen und was bleibt ("Gewinn aus dem
  Projekt", PRJ-025, PRJ-087) mit der Marge in Prozent – im Ganzen, je
  Monat (als Balken), je Kunde und je Projektleitung, dazu die Projekte mit
  dem meisten und dem wenigsten Übrig. Umsatz, Gewinn und Marge
  heißen ausdrücklich "kalkuliert" (auch beim Ertrag je
  Produkt und Exemplar): Sie stammen aus der Preisplanung, nicht aus
  ausgestellten Rechnungen, Zahlungen oder gebuchten Ausgaben. Es zählen ganze Projekte mit ihren
  Teilprojekten, ab "Bestätigt – Einzelheiten offen", nicht storniert, im Monat
  der Rückkehr ihres Materials; Servicefälle nicht. Gewählt werden ein Jahr
  oder ein Zeitraum, auf Wunsch nur abgeschlossene Projekte; die Projekte
  gibt es als CSV. Unter "Material" steht je Produkt, was seine Exemplare
  gekostet und seine Positionen eingebracht haben (MAT-053). Die Seiten
  sieht, wer das Modul "Auswertungen" (AUT-014) und alle Projekte lesen
  und Preise sehen darf; Kosten der
  Zumietung nur mit dem Recht für Einkaufspreise, die des Personals nur mit
  dem für Personalkosten, was bleibt nur mit beiden (AUT-019). Gespeichert
  wird nichts: Die Zahlen kommen aus derselben Kalkulation wie die Summen
  der Projektliste (PRJ-085). API: /reports/profitability und
  /reports/material.

Ausbaustufe 9: Weitere Anforderungen

- PRJ-116 [SOLL · A · S9] Erste Annahme für eine neue Phase: Auf
  der Seite "Zeitplanung" und im Dialog "Neue Phase …" (PRJ-094) beginnt eine
  neue Phase mit dem Zeitraum, der im Formular des Personals oder der Logistik
  steht, wenn er vom Mietzeitraum abweicht; sonst dort, wo die letzte Phase im
  Mietzeitraum endet, ohne sie mit dem Beginn des Mietzeitraums. Reicht der so
  gefundene Zeitraum über mehr als einen Tag, dauert die Phase zunächst
  höchstens acht Stunden (PRJ-124).
- PRJ-117 [SOLL · V · S9] Mehrere Personalpositionen auf einmal: Personalpositionen lassen sich wie
  Materialpositionen (PRJ-082) ankreuzen. Die Leiste setzt im Dialog
  Treffpunkt, Notiz, Phase, Von und Bis, geplante Stunden, Fahrzeug und mit
  Preisrecht den Rabatt für alle gewählten Positionen (leere Felder bleiben,
  wie sie sind), plant fest ein (PER-041), fragt an oder löscht. Jede Position
  folgt den Regeln und Rechten der Einzeländerung; übergangene werden mit
  Grund genannt. Ohne JavaScript ist der Dialog eine eigene Seite. API: POST
  /projects/{id}/crew-lines/bulk.
- PRJ-118 [SOLL · V · S9] Nachricht bei Änderung des Einsatzes (siehe PER-041):
  Die eingeplante Person erfährt, wenn
  sie fest eingeplant wird, wenn sich Zeiten, Treffpunkt, Notiz, Phase,
  Funktion oder Fahrzeug ihrer Position ändern – mit dem Wert vorher – und
  wenn sie ausgeplant wird. Eine Nachricht je Person und Aktion, auch für
  mehrere Positionen, eine verschobene Phase oder einen verschobenen
  Mietzeitraum samt Ablauf (VFG-026; die Nachricht "neuer Zeitraum" bekommt
  die Crew dann nur, wenn ihr sonst nichts gesagt wurde). Keine Nachricht über
  die eigene Änderung, ohne aktives Konto, bei abgesagten, vergangenen oder
  stornierten Einsätzen; wird wegen neuer Zeiten erneut angefragt (PER-034),
  nennt die Anfrage die Änderungen. Die Art der Benachrichtigung "Änderung
  meines Einsatzes" ist je Nutzer abschaltbar.

Ausbaustufe 9: Weitere Anforderungen

- PRJ-119 [SOLL · V · S9] Verwandte Projekte und Servicefälle: Ganze Projekte und Servicefälle können mit beliebig vielen anderen
  verwandt sein, in beide Richtungen, mit optionaler Notiz. Der Kasten
  "Verwandt" im Überblick und auf der Seite des Servicefalls zeigt Nummer,
  Name, Art, Status und Link; ohne Zugriff nur "Projekt 2027-0042 (kein
  Zugriff)". "Verknüpfen" (Suche nach Nummer oder Name) und "Lösen" brauchen
  Bearbeiten-Zugriff hier und Lese-Zugriff dort; beide Verläufe vermerken es.
  Duplizieren übernimmt keine Verwandtschaften, die Umwandlung eines
  Servicefalls behält sie. API: /projects/{id}/relations; die App bekommt
  "related". Der Kasten "Verwandt" ist klein und dezent: eine
  Überschrift und eine Zeile je Verwandtem statt Tabelle in einem Rahmen;
  "Verwandtes eintragen" klappt das Formular erst auf Wunsch auf.
- PRJ-120 [SOLL · V · S9] Personal je Phase nach Funktion:
  "Personal für diese Phase" fragt erst nach Funktionen mit Plätzen, dann je
  Platz nach der Person – Vorschläge der Personen mit der Funktion, mit
  Hinweis auf Konflikte zur Zeit der Phase; leere Plätze bleiben offen. Die
  offenen Plätze der Phase sind vorbelegt und werden zuerst besetzt. Ohne
  JavaScript in zwei Schritten. Eine neue Phase kann "Personalplätze" nennen;
  beim Speichern entstehen so viele offene Plätze mit ihrem Zeitraum (auch im
  Dialog "Neue Phase …" der Planung, deren Personal sich sofort aktualisiert).
  API: places, …/staffing.
- PRJ-121 [SOLL · V · S9] Personen im Zeitstrahl der Zeitplanung ziehen: Personen und offene Plätze lassen
  sich im Zeitstrahl der Zeitplanung ziehen (Maus, Pfeiltasten), mit demselben
  Dialog und Recht wie Phasen (VFG-026). Ist die Person die einzige ihrer
  Phase, wird die Phase mit offenen Plätzen und Fahrzeugen mitverschoben –
  reicht sie dann über den Mietzeitraum hinaus, fragt der Dialog wie bei
  PRJ-100 –, sonst die offenen Plätze ihrer Funktion mit gleichen Zeiten. Der
  Dialog sagt, was warum mitgeht, und lässt es abwählen. Je Person eine
  Nachricht (PRJ-118). API: follow.

Ausbaustufe 9: Weitere Anforderungen

- PRJ-122 [SOLL · V · S9] Kundenname in jeder Rolle:
  Wer ein Projekt oder einen Servicefall sehen darf, sieht den Namen des
  Kunden – in den Listen, auf den Seiten, auf der Packliste, in der API
  (customer_name) und in der Suche nach dem Namen –, auch ohne das Recht,
  Kunden zu lesen und auch als Crew oder freie Kraft. Zum Link wird der Name
  nur mit dem Recht, Kunden zu lesen. Alles Weitere der Kundenseite bleibt
  beim Recht: Ansprechpartner, Telefon und Mail, wer einen Servicefall
  gemeldet hat, die Seite des Kunden und die Liste seiner Projekte. Die
  Kalender und das Einsatz-PDF (AUT-023) zeigen weiter keinen Kunden.
- PRJ-123 [SOLL · V · S9] Gesamtrabatt im Projekt: Ein Projekt hat
  einen Gesamtrabatt, in Prozent (0 bis 100) oder als Betrag in Euro, nie
  beides; "Gesamtrabatt setzen" und "Gesamtrabatt ändern" unter den Summen der
  Preisplanung, mit dem Preisrecht und solange das Projekt änderbar und
  planbar ist. Er wird zuletzt abgezogen: von der Netto-Summe nach Zuschlägen,
  Rundung und Mindestmiete – ein Betrag höchstens bis zur Summe, kein Rabatt
  bei einer Summe von 0 oder weniger. Die Summen zeigen "Summe vor dem
  Gesamtrabatt" und "Gesamtrabatt"; die Steuer folgt anteilig (die
  Steuerzeilen der Rechnung, XRechnung und DATEV tragen ihn über die
  Nachlässe), Rechnung und Angebot führen ihn als eigene Zeile "Gesamtrabatt
  10 %". Er gilt je Projekt – Teilprojekte haben ihren eigenen, ein
  Gesamtprojekt zeigt je Projekt eine Zeile – und zählt nicht zu den Rabatten
  je Position (PER-026 und der Höchstrabatt je Produkt gelten nur dafür); in
  der Nachkalkulation wird er nicht auf einzelne Positionen verteilt.
  Duplizieren übernimmt ihn für den, der das Preisrecht hat (eine Kopie ohne
  Material, Personal und Fahrzeuge bekommt keinen); Aufteilen übernimmt ihn
  immer, damit sich kein Preis ändert – ein Prozentsatz in jeden Teil, ein
  Betrag anteilig nach den Summen der Teile (der Rest in Cent bleibt beim
  Gesamtprojekt). Ohne Preisrecht sieht man ihn nicht. Änderungen stehen im
  Verlauf. API: overall_ discount_percent und overall_discount_amount am
  Projekt; totals mit net_before_overall_discount und overall_discount. Es
  kann statt Prozent oder Betrag auch ein Zielbetrag netto oder
  brutto nach dem Rabatt eingegeben werden: Rentalars berechnet den
  Prozentsatz (bis zu sechs Nachkommastellen) nach der Steuerrechnung des
  Projekts, zeigt vorab Prozentsatz und Summen und speichert den Prozentsatz;
  ein später geänderter Projektstand rechnet ihn nicht neu. Lässt sich ein
  Bruttobetrag nicht auf den Cent erreichen, gilt der nächste und die Planung
  sagt es. API: POST projects/{id}/overall-discount mit percent, amount,
  target_net, target_gross und dry_run (NaN, Infinity und Zahlen außerhalb des
  Wertebereichs geben 400). Die Belege, die Preisübersicht und die CSV-Datei
  drucken den Prozentsatz mit bis zu sechs Nachkommastellen, ohne überflüssige
  Nullen ("19,99994 %", "10 %"), sodass der gedruckte Prozentsatz den gedruckten
  Rabatt auf den Cent ergibt; über etwa einer Million Euro netto erreicht ein
  Zielbetrag den Cent nicht mehr genau.

Ausbaustufe 9: Weitere Anforderungen

- PRJ-124 [SOLL · V · S9] Phasen höchstens acht Stunden: Eine neue Phase dauert zunächst höchstens acht Stunden ab dem
  Beginn und reicht nicht über das Ende des Mietzeitraums hinaus; ist der
  Mietzeitraum kürzer, endet sie mit ihm (PRJ-116). Nur ein Startwert: Wer
  mehr einträgt, in der Seite, im Dialog oder in der API, bekommt die längere
  Phase. Ein eingegebener Zeitraum über mehrere Tage dauert zunächst eine
  Stunde.
- PRJ-125 [SOLL · V · S9] Überblick als erster Reiter: Der Reiter "Überblick" steht bei Projekten wie bei
  Servicefällen an erster Stelle (PRJ-104). Wer ein Projekt aus einer Liste,
  der Suche, einem Kalender oder einer Verknüpfung öffnet, landet auf dem
  Überblick (/projects/{id}/overview/); die Planung behält ihre Adresse,
  ebenso Rücksprünge nach Aktionen in der Planung.
- PRJ-126 [SOLL · V · S9] Produktnummer in der Planung klickbar: Die Produktnummer einer Position
  führt zur Seite des Produkts, für den, der Produkte lesen darf; ebenso im
  Titel des Dialogs der Position. Der Kasten "Verfügbarkeit" ist dann auf den
  Mietzeitraum des Projekts voreingestellt, mit dem Hinweis "Zeitraum des
  Projekts …" und einem Link zurück; ein selbst eingegebener Zeitraum geht
  vor. Ungültige Angaben und Projekte ohne Zugriff werden ignoriert.
- PRJ-127 [SOLL · V · S9] Veranstaltungsende nach "Material zurück bis": Endet die Veranstaltung nach
  "Material zurück bis" (PRJ-005), warnt Rentalars – im Projektformular schon
  beim Tippen, nach dem Speichern, beim Verschieben im Zeitstrahl und in der
  API (warnings); gespeichert wird trotzdem. Servicefälle sind ausgenommen.
- PRJ-128 [SOLL · V · S9] Textposition: Eine Textposition trägt nur einen Text, ohne Produkt, Menge,
  Preis, Rabatt und Zeitraum (PRJ-017). Sie lässt sich wie jede Position
  verschieben, kopieren, in Gruppen legen und löschen und steht in der
  Planung, in Angeboten, Auftragsbestätigungen, Rechnungen und der
  Preisübersicht (Seite, PDF, CSV) als Textzeile ohne Betrag. Sie zählt
  nirgends mit: nicht in Summen, Steuer, Packliste, Verfügbarkeit,
  Nachkalkulation, XRechnung und DATEV. API: is_text an den Positionen, nur
  beim Anlegen.
- PRJ-129 [KANN · V · S10] Planung zum Ausprobieren: Die Planung eines Projekts lässt sich zeitweise
  ausprobieren und dann übernehmen oder verwerfen, ohne dass das direkte
  Speichern entfällt. Festgehalten, nicht gebaut: Jede Aktion der Planung
  steht sofort in der Datenbank; ein Entwurf müsste alle Aktionen und die
  Verfügbarkeitsprüfung zwischenhalten. Als Alternative gilt ein gesicherter
  Planungsstand, auf den man zurücksetzen kann. Der
  Anwender hat ausdrücklich zurückgestellt, die Planung mit einem Schalter für das
  automatische Speichern zu versehen; in der
  Standardeinstellung ändert sich nichts, nichts davon ist gebaut.

Ausbaustufe 10: Weitere Anforderungen

- PRJ-130 [SOLL · V · S10] Import alter Projekte aus Rechnungen: Buchhaltung → Altprojekte
  importieren: bis zu 30 eigene Ausgangsrechnungen vergangener Projekte als
  PDF (höchstens 10 MB je Datei, 120 MB je Stapel). Jede wird im Hintergrund
  gelesen – mit KI (nur der Text geht an den Anbieter, MAT-062) oder, wenn sie
  aus ist, mit Mustern: Kunde, Rechnungsnummer, Datum, Leistungszeitraum,
  Veranstaltung, Ort, Positionen, Summen. Das Ergebnis ist nur ein Vorschlag
  in einer änderbaren Vorschau mit Warnungen (Summen und Steuer, doppelte
  Nummer, Nummer im Bereich der laufenden Folge); der Kunde wird einem
  bestehenden zugeordnet oder erst nach Bestätigung neu angelegt, Positionen
  können Produkten zugeordnet werden, sonst werden es freie Zeilen. Erst die
  Übernahme nach der Bestätigungsseite, die genau zeigt, was entsteht, legt je
  Rechnung ein abgeschlossenes Projekt mit einem historischen Rechnungsbeleg
  an (Nummer, Datum, Summen, Status "bezahlt" wählbar, Original-PDF
  angehängt); mehrere Rechnungen lassen sich zu einem Projekt zusammenfassen,
  ein Stapel teilweise bestätigen. Der Import versendet nichts, legt keine
  Aufgaben und Reservierungen an, berührt die Verfügbarkeit nicht, löst keine
  Automationen oder Webhooks aus und verändert nicht die laufende
  Rechnungsnummer; dieselbe Datei und dieselbe Nummer eines Kunden werden
  vorab erkannt. Die Projekte tragen "Importiert aus Rechnung … am … von …",
  heißen ALT-Jahr-Nummer, und der Import lässt sich 7 Tage zurücknehmen, wenn
  nichts geändert wurde. Historische Belege sind weder buchbar noch
  stornierbar und kommen in den DATEV-Export nur mit "historische Belege
  einschließen" (Standard aus). Hochgeladene PDFs werden nach 14 Tagen
  entfernt, soweit sie nicht übernommen wurden. Nicht gelesen werden Scans,
  Fremdwährungen und Gutschriften. API: legacy-imports mit Vorschau,
  Bestätigen und Zurücknehmen. Jede
  Position übernimmt ihre Beschreibung (die weiteren Zeilen unter dem Namen,
  änderbar) und hat eine Art – Material, Personal oder Logistik –, aus Text und
  Einheit vorgeschlagen und änderbar. Personal wird eine Personalzeile ohne
  Person (nach Stunden, nach vollen Tagen oder als Pauschale) mit der Funktion
  als Dienstleistung, Logistik eine Fahrzeugzeile mit eigener Fahrt als
  Pauschale (ein Kraftfahrzeug des Fuhrparks), im Dokument unter Personal
  beziehungsweise Logistik. Zum Kunden sagt die Vorschau in einem Satz, ob ein
  vorhandener gefunden wurde (gleicher Name und gleiche Adresse, oder ein
  ähnlicher Name an gleicher Adresse), ob welche gemeint sein könnten oder ob
  ein neuer angelegt wird.

Ausbaustufe 10: Weitere Anforderungen

- PRJ-131 [SOLL · V · S10] Servicefall als PDF für den Kunden: Auf der Seite eines Servicefalls (Reiter
  "Überblick") erzeugt "PDF für den Kunden" ein Dokument mit dem Überblick –
  Nummer, Betreff, Status, Kunde, Verantwortliche, Zeitpunkt der Meldung,
  Beschreibung – und der Korrespondenz, aber nur den Nachrichten ohne Schloss
  (Richtung ein oder aus, Art normal) mit Absender oder Empfänger, Datum,
  Betreff, Text (je Nachricht auf 20.000 Zeichen gekürzt) und den Namen der
  Anhänge. Nicht enthalten sind Nachrichten mit Schloss, Notizen, automatische
  Antworten, Zustellfehler, offene Punkte, Beteiligte, Chat, Wiedervorlage und
  Preise; Kontaktperson und "Gemeldet von" nur, wenn der Nutzer Kunden sehen
  darf. Der Text steht in der Sprache der Firmendokumente. Wer Änderungsrecht
  am Fall hat und seine Korrespondenz lesen darf, darf es; die oder der
  Verantwortliche und die Beteiligten auch ohne das Modul "Projekte". API:
  POST /service-cases/{id}/customer-pdf.
- PRJ-132 [SOLL · V · S10] Ablage des PDFs unter "Dokumente": Das PDF wird sofort
  unter "Dokumente" des Servicefalls abgelegt (nicht für die Crew sichtbar), mit
  dem Zeitpunkt im Namen; jeder Aufruf macht eine neue Datei, frühere bleiben.
  Das Änderungsprotokoll des Falls hält fest, wann ein PDF gemacht wurde.
- PRJ-133 [SOLL · V · S10] Massenaktion Wiedervorlage bei Projekten: Die Liste der
  Projekte setzt für die gewählten Projekte eine Wiedervorlage (Datum und
  Uhrzeit, für wen, Notiz) oder nimmt sie weg. Jedes Projekt wird einzeln auf
  Recht geprüft; was nicht erlaubt ist, wird übersprungen und mit dem Grund
  genannt. API: POST /projects/bulk.
- PRJ-134 [SOLL · V · S10] Massenaktionen bei Servicefällen: Die Liste der
  Servicefälle setzt für die gewählten Fälle den Status (bei "wartend" mit dem
  Grund), die Wiedervorlage oder die zuständige Person oder nimmt die
  Wiedervorlage weg; wie PRJ-133 je Fall geprüft. API: POST /service-cases/bulk.
- PRJ-135 [SOLL · V · S10] Projektvorlagen inhaltlich bearbeiten: Jede
  Vorlage hat die Seite "Inhalt bearbeiten" (Projekte → Vorlagen → Name). Sie zeigt, was ein neues Projekt bekommt:
  Teilgruppen mit ihren Positionen, Personalplätze, Fahrzeugbuchungen, Phasen, offene Punkte, die Notizen und die
  voreingestellten Miettage. Jeder Eintrag lässt sich hinzufügen (Produkt, Freizeile, Textzeile, Gruppe, Personalplatz,
  Fahrzeugbuchung, Phase, offener Punkt), ändern, eine Stelle nach oben oder unten verschieben und löschen. Zeiträume
  stehen in Stunden ab dem Beginn des Projekts, auf Wunsch ab dem Ende (PRJ-095). Jede Änderung wird als Ganzes geprüft
  (Schachtelung und Tiefe der Gruppen, Gruppe und Alternative einer Position, Phase eines Platzes, PRJ-037, PRJ-080,
  PRJ-083): Rentalars speichert keine Vorlage, die sich nicht anwenden ließe. Eine gelöschte Gruppe gibt ihren Inhalt an
  die Gruppe darüber oder nimmt ihn mit (Rückfrage); löscht man etwas, das eine Alternative ersetzt, wird die Alternative
  zur optionalen Position. Preise (Rabatt und Pauschalpreis einer Gruppe, Preis einer Freizeile) liest und schreibt nur,
  wer Preise sehen darf. Hat jemand einen Eintrag inzwischen geändert oder gelöscht, meldet die Seite es, statt den
  falschen Eintrag zu treffen. Bereits angelegte Projekte ändern sich nicht. Recht: Projekte bearbeiten.
- PRJ-136 [SOLL · V · S10] API der Vorlageninhalte (API-014): /project-templates/{id}/content
  (GET liest, PUT ersetzt alles und prüft als Ganzes), …/content/notes (PUT), …/content/{abschnitt} (POST legt an,
  Antwort: der Schlüssel), …/content/{abschnitt}/{schlüssel} (PATCH ändert nur die gesendeten Felder, DELETE löscht,
  ?with_content=true bei einer Gruppe) und …/move (up oder down). Abschnitte: groups, lines, crew, vehicles, phases,
  open_items; offene Punkte haben keinen Schlüssel, sie werden nach Stelle und Text (expect) angesprochen. Dieselben
  Regeln wie die Seite; jede Operation hat Tests.
- PRJ-137 [SOLL · V · S10] Geänderte Produkte in Anfragen und Optionen: Jede Material-Position merkt sich neben dem Preis (PRJ-072)
  Name, Einheit, Steuersatz und Abrechnungsart (bei einem prozentualen Zuschlag auch den Prozentsatz, er ist sein Preis), die sie vom Produkt übernommen hat. In einer Anfrage, Option oder
  in "Bestätigt – Einzelheiten offen" (nicht in einem bestätigten Projekt) meldet Rentalars jede Abweichung: auf jeder Seite des Projekts als Hinweis mit Link, in der
  Planung als Liste mit alt und neu. "Änderungen übernehmen" stellt alle Positionen um, bei denen nichts von Hand geändert
  war; je Position gibt es "Übernehmen" und "Eigene Werte behalten". Menge, Zeitraum, Notiz und Rabatt bleiben. Bei
  Personal folgt nur der Preis des Dienstleistungsprodukts. Preise liest und übernimmt nur, wer Preise sehen darf (AUT-019);
  alles andere jeder, der das Projekt bearbeiten darf. Positionen, bei denen unbekannt ist, ob das Produkt oder die Position
  geändert wurde, gelten als von Hand gesetzt. Die Merkzettel stehen
  nicht im Verlauf der Position.
- PRJ-138 [SOLL · V · S10] Benachrichtigung bei geänderten Produkten: Speichert jemand ein
  Produkt – im Formular, über die API oder durch einen Import –, das in einer Anfrage, Option oder in
  "Bestätigt – Einzelheiten offen" abweicht, bekommen die
  Projektleitung und die Mitglieder mit Bearbeitungsrecht eine Benachrichtigung (Art "Produkt in einem noch nicht vollständig
  bestätigten Projekt geändert", einstellbar, nicht per E-Mail, wenn nicht eingeschaltet). Je Projekt eine, solange die letzte ungelesen
  ist und eine Stunde lang auch danach; ausgelöst nur, wenn sich etwas ändert, dem Positionen folgen (nicht beim
  Deaktivieren, Notizen, Kategorie); wer keine Preise sehen darf, erfährt von einer reinen Preisänderung nichts. Sie nennt keine
  Preise und führt zur Liste in der Planung.
- PRJ-139 [SOLL · V · S10] Geänderte Produkte von der Produktseite aus (API-014): Die
  Produktseite nennt die noch nicht vollständig bestätigten Projekte, in denen das Produkt veraltet ist (nur solche, die der Nutzer lesen
  darf, und deren Planung er lesen darf, AUT-016), mit den Unterschieden, und übernimmt sie je Projekt oder in allen Projekten, die er bearbeiten darf
  (Positionen mit Wert von Hand bleiben). Nach dem Speichern sagt eine Meldung, in wie vielen Projekten das Produkt
  nachzuziehen ist. API: /projects/{id}/product-changes (GET, POST) und /products/{id}/unconfirmed-projects (GET, POST);
  /projects/{id}/old-prices.
  Die API übernimmt Änderungen und Preise auch dort nicht in bestätigte Projekte (Fehler
  400); vereinbarte Preise bleiben (PRJ-015). Das gilt ebenso für /projects/{id}/old-prices.
- PRJ-140 [SOLL · V · S10] Neuer Ansprechpartner im Projektformular: Das Feld Ansprechpartner des Projektformulars (neues Projekt, Bearbeiten, Teilprojekt, Umwandeln eines
  Servicefalls; auch das Formular "Neuer Servicefall" und das Bearbeiten eines Servicefalls) zeigt als letzte Auswahl "+ Neuer Ansprechpartner …", sobald ein Kunde gewählt ist und wer das Formular
  benutzt Kunden ändern darf; bei einem anonymisierten Kunden fehlt sie. Die Auswahl öffnet einen Dialog (Anrede, Vorname, Nachname, Position, E-Mail, Telefon; der
  Nachname ist Pflicht), der den Ansprechpartner beim Kunden anlegt; danach ist er im Feld gewählt, ohne dass die Seite neu
  lädt und ohne dass Eingaben verloren gehen. Der erste Ansprechpartner eines Kunden wird sein Hauptansprechpartner (KND-004);
  Gruß und Hauptansprechpartner pflegt die Seite des Kunden. Die Auswahl selbst ist kein Wert: Ohne Skript abgeschickt,
  meldet das Formular einen Fehler am Feld, statt das Projekt ohne Ansprechpartner zu speichern. Dieselbe Person (Name und
  E-Mail) wird nicht doppelt angelegt.


### 5.7 Verfügbarkeit und Disposition (VFG)

Berechnung Material

- VFG-001 [MUSS · V · S1] Das System kennt die Verfügbarkeit jedes Produkts für
  jeden Zeitraum.
- VFG-002 [MUSS · A · S1] Berechnungsregel:
  Überfälliges Material (Projekt "ausgegeben", Ende überschritten) bleibt belegt, bis es
  zurückgebucht ist – auch für die Zeit nach der Anfrage.
Überlappende Sperrzeiten eines Exemplars zählen einmal; die Sperre gegen gleichzeitiges
  Buchen umfasst auch Behälter und ihren Inhalt; wer einen Einsatz abgesagt hat, gilt dafür nicht als verplant.

      frei(Produkt, Zeitraum) =
          einsatzfähiger Bestand im Zeitraum
        − höchste gleichzeitig reservierte Menge im Zeitraum

  Reserviert sind alle Materialpositionen anderer Projekte mit fester
  Reservierung, deren Zeitraum sich mit dem angefragten Zeitraum überschneidet.
  Maßgeblich ist die Spitze der gleichzeitigen Belegung, nicht die Summe aller
  Positionen.
- VFG-003 [MUSS · A · S1] Weiche Reservierungen (Status Option) werden getrennt
  ausgewiesen: "9 Bestand, 6 fest, 2 optional, 1 frei".
- VFG-004 [MUSS · A · S1] Zeiträume werden mit Datum und Uhrzeit verglichen.
  Ein Projekt, das um 10 Uhr zurück ist, blockiert kein Projekt, das um 14 Uhr
  beginnt.
- VFG-005 [MUSS · V · S1] Pufferzeiten vor und nach jedem Einsatz (Prüfen,
  Reinigen, Laden) sind einstellbar: global als Voreinstellung (0 Stunden, also
  kein Puffer) und abweichend je Kategorie oder Produkt. Im Puffer gilt das
  Material als belegt.
- VFG-006 [MUSS · A · S1] Defekte, gesperrte und ausgemusterte Instanzen sowie
  Sperrzeiträume (MAT-024) mindern den Bestand im betroffenen Zeitraum.
- VFG-007 [MUSS · A · S1] Gleichzeitige Buchungen mehrerer Nutzer dürfen nicht
  zu unbemerkter Überbuchung führen (Prüfung und Speichern in einem
  abgesicherten Schritt).
- VFG-008 [MUSS · A · S1] Sets: Die Verfügbarkeit ergibt sich aus dem knappsten
  Bestandteil. Einzeln gebuchte Mengen eines Produkts und Mengen aus Sets
  werden zusammengerechnet.

Berechnung Personal

- VFG-009 [MUSS · V · S3] Das System kennt die Verfügbarkeit jeder Person für
  jeden Zeitraum (frei, eingeplant, abwesend).
- VFG-010 [SOLL · A · S3] Suche "wer ist im Zeitraum frei und hat Funktion X".

Ansichten

- VFG-011 [MUSS · A · S1] Verfügbarkeitsauskunft je Produkt: Bestand, Belegung
  und belegende Projekte im gewählten Zeitraum.
- VFG-012 [SOLL · A · S4] Zeitstrahl je Produkt bzw. Kategorie mit Auslastung.
  Die Seite heißt "Materialauslastung" (VFG-028, VFG-029).
- VFG-013 [SOLL · A · S4] Engpassliste: alle Fehlbestände der kommenden Wochen
  mit betroffenen Projekten.
- VFG-014 [SOLL · A · S4] Personalplan: Zeitstrahl je Person mit Einsätzen und
  Abwesenheiten.
- VFG-019 [SOLL · V · S5] Jedes Produkt, jedes Materialmodell und jedes
  Exemplar hat einen eigenen Zeitstrahl über wählbare Wochen: Projekte,
  Sperrzeiten und freie Zeiträume, beim Exemplar auch der Bedarf seines
  Produkts. So sind Verfügbarkeiten in Zeiträumen direkt zu sehen.
- VFG-015 [SOLL · V · S10] Vorschlag von Ersatzprodukten bei Fehlbestand
: Ist ein Produkt im Zeitraum knapp oder
  überbucht, nennt die Planung die Ersatzprodukte, die verfügbar sind, mit den
  Zahlen der Verfügbarkeit – diese nur, wer das Recht Verfügbarkeit hat
  (AUT-032). Gerechnet wird mit derselben Verfügbarkeitsrechnung wie überall
  (VFG-002), nicht daneben (PRD-023).

Besondere Fälle

- VFG-016 [MUSS · V · S1] Fest verbaute Exemplare mindern den freien Bestand
  ihres eigenen Produkts dauerhaft. Lose enthaltene und einzeln vermietbare
  Exemplare mindern ihn in den Zeiträumen, in denen ihr umgebendes Gerät
  verplant ist, sofern sie nicht herausgelöst wurden (MAT-036, MAT-042).
  Produkte ohne eigenen Bestand (PRD-030) werden nicht geprüft.
- VFG-017 [MUSS · A · S1] Geplant wird mit Produkten, nicht mit Exemplaren. Für
  die Regel aus VFG-016 gilt deshalb: Je verplantem Stück eines Produkts gilt
  der Inhalt eines seiner Exemplare als belegt. Haben die Exemplare
  unterschiedlichen Inhalt, rechnet das System vorsichtig mit dem
  umfangreichsten, bis ein Exemplar zugeordnet ist. Bei Einzelstücken ist der
  Inhalt eindeutig.
- VFG-018 [MUSS · V · S2] Eine durch Zumietung gedeckte Menge belastet den
  eigenen Bestand nicht: Reserviert wird nur der Teil einer Position, der aus
  eigenem Bestand kommt. Andere Projekte und die Engpassliste rechnen mit
  dieser verminderten Menge.

Weitere Anforderungen

- VFG-020 [SOLL · V · S5] Im Monatskalender ist ein mehrtägiges Projekt ein
  durchgehender Balken, der in der nächsten Woche weiterläuft. Die
  Statusfarbe ist deutlich, und eine Legende erklärt die Farben.
- VFG-021 [SOLL · V · S5] Die Wochenansicht des Kalenders ist ein
  Stundenraster wie in gängigen Kalender-Apps: eine Spalte je Tag,
  Ganztägiges oben, Kürzeres zu seiner Uhrzeit, Gleichzeitiges nebeneinander
  und eine Linie für die aktuelle Uhrzeit.
- VFG-022 [SOLL · V · S5] Zeitstrahl und Personalplan lassen sich auch als
  Tag, 2 Tage und 3 Tage mit Stundenspalten zeigen. Seitliches Scrollen bis
  zum Rand lädt den nächsten oder vorigen Zeitraum nach.
  Es sind 1 bis 10 Tage wählbar (VFG-024).
- VFG-023 [SOLL · V · S5] Im Personalplan steht je Person oben ihre
  Verfügbarkeit (PER-021, Abwesenheiten), darunter ihre Einsätze.
  Doppelbelegung, Einsatz während einer Abwesenheit und Einsatz trotz
  "nicht verfügbar" sind deutlich markiert. Im Plan stehen die Personen mit
  einer Funktion (PER-025) und alle, die im Zeitraum eingeplant sind. Ohne
  den Haken bei "Nur
  Personen mit Einsätzen oder Abwesenheiten" stehen alle aktiven Personen im Plan.
  Der Haken zeigt nur, wer im
  Zeitraum Einsätze oder Abwesenheiten hat. Diese
  Konflikte sind rot ausgefüllt, alle Verfügbarkeiten
  schraffiert, und beim Darüberfahren steht die genaue Zeit (VFG-032).

Weitere Anforderungen

- VFG-024 [SOLL · V · S6] Zeitstrahl und Personalplan zeigen wahlweise
  "Wochen" – eine bis zwölf, Tag für Tag – oder "Tage": 1 bis 10 Tage mit
  Stundenspalten, bei einem Tag je Stunde, bei 2 und 3 Tagen je zwei, bei 4
  und 5 Tagen je drei, ab 6 Tagen je sechs Stunden. Die Zahl der Tage bleibt
  für die Sitzung erhalten. Jeder Balken steht genau zu seiner Zeit, auch in
  der Wochenansicht: Ein Aufbau von 14 bis 20 Uhr füllt nur diesen Teil des
  Tages, eine Phase über Mitternacht beginnt und endet zu ihrer Uhrzeit.
  Das gilt auch für die
  Materialauslastung (VFG-029); voreingestellt sind 4 Tage, und auch die Wahl
  zwischen Tagen und Wochen bleibt bis zum Abmelden erhalten (VFG-028).
- VFG-025 [SOLL · V · S6] In der Materialauslastung (VFG-012) schlägt das Feld
  für Name oder Artikelnummer schon beim Tippen passende Produkte mit Bestand
  vor, wählbar per Klick oder mit Pfeiltasten und Enter; die Seite zeigt dann
  genau dieses Produkt. Enter bei geschlossenen Vorschlägen sucht
  alle Produkte, deren Name oder Artikelnummer den Text enthält.
- VFG-026 [SOLL · V · S8] In der Ansicht "Tage" von Planung → Zeitstrahl
  (VFG-024) und im Zeitstrahl der Zeitplanung (PRJ-103) lassen sich Phasen
  und die Zeiträume eines Projekts durch Ziehen verschieben, in Schritten
  von 15 Minuten; wo es sinnvoll ist, ändert Ziehen an einem Ende die
  Dauer. Beim Loslassen zeigt ein Dialog alte und neue Zeiten und fragt
  nach. Danach folgt, was auch beim Ändern im Formular folgt: Das Personal
  der Phase wandert mit (PRJ-080), angefragte Personen werden neu angefragt
  (PER-034), über den Mietzeitraum hinaus schlägt Rentalars das Erweitern
  vor (PRJ-100), und neue Fehlbestände werden genannt. Es gibt einen Weg
  mit der Tastatur. Ziehen kann nur, wer das Projekt bearbeiten darf, und
  nur bei Projekten, die sich noch ändern lassen. Ebenso lassen
  sich die Einsätze im Personalplan ziehen (VFG-031).

Ausbaustufe 7: Weitere Anforderungen

- VFG-027 [SOLL · V · S7] Im Personalplan und im Zeitstrahl einer Person
  (PER-020) sind die Einsätze in den Farben der Legende hinterlegt und tragen
  links einen breiten Farbstreifen: orange fest (das Projekt ist bestätigt,
  auch unterwegs, wieder im Lager oder abgeschlossen), gelb Option, grau
  Projekt-Anfrage. Ist die Person angefragt und hat noch
  nicht geantwortet, ist der Balken blasser und der Streifen gestrichelt.
  Alle Markierungen der Zeitstrahlen – Balken, Verfügbarkeit,
  Abwesenheiten und die Muster der Legende – sind größer und kräftiger; im
  Zeitstrahl der Projekte sind die Balken wie im Kalender farbig hinterlegt.
- VFG-028 [SOLL · V · S7] Die Reiter der Planung stehen in der Reihenfolge
  Kalender, Zeitstrahl, Materialauslastung, Personalplan, Fehlbestände. Der Kalender öffnet mit der
  Woche, und "Woche" steht vor "Monat" (PRJ-067). Zeitstrahl,
  Materialauslastung und Personalplan öffnen mit 4 Tagen in Stundenspalten; ob
  Tage oder Wochen und wie viele Tage gewählt sind, gilt bis zum Abmelden für
  alle drei. Links mit einem Monat oder einer Woche zeigen, was sie
  nennen. Als letzter Reiter folgt "Wiedervorlagen"
  (VFG-034).
- VFG-029 [SOLL · V · S7] Die Materialauslastung (VFG-012) hat dieselbe
  Zeitansicht wie Zeitstrahl und Personalplan (VFG-024): "Tage" – 1 bis 10
  Tage in Stundenspalten – oder "Wochen" – 1 bis 12, Tag für Tag –, mit
  demselben Umschalter und demselben Blättern. Eine Stundenspalte nennt, wie
  viele Stück eines Produkts in dieser Zeit höchstens fest reserviert sind,
  klein dahinter, was Optionen zusätzlich nähmen (VFG-003). Benachbarte
  Spalten mit denselben Zahlen sind ein Feld, das beim Darüberfahren seinen
  Zeitraum nennt.

Ausbaustufe 7: Weitere Anforderungen

- VFG-030 [SOLL · V · S7] In den Zeitstrahlen – Planung → Zeitstrahl, die
  Zeitstrahlen je Produkt, Modell, Exemplar und Person (VFG-019, PER-020) und
  der Zeitstrahl des Projekts (PRJ-103) – hebt sich ein grauer Balken, etwa
  eines Projekts im Status Anfrage, deutlich vom grauen Hintergrund ab: durch
  Rand, Muster oder einen anderen Ton, im dunklen wie im hellen Modus, mit
  einem Kontrast von mindestens 3 zu 1 wie für Bedienelemente und Grafiken
  nach WCAG (NFA-025). Beschriftungen laufen nicht über andere Balken: Sie
  enden mit "…", und der Tooltip nennt den ganzen Text.

Ausbaustufe 8: Weitere Anforderungen

- VFG-031 [SOLL · V · S8] Im Personalplan lassen sich Einsätze – die
  Zeiträume von Personalpositionen – durch Ziehen verschieben, wie Phasen
  und Zeiträume im Zeitstrahl (VFG-026): in Schritten von 15 Minuten, mit
  einem Dialog, der alte und neue Zeiten und die Folgen nennt, und mit einem
  Weg über die Tastatur. Ziehen kann nur, wer das Projekt bearbeiten darf.
  Einen Einsatz auf eine andere Person zu ziehen, ist nicht verlangt.
- VFG-032 [SOLL · V · S8] Darstellung im Personalplan: Beim Darüberfahren
  nennen Verfügbarkeiten, Abwesenheiten und Einsätze nicht nur ihre Art,
  sondern auch ihre genauen Zeiten, etwa "9:00 Uhr bis 13:30 Uhr", auch für
  vorlesende Programme. Alle Arten der Verfügbarkeit sind schraffiert, auch
  "verfügbar" und "eingeschränkt verfügbar", damit klar ist, dass
  Schraffur Verfügbarkeit heißt. Konflikte – sich überschneidende Einsätze,
  ein Einsatz während einer Abwesenheit oder trotz "nicht verfügbar"
  (VFG-023) – sind rot ausgefüllt statt rot umrandet; sonst ist nichts rot
  ausgefüllt, sodass sie sofort auffallen und sich von "nicht verfügbar"
  unterscheiden. Die Legende sagt es, und dieselbe Kennzeichnung gilt in den
  anderen Zeitstrahlen, wo diese Konflikte erscheinen.
- VFG-033 [SOLL · V · S8] In allen Zeitstrahlen – Planung → Zeitstrahl,
  Personalplan, Materialauslastung, die Zeitstrahlen je Produkt, Modell,
  Exemplar und Person und der Zeitstrahl des Projekts – stehen in der
  Ansicht mit Tagen und Stunden (VFG-024) stündliche Trennlinien statt nur
  alle zwei Stunden, wenn die Breite des Bildschirms es hergibt, spätestens
  ab einer Fensterbreite von 1920 Pixeln. Die
  stündlichen Linien stehen bei jeder Breite, ab der sie erscheinen, genau
  an den Stunden der Spalten. Lässt sich das nicht genau erreichen,
  gilt die Darstellung mit einer Linie je Spalte. Ein Test im
  Browser misst die Lage der Linien bei mehreren Breiten. Die Linien liegen bei 1236 bis 1920 Pixeln auf 0,5 Pixel
  genau.
- VFG-034 [SOLL · V · S8] Die Planung hat als letzten Reiter
  "Wiedervorlagen" (VFG-028): alle Projekte und Servicefälle mit einer
  Wiedervorlage (PRJ-105) als Tabelle mit Tag, Uhrzeit (PRJ-109), für wen,
  Notiz, Projekt und Status. Filter wählen die eigenen, die fälligen und
  einen Zeitraum; Spalten, Sortierung und CSV sind wie in jeder
  tabellarischen Ansicht (UIX-015). Eine Wiedervorlage lässt sich dort
  erledigen oder verschieben wie im Projekt.

Ausbaustufe 8: Weitere Anforderungen

- VFG-035 [SOLL · V · S8] Der Zeitstrahl des Projekts im Reiter
  "Zeitplanung" (PRJ-103) zeigt das Personal wie der Personalplan: in den
  Farben der Anfrage – fest, Option, Anfrage, angefragt (VFG-027) –, mit
  schraffierten Verfügbarkeiten, wo sie gezeigt werden, rot ausgefüllten
  Konflikten und den genauen Zeiten beim Darüberfahren (VFG-032), unter
  derselben Legende. Die Zahl der Abfragen bleibt begrenzt, wie im
  Personalplan.

Ausbaustufe 8: Weitere Anforderungen

- VFG-036 [SOLL · V · S8] Meldung der Fehlbestände einstellbar:
  Wann Rentalars neue Fehlbestände meldet (UIX-005), ist
  eine Einstellung des ganzen Betriebs unter Einstellungen →
  Benachrichtigungen: die Uhrzeit (voreingestellt 4:15 Uhr), der
  Abstand – täglich, an Werktagen (Montag bis Freitag ohne die Feiertage unter
  Einstellungen → Zuschläge), einmal in der Woche an einem gewählten Wochentag
  oder nie – und der Vorlauf: Fehlbestände der Projekte, die innerhalb so
  vieler Wochen beginnen, 1 bis 26, voreingestellt vier; ein
  Fehlbestand ein Jahr vor dem Projekt wird so noch nicht gemeldet. Ein schon
  gemeldeter Fehlbestand wird je Fall einmal gemeldet, erneut nur,
  wenn er wächst oder nach seinem Verschwinden wiederkommt; wahlweise erinnert
  jede Prüfung an alle offenen ("Bekannte Fehlbestände bei jeder Prüfung
  erneut melden", voreingestellt an). Die Seite nennt
  die letzte Prüfung mit der Zahl der Meldungen und die nächste. Die Meldung
  kommt zur eingestellten Uhrzeit: Der Minuten-Zeitgeber
  der Aufgaben prüft im Hintergrund (run_jobs), ob eine
  Prüfung fällig ist, nicht das nächtliche Aufräumen; war der Server aus,
  holt er sie einmal nach. Die API kennt die Einstellungen
  (/settings/notifications). Die Seite Fehlbestände (VFG-013) und die Startseite zeigen
  Fehlbestände unabhängig davon. Eine Erinnerung je Projekt einige Tage
  vor seinem Beginn (UIX-028) ist KANN. Das ist voreingestellt an;
  bekannte Fehlbestände kommen dann als eine
  Erinnerung je Projekt und Prüfung ("Weiterhin Fehlbestände in …: 7
  Produkte", die Liste im Text), neue oder größer gewordene einzeln.

Ausbaustufe 9: Weitere Anforderungen

- VFG-037 [SOLL · V · S9] Sets in der Materialauslastung: Sets lassen sich wählen; ihre Zeile zeigt, wie viele komplette Sets
  im Zeitverlauf frei sind (gerechnet wie die Verfügbarkeit von Sets, Optionen
  als "−n"), und klappt die Bestandteile mit ihrer Auslastung und der Zahl je
  Set auf, auch ohne JavaScript. Das API /utilization liefert Sets mit ihren
  Bestandteilen.
- VFG-038 [SOLL · V · S9] Verfügbarkeit aller Personen: "Alle Personen,
  unabhängig von der Funktion" zeigt jede aktive Person, auch ohne Funktion;
  mit einer gewählten Funktion filtert die Liste (VFG-010). Ebenso
  das API /people/availability.

Ausbaustufe 9: Weitere Anforderungen

- VFG-039 [SOLL · V · S9] Phasen und Wiedervorlagen im Kalender: Über dem Kalender lässt sich ankreuzen, ob die Phasen der Projekte
  (Vorgabe: ja) und die Wiedervorlagen (Vorgabe: nein) erscheinen. Eine
  Wiedervorlage (PRJ-105) steht in der Woche zu ihrer Uhrzeit, ohne Uhrzeit im
  Ganztagsstreifen, im Monat unter ihrem Tag, mit Nummer und Notiz, und führt
  zum Projekt oder Servicefall; gezeigt werden nur die, die der Nutzer unter
  Planung → Wiedervorlagen sieht. Die Wahl steht im Link (?phases=,
  ?follow_ups=) und wird gemerkt.

Ausbaustufe 9: Weitere Anforderungen

- VFG-040 [SOLL · V · S9] Kalender-Link je Produkt, Modell und Exemplar: Produkte, Materialmodelle und Exemplare
  können je einen geheimen Kalender-Link (iCalendar, .ics) bekommen; im
  Standard hat keiner einen. Auf der Seite des Datensatzes und über die API
  wird er erstellt, durch einen neuen ersetzt oder deaktiviert – von dem, der
  das Modul schreiben und Verfügbarkeit und alle Projekte sehen darf; nur er
  sieht die Adresse, wer nur liest, sieht, dass ein Link aktiv ist.
  Fehlversuche mit falschen Adressen werden je Absender gezählt. Jede Änderung
  steht im Verlauf. Der Kalender zeigt, was der Zeitstrahl zeigt (VFG-019):
  Buchungen mit Projektnummer, Projektname, Status, Menge und Zeitraum, beim
  Exemplar seine Einsätze, Sperren und fälligen Prüfungen – 90 Tage zurück bis
  zwei Jahre voraus, ohne Preise, Kunden oder Kontaktdaten. Ein deaktiviertes
  Produkt oder ein ausgemustertes, verkauftes oder verlorenes Exemplar hat
  keinen Link mehr. API:
  /products|material-models|material-items/{id}/calendar-link (GET, POST,
  DELETE).


### 5.8 Packlisten, Ausgabe und Rücknahme (PCK)

Erstellung

- PCK-001 [MUSS · V · S1] Zu jedem Projekt lässt sich eine Packliste erstellen.
- PCK-002 [MUSS · A · S1] Die Packliste ergibt sich aus den Materialpositionen
  des Projekts und enthält je Zeile: Artikelnummer, Bezeichnung, Menge,
  Einheit, Notiz.
- PCK-003 [MUSS · A · S1] Ausgabe als druckbares PDF mit Projektkopf (Projekt,
  Kunde, Ort, Zeitraum, Projektleitung) und Feldern zum Abhaken.
- PCK-004 [SOLL · A · S5] Sortierung und Gruppierung wählbar: nach Teilgruppen
  (PRJ-014), nach Kategorie oder nach Lagerort (Laufweg im Lager).
- PCK-005 [MUSS · A · S1] Sets werden in ihre Bestandteile aufgelöst.
- PCK-006 [SOLL · A · S5] Summen für Gewicht und Volumen.
- PCK-007 [SOLL · A · S1] Preise erscheinen nie auf der Packliste.
- PCK-008 [SOLL · A · S5] Mehrere Packlisten je Projekt (z. B. je Teilgruppe,
  je Gewerk, je Fahrzeug oder je Ladetermin; künftig je Teilprojekt). Die
  Maske zum Bearbeiten
  oder Löschen einer Packliste ist aufgeräumt: Titel und Notiz sind gewöhnliche
  Textfelder wie überall, "Speichern" und "Packliste löschen" stehen als
  gleich große Knöpfe nebeneinander.

Digitales Packen

- PCK-009 [MUSS · V · S1] Packen durch Abhaken: Die Positionen der Packliste
  werden mit ihrer Menge abgehakt – in der Anwendung (auch mobil) mit
  Fortschrittsanzeige oder auf der gedruckten Packliste. Eine Zuordnung
  einzelner Exemplare ist dafür nicht nötig. Die
  Fortschrittsanzeige ist ein Balken, der zeigt, wo die Stücke sind (PCK-029).
- PCK-010 [SOLL · V · S10] Beim Packen lassen sich konkrete Exemplare per Scan
  zuordnen; der Scan bleibt freiwillig
  (PCK-020): Das Feld "Exemplar ist gepackt: ID scannen oder eintippen" wählt
  das Exemplar und zählt die Zeile hoch ("4 von 6", bei Produkten aus mehreren
  Stück je Produkt pro Stück, PRD-052). Das System prüft, ob das Exemplar zum
  geforderten Produkt gehört; ein doppelter Scan zählt nicht doppelt;
  gescannte Exemplare gehen bei der Ausgabe zuerst raus. Der Rückgabe-Scan
  gilt nur für Exemplare, die bei dieser Ausgabe zugeteilt waren; alles andere
  hakt man in der Zeile ab.
- PCK-011 [SOLL · V · S10] Warnung beim Scan:
  Ein defektes oder gesperrtes Exemplar oder eines, das für ein anderes
  Projekt gewählt oder unterwegs ist, wird abgewiesen und mit dem Grund
  genannt; eine überfällige Prüfung (MAT-032) warnt nur.
- PCK-012 [SOLL · A · S1] Mengenmaterial wird durch Eingabe der Stückzahl
  bestätigt.
- PCK-013 [SOLL · A · S5] Zusätzliches Material kann beim Packen ergänzt
  werden; es wird als Nachtrag im Projekt gekennzeichnet.
  Entscheidung des Auftraggebers zur Rolle Crew, 12.1: Material nachtragen
  darf nur, wer das Projekt bearbeiten darf oder Packen und Ausgabe für alle
  Projekte bearbeiten darf, nicht nur in zugeordneten – so behalten Lager
  und Projektleitung das Nachtragen. Die Crew packt in ihren eigenen Projekten alles, was keine
  finanzielle Wirkung hat – abhaken und scannen, Stücke wählen, ausgeben und
  zurücknehmen, Fehlteile klären, Defekte melden, Packlisten anlegen,
  umbenennen und löschen, Positionen verschieben, Übergaben buchen, Teile
  aus Behältern nehmen –, aber 1:1 nach der Packliste; an der Stelle des
  Nachtragens nennt ein Hinweis, wer es darf. Die API weist das Nachtragen
  ohne dieses Recht mit 403 und dem Code needs_project_write ab; der
  Abgleich der App lehnt eine gepackte Menge über der Packliste mit dem
  Grund needs_project_write bzw. above_packing_list ab und übernimmt die
  übrigen Änderungen (PCK-027); /offline/packlists nennt can_add_material.
  Das Update gibt der Rolle Crew das Schreiben bei Packen und Ausgabe, wenn
  sie noch Lesen hatte, und protokolliert jede eigene Rolle, die dadurch
  das Nachtragen verliert.
- PCK-014 [SOLL · A · S1] Packstatus je Projekt: offen, in Arbeit, gepackt,
  ausgegeben.
- PCK-015 [SOLL · A · S5] Ändern sich Materialpositionen nach Packbeginn,
  werden die Abweichungen auf der Packliste hervorgehoben.

Rücknahme

- PCK-016 [SOLL · A · S1] Rücknahme durch Abhaken, künftig auch per Scan;
  fehlende Instanzen bleiben offen und werden als Fehlteile ausgewiesen. Die
  Rücknahme wird wie die Ausgabe erst abgehakt und dann
  gebucht (PCK-028). Auch per Scan (PCK-010, MAT-027).
- PCK-017 [SOLL · A · S5] Bei der Rücknahme kann je Instanz ein Defekt gemeldet
  werden (MAT-023).
- PCK-018 [SOLL · A · S5] Teilausgaben und Teilrückgaben sind möglich. Es
  wird je Artikel ausgegeben, und das Projekt geht erst auf
  "Unterwegs", wenn alles ausgegeben ist (PCK-025). Auch
  die Rücknahme geht je Stück, im Wechsel mit weiteren Ausgaben (PCK-028).
- PCK-019 [SOLL · A · S1] Erst nach vollständiger Rücknahme oder
  ausdrücklicher Klärung der Fehlteile kann das Projekt den Status
  "Wieder im Lager" erhalten. Die Rücknahme einer
  Packliste ist abgeschlossen, sobald nach dem Buchen nichts mehr draußen ist und
  nichts mehr auf seine Ausgabe wartet; "Rücknahme abschließen" bucht zuerst,
  was abgehakt ist, und dient für geklärte Fehlteile und für einen Rest, der
  nicht mehr ausgegeben wird (PCK-028).
  Einzelstücke, die bei geklärten fehlenden Teilen nicht zurückkamen, werden beim Abschluss der
  Rücknahme gesperrt statt "verfügbar"; bei Mengenmaterial weist Rentalars darauf hin, den Bestand zu verringern,
  sonst bleiben die Stücke im Bestand.
- PCK-020 [MUSS · V · S1] Packen, Ausgabe und Rücknahme funktionieren
  vollständig auf Ebene von Produkt und Menge. Ein Scan oder die Auswahl eines
  Exemplars ist nie Voraussetzung: Drei Kabel lassen sich mit einem Haken
  ausgeben.
- PCK-023 [MUSS · V · S1] Nach der Ausgabe gilt ausgegebenes Material als
  "unterwegs", nicht als fehlend: Die Zeilen der Packliste bleiben neutral.
  Eine Zeile wird erst hervorgehoben, wenn ein Teil ihrer Menge zurück ist,
  und erst dann als Fehlteil mit der Frage nach dem Verbleib ausgewiesen,
  wenn die Rücknahme abgeschlossen werden soll und noch etwas fehlt
  (PCK-016, PCK-019).
- PCK-024 [SOLL · V · S1] Ein an der Position gewünschtes Modell oder Exemplar
  (PRJ-064) steht als Hinweis auf der Packliste, am Bildschirm wie im PDF.
  Ein gewünschtes Exemplar wird bei der Ausgabe vorrangig zugeordnet
  (PCK-021); ist es nicht greifbar, wird nichts blockiert.
- PCK-021 [MUSS · A · S1] Automatische Zuordnung: Hat ein Produkt genau ein
  einsatzfähiges Exemplar (typisch für Racks, Cases und Einzelgeräte) oder wird
  sein gesamter Bestand ausgegeben, ordnet das System die Exemplare von selbst
  zu.
- PCK-022 [SOLL · A · S5] Freiwillige Zuordnung: Wo es darauf ankommt, lässt
  sich ein Exemplar aus einer Liste wählen, später auch per Scan. Funktionen,
  die ein bestimmtes Exemplar brauchen – Mitausgabe des Inhalts (MAT-037),
  Prüfwarnung bei der Ausgabe (MAT-032), Einsatzhistorie (MAT-025) – greifen
  nur dann. Fehlt die Zuordnung, wird nichts blockiert. Auch
  per Scan (PCK-010).

Weitere Anforderungen

- PCK-025 [SOLL · V · S6] Ausgabe je Artikel: "Ausgeben" bucht nur, was
  abgehakt ist, mit den abgehakten Mengen; "Alles ausgeben" bucht nach einer
  Rückfrage jede Zeile mit voller Menge, etwa wenn auf Papier gepackt wurde.
  Nach einer Teilausgabe steht die Packliste auf "teilweise ausgegeben",
  nennt, was draußen ist und was fehlt ("14 von 63 Stück sind draußen"), und
  wird weitergepackt: Ganz ausgegebene Zeilen sind als "ausgegeben"
  gekennzeichnet, teilweise ausgegebene zeigen "4 von 6 ausgegeben". Das
  Projekt geht erst auf "Unterwegs", wenn alles ausgegeben ist – bei mehreren
  Packlisten jede mit Material aus dem Lager –, und auf "Wieder im Lager"
  erst, wenn nichts mehr unterwegs ist und nichts mehr auf seine Ausgabe
  wartet. Bis dahin behält es seinen Status; ausgegebenes Material gilt
  trotzdem als unterwegs, für die Verfügbarkeit wie auf der Startseite. Der
  Modus heißt "Packen/Ausgabe", und ausgegebenes Material ist
  unterwegs, bis seine Rücknahme gebucht ist (PCK-028).
  "Ausgabe rückgängig" gibt dem Projekt den Status zurück, den es vor der Ausgabe hatte (eine
  Option bleibt eine Option, nicht "bestätigt").


Begleit-App für Android

- PCK-026 [SOLL · V · S7] Die Packlisten aller bestätigten Projekte, die noch
  nicht abgeschlossen sind (Status "Bestätigt – Details offen", "Bestätigt",
  "Unterwegs"), lassen sich auf ein Telefon laden und dort ohne Netz abhaken:
  gepackt vor der Ausgabe, zurück während Material draußen ist – mit denselben
  Grenzen wie im Browser. Was abgehakt ist, geht von selbst an den Server,
  sobald er erreichbar ist (APP-003).
  GET /api/v1/offline/packlists liefert je Projekt id, number, name, status,
  start, end, venue, customer (der Name des Kunden; null bei nur der
  Einsatzsicht, AUT-023), can_write und die Packlisten wie in der Übersicht,
  dazu server_time in UTC. Es gilt die Regel für das Lesen einer Packliste,
  auch bei Rechten nur in zugeordneten Projekten.
- PCK-027 [SOLL · A · S7] Abgleich je Position nach der jüngeren Änderung: Der
  Server merkt sich je Position, wann die gepackte und wann die
  zurückgenommene Menge zuletzt geändert wurde. Eine Änderung aus der App
  trägt den Zeitpunkt, zu dem sie gemacht wurde, in der Zeit des Servers; sie
  gilt nur, wenn sie jünger ist als die letzte Änderung derselben Menge auf
  dem Server. Bei gleicher Zeit gilt der Server; ein Zeitpunkt in der Zukunft
  zählt als jetzt. Was die Packliste nicht mehr zulässt (inzwischen
  ausgegeben, Position entfallen), wird abgelehnt. Die App zeigt, welche
  Änderungen nicht übernommen wurden, und warum [A]. Jede Zeile der Packliste
  trägt packed_changed_at und
  returned_changed_at; beide ändern sich mit ihrer Menge, auf welchem Weg auch
  immer, und bleiben, solange die Menge gleich bleibt.
  POST …/packlists/{id}/sync nimmt höchstens 1000 Änderungen (line, product,
  field "packed" oder "returned", quantity, changed_at mit Zeitzone) und
  antwortet je Änderung in der Reihenfolge der Anfrage mit applied, older oder
  refused samt Grund, dazu mit der ganzen Packliste und server_time. Die
  Änderungen gelten nach ihrem Zeitpunkt geordnet, in einem Schritt und mit
  gesperrten Zeilen; was die Grenzen verletzt, wird abgelehnt, nicht
  angepasst. Ungültige Eingaben weist der Abgleich als Ganzes ab (400), ein
  Token nur zum Lesen bekommt 403. Er gibt nie aus und bucht keine Rücknahme:
  Was die App als zurück abhakt, bucht "Rücknahme buchen" im Browser
  (PCK-028). Zeitpunkte der Geräte tragen allein keine verlässliche Entscheidung
  (aus einer Code-Prüfung, Oktober 2026):
  - Jede Zeile trägt eine Versionsnummer des Servers, die mit jeder Änderung
    steigt, im Browser wie über die API. Eine Änderung aus der App kann
    nennen, auf welcher Version sie beruht (base_version), und eine eigene
    Änderungs-ID tragen; eine Änderung mit derselben ID wirkt nur einmal,
    eine Wiederholung ändert nichts.
  - Mit base_version entscheidet die Version: Hat sich die Zeile inzwischen
    geändert, ist das ein Konflikt, und die Antwort nennt für diese Zeile
    den Stand des Servers; keine Änderung geht stillschweigend verloren.
  - Ohne base_version – so sendet die Begleit-App – gilt die
    jüngere Änderung, aber eindeutig (Regel für die Uhren): Ein Zeitpunkt
    in der Zukunft zählt als die Zeit des Servers, behält aber seine
    Reihenfolge; sind zwei Zeitpunkte so gekürzt, entscheiden ihre
    ursprünglichen Zeitpunkte, dann die Reihenfolge des Eintreffens. Eine
    ältere Änderung überschreibt nie eine jüngere. Die
    Entwicklerdokumentation beschreibt die Regel.
  - Das Ereignis "zurück" der Webhooks (packing.returned, API-012) geht
    nur hinaus, wenn die zurück abgehakte Menge steigt – wie im Browser.
  - Der Abruf der Packlisten für das Telefon (GET, PCK-026) schreibt
    nichts. Fehlende Packlisten legt Rentalars dort an, wo Daten
    geschrieben werden, sodass die App jede Packliste ohne Netz
    erreicht [A].

Ausbaustufe 7: Weitere Anforderungen

- PCK-028 [SOLL · V · S7] Teilrücknahme je Stück: Die Rücknahme geht wie die
  Ausgabe (PCK-025). Der Modus zum Packen heißt "Packen/Ausgabe"; daneben
  steht "Rücknahme", sobald etwas ausgegeben ist. Dort wird abgehakt, was
  zurück ist – "Alles ist zurück" hakt alles ab –, und "Rücknahme buchen"
  bucht das Abgehakte, auch während der Rest noch gepackt und ausgegeben wird;
  Ausgabe und Rücknahme wechseln sich beliebig ab. Es gilt je Stück: Was
  zurückgenommen ist, ist für das Projekt erledigt und wird darin nicht noch
  einmal ausgegeben; was noch nicht ausgegeben war, lässt sich weiter packen
  und ausgeben. Bei 10 geplanten, 6 ausgegebenen und 4 zurückgenommenen Stück
  sind diese 4 erledigt, 4 lassen sich noch ausgeben, und 2 sind noch draußen.
  Zurückgenommenes ist sofort frei für andere Projekte. Ein Exemplar ist
  wieder "verfügbar", sobald seine Zeile ganz zurückgenommen ist, und wird im
  selben Projekt weder von selbst noch auf Wahl (PCK-021, PCK-022) noch einmal
  zugeordnet. Ist nach dem Buchen nichts mehr draußen und wartet nichts mehr
  auf seine Ausgabe, ist die Rücknahme abgeschlossen (PCK-019);
  "Rücknahme abschließen" dient für geklärte Fehlteile und für einen Rest,
  der nicht mehr ausgegeben wird.
- PCK-029 [SOLL · V · S7] Der Balken über der Packliste zeigt, wo die Stücke
  sind, und füllt sich von links: orange zurückgenommen (oder an ein anderes
  Teilprojekt übergeben, PRJ-060), orange schraffiert als zurück abgehakt,
  grün ausgegeben und draußen, grün schraffiert gepackt und noch nicht
  ausgegeben, grau im Lager. Darunter steht dasselbe in Worten und Zahlen.
  Das Gesamtprojekt zeigt denselben Balken je Teilprojekt.
- PCK-030 [SOLL · V · S7] Hat ein Gesamtprojekt Teilprojekte, stehen über
  jeder seiner Packlisten alle Teile als Reiter, in der Reihenfolge ihrer
  Nummern – das gerade geöffnete mit einem Reiter je Packliste (PCK-008) –,
  zuletzt "Alle zusammen" mit der Packliste des Gesamtprojekts samt aller
  Teile (PRJ-048). So ist jedes Teilprojekt mit einem Klick gewählt. Teile,
  deren Packliste jemand nicht sehen darf, fehlen (PRJ-049); "Alle zusammen"
  hat dieselben Reiter.


### 5.9 Zeiterfassung (ZEI)

Erfassung

- ZEI-001 [MUSS · V · S3] Eine einfache Stundenerfassung ist Teil der
  Anwendung.
- ZEI-002 [MUSS · V · S3] Jeder Zeiteintrag ist einem Projekt und innerhalb des
  Projekts einer Funktion zugeordnet – das Projekt spätestens, wenn der
  Eintrag freigegeben wird (ZEI-023).
Die Stunden eines Zeiteintrags sind die verstrichene Zeit: Über die Nacht der
  Zeitumstellung ist eine Schicht 7 oder 9 Stunden lang, nicht 8. Bereits gespeicherte Einträge werden nicht umgerechnet.
- ZEI-003 [MUSS · V · S3] Die Erfassung ist auf Schnelligkeit ausgelegt: von
  jeder Seite aus erreichbar, auf dem Smartphone bedienbar, wenige Eingaben.
- ZEI-004 [MUSS · A · S3] Felder eines Zeiteintrags: Person, Projekt, Funktion,
  Datum, Beginn, Ende, Pause in Minuten, Notiz.
- ZEI-005 [MUSS · A · S3] Zwei Erfassungsarten: nachträgliche Eingabe von
  Beginn und Ende sowie Start/Stopp-Uhr.
- ZEI-006 [MUSS · A · S3] Die Projektauswahl zeigt zuerst die Projekte, in
  denen die Person aktuell eingeplant ist; die Funktion ist aus der
  Personalposition vorbelegt.
- ZEI-007 [MUSS · A · S3] Wählbar sind nur Funktionen, die der Person im
  Projekt oder in ihren Stammdaten zugeordnet sind. Die Auswahl der Funktion ist bei der
  Zeiterfassung auf ein Projekt nie leer – auch ohne Phasen und ohne
  Personalpositionen. Zuerst stehen die eigenen Funktionen der Person und
  die, für die sie im Projekt eingeplant ist, dann die übrigen Funktionen
  der Personalpositionen und offenen Plätze des Projekts (bei einem
  Gesamtprojekt mit seinen Teilprojekten); bleibt damit nichts, ist wie bei
  Servicefällen (ZEI-024) jede aktive Funktion wählbar, ebenso ohne Projekt
  für jemanden ohne eigene Funktion. Der Satz ist der eigene, sonst der der
  Personalposition, sonst der Richtwert der Funktion. Das gilt im Browser,
  bei der Prüfung beim Speichern und in der API (/time-entries/choices, die
  die Begleit-App nutzt).
- ZEI-008 [MUSS · A · S3] Der Stundensatz wird zum Zeitpunkt der Erfassung aus
  Person und Funktion ermittelt und am Eintrag festgeschrieben.
- ZEI-009 [MUSS · A · S3] Einträge einer Person dürfen sich zeitlich nicht
  überschneiden; Ende muss nach Beginn liegen; Einträge über Mitternacht sind
  möglich.
- ZEI-010 [SOLL · A · S3] Zeiten ohne Kundenprojekt (Lager, Werkstatt, Büro)
  werden auf interne Projekte gebucht.
- ZEI-011 [SOLL · A · S3] Mit entsprechendem Recht können Zeiten für andere
  Personen erfasst werden (z. B. Crewchef für sein Team).

Freigabe

- ZEI-012 [MUSS · V · S3] Zeiten müssen freigegeben werden. Status je Eintrag:
  erfasst, eingereicht, freigegeben, abgelehnt. Freigegebene Einträge sind
  gesperrt; nur freigegebene Zeiten gehen in Abrechnung und Nachkalkulation
  ein.
- ZEI-013 [MUSS · A · S3] Freigabe durch Projektleitung oder
  Personaldisposition, einzeln oder gesammelt je Projekt bzw. Zeitraum.
- ZEI-014 [MUSS · A · S3] Jede Änderung an einem Zeiteintrag ist protokolliert.

Auswertung

- ZEI-015 [MUSS · A · S3] Auswertung nach Person, Projekt, Funktion und
  Zeitraum mit Stundensumme und – bei entsprechendem Recht – Betrag.
- ZEI-016 [MUSS · A · S3] Jede Person sieht ihre eigenen Zeiten und Summen.
- ZEI-017 [SOLL · A · S3] Export der Auswertung als CSV und PDF
  (Stundenzettel).
- ZEI-018 [SOLL · A · S8] Hinweise bei auffälligen Zeiteinträgen: eine sehr
  lange Schicht (mehr als 10 Stunden), eine fehlende Pause (bei mehr als
  6 Stunden 30 Minuten, bei mehr als 9 Stunden 45 Minuten) und eine kurze
  Ruhezeit (weniger als 11 Stunden zwischen zwei Einträgen einer Person).
  Die Grenzen sind Einstellungen mit diesen Voreinstellungen. Die Hinweise
  erscheinen beim Erfassen, in der Freigabe und in der Auswertung und
  halten nie etwas auf. Ein Arbeitszeitnachweis wird die Zeiterfassung
  dadurch nicht (3.3). Sie lassen sich zentral in den
  Einstellungen bei ihren Grenzen ein- und ausschalten ("Hinweise zu
  Arbeitszeiten anzeigen", voreingestellt und nach dem Update an);
  ausgeschaltet erscheinen sie weder beim Erfassen noch in Freigabe,
  Auswertung oder API.
- ZEI-019 [SOLL · A · S8] Spesen und Fahrtkosten je Projekt: Art
  (Verpflegung, Fahrt mit Kilometern × Satz je Kilometer, Übernachtung,
  Parken/Maut, Sonstiges), Datum, Betrag, Notiz und ein Foto des Belegs. Die
  Person erfasst sie selbst, auch am Telefon, oder das Büro für sie;
  freigegeben werden sie wie Zeiten (ZEI-012), und sie lassen sich als
  erstattet kennzeichnen. Sie zählen zu den Kosten des Projekts und mindern
  den "Gewinn aus dem Projekt" (PRJ-087). Es gibt eine Auswertung und eine
  CSV-Datei je Monat und Person; die API kennt die Spesen. Der Satz je
  Kilometer ist eine Einstellung, voreingestellt 0,30 €. Bei einer Fahrt
  wird der Arbeitsweg abgezogen (ZEI-027).
Das Foto des Belegs wird neu gerendert (aufrecht, JPEG, mit Standort); ein PDF bleibt,
  wie es kam (NFA-084).
- ZEI-020 [SOLL · A · S7] Erfassung ohne Netzverbindung mit späterer
  Übertragung. In der Android-App (APP-004); mit
  ihr Teil der Stufe 7.

Verbindung zur Abrechnung

- ZEI-021 [MUSS · A · S3] Freigegebene Zeiteinträge werden der Personalposition
  mit derselben Person und Funktion im Projekt zugerechnet; die Position zeigt
  geplante und geleistete Stunden nebeneinander. Zeiten ohne passende
  Personalposition werden im Projekt ausgewiesen und lassen sich einer Position
  zuordnen oder als neue Position übernehmen.

Zeitpunkt und Projekt

- ZEI-022 [MUSS · V · S3] Zeiten werden erfasst, wenn sie geleistet sind:
  Beginn und Ende eines Eintrags dürfen nicht in der Zukunft liegen. Die
  Stoppuhr beginnt im Augenblick des Starts und ist davon nicht betroffen.
  Die Meldung nennt die aktuelle Uhrzeit, damit eine falsch gehende Uhr des
  Geräts auffällt [A].
- ZEI-023 [MUSS · V · S3] Eine Zeit lässt sich auch ohne Projekt erfassen,
  etwa wenn die Person das Projekt noch nicht kennt. Wählbar sind dann nur
  die Funktionen aus ihren Stammdaten (ZEI-007). Freigegeben werden kann der
  Eintrag erst, wenn ihm ein Projekt zugeordnet ist; zuordnen können die
  Person selbst, solange der Eintrag nicht freigegeben ist, und wer Zeiten
  freigibt [A]. Bis dahin gehört er zu keinem Projekt und zu keiner
  Abrechnung.

Ausbaustufe 8: Weitere Anforderungen

- ZEI-024 [SOLL · V · S8] Auf einen offenen Servicefall (PRJ-090) kann jeder
  mit Zeiterfassung jederzeit Zeiten erfassen, auch ohne eingeplant zu sein
  ("spontan"), im Browser wie in der Begleit-App: Die Auswahl bei der
  Zeiterfassung bietet alle offenen Servicefälle an, die, an denen die
  Person beteiligt ist (PRJ-108), zuerst, jeweils mit jeder Funktion. Unter
  "Meine Zeiten" steht ein kleiner Hinweis, den man wegklicken kann: Zeiten
  lassen sich auch mit der Begleit-App für Android (Rentalars Companion)
  erfassen, mit Stoppuhr und ohne Netz; er führt zu Mein Konto → Tokens, wo
  der Zugang der App entsteht (AUT-021). Auf der Startseite steht er nicht.
- ZEI-025 [SOLL · V · S8] Mehrere Funktionen in einem Zeitraum: Ein erfasster
  Zeitraum (Beginn, Ende, Pause) lässt sich in Anteile teilen, jeder mit
  einer Funktion und seinen Stunden; zusammen ergeben die Anteile die
  gearbeiteten Stunden. Vorgeschlagen werden zuerst die geplanten
  Personalpositionen der Person im Projekt, mit den Zeiten ihrer Phase, etwa
  "Licht – Aufbau 08:00–12:00". Jeder
  Anteil hat seine eigene Funktion, Personalposition, Stunden und seinen
  Satz, sodass Summen, Auswertungen, Freigabelisten, Exporte und Kosten mit
  den Anteilen rechnen wie mit einzelnen Einträgen. Zuschläge (PER-009)
  verteilen sich nach den Stunden auf die Anteile; die Hinweise (ZEI-018),
  die Prüfung auf Überschneidung (ZEI-009) und die Stoppuhr behandeln den
  Zeitraum einmal; Freigeben und Ablehnen gilt für den ganzen Zeitraum. Das
  gilt im Browser – Zeit erfassen, Meine Zeiten, die Zeiten des Projekts, die
  Freigabe – und in der API; ein Eintrag ohne Anteile ist davon nicht
  betroffen, auch für die Begleit-App (APP-004).
- ZEI-026 [SOLL · V · S8] Unter "Meine Zeiten" steht zwischen "Stunden" und
  "Betrag" der Stundenlohn, bei einem Tagessatz (PER-029) "Tagessatz" mit
  seinem Betrag. Freigegebene Zeiten haben einen Knopf "In Zwischenablage
  kopieren". Er legt je Anteil eines Zeitraums (ZEI-025) einen Block in die
  Zwischenablage, eingerückt mit einem echten Tabulatorzeichen (hier
  <Tab>), das Datum mit Punkten:

      <Name des Dienstleistungsprodukts der Funktion>
      <Tab>Datum: <Startdatum als yyyy.mm.dd>
      <Tab>Projekt: <Nummer> - <Name>
      <Tab>Aktivität: <Phase der Personalposition, sonst leer>

  Vorlesende Programme hören "Kopiert". Das Kopieren geht auch, wo der
  Browser die Zwischenablage nicht direkt anbietet, etwa über http.
- ZEI-027 [SOLL · V · S8] Arbeitsweg bei Fahrtkosten: Jede Person hat die
  Angabe "Entfernung Wohnung – Betrieb (km)". Bei Fahrten (ZEI-019) zieht
  Rentalars je Person, Projekt und Tag einmal die doppelte Entfernung ab –
  hin und zurück –, und die Spese zeigt die Rechnung, etwa "42 km − 28 km
  Arbeitsweg = 14 km". Ohne Entfernung wird nichts abgezogen; eine
  Einstellung schaltet den Abzug ab. Formular und API der Person kennen die Entfernung.


Ausbaustufe 9: Weitere Anforderungen

- ZEI-028 [SOLL · V · S9] Pauschale unter "Meine Zeiten"
  (die Pauschale zählt einmal je Einsatz): Hat die Personalposition eine Pauschale für
  die Person (PER-018), zeigt der erste erledigte Eintrag des Einsatzes
  "Pauschale" mit ihrem Betrag, jeder weitere "in der Pauschale" mit 0 –
  gleich in welcher Woche; Stunden zählen als Stunden. Eine
  Pauschale geht vor einem Tagessatz. Die API nennt es je Eintrag
  (in_flat_rate). Berichte, Freigabe und Stundenzettel rechnen
  Stunden × Satz wie bei Tagessätzen (ZEI-026).

Ausbaustufe 9: Weitere Anforderungen

- ZEI-029 [SOLL · V · S9] Erinnerung an Zeiten zur Freigabe: Unter Einstellungen
  → Benachrichtigungen, Abschnitt "Zeiten zur Freigabe": an oder aus, Uhrzeit
  (Vorgabe 8:00), erste Erinnerung nach so vielen Tagen (1) und danach alle so
  viele Tage (1). Wer Zeiten freigeben darf (ZEI-013), wird an die
  eingereichten Zeiten und Spesen erinnert, die er freigeben darf – nie an die
  eigenen –, mit ihrer Zahl und einem Verweis auf Personal → Freigeben. Ein
  verpasster Termin wird einmal nachgeholt; nach dem Update ist die Erinnerung
  eingeschaltet.
- ZEI-030 [SOLL · V · S9] Korrigieren und freigeben: Auf Personal → Freigeben
  öffnet "Korrigieren und freigeben" eine Zeit im Dialog – Projekt, Funktion,
  Tag, Beginn, Ende, Pause, Notiz. Es gelten die Regeln der Erfassung; ein
  anderes Projekt muss eines sein, für das der Freigebende freigeben darf.
  Speichern gibt die Zeit frei; die alten Werte bleiben im Änderungsprotokoll
  und im Verlauf der Person ("Bei der Freigabe korrigiert"). API: POST
  /time-entries/{id}/correct.
- ZEI-031 [SOLL · V · S9] Nachricht über die Freigabe: Die Person erfährt die
  Freigabe, die Korrektur (mit den Werten vorher) und die Zurückweisung (mit
  dem Grund) ihrer Zeiten und Spesen – eine Nachricht je Person und Aktion.
  Neue Art der Benachrichtigung, je Nutzer abschaltbar.


### 5.10 Dokumente und Vorlagen (DOK)

- DOK-001 [MUSS · V · S1] Packliste als PDF (siehe PCK-003).
- DOK-002 [SOLL · A · S5] Angebot als PDF aus den Projektpositionen, mit
  Versionen. Ausgeführt in DOK-010; eine neue
  Version ist ein weiteres Angebot mit eigener Nummer.
- DOK-003 [SOLL · V · S5] Perspektivisch: Auftragsbestätigung und Lieferschein
  als PDF.
- DOK-004 [SOLL · A · S5] Crew-Disposition je Projekt als PDF (wer, wann, wo,
  Funktion, Kontaktdaten gemäß Freigabe der Person, PER-019) – ohne
  Stundensätze.
- DOK-005 [SOLL · A · S5] Dokumentvorlagen mit Logo, Kopf- und Fußzeile,
  Textbausteinen und Nummernkreisen. Wählbar, ob die
  Beschreibung der Produkte mitgedruckt wird (DOK-021). Die
  PDF-Belege zeigen die Rabattspalte nur bei einem Rabatt, richten die
  Spalten aus und gliedern klarer (DOK-025).
- DOK-006 [SOLL · V · S5] Perspektivisch: Rechnung als PDF einschließlich
  strukturierter elektronischer Rechnung; später zusätzlich Übergabe der
  Rechnungsdaten an ein Buchhaltungssystem über die API (DOK-011, DOK-012).
  Bei einem Kunden mit USt-IdNr. eines anderen EU-Landes und Steuersatz 0 % steht auf der Rechnung
  der Hinweis auf die Steuerschuldnerschaft des Leistungsempfängers mit seiner USt-IdNr. statt "Umsatzsteuerfrei".
- DOK-007 [SOLL · A · S5] Erzeugte Dokumente werden unveränderlich am Projekt
  abgelegt.
- DOK-008 [KANN · A · S5] Versand von Dokumenten per E-Mail aus der Anwendung.
- DOK-009 [MUSS · V · S1] Preisübersicht je Projekt als Grundlage für externe
  Angebote: Teilgruppen mit Bezeichnung, Beschreibung und Zwischensumme,
  wahlweise mit Positionen (Artikelnummer, Bezeichnung, Menge, Einheit,
  Miettage, Einzelpreis, Rabatt, Summe), Block Personal, Steuer je Steuerart
  und Gesamtsumme. Zunächst als Ansicht im Browser (PRJ-035); die Ausgabe als
  PDF und CSV folgt in einer späteren Stufe. Als internes Arbeitsdokument
  gekennzeichnet.

Weitere Anforderungen

- DOK-010 [SOLL · V · S5] Dokumentart Angebot (DOK-002) mit eigenem
  Nummernkreis und "gültig bis", vorgeschlagen 14 Tage [A]. Optionale und
  alternative Teilgruppen und Positionen stehen gekennzeichnet darin. Ein
  Projekt kann mehrere Angebote haben.

Übergabe an die Buchhaltung

- DOK-011 [SOLL · V · S6] Rechnungen und Stornorechnungen lassen sich an
  Lexware Office übergeben – als Beleg mit der Rentalars-Nummer, den Beträgen
  je Steuersatz und dem PDF, von Hand oder sofort beim Erstellen. Der Kunde
  wird dort über die Kundennummer gefunden oder angelegt; wahlweise wird auf
  einen Sammelkunden gebucht. Was übergeben ist, ist am Dokument vermerkt;
  nichts wird doppelt übergeben.
- DOK-012 [SOLL · V · S6] Rechnungen und Stornorechnungen eines Zeitraums
  lassen sich als DATEV-Buchungsstapel (CSV im DATEV-Format) für die
  Steuerberatung herunterladen, eine Buchung je Rechnung und Steuersatz auf
  Debitor und Erlöskonto (SKR 03 oder 04, einstellbar); dazu auf Wunsch die
  Debitoren.

Weitere Anforderungen

- DOK-013 [SOLL · V · S6] Beim Angebot ist wählbar, ob es alle Positionen
  zeigt oder nur die Teilgruppen ("Umfang": "mit Positionen" oder "nur
  Teilgruppen"). Mit "nur Teilgruppen" steht jede Teilgruppe mit Beschreibung,
  Hinweis auf Rabatt oder Pauschalpreis und Summe darin, Untergruppen
  eingerückt mit ihrer eigenen Summe; Positionen ohne Teilgruppe, Personal und
  Aufpreise sowie optionale und alternative Positionen stehen weiter einzeln
  darin. Netto, Steuer und Brutto sind in beiden Fällen gleich. Die Gültigkeit
  lässt sich als Datum ("gültig bis") oder in Tagen angeben; ändert sich das
  eine, folgt das andere sofort. Vorgeschlagen wird die Gültigkeit aus der
  Vorlage des Angebots in den Einstellungen, anfangs 14 Tage (DOK-010); für
  Texte gibt es den Platzhalter {validity_days}.
- DOK-014 [SOLL · V · S8] Einstellbar ist, ob in Rentalars Rechnungen erstellt
  werden können: "Rentalars als Buchhaltungsprogramm verwenden", voreingestellt an. Ist
  die Einstellung aus, lässt sich weder eine Rechnung noch eine
  Stornorechnung erstellen – nicht auf der Seite und nicht über die API
  (Antwort 400) –, der Vorschlag für das nächste Dokument nennt keine
  Rechnung (PRJ-078), und die Übergabe an Lexware Office und DATEV (DOK-011,
  DOK-012) ist ausgeblendet. Vorhandene Rechnungen bleiben lesbar, und
  Projekte lassen sich ohne Rechnung abschließen. Die Einstellung
 steht in einem eigenen Kasten "Buchhaltung
  und Rechnungswesen" und blendet auch die Reiter der Buchhaltung aus (DOK-055).


Ausbaustufe 8: Weitere Anforderungen

- DOK-015 [SOLL · V · S8] Erinnerung an die Rechnung und "Rechnung gestellt"
: Ein abgeschlossenes ganzes Projekt mit Kunde – nicht intern, kein
  Teilprojekt, nicht storniert – gilt als abgerechnet, wenn es eine Rechnung
  hat, die nicht storniert ist (DOK-014 an), bzw. wenn "Rechnung gestellt"
  angehakt ist (DOK-014 aus; der Haken steht im Kopf des Projekts). "Keine
  Rechnung" beendet die Erinnerungen an ein Projekt, das nie abgerechnet wird
  (kostenlos, mit einem anderen abgerechnet); beides lässt sich zurücknehmen
  und steht im Änderungsprotokoll. Bis dahin erinnert Rentalars daran: zum
  ersten Mal so viele Tage nach dem Abschluss (voreingestellt 1), dann alle so
  viele Tage (7), zur eingestellten Uhrzeit (9:00) – die Projektleitung und
  eine weitere gewählte Person, nur wer Preise sehen und das Projekt lesen
  darf; einstellbar unter Einstellungen → Benachrichtigungen, abschaltbar, auf
  Wunsch auch für erledigte Servicefälle (mit Zeiten oder Spesen auf dem
  Fall). Die Erinnerung führt zu "Rechnung erstellen" bzw. zum Projekt mit dem
  Haken. Erinnert wird nur an Projekte mit etwas abzurechnen (Summe netto über
  0), die nach dem Update abgeschlossen wurden; Projekte, die vorher
  abgeschlossen waren, stehen weder als offen in
  den Listen noch im Kopf. Ein wieder geöffnetes und erneut abgeschlossenes
  Projekt beginnt von vorn. Die Projektliste hat den Filter "Rechnung offen"
  und die Spalte "Rechnung", die Startseite den Kasten "Noch zu schreibende
  Rechnungen". API: invoice_state am Projekt, POST
  /projects/{id}/invoice-status, die Einstellungen unter
  /settings/notifications. Die Erinnerung ist auch für Servicefälle
  voreingestellt an, und das Update schaltet sie auch in bestehenden
  Installationen ein – erinnert wird dann an Servicefälle, die seit dem
  Einschalten erledigt wurden, ältere stehen weiter unter "Rechnung offen";
  wer eine Monatsrechnung nicht öffnen darf, die einen Fall abrechnet, sieht
  am Fall "Rechnung gestellt" und "Abgerechnet mit einer Monatsrechnung" ohne
  ihre Nummer.
- DOK-016 [SOLL · V · S9] Halbautomatische Monatsrechnung für
  Servicefälle: Je Kunde und Monat
  schlägt Rentalars eine Sammelrechnung vor, die vor dem Erstellen geprüft
  und geändert wird – mit den Servicefällen des Monats (erledigt oder mit
  Zeiten im Monat), je Fall den freigegebenen Zeiten nach Funktion
  (ZEI-012, PER-009), Spesen (ZEI-019), verbrauchtem oder verkauftem
  Material und einer kurzen Zusammenfassung der Tätigkeit aus
  Beschreibung, Notizen und Korrespondenz (EML-051, auf Wunsch mit der
  lokalen KI, EML-040). Die Fälle der Rechnung gelten danach als
  abgerechnet (DOK-015). Ideen dazu in Kapitel 12.2, Nummer 29 j). Stufe 9,
  gebaut nach den Ideen ohne Vertrag (DOK-017): Unter Buchhaltung
  (DOK-019) der Reiter
  "Monatsabrechnung" (mit dem Recht für Preise) mit den Kunden eines
  Monats; je Kunde ein Entwurf mit einem Abschnitt je Fall – Tätigkeit
  (Vorschlag aus Beschreibung, Notizen der Zeiten und, mit dem Recht
  dafür, der Korrespondenz; auf Wunsch von der KI zusammengefasst),
  Zeiten nach Funktion zum Preis des Dienstleistungsprodukts (PRD-044;
  nach Stunden, Tagen je Person oder pauschal je Fall, mit Stundengrenze
  und Zuschlägen wie bei Personalpositionen), Spesen zu ihrem Betrag als
  netto und eigene Positionen –, änderbar und neu einzusammeln. Jede Zeit
  und jede Spese wird nur von einer Monatsabrechnung abgerechnet; ein
  Fall über mehrere Monate wird Monat für Monat abgerechnet. Mit
  "Rentalars als Buchhaltungsprogramm verwenden" (DOK-014) entsteht daraus die
  Rechnung (Entscheidung) – eine Rechnung mit
  einem Abschnitt je Fall, die zum Fall mit der kleinsten Nummer gehört
  und alle Fälle als abgerechnet führt; sonst ist der Entwurf die
  Ansicht, aus der die Werte per Klick in die Zwischenablage gehen (wie
  in der Preisübersicht bei Projekten), und "Als abgerechnet
  markieren" setzt bei den Fällen "Rechnung gestellt" (zurücknehmbar).
  Eine stornierte Monatsrechnung macht den Entwurf und die Fälle wieder
  offen.


Ausbaustufe 9: Weitere Anforderungen

- DOK-018 [SOLL · V · S9] Vorlagentexte auf Englisch oder Deutsch:
  Unter Einstellungen → Dokumente und
  Buchhaltung übernimmt eine Seite die mitgelieferten Texte der
  Dokumentvorlagen – Überschrift, Einleitung, Schlusstext – auf Englisch
  oder Deutsch, je Vorlage mit "Jetzt" und "Neu". Eigene Texte sind
  gekennzeichnet und bleiben, solange sie nicht angehakt werden; Fuß, Logo
  und Gültigkeit des Angebots bleiben immer. Die Sprache der Dokumente ist
  eine eigene Einstellung und wechselt nur mit eigenem Haken. Jede
  Übernahme steht im Änderungsprotokoll. API GET und POST
  /document-templates/defaults.
- DOK-017 [KANN · V · S10] Vertrag je Kunde für die Monatsrechnung
  (DOK-016): Pauschale im Monat, enthaltene Stunden, Satz darüber, und ein
  Termin, an dem Rentalars an die Monatsrechnung erinnert. Festgehalten mit
  der Entscheidung: "Später".

Ausbaustufe 9: Weitere Anforderungen

- DOK-019 [SOLL · V · S9] Hauptmenü "Buchhaltung": Der Menüpunkt "Buchhaltung" steht zwischen
  "Materialverwaltung" und "Kunden", mit den Reitern "Ausgangsbelege"
  (DOK-020) und "Monatsabrechnung" (DOK-016;
  Adressen unter /accounting/, NFA-074). Er zeigt sich,
  wer Ausgangsbelege oder Monatsabrechnung sehen darf. DATEV-Export und
  Übergabe an Lexware Office bleiben unter Einstellungen → Buchhaltung; ein
  Knopf führt dorthin.
- DOK-020 [SOLL · V · S9] Ausgangsbelege: "Buchhaltung →
  Ausgangsbelege" listet alle Belege an Kunden – Angebote,
  Auftragsbestätigungen, Lieferscheine, Rechnungen und Stornorechnungen, keine
  Crew-Dispositionen – mit den gespeicherten Beträgen (netto, Steuer, brutto;
  nie neu berechnet), Status (gesendet, storniert), Übergabe an Lexware
  Office, Monatsabrechnung, Empfänger und Ersteller. Eine Tabelle nach UIX-015
  und UIX-040: Spalten wählbar, Filter (Art, Status, Lexware, Kunde, Projekt,
  Zeitraum, Suche), jede Spalte sortier- und gruppierbar, CSV; darunter die
  Summen aller gefilterten Belege je Art und "Rechnungen und Stornorechnungen
  zusammen". Nummer und Projekt führen zum PDF und zum Reiter "Dokumente". Nur
  mit Preisrecht und Lesezugriff auf alle Projekte. API: GET
  /accounting/documents und /accounting/documents/totals.

Ausbaustufe 9: Weitere Anforderungen

- DOK-021 [SOLL · V · S9] Produktbeschreibung in Dokumenten wählbar: Jede
  Dokumentvorlage (DOK-005) hat die Einstellung "Beschreibung der Produkte
  mitdrucken", im Standard aus. Beim Erstellen eines Belegs ist
  das Kästchen aus der Vorlage vorbelegt und wird am Beleg festgehalten; eine
  spätere Änderung der Vorlage ändert ausgestellte Belege nicht. Die Wahl gilt
  im PDF, in der Vorschau und im Mailanhang, bei Sammelrechnungen von
  Servicefällen und in der XRechnung (BT-154); der eigene Text einer Zeile
  bleibt immer stehen. API: print_product_descriptions.
- DOK-022 [SOLL · V · S9] Ausgangsbelege ohne Projekt: Unter Buchhaltung →
  Ausgangsbelege legt "Neuer Ausgangsbeleg" einen Entwurf an: Art (Angebot
  oder Rechnung), Kunde, Rechnungsadresse, Ansprechperson, Datum, Zahlungsziel
  bzw. Gültigkeit, Betreff und die Wahl der Beschreibungen (DOK-021). Der
  Entwurf hat eine Bearbeitungsseite mit freien Zeilen, Produktzeilen,
  Textzeilen, Rabatt, Reihenfolge und Texten und lässt sich löschen; er hat
  keine Nummer. Das Ausstellen läuft wie bei Projektbelegen: dieselbe
  lückenlose Nummer (Rechnung und Storno), Steuerzeilen, Fälligkeit,
  XRechnung, DATEV, Lexware, PDF und Mail mit Anhang; ein ausgestellter Beleg
  ist unveränderlich und wird durch Storno aufgehoben (DOK-003). Die Liste der
  Ausgangsbelege zeigt "ohne Projekt" und filtert nach der Herkunft; die Seite
  des Kunden führt seine Belege auf. Freie Belege zählen nicht zur
  Projekt-Profitabilität und nicht zu den Zahlungserinnerungen von Projekten;
  für anonymisierte oder deaktivierte Kunden gibt es keinen neuen Beleg,
  offene Entwürfe eines anonymisierten Kunden werden verworfen. API:
  accounting/drafts mit Zeilen, Vorschau und Ausstellen, project ist leer,
  dazu customer und reference. "Rechnung dazu
  erstellen" legt beim Gebrauchtverkauf aus dem Bestand einen solchen Entwurf an
  (MAT-087).
  Das Datum eines freien Belegs liegt im laufenden Jahr und nicht in der Zukunft (leer: heute);
  ein Entwurf, der über den Jahreswechsel liegen blieb, lässt sich mit seinem alten Datum nicht ausstellen.

Ausbaustufe 10: Weitere Anforderungen

- DOK-023 [SOLL · V · S10] Eingangsrechnungen: Unter
  Buchhaltung → Eingangsbelege steht das Register aller Rechnungen von
  Lieferanten: Tabelle mit Filtern (Lieferant, Zeitraum, Status, Suche),
  Summen der gefilterten Rechnungen (UIX-030, UIX-038) und CSV. Eine Rechnung
  wird als PDF oder Bild hochgeladen (Art, Inhalt und Größe werden geprüft,
  die Datei liegt wie andere Dokumente) und sofort gelesen: Rechnungsnummer,
  Datum, Fälligkeit, Lieferant, Netto, Steuer und Brutto aus dem Text des PDF,
  mit eingeschalteter KI (MAT-062) auch die Positionen und der Lieferant; ein
  bekannter Lieferant wird zugeordnet, ein unbekannter erst nach "Lieferanten
  anlegen". Alles lässt sich korrigieren; ein erneutes Lesen überschreibt nie,
  was getippt wurde, und rührt keine eingepflegte Position an. Zur Rechnung
  gehören eine Notiz, ein Status (offen, geprüft, eingepflegt) und der
  Download des Originals. Dieselbe Datei und dieselbe Nummer desselben
  Lieferanten warnen. Gescannte Bilder werden aufbewahrt, aber nicht gelesen
  (keine Texterkennung). Rechte wie bei "Kauf einpflegen" (MAT-061) und
  Einkaufspreise; gelöscht wird nur eine Rechnung, aus der nichts eingepflegt
  wurde. API: incoming-invoices mit Positionen, Lesen, Lieferant anlegen,
  Aufteilung und Einpflegen (DOK-024), dazu die Einstellungen. Buchhaltung
 hat dafür zwei Reiter: "Beleg erfassen" (Kasten
  "Rechnung hochladen"; nur mit Änderungsrecht) und "Eingangsbelege" (das
  Register, Kasten "Eingangsbelege", darunter "Summe der gefilterten
  Rechnungen"). Nach dem Hochladen fragt die Seite der Rechnung "Auch in der
  Materialverwaltung einpflegen?" (Ja führt zu "Ware einpflegen"); umgekehrt
  fragt die Seite nach "Kauf einpflegen" (MAT-061) "Auch als Eingangsbeleg in
  der Buchhaltung erfassen?", wenn der Kauf eine Rechnungsdatei hat: Bei Ja
  entsteht aus dieser Datei ein Eingangsbeleg mit Lieferant, Nummer und Datum
  des Kaufs und je Modell und Preis einer Kontierungszeile, die Exemplare sind
  verknüpft; dieselbe Datei im Register wird nicht doppelt angelegt. Die
  Positionen heißen "Kontierung" (DOK-026). Der Upload nimmt auch XML-Dateien und ZUGFeRD-PDF an (DOK-040), und
  der Kasten "Summe der gefilterten Rechnungen" sagt, wenn er unvollständig
  ist: Eine Rechnung in einer anderen Währung ohne Kurs und eine Rechnung ohne
  Summen fehlen in den Summen und werden gezählt (API: complete,
  missing_exchange_rate, without_amount).
- DOK-024 [SOLL · V · S10] Einpflegen aus Eingangsrechnungen,
  Anschaffungsnebenkosten, Art der Position: Aus den Positionen einer Eingangsrechnung
  entstehen Exemplare eines Modells (auch eines neuen) oder Mengen von
  Mengenmaterial – mit Vorschau und dem ausdrücklichen "Ja, genau so
  einpflegen", über dieselbe Logik wie "Kauf einpflegen" (MAT-061, MAT-084)
  samt ihrer Prüfungen. Eine Position wird nicht zweimal eingepflegt (Warnung;
  "Nochmals einpflegen" ist eine bewusste Wahl); das Exemplar nennt Rechnung
  und Position. Positionen, die als "Nebenkosten" gekennzeichnet sind (Fracht,
  Verpackung, Zoll …; ein Rabatt ist negativ), werden nach Wert, Stückzahl
  oder Gewicht – gewählt je Rechnung – auf die Ware aufgeteilt, centgenau, der
  Rest an die ersten Stücke; die Anschaffungskosten eines Exemplars sind sein
  Einkaufspreis plus Anteil. Je Position wird die Art gewählt: Handelsware,
  geringwertiges Wirtschaftsgut (bis zu einer Grenze netto, Standard 800 €,
  einschließlich) oder Anlagegut mit Nutzungsdauer in Monaten (Standard 60);
  Grenze und Nutzungsdauer stehen unter Einstellungen → Eingangsrechnungen.
  Das Exemplar hält Art, Nutzungsdauer, Nebenkosten, Anschaffungskosten und
  die Herkunftsposition fest (MAT-086); ein später geänderter Schlüssel ändert
  eingepflegte Exemplare nicht. Die Kosten sieht nur, wer Einkaufspreise sehen
  darf. Die Zeile der Kontierung fragt nur nach
  Beschreibung, Steuerkonto, Art, Nettobetrag der ganzen Position und
  Steuersatz; "behandelt als" nur bei Ware, die Nutzungsdauer nur bei einem
  Anlagegut (mit Verweis auf die AfA-Tabellen der Finanzverwaltung), das Gewicht
  nur bei der Verteilung nach Gewicht. Artikelnummer, Hersteller und Menge
  bleiben an der Zeile, wie das Lesen sie fand, und werden beim Einpflegen
  gebraucht; wählt die Person dort mehr Stück als die Menge der Zeile, bleibt
  der Nettobetrag der Zeile, und der Stückpreis folgt. Unter den Zeilen steht
  die Summe, die sich beim Tippen ändert (Netto, Steuer, Brutto, Abweichung zur
  Summe der Rechnung). Die Grenze schlägt
  die Art nur vor: Sie muss beim Einpflegen gewählt (bestätigt) werden; lässt
  man sie leer, lehnt "Ware einpflegen" die Position ab und nennt den
  Vorschlag. Handelsware wird nie geraten.
- DOK-025 [SOLL · V · S10] PDF-Belege klarer: Die Belege als PDF (Angebot, Auftragsbestätigung, Rechnung,
  Preisübersicht, freie Belege; DOK-002, DOK-005, DOK-022) zeigen die Spalte
  Rabatt nur, wenn mindestens eine Position einen Rabatt hat. Die
  Zahlenspalten stehen unter ihren Überschriften, mit und ohne Rabattspalte,
  mit Textzeilen und mit Teilgruppen. Die Gliederung hat drei Ebenen: oben
  Material, Personal und Logistik (samt Zuschlägen) – nur was vorkommt –,
  darunter beim Material zuerst die Teilgruppen, darunter die Positionen; jede
  obere Ebene hat eine Summenzeile ("Summe Material"). Beträge, Rabatte und
  Steuer ändern sich dadurch nicht.
- DOK-026 [SOLL · V · S10] Steuerliche Vorbereitung der Eingangsrechnung: Je
  Zeile der Kontierung einer Eingangsrechnung lässt sich ein Steuerkonto wählen.
  Die Steuerkonten sind Stammdaten (Kontonummer in 3 bis 10 Ziffern, einmalig,
  Name, aktiv); mitgeliefert ist eine Liste nach SKR 03, wie eine Firma der
  Veranstaltungstechnik sie oft braucht, als Vorschlag zur Abstimmung mit der
  Steuerberatung. Ein benutztes Konto lässt sich nicht löschen, nur
  deaktivieren. Rentalars schlägt kein Konto vor und bucht nicht. API:
  tax-accounts; die Position nennt `tax_account`. Offen bleibt das Übergabeformat
  an die Buchhaltung (12.2).

Ausbaustufe 10: Weitere Anforderungen

- DOK-030 [SOLL · V · S10] Abschlags- und Teilrechnung: Im Formular einer
  Rechnung (Reiter "Dokumente" des Projekts) wählt "Was die Rechnung abrechnet"
  zwischen der ganzen Rechnung, der Abschlagsrechnung (Zahlung
  auf Rechnung), der Teilrechnung und der Schlussrechnung. Abschlags- und
  Teilrechnung rechnen einen Betrag ab, nicht einzelne Positionen: ein
  Nettobetrag oder ein Prozentsatz der Netto-Summe (nur eins von beiden) und
  ein Text, wofür. Die Steuer folgt den Steueranteilen des Projekts, so dass
  jeder Satz im gleichen Verhältnis abgerechnet wird und die Schlussrechnung
  keinen Cent übrig lässt. Sie sind fortlaufend nummeriert ("1.
  Abschlagsrechnung", "2. Teilrechnung") und stammen wie jede Rechnung aus dem
  Kreis der Rechnungen; sie gelten nur für ein ganzes Projekt, nicht für
  Teilprojekte-Teile und nicht für Servicefälle.
- DOK-031 [SOLL · V · S10] Schlussrechnung mit Abzug der Abschläge (§ 14 Abs. 5
  UStG): Die Schlussrechnung zeigt das ganze Projekt wie die gewöhnliche
  Rechnung und zieht darunter jede gültige Abschlags- und Teilrechnung ab
  (Nummer, Datum, Netto, Steuer); zu zahlen ist der Rest. Sie braucht mindestens
  eine gültige Abschlags- oder Teilrechnung, und der Rest darf nicht negativ
  sein (sonst Meldung mit dem Ausweg Teilgutschrift, DOK-035). In Listen,
  Summen und API (`net_total`, `gross_total`) steht bei ihr, was sie
  hinzufügt (Projekt abzüglich Abschläge = Zahlbetrag), damit nichts doppelt
  gezählt wird.
- DOK-032 [SOLL · V · S10] Eindeutige Zuordnung und Schutz vor Doppelabrechnung:
  Rentalars lehnt ab und nennt den Grund, wenn Abschläge und Teile zusammen mehr
  als das Projekt netto (oder einen Steuersatz über seinen Anteil) abrechnen
  würden, wenn eine gewöhnliche Rechnung gestellt werden soll, obwohl eine
  gültige Abschlags- oder Teilrechnung besteht, wenn eine Schlussrechnung ohne
  Abschlag gestellt werden soll und wenn eine Abschlags- oder Teilrechnung
  storniert oder gutgeschrieben werden soll, die eine gültige Schlussrechnung
  abzieht. Ein Projekt, das nur Abschlags- oder Teilrechnungen hat, gilt in
  den Erinnerungen und in der Projektliste nicht als abgerechnet.
- DOK-033 [SOLL · V · S10] Abrechnungsstand: Sobald ein Projekt Abschlags- oder
  Teilrechnungen oder Teilgutschriften hat, zeigt der Reiter "Dokumente" den
  Kasten "Abrechnungsstand": Projekt netto, auf Rechnung abgerechnet, noch
  abzurechnen (netto und brutto) und je Rechnung Netto, Brutto und ihre
  Gutschriften – der Restbetrag ist so jederzeit nachvollziehbar.
- DOK-034 [SOLL · V · S10] Elektronische Rechnung und Buchung der Rechnungsarten:
  Die XRechnung nennt die Abschlags- und Teilrechnung mit dem Typ-Code 326, die
  Schlussrechnung mit 380, die abgezogenen Rechnungen als Rechnungsbezug
  (BG-3), den Abzug als bereits gezahlten Betrag (BT-113) und den Rest als
  Zahlbetrag. DATEV und Lexware Office buchen die Abschlags- und Teilrechnung
  als Rechnung und die Schlussrechnung nur mit dem Rest nach dem Abzug (die
  Abschläge sind schon gebucht). Das PDF zeigt die Abzüge und "Zu zahlender
  Betrag".
- DOK-035 [SOLL · V · S10] Teilgutschrift: Eine gültige Rechnung lässt sich
  teilweise gutschreiben (Nettobetrag oder Prozentsatz von dem, was sie noch
  abrechnet, und ein Text): Es entsteht eine Gutschrift mit negativen Beträgen,
  die die Rechnung nennt ("Gutschrift zur Rechnung …"), mit eigener Nummer aus
  dem Kreis der Rechnungen und XRechnung (Typ-Code 384); die Rechnung bleibt
  gültig, mehrere Gutschriften zusammen übersteigen sie nie. Wird die Rechnung
  später doch storniert, storniert Rentalars nur den Rest. Wird alles
  gutgeschrieben, was noch übrig ist, ist die Gutschrift die Stornierung (die
  Rechnung gilt als storniert, das Projekt lässt sich neu abrechnen). Die
  Teilgutschrift steht in den Ausgangsbelegen und im Abrechnungsstand.
- DOK-036 [SOLL · V · S10] Schnittstelle der Rechnungsarten: Die API
  /documents (Anlegen und Vorschau) nimmt `billing_type`, `amount`, `percent` und
  `note`; /documents/{id}/credit macht die Teilgutschrift; die Belege nennen
  `billing_type`, `billing_number` und `credit_for`.
- DOK-037 [SOLL · V · S10] Verkauf aus dem Bestand und Rechnung (Verknüpfung,
  Duplikatschutz, Storno): "Rechnung dazu
  erstellen" verknüpft den Entwurf mit dem Verkauf; ein zweiter Aufruf liefert
  denselben offenen Entwurf; wurde die Rechnung ausgestellt, nennt der Verkauf
  sie, und eine zweite Rechnung für denselben Verkauf wird abgelehnt, bis die
  erste storniert ist. Ein Verkauf mit gültiger Rechnung lässt sich nicht
  rückgängig machen – erst die Rechnung stornieren (MAT-087).
- DOK-038 [SOLL · V · S10] Gewählte Ausgangsbelege herunterladen: In der Liste der Ausgangsbelege lädt "Gewählte Belege
  herunterladen (ZIP)" je Beleg das PDF und, wenn es eine gibt, die XRechnung,
  benannt nach der Belegnummer; höchstens 300 Belege in einem Download. Jeder
  Beleg wird einzeln auf Recht geprüft, nicht Erlaubtes bleibt draußen und
  wird genannt (UIX-058).
- DOK-040 [SOLL · V · S10] E-Rechnungen im Eingang lesen: Eingangsrechnungen (DOK-023) nehmen XML-Dateien an –
  XRechnung (UBL Invoice oder CreditNote, CII) und die XML-Fassung von ZUGFeRD /
  Factur-X – und ZUGFeRD- oder Factur-X-PDF mit eingebettetem XML. Die Datei
  wird genau gelesen, ohne KI und ohne Textmuster: Lieferant (einem bekannten
  zugeordnet), Nummer, Datum, Fälligkeit, Währung, Summen und alle Positionen
  mit Menge, Einzelpreis, Steuersatz und Artikelnummer; Rabatte und Zuschläge
  auf Belegebene werden Positionen der Art Nebenkosten. Eine Gutschrift (Code
  381) behält die Beträge der Datei und ist gekennzeichnet; ihre Positionen sind
  "Sonstiges". XML mit Dokumenttyp-Deklaration oder Entitäten, zu großes oder
  zu tief verschachteltes XML und XML, das keine UBL-/CII-Rechnung ist, wird
  beim Hochladen abgelehnt; ein unbrauchbarer Anhang eines PDFs lässt das PDF
  stehen (Lesen als PDF, mit Hinweis). Die Summen werden gegen sich selbst
  verglichen (1 Cent Rundung); eine Abweichung ist ein Hinweis, keine
  Ablehnung. Eingepflegt wird erst nach der Prüfung durch die Person.
- DOK-041 [SOLL · V · S10] E-Rechnung anzeigen: Der Beleg zeigt "strukturierte
  E-Rechnung" mit Format (UBL, CII), Profil (XRechnung, ZUGFeRD / Factur-X
  MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED), Spezifikation, Typ-Code,
  USt-IdNr. und IBAN des Lieferanten, Käufer- und Bestellreferenz und Zahlbetrag;
  der XML-Quelltext ist ladbar (Browser, API
  /incoming-invoices/{id}/xml), das Original-PDF bleibt erhalten; "Erneut
  lesen" liest das XML noch einmal und lässt Getipptes stehen.
- DOK-042 [SOLL · V · S10] Validierung von Ausgangs- und Eingangs-E-Rechnungen:
  Rentalars prüft eine E-Rechnung (UBL oder CII, XRechnung oder ZUGFeRD / Factur-X) selbst gegen die Kernregeln der
  EN 16931 und – bei einer XRechnung – gegen die deutschen Regeln. Gebaut sind: die Pflichtangaben (BR-01 bis
  BR-16, BR-21 bis BR-26: Spezifikations-Kennung, Nummer, Datum, Typ-Code, Währung, Verkäufer und Käufer mit Name
  und Land, Summen, mindestens eine Position mit Menge, Einheit, Nettobetrag, Bezeichnung und Preis), die Summen
  (BR-CO-10, -13, -14, -15, -16, -17: Summe der Positionen, Nachlässe und Zuschläge, Steuerbeträge, Brutto,
  Zahlbetrag, Rundung auf den Cent), die Steueraufschlüsselung (BR-CO-04, -18, BR-45 bis BR-48, Steuerbasis je
  Kategorie und Satz gegen die Positionen), die Zahlungsangaben (BR-CO-25 Fälligkeit oder Zahlungsbedingung, BR-50
  IBAN bei Überweisung, Prüfsumme der IBAN), die Kennung des Verkäufers (BR-CO-26) und für die XRechnung BR-DE-1 bis
  BR-DE-9 (Zahlungsangaben, Ansprechpartner des Verkäufers mit Name, Telefon und E-Mail, Anschrift mit Ort und
  Postleitzahl), BR-DE-15 (Käuferreferenz), BR-DE-21 (Spezifikationskennung der XRechnung) und die zulässigen Typ-Codes. Jede Meldung nennt die Regel, die Stelle in
  der Datei und was zu tun ist; ein Fehler (die Datei verstößt gegen eine Regel) und ein Hinweis (plausibel
  prüfen, z. B. Format der USt-IdNr) sind getrennt. Ausgangsrechnungen werden beim Ausstellen geprüft und das
  Ergebnis zur Rechnung gespeichert (die Rechnung selbst bleibt unverändert, DOK-007); in den Einstellungen
  (Buchhaltung) legt die Verwaltung fest, ob Fehler nur gemeldet werden (Standard) oder die Rechnung nicht
  ausgestellt wird. Eingangs-E-Rechnungen werden beim Hochladen und beim erneuten Lesen geprüft; ein Fehler
  lehnt nichts ab, er steht beim Beleg. Auf Seite und API: "E-Rechnung prüfen" wiederholt die Prüfung. Nicht Teil:
  die Prüfung gegen die Schemas (XSD) und die Schematron-Regeln der KoSIT; die Prüfung ersetzt sie nicht. Für die
  Entwicklung gibt es `scripts/external_validation.py`, das die erzeugten UBL- und CII-Dateien
  gegen die offiziellen Schemas und das Schematron der EN 16931 prüft (Werkzeuge von PyPI); dabei fand sich ein Fehler
  im CII (Namensraum eines Datums), der behoben ist. Das Prüfwerkzeug der KoSIT mit den deutschen Regeln (BR-DE) war
  in der Umgebung nicht erreichbar und ist nicht gelaufen.
  Die E-Rechnung nennt in diesem Fall die Kategorie AE (Reverse Charge) mit dem Befreiungsgrund
  und verlangt die USt-IdNr. der Firma; Steuersätze ohne Nachkommastellen (20, 100) behalten ihre Nullen; zwei
  Steuersätze mit gleichem Prozentwert ergeben eine Zeile der Steueraufstellung.
- DOK-043 [SOLL · V · S10] GoBD-Archiv: Jeder Beleg – Ausgangsdokument mit PDF und XML, Eingangsrechnung mit Datei und XML – wird mit seiner
  Prüfsumme (SHA-256), dem Eingangszeitpunkt und der Aufbewahrungsfrist in das Archiv eingetragen (Eintrag
  `ArchiveRecord`, selbst unveränderlich bis auf Prüfstand und Löschvermerk). Die Frist ist einstellbar
  (Standard: 8 Jahre für Rechnungen und Buchungsbelege nach § 147 Abs. 3 AO, 6 Jahre für Geschäftsbriefe, also
  Angebote und Auftragsbestätigungen, Lieferscheine) und endet mit dem Ablauf des Kalenderjahres. Die nächtliche
  Wartung trägt neue Belege nach und prüft einen Teil des Archivs auf unveränderte Dateien (mit Fortschritt, damit
  jede Datei im Lauf einer einstellbaren Zahl von Tagen geprüft wird, Standard 30); eine abweichende oder fehlende
  Datei wird dem Archiv als Befund vermerkt, die Verwaltung wird benachrichtigt, der Selbsttest zeigt es. Eine
  Eingangsrechnung innerhalb der Aufbewahrungsfrist lässt sich nicht löschen (die Meldung nennt das Ende der
  Frist); nach der Frist darf sie gelöscht werden, Ausgangsdokumente bleiben ohnehin (DOK-007). Seite
  Einstellungen → Buchhaltung → Archiv: Zahl der Einträge, letzter Prüflauf, Befunde, Prüfung auf Knopfdruck, Liste
  mit Filter und CSV; API-Ressource /archive und Aktion /archive/verify. Nicht Teil: eine revisionssichere
  Speicherung auf WORM-Medien, ein Zeitstempel einer Zeitstempeldienststelle, Verschlüsselung des Archivs; die
  Sicherung (NFA) bleibt der Weg, das Archiv selbst zu schützen.
- DOK-044 [SOLL · V · S10] Rechnungsversand mit strukturierter Rechnung:
  Die Mail mit der Rechnung trägt die strukturierte Rechnung mit: bei einer Rechnung im Format
  XRechnung die XML-Datei als zweiten Anhang (vorgewählt, wenn die Rechnung eine Käuferreferenz, die Leitweg-ID, hat
  oder der Kunde so eingestellt ist; sonst wählbar), bei einer Rechnung im Format ZUGFeRD (DOK-049) das PDF selbst,
  in dem die Daten stecken (kein zweiter Anhang nötig). Der Versandweg (Rechnung versenden, Mailprogramm des
  Projekts) bietet die Wahl an, der Versand wird an der Rechnung vermerkt und ist im Archiv nachvollziehbar.
- DOK-045 [SOLL · V · S10] Einnahmenüberschussrechnung (EÜR; entschieden: vorrangig EÜR): Buchhaltung → EÜR zeigt zu einem Jahr
  die Betriebseinnahmen nach Zahlungseingang und die Betriebsausgaben nach Zahlungsausgang (Zufluss- und
  Abflussprinzip, § 11 EStG) aus den Zahlungen (DOK-048): Einnahmen netto je Steuersatz und die vereinnahmte
  Umsatzsteuer (Rechnungen, Teilbeträge nach dem Verhältnis der Steuersätze der Rechnung, Rückzahlungen und
  Gutschriften mindern), Ausgaben netto nach Konto der Eingangsrechnung (Steuerkonto, DOK-026; ohne Konto nach der
  Art der Position), gezahlte Vorsteuer, Abschreibungen (aus dem Anlagenspiegel, MAT-086; Anlagevermögen nur als
  Abschreibung, nicht bei der Zahlung; Geringwertige Wirtschaftsgüter im Jahr der Anschaffung), Restbuchwert
  abgegangener Anlagen und Erlöse aus Verkäufen aus dem Bestand ohne Rechnung, der Überschuss (Gewinn oder
  Verlust). Eine Einstellung "Kleinunternehmer (§ 19 UStG)" rechnet brutto, ohne Umsatz- und Vorsteuer. Zu jeder
  Summe gehört die Liste der Einzelbuchungen (Datum, Beleg, Gegenüber, netto, Steuer, brutto, Konto); Auswertung
  als Seite, CSV und API (/accounting/euer?year=…). Ein Hinweis zählt auf, was fehlt: Rechnungen ohne
  Zahlung, Eingangsrechnungen ohne Positionen oder Steuerangaben, Positionen ohne Konto. Die Auswertung ist eine
  Vorbereitung für die Anlage EÜR und die Steuerberatung, keine Steuerberatung und kein Elster-Formular
  (keine Zeilennummern der Anlage); Besonderheiten wie Privatentnahmen, Anlageverzeichnis nach § 7g, Sammelposten,
  Vorauszahlungen sind nicht gebaut. Zahlungen an das Finanzamt sind DOK-052. Rechte: Verwaltung (lesen), Preise und Einkaufspreise.
  Der Überschuss zählt die Umsatzsteuer der Zahlungen mit (Ergebnis ohne Umsatzsteuer und noch
  geschuldete Umsatzsteuer stehen daneben; Kleinunternehmer: Gewinn = Überschuss). Zahlungen an ein Finanzamt
  innerhalb von zehn Tagen um den Jahreswechsel lösen einen Hinweis aus; die 10-Tage-Regel wird nicht angewendet. Ein
  Teilverkauf aus einer Anlage aus Mengenmaterial ändert die Abschreibung früherer Jahre nicht; verlorene und
  ausgemusterte Anlagen schreiben nicht weiter ab, der Restbuchwert geht als Abgang ein (Tag aus dem
  Änderungsprotokoll).
- DOK-046 [SOLL · V · S10] Prüfbarkeit: Zwei Hilfen für
  eine Prüfung der Buchhaltung. Der Datenzugriff (Einstellungen → Buchhaltung → Datenträger für die Prüfung; API
  /accounting/audit-export) liefert zu einem Zeitraum ein ZIP: Tabellen im CSV-Format (Ausgangsrechnungen,
  Eingangsrechnungen, Zahlungen, Positionen, Anlagenspiegel, Archiv) mit einer Beschreibung `index.xml`
  (Beschreibungsstandard in der Art von GDPdU / GoBD, nach bestem Wissen und nicht mit einer Prüfsoftware
  geprüft), die Belege (PDF, XML) und eine Prüfsummenliste (`SHA256SUMS`); das Archivprotokoll ist enthalten. Die
  Verfahrensdokumentation (Seite und Download als PDF und Markdown) beschreibt, wie Rentalars Belege erzeugt,
  unveränderlich speichert, archiviert, sichert und prüft, mit Fristen, Rechten, Schnittstellen und der
  Versionsnummer, und ist nach dem Vorbild der Anforderungen der GoBD aufgebaut; sie nennt die Annahmen und was
  der Betreiber selbst ergänzen muss (Organisation, Zuständigkeiten, interne Kontrollen). Beides ist eine Hilfe
  und keine Bescheinigung der GoBD-Konformität.
- DOK-047 [KANN · V · S10] Doppelte Buchführung (entschieden): Konten, Buchungssätze
  und Abschluss. Nur vorgemerkt; nicht gebaut. Die Zahlungen (DOK-048) und das Archiv (DOK-043) sind die Grundlage.
- DOK-048 [SOLL · V · S10] Zahlungen und offene Posten (Grundlage von DOK-045):
  Zu einer Ausgangsrechnung (auch Abschlags-, Teil- und Schlussrechnung)
  lassen sich mehrere Zahlungen mit Datum (nicht in der Zukunft), Betrag, Zahlungsart (Überweisung, Bar, Karte,
  Lastschrift, Verrechnung, sonstige), Verwendungszweck und Bemerkung erfassen; ein negativer Betrag ist eine
  Rückzahlung. Eine Zahlung wird nicht geändert oder gelöscht, sondern mit Begründung storniert (bleibt sichtbar,
  zählt nicht). Der Zahlbetrag der Rechnung ist ihr Bruttobetrag mit Abzügen, Teilgutschriften und Storno; daraus
  rechnet Rentalars den Restbetrag und den Stand (offen, teilweise bezahlt, bezahlt, überzahlt, überfällig,
  Rückzahlung fällig bei stornierter bezahlter Rechnung) – nichts davon wird gespeichert. Seite
  Buchhaltung → Offene Posten (Ausgang): offene und überfällige Rechnungen nach Kunde, Fälligkeit und Restbetrag mit
  Summen, Filter, CSV. Dasselbe für Eingangsrechnungen (zu zahlen, bezahlt) mit Zahlungen an den Lieferanten.
  Rechnungen, die der Import alter Projekte als bezahlt kennt (PRJ-130), bleiben dort; Zahlungen sind eigene
  Buchungen. API: /documents/{id}/payments (lesen, erfassen), /payments/{id}/void, /incoming-invoices/{id}/payments,
  /accounting/open-items. Dazu: Kontoauszüge (DOK-050), Guthaben (DOK-053). Nicht gebaut: Mahnwesen, Onlinezahlung, Skonto.
- DOK-049 [SOLL · V · S10] ZUGFeRD / Factur-X als Format der Ausgangsrechnung:
  Eine Einstellung (Buchhaltung) wählt das Format der Rechnung: "XRechnung (PDF und XML
  getrennt)" oder "ZUGFeRD / Factur-X (EN 16931): ein PDF mit eingebetteter Rechnung". Im zweiten Fall
  ist die gespeicherte PDF-Datei ein PDF/A-3b, in dem die Rechnungsdaten als CII-XML (`factur-x.xml`, Beziehung
  "Alternative", XMP-Kennung des Profils EN 16931) stecken; die Prüfsumme (DOK-007) gilt für diese Datei, die
  Rechnung bleibt unveränderlich. Der XML-Teil steht auch als eigener Download zur Verfügung. Die Datei ist nach
  dem Aufbau der Spezifikation gebaut und mit eigener Prüfung (DOK-042) und strukturell getestet, aber nicht mit
  einem externen Prüfprogramm (veraPDF, Mustang, KoSIT) validiert. Gutschriften und Stornos folgen dem Format der
  Rechnung. Nur Rechnungen und Stornorechnungen; die Abschlags- und Teilrechnungen tragen den Typ-Code von DOK-034.
- DOK-050 [SOLL · V · S10] Kontoauszug-Import mit Zuordnungsvorschlägen:
  Buchhaltung → Bank liest einen Kontoauszug als CAMT.053 (XML, jede
  Fassung camt.053.001.xx) oder als CSV der Bank (Trennzeichen, Zeichensatz und Kopfzeile werden erkannt). Gespeichert
  werden nur die Buchungen (Tag, Betrag mit Vorzeichen, Gegenseite, IBAN, Verwendungszweck, Ende-zu-Ende-Referenz) und die
  Prüfsumme der Datei; dieselbe Datei wird nicht zweimal gelesen, eine Buchung eines früheren, überlappenden Auszugs
  nicht noch einmal (Fingerabdruck; zwei gleiche Buchungen eines Tages bleiben zwei). XML mit Dokumenttyp-Deklaration
  oder Entitäten wird abgelehnt. Zu jeder offenen Buchung schlägt die Seite Rechnungen vor, nach Rechnungsnummer im
  Verwendungszweck, Betrag gleich dem offenen Rest und Name: Geldeingang → offene Ausgangsrechnungen und Gutschriften von
  Lieferanten, Geldausgang → offene Eingangsrechnungen und Rückzahlungen an Kunden (DOK-053). Ein Vorschlag bucht
  nichts: Erst "Zahlung eintragen" legt die Zahlung nach den Regeln von DOK-048 an und verbindet sie mit der Buchung;
  eine stornierte Zahlung öffnet die Buchung wieder. Eine Buchung lässt sich mit Grund beiseitelegen und
  zurücknehmen. Eine Buchung wird als Ganzes zugeordnet, Teilzahlungen trägt man an der Rechnung ein; Fremdwährung wird
  nicht zugeordnet. Eine CSV-Zeile mit Datum, aber ohne lesbaren Betrag lehnt die Datei ab (nichts wird stillschweigend
  ausgelassen); Stornobuchungen (RvslInd) drehen das Vorzeichen; ein Vorschlag und ein Buchen gehen nur in die Richtung, in
  der bei der Rechnung Geld fließen kann. Rechte: beide Preisrechte und alle Projekte und das Material lesen; Ändern: Projekte überall und
  Material bearbeiten. API: /accounting/bank/imports, /accounting/bank/transactions und …/{id}/book, …/ignore,
  …/restore. Nicht gebaut: MT940, Abruf von der Bank (FinTS), automatisches Buchen, Mahnwesen.
- DOK-051 [SOLL · V · S10] Zahlungen sind auch im Programmcode unveränderlich:
  Das Modell verweigert
  selbst: `update`, `bulk_update` und `delete` auf Zahlungen, das Löschen einer Zahlung, das Überschreiben über eine
  vorhandene Nummer (auch `bulk_create` mit Konfliktupdate) und jede Änderung außer dem einmaligen Stornieren mit Grund
  (Fehler `PaymentLockedError`). Gilt für Zahlungen auf Ausgangs- und Eingangsrechnungen, auch im
  Verwaltungsprogramm. Nicht geschützt: SQL von Hand.
- DOK-052 [SOLL · V · S10] Zahlungen an das Finanzamt in der EÜR: Ein
  Lieferant lässt sich als "Finanzamt – Umsatzsteuer" oder "Finanzamt – Einkommensteuer und andere private Steuern"
  kennzeichnen. Zahlungen an ein Umsatzsteuer-Finanzamt sind keine Betriebsausgabe, sondern werden mit der Umsatzsteuer
  verrechnet (Anzeige "Noch an das Finanzamt zu zahlen"); die anderen stehen für sich und zählen nicht als Ausgabe. Eine
  Erstattung ist eine negative Zahlung. Gewerbesteuer ist eine Ausgabe wie jede andere. Die Kennzeichnung sieht und ändert nur, wer die EÜR sehen darf. Bestandsdaten bleiben
  ungekennzeichnet; nichts wird geraten. API: Feld `tax_office` des Lieferanten und die Summen in /accounting/euer.
- DOK-053 [SOLL · V · S10] Guthaben in den Offenen Posten: Die Seite
  "Guthaben" zeigt, was die Firma zurückzahlen muss (überzahlte Rechnungen, nach der Zahlung stornierte oder gutgeschriebene
  Rechnungen; Altrechnungen des Imports nicht) und was Lieferanten schulden (Gutschriften, zu viel bezahlte
  Eingangsrechnungen), mit Summen und CSV. Die Rückzahlung ist eine negative Zahlung an der Rechnung. Jeder sieht nur die
  Seite, die er sehen darf. API: /accounting/open-items?side=credits.
- DOK-054 [SOLL · V · S10] Export für eine Prüfung als Aufgabe im Hintergrund (ergänzt DOK-046):
  Auf der Seite Archiv und in der API (POST /accounting/audit-export, Antwort 202 mit der
  Aufgabe) lässt sich der ZIP-Export im Hintergrund erstellen, mit Fortschritt; das Ergebnis liegt unter "Aufgaben" und
  ist nur für die anfordernde Person sichtbar und läuft nach der Aufbewahrungsfrist der Ergebnisse ab. Der Download in
  der Anfrage bleibt für kleine Archive.
- DOK-055 [SOLL · V · S10] Buchhaltung ausblenden, wenn Rentalars nicht das Buchhaltungsprogramm ist: Ist die Einstellung aus,
  fehlen im Menü "Buchhaltung" Beleg erfassen, Eingangsbelege, Offene Posten, Bank, EÜR, Archiv (mit Verfahrensdokumentation
  und Prüfer-Export), Anlagenspiegel, Verkäufe aus Bestand und Altprojekte importieren, ebenso die Stellen, die dorthin
  führen (Karte "Anlagevermögen" am Exemplar, "Auch als Eingangsrechnung erfassen?" nach einem Kauf, "Eingangsrechnungen"
  in den Einstellungen). Auch ihre Adressen im Browser (Weiterleitung auf die Startseite mit Hinweis) und in der API
  (Antwort 400, Code accounting_disabled) sind gesperrt. Es bleiben Ausgangsdokumente (Angebot, Auftragsbestätigung,
  Lieferschein, frühere Rechnungen), die Monatsabrechnung der Servicefälle, die Markierung "Rechnung gestellt" und die
  Einstellungen für Lexware Office und DATEV. Hat jemand nur Rechte für ausgeblendete Reiter, entfällt der Menüpunkt.
  Nichts wird gelöscht; wieder eingeschaltet ist alles da. Die Einstellung steht in Einstellungen → Firmendaten und
  Grundeinstellungen in einem eigenen Kasten "Buchhaltung und Rechnungswesen" mit eigenem Speichern; in der API bleibt das
  Feld system.invoices_enabled.
  Bei ausgeschalteter Buchhaltung läuft auch das nächtliche Archiv nicht (DOK-043), und eine vor
  dem Ausschalten eingereihte Übergabe an Lexware Office geht nicht mehr hinaus (sie bleibt als fehlgeschlagen
  stehen).


### 5.11 Oberfläche, Suche, Dashboard (UIX)

- UIX-001 [MUSS · V · S1] Die Oberfläche ist responsive und auf Smartphone,
  Tablet und Desktop vollständig bedienbar.
- UIX-002 [MUSS · A · S1] Globale Suche über Projekte, Kunden, Produkte,
  Material (ID, Seriennummer) und Personen – begrenzt auf die Rechte des
  Nutzers.
- UIX-003 [SOLL · A · S4] Startseite je Rolle: anstehende Projekte, heute zu
  packende und zurückerwartete Projekte, Engpässe, fällige Prüfungen, eigene
  Einsätze, Schnellzugriff Zeiterfassung.
- UIX-004 [MUSS · A · S1] Listen sind sortierbar, filterbar und seitenweise
  ladbar; Filter lassen sich als Link teilen.
- UIX-005 [SOLL · A · S4] Benachrichtigungen in der Anwendung und per E-Mail
  (Einsatzanfrage, Projektänderung, Engpass, Defektmeldung, fällige Prüfung),
  je Nutzer abschaltbar. Jede Art gehört zu einer Kategorie
  wie "System" oder "Projekt", und neben "In Rentalars" und "Per Mail" gibt
  es die Wahl "In der App" für die Begleit-App (UIX-039). Uhrzeit, Abstand und Vorlauf der
  Meldungen über neue Fehlbestände sind eine Einstellung des Betriebs (VFG-036).
  Der Text einer Benachrichtigung steht in der tabellarischen
  Übersicht und in der CSV-Datei als reiner Text mit seinen Zeilenumbrüchen,
  ohne HTML; ebenso die Beschreibung einer Projektvorlage.
- UIX-006 [SOLL · V · S10] Kamerascan von Barcode und QR-Code im Browser
: Ein Dialog mit Kamerabild, Taschenlampe, wo
  das Gerät sie hat, und dem Feld zum Tippen; die Kamera stoppt beim
  Schließen, beim Verlassen der Seite und nach einem doppelten Lesen innerhalb
  von 2,5 Sekunden. Bedienbar mit der Tastatur und für Screenreader; fehlende
  Berechtigung und ein unsicherer Kontext werden erklärt (MAT-027).
- UIX-007 [KANN · A · S10] Installierbar als Web-App auf dem Startbildschirm.
- UIX-008 [MUSS · V · S1] Die gesamte Anwendung erscheint im dunklen Modus,
  mit festen Farbwerten (Design-Token): #EE591F als Hauptfarbe (Schaltflächen,
  Hervorhebungen), #EEEEEE für Text und #727272 für Linien und Zurückhaltendes.
  Die Lesbarkeit geht vor: Text hält gegenüber seinem Hintergrund ein
  Kontrastverhältnis von mindestens 4,5 zu 1 (NFA-023) [A]. Ein heller Modus
  ist vorbereitet – alle Farben stehen an einer Stelle – und wird später
  wählbar [A]. Gedrucktes und PDF bleiben hell.
- UIX-009 [SOLL · A · S1] Die Oberfläche besteht aus vom Server erzeugten
  Seiten. Stellen, die unmittelbar reagieren sollen (Positionen per Ziehen
  sortieren, Verfügbarkeit während der Eingabe, Stoppuhr der Zeiterfassung),
  werden gezielt mit wenig JavaScript ergänzt. Ein eigener Erstellungsschritt
  für die Oberfläche ist nicht nötig.
- UIX-010 [SOLL · V · S8] Chat im Projekt: Jedes Projekt hat einen Chat, den
  jeder liest und schreibt, der das Projekt öffnen darf – auch die Crew mit
  der Einsatzsicht (AUT-023); der Chat sagt das. Eine Nachricht nennt
  Verfasser und Zeit; eigene Nachrichten lassen sich kurze Zeit ändern. Wer
  mit @ erwähnt wird, wird benachrichtigt (UIX-005); ein Zähler nennt die
  ungelesenen Nachrichten. Neue Nachrichten erscheinen über die Abfrage nach
  Änderungen (UIX-020), ohne dauerhafte Verbindung. Die API kennt den Chat.
  Aus einer Code-Prüfung, Oktober 2026: Was als gelesen
  gilt, reicht höchstens bis zur neuesten Nachricht dieses Chats; eine
  Angabe darüber hinaus wird darauf begrenzt, eine Nachricht eines anderen
  Chats wird abgewiesen, und künftige Nachrichten gelten nie schon als
  gelesen. Der Änderungsstempel, an dem die Abfrage nach Änderungen
  (UIX-020) eine Änderung erkennt, ändert sich mit jeder Änderung, auch bei
  mehreren in derselben Sekunde und unter MariaDB wie unter SQLite; das gilt
  für jede Abfrage nach Änderungen, nicht nur für den Chat.
- UIX-011 [MUSS · V · S1] Von jeder Seite unterhalb der Startseiten der
  Bereiche – etwa einem Produkt, einem Exemplar oder einem Formular – führt
  ein "Zurück" oben links zur vorherigen Ansicht, und zwar so, wie sie war:
  zur Liste mit Filter, Sortierung, Seite und Seitenlänge, oder zu dem
  Projekt, aus dem das Produkt geöffnet wurde. Nach Bearbeiten und Speichern
  führt "Zurück" nicht in das Formular, sondern weiterhin dorthin, woher man
  gekommen ist [A]. Die Reiter eines Projekts gelten dabei als eine Seite [A].
  Wer ohne Vorgeschichte ankommt (Lesezeichen, Link aus einer Mail), gelangt
  mit "Zurück" zur Startseite des Bereichs [A]. "Zurück" bleibt
  auch nach der Zurück-Taste des Browsers richtig (UIX-055).
- UIX-012 [MUSS · V · S1] In allen Listen ist wählbar, wie viele Einträge eine
  Seite zeigt; voreingestellt sind 50. Zur Wahl stehen 25, 50, 100 und 200
  [A]. Die Wahl steht wie Filter und Sortierung im Link der Liste (UIX-004)
  und wird je Browser für die als Nächstes geöffneten Listen gemerkt [A].
  Auch eine eigene Zahl, gemerkt je Nutzer und Liste
  (UIX-050).
- UIX-013 [MUSS · V · S1] Produkte und Material stehen in der Navigation
  unter einem Eintrag "Materialverwaltung" mit den Reitern Produkte, Modelle,
  Exemplare, Ohne Produkt, Import – in dieser Reihenfolge. Der Eintrag führt
  zu den Produkten [A]; ein Reiter erscheint nur mit dem Recht auf sein Modul
  [A]. Die Mietstaffeln sind Stammdaten und nur über die Verwaltung
  erreichbar, nicht über den Reiter Produkte.
Die Reiter stehen in der Reihenfolge Produkte, Modelle, Exemplare, Fuhrpark, Offene
  Punkte, Prüfungen, Audit, Import; der Fuhrpark folgt gleich auf die Exemplare.
- UIX-014 [SOLL · V · S1] Angaben, die zusammengehören, stehen in Formularen
  in einer Zeile nebeneinander – allen voran "Von" und "Bis"; auf dem
  Smartphone untereinander, wo der Platz nicht reicht [A]. Mengenfelder und
  die übrigen Eingabefelder der Planung bieten keine früheren Eingaben des
  Browsers zur Auswahl an.
- UIX-015 [MUSS · V · S5] In allen tabellarischen Ansichten lassen sich
  weitere Spalten einblenden und vorhandene ausblenden; die Wahl bleibt je
  Nutzer und Liste erhalten und lässt sich auf die Standardspalten
  zurücksetzen [A]. Ein Klick auf eine Spaltenüberschrift sortiert nach
  dieser Spalte, ein zweiter dreht die Reihenfolge um. Der Export als CSV
  (IMP-005) enthält die gezeigten Spalten. Das gilt für
  jede tabellarische Ansicht, mit einklappbaren Filtern und einer CSV-Datei
  auch mit allen Spalten, und die Zeilen lassen sich nach einer Spalte
  gruppieren (UIX-040). Jede Spaltenüberschrift sortiert
, auch die einer hinzugefügten oder
  berechneten Spalte. Ausgenommen sind nur Spalten ohne sortierbaren Wert,
  etwa mit Knöpfen; sie sind im Code ausdrücklich so gekennzeichnet, mit
  Grund. Ein Test geht alle tabellarischen Ansichten durch und prüft das.

Weitere Anforderungen

- UIX-016 [SOLL · V · S5] Das Logo von Rentalars steht in der Navigation und
  ist das Symbol des Browser-Tabs und des Startbildschirms.
- UIX-017 [MUSS · V · S5] Auf dem Smartphone beginnt das Menü unterhalb der
  Kopfzeile, sodass alle Einträge erreichbar sind. Die Reiter zeigen keine
  eigene Scrollleiste. Auf breiten Bildschirmen nutzt der Inhalt die Breite.
- UIX-018 [SOLL · V · S5] Rückfragen vor dem Löschen und kurze Meldungen
  erscheinen als Dialog der Anwendung, nicht als Fenster des Browsers.
- UIX-019 [SOLL · V · S5] Die Suche der Startseite ist von jeder Seite aus
  erreichbar: oben in der Navigation, auf dem Smartphone über die Lupe und
  mit der Taste "/" [A].
- UIX-020 [SOLL · V · S5] Seiten aktualisieren sich bei Änderungen selbst,
  etwa wenn eine Mail eingeht oder jemand anderes eine Position ändert: Die
  Seite lädt sich neu und bleibt an derselben Stelle. Wer gerade tippt oder
  einen Dialog offen hat, sieht stattdessen einen Hinweis [A]. Der Zähler der
  Benachrichtigungen ist auf jeder Seite aktuell. Die
  Seite lädt auch dann neu, wenn man kurz zuvor selbst etwas gespeichert hat und
  danach jemand anderes etwas ändert – etwa eine Antwort auf eine
  Einsatzanfrage eintrifft (PER-033). Die offene
  Planung folgt auch Änderungen am Bestand und behält beim Speichern ihre
  Scrollposition (UIX-056).
- UIX-021 [SOLL · V · S5] Die Startseite zeigt alle offenen Fehlbestände,
  nicht nur die der nächsten zwei Wochen. Ihre Kästen stehen mit gleichen
  Abständen in einem Raster.
- UIX-022 [SOLL · V · S5] Die Reiter der Planung (Kalender,
  Zeitstrahl, Materialauslastung, Personalplan und Fehlbestände, VFG-028) sind
  Bereiche der Navigation und zeigen kein "Zurück" (UIX-011).
- UIX-023 [SOLL · V · S5] Der Bereich der Verwaltung heißt "Einstellungen".
  Texte der Oberfläche nennen keine Nummern von Anforderungen.
- UIX-024 [SOLL · V · S5] Sprechende Adressen: Ein Projekt ist unter seiner
  Projektnummer erreichbar (/projects/2026-0002/), ein Produkt unter seiner
  Artikelnummer (/products/L-010/). Ältere Links mit der internen Nummer
  führen weiterhin zum Ziel [A], ebenso Links mit der früheren
  Projektnummer (ADM-012) und die mit "P-"
  (/projects/P-2026-0002/, ADM-014). Die API behält ihre Schlüssel.
- UIX-025 [SOLL · V · S5] Bei Zeiträumen folgt "bis" auf "ab": Das Ende kann
  nicht vor dem Beginn liegen, und wird der Beginn verschoben, wandert das
  Ende mit gleicher Dauer mit [A]. Ein Kalender wählt Beginn und Ende
  nacheinander mit zwei Klicks. Er zeigt den jeweils anderen
  Zeitraum schraffiert (PRJ-099), und jedes einzelne Datums- und Zeitfeld
  öffnet einen Kalender mit Ziffernblatt (UIX-036).

Weitere Anforderungen

- UIX-026 [SOLL · V · S6] Der Menüpunkt "Mein Bereich" bündelt, was jede
  Person für sich tut: Verfügbarkeit (PER-028), eigene Zeiten und
  Personaldaten. Freigeben und die Auswertung der Zeiten anderer sind
  Reiter von "Personal"; wer nur die eigenen Zeiten sieht, findet die
  Auswertung in "Mein Bereich". Der Menüpunkt "Zeiterfassung" entfällt,
  "Zeit erfassen" bleibt.
- UIX-027 [SOLL · V · S6] Reiter sind überall gleich: Die Reiter unter einem
  Menüpunkt sind Startseiten und zeigen kein "Zurück", die Seiten darunter
  immer (UIX-011); die Reiter eines Datensatzes zählen für "Zurück" als eine
  Seite. Auf dem Smartphone steht "Zurück" stets oben links. Der Kopf einer
  Seite ist immer gleich hoch; Erläuterungen stehen unter den Reitern, nicht
  im Kopf.

Weitere Anforderungen

- UIX-028 [KANN · V · S10] Benachrichtigungen (UIX-005) über offene
  Fehlbestände oder offene Punkte eines Projekts eine einstellbare Zahl von
  Tagen vor seinem Beginn. Der Vorlauf der Meldungen
  über neue Fehlbestände ist einstellbar (VFG-036); die Erinnerung je Projekt
  vor seinem Beginn bleibt KANN.
- UIX-029 [SOLL · V · S8] Deutsch und Englisch: Die Sprache der
  Oberfläche – Deutsch oder Englisch – wählt jede Person für sich
  (NFA-026), unter "Mein Konto", in der Nutzerverwaltung und über die API;
  voreingestellt ist die Sprache der Installation. Die Anmeldeseite und
  Seiten ohne Anmeldung folgen der Sprache des Browsers. In der gewählten
  Sprache erscheint alles, was die Person bekommt: Seiten, Meldungen, Mails
  und Benachrichtigungen an sie, PDFs, die sie für sich herunterlädt, etwa
  Zeitnachweise, und Fehlermeldungen der API. Englisch ist britisches
  Englisch mit Datum dd/mm/yyyy und 24-Stunden-Zeit; Eingabefelder nehmen
  das gezeigte Format an. Die Sprache der Dokumente für Kunden – Angebote,
  Auftragsbestätigungen, Lieferscheine, Rechnungen, Stornorechnungen,
  Packlisten und die übrigen Dokumente sowie Mails aus Vorlagen und
  Automationen an Kunden – ist eine Einstellung für den ganzen Betrieb
  ("Sprache der Dokumente"). Sie gilt für die festen Texte der Dokumente;
  was der Betrieb selbst geschrieben hat – Textbausteine, Vorlagen,
  Produktnamen –, bleibt, wie es ist, und das sagt die Einstellung. Die
  E-Rechnung behält ihre vorgeschriebenen Codes. Die Platzhalter der
  Automationen gibt es auch englisch ({company}, {date} …); die deutschen
  ({firma}, {datum} …) gelten weiter. Das Benutzerhandbuch gibt es in
  beiden Sprachen (NFA-047); "Handbuch" in der Seitenleiste öffnet es in
  der Anwendung in der Sprache der Person, mit Inhaltsverzeichnis – fehlt
  das englische, das deutsche mit einem Hinweis. Auch die Bezeichnungen und Hilfetexte der Felder sind
  richtiges Englisch – ohne "packlist", "debitor", "o'clock" oder deutsche
  Texte wie "Sachkontenlänge…" –, ebenso die Namen der voreingestellten
  Zuschläge (etwa "Night 0–4"); die deutsche Oberfläche bleibt, wie sie
  ist, und das englische Handbuch folgt den neuen Bezeichnungen.

Weitere Anforderungen

- UIX-030 [SOLL · V · S6] Über den Listen (UIX-004) stehen die Filter hinter
  der Schaltfläche "Filter"; das Suchfeld davor bleibt sichtbar, und Enter
  darin sucht auch bei eingeklappten Filtern. Die
  Schaltfläche nennt die Zahl der gesetzten Filter ("Filter (2)"); solange
  sie eingeklappt sind, stehen die gesetzten daneben ("Status: Bestätigt").
  Ob die Filter einer Liste offen sind, merkt sich Rentalars je Gerät; ohne
  JavaScript stehen sie offen da. Das gilt für Projekte, Exemplare, Modelle,
  Produkte, Prüfungen, Kunden, Veranstaltungsorte, Personal, Zeiten
  freigeben und auswerten, Fehlbestände, Mail-, Änderungs-, Zugriffs- und
  Sicherheitsprotokoll und die Zustellungen eines Webhooks. Die Filter
  sind auf jeder Bildschirmbreite zunächst eingeklappt (UIX-038).
- UIX-031 [SOLL · V · S6] Unter der Versionsnummer in der Seitenleiste und
  unter dem Anmeldefenster steht der Urhebervermerk "von fld-vt.de" mit Link
  auf dessen Webseite, die sich in einem neuen Tab öffnet. Die Lizenz
  (NFA-052) erlaubt den Vermerk; wer Rentalars weitergibt, muss ihn
  stehen lassen und darf ihn ergänzen, aber nicht entfernen, verdecken oder
  ersetzen (NFA-075, ADDITIONAL-TERMS.md). Ein Link "Über Rentalars" führt zur
  Seite mit den Lizenzhinweisen (UIX-062).
- UIX-032 [SOLL · V · S6] Unter dem Logo und "Rentalars" steht in der
  Seitenleiste klein der Name des Unternehmens aus den Firmendaten
  (ADM-001), damit immer zu sehen ist, in welcher Installation man arbeitet;
  auf dem Smartphone in der oberen Leiste unter "Rentalars", auf sehr
  schmalen Bildschirmen oben im geöffneten Menü. Ein geänderter Name gilt ab
  der nächsten Seite.
- UIX-033 [SOLL · V · S8] An Adressen – eines Veranstaltungsorts, eines
  Kunden und seiner Adressen, eines Lieferanten, wenn er eine hat, und der
  eigenen Firma – führt der Link "Route in Google Maps" in einem neuen Tab
  in die Routenplanung von Google Maps, wo es sinnvoll ist, vom Lager aus
  (PRJ-097). Die Adresse verlässt Rentalars erst mit diesem Klick
  (NFA-050). Jeder Routenlink beginnt am aktuellen
  Standort dessen, der ihn öffnet: Rentalars
  gibt keinen Start mit, Google Maps nimmt dann den Standort – überall, auch
  vom Lager aus. Eine Fahrt mit Zwischenzielen (PRJ-097) behält diese und
  ihr Ziel; nur ihr Start ist der Standort.
  Die Karte eines Lieferanten und die Vorschläge im Lieferantenfeld (PRJ-101) sehen nur, wer Material oder
  die Verwaltung lesen oder Projekte ändern darf; die Rollen "Crew" und "Freie Kraft" bekommen 403.
- UIX-034 [SOLL · V · S8] An Adressen zeigt Rentalars eine zoombare Karte von
  OpenStreetMap. Sie lädt erst nach einem Klick auf "Karte anzeigen", sodass
  vorher weder eine Adresse noch eine Anfrage nach Kartenkacheln das Haus
  verlässt (NFA-050); eine Einstellung kann Karten sofort laden lassen. Die
  Koordinaten fragt der Server einmal je Adresse bei Nominatim
  (OpenStreetMap) ab und speichert sie; die Lage lässt sich von Hand
  korrigieren. Die Kacheln lädt der Browser vom Kachelserver von
  OpenStreetMap. Die Adressen beider Dienste stehen in der
  Konfigurationsdatei (NFA-032), sodass sich ein eigener Server nutzen
  lässt. Die Karte nennt "© OpenStreetMap-Mitwirkende"; ihre Bibliothek
  liefert Rentalars selbst aus. Damit ist entschieden,
  ob und wie eine Karte zu NFA-050 passt – erst nach einem
  Klick. Die Kacheln fragt der Browser mit einem Referer an,
  wie es die Nutzungsregeln des Kachelservers von OpenStreetMap verlangen –
  der Herkunft der Installation, nicht der Adresse der Seite.
  Die übrigen Regeln gelten: Namensnennung, keine
  Massenabrufe, keine Kacheln vor "Karte anzeigen" (außer mit der
  Einstellung, Karten sofort zu laden), und der Server fragt Nominatim mit
  einer gültigen Kennung (User-Agent) an (3.3).

Ausbaustufe 7: Weitere Anforderungen

- UIX-035 [SOLL · V · S7] Pflichtfelder sind in allen Formularen mit einem
  roten Sternchen * gekennzeichnet, und oben im Formular steht einmal
  "* Pflichtfeld" – auch beim Preis eines neuen Produkts. Was nur unter einer Bedingung Pflicht ist, bekommt das
  Sternchen, sobald die Bedingung erfüllt ist: beim Produkt der Preis außer
  bei Verkaufsware, der Verkaufspreis bei Verkaufsware, der Prozentsatz eines
  prozentualen Aufpreises, der Eigentümer bei Kundenmaterial und die Staffel,
  wenn eine abweichende gewählt ist; der Kunde eines Projekts, das nicht
  intern ist; Server und Zugangsdaten eines aktiven Postfachs je nach seinen
  Aufgaben. Vorlesende Programme erfahren es aus dem Feld selbst, nicht aus
  dem Sternchen. Die Prüfung beim Speichern bleibt davon unberührt. Die Regel
  gilt ausnahmslos, mit Test (UIX-051).
- UIX-036 [SOLL · V · S7] Jedes Datums- und Zeitfeld – etwa "Von" und "Bis"
  einer Phase – hat rechts ein Kalender- oder Uhrsymbol. Es öffnet einen
  Kalender in der Gestaltung von "Zeitraum im Kalender wählen" (UIX-025). Ein
  Datum wird mit einem Tipp auf den Tag übernommen. Bei Datum und Uhrzeit
  folgt die Uhrzeit auf einem Ziffernblatt wie in der Kalender-App unter
  Android: erst die Stunde (außen 1 bis 12, innen 13 bis 23 und 00), dann die
  Minute in Fünferschritten, durch Ziehen oder Eintippen jede Minute;
  "Übernehmen" setzt den Wert. "Heute" bzw. "Jetzt" setzt den aktuellen Wert,
  "Leeren" gibt es nur bei freiwilligen Feldern. Alles geht auch mit der
  Tastatur (Alt+↓ im Feld, Pfeiltasten, Enter, Esc). Auf dem Smartphone öffnet
  schon ein Tipp ins Feld die Auswahl, und Datum und Uhrzeit kommen
  nacheinander. Eintippen ins Feld bleibt möglich; ohne JavaScript gilt der
  Kalender des Browsers. Ein Feld zeigt nur dieses
  Symbol, nicht zusätzlich das des Browsers (UIX-042).
- UIX-037 [SOLL · V · S7] Die API-Dokumentation öffnet sich in einem neuen
  Tab, aus den Einstellungen wie von den Webhooks aus.

Ausbaustufe 7: Weitere Anforderungen

- UIX-038 [SOLL · V · S7] Die Filter über den Listen (UIX-030) sind auf jeder
  Bildschirmbreite zunächst eingeklappt. Hat
  jemand die Filter einer Liste auf- oder zugeklappt, gilt diese
  Wahl; ein Filter mit einem Fehler ist nie eingeklappt. Das
  gilt ausnahmslos für jede tabellarische Ansicht:
  auch unter Materialverwaltung – Produkte, Modelle, Exemplare und
  die übrigen Reiter – und in den Listen der Stammdaten (ADM-007). Auch
  eingeklappt ist zu sehen, dass und wonach gefiltert ist – an der Zahl auf
  der Schaltfläche und an den gesetzten Filtern daneben (UIX-030).

Ausbaustufe 8: Weitere Anforderungen

- UIX-039 [SOLL · V · S8] Die Arten der Benachrichtigungen (UIX-005) gehören
  zu Kategorien: "System" (etwa Probleme mit Mails oder Kalendern, Fehler der
  Anwendung, Aufgaben im Hintergrund), "Projekt" (etwa Einsatzanfragen und
  Antworten, neue Mail zum Projekt, Erwähnung im Chat, Wiedervorlagen,
  Änderungen am Projekt, Fehlbestände, Automationen), "Material", "Personal"
  und weitere. Unter Benachrichtigungen → Einstellungen stehen die Arten
  ("Worüber") nach Kategorien gruppiert und sortiert; die Liste der
  Benachrichtigungen lässt sich nach Kategorie filtern. Neben "In Rentalars"
  und "Per Mail" gibt es die Spalte "In der App": ob die Begleit-App (5.16)
  die Art als Benachrichtigung auf dem Telefon zeigt. Rentalars speichert nur
  die Wahl und nennt sie in der API an jeder Benachrichtigung und in den
  Einstellungen, ebenso die Kategorie; die App wird getrennt gebaut.
  Voreingestellt ist "In der App" für Arten, die die Person selbst
  betreffen, etwa Einsatzanfragen, Erwähnungen im Chat und Wiedervorlagen
  [A].
- UIX-040 [SOLL · V · S8] In jeder tabellarischen Ansicht – jeder Seite mit
  einer Liste von Datensätzen, etwa Servicefälle, Spesen, Meine Spesen,
  Anfragen, Automationen und ihr Protokoll, Benachrichtigungen, Showfiles,
  Mail-Protokoll, Nutzer, Rollen und Änderungsprotokoll – sind die Filter
  einklappbar (UIX-030, UIX-038), die Spalten wählbar (UIX-015), die Ansicht
  als CSV exportierbar, wie gezeigt und mit allen Spalten, und ein Klick auf
  eine Spaltenüberschrift sortiert nach ihr. Es lässt sich nach jeder
  eingeblendeten Spalte gruppieren ("Gruppieren nach", neben der Wahl der
  Spalten, UIX-044): Die
  Zeilen stehen dann unter einer Überschrift je Wert mit ihrer Anzahl; die
  CSV-Datei bleibt davon unberührt. Kleine Tabellen innerhalb einer Seite,
  etwa die Positionen eines Projekts, sind keine tabellarischen Ansichten.
  Jede Spalte sortiert (UIX-015), und die Filter sind in
  jeder Ansicht zunächst eingeklappt, auch unter Materialverwaltung
  (UIX-038); auch "Meine Einsätze" ist eine tabellarische Ansicht
  (UIX-043).
- UIX-041 [SOLL · V · S8] Seiten, die man über die Hauptnavigation erreicht,
  zeigen kein "Zurück" (UIX-011, UIX-022, UIX-027) – auch Servicefälle,
  Spesen und Meine Spesen. Das ist eine Regel
  für jede künftige Seite: Ein Test geht alle Einträge der Hauptnavigation
  durch und prüft, dass keine dieser Seiten einen Zurück-Knopf zeigt.
- UIX-042 [SOLL · V · S8] Datums- und Zeitfelder zeigen nur die Auswahl von
  Rentalars (UIX-036), nicht zusätzlich das Kalendersymbol des Browsers.
  Eintippen mit der Tastatur bleibt möglich.

Ausbaustufe 8: Weitere Anforderungen

- UIX-043 [SOLL · V · S8] "Mein Bereich" (UIX-026) hat als ersten Reiter
  "Meine Einsätze" und öffnet mit ihm: die eigenen Einsätze als
  tabellarische Ansicht (UIX-040) mit Filtern für Zeitraum, Status und
  Projekt, wählbaren Spalten, Sortieren, Gruppieren und CSV. Der Kasten
  "Meine Einsätze" der Startseite (UIX-003) führt zu diesem
  Reiter.

Ausbaustufe 8: Weitere Anforderungen

- UIX-044 [SOLL · V · S8] Im Auswahlfeld "Gruppieren nach" (UIX-040) ist
  jede eingeblendete Spalte wählbar, in der Reihenfolge der gezeigten
  Spalten – in jeder tabellarischen Ansicht, auch in den Listen der
  Stammdaten (ADM-007). Werte, die nur
  Rentalars berechnet, gruppiert es wie beim Sortieren bei Listen bis
  2.000 Zeilen, bei längeren mit demselben Hinweis (UIX-015). Ausgenommen
  sind nur Spalten ohne Wert zum Gruppieren, etwa mit Knöpfen oder
  Kästchen; sie sind im Code ausdrücklich so gekennzeichnet, mit Grund. Ein
  Test geht alle tabellarischen Ansichten durch und prüft das.

Ausbaustufe 8: Weitere Anforderungen

- UIX-045 [SOLL · V · S8] Menü auf dem Smartphone als Schublade: Bei der Breite, bei der die Seitenleiste zum Menü
  wird, gleitet das Menü wie in der Begleit-App von der Seite herein – von
  rechts, wo der Menüknopf sitzt – und liegt über der abgedunkelten Seite.
  Es schließt mit einem Tipp auf die abgedunkelte Seite, mit Escape, mit
  einem Knopf "Schließen" und durch Zurückwischen. Solange es offen ist,
  bleibt der Fokus darin; danach steht er wieder auf dem Menüknopf. Wer
  weniger Bewegung eingestellt hat (prefers-reduced-motion), bekommt es ohne
  Gleiten. Es funktioniert im dunklen wie im hellen Modus und besteht die
  Prüfung auf Barrierearmut (NFA-025). Umgebaut wird nur die Ansicht für das Telefon: Die Schublade gilt bis 900
  Pixel Fensterbreite, wo oben die Leiste mit dem Menüknopf steht; darüber
  bleibt die Seitenleiste unverändert. Geöffnet wird sie auch durch Wischen
  von rechts, und die Zurück-Taste schließt sie, ohne die Seite zu
  verlassen.


Ausbaustufe 8: Weitere Anforderungen

- UIX-046 [SOLL · V · S8] Einstellungen geordnet: Die Seite der Einstellungen ordnet ihre Links
  nach Themen, je ein Kasten mit Symbol: Firma (Firmendaten, Nummernkreise,
  Etiketten), Nutzer und Rechte, Abläufe (Automationen,
  Benachrichtigungen, KI), Projekte und Personal (Zuschläge, Staffeln,
  Funktionen), E-Mail, Dokumente und Buchhaltung, Stammdaten, Import und
  Export, Schnittstelle für andere Programme sowie Betrieb und Sicherheit
  (Selbsttest, Sicherung, Verschlüsselung, Serveradresse, Änderungs-,
  Sicherheits- und Zugriffsprotokoll). Die
  Kästen stehen in Spalten, die ohne Lücken aufschließen.
- UIX-047 [SOLL · V · S8] Fuß der Seitenleiste: Die Einträge stehen untereinander, je eine
  eigene Zeile mit Symbol und genug Höhe zum Tippen.
- UIX-048 [SOLL · V · S8] Aktionsleiste der Mehrfachauswahl: Wo Zeilen
  angehakt werden, um mit ihnen etwas zu tun – Exemplare, Anfragen –,
  erscheint die Leiste mit der Zahl der gewählten und ihren Knöpfen erst,
  wenn etwas angehakt ist, wie die "gewählten Positionen" der Planung
  (PRJ-082): beim Scrollen bleibt sie am unteren Rand angedockt; "Auswahl
  aufheben" nimmt alle Haken weg und blendet sie aus. Ohne Skripte steht
  sie unter der Liste.

Ausbaustufe 9: Weitere Anforderungen

- UIX-049 [SOLL · V · S9] Fotos und Videos im Chat: Eine Chatnachricht (UIX-010)
  kann Fotos und Videos tragen, auch ohne Text, am Handy direkt aus der Kamera
  – bis 10 Dateien, Fotos bis 25 MB (PNG, GIF und WebP bis 16 Megapixel),
  Videos bis 200 MB, 20 Minuten und 4096 Pixel. Geprüft wird der Inhalt, nicht
  die Endung, und die Größe, bevor ein Bild entpackt wird. Behalten wird nur
  die verkleinerte Fassung: Fotos aufrecht, höchstens 2048 Pixel, nur mit
  dem Standort als Angabe (NFA-084; vorher ganz ohne Metadaten); Videos im Hintergrund mit ffmpeg auf höchstens 720p
  (H.264/AAC, MP4), eines nach dem anderen, bis dahin "Video wird verkleinert
  …"; misslingt es, wird das Video verworfen und die Nachricht sagt es. Sehen
  darf sie, wer den Chat lesen darf; sie gehen mit der Nachricht. API:
  attachments, POST mit Dateien.
- UIX-050 [SOLL · V · S9] Einträge je Seite in jeder Tabelle: Jede Liste, die seitenweise
  lädt – auch die Listen der Stammdaten (ADM-007) –, bietet neben 25, 50, 100
  und 200 (UIX-012) eine selbst eingetippte ganze Zahl von 5 bis 1.000
  ("Eigene Anzahl"); andere Eingaben werden mit Hinweis am Feld abgewiesen.
  Die Wahl steht im Link (?per_page=) und wird je Nutzer und Liste gemerkt,
  auch über Anmeldungen und Geräte hinweg; der Link geht vor. Ohne JavaScript
  bedienbar. Ausgenommen sind Tabellen, die als Ganzes ein Formular oder eine
  Summe sind (Freigeben, Meine Zeiten und Spesen, Summen der Auswertungen,
  Regeln der Automationen). Ein Test prüft jede Tabelle.
- UIX-051 [SOLL · V · S9] Pflichtfelder überall gekennzeichnet:
  UIX-035 gilt ausnahmslos – in Seiten, Dialogen, von Hand geschriebenen
  Formularen und den Formularen der Stammdaten; eine Gruppe von Auswahlknöpfen
  trägt das Sternchen an ihrer Überschrift, ein bedingtes Pflichtfeld, solange
  die Bedingung gilt. Für Bildschirmleser ist das Feld als erforderlich
  gekennzeichnet. Ein Test geht alle Seiten und Dialoge eines Administrators
  durch.

Ausbaustufe 9: Weitere Anforderungen

- UIX-052 [SOLL · V · S9] Jede Benachrichtigung einstellbar: Jede Art von Benachrichtigung lässt sich unter Mein Konto →
  Benachrichtigungen und über die API je Kanal schalten ("In Rentalars", "Per
  Mail", "In der App"); Ausnahmen stünden ausdrücklich mit Begründung im Code,
  derzeit gibt es keine, und ein Test prüft jede Art. "Eine Aufgabe im
  Hintergrund ist fertig (z. B. KI-Zusammenfassung, Antwortentwurf, Rechnung
  lesen, Export)" steht als erste Art unter "System"; ganz ausgeschaltet kommt
  auf keinem Kanal etwas an.

Ausbaustufe 9: Weitere Anforderungen

- UIX-053 [SOLL · V · S9] Eingabezeilen der Planung einheitlich: Die Zeilen zum Hinzufügen in der
  Planung (Material, Personal, Logistik) haben ein gemeinsames Layout: alle
  Felder in einer Linie und gleich hoch, Hilfetexte unter der Zeile, Knöpfe
  und das Kästchen "Fest eingeplant" auf der Höhe der Felder; auf dem Telefon
  stehen sie untereinander.
- UIX-054 [SOLL · V · S9] Jahresauswahl mit drei Folgejahren: Die
  Auswahlen eines Jahres (Auswertungen) bieten fünf Jahre zurück und drei
  voraus; vorgewählt ist das laufende Jahr, ein in der Adresse gewähltes Jahr
  bleibt erhalten.
- UIX-055 [SOLL · V · S9] Zurück nach der Zurück-Taste des Browsers: Die Taste "Zurück" von Rentalars führt auch
  nach der Zurück-Taste des Browsers auf die zuletzt geöffnete Seite
  (UIX-011): beim Klick wird der Weg auf die Seite gekürzt, von der man kommt.

Ausbaustufe 10: Weitere Anforderungen

- UIX-056 [SOLL · V · S10] Die Planung bleibt, wo sie ist: Eine offene Planung folgt Änderungen am Bestand (Modelle, Exemplare,
  Produkte und Sets, Positionen anderer Projekte, UIX-020): Beim
  Zurückwechseln zum Tab und alle 20 Sekunden holt sie nur die
  Verfügbarkeitsspalte, die Wunschhinweise und die Hinweise über den
  Positionen neu, ohne Eingaben, Scrollposition oder Dialoge anzutasten;
  eigene Änderungen lösen das nicht aus. Das Speichern einer Gruppe,
  Teilgruppe oder Position behält Scrollposition und geöffnete Bereiche.
- UIX-057 [SOLL · V · S10] Handbuch in Seiten je Kapitel: /manual/ ist das Inhaltsverzeichnis mit Suche; jedes Kapitel
  hat seine Seite unter /manual/1/, /manual/2/ …, mit Kapitelliste und
  "Voriges"/"Nächstes Kapitel"; ein unbekanntes Kapitel ergibt 404. Alte Links
  der Form /manual/#abschnitt führen zum richtigen Kapitel; die Hilfelinks der
  Anwendung zeigen auf die Kapitelseiten. Ein Kapitel wird beim ersten Aufruf
  gerendert und gehalten, bis sich die Datei ändert. Gemessen: Kapitel von
  14 bis 55 KB (UIX-029).

Ausbaustufe 10: Weitere Anforderungen

- UIX-058 [SOLL · V · S10] Auswahl und Massenaktionen in den Tabellen: Jede Tabelle mit eigenen
  Einträgen hat vor den Zeilen ein Kästchen, in der Kopfzeile eines für die
  Seite. Wer etwas gewählt hat, sieht unten die Leiste mit der Zahl der
  gewählten Zeilen, "Auswahl als CSV herunterladen" (nur die gewählten Zeilen
  mit den eingestellten Spalten) und "Auswahl aufheben"; Seiten fügen eigene
  Aktionen hinzu (PRJ-133, PRJ-134, DOK-038). Bis zu 1.000 Zeilen lassen sich
  zusammen wählen (ab etwa 150 merkt sich die Sitzung die Auswahl, die Adresse
  bleibt kurz); Tabellen mit berechneten Zeilen ohne eigenen Eintrag haben
  keine Kästchen; Exemplare, Prüfungen und offene To-dos mit Schreibrecht
  behalten ihre eigene Leiste ohne CSV. Ohne JavaScript bleibt die Tabelle
  benutzbar.
- UIX-059 [SOLL · V · S10] Betriebsanleitungen im Handbuch verlinkt: Das Handbuch in Rentalars verlinkt die Anleitungen für den
  Betrieb – Installation, Betrieb, Aktualisierung, Sicherung, Verschlüsselung
  und Import – als eigene Seiten unter /manual/guides/<Name>/ (in der Sprache
  des Kontos, mit Rückweg zum Handbuch); Verweise auf diese Dateien im Text
  des Handbuchs sind Links statt Text. Die Seiten sehen alle angemeldeten
  Nutzer wie das Handbuch selbst; sie enthalten keine Zugangsdaten.
- UIX-062 [SOLL · V · S10] Seite "Über Rentalars": Unter /about/, erreichbar über einen Link neben dem Urhebervermerk in der Seitenleiste und unter dem
  Anmeldefenster, auch ohne Anmeldung, stehen die Lizenzhinweise (die "Appropriate Legal Notices" der GPL): Rentalars ist freie
  Software unter der GNU General Public License ab Version 3, ohne jede Gewährleistung; der Urhebervermerk mit dem Hinweis
  auf die zusätzliche Bestimmung (nur wer Rentalars weitergibt, muss ihn behalten, UIX-031, NFA-075); der Name des
  Rechteinhabers (COPYRIGHT_HOLDER in rentalars/__init__.py: "Lars Wilting, fld-vt.de"; wer eine eigene Fassung weitergibt, trägt dort den eigenen Namen ein) und das Jahr; die
  vollständigen Texte (LICENSE, ADDITIONAL-TERMS.md, THIRD-PARTY.md) als Textseiten unter /about/<Name>.txt. Nichts davon ist
  ein Geheimnis; die Seite zeigt keine Daten der Installation.
- UIX-063 [SOLL · V · S10] Einheitliche Begriffe, Schreibweisen und Bedienung: Für dieselbe Sache steht überall dasselbe Wort (Glossar in docs/dev/glossary.md: Exemplar, Behälter,
  Crew, Personal, unterwegs). Die Oberfläche duzt; Texte an Kunden siezen. Eine Anzahl steht im richtigen Numerus (ngettext),
  nie als "Position(en)" oder "1 Tage". Ein Wort mit zwei Bedeutungen hat einen Kontext (pgettext). Der erste Buchstabe wird
  mit capfirst groß geschrieben. Datumsangaben haben ein vierstelliges Jahr und folgen der Sprache des Lesers, Zahlen in
  Verläufen ebenso. Eine Auswahl ohne Wert heißt "– bitte wählen –". Statusnamen sagen, was sie bedeuten: Packliste
  "zurückgenommen", Servicefall "zurückgestellt", Projekt "Bestätigt – Preise und Einzelheiten offen". Was Daten löscht oder
  entfernt oder fremde Datensätze umschreibt (Abwesenheit löschen, Zubehör und Ersatz entfernen, Bestandteil eines Sets,
  Produktänderungen in einem oder allen Projekten übernehmen), fragt vorher; die Frage nennt die Zahl der betroffenen
  Projekte. Die Einstellungen sind ein Formular in Abschnitten mit einem Knopf; ein Fehler speichert nichts; wer die Seite mit
  ungespeicherten Änderungen verlässt, wird gefragt. Nicht gebaut: das Zurücknehmen der Massenübernahme von Produktänderungen.
- UIX-064 [SOLL · V · S10] Darstellung auf dem Telefon und im schmalen Fenster: Bei 390 Pixel Breite scrollt keine Seite seitlich; ein Formular neben einem Reiter öffnet als Blatt am
  unteren Rand; die Aktionen eines Projekts stehen in zwei Spalten, der Status in einer Zeile; Knöpfe mit Symbol sind
  mindestens 40 Pixel groß; die feste Leiste der Packliste ist eine Zeile hoch; Reiterleisten und Tabellen, die breiter als
  ihr Kasten sind, zeigen am Rand einen Schatten, wo mehr folgt. Die Lizenztexte sind Seiten des Programms (/about/<Name>/)
  mit Viewport und Rückweg; Zeilen von Fließtext sind höchstens etwa 75 Zeichen lang; die Einstellungen stehen in einer
  lesbaren Spalte; Erklärungen stehen in den Kästen, nicht lose zwischen ihnen. Nicht gebaut: kompakte Zeilen für Planung und
  Produktliste auf dem Telefon, ein einheitlicher Suchen-Knopf, die Gestaltung des Chats.


### 5.12 Import und Export (IMP)

- IMP-001 [MUSS · A · S5] Import von Material, Produkten, Kunden und Personen
  aus CSV- bzw. Tabellendateien, damit bestehende Listen übernommen werden
  können.
  Eine Tabelle darf höchstens 100.000 Zeilen und 3 Millionen Zellen haben, eine XLSX-Datei
  entpackt höchstens 200 MB; größere Dateien werden beim Lesen abgewiesen, bevor sie den Speicher füllen.
  Mehr als 300.000 gelesene Zeilen, leere eingerechnet, werden abgewiesen (mit dem Rat, leere Zeilen unter den
  Daten zu löschen); eine XLSX-Datei wird nur bis Spalte 199 gelesen, eine Überschrift darüber wird abgewiesen. Eine Datei mit
  einer Million formatierter leerer Zeilen ist in Sekunden abgewiesen; es werden keine Daten stillschweigend übergangen.
- IMP-002 [MUSS · A · S1] Der Materialimport akzeptiert die 13 Spalten aus
  MAT-011 in einer Zeile je Exemplar und legt daraus Modelle und Instanzen an;
  gleiche Artikelnamen werden zu einem Modell zusammengeführt.
- IMP-003 [MUSS · A · S1] Spaltenzuordnung beim Import frei wählbar; Probelauf
  mit Fehlerbericht vor dem endgültigen Import.
- IMP-004 [SOLL · A · S1] Wiederholter Import aktualisiert vorhandene
  Datensätze anhand der ID statt Dubletten anzulegen.
- IMP-005 [MUSS · A · S5] Export aller Listen als CSV in der aktuell
  gefilterten Ansicht.
- IMP-006 [SOLL · A · S5] Vollständiger Datenexport des Systems in einem
  offenen Format. Er steht unter Einstellungen → Sicherung
  ("Lesbarer Export aller Daten"; der Export steht nur dort), mit einem Absatz
  zum Unterschied: Die Sicherung stellt Rentalars wieder her (ganze Datenbank
  mit allen Geheimnissen, Konfiguration, Dateien, verschlüsselt, wenn
  eingeschaltet); der Export ist zum Lesen da (JSON, CSV und Dateien ohne
  Passwörter und Schlüssel, mit internen IDs). Klartext je Import: IMP-017.

Übernahme der Bestandsdaten per Skript

- IMP-007 [MUSS · V · S1] Die vorhandene Material-Tabelle (Excel) wird per
  Skript übernommen: Ein Befehl auf dem Server liest die Tabelle (XLSX oder
  CSV) und legt daraus Kategorien, Händler, Modelle und Instanzen an – ohne
  Handarbeit in der Oberfläche.
- IMP-008 [MUSS · V · S1] Bestehende IDs (vierstellige fortlaufende Zahlen,
  derzeit 0001 bis 1650) werden unverändert samt führender Nullen übernommen
  und auf Eindeutigkeit geprüft. Der Nummernkreis für neue IDs setzt hinter der
  höchsten übernommenen ID fort.
- IMP-009 [MUSS · A · S1] Das Skript nutzt dieselbe Prüflogik wie der Import in
  der Oberfläche (IMP-002, IMP-003): Probelauf ohne Schreiben, Fehlerbericht
  mit Zeilennummer und Grund, Import ganz oder gar nicht.
- IMP-010 [MUSS · V · S1] Die Spalte "Einsatz/Verbindung" wird in einem zweiten
  Durchlauf aufgelöst, weil sie auf IDs derselben Tabelle verweist. Unbekannte
  IDs und Kreisbezüge werden gemeldet. Jeder Eintrag mit einer Angabe wird als
  "fest verbaut" übernommen; die betroffenen Exemplare werden aufgelistet,
  damit sich einzelne danach auf "lose enthalten" umstellen lassen.
  Die Verbindung ist eine Zelle mit genau
  einer ID (`500`, `#0500`, `500.0`). Stehen mehrere IDs darin (`#0123,
  #1234`) – ein Exemplar kann nur in einem anderen verbaut sein – oder
  Freitext, ist das kein Fehler mehr: es wird keine Verbindung gemacht, der
  Text kommt als "Einsatz/Verbindung: …" in die Notiz des Exemplars (hinter
  eine Notiz aus der Datei) und der Bericht nennt die Zeile als Hinweis, in
  der Vorschau, im Bericht, in der API und im Befehl. Zudem
  gilt für jede Angabe, die sich nicht lesen oder nicht
  annehmen lässt (eine einzelne ID, die es nicht gibt, ein Kaufpreis wie
  "neun", ein Datum, eine Schutzklasse, ein Status, eine Menge, ein Verweis auf
  ein Set ins Leere), dasselbe wie für mehrere IDs: Sie ist kein Fehler mehr,
  das Exemplar wird ohne die Angabe übernommen (ein vorhandenes behält den
  alten Wert), bekommt den Status "Fehler Import" (MAT-020), und seine Notiz
  nennt je Angabe eine Zeile "<Überschrift der Spalte>: <Zelle>" (je Zeile nur
  einmal); ein späterer Import ohne das Problem gibt das Exemplar wieder frei.
  Der Import warnt, wenn die Spalte der
  Artikelnamen einen Status enthält ("verfügbar": vermutlich falsch
  zugeordnet) und wenn eine Zeile ein vorhandenes Exemplar in ein anderes
  Materialmodell verschiebt; das Materialmodell ist keine eigene Spalte, es
  folgt aus Artikelname und Kategorie.
  Fehler bleiben, wo es keinen Ersatz gibt: fehlende oder doppelte ID, fehlender
  Artikelname oder fehlende Kategorie, ein Exemplar außerhalb der Datei, das ein
  Set im Set verbietet. Hat ein Exemplar noch eine Menge aus früherer Zeit,
  die Datei nennt aber ein Einzelexemplar und die Spalte "Menge" ist nicht
  zugeordnet, wird die Menge 1, der alte Wert steht in der Notiz, und der
  Bericht gibt einen Hinweis statt der Meldung "Einzelexemplare haben immer die
  Menge 1".
- IMP-011 [SOLL · V · S9] Import als Vorschau statt direkt: Der Probelauf jedes Imports – Material,
  Produkte, Kunden, Personen – zeigt jede Zeile der Datei mit ihrem Ergebnis:
  neu, geändert (je Feld bisher → neu, formatiert wie im
  Änderungsprotokoll), unverändert oder Fehler, filterbar und durchsuchbar
  nach Zeile, ID und Name, 200 Zeilen je Seite; ebenso der Bericht des
  Imports danach und die Antwort der API. Werte, die der Nutzer nicht sehen
  darf (Einkaufspreise, Preise, Rabatte, Stundensätze), stehen als "nicht
  sichtbar". Ein Skript, das eine
  prüfbare SQL-Datei erzeugt, entfällt; die Vorschau prüft gegen dieselben
  Regeln wie der Import.
- IMP-012 [SOLL · A · S1] Der Lauf ist wiederholbar (IMP-004): Die
  Excel-Tabelle kann bis zur Umstellung weitergepflegt und erneut eingelesen
  werden.

Hinweis zur Umwandlung in SQL: Eine reine Umwandlung der Tabelle in
SQL-Befehle ist möglich, schreibt aber an den Prüfregeln der Anwendung
vorbei. Die Tabelle hat eine Zeile je Exemplar; die Datenbank trennt Modell
und Instanz und verweist auf Kategorien, Händler und andere Exemplare. Ein
SQL-Skript müsste diese Zuordnung selbst nachbauen und passt nach jeder
Änderung am Datenbankschema nicht mehr. Empfohlen ist deshalb der Weg über
die Importlogik (IMP-009); die SQL-Datei bleibt als Ausgabeformat möglich
(IMP-011).

Weitere Anforderungen

- IMP-013 [SOLL · V · S5] Der Kontaktexport von Lexware (CSV, Windows-1252)
  lässt sich unverändert als Kundenliste importieren, mit Lieferadresse,
  Steuernummer und Ansprechpartnern. Vorhandene Kunden werden über
  Kundennummer, USt-IdNr., E-Mail-Adresse oder Namen erkannt und ergänzt
  statt verdoppelt; leere Zellen überschreiben nichts. Der Probelauf zeigt je
  Zeile, ob der Kunde neu ist, mit wem er zusammengeführt wird und woran er
  erkannt wurde.


Ausbaustufe 8: Weitere Anforderungen

- IMP-014 [SOLL · V · S8] Netto oder brutto beim Import des Materials: Der Dialog
  fragt, ob die Kaufpreise der Datei netto oder brutto sind, und bei
  brutto den Steuersatz (die Steuersätze der Stammdaten, voreingestellt der
  Standard). Bruttopreise werden durch 1 + Satz geteilt und netto
  gespeichert; Rentalars führt Kaufpreise netto. Der Bericht nennt die
  Umrechnung. Ebenso der Befehl (--gross, --tax-rate) und die API (Optionen
  des Imports).
- IMP-015 [SOLL · V · S8] "#0802" ist die ID 0802: Ein "#" vor einer ID gilt überall, wo
  der Import eine ID liest – in der Spalte ID, bei "Einsatz/Verbindung",
  in der Preiszelle (IMP-016) – und ebenso, wo eine ID eingetippt wird.
- IMP-016 [SOLL · V · S8] Preis als "#0851": Steht in der Preiszelle eines Exemplars eine ID, wurde es mit
  diesem zusammen als Set gekauft (MAT-054): Es verweist auf 0851 und hat
  keinen eigenen Preis; 0851 trägt den Preis des Sets. Geprüft wird, dass
  die genannte ID in der Datei oder im Bestand steht, einen Preis hat und
  selbst auf keine weitere verweist; der Bericht nennt die Sets mit dem
  Exemplar mit dem Preis zuerst.

Ausbaustufe 9: Weitere Anforderungen

- IMP-017 [SOLL · V · S9] Export im Importformat: Zu jedem Import (Material,
  Produkte, Kunden, Personen) gibt es "Export im Importformat": CSV mit genau
  den Spalten und Überschriften des Imports, im Klartext – Namen und Nummern
  statt interner IDs, Kategorien und Lagerorte als Pfad, Datum TT.MM.JJJJ,
  Dezimalkomma, deutsche Auswahlnamen, eigene Felder (MAT-071) als Spalten.
  Wieder importiert ändert die Datei nichts. Preise, Einkaufspreise und
  Stundensätze nur mit dem jeweiligen Recht, sonst fehlt die Spalte; Formeln
  werden entschärft. Große Bestände werden in Teilen geschrieben (20.000
  Exemplare in wenigen Sekunden). API: GET /imports/{kind}/export.


### 5.13 Programmierschnittstelle (API)

- API-001 [MUSS · V · S1] Die Anwendung ist API-first aufgebaut: Alle
  fachlichen Funktionen stehen über eine dokumentierte HTTP-API bereit.
- API-002 [MUSS · V · S1] Oberfläche und API sind gleichwertig: Es gibt keine
  Funktion, die nur der Oberfläche vorbehalten ist. Die Oberfläche besteht aus
  vom Server erzeugten Seiten und muss nicht selbst über die API laufen; beide
  greifen auf dieselbe Fachlogik zu, damit sie sich nicht
  auseinanderentwickeln.
- API-003 [MUSS · A · S1] REST-Stil mit JSON; Ressourcen entsprechen den
  Fachobjekten (Kapitel 8).
- API-004 [MUSS · A · S1] Maschinenlesbare Beschreibung nach OpenAPI 3, die mit
  dem Code übereinstimmt und eine durchsuchbare Dokumentation erzeugt.
- API-005 [MUSS · A · S1] Versionierung im Pfad (/api/v1); inkompatible
  Änderungen nur in einer neuen Version.
- API-006 [MUSS · A · S1] Authentifizierung per Sitzung (Browser) und per Token
  (Integrationen); Rechteprüfung identisch zur Oberfläche.
- API-007 [MUSS · A · S1] Einheitliches Verhalten für Listen: Seitenweise
  Abruf, Sortierung, Filter, Auswahl einzubettender Beziehungen. Das
  gilt auch für die Liste der Altimporte (GET /legacy-imports mit count,
  results, page, page_size).
- API-008 [MUSS · A · S1] Einheitliches Fehlerformat mit maschinenlesbarem
  Code, Meldung und feldbezogenen Validierungsfehlern. Feindliche Einzelwerte
  (Text statt Zahl, Liste, NaN, "1e999", Zahlen über 2^63) geben an den
  Endpunkten, die sie prüfen müssen, 400 im selben Format statt 500
  (rentalars/api/inputs.py).
- API-009 [MUSS · A · S1] Eigener Endpunkt für Verfügbarkeitsabfragen (Produkt,
  Zeitraum, optional ohne Projekt X).
- API-010 [SOLL · A · S5] Schutz vor Doppelausführung schreibender Aufrufe und
  vor gegenseitigem Überschreiben (Versionsprüfung beim Speichern). Eine gespeicherte
  Antwort auf einen Aufruf mit Idempotency-Key gibt Rentalars erst nach der
  Anmeldung und der Prüfung der aktuellen Rechte zurück, genau wie bei einem
  neuen Aufruf. Sie ist an den Aufrufer (Nutzer bzw. Token) und an die
  Anfrage (Methode, Pfad, Inhalt) gebunden: Ein anderer Aufrufer bekommt sie
  nie; derselbe Aufrufer mit demselben Schlüssel, aber anderem Inhalt,
  bekommt 409. Die Versionsprüfung vergleicht und schreibt in einem Schritt
  (etwa mit gesperrter Zeile oder einer bedingten Änderung mit
  Versionsnummer), sodass von zwei gleichzeitigen Änderungen derselben
  Fassung nur eine gilt und die andere abgewiesen wird – überall, wo die
  Prüfung gilt, in der API wie in der Oberfläche.
- API-011 [SOLL · A · S5] Begrenzung der Aufrufrate je Token.
- API-012 [SOLL · A · S6] Webhooks für Ereignisse (Projektstatus geändert,
  Material ausgegeben/zurück, Zeiteintrag freigegeben).
- API-013 [KANN · A · S10] Kalender-Feeds (iCal) für Projekte und Einsätze. Die
  Einsätze einer Person gibt es ebenfalls (PER-023).
- API-014 [MUSS · A · S1] Für jede Fachfunktion gibt es einen automatisierten
  Test über die API. So fällt auf, wenn eine Funktion nur in der Oberfläche
  umgesetzt wurde. Die Prüfung läuft auch bei manage.py test tests.api (ein
  Spiegelmodul führt die API-Tests aus tests/unit und tests/acceptance mit
  aus; 715 Operationen werden erreicht).

Ausbaustufe 8: Weitere Anforderungen

- API-015 [SOLL · V · S8] Eigene Personaldaten und Einsätze über die API
  (Anforderung der mobilen App):
  Ohne Recht am Modul Personal liest und ändert jede Person über die API,
  was sie im Browser unter Mein Bereich (UIX-026) sehen und ändern darf. GET
  /people/me/profile nennt Telefon und E-Mail-Adresse und ob Kollegen sie
  sehen dürfen (PER-019), je mit dem Zeitpunkt der letzten Änderung, dazu
  die Funktionen – mit Sätzen nur, wenn die Person sie sehen darf (PER-010)
  – und die Qualifikationen mit Ablaufdatum. PATCH /people/me/profile nimmt
  diese vier Angaben an, jede freiwillig mit changed_at; es gilt die
  jüngere Änderung wie bei PRJ-113. GET, POST und DELETE
  /people/me/absences verwalten die eigenen Abwesenheiten ab 30 Tagen
  zurück (PER-012); POST nimmt einen Idempotency-Key an (API-010). GET
  /people/me/deployments?from=&to= liefert die eigenen Einsätze wie Mein
  Bereich → Meine Einsätze (UIX-043): je Personalposition das Projekt (id,
  number, name, status, parent), Funktion, Beginn, Ende, Ort, Treffpunkt,
  Phase, geplante Stunden, Notiz und Stand der Anfrage – auch vergangene,
  ohne stornierte Projekte, mit ETag.
  Die Zeiten der vier Angaben setzt das Speichern der
  Person, für jeden Weg; mit dem Update gilt je Angabe der letzte Eintrag
  im Änderungsprotokoll, sonst die Anlage der Person. changed_at gilt für
  alle gesendeten Angaben oder je Angabe; geprüft wird wie im Formular des
  Browsers. Die E-Mail-Adresse ist zugleich die Anmeldeadresse: Über die
  API ändert sie nur ein Token ohne Modulbeschränkung oder mit dem Modul
  E-Mail (das Token der App), sonst 403 – ein auf andere Module
  beschränktes Token könnte sonst über das Zurücksetzen des Passworts das
  Konto übernehmen.
- API-016 [SOLL · V · S8] Weitere Angaben für die Begleit-App (Anforderung
  der mobilen App; zwei davon SOLL, zwei KANN): GET /projects nennt auch bei Zugriff
  nur mit Einsatzsicht (AUT-025) den Namen der Projektleitung
  (manager_name) und den Ort (venue_label), GET /service-cases den Namen
  der verantwortlichen Person (manager_name) – Namen statt IDs, die die Crew
  sonst nicht auflösen kann. GET /me nennt die Version des Servers
  (server_version); daran erkennt die App, was der Server
  kann. GET /notifications?companion=1 liefert die Benachrichtigungen, die
  "In der App" erscheinen (UIX-039), mit der Zahl der ungelesenen unter
  ihnen; auch ältere ungelesene sind seitenweise erreichbar. Zeiteinträge
  nennen die Art der Bezahlung (pay_kind: hourly, daily oder flat) und bei
  einem Tagessatz, ob der Eintrag im Tagessatz liegt (in_day_rate), wie
  "Meine Zeiten" (ZEI-026). server_version steht
  auch in der Antwort der Anmeldung; mit einem Filter zählt unread nur die
  gefilterten Benachrichtigungen, unread_total alle; pay_kind und
  in_day_rate stehen nur da, wo die Person Sätze sehen darf.


### 5.14 Administration und Stammdaten (ADM)

- ADM-001 [MUSS · A · S1] Firmendaten (Name, Anschrift, Logo, Steuernummer,
  Bankverbindung) für Dokumente.
- ADM-002 [MUSS · A · S1] Pflege der Stammdaten: Kategorien mit Kürzel
  (PRD-027), Einheiten, Steuerarten, Funktionen, Händler, Hersteller,
  Lagerorte, Postfächer und Projektkürzel (Kapitel 5.15).
- ADM-003 [MUSS · A · S1] Nummernkreise für Projekte, Kunden, Material-IDs und
  Dokumente (Präfix, Mindeststellenzahl, Startwert). Voreinstellungen:
  Material-ID vierstellig fortlaufend, Projektnummer aus Jahr und laufender
  Nummer (2026-0042). Der Nummernkreis der Projekte
  hat das Präfix "{year}-": 2026-0042 (ADM-014).
  Ein Nummernkreis mit Neubeginn je Jahr fängt erst im neuen Jahr wieder bei
  der Startnummer an; ein von Hand eingestellter Zähler ("nächste Nummer") gilt im laufenden Jahr weiter.
- ADM-004 [SOLL · A · S1] Systemeinstellungen: Pufferzeiten, Standardzeiten,
  Passwortrichtlinie, E-Mail-Versand.
- ADM-005 [MUSS · A · S1] Systemweites Änderungsprotokoll, filterbar nach
  Objekt, Nutzer und Zeitraum.
- ADM-006 [SOLL · A · S1] Stammdaten, die in Verwendung sind, können nicht
  gelöscht, nur deaktiviert werden.
- ADM-007 [SOLL · A · S1] Stammdaten werden zunächst über die mitgelieferte
  Verwaltungsoberfläche des Frameworks gepflegt. Sie ist Administratoren
  vorbehalten und hält dieselben Fachregeln ein wie die übrige Anwendung.
  Alltagsvorgänge (Projekte, Packen, Zeiten, Korrespondenz) erhalten eigene
  Masken.

Weitere Anforderungen

- ADM-008 [SOLL · V · S5] Die Selbstprüfung (NFA-037) zeigt auch den Server:
  Prozessoren und Last, Arbeitsspeicher, Speicher von Rentalars,
  Rechnername, Netzwerk und Laufzeit, mit einer Warnung bei knappem
  Speicher oder hoher Last.
- ADM-009 [SOLL · V · S5] Die Einstellungen zeigen, ob Datenbank und
  Sicherungen verschlüsselt sind, und erklären, wie die Verschlüsselung auf
  dem Server eingeschaltet wird (NFA-067). Einen Knopf dafür gibt es nicht:
  Das Einschalten ändert den Datenbankserver und braucht Administratorrechte,
  die die Anwendung bewusst nicht hat [A].
- ADM-010 [SOLL · V · S5] "Sicherung jetzt erstellen" in den Einstellungen
  schreibt dieselbe Datei wie die nächtliche Sicherung zum Herunterladen;
  herunterladen kann sie nur, wer sie erstellt hat. Sind die Sicherungen
  verschlüsselt, bekommt die Datei einen eigenen Schlüssel, der nur dieser
  Person angezeigt wird [A].

Weitere Anforderungen

- ADM-011 [SOLL · V · S6] Neue Installationen bringen diese Stammdaten mit:
  die Einheiten Stück (Miete), Stück (Verkauf), Set (Miete), Set (Verkauf),
  Stunde, Tag, Kilometer, Pauschal, Angefangener Liter, Angefangener Meter und
  Angefangenes Kilogramm; die Staffel "Standardstaffel" mit 1 Tag = 1,0,
  2 Tage = 1,5, 3 Tage = 1,75, 4 Tage = 2,0, 5 Tage = 2,4, 6 Tage = 2,75 und
  7 Tage = 3,5, jeder weitere Tag + 0,3 (PRD-038); die Hauptkategorien Ton
  (T), Licht (L), Video/Medien (M), Rigging/Traverse (R), Kabel (K), Verkauf
  (V), Extern zugemietetes Material (E) und
  Veranstaltungstechnik-Dienstleistung (D). Eine bestehende Installation
  bekommt beim Aktualisieren nur, was fehlt; nichts Vorhandenes wird
  umbenannt, geändert oder gelöscht – eine vorhandene "Standardstaffel" behält
  ihre Faktoren. Die Hauptkategorie Fremdmaterial
  (C) für Kundenmaterial gehört dazu (PRD-043); eine bestehende Installation bekommt
  sie nur, wenn es weder das Kürzel C noch den Namen schon gibt. Auch die
  Hauptkategorie N "Nebenkosten" (PRD-045), acht Funktionen mit ihren
  Dienstleistungsprodukten (PER-037) und der Lagerort "Hauptlager" als
  Voreinstellung (MAT-052) gehören dazu.

Weitere Anforderungen

- ADM-012 [SOLL · V · S6] Frühere Projektnummern führen weiterhin ins Projekt; geregelt in ADM-014.
- ADM-013 [SOLL · V · S8] Automationen mit Auslösern lassen sich in der
  Oberfläche festlegen: Unter Einstellungen → Automationen stehen Regeln "Wenn
  …, dann …". Auslöser sind mindestens: Eine Mail ohne Projektkennung kommt in
  einem Postfach an, das solche Mails übernimmt (EML-041); ein Projekt
  erreicht einen Status; eine Antwort auf eine Einsatzanfrage kommt an; eine
  Wiedervorlage wird fällig (PRJ-105). Aktionen sind mindestens: per Mail mit
  einem Text mit Platzhaltern antworten – etwa mit einer Eingangsbestätigung
  –, eine Person benachrichtigen, einen offenen Punkt anlegen. Das weicht
  bewusst von EML-030 ab. Damit sich automatische Antworten nicht gegenseitig
  auslösen, antwortet Rentalars nie auf Mails, die als automatisch
  gekennzeichnet sind (Auto-Submitted, Precedence bulk, junk oder list,
  List-Id), nie an mailer-daemon, no-reply oder eigene Adressen und je
  Absender und Regel höchstens einmal am Tag; seine automatischen Mails tragen
  "Auto-Submitted: auto-replied". Jeder Lauf wird protokolliert und ist
  einsehbar. Für
  Servicefälle (PRJ-112) gibt es zusätzlich den Auslöser "Neue Kommunikation im Servicefall" und
  die Aktion "Status des Servicefalls setzen", und der Auslöser
  "Wiedervorlage fällig" lässt sich auf einen Status des Falls beschränken.
  Neue Installationen und bestehende bekommen drei
  Regeln, aktiv, bearbeitbar und abschaltbar: Wird die Wiedervorlage eines
  Falls in "wartet auf Schließen" fällig, wird er "erledigt"; kommt vorher
  neue Kommunikation, wird er "offen"; wird die Wiedervorlage eines Falls im
  "Rückstand" fällig, wird er "offen". Änderungen, die eine Automation selbst
  vornimmt, lösen den Auslöser "Neue Kommunikation" nicht aus; der Schutz vor
  Schleifen und das Protokoll jedes Laufs gelten auch hier.
  "Ein Defekt wird gemeldet" ist ein Auslöser,
  mit den Aktionen "Servicefall anlegen" (Titel, Beschreibung und Zuständige
  der Regel), "unter Projekte → Anfragen stellen" und "Person benachrichtigen"
  (MAT-057). Die Regel "Defektmeldung → Servicefall" ist mitgeliefert,
  aktiv, bearbeit- und abschaltbar. Die mitgelieferten Regeln sind wie eigene
  bearbeit- und löschbar und lassen sich wiederherstellen (ADM-019).

Ausbaustufe 7: Weitere Anforderungen

- ADM-014 [SOLL · V · S7] Projektnummern heißen ohne "P-" (2026-0042).
  Neue Installationen und die Ersteinrichtung haben das Präfix "{year}-"
  (2026-0001, Teilprojekte 2026-0001-1).
  Eine frühere Nummer, meist die mit "P-", steht im Kopf des Projekts
  ("früher P-2026-0042") und findet es weiter – in Suche und Projektliste, in
  alten Adressen und Lesezeichen (dauerhafte Umleitung), in Antworten auf Mails
  mit `[RL#P-2026-0042]`, beim Zuordnen einer Mail von Hand und in der API.
  Projektvorlagen nennen die Nummer ohne "P-". Ein eigenes Präfix mit
  Buchstaben (etwa "PRJ-{year}-") bleibt samt seinen Nummern; erstellte
  Dokumente bleiben unverändert.

Ausbaustufe 7: Weitere Anforderungen

- ADM-015 [SOLL · V · S7] Die Wahl "Antwort auf Einsatzanfragen" – über den
  Link, per Antwort-Mail oder beides (PER-032) – steht unter Einstellungen →
  Firmendaten und Grundeinstellungen.
- ADM-016 [SOLL · V · S8] Adresse und Zertifikat aus der Oberfläche: Die Adresse der Installation lässt sich in den Einstellungen
  ändern und das Zertifikat (NFA-035) für sie neu beantragen. Unter
  Einstellungen → "Serveradresse und Zertifikat" stehen die aktuelle
  Adresse und Art und Ablauf des Zertifikats – Let's Encrypt, selbst
  signiert, ein eigenes oder hinter einem Proxy, der TLS übernimmt. Ein
  Administrator bereitet dort eine Änderung vor: den neuen Rechnernamen
  und die Art des Zertifikats – Let's Encrypt mit E-Mail-Adresse, selbst
  signiert oder ein eigenes Zertifikat mit Schlüssel, die Rentalars beim
  Hochladen prüft (Schlüssel passt, Kette, Namen, Ablauf). Was sich aus der
  Anwendung prüfen lässt, prüft sie, etwa ob der neue Name auf diesen
  Server zeigt, und sagt, wenn sie es nicht sicher weiß. Die Änderung
  ändert den Webserver und braucht root-Rechte auf dem Server, die die
  Anwendung bewusst nicht hat (ADM-009). Entschieden ist "Nur Befehl
  anzeigen": Die Oberfläche speichert die vorbereitete Änderung, den
  Schlüssel geschützt wie andere Geheimnisse, und zeigt genau einen Befehl
  zum Kopieren, den ein Administrator per SSH auf dem Server ausführt
  (`sudo rentalars address apply …`), und was er tun wird; erst er ändert
  Adresse, Webserver und Zertifikat. Der Befehl prüft alles selbst noch
  einmal, sichert die bisherigen Dateien, schreibt die neuen Werte, prüft
  den Webserver, startet Rentalars neu und prüft, ob die neue Adresse
  antwortet; bei jedem Fehler stellt er alles wieder her, mit `--dry-run`
  zeigt er nur den Plan. Die Seite zeigt danach "angewendet am … von …"
  oder den Fehler; Mails mit Links, etwa Einladungen, nennen die neue
  Adresse. Rentalars selbst bekommt keine root-Rechte, und Zugangsdaten
  für root speichert es nie. Einen Knopf, der die Änderung selbst
  ausführt, gibt es nicht – wie beim Einschalten der Verschlüsselung
  (ADM-009). Rentalars antwortet nur auf die Namen der
  Konfiguration – den aus `url`, `localhost`, `127.0.0.1` und was der
  Betreiber unter `[rentalars]` als `allowed_hosts` einträgt (Namen und
  IP-Adressen, `.example.de` für alle Namen darunter; ein `*`, ein Schema,
  ein Port oder ein Pfad brechen den Start ab). Die IP-Adressen des Servers
  selbst brauchen keinen Eintrag (`allow_own_addresses`, voreingestellt
  ein): Rentalars liest sie vom System und antwortet auf jede davon, weil
  eine Adresse, die zu diesem Rechner gehört, nicht gegen die Anwendung
  einsetzbar ist; Links in Mails kommen immer aus `url`. Die Adressen
  werden alle 30 Sekunden neu gelesen, nur die gebräuchliche Schreibweise
  zählt (`[::1]`, nicht `[0::1]`), und wer Anfragen mit erfundenen Adressen
  schickt, erkennt an der Antwort, welche Adressen der Server hat (mit
  `allow_own_addresses = no` entfällt das). Jeder andere
  unbekannte Name führt zu einer Seite (statt "Bad Request"), die den
  geöffneten Namen (maskiert), die eingetragene Adresse und die Schritte
  für den Betreiber nennt; diese Anfrage ist kein Fehler im Fehlerprotokoll
  (NFA-018) und löst keine Meldung an die Betreiber aus, sondern steht als
  Warnung im Dienstprotokoll.

Ausbaustufe 8: Weitere Anforderungen

- ADM-017 [SOLL · V · S8] Schnittstelle für KI, anfangs ausgeschaltet: Unter Einstellungen → KI lässt sich ein
  Anbieter "OpenAI-kompatible Schnittstelle" einrichten – Adresse, Modell,
  API-Schlüssel (verschlüsselt gespeichert) und Zeitlimit –, für einen
  Server im eigenen Netz, etwa Ollama, LM Studio oder vLLM, wie für einen
  Dienst in der Cloud. Je Verwendung wird der Anbieter gewählt:
  "Zusammenfassung" (EML-040; voreingestellt die lokale KI), "Antwortentwurf
  für Mails" – beim Schreiben einer Mail schlägt "Entwurf vorschlagen"
  einen Entwurf aus dem Verlauf vor; anfangs aus, ohne Anbieter – und
  "Vorlagenvorschläge" (PRJ-091), nur als "später" genannt. Ein Anbieter in
  der Cloud zeigt eine deutliche Warnung, dass Mailinhalte den Betrieb
  verlassen (3.3). Für die Adresse gilt der Schutz vor internen Zielen
  (NFA-071): Ein Server im eigenen Netz braucht die Freigabe in der
  Konfigurationsdatei. Jeder Aufruf einer KI wird für Administratoren
  protokolliert – Verwendung, Anbieter, Modell, Dauer und Größe, nie der
  Inhalt. Zusammenfassungen
  und Entwürfe kommen gestreamt, Stück für Stück (EML-040); das Zeitlimit gilt für
  Stille – keine Ausgabe für die eingestellte Zahl von Sekunden –, nicht für
  die ganze Antwort, und die Aufgabe zeigt den Fortschritt (etwa "schreibt …
  120 Wörter"). Die Länge einer Antwort ist begrenzt. Ein Denkteil des
  Modells (<think>…</think>) wird aus jeder Antwort entfernt. Vor dem
  ersten Wort richtet sich die Wartezeit nach der geschätzten Lesezeit, und
  die ganze Aufgabe endet spätestens beim Dreifachen ihrer Schätzung. Einem
  angemeldeten Server (etwa Ollama) wird das Nachdenken zusätzlich
  abgewählt; lehnt ein Server diese Angaben ab, geht die Anfrage einmal
  ohne sie.


Ausbaustufe 8: Weitere Anforderungen

- ADM-018 [SOLL · V · S8] Stundensätze des Personals in der Ersteinrichtung
: Die Ersteinrichtung (NFA-033) fragt
  den Preis je Stunde für Kunden und die internen Kosten je Stunde,
  vorgeschlagen 45,00 € und 30,00 € netto. Beide gehen in die Funktionen
  der Startdaten (PER-037): der Preis in ihr Dienstleistungsprodukt
  (PRD-044), die Kosten als Richtwert der Funktion (PER-004) – nur wo noch
  keiner steht. Der Hinweis sagt, dass sich beides später unter Personal →
  Funktionen ändern lässt, je Funktion, mit Tagessätzen und einem höheren
  Satz ab einer Stundengrenze. Einstellungen → Projekte und Personal
  verlinkt die Funktionen (UIX-046).

Ausbaustufe 9: Weitere Anforderungen

- ADM-019 [SOLL · V · S9] Standard-Automationen wie eigene Regeln: Die vier Automationen, die Rentalars mitbringt (ADM-013),
  lassen sich bearbeiten, aus- und einschalten und löschen wie alle anderen,
  mit denselben Rechten, im Browser und über die API, im Änderungsprotokoll
  wie jede Änderung; jede Zeile der Liste hat "Bearbeiten",
  "Ausschalten"/"Einschalten" und "Löschen" in einer Reihe, gleich hoch, auch
  auf dem Telefon. Die Liste kennzeichnet sie mit "Standard" und mit
  "geändert", wenn sie von der Auslieferung abweichen. "Standard-Automationen
  wiederherstellen" (mit Rückfrage; API POST /automations/restore-defaults)
  legt die fehlenden an, wie sie kamen, und lässt vorhandene – geändert oder
  nicht – unberührt. Kein Update legt eine gelöschte wieder an oder
  überschreibt eine geänderte.


### 5.15 E-Mail-Zuordnung zu Projekten (EML)

Rentalars ordnet eingehende Mails anhand einer Kennung im Betreff einem Projekt
zu. Mails ohne Projektbezug rührt es nicht an.

Lesart der Vorgabe: Das Kürzel im Betreff bestimmt das Projekt; die Mail wird
mit ihren Anhängen in den Unterlagen dieses Projekts abgelegt. Eine feinere
Zuordnung innerhalb des Projekts ist als Ergänzung vorgesehen (EML-017).

Postfächer

- EML-001 [MUSS · V · S4] Rentalars enthält einen Mail-Client, der eingehende
  E-Mails aus einem bestehenden Postfach abruft und Projekten zuordnet. Ein
  Postfach bei einem beliebigen Anbieter genügt; auf dem Server wird kein
  Mailserver betrieben.
- EML-002 [MUSS · A · S4] Abruf über IMAP, Versand über SMTP, jeweils
  verschlüsselt. Zugangsdaten liegen verschlüsselt in der Datenbank und sind in
  der Oberfläche nicht auslesbar.
- EML-003 [SOLL · A · S9] Mehrere Postfächer (z. B. projekte@..., lager@...),
  je Postfach ein- und ausschaltbar. Erfüllt durch EML-041: Mehrere
  Postfächer werden abgerufen und sind je Postfach ein- und ausschaltbar.
  Gesendet wird auch aus weiteren Postfächern und Aliassen, nach Rolle (EML-052,
  EML-047).
- EML-004 [KANN · A · S10] Anmeldung am Postfach über OAuth 2 für Anbieter, die
  keine Passwortanmeldung zulassen (z. B. Microsoft 365, Google Workspace).
  Zunächst genügt die Anmeldung mit Benutzername und Passwort über IMAP/SMTP.
- EML-005 [MUSS · A · S4] Abruf automatisch im Hintergrund in einstellbarem
  Abstand (Voreinstellung: alle 2 Minuten) mit Bordmitteln des Servers
  (NFA-036); zusätzlich "jetzt abrufen" auf Knopfdruck. Der Abruf prüft
  zunächst nur die Kopfzeilen und verändert dabei nichts im Postfach, auch
  nicht den Gelesen-Status.
- EML-006 [MUSS · V · S4] Nur zugeordnete Mails werden angefasst: Sie werden
  übernommen, im Postfach als gelesen markiert und in einen einstellbaren
  Ordner verschoben. Alle anderen Mails bleiben unverändert im Posteingang.
  Wahlweise lassen sich zugeordnete Mails nach erfolgreicher Übernahme löschen
  statt verschieben; diese Option ist ausgeschaltet, bis sie ausdrücklich
  aktiviert wird. Je Postfach wird eingestellt, ob
  zugeordnete Mails verschoben, gelöscht oder unverändert gelassen werden
  (EML-041). Als weitere Wahl gibt es "nur als gelesen
  markieren" (ohne Verschieben); voreingestellt bleibt "als gelesen markieren
  und in einen Ordner verschieben". Die Wahl "nur als
  gelesen markieren" verschiebt die Antwort auf eine Einsatzanfrage in den Ordner für
  zugeordnete Mails (PER-043).
- EML-007 [MUSS · A · S4] Jede Mail wird nur einmal übernommen (Erkennung über
  ihre Message-ID), auch bei wiederholtem Abruf oder mehreren Postfächern.

Zuordnung über das Projektkürzel

- EML-008 [MUSS · V · S4] Eine Mail mit einem Projektkürzel im Betreff wird
  automatisch dem zugehörigen Projekt zugeordnet und in dessen Unterlagen
  abgelegt.
- EML-009 [MUSS · V · S4] Aufbau des Kürzels: eckige Klammern, Präfix, Raute,
  Projektnummer – z. B. `[RL#2026-0042]`. Das Präfix (Voreinstellung RL) ist
  systemweit einstellbar. Auch das Kürzel mit der
  früheren Nummer führt ins Projekt (ADM-012), ebenso das mit "P-"
  (`[RL#P-2026-0042]`, ADM-014).
- EML-010 [MUSS · A · S4] Das Kürzel wird an beliebiger Stelle im Betreff
  erkannt, unabhängig von Groß-/Kleinschreibung, Leerzeichen innerhalb der
  Klammern und vorangestellten Zusätzen wie "AW:", "Re:" oder "WG:".
- EML-011 [MUSS · A · S4] Jedes Projekt zeigt sein Kürzel zum Kopieren an. Aus
  Rentalars gesendete Mails tragen es im Betreff, sodass Antworten von selbst
  richtig ankommen; Projektdokumente können es im Kopf ausweisen.
- EML-012 [SOLL · A · S4] Antworten ohne Kürzel werden über die Kopfzeilen der
  Mail (Bezug auf eine bereits zugeordnete Mail) demselben Projekt zugeordnet
  und dann wie jede zugeordnete Mail behandelt.
- EML-013 [MUSS · V · S4] Mails ohne Kürzel und ohne Bezug übernimmt Rentalars
  nicht. Sie bleiben im Posteingang, wie sie sind, und werden weiter im
  gewohnten Mailprogramm bearbeitet. Je Postfach lässt sich
  einstellen, dass sie zusätzlich als Anfragen erscheinen (EML-042); auch dann
  bleiben sie im Posteingang, bis jemand sie übernimmt.
  Rentalars erkennt in jedem Postfach außerdem Antworten auf Einsatzanfragen
  an ihrem eigenen Code im Betreff (PER-032).
- EML-014 [SOLL · A · S4] Trägt eine Mail ein Kürzel, zu dem es kein Projekt
  gibt (Tippfehler, unbekannte Nummer), bleibt auch sie unangetastet.
  Rentalars zeigt sie in einer Hinweisliste mit Absender, Betreff, Datum und
  Kürzel, damit sie von Hand einem Projekt zugeordnet werden kann. Die
  Hinweisliste ist der Reiter "Anfragen" unter "Projekte"
  (EML-042).
- EML-015 [MUSS · A · S4] Eine Zuordnung kann nachträglich geändert werden; die
  Änderung wird protokolliert.
- EML-016 [KANN · A · S10] Enthält ein Betreff mehrere Kürzel, wird die Mail dem
  ersten zugeordnet; die weiteren werden als Hinweis angezeigt.
- EML-017 [KANN · A · S10] Das Kürzel kann eine Ergänzung tragen, die innerhalb
  des Projekts genauer zuordnet – z. B. ein Teilprojekt oder eine
  Unterlagenart: `[RL#2026-0042/B2]`.
- EML-018 [SOLL · A · S4] Mails zu abgeschlossenen oder stornierten Projekten
  werden zugeordnet und der Projektleitung gemeldet.
- EML-033 [KANN · A · S10] Nachträgliches Zuordnen ohne Kürzel: Eine nur lesende
  Sicht auf den Posteingang (Absender, Betreff, Datum) erlaubt es, eine Mail
  auszuwählen und einem Projekt zuzuordnen; erst dann wird sie übernommen. Ohne
  diese Funktion genügt es, die Mail mit dem Kürzel im Betreff an das Postfach
  weiterzuleiten.

Projektunterlagen

- EML-019 [MUSS · V · S4] Zugeordnete Mails erscheinen im Projekt als
  Korrespondenz in zeitlicher Folge mit Absender, Empfängern, Datum, Betreff,
  Text und Anhängen.
- EML-020 [MUSS · A · S4] Anhänge werden mit der Mail gespeichert und sind im
  Projekt abrufbar.
- EML-021 [SOLL · A · S4] Ein Anhang lässt sich in einem Schritt in die Dateien
  des Projekts übernehmen und dabei einer Unterlagenart zuordnen (z. B.
  Bühnenplan, Rider, Vertrag, Bestellung).
- EML-022 [SOLL · A · S4] Mails sind über die globale Suche auffindbar
  (Betreff, Absender, Text), begrenzt auf die Rechte des Nutzers.
- EML-023 [SOLL · A · S4] Benachrichtigung der Projektleitung bei neuer Mail
  zum Projekt (UIX-005).

Versand

- EML-024 [MUSS · V · S4] Aus dem Projekt heraus lassen sich Mails schreiben
  und beantworten. Die gesendete Mail wird im Projekt abgelegt.
- EML-025 [SOLL · A · S4] Projektdokumente (z. B. Packliste, Preisübersicht)
  lassen sich an ausgehende Mails anhängen (vgl. DOK-008).
- EML-026 [SOLL · V · S9] Signatur je Postfach. Eine gemeinsame Signatur für
  alle gibt es (EML-034). Jedes
  Postfach hat auf Wunsch eine eigene, mit denselben Platzhaltern und demselben
  Editor; leer gilt die gemeinsame. Eine Mail trägt die Signatur des
  Postfachs, aus dem sie geht, ein Alias die seines Postfachs. Ändern darf
  sie, wer die Einstellungen ändern darf. Textbausteine je Postfach siehe EML-054.

Sicherheit und Datenschutz

- EML-027 [MUSS · A · S4] Mailinhalte werden bereinigt angezeigt: Skripte
  werden nicht ausgeführt, externe Bilder und Inhalte erst auf Anforderung
  geladen.
- EML-028 [MUSS · A · S4] Anhänge unterliegen den Regeln für hochgeladene
  Dateien (NFA-007); die zulässige Größe je Mail ist einstellbar.
- EML-029 [MUSS · V · S4] Zugeordnete Mails sieht nur, wer Zugriff auf das
  Projekt und zusätzlich das Recht zum Lesen von Korrespondenz hat (AUT-019);
  Schreiben und Senden erfordern ein eigenes Recht. Die Anfragen (EML-042) und
  die Verwaltung der Postfächer liegen im Modul E-Mail (AUT-014).
- EML-030 [MUSS · A · S4] Das System versendet keine automatischen Antworten
  auf eingehende Mails. Abwesenheitsnotizen und Zustellfehler werden erkannt
  und gekennzeichnet. Mit einer Ausnahme: Eine Antwort auf
  eine Einsatzanfrage bestätigt Rentalars per Mail (PER-032) – nur an die
  gespeicherte Adresse der Person, ohne Kürzel und als automatisch erzeugt
  gekennzeichnet. Jede Mail, die Rentalars von selbst
  verschickt, endet mit dem Hinweis, dass Rentalars sie automatisch für die Firma
  versendet hat (EML-045); bei dieser Bestätigung ersetzt er den eigenen Satz
  dazu. Automatische Antworten auf andere Mails gibt es weiterhin nicht.
  Bewusst mit einer zweiten Ausnahme: Eine Automation, die
  jemand in den Einstellungen festlegt, kann auf Mails antworten, etwa mit
  einer Eingangsbestätigung, geschützt gegen Schleifen (ADM-013).
- EML-031 [SOLL · A · S4] Mails enthalten personenbezogene Daten: Die
  Aufbewahrungsfrist ist einstellbar (NFA-011), und die Anonymisierung eines
  Kunden (KND-010) bezieht dessen Mails ein.
Beim Anonymisieren eines Kunden oder einer Person werden Mails, Anhänge und Einträge des
  Mail-Protokolls nur gelöscht, wenn eine ihrer Adressen genau die Adresse des Betroffenen ist, nicht, wenn sie sie als Teil
  enthält.
- EML-032 [SOLL · A · S4] Fehler beim Abruf (falsche Zugangsdaten, Server nicht
  erreichbar) werden protokolliert, den Administratoren gemeldet und in der
  Selbstprüfung angezeigt (NFA-037), samt Zeitpunkt des letzten erfolgreichen
  Abrufs.

Weitere Anforderungen

- EML-034 [SOLL · V · S5] Eine gemeinsame Signatur für alle, als Text oder
  HTML, mit Platzhaltern für Vorname, Nachname, Position, E-Mail-Adresse,
  Telefon und Firma, gefüllt mit den Daten der Person, die schreibt.
  Ändern darf sie nur, wer die Einstellungen ändern darf. Beim Schreiben
  lässt sie sich abwählen.
- EML-035 [SOLL · V · S5] Für den Versand lassen sich Benutzer und Passwort
  des Abrufs übernehmen. Die Einstellungen des Postfachs stehen unter
  Einstellungen → E-Mail.
- EML-036 [SOLL · V · S5] Eine Mail wird kompakt gezeigt; Absender,
  Empfänger, Kopie und Datum lassen sich aufklappen. Die Korrespondenz eines
  Projekts lässt sich als Liste oder als Mailverlauf in zeitlicher Folge
  lesen, wie ein Chat: Eingegangenes links, Gesendetes rechts, Zitate und
  Signaturen eingeklappt.
- EML-037 [SOLL · V · S5] "Allen antworten"; die Felder CC und BCC;
  Vorschläge für Adressen ab drei Buchstaben aus Kunden, Ansprechpartnern und
  Personal, soweit die schreibende Person sie sehen darf.
- EML-038 [SOLL · V · S5] Als Absender erscheint "Vorname Nachname | Firma"
  mit der Adresse des Postfachs.
- EML-039 [SOLL · V · S5] Ein eigenes Mail-Protokoll hält jede ein- und
  ausgehende Mail fest, auch Einladungen und Benachrichtigungen: Zeitpunkt,
  Absender, Empfänger, Betreff, Projekt und Ergebnis, ohne den Text. Es ist
  mit Filtern und als CSV einsehbar und folgt der Frist der Mails, sonst
  einem Jahr [A].
- EML-040 [SOLL · V · S8] Die Korrespondenz eines Projekts lässt sich von
  einem KI-Modell zusammenfassen, das lokal auf dem eigenen Server läuft;
  keine Mail verlässt dafür das Haus. Es wird zusammen mit EML-044 umgesetzt
  (lokale KI, um Kosten zu sparen, einschaltbar). Die
  lokale KI installiert der Betreiber per Befehl über SSH (`sudo rentalars
  ai install`, entfernt mit `sudo rentalars ai remove`): einen
  Inferenzserver auf demselben Rechner, nur dort erreichbar, mit einem
  kleinen mehrsprachigen Modell, das Deutsch kann, zum Arbeitsspeicher
  passt und dessen Lizenz die Nutzung im Betrieb erlaubt. Unter
  Einstellungen → KI stehen Stand, Modell, Erreichbarkeit und die
  Geschwindigkeit einer Testanfrage und der Schalter "Zusammenfassungen
  mit lokaler KI", anfangs aus. "Zusammenfassen" an der Korrespondenz
  eines Projekts oder Servicefalls fasst die Mails, ein- und ausgehend,
  als Aufgabe im Hintergrund mit Fortschritt zusammen, lange Verläufe in
  Stufen. Die Zusammenfassung steht in der Sprache der Person (UIX-029),
  ist deutlich als von einer KI erzeugt gekennzeichnet, mit Modell und
  Datum, wird mit der neuesten erfassten Mail gespeichert und als
  "veraltet" markiert, wenn neue Mails kommen. Mailinhalte gehen dafür nur
  an den Anbieter, der für die Zusammenfassung eingestellt ist,
  voreingestellt die lokale KI (ADM-017). Lesen und erzeugen darf sie, wer
  die Korrespondenz lesen darf. Ohne KI gibt es immer eine Kurzübersicht:
  Beteiligte, Zahl der Mails, Datum der ersten und der letzten, genannte
  Termine und Beträge, offene Fragen der letzten Mails, Anhänge und wer
  zuletzt geantwortet hat. (Auf einem virtuellen Server in der Größe des Referenzsystems (NFA-038: 4 Kerne, 8 GB) brauchte der
  Geschwindigkeitstest 29 bzw. 10 Sekunden, und eine Zusammenfassung von
  knapp 2.000 Zeichen brach nach 600 Sekunden ohne ein Zeichen ab):
  - Der Denkmodus des Modells ist bei jeder Art von Server, die der Befehl
    einrichtet oder anmeldet, sicher aus; die Zahl der Threads ist die der
    echten Kerne, nicht aller logischen Prozessoren.
  - Der Geschwindigkeitstest nennt das Lesen der Eingabe und das Schreiben
    der Antwort getrennt, in Tokens je Sekunde. Vor einer Zusammenfassung
    schätzt die Seite ihre Dauer und
    warnt, wenn sie lange dauert; die längste Laufzeit der Aufgabe folgt aus
    der Schätzung. Antworten kommen gestreamt (ADM-017).
  - `rentalars ai status`, `ai install` und Einstellungen → KI prüfen, ob
    der Prozessor AVX2 und FMA kann, und warnen sonst – mit dem Hinweis,
    in einer virtuellen Maschine den Prozessortyp "host" einzustellen.
  - Das Modell wählt der Befehl nach Arbeitsspeicher und Kernen bzw.
    gemessener Geschwindigkeit. Ein kleineres Modell steht zur Wahl
    (`sudo rentalars ai install --model`) und wird unter einer gemessenen
    Geschwindigkeit empfohlen. Einstellungen → KI zeigt Modell,
    Geschwindigkeit und Empfehlung; gewechselt wird das Modell mit dem
    Befehl des Betreibers.
  - Qwen3 4B nur mit mindestens 6 GB, vier
    physischen Kernen und AVX2/FMA, sonst Qwen3 1.7B Q4_K_M (Umwandlung
    von ggml-org, Apache-2.0). Empfohlen wird das kleinere unter 6 Tokens
    je Sekunde beim Schreiben oder 30 beim Lesen oder ohne AVX2/FMA, mit
    dem Befehl zum Kopieren. llama-server startet mit `--reasoning off`,
    wo er es kennt; Rentalars sendet zusätzlich enable_thinking: false und
    "/no_think". Die Seite schätzt die Dauer einer Zusammenfassung ("dauert
    etwa N Minuten") und warnt ab 5 Minuten; jeder Aufruf hält die
    gemessenen Geschwindigkeiten aktuell.
  - `sudo rentalars ai refresh` übernimmt die Einstellungen der lokalen KI
    – Threads, Nachdenken aus, Speichergrenze – und startet sie nur bei
    einer Änderung neu. Es läuft nach jedem Update und, über einen
    Zeitgeber, etwa eine Minute nach jedem Start des Servers (so auch nach
    dem Umstellen des Prozessortyps einer
    virtuellen Maschine). Es lädt nie etwas herunter, baut nichts und
    wechselt nie das Modell; passt ein anderes Modell, nennt es nur den
    Befehl. llama-server kommt auf Ubuntu 26.04 aus dem Ubuntu-Paket und
    wird mit den Systemupdates aktualisiert; ein auf 24.04 gebauter wird
    nur auf Hinweis neu gebaut (`sudo rentalars ai install --rebuild`).

Weitere Anforderungen

- EML-041 [SOLL · V · S6] Rentalars ruft mehrere Postfächer ab (EML-003);
  jedes hat Name und Adresse und lässt sich ein- und ausschalten. Jedes
  Postfach hat eine oder beide Aufgaben: "Korrespondenz" – es wird abgerufen
  und zugeordnet; mehrere sind möglich, und genau eines der aktiven versendet
  die in Projekten geschriebenen Mails – und "Systemmails" für Einladungen,
  Passwort-Links und Benachrichtigungen, höchstens eines; ohne es gehen sie
  über die Konfiguration des Servers. Je Postfach ist einstellbar, ob Mails
  ohne Projektkennung als Anfragen übernommen werden (EML-042) und was mit
  zugeordneten Mails geschieht: als gelesen in einen Ordner verschieben,
  löschen oder unverändert lassen (EML-006). "Verbindung prüfen" meldet sich
  an, ohne etwas zu ändern oder zu senden. Stand und Fehler des Abrufs gelten
  je Postfach; ein gestörtes hält die anderen nicht auf. Abrufabstand, größte
  Mail und Aufbewahrung gelten für alle. Ein
  Postfach lässt sich auch löschen, wenn über es Mails kamen oder gingen (EML-046).
  Ein Postfach kann mehrere Adressen (Aliasse) mit eigener
  Behandlung haben (EML-047), und nach der Zuordnung ist auch "nur als
  gelesen markieren" wählbar (EML-006).
- EML-042 [SOLL · V · S6] Unter "Projekte" gibt es den Reiter "Anfragen" für
  alle, die das Modul E-Mail lesen dürfen: Mails mit einem Kürzel ohne Projekt
  (EML-014) und, aus Postfächern, die das übernehmen, Mails ohne Kürzel,
  gekennzeichnet "ohne Kennung", jeweils mit dem Postfach, in dem sie liegen.
  Mit der Projektnummer holt "Übernehmen" eine Mail aus ihrem Postfach ins
  Projekt. Der Menüpunkt "E-Mail" und der Kasten "Abruf" entfallen; Stand des
  Abrufs und "Jetzt abrufen" stehen in den Einstellungen unter E-Mail.
  Der Reiter steht unter /projects/inquiries/ (NFA-074)
  und listet auch Defektmeldungen, die eine Automation dorthin stellte
  (MAT-057).
- EML-043 [SOLL · V · S6] Beim Schreiben einer Mail stehen am Feld "An" zwei
  Knöpfe: "Crew hinzufügen" trägt alle ein, die in den Personalpositionen des
  Projekts eingeplant sind, ohne abgelehnte Anfragen – beim Gesamtprojekt auch
  die Crew der Teilprojekte, die die schreibende Person sehen darf –, mit
  Adressen wie in der Einsatzansicht nur, soweit sie sie sehen darf (PER-019).
  "Kunde hinzufügen" trägt den Ansprechpartner des Projekts ein, sonst die
  Adresse des Kunden. Keine Adresse kommt doppelt hinein; daneben steht, was
  hinzukam.
- EML-044 [SOLL · V · S8] Korrespondenzen lassen sich von einer KI
  zusammenfassen. Das bestätigt
  EML-040; beide werden gemeinsam und unter deren Bedingungen umgesetzt.
  Die Umsetzung folgt EML-040: mit einer
  einschaltbaren lokalen KI, ohne KI als Kurzübersicht; andere
  Verwendungen einer KI gehen über die Schnittstelle (ADM-017).

Ausbaustufe 7: Weitere Anforderungen

- EML-045 [SOLL · V · S7] Jede Mail, die Rentalars von selbst verschickt –
  Benachrichtigungen, Einladungen, Passwort-Links, Einsatzanfragen und die
  Bestätigung von Antworten (PER-032), Fehlermeldungen, die Testmail der
  Selbstprüfung –, endet mit dem Hinweis "Diese Nachricht wurde automatisch
  von Rentalars für <Firmenname> versendet: <Adresse>". Der Name kommt aus den
  Firmendaten (ADM-001), die Adresse ist die der Installation; ohne
  Firmennamen entfällt "für …". Im Text steht der Hinweis hinter dem üblichen
  Signaturtrenner "-- ", im HTML-Teil als letzter Absatz, in jeder Mail nur
  einmal. Mails, die jemand im Projekt schreibt (EML-024), bekommen ihn nicht;
  sie tragen die Signatur (EML-034).

Ausbaustufe 7: Weitere Anforderungen

- EML-046 [SOLL · V · S7] Ein Postfach lässt sich löschen, auch wenn über es
  Mails kamen oder gingen. Vorher fragt Rentalars nach und sagt, was folgt:
  Für seine Aufgaben gibt es dann kein Postfach mehr, die Mails bleiben. Mails
  und Mail-Protokoll (EML-039) nennen weiter seinen Namen. Ausschalten statt
  Löschen bleibt möglich (EML-041). Über die API löscht DELETE ebenso.

Ausbaustufe 8: Weitere Anforderungen

- EML-047 [SOLL · V · S8] Ein IMAP-Postfach mit mehreren Adressen (Aliassen),
  etwa support@ und projekt@, behandelt eingehende Mails je Adresse: Das
  Postfach hat eine Liste seiner Adressen. An welche Adresse eine Mail ging,
  liest Rentalars aus den Kopfzeilen Delivered-To, X-Original-To, To und Cc,
  in dieser Reihenfolge. Je Adresse ist wählbar, was mit Mails ohne
  Projektkennung geschieht: "nicht übernehmen", "als Anfrage" (EML-042) oder
  "gleich als Servicefall anlegen" (PRJ-090). Eine Adresse kann die Rolle
  "nur für Servicefälle" haben: Mails, die in einem Servicefall geschrieben
  werden, gehen mit dieser Adresse als Absender hinaus, sonst mit der
  Adresse des Postfachs, das die Korrespondenz versendet; Antworten mit der
  Kennung eines Servicefalls werden zugeordnet. Die eigene
  Adresse des Postfachs verhält sich nach der Einstellung "Mails
  ohne Projektkennung übernehmen" (EML-041), außer sie steht selbst in der
  Liste. Der Auslöser "Mail ohne Kennung" der Automationen (ADM-013) gilt
  für Anfragen. Die Adressen stehen unter Einstellungen → Postfächer
  und in der API am Postfach.
- EML-048 [SOLL · V · S8] Ohne Mailserver gilt eine Mail nicht als gesendet:
  Ist weder in der Konfigurationsdatei ein Server für den Versand
  eingetragen ([email] host) noch ein Postfach mit der Aufgabe Systemmails
  eingerichtet (EML-041), zeigt eine versandte Mail statt "gesendet" den
  Stand "nicht versendet – kein Mailserver eingerichtet" und zählt nicht als
  gesendet. Die Stelle, die sendet, zeigt die Warnung und verweist auf
  Einstellungen → Postfächer; die Selbstprüfung nennt den fehlenden
  Mailserver (EML-032, NFA-037). rentalars@localhost ist nur der
  voreingestellte Absender der Konfigurationsdatei, wenn dort nichts
  eingetragen ist, und kein Postfach, über das eine Mail ankäme.

Ausbaustufe 8: Weitere Anforderungen

- EML-049 [SOLL · V · S8] Mails ohne Projektkennung übernimmt Rentalars –
  als Anfrage (EML-042) oder gleich als Servicefall (EML-047) – nur ab
  einem Zeitpunkt: Je Postfach und je Adresse eines Postfachs, die solche
  Mails übernimmt (EML-041, EML-047), gibt es "ab" mit Datum und Uhrzeit.
  Beim Einschalten von "Mails ohne Projektkennung übernehmen" setzt
  Rentalars ihn auf diesen Moment; er steht dabei und lässt sich ändern.
  Wahlweise übernimmt Rentalars dazu nur ungelesene Mails ("nur
  ungelesene"). Mails von vor diesem Zeitpunkt bleiben unberührt im
  Posteingang; Mails mit Kennung oder Bezug (EML-008, EML-012) betrifft das
  nicht. Die API
  kennt beide Angaben.

Ausbaustufe 8: Weitere Anforderungen

- EML-050 [SOLL · V · S8] Dieselbe Korrespondenz in Projekt und Servicefall
: Der Reiter "Korrespondenz" sieht in einem
  Projekt und in einem Servicefall gleich aus und verhält sich gleich –
  dieselbe Vorlage, dieselben Kästen, dieselben Knöpfe. Der Kasten mit der
  Zusammenfassung (EML-040) heißt "Zusammenfassung", nicht "Überblick". Die
  Zusammenfassung der KI steht, wenn es eine gibt, oben darin; die
  Kurzübersicht ohne KI ("Kurzüberblick ohne KI") darunter ist beim Öffnen
  stets eingeklappt und lässt sich aufklappen. Projekt und Servicefall nutzen
  dieselbe Ansicht. Ein Test
  vergleicht beide Seiten.
  Auch die
  Zusammenfassung der KI ist beim Öffnen eingeklappt; offen steht sie nur
  gleich, nachdem sie geschrieben wurde. Notizen stehen in der
  Korrespondenz an ihrem Zeitpunkt (EML-051).


Ausbaustufe 8: Weitere Anforderungen

- EML-051 [SOLL · V · S8] Notizen in der Korrespondenz: Im Reiter Korrespondenz eines Projekts oder Servicefalls fügt
  "Notiz hinzufügen" ein Telefonat, ein Gespräch oder eine Absprache mit
  dem Zeitpunkt ein, zu dem es war – jetzt oder früher, nie in der
  Zukunft –, mit Text und auf Wunsch einem Betreff. Versendet wird nichts.
  Die Notiz steht in der Liste ("Notiz", notiert von …) und im Verlauf
  (in der Mitte, gestrichelt) an ihrem Zeitpunkt zwischen den Mails, in der
  Kurzübersicht (gezählt als Notiz, nicht als Mail) und in dem, was die KI
  zusammenfasst (EML-040). Ändern und entfernen kann sie, wer sie schrieb
  oder das Projekt bearbeiten darf; schreiben, wer Korrespondenz schreiben
  darf (EML-029), auch in einem abgeschlossenen Projekt. Eine Notiz wird
  nicht beantwortet, ist keine "neue Kommunikation" für die Automationen
  der Servicefälle (ADM-013) und wird mit den Mails nach der Aufbewahrungs-
  frist entfernt (EML-031). API: POST /projects/{id}/mails/notes, PATCH
  und DELETE /projects/{id}/mails/{id}; in der Liste direction "note".


Ausbaustufe 9: Weitere Anforderungen

- EML-052 [SOLL · V · S9] Absender wählbar nach Berechtigung: Beim Schreiben einer Mail steht "Absender" zur Wahl, wenn es
  mehr als eine Adresse gibt – die Postfächer der Korrespondenz, die
  senden können, und ihre Aliasse (EML-047). Das Postfach für den Versand
  steht allen offen, die Korrespondenz schreiben dürfen (EML-029); jede
  weitere Adresse nur den Rollen, die an ihr angehakt sind ("Als Absender
  wählbar für"). Beim Antworten ist die Adresse vorgewählt, an die die Mail
  kam. Gesendet wird über das Postfach der Adresse; Absender und Signatur
  (EML-026) folgen ihr. API: sender beim Senden, GET
  /projects/{id}/mails/senders; die Rollen am Postfach und am Alias.
- EML-053 [SOLL · V · S9] Anfragen von Hand anlegen: Unter Projekte → Anfragen legt "Anfrage anlegen" eine Anfrage
  an – wann, wer, Telefon, E-Mail-Adresse, Kunde, Betreff, Notiz; nötig
  sind eine Angabe, wie man jemanden erreicht, und eine, worum es geht. Sie
  steht mit "Notiert" in der Liste, lässt sich ändern und löschen, und
  "Übernehmen", "Als Projekt anlegen" oder "Als Servicefall anlegen" machen
  aus ihr eine Notiz der Korrespondenz (EML-051) – ohne Postfach, ohne
  Automationen für eingehende Mails. API POST /mail/unknown, GET, PATCH,
  DELETE /mail/unknown/{id}.
- EML-054 [KANN · A · S10] Textbausteine je Postfach.

Ausbaustufe 9: Weitere Anforderungen

- EML-055 [SOLL · V · S9] Nachrichten mit Schloss: Jede Nachricht der
  Korrespondenz (Mail, Notiz) ist mit Schloss oder offen. Mit Schloss liest
  sie nur, wer die Korrespondenz lesen darf und "Preise und Kalkulation sehen"
  hat; offen zusätzlich die im Projekt eingeplante Crew (nur lesen) und wer am
  Servicefall arbeitet (AUT-033). Ob neue Nachrichten – eingehend,
  geschrieben, Notiz, übernommene Anfrage, Servicefall aus einer Mail – mit
  Schloss beginnen, ist je für Projekte (Vorgabe: ja) und Servicefälle
  (Vorgabe: nein) einstellbar; wer ohne Preisrecht schreibt, schreibt offen.
  Setzen und entfernen darf das Schloss, wer Korrespondenz schreibt und Preise
  sieht; wird es entfernt, erfährt es die eingeplante Crew. Anhänge folgen
  ihrer Nachricht. Eine Nachricht, die jemand nicht lesen darf, gibt es für
  ihn nicht (404) – auch nicht ihr Betreff im Verlauf des Projekts oder in
  Meldungen von Automationen. Eine Antwort auf eine Nachricht mit Schloss
  beginnt mit Schloss, auch eine eingehende. KI-Zusammenfassung und
  Antwortentwurf nur für Leser aller Nachrichten. API: locked, PATCH …/lock.

Ausbaustufe 10: Weitere Anforderungen

- EML-056 [SOLL · V · S10] Automatische KI-Zusammenfassungen: Ein Nachtauftrag
  (manage.py ai_summaries, gestartet vom Minuten-Zeitgeber) fasst Projekte und
  Servicefälle zusammen, deren lesbare Korrespondenz (Mails, Notizen, wenn
  erlaubt Chat) sich seit der letzten Zusammenfassung geändert hat;
  entscheidend ist der Hash der Eingabe, nicht ein Zeitstempel, ein Lauf ohne
  Änderung ruft das Modell nicht auf. Der Weg ist derselbe wie beim Knopf
  "Zusammenfassen"; Zeitpunkt, Modell, Anbieter, Hash und das Kennzeichen
  "automatisch" werden gespeichert, frühere Fassungen bleiben (Standard 5),
  eine manuelle wird nie ungekennzeichnet überschrieben. Aus ist der Standard,
  das Einschalten setzt die ausdrückliche Zustimmung zu Anbieter und
  Datenklassen voraus und gilt für genau diesen Anbieter. Einstellbar:
  Zeitfenster (Standard 01:00 bis 05:00), Höchstzahl und Token-Budget je
  Nacht, Status der Projekte und Servicefälle, Mindestabstand und Mindestzahl
  an Mails, Ausschluss je Projekt und je Kunde, Probelauf. Der Auftrag läuft
  als eigener Dienst-Nutzer mit festem Mindestumfang (Mails und Notizen; Chat
  und Preise nur nach Freigabe); ein Fehler bricht ihn nie ab, die nächste
  Nacht versucht es erneut, Administratoren sehen Läufe und Fehler. Im Projekt
  steht die letzte Zusammenfassung mit "automatisch erstellt", Modell und
  Datum, einem Hinweis bei neueren Mails, "Erneut zusammenfassen" und den
  früheren Fassungen; sichtbar für wer alle Nachrichten lesen darf. Keine
  Benachrichtigungen. API: ai/auto-summaries mit Einstellungen, Läufen,
  Probelauf und Lauf, dazu der Ausschluss je Kunde und je Projekt.
- EML-057 [SOLL · V · S10] Absender einer Antwort per Mail bestätigen: Die Adresse im From lässt sich fälschen. Verglichen wird die Adresse der strukturierten From-Zeile
  (genau eine, mit Domain; nicht, was ein Parser aus dem Text macht: From: "anna@mail.example" <x@evil.example> ist
  x@evil.example). In Einstellungen → Postfächer trägt der Betreiber den Namen seines Mailservers in den Prüfergebnissen
  ein (der Teil vor dem ersten Semikolon in Authentication-Results). Dann zählt eine Antwort nur, wenn dieser Server
  dmarc=pass oder dkim=pass für die Domain des Absenders (oder eine übergeordnete Domain) schrieb; Prüfergebnisse anderer
  Absender zählen nie. Nicht bestätigte Antworten gelten nicht; die Person bekommt eine Mail mit dem Link zur Antwort im
  Browser. Ohne den Eintrag bleibt es beim Vergleich der Adresse und der Abweisung bei dmarc=fail (PER-046); das ist keine
  Bestätigung des Absenders. API: Feld crew_answer_trusted_server der Postfacheinstellungen.
Der Name des Mailservers ist ein Wort ohne Leerzeichen, Semikolon und Anführungszeichen;
  Rentalars speichert nichts anderes. Der Selbsttest meldet, wenn in den letzten Mails keine Kopfzeile dieses Servers stand.


### 5.16 Begleit-App für Android (APP)

Die responsive Webanwendung bleibt die Oberfläche für alles. Die App deckt nur
ab, was ohne Netz gebraucht wird: Packen im Lager oder im Lkw und die
Zeiterfassung am Einsatzort. Sie arbeitet ausschließlich über die API. Gebaut
ist sie als Rentalars-App 1.0 und wird getrennt von Rentalars geliefert; was
sie vom Server braucht, ist Teil von Rentalars und gehört zu Stufe 7 (PCK-026, PCK-027, AUT-021).

- APP-001 [SOLL · A · S7] Anmeldung mit Name, Passwort und – falls
  eingerichtet – dem Code der Authenticator-App. Die App erhält dafür ein
  eigenes Token, beschränkt auf Packlisten, Projekte und Zeiterfassung, mit
  wählbarer Gültigkeit (30, 90 oder 180 Tage). Das Passwort wird nicht
  gespeichert. Abmelden widerruft das Token und löscht alle Daten der App
  vom Telefon; im Browser lässt sich das Token jederzeit widerrufen (AUT-021).
  Das Token ist auf Packlisten,
  Projekte, Zeiterfassung und E-Mail beschränkt (packing, projects,
  time_tracking, email); damit gehen Chat, Korrespondenz, Preisübersicht und
  Anfragen auch in der App.
- APP-002 [SOLL · A · S7] Die App verlangt eine Displaysperre am Telefon und
  fragt sie beim Öffnen und nach fünf Minuten im Hintergrund ab. Alles, was
  sie speichert, ist verschlüsselt (AES-256-GCM, Schlüssel im Android
  Keystore). Keine Bildschirmfotos, keine Sicherung der Daten, nur https mit
  gültigem Zertifikat.
- APP-003 [SOLL · A · S7] Der Abgleich läuft von selbst, sobald ein Netz da
  ist, auch bei geschlossener App, und auf Wunsch sofort. Die App zeigt, wann
  zuletzt abgeglichen wurde und wie viele Änderungen warten.
- APP-004 [SOLL · A · S7] Zeiterfassung ohne Netz: Stoppuhr auf dem Telefon
  und nachgetragene Zeiten (ZEI-004) auf die Projekte und Funktionen, die die
  Person buchen kann (ZEI-006, ZEI-007). Es gelten die Regeln des Servers
  (keine Zeiten in der Zukunft, keine Überschneidungen). Jeder Eintrag geht
  genau einmal an den Server, auch wenn eine Antwort verloren geht; was der
  Server ablehnt, zeigt die App mit dem Grund.
- APP-005 [SOLL · A · S7] Die Zeitpunkte von Änderungen werden in der Zeit
  des Servers geführt, auch wenn die Uhr des Telefons falsch geht oder das
  Telefon ohne Netz neu startet (PCK-027, ZEI-022).
- APP-006 [SOLL · A · S7] Die App wird als signierte APK geliefert und lässt
  sich mit den Paketen von Ubuntu ohne weitere Downloads bauen und mit dem
  eigenen Schlüssel signieren.


### 5.17 Logistik und Fuhrpark (LOG)

Grundlage sind die Anforderungen zur Logistikplanung: Wie das Personal steht die Logistik (Fahrzeuge, KFZ-Anhänger) nicht in den Materialpositionen eines Projekts, sondern separat unter dem Personal; die Verwaltung des Fuhrparks bleibt im Bereich "Materialverwaltung". KFZ werden nach €/km abgerechnet, KFZ-Anhänger wahlweise über Tagesmiete oder ebenfalls €/km. Zieht ein KFZ auf einer Strecke einen KFZ-Anhänger, wird es mit einem höheren €/km-Satz abgerechnet als im Produkt angegeben; das wird möglichst automatisch erkannt. Stufe 9.
Die Fragen aus 12.2, Nummer 30, sind entschieden
(12.1); die Anforderungen nennen die Antworten.

Integration und Fuhrpark

- LOG-001 [MUSS · V · S9] In der Planung eines Projekts gibt es den Bereich
  "Logistik" unterhalb des Personals. Fahrzeuge (KFZ) und KFZ-Anhänger
  stehen nicht als Materialpositionen im Projekt, sondern werden dort
  separat disponiert – ähnlich wie das Personal (PRJ-019).
- LOG-002 [MUSS · V · S9] Der Fuhrpark wird in der Materialverwaltung
  geführt: Fahrzeuge und Anhänger sind einzeln identifizierbare Ressourcen
  mit Bezeichnung, Kennzeichen, Status (wie bei Exemplaren, MAT-021) und
  zugehörigem Produkt, das die Abrechnungssätze trägt (LOG-005). Ein
  eigener Reiter "Fuhrpark" der Materialverwaltung listet sie.
  Entschieden ("Als Exemplare"): Ein Fahrzeug ist ein
  Exemplar (MAT-011) eines Materialmodells, dessen Produkt die Produktart
  "Fahrzeug" hat – KFZ oder Anhänger; so hat es Status, Prüfungen,
  Dateien, Defektmeldungen, Etiketten und Verlauf. Kennzeichen (eindeutig),
  Sitzplätze, Führerscheinklasse, Anhängelast und zulässiges Gesamtgewicht
  stehen als Fahrzeugdaten auf der Seite des Exemplars. Die Hauptkategorie
  FZ "Fuhrpark" ist dafür voreingestellt. Der Reiter "Fuhrpark" listet
  Kennzeichen, Art, Modell, Produkt, Sitzplätze, Führerscheinklasse,
  Status, nächste Prüfung und laufende oder nächste Buchung. Fahrzeuge
  zählen nicht zur Verfügbarkeit des Materials (VFG) und werden nicht
  gepackt.
- LOG-003 [MUSS · V · S9] Für jedes KFZ stehen in den Stammdaten die
  Sitzplätze als Mindest- und Höchstwert ("Sitzplätze min." und
  "Sitzplätze max."), für Fahrzeuge mit herausnehmbaren oder variabel
  montierbaren Sitzen. Beide sind Pflicht und positive ganze Zahlen; der
  Mindestwert ist höchstens der Höchstwert; bei fester Sitzzahl sind beide
  gleich.
- LOG-004 [MUSS · V · S9] Die Verfügbarkeit der Fahrzeuge und Anhänger gilt
  über alle Projekte: Überschneidende Buchungen werden erkannt und
  angezeigt – in der Logistik des Projekts, wie eine Überbuchung beim
  Material (PRJ-013) oder eine Doppelbuchung beim Personal (PRJ-022), und in
  der Auslastung des Fuhrparks (LOG-018).

Abrechnung

- LOG-005 [MUSS · V · S9] KFZ werden nach gefahrenen Kilometern abgerechnet
  (€/km); Anhänger wahlweise nach Tagesmiete (€/Tag) oder nach Kilometern
  (€/km). Die regulären Sätze stehen im Produkt und gehen in die
  Kalkulation des Projekts; Preise und Kilometer lassen sich im Projekt bei
  Bedarf von Hand anpassen (wie der Einzelpreis einer Position, PRJ-015).
  Entschieden: Die Tage einer Tagesmiete zählen wie die
  Miettage des Materials – an der Buchung eingetragen, sonst die ihres
  eigenen Zeitraums, sonst die des Projekts – mit dem Faktor der Staffel
  (PRD-033); ohne Staffel zählt jeder Tag voll. In der Buchung
  umschaltbar in der Planung (in der Planungsposition): nur die Tage, an denen der Anhänger fährt.
  Die Sätze werden beim Buchen aus dem Produkt übernommen und gehören dann
  der Buchung; der Rabatt einer Buchung ist höchstens der Höchstrabatt des
  Produkts (PRD-041).
- LOG-006 [MUSS · V · S9] Anhängerbetrieb: Zieht ein KFZ auf einer Fahrt
  einen Anhänger, steigt sein Kilometerpreis um den Anhängerzuschlag, der
  am Fahrzeug steht (€/km). Rentalars erkennt das selbst an der Zuordnung
  des Anhängers zum Zugfahrzeug auf der Fahrt (LOG-007); der Zuschlag gilt
  nur für die Fahrten, auf denen wirklich ein Anhänger zugeordnet ist. Der
  Anhänger selbst wird zusätzlich nach seiner Abrechnungsart berechnet.
  Entschieden: Der Zuschlag steht am Zugfahrzeug, gleich welcher Anhänger
  dranhängt; ein Gespann hat höchstens einen Anhänger, ein Anhänger fährt
  auf einer Fahrt hinter höchstens einem Fahrzeug.

Fahrten und Kilometer

- LOG-007 [MUSS · V · S9] Die Logistik baut auf den Fahrten des Projekts
  auf (PRJ-097, PRJ-111): Je Fahrt lassen sich ein Fahrzeug, optional ein
  Anhänger und die geplanten bzw. gefahrenen Kilometer angeben, zunächst
  von Hand; eine Routenberechnung ist nicht nötig (LOG-017). Ein Fahrzeug
  kann im selben Projekt mehrere Fahrten mit unterschiedlichen Anhängern
  haben. Entschieden ("Wahlweise je Fahrt"): Je Fahrt
  wird gewählt, was berechnet wird – die gefahrenen Kilometer (solange sie
  fehlen, die geplanten, als Schätzung gekennzeichnet), die geplanten oder
  eine Pauschale für die Fahrt (Fahrzeug, Zuschlag und ein Anhänger nach
  Kilometern zusammen). Eine Fahrt, die es nicht mehr gibt (Phase
  entfernt), behält ihre Fahrzeuge mit einem Hinweis, sie einer anderen
  Fahrt zuzuordnen.

Verbindung zur Personalplanung

- LOG-008 [SOLL · V · S9] Personalpositionen lassen sich optional einem
  eingeplanten KFZ zuordnen – wer mit welchem Fahrzeug fährt –, bei
  mehreren Personen mit dem vorgesehenen Fahrer. Die Zuordnung steht im
  Überblick bzw. der Einsatzübersicht (PRJ-081) der Personen. Sind mehr
  Personen zugeordnet, als das Fahrzeug höchstens Sitzplätze hat
  (LOG-003), weist Rentalars darauf hin [A]. Entschieden: Die Fahrzeit
  des Fahrers ist Arbeitszeit seiner Personalposition; die Logistik
  rechnet nur das Fahrzeug ab. Die Zuordnung steht auch in der
  Crew-Disposition (DOK-004), unter "Meine Einsätze" und in der API.

Kalkulation

- LOG-009 [MUSS · V · S9] Alle Kosten der Logistik gehen in die
  Kalkulation des Projekts (PRJ-024, PRJ-025). Fahrzeuge, Anhänger und die
  Anhängerzuschläge stehen nachvollziehbar je Fahrt mit Kilometern bzw.
  Tagen und Satz. In der Preisübersicht (PRJ-033) ist die Logistik ein
  eigener Bereich nach Material und Personal; Rabatte und Pauschalpreise
  gelten wie für das Personal [A]. Die Logistik zählt wie das Personal zur
  Grundlage eines Aufpreises "auf das ganze Projekt" (PRD-031), steht in
  der Projektliste als "Logistikumsatz" und "Logistikkosten" (PRJ-085) und
  in den Auswertungen (PRJ-115).
- LOG-010 [SOLL · A · S9] Interne Kosten der eigenen Fahrzeuge (je
  Kilometer, bei Anhängern je Tag oder Kilometer) stehen am Fahrzeug bzw.
  Produkt und gehen in den "Gewinn aus dem Projekt" (PRJ-025, PRJ-087) und
  die Profitabilität (PRJ-115) ein; sichtbar nur mit dem Recht für
  Einkaufspreise (AUT-019). Entschieden ("Zumietung wie eigene"): Ein
  zugemietetes Fahrzeug wird wie ein eigenes gebucht, ohne Exemplar, mit
  dem Lieferanten; was der Lieferant für die Buchung berechnet, sind seine
  Kosten.
- LOG-011 [SOLL · A · S9] Angebot, Auftragsbestätigung und Rechnung
  (DOK-010, DOK-003, DOK-006) zeigen die Logistik als eigenen Abschnitt mit
  Kilometern bzw. Tagen und Satz, ebenso der Export an die Buchhaltung
  (DOK-011, DOK-012). Entschieden: Die Packliste nennt das Fahrzeug nur,
  in das sie verladen wird ("Verladen in"), auf der Seite und im PDF.

Weitere abgeleitete Anforderungen

- LOG-012 [SOLL · A · S9] Fahrerlaubnis: Am Fahrzeug steht die nötige
  Führerscheinklasse (B, BE, C1, C1E …), ein Gespann braucht die des
  Gespanns. Hat der vorgesehene Fahrer (LOG-008) die Klasse nicht als
  Qualifikation (PER-014), weist Rentalars darauf hin. Entschieden: nur ein
  Hinweis, nichts wird verhindert. Eine Qualifikationsart nennt die
  Klassen, die sie umfasst ("Führerscheinklassen", z. B. "B, BE"); die
  Klasse des Gespanns steht am Anhänger. Ohne solche Qualifikationsarten
  wird nicht geprüft.
Die Gültigkeit des Führerscheins wird gegen das Ende der Buchung geprüft, nicht gegen
  den Tag der Planung.
- LOG-013 [SOLL · A · S9] Anhängelast: Am KFZ steht, ob und bis zu welcher
  Last es ziehen darf, am Anhänger sein zulässiges Gesamtgewicht. Ein
  Anhänger an einem Fahrzeug, das ihn nicht ziehen darf, ergibt einen
  Hinweis.
- LOG-014 [SOLL · A · S9] Fristen der Fahrzeuge – Hauptuntersuchung,
  Prüfung nach DGUV/UVV, Inspektion – laufen über die Prüfarten der
  Materialverwaltung (MAT-030 bis MAT-032) mit Fälligkeiten und Hinweisen.
- LOG-015 [SOLL · A · S9] Fuhrpark und Logistik je Projekt gehen vollständig
  über die API (API-002): Fahrzeuge und Anhänger, ihre Buchungen und
  Verfügbarkeit, die Zuordnung zu Fahrten und Personal, Kilometer und
  Sätze; jede Operation hat einen Test (API-014).
- LOG-016 [SOLL · A · S9] Fahrzeuge, die als Material geführt sind, lassen
  sich in den Fuhrpark übernehmen.
  "In den Fuhrpark übernehmen" auf der Seite eines
  Materialmodells legt ein Fahrzeugprodukt an und ordnet ihm das Modell
  zu; das bisherige Produkt und seine Positionen bleiben, und offene
  Projekte, die es noch als Material planen, werden genannt.
- LOG-017 [KANN · A · S9] Kilometer per Routenberechnung vorschlagen – über
  einen Dienst, der in Deutschland oder beim Betreiber selbst läuft
  (NFA-050) –, stets änderbar. Entschieden (der Routendienst ist optional installier- und aktivierbar, auch nachträglich; ohne ihn Kilometer von Hand): `rentalars route install`
  richtet Routino mit der Karte Deutschlands oder eines Bundeslands von
  OpenStreetMap auf dem Server ein, `route register` nennt einen eigenen
  OSRM-kompatiblen Dienst; die Einstellungen zeigen den Stand. Im Dialog
  einer Fahrt schlägt "Geplante km aus der Route vorschlagen" die
  Kilometer über alle Halte vor; ohne Dienst gibt es den Knopf nicht.
- LOG-018 [SOLL · A · S9] Auslastung des Fuhrparks: ein Zeitstrahl der
  Fahrzeuge und Anhänger über die Projekte, wie die Materialauslastung
  (VFG-019, VFG-029), mit überschneidenden Buchungen in Rot.
- LOG-019 [SOLL · A · S9] Die Logistik folgt dem Projekt (seit Version
  0.27): Buchungen mit dem Zeitraum des Projekts ziehen mit, wenn er sich
  ändert; Buchungen einer Phase ziehen mit der Phase und ihrem Personal
  mit (PRJ-080); das Verschieben eines ganzen Projekts im Zeitstrahl nimmt
  sie mit (VFG-026). Duplizieren übernimmt auf Wunsch die Logistik
  ("mit der Logistik") samt Fahrteinsätzen, ohne gefahrene Kilometer
  (PRJ-029); eine Projektvorlage merkt sich die Buchungen als offene
  Buchungen ihres Produkts (PRJ-076). Beim Gliedern in Teilprojekte bleibt
  die Logistik beim Gesamtprojekt (PRJ-050).

Ausbaustufe 9: Weitere Anforderungen

- LOG-020 [SOLL · V · S9] Fuhrpark nur für Fahrzeug-Kategorien: "In den Fuhrpark übernehmen"
  (LOG-016) erscheint auf der Seite eines Materialmodells nur, wenn seine
  Kategorie oder eine übergeordnete die Produktart "Fahrzeug" vorgibt (wie FZ
  "Fuhrpark"); Dialog und API lehnen andere Modelle mit einer Meldung ab.


### 5.18 Anbindung an das Rentalars Gateway (GWL)

Das Rentalars Gateway ist ein eigenes Programm (eigenes Archiv, eigene Anforderungen GWS, GWA und GWY) in der
DMZ. Es nimmt die Anfragen der Apps aus dem Internet an und hält sie bereit; der Server holt sie ab. Der Server
baut nie eine Verbindung vom Gateway aus auf, in der Firewall des internen Netzes ist keine eingehende Freigabe
nötig. Was die Apps schicken, ist zwischen App und Server Ende-zu-Ende verschlüsselt (Protokoll RGW1). Dieser
Abschnitt beschreibt die Seite des Servers. Die Apps sind nicht Teil dieses Archivs. Der direkte Weg der Apps zum
Server bleibt unverändert; wer kein Gateway verbindet, merkt nichts.

Ausbaustufe 10: Anbindung des Rentalars Gateway

- GWL-001 [SOLL · V · S10] Verbinden: `sudo rentalars gateway connect 'RGWL1:…'` legt die beiden Schlüsselpaare
  dieser Installation an (Signatur der Aufrufe, Entschlüsselung der Anfragen), meldet den Server beim Gateway an und
  schaltet den Dienst ein; `disconnect` schaltet ihn ab und lässt Schlüssel und Geräte stehen. Hat das Gateway ein
  selbstgemachtes Zertifikat, vertraut die Installation genau diesem (Fingerabdruck im Verbindungstext); `status`
  nennt Adresse, Fingerabdruck, den letzten Abruf und die Zahl der Geräte. Ohne `connect` läuft kein Dienst, und
  nichts an der Installation ändert sich.
- GWL-002 [SOLL · V · S10] Verbindungsdienst `rentalars-gateway-link`: Er fragt das Gateway in langen Abfragen
  (25 Sekunden) nach neuen Anfragen, führt sie gegen die Anwendung auf demselben Rechner aus (Socket von gunicorn)
  und schickt die versiegelte Antwort zurück. Er schreibt nichts auf die Platte, läuft mit eingeschränkten Rechten,
  startet erst nach `connect` (sonst übersprungen, nicht fehlgeschlagen) und mit dem Dienst der Anwendung; `rentalars
  status` zeigt ihn. Optional: Abschnitt `[gateway]` der Konfiguration (`local`, `workers`, `time_window`,
  `max_response_mib`, `call_timeout`).
- GWL-003 [SOLL · V · S10] Das Gateway wird nicht vertraut: Eine Anfrage wird in dieser Reihenfolge geprüft, und
  ein Schritt, der scheitert, beendet sie, ohne dass etwas ausgeführt wird: Gerät bekannt, Signatur des Geräts über
  die versiegelten Bytes, Entschlüsselung, Gerät nicht gesperrt und Konto aktiv (sonst versiegelt "device_revoked"),
  Uhr des Geräts im Fenster (sonst versiegelt "time_skew" mit der Zeit des Servers), Anfrage-Kennung noch nicht
  gesehen (eine wiederholte wird nicht ein zweites Mal ausgeführt), Pfad und Methode erlaubt. Erlaubt ist nur
  `/api/v1/` mit GET, POST, PUT, PATCH und DELETE; Weboberfläche, Verwaltung und statische Dateien gehen nicht
  durch (versiegelt "path_forbidden").
- GWL-004 [SOLL · V · S10] Protokoll RGW1 (ECDH P-256, HKDF-SHA256, AES-256-GCM, ECDSA P-256) ist als Kopie der
  Festlegung des Gateways im Paket und wird mit dessen Testvektoren (`gateway_testvektoren.json`) geprüft: Die
  versiegelte Anfrage der Vektoren wird nachgebildet und geöffnet, die Antwort der Vektoren lässt sich öffnen.
  Antworten tragen die Zeit des Servers und, solange gesetzt, die Ankündigung eines Umzugs (GWL-009).
- GWL-005 [SOLL · V · S10] Koppeln: `sudo rentalars gateway pair BENUTZER --name "…"` erzeugt einen einmaligen
  Kopplungscode (zehn Minuten gültig, Text `RGW1:…` und QR-Code), dessen Geheimnis verschlüsselt gespeichert wird;
  die Zahl offener Angebote ist begrenzt, für ein deaktiviertes Konto gibt es keines. Die Kennung des Geräts
  leitet sich aus seinem Schlüssel ab. Ein Gerät gehört zu genau einem Konto: Über das Gerät kann man sich nur mit
  diesem Konto anmelden (Name oder E-Mail), eine Anmeldung mit einem anderen Konto wird abgelehnt und eine Sitzung
  dazu beendet.
- GWL-006 [SOLL · V · S10] Geräte verwalten: `devices` (mit `--all` auch gesperrte), `revoke KENNUNG` (die ersten
  Zeichen genügen; das Gateway erfährt es sofort); das Gerät eines deaktivierten Kontos ist sofort gesperrt.
  `rekey --yes` erneuert den Schlüssel der Installation: Alle Kopplungen enden, alle über Geräte angelegten Tokens
  werden widerrufen.
- GWL-007 [SOLL · V · S10] Token gehört zum Gerät: Ein API-Token, das über ein Gerät angelegt wurde, gilt nur über
  dieses Gerät (Bindung beim Anlegen durch den Dienst, Nachweis im Kopf `X-Rentalars-Device` mit einem Schlüssel
  aus `secret_key`, den nur diese Installation machen kann). Tokens des direkten Wegs sind unberührt; ist das Gerät
  gelöscht, gilt das Token nirgends mehr.
- GWL-008 [SOLL · V · S10] Anschrift je Gerät: Alle Anfragen kommen aus demselben lokalen Prozess. Damit die
  Sperre nach falschen Anmeldungen und die Grenzen je Anschrift nicht ein Gerät für alle sperren, trägt jede
  Anfrage eine aus der Gerätekennung abgeleitete Anschrift (`fd00::/8`). Kopfzeilen der App können sich nicht als
  die des Dienstes ausgeben.
- GWL-009 [SOLL · V · S10] Betrieb: Dateien aus dem Medienordner werden mit Typ, den Köpfen der Anwendung und
  Bereichsabfrage (Range) ausgeliefert, nichts außerhalb des Ordners, nichts über dem Limit; eine Antwort über der
  Grenze (12 MiB), eine Anwendung, die nicht antwortet, und ein Zeitlimit werden als versiegelter Fehler
  beantwortet. Umzug des Gateways: `announce-move --url … --fingerprint … [--next …]` hängt die neue Adresse an
  jede Antwort, bis `announce-clear` sie zurücknimmt.
- GWL-010 [SOLL · V · S10] Daten und Sicherung: Die privaten Schlüssel liegen verschlüsselt in der Datenbank (mit
  einem Schlüssel aus `secret_key`) und damit in jeder Sicherung; eine Wiederherstellung mit der Konfiguration der
  Sicherung bringt sie zurück. Im Datenexport fehlen die Schlüssel und das Geheimnis eines offenen Angebots sowie die
  gesehenen Anfrage-Kennungen; nach dem Laden wird das Gateway neu verbunden und werden die Geräte neu gekoppelt.
  Die Migration legt fünf Tabellen an. Anleitung auf Deutsch und Englisch
  (`docs/betrieb/gateway.md`, `docs/en/operations/gateway.md`).
- GWL-011 [KANN · V · S10] Geräte in der Weboberfläche: Einstellungen → Gateway zeigt den Zustand der Verbindung,
  macht für ein aktives Konto einen Kopplungscode (QR-Code und Text, gültig 1, 5 oder 10 Minuten und einmal; die Seite
  speichert ihn nicht und wird nicht zwischengespeichert), listet die Geräte mit Konto, Name, Kopplung und letzter Nutzung
  und sperrt eines; gesperrte stehen eingeklappt darunter. Koppeln und Sperren verlangen das Recht zu löschen in den
  Einstellungen (Lesen genügt zum Ansehen) und stehen im Änderungsprotokoll (ohne den Code). Ist das Gateway beim Sperren
  nicht erreichbar, ist das Gerät hier trotzdem gesperrt, und die Seite sagt es. Verbinden, Trennen und Schlüsselwechsel
  bleiben Befehle auf dem Server. Nicht gebaut: das Koppeln in der Konto-Verwaltung und über die API.
- GWL-014 [KANN · V · S10] Selbsttest: Die Gruppe "Gateway" steht in der Systemprüfung der Einstellungen und
  in `rentalars selfcheck`: die Adresse, ob das Gateway antwortet (letzte Antwort höchstens 90 Sekunden alt, sonst Fehler;
  noch keine Antwort ist eine Warnung), der letzte Fehler, die Zahl der gekoppelten und gesperrten Apps und ein angekündigter
  Umzug. Ohne Gateway steht dort eine Zeile "keine – die Apps erreichen den Server direkt". Die Prüfung liest nur die
  Datenbank und ruft das Gateway nicht auf; der Ablauf des Zertifikats des Gateways wird nicht geprüft.

Vorgemerkt, je KANN – was die Anbindung noch nicht kann:

- GWL-012 [KANN · A · S11] Nur über das Gateway (GWS-043): Ein Konto oder die ganze Installation verlangt für die
  API den Weg über das Gateway ("require_for_api"); der direkte Weg wird dann abgelehnt.
- GWL-013 [KANN · A · S11] Sicherheitsereignisse: Kopplung, Sperre, abgelehnte Anmeldung eines fremden Kontos über ein
  Gerät, falsche Signatur und Schlüsselerneuerung erscheinen als eigene Arten im Sicherheitsprotokoll (AUT-021) und
  lösen die vorhandenen Benachrichtigungen aus.

## 6. Nicht-funktionale Anforderungen (NFA)

Datenbank

- NFA-001 [MUSS · V · S1] Datenhaltung in MariaDB (eine aktuell unterstützte
  Langzeitversion).
- NFA-002 [MUSS · A · S1] Zeichensatz utf8mb4, transaktionssichere Tabellen,
  Fremdschlüssel zur Sicherung der Beziehungen.
- NFA-003 [MUSS · A · S1] Geldbeträge als Festkommazahl, nie als
  Gleitkommazahl. Zeitpunkte in UTC gespeichert, in der Oberfläche in Ortszeit
  angezeigt.
- NFA-004 [MUSS · A · S1] Schemaänderungen ausschließlich über versionierte,
  wiederholbare Migrationen.

Sicherheit

- NFA-005 [MUSS · A · S1] Ausschließlich verschlüsselte Übertragung (HTTPS).
- NFA-006 [MUSS · A · S1] Schutz gegen die gängigen Angriffsklassen für
  Webanwendungen (u. a. Einschleusen von Befehlen, Cross-Site-Scripting,
  Cross-Site-Request-Forgery, fehlerhafte Zugriffskontrolle).
- NFA-007 [MUSS · A · S1] Hochgeladene Dateien werden auf Typ und Größe geprüft
  und nur an Berechtigte ausgeliefert.
- NFA-008 [MUSS · A · S1] Zugangsdaten und Schlüssel liegen nicht im Quellcode.

Datenschutz

- NFA-009 [MUSS · A · S3] Personenbezogene Daten sind auf das Notwendige
  begrenzt; Auskunft (Export je Person/Kunde) und Löschung bzw. Anonymisierung
  sind möglich.
- NFA-010 [MUSS · A · S3] Zugriff auf Personal- und Zeitdaten nur für
  Berechtigte.
- NFA-011 [SOLL · A · S5] Konfigurierbare Aufbewahrungsfristen.

Leistung

- NFA-012 [SOLL · A · S1] Übliche Seiten und API-Aufrufe antworten beim
  angenommenen Mengengerüst (3.2) in unter einer Sekunde.
- NFA-013 [SOLL · A · S1] Die Verfügbarkeitsprüfung beim Hinzufügen einer
  Position antwortet in unter einer halben Sekunde.
- NFA-014 [SOLL · A · S1] Ein Projekt mit 500 Materialpositionen bleibt flüssig
  bedienbar.

Betrieb

- NFA-015 [MUSS · A · S1] Tägliche automatische Sicherung von Datenbank und
  Dateien; die Wiederherstellung ist dokumentiert und erprobt.
- NFA-016 [KANN · A · S10] Zusätzlich zur Installation direkt auf dem Server
  (NFA-027 ff.) eine Bereitstellung als Container.
- NFA-017 [SOLL · A · S1] Getrennte Umgebungen für Entwicklung, Test und
  Betrieb; Testdaten per Befehl erzeugbar.
- NFA-018 [SOLL · A · S4] Protokollierung von Fehlern mit Benachrichtigung der
  Betreiber.

Qualität und Wartbarkeit

- NFA-019 [MUSS · A · S1] Automatisierte Tests für Kernlogik: Verfügbarkeit,
  Rechteprüfung, Preis- und Stundensatzermittlung, Artikelnummernprüfung.
- NFA-020 [SOLL · A · S1] Automatisierte Prüfung bei jeder Codeänderung (Tests,
  Stilprüfung, statische Analyse).
- NFA-021 [SOLL · A · S1] Fachliche Module sind im Code klar getrennt, sodass
  Rechte, Navigation und API je Modul geschnitten sind.

Benutzbarkeit

- NFA-022 [MUSS · V · S1] Responsive ab 360 Pixel Bildschirmbreite.
- NFA-023 [MUSS · A · S1] Unterstützung der aktuellen Versionen von Chrome,
  Firefox, Safari und Edge.
- NFA-024 [SOLL · A · S1] Bedienelemente der mobilen Ansichten (Packen,
  Zeiterfassung) sind für Touch-Bedienung und Arbeit mit Handschuhen
  ausreichend groß.
- NFA-025 [SOLL · A · S5] Barrierearmut in Anlehnung an WCAG 2.1 Stufe AA.
  Ein Test über alle Seiten und Dialoge eines
  Administrators prüft, dass jedes aria-describedby und aria-labelledby auf ein
  vorhandenes Element zeigt; die Hilfetexte der Formulare tragen die Kennung,
  die Django nennt.
- NFA-026 [SOLL · A · S1] Alle Texte der Oberfläche liegen in Sprachdateien;
  Deutsch ist vollständig, weitere Sprachen sind ergänzbar.

Installation und Aktualisierung

- NFA-027 [MUSS · V · S1] Das gesamte System lässt sich mit geringem Aufwand
  installieren. Referenzumgebung ist Ubuntu Server (aktuelle LTS-Version) mit
  NGINX als Webserver und MariaDB. Welche Versionen unterstützt sind, nennt
  NFA-063.
- NFA-028 [MUSS · A · S1] Alle Bestandteile – Webserver, Anwendung, Datenbank,
  Hintergrundaufgaben und Dateiablage – laufen auf einem einzigen Server.
  Externe Dienste sind für den Betrieb nicht zwingend erforderlich.
- NFA-029 [MUSS · A · S1] Die Laufzeit kommt aus der Paketverwaltung des
  Betriebssystems (Python, NGINX, MariaDB). Die Python-Bibliotheken werden in
  eine eigene, abgeschlossene Umgebung mit festgeschriebenen Versionen
  installiert. Zusätzliche Server (z. B. für Zwischenspeicher, Suche,
  Warteschlangen oder Echtzeitverbindungen) sind nicht nötig und höchstens
  optional.
- NFA-030 [MUSS · A · S1] Es gibt eine Schritt-für-Schritt-Anleitung für die
  Referenzumgebung mit fertigen Beispielkonfigurationen für NGINX (HTTPS) und
  MariaDB.
- NFA-031 [MUSS · V · S1] Ein Installationsskript richtet auf einem frisch
  installierten Ubuntu Server alles ein: Pakete, Python-Umgebung,
  Anwendungsdienst, Datenbank und Datenbanknutzer, NGINX-Konfiguration,
  Zertifikat, Hintergrundaufgaben, ersten Administrator. Ziel: betriebsbereit
  in unter 30 Minuten mit Linux-Grundkenntnissen, da jeder Betrieb selbst
  installiert.
- NFA-063 [MUSS · V · S1] Installationsskript, Aktualisierungsbefehl,
  Sicherung und Wiederherstellung laufen unter Ubuntu Server 24.04 LTS und
  unter Ubuntu Server 26.04 LTS – jeweils mit den Paketen, die diese Version
  mitbringt (Python, NGINX, MariaDB). Jede unterstützte Version ist erprobt
  [A]. Auf einer älteren Version bricht das Skript ab, bevor es etwas ändert;
  auf einer anderen neueren weist es darauf hin, dass sie nicht erprobt ist
  [A]. Eine bestehende Installation übersteht den Wechsel von 24.04 auf
  26.04: Danach bringt der Aktualisierungsbefehl (NFA-034) sie wieder in Gang
  [A]. Kommt eine neue LTS-Version hinzu, wird diese Liste fortgeschrieben
  [A]. Das gilt auch auf dem Raspberry Pi, dort zusätzlich
  unter Raspberry Pi OS auf Grundlage von Debian 13 (NFA-070).
- NFA-032 [MUSS · A · S1] Die gesamte Konfiguration liegt in einer einzigen
  Datei (Adresse, Datenbankzugang, E-Mail-Versand); sinnvolle Voreinstellungen
  machen weitere Anpassungen überflüssig.
  Die Konfigurationsdatei (Datenbankpasswort, geheimer Schlüssel) gehört dem Dienstkonto (Modus 400);
  der Webserver-Benutzer (www-data) bleibt in der Gruppe des Dienstkontos (Socket, media), kann die Datei aber nicht
  lesen. backup.sh schreibt seine Statusdatei ohne einem Link im Datenordner zu
  folgen.
  Ein Produktionsserver startet nicht, wenn secret_key der Platzhalter der Beispieldatei oder ein
  bekannter Standardwert ist. Wiederherstellung und Sicherung laufen als root, ohne einem Link im Datenordner des
  Dienstkontos zu folgen: restore.sh entpackt im Ordner der Sicherungen (gehört root) und ersetzt media mit mv -T. Der
  Webserver-Benutzer bleibt in der Gruppe des Dienstkontos (Socket); Dateien im Datenordner, die für die Gruppe lesbar sind,
  kann er lesen (offen, 12.2 Nummer 46).
- NFA-033 [MUSS · A · S1] Ersteinrichtung im Browser: Firmendaten,
  Administrator, Nummernkreise, Steuerarten, auf Wunsch Beispieldaten.
- NFA-064 [MUSS · V · S1] Die Ersteinrichtung ist ohne den einmaligen
  Einrichtungsschlüssel nicht erreichbar – auch dann nicht, wenn der
  Schlüssel noch gar nicht erzeugt wurde. Das Installationsskript erzeugt ihn,
  bevor der Webserver die Anwendung ausliefert. Nur in einer ausdrücklich so
  eingestellten Entwicklungsumgebung geht es ohne Schlüssel [A].
- NFA-066 [MUSS · V · S1] Statt der MariaDB auf demselben Server lässt sich
  bei der Installation ein vorhandener Datenbankserver angeben: Rechnername
  oder Adresse, Port, Benutzer, Passwort und Name der Datenbank. Die Datenbank
  ist bereits angelegt und der Benutzer hat darauf alle Rechte. Abgelehnt
  werden der Benutzer root und jeder Benutzer mit Rechten über diese eine
  Datenbank hinaus – auf andere Datenbanken, auf den Server als Ganzes oder
  über Rollen [A]. Das Skript prüft Verbindung, Rechte und Zeichensatz, bevor
  es etwas ändert, und meldet jeden Grund für eine Ablehnung. Liegt der
  Datenbankserver auf einem anderen Rechner, wird die Verbindung mit TLS
  verschlüsselt, wahlweise mit Prüfung des Zertifikats; unverschlüsselt nur
  auf ausdrücklichen Wunsch [A]. Die Selbstprüfung (NFA-037) prüft die Rechte
  des Benutzers fortlaufend.
- NFA-067 [MUSS · V · S1] Die Installation fragt, ob die Daten verschlüsselt
  abgelegt werden sollen. Verschlüsselt werden dann die Dateien der Datenbank
  (MariaDB-Verschlüsselung für Tabellen, Protokolle und Zwischendateien) und
  die Sicherungen [A]. Alles hängt an einem Wiederherstellungsschlüssel, den
  das Skript einmal anzeigt und der sich mit root-Rechten jederzeit wieder
  anzeigen lässt. Im Notfall entschlüsselt ein angemeldeter Administrator
  mit diesem Schlüssel und Standardwerkzeugen (openssl, MariaDB) – ohne
  Rentalars [A]. Bei einem vorhandenen Datenbankserver (NFA-066) verschlüsselt
  Rentalars die Sicherungen; die Dateien der Datenbank sind Sache dieses
  Servers, die Selbstprüfung zeigt, ob er verschlüsselt [A].
- NFA-068 [SOLL · V · S1] Verschlüsselung und Datenbank lassen sich nachträglich
  ändern, ohne dass Daten verloren gehen oder unbemerkt abweichen: Ein Befehl
  verschlüsselt eine bestehende Installation an Ort und Stelle; ein zweiter
  zieht die Datenbank in eine neue Datenbank mit eigenem Benutzer um – auf
  demselben oder einem anderen Server. Beide sichern vorher, halten die
  Anwendung während des Vorgangs an und vergleichen danach Zeilenzahl und
  Prüfsumme jeder Tabelle. Erst wenn alles übereinstimmt, wird umgestellt;
  sonst bleibt die bisherige Datenbank in Betrieb. Die alte Datenbank wird
  nicht gelöscht, sondern von Hand entfernt, wenn alles läuft [A].
- NFA-034 [MUSS · A · S1] Aktualisierung mit einem einzigen dokumentierten
  Befehl einschließlich Datenbankmigration. Vorher wird automatisch gesichert;
  der Rückweg auf die vorige Version ist beschrieben.
- NFA-035 [MUSS · V · S1] HTTPS mit gültigem Zertifikat ist Teil der
  Installation – auch solange der Server nur per VPN erreichbar ist.
  Unterstützt werden automatisch erneuerte Zertifikate bei Erreichbarkeit aus
  dem Internet, die Ausstellung über einen DNS-Nachweis ohne öffentliche
  Erreichbarkeit und das Einbinden eines eigenen Zertifikats.
- NFA-036 [SOLL · A · S1] Hintergrundaufgaben (E-Mail-Versand, Erinnerungen,
  Sicherung, große Importe) nutzen Bordmittel des Betriebssystems
  (Systemdienst, Zeitsteuerung) statt eigener Infrastruktur.
- NFA-037 [SOLL · A · S4] Eine Selbstprüfung (Seite für Administratoren und
  Befehl) zeigt den Zustand der Installation: Versionen, Dateirechte,
  Datenbankverbindung, E-Mail-Versand, letzte Sicherung, freier Speicherplatz.

Systemanforderungen

- NFA-038 [MUSS · V · S1] Referenzsystem: 4 Prozessorkerne und 8 GB
  Arbeitsspeicher. Darauf läuft das gesamte System (NFA-028) für einen kleinen
  Betrieb mit bis zu zwei gleichzeitig arbeitenden Nutzern flüssig.
- NFA-039 [MUSS · A · S1] Die Antwortzeiten aus NFA-012 bis NFA-014 gelten auf
  dem Referenzsystem bei zwei gleichzeitigen Nutzern und dem Mengengerüst aus
  3.2.
- NFA-040 [SOLL · A · S1] Im Normalbetrieb belegt das System höchstens die
  Hälfte des Arbeitsspeichers des Referenzsystems, damit Reserven für
  Sicherung, PDF-Erzeugung und Import bleiben.
- NFA-041 [SOLL · A · S5] Rechenintensive Vorgänge (großer Import, Sammeldruck,
  Sicherung) laufen im Hintergrund und blockieren die Bedienung nicht.
- NFA-042 [SOLL · A · S1] Mitgelieferte, auf das Referenzsystem abgestimmte
  Voreinstellungen für Datenbank und Anwendungsserver.
- NFA-043 [SOLL · A · S1] Die Anleitung nennt eine Empfehlung für den
  Speicherplatz (SSD) und erklärt, wodurch er wächst (vor allem Anhänge und
  Sicherungen).
- NFA-044 [KANN · A · S5] Ein mitgeliefertes Prüfskript erzeugt Testdaten im
  Umfang des Mengengerüsts und misst die Antwortzeiten auf der eigenen
  Hardware.

Verbreitung und Betrieb im Internet

- NFA-045 [MUSS · V · S1] Rentalars ist nicht mandantenfähig: Jeder Betrieb
  betreibt seine eigene Instanz mit eigener Datenbank.
- NFA-046 [MUSS · V · S1] Rentalars ist für jeden Betrieb kostenlos verfügbar
  und selbst installierbar. Installationspaket, Installationsskript und
  Dokumentation sind öffentlich abrufbar.
- NFA-047 [MUSS · A · S1] Installation, Aktualisierung, Sicherung und
  Wiederherstellung sind so dokumentiert, dass ein Betrieb sie ohne Hilfe des
  Entwicklers durchführen kann. Dazu gehört ein Benutzerhandbuch für die
  Fachfunktionen.
- NFA-048 [MUSS · V · S1] Die Anwendung ist von Beginn an so abgesichert, dass
  sie ohne Umbau aus dem Internet erreichbar betrieben werden kann, auch wenn
  sie in der Testphase nur per VPN genutzt wird.
- NFA-049 [SOLL · A · S4] Für den Betrieb aus dem Internet:
  Zwei-Faktor-Anmeldung für Konten mit weitreichenden Rechten erzwingbar
  (AUT-006), sichere Voreinstellungen in der mitgelieferten
  NGINX-Konfiguration, Hinweis in der Selbstprüfung bei unsicheren
  Einstellungen.
- NFA-065 [MUSS · A · S1] Nach einer Aktualisierung sehen alle Nutzer ohne
  eigenes Zutun die neue Oberfläche: Gestaltungs- und Skriptdateien tragen
  eine Kennung ihres Inhalts in der Adresse, sodass der Browser keine
  veraltete Fassung aus seinem Zwischenspeicher verwendet.
- NFA-050 [SOLL · A · S1] Die Anwendung überträgt von sich aus keine Daten an
  Dritte. Ein Hinweis auf verfügbare Aktualisierungen ist abschaltbar. Eine
  Adresse verlässt das Haus nur auf einen Klick: mit dem
  Routenlink zu Google Maps (UIX-033) und mit "Karte anzeigen" an
  OpenStreetMap und Nominatim (UIX-034); wer Karten sofort laden lässt,
  stellt das selbst ein.
- NFA-051 [SOLL · A · S3] Das Referenzsystem bleibt auch bei kurzzeitig bis zu
  zehn gleichzeitigen Nutzern bedienbar (z. B. wenn die Crew Zeiten erfasst).
  Für dauerhaft mehr gleichzeitige Nutzer nennt die Anleitung Richtwerte für
  größere Hardware.

Lizenz und Pflege

- NFA-052 [MUSS · V · S1] Rentalars steht unter der GNU General Public License,
  Version 3 oder später (GPL-3.0-or-later). Der Quellcode ist öffentlich
  abrufbar; das Paket enthält Lizenztext und Urheberhinweis.
- NFA-053 [MUSS · A · S1] Alle verwendeten Bibliotheken haben eine mit der GPL
  v3 vereinbare Lizenz; das wird bei jeder Codeänderung automatisch geprüft.
  Code aus Projekten unter AGPL wird nicht übernommen, weil
  sonst deren zusätzliche Bedingungen gälten.
- NFA-054 [SOLL · A · S1] Django und Python werden auf Versionen gehalten, die
  noch Sicherheitskorrekturen erhalten; bevorzugt werden die Langzeitversionen
  von Django und die Python-Version der jeweiligen Ubuntu-LTS-Version. Der
  Aktualisierungsbefehl (NFA-034) prüft die Voraussetzungen, bevor er etwas
  ändert.

Verständlichkeit und Dokumentation des Codes

- NFA-055 [MUSS · V · S1] Der Code ist so dokumentiert, dass nachvollziehbar
  ist, was geschieht und warum. Maßstab ist eine Person mit Grundkenntnissen in
  Python, die das Projekt nicht kennt.
- NFA-056 [MUSS · A · S1] Jedes Modul, jede Klasse und jede Funktion mit
  Fachlogik trägt eine Beschreibung: Zweck, Eingaben, Ergebnis, Sonderfälle, wo
  sinnvoll mit einem kleinen Beispiel. Kommentare im Code erklären das Warum
  (Fachregel, Abwägung, bekannte Falle) und wiederholen nicht, was die Zeile
  ohnehin zeigt.
- NFA-057 [MUSS · A · S1] Fachregeln nennen die Anforderung, die sie umsetzen
  (z. B. "VFG-002" an der Verfügbarkeitsberechnung). Über die Suche nach der
  Kennung findet sich zu jeder Anforderung die Stelle im Code und der
  zugehörige Test.
- NFA-058 [MUSS · A · S1] Entwicklerdokumentation im Quellcode-Verzeichnis:
  Überblick über Aufbau und Module, Datenmodell mit Schaubild, Ablauf der
  Kernvorgänge (Verfügbarkeit, Preisberechnung, Zuordnung von E-Mails, Import)
  in Worten und an Beispielen, Einrichten einer Entwicklungsumgebung Schritt
  für Schritt.
- NFA-059 [SOLL · A · S1] Wichtige Entscheidungen werden kurz festgehalten: was
  entschieden wurde, warum, welche Alternativen verworfen wurden. Die
  Entscheidungen aus Kapitel 12.1 bilden den Anfang.
- NFA-060 [SOLL · A · S1] Tests sind als lesbare Beispiele geschrieben und
  sprechend benannt. Die Abnahmeszenarien aus Kapitel 11 finden sich als Tests
  wieder.
- NFA-061 [MUSS · V · S1] Sprache: Im Code ist alles englisch – Bezeichner,
  Beschreibungen, Kommentare und Entwicklerdokumentation. Eine feste
  Übersetzungsliste ordnet die deutschen Fachbegriffe dieses Katalogs den
  englischen Bezeichnern zu (Abschnitt 2.1). Oberfläche und Benutzerhandbuch
  bleiben deutsch [A]. Ausdrücklich
  auch in der Datenbank und überall im Code: Namen von Tabellen
  und Spalten, gespeicherte Werte von Auswahlfeldern und Schlüssel
  gespeicherter JSON-Daten sind englisch, ebenso Namen in Vorlagen,
  CSS-Klassen, Bezeichner in JavaScript und die Entwicklerdokumentation.
  Was in einer bestehenden Datenbank noch deutsch heißt, benennt eine
  Migration um, ohne Daten zu verlieren (NFA-004); Werte, die die API nach
  außen gibt, ändern sich dabei nur in einer neuen Version der API
  (API-005) [A]. Oberfläche und
  Benutzerhandbuch gibt es auch auf Englisch (UIX-029), und die Texte der Oberfläche im Code sind dabei das
  Englisch der Oberfläche.
- NFA-062 [SOLL · A · S1] Verständlichkeit geht vor Kürze: sprechende Namen,
  kurze Funktionen, keine verdichteten Einzeiler in der Fachlogik. Stil und
  Formatierung sind einheitlich und werden automatisch geprüft; die Prüfung
  meldet auch fehlende Beschreibungen (NFA-020).

Weitere Anforderungen

- NFA-069 [SOLL · V · S6] Der Befehl `rentalars` und die Aktualisierung
  (NFA-034) funktionieren auch dann, wenn die Skripte eines Pakets ihr
  Ausführungsrecht verloren haben, etwa weil es auf einem anderen Rechner
  entpackt oder über eine Freigabe kopiert wurde. Jede Installation und
  Aktualisierung legt den Befehl `rentalars` neu an, und die Skripte rufen
  einander so auf, dass sie das Ausführungsrecht nicht brauchen.

Ausbaustufe 7: Weitere Anforderungen

- NFA-070 [SOLL · V · S8] Rentalars lässt sich auf einem Raspberry Pi 4 oder 5
  (64 Bit, arm64) installieren und aktualisieren – mit Ubuntu Server 24.04
  LTS oder 26.04 LTS in der Fassung für den Raspberry Pi und mit Raspberry
  Pi OS auf Grundlage von Debian 13. Installationsskript, Aktualisierung und
  der Befehl `rentalars` erkennen beides an Betriebssystem, Architektur und
  Modell, installieren die Pakete unter ihren Debian-Namen, wo diese
  abweichen, und prüfen Python, MariaDB, NGINX und certbot. Die Zahl der
  Arbeitsprozesse richtet sich nach dem Arbeitsspeicher (NFA-042). Unter
  4 GB Arbeitsspeicher und auf einer SD-Karte warnt das Skript und empfiehlt
  eine SSD für Datenbank und Sicherungen. Unter Ubuntu auf x86 gilt
  das Referenzsystem (NFA-038).
  Was sich in der Bauumgebung nicht erproben
  lässt, nennt 12.2 (24 m).

Ausbaustufe 8: Weitere Anforderungen

- NFA-071 [SOLL · V · S8] Verbindungen, die der Server zu Adressen aufbaut,
  die jemand in der Oberfläche oder über die API einträgt – verknüpfte
  Kalender (ICS-Links, CalDAV; PER-023, PER-031), Webhooks (API-012), die
  Server der Postfächer (IMAP, SMTP; EML-041) und jede weitere solche
  Verbindung –, erreichen keine internen Ziele: Rentalars löst den Namen
  auf und lehnt Loopback, Link-Local, private Netze, Carrier-Grade-NAT,
  Multicast, reservierte Bereiche und die eigenen Adressen des Servers ab,
  außer der Betreiber gibt sie in der Konfigurationsdatei frei (NFA-032) –
  etwa ein NAS im eigenen Netz mit CalDAV; die Anleitung beschreibt das.
  Verbunden wird mit der geprüften Adresse, ohne zweite Auflösung des
  Namens (Schutz vor DNS-Rebinding). Weiterleitungen folgt Rentalars nur
  selbst und prüft jede erneut. Die Adressen der Konfigurationsdatei, etwa
  für Karten (UIX-034), sind Sache des Betreibers und davon ausgenommen.
  Eine Ablehnung nennt einen verständlichen Grund. Vorhandene Einstellungen,
  die nun auf ein gesperrtes Ziel zeigen, nennt die Selbstprüfung
  (NFA-037); gelöscht wird nichts. Anlass: Kalenderadressen ließen sich
  frei auf interne Ziele setzen, die der Server dann aufrief. Seit Version
  0.24 gilt die lokale KI, die der Betreiber mit `sudo rentalars ai
  install` einrichtet (EML-040), als Sache des Betreibers wie die Adressen
  der Konfigurationsdatei: Rentalars erreicht sie, ohne dass jemand sie
  freigibt. Eine Schnittstelle für KI, die jemand in der Oberfläche
  einträgt (ADM-017), prüft Rentalars wie jede andere Verbindung.
- NFA-072 [SOLL · V · S8] Zugangsdaten gehen nur an den Server, für den sie
  eingetragen sind: Benutzername, Passwort oder Token eines verknüpften
  Kalenders und jeder anderen Verbindung (NFA-071) sendet Rentalars nur an
  genau dasselbe Schema, denselben Host und denselben Port, auch nach einer
  Weiterleitung. Ausnahmen gelten nur für ausdrücklich genannte Anbieter und
  ihre bekannten Weiterleitungen, etwa die Partitionsserver von iCloud für
  CalDAV.
- NFA-073 [SOLL · V · S8] Im Betrieb (nicht im Entwicklungsmodus) startet
  Rentalars nicht, wenn die Adresse der Installation mit "http://" beginnt,
  außer die Konfigurationsdatei erlaubt es ausdrücklich – etwa für eine
  Installation hinter einem Proxy, der TLS übernimmt und X-Forwarded-Proto
  setzt; die Anleitung beschreibt das. Die Meldung beim Start sagt, was zu
  tun ist, und die Selbstprüfung (NFA-037) nennt den Stand. Das ergänzt
  NFA-005 und NFA-035; Installationen, die das Installationsskript
  eingerichtet hat, haben eine Adresse mit "https://" [A].


Ausbaustufe 8: Weitere Anforderungen

- NFA-074 [SOLL · V · S8] Adressen nach Bereich: Seiten stehen unter der Adresse des Bereichs, zu dem
  sie gehören: Projekte → Anfragen unter /projects/inquiries/,
  die Staffeln unter /administration/scales/, das Mail-Protokoll unter /administration/mail/log/,
  "Jetzt abrufen" unter /administration/mail/fetch/, die Vorschläge der
  Adressfelder unter /projects/mail-addresses/. Gespeicherte Links der
  Benachrichtigungen folgen diesen Adressen; Links im Code entstehen aus
  den Namen der Seiten, nicht aus fest geschriebenen Pfaden. Die API
  (/api/v1) ist stabil, damit Begleit-App und andere Programme
  funktionieren (API-003).


Ausbaustufe 9: Weitere Anforderungen

- NFA-075 [SOLL · V · S9] Urhebervermerk als zusätzliche Bestimmung nach
  Abschnitt 7 b der GPL: Mit der Datei ADDITIONAL-TERMS.md gilt,
  dass, wer Rentalars oder eine darauf beruhende Software weitergibt (wer
  es nur über das Netz betreibt, gibt es nicht weiter; die
  Bestimmung gilt dafür nicht), den Vermerk "von fld-vt.de" ("by fld-vt.de")
  mit Link unter der Version im Menü und auf der Anmeldeseite erhält;
  ergänzen ist erlaubt, entfernen nicht. Die betroffenen Dateien verweisen
  darauf, ebenso README und Lizenzhinweise. (Keine Rechtsberatung; die
  Formulierung sollte rechtlich geprüft werden.)

Ausbaustufe 9: Weitere Anforderungen

- NFA-076 [SOLL · A · S9] Pakete des Servers bei Installation und
  Aktualisierung (zu UIX-049): Installation und Aktualisierung richten die
  Pakete ein, die eine Version braucht – ffmpeg –, auch bei der
  Aktualisierung von der Vorversion aus; sie warten bis zu zwei Minuten auf
  eine laufende Paketverwaltung, und misslingt es, läuft die Aktualisierung
  mit Warnung durch. Der Selbsttest warnt, wenn ffmpeg fehlt (dann werden nur
  Videos abgelehnt) oder NGINX kleinere Uploads annimmt als der Chat erlaubt.
- NFA-077 [SOLL · V · S9] Keine Unterstützung älterer Versionen:
  Die Datenbankschritte sind zu einem je Bereich zusammengefasst
  (eine Neuinstallation ergibt dieselbe Datenbank). Eine Datenbank einer älteren Version wird nicht
  angefasst: "migrate" und die Aktualisierung brechen mit einer Meldung ab;
  die Wiederherstellung lehnt Sicherungen älterer Versionen ab.

Ausbaustufe 9: Weitere Anforderungen

- NFA-078 [SOLL · V · S9] Deinstallation: "sudo rentalars uninstall" entfernt Rentalars
  von einem Server, nur nach ausdrücklicher Wahl: ohne Angabe zeigt es die
  drei Möglichkeiten und tut nichts. "--dry-run" zeigt, was entfernt würde und
  was bleibt, und ändert nichts (mit "--purge" für die vollständige
  Entfernung). "--keep-data" hält Dienste und Zeitgeber an, entfernt die
  NGINX-Seite, das Programm und den Befehl und behält Datenbank, Dateien,
  Sicherungen, Konfiguration und Verschlüsselungsschlüssel. "--purge" entfernt
  zusätzlich die Datenbank und den Datenbankbenutzer von Rentalars (auf einem
  fremden Datenbankserver nur deren Tabellen), Sicherungen, Datenordner,
  Konfiguration, Zertifikat und Systembenutzer – nach Eingabe des Hostnamens;
  ohne Terminal nur mit "--yes-i-really-want-to-delete-everything". Vorher
  kann eine letzte Sicherung geschrieben werden ("--backup-to"). Pakete,
  fremde Datenbanken und der Verschlüsselungsschlüssel von MariaDB bleiben
  immer; alle Pfade stammen aus denselben Festlegungen wie bei der
  Installation.

Ausbaustufe 10: Weitere Anforderungen

- NFA-079 [SOLL · V · S10] Informationssicherheit der KI-Zusammenfassungen
: Auf allen
  Wegen, die Text an einen KI-Anbieter schicken (Zusammenfassung von Hand und
  automatisch, Antwortentwurf), gilt: Datensparsamkeit – IBAN, Karten- und
  Zugangsdaten, E-Mail-Adressen und Telefonnummern werden vor dem Senden
  entfernt, je Datenklasse einstellbar, Namen und Adressen im Fließtext lassen
  sich nicht erkennen und gehen mit. Texte aus Mails und Notizen sind nicht
  vertrauenswürdig: unsichtbare Zeichen werden zuerst entfernt und der Text
  nach NFKC normalisiert, damit sie den Filter für Datenklassen nicht umgehen;
  danach werden die Datenklassen entfernt (breitere Trenner bei IBAN und
  Karten) und Begrenzer und Sondertoken entschärft – derselbe Weg für
  Zusammenfassungen, Entwürfe und das Lesen von Altrechnungen (diese behalten
  Telefonnummern, entfernen IBAN, Karten, Zugangsdaten und E-Mail-Adressen), die Anweisung bleibt getrennt, die Antwort des Modells löst nie
  eine Handlung aus, wird zu reinem Text bereinigt und beim Anzeigen maskiert
  (kein HTML, keine Bilder, keine Links). Internetanbieter nur mit https, ohne
  Weiterleitungen, mit Schutz vor Adressen im eigenen Netz (NFA-071); der
  Schlüssel steht verschlüsselt, nie in Protokoll oder Fehlerseite.
  Handaufrufe sind je Nutzer und Stunde begrenzt, der Nachtauftrag hat ein
  Budget. Das Protokoll hält fest, wer was ausgelöst hat, mit Zählwerten statt
  Inhalten. Kundenexport und Anonymisierung erfassen Zusammenfassungen und
  ihre Fassungen; der Kundenexport enthält sie nur für den, der sie auf der
  Projektseite lesen dürfte (Leserecht für alle Nachrichten, auch mit Schloss),
  und zählt die ausgelassenen (ai_summaries_withheld); das Löschen einer
  Chatnachricht löscht die Zusammenfassungen, die den Chat danach gelesen
  haben. Das Lesen von Eingangsrechnungen durch die KI hat keinen
  Datenschutzfilter (offen). Offen: eine Positivliste der Anbieter-Hosts je Betreiber,
  Chat als Auslöser der Veraltung, Fehlertexte des Anbieters im Protokoll;
  nicht lösbar: Fehler und Erfindungen der Modelle (Hinweis in der
  Oberfläche).

Ausbaustufe 10: Weitere Anforderungen

- NFA-080 [SOLL · V · S10] Sicherung konsistent, Auszug nie unverschlüsselt,
  Wiederherstellung beschrieben (Datenbank und
  Dateien werden zeitversetzt gesichert; bei verschlüsselten Sicherungen liegt
  der Auszug unverschlüsselt; die Wiederherstellung soll genauer beschrieben
  sein): Eine gelöschte Datei wandert für sieben Tage in den Ordner `.deleted`
  der Dateien, den die Sicherung mitnimmt; die tägliche Wartung löscht sie
  danach. So ist alles, was die Datenbank einer Sicherung nennt, auch in ihren
  Dateien. Mit verschlüsselten Sicherungen läuft der Auszug der Datenbank durch
  die Verschlüsselung, bevor er auf die Platte kommt (`database.sql.enc`; Datei
  mit Rechten 600, auch im temporären Ordner nie lesbar). Die Anleitungen und
  `rentalars restore` nennen die Schritte der Wiederherstellung und prüfen am
  Ende, was zu prüfen ist.
- NFA-081 [SOLL · V · S10] Bibliotheken ohne bekannte Schwachstellen, Bilder nur in erwarteten Formaten: Die Versionen in requirements.txt sind festgelegt und
  werden bei einer Lieferung auf den Stand ohne bekannte Schwachstellen gebracht (Pillow 13.0.0, pypdf 6.21.2,
  Brotli 1.2.1). scripts/check.sh fragt mit pip-audit die Schwachstellendatenbank ab (RENTALARS_SKIP_AUDIT=1 überspringt es
  ohne Netz), und eine Datei für Dependabot lässt GitHub Aktualisierungen vorschlagen. Hochgeladene Bilder (Logo, Foto im
  Chat, Beleg, Etikettenvorlage, eingegangene Belege) öffnet Rentalars nur mit den Formaten, die die jeweilige Stelle
  erwartet; eine GIF-, XBM- oder TIFF-Datei mit der Endung .png wird abgewiesen, ohne dass der Decoder des fremden Formats
  sie liest.
- NFA-082 [SOLL · V · S10] Anmeldung hinter einem Vorschaltserver: Steht ein anderer Server vor dem NGINX der Installation (Load Balancer, Firewall), sehen alle Besucher
  dieselbe Adresse, und zwanzig Fehlversuche irgendeines Besuchers sperren die Anmeldung für alle. Unter [rentalars]
  trusted_proxies in der Konfigurationsdatei stehen die Adressen oder Netze dieser Server (mit Komma). Nur Anfragen von dort
  dürfen NGINX die Adresse des Besuchers in X-Forwarded-For nennen (set_real_ip_from, real_ip_recursive); die Installation und
  rentalars nginx-site schreiben dazu eine eigene Datei in /etc/nginx/snippets und binden sie in die Site ein; die Deinstallation entfernt sie.
- NFA-083 [SOLL · V · S10] Weiterleitungen nur auf eigene Seiten: Der Parameter next eines Formulars führt nur auf eine Seite dieser Installation. Alle Stellen
  benutzen dieselbe Prüfung (rentalars/core/redirects.py mit der Prüfung von Django, die auch die Schreibweise /\host
  kennt, die Browser wie //host lesen); sonst geht es auf die Standardseite.
- NFA-084 [SOLL · V · S10] Bilder und Videos werden stets neu gerendert, der Standort bleibt: Jedes Foto, das
  Rentalars aufnimmt – im Chat, an einer Defektmeldung (Seite, API, Packliste), als Foto eines Spesenbelegs und an Modell und
  Exemplar sowie ein Bild, das als Handbuch, Protokoll oder Sonstiges am Material hängt (nicht die Kopie einer Rechnung) –, wird nicht aufbewahrt, sondern neu erzeugt: aufrecht, als JPEG (progressiv, optimiert, Farbprofil bleibt),
  höchstens 2048 Pixel lang, auch wenn es schon kleiner ist. Von den Metadaten bleibt der Standort (Breite, Länge und, soweit
  plausibel, Höhe); Gerät, Aufnahmezeit, Richtung, Kommentar und XMP entfallen, die vom Chat und den Fotos des Materials
  erzeugte Vorschau trägt weder Standort noch Gerät (nur ein kleines Farbprofil bleibt, bis 128 KB). Videos werden mit ffmpeg auf höchstens 720p (H.264/AAC, MP4) ohne Metadaten umgerechnet
  (UIX-049). Unberührt bleiben Dokumente, die so bleiben müssen, wie sie kamen: Projektdateien, Rechnungen und Belege der
  Buchhaltung, Mailanhänge, Hallenplan, Logo, Etikettenvorlage sowie Lieferanten- und Zertifikatsdateien. Eine Stelle (rentalars/core/photos.py) erzeugt die Fotos.


## 7. Datenmodell (Entwurf)

Vereinfachte Übersicht der Fachobjekte. Namen sind Arbeitstitel.

### 7.1 Beziehungen

    Kategorie 1───n Materialmodell 1───n Materialinstanz
                         │n                   │n
                         │                    │ (abweichende Zuordnung)
                         1                    1
    Kategorie 1──────────n Produkt ───────────┘
                              │1
                              │n
    Kunde 1───n Projekt 1───n Materialposition n───m Materialinstanz
                   │1                    (Zuteilung beim Packen)
                   │n
              Personalposition n───1 Funktion
                   │n                   │
                   1                    │
                Person 1───n PersonFunktion n───1 Funktion
                   │1        (Stunden- und Tagessatz)
                   │n
              Zeiteintrag n───1 Projekt, n───1 Funktion

    Nutzer n───m Rolle 1───n Recht
    Nutzer n───m Projekt   (Projektmitgliedschaft)
    Nutzer 0..1───1 Person

    Projekt 1───n Teilgruppe 1───n Materialposition
    Teilgruppe 0..1───n Teilgruppe      (Untergruppe)
    Projekt 0..1───n Projekt            (Teilprojekt, spätere Ausbaustufe)

    Materialinstanz 0..1───n Materialinstanz   (verbaut in)
    Produkt 1───n Setbestandteil n───1 Produkt (Set)
    Funktion 1───1 Produkt                     (Dienstleistung, Kategorie D; 1:1)
    Postfach 0..1───n E-Mail n───1 Projekt     (nur zugeordnete Mails; ihr Postfachname bleibt)
    Personalposition n───0..1 Projektphase     (Personal je Phase)
    Materialposition n───0..1 Materialposition (Alternative; ebenso Teilgruppe)
    Person 1───n verknüpfter Kalender 1───n Verfügbarkeit (belegte Zeiten)
    Produkt n───0..1 Kunde                     (Eigentümer, Kundenmaterial)
    Personalposition 1───n Einsatzanfrage per Mail (Antwort per Mail)
    Projekt n───0..1 Nutzer                    (Wiedervorlage für, PRJ-105)
    Projekt 1───n Dokument eines Lieferanten n───1 Händler (Zumietung, PRJ-106)
    Projekt 1───n Chatnachricht n───1 Nutzer   (Chat im Projekt, UIX-010)
    Projekt 1───n Spesenposten n───1 Person    (Spesen, ZEI-019)
    Projekt 1───n Fahrt                        (aus Phasen und Adressen ermittelt, PRJ-097)
    Automation 1───n Lauf                      (Protokoll der Automation, ADM-013)
    Postfach 1───n Adresse eines Postfachs     (Aliasse, EML-047)
    Projekt 1───n Beteiligter n───1 Person     (nur Servicefall, PRJ-108)
    Zeitraum 1───n Anteil n───1 Funktion       (Anteile eines Zeitraums, ZEI-025)
    Zuschlagsregel; eigener Feiertag           (Einstellungen des Betriebs, PER-040)
    Projekt 1───n Anpassung einer Fahrt        (entfernt, geändert, eigene Fahrt, PRJ-111)
    Projekt 1───n Zusammenfassung der Korrespondenz (EML-040)
    KI-Anbieter 1───n Verwendung; KI-Aufruf    (Schnittstelle und Protokoll, ADM-017)
    Vorbereitete Adressänderung n───1 Nutzer   (vorbereitet, angewendet von, ADM-016)
    Materialinstanz n───0..1 Materialinstanz   (Preis enthalten in, Kaufset, MAT-054)
    Projekt n───0..1 Defektmeldung             (Servicefall aus der Meldung, MAT-057)
    Anfrage 0..1───1 Defektmeldung             (Meldung unter Projekte → Anfragen, MAT-057)
    Projekt 1───0..1 Erinnerung an die Rechnung (DOK-015)

    Stufe 9 (Logistik):
    Materialinstanz 1───0..1 Fahrzeugdaten     (Fuhrpark: das Exemplar eines Fahrzeugprodukts, LOG-002)
    Projekt 1───n Fahrzeugbuchung n───1 Produkt (Fahrzeug), n───0..1 Materialinstanz,
      n───0..1 Lieferant                      (Logistik im Projekt, LOG-001, LOG-010)
    Projekt 1───n Fahrteinsatz n───1 Fahrzeugbuchung (Zugfahrzeug), n───0..1 Fahrzeugbuchung
      (Anhänger); die Fahrt ist über ihren Schlüssel benannt (LOG-007)
    Personalposition n───0..1 Fahrzeugbuchung  (wer mit welchem Fahrzeug fährt, Fahrer, LOG-008)
    Packliste n───0..1 Fahrzeugbuchung         (verladen in, LOG-011)
    Qualifikationsart: Führerscheinklassen     (LOG-012)
    Stufe 9:
    Postfach, Alias n───m Rolle                (als Absender wählbar für, EML-052)
    Anfrage: von Hand notiert, n───0..1 Kunde  (EML-053)
    Monatsabrechnung n───1 Kunde, n───m Projekt (Servicefälle), n───0..1 Dokument (DOK-016)
    Dokument n───m Projekt                     (weitere abgerechnete Servicefälle, DOK-016)

    Projekt 1───n Packliste 1───n Materialposition   (Zuordnung, Stufe 5)
    Projekt 1───n Dokument 0..1───0..1 Dokument      (Stornorechnung zur Rechnung)
    Kunde 1───n Adresse; Projekt n───0..1 Adresse    (Rechnungs-, Lieferadresse)
    Prüfart n───m Kategorie, n───m Materialmodell; Materialinstanz 1───n Prüfung

### 7.2 Objekte und Kernfelder

Material
- Kategorie (gemeinsam für Material und Produkte): Name, Kürzel (an der
  Hauptkategorie), Oberkategorie, Bezeichnung und Typ der
  kategoriespezifischen Angabe, weitere Zusatzfelder, Voreinstellungen für
  Produkte, eigener Bestand ja/nein, Kundenmaterial ja/nein (nur an einer
  Hauptkategorie mit eigenem Bestand, PRD-043)
- Hersteller: Name
- Händler: Name, Kontakt, Notiz, E-Mail-Adresse, Telefon,
  Ansprechpartner (PRJ-106)
- Materialmodell: Artikelname, Kurzname, Kategorie, Hersteller, Spezifikation
  (in der Oberfläche "Beschreibung", MAT-049),
  kategoriespezifische Angabe, Standardprodukt,
  Führungsart (Einzelexemplare oder Menge), Gewicht, Maße, Leistung (MAT-049;
  jede Angabe an einer Stelle)
- Materialinstanz: ID, Modell, abweichendes Produkt, verbaut in (Instanz),
  Art der Verbindung (fest verbaut/lose enthalten), einzeln planbar,
  Seriennummer, Notiz,
  Kaufdatum ("Rechnungsdatum"), Rechnungsnummer (MAT-050),
  Kaufnotiz, Kaufpreis, Händler, Händler-Artikelnummer, Status,
  Lagerort, Menge (nur bei Mengenmaterial)
- Prüfart: Bezeichnung, Intervall in Monaten, Beschreibung, Kategorien,
  Materialmodelle, aktiv
- Prüfung: Instanz, Prüfart, Datum, Ergebnis, Prüfer, Protokoll; die nächste
  Fälligkeit wird berechnet, nicht gespeichert
- Sperrzeit: Instanz, Zeitraum, Grund
- Herauslösung: Instanz, Projekt, Zeitraum (lose Inhalte, MAT-042)
- Defektmeldung: Instanz, Beschreibung, Foto, Fundort (z. B. Rücknahme eines
  Projekts), gemeldet von und am
- Datei an Modell oder Instanz: Art (Bild, Handbuch, Rechnung,
  Prüfprotokoll, Sonstiges), Titel, Datei
- Lagerort: Bezeichnung, übergeordneter Lagerort (Halle, Regal, Fach, Case),
  Voreinstellung für neue Exemplare ja/nein (MAT-052)

Produkte
- Produkt: Artikelnummer, Kategorie, GTIN/EAN, Bezeichnung,
  Beschreibung, Notiz, Einheit, Steuerart, Mietpreis netto, Verkaufspreis
  netto, Abrechnungsart, Staffel (Voreinstellung/abweichend/keine),
  Kalkulationsnotiz, Produktart (auch Nebenkosten, PRD-045;
  Fahrzeug mit Fahrzeugart, Sätzen und Kosten, LOG-005),
  Mindestbestand, höchster Rabatt in Prozent (PRD-041), Eigentümer (ein
  Kunde; genau bei Kundenmaterial, PRD-043), aktiv; beim
  Dienstleistungsprodukt die Stundengrenze je Tag und der Preis je Stunde ab
  der Grenze (PER-035) und "ohne Zuschläge" (PER-009)
- Setbestandteil: Set-Produkt, Bestandteil-Produkt, Menge
- Staffel: Bezeichnung, Regel für längere Mietdauer; je Zeile Miettage und
  Faktor; gilt als Voreinstellung, für eine Kategorie oder für ein Produkt
- Steuerart: Bezeichnung, Satz, gültig ab
- Einheit: Bezeichnung, Kürzel

Kunden
- Kunde: Kundennummer, Art, Name/Firma, USt-IdNr., Leitweg-ID, Zahlungsziel,
  Standardrabatt, Notiz, aktiv
- Adresse: Kunde, Art (Rechnung oder Lieferung), Bezeichnung, Name, Straße,
  PLZ, Ort, Land, Standard
- Ansprechpartner: Kunde, Name, Funktion, E-Mail, Telefon
- Veranstaltungsort: Name, Adresse, Ansprechpartner vor Ort, Hinweise zu
  Zufahrt und Strom, Lageplan/Hallenplan, aktiv
- Lage einer Adresse (UIX-034): Koordinaten zu einer Adresse
  (Veranstaltungsort, Kunde, Firma und weitere), einmal bei Nominatim
  abgefragt und gespeichert, von Hand korrigierbar

Personal
- Person: Name, Kontakt, Art, verknüpfter Nutzer, aktiv, Sichtbarkeit der
  eigenen Kontaktdaten für Kollegen, Entfernung Wohnung – Betrieb
  in km, freiwillig (ZEI-027); für Telefon, E-Mail-Adresse und
  ihre Sichtbarkeit für Kollegen je der Zeitpunkt der letzten Änderung
  (API-015)
- Funktion: Bezeichnung, Dienstleistungsprodukt (Kategorie D; genau eines, das zu keiner anderen Funktion gehört, PRD-044), Richtwerte
  interne Kosten je Stunde und je Tag (PER-029) und je Stunde ab der
  Stundengrenze (PER-035)
- PersonFunktion: Person, Funktion, Stundensatz, Tagessatz, gültig ab – alle
  drei freiwillig, ohne Datum gilt die Zeile immer (PER-029); Kostensatz ab
  der Stundengrenze (PER-035)
- Abwesenheit: Person, Zeitraum, Art
- Verfügbarkeit: Person, Zeitraum, Farbe, Notiz, Herkunft (eigener Eintrag
  oder Termin eines verknüpften Kalenders, dann mit diesem Kalender),
  Zeitpunkt der Angabe, Serie
- Verknüpfter Kalender: Person, ICS-Link, Name, verknüpft am, zuletzt
  gelesen, Problem, Zahl der Fehlversuche; höchstens zehn je Person, jeder
  Link einmal (PER-031)
- Verfügbarkeitsserie: Person, Farbe, Notiz, erster Termin (Tage und
  Uhrzeiten), Wiederholung (täglich, wöchentlich an Wochentagen, monatlich),
  Abstand, Ende (Datum oder Anzahl)
- Qualifikationsart: Bezeichnung, Beschreibung, übliche Gültigkeit in Monaten
- Qualifikation: Person, Art, Angabe (z. B. Klassen), erworben am, gültig
  bis, Nachweis (Datei)
- Spesenposten (ZEI-019): Person, Projekt, Art (Verpflegung,
  Fahrt, Übernachtung, Parken/Maut, Sonstiges), Datum, Betrag, bei einer
  Fahrt Kilometer und Satz, Notiz, Foto des Belegs, Status der Freigabe,
  erstattet, bei einer Fahrt der abgezogene Arbeitsweg, damit die
  Spese ihre Rechnung zeigt (ZEI-027)

Projekte
- Projekt: Projektnummer, frühere Projektnummer (nicht änderbar; die Nummer
  vor der letzten Umnummerierung, meist die mit "P-", ADM-012,
  ADM-014), Name, Kunde, Ansprechpartner, Veranstaltungsort, Rechnungs- und
  Lieferadresse, Projektleitung, Status, Beginn, Ende, Notizen, übergeordnetes
  Projekt (Gesamtprojekt eines Teilprojekts, eine Ebene), Wiedervorlage mit
  Datum, Notiz und für wen (PRJ-105), mit freiwilliger Uhrzeit
  (PRJ-109); die Art (Projekt oder
  Servicefall) und beim Servicefall Beschreibung, Status (offen, in Arbeit,
  erledigt) und verantwortliche Person (PRJ-090); auch die Status
  wartet (mit dem Grund Rückmeldung, Aktion oder Materiallieferung), wartet
  auf Schließen und Rückstand (PRJ-112); je änderbarem Feld der
  Zeitpunkt seiner letzten Änderung (PRJ-113), beim Servicefall auch der des
  Status (PRJ-114), gespeichert als ein Feld mit einem Zeitpunkt je Name
  der API
- Beteiligter eines Servicefalls (PRJ-108): Servicefall, Person,
  Funktion (freiwillig), Notiz; keine Personalposition, ohne Prüfung der
  Verfügbarkeit, ohne Einsatzanfrage und ohne Kosten
- Projektphase: Projekt, Art (Planungen und Besprechungen, Packen, Anfahrt,
  Aufbau, Probe, Veranstaltung, Abbau, Rückfahrt, Nachbereitung, Reinigung,
  Sonstiges; PRJ-006), Bezeichnung, Zeitraum, Veranstaltungsort oder freier
  Ort, Notiz
- Projektvorlage: Name, Beschreibung, Nummer des Projekts, aus dem sie
  entstand, angelegt von und am, Inhalt (Teilgruppen, Positionen,
  Personalplätze, Phasen, offene Punkte, Notizen; Zeiten relativ zum Beginn
  des Projekts, mit "anchor": "end" zu seinem Ende, PRJ-076)
- Projektdatei: Projekt, Unterlagenart, Titel, Datei, für die Crew sichtbar,
  Herkunft (Mailanhang), hochgeladen von und am; bei einem Showfile Pult bzw. Software, Version und "aktuell" (PRJ-089)
- Unterlagenart: Bezeichnung, für die Crew sichtbar (Voreinstellung)
- Dokument eines Lieferanten (PRJ-106): Projekt, Lieferant, Art (Angebot,
  Auftragsbestätigung, Lieferschein, Rechnung, Sonstiges), Datei; erscheint
  auch bei den Dateien des Projekts
- Fahrt (PRJ-097): Projekt, Phase, Start, Ziel, Zwischenziele,
  Routenlink zu Google Maps; ermittelt aus Phasen und Adressen, ohne
  Entfernung
- Anpassung einer Fahrt (PRJ-111): Projekt, die ermittelte
  Fahrt, auf die sie sich bezieht (leer bei einer eigenen Fahrt), entfernt
  ja/nein, geänderte Angaben (Start, Ziel, Zwischenziele, Zeit, Notiz);
  ohne Anpassung gilt die ermittelte Fahrt, "Zurücksetzen" löscht die
  Anpassungen des Projekts
- Chatnachricht (UIX-010): Projekt, Verfasser, Zeitpunkt, Text,
  geändert am, erwähnte Personen; je Nutzer, bis wohin gelesen ist
- Offener Punkt: Projekt, Text, erledigt (für "Bestätigt – Einzelheiten offen")
- Aufpreisbezug: Aufpreisposition, Ziel (Position, Teilgruppe, Personal oder
  Projekt); mehrere Ziele je Aufpreis möglich
- Teilgruppe: Projekt, Bezeichnung, Beschreibung, Obergruppe, Reihenfolge,
  Rabatt, Pauschalpreis, Kennzeichen optional/Alternative, bei einer
  Alternative die Teilgruppe, die sie ersetzen könnte (PRJ-083)
- Materialposition: Projekt, Teilgruppe (optional), Produkt, Menge, Beginn,
  Ende, Miettage, Staffelfaktor, Miete oder Verkauf, Einzelpreis, Rabatt,
  Reihenfolge, Notiz, Nachtrag beim Packen; bei Zumietung zusätzlich
  Lieferant, Einkaufspreis, Status (voreingestellt "offen",
  PRJ-101), "wird beim Lieferanten abgeholt" (PRJ-097) und die
  Position, deren Fehlmenge gedeckt wird; bei einer
  Übernahme die Position eines anderen Teilprojekts, deren Stücke sie
  übernimmt (PRJ-060); bei einer Alternative die Position, die sie
  ersetzen könnte (PRJ-083). Kundenmaterial ist eine Position, deren Produkt
  einen Eigentümer hat (PRJ-096); ein eigenes Feld gibt es dafür nicht
- Packliste: Projekt, Titel, Hinweis, Status (offen, in Arbeit, gepackt,
  teilweise ausgegeben, ausgegeben, zurück), Stand der Positionen bei
  Packbeginn; die erste Packliste eines Projekts nimmt alle Positionen auf,
  die keiner anderen zugeordnet sind
- Zeile einer Packliste: Packliste, Position, Produkt, Stand bei Packbeginn
  (PCK-015), gepackt, ausgegeben, als zurück abgehakt, zurückgenommen mit dem
  Zeitpunkt der letzten Buchung (PCK-028), an ein anderes Teilprojekt
  übergeben (PRJ-060), Fehlteile geklärt mit Notiz (PCK-019), Zeitpunkt der
  letzten Änderung der gepackten und der zurück abgehakten Menge (PCK-027);
  eine Versionsnummer, die mit jeder Änderung der Zeile steigt,
  und die Änderungs-IDs der App, die schon angewandt sind, damit eine
  Wiederholung nichts doppelt ändert (PCK-027)
- Materialzuteilung: Materialposition, Instanz, Menge, ausgegeben am, zurück
  am, Zustand bei Rückgabe; vor der Ausgabe auch als freiwillige Wahl eines
  Exemplars (PCK-022)
- Übergabe zwischen Teilprojekten: Packliste des übernehmenden Teilprojekts,
  Position, von der übernommen wird, Menge, gebucht von und am (PRJ-060)
- Personalposition: Projekt, Phase (optional, PRJ-080), Funktion, Person
  (optional), Beginn, Ende, Stundensatz und Tagessatz oder Pauschale, geplante
  Stunden, Tage (bei Abrechnung je Tag; leer: die Kalendertage des Zeitraums),
  Rückmeldestatus mit angefragt am, beantwortet am, Anmerkung und den
  angefragten Zeiten (PER-033), geleistete Stunden, Abrechnungsweise (Plan,
  pauschal, Aufwand, je Tag; voreingestellt Aufwand, PER-036),
  Dienstleistungsprodukt, Verkaufspreis (ohne Teilgruppe, PRJ-038),
  Stundengrenze mit Preis und Kostensatz ab der Grenze (PER-035); die Zuschläge für Preis und Kosten getrennt ausgewiesen (PER-009)
- Zeiteintrag: Person, Projekt (bis zur Freigabe optional), Funktion, Beginn,
  Ende, Pause, Stundensatz, Status, Notiz; die API nennt die Art
  der Bezahlung und ob er im Tagessatz liegt, berechnet wie unter "Meine
  Zeiten", nicht gespeichert (API-016)
- Anteil eines Zeitraums (ZEI-025): ein erfasster Zeitraum
  (Beginn, Ende, Pause) in Anteilen, je Anteil Funktion, Personalposition,
  Stunden und Satz. Jeder Anteil zählt in Summen, Auswertungen,
  Freigabelisten, Exporten und Kosten wie ein Zeiteintrag; wie die Anteile
  gespeichert sind, legt der Bau fest (etwa als Zeiteinträge eines Zeitraums
  mit gemeinsamem Schlüssel und dessen Zeiten). Ein Eintrag ohne Anteile
  bleibt ein Zeiteintrag

Dokumente
- Dokumentvorlage je Dokumentart: Überschrift, Einleitung, Schluss,
  Fußzeile, Logo ja/nein; Texte mit Platzhaltern; beim Angebot die
  Gültigkeit in Tagen (DOK-013)
- Textbaustein: Bezeichnung, Text, Dokumentarten, aktiv
- Dokument: Projekt, Art (Angebot, Auftragsbestätigung, Lieferschein,
  Rechnung, Stornorechnung, Crew-Disposition), Nummer, Datum, Inhalt
  (festgeschrieben), Umfang (beim Angebot mit Positionen oder nur
  Teilgruppen, DOK-013), netto, brutto, fällig am, PDF mit Prüfsumme,
  XRechnung, storniert durch, storniert, gesendet am und an; nach dem
  Erstellen unveränderlich
- Die Einsatzübersicht (PRJ-081) wird bei jedem Abruf erzeugt; sie wird
  nicht abgelegt und hat keine Nummer
- Buchhaltung: Zugang zu Lexware Office (Schlüssel verschlüsselt),
  Übergabe automatisch oder von Hand, Sammelkunde, Buchungskategorie je
  Steuersatz; DATEV-Angaben (Berater, Mandant, Wirtschaftsjahr,
  Kontenrahmen, Erlöskonten, Debitorenkonten); Übergabe je Dokument mit
  Status und Beleg-ID (DOK-011, DOK-012)

E-Mail
- Postfach (mehrere, EML-041): Name, Adresse, aktiv, Aufgaben
  (Korrespondenz, Postausgang der Korrespondenz, Systemmails), Serverdaten
  für Abruf und Versand, Zugangsdaten (verschlüsselt), Ordner des
  Posteingangs, Mails ohne Projektkennung übernehmen, Verhalten nach der
  Zuordnung (in einen Ordner verschieben, löschen, unverändert lassen; auch nur als gelesen markieren, EML-006),
  Stand des Abrufs (letzter erfolgreicher Abruf, letzter Fehler); für Mails ohne Projektkennung "ab" (Zeitpunkt) und "nur ungelesene"
  (EML-049)
- Adresse eines Postfachs (EML-047): Postfach, Adresse (Alias),
  Umgang mit Mails ohne Projektkennung (nicht übernehmen, als Anfrage, gleich
  als Servicefall anlegen), Rolle "nur für Servicefälle"; "ab"
  (Zeitpunkt) und "nur ungelesene" (EML-049)
- Regeln für alle Postfächer: Abrufabstand, größte Mail, Aufbewahrung,
  Absendername, Signatur, Antwort auf Einsatzanfragen (Link, Antwort-Mail
  oder beides, PER-032; in der Oberfläche unter Firmendaten und
  Grundeinstellungen, ADM-015)
- E-Mail: Postfach (leer, wenn es gelöscht ist) und sein Name (EML-046),
  Projekt, Richtung, Message-ID,
  Bezug (Antwort auf), Absender, Empfänger, Betreff, Text, Zeitpunkt, Art der
  Zuordnung (Kürzel, Bezug, von Hand), Status; Anhänge über das Objekt Anhang
- Wartende Mail (Anfragen, EML-042): Postfach, Message-ID, Absender, Betreff,
  Datum, Kürzel (leer bei einer Mail ohne Kennung), gefunden am, erledigt am
- Einsatzanfrage per Mail (PER-032): Code (zufällig, eindeutig),
  Personalposition, Person, angefragt am, angelegt am, beantwortet am
- Eintrag im Mail-Protokoll (EML-039): Zeitpunkt, Absender, Empfänger,
  Betreff, Projekt, Ergebnis, Postfach (leer, wenn es gelöscht ist) und sein
  Name (EML-046); das Ergebnis "nicht versendet – kein
  Mailserver eingerichtet" (EML-048)
- Zusammenfassung der Korrespondenz (EML-040): Projekt bzw.
  Servicefall, Text, Sprache, Modell, erzeugt am und von, die neueste
  erfasste Mail (daraus "veraltet"); als von einer KI erzeugt
  gekennzeichnet. Die Kurzübersicht ohne KI wird berechnet [A]

System
- Nutzer, Rolle, Recht, Projektmitgliedschaft (Einsatzsicht, Lesen oder
  Bearbeiten; in einem Teilprojekt auch "kein Zugriff"), API-Token; am
  Nutzer die Sprache der Oberfläche (UIX-029)
- Webhook: Adresse, Ereignisse, aktiv, Geheimnis (verschlüsselt),
  Beschreibung; Zustellung: Ereignis, Inhalt, Versuche, Status, nächster
  Versuch, zugestellt am (API-012)
- Anhang (an beliebigem Objekt), Änderungsprotokoll, Nummernkreis, Einstellung
  (darunter "Bei geänderten Zeiten neu anfragen", PER-034; die Zuschläge mit Prozentsätzen für Preis und Kosten, Zeitfenster der
  Nacht und Bundesland, PER-009; "Rentalars als Buchhaltungsprogramm verwenden",
  DOK-014; Karten sofort laden, UIX-034; Adresse des Lagers, PRJ-097; die
  Grenzen der Hinweise auf Zeiten, ZEI-018; Satz je Kilometer, ZEI-019;
  "Hinweise zu Arbeitszeiten anzeigen", ZEI-018, und der Abzug
  des Arbeitswegs, ZEI-027; die Sprache der Dokumente, UIX-029,
  und "Zusammenfassungen mit lokaler KI" mit der Adresse der lokalen KI,
  EML-040; unter Benachrichtigungen die Meldung der Fehlbestände
  mit Uhrzeit, Abstand – täglich, an Werktagen, wöchentlich mit Wochentag,
  nie –, Vorlauf in Wochen und "erneut melden", dazu, nur von der Prüfung
  geschrieben, letzte Prüfung und Zahl der Meldungen, VFG-036)
- Vorbereitete Adressänderung (ADM-016): neuer Rechnername,
  Art des Zertifikats, E-Mail-Adresse für Let's Encrypt bzw. eigenes
  Zertifikat und Schlüssel (geschützt wie andere Geheimnisse), Ergebnis der
  Prüfungen, vorbereitet von und am, der angezeigte Befehl, angewendet am
  und von bzw. der Fehler
- KI-Anbieter (ADM-017): Art (lokale KI des Betreibers oder
  OpenAI-kompatible Schnittstelle), Adresse, Modell, API-Schlüssel
  (verschlüsselt), Zeitlimit; je Verwendung (Zusammenfassung,
  Antwortentwurf für Mails, später Vorlagenvorschläge) eingeschaltet ja/nein
  und der Anbieter; das Zeitlimit gilt für Stille, nicht für die
  ganze Antwort (ADM-017), und zur lokalen KI gehören das Modell, die
  gemessene Geschwindigkeit beim Lesen und beim Schreiben (Tokens je
  Sekunde) mit dem Zeitpunkt der Messung, das Ergebnis der Prüfung des
  Prozessors (AVX2, FMA) und die Empfehlung eines Modells (EML-040)
- KI-Aufruf (ADM-017): Zeitpunkt, Verwendung, Anbieter, Modell,
  Dauer, Größe, Ergebnis; nie der Inhalt
- Zuschlagsregel (PER-040): Art (Tageszeit, Wochentag,
  Feiertag, bestimmter Tag im Jahr ab einer Uhrzeit), dazu je nach Art das
  Zeitfenster, die Wochentage oder Tag und Uhrzeit, Prozentsatz für den
  Preis, Prozentsatz für die Kosten, Reihenfolge; dazu die Bundesländer der
  Feiertage
- Eigener Feiertag (PER-040): festes Datum jedes Jahr, einzelnes
  Datum oder Tage relativ zum Ostersonntag
- Automation (ADM-013): Name, aktiv, Auslöser mit Bedingung,
  Aktion mit Text bzw. Person; Lauf: Automation, Zeitpunkt, Anlass,
  Ergebnis (auch ausgelassen, mit Grund); der Auslöser "Neue
  Kommunikation im Servicefall", die Bedingung auf den Status des Falls und
  die Aktion "Status des Servicefalls setzen" mit dem neuen Status (ADM-013)
- Benachrichtigung: Nutzer, Art (auch die fällige Wiedervorlage,
  PRJ-105; die Erwähnung im Chat, UIX-010), Titel, Text, Link,
  Projekt, gelesen am; Einstellung je Nutzer und Art (in der Anwendung, per
  E-Mail, in der App, UIX-039); die Kategorie einer Art legt der
  Code fest, gespeichert wird sie nicht (UIX-039)
- Je Nutzer, ob der Hinweis auf die Begleit-App unter "Meine
  Zeiten" weggeklickt ist (ZEI-024), dort, wo Rentalars andere Wahlen der
  Oberfläche je Nutzer speichert
- Sitzung: Nutzer, Browser, Adresse, angemeldet am, zuletzt aktiv;
  Sicherheitsereignis: Art, Nutzer, eingegebener Name, Adresse, Zeitpunkt
- Zwei-Faktor-Anmeldung am Nutzer: Schlüssel (verschlüsselt), eingerichtet
  am, Wiederherstellungscodes (nur als Hash)
- Fehler der Anwendung: Stelle, Meldung, Anzahl, zuerst, zuletzt, gemeldet
- Aufgabe im Hintergrund: Art, Titel, Status, Fortschritt, Meldung,
  Ergebnisdatei, Ergebnis (z. B. Bericht eines Imports), gestartet von
- Spaltenwahl: Nutzer, Liste, gezeigte Spalten
- API-Schutz: Aufrufe je Token und Minute; Antworten auf Aufrufe mit
  Idempotency-Key (einen Tag), gebunden an den Aufrufer (Nutzer
  bzw. Token) und die Anfrage (Methode, Pfad, Prüfsumme des Inhalts,
  API-010)

Weitere Angaben
- Projekt: Stand der Rechnung (offen, "Rechnung gestellt", "keine
  Rechnung", DOK-015); die Defektmeldung, aus der ein Servicefall entstand
  (MAT-057); "intern" auch für Servicefälle (PRJ-090)
- Materialinstanz: Preis enthalten in (Materialinstanz, MAT-054)
- Etiketten-Einstellungen (einmal für den Betrieb, MAT-056): Name neben dem
  Logo, Name auf dem Kabeletikett, Logo für Etiketten, Telefonnummer mit
  den Worten davor, Worte vor der ID, gedruckte Webadresse, Text um das
  Kabel, Text für Finder, Ziel des QR-Codes mit {id}, vorgeschlagenes
  Etikett, Länge des Kabeletiketts
- Einstellung der Benachrichtigungen (VFG-036) um die Erinnerung an
  Rechnungen: an/aus, Uhrzeit, erste Erinnerung nach Tagen, danach alle
  Tage, weitere Person, auch Servicefälle; Buchhaltung der Prüfung (seit
  wann, letzter Lauf, letzte Prüfung, Zahl der Erinnerungen), die nur die
  Prüfung schreibt (DOK-015)
- Erinnerung an die Rechnung: Projekt, erste und letzte Erinnerung, Anzahl
  (DOK-015)
- E-Mail eines Projekts: Richtung auch "Notiz" – ohne Adressen und
  Message-ID, mit Verfasser und Zeitpunkt (EML-051)
- Anfrage (wartende Mail): Defektmeldung, aus der eine Automation sie machte
  (MAT-057)
- Automation: Auslöser "Ein Defekt wird gemeldet", Aktionen "Servicefall
  anlegen" und "unter Projekte → Anfragen stellen" (ADM-013, MAT-057)

Stufe 9 – Logistik
- Produkt der Art "Fahrzeug" (LOG-002, LOG-005, LOG-006, LOG-010):
  Fahrzeugart (KFZ oder Anhänger), Preis je Kilometer, beim KFZ
  Anhängerzuschlag je Kilometer, beim Anhänger der Preis je Tag (der Preis
  des Produkts, mit Staffel) und wie neue Buchungen abgerechnet werden (je
  Tag oder je Kilometer); interne Kosten je Kilometer und – beim Anhänger –
  je Tag
- Fahrzeugdaten am Exemplar (LOG-002, LOG-003, LOG-012, LOG-013):
  Kennzeichen (eindeutig, wenn angegeben), beim KFZ Sitzplätze min. und
  max. und Anhängelast (0: darf nicht ziehen), Führerscheinklasse (beim
  Anhänger die des Gespanns), zulässiges Gesamtgewicht
- Fahrzeugbuchung (LOG-001): Projekt, Produkt, Exemplar (leer: noch offen
  oder zugemietet), Bezeichnung, Phase, Von, Bis, Notiz; Abrechnung (beim
  KFZ je Kilometer, beim Anhänger je Tag oder je Kilometer), Preis je
  Kilometer, Anhängerzuschlag je Kilometer, Preis je Tag, Miettage (leer:
  wie Material), "nur Tage mit Fahrten", Staffel (Stand bei der Anlage),
  Rabatt, Steuersatz; interne Kosten je Kilometer und je Tag; Lieferant und
  was er berechnet
- Fahrteinsatz (LOG-006, LOG-007): Projekt, Fahrt (Schlüssel wie bei der
  Anpassung einer Fahrt, PRJ-111), Zugfahrzeug, Anhänger (optional),
  Kilometer geplant und gefahren, berechnet (gefahrene, geplante,
  pauschal), Pauschale, Notiz
- Personalposition: Fahrzeugbuchung und "Fahrer" (LOG-008); Packliste:
  Fahrzeugbuchung (LOG-011); Qualifikationsart: Führerscheinklassen
  (LOG-012)

Stufe 9 – Weitere Anforderungen
- Postfach und Alias: Rollen, für die die Adresse als Absender wählbar ist
  (EML-052); Postfach: eigene Signatur (EML-026)
- Anfrage: Herkunft (Mail oder von Hand), Name, E-Mail-Adresse, Telefon,
  Kunde, Notiz, notiert von (EML-053)
- Monatsabrechnung (DOK-016): Kunde, Monat, Status (Entwurf, abgerechnet,
  als abgerechnet markiert), Servicefälle, Inhalt (je Fall Tätigkeit und
  Positionen, eigene Positionen), Rechnung; Dokument: weitere abgerechnete
  Projekte

Stufe 9 – Weitere Anforderungen
- Produkt: genau ein Preis – der Verkaufspreis eines Verkaufsprodukts, der
  Preis jedes anderen (PRD-047)
- Personalposition: Status der Anfrage auch "fest eingeplant" (PER-041)
- Rolle: Projektzugriff auch "nur zugeordnete Projekte, Überblick ohne
  Planung" (AUT-031); Sonderrecht "Verfügbarkeit von Material sehen"
  (AUT-032)
- Benachrichtigungen der Firma: Erinnerung an Zeiten zur Freigabe – an
  oder aus, Uhrzeit, erste nach Tagen, danach alle Tage, letzter Lauf
  (ZEI-029); Arten "Änderung meines Einsatzes" (PRJ-118) und "Meine Zeiten
  freigegeben, korrigiert oder zurückgegeben" (ZEI-031)
- KI-Einstellungen: Verwendung "Rechnungen lesen" mit Quelle und Anbieter;
  im Protokoll der KI-Aufrufe die Verwendung "invoice" (MAT-062)
- Ein Kauf (MAT-061) ist kein eigenes Objekt: Händler, Rechnungsnummer,
  Rechnungsdatum und Kaufpreis stehen an jedem Exemplar, die Rechnung als
  Datei der Art "Rechnung" an jedem

Stufe 9 – Weitere Anforderungen
- Audit: Exemplar, Zeitpunkt, wer, Ergebnis (in Ordnung oder mit To-Dos);
  To-Do: Exemplar, Text, notiert von und am, erledigt von und am, aus
  welchem Audit; Einstellungen: Audit-Intervall in Monaten, Schnellauswahl
  (MAT-067 bis MAT-069)
- Eigenes Feld: Name, Typ, Auswahlwerte, Einheit, Prüfmuster, Hilfetext, in
  Listen, eindeutig, vertraulich; Feldsatz: Name, Felder in Reihenfolge, je
  Pflicht oder freiwillig; Materialmodell: Feldsatz; Wert je Exemplar und
  Feld, ein vertraulicher getrennt gespeichert (MAT-071 bis MAT-073)
- Anhang einer Chatnachricht: Foto oder Video, verkleinerte Datei,
  Standbild, Zustand (wird verkleinert, fertig, misslungen), Größe, Maße,
  Dauer (UIX-049)
- Nachricht der Korrespondenz: mit Schloss; Mail-Einstellungen: neue
  Nachrichten mit Schloss in Projekten, in Servicefällen (EML-055)
- Verwandtschaft: zwei Projekte oder Servicefälle, Notiz, angelegt von und
  am (PRJ-119)
- Listeneinstellung je Nutzer und Liste: Einträge je Seite (UIX-050)

Stufe 9 – Weitere Anforderungen
- Materialmodell: Schutzklasse; Exemplar: eigene Schutzklasse (MAT-077)
- Prüfart: elektrische Prüfung ja/nein; Prüfung: Schutzklasse, Prüfgerät,
  Sichtprüfung, Leitungslänge, R_PE, R_ISO, I_PE, I_B, Funktionsprüfung
  (MAT-078)
- Kalender-Link: Produkt, Materialmodell oder Exemplar (genau eines),
  geheimer Schlüssel, erstellt von und am (VFG-040)
- Automation: fester Schlüssel einer mitgelieferten Regel (ADM-019)

Stufe 9 – Weitere Anforderungen
- Exemplar: Lagerplatz, bis 12 Zeichen, innerhalb des Lagerorts (MAT-080)
- Projekt: Gesamtrabatt in Prozent (0 bis 100) oder als Betrag in Euro, nie
  beides (PRJ-123)

Stufe 9 – Weitere Anforderungen
- Produkt: Stück je Produkt, ganze Zahl ab 1 (PRD-052)
- Ansprechpartner: Vorname, Nachname, Anrede in E-Mails mit eigener Zeile
  (KND-011)
- Positionen: Textposition (PRJ-128)
- Beleg: ohne Projekt mit Kunde und Betreff, Entwurf mit eigenen Zeilen und
  Wahl der Produktbeschreibung (DOK-021, DOK-022)

Stufe 10 – Weitere Anforderungen
- Eingangsrechnung: Lieferant, Nummer, Datum, Fälligkeit, Beträge, Notiz,
  Status, Datei, Positionen (Kontierungszeilen) mit Art (Ware, GWG, Anlagegut),
  Nutzungsdauer und Nebenkosten-Kennzeichen (DOK-023, DOK-024)
- Steuerkonto: Kontonummer (einmalig), Name, aktiv; an der Position der
  Eingangsrechnung (DOK-026)
- Exemplar: Art, Nutzungsdauer in Monaten, Nebenkosten, Anschaffungskosten,
  Herkunftsposition, Genauigkeit des Rechnungsdatums (MAT-086, MAT-088)
- Verkauf aus Bestand: Exemplar, Käufer, Datum, Nettopreis, Restbuchwert,
  Gewinn oder Verlust (MAT-087)
- Verbaute Menge: Mengenmaterial in einem Exemplar (MAT-040)
- Produkt: Zubehör und Ersatz mit Reihenfolge und Hinweis (PRD-023, VFG-015)
- Position: weitere gewünschte Exemplare (PRJ-064)
- Altimport: Stapel und Rechnungen mit Vorschlag und Herkunft (PRJ-130)
- Anmeldung: Verzeichnis-Einstellungen, Gruppen-Rollen-Zuordnung, Herkunft
  der Rolle (AUT-029)
- Preisangebot: Einstellungen, Angebote und Verhandlungsschritte (PER-038)
- KI: Einstellungen und Läufe der automatischen Zusammenfassung, Fassungen
  (EML-056)

Stufe 10 – Weitere Anforderungen
- Beleg: Art der Rechnung (Abschlag, Teil, Schluss, Gutschrift), Nummer innerhalb
  der Art, Bezug auf die gutgeschriebene Rechnung, Abzüge im Inhalt
  (DOK-030 bis DOK-036)
- Eingangsrechnung: XML-Datei und Format der E-Rechnung (DOK-040)
- Verkauf aus Bestand: Entwurf der Rechnung, bis sie ausgestellt ist (DOK-037)

### 7.3 Regeln im Datenmodell

- Preise und Stundensätze werden beim Zuordnen in die Position kopiert
  (Festschreibung); spätere Stammdatenänderungen wirken nicht zurück.
- Gelöscht wird fachlich nie hart, wenn Abhängigkeiten bestehen; stattdessen
  Deaktivierung bzw. Archivierung.
- Eine Instanz darf sich nicht in zwei zeitlich überlappenden Zuteilungen
  befinden.
- Eine Instanz kann weder in sich selbst noch im Kreis verbaut sein.
- Das Kürzel einer Kategorie ist unveränderlich, sobald Artikelnummern dazu
  bestehen.
- Übernommen werden nur zugeordnete E-Mails; jede gehört zu genau einem
  Projekt, ihre Message-ID ist systemweit eindeutig.
- Lose enthaltene Exemplare gelten als mit verplant, solange ihr umgebendes
  Gerät verplant ist und sie nicht herausgelöst wurden.
- Ein erstelltes Dokument wird nie geändert oder gelöscht; je Projekt gilt
  höchstens eine nicht stornierte Rechnung.
- Reserviert wird nur der Teil einer Position, der aus eigenem Bestand kommt.
- Höchstens ein Postfach versendet die Korrespondenz – eines der aktiven
  Postfächer der Korrespondenz – und höchstens eines die Systemmails; wer
  einem Postfach eine dieser Aufgaben gibt, nimmt sie dem bisherigen. Ein
  Postfach, über das Mails kamen oder gingen, lässt sich löschen, und Mails und
  Mail-Protokoll behalten seinen Namen (EML-046).
- Funktion und Dienstleistungsprodukt gehören 1:1 zusammen. Eine neue
  Materialposition hat nie ein Dienstleistungsprodukt (PRD-044).
- Eine Zumietung hat einen anderen Status als "offen" nur mit Lieferant
  (PRJ-101).
- Höchstens ein Lagerort ist die Voreinstellung für neue Exemplare (MAT-052).
- Die Stundengrenze zählt je Kalendertag und nur bei Abrechnung nach Stunden
  (PER-035).
- Zuschläge gelten ausdrücklich nur für Personalpositionen (PER-009) und nur bei Abrechnung nach Stunden; der Nachtzuschlag kommt
  zu Sonn- oder Feiertag hinzu, von Sonntag und Feiertag zählt der höhere
  (PER-009). Allgemein: Von den Regeln, die einen Tag betreffen
  (Wochentag, Feiertag, bestimmter Tag ab einer Uhrzeit), zählt die höchste;
  die Regeln der Tageszeit kommen hinzu (PER-040).
- Die Anteile eines Zeitraums ergeben zusammen seine gearbeiteten Stunden;
  Zuschläge verteilen sich nach den Stunden auf sie. Überschneidung,
  Hinweise und Stoppuhr gelten für den Zeitraum einmal, Freigeben und
  Ablehnen für den ganzen Zeitraum (ZEI-025).
- Der Arbeitsweg wird je Person, Projekt und Tag einmal abgezogen, hin und
  zurück; ohne Entfernung an der Person nichts (ZEI-027).
- Ein Beteiligter eines Servicefalls ist keine Personalposition: keine
  Verfügbarkeitsprüfung, keine Einsatzanfrage, keine Kosten (PRJ-108).
- Die Adresse, an die eine Mail ging, kommt aus Delivered-To, X-Original-To,
  To und Cc in dieser Reihenfolge; die eigene Adresse eines Postfachs folgt
  seiner Einstellung, außer sie steht selbst in der Liste
  (EML-047).
- Ohne Server für den Versand und ohne Postfach der Systemmails zählt eine
  Mail nicht als gesendet (EML-048).
- Ein Servicefall nimmt seine Nummer aus dem Nummernkreis der Projekte und
  zählt nicht in Verfügbarkeit, Kalender, Zeitstrahl und Fehlbeständen
  (PRJ-090).
- Eine Automation antwortet nie auf eine als automatisch gekennzeichnete
  Mail und je Absender und Regel höchstens einmal am Tag (ADM-013).
- Eine Alternative verweist auf eine Position bzw. Teilgruppe desselben
  Projekts, die selbst keine Alternative ist; eine Teilgruppe nicht auf eine
  über oder unter ihr. Fällt das Ziel weg, wird die Alternative optional.
- Je Person und Funktion gibt es höchstens eine Zeile der Sätze ohne Datum.
- Ein Produkt hat genau dann einen Eigentümer, wenn seine Kategorie als
  Kundenmaterial markiert ist; es hat dann keinen Preis und steht nur in
  Projekten seines Eigentümers und deren Teilprojekten. Die Markierung einer
  Kategorie mit Produkten und der Eigentümer eines eingeplanten Produkts
  bleiben, wie sie sind; ein Kunde mit Material im Lager wird nicht gelöscht.
- Eine neue Projektnummer ist nie die frühere Nummer eines anderen Projekts.
  Passt eine Nummer zu einem Projekt als heutige und zu einem anderen als
  frühere, ist das erste gemeint; Groß- und Kleinschreibung zählt nicht
  (ADM-012, ADM-014). Eine frühere Nummer hat keine Buchstaben außer einem
  "P-" am Anfang.
- Je Zeile einer Packliste gilt: gepackt ≥ ausgegeben ≥ als zurück abgehakt ≥
  zurückgenommen. Zurückgenommene Stücke werden im selben Projekt nicht wieder
  ausgegeben. Die Zeit der letzten Änderung einer abgehakten Menge ändert sich
  nur, wenn sich die Menge ändert (PCK-027, PCK-028).
- Die Version einer Zeile der Packliste steigt mit jeder
  Änderung, auf welchem Weg auch immer. Eine Änderung der App mit
  base_version gilt nur, wenn die Zeile noch diese Version hat, sonst ist sie
  ein Konflikt; eine Änderungs-ID wirkt nur einmal. Ohne base_version gilt
  die jüngere Änderung nach der Regel für die Uhren; eine ältere
  überschreibt nie eine jüngere (PCK-027).
- Eine gespeicherte Antwort auf einen Aufruf mit
  Idempotency-Key bekommt nur derselbe Aufrufer mit derselben Anfrage, nach
  Prüfung seiner aktuellen Rechte. Versionsprüfung und Speichern geschehen
  in einem Schritt (API-010).
- Eine Mail ohne Projektkennung wird nur übernommen, wenn sie
  nach dem Zeitpunkt "ab" ihres Postfachs bzw. ihrer Adresse einging – bei
  "nur ungelesene" zudem nur ungelesen (EML-049).
- Eine entfernte ermittelte Fahrt bleibt entfernt, auch wenn
  Rentalars die Fahrten eines Projekts neu ermittelt; eine geänderte behält
  ihre Änderungen (PRJ-111).
- Ein Servicefall in "wartet", "wartet auf Schließen" oder
  "Rückstand" hat eine Wiedervorlage, bei "wartet auf Schließen" mit
  Uhrzeit. Ein Fall im "Rückstand" steht vor ihrer Fälligkeit nur in der
  Liste der Servicefälle (PRJ-112).
- Mailinhalte gehen an eine KI nur über den Anbieter, der für
  die Verwendung gewählt und eingeschaltet ist; das Protokoll der Aufrufe
  enthält nie Inhalte (EML-040, ADM-017).
- Eine vorbereitete Adressänderung ändert nichts, bis der
  Befehl auf dem Server sie anwendet; er prüft sie selbst noch einmal und
  stellt bei einem Fehler den alten Stand wieder her (ADM-016).
- Jede Änderung eines Feldes eines Projekts setzt seine
  Änderungszeit, auf welchem Weg auch immer. Eine Änderung mit changed_at
  gilt je Feld nur, wenn ihr Zeitpunkt später liegt als der gespeicherte;
  bei Gleichstand gilt der Server, ein Zeitpunkt in der Zukunft zählt als
  jetzt; Vergleich und Schreiben geschehen gesperrt in einem Schritt. Das
  gilt ebenso für den Status eines Servicefalls und die eigenen
  Personaldaten (PRJ-113, PRJ-114, API-015).
- Neue Fehlbestände werden nur im eingestellten Vorlauf
  gemeldet, zur eingestellten Uhrzeit und im eingestellten Abstand, je Fall
  einmal, außer "erneut melden" ist an. Eine Prüfung gilt je geplantem
  Zeitpunkt nur einmal, auch wenn zwei Läufe sie zugleich beginnen
  (VFG-036).
- Material beim Packen nachtragen darf nur, wer das Projekt
  bearbeiten darf oder Packen und Ausgabe für alle Projekte bearbeiten
  darf; abgehakt wird nie mehr, als die Packliste nennt (PCK-013).
- Ein abgeschlossenes ganzes Projekt mit Kunde, nicht intern,
  gilt als abgerechnet, sobald es eine nicht stornierte Rechnung hat oder
  "Rechnung gestellt" angehakt ist; "keine Rechnung" beendet die
  Erinnerungen ebenso. Erinnert wird nur an Projekte, die nach dem Update
  abgeschlossen wurden und netto über 0 kosten (DOK-015).
- Ein Exemplar, dessen Preis in dem eines anderen enthalten ist,
  hat keinen eigenen; das andere hat einen und verweist selbst auf keines
  (MAT-054).
- Aus einer Defektmeldung entsteht höchstens ein Servicefall;
  ein Eintrag unter Anfragen, der eine Defektmeldung ist, wird nie
  "übernommen" und nie ein Projekt (MAT-057).
- Eine Notiz der Korrespondenz liegt nie in der Zukunft; sie
  ist keine neue Kommunikation für die Automationen (EML-051).
- Stufe 9: Sitzplätze min. ≤ max., beide positive ganze Zahlen (LOG-003);
  der Anhängerzuschlag gilt nur auf Fahrten mit zugeordnetem Anhänger
  (LOG-006); Buchungen eines Fahrzeugs überschneiden sich nicht unbemerkt
  (LOG-004).
- Ein Produkt der Art "Fahrzeug" ist nie eine
  Materialposition, nie Teil eines Sets und wird nicht gepackt; ein KFZ
  braucht seinen Preis je Kilometer und hat keinen Preis je Tag; ein
  Anhänger braucht den Preis seiner Abrechnungsart. Ein gebuchtes
  Fahrzeugprodukt bleibt Fahrzeug seiner Art (LOG-002, LOG-005).
- Das Exemplar einer Buchung gehört zu ihrem Produkt; ein
  eigenes Fahrzeug hat keinen Lieferanten. Ein Fahrteinsatz hat ein KFZ
  des Projekts als Zugfahrzeug, höchstens einen Anhänger des Projekts,
  ein Fahrzeug fährt eine Fahrt einmal, ein Anhänger hängt auf einer
  Fahrt an höchstens einem Fahrzeug; "pauschal" braucht die Pauschale
  (LOG-006, LOG-007). Eine Personalposition fährt nur in einem KFZ ihres
  Projekts; ein Fahrer fährt ein Fahrzeug (LOG-008).
- Eine Monatsabrechnung enthält nur Servicefälle ihres Kunden,
  die nicht schon selbst abgerechnet sind; je Kunde und Monat gibt es
  höchstens einen Entwurf, und jede Zeit und jede Spese wird von höchstens
  einer Monatsabrechnung abgerechnet – ein Fall über mehrere Monate also
  Monat für Monat (DOK-016).
- Ein Verkaufsprodukt hat nur den Verkaufspreis, jedes andere
  Produkt keinen; eine Position verkauft nur ein Verkaufsprodukt – außer
  sie verkaufte schon vorher ein Mietprodukt (PRD-047, PRJ-015).
- Eine fest eingeplante Position hat eine Person; sie wird
  weder angefragt noch beantwortet, und neue Zeiten setzen sie nicht
  zurück (PER-041). Der Projektzugriff "Überblick ohne Planung" ist eine
  Obergrenze über jeder Mitgliedschaft (AUT-031).
- Zwei Projekte oder Servicefälle sind höchstens einmal
  miteinander verwandt, gleich in welcher Richtung, nie mit sich selbst
  (PRJ-119). Ein Exemplar hat je eigenes Feld höchstens einen Wert, ein
  eindeutiges Feld jeden Wert höchstens einmal, ein Feldsatz jedes Feld
  höchstens einmal (MAT-071, MAT-072). Ein offenes To-Do gleichen Textes
  gibt es je Exemplar nur einmal (MAT-069).
- Die Schutzklasse eines Exemplars ist seine eigene, sonst die
  seines Modells (MAT-077). Eine Prüfung einer nicht elektrischen Prüfart
  hat keine Messwerte; "bestanden" gegen den Vorschlag der Grenzwerte hat
  eine Begründung (MAT-078). Je Produkt, Modell und Exemplar gibt es
  höchstens einen Kalender-Link, je mitgelieferter Automation höchstens eine
  Regel mit ihrem Schlüssel (VFG-040, ADM-019).
- Ein Projekt hat höchstens einen Gesamtrabatt – Prozent oder
  Betrag, nicht beide (PRJ-123). Der Lagerplatz eines Exemplars, das in einem
  anderen verbaut ist, ist der des anderen (MAT-080).
- Eine Personalposition merkt sich die Zeiten ihrer letzten Anfrage; als
  geändert zählen nur Beginn und Ende. Eine andere Person setzt die Anfrage
  zurück (PER-033, PER-034).
- Zwischensummen von Teilgruppen werden aus den Positionen berechnet und nicht
  als eigener Wert gespeichert – außer ein Pauschalpreis ist gesetzt.
- Alle projektbezogenen Abfragen (Summen, Verfügbarkeit, Rechte) sind so
  aufgebaut, dass sie später ein Projekt samt seiner Teilprojekte erfassen
  können.
- Technischer Hinweis: MariaDB kennt keine Bereichstypen mit
  Ausschluss-Constraints wie PostgreSQL. Die Überbuchungsprüfung auf
  Produktebene muss daher in der Anwendung innerhalb einer Transaktion mit
  Sperre erfolgen. Für die Überlappungsfreiheit einzelner Instanzen ist zu
  prüfen, ob MariaDBs Zeitraum-Unterstützung (Application-Time Periods,
  WITHOUT OVERLAPS) nutzbar ist.


## 8. API-Ressourcen (Entwurf)

Basis: /api/v1 – je Ressource die üblichen Operationen Liste, Einzelabruf,
Anlegen, Ändern, Löschen/Deaktivieren, soweit fachlich zulässig.

    /auth/login, /auth/logout, /auth/password-reset, /me
    /users, /roles, /permissions, /tokens

    /categories                              (für Material und Produkte)
    /manufacturers
    /suppliers
    /material-models
    /material-models/{id}/items
    /material-items
    /material-items/{id}/history
    /material-items/{id}/inspections
    /material-items/{id}/contents            (verbaute Exemplare)
    /material-items/lookup?code=...          (Scan)

    /products
    /products/{id}/materials                 (zugeordnete Modelle/Instanzen)
    /products/{id}/components                (Set-Bestandteile)
    /products/{id}/availability?from=&to=
    /availability?from=&to=&products=...     (Sammelabfrage)

    /customers
    /customers/{id}/contacts
    /customers/{id}/addresses
    /venues

    /people
    /people/{id}/job-functions               (inkl. Stunden- und Tagessätze)
    /people/{id}/absences
    /people/{id}/qualifications
    /people/availability?from=&to=&job_function=
    /job-functions

    /projects
    /projects/{id}/subprojects               (siehe unten: parent, subprojects, family)
    /projects/{id}/groups                    (Teilgruppen)
    /projects/{id}/groups/{id}/copy
    /projects/{id}/material-lines
    /projects/{id}/crew-lines
    /projects/{id}/members
    /projects/{id}/packlists
    /projects/{id}/packlists/{id}/scan       (Ausgabe / Rücknahme)
    /projects/{id}/documents
    /projects/{id}/totals
    /projects/{id}/shortages                 (Fehlmengen, Zumietvorschlag)
    /projects/{id}/price-overview            (Summen je Teilgruppe, PDF/CSV/JSON)
    /projects/{id}/history

    /time-entries
    /time-entries/timer/start, /time-entries/timer/stop
    /time-entries/approve
    /reports/hours?person=&project=&from=&to=

    Umgesetzt mit Stufe 4; die genaue Beschreibung liefert
    die API selbst (API-004):
    /projects/{id}/mails                     (Korrespondenz, Senden)
    /projects/{id}/mails/{id}/assign         (umhängen)
    /projects/{id}/mails/{id}/attachments/{id}[/to-files]
    /mail/unknown, /mail/unknown/{id}/assign (Mails mit unbekanntem Kürzel)
    /mail/fetch                              (jetzt abrufen)
    /mail/settings                           (das Projektpostfach)
    /projects/{id}/phases, /projects/{id}/open-items, /open-items
    /projects/{id}/files, /projects/{id}/files/{id}/content
    /projects/{id}/duplicate
    /projects/{id}/crew-lines/{id}/request, …/answer
    /calendar, /utilization, /personnel-plan
    /notifications, /notifications/read, /notifications/preferences
    /me/sessions, /security-log, /users/{id}/reset-two-factor

    Umgesetzt mit Stufe 5:
    /projects/{id}/packlists[/{id}[/lines|/items|/pdf|/{action}]]
    /projects/{id}/extractions               (Herauslösen, MAT-042)
    /projects/{id}/documents[/preview], /documents/{id}[/pdf|/xml|/cancel]
    /document-templates, /text-blocks
    /projects/{id}/price-overview/pdf, …/csv
    /material-items/{id}/blocks, …/defects, …/inspections, …/files,
    …/take-out, …/put-back, …/timeline; /material-items/bulk-update
    /material-models/{id}/files, …/timeline; /products/{id}/timeline
    /inspection-types, /inspections/due, /labels
    /customers/{id}/addresses, /customers/duplicates
    /qualification-types, /people/{id}/qualifications, /people/{id}/timeline
    /imports/{kind}                          (material, products, customers, people)
    /exports/full, /jobs/{id}[/result]       (Aufgaben im Hintergrund)

    Weitere Pfade:
    /project-templates                       (PRJ-076; "template" beim Anlegen eines Projekts)
    /projects/{id}/mvr                       (Lichtplot, PRJ-077)
    /projects/{id}/old-prices, /projects/{id}/material-lines/{id}/duplicate
    /people/{id}/availability-marks[/{id}|/clear], /people/{id}/calendars[/subscription|/sync|/deployments]
    /mail/signature, /mail/address-suggestions, /mail/log
    /backups, /encryption, /access-log
    /calendar, /utilization, /personnel-plan mit days=1 bis 84

    Umgesetzt mit Stufe 6:
    /projects mit parent (Teilprojekt anlegen) und subprojects, /projects?parent=
    /projects/{id}/family                    (Gesamtprojekt mit allen Teilen, PRJ-046)
    /projects/{id}/status mit with_subprojects, /projects/{id}/duplicate mit with_subprojects
    /projects/{id}/material-lines mit taken_over_from (Übernahme, PRJ-060)
    /projects/{id}/packlists/family[/pdf], …/packlists/{id}/handovers[/{id}]
    /projects/{id}/groups/{id}/move          (geschachtelte Teilgruppen, PRJ-037)
    /webhooks[/{id}/deliveries[/{id}/redeliver]|/test|/secret] (API-012)
    /documents/{id}/lexware, /accounting/settings, /accounting/lexware/check,
    /accounting/lexware/transfers, /accounting/datev/bookings, /accounting/datev/debitors

    Verfügbarkeit:
    /people/{id}/availability-periods        (die geltende Verfügbarkeit, PER-027)
    /people/{id}/availability-series[/{id}]  (Serien, PER-028)

    Postfächer und weitere Pfade:
    /mail/mailboxes[/{id}[/check]]           (Postfächer, EML-041; /mail/settings: Regeln für alle)
    /mail/unknown mit is_inquiry und mailbox (Anfragen, EML-042)
    /mail/fetch mit inquiries und mailboxes, /mail/log mit mailbox (EML-041)
    /projects/{id}/material-lines/bulk       (mehrere Positionen auf einmal, PRJ-082)
    /projects/{id}/material-lines und …/groups mit alternative_to (PRJ-083)
    /projects/{id}/shortages/accept mit status, /projects/{id}/mvr mit kept_file (PRJ-084, PRJ-086)
    /projects/{id}/crew-lines mit phase, days, billing "day", daily_rate (PRJ-080, PER-029)
    /projects/{id}/phases mit crew_lines und move_crew (PRJ-080)
    /projects/{id}/price-overview[/pdf|/csv]?crew=phases (Personal je Phase, PRJ-088)
    /projects/{id}/deployment/pdf            (Einsatzübersicht, PRJ-081)
    /projects/{id}/documents mit detail und validity_days, /document-templates mit validity_days
    /projects/{id}/packlists/{id}/issue      (only_packed voreingestellt true, PCK-025)
    /products mit max_discount_percent       (PRD-041)
    /job-functions mit guide_daily_cost_rate, /people/{id}/job-functions mit daily_rate (PER-029)
    /people/{id}/calendars/feeds[/{id}]      (mehrere Kalender, PER-031)
    /people/{id}/timeline mit der Zeile availability statt absence (PER-020)

    Projektnummern:
    /projects?number=                        (heutige oder frühere Projektnummer, ADM-012)
    /projects mit former_number (nur lesend); ?q= sucht auch darin (ADM-012)
    /projects/{id}/mails/{id}/assign, /mail/unknown/{id}/assign: project_number auch die frühere
    /projects/{id}/phases mit kind planning und aftercare; loading ist "Packen" (PRJ-092)
    /projects mit status returned: "Wieder im Lager" (PRJ-093)
    /project-templates: content mit "anchor": "end" (nur lesend; PRJ-076, PRJ-095)
    /categories mit is_customer_material, auch als Filter (PRD-043)
    /products mit owner, auch als Filter ?owner= (PRD-043)
    /projects/{id}/material-lines und …/price-overview mit is_customer_material (PRJ-096)
    /projects/{id}/shortages mit suggestion null bei Kundenmaterial (PRJ-096)
    /projects/{id}/crew-lines/{id}/request: notified auch über die Anfrage-Mail (PER-032)
    /mail/settings mit crew_answers und crew_answer_address, /mail/log?result=crew_answer (PER-032)
    /calendar: auch Projekte, von denen nur eine Phase im Zeitraum liegt (PRJ-092)
    Nur in der Oberfläche: der Dialog "Neue Phase" der Personalplanung (PRJ-094; die API
    legt Phasen mit /projects/{id}/phases an) und die Vorschläge der Produktsuche
    /products/suggest/?project=&owner= (Kundenmaterial nur beim Eigentümer, PRJ-096)

    Umgesetzt mit Ausbaustufe 7:
    /offline/packlists                       (Packlisten für das Telefon, PCK-026)
    /projects/{id}/packlists/{id}/sync       (Abgleich nach der jüngeren Änderung, PCK-027)
    /projects/{id}/packlists/{id}/take-back  (Rücknahme buchen, PCK-028); returned ist ein Haken,
      return-all hakt nur ab, complete-return bucht zuerst das Abgehakte
    /projects/{id}/packlists/{id} mit taken_back, ready_to_take_back, still_out und bar;
      je Zeile packed_changed_at, returned_changed_at; Mengen als Text (PCK-027 bis PCK-029)
    /tokens: ein auf Module beschränktes Token erstellt keine Tokens, sieht nur sich (AUT-021)
    /projects/{id}/phases mit outside_rental_period, rental_period_suggestion (PRJ-100)
    /projects/{id}/crew-lines mit request_status, requested_at, answered_at, answer_note,
      requested_start, requested_end, times_changed_since_request (PER-033)
    /projects/{id}/crew-lines/{id}/request: 400 nach Antwort für dieselben Zeiten (PER-033)
    /settings mit ask_again_on_new_times     (Bei geänderten Zeiten neu anfragen, PER-034)
    /projects?number=, former_number: die frühere Nummer ist meist die mit "P-" (ADM-014)
    /people/{id}/timeline: Einsätze mit kind "crew status-…" (VFG-027)
    /docs auch ohne Schrägstrich am Ende, ohne Weiterleitung

    Weitere Pfade; die genaue
    Beschreibung liefert die API selbst (API-004):
    /job-functions mit genau einem Dienstleistungsprodukt; legt es an, wo es fehlt (PRD-044)
    /projects/{id}/material-lines: ein Dienstleistungsprodukt wird mit Grund abgewiesen (PRD-044)
    /products mit der Produktart incidental "Nebenkosten" (PRD-045)
    /products, /job-functions, /people/{id}/job-functions mit Stundengrenze und Sätzen
      ab der Grenze; /projects/{id}/crew-lines und …/price-overview mit normalen Stunden
      und Stunden ab der Grenze (PER-035)
    /projects/{id}/crew-lines: neue Positionen nach Stunden voreingestellt "effort" (PER-036)
    /projects/{id}/material-lines und …/shortages/accept: Zumietung mit Status "offen"
      voreingestellt; ein anderer Status ohne Lieferant wird abgewiesen (PRJ-101)
    /suppliers mit E-Mail-Adresse, Telefon und Ansprechpartner; die Dokumente einer Zumietung
      und die Verbindung der Mails mit dem Lieferanten (PRJ-106)
    /projects mit der Wiedervorlage (Datum, Notiz, für wen), auch als Filter (PRJ-105)
    /storage-locations mit der Voreinstellung für neue Exemplare (MAT-052)
    /material-models, /material-items: die Angaben an Modell und Exemplar (MAT-049, MAT-050)
    /mail/mailboxes/{id}: DELETE löscht auch ein benutztes Postfach; Mails und Mail-Protokoll
      behalten seinen Namen (EML-046)
    /mail/settings: crew_answers bleibt dort, auch wenn die Oberfläche die Wahl unter den
      Grundeinstellungen zeigt (ADM-015)
    Nur in der Oberfläche: Reiter und Titel "Überblick" (PRJ-104; der PDF-Pfad
    ist /projects/{id}/deployment/pdf), Filter eingeklappt (UIX-038), Balken der
    Zeitstrahlen (VFG-030)

    Vorgesehen mit Ausbaustufe 8; Pfade und Felder legt der
    Bau fest und trägt sie danach hier nach, die genaue Beschreibung liefert die
    API selbst (API-004):
    In Teilprojekte gliedern, Teilgruppen in Teilprojekte umwandeln (PRJ-050)
    Chat eines Projekts (UIX-010)
    Spesen: erfassen, freigeben, als erstattet kennzeichnen (ZEI-019)
    Zuschläge getrennt in Personalpositionen und Preisübersicht (PER-009)
    Rechnung und Stornorechnung: 400, wenn Rechnungen abgeschaltet sind (DOK-014)
    Servicefälle, Showfiles, Automationen und ihre Läufe, Fahrten und die Lage von
    Adressen, wie alles andere auch über die API (API-002; PRJ-090, PRJ-089, ADM-013,
    PRJ-097, UIX-034)

    Vorgesehen; Pfade und Felder
    legt der Bau fest und trägt sie danach hier nach, die genaue Beschreibung
    liefert die API selbst (API-004):
    /mail/mailboxes mit den Adressen eines Postfachs, ihrem Umgang mit Mails ohne
      Kennung und der Rolle "nur für Servicefälle" (EML-047); nach der Zuordnung
      auch "nur als gelesen markieren" (EML-006)
    Versand und Mail-Protokoll: "nicht versendet – kein Mailserver eingerichtet" (EML-048)
    Beteiligte eines Servicefalls: Person, Funktion, Notiz (PRJ-108)
    /projects: die Uhrzeit der Wiedervorlage (PRJ-109); alle Wiedervorlagen (VFG-034)
    /notifications und /notifications/preferences mit Kategorie und "In der App" (UIX-039)
    /time-entries und /time-entries/choices: Anteile eines Zeitraums; ein Eintrag ohne
      Anteile ist möglich, damit die Begleit-App unverändert arbeitet (ZEI-025); offene
      Servicefälle in der Auswahl (ZEI-024)
    /people mit der Entfernung Wohnung – Betrieb; Spesen mit dem Abzug des Arbeitswegs;
      /settings mit dem Schalter für den Abzug (ZEI-027)
    /settings mit "Hinweise zu Arbeitszeiten anzeigen"; ausgeschaltet nennt die API keine
      Hinweise (ZEI-018)
    Zuschlagsregeln und eigene Feiertage (PER-040)
    Vor allem die Oberfläche betreffen: "Als Projekt anlegen", Vorschläge und
    Mehrfachauswahl unter Anfragen (PRJ-107), Ziehen und Darstellung im
    Personalplan (VFG-031, VFG-032), Linien und Scrollbereich der Zeitstrahlen
    (VFG-033), Gruppieren in Tabellen (UIX-040), kein "Zurück" (UIX-041),
    Symbol der Datumsfelder (UIX-042), Markieren in der Woche (PER-039; die
    API trägt Verfügbarkeiten ein), Stundenlohn und Kopieren unter
    Meine Zeiten (ZEI-026)

    Vorgesehen; Pfade und Felder legt der Bau fest und trägt sie danach hier
    nach, die genaue Beschreibung liefert die API selbst (API-004). Was die
    Begleit-App nutzt (/offline/packlists, …/sync, /time-entries,
    /time-entries/choices, /projects/{id}/deployment), bleibt kompatibel;
    zusätzlich gibt es:
    Jeder schreibende Aufruf mit Idempotency-Key: die gespeicherte Antwort erst nach
      Anmeldung und Prüfung der aktuellen Rechte, nur für denselben Nutzer bzw. dasselbe
      Token und dieselbe Anfrage; derselbe Schlüssel mit anderem Inhalt 409 (API-010)
    Jede Versionsprüfung (ETag/If-Match bzw. Versionsnummer): Vergleich und Speichern in
      einem Schritt; von zwei gleichzeitigen Änderungen wird die zweite abgewiesen (API-010)
    /offline/packlists: GET legt nichts an; je Zeile die Version des Servers (PCK-026, PCK-027)
    …/packlists/{id}/sync: je Änderung freiwillig base_version und eine Änderungs-ID; bei
      einem Konflikt der Stand des Servers für die Zeile; ohne base_version nach
      der Regel für die Uhren (PCK-027)
    Webhook packing.returned nur, wenn die zurück abgehakte Menge steigt (API-012, PCK-027)
    Chat: "gelesen bis" (up_to) höchstens die neueste Nachricht dieses Chats; eine Nachricht
      eines anderen Chats wird abgewiesen (UIX-010)
    Abfrage nach Änderungen: der Stempel ändert sich mit jeder Änderung (UIX-010, UIX-020)
    /mail/mailboxes mit "ab" und "nur ungelesene" je Postfach und je Adresse (EML-049)
    /projects: ein Servicefall ohne Kunden wird mit 400 abgewiesen (PRJ-090)
    Fahrten eines Projekts: entfernen, ändern, eigene anlegen, zurücksetzen (PRJ-111)
    /projects/{id}/crew-lines: ändern; Zeitplanung → Phasen nutzt dieselben
      Regeln (PRJ-110)
    Webhooks, verknüpfte Kalender, Postfächer: ein internes Ziel ohne Freigabe wird mit 400
      und Grund abgewiesen; Zugangsdaten nur an denselben Server (NFA-071, NFA-072)
    /self-check nennt gesperrte Ziele vorhandener Einstellungen und den Stand von HTTPS
      (NFA-071, NFA-073)
    Vor allem die Oberfläche betreffen: Meine Einsätze (UIX-043), Personal im
    Zeitstrahl der Zeitplanung (VFG-035), Sortieren und eingeklappte Filter
    (UIX-015, UIX-038, UIX-040), Routenlinks ab dem Standort (UIX-033),
    Referer der Kacheln (UIX-034), Hinweis auf Showfiles (PRJ-089)

    Vorgesehen; Pfade und Felder
    legt der Bau fest und trägt sie danach hier nach, die genaue
    Beschreibung liefert die API selbst (API-004):
    /me bzw. /users mit der Sprache der Oberfläche; Fehlermeldungen in der Sprache des
      Aufrufers – seiner Wahl, sonst nach Accept-Language (UIX-029)
    /settings mit der Sprache der Dokumente (UIX-029)
    /projects: Servicefälle mit den Status wartet (mit Grund), wartet auf Schließen und
      Rückstand; ohne die nötige Wiedervorlage 400 (PRJ-112, PRJ-109)
    Automationen: Auslöser "Neue Kommunikation im Servicefall", Bedingung auf den Status,
      Aktion "Status des Servicefalls setzen"; die drei voreingestellten Regeln (ADM-013)
    Zusammenfassung der Korrespondenz eines Projekts oder Servicefalls: erzeugen als
      Aufgabe im Hintergrund (/jobs/{id}), lesen mit Stand "veraltet"; die Kurzübersicht
      ohne KI (EML-040, EML-044)
    KI-Anbieter, Verwendungen und das Protokoll der KI-Aufrufe ohne Inhalt (ADM-017)
    Vor allem die Oberfläche bzw. den Server betreffen: Adresse und Zertifikat
    vorbereiten und der Befehl `sudo rentalars address apply` (ADM-016), die
    Installation der lokalen KI mit `sudo rentalars ai install` (EML-040),
    "Entwurf vorschlagen" beim Schreiben einer Mail (ADM-017), Gruppieren nach
    jeder Spalte (UIX-044), das Handbuch in der Anwendung (UIX-029)

    Umgesetzt mit den Anforderungen der Begleit-App; die genaue Beschreibung
    liefert die API selbst (API-004). Was die Begleit-App nutzt, bleibt
    kompatibel; zusätzlich gibt es:
    /projects, /projects/{id}: field_changed_at mit dem Zeitpunkt der letzten Änderung je
      Feld – name, venue, start, end, event_start, event_end, notes, status, follow_up
      (Tag, Uhrzeit, Notiz und Person der Wiedervorlage) und die übrigen Felder, die PATCH
      ändert; bei Einsatzsicht nur die gezeigten (PRJ-113)
    PATCH /projects/{id} mit changed_at: jedes gesendete Feld nur, wenn jünger; die Antwort
      ist das Projekt, wie es jetzt ist, mit applied: [...]; ohne changed_at mit
      If-Match (API-010) (PRJ-113)
    POST /projects/{id}/status, PUT und DELETE /projects/{id}/follow-up mit changed_at
      (bei DELETE auch in der Abfrage); ein Statuswechsel, der beim Eintreffen nicht mehr
      erlaubt ist: 409 mit dem aktuellen Projekt und dem Code status_not_allowed (PRJ-113)
    /service-cases, /service-cases/{id}: case_status_changed_at und field_changed_at;
      PATCH mit case_status_changed_at (Status, Grund und Wiedervorlage als Einheit) und
      changed_at (je Feld) (PRJ-114); manager_name (API-016)
    /people/me/profile: GET mit updated_at je Angabe, PATCH mit changed_at (eine Zeit oder
      je Angabe); /people/me/absences: GET, POST mit Idempotency-Key,
      DELETE /people/me/absences/{id}; /people/me/deployments?from=&to= mit ETag – alle
      ohne Recht am Modul Personal (API-015)
    /projects mit manager_name und venue_label, auch bei Einsatzsicht; /me und die Antwort
      der Anmeldung mit server_version; /notifications?companion=1: unread zählt im Filter,
      dazu unread_total; Zeiteinträge mit pay_kind und in_day_rate, wo Sätze sichtbar sind
      (API-016)
    /settings/notifications: GET, PATCH – Uhrzeit, Abstand, Wochentag, Vorlauf, erneut
      melden; dazu shortage_next_check (VFG-036)
    /projects/{id}/correspondence-summary mit estimate; /ai/settings mit Prozessor,
      Threads, typischer Dauer und Empfehlung; Geschwindigkeitstest und Protokoll mit
      Lese- und Schreibgeschwindigkeit (EML-040); Zeitlimit als Stille (ADM-017)
    /time-entries/choices: die Auswahl der Funktion ist bei einem Projekt nie leer (ZEI-007)
    Packen: Material nachtragen ohne Recht 403 mit needs_project_write; …/sync lehnt eine
      Menge über der Packliste mit dem Grund needs_project_write bzw. above_packing_list ab;
      /offline/packlists mit can_add_material; DELETE an Packliste, Übergabe und Entnahme
      braucht wie im Browser "bearbeiten" (PCK-013, PCK-027)
    /products: time_surcharges null bei Produkten, die keine Dienstleistung sind (PER-009)
    Mit dem Token der App (packing, projects, time_tracking, email) gehen
      Chat, Korrespondenz, Preisübersicht und Anfragen (/mail/unknown) (APP-001)
    Vor allem die Oberfläche betreffen: Menü als Schublade auf dem Smartphone
    (UIX-045), Korrespondenz gleich in Projekt und Servicefall (EML-050), Reiter
    "Überblick" im Servicefall (PRJ-090), Linien der Zeitstrahlen (VFG-033),
    Zuschläge nur für Personalpositionen (PER-009, PER-040), englische
    Bezeichnungen der Felder (UIX-029)

    Umgesetzt; die genaue
    Beschreibung liefert die API selbst (API-004). Was es gab, bleibt
    unverändert – auch die Pfade unter /api/v1 (NFA-074):
    /projects/{id}: invoice_status (leer, issued, not_needed, earlier) und
      invoice_state (open, invoiced, not_needed, leer); POST
      /projects/{id}/invoice-status mit issued, not_needed oder leer (DOK-015)
    /settings/notifications: invoice_reminders, invoice_time, invoice_first_days,
      invoice_every_days, invoice_user, invoice_service_cases; lesend
      invoice_checked_at, invoice_reminded, invoice_reminders_since, invoice_next_check
      (DOK-015)
    /reports/profitability?year=|since=&until=&closed=1, /reports/material?year=,
      /material-items/{id}/revenue (PRJ-115, MAT-053)
    /material-items: purchase_price_in; beim Anlegen mehrerer price_for_set (MAT-054)
    /labels mit format small, large, cable; /label-settings GET und PATCH (MAT-056)
    Import des Materials: Optionen prices (net, gross) und price_tax_rate (IMP-014);
      "#0802" als ID, "#0851" als Preis (IMP-015, IMP-016)
    /automations: Auslöser defect, Aktionen create_case und create_inquiry (MAT-057)
    /service-cases: is_internal, source_defect; mit inquiry auch aus einer Defektmeldung
      (MAT-057, PRJ-090); /mail/unknown mit defect_report
    POST /projects/{id}/mails/notes, PATCH /projects/{id}/mails/{id} (nur Notizen),
      DELETE auch durch den Verfasser; in der Liste direction "note" (EML-051)
    Vor allem die Oberfläche betreffen: Einstellungen geordnet (UIX-046), Fuß der
    Seitenleiste (UIX-047), Aktionsleiste der Mehrfachauswahl (UIX-048), Modell
    in der Ansicht eines Exemplars (MAT-055), Stundensätze in der
    Ersteinrichtung (ADM-018), Adressen der Seiten (NFA-074)

    Umgesetzt mit Stufe 9; was es gab, bleibt unverändert:
    /vehicles (?type=car|trailer, ?status=), /vehicles/{id} GET, PATCH, PUT
      (Fuhrpark: das Exemplar mit seinen Fahrzeugdaten, LOG-002, LOG-003)
    /vehicles/{id}/availability?start=&end= (Buchungen über die Projekte, overlaps,
      free, LOG-004)
    /material-models/{id}/to-fleet POST (in den Fuhrpark übernehmen, LOG-016)
    /projects/{id}/logistics GET, POST; /projects/{id}/logistics/{id} GET, PUT, PATCH,
      DELETE (Fahrzeugbuchungen mit Fahrten, Kilometern, Tagen, Preisen, Kosten und
      Hinweisen, LOG-001, LOG-005, LOG-009, LOG-010)
    /projects/{id}/trips/{key}/vehicles GET, POST; /projects/{id}/trip-vehicles/{id}
      GET, PUT, PATCH, DELETE (Fahrteinsätze mit Anhänger und km, LOG-006, LOG-007)
    /projects/{id}/trips/{key}/route GET (Kilometer vom Routendienst, LOG-017)
    /projects/{id}/trips: vehicles je Fahrt (LOG-007)
    /projects/{id}/crew-lines: vehicle_line, is_driver; /projects/{id}/deployment und
      /people/me/deployments: vehicle, is_driver (LOG-008)
    /projects/{id}/planning: logistics; /projects/{id}/totals: logistics_total,
      logistics_cost; Preisübersicht mit dem Bereich logistics (LOG-009);
      /reports/profitability mit logistics_revenue, logistics_cost
    /projects/{id}/duplicate: with_logistics (LOG-019)
    /projects/{id}/packlists: vehicle_line (LOG-011)
    /products: vehicle_type, price_per_km, trailer_surcharge_per_km, trailer_billing,
      cost_per_km, cost_per_day (LOG-005, LOG-010); /qualification-types:
      licence_classes (LOG-012)
    /material-models/{id}/revenue (MAT-058)
    Import: rows und row_counts in der Antwort und im Bericht (IMP-011)
    /projects/{id}/mails: sender beim Senden; /projects/{id}/mails/senders
      (EML-052); Postfächer und Aliasse mit sender_roles, Postfächer mit
      signature_html (EML-026)
    /mail/unknown POST; /mail/unknown/{id} GET, PATCH, DELETE (EML-053)
    /service-statements (?month=) GET, POST; /service-statements/{id} GET, PATCH,
      DELETE; /service-statements/{id}/invoice POST; /service-statements/{id}/mark
      POST; Dokumente mit billed_projects (DOK-016)
    /document-templates/defaults GET, POST (DOK-018)
    /time-entries: in_flat_rate (ZEI-028)

    Umgesetzt mit Stufe 9; was es gab, bleibt unverändert, außer
    beim Preis der Produkte (PRD-047):
    /purchases POST (Kauf einpflegen, MAT-061); /purchases/invoices POST (Rechnung
      hochladen und lesen, Vorschlag, mit KI über /jobs/{id}, MAT-062)
    /material-models/{id}/items, /material-items POST, /material-items/{id} PATCH:
      prices (net, gross) und price_tax_rate (MAT-059)
    /products/{id}/duplicate POST (PRD-048); /products/suggest-article-number:
      product (PRD-049); /products: sale_price nur bei Verkaufsprodukten, price
      nicht bei ihnen; /projects/{id}/material-lines: is_sale nur bei Verkaufsprodukten
      oder schon verkauften Positionen (PRD-047)
    /utilization: Sets mit components, per_kit und free (VFG-037)
    /people/availability: alle Personen ohne Funktion (VFG-038)
    /projects/{id}/crew-lines: firm; /projects/{id}/crew-lines/bulk POST
      (PRJ-117, PER-041)
    /time-entries/{id}/correct POST (ZEI-030); /settings/notifications: approval_*
      (ZEI-029)
    /accounting/documents GET, /accounting/documents/totals GET (DOK-020)
    /permissions, /roles: Projektzugriff deployment, Sonderrecht availability
      (AUT-031, AUT-032); ohne das Recht availability und shortage_total null,
      /availability, /shortages, /utilization 403
    /service-cases: auch für Zuständige und Beteiligte ohne Modul Projekte (AUT-033)
    /users, /people: data_access (AUT-034)
    /ai/settings: invoice (MAT-062)

    Umgesetzt mit Stufe 9; was es gab, bleibt unverändert:
    /material-items/{id}/audits GET, POST; /material-items/{id}/todos GET, POST,
      …/todos/{todo}/done POST; /material-todos GET, /material-todos/done POST;
      /material-audits/due GET;
      /audit-settings GET, PATCH; /material-items: last_audit, next_audit,
      audit_due, open_todos (MAT-067 bis MAT-070)
    /custom-fields, /custom-fieldsets (alle Methoden); /material-models: fieldset;
      /material-items: custom_fields, Filter cf<id> (MAT-071 bis MAT-073)
    /projects/{id}/chat: attachments, POST mit files; /projects/{id}/chat/media/{id}
      GET, …/thumbnail GET (UIX-049)
    /projects/{id}/mails, …/notes: locked; /projects/{id}/mails/{mail}/lock PATCH;
      /mail/settings: lock_new_in_projects, lock_new_in_cases (EML-055)
    /projects/{id}/access GET (AUT-035)
    /projects/{id}/relations GET, POST, …/relations/{id} DELETE; /projects/{id}:
      related (PRJ-119)
    /projects/{id}/phases: places; /projects/{id}/phases/{phase}/staffing POST
      (PRJ-120); /projects/{id}/reschedule: follow (PRJ-121)
    /imports/{kind}/export GET (IMP-017)

    Umgesetzt mit Stufe 9; was es gab, bleibt unverändert:
    /automations: default_key, default_changed; /automations/restore-defaults POST
      (ADM-019)
    /purchases/invoices, /jobs/{id}: total_net, total_gross, currency, je Position
      serial_numbers, category, product, hints (MAT-075, MAT-076)
    /material-models: protection_class; /material-items: protection_class_override,
      effective_protection_class (MAT-077)
    /inspection-types: is_electrical; Prüfungen mit Messwerten, evaluation,
      report_url; /material-items/{id}/inspections/check POST;
      /inspections/{id}/report GET (MAT-078)
    /products/{id}/calendar-link, /material-models/{id}/calendar-link,
      /material-items/{id}/calendar-link GET, POST, DELETE (VFG-040)
    /notifications/preferences: label, category_label (UIX-052)

    Umgesetzt mit Stufe 9; was es gab, bleibt unverändert:
    /material-items: storage_spot, effective_storage_spot; /material-items/
      bulk-update: storage_spot (MAT-080)
    /material-items/inspections/batch POST (MAT-082)
    /projects: overall_discount_percent, overall_discount_amount; totals:
      net_before_overall_discount, overall_discount (PRJ-123)
    /projects, /service-cases: customer_name (PRJ-122)

    Umgesetzt mit Stufe 9; was es gab, bleibt unverändert:
    /products: pieces_per_product, stock_pieces (PRD-052)
    /contacts: first_name, last_name, greeting_style, greeting_text, greeting
      (KND-011)
    /projects: warnings (PRJ-127); Positionen: is_text (PRJ-128), warnings
      (PER-044); /material-items, /purchases: warnings (MAT-084)
    /accounting/drafts und .../lines, .../preview, .../issue;
      /accounting/documents/{id}/send (DOK-022); Dokumente: project leer,
      customer, reference, print_product_descriptions (DOK-021)

    Umgesetzt mit Stufe 10:
    /incoming-invoices mit Positionen, Lesen, Lieferant anlegen, Aufteilung,
      Einpflegen (Vorschau, confirm) und /incoming-settings (DOK-023, DOK-024)
    /material-items/{id}/asset, .../sale-preview, .../sell; /asset-register
      (+totals, csv); /stock-sales (+summary, csv, {id}, cancel, invoice)
      (MAT-086, MAT-087); purchase_date mit Genauigkeit (MAT-088)
    /legacy-imports mit Vorschau, Bestätigen, Zurücknehmen (PRJ-130)
    /tax-accounts (DOK-026); `tax_account` an den
      Positionen von /incoming-invoices; Position der Altimport-Vorschau mit
      note, kind (material, crew, logistics), Funktion und Fahrzeug (PRJ-130);
      Exemplar-Status import_error nur durch den Import (MAT-020, IMP-010)
    /projects/bulk, /service-cases/bulk (PRJ-133, PRJ-134);
      /service-cases/{id}/customer-pdf (PRJ-131); /incoming-invoices/{id}/xml und
      einvoice_format, einvoice, xml_url an der Eingangsrechnung (DOK-040,
      DOK-041); /documents/{id}/credit sowie billing_type, amount, percent und note
      beim Anlegen, billing_type, billing_number und credit_for am Beleg (DOK-030
      bis DOK-036); complete, missing_exchange_rate, without_amount bei den
      Summen der Eingangsrechnungen (DOK-023)
    /ldap/settings, /ldap/mappings, /ldap/test-connection, /ldap/test-login,
      /ldap/sync (AUT-029)
    /ai/auto-summaries (+runs, dry-run, run), /customers/{id}/ai-summaries,
      /projects/{id}/correspondence-summary (EML-056)
    /crew-lines/{id}/offers (+accept, reject, counter, withdraw), /price-offers,
      /people/me/offers, /settings/price-offers (PER-038)
    /scan/resolve, /products/{id}/relations, /projects/{id}/suggestions,
      Aktion scan der Packliste (MAT-027, PRD-023, PCK-010)
    /projects/{id}/overall-discount (PRJ-123)

    /settings, /tax-rates, /units, /number-ranges, /rental-scales
    /audit-log
    /webhooks
    /self-check                              (Selbstprüfung, NFA-037)


## 9. Technische Grundlage

### 9.1 Entscheidungen

- Eigenentwicklung. Ein vorhandenes Inventarsystem taugt weder als Codebasis
  noch als zweite Anwendung neben Rentalars: Es kennt keine zeitraumbezogene
  Verfügbarkeit, keine Produkte, Projekte und Personaldisposition, und zwei
  Anwendungen verdoppelten Installation, Rechte und Sicherung (Ziel "wenig
  Aufwand").
- Technikstack: Python mit Django und Django REST Framework, ausgeliefert
  über einen Anwendungsdienst (z. B. Gunicorn) hinter NGINX, Datenbank
  MariaDB.
- Oberfläche: vom Server erzeugte Seiten; die API steht gleichwertig daneben
  (API-002).
- Lizenz: GNU General Public License, Version 3 oder später (NFA-052). Code
  aus Projekten unter AGPL wird nicht übernommen (NFA-053).

Den Ausschlag für Django gab, dass
Grundkenntnisse in Python vorhanden sind, in PHP nicht – und dass der Code
für den Betreiber lesbar und pflegbar bleiben soll (NFA-055).

### 9.2 Was für Django spricht

- Lesbarkeit: Python ist bekannt; Sprache und Framework müssen nicht
  gleichzeitig neu gelernt werden.
- Verwaltungsoberfläche inklusive: Stammdaten wie Kategorien, Steuerarten,
  Funktionen, Händler oder Staffeln lassen sich ohne eigene Masken pflegen
  (ADM-007).
- Langzeitversionen mit mehrjähriger Unterstützung: weniger Pflegedruck, auch
  für Betriebe, die selbst installieren (NFA-054).
- Der Import der Excel-Tabelle entsteht in derselben Sprache (IMP-007).
- MariaDB wird offiziell unterstützt; Anmeldung, Rechte, Migrationen und
  Mailversand gehören zum Framework.
- Hintergrundaufgaben wie der Mailabruf lassen sich als Befehle über die
  Zeitsteuerung des Servers starten, ohne zusätzlichen Dienst (NFA-036).

### 9.3 Nachteile von Django – und wie der Katalog ihnen begegnet

- Installation über eine eigene Python-Umgebung statt nur über
  Distributionspakete. Das Installationsskript legt sie an; die Versionen der
  Bibliotheken sind festgeschrieben (NFA-029, NFA-031).
- Kein fertiger Code im selben Stack, der sich übernehmen ließe: Datenmodell
  und Abläufe müssen selbst entworfen werden.
- Rechte je Projekt sind Eigenbau: Das Framework kennt Rechte je Datenart,
  nicht je einzelnem Datensatz. Projektrechte und die getrennten Rechte für
  Finanzen und Korrespondenz (AUT-016 ff., AUT-019, AUT-025) brauchen eigene
  Logik oder eine Zusatzbibliothek und gehören zu den getesteten
  Kernbausteinen (NFA-019).
- Die Verwaltungsoberfläche verführt dazu, alles dort abzuwickeln. Sie ist
  für Stammdaten gedacht, nicht für den Alltag von Lager und Crew, und darf
  die Fachregeln nicht umgehen (ADM-007).
- Vom Server erzeugte Seiten reagieren weniger unmittelbar als eine
  eigenständige Oberfläche. Wo es darauf ankommt, wird gezielt ergänzt
  (UIX-009).
- Oberfläche und API können auseinanderlaufen, weil die Oberfläche die API
  nicht selbst benutzt. Beide greifen deshalb auf dieselbe Fachlogik zu, und
  jede Fachfunktion hat einen Test über die API (API-002, API-014).
- Fehler erst zur Laufzeit: Auch Python prüft Typen nicht vor der Ausführung.
  Gegenmittel sind Typangaben mit automatischer Prüfung und Tests (NFA-019,
  NFA-020).
- Viele Einzelabfragen bleiben leicht unbemerkt. Verfügbarkeit und
  Preisberechnung liegen in eigenen Bausteinen, und die Antwortzeiten werden
  gemessen (NFA-021, NFA-044).

### 9.4 Alternativen

- PHP
  + beide Vorbilder bauen darauf; Laufzeit vollständig aus Ubuntu-Paketen
  − neue Sprache; jährliche Hauptversionen mit nur rund zwei Jahren
    Sicherheitskorrekturen
- PHP mit Symfony (und API Platform)
  + Langzeitversionen; API samt Beschreibung entsteht weitgehend aus dem
    Datenmodell
  − neue Sprache, steilere Lernkurve, mehr Konfiguration
- TypeScript mit Node.js (z. B. NestJS)
  + eine Sprache für Oberfläche und Server, durchgehend typisiert
  − viele kurzlebige Abhängigkeiten, Laufzeit nicht aktuell in den
    Ubuntu-Paketen, mehr Eigenbau bei Rechten und Verwaltung
- Go
  + eine einzige ausführbare Datei: die einfachste Installation von allen,
    geringster Speicherbedarf
  − kaum fertige Bausteine für Rechte, Verwaltung, PDF; deutlich mehr
    Eigenentwicklung bei einer Anwendung mit so vielen Datenmasken
- Java/Kotlin mit Spring Boot oder C# mit .NET
  + streng typisiert, sehr robust, Auslieferung als eine Datei
  − höherer Speicherbedarf und mehr Aufwand, als ein kleines Projekt braucht

Alle genannten Wege erfüllen die Vorgaben (NGINX, MariaDB, Referenzsystem).
Den Ausschlag geben die Erfahrung derer, die entwickeln, und der
Pflegeaufwand über Jahre.


## 10. Ausbaustufen

Jede Anforderung trägt ihre Stufe (S1 bis S11). Die Stufen bauen aufeinander
auf, und jede endet mit einem Stand, der für sich einsetzbar ist. Gebaut wird
eine Stufe nach der anderen; was nicht S1 ist, bleibt liegen, bis S1 läuft.

| Stufe | Inhalt                       | MUSS | SOLL | KANN | gesamt |
|-------|------------------------------|------|------|------|--------|
| S1    | Kern                         |  168 |   42 |    0 |    210 |
| S2    | Preise und Zumietung         |   20 |   11 |    0 |     31 |
| S3    | Personal und Zeit            |   43 |   13 |    0 |     56 |
| S4    | Korrespondenz und Planung    |   18 |   27 |    0 |     45 |
| S5    | Lager und Dokumente          |    8 |   89 |    2 |     99 |
| S6    | Erweiterungen                |    0 |   51 |    0 |     51 |
| S7    | Wünsche und Begleit-App      |    0 |   46 |    0 |     46 |
| S8    | Service, Karten, Zuschläge   |    2 |   69 |    0 |     71 |
| S9    | Logistik und Wünsche         |    8 |  104 |    1 |    113 |
| S10   | Erweiterungen                |    0 |   79 |   19 |     98 |
| S11   | Vorgemerkt                   |    0 |    0 |    2 |      2 |
|       | alle Stufen                  |  267 |  531 |   24 |    822 |

Stand der Umsetzung: Gebaut sind alle MUSS- und SOLL-Anforderungen der Stufen 1 bis 10 sowie die KANN-Anforderungen, die
unten als gebaut genannt sind (zum Beispiel GWL-011 und GWL-014). Die übrigen KANN-Anforderungen der Stufen 10 und 11 sind
vorgemerkt. Die Planung mit Schalter für das automatische Speichern (PRJ-129) bleibt auf Wunsch zurückgestellt.
Anforderungen, die nachträglich zu einer bereits gebauten Stufe hinzukamen, sind dort mitgezählt und ebenfalls umgesetzt.

Stufe 0 – Vorbereitung (keine Anforderungen)
- Entschieden: Eigenentwicklung mit Python und Django, vom Server erzeugte
  Oberfläche mit gleichwertiger API, Lizenz GPL v3 oder später (Kapitel 9)
- Annahmen aus Kapitel 12.2 bestätigen, Datenmodell und API-Beschreibung für
  Stufe 1 abstimmen
- Grundgerüst mit Regeln für Aufbau, Benennung und Dokumentation des Codes
  anlegen (NFA-055 ff.), bevor Fachfunktionen entstehen

Stufe 1 – Kern
Ergebnis: Das Material ist erfasst, Projekte lassen sich mit Material planen,
die Verfügbarkeit stimmt, und die Packliste kommt heraus.
- Anmeldung, Nutzer, Rollen, Modulrechte; getrennte Rechte für Preise
- Stammdaten mit gemeinsamen Kategorien und Kürzeln, Steuerarten
- Material (Modell/Instanz, Mengenmaterial, "verbaut in" fest oder lose),
  Produkte mit Artikelnummer, einfachem Preis und Zuordnung, Sets
- Übernahme der Excel-Bestandsliste per Skript (IDs 0001 bis 1650)
- Kunden, Projekte mit Status, Materialpositionen und Teilgruppen mit
  Zwischensummen; Preisübersicht im Browser
- Verfügbarkeit mit Pufferzeiten, Warnung bei Überbuchung, mit verplanten
  Inhalten von Cases
- Packliste als PDF, Packen und Rücknahme durch Abhaken, ohne Scan
- Dunkle Oberfläche in den festgelegten Farben; ein Eintrag "Materialverwaltung"
- API mit Beschreibung und Tests
- Installationsskript für Ubuntu Server 24.04 LTS und 26.04 LTS,
  Ersteinrichtung im Browser, HTTPS, Sicherung, Aktualisierungsbefehl;
  Leistungsnachweis auf dem Referenzsystem
- Kommentierter Code und Entwicklerdokumentation von Beginn an
- Datenmodell für Teilprojekte, geschachtelte Teilgruppen und Projektrechte
  vorbereitet, noch ohne Oberfläche

Stufe 2 – Preise und Zumietung
Ergebnis: Die Preisübersicht taugt als Grundlage für Angebote.
- Abrechnungsarten, Miettage, Staffel, Miet- und Verkaufspreis
- Aufpreise als Betrag und Prozent, Fahrt/Transport, freie Positionen
- Rabatt, Pauschalpreis und optionale/alternative Teilgruppen
- Zumietung über Kategorie E mit Vorschlag bei Fehlmenge
- Kalkulation mit Kosten und Gewinn aus dem Projekt

Stufe 3 – Personal und Zeit
Ergebnis: Die Crew ist eingeplant, erfasst ihre Zeiten selbst, und das
Personal steht mit Preis und Kosten im Projekt.
- Personen, Funktionen, Stundensätze, Pauschalen, Abwesenheiten
- Dienstleistungsprodukte (Kategorie D) je Funktion; Abrechnung nach Plan,
  pauschal oder nach Aufwand
- Personalpositionen im Projekt, Konfliktprüfung
- Zeiterfassung mit Schnellerfassung, Freigabe, Auswertung, Export
- Rechte je Projekt mit Einsatzsicht; eingeschränkte Konten für freie Kräfte

Stufe 4 – Korrespondenz und Planung
Ergebnis: Projektmails liegen am Projekt, und der Überblick über Wochen und
Engpässe ist da.
- E-Mail: Abruf, Zuordnung über das Projektkürzel, Korrespondenz am Projekt,
  Versand aus dem Projekt (hängt nur von Stufe 1 ab und lässt sich vorziehen)
- Kalender, Zeitstrahl, Engpassliste, Startseite
- Benachrichtigungen, Einsatzanfragen, offene Punkte je Projekt
- Zwei-Faktor-Anmeldung und Selbstprüfung der Installation, spätestens vor
  dem Betrieb aus dem Internet

Stufe 5 – Lager und Dokumente
Ergebnis: Das Lager arbeitet vollständig digital, und die Dokumente für den
Kunden entstehen in Rentalars.
- Etiketten, Lagerorte, Defektmeldung, Prüfungen und Fälligkeiten,
  Sperrzeiten
- Freiwillige Zuordnung von Exemplaren, Herauslösen loser Inhalte
- Verbrauchsprodukte mit Mindestbestand
- Auftragsbestätigung, Lieferschein, Rechnung, Crew-Disposition
- Import und Export in der Oberfläche, Preisübersicht als PDF und CSV
- Wünsche aus der vierten Benutzung: Spalten wählen und sortieren, Kalender
  als Woche, Zeitstrahl je Material und Person (UIX-015, PRJ-067, VFG-019,
  PER-020)
- Weitere Anforderungen:
  Personal und Nutzer zusammengeführt, Einmal-Passwort, Zugriffsprotokoll
  (AUT-026 bis AUT-028); Verfügbarkeitskalender, Kalender-Links und CalDAV,
  Position, Funktion als Voraussetzung, Höchstrabatt (PER-021 bis PER-026);
  Projektvorlagen, Kunde per Eingabe, Lichtplot (MVR), alte Preise,
  optionale Positionen, Angebot (PRJ-068 bis PRJ-077, DOK-010); Kalender
  und Pläne (VFG-020 bis VFG-023); Signatur, CC/BCC, Mailverlauf,
  Mail-Protokoll (EML-034 bis EML-039); Lexware-Import (IMP-013);
  Sicherung im Browser und Server im Selbsttest (ADM-008 bis ADM-010);
  Oberfläche (UIX-016 bis UIX-025, MAT-047)

Stufe 6 – Erweiterungen
Ergebnis: Große Produktionen werden als Gesamtprojekt mit Teilprojekten
geplant, und andere Systeme erfahren, was in Rentalars geschieht.
- Teilprojekte mit eigener Mietdauer, eigenen Positionen, eigenem Personal
  und eigenem Status; Summen und Engpässe im Gesamtprojekt; Material, das
  von einem Teilprojekt ins nächste wechselt; Rechte je Teilprojekt
  (PRJ-031, PRJ-044 bis PRJ-049, PRJ-060)
- Geschachtelte Teilgruppen mit Ziehen und Ablegen, bis zu drei Ebenen
  (PRJ-037)
- Webhooks für Projektstatus, Ausgabe und Rücknahme, freigegebene Zeiten
  (API-012)
- Übergabe der Rechnungen an Lexware Office und als DATEV-Buchungsstapel
  (DOK-011, DOK-012)
- Weitere Anforderungen: zu
  jedem Zeitpunkt eine Verfügbarkeit, Kalendertermine als Block, Serien
  (PER-027, PER-028); "Mein Bereich" und einheitliche Reiter (UIX-026,
  UIX-027)
- Weitere Anforderungen: Kopf des
  Projekts mit Status als Auswahlliste und Vorschlag für das nächste Dokument,
  Dokumente und Dateien in einem Reiter, Personal je Phase im Reiter
  "Zeitplanung", Einsatzübersicht als PDF, mehrere Positionen auf einmal,
  Symbole für optional und Alternative, Zumietung als Teilzeile, Summen in der
  Projektliste, MVR-Datei in den Projektdateien, "Gewinn aus dem Projekt",
  Personal je Phase in der Preisübersicht (PRJ-078 bis PRJ-088); Stunden über
  den ganzen Zeitraum (PRJ-073); Tage-Ansicht und Vorschläge in
  der Auslastung (VFG-024, VFG-025); Angebot nur mit Teilgruppen, Gültigkeit
  in Tagen (DOK-013); Ausgabe je Artikel (PCK-025); mehrere Postfächer,
  Anfragen, Crew und Kunde als Empfänger (EML-041 bis EML-043); höchster
  Rabatt je Produkt (PRD-041); Funktionen ohne Pflichtsatz und Tagessätze,
  Woche und mehrere Kalender in der Verfügbarkeit (PER-029 bis PER-031);
  Standardwerte (ADM-011); Befehl und Aktualisierung ohne Ausführungsrecht
  (NFA-069)
- Weitere Anforderungen: Phasen
  "Planungen und Besprechungen", "Packen" und "Nachbereitung", Status
  "Wieder im Lager", neue Phase aus der Personalplanung, Vorlage "Dry Hire",
  Kundenmaterial im Projekt (PRJ-092 bis PRJ-096, PRJ-006, PRJ-071);
  Kundenmaterial im Lager, Kategorie C "Fremdmaterial" (PRD-043);
  frühere Projektnummern gelten weiter (ADM-014);
  Einsatzanfragen per Antwort-Mail beantworten
  (PER-032); einklappbare Filter, Urhebervermerk, Firmenname in der
  Seitenleiste (UIX-030 bis UIX-032)

Stufe 7 – Wünsche und Begleit-App
Ergebnis: Packen und Zeiterfassung gehen auch ohne Netz, die Rücknahme geht
Stück für Stück. Funktionen planen ihr Personal über genau ein
Dienstleistungsprodukt, und Transport ist Nebenkosten.
- Begleit-App für Android, gebaut als Rentalars-App 1.0, mit der Serverseite
  in Rentalars: Anmeldung mit eigenem Token, Packlisten und
  Zeiterfassung ohne Netz, Abgleich nach der jüngeren Änderung (APP-001 bis
  APP-006, PCK-026, PCK-027, ZEI-020); ein Token erstellt nie mehr, als es
  selbst darf (AUT-021, Korrektur)
- Packen/Ausgabe und Rücknahme je Stück, auch im Wechsel; ein Balken zeigt, wo
  die Stücke sind; Teilprojekte als Reiter der Packliste (PCK-028 bis PCK-030)
- Projektnummern wieder ohne "P-" (ADM-014)
- Pflichtfelder gekennzeichnet, Kalender mit Ziffernblatt in jedem Datums- und
  Zeitfeld, API-Dokumentation im neuen Tab (UIX-035 bis UIX-037)
- Automatische Mails nennen Rentalars, Firma und Adresse (EML-045)
- Offene Fehlbestände unter den offenen Punkten, der andere Zeitraum
  schraffiert im Kalender, Vorschlag zum Erweitern des Mietzeitraums bei
  Phasen darüber hinaus (PRJ-098 bis PRJ-100)
- Antworten auf Einsatzanfragen sofort sichtbar, erneut anfragen erst nach
  geänderten Zeiten, neue Anfrage bei neuen Zeiten (PER-033, PER-034)
- Farben im Personalplan, Reihenfolge und Voreinstellungen der Planung,
  Materialauslastung mit Tagen und Wochen (VFG-027 bis VFG-029)
- Weitere Anforderungen:
  Dienstleistungsprodukte 1:1 mit den Funktionen und nur in der
  Personalplanung, Nebenkosten als eigene Produktart, im Produktformular erst
  die Art, dann die Kategorie, vorhandene Modelle zuordnen (PRD-044 bis
  PRD-046); höherer Satz ab einer Stundengrenze je Tag, "nach Aufwand" als
  Voreinstellung, Funktionen als Startdaten (PER-035 bis PER-037); Lieferant
  einer Zumietung per Eingabe und Status "offen", Zeitplanung ohne Kasten
  "Veranstaltungsort" und mit Zeitstrahl, Reiter "Überblick" und Packliste vor
  Korrespondenz, Wiedervorlage, Zumietung mit Korrespondenz und Dokumenten
  (PRJ-101 bis PRJ-106); deutliche Balken in den Zeitstrahlen (VFG-030; dazu
  die Korrektur des Personalplans, VFG-023); Hersteller und Produkt per
  Eingabe, Gewicht, Maße und Leistung im Modell, "Beschreibung",
  Rechnungsdaten, Seriennummern und Start-ID bei neuen Exemplaren, Modell als
  Produkt, Hauptlager (MAT-048 bis MAT-052); Filter auf jeder Breite
  eingeklappt (UIX-038); "Antwort auf Einsatzanfragen" in den
  Grundeinstellungen (ADM-015); Postfächer löschbar (EML-046)

Stufe 8 – Service, Karten, Zuschläge
Ergebnis: Ein Projekt lässt sich nachträglich gliedern und im Chat
besprechen, ein Servicefall braucht keine Planung, Adressen haben Karte und
Route, Personal hat Zuschläge und Spesen, und Rentalars antwortet auf
Wunsch selbst – auch auf einem Raspberry Pi. Servicefälle haben
Beteiligte und spontane Zeiten, ein Zeitraum lässt sich auf mehrere
Funktionen teilen, Zuschläge passen in jedem Land. Rentalars schließt, was eine Code-Prüfung fand – API,
Verbindungen nach außen, HTTPS, Offline-Abgleich und Chat. Adresse und Zertifikat lassen sich aus der Oberfläche
vorbereiten, Rentalars spricht Deutsch und Englisch, fasst die
Korrespondenz zusammen – auf Wunsch mit einer lokalen KI –, Servicefälle
können warten, und jede Spalte lässt sich gruppieren. Die
Begleit-App gleicht Projekte, Servicefälle und die eigenen Daten nach der jüngeren
Änderung ab, die Crew packt mit ihr in ihren Projekten, Fehlbestände
werden gemeldet, wann der Betrieb es einstellt, und die lokale KI
antwortet ohne Denkmodus, Stück für Stück und mit geschätzter Dauer.
Rentalars erinnert an Rechnungen, zeigt die Profitabilität von
Projekten und Material bis zum einzelnen Exemplar, druckt die drei
Etiketten des Betriebs aus dem Browser, macht aus einer Defektmeldung einen
Servicefall und hält Telefonate als Notizen in der Korrespondenz fest.
- Projekte: nachträglich in Teilprojekte gliedern, eine Teilgruppe wird
  Teilprojekt (PRJ-050); Servicefälle als eigene Art von Projekt (PRJ-090);
  Showfiles als Projektdateien (PRJ-089); Chat im Projekt, auch für die Crew
  (UIX-010)
- Planung: Phasen und Zeiträume im Zeitstrahl ziehen (VFG-026)
- Karten: Routenlink zu Google Maps an Adressen (UIX-033), zoombare Karte von
  OpenStreetMap erst nach einem Klick (UIX-034), Fahrten eines Projekts mit
  Routenlinks, ohne Entfernungen (PRJ-097)
- Automationen mit Auslösern, etwa eine Eingangsbestätigung (ADM-013);
  Rechnungen abschaltbar (DOK-014)
- Personal: Zuschläge für Nacht, Sonn- und Feiertag auf Preis und Kosten
  (PER-009); Hinweise bei auffälligen Zeiten (ZEI-018); Spesen und
  Fahrtkosten je Projekt (ZEI-019)
- Betrieb: Raspberry Pi 4 oder 5 mit Ubuntu Server für den Raspberry Pi oder
  Raspberry Pi OS (NFA-070)
- Weitere Anforderungen:
  Alias-Adressen eines Postfachs mit eigener Behandlung und Absender für
  Servicefälle, kein "gesendet" ohne Mailserver (EML-047, EML-048; EML-006
  um "nur als gelesen markieren" ergänzt); Anfragen als Projekt anlegen, mit
  Vorschlägen und Mehrfachauswahl, Beteiligte eines Servicefalls, Uhrzeit
  der Wiedervorlage (PRJ-107 bis PRJ-109); Ziehen, Zeiten beim
  Darüberfahren, Schraffur und rot ausgefüllte Konflikte im Personalplan,
  stündliche Linien und doppelter Scrollbereich der Zeitstrahlen, Reiter
  "Wiedervorlagen" (VFG-031 bis VFG-034); Kategorien und "In der App" bei
  den Benachrichtigungen, Gruppieren und mehr in jeder Tabelle, kein
  "Zurück" auf Seiten der Hauptnavigation, nur ein Symbol in Datumsfeldern
  (UIX-039 bis UIX-042); spontane Zeiten auf Servicefälle und Hinweis auf
  die Begleit-App, mehrere Funktionen in einem Zeitraum, Stundenlohn und
  Kopieren unter Meine Zeiten, Arbeitsweg bei Fahrtkosten (ZEI-024 bis
  ZEI-027; ZEI-018 zentral abschaltbar); Verfügbarkeit in der Woche
  markieren, Zuschläge für jedes Land (PER-039, PER-040)
- Weitere Anforderungen und eine Code-Prüfung (Oktober 2026):
  interne Ziele gesperrt, Zugangsdaten nur
  an denselben Server, im Betrieb nur HTTPS (NFA-071 bis NFA-073);
  Idempotenz an Aufrufer und Rechte gebunden, Versionsprüfung in einem
  Schritt (API-010); Offline-Abgleich mit Versionen des Servers und
  Änderungs-IDs, Webhook "zurück" nur bei mehr, GET schreibt nichts
  (PCK-027); Lesestand und Änderungsstempel im Chat (UIX-010); Mails ohne
  Kennung nur ab einem Zeitpunkt (EML-049); Personal im Zeitstrahl der
  Zeitplanung wie im Personalplan (VFG-035); Personal je Phase ändern und
  offene Plätze besetzen, Fahrten anpassen (PRJ-110, PRJ-111); "Meine
  Einsätze" als erster Reiter von Mein Bereich (UIX-043); jede Spalte
  sortierbar, Filter überall eingeklappt (UIX-015, UIX-038, UIX-040);
  Routenlinks ab dem Standort, Kacheln mit Referer (UIX-033, UIX-034);
  Kunde im Servicefall Pflicht (PRJ-090); Showfiles im Hinweis der
  Dokumente (PRJ-089); englische Namen auch in der Datenbank (NFA-061)
- Weitere Anforderungen:
  Adresse und Zertifikat aus der Oberfläche, angewendet mit einem Befehl
  per SSH ("Nur Befehl anzeigen", ADM-016); Deutsch und Englisch – die
  Oberfläche je Person, die Dokumente für Kunden je Betrieb, das Handbuch
  in beiden Sprachen, in der Anwendung in der Sprache der Person (UIX-029);
  Zusammenfassung der
  Korrespondenz mit einer einschaltbaren lokalen KI und ohne KI als
  Kurzübersicht (EML-040, EML-044); Schnittstelle für KI je Verwendung,
  anfangs aus, mit Warnung bei Diensten in der Cloud und Protokoll ohne
  Inhalt, erste weitere Verwendung "Antwortentwurf für Mails" (ADM-017);
  Status "wartet", "wartet auf Schließen" und "Rückstand" eines
  Servicefalls mit Wiedervorlage (PRJ-112; PRJ-105, PRJ-109) und Regeln
  dazu in den Automationen (ADM-013); Gruppieren nach jeder eingeblendeten
  Spalte (UIX-044, UIX-040); die lokale KI des Betreibers als erlaubtes
  Ziel (NFA-071)
- Weitere Anforderungen und Anforderungen der Begleit-App:
  Änderungszeit je Feld eines Projekts und des Status eines Servicefalls, Abgleich nach der
  jüngeren Änderung (PRJ-113, PRJ-114); eigene Personaldaten,
  Abwesenheiten und Einsätze über die API, Namen für die Einsatzsicht,
  Version des Servers, Benachrichtigungen der App, Bezahlung je
  Zeiteintrag (API-015, API-016); Meldung der Fehlbestände mit Uhrzeit,
  Abstand und Vorlauf (VFG-036, UIX-005); Menü als Schublade auf dem
  Smartphone, nur bis 900 Pixel (UIX-045); die Rolle Crew packt in ihren
  Projekten, Material nachtragen nur mit Recht auf das Projekt oder Packen
  für alle Projekte (PCK-013, Kapitel 4); das Token der App mit E-Mail
  (APP-001); dieselbe Korrespondenz in Projekt und Servicefall
  mit dem Kasten "Zusammenfassung" (EML-050); Linien der Zeitstrahlen
  genau an den Stunden (VFG-033); Reiter "Überblick" im Servicefall
  (PRJ-090); Funktion bei der Zeiterfassung nie leer (ZEI-007); Zuschläge
  nur für Personalpositionen (PER-009, PER-040); lokale KI ohne Denkmodus,
  gestreamt, mit gemessener Geschwindigkeit, Prüfung des Prozessors,
  kleinerem Modell und `rentalars ai refresh` nach jedem Update (EML-040,
  ADM-017); englische Bezeichnungen der Felder (UIX-029)
- Weitere Anforderungen:
  Erinnerung an die Rechnung, "Rechnung gestellt" und "keine Rechnung"
  (DOK-015); Preis und Kosten je Stunde in der Ersteinrichtung (ADM-018);
  Profitabilität je Monat, Kunde und Projektleitung, Ertrag je Produkt und
  Exemplar (PRJ-115, MAT-053); Kaufsets (MAT-054), Modell in der Ansicht
  eines Exemplars (MAT-055), drei Etiketten im Layout des Betriebs aus dem
  Browser (MAT-056; MAT-026); aus einer Defektmeldung ein Servicefall oder
  eine Anfrage, interne Servicefälle (MAT-057; MAT-023, ADM-013, PRJ-090);
  netto oder brutto, "#0802" und "#0851" beim Import (IMP-014 bis
  IMP-016); Einstellungen nach Themen, Fuß der Seitenleiste, Aktionsleiste
  erst bei Auswahl (UIX-046 bis UIX-048); Notizen in der Korrespondenz,
  KI-Zusammenfassung eingeklappt (EML-051, EML-050); Adressen der Seiten
  bereinigt (NFA-074)

Stufe 9 – Logistik und Wünsche
Ergebnis: Fahrzeuge und Anhänger werden je Projekt unter dem Personal
disponiert, je Fahrt mit Kilometern und Anhänger abgerechnet – mit dem
Anhängerzuschlag, sobald ein Anhänger dranhängt –, und der Fuhrpark steht
mit Sitzplätzen und Verfügbarkeit in der Materialverwaltung.
- Bereich "Logistik" in der Planung unter dem Personal, nicht als
  Materialpositionen (LOG-001); Fuhrpark in der Materialverwaltung mit
  Sitzplätzen min. und max., Verfügbarkeit über alle Projekte (LOG-002 bis
  LOG-004)
- Abrechnung: KFZ je Kilometer, Anhänger je Tag oder Kilometer, Sätze im
  Produkt, im Projekt anpassbar; Anhängerzuschlag automatisch je Fahrt mit
  Anhänger (LOG-005, LOG-006)
- Fahrten des Projekts mit Fahrzeug, Anhänger und Kilometern (LOG-007);
  Personal je Fahrzeug mit Fahrer (LOG-008)
- Kalkulation und Preisübersicht mit eigenem Bereich Logistik, interne
  Kosten, Dokumente (LOG-009 bis LOG-011)
- Abgeleitet: Fahrerlaubnis, Anhängelast, Fristen der Fahrzeuge, API,
  Übernahme von Fahrzeugen, Auslastung des Fuhrparks; Routenberechnung KANN (LOG-012 bis
  LOG-018); die Logistik folgt dem Projekt, beim Duplizieren und in
  Vorlagen (LOG-019)
- Weitere Wünsche: Monatsrechnung für Servicefälle
  (DOK-016), Import als Vorschau (IMP-011), Absender nach Rolle und
  Signatur je Postfach (EML-052, EML-026, EML-003), Anfragen von Hand
  (EML-053), Ertrag je Modell (MAT-058), Pauschale unter "Meine Zeiten"
  (ZEI-028), Hinweis bei geänderten Anmeldedaten (AUT-030), Vorlagentexte
  auf Englisch oder Deutsch (DOK-018), Urhebervermerk (NFA-075)
- Kauf
  einpflegen mit Rechnung (MAT-061, MAT-062), Exemplare (MAT-059, MAT-060,
  MAT-063, MAT-064), Etiketten (MAT-065, MAT-066), Produkte (PRD-047 bis
  PRD-051), Sets in der Auslastung (VFG-037), Rechte (AUT-031 bis
  AUT-034), Personal (PRJ-117, PRJ-118, PER-041, VFG-038), Freigabe der
  Zeiten (ZEI-029 bis ZEI-031), Buchhaltung (DOK-019, DOK-020), neue Phase
  (PRJ-116)
- Audits und
  To-Dos (MAT-067 bis MAT-070), eigene Felder (MAT-071 bis MAT-073), Fotos
  und Videos im Chat (UIX-049, NFA-076), Schloss (EML-055), Zugriff
  (AUT-035), Projekte (PRJ-119 bis PRJ-121), Kalender (VFG-039), Zusage
  (PER-042), Tabellen und Formulare (UIX-050, UIX-051), Export (IMP-017),
  Altlasten (NFA-077)
- Kauf
  einpflegen (MAT-074 bis MAT-076), Schutzklasse und elektrische Prüfung
  (MAT-077, MAT-078), Audit (MAT-079), Kalender-Links (VFG-040),
  Benachrichtigungen (UIX-052), Automationen (ADM-019), Fuhrpark (LOG-020)
- Deinstallation
  (NFA-078), Seriennummern, Etiketten (MAT-084, MAT-085), Produkt aus mehreren
  Stück (PRD-052), Ansprechpartner (KND-011), Rabatte und Funktionen (PER-044,
  PER-045), Projekte (PRJ-124 bis PRJ-128), Dokumente (DOK-021, DOK-022),
  Oberfläche (UIX-053 bis UIX-055)
- Standardrechte
  der Rollen (AUT-036), Lagerplatz (MAT-080), Prüfungen (MAT-081 bis
  MAT-083), Zusagen im Postfach (PER-043), Kundenname (PRJ-122), Gesamtrabatt
  (PRJ-123)

Stufe 10 – Weitere Erweiterungen
Ergebnis: Was als Möglichkeit festgehalten ist, kommt einzeln und nach Bedarf;
vorneweg der Verzeichnisdienst. Stufe 9 ist die Logistik. ADM-016
und UIX-029 gehören zu Stufe 8, ebenso die
Zusammenfassung der Korrespondenz durch ein lokal laufendes KI-Modell
(EML-040, EML-044).
- Anmeldung über LDAP bzw. Active Directory, Gruppen als Rollen (AUT-029),
  und über einen externen Identitätsdienst mit OIDC oder SAML (AUT-007)
- Aus Stufe 6 übernommen, je KANN:
  - Scan beim Packen und bei der Rücknahme, stets freiwillig, und Aufruf
    eines Exemplars durch Scannen (MAT-027, PCK-010, PCK-011, UIX-006)
  - Qualifikationen als Voraussetzung (PER-015)
  - Web-App auf dem Startbildschirm (UIX-007)
  - Kalender-Feeds für Projekte (API-013)
  - OAuth 2, mehrere Kürzel, Ergänzungen am Kürzel, nachträgliches
    Zuordnen (EML-004, EML-016, EML-017, EML-033); weitere Postfächer und
    die Signatur je Postfach (EML-003, EML-026) gehören zu Stufe 9
  - Kundenpreise, Zubehör- und Ersatzvorschläge (PRD-018, PRD-023,
    VFG-015), verbautes Mengenmaterial (MAT-040)
  - Bereitstellung als Container (NFA-016); der Import als Vorschau
    (IMP-011) gehört zu
    Stufe 9. Die Erfassung ohne Netz (ZEI-020) kam mit der App in Stufe 7;
    Zuschläge, Chat, nachträgliches Gliedern, Hinweise bei auffälligen
    Zeiten und Spesen (PER-009, UIX-010, PRJ-050, ZEI-018, ZEI-019) kamen in
    Stufe 8.
- Festgehalten, je KANN: Funktionen
  bei den Produkten, Produkte und Services getrennt (PRD-042);
  Benachrichtigung über Fehlbestände und offene Punkte vor Projektbeginn
  (UIX-028); KI-Vorschläge für Projektvorlagen (PRJ-091, unter
  Einstellungen → KI als "später" genannt). Die übrigen vier Notizen
  (DOK-014, VFG-026, PRJ-089, PRJ-090) kamen in Stufe 8, ebenso vier
  weitere (UIX-033, UIX-034, PRJ-097, ADM-013) und NFA-070;
  Oberfläche auf Deutsch oder Englisch (UIX-029) und die KI-Zusammenfassung
  von Korrespondenzen (EML-044, mit EML-040) kamen in Stufe 8.
- Festgehalten, je KANN: Freie
  Kräfte nennen in einer Einsatzanfrage ihren Preis selbst (PER-038). Adresse
  und Zertifikat im Browser (ADM-016) kam in Stufe 8.
- Festgehalten, je KANN: Vertrag
  je Kunde für die Monatsrechnung (DOK-017); Textbausteine je Postfach
  (EML-054). Die Monatsrechnung selbst (DOK-016)
  kam in Stufe 9, ebenso der Import als Vorschau (IMP-011) und
  Signatur und Absender je Postfach (EML-026, EML-003).


Stufe 10 – Anbindung des Rentalars Gateway
- Verbinden, Verbindungsdienst, Prüfreihenfolge, Protokoll RGW1, Koppeln, Geräte, Token am Gerät,
  Anschrift je Gerät, Medien und Umzug, Schlüssel in der Sicherung (GWL-001 bis GWL-010)
- Kabel-Etikett mit vollständigem QR-Code (MAT-089)

Stufe 10 – Buchhaltung vervollständigen
- Validierung der E-Rechnung, GoBD-Archiv, Versand der strukturierten Rechnung, EÜR, Prüfbarkeit (DOK-042 bis
  DOK-046), Zahlungen und offene Posten (DOK-048), ZUGFeRD / Factur-X (DOK-049)

Stufe 10 – Vorlagen bearbeiten, Kontoauszüge, Guthaben
- Inhalt von Projektvorlagen bearbeiten, auch über die API (PRJ-135, PRJ-136)
- Kontoauszug-Import mit Zuordnungsvorschlägen (DOK-050), unveränderliche Zahlungen im Modell (DOK-051), Finanzamt
  in der EÜR (DOK-052), Guthaben (DOK-053), Prüfer-Export im Hintergrund (DOK-054)

Stufe 10 – Geänderte Produkte in Anfragen und Optionen
- Erkennen, Hinweis auf jeder Seite des Projekts, Übernehmen (PRJ-137), Benachrichtigung (PRJ-138), Produktseite und API (PRJ-139)

Stufe 10 – Absender der Antwort, Buchhaltung ausblendbar
- Antwort auf Einsatzanfragen nur von der angeschriebenen Adresse (PER-046)
- Buchhaltung ausblenden, eigener Kasten "Buchhaltung und Rechnungswesen" (DOK-055)

Stufe 10 – Prüfung vor der Veröffentlichung
- Seite "Über Rentalars" mit den Lizenzhinweisen (UIX-062); Zusatzbestimmung gilt nur beim Weitergeben (NFA-075, UIX-031)
- Korrekturen: Rechnungsnummern (ADM-003), freie Belege (DOK-022), EÜR und GWG (DOK-045, MAT-086), Reverse Charge und
  E-Rechnung (DOK-006, DOK-042), Absenderprüfung (PER-046), Miettage über die Zeitumstellung (PRJ-005), Überbuchung
  (VFG-002, PCK-019), Produktänderungen in bestätigten Projekten (PRJ-139), Zwei-Faktor-Sperre (AUT-005), keine Staffel
  (PRD-034), Ausgabe rückgängig (PCK-025), Buchhaltung aus (DOK-055), Dateigrenzen beim Import (IMP-001), Server (NFA-032)

Stufe 10 – Sicherheitslücken
- Bibliotheken und Bildformate (NFA-081), Anmeldung hinter einem Vorschaltserver (NFA-082), Weiterleitungen (NFA-083),
  Absender von Antworten per Mail bestätigen (EML-057)
- Geändert: Platzhalter-Schlüssel, Sicherung und Wiederherstellung als root (NFA-032), leere Zeilen im Import (IMP-001),
  Nur-Lese-Tokens (AUT-021), Lieferantenkarten (UIX-033, PRJ-101), Absender (PER-046)

Stufe 10 – Logik, Bedienung und Layout
- Einheitliche Begriffe, Schreibweisen und Bedienung (UIX-063), Darstellung auf dem Telefon und im schmalen Fenster (UIX-064)
- Geändert: Status "Bestätigt – Preise und Einzelheiten offen" (PRJ-008), Name des Mailservers (EML-057), Konto über die API (AUT-009),
  Exemplar löschen und verkauftes Mengenmaterial (MAT-040), Führerschein (LOG-012), Stunden über die Zeitumstellung (ZEI-002),
  Anonymisieren und Mails (EML-031), nachgetragene Prüfung (MAT-031), Sperrzeiten und Buchungssperre (VFG-002)

Stufe 10 – Apps im Browser koppeln, Gateway im Selbsttest, Fotos neben den Daten
- Keine neue Anforderung; Geräte des Gateways in der Weboberfläche (GWL-011) und Eintrag im Selbsttest (GWL-014), beide aus Stufe 11
  in Stufe 10; Kasten „Fotos“ schmal neben den Daten (MAT-090)
- Entfallen: Abschnitt 5.19 (Präfix LUE, 13 vorgemerkte KANN-Anforderungen)

Stufe 10 – Servicefall, Rechteinhaber, Vorbereitung der Veröffentlichung
- Keine neue Anforderung; neuer Ansprechpartner (PRJ-140) auch im Servicefall, Rechteinhaber eingetragen (UIX-062)

Stufe 10 – Fotos, Ansprechpartner, Reiter
- Fotos an Modell und Exemplar (MAT-090), neuer Ansprechpartner im Projektformular (PRJ-140), Bilder und Videos stets neu rendern, der
  Standort bleibt (NFA-084)
- Geändert: Reihenfolge der Reiter der Materialverwaltung (UIX-013), Fotos im Chat (UIX-049), Dateien des Materials (MAT-017),
  Defektmeldung (MAT-023), Spesenbeleg (ZEI-019)

Stufe 11 – Vorgemerkt, je KANN
- Anbindung des Gateways ausbauen: nur über das Gateway (GWL-012), Sicherheitsereignisse (GWL-013); Geräte in der
  Weboberfläche (GWL-011) und Eintrag im Selbsttest (GWL-014) sind gebaut


## 11. Abnahmeszenarien (Auszug)

Szenario 1 – Produkt aus mehreren Herstellern
- Gegeben: Produkt K-005 "XLR-Kabel 5 m" mit 4 Instanzen von Hersteller A und
  5 Instanzen von Hersteller B.
- Dann zeigt das Produkt einen Bestand von 9.
- Wird eine Instanz auf "defekt" gesetzt, zeigt das Produkt 8 einsatzfähige.

Szenario 2 – Verfügbarkeit über Zeiträume
- Gegeben: Bestand 9. Projekt P1 (bestätigt) bucht 6 Stück vom 10. bis 12.
- Wenn Projekt P2 für den 11. bis 13. dasselbe Produkt anfragt, zeigt das
  System 3 frei.
- Wenn P2 4 Stück einträgt, warnt das System mit Fehlmenge 1. Die Position
  lässt sich speichern, ist als Fehlbestand markiert, und das System schlägt
  eine Zumietung über 1 Stück für den 11. bis 13. vor.
- Wird der Vorschlag angenommen, entsteht eine verknüpfte Zumietposition
  (Kategorie E); der Preis für den Kunden ändert sich dadurch nicht.
- Danach belegt P2 nur noch 3 Stück aus eigenem Bestand: Ein drittes Projekt
  im selben Zeitraum sieht 0 frei, und die Engpassliste zeigt keinen Engpass
  mehr.
- Ohne Pufferzeit (Voreinstellung): Wenn P2 erst am 13. beginnt, sind 9
  frei. Mit einem Tag Pufferzeit sind am 13. nur 3 frei, ab dem 14. wieder 9.

Szenario 3 – Artikelnummer
- "K-005", "L-0142" und "D-001" werden angenommen.
- "X-001" wird abgelehnt, solange es keine Kategorie mit dem Kürzel X gibt.
  Nach Anlegen der Kategorie "P – 3D-Druck" wird "P-001" angenommen.
- "K005", "K-05", "5-001" und "-001" werden mit Fehlermeldung abgelehnt.
- Eine bereits vergebene Nummer wird abgelehnt.

Szenario 4 – Stundensatz je Funktion
- Gegeben: Person A mit Funktion Tontechnik zu 35,00 und Stagehand zu 20,00.
- Wird A im Projekt als Tontechnik eingeplant, steht 35,00 an der Position.
- Erfasst A 4 Stunden als Stagehand im selben Projekt, wird der Eintrag mit
  20,00 bewertet.
- Wird der Satz Tontechnik später auf 38,00 erhöht, bleiben bestehende
  Positionen und Zeiteinträge unverändert.

Szenario 5 – Schnelle Zeiterfassung
- Eine Person öffnet auf dem Smartphone die Zeiterfassung, sieht ihr heutiges
  Projekt mit vorbelegter Funktion, trägt Beginn und Ende ein und speichert –
  ohne weitere Seite aufzurufen.
- Ein zweiter Eintrag mit überlappender Zeit wird abgelehnt.

Szenario 6 – Rechte
- Ein Nutzer ohne Recht auf Personalverwaltung sieht das Modul nicht und
  erhält bei direktem API-Aufruf eine Ablehnung.
- Ein Nutzer mit "nur zugeordnete Projekte" sieht in Liste, Suche und API
  ausschließlich seine Projekte.
- Ein Nutzer ohne Preisrecht sieht Projekte ohne Preise und Stundensätze.
- Ein Crewmitglied mit Personalposition sieht Einsatzdaten und Packliste des
  Projekts, aber weder Preise noch Korrespondenz.

Szenario 7 – Packliste
- Für ein Projekt mit 12 Positionen in 3 Gruppen wird eine Packliste als PDF
  erzeugt; sie enthält alle Positionen mit Artikelnummer, Bezeichnung und
  Menge, gruppiert, ohne Preise.

Szenario 8 – Import
- Eine Tabelle mit den 13 Materialspalten und 200 Zeilen wird im Probelauf
  geprüft; fehlerhafte Zeilen werden mit Zeilennummer und Grund gemeldet;
  nach dem Import existieren die erwarteten Modelle und 200 Instanzen.

Szenario 9 – Teilgruppen mit Preisen
- Gegeben: Ein Projekt mit der Teilgruppe "Licht Front-Traverse" (3
  Positionen, zusammen 420,00), der Teilgruppe "Licht Rear-Traverse" (2
  Positionen, zusammen 310,00) und einer Position ohne Teilgruppe (50,00).
- Dann zeigt die Planung die Zwischensummen 420,00 und 310,00, den Betrag
  ohne Teilgruppe 50,00 und die Projektsumme 780,00 netto.
- Die Preisübersicht im Browser zeigt dieselben Teilgruppen, Summen und – bei
  gewählter Detailansicht – alle Positionen; Beträge lassen sich kopieren.
- Erhält "Licht Rear-Traverse" 10 % Rabatt, zeigt sie 279,00 und das Projekt
  749,00.
- Eine als "optional" gekennzeichnete Teilgruppe "Nebel" (80,00) wird mit
  Preis gezeigt, zählt aber nicht zur Projektsumme.
- Steht derselbe Scheinwerfer (Bestand 6) mit je 4 Stück in beiden
  Teilgruppen, meldet das System eine Fehlmenge von 2.
- Ein Nutzer ohne Preisrecht sieht die Teilgruppen ohne Beträge.

Szenario 10 – Installation
- Auf einem frisch installierten Ubuntu Server (aktuelle LTS-Version, 4
  Kerne, 8 GB RAM) führt die Anleitung bzw. das Skript in unter 30 Minuten zu
  einer per HTTPS über NGINX erreichbaren Anwendung mit angemeldetem
  Administrator.
- Auf dem Server laufen ausschließlich NGINX, die Anwendung und MariaDB.
- Der Aktualisierungsbefehl hebt die Installation auf die nächste Version;
  alle Daten bleiben erhalten, die vorherige Sicherung ist vorhanden.
- Das gilt unter jeder unterstützten Ubuntu-Version: 24.04 LTS und 26.04 LTS
  (NFA-063).
- Haben die Skripte des Pakets ihr Ausführungsrecht verloren – auf einem
  anderen Rechner entpackt, über eine Freigabe kopiert –, laufen Installation
  und Aktualisierung trotzdem, und der Befehl `rentalars` ist danach da
  (NFA-069).

Szenario 11 – Leistung auf dem Referenzsystem
- Gegeben: Testdaten mit 100 Nutzerkonten, 20.000 Instanzen und 1.000
  Projekten; zwei Nutzer arbeiten gleichzeitig.
- Ein Projekt mit 500 Positionen in 20 Teilgruppen öffnet in unter einer
  Sekunde; das Hinzufügen einer Position einschließlich
  Verfügbarkeitsprüfung antwortet in unter einer halben Sekunde.
- Der belegte Arbeitsspeicher bleibt dabei unter 4 GB.

Szenario 12 – E-Mail-Zuordnung
- Gegeben: Projekt 2026-0042 mit dem Kürzel [RL#2026-0042] und ein
  eingerichtetes Postfach.
- Eine Mail mit dem Betreff "AW: Bühnenplan [RL#2026-0042]" und
  PDF-Anhang erscheint nach dem nächsten Abruf in der Korrespondenz des
  Projekts. Der Anhang ist abrufbar und lässt sich in die Projektdateien
  übernehmen.
- Eine Mail mit "[rl# 2026-0042]" im Betreff wird ebenso zugeordnet.
- Ist P-2026-0042 die frühere Nummer des Projekts, wird auch eine Antwort mit
  [RL#P-2026-0042] im Betreff ihm zugeordnet (ADM-014).
- Eine Mail ohne Kürzel bleibt ungelesen und unverschoben im Posteingang und
  erscheint nicht in Rentalars. Eine Mail mit [RL#2026-9999] bleibt
  ebenfalls unangetastet und steht unter "Projekte" im Reiter "Anfragen"
  (EML-042).
- Die zugeordnete Mail liegt danach als gelesen im eingestellten Ordner; ein
  erneuter Abruf erzeugt keinen zweiten Eintrag.
- Eine aus dem Projekt gesendete Mail trägt das Kürzel im Betreff; die
  Antwort des Kunden wird ohne Zutun zugeordnet.
- Ein Nutzer ohne Zugriff auf das Projekt findet die Mail weder im Projekt
  noch über die Suche. Dasselbe gilt für einen Nutzer mit Projektzugriff,
  aber ohne das Recht für Korrespondenz.

Szenario 13 – Verbaute Exemplare
- Gegeben: Rack 0500 und das Produkt T-050 "Funkempfänger" mit den
  Exemplaren 0310, 0311 und 0312.
- Wird bei 0310 als Einsatz/Verbindung "0500" mit der Art "fest verbaut"
  eingetragen, zeigt das Rack 0310 als Inhalt, und T-050 hat einen frei
  planbaren Bestand von 2.
- Das Rack ist ein Einzelstück und wird bei der Ausgabe von selbst
  zugeordnet; 0310 gilt damit als mit ausgegeben.
- 0311 liegt "lose enthalten" im Case 0600. Ist das Case vom 10. bis 12.
  verplant, zeigt T-050 in diesem Zeitraum 1 frei, davor und danach 2.
- Wird 0311 für das Projekt herausgelöst, sind es wieder 2, und die Packliste
  des Case vermerkt den fehlenden Inhalt.
- Der Eintrag "0500 verbaut in 0310" wird als Kreisbezug abgelehnt, eine
  unbekannte ID ebenso.

Szenario 14 – Set und Einzelvermietung
- Gegeben: K-010 "XLR-Kabel 10 m" mit Bestand 9, T-010 "Aktivbox" mit
  Bestand 4, S-020 "Boxenstativ" mit Bestand 6. Das Set T-100 besteht aus je
  einem Stück davon.
- Ein Projekt bucht im selben Zeitraum 3 Sets und zusätzlich 5x K-010
  einzeln. Dann sind von K-010 8 belegt und 1 frei, von T-010 ist 1 frei.
- Ein viertes Set ist möglich; ein fünftes meldet je 1 Fehlmenge bei T-010
  und K-010.
- Die Packliste löst die Sets in ihre Bestandteile auf.

Szenario 15 – Personal über Dienstleistungsprodukt
- Gegeben: Die Funktion Tontechnik ist mit D-001 "Tontechniker, Stunde" zu
  45,00 verknüpft; Person A hat für Tontechnik den Stundensatz 35,00.
- Wird A für 8 Stunden eingeplant, zeigt die Position einen Preis von 360,00
  und – mit Preisrecht – interne Kosten von 280,00.
- Die Preisübersicht weist die 360,00 im Block Personal aus, nicht in einer
  Teilgruppe; der Stundensatz von A erscheint dort nicht.
- Ist für den Einsatz stattdessen eine Pauschale von 300,00 vereinbart,
  betragen die internen Kosten 300,00 unabhängig von den Stunden.
- Bei Abrechnung nach Aufwand und 9,5 freigegebenen Stunden beträgt der Preis
  427,50; bis zur Freigabe stehen die 360,00 als Schätzwert.

Szenario 16 – Übernahme der Excel-Tabelle
- Der Importbefehl liest die Tabelle im Probelauf und meldet Fehler mit
  Zeilennummer, ohne etwas zu schreiben.
- Nach dem Import trägt jedes Exemplar seine bisherige ID (0001 bis 1650);
  Verweise in "Einsatz/Verbindung" zeigen auf die richtigen Exemplare. Das
  nächste neu angelegte Exemplar erhält die ID 1651.
- Ein zweiter Lauf mit derselben Tabelle erzeugt keine Dubletten.

Szenario 17 – Tagesmiete, Staffel und Aufpreis
- Gegeben: L-010 "LED-Scheinwerfer" mit Tagesmietpreis 20,00; Staffel
  1 Tag = 1,0 und 2 Tage = 1,5.
- 4 Stück für 1 Miettag ergeben 80,00; für 2 Miettage 4 × 20,00 × 1,5 =
  120,00.
- Die Position weist 2 Miettage und den Faktor 1,5 aus; eine eigene
  Aufpreiszeile für die Staffel entsteht nicht.
- Hat die Kategorie L eine eigene Staffel mit 2 Tage = 1,6, ergibt dieselbe
  Position 128,00.
- Werden die Miettage der Position von 2 auf 1 gesetzt, rechnet sie sofort
  mit dem Faktor 1,0 neu: 80,00.
- Wird die Staffeltabelle geändert, rechnet die bestehende Position mit dem
  bisherigen Stand weiter, bis sie umgestellt wird.
- Der feste Aufpreis A-001 "Expresszuschlag" zu 50,00 erhöht eine Teilgruppe
  von 120,00 auf 170,00.
- Ein Produkt mit der Abrechnungsart "pauschal" zu 150,00 bleibt auch bei
  2 Miettagen bei 150,00.
- Ein Aufpreis von 10 % mit Bezug auf zwei Teilgruppen zu 420,00 und 310,00
  beträgt 73,00 und steht im Block Aufpreise des Projekts. Ändert sich eine
  der beiden Teilgruppen, rechnet er neu.

Szenario 18 – Eingeschränktes Konto und Freigabe
- Eine freie Kraft mit Konto sieht in der Projektliste nur Projekte, in denen
  sie eingeplant ist, und darin Zeit, Ort und Funktion – keine Preise, keine
  Korrespondenz, keine Stundensätze anderer.
- Ihre erfassten Zeiten stehen auf "eingereicht", bis die Projektleitung sie
  freigibt; danach sind sie gesperrt und gehen in die Nachkalkulation ein.
- Sie sieht die Packliste, den Namen des Kunden (ohne Link) und die Namen der
  Kollegen im selben Einsatz. Die
  Telefonnummer eines Kollegen sieht sie nur, wenn dieser sie freigegeben
  hat.

Szenario 19 – Verständlichkeit des Codes
- Die Suche nach "VFG-002" im Code führt zur Verfügbarkeitsberechnung. Ihre
  Beschreibung erklärt die Regel in Worten und an einem Zahlenbeispiel und
  begründet, warum die Spitze der Belegung zählt und nicht die Summe.
- Eine Person mit Python-Grundkenntnissen richtet anhand der
  Entwicklerdokumentation eine Entwicklungsumgebung ein und führt die Tests
  aus, ohne Rückfragen stellen zu müssen.
- Die automatische Prüfung schlägt an, wenn einer Funktion mit Fachlogik die
  Beschreibung fehlt.
- Zu jedem Abnahmeszenario dieses Kapitels gibt es einen gleich benannten
  Test.

Szenario 20 – Bestätigt mit offenen Punkten
- Ein Auftrag ist erteilt, die Aufbauzeiten fehlen noch: Das Projekt steht auf
  "Bestätigt – Einzelheiten offen" mit dem offenen Punkt "Aufbauzeiten". Das
  Material ist fest reserviert.
- Das Projekt erscheint in der Übersicht der Projekte mit offenen Punkten.
- Ist der Punkt erledigt, schlägt das System den Wechsel auf "Bestätigt" vor.

Szenario 21 – Ausgabe ohne Scan
- Drei Kabel K-005 werden durch Abhaken der Position ausgegeben, ohne ein
  Exemplar zu wählen oder zu scannen.
- Das Rack 0500 wird als Einzelstück beim Abhaken von selbst zugeordnet und
  erhält einen Eintrag in seiner Einsatzhistorie.
- Für die Kabel entsteht keine Einsatzhistorie je Exemplar; nichts wird
  deshalb blockiert oder angemahnt.


## 12. Entscheidungen und offene Punkte

### 12.1 Bereits entschieden

Material und Produkt

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Einsatz/Verbindung             | "verbaut in": stets die ID einer anderen Materialinstanz         | MAT-033 ff.          |
| Art der Verbindung             | "fest verbaut" und "lose enthalten"; beides kommt vor            | MAT-036, MAT-041     |
| Lose Inhalte                   | mit verplant, sobald das Case verplant ist; Herauslösen möglich  | MAT-036, MAT-042     |
| Verbindung beim Import         | jeder Eintrag mit Angabe wird als "fest verbaut" übernommen      | IMP-010              |
| Felder je Modell/Instanz       | Aufteilung wie in MAT-011                                        | MAT-011              |
| Kategoriespezifische Angabe    | eine je Kategorie, um weitere Felder erweiterbar                 | MAT-009, MAT-010     |
| Mengenmaterial                 | ja                                                               | MAT-005              |
| Material in mehreren Produkten | ein Einzelprodukt, zusätzlich in Sets                            | PRD-004, PRD-022     |
| Kategorien                     | eine gemeinsame Gliederung für Material und Produkte             | PRD-009              |
| Artikelnummer                  | Kürzel je Kategorie, erweiterbar; Ziffern mit Mindestlänge       | PRD-007, PRD-027     |
| Bestehende IDs                 | vierstellig fortlaufend (0001 bis 1650), Übernahme per Skript    | MAT-003, IMP-007 ff. |
| IDs über 9999                  | fünfstellig weiterzählen                                         | MAT-003              |

Preise

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Mietpreis                      | Tagesmietpreis; Abrechnungsart je Produkt wählbar                | PRD-013, PRD-014     |
| Staffel                        | anpassbar, auch je Kategorie; im Positionspreis eingerechnet     | PRD-015, PRD-034 f.  |
| Staffel-Startwerte             | 1 Tag = 1,0; 2 Tage = 1,5; Regel für längere Dauer bestätigt     | PRD-015, PRD-038     |
| Staffelfaktor                  | folgt den Miettagen; Teilprojekte mit eigener Mietdauer          | PRD-036, PRJ-044     |
| Aufpreise                      | fester Betrag und Prozentsatz                                    | PRD-031              |
| Bezug von Prozentaufpreisen    | Positionen, Teilgruppen, Personal oder gesamt; auch mehrere      | PRD-031, PRJ-058     |
| Miet- und Verkaufspreis        | beides an einem Produkt möglich                                  | PRD-017              |
| Steuer                         | 19 % (Voreinstellung) oder steuerfrei                            | PRD-016              |

Projekt und Disposition

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Projektstatus                  | acht Status; "Bestätigt" zweigeteilt (Einzelheiten offen)             | PRJ-008, PRJ-059     |
| Überbuchung                    | nur Warnung; die Planung bleibt möglich                          | PRJ-013              |
| Zumietung                      | über Kategorie E, mit Vorschlag bei Fehlmenge                    | PRJ-018, PRJ-054     |
| Kategorie E                    | Sammelkategorie für alles Externe, nicht untergliedert           | PRD-040              |
| Gedeckte Fehlmenge             | belastet den eigenen Bestand nicht                               | VFG-018              |
| Pufferzeiten                   | ja; Voreinstellung 0 Stunden                                     | VFG-005              |
| Packen                         | Abhaken genügt; Scan später und nie zwingend                     | PCK-009, PCK-020     |
| Teilgruppen                    | Rabatt, Pauschalpreis, optional/Alternative; bis drei Ebenen     | PRJ-037 bis PRJ-040  |
| Personal in Teilgruppen        | nein; Personal steht am Projekt bzw. Teilprojekt                 | PRJ-038              |
| Teilprojekte                   | eine Ebene; erben Kunde und Rechnungsdaten; Material wechselt    | PRJ-044 f., PRJ-060  |
| Angebote                       | extern; zunächst Ansicht im Browser, händische Übertragung       | PRJ-035, DOK-009     |
| Weitere Dokumente              | Auftragsbestätigung, Lieferschein, Rechnung perspektivisch       | DOK-003, DOK-006     |

Personal und Zeit

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stundensatz                    | interner Kostensatz; Kundenpreis über Kategorie D                | PER-008, PRJ-051     |
| Pauschalen                     | für Kosten, Kundenpreis oder beides; Tagessätze später           | PER-018, PER-009     |
| Personal nach Aufwand          | freigegebene Stunden × Preis des Dienstleistungsprodukts         | PRJ-061, ZEI-021     |
| Zeiterfassung                  | nur Projektzeiten, kein Arbeitszeitnachweis; mit Freigabe        | ZEI-012              |
| Freie Kräfte                   | eingeschränktes Konto; Packliste, Namen, freigegebene Kontakte   | AUT-023, PER-019     |
| Zeiten in der Zukunft          | nicht erfassbar; Zeiten werden erfasst, wenn sie geleistet sind  | ZEI-022              |
| Zeit ohne Projekt              | erfassbar; freigegeben erst mit zugeordnetem Projekt             | ZEI-023              |

E-Mail

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Postfach                       | ein Postfach über IMAP/SMTP                                      | EML-002, EML-003     |
| Kürzel                         | [RL#2026-0042]; Zuordnung zunächst nur zum Projekt               | EML-009              |
| Versand                        | ja                                                               | EML-024              |
| Nach dem Abruf                 | nur zugeordnete Mails verschieben; alle anderen unberührt        | EML-006, EML-013     |

Technik und Betrieb

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Grundlage                      | Eigenentwicklung                                                 | Kapitel 9            |
| Technikstack                   | Python mit Django hinter NGINX, MariaDB                          | Kapitel 9            |
| Oberfläche                     | vom Server erzeugte Seiten; API gleichwertig daneben             | API-002, UIX-009     |
| Code-Dokumentation             | muss erklären, was geschieht und warum                           | NFA-055 ff.          |
| Sprache im Code                | alles englisch, mit fester Übersetzungsliste                     | NFA-061, 2.1         |
| Eigene Rechte                  | Finanzen und Kundenkorrespondenz stets getrennt berechtigt       | AUT-019, AUT-025     |
| Lizenz                         | GNU General Public License, Version 3 oder später                | NFA-052              |
| Verbreitung                    | eine Instanz je Betrieb, kostenlos, selbst installierbar         | NFA-045, NFA-046     |
| Umgebung                       | nur Ubuntu Server mit NGINX; Installationsskript ist MUSS        | NFA-027, NFA-031     |
| Ubuntu-Versionen               | Skripte laufen unter Ubuntu Server 24.04 LTS und 26.04 LTS       | NFA-063              |
| Server                         | eigener Server mit Zertifikat; in der Testphase nur per VPN      | NFA-035, NFA-048     |
| Mengengerüst                   | 100 Konten, über 10.000 Exemplare, mehrere Hundert Projekte      | Abschnitt 3.2        |
| Buchhaltung                    | Lexware Office als Beleg; DATEV als Buchungsstapel               | DOK-011, DOK-012     |
| Erscheinungsbild               | dunkler Modus mit Farbwerten #EE591F, #EEEEEE, #727272 (Design-Token)       | UIX-008              |
| Navigation                     | ein Eintrag "Materialverwaltung" für Produkte und Material       | UIX-013              |
| Statuswechsel am Exemplar      | Grund wird abgefragt, bei "defekt" Pflicht; von dort nur drei Wege | MAT-044, MAT-045   |
| Verbindung von beiden Seiten   | "Verbaut in" am Exemplar, "Enthält" am Gerät; keine Kreise       | MAT-046              |
| Modell oder Exemplar wünschen  | interner Hinweis an der Position, findbar über die Produktsuche  | PRJ-064, PRJ-065     |
| Miettage einer Position        | folgen ihrem eigenen Zeitraum                                    | PRJ-062              |
| Packliste nach der Ausgabe     | Ausgegebenes ist "unterwegs", nicht fehlend                      | PCK-023              |
| Ersteinrichtung                | ohne Einrichtungsschlüssel nie erreichbar                        | NFA-064              |
| Vorhandener Datenbankserver    | möglich; nie root, nur Rechte auf genau diese eine Datenbank     | NFA-066              |
| Verschlüsselung                | bei der Installation wählbar; Notfall mit Wiederherstellungsschlüssel | NFA-067         |
| Nachträglich verschlüsseln     | an Ort und Stelle oder Umzug in neue Datenbank, beides mit Prüfsumme | NFA-068          |
| Preisübersicht ohne Positionen | jede Teilgruppe nennt zusammengefasst, was sie enthält           | PRJ-066              |
| Dokumente                      | unveränderlich am Projekt; eine falsche Rechnung wird storniert  | DOK-006, DOK-007     |
| Elektronische Rechnung         | XRechnung (UBL, EN 16931) zu jeder Rechnung und Stornorechnung   | DOK-006              |
| Import                         | eine Logik für alle Listen; Probelauf und Import im Hintergrund  | IMP-001, NFA-041     |
| Datenexport                    | JSON und CSV mit allen Dateien, ohne Passwörter und Geheimnisse  | IMP-006              |
| Schutz der API                 | Idempotency-Key, ETag/If-Match, 600 Aufrufe je Token und Minute  | API-010, API-011     |
| Listen                         | Spalten je Nutzer wählbar, Sortieren per Klick, CSV wie gezeigt  | UIX-015, IMP-005     |

Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Personal und Nutzer            | eins: jede Person meldet sich an, Personal ohne Anmeldung gibt es nicht | AUT-026       |
| Kalender der Einsätze          | Abo-Link und CalDAV, weil der Server oft nicht im Internet steht | PER-023              |
| Google Kalender                | liest den Abo-Link; Schreiben per CalDAV bräuchte OAuth          | PER-023              |
| Reihenfolge der Lieferung      | erst die Wünsche, dann Stufe 6                           | Kapitel 10           |
| KI-Zusammenfassung, LDAP       | LDAP Stufe 10; KI lokal, Stufe 8, einschaltbar | EML-040, AUT-029 |
| Verschlüsselung einschalten    | auf dem Server per Befehl, ohne Knopf in der Anwendung           | ADM-009, NFA-067     |
| Sicherung im Browser           | wie die nächtliche; verschlüsselt mit eigenem Schlüssel je Datei | ADM-010              |
| Adressen                       | Projektnummer und Artikelnummer; alte Links gelten weiter        | UIX-024              |

Stufe 6

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Umfang der Stufe 6             | nur SOLL; KANN nach Stufe 7, dann 8, 9 (0.21), 10 (0.23), 9 (0.24), seit 0.26 wieder Stufe 10 | Kapitel 10 |
| Externe Anmeldung              | zurückgestellt; mit LDAP in Stufe 10 (bis 0.18: 7, bis 0.20: 8, bis 0.25: 9, außer 0.23: 10) | AUT-007, AUT-029 |
| Postfach                       | eigener Anbieter über IMAP/SMTP; kein OAuth                      | EML-002, EML-004     |
| Buchhaltung                    | beides: Lexware Office und DATEV                                 | DOK-011, DOK-012     |
| Nummer eines Teilprojekts      | die des Gesamtprojekts mit Zähler: 2026-0042-1, 2026-0042-2      | PRJ-044              |
| Zeitraum eines Teilprojekts    | im Mietzeitraum des Gesamtprojekts; verschiebt sich mit ihm      | PRJ-044              |
| Status                         | je Teilprojekt; Storno des Ganzen storniert die Teile            | PRJ-044              |
| Abrechnung                     | Angebot, AB, Rechnung am Gesamtprojekt mit allen Teilen          | PRJ-045, PRJ-046     |
| Dokumente am Teilprojekt       | Lieferschein und Crew-Disposition                                | PRJ-048, DOK-003     |
| Rechte                         | gelten vom Ganzen aus; je Teil ersetzbar, auch durch "kein Zugriff" | PRJ-049           |
| Übernahme                      | durchgehend reserviert, ohne Puffer; einmal berechnet            | PRJ-060              |
| Übergabe beim Packen           | beim übernehmenden Teil gebucht; zählt beim früheren als zurück  | PRJ-048, PRJ-060     |
| Webhooks                       | signiert, minütlich mit Wiederholungen; ohne Preise              | API-012              |

Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Eigener Eintrag und Termin     | die neuere Angabe gilt, ohne Datum des Termins die strengere     | PER-027              |
| Termine des Kalenders          | eine eigene Ebene, bei jedem Lesen ersetzt; als Block gezeigt    | PER-027              |
| Serien                         | täglich, wöchentlich, monatlich; bis Datum oder n-mal            | PER-028              |
| Mein Bereich                   | Verfügbarkeit, eigene Zeiten, Personaldaten                      | UIX-026              |
| Freigeben und Auswertung       | Reiter von "Personal"; "Zeiterfassung" entfällt als Menüpunkt    | UIX-026              |
| Zurück                         | nicht auf Reitern, auf Seiten darunter; am Smartphone immer oben | UIX-027              |
| Erläuterungen                  | unter den Reitern, damit der Kopf gleich hoch bleibt             | UIX-027              |

Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Personal und Phasen            | Personal je Phase; Zeitraum folgt der Phase, Liste je Phase      | PRJ-080              |
| Stunden des Personals          | durchgehend: Mo 08:00 – Di 20:00 sind 36 Stunden                 | PRJ-073              |
| Packliste                      | Ausgabe je Artikel; "Unterwegs" erst, wenn alles draußen ist     | PCK-025, PCK-018     |
| Tagessatz                      | Feld an Person und Funktion und Abrechnung "je Tag"              | PER-029              |
| Sätze einer Person             | Stundensatz, Tagessatz und "gültig ab" sind freiwillig           | PER-029              |
| Kopf eines Projekts            | "Projekt bearbeiten" zuerst; Status als Auswahlliste             | PRJ-078              |
| Nächstes Dokument              | Anfrage, Option: Angebot; bestätigt: Auftragsbestätigung         | PRJ-078              |
| Nächstes Dokument, danach      | Unterwegs: Lieferschein; Wieder im Lager, Abgeschlossen: Rechnung | PRJ-078             |
| Dokument erstellen             | der Knopf öffnet den Reiter "Dokumente"; erstellt wird dort      | PRJ-078, PRJ-079     |
| Dokumente und Dateien          | ein Reiter; der Kasten "Dokument erstellen" bleibt               | PRJ-079              |
| Namen                          | "Zeitplanung" statt "Ablauf", "Gewinn aus dem Projekt"           | PRJ-080, PRJ-087     |
| Postfächer                     | mehrere; Aufgaben Korrespondenz und System; eines sendet         | EML-041              |
| Mails ohne Kennung             | je Postfach wählbar; als Anfragen unter "Projekte"               | EML-041, EML-042     |
| Höchster Rabatt                | auch je Produkt; gelten zwei Grenzen, zählt die strengere        | PRD-041              |
| Verknüpfte Kalender            | bis zu zehn je Person, zusammen eine Ebene "belegt"              | PER-031              |
| Standardwerte                  | bestehende Installationen bekommen nur, was fehlt                | ADM-011              |
| Einsatzübersicht in der Mail   | Sicht eines Kollegen, Kontakte nur soweit freigegeben            | PRJ-081              |

Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Status "Zurück"                | heißt "Wieder im Lager"; Wert in der API bleibt returned         | PRJ-093              |
| Phasen                         | "Planungen und Besprechungen" zuerst; "Packen"; "Nachbereitung"  | PRJ-092, PRJ-006     |
| Neue Phase in der Planung      | "Neue Phase …" in der Auswahl, Dialog wie beim neuen Kunden      | PRJ-094              |
| Dry Hire                       | Vorlage ohne Personal, bei Ersteinrichtung und Update angelegt   | PRJ-095              |
| Einsatzanfrage per Mail        | Antwort-Mail, der Server bleibt im eigenen Netz                  | PER-032              |
| Kundenmaterial im Lager        | Produkt in C "Fremdmaterial", Kunde als Eigentümer, mit Modell   | PRD-043              |
| Kundenmaterial im Projekt      | nur beim Eigentümer; mitgeführt, ohne Preis, auf der Packliste   | PRJ-096              |
| Frühere Projektnummern         | gelten weiter: Adressen, Mail-Kürzel, Suche, Liste, API          | ADM-014              |
| Filter über Listen             | einklappbar             | UIX-030              |
| Urhebervermerk                 | "von fld-vt.de" unter der Version und unter der Anmeldung        | UIX-031              |
| Firmenname                     | klein unter "Rentalars" in der Seitenleiste                      | UIX-032              |

Ausbaustufe 7: Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufen 7 und 8                 | nicht Genanntes geht nach Stufe 8                                | Kapitel 10           |
| Begleit-App                    | gebaut: SOLL in Stufe 7; die Serverseite gehört zu Rentalars     | APP-001 ff.          |
| Teilrücknahme                  | je Stück: Zurückgenommenes geht im Projekt nicht wieder hinaus   | PCK-028              |
| Rücknahme                      | abhaken, dann "Rücknahme buchen" – wie bei der Ausgabe           | PCK-028              |
| Name des Packens               | "Packen/Ausgabe"                                                 | PCK-028              |
| Phase über den Mietzeitraum    | erst nachfragen; "Planungen und Besprechungen" fragen nie        | PRJ-100              |
| Uhrzeit wählen                 | Ziffernblatt: erst die Stunde, dann die Minute                   | UIX-036              |
| Projektnummern                 | ohne "P-"                                                        | ADM-014              |
| Nummer mit "P-"                | gilt als frühere Nummer weiter                                   | ADM-014              |
| Neue Zeiten im Personal        | fragen von selbst neu an; in den Einstellungen abschaltbar       | PER-034              |
| Fußzeile                       | nur in Systemmails; die Korrespondenz trägt die Signatur         | EML-045              |
| Raspberry Pi                   | SOLL in Stufe 8                       | NFA-070              |

Ausbaustufe 7: Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Dienstleistungsprodukte        | bleiben; 1:1 mit den Funktionen, nur in der Personalplanung      | PRD-044              |
| Transport                      | keine Dienstleistung, sondern Nebenkosten: eigene Produktart     | PRD-045              |
| Höherer Stundensatz            | ab einer Grenze je Tag, für Preis und Kosten                     | PER-035              |
| Abrechnung des Personals       | voreingestellt nach Aufwand                                      | PER-036              |
| Funktionen als Startdaten      | acht; beim Update nur ohne jede Funktion                     | PER-037              |
| Name der Einsatzansicht        | Reiter "Überblick"; das PDF bleibt "Einsatzübersicht"            | PRJ-104              |
| Produktformular                | erst die Art, dann die Kategorie                                 | PRD-046              |
| Status einer Zumietung         | "offen" zuerst und voreingestellt; sonst nur mit Lieferant       | PRJ-101              |
| Filter über Listen             | auf jeder Breite zunächst eingeklappt                            | UIX-038              |
| Postfach löschen               | möglich; Mails und Mail-Protokoll behalten den Namen             | EML-046              |
| Antwort auf Einsatzanfragen    | unter Firmendaten und Grundeinstellungen                         | ADM-015              |
| Adresse und Zertifikat         | festgehalten; SOLL in Stufe 8                                    | ADM-016 |
| Preis freier Kräfte            | nur festgehalten: KANN in Stufe 10                               | PER-038              |
| Stufe 7                        | gebaute Wünsche sind SOLL in Stufe 7                             | Kapitel 10           |

Ausbaustufe 8

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufen 8 und 9                 | Stufe 8 ist je SOLL; der Rest geht nach Stufe 10                 | Kapitel 10 |
| Karten                         | OpenStreetMap, zoombar; Routen als Link zu Google Maps           | UIX-033, UIX-034     |
| Routen und Fahrten             | kein Routendienst, keine Entfernungen; Fahrten mit Routenlink    | PRJ-097              |
| Karte laden                    | erst nach "Karte anzeigen"; per Einstellung sofort               | UIX-034, NFA-050     |
| Koordinaten                    | Nominatim, vom Server einmal je Adresse gefragt und gespeichert  | UIX-034              |
| Kacheln                        | lädt der Browser von OpenStreetMap; "© OpenStreetMap-Mitwirkende" | UIX-034             |
| Eigener Kartenserver           | Adressen von Kachel- und Suchdienst in der Konfigurationsdatei   | UIX-034, NFA-032     |
| Chat                           | einer je Projekt; wer das Projekt öffnen darf, auch die Crew     | UIX-010, AUT-023     |
| Dummy-Projekte                 | heißen Servicefälle: eine eigene Art von Projekt                 | PRJ-090              |
| Zuschläge                      | Nacht, Sonn- und Feiertag für Preis und Kosten                   | PER-009              |
| Sätze der Zuschläge            | Voreinstellung nach § 3b EStG, jeder Wert änderbar               | PER-009              |
| Raspberry Pi                   | Ubuntu Server für den Pi und Raspberry Pi OS (Debian 13)         | NFA-070              |
| Automatische Antworten         | als Automation erlaubt, bewusst gegen EML-030; Schutz vor Schleifen | ADM-013, EML-030  |

Ausbaustufe 8: Weitere Anforderungen

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 8                        | Wünsche sind SOLL in Stufe 8                                     | Kapitel 10           |
| Alias-Adressen                 | Liste am Postfach; Adresse aus Delivered-To, X-Original-To, To, Cc | EML-047            |
| Mails ohne Kennung je Adresse  | nicht übernehmen, als Anfrage oder gleich als Servicefall        | EML-047              |
| Adresse "nur für Servicefälle" | Absender der Mails im Servicefall, sonst die des Postausgangs    | EML-047              |
| Eigene Adresse des Postfachs   | nach seiner Einstellung, außer sie steht in der Liste            | EML-047, EML-041     |
| Ohne Mailserver (Punkt 20)     | "nicht versendet – kein Mailserver eingerichtet", nicht gesendet | EML-048              |
| Mailserver                     | [email] host in der Konfiguration oder Postfach der Systemmails  | EML-048, EML-041     |
| rentalars@localhost            | nur Absender der Konfigurationsdatei, wenn nichts eingetragen ist | EML-048             |
| Nach der Zuordnung             | auch "nur als gelesen markieren"; Voreinstellung bleibt          | EML-006              |
| Mehrere Funktionen             | Anteile eines Zeitraums mit Funktion, Position, Stunden und Satz | ZEI-025              |
| Rechnen mit Anteilen           | wie mit Einträgen; kein zweiter Weg für Summen und Kosten        | ZEI-025              |
| Zuschläge auf Anteile          | nach den Stunden verteilt                                        | ZEI-025, PER-009     |
| Prüfen und Freigeben           | Hinweise, Überschneidung, Stoppuhr, Freigabe je ganzer Zeitraum  | ZEI-025              |
| Zeiten auf Servicefälle        | spontan für jeden mit Zeiterfassung, auch ohne Planung           | ZEI-024              |
| Beteiligte eines Servicefalls  | Person, Funktion, Notiz; keine Personalplanung, keine Kosten     | PRJ-108              |
| Hinweis auf die Begleit-App    | in "Meine Zeiten", wegklickbar, mit Link zu den Tokens           | ZEI-024              |
| Hinweis auf der Startseite     | nein                                                             | ZEI-024              |
| In der App                     | dritte Spalte; Rentalars speichert nur die Wahl und nennt sie    | UIX-039              |
| Arbeitsweg                     | doppelte Entfernung einmal je Person, Projekt und Tag abgezogen  | ZEI-027              |
| Ohne Entfernung                | kein Abzug; eine Einstellung schaltet den Abzug ab               | ZEI-027              |
| Zuschläge für jedes Land       | Regeln: Tageszeit, Wochentag, Feiertag, Tag im Jahr ab Uhrzeit   | PER-040              |
| Regeln verrechnen              | von den Tagesregeln die höchste; die Tageszeit kommt hinzu       | PER-040              |
| § 3b EStG                      | Knopf stellt den deutschen Satz ein, mit Nachtarbeit             | PER-040, PER-009     |
| Feiertage                      | Bundesländer, dazu eigene (fest, einmal, zu Ostern)              | PER-040              |
| Herkunft der Feiertage (Punkt 30) | rechnet Rentalars je Bundesland selbst, kein Dienst wird gefragt | PER-009, PER-040 |
| Bewegliche Feiertage           | aus dem Datum des Ostersonntags berechnet                        | PER-009, PER-040     |
| Hinweise auf Zeiten            | zentral abschaltbar; voreingestellt an                           | ZEI-018              |
| Zurück                         | nie auf Seiten der Hauptnavigation; ein Test prüft alle          | UIX-041              |
| Tabellen                       | überall Filter, Spalten, Sortieren, CSV, Gruppieren              | UIX-040              |

Ausbaustufe 8: Weitere Anforderungen

Die Punkte sind die Nummern der Anforderungsliste; 16 bis 19 und 25 bis 33
sind Funde einer Code-Prüfung.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 8                        | Wünsche und die Code-Prüfung sind SOLL in Stufe 8                | Kapitel 10 |
| Fehler beim Senden (Punkt 2)   | eine Meldung am Formular, in jedem Formular | EML-024         |
| Altlasten (Punkt 3)            | entfernen, was sicher entbehrlich ist; Migrationen bleiben       | NFA-062              |
| Englische Namen (Punkt 5)      | auch in Datenbank, Vorlagen, CSS und JavaScript; die API bleibt  | NFA-061              |
| Showfiles (Punkt 6)            | im Hinweis eines leeren Reiters "Dokumente"                      | PRJ-089              |
| Zeitstrahl der Zeitplanung (7) | Personal wie im Personalplan: Farben, Schraffur, Konflikte, Zeiten | VFG-035            |
| Personal je Phase (Punkt 8)    | ändern, entfernen, offene Plätze besetzen wie im Dialog          | PRJ-110              |
| Kacheln (Punkt 9)              | mit der Herkunft der Installation als Referer, nach den Regeln von OSM | UIX-034        |
| Routenlinks (Punkt 10)         | immer ab dem aktuellen Standort; Zwischenziele und Ziel bleiben  | UIX-033, PRJ-097     |
| Fahrten (Punkt 11)             | je Projekt anpassen und entfernen; die ermittelten bleiben Voreinstellung | PRJ-111     |
| Meine Einsätze (Punkt 12)      | erster Reiter in Mein Bereich, als Tabelle; der Kasten bleibt    | UIX-043              |
| Filter (Punkt 13)              | in jeder Tabelle zunächst eingeklappt, auch in der Materialverwaltung | UIX-038, UIX-040 |
| Kunde im Servicefall (14)      | Pflicht wie im Projekt                                           | PRJ-090              |
| Beschreibung im Servicefall    | bleibt freiwillig                                                | PRJ-090              |
| Idempotenz (Punkt 16)          | erst Anmeldung und Rechte; an Aufrufer und Anfrage gebunden; 409 | API-010              |
| Zugangsdaten (Punkt 17)        | nur an denselben Host; Ausnahmen nur für genannte Anbieter       | NFA-072              |
| Versionsprüfung (Punkt 18)     | Vergleich und Speichern in einem Schritt (API, If-Match)         | API-010              |
| Interne Ziele (Punkt 19)       | gesperrt, außer in der Konfiguration freigegeben; DNS und Weiterleitungen geprüft | NFA-071 |
| Mails ohne Kennung (Punkt 20)  | nur ab einem Zeitpunkt, wahlweise nur ungelesene                 | EML-049              |
| Zeitpunkt "ab"                 | beim Einschalten gesetzt, änderbar; nach dem Update der des Updates | EML-049           |
| Sortieren (Punkt 21)           | jede Spalte, auch hinzugefügte und berechnete; Ausnahmen mit Grund | UIX-015            |
| Offline-Abgleich (25, 31)      | Versionen des Servers und Änderungs-IDs; ohne sie die Regel für die Uhren | PCK-027     |
| Webhook "zurück" (Punkt 26)    | nur, wenn die Menge steigt – wie im Browser                      | PCK-027, API-012     |
| Lesestand im Chat (Punkt 27)   | höchstens bis zur neuesten Nachricht des Chats                   | UIX-010              |
| Änderungsstempel (Punkt 28)    | ändert sich mit jeder Änderung; gilt für jede Abfrage nach Änderungen | UIX-010, UIX-020 |
| GET (Punkt 29)                 | schreibt nichts; Packlisten entstehen, wo geschrieben wird       | PCK-026, PCK-027     |
| HTTP im Betrieb (Punkt 33)     | Start verweigert, außer die Konfiguration erlaubt es ausdrücklich | NFA-073             |
| Begleit-App                    | arbeitet unverändert; die API bietet zusätzlich mehr            | PCK-027, APP-001 ff. |

Ausbaustufe 9

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 9                        | die Logistik                                                     | Kapitel 10 |
| Stufe 10                       | die übrigen 27 KANN-Anforderungen                                | Kapitel 10 |
| Adresse und Zertifikat         | "Nur Befehl anzeigen": die Oberfläche zeigt den Befehl für SSH   | ADM-016              |
| Rechte der Anwendung           | kein root für Rentalars; Zugangsdaten für root nie gespeichert   | ADM-016, ADM-009     |
| Sprache der Oberfläche         | Deutsch oder Englisch, je Nutzer                                 | UIX-029, NFA-026     |
| Sprache der Dokumente          | eine Einstellung für den ganzen Betrieb, auch für Mails aus Vorlagen | UIX-029          |
| Benutzerhandbuch               | auf Deutsch und Englisch                                         | UIX-029, NFA-047     |

Ausbaustufe 8: Weitere Anforderungen

Anforderungen: Serveradresse und Zweisprachigkeit; die Vorgabe zur KI gilt generell, nicht nur für den Raspberry Pi.
Dazu gehören Gruppieren nach jeder Spalte, drei Status eines Servicefalls und
Regeln dafür in den Automationen. Entschieden: Adresse und Zweisprachigkeit
werden vollständig gebaut. Die Zusammenfassung
von Korrespondenzen im Projekt arbeitet mit einer lokalen KI, um Kosten zu
sparen: Für den Anwendungsfall "Zusammenfassung" wird, wenn möglich, eine
aktivierbare lokale KI integriert; für andere Anwendungsfälle wird die
Schnittstelle integriert, aber anfänglich ausgeschaltet.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 8                        | Wünsche sind SOLL in Stufe 8                                     | Kapitel 10           |
| Stufe 9                        | Adresse und Sprachen vollständig in Stufe 8; Stufe 9 ist die Logistik | ADM-016, UIX-029     |
| Weitere Erweiterungen          | Stufe 10, ohne EML-040 und EML-044                               | Kapitel 10           |
| Adresse und Zertifikat         | weiter "Nur Befehl anzeigen": die Seite bereitet vor, der Befehl per SSH wendet an | ADM-016 |
| Der Befehl                     | prüft selbst erneut, sichert, stellt bei Fehlern alles wieder her; Probelauf | ADM-016    |
| Rechte der Anwendung           | kein root; Zugangsdaten für root nie gespeichert                 | ADM-016, ADM-009     |
| Sprache der Oberfläche         | je Person; ohne Anmeldung nach dem Browser; sonst die der Installation | UIX-029        |
| Englisch                       | britisch: dd/mm/yyyy, 24 Stunden; die Texte im Code sind das Englisch der Oberfläche | UIX-029, NFA-061 |
| Sprache der Dokumente          | eine Einstellung für den Betrieb; selbst Geschriebenes bleibt, wie es ist | UIX-029     |
| Handbuch                       | in der Anwendung in der Sprache der Person; ohne englisches das deutsche mit Hinweis | UIX-029, NFA-047 |
| KI (Antwort)                   | Zusammenfassung mit lokaler KI, einschaltbar; andere Verwendungen über die Schnittstelle, anfangs aus | EML-040, ADM-017 |
| KI auf jedem Server            | gilt generell, nicht nur für den Raspberry Pi                    | EML-040, NFA-070     |
| Lokale KI                      | installiert der Betreiber per Befehl; nur auf demselben Rechner erreichbar | EML-040, NFA-071 |
| Ohne KI                        | immer eine Kurzübersicht der Korrespondenz                       | EML-040              |
| Dienste in der Cloud           | über die Schnittstelle möglich, mit deutlicher Warnung           | ADM-017              |
| Protokoll                      | jeder KI-Aufruf ohne Inhalt: Verwendung, Anbieter, Modell, Dauer, Größe | ADM-017       |
| Weitere Verwendungen           | "Antwortentwurf für Mails", anfangs aus; Vorlagenvorschläge später | ADM-017, PRJ-091   |
| Status eines Servicefalls      | wartet (Rückmeldung, Aktion, Materiallieferung), wartet auf Schließen, Rückstand | PRJ-112 |
| Wiedervorlage                  | Pflicht bei den drei Status; bei "wartet auf Schließen" mit Uhrzeit | PRJ-112, PRJ-109  |
| Rückstand                      | bis zur Fälligkeit in keinem Dashboard, nur in der Liste der Servicefälle | PRJ-112      |
| Regeln für Servicefälle        | drei Automationen, voreingestellt und aktiv, bearbeit- und abschaltbar | ADM-013        |
| Gruppieren                     | nach jeder eingeblendeten Spalte; Knöpfe und Kästchen ausgenommen | UIX-044, UIX-040    |

Ausbaustufe 8: Weitere Anforderungen

Die Punkte sind die Nummern der Anforderungsliste: (1) Es werden unter
anderem die Anforderungen aus dem Anforderungsdokument der App-Entwicklung
aufgenommen. (2) Die Stundenmarkierungen in Zeitstrahlen passen ab etwa
1236 px Gesamtbreite nicht, ab 1920 px wird es besser; sie werden angepasst,
und wo das nicht geht, gilt die vorherige Einstellung. (3) Global einstellbar
sind die Uhrzeit der Fehlmaterial-Benachrichtigungen, das Intervall (etwa
tägliche Meldung) und der Vorlauf (ein Jahr vorher muss noch nicht
benachrichtigt werden). (4) Im Servicefall heißt der erste Reiter "Überblick"
statt "Servicefall". (5) Bei der Zeiterfassung für ein Projekt war das
Auswahlfeld "Funktion" leer, wenn keine Phasen angegeben sind; das ist ein
Fehler und wird behoben. (6) Aufschläge gelten nur für Personalpositionen;
gemeint sind die Zuschläge für Nacht, Sonn- und Feiertag unter Einstellungen →
Zuschläge. (7) In der Mobilansicht gleitet das Menü wie in der App von der
Seite herein. (8) Die Korrespondenz-Ansicht in Projekten und Servicefällen ist
identisch, die "Zusammenfassung ohne KI" stets eingeklappt, und der Kasten
"Überblick" im Reiter "Korrespondenz" heißt "Zusammenfassung". Die
Anforderungen der App betreffen unter anderem die Rolle Crew
und den Token der App, mit dem Chat, Korrespondenz, Preisübersicht und Anfragen
unverändert gehen. Dazu kam ein Test der lokalen KI auf einem virtuellen Server mit
Ubuntu 26.04 (Größe des Referenzsystems, NFA-038) mit dem Modell qwen3-4b, vom
Befehl selbst gewählt: Der Geschwindigkeitstest dauerte 29 Sekunden, beim
zweiten Mal 10, für 84 Zeichen hinein und 32 heraus; eine Zusammenfassung von
1.979 Zeichen brach nach 600 Sekunden ab (Meldung "Lokale KI hat nicht
rechtzeitig geantwortet", 0 Zeichen empfangen).

Zur Rolle Crew (Hinweis der App) wurde entschieden: Die Crew darf alles,
was schreibt, aber keine finanzielle Auswirkung hat. Das heißt, Material
nachtragen darf sie nicht; sie hält sich 1:1 an die Packliste, und Mehrmaterial
müssen berechtigte Personen hinzufügen. Das Menü wird nur für die mobile
Ansicht umgebaut. Zu AVX2 auf dem virtuellen Server: Der Prozessortyp war nicht
"host", sondern die Standardeinstellung der Virtualisierung (x86-64-v2-AES).
Die gemeldeten 16 AVX2-/FMA-Einträge stammen sehr wahrscheinlich vom Wirtsrechner
selbst; mit dem Typ x86-64-v2-AES bekommt die virtuelle Maschine kein AVX2.
Empfohlen ist der Typ "host", danach die Maschine herunterfahren und wieder
starten. Zur Aktualisierung der KI mit dem Update: Die Einstellungen der
lokalen KI übernimmt jedes Update selbst; das Modell wechselt nie von allein;
llama-server kommt auf Ubuntu 26.04 aus dem Ubuntu-Paket und wird mit den
Systemupdates (apt) aktualisiert.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 8                        | Wünsche und die Anforderungen der App sind Stufe 8               | Kapitel 10 |
| Anforderungen der App (1)      | H und 1 bis 7 aufgenommen                                        | PRJ-113, PRJ-114, API-015, API-016 |
| Priorität                      | H und 1 MUSS wie in den Dokumenten der App; 2 bis 7 SOLL, auch was die App KANN nennt | PRJ-113, PRJ-114, Kapitel 10 |
| Jüngere Änderung               | gewinnt je Feld nach dem Zeitpunkt der Änderung; Gleichstand: Server; Zukunft: jetzt | PRJ-113, PRJ-114, API-015 |
| Servicefälle                   | sind Projekte: Status des Falls (Anforderung 1 der App) und Felder des Projekts (H) mit einem Mechanismus | PRJ-114, PRJ-113 |
| Startwerte                     | je Feld der letzte Eintrag im Änderungsprotokoll, der es wirklich änderte, sonst die Anlage; für Projekte, Fälle und Personen | PRJ-113, PRJ-114, API-015 |
| Ohne Änderungszeit             | es gilt If-Match                                                 | PRJ-113, API-010     |
| Statuswechsel zu spät          | 409 mit dem aktuellen Projekt; beim Servicefall kein 409, jede Folge ist erlaubt | PRJ-113, PRJ-114 |
| Eigene Daten über die API      | ohne Recht am Modul Personal, wie in Mein Bereich                | API-015, UIX-026     |
| Token der App                  | packing, projects, time_tracking, email; auch Chat, Mails, Preisübersicht, Anfragen | APP-001, AUT-021 |
| Rolle Crew (Entscheidung)      | packt in ihren Projekten alles ohne finanzielle Wirkung, 1:1 nach der Packliste, auch in der App | PCK-013, Kapitel 4 |
| Material nachtragen            | nur wer das Projekt bearbeiten darf oder für alle Projekte packt (Lager, Projektleitung) | PCK-013 |
| Abgleich der App               | Menge über der Packliste abgelehnt mit needs_project_write bzw. above_packing_list; der Rest kommt an | PCK-013, PCK-027 |
| Zeitstrahlen (2)               | Linien genau an den Stunden (auf 0,5 Pixel)                      | VFG-033 |
| Fehlbestände (3)               | unter Einstellungen → Benachrichtigungen: Uhrzeit, Abstand, Vorlauf 1 bis 26 Wochen | VFG-036, UIX-005 |
| Werktage                       | Montag bis Freitag ohne die Feiertage unter Einstellungen → Zuschläge | VFG-036          |
| Zeitgeber                      | der Minuten-Zeitgeber der Aufgaben im Hintergrund (run_jobs)     | VFG-036 |
| Erneut melden                  | wählbar; voreingestellt je Fall einmal                           | VFG-036              |
| Reiter im Servicefall (4)      | "Überblick"                                                      | PRJ-090              |
| Funktion bei Zeiterfassung (5) | nie leer: eigene und eingeplante, dann die des Projektpersonals und offener Plätze, sonst alle aktiven; auch für die App | ZEI-007 |
| "Aufschläge" (6)               | gemeint sind die Zuschläge; sie gelten nur für Personalpositionen | PER-009, PER-040    |
| Menü auf dem Smartphone (7)    | gleitet wie in der App als Schublade über der abgedunkelten Seite herein | UIX-045       |
| Seite des Menüs                | von rechts, wo der Menüknopf sitzt, wie in der App – nicht von links | UIX-045          |
| Nur mobil                      | nur bis 900 Pixel, wo die Leiste mit dem Menüknopf steht; am Computer bleibt die Seitenleiste | UIX-045 |
| Korrespondenz (8)              | in Projekt und Servicefall gleich; Kasten "Zusammenfassung"; ohne KI eingeklappt | EML-050, EML-040 |
| Testsystem der lokalen KI      | Ubuntu 26.04 als virtueller Server, wie das Referenzsystem (NFA-038) – ein typisches Betreibersystem | NFA-038, EML-040 |
| KI zu langsam                  | Denkmodus aus, Antworten gestreamt, Zeitlimit für Stille statt für die ganze Antwort | EML-040, ADM-017 |
| Geschwindigkeit                | Lesen und Schreiben getrennt gemessen; Dauer vorher geschätzt, Warnung ab 5 Minuten | EML-040 |
| Prozessor                      | Prüfung auf AVX2 und FMA mit Hinweis für VMs (Typ "host" der Virtualisierung); Threads = physische Kerne | EML-040 |
| AVX2 auf virtuellen Servern    | der Prozessortyp x86-64-v2-AES hat kein AVX2; Typ "host" empfohlen | EML-040           |
| Modell                         | Qwen3 4B ab 6 GB, 4 physischen Kernen und AVX2/FMA, sonst Qwen3 1.7B Q4_K_M; empfohlen unter 6 Tokens/s Schreiben oder 30 Lesen | EML-040 |
| Update der KI                  | Einstellungen mit jedem Update und Start (`ai refresh`), das Modell nie von selbst; llama-server auf 26.04 per apt | EML-040 |

Ausbaustufe 8: Weitere Anforderungen

Die Anforderungen im Überblick: eine Erinnerung an
die Rechnung (ist im System die Rechnungsstellung aktiviert, wird nach einem
abgeschlossenen Projekt regelmäßig daran erinnert, eine Rechnung zu schreiben;
ist sie deaktiviert, wird ein Wahrheitswert "Rechnung gestellt" geführt); Ideen
für halbautomatische Monatsrechnungen für Servicefälle je Kunde mit
Zusammenfassung der Tätigkeit; im Installationsprozess werden die Werte
abgefragt, die für die Personalprodukte als interne Preise/Kosten und als
Kundenpreise eingesetzt werden (0 € ist als Startwert ungeeignet); eine
Möglichkeit, die Profitabilität im Blick zu haben; je Exemplar eine Übersicht,
wie viel Geld unmittelbar mit dem Objekt eingenommen wurde und welchen Anteil
das am Kaufpreis ausmacht; drei Änderungen am Import (netto oder brutto,
Kennungen mit vorangestelltem Doppelkreuz, Preise als gekauftes Set); das
Modell in der Ansicht eines Exemplars; drei Arten von Etiketten (klein, groß,
Kabel) nach den vorhandenen Vorlagen des Betriebs, direkt aus dem Browser auf
Etikettendruckern druckbar; Altlasten entfernen, vor allem in den URL-Pfaden;
eine Logistikplanung als Anforderung aufnehmen (Kapitel 5.17); aus
Defektmeldungen direkt einen Servicefall erstellen (als Automation in den
Einstellungen, vom Anwender änderbar) und als Aktion der Automation auch nur
eine Anfrage; die Einstellungen ordnen, vor allem den sehr vollen Kasten
"System"; in der Seitenleiste wirken "Mein Konto", "Handbuch" und "Abmelden"
gedrungen. Hinzu kamen die drei Vorlagen des Etikettendruckers (P-touch
Editor, .lbx) und: Etiketten-Logo und -Firmenname sind getrennt angebbar, ebenso
QR-Code, Telefonnummer, URL und Text konfigurierbar, das Layout bleibt; in der
Korrespondenz sind auch reine Notizen mit Zeitstempel möglich, um die
Chronologie zu wahren; die KI-Zusammenfassungen sind ebenfalls eingeklappt.
Schließlich: Aktionsleisten für Mehrfachauswahlen werden erst angezeigt, wenn
Kästchen angehakt sind, wie in der Planung eines Projekts als Popup, das beim
Scrollen unten andockt.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 8                        | alle Wünsche sind Stufe 8, SOLL                                  | Kapitel 10           |
| Abgerechnet                    | mit Rechnungen in Rentalars: eine nicht stornierte Rechnung; ohne: der Haken "Rechnung gestellt" | DOK-015 |
| "Keine Rechnung"               | für Projekte, die nie abgerechnet werden; beendet die Erinnerungen | DOK-015            |
| Wann erinnert                  | 1 Tag nach dem Abschluss, dann alle 7 Tage, 9:00 Uhr; einstellbar, abschaltbar | DOK-015 |
| Wen                            | Projektleitung und eine gewählte Person, nur mit dem Recht für Preise | DOK-015, AUT-019 |
| Alte Projekte                  | nur Projekte, die nach dem Update abgeschlossen wurden            | DOK-015             |
| Monatsrechnung                 | als Idee festgehalten, KANN in Stufe 10 (seit 0.27 Stufe 9, gebaut) | DOK-016           |
| Stundensätze der Einrichtung   | vorgeschlagen 45,00 € Preis und 30,00 € Kosten je Stunde, nur wo noch keiner steht | ADM-018 |
| Profitabilität                 | Eintrag "Auswertungen": je Monat, Kunde, Projektleitung; nichts gespeichert, aus der Kalkulation | PRJ-115 |
| Recht auf Auswertungen         | Modul Auswertungen lesen, alle Projekte lesen, Preise sehen; Kosten mit den Rechten dafür | AUT-014, PRJ-115, MAT-053 |
| Ertrag je Exemplar             | zugeordnet beim Packen, sonst gleichmäßig geschätzt; Set gegen den Preis des Sets | MAT-053 |
| Kaufset                        | Verweis "Preis enthalten in" am Exemplar; keine Ketten            | MAT-054, IMP-016    |
| Netto oder brutto              | Auswahl im Dialog mit Steuersatz; gespeichert wird netto          | IMP-014             |
| Etiketten                      | Layout der drei Vorlagen nachgebaut; Inhalte unter Einstellungen → Etiketten | MAT-056 |
| Druck aus dem Browser          | eine Seite je Etikett in genauer Größe, Druckdialog öffnet sich selbst; Brother DK-11204, DK-11201, DK-22210 | MAT-056 |
| QR-Code                        | Ziel einstellbar mit {id}; leer die Seite des Exemplars in Rentalars | MAT-056          |
| Defektmeldung                  | Automation, voreingestellt aktiv: Servicefall; wahlweise Anfrage  | MAT-057, ADM-013    |
| Kunde des Falls                | intern (eigenes Material) oder der Eigentümer von Kundenmaterial  | MAT-057, PRJ-090    |
| Notizen                        | mit Zeitpunkt, nie in der Zukunft; keine neue Kommunikation       | EML-051             |
| KI-Zusammenfassung             | beim Öffnen eingeklappt, offen nur gleich nach dem Schreiben      | EML-050             |
| Einstellungen                  | zehn Kästen nach Themen; "System" aufgeteilt                      | UIX-046             |
| Aktionsleiste                  | erst bei Auswahl, unten angedockt wie in der Planung; "Auswahl aufheben" | UIX-048       |
| Adressen                       | Anfragen, Staffeln, Mail-Protokoll unter ihrem Bereich; keine Umleitungen; API unverändert | NFA-074 |
| Logistik                       | als Stufe 9 aufgenommen, die KANN-Erweiterungen sind Stufe 10    | Kapitel 5.17, 10 |

Stufe 9: Entscheidungen (Teil 1)

Umfang: Stand 9 wird erweitert; die Monatsabrechnung wird in Stand 9
vorgezogen, ebenso der Import als Vorschau statt direkt (IMP-011); offene
Fragen werden vor dem Bau geklärt. Der Vorschlag zu einer halbautomatischen
Monatsrechnung für Servicefälle wurde angenommen. Zu klären war außerdem, ob
der Punkt "mehrere Postfächer" (Stufe 10) nicht schon integriert ist. Die
Auswertungen von /material/items/x/ erscheinen auch unter /material/models/x/
(dort aggregiert für alle zugeordneten Exemplare). Dazu: Anfragen sind auch von
Hand erstellbar (etwa um einen eingehenden Anruf gleich für die Bearbeitung im
Büro zu notieren). Die Entscheidungen zu den Rückfragen stehen in der
Tabelle.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stufe 9                        | Logistik und alle Wünsche                                        | Kapitel 10           |
| Fahrzeuge                      | "Als Exemplare" eines Materialmodells mit Produktart "Fahrzeug"   | LOG-002, LOG-014     |
| Kilometer                      | "Wahlweise je Fahrt": gefahrene (sonst geplante als Schätzung), geplante oder pauschal | LOG-007 |
| Anhängerzuschlag               | "Am Zugfahrzeug"; ein Gespann hat höchstens einen Anhänger        | LOG-006              |
| Fahrer                         | "Über seine Personalposition"; die Logistik rechnet nur das Fahrzeug ab | LOG-008       |
| Zumietung                      | wie eigene; was der Lieferant berechnet, sind die Kosten          | LOG-010              |
| Führerschein, Anhängelast      | nur Hinweise                                                      | LOG-012, LOG-013     |
| Packliste                      | nennt nur das Fahrzeug ("Verladen in")                            | LOG-011              |
| Tagesmiete                     | Miettage wie Material, umschaltbar auf nur die Tage mit Fahrten | LOG-005 |
| Routen                         | Routendienst optional installier- und aktivierbar, auch nachträglich; ohne ihn von Hand | LOG-017 |
| Monatsrechnung                 | orientiert sich am Haken "Rentalars als Buchhaltungsprogramm verwenden": Rechnungsentwurf; sonst Ansicht zum Kopieren | DOK-016 |
| Verträge je Kunde              | später                                                          | DOK-017              |
| Import                         | "Vorschau im Browser" statt SQL-Datei                             | IMP-011              |
| Postfächer                     | Absender wählbar, stets nach Berechtigung; Rollen je Adresse | EML-052, EML-003 |
| Profitabilität                 | im Monat des Projektendes                                         | PRJ-115              |
| "Rechnung gestellt"            | nur ohne Rechnungen in Rentalars                           | DOK-015              |
| Pauschale in "Meine Zeiten"    | "Einmal je Einsatz"                                               | ZEI-028              |
| Hinweis-Mail                   | gebaut: an die bisherige Adresse bzw. bei neuem Passwort      | AUT-030              |
| Vorlagentexte                  | gebaut: Englisch oder Deutsch auf Knopfdruck                  | DOK-018              |
| Urhebervermerk                 | Zusatzbestimmung aufnehmen (GPL Abschnitt 7 b)                   | NFA-075              |
| Etiketten am Drucker           | noch nicht; Erinnerung vorgemerkt – Test am Brother-Drucker offen  | MAT-056, 12.2 Nr. 31 |

Stufe 9: Entscheidungen (Teil 2)

Umfang: 26 Punkte, alle
umgesetzt; Unklarheiten wurden vorab geklärt. Die Wünsche sind in den
Anforderungen zusammengefasst; zwei kleine Punkte der Planung (Abstand zwischen
Logistik und Summen, kein Hinweis "in keiner Teilgruppe" mehr) brauchten keine
Anforderung. Die Antworten auf die Rückfragen:

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Rechnung hochladen             | "KI liest die Rechnung"; ohne KI nur die Kopfdaten               | MAT-062              |
| Verkaufspreis von Mietprodukten | "Verkaufspreis streichen", im Änderungsprotokoll vermerkt       | PRD-047              |
| Ausgangsbelege                 | auch Angebote und die übrigen Ausgangsbelege; die tabellarischen Darstellungen (UIX-040) bieten dann alle Möglichkeiten | DOK-020 |
| Servicefall der Crew           | beteiligte Crew kann alles, was zur Mitarbeit nötig ist (auch Korrespondenz, Chat, Status ändern); Korrespondenz in Projekten bleibt vertraulich | AUT-033 |
| Fehler in der Logistik         | Ursache: die erste Annahme für eine neue Phase über zwei Tage     | PRJ-116              |
| Etiketten am Drucker           | Scan von Originalen und Ausdrucken; Druck offen                   | MAT-065, 12.2 Nr. 32 |

Stufe 9: Entscheidungen (Teil 3)

Der Auftrag: 16 Punkte. Die
Wünsche sind in den Anforderungen zusammengefasst. Die Frage nach dem Unterschied zwischen
dem vollständigen Export und der Sicherung ist in IMP-006 beantwortet: Die
Sicherung dient der Wiederherstellung, der Export dem Lesen; der Export
steht nur unter "Sicherung". Die Antworten auf die Rückfragen:

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Schloss                        | "Offen: Crew; neu mit Schloss" – offene Nachrichten liest auch die eingeplante Crew, mit Schloss nur, wer Preise sieht | EML-055 |
| Schloss bei neuen Nachrichten  | Aus der Vorgabe, dass Korrespondenz in Projekten immer vertraulich ist, in Servicefällen normalerweise nicht: in Projekten mit Schloss, in Servicefällen offen, je einstellbar | EML-055 |
| Videos im Chat                 | "Auf dem Server verkleinern" – höchstens 720p, Fotos 2048 Pixel, nur die kleine Fassung bleibt | UIX-049, NFA-076 |
| Audits                         | "Eigener Audit-Modus" – IDs nacheinander scannen                 | MAT-068              |
| Altlasten                      | Datenbanken älterer Versionen werden nicht angefasst             | NFA-077           |

Stufe 9: Entscheidungen (Teil 4)

Der Auftrag: 16 Punkte. Die
Wünsche sind in den Anforderungen zusammengefasst. Die Antworten auf die Rückfragen:

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| DGUV-Prüfung                   | "Messwerte + Schutzklasse" – Schutzklasse an Modell und Exemplar, Messwerte mit Grenzwerten und Vorschlag bei elektrischen Prüfarten | MAT-077, MAT-078 |
| Vorgaben der Benachrichtigungen | beim Update einschalten – auch bestehende Installationen, im Änderungsprotokoll vermerkt | VFG-036, DOK-015 |

Stufe 10: Entscheidungen (Teil 1)

Die Antworten
auf die Rückfragen:

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Buchhaltung                    | vorrangig EÜR; die doppelte Buchführung ist für die Zukunft vorgemerkt  | DOK-045, DOK-047     |
| Massenaktion ohne Änderung     | "CSV-Download" der Auswahl für jede Tabelle, die sonst keine Aktion hat | UIX-058         |
| Validierung der E-Rechnung     | "Eigene Kernprüfungen" statt externem Prüftool                   | DOK-042              |
| Haken                          | "Rechnungen in Rentalars erstellen" heißt "Rentalars als Buchhaltungsprogramm verwenden" | DOK-014 |

Stufe 10: Entscheidungen (Teil 2)

Umfang: Gebaut ist der Inhalt, der vorgemerkt war.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Inhalt                         | Validierung, GoBD-Archiv, Versand, EÜR, Prüfbarkeit; doppelte Buchführung bleibt vorgemerkt | DOK-042 bis DOK-047 |
| Grundlage der EÜR              | Zahlungen als eigene, nicht änderbare Buchungen mit Storno; deshalb neu DOK-048 | DOK-048, DOK-045 |
| ZUGFeRD                        | als Wahl des Formats der Rechnung; das gespeicherte PDF ist dann das PDF/A-3b mit der Rechnung | DOK-049 |
| Prüfung der E-Rechnung         | wie entschieden eigene Kernprüfungen; Fehler melden statt blockieren (einstellbar) | DOK-042 |
| Anlagevermögen in der EÜR      | nur als Abschreibung aus dem Anlagenspiegel, nicht als Ausgabe bei Zahlung | DOK-045, MAT-086 |

Stufe 10: Entscheidungen (Teil 3)

Umfang: die noch offenen Punkte und inhaltlich bearbeitbare Projektvorlagen. Gebaut sind
die offenen Punkte – bis auf die doppelte Buchführung und das Mahnwesen – und der
Vorlageneditor.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Vorlagen bearbeiten            | Eintrag für Eintrag, mit Prüfung des Ganzen; Seite und API über denselben Dienst | PRJ-135, PRJ-136 |
| Offene Punkte                  | Zahlungsschutz im Modell, Finanzamt in der EÜR, Guthaben, BR-DE-21, Prüfer-Export im Hintergrund, Kontoauszug-Import | DOK-050 bis DOK-054, DOK-042 |
| Kontoauszug                    | nur Vorschläge; gebucht wird auf Klick, eine Buchung als Ganzes   | DOK-050              |
| Doppelte Buchführung, Mahnwesen | bleiben vorgemerkt                                               | DOK-047              |
| Externe Prüfung                | Schemas und Schematron der EN 16931 aus PyPI-Paketen; das Werkzeug der KoSIT war nicht erreichbar | DOK-042 |

Stufe 10: Entscheidungen (Teil 4)

Umfang: Apps im Browser koppeln, Gateway im Selbsttest, der Kasten „Fotos“, weitere Bereinigung für eine Veröffentlichung
(12.2 Nummer 50).

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Koppeln im Browser             | Einstellungen → Gateway macht den Kopplungscode (QR-Code und Text); Recht zu löschen in den Einstellungen; der Code wird nicht gespeichert, die Seite nicht zwischengespeichert; kein SSH nötig | GWL-011 |
| Sperren                        | Das Gerät ist in Rentalars gesperrt, auch wenn das Gateway nicht antwortet; die Seite sagt es | GWL-011 |
| Selbsttest                     | Gruppe „Gateway“ liest nur die Datenbank; die letzte Antwort darf höchstens 90 Sekunden alt sein; das Zertifikat wird nicht geprüft | GWL-014 |
| Kasten „Fotos“                 | Schmal rechts neben den Daten (darunter auf einem schmalen Fenster), kleinere Vorschaubilder | MAT-090 |
| Wettbewerbskapitel             | Abschnitt 5.19 (LUE) entfällt samt Stufe 12 | – |
| Beispieldaten                  | Weitere erfundene Namen und Adressen (192.168.1.50 als Beispieladresse) | NFA-075 |

Stufe 10: Entscheidungen (Teil 5)

Umfang: offene Punkte und die Vorbereitung des Quelltexts für eine Veröffentlichung
(12.2 Nummer 49).

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Ansprechpartner im Servicefall | Dieselbe Funktion wie im Projektformular (offer_new_contact); beide Formulare zeigen die Auswahl nach denselben Regeln | PRJ-140 |
| Rechteinhaber                  | "Lars Wilting, fld-vt.de"; der Platzhalter bleibt im Code, damit eine Fassung ihn zurücksetzen kann | UIX-062 |
| Formulierung                   | Anforderungen und Entscheidungen stehen sachlich formuliert, ohne betriebsinterne Angaben | NFA-075 |
| Beispieldaten                  | Erfundene Namen (Lieferant "Musikhaus Muster", Benutzer "luka"); Domains der Beispieladressen enden auf `.example` | NFA-075 |
| Ausgeschlossene Dateien        | `.gitignore` schließt Schlüsselspeicher, Zertifikate, APK und `.env` aus | NFA-075 |

Stufe 10: Entscheidungen (Teil 6)

Der Auftrag: vier Anforderungen (Bilder und Videos stets neu rendern, neuer Ansprechpartner im
Projektformular, Reiter Fuhrpark nach Exemplare, Fotos an Modellen und Exemplaren). Was dabei entschieden wurde und was nicht
gebaut ist, steht hier und in 12.2 Nummer 48.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Eine Stelle für Fotos          | rentalars/core/photos.py rendert jedes Foto; Chat, Defektmeldung, Spesenbeleg und die Fotos an Modell und Exemplar rufen sie, statt je eine eigene Fassung zu führen | NFA-084 |
| Standort bleibt                | Breite, Länge und Höhe (soweit plausibel: Breite ±90, Länge ±180) bleiben als einzige Angabe; Gerät, Aufnahmezeit, Richtung, Kommentar und XMP entfallen. Die Vorschau hat keine Metadaten, auch keinen Standort | NFA-084, UIX-049 |
| Auch kleine Fotos              | Ein Foto wird immer neu erzeugt, auch wenn es schon klein ist: Metadaten und Anhängsel am Dateiende sind der Grund, nicht die Größe | NFA-084 |
| Videos                         | Höchstens 720p, H.264/AAC, ohne Metadaten (UIX-049); die Umrechnung läuft für jedes Video, ein Test prüft es | UIX-049 |
| Dokumente                      | Nicht neu gerendert: Projektdateien, Rechnungen und Belege der Buchhaltung, Mailanhänge, Hallenplan, Logo und Etikettenvorlage. Ein Beleg muss so bleiben, wie er kam (Aufbewahrung, Nachweis); ein Foto, das als Dokument abgelegt wird, bleibt ein Dokument | NFA-084 |
| Fotos an Modell und Exemplar   | Wiederverwendet wird die Datei des Materials (MAT-017) mit der Art "Foto" statt einer neuen Tabelle: Rechte, Auslieferung, Löschen, Änderungsprotokoll und API sind schon da. Die Vorschau steht im Feld thumbnail (Migration material.0017) | MAT-090 |
| Reiter "Dateien"               | Bietet die Art "Foto" nicht an und zeigt keine Fotos; die Fotos stehen im Kasten "Fotos" der Seite. Fotos der Art "Bild" bleiben und stehen dort, ohne Vorschau (sie werden ganz ausgeliefert) | MAT-017, MAT-090 |
| Exemplar und Modell            | Ein Exemplar zeigt im Kopf sein erstes Foto, sonst das seines Modells, und führt die Fotos seines Modells unter den eigenen auf; das Modell zeigt nur seine | MAT-090 |
| Grenzen                        | Bis 20 Fotos je Upload, 25 MB je Foto (NFA-007); eine Datei, die kein Foto ist, wird mit ihrem Namen genannt, die anderen werden gespeichert | MAT-090 |
| Neuer Ansprechpartner          | Letzte Auswahl im Feld, nur wenn ein Kunde gewählt ist und die Person Kunden ändern darf; der Dialog fragt Name und Erreichbarkeit, Gruß und Hauptansprechpartner bleiben Sache der Kundenseite. Die Auswahl selbst ist kein Wert | PRJ-140 |
| Reihenfolge der Reiter         | Produkte, Modelle, Exemplare, Fuhrpark, Offene Punkte, Prüfungen, Audit, Import | UIX-013 |

Stufe 10: Entscheidungen (Teil 7)

Umfang: die Funde der Prüfung (Logikfehler L1 bis L16, Bedienung und Texte B1 bis B12, Layout V1 bis V26,
Code C1 bis C9). Was dabei anders entschieden wurde als vorgeschlagen und was nicht gebaut ist, steht hier und in 12.2 Nummer 47.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Stunden über die Zeitumstellung | Eine Dauer ist die verstrichene Zeit; Tage zählen nach der Uhr (Miettage). Gespeicherte Einträge werden nicht umgerechnet: Bezahlte Stunden ändert nur, wer sie bearbeitet | ZEI-002 |
| Anonymisierte Datensätze       | Die API antwortet 409 (nicht 403): Der Datensatz ist da, aber nicht mehr zu füllen; das Modell bleibt unverändert, weil das Anonymisieren selbst es schreibt | AUT-009, EML-031 |
| Name des Mailservers           | Ein Wort; ein gespeicherter falscher Wert wird nicht per Migration "repariert" (der Betreiber kennt den richtigen Namen), sondern vom Selbsttest gemeldet | EML-057 |
| Einstellungen                  | Ein Formular mit einem Knopf statt dreier Knöpfe mit Warnung: Drei Formulare auf einer Seite sind drei Wege, Eingaben zu verlieren | UIX-063 |
| Massenübernahme von Produktänderungen | Die Rückfrage nennt die Zahl der Projekte; das Zurücknehmen ist nicht gebaut (die alten Werte würden gespeichert, das wäre eine Änderung des Modells) | UIX-063 |
| Statusnamen                    | Deutsch "zurückgenommen", "zurückgestellt", "Bestätigt – Preise und Einzelheiten offen"; die englischen Bezeichnungen bleiben (Wert und Text sind gespeichert, ein Wechsel brauchte eine Migration) | PRJ-008, UIX-063 |
| Glossar                        | Eine Liste in docs/dev/glossary.md; "Gerät" nur für Elektrogeräte, Case und Rack sind "Behälter"; "Crew" und "Personal" getrennt | UIX-063 |
| Datumsformate                  | Vierstellige Jahre; Dateien mit eigenem Format (DATEV, Exporte, Kommandozeile des Gateways) behalten das deutsche Muster | UIX-063 |
| Englische Reste                | Die beiden Formulierungen und der Titel der EÜR; Schnell-To-dos und Einheiten sind gespeicherte Daten der Startdaten und werden nicht angefasst | UIX-063 |
| Aktionen eines Projekts am Telefon | Zwei Spalten statt eines Menüs "Aktionen": Das Menü versteckt die Hauptaktion vor wem sie nicht kennt | UIX-064 |
| Lizenztexte                    | Seiten des Programms (/about/<Name>/); der Klartext bleibt unter .txt; die Seite "Über" bleibt ohne "Zurück" (Eintrag der Navigation) | UIX-062, UIX-064 |
| Nicht gebaut                   | Kompakte Zeilen am Telefon (V3), Suchen-Knopf (V19), Chat (V20), Datum des Konflikts (V15); Buchhaltung aus dem Anhang der Prüfung | 12.2 Nummer 47 |
| Code                           | C1/C2 nur, wo ein Fund es verlangte; mypy bleibt eine Baseline; README kurz, CONTRIBUTING.md; C5, C6, C8, C9 nicht angefasst | C1 – C9 |

Stufe 10: Entscheidungen (Teil 8)

Umfang: die elf Funde S1 bis S11 einer Sicherheitsprüfung, je mit einem Nachweis durch einen
Test. Was dabei anders entschieden wurde als vorgeschlagen, steht hier; was offen bleibt, in 12.2 Nummer 46.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| S1 Bibliotheken                | Drei Bibliotheken auf den Stand ohne bekannte Schwachstellen; pip-audit in check.sh (überspringbar ohne Netz), Dependabot. Bilder werden nur mit den erwarteten Formaten geöffnet (Pillow braucht dafür die geladenen Erweiterungen, Image.init()) | NFA-081 |
| S2 Absender                    | Die strukturierte From-Zeile zählt. Bestätigung nur über den eingetragenen Mailserver (authserv-id, RFC 8601); ohne Eintrag kein Anspruch auf Echtheit, das steht im Handbuch. Kein eigenes SPF/DKIM | EML-057, PER-046 |
| S3 Zwei-Faktor-Codes           | Schon behoben (Zählung und Sperre im Browser und in der API, mit Tests); nichts geändert | AUT-005 |
| S4 Platzhalter als Schlüssel   | Der Start in der Produktion bricht ab; kurze Schlüssel werden weiter nur gewarnt, nicht abgewiesen (ein Betreiber mit vorhandenem Schlüssel soll nicht ausgesperrt werden) | NFA-032 |
| S5 www-data und Geheimnisse    | Die Annahme der Prüfung, gunicorn --umask schütze die Dateien, trifft nicht zu: Die Option wirkt nur auf den Socket und auf Arbeitsdateien, nicht auf die Umask des Prozesses. Der Socket muss für NGINX in der Gruppe lesbar bleiben; deshalb bleibt www-data in der Gruppe. Die Konfiguration (400) ist geschützt; für die Dateien im Datenordner bleibt es bei der Gruppenlesbarkeit | NFA-032 |
| S6 Skripte als root            | Die Wiederherstellung arbeitet im Ordner der Sicherungen (root) und ersetzt mit mv -T; die Statusdatei der Sicherung wird ohne Link geschrieben | NFA-032 |
| S7 Leere Zeilen im Import      | Obergrenze für gelesene Zeilen (300.000, leere eingerechnet) mit klarer Meldung; die Kosten einer leeren Zeile liegen in ihrer Breite (Excel schreibt bis Spalte XFD), darum nur bis Spalte 199 gelesen. Ein Abbruch nach einer Reihe leerer Zeilen mit dem Rest als leer wurde erwogen und verworfen: er würde Daten nach einer Lücke stillschweigend auslassen | IMP-001 |
| S8 Ein Vorschaltserver         | Opt-in über trusted_proxies; ohne Eintrag ändert sich nichts. NGINX nimmt die Adresse nur von dort an (realip), die Anwendung liest die letzte Adresse aus X-Forwarded-For | NFA-082 |
| S9 Nur-Lese-Tokens             | Eine Berechtigung für alle Endpunkte, die nur eine Anmeldung verlangen: Ändernde Aufrufe mit einem Nur-Lese-Token sind 403 (auch das Erstellen von Tokens, vorher 400) | AUT-021 |
| S10 Lieferantenkarten          | Material oder Verwaltung lesen, oder Projekte ändern (wer Zumietungen plant); Projekte lesen allein reicht nicht. Dieselbe Regel für die Vorschläge im Lieferantenfeld, die dieselben Daten zeigten | UIX-033, PRJ-101 |
| S11 Weiterleitungen            | Eine gemeinsame Prüfung mit der Funktion von Django statt dreier handgeschriebener | NFA-083 |

Stufe 10: Entscheidungen (Teil 9)

Umfang: die Funde der Prüfung vor der Veröffentlichung (Lizenz, Vorbereitung des Uploads, neun
schwere und weitere Logikfehler). Was dabei nicht der Code entscheiden kann, steht in 12.2 Nummer 45.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Zusatzbestimmung               | Gilt nur, wer Rentalars weitergibt; wer es nur betreibt, ist frei (sonst wäre es eine streichbare weitere Einschränkung nach § 7 GPL). Eine AGPL wurde nicht gewählt | NFA-075, UIX-031 |
| Seite "Über Rentalars"         | Der Vermerk steht zusätzlich auf einer Seite, die auch ohne Anmeldung erreichbar ist; die feste Stelle in der Oberfläche bleibt | UIX-062 |
| Rechteinhaber                  | Eingetragen ist "Lars Wilting, fld-vt.de" (COPYRIGHT_HOLDER); wer eine eigene Fassung weitergibt, trägt dort den eigenen Namen ein | UIX-062 |
| Keine Staffel                  | Jeder Tag voll (Faktor = Miettage), wie Handbuch und Fahrzeuge. Das ändert Preise von Produkten mit "keine Staffel" | PRD-034 |
| Miettage                       | Stunden der Uhr in Ortszeit, nicht vergangene Zeit             | PRJ-005 |
| Überfälliges Material          | Bleibt belegt, bis es zurückgebucht ist                         | VFG-002 |
| Fehlende, geklärte Teile       | Einzelstücke werden gesperrt; Mengenmaterial: Hinweis, die Menge zu verringern | PCK-019 |
| Zwei-Faktor-Sperre             | Falsche Codes zählen für den Namen des Kontos, ein richtiges Passwort löscht die Zählung nicht | AUT-005 |
| Reverse Charge                 | Kunde mit USt-IdNr. eines anderen EU-Landes und Satz 0 %: Hinweis auf der Rechnung, Kategorie AE; sonst bleibt es "steuerfrei" | DOK-006, DOK-042 |
| EÜR                            | Überschuss mit Umsatzsteuer; die 10-Tage-Regel wird nur gemeldet, nicht angewendet | DOK-045 |
| Konfigurationsdatei            | Besitzer Dienstkonto, Modus 400; Webserver bleibt in der Gruppe | NFA-032 |

Stufe 10: Entscheidungen (Teil 10)

Umfang: Eine weitergeleitete Anfrage lässt sich nicht im Namen des ursprünglichen Empfängers beantworten; die
Buchhaltung lässt sich ausblenden; die Hinweise auf geänderte Produkte
gelten auch dort; das Repository wird auf personenbezogene Daten und die Lizenzangabe geprüft.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Absender einer Antwort         | Die Anfrage speichert die Zieladresse; nur genau diese Adresse zählt. Kein Umweg über "bekannte Adressen" der Person (Konto-Adresse, frühere Adresse) | PER-046 |
| Gefälschte Absender            | Keine eigene SPF-/DKIM-Auswertung (Rentalars sieht den Weg der Mail nicht); gelesen wird nur das Prüfergebnis des empfangenden Servers, abgewiesen wird bei "dmarc=fail". Fehlt es, lässt sich nichts weiter prüfen | PER-046 |
| Was Buchhaltung ist            | Eingangsbelege samt Erfassen, Offene Posten, Bank, EÜR, Archiv, Anlagenspiegel, Verkäufe aus Bestand, Import alter Projekte (er legt ausgestellte Rechnungen an). Es bleiben Ausgangsdokumente und Monatsabrechnung (sie dienen dem Übertragen in das andere Programm) | DOK-055 |
| Wie ausgeblendet wird          | Menü, Reiter und Verweise, dazu eine Sperre für Adressen im Browser und in der API (nicht nur ein versteckter Link); nichts wird gelöscht | DOK-055 |
| Eigener Kasten                 | Der Schalter hat ein eigenes Formular mit eigenem Speichern, damit das Speichern der anderen Einstellungen ihn nie ausschaltet | DOK-055 |
| Status                         | Nur der angezeigte Name ändert sich; gespeicherter Wert und API bleiben confirmed_open | PRJ-008 |
| Geänderte Produkte             | "Bestätigt – Einzelheiten offen" zählt als noch nicht vollständig bestätigt: Hinweis, Übernahme, Benachrichtigung, Produktseite, API | PRJ-072, PRJ-137 bis PRJ-139 |

Stufe 10: Entscheidungen (Teil 11)

Umfang: Preise und Texte eines Produkts lassen sich in noch nicht bestätigten Projekten übernehmen, und die
Änderung wird gemeldet.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Warum man es nicht merkte      | Der Hinweis stand nur auf dem Reiter "Planung"; beim Öffnen landet man auf "Überblick". Jetzt auf jeder Seite des Projekts | PRJ-137 |
| Was zählt                      | Name, Einheit, Steuersatz, Abrechnungsart und Preis; nicht die Beschreibung (sie wird ohnehin vom Produkt gelesen), nicht Menge, Zeitraum, Notiz, Rabatt | PRJ-137 |
| Von Hand gesetzt               | Wie beim Preis: nie automatisch, nur je Position oder "Eigene Werte behalten"; unbekannter Stand zählt als von Hand | PRJ-072, PRJ-137 |
| Benachrichtigung               | Beim Speichern des Produkts, einmal je Projekt, ohne Preise, nicht per E-Mail vorbelegt | PRJ-138 |
| Von der Produktseite aus       | Wer das Produkt ändert, sieht dort alle betroffenen Projekte und kann sie in einem Zug nachziehen | PRJ-139 |
| Bestätigte Projekte            | unverändert: was vereinbart ist, ist vereinbart                  | PRJ-015, PRJ-072     |

Stufe 10 und 11: Entscheidungen zum Gateway

Umfang: Der Zweig mit der Anbindung des Servers an das Rentalars Gateway und den angepassten
Kabel-Etiketten wird geordnet übernommen, die Nutzung des Gateways funktioniert.

| Thema                          | Entscheidung                                                     | Umgesetzt in         |
|--------------------------------|------------------------------------------------------------------|----------------------|
| Inhalt                         | Gateway-Anbindung und Kabel-Etikett statt GoBD, EÜR usw.; Letzteres ist vorgemerkt | GWL-001 bis GWL-010, MAT-089, DOK-042 bis DOK-047 |
| Direkter Weg                   | bleibt unverändert; ohne `rentalars gateway connect` läuft nichts Neues | GWL-001, GWL-002 |
| Übernahme aus dem Zweig        | nur Neues und die Haken im Bestehenden; die ältere Migrationsreihe des Zweigs (vor dem Zusammenfassen) wird nicht übernommen | |

### 12.2 Offene Annahmen und bekannte Grenzen


Alle gestellten Fragen sind beantwortet. Offen ist nur, ob die folgenden
Annahmen stimmen, die aus den Antworten abgeleitet wurden:

1. Reservierung: Beide Status "Bestätigt" reservieren fest, "Option"
   reserviert nur sichtbar vor, "Anfrage" gar nicht (PRJ-008).
2. Prozentuale Aufpreise rechnen auf die Beträge nach Rabatt und nicht auf
   andere Aufpreise (PRD-039).
3. Material, das zwischen Teilprojekten wechselt, wird nur einmal berechnet
   (PRJ-060).
4. Kontaktdaten sind für Kollegen erst sichtbar, wenn die Person sie
   freigibt; nur der Name ist immer sichtbar (PER-019).
5. Lizenzangabe "Version 3 oder später" (NFA-052).
6. Oberfläche, Dokumente und Benutzerhandbuch gibt es auf Deutsch und
   Englisch; der Code ist englisch (NFA-061, UIX-029).
7. Gibt es von einem Case mehrere gleiche Exemplare mit unterschiedlichem
   Inhalt, rechnet die Verfügbarkeit vorsichtig mit dem umfangreichsten
   Inhalt, bis ein Exemplar zugeordnet ist (VFG-017).
8. Mails mit einem Kürzel, zu dem es kein Projekt gibt, bleiben ebenfalls
   unangetastet im Posteingang und erscheinen nur als Hinweis (EML-014).
9. Rechte je Projekt gelten für Crew und freie Kräfte, die eigene Konten
   haben (Kapitel 10).
10. Ubuntu-Versionen: Auf einer Version vor 24.04 bricht das Skript ab; auf
    einer anderen neueren als 26.04 läuft es mit einem Hinweis, dass sie
    nicht erprobt ist. Nach dem Wechsel einer bestehenden Installation von
    24.04 auf 26.04 genügt der Aktualisierungsbefehl (NFA-063).
11. Bedienung: "Zurück" führt nach dem Speichern am Formular vorbei dorthin,
    woher man gekommen ist; die Reiter eines Projekts gelten dabei als eine
    Seite; wer ohne Vorgeschichte ankommt, gelangt zur Startseite des
    Bereichs (UIX-011). Zur Wahl stehen 25, 50, 100 und 200 Einträge je
    Seite, gemerkt je Browser und nicht am Nutzerkonto (UIX-012).
    "Materialverwaltung" öffnet die Produkte (UIX-013).
12. Wünsche aus der zweiten Benutzung: Von Hand eingetragene Miettage gehen
    dem eigenen Zeitraum der Position vor (PRJ-062). Ein Wunsch nach Modell
    oder Exemplar bleibt ein Hinweis und reserviert nichts (PRJ-064). Ein
    defektes Exemplar wird erst aus der Reparatur heraus wieder verfügbar
    (MAT-045). Ein Exemplar, das schon woanders verbaut ist, wird über
    "Enthält" nicht umgehängt (MAT-046). Der dunkle Modus hellt die
    Hauptfarbe für Text auf dunklem Grund leicht auf, wo #EE591F allein den
    Kontrast von 4,5 zu 1 nicht erreicht; Schaltflächen tragen sie
    unverändert (UIX-008).
13. Personal und Zeit (Stufe 3):
    a) Eine Personalposition ist genau eine Person oder ein offener Platz;
       "2x Stagehand" sind zwei Positionen (PRJ-020).
    b) Personal wird in Stunden geplant und berechnet; Tagessätze folgen mit
       PER-009. Die geplanten Stunden werden aus dem Zeitraum vorgeschlagen:
       bis 16 Stunden die Dauer, darüber 8 Stunden je angefangenem Tag
       (PRJ-023). Es gibt Tagessätze (PER-029), und
       vorgeschlagen wird immer die ganze Dauer (PRJ-073, 20 b).
    c) Der Rückmeldestatus einer Personalposition (PRJ-023) kommt mit dem
       Anfrage-Ablauf in Stufe 4 (PER-016).
    d) Die Schnellerfassung reicht einen Eintrag sofort zur Freigabe ein,
       sofern der Haken nicht entfernt wird (ZEI-003, ZEI-012).
    e) Zeiten freigeben und für andere erfassen ist ein eigenes Sonderrecht;
       Projektleitung und Personaldisposition haben es (ZEI-011, ZEI-013).
       Personen außerhalb ihrer Funktionen einzuplanen ebenso (PER-006).
    f) Interne Projekte haben keinen Kunden; jeder, der Zeiten erfasst, kann
       darauf buchen (ZEI-010).
    g) Mit der Einsatzsicht allein bleibt auch der Kunde eines Projekts
       verborgen – in Liste, Suche, Packliste und API (AUT-023). Ein Projekt
       ohne Zugriff verhält sich wie ein nicht vorhandenes.
    h) Eine Mitgliedschaft gewährt nie mehr, als die Rolle erlaubt: Wer nur
       lesen darf, liest auch als Mitglied mit Stufe "Bearbeiten" (AUT-025).
    i) Die Personaldisposition plant Personal in Projekten, die sie nur
       lesen darf (Kapitel 4).
    j) Beim Anonymisieren einer Person wird auch ihr Nutzerkonto geschlossen
       und um Namen und Adresse bereinigt. Ein Konto mit
       allen Rechten lässt sich nicht anonymisieren; das Recht wird vorher entzogen
       (NFA-009, AUT-026).
    k) "Bedienbar" bei zehn gleichzeitigen Nutzern heißt: Jede Antwort beim
       Erfassen und Lesen von Zeiten kommt in unter zwei Sekunden (NFA-051).
    l) Ein Stundenzettel als PDF umfasst höchstens 3.000 Einträge; darüber
       bittet Rentalars, die Auswahl einzugrenzen. Die CSV-Datei hat keine
       Grenze (ZEI-017). Hintergrund: Ein Monat mit 100 Personen ergibt
       rund 80 Seiten und braucht schon etwa 20 Sekunden.

14. Korrespondenz und Planung (Stufe 4):
    a) Ein gemeinsames Projektpostfach; das Präfix des Kürzels ist RL. Der
       Abruf wird jede Minute angestoßen und läuft im eingestellten Abstand
       (Voreinstellung 2 Minuten). Eine Mail über 25 MB wird mit ihrem Text
       übernommen, ihre Anhänge bleiben im Postfach (EML-028). Seit Version
       0.16 sind es mehrere Postfächer (EML-041, 20 l).
    b) Mails werden aufbewahrt, bis sie von Hand entfernt werden; eine Frist
       in Tagen lässt sich einstellen (EML-031). Aus Rentalars entfernte
       Mails bleiben im Ordner des Postfachs.
    c) Externe Bilder einer Mail werden je Mail auf Knopfdruck geladen, nicht
       dauerhaft je Absender (EML-027).
    d) Einsatzanfragen: Eine Person ohne Nutzerkonto wird außerhalb von
       Rentalars gefragt; die Planung trägt ihre Antwort ein (PER-016).
       Jede Person hat ein Konto (AUT-026); die Planung
       kann eine Antwort aber weiterhin eintragen. Die Person kann
       auch per Antwort-Mail antworten, ohne sich anzumelden
       (PER-032, 21 e).
    e) Benachrichtigungen per E-Mail sind voreingestellt für Einsatzanfragen
       und Antworten, Fehlbestände, Defekte, neue Mails, Probleme beim Abruf
       und Fehler der Anwendung; Änderungen an Projekten erscheinen nur in der
       Anwendung, bis die Person es anders einstellt. Fehlbestände der
       kommenden vier Wochen werden nachts geprüft und je Position einmal
       gemeldet (UIX-005); Uhrzeit, Abstand und
       Vorlauf sind einstellbar (VFG-036). "Fällige Prüfung" kommt mit den
       Prüfungen in Stufe 5 (MAT-030 ff.).
    f) Die Startseite ist für alle dieselbe; was sie zeigt, richtet sich nach
       den Rechten und der verknüpften Person, nicht nach dem Namen der Rolle
       (UIX-003).
    g) Zwei-Faktor-Anmeldung nach RFC 6238 (sechs Stellen, 30 Sekunden) mit
       einer beliebigen Authenticator-App; zehn Wiederherstellungscodes für
       ein verlorenes Telefon; ein Administrator kann sie für einen Nutzer
       zurücksetzen. Persönliche API-Token gelten als eigener Schlüssel und
       verlangen keinen Code; angelegt werden sie nur nach vollständiger
       Anmeldung im Browser (AUT-006, AUT-021).
    h) Abmeldung nach 240 Minuten ohne Aktivität als Voreinstellung (AUT-008).
       Das Sicherheitsprotokoll wird ein Jahr aufbewahrt (AUT-022).
    i) Ein dupliziertes Projekt beginnt als "Anfrage"; die Uhrzeiten von
       Positionen und Phasen bleiben auch über eine Zeitumstellung hinweg
       gleich. Personal wird als offene Plätze übernommen, nicht mit den
       bisherigen Personen (PRJ-029).
    j) Die Crew sieht in der Einsatzsicht nur Projektdateien, deren Art dafür
       vorgesehen ist (Bühnenplan, Rider, Ablaufplan, Hallenplan), oder die
       einzeln freigegeben sind (PRJ-007, AUT-023).
    k) Ein Fehler der Anwendung wird den Betreibern einmal gemeldet und erst
       nach 24 Stunden erneut, wenn er weiter auftritt (NFA-018).
15. Datenbank (NFA-066 bis NFA-068): Ein vorhandener Datenbankserver wird nur
    mit einem Benutzer angenommen, der ausschließlich auf die eine Datenbank
    Rechte hat. Bei einem vorhandenen Server verschlüsselt Rentalars nur die
    Sicherungen. Der Wiederherstellungsschlüssel liegt auf dem Server und ist
    nur für root lesbar; wer ihn zusätzlich außerhalb aufbewahrt, kann auch
    eine Sicherung ohne den Server entschlüsseln.
16. Lager und Dokumente (Stufe 5):
    a) Ein Exemplar, das nie geprüft wurde, gilt als überfällig, sobald eine
       Prüfart für es gilt; die letzte Prüfung aus den Papieren lässt sich
       nachtragen. "Bald fällig" heißt: innerhalb von 30 Tagen (MAT-031,
       MAT-032).
    b) Das Gewicht eines Produkts auf der Packliste ist das seines
       schwersten Modells; Zeilen ohne Gewicht werden gezählt und genannt
       (PCK-006).
    c) Je Projekt gilt eine Rechnung; korrigiert wird sie durch eine
       Stornorechnung mit umgekehrten Beträgen und eine neue Rechnung. Die
       Stornorechnung zählt im Nummernkreis der Rechnungen (DOK-006).
    d) Leistungszeitraum auf Dokumenten ist der Zeitraum des Projekts, über
       den die Miettage gezählt werden. Optionale Teilgruppen stehen in der
       Auftragsbestätigung, nicht in der Rechnung.
    e) Die Käuferreferenz der XRechnung ist die Leitweg-ID des Kunden, sonst
       die Projektnummer. Zahlungsziel: das des Kunden, sonst 14 Tage aus
       den Firmendaten (KND-006).
    f) Beim Anonymisieren eines Kunden oder einer Person bleiben die
       erstellten Dokumente unverändert: Rechnungen und ihre Grundlagen
       unterliegen der Aufbewahrungspflicht (DOK-007, NFA-009).
    g) Import: Produkte werden an der Artikelnummer erkannt, Kunden an der
       Kundennummer (eine unbekannte Nummer wird übernommen), Personen an der
       E-Mail-Adresse, sonst am Namen. Preise, Rabatte und Stundensätze
       importiert nur, wer sie sehen darf (IMP-001, IMP-004).
    h) Den vollständigen Datenexport starten nur Administratoren; sein
       Ergebnis sieht nur, wer ihn gestartet hat (IMP-006).
    i) Aufbewahrungsfristen als Voreinstellung: Sicherheitsprotokoll 365
       Tage, Änderungsprotokoll dauerhaft, Benachrichtigungen 180 Tage,
       Ergebnisse von Aufgaben im Hintergrund 7 Tage (NFA-011). Damit ist
       die Frist aus 14 h) einstellbar geworden.
    j) Die Grenze der API liegt bei 600 Aufrufen je Token und Minute, die
       Antwort auf einen Aufruf mit Idempotency-Key wird einen Tag
       aufbewahrt (API-010, API-011).
    k) Barrierearmut wird mit axe-core gegen WCAG 2.1 Stufe A und AA geprüft,
       dazu bei jedem Testlauf Beschriftungen, Namen und eindeutige IDs
       (NFA-025).

#### Bekannte Grenzen

Was Rentalars nicht oder nur eingeschränkt kann und was vor dem Einsatz zu klären oder zu erproben ist:

**Betrieb und Sicherheit**

1. Geprüft ist mit automatischen Tests (SQLite und MariaDB) und mit Browser-Testwerkzeugen. Nicht erprobt sind ein echter Server mit Webserver und Dienstverwaltung, ein Load Balancer, ein echtes Active Directory, echte Postfächer und ein laufendes Gateway. Vor dem Einsatz: installieren bzw. aktualisieren, ein Bild aus "media" und eine Datei aus "static" abrufen; hinter einem Vorschaltserver nach dem Eintragen von trusted_proxies zwei Anmeldungen von verschiedenen Adressen vergleichen (NFA-032, NFA-063).
2. Nicht auf echten Geräten erprobt: Raspberry Pi mit seinen Paketen (NFA-070), Etikettendrucker (MAT-056, MAT-065, MAT-089), Telefone mit Kamera, Menü und Fotokasten (UIX-045, MAT-090), Firefox, Safari und Chrome unter Android bei Datums- und Zeitfeldern (UIX-036, UIX-042).
3. Dateien im Datenordner, die für die Gruppe des Dienstkontos lesbar sind, kann auch der Webserver-Benutzer lesen. Dies zu schließen (ACLs oder eigene Gruppe) ist nicht gebaut (NFA-032).
4. Verbindungen nach außen sind nur für Kalender, Webhooks und die Mailserver der Postfächer geschützt, nicht für das, was in der Konfigurationsdatei steht (Mailserver, Karten, Datenbank). Ziele im eigenen Netz brauchen eine Freigabe unter [network] allow_internal (NFA-071, NFA-072).
5. Ein vorhandener Datenbankserver wird nur mit einem Benutzer angenommen, der ausschließlich auf die eine Datenbank Rechte hat; dort verschlüsselt Rentalars nur die Sicherungen. Der Wiederherstellungsschlüssel liegt auf dem Server und ist nur für root lesbar; wer ihn nicht zusätzlich außerhalb aufbewahrt, kann eine Sicherung ohne den Server nicht entschlüsseln (NFA-066 bis NFA-068).
6. Der Zahlungsschutz wirkt gegen update, bulk_update und delete im Programmcode, nicht gegen SQL von Hand (DOK-051). Persönliche API-Token gelten als eigener Schlüssel und verlangen keinen Zwei-Faktor-Code (AUT-006, AUT-021).
7. Kartenabfragen nutzen Nominatim und einen Kachelserver mit eigenen Nutzungsregeln; wer viel abfragt, braucht einen eigenen Server (UIX-033, UIX-034).
8. Fotos tragen den Ort der Aufnahme; wer ein Foto herunterlädt oder weitergibt, gibt ihn mit. Das ist ein personenbezogenes Datum; wer ein Verzeichnis der Verarbeitungen führt, trägt es ein (NFA-084).
9. Kamerafotos auf den Wegen für Dokumente (Projektdateien, Mailanhänge, Lieferanten- und Zertifikatsdateien, Belege) werden nicht neu gerendert; das bleibt zu entscheiden, bei Belegen ist es nicht empfohlen. Bereits gespeicherte Dateien (Chat-Fotos, Defektfotos, Spesenbelege, Bilder an Modellen und Exemplaren) werden nicht umgerechnet (NFA-084).
10. Der Routendienst braucht eine Karte (Deutschland etwa 4,5 GB, Aufbereitung dauert Stunden), die unter /opt/rentalars/routes liegt und nicht gesichert wird (LOG-017).
11. Tabellen mit mehr als 300.000 Zeilen (leere eingerechnet) werden abgewiesen; XLSX-Dateien werden nur bis Spalte 199 gelesen. Der Import des Materials übernimmt Kaufpreise auch ohne das Recht, Einkaufspreise zu sehen; ob er sie dann ablehnen soll, ist offen (IMP-001, IMP-011).

**Lizenz und Recht**

12. Die Zusatzbestimmung zum Urhebervermerk (ADDITIONAL-TERMS.md) ist rechtlich nicht geprüft (NFA-052, NFA-075).
13. Ob und wie sich Code, den eine KI geschrieben hat, auf Urheberrecht und Copyleft auswirkt, ist rechtlich nicht abschließend geklärt (NFA-052, UIX-062).

**Buchhaltung und Steuern**

14. Nicht gebaut: doppelte Buchführung, Mahnwesen, Onlinezahlung, Skonto, MT940 und Abruf von der Bank. Zahlungen kommen von Hand oder aus einem Kontoauszug (CAMT.053 oder gängige CSV-Spalten); die Leser sind nur mit nachgebauten Dateien getestet, die Gewichte der Zuordnungsvorschläge sind eine erste Annahme. Alte Rechnungen aus dem Import haben keine Zahlungen und stehen in den offenen Posten, in der EÜR fehlt ihr Zufluss (DOK-047, DOK-048, DOK-050).
15. Die EÜR ist eine Vorbereitung nach dem Zu- und Abflussprinzip, keine Steuerberatung und keine Zeilen der Anlage EÜR. Teilzahlungen werden im Verhältnis der Steuersätze der Rechnung aufgeteilt, das Anlagevermögen geht nur über die Abschreibung ein. Ob Verkäufe aus dem Bestand ohne Rechnung am Verkaufstag als Einnahme gelten, ist zu bestätigen. Mit der Steuerberatung abgleichen (DOK-045).
16. Abschreibung: linear nach Monaten, Kaufmonat voll, GWG-Grenze (800 € netto) und Nutzungsdauer (60 Monate) sind Standardwerte. Degressive und Sonderabschreibung, Halbjahresregel und Sammelposten fehlen; der Anlagenspiegel hat keinen DATEV-Export. Ein nicht erfasstes Exemplar geht mit Restbuchwert 0 € in den Verkauf (ganzer Preis ist Gewinn); die Rechnung dazu ist ein nicht verknüpfter Entwurf (MAT-086, MAT-087, DOK-024).
17. GoBD: Archiv, Prüfsummen und index.xml sind eine Hilfe und nicht mit einer Prüfsoftware geprüft. Die Verfahrensdokumentation ist ein Gerüst; Organisation und interne Kontrollen ergänzt der Betreiber. Es ist keine Bescheinigung der GoBD-Konformität (DOK-043, DOK-046).
18. Ausgehende E-Rechnung: Die Prüfung besteht aus eigenen Kernprüfungen und ist kein Ersatz für das Prüftool der KoSIT (Regeln BR-DE); Behörden prüfen strenger. UBL und CII sind gegen Schemas und Schematron der EN 16931 geprüft, Teilgutschrift und Schlussrechnung mit Abzügen sowie ZUGFeRD (PDF/A-3b) nicht mit KoSIT, veraPDF, Mustang oder einem Empfängerprogramm. Vor dem Einsatz eine Rechnung beim Empfänger erproben (DOK-034, DOK-035, DOK-042, DOK-049).
19. Eingehende E-Rechnung: Gelesen wurden nur selbst gebaute Beispiele (UBL, CII, ZUGFeRD-PDF), keine echten Lieferantenrechnungen. Die ältere ZUGFeRD-Fassung wird nicht gelesen; Steuerbefreiungen, Skonto und Anzahlungen werden nur als Zahlen gelesen; eine Prüfung gegen Schematron findet nicht statt (DOK-040, DOK-041).
20. Reverse Charge gilt nur für Kunden mit USt-IdNr. eines anderen EU-Landes (nicht Nordirland) und nicht für Kleinunternehmer. Innergemeinschaftliche Lieferungen, Leistungen an Kunden außerhalb der EU und steuerfreie Ausfuhren sind nicht abgebildet (DOK-006, DOK-042).
21. Mit der Steuerberatung zu entscheiden sind: Eingangsrechnungs-Positionen ohne Steuersatz, Vorsteuer auf Anlagen bei Kleinunternehmern, erneute Übertragung einer Schlussrechnung an Lexware, DATEV-Erlöskonto bei Ausfuhr und innergemeinschaftlicher Leistung sowie mehrere Vorrechnungen in ZUGFeRD (DOK-011, DOK-012, DOK-042).
22. Die Formate für Lexware Office und DATEV sind nach veröffentlichten Beschreibungen gebaut und gegen die echten Systeme zu prüfen. Die SKR-03-Liste ist ein Vorschlag; Rentalars schlägt kein Konto vor und bucht nicht. Für das Finanzamt muss das Kennzeichen am Lieferanten einmal von Hand gesetzt werden; die Aufteilung von Zahllast und Vorauszahlungen ist nicht gebaut (DOK-011, DOK-012, DOK-026, DOK-052).
23. Abschlags- und Teilrechnungen rechnen einen Betrag ab (netto oder Prozent), keine einzelnen Positionen, und gelten nur für ein ganzes Projekt. Eine Abrechnung nach Leistungsstand mit zeilenweiser Teilung gibt es nicht (DOK-030 bis DOK-036).
24. Eingangsrechnungen: Gescannte Rechnungen und Bilder werden aufbewahrt, aber nicht gelesen; eine Texterkennung ist nicht vorgesehen, gelesen werden nur PDFs mit Text. Beim Einpflegen eines Kaufs gilt netto oder brutto für den ganzen Kauf; Versand, Rabatte und Pfand sind keine Positionen. Beim Import alter Projekte wird die Art einer Position geraten; die Vorschau ist kritisch zu lesen, echte Fremdrechnungen sind nicht geprüft (DOK-023, MAT-061, MAT-075, PRJ-130).
25. Je Projekt gilt eine Rechnung; korrigiert wird durch Stornorechnung und neue Rechnung. Beim Anonymisieren eines Kunden oder einer Person bleiben erstellte Dokumente wegen der Aufbewahrungspflicht unverändert. In der Monatsrechnung für Servicefälle werden Spesen netto übernommen, Rabatte setzt Rentalars nicht selbst, und Rundung kann einen Cent von der Personalposition abweichen (DOK-006, DOK-007, DOK-016).

**Material und Fotos**

26. Kamera-Scannen braucht HTTPS und einen Browser mit BarcodeDetector; in Safari und Firefox bleiben Tippen und USB-Scanner (MAT-027).
27. Etiketten: Die Schrift ist Barlow statt der Schrift der Vorlage; im Druckdialog sind Papier und "100 %" zu wählen. Beim Kabeletikett von 90 mm passt der Text um das Kabel dreimal statt viermal (MAT-056, MAT-065).
28. Gibt es von einem Case mehrere gleiche Exemplare mit unterschiedlichem Inhalt, rechnet die Verfügbarkeit vorsichtig mit dem umfangreichsten Inhalt, bis ein Exemplar zugeordnet ist (VFG-017).
29. Fehlende, geklärte Stücke von Mengenmaterial bleiben im Bestand, bis jemand die Menge verringert; Rentalars weist nur darauf hin (PCK-019).
30. Der Lagerplatz ist ein Textfeld ohne Platzverwaltung (keine Belegung, keine freien Plätze). Der Ertrag je Exemplar ist ohne Scan beim Packen für die meisten Kabel geschätzt (MAT-080, MAT-053).
31. Ein Wunsch nach einem Exemplar bei einem Paket aus mehreren Stück lässt die Menge bei 1 und zeigt etwa "1 von 10 Stück"; eine echte Teilung der Position gibt es nicht (PRJ-064).
32. Die Massenübernahme von Produktänderungen in Projekte lässt sich nicht zurücknehmen. Positionen, die beim Einspielen schon vom Produkt abwichen, gelten als "von Hand gesetzt"; das ist eine Annahme (PRJ-137, PRJ-138).

**Projekte und Planung**

33. Bei Teilprojekten wird am Gesamtprojekt abgerechnet. Einen gemeinsamen Lieferschein gibt es nicht; ein Prozentaufpreis "auf das ganze Projekt" rechnet nur auf die eigenen Positionen des Gesamtprojekts; in den Summen der Projektliste zählt ein Teilprojekt doppelt, wenn es zusammen mit seinem Gesamtprojekt gelistet ist; Material-Kosten sind nur die der Zumietungen (PRJ-045, PRJ-046, PRJ-085).
34. Der Gesamtrabatt gilt je Projekt, nicht je Position, und zählt nicht zum Höchstrabatt; in der Nachkalkulation ist er nicht auf Positionen verteilt. Die Karte eines Projekts zeigt der Crew Name und Anschrift von Lieferanten, bei denen eine Zumietung abzuholen ist; ob das so bleibt, entscheidet der Auftraggeber (PRJ-123, UIX-033).

**Personal und Zeit**

35. Schon gespeicherte Zeiteinträge über die Nacht der Zeitumstellung sind nicht umgerechnet; eine Auswertung, die sie enthält, liegt bis zur nächsten Bearbeitung oder Freigabe um eine Stunde daneben (ZEI-002).
36. Zuschläge nach § 3b EStG sind Einstellungen, die steuerlich zu prüfen sind. Es gilt ein Bundesland für den ganzen Betrieb, nicht der Ort des Einsatzes; Personalpositionen pauschal oder je Tag bekommen keine Zuschläge (PER-009, PER-040).
37. Die Stundengrenze (Satz ab der Grenze) zählt je Kalendertag und je Personalposition, nicht über mehrere Positionen einer Person, und gilt nur bei Abrechnung nach Stunden. Wie eine Pauschale in den Wochensummen von "Meine Zeiten" zählen soll, ist offen (PER-035, API-015).
38. Führerscheinklassen sind Qualifikationen; Rentalars weist nur hin und verhindert nichts (LOG-012, PER-014).

**Mail und KI**

39. Antworten per Mail: Ohne den Namen des eigenen Mailservers in den Einstellungen und ohne Authentication-Results ist der Vergleich der Absenderadresse eine Hürde, kein Beweis; ein strenger Modus ist nicht gebaut. Antworten von einer Zweitadresse der Person werden abgewiesen, ein Weg, sie zuzulassen, fehlt (EML-057, PER-032, PER-046).
40. Mails über 25 MB werden mit Text übernommen, ihre Anhänge bleiben im Postfach. Ohne Mailserver (nur Protokoll-Versand in der Konfiguration) landen Mails nur im Protokoll und zählen nicht als gesendet (EML-028, EML-048).
41. KI-Zusammenfassungen sind im Standard aus. Ist ein Anbieter eingeschaltet, gehen Namen und Adressen im Fließtext an ihn; eine Positivliste der Anbieter-Hosts je Betreiber gibt es nicht (EML-056, NFA-079).
42. Die lokale KI ist auf schwacher Hardware langsam (virtuelle Maschine ohne AVX2/FMA, Raspberry Pi); ob sie schnell genug ist, zeigt erst die Benutzung. Den Prozessortyp in der Virtualisierung stellt der Betreiber selbst um (EML-040, ADM-017).

**Gateway und Apps**

43. Gateway: Die Kryptografie ist nach der Festlegung des Gateways gebaut, aber nicht von dritter Seite begutachtet. Es gehen nur API-Aufrufe durch, Antworten sind auf 12 MiB begrenzt. Nicht gebaut: Gateway verpflichtend machen, Sicherheitsereignisse, Koppeln in der Konto-Verwaltung und über die API; der Ablauf des Zertifikats des Gateways wird im Selbsttest nicht geprüft (GWL-001 bis GWL-014).
44. Die Apps und das Gateway selbst sind nicht Teil dieses Pakets (GWL-011).
45. Was die App als zurück abhakt, ist nur abgehakt; gebucht wird im Browser. Ob Felder und Antworten zur Beschreibung der App passen, ist gegen die App selbst nicht erprobt (PCK-026, PCK-027, PCK-028).


## 13. Quellen

Der Katalog stützt sich auf die Angaben des Auftraggebers und der Benutzer;
externe Quellen werden nicht gebraucht.
