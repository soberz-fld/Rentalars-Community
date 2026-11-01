# Import: Material, Produkte, Kunden, Personal

Vier Listen lassen sich aus einer Excel- oder CSV-Datei nach Rentalars
übernehmen (IMP-001): die bisherige **Materialliste** – eine Zeile je
Exemplar –, **Produkte**, **Kunden** und **Personal**. Alle vier Importe sind
so gebaut, dass du sie gefahrlos ausprobieren und beliebig oft wiederholen
kannst:

- **Erst ein Probelauf.** Er prüft die ganze Datei und sagt genau, was der
  Import tun würde. Geschrieben wird dabei nichts.
- **Ganz oder gar nicht.** Hat auch nur eine Zeile einen Fehler, wird nichts
  importiert. Es gibt keinen halb übernommenen Bestand.
- **Wiederholbar.** Was es schon gibt, wird erkannt und aktualisiert, nie
  doppelt angelegt: ein Exemplar an seiner ID, ein Produkt an seiner
  Artikelnummer, ein Kunde an Kundennummer, USt-IdNr., E-Mail-Adresse oder
  Namen – dort ändern leere Zellen nichts (unten „Kunden“) –,
  eine Person an ihrer E-Mail-Adresse oder ihrem Namen. Du kannst die Liste
  also korrigieren und noch einmal einspielen.

Es gibt drei Wege, die dasselbe tun: im Browser (für die meisten der
bequemere), über die API und auf der Kommandozeile des Servers.

Zu jedem Import gibt es auch den Weg zurück: den **Export im
Importformat** – eine CSV-Datei mit genau den Spalten des Imports, im
Klartext (unten, „Export im Importformat“).

## Die Datei

Eine Excel-Datei (`.xlsx`) oder eine CSV-Datei, höchstens 25 MB groß, mit
einer Überschriftenzeile und **einer Zeile je Datensatz**. Leere Zeilen
stören nicht. Bei CSV werden Trennzeichen (Semikolon, Komma, Tabulator) und
Zeichensatz erkannt; beim Zeichensatz probiert der Import der Reihe nach
Byte-Order-Mark, UTF-8, Windows-1252 (wie oft bei Exporten aus Lexware)
und ISO-8859-1, Umlaute kommen also auch aus älteren Programmen richtig an.
Bei Excel-Dateien mit mehreren Blättern gilt das erste Blatt; ein anderes
lässt sich über die API und auf der Kommandozeile wählen.

Alte Excel-Dateien (`.xls`) bitte in Excel als `.xlsx` speichern.

Die Spalten werden an ihren Überschriften erkannt. Groß- und
Kleinschreibung, Zeilenumbrüche in der Überschrift und die Reihenfolge der
Spalten spielen keine Rolle. Heißt eine Spalte bei euch anders, ist das kein
Problem: Du ordnest sie beim Import zu (siehe unten). Welche Überschriften
erkannt werden, steht in den Tabellen der folgenden Abschnitte, im Browser
unter „Welche Spalten werden erkannt?“ und über die API
(`GET /api/v1/imports/{art}`).

**Für alle Listen gilt:**

- Zahlen: `1.250,00`, `1250`, `1250.50`, `499,00 €`, `19 %`. Steht ein
  Komma in der Zahl, ist es das Dezimalzeichen und ein Punkt trennt
  Tausender.
- Ja/Nein-Spalten („Aktiv“) verstehen `ja`/`nein`, `1`/`0`, `x`, `aktiv`/
  `inaktiv`. Eine leere Zelle ändert dort nichts.
- **Eine aus Rentalars exportierte Liste lässt sich wieder einlesen.** In
  der „CSV mit allen Spalten“ der Listen von Produkten, Kunden und Personal
  stehen die Angaben unter Überschriften, die der Import erkennt (Spalten
  wie „Projekte“ oder „Kontakt“, die er nicht kennt, bleiben einfach
  unbeachtet). So lassen sich viele Datensätze in einer Tabellenkalkulation
  ändern und zurückspielen; eine unveränderte Liste ändert beim Einlesen
  nichts. Genau dafür gemacht ist der Export im Importformat,
  auch für das Material (unten).
- **Apostroph vor einer Formel**: Beginnt eine Zelle mit
  einem Apostroph, auf den `=`, `+`, `-` oder `@` folgt – so schreiben die
  Exporte von Rentalars Text, den eine Tabellenkalkulation sonst als Formel
  ausführen würde, etwa `'=Summe` oder `'- defekt` –, nimmt der Import den
  Apostroph weg. Jeder andere Apostroph am Anfang bleibt stehen.

## Material

### Die Spalten

Die 13 Spalten der bisherigen Liste werden an ihren Überschriften erkannt:

| Spalte | Pflicht | Erkannte Überschriften | Wird zu |
|---|---|---|---|
| ID | ja | ID, Inventarnummer, Inventar-Nr, Nr, Nummer | ID des Exemplars |
| Artikelname | ja | Artikelname, Artikelname (evtl. gekürzt), Artikel, Name | Materialmodell |
| Kategorie | ja | Kategorie | Kategorie des Modells |
| Beschreibung | | Spezifikation, Spec, Beschreibung | am Modell |
| Kategoriespezifische Angabe | | Kategoriespezifische Angabe, Kategoriespezifisch, Kat.-spez. Angabe | am Modell, z. B. „5 m“ |
| Einsatz/Verbindung | | Einsatz/Verbindung, Einsatz, Verbindung, Verbaut in | „verbaut in“ – die ID eines anderen Exemplars |
| Seriennummer | | Seriennummer, Serien-Nr, SN, S/N | am Exemplar |
| Notiz | | Notiz, Notizen, Bemerkung | am Exemplar |
| Rechnungsdatum | | Tag des Kaufs, Kaufdatum, Gekauft am, Rechnungsdatum | am Exemplar |
| Kaufnotiz | | Kaufnotiz | am Exemplar |
| Kaufpreis | | Kaufpreis, Preis, EK | am Exemplar |
| Gekauft (Händler) | | Gekauft (Händler), Gekauft, Händler | Händler; wird angelegt, wenn er fehlt |
| Artikelnummer beim Händler | | Artikelnummer beim Händler, Händler-Artikelnummer, Bestellnummer | am Exemplar |

Dazu neun Spalten, die die alte Liste nicht hat, die du aber ergänzen
kannst, wenn du die Angaben ohnehin weißt:

| Spalte | Erkannte Überschriften | Bedeutung |
|---|---|---|
| Hersteller | Hersteller | am Modell; wird angelegt, wenn er fehlt |
| Kurzname | Kurzname | am Modell |
| Menge | Menge, Anzahl, Stückzahl | für Mengenmaterial: eine Zeile mit Stückzahl statt vieler Zeilen |
| Status | Status, Zustand | verfügbar, defekt, in Reparatur, gesperrt, ausgemustert, verkauft, verloren; ohne Angabe sind neue Exemplare verfügbar |
| Lagerort | Lagerort, Lager | der Name eines Lagerorts oder sein Pfad, etwa `Halle 1 > Regal A` – so schreibt ihn der Export im Importformat, denn zwei Regale können gleich heißen; ein Name, den es noch nicht gibt, wird als Lagerort auf oberster Ebene angelegt |
| Produkt | Produkt, Artikelnummer | Artikelnummer eines vorhandenen Produkts, z. B. `K-005`; ordnet das Modell diesem Produkt zu |
| Rechnungsnummer | Rechnungsnummer, Rechnungs-Nr, Re-Nr, Rechnung | am Exemplar |
| Leistung (W) | Leistung, Leistung in W, Watt | am Modell, in Watt |
| Schutzklasse | Schutzklasse, Schutzkl., SK, Protection class | die Schutzklasse des Exemplars, `I`, `II` oder `III` (unten); am Modell nur, wenn es noch keine hat und alle seine Zeilen sich einig sind |

> **Hinweis.** Die erkannten Überschriften folgen der Beschreibung im
> Anforderungskatalog und üblichen Schreibweisen. Eine Spalte, deren
> Überschrift nicht erkannt wird, ordnest du in der Vorschau von Hand zu.

### Wie die Angaben gelesen werden

- **ID:** eine Zahl; führende Nullen sind erlaubt (`0042` und `42` meinen
  dasselbe Exemplar). Jede ID darf in der Datei nur einmal vorkommen.
- **Artikelname:** Zeilen mit demselben Artikelnamen werden zu *einem*
  Materialmodell mit mehreren Exemplaren. Achte deshalb auf einheitliche
  Schreibweise – „XLR Kabel 5m“ und „XLR-Kabel 5 m“ wären zwei Modelle.
  (Zusammenführen lässt sich das später nur von Hand.)
- **Kategorie:** der Name oder das Kürzel einer vorhandenen Kategorie („Ton“
  oder „T“). Eine Unterkategorie schreibst du als `Ton > Mikrofone` (oder
  `Ton / Mikrofone`). Kategorien, die es noch nicht gibt, werden angelegt;
  eine neue Hauptkategorie bekommt ein Kürzel aus ihren Anfangsbuchstaben.
  Der Bericht nennt alle neu angelegten – prüfe die Kürzel, bevor ihr
  Artikelnummern vergebt. Eine neue Installation bringt die
  Hauptkategorien Ton (T), Licht (L), Video/Medien (M), Rigging/Traverse
  (R), Kabel (K), Verkauf (V), Extern zugemietetes Material (E) und
  Veranstaltungstechnik-Dienstleistung (D) mit, auch
  Fremdmaterial (C) für das Material von Kunden, Nebenkosten
  (N). Ein Schrägstrich, der zum
  Namen einer vorhandenen Hauptkategorie gehört, bleibt Teil des Namens:
  „Video/Medien“ ist die Kategorie Video/Medien, „Video/Medien/Beamer“ ihre
  Unterkategorie Beamer. Eindeutig ist immer `Video/Medien > Beamer` oder
  das Kürzel `M`.
- **Einsatz/Verbindung:** die ID des Exemplars, in dem dieses steckt. Die ID
  muss in der Datei oder schon in Rentalars vorkommen. Jede solche Angabe
  wird als **„fest verbaut“** übernommen. Was nur lose in einem Case liegt,
  stellst du danach am Exemplar auf „lose enthalten“ um; der Bericht listet
  alle Verknüpfungen dafür auf. Es gilt: Eine Zelle mit **genau
  einer** ID (`500`, `#0500`, `500.0`) ist die Verbindung. Stehen mehrere
  IDs darin (`#0123, #1234`), wird **keine** Verbindung gemacht – ein
  Exemplar kann nur in einem anderen stecken, und welches gemeint ist, lässt
  sich nicht raten. Dasselbe gilt für Freitext (`Rack`, `Bühne links`). In
  beiden Fällen ist das kein Fehler: der Text der Zelle wird in die Notiz des
  Exemplars übernommen (`Einsatz/Verbindung: #0123, #1234`, hinter einer
  Notiz aus der Datei) und der Bericht nennt die Zeile als Hinweis. Die
  Verbindung legst du danach am Exemplar an. Dieselbe Zeile steht nur einmal
  in der Notiz, auch wenn du die Datei erneut einliest; ändert sich der Text
  in der Zelle, kommt die neue Zeile hinzu, eine frühere wird nicht entfernt.
  Eine Zahl wie `1,5` ist keine Liste von IDs; sehr lange Ziffernfolgen
  (mehr als neun Stellen) sind keine ID und gelten als Text.
Außerdem gilt:

- **Status „Fehler Import“.** Eine Angabe, die Rentalars nicht lesen oder nicht
  annehmen kann – ein Kaufpreis wie „neun“, ein Rechnungsdatum wie
  `32.13.2019`, eine Schutzklasse, die keine ist, ein Status, den es nicht gibt,
  eine Menge, die keine ganze Zahl ist, eine Einsatz-ID, die es nicht gibt, ein
  Verweis auf ein Set ins Leere –, hält den Import **nicht auf**. Das
  Exemplar wird ohne diese Angabe übernommen (ein vorhandenes behält den alten
  Wert), bekommt den Status **„Fehler Import“**, und seine Notiz nennt je Angabe
  eine Zeile: die Überschrift der Spalte aus der Datei und den Inhalt der Zelle
  („Kaufpreis: neun“). Ein Exemplar in diesem Status **steht nicht zur
  Vermietung bereit**, bis du die Felder von Hand ausfüllst und einen anderen
  Status wählst; diesen Status kannst du nicht selbst setzen, nur der Import. Der
  Bericht und der Probelauf zählen die Exemplare („3 Exemplare bekommen den
  Status „Fehler Import““), und jede Zeile steht mit ihrem Hinweis in der Liste.
  Liest du dieselbe Datei später ohne Problem noch einmal ein, ist das Exemplar
  wieder frei: Es nimmt den Status aus der Datei, sonst „verfügbar“; die Zeilen
  in der Notiz stehen nur einmal. **Ausnahme:** Ein Exemplar, das ohnehin nicht vermietbar ist (verkauft, ausgemustert, verloren, gesperrt, defekt, in Reparatur), behält seinen Status und dessen Grund; die Notiz nennt die Angaben trotzdem, und ein späterer fehlerfreier Import macht es nicht wieder verfügbar. **Fehler bleiben** Fehler, wo es keine
  Ersatzangabe gibt: fehlende oder doppelte ID, fehlender Artikelname oder
  fehlende Kategorie, ein Exemplar außerhalb der Datei, das ein Set in einem Set
  verbietet – dann schreibt Rentalars nichts (alles oder nichts).
- **Menge bei Einzelexemplaren.** Ordnest du „Menge (Mengenmaterial)“ der
  Spalte „– nicht importieren –“ zu und ein Exemplar hat noch eine Menge
  (es war Mengenmaterial), gibt es keine Meldung
  „Einzelexemplare haben immer die Menge 1“: Die Menge wird auf 1 gesetzt, der
  alte Wert steht in der Notiz, und der Bericht nennt es als Hinweis.

- **Rechnungsdatum:** ein Datum aus Excel, oder als Text `12.03.2021`,
  `12.03.21`, `2021-03-12`, `12/03/2021`, auch nur `03/2021` oder `2021`.
  Von einem alten Exemplar darf Tag oder Monat unbekannt sein:
  `00.00.2015` (nur das Jahr), `00.05.2015` (Monat und Jahr), auch
  `05.2015`, `2015-05-00` und `2015-00-00`. Rentalars speichert den ersten
  Tag des bekannten Zeitraums (für die Abschreibung) und merkt sich, wie
  genau das Datum ist; angezeigt wird `2015`, `05.2015` oder das volle Datum.
  Die Exportdatei im Importformat schreibt diese Daten wieder so, ein
  Export und erneuter Import verliert also nichts. Eine Zahl wie `215` oder
  `20150` wird als Fehler gemeldet.
- **Kaufpreis:** `1.250,00`, `1250`, `499,00 €`. Netto.
- **Lagerort** (auch als Pfad): Steht ein `>` in der Zelle,
  sucht der Import den Lagerort mit genau diesem Pfad (Groß- und
  Kleinschreibung und die Leerzeichen um `>` zählen nicht). Gibt es den
  Pfad nicht, legt er – wie bei einem unbekannten Namen – einen Lagerort
  **auf oberster Ebene** an, der den ganzen Text als Namen trägt
  (`Halle 1 > Regal B`), statt Halle und Regal einzeln. Neue Lagerorte
  also vorher unter Einstellungen → Lagerorte anlegen.
- **Schutzklasse** (MAT-077, für die elektrische Prüfung nach
  DGUV V3;
  [Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 4,
  „Schutzklasse“): `I`, `II` oder `III`, ebenso `1`, `2`, `3` (auch `2.0`
  aus einer Zahlenzelle) und mit einem Wort davor wie `SK II`,
  `Schutzkl. 2`, `Schutzklasse III` oder `Klasse 1`; Groß- und
  Kleinschreibung zählt nicht. Alles andere ist ein Fehler der Zeile. Die
  Zelle ist die Klasse des **Exemplars**:
  - Ein Materialmodell **ohne** Schutzklasse bekommt die Klasse, die alle
    seine Zeilen der Datei nennen – nur, wenn alle dieselbe nennen (keine
    leer) und keines seiner Exemplare in Rentalars eine eigene hat. Dann
    gilt sie für das ganze Modell, und eine Datei aus dem Export im
    Importformat kommt unverändert zurück.
  - Sonst bekommt jedes Exemplar, dessen Zelle von der Klasse seines
    Modells abweicht, eine **eigene**; dieselbe Klasse wie das Modell oder
    eine leere Zelle heißt „wie das Modell“ und nimmt einem Exemplar seine
    eigene.
  - Die Schutzklasse eines Modells, das schon eine hat, ändert der Import
    nie – das geht auf der Seite des Modells.

### Eigene Felder

Exemplare haben (MAT-073) **eigene Felder**, zusammengefasst
in einem Feldsatz je Materialmodell
([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), Abschnitt 4,
„Eigene Felder“). Der Materialimport liest sie mit:

- **Spalte = Name des Feldes.** Eine Spalte, deren Überschrift der Name
  eines eigenen Feldes ist (Groß- und Kleinschreibung zählt nicht), füllt
  dieses Feld – ohne Zuordnung im Schritt „Spalten zuordnen“. Eine Spalte,
  die dort einem der üblichen Felder zugeordnet ist, bleibt dieses Feld.
  Welche Namen es gibt, steht im Browser unter „Welche Spalten werden
  erkannt?“. Die CSV-Datei der Exemplarliste und der Export im
  Importformat schreiben die Felder unter genau diesen Überschriften.
- **Fehler je Zeile.** Jeder Wert wird gegen den Feldsatz des
  Materialmodells seiner Zeile geprüft, wie ein Wert im Formular: Typ
  (Zahl, Datum `01.03.2027`, „ja“/„nein“, Auswahlwert …), Prüfmuster und
  „eindeutig“. Hat der Feldsatz das Feld nicht („Das Materialmodell „…“
  hat kein eigenes Feld „…“ in seinem Feldsatz.“), passt der Wert nicht
  oder hat schon ein anderes Exemplar denselben eindeutigen Wert, ist das
  ein Fehler dieser Zeile – und wie bei jedem Fehler wird nichts
  importiert.
- **Eine leere Zelle leert den Wert** – die Datei gilt, wie bei
  Seriennummer oder Notiz. Für ein Feld, das nicht zum Feldsatz des Modells
  gehört, wird eine leere Zelle übergangen.
- **Pflichtfelder werden nicht verlangt.** Der Import darf Exemplare ohne
  ihre Pflichtangaben anlegen, wie das Anlegen mehrerer Exemplare auf
  einmal; die Seite des Exemplars nennt, was fehlt.
- **Vertrauliche Felder** („nur mit dem Recht, Einkaufspreise zu sehen“):
  Ohne dieses Recht übergeht der Import die Spalte mit dem Hinweis „Die
  Spalte wird nicht eingelesen: Die Werte dieses Feldes brauchen das Recht,
  Einkaufspreise zu sehen.“

Im Probelauf steht eine Änderung als „Name (eigenes Feld)“ mit bisher und
neu, wie die übrigen Felder; ein vertraulicher Wert ohne das Recht als
„nicht sichtbar“.

Importieren darf, wer Material bearbeiten darf.

## Produkte

Eine Zeile je Produkt. Importieren darf, wer Produkte bearbeiten darf.

| Spalte | Pflicht | Erkannte Überschriften | Bedeutung |
|---|---|---|---|
| Art.-Nr. | ja | Art.-Nr., Artikelnummer, Art.-Nr, Art-Nr, Artikel-Nr., Article no. | Artikelnummer wie `K-005`; erkennt vorhandene Produkte |
| Name | ja | Name, Artikelname, Bezeichnung, Produkt | |
| Kategorie | | Kategorie, Unterkategorie, Category | eine Unterkategorie der Hauptkategorie, siehe unten |
| Art | | Art, Produktart, Kind | Mietprodukt, Verkaufs- oder Verbrauchsprodukt, Dienstleistung, Set, Aufpreis, Zumietung, Nebenkosten |
| Preis | | Preis, Mietpreis, Preis (netto), Tagespreis, Price | netto |
| Verkaufspreis | | Verkaufspreis, Verkaufspreis (netto), VK, Sale price | netto |
| Höchstrabatt | | Höchstrabatt, Höchster Rabatt, Höchster Rabatt in Prozent, Max. Rabatt, Maximaler Rabatt, Maximum discount | in Prozent, 0 bis 100; leer: keine Grenze, 0: nicht rabattierbar |
| Einheit | | Einheit, Unit | Name oder Abkürzung einer vorhandenen Einheit, auch ohne Klammerteil („Stück“ für „Stück (Miete)“), siehe unten |
| Steuerart | | Steuerart, Steuersatz, MwSt, USt, Tax rate | Name einer vorhandenen Steuerart oder ihr Satz, z. B. `19` |
| Abrechnungsart | | Abrechnungsart, Abrechnung, Billing mode | Tagesmiete je Stück, Tagesmiete je Set, pauschal, nach Stunden, nach Aufwand |
| GTIN/EAN | | GTIN/EAN, GTIN, EAN, Barcode | |
| Beschreibung | | Beschreibung, Description | |
| Interne Notiz | | Interne Notiz, Notiz, Bemerkung, Note | |
| Mindestbestand | | Mindestbestand, Minimum stock | ganze Zahl; leer oder 0: keine Warnung |
| Eigentümer | | Eigentümer, Eigentum, Eigentümerin, Kunde, Owner | nur für Kundenmaterial: Kundennummer oder Name des Kunden, dem das Produkt gehört; leer: eigenes Material |
| Aktiv | | Aktiv, Active | ja/nein |

- **Die Artikelnummer entscheidet.** Gibt es ein Produkt mit dieser Nummer,
  wird es aktualisiert, sonst angelegt. Kleinbuchstaben und Leerzeichen
  stören nicht (`k-005` ist `K-005`). Die Buchstaben vor dem Bindestrich
  nennen die **Hauptkategorie**; eine Kategorie mit diesem Kürzel muss es
  geben – der Produktimport legt keine Kategorien an.
- **Kategorie:** Name oder Pfad (`Ton > Mikrofone`) einer Unterkategorie
  dieser Hauptkategorie. Ist die Zelle leer, gilt die Hauptkategorie.
- **Art und Abrechnungsart** verstehen die Bezeichnungen aus Rentalars und
  gängige Wörter (Miete, Verkauf, Verbrauch, Verbrauchsmaterial, Zuschlag;
  pro Tag, täglich, Pauschale, pro Stunde, stündlich). Was ein **neues**
  Produkt in der Datei nicht hat – Art, Einheit, Steuerart, Abrechnungsart –,
  kommt aus den Vorgaben seiner Kategorie, wie bei einem Produkt, das im
  Browser angelegt wird. Jede **Dienstleistung** gehört zu
  genau einer Funktion des Personals: Eine neue legt ihre Funktion mit
  demselben Namen an; einen Namen, den schon eine Funktion trägt, meldet
  der Probelauf als Fehler. Transport und Fahrtkosten importierst du als
  „Nebenkosten“.
- **Einheit:** Eine neue Installation bringt die Einheiten Stück
  (Miete), Stück (Verkauf), Set (Miete), Set (Verkauf), Stunde, Tag,
  Kilometer, Pauschal, Angefangener Liter, Angefangener Meter und
  Angefangenes Kilogramm mit. Ein genau passender Name gilt immer. Passt
  der Text auf mehrere Einheiten – ein Name ohne seinen Klammerteil wie
  „Stück“ oder „Set“, oder eine Abkürzung, die mehrere teilen, wie „Stk.“
  –, nimmt der Import die Einheit, die die Kategorie des Produkts vorgibt:
  im Ton „Stück (Miete)“, im Verkauf „Stück (Verkauf)“. Gibt die Kategorie
  keine davon vor, gilt die erste nach dem Namen. Eine ältere
  Installation, die noch die Einheit „Stück“ hat, nimmt bei „Stück“ diese.
- **Preise** importiert nur, wer Preise sehen darf – ebenso den
  **Höchstrabatt**. Ist „Preis“, „Verkaufspreis“ oder „Höchstrabatt“ eine
  Spalte zugeordnet und fehlt das Recht, bricht der Import mit „Preise zu
  importieren braucht das Recht, Preise zu sehen.“ ab – dann diese Spalten
  auf „nicht importieren“ stellen.
- **Eigentümer**: Material, das Kunden bei euch lagern – das
  Mischpult einer Band –, ist **Kundenmaterial** in einer dafür markierten
  Kategorie, etwa C „Fremdmaterial“
  ([Benutzerhandbuch](../handbuch/benutzerhandbuch.md), „Kundenmaterial“).
  Die Spalte nennt den Kunden mit seiner **Kundennummer** oder seinem
  **Namen** (beim Namen zählt Groß- und Kleinschreibung nicht); heißen
  mehrere Kunden gleich, verlangt der Import die Kundennummer. Den Kunden
  muss es geben – der Produktimport legt keine Kunden an. Ein Produkt einer
  Kategorie für Kundenmaterial braucht einen Eigentümer, ist ein
  Mietprodukt oder Set und darf keinen Preis und keinen Verkaufspreis
  haben (ein Höchstrabatt wird verworfen); ein Produkt einer anderen
  Kategorie darf keinen Eigentümer haben. Sonst meldet der Probelauf die
  Zeile als Fehler. Ist das Produkt schon in einem Projekt geplant, lässt
  sich sein Eigentümer nicht mehr ändern. Die exportierte Produktliste
  („Spalten“ → „Eigentümer“ oder „CSV mit allen Spalten“) enthält den
  Namen des Kunden.

## Kunden

Eine Zeile je Kunde. Importieren darf, wer Kunden bearbeiten darf. Auch
der **Kontaktexport von Lexware** (CSV) lässt sich unverändert
einlesen (IMP-013): Seine Spalten – „Firmenname“, „Straße 1“, „PLZ 1“,
„Ansprechpartner 1 Vorname“ und so weiter – stehen in der Tabelle, und
seinen Zeichensatz erkennt der Import (oben, „Die Datei“).

| Spalte | Pflicht | Erkannte Überschriften | Bedeutung |
|---|---|---|---|
| Nummer | | Nummer, Kundennummer, Kunden-Nr., Kd.-Nr., Number | erkennt vorhandene Kunden, siehe unten |
| Name | (*) | Name, Firmenname, Firma, Kunde, Name oder Firma | |
| Vorname | (*) | Vorname, First name | ohne Firmenname: Vor- und Nachname sind der Name einer Privatperson |
| Nachname | (*) | Nachname, Familienname, Last name | |
| Anrede | | Anrede, Salutation | wird nur bei Ansprechpersonen gespeichert, nicht beim Kunden |
| Art | | Art, Kundenart, Kind | Firma oder Organisation (auch Firma, Unternehmen, Organisation), Privatperson (auch Privat) |
| Zusatz | | Zusatz, Adresszusatz 1, Adresszusatz, Namenszusatz, Abteilung | |
| Straße | | Straße, Straße 1, Strasse 1, Strasse, Straße und Hausnummer, Anschrift, Street | |
| Postleitzahl | | Postleitzahl, PLZ 1, PLZ, Postal code | |
| Ort | | Ort, Ort 1, Stadt, City | |
| Land | | Land, Land 1, Country | |
| Lieferadresse Zusatz, Straße, Postleitzahl, Ort, Land | | Lieferadresse Zusatz, Adresszusatz 2; Lieferadresse Straße, Straße 2, Strasse 2; Lieferadresse Postleitzahl, PLZ 2, Lieferadresse PLZ; Lieferadresse Ort, Ort 2; Lieferadresse Land, Land 2 | eine Lieferadresse des Kunden |
| E-Mail | | E-Mail, E-Mail 1, Email 1, E-Mail-Adresse, Mail, Email | |
| E-Mail 2 | | E-Mail 2, Email 2 | kommt in die Notiz |
| Telefon | | Telefon, Telefon 1, Tel., Telefonnummer, Phone | |
| Telefon 2 | | Telefon 2, Tel. 2 | kommt in die Notiz |
| USt-IdNr. | | USt-IdNr., USt-ID, UStID, Umsatzsteuer-ID, Umsatzsteuer ID, VAT ID | z. B. `DE123456789` |
| Steuernummer | | Steuernummer, Steuer-Nr., St.-Nr., Tax number | |
| Zahlungsziel (Tage) | | Zahlungsziel (Tage), Zahlungsziel, Payment terms (days) | leer: wie in den Firmendaten |
| Standardrabatt % | | Standardrabatt %, Rabatt, Standardrabatt | |
| Notiz | | Notiz, Bemerkung, Note | |
| Ansprechperson | | Ansprechperson, Kontakt, Ansprechpartner, Ansprechpartnerin, Kontaktperson | Name der Ansprechperson |
| E-Mail der Ansprechperson | | E-Mail der Ansprechperson, E-Mail Ansprechpartner | |
| Telefon der Ansprechperson | | Telefon der Ansprechperson, Telefon Ansprechpartner | |
| Ansprechpartner 1 und 2 | | Ansprechpartner 1, Ansprechpartner 1 Anrede, … Vorname, … Nachname, … E-Mail, … Telefon; ebenso mit 2 | zwei weitere Ansprechpersonen, wie im Kontaktexport von Lexware |
| Aktiv | | Aktiv, Active | ja/nein |

(*) „Name“ oder „Vorname“ bzw. „Nachname“ muss eine Spalte zugeordnet sein.

Die Spalte „Lieferantennummer“ des Lexware-Exports übernimmt der Import
nicht; der Bericht sagt das. Die Spalte „Kontakt“ der aus Rentalars
exportierten Kundenliste (E-Mail und Telefon) erkennt er als solche und
lässt sie aus, sodass die Liste unverändert zurückkommt.

**Wer ist wer.** Der Import sucht für jede Zeile den passenden
Kunden, der Reihe nach

1. an der **Kundennummer**,
2. an der **USt-IdNr.**,
3. an der **E-Mail-Adresse** – des Kunden oder einer seiner
   Ansprechpersonen –,
4. am **Namen**, ohne Rücksicht auf Groß- und Kleinschreibung, Satzzeichen
   und Rechtsform, mit ausgeschriebenen Umlauten: „Müller GmbH“ ist
   „MUELLER gmbh“.

Findet ein Schritt mehrere, entscheiden die folgenden. Bleiben mehrere
übrig, wird die Zeile ein neuer Kunde, und der Probelauf nennt, wer in
Frage kam („Mehrere Kunden passen (…), deshalb wird ein neuer Kunde
angelegt.“) – trag dann die Kundennummer in die Datei ein. Dabei ist der
Import vorsichtig:

- Ein Kunde wird von höchstens einer Zeile einer Datei gefunden; eine
  zweite Zeile, die genauso aussieht, wird ein neuer Kunde mit Hinweis
  (trägt sie dieselbe Kundennummer, ist es ein Fehler).
- Eine Privatperson wird nie einer Firma mit Rechtsform im Namen
  zugeordnet, und nur über ihre eigene E-Mail-Adresse, nicht über die
  einer Ansprechperson.
- Passt nur die Nummer, aber weder Name noch USt-IdNr. noch
  E-Mail-Adresse, warnt der Probelauf. Lexware zählt ebenfalls ab 10001;
  seine Nummern können also ganz andere Kunden treffen. Stammen die
  Nummern der Datei aus einem anderen Programm, stell die Spalte
  „Kundennummer“ auf „– nicht importieren –“; dann erkennt der Import die
  Kunden an USt-IdNr., E-Mail-Adresse und Namen.

Ein gefundener Kunde wird **ergänzt, nie geleert**:

- **Leere Zellen ändern nichts** – in jeder Spalte, bei jedem
  Kundenimport. Ein Feld lässt sich über den Import deshalb nicht
  leeren; das geht im Browser.
- Ein Name, der sich nur in der Schreibweise unterscheidet, bleibt, wie er
  in Rentalars steht.
- Nennt die Datei eine **andere Straße oder einen anderen Ort**, wird das
  die Adresse des Kunden, und die bisherige bleibt als weitere
  Rechnungsadresse erhalten. Dieselbe Adresse erkennt der Import auch, wenn
  einmal „Str.“ und einmal „Straße“ steht oder die Postleitzahl fehlt.
- Eine **Lieferadresse** kommt dazu, außer der Kunde hat schon eine mit
  derselben Straße, Postleitzahl und demselben Ort.
- Eine **Ansprechperson** kommt dazu, außer es gibt schon eine mit
  demselben Namen oder derselben E-Mail-Adresse; die wird ergänzt. Die
  erste Ansprechperson eines Kunden wird seine Hauptansprechperson.
- „E-Mail 2“ und „Telefon 2“ kommen einmal in die Notiz.
- Wurde der Kunde über USt-IdNr., E-Mail-Adresse oder Namen gefunden und
  die Datei nennt eine andere Nummer, behält er seine Nummer in Rentalars
  („Die Datei nennt die Nummer …; der Kunde behält seine Nummer …“).

Findet der Import keinen Kunden, legt er einen neuen an – mit der Nummer
aus der Datei, wenn Rentalars sie noch nicht kennt; so behalten Kunden
ihre Nummer aus dem bisherigen Programm. Sonst, oder ohne Nummer, bekommt
er die nächste Nummer des Nummernkreises. Sieht ein neuer Kunde einem
vorhandenen ähnlich – ähnlicher Name oder gleiche E-Mail-Adresse –, nennt
der Probelauf das als Hinweis („Ist vielleicht derselbe wie 10003 …“); der
Hinweis hält den Import nicht auf. Ein anonymisierter Kunde wird nicht
geändert.

Der **Bericht** nennt für jede Zeile, ob der Kunde neu ist, mit wem er
zusammengeführt wird und woran er erkannt wurde, oder ob er unverändert
bleibt.

- **Standardrabatt** importiert nur, wer Preise sehen darf; sonst bricht der
  Import ab („Rabatte zu importieren braucht das Recht, Preise zu sehen.“).

## Personal

Eine Zeile je Person. Importieren darf, wer das Personal bearbeiten darf.
Jede Person ist ein Konto (AUT-026): Eine neu angelegte Person
bekommt ein Konto mit einem Benutzernamen aus ihrem Namen, ohne Passwort
und mit der Rolle Crew, eine freie Kraft mit der Rolle Freie Kraft.
Anmelden kann sie sich erst, wenn sie unter Einstellungen → Nutzer
eingeladen wird oder ein Einmal-Passwort bekommt.

| Spalte | Pflicht | Erkannte Überschriften | Bedeutung |
|---|---|---|---|
| Name | (*) | Name, „Name, Vorname“, „Nachname, Vorname“, Person | „Nachname, Vorname“ wie in der exportierten Liste, oder „Vorname Nachname“ |
| Vorname | | Vorname, First name | |
| Nachname | (*) | Nachname, Familienname, Last name | |
| Art | | Art, Beschäftigung, Anstellung, Kind | Festangestellte (auch fest, festangestellt, angestellt, Mitarbeiter), Aushilfe (auch Minijob), Freie Kraft (auch frei, Freelancer, freiberuflich) |
| Funktionen | | Funktionen, Funktion, Job functions, Tätigkeiten | siehe unten |
| E-Mail | | E-Mail, E-Mail-Adresse, Mail, Email | erkennt vorhandene Personen |
| Telefon | | Telefon, Tel., Mobil, Handy, Phone | |
| Firma | | Firma, Company | |
| Straße | | Straße, Strasse, Anschrift, Street | |
| Postleitzahl | | Postleitzahl, PLZ, Postal code | |
| Ort | | Ort, Stadt, Wohnort, City | |
| Steuernummer | | Steuernummer, St.-Nr., Tax number | |
| USt-IdNr. | | USt-IdNr., USt-ID, VAT ID | |
| Notiz | | Notiz, Bemerkung, Note | |
| Aktiv | | Aktiv, Active | ja/nein |

(*) „Name“ oder „Nachname“ muss eine Spalte zugeordnet sein.

- **Wer ist wer:** Eine Person wird an ihrer E-Mail-Adresse erkannt, sonst an
  Vor- und Nachname. Gibt es mehrere Personen gleichen Namens und keine
  E-Mail-Adresse, die sie unterscheidet, meldet der Probelauf einen Fehler.
  Wer nicht gefunden wird, wird angelegt. Eine E-Mail-Adresse gehört zu
  genau einem Konto; nennt die Datei für eine Person die Adresse eines
  anderen Kontos, ist das ein Fehler („Diese E-Mail-Adresse gehört schon
  zu einem anderen Nutzer.“).
- **Funktionen** stehen durch Komma oder Semikolon getrennt in einer Zelle:
  `Tontechnik, Licht`. Jede muss es in Rentalars schon geben. Eigene Sätze
  stehen hinter einem Doppelpunkt, der **Stundensatz** und nach
  einem Schrägstrich der **Tagessatz**:

  | Zelle | bedeutet |
  |---|---|
  | `Tontechnik: 35,00/280,00` | Tontechnik mit 35,00 € die Stunde und 280,00 € am Tag |
  | `Tontechnik: 35,00` | nur ein eigener Stundensatz |
  | `Licht: /250` | nur ein eigener Tagessatz |
  | `Rigging` | ohne eigene Sätze – es gelten die Richtwerte der Funktion |

  Mehrere zusammen: `Tontechnik: 35,00/280,00, Licht: /250, Rigging`. Ein
  Komma in einem Satz (`35,00`) trennt keine Funktionen. Eine **neue**
  Funktion bekommt die Sätze der Zeile ohne „Gültig ab“, also von Anfang
  an – oder keine eigenen; einen Richtwert kopiert der Import
  nicht als eigenen Satz hinein, und eine Funktion ohne Richtwert
  braucht keinen Satz. Hat die Person die Funktion schon, behält sie
  ihre Sätze, es sei denn, die Zeile nennt andere; die gelten dann ab dem
  Tag des Imports, und ein Satz, den die Zeile nicht nennt, wird aus den
  bisherigen übernommen. Der Import nimmt nie eine Funktion weg. Die aus
  Rentalars exportierte Personenliste nennt nur die Funktionen, ohne
  Sätze; eingelesen ändert sie an den Sätzen nichts.
- **Stunden- und Tagessätze** sind Personalkosten: Sie importiert nur, wer
  Personalkosten sehen darf („Stundensätze zu importieren braucht das
  Recht, Personalkosten zu sehen.“). Funktionen ohne Sätze darf jeder
  zuordnen, der das Personal bearbeiten darf.

## Im Browser

Die Importe stehen dort, wo die Listen sind, und gesammelt unter
**Einstellungen → Import und Export**:

| Liste | Wo | Recht |
|---|---|---|
| Material | Material → Import, Reiter „Materialexemplare“ | Material bearbeiten |
| Produkte | Material → Import, Reiter „Produkte“ (der Knopf „Import“ über der Produktliste ist „Kauf einpflegen“ gewichen) | Produkte bearbeiten |
| Kunden | Kunden → „Import“ | Kunden bearbeiten |
| Personal | Personal → „Import“ | Personal bearbeiten |

1. **Datei wählen** und hochladen.
2. **Spalten zuordnen.** Rentalars zeigt für jedes Feld, welche Spalte es
   erkannt hat, und die ersten Werte daraus. Stimmt etwas nicht, wähle die
   richtige Spalte – oder „– nicht importieren –“. Dann **„Probelauf:
   prüfen, ohne zu schreiben“**.
3. Der Bericht zeigt, was geschehen würde, oder die Fehler mit Zeile und
   Spalte. Ohne Fehler erscheint **„Jetzt importieren“**.

**Probelauf und Import laufen als Aufgabe im Hintergrund** (NFA-041). Die
Seite zeigt den Fortschritt und, sobald die Aufgabe fertig ist, den Bericht.
Du kannst währenddessen weiterarbeiten; wenn sie fertig ist, bekommst du eine
Benachrichtigung, und unter Mein Konto → Aufgaben im Hintergrund findest du
sie wieder. Eine Obergrenze für die Zahl der Zeilen gibt es im Browser
nicht. (Zum Vergleich: Prüfen und Importieren dauerten bei
1.650 Zeilen Material etwa eine Viertelminute.)

Die hochgeladene Datei bleibt zwischen den Schritten auf dem Server
(`/var/lib/rentalars/imports/`, unter einem zufälligen Namen). Nach dem
Import, mit „Andere Datei verwenden“ oder spätestens nach zwei Tagen wird
sie gelöscht.

Oben auf der Seite jedes Imports und unter Einstellungen
→ Import und Export neben jedem Import steht der Link **„Export im
Importformat“** (unten).

## Über die API

```
GET  /api/v1/imports/{art}          welche Felder, welche Überschriften erkannt werden
POST /api/v1/imports/{art}          Probelauf oder Import
GET  /api/v1/imports/{art}/export   der Export im Importformat (unten)
```

`{art}` ist `material`, `products`, `customers` oder `people`. Es gelten
dieselben Rechte wie im Browser. `POST` nimmt die Datei als `file`
(multipart) und diese Angaben:

| Angabe | Bedeutung |
|---|---|
| `dry_run` | `true` (Voreinstellung): nur prüfen; `false`: importieren |
| `mapping` | Spalten von Hand zuordnen, als JSON: `{"name": "Gerät"}`; der Wert ist die Überschrift, die Nummer der Spalte (ab 0) oder leer für „nicht importieren“ |
| `sheet` | bei Excel-Dateien mit mehreren Blättern: welches Blatt (sonst das erste) |
| `background` | `true`: als Aufgabe im Hintergrund |

**Ohne `background`** wird in der Anfrage selbst importiert, und eine Datei
darf höchstens **5.000 Zeilen** haben – eine Anfrage an Rentalars darf
höchstens zwei Minuten dauern. Die Antwort ist der Bericht (Status 200, mit
Fehlern 400), dazu unter `mapping`, welche Überschrift welches Feld
gefüllt hat. Jeder Fehler nennt `row`, `column`, `message` und als `text`
alles in einem Satz.

**Mit `background=true`** gibt es keine Obergrenze. Die Antwort (Status
202) ist die Aufgabe; `GET /api/v1/jobs/{id}` sagt, wie weit sie ist, und
enthält, wenn sie fertig ist, den Bericht unter `result.report`:

```sh
curl -H "Authorization: Bearer rl_…" \
     -F file=@kunden.xlsx -F dry_run=false -F background=true \
     https://rentalars.example.de/api/v1/imports/customers
```

## Auf der Kommandozeile

Wenn du lieber auf dem Server arbeitest. Die Befehle kennen keine
Obergrenze.

Die Datei muss für das Dienstkonto von Rentalars lesbar sein. Lege sie am
einfachsten in das dafür vorgesehene Verzeichnis:

```sh
sudo cp bestand.xlsx /var/lib/rentalars/imports/
sudo chmod 644 /var/lib/rentalars/imports/bestand.xlsx
```

Dasselbe Verzeichnis nutzt der Browser für seine hochgeladenen Dateien.
Die tägliche Wartung löscht dort aber nur diese – sie tragen einen
zufälligen Namen aus 32 Zeichen –, wenn sie älter als zwei Tage sind. Was
du selbst hineinlegst, bleibt liegen; lösch es nach dem Import.

### Material: `import_material`

**Probelauf** – das ist der Normalfall, ohne weitere Angabe:

```sh
sudo rentalars import_material /var/lib/rentalars/imports/bestand.xlsx
```

```
Datei: /var/lib/rentalars/imports/bestand.xlsx, 5 Zeilen
Spaltenzuordnung:
  inventory_number         ID *                             “ID”
  name                     Artikelname *                    “Artikelname (evtl. gekürzt)”
  category                 Kategorie *                      “Kategorie”
  …
  manufacturer             Hersteller                       –

Materialmodelle: 3 neu, 0 geändert
Exemplare: 5 neu, 0 geändert, 0 unverändert
2 Exemplar(e) als „fest verbaut“ verknüpft (einzelne bei Bedarf auf „lose enthalten“ umstellen):
  0310 → 0500
  0311 → 0500
Höchste ID: 0743, nächste neue ID: 0744
Probelauf ohne Fehler. Mit --commit wird importiert.
```

Ein Strich in der Spaltenzuordnung heißt: Für dieses Feld wurde keine Spalte
gefunden.

**Mit Fehlern** sieht das Ende so aus – alle Fehler der Datei auf einmal,
damit du sie in einem Durchgang beheben kannst:

```
Fehler: Zeile 6, Artikelname: Der Artikelname fehlt.
Fehler: Zeile 7, Kategorie: Die Kategorie fehlt.
Fehler: Zeile 9, ID: Die ID 0500 kommt schon in Zeile 4 vor.
CommandError: 3 Fehler. Es wurde nichts importiert.
```

Eine Angabe, die sich nicht lesen lässt (Kaufpreis „neun“, Rechnungsdatum
„32.13.2019“, Einsatz/Verbindung auf eine ID, die es nicht gibt), ist
**kein Fehler** mehr: Der Bericht nennt sie als Hinweis, das Exemplar bekommt den
Status „Fehler Import“ (oben), und es wird trotzdem importiert.

Die Zeilennummer ist die aus Excel.

**Wirklich importieren:**

```sh
sudo rentalars import_material /var/lib/rentalars/imports/bestand.xlsx --commit
```

### Produkte, Kunden, Personal: `import_data`

Genauso, mit der Art der Liste vorneweg – `products`, `customers` oder
`people`:

```sh
sudo rentalars import_data customers /var/lib/rentalars/imports/kunden.xlsx            # Probelauf
sudo rentalars import_data customers /var/lib/rentalars/imports/kunden.xlsx --commit   # importieren
```

```
Datei: /var/lib/rentalars/imports/kunden.xlsx, 3 Zeilen
Spaltenzuordnung:
  number                     Nummer                           “Kundennummer”
  name                       Name *                           “Firma”
  …
  active                     Aktiv                            –

Hinweis: Zeile 4: Ist vielleicht derselbe wie 10003 Kulturverein Musterstadt (ähnlicher Name).
Datensätze: 2 neu, 1 geändert, 0 unverändert
Probelauf ohne Fehler. Mit --commit wird importiert.
```

Auf dem Server gelten alle Rechte: Preise, Rabatte, Stunden- und
Tagessätze werden ohne Weiteres übernommen. `import_data material` gibt es
auch und nennt die Zahl der Exemplare („Exemplare: … neu, … geändert, … unverändert“); für die
Materialliste ist aber `import_material` gesprächiger (Modelle,
Verknüpfungen, nächste ID).

**Weitere Angaben** (beide Befehle):

| Angabe | Zweck |
|---|---|
| `--show-mapping` | nur die erkannte Spaltenzuordnung zeigen |
| `--map "FELD=SPALTE"` | eine Spalte von Hand zuordnen, z. B. `--map "inventory_number=Inv.-Nr." --map "name=Gerät"`; mehrfach verwendbar. `FELD` ist der Name ganz links in der Spaltenzuordnung. `--map "note="` lässt ein Feld weg. |
| `--sheet NAME` | bei Excel-Dateien mit mehreren Blättern: welches Blatt (sonst das erste) |

## Nach dem Import

**Material:**

1. **Nummernkreis.** Die nächste neue Material-ID liegt jetzt hinter der
   höchsten importierten. Nachsehen und ändern: „Einstellungen → Nummernkreise“.
2. **Neue Kategorien prüfen** („Einstellungen → Kategorien und Kürzel“):
   Stimmen die Kürzel? Solange noch kein Produkt eine Artikelnummer mit dem
   Kürzel trägt, lässt es sich ändern.
3. **Lose Inhalte umstellen.** Alles aus „Einsatz/Verbindung“ gilt nach dem
   Import als fest verbaut. Kabel im Case, Mikrofone im Koffer: am Exemplar
   auf „lose enthalten“ stellen, damit sie auch einzeln verplant werden
   können.
4. **Produkte zuordnen.** Material lässt sich erst verplanen, wenn es einem
   Produkt zugeordnet ist. „Materialverwaltung → Offene Punkte → Material
   ohne Produkt“ zeigt, was noch fehlt.
   Lege die Produkte an – auch das geht mit einem Import, siehe oben – und
   trage sie am Modell ein; das gilt dann für alle Exemplare des Modells. Wie
   das geht, steht im [Benutzerhandbuch](../handbuch/benutzerhandbuch.md),
   „Material einem Produkt zuordnen“.

**Kunden:** Kunden mit übernommener Nummer verschieben den Nummernkreis
nicht; neue Kunden bekommen die nächste freie Nummer, vergebene werden
übersprungen.

Jeder Import steht mit Zeitpunkt, Nutzer und Zahlen im Änderungsprotokoll;
jeder angelegte oder geänderte Datensatz hat seinen eigenen Eintrag.

## Noch einmal importieren

Du hast in der Liste weitergearbeitet oder Fehler korrigiert? Spiel sie
einfach noch einmal ein.

- Was es schon gibt (gleiche ID, Artikelnummer, E-Mail-Adresse oder
  gleicher Name einer Person; bei Kunden siehe oben, „Wer ist wer“), wird
  mit den Angaben der Datei **aktualisiert**. Der Probelauf zeigt, wie viele
  sich ändern würden.
- Felder, für die die Datei **keine Spalte** hat – oder deren Spalte du auf
  „nicht importieren“ stellst –, bleiben unberührt. Was ihr in
  Rentalars gepflegt habt, geht so nicht verloren.
- Datensätze, die in der Datei **fehlen**, bleiben, wie sie sind. Der Import
  löscht nie etwas.

**Leere Zellen** wirken je nach Spalte verschieden:

- **Material:** Für **Seriennummer, Notiz, Rechnungsdatum,
  Rechnungsnummer, Kaufnotiz, Kaufpreis, Händler, Artikelnummer beim
  Händler** und
  **Einsatz/Verbindung** gilt die Datei – auch dort, wo ihre Zelle leer ist:
  Eine leere Zelle leert die Angabe in Rentalars bzw. löst die Verknüpfung.
  **Beschreibung, kategoriespezifische Angabe, Leistung, Hersteller,
  Kurzname, Produkt, Menge, Status** und **Lagerort** werden nur gesetzt,
  wo die Datei etwas enthält. Eine Verknüpfung, die es schon gibt, bleibt, wie sie ist –
  auch wenn ihr sie auf „lose enthalten“ umgestellt habt. In
  einer Spalte eines **eigenen Feldes** gilt ebenfalls die
  Datei: Eine leere Zelle leert den Wert (oben, „Eigene Felder“). Ebenso
  bei der **Schutzklasse** am Exemplar: Eine leere Zelle
  nimmt ihm seine eigene; die Klasse eines Modells, das schon eine hat,
  bleibt (oben, „Wie die Angaben gelesen werden“).
- **Produkte, Personal:** Für die Text-, Preis- und Zahlenspalten gilt die
  Datei; eine leere Zelle leert die Angabe (beim Mindestbestand: keine
  Warnung). Ein leerer Name eines Produkts und ein fehlender Nachname einer
  Person sind Fehler. Eine leere „Kategorie“ setzt ein Produkt auf seine
  Hauptkategorie. **Art, Abrechnungsart, Einheit, Steuerart** und
  **Aktiv** bleiben bei einer leeren Zelle, wie sie sind; ebenso die
  Funktionen einer Person.
- **Kunden:** Eine leere Zelle ändert nie etwas (oben,
  „Kunden“). Eine Zeile ganz ohne Namen – weder Name noch Vor- oder
  Nachname – ist ein Fehler.

Sobald ihr mit Rentalars arbeitet, ist Rentalars die Wahrheit. Der
wiederholte Import ist für die Übergangszeit gedacht und für Änderungen an
vielen Datensätzen auf einmal (exportieren, in der Tabellenkalkulation
ändern, wieder einlesen), nicht als dauerhafter Abgleich mit einer
Excel-Liste.

## Export im Importformat

Zu jedem der vier Importe gibt es (IMP-017) einen Export, der
genau das Format des Imports hat – damit sich eine Liste ohne Rentalars
weiterverwenden, in einer Tabellenkalkulation bearbeiten und wieder
einlesen lässt. Im Browser unter **Einstellungen → Import und Export**
neben jedem Import und oben auf der Seite des Imports („Export im
Importformat“), über die API mit `GET /api/v1/imports/{art}/export`
(`material`, `products`, `customers`, `people`).

**Die Datei:**

- **Genau die Spalten des Imports**, unter denselben Überschriften und in
  derselben Reihenfolge wie in den Tabellen oben; beim Material danach eine
  Spalte je eigenem Feld, mit dem Namen des Feldes als Überschrift.
- **Klartext statt interner IDs:** die ID eines Exemplars mit führenden
  Nullen, „Einsatz/Verbindung“ als ID des Geräts, Kategorie und Lagerort
  als Pfad (`Ton > Mikrofone`, `Halle 1 > Regal A`), Händler, Hersteller,
  Einheit und Steuerart mit ihrem Namen, das Produkt eines Modells und der
  Eigentümer von Kundenmaterial mit Artikel- bzw. Kundennummer, die
  Funktionen einer Person mit ihren heute geltenden Sätzen
  (`Licht: 28,00/250,00, Tontechnik: /280,00, Rigging`), ein als Set
  gekauftes Exemplar mit `#0851` in der Spalte des Kaufpreises, in der Spalte „Schutzklasse“ die Klasse, die für das Exemplar
  gilt – seine eigene, sonst die seines Modells –, als `I`, `II` oder
  `III`.
- **Geschrieben, wie der Import liest:** UTF-8 mit Byte-Order-Mark,
  Semikolon, Zahlen mit Dezimalkomma und ohne Tausenderpunkt (`1234,50`),
  Datum `31.12.2027`, „ja“/„nein“, Auswahlwerte mit ihren deutschen
  Namen – immer auf Deutsch wie die Überschriften, gleich in welcher
  Sprache der Nutzer arbeitet. Text, den eine Tabellenkalkulation als
  Formel ausführen würde, bekommt einen Apostroph davor; der Import nimmt
  ihn wieder weg (oben, „Die Datei“).

**Rechte.** Herunterladen darf, wer die Liste lesen darf (Lesen im Modul
des Imports). Spalten mit Preisen, dem Höchstrabatt und den Sätzen der
Fahrzeuge brauchen das Recht „Preise und Kalkulation sehen“, Kaufpreise
und interne Kosten der Fahrzeuge „Einkaufs- und Kaufpreise sehen“,
vertrauliche eigene Felder ebenso; ohne das Recht **fehlt die Spalte**.
Bei den Personen bleibt die Spalte „Funktionen“, nennt ohne das Recht
„Stundensätze und Personalkosten sehen“ aber nur die Funktionen. Wer eine
solche Datei wieder importiert, lässt diese Werte, wie sie sind – für die
fehlenden Spalten gilt, was oben unter „Noch einmal importieren“ steht.

**Hin und zurück ändert nichts.** Wieder importiert, nennt der Probelauf
jede Zeile „unverändert“; in der Tabellenkalkulation bearbeitet, ändert
die Datei genau das, was bearbeitet wurde. So ist es getestet.

**Was nicht darin steht:** was der Import nicht kennt – beim Material die
eigene Beschreibung und die eigenen kategoriespezifischen Angaben eines
Exemplars, bei Kunden ein vierter Ansprechpartner, weitere Rechnungs- und
Lieferadressen und die Position des ersten Ansprechpartners, natürlich
auch Projekte und ihre Positionen. Anonymisierte Kunden und Personen
fehlen: Der Import würde die Kunden abweisen und die Personen neu anlegen.
Für alle
Daten auf einmal gibt es den lesbaren Export unter Einstellungen →
Sicherung ([betrieb.md](betrieb.md), „Vollständiger Datenexport“;
[sicherung.md](sicherung.md), „Der lesbare Export ist keine Sicherung“).

**Große Bestände.** Die Datei wird beim Senden geschrieben, in Teilen zu
2.000 Datensätzen und mit einer festen Zahl von Datenbankabfragen je Teil;
20.000 Exemplare dauern wenige Sekunden. Es gibt keine Aufgabe im
Hintergrund und keine Obergrenze.

## Wenn es nicht klappt

| Meldung | Abhilfe |
|---|---|
| „Importiert werden können nur XLSX- und CSV-Dateien“ / „Die Datei ist keine lesbare XLSX-Datei“ | Die Datei hat ein anderes Format (auch wenn sie `.xlsx` heißt). In Excel öffnen und als `.xlsx` neu speichern. |
| „Die Datei ist zu groß (höchstens 25 MB)“ | Die Datei teilen oder als CSV speichern (kleiner). |
| „Diesem Pflichtfeld ist keine Spalte der Datei zugeordnet“ | Die Überschrift eines Pflichtfelds (Material: ID, Artikelname, Kategorie; Produkte: Art.-Nr., Name; Kunden: Name oder Vor- bzw. Nachname) heißt bei euch anders. Im Browser zuordnen oder `--map` verwenden. |
| „… hat aus Zeile … schon die Kategorie …; diese Zeile weicht davon ab“ (Hinweis) | Gleicher Artikelname, verschiedene Kategorien. Es gilt die erste; vereinheitliche die Liste. |
| „Die ID … kommt schon in Zeile … vor“ / „Die Artikelnummer … kommt schon in Zeile … vor“ | Doppelter Schlüssel in der Datei; eine der beiden Zeilen korrigieren. |
| „Die ID … gibt es nicht“ (Einsatz/Verbindung, ein Hinweis) | Das genannte Exemplar steht weder in der Datei noch in Rentalars. Tippfehler? Das Exemplar wird ohne Verbindung übernommen und hat den Status „Fehler Import“; die Notiz nennt die Zelle. |
| „… nennt mehrere Exemplare … in die Notiz übernommen“ / „… ist nicht die ID eines Exemplars – in die Notiz übernommen“ (Hinweis, Einsatz/Verbindung) | Die Zelle hatte mehrere IDs oder Freitext. Es wurde keine Verbindung gemacht, der Text steht in der Notiz des Exemplars. Wenn eine Verbindung gewollt war: in der Datei nur eine ID eintragen oder sie am Exemplar anlegen. |
| „Das Materialmodell „…“ hat kein eigenes Feld „…“ in seinem Feldsatz.“ (Material) | Die Zeile hat einen Wert in der Spalte eines eigenen Feldes, das zum Feldsatz ihres Modells nicht gehört. Zelle leeren oder dem Modell den passenden Feldsatz geben. |
| „„…“ ist keine Schutzklasse. Schreib I, II oder III.“ (Material) | In der Spalte „Schutzklasse“ steht etwas anderes als I, II, III, 1, 2 oder 3 (mit oder ohne „SK“, „Schutzklasse“ davor). Korrigieren oder die Zelle leeren. |
| „Die Spalte wird nicht eingelesen: Die Werte dieses Feldes brauchen das Recht, Einkaufspreise zu sehen.“ (Hinweis) | Ein vertrauliches eigenes Feld; den Import macht jemand mit dem Recht „Einkaufs- und Kaufpreise sehen“. |
| „Es gibt keine Kategorie mit dem Kürzel …“ (Produkte) | Die Buchstaben der Artikelnummer passen zu keiner Hauptkategorie. Kategorie anlegen oder Artikelnummer korrigieren. |
| „Preise zu importieren braucht das Recht, Preise zu sehen.“ (ebenso Höchstrabatt, Rabatte, Stunden- und Tagessätze) | Die Spalte auf „nicht importieren“ stellen oder den Import von jemandem mit dem Recht machen lassen. |
| „Eine Funktion „…“ gibt es nicht.“ (Personal) | Funktion unter Personal → Funktionen anlegen oder den Namen in der Datei angleichen. |
| „Es gibt mehrere Personen namens …“ (Personal) | Eine Spalte mit der E-Mail-Adresse ergänzen. |
| „Die Datei hat … Zeilen. In einer Anfrage lassen sich höchstens 5000 Zeilen importieren.“ (API) | Mit `background=true` senden oder auf dem Server importieren. |
| „Permission denied“ / Datei nicht gefunden (Kommandozeile) | Das Dienstkonto kann die Datei nicht lesen. Lege sie nach `/var/lib/rentalars/imports/` (siehe oben). |
