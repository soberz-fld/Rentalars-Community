# Benutzerhandbuch

Rentalars, Version 1.0.0

Dieses Handbuch erklärt die Arbeit mit Rentalars: Material und Produkte
pflegen, prüfen – elektrische Geräte nach DGUV V3 mit Messwerten –, im
Audit kontrollieren, beschriften und scannen, Einkäufe samt Rechnung
einpflegen, Eingangsrechnungen erfassen, Anlagen abschreiben und gebraucht
verkaufen, die Belegung von Material im eigenen Kalender abonnieren,
Projekte planen und kalkulieren – große
Produktionen auch als Gesamtprojekt mit Teilprojekten –, Fahrzeuge und
Anhänger des Fuhrparks auf die Fahrten eines Projekts setzen, Servicefälle
schnell bearbeiten, Verfügbarkeit prüfen, packen, ausgeben und
zurücknehmen, Angebot, Auftragsbestätigung, Lieferschein und Rechnung
schreiben und an die Buchhaltung geben, die Profitabilität im Blick
behalten, Personal mit Zuschlägen einplanen, Zeiten und Spesen erfassen,
mit Kunden über das Projekt korrespondieren und
im Team im Chat des Projekts, Adressen auf der Karte und die Fahrten eines
Projekts mit ihrer Route sehen, den Überblick über die kommenden Wochen
behalten, Rentalars mit Automationen von selbst antworten lassen und
andere Programme über Webhooks auf dem Laufenden halten. Packlisten und
Zeiten gibt es unterwegs
auch ohne Netz, mit der Companion-App für Android (Abschnitt 2). Für die
Installation und den Betrieb des Servers gibt es eigene Anleitungen, die du
auch hier im Handbuch öffnen kannst: [Installation](../betrieb/installation.md),
[Betrieb](../betrieb/betrieb.md), [Aktualisierung](../betrieb/aktualisierung.md),
[Sicherung](../betrieb/sicherung.md), [Verschlüsselung](../betrieb/verschluesselung.md)
und [Übernahme der Materialliste](../betrieb/import.md).

Rentalars spricht Deutsch und Englisch – jede Person wählt ihre Sprache
selbst (Abschnitt 2, „Mein Konto“). Dieses Handbuch gibt es in beiden
Sprachen, auch direkt in Rentalars: „Handbuch“ unten in der Seitenleiste
öffnet es in deiner Sprache – Kapitel für Kapitel, mit
Inhaltsverzeichnis und Suche (Abschnitt 2, „Das Handbuch in Rentalars“).

**Inhalt**

1. [Das Wichtigste in fünf Minuten](#1-das-wichtigste-in-fünf-minuten)
2. [Anmelden und zurechtfinden](#2-anmelden-und-zurechtfinden)
3. [Die ersten Schritte nach der Installation](#3-die-ersten-schritte-nach-der-installation)
4. [Material](#4-material)
5. [Produkte](#5-produkte)
6. [Kunden](#6-kunden)
7. [Projekte planen](#7-projekte-planen)
8. [Preise](#8-preise)
9. [Verfügbarkeit, Fehlbestände, Zumietung](#9-verfügbarkeit-fehlbestände-zumietung)
10. [Packen, Ausgabe, Rücknahme](#10-packen-ausgabe-rücknahme)
11. [Dokumente](#11-dokumente)
12. [Personal](#12-personal)
13. [Zeiterfassung](#13-zeiterfassung)
14. [Korrespondenz](#14-korrespondenz)
15. [Planung und Überblick](#15-planung-und-überblick)
16. [Einstellungen](#16-einstellungen)
17. [Was diese Version noch nicht kann](#17-was-diese-version-noch-nicht-kann)
18. [Fragen und Antworten](#18-fragen-und-antworten)

---

## 1. Das Wichtigste in fünf Minuten

Rentalars unterscheidet drei Dinge, die im Alltag oft dasselbe Wort tragen:

| Begriff | Was es ist | Beispiel |
|---|---|---|
| **Materialmodell** | ein Artikeltyp, wie er im Katalog des Herstellers steht | „Cordial CPM 5 FM“ |
| **Exemplar** | ein einzelnes Stück davon, mit eigener ID auf dem Aufkleber | `0001`, `0002`, … |
| **Produkt** | das, was ihr verplant, anbietet und berechnet | `K-005` „XLR-Kabel 5 m“, 1,50 € pro Tag |

Der Kunde mietet kein „Cordial CPM 5 FM“, sondern ein „XLR-Kabel 5 m“ – und
es ist ihm gleich, von welchem Hersteller. Darum hängen an einem **Produkt**
oft mehrere **Modelle**: zwölf Kabel von Cordial und acht von Sommer Cable
sind zusammen zwanzig Stück `K-005`.

**Ein Produkt hat keinen Bestand, den jemand pflegt.** Sein Bestand ist die
Zahl der Exemplare, die ihm zugeordnet sind. Geht ein Kabel kaputt, stellst
du das Exemplar auf „defekt“ – und das Produkt hat eines weniger.

Material, das einem **Kunden gehört** und bei euch lagert – Mischpult und
Multicores einer Band, die ihr zu ihren Gigs mitnehmt –, führst du genauso:
als Produkt mit Modell und Exemplaren, aber mit dem Kunden als
**Eigentümer** und ohne Preis (Abschnitt 5, „Kundenmaterial“).

Ein **Projekt** ist eine Veranstaltung, Vermietung oder Produktion für einen
Kunden, mit einer Nummer wie `2026-0042`. Es enthält **Positionen** („12 × K-005“), die sich in **Teilgruppen**
gliedern lassen („Ton FOH“, „Licht Bühne“) – auch ineinander („Licht ›
Front-Traverse“). Personal, Fahrzeuge und Anhänger
stehen nicht in den Teilgruppen, sondern in eigenen Blöcken darunter
(Abschnitt 7, „Logistik“). Eine große Produktion, etwa ein Stadtfest mit mehreren
Bühnen, planst du als **Gesamtprojekt** mit **Teilprojekten**, jedes mit
eigenem Zeitraum, Material, Personal und Status (Abschnitt 7,
„Teilprojekte“). Ein bestehendes Projekt lässt sich auch nachträglich so
gliedern. Für eine Störung, eine Frage oder eine Reparatur, die keine
Planung braucht, gibt es den **Servicefall** – mit Nummer und
Korrespondenz wie ein Projekt, aber ohne Material und Personal (Abschnitt
7, „Servicefälle“).

Einige Wörter meint Rentalars überall gleich (die Liste für Mitwirkende steht in `docs/dev/glossary.md`):

| Wort | Bedeutung | Nicht gemeint |
|---|---|---|
| **Behälter** | ein Case, Rack oder Road-Case, der anderes Material enthält | „Gerät“ |
| **Gerät** | nur ein Elektrogerät oder ein Fixture (elektrische Prüfung, MVR-Datei) | ein Case oder Rack |
| **Crew** | die Personen, die in einem Projekt eingeplant sind | der Bereich „Personal“ |
| **Personal** | der Bereich der Verwaltung: Personen, Funktionen, Zeiten, Kosten | die Crew eines Projekts |
| **unterwegs** | Material, das ausgegeben und noch nicht zurückgenommen ist | „draußen“, „außer Haus“ (so heißt nur der Mietzeitraum) |
| **Anfrage** | ein Projekt im Status „Anfrage“ oder eine Mail, die ein Projekt werden kann | die **Einsatzanfrage** an eine Person |
| **Auftrag** | was ein Kunde gibt („Auftragsbestätigung“) | eine **Aufgabe**, die im Hintergrund läuft |

Der rote Faden:

```
Material ──▶ Produkte ──▶ Projekt planen ──▶ Verfügbarkeit ──▶ Packen ──▶ Ausgabe ──▶ Rücknahme ──▶ Rechnung
 (was wir      (was wir       (was, wann,        (reicht es?)
  haben)       anbieten)       für wen, wie teuer)
```

Unterwegs entstehen die **Dokumente** für den Kunden – Angebot,
Auftragsbestätigung, Lieferschein, Rechnung – und für die Crew die
Crew-Disposition (Abschnitt 11). Alle Belege an Kunden stehen
unter Buchhaltung → Ausgangsbelege (Abschnitt 11, „Ausgangsbelege“).
Rechnungen gehen auf Wunsch weiter an Lexware Office oder als DATEV-Datei
an die Steuerberatung (Abschnitt 16, „Buchhaltung“).

---

## 2. Anmelden und zurechtfinden

### Anmelden

Öffne die Adresse eures Rentalars im Browser und melde dich mit
Benutzername (oder E-Mail-Adresse) und Passwort an. Es genügt ein aktueller
Browser – am Rechner, am Tablet oder am Telefon.

- **Passwort vergessen?** „Passwort vergessen“ auf der Anmeldeseite schickt
  dir einen Link an deine E-Mail-Adresse – auch dann, wenn du eingeladen
  bist, aber noch nie ein Passwort gesetzt hast.
- **Zu oft vertippt?** Nach fünf Fehlversuchen ist der Name für 15 Minuten
  gesperrt. Danach geht es von selbst weiter.
- **Neu im Team?** Jede Person im Personal hat eine eigene Anmeldung
  (Abschnitt 12). Du bekommst eine E-Mail mit einem Link, über den du dein
  Passwort selbst setzt – oder, etwa ohne E-Mail-Adresse, ein
  **Einmal-Passwort**, persönlich oder am Telefon. Mit ihm meldest du dich
  einmal an; danach fragt Rentalars zuerst nach einem eigenen Passwort
  („Wähle dein Passwort“). Vorher lässt sich nichts anderes tun.
- **Mit dem Konto der Firma anmelden**. Hat eure
  Administration die Anmeldung über das Firmenverzeichnis eingeschaltet
  (LDAP – OpenLDAP oder Active Directory; Abschnitt 16, „Verzeichnis
  (LDAP)“), meldest du dich mit dem Benutzernamen und dem Passwort an, die
  du im Büro auch sonst benutzt. Die Anmeldeseite sieht aus wie immer. Hast
  du in Rentalars noch kein Konto, legt Rentalars es beim ersten Anmelden an
  – aber nur, wenn eine Gruppe von dir im Verzeichnis eine Rolle bekommen
  hat; sonst geht es wie bei einem falschen Passwort nicht weiter, und
  deine Administration sagt dir, in welche Gruppe du gehörst. Hast du in
  Rentalars schon ein Konto, meldest du dich über das Verzeichnis nur an, wenn
  deine Administration es damit verknüpft hat (oder das Verknüpfen über den
  Namen eingeschaltet hat); sonst wird die Anmeldung über das Verzeichnis
  abgewiesen, und du meldest dich weiter mit deinem eigenen Passwort an. Deine Rollen
  folgen bei jeder Anmeldung deinen Gruppen: Wirst du dort in eine andere
  Gruppe gesetzt, ändern sich die Rechte bei der nächsten Anmeldung, und
  wer in keiner Gruppe mehr ist, kommt nicht mehr hinein. **Dein Passwort
  änderst du im Verzeichnis, nicht in Rentalars** – „Mein Konto“ sagt das,
  und „Passwort vergessen?“ schickt dir nichts. Die
  Zwei-Faktor-Anmeldung (unten) gilt zusätzlich, wenn du sie hast: erst
  das Passwort des Verzeichnisses, dann der Code. Antwortet das Verzeichnis
  nicht, sagt die Anmeldeseite „Das Firmenverzeichnis war eben nicht
  erreichbar“; versuch es später noch einmal oder frag die Administration –
  für genau diesen Fall gibt es dort Konten, die sich mit eigenem Passwort
  anmelden („lokales (Notfall-)Konto“).
- **Zwei-Faktor-Anmeldung:** Hast du sie eingerichtet (unten, „Mein
  Konto“), fragt Rentalars nach dem Passwort nach dem sechsstelligen Code
  deiner Authenticator-App. Telefon nicht zur Hand? Einer deiner
  Wiederherstellungscodes geht auch – jeder genau einmal.
- **Abgemeldet, ohne es zu wollen?** Nach einer Zeit ohne Aktivität –
  voreingestellt vier Stunden – meldet Rentalars ab. Dann einfach wieder
  anmelden; du landest auf der Seite, die du öffnen wolltest.

### Die Seitenleiste

Oben in der Seitenleiste stehen das **Logo** von Rentalars – ein Klick
führt zur Startseite; dasselbe Logo ist das Symbol im Browser-Tab und auf
dem Startbildschirm des Telefons, wenn du Rentalars dort ablegst – und das
**Suchfeld** (unten, „Startseite und Suche“). Unter dem Logo und
„Rentalars“ steht klein der **Name eures Unternehmens** aus Einstellungen →
Firmendaten und Grundeinstellungen. So siehst du immer, in welcher
Installation du bist – praktisch, wenn ihr eine zweite zum Ausprobieren
habt. Ändert jemand den Namen, zeigt die nächste Seite den neuen. Darunter
die Bereiche:

| Eintrag | Inhalt |
|---|---|
| **Projekte** | alle Projekte und Teilprojekte, ihre Planung mit den Zumietungen und der Logistik, Preise, Dokumente und Dateien, Zeitplanung mit den Fahrten, Packlisten, Korrespondenz, Chat und der Überblick für die Crew; die offenen Punkte; die Servicefälle; die Projektvorlagen; die Anfragen – Mails, die noch keinem Projekt gehören, und von Hand notierte Anfragen (Abschnitt 14) |
| **Planung** | Kalender, Zeitstrahl, Materialauslastung, Personalplan und Fehlbestände (Abschnitt 15) |
| **Materialverwaltung** | Produkte und Sets (der erste Reiter), Modelle, Exemplare, der Fuhrpark (gleich nach den Exemplaren), „Offene Punkte“ (mit der Zahl der offenen Punkte), Prüfungen, „Audit“, der Import; „Kauf einpflegen“ und im Kopf jedes Reiters das Feld „Exemplar-ID“, mit dem auch Scanner und Kamera arbeiten (Abschnitt 4) |
| **Buchhaltung** | die **Ausgangsbelege** – alle Belege an Kunden mit ihren Summen (Abschnitt 11, „Ausgangsbelege“) – und die **Monatsabrechnung** der Servicefälle (Abschnitt 7, „Monatsabrechnung“); dazu die **Eingangsrechnungen** (Abschnitt 11), der **Anlagenspiegel** und die **Verkäufe aus Bestand** (Abschnitt 4) und das Importieren von **Altprojekten** (Abschnitt 11); jeder Reiter für alle, die ihn sehen dürfen |
| **Kunden** | Kunden mit ihren Adressen und Ansprechpartnern, Veranstaltungsorte – mit Route und Karte (Abschnitt 6) |
| **Personal** | Personen mit ihrer Anmeldung, ihren Funktionen, Stunden- und Tagessätzen und Qualifikationen, ihrer Verfügbarkeit; Freigeben und Auswertung der Zeiten und Spesen (Abschnitt 13) |
| **Auswertungen** | die Profitabilität der Projekte und was das Material eingebracht hat – für alle mit dem Modul Auswertungen, die alle Projekte lesen und Preise sehen dürfen (Abschnitt 8, „Auswertungen“) |
| **Mein Bereich** | was du für dich selbst tust: deine Einsätze (der erste Reiter), deine Verfügbarkeit, deine Zeiten, deine Spesen, deine Personaldaten (Abschnitt 12) |
| **Einstellungen** | in Kästen nach Themen: Firma (mit den Etiketten), Nutzer und Rechte (mit dem Verzeichnis, LDAP), Abläufe (Automationen, Benachrichtigungen, KI), Projekte und Personal (Zuschläge, Preisangebote freier Kräfte, Staffeln, Funktionen), E-Mail, Dokumente und Buchhaltung (mit den Eingangsrechnungen), Stammdaten, Import und Export, Schnittstelle für andere Programme, Betrieb und Sicherheit (Abschnitt 16) |

Unten in der Seitenleiste – am Telefon oben neben dem Menü – steht die
**Glocke** mit der Zahl deiner ungelesenen Benachrichtigungen (Abschnitt 15).
Sie zählt auf jeder Seite mit, auch ohne neu zu laden.

Darunter steht auf jeder Seite der Knopf **„Zeit erfassen“** – am Telefon
die Uhr oben rechts (Abschnitt 13).

Unter deinem Namen stehen untereinander **„Mein Konto“** (unten),
**„Handbuch“** und **„Abmelden“** – jedes in einer eigenen
Zeile mit Symbol, auch am Telefon gut zu treffen. „Handbuch“ öffnet
dieses Handbuch in deiner Sprache (mit dem Inhaltsverzeichnis
als Startseite und Kapitel für Kapitel, siehe „Das Handbuch in
Rentalars“ weiter unten);
Die Anleitungen für den Betrieb stehen ebenfalls dort, unter dem
Inhaltsverzeichnis, und lassen sich aus dem Handbuch direkt öffnen. Gibt es
eine Sprache noch nicht, zeigt Rentalars das deutsche Handbuch mit einem
Hinweis.

Ganz unten stehen die **Versionsnummer** („Rentalars 1.0.0“) und darunter
**„von fld-vt.de“** – der Hinweis, wer Rentalars entwickelt hat; der Link
öffnet dessen Webseite in einem neuen Tab. Denselben Hinweis findest du
unter dem Anmeldefenster. Eine zusätzliche Bestimmung
zur Lizenz (GPL, Abschnitt 7 b; Datei `ADDITIONAL-TERMS.md`) verlangt, dass, wer
Rentalars weitergibt, diesen Hinweis samt Link stehen lässt; ergänzen ist
erlaubt, entfernen nicht. Wer es nur betreibt, ohne es weiterzugeben, ist davon
nicht betroffen. Unter „Über Rentalars“ (Link neben dem Hinweis) stehen
Lizenz, Urheberrecht und die Bibliotheken, die Rentalars verwendet.

Unter einem Eintrag stehen oft **Reiter**, etwa bei Personal „Personen“,
„Verfügbarkeit“, „Funktionen“, „Freigeben“, „Auswertung“ und „Spesen“, bei
Projekte „Projekte“, „Offene Punkte“, „Servicefälle“ und „Anfragen“, bei
Buchhaltung „Ausgangsbelege“ und „Monatsabrechnung“, außerdem „Eingangsrechnungen“,
„Anlagenspiegel“, „Verkäufe aus Bestand“ und „Altprojekte importieren“.
Jeder Reiter
ist eine Startseite des Bereichs; was ihn erklärt, steht direkt unter den
Reitern. Der Kopf mit der Überschrift ist auf allen Seiten gleich hoch, die
Reiter stehen also immer an derselben Stelle.

Du siehst nur, worauf deine Rolle Zugriff gibt. Fehlt ein Eintrag oder ein
Knopf, den dieses Handbuch beschreibt, fehlt dir das Recht dafür – sprich
einen Administrator an. Dasselbe gilt für **Preise**: Sie sind ein eigenes
Recht. Wer es nicht hat, sieht die Planung ohne Preisspalten.

**Bedienung auf dem Telefon.** Am Telefon – und in Fenstern bis 900 Pixel
Breite, wo oben die Leiste mit dem Menüknopf steht – verbirgt sich die
Seitenleiste hinter dem Menüknopf oben rechts. Das Menü gleitet
wie in der App von rechts über die abgedunkelte Seite. Du öffnest es mit
dem Menüknopf oder indem du irgendwo auf der Seite von rechts nach links
wischst; das Menü folgt dabei deinem Finger. Wischst du auf etwas, das sich
selbst seitlich verschieben lässt, etwa einem Zeitstrahl oder einer breiten
Tabelle, verschiebt sich das, und das Menü bleibt zu. Schließen kannst du
es mit dem Kreuz, mit einem Tipp neben das Menü, mit einem Wisch nach
rechts, mit Esc oder mit der Zurück-Taste – du bleibst dabei auf der Seite.
Im Menü steht alles wie in der Seitenleiste am Computer: Name und Firma,
die Bereiche (der aktuelle orange markiert), „Zeit erfassen“,
Benachrichtigungen, dein Konto, Abmelden und die Version. Die **Lupe**
neben dem Menüknopf öffnet es gleich mit dem Cursor im Suchfeld. Der Name
eures Unternehmens steht am Telefon außerdem in der Kopfzeile unter
„Rentalars“ (ist er zu lang, endet er mit „…“). Am Computer bleibt die
Seitenleiste, wie sie ist.

Rentalars erscheint **dunkel**, in euren Hausfarben: Orange für alles, was
man anklicken soll oder was hervorsticht, helles Grau für Text. Was gedruckt
wird – Packliste, Preisübersicht, Stundenzettel, Etiketten, Dokumente –,
bleibt schwarz auf weiß.

Die Seiten folgen den Regeln für barrierearme Webseiten (WCAG 2.1, Stufe
AA) – auch für die Bedienung mit der Tastatur und mit einem Bildschirmleser.
Ein Bildschirmleser liest zu einem Feld auch seinen Hilfetext
vor, etwa „Leer: wie das Modell – …“.
Wer mit der Tastatur arbeitet: Der erste Druck auf die Tabulatortaste zeigt
**„Zum Inhalt springen“** – das überspringt die Seitenleiste.

### Das Handbuch in Rentalars

„Handbuch“ unten in der Seitenleiste öffnet zuerst das
**Inhaltsverzeichnis**: oben das Feld **„Im Handbuch suchen“**, darunter die
achtzehn Kapitel, jedes mit einem kurzen Satz dazu und den Namen seiner
Abschnitte. Ein Klick auf ein Kapitel öffnet **nur dieses Kapitel** – das
geht schnell. Links im
Kapitel stehen die Kapitel und, unter dem aktuellen, seine Abschnitte;
oben und unten führen **„Voriges Kapitel“** und **„Nächstes Kapitel“**
weiter, **„Inhalt“** zurück zum Verzeichnis.

- **Suchen.** Tippe ein oder mehrere Wörter ein und drück „Suchen“. Rentalars
  nennt alle Abschnitte, in denen **alle** Wörter vorkommen, mit Kapitel und
  einem Ausschnitt, in dem die Wörter markiert sind; ein Klick springt
  genau dorthin. Findet es nichts, hilft meist ein Wort weniger oder ein
  kürzeres („Rechnung“ statt „Rechnungen“).
- **Verweise im Text** („Abschnitt 11, „Ausgangsbelege““) sind Links; sie
  führen auch in ein anderes Kapitel.
- **Alte Adressen** gelten weiter: Hast du einen Link der Form
  `/manual/#7-projekte-planen` gespeichert oder von jemandem bekommen, springt
  Rentalars zum richtigen Kapitel. (Das tut ein kleines Skript im Browser;
  ohne Skript bleibst du im Inhaltsverzeichnis.) Ein Kapitel, das es nicht
  gibt (`/manual/99/`), meldet „nicht gefunden“.
- **Sprache.** Du siehst das Handbuch in der Sprache, die du unter „Mein
  Konto“ gewählt hast; gibt es sie nicht, steht das deutsche da, mit einem
  Hinweis.
- Eine Seite des Handbuchs ist nur nach der Anmeldung zu sehen.

### Startseite und Suche

Die Startseite zeigt, was dich **jetzt** angeht – jeweils nur, wofür du die
Rechte hast:

- **Neu für dich:** ungelesene Benachrichtigungen.
- **Du bist angefragt:** Einsätze, zu denen du zu- oder absagen sollst –
  mit den Knöpfen gleich daneben.
- **Deine Wiedervorlagen:** Projekte, deren Wiedervorlage für dich fällig
  ist, mit ihrer Notiz, „überfällig“, wenn der Tag vorbei ist, und
  „Erledigt“, mit Uhrzeit, wenn sie eine hat; „Alle meine Wiedervorlagen“
  führt zu Planung → Wiedervorlagen (Abschnitt 15). Ein
  Servicefall trägt dort das Schild „Servicefall“.
- **Noch zu schreibende Rechnungen:** abgeschlossene
  Projekte, die noch keine Rechnung haben – deine eigenen zuerst; „Alle“
  führt zur Projektliste, gefiltert auf abgeschlossene Projekte ohne
  Rechnung (Abschnitt 11, „Noch zu schreibende Rechnungen“). Nur mit dem
  Recht, Preise zu sehen.
- **Meine Servicefälle:** die Servicefälle, für die du zuständig bist oder
  an denen du beteiligt bist und die noch nicht erledigt sind, mit Status;
  „Alle meine Servicefälle“ führt zu Mein Bereich → „Servicefälle“
  (Abschnitt 7, „Servicefälle“). Ein **zurückgestellter** Fall fehlt hier und
  bei den Wiedervorlagen, bis seine Wiedervorlage fällig ist.
- **Meine Einsätze:** Projekt, Funktion, Zeit und Treffpunkt; ein
  laufender Einsatz mit „Läuft seit …“. „Alle meine Einsätze“ führt zu
  Mein Bereich → „Meine Einsätze“ (Abschnitt 12, „Mein Bereich“).
- **Steht an** und **Gerade unterwegs:** die nächsten Projekte und was
  ausgegeben ist – auch schon teilweise („teilweise ausgegeben“).
- **Heute und morgen zu packen**, **Heute zurückerwartet** – für das Lager;
  Überfälliges ist markiert.
- **Offene Punkte:** Projekte, bei denen noch etwas zu klären ist.
- **Offene Fehlbestände:** alle offenen Fehlmengen, nicht nur die der
  nächsten Wochen. Die ersten sechs stehen da; der Knopf daneben („12
  insgesamt“) führt zur ganzen Liste (Abschnitt 9).
- **E-Mail:** welches Postfach sich nicht abrufen lässt und wie viele
  Anfragen und Mails mit unbekannter Kennung auf ein Projekt warten.

Die Kästen stehen in einem gleichmäßigen Raster; was dich nicht betrifft,
fehlt ganz.

**Die Suche** gibt es auf jeder Seite: oben in der Seitenleiste, am
Telefon hinter der Lupe, und auf der Tastatur mit der Taste **„/“** – sie
setzt den Cursor ins Suchfeld, solange du nicht gerade in einem Feld
tippst. Die Startseite hat zusätzlich ein großes Suchfeld. Die Suche findet
Projekte, Servicefälle, Kunden, Veranstaltungsorte, Produkte, Material,
Personen und Mails – nach Name, Projektnummer (auch in der Schreibweise
`P-2026-0042` für `2026-0042`; Abschnitt 7, „Ein Projekt anlegen“),
Artikelnummer, Material-ID, Seriennummer, dem Wert eines
eigenen Feldes (außer vertraulichen; Abschnitt 4, „Eigene Felder“) oder
Betreff. Wer die ID `0742` vom Aufkleber eintippt, landet beim
Exemplar – noch schneller geht es mit dem QR-Code auf dem Etikett: Die
Kamera des Telefons öffnet die Seite des Exemplars direkt (Abschnitt 4,
„Etiketten“). Mails findet nur, wer sie auch lesen darf – solche mit Schloss nur, wer auch Preise sieht (Abschnitt 14).
Ein Teilprojekt steht mit „Teil von 2026-0042 Stadtfest“ in der Liste,
und der Name eines Gesamtprojekts findet auch seine Teilprojekte.

**Sprechende Adressen.** Ein Projekt ist unter seiner Projektnummer
erreichbar, ein Produkt unter seiner Artikelnummer:
`…/projects/2026-0002/`, `…/products/L-010/`. Solche Links lassen sich
weitergeben und als Lesezeichen speichern. Auch Links mit der
internen Nummer führen zum Ziel, ebenso Links in der Schreibweise
`…/projects/P-2026-0002/`: Sie leiten zur heutigen Adresse
um.

### Listen

Alle Listen funktionieren gleich:

- **Filtern** über die Felder hinter der Schaltfläche **„Filter“** oberhalb
  der Liste (unten, „Filter ein- und ausklappen“).
- **Sortieren** durch Klick auf eine Spaltenüberschrift; ein zweiter Klick
  dreht die Reihenfolge um. Ein kleines Dreieck (▲ oder ▼) zeigt, wonach
  gerade sortiert ist. Filter und Seitenlänge bleiben dabei erhalten.
  Jede Spaltenüberschrift sortiert, auch bei Spalten, die du
  unter „Spalten“ dazunimmst, und bei berechneten Spalten wie den Summen
  eines Projekts, dem Bestand oder dem kategoriespezifischen Wert.
  Berechnete Spalten sortiert Rentalars bei Listen bis 2.000 Zeilen; ist
  die Liste länger, steht sie in ihrer üblichen Reihenfolge, und ein
  Hinweis bittet dich, sie mit den Filtern einzugrenzen. Zahlen in Texten
  sortiert Rentalars wie gelesen: „5 m“ vor „10 m“. Bei Spalten mit
  mehreren Werten (etwa den Funktionen einer Person) zählt der im Alphabet
  erste. Nur Spalten mit Knöpfen oder Häkchen sortieren nicht.
- **Einträge je Seite:** unten rechts an jeder Liste – 25, 50, 100 oder
  200, daneben das Feld **„Eigene Anzahl“** für eine ganze Zahl
  von 5 bis 1.000; „Anzeigen“ übernimmt sie, auch ohne JavaScript. Eine
  andere Zahl weist Rentalars mit einem Hinweis am Feld ab, und die Liste
  bleibt, wie sie war. Voreingestellt sind 50. Rentalars merkt sich
  die Wahl **für dich und für diese Liste** – an deinem Konto,
  also auch nach dem nächsten Anmelden und an einem anderen Gerät; jede
  Liste behält ihre eigene Zahl. Ein Link mit einer anderen Zahl geht vor und
  wird dann für diese Liste gemerkt. Das gilt für jede Tabelle, die
  seitenweise lädt, auch für die Listen der Stammdaten; ausgenommen sind
  Tabellen, die als Ganzes ein Formular oder eine Summe sind – Freigeben,
  Meine Zeiten, die Summen der Auswertungen und die Regeln der
  Automationen.
- Filter, Sortierung und Seitenlänge stehen in der Adresse der Seite. Du
  kannst eine gefilterte Ansicht als Lesezeichen speichern oder als Link
  verschicken.

**Jede Liste ist eine Tabelle.** Alles, was
dieser Abschnitt beschreibt – Filter, Spalten, Sortieren, CSV und
Gruppieren –, gilt für jede Liste in Rentalars: auch für Servicefälle, Anfragen,
Spesen und Meine Spesen, Offene Punkte, Projektvorlagen, Prüfungen,
Fehlbestände, Automationen und ihre Ausführungen, Benachrichtigungen,
Wiedervorlagen, Rollen, Sicherheitsprotokoll, Webhooks und Aufgaben im
Hintergrund. Keine solchen Tabellen sind kleine Tabellen auf der Seite
eines Eintrags (etwa die Positionen eines Projekts oder seine Dateien), das
Änderungsprotokoll (es hat seine Filter), „Meine Zeiten“, „Freigeben“ und
die Auswertung der Zeiten, die Mietstaffeln und Personal → Verfügbarkeit.

**Auswahl und Massenaktionen**. Vor jeder Zeile der Tabellen
steht ein **Kästchen**; das Kästchen in der Kopfzeile wählt alle Zeilen der
Seite. Sobald du etwas gewählt hast, erscheint unten am Rand die **Leiste der
Auswahl** mit der Zahl der gewählten Zeilen. Überall gilt:

- **„Auswahl als CSV herunterladen“** lädt nur die gewählten Zeilen – mit den
  Spalten, die du eingestellt hast – als CSV;
- **„Auswahl aufheben“** nimmt alle Haken weg.

Einige Listen haben zusätzliche Aktionen in der Leiste:

- **Projekte:** **„Wiedervorlage setzen“** (Datum und Uhrzeit, für wen, eine
  Notiz) und **„Wiedervorlage entfernen“** für alle gewählten Projekte.
- **Servicefälle:** **„Status setzen“** (bei „wartend“ mit dem Grund),
  **„Wiedervorlage setzen“** und **„Wiedervorlage entfernen“** sowie
  **„Zuständige setzen“**.
- **Ausgangsbelege** (Buchhaltung): **„Gewählte Belege herunterladen (ZIP)“** –
  je Beleg das PDF und, wenn es eine gibt, die XRechnung, benannt nach der
  Belegnummer; bis zu 300 Belege in einem Download.

Jede Zeile wird einzeln geprüft: Was du bei einem Projekt oder Servicefall nicht
ändern darfst (Recht, geschlossenes Projekt, ein Projekt statt eines
Servicefalls), wird übersprungen, und die Meldung nennt die übersprungenen
Zeilen mit dem Grund; die übrigen werden geändert. Bis zu 1.000 Zeilen lassen
sich gemeinsam wählen. Tabellen, deren Zeilen berechnet sind und keinen
eigenen Eintrag haben, haben keine Kästchen. Die Tabellen, die schon eine eigene
Leiste haben – Exemplare, Prüfungen und offene To-dos, wenn du das Material
ändern darfst –, behalten sie und haben **kein** „Auswahl als CSV herunterladen“
(wer nur lesen darf, hat es). In der Übersicht der Prüfungen wählt das
Kästchen ein Exemplar mit allen seinen Prüfarten. Die Auswahl gilt für die
Seite, die du siehst; blätterst du weiter, beginnt sie neu. Bei mehr als etwa
150 gewählten Zeilen merkt sich Rentalars die Auswahl in deiner Sitzung (die
Adresse der CSV-Datei bleibt kurz) – diese Adresse gilt nur dort. Über die API: `POST
/api/v1/projects/bulk` (Schreibrecht am Modul „Projekte“) und `POST
/api/v1/service-cases/bulk` (dasselbe, oder wer an Servicefällen arbeitet – wie im
Browser entscheidet Rentalars je Fall).

**Filter ein- und ausklappen.** Über den Listen – Projekte, Exemplare,
Modelle, Produkte, Prüfungen, Kunden, Veranstaltungsorte, Personen, Zeiten
freigeben und auswerten, Fehlbestände, Mail-, Änderungs-, Zugriffs- und
Sicherheitsprotokoll, Zustellungen eines Webhooks und allen
anderen Tabellen – stehen die Filter
hinter der Schaltfläche **„Filter“**; das **Suchfeld** davor bleibt immer
sichtbar. Die Filter sind bei jedem Öffnen einer Liste eingeklappt – auf
jedem Bildschirm, auch wenn du sie vorher aufgeklappt hattest; ein Klick
oder Tipp auf „Filter“ klappt sie auf oder zu. Sind Filter gesetzt, zeigt
die Schaltfläche ihre Zahl, etwa **„Filter (2 aktiv)“**, und solange sie
eingeklappt sind, steht daneben, was gefiltert ist, etwa „Status:
Bestätigt“ – so siehst du immer, warum die Liste kürzer ist. Das gilt auch
in der Materialverwaltung und in den Listen der Stammdaten; dort nennt die
Überschrift eines gesetzten Filters die Auswahl, etwa „Nach Aktiv: Ja“.
Hat ein Filter einen Fehler, ist er nie eingeklappt, damit du ihn siehst. Bei
eingeklappten Filtern suchst du, indem du den
Begriff eintippst und die Eingabetaste drückst (am Telefon „Suchen“ oder
„Los“). Ohne JavaScript gibt es die Schaltfläche nicht, und alle Filter
stehen offen da.

**Spalten wählen.** Jede Tabelle – von Projekten, Produkten und Exemplaren
bis zu den Servicefällen und Spesen – hat über der Tabelle den Knopf
**„Spalten“**. Er klappt die Liste aller
Spalten auf, die es gibt: Haken setzen blendet eine Spalte ein, Haken
herausnehmen blendet sie aus, „Übernehmen“ speichert die Wahl. Bei den
Exemplaren lassen sich zum Beispiel Produkt, Lagerort, Hersteller,
Kurzname und der Grund des Status dazunehmen, bei den Projekten Summen wie
Mannstunden, Einnahmen, Kosten und Gewinn (Abschnitt 8, „Summen in der
Projektliste“). Die Spalte, die eine Zeile
kennzeichnet (etwa die ID eines Exemplars), bleibt immer stehen. Rentalars
merkt sich die Wahl für dich und für diese Liste – an deinem Konto, also
auch an einem anderen Rechner. **„Standardspalten“** stellt die
ursprüngliche Auswahl wieder her. Spalten, für die dir ein Recht fehlt
(etwa Preise), werden gar nicht erst angeboten.

**Als CSV herunterladen.** Daneben stehen zwei Links:

- **„CSV“** liefert die Liste so, wie du sie siehst – mit den gezeigten
  Spalten, gefiltert und sortiert, aber mit allen Zeilen, nicht nur der
  aktuellen Seite.
- **„CSV mit allen Spalten“** liefert dieselben Zeilen mit jeder Spalte,
  die du sehen darfst.

Die Datei hat das Semikolon als Trenner und schreibt Zahlen und Daten in
der Sprache der Oberfläche – auf Deutsch mit Dezimalkomma und Datum als
`31.12.2026`, wie deutsche Tabellenprogramme es erwarten, auf Englisch mit
Dezimalpunkt und Datum als `31/12/2026`; auch Spaltennamen, „ja“/„nein“
und der Dateiname folgen ihr. Excel und LibreOffice öffnen sie mit einem
Doppelklick, Umlaute inklusive.
Eine aus der Liste der Produkte, Kunden oder Personen exportierte Datei
lässt sich nach dem Bearbeiten wieder importieren (Abschnitt 16, „Import
und Export“). Spalten mit Knöpfen oder Häkchen stehen nie in der Datei.

**Gruppieren nach.** Neben „Spalten“ steht **„Gruppieren nach“**: Wählst
du eine Spalte – bei den Servicefällen etwa den Status, bei den Anfragen
den Absender oder das Postfach, bei den Projekten den Kunden –, stehen die
Zeilen unter einer Überschrift je Wert, und neben jeder Überschrift steht,
wie viele Einträge die Gruppe in der ganzen gefilterten Liste hat. Werte mit
fester Reihenfolge stehen in dieser („offen, in Arbeit, erledigt“), Kunden
und Ähnliches nach dem Namen; Zeilen ohne Wert stehen unter „(ohne
Angabe)“. Innerhalb einer Gruppe gilt die Sortierung, die du gewählt hast.
Geht eine Gruppe auf der nächsten Seite weiter, steht ihre Überschrift dort
noch einmal. Filter und Sortierung bleiben beim Gruppieren erhalten, und
wie sie steht die Gruppierung in der Adresse der Seite. Die **CSV-Datei**
ist nie gruppiert.

Du kannst unter „Gruppieren nach“ **jede eingeblendete Spalte**
wählen, in der Reihenfolge der Tabelle; nur Spalten mit Knöpfen oder
Häkchen fehlen. Blendest du eine Spalte aus, verschwindet sie auch aus
der Auswahl. Spalten mit Datum und Uhrzeit gruppieren nach dem Tag, ein
Zeitraum nach seinem ersten Tag. Berechnete Spalten (Summen, Bestand,
Anzahl der Projekte …) gruppieren Listen mit höchstens 2.000 Zeilen; ist
die Liste länger, sagt Rentalars das über der Tabelle und zeigt sie ohne
Gruppen – grenze sie dann mit den Filtern ein. „Freigeben“ bleibt nach
Projekten gruppiert, und die Summen der Auswertung sind schon Gruppen;
beide haben kein „Gruppieren nach“. Auch die Listen der Stammdaten lassen
sich nach jeder eingeblendeten Spalte gruppieren, zum Beispiel Lagerorte
nach ihrem Pfad.

### Zurück

Auf jeder Seite unterhalb der Listen – einem Produkt, einem Exemplar, einem
Formular – steht oben links **„← Zurück“**. Es führt zu der Ansicht, aus der
du gekommen bist, und zwar so, wie du sie verlassen hast: zur Liste mit
ihrem Filter und auf derselben Seite, zum Suchergebnis, oder zu dem
Exemplar, von dem aus du das Produkt geöffnet hast.

Anders als der Zurück-Knopf des Browsers führt es nach dem Bearbeiten und
Speichern nicht noch einmal in das Formular. Die Reiter eines Projekts,
einer Person, eines Produkts, eines Modells und eines Exemplars zählen als
eine Seite: „Zurück“ verlässt den Datensatz. Wer eine Seite über ein
Lesezeichen oder einen Link öffnet, kommt mit „Zurück“ zur Liste des
Bereichs. „Zurück“ führt auch dann zur zuletzt geöffneten Seite,
wenn du vorher die Zurück-Taste des Browsers benutzt hast. (Das klappt nur, solange
der Browser die Herkunftsseite mitschickt, was er standardmäßig tut.)

Die Reiter unter einem Eintrag der Seitenleiste – etwa Kalender,
Zeitstrahl, Materialauslastung, Personalplan und Fehlbestände unter
„Planung“ oder
Kunden und Veranstaltungsorte unter „Kunden“ – sind Startseiten und zeigen
kein „Zurück“; die Seiten darunter immer. Das gilt für jede Seite, die du
über die Seitenleiste, die Links an ihrem Fuß oder einen Reiter öffnest –
auch für Servicefälle, Spesen und Meine Spesen, und für
jeden neuen Reiter wie Planung → Wiedervorlagen oder Mein Bereich →
Servicefälle. **Am Telefon** steht „Zurück“
immer oben links in der Kopfzeile, auf den Startseiten führt es dorthin,
wo du vorher in Rentalars warst.

### Rückfragen und Seiten, die sich selbst aktualisieren

**Rückfragen** – „Diese Position löschen?“, „Diese Person anonymisieren?“ –
erscheinen als Dialog von Rentalars, nicht als graues Fenster des
Browsers. „Abbrechen“ lässt alles, wie es ist; der andere Knopf führt die
Aktion aus. Er heißt wie die Aktion („Person löschen“, „Anonymisieren“)
oder schlicht „Ja, löschen“ – rot, wenn etwas gelöscht oder entfernt wird.

**Seiten bleiben aktuell.** Die Seiten eines Projekts – alle Reiter – und
die Anfragen (Projekte → Anfragen) folgen Änderungen von selbst: Geht eine Mail zum Projekt
ein oder ändert jemand anderes etwas daran – eine Position, den Status,
eine Packliste –, lädt sich die Seite nach spätestens etwa 20 Sekunden neu
und bleibt an derselben Stelle. Tippst du gerade etwas oder ist ein Dialog
offen, geht nichts verloren: Dann erscheint unten nur der Hinweis **„Auf
dieser Seite gibt es etwas Neues.“** mit dem Knopf **„Anzeigen“**, und du
lädst neu, wenn es dir passt. Was du selbst speicherst, löst kein Neuladen
aus – was jemand anderes kurz davor oder danach geändert hat, zeigt die
Seite trotzdem, etwa die Zusage zu einer Einsatzanfrage (Abschnitt 12).
Eine offene **Packliste** folgt auch dem Abhaken: Hakt jemand
anderes ab – im Browser oder mit der Companion-App –, lädt sie sich nach
spätestens 20 Sekunden neu (beim Tippen erscheint stattdessen der
Hinweis). Die Zahl an der Glocke ist auf jeder Seite aktuell. Eine neue Nachricht im
**Chat** eines Projekts lädt keine Seite neu: Am Reiter „Chat“ erscheint
die Zahl der ungelesenen Nachrichten, und der Chat selbst zeigt neue
Nachrichten von allein (Abschnitt 7, „Chat im Projekt“) – auch jede
Änderung einer Nachricht, selbst zwei Änderungen in derselben Sekunde.

### Pflichtfelder

Pflichtfelder erkennst du am roten **Sternchen \***; oben im Formular steht
einmal „\* Pflichtfeld“. Manche Felder sind nur unter einer Bedingung
Pflicht – der Preis bei Mietprodukten, der Verkaufspreis bei
Verkaufsprodukten, der Kunde bei einem Projekt, das nicht intern ist, oder
die Daten für IMAP bei einem Postfach der Korrespondenz. Ihr Sternchen
erscheint, sobald die Bedingung erfüllt ist, etwa wenn du die Produktart
wählst.

Das gilt ausnahmslos: in jeder Seite und jedem
Dialog, in den Formularen der Stammdaten und in Formularen mit vielen
Zeilen wie „Kauf einpflegen“. Bei einer Gruppe von
Auswahlknöpfen steht das Sternchen an ihrer Überschrift. Ein
Bildschirmleser erfährt am Feld selbst, dass es erforderlich ist.

### Datum und Uhrzeit wählen

In jedem Feld für ein Datum, eine Uhrzeit oder beides steht rechts ein
**Kalender- bzw. Uhrsymbol**. Es öffnet einen Kalender wie bei „Zeitraum
im Kalender wählen“ (unten), bei einer reinen Uhrzeit gleich das
Ziffernblatt:

- **Ein Datum** übernimmst du mit einem Tipp auf den Tag.
- **Datum und Uhrzeit:** Nach dem Tag wählst du die Uhrzeit auf dem
  **Ziffernblatt** – erst die Stunde (außen 1 bis 12, innen 13 bis 23 und
  00), dann die Minute. Das Ziffernblatt zeigt Schritte von fünf Minuten;
  durch Ziehen oder Eintippen in die Felder „Stunde“ und „Minute“ bekommst
  du jede Minute. **„Übernehmen“** trägt den Wert ins Feld ein.
- **„Heute“** bzw. **„Jetzt“** setzt den aktuellen Tag oder die aktuelle
  Uhrzeit, **„Leeren“** – nur bei Feldern, die nicht Pflicht sind – löscht
  das Feld.
- **Mit der Tastatur:** im Feld Alt+↓, im Kalender die Pfeiltasten (Bild↑
  und Bild↓ blättern die Monate), Enter wählt den Tag; auf dem Ziffernblatt
  ändern die Pfeiltasten den Wert, Enter geht von der Stunde zur Minute und
  übernimmt dann. Esc schließt ohne Änderung.
- **Am Telefon** öffnet schon ein Tipp ins Feld die Auswahl; Tag und
  Uhrzeit kommen dort nacheinander.

Eintippen direkt ins Feld geht weiterhin. Im
Feld steht nur dieses eine Symbol; das eigene Kalender- oder Uhrsymbol, das
manche Browser daneben zeigten, ist ausgeblendet oder verdeckt. Gehört das
Feld zu einem
Zeitraum, ist im Kalender der andere Tag des Zeitraums umrandet und die
Tage dazwischen sind getönt.

### Zeiträume eingeben

Wo ein Formular einen Zeitraum mit Beginn und Ende fragt – das Projekt,
eine Position, eine Personalposition, eine Abwesenheit, eine Sperrzeit –,
helfen die beiden Felder einander:

- **„bis“ kann nicht vor „ab“ liegen.** Ein Ende vor dem Beginn setzt
  Rentalars auf den Beginn.
- **Das Ende wandert mit.** Verschiebst du den Beginn, rückt das Ende mit
  und der Zeitraum behält seine Länge – nach vorn wie nach hinten: Aus „Fr
  12:00 bis Sa 12:00“ wird nach dem Verschieben des Beginns auf Samstag
  12:00 „Sa 12:00 bis So 12:00“. Die Länge zählt nach der Uhr, 12 bis 12
  Uhr bleibt also auch über die Zeitumstellung 12 bis 12 Uhr. Danach
  stellst du das Ende ein, wie du es brauchst.
- **„Zeitraum im Kalender wählen“** neben den Feldern öffnet einen
  Kalender: Der erste Klick wählt den ersten Tag, der zweite den letzten.
  Bei Feldern mit Uhrzeit stehen darunter „Ab (Uhrzeit)“ und „Bis
  (Uhrzeit)“; auch sie haben das Ziffernblatt (oben). „Übernehmen“ trägt
  alles in die Felder ein. Liegt das Ende am selben Tag nicht nach dem
  Beginn – 12 bis 12 Uhr –, ist der Folgetag gemeint.
- **Die anderen Zeiträume des Projekts** sind in diesen Kalendern
  **schraffiert**, damit du dich schnell zurechtfindest: der Mietzeitraum
  grau, die Veranstaltung grün, mit Linien in entgegengesetzter Richtung;
  die Legende unter dem Kalender nennt die Zeiten. Im Projektformular ist
  im Kalender des Mietzeitraums die Veranstaltung schraffiert, sobald du
  sie eingetragen hast, und umgekehrt; beim Anlegen oder Ändern einer
  Phase sind beide schraffiert (Abschnitt 7).

### Mein Konto

Unten in der Seitenleiste, unter deinem Namen: Passwort ändern (nicht bei einem Konto aus dem Firmenverzeichnis – dort steht ein
Hinweis, dass du das Passwort im Verzeichnis änderst) und
API-Token verwalten (Abschnitt 16). Weil jedes Konto zugleich eine Person
im Personal ist, führt von dort **„Meine Personaldaten“** zu deinen
Kontaktdaten, Einsätzen und Abwesenheiten; deine Verfügbarkeit und deine
Kalender stehen im Menü unter **„Mein Bereich“** (Abschnitt 12). Außerdem:

- **Zwei-Faktor-Anmeldung.** Nach dem Passwort fragt Rentalars dann nach
  einem Code aus einer App auf deinem Telefon – FreeOTP, Aegis, ein
  Passwortmanager oder der Authenticator von Google oder Microsoft.
  Einrichten: QR-Code mit der App scannen, den Code eingeben, den sie
  zeigt, fertig. Danach zeigt Rentalars **zehn Wiederherstellungscodes** –
  schreib sie auf oder druck sie aus und bewahre sie getrennt vom Telefon
  auf; jeder ersetzt die App ein Mal. Sie werden nur dieses eine Mal
  angezeigt. Ausschalten geht mit dem Passwort – außer eine deiner Rollen
  schreibt die Anmeldung vor. Dann kommst du nach dem Anmelden direkt zur
  Einrichtung und kannst vorher nichts anderes tun. Telefon und Codes
  verloren? Ein Administrator setzt sie zurück, und du richtest sie neu
  ein. Falsche Codes zählen wie falsche Passwörter: Nach der eingestellten Zahl von Fehlversuchen ist der Name
  für einige Minuten gesperrt, auch in der Schnittstelle.
- **Sitzungen:** wo du angemeldet bist – Browser, Adresse, wann zuletzt
  aktiv. Eine Sitzung, die du nicht kennst, beendest du hier („Beenden“
  oder „Alle anderen Sitzungen beenden“) – und änderst dein Passwort.
- **„Deine Anmeldedaten wurden geändert“**: Ändert sich die
  E-Mail-Adresse deines Kontos, geht diese Mail an die **bisherige**
  Adresse; ändert sich dein Passwort – durch dich, nach einem
  Einmal-Passwort, über den Link „Passwort vergessen?“ oder weil ein
  Administrator ein Einmal-Passwort festlegt –, an deine **aktuelle**. Das
  gilt auch, wenn ein Administrator oder der Import der Personen die
  Adresse geändert hat. Die Mail nennt, was sich wann geändert hat, deinen
  Benutzernamen und – wenn nicht du es warst – „Geändert von: …“. Warst du
  es nicht: Bei einer neuen E-Mail-Adresse sag sofort den Administratoren
  Bescheid; bei einem neuen Passwort setz sofort über „Passwort vergessen?“
  ein eigenes (der Link steht in der Mail) und sag ihnen ebenfalls
  Bescheid. Für ein neues Konto und das erste Passwort gibt es keine Mail.
- **Benachrichtigungen:** worüber du benachrichtigt wirst – in Rentalars,
  per E-Mail und in der Companion-App auf deinem Telefon, je Art – ausnahmslos jede, auch die fertige Aufgabe der KI (Abschnitt 15).
  Wann und wie weit voraus Fehlbestände gemeldet werden, gilt für die ganze
  Firma: Einstellungen → Benachrichtigungen (Abschnitt 16); wer die
  Einstellungen lesen darf, kommt über den Hinweis auf der Seite dorthin.
- **„Sprache“:** ob Rentalars für dich Deutsch oder Englisch spricht –
  Seiten, Mails und Benachrichtigungen an dich und die PDFs, die du für
  dich herunterlädst, etwa den Stundenzettel („Sprache speichern“). „Wie
  die Installation“ übernimmt die Sprache, die euer Server vorgibt. Auf
  Englisch erscheinen Daten als 16/10/2026, Uhrzeiten mit 24 Stunden und
  Zahlen mit Dezimalpunkt (1,234.50); Eingaben schreibst du im selben
  Format. Die Dokumente für Kunden haben die Sprache, die für die Firma
  eingestellt ist (Abschnitt 16, „Firmendaten und Grundeinstellungen“).
  Die Anmeldeseite folgt der Sprache deines Browsers.
- **„Aufgaben im Hintergrund“** (Knopf oben auf der Seite): was du in den
  letzten Tagen an großen Arbeiten angestoßen hast – Importe, viele
  Etiketten, einen Datenexport –, mit Stand und Ergebnis zum Herunterladen
  (Abschnitt 16).
- **API-Token:** auch das Token, mit dem die Rentalars-App auf deinem
  Telefon arbeitet (unten). Widerrufst du es hier, kommt die App nicht
  mehr an Rentalars heran; du meldest dich in ihr neu an. Am Telefon steht
  die Tabelle deiner Token als Karten untereinander und ist
  nicht mehr breiter als ihr Kasten.

### Die Rentalars-App für Android

Für die Arbeit **ohne Netz** – Packen im Lager oder im Lkw, Zeiten am
Einsatzort – gibt es eine Begleit-App für Android-Telefone (ab Android 8):
**Rentalars Companion**, kurz die Companion-App.
Alles andere bleibt im Browser; die App spricht mit Rentalars über die
Schnittstelle (Abschnitt 16, „API-Token“). Sie gehört nicht zum Paket von
Rentalars, sondern wird **eigens ausgeliefert**: Woher ihr sie bekommt und
wie sie auf die Telefone kommt, weiß euer Administrator. Sie braucht
Rentalars, erreichbar über https mit gültigem
Zertifikat.

**Was sie kann:**

- **Packlisten ohne Netz.** Die App lädt die Packlisten aller Projekte im
  Status „Bestätigt – Preise und Einzelheiten offen“, „Bestätigt“ und „Unterwegs“, die du
  sehen darfst. Darin hakst du ab wie im Browser – gepackt, solange eine
  Zeile noch nicht ausgegeben ist, zurück, solange Material unterwegs ist –,
  mit denselben Grenzen und denselben Rechten: Wer Packlisten nur lesen
  darf – etwa mit der Rolle Freie Kraft –, sieht sie in der App nur. Mit
  der Rolle Crew packst du in deinen eigenen Projekten, auch
  ohne Netz, 1:1 nach der Packliste (Abschnitt 10, „Packen mit der Rolle
  Crew“); eine Menge über der Packliste lehnt Rentalars beim Abgleich ab,
  deine übrigen Häkchen kommen an. Wer nur
  seine Einsätze sieht, sieht dort keinen Kunden. **Ausgeben** und
  **„Rücknahme buchen“** bleiben ein Schritt im Browser (Abschnitt 10).
- **Zeiten ohne Netz.** Eine Stoppuhr auf dem Telefon und nachgetragene
  Zeiten, auf die Projekte und Funktionen, auf die du auch im Browser
  buchen kannst (Abschnitt 13) – bietet Rentalars ihr dafür
  auch die offenen Servicefälle und deine Einsätze mit Phase und Zeiten an.
  Es gelten dieselben Regeln: keine Zeiten in
  der Zukunft, keine Überschneidungen. Was Rentalars ablehnt, zeigt die
  App mit dem Grund.
- **Abgleich.** Sobald das Telefon Netz hat, schickt die App von selbst,
  was sich geändert hat – auch wenn sie geschlossen ist –, und auf Wunsch
  sofort. Sie zeigt, wann zuletzt abgeglichen wurde und wie viele
  Änderungen noch warten. Hat an derselben Zeile inzwischen jemand anderes
  abgehakt, gilt die **jüngere** Änderung, getrennt für „gepackt“ und
  „zurück“; bei gleicher Zeit gilt Rentalars. Geht die Uhr deines
  Telefons vor, zählt eine Zeit in der Zukunft als „jetzt“ – deine
  Änderungen untereinander behalten trotzdem ihre Reihenfolge. Jede
  Änderung und jede Zeit kommt genau einmal an, auch wenn die Verbindung
  unterwegs abreißt. Außerdem gilt: Hat jemand
  die Zeile geändert, nachdem dein Telefon sie geladen hat, übernimmt
  Rentalars deine Änderung nicht stillschweigend, sondern meldet, dass sie
  inzwischen auf dem Server geändert wurde und was dort jetzt steht. Du
  siehst den Stand von Rentalars und hakst neu ab, wenn deiner stimmt.
- **Jedes bestätigte Projekt hat seine Packliste** von Anfang an – die App
  findet sie also, auch wenn sie im Browser noch niemand geöffnet hat.
- **Benachrichtigungen auf dem Telefon.** Du wählst unter Mein
  Konto → Benachrichtigungen in der Spalte „In der App“, welche
  Benachrichtigungen die App auf deinem Telefon zeigen soll (Abschnitt 15,
  „Benachrichtigungen“). Rentalars merkt sich die Wahl und gibt sie der App
  mit jeder Benachrichtigung; wie die App sie zeigt, entscheidet die App.
- **Projekte und Servicefälle ohne Netz.** Rentalars merkt sich
  für jedes Feld eines Projekts und eines Servicefalls, wann es zuletzt
  geändert wurde – im Browser, in der App, durch eine Automation oder einen
  Import. Änderst du in der App Name, Ort, Zeiten, Notizen, Status oder
  Wiedervorlage ohne Netz, gilt beim Abgleich für jedes Feld die
  **jüngere** Änderung: Hat jemand dasselbe Feld nach dir geändert, bleibt
  seine Änderung; deine anderen Felder kommen trotzdem an. Bei gleicher
  Zeit gilt Rentalars; geht die Uhr deines Telefons vor, zählt ihre Zeit
  als „jetzt“. Ist ein Statuswechsel inzwischen nicht mehr möglich – das
  Projekt wurde etwa storniert –, nimmt Rentalars ihn nicht an, und die App
  zeigt dir den Stand von Rentalars. Beim Servicefall gehören zum Status
  die Angabe, worauf er wartet, und die Wiedervorlage dazu; sie kommen nur
  zusammen an.
- **Namen statt Nummern:** Projektleitung und Ort siehst du in der App mit
  Namen, auch wenn du nur deine Einsätze siehst.
- **Deine Personaldaten, Abwesenheiten und Einsätze.** In der App siehst
  du deine Personaldaten wie unter „Mein Bereich → Personaldaten“:
  Telefon, E-Mail, was Kollegen sehen dürfen, deine Funktionen (mit Sätzen
  nur, wenn du sie sehen darfst) und deine Qualifikationen mit
  Ablaufdatum. Telefon, E-Mail und die Freigaben kannst du dort auch ohne
  Netz ändern. Sobald die App wieder verbunden ist, gilt die jüngere
  Änderung: Hast du am selben Feld inzwischen im Browser etwas geändert,
  bleibt die spätere Änderung stehen. Abwesenheiten trägst du in der App
  ein oder löschst sie; zu sehen sind sie ab 30 Tagen zurück. „Meine
  Einsätze“ zeigt dir alle deine Einsätze, auch vergangene, ohne abgesagte
  Projekte.

Unter Mein Bereich → „Meine Zeiten“ weist ein kleiner Hinweis auf die App
hin; mit × blendest du ihn für immer aus.

**Anmelden und Sicherheit.** Du meldest dich in der App mit Name und
Passwort an – und mit dem Code deiner Authenticator-App, falls du die
Zwei-Faktor-Anmeldung eingerichtet hast. Die App bekommt dafür ein eigenes
**Token**, beschränkt auf Packlisten, Projekte, Zeiterfassung und E-Mail, gültig
30, 90 oder 180 Tage; dein Passwort speichert sie nicht. Das Token steht
unter Mein Konto → API-Token und lässt sich dort jederzeit widerrufen –
etwa wenn ein Telefon verloren geht. Ein solches Token kann keine weiteren
Tokens erstellen und sieht keine anderen Tokens deines Kontos. Abmelden in
der App widerruft das Token und löscht alle Daten der App vom Telefon. Die
App verlangt eine Displaysperre und fragt sie beim Öffnen ab, speichert
alles verschlüsselt und lässt keine Bildschirmfotos zu.

---

## 3. Die ersten Schritte nach der Installation

In dieser Reihenfolge kommt ihr am schnellsten zu einem arbeitsfähigen
System. Jeder Schritt ist weiter unten ausführlich beschrieben.

1. **Firmendaten und Logo** eintragen (Einstellungen → Firmendaten und
   Grundeinstellungen). Sie erscheinen auf der Packliste und auf den
   Dokumenten. Bevor die erste Rechnung entsteht, gehören auch
   Bankverbindung, Registerangaben, E-Mail-Adresse, USt-IdNr. oder
   Steuernummer und das Zahlungsziel dazu (Abschnitt 11). Liegt das Lager
   nicht an der Anschrift der Firma, trag die **„Anschrift des Lagers“**
   ein – dort beginnen und enden die Fahrten der Projekte (Abschnitt 7,
   „Zeitplanung“). Auf derselben Seite stehen die üblichen Projektzeiten –
   voreingestellt 12 Uhr bis 12 Uhr am Folgetag –, ob Rentalars die
   Rechnungen schreibt („Rentalars als Buchhaltungsprogramm verwenden“, Abschnitt 11),
   und die **„Sprache der Dokumente“** für eure Kunden – die Sprache der
   Ersteinrichtung ist vorgewählt (Abschnitt 16). Was auf den Etiketten
   des Materials steht – Logo, Telefonnummer, Webadresse –, legst du unter
   **Einstellungen → Etiketten** fest (Abschnitt 4, „Etiketten“).
2. **Kategorien, Einheiten und Staffel prüfen** (Einstellungen →
   Kategorien und Kürzel, Einheiten, Staffeln). Mitgeliefert sind die
   Kategorien Ton (T), Licht (L),
   Video/Medien (M), Rigging/Traverse (R), Kabel (K), Verkauf (V), Extern
   zugemietetes Material (E), Veranstaltungstechnik-Dienstleistung (D),
   Fremdmaterial (C), Nebenkosten (N) und Fuhrpark (FZ) für
   eure Fahrzeuge und Anhänger (Abschnitt 4, „Fuhrpark“).
   In E landen Zumietungen – mit dem Produkt E-001 „Zumietung“ –, in D die
   Dienstleistungsprodukte der Funktionen des Personals (Abschnitt 12,
   „Funktionen“), in N Transport, Fahrtkosten und Gebühren (Abschnitt 5,
   „Produktarten“); alle drei haben keinen eigenen Bestand. In C
   kommt Material, das Kunden bei euch lagern (Abschnitt 5,
   „Kundenmaterial“).
   Aufpreise legst du in einer eigenen Kategorie an. Das Kürzel einer
   Kategorie wird zum Anfang der Artikelnummern ihrer
   Produkte – ändere es jetzt, später geht es nicht mehr ohne Weiteres. Dazu
   kommen die üblichen Einheiten und die „Standardstaffel“ (Abschnitt 16,
   „Stammdaten“).
3. **Lagerorte anlegen** (Einstellungen → Lagerorte), Halle für Halle, Regal
   für Regal – dann kann die Packliste den Laufweg im Lager zeigen.
   Mitgeliefert ist „Hauptlager“; es ist im Formular „Neue Exemplare“
   vorgewählt, bis du einen anderen Lagerort zum Standard machst (Abschnitt
   4, „Lagerorte“).
4. **Material übernehmen**: die Excel-Liste importieren
   (Materialverwaltung → Import), oder die ersten Modelle von Hand anlegen.
   Produkte, Kunden und Personal lassen sich ebenso aus einer Tabelle
   übernehmen (Abschnitt 16, „Import und Export“).
5. **Produkte anlegen** und **das Material zuordnen**. Erst dann lässt es
   sich verplanen. Die Liste „Materialverwaltung → Offene Punkte → Material
   ohne Produkt“ zeigt, was noch fehlt.
6. **Prüfarten anlegen** (Einstellungen → Stammdaten → Prüfarten), wenn
   Material regelmäßig geprüft werden muss – für Fahrzeuge etwa HU und
   DGUV/UVV –, und die letzte Prüfung aus den Papieren nachtragen
   (Abschnitt 4, „Prüfungen“). Für die Prüfung elektrischer Geräte nach
   DGUV V3 markierst du die Prüfart als elektrische Prüfung und trägst an
   den Modellen die Schutzklasse ein – dann fragt Rentalars die Messwerte
   ab. Für die kurze Kontrolle zwischendurch – Label da, Klett
   da? – gibt es die **Audits**: Intervall und Schnellauswahl
   unter Einstellungen → Audits prüfen (Abschnitt 4, „Audits und To-Dos“).
   Hat jedes Stück eigene Angaben wie MAC-Adresse oder Firmware, legst du
   dafür **eigene Felder** an (Abschnitt 4, „Eigene Felder“).
7. **Funktionen und ihre Preise prüfen** (Personal → Funktionen).
   Mitgeliefert sind Techniker, Lichttechniker, Tontechniker,
   Medientechniker, Stagehand, Lager, Projektplanung und Sonstiges, jede mit
   ihrem Dienstleistungsprodukt. Die Ersteinrichtung fragt dafür
   nach zwei Werten, beide netto: **„Preis je Stunde für den Kunden“**
   (vorgeschlagen 45,00 €) und **„Interne Kosten je Stunde“** (30,00 €).
   Alle acht Funktionen bekommen diesen Preis an ihrem
   Dienstleistungsprodukt und diese Kosten als Richtwert. Passe sie hier
   für jede Funktion einzeln an – mit Tagessätzen und einem höheren Satz ab
   einer Anzahl Stunden (Abschnitt 12, „Funktionen“). Haben die Funktionen
   keinen Preis, trag an jedem Dienstleistungsprodukt den Preis je Stunde ein, damit
   Personal im Projekt einen Preis hat. Sollen Nacht-, Sonn- und
   Feiertagsstunden mehr kosten, wähl unter **Einstellungen → Zuschläge**
   das Bundesland, prüf die Sätze und schalte die Zuschläge ein – anfangs
   sind sie aus (Abschnitt 16, „Zuschläge“).
8. **Personen anlegen** (Personal → Neue Person), ihnen Funktionen geben –
   eigene Stunden- oder Tagessätze nur, wo sie vom Richtwert der Funktion
   abweichen – und sie einladen. Jede Person bekommt dabei ihre
   Anmeldung mit der Rolle Crew (freie Kräfte: Freie Kraft). Wer mehr darf –
   Projektleitung, Lager, Büro –, bekommt die passende Rolle unter
   Einstellungen → Nutzer (Abschnitt 12, „Personen“, und Abschnitt 16).
9. Ein **internes Projekt** anlegen („Lager und Werkstatt“), auf das Zeiten
   ohne Kundenprojekt gebucht werden.
10. **Die Postfächer** und die **Signatur** einrichten (Einstellungen →
    Postfächer und Signatur), damit Mails mit dem Projektkürzel im Projekt
    landen (Abschnitt 14) – und damit die Crew Einsatzanfragen per
    Antwort-Mail beantworten kann (Abschnitt 12, „Anfragen: Zusage oder
    Absage“). Soll jede neue Anfrage gleich eine Eingangsbestätigung
    bekommen, legst du dafür eine **Automation** an (Abschnitt 16,
    „Automationen“).
11. **Die Zwei-Faktor-Anmeldung** für dich einrichten (Mein Konto) und für
    alle Administratoren vorschreiben (Einstellungen → Firmendaten und
    Grundeinstellungen) – spätestens, bevor Rentalars aus dem Internet
    erreichbar ist. Ein Blick in den **Selbsttest** (Einstellungen) zeigt,
    was sonst noch fehlt, und „Sicherung und Verschlüsselung“, ob die
    nächtliche Sicherung läuft.
12. **Häufige Veranstaltungsorte** anlegen (Kunden → Veranstaltungsorte),
    mit Zufahrt, Strom und Lageplan/Hallenplan.
13. **Dokumentvorlagen und Textbausteine** einmal durchsehen (Einstellungen
    → Dokumentvorlagen, Einstellungen → Textbausteine): Überschriften,
    Einleitung und Schlusstexte, eure Mietbedingungen. Schreibt ihr an
    Kunden auf Englisch, übernimmt „Vorlagentexte auf Englisch oder
    Deutsch“ die englischen Texte (Abschnitt 11, „Vorlagen und
    Textbausteine“).
14. **Die Buchhaltung** einrichten, wenn Rechnungen an Lexware Office oder
    als DATEV-Datei an die Steuerberatung gehen sollen (Einstellungen →
    Buchhaltung, Abschnitt 16) – die Angaben für DATEV am besten zusammen
    mit der Steuerberatung. Schreibt ihr die Rechnungen in einem anderen
    Programm, nimm stattdessen unter Firmendaten und Grundeinstellungen den
    Haken „Rentalars als Buchhaltungsprogramm verwenden“ heraus (Abschnitt 11).
15. **Den ersten Kunden und das erste Projekt** anlegen. Für Formate, die
    immer wiederkehren, speichert ihr ein Projekt danach als **Vorlage**
    (Abschnitt 7). Für Vermietungen, bei denen der Kunde selbst abholt,
    liegt die Vorlage **„Dry Hire (Vermietung ohne Personal)“** schon
    bereit (Abschnitt 7, „Dry Hire – Vermietung ohne Personal“).

Zum gefahrlosen Ausprobieren kannst du bei der Ersteinrichtung Beispieldaten
anlegen lassen – am besten in einer eigenen Testinstallation.

---

## 4. Material

„Material“ ist alles, was im Lager steht und einen Aufkleber hat (oder, bei
Verbrauchsmaterial, gezählt wird).

### Modell und Exemplar

Ein **Modell** hält fest, was für alle Stücke gleich ist: Artikelname,
Kurzname, Kategorie, Hersteller, Beschreibung, Gewicht, Maße und Leistung, die
Schutzklasse (unten, „Schutzklasse“). Ein **Exemplar** hält fest,
was das einzelne Stück ausmacht: ID, Seriennummer, wo es gekauft wurde
(„Gekauft bei“) mit Rechnungsnummer, Rechnungsdatum und Kaufpreis, Zustand,
Lagerort, Notiz.

Unter „Materialverwaltung“ zeigt der Reiter **Modelle** die Modelle mit der
Zahl ihrer Exemplare. Der Reiter **Exemplare** zeigt beides zusammen, eine
Zeile je Exemplar mit 13 Spalten;
weitere Spalten blendest du über „Spalten“ ein (Abschnitt 2, „Listen“).

**Die Seite eines Exemplars** hat oben die Knöpfe „Defekt melden“,
„Etikett“ (unten, „Etiketten“), „Duplizieren“ (unten,
„Duplizieren“) und „Exemplar bearbeiten“ und darunter fünf Reiter:

| Reiter | Inhalt |
|---|---|
| **Exemplar** | die Daten, daneben der schmale Kasten „Fotos“ (unten, „Fotos und Dateien“), bei einem Fahrzeug der Kasten „Fahrzeugdaten“ (unten, „Fuhrpark“), die Kästen „Eigene Felder“ (unten, „Eigene Felder“) und „Audit und To-Dos“ (unten, „Audits und To-Dos“), für alle, die die Auswertungen sehen, der Kasten „Ertrag“ (unten, „Was ein Exemplar einbringt“), darunter „Status ändern“, „Verbaut in / Enthält“ (mit „Einbauen in“ und „Exemplar hinzufügen“), Sperrzeiten, der Kasten „Kalender-Link“ (unten, „Kalender-Link“) |
| **Zeitstrahl** | wann das Exemplar und sein Produkt belegt sind – nur mit dem Sonderrecht „Verfügbarkeit von Material sehen“ (Abschnitt 16, „Rollen und Rechte“) |
| **Prüfungen** | was wann fällig ist, die bisherigen Prüfungen – bei einer elektrischen Prüfung mit Messwerten und „Prüfprotokoll (PDF)“ –, „Prüfung erfassen“ |
| **Dateien und Defekte** | Rechnung, Handbuch, Prüfprotokoll; die Defektmeldungen mit Foto und ihrem Servicefall |
| **Verlauf** | jede Änderung, jeder Ein- und Ausbau, jedes Projekt; die einzelnen geänderten Felder eingeklappt |

Bei den Daten steht neben Kategorie, Hersteller, Produkt und
Seriennummer auch das **Modell** – ein Klick führt zu seiner Seite.

Neben dem Status stehen oben Hinweise, die nicht übersehen werden sollen:
eine überfällige oder bald fällige Prüfung („nie geprüft“, wenn es noch
keine gibt) und – an einem Rack oder Case – ein Problem mit einem Teil
darin („0815 darin ist defekt“, „0815 darin: Prüfung überfällig“). Dort stehen auf jedem Reiter des Exemplars auch **„Audit fällig“**
und **„2 To-Dos“**; ein Klick führt zum Kasten „Audit und To-Dos“ (unten,
„Audits und To-Dos“).

**Die Seite eines Modells** hat die Reiter **Modell** (die Daten, die
Prüfungen, die für das Modell gelten, den Kasten „Ertrag“,
die Liste seiner Exemplare und den Kasten „Kalender-Link“),
**Zeitstrahl** (wie am Exemplar nur mit dem
Sonderrecht „Verfügbarkeit von Material sehen“) und **Dateien**. Oben
stehen „Neue Exemplare“, **„Kauf einpflegen“** mit diesem
Modell in der ersten Zeile (unten, „Kauf einpflegen“), „Modell
bearbeiten“, **„Duplizieren“** und **„Etiketten“** für alle Exemplare
des Modells (unten, „Etiketten“).

**Ein Exemplar über seine ID öffnen**. Im Kopf jedes Reiters
der Materialverwaltung – Produkte, Modelle, Exemplare, Fuhrpark, „Offene Punkte“,
Prüfungen, Audit, Import – steht das Feld **„Exemplar-ID“**. Tipp die
ID ein, wie sie auf dem Etikett steht oder wie du sie aus einer Liste
kopierst – `0427`, `427` oder `#0427` – und drück Enter oder „Öffnen“:
Rentalars öffnet das Exemplar, auch ein ausgemustertes. Gibt es die ID
nicht, sagt Rentalars es und zeigt die Liste der Exemplare, gefiltert nach
dem, was du getippt hast. Das Feld hat, wer das Material lesen darf.

Gehört das Material einem Kunden, steht auf den Seiten von Modell und
Exemplar oben **„Eigentum von …“** mit dem Namen des Kunden (Abschnitt 5,
„Kundenmaterial“). Prüfungen, Defekte, Sperrzeiten und Etiketten gibt es
dafür wie für euer eigenes Material.

### Neues Material anlegen

1. **Materialverwaltung → Modelle → Neues Materialmodell.** Artikelname und
   Kategorie sind Pflicht.
   - **Hersteller:** tippen; Rentalars schlägt bekannte Hersteller vor.
     Gibt es ihn noch nicht, tippst du den Namen einfach aus – der letzte
     Vorschlag sagt dann „neuer Hersteller“ –, und er wird mit dem Modell
     angelegt.
   - **Produkt:** ebenso per Artikelnummer oder Name aus den Vorschlägen
     wählen, zu welchem Produkt das Modell gehört. Das kann auch später
     geschehen; leer lässt sich das Modell noch nicht planen (unten,
     „Material einem Produkt zuordnen“).
   - Der **Kurzname** steht in Listen und auf den Etiketten; leer bleibt es
     beim Artikelnamen.
   - Unter **„Gewicht, Maße und Leistung“** trägst du Gewicht, Leistung und
     die Maße ein (unten).
2. Auf der Seite des Modells: **Neue Exemplare.** Gib die **Anzahl der
   Exemplare** an; sie bekommen fortlaufende IDs und teilen sich die
   Kaufdaten:
   - **Start-ID** – leer vergibt Rentalars die nächsten freien IDs. Trägst
     du eine ein, bekommt das erste Exemplar diese ID und jedes weitere die
     nächste freie danach. Ist die Start-ID schon vergeben, sagt Rentalars
     es.
   - **Seriennummern** – für jedes Exemplar ein Feld, in der Reihenfolge der
     IDs; erhöhst du die Anzahl, kommen Felder dazu. Mit Enter springst du
     ins nächste Feld – praktisch mit einem Handscanner, der nach jeder
     Nummer Enter schickt –, und mehrere eingefügte Zeilen füllen die
     folgenden Felder (und erhöhen, wenn nötig, die Anzahl). Ein leeres Feld
     lässt sein Exemplar ohne Seriennummer. **Gibt es eine Seriennummer
     schon** – bei einem anderen Exemplar, gleich welchen
     Modells, auch bei einem ausgemusterten, verkauften oder verlorenen;
     Groß- und Kleinschreibung und Leerzeichen am Rand zählen nicht –,
     oder tippst du sie zweimal ins Formular, warnt Rentalars nach dem
     ersten Speichern („Die Seriennummer 4711 gibt es schon: Exemplar 0042
     (Modell …).“); mit dem Häkchen **„Trotzdem anlegen“** legst du die
     Exemplare an. Dasselbe gilt für „Kauf einpflegen“, das Ändern und das
     Duplizieren eines Exemplars (dort „Trotzdem speichern“, und nur, wenn
     du die Seriennummer geändert hast), für den Import (die Vorschau nennt
     jede Zeile; ab 100 Zeilen eine Zusammenfassung) und für die API
     (`warnings`). Verboten ist es nie – es gibt Hersteller, die Nummern
     doppelt vergeben. Ohne JavaScript ist es ein Feld mit einer
     Seriennummer je Zeile.
   - **Lagerort** – vorgewählt ist der Standard-Lagerort (unten,
     „Lagerorte“).
   - Unter **„Einkauf“**: **„Gekauft bei“** – tippen und aus den Vorschlägen
     wählen; ein neuer Händler wird mit den Exemplaren angelegt –, die
     „Artikelnummer beim Händler“, **Rechnungsnummer**, **Rechnungsdatum**, Kaufpreis und Kaufnotiz. Händler
     und Artikelnummer beim Händler schlägt Rentalars vom zuletzt angelegten
     Exemplar dieses Modells vor – die zweite Lieferung desselben Kabels
     kommt meist vom selben Händler.

   Unter „Exemplar bearbeiten“ stehen „Gekauft bei“ mit Vorschlägen und die
   Rechnungsnummer ebenso.

**Kaufdatum, wenn du nur das Jahr kennst**. Von einem Gerät,
das seit Jahren im Lager steht, weißt du oft nur das Jahr oder den Monat des
Kaufs. Das Feld **Rechnungsdatum** nimmt deshalb auch ein unvollständiges
Datum: `00.00.2015` (nur das Jahr bekannt) oder `00.05.2015` (Monat und
Jahr) – kurz geht auch `2015` oder `05.2015`; ein ganzes Datum schreibst du
so: `12.05.2015` (auch zweistellig, `12.05.15` – 00 bis 68 bedeuten
2000 bis 2068, 69 bis 99 bedeuten 1969 bis 1999). Rentalars merkt sich, wie genau das Datum ist, und
zeigt es genau so: `2015`, `05.2015` oder `12.05.2015` – in den Listen, auf
den Seiten von Exemplar und Modell und in der CSV-Datei. Dahinter steht der
erste Tag des bekannten Zeitraums; danach sortiert Rentalars, und von dort
an läuft die Abschreibung (unten, „Anlagevermögen“). Das Feld
gibt es bei „Neue Exemplare“, bei „Exemplar bearbeiten“ und in der Spalte
„Rechnungsdatum“ des Imports (Abschnitt 16, „Import und Export“); über die
Schnittstelle heißt das Datum `purchase_date` und darf `2015-05-00` oder
`2015-00-00` sein, die Genauigkeit steht daneben in `purchase_date_precision`
(`day`, `month`, `year`; nur lesbar). Ein Jahr außerhalb von 1900 bis 2999
nimmt Rentalars nicht an – so fällt ein Tippfehler wie `215` auf. „Kauf
einpflegen“ und das Einpflegen einer Eingangsrechnung (Abschnitt 11) bleiben
bei vollständigen Daten: Eine Rechnung hat ein Datum.

**Netto oder brutto**. Steht auf der Rechnung der
Bruttopreis, musst du nicht selbst rechnen: Unter dem Einkaufspreis wählst
du bei **„Der Preis ist“** „netto“ oder „brutto“ und bei brutto unter
**„Der Bruttopreis enthält“** den Steuersatz (vorgewählt der
Standard-Steuersatz). Gespeichert wird immer netto, auf Cent gerundet –
aus 119,00 € brutto mit 19 % werden 100,00 €. Das gibt es bei „Neue
Exemplare“, bei „Exemplar bearbeiten“ und in „Kauf einpflegen“, nur mit
dem Recht „Einkaufs- und Kaufpreise sehen“. Rentalars merkt sich deine
letzte Wahl für das nächste Formular.

**Ein neuer Händler mit seinen Stammdaten**. Tippst du bei
„Gekauft bei“ einen Namen, den es noch nicht gibt, und wählst den
Vorschlag **„neuer Händler“**, öffnet sich ein Fenster „Neuer Händler“:
Name (schon eingetragen), Ansprechpartner, „Unsere Kundennummer dort“,
E-Mail, Telefon, Anschrift und Notiz. **„Händler speichern“** legt ihn an
und trägt ihn ins Feld ein; was du im Formular darunter schon eingetragen
hast, bleibt stehen. Einen Namen, den es schon gibt, nimmt das Fenster nicht an. Das
Fenster hat, wer Material oder die Einstellungen bearbeiten darf. Ohne
JavaScript – oder wenn du den neuen Namen einfach stehen lässt – legt
Rentalars den Händler beim Speichern an, nur mit dem Namen.

### Kauf einpflegen

Eine Lieferung mit zehn Kabeln, vier Scheinwerfern und einem Funkset auf
einer Rechnung? Du erfasst sie in einem Schritt: **„Kauf
einpflegen“** steht oben in Materialverwaltung → Modelle, → Exemplare
und → Produkte, und auf der
Seite eines Modells – dort steht das Modell schon in der ersten Zeile.
Dafür braucht es das Recht, Material zu bearbeiten.

1. **Rechnung** (freiwillig): die Datei der Rechnung wählen. Sie wird beim
   Speichern an jedes neue Exemplar gehängt, als Datei der Art „Rechnung“ –
   gespeichert ist sie nur einmal. **„Rechnung lesen“** füllt das Formular
   aus ihr vor (unten); „Rechnung entfernen“ nimmt sie wieder weg.
2. **Einkauf**, einmal für alle: **„Gekauft bei“** (vorhandener oder neuer
   Händler, oben), **Rechnungsnummer**, **Rechnungsdatum**, mit dem Recht
   für Einkaufspreise **„Die Preise sind“** netto oder brutto mit dem
   Steuersatz (oben, „Netto oder brutto“), die **Start-ID** – leer die
   nächsten freien IDs – und eine **Kaufnotiz** für alle Exemplare.
3. **Positionen**, eine Zeile je Modell: **Modell** – tippen und ein
   vorhandenes wählen, oder den Namen eines neuen eintippen; dann klappt
   „Neues Modell: Kategorie, Hersteller, Produkt“ auf, und die Kategorie ist
   Pflicht –, **Anzahl der Exemplare**, **Kaufpreis je Stück**,
   **Lagerort**, **Artikelnummer beim Händler**, **Seriennummern** (ein Feld
   je Exemplar, wie bei „Neue Exemplare“) und **„Als Set gekauft“** – dann
   gilt der Preis für alle Stück zusammen, und das erste Exemplar bekommt
   ihn. Bei Mengenmaterial wird die Zeile eine Bestandszeile mit der Anzahl
   als Menge. Das Formular beginnt mit **einer** Position;
   **„Weitere Position“** fügt je eine hinzu – ohne JavaScript schickt der
   Knopf das Formular ab, und alles Eingetragene samt der gewählten
   Rechnung bleibt. Der Vorschlag der KI legt je Position der Rechnung eine
   Zeile an (unten). Leere Zeilen übergeht Rentalars; höchstens 100
   Positionen je Kauf. Den Kaufpreis darfst du mit Tausenderpunkt tippen
   („1.072,50“).
4. **„Exemplare anlegen“.**

**Die Summe zum Gegenprüfen**. Unter den Positionen steht
**„Summe der Positionen:“** netto und brutto, mit dem Steuersatz, mit dem
gerechnet wird – Preis mal Anzahl, ein Setpreis einmal; beim Tippen
gleich mitgerechnet und nach jedem Absenden neu. Eine Position ohne Preis
zählt mit 0, und die Zeile darunter sagt, wie viele das sind. Sind die
Preise brutto eingetragen, ist die Bruttosumme die Summe deiner Preise und
die Nettosumme das, was Rentalars speichert (jeder Preis netto, auf Cent
gerundet); bei Nettopreisen rechnet Rentalars die Bruttosumme einmal mit
dem Steuersatz, wie eine Rechnung. Hat „Rechnung lesen“ deren Summe
gefunden, steht daneben **„Rechnung:“** mit ihrer Summe netto und brutto
und die **Differenz** – brutto, wenn beide Bruttosummen bekannt sind,
sonst netto – oder „stimmt überein“. Versand, Rabatte und Pfand der
Rechnung sind keine Positionen und können eine Differenz erklären. Die
Summen sieht nur, wer das Recht „Einkaufs- und Kaufpreise sehen“ hat.

Rentalars legt alle Exemplare in einem Vorgang an, mit fortlaufenden IDs
über alle Positionen – oder, wenn etwas nicht stimmt, gar keines und sagt,
in welcher Zeile. Danach zeigt **„Kauf eingepflegt“** die neuen Exemplare
mit ID, Modell, Seriennummer, Lagerort und Kaufpreis; **„Etiketten
drucken“** führt mit genau diesen Exemplaren zur Seite „Etiketten“ (unten),
„Weiteren Kauf einpflegen“ zum nächsten.

**Rechnung lesen.** Gelesen wird nur ein **PDF mit Text** – eine
gescannte Rechnung nicht, denn eine Texterkennung gibt es nicht; ein Foto
oder Scan wird trotzdem angehängt. Was „Rechnung lesen“ einträgt, hängt
davon ab, ob unter Einstellungen → KI **„Rechnungen lesen“** eingeschaltet
ist (Abschnitt 16, „KI“):

- **Ohne KI** findet Rentalars Rechnungsnummer, Rechnungsdatum, einen
  Händler, den es schon kennt, und die Summe der Rechnung
  (netto und den Betrag, der zu zahlen ist). Die Positionen trägst du
  selbst ein.
- **Mit KI** liest die KI im Hintergrund auch die Positionen – Modell,
  Anzahl, Preis, Artikelnummer und die **Seriennummern**, die
  auf der Rechnung stehen. Für ein neues Modell schlägt sie **Kategorie**
  und **Produkt** aus euren vorhandenen vor. Du kannst währenddessen
  weitertippen. Ist sie fertig, zeigt Rentalars, was sie gefunden hat –
  „Gefunden: 3 Positionen · Rechnung RE-2027-118 · Summe 1.276,28 €
  brutto“ –, und **„KI-Vorschlag eintragen“** trägt es ins Formular ein; gespeichert wird erst mit
  „Exemplare anlegen“. Ihr Ergebnis ist mit „von KI erstellt“
  gekennzeichnet. Kam die KI nicht zum Ziel, heißt der Knopf
  „Gefundenes eintragen“ und trägt ein, was Rentalars ohne KI gefunden hat.

In beiden Fällen ist es ein **Vorschlag**: Er füllt nur leere Felder und
hängt Zeilen an; was du eingetippt hast, bleibt. Händler und Modelle
gleicht Rentalars mit den vorhandenen ab – ein Modell setzt es aber nur
bei einem sicheren Treffer ein, sonst steht unter der Zeile „Vielleicht:“
mit den Modellen, die gemeint sein könnten, zum Anklicken. Ebenso
Kategorie und Produkt eines neuen Modells: Rentalars trägt sie nur ein,
wenn die KI eine vorhandene Kategorie (mit ihrem Pfad, ihrem Kürzel oder
einem Namen, den nur sie trägt) oder ein vorhandenes eigenes Produkt (mit
der Artikelnummer oder einem Namen, den nur es trägt) genau trifft –
Kundenmaterial schlägt Rentalars für einen Kauf nie vor und nimmt es
dort auch nicht an –; sonst
bleibt das Feld leer, und ein Hinweis an der Zeile nennt den Vorschlag
(„Die KI hat die Kategorie „Licht > Fluter“ vorgeschlagen, die es nicht
gibt: Wähle die Kategorie selbst.“). Seriennummern, die nicht im Text der
Rechnung stehen, lässt Rentalars weg und sagt es. **Beträge** liest
Rentalars selbst, so wie sie auf der Rechnung stehen – „1.072,50“,
„1,072.50“, „1.072,50 €“ oder „1.072,-“; ob „1.072“ tausendzweiundsiebzig
oder ein Euro und sieben Cent heißt, entscheiden die übrigen Beträge, der
Text der Rechnung, ihre Währung und ihre Sprache, und jeder Betrag wird
mit den Beträgen im Text abgeglichen. Ist eine Rechnung zu lang für die KI, sagt der
Vorschlag, dass ihr Ende nicht gelesen wurde; die letzten Positionen
trägst du dann von Hand ein. Jede Zeile, die aus der Rechnung kommt, trägt
„aus der Rechnung“ mit dem, was dort stand, und muss mit dem Haken
**„Geprüft“** bestätigt werden, bevor Rentalars etwas anlegt.

Eine hochgeladene Rechnung hält Rentalars zwei Tage für den Kauf bereit,
nur für dich; wird der Kauf nicht gespeichert, löscht Rentalars sie danach
von selbst. Über die Schnittstelle geht dasselbe (Abschnitt 16,
„API-Token“).

**Die Rechnung erst erfassen, prüfen, dann einpflegen**. „Kauf
einpflegen“ legt Exemplare an, sobald du speicherst. Soll die Rechnung vorher
in einem Register stehen – mit Status, Notiz, Fracht und Verpackung als
Nebenkosten, die auf die Ware umgelegt werden, und mit der Einstufung der
Ware als Handelsware, geringwertiges Wirtschaftsgut (GWG) oder Anlagegut –,
dann lädst du sie unter **Buchhaltung → Eingangsrechnungen** hoch (Abschnitt
11, „Eingangsrechnungen“). Das Einpflegen dort benutzt dieselben Prüfungen
wie diese Seite. Was am Exemplar daraus wird, steht weiter unten unter
„Anlagevermögen, Abschreibung und Restbuchwert“.

### Duplizieren

Ähnliches Material legst du mit **„Duplizieren“** an:

- **An einem Modell** öffnet es „Neues Materialmodell“ mit allen Werten
  des Originals – der Name mit „(Kopie)“, Kategorie samt den Feldern der
  Kategorie, Hersteller, Produkt, Beschreibung, Gewicht, Maße und
  Leistung. Gelten für das Original eigene Prüfarten, bietet das Formular
  an: **„Die Kopie bekommt auch die Prüfarten des Originals: …“**.
  Exemplare und Dateien bleiben beim Original. Gespeichert wird erst mit
  dem Knopf des Formulars.
- **An einem Exemplar** öffnet es „Neue Exemplare“ für dasselbe Modell,
  ausgefüllt mit Händler, Artikelnummer beim Händler, Rechnungsnummer,
  Rechnungsdatum, Kaufnotiz und Lagerort, Status „verfügbar“ – ohne ID und
  Seriennummer. Den Kaufpreis übernimmt es nur mit dem Recht „Einkaufs-
  und Kaufpreise sehen“ und nicht von einem Exemplar, das als Teil eines
  Sets gekauft wurde.

Duplizieren darf, wer Material anlegen darf. Produkte duplizierst du
ebenso (Abschnitt 5, „Ein Produkt anlegen“).

**Als Set gekauft.** Kommen mehrere Exemplare zusammen zu einem Preis – ein
Funkset aus Sender und Empfänger, ein Case mit Inhalt –, steht der
Kaufpreis an einem Exemplar, etwa `0851`; die anderen haben keinen eigenen.
Legst du sie zusammen an, setz unter „Einkauf“ den Haken **„Der Preis gilt
für alle diese Exemplare zusammen (ein Set)“**: Das erste Exemplar bekommt
den Preis, bei den anderen ist er im ersten enthalten. Nachträglich trägst
du unter „Exemplar bearbeiten“ bei **„Preis enthalten in (ID)“** die ID des
Exemplars mit dem Preis ein (leer: einzeln gekauft). Die Seite des
Exemplars zeigt dann beim Kaufpreis „im Preis von 0851 enthalten“ und
unter **„Als Set gekauft“** alle IDs des Sets, das mit dem Preis zuerst. In
der Liste der Exemplare steht in der Spalte „Einkaufspreis“ statt eines
Betrags `#0851` – ebenso in der CSV-Datei, die der Import wieder so liest
(unten, „Die Excel-Liste übernehmen“). Kaufpreise sieht und ändert nur,
wer das Recht „Einkaufs- und Kaufpreise sehen“ hat.

**Die ID** ist eine fortlaufende Nummer, mit mindestens vier Stellen
geschrieben: `0001`, `0002`, … und nach `9999` geht es mit `10000` weiter.
Rentalars vergibt die nächste freie. Haben die Stücke schon Aufkleber,
trägst du die ID des ersten als Start-ID ein (oben).

**Die kategoriespezifische Angabe** ist das eine Merkmal, das in einer
Kategorie zählt: bei Kabeln die Länge, bei Traversen das Maß. Was das Feld
bedeutet, legt die Kategorie fest (Abschnitt 16).

**Weitere Felder je Kategorie.** Eine Kategorie kann mehr als ein Merkmal
haben – bei Scheinwerfern etwa Lichtquelle, Abstrahlwinkel und „DMX
ja/nein“. Jedes Feld hat einen Typ: Text, Zahl mit Einheit, Auswahl oder
Ja/Nein. Angelegt werden sie in den Einstellungen an der Kategorie
(Abschnitt 16). Die Leistung ist kein Feld der Kategorie: Sie hat jedes
Modell als eigenes Feld (unten).
Die weiteren Felder erscheinen unter „Modell bearbeiten“, sobald das
Modell einmal gespeichert ist. Rentalars prüft die Eingabe: In ein
Zahlenfeld gehört eine Zahl, „12,5“ oder „12,5 m“.

**Abweichend am Exemplar.** Ein einzelnes Stück kann von seinem Modell
abweichen – das umgebaute Kabel ist 7 m statt 10 m lang. Unter „Exemplar
bearbeiten“ steht dafür bei jedem Feld der Kategorie und bei der eigenen
Beschreibung, was das Modell sagt („Leer: wie das Modell – 10 m“). Leer
gelassen gilt der Wert des Modells; ein eigener Wert ist auf der Seite des
Exemplars mit „eigen“ markiert.

**Gewicht, Maße und Leistung** trägst du am Modell ein, im Kasten
„Gewicht, Maße und Leistung“ seines Formulars: Gewicht in kg, die Leistung
eines Stücks in Watt („Leistung (W)“), Länge, Breite und Höhe in cm. Aus
den Maßen rechnet Rentalars das Volumen; daraus und aus dem Gewicht rechnet
die Packliste Gewicht und Volumen einer Ladung zusammen (Abschnitt 10).

**Schutzklasse**. Bei einem elektrischen Gerät wählst du im
selben Kasten die **Schutzklasse**: „I (Schutzleiter)“, „II
(Schutzisolierung)“ oder „III (Schutzkleinspannung)“ – „–“ für alles, was
nicht elektrisch ist oder dessen Klasse du nicht kennst. Sie gilt für alle
Exemplare des Modells. Weicht ein Stück ab, etwa nach einem Umbau, wählst
du unter „Exemplar bearbeiten“ im Kasten „Abweichend vom Modell“ bei
**„eigene Schutzklasse“** eine andere („Leer: wie das Modell – …“); die
Seite des Exemplars markiert sie mit „eigen“. Dieselbe Klasse wie das
Modell ist keine eigene: Rentalars leert das Feld dann beim Speichern. Die
Schutzklasse steht bei den Daten von Modell und Exemplar, als Spalte
„Schutzklasse“ in den Listen der Modelle und der Exemplare (über
„Spalten“, beim Exemplar seine eigene, sonst die des Modells), in der
Stammdatenübersicht des Audits und im Import und Export (unten, „Die
Excel-Liste übernehmen“); „Duplizieren“ übernimmt sie. Die elektrische
Prüfung nimmt sie als Vorgabe (unten, „Prüfungen“).

### Eigene Felder

Manche Angaben hat jedes Stück für sich: die MAC-Adresse eines
Netzwerkgeräts, den Firmwarestand eines Pults, den Versicherungswert eines
Kamerasets, die Prüfplakette. Dafür gibt es
**eigene Felder**, zusammengefasst zu **Feldsätzen**; ein Materialmodell
bekommt einen Feldsatz, und jedes seiner Exemplare hat dessen Felder mit
eigenem Wert.

**Faustregel:** Die **kategoriespezifischen Felder** (oben) beschreiben
das **Modell** – die Länge eines Kabels ist bei jedem Stück gleich, und
nur ein umgebautes Stück bekommt einen abweichenden Wert. **Eigene
Felder** beschreiben **das einzelne Stück** – MAC-Adresse, Firmware,
Versicherungswert: Jedes Exemplar hat seinen eigenen Wert.

**Felder anlegen:** Einstellungen → **Eigene Felder**, „Neues eigenes
Feld“:

- **Name** – zugleich die Überschrift seiner Spalte in Listen, Exporten
  und Importen; jeder Name nur einmal.
- **Typ** – Text, langer Text, Zahl mit Einheit, Datum, Ja/Nein,
  Auswahlliste, Webadresse oder E-Mail-Adresse; bei einer Zahl die
  **Einheit** („m“, „W“, „kg“), bei der Auswahlliste die
  **Auswahlwerte**.
- **Prüfmuster** – freiwillig: ein regulärer Ausdruck, zu dem jeder Wert
  passen muss, etwa `^[0-9A-F]{2}(:[0-9A-F]{2}){5}$` für eine MAC-Adresse
  (bei Text, langem Text, Zahl, Web- und E-Mail-Adresse). Damit das Prüfen
  eines Werts nicht Minuten dauert, lehnt Rentalars beim Speichern ab:
  verschachtelte Wiederholungen, deren Anzahl sich ändern kann, etwa
  `(a+)+` oder `(.*,){5}`; Alternativen in einer offenen Wiederholung,
  etwa `(ab|cd)+` – mit Obergrenze `(ab|cd){1,5}` geht es –;
  Rückverweise wie `\1`; und Muster mit mehr als 200 Zeichen. Eine feste
  Anzahl innen ist erlaubt, wie `(:[0-9A-F]{2}){5}` im Beispiel, ebenso
  eine kleine begrenzte wie `([0-9]{1,3}\.){3}`. Die Meldung sagt jeweils,
  wie es anders geht.
- **Hilfetext** – steht im Formular unter dem Feld.
- **„in Listen als Spalte wählbar“** – die Liste der Exemplare bietet das
  Feld als Spalte an (unten).
- **„eindeutig“** – keine zwei Exemplare dürfen denselben Wert haben,
  etwa bei einer MAC-Adresse.
- **„nur mit dem Recht, Einkaufspreise zu sehen“** – die Werte sieht,
  durchsucht, exportiert und ändert nur, wer das Recht „Einkaufs- und
  Kaufpreise sehen“ hat, auch im Verlauf und über die Schnittstelle; auf
  der Seite des Exemplars trägt das Feld das Schild „vertraulich“. Für
  Versicherungswert, Leasingvertrag oder PIN. Hakst du es bei einem Feld
  an, das schon Werte hat, verschwinden für alle ohne dieses Recht auch
  die früheren Werte aus dem Verlauf der Exemplare und aus dem
  Änderungsprotokoll.

Haben schon Exemplare einen Wert, übernimmt Rentalars einen neuen Typ,
andere Auswahlwerte, ein Prüfmuster oder „eindeutig“ nur, wenn jeder
gespeicherte Wert dazu passt; sonst nennt es die Werte, die nicht passen.
Ein Prüfmuster prüft Werte bis 4000 Zeichen – so lang darf ein langer
Text höchstens sein –; einen längeren Wert lehnt es ab. Dauert das Prüfen
eines Werts trotzdem zu lange (mehr als eine halbe Sekunde), lehnt
Rentalars den Wert ab mit „Prüfmuster zu aufwendig: Das Prüfen des Werts
im Feld … hat zu lange gedauert. Bitte das Prüfmuster unter Einstellungen
→ Eigene Felder vereinfachen.“ – im Formular, beim Import und über die
Schnittstelle. Ein Prüfmuster, das vor dieser Prüfung gespeichert wurde,
gilt weiter, bis jemand das Feld bearbeitet; dann muss es den Regeln oben
genügen.
Ein Feld mit Werten löschst du unter „Eigenes Feld löschen“ erst, wenn du
„Die Werte von … Exemplaren mitlöschen“ anhakst; der Verlauf jedes
Exemplars behält sie.

**Feldsätze:** Einstellungen → **Feldsätze** (oder der Reiter daneben),
„Neuer Feldsatz“: Name, Beschreibung und darunter alle Felder – hake an,
was zum Feldsatz gehört, bestimme mit der **Position** die Reihenfolge in
den Formularen und auf der Seite des Exemplars und hake je Feld
**„Pflichtfeld“** an, wo ein Wert sein muss. Ein Feld kann in mehreren
Feldsätzen stehen. Einen Feldsatz, den ein Modell hat, kannst du nicht
löschen; ohne Modell verschwindet nur er, Felder und Werte bleiben.
Felder und Feldsätze ansehen darf, wer die Einstellungen lesen darf;
anlegen und ändern, wer sie ändern darf; löschen, wer dort löschen darf –
wie bei den Kategorien.

**Dem Modell einen Feldsatz geben:** im Formular des Materialmodells,
Kasten **„Eigene Felder der Exemplare“**, unter „Feldsatz“ – oder „ohne“.
Duplizieren übernimmt ihn. Auf der Seite des Modells steht er bei den
Daten unter „Eigene Felder“ mit seinen Feldern; Pflichtfelder tragen das
Sternchen.

**Werte eintragen:** „Neue Exemplare“ und „Exemplar bearbeiten“ haben den
Kasten **„Eigene Felder“** mit den Feldern des Feldsatzes. Ein Pflichtfeld
braucht einen Wert, wenn du **ein** Exemplar anlegst oder bearbeitest.
Legst du **mehrere auf einmal** an, gelten die Werte für jedes neue
Exemplar, und Pflichtfelder dürfen leer bleiben – eine MAC-Adresse ist
für jedes Stück eine andere –; ein eindeutiges Feld erscheint dann gar
nicht. „Kauf einpflegen“ fragt keine eigenen Felder ab; danach nennt
Rentalars die neuen Exemplare, denen eine Pflichtangabe fehlt, jedes mit
einem Link zu seinem Formular. Duplizieren übernimmt alle Werte außer
denen eindeutiger Felder.

Die Seite des Exemplars zeigt im Kasten **„Eigene Felder“** die Werte in
der Reihenfolge des Feldsatzes, darüber „Eine Pflichtangabe fehlt: …“,
wenn noch etwas fehlt. Eine Webadresse ist dort und in der Liste ein Link,
wenn sie mit `http://` oder `https://` beginnt, eine E-Mail-Adresse, wenn
sie gültig ist; jeder andere Wert steht als Text da. Jede Änderung steht im Verlauf. Bekommt das Modell
einen anderen Feldsatz, bleiben die Werte erhalten: Werte von Feldern, die
nicht mehr dazugehören, stehen eingeklappt unter „Werte von Feldern, die
nicht mehr zum Feldsatz gehören“ und erscheinen wieder, sobald das Feld
wieder dazugehört.

**In Listen, Suche, Import und Export.** Felder mit „in Listen als Spalte
wählbar“ blendest du unter Materialverwaltung → Exemplare über „Spalten“
ein; sie sortieren wie Zahlen, Daten oder Text, stehen in der CSV-Datei,
und unter „Filter“ hat jedes ein eigenes Suchfeld. Das Suchfeld der
Exemplare und die Suche in der Seitenleiste finden ein Exemplar auch an
den Werten seiner eigenen Felder – an denen vertraulicher Felder nie. Der
Materialimport liest Spalten, deren Überschrift der Name eines Feldes ist,
und der Export im Importformat schreibt sie (Abschnitt 16, „Import und
Export“).

### Fotos und Dateien

**Fotos**. Die Seite eines Modells und die eines Exemplars haben einen schmalen Kasten **„Fotos“** rechts neben den Daten, auf einem schmalen Bildschirm darunter. Mit dem Feld und
**„Hochladen“** legst du ein oder mehrere Fotos auf einmal ab (bis 20, am Telefon öffnet sich auf Wunsch die Kamera); die
Fotos stehen als Vorschaubilder nebeneinander, ein Klick öffnet das Foto in voller Größe, **„entfernen“** löscht es nach einer
Rückfrage. Das zuerst hochgeladene Foto steht im Kopf der Seite. Das Exemplar zeigt sein eigenes erstes Foto, sonst das seines Modells, und führt die
Fotos seines Modells unter den eigenen auf. Wer das Material nur lesen darf, sieht die Fotos und ändert sie nicht.

Rentalars bewahrt ein Foto nicht auf, wie es kam, sondern **erzeugt es neu**: aufrecht gedreht, als JPEG, höchstens 2048 Pixel an der
langen Seite – das spart Platz –, dazu eine kleine Vorschau. Von den Angaben der Kamera bleibt **nur der Ort der Aufnahme** (GPS: Breite,
Länge, Höhe); Gerät, Uhrzeit, Richtung und Kommentar werden entfernt. Wer ein Foto herunterlädt oder weitergibt, gibt den Ort mit. Dasselbe
gilt für Fotos im Chat, an Defektmeldungen und an Spesenbelegen. **Dokumente** – PDF-Dateien, die Kopie einer Rechnung, Projektdateien, Mailanhänge –
bleiben, wie sie kamen; ein Bild, das du als Handbuch, Protokoll oder Sonstiges ablegst, wird wie ein Foto neu erzeugt.

**Dateien.** Am Modell (Reiter **Dateien**) und am Exemplar (Reiter **Dateien und Defekte**) lassen sich Dokumente ablegen:
„Datei hinzufügen“, Art wählen – Handbuch, Rechnung, Prüfprotokoll oder Sonstiges –, auf Wunsch eine Bezeichnung, „Hochladen“.
Handbücher und Datenblätter gehören zum Modell, die Rechnung eines einzelnen Kaufs zum Exemplar. Das Exemplar zeigt die Dateien seines
Modells mit an.

### Mengenmaterial

Gaffa-Tape, Kabelbinder, Leuchtmittel: Dinge, die niemand einzeln beklebt.
Stelle am Modell „Bestand wird geführt als“ auf **Menge**. Statt vieler
Exemplare gibt es dann eine Zeile mit einer Stückzahl („Neue
Bestandszeile“). Steckt ein Teil davon fest in einem Rack, Case oder
Fahrzeug – zehn Meter Kabel und vier Stecker im Rack –, trägst du es dort
ein, und es zählt nicht mehr zum freien Bestand (unten, „Verbaut in“,
Absatz „Mengenmaterial einbauen“).

### Lagerorte

Wo etwas liegt, steht am Exemplar im Feld **„Lagerort“**. Die Lagerorte
stehen als Baum unter Einstellungen → Lagerorte: Halle, darin Regale,
darin Fächer – auch ein Case, das immer an derselben Stelle steht, kann
ein Lagerort sein. Jeder Ort nennt, wovon er **„Teil von“** ist;
Rentalars schreibt ihn dann mit dem ganzen Weg: „Halle 1 > Regal A > Fach
3“.

Die Liste der Exemplare lässt sich nach Lagerort filtern. Die Packliste
kann nach Lagerort sortieren und ergibt so den Laufweg durchs Lager
(Abschnitt 10).

**Der Standard-Lagerort.** Ein Lagerort kann der Standard für neue
Exemplare sein: Das Formular „Neue Exemplare“ schlägt ihn vor. Eine neue
Installation bringt „Hauptlager“ als Standard mit. Welcher es ist, legst du
unter Einstellungen → Lagerorte mit dem Haken **„Standard für neue
Exemplare“** fest; es gibt höchstens einen, und ein deaktivierter Lagerort
kann es nicht sein. Die Seite Einstellungen nennt ihn neben „Lagerorte“
(„Neue Exemplare kommen nach: Hauptlager“). Der Import und die API setzen
ihn nicht von selbst.

**Verbautes Material steht dort, wo sein Gerät steht.** Steckt ein
Funkempfänger in einem Rack, zählt der Lagerort des Racks; die Seite des
Empfängers schreibt dazu „(wo sein Gerät ist)“. Zieht das Rack um, muss
niemand den Empfänger umtragen.

**Der Lagerplatz.** Innerhalb eines Lagerorts liegt ein Exemplar an einem
Platz – „Regal 3, zweites Fach, dritte Stelle“. Dafür hat jedes Exemplar
 ein kurzes Feld **„Lagerplatz“** (bis 12 Zeichen) im Formular
des Exemplars und beim Anlegen neuer. Üblich ist die Kurzform
**„03-A-2“**: eine zweistellige Zahl, ein Buchstabe, eine Ziffer. Du musst
sie nicht genau tippen: „3a2“, „3 A 2“ und „03.a.2“ macht Rentalars selbst
zu „03-A-2“; anderer kurzer Text bleibt, wie du ihn schreibst. Es ist ein
Textfeld und keine Liste von Plätzen, die jemand pflegen müsste – dafür
braucht es nichts weiter, und die Suche und der Import kommen damit aus.

Der Platz steht auf der Seite des Exemplars hinter dem Lagerort, in der
Liste der Exemplare in der Spalte „Lagerort“ („Halle 1 03-A-2“; sortiert
wird nach Lagerort und Platz), in den Listen der Prüfungen und Audits und
im Audit-Modus. Die Suche findet ihn („3a2“ genügt), die Massenbearbeitung
setzt ihn für alle gewählten Exemplare (unten), der Import kennt die
Spalte **„Lagerplatz“** und der Export schreibt sie mit, das Duplizieren
übernimmt ihn, die Schnittstelle nennt ihn `storage_spot`. Auf der Packliste
steht er neben dem gewählten, noch nicht ausgegebenen Exemplar – so
findest du es beim Packen. Ein verbautes Exemplar zeigt den Platz dessen,
worin es steckt. Legst du ein Exemplar in der Massenbearbeitung in einen
anderen Lagerort, entfällt sein alter Platz, wenn du keinen neuen nennst.

### Der Zustand eines Exemplars

Auf der Seite des Exemplars, unter „Status ändern“ – gleich unter den
Daten, noch vor „Verbaut in / Enthält“:

| Status | Bedeutung | Zählt zum Bestand? |
|---|---|---|
| verfügbar | im Lager, einsatzbereit | ja |
| im Einsatz | gerade mit einem Projekt unterwegs (setzt Rentalars bei der Ausgabe selbst) | ja |
| defekt | kaputt, noch nicht in Arbeit | **nein** |
| in Reparatur | beim Service | **nein** |
| gesperrt | soll nicht raus, z. B. ungeprüft | **nein** |
| ausgemustert, verkauft, verloren | nicht mehr da | **nein**; verschwindet aus der Alltagsliste |

Wer ein Exemplar auf „defekt“ stellt, nimmt es sofort aus der Planung: Die
Verfügbarkeit aller Projekte rechnet mit einem Stück weniger – und zeigt
gegebenenfalls eine Fehlmenge.

**Der Grund.** Bei jeder Statusänderung fragt Rentalars nach dem Grund. Für
„defekt“ ist er Pflicht – „Lüfter klemmt“, „Display gerissen“ –, sonst
freiwillig. Der Grund steht am Exemplar, solange der Status gilt, und
bleibt im Verlauf.

**Aus „defekt“ führen nur drei Wege:** in Reparatur, ausgemustert oder
verkauft. Ein defektes Stück lässt sich nicht einfach wieder auf
„verfügbar“ stellen – erst aus der Reparatur heraus. So verschwindet kein
Defekt unbemerkt aus der Liste.

Ausgemusterte, verkaufte und verlorene Exemplare bleiben mit ihrem Verlauf
erhalten. Du findest sie über den Statusfilter der Materialliste.

Für einen Defekt gibt es einen kürzeren Weg mit Foto („Defekt melden“), für
eine Reparatur mit festem Ende die Sperrzeit – beides gleich im Anschluss.

### Defekt melden

Gemacht für das Telefon im Lager: **„Defekt melden“** oben auf der Seite
des Exemplars (am schnellsten über den QR-Code auf dem Etikett, siehe
unten).

1. Unter **„Was ist defekt?“** beschreiben, was los ist – „Stecker lose“.
2. Auf Wunsch ein **Foto** dazu. Am Telefon öffnet sich die Kamera.
3. „Defekt melden“.

Das Exemplar steht damit auf „defekt“, mit der Beschreibung als Grund, und
das Lager bekommt eine Benachrichtigung „Defekt gemeldet“ (alle, die
Material ändern dürfen). Ist das Exemplar schon defekt, kommt die Meldung
dazu – ein zweiter Fehler ist auch gut zu wissen.

**Aus der Meldung wird ein Servicefall.** Die Automation
**„Defektmeldung → Servicefall“** legt zu jeder Meldung gleich einen Servicefall
an – mit Titel wie „Defekt 0042 SM58“, mit dem, was defekt ist, und dem
Foto in seinen Dateien. Bei eurem eigenen Material ist der Fall intern,
bei Kundenmaterial gehört er dem Kunden (Abschnitt 7, „Servicefälle“). Ob
und wie das geschieht, stellt ein Administrator unter Einstellungen →
Automationen ein; statt des Falls kann die Meldung auch erst unter
Projekte → Anfragen warten (Abschnitt 16, „Automationen“).

Alle Meldungen stehen im Reiter **„Dateien und Defekte“** unter
„Defektmeldungen“: wann, von wem, in welchem Zusammenhang (etwa „Rücknahme
2026-0042“), mit Foto – und mit ihrem Servicefall und dessen Status. Hat
eine Meldung noch keinen, macht **„Als Servicefall anlegen“** einen daraus
(mit dem Recht, Projekte anzulegen). Aus einer Meldung wird höchstens ein
Servicefall. Defekte, die bei der Rücknahme auffallen, meldest du
direkt auf der Packliste (Abschnitt 10).

### Sperrzeiten

Ein Gerät ist vom 3. bis 14. April beim Hersteller in Reparatur? Statt den
Status von Hand hin und her zu stellen, trägst du auf der Seite des
Exemplars unter **„Sperrzeiten“** ein: **Von**, **Bis** und den **Grund**
(„beim Hersteller in Reparatur“), dann „Sperren“.

In diesem Zeitraum zählt das Exemplar nicht zum Bestand: Sein Produkt hat
ein Stück weniger, und ein Projekt, das es braucht, zeigt dort
gegebenenfalls eine Fehlmenge. Davor und danach ist es ganz normal
planbar. „aufheben“ beendet eine Sperre vorzeitig. Sperrzeiten erscheinen
im Zeitstrahl.

Der Unterschied zum Status „gesperrt“: Der Status gilt, bis ihn jemand
ändert. Eine Sperrzeit gilt nur für ihren Zeitraum und endet von selbst.

### Prüfungen

Elektrische Prüfung, Sichtprüfung der Anschlagmittel, UVV der Kettenzüge –
was regelmäßig geprüft werden muss, verwaltet Rentalars mit.

**Prüfarten** stehen unter Einstellungen → Stammdaten → Prüfarten
(Abschnitt 16): Name, **Abstand (Monate)**, eine Beschreibung und, für
welche **Kategorien** und **Materialmodelle** sie gilt, der
Haken **„elektrische Prüfung (DGUV V3 / DIN VDE 0701-0702)“** (unten). Eine
Prüfart an einer Kategorie gilt für alle Exemplare aller Modelle darin,
Unterkategorien eingeschlossen.

**Wann ist eine Prüfung fällig?** Rentalars rechnet es aus:

- **Nächste Prüfung = letzte bestandene Prüfung + Abstand.**
- Eine **nicht bestandene** Prüfung setzt das Exemplar auf „defekt“; es ist
  sofort wieder fällig und wird nach der Reparatur neu geprüft.
- Ein Exemplar, das **noch nie geprüft** wurde, gilt als **überfällig**.
  „Wissen wir nicht“ ist nicht „in Ordnung“. Eine neue Prüfart macht also
  zunächst alle ihre Exemplare überfällig – bis sie geprüft sind oder die
  letzte Prüfung aus den Papieren nachgetragen ist.
- **Bald fällig** ist, was in den nächsten 30 Tagen fällig wird.

**Eine Prüfung erfassen:** Reiter **„Prüfungen“** des Exemplars, „Prüfung
erfassen“: Prüfung, Datum, „Geprüft von“, Ergebnis („bestanden“ oder
„fehlgeschlagen“), Notiz und auf Wunsch das **Protokoll** als Datei,
„Erfassen“. **Datum** (heute) und **„Geprüft von“** (du
selbst) stehen schon drin – änderbar, wenn ein anderer geprüft hat oder du später
einträgst. Oben im Reiter steht je Prüfart, wann zuletzt geprüft wurde
und wann die nächste fällig ist – rot überfällig, gelb bald fällig, grün in
Ordnung. Darunter die bisherigen Prüfungen mit ihren Protokollen.

**Elektrische Prüfung nach DGUV V3**. Ist eine Prüfart als
elektrische Prüfung markiert und wählst du sie beim Erfassen, erscheint
unter Datum und „Geprüft von“ der Kasten **„Elektrische Prüfung (DGUV V3 /
DIN VDE 0701-0702)“** – mit den Prüfschritten in der Reihenfolge der Norm:

- **Schutzklasse** (Pflicht) – vorbelegt mit der des Exemplars (oben,
  „Schutzklasse“); von ihr hängen die Grenzwerte ab. **Leitungslänge (m)**
  – vorbelegt aus der kategoriespezifischen Angabe „Länge“ (in m, cm oder
  mm, die eigene des Exemplars zuerst); leer gilt sie als bis 5 m. Das
  **Prüfgerät** („Benning ST 760, SN 12345“) ist mit dem vorbelegt, das du
  zuletzt eingetragen hast.
- **Sichtprüfung** (Pflicht; ein Kontrollkästchen
  **„Sichtprüfung bestanden“**): angehakt heißt bestanden, nicht angehakt
  nicht bestanden – dann schlägt Rentalars „fehlgeschlagen“ vor.
- **Schutzleiterwiderstand R<sub>PE</sub> (Ω)**, **Isolationswiderstand
  R<sub>ISO</sub> (MΩ)**, **Schutzleiterstrom I<sub>PE</sub> (mA)** und
  **Berührungsstrom I<sub>B</sub> (mA)**. Neben jedem Feld steht sein
  **Grenzwert**, bei R<sub>PE</sub> mit der Länge, für die er gilt, und
  sobald du einen Wert tippst, „im Grenzwert“ (grün) oder „außerhalb des
  Grenzwerts“ (rot). Was bei der Schutzklasse nicht gemessen wird, steht
  als „Nur bei Schutzklasse I“ da und bleibt leer; einen Wert, den du
  nicht gemessen hast, lässt du ebenfalls leer.
- **Funktionsprüfung**: „bestanden“, „nicht bestanden“ oder **„entfällt“**
  – etwa bei einem Kabel.

Darunter steht das **vorgeschlagene Ergebnis** mit seinen Gründen:
„bestanden“, wenn die Sichtprüfung bestanden ist, gemessen ist, was die
Schutzklasse verlangt (unten), die Funktionsprüfung nicht fehlschlug und
jeder eingetragene Wert im Grenzwert liegt; sonst „fehlgeschlagen“, etwa
mit „RPE 0,52 Ω liegt außerhalb des Grenzwerts ≤ 0,3 Ω.“ Fehlt ein nötiger
Messwert, ist auch das ein Grund; in der Liste der Prüfungen und im
Prüfprotokoll steht sein „nicht gemessen“ dann rot. Die Werte prüft
Rentalars beim Tippen, ohne JavaScript beim Absenden. Das Ergebnis wählst du selbst: **Wählst du gegen den Vorschlag
„bestanden“, verlangt Rentalars den Grund in der Notiz.** Ein
fehlgeschlagenes Exemplar wird wie immer „defekt“; ohne Notiz steht der
Befund der Messung als Grund daran. Eine Prüfart ohne den Haken nimmt
keine Messwerte an.

**Die Grenzwerte**, wie Rentalars sie aus DIN VDE 0701-0702 führt – für
alle Prüfungen gleich, nicht einstellbar:

| Prüfschritt | Grenzwert | gemessen bei Schutzklasse |
|---|---|---|
| Schutzleiterwiderstand R<sub>PE</sub> | höchstens 0,3 Ω bei einer Leitung bis 5 m; je weitere **angefangene** 7,5 m 0,1 Ω mehr, höchstens 1 Ω – also 0,4 Ω bis 12,5 m, 0,5 Ω bis 20 m (12,6 m sind schon 0,5 Ω), 0,9 Ω bis 50 m, darüber 1 Ω | I |
| Isolationswiderstand R<sub>ISO</sub> | mindestens 1 MΩ (I), 2 MΩ (II), 0,25 MΩ (III) | I, II, III |
| Schutzleiterstrom I<sub>PE</sub> | höchstens 3,5 mA | I |
| Berührungsstrom I<sub>B</sub> | höchstens 0,5 mA | I (an leitfähigen Teilen ohne Schutzleiter) und II |

**Was gemessen sein muss.** Bei Schutzklasse I der Schutzleiterwiderstand
und ein Nachweis der Isolation – der Isolationswiderstand oder, wie die
Norm es als Ersatz zulässt, der Schutzleiter- oder der Berührungsstrom;
bei Schutzklasse II der Isolationswiderstand oder der Berührungsstrom; bei
Schutzklasse III genügt die Sichtprüfung, den Isolationswiderstand trägst
du ein, wo du ihn messen konntest. Fehlt etwas davon, schlägt Rentalars
„fehlgeschlagen“ vor; „bestanden“ geht dann nur mit Begründung in der
Notiz.

**Messwerte und Prüfprotokoll.** Unter „Bisherige Prüfungen“ hat eine
elektrische Prüfung in der Spalte **„Messwerte“** jeden Prüfschritt mit
Wert, Grenzwert und Bewertung und das Prüfgerät – eingeklappt, mit „1
außerhalb des Grenzwerts“, wenn ein Wert herausfiel – und den Link
**„Prüfprotokoll (PDF)“**: eine Seite mit eurer Firma, dem Gerät (ID,
Seriennummer, Modell, Hersteller, Schutzklasse, Leitungslänge), Prüfart,
Datum, Prüfer und Prüfgerät, den Prüfschritten mit Wert, Grenzwert und
Bewertung, dem Ergebnis – bestanden mit „nächste Prüfung fällig bis …“ –,
den Befunden, der Notiz und Platz für die Unterschriften des Prüfers und
der verantwortlichen Person, in der Sprache eurer Dokumente. Ein
hochgeladenes Protokoll des Prüfgeräts bleibt daneben in der Spalte
„Protokoll“.

**Über die Schnittstelle** (Abschnitt 16, „API-Token“): Prüfarten nennen
`is_electrical`; `POST /material-items/{id}/inspections` nimmt die
Messwerte mit – Schutzklasse und Leitungslänge, wenn sie fehlen, vom
Exemplar –, `POST /material-items/{id}/inspections/check` bewertet sie,
ohne etwas zu speichern, jede Prüfung nennt Messwerte, `evaluation` und
`report_url`, und `GET /inspections/{id}/report` liefert das
Prüfprotokoll.

**Was fällig ist:** **Materialverwaltung → Prüfungen** listet alle
überfälligen und bald fälligen Prüfungen, die dringendsten zuerst, mit
Lagerort und Status. Filtern lässt sich nach Prüfart, nach Stand
(„überfällig und bald fällig“, „überfällig“, „bald fällig“) und mit
„Fällig innerhalb von … Tagen“ (voreingestellt 30). Ein Klick auf die ID
führt zu den Prüfungen des Exemplars. Oben rechts führt **„Prüfarten“** (für
alle, die die Einstellungen lesen dürfen) zur Verwaltung der
Prüfarten.

**Viele Exemplare auf einmal prüfen** (dafür braucht es das
Recht, Material zu ändern). Vor jeder Zeile der Liste steht ein Kästchen,
das Kästchen im Kopf wählt alle auf der Seite. Sobald ein Exemplar gewählt
ist, erscheint unter der Liste eine Leiste mit **„Gewählte Exemplare
prüfen“**; sie führt zur Seite „Mehrere Exemplare prüfen“:

- Oben stehen, was für alle gilt: die **Prüfung** (nur Prüfarten, die für
  alle gewählten Exemplare gelten; die Prüfart, nach der du die Liste
  gefiltert hast, ist schon gewählt), das **Datum** (heute), **„Geprüft
  von“** (du selbst) und bei einer elektrischen Prüfart das **Prüfgerät**
  – **einmal für alle**, vorbelegt mit dem, das du zuletzt eingetragen hast.
- Darunter steht je Exemplar eine Zeile mit **Ergebnis**, **Notiz** und,
  bei einer elektrischen Prüfart, **„Sichtprüfung bestanden“** (das
  Kästchen im Tabellenkopf hakt alle an), Schutzklasse, Leitungslänge, den
  Messwerten und der Funktionsprüfung – wie auf der Seite eines einzelnen
  Exemplars. Das Ergebnis „nach den Messwerten (elektrisch)“ nimmt, was die
  Grenzwerte vorschlagen; eine andere Wahl gilt, „bestanden“ gegen den
  Vorschlag braucht wie dort einen Grund in der Notiz.
- **„Prüfungen erfassen“** speichert für jedes Exemplar eine Prüfung.
  **Alles oder nichts:** Verstößt ein Exemplar gegen eine Regel der
  einzelnen Prüfung, wird nichts gespeichert; die Seite behält alles, was
  du eingetragen hast, und zeigt am Exemplar, was fehlt. Höchstens 1.000
  Exemplare auf einmal.

Über die Schnittstelle: `POST /material-items/inspections/batch` (JSON)
mit Prüfart, Datum, Prüfer, Prüfgerät und `items` – je Exemplar `item`
(die ID in der Datenbank), `result`, `note` und die Messwerte; Fehler
nennen den Eintrag (`items[1].note`).

Einmal am Tag meldet Rentalars dem Lager neu fällige Prüfungen – jede nur
einmal, gesammelt in einer Benachrichtigung „Fällige Prüfungen“.

**Und beim Packen?** Die Packliste weist an einer Zeile darauf hin, wenn
Exemplare des Produkts eine überfällige Prüfung haben. Wählst du ein
solches Exemplar für die Packliste oder geht es bei der Ausgabe raus, warnt
Rentalars („Die Prüfung von 0742 ist überfällig.“). Es verhindert nichts –
entscheiden müsst ihr.

### Audits und To-Dos

Ein **Audit** ist eine kurze Kontrolle eines Exemplars: Ist
das Label noch dran, der Klett am Kabel, ist es sauber und vollständig?
Anders als eine Prüfung hat es kein Ergebnis je Prüfart, kein Protokoll
und sperrt nichts – entweder ist das Stück **in Ordnung**, oder du
notierst, was zu tun ist, als **To-Do**.

**Einstellungen → Audits:**

- **Audit-Intervall (Monate)** – voreingestellt 24, also zwei Jahre;
  **0** schaltet Audits aus: Dann wird nichts fällig, Audits und To-Dos
  lassen sich trotzdem notieren.
- **Schnellauswahl für To-Dos** – eine pro Zeile, höchstens 12;
  voreingestellt „Label fehlt“, „Klett fehlt“, „Beschädigt“, „Reinigen“
  und „Teile fehlen“ (ein englisches Unternehmen erhält sie auf Englisch).
  Sie erscheinen als Knöpfe im Audit und auf der Seite eines Exemplars.

Ansehen darf die Seite, wer die Einstellungen lesen darf, ändern, wer sie
ändern darf.

**Wann ist ein Audit fällig?** Ein Intervall nach dem letzten Audit –
gleich, was es ergab; die notierten To-Dos werden als To-Dos erledigt,
nicht durch ein neues Audit. Ein Exemplar, das **noch nie** geprüft wurde,
ist ein Intervall nach seiner **Anlage in Rentalars** fällig – nicht
sofort. Eine frische Installation oder 3.000 heute importierte Exemplare
werden also nicht auf einen Schlag fällig, sondern nach und nach, die
ältesten zuerst. **Ausgemusterte, verkaufte und verlorene** Exemplare und
**Mengenmaterial** werden nie fällig, lassen sich aber trotzdem prüfen.

**Der Audit-Modus:** **Materialverwaltung → Audit** (für alle, die
Material ändern dürfen) – für eine Runde durchs Lager, am Telefon wie am
Rechner, auch ohne JavaScript:

1. Unter **„ID des Exemplars“** die ID tippen oder das Etikett scannen –
   `0427`, `427`, `#0427` oder die Adresse aus dem QR-Code –, Enter.
2. Rentalars zeigt das Exemplar mit letztem Audit und wann das nächste
   fällig ist, und darunter kompakt seine **Stammdaten**: ID,
   Modell, Hersteller, Kategorie, Seriennummer, Rechnungsdatum, „Gekauft
   bei“, mit dem Recht „Einkaufs- und Kaufpreise sehen“ den Kaufpreis,
   Lagerort, Status, Schutzklasse, die kategoriespezifischen Angaben
   (etwa die Länge) und die eigenen Felder – vertrauliche nur mit diesem
   Recht. Jede Angabe steht da, auch eine leere: als rotes **„–“** (ein
   Bildschirmleser sagt „nicht erfasst“), ein leeres Pflichtfeld mit
   „Pflichtangabe fehlt“. Fehlt etwas, öffnet **„Exemplar bearbeiten“**
   daneben das Formular; nach dem Speichern – oder mit „Abbrechen“ – bist
   du wieder im Audit desselben Exemplars.
3. Ist alles gut: **„In Ordnung“**. Schneller geht es mit dem Feld
   **„In Ordnung – nächste ID“** darunter, in dem der Cursor schon steht:
   die nächste ID tippen oder scannen, Enter – das gezeigte Exemplar ist
   als in Ordnung erfasst, und das nächste steht da. Leer geht Enter
   zurück zum Feld oben.
4. Gibt es etwas zu tun: unter **„To-Dos notieren“** die Knöpfe der
   Schnellauswahl anhaken und/oder ein **„Weiteres To-Do“** eintippen, auf
   Wunsch eine **„Notiz zum Audit“**; offene To-Dos des Exemplars, die
   inzwischen erledigt sind, hakst du unter „Offene To-Dos – hake ab, was
   erledigt ist“ ab. Dann **„Audit speichern“**.

**„In dieser Runde geprüft“** listet, was du in dieser Runde erfasst hast,
mit Ergebnis und Uhrzeit; **„Neue Runde“** beginnt eine neue. Die Runde
gehört zu deiner Anmeldung.

**To-Dos am Exemplar:** Die Seite eines Exemplars hat den Kasten **„Audit
und To-Dos“** mit dem letzten Audit, dem nächsten fälligen, den **offenen
To-Dos** – jedes mit „erledigt“ zum Abhaken –, dem Feld **„To-Do
notieren“** samt den Knöpfen der Schnellauswahl, den zuletzt erledigten
To-Dos (eingeklappt) und den **bisherigen Audits**. „Audit erfassen“
öffnet den Audit-Modus mit diesem Exemplar. Ein To-Do notierst du
jederzeit, nicht nur im Audit. Ein offenes To-Do mit demselben Text wird
nicht doppelt notiert; gelöscht wird keins, nur erledigt. Audits und
To-Dos stehen im Verlauf des Exemplars („Audit: in Ordnung“, „To-Do
notiert: Label fehlt“).

**Offene Punkte:** Der Reiter **Materialverwaltung → Offene Punkte** hat drei Unterreiter, jeder mit der Zahl seiner
Einträge. Die Summe dieser drei Zahlen steht auch am Reiter
„Offene Punkte“ selbst, auf jedem Reiter der Materialverwaltung – so
siehst du von überall, ob und wie viel offen ist:

- **„Material ohne Produkt“** – die Exemplare, die noch keinem Produkt
  zugeordnet sind und deshalb nicht verplant werden können (unten,
  „Material einem Produkt zuordnen“).
- **„Material mit To-Do“** – eine Zeile je offenem To-Do (ohne
  ausgemusterte, verkaufte und verlorene Exemplare), als Tabelle wie jede
  Liste: suchen nach To-Do, Name oder ID,
  filtern nach To-Do und Kategorie, nach To-Do gruppieren („Label fehlt“
  an 20 Kabeln). Wer Material ändern darf, hakt Zeilen an und erledigt sie
  mit **„Gewählte To-Dos erledigt“** auf einmal.
- **„Audit fällig“** – die Exemplare, deren Audit fällig ist, die ältesten
  zuerst, mit letztem Audit, „Fällig seit“ und offenen To-Dos; ein Klick
  auf die ID führt zum Kasten „Audit und To-Dos“, der Knopf **„Audit“** in
  der Zeile öffnet den Audit-Modus mit diesem Exemplar, **„Audit
  starten“** oben ohne.

### Verbaut in – Racks, Cases, Sets aus Einzelteilen

Steckt ein Exemplar in einem anderen – der Funkempfänger im Rack, das Kabel
im Case –, baust du es direkt auf seiner Seite ein: unter „Verbaut in /
Enthält“ bei **„Einbauen in“** die ID oder den Namen des äußeren Stücks
eintippen und aus den Vorschlägen wählen, die **Art der Verbindung**
wählen, **„Einbauen“**. Dasselbe steht unter „Exemplar bearbeiten“ im Feld
**„Verbaut in (ID)“**. Die Arten der Verbindung:

- **fest verbaut**: verschraubt, verkabelt, bleibt drin. Das Teil reist nur
  mit seinem Rack und wird **nicht einzeln verplant**. Es zählt nicht zum
  planbaren Bestand seines Produkts.
  Ausnahme: Du hakst **„Einzeln vermietbar“** an – für fest eingebaute
  Teile, die bei Bedarf doch herausgenommen werden.
- **lose enthalten**: liegt nur drin. Das Teil bleibt einzeln planbar. Wird
  aber das Case verplant, gelten seine losen Inhalte als **mit belegt**.

Die Seite eines Exemplars zeigt beides: worin es steckt und was in ihm
steckt.

**Von der anderen Seite: „Enthält“.** Dieselbe Verbindung lässt sich auch
am äußeren Stück pflegen. Auf der Seite des Racks, unter „Verbaut in /
Enthält“, tippst du bei **„Exemplar hinzufügen“** die ID oder den Namen
des Empfängers ein, wählst die Art der Verbindung und drückst **„Hier
verbauen“**. Neben jedem Inhalt steht, wie er wieder herauskommt:
„herausnehmen“ bei lose enthaltenen (siehe „Entnehmen und Zurücklegen“),
„entfernen“ bei fest verbauten. Es ist dieselbe Angabe wie „Verbaut in“ am
Empfänger – nur von der anderen Seite eingetragen.

Im Kreis geht es nicht: Ein Rack kann nicht in etwas verbaut werden, das
selbst in ihm steckt. Und ein Stück, das schon woanders verbaut ist, wird
über „Enthält“ nicht stillschweigend umgehängt – Rentalars sagt, wo es
steckt; zum Umbauen änderst du „Verbaut in“ am Stück selbst.

> **Beispiel.** Das Produkt T-050 „Funkempfänger“ hat sechs Exemplare. Vier
> davon sind fest in einem Funkrack verbaut. Die Produktliste zeigt den
> Bestand als „2 / 6 Stk.“: sechs vorhanden, zwei einzeln planbar. Wer das
> Funkrack bucht, bekommt die vier anderen mit.

Ein Exemplar, in dem noch etwas steckt, lässt sich nicht ausmustern. Nimm
erst die Inhalte heraus (bei ihnen „Verbaut in“ leeren).

**Mengenmaterial einbauen**. Nicht alles, was in einem Rack
steckt, ist ein Exemplar mit eigener ID: Zehn Meter Kabel, vier Stecker
oder eine Handvoll Schrauben sind Mengenmaterial (oben, „Mengenmaterial“).
Auch das baust du ein, auf der Seite des Racks, Cases oder Fahrzeugs:
Dort steht der Kasten **„Verbautes Mengenmaterial“**. Unter **„Verbauen“**
suchst du das Mengenmaterial nach ID oder Namen („Mengenmaterial (ID)“),
trägst die **Menge** und auf Wunsch eine Notiz ein („Ersatzkabel“) und
drückst **„Verbauen“**. Der Kasten listet danach, was drinsteckt – mit
Menge, „Verbaut seit“ und „Verbaut von“. Mit **„herausnehmen“** nimmst du
alles heraus, oder du tippst vorher eine kleinere Menge ins Feld daneben
(„Menge zum Herausnehmen; leer: alles“) und nimmst nur die heraus.

- Die verbaute Menge **verlässt den freien Bestand**: Die Zeile des
  Mengenmaterials zeigt weniger, Bestand und Verfügbarkeit des Produkts,
  Planung und Packen rechnen damit – nichts wird doppelt gezählt. Auf
  der Seite des Mengenmaterials steht der Kasten **„In andere Exemplare
  verbaut“** mit „Freier Bestand“, „Verbaut“ und „Zusammen“ und der
  Tabelle, worin wie viel steckt.
- Mehr, als frei ist, lässt sich nicht verbauen; nur
  Mengenmaterial, das einsatzbereit ist, und nur in ein einzelnes
  Exemplar, das nicht ausgemustert ist – nicht in anderes Mengenmaterial.
- Geht das Rack raus, **geht das Verbaute mit**. Auf seiner Packliste steht
  es unter dem Rack als **„enthält 10 m × Kabel …“** und zählt nicht noch
  einmal als eigene Zeile (Abschnitt 10).
- Einbau und Ausbau – auch ein Teil davon – stehen mit Menge, Nutzer und
  Zeit im Verlauf **beider** Seiten. Ein Exemplar, in dem Mengenmaterial
  verbaut ist, lässt sich nicht verkaufen (unten, „Gebrauchtverkauf aus
  dem Bestand“).
- Es gibt kein Bestandsbuch: Rentalars schreibt keine Bewegungen fort,
  sondern ändert die Menge und hält den Vorgang im Verlauf fest.

Ein- und Ausbau stehen mit Zeitpunkt und Nutzer im Verlauf **beider**
Exemplare. Ist ein Teil in einem Rack defekt oder seine Prüfung überfällig,
zeigt das Rack es oben auf seiner Seite – so fällt es auf, bevor das Rack
rausgeht. Geht das Rack bei einer Ausgabe raus, geht sein Inhalt mit, und
mit der Rücknahme kommt er zurück (Abschnitt 10, „Exemplare wählen“).

### Entnehmen, Zurücklegen und Herauslösen

**Entnehmen und Zurücklegen.** Ein lose enthaltenes Mikrofon wird kurz
woanders gebraucht? Auf seiner Seite steht unter „Verbaut in“ der Knopf
**„Aus 0500 entnehmen“** – ein Klick, und es ist nicht mehr im Case.
Rentalars merkt sich, woher es kam: Danach steht dort **„In 0500
zurücklegen“**, und ein Klick legt es wieder hinein. Auf der Seite des
Cases tut „herausnehmen“ neben dem Inhalt dasselbe. Fest verbaute Teile
entnimmt man nicht nebenbei; bei ihnen änderst du „Verbaut in“ bewusst.

**Herauslösen für ein Projekt.** Manchmal soll ein loser Inhalt nur für
*ein* Projekt im Lager bleiben – das Case fährt zum Kunden, aber ohne das
teure Mikrofon, das zur selben Zeit woanders gebraucht wird. Dafür gibt es
auf der Seite des Mikrofons den Abschnitt **„Für Projekte herausgelöst“**.
Er erscheint, sobald ein laufendes oder kommendes Projekt das Case
mitnimmt: Projekt wählen („Herauslösen für Projekt“), **„Für dieses
Projekt herauslösen“**.

- Das Mikrofon ist während dieses Projekts **frei** für andere.
- Die **Packliste** des Projekts nennt, was fehlt: „0123 Funkmikrofon
  bleibt da (aus 0500 herausgelöst)“ – an der Zeile des Cases und oben in
  der Liste.
- Bei der Ausgabe geht das Case ohne das Mikrofon raus.

**„geht wieder mit“** neben dem Projekt macht das Herauslösen rückgängig.
Herauslösen darf, wer packen darf (Modul „Packen und Ausgabe“).

### Material einem Produkt zuordnen

Am **Modell**, Feld „Produkt“: gilt für alle seine Exemplare. Das ist der
Normalfall.

Am **Exemplar**, Feld „Abweichendes Produkt“: nur für den Sonderfall, dass
ein einzelnes Stück zu einem anderen Produkt gehört als seine Geschwister –
etwa ein umgebautes Gerät.

Gehört das Produkt zu einer anderen Hauptkategorie als das Material – ein
Stativ aus „Rigging“ an einem Produkt aus „Ton“ –, weist Rentalars beim
Speichern darauf hin. Das ist kein Fehler, oft aber ein verrutschter
Mausklick.

Die Liste **„Materialverwaltung → Offene Punkte → Material ohne
Produkt“** zeigt alles, was noch
keinem Produkt zugeordnet ist und deshalb nicht verplant werden kann.

**Als Produkt anlegen.** Hat ein Modell noch kein Produkt, steht auf seiner
Seite neben „Produkt“ der Knopf **„Als Produkt anlegen“**. Ein Klick legt
ein Produkt mit dem Namen des Modells an – ein Mietprodukt, in einer
Kategorie für Verkauf ein Verkaufsprodukt –, mit der nächsten freien
Artikelnummer und den Voreinstellungen der Kategorie, und ordnet ihm das
Modell zu. Danach öffnet sich das Formular des Produkts: Trag den Preis
ein, er steht zunächst auf 0. Ohne das Recht, Preise zu sehen, öffnet sich
die Seite des Produkts, und den Preis trägt jemand mit dem Recht ein. Den
Knopf hat, wer Material und Produkte bearbeiten darf. Bei Kundenmaterial
steht dort „Neues Produkt“, denn das Produkt braucht seinen Eigentümer
(Abschnitt 5, „Kundenmaterial“).

**Vom Produkt aus.** Auf der Seite eines Produkts unter „Zugeordnetes
Material“ legst du mit „Neues Materialmodell“ ein Modell an, das gleich
dazugehört, oder übernimmst ein vorhandenes mit „Vorhandenes Modell
zuordnen“ (Abschnitt 5, „Bestand und Verfügbarkeit eines Produkts“).

### Etiketten

Jedes Exemplar bekommt ein Etikett mit seiner **ID** und einem **Code**:

- **QR-Code** – er enthält die Adresse der Seite des Exemplars, etwa
  `https://rentalars.eure-firma.example/m/0042`. Die Kamera jedes Telefons
  öffnet sie; wer angemeldet ist, steht direkt auf der Seite des
  Exemplars und kann einen Defekt melden oder die Prüfungen nachsehen.
  Wohin der QR-Code der Etiketten für den Etikettendrucker führt, lässt
  sich einstellen (unten, „Etiketten einrichten“).
- **Strichcode** (Code 128) – er enthält nur die ID, für Handscanner; nur
  auf den Bögen (unten).

**Drei Etiketten für den Etikettendrucker.** Es gibt drei
Etiketten im Layout eurer Firma, gemacht für Etikettendrucker von Brother:

| Etikett | Rolle | Was darauf steht |
|---|---|---|
| **„Klein, 17 × 54 mm“** | DK-11204 | Logo, Name, QR-Code, Telefonnummer, Webadresse, ID und klein ein Text für Finder |
| **„Groß, 29 × 90 mm“** | DK-11201 | dasselbe, größer – für Geräte, Cases, Racks |
| **„Kabel, 29-mm-Rolle“** | DK-22210, Endlosrolle | am Anfang 18 mm frei – die erste Wicklung, die von den folgenden verdeckt wird –, dann ein Text, der sich um das Kabel legt und sich quer zum Band wiederholt, höchstens 14 mm auseinander; unten eine Fahne mit Logo, dem kürzeren Namen für Kabel, Webadresse, Telefonnummer, ID und darunter dem QR-Code. 60 bis 200 mm lang, voreingestellt 90 mm – ein längeres Etikett wiederholt den Text öfter |

Bei **Kundenmaterial** steht statt eures Namens „Eigentum von …“ mit dem
Namen des Kunden (Abschnitt 5, „Kundenmaterial“).

**Gut lesbar**. Die drei Etiketten werden in der Schrift
**Liberation Sans** gedruckt – maßgleich mit Arial, der Schrift eurer
P-touch-Vorlagen, und mit Rentalars ausgeliefert –, in den Schriftgrößen
der Vorlagen und in reinem Schwarz; verkleinert wird ein Text nur, wenn er
nicht in sein Feld passt. Das Logo druckt schwarz-weiß in der Auflösung des
Druckers. Alles liegt im Bereich, den ein Brother-QL-Drucker bedrucken
kann, an den Enden mit etwas Abstand – so schneidet der Drucker nichts mehr
ab. Der **QR-Code** sitzt an der Stelle der Vorlage und ist
mindestens so groß wie dort – auf dem kleinen Etikett etwa 8,5 mm, auf dem
großen etwa 16,8 mm, auf dem Kabeletikett etwa 8,2 mm –, wächst aber in den
freien Platz daneben (ganze Druckerpunkte, damit der Code scharf bleibt).

**Wie die Originale**. Auf dem kleinen und dem großen Etikett
steht der Titel in der Größe der Vorlage über der ganzen Breite, darunter
Logo und Text neben dem QR-Code; der „Text für Finder“ steht in seinem Feld
der Vorlage. Die Kabelfahne hat den QR-Code unten links, das Logo darüber und
die Texte daneben; der Text um das Kabel wiederholt sich bei 90 mm fünfmal
statt dreimal. Eine ID mit acht Ziffern wird kleiner gesetzt, statt
abgeschnitten zu werden. **Die Reihenfolge im Titel** („Max Muster - BSP“
oder „BSP - Max Muster“) druckt Rentalars so, wie du sie unter
Einstellungen → Etiketten bei „Name auf Etiketten“ eintippst – ebenso die
Schreibweise der Webadresse (bei „Text um das Kabel“). Stimmt ein Etikett
nicht mit der Vorlage überein, ändere zuerst diese Einstellungen.

**So geht's:**

- **Ein Etikett:** **„Etikett“** oben auf der Seite des Exemplars öffnet
 ein kleines Fenster mit den drei Etiketten – das unter
  Einstellungen → Etiketten vorgeschlagene zuerst – und darunter „Bögen und
  Rolle“. Ein Klick öffnet die Druckseite genau dieses Etiketts in einem
  neuen Tab, mit dem Druckdialog (unten). „Weitere Einstellungen“ führt zur
  Seite „Etiketten“. Ausgemusterte, verkaufte und verlorene Exemplare
  bekommen kein Etikett; das Fenster sagt es.
- **Alle Exemplare eines Modells:** **„Etiketten“** oben auf der Seite des
  Modells führt mit allen Exemplaren des Modells, die noch
  da sind, zur Seite „Etiketten“.
- **Eine Auswahl:** in „Materialverwaltung → Exemplare“ die Exemplare
  ankreuzen und in der Leiste unten **„Etiketten“** drücken (siehe „Viele
  Exemplare auf einmal ändern“). Nach „Kauf einpflegen“ führt „Etiketten
  drucken“ mit den neuen Exemplaren dorthin (oben, „Kauf einpflegen“).
- **Ein Bereich:** Diese Knöpfe führen auf die Seite „Etiketten“. Dort
  lässt sich die Auswahl unter **„IDs“** ändern – durch Kommas oder
  Leerzeichen getrennt, Bereiche als `0100-0120` – oder mit „oder alle von
  ID“ … „bis ID“ ein ganzer Bereich angeben.

Auf der Seite „Etiketten“ wählst du unter **„Etikett“** eines der drei
Etiketten – vorgewählt
ist das, das unter Einstellungen → Etiketten vorgeschlagen ist – und
drückst **„Drucken“**. Ein neuer Tab zeigt die Etiketten, eines je Seite
in seiner genauen Größe, und öffnet von selbst den Druckdialog des
Browsers. Wähle dort

- den **Etikettendrucker**,
- das **Papier in der Größe des Etiketts**, etwa 17 × 54 mm,
- die Skalierung **100 % (tatsächliche Größe)**, nicht „an Seite
  anpassen“,
- **keine Ränder**.

Die Leiste über den Etiketten sagt es noch einmal, mit der passenden Rolle
von Brother; ihr Knopf „Drucken“ öffnet den Dialog erneut. Direkt aus dem
Browser gehen bis zu 240 Etiketten auf einmal. **„PDF erstellen“** macht
dieselben Etiketten als Datei, auch für mehr. „Auswahl zeigen“ listet die
gewählten Exemplare; die Seite „Etiketten“ bleibt offen, falls du noch
weitere brauchst.

**Weitere Bögen** stehen unter „Etikett“ zur Wahl:

| Bogen | Wofür |
|---|---|
| A4, 24 Etiketten 70 × 37 mm (3 × 8) | Geräte, Cases, Racks |
| A4, 65 Etiketten 38,1 × 21,2 mm (5 × 13) | Kabel und kleine Teile |
| Etikettendrucker, 62 × 29 mm, eines je Etikett | Rollendrucker |

Sie tragen ID und Kurzname, und für sie wählst du den **Code** –
„QR-Code (öffnet die Seite des Exemplars)“ oder „Strichcode (Code 128, die
ID)“. Auf den größeren steht unter einem QR-Code auch euer Firmenname –
bei Kundenmaterial „Eigentum von …“, beim Strichcode unter dem Namen. Ist
ein Bogen schon angebrochen, sagt **„Am Anfang frei lassen“**, wie viele
Felder übersprungen werden. Bögen druckst du über „PDF erstellen“, in
Originalgröße („100 %“), sonst passen die Etiketten nicht auf den Bogen.

Mehr als 240 Etiketten auf einmal entstehen als PDF **im Hintergrund**: Du
kannst weiterarbeiten und bekommst Bescheid, sobald das PDF fertig ist; es
liegt dann unter Mein Konto → „Aufgaben im Hintergrund“. Höchstens 5.000
Etiketten gehen auf einmal.

**Etiketten einrichten.** Was auf den drei Etiketten steht, legt ein
Administrator unter **Einstellungen → Etiketten** fest – auch über
**„Etiketten einrichten“** auf der Seite „Etiketten“:

- **„Logo für Etiketten“** – PNG oder JPEG, am besten quadratisch;
  schwarz-weiß druckt ein Etikettendrucker am saubersten. Leer: das Logo
  aus den Firmendaten.
- **„Name auf Etiketten“** neben dem Logo und der kürzere **„Name auf
  Kabeletiketten“**.
- **„Telefonnummer“** und **„Text vor der Telefonnummer“**
  (voreingestellt „Telefonnummer:“), dazu **„Text vor der ID“**
  (voreingestellt „Equipment-ID:“).
- **„Gedruckte Webadresse“** – so, wie sie auf dem Etikett stehen soll,
  etwa `EXAMPLE.DE`.
- **„Text um das Kabel“** – er wird genau so gedruckt, wie du ihn
  eintippst, in Groß- und Kleinbuchstaben. Leer steht dort die gedruckte
  Webadresse, und zwar so, wie sie im Feld darüber oder in den Firmendaten
  steht (oft klein geschrieben). Willst du sie in Großbuchstaben um das
  Kabel, tippst du sie hier so ein, etwa `EQUIP.EXAMPLE.DE`.
- Der **„Text für Finder“**, etwa wohin man ein gefundenes Gerät meldet.
- **„QR-Code führt zu“** – eine Webadresse mit `{id}` an der Stelle der
  ID, etwa `https://equip.example.de/id/{id}`; leer führt er zur Seite des
  Exemplars in Rentalars.
- **„Vorgeschlagenes Etikett“** und die **„Länge des Kabeletiketts
  (mm)“**.

Leere Felder nehmen die Angaben aus Einstellungen → Firmendaten und
Grundeinstellungen. Daneben zeigt eine **Vorschau** die drei Etiketten am
Beispiel des Exemplars 0427, so wie gespeichert. Eine
gestrichelte Linie zeigt darin, was der Etikettendrucker bedrucken kann – sie
wird nicht mitgedruckt –, und unter dem Kabeletikett steht, wie lang sein
freier Anfang ist. Ist das Kabeletikett zu kurz für die 18 mm, wird der
freie Anfang gekürzt, und die Vorschau sagt es.

### Scannen: Codes lesen statt tippen

Rentalars liest Codes von Etiketten: mit der **Kamera** des
Telefons oder Tablets, mit einem **Handscanner** oder – ohne alles davon –
von dir **getippt**. Alle drei Wege liefern Rentalars dasselbe, einen Text,
und der Rest ist gleich. Das Feld zum Eintippen gibt es immer; die Kamera
ist ein Extra.

**Wo du scannen kannst.**

- **In der Materialverwaltung**, im Feld **„Exemplar-ID“** im Kopf jedes
  Reiters (oben, „Ein Exemplar über seine ID öffnen“): Der Knopf
  **„Scannen“** daneben öffnet die Kamera; Rentalars springt zur Seite des
  Exemplars, des Produkts, der Liste eines Lagerplatzes.
- **Auf der Packliste** beim Packen und bei der Rücknahme (Abschnitt 10,
  „Scannen beim Packen und bei der Rücknahme“).
- **In der Planung** mit dem Knopf **„Exemplare scannen“** neben „Position
  ohne Produkt“: Jedes gelesene Exemplar kommt mit Menge 1 in die
  Planung, und zwar als Wunsch für genau dieses Exemplar (Abschnitt 7,
  „Ein bestimmtes Modell oder Exemplar“); der Code eines Produkts legt das
  Produkt an. Der Dialog bleibt offen für den nächsten Code, jeder wird mit
  „Hinzugefügt: …“ bestätigt; was sich nicht planen lässt, sagt es („kann
  nicht geplant werden“).

**Was Rentalars erkennt.** Die ID eines Exemplars (`0042`, `42`, `#0042`);
die Adresse im QR-Code eines Etiketts, also `…/m/0042` oder die Adresse, die
ihr unter Einstellungen → Etiketten bei „QR-Code führt zu“ eingestellt habt
(oben, „Etiketten“); der Strichcode (Code 128) mit der ID; eine
Seriennummer; die GTIN eines Produkts (8, 12, 13 oder 14 Stellen, auf dem
Produkt eingetragen, Abschnitt 5); ein Lagerplatz wie `01-A-1` und der Name
eines Lagerorts. Zeichen, die ein Scanner vor oder hinter den Code setzt,
stören nicht. Du bekommst nur, was du sehen darfst: Ein Code, der zu etwas
führt, das du nicht lesen darfst, antwortet wie ein unbekannter – ein Scan
verrät nicht, dass es etwas gibt.

**Die Kamera.** Im Dialog **„Code scannen“** zeigt Rentalars das Kamerabild
(„Halte den Code vor die Kamera“), darunter das Feld **„Code eintippen oder
scannen“** und, wo die Kamera es kann, die **Taschenlampe**.

- Die Kamera braucht eine **gesicherte Verbindung (HTTPS)** – Rentalars
  bei euch muss also über `https://` laufen (Abschnitt 16, „Serveradresse
  und Zertifikat“); nur auf dem Rechner, auf dem Rentalars selbst läuft
  (`localhost`), geht es ohne.
- Der Browser muss Codes im Kamerabild erkennen können. Das können
  **Chrome, Edge und die Browser auf Android**. **Firefox und Safari**
  (auch auf dem iPhone) können es nicht: Dort sagt der Dialog es, und du
  tippst den Code oder nimmst einen Handscanner.
- Das Bild bleibt im Browser. An Rentalars geht nur der gelesene **Text**;
  Rentalars speichert kein Foto.
- Erlaubst du dem Browser die Kamera nicht, oder gibt es keine, sagt der
  Dialog es und das Feld bleibt.

**Der Handscanner** (USB oder Bluetooth) tippt wie eine Tastatur in das Feld,
in dem der Cursor steht, und schickt Enter hinterher. Er braucht nichts
eingerichtet. Wo ein Feld den Scanner erwartet – etwa beim Packen –, hat es
schon den Cursor.

### Viele Exemplare auf einmal ändern

Zwanzig neue Kabel kommen ins Regal B, ein ganzes Case geht in Reparatur:
In **Materialverwaltung → Exemplare** hat jede Zeile vorne ein Kästchen
(dafür braucht es das Recht, Material zu ändern). Das Kästchen im
Tabellenkopf wählt alle auf dieser Seite – stelle die Seitenlänge auf 200
(oder unter „Eigene Anzahl“ bis 1.000) oder filtere vorher, wenn es mehr
sind.

Sobald ein Exemplar gewählt ist, erscheint unter der Liste eine Leiste –
beim Scrollen bleibt sie am unteren Rand stehen, wie die Leiste der
gewählten Positionen in der Planung. Sie zeigt, wie viele gewählt sind,
und daneben:

- **Status** – mit **Grund**; für „defekt“ ist er Pflicht,
- **Lagerort** – oder „kein Lagerort“,
- **Lagerplatz** – leer lässt die Plätze, wie sie sind; ein
  anderer Lagerort ohne neuen Platz entfernt den alten,
- **Produkt** – oder „wie das Modell“.

Was auf „– unverändert –“ bleibt, bleibt, wie es ist. **„Gewählte
Exemplare ändern“** ändert alle auf einmal, höchstens 1.000.

**Alle oder keins:** Verstößt ein einziges Exemplar gegen eine Regel – etwa
ein defektes, das auf „verfügbar“ soll –, ändert Rentalars nichts und nennt
das Exemplar. Jede Änderung steht im Verlauf des einzelnen Exemplars.
Hinweise, die nichts aufhalten, erscheinen danach: dass verbaute Exemplare
dort bleiben, wo ihr Gerät steht, oder dass ein Produkt zu einer anderen
Hauptkategorie gehört.

**„Etiketten“** in derselben Leiste führt mit den gewählten Exemplaren zur
Seite „Etiketten“ (oben). **„Auswahl aufheben“** nimmt alle Haken heraus;
ohne Haken verschwindet die Leiste wieder.

### Zeitstrahl

Wann ist dieses Gerät frei? Der Reiter **„Zeitstrahl“** an jedem Exemplar
und jedem Modell (ebenso an Produkten und Personen) zeigt Wochen
nebeneinander, Tag für Tag:

- am **Exemplar** seine Einsätze, Projekte, die genau dieses Exemplar
  wünschen, Zeiten mit seinem Gerät oder aus ihm herausgelöst, Sperrzeiten
  und fällige Prüfungen; darunter, wie viele Stück seines Produkts an
  jedem Tag frei sind, und die Projekte, die das Produkt brauchen;
- am **Modell** die freien Stück seines Produkts und je Exemplar eine Zeile
  (die ersten 40).

Die Zahlen in der Zeile „frei“ sind die freien Stück des Tages; die kleine
Zahl daneben, was Optionen zusätzlich nehmen würden. Balken zeigen feste
Reservierungen, Optionen, was außer Haus ist und was gesperrt ist – die
Legende steht darunter. Projekte, die du nicht öffnen darfst, erscheinen
nur mit ihrer Nummer. Den Reiter gibt es an Exemplar, Modell
und Produkt nur mit dem Sonderrecht **„Verfügbarkeit von Material
sehen“** – die Rolle Crew hat es nicht (Abschnitt 16, „Rollen und
Rechte“).

Oben wählst du den Zeitraum: **„‹ früher“**, **„diese Woche“**,
**„später ›“**, ein Datum unter **„Von“** und die Zahl der **„Wochen“**
(eine bis zwölf).

### Auswertungen: Jahr wählen

Die Auswahlen eines Jahres (Profitabilität, Auswertungen des Materials)
bieten fünf Jahre zurück und **drei Jahre voraus**; vorgewählt ist
das laufende Jahr, und ein Jahr in der Adresse bleibt, wie es ist.

### Kalender-Link

Wann ist das Gerät unterwegs – im eigenen Kalender, ohne Rentalars zu
öffnen? Jedes Produkt, Materialmodell und Exemplar kann einen
**Kalender-Link** bekommen: eine geheime Adresse im Format iCalendar
(.ics), die dein Kalenderprogramm abonniert. Im Standard hat keines einen.

Der Kasten **„Kalender-Link“** steht auf der Seite des Exemplars (Reiter
„Exemplar“, unten), des Modells (Reiter „Modell“, unter seinen Exemplaren)
und des Produkts (Reiter „Produkt“, über dem Verlauf). Er sagt, was der
Kalender zeigt, und hat:

- **„Kalender-Link erstellen“** – danach steht die Adresse unter
  **„Adresse für Kalenderprogramme“** mit **„Kopieren“** und darunter,
  wann und von wem sie erstellt wurde;
- **„Neuen Link erstellen“** – ersetzt die Adresse durch eine neue; die
  alte funktioniert sofort nicht mehr;
- **„Link deaktivieren“** – schaltet die Adresse ab, ohne neue.

Die beiden letzten fragen vorher nach. Jede dieser Änderungen steht im
Verlauf des Produkts, Modells oder Exemplars („Kalender-Link (iCalendar)
erstellt“), die Adresse selbst nie – auch nicht im Änderungsprotokoll.

**Wer darf.** Den Kasten sieht, wer das Modul lesen darf – „Produkte“ beim
Produkt, „Material“ bei Modell und Exemplar –, das Sonderrecht
„Verfügbarkeit von Material sehen“ hat und alle Projekte lesen darf, nicht
nur die zugeordneten: Der Kalender nennt Projekte, und das ohne Anmeldung.
Erstellen, ersetzen und deaktivieren darf, wer das Modul außerdem
bearbeiten darf – und nur wer das darf, sieht auch die **Adresse**: Sie
funktioniert ohne Anmeldung, und beenden kann sie nur, wer den Link ändern
darf. Wer nur lesen darf, sieht, dass ein Link aktiv ist, seit wann und von
wem, und was der Kalender zeigt. Die Rolle Crew sieht den Kasten nicht.

**Was der Kalender zeigt** – was der Zeitstrahl zeigt (oben), als Termine
von 90 Tagen zurück bis zwei Jahre voraus:

- beim **Produkt** jede Buchung in einem Projekt, auch in einem Set oder
  Case: „3× 2027-0042 Stadtfest“, in der Beschreibung Projekt, Status und
  Menge, der Zeitraum mit den Pufferzeiten davor und danach; eine Option
  oder optionale Position als vorläufiger Termin („– Option“), ein Verkauf
  am Tag des Verkaufs; dazu die Sperrzeiten seiner Exemplare;
- beim **Modell** dasselbe für das Produkt seiner Exemplare (haben einzelne
  Exemplare ein abweichendes Produkt, für jedes dieser Produkte, mit dessen
  Namen);
- beim **Exemplar**, wann es mit einem Projekt unterwegs ist
  („Ausgegeben: …“) oder für dessen Packliste gewählt, wann ein Projekt
  genau dieses Exemplar wünscht, wann es mit seinem Gerät reist oder
  herausgelöst ist, seine Sperrzeiten und fällige Prüfungen. Buchungen seines Produkts, die
  kein Exemplar nennen, stehen im Kalender des Produkts.

Jeder Termin hat einen Link zum Projekt; öffnen kann es nur, wer sich
anmeldet und es sehen darf. **Nicht** im Kalender stehen Preise, Kunden,
Kontaktdaten und Orte. Ändert sich eine Buchung, ändert das
Kalenderprogramm ihren Termin, statt einen zweiten anzulegen. Die Texte
sind in der Sprache der Installation.

**Abonnieren.** Kopiere die Adresse und trag sie in deinem
Kalenderprogramm als abonnierten Kalender ein – je nach Programm „Per URL“
oder „Kalender abonnieren“. Das Programm holt die Termine dann selbst und
hält sie aktuell (Rentalars bittet, alle 30 Minuten nachzufragen). Es muss
Rentalars dafür erreichen; Google Kalender etwa holt die Adresse von
seinen eigenen Servern, also nur, wenn Rentalars aus dem Internet
erreichbar ist.

**Behandle die Adresse wie ein Passwort.** Sie funktioniert ohne
Anmeldung: Wer sie kennt, sieht diese Termine. Gib sie nur weiter, wem du
sie zeigen willst; ist sie in falsche Hände geraten, nimm „Neuen Link
erstellen“.

**Wenn das Material geht.** Wird ein Exemplar ausgemustert, verkauft oder
als verloren markiert oder ein Produkt deaktiviert, ist sein Kalender-Link
endgültig deaktiviert (im Verlauf: „Kalender-Link deaktiviert: Der
Datensatz ist nicht mehr in Gebrauch“); kommt es zurück, braucht es einen
neuen Link. Ein gelöschter Datensatz nimmt seinen Link mit. Ein Produkt
ohne eigenen Bestand – etwa ein Set oder eine Dienstleistung – hat keinen
Kasten. Über die Schnittstelle geht dasselbe:
`GET`, `POST` und `DELETE` auf `/products/{id}/calendar-link`,
`/material-models/{id}/calendar-link` und
`/material-items/{id}/calendar-link` (Abschnitt 16, „API-Token“); die
Adresse (`url`) nennt `GET` nur dem, der den Link ändern darf.

### Verlauf

Jedes Exemplar hat einen Verlauf: wann angelegt, jede Statusänderung, jede
Änderung an seinen Daten – auch an den Werten seiner eigenen
Felder –, jeder Ein- und Ausbau, jede Defektmeldung, jedes
Audit und jedes notierte und erledigte To-Do, und mit
welchen Projekten es unterwegs war – jeweils mit Zeitpunkt und Nutzer. Damit
die Liste lesbar bleibt, sind die einzelnen geänderten Felder eingeklappt:
„3 Änderungen“ klappt sie mit altem und neuem Wert auf.

### Was ein Exemplar einbringt

Hat sich das Gerät bezahlt gemacht? Auf der Seite eines
Exemplars steht der Kasten **„Ertrag“** – für alle, die die Auswertungen sehen
dürfen (Abschnitt 8): Er rechnet über die Projekte aller Kunden.
Er lädt kurz nach der Seite, denn Rentalars rechnet dafür alle Projekte
durch:

- **„Mit diesem Exemplar eingenommen“** – zusammen, und in wie vielen
  Projekten;
- **„davon zugeordnet“** – aus den Projekten, für die es beim Packen
  gewählt wurde: je Projekt der Anteil eines Stücks an dem, was die
  Positionen seines Produkts eingebracht haben;
- **„davon geschätzt“** – sein Anteil an den Stücken, die ohne gewähltes
  Exemplar rausgingen. Welches der zwanzig Kabel mitfuhr, weiß meist
  niemand; solche Stücke verteilt Rentalars gleichmäßig auf die Exemplare,
  die das Produkt damals hatte.
- **„Anteil am Kaufpreis“** – das Eingenommene im Verhältnis zum
  „Kaufpreis (netto)“, als Prozent und Balken: gelb ab 50 %, grün ab
  100 %. Diese Zeilen sieht nur, wer Einkaufs- und Kaufpreise sehen darf.
  Ein Exemplar, das als **Set** gekauft wurde (oben, „Neues Material
  anlegen“), rechnet zusammen mit seinem Set: „Das Set hat eingenommen“
  gegen den „Kaufpreis des Sets“.

Gezählt werden die Positionen nach ihren Rabatten, in Projekten, deren
Material rausging („Unterwegs“, „Wieder im Lager“, „Abgeschlossen“); die
Position eines Sets verteilt Rentalars nach den Preisen auf seine
Bestandteile. Optionale und alternative Positionen und Kundenmaterial
bringen nichts ein. Dieselbe Rechnung je Produkt zeigt Auswertungen →
„Material“ (Abschnitt 8, „Auswertungen“).

**Was ein Modell einbringt.** Auch die Seite eines Modells hat
den Kasten **„Ertrag“** – für dieselben Personen und gleich gerechnet, aber
zusammengezählt über alle seine Exemplare: **„Mit den Exemplaren dieses
Modells eingenommen“** und in wie vielen Projekten, „davon zugeordnet“ und
„davon geschätzt“, mit dem Recht für Kaufpreise dazu **„Kaufpreise
zusammen (netto)“** und **„Anteil an den Kaufpreisen“**. Hat das Modell
mehrere Exemplare, steht darunter je Exemplar, was es eingebracht hat, in
wie vielen Projekten und – mit dem Recht – sein Kaufpreis und sein Anteil;
diese Tabelle ist eingeklappt: **„Ertrag je Exemplar (12
Exemplare)“** klappt sie auf, auch ohne JavaScript, und die Summen darüber
bleiben immer sichtbar.
Ein Exemplar aus einem Kaufset zählt mit seinem Anteil am Preis des Sets.

### Anlagevermögen, Abschreibung und Restbuchwert

Für die Bücher wollen Steuerberatung und Buchhaltung wissen, was ein Gerät
gekostet hat und was es heute „noch wert“ ist. Rentalars rechnet
das aus. Es ist eine **vereinfachte Standardrechnung, keine
Steuerberatung**: Ob sie für euren Abschluss genügt, entscheidet die
Steuerberatung. Rentalars prüft die **GWG-Grenze** (netto je Stück, in den
Einstellungen): Kostet ein Stück mehr, wählst du „Anlagegut“ – im Formular, beim
Einpflegen eines Kaufs und bei Mengenmaterial (Anschaffung je Stück).

**Die Karte „Anlagevermögen“** steht auf der Seite eines Exemplars – für alle,
die Einkaufs- und Kaufpreise sehen und das Material lesen dürfen; ändern darf
sie, wer das Material bearbeiten darf. Sie zeigt die **Art des
Wirtschaftsguts**, bei einem Anlagegut die **Nutzungsdauer**, das
**Kaufdatum**, die **Anschaffungskosten (netto)**, die **Abschreibung bisher**
bis heute, den **Restbuchwert** heute und darunter die **Abschreibung je Jahr**
(Monate, Abschreibung, bisher, Restbuchwert am 31. Dezember).

Die Art ist eine von dreien:

- **Handelsware** – wird nicht abgeschrieben, bleibt mit den Anschaffungskosten
  stehen.
- **Geringwertiges Wirtschaftsgut (GWG)** – bis zu einer Grenze (voreingestellt
  800 € netto je Stück, einschließlich) im Jahr des Kaufs ganz abgeschrieben:
  Am 31. Dezember dieses Jahres ist der Restbuchwert 0.
- **Anlagegut** – wird über die **Nutzungsdauer** (voreingestellt 60 Monate)
  gleichmäßig abgeschrieben.

Die Anschaffungskosten sind der Einkaufspreis netto plus die **Nebenkosten**
(Fracht, Verpackung, Zoll), die zu dem Stück gehören. Bei Material, das du über
eine Eingangsrechnung einpflegst (Abschnitt 11), setzt Rentalars Art,
Nutzungsdauer und Kosten selbst. **Ältere Exemplare** trägst du von Hand ein:
Auf der Karte steht dann **„Als Anlage erfassen“** (später **„Anlagedaten
ändern“**) mit **„Art des Wirtschaftsguts“**, **„Nutzungsdauer (Monate)“**,
**„Anschaffungsnebenkosten (netto)“** und **„Anschaffungskosten (netto)“**
(leer: aus dem Einkaufspreis errechnet) und **„Anlagedaten speichern“**. Wählst
du bei der Art „nicht als Anlage erfasst“, nimmt Rentalars das Exemplar wieder
aus den Büchern.

**Die Regeln im Einzelnen.**

- Linear nach **Monaten**; der **Kaufmonat zählt voll**. Kennst du nur das
  Jahr, rechnet Rentalars ab Januar (oben, „Kaufdatum, wenn du nur das Jahr
  kennst“) und sagt es auf der Karte.
- Die bisher abgeschriebene Summe ist auf Cent gerundet, der **letzte Monat
  gleicht aus**: Am Ende stimmt die Summe genau.
- Ein **Kaufdatum in der Zukunft** heißt „noch nicht angeschafft“; das Stück
  steht dann in keiner Summe.
- Fehlen **Kosten, Kaufdatum oder Nutzungsdauer**, gibt es keinen Restbuchwert; die
  Karte sagt, was fehlt („keine Anschaffungskosten“, „kein Kaufdatum“, „keine
  Nutzungsdauer“).
- Auf Wunsch bleibt ein voll abgeschriebenes Anlagegut mit **1 €** stehen
  (**Erinnerungswert**), bis es verkauft oder ausgemustert wird. Das schaltest du in
  Einstellungen → Eingangsrechnungen ein (Abschnitt 11, „Einstellungen für
  Eingangsrechnungen“); voreingestellt ist es aus.
- Mengenmaterial hat eine Zeile mit den Kosten **der ganzen Zeile**.

**Nicht gebaut:** degressive Abschreibung, Sonderabschreibung,
Halbjahresregel und ein GWG-Sammelposten. Die Grenze für ein GWG und die
Nutzungsdauer sind Einstellungen, keine Steuerregeln, die Rentalars für euch
nachschlägt (Abschnitt 17).

### Der Anlagenspiegel

**Buchhaltung → Anlagenspiegel** (für alle, die Einkaufspreise sehen und
das Material lesen dürfen) listet die Exemplare mit ihren
**Anschaffungskosten**, der **Abschreibung** und dem **Restbuchwert** – zu
einem **Tag** („Oder an diesem Tag“) oder zum **Bilanzstichtag** („Bilanzjahr
(31. Dezember)“, gewählt aus den Jahren der Käufe), vorgewählt heute. Wie jede
Tabelle (Abschnitt 2, „Listen“) lässt sie sich sortieren, filtern, gruppieren
und als CSV laden.

- Gefiltert wird nach **Art des Wirtschaftsguts** (vorgewählt „Anlagegüter und
  GWG“; auch „Ware“ oder „Nicht als Anlage erfasst“ oder alles), **Lagerort**,
  **Modell** und einem Suchwort (ID, Modell, Seriennummer, Notiz). Mit
  **„Auch Artikel, die den Bestand verlassen haben“** stehen auch verkaufte
  und ausgemusterte darin.
- Unter der Tabelle stehen die **Summen** je Art und insgesamt – über alles, was
  der Filter ergibt, nicht nur über die Seite –: Stück, Anschaffungskosten,
  Abschreibung bisher, Abschreibung im Jahr, Restbuchwert. Darunter sagt
  Rentalars, wie viele Stücke **keinen Restbuchwert** haben (es fehlen Kosten,
  Datum oder Nutzungsdauer), wie viele erst **nach dem Tag** gekauft wurden und
  wie viele bis dahin schon **den Bestand verlassen** hatten – sie stehen in
  keiner Summe.
- Es gibt **keinen DATEV-Export** des Anlagenspiegels; die CSV-Datei ist
  für die Steuerberatung zum Weiterverarbeiten gedacht.

### Gebrauchtverkauf aus dem Bestand

Ein Gerät, das ihr nach Jahren verkauft – an einen Kunden oder jemanden, der
keiner ist –, geht nicht über ein Projekt hinaus, sondern **aus dem Bestand**.
Auf der Seite des Exemplars steht in der Karte „Anlagevermögen“ der Knopf
**„Gebrauchtverkauf aus Bestand“** (für alle, die Einkaufspreise sehen und das
Material bearbeiten dürfen):

1. **Der Verkauf.** Wähle den **Kunden** der Stammdaten – oder tippe den **Namen
   des Käufers** –, den **Tag des Verkaufs**, den **Preis (netto)**, die
   **Steuerart** und auf Wunsch eine Notiz. Bei Mengenmaterial gibst du auch
   die **Menge** an: Verkauft wird dann ein Teil der Zeile.
2. **„Vorschau zeigen“.** Rentalars zeigt Preis netto, Steuer und brutto, die
   Anschaffungskosten, die Abschreibung bis zum Tag, den **Restbuchwert** an
   diesem Tag und den **Gewinn oder Verlust** (Preis netto minus Restbuchwert).
   War das Exemplar nicht mit Kosten und Datum als Anlage erfasst, sagt die
   Vorschau, dass sein Restbuchwert mit **0 €** angesetzt wird – der ganze Preis
   ist dann Gewinn. Ein GWG, das vor dem 31. Dezember verkauft wird, verlässt die
   Bücher mit seinen Kosten.
3. **„Verkaufen“** – nach einer Rückfrage („Diesen Artikel jetzt verkaufen? Er
   verlässt den Bestand.“). Das Exemplar bekommt den Status **„verkauft“** (so
   wie ein ausgemustertes, Abschnitt 4, „Der Zustand eines Exemplars“); im
   Verlauf steht der Verkauf ohne Beträge, weil den Verlauf alle lesen, die
   das Material lesen.

**Wann es nicht geht.** Rentalars verweigert den Verkauf, wenn das Exemplar
schon aus dem Bestand ist (verkauft, verloren), im Einsatz ist, in einem
anderen Exemplar **verbaut** ist oder selbst andere Exemplare oder
Mengenmaterial enthält, für ein Projekt **gewählt, gepackt oder unterwegs** ist,
der Tag in der Zukunft oder vor dem Kauf liegt, der Preis fehlt oder der Käufer
fehlt. Nur **fragen** muss Rentalars, wenn ein offenes Projekt das Exemplar in
der Planung **wünscht** oder noch **Sperrzeiten** laufen – dann musst du
„Trotzdem verkaufen“ bestätigen.

**Storno.** Ein Verkauf lässt sich **stornieren**, solange das Exemplar noch
„verkauft“ ist: auf der Seite des Verkaufs **„Verkauf stornieren“** mit einem
**Grund**. Das Exemplar bekommt den Status zurück, den es vorher hatte; bei
Mengenmaterial gehen die Stücke mit ihren Kosten zurück in die Zeile. Der
Verkauf bleibt als **storniert** in der Liste stehen.

**Buchhaltung → Verkäufe aus Bestand** listet alle Verkäufe mit Käufer,
Preis, Restbuchwert und Gewinn oder Verlust – filterbar nach Jahr, Zeitraum,
Suchwort und „Auch stornierte Verkäufe“ – und darunter **„Gewinn und Verlust je
Jahr“**. Auf der Seite eines Verkaufs erzeugt **„Rechnung dazu erstellen“** den
Entwurf eines freien Ausgangsbelegs (Abschnitt 11, „Ausgangsbelege ohne
Projekt“) – nur, wenn der Käufer ein Kunde der Stammdaten ist. Der Beleg ist
mit dem Verkauf **verknüpft**: Ein zweiter Klick liefert denselben
Entwurf, solange er offen ist; ist die Rechnung erstellt, steht ihre Nummer
am Verkauf, und eine zweite Rechnung für denselben Verkauf lehnt Rentalars ab,
bis du die erste storniert hast. Einen Verkauf mit gültiger Rechnung kannst du
nicht rückgängig machen – storniere erst die Rechnung (Buchhaltung →
Ausgangsbelege). Wer einen Kunden
anonymisiert (Abschnitt 6), nimmt seinen Namen auch aus den Verkäufen, dem
Änderungsprotokoll und dem Verlauf der Exemplare.

Für Verkäufe aus dem Bestand gibt es **keinen DATEV-Export**.

### Fuhrpark

Ihr führt eure Fahrzeuge (KFZ) und Anhänger in der
Materialverwaltung, im Reiter **„Fuhrpark“**. Ein Fahrzeug ist ein
**Exemplar** – mit ID, Status, Prüfungen, Dateien, Defektmeldungen, Etikett
und Verlauf wie jedes andere – eines Modells, dessen Produkt die Produktart
**„Fahrzeug“** hat (Abschnitt 5, „Produktarten“). Das Produkt trägt die
Sätze, nach denen abgerechnet wird; das Modell sagt, was für ein Fahrzeug
es ist. Geplant werden Fahrzeuge nicht als Material, sondern im Block
„Logistik“ eines Projekts (Abschnitt 7, „Logistik“); sie zählen nicht zur
Verfügbarkeit des Materials und werden nicht gepackt.

**Ein Fahrzeug anlegen:**

1. Ein **Produkt** der Art „Fahrzeug“ anlegen – am einfachsten in der
   Kategorie FZ „Fuhrpark“, die die Art vorgibt –, als KFZ oder Anhänger,
   mit seinen Sätzen (Abschnitt 5, „Produktarten“).
2. Ein **Materialmodell** zu diesem Produkt anlegen und je Fahrzeug ein
   **Exemplar** (oben, „Neues Material anlegen“).
3. Auf der Seite jedes Exemplars im Kasten **„Fahrzeugdaten“** auf
   **„Fahrzeugdaten bearbeiten“**: **„Kennzeichen“** (jedes nur einmal),
   beim KFZ **„Sitzplätze min.“** und **„Sitzplätze max.“** – Pflicht; bei
   herausnehmbaren Sitzen verschieden, bei fester Zahl beide gleich –,
   **„Führerscheinklasse“** (beim Anhänger die des Gespanns, etwa BE), beim
   KFZ **„Anhängelast (kg)“** (0: darf nicht ziehen) und bei beiden
   **„Zulässiges Gesamtgewicht (kg)“**. Das darf, wer Material bearbeiten
   darf.

Unter den Fahrzeugdaten stehen die **„Buchungen“** des Fahrzeugs jetzt und
in den nächsten zwölf Monaten, mit „jetzt“ und „überschneidet sich mit
einer anderen Buchung“. Projekte, die du nicht öffnen darfst, stehen nur
mit ihrer Nummer da.

**Der Reiter „Fuhrpark“** listet die Fahrzeuge und Anhänger mit
Kennzeichen, Art (KFZ oder Anhänger), Modell, Produkt, Sitzplätzen
(„Sitzplätze fehlen“, wenn sie bei einem KFZ nicht eingetragen sind),
Führerscheinklasse, Status, nächster Prüfung (überfällig in Rot) und der
laufenden oder nächsten Buchung („überschneidende Buchungen“). Anhängelast,
Gesamtgewicht, Seriennummer und Rechnungsdatum blendest du über „Spalten“
ein. Filtern lässt sich nach Kennzeichen, Modell oder Seriennummer, nach Art
und Status („Alle genutzten“ lässt Ausgemustertes weg).

**„Auslastung des Fuhrparks“** oben auf der Seite zeigt je Fahrzeug seine
Buchungen über alle Projekte als Zeitstrahl, in den Farben des
Personalplans (fest, Option, Anfrage), Sperrzeiten als eigene Balken. Ist
ein Fahrzeug zur selben Zeit doppelt gebucht – in einem Projekt oder in
mehreren –, sind die Buchungen rot gefüllt, und vor dem Namen steht „!“.
Bedient wird er wie die Materialauslastung (Abschnitt 15).

**Fristen.** Hauptuntersuchung (HU), Prüfung nach DGUV/UVV oder Inspektion
legst du als Prüfarten für die Kategorie FZ oder die Modelle an (oben,
„Prüfungen“). Was überfällig oder vor dem Ende einer Buchung fällig ist,
nennt auch die Logistik des Projekts.

**Fahrzeuge, die bisher als Material geführt sind.** Habt ihr den Sprinter
bisher als Mietprodukt geplant, steht auf der Seite seines Modells **„In
den Fuhrpark übernehmen“** (für alle, die Material und Produkte bearbeiten
dürfen) – nur, wenn die Kategorie des Modells oder eine
übergeordnete die Produktart **„Fahrzeug“** vorgibt, wie FZ „Fuhrpark“
(Abschnitt 16, „Stammdaten“). Bei einem Kabel oder Scheinwerfer steht der
Knopf also nicht mehr; steht der Sprinter noch in einer anderen Kategorie,
gib seinem Modell zuerst eine solche. Dialog und Schnittstelle lehnen
andere Modelle ab („Nur Modelle einer Fahrzeug-Kategorie (Produktart
„Fahrzeug“) kommen in den Fuhrpark.“). Der Dialog fragt nach der
Fahrzeugart, mit Preisrecht nach den
Sätzen, mit dem Recht für Einkaufspreise nach den internen Kosten.
Rentalars legt ein neues Fahrzeugprodukt an – nächste freie Nummer der
Kategorie, Name, Einheit, Steuerart und Höchstrabatt vom bisherigen
Produkt; der Tagespreis eines Anhängers ist zunächst dessen Preis – und
ordnet ihm das Modell zu. Das bisherige Produkt und alle Positionen
bleiben, wie sie sind; kein Preis und keine Summe ändert sich. Aber das
bisherige Produkt hat die Exemplare nicht mehr: Offene Projekte, die es noch
als Material planen, nennt die Seite danach („Diese offenen Projekte planen
… noch als Material: …“). Buche dort die Fahrzeuge unter „Logistik“ und
entferne die Materialpositionen – bis dahin zeigen sie eine Fehlmenge.
Kundenmaterial, Mengenmaterial und Material anderer Produktarten lassen
sich nicht übernehmen.

### Die Excel-Liste übernehmen

„Materialverwaltung → Import“ führt in drei Schritten durch: Datei wählen, Spalten
zuordnen, Probelauf – und erst wenn der Probelauf fehlerfrei ist,
importieren. Probelauf und Import laufen im Hintergrund; die Seite zeigt
den Fortschritt, und du kannst währenddessen weiterarbeiten. Im Browser gibt es
keine Grenze für die Zahl der Zeilen. Wie der Import
allgemein funktioniert, steht in Abschnitt 16, „Import und Export“; alles
Weitere zu den Spalten der Materialliste und zum wiederholten Import in der
Anleitung [Übernahme der Materialliste](../betrieb/import.md).

Der Probelauf zeigt **jede Zeile der Datei** mit ihrem
Ergebnis – neu, geändert (je Feld „bisher“ und „neu“), unverändert oder
Fehler –, beim Material auch Änderungen am Modell („Beschreibung
(Materialmodell)“) und Hinweise wie „neues Materialmodell …“ oder „neuer
Händler …“ (Abschnitt 16, „Import und Export“). Haben Zellen der Datei
Fehler, stehen zunächst nur die Zeilen mit Fehlern da; die übrigen prüft
der nächste Probelauf. Wer Einkaufs- und Kaufpreise nicht sehen darf, sieht
deren Werte als „nicht sichtbar“ – übernommen werden die Kaufpreise der
Datei trotzdem, und der Bericht sagt es.

Außerdem gilt:

- **Netto oder brutto.** Rentalars führt Kaufpreise netto. Im Schritt
  „Spalten zuordnen“ fragt der Import deshalb **„Die Kaufpreise der Datei
  sind“** „netto – werden so übernommen“ oder „brutto – die Steuer wird
  herausgerechnet“, und für Bruttopreise **„Bruttopreise enthalten“** – den
  Steuersatz, vorgewählt der Standardsteuersatz. Ein Bruttopreis wird
  durch 1 plus den Satz geteilt und netto gespeichert: 119,00 € mit 19 %
  werden 100,00 €. Der Bericht nennt es („als brutto mit 19 % Steuer
  gelesen und netto gespeichert“).
- **IDs mit „#“.** Eine Zelle wie `#0802` liest der Import als die ID
  `0802` – in der Spalte der ID, in „Einsatz/Verbindung“ und in der
  Spalte des Kaufpreises.
- **Mehrere IDs oder Text in „Einsatz/Verbindung“.** Ein Exemplar steckt in
  höchstens einem anderen. Steht in der Zelle genau eine ID, ist das die
  Verbindung. Stehen mehrere darin (`#0123, #1234`) oder Text (`Rack`),
  macht der Import **keine** Verbindung und meldet es auch nicht als
  Fehler: der Text steht danach in der Notiz des Exemplars
  („Einsatz/Verbindung: …“), und die Vorschau und der Bericht nennen die
  Zeile als Hinweis. Die Verbindung legst du am Exemplar an.
- **Als Set gekauft.** Steht in der Zelle des Kaufpreises `#0851`, heißt
  das: als Set gekauft, der Preis steht bei 0851 (oben, „Neues Material
  anlegen“). Das Exemplar bekommt keinen eigenen Preis und wird mit 0851
  verbunden. 0851 muss in der Datei oder schon in Rentalars sein; nennt
  0851 selbst wieder ein anderes Exemplar, gilt das am Ende der Kette,
  und eine Kette im Kreis ist ein Fehler. Hat das Exemplar mit dem Preis
  keinen Kaufpreis, gibt der Probelauf einen Hinweis. Der Bericht listet
  die zusammen gekauften Sets, das Exemplar mit dem Preis zuerst.

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
  Spalte „– nicht importieren –“ zu und ein Exemplar hat noch eine Menge aus
  früherer Zeit (es war Mengenmaterial), gibt es keine Meldung
  „Einzelexemplare haben immer die Menge 1“: Die Menge wird auf 1 gesetzt, der
  alte Wert steht in der Notiz, und der Bericht nennt es als Hinweis.

Beim Import auf dem Server mit `rentalars import_material` sagen
`--gross` und `--tax-rate 19` dasselbe (Anleitung „Übernahme der
Materialliste“).

Zusätzlich gilt:

- **Eigene Felder.** Eine Spalte, deren Überschrift der Name eines eigenen
  Feldes ist (oben, „Eigene Felder“), füllt dieses Feld – ohne Zuordnung;
  welche Namen das sind, steht beim Import unter „Welche Spalten werden
  erkannt?“.
  Jeder Wert wird wie im Formular gegen den Feldsatz des Modells geprüft;
  ein Feld, das der Feldsatz nicht hat, ein unpassender Wert oder ein
  eindeutiger Wert, den schon ein anderes Exemplar hat, ist ein Fehler
  dieser Zeile. Eine leere Zelle leert den Wert. Pflichtfelder verlangt
  der Import nicht – wie beim Anlegen mehrerer Exemplare. Die Spalte
  eines vertraulichen Feldes übergeht er mit einem Hinweis, wenn du
  Einkaufspreise nicht sehen darfst.
- **Lagerort als Pfad.** `Halle 1 > Regal A` meint das Regal A in Halle 1
  – wichtig, wenn zwei Regale gleich heißen.
- **Hin und zurück.** Was der Export im Importformat schreibt, liest der
  Import unverändert wieder ein; ein Apostroph, den der Export vor Text
  wie „=Summe“ oder „- defekt“ setzt, nimmt der Import wieder weg
  (Abschnitt 16, „Import und Export“).

Die **Schutzklasse** (oben, „Schutzklasse“): Die Spalte
**„Schutzklasse“** (auch „Schutzkl.“ oder „SK“) nennt die Klasse des
Exemplars als `I`, `II` oder `III`; der Import nimmt auch `1`, `2`, `3`
und Schreibweisen wie „SK II“ oder „Schutzklasse 2“, alles andere ist ein
Fehler der Zeile („„IV“ ist keine Schutzklasse. Schreib I, II oder
III.“). Ein Modell **ohne** Schutzklasse bekommt die Klasse, die alle
seine Zeilen der Datei nennen – nur, wenn sie sich einig sind und kein
Exemplar eine eigene hat; sonst bekommt jedes Exemplar, dessen Zeile von
seinem Modell abweicht, eine eigene. Dieselbe Klasse wie das Modell oder
eine leere Zelle heißt „wie das Modell“ und nimmt einem Exemplar seine
eigene. Die Schutzklasse eines Modells, das schon eine hat, ändert der
Import nie – das geht auf seiner Seite. Der Export im Importformat
schreibt in die Spalte die Klasse, die für das Exemplar gilt.

---

## 5. Produkte

Ein Produkt ist, was in Projekten erscheint. Es hat eine Artikelnummer,
einen Namen, eine Einheit, einen Preis und eine Steuerart.

### Produktarten

| Art | Wofür | Bestand |
|---|---|---|
| **Mietprodukt** | kommt nach dem Projekt zurück | aus dem zugeordneten Material |
| **Verkaufs- oder Verbrauchsprodukt** | bleibt beim Kunden oder wird verbraucht | aus dem zugeordneten Material; verlässt ihn bei der Ausgabe für immer |
| **Dienstleistung** | der Preis einer Funktion des Personals – Tontechniker, Stagehand, Projektplanung; wird nur unter Personal geplant | keiner – wird nicht auf Verfügbarkeit geprüft |
| **Nebenkosten** | Transport, Fahrtkosten, Gebühren – wie Material geplant, voreingestellt pauschal | keiner; steht nicht auf der Packliste |
| **Set** | ein Paket aus anderen Produkten | ergibt sich aus seinen Bestandteilen |
| **Aufpreis** | fester Betrag oder Prozentsatz | keiner |
| **Zumietung** | Material von einem Lieferanten | keiner |
| **Fahrzeug** | ein KFZ oder Anhänger des Fuhrparks, nach Kilometern bzw. Tagen abgerechnet; wird nur unter Logistik geplant | seine Fahrzeuge sind die Exemplare des zugeordneten Materials; sie zählen nicht zur Verfügbarkeit des Materials |

**Dienstleistungen gehören zu Funktionen.** Jedes Dienstleistungsprodukt
gehört zu genau einer Funktion des Personals und jede Funktion zu genau
einem Dienstleistungsprodukt, beide mit demselben Namen. Legst du ein
Produkt der Art „Dienstleistung“ an, entsteht beim Speichern die Funktion
dazu; legst du eine Funktion an, entsteht ihr Produkt (Abschnitt 12,
„Funktionen“). Einen Namen, den schon eine Funktion trägt, nimmt Rentalars
für eine neue Dienstleistung nicht an. Benennst du eines um, folgt das
andere, solange beide gleich hießen. Das Produkt einer Funktion behält
seine Art und lässt sich nicht für sich löschen; du löschst die Funktion,
und das Produkt geht mit. Geplant werden Dienstleistungen nur über das
Personal eines Projekts, nicht als Material und nicht in Sets (Abschnitt 7,
„Eine Position hinzufügen“).

**Nebenkosten** sind, was weder Material noch Personal ist: der Transport
mit dem Sprinter, Fahrtkosten, Gebühren. Sie haben keinen Bestand, stehen
nicht auf der Packliste, werden voreingestellt pauschal abgerechnet und im
Projekt hinzugefügt wie Material. Die Installation bringt dafür die
Kategorie N „Nebenkosten“ mit. Eure **eigenen Fahrzeuge** plant
ihr mit der Produktart „Fahrzeug“ unter
Logistik (unten).

**Fahrzeuge** sind die Produkte des Fuhrparks (Abschnitt 4,
„Fuhrpark“). Wählst du die Art **„Fahrzeug“** – in der Kategorie FZ
„Fuhrpark“ ist sie vorgegeben –, fragt das Formular:

- **„Fahrzeugart“** – KFZ oder Anhänger;
- beim KFZ **„Preis je Kilometer (netto)“** (Pflicht) und
  **„Anhängerzuschlag je Kilometer (netto)“** – er kommt auf jeder Fahrt
  hinzu, auf der das KFZ einen Anhänger zieht;
- beim Anhänger **„Anhänger abrechnen“** „je Tag“ oder „nach Kilometern“ –
  so beginnt eine neue Buchung, im Projekt umschaltbar – und dazu den
  **„Preis (netto)“** je Tag (mit Staffel, wie Material) oder den **„Preis
  je Kilometer (netto)“**;
- mit dem Recht für Einkaufspreise **„Interne Kosten je Kilometer“** –
  Kraftstoff, Verschleiß, Versicherung – und beim Anhänger mit Tagesmiete
  **„Interne Kosten je Tag“**.

Die Sätze sehen und ändern nur, wer Preise sehen darf, die Kosten nur, wer
Einkaufspreise sehen darf. Eine Abrechnungsart hat ein Fahrzeug nicht. Die
Seite des Produkts zeigt Fahrzeugart, Sätze und Kosten und unter
**„Fahrzeuge“** seine Modelle und Exemplare. Ein Fahrzeug, das in Projekten
gebucht ist, bleibt ein Fahrzeug seiner Art. In ein Set kommt es nicht.

### Ein Produkt anlegen

**Materialverwaltung → Produkte → Neues Produkt.** Wähle zuerst die
**Produktart**, dann die **Kategorie**: Die Kategorien, die diese Art
vorgeben, stehen oben in der Liste („Kategorien für „Mietprodukt““), die
übrigen darunter („Weitere Kategorien“). Die Kategorie schlägt die nächste
freie Artikelnummer vor und füllt sinnvolle Voreinstellungen ein (Einheit,
Abrechnungsart); die gewählte Art bleibt dabei. Wählst du bei einem neuen
Produkt Art oder Kategorie, lädt das Formular neu – trag Name und Preis
also danach ein.

**Die Artikelnummer** beginnt mit dem Kürzel der Hauptkategorie, dann folgt
eine Nummer: `K-005`, `T-100`. Du kannst die vorgeschlagene Nummer ändern,
solange sie zum Kürzel passt und noch frei ist. Ist ein Produkt schon in
Projekten verwendet, braucht das Ändern seiner Artikelnummer ein eigenes
Recht. Wählst du im Formular eines **bestehenden** Produkts eine andere
Kategorie – etwa nach „Als Produkt anlegen“ (Abschnitt 4), wenn das Modell
in der falschen Hauptkategorie landete –, schlägt Rentalars
gleich die nächste freie Artikelnummer der neuen Kategorie vor; die
übrigen Eingaben bleiben stehen.

**Ein Produkt, ein Preis.** **Preis (netto)** ist bei Mietprodukten der
Preis **pro Tag**. Jedes Produkt hat genau einen Preis: ein
Verkaufsprodukt seinen **Verkaufspreis**, jedes andere Produkt seinen
**Preis** – das Feld „Verkaufspreis“ zeigt das Formular nur bei der Art
„Verkauf“, und die Produktliste zeigt ihn in einer Spalte „Preis“. Was
ihr verkauft, ist also ein Verkaufsprodukt; soll ein
Mietartikel auch verkauft werden, legst du dafür ein eigenes
Verkaufsprodukt an. Positionen, die ein Mietprodukt schon verkauft
haben, behalten ihren Preis (Abschnitt 7, „Eine Position bearbeiten“).
Welche Felder für die gewählte Produktart Pflicht sind – der Preis bei
allen Arten außer Verkauf und Dienstleistung, der Verkaufspreis bei
Verkaufsprodukten –, zeigt ihr Sternchen (Abschnitt 2, „Pflichtfelder“).

**Duplizieren**. Auf der Seite eines Produkts öffnet
**„Duplizieren“** das Formular eines neuen Produkts, ausgefüllt mit den
Angaben des Originals und der nächsten freien Artikelnummer seiner
Kategorie – Preise nur mit dem Recht „Preise und Kalkulation sehen“,
interne Kosten nur mit dem Recht für Einkaufspreise. Nicht übernommen
werden GTIN, zugeordnetes Material und „deaktiviert“. Gespeichert wird
erst mit **„Produkt speichern“**; ein Set bringt dann seine Bestandteile
mit – das Formular nennt sie unter „Bestandteile des Sets“. Den Knopf hat,
wer Produkte bearbeiten darf.

Eine **Dienstleistung** hat unter dem Preis außerdem **„Grenze in Stunden
pro Tag“** und **„Preis je Stunde ab der Grenze (netto)“** – für einen
höheren Stundenpreis ab einer Zahl von Stunden am Tag (Abschnitt 12, „Was
Personal kostet und einbringt“) – und den Haken **„Zuschläge für Nacht,
Sonn- und Feiertage“** (gesetzt): Nimmst du ihn heraus, bekommen
Personalpositionen dieser Dienstleistung keine Zuschläge, weder im Preis
noch in den Kosten – etwa für eine Nachtwache, deren Preis die Nacht schon
enthält. Die Seite des Produkts zeigt es unter „Zuschläge“. Andere
Produktarten haben diesen Haken nicht: Zuschläge bekommen nur
Personalpositionen. Abgerechnet
wird eine Dienstleistung voreingestellt nach Stunden.

**Höchster Rabatt.** Wie an einer Funktion legst du auch an einem Produkt
einen **„höchsten Rabatt in Prozent“** fest: leer heißt keine Grenze, 0
heißt nicht rabattierbar. Er begrenzt jede Position dieses Produkts – ihren
eigenen Rabatt, den Standardrabatt des Kunden und ihren Anteil am Rabatt
oder Pauschalpreis der Teilgruppe. Gelten Produkt und Funktion, zählt die
strengere Grenze. Die Produktseite zeigt den Wert unter „Höchstrabatt“
(„5 %“, „nicht rabattierbar“ oder „keine Grenze“); in der Produktliste
blendest du die Spalte „Höchstrabatt“ über „Spalten“ ein – sie geht mit in
den Export und wird beim Import wieder eingelesen. Feld und Spalte sehen
und ändern nur, wer Preise sehen darf.

Viele Produkte auf einmal anlegen oder ändern – neue Preise für den ganzen
Katalog etwa – geht mit dem Import der Produkte unter Einstellungen →
Import und Export oder Materialverwaltung → Import, Reiter „Produkte“: Liste
als CSV herunterladen, in der Tabellenkalkulation ändern, wieder einlesen
(Abschnitt 16, „Import und Export“). Über der
Produktliste steht „Kauf
einpflegen“ (Abschnitt 4).

### Abrechnungsarten

| Abrechnungsart | So entsteht der Betrag |
|---|---|
| Tagesmiete je Stück | Menge × Tagespreis × Faktor der Miettage |
| Tagesmiete je Set | wie oben; die Menge ist die Zahl der Sets |
| pauschal | Menge × Preis – unabhängig von der Dauer |
| nach Stunden | Menge × Stunden × Preis |
| nach Aufwand | Menge × Preis; die Menge wird zunächst geschätzt und später durch den tatsächlichen Aufwand ersetzt |

### Staffeln

Wer länger mietet, zahlt pro Tag weniger. Die Staffel macht aus der Zahl
der Miettage einen Faktor auf den Tagespreis. Mitgeliefert ist die
**„Standardstaffel“**:

| Miettage | 1 | 2 | 3 | 4 | 5 | 6 | 7 | jeder weitere |
|---|---|---|---|---|---|---|---|---|
| Faktor | 1,0 | 1,5 | 1,75 | 2,0 | 2,4 | 2,75 | 3,5 | + 0,3 |

Ein Scheinwerfer zu 20 € pro Tag kostet für zwei Miettage also
20 € × 1,5 = 30 €, für acht Miettage 20 € × 3,8 = 76 €.

Eine vorhandene „Standardstaffel“ rechnet weiter
mit 1 / 1,5 / 2 / 2,5 und + 0,5. Willst du die neuen Faktoren, trägst du
sie unter Einstellungen → Staffeln ein (Abschnitt 16, „Stammdaten“).

Unter **Einstellungen → Staffeln** änderst du die Tabelle oder legst
weitere an (dafür braucht es das Recht „Staffeln bearbeiten“). Welche
Staffel gilt:

- die der **Kategorie** des Produkts, wenn dort eine eingetragen ist,
- sonst die **Standardstaffel**,
- es sei denn, das Produkt nennt eine **eigene Staffel** oder **keine
  Staffel** (dann zählt jeder Tag voll).

**Geänderte Staffeln und bestehende Projekte.** Eine Position merkt sich den
Stand der Staffel, mit dem sie kalkuliert wurde. Änderst du die Tabelle,
bleiben bestehende Projekte bei ihren Preisen. Die Planungsseite weist
darauf hin und bietet an, „Auf die aktuelle Staffel um[zu]stellen“; danach
zeigt sie gleich wieder die ganze Planung. Für geänderte Produktpreise
gibt es einen ähnlichen Hinweis (Abschnitt 8, „Geänderte Produkte“).

### Sets

Ein Set bündelt Produkte, die zusammen rausgehen: das „Aktivbox-Set“ aus
einer Box, einem Stativ und einem Kabel. Lege ein Produkt der Art **Set**
an und füge auf seiner Seite unter **„Bestandteile des Sets“** die Produkte
mit ihrer Menge hinzu.

- Ein Set hat **einen Preis** – unabhängig von den Preisen der Teile.
- Die Bestandteile **bleiben einzeln vermietbar**.
- Die **Verfügbarkeit** eines Sets ergibt sich aus dem knappsten
  Bestandteil: Vier Boxen, aber nur drei Stative frei – drei Sets.
- Auf der **Packliste** erscheinen die Bestandteile, nicht das Set: Gepackt
  werden Boxen, Stative und Kabel.

### Verbrauchsmaterial und Mindestbestand

Gaffa-Tape, Batterien, Fluid für die Nebelmaschine: Was verkauft oder
verbraucht wird, ist ein **Verkaufs- oder Verbrauchsprodukt**, meist in
der Kategorie Verkauf (V). Bei der **Ausgabe** verlässt es den Bestand für
immer – es kommt nicht zurück und steht auf der Packliste deshalb nicht zum
Zurücknehmen.

Damit nichts ausgeht, trägst du am Produkt einen **Mindestbestand** ein.
Fällt der Bestand darunter – nach einer Ausgabe oder bei der täglichen
Prüfung –, bekommt das Lager eine Benachrichtigung („Unter dem
Mindestbestand: V-010 Gaffa-Tape schwarz“, mit Bestand und Mindestbestand),
einmal, bis wieder genug da ist. Die Seite des Produkts zeigt dann „unter
dem Mindestbestand“, und der Haken **„Unter dem Mindestbestand“** in der
Produktliste zeigt alles, was nachbestellt werden sollte. Leer gelassen
gibt es keine Warnung.

### Bestand und Verfügbarkeit eines Produkts

Die Seite eines Produkts hat zwei Reiter. **Produkt** zeigt

- unter **Verfügbarkeit**: für einen Zeitraum deiner Wahl, wie viel
  vorhanden, fest reserviert, optional reserviert und frei ist – und welche
  Projekte es belegen. Die Zahlen folgen dem Zeitraum sofort,
  sobald du ihn in den Feldern oder im Kalender änderst; „Zeitraum prüfen“
  gibt es nur noch ohne JavaScript. **„In der Materialauslastung zeigen“**
  darunter öffnet Planung → Materialauslastung mit genau diesem Produkt und
  Zeitraum – bis zehn Tage in Stunden, längere in Wochen (Abschnitt 15,
  „Materialauslastung“). Den Kasten und den Reiter „Zeitstrahl“ sieht nur,
  wer das Sonderrecht „Verfügbarkeit von Material sehen“ hat;
- unter **Zugeordnetes Material**: die Exemplare, aus denen sich der
  Bestand ergibt. Mit „Neues Materialmodell“ legst du ein Modell für das
  Produkt an; ein vorhandenes Modell ohne Produkt suchst du im Feld „Modell
  ohne Produkt suchen“ und übernimmst es mit **„Vorhandenes Modell
  zuordnen“** (dafür braucht es das Recht, Material zu bearbeiten). Das Feld schlägt schon beim Hineinklicken die ersten Modelle ohne
  Produkt vor, und es sucht **Wort für Wort** in Name, Kurzname, Hersteller
  und Kategorie – „Martin MAC“ findet „MAC Aura“ von Martin, auch wenn
  die Wörter in verschiedenen Feldern stehen. Modelle, die zu einem
  anderen Produkt gehören, stehen am Ende grau und lassen sich nicht wählen
  („gehört schon zu K-005“; umhängen geht auf der Seite des Modells); findet
  das Feld nichts, sagt es „Kein Modell gefunden. Zugeordnet werden können nur
  Modelle ohne Produkt.“ Gehört
  das Modell zu einer anderen Hauptkategorie, weist Rentalars darauf hin
  (Abschnitt 4, „Material einem Produkt zuordnen“). Material haben nur
  Miet- und Verkaufsprodukte und Fahrzeuge – bei ihnen heißt der
  Kasten „Fahrzeuge“, und ihre Buchungen zeigt statt der Verfügbarkeit die
  Auslastung des Fuhrparks (Abschnitt 4, „Fuhrpark“);
- den Kasten **„Kalender-Link“**: die Buchungen des Produkts
  als Kalender zum Abonnieren (Abschnitt 4, „Kalender-Link“).

**Zeitstrahl** zeigt dasselbe über Wochen: oben je Tag, wie viele Stück
frei sind (klein daneben, was Optionen zusätzlich nehmen würden), darunter
je Projekt ein Balken – fest reserviert oder als Option, auch wenn das
Produkt in einem Set oder Case steckt. So siehst du auf einen Blick, wann
es eng wird und wann etwas frei ist. Bedient wird er wie am Exemplar
(Abschnitt 4, „Zeitstrahl“).

In der Produktliste bedeutet „2 / 6 Stk.“: sechs vorhanden, zwei davon
einzeln planbar (der Rest ist fest verbaut, defekt oder gesperrt).

### Zubehör und Ersatz

Zu einem Lautsprecher gehört ein Kabel, zu einem Scheinwerfer ein Stativ;
und ist der eine Scheinwerfer gerade ausgebucht, würde ein ähnlicher auch
gehen. Das hältst du **am Produkt** fest – denn mit Produkten
wird geplant, gleich welche Modelle dahinterstehen (Abschnitt 1) –, und die
Planung erinnert daran. Es sind **Vorschläge**: Sie halten nie etwas auf und
ändern nie etwas von selbst.

**Eintragen.** Auf der Seite eines Produkts steht der Kasten **„Zubehör und
Ersatz“** (zum Ändern braucht es das Recht, Produkte zu bearbeiten):

- Unter **„Produkt hinzufügen“** suchst du das andere Produkt nach Nummer oder
  Name. Bei **„Art“** wählst du **„Zubehör“** oder **„Ersatz“**, bei **„Stück je
  Stück“** trägst du ein, wie viele davon zu einem Stück dieses Produkts
  gehören (Zubehör: zwei Kabel je Lautsprecher) oder wie viele ein fehlendes
  Stück ersetzen; dazu eine **Notiz** für die, die planen („für den 3-poligen
  Stecker“). Mit dem Haken **„Notwendig (nur Zubehör)“** wird das Zubehör
  „vorgeschrieben“ statt „empfohlen“ – das steht dann im Vorschlag.
  **„Ersatz auch umgekehrt eintragen“** legt zugleich den Ersatz in die
  andere Richtung an. Dann **„Hinzufügen“**.
- Jede Zeile kannst du ändern (**„Speichern“**), mit den Pfeilen **nach
  oben** und **nach unten** umsortieren – in dieser Reihenfolge schlägt die
  Planung vor – und **entfernen**.
- Darunter steht, bei welchen Produkten dieses selbst als Zubehör oder Ersatz
  eingetragen ist.
- Ein Set hat Zubehör, aber keinen Ersatz. Fahrzeuge, Dienstleistungen,
  Zumietungen und Aufpreise sind weder Zubehör noch Ersatz; Kundenmaterial
  geht nur mit Produkten desselben Kunden zusammen, euer eigenes nur mit
  eurem.
- Die **Seite eines Modells** zeigt den Kasten des Produkts nur zum Lesen, mit
  einem Link „Auf der Produktseite bearbeiten“.

**In der Planung** (Abschnitt 7, „Zubehör und Ersatz in der Planung“)
erscheinen die Vorschläge in einem Kasten über den Positionen; beim Erstellen
eines Angebots (Abschnitt 11) stehen sie als Hinweis, ohne dass etwas
hinzugefügt wird.

### Produkte aus mehreren Stück

Manches wird in Stückzahlen vermietet, die man als eine Einheit sieht: zehn
XLR-Kabel 1,5 m als „Kabelpaket K-005“. Du trägst dafür am
Produkt **„Stück je Produkt“** ein (nur Miet- und Verkaufsprodukte, ganze Zahl,
voreingestellt 1). Das Modell bleibt das einzelne Kabel; Rentalars rechnet in
Stück um:

- **Bestand:** einsatzbereite Exemplare geteilt durch die Stückzahl,
  abgerundet – 105 Kabel sind 10 Pakete, fällt ein Kabel aus, sind es 9. Die
  Produktliste zeigt „105 Exemplare“ und eine Spalte „Stück je Produkt“; das
  Produkt „Besteht aus 10 × XLR-Kabel 1,5 m“, das Modell „Ein Exemplar des
  Produkts K-005 besteht aus 10 Stück dieses Modells.“
- **Planung und Verfügbarkeit:** „3 × K-005“ reserviert 30 Kabel; Sperrzeiten
  schneiden an Anfang und Ende, übrige Kabel decken keine Sperrzeit ab; lose
  Inhalte eines Cases werden auf ganze Pakete aufgerundet.
- **Packen:** je Einheit werden entsprechend viele Exemplare gewählt und
  ausgegeben; die Zeile sagt „je 10 Stück“ und „15 von 20 Exemplaren
  gewählt“; Rentalars wählt selbst, wenn genau eine Einheit übrig ist oder
  der ganze Bestand rausgeht. Das Gewicht der Zeile ist Gewicht × Stück.
  Verkaufte Pakete nehmen ganze Pakete aus dem Bestand.
- **Auswertung:** der Ertrag je Exemplar (Abschnitt 4, „Was ein Exemplar
  einbringt“) ist der Positionsbetrag geteilt durch Menge × Stück; Wünsche
  (Fehlbestand) vergleichen Exemplare.
- **Wunsch nach einem bestimmten Exemplar**: Jedes gewünschte
  Exemplar deckt **ein Stück** der Zeile, nicht die ganze Menge. Wünschst du
  für „1 × Kabelpaket K-005“ (10 Stück) das Kabel 0042, bleibt die Zeile bei
  Menge 1 und Preis und zeigt „1 von 10 Stück“; die übrigen neun kommen aus
  irgendwelchen Exemplaren (Abschnitt 7, „Ein bestimmtes Modell oder
  Exemplar“).

Die Stückzahl lässt sich nicht ändern, solange Exemplare des Produkts auf einer
Packliste gewählt oder unterwegs sind oder solange Positionen des Produkts in
Projekten stehen, die noch nicht abgeschlossen sind – sonst würden sich deren
Mengen stillschweigend ändern. Sie lässt sich auch **nicht unter die Zahl der
gewünschten Exemplare** einer Position senken: Rentalars lehnt das ab und nennt
die Positionen („2027-0003 (3 Exemplare, 2 Stück)“); nimm zuerst die
überzähligen Wünsche heraus. Dupliziert du ein Projekt oder kopierst eine
Gruppe, behält die Kopie von den Wünschen nur so viele, wie ihre Stücke tragen. Fällt ein einzelnes Exemplar in eine Sperrzeit,
verliert die Planung nur dann ein ganzes Paket, wenn dadurch wirklich eines
weniger voll wird. Nicht unterstützt: Container-Produkte
mit mehr als einem Stück; der MVR-Import nimmt ein Gerät je Produkt an.
Unberührt bleiben Prüfungen, Etiketten, Defekte, Übergabe, Mindestbestand
(Exemplare) und Sets (sie nehmen die Stückzahl des Packprodukts). Import und
Export haben die Spalte „Stück je Produkt“; die API `pieces_per_product`.

### Deaktivieren statt löschen

Ein Produkt, das in Projekten vorkommt, lässt sich nicht löschen – alte
Projekte müssen lesbar bleiben. **Deaktiviere** es: Es bleibt in alten
Projekten sichtbar, lässt sich aber nicht mehr neu verplanen; dabei
endet auch sein Kalender-Link (Abschnitt 4, „Kalender-Link“). Das
Dienstleistungsprodukt einer Funktion löschst du mit seiner Funktion
(Abschnitt 12, „Funktionen“).

### Kundenmaterial – Material eines Kunden lagern und mitnehmen

Du betreust eine Band, lagerst ihr Mischpult und ihre Multicores bei dir
und nimmst sie zu ihren Gigs mit, wo du dein eigenes Material vermietest
und mit aufbaust? Dann führst du das Material der Band als
**Kundenmaterial**: wie euer eigenes, mit Modell, Gewicht, Maßen und
Lagerort, auf Wunsch mit Exemplaren, IDs und Etiketten – aber als
**Eigentum des Kunden**. Es hat nie einen Preis, wird nie an andere
vermietet und lässt sich nur in Projekten dieses Kunden einplanen. Im
Angebot steht es ohne Preis mit dem Hinweis, dass es mitgeführt wird, auf
der Packliste mit Gewicht und Volumen.

**Einrichten.** Einmal je Gerät oder Gerätegruppe:

1. Öffne den Kunden und klicke im Abschnitt **„Material des Kunden im
   Lager“** auf **„Material hinzufügen“**. Das Produktformular kommt mit
   der Kategorie C **„Fremdmaterial“**, der nächsten Artikelnummer (etwa
   `C-001`) und dem Kunden als **Eigentümer**. Über Materialverwaltung →
   Produkte → „Neues Produkt“ geht es ebenso: Kategorie C wählen, den
   Eigentümer eintippen – Name, Kundennummer oder Ort; den Kunden kannst
   du dort auch neu anlegen.
2. Name eintragen, zum Beispiel „Mischpult Band Nordlicht“. Statt nach
   Preisen fragt das Formular nur nach dem Eigentümer: Kundenmaterial hat
   keinen Preis, keinen Verkaufspreis, keinen Aufpreis, keine Staffel und
   keinen Rabatt. Es ist ein Mietprodukt – oder ein Set aus Produkten
   desselben Kunden; in eure eigenen Sets kommt es nie. „Speichern“.
3. Lege dazu wie gewohnt ein **Modell** an, mit Gewicht und Maßen, und
   ordne es dem Produkt zu (Abschnitt 4, „Neues Material anlegen“) – als
   Mengenmaterial ohne einzelne IDs („8 × Multicore 30 m“) oder mit
   Exemplaren, IDs, Lagerort und Etiketten, ganz wie euer eigenes
   Material.

**Wo es erscheint:**

- Die Seite des **Kunden** listet unter „Material des Kunden im Lager“
  alles, was ihm gehört, mit Bestand und Lagerort.
- **Produkt**, **Modell** und **Exemplare** tragen „Eigentum von …“ und
  das Schild „Kundenmaterial“; die Produktseite sagt statt eines Preises
  „Kundenmaterial, wird nie berechnet. Nur in Projekten dieses Kunden
  einplanbar.“ Die **Etiketten** nennen den Kunden statt eures
  Firmennamens (Abschnitt 4, „Etiketten“). Prüfungen, Defekte und
  Sperrzeiten gibt es wie für euer Material; aus einer Defektmeldung wird
  ein Servicefall für den Kunden (Abschnitt 4, „Defekt melden“).
- In der **Produktliste** filterst du unter „Eigentümer“ nach eigenem
  Material, Kundenmaterial oder einem bestimmten Kunden; die Spalte
  „Eigentümer“ blendest du über „Spalten“ ein. Sie geht mit in den Export
  und wird beim Import wieder eingelesen, mit Kundennummer oder Namen
  (Abschnitt 16, „Import und Export“).

**Im Projekt** planst du es wie jedes andere Material über das Feld unter
einer Teilgruppe. Die Suche bietet es nur in Projekten des Eigentümers
und ihren Teilprojekten an, mit dem Hinweis „Kundenmaterial“; in einem
fremden Projekt lehnt Rentalars es ab. Die Position trägt das Schild
**„Kundenmaterial – wird mitgeführt“** und statt eines Betrags „nicht
berechnet“. Sie bekommt keinen Rabatt – auch nicht den Standardrabatt des
Kunden –, kann nicht optional, Alternative oder verkauft sein und zählt in
keine Summe, nicht in die Steuer und nicht in die Einnahmen aus Material.

- **Verfügbarkeit:** Rentalars prüft sie wie bei eurem Material – ein
  Exemplar ist defekt, die Band hat zur selben Zeit einen zweiten Gig. Eine
  Fehlmenge kommt aber ohne „zumieten“: Kundenmaterial kann niemand
  anderes liefern.
- **Angebot und Auftragsbestätigung** führen es an seiner Stelle auf, mit
  Menge, ohne Preis und Betrag, mit dem Hinweis „Kundeneigenes Material –
  wird mitgeführt, ohne Berechnung“ – auch ein Angebot „nur Teilgruppen“
  nennt es unter seiner Teilgruppe. So weiß der Kunde, dass seine Sachen
  vor Ort sind. Der **Lieferschein** listet es mit „Kundeneigenes Material
  – wird mitgeführt“; **Rechnung** und XRechnung lassen es weg.
- **Preisübersicht** (Seite, PDF und CSV): mit dem Schild und „nicht
  berechnet“ statt der Preisspalten.
- **Packliste** (Bildschirm und PDF): mit Gewicht, Volumen und Lagerort
  und dem Hinweis „Kundenmaterial – wird mitgeführt“; das Gewicht zählt in
  die Ladung. Packen, Ausgabe und Rücknahme laufen wie gewohnt.
- Solange Kundenmaterial im Projekt geplant ist, lässt sich der **Kunde
  des Projekts nicht wechseln**. In ein Projekt eines anderen Kunden kommt
  es nicht mit: Wendest du dort eine Vorlage an, die es enthält, lässt
  Rentalars es weg und sagt es („Kundenmaterial eines anderen Kunden:
  …“).

**Weitere Kategorien.** Reicht euch C nicht – etwa, weil ihr Ton und Licht
der Kunden trennen wollt –, legt eine weitere Hauptkategorie mit eigenem
Bestand an und setzt an ihr den Haken **„Kundenmaterial“** (Einstellungen
→ Kategorien und Kürzel; Abschnitt 16, „Stammdaten“). Ihre
Unterkategorien folgen ihr. Umstellen lässt sich der Haken nur, solange die
Kategorie keine Produkte hat.

**Ein Kunde mit Material im Lager** lässt sich nicht löschen, nur
deaktivieren. Ändern lässt sich der Eigentümer eines Produkts nur, solange
es in keinem Projekt geplant ist.

---

## 6. Kunden

**Kunden → Neuer Kunde.** Firma oder Privatperson, Rechnungsadresse,
E-Mail, Telefon. Die Kundennummer vergibt Rentalars.

Auf der Seite des Kunden:

- **Rechnungsadresse** mit den kaufmännischen Angaben (unten), mit
  „Route in Google Maps“ und „Karte anzeigen“ (unten, „Route und Karte“);
- **Weitere Adressen** für Rechnung und Lieferung (unten), jede mit ihrem
  Link „Route in Google Maps“;
- **Ansprechpartner** anlegen, mit Anrede, Vorname, Nachname, Position,
  E-Mail und Telefon; einer davon kann der Hauptkontakt sein. Im Projekt
  wählst du, wer für diese Veranstaltung zuständig ist. Siehe unten,
  „Ansprechpartner: Vorname, Nachname und Anrede in Mails“.
- **Projekte** des Kunden, und der Knopf „Neues Projekt“ für diesen Kunden.
- **Material des Kunden im Lager** – was er bei euch lagert, mit Bestand
  und Lagerort, und der Knopf „Material hinzufügen“ (Abschnitt 5,
  „Kundenmaterial“).
- **Verlauf** aller Änderungen.

Einen neuen Kunden kannst du auch gleich beim Anlegen eines Projekts
erfassen, ohne das Projektformular zu verlassen (Abschnitt 7, „Ein Projekt
anlegen“).

**Wer den Namen des Kunden sieht.** Jeder, der ein
Projekt oder einen Servicefall sehen darf, sieht den **Namen des Kunden** – in
der Projektliste, in den Listen der Servicefälle, auf den Seiten, auf der
Packliste, in der Suche nach dem Namen und in der Schnittstelle
(`customer_name`), auch als Crew oder freie Kraft. **Klickbar** ist der
Name nur für alle, die Kunden lesen dürfen; für die übrigen steht er als
Text da. Alles Weitere bleibt beim Recht auf Kunden: Ansprechpartner,
Telefon und E-Mail, „Gemeldet von“, die Seite des Kunden mit seinen
Projekten. Kalender und Einsatz-PDF nennen weiter keinen Kunden.

Viele Kunden auf einmal – etwa aus dem bisherigen Programm oder aus
Lexware – übernimmst du mit „Import“ über der Kundenliste (Abschnitt 16,
„Import und Export“).

### Ansprechpartner: Vorname, Nachname und Anrede in Mails

Ein Ansprechpartner hat **Vorname** (freiwillig) und **Nachname**
(Pflicht); „Neuer Ansprechpartner“ öffnet eine ganze
Seite mit Anrede (Vorschläge Herr, Frau, Dr., Prof., Prof. Dr.), Vorname,
Nachname, Position, E-Mail, Telefon und „Hauptansprechpartner“. Der Name in
Listen, Suche, Exporten, Dokumenten und Empfängerlisten bleibt der
zusammengesetzte; sortiert wird nach Nachname, dann Vorname. Tippst du
beim Import oder über die API nur einen Namen, zerlegt ihn Rentalars: das
letzte Wort ist der Nachname, „von“, „van“, „de“, „der“, „zu“, „zur“ bleiben
beim Nachnamen, „Berg, Anna“ wird erkannt, ein einzelnes Wort ist der
Nachname. Eine Anrede vorn („Frau Müller“, „Hr. Berg“) wird zur Anrede
(oder entfällt, wenn schon eine eingetragen ist), Text in Klammern entfällt,
eine Bemerkung nach einem Komma („Anna Berg, Technik“) wird zur Position,
wenn diese leer ist. Vor- und Nachname zusammen dürfen höchstens 200 Zeichen
lang sein. Ältere Namen wurden so
zerlegt – ein Name mit Titel wie „Dr. Anna Berg“ ergibt den Vornamen „Dr.
Anna“; trage den Titel bei Bedarf in die Anrede um.

**Die Anrede in E-Mails** stellst du je Ansprechpartner im Abschnitt
„Anrede in E-Mails“ des Formulars ein; eine Vorschau zeigt, wie sie
lautet, und die Kundenseite hat eine Spalte dafür:

- **förmlich** (voreingestellt): „Sehr geehrte Frau Berg,“ / „Sehr geehrter
  Herr Berg,“ – nach der Anrede Frau/Herr (englisch Ms/Mr); ein Titel ohne
  Geschlecht („Dr.“) ergibt „Guten Tag Dr. Berg,“; ganz ohne Anrede „Guten
  Tag Anna Berg,“;
- **persönlich:** „Hallo Anna,“ – Titel entfallen; ohne Vorname wird sie
  förmlich;
- **eigener Text:** wörtlich, was du schreibst.

Die Anrede steht in neuen E-Mails, in der Antwort und in der Mail zu einem
Dokument – wenn genau ein Empfänger gewählt ist und er ein Ansprechpartner
des Kunden dieses Projekts ist –, im Entwurf der KI (wörtlich) und, als
`{greeting}` oder `{anrede}`, in den Texten der Dokumente und der automatischen
Antwort auf Anfragen. Nicht gebaut: eine Standardanrede für die ganze
Firma; die Knöpfe „An“ im Mailformular ändern die Anrede nicht, wenn man
sie nach dem Schreiben benutzt.

### Gibt es den Kunden schon?

Beim Anlegen vergleicht Rentalars schon während des Tippens Name und
E-Mail-Adresse mit den vorhandenen Kunden. Gibt es einen mit ähnlichem
Namen oder derselben E-Mail-Adresse, erscheint **„Diesen Kunden gibt es
vielleicht schon:“** mit Name, Kundennummer, Ort und dem Grund („ähnlicher
Name“, „gleiche E-Mail-Adresse“). Ein Klick öffnet ihn in einem neuen
Fenster.

Ist es wirklich derselbe, arbeitest du mit dem vorhandenen weiter. Ist es
ein anderer – zwei Firmen „Müller GmbH“ in verschiedenen Städten –, setzt du
beim Speichern den Haken **„Trotzdem anlegen – es ist ein anderer Kunde“**.
Ohne diesen Haken legt Rentalars keinen zweiten an.

### Kaufmännische Angaben

Im Formular des Kunden („Kunde bearbeiten“):

- **USt-IdNr.** – mit Länderkürzel, ohne Leerzeichen, z. B. `DE123456789`
  (Leerzeichen entfernt Rentalars selbst). Sie steht auf Auftragsbestätigung
  und Rechnung als „Ihre USt-IdNr.“. Hat der Kunde eine USt-IdNr. eines anderen EU-Landes und gilt für die Leistung der Steuersatz 0 %, steht auf der Rechnung der Hinweis auf die
  Steuerschuldnerschaft des Leistungsempfängers (Reverse Charge) statt „Umsatzsteuerfrei“; die E-Rechnung nennt die Kategorie AE und verlangt die USt-IdNr. deiner Firma. Das gilt nicht für Kleinunternehmer (§ 19 UStG, Einstellung in der Buchhaltung) und nicht für Kunden in Nordirland (XI); bei Warenverkäufen an Unternehmen im EU-Ausland (innergemeinschaftliche Lieferung) ist es nicht der richtige Fall – das mit der Steuerberatung klären.
- **Steuernummer** – etwa für Kunden ohne USt-IdNr.; der Import aus Lexware
  bringt sie mit.
- **Leitweg-ID oder Käuferreferenz** – für Rechnungen an Behörden die
  Leitweg-ID, sonst eine Referenz, die der Kunde auf seinen Rechnungen
  verlangt. Rentalars setzt sie als Käuferreferenz in die XRechnung
  (Abschnitt 11); leer steht dort die Projektnummer.
- **Zahlungsziel in Tagen** – wie lange der Kunde für eine Rechnung Zeit
  hat. Leer gilt das Zahlungsziel aus den Firmendaten (Abschnitt 16).
- **Standardrabatt in Prozent** – geht in jede neue Materialposition, die
  ihr in seinen Projekten hinzufügt, und bleibt dort je Position änderbar.
  Bestehende Positionen ändert er nicht. Sehen und ändern darf ihn nur, wer
  Preise sehen darf; für alle anderen gibt es das Feld nicht.

### Mehrere Adressen

Die Adresse am Kunden ist seine **Hauptadresse** und bleibt die
Rechnungsadresse, wenn nichts anderes gewählt ist. Daneben kann ein Kunde
beliebig viele **weitere Adressen** haben – die Buchhaltung in der
Zentrale, das Lager Nord als Lieferadresse.

**Weitere Adressen → Neue Adresse:** Art (**Rechnungsadresse** oder
**Lieferadresse**), eine Bezeichnung („Lager Nord“), Name bzw. Firma (leer:
der Name des Kunden), Zusatz („Abteilung, c/o …“) und die Anschrift. Mit
**„Voreinstellung“** wird sie zur Standardadresse ihrer Art; je Art gibt es
eine.

**Im Projekt.** Ein neues Projekt übernimmt die Standardadressen seines
Kunden von selbst – ob du den Kunden im Formular wählst, das Projekt über
„Neues Projekt“ auf der Seite des Kunden anlegst oder ein anderes Programm
es über die API anlegt. Unter „Projekt bearbeiten“ kannst du danach eine
andere **Rechnungsadresse** und **Lieferadresse** aus den weiteren Adressen
des Kunden wählen; die Felder erscheinen, wenn der Kunde solche Adressen
hat.

- Die Rechnungsadresse steht auf Auftragsbestätigung und Rechnung. Leer:
  die Adresse des Kunden.
- Die Lieferadresse steht auf dem Lieferschein. Leer: der
  Veranstaltungsort, sonst die Adresse des Kunden.

Wechselt der Kunde eines Projekts, passen die Adressen des bisherigen
Kunden nicht mehr: An ihre Stelle treten die Standardadressen des neuen.

### Löschen und Anonymisieren

Ein Kunde ohne Projekte lässt sich löschen – außer, er hat Material bei
euch im Lager (Abschnitt 5, „Kundenmaterial“); dann deaktivierst du ihn.
Hat er Projekte, bleiben diese
als Geschäftsvorgänge erhalten; der Kunde
kann dann **anonymisiert** werden („Kunde anonymisieren“ unten auf seiner
Seite): Name, Adresse, Kontaktdaten und Notiz werden überschrieben, alle
Ansprechpartner gelöscht, und auch aus dem Änderungsprotokoll verschwinden
die alten Angaben. Kundennummer und Projekte bleiben mit ihren Zahlen
bestehen. Das ist für Löschwünsche gedacht und lässt sich **nicht
rückgängig machen**. Wer nur nicht mehr in Auswahllisten erscheinen soll,
wird stattdessen auf „nicht aktiv“ gestellt. Mit einem anonymisierten
Kunden verschwinden auch die Mails, die von ihm stammen oder an ihn
gingen (Abschnitt 14).

### Veranstaltungsorte

**Kunden → Veranstaltungsorte.** Hallen, Clubs, Plätze, an denen ihr
öfter arbeitet, mit allem, was die Crew wissen muss: Anschrift,
**Ansprechpartner vor Ort** mit Telefon, **Zufahrt und Anlieferung**
(Ladezone, Durchfahrtshöhe, Parken, Schlüssel), **Strom** (Anschlüsse,
Absicherung, Entfernungen), Notizen und ein **Lageplan/Hallenplan** als
PDF oder Bild.

Im Projekt tippst du den Ort ins Feld „Veranstaltungsort“ und wählst ihn
aus den Vorschlägen; einen neuen legst du dort gleich im Dialog an
(Abschnitt 7, „Ein Projekt anlegen“). Das Feld „Ort, freier Text“ nimmt
Ergänzungen wie „Halle 3“ auf – oder einen Ort, der keine Stammdaten
verdient. Im Kopf des Projekts führt der Name des Orts zu seiner Seite;
seine Hinweise stehen im Reiter „Überblick“ des Projekts, den auch die
Crew sieht (Abschnitt 12). Ein Ort, den Projekte nennen, lässt sich nicht
löschen, nur deaktivieren. Auf seiner Seite führt „Route in Google Maps“
von dort, wo du gerade bist, zum Ort, und „Karte anzeigen“ zeigt, wo er
liegt (gleich unten).

### Route und Karte

An jeder Anschrift – Veranstaltungsort, Kunde und seine weiteren Adressen,
Lieferant (auf der Seite „Zumietung bei …“, Abschnitt 9), eure Firma unter
Einstellungen → Firmendaten und Grundeinstellungen – steht der Link
**„Route in Google Maps“**. Er öffnet die Routenplanung von Google Maps
in einem neuen Tab und startet immer an deinem aktuellen Standort – bei
jeder Anschrift, auch bei Veranstaltungsorten, Lieferadressen und
Lieferanten. Bei Fahrten mit Zwischenstopps bleiben die Stopps erhalten
(Abschnitt 7, „Die Fahrten eines Projekts“). Die Anschrift verlässt
Rentalars erst mit diesem Klick. Eine Entfernung rechnet Rentalars nur aus,
wenn euer Administrator den Routendienst eingerichtet hat – und dann nur als
Vorschlag für die Kilometer eines Fahrzeugs auf einer Fahrt (Abschnitt 7,
„Logistik“).

**Die Karte.** Unter der Anschrift steht **„Karte anzeigen“**. Erst mit dem
Klick fragt Rentalars bei OpenStreetMap, wo die Anschrift liegt – einmal je
Anschrift; die Antwort merkt es sich –, und dein Browser lädt die Karte von
OpenStreetMap. Vorher geht nichts hinaus. Mit den Kartenbildern schickt
dein Browser die Adresse eurer Installation (nur Schema und Host, ohne
Pfad) an OpenStreetMap – das verlangen dessen Nutzungsregeln. Die Karte zoomst du mit „+“ und
„−“, am Telefon mit zwei Fingern, mit dem Mausrad erst, wenn du in die
Karte geklickt hast – sonst würde sie beim Scrollen der Seite mitzoomen;
unten rechts steht „© OpenStreetMap-Mitwirkende“. Jede Anschrift hat eine
nummerierte Markierung. Unter der Karte steht je Anschrift,
woher ihre Position kommt: „Position von OpenStreetMap“, „Position von Hand
gesetzt“ oder „Auf der Karte nicht gefunden.“

**Liegt eine Markierung falsch** – eine neue Halle, eine Anschrift, die
OpenStreetMap nicht kennt –, öffne darunter **„Position korrigieren“**:
Klick in die Karte, zieh die Markierung oder gib Breiten- und Längengrad
ein (der Weg mit der Tastatur), dann **„Position speichern“**. Die Position
gilt für alles mit derselben Anschrift – auch für Projekte und Kunden, die
diesen Ort nennen. **„Neu suchen lassen“** verwirft die Position und fragt
OpenStreetMap noch einmal. Korrigieren darf, wer den Datensatz ändern darf,
zu dem die Karte gehört – bei einem Projekt, wer es bearbeiten darf; die
Änderung steht in dessen Verlauf.

Die Karte eines Projekts steht bei seinen Fahrten, in der Zeitplanung und
im Überblick (Abschnitt 7, „Zeitplanung“). Wer die Karten immer gleich
sehen will, schaltet unter Einstellungen → Firmendaten und
Grundeinstellungen **„Karten sofort laden“** ein; dann geht jede Anschrift
schon beim Öffnen der Seite an OpenStreetMap. Hat euer Administrator die
Karten in der Konfiguration abgeschaltet, gibt es nur die Links zu Google
Maps.

---

## 7. Projekte planen

### Ein Projekt anlegen

**Projekte → Neues Projekt.** Name und Kunde sind Pflicht; die Projektnummer
vergibt Rentalars. Gibt es Projektvorlagen, steht oben das
Feld **„Vorlage“**: Wählst du eine, kommen Teilgruppen, Positionen,
Personalpositionen und Zeitplanung der Vorlage beim Speichern dazu (unten,
„Projektvorlagen“). Für eine Vermietung ohne Personal gibt es die Vorlage
„Dry Hire (Vermietung ohne Personal)“ (unten, „Dry Hire – Vermietung ohne
Personal“).

**Projekte aus der Zeit vor Rentalars**. Habt ihr alte Rechnungen
als PDF und wollt die Projekte dahinter in Rentalars haben, legst du sie nicht von Hand
an: Buchhaltung →
Altprojekte importieren liest die Rechnungen und legt abgeschlossene Projekte
an (Abschnitt 11, „Altprojekte importieren“).

**Die Projektnummer** besteht aus dem Jahr und einer laufenden Nummer:
`2026-0042`. Mit jedem Jahr beginnt die Zählung wieder bei 0001.
Teilprojekte tragen die Nummer ihres Gesamtprojekts mit einer angehängten
Zahl: `2026-0042-1`, `2026-0042-2`. Das Präfix stellt ein Administrator
unter Einstellungen → Nummernkreise ein (Abschnitt 16); eine Änderung gilt
nur für neue Projekte.

**Nummern mit „P-“.** Projektnummern beginnen nicht mit „P-“
(`P-2026-0042`); eine Nummer mit „P-“ wird trotzdem verstanden.
Sie steht im Kopf des Projekts hinter der heutigen –
„(früher P-2026-0042)“ – und funktioniert: in der Suche, im Filter
der Projektliste, wo du eine Projektnummer einträgst (etwa beim
Verschieben oder Übernehmen einer Mail), in Links und Lesezeichen
(sie führen zur heutigen Adresse) und in Antworten auf Mails mit der
Kennung `[RL#P-2026-0042]` – solche Mails landen im Projekt
(Abschnitt 14).

**Kunde und Veranstaltungsort durch Tippen.** Statt aus einer langen Liste
wählst du den Kunden, indem du ein paar Buchstaben von Name, Kundennummer
oder Ort eintippst und einen der Vorschläge nimmst. Gibt es den Kunden noch
nicht, lautet der letzte Vorschlag etwa **„Müller GmbH“ als neuen Kunden
anlegen**. Er öffnet das Kundenformular in einem Dialog, mit dem
Getippten als Namen und mit derselben Warnung vor Dubletten wie unter
Kunden (Abschnitt 6, „Gibt es den Kunden schon?“). Nach „Kunde speichern“
steht der neue Kunde im Projekt, und du bist weiter im Projektformular.
Ebenso das Feld **„Veranstaltungsort“**: Name oder Ort tippen, oder als
letzten Vorschlag **„…“ als neuen Veranstaltungsort anlegen**. Neu anlegen
kann, wer Kunden bearbeiten darf.

**Ansprechpartner anlegen**. Im Feld **„Ansprechpartner“** stehen die Ansprechpartner des gewählten Kunden; als
letzte Auswahl steht **„+ Neuer Ansprechpartner …“**, sobald ein Kunde gewählt ist und du Kunden bearbeiten darfst. Sie öffnet einen
Dialog mit Anrede, Vorname, Nachname (Pflicht), Position, E-Mail und Telefon; nach „Ansprechpartner speichern“ ist die Person im Feld
gewählt, und im Projektformular geht nichts verloren. Der erste Ansprechpartner eines Kunden wird sein Hauptansprechpartner; den Gruß
in Mails und weitere Angaben pflegst du auf der Seite des Kunden. Das gilt im Formular für ein neues Projekt, beim Bearbeiten, für ein
Teilprojekt und beim Umwandeln eines Servicefalls sowie im Formular „Neuer Servicefall“ und beim Bearbeiten eines Servicefalls. Bei einem anonymisierten Kunden fehlt die Auswahl; wer zweimal klickt,
legt dieselbe Person nicht doppelt an.

Hat der Kunde Standardadressen für Rechnung und Lieferung, übernimmt das
Projekt sie; eine andere wählst du unter „Projekt bearbeiten“ (Abschnitt
6, „Mehrere Adressen“).

**Internes Projekt.** Mit dem Haken „internes Projekt“ braucht ein Projekt
keinen Kunden. Es ist für Zeiten gedacht, die zu keinem Kundenprojekt
gehören – Lager, Werkstatt, Büro. Jeder, der Zeiten erfasst, kann darauf
buchen (Abschnitt 13). Am einfachsten legt ihr eines an, das das ganze Jahr
läuft.

Ein Projekt hat **zwei Zeiträume**. Das Formular nennt sie nach dem, was
sie entscheiden, und der Unterschied ist wichtig:

| Im Formular | Felder | Bedeutung | Wofür |
|---|---|---|---|
| **„Mietzeitraum: Material ist außer Haus“** | „Material außer Haus ab“, „Material zurück bis“ | vom Verlassen des Lagers bis zur Rückkehr, Auf- und Abbau eingeschlossen | entscheidet über die **Verfügbarkeit**; die Positionen übernehmen ihn |
| **„Veranstaltung – für die berechneten Miettage“** | „Veranstaltung von“, „Veranstaltung bis“, „Miettage“ | freiwillig: die Tage der Veranstaltung selbst, etwa die Showtage | schlägt nur die **Miettage** vor, die berechnet werden |

**Nur der Mietzeitraum entscheidet, wann das Material belegt ist.** Eine
Hochzeit am Samstag von 15 bis 2 Uhr ist *ein* Miettag. Das Material
verlässt aber am Freitag das Lager und kommt am Montag zurück – so lange ist
es für andere Projekte nicht zu haben. Den Veranstaltungszeitraum darfst
du leer lassen; er ändert an der Verfügbarkeit nichts.

Beide Kästen sind gleich aufgebaut: „von“, „bis“ und **„Zeitraum im
Kalender wählen“** in einer Zeile, bei der Veranstaltung darunter die
Miettage; in schmalen Fenstern rückt der Knopf unter die Felder. Im
Kalender des Mietzeitraums ist die Veranstaltung schraffiert, sobald du
sie eingetragen hast, und umgekehrt – so siehst du beim Wählen gleich, wie
die beiden zueinander liegen (Abschnitt 2, „Zeiträume eingeben“).

**Übliche Zeiten: 12 bis 12 Uhr.** Ein neues Projekt schlägt als
Mietzeitraum morgen 12:00 Uhr bis übermorgen 12:00 Uhr vor. Die Uhrzeiten
stellt ihr unter Einstellungen → Firmendaten und Grundeinstellungen um
(„Übliche Beginnzeit“, „Übliche Endzeit“).

**Miettage** sind die Tage, die berechnet werden. Lässt du das Feld leer,
rechnet Rentalars sie aus dem Veranstaltungszeitraum aus – gibt es keinen,
aus dem Mietzeitraum: Jede angefangenen 24 Stunden zählen als ein Tag. Du
kannst jeden anderen Wert eintragen – was ihr berechnet, ist eure
Entscheidung.

**Mehrteilige Veranstaltungen** – Aufbau am Donnerstag, Show am Freitag und
Samstag – tragt ihr nicht als mehrere Veranstaltungszeiträume ein, sondern
als **Phasen** im Reiter „Zeitplanung“ (Aufbau, Showtag 1, Showtag 2 …;
unten, „Zeitplanung“). Der Mietzeitraum umfasst alles; die Miettage tragt
ihr ein, wie ihr sie berechnet.

### Der Status

Der Status sagt, wie verbindlich das Projekt ist – und davon hängt ab, ob
es Material für andere blockiert.

| Status | Bedeutung | Reserviert Material? |
|---|---|---|
| **Anfrage** | jemand hat gefragt | nein |
| **Option** | Kunde hat Interesse, noch nicht zugesagt | **vorgemerkt**: sichtbar für andere, nimmt aber nichts weg |
| **Bestätigt – Preise und Einzelheiten offen** | zugesagt, Einzelheiten fehlen noch | **fest** |
| **Bestätigt** | zugesagt | **fest** |
| **Unterwegs** | alles Material ist ausgegeben | **fest** |
| **Wieder im Lager** | Material ist wieder da | nein |
| **Abgeschlossen** | erledigt; nicht mehr änderbar | nein |
| **Storniert** | findet nicht statt | nein |

Den Status änderst du oben im Kopf des Projekts, auf jedem Reiter: Wähle
in der Liste **„Status ändern auf …“** den neuen Status und klicke
**„Status ändern“**. Die Liste bietet nur sinnvolle nächste Schritte; vor
„Storniert“ fragt Rentalars nach. Du bleibst auf dem Reiter, auf dem du
warst (unten, „Der Kopf eines Projekts“).

„Wieder im Lager“ heißt nicht „Zurück“,
damit es niemand mit dem Knopf „← Zurück“ verwechselt (Abschnitt 2).

„Unterwegs“ und „Wieder im Lager“ musst du nicht von Hand setzen: Rentalars
setzt „Unterwegs“, sobald **alles** Material des Projekts ausgegeben ist –
bei mehreren Packlisten, wenn alle ausgegeben sind –, und „Wieder im
Lager“, sobald die Rücknahme abgeschlossen ist – von selbst, wenn mit
„Rücknahme buchen“ alles zurück ist – und keine Packliste mehr unterwegs
ist oder auf ihre Ausgabe wartet (Abschnitt 10). Ist erst ein Teil unterwegs, behält das
Projekt seinen Status, zum Beispiel „Bestätigt“. Das ausgegebene Material
ist trotzdem unterwegs und für andere Projekte nicht frei. Willst du das
Projekt schon vorher auf „Unterwegs“ stellen, geht das von Hand; „Anfrage“,
„Option“ und „Storniert“ lassen sich nicht setzen, solange Material
unterwegs ist.

Ein **abgeschlossenes** Projekt lässt sich nicht mehr ändern – nur, ob es
eine Rechnung hat, lässt sich noch vermerken (Abschnitt 11, „Noch zu
schreibende Rechnungen“). Wieder öffnen darf nur, wer das Recht
„Abgeschlossene Projekte wieder öffnen“ hat.

**Löschen** lassen sich nur Anfragen, Optionen und stornierte Projekte. Ein
bestätigtes Projekt wird storniert, nicht gelöscht – so bleibt
nachvollziehbar, was war.

### Der Kopf eines Projekts

Die Seite eines Projekts hat zehn Reiter: **Überblick**, **Planung**,
**Preisübersicht**, **Dokumente** – direkt nach den Preisen, aus denen sie
entstehen, und mit den Dateien des Projekts –, **Zeitplanung**,
**Packliste**, **Korrespondenz**, **Chat**, **Zugriff**,
**Verlauf**. **Der Überblick ist der erste Reiter**, wie bei einem
Servicefall, und dort landest du, wenn du ein Projekt aus einer Liste, der
Startseite, der Suche, einem Kalender, der Kundenseite oder einer
Benachrichtigung öffnest (Adresse `/projects/<Nr>/overview/`). Die Planung
bleibt unter „Planung“ (`/projects/<Nr>/`); gespeicherte Links, Sprünge zu
Fehlbeständen und die Rückkehr nach einer Planungsaktion führen weiter dorthin.
Wer nur eingeplant ist und sonst nichts planen darf, sieht im
persönlichen Kasten des Überblicks „Du bist nicht eingeplant“, solange er
nicht eingeplant ist. Wer nur eingeplant ist, sieht davon
„Packliste“, „Chat“ und „Überblick“ und – nach seiner Zusage
oder fest eingeplant – „Korrespondenz“ mit den offenen Nachrichten
(Abschnitt 12); sonst „Korrespondenz“ nur,
wer Mails lesen darf (Abschnitt 14); „Preisübersicht“ nur, wer Preise sehen
darf. Ein Gesamtprojekt und seine Teilprojekte haben direkt nach „Planung“
den Reiter **Teilprojekte** (unten, „Teilprojekte“). Ein Servicefall hat
weniger Reiter (unten, „Servicefälle“).

Ganz oben steht die Projektnummer – bei einem Projekt mit einer Nummer mit „P-“ steht diese dahinter, „(früher
P-2026-0042)“ (oben, „Ein Projekt anlegen“). Über den Reitern stehen
Status, Kunde, Zeitraum, Veranstaltungsort und das **Kürzel** des Projekts
für den Betreff von Mails, etwa `[RL#2026-0042]` – ein Klick kopiert es –,
darunter eine **Wiedervorlage**, wenn es eine gibt (unten). Dort steht ab „Wieder im Lager“ für alle, die Preise sehen dürfen, auch
der Stand der **Rechnung** – „Rechnung RE-…“, „Rechnung gestellt“, „Keine
Rechnung“ oder „Rechnung offen“ (Abschnitt 11, „Noch zu schreibende
Rechnungen“). Rechts daneben stehen die Aktionen, auf jedem Reiter gleich
und immer in dieser Reihenfolge:

- **„Projekt bearbeiten“** – Name, Kunde, Zeiträume, Adressen (oben, „Ein
  Projekt anlegen“).
- **Status:** Wähle in der Liste „Status ändern auf …“ den neuen Status
  und klicke „Status ändern“. Die Liste bietet nur, was vom jetzigen Status
  aus möglich ist; der Knopf lässt sich erst drücken, wenn du einen Status
  gewählt hast. Vor „Storniert“ fragt Rentalars nach. Bei einem Projekt
  mit Teilprojekten steht daneben „Teilprojekte auch“ (unten,
  „Teilprojekte“). Du bleibst auf dem Reiter, auf dem du warst – nur
  „Bestätigt – Preise und Einzelheiten offen“ ohne offene Punkte führt in die Zeitplanung,
  damit du sie notierst.
- **Dokument erstellen:** Der Knopf schlägt vor, was als Nächstes dran ist
  – bei einer Anfrage oder Option „Angebot erstellen“, bei einem
  bestätigten Projekt „Auftragsbestätigung erstellen“, unterwegs
  „Lieferschein erstellen“, wieder im Lager oder abgeschlossen „Rechnung
  erstellen“. Hinter dem Pfeil ▾ stehen die übrigen Dokumente. Der Knopf
  öffnet den Reiter „Dokumente“ mit dem gewählten Dokument im Kasten
  „Dokument erstellen“; dort siehst du den Entwurf und erstellst es
  (Abschnitt 11). Ein Klick im Kopf erstellt also noch nichts. Ein
  Teilprojekt bekommt Angebot, Auftragsbestätigung und Rechnung über sein
  Gesamtprojekt, und ohne Preisrecht gibt es keine Dokumente mit Preisen –
  dann schlägt der Knopf bei einem bestätigten oder laufenden Projekt den
  Lieferschein vor, sonst nichts; die Liste hinter dem Pfeil bleibt. Ist
  „Rentalars als Buchhaltungsprogramm verwenden“ aus (Abschnitt 11), schlägt er keine
  Rechnung vor, und hinter dem Pfeil steht keine.
- **„Wiedervorlage“** – das Projekt an einem Tag wieder vorlegen lassen
  (unten, „Wiedervorlage“). Hat es schon eine, fehlt der Knopf; die
  Wiedervorlage steht dann mit „Ändern“ und „Erledigt“ unter den Angaben
  des Kopfs.
- **„Duplizieren“**, **„Als Vorlage speichern“**, **„Teilprojekt
  anlegen“** – hinter dessen Pfeil ▾ **„In Teilprojekte gliedern“**, an
  einem Gesamtprojekt **„Teilgruppen in Teilprojekte umwandeln“** (unten,
  „Teilprojekte“).

Was du nicht darfst, fehlt: Status, Dokumente und Wiedervorlage nur mit dem
Recht, das Projekt zu bearbeiten, „Projekt bearbeiten“ nur, solange es
nicht abgeschlossen ist.

### Wiedervorlage

Ein Angebot nachfassen, beim Kunden nach den Aufbauzeiten fragen: Mit
**„Wiedervorlage“** im Kopf des Projekts legt Rentalars das Projekt an
einem Tag wieder vor. Im Dialog wählst du **„Wiedervorlage am“** – den Tag
–, auf Wunsch eine **„Uhrzeit“**, **„Für“** – vorgewählt bist
du; zur Wahl steht, wer das
Projekt öffnen darf – und schreibst auf Wunsch eine **„Notiz“**, etwa
„Angebot nachfassen“; „Wiedervorlage speichern“. Das
geht in jedem Status, auch bei abgeschlossenen Projekten, denn an der
Planung ändert es nichts. Typisch ist es für Anfragen und Optionen.

- **Am Tag** bekommt die Person die Benachrichtigung „Wiedervorlage: …“ –
  ohne Uhrzeit ab 6 Uhr morgens, mit Uhrzeit ab dieser Uhrzeit (auch vor
  6 Uhr). Erst dann gilt die Wiedervorlage als fällig – im Kopf, auf der
  Startseite, in der Projektliste und für die Automation „Wiedervorlage
  fällig“. Die Benachrichtigung kommt in Rentalars und, wie unter Mein
  Konto → Benachrichtigungen bei „Wiedervorlage eines Projekts“ eingestellt
  (voreingestellt ja), per Mail und in der Companion-App. Ein Tag, der
  schon vorbei ist, ist sofort fällig. Ist die Person inzwischen
  deaktiviert, geht die Benachrichtigung an die Projektleitung. Änderst du
  nur die Notiz, kommt keine neue; ein neuer Tag, eine neue Uhrzeit oder
  eine andere Person bekommt eine.
- **Im Kopf des Projekts** steht sie, bis sie erledigt ist – „Wiedervorlage
  am Di 20.10.2026 um 14:30 für Anna Becker – Angebot nachfassen“, ab ihrer
  Zeit mit „fällig“ –, für alle, die die Planung lesen dürfen; mit „Ändern“
  und „Erledigt“ für alle, die das Projekt bearbeiten dürfen.
- **Auf der Startseite** stehen unter „Deine Wiedervorlagen“ die fälligen,
  die für dich sind (Abschnitt 2, „Startseite und Suche“); „Alle meine
  Wiedervorlagen“ führt zu Planung → Wiedervorlagen.
- **Unter Planung → Wiedervorlagen** stehen alle Wiedervorlagen von
  Projekten und Servicefällen in einer Tabelle (Abschnitt 15,
  „Wiedervorlagen“).
- **In der Projektliste** steht sie unter dem Namen des Projekts. Der
  Filter **„Wiedervorlage“** zeigt „fällig“, „für mich“ oder „alle mit
  Wiedervorlage“ – über alle Status, wie eine Suche –, und die Spalte
  „Wiedervorlage“ blendest du über „Spalten“ ein, um danach zu sortieren.
  Filter, Spalte und Notiz in der Liste sieht nur, wer auch die Kunden
  sehen darf; die Crew sieht keine Wiedervorlagen.
- **Im Kalender** mit dem Haken „Wiedervorlagen“ über dem
  Kalender (Abschnitt 15, „Kalender“).

**„Erledigt“** nimmt die Wiedervorlage vom Projekt. Setzen, Ändern und
Erledigen stehen im Verlauf des Projekts.

### Verwandte Projekte und Servicefälle

Die Reklamation zum Stadtfest, der Servicefall zum Pult, das beim
Kunden ausfiel, das Folgeprojekt im nächsten Jahr: Du verbindest
Projekte und Servicefälle miteinander. Ein Projekt oder Servicefall kann mit beliebig vielen anderen
verwandt sein; die Verwandtschaft gilt in beide Richtungen und steht bei
beiden.

Der Kasten **„Verwandt“** steht im **Überblick** eines Projekts und auf
der **Seite eines Servicefalls** – für alle, die die Planung lesen dürfen
oder am Servicefall arbeiten. Er ist klein und dezent: eine
Überschrift und eine Zeile je Eintrag mit Nummer, Name, Art (Projekt oder
Servicefall), Status und der Notiz, mit einem Link; das Formular zum
Verknüpfen klappt erst unter „Verwandtes eintragen“ auf. Darfst
du das andere Projekt nicht öffnen, steht dort nur „Projekt 2027-0042
(kein Zugriff)“ – ohne Name, Status, Notiz und Link.

- **Verknüpfen:** Unter **„Projekt oder Servicefall“** Nummer oder Namen
  tippen und aus den Vorschlägen wählen (ohne JavaScript die ganze
  Nummer), auf Wunsch eine **„Notiz (optional)“** wie „Reklamation zu
  …“, dann **„Verknüpfen“**. Das darf, wer dieses Projekt bearbeiten und
  das andere lesen darf.
- **Lösen:** **„Lösen“** in der Zeile, nach einer Rückfrage – mit
  Bearbeiten-Zugriff hier und Lese-Zugriff dort.

Verwandt sind immer ganze Projekte und Servicefälle; ein Teilprojekt
zeigt den Kasten nur, wenn es schon Einträge hat – verknüpfe sein
Gesamtprojekt. Verknüpfen und Lösen stehen im Verlauf beider Seiten.
Duplizieren übernimmt keine Verwandtschaften; wird aus einem Servicefall
ein Projekt, behält es sie.

### Die Planungsseite

Die Planung zeigt die Positionen, Teilgruppe für Teilgruppe, darunter die
Positionen ohne Teilgruppe, das **Personal**, die **Logistik**
(unten, „Logistik“), die Aufpreise und die Summen.
Jede Zeile zeigt Menge, Produkt, **Verfügbarkeit** und – mit Preisrecht –
Miettage, Einzelpreis und Betrag.

#### Eine Position hinzufügen

Unter jeder Teilgruppe (und unter „Ohne Teilgruppe“) ist ein Feld:
**„Hinzufügen: Artikelnummer, Produkt, Modell oder Exemplar-ID“.**

1. Tippe ein paar Zeichen – `K-005` oder `xlr`. Eine Liste schlägt Produkte
   vor, mit ihrem Bestand.
2. Wähle mit Mausklick oder Pfeiltasten und Enter.
3. Trage die Menge ein, drücke Enter oder „Hinzufügen“.

Die Position erscheint sofort, mit Preis und Ampel. Der Zeitraum der
Position ist zunächst der des Projekts. **Kundenmaterial** – was ein Kunde
bei euch lagert – schlägt das Feld nur in Projekten dieses Kunden vor; es
steht dann ohne Preis mit „Kundenmaterial – wird mitgeführt“ da (Abschnitt
5, „Kundenmaterial“). **Nebenkosten** – Transport, Fahrtkosten, Gebühren –
fügst du hier hinzu wie Material.

**Dienstleistungen** schlägt das Feld nicht vor: Personal planst du im
Block „Personal“ über seine Funktion, und die Personalposition übernimmt
den Preis ihres Dienstleistungsprodukts (Abschnitt 12, „Personal im Projekt
einplanen“). Tippst du doch eine Dienstleistung ein, lehnt Rentalars sie
mit diesem Hinweis ab. Ältere Materialpositionen mit einer Dienstleistung
bleiben, wie sie sind – mit Preis und auf erstellten
Dokumenten –, tragen aber den Hinweis „Dienstleistung – unter Personal
planen“; für neue Einsätze planst du die Funktion im Block Personal.

**Fahrzeuge und Anhänger** schlägt das Feld ebenso wenig vor:
Sie buchst du im Block „Logistik“ (unten, „Logistik“). Tippst du doch eins
ein, lehnt Rentalars es ab („… ist ein Fahrzeug. Fahrzeuge und Anhänger
werden unter „Logistik“ gebucht.“).

**Ein bestimmtes Modell oder Exemplar.** Das Feld findet auch Modelle
(„Robe Pointe“, „Sennheiser“) und einzelne Exemplare (die ID `0742` oder
eine Seriennummer). Wählst du einen solchen Treffer, entsteht die Position
für das zugehörige Produkt – und das Modell oder Exemplar steht als
**Wunsch** daran. Der Wunsch ist ein interner Hinweis für das Lager: Er
erscheint an der Position und auf der Packliste, nicht in der
Preisübersicht, und er ändert weder Preis noch Verfügbarkeit. Rentalars
warnt, wenn das gewünschte Exemplar defekt, fest verbaut oder im selben
Zeitraum schon anderswo gewünscht ist. Mit **„Exemplare scannen“** (unten,
„Unter den Teilgruppen“) wünschst du Exemplare, indem du ihr Etikett liest
(Abschnitt 4, „Scannen“).

**Ein Wunsch deckt ein Stück, nicht die Zeile**. Steht eine
Position für mehrere Stücke – „1 × Kabelpaket“ aus zehn Kabeln oder „6 ×
Mikrofon“ –, deckt jedes gewünschte Exemplar **eines** dieser Stücke. Die
Zeile bleibt, wie sie war: Menge 1, derselbe Preis, dieselbe Verfügbarkeit; der
Wunsch steht als **„Wunsch: Exemplar 0042 (Cordial XLR) – 1 von 10 Stück“**
daran. Die übrigen neun Kabel kommen aus irgendwelchen Exemplaren.

- **Mehrere Exemplare wünschen:** Im Dialog der Position (Stift) trägst du das
  erste bei **„Bestimmtes Exemplar (ID)“** ein, weitere bei **„Weitere
  bestimmte Exemplare (ID)“**, durch Kommas getrennt: `0043, 0044`. Das
  zweite Feld gibt es, sobald die Position mehr als ein Stück hat. Dann steht
  an der Zeile „Exemplare 0042 (Cordial XLR), 0043 (Cordial XLR), 0044
  (Cordial XLR) – 3 von 10 Stück“.
- **Nicht mehr Exemplare als Stücke:** Wünschst du mehr, als die Position
  Stücke hat, lehnt Rentalars das ab („3 Exemplare sind gewünscht, die Position
  hat aber nur 2 Stück. Jedes gewünschte Exemplar nimmt ein Stück.“).
  Alle gewünschten Exemplare müssen zum Produkt gehören.
- **Auf der Packliste** stehen genau diese Exemplare, mit ihrem Lagerplatz,
  als „Gewünscht: …“ – auf dem Bildschirm, im PDF und in der Schnittstelle.
  Im Dialog „Exemplare wählen“ sind sie als „vom Planer gewünscht“ markiert
  und stehen oben, und bei der Ausgabe nimmt Rentalars sie als erste (Abschnitt
  10), sofern sie einsatzbereit und nicht bei einem anderen Projekt sind.
- **Löschst du ein gewünschtes Exemplar** (aus dem Bestand), rückt das nächste
  gewünschte der Position an seine Stelle; die Wünsche bleiben sichtbar und
  zählen weiter, auch für die Hinweise auf Doppelwünsche in anderen Projekten.
- **Gesperrt oder ausgemustert:** Ein gewünschtes Exemplar, das im Zeitraum der
  Position gesperrt ist, meldet die Planung mit „… ist in diesem Zeitraum
  gesperrt: …“. Wird es ausgemustert, bleibt der Wunsch bestehen, und die
  Planung warnt („Exemplar … ist ausgemustert“); er wird nicht stillschweigend
  gelöscht.
- **Noch nicht möglich:** Die Bestandteile eines Sets lassen sich nicht einzeln
  wünschen. Fügst du dasselbe Paket noch einmal mit einem anderen Exemplar
  hinzu, entsteht eine zweite Position (nutze stattdessen „Weitere bestimmte
  Exemplare“). Und wer eine Position wirklich in zwei Zeilen teilen will –
  „1/10“ als eigene Position mit eigener Menge –, braucht dafür zwei Positionen,
  die er selbst im Gleichschritt hält (Abschnitt 17).

#### Zubehör und Ersatz in der Planung

Hat ein Produkt der Planung Zubehör (Abschnitt 5, „Zubehör und Ersatz“), zeigt
die Planung über den Positionen den Kasten **„Zubehör und Ersatz,
an die du denken solltest“** („Vorschläge für die Planung“). Er lädt nach der
Seite; er hält nie etwas auf und ändert nie von selbst etwas.

- **Zubehör, das noch nicht geplant ist.** Für jedes Produkt der Planung mit
  Zubehör nennt der Kasten das Zubehör, das weder als Position noch in einem
  Set der Planung steht – „gehört zu Lautsprecher …“, „empfohlen“ oder
  „vorgeschrieben“, und wie viel davon im Zeitraum frei ist (die Zahl nur mit
  dem Sonderrecht „Verfügbarkeit von Material sehen“). Die vorgeschlagene
  **Menge** ist die Menge des Produkts mal „Stück je Stück“, aufgerundet: Sechs
  Lautsprecher mit je einem Kabel ergeben sechs Kabel. Nennen **mehrere
  Produkte** der Planung dasselbe Zubehör, **summiert** Rentalars die Mengen
  und rundet einmal auf (3 × A und 2 × B mit demselben Kabel ergeben fünf, nicht
  drei); das Zubehör ist „vorgeschrieben“, sobald es eines der Produkte
  verlangt. Ist das Zubehör schon geplant, aber in einer zu kleinen Menge,
  schlägt der Kasten es für den **Rest** noch einmal vor. Du kannst die Menge
  ändern und mit **„Hinzufügen“** eine Position anlegen, in der Teilgruppe des
  Produkts; ein zweiter Klick legt nichts doppelt an („… ist schon in der
  Planung“). **„Verwerfen“** blendet den Vorschlag **für dieses Projekt** aus.
- **Ersatz bei einer Fehlmenge.** Ist eine Position knapp oder ihr Produkt
  deaktiviert, nennt der Kasten die Ersatzprodukte, mit der Zahl der Stücke,
  die im Zeitraum der Position frei sind, und ob sie den Bedarf **decken** oder
  **nur teilweise**. **„Ersatz hinzufügen“** legt den Ersatz als **neue**
  Position an (Menge: fehlende Stücke mal „Stück je Stück“); die knappe Position
  bleibt unverändert – ob du sie verkleinerst oder löschst, entscheidest du.
  Ersatz, der schon in der Planung steht, schlägt der Kasten nicht noch einmal
  vor. Ersatz sieht nur, wer das Sonderrecht „Verfügbarkeit von Material sehen“
  hat.
- **Verworfenes** bleibt im Kasten gezählt („2 Vorschläge sind in diesem
  Projekt verworfen“) und kommt mit **„Wieder anzeigen“** zurück; **„Alle
  Vorschläge in diesem Projekt verwerfen“** räumt den Kasten auf. Pro Art
  zeigt Rentalars höchstens zwölf Vorschläge auf einmal, die Ersatzvorschläge
  höchstens für acht knappe Positionen; ist etwas erledigt, kommen die
  nächsten.
- **Der Kasten braucht einen Moment.** Er lädt sich erst neu, wenn du etwa 0,6
  Sekunden nichts mehr an der Planung geändert hast, und prüft pro
  Anfrage höchstens sechs Ersatzprodukte. Während eine Anfrage läuft, sind die
  Knöpfe gesperrt. Ein Screenreader liest nicht jede Änderung vor, sondern nur
  eine Statuszeile, wenn sich die Zahl der Vorschläge ändert.
- **Beim Angebot** (Abschnitt 11, „Ein Dokument erstellen“) zeigt Rentalars
  dieselben Hinweise, sobald du die Art „Angebot“ wählst – nur als Hinweis, es
  wird nichts hinzugefügt.

#### Die Ampel

| Anzeige | Bedeutung |
|---|---|
| 🟢 **frei** | Es reicht. |
| 🟡 **knapp** | Es reicht – aber die **Option** eines anderen Projekts will dasselbe Material. Wird sie bestätigt, fehlt etwas. |
| 🔴 **Fehlmenge 2** | Es reicht nicht; so viele Stück fehlen. |
| ⚪ **nicht geprüft** | Nebenkosten, Aufpreis, Zumietung – nichts, was ausgehen kann. |

Darunter steht in kleiner Schrift, woraus sich das ergibt:
„Bestand 12, anderswo 8, optional 6“ heißt: zwölf vorhanden, acht davon in
diesem Zeitraum fest für andere Projekte reserviert, sechs weitere durch
Optionen vorgemerkt.

**Eine Fehlmenge verhindert das Speichern nicht.** Du kannst überbuchen –
manchmal weiß man eben, dass noch etwas dazukommt. Die Position bleibt rot,
oben auf der Seite steht, wie viele Stück insgesamt fehlen, und die Seite
„Fehlbestände“ führt sie auf, bis die Lücke geschlossen ist: Menge
verringern, Zeitraum verschieben oder zumieten (Abschnitt 9).

Die Ampel – in der Planung und im Dialog einer Position – und die Hinweise
auf fehlendes Material sieht nur, wer das Sonderrecht
**„Verfügbarkeit von Material sehen“** hat (Abschnitt 16, „Rollen und
Rechte“). Alle mitgelieferten Rollen außer Crew haben es.

#### Eine Position bearbeiten

Am Ende jeder Zeile stehen fünf Symbole: **optional**, **Alternative**
(beide unten, „Optionale und alternative Positionen“), **Stift**,
**Kopieren** und **Papierkorb**. Der Stift öffnet einen Dialog:

- **Bezeichnung** – so, wie sie auf Dokumenten erscheinen soll.
- **Menge**.
- **Teilgruppe** – verschiebt die Position.
- **„Zählt als“** – normal, optional oder Alternative; bei einer
  Alternative darunter **„Alternative zu“** mit der Position, die sie
  ersetzen könnte (unten, „Optionale und alternative Positionen“).
- **Von / Bis** – nebeneinander in einer Zeile: ein eigener Zeitraum für
  diese Position, wenn sie früher raus muss oder später zurückkommt als der
  Rest. Die Verfügbarkeit wird für genau diesen Zeitraum geprüft; der Dialog
  zeigt sie während des Tippens – und dazu, wie viele **Miettage** sich aus
  dem Zeitraum ergeben (Abschnitt 8).
- **Bestimmtes Modell**, **Bestimmtes Exemplar (ID)** und – bei einer
  Position mit mehr als einem Stück – **Weitere bestimmte Exemplare (ID)** –
  der Wunsch von oben, hier auch nachträglich einzutragen oder zu entfernen.
- **Notiz** – erscheint auf der Packliste („mit Torblende“).
- **Miettage**, **Einzelpreis**, **Rabatt in Prozent**, **Staffelfaktor von
  Hand** – siehe Abschnitt 8. Nur mit Preisrecht.
- **„Verkaufen statt vermieten“** – nur an einer Position,
  die ein Mietprodukt schon verkauft: Sie behält ihren Preis und bleibt
  bearbeitbar; nimmst du den Haken heraus, wird das Material zum Preis des
  Produkts vermietet. Neu verkauft wird ein Mietprodukt nicht – dafür
  gibt es Verkaufsprodukte (Abschnitt 5, „Ein Produkt anlegen“).

Der Papierkorb löscht die Position – nach einer Rückfrage mit „Ja,
löschen“. Ist ihr Material schon ausgegeben, geht das nicht mehr.

**Position duplizieren.** Das Doppelblatt-Symbol in der Zeile („Position
duplizieren“) legt eine Kopie direkt darunter an, in derselben Teilgruppe:
mit Produkt, Menge, Zeitraum, Preis und Rabatt, Notiz, „Zählt als“ und
gewünschtem Modell – nicht aber mit einem gewünschten Exemplar, das ja nur
einmal da ist. Praktisch für dieselben Scheinwerfer in einem zweiten
Zeitraum oder als Alternative. Eine Zumietung, die eine Fehlmenge deckt,
lässt sich nicht duplizieren.

#### Mehrere Positionen auf einmal

Vor jeder Position steht ein Kästchen. Hake die Positionen an, die du
gemeinsam ändern willst; das Kästchen im Kopf einer Teilgruppe wählt alle
Positionen dieser Teilgruppe aus (ebenso bei „Ohne Teilgruppe“ und den
Aufpreisen). Sobald eine Position gewählt ist, erscheint unten eine Leiste
mit der Zahl der gewählten Positionen. Damit machst du sie

- **„Optional“** oder setzt sie mit **„Nicht mehr optional“** zurück,
- **„Als Alternative zu …“** einer anderen Position – ein Fenster fragt,
  zu welcher,
- unter **„Verschieben nach …“** in eine andere Teilgruppe, auch in eine
  Untergruppe oder nach „ohne Teilgruppe“, mit „Verschieben“,
- mit einem **Rabatt** in Prozent („Rabatt setzen“, nur mit Preisrecht),
- weg mit **„Löschen“** – nach einer Rückfrage.

Positionen, bei denen das nicht geht, bleiben unverändert; Rentalars nennt
sie mit dem Grund („Unverändert geblieben: …“) – etwa weil ihr Material
schon ausgegeben ist, weil andere Teilprojekte Stücke davon übernehmen
oder weil es eine Zumietung ist, die zu einer anderen Position gehört und
mit ihr wandert. Ein prozentualer Aufpreis bekommt keinen Rabatt und
bleibt bei dem, worauf er sich bezieht. Jede Änderung steht wie gewohnt
im Verlauf. **„Auswahl aufheben“** nimmt alle Haken heraus.

#### Optionale und alternative Positionen

Nicht nur eine ganze Teilgruppe, auch eine einzelne Position kann ein
Zusatzangebot oder eine Variante sein: der zweite Nebel, die größere
Leinwand statt der kleinen. Am schnellsten geht es mit den beiden
Symbolen am Ende der Zeile, vor dem Stift:

- **optional** schaltet die Position auf optional und wieder zurück. Ist
  das Symbol orange umrandet, ist sie optional.
- **Alternative** öffnet ein Fenster: Darin wählst du, welche Position die
  Alternative ersetzen könnte. Diese Angabe ist Pflicht.

Dasselbe geht im Dialog der Position unter **„Zählt als“**:

- **normal** – Teil des Projekts.
- **optional** – ein Zusatz, den der Kunde dazunehmen kann.
- **Alternative** – eine Variante zu einer anderen Position, die du unter
  „Alternative zu“ wählst.

Eine optionale oder alternative Position trägt in der Planung ein gelbes
Schild „optional“ oder „Alternative“ und zeigt ihren Preis mit dem Vermerk
„nicht in der Summe“. Unter einer Alternative steht, was sie ersetzen
könnte: in der Planung und in der Preisübersicht „Alternative zu „8 ×
LED-Scheinwerfer““, im Angebot und in der Auftragsbestätigung „Alternative
zu Pos. 3“. Löschst du die Position, zu der eine Alternative gehört, wird
die Alternative zu einer optionalen Position. Ältere Alternativen haben noch keine solche Angabe; bearbeitest du eine,
fragt der Dialog danach. Sie

- zählt **nicht** zur Zwischensumme ihrer Teilgruppe und nicht zur
  Projektsumme; die Summen nennen sie eigens („Optionale Positionen, nicht
  enthalten“, „Alternative Positionen, nicht enthalten“);
- **reserviert nur wie eine Option**: Sie macht andere Projekte „knapp“,
  nimmt ihnen aber nichts weg (Abschnitt 9);
- steht **nicht auf der Packliste** und **nicht auf der Rechnung**;
- steht gekennzeichnet in der Preisübersicht, im Angebot und in der
  Auftragsbestätigung (Abschnitt 11).

Nimmt der Kunde sie, stellst du sie auf „normal“. Ein prozentualer Aufpreis
rechnet nur dann auf eine optionale Position, wenn er selbst optional ist.
Nicht optional und keine Alternative werden können eine Zumietung, die
eine Fehlmenge deckt (sie zählt wie ihre Position), eine Position, deren
Material schon ausgegeben ist, und eine, von der andere Teilprojekte
Stücke übernehmen.

#### Teilgruppen

Teilgruppen gliedern ein Projekt – nach Gewerk, nach Bühne, nach Tag. Jede
hat eine eigene Zwischensumme. Teilgruppen lassen sich **schachteln**, bis
zu drei Ebenen tief: „Licht › Front-Traverse › Traverse 1“ (unten,
„Geschachtelte Teilgruppen“).

- **Anlegen:** in der Zeile direkt unter „Ohne Teilgruppe“ (unten, „Unter
  den Teilgruppen“) den Namen ins Feld „Neue Teilgruppe“ tippen, daneben
  „auf der obersten Ebene“ lassen oder „in …“ einer anderen wählen,
  „Teilgruppe hinzufügen“.
- **Bearbeiten** (Stift in der Kopfzeile der Gruppe): Name, Beschreibung,
  **„Übergeordnete Teilgruppe“**, eigene Miettage, Rabatt oder
  Pauschalpreis (Abschnitt 8) und **„Zählt als“**:
  - **normal** – Teil des Projekts.
  - **optional** – ein Zusatzangebot („Nebel und Effekte“). Wird mit
    Zwischensumme gezeigt, zählt aber **nicht** zur Projektsumme und
    reserviert Material nur als Vormerkung.
  - **Alternative** – eine zweite Variante zu einer anderen Gruppe, die du
    unter „Alternative zu“ wählst; verhält sich wie „optional“. Eine
    Teilgruppe kann nur Alternative zu einer Teilgruppe sein, nicht zu
    einer Position, und nicht zu einer Gruppe über oder unter ihr.
- **Optional** und **Alternative** gehen auch schneller, mit den beiden
  Symbolen in der Kopfzeile der Gruppe vor dem Stift – wie bei einer
  Position (oben). Im Kopf einer alternativen Gruppe steht dann
  „Alternative zu „Licht Variante A““.
- **Kopieren** (Doppelblatt-Symbol): legt die Gruppe samt Positionen und
  Untergruppen noch einmal an, am Ende derselben Obergruppe.
- **Löschen** (Papierkorb): Positionen und Untergruppen wandern eine Ebene
  nach oben – in die Obergruppe; bei einer Teilgruppe der obersten Ebene
  kommen die Positionen nach „Ohne Teilgruppe“ und die Untergruppen auf die
  oberste Ebene. Die Rückfrage sagt, wohin.

#### Geschachtelte Teilgruppen

Ziehe eine Teilgruppe am **Griff** neben ihrem Namen in eine andere hinein,
aus ihr heraus oder an eine andere Stelle. Mit der Tastatur: Griff
fokussieren, ↑ und ↓ ändern die Reihenfolge, → schiebt die Teilgruppe in
die darüberstehende, ← holt sie eine Ebene höher. Im Dialog „Teilgruppe
bearbeiten“ wählst du alternativ die **„Übergeordnete Teilgruppe“**; die
Teilgruppe wandert dann mit ihren Positionen und Untergruppen dorthin, als
letzte Untergruppe. Mit dem Pfeil vor dem Namen klappst du Untergruppen
ein und wieder aus. Tiefer als drei Ebenen und in sich selbst lässt sich
eine Teilgruppe nicht schieben; Rentalars sagt es und lässt sie, wo sie
war.

- Eine **Obergruppe** kann eigene Positionen haben – das Lichtpult in
  „Licht“ etwa. Sie stehen vor ihren Untergruppen; die **„Zwischensumme …
  mit Untergruppen“** steht unter der letzten Untergruppe.
- **Rabatte:** Erst wirkt der Rabatt der Untergruppe, dann der der
  Obergruppe auf das Ergebnis; ein **Pauschalpreis** der Obergruppe ersetzt
  alles darunter (Abschnitt 8).
- **Optional:** Untergruppen einer optionalen Teilgruppe sind ebenfalls
  optional, die einer alternativen ebenfalls Alternative – die Planung
  schreibt „optional wie die Obergruppe“. Eine Untergruppe, die selbst
  optional ist, zählt nicht zur Summe ihrer Obergruppe.
- **Miettage:** Hat eine Untergruppe keine eigenen, gelten die der
  nächsten Obergruppe, die welche hat.

Preisübersicht, Dokumente, Packlisten, Vorlagen und das Duplizieren
übernehmen die Gliederung.

#### Sortieren

Fasse eine Position an den sechs Punkten am Zeilenanfang und ziehe sie an
eine andere Stelle – auch in eine andere Teilgruppe. Ohne Maus geht es auch:
Springe mit der Tab-Taste zu den sechs Punkten und verschiebe die Position
mit den Pfeiltasten nach oben oder unten. In eine andere Teilgruppe kommt
sie über „Bearbeiten“ – mehrere auf einmal über die Auswahl (oben,
„Mehrere Positionen auf einmal“). Eine Zumietung, die eine Fehlmenge
deckt, wandert mit ihrer Position. Ganze Teilgruppen verschiebst du an
ihrem Griff (oben, „Geschachtelte Teilgruppen“).

#### Unter den Teilgruppen

Direkt unter „Ohne Teilgruppe“, über dem Personal, steht eine Zeile mit
allem, was du außer Produkten hinzufügen kannst – in dieser Reihenfolge:

- **neue Teilgruppe**: Name, Ebene, „Teilgruppe hinzufügen“ (oben,
  „Teilgruppen“);
- **„Position ohne Produkt“**, daneben **„Textposition
  einfügen“**, **„Exemplare scannen“** (Abschnitt 4, „Scannen“:
  Etikett lesen, und das Exemplar kommt als Wunsch in die Planung) und, in
  einem Gesamtprojekt mit Teilprojekten, **„Aus anderem Teilprojekt
  übernehmen“** (unten, „Teilprojekte“);
- **„MVR-Datei importieren“** (unten).

Produkte selbst fügst du im Feld unter jeder Teilgruppe hinzu (oben, „Eine
Position hinzufügen“). Am Telefon bricht die Zeile um, und die Felder
nehmen die ganze Breite.

#### Position ohne Produkt

Für Einmaliges, das kein Produkt verdient: „Bühnenpodest vom Veranstalter“,
„Anfahrt Sonderfahrzeug“. Der Knopf **„Position ohne Produkt“** unter den
Teilgruppen fragt nach Bezeichnung, Menge, Einheit, Preis und Steuerart.
Solche Positionen werden nicht auf Verfügbarkeit geprüft.

#### Textposition einfügen

**„Textposition einfügen“** fügt eine Position nur mit Text ein –
ohne Produkt, Menge, Preis, Rabatt und Zeitraum: eine Überschrift, ein
Hinweis wie „Aufbau durch den Veranstalter“, ein Absatz zwischen den
Positionen. Der Dialog fragt nach dem Text und, wenn du willst, einem
weiteren Text. Die Position steht in der Planung, im Angebot, in der
Auftragsbestätigung, in der Rechnung, der Stornorechnung und in der
Preisübersicht (Seite, PDF und CSV) als Zeile ohne Betrag; sie lässt sich
verschieben, kopieren, duplizieren, aufteilen und in Vorlagen übernehmen
wie jede Position. Nicht berücksichtigt wird sie bei Packliste und
Lieferschein, Verfügbarkeit und Fehlbestand, Übernahmen, Nachkalkulation, in
den Positionszeilen der XRechnung und in DATEV, in Summen, Steuer und
Gruppenanteilen; „optional“, „Alternative“ und Rabatt für mehrere Positionen
überspringen sie. Ob eine Position eine Textposition ist, lässt sich nur
beim Anlegen entscheiden (API: `"is_text": true`). Eine Textposition kann
weder „Alternative zu“ noch Ziel eines prozentualen Zuschlags sein.

#### Warnungen und Verweise in der Planung

In der Planung gilt:

- **Rabatt über dem Höchstwert:** Tippst du einen höheren Rabatt, als die
  Position (Gruppe, Personal, Fahrzeug) zulässt, bleibt deine Eingabe stehen,
  abgerechnet wird der Höchstwert, und eine Warnung sagt es: „angerechnet
  werden 20 %“. Im Dialog erscheint der Hinweis schon unter dem Feld; die API
  liefert `warnings` mit Status 2xx. Der Gesamtrabatt (unten) hat keinen
  Höchstwert, Duplikate und Gruppenkopien warnen nicht.
- **Veranstaltungsende:** Endet die Veranstaltung nach „Material zurück
  bis“, warnt das Projektformular schon beim Eintippen und nach dem
  Speichern („Die Veranstaltung endet nach „Material zurück bis“. Prüfe den
  Zeitraum.“), ebenso beim Verschieben im Kalender oder Zeitstrahl und die
  API (`warnings`). Nichts wird verhindert; Servicefälle haben die Warnung
  nicht.
- **Produktnummer als Verweis:** In der Planung (und im Titel des
  Positionsdialogs) führt die Nummer zum Produkt – mit dem Recht, Produkte zu
  lesen. Dessen Kasten „Verfügbarkeit“ ist mit dem Mietzeitraum des
  Projekts vorbelegt, mit dem Hinweis „Zeitraum des Projekts 2027-0001 ·
  Zurück zu …“; ein von dir eingetippter Zeitraum gilt vor dem Vorschlag.
- **Gleiches Aussehen der Eingabezeilen:** Material, Personal und Logistik
  haben dieselbe Zeile – Felder 40 px hoch in einer Zeile, Hilfetexte
  darunter, Schaltflächen als Gruppe, unter 720 px untereinander.

#### Die offene Planung bleibt aktuell

Dass die Seiten eines Projekts Änderungen von selbst folgen, steht in
Abschnitt 2 („Rückfragen und Seiten, die sich selbst aktualisieren“). Das gilt auch für den **Bestand**: Verknüpfst du in einem zweiten Tab
ein Modell mit einem Produkt, sperrst du ein Exemplar, ändert ein Kollege eine
Position in einem anderen Projekt, die dasselbe Material braucht – dann
aktualisieren sich in einer **offenen Planung** die Spalte „Verfügbarkeit“,
die Hinweise zu den Wünschen und die Hinweise über den Positionen, ohne dass
die Seite neu lädt. Was du tippst, die Stelle, an der du in der Seite stehst,
und offene Dialoge bleiben. Es geschieht, wenn du **in den Tab zurückkehrst** und
mit der Abfrage, die die Seite ohnehin etwa alle 20 Sekunden macht – die Frage
selbst ist billig und rechnet erst, wenn sich am Bestand etwas geändert hat.
Zwischen zwei Aktualisierungen liegen **mindestens 20 Sekunden**; kommt
währenddessen eine weitere Änderung, folgt danach genau eine weitere. Eine
Zelle, in der du gerade stehst, bleibt, wie sie ist, und wird später
aktualisiert; hängt eine Anfrage länger als 15 Sekunden, gibt der Tab sie auf
und fragt beim nächsten Mal neu. Das gilt nur, wenn du das Sonderrecht
„Verfügbarkeit von Material sehen“ hast; nicht erfasst sind Häkchen auf
Packlisten.

**Gespeichert, und die Seite bleibt, wo sie ist.** Speicherst du eine
Teilgruppe, eine Gruppe oder eine Position, springt die Seite nicht
mehr an eine andere Stelle, und aufgeklappte Bereiche bleiben aufgeklappt.

#### MVR-Datei importieren

Der Lichtdesigner schickt seinen Plot aus Vectorworks, grandMA3, Capture
oder WYSIWYG als **MVR-Datei**? Dann musst du die Scheinwerfer nicht
abzählen. **„MVR-Datei importieren“** unter den Teilgruppen:

1. Die MVR-Datei wählen, **„Datei lesen“**. Rentalars zählt die Geräte je
   Gerätetyp und Modus – Scheinwerfer, aber auch Traversen, Leinwände und
   Projektoren, auch in verschachtelten Gruppen des Plots.
2. Unter **„Produkte den Gerätetypen zuordnen“** steht je Typ die gezählte
   Menge und ein vorgeschlagenes Produkt. **„gemerkt“** heißt: Dieses
   Produkt hat jemand schon einmal für denselben Typ gewählt (**„gemerkt
   für einen anderen Modus“**: für denselben Typ in einem anderen Modus);
   **„ähnlich“** heißt: Der Name passt. Du kannst jeden Vorschlag ändern,
   unter **„anderes Produkt:“** ein anderes suchen oder den Typ mit **„nicht
   übernehmen“** auslassen. Dienstleistungen, Nebenkosten, Aufpreise,
   Zumietungen und Fahrzeuge schlägt Rentalars nie vor.
3. Unter **„Wohin die Positionen kommen“** eine vorhandene Teilgruppe
   wählen, „ohne Teilgruppe“ oder **„eine neue Teilgruppe“** mit Namen.
4. **„Positionen hinzufügen“** legt je Typ eine Position mit der gezählten
   Menge an – mit Preis, Rabatt und Ampel wie von Hand hinzugefügt. Alles
   oder nichts: Klappt eine Position nicht, entsteht keine.

Deine Zuordnung merkt sich Rentalars für den nächsten Plot.

**Die Datei bleibt beim Projekt.** Schon beim Lesen legt Rentalars die
MVR-Datei in den Dateien des Projekts ab (Reiter „Dokumente“, Abschnitt
11, „Dateien des Projekts“). Ihr Name beginnt mit Datum und Uhrzeit, etwa
`20261013-221530_Rig.mvr` – so stehen die Plots eines Projekts in der
Reihenfolge, in der sie kamen. Die Datei hat keine Dokumentart und ist für
die Crew nicht sichtbar; beides lässt sich am Stift der Datei ändern.
„Andere Datei wählen“ entfernt sie wieder. Ist die Datei größer, als
Projektdateien sein dürfen, legt Rentalars sie nicht ab und sagt es; die
Positionen kannst du trotzdem übernehmen. Eine MVR-Datei lässt sich auch
von Hand bei den Dateien hochladen.

### Zeitplanung: offene Punkte, Zeitstrahl, Phasen, Personal

Der Reiter **Zeitplanung** sammelt, was alle
wissen müssen, die am Projekt arbeiten – von oben nach unten die offenen
Punkte, den Zeitstrahl des Projekts, die Phasen mit ihrem Personal und
zuletzt die Fahrten:

- **Offene Punkte:** was noch fehlt. Ein Punkt je Zeile eintippen,
  „Notieren“. Abhaken über das Kästchen davor; Rentalars merkt sich, wer
  wann. Versehentlich notiert? Mülleimer.
- **Zeitstrahl:** das Projekt als Zeitstrahl wie unter Planung →
  Zeitstrahl (Abschnitt 15). Oben der **Mietzeitraum** in der Farbe des
  Status und, wenn eingetragen, die **Veranstaltung**; darunter jede
  **Phase** in einer eigenen Zeile, mit ihren Uhrzeiten im Balken; dann das
  **Personal** – je Person eine Zeile mit ihren Einsätzen, die Funktion im
  Balken. Du siehst das Personal wie im Personalplan (Abschnitt
  15, „Personalplan“): fest, Option und Anfrage in ihren Farben, angefragte
  Einsätze gestrichelt; abgesagt: rot schraffiert und durchgestrichen.
  Offene Plätze stehen gelb schraffiert je Funktion mit „offen“. Ist
  jemand doppelt eingeplant – auch in einem anderen Projekt –, abwesend
  oder „nicht verfügbar“, ist der Einsatz **rot ausgefüllt**, und vor dem
  Namen steht „!“. Darfst du das Personal einsehen, steht über den
  Einsätzen jeder Person ihre Verfügbarkeit, schraffiert. Fährst du mit
  der Maus über einen Balken, nennt er die genauen Zeiten, Person,
  Funktion und Stand der Anfrage; die Legende darunter ist die des
  Personalplans. Wer das Personal sehen darf, kommt über den Namen zur
  Person. Der Zeitstrahl
  öffnet mit dem Mietzeitraum – bis zu 10 Tage in Stundenspalten, längere
  Projekte in Wochen (höchstens zwölf). „Tage“, „Wochen“, „‹ früher“,
  „später ›“ und „Von“ funktionieren wie in der Planung, und seitliches
  Scrollen bis zum Rand lädt die nächsten Stunden nach; anders als dort
  merkt sich Rentalars die Wahl nicht – beim nächsten Öffnen zeigt er
  wieder den Mietzeitraum. Liegt eine Phase oder ein Einsatz außerhalb der
  gezeigten Tage, bleibt die Zeile, ohne Balken. In den Stundenspalten
  ziehst du Mietzeitraum, Veranstaltung und Phasen – auch die
  Einsätze der Personen und die offenen Plätze – an eine andere Zeit
  oder an einem Ende länger oder kürzer; ein Klick auf ihren Balken öffnet
  ein Fenster, in dem du die Zeiten eintippst (Abschnitt 15, „Termine im
  Zeitstrahl verschieben“). Ist eine Person die einzige ihrer Phase, geht
  die Phase mit (unten, „Personen im Zeitstrahl ziehen“).
- **Phasen:** **Planungen und Besprechungen**, **Packen**, Anfahrt,
  Aufbau, Probe, Veranstaltung, Abbau, Rückfahrt, **Nachbereitung**,
  Reinigung und zuletzt Sonstiges – in dieser Reihenfolge stehen sie in der
  Auswahl; jede mit Zeitraum und Ort, auf Wunsch mit eigener Bezeichnung
  („Aufbau Halle 3“, „Showtag 2“). Die Phasen stehen auch
  im Überblick für die Crew, im Kalender und im Zeitstrahl. Eine
  Veranstaltung über mehrere Tage oder in mehreren Teilen bildest du so ab:
  eine Phase je Teil.

  **Womit eine neue Phase beginnt**. „Neue Phase“ und der
  Dialog „Neue Phase …“ schlagen vor: den Zeitraum, den du im Formular des
  Personals oder eines Fahrzeugs schon eingetragen hast, wenn er vom
  Mietzeitraum abweicht; sonst den Anschluss an die bisher letzte Phase –
  die neue beginnt dort, wo jene endet, solange das im Mietzeitraum liegt,
  sonst mit dem Beginn des Mietzeitraums. Die neue Phase dauert
  zunächst **höchstens acht Stunden**: ab dem Beginn des Mietzeitraums oder dort, wo die
  letzte Phase endet, nie über das Ende hinaus – ist das Projekt kürzer,
  endet sie mit ihm. Das ist nur der Vorschlag; länger machst du sie in der
  Seite, im Dialog oder über die API von Hand. Ein von dir über mehrere Tage
  eingetragener Zeitraum beginnt mit **einer Stunde am ersten Tag**;
  meist änderst du dann nur noch die Uhrzeiten. Eine Phase über
  mehrere Tage legst du bewusst an, mit dem Tag ihres Endes. Eine Phase mit falschem Zeitraum korrigierst du in der Zeitplanung, mit dem
  Haken „Personal und Fahrzeuge dieser Phase mitverschieben“ – dann folgen
  die Buchungen.
  - **„Planungen und Besprechungen“** ist für Ortstermine und
    Technikbesprechungen, auch Wochen vor dem Mietzeitraum.
  - **„Packen“** – Material zusammenstellen und verladen. Der Verladetermin einer Packliste heißt
    „Verladen“ (Abschnitt 10).
  - **„Nachbereitung“** ist die Zeit nach der Rückkehr: Material vom
    Transport auspacken, Eingangskontrolle, einlagern.

  Im Formular einer Phase – „Neue Phase“, Bearbeiten und der Dialog
  „Neue Phase …“ – sind in den Kalendern der Mietzeitraum (grau) und die
  Veranstaltung (grün) schraffiert; die Legende darunter nennt die Zeiten
  (Abschnitt 2, „Zeiträume eingeben“).

  **Personalplätze gleich mit anlegen**. „Neue Phase“ und der
  Dialog „Neue Phase …“ haben den Kasten **„Personalplätze
  (optional)“**: je Zeile eine **Funktion** und die Zahl der **Plätze**,
  „Weitere Funktion“ für noch eine Zeile, der Papierkorb für eine weniger
  – etwa „Stagehand, 4“ und „Lichttechniker, 1“. Beim Speichern der Phase
  entstehen so viele **offene Plätze** in ihr, mit ihrem Zeitraum; die
  Personen setzt du danach mit „Personal für diese Phase“ ein (unten).
  Legst du die Phase im Dialog aus der Planung an, steht ihr Personal dort
  sofort mit da.

  Eine Phase **außerhalb des Mietzeitraums** – der Ortstermin drei Wochen
  vorher – steht im Kalender und im Zeitstrahl an ihrem Tag, im Zeitstrahl
  in der Zeile ihres Projekts. Das Material belegt sie nicht; dafür zählt
  nur der Mietzeitraum. Deshalb **fragt Rentalars nach**, wenn du eine
  Phase speicherst, die ganz oder teilweise außerhalb des Mietzeitraums
  liegt (unten, „Phase außerhalb des Mietzeitraums“) – nur bei
  „Planungen und Besprechungen“ nie.
- **Personal je Phase:** Unter jeder Phase steht, wer dort arbeitet –
  Funktion, Person oder „offen“, die Stunden und, wenn er vom Zeitraum der
  Phase abweicht, der eigene Zeitraum. Mit **„Personal für diese Phase“**
  planst du direkt für die Phase, Funktion für Funktion – wie
  bei „Neue Exemplare“ eine Seriennummer je Stück:

  1. **„1. Funktionen und Plätze“:** je Zeile eine Funktion und die Zahl
     ihrer Plätze; „Weitere Funktion“ fügt eine Zeile an (höchstens zehn),
     der Papierkorb nimmt eine weg. Die offenen Plätze, die die Phase
     schon hat, stehen hier bereits.
  2. **„2. Personen“:** je Platz ein Feld, **„Platz 1“**, „Platz 2“ …;
     es schlägt die Personen mit dieser Funktion vor und sagt dazu, ob
     jemand zur Zeit der Phase schon anderswo eingeplant, abwesend oder
     „nicht verfügbar“ ist. Ein leerer Platz bleibt offen.

  **„Einplanen“** plant alle für den Zeitraum der Phase ein. Eine
  gewählte Person besetzt zuerst einen offenen Platz ihrer Funktion in
  der Phase – so wird nichts doppelt geplant –; Plätze darüber hinaus
  kommen dazu. Mit **„Fest eingeplant (ohne Anfrage)“** werden die
  gewählten Personen ohne Anfrage eingeplant (Abschnitt 12, „Anfragen:
  Zusage oder Absage“). Ohne JavaScript geht es in zwei Schritten: nach
  den Funktionen „Weiter zu den Personen“.

  Personal, das zu keiner Phase
  gehört, steht darunter unter **„Personal ohne Phase“**; „Zur Planung“
  führt zu seinem Block in der Planung (Abschnitt 12, „Personal im Projekt
  einplanen“). Planst du dort Personal und fehlt die Phase noch, legst du
  sie mit **„Neue Phase …“** in der Phasenauswahl gleich an, ohne in die
  Zeitplanung zu wechseln.

  **Personal einer Phase ändern.** Darfst du das Personal planen, steht an
  jeder Zeile der Stift: Er öffnet den Personaldialog der Planung. Dort
  besetzt du einen offenen Platz mit einer Person („Mit einer Person
  besetzen“) oder änderst Person, Funktion oder Zeiten. Rentalars nennt an
  der Zeile und nach dem Speichern, was nicht passt – Überschneidung,
  Abwesenheit, Verfügbarkeit. Mit **„anfragen“** fragst du die Person an,
  mit „eintragen: zugesagt“ oder „abgesagt“ trägst du ihre Antwort ein,
  mit dem Papierkorb entfernst du die Position. Danach steht die
  Zeitplanung wieder da, mit dem neuen Stand.
- **Fahrten:** jede Fahrt des Projekts, die Rentalars aus Phasen und
  Anschriften ermittelt, und eigene Fahrten, mit Zeit, Strecke, den
  Fahrzeugen der Logistik darauf (unten, „Logistik“) und dem Link
  **„Route in Google Maps“** – ab deinem Standort über die Zwischenstopps
  zum Ziel (unten, „Die Fahrten eines Projekts“).

Die Zeitplanung hat keinen eigenen Kasten **„Veranstaltungsort“**. Der Ort steht im Kopf des Projekts – wer Kunden
sehen darf, kommt über seinen Namen zu seiner Seite mit Anschrift, Zufahrt,
Strom und Lageplan/Hallenplan –, und mit allen Hinweisen im Reiter
„Überblick“, den auch die Crew sieht (Abschnitt 12).

**Phase außerhalb des Mietzeitraums.** Liegt eine Phase ganz oder
teilweise außerhalb des Mietzeitraums, wird sie trotzdem gespeichert.
Rentalars fragt dann – auf der Zeitplanung oder, beim Dialog „Neue Phase
…“, im Dialog selbst –: „Mietzeitraum auf Fr 23.10. 14:00 – Di 27.10. 18:00
erweitern?“ Vorgeschlagen ist der bisherige Mietzeitraum, gerade so weit
verlängert, dass er die Phase umfasst.

- **„Erweitern“** ändert den Mietzeitraum wie „Projekt bearbeiten“:
  Positionen mit dem bisherigen Mietzeitraum übernehmen den neuen, alle im
  Projekt Eingeplanten werden benachrichtigt, und fehlt dadurch Material,
  sagt Rentalars es („Im neuen Mietzeitraum fehlen 2 Stück. Sieh dir die
  rot markierten Positionen an.“).
- **„Nicht erweitern“** lässt alles, wie es ist. Die Phase bleibt
  gespeichert; Material ist weiter nur für den Mietzeitraum reserviert.

Phasen der Art **„Planungen und Besprechungen“** fragen nie – ein
Ortstermin Wochen vorher soll kein Material blockieren. Bei einem
**Teilprojekt** muss der neue Mietzeitraum im Gesamtprojekt liegen; sonst
nennt Rentalars den Mietzeitraum des Gesamtprojekts und bietet kein
„Erweitern“ an – erweitere dann zuerst dessen Mietzeitraum.

**Eine Phase verschieben.** Gehört Personal zu einer Phase, steht im
Formular der Phase **„Personal dieser Phase mitverschieben“** (angehakt) –
gehören auch Fahrzeugbuchungen dazu, **„Personal und Fahrzeuge dieser Phase
mitverschieben“**; die Buchungen wandern nach derselben Regel wie das
Personal.
Ändert sich ihr Zeitraum, bekommt eine Personalposition mit genau dem
Zeitraum der Phase den neuen; jede andere verschiebt sich so weit wie der
Beginn der Phase und behält ihre Länge. Ändert sich nur das Ende der
Phase, bleiben diese also, wo sie sind. Vorgeschlagene Stunden wandern
mit, eingetippte Stunden, Tage und Sätze bleiben. Rentalars sagt, wie
viele Personalpositionen mitgewandert sind, und ob jemand zur neuen Zeit
schon woanders eingeplant oder nicht verfügbar ist. Wer für die alten
Zeiten angefragt war oder zugesagt hatte, bekommt von selbst eine neue
Anfrage mit den neuen Zeiten (Abschnitt 12, „Anfragen: Zusage oder
Absage“). Entfernst du eine Phase, bleibt ihr Personal mit seinem Zeitraum
erhalten – nur ohne Phase. Schneller geht das Verschieben im Zeitstrahl
darüber: Balken der Phase ziehen, im Fenster die Folgen ansehen,
„Verschieben“ (Abschnitt 15, „Termine im Zeitstrahl verschieben“).

**Personen im Zeitstrahl ziehen**. Im Zeitstrahl der
Zeitplanung ziehst du auch den Einsatz einer Person oder einen offenen
Platz – mit der Maus oder mit den Pfeiltasten, mit demselben Fenster und
demselben Recht wie bei den Phasen. Was mitgeht, entscheidet eine enge
Regel:

- **Ist die Person die einzige ihrer Phase** (offene Plätze zählen nicht
  mit), geht die **Phase** mit – samt ihren offenen Plätzen und
  Fahrzeugbuchungen. Hat der Einsatz genau die Zeiten der Phase, bekommt
  die Phase die neuen Zeiten; sonst verschiebt sie sich so weit wie der
  Beginn des Einsatzes – änderst du nur sein Ende, bleibt die Phase.
  Liegt die Phase danach außerhalb des Mietzeitraums, fragt das Fenster
  wie beim Ziehen einer Phase, ob der Mietzeitraum erweitert wird.
- **Sonst** gehen die **offenen Plätze ihrer Funktion** in derselben
  Phase (oder, ohne Phase, im Personal ohne Phase) mit, die genau
  dieselben Zeiten haben – wenn keine andere Person dieser Funktion
  dieselben Zeiten hat.
- Sonst geht nur dieser Einsatz; ebenso, wenn du einen offenen Platz
  ziehst.

Das Fenster nennt, was mitgeht und warum („Die Phase „Aufbau“ wird
mitverschoben, weil Anna Becker die einzige Person darin ist.“), mit dem
angehakten Kasten **„Phase „Aufbau“ mitverschieben“** bzw. **„Offene
Plätze als Stagehand mitverschieben“** – ohne den Haken wird nur dieser
Einsatz verschoben. Wer neu angefragt wird und welche Überschneidungen es
gibt, steht darunter; jede betroffene Person bekommt eine Nachricht
(Abschnitt 12, „Nachrichten über den Einsatz“). Im Personalplan unter
Planung verschiebst du weiterhin nur den einzelnen Einsatz (Abschnitt 15,
„Personalplan“).

**Die Fahrten eines Projekts.** Unten in der Zeitplanung – und im
Überblick für die Fahrer – stehen unter **„Fahrten“** die Fahrten, die
Rentalars aus den Phasen und Anschriften ermittelt:

| Fahrt | wann | Strecke |
|---|---|---|
| Fahrt zum Aufbau, Rückfahrt vom Aufbau | Beginn und Ende jeder Phase „Aufbau“ | Lager → Veranstaltungsort, zurück |
| Fahrt zum Abbau, Rückfahrt vom Abbau | Beginn und Ende jeder Phase „Abbau“ | ebenso |
| Abholung bei den Lieferanten | Beginn der Phase „Packen“ | Lager → jeder Lieferant, bei dem abgeholt wird → Lager |
| Rückgabe bei den Lieferanten | Beginn der Phase „Nachbereitung“ | ebenso |

Abgeholt und zurückgebracht wird nur bei Zumietungen, an denen **„Wird
beim Lieferanten abgeholt“** angehakt ist (Abschnitt 9, „Zumieten“); ohne Phase
„Packen“ oder „Nachbereitung“ zählen Beginn und Ende der Zumietung.
Optionale und alternative Positionen bleiben außen vor. Der
Veranstaltungsort ist der der Phase, sonst der des Projekts, sonst der
eingetippte Ort der Phase oder des Projekts, sonst die Lieferadresse. Das
Lager ist die „Anschrift des Lagers“ unter Einstellungen → Firmendaten und
Grundeinstellungen – leer die Anschrift der Firma.

Jede Fahrt hat den Link **„Route in Google Maps“**; er öffnet die
Routenplanung in einem neuen Tab, startet an deinem aktuellen Standort und
führt über die Zwischenstopps der Fahrt zum Ziel. Den Start der Fahrt
(etwa das Lager) zeigt die Zeitplanung weiter an, der Link aber beginnt
dort, wo du gerade bist. Fahrzeiten rechnet Rentalars nicht, Entfernungen
nur mit dem Routendienst als Vorschlag für die Kilometer eines Fahrzeugs
(unten, „Logistik“). Fehlt eine Anschrift,
sagt die Zeitplanung an der Fahrt, welche („Der Lieferant … hat noch keine
Anschrift.“); der Überblick lässt solche Hinweise weg. Darunter zeigt
„Karte anzeigen“ alle Orte der Fahrten auf einer Karte (Abschnitt 6,
„Route und Karte“). Gibt es noch keine Fahrt, steht dort, woraus Fahrten
entstehen.

**Fahrten anpassen.** Wer das Projekt bearbeiten darf, passt eine Fahrt
mit dem Stift an („Fahrt anpassen“): Abfahrt, Start, Zwischenstopps (eine
Adresse pro Zeile, höchstens neun), Ziel, Bezeichnung und eine Notiz, die
die Fahrer im Überblick sehen. Was du so lässt, folgt weiter den Phasen.
Eine angepasste Fahrt trägt das Schild „angepasst“; **„Zurücksetzen“**
holt die ermittelte Fahrt zurück. Mit dem Papierkorb entfernst du eine
Fahrt; sie bleibt entfernt, auch wenn sich die Phasen ändern, und steht
unter **„Entfernte Fahrten“** mit „Zurückholen“. Mit **„Fahrt
hinzufügen“** legst du eine eigene Fahrt an, etwa eine Nachlieferung; sie
trägt das Schild „eigene Fahrt“. Der Routen-Link folgt deinen Änderungen.
Bei einem abgeschlossenen Projekt lassen sich Fahrten nicht mehr ändern.
Beim Duplizieren oder Gliedern eines Projekts gehen angepasste Fahrten
nicht mit.

**„Bestätigt – Preise und Einzelheiten offen“.** Für den häufigen Fall, dass der Auftrag da
ist, aber die Aufbauzeiten oder der Ansprechpartner noch fehlen: Setzt du
den Status, führt Rentalars dich in die Zeitplanung, damit du notierst,
was offen ist. Das Material ist ab da fest reserviert. Sind alle Punkte
abgehakt, erscheint oben **„Auf ‚Bestätigt‘ setzen“** – ein Klick genügt.

**Projekte → Offene Punkte** zeigt alle Projekte mit offenen Punkten. Neben
den notierten Punkten stehen dort als weitere Punkte die **Fehlbestände**
des Projekts, die noch nicht gelöst sind, etwa „Fehlbestand: 4 ×
LED-Scheinwerfer (2 zugemietet, 2 offen)“. Ein Klick darauf öffnet die
Planung des Projekts an der betroffenen Position; sie ist dort farbig
hinterlegt. Projekte mit Fehlbeständen erscheinen auch dann, wenn sie keine
offenen Punkte haben. Du siehst nur Projekte, deren Planung du sehen
darfst, und die Fehlbestände nur mit dem Sonderrecht „Verfügbarkeit von
Material sehen“; mit dem Projektzugriff „Überblick ohne Planung“ (Rolle
Crew) gibt es den Reiter gar nicht.

### Logistik: Fahrzeuge und Anhänger

In der Planung steht unter dem Personal der Block
**„Logistik“**: die Fahrzeuge (KFZ) und Anhänger eures Fuhrparks, die das
Projekt braucht, und auf welchen Fahrten sie fahren. Fahrzeuge sind keine
Materialpositionen – sie stehen in keiner Teilgruppe, nicht auf der
Packliste und zählen nicht zur Verfügbarkeit des Materials. Woher sie
kommen, steht in Abschnitt 4, „Fuhrpark“, ihre Sätze stehen an ihrem
Produkt (Abschnitt 5, „Produktarten“). Gibt es noch kein Fahrzeugprodukt,
sagt der Block es: „Der Fuhrpark ist leer: …“.

**Ein Fahrzeug buchen.** Unter dem Block wählst du bei **„Fahrzeug oder
Anhänger“** ein bestimmtes Fahrzeug – nach Produkt gruppiert, mit
Kennzeichen – oder beim Produkt **„noch offen oder zugemietet“**, wenn noch
nicht feststeht, welches fährt. Hat das Projekt Phasen, wählst du auf
Wunsch die **„Phase“**; **„Von“** und **„Bis“** übernehmen dann ihren
Zeitraum, sonst steht der des Projekts darin – oder du trägst einen eigenen
ein. **„Buchen“**. Eine offene Buchung trägt das Schild „Fahrzeug noch
offen“; das Fahrzeug wählst du später am Stift.

**Eine Buchung bearbeiten** – der Stift öffnet den Dialog:

- **„Fahrzeug oder Anhänger“**, **„Bezeichnung“**, **„Phase“**, **„Von“**
  und **„Bis“**, **„Notiz“**;
- mit Preisrecht die **Sätze** – beim Buchen aus dem Produkt übernommen
  und danach die der Buchung; eine spätere Änderung am Produkt ändert sie
  nicht: beim KFZ **„Preis je Kilometer (netto)“** und
  **„Anhängerzuschlag je Kilometer (netto)“**, beim Anhänger die
  **„Abrechnung“** „je Tag“ oder „nach Kilometern“ mit **„Preis je Tag
  (netto)“**, **„Miettage“** und **„Nur Tage mit Fahrten“** oder dem Preis
  je Kilometer; dazu **„Rabatt in Prozent“** – höchstens der Höchstrabatt
  des Produkts – und die **„Steuerart“**;
- mit dem Recht für Einkaufspreise **„Interne Kosten je Kilometer“** und
  beim Anhänger **„Interne Kosten je Tag“**;
- **„Zugemietet bei“**: Ein Fahrzeug, das ihr bei einem Lieferanten mietet,
  buchst du wie ein eigenes, nur ohne Fahrzeug und mit dem Lieferanten. Was
  er für die ganze Buchung berechnet, steht unter **„Was der Lieferant
  berechnet“** – das sind die Kosten statt der Kosten je Kilometer und Tag;
  der Kunde zahlt die Sätze des Produkts wie bei einem eigenen.

„Buchung speichern“. Der Papierkorb entfernt die Buchung mit ihren
Fahrten.

**Die Fahrten.** Unter den Buchungen stehen unter **„Fahrten“** die Fahrten
des Projekts: die aus den Phasen Aufbau und Abbau, Abholung und Rückgabe
bei Lieferanten und eure eigenen (oben, „Die Fahrten eines Projekts“).
Sobald ein KFZ gebucht ist, öffnet **„Fahrzeug“** (mit dem Plus) an einer
Fahrt den Dialog „Fahrzeug der Fahrt zuordnen“:

- **„Fahrzeug“** – ein KFZ des Projekts – und auf Wunsch der
  **„Anhänger“**, den es zieht. Auf einer Fahrt können mehrere KFZ fahren,
  jedes mit höchstens einem Anhänger.
- **„Geplante km“** und **„Gefahrene km“**. Hat euer Administrator den
  Routendienst eingerichtet, schlägt **„Geplante km aus der Route
  vorschlagen“** die Kilometer über alle Halte der Fahrt vor – „… km laut
  Route – ein Vorschlag, änderbar.“ Fehlt einem Ort die Anschrift oder
  findet der Dienst keine Route, nennt die Meldung den Ort („„Lager“ hat
  noch keine Adresse.“). Ohne Routendienst gibt es den Knopf nicht, und du
  trägst die Kilometer von Hand ein (Abschnitt 16, „Firmendaten und
  Grundeinstellungen“).
- mit Preisrecht **„Berechnet“**: „gefahrene Kilometer“ (voreingestellt –
  bis sie eingetragen sind, gelten die geplanten, mit dem Schild
  „Schätzung“), „geplante Kilometer“ oder „Pauschale für die Fahrt“ mit
  ihrem Betrag – Fahrzeug, Zuschlag und ein Anhänger nach Kilometern
  zusammen;
- **„Notiz“**.

An jedem Fahrzeug einer Fahrt stehen „Ändern“ und „Von der Fahrt nehmen“.
Gibt es eine Fahrt nicht mehr – ihre Phase wurde entfernt oder die Fahrt
gelöscht –, stehen ihre Fahrzeuge mit ihren Kilometern unter „Eine Fahrt,
die es nicht mehr gibt“ und werden **nicht berechnet**; ordne sie einer
anderen Fahrt zu oder entferne sie.

**Was berechnet wird:**

| Buchung | Betrag |
|---|---|
| KFZ | je Fahrt die Kilometer × Preis je Kilometer; zieht es auf der Fahrt einen Anhänger, von selbst × (Preis je Kilometer + Anhängerzuschlag) – oder die Pauschale der Fahrt |
| Anhänger nach Kilometern | je Fahrt dieselben Kilometer wie sein KFZ × sein Preis je Kilometer; bei einer Pauschale ist er darin enthalten |
| Anhänger je Tag | Preis je Tag × Faktor der Staffel für seine Tage, wie beim Material (Abschnitt 8); ohne Staffel zählt jeder Tag voll. Tage: an der Buchung eingetragen, sonst die ihres eigenen Zeitraums, sonst die Miettage des Projekts – mit „Nur Tage mit Fahrten“ nur die Tage, an denen er fährt |

Die Spalte „Berechnet“ zeigt die Kilometer und die Zahl der Fahrten oder
die Tage, „Preis“ den Satz, etwa „+ 0,20 € je km mit Anhänger“, „Betrag“
das Ergebnis mit „davon Anhängerzuschlag …“. Die Spalte **„Kosten“** (mit
dem Recht für Einkaufspreise): die Kilometer jeder Fahrt – gefahrene,
sonst geplante – × interne Kosten je Kilometer, beim Anhänger je Tag seine
Tage × interne Kosten je Tag; ein zugemietetes Fahrzeug kostet, was der
Lieferant berechnet. Darunter steht die „Zwischensumme Logistik“.

**Hinweise.** Rentalars sagt an der Buchung und nach dem Speichern
Bescheid, verhindert aber nichts:

- das Fahrzeug ist zur selben Zeit **anderswo gebucht** („Auch gebucht für
  Projekt 2027-0042 von … bis …“ – nur mit der Nummer, denn nicht jede
  darf das andere Projekt öffnen) oder in diesem Projekt doppelt;
- es ist **nicht einsatzbereit** – defekt, in Reparatur, gesperrt – oder
  hat eine **Sperrzeit**;
- eine **Prüfung** wie HU oder UVV ist überfällig oder vor dem Ende der
  Buchung fällig;
- es fahren mehr Personen mit, als es **Sitzplätze** hat;
- der Fahrer hat **keinen Führerschein der Klasse**, die das Fahrzeug oder
  das Gespann braucht – geprüft wird nur, wenn eure Qualifikationsarten
  Führerscheinklassen nennen (Abschnitt 12, „Qualifikationen und
  Nachweise“);
- das KFZ darf **keinen Anhänger ziehen**, oder der Anhänger wiegt mehr,
  als es ziehen darf.

**Wer mitfährt.** Im Dialog einer Personalposition wählst du unter
**„Fahrzeug“** ein KFZ des Projekts und hakst **„Fährt das Fahrzeug“** an,
wenn die Person fährt (Abschnitt 12, „Personal im Projekt einplanen“). Die
Buchung zeigt dann „Fahren mit: …“, der Fahrer mit „Fahrer“. Das Fahrzeug
nennen auch die Personalposition, der Überblick der Person, die
Crew-Disposition und Mein Bereich → „Meine Einsätze“. Die Fahrzeit ist
Arbeitszeit der Personalposition; die Logistik berechnet nur das Fahrzeug.

**Die Logistik folgt dem Projekt.** Buchungen mit dem Zeitraum des
Projekts übernehmen einen neuen; Buchungen einer Phase wandern mit ihr
(oben, „Eine Phase verschieben“), und wer das ganze Projekt im Zeitstrahl
verschiebt, nimmt sie mit (Abschnitt 15). Wie Duplizieren, Vorlagen und
Teilprojekte mit der Logistik umgehen, steht in den Abschnitten unten.

**Summen und Dokumente.** Die Logistik gehört zur Summe netto, zur Steuer,
zur Grundlage eines Aufpreises auf das gesamte Projekt und zum Gewinn aus
dem Projekt (Abschnitt 8). Angebot, Auftragsbestätigung und Rechnung haben
einen Abschnitt „Logistik“ (Abschnitt 11); die Packliste nennt das
Fahrzeug, in das sie verladen wird (Abschnitt 10, „Die Packliste“).

**Wer darf.** Fahrzeuge buchen und den Fahrten zuordnen darf, wer das
Projekt bearbeiten darf – oder es lesen und Material bearbeiten darf, denn
der Fuhrpark gehört zum Material. Sätze, Abrechnung und Rabatte setzt nur,
wer Preise sehen darf, Kosten nur, wer Einkaufspreise sehen darf. In einem
abgeschlossenen Projekt lässt sich die Logistik nicht mehr ändern; ein
Servicefall hat keine.

### Ein Projekt duplizieren

Das Stadtfest jedes Jahr, die Messe jeden Herbst: **„Duplizieren“** oben
auf der Projektseite macht aus einem Projekt ein neues, für einen neuen
Zeitraum.

- Übernommen werden Kunde, Ansprechpartner, Veranstaltungsort, Notizen und
  die **Phasen**, verschoben in den neuen Zeitraum.
- **Material** auf Wunsch (voreingestellt), mit Teilgruppen, Preisen und
  Rabatten. Positionen mit eigenem Zeitraum behalten ihre Lage zum
  Beginn; Uhrzeiten bleiben auch über eine Zeitumstellung hinweg gleich.
- **Personal** auf Wunsch – als offene Plätze, jeder in seiner Phase. Wer
  an den neuen Terminen Zeit hat, ist eine neue Frage.
- **Logistik** auf Wunsch (**„mit der Logistik (Fahrzeuge und
  ihre Fahrten)“**): die Fahrzeugbuchungen mit Fahrzeug, Sätzen und Phase,
  verschoben wie die Positionen, und die Fahrzeuge auf den Fahrten zu
  Aufbau und Abbau, Abholung und Rückgabe – mit Anhänger, geplanten
  Kilometern und dem, was berechnet wird, aber ohne gefahrene Kilometer.
  Eigene Fahrten gehen nicht mit. Ist ein Fahrzeug an den neuen Terminen
  schon gebucht, sagt es die Logistik der Kopie. Wird auch das Personal
  kopiert, behält es sein Fahrzeug.
- Alternativen nennen in der Kopie die kopierte Position oder Teilgruppe,
  zu der sie eine Alternative sind.
- Zumietungen beginnen in der Kopie mit dem Status **„offen“** – beim
  Lieferanten ist dafür noch nichts angefragt (Abschnitt 9, „Zumieten“).
  Ältere Materialpositionen mit einer Dienstleistung lässt die Kopie weg; plane das Personal im Block Personal.
- Die Kopie beginnt als **Anfrage**, mit dir als Projektleitung.

**Ein Gesamtprojekt** wird mit seinen Teilprojekten kopiert – **„mit
Teilprojekten“** ist vorbelegt (unten, „Teilprojekte“):

- Jedes Teilprojekt behält seine Lage zum Beginn und seine Dauer. Ist der
  neue Zeitraum kürzer, wird es auf ihn gekürzt.
- Was ein Teilprojekt selbst anders eingestellt hat – Projektleitung,
  Lieferadresse, Ansprechpartner, Ort –, behält es.
- Übernahmen zwischen den Teilprojekten bleiben erhalten. Passt eine nicht
  mehr, wird sie eine normale Position; die Seite sagt, wie viele.
- Einzeln stornierte Teilprojekte werden nicht kopiert.

**Ein Teilprojekt duplizieren:** Mit dem Haken **„als neues Teilprojekt
desselben Gesamtprojekts“** (vorbelegt) wird die Kopie ein weiteres
Teilprojekt; ihr Zeitraum muss im Zeitraum des Gesamtprojekts liegen, und
sie beginnt mit dem Status, den ein neues Teilprojekt dort bekommt – bei
einem bestätigten Gesamtprojekt „Bestätigt – Preise und Einzelheiten offen“. Dafür musst
du das Gesamtprojekt bearbeiten dürfen. Ohne Haken wird die Kopie ein
eigenständiges Projekt, und übernommene Positionen werden zu normalen
Positionen.

### Projektvorlagen

Duplizieren nimmt ein Projekt samt Kunde und Preisen mit. Für Formate, die
bei immer anderen Kunden wiederkehren – die Hochzeit „Standard“, die
Firmenfeier mit kleiner Bühne –, gibt es **Vorlagen**: die Struktur eines
bewährten Projekts, ohne Kunde und ohne alte Preise.

**Eine Vorlage speichern.** **„Als Vorlage speichern“** oben auf der
Projektseite öffnet einen Dialog:

- **„Name der Vorlage“** – vorbelegt mit dem Namen des Projekts – und eine
  **„Beschreibung“**;
- was mitkommt: **„Teilgruppen und Material“**, **„Personalplätze und
  Fahrzeugbuchungen (offen, ohne Personen und Fahrzeuge)“**, **„Zeitplanung: Phasen und offene
  Punkte“** – voreingestellt alles;
- **„Gleichnamige Vorlage ersetzen“**, wenn es schon eine Vorlage dieses
  Namens gibt und die neue sie ablösen soll. Ohne den Haken lehnt
  Rentalars einen doppelten Namen ab.

„Vorlage speichern“. Eine Vorlage hält **ein** Projekt fest: Aus einem
Gesamtprojekt enthält sie nur dessen eigene Positionen; Teilprojekte
speicherst du einzeln als Vorlage – der Dialog sagt es dazu. Was die
Vorlage behält:

- die **Teilgruppen** mit ihren Einstellungen und ihrer Schachtelung und
  die **Positionen** mit Produkt, Menge, Miete oder Verkauf, Notiz,
  gewünschtem Modell und „Zählt als“ – eine Alternative mit der Position
  oder Teilgruppe, die sie ersetzen könnte; Positionen ohne Produkt mit
  Bezeichnung und Preis (eine ältere Materialposition mit einer
  Dienstleistung lässt Rentalars beim Anwenden der Vorlage weg und sagt es,
  unten);
- die **Personalpositionen** mit Funktion, Stunden, Phase, Treffpunkt und
  Notiz – ohne Personen, also als offene Plätze;
- mit ihnen die **Fahrzeugbuchungen** mit Produkt,
  Bezeichnung, Notiz, Phase und Zeitraum – als offene Buchungen ihres
  Produkts, ohne das Fahrzeug selbst und mit den Sätzen, die das Produkt
  am Tag des neuen Projekts hat;
- die **Phasen** und **offenen Punkte** und die Notizen des Projekts.

Alle Zeiten merkt sie sich **relativ zum Beginn** des Projekts: Der Aufbau
„am Vortag 14 Uhr“ ist im neuen Projekt wieder am Vortag um 14 Uhr. Eine
Position mit eigenem Zeitraum behält ihre Lage zum Beginn, gekürzt auf den
neuen Mietzeitraum.

Was sie **nicht** behält: Kunde, Veranstaltungsort, Status, Personen und
die Preise der Produkte. Eine Vorlage wird oft Monate später verwendet; es
gelten dann die **Preise des Tages**, an dem das neue Projekt entsteht, und
der Standardrabatt des neuen Kunden – als würdest du die Positionen von
Hand hinzufügen. Nur Rabatt und Pauschalpreis einer Teilgruppe und der
Preis von Positionen ohne Produkt bleiben, und das nur, wenn, wer die
Vorlage speichert, Preise sehen darf.

**Den Inhalt einer Vorlage bearbeiten.** Ein Klick auf den Namen
in der Liste der Vorlagen (oder „Inhalt bearbeiten“ auf der Seite der Vorlage) öffnet
den **Inhalt**: so, wie ein neues Projekt daraus entsteht – Teilgruppen mit ihren
Positionen, Personalplätze, Fahrzeugbuchungen, Phasen, offene Punkte und die Notizen.
Ein Eintrag lässt sich **hinzufügen** („Produkt hinzufügen“, „Freizeile hinzufügen“,
„Text hinzufügen“, „Gruppe hinzufügen“, „Personalplatz hinzufügen“ …), **ändern**,
mit den Pfeilen **eine Stelle hoch oder runter verschieben** und **löschen**. Eine
Gruppe, die du löschst, fragt vorher, was mit ihrem Inhalt geschieht: ihren Platz in
der Gruppe darüber einnehmen oder mit ihr gelöscht werden. Zeiträume gibst du in
**Stunden ab Beginn** des Projekts an („Von“, „Bis“), auf Wunsch ab dem **Ende**
(„Rücknahme drei Stunden vor Schluss“); „Phase“ nennt die Phase, zu der ein Platz oder
eine Buchung gehört. Rentalars prüft jede Änderung auf Zusammenhänge – eine Position
in einer Gruppe, die es gibt; eine Alternative, die etwas ersetzt, das es gibt; die
Schachtelung der Gruppen – und speichert nichts, was beim Anlegen eines Projekts
nicht gelesen werden könnte. **Preise** (Rabatt und Pauschalpreis einer Gruppe, Preis
einer Freizeile) sieht und ändert nur, wer Preise sehen darf; für alle anderen bleiben
sie, wie sie sind. Hat jemand anderes einen Eintrag inzwischen geändert oder gelöscht,
sagt die Seite es („Dieser Eintrag wurde inzwischen von jemand anderem geändert oder
entfernt“), statt den falschen Eintrag zu treffen. **Projekte, die schon aus der
Vorlage entstanden sind, ändern sich nicht.** Dafür braucht es das Recht, Projekte zu
bearbeiten. Dieselbe Arbeit macht die API (`/project-templates/{id}/content`).

**Ein Projekt mit einer Vorlage beginnen.** Projekte → Neues Projekt, im
Feld **„Vorlage“** die Vorlage wählen, Name, Kunde und Zeitraum wie immer.
Beim Speichern kommen Teilgruppen, Positionen, Personalpositionen,
Fahrzeugbuchungen und Zeitplanung dazu, mit der Verfügbarkeit des neuen
Zeitraums. Ist ein Produkt
oder eine Funktion inzwischen deaktiviert oder gelöscht, lässt Rentalars
diese Position aus und sagt es („Aus der Vorlage weggelassen: …“) –
ebenso eine Materialposition mit einer Dienstleistung („eine
Dienstleistung, die unter Personal geplant wird: …“).

**Vorlagen verwalten.** Projekte → **„Vorlagen“** listet alle Vorlagen mit
Inhalt („3 Teilgruppen, 42 Positionen, 4 Personalpositionen, 5 Phasen“),
dem Projekt, aus dem sie entstanden sind, und wer sie wann angelegt hat.
Ein Klick auf den Namen öffnet den Inhalt (siehe oben); Namen und
Beschreibung änderst du auf der Seite „Vorlage bearbeiten“;
„löschen“ entfernt sie (mit dem Recht, Projekte zu löschen). Projekte, die
aus einer Vorlage entstanden sind, bleiben, wie sie sind.

**Die mitgelieferte Vorlage „Dry Hire (Vermietung ohne Personal)“.** Neue
Installationen bekommen sie bei der Ersteinrichtung. Sie enthält keine Positionen und kein Personal, dafür vier Phasen,
jede mit dem Ort „Lager“ und einer kurzen Notiz, und eine Projektnotiz,
dass der Kunde abholt und zurückbringt:

| Phase | wann |
|---|---|
| Packen | die ersten zwei Stunden des Mietzeitraums |
| Übergabe an den Kunden (Abholung) – Art „Sonstiges“ | die Stunde danach |
| Rücknahme – Art „Rückfahrt“ | drei bis zwei Stunden vor dem Ende |
| Nachbereitung | die letzten zwei Stunden |

Anders als bei selbst gespeicherten Vorlagen richten sich Rücknahme und
Nachbereitung nach dem **Ende** des Mietzeitraums; so passen sie zu jeder
Mietdauer. Ist der Mietzeitraum sehr kurz, werden sie auf ihn gekürzt. Du
kannst die Vorlage umbenennen, mit einer eigenen gleichen Namens ersetzen
oder löschen; gelöscht kommt sie nicht wieder. Speicherst du ein Projekt,
das aus ihr entstanden ist, als eigene Vorlage, merkt diese sich alle
Zeiten wieder relativ zum Beginn.

### Dry Hire – Vermietung ohne Personal

Der Kunde holt das Material im Lager ab, baut selbst auf und bringt es
zurück – ohne euer Personal und ohne Transport. So bildest du das ab:

1. **Projekte → Neues Projekt**, unter „Vorlage“ **„Dry Hire (Vermietung
   ohne Personal)“** wählen, Name und Kunde eintragen.
2. **Mietzeitraum:** vom Packen vor der Abholung bis nach der Rückgabe –
   so lange ist das Material für andere Projekte belegt. Abholung am
   Freitag um 14 Uhr, Rückgabe am Montag um 9 Uhr: Freitag 12:00 bis
   Montag 12:00. Dann liegen Packen (12 bis 14 Uhr) und Übergabe (14 bis
   15 Uhr) am Freitag, Rücknahme (9 bis 10 Uhr) und Nachbereitung (10 bis
   12 Uhr) am Montag. Kommt der Kunde zu einer anderen Zeit, änderst du die
   Uhrzeiten der Phasen in der Zeitplanung.
3. **Miettage** trägst du ein, wie ihr sie berechnet – etwa einen Tag für
   ein Wochenende, wenn ihr das so haltet; leer rechnet Rentalars sie aus
   dem Mietzeitraum (oben, „Ein Projekt anlegen“).
4. **Material** wie gewohnt hinzufügen; Verfügbarkeit, Ampel und Preise
   gelten wie bei jedem Projekt.
5. **Dokumente:** Angebot und Auftragsbestätigung wie immer. Bei der
   Abholung **packen und ausgeben** (Abschnitt 10) und danach den
   **Lieferschein** erstellen – er nennt die ausgegebenen Exemplare und hat
   die Felder für die Unterschrift des Kunden. Kommt das Material zurück,
   die **Rücknahme** auf der Packliste abhaken und mit „Rücknahme buchen“
   buchen – ist alles zurück, geht das Projekt von selbst auf „Wieder im
   Lager“ – und die **Rechnung** erstellen.

Personal und Transport fehlen einfach; brauchst du doch jemanden, etwa für
eine Einweisung, planst du ihn wie in jedem Projekt ein. Ohne
Veranstaltungsort und ohne eigene Lieferadresse steht auf dem Lieferschein
die Anschrift des Kunden – bei einer Abholung genau richtig. Vermietet ihr
oft dasselbe Paket ohne Personal, speichert ihr ein solches Projekt als
eigene Vorlage.

### Verlauf

Der Reiter „Verlauf“ zeigt jede Änderung am Projekt: wer wann den Status
geändert, eine Position oder ein Fahrzeug hinzugefügt, eine Menge oder
einen Preis verändert,
eine Phase, Datei oder einen offenen Punkt angelegt, eine Mail einem
anderen Projekt oder einer Zumietung zugeordnet, ein Dokument erstellt,
storniert, gesendet oder an Lexware Office übergeben, Material an ein
anderes Teilprojekt übergeben, eine Wiedervorlage gesetzt oder erledigt,
das Projekt in Teilprojekte gegliedert, einen Termin im Zeitstrahl
verschoben oder eine Position auf der Karte korrigiert hat.
Preisänderungen sieht nur, wer Preise sehen darf. Den Betreff einer Mail
oder den Titel einer Notiz der Korrespondenz sieht nur, wer
diese Nachricht lesen darf (Abschnitt 14, „Nachrichten mit Schloss“); die
anderen sehen einen Eintrag ohne Betreff, etwa „Nachricht, eingegangen am
…“ oder „Notiz vom …“. Nachrichten im Chat
stehen nicht im Verlauf, sondern im Chat.

### Chat im Projekt

Kurze Absprachen im Team – „Bühne steht, Licht kommt um 15 Uhr“, „Wer bringt
die Kabeltrommel mit?“ – gehören nicht in die Korrespondenz mit dem Kunden.
Dafür hat jedes Projekt, jedes Teilprojekt und jeder Servicefall den
Reiter **„Chat“**.

- **Wer mitliest:** alle, die das Projekt öffnen können – auch die
  eingeplante Crew, die sonst nur den Überblick sieht. Die Seite sagt das
  oben, und **„… Personen lesen mit“** klappt auf, wer. Schreib also
  nichts hinein, was die Crew nicht lesen soll, etwa Preise.
- **Schreiben:** Text ins Feld „Nachricht“, **„Senden“** – oder
  **Strg+Enter**. Jede Nachricht steht mit Name und Uhrzeit da, die
  neueste unten; **„Ältere Nachrichten“** holt frühere.
- **Fotos und Videos**: Unter dem Feld wählst du mit
  **„Fotos oder Videos anhängen“** Dateien aus; am Telefon öffnet
  **„Foto oder Video aufnehmen“** gleich die Kamera. Eine Nachricht darf
  nur aus Fotos und Videos bestehen, ohne Text. Erlaubt sind bis zu
  **10 Dateien** je Nachricht, **Fotos bis 25 MB**, **Videos bis 200 MB
  und 20 Minuten**, zusammen bis 500 MB; geprüft wird der Inhalt der
  Datei, nicht ihre Endung. Ein Foto als PNG, GIF oder WebP darf
  höchstens **16 Megapixel** haben; ein größeres lehnt der Server ab
  („Größere Fotos bitte als JPEG senden.“) – als JPEG darf es bis
  150 Megapixel haben. Abgelehnt werden auch Videos, deren Bild an einer
  Seite mehr als 4096 Pixel hat, die mehr als 240 Bilder pro Sekunde
  haben oder mehr Einzelbilder als 20 Minuten bei 60 Bildern pro Sekunde.
  **Der Server verkleinert alles und behält nur die kleine Fassung** –
  das Original ist danach weg: Fotos werden
  aufrecht gedreht, auf höchstens 2048 Pixel an der langen Seite
  verkleinert und **nur mit dem Ort der Aufnahme** (GPS) als Angabe gespeichert, ohne
  Gerät und Uhrzeit der Kamera; im Chat steht eine Vorschau, ein Klick
  öffnet das Foto in voller Größe. Videos verkleinert der Server im
  Hintergrund auf höchstens 720p (MP4), eines nach dem anderen – bis
  dahin steht dort **„Video wird verkleinert …“**. Schicken mehrere
  gleichzeitig Videos, wartet deins, bis die vorigen fertig sind, und der
  Hinweis steht entsprechend länger da. Misslingt das Verkleinern, wird
  das Video verworfen, die Nachricht sagt es, und wer es geschickt hat,
  bekommt eine Benachrichtigung. Fehlt auf dem Server das Programm dafür, sagt das
  Formular „Videos gehen gerade nicht: Auf dem Server fehlt ffmpeg.“ –
  Fotos gehen trotzdem. Sehen kann die Fotos und Videos, wer den Chat
  lesen darf; wird die Nachricht gelöscht, gehen sie mit.
- **Jemanden erwähnen:** **@** und den Anfang eines Namens tippen, dann
  aus der Liste wählen (Pfeiltasten und Enter, oder ein Klick) – oder in
  „… Personen lesen mit“ auf einen Namen klicken. Die Person bekommt eine
  Benachrichtigung „… hat dich im Chat von … erwähnt“, in Rentalars und –
  wie unter Mein Konto → Benachrichtigungen eingestellt, voreingestellt
  ja – per Mail. Erwähnen lässt sich nur, wer den Chat lesen kann.
- **Ändern und löschen:** eigene Nachrichten in den ersten **15 Minuten**
  nach dem Schreiben; eine geänderte trägt danach „geändert“. Wer in einer
  geänderten Nachricht neu erwähnt wird, wird benachrichtigt, die anderen
  nicht noch einmal. **Löschst du eine Nachricht**, löscht Rentalars auch die
  KI-Zusammenfassungen des Projekts (und die früheren Fassungen), die den Chat
  nach dieser Nachricht gelesen haben – sonst stünde ihr Inhalt dort weiter
  (Abschnitt 14, „Zusammenfassung und Kurzüberblick“). Eine neue Zusammenfassung
  schreibst du mit „Zusammenfassen“.
- **Neue Nachrichten** anderer erscheinen von selbst, ohne dass die Seite
  neu lädt – was du gerade tippst, bleibt stehen. Auf den anderen Reitern
  des Projekts zeigt „Chat“ die Zahl der Nachrichten, die du noch nicht
  gelesen hast.

Geschrieben werden kann in jedem Status, auch in einem abgeschlossenen
Projekt.

### Teilprojekte

Eine große Produktion – etwa ein Stadtfest mit mehreren Bühnen – planst du
als **Gesamtprojekt** mit **Teilprojekten**. Jedes Teilprojekt ist ein
Projekt für sich: mit eigenem Namen, Ort, eigener Projektleitung, eigenem
Mietzeitraum und eigenen Miettagen – eine Bühne muss vielleicht einen Tag
früher fertig sein –, eigenen Positionen mit Teilgruppen, eigenem Personal
und eigenem Status. Gemeinsames – zentrale Stromversorgung,
Produktionsleitung – planst du direkt am Gesamtprojekt. Es gibt genau eine
Ebene: Ein Teilprojekt hat keine Teilprojekte.

#### Ein Teilprojekt anlegen

**„Teilprojekt anlegen“** oben auf der Seite des Gesamtprojekts öffnet das
Formular „Neues Teilprojekt“:

- Den **Namen** gibst du ihm – „Bühne Marktplatz“. **Ort,
  Projektleitung, Ansprechpartner, Lieferadresse und Mietzeitraum** sind
  vom Gesamtprojekt vorgeschlagen und änderbar. Wie jedes neue Projekt
  kann auch ein Teilprojekt mit einer **Vorlage** beginnen (oben,
  „Projektvorlagen“).
- **Kunde und Rechnungsadresse** sind immer die des Gesamtprojekts; das
  Formular zeigt sie nur an („Vom Gesamtprojekt, mit dessen
  Rechnungsadresse. Dort änderbar.“). Ändert sich der Kunde oder die
  Rechnungsadresse am Gesamtprojekt, ändern sie sich in allen
  Teilprojekten.
- Der **Mietzeitraum** liegt im Mietzeitraum des Gesamtprojekts.
  Verschiebst du den des Gesamtprojekts als Ganzes – Beginn und Ende um
  dieselbe Zeit –, wandern die Teilprojekte mit. Verkürzt du ihn so, dass ein Teilprojekt
  herausragen würde, lehnt Rentalars das ab; ändere dann zuerst das
  Teilprojekt.

Das Teilprojekt bekommt die **Nummer** des Gesamtprojekts mit einem Zähler:
`2026-0042-1`, `2026-0042-2`. Unter dieser Nummer ist es erreichbar, und
`[RL#2026-0042-1]` ist sein Kürzel für Mails (Abschnitt 14). Über dem Namen
steht „Teilprojekt“, die Zeile darüber führt zum Gesamtprojekt.

Ein neues Teilprojekt beginnt mit dem Status, der zu seinem Gesamtprojekt
passt: bei einer Anfrage als Anfrage, bei einer Option als Option, bei
einem bestätigten Gesamtprojekt als **„Bestätigt – Preise und Einzelheiten offen“** – eine
neue Bühne ist selten gleich fertig geplant. Ein storniertes oder
abgeschlossenes Gesamtprojekt bekommt keine neuen Teilprojekte.

#### Ein Projekt nachträglich gliedern

Das Stadtfest war als ein Projekt geplant, mit einer Teilgruppe je Bühne –
und jetzt soll jede Bühne ihren eigenen Zeitraum, ihre Packliste und ihren
Status bekommen? Dann muss nichts neu angelegt werden: Im Kopf des Projekts
steht am Pfeil ▾ neben „Teilprojekt anlegen“ **„In Teilprojekte
gliedern“**.

1. Unter **„Teilgruppen, die Teilprojekte werden“** wählst du die
   Teilgruppen der obersten Ebene, die eigene Teilprojekte werden sollen.
   Neben jeder steht, wie viele Positionen und Untergruppen sie hat und
   was aus ihr wird.
2. Unter **„Crew“** wählst du für jede Personalposition unter „Geht an“,
   wohin sie geht: Sie „bleibt am Gesamtprojekt“ oder „geht mit
   „…““ einer der gewählten Teilgruppen – Personal steht in keiner
   Teilgruppe, deshalb fragt Rentalars. Ihre Zeiteinträge gehen mit, ihre Phase wird ins Teilprojekt
   kopiert.
3. **„In Teilprojekte gliedern“.**

Das Projekt wird zum **Gesamtprojekt**. Jede gewählte Teilgruppe wird ein
Teilprojekt mit der Nummer des Projekts und „-1“, „-2“ …, mit ihren
Positionen, mit dem Mietzeitraum, der Veranstaltung, den Miettagen und dem
Status des Projekts und den Voreinstellungen eines neuen Teilprojekts
(Ort, Ansprechpartner, Projektleitung). Die Teilgruppe selbst löst sich
dabei auf: Ihre Positionen stehen im Teilprojekt ohne Teilgruppe, ihre
Untergruppen werden dessen Teilgruppen. Hat sie einen Rabatt, einen
Pauschalpreis, eigene Miettage, eine Beschreibung, ist sie optional oder
Alternative oder bezieht sich ein Aufpreis auf sie, bleibt sie als
Teilgruppe im Teilprojekt – so bleiben die Preise gleich. Eine Zumietung,
die eine Fehlmenge deckt, geht mit ihrer Position.

Was du nicht wählst, bleibt am Gesamtprojekt – zentrale Stromversorgung,
Produktionsbüro. Ebenso bleiben Dokumente, Mails, Dateien, Phasen, offene
Punkte, die Wiedervorlage und die Logistik am Gesamtprojekt; eine
Personalposition, die in ein Teilprojekt geht, nennt danach kein Fahrzeug
mehr. Danach kann jedes
Teilprojekt einen eigenen Zeitraum, Ort, eine Packliste und einen Status
bekommen.

**Nicht möglich** ist es in einem Teilprojekt und bei einem Servicefall,
wenn das Projekt unterwegs, wieder im Lager, abgeschlossen oder storniert
ist, für eine Teilgruppe, deren Material schon gepackt oder ausgegeben ist,
und wenn eine Alternative oder ein Aufpreis über die neue Grenze hinweg
reicht – die Seite nennt bei jeder Teilgruppe den Grund. Bezieht sich ein
prozentualer Aufpreis auf das ganze Projekt, sagt Rentalars vorher: Er
bleibt am Gesamtprojekt und rechnet danach nur noch auf das, was dort
bleibt. Hat das Projekt noch keine Teilgruppen, fasse die Positionen jedes
künftigen Teils zuerst in einer Teilgruppe zusammen.

**Aufgeteilte Zeiträume bleiben zusammen**. Hat jemand einen
Zeitraum auf mehrere Funktionen aufgeteilt (Abschnitt 13, „Mehrere
Funktionen in einem Zeitraum“), gehören die Teile zu verschiedenen
Personalpositionen. Gingen diese Positionen in verschiedene Teilprojekte,
risse der Zeitraum auseinander – deshalb lehnt Rentalars das Gliedern dann
ab und nennt Person, Tag, Uhrzeiten und Funktionen. Wähle für diese
Personalpositionen dasselbe Ziel; gehen sie zusammen, geht der Zeitraum
ganz mit.

**An einem Gesamtprojekt** heißt derselbe Punkt **„Teilgruppen in
Teilprojekte umwandeln“**: Jede gewählte Teilgruppe des Gesamtprojekts
wird ein weiteres Teilprojekt mit seinen Zeiträumen; die vorhandenen
Teilprojekte bleiben, wie sie sind.

Der Verlauf des Gesamtprojekts hält fest „In Teilprojekte gegliedert: …“,
jedes neue Teilprojekt, aus welcher Teilgruppe es entstanden ist.

#### Der Reiter „Teilprojekte“

Am Gesamtprojekt und an jedem Teilprojekt zeigt der Reiter
**„Teilprojekte“** alle Teile nebeneinander: eine Zeile für die eigenen
Positionen des Gesamtprojekts, eine je Teilprojekt, mit Mietzeitraum,
Positionen, Stück, Personal, offenen Plätzen, Stunden, Netto (mit
Preisrecht) und Fehlmengen – und darunter die Summe von allem
(„Gesamtprojekt mit allen Teilen“). Darunter stehen die **„Engpässe
zwischen den Teilprojekten“**: Positionen, denen etwas fehlt, weil andere
Teilprojekte dasselbe Material gleichzeitig fest belegen. Teilprojekte,
deren Planung du nicht lesen darfst, fehlen; die Seite sagt, wie viele,
und die Summen sind ohne sie.

Über der Planung führt eine **Leiste** zum Gesamtprojekt und zu jedem
Teil – so wechselst du schnell von Bühne zu Bühne.

#### Status

Jedes Teilprojekt hat seinen eigenen Status. Änderst du den Status des
Gesamtprojekts, nimmt der Haken **„Teilprojekte auch“** neben der Liste
„Status ändern auf …“ – er ist gesetzt – die Teile mit, wo der Schritt für sie möglich ist; die
übrigen behalten ihren Status, und Rentalars nennt sie. Drei Regeln gelten
immer:

- **Storniert** wird das Gesamtprojekt immer mit seinen Teilen; die
  Rückfrage sagt es. Ist Material eines Teilprojekts unterwegs – auch nur
  ein Teil davon –, geht das nicht.
- **Abschließen** lässt sich das Gesamtprojekt erst, wenn alle Teile
  abgeschlossen oder storniert sind.
- Ein Teilprojekt eines stornierten Gesamtprojekts lässt sich nicht allein
  wieder aufnehmen – nimm zuerst das Gesamtprojekt wieder auf.

Ein Gesamtprojekt mit Teilprojekten lässt sich nicht löschen.

#### Zugriff

Wer nur zugeordnete Projekte sieht (Abschnitt 12, „Wer welches Projekt
sieht“):

- **Mitglieder des Gesamtprojekts** haben denselben Zugriff in allen
  Teilprojekten.
- Unter **„Zugriff“ eines Teilprojekts** gibst du einem Mitglied dort
  anderen Zugriff – mehr oder weniger – oder **„kein Zugriff“**. Diese
  Mitgliedschaft ersetzt die im Gesamtprojekt, nur für dieses Teil.
- Eine Mitgliedschaft **nur in einem Teilprojekt** öffnet nur dieses –
  weder das Gesamtprojekt noch die anderen Teile. Eine externe
  Bühnenleitung bekommt so genau ihre Bühne.
- Wer in einem Teilprojekt **eingeplant** ist, sieht dessen Überblick und
  Packliste, auch bei „kein Zugriff“.

Wer ein Teilprojekt sieht, sieht auch Nummer und Name seines
Gesamtprojekts („Teil von 2026-0042 Stadtfest“). Rollen für alle Projekte
gelten in allen Teilen.

#### Material, das weiterwandert: Übernahme

Sollen dieselben Stücke erst auf der einen, dann auf der anderen Bühne
stehen, plane sie im späteren Teilprojekt als **Übernahme**:

1. In der Planung des späteren Teilprojekts **„Aus anderem Teilprojekt
   übernehmen“**. Der Dialog zeigt die Positionen der anderen Teile (und
   des Gesamtprojekts), die früher beginnen und noch Stücke übrig haben –
   mit „Übrig“ und wann sie dort frei sind.
2. Position wählen, Menge eintragen (voreingestellt: alles, was übrig ist)
   und die Teilgruppe, in die die Übernahme kommt; „Übernehmen“.

Oder im Dialog einer Position unter **„Übernahme aus“** die Position
wählen, von der die Stücke kommen – angeboten werden Positionen desselben
Produkts, die früher beginnen. Verkaufte Ware lässt sich nicht übernehmen.

Was die Übernahme bewirkt:

- **Verfügbarkeit:** Die Stücke gelten als durchgehend unterwegs, vom
  ersten Teilprojekt bis zum Ende des zweiten – ohne Pufferzeiten
  dazwischen, denn sie gehen nicht zurück ins Lager. Überschneiden sich
  die Zeiträume, zeigt die Planung eine Fehlmenge: Dieselben Stücke können
  nicht auf zwei Bühnen zugleich stehen.
- **Preis:** Die übernommene Position kostet nichts – berechnet wird sie
  dort, wo sie herkommt. Sie trägt das Schild „übernommen“, „kommt von …“
  und „nicht berechnet / berechnet in 2026-0042-1“.
- **Am anderen Ende** zeigt die Position, von der übernommen wird, „6
  gehen weiter an …“. Sie lässt sich nicht unter die Menge verkleinern,
  die andere übernehmen; löschst du sie, werden die übernehmenden
  Positionen zu normalen.
- **Packliste:** Die Stücke stehen auf beiden Packlisten; ihre Ankunft
  wird als **Übergabe** gebucht (Abschnitt 10, „Übernahme und Übergabe
  zwischen Teilprojekten“).

#### Rechnen, packen, abrechnen

- **Abgerechnet wird am Gesamtprojekt:** Angebot, Auftragsbestätigung und
  Rechnung enthalten alle Teilprojekte; am Teilprojekt entstehen
  Lieferscheine und Crew-Dispositionen (Abschnitt 11, „Gesamtprojekt und
  Teilprojekte“).
- Die **Preisübersicht** des Gesamtprojekts zeigt alle Teile und die Summe
  aller (Abschnitt 8).
- Jedes Teilprojekt wird für sich **gepackt und ausgegeben**; über jeder
  Packliste stehen die übrigen Teile als Reiter, und **„Alle zusammen“**
  zeigt die Packliste des Gesamtprojekts mit allen Teilen (Abschnitt 10).

#### Teilprojekte in der übrigen Anwendung

- **Duplizieren:** Ein Gesamtprojekt wird mit seinen Teilprojekten
  kopiert, ein Teilprojekt als neues Teilprojekt desselben Gesamtprojekts
  oder als eigenständiges Projekt (oben, „Ein Projekt duplizieren“).
- **Vorlagen:** Eine Vorlage aus einem Gesamtprojekt enthält nur dessen
  eigene Positionen; Teilprojekte speicherst du einzeln als Vorlage.
- **Kalender, Zeitstrahl, Personalplan:** Teilprojekte heißen „Bühne
  Marktplatz (Stadtfest)“, im Tooltip steht „Teil von 2026-0042
  Stadtfest“. Im Zeitstrahl stehen sie eingerückt unter ihrem
  Gesamtprojekt. Im Zeitstrahl eines Produkts beginnt übernommenes
  Material dort, wo die Position endet, von der es kommt („6× übernommen“).
- **Suche, Startseite, Listen:** Teilprojekte tragen „Teil von …“. Der Name
  des Gesamtprojekts findet auch seine Teile. In der Projektliste steht am
  Gesamtprojekt, wie viele Teilprojekte es hat; auf der Seite eines Kunden
  folgen die Teilprojekte ihrem Gesamtprojekt. Die Summenspalten der
  Projektliste zeigen am Gesamtprojekt die Summe aus ihm und seinen
  Teilprojekten (Abschnitt 8, „Summen in der Projektliste“).
- **Fehlbestände:** Dort steht „davon belegt durch andere Teilprojekte: N“
  mit einem Link zum Reiter „Teilprojekte“ (Abschnitt 9).
- **Zeiterfassung und Überblick:** Personal und Zeiten gehören zum
  Teilprojekt. Die Projektauswahl zeigt „2026-0042-1 Bühne Marktplatz
  (Stadtfest)“; der Überblick und der Kalendereintrag nennen das
  Gesamtprojekt.
- **Korrespondenz:** Mails mit `[RL#2026-0042-1]` landen im Teilprojekt.
  Das Gesamtprojekt zeigt die Mails seiner Teilprojekte mit an,
  gekennzeichnet mit deren Nummer (Abschnitt 14).
- **Chat:** Jedes Teilprojekt hat seinen eigenen Chat (unten, „Chat im
  Projekt“).

### Servicefälle

Ein Beamer im Tagungsraum eines Kunden fällt aus, ein Hotel fragt nach
einem Ersatzmikrofon, ein Gerät kommt zur Reparatur: Dafür ein Projekt mit
Zeitraum und Planung anzulegen, wäre zu viel. Ein **Servicefall** ist eine
schnelle Art von Projekt – mit Nummer, Kürzel und Korrespondenz, aber ohne
Material, Personal, Logistik und Packliste.

**Projekte → Servicefälle** listet voreingestellt alle Fälle, die nicht
erledigt sind („Alle nicht erledigten“) – auch die wartenden und die
zurückgestellten; erledigte siehst du, wenn du unter „Status“ „erledigt“ wählst.
Filtern lässt sich nach Text (Nummer, Betreff, Kunde oder wer es gemeldet
hat), Status und „nur meine“. Mit **„Neuer Servicefall“** legst du einen
an:

- **„Worum geht es?“** – Pflicht, etwa „Beamer Saal 2 ohne Bild“;
- **Kunde** – Pflicht, wie bei einem Projekt; mit dem Kunden wählst du
  einen seiner **Ansprechpartner**. Noch kein Kunde? Tippe den Namen ein
  und wähle „… als neuen Kunden anlegen“. Geht es um euer eigenes
  Material – etwa die Reparatur eines defekten Geräts –, setz stattdessen
 den Haken **„Intern – eigenes Material, kein Kunde“**; dann
  braucht der Fall keinen Kunden, und beim Kunden steht „intern“;
- **„Gemeldet von“** – Name, Telefon oder E-Mail-Adresse dessen, der es
  gemeldet hat, wenn er kein Ansprechpartner des Kunden ist;
- **Beschreibung** (freiwillig) und **„Zuständig“** – die zuständige
  Person bekommt eine Benachrichtigung, dass der Fall bei ihr liegt.

„Servicefall anlegen“. Die **Nummer** kommt aus dem Nummernkreis der
Projekte (`2026-0057`), und Mails mit dem Kürzel `[RL#2026-0057]` im Betreff
landen im Fall wie in einem Projekt (Abschnitt 14).

**Aus einer Anfrage.** Unter Projekte → Anfragen steht an jeder Mail ohne
Kennung **„Als Servicefall anlegen“**. Das Formular nennt die Mail und
schlägt den Kunden aus dem Absender vor, wenn Rentalars ihn kennt; beim
Speichern holt Rentalars sie aus dem Posteingang in den neuen Fall – oder,
wenn etwas nicht klappt, tut es gar nichts. Dafür braucht es das Recht,
Projekte anzulegen und im Modul E-Mail zu bearbeiten. Das geht
auch mit einer Anfrage, die jemand von Hand notiert hat – etwa während
eines Anrufs (Abschnitt 14, „Anfragen“): Aus ihr wird eine Notiz in der
Korrespondenz des Falls.

**Gleich aus einer Mail.** Hat euer Postfach eine Adresse wie `support@`,
für die „gleich als Servicefall anlegen“ eingestellt ist (Abschnitt 14,
„Weitere Adressen eines Postfachs“), legt Rentalars aus jeder Mail ohne
Kennung an diese Adresse sofort einen Servicefall an – Betreff, Kunde und
Ansprechpartner aus dem Absender, so weit Rentalars sie kennt – und
benachrichtigt die Person, die dort „verantwortlich für neue
Servicefälle“ ist; sie ist dann „Zuständig“. Kennt Rentalars den Absender
nicht, legt es den Fall ohne Kunden an (unten, „Kunde fehlt“). Klappt das
Anlegen nicht, bleibt die Mail eine Anfrage.

**Aus einer Defektmeldung.** Jeder gemeldete Defekt – auf
der Seite des Exemplars, bei der Rücknahme oder über die Schnittstelle –
wird von selbst ein Servicefall: Die Automation „Defektmeldung → Servicefall“
ist in jeder Installation eingerichtet und eingeschaltet (Abschnitt 16,
„Automationen“). Der Fall heißt etwa „Defekt 0042 SM58“; die Beschreibung
nennt, was defekt ist, das Exemplar mit Seriennummer, wo es auffiel, wer es
wann gemeldet hat, und den Link zum Exemplar. Bei eigenem Material ist der
Fall intern („intern“ und „eigenes Material“ beim Kunden), bei
Kundenmaterial gehört er dessen Eigentümer. „Gemeldet von“ ist, wer den
Defekt gemeldet hat; zuständig ist, wen die Automation nennt. Das Foto der
Meldung kommt in die Dateien des Falls. Ist die Automation so
eingestellt, wartet die Meldung stattdessen unter Projekte → Anfragen
(Abschnitt 14, „Anfragen“); von dort – oder im Reiter „Dateien und
Defekte“ des Exemplars – macht **„Als Servicefall anlegen“** den Fall,
vorbelegt mit denselben Angaben. Aus einer Meldung wird höchstens ein
Servicefall.

**„Kunde fehlt“.** Fälle ohne Kunden – von Rentalars aus der Mail eines unbekannten
Absenders angelegt – bleiben gültig und zeigen beim Kunden das Schild
„Kunde fehlt“; wer den Fall bearbeiten darf, sieht daneben „Kunden wählen“. Beim
nächsten Bearbeiten fragt das Formular nach dem Kunden; den Status setzen
kannst du auch ohne ihn.

**Die Seite eines Servicefalls** hat die Reiter **Überblick**,
Dokumente, Korrespondenz, Chat, Zugriff und Verlauf. Der erste Reiter
heißt „Überblick“ (vorher „Servicefall“). Er zeigt
Status, Kunde, Ansprechpartner, „Gemeldet von“, „Zuständig“, wann der Fall
angelegt wurde, die Beschreibung, die letzten Mails mit „Mail schreiben“,
die offenen Punkte und den Kasten „Verwandt“ mit den
verwandten Projekten und Servicefällen (oben, „Verwandte Projekte und
Servicefälle“). „Mail schreiben“ steht dort unter denselben
Bedingungen wie im Reiter Korrespondenz (Abschnitt 14, „Der Reiter
„Korrespondenz““). Den **Status** setzt du dort mit „Status setzen“,
in jeder Reihenfolge (unten, „Der Status eines Servicefalls“); „Servicefall
bearbeiten“ im Kopf ändert die übrigen Angaben. Eine Wiedervorlage geht
wie bei einem Projekt (oben, „Wiedervorlage“). Hat eine
Adresse eures Postfachs die Rolle „nur für Servicefälle“, gehen Mails, die
du im Servicefall schreibst, mit dieser Adresse als Absender hinaus – sie ist unter „Absender“ vorgewählt (Abschnitt 14, „Schreiben und
antworten“). Der Reiter Korrespondenz sieht aus wie im Projekt: Über
den Mails steht der Kasten „Zusammenfassung“ mit dem Kurzüberblick und,
wenn eingeschaltet, der Zusammenfassung durch die KI (Abschnitt 14,
„Zusammenfassung und Kurzüberblick“); du erreichst ihn über „Alle … Mails“
oder den Reiter Korrespondenz.

**Der Status eines Servicefalls.** Neben **offen**, **in Arbeit** und
**erledigt** gibt es drei Status, die eine Wiedervorlage
brauchen:

| Status | Wofür | Was die Wiedervorlage braucht |
|---|---|---|
| **wartet** – auf Rückmeldung, Aktion oder Materiallieferung | Der Ball liegt beim Kunden, bei jemand anderem oder beim Lieferanten. Der Fall heißt dann etwa „wartet auf Rückmeldung“. | Tag (Uhrzeit freiwillig) und worauf er wartet |
| **wartet auf Schließen** | Alles ist getan; meldet sich bis zum Termin niemand, wird der Fall geschlossen. | Tag und Uhrzeit |
| **zurückgestellt** | Der Fall hat Zeit. Bis zur Wiedervorlage steht er nur unter Projekte → Servicefälle. | Tag (Uhrzeit freiwillig) |

Wählst du einen davon in der Statusliste, öffnet sich sofort der Dialog
der Wiedervorlage (mit der Tastatur: mit den Pfeiltasten auswählen, dann
Enter): Tag (bei „wartet auf Schließen“ auch die Uhrzeit), für
wen, Notiz – bei „wartet“ auch, worauf. Erst mit der Wiedervorlage wird
der Status gespeichert; „Abbrechen“ lässt den bisherigen Status stehen.
Verschiebst du später die Wiedervorlage eines Falls, der auf Schließen
wartet, bleibt die Uhrzeit Pflicht. Die Status haben eigene Farben in der
Liste und stehen im Verlauf.

- **wartet auf Schließen:** Tut sich bis zum Termin nichts, schließt
  Rentalars den Fall („erledigt“) und nimmt die Wiedervorlage weg; eine
  Benachrichtigung zur Wiedervorlage kommt dann nicht. Kommt vorher eine
  neue Mail – empfangen oder gesendet – oder eine Chatnachricht, steht der
  Fall wieder auf „offen“; die Wiedervorlage bleibt als Erinnerung.
- **Zurückgestellt:** Bis zur Wiedervorlage steht der Fall nicht auf der
  Startseite, nicht unter Mein Bereich → Servicefälle und nicht unter
  Planung → Wiedervorlagen (dort und unter Mein Bereich holt ihn „Auch
  Zurückgestellte“ bzw. „auch Zurückgestellte“ in die Liste). Zur Wiedervorlage steht
  er wieder auf „offen“, und die Person bekommt die Benachrichtigung.
- **„Erledigt“ an der Wiedervorlage** eines Falls in einem dieser drei
  Status stellt ihn wieder auf „offen“ – mit einem Hinweis.

Das Schließen und Wiederöffnen erledigen drei Automationen, die
eingerichtet und eingeschaltet sind (Abschnitt 16, „Automationen“); du
kannst sie ändern oder ausschalten.

**Beteiligte.** Du fügst auf der Seite eines Servicefalls unter
**„Beteiligte“** weitere Personen hinzu: Person, auf Wunsch die
**Funktion** und eine **Notiz**, dann „Person hinzufügen“. Das ist keine
Crew-Planung – es gibt keine Einsatzanfrage, keine Verfügbarkeitsprüfung
und keine Kosten aus der Planung; Personalplan und „Wer ist frei?“ kennen
Beteiligte nicht. Die Person bekommt die Benachrichtigung „Zu einem
Servicefall hinzugefügt“ (voreingestellt in Rentalars, per E-Mail und in
der App), sieht den Fall unter **Mein Bereich → „Servicefälle“**
und auf der Startseite unter „Meine Servicefälle“ und erfasst ihre Zeiten
darauf (Abschnitt 13). Sie arbeitet am Fall mit, gleich welche
Rolle sie hat (unten, „Mitarbeit am Fall“). Fügst du eine
Person noch einmal hinzu, änderst du nur Funktion und Notiz; deaktivierte
Personen und Funktionen stehen nicht zur Wahl. Mit dem **Papierkorb**
(„Vom Servicefall nehmen“) nimmst du sie nach einer Rückfrage vom Fall;
ihre Zeiten bleiben. Hinzufügen und Entfernen stehen im Verlauf des Falls.

**Mein Bereich → Servicefälle** listet die Fälle, an denen du beteiligt
bist oder für die du zuständig bist und die nicht erledigt sind –
ohne die zurückgestellten, bis seine Wiedervorlage fällig ist; erledigte mit dem
Filter „auch erledigte“, die zurückgestellten mit „auch Zurückgestellte“. Es ist eine
Tabelle wie jede Liste, auch nach Status zu gruppieren.

**Mitarbeit am Fall**. Wer für einen Servicefall
**zuständig** oder an ihm **beteiligt** ist, öffnet und bearbeitet ihn –
unabhängig von seiner Rolle, auch mit der Rolle Crew und ohne Zugriff auf
die Projekte: Status mit Wiedervorlage, die Angaben des Falls samt
„Zuständig“, die Beteiligten, die offenen Punkte, den Chat und die
Korrespondenz des Falls – Mails lesen, schreiben und beantworten, Notizen
schreiben; die offenen Nachrichten, die mit Schloss nur mit
dem Recht „Preise und Kalkulation sehen“ (Abschnitt 14, „Nachrichten mit
Schloss“). Der Link in der Benachrichtigung führt direkt hin, und Mein
Bereich → Servicefälle und die Startseite zeigen die eigenen Fälle auch
ohne Zugriff auf die Projekte. Nicht dazu gehören „In Projekt umwandeln“,
Löschen, Preise (die hängen weiter am Preisrecht) und alle anderen Fälle.
Die **Korrespondenz von Projekten bleibt vertraulich**: Dafür braucht es
weiter die Sonderrechte für Korrespondenz. **Kunde, Ansprechpartner und
„Gemeldet von“** sieht und ändert nur, wer Kunden sehen darf – sonst fehlen
sie auf der Seite und im Formular des Falls und bleiben über die
Schnittstelle leer. Das gilt ebenso über die Schnittstelle und in der
Rentalars-App.

**Zeiten auf einem Servicefall.** Auf jeden Servicefall, der nicht
erledigt ist, kann jede Person, die Zeiten erfasst, Zeiten buchen – auch
ohne eingeplant oder beteiligt zu sein, und mit jeder Funktion
(Abschnitt 13, „Zeit erfassen“). Der Knopf **„Zeit erfassen“** steht dafür
auch oben auf der Seite des Falls und in jeder Zeile unter Mein Bereich →
„Servicefälle“; er öffnet das Erfassen mit dem Fall schon gewählt.

**Wo ein Servicefall nicht erscheint:** Er hat keinen Mietzeitraum,
reserviert nichts und steht deshalb nicht in Kalender, Zeitstrahl,
Verfügbarkeit, Fehlbeständen und der Projektliste, auch nicht unter „Steht
an“ auf der Startseite. Er erscheint in der Suche (mit „Servicefall“),
unter Projekte → Offene Punkte, bei den Wiedervorlagen (auch unter
Planung → Wiedervorlagen), unter Mein Bereich → Servicefälle und auf der
Startseite unter „Meine Servicefälle“ – ein zurückgestellter Fall erst, wenn
seine Wiedervorlage fällig ist.

**PDF für den Kunden.** Auf der Seite eines Servicefalls (Reiter „Überblick“) erstellt der Knopf **„PDF für den Kunden“**
ein Dokument, das du dem Kunden schicken kannst. Es enthält den Überblick des Falls – Nummer, Betreff, Status, Kunde,
Verantwortliche, Zeitpunkt der Meldung und Beschreibung – und die Korrespondenz, aber **nur die Nachrichten ohne
Schloss**, mit Absender bzw. Empfänger, Datum, Betreff, Text und den Namen der Anhänge. Nicht enthalten sind
Nachrichten mit Schloss, Notizen, automatische Antworten und Zustellfehler, offene Punkte, Beteiligte, Chat,
Wiedervorlage und alle Preise. Kontaktperson und „Gemeldet von“ stehen nur im Dokument, wenn du Kunden sehen darfst.
Das PDF wird sofort unter **„Dokumente“** des Servicefalls abgelegt (nicht für die Crew sichtbar) und trägt den
Zeitpunkt im Namen; jeder Aufruf erzeugt eine neue Datei, frühere bleiben erhalten. Im Änderungsprotokoll des Falls
steht, wann ein PDF erstellt wurde. Der Text steht in der Sprache der Firmendokumente. Du brauchst dafür Änderungsrecht
am Servicefall und das Recht, seine Korrespondenz zu lesen; die oder der Verantwortliche und die Beteiligten arbeiten
am Fall und dürfen es auch ohne die Rolle „Projekte“. Beachte: Das PDF ist eine Datei des Falls wie ein übernommener
Anhang einer Mail – **wer die Dokumente des Falls lesen darf, kann es öffnen**, auch wer die Korrespondenz oder die
Kunden nicht sehen dürfte. Nachrichten aus reinem HTML erscheinen als Text. Über die API: `POST /api/v1/service-cases/{id}/customer-pdf`.

**Wird mehr daraus** – der Kunde will gleich eine Ersatzanlage mit
Techniker –, macht **„In Projekt umwandeln“** im Kopf aus dem Fall ein
Projekt. Das Formular ist das eines Projekts; Kunde und Mietzeitraum
braucht es. Das Projekt behält Nummer, Mails, Dateien, offene Punkte und
Verlauf und beginnt als Anfrage; danach planst du Material und Personal
wie immer. Beteiligte des Falls haben im Projekt keine Bedeutung mehr –
plane sie dort als Crew ein.

#### Monatsabrechnung

Ihr rechnet die Servicefälle eines Kunden gesammelt je Monat
ab: **Buchhaltung → „Monatsabrechnung“** – für alle, die Preise sehen
dürfen (unten, „Wer darf“). Sie steht im Menüpunkt **Buchhaltung** neben den
Ausgangsbelegen (Abschnitt 11, „Ausgangsbelege“).

**Die Übersicht.** Unter **„Monat“** wählst du den Monat; zuerst steht der
vorige da, mit ‹ und › blätterst du. Je Kunde steht eine Zeile mit seinen
Servicefällen, den Stunden, dem Betrag netto und dem Status – „offen“,
„Entwurf“, „Rechnung RE-…“ oder „als abgerechnet markiert“ – und dem Knopf
**„Entwurf anlegen“** bzw. **„Entwurf öffnen“**. Wer Zeiten freigeben
darf, sieht außerdem, wie viele Zeiten des Monats noch kein Projekt haben:
Sie gehören zu keinem Fall und werden nicht abgerechnet, bis sie unter
Personal → Freigeben einem zugeordnet sind.

**Welche Fälle.** Fälle mit einem Kunden, die im Monat auf „erledigt“
gesetzt wurden oder darin freigegebene Zeiten oder Spesen haben. Ein im
Monat erledigter Fall bringt auch frühere freigegebene Zeiten und Spesen
mit, die noch keine Abrechnung hat. Nicht dabei sind interne Fälle, Fälle
mit „Keine Rechnung“, mit einer eigenen Rechnung oder mit „Rechnung
gestellt“ von Hand (Abschnitt 11, „Noch zu schreibende Rechnungen“) und
Fälle in einem anderen Entwurf. Jede Zeit und jede Spese rechnet genau eine
Abrechnung ab – auch, wenn ihre Position dort entfernt wurde. Ein Fall, der
über mehrere Monate läuft, wird so Monat für Monat abgerechnet. Je Kunde und
Monat gibt es einen Entwurf; Fälle, die danach dazukommen, holt „Neu
einsammeln“ in ihn („noch nicht im Entwurf“), und nach der Rechnung lässt
sich für sie eine weitere Abrechnung anlegen.

**Der Entwurf** hat je Fall einen Abschnitt „Servicefall 2027-0043 –
Titel“; die Nummer führt zum Fall:

- **„Tätigkeit“** – steht auf der Rechnung unter dem Fall. Vorgeschlagen
  aus der Beschreibung des Falls, den Notizen der Zeiten und – wenn du die
  Korrespondenz lesen darfst – den Notizen und Betreffs der Mails des
  Monats; ändere sie, wie du willst. Ist eine KI für Zusammenfassungen
  eingeschaltet und erreichbar (Abschnitt 16, „KI“), schreibt **„Mit
  lokaler KI zusammenfassen“** bzw. **„Mit KI zusammenfassen“** sie neu;
  der Text trägt dann „von KI erstellt“. Den Knopf hat, wer die
  Korrespondenz lesen darf.
- die **Positionen** mit Bezeichnung, Menge, Einheit, Einzelpreis und
  Steuerart – alle änderbar; eine geänderte trägt „geändert“. Der
  Papierkorb entfernt eine Position; entfernte stehen eingeklappt darunter
  („… Position entfernt – nicht berechnet“) mit **„Wieder aufnehmen“**.
- **„Position hinzufügen“** für verbrauchtes oder verkauftes Material, eine
  Fahrt …: Art.-Nr., Bezeichnung, Menge, Einheit, Einzelpreis und
  Steuerart. Mit einer Artikelnummer kommen die leeren Felder vom Produkt,
  bei einem Verkaufsprodukt sein Verkaufspreis.
- **„Fall aus der Abrechnung nehmen“** – seine Zeiten und Spesen sind dann
  wieder frei für eine andere Abrechnung.

Hinweise am Fall nennen, was fehlt – etwa Zeiten des Monats, die noch
nicht freigegeben sind. Darunter stehen die Summen: netto, Steuer je
Steuerart, brutto.

**Wie die Positionen entstehen.** Die freigegebenen Zeiten zählen je
Funktion, zum Preis ihres Dienstleistungsprodukts: nach Stunden oder nach
Aufwand die Stunden, je Tag die Tage je Person (zwei Personen an einem Tag
sind zwei Tage), pauschal einmal je Fall. Stunden eines Tages über der
Grenze stehen als eigene Position zum Preis ab der Grenze, Zuschläge für
Nacht, Sonn- und Feiertage wie bei Personalpositionen (Abschnitt 12, „Was
Personal kostet und einbringt“). Rabatte gibt es keine von selbst. Jede
freigegebene Spese wird eine Position – eine Fahrt mit dem eigenen Auto mit
Kilometern × Satz, sonst ihr Betrag –, als Nettopreis zur
Standard-Steuerart; enthält ein Beleg Umsatzsteuer, korrigierst du den
Preis im Entwurf. Eine Funktion ohne Preis ergibt 0 € und einen Hinweis.

**Speichern, neu einsammeln, löschen.** **„Speichern“** hält fest, was du
geändert hast; jeder andere Knopf speichert vorher ebenso. **„Neu
einsammeln“** holt neue Zeiten, Spesen und Fälle des Monats dazu.
Tätigkeiten, hinzugefügte und entfernte Positionen und deine geänderten
Positionen bleiben; eine geänderte Position, deren Zeiten sich inzwischen
geändert haben, rechnet Rentalars neu und sagt es an ihr. Ein Fall, der
inzwischen anders abgerechnet wird, fällt heraus; einen, den du
herausgenommen hast, holt es nicht zurück. **„Entwurf löschen“** gibt
Fälle, Zeiten und Spesen wieder frei.

**Rechnung erstellen** – wenn Rentalars die Rechnungen schreibt (Abschnitt
11, „Rechnungen in einem anderen Programm“). Über den Fällen steht die
**„Einleitung der Rechnung“**, vorbelegt mit „Für die Servicefälle im März
2027 berechnen wir:“. **„Entwurf als PDF“** zeigt die Rechnung mit
„ENTWURF“, **„Rechnung erstellen“** erstellt sie nach einer Rückfrage:
eine Rechnung mit einem Abschnitt je Fall – Titel, Tätigkeit, Positionen –,
mit Nummer aus dem Kreis der Rechnungen, PDF und XRechnung; Schlusstext und
Fuß kommen aus der Vorlage der Rechnung. Sie gehört zum Fall mit der
niedrigsten Nummer und rechnet alle Fälle ab; die Seite sagt es vorher
(Abschnitt 11, „Rechnung und XRechnung“).

**Als abgerechnet markieren** – wenn ihr die Rechnungen in einem anderen
Programm schreibt. Der Kasten **„Zum Übertragen in dein
Rechnungsprogramm“** zeigt Kunde, Monat und je Fall Tätigkeit und
Positionen; ein Klick kopiert einen Wert. **„Alle Positionen als Tabelle
kopieren“** und das Feld darunter liefern alle Positionen durch Tabulatoren
getrennt, etwa für eine Tabellenkalkulation. Danach setzt **„Als
abgerechnet markieren“** an jedem Fall „Rechnung gestellt“; **„Markierung
zurücknehmen“** nimmt das wieder weg.

**Am Servicefall** steht oben, wo er abgerechnet ist: „Abgerechnet mit der
Monatsrechnung RE-… (März 2027)“, „Als abgerechnet markiert mit der
Monatsabrechnung März 2027“ oder „In der Monatsabrechnung März 2027
(Entwurf)“, mit „Abrechnung öffnen“ – für alle, die Preise sehen dürfen.
Abgerechnete Fälle gelten als berechnet; an sie erinnert Rentalars nicht
mehr (Abschnitt 11, „Noch zu schreibende Rechnungen“).

**Wer darf.** Die Monatsabrechnung sieht, wer Projekte lesen, Preise und
Kunden sehen und jeden ihrer Fälle lesen darf; anlegen und ändern darf
sie, wer Projekte bearbeiten und jeden ihrer Fälle bearbeiten darf; einen
Entwurf löschen, wer Projekte löschen darf. Über die Schnittstelle geht
dasselbe (Abschnitt 16, „API-Token“).

---

## 8. Preise

*Für alle mit dem Recht „Preise und Kalkulation sehen“.*

### Wie der Betrag einer Position entsteht

Beim Hinzufügen übernimmt die Position Preis, Abrechnungsart und Steuerart
vom Produkt. Danach gehört der Preis der Position: Ändert sich später der
Preis des Produkts, bleiben bestehende Projekte, wie sie waren – bei
Anfragen und Optionen bietet die Planung aber an, die neuen Preise zu
übernehmen (unten, „Geänderte Produkte“).

Für die Tagesmiete gilt:

> **Betrag = Menge × Einzelpreis × Faktor der Miettage, abzüglich Rabatt**

Die Spalte „Miettage“ zeigt, womit gerechnet wurde: oben die Tage („2
Tage“), darunter der Staffelfaktor („Faktor 1,5“). Zwei Miettage kosten
also das Anderthalbfache eines Tages – nicht zwei mal anderthalb.

> **Beispiel.** 4 Scheinwerfer zu 20,00 € pro Tag, 2 Miettage:
> 4 × 20,00 € × 1,5 = **120,00 €**. Mit 10 % Rabatt: 108,00 €.

**Welche Miettage gelten?** Es gilt die genaueste Angabe:

1. Miettage, die an der Position **eingetragen** sind;
2. sonst der **eigene Zeitraum** der Position, wenn er vom Projekt abweicht:
   jede angefangenen 24 Stunden sind ein Tag;
3. sonst die Miettage der Teilgruppe;
4. sonst die des Projekts.

Verschiebst du also eine Position auf andere Tage, rechnet Rentalars ihre
Miettage von selbst neu – du musst nichts nachtragen. Unter der Zahl steht,
woher sie stammt („aus dem Zeitraum dieser Position“, „wie die
Teilgruppe“). Willst du etwas
anderes berechnen als der Zeitraum ergibt, trägst du die Miettage an der
Position ein; das geht immer vor.

Eine Teilgruppe „Aufbautag“ kann so nur einen Tag kosten, während der Rest
drei Tage läuft.

**Für das Projekt als Ganzes bleiben Miettage und Zeitraum unabhängig:**
„Material außer Haus“ entscheidet, wann das Material belegt ist, die
Miettage des Projekts entscheiden, was es kostet.

**Staffelfaktor von Hand.** Trägst du im Dialog einen Faktor ein, gilt
dieser statt des Werts aus der Staffel – für die Sonderabsprache mit dem
Stammkunden.

### Geänderte Produkte (alte Preise und Texte)

Ein Produkt wird teurer, bekommt einen anderen Namen, eine andere Einheit
oder einen anderen Steuersatz, das Angebot ist aber schon geplant? Solange
ein Projekt eine **Anfrage**, eine **Option** oder „Bestätigt – Preise und Einzelheiten offen“
ist (vorher nur Anfrage und Option), merkt Rentalars das:

- **Auf jeder Seite des Projekts** steht unter dem Kopf der Hinweis „3 Positionen
  weichen von ihren Produkten ab“ mit einem Link zur Planung – auch auf dem
  Reiter „Überblick“, auf dem du beim Öffnen eines Projekts landest.
- **Die Projektleitung und die Mitglieder mit Bearbeitungsrecht werden benachrichtigt**,
  sobald jemand das Produkt speichert (Glocke; ob auch per E-Mail, stellt jeder in
  seinen Einstellungen ein). Die Benachrichtigung nennt keine Preise.
- **Die Planung** zeigt oben die Liste „Alte und neue Werte“: je Position, was sich
  geändert hat (Name, Einheit, Steuersatz, Abrechnungsart, Preis), jeweils alt → neu.
  Das gilt für Material und für Personal (dort nur der Preis, er kommt vom
  Dienstleistungsprodukt der Funktion; mit dem Preis kommen die Grenze in Stunden
  pro Tag und der Preis ab der Grenze, Abschnitt 12).

Was du tun kannst:

- **„Änderungen übernehmen“** stellt alle Positionen um, bei denen du nichts von
  Hand geändert hattest.
- **„Übernehmen“** stellt eine einzelne Position um.
- Positionen, bei denen jemand einen Wert **von Hand** geändert hat (ein Sonderpreis,
  eine eigene Bezeichnung), tragen das Schild „von Hand gesetzt“. Sie bleiben, bis du
  Position für Position „Übernehmen“ oder **„Eigene Werte behalten“** wählst; danach
  meldet Rentalars diese Änderung nicht mehr.
- **Auf der Produktseite** nennt der Abschnitt „Geplant in Projekten, die noch nicht
  vollständig bestätigt sind“ alle Projekte, in denen das Produkt veraltet ist. Dort übernimmst du die
  Änderungen je Projekt oder „In allen diesen Projekten“ – in denen, die du bearbeiten
  darfst. Nach dem Speichern eines Produkts sagt eine Meldung, in wie vielen Projekten
  es nachzuziehen ist.

Preise siehst und übernimmst du nur mit dem Recht „Preise sehen und Kalkulation“;
ohne das Recht gehen Namen, Einheiten und Steuersätze, und der Preis bleibt für
jemanden mit dem Recht stehen. Menge, Zeitraum, Notiz und Rabatt einer Position
bleiben beim Umstellen, wie sie sind. **Bestätigte Projekte** (Status „Bestätigt“ und
alle danach) behalten ihre Werte ohne Hinweis – was vereinbart ist, ist vereinbart.

### Rabatte

- **Je Position:** „Rabatt in Prozent“ im Dialog der Position. Hat der
  Kunde einen **Standardrabatt** (Abschnitt 6), steht er in jeder neuen
  Materialposition schon drin – änderbar wie jeder andere.
- **Je Personalposition:** ebenfalls „Rabatt in Prozent“, im Dialog der
  Personalposition (Abschnitt 12). Neue Personalpositionen beginnen mit
  0 %; der Standardrabatt des Kunden gilt für sie nicht.
- **Je Fahrzeugbuchung**: „Rabatt in Prozent“ im Dialog der
  Buchung, höchstens der Höchstrabatt ihres Produkts (Abschnitt 7,
  „Logistik“); auch hier gilt der Standardrabatt des Kunden nicht.
- **Je Teilgruppe:** im Dialog der Gruppe, als Prozentsatz oder als Betrag.
- **Pauschalpreis der Teilgruppe:** ersetzt die Summe ihrer Positionen
  vollständig. Die Einzelpreise bleiben sichtbar; die Planung zeigt, um wie
  viel die Pauschale darunter liegt.
- **Bei geschachtelten Teilgruppen** (Abschnitt 7) wirkt erst der Rabatt
  der Untergruppe, dann der Rabatt der Obergruppe auf alles darin – ihre
  eigenen Positionen und die Zwischensummen ihrer Untergruppen, Aufpreise
  in den Untergruppen eingeschlossen. Ein Pauschalpreis der Obergruppe
  ersetzt alles darunter.

**Der Gesamtrabatt**. Ein Rabatt auf das ganze Projekt statt auf
einzelne Positionen: unter den Summen der Planung **„Gesamtrabatt
setzen“** (hat das Projekt schon einen, **„Gesamtrabatt ändern“**). Du
gibst **eines** von vier Dingen an – nie mehrere; leer entfernt ihn:

- **„Gesamtrabatt in Prozent“** (0 bis 100),
- **„Gesamtrabatt als Betrag“** in Euro,
- den **„Zielbetrag netto“** oder
- den **„Zielbetrag brutto“**.

Das darf, wer Preise sehen und das Projekt planen darf – ein abgeschlossenes
oder nicht mehr planbares Projekt nimmt ihn nicht an.

**Vom Zielbetrag zum Rabatt**. Der Kunde will „für 12.000 €
netto“ – oder „für 14.280 € brutto“? Tipp diesen Betrag bei „Zielbetrag
netto“ oder „Zielbetrag brutto“ ein: Rentalars rechnet daraus den
**Prozentsatz** aus, den du als Rabatt brauchst, und speichert ihn – mit
bis zu **sechs Nachkommastellen**, damit der Betrag stimmt. Unter den Feldern
zeigt eine **Vorschau** schon beim Tippen „Gespeicherter Prozentsatz“, den
Rabatt und was das Projekt dann netto und brutto kostet. Gerechnet wird mit
der Steuer, die das Projekt hat, auch bei mehreren Steuersätzen. Kann ein
Bruttobetrag nicht auf den Cent erreicht werden, nimmt Rentalars den
**nächstliegenden** Betrag und sagt es. Ein Zielbetrag über der Summe ohne
Rabatt wird abgelehnt: Ein Rabatt kann die Summe nicht erhöhen.

Wichtig: Der Prozentsatz wird **einmal** berechnet. Ändert sich das Projekt
später – eine Position mehr, ein anderer Preis –, bleibt der gespeicherte
Prozentsatz, und der Gesamtbetrag ändert sich mit; ein neuer Zielbetrag
rechnet neu. In Angebot, Auftragsbestätigung und Rechnung, in der
Preisübersicht und in der CSV-Datei steht der Prozentsatz mit **bis zu sechs
Nachkommastellen** und deutschem Komma, ohne überflüssige Nullen
(„Gesamtrabatt 19,99994 %“, aber „Gesamtrabatt 10 %“); der gedruckte
Prozentsatz ergibt also den gedruckten Rabatt auf den Cent. Gerechnet wird mit
dem gespeicherten Wert. Über etwa einer Million Euro netto erreicht ein
Zielbetrag den Cent nicht mehr genau; Rentalars nimmt dann den nächstliegenden
Betrag. Über die Schnittstelle geht es mit `POST
/projects/{id}/overall-discount` (`percent`, `amount`, `target_net`,
`target_gross`, `dry_run`); ohne das Preisrecht antwortet sie mit 403.

Der Gesamtrabatt wird **zuletzt** abgezogen: von der Netto-Summe nach allen
Positionen, Rabatten, Zuschlägen, Rundungen und der Mindestmiete. Ein
Betrag ist höchstens so groß wie die Summe; bei einer Summe von null oder
darunter gibt es keinen Rabatt. Die Summen zeigen **„Summe vor dem
Gesamtrabatt“**, **„Gesamtrabatt 10 %“** und darunter die neue Netto-Summe;
die Steuer wird auf die verminderte Summe gerechnet, je Steuerart anteilig.
Preisübersicht (PDF und CSV), Angebot, Auftragsbestätigung und Rechnung
führen ihn als **eigene Zeile „Gesamtrabatt 10 %“** am Ende; die
elektronische Rechnung (XRechnung) und der DATEV-Export tragen ihn mit.

Was du wissen solltest:

- Er gilt **je Projekt**. Ein Teilprojekt hat seinen eigenen; im
  Gesamtprojekt hat jedes Projekt seine Zeile, und die Summen des
  Gesamtprojekts zählen sie zusammen.
- Er ist **kein Rabatt je Position**. Die Grenzen „Höchster Rabatt je
  Funktion“ und „je Produkt“ (unten) und die Regel für Personalpositionen
  gelten nur für die Rabatte der Positionen und Teilgruppen, nicht für ihn.
- In der **Nachkalkulation** (Ertrag je Position, Gewinn) wirkt er auf die
  Projektsumme; auf Material, Personal und Fahrzeuge wird er anteilig
  verteilt, nicht auf einzelne Positionen.
- **Duplizieren** übernimmt ihn – für den, der Preise sehen darf, und nur,
  wenn Material, Personal oder Fahrzeuge mitkopiert werden. **Aufteilen**
  übernimmt ihn immer, damit sich kein Preis ändert: ein Prozentsatz in
  jeden Teil, ein Betrag anteilig nach den Summen der Teile. Wer keine Preise
  sehen darf, sieht ihn nirgends, auch nicht in der API.
- Die Änderung steht im Verlauf des Projekts. API: `overall_discount_percent`
  und `overall_discount_amount` am Projekt, in den Summen
  `net_before_overall_discount` und `overall_discount`.

**Höchster Rabatt je Funktion.** Manche Leistungen sollen nie oder nur
wenig rabattiert werden – etwa der Rigger. An der Funktion legst du dafür
einen **„Höchster Rabatt in Prozent“** fest (Personal → Funktionen,
Abschnitt 12): leer heißt keine Grenze, 0 heißt nie rabattiert. Die Grenze
gilt für Personalpositionen dieser Funktion und für ältere
Materialpositionen mit ihrem Dienstleistungsprodukt – für deren eigenen Rabatt, für den Standardrabatt
des Kunden und für ihren Anteil am Rabatt oder Pauschalpreis der
Teilgruppe. Was eine Position nicht nehmen darf, geht nicht auf andere
über: Der Rabatt der Teilgruppe fällt dann kleiner aus, ein Pauschalpreis
entsprechend höher. Greift die Grenze, zeigen Planung und Preisübersicht
an der Position „höchstens 5 % (Funktion)“; eingetragene Werte bleiben
stehen, gerechnet wird mit der Grenze. Die Grenze sehen und ändern darf
nur, wer Preise sehen darf.

**Höchster Rabatt je Produkt.** Dasselbe gibt es an jedem Produkt
(Abschnitt 5, „Ein Produkt anlegen“), etwa für Verbrauchsmaterial oder
Neuware. Greift dessen Grenze, steht an der Position „höchstens 5 %
(Produkt)“. Haben Produkt und Funktion eine Grenze, zählt die strengere.
Personalpositionen begrenzt nur die Funktion.

### Aufpreise

Aufpreise sind Produkte der Art „Aufpreis“ – ein **fester Betrag**
(„Expresszuschlag 50 €“) oder ein **Prozentsatz** („Außeneinsatz 10 %“).
Du fügst sie wie jedes andere Produkt hinzu. Die Zuschläge für Nacht-,
Sonn- und Feiertagsstunden des Personals sind kein Aufpreis: Die rechnet
Rentalars an jeder Personalposition selbst (Abschnitt
12, „Zuschläge für Nacht, Sonn- und Feiertage“).

Bei einem **prozentualen** Aufpreis legst du im Dialog der Position fest,
**worauf er sich bezieht**: auf das gesamte Projekt, auf einzelne
Teilgruppen oder auf einzelne Positionen – auch auf mehrere. Die Planung
zeigt unter dem Aufpreis, worauf er rechnet und von welchem Betrag.

Der Prozentsatz rechnet auf die Beträge **nach Rabatt** und **nie auf
andere Aufpreise**. Ein Aufpreis auf das gesamte Projekt rechnet auch auf
Personal und Logistik; optionale Teilgruppen und optionale oder
alternative Positionen zählen dabei nicht mit.

> **Beispiel.** Außeneinsatz 10 % auf die Teilgruppen „Licht
> Front-Traverse“ (321,00 €) und „Licht Rear-Traverse“ (351,00 €):
> 10 % von 672,00 € = **67,20 €**.

### Die Summen

Unten auf der Planungsseite:

```
Teilgruppen                              1.329,00 €
Ohne Teilgruppe                            272,20 €
Personal                                 1.666,00 €
Aufpreise                                   67,20 €
Summe netto                              3.334,40 €
Steuer 19 % auf 3.334,40 €                 633,54 €
Summe brutto                             3.967,94 €
Optionale Teilgruppen, nicht enthalten     135,00 €
Optionale Positionen, nicht enthalten       48,00 €
Personalkosten (geplant)                 1.294,00 €
Spesen und Fahrtkosten (freigegeben)        84,00 €
Gewinn aus dem Projekt                   1.956,40 €
```

„Personal“ ist die Zwischensumme des Blocks Personal (Abschnitt 12) –
Zuschläge für Nacht, Sonn- und Feiertage sind darin enthalten. Hat das
Projekt Fahrzeuge, steht darunter **„Logistik“**, die
Zwischensumme des Blocks Logistik (Abschnitt 7, „Logistik“), und – mit dem
Recht für Einkaufspreise – unter den Kosten **„Kosten der Fahrzeuge“**.
Solange gefahrene Kilometer fehlen, steht an der Nettosumme „enthält
Schätzungen“. Die
Personalkosten und die freigegebenen **Spesen und Fahrtkosten** der Crew
(Abschnitt 13, „Spesen und Fahrtkosten“) sieht nur, wer Stunden- und
Tagessätze und Personalkosten sehen darf. Optionale und
alternative Positionen stehen, wenn es welche gibt, eigens unter der
Bruttosumme („Optionale Positionen, nicht enthalten“, „Alternative
Positionen, nicht enthalten“). **Kundenmaterial** zählt in keine Summe und
steht auch nicht darunter: Es wird nie berechnet (Abschnitt 5,
„Kundenmaterial“).

Hat ein Projekt Positionen mit verschiedenen Steuerarten, wird die Steuer
je Steuerart ausgewiesen. Enthält es geschätzte Mengen (Abrechnung nach
Aufwand), steht an der Nettosumme „enthält Schätzungen“.

Wer zusätzlich Einkaufspreise und Personalkosten sehen darf, sieht die
Kosten der Zumietungen und des Personals und den **Gewinn aus dem
Projekt**: die Nettosumme abzüglich
dieser Kosten, der freigegebenen Spesen und der Kosten der Fahrzeuge. Wo er
je Zeile steht – in der Projektliste, in der Preisübersicht je Funktion –,
heißt die Spalte kurz „Gewinn“.

Summen werden nirgends gespeichert. Sie werden bei jedem Aufruf aus den
Positionen errechnet und können deshalb nie von ihnen abweichen.

### Die Preisübersicht

Der Reiter **Preisübersicht** zeigt dasselbe als aufgeräumtes
Arbeitsdokument: je Teilgruppe eine Tabelle mit Artikelnummer, Name, Menge,
Einheit, Miettagen, Einzelpreis, Rabatt und Betrag; dazu das Personal als
eigener Block mit der Artikelnummer seines Dienstleistungsprodukts, Stunden
oder Tagen, Preis und Betrag – und, wo eine Grenze je Tag überschritten
ist, unter dem Preis „davon 2 Std. über 10 Std. am Tag zu 55,00 €“
(Abschnitt 12, „Was Personal kostet und einbringt“), und wo Zuschläge für
Nacht, Sonn- und Feiertage gelten, „inkl. Zuschläge …“ mit jeder Art;
unter dem Block steht ihre Summe („Darin: Zuschläge für Nacht, Sonn- und
Feiertage von … (vor Rabatten).“); jede Zeile heißt wie ihre
Regel unter Einstellungen → Zuschläge. Stunden- und
Tagessätze und Wünsche nach bestimmten Exemplaren stehen dort nie; Kosten
nur in der Aufschlüsselung je Phase, mit dem Recht dafür (unten).

Optionale und alternative Positionen stehen darin mit ihrem Schild und
zählen nicht zur Summe; unter einer Alternative steht, was sie ersetzen
könnte („Alternative zu „8 × LED-Scheinwerfer““). Untergruppen stehen
eingerückt in ihrer Obergruppe, die Obergruppe mit ihrer „Zwischensumme
mit Untergruppen“.

Nach dem Personal folgt der Block **„Logistik“**: je
Fahrzeugbuchung Artikelnummer, Name, Menge – Kilometer, Tage oder
Pauschalen –, Einheit, Einzelpreis, Rabatt und Betrag, mit dem
Anhängerzuschlag darin; PDF und CSV übernehmen ihn. Interne Kosten stehen
dort nie.

**Personal je Phase und Funktion.** Der Knopf **„Personal je Phase und
Funktion“** schlüsselt den Block Personal auf: je Phase eine Zeile pro
Funktion mit Plätzen, Stunden oder Tagen und Betrag, darunter die
Zwischensumme der Phase; Personal ohne Phase steht zuletzt unter „Ohne
Phase“. So siehst du etwa, was Aufbau und Show je Tontechnik kosten. Wer
das Recht für Personalkosten hat, sieht in dieser Ansicht auch die Spalten
„Kosten“ und „Gewinn“. **„Personal wie die übrigen Blöcke“** schaltet
zurück. PDF und CSV übernehmen die gewählte Ansicht – ohne Kosten, denn
das PDF geht an Kunden.

**Gesamtprojekt und Teilprojekte.** Die Preisübersicht eines
Gesamtprojekts zeigt erst seine eigenen Positionen, dann jedes Teilprojekt
mit Nummer, Name und Zeitraum und seiner Summe, und unten die **„Summen
des Gesamtprojekts mit allen Teilprojekten“**: Netto, Steuer je Steuerart
und Brutto über alles. Jedes Teilprojekt rechnet dabei für sich – ein
Prozentaufpreis „auf das gesamte Projekt“ am Gesamtprojekt rechnet nur
auf dessen eigene Positionen. Stornierte Teilprojekte fehlen und werden
genannt; Teilprojekte, die du nicht lesen darfst, fehlen ebenfalls, und
die Seite sagt, wie viele. Übernommene Positionen stehen mit
„übernommen“ und „nicht berechnet / berechnet in …“ darin. Die
Preisübersicht eines Teilprojekts zeigt nur dieses, mit dem Hinweis „Teil
von …; Summe aller Teile im Gesamtprojekt“ und einem Link dorthin.

Die Übersicht ist zum Weiterverwenden gebaut: **Ein Klick auf einen Betrag
oder Text kopiert ihn** in die Zwischenablage. „Teilgruppen nur mit
Summen“ blendet die Positionen aus, „Teilgruppen mit allen Positionen“
holt sie zurück. Angebot, Auftragsbestätigung und Rechnung schreibt
Rentalars selbst (Abschnitt 11).

**Als PDF und als CSV.** Oben rechts liefert **„PDF“** die Übersicht als
Datei zum Drucken oder Weitergeben, **„CSV“** dieselben Zahlen für die
Tabellenkalkulation (Semikolon, Dezimalkomma). Beide nehmen die Ansicht, die
gerade gewählt ist: alle Positionen oder nur die Teilgruppen mit ihren
Summen, das Personal als Block oder je Phase und Funktion – beim
Gesamtprojekt mit den Teilprojekten, die du lesen darfst.

**Was in einer Teilgruppe steckt.** Ohne Positionen steht unter jeder
Teilgruppe eine Zeile, die zusammenfasst, was sie enthält:

> **Licht Front-Traverse** – 8 × LED-Scheinwerfer RGBW, 6 × Traverse
> 4-Punkt 2 m, 2 × Kettenzug 500 kg und 3 weitere Positionen … 420,00 €

So weiß der Kunde grob, wofür der Betrag steht, ohne jedes Kabel zu lesen.
Gleiche Produkte werden zusammengezählt, ein Set heißt wie das Set.
Genannt werden höchstens sechs Dinge – die wertvollsten, in der Reihenfolge
der Planung –, der Rest als „und … weitere Positionen“. Zumietungen, die
nur eine Fehlmenge decken, erscheinen nicht; der Kunde sieht die Position,
die sie decken.

Als PDF lässt sich die Preisübersicht einer Mail anhängen (Abschnitt 14) –
beim Gesamtprojekt dann mit allen Teilprojekten, die nicht storniert
sind, wie in Angebot und Rechnung.

### Summen in der Projektliste

Was bringen die Projekte des nächsten Monats ein, wie viele Mannstunden
sind geplant? In der Projektliste (Projekte) lassen sich über **„Spalten“**
(Abschnitt 2, „Listen“) auch Summen einblenden – voreingestellt ist keine
davon:

| Spalte | was darin steht |
|---|---|
| **Geplante Mannstunden** | die geplanten Stunden aller Personalpositionen |
| **Material-Einnahme** | Summe netto ohne das Personal und die Logistik: Teilgruppen, Positionen ohne Teilgruppe, Aufpreise |
| **Personal-Einnahme** | was der Kunde für das Personal zahlt |
| **Logistikumsatz** | was der Kunde für Fahrzeuge und Anhänger zahlt |
| **Summe netto**, **Summe brutto** | wie in der Planung |
| **Material-Kosten** | was die Zumietungen kosten |
| **Personal-Kosten** | was das Personal kostet (geplant) |
| **Logistikkosten** | die internen Kosten der Fahrzeuge und was zugemietete kosten |
| **Gewinn** | der Gewinn aus dem Projekt: Summe netto minus alle Kosten und die freigegebenen Spesen |

Material-, Personal-Einnahme und Logistikumsatz ergeben zusammen die Summe
netto. Ein
**Gesamtprojekt** zeigt die Summe aus sich und seinen Teilprojekten (ohne
stornierte), wie seine Preisübersicht und sein Angebot; jedes Teilprojekt
zeigt in seiner Zeile seine eigenen Summen. Stehen beide in der Liste,
zählt ein Teilprojekt beim Zusammenrechnen der Spalte doppelt.

Wer was sieht, ist wie in der Planung: Einnahmen und Summen nur mit dem
Recht, Preise zu sehen; Material- und Logistikkosten zusätzlich mit dem
Recht für Einkaufspreise; Personal-Kosten mit dem Recht für
Personalkosten; den Gewinn nur mit allen dreien. Die Mannstunden sieht jeder, der die Liste
sieht. Bei Projekten, die du nur über deinen Einsatz kennst, bleiben die
Felder leer. Auch ein Klick auf diese Spalten sortiert – bei
bis zu 2.000 Projekten in der gefilterten Liste; bei mehr bleibt die
Liste in ihrer üblichen Reihenfolge, und ein Hinweis bittet dich, sie mit
den Filtern einzugrenzen (Abschnitt 2, „Listen“). Im CSV-Export stehen sie, wenn sie
eingeblendet sind (oder bei „CSV mit allen Spalten“).

### Auswertungen

Lohnen sich die Projekte, die Kunden, das Material? Dafür steht
in der Seitenleiste **„Auswertungen“** – für alle, deren Rolle das Modul
Auswertungen lesen und alle Projekte lesen darf und die Preise sehen
dürfen. Die Zahlen kommen aus der Kalkulation der
Planung, wie in der Preisübersicht und den Summen der Projektliste
(oben); gespeichert wird nichts.

**Reiter „Profitabilität“.** Oben wählst du ein **„Jahr“** oder einen
Zeitraum („oder ab“ … „bis“) und auf Wunsch **„nur abgeschlossene
Projekte“**, dann „Anzeigen“. Gezählt werden ganze Projekte mit ihren
Teilprojekten ab dem Status „Bestätigt – Preise und Einzelheiten offen“, ohne stornierte,
jeweils in dem Monat, in dem ihr Material zurückkommt; Servicefälle nicht.
Die Seite zeigt

- oben die Summen: Zahl der Projekte, **„Umsatz netto“** (Material,
  Personal und Logistik), **„Kosten“** (Zumietungen, Crew,
  freigegebene Spesen und die Kosten der Fahrzeuge) und den **„Gewinn“** –
  was übrig bleibt – mit seinem Anteil am Umsatz;
- **„Je Monat“** eine Zeile je Monat mit Umsatz, Kosten, Gewinn und
  **„Marge“** in Prozent, dazu Balken für Umsatz und Gewinn;
- **„Je Kunde“** und **„Je Projektleitung“** dasselbe zusammengefasst;
- **„Am meisten übrig“** und **„Am wenigsten übrig“** – die Projekte mit
  dem größten und dem kleinsten Gewinn.

**Kalkulierte Werte.** „Umsatz“ und „Gewinn“ sind hier **kalkuliert**: Sie
stammen aus der Preisplanung der Projekte, nicht aus ausgestellten Rechnungen,
eingegangenen Zahlungen oder gebuchten Ausgaben – die Seite sagt es, und die
Spalten heißen „Kalkulierter Umsatz netto“, „Kalkulierter Gewinn“ und
„Kalkulierte Marge“. Die Bücher findest du unter Buchhaltung.

**„CSV der Projekte“** liefert die Projekte des Zeitraums mit ihren Zahlen
für die Tabellenkalkulation. Wer was sieht, ist wie in der Projektliste:
Kosten und Gewinn zeigt die Seite nur mit den Rechten, Einkaufs- und
Kaufpreise und Personalkosten zu sehen. In der CSV-Datei stehen die Kosten
der Zumietungen und die Logistikkosten schon mit dem Recht für
Einkaufspreise, die der Crew und die Spesen mit dem für Personalkosten, der
Gewinn nur mit beiden; der Logistikumsatz steht neben Material- und
Personal-Einnahme.

**Reiter „Material“** – mit dem Recht, Einkaufs- und Kaufpreise zu sehen:
je Produkt die Zahl der **Exemplare**, ihre **Kaufpreise**, was die
Positionen des Produkts nach Rabatten **eingebracht** haben, und der
**„Anteil am Kaufpreis“** in Prozent. Unter **„Eingenommen in“** wählst du
„Gesamte Zeit“ oder ein Jahr. Wie gerechnet wird – nur Projekte, deren
Material rausging, die Position eines Sets nach Preisen auf seine
Bestandteile verteilt, ein Set aus dem Einkauf mit seinem Preis –, steht in
Abschnitt 4, „Was ein Exemplar einbringt“; dort steht auch der Anteil
jedes einzelnen Exemplars.

---

## 9. Verfügbarkeit, Fehlbestände, Zumietung

### Wie Rentalars rechnet

> **Frei = planbarer Bestand − höchste gleichzeitige Reservierung im Zeitraum**

Es zählt die *höchste gleichzeitige* Belegung, nicht die Summe: Zwei
Projekte, die dieselben sechs Kabel nacheinander nutzen, brauchen sechs
Kabel, nicht zwölf.

> **Beispiel.** Bestand: 9 XLR-Kabel.
> Projekt A (bestätigt) hat 6 Kabel vom 10. bis 12.
> Projekt B braucht Kabel vom 11. bis 13.
> Im Zeitraum von B sind höchstens 6 gleichzeitig weg – **3 sind frei**.
> Bucht B vier Kabel, fehlt eines.

Dabei gilt:

- Gerechnet wird mit **Datum und Uhrzeit**. Was um 10 Uhr zurückkommt, kann
  um 10 Uhr wieder raus.
- **Planbar** ist, was verfügbar oder im Einsatz ist und nicht fest in etwas
  anderem verbaut. Defektes, Gesperrtes und Ausgemustertes zählt nicht.
  Ein Exemplar mit **Sperrzeit** fehlt nur in deren Zeitraum (Abschnitt 4).
- **Fest** reservieren bestätigte Projekte und solche, die unterwegs sind.
  **Optionen**, **optionale Teilgruppen** und **optionale oder alternative
  Positionen** merken nur vor – sie machen andere Positionen „knapp“, nicht
  „rot“. Anfragen reservieren nichts.
- **Sets** belegen ihre Bestandteile. **Cases** belegen ihre losen Inhalte –
  außer denen, die für dieses Projekt herausgelöst sind (Abschnitt 4).
- **Verkauftes** kommt nicht zurück: Es ist ab Projektbeginn dauerhaft weg.
- Ist ein Projekt **überfällig** – noch „unterwegs“, obwohl es zurück sein
  sollte –, gilt sein Material weiter als belegt, und zwar bis es zurückgebucht ist, auch für
  die kommenden Tage.
- **Zurückgenommenes** ist ab der Buchung („Rücknahme buchen“) wieder frei
  für andere Projekte – auch wenn der Rest des Projekts noch unterwegs ist
  (Abschnitt 10, „Zurücknehmen“).
- **Teilprojekte** belegen wie eigene Projekte, jedes mit seinem Zeitraum
  und Status. Brauchen zwei Bühnen desselben Gesamtprojekts gleichzeitig
  dasselbe Material, zeigt das die Fehlmenge – und der Reiter
  „Teilprojekte“ nennt diese Engpässe eigens.
- **Übernommenes Material** (Abschnitt 7, „Teilprojekte“) gilt als
  durchgehend unterwegs, von der früheren Bühne bis zum Ende der späteren,
  ohne Pufferzeiten dazwischen.

Jedes Projekt wird so beurteilt, **als wäre es bestätigt**. Auch eine
Anfrage zeigt deshalb schon, ob das Material reichen würde.

Haben zwei bestätigte Projekte zusammen mehr gebucht, als da ist, zeigen
**beide** die Fehlmenge. Wer zurücksteckt, entscheidet ihr – nicht die
Reihenfolge der Eingabe.

### Pufferzeiten

Material braucht Zeit zum Prüfen, Laden, Reinigen. Unter „Einstellungen →
Firmendaten und Grundeinstellungen“ stellst du ein, wie viele Stunden
**vor** und **nach** jedem Einsatz das Material zusätzlich als belegt gilt
(Voreinstellung: 0). Eine Kategorie kann davon abweichen (Nebelmaschinen
brauchen länger), ein einzelnes Produkt ebenso.

### Die Seite „Fehlbestände“

**Planung → Fehlbestände:** alle offenen Fehlmengen aller laufenden und
kommenden Projekte auf einen Blick: Projekt, Produkt, Zeitraum, fehlende
Stückzahl – auf Wunsch nur die nächsten Wochen oder **nach Produkt**
zusammengefasst („Fehlen höchstens“). Darunter alle **Zumietungen** mit
Lieferant und Status; ein Klick auf den Namen eines Lieferanten öffnet die
Seite „Zumietung bei …“ des Projekts (unten, „Zumieten“), ohne Lieferant
steht dort „offen“. Der Filter **„Lieferant“** zeigt nur die Zumietungen
bei einem Lieferanten („Zumietungen bei Verleih Nord“) – dorthin führt auch
„Zumietungen bei diesem Lieferanten anzeigen“ in seinen Stammdaten. Ein
guter Start in den Tag für alle, die
disponieren; die ersten offenen Fehlbestände stehen auch auf der
Startseite (Abschnitt 2), und unter Projekte → Offene Punkte steht jeder
bei seinem Projekt (Abschnitt 7, „Zeitplanung“). Neue Fehlbestände meldet
Rentalars außerdem der Projektleitung – wann und wie weit voraus, steht
unter Einstellungen → Benachrichtigungen (voreingestellt jeden Tag um
4:15 Uhr für die kommenden vier Wochen; Abschnitt 16).

Die Verfügbarkeit des Materials ist ein **Sonderrecht**:
„Verfügbarkeit von Material sehen“. Ohne dieses Recht fehlen die Seite
Fehlbestände, die Materialauslastung, die Ampeln, der Kasten
„Verfügbarkeit“ und der Zeitstrahl von Produkten und Material, die
Fehlbestände auf der Startseite und unter den offenen Punkten, und
Meldungen über Fehlbestände kommen nicht. Alle mitgelieferten Rollen außer
Crew haben es (Abschnitt 16, „Rollen und Rechte“).

Fehlt einem Teilprojekt etwas, weil andere Teilprojekte desselben
Gesamtprojekts das Material zur selben Zeit belegen, steht dabei **„davon
belegt durch andere Teilprojekte: N“** – mit einem Link zum Reiter
„Teilprojekte“. Werden die Stücke nicht gleichzeitig, sondern nacheinander
gebraucht und stehen nur die Pufferzeiten im Weg, hilft eine Übernahme
(Abschnitt 7).

**Ein Ersatzprodukt statt Zumieten**. Habt ihr am Produkt Ersatz
eingetragen (Abschnitt 5, „Zubehör und Ersatz“), nennt die Planung bei einer
knappen Position die Ersatzprodukte, mit der Zahl der Stücke, die im Zeitraum
frei sind: **„Ersatz hinzufügen“** legt sie als neue Position an (Abschnitt 7,
„Zubehör und Ersatz in der Planung“). Die knappe Position bleibt dabei, wie sie
war – die Fehlmenge steht auf dieser Seite, bis du sie verkleinert oder
gelöscht hast. Die Hinweise sieht nur, wer „Verfügbarkeit von Material
sehen“ hat.

### Zumieten

Fehlt etwas, bietet die rote Position einen Knopf an: **„2 × L-010
zumieten“** – außer bei Kundenmaterial, das niemand anderes liefern kann
(„Kundenmaterial lässt sich nicht zumieten.“). Er öffnet ein Fenster „Zumietung anlegen“, in dem du
einträgst:

- **Menge** – vorgeschlagen ist die Fehlmenge.
- **Lieferant** – tippen: Rentalars schlägt passende Lieferanten aus den
  Händlern vor (Einstellungen → Händler), nach Name, Ansprechpartner oder
  E-Mail. Gibt es ihn noch nicht, wähl den letzten Vorschlag **„„…“ als
  neuen Lieferanten anlegen“**: Ein zweites Fenster „Neuer Lieferant“
  öffnet sich über der Zumietung, mit dem Getippten als Namen; du trägst
  Ansprechpartner, E-Mail, Telefon und „unsere Kundennummer dort“ ein und
  drückst „Lieferanten speichern“ – alles, was du in der Zumietung schon
  eingetragen hast, bleibt stehen. Leer lassen geht auch, solange noch
  niemand gefragt ist.
- **Einkaufspreis je Einheit** – was der Lieferant für den ganzen Zeitraum
  berechnet. Dafür braucht es das Recht, Einkaufspreise zu sehen.
- **Status**: **offen** (voreingestellt) → angefragt → bestellt → erhalten
  → zurück. Jeder Status außer „offen“ braucht einen Lieferanten („Ohne
  Lieferanten kann der Status nur „offen“ sein.“) – „angefragt“ bei
  niemandem gibt es nicht.

Einen Mietpreis fragt das Fenster nicht: Der Kunde zahlt die ursprüngliche
Position zum normalen Preis, die Zumietung selbst wird ihm **nicht
berechnet**. „Zumietung anlegen“ – und die Fehlmenge ist verschwunden.

Die Zumietung steht danach **eingerückt direkt unter ihrer Position**, als
Teil von ihr und nicht als weitere Position: „↳ davon 2 zugemietet bei
Verleih Nord · bestellt · EK 15,00 € je Stk. (30,00 €)“. Sie hat keinen
eigenen Betrag und kein Kopiersymbol. Mit Stift und Papierkorb in dieser
Zeile bearbeitest oder löschst du sie; der Dialog hat Bezeichnung, Menge,
Zeitraum, Lieferant, Status, Einkaufspreis, **„Wird beim Lieferanten
abgeholt“** und Notiz, aber keine Teilgruppe und keine Preise. Den Haken
setzt du, wenn ihr das Material selbst beim Lieferanten holt und
zurückbringt – dann gehören Abholung und Rückgabe zu den Fahrten des
Projekts (Abschnitt 7, „Die Fahrten eines Projekts“); ohne Haken bringt
und holt der Lieferant. Verschiebst du die Position – ziehen, über
den Dialog oder mit der Auswahl –, wandert die Zumietung mit. Der
Einkaufspreis geht in die Kosten des Projekts und damit in den Gewinn aus
dem Projekt ein. Kopierst du eine Zumietung – mit dem Projekt, mit ihrer
Teilgruppe oder als Position –, steht die Kopie auf „offen“.

**Zumieten ohne Fehlmenge** – etwas, das ihr gar nicht im Bestand habt:
Füge das Produkt `E-001 Zumietung` wie jede andere Position hinzu, gib ihr
im Dialog eine sprechende Bezeichnung („Hazer Tour Hazer II“), Preis für
den Kunden, Lieferant und Einkaufspreis.

**Die Seite „Zumietung bei …“.** Der Name des Lieferanten an einer
Zumietung – in der Planung und unter Planung → Fehlbestände – öffnet die
Seite **„Zumietung bei Verleih Nord“** dieses Projekts. Sie gehört zur
Planung („Planung“ oben führt zurück) und zeigt oben die Angaben des
Lieferanten – Ansprechpartner, E-Mail, Telefon, eure Kundennummer dort und
seine Anschrift mit „Route in Google Maps“ von deinem Standort aus und
„Karte anzeigen“ (Abschnitt 6, „Route und Karte“); „Lieferanten bearbeiten“ hat,
wer die Einstellungen ändern darf –, dann drei Teile:

- **„Zugemietet“:** alles, was ihr für dieses Projekt bei ihm zugemietet
  habt, mit Zeitraum, Status und **„Abholung“** – angehakt „Wird beim
  Lieferanten abgeholt“, sonst „wird geliefert“ –, mit dem Recht für
  Einkaufspreise auch dem „Einkaufspreis je Einheit“, dem „Einkauf“ je
  Zeile und „Einkauf gesamt“. Status, Abholung und Einkaufspreise änderst
  du hier für alle Zeilen auf einmal: **„Status, Abholung und Preise
  speichern“**.
- **„Dokumente des Lieferanten“:** Angebote, Auftragsbestätigungen,
  Lieferscheine und Rechnungen. Unter **„Dokument ablegen“** die Datei
  wählen, die **„Art des Dokuments“** (Angebot, Auftragsbestätigung,
  Lieferschein, Rechnung, Sonstiges) und auf Wunsch einen Titel,
  „Hochladen“. Die Dokumente stehen auch im Reiter „Dokumente“ bei den
  Dateien des Projekts (Abschnitt 11); die Crew sieht sie nicht.
- **„Korrespondenz“:** die Mails des Projekts von und an die
  E-Mail-Adresse des Lieferanten – sie erscheinen von selbst, beim Abruf
  wie beim Senden. **„Mail schreiben“** schreibt ihm, mit seiner Adresse
  als Empfänger, „Zumietung für …“ und dem Kürzel des Projekts im Betreff;
  die Antworten kommen ins Projekt und stehen hier. Gehört eine Mail von
  einer anderen Adresse dazu, ordnest du sie auf der Seite der Mail unter
  **„Gehört zu einer Zumietung?“** zu (Abschnitt 14). Hat der Lieferant
  noch keine E-Mail-Adresse, sagt die Seite es; trag sie in den Stammdaten
  ein (Abschnitt 16, „Stammdaten“).

Lesen darf die Seite, wer die Planung des Projekts lesen darf; Status,
Preise und Dokumente ändern, wer das Projekt bearbeiten darf, solange es
nicht abgeschlossen ist. Einkaufspreise, Mails und das Schreiben von Mails
brauchen ihre Sonderrechte wie überall.

**Zumietung nicht mehr nötig.** Wird die gedeckte Position kleiner oder
kommt eigenes Material frei, weist die Planung darauf hin: „Eine Zumietung
wird nicht mehr in voller Höhe gebraucht“. Rentalars löscht sie nicht von
selbst – die Bestellung beim Lieferanten läuft vielleicht schon.

Zugemietetes Material erscheint auf der Packliste mit dem Hinweis
„Zumietung“ und dem Lieferanten.

---

## 10. Packen, Ausgabe, Rücknahme

*Für alle mit Zugriff auf „Packen und Ausgabe“. Die Seite ist für das
Telefon gebaut: große Tasten, auch mit Handschuhen zu treffen.*

Der Grundsatz: **Gepackt wird nach Produkt und Menge.** Niemand muss
einzelne Exemplare heraussuchen oder scannen. „12 × XLR-Kabel 5 m“ heißt:
zwölf aus dem Regal nehmen, abhaken. Wo es doch auf das einzelne Stück
ankommt – das Rack mit seinem Inhalt, das Gerät mit der Prüfung –, kannst
du Exemplare wählen; nötig ist es nie.

Ausgabe und Rücknahme laufen gleich: **abhaken, dann buchen**. Beim Packen
hakst du ab, was gepackt ist, und „Ausgeben“ bucht es aus dem Lager; bei
der Rücknahme hakst du ab, was zurück ist, und „Rücknahme buchen“ bucht es
ins Lager. Beides geht in Teilen und nebeneinander.

Ohne Netz – im Lkw, in der Halle ohne Empfang – hakst du mit der
**Rentalars-App für Android** ab; sobald das Telefon wieder Netz hat,
kommen die Haken hier an. Ausgeben und „Rücknahme buchen“ bleiben ein
Schritt im Browser (Abschnitt 2, „Die Rentalars-App für Android“).

### Die Packliste

Reiter **Packliste** im Projekt. Sobald ein Projekt bestätigt ist
(„Bestätigt – Preise und Einzelheiten offen“, „Bestätigt“) oder unterwegs ist, hat es seine
Packliste – auch wenn sie noch niemand geöffnet hat, damit die
Companion-App sie findet. Die Liste entsteht aus der Planung und ist
immer auf deren Stand:

- eine Zeile je Produkt und Position, gegliedert nach Teilgruppen und
  ihren Untergruppen;
- **Sets sind aufgelöst** in ihre Bestandteile („4 × Aktivbox 12 Zoll, aus
  4 × Aktivbox-Set“);
- Dienstleistungen, Nebenkosten und Aufpreise fehlen – sie lassen sich
  nicht einpacken;
  ebenso optionale und alternative Positionen und Teilgruppen, solange sie
  nicht auf „normal“ stehen (Abschnitt 7);
- Verkaufsware und Zumietungen sind markiert, Übernahmen aus anderen
  Teilprojekten ebenfalls (unten, „Übernahme und Übergabe zwischen
  Teilprojekten“), Material des Kunden mit **„Kundenmaterial – wird
  mitgeführt“** – mit Gewicht, Volumen und Lagerort wie euer eigenes
  (Abschnitt 5, „Kundenmaterial“);
- die Notiz der Position steht dabei – und der **Wunsch** nach einem
  bestimmten Modell oder Exemplar („Wunsch: 0742“). Die Zeile nennt
  genau die gewünschten Exemplare mit ihrem Lagerplatz („Gewünscht: 0742
  XLR-Kabel, 01-A-1“), bei einer Position aus mehreren Stück mit „3 von 10
  Stück“ (Abschnitt 7, „Ein bestimmtes Modell oder Exemplar“); auch das PDF
  und die Schnittstelle tun es;
- Mengenmaterial, das in einem Rack oder Case **verbaut** ist (Abschnitt 4),
  steht unter diesem als **„enthält 10 m × Kabel“** – es geht mit und zählt
  nicht noch einmal als eigene Zeile.

Unter einer Zeile stehen, wo nötig, **Hinweise** für das Lager:

- „auch in: Halle 2 > Regal C“ – bei der Reihenfolge nach Lagerort, wenn
  das Produkt an mehreren Orten liegt;
- „lose in Geräten: 0123 in 0500“ – Stücke, die gerade in einem Case
  liegen;
- „2 Exemplar(e) im Bestand mit überfälliger Prüfung“ (Abschnitt 4,
  „Prüfungen“);
- „0123 Funkmikrofon bleibt da (aus 0500 herausgelöst)“ – an der Zeile des
  Cases, wenn ein Inhalt für dieses Projekt im Lager bleibt (Abschnitt 4).

**PDF zum Drucken** (oben rechts) erzeugt die Liste für das Klemmbrett: mit
Firmenkopf, Kästchen zum Abhaken und Feldern für Unterschrift und Datum –
in der Reihenfolge, die du gewählt hast, mit Gewicht und Volumen und, wenn
eingeblendet, mit dem Inhalt der Geräte.

**„Verladen in“**. Sind im Projekt Fahrzeuge gebucht
(Abschnitt 7, „Logistik“), wählst du unten auf der Packliste bei
**„Verladen in“**, in welches Fahrzeug sie geladen wird, und speicherst.
Der Kopf der Packliste und ihr PDF nennen es dann. Hat das Projekt mehrere
Packlisten – etwa eine je LKW (unten) –, wählst du es für jede. Das darf,
wer packen darf, solange die Packliste nicht zurückgenommen ist.

### Reihenfolge, Gewicht und Inhalt

Über der Liste wählst du unter **„Reihenfolge“**, wie die Zeilen sortiert
sind:

- **„Teilgruppen“** – wie in der Planung (voreingestellt);
- **„Kategorie“** – alle Kabel zusammen, alle Scheinwerfer zusammen;
- **„Lagerort“** – gruppiert nach dem Ort, an dem die meisten Stück des
  Produkts liegen, mit dem Ort an jeder Zeile. Das ergibt den **Laufweg**
  durchs Lager; was keinen Lagerort hat, steht am Ende unter „Ohne
  Lagerort“.

Die Wahl gilt für alle Packlisten und auch für das PDF, bis du sie änderst
oder dich abmeldest.

**„Inhalt der Geräte zeigen“** listet unter einem Rack oder Case, was darin
steckt, eingerückt – für gewählte Exemplare oder wenn es von dem Produkt
nur eines gibt. „Inhalt der Geräte ausblenden“ macht die Liste wieder kurz.

**Gewicht und Volumen.** Über der Liste steht, was die Ladung ungefähr
wiegt und wie viel Platz sie braucht – „ca. 412 kg, 1.830 l“ –, an jeder
Teilgruppe ihr Gewicht. Gerechnet wird mit Gewicht und Maßen der Modelle
(Abschnitt 4); hat ein Produkt Modelle verschiedenen Gewichts, zählt das
schwerste, damit die Summe nie zu leicht für den LKW ist. Fehlen bei
einigen Zeilen die Angaben, steht dabei, wie viele („3 Zeilen ohne
Gewicht“) – die Summe ist dann eine Untergrenze.

### Mehrere Packlisten

**Wann mehrere Packlisten?** Du brauchst sie nicht: Eine Packliste je
Projekt ist der Normalfall, und jedes Projekt hat sie von selbst. Mehrere
lohnen sich, wenn das Material eines Projekts in getrennten Ladungen das
Lager verlässt – zum Beispiel

- **zwei LKW**, die getrennt beladen werden und zu verschiedenen Zeiten
  fahren;
- **Ton und Licht** aus verschiedenen Hallen oder Lagern, von
  verschiedenen Leuten gepackt;
- eine **Vorabladung** – Traversen und Rigging Tage vor dem Rest, weil der
  Aufbau früher beginnt.

Dann hat jede Ladung ihre eigene Packliste mit eigener Bezeichnung
(„LKW 2“), eigenem Hinweis, eigenem Verladetermin, eigenem PDF und eigenem
Stand – gepackt, ausgegeben, zurück. Jede wird für sich ausgegeben, Artikel
für Artikel (unten, „Ausgeben“), und für jede lässt sich ein eigener
Lieferschein erstellen (Abschnitt 11). Eine Ladung, die nur später fährt,
aber von denselben Leuten am selben Ort gepackt wird, braucht keine eigene
Packliste: Dafür reicht die Teilausgabe.

So teilst du auf:

1. Über der Packliste steht für jede Packliste ein Reiter (bei einem
   Gesamtprojekt und seinen Teilprojekten dazu die übrigen Teile, unten
   „Die Packliste des Gesamtprojekts“). **„+ Packliste“** daneben fragt nach **Bezeichnung** („LKW 2“), **Verladen** (Datum und
   Uhrzeit) und **Notiz**; „Packliste anlegen“.
2. Eine neue Packliste ist zunächst leer. **„Positionen verteilen“** zeigt
   alle Positionen des Projekts mit Teilgruppe und Menge; je Position
   wählst du die Packliste, „Verteilung speichern“. Jede Position steht auf
   genau einer Packliste. Haken einer verschobenen Position entfallen;
   Positionen, deren Material schon ausgegeben ist, bleiben, wo sie sind.
3. Neue Positionen aus der Planung landen auf der ersten Packliste.

Unten auf einer weiteren Packliste klappt **„Packliste bearbeiten oder
löschen“** auf: Bezeichnung, Verladen und Notiz ändern („Speichern“), oder
„Packliste löschen“ – ihre Positionen kommen dann zurück auf die erste.
Die Felder dort sind gewöhnliche Textfelder wie überall, und die
beiden Knöpfe stehen gleich groß nebeneinander. Die erste
Packliste lässt sich nicht löschen, eine ausgegebene auch nicht.

Jede Packliste wird für sich gepackt, ausgegeben und zurückgenommen. Das
Projekt geht auf „Unterwegs“, sobald **alles** unterwegs ist, also jede
Packliste mit Material aus dem Lager vollständig ausgegeben – eine leere
Packliste oder eine nur mit Übernahmen aus anderen Teilprojekten hält es
nicht auf. Bis dahin sagt eine ausgegebene Packliste: „Das Projekt bleibt
„Bestätigt“, bis auch das Material seiner anderen Packlisten ausgegeben
ist.“ Auf „Wieder im Lager“ geht es, wenn keine Packliste mehr unterwegs
ist und keine mehr auf ihre Ausgabe wartet. Einen Lieferschein gibt es je
Packliste oder für alle zusammen (Abschnitt 11).

### Packen

- **Der große Haken** rechts hakt die ganze Zeile ab. Noch einmal tippen
  nimmt den Haken zurück.
- **Das Zahlenfeld** daneben ist für Teilmengen: 8 von 12 gepackt.
- **„Alle Zeilen abhaken“** unten, wenn alles beisammen ist.

Der Status der Packliste wechselt von „offen“ über „in Arbeit“ zu
„gepackt“.

**Der Balken** oben auf der Packliste zeigt vom Packen bis zur Rücknahme,
wo die Stücke sind. Er füllt sich von links:

| Farbe | heißt |
|---|---|
| orange | zurückgenommen – wieder im Lager gebucht oder an ein späteres Teilprojekt übergeben |
| orange schraffiert | als zurück abgehakt, noch nicht gebucht |
| grün | ausgegeben und noch unterwegs |
| grün schraffiert | gepackt (abgehakt), noch nicht ausgegeben |
| grau | im Lager |

Darunter steht dasselbe in Worten und Zahlen, jeweils mit seinem Farbfeld –
etwa „4 zurückgenommen“, „2 zurück abgehakt“, „30 ausgegeben“, „6
gepackt“, „21 im Lager“; was es gerade nicht gibt, fehlt.

### Exemplare wählen

Meist ist es gleich, welches der zwölf Kabel rausgeht. Manchmal nicht: Das
Funkrack 0500 soll es sein, weil sein Inhalt mitgehen soll; das Gerät mit
frischer Prüfung; das Stück, dessen Verlauf ihr verfolgen wollt. Dafür hat
jede Zeile (außer Mengenmaterial und Zumietungen) den Link **„Exemplare
wählen“**.

Er öffnet eine Liste der Exemplare des Produkts. Dabei steht, was zu
beachten ist – „bei 2026-0041“, „in 0500“, „Prüfung überfällig“.
Exemplare, die für ein anderes Projekt gewählt oder mit ihm unterwegs sind,
lassen sich nicht ankreuzen, ebenso wenig Exemplare, die aus diesem
Projekt schon zurückgekommen sind („aus diesem Projekt zurückgekommen“) –
sie gehen darin nicht noch einmal raus (unten, „Zurücknehmen“).
Ankreuzen, höchstens so viele, wie die Zeile
braucht, „Auswahl speichern“. Die IDs stehen danach an der Zeile; ein
Exemplar mit überfälliger Prüfung ist hervorgehoben, und Rentalars warnt
schon beim Speichern. „Exemplare ändern“ ändert die Auswahl, solange die
Packliste nicht vollständig ausgegeben ist.

Was die Wahl bewirkt:

- Bei der Ausgabe gehen **genau diese Exemplare** raus; für die übrigen
  Stück der Zeile gilt, was unter „Ausgeben“ steht.
- Der **Inhalt** eines gewählten Racks oder Cases geht mit aus und kommt
  mit der Rücknahme zurück – fest Verbautes immer, lose Enthaltenes, sofern
  es nicht für dieses Projekt herausgelöst ist.
- Die **Prüfung** wird bei der Ausgabe geprüft: Geht ein Exemplar mit
  überfälliger Prüfung raus, sagt Rentalars es („0742 ist ausgegeben,
  obwohl seine Prüfung überfällig ist.“).

### Scannen beim Packen und bei der Rücknahme

Über der Packliste steht, wenn du packen darfst, ein Feld: beim
Packen **„Exemplar ist gepackt: ID scannen oder eintippen“**, bei der
Rücknahme **„Exemplar ist zurück: ID scannen oder eintippen“**. Du tippst die
ID (oder den Inhalt des Etiketts) ein oder liest sie mit dem Handscanner –
beides lässt sich mit **„Zählen“** oder Enter abschicken – oder du drückst
**„Scannen“** und hältst das Etikett vor die Kamera (Abschnitt 4,
„Scannen“, auch zu den Grenzen der Kamera). Der Dialog bleibt offen für das
nächste Etikett. **Freiwillig ist es immer:** Das Abhaken von Hand (oben,
„Packen“) bleibt möglich; das Scannen zählt nur dasselbe Häkchen
hoch.

**Packen.**

- Rentalars sucht die Zeile des Produkts, wählt das Exemplar für sie
  („Exemplare wählen“, oben) und zählt es: „0042 gepackt: 4 von 6 bei XLR-Kabel“.
  Bei einem Produkt aus mehreren Stück (Abschnitt 5) zählt ein Stück, wenn
  alle seine Exemplare gelesen sind: „0042 gepackt: Exemplar 4 von 10 bei
  Kabelpaket (0 von 1 Stück)“.
- Dasselbe Etikett zweimal zu lesen zählt **nicht doppelt** („0042 ist für XLR-Kabel
  schon gezählt“).
- Gescannte Exemplare gehen bei der Ausgabe **als erste** raus.
- Rentalars **verweigert** und sagt warum, wenn das Exemplar auf keiner Zeile
  dieser Packliste steht, **defekt oder gesperrt** ist („kann nicht gepackt
  werden: Der Status ist …“), für ein anderes Projekt vorgesehen oder dort
  unterwegs ist oder alle Exemplare der Zeile schon gewählt sind. Eine
  **überfällige Prüfung** verweigert es nicht, es warnt nur.
- Steckt das Exemplar in einem Case, das auf der Packliste steht, sagt
  Rentalars, dass es mit ihm hinausgeht. **Mengenmaterial** bestätigst du mit
  seiner Stückzahl in der Zeile – ein Scan zeigt nur auf die Zeile.

**Rücknahme.** Ein gelesenes Exemplar zählt als zurück („0042 ist zurück: 5 von
6 bei XLR-Kabel“), einmal, egal wie oft du den Code liest. Es muss mit **dieser**
Packliste hinausgegangen sein; sonst sagt Rentalars „Hake die Position von Hand
ab“. Kam es in einem Case, kommt es mit ihm zurück. Das Buchen der Rücknahme
bleibt ein eigener Schritt (unten, „Zurücknehmen“).

Die Etiketten, die Rentalars druckt (Abschnitt 4, „Etiketten“), sind dafür
gemacht: Der QR-Code und der Strichcode tragen die ID.

### Material beim Packen ergänzen

Beim Packen fällt auf, dass noch zwei Kabeltrommeln fehlen? Unten auf der
Packliste steht das Feld **„Material beim Packen ergänzen“**: Produkt
suchen, Menge eintragen, **„Als Nachtrag ergänzen“**.

Die Position kommt in die Planung des Projekts – mit der Notiz „Beim
Packen ergänzt“ und mit Preis wie jede andere – und auf diese Packliste,
gleich als gepackt. Auf der Packliste und im PDF ist sie als **„Nachtrag“**
markiert. Reicht der Bestand nicht, sagt Rentalars es („Fehlmenge: 2 ×
F-020 sind im Zeitraum nicht frei.“). Ergänzen lässt sich nur Material,
keine Dienstleistung, keine Nebenkosten und kein Aufpreis – und nur,
solange nicht alles ausgegeben ist.

Material nachtragen darf, wer das Projekt ändern darf oder für alle
Projekte packt – etwa Lager und Projektleitung. Allen anderen zeigt
Rentalars an der Stelle des Feldes den Hinweis „Material nachtragen dürfen
nur Personen, die das Projekt ändern dürfen oder für alle Projekte packen.“

### Packen mit der Rolle Crew

Mit der Rolle Crew packst du in deinen eigenen Projekten – im
Browser und in der App, auch ohne Netz: abhaken (auch per Scan), Stücke
wählen, ausgeben und zurücknehmen, fehlende Teile klären, Defekte melden,
weitere Packlisten anlegen, umbenennen und löschen, Positionen zwischen
Packlisten verschieben, Übergaben buchen, Teile aus Behältern nehmen.
Material nachtragen kannst du nicht: Du packst 1:1, was auf der Packliste
steht. Mehrmaterial tragen Personen nach, die das Projekt ändern dürfen
oder für alle Projekte packen; an der Stelle des Feldes steht dann dieser
Hinweis. In der App wird eine Menge über der Packliste abgelehnt, deine
übrigen Häkchen kommen an.

Nichts davon ändert, was das Projekt kostet: Abhaken geht nie über die
Packliste hinaus, fehlende Teile klären ist nur eine Notiz (für Einzelstücke, die nicht zurückkamen, sperrt Rentalars beim Abschluss der Rücknahme das Exemplar, damit es nicht dem nächsten Projekt zugesagt wird; bei Mengenmaterial weist es darauf hin, die Menge zu verringern, wenn die Stücke endgültig verloren sind), beim Löschen
einer Packliste wandern ihre Positionen auf die erste, und eine Übergabe
zwischen Teilprojekten wird nur einmal berechnet – beim Teilprojekt, von
dem das Material kommt. Soll die Crew bei euch nicht packen, stellt ein
Administrator an der Rolle Crew „Packen und Ausgabe“ auf „lesen“
(Abschnitt 16, „Rollen und Rechte“).

### Änderungen nach Packbeginn

Ändert jemand die Planung, während schon gepackt wird, soll das Lager es
merken. Rentalars hebt die Änderungen hervor:

- eine **neue** Zeile mit „neu“,
- eine geänderte Menge mit „war 12“ – die Menge vor der Änderung,
- eine **entfallene** Zeile oben im Kasten „Die Planung hat sich seit
  Packbeginn geändert.“, durchgestrichen und mit „nicht mehr nötig“ –
  war schon etwas gepackt, steht dabei „4 gepackt, zurücklegen“.

„neu“ und „war 12“ stehen auch im PDF. Die Hinweise bleiben, bis jemand
aus dem Lager **„Änderungen erledigt“** drückt.

### Ausgeben

Du gibst aus, was du abgehakt hast – Artikel für Artikel, so wie es auf
den LKW geht. Unten auf der Packliste stehen zwei Knöpfe:

- **„Ausgeben“** bucht genau das Abgehakte mit den abgehakten Mengen aus
  dem Lager. Daneben steht, wie viel rausgeht („12 abgehakte Stück gehen
  raus.“). Ist noch nichts Neues abgehakt, lässt sich der Knopf nicht
  drücken.
- **„Alles ausgeben“** bucht jede Zeile mit voller Menge, auch was nicht
  abgehakt ist – für den Fall, dass auf Papier gepackt wurde; Rentalars
  fragt vorher nach. Ist schon alles abgehakt, fehlt dieser Knopf, denn
  „Ausgeben“ tut dann dasselbe.
- Verkaufsware wird dauerhaft aus dem Bestand genommen (Abschnitt 5,
  „Verbrauchsmaterial und Mindestbestand“).
- Das Projekt wechselt auf **„Unterwegs“**, sobald alles ausgegeben ist –
  bei mehreren Packlisten, wenn alle ausgegeben sind.

Welche Exemplare rausgegangen sind: zuerst die gewählten, dann ein
gewünschtes Exemplar; im Übrigen merkt Rentalars sie sich dort, wo es von
selbst weiß, welche es sein müssen – etwa weil alle Exemplare eines
Produkts rausgehen. Sie stehen dann auf „im Einsatz“, und ihr Verlauf
zeigt das Projekt.

Nach der Ausgabe ist das Material **unterwegs** – so steht es an jeder
Zeile, und so bleibt die Liste: ruhig und ohne Rot. Unterwegs ist nicht
dasselbe wie fehlend.

**Teilausgabe.** Der erste LKW fährt heute, der Rest morgen? Hake ab, was
heute rausgeht, und drück „Ausgeben“. Die Packliste steht dann auf
**„teilweise ausgegeben“** (gelb) und sagt oben, wie viel unterwegs ist und
wie viel noch fehlt („Teilweise ausgegeben: 14 von 63 Stück sind unterwegs.
49 Stück sind noch nicht ausgegeben.“). Du packst einfach weiter:

- Eine Zeile, die vollständig unterwegs ist, ist grau und mit
  **„ausgegeben“** markiert. Sie hat keinen Haken mehr.
- Eine Zeile, von der erst ein Teil unterwegs ist, zeigt „4 von 6
  ausgegeben“. Hake den Rest ab, sobald er gepackt ist.
- Ist der Rest gepackt, bucht „Ausgeben“ ihn aus. „Alles ausgeben“ bucht
  den ganzen Rest auf einmal.

Oben wechselst du zwischen **„Packen/Ausgabe“** und **„Rücknahme“**. So
lässt sich zurücknehmen, was schon unterwegs ist, während der Rest noch
gepackt und ausgegeben wird – auch mehrmals hin und her: ausgeben,
zurücknehmen, wieder etwas ausgeben, später wieder zurücknehmen. Was
schon zurückgenommen ist, zählt dabei als erledigt und geht in diesem
Projekt nicht noch einmal raus; was noch nicht ausgegeben war, packst und
gibst du weiter aus. Beispiel: 10 geplant, 6 ausgegeben, 4 davon
zurückgenommen – diese 4 sind erledigt, 2 sind noch unterwegs, und die
übrigen 4 kannst du noch ausgeben. Bis alles ausgegeben ist, behält das
Projekt seinen Status, und die
Packliste sagt es („Das Projekt bleibt „Bestätigt“, bis alles ausgegeben
ist.“). Das ausgegebene Material gilt trotzdem sofort als unterwegs: Es ist
für andere Projekte nicht frei, und auf der Startseite steht das Projekt
unter „Gerade unterwegs“, mit dem Hinweis „teilweise ausgegeben“. Im PDF
steht an jeder Zeile, was schon ausgegeben ist.

Wird der Rest nicht mehr gebraucht, schließ die Rücknahme ab („Rücknahme
abschließen“ in der Ansicht „Rücknahme“, unten): Was nicht ausgegeben
wurde, bleibt im Lager, und das Projekt geht auf „Wieder im Lager“.
Ändert sich die Planung nach der Ausgabe, drück „Änderungen erledigt“.
Fällt der Rest weg, steht die Packliste danach auf „ausgegeben“. Kommt eine
Position dazu, steht sie wieder auf „teilweise ausgegeben“, und die neue
Position lässt sich packen und ausgeben.

**Versehentlich ausgegeben?** „Ausgabe zurücknehmen“ macht alle Ausgaben
dieser Packliste rückgängig, solange noch nichts als zurück abgehakt ist.
Die Haken bleiben. Das Projekt hat danach wieder den Status von vor der Ausgabe – eine Option bleibt eine Option.

### Zurücknehmen

Kommt das Material zurück, öffnest du dieselbe Seite – nach einer
Teilausgabe mit **„Rücknahme“** oben. Sie zeigt jetzt die ausgegebenen
Mengen. Die Rücknahme geht wie die Ausgabe: erst abhaken, dann buchen.

- **Haken** für „vollständig zurück“, **Zahlenfeld** für Teilmengen.
- **„Alles ist zurück“** hakt alles ab, was unterwegs ist.
- **„Rücknahme buchen“** unten bucht genau das Abgehakte ins Lager. Daneben
  steht, wie viel zurückkommt („6 abgehakte Stück kommen zurück.“); ist
  nichts Neues abgehakt, lässt sich der Knopf nicht drücken.

Das geht, sobald etwas unterwegs ist – auch während der Rest noch gepackt
und ausgegeben wird (oben, „Teilausgabe“). Was gebucht ist, ist **sofort
wieder frei** für andere Projekte (Abschnitt 9). Ist eine Zeile ganz
zurückgenommen, stehen ihre Exemplare – samt Inhalt – wieder auf
„verfügbar“, und die Zeile hat keinen Haken mehr; solange erst ein Teil
einer Zeile zurück ist, bleiben ihre Exemplare „im Einsatz“, denn welche
davon zurück sind, weiß Rentalars nicht. Ein gebuchtes Stück lässt sich
nicht mehr „ent-haken“, und es geht **in diesem Projekt nicht noch einmal
raus**: Rentalars wählt ein zurückgekommenes Exemplar nicht wieder aus,
und „Exemplare wählen“ bietet es nicht an.

An jeder Zeile steht, wie weit sie ist: „2 von 6 zurückgenommen“, „2 noch
nicht gebucht“ (abgehakt, aber noch nicht gebucht) oder „zurückgenommen“,
wenn alles zurück ist. Eine Zeile, von der erst ein **Teil** zurück ist,
wird gelb hervorgehoben und sagt, was offen ist („4 Stück sind nicht
zurück“) – damit du siehst, wo du noch nicht fertig bist. Nach einer
Teilausgabe steht an Zeilen, die nie rausgegangen sind, „nicht
ausgegeben“; sie brauchen keinen Haken.

**Fertig von selbst.** Ist nach dem Buchen nichts mehr unterwegs und wartet
nichts mehr auf seine Ausgabe oder Übergabe, ist die Rücknahme der
Packliste abgeschlossen – du musst nichts weiter tun. Die Packliste steht
dann auf „zurückgenommen“, und das Projekt geht auf „Wieder im Lager“, sobald
keine seiner Packlisten mehr unterwegs ist (unten).

**Kommt etwas nicht zurück**, trägst du an der Zeile ein, was damit ist –
„Kabel defekt, bleibt in der Werkstatt“, „beim Kunden vergessen, wird
Freitag gebracht“ – und drückst **„Vermerken und Zeile abschließen“**. Das
Feld dafür steht an teilweise zurückgenommenen Zeilen offen; an allen
anderen klappt es unter **„Kommt nicht zurück?“** auf.

**Defekt bei der Rücknahme.** Fällt beim Auspacken ein Schaden auf, klappst
du unten **„Defekt eines zurückgenommenen Exemplars melden“** auf: die
**ID** des Exemplars (die Liste schlägt die ausgegebenen vor), „Was ist
defekt?“ und auf Wunsch ein **Foto** – am Telefon öffnet sich die Kamera –,
dann „Defekt melden“. Das Exemplar steht sofort auf „defekt“, das Lager
bekommt Bescheid, die Meldung steht am Exemplar mit dem Vermerk
„Rücknahme 2026-0042“, und wird daraus wie aus jeder
Defektmeldung ein Servicefall (Abschnitt 4, „Defekt melden“). Melden lässt sich
jedes Exemplar eines Produkts dieser Packliste – auch wenn nicht vermerkt
ist, welches der zwölf Kabel rausging.

**„Rücknahme abschließen“** steht unter der Liste, mit der Frage „Kommt
etwas nicht zurück, oder wird der Rest nicht mehr ausgegeben?“. Du
brauchst es nur, wenn die Rücknahme nicht von selbst fertig wird: wenn
Fehlteile an ihrer Zeile vermerkt sind oder wenn nach einer Teilausgabe
der Rest nicht mehr rausgeht. Es bucht, was noch abgehakt und nicht
gebucht ist, gibt das Material der Packliste wieder frei und setzt das
Projekt auf **„Wieder im Lager“**, sobald keine seiner Packlisten mehr
unterwegs ist und keine mehr auf ihre Ausgabe wartet. Nach einer
Teilausgabe bleibt, was nie rausging, einfach im Lager – auch wenn das
Projekt nie auf „Unterwegs“ stand; Rentalars fragt vorher nach.

Rot wird die Liste erst, wenn du die Rücknahme abschließen willst und noch
etwas fehlt: Dann zeigt Rentalars die Zeilen, die noch offen sind. Erst
wenn jede Zeile als zurück abgehakt oder vermerkt ist, lässt sich die
Rücknahme abschließen.

Verkaufte Ware kommt nicht zurück und steht deshalb nicht zum Abhaken.

### Die Packliste des Gesamtprojekts

Jedes Teilprojekt (Abschnitt 7) hat seine eigenen Packlisten und wird für
sich gepackt, ausgegeben und zurückgenommen. Damit du schnell wechselst,
stehen auf der Packliste jedes Teilprojekts und des Gesamtprojekts **alle
Teile als Reiter** über der Liste, nach ihren Nummern: das Gesamtprojekt,
jedes Teilprojekt – das gerade geöffnete mit einem Reiter je Packliste,
wenn es mehrere hat – und zuletzt **„Alle zusammen“**. Teilprojekte, deren
Packliste du nicht sehen darfst, fehlen. „Alle zusammen“ öffnet die
Übersicht aller Packlisten (mit denselben Reitern darüber):

- **„Nach Teilprojekt“** – die eigenen Positionen des Gesamtprojekts und
  jedes Teilprojekt mit seinem Fortschritt: wie viel gepackt, ausgegeben
  und zurück ist, dazu der Balken mit seinen Farben (oben, „Packen“), was
  aus anderen Teilprojekten übernommen und schon angekommen ist, was an
  spätere weitergeht.
- **„Nach Artikel zusammengefasst“** – so sieht das Lager, wie viel von
  jedem Artikel insgesamt **aus dem Lager** geht. Was zwischen den
  Teilprojekten weiterwandert, steht eigens unter **„Übernahme“** und wird
  nicht doppelt gezählt.

Die Übersicht ist **nur zum Lesen**: Gepackt, ausgegeben, übergeben und
zurückgenommen wird auf der Packliste des jeweiligen Teilprojekts.
Teilprojekte, deren Packliste du nicht sehen darfst, fehlen; die Seite
sagt, wie viele. Beide Ansichten gibt es als **PDF**.

### Übernahme und Übergabe zwischen Teilprojekten

Übernimmt ein Teilprojekt Material aus einem früheren (Abschnitt 7,
„Material, das weiterwandert“), zeigen beide Packlisten die Stücke:

- beim **früheren** Teilprojekt an der Zeile „6 gehen weiter an 2026-0042-2
  Bühne Schlosspark“ – diese Stücke packst und gibst du ganz normal aus;
- beim **späteren** „Übernahme aus 2026-0042-1 Bühne Marktplatz, nicht aus
  dem Lager“. Diese Zeile wird dort nicht im Lager gepackt und nicht
  ausgegeben; sie zählt weder beim Fortschritt noch beim Gewicht.

**Kommen die Stücke an**, buchst du auf der Packliste des späteren
Teilprojekts an der Zeile **„Übergabe buchen“** – auch in Teilen,
voreingestellt mit allem, was noch erwartet wird. Übergeben lässt sich
erst, wenn das Material des früheren Teilprojekts ausgegeben ist. Für das
frühere Teilprojekt zählen die Stücke damit als **zurück**, für das
spätere als **ausgegeben**: Seine Packliste steht danach auf „unterwegs“,
das Teilprojekt, sobald auch sein Material aus dem Lager ausgegeben ist,
und mit ihm kommen die Stücke später ins Lager zurück. Hat das frühere
Teilprojekt bestimmte Exemplare ausgegeben und gehen alle weiter, wandern sie mit – ihr Verlauf zeigt dann beide
Teilprojekte. Für die Übergabe musst du **beide Packlisten bearbeiten
dürfen**.

**Eine falsch gebuchte Übergabe** nimmst du an der Zeile mit
„zurücknehmen“ zurück – die letzte Buchung zuerst, und nur, solange keines
der beiden Teilprojekte zurückgebucht ist und keines der Stücke schon
wieder im Lager oder weitergegangen ist.

**Stücke, die noch auf ihre Übergabe warten, fehlen beim früheren
Teilprojekt.** „Alles ist zurück“ lässt sie aus, und seine Rücknahme lässt
sich erst abschließen, wenn sie übergeben, doch zurückgebucht oder an der
Zeile vermerkt sind; die Meldung nennt das Teilprojekt, auf das sie warten.
Nach der Rücknahme des früheren Teilprojekts kann von dort nichts mehr
übergeben werden. Zugemietete Stücke wandern nicht mit: Übergeben werden
nur Stücke aus dem eigenen Bestand.

---

## 11. Dokumente

*Der Reiter „Dokumente“ – direkt nach der Preisübersicht – ist für alle,
die die Planung eines Projekts sehen. Erstellen darf, wer das Projekt
bearbeiten darf; Angebot, Auftragsbestätigung und Rechnung nur, wer
zusätzlich Preise sehen darf.*

Der Reiter enthält alles, was an Papier zum Projekt gehört: oben die
**erstellten Dokumente**, daneben der Kasten **„Dokument erstellen“** und
darunter die **Dateien** des Projekts mit „Datei hochladen“ (unten,
„Dateien des Projekts“). Den Kasten erreichst du auch über den Knopf
„… erstellen“ im Kopf des Projekts, der das nächste Dokument vorschlägt
(Abschnitt 7, „Der Kopf eines Projekts“).

Rentalars schreibt die Dokumente eines Projekts selbst – als PDF, mit eurem
Logo, eurer Anschrift, Bankverbindung und Registerangaben aus den
Firmendaten (Abschnitt 16):

| Dokument | Was darin steht | Nummer, voreingestellt |
|---|---|---|
| **Angebot** | die Positionen mit Preisen wie in der Auftragsbestätigung – oder nur die Teilgruppen mit ihren Summen –, optionale und alternative Teilgruppen und Positionen gekennzeichnet; dazu „Gültig bis“ | `AN-2026-0001` |
| **Auftragsbestätigung** | die Positionen mit Preisen, wie vereinbart: Teilgruppen mit Zwischensummen, Personal, Logistik, Aufpreise, Steuer, Summe | `AB-2026-0001` |
| **Lieferschein** | was zum Kunden geht: Menge, Einheit, Artikelnummer, Bezeichnung, nach der Ausgabe auch die IDs der ausgegebenen Exemplare – ohne Preise; mit Feldern „Geliefert von, Datum“ und „Erhalten von, Datum, Unterschrift“ | `LS-2026-0001` |
| **Rechnung** | wie die Auftragsbestätigung, aber ohne optionale Teilgruppen und ohne optionale oder alternative Positionen; dazu „Fällig am“; mit **XRechnung** als zweiter Datei – nur, solange „Rentalars als Buchhaltungsprogramm verwenden“ an ist (unten) | `RE-2026-0001` |
| **Stornorechnung** | hebt eine Rechnung auf, mit umgekehrten Beträgen | aus demselben Kreis wie die Rechnungen |
| **Crew-Disposition** | wer wann wo in welcher Funktion arbeitet | `CD-2026-0001` |

**Sprache.** Die festen Texte der Dokumente – Spaltennamen, Summenzeilen,
Einheiten, Daten und Beträge – folgen der „Sprache der Dokumente“ eurer
Firma, nicht der Sprache dessen, der sie erstellt (Abschnitt 16,
„Firmendaten und Grundeinstellungen“); auf Englisch stehen Daten als
16/10/2026. Was ihr selbst geschrieben habt, bleibt, wie es ist: die
Überschrift, Einleitung und Schlusstext aus den Dokumentvorlagen (unten,
„Vorlagen und Textbausteine“), Textbausteine, Positionstexte und
Produktnamen. Stellt ihr auf Englisch um, übernimmt die Seite
„Vorlagentexte auf Englisch oder Deutsch“ die mitgelieferten Texte der
Vorlagen (unten, „Vorlagen und Textbausteine“); eure eigenen Texte,
Textbausteine und Produktnamen übersetzt ihr selbst. Eine Installation,
die auf Englisch eingerichtet wurde, beginnt mit englischen Vorlagen
(„Quotation“, „Invoice“ …). Die XRechnung behält ihre Codes in jeder
Sprache.

**Wer was sieht.** Angebot, Auftragsbestätigung, Rechnung und
Stornorechnung zeigen Preise; sie sieht nur, wer Preise sehen darf.
Lieferschein und Crew-Disposition sehen alle, die den Reiter sehen – auch
das Lager. Wer im Projekt nur eingeplant ist, sieht den Reiter nicht.

### Ein Dokument erstellen

Reiter **Dokumente** im Projekt, rechts **„Dokument erstellen“** – oder
direkt über den Knopf im Kopf des Projekts, dann ist die Art schon
gewählt:

1. Unter **„Dokument“** die Art wählen. Das Angebot steht ganz oben.
2. Beim Angebot:
   - **„Umfang“** – **„mit Positionen“** oder **„nur
     Teilgruppen“**. Mit „nur Teilgruppen“ steht jede Teilgruppe mit ihrer
     Beschreibung und ihrer Summe im Angebot, ohne die Positionen darin;
     Untergruppen stehen eingerückt mit ihrer eigenen Summe, die Teilgruppe
     darüber endet mit „Zwischensumme … mit Untergruppen“. Ein Rabatt oder
     Pauschalpreis der Teilgruppe steht als Hinweis darunter. Positionen
     ohne Teilgruppe, das Personal, die Logistik und die Aufpreise stehen
     weiter einzeln drin, ebenso optionale und alternative Positionen einer
     Teilgruppe –
     sie gehören nicht zu deren Summe. Die Positionen werden fortlaufend ab
     1 nummeriert. Netto, Steuer und Brutto sind in beiden Fällen gleich.
     Beim Angebot eines Gesamtprojekts gilt das für die Teilgruppen jedes
     Teilprojekts; die Blöcke der Teilprojekte mit ihrer Summe bleiben.
   - **„Gültig bis“** und **„Gültigkeit in Tagen“** – trag eins von
     beiden ein, das andere ändert sich sofort mit (gezählt ab heute, dem
     Datum des Angebots). Vorgeschlagen ist die Gültigkeit aus der Vorlage
     des Angebots (unten, „Vorlagen und Textbausteine“; anfangs 14 Tage).

   Beim Lieferschein, wenn das Projekt mehrere Packlisten hat: unter
   **„Packliste“** eine bestimmte oder „alle Packlisten“.
3. Unter **„Textbausteine“** anhaken, was mit soll – eure Mietbedingungen
   etwa (siehe unten). Angeboten werden nur die Bausteine, die für die
   gewählte Dokumentart gedacht sind; wechselst du die Art, wechselt die
   Liste mit.
4. **„Entwurf als PDF“** zeigt das Dokument, wie es würde – mit „ENTWURF“
   statt einer Nummer. Ein Entwurf zählt keine Nummer und wird nicht
   gespeichert; sieh ihn dir so oft an, wie du willst.
5. **„Dokument erstellen“** – nach einer Rückfrage bekommt das Dokument
   seine Nummer und liegt ab jetzt beim Projekt.

Was im Dokument steht, nimmt Rentalars aus dem Projekt, wie es in diesem
Moment ist: Positionen und Preise aus der Planung, die Anschrift aus der
Rechnungs- bzw. Lieferadresse (Abschnitt 6), dazu Kundennummer, die
USt-IdNr. des Kunden, Projektnummer, Veranstaltungsort und
Ansprechpartner. Als **Leistungszeitraum** steht auf Angebot,
Auftragsbestätigung und Rechnung der Mietzeitraum („Material außer Haus“)
– über ihn werden die Miettage gezählt. **Optionale Teilgruppen** stehen in
Angebot und Auftragsbestätigung mit dem Vermerk „optional, nicht in der
Summe enthalten“, darunter ihre Summe; **optionale und alternative
Positionen** stehen dort mit „(optional)“ oder „(Alternative)“ und „nicht
in der Gesamtsumme enthalten“, ihre Summen unter der Bruttosumme. In der
Rechnung fehlen beide ganz, und die Positionen sind ohne sie
durchnummeriert. Zumietungen, die nur eine Fehlmenge decken, erscheinen
nicht – der Kunde zahlt die Position, die sie decken. **Kundenmaterial**
steht in Angebot und Auftragsbestätigung an seiner Stelle, mit Menge, ohne
Preis und Betrag und mit „Kundeneigenes Material – wird mitgeführt, ohne
Berechnung“; im Lieferschein mit „Kundeneigenes Material – wird
mitgeführt“. Rechnung und XRechnung lassen es weg (Abschnitt 5,
„Kundenmaterial“).
Der Lieferschein nennt nach der Ausgabe die ausgegebenen Mengen, vorher die
geplanten – am besten erstellst du ihn also nach dem Ausgeben.

**Die Gliederung der PDFs**. Angebot, Auftragsbestätigung,
Rechnung und Stornorechnung sind so gegliedert: Auf der obersten Ebene
stehen **Material**, **Personal** und **Logistik** (und danach Aufpreise,
Gesamtrabatt und Summen); unter „Material“ stehen zuerst die Teilgruppen mit
ihren Untergruppen, dann die Positionen ohne Teilgruppe. Jede obere Ebene
schließt mit ihrer Summe („Summe Material“, „Summe Personal“). Die Spalte
**Rabatt** gibt es nur, wenn mindestens eine Position einen Rabatt hat, und die
Zahlenspalten stehen unter ihren Überschriften.

**Angebote.** Ein Projekt kann beliebig viele Angebote haben – nach jeder
Änderung des Kunden ein neues, mit neuer Nummer. In der Liste steht unter
dem Datum „gültig bis …“ und, wenn es so erstellt ist, „nur Teilgruppen“.
Eine XRechnung gibt es zum Angebot nicht. Eine Alternative nennt im
Angebot und in der Auftragsbestätigung die Position, die sie ersetzen
könnte („Alternative zu Pos. 3“); eine alternative Teilgruppe heißt
„Alternative zu „Licht Variante A“, nicht in der Gesamtsumme enthalten“.

**Was nicht geht:** ein Angebot, eine Auftragsbestätigung oder Rechnung
für ein internes Projekt (es hat keinen Kunden) oder für ein Teilprojekt
(sie entstehen am Gesamtprojekt, unten), eine Crew-Disposition für ein
Projekt, in dem noch niemand eingeplant ist, und eine zweite gültige
Rechnung (unten). Rentalars sagt dann, was fehlt, und vergibt keine
Nummer.

### Gesamtprojekt und Teilprojekte

**Abgerechnet wird am Gesamtprojekt** (Abschnitt 7, „Teilprojekte“):
Erstelle Angebot, Auftragsbestätigung und Rechnung im Reiter „Dokumente“
des Gesamtprojekts. Der Kunde bekommt so ein Angebot und eine Rechnung für
die ganze Produktion:

- zuerst die **gemeinsamen Positionen** des Gesamtprojekts (z. B. zentrale
  Stromversorgung), ohne eigene Überschrift;
- dann jedes **Teilprojekt, das nicht storniert ist**, als eigener Block:
  mit der Überschrift „Teilprojekt 2026-0042-1 Bühne Marktplatz,
  10.03.–12.03.2027“, darunter „Veranstaltungsort: …“, seinen Teilgruppen
  und seiner Zwischensumme. Ein Teilprojekt, in dem nichts zu berechnen
  ist, fehlt;
- die Positionen sind **durchnummeriert**; Steuern und Summe gelten für
  alles zusammen, auch in der XRechnung. Als Leistungszeitraum steht der
  Zeitraum vom ersten Beginn bis zum letzten Ende aller Teile darin.

**Übernommenes Material** wird nur einmal berechnet – dort, wo es
herkommt – und steht deshalb kein zweites Mal in Angebot und Rechnung.

**Im Reiter „Dokumente“ eines Teilprojekts** erstellst du Lieferscheine –
an dessen Lieferadresse, mit dessen Material – und Crew-Dispositionen.
Angebot, Auftragsbestätigung und Rechnung bietet er nicht an; er sagt,
dass sie am Gesamtprojekt entstehen, und führt dorthin. Ein Lieferschein
des Gesamtprojekts enthält nur dessen eigenes Material; einen gemeinsamen
Lieferschein für alle Teilprojekte gibt es nicht. Übernommenes Material
steht auf dem Lieferschein des übernehmenden Teilprojekts mit „Übernahme
aus 2026-0042-1 Bühne Marktplatz“.

**Darfst du ein Teilprojekt nicht lesen**, kannst du die Preisdokumente
des Gesamtprojekts weder erstellen noch als Entwurf ansehen – sie enthalten
jedes Teilprojekt; die Meldung nennt es. Bitte jemanden, der alle
Teilprojekte lesen darf.

### Unveränderlich abgelegt

Ein erstelltes Dokument **ändert sich nie mehr** und **lässt sich nicht
löschen**. Rentalars legt das PDF zusammen mit seinem Inhalt und einer
Prüfsumme ab; die Prüfsumme belegt, dass die Datei noch die ist, die
erstellt wurde. Ändert sich danach die Planung, bleibt das Dokument, wie es
war.

Die Liste **„Dokumente des Projekts“** zeigt jedes Dokument mit Nummer,
Datum (bei Rechnungen dazu „fällig“), Bruttobetrag und wann es an wen
gesendet wurde. Ein Klick auf den Namen öffnet das PDF.

Stimmt ein Angebot, eine Auftragsbestätigung, ein Lieferschein oder eine
Crew-Disposition nicht mehr, erstellst du eine neue – mit neuer Nummer;
die alte bleibt in der Liste. Bei einer Rechnung geht das nicht so
einfach: siehe „Stornieren“.

### Rechnung und XRechnung

Je Projekt gilt **eine** Rechnung (oder, eine Schlussrechnung mit
Abschlägen, siehe „Abschlags-, Teil- und Schlussrechnungen“ weiter unten). Sie enthält, was in der Planung steht
und berechnet wird: Positionen mit Miettagen und Rabatten, Rabatte und
Pauschalpreise der Teilgruppen, das Personal mit Stunden oder – bei „je
Tag“ – mit Tagen (Einheit „Tag“), Stunden über einer Grenze je Tag mit
dem Vermerk „davon 2 Std. über 10 Std. am Tag zu 55,00 €“ (Abschnitt 12),
Zuschläge für Nacht, Sonn- und Feiertage im Betrag der Personalposition
mit dem Vermerk „inkl. Zuschläge 126,00 €: Nacht 25 % auf 4 Std.
45,00 €, …“ – Angebot und Auftragsbestätigung ebenso –, den
Abschnitt **„Logistik“** mit einer Position je Fahrzeugbuchung – Menge in
km, Tagen oder Pauschalen, darunter je Fahrt Kilometer und Satz („12.06.
Fahrt zum Aufbau: 84 km à 0,85 € (inkl. Anhängerzuschlag 0,20 €)“) bzw. die
Tage mit dem Faktor der Staffel; eine Buchung ohne Fahrt und Betrag fehlt
–, die Aufpreise, die Steuer je Steuerart und den Bruttobetrag – optionale
Teilgruppen und optionale oder alternative Positionen nicht. Angebot und
Auftragsbestätigung zeigen die Logistik ebenso. Dazu:

- **Leistungszeitraum** – der Zeitraum „Material außer Haus“;
- **Zahlungsziel** – das des Kunden, sonst das aus den Firmendaten
  (voreingestellt 14 Tage); daraus **„Fällig am“**.

Rechnet ihr Personal **nach Aufwand** ab (Abschnitt 12) – die Voreinstellung für neue Personalpositionen –, gebt vorher die
Zeiten frei – sonst steht die geplante Stundenzahl auf der Rechnung, als
„Schätzung“ markiert.

**XRechnung.** Mit jeder Rechnung entsteht eine zweite Datei: die
elektronische Rechnung im Format **XRechnung** (UBL, nach EN 16931). Im
Geschäft zwischen Unternehmen muss in Deutschland seit 2025 jeder solche
Rechnungen empfangen können; in den nächsten Jahren müssen sie auch
verschickt werden. Der Link „XRechnung“ steht neben der Rechnung in der
Liste.

**Rechnungen an Behörden** brauchen in der XRechnung die **Leitweg-ID** der
Behörde. Trag sie am Kunden unter „Leitweg-ID oder Käuferreferenz“ ein
(Abschnitt 6); Rentalars setzt sie als Käuferreferenz in jede XRechnung an
diesen Kunden. Verlangt ein anderer Kunde eine eigene Bestellnummer oder
Referenz, gehört sie ins selbe Feld. Ist es leer, steht dort die
Projektnummer.

Für die XRechnung braucht es einige Angaben, die sonst gern fehlen. Bevor
eine Nummer vergeben wird, prüft Rentalars sie und sagt, was fehlt
(„Für die elektronische Rechnung fehlt: E-Mail-Adresse der Firma.“):

- Firmenname und Anschrift der Firma,
- E-Mail-Adresse und Telefonnummer der Firma,
- USt-IdNr. oder Steuernummer der Firma (alles unter Einstellungen →
  Firmendaten und Grundeinstellungen),
- die Rechnungsanschrift des Kunden.

Eine Stornorechnung nennt die Firmendaten, wie sie am Tag des Stornos
sind; fehlt dann etwas davon, sagt Rentalars es ebenso, bevor eine Nummer
vergeben wird.

**Die Monatsrechnung der Servicefälle**. Die Servicefälle
eines Kunden und Monats lassen sich in einer Rechnung abrechnen (Abschnitt
7, „Monatsabrechnung“). Sie hat einen Abschnitt je Fall mit Titel,
Tätigkeit und Positionen, wird nummeriert, als PDF und XRechnung abgelegt
und an Lexware Office übergeben wie jede Rechnung. Sie gehört zum Fall mit
der niedrigsten Nummer; gesendet wird sie aus diesem Fall. Im Reiter
„Dokumente“ der übrigen Fälle steht sie mit „Monatsrechnung der
Servicefälle, gehört zu …“. Wird sie storniert, ist die Abrechnung wieder
ein Entwurf, und ihre Fälle sind wieder offen.

### Abschlags-, Teil- und Schlussrechnungen

Ein Projekt darf mehrere Rechnungen haben, wenn sie verschiedene
Arten sind. Im Formular „Dokument erstellen“ steht bei einer Rechnung das Feld
**„Was die Rechnung abrechnet“**:

- **Das ganze Projekt in einer Rechnung.** Sie ist nur möglich,
  solange das Projekt keine gültige Abschlags- oder Teilrechnung hat.
- **Abschlagsrechnung (Zahlung auf Rechnung)** und **Teilrechnung** – sie
  rechnen einen **Betrag** ab, nicht einzelne Positionen: Gib den
  **Nettobetrag** oder einen **Prozentsatz der Netto-Summe** an (nur eins von
  beiden) und bei Bedarf unter „Wofür?“ einen Text, der auf der Rechnung steht
  („Anzahlung bei Auftrag“). Die Rechnung zeigt eine Zeile mit dem Betrag und
  die Steuer in den Anteilen des Projekts. Sie bekommt die nächste Nummer aus
  dem Kreis der Rechnungen und heißt „1. Abschlagsrechnung“, „2. Teilrechnung“
  usw.
- **Schlussrechnung** – sie zeigt das **ganze Projekt** und zieht darunter
  die bereits gestellten Abschlags- und Teilrechnungen ab („Abzüglich 1.
  Abschlagsrechnung RE-2026-0007 vom 12.10.2026“, netto und Steuer). Der
  **zu zahlende Betrag** ist der Rest. Sie braucht mindestens eine gültige
  Abschlags- oder Teilrechnung, und der Rest darf nicht negativ sein.

**Der Abrechnungsstand.** Sobald ein Projekt Abschlags-, Teilrechnungen oder
Teilgutschriften hat, steht im Reiter „Dokumente“ über der Liste der Kasten
**„Abrechnungsstand“**: Projekt netto, auf Rechnung abgerechnet (netto),
**noch abzurechnen** (netto und brutto) und je Rechnung Netto, Brutto und
ihre Gutschriften. So siehst du jederzeit, was noch offen ist. Ist noch nichts
mit einer Schlussrechnung abgerechnet, ist sie im Formular vorgewählt.

**Schutz vor Doppelabrechnung.** Rentalars lehnt ab (und nennt den Grund),
wenn
- Abschlags- und Teilrechnungen zusammen mehr als das Projekt netto
  abrechnen würden (der Rest zeigt, was noch möglich ist),
- eine gewöhnliche Rechnung gestellt werden soll, obwohl eine gültige
  Abschlags- oder Teilrechnung besteht (erst die Schlussrechnung),
- eine Schlussrechnung ohne Abschlags- oder Teilrechnung gestellt werden soll,
- eine Abschlags- oder Teilrechnung storniert oder gutgeschrieben werden soll,
  obwohl eine gültige Schlussrechnung sie abzieht (erst die Schlussrechnung
  stornieren).

Abschlags-, Teil- und Schlussrechnungen gibt es nur für das **ganze Projekt**,
nicht für Teile eines Projekts und nicht für Servicefälle. Eine Projektliste
meldet ein Projekt, das nur eine Abschlagsrechnung hat, noch nicht als
„abgerechnet“.

**Die elektronische Rechnung.** Die XRechnung nennt eine Abschlags- oder
Teilrechnung mit Typ-Code 326 (Teilrechnung), eine Schlussrechnung mit
Typ-Code 380; die abgezogenen Rechnungen stehen als Rechnungsbezug (BG-3), der
Abzug als bereits gezahlter Betrag (BT-113) und der Rest als Zahlbetrag.
Die XRechnung ist nur von uns gebaut und **nicht** gegen die Prüfregeln der
KoSIT geprüft; Rentalars prüft sie gegen eigene Kernprüfungen (siehe „Zahlungen, Offene Posten, EÜR und Archiv“).

**DATEV und Lexware.** Eine Abschlags- oder Teilrechnung wird als Rechnung
gebucht. Die Schlussrechnung bucht nur den **Rest** nach dem Abzug (Erlös
netto und Steuer in den Anteilen des Rests), weil die Abschläge schon gebucht
sind.

**Summen und Listen.** In der Liste der Belege, in den Summen der Ausgangsbelege und in
der API (`net_total`, `gross_total`) steht bei einer Schlussrechnung das, was sie
**hinzufügt** – das Projekt abzüglich der Abschläge, also der Zahlbetrag. Die
Abschläge zählen mit ihren eigenen Rechnungen; so wird nichts doppelt gezählt.
Die Steuer jeder Abschlags- und Teilrechnung ist ihr Netto mal dem Satz, auf den Cent
gerundet; ein Rest der Schlussrechnung gleicht die Abweichungen aus.

### Stornieren

Ist eine Rechnung falsch, wird sie nicht geändert, sondern **storniert** –
so verlangt es das Steuerrecht:

1. In der Liste neben der Rechnung **„stornieren“** und die Rückfrage
   bestätigen.
2. Rentalars erstellt eine **Stornorechnung**: dieselben Positionen mit
   umgekehrten Beträgen, mit dem Satz „Storniert die Rechnung RE-2026-0007
   vom 12.10.2026.“ und ebenfalls mit XRechnung. Sie bekommt die nächste
   Nummer aus dem Kreis der Rechnungen.
3. Die Rechnung steht nun grau mit „storniert“ in der Liste, die
   Stornorechnung mit „storniert RE-2026-0007“. Beide bleiben beim Projekt.
4. Jetzt lässt sich eine neue, richtige Rechnung erstellen.

Solange eine Rechnung des Projekts gültig ist, lehnt Rentalars eine zweite
ab („Rechnung RE-2026-0007 dieses Projekts ist noch gültig. Storniere sie
zuerst.“) – Ausnahme sind Abschlags-, Teil- und Schlussrechnungen (siehe oben).

**Teilgutschrift.** Eine gültige Rechnung muss nicht ganz storniert werden,
wenn nur ein Teil falsch ist: In der Liste neben ihr öffnet **„teilweise
gutschreiben“** ein kleines Formular – **Nettobetrag** oder **Prozentsatz**
von dem, was die Rechnung noch abrechnet, und ein Text „Wofür?“; der Knopf heißt „Gutschrift erstellen“. Rentalars
erstellt eine **Gutschrift** mit negativen Beträgen („Gutschrift zur Rechnung
RE-2026-0007 vom 12.10.2026“), nummeriert aus dem Kreis der Rechnungen, mit
XRechnung (Typ-Code 384). Die Rechnung bleibt gültig und zeigt in der Liste
„schreibt RE-… gut“ bei der Gutschrift; im Abrechnungsstand steht sie bei der
Rechnung. Mehr als der Rest der Rechnung lässt sich nicht gutschreiben.
Stornierst du die Rechnung später doch, storniert Rentalars nur den **Rest**
(Netto minus bisherige Teilgutschriften). Schreibst du **alles** gut, was noch übrig ist (100 Prozent oder den ganzen
Restbetrag), ist die Gutschrift die **Stornierung**: Die Rechnung gilt als
storniert und das Projekt lässt sich neu abrechnen. Hatte eine Schlussrechnung
einen Steuersatz, der durch die Abschläge ins Minus gerät, kann die Steuer der
Stornierung um Cent von der Regel BR-CO-17 abweichen; die Summe aus Rechnung,
Gutschriften und Stornierung bleibt dafür genau null. Auch die Teilgutschrift lässt sich
nicht ändern, nur durch eine weitere Rechnung ausgleichen.

### Rechnungen in einem anderen Programm

Schreibt ihr die Rechnungen in eurer Buchhaltung oder einem anderen
Programm, nimm unter Einstellungen → Firmendaten und Grundeinstellungen den
Haken **„Rentalars als Buchhaltungsprogramm verwenden“** heraus (anfangs ist er
gesetzt; er steht in einem eigenen Kasten **„Buchhaltung und
Rechnungswesen“** auf dieser Seite). Dann

- bietet Rentalars weder Rechnung noch Stornorechnung an – nicht im Kasten
  „Dokument erstellen“, nicht im Kopf eines Projekts, nicht über die
  Schnittstelle –, und der Kopf schlägt auch bei einem Projekt, das wieder
  im Lager ist, keine Rechnung vor;
- sind unter Einstellungen → Buchhaltung die Übergabe an Lexware Office
  und der DATEV-Export ausgeblendet; die Seite sagt „Rechnungen sind
  abgeschaltet“;
- verschwinden im Menü **Buchhaltung** alle Reiter, bei denen es um
  Buchhaltung geht: **Beleg erfassen** und **Eingangsbelege**, **Offene Posten**,
  **Bank**, **EÜR** und **Archiv**, **Anlagenspiegel** und **Verkäufe aus Bestand** sowie
  **Altprojekte importieren**. Weg sind auch die Stellen, die dorthin führen: die
  Karte „Anlagevermögen“ am Exemplar, die Frage „Auch als Eingangsrechnung
  erfassen?“ nach einem Kauf und der Eintrag „Eingangsrechnungen“ in den
  Einstellungen. Ruft jemand eine solche Adresse trotzdem auf (ein altes
  Lesezeichen), landet er auf der Startseite mit dem Hinweis, dass in Rentalars
  keine Buchhaltung geführt wird; die Schnittstelle antwortet mit dem Fehler
  `accounting_disabled`. **Ausgangsdokumente** (Angebote, Auftragsbestätigungen,
  Lieferscheine und früher erstellte Rechnungen) und die **Monatsabrechnung** bleiben;
  hat jemand nur Rechte für die ausgeblendeten Reiter, verschwindet der Menüpunkt
  „Buchhaltung“ ganz. Gelöscht wird nichts: Setzt du den Haken wieder, ist alles da;
- bleiben früher erstellte Rechnungen am Projekt lesbar und lassen sich
  weiter versenden; stornieren oder an Lexware Office übergeben lassen sie
  sich nicht.

Angebot, Auftragsbestätigung, Lieferschein und Crew-Disposition bleiben,
wie sie sind. Die Monatsabrechnung der Servicefälle zeigt dann die Werte
zum Übertragen in euer Programm und markiert die Fälle als abgerechnet
(Abschnitt 7, „Monatsabrechnung“). Ein Projekt schließt du ohne Rechnung
ab – das ging schon immer. Dass die Rechnung im anderen Programm geschrieben ist, vermerkst du
 mit dem Haken **„Rechnung gestellt“** im Kopf des Projekts
(unten). Setzt du den Haken „Rentalars als Buchhaltungsprogramm verwenden“ wieder,
ist alles wie vorher.

### Noch zu schreibende Rechnungen

Rentalars erinnert daran, wenn ein abgeschlossenes Projekt noch
keine Rechnung hat.

**Wann ein Projekt als berechnet gilt.** Das betrifft ganze Projekte mit
einem Kunden – keine internen, keine Teilprojekte (sie rechnet ihr
Gesamtprojekt ab) und keine stornierten. Ein solches Projekt ist berechnet,

- wenn Rentalars die Rechnungen schreibt: sobald es eine Rechnung hat, die
  nicht storniert ist;
- wenn ihr sie in einem anderen Programm schreibt (oben): sobald im Kopf
  des Projekts der Haken **„Rechnung gestellt“** gesetzt ist.

Wird ein Projekt nie berechnet – es war kostenlos, oder es wird mit einem
anderen Projekt abgerechnet –, markierst du es mit **„Keine Rechnung
nötig“**; dann erinnert Rentalars nicht mehr daran. **„Rückgängig“** nimmt
die Markierung wieder weg.

**Im Kopf des Projekts** steht ab „Wieder im Lager“ – vorher im Reiter
„Dokumente“ –, wie es um die Rechnung steht: **„Rechnung RE-2026-0007“**
mit Datum, **„Rechnung gestellt“**, **„Keine Rechnung“** oder **„Rechnung
offen“**, gelb, sobald das Projekt abgeschlossen ist. Daneben stehen der
Haken „Rechnung gestellt“ (wenn die Rechnungen in einem anderen Programm
entstehen) und „Keine Rechnung nötig“ bzw. „Rückgängig“. Sehen kann das,
wer Preise sehen darf; ändern, wer zusätzlich das Projekt bearbeiten darf
– auch, wenn es schon abgeschlossen ist. Rechnet eine Monatsrechnung
einen Servicefall ab (Abschnitt 7, „Monatsabrechnung“), nennt der Kopf
des Falls ihre Nummer nur, wer sie öffnen darf – also ihr
Projekt und jeden Fall lesen darf, den sie abrechnet; alle anderen sehen
„Rechnung gestellt“.

**Die Erinnerung** kommt als Benachrichtigung „Rechnung noch zu schreiben“
(Abschnitt 15) an die Projektleitung und an die Person, die unter
Einstellungen → Benachrichtigungen bei „Außerdem erinnern“ steht – an
beide nur, wenn sie Preise sehen dürfen. Ein Klick führt, wenn Rentalars
die Rechnungen schreibt, zu „Rechnung erstellen“ im Reiter „Dokumente“,
sonst zum Projekt mit dem Haken. Wann und wie oft erinnert wird, steht
unter Einstellungen → Benachrichtigungen im Kasten „Rechnungen“ –
voreingestellt um 9:00 Uhr, das erste Mal einen Tag nach dem Abschließen,
dann alle sieben Tage, bis die Rechnung da ist (Abschnitt 16,
„Benachrichtigungen der Firma“). Erinnert wird nur an Projekte, die netto mehr als 0 €
kosten. Wird ein Projekt wieder geöffnet und erneut abgeschlossen,
beginnt die Erinnerung von vorn. Mit **„Auch Servicefälle“** (voreingestellt an) erinnert
Rentalars ebenso an erledigte Servicefälle mit einem Kunden, an denen
etwas zu berechnen ist – Zeiten oder Spesen, die auf den Fall gebucht und
nicht abgelehnt sind –, an die, die erledigt wurden, nachdem
der Haken eingeschaltet wurde (Abschnitt 16, „Benachrichtigungen der
Firma“). Ein Servicefall gilt auch als berechnet,
wenn ihn eine Monatsrechnung abrechnet oder eine Monatsabrechnung als
abgerechnet markiert hat (Abschnitt 7, „Monatsabrechnung“).

**Ältere abgeschlossene Projekte** verfolgt Rentalars
nicht: Ob ihre Rechnung geschrieben ist, weiß es nicht. Sie stehen nicht
als „Rechnung offen“ in Liste, Filter und Kopf; eine Rechnung aus Rentalars
zeigt sich aber weiter. Wird so ein Projekt wieder geöffnet, zählt es ab
dann wie jedes andere.

**Den Überblick** geben die Startseite mit dem Kasten **„Noch zu
schreibende Rechnungen“** (Abschnitt 2) und die Projektliste: Der Filter
**„Rechnung“** mit „abgeschlossen, Rechnung offen“ zeigt alle
abgeschlossenen Projekte ohne Rechnung, und die Spalte **„Rechnung“**
(unter „Spalten“) nennt bei jedem Projekt die Nummer der Rechnung,
„Rechnung gestellt“, „Keine Rechnung“ oder – wenn es abgeschlossen ist – „Rechnung offen“.

Andere Programme lesen und setzen den Stand über die Schnittstelle
(Abschnitt 16, „API-Token“).

### Crew-Disposition

Der Einsatzplan für alle, die am Projekt arbeiten: je Einsatz **Tag**,
**Von**, **Bis**, **Person**, **Funktion**, **Treffpunkt** (sonst der
Veranstaltungsort) und **Kontakt**. Offene Plätze stehen als „offen“ darin.
Fährt jemand mit einem Fahrzeug der Logistik, steht es unter der
Funktion, beim Fahrer mit „Fahrer“ (Abschnitt 7, „Logistik“).

Telefon und E-Mail stehen nur bei Personen, die sie für Kollegen
freigegeben haben (Abschnitt 12, „Mein Bereich“) – das PDF sagt es
selbst dazu. **Stunden- und Tagessätze und Pauschalen stehen nie darin.**

Brauchst du nur schnell einen Ausdruck für die Crew, ohne Nummer und ohne
dass er abgelegt wird, nimm die **Einsatzübersicht**: „Drucken / PDF“ im
Reiter „Überblick“ (Abschnitt 12, „Der Überblick – was die Crew sieht“).

### Senden

**„Senden“** neben einem Dokument öffnet „Mail schreiben“ im Projekt, mit
dem Dokument im Anhang – bei einer Rechnung auch mit der XRechnung. Der
Empfänger ist mit dem Ansprechpartner des Projekts vorbelegt, der Betreff
trägt das Projektkürzel (Abschnitt 14). Nach dem Senden steht in der Liste,
wann und an wen das Dokument ging, und der Verlauf des Projekts hält es
fest.

Die Dokumente lassen sich auch jeder anderen Mail aus dem Projekt
anhängen: Unter „Dokumente“ stehen sie neben Packliste, Preisübersicht und
Einsatzübersicht. Senden darf, wer das Sonderrecht „Korrespondenz
schreiben und senden“ hat; ein Postfach für den Postausgang der
Korrespondenz muss eingerichtet sein (Abschnitt 14, „Postfächer
einrichten“).

### An Lexware Office übergeben

Führt ihr eure Bücher in Lexware Office und ist die Übergabe unter
Einstellungen → Buchhaltung eingeschaltet (Abschnitt 16), steht bei jeder
Rechnung und Stornorechnung im Reiter „Dokumente“, ob sie schon in Lexware
Office ist:

- **„An Lexware Office übergeben“** übergibt sie – als **Beleg** mit der
  Rentalars-Nummer, den Beträgen je Steuersatz und dem PDF; eine zweite
  Rechnungsnummer entsteht dort nicht. Das läuft im Hintergrund; du
  bekommst eine Nachricht, wenn es fertig ist, und an der Rechnung steht
  danach **„Seit … in Lexware Office“**.
- Ist **„sofort übergeben“** eingestellt, geht jede neue Rechnung und
  Stornorechnung gleich beim Erstellen hinüber. Klappt das nicht, bekommt,
  wer sie erstellt hat, eine Nachricht; die Rechnung selbst ist trotzdem
  erstellt.
- **„Nicht an Lexware Office übergeben: …“** nennt den Grund, wenn etwas
  schiefging; **„Erneut übergeben“** versucht es noch einmal und macht nur,
  was noch fehlt.

Den **Kunden** sucht Rentalars in Lexware Office über die Kundennummer;
gibt es ihn dort nicht, legt es ihn an. Gehört die Kundennummer in Lexware
Office zu einem anderen Namen, hält die Übergabe an und sagt es. Sind es
wirklich verschiedene Kunden, übergibst du mit **„Als neuen Kontakt
übergeben“**; Lexware Office gibt dem neuen Kontakt dann eine eigene
Nummer. Eine Rechnung wird nie doppelt übergeben.

Übergeben darf, wer die Rechnung erstellen darf (das Projekt bearbeiten
und Preise sehen) oder die Einstellungen ändern und Preise sehen darf.

### Beschreibung der Produkte in Dokumenten

Ob die **Beschreibung der Produkte** unter jeder Position gedruckt wird,
entscheidest du selbst: als Einstellung der Vorlage
(Einstellungen → Dokumentvorlagen, „Beschreibung der Produkte mitdrucken“,
voreingestellt aus) und mit einem Häkchen beim Erstellen eines
Dokuments, das mit der Einstellung der Vorlage vorbelegt ist und mit dem
Dokument gespeichert wird. Es gilt für PDF, Vorschau, Mail-Anhang,
Sammelrechnungen der Servicefälle und für die XRechnung (BT-154). Der Text,
den eine Position selbst trägt, bleibt immer stehen.

### Ausgangsbelege ohne Projekt

Ein Angebot oder eine Rechnung ohne Projekt – für einen Verkauf, eine
Dienstleistung, eine Nachberechnung – legst du unter
**Buchhaltung → Ausgangsbelege → „Neuer Ausgangsbeleg“** an. Der Dialog
fragt Art (Angebot oder Rechnung), Kunde, Rechnungsadresse, Ansprechpartner,
Datum, Zahlungsziel bzw. Gültigkeit, Betreff und die Wahl der
Beschreibungen. Dann öffnet sich der **Entwurf** mit eigener Seite: freie
Positionen, Positionen aus Produkten (keine Dienstleistungen, keine
Fahrzeuge), Textpositionen, Rabatt, Reihenfolge und Texte; ein Entwurf hat
keine Nummer und lässt sich löschen. **„Ausstellen“** macht daraus einen
Beleg wie in einem Projekt: dieselbe lückenlose Nummer, Steuerzeilen,
Fälligkeit, XRechnung, DATEV, Lexware Office, PDF und Mail mit Anhang;
unveränderlich, korrigiert wird mit einer Stornorechnung. Die Liste zeigt
„ohne Projekt“ in der Spalte Projekt und filtert nach **„Herkunft“**; die
Kundenseite zeigt die Belege des Kunden (Entwürfe, die letzten zehn, Link auf
alle). Ein Beleg ohne Projekt zählt nicht in die Profitabilität und nicht in
die Zahlungserinnerungen der Projekte. Für einen anonymisierten oder
deaktivierten Kunden gibt es keinen neuen Beleg; offene Entwürfe eines
anonymisierten Kunden werden verworfen. Sehen darf es, wer Preise sehen und
alle Projekte lesen darf; anlegen und ändern zusätzlich mit dem Recht,
Projekte zu bearbeiten. Mails brauchen ein Postfach für ausgehende Post
(Absender-Voreinstellung). Webhooks tragen für diese Belege `project: null`.
Nicht gebaut: der freie Einleitungstext der Vorlage zählt
nicht zum Vergleich mit den Standardtexten.

### Ausgangsbelege

In der Seitenleiste gibt es den Menüpunkt **Buchhaltung**,
zwischen Materialverwaltung und Kunden, mit den Reitern
**„Ausgangsbelege“** und **„Monatsabrechnung“** (Abschnitt 7,
„Monatsabrechnung“); **„Eingangsrechnungen“**, **„Anlagenspiegel“**,
**„Verkäufe aus Bestand“** und **„Altprojekte importieren“** kommen dazu (unten, und
Abschnitt 4). **Buchhaltung → Ausgangsbelege** listet jeden Beleg,
den ein Kunde bekommen hat – Angebote, Auftragsbestätigungen,
Lieferscheine, Rechnungen und Stornorechnungen, über alle Projekte und
Servicefälle; Crew-Dispositionen gehen an die Crew und fehlen hier.

Die Tabelle ist eine Liste wie jede andere (Abschnitt 2, „Listen“).
Voreingestellt zeigt sie Nummer, Art, Datum, Projekt, Kunde, Netto,
Steuer, Brutto und Status; über „Spalten“ kommen Bezeichnung, Monat,
Empfänger, Fällig am, Gesendet, Lexware Office, Monatsabrechnung und
„Angelegt von“ dazu. Jede Spalte lässt sich sortieren und gruppieren, die
Liste als CSV herunterladen. Die Beträge sind die, die mit dem Beleg
gespeichert wurden – Rentalars rechnet sie nie neu. Die Nummer öffnet das
PDF, das Projekt seinen Reiter „Dokumente“. Unter „Filter“ grenzt du ein
nach Art – auch „Rechnungen und Stornos“ oder „Monatsrechnungen der
Servicefälle“ –, Status (gesendet, nicht gesendet, storniert, nicht
storniert), Lexware Office (übergeben, fehlgeschlagen, nicht übergeben),
Kunde, Zeitraum mit Von und Bis und mit der Suche nach Nummer, Projekt
oder Kunde.

Unter der Tabelle stehen die **„Summen der gefilterten Belege“** – aller
Belege des Filters, nicht nur dieser Seite: je Art Anzahl, Netto, Steuer
und Brutto und dazu **„Rechnungen und Stornorechnungen zusammen“**;
Stornorechnungen zählen negativ. So siehst du etwa den Umsatz eines
Monats: Art „Rechnungen und Stornos“, Zeitraum wählen, fertig.

Die Ausgangsbelege sieht, wer Preise sehen und alle Projekte lesen darf –
wie die Auswertungen. Wer die Einstellungen lesen darf, findet oben den
Knopf **„DATEV-Export und Lexware Office“**: DATEV-Export und Übergabe an
Lexware Office bleiben unter Einstellungen → Buchhaltung (Abschnitt 16).
Über die Schnittstelle gibt es dieselbe Liste mit ihren Summen (Abschnitt
16, „API-Token“).

### Eingangsrechnungen

Die Rechnungen, die **Lieferanten euch schicken**, sammelt Rentalars in der **Buchhaltung**. Das sind zwei Reiter: **Beleg
erfassen** (hier lädst du eine Rechnung hoch) und **Eingangsbelege** (das
Register mit Status und Notiz), aus dem du die Ware **einpflegst** – als Exemplare oder als Mengen von
Mengenmaterial –, samt der **Nebenkosten** (Fracht, Verpackung, Zoll), die auf
die Ware umgelegt werden, und der Einstufung der Ware für die Bücher. Das
Register sieht, wer Einkaufs- und Kaufpreise sehen und das Material lesen
darf; hochladen, ändern und einpflegen darf zusätzlich, wer das Material
bearbeiten darf, löschen, wer es löschen darf. Wer eine Rechnung nur schnell
einpflegen will, ohne sie vorher zu erfassen, nimmt weiter „Kauf einpflegen“
(Abschnitt 4, „Kauf einpflegen“).

**Die Liste** (Reiter **Eingangsbelege**). Eine Zeile je Rechnung: Rechnungsnummer, Lieferant,
Rechnungsdatum, Fällig am, Netto, Steuer, Brutto, Status, Positionen und
Notiz; über „Spalten“ kommen Währung, Auslesen, Datei und „Hochgeladen von“
dazu. Wie jede Liste (Abschnitt 2, „Listen“) lässt sie sich sortieren,
gruppieren und als CSV laden. Gefiltert wird nach **Lieferant**, **Status**,
einem Zeitraum (**Von**, **Bis**) und einem Suchwort (Nummer, Lieferant, Notiz
oder Position). Unter der Tabelle steht der Kasten **Summe der gefilterten
Rechnungen** (Anzahl, Netto, Steuer, Brutto – über alle Rechnungen des Filters,
nicht nur der Seite); Rechnungen in einer anderen Währung sind mit dem Kurs
ihrer Rechnung umgerechnet und werden gezählt. Hat eine Rechnung in einer
anderen Währung noch **keinen Kurs** oder noch **keine Summen**, fehlt sie in
den Summen: Der Kasten sagt dann „Die Summen sind unvollständig.“ und nennt,
wie viele Rechnungen fehlen – trag Kurs oder Summen nach.

**Hochladen und auslesen.** Auf dem Reiter **Beleg erfassen** wählst du unter **„Rechnung hochladen“** die Datei – ein **PDF oder ein Bild** (PNG, JPEG, WEBP) oder eine
**E-Rechnung als XML** (siehe unten) – und
drückst **„Hochladen und auslesen“**. Rentalars prüft Art, Inhalt und Größe
(die größte erlaubte Datei steht in den Firmendaten und Grundeinstellungen)
und liest die Rechnung **sofort**:

- Aus dem **Text eines PDFs** holt Rentalars Rechnungsnummer, Rechnungsdatum,
  Fälligkeit, einen Lieferanten, den es schon kennt, und die Summen netto,
  Steuer und brutto.
- Ist unter Einstellungen → KI **„Rechnungen lesen“** eingeschaltet (derselbe
  Schalter wie bei „Kauf einpflegen“, Abschnitt 16, „KI“), liest die KI im
  Hintergrund auch die **Positionen**. Ohne KI trägst du die Positionen selbst
  ein. Der Lieferant wird von der KI nur vorgeschlagen; ein Lieferant, den es
  noch nicht gibt, wird nie von allein angelegt: Auf der Seite der Rechnung legst
  du ihn mit **„Lieferanten anlegen“** an – oder bei der Einpflege.
- **Scans und Fotos bewahrt Rentalars auf, liest sie aber nicht.** Es gibt
  keine Texterkennung: Die Seite sagt es, und du erfasst die Rechnung von
  Hand.

Danach öffnet sich die Seite der Rechnung, und Rentalars fragt: **„Auch in der
Materialverwaltung einpflegen?“** – **Ja** führt zu „Ware einpflegen“ (gibt es
noch keine Warenposition, steht dort, dass es geht, sobald die Positionen
gelesen oder eingetragen sind), **Nein** lässt die Rechnung, wie sie ist. Der
Weg zurück: Nach **„Kauf einpflegen“** (Abschnitt 4) fragt Rentalars auf der
Seite „Kauf eingepflegt“, ob der Kauf **auch als Eingangsbeleg in der
Buchhaltung erfasst** werden soll – wenn eine Rechnungsdatei am Kauf hängt. Bei
**Ja** entsteht ein Eingangsbeleg aus dieser Datei: Lieferant, Nummer und Datum
kommen vom Kauf, je Modell und Preis eine Kontierungszeile, und die Exemplare
sind mit ihr verknüpft. Die Summen der Rechnung trägst du selbst ein. Liegt
dieselbe Datei schon im Register, öffnet Rentalars diesen Beleg und legt nichts
doppelt an.

Kopierst du dieselbe Datei noch einmal hoch – oder gibt es schon eine Rechnung
mit derselben Nummer desselben Lieferanten –, warnt Rentalars: „Diese
Rechnung hast du vielleicht schon“, mit Link. Es verhindert nichts.

**Die Seite einer Rechnung.** Oben **„Original öffnen“** (die Datei, geschützt:
nur wer das Register sieht, darf sie laden) und **„Ware einpflegen“**. Darunter:

- Der **Kopf**: Lieferant (suchen oder den Namen tippen), Rechnungsnummer,
  Rechnungsdatum, Fällig am, Währung (und der Umrechnungskurs, wenn sie nicht
  der Euro ist), Summe netto, Steuer, Summe brutto und eine Notiz. **Jedes Feld
  lässt sich korrigieren.** **„Nochmals auslesen“** füllt nur leere Felder und
  überschreibt nie, was du getippt hast; die Positionen ersetzt es nur, solange
  keine von ihnen eingepflegt ist.
- Die **Kontierung**: Rentalars verteilt die Rechnung
  auf **Steuerkonten**, eine Zeile für jede Kostenart. Eine Zeile hat
  **Beschreibung**, **Steuerkonto**, **Art** (**Ware**, **Nebenkosten** oder
  **Sonstiges** – eine Dienstleistung, ein Pfand; wird nur aufbewahrt),
  **Nettobetrag** (der Betrag der ganzen Position, nicht ein Einzelpreis) und
  **Steuersatz**. Nur bei **Ware** fragt die Zeile, **als was sie behandelt
  wird** (Handelsware, GWG, Anlagegut), und nur bei **Anlagegut** nach der
  **Nutzungsdauer in Monaten** – mit einem Link auf die AfA-Tabellen des
  Bundesfinanzministeriums, in denen die Finanzverwaltung Richtwerte
  veröffentlicht. Das **Gewicht eines Stücks** fragt die Zeile nur, wenn die
  Nebenkosten **nach Gewicht** verteilt werden. Artikelnummer, Hersteller und
  Menge fragt die Seite nicht; was das Auslesen dort fand, bleibt an der
  Zeile und wird beim Einpflegen gebraucht – die Stückzahl wählst du dort.
  Ändert du den Nettobetrag einer Zeile, behält sie ihre Menge, und der
  Einzelpreis folgt. **„Weitere Kontierung“** fügt eine Zeile hinzu, höchstens
  100 je Rechnung. Hat die Rechnung Positionen, die Fracht, Versand, Verpackung
  oder Zoll heißen, stuft die Auslesung sie als Nebenkosten ein; ein Rabatt ist
  dabei ein **negativer** Betrag.
- **Die Summe, während du tippst.** Unter den Zeilen steht „Die Kontierungen
  ergeben zusammen … netto“, dazu Steuer und brutto, wenn jede Zeile mit Betrag
  einen Steuersatz hat, und die **Abweichung zur Summe netto** der Rechnung. Sie
  ändert sich mit jedem Wert, den du eingibst, ohne dass die Seite neu lädt;
  gespeichert wird erst mit **„Speichern“**.
- **Das Steuerkonto.** Die Konten sind Stammdaten (Einstellungen → Stammdaten →
  **Steuerkonten**): Nummer und Name, ein Konto lässt sich deaktivieren. Rentalars
  liefert eine Liste nach **SKR 03** mit, wie sie eine Firma der Veranstaltungs-
  technik oft braucht (Wareneingang 3400, Fremdleistungen 3100, Betriebsbedarf
  4980, Werkzeuge und Kleingeräte 4985 …). **Das ist ein Vorschlag:** Stimme die
  Liste mit der Steuerberatung ab, bevor du danach buchst; Rentalars bucht nichts
  und schlägt kein Konto vor, es hält nur fest, was du wählst. Ein Konto, das auf
  einer Kontierung steht, lässt sich nicht löschen.
- **Nebenkosten und Anschaffungskosten.** Die Nebenkosten werden auf die Ware
  umgelegt, **nach Wert** (voreingestellt), **nach Menge** oder **nach Gewicht**
  – den Schlüssel wählst du je Rechnung; ändern zeigt sofort die neue
  Aufteilung darunter, gespeichert wird sie erst mit der Rechnung. Aufgeteilt wird auf
  den Cent genau: Die Anteile ergeben genau die Nebenkosten, ungerade Cent
  bekommen die ersten Stücke. Jede Position zeigt danach ihre
  **Anschaffungskosten** (Betrag plus Anteil) und je Stück. Das Gewicht nimmt
  Rentalars vom Modell, wenn du keines nennst.
- Je Warenposition die **Art des Wirtschaftsguts**: **Handelsware**, **GWG** oder
  **Anlagegut** (mit **Nutzungsdauer in Monaten**). Die Grenze aus den
  Einstellungen **schlägt** nur vor, was die Anschaffungskosten je Stück
  nahelegen (bis zur Grenze – einschließlich – ein GWG, darüber ein
  Anlagegut). Du musst die Art **bestätigen**, indem du sie
  wählst: Lässt du sie leer, lehnt „Ware einpflegen“ die Position ab und nennt
  den Vorschlag. Handelsware wird nie geraten.
- Der **Status**: **offen**, **geprüft**, **eingepflegt**. „Als geprüft
  markieren“ setzt du selbst; „eingepflegt“ setzt Rentalars, sobald jede
  Warenposition ganz eingepflegt ist (du kannst es auch von Hand).
- **Löschen** lässt sich eine Rechnung nur, solange aus ihr noch nichts
  eingepflegt wurde; eine eingepflegte Position lässt sich nicht entfernen. Die
  Exemplare behalten den Link zur Rechnung.

**E-Rechnungen (XRechnung, ZUGFeRD).**

**E-Rechnungen hochladen.** Unter Buchhaltung → Beleg erfassen (und in der Liste der Eingangsrechnungen) kannst du neben PDF und Bildern auch **XML-Dateien** hochladen: XRechnung (UBL oder CII) und die XML-Fassung von ZUGFeRD / Factur-X. Ebenso ein **ZUGFeRD- oder Factur-X-PDF**: Rentalars findet das im PDF eingebettete XML selbst.

**Was passiert.** Eine E-Rechnung wird *exakt* aus ihren Daten gelesen – ohne KI und ohne Textmuster: Lieferant (mit bekanntem Lieferanten verknüpft), Rechnungsnummer, Datum, Fälligkeit, Währung, Summen netto/Steuer/brutto und **alle Positionen** mit Menge, Einzelpreis, Steuersatz und Artikelnummer. Rabatte und Zuschläge auf Belegebene (z. B. Fracht) werden eigene Positionen der Art „Nebenkosten“ (Rabatte negativ). Du prüfst und korrigierst alles wie bei jeder Eingangsrechnung; eingepflegt wird erst, wenn du es sagst.

**Was du siehst.** Unter „Datei“ steht der Hinweis *strukturierte E-Rechnung* mit Format (UBL / CII), Profil (XRechnung, ZUGFeRD / Factur-X MINIMUM, BASIC WL, BASIC, EN 16931, EXTENDED), Spezifikation, Typ-Code, USt-IdNr. und IBAN des Lieferanten, Käufer- und Bestellreferenz und dem Zahlbetrag. Der **XML-Quelltext** lässt sich herunterladen (bei einem ZUGFeRD-PDF zusätzlich zum PDF, das das Original bleibt).

**Wenn sich die Datei widerspricht.** Rentalars vergleicht die Datei mit sich selbst (Summe der Positionen gegen Positionssumme, Positionen mit Rabatten und Zuschlägen gegen Netto, Netto + Steuer gegen Brutto; ein Cent Rundung ist erlaubt). Eine Abweichung ist ein **Hinweis**, keine Ablehnung: Die Rechnung steht trotzdem im Register, du entscheidest am Original.

**Gutschriften.** Eine Gutschrift (UBL CreditNote, Typ-Code 381) behält die Beträge, wie die Datei sie schreibt, und ist als „Gutschrift“ gekennzeichnet. Ihre Positionen haben die Art „Sonstiges“: Aus einer Gutschrift lässt sich keine Ware einpflegen.

**Nicht lesbare Dateien.** XML mit Dokumenttyp-Deklaration (DTD) oder Entitäten wird abgelehnt (die XRechnung verbietet sie; so ist ausgeschlossen, dass beim Lesen Dateien geladen werden oder sich etwas aufbläht), ebenso XML, das kein UBL/CII ist oder nicht wohlgeformt. Ist das an ein PDF angehängte XML unbrauchbar, bleibt das PDF erhalten und wird als PDF gelesen; ein Hinweis nennt den Grund.

**Erneut lesen.** „Erneut lesen“ liest wieder aus dem XML: Leere Felder werden gefüllt, Positionen, die du getippt oder korrigiert hast, bleiben.

**Grenzen.** Rentalars *prüft* eingehende E-Rechnungen nicht gegen die Schematron-Regeln von EN 16931 / KoSIT; es liest sie und vergleicht die Summen. Es liest keine Rechnungen, die nur als Bild oder Scan kommen.

**Ware einpflegen.** Auf der Seite **„Ware einpflegen“** steht je
Warenposition eine Zeile: Wähle ein **Modell** oder tippe den Namen eines neuen
– ein neues Modell braucht seine Kategorie –, gib die **Stückzahl** (vorgewählt:
was von der Position noch übrig ist; wählst du **mehr** als die Menge der Zeile,
bleibt ihr Nettobetrag, und der Stückpreis folgt – drei Stück einer Zeile über
300 € kosten zusammen 300 €, nicht je 300 €; teilt sich der Betrag nicht auf vier Nachkommastellen durch die Stückzahl, bleibt die Menge der Zeile, und die Stücke teilen den Betrag auf den Cent genau unter sich auf), den Lagerort und auf Wunsch die
Seriennummern an; bei einem neuen Modell lässt sich **„Als Menge führen
(Mengenmaterial)“** wählen. Mit dem Haken „Diese Position einpflegen“ nimmst du
sie mit, ohne lässt du sie aus. **„Vorschau zeigen“** zeigt dann, **was angelegt
würde**: je Position Modell, Stück, Nettobetrag, Anteil an den Nebenkosten,
Anschaffungskosten, je Stück, Art des Wirtschaftsguts und Nutzungsdauer. Es
wird nichts angelegt, bevor du **„Ja, genau so einpflegen“** ankreuzt und
**„Einpflegen“** drückst – dann alles oder nichts.

- Rentalars benutzt dabei dieselben Prüfungen wie „Kauf einpflegen“: fortlaufende
  IDs, Händler, Rechnungsnummer und -datum, die Rechnung als Datei am Exemplar,
  Warnung bei doppelter Seriennummer, kein Kundenmaterial, und Preise nur mit dem
  Recht für Einkaufspreise.
- Jedes Exemplar bekommt seinen **Einkaufspreis**, den **Anteil an den
  Nebenkosten**, die **Anschaffungskosten** (Einkaufspreis plus Nebenkosten), die
  Art und die Nutzungsdauer – und das **Kaufdatum** ist das Rechnungsdatum.
  Daraus rechnet Rentalars Abschreibung und Restbuchwert (Abschnitt 4,
  „Anlagevermögen, Abschreibung und Restbuchwert“). Die Kosten bleiben an den
  Exemplaren, wie sie waren: Ändert sich später der Schlüssel der Rechnung,
  ändert Rentalars die Exemplare nicht nachträglich.
- Eine Position, die schon eingepflegt ist, wird nicht noch einmal
  eingepflegt – außer du setzt **„Nochmals einpflegen“**. Eine nur zum Teil
  eingepflegte Position (6 von 10) lässt sich vervollständigen. Am Exemplar steht,
  aus welcher Rechnung und Position es stammt.

**Einstellungen für Eingangsrechnungen.** Unter Einstellungen → Dokumente und
Buchhaltung → **Eingangsrechnungen** (oder über den Knopf auf der Liste; dafür
braucht es das Modul Verwaltung) stellst du ein: die **Grenze eines
geringwertigen Wirtschaftsguts (GWG), netto** – voreingestellt 800 € –, die
**Standard-Nutzungsdauer (Monate)** eines Anlageguts ohne eigene – voreingestellt 60
– und, ob ein voll abgeschriebenes Anlagegut mit **1 € Erinnerungswert**
stehen bleibt (**„Erinnerungswert von 1 € behalten“**, aus).

**Gespeichert** liegen die Dateien im Medienordner des Servers, unter
`incoming/<Jahr>/` – sie gehören in die Sicherung (Anleitung [Sicherung](../betrieb/sicherung.md)).
Über die Schnittstelle gibt es alles auch (Abschnitt 16, „API-Token“): die
Liste mit ihren Summen, Hochladen, Positionen, die Aufteilung der Nebenkosten
und das Einpflegen mit Vorschau und Bestätigung.

**Nicht gebaut:** Rentalars bucht nicht selbst und schlägt kein Steuerkonto
vor; die Konten der Kontierung sind die Vorbereitung für den Austausch mit der
Steuerberatung (Abschnitt 17).

### Zahlungen, Offene Posten, EÜR und Archiv

*Die Zahlungen sieht, wer die Liste der Ausgangsbelege sieht (Preisrecht und alle Projekte), und bei Eingangsrechnungen, wer das Register sieht; eintragen darf, wer dort auch ändern darf. EÜR, Archiv und Prüfer-Export brauchen Einstellungen (Lesen) und beide Preisrechte – Verkaufs- und Einkaufspreise –, weil sie die Zahlen der ganzen Firma zusammenführen.*

**Zahlungen.** Zu jeder Rechnung – ausgehend und eingehend – trägst du
**Zahlungen** ein: Tag, Betrag (brutto, wie er auf dem Konto ankam oder ging;
negativ ist eine Rückzahlung), Art und Verwendungszweck. Der Knopf
**„Zahlungen“** steht an der Rechnung (Reiter „Dokumente“ des Projekts, Seite
einer freien Rechnung, Seite der Eingangsrechnung). Ein Rest wird **gerechnet,
nie gespeichert**: Rechnungsbetrag (bei einer Schlussrechnung nach Abzug der
Abschläge), minus Teilgutschriften und Storno, minus die Zahlungen. Der Stand
heißt „offen“, „teilweise bezahlt“, „bezahlt“, „überzahlt“, „storniert“ oder
„Rückzahlung fällig“. **Eine Zahlung wird nicht geändert und nicht gelöscht:**
Eine falsche wird **storniert**, mit Grund; sie bleibt in der Liste stehen,
zählt aber nicht mehr. Altrechnungen aus dem Import, die dort als bezahlt galten,
gelten als bezahlt, ohne dass eine Zahlung eingetragen ist. Zahlungen
werden von Hand eingetragen oder aus einem Kontoauszug übernommen
(siehe „Bank“ unten). Bei einer Eingangsrechnung in fremder Währung stehen Betrag und Zahlung in
der Währung der Rechnung; die Euro folgen aus dem Kurs der Rechnung.

**Offene Posten** (Reiter in der Buchhaltung) zeigt, was Kunden noch schulden
(„Kunden schulden“) und, für wer Einkaufspreise sehen darf, was noch an Lieferanten zu zahlen ist, das
älteste Fälligkeitsdatum zuerst, mit Summe und dem überfälligen Teil, auch als CSV.
Daneben gibt es die Seite **„Guthaben“**: Rechnungen, die **überzahlt** oder
nach der Zahlung **storniert oder gutgeschrieben** wurden (wir schulden dem Kunden Geld),
und **Gutschriften von Lieferanten**, die noch nicht zurückgezahlt sind (der Lieferant
schuldet uns Geld). Die Rückzahlung trägst du als **negative Zahlung** an der Rechnung ein;
danach verschwindet die Zeile. Jeder sieht nur die Seite, die er sehen darf.

**Bank.** Der Reiter **Bank** (sieht, wer beide Preisrechte hat und alle Projekte und das Material lesen
darf; ändern darf, wer auch Projekte überall und das Material bearbeiten darf) liest einen **Kontoauszug** ein: **CAMT.053** (XML) oder die
**CSV-Datei** der Bank (Trennzeichen, Zeichensatz und die Kopfzeile werden erkannt,
Zeilen davor und danach übersprungen; eine Zeile mit Datum, aber ohne lesbaren Betrag
lehnt die Datei ab – ein Auszug mit fehlender Zeile wäre schlimmer als keiner). Von der Datei bleiben nur die Buchungen – Tag,
Betrag, Gegenseite, IBAN, Verwendungszweck – und ihre Prüfsumme; dieselbe Datei wird nicht
zweimal gelesen, und eine Buchung, die ein früherer, überlappender Auszug schon hatte,
kommt nicht noch einmal hinein. Zu jeder **offenen** Buchung zeigt die Seite die Rechnungen,
zu denen sie passen könnte, nach: **Rechnungsnummer im Verwendungszweck** (das stärkste
Zeichen), **Betrag gleich dem offenen Rest** und **Name**. Eingehendes Geld passt zu
offenen Ausgangsrechnungen und zu Gutschriften von Lieferanten, ausgehendes zu offenen
Eingangsrechnungen und zu Rückzahlungen an Kunden – in die falsche Richtung bucht Rentalars
nicht. Sehr kurze oder reine Zahlen als Rechnungsnummer (Datum, Betrag) liest es nicht aus dem
Verwendungszweck. **Ein Vorschlag bucht nichts:** Erst ein
Klick auf **„Zahlung eintragen“** legt die Zahlung an – mit denselben Regeln wie von Hand
(kein Tag in der Zukunft, nur Euro) – und verbindet sie mit der Buchung. Mit einem Grund
lässt sich eine Buchung **beiseitelegen** („Beiseitelegen“, etwa für Privates oder
Gebühren) und wieder zurücknehmen. Stornierst du die Zahlung an der Rechnung, ist die
Buchung wieder offen. Teilzahlungen trägst du von Hand an der Rechnung ein; eine Buchung
wird immer als Ganzes zugeordnet. Die Zuordnung ist ein Hilfsmittel, **kein
Abgleich mit der Bank**: Rentalars holt keine Auszüge von selbst ab, und Fremdwährung wird
nicht zugeordnet. Die API: `/accounting/bank/imports` und `/accounting/bank/transactions`.

**Die E-Rechnung prüfen.** Rentalars prüft jede Rechnung, die es ausstellt, und jede
E-Rechnung, die ihr bekommt, gegen **eigene Kernprüfungen** der EN 16931 und der
XRechnung (Pflichtangaben, Summen, Steuerkategorien, Leitweg-ID …). Das
Ergebnis steht an der Rechnung („erfüllt die geprüften Regeln“ oder „n Regeln
verletzt“ mit der Nummer der Regel) und lässt sich mit „Erneut prüfen“
wiederholen. Standardmäßig ist die Prüfung **ein Befund, keine Sperre**: Die
Rechnung wird trotzdem ausgestellt. Wer das nicht will, schaltet in den
Einstellungen **„Rechnung mit Fehlern nicht ausstellen“** ein. **Das ist kein
Ersatz für einen Validator:** Schema und Schematron der KoSIT gehören nicht dazu.

**ZUGFeRD / Factur-X.** In den Einstellungen wählst du das **Format der
Rechnung**: **XRechnung** (die PDF und, daneben, die XML-Datei) oder **ZUGFeRD /
Factur-X** (eine PDF/A-3, in der die Rechnungsdaten stecken). Das Format gilt für
Rechnungen, die ab jetzt erstellt werden; vorhandene bleiben, wie sie sind. Die
Prüfsumme der Rechnung ist die der gespeicherten Datei. Beim Versand geht bei
einer XRechnung die XML-Datei mit, wenn der Kunde eine Käuferreferenz (die
Leitweg-ID einer Behörde) hat; sonst lässt sie sich dazuwählen. Eine ZUGFeRD-PDF
geht allein, ihre Daten stecken darin.

**EÜR.** Der Reiter **EÜR** rechnet das Jahr nach **Zufluss und Abfluss**: Einnahmen sind
die Zahlungen auf Ausgangsrechnungen, aufgeteilt nach den Steuersätzen der
Rechnung, dazu Verkäufe aus dem Bestand ohne Rechnung am Tag des Verkaufs;
Ausgaben sind die Zahlungen auf Eingangsrechnungen, aufgeteilt nach dem
Steuerkonto der Positionen. **Was als Anlagegut oder GWG eingepflegt ist,
kommt nicht als Ausgabe, sondern als Abschreibung** (ein GWG im Jahr der
Anschaffung ganz, ein Anlagegut nach dem Monatsprinzip); bei einem Verkauf
geht der Restbuchwert als Ausgabe ab. Die **Umsatzsteuer** steht daneben:
vereinnahmt, gezahlte Vorsteuer, Saldo. Zahlungen an das Finanzamt erkennt
Rentalars am **Lieferanten**: In den Stammdaten kennzeichnest du ihn als
„Finanzamt – Umsatzsteuer“ oder „Finanzamt – Einkommensteuer und andere private
Steuern“. Was an ein Finanzamt für Umsatzsteuer gezahlt wird, ist keine Ausgabe, sondern
wird mit der Umsatzsteuer verrechnet („Noch an das Finanzamt zu zahlen“); die andere Art
steht für sich und zählt nicht als Betriebsausgabe. Eine Erstattung ist eine negative
Zahlung. Die Gewerbesteuer ist eine Ausgabe wie jede andere; ihr Lieferant bleibt
ungekennzeichnet. Die Kennzeichnung sieht und ändert nur, wer die EÜR sehen darf (sie bestimmt
den Gewinn). Bei einem **Kleinunternehmer** (Einstellung) zählt alles brutto.

Die EÜR zeigt zwei Zahlen: das **Ergebnis ohne Umsatzsteuer** und den **Überschuss, wie ihn die EÜR zählt** (mit der Umsatzsteuer der Zahlungen; die noch geschuldete Umsatzsteuer steht dazwischen). Zahlungen an ein Finanzamt innerhalb von zehn Tagen um den Jahreswechsel meldet Rentalars als Hinweis: Die 10-Tage-Regel (§ 11 EStG) wendet es **nicht** an, jede Zahlung zählt an ihrem Tag. Verkaufst du einen Teil einer Anlage aus Mengenmaterial, bleibt die Abschreibung früherer Jahre unverändert; die verkauften Stücke schreiben bis zum Tag des Verkaufs ab. Ein Anlagegut, das als **verloren** oder **ausgemustert** gesetzt wird, schreibt von diesem Tag an nicht weiter ab, und sein Restbuchwert geht als Abgang in die EÜR ein; kennt das Änderungsprotokoll den Tag nicht mehr, meldet Rentalars das.
Die Seite nennt, was nur genähert ist (Verkäufe ohne Rechnung,
Auslandsrechnungen ohne Kurs, Ware über der GWG-Grenze, die noch nicht
eingepflegt ist) und liefert eine **CSV-Datei** mit jeder Zeile hinter den Zahlen.
**Das ist eine Vorbereitung für die Steuerberatung, keine Steuerberatung und
keine Abgabe.** Eine doppelte Buchführung gibt es nicht; sie ist vorgemerkt.

**Archiv.** Jede ausgestellte Ausgangsrechnung (und jedes andere Dokument für
Kunden) und jede Eingangsrechnung kommt nachts ins **Archiv**: Dateien mit
SHA-256 und Größe, dazu das Ende der **Aufbewahrungsfrist** – das Ende des
Kalenderjahres plus acht Jahre für Rechnungen und Buchungsbelege, sechs für
Geschäftsbriefe (Einstellungen). Nachts wird ein Teil des Archivs gegen die
Prüfsummen geprüft, so dass jede Datei innerhalb der eingestellten Tage drankommt.
Eine veränderte oder fehlende Datei macht den **Selbsttest** rot und erreicht die
Betreiber. Eine archivierte Eingangsrechnung lässt sich bis zum Ende der Frist
nicht löschen (ein neuer Upload noch einen Tag lang); nach der Frist bleibt der
Eintrag im Protokoll („nach der Frist gelöscht“). Ausgangsbelege lassen sich nie löschen.
Auf der Seite **Archiv** siehst du die Zahlen, die Befunde und die Liste und prüfst
alles sofort. Die Wartung ändert nichts an Zahlungen: Eine Zahlung lässt sich auch im Programmcode nicht mehr ändern oder löschen, nur stornieren.

**Export für eine Prüfung und Verfahrensdokumentation.** Auf der Seite Archiv lädst du
einen **ZIP-Export** (ein Jahr oder alle Jahre) – bei einem großen Archiv mit
**„Im Hintergrund erstellen“**: Die Seite zeigt den Fortschritt, die ZIP-Datei liegt
danach unter „Aufgaben“ und nur die Person, die sie angefordert hat, sieht sie: Tabellen als CSV (Ausgangsbelege,
Eingangsrechnungen, Zahlungen, die Zeilen der EÜR, Anlagenspiegel, Archivprotokoll), eine
Beschreibung `index.xml` in der Art des Beschreibungsstandards, die Belege selbst
und `SHA256SUMS`. Die **Verfahrensdokumentation** ist ein Entwurf, den Rentalars
aus den Einstellungen füllt (Seite, PDF, Markdown); den Rest ergänzt die Firma
selbst. **Rentalars ist nicht GoBD-zertifiziert, und `index.xml` ist nicht mit einer
Prüfsoftware getestet** – bespreche beides mit der Steuerberatung.

### Altprojekte importieren

Aus der Zeit vor Rentalars liegen eure Rechnungen als PDF herum. **Buchhaltung → Altprojekte importieren** macht daraus **abgeschlossene
Projekte** mit ihrer Rechnung – damit Kunde, Verlauf und Beleg in Rentalars
stehen. Wer dafür Preise sehen und Projekte bearbeiten darf, sieht den Reiter.

1. **Hochladen.** Wähle bis zu **30 PDFs** (jedes höchstens 10 MB, zusammen
   höchstens 120 MB), die **eigenen Ausgangsrechnungen** vergangener Projekte, und
   drücke **„Hochladen und auslesen“**. Eine Datei, die schon einmal importiert
   wurde oder zweimal im Stapel liegt, erkennt Rentalars und liest sie nicht.
   Rentalars liest im Hintergrund; ein Stapel von 30 PDFs dauert wenige
   Sekunden. Nur **PDFs mit Text** gehen – ein Scan wird nicht gelesen (es gibt
   keine Texterkennung).
2. **Auslesen.** Ist unter Einstellungen → KI das Lesen von Rechnungen
   eingeschaltet, liest die KI jede Rechnung; **nur der Text** geht an den
   Anbieter, der dort gewählt ist. Sonst – oder wenn die KI nicht antwortet –
   holt Rentalars Kunde, Rechnungsdaten und Positionen mit Mustern aus dem Text.
   Das klappt bei einfachen Rechnungen; kontrolliere jedes Feld. Der Reiter
   zeigt unter **„Zu prüfen“** den Stapel.
3. **Prüfen.** Unter **„Alte Rechnungen prüfen“** steht jede Rechnung als Formular,
   mit dem Original-PDF daneben: **Kunde** (ein vorhandener Kunde der Stammdaten
   oder die Daten eines neuen aus der Rechnung), **Rechnungsnummer**, Datum,
   Leistungszeitraum, **Veranstaltung / Projektname**, Veranstaltungsort,
   **„Die Rechnung wurde bezahlt“** (und „Bezahlt am“) und die **Positionen**
   (Text, Menge, Einheit, Einzelpreis netto, Rabatt, Steuer, auf Wunsch einem
   **Produkt** zugeordnet – sonst eine freie Zeile –, auch Textzeilen). Rentalars
   markiert, was nicht stimmt: **Fehler** verhindern das Übernehmen (keine
   Nummer, eine Nummer, die es schon gibt oder die in eurer laufenden Folge
   liegt, ein unbekannter Steuersatz); **Warnungen** nur sagen, dass Summen und
   Steuer nicht zu den Positionen passen. **„Nicht übernehmen“** lässt eine
   Rechnung aus; bei **„Projekt“** kannst du mehrere Rechnungen **zu einem
   Projekt zusammenfassen** – die weitere Rechnung nimmt dessen Kunden.
   **„Änderungen speichern“**, dann **„Prüfen und weiter“**.
   Zusätzlich gilt: Jede Position hat eine **Beschreibung** (die
   weiteren Zeilen unter dem Namen, wie sie auf der Rechnung standen – du kannst
   sie ändern) und eine **Art**: **Material**, **Personal** oder **Logistik**.
   Rentalars schlägt die Art aus Text und Einheit vor (Stunden, „Techniker“,
   „Tontechnik“ → Personal; Kilometer, „Transport“, „Anlieferung“ → Logistik;
   sonst Material); du kannst sie ändern und **speichern**, dann bietet
   Rentalars die passende **Funktion** (Personal) oder das passende **Fahrzeug**
   (Logistik: ein Kraftfahrzeug des Fuhrparks) beziehungsweise das **Produkt**
   (Material) an. Personal wird eine Personalzeile ohne Person – nach Stunden
   (Einheit Stunden), nach Tagen (volle Tage) oder als Pauschale –, Logistik eine
   Fahrzeugzeile mit eigener Fahrt als Pauschale. Beim **Kunden** zeigt die Seite
   in einem Satz, was Rentalars gefunden hat: ein vorhandener Kunde (gleicher
   Name und gleiche Adresse, oder ein ähnlicher Name an der gleichen Adresse),
   Kunden, die gemeint sein könnten, oder „kein bestehender Kunde passt – aus den
   Daten der Rechnung wird ein neuer angelegt“. Das Übernehmen legt einen neuen
   Kunden nur an, wenn du es so stehen lässt.
4. **Übernehmen.** Die Seite **„Altprojekte übernehmen“** zeigt **genau, was
   angelegt wird**: Kunde („wird angelegt“ oder vorhandener Kunde), Projekt,
   Positionen und Rechnungen. Erst **„n Projekte übernehmen“** legt es an. Du
   kannst den Stapel auch teilweise übernehmen.

**Was daraus wird.** Pro Rechnung (oder Gruppe) ein **abgeschlossenes Projekt**
mit der Nummer `ALT-<Jahr>-<laufende Nummer>` (eigener Zähler) und den Positionen
als freie Zeilen oder Produktzeilen, und die Rechnung als **ausgestellter Beleg**
mit Nummer, Datum, Summen, dem Stand „bezahlt“ oder „offen“ und dem Original-PDF.
Im Verlauf des Projekts steht „Importiert aus Rechnung …“.

**Was es nicht tut.** Der Import ist **still**: Es geht keine Mail hinaus, es
entstehen keine Aufgaben, nichts wird reserviert und keine Verfügbarkeit
verändert, keine Automation und kein Webhook läuft, nichts geht an Lexware Office,
und die **Nummernfolge eurer laufenden Rechnungen bleibt unberührt**. Gutschriften,
andere Währungen und Scans gehen nicht.

**Zurücknehmen.** Auf dem Reiter lässt sich ein Import **sieben Tage lang**
zurücknehmen (**„Import zurücknehmen“**), solange an den Projekten, Rechnungen und
neuen Kunden nichts geändert wurde; sie werden dann wieder entfernt. Die
hochgeladenen PDFs, die nicht übernommen wurden, räumt Rentalars nach **14 Tagen**
weg – nicht nach der Uhr, sondern erst, wenn jemand die Übersicht öffnet oder
eine Datei hochlädt (Betrieb: `DATA_DIR/legacy-invoices`).

**DATEV.** Importierte Rechnungen stehen **nicht** im DATEV-Export, solange du
im Export nicht **„Aus einem Altsystem übernommene Rechnungen einschließen“**
ankreuzt (Abschnitt 16, „Buchhaltung: Lexware Office und DATEV“; über die
Schnittstelle `include_historic`). Sie lassen sich nicht an Lexware Office
übergeben, nicht buchen und nicht stornieren und stehen nicht in der
Fehlerliste von Lexware.

Wie gut die KI **fremde** Rechnungen liest, ist nicht geprüft: Lass die ersten
Stapel von jemandem ansehen und lies die Vorschau kritisch.

### Vorlagen und Textbausteine

**Dokumentvorlagen** (Einstellungen → Dokumentvorlagen): Für jede
Dokumentart – auch das Angebot – gibt es eine Vorlage mit **Überschrift**,
**Einleitung**, **Schlusstext**, einer **zusätzlichen Fußzeile** (sie
steht unter Anschrift, Bankverbindung und Registerangaben) und dem Haken
**„Logo drucken“**. Vorlagen werden geändert, nicht angelegt oder
gelöscht.

Die Vorlage des **Angebots** hat zusätzlich das Feld **„Gültigkeit in
Tagen“**: So viele Tage gilt ein neues Angebot, wenn du beim Erstellen
nichts anderes einträgst. Voreingestellt sind 14 Tage.

In Einleitung und Schlusstext setzen **Platzhalter** die Daten des
Projekts ein:

| Platzhalter | wird zu |
|---|---|
| `{project}` | der Projektnummer, z. B. 2026-0042 |
| `{project_name}` | dem Namen des Projekts |
| `{customer}` | dem Namen des Kunden |
| `{period}` | dem Zeitraum „Material außer Haus“ – dem Leistungszeitraum –, z. B. 12.06.2026 – 15.06.2026 |
| `{venue}` | dem Veranstaltungsort |
| `{due_date}` | dem Fälligkeitsdatum (nur bei der Rechnung) |
| `{payment_terms}` | dem Zahlungsziel in Tagen (nur bei der Rechnung) |
| `{valid_until}` | dem Datum „Gültig bis“ (nur beim Angebot) |
| `{validity_days}` | der Gültigkeit in Tagen, z. B. 30 (nur beim Angebot) |

Mitgeliefert ist für die Rechnung zum Beispiel diese Einleitung und dieser
Schlusstext:

```
Für das Projekt {project} „{project_name}“ ({period}) berechnen wir:

Bitte überweisen Sie den Betrag bis zum {due_date} unter Angabe der Rechnungsnummer.
```

Und für das Angebot:

```
Gerne bieten wir Ihnen für das Projekt {project} „{project_name}“ im Zeitraum {period} Folgendes an. Dieses Angebot gilt bis zum {valid_until}.

Wir freuen uns auf Ihren Auftrag.
```

Ein Platzhalter, den Rentalars nicht kennt, bleibt stehen, wie er
geschrieben ist – ein Tippfehler fällt im Entwurf also auf.

**Vorlagentexte auf Englisch oder Deutsch**. Schreibt ihr
euren Kunden auf Englisch – oder wollt ihr zurück zu Deutsch –, öffne unter
Einstellungen → „Dokumente und Buchhaltung“ (oder über der Liste der
Dokumentvorlagen) die Seite **„Vorlagentexte auf Englisch oder
Deutsch“**:

1. Oben **„Englische Texte“** oder **„Deutsche Texte“** wählen.
2. Je Vorlage stehen Überschrift, Einleitung und Schlusstext mit
   **„Jetzt“** und **„Neu“**; angehakt ist, was übernommen wird. Felder mit
   **„eigener Text“** – weder der deutsche noch der englische Standardtext
   – sind nicht angehakt und bleiben, solange du sie nicht anhakst.
   Fußzeile, Logo und die Gültigkeit des Angebots bleiben immer.
3. Die „Sprache der Dokumente“ ist eine eigene Einstellung (Abschnitt 16,
   „Firmendaten und Grundeinstellungen“); mit **„Auch die Dokumente auf
   Englisch stellen“** bzw. „… auf Deutsch stellen“ wechselt sie gleich mit.
4. **„Englische Vorlagentexte übernehmen“** bzw. „Deutsche Vorlagentexte
   übernehmen“.

Das Änderungsprotokoll behält die bisherigen Texte. Hat jemand einen Text
geändert, während die Seite offen war, bleibt seiner stehen, und die Seite
sagt es. Ansehen darf die Seite, wer die Einstellungen lesen darf;
übernehmen, wer sie ändern darf.

**Textbausteine** (Einstellungen → Textbausteine) sind Absätze, die beim
Erstellen eines Dokuments dazukommen: Mietbedingungen, Haftungshinweise,
„Aufbau nur bei trockener Witterung“. Jeder hat einen **Namen**, den
**Text** (Platzhalter gehen auch hier), unter **„für“** die Dokumentarten,
bei denen er angeboten wird (keine angehakt: alle), und den Haken
**aktiv**. Beim Erstellen hakst du an, welche mitkommen; sie stehen über
dem Schlusstext. Eine Stornorechnung bekommt nie Textbausteine.

### Nummernkreise der Dokumente

Jede Dokumentart zählt für sich (Einstellungen → Nummernkreise):
**Angebote** (`AN-2026-0001`), **Auftragsbestätigungen**
(`AB-2026-0001`), **Lieferscheine** (`LS-2026-0001`), **Rechnungen und
Stornos** (`RE-2026-0001`) und **Crew-Dispositionen** (`CD-2026-0001`),
jedes Jahr neu. Präfix, Stellen und nächste Nummer lassen sich ändern wie
bei den übrigen Kreisen (Abschnitt 16).

Rechnungsnummern müssen lückenlos sein. Darum vergibt Rentalars eine
Nummer erst, wenn das Dokument wirklich erstellt wird – nie für einen
Entwurf und nie, wenn etwas fehlt. Setze die nächste Rechnungsnummer
nicht herunter. Ein Kreis, der jedes Jahr neu beginnt, behält die „nächste Nummer“, die du
mitten im Jahr einträgst (etwa nach einem Umstieg von einem anderen Programm); erst im
neuen Jahr fängt er wieder bei der Startnummer an. Das Datum eines Belegs ohne Projekt liegt im laufenden Jahr und nicht
in der Zukunft; lässt du es leer, gilt heute.

### Dateien des Projekts

Unter den Dokumenten steht im selben Reiter der Kasten **„Dateien“**: alles,
was sonst zum Projekt gehört – Bühnenpläne, Rider, Showfiles, Verträge,
Bestellungen, Lichtplots; beim Servicefall ebenso. Mit **„Datei hochladen“** darin legst du eine
Datei ab. Dabei wählst du eine **Dokumentart**; sie bestimmt, ob die Datei
**für die Crew sichtbar** ist. Bühnenplan, Rider, Ablaufplan und Hallenplan
sind es, Vertrag und Bestellung nicht. Das lässt sich je Datei anders
einstellen (Stift).

**Dokumente der Lieferanten** – Angebote, Auftragsbestätigungen,
Lieferscheine und Rechnungen zu Zumietungen – stehen hier ebenfalls, mit
ihrer Art und einem Link „Zumietung bei …“ zur Seite des Lieferanten in
diesem Projekt; abgelegt werden sie dort (Abschnitt 9, „Zumieten“). Ihre
Art änderst du am Stift unter „Art des Dokuments“; für die Crew sind sie
nicht sichtbar, solange du es nicht anders einstellst.

Erlaubt sind die üblichen Dokument- und Bildformate (PDF, Office- und
OpenDocument-Dateien, Bilder, Text), ZIP-Archive, MVR-Dateien und Showfiles (gleich unten), bis zu einer Größe, die in den
Einstellungen steht (voreingestellt 50 MB; das Formular nennt sie).
Programme und Skripte nimmt Rentalars nicht an. Anhänge einer Mail landen
hier mit einem Klick (Abschnitt 14), eine MVR-Datei beim Import von selbst
(Abschnitt 7, „MVR-Datei importieren“).

**Showfiles.** Die Show eines Lichtpults, Medienservers oder Tonpults
gehört zum Projekt: Wer die nächste Show programmiert, findet hier den
letzten Stand, und die Crew hat ihn vor Ort. Mit „Datei hochladen“ lädst
du sie hoch wie jede andere Datei. Rentalars erkennt Showfiles an der
Endung – etwa grandMA3 (`.show`), grandMA2 (`.show.gz`), ETC Eos
(`.esf`, `.esf3d`), Hog 4 und ChamSys MagicQ (`.shw`), Avolites Titan
(`.avo`), Resolume (`.avc`), WATCHOUT, QLab, Yamaha DM7 (`.dm7f`), DM3,
CL/QL und TF, Midas M32 und Behringer X32, DiGiCo (`.ses`), d&b R1
(`.dbpr`) und L-Acoustics LA Network Manager; welche Endungen genau, nennt
die Meldung, wenn eine Datei nicht angenommen wird. Eine Show, die ein
**Ordner** ist – disguise, dLive und viele andere –, packst du als
**ZIP-Datei**.

Ein Showfile bekommt von selbst die Dokumentart **„Showfile“** (für die
Crew sichtbar) und, wo die Endung es eindeutig sagt, das **„Pult oder
Software“**; bei `.shw` – Hog 4, MagicQ oder M32 – wählst du es selbst.
Trag die **„Software-Version“** ein, mit der die Show gespeichert wurde.
Das zuletzt hochgeladene Showfile eines Pults ist seine **„aktuelle
Show“**; frühere desselben Pults bleiben, wie sie sind. Am Stift der Datei
änderst du Pult, Version und welches die aktuelle Show ist. In der Liste
und im Überblick steht unter dem Namen „Pult · Version …“ und, bei der
aktuellen, „aktuelle Show“. Für große Shows mit Medien kann ein
Administrator die „größte hochladbare Datei“ erhöhen (Abschnitt 16).

---

## 12. Personal

*Für alle mit Zugriff auf „Personal“; der Teil über das eigene Profil und
den Überblick eines Projekts ist für jeden, der eingeplant wird.*

Zwei Dinge, die Rentalars streng auseinanderhält:

| | Woher | Wer sieht es |
|---|---|---|
| **Preis für den Kunden** | vom Dienstleistungsprodukt der Funktion, z. B. `D-003` „Tontechniker“ zu 45,00 € die Stunde | wer Preise sehen darf |
| **Kosten für die Firma** | vom Stunden- oder Tagessatz der Person in dieser Funktion, z. B. 35,00 € die Stunde, 280,00 € am Tag – ohne eigenen Satz vom Richtwert der Funktion | wer Stundensätze und Personalkosten sehen darf – und die Person selbst |

Beide können ab einer Grenze von Stunden am Tag höher sein (unten, „Was
Personal kostet und einbringt“).

Der Kunde zahlt nicht „Annas Stundensatz“, sondern eine Tontechnikerstunde.
Was Anna die Firma kostet, geht ihn nichts an – und auch nicht jeden im
Haus.

### Funktionen

**Personal → Funktionen.** Eine Funktion ist, *als was* jemand eingeplant
wird: Tontechniker, Lichttechniker, Stagehand. Eine neue Installation
bringt acht mit – Techniker, Lichttechniker, Tontechniker,
Medientechniker, Stagehand, Lager, Projektplanung und Sonstiges –; du
kannst sie umbenennen, ergänzen, deaktivieren.

**Was der Satz bedeutet** (Hinweis in Liste und Formular): Der
Satz einer Funktion ist der **Stundenlohn** bzw. die Tageskosten der
eingeplanten Kräfte – ein interner Kostenwert, **nicht der Preis für den
Kunden**. Kundenpreise änderst du unter Materialverwaltung → Produkte, am
Dienstleistungsprodukt der Funktion; der Hinweis führt mit einem Link dorthin
(nur mit dem Recht, Produkte zu lesen).

**Jede Funktion hat genau ein Dienstleistungsprodukt**, und jedes
Dienstleistungsprodukt gehört zu genau einer Funktion – beide mit demselben
Namen, das Produkt in der Kategorie D. Sein Preis ist, was der Kunde für
eine Stunde dieser Funktion zahlt. Legst du eine Funktion an („Neue
Funktion“), entsteht ihr Dienstleistungsprodukt beim Speichern von selbst
– Einheit Stunde, Abrechnung nach Stunden –; den **„Preis je Stunde für
den Kunden (netto)“** trägst du gleich im Formular ein (mit Preisrecht)
oder später am Produkt. Umgekehrt entsteht die Funktion, wenn du unter
Materialverwaltung → Produkte eine Dienstleistung anlegst (Abschnitt 5,
„Produktarten“). Benennst du eines um, folgt das andere, solange beide
gleich hießen.

In der Liste der Funktionen führt das Dienstleistungsprodukt zu seiner
Seite, ebenso auf der Seite einer Funktion; dort änderst du Preis,
Steuersatz und die Grenze in Stunden pro Tag (unten, „Was Personal kostet
und einbringt“). Hat es noch keinen Preis, steht „noch kein Preis“ da, und
Personalpositionen dieser Funktion kosten den Kunden 0,00 €, bis du einen
einträgst. Die acht mitgelieferten Funktionen bekommen den
Preis und die internen Kosten je Stunde, die bei der Ersteinrichtung
angegeben wurden (vorgeschlagen 45,00 € und 30,00 €, Abschnitt 3); in
Installationen von vorher kamen sie ohne Preis.

Je Funktion außerdem:

- **Richtwert für interne Kosten je Stunde** – damit die Kalkulation schon
  rechnen kann, solange ein Platz noch nicht besetzt ist oder die Person
  keinen eigenen Stundensatz hat.
- **Richtwert je Stunde ab der Grenze** – dasselbe für die Stunden eines
  Tages über der Grenze des Dienstleistungsprodukts; leer gilt der
  Richtwert je Stunde.
- **Richtwert für interne Kosten je Tag** – dasselbe für einen ganzen Tag
  (Abrechnung „je Tag“, Abschnitt 12, „Was Personal kostet und
  einbringt“); er gilt, solange ein Platz nicht besetzt ist oder die
  Person keinen eigenen Tagessatz hat. Die Liste der Funktionen zeigt ihn
  in der Spalte „Richtwert je Tag“. Die Richtwerte sieht nur, wer
  Personalkosten sehen darf.
- **Höchster Rabatt in Prozent** – leer: keine Grenze, 0: wird nie
  rabattiert (Abschnitt 8, „Rabatte“). Nur mit Preisrecht.

**Löschen.** „Funktion löschen“ nimmt das Dienstleistungsprodukt mit. Haben
Personen die Funktion oder war sie schon eingeplant – auch als
Materialposition mit ihrem Produkt –, geht das nicht; dann deaktivierst du
sie. Das Produkt einer Funktion lässt sich nicht für sich löschen.

**Die Funktion ist die Voraussetzung fürs Einplanen.** Zur Planung
angeboten wird nur, wem mindestens eine Funktion zugeordnet ist – in der
Auswahl der Personalpositionen und bei „Wer ist frei?“. Reine Büro-Konten
ohne Funktion erscheinen dort nicht; im Personalplan stehen sie trotzdem,
solange der Haken „Nur Personen mit Einsätzen oder Abwesenheiten“ nicht
gesetzt ist (Abschnitt 15, „Personalplan“).

### Personen

**Personal → Neue Person.** Vorname, Nachname, Art (Festangestellte,
Aushilfe, Freie Kraft), **Position im Unternehmen** – etwa „Leitung Licht“;
sie steht auch in der E-Mail-Signatur (Abschnitt 14) –, E-Mail, Telefon,
Notiz. Für freie Kräfte zusätzlich Firma, Anschrift, Steuernummer und
USt-IdNr. Unter „Anmeldung und Kollegen“ legst du fest, ob Kollegen
Telefon und E-Mail sehen dürfen (unten, „Mein Bereich“). Es gibt
außerdem **„Entfernung Wohnung – Betrieb (km)“**: Damit zieht Rentalars
bei Fahrten der Person den Arbeitsweg ab (Abschnitt 13, „Spesen und
Fahrtkosten“); leer wird nichts abgezogen. Die Entfernung pflegt, wer das
Personal bearbeiten darf; sie steht in der Datenauskunft der Person und
verschwindet beim Anonymisieren.
Funktionen – und, wo nötig, eigene Sätze – trägst du nach „Person
speichern“ auf der Seite der Person ein.

**Jede Person hat eine Anmeldung.** Personal und Nutzer sind in Rentalars
eins: Jede Person ist zugleich ein Konto, mit dem sie sich anmeldet – um
ihre Einsätze zu sehen, zuzusagen, Zeiten zu erfassen und ihre
Verfügbarkeit zu pflegen. Und jedes Konto, das unter Einstellungen → Nutzer
entsteht, steht auch im Personal.

- Beim Speichern einer neuen Person legt Rentalars ihr Konto an: mit der
  Rolle **Crew** (freie Kräfte: **Freie Kraft**) und einem Benutzernamen
  aus dem Namen – `anna.becker`, gibt es den schon, `anna.becker2`. Ein
  Passwort hat das Konto noch nicht; anmelden kann sich die Person erst
  nach der Einladung oder mit einem Einmal-Passwort.
- **„Einladung jetzt per E-Mail senden“** (nur beim Anlegen) schickt gleich
  den Link, mit dem die Person ihr Passwort selbst wählt. Später geht das
  unter Einstellungen → Nutzer (Abschnitt 16).
- Die **E-Mail-Adresse ist freiwillig.** Ohne sie gibt es keine Einladung,
  sondern ein **Einmal-Passwort**, das du der Person persönlich oder am
  Telefon gibst (Abschnitt 16, „Nutzer“). Eine E-Mail-Adresse gehört zu
  genau einer Person.
- Vorname, Nachname, E-Mail-Adresse und „aktiv“ teilen sich Person und
  Konto: Was du an einer Stelle änderst, gilt an beiden.
- **Rollen und Rechte** bleiben unter **Einstellungen → Nutzer**. Wer mehr
  darf als Crew – Projektleitung, Lager, Büro –, bekommt dort seine Rolle.

Auf der Seite der Person steht unter **„Anmeldung“** der Benutzername und
der Stand: „noch kein Passwort – einladen oder Einmal-Passwort
festlegen“, „Passwort gesetzt, noch nicht angemeldet“ oder „zuletzt
angemeldet am …“. Wer die Einstellungen sehen darf, kommt über „Rollen und
Zugang“ direkt zum Konto.

**Wer was sehen darf**. Die Liste Personal → Personen hat –
wie Einstellungen → Nutzer – drei Spalten, die du unter „Spalten“
einblendest: **„Finanzen“** (Preise, Einkaufspreise, beides oder nein),
**„Personaldaten“** (Personen, Stundensätze, beides oder nein) und
**„Kundendaten“** (lesen, ändern oder nein). Rentalars rechnet sie aus
den Rollen des Kontos: „Finanzen“ aus den Sonderrechten „Preise und
Kalkulation sehen“ und „Einkaufs- und Kaufpreise sehen“, „Personaldaten“
aus dem Modul Personal – die Personen mit ihren Kontaktdaten – und dem
Sonderrecht „Stundensätze und Personalkosten sehen“, „Kundendaten“ aus dem
Modul Kunden. **„kein Zugang“** heißt: Das Konto kann sich nicht anmelden
– es hat noch kein Passwort, ist deaktiviert oder sein „gültig bis“ ist
vorbei (auch schon, bevor die nächtliche Aufgabe es deaktiviert hat;
Abschnitt 16, „Nutzer“). Die Spalten lassen sich
sortieren und gruppieren und gehen mit in die CSV-Datei; eine Legende
unter der Liste erklärt sie. So siehst du etwa vor einer Datenauskunft auf
einen Blick, wer an Stundensätze oder Kundendaten herankommt.

**Funktionen und Sätze.** Auf der Seite der Person unter **„Funktion
zuordnen“**: Funktion wählen, „Speichern“. Mehr braucht es nicht – Anna ist
damit als Tontechnikerin einplanbar. **Stundensatz**, **Stundensatz ab der
Grenze**, **Tagessatz** und **Gültig ab** sind freiwillig:

- Ohne eigenen Satz gilt der **Richtwert** der Funktion; die Liste zeigt
  ihn grau mit „(Richtwert)“.
- Der **Stundensatz ab der Grenze** kostet die Stunden eines Tages über der
  Grenze des Dienstleistungsprodukts (unten, „Was Personal kostet und
  einbringt“); leer gilt der Stundensatz („wie Stundensatz“). Die Seite
  der Person zeigt ihn in der Spalte „Ab der Grenze“.
- Ohne „Gültig ab“ gelten die Sätze **immer**, von Anfang an.
- Eine Person kann mehrere Funktionen haben, jede mit eigenen Sätzen –
  Anna als Tontechnikerin mit 35,00 € die Stunde und 280,00 € am Tag, als
  Stagehand ohne eigenen Satz.

Erst mit einer Funktion lässt sich eine Person einplanen. Funktionen
zuordnen darf, wer das Personal bearbeiten darf. Sätze sehen und ändern
darf nur, wer außerdem Stundensätze und Personalkosten sehen darf – der
Tagessatz gehört dazu; ohne dieses Recht hat „Funktion zuordnen“ nur das
Feld Funktion, und die Sätze trägt später jemand mit dem Recht ein.
„entfernen“ nimmt der Person eine Funktion wieder; bestehende
Personalpositionen und Zeiteinträge bleiben. Hat die Person in dieser
Funktion eigene Sätze, kann sie nur entfernen, wer die Sätze sehen darf –
sie gehen mit.

> **Ein Satz ändert sich.** Trage die neuen Sätze mit dem Tag ein, ab dem
> sie gelten. Die alten bleiben für die Zeit davor stehen („Alle Sätze mit
> Datum“). Eine Zeile gilt als Ganzes: Lässt du darin den Tagessatz leer,
> gilt ab diesem Tag wieder der Richtwert, nicht der alte Tagessatz.
> Positionen in Projekten und Zeiteinträge, die es schon gibt, behalten den
> Satz, mit dem sie entstanden sind – eine Erhöhung im Juli ändert kein
> Projekt vom Mai. Sätze ohne Datum gibt es je Funktion nur einmal; willst
> du sie ändern, trägst du sie dort neu ein.

Die Seite einer Person hat drei Reiter. **Person** zeigt außerdem ihre
Anmeldung, ihre **geplanten Einsätze**, ihre **Abwesenheiten**, ihre
**Qualifikationen** und ihre **erfassten Zeiten**; **Zeitstrahl** zeigt
ihre Wochen, **Verfügbarkeit** ihren Verfügbarkeitskalender – als Monat
oder Woche – und ihre verknüpften Kalender (beides unten).

**Viele Personen auf einmal** – etwa die Liste der freien Kräfte aus einer
Tabelle – übernimmst du mit „Import“ über der Personenliste (Abschnitt 16,
„Import und Export“). Auch sie bekommen ihre Anmeldung mit der Rolle Crew
bzw. Freie Kraft.

**Deaktivieren, exportieren, anonymisieren, löschen** (unten auf der Seite,
„Deaktivieren, Datenschutz“). Wer nicht mehr mitarbeitet, wird
deaktiviert („Person deaktivieren“): nicht mehr planbar, keine Anmeldung
mehr, alles Erfasste bleibt; „Person wieder aktivieren“ holt sie zurück.
Für eine Auskunft nach der Datenschutz-Grundverordnung liefert „Alle
gespeicherten Daten exportieren“ eine Datei mit allem, was über die Person
gespeichert ist. „Anonymisieren“ löscht Name, Kontaktdaten, Notizen,
Abwesenheiten, Verfügbarkeit, Kalender-Links und Qualifikationen samt
Nachweisen endgültig und schließt die Anmeldung; Einsätze und Zeiten
bleiben ohne Namen stehen, damit alte Projekte vollständig bleiben. Ein
Konto mit „hat alle Rechte“ lässt sich nicht anonymisieren – nimm ihm das
Recht vorher unter Einstellungen → Nutzer. **Löschen** („Person löschen“)
lässt sich nur, wer sich nie angemeldet hat, nie eingeplant war und nie
eine Zeit erfasst hat; mit der Person verschwindet ihr Konto. Wer sich
schon angemeldet hat, wird deaktiviert oder anonymisiert. Das eigene Konto
und das letzte Konto, das die Einstellungen verwalten darf, lassen sich
nicht deaktivieren. Für Kunden gibt es denselben Export auf der
Kundenseite. Er enthält die **KI-Zusammenfassungen** der Projekte des Kunden
(samt früheren Fassungen) nur, wenn du sie auf der Seite des Projekts selbst
lesen dürftest – dazu gehört das Recht, alle Nachrichten zu lesen, auch die
mit Schloss. Wie viele er ausgelassen hat, steht darin als
`ai_summaries_withheld`.

### Qualifikationen und Nachweise

Führerschein, Hubarbeitsbühne, Rigging, Ersthelfer, Unterweisungen: Was
jemand kann und nachweisen muss, steht auf der Seite der Person unter
**„Qualifikationen“**. „Hinzufügen“ fragt nach:

- **Qualifikation** – die Art, aus der Liste unter Einstellungen →
  Qualifikationsarten (Abschnitt 16);
- **Einzelheiten** – etwa die Führerscheinklassen: „B, BE, C1E“;
- **erworben am** und **gültig bis**. Bleibt „gültig bis“ leer und sagt die
  Art, wie lange sie gilt (ein Erste-Hilfe-Kurs zwei Jahre), rechnet
  Rentalars das Datum aus „erworben am“ aus. Sonst heißt leer: läuft nicht
  ab („unbefristet“);
- **Nachweis** – das PDF oder Bild der Bescheinigung. Eine neue Datei
  ersetzt die gespeicherte.

„Qualifikation speichern“. Die Liste zeigt das Ablaufdatum grün, gelb in
den letzten 60 Tagen davor und rot, wenn es vorbei ist. Läuft eine
Qualifikation bald ab oder ist sie abgelaufen, steht das auch oben auf der
Seite der Person („Rigging bis 30.11.2026“, „Ersthelfer abgelaufen“).

**Führerscheine.** Eine Qualifikationsart für einen
Führerschein nennt unter **„Führerscheinklassen“**, welche Klassen sie umfasst,
etwa „B, BE“ (Abschnitt 16, „Stammdaten“). Daran prüft die Logistik, ob der
Fahrer eines Fahrzeugs die nötige Klasse hat – nur als Hinweis, und nur
mit einer gültigen Qualifikation (Abschnitt 7, „Logistik“).

**60 Tage vor dem Ablauf** bekommt die Personaldisposition eine
Benachrichtigung („Nachweis läuft ab“) – und die Person selbst.
Rechtzeitig, um den Kurs zu buchen.

### Der Zeitstrahl einer Person

Der Reiter **„Zeitstrahl“** an jeder Person zeigt ihre Wochen auf einen
Blick: **Einsätze** als Balken (Projekt und Funktion) in den Farben des
Personalplans – orange fest, gelb Option, grau Projekt-Anfrage, blasser
mit gestricheltem Streifen noch angefragt, **rot ausgefüllt** ein Einsatz
im Konflikt (Abschnitt 15, „Personalplan“) –, darunter die
**Verfügbarkeit** – grün, gelb und rot, wie die Person sie eingetragen
hat, schraffiert die belegten Zeiten aus ihren verknüpften Kalendern, dazu
ihre Abwesenheiten – und, wann eine
**Qualifikation** abläuft. Die Legende steht darunter. Es gilt dieselbe
Verfügbarkeit wie im Personalplan: zu jedem Zeitpunkt eine. So siehst du,
wann jemand frei ist, bevor du anfragst. Zeitraum und Navigation wie
überall: „‹ früher“, „diese Woche“, „später ›“, „Von“ und eine bis zwölf
„Wochen“. Projekte, die du nicht öffnen darfst, erscheinen nur mit ihrer
Nummer.

### Abwesenheiten und Verfügbarkeit

**Abwesenheiten** – Urlaub, krank, nicht verfügbar, mit Von und Bis –
trägst du auf der Seite der Person ein („Abwesenheit eintragen“). Jede
Person kann eigene Abwesenheiten auch selbst eintragen und ihre
Verfügbarkeit im eigenen Kalender pflegen (unten, „Verfügbarkeitskalender“
und „Mein Bereich“).

**Personal → Verfügbarkeit** beantwortet die Frage „Wer ist frei?“:
Zeitraum wählen, auf Wunsch eine Funktion – „wer ist am Samstag frei und
kann Tontechnik?“. Mit gewählter Funktion werden nur die Personen gefragt,
die sie haben. Ohne Funktion – **„Alle Personen, unabhängig von der
Funktion“** – zeigt Rentalars jede aktive Person, auch ohne
Funktion, etwa das Büro. Jede
Person ist

- 🟢 **frei**,
- 🟡 **eingeplant** – mit dem Projekt, in dem sie steckt – oder
- 🔴 **abwesend** – eine Abwesenheit, oder sie hat sich für diese Zeit
  rot eingetragen („Nicht verfügbar (eigene Angabe)“), oder einer ihrer
  verknüpften Kalender ist belegt („Laut eigenem Kalender belegt“).

Die Freien stehen oben, und unter ihnen zuerst, wer sich grün als
verfügbar eingetragen hat („hat sich als verfügbar gemeldet“). Gelbe
Einträge – „eingeschränkt“, mit dem Hinweis der Person – stehen dabei; sie
ändern den Stand nicht, die Person steht unter den Freien aber hinten.

### Verfügbarkeitskalender

Jede Person führt einen eigenen Kalender, in dem sie zeigt, wann sie
arbeiten kann: **grün** verfügbar, **gelb** eingeschränkt (mit einem
Hinweis wie „nur bis 18 Uhr“) oder **rot** nicht verfügbar. Die Person
pflegt ihn selbst unter **„Mein Bereich“ → „Verfügbarkeit“**; die
Personaldisposition sieht ihn im Reiter **„Verfügbarkeit“** der Person und
kann ihn dort mit Schreibrecht für sie ändern – auch Serien.

So trägst du etwas ein:

1. Im Monatskalender auf den **ersten** und den **letzten Tag** tippen –
   oder die Tage in die Felder „Von“ und „Bis“ schreiben. Für einen
   einzelnen Tag bleibt „Bis“ leer.
2. Auf Wunsch **„Nur zu bestimmten Uhrzeiten“** anhaken und „von“ und
   „bis“ angeben – dann gilt die Farbe an jedem der Tage zu diesen
   Uhrzeiten, sonst ganztägig. Und auf Wunsch eine **Notiz**.
3. Die Farbe wählen: **„Verfügbar“**, **„Eingeschränkt“** oder **„Nicht
   verfügbar“**. **„Eintrag entfernen“** löscht, was für diese Tage
   eingetragen war.

Der Kalender malt wie ein Pinsel: Eine neue Farbe ersetzt, was für diese
Zeit eingetragen war. Dieselbe Farbe mit derselben Notiz direkt daneben
erscheint als ein Zeitraum – erst Montag, dann Dienstag grün ergibt
„Montag bis Dienstag“. Unter dem Kalender stehen die Zeiträume des Monats
mit ihrer Herkunft – „eingetragen“, „Serie“ oder „belegt im verknüpften
Kalender“ –, deine eigenen mit „entfernen“. Ein Punkt an einem Tag heißt:
eingeplant. „‹“ und „›“ blättern die Monate.

**Monat oder Woche.** Über dem Kalender wählst du **„Monat“** oder
**„Woche“**; Rentalars merkt sich die Wahl. Die Woche zeigt sieben Spalten
mit Stunden wie der Wochenkalender der Planung (Abschnitt 15, „Kalender“):

- die Verfügbarkeit als Farbe über ihren Stunden – grün, gelb, rot,
  schraffiert die belegten Zeiten aus den verknüpften Kalendern;
- die **Einsätze** als Blöcke rechts daneben; liegt ein Einsatz in einer
  roten Zeit, ist er rot ausgefüllt („Einsatz trotz „nicht
  verfügbar““);
- oben die Tage in der Farbe, die sie im Monat haben. Zum Eintragen tippst
  du auf den Kopf des ersten und des letzten Tages, dann auf die Farbe –
  oder gibst wie gewohnt „Von“, „Bis“ und Uhrzeiten an.

**Zeitbereich in der Woche markieren**. In der Woche
markierst du einen Zeitbereich direkt in den Spalten: mit der Maus vom
Beginn bis zum Ende ziehen, in Schritten von 15 Minuten – auch über
mehrere Tage; dann gelten an jedem dieser Tage dieselben Stunden. Auf dem
Telefon tippst du erst den Beginn und dann das Ende an (in Schritten von
30 Minuten). Rentalars trägt Tage und Uhrzeiten ins Formular darunter ein,
und eine Zeile über den Farbknöpfen sagt in Worten, was markiert ist. Dann
wählst du „Verfügbar“, „Eingeschränkt“ oder „Nicht verfügbar“ und kannst
eine Notiz dazuschreiben. Mit der Tastatur füllst du dieselben Felder des
Formulars aus. Für eine Nacht über Mitternacht trägst du die Zeiten im
Formular ein (Ende vor Beginn), statt zu ziehen.

„‹“ und „›“ blättern die Wochen, „diese Woche“ springt zurück. Die Woche
öffnet bei 6 Uhr, die heutige Spalte ist im Blick. Auf dem Telefon
schiebst du die Woche zur Seite und nach oben und unten. Unter der Woche
stehen ihre Zeiträume wie unter dem Monat („Einträge in dieser Woche“).
Dieselbe Wahl hat die Personaldisposition im Reiter „Verfügbarkeit“ einer
Person; Projekte, die sie nicht öffnen darf, stehen dort nur als „Funktion
· eingeplant“.

**Wiederholen wie ein Serientermin.** Unter **„Wiederholen …“** wird aus
den gewählten Tagen der erste Termin einer Serie:

- **täglich**, **wöchentlich** oder **monatlich**, und dazu „alle“ 1, 2, 3 …
  Tage, Wochen oder Monate – „alle 2 Wochen“ heißt jede zweite Woche;
- wöchentlich **an diesen Wochentagen**, etwa Di und Do; ohne Auswahl am
  Wochentag des ersten Tages;
- monatlich am selben Tag des Monats; Monate ohne diesen Tag (der 31.)
  fallen aus;
- endet **am** einem Datum **oder nach** einer Anzahl von Terminen,
  höchstens ein Jahr nach dem ersten Tag.

Dann die Farbe wählen. Jeder Termin malt wie jeder andere Eintrag: Er
ersetzt, was für seine Zeit eingetragen war, und was du später einträgst,
ersetzt ihn. Unter dem Kalender stehen die **Serien** mit ihrer Regel –
„wöchentlich am Di, Do, 18:00–23:00, ab 03.11.2026, bis 31.12.2026“:

- **„Ändern“** öffnet die Serie: Farbe, Notiz, Uhrzeiten, Wiederholung und
  Ende ändern und angeben, **ab** welchem Tag das gilt (sonst ab heute).
  Was davor liegt, bleibt; von da an werden die Termine neu gesetzt.
- **„Ab diesem Tag entfernen“** beendet die Serie am Tag davor;
  **„Ganz entfernen“** nimmt alle ihre Termine heraus, auch vergangene.
- Ein einzelner Termin lässt sich wie jeder Eintrag überschreiben oder
  entfernen; er gehört dann nicht mehr zur Serie.

**Zu jedem Zeitpunkt eine Verfügbarkeit.** Eigene Einträge überschneiden
sich nie. Belegte Termine aus den verknüpften Kalendern (unten) sind eine
eigene Ebene, die Rentalars bei jedem Lesen neu übernimmt – deshalb
überschreiben sie deine Einträge nicht, und deine Einträge nicht sie. Wo
sich beide treffen, gilt die **neuere Angabe**: dein Eintrag mit dem
Zeitpunkt, an dem du ihn gemacht hast, der Termin mit seinem
Änderungsdatum im Kalender. Trägst du nach einem Arzttermin „verfügbar“
ein, gilt also grün; verschiebt sich danach der Termin in deinem
Kalender, gilt wieder er. Nennt dein Kalender kein Änderungsdatum, gilt
die strengere Angabe – rot. Termine, die sich überschneiden oder
aneinanderstoßen, erscheinen als ein Block.

**Was die Disposition davon hat.** Die Farben stehen bei „Wer ist frei?“
(oben) und im Personalplan (Abschnitt 15), jeweils so, wie sie nach diesen
Regeln gelten. Wer jemanden in einem roten Zeitraum einplant, bekommt an
der Personalposition eine Warnung („Laut eigener Angabe nicht verfügbar:
…“), bei Gelb einen leiseren Hinweis („Nur eingeschränkt verfügbar: …“).
Verhindert wird nichts.

### Kalender verknüpfen

Wer seine Termine ohnehin in Google, Outlook, iCloud oder Nextcloud führt,
muss sie nicht abschreiben: Unter „Mein Bereich“ → „Verfügbarkeit“ →
„Kalender“ → **„Belegte Zeiten aus deinen Kalendern“** trägst du den
privaten **ICS-Link** eines Kalenders ein, auf Wunsch mit einem **Namen**
wie „Band“, und tippst auf **„Kalender verknüpfen“**. Führst du mehrere
Kalender – den privaten, den der Band, den des anderen Arbeitgebers –,
verknüpfst du jeden („Weiteren Kalender verknüpfen“); bis zu zehn. „Wo
finde ich den Link?“ erklärt, wo er bei Google, Outlook/Microsoft 365,
iCloud und Nextcloud steht; auch ein `webcal://`-Link geht.

- Rentalars liest **jeden Kalender alle 30 Minuten** – den vergangenen
  Monat und das kommende halbe Jahr –, „Jetzt lesen“ alle sofort.
- Jeder **belegte** Termin gilt als **„nicht verfügbar“**. Die Termine
  aller Kalender sind **eine** Ebene „belegt im verknüpften Kalender“ und
  erscheinen im Verfügbarkeitskalender als rote Zeit: Überlappende und
  aneinandergrenzende Termine erscheinen als ein Block, auch aus
  verschiedenen Kalendern. Wo du für dieselbe Zeit selbst etwas
  eingetragen hast, gilt das Neuere (oben). Als frei markierte und
  abgesagte Termine zählen nicht, sich wiederholende werden aufgelöst.
- **Titel und Inhalte der Termine übernimmt Rentalars nie.** Die
  Disposition erfährt, *dass* du belegt bist, nicht *warum*. Auch die Links
  selbst sieht sie nicht, nur den Namen, den du vergeben hast, und den
  Server.
- Jeder Kalender zeigt seinen Stand: „verknüpft, zuletzt gelesen …“ oder
  „Problem“ mit dem Grund. Klemmt einer länger, bekommst du einmal
  Bescheid, mit seinem Namen. Seine zuletzt gelesenen Zeiten bleiben so
  lange stehen; die anderen Kalender liest Rentalars weiter wie gewohnt.

„entfernen“ an einem Kalender hebt seine Verknüpfung auf; nur die daraus
gelesenen Zeiten verschwinden. Die Personaldisposition kann im Reiter
„Verfügbarkeit“ der Person Kalender für sie verknüpfen, jetzt lesen oder
entfernen – die Links sieht sie auch dabei nicht.

**Kalender im eigenen Netz.** Rentalars verbindet sich zu
verknüpften Kalendern und zu deinem CalDAV-Kalender nur, wenn die Adresse
nicht ins interne Netz führt – also nicht zu diesem Rechner, nicht in
private Netze (etwa 192.168.x.x oder 10.x.x.x) und nicht zum Server
selbst. Ein NAS oder eine Nextcloud im eigenen Netz geht trotzdem, wenn
der Betreiber sie in der Konfigurationsdatei freigibt. Sonst siehst du
„Die Adresse führt in ein internes Netz …“ – bei einer IP-Adresse oder
`localhost` schon beim Eintragen, bei einem Namen beim Lesen oder
Schreiben (Abschnitt 16, „Selbsttest“).

### Die eigenen Einsätze im eigenen Kalender

Umgekehrt holst du dir deine Einsätze aufs Telefon: unter „Meine
Personaldaten“ → „Kalender“ → **„Deine Einsätze in deinem Kalender“**.
Jeder Eintrag nennt Funktion, Projekt, Ort, Treffpunkt, Zeiten und die
Notiz für die Crew – keinen Kunden, keine Preise; nur, was du im Überblick
des Projekts ohnehin siehst. Drei Wege:

- **„Als .ics-Datei herunterladen“** – ein Stand zum Importieren.
- **Abonnieren:** „Abo-Link erzeugen“ liefert einen geheimen Link
  („Kopieren“), den du in deinem Kalenderprogramm als abonnierten Kalender
  einträgst („Per URL“, „Kalender abonnieren“). Er hält sich dann selbst
  aktuell. Der Link funktioniert ohne Anmeldung – behalte ihn für dich.
  „Neuer Link“ macht den alten sofort ungültig, „Link abschalten“ schaltet
  ihn ab. Dein Kalenderprogramm muss Rentalars dafür über das Internet
  erreichen; Google Kalender liest so einen Link auch.
- **„In einen CalDAV-Kalender schreiben“** – für den Fall, dass Rentalars
  nur im Firmennetz läuft: Rentalars schreibt deine Einsätze dann selbst in
  einen Kalender im Internet, etwa bei Nextcloud, iCloud, mailbox.org oder
  Posteo. Adresse des Kalenders oder nur des Servers, Benutzername und
  Passwort (oft ein App-Passwort), „Speichern und schreiben“. Gibst du nur
  den Server an, legt Rentalars dort den Kalender „Rentalars“ an. Nach
  jeder Änderung an einem Einsatz schreibt Rentalars binnen Minuten nach,
  und abgesagte Einsätze verschwinden; „Jetzt abgleichen“ sofort,
  „Verbindung trennen“ hört auf zu schreiben. Nimm dafür am besten einen
  eigenen Kalender: Änderungen, die du dort an den Einträgen machst,
  überschreibt Rentalars. Google Kalender lässt sich auf diesem Weg nicht
  beschreiben.

Was du unter „Welche Adresse gebe ich an?“ für Nextcloud, iCloud,
mailbox.org und Posteo eintragen musst, steht direkt auf der Seite. Abo-Link
und CalDAV bleiben deine Sache – die Personaldisposition sieht sie nicht.
Der Kalender nennt sein Aktualisierungsintervall (30 Minuten)
in der Form, die Kalenderprogramme lesen. Die Belegung von Produkten,
Modellen und Exemplaren abonnierst du ebenso, mit ihrem Kalender-Link
(Abschnitt 4, „Kalender-Link“).

Die Anmeldedaten deines CalDAV-Kalenders schickt Rentalars nur
an genau den Server, für den du sie eingetragen hast – auch wenn er
weiterleitet. Verweist der Server auf einen anderen Server, trag die
Adresse des Kalenders auf jenem Server ein. Einzige Ausnahme ist iCloud
(`caldav.icloud.com` gibt an `pNN-caldav.icloud.com` weiter). Ein
Kalender im eigenen Netz braucht die Freigabe des Betreibers (oben,
„Kalender verknüpfen“).

### Personal im Projekt einplanen

Auf der Planungsseite eines Projekts steht unter den Teilgruppen der Block
**„Personal“**. Personal gehört zum ganzen Projekt, nicht zu einer
Teilgruppe, und hat eine eigene Zwischensumme.

**Einplanen:** unter dem Block Funktion wählen, Person wählen, Von und Bis
eintragen, „Einplanen“. Die Personalposition zeigt die Artikelnummer des
Dienstleistungsprodukts ihrer Funktion – ein Klick öffnet es – und
übernimmt von ihm Preis, Steuersatz und die Grenze in Stunden pro Tag
(unten, „Was Personal kostet und einbringt“). Neue Personalpositionen nach
Stunden werden **nach Aufwand** abgerechnet. Als Materialposition lässt
sich eine Dienstleistung nicht planen (Abschnitt 7, „Eine Position
hinzufügen“).

- **Noch niemand bestimmt?** Lass „Person“ auf „– noch offen –“ und trage
  bei „Plätze“ ein, wie viele gebraucht werden: „2 × Stagehand, Samstag
  8–14 Uhr“ sind zwei offene Plätze. Oben am Block steht, wie viele Plätze
  offen sind. Besetzt werden sie später über den Stift.
- **Fest eingeplant (ohne Anfrage)**: Hakst du das an, ist
  die Person gleich fest eingeplant, ohne Einsatzanfrage – sie bekommt
  stattdessen eine Nachricht (unten, „Fest einplanen“). Das geht nur mit
  einer Person, nicht mit offenen Plätzen.
- **Wer angeboten wird:** In der Auswahl „Person“ stehen nur Personen mit
  einer Funktion, jede mit ihren Funktionen in Klammern („Becker, Anna
  (Stagehand, Tontechnik)“). Hast du eine Funktion gewählt, bleiben nur
  die, die diese Funktion haben. Wer das Sonderrecht „Personen außerhalb
  ihrer Funktionen einplanen“ hat, sieht die übrigen dahinter,
  gekennzeichnet, und kann sie trotzdem wählen – dann steht ein Hinweis an
  der Zeile. Fehlt jemand ganz, hat er noch keine Funktion (oben,
  „Funktionen“).
- **Phase:** Hat das Projekt Phasen, wählst du beim Einplanen die Phase –
  Von und Bis übernehmen ihren Zeitraum. An der Zeile steht dann „Phase:
  Aufbau“ unter dem Zeitraum, und in der Zeitplanung steht die Person unter
  ihrer Phase (Abschnitt 7, „Zeitplanung“). Ohne Phase gehört die Position
  zu keiner; das geht genauso.
- **Neue Phase …:** Fehlt die Phase noch, wählst du am Ende der Liste
  **„Neue Phase …“** – im Formular unter dem Personal und im Dialog der
  Personalposition. Ein Dialog fragt nach Phase, Bezeichnung, Von, Bis,
  Veranstaltungsort und Ort, vorbelegt mit dem Zeitraum, den du schon
  eingetragen hast, sonst im Anschluss an die letzte Phase – über mehrere Tage zunächst eine Stunde am ersten Tag (Abschnitt 7,
  „Zeitplanung“). **„Phase speichern“** legt
  sie in der Zeitplanung an und wählt sie gleich aus: Funktion, Person,
  Plätze und Notiz bleiben, Von und Bis übernehmen den Zeitraum der Phase.
  „Abbrechen“ oder Esc schließt den Dialog, und die vorige Phase ist
  wieder gewählt. Mit der Tastatur: mit den Pfeiltasten auf „Neue Phase …“,
  dann Enter oder Leertaste. Den Eintrag gibt es, wenn du das Projekt
  bearbeiten darfst und es nicht abgeschlossen ist – wer nur Personal
  disponiert, legt Phasen nicht an – und nur mit eingeschaltetem
  JavaScript. Hat das Projekt noch gar keine Phase, steht die Auswahl
  trotzdem da – mit „– keine Phase –“ und „Neue Phase …“.
- **Geplante Stunden** schlägt Rentalars aus dem Zeitraum vor: immer die
  ganze Dauer, Ende minus Beginn. Samstag 08:00 bis 14:00 sind 6 Stunden,
  Montag 08:00 bis Dienstag 20:00 sind 36 Stunden – der Zeitraum gilt als
  durchgearbeitet. Arbeitet niemand durch, trägst du über den Stift die
  wirklichen Stunden ein – etwa 24 für zwei Tage zu je 12 Stunden. Über
  die Umstellung auf Sommerzeit ist eine Nacht eine Stunde kürzer, und so
  zählt Rentalars sie auch.

**Der Stift** öffnet den Dialog einer Personalposition:

- Funktion, Person, **Phase**, **Von / Bis**, geplante Stunden – die
  Auswahl „Person“ folgt der gewählten Funktion wie oben; wählst du eine
  andere Phase, übernehmen Von und Bis deren Zeitraum;
- **Treffpunkt** und **Notiz** – beides sieht die Person im Reiter
  „Überblick“ des Projekts;
- mit Preisrecht: **Abrechnung**, **Preis**, bei „je Tag“ die **Tage**,
  **Grenze in Stunden pro Tag** und **Preis je Stunde ab der Grenze**,
  **Rabatt in Prozent** (siehe unten) und **„Zuschläge für Nacht, Sonn-
  und Feiertage im Preis“**; erlaubt die Funktion weniger Rabatt, steht das
  darunter („Die Funktion erlaubt höchstens 10 %.“);
- mit dem Recht für Personalkosten: **Stundensatz (intern)**,
  **Stundensatz ab der Grenze (intern)** und **Tagessatz (intern)** – beim
  Zuweisen von der Person übernommen, hier nur für diesen Einsatz zu
  ändern; leer gilt der Richtwert der Funktion –, **Pauschale für die
  Person** und **„Zuschläge für Nacht, Sonn- und Feiertage in den
  Kosten“** (unten, „Zuschläge für Nacht, Sonn- und Feiertage“);
- sobald im Projekt ein KFZ gebucht ist: **„Fahrzeug“** – mit
  welchem Fahrzeug der Logistik die Person fährt – und **„Fährt das
  Fahrzeug“** (Abschnitt 7, „Logistik“);
- **„Fest eingeplant (ohne Anfrage)“** – nimmst du den Haken
  heraus, ist die Position wieder „nicht angefragt“ und lässt sich
  anfragen. Wer schon zugesagt hat, gilt ohnehin als fest eingeplant.

Denselben Haken hat der Dialog „Personal für diese Phase“ in der
Zeitplanung (Abschnitt 7).

**Warnungen.** Rentalars sagt Bescheid, verhindert aber nichts:

- die Person ist zur selben Zeit **woanders eingeplant** (in diesem oder
  einem anderen Projekt),
- der Zeitraum fällt in eine **Abwesenheit**,
- die Person hat sich für diese Zeit **nicht verfügbar** eingetragen, oder
  einer ihrer verknüpften Kalender ist belegt; bei „eingeschränkt“ gibt es
  einen leiseren Hinweis (oben, „Verfügbarkeitskalender“),
- die Funktion gehört **nicht zu den Funktionen** der Person.

#### Mehrere Personalpositionen auf einmal

Für alle, die Personal planen dürfen, hat auch jede
Personalposition vorne ein Kästchen, wie die Materialpositionen (Abschnitt
7, „Mehrere Positionen auf einmal“). Sobald eine gewählt ist, erscheint
unten die Leiste „Gewählte Personalpositionen“ mit:

- **„Werte setzen …“** – ein Dialog mit Treffpunkt (oder „Treffpunkt
  entfernen“), Notiz (oder „Notiz entfernen“), Phase (oder „ohne Phase“),
  Von und Bis, geplanten Stunden, sobald im Projekt ein KFZ gebucht ist dem
  Fahrzeug und mit Preisrecht dem Rabatt in Prozent. Gesetzt wird nur, was
  du ausfüllst; was leer oder auf „– unverändert –“ bleibt, bleibt an jeder
  Position, wie es ist. Wählst du eine Phase ohne Von und Bis, übernehmen
  die Positionen deren Zeitraum. Leere geplante Stunden folgen dem neuen
  Zeitraum, wo sie dem alten folgten; eingetippte Stunden bleiben.
  **„Für die gewählten Positionen setzen“** speichert.
- **„Fest einplanen“** – alle gewählten Personen ohne Anfrage (unten,
  „Fest einplanen“).
- **„Anfragen“** – eine Einsatzanfrage je Person.
- **„Löschen“** – nach einer Rückfrage.
- **„Auswahl aufheben“**.

Jede Position folgt den Regeln, die auch für sie allein gelten: Eine
angefragte oder zugesagte Person wird für neue Zeiten neu angefragt, eine
fest eingeplante nur benachrichtigt. Positionen, bei denen etwas nicht
geht – ein offener Platz lässt sich nicht anfragen oder fest einplanen,
eine fest eingeplante Person nicht anfragen –, bleiben unverändert, und
Rentalars nennt sie mit dem Grund. Jede betroffene Person bekommt **eine**
Nachricht, auch wenn mehrere ihrer Positionen geändert wurden. Die Funktion
setzt die Leiste bewusst nicht – sie ändert Preis und Sätze. Ohne
JavaScript geht alles genauso, nur über eine eigene Seite.

#### Anfragen: Zusage oder Absage

Wer eingeplant ist, ist noch nicht gefragt. Unter dem Namen einer
eingeplanten Person steht **„anfragen“**. Die Person bekommt eine
**Einsatzanfrage** – in der Anwendung und, wenn sie eine E-Mail-Adresse
hat, per E-Mail – und sagt **zu** oder **ab**, auf Wunsch mit einer Notiz
(„erst ab 10 Uhr“): auf ihrer Startseite oder im Reiter „Überblick“ des
Projekts – oder,
wenn eure Installation es so eingestellt hat, **per Antwort-Mail**, ganz
ohne Anmeldung (unten, „Einsatzanfragen per Mail beantworten“). Die
Projektleitung und wer gefragt hat, erfahren die Antwort.
Eine Antwort-Mail legt Rentalars im Postfach wie jede zugeordnete Mail ab
– auch dann in den Ordner „Rentalars“, wenn das Postfach
zugeordnete Mails nur als gelesen markiert (Abschnitt 14, „Zugeordnete
Mails im Postfach“): Im Posteingang bleiben die Mails, die jemand lesen
muss.

Fragst du lieber am Telefon – etwa, weil die Person sich noch nie
angemeldet hat –, drückst du trotzdem „anfragen“. Die Zeile steht dann auf
„angefragt“, und du trägst die Antwort selbst ein („eintragen: zugesagt“
oder „abgesagt“).

**Eine Zusage trägt „verfügbar“ ein**. Sagt eine Person für
eine Zeit zu, in der ihr eigener Verfügbarkeitskalender **„nicht
verfügbar“** zeigt – im Browser, per Antwort-Mail, in der App oder über
die Schnittstelle, oder trägst du ihre Zusage ein –, trägt Rentalars für
genau die Zeit der Position **„verfügbar“** ein, mit der Notiz „Zugesagt:
2026-0042 Stadtfest – Tontechnik“. Einträge, die in diese Zeit reichen,
werden gekürzt oder geteilt, auch Termine einer Serie. Die Bestätigung
sagt es („Für … ist jetzt „verfügbar“ eingetragen.“). Zeigt der Kalender
dort nichts „nicht verfügbar“, ändert sich nichts. Verknüpfte Kalender
bleiben, wie sie sind; der neue Eintrag ist ein eigener Eintrag der
Person und gilt als neuere Angabe vor einer belegten Zeit daraus
(oben, „Verfügbarkeitskalender“). Fest einplanen (unten) trägt nichts
ein – das entscheidet das Büro, nicht die Person –, und wird der Einsatz
später entfernt, bleibt der Eintrag: Es ist der Kalender der Person.

An der Zeile steht der Stand: **angefragt** (gelb), **zugesagt** (grün),
**abgesagt** (rot), auch **fest eingeplant** (grün). Eine
Absage verhindert nichts – die Position bleibt,
bis du eine andere Person einplanst. Wechselt die Person, beginnt die
Anfrage von vorn. Im Personalplan sind angefragte Einsätze blasser und
gestrichelt (Abschnitt 15).

**Fest einplanen**. Manchmal ist längst abgesprochen, wer
kommt – dann planst du die Person **ohne Anfrage** ein: mit dem Haken
„Fest eingeplant (ohne Anfrage)“ beim Einplanen oder im Dialog, mit
**„fest einplanen“** an der Zeile (bei einer Position, die nicht
angefragt, angefragt oder abgesagt ist) oder für mehrere Positionen in der
Leiste (oben). Das zählt wie eine Zusage: Der Einsatz steht unter Meine
Einsätze, in den Kalendern und im Überblick der Person, und im Personalplan
als geplant. Die Person bekommt keine Anfrage, sondern die Nachricht
„Fest eingeplant: …“ mit Treffpunkt und Notiz. Ändern sich später die
Zeiten, fragt Rentalars sie **nicht** neu an – sie bleibt fest eingeplant
und erfährt die neuen Zeiten. Im Dialog nimmst du das zurück; die
Position ist dann „nicht angefragt“.

**Nachrichten über den Einsatz**. Die eingeplante Person
erfährt von selbst – in Rentalars, per E-Mail und in der App, als
Benachrichtigung „Änderung meines Einsatzes“ (Abschnitt 15,
„Benachrichtigungen“):

- dass sie **fest eingeplant** wurde;
- dass sich **Zeiten, Treffpunkt, Notiz, Phase, Funktion oder Fahrzeug**
  ihres Einsatzes geändert haben – jeweils mit dem Wert vorher;
- dass sie **ausgeplant** wurde – die Position gelöscht oder mit jemand
  anderem besetzt.

Je Person und Aktion kommt **eine** Nachricht: Änderst du mehrere
Positionen auf einmal oder verschiebst eine Phase oder den Mietzeitraum
samt Personal, nennt sie alle betroffenen Einsätze der Person zusammen.
Wird die Person für neue Zeiten neu angefragt (unten), nennt die Anfrage
die übrigen Änderungen mit. Keine Nachricht gibt es, wenn du deinen eigenen
Einsatz änderst, für abgesagte Positionen, vergangene Einsätze, stornierte
Projekte und Personen ohne aktives Konto.

**Antworten erscheinen sofort.** Sagt jemand zu oder ab – im Browser oder
per Antwort-Mail –, zeigt die offene Planung das von selbst, spätestens
etwa 20 Sekunden später; bei einer Antwort-Mail, sobald Rentalars das
Postfach abgerufen hat. Das gilt auch, wenn du in der Zwischenzeit selbst
etwas gespeichert hast. Tippst du gerade, erscheint unten „Auf dieser
Seite gibt es etwas Neues.“ (Abschnitt 2).

**„erneut anfragen“** gibt es erst, wenn sich **Beginn oder Ende** der
Position seit der Anfrage geändert haben. Die Zeile sagt dann zum Beispiel
„Zeiten geändert seit der Zusage – angefragt war: Mi 10.03. 08:00 – Mi
10.03. 18:00“ (oder „… seit der Absage“, „… seit der Anfrage“). Für
dieselben Zeiten fragt Rentalars nicht noch einmal an; eine zugesagte oder
abgesagte Position mit unveränderten Zeiten zeigt nur ihren Stand.

**Neue Zeiten, neue Anfrage.** Änderst du Beginn oder Ende einer
**angefragten oder zugesagten** Personalposition – im Dialog, mit
„Personal dieser Phase mitverschieben“ (Abschnitt 7) oder über die
Schnittstelle –, fragt Rentalars die Person von selbst neu an; nach dem
Dialog und nach dem Speichern der Phase sagt es dir das („Anna Becker
wurde für die neuen Zeiten neu angefragt.“). Die Anfrage
heißt „Einsatzanfrage mit neuen Zeiten: …“ und nennt „Neue Zeiten: …
(vorher: …)“; die Zeile steht bis zur Antwort wieder auf „angefragt“. Eine
Antwort auf die ältere Anfrage-Mail übernimmt Rentalars nicht mehr. Nicht
von selbst angefragt werden:

- **abgesagte** Positionen – dort erscheint „erneut anfragen“, und du
  entscheidest;
- **fest eingeplante** Positionen – die Person erfährt die
  neuen Zeiten (oben, „Nachrichten über den Einsatz“);
- Positionen eines stornierten Projekts und deaktivierte Personen;
- Änderungen an Stunden, Treffpunkt, Notiz oder Funktion – sie lösen
  keine Anfrage aus; die Person bekommt für Treffpunkt, Notiz,
  Funktion, Phase und Fahrzeug eine Nachricht.

Abschalten lässt sich das unter Einstellungen → Firmendaten und
Grundeinstellungen → **„Bei geänderten Zeiten neu anfragen“**
(voreingestellt an; Abschnitt 16). Dann bleibt der Stand nach einer
Zeitänderung, wie er war, und die Zeile bietet „erneut anfragen“ an.

#### Einsatzanfragen per Mail beantworten

**Für dich als Crew.** Du bekommst die Anfrage als Mail „Einsatzanfrage:
…“ mit Projekt, Funktion, Zeit, Ort und Treffpunkt – davor steht, wenn
die Firmendaten einen Namen haben, eine Zeile „Firma:“ mit dem Namen eurer Firma,
damit du weißt, wer fragt – und den Knöpfen
**„Zusagen“** und **„Absagen“**. Tipp auf einen davon: Dein Mailprogramm
öffnet eine fertige Mail. Hinter **„Anmerkung:“** kannst du etwas für die
Planung schreiben, etwa „komme erst um 9“. Lass den Betreff, wie er ist –
er enthält den Code in eckigen Klammern, an dem Rentalars deine Antwort
erkennt – und schick die Mail ab. Sobald Rentalars das Postfach abruft,
meist nach wenigen Minuten, bekommst du die Mail **„Deine Zusage ist
angekommen“** (oder „Deine Absage …“). Ist die Anfrage schon beantwortet,
der Einsatz vorbei, die Anfrage zurückgenommen, das Projekt abgesagt oder
abgeschlossen, oder gibt es eine neuere Anfrage, bekommst du stattdessen
eine Mail, dass nichts übernommen wurde, und warum. Eine normale Antwort
mit „Ja“ oder „Nein“ wertet Rentalars nicht aus – sie landet bei dem, der
das Postfach liest. Leite die Anfrage nicht weiter: Wer den Code hat, kann
für dich antworten. Steht in der Mail auch „Oder in Rentalars antworten“,
geht beides. Per Mail zählt nur die erste Antwort; willst du sie danach
ändern, sag der Planung Bescheid. Ändern sich die Zeiten eines Einsatzes,
für den du angefragt bist oder zugesagt hast, bekommst du eine neue Mail
„Einsatzanfrage mit neuen Zeiten: …“ mit den neuen und den bisherigen
Zeiten („die Zeiten deines Einsatzes haben sich geändert. Übernimmst du
ihn zu den neuen Zeiten?“). Antworte mit den Knöpfen dieser neuesten Mail
– die der älteren gelten dann nicht mehr.

Die Mail mit den Knöpfen bekommt jede aktive Person mit E-Mail-Adresse,
auch wer sich nie anmeldet – sofern Antworten per Mail eingeschaltet sind
(unten). Wer unter Mein Konto → Benachrichtigungen die Mails zu
Einsatzanfragen abgeschaltet hat, bekommt keine; die Anfrage steht dann nur
in Rentalars.

**Für die Planung** sieht eine Antwort per Mail aus wie eine aus dem
Browser: Die Zeile steht auf „zugesagt“ oder „abgesagt“, mit der Notiz, und
die Projektleitung und wer gefragt hat, bekommen Bescheid. Im Verlauf des
Projekts steht „Antwort von … kam per Antwort-Mail“.

**Nur von der Adresse, an die die Anfrage ging.** Der Code im
Betreff allein genügt nicht: Eine Antwort zählt nur, wenn die Mail von
genau der Adresse kommt, an die die Anfrage geschickt wurde (Groß- und
Kleinschreibung spielen keine Rolle). Leitet jemand die Anfrage weiter, kann
der neue Empfänger also nicht im Namen des ursprünglichen zusagen: Seine
Antwort ändert nichts, sie steht im Mail-Protokoll mit dem Grund „nicht von
der Adresse, an die die Anfrage ging“, und die Person bekommt an ihre eigene
Adresse eine Mail, dass eine Antwort von einer anderen Adresse kam und
nichts geändert wurde. Wer von einer anderen Adresse antworten möchte,
antwortet im Browser oder bittet die Planung, die Anfrage noch einmal zu
stellen. Die Adresse merkt sich Rentalars mit der Anfrage; ändert sich die
Adresse der Person danach, gilt für diese Anfrage noch die alte.

Eine Absenderadresse lässt sich fälschen. Schreibt der Mailserver, der die
Antwort entgegennimmt, in den Kopf der Mail ein Prüfergebnis
(`Authentication-Results`) und meldet er darin, dass die DMARC-Prüfung
fehlgeschlagen ist, übernimmt Rentalars die Antwort ebenfalls nicht („die
Prüfung des Absenders schlug fehl“). Das gilt auch, wenn die Absender-Domain
DMARC nur zur Beobachtung eingerichtet hat (`p=none`): wer „im Namen“ einer
anderen Adresse sendet, antwortet dann besser in Rentalars. Eine Mail mit
zwei `Von`-Zeilen wird ebenfalls nicht übernommen. Fehlt ein Prüfergebnis des
Mailservers, kann Rentalars den Absender nicht weiter prüfen; viele
Mailanbieter tragen es ein, wenn die Absender-Domain DMARC eingerichtet hat.
Wer die Antwort verweigert bekommt, erhält die Warnmail höchstens einmal pro
Stunde und Anfrage.

**Für Administratoren: einstellen.** Unter Einstellungen → Firmendaten und
Grundeinstellungen steht die Einstellung **„Antwort auf Einsatzanfragen“**
(ändern darf sie, wer die Einstellungen ändern darf):

- **„über den Link im Browser“** – die Mail
  enthält nur einen Link zu Rentalars.
- **„per Antwort-Mail“** – die Mail enthält nur die Knöpfe „Zusagen“ und
  „Absagen“, keinen Link.
- **„beides“** (voreingestellt) – Knöpfe und Link.

Antworten per Mail brauchen ein **aktives Postfach der Korrespondenz mit
Adresse**, das Rentalars abruft: das Postfach für die Systemmails, wenn es
auch Korrespondenz ist, sonst den Postausgang der Korrespondenz (Abschnitt
14, „Postfächer einrichten“). Die Seite sagt unter der Einstellung, wohin
die Antworten gehen – oder dass es noch kein solches Postfach gibt; dann
enthalten die Anfragen nur den Link, auch bei „beides“ und „per
Antwort-Mail“. Rentalars erkennt Antworten in **jedem** Postfach, das es
abruft, gleich ob es Mails ohne Projektkennung übernimmt, und behandelt sie
danach wie zugeordnete Mails: verschieben, löschen oder liegen lassen. Im
Mail-Protokoll stehen sie mit dem Ergebnis „Antwort auf Einsatzanfrage“ und
„Zusage“, „Absage“ oder dem Grund, warum nichts übernommen wurde (Abschnitt
14, „Mail-Protokoll“). Die Adresse im Absender einer Mail lässt sich fälschen.
Wer den Namen seines Mailservers in den Prüfergebnissen unter Einstellungen →
Postfächer einträgt (Betriebsanleitung), lässt nur Antworten gelten, die dieser
Server bestätigt hat; ohne den Eintrag ist eine Antwortmail kein Beweis, wer sie
schrieb.

**Geht das ohne Erreichbarkeit aus dem Internet?** Ja. Der Link in der
Anfrage führt in Rentalars und funktioniert nur, wo Rentalars erreichbar
ist – läuft es nur im eigenen Netz oder per VPN, führt er von außen ins
Leere. Die Knöpfe „Zusagen“ und „Absagen“ dagegen öffnen eine fertige Mail
mit einem nicht erratbaren Code im Betreff an euer Postfach. Rentalars
holt diese Antwort selbst bei eurem Mailanbieter ab, wie die übrigen Mails;
die Verbindung geht nur von innen nach außen. Stellt dann „per
Antwort-Mail“ ein, damit niemand einem Link folgt, der nicht funktioniert.

#### Preisangebote freier Kräfte

*Ausgeschaltet, bis du es einschaltest.* Eine freie Kraft kennt
ihren Marktwert. Statt nur „Zusagen“ oder „Absagen“ kann sie auf eine
Einsatzanfrage mit einem **eigenen Preis** antworten; ihr nehmt ihn an, lehnt
ihn ab oder macht ein Gegenangebot. Wer ein Angebot annimmt, sagt damit zu
dem Einsatz **zu diesem Preis** zu.

**Einschalten.** Unter Einstellungen → Projekte und Personal →
**„Preisangebote freier Kräfte“** (Abschnitt 16): der Schalter **„Freie Kräfte
dürfen einen eigenen Preis anbieten“** (aus); **„Auch Aushilfen“** (aus – dann
gilt es nur für Personen der Art „freie Kraft“); **„Niedrigstes Angebot in
Prozent des hinterlegten Satzes“** und **„Höchstes Angebot in Prozent des
hinterlegten Satzes“** (beide leer = keine Grenze; Angebote außerhalb weist
Rentalars ab, und die Fehlermeldung nennt den Bereich nur, wer seine Sätze
sehen darf) und **„Vorschläge je Anfrage, höchstens“** (voreingestellt 4, von 1 bis
10; Angebote und Gegenangebote zählen zusammen, nach dem letzten bleibt nur
Annehmen oder Ablehnen). Die Grenzen gelten für das Angebot der freien Kraft,
**nicht für euer Gegenangebot**; ohne hinterlegten Satz lässt sich keine Grenze
prüfen. Die Seite ändert, wer Einstellungen ändern darf.

**Für die freie Kraft.** Solange die Funktion an ist, steht in der Mail der
Einsatzanfrage der Satz „Du möchtest deinen eigenen Preis nennen? Das geht in
Rentalars:“ mit einem Link. Im Reiter **„Überblick“** des Projekts (oben, „Der
Überblick – was die Crew sieht“) steht unter der offenen Anfrage „Du kannst die
Anfrage annehmen, absagen oder einen eigenen Preis nennen.“ und der Knopf
**„Preisangebot machen“**; ihn gibt es auch neben der Anfrage auf deiner
Startseite. Du gibst den **Betrag** (Euro, ohne Umsatzsteuer, zwei
Nachkommastellen), **„Je“** Stunde bzw. Tag und insgesamt – **„je Tag“** nur für
Positionen, die nach Tagen abgerechnet werden –, auf Wunsch eine **Nachricht**
(500 Zeichen) und **„Gültig bis“** an und drückst **„Angebot senden“**. Bis zur
Antwort kannst du **„Angebot zurückziehen“**. Antwortet die Planung mit einem
**Gegenangebot**, bietet die Seite **„Gegenangebot annehmen“**, **„Ablehnen“**
und **„Erneut kontern“**; „Bisheriger Austausch“ zeigt alle Runden. Nur du
siehst deine Angebote, und die Mail und die Benachrichtigung „Antwort auf mein
Preisangebot“ sagen dir, was geschehen ist. Den hinterlegten Satz siehst du
nur, wenn du deine Sätze sehen darfst (Sonderrecht oder die Einstellung
„Personen dürfen ihre eigenen Stundensätze sehen“).

**Für die Planung.** Wer Personal im Projekt planen und die Personalkosten sehen
darf, sieht das Angebot in der Planung unter der Anfrage: das Zeichen
„Preisangebot“, den Betrag, den **hinterlegten** Satz und, wie weit das Angebot
davon abweicht (in Prozent). Dort – oder unter **Personal → Preisangebote**,
wo die Angebote mit „Wartet auf Antwort“ und „Alle“ gefiltert stehen – **nimmst
du an**, **lehnst ab** oder **machst ein Gegenangebot**. Die freie Kraft kann ein
Gegenangebot annehmen oder ablehnen und, solange die Runden reichen, erneut
kontern; du kannst dein Gegenangebot zurückziehen. Wer Personalkosten nicht sehen
darf, sieht von Angeboten **nichts**: keine Beträge, keine Zeichen, keine Seite.
Rentalars meldet ein Angebot allen, die das Sonderrecht haben und das
Projekt lesen dürfen (Abschnitt 15, „Benachrichtigungen“).

**Was die Annahme tut.** Die Anfrage gilt als **zugesagt**, und der
**Kostensatz genau dieser Position** wird der Preis: je Stunde der Stundensatz
(die Rate ab der Stundengrenze folgt ihm), je Tag der Tagessatz, „insgesamt“ ein
Pauschalbetrag. Die alten Werte der Position bleiben auf dem Angebot
gespeichert. **Der Preis für den Kunden ändert sich nicht**, und der Satz der
Person und der Funktion bleibt, wie er war. An der Position steht „Preisangebot“,
solange das Angebot gilt; es **endet**, wenn jemand den Kostensatz von Hand
ändert oder die Position eine andere Person oder Funktion bekommt – bei einem
Pauschalbetrag auch, wenn die Person für neue Zeiten neu angefragt wird. Eine neue
Anfrage beginnt eine neue Verhandlung. „Gültig bis“ gilt bis zum Ende des Tages;
ein abgelaufenes Angebot lässt sich nicht mehr annehmen.

**Grenzen.** Nur Euro; höchstens 30 Angebotsschritte je Nutzer und Stunde.
Ein Angebot, das jemand am Telefon nennt, kann die Planung nicht mit einem Knopf
für die Person eintragen; die Schnittstelle erlaubt es (Abschnitt 16, „API-Token“).
Ein Preisangebot ist kein Vertrag in Rentalars: Das Programm setzt den
Kostensatz, mehr nicht. Änderungen am Satz zeigt der Verlauf der Position.

#### Was Personal kostet und einbringt

Je Zeile zeigt der Block Stunden oder Tage, Preis, Betrag – und, mit dem
Recht dafür, die Kosten.

| Abrechnung | Betrag für den Kunden | Beispiel (45,00 € je Stunde, 400,00 € je Tag) |
|---|---|---|
| **nach Plan** | geplante Stunden × Preis | 8 Std. → 360,00 € |
| **Pauschale** | der Preis, unabhängig von den Stunden | 300,00 € |
| **nach Aufwand** | freigegebene Stunden × Preis; bis zur Freigabe die geplanten Stunden, als **Schätzung** markiert | 9,5 Std. → 427,50 € |
| **je Tag** | Tage × Preis je Tag | 2 Tage → 800,00 € |

Die Abrechnung einer neuen Personalposition folgt ihrem
Dienstleistungsprodukt: Ein Produkt nach Stunden – die Voreinstellung –
oder nach Aufwand macht sie zu **„nach Aufwand“**, ein pauschales zu
„Pauschale“, eines mit Tagesmiete zu „je Tag“. „Nach Aufwand“ ist damit
der Normalfall: Berechnet werden die freigegebenen
Stunden, bis dahin die geplanten als Schätzung. An der Position lässt sich die Abrechnung
ändern, ebenso der Preis.

Die **Kosten** sind geplante Stunden × Stundensatz der Person. Hat die
Person in dieser Funktion keinen eigenen Stundensatz, rechnet Rentalars mit
dem Richtwert der Funktion und schreibt „Richtwert“ unter die Kosten –
ebenso für einen offenen Platz. Ist mit der Person eine **Pauschale**
vereinbart, gilt diese – unabhängig von den Stunden und unabhängig davon,
wie dem Kunden berechnet wird.

**Je Tag.** Die Tage sind die Kalendertage, die der Zeitraum berührt:
Montag 08:00 bis Dienstag 20:00 sind 2 Tage, Samstag 22:00 bis Sonntag
04:00 ebenfalls; ein Ende genau um Mitternacht zählt den neuen Tag nicht
mit. Im Dialog kannst du die Tage überschreiben. Die Kosten sind dann Tage
× **Tagessatz** der Person – beim Zuweisen übernommen wie der Stundensatz,
sonst der Richtwert je Tag der Funktion. Gibt es gar keinen Tagessatz,
rechnet Rentalars Stunden × Stundensatz. Auf Angebot,
Auftragsbestätigung und Rechnung steht die Zahl der Tage mit der Einheit
„Tag“.

> **Beispiel.** Anna, Tontechnik, 8 Stunden: Preis 8 × 45,00 € = 360,00 €,
> Kosten 8 × 35,00 € = 280,00 €. Vereinbart ihr mit Anna 300,00 € pauschal,
> sind die Kosten 300,00 € – der Preis bleibt 360,00 €. Dieselbe Anna je
> Tag, Montag 08:00 bis Dienstag 20:00: Preis 2 × 400,00 € = 800,00 €,
> Kosten 2 × 280,00 € = 560,00 €.

**Ab einer Grenze je Tag teurer.** Lange Tage kosten mehr: Am
Dienstleistungsprodukt trägst du eine **„Grenze in Stunden pro Tag“** und
den **„Preis je Stunde ab der Grenze (netto)“** ein, z. B. 10 und 55,00 € –
dann kostet ab der 11. Stunde eines Tages jede Stunde 55,00 €. Für die
Kosten trägst du bei der Person je Funktion den **„Stundensatz ab der
Grenze“** ein (fehlt er, gilt ihr Stundensatz) und an der Funktion den
**„Richtwert je Stunde ab der Grenze“** für offene Plätze und Personen ohne
eigenen Satz. Gezählt wird je Kalendertag und je Position:

- **nach Plan** die geplanten Stunden, wie sie auf die Tage fallen – Montag
  08:00 bis Dienstag 20:00 sind 16 und 20 Stunden; von Hand eingetragene
  Stunden verteilt Rentalars gleichmäßig auf die Tage des Zeitraums;
- **nach Aufwand** die freigegebenen Zeiten, jede am Tag ihres Beginns;
- bei **Pauschale** und **je Tag** gilt keine Grenze.

Eine neue Personalposition übernimmt Grenze und Preis ab der Grenze vom
Produkt wie den Preis selbst; im Dialog der Position lassen sie sich
ändern (mit Preisrecht), den Stundensatz ab der Grenze mit dem Recht für
Personalkosten. Die Planung zeigt unter dem Preis „ab 10 Std. am Tag:
55,00 €“ und unter dem Betrag „davon 2 Std. über der Grenze“;
Preisübersicht, Angebot, Auftragsbestätigung und Rechnung schreiben „davon
2 Std. über 10 Std. am Tag zu 55,00 €“.

> **Beispiel.** Tontechniker zu 45,00 € je Stunde, ab 10 Stunden am Tag
> 55,00 €; Anna arbeitet am Montag von 08:00 bis 20:00, nach Plan: Preis
> 10 × 45,00 € + 2 × 55,00 € = 560,00 €. Mit ihrem Stundensatz von 35,00 €
> und 42,00 € ab der Grenze kostet sie 10 × 35,00 € + 2 × 42,00 € =
> 434,00 €.

Die Preisübersicht führt das Personal als eigenen Block, auf Wunsch je
Phase und Funktion aufgeschlüsselt (Abschnitt 8, „Die Preisübersicht“).
Stunden- und Tagessätze stehen dort nie.

#### Zuschläge für Nacht, Sonn- und Feiertage

Stunden in der Nacht, an Sonn- und Feiertagen kosten
auf Wunsch mehr – im **Preis für den Kunden**, in den **Personalkosten**
oder in beidem. Welche Regeln gelten und ob neue Personalpositionen die
Zuschläge bekommen, steht unter Einstellungen → Zuschläge (Abschnitt 16).
Die Zuschläge sind eine Liste von Regeln, die in jedem Land
taugt; voreingestellt sind die steuerfreien Sätze nach § 3b EStG, und
beide Schalter sind zunächst aus.

- **Welche Positionen:** nur Personalpositionen **nach Plan** oder **nach
  Aufwand** – nie eine Pauschale oder eine Position je Tag; Zuschläge in
  den Kosten nicht, wenn mit der Person eine Pauschale vereinbart ist.
  Material, Nebenkosten, Aufpreise und alle anderen Positionen bekommen
  nie Zuschläge; den Schalter zum Ausnehmen gibt es deshalb nur bei
  Dienstleistungen.
- **An der Position:** Jede Personalposition hat zwei eigene Schalter im
  Dialog: „Zuschläge für Nacht, Sonn- und Feiertage im Preis“ (mit
  Preisrecht) und „… in den Kosten“ (mit dem Recht für Personalkosten).
  Eine neue Position bekommt sie aus den Einstellungen, sofern ihr
  Dienstleistungsprodukt die Zuschläge nicht ausnimmt (Abschnitt 5, „Ein
  Produkt anlegen“). Positionen, die schon geplant waren, ändert ein
  Umschalten der Einstellungen nicht; dort schaltest du sie bei Bedarf im Dialog ein.
- **Welche Stunden:** nach Plan der geplante Zeitraum, nach Aufwand jede
  freigegebene Zeit – die Pause anteilig abgezogen. Hast du die geplanten
  Stunden von Hand eingetragen, verteilt Rentalars sie wie bei der Grenze
  je Tag auf die Tage und innerhalb des Tages anteilig. Gezählt werden die
  Stunden, die wirklich vergehen: Die Nacht der Umstellung auf Sommerzeit
  ist eine Stunde kürzer.
- **Wie sie zusammenkommen:** Von den Regeln an Wochentagen, Feiertagen und
  Tagen im Jahr zählt nur der höchste Satz, von den Regeln zu einer Uhrzeit
  ebenso; beide werden addiert. Mit den Regeln nach § 3b EStG heißt das:
  Der Nachtzuschlag kommt zu einem Sonn- oder Feiertagszuschlag hinzu; von
  Sonntag, Feiertag und Weihnachten/1. Mai zählt nur der höchste. Ein
  Feiertag, der auf einen Sonntag fällt, um 22 Uhr: 25 % + 125 %. Begann
  die Arbeit vor 0 Uhr, gilt von 0 bis 4 Uhr die Regel „Nacht 0–4 Uhr“
  statt der Nacht, und ein Sonn- oder Feiertag reicht bis 4 Uhr des
  nächsten Tages (einstellbar). Preis und Kosten wählen ihre Regel jeweils
  für sich.
- **Mit der Grenze je Tag** (oben) ist der Zuschlag ein Prozentsatz des
  Preises bzw. Satzes, der für diese Stunde gilt; die Stunden über der
  Grenze sind die letzten des Tages.
- Der **Rabatt** der Position gilt auch für die Zuschläge.

Die Planung zeigt unter Betrag und Kosten **„inkl. Zuschläge …“** und
darunter jede Regel mit ihrer Bezeichnung – Regeln mit gleicher
Bezeichnung und gleichem Satz als eine Zeile, etwa „Weihnachten und
1. Mai“ –; Preisübersicht, Angebot, Auftragsbestätigung und Rechnung
nennen sie ebenso.

> **Beispiel.** Tontechniker zu 45,00 € je Stunde, Samstag 18:00 bis
> Sonntag 02:00, nach Plan, Zuschläge im Preis an: Betrag 486,00 € – 8 ×
> 45,00 € = 360,00 € und „inkl. Zuschläge 126,00 €: Nacht 25 % auf 4 Std.
> 45,00 €, Nacht 0–4 Uhr 40 % auf 2 Std. 36,00 €, Sonntag 50 % auf 2 Std.
> 45,00 €“.

Ändert jemand unter Einstellungen → Zuschläge eine Regel, einen Satz, die
Feiertage oder das Bundesland, rechnet jede Position mit Zuschlägen sofort
neu – auch in abgeschlossenen Projekten; erstellte Dokumente bleiben, wie
sie sind.

#### Geplant und geleistet

Sobald Zeiten freigegeben sind (Abschnitt 13), zeigt jede Personalposition
neben den geplanten die **geleisteten Stunden**. Rentalars rechnet eine
freigegebene Zeit der Position mit derselben Person und Funktion zu.

Hat jemand gearbeitet, ohne in dieser Funktion eingeplant zu sein,
erscheint unter dem Block **„Freigegebene Zeiten ohne Personalposition“**.
Mit „Übernehmen“ rechnest du sie einer vorhandenen Position zu oder machst
eine neue daraus – damit nichts Geleistetes untergeht.

### Der Überblick – was die Crew sieht

Der Reiter **Überblick** eines Projekts ist
das, was eingeplante Personen von einem Projekt sehen:

- **Wann und wo:** Zeitraum, Veranstaltungsort, Ansprechpartner vor Ort;
- **Zeitplanung:** die Phasen mit Zeit und Ort;
- **der Veranstaltungsort** mit Anschrift, Ansprechpartner, Zufahrt und
  Strom, mit „Route in Google Maps“ von dort, wo du gerade bist (Abschnitt
  6, „Route und Karte“);
- **Mein Einsatz:** Funktion, Zeit, Treffpunkt, Notiz, das
  Fahrzeug, mit dem du fährst („Fahrzeug: … – du fährst“), der eigene
  Stunden- und Tagessatz („Mein Stundensatz hier“, „Mein Tagessatz hier“),
  sofern deine Firma ihn dir zeigt – und, wenn du angefragt bist, die
  Knöpfe „Zusagen“ und „Absagen“;
- **Fahrten:** die Fahrten des Projekts mit den Fahrzeugen darauf, ihrer
  Route in Google Maps und der Karte der Orte – für alle, die fahren
  (Abschnitt 7, „Die Fahrten eines Projekts“);
- **Dateien für die Crew:** Bühnenplan, Rider, Ablaufplan, Hallenplan,
  Showfiles mit Pult, Version und „aktuelle Show“ – nicht der Vertrag;
- **Crew:** wer noch dabei ist, in welcher Funktion, wann und mit welchem
  Fahrzeug;
- **meine Zeiten** in diesem Projekt und der Knopf „Zeit erfassen“;
- **meine Spesen** in diesem Projekt und der Knopf „Spesen erfassen“
  (Abschnitt 13, „Spesen und Fahrtkosten“).

Die **Packliste** zum Nachlesen und den **Chat** des Projekts (Abschnitt
7, „Chat im Projekt“) haben eingeplante Personen als eigene Reiter, auch die **Korrespondenz** – mit den offenen Nachrichten, zum
Lesen, sobald sie zugesagt haben oder fest eingeplant sind (Abschnitt 14,
„Nachrichten mit Schloss“).

Sie sehen **nicht**: Preise, Kalkulation, den Kunden, die Planung, die
Nachrichten der Korrespondenz mit Schloss, die Stunden- und Tagessätze
anderer.

**Mit der Rolle Crew** sind Überblick (mit den Phasen), Packliste und Chat
 die einzigen Reiter ihrer Projekte, dazu die
Korrespondenz mit den offenen Nachrichten – auch wenn jemand sie unter
„Zugriff“ mit der Stufe „Lesen“ oder „Bearbeiten“ eingetragen hat. Planung,
Zeitplanung, Zugriff, Verlauf, Dokumente, Teilprojekte, die offenen Punkte
und die Fehlbestände bleiben ihr verschlossen, auch über die
Schnittstelle; ein Link auf die Planung führt zum Überblick. Das regelt der
Projektzugriff „nur zugeordnete Projekte, Überblick ohne Planung“ der Rolle
(unten, „Wer welches Projekt sieht“).

**Kontaktdaten der Kollegen.** Der Name ist immer sichtbar. Telefon und
E-Mail sieht ein Kollege nur, wenn die Person das selbst freigegeben hat.
Projektleitung und Personaldisposition sehen sie immer.

Wer das Projekt lesen darf, nutzt denselben Reiter als Crew-Übersicht.

**Drucken.** Oben rechts im Reiter steht **„Drucken / PDF“**: Er öffnet die
**Einsatzübersicht** als PDF (sie heißt weiter so) – mit Briefkopf und
Fußzeile wie die Dokumente und mit allem, was du im Reiter siehst: wann und wo,
Zeitplanung, Veranstaltungsort, dein Einsatz, die Crew, deine Zeiten,
oben mit „Stand“ und Uhrzeit. Preise, Stunden- und Tagessätze und den
Kunden enthält sie nie. Sie bekommt keine Nummer und wird nicht abgelegt;
der Dateiname ist `Einsatzuebersicht-2026-0042.pdf`. Auch die Seite selbst
lässt sich direkt aus dem Browser drucken; Reiter und Knöpfe bleiben dabei
weg.

Die Einsatzübersicht lässt sich auch **einer Mail anhängen** (Abschnitt
14, „Schreiben und antworten“) – dann als Sicht eines beliebigen
Kollegen. Fest abgelegt mit Nummer gibt es die **Crew-Disposition**
(Abschnitt 11).

### Mein Bereich

*Für jeden – jedes Konto ist eine Person: der Eintrag **„Mein Bereich“** in
der Seitenleiste. Ein Recht für das Personal braucht es dafür nicht.*

Mein Bereich öffnet mit „Meine Einsätze“. Die Reiter:

- **Meine Einsätze:** alle Einsätze, in denen du eingeplant bist, als
  Tabelle wie jede Liste (Abschnitt 2, „Listen“) – Projekt, Als, Von, Bis,
  Phase, Ort, Treffpunkt, Geplante Stunden, Stand und Anfrage, mit Spaltenwahl,
  Sortierung, „Gruppieren nach“ und CSV; die Spalte
  „Fahrzeug“ (unter „Spalten“) nennt, mit welchem Fahrzeug du fährst. Die Filter zeigen zuerst die
  kommenden Einsätze (ein laufender bleibt noch zwölf Stunden nach seinem
  Ende stehen); wähle „vergangene“ oder „alle“, einen Zeitraum mit Von und
  Bis, den Stand (fest, Option, Anfrage), die Anfrage (angefragt,
  zugesagt, abgesagt, nicht angefragt) oder ein Projekt. Stornierte
  Projekte fehlen. Ein Klick auf das Projekt öffnet seinen Überblick. Auf
  der Startseite führt „Alle meine Einsätze“ hierher.
- **Verfügbarkeit:** der Verfügbarkeitskalender – grün, gelb, rot, auch als
  Serie, als Monat oder Woche, in der Woche mit markierten Zeitbereichen
  (oben, „Verfügbarkeitskalender“) – und
  daneben die **Kalender**: belegte Zeiten aus deinen eigenen Kalendern
  übernehmen und deine Einsätze in deinen Kalender bringen (oben,
  „Kalender verknüpfen“ und „Die eigenen Einsätze im eigenen Kalender“).
- **Meine Zeiten:** deine Zeiten Woche für Woche (Abschnitt 13).
- **Meine Spesen:** deine Spesen und Fahrtkosten Monat für Monat, mit
  „Spesen erfassen“ (Abschnitt 13, „Spesen und Fahrtkosten“).
- **Auswertung** – nur, wer allein die eigenen Zeiten sieht: die eigenen
  Stunden mit dem Stundenzettel (Abschnitt 13).
- **Servicefälle**: die Servicefälle, an denen du beteiligt
  bist oder für die du zuständig bist (Abschnitt 7, „Servicefälle“).
- **Personaldaten** – auch über „Mein Konto“ → „Meine Personaldaten“:
  - **Kontaktdaten und Kollegen:** Telefon und E-Mail pflegen und ankreuzen,
    ob Kollegen im selben Einsatz sie sehen dürfen. Voreingestellt ist:
    nein.
  - **Meine Funktionen** – mit deinem Stundensatz und Tagessatz, sofern
    deine Firma sie dir zeigt; sonst nur die Funktionen.
  - **Meine Einsätze** – die kommenden.
  - **Wann ich nicht verfügbar bin:** Abwesenheit mit Art und Zeitraum
    eintragen. Die Disposition sieht es sofort in der Verfügbarkeit.
  - **Meine Qualifikationen** – mit Ablaufdatum und Nachweis, zum
    Nachsehen; eintragen und ändern tut die Personaldisposition.

### Wer welches Projekt sieht

Rechte gelten zunächst für ein ganzes Modul (Abschnitt 16). Für Projekte
kommt eine zweite Frage dazu: **für alle – oder nur für zugeordnete?** Das
legt die Rolle fest.

- Eine Rolle mit **„alle Projekte“** (Projektleitung, Lager, Disposition)
  gilt in jedem Projekt.
- Eine Rolle mit **„nur zugeordnete Projekte“**
  gilt nur dort, wo der Nutzer zugeordnet ist. Alle anderen Projekte gibt es für
  ihn nicht – nicht in der Liste, nicht in der Suche, nicht über eine
  Adresse.
- Eine Rolle mit **„nur zugeordnete Projekte, Überblick ohne Planung“**
  (Crew, auch Freie Kraft) gilt ebenso nur in
  zugeordneten Projekten, öffnet dort
  aber höchstens Überblick, Packliste und Chat – dazu die
  offenen Nachrichten der Korrespondenz –, gleich, welche Stufe eine
  Mitgliedschaft nennt (oben, „Der Überblick – was die Crew sieht“).

Zugeordnet wird man auf zwei Wegen:

1. **Von selbst**, wenn die eigene Person im Projekt eingeplant ist. Das
   gibt die Stufe **Einsatzsicht**: die Reiter „Überblick“, „Chat“ und
   „Packliste“, nach der Zusage oder fest eingeplant auch
   „Korrespondenz“ mit den offenen Nachrichten.
   Wer für einen **Servicefall zuständig** oder an ihm
   **beteiligt** ist, arbeitet an ihm mit – gleich, was seine
   Rolle sagt (Abschnitt 7, „Mitarbeit am Fall“).
2. **Ausdrücklich**, über den Reiter **Zugriff** des Projekts: Nutzer
   wählen, Stufe wählen, „Mitglied hinzufügen“.

| Stufe | Zeigt |
|---|---|
| **Einsatzsicht** | Zeit, Ort, Funktion, Kollegen, Fahrten, Packliste, Chat, eigene Zeiten und Spesen; die offenen Nachrichten der Korrespondenz, wenn man zugesagt hat oder fest eingeplant ist |
| **Lesen** | zusätzlich die Planung, ohne etwas ändern zu können |
| **Bearbeiten** | Planung, Teilgruppen, Positionen, Status |
| **kein Zugriff** | nichts – nur in einem Teilprojekt wählbar (unten) |

Zwei Regeln, die Überraschungen ersparen:

- Eine Mitgliedschaft gibt **nie mehr, als die Rolle erlaubt**. Wer mit
  seiner Rolle Projekte nur lesen darf, liest auch als Mitglied mit Stufe
  „Bearbeiten“.
- **Preise, Kosten und Korrespondenz** hängen an keiner dieser Stufen. Sie
  kommen nur über die Sonderrechte der Rolle. Einzige Ausnahme: Die eingeplante Crew liest nach ihrer Zusage (oder fest
  eingeplant) die offenen Nachrichten der Korrespondenz (Abschnitt 14,
  „Nachrichten mit Schloss“).

**Wer Zugriff hat**. Der Reiter **Zugriff** eines Projekts
oder Servicefalls zeigt in der Tabelle **„Wer Zugriff hat“** alle, die
ihm zugeordnet sind, je Zeile mit
**Nutzer**, **Zugriff** und **Grund**:

- Mitglieder („Mitglied: bearbeiten“) – nur diese Zeilen lassen sich hier
  ändern („entfernen“, „Mitglied hinzufügen“);
- Mitglieder des Gesamtprojekts in einem Teilprojekt („Mitglied des
  Gesamtprojekts 2026-0042: lesen“ – „Vom Gesamtprojekt – eine
  Mitgliedschaft hier ersetzt sie.“);
- die eingeplante Crew mit Konto („eingeplant als Tontechnik“ – „Aus der
  Planung – ändert sich mit der Personalposition.“);
- bei einem Servicefall, wer zuständig oder beteiligt ist („zuständig für
  den Servicefall“, „beteiligt am Servicefall“ – „Aus dem Servicefall –
  ändert sich dort.“).

„Zugriff“ ist, was die Person in diesem Projekt **wirklich** darf, nach
ihren Rollen – also etwa „Einsatzsicht“ für eine Mitgliedschaft
„bearbeiten“ mit der Rolle Crew. Gibt ihre Rolle für alle Projekte mehr
als die Zuordnung, steht beim Grund „Rolle für alle Projekte“. Ein Konto,
das sich nicht anmelden kann – ohne Passwort, deaktiviert oder nach
seinem „gültig bis“ –, zeigt „kein Zugang – kann sich nicht
anmelden“, wie die Spalten zum Datenzugriff (Abschnitt 12, „Personen“). Wer nur über eine Rolle für alle Projekte hineinkommt, ohne
zugeordnet zu sein, steht nicht in der Liste – solche Rollen
gelten ohnehin überall.

**Teilprojekte** (Abschnitt 7): Mitglieder des Gesamtprojekts haben
denselben Zugriff in allen Teilprojekten; der Reiter Zugriff eines
Teilprojekts nennt sie mit dem Grund „Mitglied des
Gesamtprojekts 2026-0042: …“. Unter „Zugriff“
eines Teilprojekts gibst du einem Mitglied dort anderen Zugriff – mehr,
weniger oder **„kein Zugriff“**. Eine Mitgliedschaft nur in einem
Teilprojekt öffnet nur dieses, nicht das Gesamtprojekt und nicht die
anderen Teile. Wer in einem Teilprojekt eingeplant ist, sieht dessen
Überblick und Packliste in jedem Fall.

---

## 13. Zeiterfassung

*Für alle mit Zugriff auf die Zeiterfassung. Erfasst wird für die eigene
Person – jedes Konto ist zugleich eine Person im Personal (Abschnitt 12).
Die eigenen Zeiten stehen unter „Mein Bereich“ → „Meine Zeiten“, die
eigenen Spesen unter „Meine Spesen“, Freigeben, Auswertung und Spesen
unter „Personal“; wer nur die eigenen Zeiten sieht, findet die Auswertung
ebenfalls unter „Mein Bereich“.*

### Zeit erfassen – in ein paar Sekunden

Der Knopf **„Zeit erfassen“** steht auf jeder Seite: unter der Seitenleiste,
am Telefon als Uhr oben rechts. Er öffnet einen kleinen Dialog; die Seite
dahinter bleibt, wo sie war.

1. **Projekt** – vorbelegt mit dem Projekt, in dem du gerade eingeplant
   bist. Danach folgen deine anderen Einsätze und die internen Projekte.
   Ein Teilprojekt steht mit seinem Gesamtprojekt da: „2026-0042-1 Bühne
   Marktplatz (Stadtfest)“. Unter **„Servicefälle“** stehen auch
   alle offenen Servicefälle (unten, „Zeiten auf Servicefällen“).
2. **Funktion** – vorbelegt mit der Funktion aus deinem Einsatz. „Funktion“ ist nie leer: Zuerst stehen deine eigenen Funktionen und die,
   für die du im Projekt eingeplant bist, danach die übrigen Funktionen,
   mit denen im Projekt Personal geplant ist (auch offene Plätze und
   Teilprojekte). Hast du keine eigene Funktion und ist im Projekt niemand
   geplant, wählst du aus allen aktiven Funktionen – wie bei einem
   Servicefall. Oben stehen unter **„Für dich eingeplant“**
   deine Einsätze im Projekt mit Funktion, Phase und Zeiten, etwa „Licht –
   Aufbau, Mi 10.03. 08:00–12:00“ – so ist klar, welcher Einsatz gemeint
   ist, wenn du in einem Projekt mehrmals eingeplant bist. Wählst du einen
   davon, zählt die Zeit genau zu dieser Personalposition; wählst du nur
   die Funktion, sucht Rentalars die passende Position nach der Uhrzeit.
3. **Tag**, **Beginn**, **Ende** – steht das Ende vor dem Beginn, ist der
   Folgetag gemeint: 22:00 bis 02:15 sind 4,25 Stunden.
4. **Pause** in Minuten und eine **Notiz**, wenn nötig.
5. **„Zeit speichern“.**

Der Dialog bestätigt mit Stunden, Funktion und Projekt – und mit einem
Hinweis, wenn die Zeit auffällt (unten, „Hinweise bei auffälligen
Zeiten“). „Weitere Zeit“ bringt das Formular zurück, „Spesen erfassen“
öffnet gleich den Dialog für Spesen zu diesem Projekt (unten), „Fertig“
schließt.

**Stoppuhr.** Statt Beginn und Ende einzutippen: „Stoppuhr starten“ – und
später, über denselben Knopf, „Stoppen“. Die Uhr läuft auf dem Server; du
kannst den Browser schließen und das Telefon wegstecken.

**Mehrere Funktionen in einem Zeitraum**. Hast du von Beginn
bis Ende in mehr als einer Funktion gearbeitet – morgens Licht, nachmittags
Stagehand –, öffne beim Erfassen **„Mehrere Funktionen in diesem
Zeitraum“**. Trag unter „Weitere Funktion 1“, „Weitere Funktion 2“ … jede
weitere Funktion (oder jeden weiteren Einsatz) mit ihren Stunden ein; die
Funktion oben bekommt die übrigen Stunden. Zusammen ergeben die Teile die
Stunden des Zeitraums.

- Jeder Teil zählt mit seiner Funktion und seinem Satz zu seiner
  Personalposition – in den Summen, der Auswertung, den Exporten, den
  Kosten und bei den Zuschlägen, die nach den Stunden der Teile verteilt
  werden.
- Der Zeitraum zählt **einmal**: für die Hinweise (die Pause zählt einmal),
  für die Prüfung auf Überschneidungen und beim Einreichen, Freigeben,
  Zurückgeben und Löschen – das gilt immer für den ganzen Zeitraum.
- Änderst du Beginn, Ende oder Pause, ändern sie sich für alle Teile, und
  die Stunden der Teile wachsen oder schrumpfen im selben Verhältnis.
- Eine laufende Stoppuhr lässt sich nicht aufteilen – teile den Zeitraum
  auf, nachdem du sie gestoppt hast.
- In den Listen steht an jedem Teil, welcher er ist, etwa „Teil 1 von 2
  eines Zeitraums von 8 Std.“; beim Freigeben hat ein aufgeteilter
  Zeitraum ein Häkchen.

**Zeiten auf Servicefällen**. Auf jeden offenen Servicefall
– offen oder in Arbeit – kannst du Zeiten erfassen, auch ohne eingeplant
zu sein, und zwar mit jeder Funktion. Fälle, an denen du beteiligt bist
(Abschnitt 7, „Servicefälle“), stehen zuerst, vorbelegt mit der Funktion,
mit der du beteiligt bist; danach alle anderen offenen Fälle.

**Was nicht geht:**

- zwei Einträge derselben Person zur selben Zeit. Der zweite wird mit einem
  Hinweis auf den ersten abgelehnt;
- **Zeiten in der Zukunft.** Erfasst wird, was geleistet ist. Die Meldung
  nennt die Uhrzeit des Servers – geht die Uhr deines Telefons falsch,
  fällt es so auf. Die Stoppuhr ist nicht betroffen: Sie beginnt jetzt;
- mehr als 24 Stunden in einem Eintrag.

**Zeiten ohne Kundenprojekt** – Lager, Werkstatt, Büro – buchst du auf ein
internes Projekt (Abschnitt 7).

**Projekt noch unbekannt?** Wähle im Feld Projekt **„später zuordnen“**.
Zur Wahl stehen dann die Funktionen aus deinen Stammdaten – hast du keine,
alle aktiven Funktionen. Die Zeit ist
gespeichert, kann aber erst **freigegeben** werden, wenn sie einem Projekt
gehört: Ordne es unter „Meine Zeiten“ zu, sobald du es weißt (Stift) – oder
wer freigibt, tut es beim Freigeben.

Der **Stundensatz** wird beim Erfassen ermittelt und am Eintrag
festgehalten: dein eigener Satz in dieser Funktion, sonst der der
Personalposition, sonst der Richtwert der Funktion. Spätere Änderungen
deines Satzes ändern ihn nicht.

**Ohne Netz am Einsatzort?** Mit der **Companion-App für Android**
(Rentalars Companion) läuft die Stoppuhr auf dem Telefon, und du trägst
Zeiten auch ohne Netz nach – auch auf offene Servicefälle; sobald das
Telefon wieder Netz hat, kommen sie hier an – jede genau einmal und mit
denselben Regeln wie im Browser (Abschnitt 2, „Die Rentalars-App für
Android“). Den Zugang für die App legst du unter Mein Konto → API-Token
an.

### Hinweise bei auffälligen Zeiten

Rentalars weist auf Zeiten hin, die nach dem Arbeitszeitgesetz auffallen:

| Hinweis | voreingestellt |
|---|---|
| **Langer Arbeitstag** | mehr als 10 Stunden Arbeit an einem Arbeitstag, ohne Pausen |
| **Kurze Pause** | bei mehr als 6 Stunden Arbeit weniger als 30 Minuten Pause, bei mehr als 9 Stunden weniger als 45 Minuten |
| **Kurze Ruhezeit** | weniger als 11 Stunden zwischen dem Ende eines Arbeitstags und dem Beginn des nächsten |

Gerechnet wird je Person und **Arbeitstag**, über alle Projekte – auch
solche, die du nicht sehen darfst; der Hinweis nennt dann nur Stunden, nie
das Projekt. Als Pause zählen die erfasste Pause und Lücken ab 15 Minuten
zwischen den Einträgen des Tages. Ein neuer Arbeitstag beginnt nach einer
Lücke von mindestens der Ruhezeit (11 Stunden) – oder von mindestens 3
Stunden, wenn der nächste Eintrag an einem späteren Datum beginnt.
Abgelehnte Einträge und eine laufende Stoppuhr zählen nicht.
„Langer Arbeitstag“ und „Kurze Pause“ stehen an jedem Eintrag des Tages,
„Kurze Ruhezeit“ am ersten Eintrag des neuen Tages, etwa „Kurze Ruhezeit:
9,5 Stunden seit dem Ende um 23:30 am 14.10.2026 (weniger als 11).“

Die Hinweise erscheinen gleich nach dem Speichern („Bitte prüfen:“ – „Die
Zeit ist gespeichert. Stimmt sie, ist nichts weiter zu tun.“), unter
„Meine Zeiten“, beim Freigeben und in der Auswertung, auch im CSV (letzte
Spalte „Hinweise“) und im Stundenzettel. Sie **halten nichts auf**: Die
Zeit ist gespeichert und lässt sich freigeben wie jede andere. Die
Grenzen stellt ein Administrator unter Einstellungen → Firmendaten und
Grundeinstellungen ein; 0 schaltet einen Hinweis aus (Abschnitt 16). Dort schaltet **„Hinweise zu Arbeitszeiten anzeigen“** alle Hinweise
für alle zugleich an oder aus – bei der Erfassung, unter „Meine Zeiten“,
beim Freigeben, in der Auswertung und in der Companion-App; die Grenzen
bleiben gespeichert. Ausgeschaltet fehlt in der Auswertung der Haken „Nur
Einträge mit Hinweisen“, und die Spalte „Hinweise“ im CSV bleibt leer. Für
Festangestellte, Aushilfen und freie Kräfte gelten dieselben Hinweise. Ein
Arbeitszeitnachweis im Sinne des Gesetzes wird die Zeiterfassung dadurch
nicht.

### Einreichen und freigeben

Jeder Eintrag hat einen Status:

| Status | Bedeutung |
|---|---|
| **erfasst** | aufgeschrieben, noch bei dir |
| **eingereicht** | zur Freigabe abgegeben; du kannst ihn noch korrigieren |
| **freigegeben** | geprüft und **gesperrt**; zählt im Projekt und in der Auswertung |
| **abgelehnt** | zurückgegeben, mit Grund; korrigieren und neu einreichen |

Der Haken **„Gleich zur Freigabe einreichen“** im Dialog ist gesetzt – ein
gespeicherter Eintrag ist also sofort eingereicht. Nimmst du den Haken
heraus, bleibt der Eintrag bei dir, bis du ihn unter „Meine Zeiten“
einreichst.

**Freigeben** (Personal → Reiter „Freigeben“, mit dem Sonderrecht „Zeiten
freigeben und für andere erfassen“ – Projektleitung und
Personaldisposition haben es): Die wartenden Zeiten stehen nach Projekten
geordnet, alle angehakt, auffällige mit ihrem Hinweis (oben); darunter
stehen bei jedem Projekt die eingereichten **Spesen** und entscheiden sich
mit denselben Knöpfen (unten, „Spesen und Fahrtkosten“).
Zeiten **ohne Projekt** stehen in einem eigenen Block obenan; jede Zeile hat
dort eine Projektauswahl und „Zuordnen“. Erst danach lassen sie sich
freigeben – die Person sieht die Zuordnung in ihren Zeiten.
„Angehakte freigeben“ gibt sie gesammelt frei; einzelne nimmst du vorher
heraus. Über die Filter lässt sich nach Projekt, Person und Zeitraum
eingrenzen. „Angehakte zurückgeben“ verlangt einen Grund – die Person soll
wissen, was zu korrigieren ist.

**Korrigieren und freigeben**. Stimmt nur eine Kleinigkeit
nicht – die Pause fehlt, das Ende ist vertippt –, musst du die Zeit nicht
zurückgeben: **„Korrigieren“** am Ende der Zeile öffnet den Dialog
„Korrigieren und freigeben“ mit Projekt, Funktion, Tag, Beginn, Ende,
Pause und Notiz, darüber, was die Person eingereicht hat. **„Speichern und
freigeben“** speichert deine Korrektur und gibt die Zeit sofort frei. Es
gelten dieselben Regeln wie beim Erfassen – nichts in der Zukunft, keine
Überschneidung, eine Funktion, die die Person im Projekt buchen kann –,
und auch das neue Projekt muss eines sein, für das du freigeben darfst.
Bei einem Teil eines aufgeteilten Zeitraums gelten Zeiten, Pause, Projekt
und Notiz für den ganzen Zeitraum, die Funktion für diesen Teil; freigegeben
wird der ganze Zeitraum. Was vorher eingetragen war, bleibt im
Änderungsprotokoll, und der Verlauf der Person nennt es („Bei der
Freigabe korrigiert – vorher: …“).

**Die Person erfährt es**. Freigabe, Korrektur – mit den
Werten vorher – und Zurückgeben – mit dem Grund – meldet Rentalars der
Person als Benachrichtigung „Meine Zeiten freigegeben, korrigiert oder
zurückgegeben“, eine Nachricht je Person und Aktion: Gibst du zwanzig
Zeiten einer Person auf einmal frei, bekommt sie eine.

**Erinnerung an Freigaben**. Wer Zeiten freigeben darf, wird
an die eingereichten Zeiten und Spesen erinnert, die auf seine Freigabe
warten – nur an die, die er freigeben darf, nicht an die eigenen – mit
der Benachrichtigung „Zeiten warten auf meine Freigabe“. Voreingestellt ist
das eingeschaltet: täglich um 8:00 Uhr, das erste Mal einen Tag nach dem
Einreichen, dann jeden Tag, solange etwas wartet. Ändern oder ausschalten
lässt es sich unter Einstellungen → Benachrichtigungen, „Zeiten zur
Freigabe“ (Abschnitt 16, „Benachrichtigungen der Firma“).

Nur freigegebene Zeiten gehen in die Abrechnung nach Aufwand und in den
Vergleich von geplanten und geleisteten Stunden ein (Abschnitt 12). Eine
Freigabe lässt sich zurücknehmen („entsperren“ in der Auswertung); der
Eintrag ist dann wieder eingereicht.

**Für andere erfassen** – der Crewchef für sein Team – geht mit demselben
Sonderrecht.

Jede Änderung an einem Zeiteintrag steht im Verlauf der Person.

### Meine Zeiten

Mein Bereich → Reiter **„Meine Zeiten“**: Woche für Woche die eigenen Einträge mit Stunden,
Status und Summe; darüber die laufende Stoppuhr und alles, was noch nicht
eingereicht ist. Offene Einträge lassen sich über den Stift korrigieren
oder löschen; freigegebene nicht mehr.

- **Stundenlohn**: zwischen „Stunden“ und „Betrag“ steht dein
  Satz für diesen Eintrag. Bei einem Einsatz „je Tag“ mit deinem eigenen
  Tagessatz stehen dort „Tagessatz“ und sein Betrag, einmal am Tag je
  Einsatz; weitere Einträge desselben Tages zeigen „im Tagessatz“. Hat
  dein Einsatz eine **Pauschale** für dich, stehen dort „Pauschale“ und
  ihr Betrag; sie zählt nur einmal je Einsatz – beim ersten
  erledigten Eintrag, gleich in welcher Woche. Weitere Einträge desselben
  Einsatzes zeigen „in der Pauschale“ und zählen 0; die Stunden zählen
  weiter. Eine Pauschale geht einem Tagessatz vor. Die Summe der Woche
  zählt, was dort steht. Den Richtwert einer Funktion
  zeigt Rentalars nie als deinen Lohn. Spalte und Beträge siehst du nur,
  wenn deine Firma dir deine Sätze zeigt.
- **„In Zwischenablage kopieren“** an freigegebenen Zeiten legt einen Text
  für deine eigene Abrechnung in die Zwischenablage – je Funktion des
  Zeitraums ein Block:

  ```
  Lichttechniker
  	Datum: 2026.10.16
  	Projekt: 2026-0042 - Stadtfest
  	Aktivität: Aufbau
  ```

  Die erste Zeile ist der Name des Dienstleistungsprodukts der Funktion,
  eingerückt ist mit einem Tabulator; das Datum ist der Tag des Beginns,
  „Aktivität“ die Phase des Einsatzes (sonst leer). Rentalars bestätigt
  mit „Kopiert“.
- **Hinweis auf die Companion-App:** Oben steht ein kleiner Hinweis, dass
  du deine Zeiten auch mit der App Rentalars Companion für Android
  erfassen kannst – mit Stoppuhr, auch ohne Verbindung; den Zugang legst
  du unter Mein Konto → API-Token an. Mit × blendest du ihn für immer aus.

### Auswertung

Reiter **„Auswertung“** – unter „Personal“ für alle, die Zeiten freigeben
dürfen, sonst unter „Mein Bereich“: Stunden nach **Person, Projekt, Funktion oder
Tag** summiert, gefiltert nach Person, Projekt, Funktion, Zeitraum und
Status. Ohne Filter zeigt sie den laufenden Monat.

- Jeder sieht die Auswertung der **eigenen** Zeiten.
- Die Zeiten anderer sieht, wer Zeiten freigeben darf – für die Projekte,
  die er sehen darf.
- **Beträge** erscheinen nur, wo du die Stundensätze sehen darfst: mit dem
  Sonderrecht alle, sonst die eigenen. Würde eine Summe einen verborgenen
  Betrag enthalten, fehlt sie ganz, statt zu klein zu erscheinen.

Unter den Summen stehen die einzelnen Einträge, seitenweise wie in jeder
Liste; die Summen umfassen immer alle. Haben Einträge einen Hinweis (oben,
„Hinweise bei auffälligen Zeiten“), sagt die Seite, wie viele; der Haken
**„Nur Einträge mit Hinweisen“** im Filter zeigt nur sie. „Die Einträge“ ist eine Tabelle wie jede Liste: Spalten, Sortierung, „Gruppieren
nach“ und CSV über der Liste gehören nur zu dieser Liste; der Knopf **CSV**
oben liefert die Datei der Auswertung.

**CSV** liefert die Einträge für die Tabellenkalkulation – mit der letzten
Spalte „Hinweise“ –, **Stundenzettel (PDF)** dieselbe Auswahl zum Drucken
und Unterschreiben – je Person ein Abschnitt mit Unterschriftszeile, die
Hinweise unter dem Eintrag. Beide enthalten genau das, was die Seite
zeigt, ohne Filter also den laufenden Monat.

> **Viele Personen auf einmal.** Ein Stundenzettel für alle braucht
> Geduld: Einen Monat mit 100 Personen (78 Seiten) baut Rentalars in etwa
> 20 Sekunden. Mehr als 3.000 Einträge in einem Stundenzettel lehnt es ab
> und bittet, nach Person, Projekt oder Zeitraum einzugrenzen. Für die
> CSV-Datei gilt diese Grenze nicht.

### Spesen und Fahrtkosten

Verpflegung unterwegs, die Fahrt mit dem eigenen Auto, das Hotel, Parken
und Maut: Solche Auslagen erfasst jede Person selbst, zu dem Projekt, für
das sie entstanden sind – am besten gleich vor Ort mit dem Telefon.

**Erfassen.** **„Spesen erfassen“** steht unter Mein Bereich → „Meine
Spesen“, im Überblick eines Projekts bei „Meine Spesen in diesem Projekt“
und im Dialog nach einer erfassten Zeit. Im Dialog:

1. **Projekt** – vorbelegt wie bei den Zeiten mit dem, in dem du gerade
   eingeplant bist. Spesen gehören immer zu einem Projekt; auf ein
   abgeschlossenes oder storniertes lassen sie sich nicht buchen.
2. **Art** – Verpflegung, Fahrt, Übernachtung, Parken/Maut oder Sonstiges –
   und **Tag** (nicht in der Zukunft).
3. **Betrag in Euro** – oder, bei einer **Fahrt mit dem eigenen Auto**, nur
   die **Kilometer**: Rentalars rechnet Kilometer × Satz je Kilometer
   (voreingestellt 0,30 €; der Dialog nennt den Satz). Eine Fahrt behält
   den Satz, mit dem sie erfasst wurde. Für ein Bahnticket trägst du den
   Betrag ein. Rentalars zieht dabei den Arbeitsweg ab (unten).
4. **Notiz** – was es war, etwa „Lager – Stadthalle und zurück“ – und der
   **Beleg**: am Telefon gleich mit der Kamera fotografiert, sonst ein Foto
   oder eine PDF-Datei. Fotos dreht Rentalars richtig herum, verkleinert
   sie und entfernt dabei alle Angaben der Kamera – nur der Ort der Aufnahme bleibt.
5. **„Gleich zur Freigabe einreichen“** ist angehakt; ohne Haken bleiben
   die Spesen bei dir, bis du sie unter „Meine Spesen“ einreichst.

Wer Zeiten freigeben darf, kann Spesen auch für andere erfassen und wählt
im Dialog zuerst die Person.

**Arbeitsweg**. Den Weg von der Wohnung zum Betrieb und
zurück fährt jeder ohnehin; er ist keine Auslage. Ist bei einer Person
unter Personal die **„Entfernung Wohnung – Betrieb (km)“** eingetragen
(Abschnitt 12, „Personen“), zieht Rentalars bei Fahrten nach Kilometern
**einmal am Tag je Projekt die doppelte Entfernung** ab – hin und zurück.
Wohnt jemand 14 km vom Betrieb entfernt, rechnet eine Fahrt von 42 km so:
„42 km − 28 km Arbeitsweg = 14 km“ – genau so steht es an der Fahrt, und
nur die 14 km werden bezahlt.

- Mehrere Fahrten am selben Tag zum selben Projekt teilen sich den Abzug,
  in der Reihenfolge, in der sie erfasst wurden. Eine Fahrt, die kürzer
  ist als der übrige Arbeitsweg, bleibt mit 0,00 € erfasst.
- Ohne eingetragene Entfernung wird nichts abgezogen; Fahrten mit einem
  Betrag statt Kilometern (Bahnticket) ebenfalls nicht.
- Was eine Fahrt abgezogen hat, bleibt an ihr gespeichert. Neu gerechnet
  wird sie nur, wenn du an ihr Projekt, Art, Tag oder Kilometer änderst.
- Unter Einstellungen → Firmendaten und Grundeinstellungen schaltet
  **„Arbeitsweg von Fahrten abziehen“** den Abzug für alle aus.
  Spesen, die schon erfasst sind, ändern sich dadurch nicht.

**Meine Spesen** zeigt Monat für Monat deine Spesen mit Art, Betrag,
Status und Beleg, die Summe des Monats und was davon erstattet ist, als
CSV zum Herunterladen; oben steht unter „Noch nicht eingereicht“, was
noch bei dir liegt oder zurückgegeben wurde, mit „Alle einreichen“.
Solange Spesen nicht freigegeben sind, änderst du sie am Stift oder
löschst sie samt Beleg; freigegebene sind gesperrt.

**Freigeben.** Eingereichte Spesen stehen unter Personal → „Freigeben“ bei
ihrem Projekt unter den Zeiten, angehakt, mit Beleg – „Angehakte
freigeben“ und „Angehakte zurückgeben“ gelten für beides. Wie bei den
Zeiten braucht das Zurückgeben einen Grund. Die Person bekommt eine
Benachrichtigung, wenn ihre Spesen zurückgegeben werden.

**Erstatten und auswerten.** Personal → Reiter **„Spesen“** – für alle,
die Zeiten freigeben dürfen; wer nur die eigenen sieht, kommt über „Meine
Spesen“ an seine – zeigt je **Monat und Person** die Summe, was erstattet
ist und was noch zu erstatten ist; darunter die einzelnen Spesen. Filtern
lässt sich nach Person, Projekt, Art, Zeitraum und Status – „Zu
erstatten“ heißt: freigegeben und noch nicht als erstattet markiert. Ohne
Filter zeigt die Seite den laufenden Monat. Habt ihr ausgezahlt, kreuzt du
die Spesen an, wählst unter **„Erstattet am“** den Tag und drückst
**„Angekreuzte als erstattet markieren“**; die Person bekommt Bescheid.
„nicht erstattet“ nimmt die Markierung zurück, „entsperren“ eine Freigabe.
Die einzelnen Spesen sind eine Tabelle wie jede Liste (Abschnitt 2,
„Listen“). **„CSV mit allen Spalten“** lädt dieselbe Auswahl mit allen
Spalten herunter, nach Tag
sortiert, mit der Spalte „Arbeitsweg (km)“ und als
`spesen-<Datum>.csv` – das ist die Datei für die Lohnbuchhaltung; „CSV“
nur die gezeigten Spalten.

**Kosten des Projekts.** Freigegebene Spesen zählen zu den Kosten des
Projekts: Die Planung zeigt sie unter den Summen als „Spesen und
Fahrtkosten (freigegeben)“, und sie mindern den Gewinn aus dem Projekt –
auch in der Projektliste (Abschnitt 8, „Die Summen“). Die Zeile sieht, wer
Personalkosten sehen darf. In der Preisübersicht und auf den Dokumenten
für den Kunden stehen Spesen nicht; wollt ihr sie weiterberechnen, plant
sie als Nebenkosten (Abschnitt 5).

---

## 14. Korrespondenz

*Mails eines Projekts sieht, wer das Projekt lesen darf und das Sonderrecht
„Korrespondenz lesen“ hat; schreiben verlangt zusätzlich „Korrespondenz
schreiben und senden“. Projektleitung hat beides, Nur-Lesen das Lesen, die
Crew keins davon. Jede Nachricht hat ein Schloss oder ist
offen: Nachrichten mit Schloss liest nur, wer dazu „Preise und
Kalkulation sehen“ darf; offene liest auch die im Projekt eingeplante
Crew, die zugesagt hat oder fest eingeplant ist (unten, „Nachrichten mit
Schloss“).*

### Wie Mails ins Projekt kommen

Rentalars liest ein oder mehrere **Postfächer** mit, etwa
`projekte@eure-firma.example` und `info@eure-firma.example` (unten, „Postfächer
einrichten“). Jedes Projekt hat ein **Kürzel**, das oben auf der
Projektseite steht:

```
[RL#2026-0042]
```

Steht es im **Betreff** einer Mail – irgendwo, in welcher Schreibweise auch
immer, auch hinter „AW:“ –, holt Rentalars die Mail beim nächsten Abruf ins
Projekt, mit allen Anhängen, gleich in welchem Postfach sie liegt. Das
geschieht alle paar Minuten von selbst; „Jetzt abrufen“ in den
Einstellungen unter „Postfächer und Signatur“ geht schneller.

Damit Kunden das Kürzel verwenden, ist es in jeder Mail, die ihr **aus
Rentalars** schreibt, schon im Betreff. Antwortet der Kunde, kommt die
Antwort von selbst zurück – auch wenn er das Kürzel aus dem Betreff
löscht, denn Rentalars erkennt, worauf sie antwortet.

Ein Teilprojekt hat sein eigenes Kürzel, etwa `[RL#2026-0042-1]`; Mails
damit landen im Teilprojekt. Ebenso hat jeder Servicefall ein Kürzel aus
seiner Nummer (Abschnitt 7, „Servicefälle“).

Für Mails, die ihr außerhalb von Rentalars schreibt: Kürzel per Klick
kopieren und in den Betreff setzen. Eine Mail, die ohne Kürzel ankam, holt
ihr ins Projekt, indem ihr sie mit dem Kürzel im Betreff an ein Postfach
der Korrespondenz weiterleitet – oder, wenn ihr Postfach Mails ohne
Projektkennung übernimmt, über die Anfragen (unten).

**Was Rentalars nicht anfasst:** Mails **ohne** Kürzel bleiben im
Posteingang, wie sie sind – ungelesen, unverschoben. Rentalars ist kein
Mailprogramm; alles andere bearbeitet ihr wie gewohnt. Ist ein Postfach so
eingestellt, dass es Mails ohne Projektkennung übernimmt, erscheinen sie
zusätzlich als **Anfragen** unter Projekte – nur Mails, die ab
dem Zeitpunkt unter „übernehmen ab“ ankamen, auf Wunsch nur ungelesene
(unten, „Postfächer einrichten“); auch dann bleiben sie im
Posteingang, bis jemand sie übernimmt. Hat ein Postfach mehrere Adressen,
gilt das je Adresse (unten, „Weitere Adressen eines Postfachs“). Was mit
übernommenen Mails im Postfach geschieht, stellt ihr je Postfach ein: als
gelesen markieren und in einen Ordner verschieben (voreingestellt
„Rentalars“, damit der Posteingang aufgeräumt bleibt), nur als gelesen
markieren, löschen oder unverändert im Posteingang lassen.

**Antworten der Crew auf Einsatzanfragen** tragen einen eigenen Code im
Betreff, etwa `[RA-E-…-JA]`. Rentalars erkennt sie in jedem Postfach, das
es abruft, trägt die Zusage oder Absage ein und behandelt die Mail danach
wie eine zugeordnete (Abschnitt 12, „Einsatzanfragen per Mail
beantworten“). Im Reiter Korrespondenz eines Projekts erscheinen sie
nicht.

### Der Reiter „Korrespondenz“

Alle Mails des Projekts, ein- und ausgehende, in zwei Ansichten – oben
rechts umzuschalten; Rentalars merkt sich die Wahl, bis du dich abmeldest:

- **„Liste“** – die neueste oben: „gesendet“ oder „empfangen“, Betreff,
  Absender oder Empfänger, Datum, Anhänge.
- **„Mailverlauf“** – das Gespräch in zeitlicher Folge wie in einem Chat,
  die neueste Mail unten: Eingegangenes links, Gesendetes rechts. Jede
  Mail zeigt nur, was in ihr neu ist; zitierte frühere Mails und die
  Signatur sind eingeklappt („Zitat und Signatur anzeigen“).

Beim **Gesamtprojekt** stehen auch die Mails seiner Teilprojekte in der
Liste – die, die du lesen darfst –, jede mit der Nummer ihres Teilprojekts
gekennzeichnet; ein Klick öffnet sie im Teilprojekt.

Ein Klick auf den Betreff öffnet die Mail. Sie erscheint **kompakt**: oben
in einer Zeile Absender, Empfänger, Datum und die Zahl der Anhänge, gleich
darunter der Text. Ein Klick auf diese Zeile klappt die Einzelheiten auf –
Von, An, CC, BCC, Datum, Betreff und wie die Mail zugeordnet wurde, auch „als neuer Servicefall“ für eine Mail, aus der gleich ein
Servicefall wurde (unten, „Weitere Adressen eines Postfachs“).

- **Text:** Rentalars zeigt die Mail bereinigt in einem eigenen Rahmen –
  ohne Skripte, und **ohne Bilder von fremden Servern**: Solche Bilder
  verraten dem Absender, wann und wo eine Mail gelesen wurde. Über dem Text
  steht, wie viele zurückgehalten wurden; „Laden“ zeigt sie für diese Mail.
- **Anhänge** öffnen oder herunterladen. **„Zu den Projektdateien“** legt
  einen Anhang mit einer Dokumentart zu den Dateien des Projekts (Reiter
  „Dokumente“) – den
  Bühnenplan des Kunden zum Beispiel, den die Crew dann im Reiter
  „Überblick“ findet.
- **Abwesenheitsnotizen** und **Unzustellbarkeitsmeldungen** sind
  gekennzeichnet. Auf Mails im Projekt antwortet Rentalars nie von selbst
  (bestätigt wird nur der Crew ihre Antwort auf eine Einsatzanfrage,
  Abschnitt 12); auf Mails ohne Projektkennung nur, wenn ihr dafür eine
  Automation eingerichtet habt (Abschnitt 16, „Automationen“).
- **Gehört zu einem anderen Projekt?** Projektnummer eintragen, „Mail
  verschieben“. Das steht im Verlauf beider Projekte.
- **Gehört zu einer Zumietung?** Kam die Mail von genau einem Lieferanten
  des Projekts oder ging sie an ihn, hat Rentalars sie schon seiner
  Zumietung zugeordnet; die Einzelheiten der Mail nennen dann unter
  „Zumietung“ den Lieferanten, mit einem Link zur Seite „Zumietung bei …“
  (Abschnitt 9, „Zumieten“).
  Hier wählst du einen anderen Lieferanten des Projekts oder „– zu keiner
  Zumietung –“.
- **Entfernen** nimmt die Mail aus Rentalars; im Ordner des Postfachs
  bleibt sie.

Kam eine Mail zu einem **abgeschlossenen oder stornierten** Projekt, steht
sie trotzdem dort, mit einem Hinweis, und die Projektleitung erfährt es.

Der Reiter Korrespondenz sieht im Projekt und im Servicefall gleich aus
und bietet dieselben Knöpfe. **„Mail schreiben“** steht dort – und auf der
Seite eines Servicefalls im Kasten „Letzte Mails“ –, wenn du die
Korrespondenz lesen und schreiben darfst und ein Postfach diese Mail
senden kann; ein Servicefall sendet auch über das Postfach seiner Adresse
„nur für Servicefälle“, wenn kein Postausgang eingerichtet ist
(unten, „Weitere Adressen eines Postfachs“).

### Notizen in der Korrespondenz

Nicht alles läuft per Mail: Der Kunde ruft an, am Lagertresen wird etwas
vereinbart. Du hältst das im Reiter Korrespondenz – im Projekt
wie im Servicefall – mit **„Notiz hinzufügen“** fest:

- **„Wann“** – wann es war; voreingestellt jetzt. Es darf auch früher
  gewesen sein, nie in der Zukunft.
- **„Betreff“** – freiwillig; leer gilt die erste Zeile der Notiz.
- **„Notiz“** – was gesagt oder vereinbart wurde.

„Notiz speichern“. **Versendet wird nichts** – die Notiz steht nur in der
Korrespondenz, und zwar zu ihrer Zeit zwischen den Mails: in der „Liste“
mit dem Schild „Notiz“ und „notiert von …“, im „Mailverlauf“ in der Mitte
mit gestricheltem Rahmen. Der Kurzüberblick zählt Notizen eigens („2
Notizen“), und die Zusammenfassung durch die KI liest sie mit (unten).

Schreiben darf eine Notiz, wer Korrespondenz schreiben darf, auch in einem
abgeschlossenen Projekt. Ändern oder entfernen darf sie, wer sie
geschrieben hat oder das Projekt bearbeiten darf – auf ihrer Seite unter
**„Notiz ändern“** bzw. mit „Entfernen“. Beantworten lässt sie sich
nicht. Für die Automationen eines Servicefalls ist eine Notiz keine neue
Kommunikation (Abschnitt 16, „Automationen“). Notizen verschwinden mit den
Mails nach der Frist unter „Mails aufbewahren für … Tage“ (unten,
„Postfächer einrichten“).

### Nachrichten mit Schloss

Jede Nachricht der Korrespondenz – Mail oder Notiz – ist
**mit Schloss** oder **offen**. Damit steuerst du, ob die Crew eine Nachricht lesen
kann oder nur, wer die Finanzen sieht:

| | liest sie |
|---|---|
| **mit Schloss** | wer die Korrespondenz lesen darf **und** das Sonderrecht „Preise und Kalkulation sehen“ hat |
| **offen** | wer die Korrespondenz lesen darf – und zusätzlich die im Projekt **eingeplante Crew**, die zugesagt hat oder fest eingeplant ist (nur lesen), und, wer an einem Servicefall arbeitet (Abschnitt 7, „Mitarbeit am Fall“) |

Wer die Korrespondenz überhaupt lesen darf, ändert sich damit nicht
(oben, am Anfang des Abschnitts). Wer sie ohne Preisrecht liest, sieht
nur die offenen Nachrichten; die Liste sagt das („Du siehst die offenen
Nachrichten. …“). Eine Nachricht, die du nicht lesen darfst, gibt es für
dich nicht – nicht in der Liste, nicht im Mailverlauf, nicht in der
Suche, nicht als Benachrichtigung; ihre Anhänge folgen ihr. Im Verlauf
des Projekts steht sie ohne Betreff: „Nachricht, eingegangen am …“,
„Nachricht, gesendet am …“ oder „Notiz vom …“ – auch bei älteren Einträgen; eine entfernte oder in ein anderes Projekt verschobene
Nachricht nennt der Verlauf mit Betreff nur denen, die auch die
Nachrichten mit Schloss lesen. Benachrichtigungen und offene Punkte aus
Automationen nennen bei einer Mail mit Schloss statt des Betreffs nur
„Mail von … (mit Schloss)“ bzw. „Mail gesendet (mit Schloss)“
(Abschnitt 16, „Automationen“). Wer im
Projekt zugesagt hat oder fest eingeplant ist, bekommt dafür
den Reiter „Korrespondenz“, mit den offenen Nachrichten zum Lesen;
schreiben, antworten oder Notizen anlegen kann die Crew dort nicht. Wer
eingeplant ist, aber noch nicht angefragt wurde, noch nicht geantwortet
oder abgesagt hat, sieht den Überblick, aber keine
Korrespondenz.

**Wie neue Nachrichten beginnen.** Unter **Einstellungen → Postfächer und
Signatur**, bei den „Regeln für alle Postfächer“ unter **„Schloss neuer
Nachrichten“**:

- **„Neue Nachrichten in Projekten: mit Schloss“** – voreingestellt an:
  Korrespondenz in Projekten ist vertraulich.
- **„Neue Nachrichten in Servicefällen: mit Schloss“** – voreingestellt
  aus: Wer am Servicefall arbeitet, liest sie, auch ohne Preisrecht.

Das gilt für eingehende Mails, geschriebene Mails und Notizen,
übernommene Anfragen und einen Servicefall, der aus einer Mail entsteht.
Ausnahme: Eine **Antwort auf eine Nachricht mit Schloss** beginnt mit
Schloss – sie zitiert diese Nachricht; über die Schnittstelle ebenso, wenn
das Programm `locked` weglässt –, und eine eingehende Mail, die auf
eine Nachricht mit Schloss desselben Projekts antwortet, wird mit Schloss
gespeichert. Wird eine Mail in ein anderes Projekt verschoben, behält sie
ihr Schloss.

**Das Schloss setzen und entfernen** darf, wer Korrespondenz schreiben
darf und Preise sieht. Beim Schreiben einer Mail, einer Antwort oder einer
Notiz steht dafür der Haken **„Mit Schloss“**, angehakt, wie die
Einstellung für Projekte bzw. Servicefälle sagt – bei einer Antwort auf
eine Nachricht mit Schloss immer. In der Liste trägt eine
Nachricht mit Schloss das Schloss-Zeichen, daneben **„Schloss
entfernen“** bzw. bei einer offenen **„Schloss setzen“**; auf der Seite
einer Nachricht steht, wer sie liest („Mit Schloss: Nur wer Preise und
Kalkulation sehen darf, liest diese Nachricht.“ oder „Offen: Auch die
Crew des Projekts liest diese Nachricht.“), mit demselben Knopf. Wer
Korrespondenz schreibt, aber keine Preise sieht, schreibt offene
Nachrichten – mit Schloss könnte er seine eigene nicht mehr lesen; das
Formular sagt es.

**Wird das Schloss entfernt**, erfährt es die eingeplante Crew (mit
Zusage oder fest eingeplant), die die Nachricht bisher nicht lesen konnte
– einmal je Nachricht und Person, als Benachrichtigung „Neue Nachricht für
die Crew von …“ der Art „Neue Mail zu einem Projekt“. Benachrichtigungen
über eine neue Mail gehen ohnehin nur an die, die sie lesen dürfen.

### Zusammenfassung und Kurzüberblick

Über der Korrespondenz steht – im Projekt wie im Servicefall gleich – der
Kasten **Zusammenfassung**.
Gibt es eine Zusammenfassung durch die KI, steht sie oben in einer Zeile
mit „von KI erstellt“ und ihrem Datum. Sie ist beim Öffnen der
Seite zugeklappt; ein Klick auf die Zeile klappt sie auf. Offen steht sie
nur gleich, nachdem sie fertig geschrieben ist. Darunter ist ebenso der
**Kurzüberblick ohne KI** zugeklappt.

**Der Kurzüberblick ohne KI** ist immer da, auch wenn bei euch keine KI
eingerichtet ist: wer beteiligt ist, wie viele Mails (empfangen und
gesendet) und Notizen, die erste und die letzte, wer zuletzt geschrieben
hat – mit dem Hinweis „empfangen – noch nicht beantwortet“, wenn die
letzte Mail von außen kam –, genannte Termine und Beträge, offene Fragen
aus den neuesten Mails und die Anhänge. Termine, Beträge und Fragen sucht
Rentalars in den neuesten 200 Mails.

**„Zusammenfassen“** gibt es, wenn eure Firma Zusammenfassungen mit KI
eingeschaltet hat (Abschnitt 16, „KI“); sonst steht dort, wer sie
einschalten kann. Notizen (oben) liest die KI mit; mit **„Chat
einbeziehen“** kommt der Chat des Projekts dazu. Wird später eine Chatnachricht
gelöscht, verschwinden die Zusammenfassungen, die den Chat danach gelesen
hatten (Abschnitt 7, „Chat im Projekt“). Die Zusammenfassung
entsteht im Hintergrund – du kannst weiterarbeiten und bekommst eine
Benachrichtigung, wenn sie fertig ist. Sie ist als **„von KI erstellt“**
gekennzeichnet, mit Modell und Datum, und in deiner Sprache geschrieben.
Kommt danach eine neue Mail – oder, wenn der Chat einbezogen war, eine
neue Chatnachricht –, steht **„veraltet“** daneben – dann „Neu
zusammenfassen“; das macht auf Wunsch die Nacht (unten,
„Automatische Zusammenfassungen“). Wird eine Mail gelöscht, die sie zusammenfasst,
verschwindet auch die Zusammenfassung.

Vor „Zusammenfassen“ steht, wie lange es etwa dauert – gemessen
auf eurem Server. Dauert es lange (mehr als fünf Minuten), sagt Rentalars
das; du kannst trotzdem starten und weiterarbeiten. Während die KI
arbeitet, siehst du, was sie gerade tut („liest die Mails …“, „schreibt …
120 Wörter“). Abgebrochen wird erst, wenn die KI längere Zeit gar nichts
mehr schreibt – nicht nach einer festen Gesamtzeit.

- **KI kann sich irren.** Prüf wichtige Angaben – Termine, Beträge,
  Zusagen – in den Mails selbst.
- **Wohin die Mails gehen:** Mit der lokalen KI verlassen sie den Server
  nicht. Hat eure Firma für Zusammenfassungen eine andere Schnittstelle
  gewählt, nennt der Block sie, bevor du „Zusammenfassen“ klickst. Auf
  einem Raspberry Pi dauert eine Zusammenfassung einige Minuten.
- **Wer sie sieht:** Lesen und anstoßen darf sie, wer die Korrespondenz
  lesen darf. Fasst sie bei einem Gesamtprojekt auch Teilprojekte
  zusammen, deren Mails du nicht lesen darfst, siehst du sie nicht. Weil
  die KI alle Nachrichten liest, auch die mit Schloss, gibt es
  Zusammenfassung und Antwortentwurf nur für die, die alle
  Nachrichten lesen dürfen (oben, „Nachrichten mit Schloss“).

### Automatische Zusammenfassungen

*Ausgeschaltet, bis eine Administratorin sie einschaltet.* Statt
dass jemand „Zusammenfassen“ drückt, kann Rentalars **nachts** Projekte und
Servicefälle selbst zusammenfassen, in die seit der letzten Zusammenfassung
Mails gekommen sind. Du siehst es im Kasten **Zusammenfassung** über der
Korrespondenz: Das Zeichen **„automatisch erstellt“** steht neben „von KI
erstellt“, und der Text darunter sagt „Automatisch in der Nacht erstellt.“.
Die Fassung davor – auch eine von Hand gemachte – bleibt unter „n frühere
Zusammenfassungen“ stehen (voreingestellt fünf), mit dem Vermerk „automatisch
erstellt“ oder „auf Anfrage erstellt“; im Verlauf des Projekts steht, wer oder
was sie gemacht hat.

**Wann Rentalars zusammenfasst.** Nur wenn sich die Korrespondenz geändert hat:
die Zahl der Mails oder die neueste Mail – und, wenn der Chat dazugehört, eine
**neue Chatnachricht**. Das Bearbeiten einer Chatnachricht genügt nicht;
Planung, Aufgaben, Zeiten und Dokumente spielen keine Rolle, denn die KI liest
sie nicht. Ob sich der Text wirklich geändert hat, prüft Rentalars noch einmal,
bevor es die KI fragt; ohne Änderung kostet die Nacht keinen Aufruf. Damit
nicht jede neue Mail eine neue Zusammenfassung auslöst, gibt es einen
**kürzesten Abstand** zwischen zwei Zusammenfassungen (voreingestellt 20
Stunden) und eine **kleinste Zahl von Mails** (voreingestellt 2). Bis die Nacht
kommt, steht **„veraltet“** an der Zusammenfassung, mit „1 neuere Mail ist nicht
in der Zusammenfassung.“ und, wenn die automatischen Zusammenfassungen laufen
und für dieses Projekt nicht ausgeschlossen sind, „Sie wird nachts automatisch
erneuert, oder drücke jetzt „Neu zusammenfassen“.“. Von Hand geht es
jederzeit.

**Was die KI liest.** Der Auftrag hat keinen Nutzer und arbeitet mit einem
festen Umfang, den Administratoren einstellen (Abschnitt 16, „KI“): die Mails
des Projekts und seiner Teilprojekte ohne die zitierten älteren Mails, dazu die
Notizen (voreingestellt an), auf Wunsch den Chat (voreingestellt aus) und die
**Nachrichten mit Schloss** – die Einstellung heißt in der Oberfläche **„Nachrichten
mit Sperre lesen“** (voreingestellt an). Weil in Projekten jede neue Nachricht
mit Schloss beginnt (oben, „Nachrichten mit Schloss“), liest der Auftrag dort
**nichts**, wenn sie aus ist. Deshalb sieht die Zusammenfassung **nur, wer alle
Nachrichten lesen darf** (oben, „Zusammenfassung und Kurzüberblick“); der
Kasten sagt „Nachrichten mit Sperre wurden nicht gelesen.“, wenn sie fehlen.

**Dieses Projekt oder diesen Kunden ausnehmen.** Im Kasten stehen, solange die
automatischen Zusammenfassungen laufen, zwei Knöpfe: **„Keine automatischen
Zusammenfassungen für dieses Projekt“** (wer das Projekt bearbeiten darf) und
**„Keine automatischen Zusammenfassungen für Projekte dieses Kunden“** (wer
Kunden bearbeiten darf). Das Projekt bzw. der Kunde trägt dann das Zeichen
„ausgeschlossen“ bzw. „Kunde ausgeschlossen“; **„Automatische
Zusammenfassungen für dieses Projekt wieder erlauben“** (und „… für diesen
Kunden …“) nimmt es zurück. Eine Zusammenfassung von Hand bleibt möglich.

**Was das für die Datensicherheit heißt.** Lies das, bevor ihr es einschaltet:

- Mit der **lokalen KI** verlassen die Mails den Server nicht. Mit einem
  **Cloud-Dienst** gehen die Texte eurer Kundenmails dorthin – mit Namen, Terminen
  und Beträgen. Die Seite sagt es in Rot.
- Vor dem Senden entfernt Rentalars aus jedem Text, was an seiner **Form** zu
  erkennen ist: IBAN, Kartennummern, Passwörter und Schlüssel,
  E-Mail-Adressen, Telefonnummern (einstellbar). **Namen, Anschriften und was
  in freien Worten steht, erkennt kein Filter** – es geht mit. Nie gesendet
  werden die Preise, die Kalkulation und die Gewinne aus Rentalars, Personalkosten
  und Zeiten, die Stammdaten der Kunden (Kontakt- und Bankdaten), Dateien und ihr
  Inhalt, Fotos – was in einer Mail oder einer Notiz steht, geht dagegen mit,
  auch ein Preis in einer Mail mit Schloss.
- Die **Zustimmung** gilt für **den Server**, an den die Texte gehen: die lokale
  KI oder die Adresse (Schema, Rechner und Port) der Schnittstelle – nicht für
  einen Namen. Wechselt die Zusammenfassung zu einer anderen Adresse, hält
  der Auftrag an („angehalten: anderer Anbieter“), bis eine Administratorin
  erneut zustimmt. Das Ändern des Modells oder des Anzeigenamens gilt nicht als
  Wechsel.
- Der Text der KI ist ein Text von außen: Rentalars zeigt ihn nur als einfachen
  Text, ohne Verweise, Bilder oder Formatierung, und führt nichts aus, was darin
  steht. Das Programm schützt sich gegen Mails, die der KI Anweisungen
  unterschieben wollen – verlass dich nicht darauf, dass es immer gelingt.
- Die KI kann sich irren; prüf Termine, Beträge und Zusagen in den Mails.

**Nicht gebaut:** eine Liste von Servern, die der Betrieb erlaubt (nur die
Adresse prüft Rentalars: für das Internet nur https, kein Weiterleiten, nicht
ins eigene Netz ohne Freigabe); keine Benachrichtigung, wenn die Nacht fertig ist
(die Seite „Automatische Zusammenfassungen“ zeigt die Läufe).

### Schreiben und antworten

**„Mail schreiben“** im Reiter Korrespondenz, oder an einer Mail
**„Antworten“** bzw. **„Allen antworten“**:

- **An** ist vorbelegt – bei einer neuen Mail mit dem Ansprechpartner des
  Projekts, bei „Antworten“ mit dem Absender der Mail (auf eine gesendete
  Mail: mit ihren Empfängern). „Allen antworten“ nimmt zusätzlich alle
  übrigen Empfänger aus An und CC mit, nur die eigenen Postfächer nicht.
- Unter **An** stehen zwei Knöpfe: **„Crew hinzufügen“** trägt alle ein,
  die in den Personalpositionen des Projekts eingeplant sind – ohne
  abgelehnte Anfragen und ohne Personen ohne E-Mail-Adresse; beim
  Gesamtprojekt kommt die Crew der Teilprojekte dazu, die du sehen darfst.
  **„Kunde hinzufügen“** trägt den Ansprechpartner des Projekts ein (beim
  Teilprojekt sonst den des Gesamtprojekts), ohne Ansprechpartner die
  Adresse des Kunden. Was schon im Feld steht, kommt nicht doppelt hinein;
  daneben steht, was hinzukam („Zu „An“ hinzugefügt: …“). Die Seite lädt
  dabei nicht neu. Gibt es keine Adresse, fehlt der Knopf.
- Adressen der Crew bekommst du wie im Überblick: Wer das Projekt
  bearbeiten oder das Personal sehen darf, alle; sonst nur die, die eine
  Person für Kollegen freigegeben hat.
- **CC** und **BCC** – wer unter BCC steht, bekommt die Mail, ohne dass die
  anderen Empfänger es sehen.
- Mehrere Adressen trennst du durch Kommas. Ab drei Buchstaben schlägt
  Rentalars **Adressen** vor – aus Kunden, Ansprechpartnern und Personal,
  soweit du sie sehen darfst.
- Der Betreff bekommt das Kürzel von selbst, eine Antwort den zitierten
  Text und vor dem Betreff „AW:“ – wer Rentalars auf Englisch nutzt,
  schreibt „Re:“.
- **„Signatur anhängen“** ist angehakt: Unter den Text kommt die Signatur
  mit deinen Daten (unten, „Signatur“). Für eine kurze Antwort nimmst du
  den Haken heraus.

Als **Absender** sieht der Empfänger deinen Namen und die Firma, etwa „Max
Mustermann | Muster Veranstaltungstechnik“, mit einer Adresse eurer
Postfächer. Voreingestellt ist die des Postfachs, das die Korrespondenz
versendet (Postausgang, unten), in einem **Servicefall** die
Adresse mit der Rolle „nur für Servicefälle“, wenn ihr eine eingetragen
habt (unten, „Weitere Adressen eines Postfachs“).

**Den Absender wählen**. Darfst du mit mehr als einer Adresse
senden, steht im Formular **„Absender“**: die Postfächer der Korrespondenz,
die senden können, und ihre weiteren Adressen. Die voreingestellte Adresse
nimmt jeder, der Korrespondenz schreiben darf; jede weitere nur, wer eine Rolle
hat, die an ihr unter **„Als Absender wählbar für“** angehakt ist (unten,
„Postfächer einrichten“). Beim **Antworten** ist die Adresse vorgewählt, an
die die Mail kam, wenn du sie nehmen darfst. Gesendet wird über das
Postfach der gewählten Adresse, und die Mail trägt dessen Signatur (unten,
„Signatur“) – die Vorschau wechselt mit. Oben im Formular steht dann
„Gesendet als …“. Antworten kommen so immer zurück in ein Postfach der
Korrespondenz und damit ins Projekt.

Anhängen lassen sich:

- **Dateien des Projekts** (Häkchen),
- unter **„Dokumente“**: **Packliste**, **Preisübersicht** und
  **Einsatzübersicht** als PDF, frisch erzeugt – die Preisübersicht nur
  mit Preisrecht –, und die erstellten **Dokumente** des Projekts
  (Abschnitt 11), bei Rechnungen auch die XRechnung; Dokumente mit Preisen
  nur mit Preisrecht. Die Einsatzübersicht in der Mail ist die Sicht eines
  beliebigen Kollegen: ohne „Mein Einsatz“, Telefon und E-Mail der Crew
  nur, soweit freigegeben – die Mail verlässt das Haus. Angehakt ist sie
  nicht von selbst,
- **weitere Dateien** vom Rechner.

„Senden“ schickt die Mail über das Postfach des Absenders ab und legt sie
im Projekt ab, mit allem, was dranhing. Ging ein erstelltes Dokument mit,
vermerkt Rentalars an ihm, wann und an wen.

„Senden“ neben einem Dokument im Reiter Dokumente führt direkt hierher, mit
dem Dokument schon angehakt.

**Entwurf vorschlagen.** Hat eure Firma Antwortentwürfe eingeschaltet
(Abschnitt 16, „KI“), steht in „Mail schreiben“ der Knopf **„Entwurf
vorschlagen“**: Die KI schreibt aus den bisherigen Mails eine Antwort. Das
dauert einen Moment; den **„Entwurf der KI“** siehst nur du. **„In den Text
übernehmen“** setzt ihn über die zitierte Mail, „Neuen Entwurf
vorschlagen“ versucht es noch einmal. Prüf und ändere ihn, bevor du
sendest – gesendet wird nur, was du selbst abschickst. Dafür brauchst du
das Recht, Korrespondenz zu schreiben.

### Anfragen

**Projekte → Reiter „Anfragen“** – für alle, die das Modul E-Mail lesen
dürfen; wer nur das Modul E-Mail hat, kommt über „Projekte“ in der
Seitenleiste direkt hierher. Hier warten zwei Arten von Mails:

- Mails mit einem **Kürzel, zu dem es kein Projekt gibt** – ein
  Tippfehler, eine alte Nummer –, mit ihrer Kennung;
- aus Postfächern, die Mails ohne Projektkennung übernehmen (unten),
  Mails **ohne Kürzel**, gekennzeichnet mit „ohne Kennung“ – etwa die
  Anfrage eines neuen Kunden an `info@`.

Hier kann außerdem eine **Defektmeldung** warten – wenn die
Automation für Defektmeldungen sie nicht gleich zum Servicefall macht,
sondern „unter Projekte → Anfragen stellt“ (Abschnitt 16, „Automationen“).
Sie trägt das Schild „Defektmeldung“, ihr Betreff führt zum Exemplar, und
unter „Filter“ findest du alle mit **„Art: Defektmeldung“**. Eine
Defektmeldung ist keine Mail: Übernehmen oder „Als Projekt anlegen“ gibt
es dafür nicht, nur **„Als Servicefall anlegen“** (Abschnitt 7,
„Servicefälle“) oder den Papierkorb.

**Anfragen von Hand notieren**. Nicht jede Anfrage kommt per
Mail. Ruft jemand an, notierst du sie mit **„Anfrage anlegen“** oben auf
der Seite, damit sie im Büro weiterbearbeitet wird:

- unter „Wer und wann“: **„Wann“** (voreingestellt jetzt, nie in der
  Zukunft), **„Wer“**, **„Telefon“**, **„E-Mail-Adresse“** und auf Wunsch
  der **„Kunde“** – tippen und aus den Vorschlägen wählen;
- unter „Worum es geht“: **„Betreff“** und **„Notiz“** – was gefragt oder
  vereinbart wurde.

Nötig sind eine Angabe, wie man jemanden erreicht (Wer, Telefon,
E-Mail-Adresse oder Kunde), und eine, worum es geht (Betreff oder Notiz);
„Anfrage notieren“. In der Liste steht sie mit dem Schild **„Notiert“**,
unter dem Namen Telefon, E-Mail-Adresse und Kunde. Unter „Filter“ findest
du alle mit **„Art: händisch notiert“**; die Suche findet auch Telefon,
Notiz und Kunde. **„Bearbeiten“** ändert sie („Anfrage speichern“), und
dort löscht **„Anfrage löschen“** sie endgültig – der Papierkorb in der
Liste nimmt sie nur von der Liste. **„Übernehmen“**, **„Als Projekt
anlegen“** und **„Als Servicefall anlegen“** gehen wie bei einer Mail; das
neue Projekt oder der Fall ist mit Kunde und Betreff vorbelegt, und aus der
Anfrage wird eine **Notiz** in seiner Korrespondenz (oben, „Notizen in der
Korrespondenz“) – mit Wer, Telefon, E-Mail-Adresse und Kunde, geschrieben
von dem, der sie notiert hat. Ein Postfach braucht es dafür nicht, und die
Automationen für eingehende Mails laufen nicht. Notieren darf, wer im Modul
E-Mail bearbeiten darf; ändern und löschen außerdem, wer sie notiert hat.

Die Anfragen sind eine **Tabelle** wie jede Liste (Abschnitt 2,
„Listen“): mit Betreff, Absender, Datum, Kennung und Postfach, Spalten zum
Wählen, Sortieren per Klick auf die Überschrift, Filtern nach Text, Art
und Postfach, „CSV“ und „CSV mit allen Spalten“ und **„Gruppieren nach“**
Absender, Datum, Kennung, Postfach oder Empfangsadresse. Die Spalte
**„Empfangsadresse“** (unter „Spalten“) nennt die Adresse des Postfachs,
an die die Mail ging – bei mehreren Adressen eines Postfachs die, an die
sie geschrieben war; ältere Mails haben keine
(beim Gruppieren „(ohne Angabe)“). Alle Mails bleiben unverändert im
Posteingang, bis jemand sie übernimmt.

- **Einem Projekt zuordnen:** Projektnummer eintragen und
  **„Übernehmen“** – Rentalars holt die Mail aus ihrem Postfach ins
  Projekt. Schon beim Tippen schlägt das Feld passende Projekte vor, mit
  Nummer und Name, auch wenn du einen Teil des Namens tippst; vorgeschlagen
  wird nur, was du sehen darfst.
- **„Als Projekt anlegen“** an einer Mail ohne Kennung öffnet
  ein neues Projekt, vorbelegt mit dem Betreff als Name und mit Kunde und
  Ansprechpartner aus dem Absender, soweit Rentalars ihn kennt. Beim
  Speichern kommt die Mail ins neue Projekt – oder, wenn etwas nicht
  klappt, bleibt alles, wie es war.
- **„Als Servicefall anlegen“** macht aus einer Störung, einer Frage oder
  einer Reparatur gleich einen Servicefall, mit der Mail darin (Abschnitt
  7, „Servicefälle“).
- **Der Papierkorb** („von der Liste nehmen“) entfernt nur den Eintrag,
  ohne Rückfrage; die Mail bleibt, wo sie ist. Mit den **Häkchen** vor den
  Zeilen nimmst du mehrere auf einmal herunter: Sobald eines gesetzt ist,
  erscheint unter der Liste eine Leiste, die beim Scrollen am unteren Rand
  stehen bleibt, mit der Zahl der gewählten Einträge, **„Ausgewählte von
  der Liste nehmen“** (nach einer Rückfrage) und „Auswahl aufheben“.

Übernehmen, anlegen und von der Liste nehmen darf, wer im Modul E-Mail
bearbeiten darf; für ein neues Projekt oder einen Servicefall braucht es
dazu das Recht, Projekte anzulegen. Soll jede neue Anfrage gleich eine
Eingangsbestätigung bekommen, richtet ein Administrator eine Automation
ein (Abschnitt 16, „Automationen“). Die Knöpfe
„Mail-Protokoll“ und „Postfächer“ führen in die Einstellungen; den Stand
des Abrufs und „Jetzt abrufen“ findest du dort (unten).

### Postfächer einrichten

*Einstellungen → E-Mail → „Postfächer und Signatur“ (oder „Postfächer“ bei
den Anfragen). Postfächer und die Regeln für alle Postfächer ändert, wer
das Modul E-Mail bearbeiten darf; Postfächer löschen, wer darin löschen
darf – voreingestellt nur Administratoren; die Signatur, wer die
Einstellungen ändern darf.*

Die Seite listet alle **Postfächer** mit ihren Rollen und ihrem Stand:
aktiv oder aus, letzter erfolgreicher Abruf, letzter Fehler. **„Jetzt
abrufen“** ruft alle Postfächer der Korrespondenz ab; **„Verbindung
prüfen“** meldet sich bei IMAP und SMTP an, ohne etwas zu ändern oder zu
senden. „Postfach hinzufügen“ legt ein weiteres an, **„Bearbeiten“**
öffnet eines; „Verbindung prüfen“ und „Bearbeiten“ stehen in jeder Zeile
nebeneinander auf gleicher Höhe, am Telefon ebenso. Ein vorhandenes
Postfach bei einem beliebigen
Anbieter genügt; es braucht IMAP zum Abrufen und SMTP zum Senden, beides
verschlüsselt. Jedes Postfach hat:

- **Name** – erscheint in der Liste, im Mail-Protokoll und bei den
  Anfragen – und **Adresse**, mit der gesendete Mails beim Empfänger
  erscheinen. Als Name steht davor, wer schreibt, und die Firma („Max
  Mustermann | Firma“).
- **Aktiv** – ausgeschaltet wird es weder abgerufen noch zum Senden
  benutzt.
- **Rollen:**
  - **Korrespondenz** – neue Mails werden abgerufen und über das Kürzel
    ihrem Projekt zugeordnet; mehrere Postfächer können diese Rolle haben.
  - **Postausgang der Korrespondenz** – in Projekten geschriebene Mails
    gehen über dieses Postfach hinaus, solange niemand einen anderen
    Absender wählt (oben, „Schreiben und antworten“). Das ist genau eines
    der aktiven Postfächer der Korrespondenz; setzt du es bei einem
    anderen, gibt das bisherige die Rolle ab, und die Seite sagt es.
  - **Systemmails** – Einladungen, Passwort-Links und Benachrichtigungen
    gehen über dieses Postfach hinaus; höchstens eines. Ohne ein solches
    gehen sie über den Mailserver aus der Konfiguration der Installation –
    und ist dort keiner eingetragen, gar nicht (unten, „Ohne Mailserver“).
    Jede Systemmail endet mit dem Hinweis, dass Rentalars sie verschickt
    hat (unten, „Signatur“).

  Ein Postfach darf mehrere Rollen haben – ein einziges für alles geht
  also auch.
- **Empfangen (IMAP):** Server, Port, Verschlüsselung (SSL/TLS oder
  STARTTLS), Benutzer, Passwort und **Ordner Posteingang** (meist
  „INBOX“). Für Postfächer der Korrespondenz außerdem:
  - **„Mails ohne Projektkennung übernehmen“** – eingeschaltet erscheinen
    sie als Anfragen unter Projekte (oben); ausgeschaltet (voreingestellt)
    bleiben sie unberührt im Posteingang. Das gilt für die Adresse des
    Postfachs und jede Adresse, die nicht unter „Weitere Adressen
    (Aliasse)“ steht (unten).
  - **„übernehmen ab“** – das Übernehmen wirkt erst ab einem
    Zeitpunkt: Schaltest du es ein, setzt Rentalars „übernehmen ab“ auf
    diesen Moment. Ältere Mails bleiben unverändert im Posteingang. Den
    Zeitpunkt kannst du ändern, zum Beispiel einige Tage zurück. Maßgeblich
    ist, wann die Mail im Postfach ankam. Schaltest du das Übernehmen aus,
    ist das Feld wieder leer; beim nächsten Einschalten gilt wieder dieser
    Moment.
  - **„nur ungelesene Mails“** – Rentalars übernimmt nur
    Mails, die im Postfach noch nicht gelesen sind.

    In der Liste der Postfächer steht beides hinter der Regel, etwa „ab
    01.03.2027 08:00, nur ungelesene“. Mails mit Projektkennung und
    Antworten auf zugeordnete Mails betrifft beides nicht; sie kommen immer
    in ihr Projekt. Warum eine Mail liegen blieb, steht im Mail-Protokoll
    („angekommen vor dem Zeitpunkt, ab dem Mails ohne Kennung übernommen
    werden“ oder „schon gelesen – …“). Schon übernommene Anfragen bleiben.
  - **„Zugeordnete Mails im Postfach“**: als gelesen markieren und in einen
    Ordner verschieben (voreingestellt „Rentalars“; Rentalars legt ihn an,
    wenn es ihn nicht gibt), **nur als gelesen markieren** (die Mail bleibt gelesen im Posteingang – außer die Antwort auf eine
    Einsatzanfrage, die auch dann in den Ordner kommt), **löschen** – nur, wenn
    Rentalars der einzige Ort ist, an dem sie aufbewahrt werden – oder
    **unverändert im Posteingang lassen**, auch ungelesen.
- **Senden (SMTP):** Server, Port, Verschlüsselung. Der Haken **„gleicher
  Benutzer und gleiches Passwort wie beim Empfang (IMAP)“** ist
  voreingestellt – dann braucht der Versand keine eigenen Zugangsdaten.
  Nimmst du ihn heraus, erscheinen eigene Felder für Benutzer und Passwort
  des Versands; bleibt der Benutzer leer, sendet Rentalars ohne Anmeldung.
- **„Als Absender wählbar für“** – die Rollen, deren
  Mitglieder die Adresse dieses Postfachs beim Schreiben unter „Absender“
  wählen dürfen (oben, „Schreiben und antworten“). Den Postausgang – im
  Servicefall die Adresse „nur für Servicefälle“ – dürfen ohnehin alle, die
  Korrespondenz schreiben dürfen; ohne angehakte Rolle steht jede andere
  Adresse nur Konten mit „Hat alle Rechte“ offen.
- **„Signatur“** (auf der Seite des Postfachs) – eine eigene
  Signatur für alle Mails von seinen Adressen (unten, „Signatur“).

**Regeln für alle Postfächer:** **Abrufen alle … Minuten** (voreingestellt
2), **größte Mail** (25 MB; von größeren übernimmt Rentalars den Text, die
Anhänge bleiben im Postfach) und **Mails aufbewahren für … Tage** (0:
unbegrenzt), unter **„Schloss neuer Nachrichten“**, ob neue
Nachrichten in Projekten und in Servicefällen mit Schloss beginnen
(voreingestellt: in Projekten ja, in Servicefällen nein; oben,
„Nachrichten mit Schloss“); „Regeln speichern“. Darunter steht, wie Einsatzanfragen
beantwortet werden („Antwort auf Einsatzanfragen: „Beides““) und an welches
Postfach Antworten per Mail gehen. Gewählt wird das
unter Einstellungen → Firmendaten und Grundeinstellungen; der Link
„Ändern unter Firmendaten und Grundeinstellungen“ führt dorthin (Abschnitt
12, „Einsatzanfragen per Mail beantworten“).

Passwörter speichert Rentalars verschlüsselt und zeigt sie nie wieder an;
ein leeres Feld behält das gespeicherte. Klemmt ein Postfach, werden die
anderen weiter abgerufen, und die Administratoren bekommen eine
Benachrichtigung mit dem Namen des Postfachs – eine, nicht bei jedem
Versuch.

**Mailserver im eigenen Netz.** Rentalars verbindet sich zu
einem IMAP- oder SMTP-Server, der ins interne Netz führt – dieser Rechner,
private Netze wie 192.168.x.x, der Server selbst –, nur, wenn der
Betreiber ihn in der Konfigurationsdatei freigibt (`[network]
allow_internal`). Sonst meldet „Verbindung prüfen“ „Die Adresse führt in
ein internes Netz …“, und der Selbsttest nennt das Postfach (Abschnitt 16,
„Selbsttest“).

#### Weitere Adressen eines Postfachs

Oft kommen in **einem** Postfach die Mails mehrerer Adressen an, etwa
`support@` und `projekt@` als Aliasse von `info@`. Du trägst sie
unter Einstellungen → Postfächer und Signatur → „Bearbeiten“ am Postfach
unter **„Weitere Adressen (Aliasse)“** ein, jede mit eigener Regel:

- **Adresse** – so, wie die Mails an sie adressiert sind; Groß- und
  Kleinschreibung zählt nicht.
- **Mails ohne Projektkennung:**
  - **„nicht übernehmen“** – sie bleiben unberührt im Posteingang;
  - **„als Anfrage“** (voreingestellt) – sie warten unter Projekte →
    Anfragen;
  - **„gleich als Servicefall anlegen“** – Rentalars legt sofort einen
    Servicefall mit der Mail an (Abschnitt 7, „Servicefälle“) und
    benachrichtigt die Person, die du unter **„verantwortlich für neue
    Servicefälle“** einträgst; sie ist dann für den Fall zuständig.
- **„übernehmen ab“** und **„nur ungelesene Mails“** – wie
  beim Postfach (oben): Eine Adresse, die Mails als Anfrage oder als
  Servicefall übernimmt, übernimmt nur Mails ab diesem Zeitpunkt und auf
  Wunsch nur ungelesene. Wählst du eine dieser Regeln, setzt Rentalars den
  Zeitpunkt auf diesen Moment.
- **„nur für Servicefälle“** – Mails, die du in einem Servicefall
  schreibst, gehen mit dieser Adresse als Absender hinaus (sonst mit der
  Adresse des Postausgangs); sie ist dort unter „Absender“
  vorgewählt. Nur eine Adresse kann diese Rolle haben; gibst du sie einer
  anderen, verliert die bisherige sie, und die Seite sagt es.
- **„Als Absender wählbar für“** – wie beim Postfach (oben):
  welche Rollen diese Adresse beim Schreiben wählen dürfen. Gesendet wird
  über das Postfach der Adresse, oder über den Postausgang, wenn es selbst
  nicht senden kann; die Liste der Adressen nennt die Rollen („Absender
  für: …“).

Mails **mit** Projektkennung und Antworten auf zugeordnete Mails kommen
immer in ihr Projekt oder ihren Servicefall, gleich an welche Adresse sie
gingen. An welche Adresse eine Mail ging, liest Rentalars aus den
Kopfzeilen Delivered-To, X-Original-To, An und CC, in dieser Reihenfolge;
die erste eingetragene Adresse, die dort steht, entscheidet. Mails an
Adressen, die nicht in der Liste stehen – auch an die Adresse des
Postfachs selbst –, folgen der Einstellung „Mails ohne Projektkennung
übernehmen“ des Postfachs. Trägst du die Adresse des Postfachs selbst in
die Liste ein, gilt ihre Regel statt dieser Einstellung – für jede Mail,
die zu keiner anderen eingetragenen Adresse passt. (Viele Mailserver
schreiben die Adresse des Postfachs auch bei einer Mail an einen Alias in
Delivered-To; deshalb prüft Rentalars sie zuletzt.)

Eine Eingangsbestätigung einer Automation (Abschnitt 16, „Automationen“)
geht von der Adresse hinaus, an die die Mail geschrieben war. Die eigenen
Adressen lässt „Allen antworten“ weg, und Automationen antworten nie an
sie. Änderungen an den Adressen stehen im Verlauf des Postfachs.

#### Ohne Mailserver

Gibt es kein Postfach mit der Rolle „Systemmails“ und in der Konfiguration
der Installation keinen Mailserver, kann Rentalars **keine Systemmails**
verschicken – keine Einladungen, Passwort-Links, Einsatzanfragen per Mail
und Benachrichtigungen per Mail. Als Absender stünde dann
`rentalars@localhost` da, die Vorgabe der Konfigurationsdatei, und
nirgends käme etwas an. Rentalars sagt das, statt „gesendet“ zu
melden:

- Im **Mail-Protokoll** steht eine solche Mail als **„nicht versendet –
  kein Mailserver eingerichtet“**; sie zählt nicht als gesendet, und eine
  Benachrichtigung gilt nicht als per Mail verschickt.
- Wo du etwas versendest – die Testmail des Selbsttests, eine Einladung
  beim Anlegen eines Nutzers oder einer Person, „Link zum Setzen des
  Passworts senden“, eine Einsatzanfrage –, zeigt die Seite „Nicht
  versendet – kein Mailserver eingerichtet.“ mit einem Link zu
  Einstellungen → Postfächer und Signatur. Nach dem Anlegen eines Nutzers
  ohne Mailserver führt Rentalars gleich zu seiner Seite, damit du ihm ein
  Einmal-Passwort geben kannst (Abschnitt 16, „Nutzer“).
- Die Seite „Postfächer und Signatur“ und das Mail-Protokoll zeigen oben
  einen Hinweis, und der **Selbsttest** nennt unter „E-Mail“ den fehlenden
  Mailserver (Abschnitt 16, „Selbsttest“).

Abhilfe: Gib einem Postfach die Rolle „Systemmails“ – oder lass den
Administrator des Servers einen Mailserver in die Konfiguration
eintragen.

**Postfach löschen.** Unten im Formular eines Postfachs führt **„Postfach
löschen“** zu einer Seite, die unter „Was dann passiert“ sagt, was folgt:

- Die Mails der Projekte, die über das Postfach kamen oder gingen, und die
  Einträge im Mail-Protokoll bleiben und nennen das Postfach weiter beim
  Namen – im Protokoll mit „(gelöscht)“.
- Anfragen und Mails mit unbekannter Kennung, die in dem Postfach warten,
  verschwinden aus Projekte → Anfragen; auf dem Server bleiben sie im
  Postfach.
- Danach hat kein Postfach mehr seine Rollen. Neue Mails darin ruft
  Rentalars nicht mehr ab; Systemmails gehen, ohne ein anderes Postfach
  dafür, über den Mailserver aus der Konfiguration der Installation.
- Gehen Antworten auf Einsatzanfragen per Mail an dieses Postfach, kommen
  Antworten auf die bisher verschickten Anfragen nicht mehr an.
- Versendet es die Korrespondenz, übernimmt das ein anderes Postfach der
  Korrespondenz: Gibt es nur eines, das senden kann, nennt die Seite es;
  gibt es mehrere, wählst du unter „Versendet ab jetzt die Korrespondenz“.
  Kann keines senden, lässt sich das Postfach nicht löschen – trag zuerst
  bei einem anderen SMTP-Server und Adresse ein oder schalte die anderen
  aus.

Statt zu löschen, kannst du das Postfach dort auch **„Nur ausschalten“**:
Es bleibt in der Liste und lässt sich wieder einschalten.

**Das Postfach „Projekte“.** Es hat die
Rollen Korrespondenz und Postausgang, seine Zugangsdaten und den Stand
des Abrufs. Mails ohne Projektkennung übernimmt es erst, wenn ihr es
einschaltet.

Das **Präfix** des Kürzels – „RL“ in `[RL#2026-0042]` – stellt ihr unter
Einstellungen → Firmendaten und Grundeinstellungen ein. Ändert ihr es,
brauchen Antworten auf ältere Mails weiterhin das alte. (Mit dem Präfix
der Projektnummern hat es nichts zu tun; das gehört zur Nummer, Abschnitt
16, „Nummernkreise“.)

### Signatur

Eine **gemeinsame Signatur für alle** steht auf derselben Seite
(Einstellungen → E-Mail, Abschnitt „Signatur“) – mit einer Vorschau, wie
sie mit deinen Daten aussieht. **„Signatur schreiben“** bzw. **„Signatur
bearbeiten“** öffnet den Editor; ändern darf sie, wer die Einstellungen
ändern darf.

- Die Signatur ist **einfacher Text oder HTML**. Ohne HTML-Tags bleiben die
  Zeilenumbrüche erhalten; mit HTML sind Links, fetter Text, Tabellen und
  Bilder von einer Webadresse möglich. Skripte und Formulare entfernt
  Rentalars.
- **Platzhalter** setzen die Daten dessen ein, der die Mail schreibt –
  aus seiner Person im Personal (Abschnitt 12) –, und den Firmennamen aus
  den Firmendaten: `{vorname}`, `{nachname}`, `{position}`, `{email}`,
  `{telefon}`, `{firma}`. Ein Klick auf einen Platzhalter in der Liste
  daneben setzt ihn an der Stelle des Cursors ein.
- **„Vorschau zeigen“** zeigt sie mit deinen Daten; beim Tippen folgt die
  Vorschau von selbst. „Speichern“.

Zum Beispiel:

```
Viele Grüße
{vorname} {nachname}
{position}
{firma} · Telefon {telefon} · {email}
```

Rentalars hängt sie an jede Mail, die ihr aus einem Projekt schreibt; beim
Schreiben lässt sie sich mit „Signatur anhängen“ abwählen. Mails mit
Signatur gehen als Text und als HTML hinaus. Ohne Signatur gehen Mails nur
mit ihrem Text hinaus.

**Signatur je Postfach**. Ein Postfach kann eine eigene
Signatur haben – etwa `support@` mit der Nummer der Hotline. Auf der Seite
des Postfachs (Einstellungen → „Postfächer und Signatur“ → „Bearbeiten“)
öffnet im Kasten **„Signatur“** der Knopf **„Eigene Signatur schreiben“**
bzw. **„Signatur des Postfachs bearbeiten“** denselben Editor mit denselben
Platzhaltern. Mails von den Adressen dieses Postfachs – seiner eigenen und
seinen weiteren – tragen dann seine Signatur; bleibt sie leer, gilt die
gemeinsame. Welches Postfach welche hat, zeigt die Seite „Postfächer und
Signatur“ unter **„Signaturen der Postfächer“** („eigene Signatur“ oder
„gemeinsame Signatur“). Ändern darf sie, wer die Einstellungen ändern darf.

**Mails, die Rentalars von selbst verschickt** – Benachrichtigungen,
Einladungen, Links zum Passwort, Einsatzanfragen und die Bestätigungen
von Antworten per Mail, Meldungen über Fehler und Aufgaben im
Hintergrund, die Testmail des Selbsttests –, tragen keine Signatur.
Stattdessen enden sie mit dem Satz „Diese Nachricht wurde automatisch von
Rentalars für Muster Veranstaltungstechnik versendet:
https://rentalars.example.de“ – mit dem Firmennamen aus den Firmendaten
(Abschnitt 16) und der Adresse eurer Installation. So sieht jeder
Empfänger, woher die Mail kommt. Die Adresse stellt der Administrator des
Servers ein. Mails, die ihr im Projekt schreibt, bekommen diesen Satz
nicht.

### Mail-Protokoll

**Einstellungen → Mail-Protokoll** (auch über „Mail-Protokoll“ bei den
Anfragen) hält jede Mail fest, die in einem Postfach der Korrespondenz
ankam oder Rentalars verlassen hat – auch Einladungen, Links zum
Zurücksetzen des Passworts und Benachrichtigungen: Zeitpunkt, Absender,
Empfänger, Betreff, Projekt, **Postfach** und **Ergebnis** – „Anfrage“
für Mails ohne Kennung, die bei den Anfragen gelandet sind, **„Antwort auf
Einsatzanfrage“** mit „Zusage“ oder „Absage“ für Antworten der Crew per
Mail (Abschnitt 12) – und die Art **„automatische
Antwort“** für Antworten einer Automation (Abschnitt 16, „Automationen“),
 das Ergebnis **„nicht versendet – kein Mailserver
eingerichtet“** für Systemmails, die mangels Mailserver nicht hinausgingen
(oben, „Ohne Mailserver“). Wurde eine Antwort der Crew nicht
übernommen, ist das
Ergebnis gelb und nennt den Grund („Absage – nicht übernommen: schon
beantwortet“). So lässt sich klären, ob eine Mail wirklich hinausging oder
ankam. Den Text einer Mail speichert das Protokoll nie. Ist ein Postfach
gelöscht, steht es mit seinem Namen und „(gelöscht)“ da, etwa „Info
(gelöscht)“; die Suche nach dem Namen findet es weiter.

Filtern lässt sich nach Text (Adresse, Betreff, Projektnummer,
Postfachname), **Richtung**, **Art**, **Ergebnis** und Zeitraum; wie jede Liste gibt es
das Protokoll auch als CSV. Die Einträge bleiben so lange wie die Mails
(„Mails aufbewahren für … Tage“), bei unbegrenzter Aufbewahrung ein Jahr.
Mit einem anonymisierten Kunden verschwinden auch seine Einträge.

---

## 15. Planung und Überblick

*Kalender und Zeitstrahl für alle mit Zugriff auf Projekte – jeder sieht
darin die Projekte, die er sehen darf. Materialauslastung und
Fehlbestände für alle, deren Projektrechte für alle Projekte gelten; der
Personalplan für die Personalverwaltung; die Wiedervorlagen für alle mit
Zugriff auf Projekte.*

Die Seitenleiste hat dafür den Eintrag **Planung** mit sechs Reitern, in
dieser Reihenfolge: Kalender, Zeitstrahl, Materialauslastung, Personalplan,
Fehlbestände und Wiedervorlagen. Einen Zeitstrahl für ein einzelnes Produkt, Modell,
Exemplar oder eine Person gibt es außerdem an deren eigener Seite
(Abschnitte 4, 5 und 12), für ein Projekt mit seinen Phasen und seinem
Personal in seiner Zeitplanung (Abschnitt 7, „Zeitplanung“).

Zeitstrahl, Materialauslastung und Personalplan haben dieselbe
Zeit-Ansicht: Sie zeigen zuerst **4 Tage** in Stunden-Spalten. Mit
**„Tage“** und **„Wochen“** wechselst du die Ansicht, mit „‹ früher“,
„heute“ bzw. „diese Woche“ und „später ›“ blätterst du, unter „Von“
wählst du den ersten Tag. Rentalars merkt sich bis zum Abmelden, ob du
Tage oder Wochen gewählt hast und wie viele Tage – gemeinsam für alle
drei Reiter (unten, „Zeitstrahl“).

Servicefälle (Abschnitt 7) haben keinen Zeitraum und erscheinen deshalb
weder im Kalender noch im Zeitstrahl, in der Materialauslastung oder bei
den Fehlbeständen.

### Kalender

Der Kalender öffnet mit der **Woche**. Oben wählst du die **Ansicht**:
**„Woche“** oder **„Monat“**. Rentalars merkt sich die Wahl, bis du dich
abmeldest.

**Phasen und Wiedervorlagen**. Über dem Kalender kreuzt du
an, was er außer den Projekten zeigt: **„Phasen der Projekte“**
(voreingestellt an) und **„Wiedervorlagen“** (voreingestellt
aus). Eine Wiedervorlage steht in der Woche zu ihrer Uhrzeit, ohne
Uhrzeit im Streifen „ganztägig“, im Monat unter ihrem Tag – mit Nummer
und Notiz; ein Klick öffnet das Projekt oder den Servicefall. Gezeigt
werden nur die Wiedervorlagen, die du auch unter Planung →
Wiedervorlagen siehst (unten). Die Wahl steht in der Adresse der Seite
(`?phases=`, `?follow_ups=`) und bleibt, bis du dich abmeldest; ohne
JavaScript übernimmt „Übernehmen“ sie.

Neben dem Kalender – am Telefon darunter – steht eine **Legende**: welche
Farbe welcher Status ist und was die Zeichen bedeuten. Die Farbe ist nie
das einzige Merkmal; jeder Eintrag nennt seinen Status auch im Text, den
ein Bildschirmleser vorliest.

**Monat.** Die Projekte eines Monats, Woche für Woche, Montag zuerst. Ein
Projekt über mehrere Tage ist **ein durchgehender Balken** über seine Tage,
mit einem breiten Rand in der Farbe seines Status. Am Ende der Woche läuft
der Balken in der nächsten Zeile weiter; ein Pfeil am Rand zeigt, dass er
weitergeht oder schon vorher begann. Unter den Balken stehen die Phasen des
Tages („Aufbau · 2026-0042“) – auch eine Phase außerhalb des
Mietzeitraums, etwa der Ortstermin drei Wochen vorher. Passen an einem Tag nicht alle Projekte
hinein, steht dort **„+3“** – ein Klick öffnet die Woche, ebenso ein Klick
auf die Zahl eines Tages. „‹ Februar“ und „April ›“ blättern, „heute“
springt zurück in den laufenden Monat.

**Woche.** Ein **Stundenraster** wie in gängigen Kalender-Apps: eine Spalte
je Tag, Montag bis Sonntag, die Stunden von oben nach unten, oben
Kalenderwoche und Datum („KW 42“).

- Was einen ganzen Tag oder länger dauert, steht oben im Streifen
  **„ganztägig“**; sind es viele, zeigt „Alle ganztägigen Einträge
  zeigen“ den Rest, „Weniger zeigen“ klappt wieder zu.
- Kürzere Projekte und die **Phasen** (gestrichelt, etwa „Aufbau“) stehen
  zu ihrer Uhrzeit – so siehst du, was morgens verladen und abends
  abgebaut wird. Was gleichzeitig läuft, steht nebeneinander.
- Die Ansicht beginnt um 6 Uhr (oder beim frühesten Eintrag des Tages);
  die Nacht erreichst du durch Scrollen. Eine orange Linie zeigt die
  aktuelle Uhrzeit.
- Ein Klick auf einen Eintrag öffnet das Projekt.
- Am Telefon wischst du seitlich durch die Tage.

„‹“ und „›“ blättern wochenweise, „diese Woche“ springt zurück.

Stornierte Projekte sind in beiden Ansichten ausgeblendet; „Auch diese
zeigen“ holt sie zurück. Ein Teilprojekt heißt auf dem Balken „Bühne
Marktplatz (Stadtfest)“; der Tooltip nennt „Teil von 2026-0042
Stadtfest“.

### Zeitstrahl

Die Projekte als Balken, je Projekt eine Zeile, farbig hinterlegt in der
Farbe ihres Status wie im Kalender, die Phasen darunter gestrichelt. Gut,
um zu sehen, wo es eng wird: Was übereinander steht,
läuft gleichzeitig. Teilprojekte stehen eingerückt direkt unter ihrem
Gesamtprojekt. Eine Phase außerhalb des Mietzeitraums – Planungen und
Besprechungen Wochen vorher, die Nachbereitung danach – steht in der Zeile
ihres Projekts an ihrem Tag; das Projekt erscheint auch dann, wenn nur
diese Phase in den gezeigten Zeitraum fällt.

Oben wählst du, wie weit du blickst – genauso in der Materialauslastung
und im Personalplan:

- **„Tage“** (voreingestellt) – mit Spalten für die Stunden, wenn es auf
  die Uhrzeit ankommt: wann verladen wird, wann der Aufbau beginnt. Unter
  „Tage“ wählst du 1 bis 10 Tage, voreingestellt 4. Bei einem Tag hat jede
  Stunde ihre Spalte, bei 2 und 3 Tagen je zwei Stunden, bei 4 und 5 Tagen
  je drei, ab 6 Tagen je sechs. Ist der Bildschirm breit genug, trennen
 feine Linien jede einzelne Stunde, auch wenn eine Spalte zwei,
  drei oder sechs Stunden umfasst – sobald eine Stunde mindestens 8 Pixel
  breit ist; bei 1920 Pixeln Fensterbreite etwa bis 7 Tage, bei 1280 Pixeln
  bis 4 Tage. Die feinen Stundenlinien liegen in jeder Fensterbreite genau
  auf den Stunden – auch zwischen etwa 1236 und 1920 Pixeln.
- **„Wochen“** – Tag für Tag über einige Wochen, voreingestellt vier (in
  Materialauslastung und Personalplan zwei), unter „Wochen“ wählbar von
  einer bis zwölf.

Rentalars merkt sich bis zum Abmelden, ob du Tage oder Wochen gewählt hast
und wie viele Tage; das gilt für Zeitstrahl, Materialauslastung und
Personalplan gemeinsam. Wechselst du von „Wochen“ zu „Tage“, steht dort
die zuletzt gewählte Zahl, sonst 4.

Jeder Balken steht genau zu seiner Zeit, auch in der Ansicht „Wochen“: Ein
Aufbau von 14 bis 20 Uhr füllt nur diesen Teil des Tages, eine Phase über
Mitternacht beginnt und endet zur richtigen Uhrzeit, statt zwei ganze Tage
zu füllen. Was einen ganzen Tag dauert, füllt ihn.

„‹ früher“ und „später ›“ springen um den gezeigten Zeitraum, „diese
Woche“ bzw. „heute“ zurück; unter „Von“ wählst du den Beginn. In den
Ansichten mit Stunden reicht der Scrollbalken zwei gezeigte Zeiträume weit
in die Vergangenheit und zwei in die
Zukunft, und Rentalars lädt den nächsten oder vorigen Zeitraum
nach, sobald du seitlich ans Ende scrollst – ohne die Stelle zu verlieren.
Das gilt für Zeitstrahl, Materialauslastung, Personalplan und den
Zeitstrahl der Zeitplanung.
Die Namen bleiben dabei links stehen. Die gewählte Ansicht und Zahl der
Tage oder Wochen bleiben beim Blättern erhalten.

**Balken und Beschriftungen.** Jeder Balken hat einen Rahmen in seiner
Farbe, so dass du auch bei grauen Balken – etwa einer Anfrage – auf dem
grauen Grund siehst, wo er beginnt und endet, im dunklen wie im hellen
Modus; ebenso Phasen, Abwesenheiten, Sperrzeiten und die Verfügbarkeit.
Stornierte Projekte sind blass und durchgestrichen. Passt die Beschriftung
nicht in den Balken, endet sie mit „…“, statt über den nächsten Balken zu
laufen; fährst du mit der Maus darüber, steht der ganze Text im Tooltip.
Das gilt für alle Zeitstrahlen – hier, im Personalplan, an Produkten,
Modellen, Exemplaren und Personen und in der Zeitplanung eines Projekts.

### Termine im Zeitstrahl verschieben

Der Aufbau beginnt zwei Stunden später, die Abholung rückt einen Tag nach
vorn: In der Ansicht **„Tage“** von Planung → Zeitstrahl und im
Zeitstrahl der Zeitplanung eines Projekts (Abschnitt 7) ziehst du einen
Balken mit der Maus an seine neue Zeit:

- **den Balken selbst** – er wandert mit seiner Länge;
- **eines seiner Enden** – das ändert nur Beginn oder Ende.

Verschieben lassen sich der **Mietzeitraum**, jede **Phase** und – in der
Zeitplanung – die **Veranstaltung**, dort auch die **Einsätze
der Personen** und die **offenen Plätze**. Die Zeiten rasten in Schritten von
15 Minuten ein; ein gestrichelter Rahmen zeigt beim Ziehen die neuen
Zeiten. Ein Ende, das außerhalb der gezeigten Spalten liegt, hat keinen
Griff – blättere oder wähle mehr Tage.

**Mit der Tastatur:** den Balken mit Tab wählen, **←** und **→**
verschieben ihn um 15 Minuten, mit **Umschalt** nur sein Ende; Rentalars
sagt die neuen Zeiten an. **Enter** zeigt die Folgen, **Escape** nimmt die
Verschiebung zurück. **In der Zeitplanung** öffnet auch ein Klick auf einen
Balken dasselbe Fenster, in dem du die Zeiten eintippst; in Planung →
Zeitstrahl führt ein Klick zum Projekt. Am Telefon zieht man
nicht – ein Finger scrollt den Zeitstrahl; tippe in der Zeitplanung auf
den Balken.

**Erst das Fenster speichert.** Nach dem Loslassen öffnet sich „…
verschieben“ mit **„Bisher“** und **„Neu“** und darunter, was dann
passiert – Rentalars probiert die Verschiebung dafür einmal aus, ohne
etwas zu speichern oder zu verschicken:

- welche Personalpositionen mitziehen und wer **neu angefragt** wird
  (Abschnitt 12, „Anfragen: Zusage oder Absage“), und ob jemand zur neuen
  Zeit schon anderswo eingeplant ist;
- bei einer Phase, die danach außerhalb des Mietzeitraums liegt, der Haken
  **„Mietzeitraum auf … erweitern“** (nicht angehakt) mit der Vorschau,
  ob dann Material fehlt – ohne Haken verschiebt sich nur die Phase;
- beim Mietzeitraum, wie viele Positionen den neuen übernehmen, welche
  Teilprojekte mitziehen und ob danach **Material fehlt** („Mit dem neuen
  Mietzeitraum fehlen 2 Stück.“);
- beim Einsatz einer Person in der Zeitplanung die geplanten
  Stunden vorher und nachher, ob sie neu angefragt wird, und – wenn sie
  die einzige ihrer Phase ist – der angehakte Kasten **„Phase „…“
  mitverschieben“**, sonst gegebenenfalls **„Offene Plätze als …
  mitverschieben“**, jeweils mit dem Grund; ohne den Haken wird nur der
  Einsatz verschoben (Abschnitt 7, „Personen im Zeitstrahl ziehen“).

Ziehst du den **ganzen Mietzeitraum** (mit gleicher Länge), ist
**„Veranstaltung, Phasen und Personal mitverschieben“** angehakt – damit wandern auch die Fahrzeugbuchungen der Logistik (Abschnitt 7,
„Logistik“). Nimm den Haken weg, wenn nur der Mietzeitraum wandern soll;
Fahrzeugbuchungen mit dem Zeitraum des Projekts folgen ihm trotzdem. Änderst du nur ein Ende
des Mietzeitraums, ändert sich nur dieser. Wer im Projekt eingeplant ist,
erfährt vom neuen Mietzeitraum – jede Person **einmal**: Wer
eigene Einsätze mitverschoben bekommt, erhält eine Nachricht mit allen
geänderten Einsätzen (Abschnitt 12, „Nachrichten über den Einsatz“) und
dann nicht zusätzlich „neuer Zeitraum …“; die übrige Crew bekommt nur
diese. **„Verschieben“** speichert, „Abbrechen“
lässt alles, wie es war; danach lädt die Seite neu und steht wieder auf
dem Balken.

Verschieben kann, wer das Projekt bearbeiten darf, und nur, solange es
nicht abgeschlossen ist. Phasen der Art „Planungen und Besprechungen“
fragen nie nach dem Mietzeitraum (Abschnitt 7, „Phase außerhalb des
Mietzeitraums“). Einsätze einzelner Personen ziehst du genauso
im Personalplan (unten, „Personalplan“) – dort geht nie etwas mit – und
 im Zeitstrahl der Zeitplanung, wo Phase oder offene Plätze
mitgehen können.

### Materialauslastung

Wie viel von einem Produkt reserviert ist: Kategorie wählen oder nach Name oder Artikelnummer
suchen. Schon beim Tippen schlägt Rentalars passende Produkte mit Bestand
vor; wähle eines per Klick oder mit den Pfeiltasten und Enter, dann zeigt
die Seite genau dieses Produkt. Schließt du die Vorschläge mit Esc und
drückst Enter, zeigt sie alle Produkte, deren Name oder Artikelnummer den
Text enthält. Wählst du danach eine Kategorie, zeigt sie wieder die ganze
Kategorie.

Die Zeit-Ansicht ist dieselbe wie im Zeitstrahl und im Personalplan:
zuerst 4 Tage in Stunden-Spalten, mit „Tage“ 1 bis 10 Tage, mit „Wochen“
eine bis zwölf Wochen Tag für Tag (oben, „Zeitstrahl“).

Je Spalte – Stunden oder Tag – steht, wie viele Stück in dieser Zeit
höchstens fest reserviert sind, mit „+2“ dazu, was Optionen zusätzlich
vormerken. Nebeneinanderliegende Spalten mit denselben Zahlen sind zu
einem Feld zusammengefasst; fährst du mit der Maus darüber, siehst du den
Zeitraum. Die Farbe sagt, wie eng es ist:

| Farbe | Bedeutung |
|---|---|
| grün | reserviert, es ist noch Luft |
| gelb | 80 % und mehr, oder Optionen über den Bestand hinaus |
| rot | mehr reserviert, als da ist |

**Sets** stehen mit in der Liste. Ihre Zeile zählt komplette
Sets: wie viele **frei** sind, klein daneben mit „−2“, was Optionen davon
noch nehmen würden – so wie der Zeitstrahl eines Produkts. Unter dem Namen
steht, wie viele komplette Sets es gibt. Der Pfeil vor dem Namen klappt die
Bestandteile auf, je mit „2 ×“ – so viele Stück braucht ein Set – und
ihrer eigenen Auslastung; so siehst du, welcher Bestandteil knapp wird.
Das geht auch ohne JavaScript.

Auf der Seite eines Produkts führt „In der Materialauslastung zeigen“
direkt hierher, mit dem Produkt und dem gewählten Zeitraum (Abschnitt 5,
„Bestand und Verfügbarkeit eines Produkts“).

Gerechnet wird genauso wie überall (Abschnitt 9) – über alle Projekte,
auch die, die du sonst nicht öffnen kannst. Deshalb gibt es die Seite nur
für Projektrechte, die für alle Projekte gelten, und nur mit
dem Sonderrecht „Verfügbarkeit von Material sehen“. Fahrzeuge und Anhänger
stehen nicht hier, sondern unter Materialverwaltung → Fuhrpark →
„Auslastung des Fuhrparks“ (Abschnitt 4, „Fuhrpark“).

### Fehlbestände

Die Seite aus Abschnitt 9, „Die Seite ‚Fehlbestände‘“.

### Personalplan

Jede Person eine Zeile, zuerst über 4 Tage mit Stundenspalten, wie beim
Zeitstrahl über 1 bis 10 Tage oder über ein bis zwölf Wochen; Einsätze,
Verfügbarkeit und Abwesenheiten stehen genau zu ihrer Uhrzeit. Jede Zeile
hat zwei Streifen:

- **oben die Verfügbarkeit:** was die Person in ihrem
  Verfügbarkeitskalender eingetragen hat – alle **schraffiert**,
  damit klar ist, dass es Verfügbarkeiten sind: grün verfügbar, gelb
  eingeschränkt, rot nicht verfügbar, auch belegte Zeiten aus ihren
  verknüpften Kalendern (Abschnitt 12) – und grau schraffiert ihre
  **Abwesenheiten**;
- **darunter die Einsätze** als Balken (Projektnummer und Funktion),
  farbig hinterlegt und mit einem breiten Farbstreifen links: **orange**
  fest (das Projekt ist bestätigt – auch unterwegs, wieder im Lager oder
  abgeschlossen), **gelb**
  Option, **grau** Projekt-Anfrage. Ist die Person **angefragt** und hat
  noch nicht geantwortet, ist der Balken blasser und der Streifen
  gestrichelt. Ein Klick öffnet das Projekt. Bei einem Teilprojekt nennt
  der Tooltip auch das Gesamtprojekt („Bühne Marktplatz (Stadtfest)“).

**Genaue Zeiten.** Fährst du mit der Maus über einen Balken – Einsatz,
Verfügbarkeit oder Abwesenheit –, nennt er die genauen Zeiten, etwa „Mi
10.03., 9:00 Uhr bis 13:30 Uhr“, „… bis 24:00 Uhr“ oder „Mi 10.03.,
ganztägig“. Ein Bildschirmleser liest dasselbe vor.

Ist jemand **doppelt eingeplant**, **während einer Abwesenheit** oder
**trotz „nicht verfügbar“** eingeplant, steht ein rotes **!** am Namen, und
 ist der betroffene **Einsatz rot ausgefüllt** – sonst ist keine
Art im Plan rot ausgefüllt, so fällt es sofort auf und ist von „nicht
verfügbar“ (rot schraffiert) gut zu unterscheiden. Der farbige Streifen am
Anfang des Balkens behält die Farbe von fest, Option oder Anfrage.
Verfügbarkeiten und Abwesenheiten werden nicht ausgefüllt; ihr Hover nennt
„Konflikt“. Verglichen werden die echten Uhrzeiten: Ein Einsatz morgens und
einer abends am selben Tag sind keine Doppelbelegung. „Eingeschränkt“ ist
sichtbar, aber keine Warnung. Die Legende unter dem Plan erklärt die
Farben. Dieselbe rote Füllung zeigen die Woche des Verfügbarkeitskalenders
und der Zeitstrahl einer Person (Abschnitt 12).

**Einsätze verschieben**. In der Ansicht **„Tage“** ziehst du
einen Einsatz wie die Phasen im Zeitstrahl (oben, „Termine im Zeitstrahl
verschieben“) an eine andere Zeit, oder an einem Ende länger oder kürzer –
in Schritten von 15 Minuten, mit der Tastatur mit ← und → (mit Umschalt
nur das Ende). Das Fenster zeigt vorher alte und neue Zeiten, die
geplanten Stunden vorher und nachher, ob die Person neu angefragt wird und
ob es zu den neuen Zeiten Überschneidungen gibt. Erst **„Verschieben“**
speichert – wie eine Änderung im Dialog der Personalposition: Die
geplanten Stunden ziehen mit, wenn sie die vorgeschlagenen waren, und wer
angefragt war oder zugesagt hat, wird neu angefragt (sofern so
eingestellt). Die Phase und das Projekt behalten ihre Zeiten – dass sie
mitgehen, gibt es nur im Zeitstrahl der Zeitplanung (Abschnitt
7, „Personen im Zeitstrahl ziehen“). Verschieben
kann, wer das Projekt bearbeiten darf, solange es nicht abgeschlossen ist;
auf eine andere Person ziehen lässt sich ein Einsatz nicht.

Im Plan stehen alle aktiven Personen – auch Büro-Konten ohne Funktion. Mit
dem Haken **„Nur Personen mit Einsätzen oder Abwesenheiten“** bleiben nur
die, die im gezeigten Zeitraum eingeplant oder abwesend sind.

### Wiedervorlagen

**Wiedervorlagen** ist der letzte Reiter der Planung – für alle,
die Projekte lesen dürfen. Er zeigt alle Projekte und Servicefälle mit
einer Wiedervorlage (Abschnitt 7, „Wiedervorlage“) als Tabelle:
**Tag**, **Uhrzeit**, **Für**, **Notiz**, **Projekt**, **Art** (Projekt
oder Servicefall) und **Status**; „Kunde“ und „Zuständig“ blendest du
unter „Spalten“ ein. Filtern lässt sich nach „Für“ (alle oder für mich),
**„Nur fällige“**, **„Auch Zurückgestellte“** (zurückgestellte
Servicefälle, deren Wiedervorlage noch nicht fällig ist; ohne den Haken
fehlen sie) und einem Zeitraum (Von, Bis). Wie jede Liste lässt sie
sich sortieren, nach Tag, Für oder Art gruppieren und als CSV laden
(Abschnitt 2, „Listen“).

**„Verschieben“** öffnet den Dialog der Wiedervorlage, in dem du Tag,
Uhrzeit, Person oder Notiz änderst, und kehrt danach zur Tabelle zurück;
**„Erledigt“** nimmt die Wiedervorlage vom Projekt – wie im Projekt
selbst. Beides steht nur bei Projekten, die du bearbeiten darfst.

Wer die Kunden sehen darf, sieht hier die Wiedervorlagen aller Projekte,
die er sehen darf; wer nicht – etwa die Crew –, nur die eigenen. „Alle
meine Wiedervorlagen“ auf der Startseite führt hierher, schon auf „für
mich“ gefiltert.

### Benachrichtigungen

Die **Glocke** zeigt, wie viele ungelesene Benachrichtigungen du hast; ein
Klick führt zur Liste. Eine Benachrichtigung öffnen bringt dich dorthin, wo
etwas geschehen ist, und markiert sie als gelesen. „Alle als gelesen
markieren“ räumt auf.

Worüber Rentalars benachrichtigt – jeweils nur, was dich angeht und was
du sehen darfst. Jede Art gehört zu einer **Kategorie**:
**Projekt** (was in Projekten und Servicefällen geschieht), **Personal**
(was dich als Mitarbeiter angeht), **Material** (das Lager) und **System**
(der Betrieb der Installation). In dieser Reihenfolge stehen sie auch in
den Einstellungen:

| Art | Wer | per E-Mail voreingestellt | in der App voreingestellt |
|---|---|---|---|
| **Projekt** | | | |
| Einsatzanfrage – bei Antworten per Mail als Mail mit den Knöpfen „Zusagen“ und „Absagen“; nach geänderten Zeiten als neue Anfrage mit alten und neuen Zeiten (Abschnitt 12) | die angefragte Person | ja | ja |
| Antwort auf eine Einsatzanfrage | wer gefragt hat, die Projektleitung | ja | nein |
| Preisangebot einer freien Kraft – nur wenn die Funktion eingeschaltet ist (Abschnitt 12, „Preisangebote freier Kräfte“) | wer das Sonderrecht „Stundensätze und Personalkosten sehen“ hat und das Projekt lesen darf | ja | nein |
| Antwort auf mein Preisangebot – angenommen, abgelehnt oder Gegenangebot | die freie Kraft | ja | nein |
| Änderung meines Einsatzes – fest eingeplant, Zeiten, Treffpunkt, Notiz, Phase, Funktion oder Fahrzeug geändert (mit dem Wert vorher), ausgeplant; eine Nachricht je Aktion (Abschnitt 12, „Nachrichten über den Einsatz“) | die eingeplante Person | ja | ja |
| Im Chat eines Projekts erwähnt (Abschnitt 7, „Chat im Projekt“) | wer mit @ erwähnt wurde | ja | ja |
| Wiedervorlage eines Projekts – am Tag, ab 6 Uhr oder ab ihrer Uhrzeit (Abschnitt 7, „Wiedervorlage“) | für wen die Wiedervorlage ist; ist die Person deaktiviert, die Projektleitung | ja | ja |
| neue Mail zu einem Projekt – auch ein Servicefall, der gleich aus einer Mail entstand; auch „Neue Nachricht für die Crew von …“, wenn jemand das Schloss einer Nachricht entfernt (Abschnitt 14, „Nachrichten mit Schloss“) | die Projektleitung; beim neuen Servicefall, wer für die Adresse verantwortlich ist – nur, wer die Nachricht lesen darf; beim entfernten Schloss die eingeplante Crew, die zugesagt hat oder fest eingeplant ist | ja | nein |
| Änderung an einem Projekt (Status, Zeitraum) – auch, dass ein Servicefall jetzt bei dir liegt oder dass du an einem beteiligt bist | die Projektleitung und Mitglieder mit „Bearbeiten“; bei neuem Zeitraum oder Stornierung auch die eingeplante Crew; bei einem Servicefall, wer neu zuständig oder beteiligt ist | nein | nein |
| neuer Fehlbestand – wann und wie weit voraus, legt Einstellungen → Benachrichtigungen fest (voreingestellt täglich, vier Wochen); voreingestellt auch die Erinnerung an bekannte Fehlbestände, eine je Projekt („Weiterhin Fehlbestände in …“) | die Projektleitung – nur mit dem Sonderrecht „Verfügbarkeit von Material sehen“ | ja | nein |
| Rechnung noch zu schreiben – für ein abgeschlossenes Projekt ohne Rechnung, voreingestellt auch für einen erledigten Servicefall (Abschnitt 11, „Noch zu schreibende Rechnungen“) | die Projektleitung und wen Einstellungen → Benachrichtigungen unter „Außerdem erinnern“ nennt – nur, wer Preise sehen darf | ja | nein |
| Meldung einer Automation (Abschnitt 16, „Automationen“) | wen die Automation nennt | ja | nein |
| **Personal** | | | |
| Meine Spesen zurückgegeben oder erstattet (Abschnitt 13) | die Person, deren Spesen es sind | ja | nein |
| Meine Zeiten freigegeben, korrigiert oder zurückgegeben – mit den Werten vorher bzw. dem Grund (Abschnitt 13, „Einreichen und freigeben“) | die Person, deren Zeiten es sind | ja | nein |
| Zeiten warten auf meine Freigabe – zur Uhrzeit unter Einstellungen → Benachrichtigungen (Abschnitt 13) | wer sie freigeben darf, nie für die eigenen | ja | nein |
| Nachweis läuft ab – 60 Tage vorher | die Personaldisposition und die Person selbst | ja | nein |
| **Material** | | | |
| Defekt gemeldet | das Lager | ja | nein |
| Bestand unter dem Mindestbestand | das Lager | ja | nein |
| Fällige Prüfungen – einmal am Tag, gesammelt | das Lager | ja | nein |
| **System** | | | |
| Eine Aufgabe im Hintergrund ist fertig (z. B. KI-Zusammenfassung, Antwortentwurf, Rechnung lesen, Export) – so heißt sie in den Einstellungen, als erste Art unter „System“; auch eine Übergabe an Lexware Office; auch „Video für den Chat von … fehlgeschlagen“ | wer sie gestartet hat; bei der sofortigen Übergabe einer neuen Rechnung nur, wenn sie scheitert, an den, der die Rechnung erstellt hat; beim Video, wer es geschickt hat | nein | nein |
| Problem beim Abruf der Mails – mit dem Namen des Postfachs | die Administratoren | ja | nein |
| Problem mit meinem Kalender | die Person selbst, wenn einer ihrer verknüpften Kalender (mit seinem Namen) oder ihr CalDAV-Kalender länger nicht klappt | ja | nein |
| Fehler der Anwendung – auch: Webhook abgeschaltet (Abschnitt 16, „Webhooks“) | die Administratoren (beim Webhook alle, die die Einstellungen ändern dürfen) | ja | nein |

„Das Lager“ heißt: alle, die Material ändern dürfen; „die
Personaldisposition“: alle, die Personal ändern dürfen.

Wie du benachrichtigt wirst, stellst du unter **Mein Konto →
Benachrichtigungen** je Art ein, nach Kategorien geordnet, in drei
Spalten:

- **„In Rentalars“** – an der Glocke und in der Liste;
- **„Per E-Mail“** – zusätzlich als Mail;
- **„In der App“** – die Companion-App für Android zeigt die
  Benachrichtigung auf deinem Telefon (Abschnitt 2, „Die Rentalars-App für
  Android“). Voreingestellt ist das für Einsatzanfragen, Erwähnungen im
  Chat und Wiedervorlagen – das, was dich direkt angeht und eine schnelle
  Antwort will – und für Änderungen deines Einsatzes, die du
  unterwegs brauchst.

Willst du eine Art nur in der App, steht sie in Rentalars gleich als
gelesen da – wie bei „nur per E-Mail“. Sind alle drei Spalten aus, gibt es
für diese Art keine Benachrichtigung. Ausnahmslos
jede Art lässt sich so einstellen – auch, ob dir Rentalars Bescheid gibt, wenn die
KI eine Zusammenfassung, einen Antwortentwurf oder das Lesen einer
Rechnung fertig hat: Das ist „Eine Aufgabe im Hintergrund ist fertig (z. B.
KI-Zusammenfassung, Antwortentwurf, Rechnung lesen, Export)“, die erste
Art unter „System“. Die Einstellung gab es schon vorher, nur ohne die KI
im Namen und als letzte Art unter „System“. Die **Liste der Benachrichtigungen**
ist eine Tabelle wie jede Liste; unter „Filter“ wählst du auch eine
Kategorie. Der Text einer Benachrichtigung steht dort und in
der CSV-Datei als reiner Text mit seinen Zeilenumbrüchen; ebenso die Beschreibung einer
Projektvorlage in ihrer Liste. HTML-Tags fallen dabei weg, und
Schreibweisen wie `&amp;` werden wieder zu „&“; ein Text in spitzen
Klammern, der kein Tag ist, bleibt stehen, etwa
`Max <max@example.org>`. Ohne E-Mail-Adresse am
Konto gibt es keine Mails. Was du selbst ausgelöst hast, meldet
Rentalars dir nicht – außer dass eine Aufgabe im Hintergrund fertig ist.
Jede Benachrichtigung per E-Mail endet mit dem Hinweis, dass Rentalars sie
für eure Firma verschickt hat, und der Adresse eurer Installation
(Abschnitt 14, „Signatur“).

Benachrichtigungen bleiben 180 Tage und verschwinden dann von selbst; die
Frist steht in den Einstellungen (Abschnitt 16, „Aufbewahrungsfristen“).

---

## 16. Einstellungen

*Für Administratoren.*

Die Seite **Einstellungen** gliedert sich in Kästen nach
Themen:

| Kasten | Darin |
|---|---|
| **Firma** | Firmendaten und Grundeinstellungen (mit dem Stand des Routendienstes), Nummernkreise, Etiketten (Abschnitt 4, „Etiketten“) |
| **Nutzer und Rechte** | Nutzer, Rollen und das Verzeichnis (LDAP) |
| **Abläufe** | Automationen, Benachrichtigungen, KI (mit den automatischen Zusammenfassungen) |
| **Projekte und Personal** | Zuschläge, die Preisangebote freier Kräfte (Abschnitt 12, „Preisangebote freier Kräfte“), Staffeln (Abschnitt 5) und – mit Zugriff auf das Personal – Funktionen (Abschnitt 12) |
| **E-Mail** | Postfächer und Signatur, Mail-Protokoll (Abschnitt 14) |
| **Dokumente und Buchhaltung** | Dokumentvorlagen, „Vorlagentexte auf Englisch oder Deutsch“ (Abschnitt 11), Textbausteine und – mit dem Recht, Preise zu sehen – Buchhaltung, die Eingangsrechnungen (Grenze für GWG und Nutzungsdauer; Abschnitt 11, „Eingangsrechnungen“) |
| **Stammdaten** | Kategorien und Kürzel, Eigene Felder und Feldsätze (Abschnitt 4, „Eigene Felder“), Steuerarten, Einheiten, Hersteller, Händler, Lagerorte, Dokumentarten, Prüfarten, Audits (Abschnitt 4, „Audits und To-Dos“), Qualifikationsarten |
| **Import und Export** | die Importe, die du starten darfst, und je Import der „Export im Importformat“ für alle, die die Liste lesen dürfen; der vollständige Export steht unter „Sicherung“ |
| **Schnittstelle für andere Programme** | API-Dokumentation – sie öffnet in einem neuen Tab –, „Meine API-Token“, Webhooks |
| **Betrieb und Sicherheit** | Selbsttest, Sicherung (mit dem „Lesbaren Export aller Daten“), Verschlüsselung, Serveradresse und Zertifikat, Änderungsprotokoll, Sicherheitsprotokoll, Zugriffsprotokoll |

Was du nicht sehen darfst, fehlt auch hier – etwa der Kasten „E-Mail“ ohne
das Modul E-Mail.

### Nutzer

**Personal und Nutzer sind eins.** Jede Person im Personal hat eine
Anmeldung, und jedes Konto ist eine Person (Abschnitt 12, „Personen“).
Meist legst du deshalb eine **Person** an (Personal → Neue Person); ihr
Konto entsteht dabei mit der Rolle Crew bzw. Freie Kraft. Hier, unter
**Einstellungen → Nutzer**, vergibst du Rollen und Rechte und hilfst beim
Anmelden. Vorname, Nachname, E-Mail-Adresse und „aktiv“ ändern sich an
beiden Stellen zugleich.

**Einstellungen → Nutzer → Nutzer einladen** geht auch: Benutzername,
E-Mail-Adresse, Name, **Sprache**, Rollen, „Einladung senden“. Das Konto
steht danach auch im Personal. Die Sprache – „Wie die Installation“,
Deutsch oder English – legt fest, wie Rentalars mit der Person spricht;
die Einladung geht gleich in dieser Sprache hinaus, und die Person kann
sie später unter Mein Konto selbst ändern (Abschnitt 2). Der neue Nutzer
bekommt eine E-Mail mit einem Link und
setzt sein Passwort selbst – du erfährst es nie. Der Link gilt 72 Stunden;
auf der Seite des Nutzers schickt „Link zum Setzen des Passworts senden“
einen neuen. Ohne E-Mail-Adresse gibt es keine Einladung – dann das
Einmal-Passwort (gleich unten). Ist kein Mailserver eingerichtet, geht die
Einladung nicht hinaus: Die Seite sagt „Nicht versendet – kein Mailserver
eingerichtet.“, führt dich zur Seite des Nutzers, damit du ein
Einmal-Passwort festlegen kannst, und verlinkt Einstellungen → Postfächer
und Signatur (Abschnitt 14, „Ohne Mailserver“).

**Einmal-Passwort.** Für Personen ohne E-Mail-Adresse, oder wenn die
Einladung nicht ankommt: Auf der Seite des Nutzers **„Einmal-Passwort
festlegen“**. Nach einer Rückfrage zeigt Rentalars ein Passwort aus vier
Gruppen von Buchstaben und Ziffern – **nur dieses eine Mal**. Gib es der
Person persönlich oder am Telefon, nicht per E-Mail. Bei der nächsten
Anmeldung muss sie zuerst ein eigenes Passwort wählen („Wähle dein
Passwort“); bis dahin kommt sie an nichts anderes heran, auch nicht über
die API. Ein bisheriges Passwort gilt ab dem Festlegen nicht mehr. Das
Sicherheitsprotokoll hält fest, wer wann ein Einmal-Passwort festgelegt
hat. Für deaktivierte Konten geht es nicht.

Auf der Seite der Person zeigt „Anmeldung“, ob jemand schon ein Passwort
hat und wann er sich zuletzt angemeldet hat (Abschnitt 12).

**Gültig bis.** Für Aushilfen, die nur einmal gebucht sind: Trage beim
Konto ein Datum ein. Nach diesem Tag wird das Konto von selbst deaktiviert.

Nutzer werden hier nicht gelöscht, sondern **deaktiviert** („Nutzer
deaktivieren“ auf seiner Seite): Der Verlauf soll weiterhin zeigen, wer
etwas getan hat. Ein deaktivierter Nutzer kann sich nicht mehr anmelden,
ist als Person nicht mehr planbar und lässt sich jederzeit wieder
aktivieren. Eine Person, die sich nie angemeldet hat und nie eingeplant
war, lässt sich samt Konto im Personal löschen (Abschnitt 12).

„Hat alle Rechte“ ist ein Notzugang, der von Rollen unabhängig ist. Vergib
ihn sparsam – der erste Administrator hat ihn. Ein Konto mit diesem Recht
lässt sich nicht anonymisieren.

**Datenzugriff auf einen Blick**. Die Liste der Nutzer hat –
wie Personal → Personen – die wählbaren Spalten „Finanzen“,
„Personaldaten“ und „Kundendaten“, aus den Rollen jedes Kontos berechnet;
„kein Zugang“ heißt, das Konto kann sich nicht anmelden (Abschnitt 12,
„Personen“).

### Rollen und Rechte

Eine **Rolle** bündelt Rechte; ein Nutzer kann mehrere Rollen haben. Dann
zählt je Modul das höchste Recht.

**Je Modul** gibt es vier Stufen, jede schließt die vorigen ein:

| Stufe | Darf |
|---|---|
| kein Zugriff | das Modul erscheint nicht |
| lesen | ansehen |
| anlegen und bearbeiten | ändern |
| löschen | auch löschen |

Module sind: Material, Produkte, Kunden, Projekte, Packen und Ausgabe,
Personal, Zeiterfassung, E-Mail, Einstellungen und Auswertungen. Die Auswertungen (Abschnitt 8) sieht, wer dieses Modul
lesen, dazu alle Projekte lesen und Preise sehen darf; die Rollen
Administrator, Projektleitung und Nur-Lesen haben es von Anfang an. Das Modul **E-Mail** umfasst die Anfragen unter Projekte
(lesen; übernehmen und von Hand notieren mit „bearbeiten“), die Postfächer
und die Regeln für alle Postfächer („bearbeiten“; Postfächer löschen mit
„löschen“). Wer nur das Modul E-Mail hat, sieht in der Seitenleiste
„Projekte“ mit den Anfragen. Die Signaturen – die gemeinsame und die der
Postfächer – ändert, wer die Einstellungen bearbeiten darf; das
Mail-Protokoll sieht, wer die Einstellungen lesen darf. Mit welcher
Adresse jemand Mails aus Projekten senden darf, legen die Rollen unter
„Als Absender wählbar für“ an jedem Postfach fest (Abschnitt 14).
Die **Logistik** eines Projekts plant, wer es bearbeiten darf – oder es
lesen und Material bearbeiten darf (Abschnitt 7, „Logistik“). Die
**Monatsabrechnung** der Servicefälle sieht, wer Projekte lesen, Preise
und Kunden sehen und jeden ihrer Fälle lesen darf; ändern darf sie, wer
Projekte und jeden ihrer Fälle bearbeiten darf, einen Entwurf löschen, wer
in Projekten löschen darf (Abschnitt 7, „Monatsabrechnung“). Die
**Ausgangsbelege** sieht, wer Preise sehen und alle Projekte
lesen darf; der Menüpunkt **Buchhaltung** erscheint, wenn man eines von
beidem sehen darf (Abschnitt 11, „Ausgangsbelege“). Die Mails
in den Projekten hängen an den Sonderrechten für Korrespondenz. Zuschläge
und Automationen gehören zum Modul **Einstellungen**: lesen zum Ansehen,
bearbeiten zum Ändern – bei Automationen auch zum Löschen.

**Projektzugriff.** Je Rolle stellst du ein, ob ihre Rechte auf Projekte
und Packlisten für **alle Projekte** gelten oder **nur für zugeordnete** –
auch **„nur zugeordnete Projekte, Überblick ohne Planung“**:
Dann öffnet die Rolle in ihren Projekten nur Überblick, Packliste und
Chat, nie Planung, Zeitplanung, Zugriff, Verlauf, offene Punkte oder
Fehlbestände – gleich, was eine Mitgliedschaft sagt. Der Hinweis unter dem
Feld erklärt es. Was das bedeutet und wie man zugeordnet wird, steht in
Abschnitt 12, „Wer welches Projekt sieht“. Servicefälle, für die jemand
zuständig ist oder an denen er beteiligt ist, bearbeitet er unabhängig
davon (Abschnitt 7, „Mitarbeit am Fall“).

**Sonderrechte** werden unabhängig davon vergeben:

| Sonderrecht | Wofür |
|---|---|
| Preise und Kalkulation sehen | Preisspalten, Summen, Preisübersicht, Preise ändern, alte Preise übernehmen; Angebot, Auftragsbestätigung, Rechnung und Stornorechnung sehen und erstellen, Rechnungen an Lexware Office übergeben; mit Zugriff auf die Einstellungen die Seite Buchhaltung; Standardrabatt der Kunden und höchster Rabatt der Funktionen und Produkte; Zuschläge im Preis an Personalpositionen und Dienstleistungen; die Monatsabrechnung der Servicefälle; Sätze, Abrechnung und Rabatte der Fahrzeuge und ihrer Buchungen und was auf einer Fahrt berechnet wird; Einnahmen und Summen in der Projektliste; mit dem Modul Auswertungen und Lesezugriff auf alle Projekte die Auswertungen; den Stand der Rechnung eines Projekts und die Erinnerungen daran; Preise und Rabatte importieren; die Nachrichten der Korrespondenz mit Schloss lesen und – mit „Korrespondenz schreiben und senden“ – das Schloss setzen und entfernen |
| Einkaufs- und Kaufpreise sehen | Kaufpreise am Material, Einkaufspreise von Zumietungen, interne Kosten der Fahrzeuge und was zugemietete kosten, Gewinn aus dem Projekt (mit den beiden anderen Rechten dazu), Material- und Logistikkosten in der Projektliste; der Anteil am Kaufpreis im Kasten „Ertrag“ eines Exemplars und eines Modells und der Reiter „Material“ der Auswertungen; die Werte vertraulicher eigener Felder |
| Abgeschlossene Projekte wieder öffnen | |
| Verwendete Artikelnummern ändern | |
| Staffeln bearbeiten | |
| Stundensätze und Personalkosten sehen | Stunden- und Tagessätze an Personen, Funktionen (Richtwerte), Positionen und Zeiten; Funktionen mit eigenen Sätzen zuordnen und entfernen; Zuschläge in den Kosten an Personalpositionen; Personalkosten, freigegebene Spesen und Gewinn aus dem Projekt, auch in der Preisübersicht je Phase und in der Projektliste; Sätze importieren |
| Zeiten freigeben und für andere erfassen | Reiter „Freigeben“ und „Spesen“, Zeiten und Spesen anderer sehen und erfassen, Spesen als erstattet markieren |
| Personen außerhalb ihrer Funktionen einplanen | Ausnahme von der Regel, dass jemand nur in seinen Funktionen eingeplant wird; die übrigen Personen erscheinen gekennzeichnet in der Auswahl |
| Verfügbarkeit von Material sehen | die Ampeln in Planung und Positionsdialog und die Hinweise auf fehlendes Material, der Kasten „Verfügbarkeit“ auf der Seite eines Produkts, die Zeitstrahlen von Produkten, Modellen und Exemplaren, die Materialauslastung, die Fehlbestände – Seite, Startseite, offene Punkte, Benachrichtigungen –, die Kalender-Links von Produkten, Modellen und Exemplaren (zusammen mit dem Lesen aller Projekte; Abschnitt 4, „Kalender-Link“) und dasselbe über die Schnittstelle. Nicht: den Bestand eines Produkts und den Fuhrpark |
| Korrespondenz lesen | die Mails der Projekte, die man lesen darf (Abschnitt 14) – die mit Schloss nur zusammen mit „Preise und Kalkulation sehen“ |
| Korrespondenz schreiben und senden | Mails aus dem Projekt schreiben und beantworten, Dokumente senden; mit „Projekte löschen“ auch Mails entfernen |

So kann das Lager Material pflegen und packen, ohne zu sehen, was ein
Projekt kostet.

**Dokumente** (Abschnitt 11) erstellt, wer das Projekt bearbeiten darf;
für Angebot, Auftragsbestätigung und Rechnung braucht es zusätzlich
„Preise und Kalkulation sehen“. Lieferschein und Crew-Disposition sieht
jeder, der die Planung des Projekts lesen darf – auch das Lager.

**Mitgelieferte Rollen** – Vorschläge, die du ändern und ergänzen kannst:

| Rolle | Gedacht für | Kurz |
|---|---|---|
| Administrator | Nutzer, Rechte, Stammdaten, Einstellungen | alles |
| Projektleitung | Projekte anlegen, disponieren, kalkulieren | Projekte „anlegen und bearbeiten“ (nicht löschen); Kunden bearbeiten; **Produkte lesen**; Material lesen; Preise und Einkaufspreise |
| Lager | Material pflegen, packen, ausgeben, zurücknehmen | Material „anlegen und bearbeiten“ (nicht löschen); Packen; Projekte und Produkte lesen; Kaufpreise, aber **keine** Mietpreise; Korrespondenz lesen |
| Nur-Lesen | Buchhaltung, Geschäftsführung | alles lesen, mit Preisen; nichts ändern |
| Personaldisposition | Personalplanung | Personal und Zeiterfassung voll; Projekte lesen und darin Personal einplanen; Stunden- und Tagessätze; Zeiten freigeben |
| Crew | eigene Einsätze, Packliste abarbeiten, eigene Zeiten; jede neue Person bekommt Crew oder Freie Kraft | Projekte lesen, Packen „anlegen und bearbeiten“ – **nur zugeordnete Projekte, Überblick ohne Planung**; Zeiten erfassen; kein Material nachtragen; keine Preise; keine Verfügbarkeit des Materials; Korrespondenz lesen |
| Freie Kraft | „Nur das Wichtigste: Eigene Einsätze und die Stundenerfassung, keine Projektinfos“ | Projekte und Packlisten lesen – **nur zugeordnete Projekte, Überblick ohne Planung**; Zeiten erfassen; keine Preise, **keine Verfügbarkeit des Materials**, keine Sonderrechte |

Die Projektleitung hat zusätzlich die Sonderrechte für
Stundensätze, Freigabe und das Einplanen außerhalb der Funktionen; die
Rechte für E-Mail und Korrespondenz hat sie, Nur-Lesen das
Lesen.

**Standardrechte der Rollen.** Vier Rollen haben besondere Rechte
(Tabelle oben): **Freie Kraft** – die Beschreibung „Nur
das Wichtigste: Eigene Einsätze und die Stundenerfassung, keine
Projektinfos“, ohne das Sonderrecht „Verfügbarkeit von Material sehen“ und
mit dem Projektzugriff „nur zugeordnete Projekte, Überblick ohne
Planung“ (eine Mitgliedschaft kann ihr die Planung eines
Projekts nicht öffnen); **Crew** – dazu „Korrespondenz
lesen“; **Lager** – Material „anlegen und bearbeiten“ statt „löschen“, dazu
„Korrespondenz lesen“; **Projektleitung** – Projekte „anlegen und
bearbeiten“ statt „löschen“, Produkte „lesen“ statt „bearbeiten“.
Eine Rolle, die ihr geändert habt, bleibt, wie sie ist. Wer die Standardrechte in einer
geänderten Rolle will, stellt sie unter Einstellungen → Rollen von Hand ein.

**Projektzugriff und Verfügbarkeit von Material.** Die Rolle
**Crew** hat den Projektzugriff „nur zugeordnete Projekte, Überblick ohne
Planung“ – aber nur, wenn sie noch ihre Startrechte hat (nur zugeordnete
Projekte, Projekte lesen, kein Sonderrecht). **Alle anderen Rollen** –
auch eine Crew, die ihr geändert hattet; sie behält ihren Projektzugriff –
haben das Sonderrecht „Verfügbarkeit von Material sehen“.

**Packen ohne Material nachzutragen.** Die Crew packt in ihren
Projekten (Abschnitt 10, „Packen mit der Rolle Crew“). **Material
nachtragen** beim Packen darf nur, wer das Projekt bearbeiten darf oder
für **alle Projekte** packen darf – Lager und Projektleitung also weiter,
eine Rolle mit Packen nur in zugeordneten Projekten und ohne „Projekte:
anlegen und bearbeiten“ nicht. Brauchen solche eigenen Rollen das Nachtragen, gib
ihnen „Projekte: anlegen und bearbeiten“ oder Packen für alle Projekte.

**Nur-Lesen und die Buchhaltung.** „Alles lesen“ heißt bei Nur-Lesen: alle
Module außer den Einstellungen. Den Menüpunkt Buchhaltung mit den
Ausgangsbelegen sieht Nur-Lesen (Preise und alle Projekte lesen). Die Seite **Einstellungen → Buchhaltung**
(unten) braucht aber Lesezugriff auf die Einstellungen. Soll die
Buchhaltung dort DATEV-Dateien holen und sehen, was an Lexware Office
ging, gib der Rolle Nur-Lesen unter „Einstellungen“ die Stufe „lesen“ –
oder lege eine eigene Rolle „Buchhaltung“ an: Einstellungen „lesen“ und
das Sonderrecht „Preise und Kalkulation sehen“, dazu Projekte „lesen“.
Lesezugriff auf die Einstellungen zeigt auch Protokolle und Nutzer; wägt
ab, was euch lieber ist.

**Zwei-Faktor-Anmeldung vorschreiben.** An jeder Rolle lässt sich
ankreuzen, dass ihre Nutzer die Zwei-Faktor-Anmeldung einrichten müssen
(Abschnitt 2, „Mein Konto“). Wer sie noch nicht hat, kommt nach dem
Anmelden direkt zur Einrichtung und kann vorher nichts anderes tun. Für
alle, die die Einstellungen ändern dürfen, schreibt eine Einstellung sie
vor (unten, „Firmendaten und Grundeinstellungen“).

**Zwei-Faktor-Anmeldung zurücksetzen.** Hat jemand Telefon und
Wiederherstellungscodes verloren: Einstellungen → Nutzer → der Nutzer →
„Zwei-Faktor-Anmeldung zurücksetzen“. Er meldet sich dann mit dem Passwort
an und richtet sie neu ein. Ist der einzige Administrator betroffen, hilft
auf dem Server `sudo rentalars reset_two_factor NAME`.

### Verzeichnis (LDAP)

*Ausgeschaltet, bis ihr es einschaltet.* Hat eure Firma ein
Verzeichnis (OpenLDAP oder Active Directory), melden sich die Kolleginnen und
Kollegen mit ihrem Firmenkonto an, und **ihre Gruppen im Verzeichnis bestimmen
ihre Rollen** in Rentalars. Die Seite findest du unter **Einstellungen → Nutzer
und Rechte → „Verzeichnis (LDAP)“** (nicht im Kasten „Betrieb und Sicherheit“);
sie sehen und ändern, wer die Einstellungen sehen bzw. ändern darf.

**Bevor du einschaltest:**

1. **Ein lokales Notfallkonto.** Setze in **Einstellungen → Nutzer** bei
   mindestens einer Administratorin das Häkchen **„lokales (Notfall-)Konto“** (auf
   der Seite des Nutzers). Dieses Konto meldet sich **nur mit seinem Passwort in
   Rentalars** an, das Verzeichnis fragt Rentalars nie nach ihm und ändert weder
   seine Rollen noch deaktiviert es – damit komme ihr hinein, wenn das
   Verzeichnis nicht antwortet. Dasselbe gilt für Konten mit „Hat alle Rechte“.
   Solange keins da ist, weist die Seite rot darauf hin, und
   „Anmeldung mit lokalem Passwort erlauben“ lässt sich nicht ausschalten.
   Lokale Notfallkonten und Konten mit „Hat alle Rechte“ sind auch dann
   geschützt, wenn das Verzeichnis einen Eintrag mit demselben Namen oder
   demselben Eintragsnamen (DN) hat: Sie werden weder angemeldet noch
   abgeglichen, und eine Verknüpfung mit dem Verzeichnis wird gelöscht, sobald
   ein Konto lokal wird oder alle Rechte bekommt.
2. **Server nach Namen.** Trag die Server **mit ihrem Namen** ein
   (`ldaps://dc1.firma.example`), nicht mit der IP-Adresse: Die Prüfung des
   Zertifikats vergleicht Namen. Liegt das Verzeichnis im eigenen Netz – das
   tut es meist –, muss der Betrieb Rentalars die Verbindung dorthin freigeben
   (`[network] allow_internal` in der Konfigurationsdatei; Anleitung [„Betrieb“](../betrieb/betrieb.md));
   sonst meldet der Test „nicht erreichbar“.
3. **Mindestens eine Zuordnung** von Gruppe zu Rolle (unten). Ohne sie kann sich
   niemand über das Verzeichnis anmelden, und die Seite sagt es.
4. **Bestehende Konten.** Jemand, der schon ein Konto in Rentalars hat,
   meldet sich über das Verzeichnis **nur an, wenn das Konto mit dem Verzeichnis
   verknüpft ist**. Voreingestellt ist das Verknüpfen über den Namen
   **aus** („Bestehende Konten über den Namen verknüpfen“, unten): Ein Name im
   Verzeichnis beweist nicht, dass es dieselbe Person ist. Wer sich bisher mit
   einem eigenen Passwort in Rentalars anmeldet, bleibt dabei, solange die Anmeldung
   mit lokalem Passwort erlaubt ist; will eine
   Administratorin solche Konten ins Verzeichnis holen, schaltet sie den
   Schalter an, lässt die Betroffenen sich einmal anmelden und schaltet ihn
   wieder aus – verknüpfte Konten melden sich danach weiter an.

**Die Seite** hat vier Kästen. Mit „Vorschläge eintragen: OpenLDAP · Active
Directory“ oben rechts im ersten füllst du die Felder mit den üblichen Werten
vor (gespeichert wird erst mit „Einstellungen speichern“).

- **„Verbindung“**: der Schalter **„Anmeldung über das Verzeichnis“**; die **Server**
  (eine Adresse je Zeile, `ldaps://…` oder `ldap://…:389`, mehrere werden der
  Reihe nach versucht); **„Mit StartTLS verschlüsseln“** (für `ldap://`; eine Adresse `ldap://` **ohne**
  StartTLS schickt Passwörter im Klartext – die Seite, der Verbindungstest und
  die Schnittstelle warnen davor);
  **„Zertifikat des Servers prüfen“** (an – schalte es nur für einen Test aus, denn
  ohne Prüfung kann sich jeder als der Server ausgeben); **„Datei mit dem
  CA-Zertifikat“** (der absolute Pfad einer Datei auf dem Server, die Rentalars
  lesen kann und die ein Zertifikat im PEM-Format enthält – sonst lehnt die
  Seite sie ab) oder **„CA-Zertifikat (eingefügt)“**, wenn
  ihr eine eigene Zertifizierungsstelle habt; **„Zeitlimit in Sekunden“** (8).
- **„Suchkonto“**: **„Suchkonto (DN)“** und **„Passwort des Suchkontos“** – das Konto, mit
  dem Rentalars nach Nutzern und Gruppen sucht. Leer: anonyme Suche. Das Passwort
  wird verschlüsselt gespeichert und nie wieder gezeigt; leer lassen behält es,
  **„Gespeichertes Passwort entfernen“** löscht es, und ändern sich Server oder
  Suchkonto, wird es verworfen, damit es nicht an einen anderen Ort geht. Wird
  der geheime Schlüssel der Installation geändert, ist es unlesbar; die Seite sagt
  es, und du trägst es neu ein.
- **„Nutzer finden“**: **„Suchbasis für Nutzer“**, **„Filter für Nutzer“** mit
  `{username}` für den getippten Namen – OpenLDAP
  `(&(objectClass=inetOrgPerson)(uid={username}))`, Active Directory
  `(&(objectClass=person)(sAMAccountName={username}))` – und die Attribute für
  Benutzername, E-Mail-Adresse, Vor- und Nachname.
- **„Gruppen finden“**: **„Gruppen finden“** entweder über **„Attribut des Nutzers
  (memberOf)“** (Active Directory; **„Attribut mit den Gruppen“**) oder **„In den
  Gruppen suchen“** (**„Suchbasis für Gruppen“**, **„Filter für Gruppen“** mit
  `{user_dn}` bzw. `{username}`, z. B.
  `(&(objectClass=groupOfNames)(member={user_dn}))`). Verschachtelte Gruppen gibt es
  nur in Active Directory: Rentalars liest sonst nur die Gruppen, in denen jemand
  unmittelbar Mitglied ist. Verschachtelte findet eine Gruppensuche mit dem Filter
  `(&(objectClass=group)(member:1.2.840.113556.1.4.1941:={user_dn}))` (mit den
  äußeren Klammern; ohne sie lehnt Rentalars den Filter ab). Der Filter ist als
  Text und gegen den Filter-Parser geprüft, aber nicht an einem echten Active
  Directory. OpenLDAP kennt diese Regel nicht; dort müssen die Gruppen, die eine
  Rolle bekommen sollen, die Person selbst als Mitglied führen.
- **„Bei der Anmeldung“**: **„Anmeldung mit lokalem Passwort erlauben“** (an: Konten
  mit einem Passwort in Rentalars melden sich weiter damit an; aus: nur lokale
  Notfallkonten, alle anderen über das Verzeichnis), **„Konten bei der ersten
  Anmeldung anlegen“** (an), **„Bestehende Konten über den Namen verknüpfen“**
  (aus; unten) und **„Konten jede Nacht abgleichen“** (aus; unten).

**Gruppen und Rollen.** Unter dem Formular, im Kasten **„Gruppen und Rollen“**,
legst du mit **„Neue Zuordnung“** fest, welche Rollen die Mitglieder einer Gruppe
bekommen: die **Gruppe** (ihr DN, z. B. `cn=technik,ou=gruppen,dc=firma,dc=de`,
oder nur ihr Name `technik`; ohne Rücksicht auf Groß- und Kleinschreibung; höchstens
480 Zeichen; die
deutsche Oberfläche nennt Spalte und Feld hier „Teilgruppe“, gemeint ist die
Gruppe im Verzeichnis), die **Rollen**, die **Priorität** (100) und den Haken
**„letzter Treffer“**. Eine Gruppe darf nur eine Zuordnung haben. **Nimm den
vollständigen DN.** Ein bloßer Name passt auf eine Gruppe dieses Namens
**irgendwo** im Verzeichnis, auch in einem Bereich, in den andere schreiben
dürfen; die Seite und die Schnittstelle warnen bei einer solchen Zuordnung
(`name_only`, `warning`). Bestehende Zuordnungen mit Namen laufen weiter.

- Wer in mehreren Gruppen ist, bekommt **die Rollen aller** (die Vereinigung).
  Die Zuordnungen werden nach der Priorität geprüft, die kleinste Zahl zuerst;
  „letzter Treffer“ beendet die Liste für die Mitglieder dieser Gruppe.
- Das Verzeichnis vergibt **nie** „Hat alle Rechte“ und nimmt die Rolle der
  letzten Administratorin, die die Einstellungen ändern darf, nie weg.
- **Rollen aus dem Verzeichnis** folgen bei **jeder Anmeldung** den Gruppen und
  lassen sich in Rentalars **nicht** von Hand entfernen; sie stehen bei dem Nutzer
  unter „Rollen aus dem Verzeichnis (LDAP)“ mit „aus dem Verzeichnis“. Rollen, die
  du von Hand gegeben hast, bleiben auch dann, wenn die Gruppe sie nicht mehr
  gibt. Löschst du eine Zuordnung, werden ihre Rollen bei der nächsten
  Anmeldung zurückgenommen.

**Was bei der Anmeldung geschieht.** Die Anmeldeseite bleibt, wie sie ist.
Rentalars prüft Name und Passwort zuerst lokal, dann im Verzeichnis (bei einem
lokalen Notfallkonto oder „Hat alle Rechte“ nur lokal); Sperre nach
Fehlversuchen, Sicherheitsprotokoll und Zwei-Faktor-Anmeldung gelten wie immer –
**erst das Passwort des Verzeichnisses, dann der Code**.

- Hat der Nutzer noch kein Konto, legt Rentalars eins an – **aber nur, wenn
  mindestens eine seiner Gruppen eine Rolle gibt** und die Anmeldung nicht
  ausgeschaltet ist („Konten bei der ersten Anmeldung anlegen“). Name, E-Mail-Adresse
  und Rollen kommen aus dem Verzeichnis; das Konto hat **kein eigenes Passwort**:
  Passwort ändern, „Passwort vergessen?“ und Einladung gibt es für diese Konten nicht.
  Gibt es schon ein Konto mit demselben Benutzernamen – kein Notfallkonto, ohne „Hat
  alle Rechte“ und noch an kein Verzeichnis gebunden –, übernimmt das
  Verzeichnis es **nur, wenn „Bestehende Konten über den Namen verknüpfen“ an ist**
  (voreingestellt aus): Dann behält das Konto die Rollen, die eine Administratorin
  ihm gegeben hat; die Seite warnt in Rot, solange der Schalter an ist. Ist er aus,
  wird die Anmeldung abgewiesen; der Nutzer sieht nur eine allgemeine Ablehnung,
  der Grund steht im Sicherheitsprotokoll, und der Test der Anmeldung nennt ihn
  („nicht mit dem Verzeichnis verknüpft“). Zwei Namen, die die Datenbank nicht
  unterscheidet (`müller` und `muller`), werden ebenfalls abgewiesen. Ein Konto,
  das schon mit einem Eintrag verknüpft ist, wird nicht über den Namen auf einen
  anderen Eintrag umgehängt (siehe „Neuen Eintrag übernehmen“ unten).
- Der Benutzername aus dem Verzeichnis darf nur Buchstaben, Ziffern und `@ . + - _`
  enthalten und höchstens 150 Zeichen lang sein; ein anderer wird **abgewiesen**,
  nicht gekürzt (so auch ein getippter Name über 256 Zeichen). Vor- und
  Nachname kürzt Rentalars auf 150 Zeichen.
- Ist der Nutzer in **keiner** zugeordneten Gruppe, wird die Anmeldung abgewiesen,
  und ein Konto, das das Verzeichnis führt, wird **deaktiviert** (und wieder
  aktiviert, wenn die Gruppe zurückkommt). Ein Konto, das eine Administratorin
  deaktiviert hat, bleibt deaktiviert.
- Antwortet das Verzeichnis nicht, sagt die Anmeldeseite „Das Firmenverzeichnis war
  eben nicht erreichbar“; die lokalen Konten gehen weiter.
- Benutzername und Passwort gehen nur an das Verzeichnis, ein leeres Passwort nie;
  das Passwort steht in keinem Protokoll. Das Sicherheitsprotokoll kennt dafür
  „Anmeldung über das Verzeichnis abgewiesen“, „Verzeichnis nicht erreichbar“, „Konto
  vom Verzeichnis angelegt oder geändert“, „Rollen vom Verzeichnis geändert“,
  „Konten mit dem Verzeichnis abgeglichen“ und „Verzeichnis-Anmeldung von einem
  Administrator ausprobiert“.
- Auf der Seite des Nutzers steht ein Kasten **„Verzeichnis (LDAP)“** mit dem
  **Eintrag im Verzeichnis**, „Zuletzt vom Verzeichnis bestätigt“ und, wenn es das
  Konto deaktiviert hat, „Vom Verzeichnis deaktiviert“.

**Testen, ohne etwas zu schreiben.** Im Kasten **„Test“** (nur mit Änderungsrecht;
die Tests benutzen die **gespeicherten** Einstellungen):

- **„Verbindung testen“**: Schritt für Schritt „Server“, „Verschlüsselung“,
  „Verbindung und Suchkonto“ und die Suchbasen für Nutzer und Gruppen – je Schritt
  „OK“ oder „Problem“ mit der Ursache.
- **„Anmeldung für einen Nutzer testen“**: Gib den **Benutzernamen** ein – das
  **Passwort ist freiwillig** und wird, wenn du es eingibst, nur dieses eine Mal
  geprüft – und **„Anmeldung testen“** zeigt: den Eintrag im Verzeichnis, Name,
  E-Mail-Adresse, die Gruppen, die **Zuordnungen, die gelten**, die **Rollen aus
  dem Verzeichnis** und „Die Anmeldung würde …“: ein neues Konto anlegen, das
  vorhandene benutzen, abgewiesen werden und das Konto deaktivieren – mit dem
  Grund. Damit findest du auch heraus, warum jemand trotz richtigem Passwort
  nicht hineinkommt. Der Test steht als „Verzeichnis-Anmeldung von einem
  Administrator ausprobiert“ im Sicherheitsprotokoll und **zählt zur Sperre
  nach Fehlversuchen** wie eine Anmeldung (über die Schnittstelle: Antwort 429),
  damit er kein Weg zum Raten von Passwörtern ist.
- **„Neuen Eintrag übernehmen“.** Wurde jemand im Verzeichnis **verschoben**
  (sein DN hat sich geändert), weist die Anmeldung das Konto ab, weil es mit dem
  alten Eintrag verknüpft ist – ein Name allein beweist nichts. Der Test zeigt
  dann „Im Verzeichnis verschoben?“ und den Knopf **„Neuen Eintrag übernehmen“**
  (mit Rückfrage; über die Schnittstelle `POST /ldap/adopt-dn`): Er hängt das
  Konto an den Eintrag, den das Verzeichnis für den Namen findet – **nur, wenn
  der alte Eintrag im Verzeichnis nicht mehr existiert**, und nie bei einem
  lokalen Konto oder einem mit „Hat alle Rechte“. Der Vorgang steht im Verlauf
  des Kontos und im Sicherheitsprotokoll.
- **„Konten mit dem Verzeichnis abgleichen“**: **„Unterschiede anzeigen“** listet,
  was geschähe – wer deaktiviert, wieder aktiviert oder aktualisiert würde –, und
  **„Diese Änderungen anwenden“** tut es. Der Abgleich legt **niemanden** an; er
  stellt nur die Konten richtig, die das Verzeichnis führt. Er hält an, wenn er
  mehr als drei Konten und mehr als die Hälfte aller deaktivieren würde (ein
  falscher Filter, ein Verzeichnis, das mit nichts antwortet); die Seite sagt es.
  Mit **„Konten jede Nacht abgleichen“** geschieht dasselbe nachts mit den
  Wartungsaufgaben, ohne auf die nächste Anmeldung zu warten (Server: `ldap_sync`, nur
  Vorschau, mit `--apply` schreibend, mit `--force` über die Schutzgrenze).

**Grenzen.** Rentalars **schreibt nie ins Verzeichnis**, und ein Konto entsteht nur
bei einer Anmeldung, nie durch den Abgleich. Getestet ist die
Anmeldung gegen ein simuliertes Verzeichnis und einen echten OpenLDAP-Server,
**nicht gegen Active Directory**; probiere es dort zuerst mit dem Test der
Anmeldung. Über die Schnittstelle gibt es dasselbe (Abschnitt 16, „API-Token“);
Nutzer haben dort die Felder `local_account`, `ldap_dn` und `directory_roles`.
**Schaltet ihr das Verzeichnis wieder ab**, sind Konten, die nur im Verzeichnis
existierten und kein Passwort in Rentalars haben, nicht gestrandet: Eine
Administratorin kann sie einladen oder ihnen ein Passwort setzen.

### Firmendaten und Grundeinstellungen

**Einstellungen → Firmendaten und Grundeinstellungen** – zwei Formulare
auf einer Seite:

- **Firmendaten:** Name, Anschrift, Telefon, E-Mail, Website,
  Steuernummer, USt-IdNr., Bank mit IBAN und BIC, **Logo** (PNG oder
  JPEG). Sie erscheinen auf der Packliste und auf den Dokumenten – im Kopf
  das Logo mit Anschrift, im Fuß Anschrift, Kontakt, Steuernummern und
  Bankverbindung. Dazu:
  - **Register und Geschäftsführung** – steht im Fuß der Dokumente, z. B.
    „Amtsgericht Musterstadt HRB 1234 · Geschäftsführung: …“;
  - **Zahlungsziel in Tagen** – für Rechnungen, sofern der Kunde kein
    eigenes hat; voreingestellt 14;
  - **Anschrift des Lagers** – in einer Zeile, etwa „Industriestraße 5,
    12345 Musterstadt“: Hier beginnen und enden die Fahrten der Projekte
    (Abschnitt 7, „Die Fahrten eines Projekts“). Die Links „Route in Google
    Maps“ starten immer an deinem aktuellen Standort, nicht am
    Lager (Abschnitt 6, „Route und Karte“). Leer gilt die
    Anschrift der Firma. Unter dem Formular stehen „Route in Google Maps“
    zur Firma, „Route zum Lager“ und „Karte anzeigen“.

  Für die XRechnung sind **E-Mail-Adresse**, **Telefonnummer** und
  **USt-IdNr. oder Steuernummer** Pflicht (Abschnitt 11). Trag alles ein,
  bevor die erste Rechnung entsteht. Der Firmenname steht auch im Absender
  gesendeter Mails, in der Signatur (`{firma}`, Abschnitt 14), am Ende
  jeder Mail, die Rentalars von selbst verschickt (Abschnitt 14,
  „Signatur“), und klein in der Seitenleiste unter „Rentalars“
  (Abschnitt 2).
- **Sprache der Dokumente**: Deutsch oder English – in
  welcher Sprache Angebote, Auftragsbestätigungen, Lieferscheine,
  Rechnungen, Packlisten und Crew-Disposition entstehen und die Mails, die
  Rentalars von selbst an Kunden schreibt, etwa die Antworten von
  Automationen. Feste Texte wie Spaltennamen, Einheiten und Daten folgen
  ihr; was ihr selbst eingetippt habt – Dokumentvorlagen, Textbausteine,
  Mailvorlagen, Produktnamen –, bleibt, wie es ist (Abschnitt 11,
  „Sprache“). Sie gilt für die ganze Firma; die Oberfläche wählt jede
  Person für sich (Abschnitt 2, „Mein Konto“). Voreingestellt ist die
  Sprache der Installation.
- **Pufferzeiten** vor und nach dem Einsatz (Abschnitt 9).
- **Übliche Beginnzeit** und **übliche Endzeit:** die Uhrzeiten, mit denen
  ein neues Projekt vorbelegt wird – voreingestellt 12:00 und 12:00. Liegt
  die Endzeit nicht nach der Beginnzeit, endet das Projekt am Folgetag (12
  bis 12 Uhr: ein Tag, Abschnitt 7).
- **Passwörter und Anmeldung:** Mindestlänge des Passworts, Zahl der
  Fehlversuche bis zur Sperre, Dauer der Sperre.
- **Personen dürfen ihre eigenen Stundensätze sehen:** eingeschaltet – das
  gilt auch für die Tagessätze. Wer das nicht möchte, nimmt den Haken
  heraus; dann sehen nur noch Nutzer mit dem Sonderrecht für
  Personalkosten Sätze und Beträge.
- **Bei geänderten Zeiten neu anfragen:** eingeschaltet (voreingestellt)
  bekommt eine angefragte oder zugesagte Person von selbst eine neue
  Einsatzanfrage, wenn sich Beginn oder Ende ihrer Personalposition
  ändern, und die Position steht bis zur Antwort wieder auf „angefragt“;
  abgesagte Positionen nicht (Abschnitt 12, „Anfragen: Zusage oder
  Absage“). Ausgeschaltet fragst du mit „erneut anfragen“ selbst neu an.
- **Antwort auf Einsatzanfragen**: wie Personen auf eine Einsatzanfrage antworten – „über den Link
  im Browser“, „per Antwort-Mail“ oder „beides“ (voreingestellt). Darunter
  steht, an welches Postfach Antworten per Mail gehen – oder dass es noch
  keines gibt (Abschnitt 12, „Einsatzanfragen per Mail beantworten“).
- **Abmelden nach … Minuten ohne Aktivität:** voreingestellt 240.
- **Zwei-Faktor-Anmeldung für Administratoren vorschreiben:** für alle, die
  die Einstellungen ändern dürfen, und jedes Konto mit allen Rechten.
  Spätestens wenn Rentalars aus dem Internet erreichbar ist, einschalten.
- **Präfix der Projektkennung in Mails:** „RL“, die Kennung lautet dann
  `[RL#2026-0042]` (Abschnitt 14).
- **Größte hochladbare Datei:** voreingestellt 50 MB, höchstens 500 MB –
  für Projektdateien und Showfiles, Hallenpläne, Belege von Spesen und
  Anhänge gesendeter Mails. Für Showfiles mit Medien darf es mehr sein
  (Abschnitt 11, „Dateien des Projekts“).
- **Karten sofort laden:** aus (voreingestellt) erscheint eine Karte erst
  nach einem Klick auf „Karte anzeigen“ – erst dann geht die Anschrift an
  OpenStreetMap; an zeigt jede Seite mit einer Anschrift ihre Karte sofort
  (Abschnitt 6, „Route und Karte“).
- **Buchhaltung und Rechnungswesen** (eigener Kasten): **Rentalars als
  Buchhaltungsprogramm verwenden** – an (voreingestellt). Aus: keine Rechnungen und
  Stornorechnungen, Übergabe an Lexware Office und DATEV-Export und alle
  Buchhaltungs-Reiter (Eingangsbelege, Offene Posten, Bank, EÜR, Archiv,
  Anlagenspiegel …) ausgeblendet; früher erstellte Rechnungen bleiben lesbar
  (Abschnitt 11, „Rechnungen in einem anderen Programm“).
- **Hinweise bei auffälligen Zeiten:** **„Hinweise zu Arbeitszeiten
  anzeigen“** (eingeschaltet) schaltet alle Hinweise für alle
  an oder aus; die Grenzen darunter bleiben dabei gespeichert. „Hinweis:
  Arbeitstag länger als … Stunden“ (10), „Hinweis: Pause nötig ab mehr als
  … Stunden Arbeit“ (6) mit „Hinweis: diese Pause dauert mindestens …
  Minuten“ (30), die längere Pause ab 9 Stunden mit 45 Minuten, „Hinweis:
  Ruhezeit zwischen zwei Arbeitstagen kürzer als … Stunden“ (11); 0
  schaltet einen einzelnen Hinweis aus (Abschnitt 13, „Hinweise bei
  auffälligen Zeiten“).
- **Fahrtkosten je Kilometer:** voreingestellt 0,30 € – für Fahrten mit dem
  eigenen Auto, die als Spesen erfasst werden. Eine Fahrt behält den Satz,
  mit dem sie erfasst wurde (Abschnitt 13, „Spesen und Fahrtkosten“).
- **„Arbeitsweg von Fahrten abziehen“** (eingeschaltet): Bei
  Fahrten nach Kilometern wird einmal am Tag je Projekt die doppelte
  „Entfernung Wohnung – Betrieb“ der Person abgezogen (Abschnitt 13,
  „Spesen und Fahrtkosten“). Ausgeschaltet wird nichts abgezogen.
- **API-Aufrufe je Token und Minute:** voreingestellt 600 (unten,
  „API-Token“). 0 heißt: keine Grenze.
- **Aufbewahrungsfristen** für Protokolle (auch das Zugriffsprotokoll),
  Benachrichtigungen und Hintergrundaufgaben (unten,
  „Aufbewahrungsfristen“).

Die **Postfächer** und die **Signatur** stehen nicht hier, sondern unter
Einstellungen → E-Mail → „Postfächer und Signatur“ (Abschnitt 14).

**Routendienst**. Unter den Formularen zeigt der Kasten
**„Routendienst“**, ob er „eingerichtet“ oder „nicht eingerichtet“ ist, und
wenn ja, seine Art, die Region und wie alt die Karte ist. Der Routendienst
schlägt für ein Fahrzeug auf einer Fahrt die geplanten Kilometer aus der
Route vor, stets änderbar (Abschnitt 7, „Logistik“); die Route berechnet
euer Server oder ein Routenserver des Betreibers oder in Deutschland, die
Orte findet Rentalars wie auf den Karten. Einrichten, aktualisieren und
entfernen kann ihn nur, wer den Server betreut, mit den Befehlen, die der
Kasten nennt (Anleitung [„Betrieb“](../betrieb/betrieb.md), „Routendienst“). Ohne Routendienst
werden die Kilometer von Hand eingetragen.

### Nummernkreise

Für Projekte, Kunden, Material-IDs und die Dokumente: Präfix, Mindestzahl
der Stellen, nächste Nummer, und ob jedes Jahr neu begonnen wird. Im
Präfix steht `{year}` für das laufende Jahr – mit dem voreingestellten
Präfix `{year}-` entstehen Projektnummern wie `2026-0001`. Oben an jedem
Kreis steht, wie die nächste Nummer aussieht.

Änderst du das Präfix, gilt das nur für neue Projekte; vorhandene
behalten ihre Nummer. Eine Nummer, die ein Projekt einmal getragen hat,
vergibt Rentalars nicht neu.

Für die Dokumente (Abschnitt 11) gibt es eigene Kreise: **Angebote**
(`AN-{year}-`, also `AN-2026-0001`), **Auftragsbestätigungen**
(`AB-{year}-`), **Lieferscheine** (`LS-{year}-`), **Rechnungen und
Stornos** (`RE-{year}-`) und **Crew-Dispositionen** (`CD-{year}-`) – alle
jedes Jahr neu.

Die „nächste Nummer“ kannst du hochsetzen, etwa um an eine bestehende
Nummerierung anzuschließen. Heruntersetzen solltest du sie nur, wenn die
Nummern wirklich noch frei sind – bei Rechnungen nie: Rechnungsnummern
müssen lückenlos und eindeutig sein.

### Zuschläge

**Einstellungen → Zuschläge** („Zuschläge für Nacht, Sonn- und
Feiertage“) legt fest, ob und wie viel Personalpositionen zu bestimmten
Zeiten mehr kosten – für den Preis des Kunden und für die Personalkosten
getrennt. Wie Rentalars damit rechnet, steht in Abschnitt 12, „Zuschläge
für Nacht, Sonn- und Feiertage“. Die Zuschläge sind eine **Liste von
Regeln**, die in jedem Land taugt.

Zuschläge für Nacht, Sonn- und Feiertage bekommen **nur
Personalpositionen**, die nach Stunden abgerechnet werden (nach Plan oder
nach Aufwand) – nie Material, Nebenkosten, Aufpreise oder andere
Positionen und keine Personalposition mit Pauschale oder Tagessatz. Den
Schalter zum Ausnehmen gibt es nur bei Dienstleistungen.

- **„Welche Personalpositionen“:** **„Zuschläge im Preis der
  Personalpositionen“** und **„Zuschläge in den Personalkosten der
  Personalpositionen“** – beide anfangs aus.
  Eingeschaltet bekommen Personalpositionen nach Stunden, die **ab dann**
  geplant werden, die Zuschläge; vorher geplante bleiben, wie sie sind.
  Jede Position behält ihre eigenen Schalter im Dialog, und eine
  Dienstleistung kann ihre Positionen auf ihrer Produktseite ausnehmen;
  andere Produkte haben diesen Schalter nicht – ihre Positionen bekommen
  nie Zuschläge.
- **„Regeln“:** Jede Regel steht in einer eigenen Karte. In der ersten
  Zeile: **„Name“** (er steht in Planung und Dokumenten), **„gilt“** –
  wann sie gilt –, **„im Preis, in Prozent“**, **„in den Kosten, in
  Prozent“** (0 heißt kein Zuschlag), **↑** und **↓** für die Reihenfolge
  und **„Löschen“**. Darunter die Angaben, die zur gewählten Art passen:
  - **zu einer Uhrzeit** – von … bis, auch über Mitternacht (Nacht 20–6
    Uhr); mit dem Haken **„nur bei Arbeit, die vor 0 Uhr begann“** gilt die
    Regel nur dann und tritt an die Stelle der anderen Uhrzeit-Regeln (die
    40 % von 0 bis 4 Uhr nach § 3b EStG);
  - **an Wochentagen** – Mo bis So zum Ankreuzen, auf Wunsch ab einer
    Uhrzeit (Samstag ab 13 Uhr);
  - **an Feiertagen** – an den gesetzlichen und euren eigenen (unten), auf
    Wunsch ab einer Uhrzeit;
  - **an einem Tag im Jahr** – Tag und Monat, auf Wunsch ab einer Uhrzeit
    (24.12. ab 14 Uhr).

  **„Regel hinzufügen“** bringt eine neue Karte; zum Entfernen setzt du
  „Löschen“ und speicherst. Ohne JavaScript steht unten immer eine leere
  Karte für eine neue Regel.
- **Wie die Regeln zusammenkommen:** Von den Regeln an Wochentagen,
  Feiertagen und Tagen im Jahr zählt nur der höchste Satz, von den Regeln
  zu einer Uhrzeit ebenso; beide werden addiert – Nacht 25 % plus Feiertag
  125 %. Bei gleichem Satz zählt die weiter unten stehende Regel. Preis und
  Kosten wählen ihre Regel jeweils für sich. Regeln mit gleicher
  Bezeichnung und gleichem Satz stehen in Planung und Dokumenten als eine
  Zeile.
- **Bis wann ein Tag mit Zuschlag in den nächsten reicht:** Bei Arbeit,
  die vor 0 Uhr begann, gelten die Tagesregeln des Vortags (Sonntag,
  Feiertag) noch bis zu dieser Uhrzeit – nach § 3b EStG bis 4 Uhr. Leer
  heißt: nie.
- **„Nach § 3b EStG einstellen“** ersetzt nach einer Rückfrage alle Regeln
  durch die steuerfreien Sätze nach § 3b EStG und stellt 4 Uhr ein;
  Feiertage, Bundesland und die beiden Schalter oben bleiben. Die Regeln
  sind dann:

  | Regel | gilt | Satz |
  |---|---|---|
  | Nacht | zu einer Uhrzeit, 20 bis 6 Uhr | 25 % |
  | Nacht 0–4 Uhr | zu einer Uhrzeit, 0 bis 4 Uhr, nur bei Arbeit, die vor 0 Uhr begann | 40 % |
  | Sonntag | an Wochentagen: So | 50 % |
  | Feiertag | an Feiertagen; und am 31.12. ab 14 Uhr | 125 % |
  | Weihnachten und 1. Mai | am 24.12. ab 14 Uhr, am 25.12., am 26.12., am 1.5. | 150 % |

  Ob die Sätze für eure Lohnabrechnung passen, klärt ihr mit der
  Lohnbuchhaltung; jeder Wert ist änderbar. Eine neue Installation hat
  diese Regeln von Anfang an; löschst du alle, heißt die leere Liste: keine
  Zuschläge.
- **„Feiertage“:** **„Feiertage von“** – das Bundesland, dessen
  gesetzliche Feiertage gelten, für alle Projekte dasselbe; ohne Wahl nur
  die bundesweiten. Für Bayern, Sachsen und Thüringen gibt es die Varianten
  mit und ohne Mariä Himmelfahrt bzw. Fronleichnam, dazu die Stadt
  Augsburg mit dem Friedensfest. Nimmst du den Haken **„gesetzliche
  Feiertage in Deutschland“** heraus (voreingestellt gesetzt), zählen nur
  eure eigenen Feiertage – etwa, wenn ihr in einem anderen Land arbeitet;
  die Liste unten nennt dann „nur eigene Feiertage“.
- **„Eigene Feiertage“** – für die Arbeit in einem anderen Land oder Tage,
  die der Betrieb begeht; sie gelten für den ganzen Betrieb wie das
  Bundesland. „Feiertag hinzufügen“, dann Bezeichnung und eine der drei
  Arten: **„jedes Jahr am“** (Tag und Monat), **„einmalig am“** (ein
  Datum) oder **„Tage ab Ostersonntag“** – eine Zahl von −80 bis 240,
  etwa Ostermontag 1, Christi Himmelfahrt 39, Pfingstmontag 50,
  Fronleichnam 60.

„Einstellungen speichern“. Darunter stehen die **Feiertage** dieses und
des nächsten Jahres, wie Rentalars sie berechnet – die gesetzlichen des
gewählten Bundeslands und die eigenen. Prüfe sie einmal. Eine Änderung
gilt sofort für jede Position mit Zuschlägen, auch in abgeschlossenen
Projekten; erstellte Dokumente bleiben, wie sie sind.

Die Sätze sieht und ändert nur, wer das passende Recht hat: die Sätze auf
den Preis mit „Preise und Kalkulation sehen“, die auf die Kosten mit
„Stundensätze und Personalkosten sehen“ – auch im Änderungsprotokoll.

**Woher kommen die Feiertage?** Rentalars berechnet sie selbst, je
Bundesland – auch die beweglichen, die vom Osterdatum abhängen, wie
Karfreitag, Ostermontag, Christi Himmelfahrt, Pfingstmontag und
Fronleichnam. Dafür wird kein Dienst im Internet gefragt; es braucht keine
Verbindung nach außen und kein Abo. Die Liste unten auf der Seite zeigt,
was dabei herauskommt.

### Automationen

**Einstellungen → Automationen** lässt Rentalars von selbst etwas tun,
wenn etwas geschieht: jede neue Anfrage mit einer Eingangsbestätigung
beantworten, die Projektleitung benachrichtigen, wenn ein Projekt
bestätigt ist, einen offenen Punkt „Ersatz suchen“ notieren, wenn jemand
absagt, aus einem gemeldeten Defekt einen Servicefall machen. Jede Regel
heißt „Wenn … dann …“; **„Neue Automation“** legt eine an:

- **Name** – steht in der Liste und bei jeder Ausführung – und **aktiv**.
- **„Wenn …“** – der Auslöser:
  - **eine Mail ohne Projektkennung kommt an** – in einem Postfach, das
    Mails ohne Projektkennung übernimmt, oder an eine weitere Adresse, die
    sie als Anfrage oder gleich als Servicefall übernimmt (Abschnitt 14,
    „Postfächer einrichten“); unter „nur im Postfach“ eines davon, leer
    jedes. Wurde aus der Mail gleich ein Servicefall, gehört die
    Ausführung zu diesem Fall – ein offener Punkt landet also dort;
  - **ein Projekt erreicht einen Status** – du wählst den Status; das
    zählt auch beim Anlegen und, wenn Rentalars den Status selbst setzt,
    etwa „Unterwegs“ nach der Ausgabe;
  - **eine Antwort auf eine Einsatzanfrage kommt an** – Zusage, Absage oder
    beides, gleich ob im Browser, per Antwort-Mail oder über die
    Schnittstelle;
  - **eine Wiedervorlage ist fällig** (Abschnitt 7, „Wiedervorlage“);
  - **die Wiedervorlage eines Servicefalls ist fällig** – mit
    „Status des Servicefalls“ auf Wunsch nur bei einem Status, etwa
    „wartet auf Schließen“;
  - **neue Kommunikation im Servicefall** – eine empfangene
    oder gesendete Mail, eine von Hand in den Fall verschobene Mail oder
    eine neue Chatnachricht; wahlweise nur eine dieser Arten und nur bei
    einem Status. Abwesenheitsnotizen, Zustellfehler, geänderte
    Chatnachrichten und Notizen in der Korrespondenz (Abschnitt 14) zählen
    nicht;
  - **ein Defekt wird gemeldet** – auf der Seite eines
    Exemplars, bei der Rücknahme oder über die Schnittstelle (Abschnitt 4,
    „Defekt melden“).
- **„… dann“** – die Aktion, eine je Regel; für mehrere Aktionen legst du
  mehrere Regeln an:
  - **die Mail beantworten** – nur beim Auslöser „Mail ohne
    Projektkennung“: „Betreff der Antwort“ (leer: „AW:“ und der Betreff)
    und „Text der Antwort“. Vorgeschlagen ist eine Eingangsbestätigung
    („Guten Tag {name}, vielen Dank für Ihre Nachricht …“) – sie geht an
    Kunden und siezt deshalb;
  - **jemanden benachrichtigen** – „an wen“: einen bestimmten Nutzer, die
    Projektleitung, wer den Einsatz angefragt hat, oder für wen die
    Wiedervorlage ist, je nach Auslöser; mit „Titel der Benachrichtigung“
    und „Text der Benachrichtigung“;
  - **einen offenen Punkt im Projekt notieren** – nur bei Auslösern zu
    einem Projekt;
  - **den Status des Servicefalls setzen** – nur bei den
    Auslösern eines Servicefalls: „Neuer Status“ offen, in Arbeit oder
    erledigt. Die Status mit Wiedervorlage setzt nur eine Person;
  - **einen Servicefall anlegen** – nur beim Auslöser „ein
    Defekt wird gemeldet“: mit **„Titel des Servicefalls“** (leer:
    „Defekt“, die ID und der Kurzname, etwa „Defekt 0042 SM58“),
    **„Beschreibung des Servicefalls“** (leer: was defekt ist, das
    Exemplar, wo es gefunden wurde, wer es wann gemeldet hat) und
    **„Zuständig“** – die Person erfährt per Benachrichtigung, dass der
    Fall bei ihr liegt; leer ist noch niemand zuständig;
  - **unter Projekte → Anfragen stellen** – ebenfalls nur bei
    einer Defektmeldung: Sie wartet dort mit dem **„Betreff in der Liste
    der Anfragen“**, bis jemand einen Servicefall daraus macht oder sie von
    der Liste nimmt (Abschnitt 14, „Anfragen“). Bei einer Defektmeldung
    geht als dritte Aktion „jemanden benachrichtigen“, an einen bestimmten
    Nutzer.

In den Texten setzen **Platzhalter** ein, was gerade geschehen ist; welche
es gibt, steht im Formular unter „Platzhalter für die Texte“, je nach
Auslöser: `{name}`, `{absender}`, `{betreff}` und `{postfach}` bei einer
Mail; `{projekt}`, `{projektnummer}`, `{projektname}`, `{status}`,
`{projektleitung}` und `{link}` bei einem Projekt – bei einem Servicefall
sind `{status}` und `{link}` die des Falls; dazu `{person}`,
`{antwort}`, `{funktion}`, `{einsatz}` und `{anmerkung}` bei einer Antwort
auf eine Einsatzanfrage, `{wiedervorlage}`, `{notiz}` und `{fuer}` bei
einer Wiedervorlage, `{kommunikation}` (die Mail oder Chatnachricht in
wenigen Worten, etwa „Mail von kunde@example.org: Mikrofon defekt“; bei
einer Mail mit Schloss ohne Betreff: „Mail von … (mit
Schloss)“ bzw. „Mail gesendet (mit Schloss)“ – so auch im Titel einer
Benachrichtigung ohne eigenen Titel) bei neuer Kommunikation; `{id}`, `{kurzname}`,
`{modell}`, `{produkt}`, `{seriennummer}`, `{beschreibung}` (was defekt
ist), `{gefunden}` (wo, etwa bei der Rücknahme eines Projekts),
`{gemeldet_von}`, `{gemeldet_am}` und `{link}` (die Adresse des Exemplars)
bei einer Defektmeldung; `{firma}` und `{datum}` immer.
Jeder Platzhalter hat auch einen englischen Namen, etwa
`{company}`, `{date}`, `{sender}`, `{subject}`, `{project_number}`,
`{follow_up}` oder `{communication}`, bei einer Defektmeldung
`{short_name}`, `{model}`, `{product}`, `{serial_number}`,
`{description}`, `{found}`, `{reported_by}` und `{reported_at}`; beide
Namen gelten in jedem Text. Wer
Rentalars auf Englisch nutzt, sieht im Formular die englischen. Ein
Platzhalter, den Rentalars nicht kennt, bleibt stehen, wie er geschrieben
ist.

**Schutz vor Antwortschleifen.** Eine Abwesenheitsnotiz, die auf eine
Eingangsbestätigung antwortet, die wieder bestätigt wird … – das verhindert
Rentalars. Es beantwortet **nie**:

- Mails, die als automatisch versendet gekennzeichnet sind –
  Abwesenheitsnotizen, Zustellfehler, Mailinglisten, Newsletter;
- Mailsysteme und No-Reply-Adressen (mailer-daemon, postmaster, no-reply
  und ähnliche) und eigene Adressen – die Postfächer, den Absender der
  Systemmails, die Adresse der Firma;
- einen Absender, dem dieselbe Automation heute schon geantwortet hat –
  jeder bekommt höchstens eine Antwort je Regel und Tag.

Die Antwort geht über das Postfach, in dem die Mail ankam (sonst das, das
die Korrespondenz versendet), mit der Adresse als Absender, an
die die Mail geschrieben war – bei einer Mail an `support@` also von
`support@` –, an die Antwortadresse der Mail, ist als
automatische Antwort gekennzeichnet, damit andere Systeme nicht
zurückantworten, endet mit dem Hinweis auf Rentalars (Abschnitt 14,
„Signatur“) und steht im Mail-Protokoll als „automatische Antwort“. Die
Mail selbst bleibt als Anfrage stehen, bis jemand sie übernimmt – außer,
sie wurde gleich ein Servicefall.

Mit einer Wiedervorlage, die eine Uhrzeit hat, löst **„eine Wiedervorlage
ist fällig“** erst ab dieser Uhrzeit aus; der Platzhalter
`{wiedervorlage}` lautet dann etwa „Mo 20.10.2026 um 14:30“.

**Automationen für Servicefälle.** Drei Automationen sind
eingerichtet und eingeschaltet:

| Automation | Wenn … | dann … |
|---|---|---|
| Wartet auf Schließen: zum Termin schließen | die Wiedervorlage eines Servicefalls ist fällig, Status „wartet auf Schließen“ | Status „erledigt“; die Wiedervorlage fällt weg |
| Wartet auf Schließen: bei neuer Kommunikation wieder öffnen | neue Kommunikation im Servicefall, Status „wartet auf Schließen“ | Status „offen“; die Wiedervorlage bleibt als Erinnerung |
| Rückstand: zur Wiedervorlage wieder öffnen | die Wiedervorlage eines Servicefalls ist fällig, Status „zurückgestellt“ | Status „offen“ |

Du kannst sie ändern, ausschalten oder löschen. Solange die erste
eingeschaltet ist, bekommt bei „wartet auf Schließen“ niemand eine
Wiedervorlage-Benachrichtigung zum Termin; schaltest du sie aus, kommt die
Benachrichtigung wie gewohnt. Die Automationen eines Servicefalls laufen
auch, wenn niemand für ihn zuständig ist. Was eine Automation selbst tut –
etwa einen Status setzen –, löst keine weitere Automation aus. Kurz bevor
sie ausgeführt wird, prüft Rentalars noch einmal, ob Status und Termin
noch stimmen; hat jemand den Fall inzwischen geändert, steht die
Ausführung als „ausgelassen“ mit dem Grund da. Soll eine neue Mail auch
einen wartenden Fall wieder öffnen, legst du eine Regel wie die zweite mit
dem Status „wartet“ an.

**Defektmeldung → Servicefall.** Jede Installation hat
eine weitere eingeschaltete Automation: Wenn ein Defekt gemeldet wird,
legt sie einen Servicefall an. Er ist intern – euer eigenes Material, kein
Kunde –, bei Kundenmaterial gehört er dessen Eigentümer; das Foto der
Meldung kommt in seine Dateien (Abschnitt 7, „Servicefälle“). Titel,
Beschreibung und „Zuständig“ stellst du an der Regel ein. Du kannst sie
ändern, ausschalten oder auf „unter Projekte → Anfragen stellen“
umstellen, wenn erst jemand entscheiden soll. Aus einer Meldung wird
höchstens ein Servicefall; Meldungen von vor der Aktualisierung lösen
nichts aus.

**Die mitgelieferten Automationen**. Die vier Automationen,
die Rentalars mitbringt – die drei für Servicefälle und „Defektmeldung →
Servicefall“ –, sind Regeln wie eure eigenen: Du bearbeitest sie,
schaltest sie aus und ein und löschst sie mit denselben Rechten, im
Browser wie über die Schnittstelle, und jede Änderung steht im
Änderungsprotokoll. In der Liste tragen sie **„Standard“**, und
**„geändert“**, sobald sie von der Auslieferung abweichen – Ausschalten
zählt nicht, ebenso wenig der Name auf Deutsch oder auf Englisch. Oben im
Formular einer solchen Regel steht „Diese Automation kam mit Rentalars.“
bzw. „… und wurde seitdem geändert.“ Fehlt eine, steht oben in der Liste
**„Standard-Automationen wiederherstellen“**: Nach einer Rückfrage, die
nennt, was angelegt wird, legt Rentalars die fehlenden an, wie sie kamen,
eingeschaltet; vorhandene – geändert oder nicht – bleiben, wie sie sind.
Eine Regel von euch mit demselben Namen zählt dabei nicht als
mitgelieferte. Keine Aktualisierung legt eine gelöschte wieder an oder
überschreibt eine geänderte.

**Die Liste** zeigt unter **„Regeln“** jede Automation mit „Wenn“ und
„Dann“, wie oft sie lief und wie oft davon etwas fehlschlug; daneben
**„Bearbeiten“**, „Ausschalten“ bzw. „Einschalten“ und „Löschen“ – in
einer Reihe und gleich hoch, auch am Telefon. Über „Spalten“
blendest du die Spalte **„Herkunft“** ein („Standard“ oder „Standard,
geändert“). Im Formular einer Regel steht „Löschen“ neben „Automation
speichern“. Unter **„Ausführungen“**
steht jede Ausführung mit Zeitpunkt, Automation, Ereignis und Ergebnis –
„erledigt“, „ausgelassen“ mit Grund (etwa „hat heute schon eine Antwort
dieser Automation bekommen“) oder „fehlgeschlagen“ –, zu filtern nach
Automation und Ergebnis. Ausführungen bleiben ein Jahr, auch wenn ihre
Regel gelöscht ist. Eine Ausführung, die ein Neustart unterbricht, wird
nicht wiederholt, damit nichts doppelt hinausgeht. Wird ein Postfach
gelöscht, schalten sich die Regeln aus, die nur für dieses galten.

### Benachrichtigungen der Firma

Unter **Einstellungen → Benachrichtigungen** legst du für
die ganze Firma fest, wann Rentalars Fehlbestände meldet, wann es an noch zu schreibende Rechnungen erinnert, und wann
es an Zeiten zur Freigabe erinnert. Ob eine Person
sie in Rentalars, per E-Mail oder in der App bekommt, stellt sie weiter
unter Mein Konto → Benachrichtigungen ein (Abschnitt 15,
„Benachrichtigungen“). Ansehen darf die Seite, wer die Einstellungen lesen
darf; ändern, wer sie bearbeiten darf.

Im Kasten **„Fehlbestände“**:

- **Wie oft**: jeden Tag, an Werktagen (Montag bis Freitag, nicht an
  Feiertagen – es zählen die Feiertage unter Einstellungen → Zuschläge),
  einmal in der Woche an dem **Wochentag**, den du wählst, oder nie.
- **Uhrzeit**: Rentalars prüft binnen einer Minute nach dieser Uhrzeit.
- **Wie weit voraus (Wochen)**: Fehlbestände der Projekte, die innerhalb
  so vieler Wochen beginnen – 1 bis 26.
- **Bekannte Fehlbestände bei jeder Prüfung erneut melden**: Aus, meldet
  Rentalars jeden Fehlbestand einmal – erneut nur, wenn er größer wird
  oder behoben war und wiederkommt. An – voreingestellt –
  erinnert jede Prüfung außerdem an alle offenen, die schon gemeldet
  sind: in **einer** Nachricht je Projekt – bei einem Fehlbestand
  „Weiterhin Fehlbestand in …: 3 × Topteil fehlen“, bei mehreren
  „Weiterhin Fehlbestände in …: 7 Produkte“ mit der Liste im Text, eine
  Zeile je Produkt („2 × Topteil fehlen“). Neue oder größer gewordene
  Fehlbestände kommen weiter einzeln („Fehlbestand in …“). Wer das nicht will, schaltet sie hier aus.

Voreingestellt ist jeden Tag um 4:15 Uhr, vier Wochen voraus
und die Erinnerung an bekannte Fehlbestände. Unter den Feldern siehst du,
wann zuletzt geprüft wurde, wie viele Fehlbestände dabei gemeldet wurden
und wann die nächste Prüfung ist. Änderst du Uhrzeit oder Rhythmus, gilt
das ab dem nächsten Termin; eine Uhrzeit, die heute schon vorbei ist, wird
nicht nachgeholt. War der Server zur Zeit der Prüfung aus, holt Rentalars
sie einmal nach. Die Meldung geht an die Projektleitung und die
Mitglieder, die das Projekt bearbeiten dürfen; hat ein Projekt keine, an
alle, die Projekte ändern dürfen. Ein Fehlbestand, der schon gemeldet
wurde, bleibt bekannt, auch wenn sein Projekt inzwischen weiter als der
Vorlauf entfernt beginnt – kürzt du den Vorlauf oder verschiebst ein
Projekt, kommt er also nicht ein zweites Mal.

Im Kasten **„Rechnungen“** (Abschnitt 11, „Noch zu schreibende
Rechnungen“):

- **„An Rechnungen erinnern“** – eingeschaltet (voreingestellt), erinnert
  Rentalars an jedes abgeschlossene Projekt ohne Rechnung, bis die
  Rechnung da ist, „Rechnung gestellt“ angehakt oder das Projekt mit
  „Keine Rechnung nötig“ markiert ist.
- **„Uhrzeit“** – einmal am Tag um diese Uhrzeit; voreingestellt 9:00.
- **„Erste Erinnerung nach (Tagen)“** – Tage nach dem Abschließen;
  voreingestellt 1, 0 heißt am Tag des Abschließens.
- **„Danach wieder alle (Tage)“** – voreingestellt 7.
- **„Außerdem erinnern“** – eine Person, die neben der Projektleitung
  erinnert wird, und für Projekte ohne Projektleitung; leer nur die
  Projektleitung. Zur Wahl stehen nur Nutzer, die Preise sehen dürfen.
- **„Auch Servicefälle“** – erinnert auch an erledigte Servicefälle, an
  denen etwas zu berechnen ist; voreingestellt an.
  Erinnert wird nur an Fälle, die **nach dem Einschalten** erledigt
  wurden; frühere stehen weiter mit „Rechnung offen“ in den Listen, aber ohne
  Erinnerung. Schaltest du es aus und wieder ein, zählt der neue Zeitpunkt.

Darunter stehen die letzte und die nächste Prüfung mit der Zahl der
Projekte, an die erinnert wurde, und seit wann abgeschlossene Projekte
zählen; an früher abgeschlossene
Projekte erinnert Rentalars nicht.

Im Kasten **„Zeiten zur Freigabe“** (Abschnitt 13,
„Einreichen und freigeben“):

- **„An Zeiten zur Freigabe erinnern“** – eingeschaltet (voreingestellt),
  erinnert Rentalars alle, die Zeiten freigeben dürfen, an die
  eingereichten Zeiten und Spesen, die unter Personal → Freigeben auf sie
  warten – jeden nur an die, die er freigeben darf, nicht an die eigenen.
- **„Uhrzeit“** – voreingestellt 8:00.
- **„Erste Erinnerung nach (Tagen)“** – Tage nach dem Tag des Einreichens;
  voreingestellt 1, 0 heißt bei der nächsten Prüfung nach dem Einreichen.
- **„Danach wieder alle (Tage)“** – solange etwas wartet; voreingestellt 1,
  also jeden Tag.

Darunter stehen die letzte Prüfung mit der Zahl der erinnerten Personen und
die nächste. War der Server zur Zeit der Prüfung aus, holt Rentalars sie
einmal nach. Ob jemand die Erinnerung in Rentalars, per E-Mail oder gar
nicht bekommt, stellt er selbst unter Mein Konto → Benachrichtigungen ein
(„Zeiten warten auf meine Freigabe“).

### KI

**Einstellungen → KI** regelt, ob und womit Rentalars
Sprachmodelle nutzt – für die Zusammenfassung der Korrespondenz und
Antwortentwürfe (Abschnitt 14) und zum Lesen von Rechnungen in
„Kauf einpflegen“ (Abschnitt 4). **Alles ist aus, bis ihr es einschaltet.**
Den Kurzüberblick ohne KI gibt es immer. Ändern darf, wer die
Einstellungen ändern darf.

- **Lokale KI:** ein kleines Sprachmodell auf eurem eigenen Server. Mails,
  die es zusammenfasst, verlassen den Server nicht, und es kostet nichts
  je Aufruf. Einrichten kann es nur, wer den Server betreut – mit einem
  Befehl per SSH, den die Seite nennt (`sudo rentalars ai install`;
  Anleitung [„Betrieb“](../betrieb/betrieb.md), „KI“). Bis dahin steht dort „nicht installiert“.
  Danach zeigt die Seite Status, Modell und Server; **„Geschwindigkeit
  messen“** schickt eine Testfrage und zeigt, wie schnell die Antwort kam.
  **„Zusammenfassungen mit lokaler KI einschalten“** schaltet die
  Zusammenfassungen ein; derselbe Knopf schaltet sie wieder aus.

  Unter „Lokale KI“ stehen auch der **Prozessor** (physische
  und logische Kerne, ob AVX2 und FMA vorhanden sind) und die **gemessene
  Geschwindigkeit**: wie schnell die KI liest und schreibt, und wie lange
  eine Zusammenfassung von etwa 20 Mails damit dauert. „Geschwindigkeit
  messen“ misst beides neu; jede Zusammenfassung hält die Werte aktuell.
  Ist die KI zu langsam, empfiehlt Rentalars das kleinere Modell Qwen3
  1.7B und nennt den Befehl für den Server; das Modell wechselt nur, wer
  den Server betreut. Fehlen AVX2 oder FMA, läuft die KI um ein Vielfaches
  langsamer – in einer virtuellen Maschine den Prozessortyp auf „host“
  stellen (Proxmox: Hardware → Prozessoren → Typ: host) und die Maschine
  herunterfahren und wieder starten (Abschnitt 18, „Warum ist die lokale
  KI so langsam?“). Nach einem Update übernimmt der Server die
  Einstellungen der lokalen KI von selbst; neu installieren muss sie
  niemand.
- **Anwendungsfälle:** Für **„Zusammenfassung der Korrespondenz“**,
  **„Antwortentwurf für Mails“** und **„Rechnungen lesen“**
  wählst du je „Aus“, „Lokale KI“ oder eine der Schnittstellen darunter,
  dann „Anwendungsfälle speichern“. Alle sind anfangs aus. **„Rechnungen
  lesen“**: In „Kauf einpflegen“ liest die KI eine hochgeladene Rechnung
  (PDF mit Text) und schlägt Händler, Nummer, Datum, Summen und Positionen
  vor, mit Seriennummern und für neue Modelle mit Kategorie und
  Produkt; die Beträge liest Rentalars selbst, wie sie auf der Rechnung
  stehen. Du prüfst jede Zeile, bevor etwas angelegt wird. Aus, übernimmt
  Rentalars nur Nummer, Datum, einen bekannten Händler und die Summen aus
  dem Text (Abschnitt 4, „Kauf einpflegen“). Damit die KI Kategorie und
  Produkt wählen kann, nennt Rentalars ihr eure Kategorien und
  bis zu 40 eigene Produkte (kein Kundenmaterial). Liegt die gewählte Schnittstelle im Internet, steht
  darunter rot, dass der Text einer hochgeladenen Rechnung beim Lesen das
  Unternehmen verlässt – auf einer Rechnung stehen Preise, eure
  Kundennummer und Anschriften; mit ihr gehen auch die Namen eurer
  Kategorien und dieser Produkte hinaus. **Vorlagenvorschläge** – Vorschläge für
  Projektvorlagen aus früheren Projekten – stehen als „später“ da.
- **Schnittstellen (OpenAI-kompatibel):** für einen Server, der die
  Schnittstelle von OpenAI spricht – Ollama, LM Studio oder vLLM im
  Firmennetz oder ein Cloud-Dienst. **„Neue Schnittstelle“**: Name,
  Basis-URL, Modell, API-Schlüssel (er wird verschlüsselt gespeichert und
  nie wieder angezeigt), Zeitlimit und Kontextgröße. Das Zeitlimit sagt
, wie lange Rentalars wartet, wenn der Server nichts schickt –
  die Antwort selbst darf länger dauern. Eine Schnittstelle
  wird nur für die Anwendungsfälle genutzt, die du ihr zuweist. Liegt die
  Adresse im Internet, zeigt Rentalars rot **„Cloud – Daten verlassen das
  Unternehmen“**: Was ihr hinschickt – die Mails eurer Projekte,
  auf Wunsch der Text eurer Einkaufsrechnungen –, geht an diesen Dienst. Nimm ihn nur, wenn euer Vertrag mit ihm die Verarbeitung
  dieser Daten erlaubt; ob ihr dafür einen Vertrag zur
  Auftragsverarbeitung braucht, klärt ihr selbst. Eine Adresse im eigenen
  Netz geht nur, wenn der Server sie freigibt (Anleitung [„Betrieb“](../betrieb/betrieb.md),
  „Verbindungen ins interne Netz“).
- **Automatische Zusammenfassungen**: ein eigener Kasten auf
  der Seite mit dem Knopf **„Öffnen“**; die Seite heißt **„Automatische
  Zusammenfassungen“**. Wer die Einstellungen sehen darf, sieht sie, wer sie
  ändern darf, ändert sie. Ausgeschaltet, bis jemand **„Jede Nacht
  automatisch zusammenfassen“** ankreuzt – dazu muss unter „Anwendungsfälle“
  eine Zusammenfassung mit einer KI eingerichtet sein, und beim Einschalten
  musst du **„Ich habe gelesen, was an den Anbieter geht, und stimme zu“**
  ankreuzen. Oben steht **„Wohin die Daten gehen“**: an wen, ob die KI lokal
  ist, im Firmennetz oder ein Cloud-Dienst („Daten verlassen das
  Unternehmen“), **„Was gesendet wird“**, **„Vor dem Senden aus den Texten
  entfernt“** und **„Wird nie gesendet“** – der Text entsteht aus deinen
  Einstellungen und sagt, was wirklich geschieht. Wer eingeschaltet hat und
  wann, steht darunter. Die Zustimmung gilt für den **Server** der
  Zusammenfassung (die lokale KI oder Adresse samt Port), nicht für einen
  Namen: Wechselt die Zusammenfassung zu einem anderen Server, hält der
  Auftrag an, die Seite zeigt „angehalten: anderer Anbieter“, bis du erneut
  zustimmst. Eingestellt wird:
  - das **Zeitfenster** (**„Zeitfenster von“** und **„bis“**, voreingestellt
    1:00 bis 5:00; es darf über Mitternacht gehen), **höchstens so viele
    Zusammenfassungen pro Nacht** (20) und das **Token-Budget pro Nacht**
    (200 000; 0 = ohne Grenze) – der Auftrag hält an, wenn eines erreicht ist
    und macht in der nächsten Nacht weiter;
  - **Projekte in diesen Status** (voreingestellt alle außer „Abgeschlossen“ und
    „Storniert“) und **Servicefälle in diesen Status** (voreingestellt offen, „in Arbeit“,
    „wartet“ und „wartet auf Schließen“);
  - der **kürzeste Abstand zwischen zwei Zusammenfassungen** in Stunden (20), die
    **kleinste Zahl von Mails** (2) und wie viele **frühere
    Zusammenfassungen aufbewahrt** werden (5);
  - **„Was der Auftrag liest“**: **„Notizen aus der Korrespondenz lesen“** (an),
    **„Den Chat des Projekts lesen“** (aus) und **„Nachrichten mit Sperre
    lesen“** (an; die Oberfläche sagt hier „Sperre“ und meint das Schloss von
    Nachrichten, Abschnitt 14) – der Auftrag hat keinen Nutzer; diese Haken sind
    sein Umfang;
  - **„Für alle Zusammenfassungen“** (auch die von Hand): **„Namen angehängter
    Dateien mitschicken“** (an), **„Aus jedem Text entfernt, bevor er an die KI
    geht“** (voreingestellt alles: IBAN, Kartennummern, Geheimnisse,
    E-Mail-Adressen, Telefonnummern), der **längste Text pro Zusammenfassung**
    (150 000 Zeichen; bei mehr bleiben die ältesten Mails weg, und der Kasten
    sagt es) und **Zusammenfassungen von Hand je Nutzer und Stunde** (30).
  
  **„Zeigen, was zusammengefasst würde“** listet die Projekte, ohne eine KI zu
  fragen und ohne etwas zu speichern; **„Jetzt ausführen“** (nur bei
  gültiger Zustimmung) startet einen Lauf sofort, auch außerhalb des
  Zeitfensters. Unter **„Ausführungen“** stehen die letzten Läufe mit Ergebnis,
  Zahl der Zusammenfassungen, der unveränderten und der fehlgeschlagenen Projekte
  und den Token; ein Fehler bei einem Projekt hält den Lauf nicht an, das Projekt
  kommt in der nächsten Nacht wieder dran. Ein Lauf meldet sich nicht per
  Benachrichtigung. Den Auftrag startet der Zeitgeber des Servers (Anleitung [„Betrieb“](../betrieb/betrieb.md),
  `ai_summaries`), nachts im Zeitfenster. Was
  Anwender davon sehen, steht in Abschnitt 14, „Automatische
  Zusammenfassungen“.
- **Sicherheit der Schnittstellen**: Eine Schnittstelle im Internet
  braucht **https** – eine Adresse mit http wird beim Speichern abgelehnt,
  ebenso eine Weiterleitung; der API-Schlüssel erscheint nirgends im Klartext.
- **Protokoll der KI-Aufrufe** („Alle Aufrufe“): welcher Anwendungsfall
  wann welches Modell gefragt hat, wie lange es dauerte, wie viel Text hin
  und zurück ging und ob es klappte – **nie den Inhalt**. Es bleibt ein
  Jahr.

**Was es kostet.** Die lokale KI kostet nichts außer Strom und
Arbeitsspeicher auf eurem Server; eine Schnittstelle zu einem
Cloud-Dienst kostet, was der Anbieter je Aufruf verlangt.

### Stammdaten

- **Kategorien und Kürzel.** Eine gemeinsame Gliederung für Material und
  Produkte, beliebig tief („Ton > Mikrofone > Funkstrecken“). Nur
  **Hauptkategorien** tragen ein **Kürzel**; es wird zum Anfang der
  Artikelnummern. Ein Kürzel, mit dem es schon Artikelnummern gibt, lässt
  sich nicht mehr ändern, und die Kategorie nicht löschen – nur
  deaktivieren. An der Kategorie stellst du außerdem ein:
  - die **kategoriespezifischen Felder**: je Feld Position, Bezeichnung
    („Länge“), Typ (Text, Zahl mit Einheit, Auswahl, Ja/Nein), Einheit
    („m“) und bei „Auswahl“ die Auswahlwerte, einer je Zeile. Das Feld mit
    der kleinsten Position ist **die** kategoriespezifische Angabe, die in
    der Materialliste steht; alle weiteren erscheinen im Formular des
    Modells und lassen sich am Exemplar abweichend setzen (Abschnitt 4).
    Unterkategorien erben die Felder. Ein Zahlenfeld „Leistung“ in Watt
    nimmt Rentalars nicht an: Die Leistung hat jedes Modell als eigenes
    Feld „Leistung (W)“.
  - **Voreinstellungen für neue Produkte**: Produktart, Einheit, Steuerart,
    Abrechnungsart.
  - die **Staffel** der Kategorie und abweichende **Pufferzeiten**.
  - **„Kundenmaterial“** – nur an Hauptkategorien mit eigenem Bestand:
    Ihre Produkte gehören einem Kunden, haben einen Eigentümer und keinen
    Preis und lassen sich nur in Projekten dieses Kunden einplanen
    (Abschnitt 5, „Kundenmaterial“). Unterkategorien folgen ihrer
    Hauptkategorie. Der Haken lässt sich nur setzen oder herausnehmen,
    solange die Kategorie keine Produkte hat.
- **Staffeln:** siehe Abschnitt 5. Sie stehen im Kasten „Projekte und
  Personal“.
- **Steuerarten:** mitgeliefert sind 19 % und steuerfrei.
- **Einheiten:** mitgeliefert sind Stück (Miete), Stück (Verkauf), Set
  (Miete), Set (Verkauf), Stunde, Tag, Kilometer, Pauschal, Angefangener
  Liter, Angefangener Meter und Angefangenes Kilogramm. Auf Dokumenten
  steht die Abkürzung – „Stk.“, „Set“, „Std.“, „Tag“, „km“, „psch.“, „l“,
  „m“, „kg“ –; Miete und Verkauf unterscheidet nur Rentalars intern.
- **Steuerkonten**: die Konten, auf die die Kontierung der
  Eingangsbelege (Abschnitt 11, „Eingangsrechnungen“) einen Betrag bucht – je Konto
  eine **Kontonummer** (nur Ziffern, 3 bis 10 Stellen, einmalig) und ein
  **Name**; ein Konto lässt sich deaktivieren, dann wird es nicht mehr
  angeboten, bleibt aber dort stehen, wo es schon benutzt ist. Mitgeliefert ist
  eine Liste nach SKR 03; sie ist ein Vorschlag und gehört mit der
  Steuerberatung abgestimmt. Zu finden unter Einstellungen → Stammdaten →
  Steuerkonten, über die Schnittstelle unter `/tax-accounts`.
- **Hersteller** und **Händler** – die Händler sind zugleich die
  Lieferanten für Zumietungen, mit Name, Ansprechpartner, E-Mail, Telefon,
  „unsere Kundennummer dort“, Notiz und ihrer
  Anschrift („Straße und Hausnummer“, „Postleitzahl“, „Ort“, „Land“): Sie
  steht auf der Seite „Zumietung bei …“ mit Route und Karte, und zu ihr
  führt die Abholung bei den Fahrten eines Projekts (Abschnitt 7). An die
  E-Mail-Adresse knüpft
  Rentalars die Korrespondenz der Zumietungen (Abschnitt 9, „Zumieten“);
  „Zumietungen bei diesem Lieferanten anzeigen“ führt zu Planung →
  Fehlbestände, gefiltert auf ihn. Hersteller und Händler entstehen auch
  unterwegs – beim Tippen im Formular eines Modells und bei „Neue
  Exemplare“ (Abschnitt 4), im Dialog „Neuer Lieferant“ einer Zumietung
  (Abschnitt 9). Ein Händler mit Zumietungen
  oder Dokumenten lässt sich nicht löschen, nur deaktivieren.
- **Lagerorte** als Baum: Jeder Ort nennt, wovon er „Teil von“ ist –
  „Halle 1 > Regal A > Fach 3“, auch ein Case –, einer davon mit dem Haken
  „Standard für neue Exemplare“ (Abschnitt 4, „Lagerorte“).
- **Dokumentarten** für die Projektdateien: Bühnenplan, Rider, Ablaufplan,
  Hallenplan, Vertrag, Bestellung, Showfile,
  Sonstiges. Je Art ist eingestellt, ob solche Dateien der Crew gezeigt
  werden. Die Art „Showfile“ ist für Showfiles da: Dateien dieser Art
  nennen Pult oder Software, Version und welche die aktuelle Show ist
  (Abschnitt 11, „Dateien des Projekts“).
- **Prüfarten:** Name, **Abstand (Monate)**, Beschreibung („Was geprüft
  wird, nach welcher Norm“) und die **Kategorien** und **Materialmodelle**,
  für die sie gelten. Eine neue Prüfart macht alle ihre Exemplare
  überfällig, bis sie geprüft sind oder die letzte Prüfung nachgetragen ist
  (Abschnitt 4, „Prüfungen“). Der Haken
  **„elektrische Prüfung (DGUV V3 / DIN VDE 0701-0702)“** markiert die Prüfung
  elektrischer Geräte: Das Erfassen fragt dann Sichtprüfung, Messwerte,
  Funktionsprüfung und Prüfgerät ab, zeigt die Grenzwerte und schlägt das
  Ergebnis vor (Abschnitt 4, „Prüfungen“). Die Liste der Prüfarten zeigt
  den Haken als Spalte. Keine
  Prüfart ist elektrisch, bis jemand den Haken setzt.
- **Audits**: das **Audit-Intervall (Monate)** –
  voreingestellt 24, 0 schaltet Audits aus – und die **Schnellauswahl für
  To-Dos**, höchstens 12 (Abschnitt 4, „Audits und To-Dos“).
- **Eigene Felder** und **Feldsätze**: Felder mit einem
  eigenen Wert je Exemplar, etwa MAC-Adresse oder Prüfplakette, und ihre
  Zusammenstellung je Materialmodell (Abschnitt 4, „Eigene Felder“).
  Anders als die kategoriespezifischen Felder oben gilt ihr Wert nicht für
  das ganze Modell, sondern für das einzelne Stück.
- **Qualifikationsarten:** Führerscheine, Unterweisungen, Nachweise von
  Personen – Name, Beschreibung und **gültig für Monate** (leer: läuft
  nicht von selbst ab). Aus dem Erwerbsdatum und dieser Zahl rechnet
  Rentalars das Ablaufdatum aus (Abschnitt 12). Ein
  Führerschein nennt unter **„Führerscheinklassen“** die Klassen, die er umfasst,
  durch Kommas getrennt, etwa „B, BE“ – daran prüft die Logistik die Fahrer
  (Abschnitt 7, „Logistik“). Hat keine Qualifikationsart Klassen, wird
  nicht geprüft.

Stammdaten, die verwendet werden, lassen sich nicht löschen, nur
deaktivieren. Sie verschwinden dann aus den Auswahllisten.

**Was eine neue Installation mitbringt.** Neben den Einheiten oben die
Hauptkategorien mit ihren Voreinstellungen:

| Kategorie | Kürzel | eigener Bestand | neue Produkte |
|---|---|---|---|
| Ton, Licht, Video/Medien, Rigging/Traverse, Kabel | T, L, M, R, K | ja | Mietprodukt, Stück (Miete) |
| Verkauf | V | ja | Verkaufsprodukt, Stück (Verkauf) |
| Extern zugemietetes Material | E | nein | Zumietung, Stück (Miete) – mit dem Produkt E-001 „Zumietung“ |
| Veranstaltungstechnik-Dienstleistung | D | nein | Dienstleistung, Stunde – die Dienstleistungsprodukte der Funktionen |
| Fremdmaterial – markiert als „Kundenmaterial“ | C | ja | Mietprodukt, Stück (Miete), mit Eigentümer und ohne Preis |
| Nebenkosten | N | nein | Nebenkosten, Pauschal |
| Fuhrpark | FZ | ja | Fahrzeug, Stück (Miete) – die Fahrzeuge sind die Exemplare (Abschnitt 4, „Fuhrpark“) |

Dazu die **„Standardstaffel“** mit 1,0 / 1,5 / 1,75 / 2,0 / 2,4 / 2,75 /
3,5 für 1 bis 7 Tage und + 0,3 je weiterem Tag (Abschnitt 5, „Staffeln“),
der Lagerort **„Hauptlager“** als Standard für neue Exemplare, die acht
Funktionen Techniker, Lichttechniker, Tontechniker, Medientechniker,
Stagehand, Lager, Projektplanung und Sonstiges mit ihren
Dienstleistungsprodukten D-001 bis D-008 – mit dem Preis und
den internen Kosten je Stunde aus der Ersteinrichtung
(Abschnitt 12, „Funktionen“) –, die Dokumentarten samt „Showfile“ und die
Zuschläge mit den Sätzen nach § 3b EStG, ausgeschaltet (oben,
„Zuschläge“).

Prüfarten für Fahrzeuge bringt die Hauptkategorie FZ „Fuhrpark“ nicht mit; die legt ihr selbst
an (Abschnitt 4, „Fuhrpark“).

Beim **Produktimport** darf in der Spalte „Einheit“ auch „Stück“ oder
„Stk.“ stehen: Rentalars nimmt dann das Stück, das die Kategorie vorgibt –
im Ton „Stück (Miete)“, im Verkauf „Stück (Verkauf)“. Ein genau passender
Name geht immer vor.

### Dokumentvorlagen und Textbausteine

**Einstellungen → Dokumentvorlagen:** je Dokumentart Überschrift,
Einleitung, Schlusstext, zusätzliche Fußzeile und „Logo drucken“, mit
Platzhaltern wie `{project}`, `{due_date}` oder – beim Angebot –
`{valid_until}` und `{validity_days}`; beim Angebot außerdem die
**Gültigkeit in Tagen**, die ein neues Angebot vorschlägt (voreingestellt
14). **Einstellungen → Textbausteine:** Absätze wie
eure Mietbedingungen, die beim Erstellen eines Dokuments angehakt werden.
Beides ist in Abschnitt 11, „Vorlagen und Textbausteine“, beschrieben. Sieh
die mitgelieferten Texte einmal durch, bevor das erste Dokument entsteht.
**„Vorlagentexte auf Englisch oder Deutsch“** übernimmt die
mitgelieferten Überschriften, Einleitungen und Schlusstexte in der anderen
Sprache – eigene Texte nur, wenn du sie anhakst (ebenfalls Abschnitt 11).

### Buchhaltung: Lexware Office und DATEV

*Ansehen und die DATEV-Dateien holen darf, wer die Einstellungen lesen und
Preise sehen darf; ändern, wer die Einstellungen ändern darf (oben,
„Nur-Lesen und die Buchhaltung“).*

**Einstellungen → Buchhaltung** bringt Rechnungen und Stornorechnungen in
die Buchhaltung – einzeln als Belege nach **Lexware Office**, oder für die
Steuerberatung als **DATEV-Datei** je Zeitraum. Beides geht auch
zusammen.

**Lexware Office einrichten:**

1. In Lexware Office erstellt jemand mit Administratorrechten dort einen
   **API-Schlüssel** (Add-ons → Public API). Der Tarif muss die
   Buchhaltung enthalten.
2. Hier trägst du ihn unter **„API-Schlüssel“** ein. Rentalars speichert
   ihn verschlüsselt und zeigt ihn nie wieder an – nur „gespeichert, endet
   auf …“. Ein leeres Feld behält den gespeicherten Schlüssel.
3. **„Rechnungen an Lexware Office übergeben“** einschalten. Mit **„sofort
   übergeben“** geht jede neue Rechnung und Stornorechnung gleich beim
   Erstellen hinüber; ohne den Haken übergibst du von Hand im Reiter
   „Dokumente“ eines Projekts (Abschnitt 11, „An Lexware Office
   übergeben“).
4. **„auf den Sammelkunden buchen“**, wenn ihr eure Kunden in Lexware
   Office nicht einzeln führen wollt. Sonst sucht Rentalars jeden Kunden
   dort über die Kundennummer und legt ihn an, wenn es ihn nicht gibt.
5. **„Verbindung prüfen“** meldet, mit welcher Firma Rentalars verbunden
   ist, und holt die Buchungskategorien. Danach wählst du unter
   **„Buchungskategorie je Steuersatz“** die Kategorie; voreingestellt ist
   „Einnahmen“. Sieh vor allem die für 0 % einmal mit der Steuerberatung
   durch.

Unter **„Übergabe an Lexware Office“** stehen die Rechnungen, die gerade
warten oder deren Übergabe fehlgeschlagen ist, mit dem Fehler und
**„Erneut übergeben“**; „Nichts wartet, nichts ist fehlgeschlagen.“ heißt,
alles ist drüben.

**DATEV einrichten** – am besten zusammen mit der Steuerberatung:

- **Beraternummer** und **Mandantennummer**;
- **Wirtschaftsjahr beginnt im** – Januar, wenn es das Kalenderjahr ist;
- **Sachkontenlänge** – meist 4; Debitorenkonten haben eine Stelle mehr;
- **Kontenrahmen** – SKR 03 oder SKR 04;
- **Erlöskonten** je Steuersatz. Leer gelten die Standardkonten: SKR 03
  8400 (19 %), 8300 (7 %), 8336 (0 %), SKR 04 4400, 4300, 4336. Es sind
  Automatikkonten, DATEV bucht die Umsatzsteuer selbst; frag die
  Steuerberatung, bevor du sie änderst;
- **Debitorenkonten** – **„ein Debitorenkonto je Kunde“**: die
  Kundennummer plus der **„Zuschlag auf die Kundennummer“** (Kunde 10001
  wird mit 0 zum Debitor 10001, mit 10000 zum Debitor 20001); oder **„ein
  Sammel-Debitorenkonto für alle“** mit seiner Nummer, z. B. 10000.

**Der DATEV-Export.** Unter **„DATEV-Export“** wählst du den Zeitraum –
vorgeschlagen ist der vorige Monat – und siehst, wie viele Rechnungen und
Stornorechnungen darin liegen. Dann:

- **„Buchungsstapel“** – alle Rechnungen und Stornorechnungen mit einem
  Datum im Zeitraum, eine Buchung je Rechnung und Steuersatz. Eine
  stornierte Rechnung und ihre Stornorechnung sind zwei Belege, jeder im
  Zeitraum seines Datums. Der Zeitraum muss innerhalb eines
  Wirtschaftsjahres liegen.
- **„Debitoren des Zeitraums“** – die Kunden dieser Rechnungen mit
  Anschrift, USt-IdNr. und Zahlungsziel, wie sie jetzt in Rentalars
  stehen. Die Steuerberatung spielt sie vor dem ersten Buchungsstapel ein,
  wenn die Debitorenkonten in DATEV noch fehlen.

Beide Dateien sind CSV im DATEV-Format; die Steuerberatung liest sie in
DATEV Rechnungswesen ein und schreibt sie dort fest. Fehlt etwas – die
Beraternummer, ein Erlöskonto für einen Steuersatz, eine Kundennummer aus
Ziffern –, sagt Rentalars es, statt eine halbe Datei zu liefern.

**Rechnungen aus einem Altsystem**. Rechnungen, die ihr mit
„Altprojekte importieren“ übernommen habt (Abschnitt 11, „Altprojekte
importieren“), stehen **nicht** im Export, solange du über dem Export nicht
**„Aus einem Altsystem übernommene Rechnungen einschließen“** ankreuzt – dann
stehen sie im Buchungsstapel und in den Debitoren; über die Schnittstelle heißt
das `include_historic`. Sie lassen sich nicht an Lexware Office übergeben.

**Bitte prüft die erste Übergabe und den ersten Import.** Die Formate von
Lexware Office und DATEV sind nach deren veröffentlichten Beschreibungen
gebaut. Seht euch den ersten Beleg in Lexware Office an und lasst die
Steuerberatung den ersten Buchungsstapel prüfen, bevor ihr euch darauf
verlasst.

### Änderungsprotokoll

**Einstellungen → Änderungsprotokoll** zeigt jede Änderung an den Daten:
wer, wann, was – mit altem und neuem Wert. Filtern lässt sich nach Art des
Objekts, Nutzer, Zeitraum und Text.

Einträge von „system:…“ stammen von Rentalars selbst: `system:import` vom
Import auf dem Server, `system:setup` von der Ersteinrichtung. Ein Import im
Browser steht unter dem Namen dessen, der ihn gestartet hat. Einträge von
„Aktualisierung …“ hat eine Aktualisierung geschrieben.
Einige dieser Einträge nennen einen Verweis als Text,
etwa „D-001“; solche Werte stehen als Text da.

Die Sätze der Zuschläge in einem Eintrag sieht nur, wer sie auch unter
Einstellungen → Zuschläge sehen darf (oben, „Zuschläge“).

Das Protokoll lässt sich nicht bearbeiten. Voreingestellt bleibt es
dauerhaft; eine kürzere Frist ist unter „Aufbewahrungsfristen“ möglich.

### Sicherheitsprotokoll

**Einstellungen → Sicherheitsprotokoll:** wer sich wann angemeldet und
abgemeldet hat, fehlgeschlagene Anmeldungen (mit dem eingegebenen Namen),
falsche Codes der Zwei-Faktor-Anmeldung, benutzte Wiederherstellungscodes,
beendete Sitzungen, Passwortänderungen, festgelegte Einmal-Passwörter,
Abmeldungen nach Inaktivität – je mit Adresse und Browser. Filter nach Art
und nach Name oder Adresse. Darunter die letzten Änderungen an Nutzern,
Rollen und Tokens. Einträge werden nach der eingestellten Frist gelöscht,
voreingestellt nach 365 Tagen (unten, „Aufbewahrungsfristen“).

### Zugriffsprotokoll

Das Änderungsprotokoll sagt, wer etwas *geändert* hat. Für den Datenschutz
zählt aber auch, wer etwas *angesehen* hat. **Einstellungen →
Zugriffsprotokoll** hält fest, wer

- Kunden, Personen und Projekte geöffnet hat – bei Projekten auch ihre
  Mails, Dateien und Dokumente,
- Listen als CSV heruntergeladen,
- den vollständigen Export oder eine Sicherung heruntergeladen hat –

im Browser wie über die API, mit Zeitpunkt und Art des Zugriffs. Liest
dieselbe Person denselben Datensatz innerhalb von fünf Minuten mehrmals,
zählt das einmal. Was eine Person über sich selbst ansieht, steht nicht
darin.

Filtern lässt sich nach Nutzer, „Art des Objekts“, „Zugriff“, Zeitraum und
Text (Name, Nummer oder IP-Adresse); ein Klick auf ein Objekt in der Liste
zeigt nur die Zugriffe darauf, „mit allem, was dazugehört“ – bei einem
Projekt also auch auf seine Mails und Dateien. Das Protokoll gibt es auch
als CSV. Voreingestellt bleibt es 180 Tage (unten,
„Aufbewahrungsfristen“). Wird ein Kunde oder eine Person anonymisiert,
verschwindet der Name auch hier.

### Aufbewahrungsfristen

Wie lange Rentalars Protokolle und Nebenprodukte aufhebt, stellst du unter
**Einstellungen → Firmendaten und Grundeinstellungen** ein. Die tägliche
Wartung räumt danach auf.

| Einstellung | voreingestellt | erlaubt |
|---|---|---|
| Sicherheitsprotokoll aufbewahren (Tage) | 365 | 30 bis 3.650 |
| Änderungsprotokoll aufbewahren (Tage) | 0 – dauerhaft | 0 oder bis 36.500 |
| Benachrichtigungen aufbewahren (Tage) | 180 | 7 bis 3.650 |
| Ergebnisse von Hintergrundaufgaben aufbewahren (Tage) | 7 | 1 bis 365 |
| Zugriffsprotokoll aufbewahren (Tage) | 180 | 30 bis 3.650 |

Das Mail-Protokoll folgt der Frist der Mails im Postfach (Abschnitt 14).
Die Ausführungen von Automationen bleiben fest ein Jahr (oben,
„Automationen“).

Bedenke beim Änderungsprotokoll: Aus ihm entstehen auch die Reiter
„Verlauf“ an Projekten, Exemplaren, Produkten und Kunden. Eine Frist kürzt
also auch sie. Die Ergebnisse von Hintergrundaufgaben – Importberichte,
Etiketten-PDFs, vollständige Exporte – verschwinden samt ihren Dateien.
Erstellte Dokumente (Abschnitt 11) sind von keiner Frist betroffen; sie
bleiben immer.

### Import und Export

**Einstellungen → Import und Export** sammelt alles, was Daten nach
Rentalars hinein- oder herausbringt.

**Importieren** lassen sich vier Listen, jede aus einer **XLSX**- oder
**CSV**-Datei mit einer Überschriftenzeile und einer Zeile je Datensatz.
Eine CSV-Datei darf in UTF-8 oder – wie aus Lexware, DATEV oder älterem
Excel – in Windows-1252 sein; Umlaute kommen in beiden Fällen richtig an. Eine Tabelle darf höchstens 100.000 Zeilen und 3 Millionen Zellen haben (gelesen: höchstens 300.000 Zeilen, leere eingerechnet – löschen Sie leere Zeilen unter den Daten –, und eine XLSX-Datei nur bis Spalte 199) und eine XLSX-Datei entpackt höchstens 200 MB; größere Dateien weist Rentalars beim Lesen ab (teile sie auf mehrere auf).

| Liste | Wo noch | Erkannt wird ein vorhandener Datensatz an … |
|---|---|---|
| Material importieren | Materialverwaltung → Import | der ID (Anleitung [Übernahme der Materialliste](../betrieb/import.md)) |
| Produkte importieren | Materialverwaltung → Import, Reiter „Produkte“ | der **Artikelnummer** |
| Kunden importieren | „Import“ über der Kundenliste | der **Kundennummer**, sonst **USt-IdNr.**, **E-Mail-Adresse** oder **Name** |
| Personal importieren | „Import“ über der Personenliste | der **E-Mail-Adresse**, sonst **Vor- und Nachname** |

Jeder Import braucht das Recht, im jeweiligen Modul anzulegen und zu
bearbeiten; die Einstellungen zeigen nur die Importe, die du starten
darfst. Daneben steht zu jeder Liste, die du lesen darfst, der
**„Export im Importformat“** (unten).

**So geht's – bei allen vier gleich:**

1. **Datei wählen**, „Datei hochladen“. „Welche Spalten werden erkannt?“
   zeigt, welche Überschriften Rentalars von selbst zuordnet.
2. **Spalten zuordnen.** Je Feld steht die Spalte der Datei, die Rentalars
   erkannt hat, daneben die ersten Werte. Passt etwas nicht, wählst du eine
   andere Spalte oder „– nicht importieren –“. Mit * markierte Felder sind
   Pflicht. Beim Material fragt dieser Schritt außerdem, ob die
   Kaufpreise der Datei netto oder brutto sind (Abschnitt 4, „Die
   Excel-Liste übernehmen“).
3. **„Probelauf: prüfen, ohne zu schreiben“.** Er läuft im Hintergrund; die
   Seite zeigt den Fortschritt, und du kannst weiterarbeiten. Danach steht
   da, was der Import tun würde – „12 neu, 340 geändert, 5 unverändert“ –,
   welche Zeilen Fehler haben und welche Hinweise es gibt, und
   darunter unter **„Zeilen der Datei“** jede Zeile mit ihrem Ergebnis
   (unten, „Jede Zeile im Probelauf“).
4. Erst wenn der Probelauf **keine Fehler** gefunden hat, erscheint unter
   der Liste **„Jetzt importieren“**. Der Import macht genau das, was der
   Probelauf gezeigt hat, und läuft ebenfalls im Hintergrund.

**Jede Zeile im Probelauf**. Die Liste „Zeilen der Datei“ –
nach dem Import „Importierte Zeilen“ – nennt je Zeile ihre Nummer, den
Datensatz (ID, Artikelnummer, Name …), das Ergebnis – **„neu“**,
**„geändert“**, **„unverändert“** oder **„Fehler“** – und die
Einzelheiten: bei einer geänderten Zeile jedes Feld mit **„bisher“** und
**„neu“**, geschrieben wie im Änderungsprotokoll (12.03.2021, 499,00 €,
„ja“/„nein“), bei einem Fehler die Meldung, dazu die Hinweise der Zeile.
Unter **„Anzeigen“** wählst du „Alle außer unveränderten“ (voreingestellt,
wenn es andere gibt), „Alle“, „Neu“, „Geändert“, „Unverändert“ oder
„Fehler“, jeweils mit ihrer Zahl; das Feld **„Zeile, ID oder Name“** sucht,
„Filtern“. Es sind 200 Zeilen je Seite. Werte, die du nicht sehen darfst –
Einkaufspreise, Preise und Rabatte, Stunden- und Tagessätze –, stehen als
**„nicht sichtbar“** da. Nach dem Import zeigt die Seite die importierten
Zeilen; filtern und blättern geht dort genauso.

**Alles oder nichts:** Hat eine einzige Zeile einen Fehler, schreibt
Rentalars nichts. Korrigiere die Datei oder die Zuordnung und versuche es
noch einmal („Andere Datei verwenden“ beginnt von vorn). Geschrieben wird
nur, was einer Spalte zugeordnet ist; alle anderen Angaben bleiben, wie sie
sind. Im Änderungsprotokoll stehen die Änderungen mit deinem Namen.

**Was vorhanden ist, wird aktualisiert, nie verdoppelt:**

- **Produkte:** Die Artikelnummer entscheidet – ein vorhandenes Produkt
  wird aktualisiert, ein neues angelegt. Ihre Buchstaben nennen die
  Hauptkategorie; die Spalte „Kategorie“ kann eine Unterkategorie nennen.
  Einheit, Steuerart, Produktart und Abrechnungsart werden am Namen
  erkannt; was die Datei nicht nennt, kommt aus den Voreinstellungen der
  Kategorie. Eine Einheit ohne ihren Klammerteil oder mit einer Abkürzung,
  die mehrere Einheiten teilen – „Stück“, „Stk.“ –, wird die Einheit, die
  die Kategorie vorgibt (Abschnitt 16, „Stammdaten“). Die Spalten „Preis“,
  „Verkaufspreis“ und „Höchstrabatt“ brauchen das Recht „Preise und
  Kalkulation sehen“. Jedes Produkt hat genau einen Preis
  (Abschnitt 5, „Ein Produkt anlegen“): Bei einem Verkaufsprodukt füllt die
  Spalte „Preis“ seinen Verkaufspreis, wenn „Verkaufspreis“ leer ist; einen
  Verkaufspreis für ein anderes Produkt übergeht der Import mit einem
  Hinweis. Die Spalte **„Eigentümer“** nennt bei Kundenmaterial
  den Kunden – mit Kundennummer oder Namen; heißen mehrere Kunden gleich,
  nimm die Kundennummer. Ein Produkt einer Kategorie für Kundenmaterial
  braucht einen Eigentümer und keinen Preis; eine leere Zelle heißt
  „eigenes Material“ (Abschnitt 5, „Kundenmaterial“). Eine neue
  **Dienstleistung** bringt ihre Funktion mit; einen Namen, den schon eine
  Funktion trägt, lehnt der Probelauf ab. Die Art „Nebenkosten“ erkennt
  der Import an diesem Namen, die Art „Fahrzeug“ an „Fahrzeug“ oder
  „Fuhrpark“; deren Sätze stehen in den Spalten „Fahrzeugart“,
  „Preis je km“, „Anhängerzuschlag je km“ und „Anhänger abrechnen“
  (Preisrecht), ihre Kosten in „Interne Kosten je km“ und „Interne Kosten
  je Tag“ (Recht für Einkaufspreise).
- **Kunden:** Jede Zeile sucht den Kunden, den sie beschreibt – der Reihe
  nach an der **Kundennummer**, der **USt-IdNr.**, der **E-Mail-Adresse**
  (des Kunden oder eines Ansprechpartners) und am **Namen**. Beim Namen
  zählen Groß- und Kleinschreibung, Satzzeichen, Rechtsform und die
  Schreibweise der Umlaute nicht: „Müller GmbH“ ist „MUELLER gmbh“. Eine
  Privatperson wird nie einer Firma zugeordnet und umgekehrt. Ein
  gefundener Kunde wird **ergänzt statt verdoppelt**:
  - **Leere Zellen überschreiben nichts** – was Rentalars schon weiß,
    bleibt. (Ein Feld lässt sich über den Import deshalb nicht leeren.)
  - Ansprechpartner kommen dazu, wenn es noch keinen mit demselben Namen
    oder derselben E-Mail-Adresse gibt, sonst werden sie ergänzt; ebenso
    eine Lieferadresse.
  - Hat sich die Anschrift geändert, bleibt die bisherige als weitere
    Rechnungsadresse erhalten.
  - Findet Rentalars einen Kunden an USt-IdNr., E-Mail oder Namen, der in
    der Datei eine andere Nummer hat, behält er seine Nummer in Rentalars.

  Eine Zeile ohne Treffer wird ein neuer Kunde: mit der Nummer aus der
  Datei, wenn Rentalars sie noch nicht kennt – so behalten Kunden aus dem
  alten Programm ihre Nummer –, sonst mit der nächsten Nummer. Passen
  mehrere Kunden, legt Rentalars lieber einen neuen an und sagt, welche in
  Frage kamen. Der **Probelauf** zeigt je Zeile, was geschieht: neu,
  zusammengeführt mit welchem Kunden und woran erkannt („zusammengeführt
  mit 10042 „Kulturverein“ (gefunden über die E-Mail-Adresse)“), oder
  unverändert. Die Spalte „Ansprechperson“ (mit E-Mail und Telefon) legt
  den Hauptkontakt an oder aktualisiert ihn. „Standardrabatt %“ braucht das
  Preisrecht.
- **Kunden aus Lexware:** Den **Kontaktexport** von Lexware (CSV) lädst du
  unverändert hoch. Rentalars erkennt seine Spalten von selbst –
  „Firmenname“, „Straße 1“, Lieferadresse („… 2“), Steuernummer,
  USt-IdNr., „Ansprechpartner 1 Vorname“ mit Anrede und so weiter. Adresse
  1 wird die Hauptadresse, Adresse 2 eine Lieferadresse; eine zweite
  E-Mail-Adresse oder Telefonnummer landet in der Notiz. Die
  Lieferantennummer übernimmt Rentalars nicht, und der Bericht sagt es.
  Lexware zählt Kundennummern ebenfalls ab 10001 – stimmt bei einer Zeile
  nur die Nummer, aber weder Name, USt-IdNr. noch E-Mail, warnt der
  Probelauf, denn dann ist es wahrscheinlich ein anderer Kunde.
- **Personal:** Eine Person wird an ihrer E-Mail-Adresse erkannt, sonst an
  Vor- und Nachname; erkannte werden aktualisiert, die übrigen angelegt.
  Der Name kann in einer Spalte stehen („Nachname, Vorname“ wie im Export,
  oder „Vorname Nachname“) oder in zweien. Die Spalte **„Funktionen“**
  zählt die Funktionen durch Kommas getrennt auf. Eigene Sätze stehen
  hinter einem Doppelpunkt, der Stundensatz und nach einem Schrägstrich
  der Tagessatz: `Tontechnik: 35,00/280,00, Licht: /250, Rigging` –
  Tontechnik mit 35,00 € die Stunde und 280,00 € am Tag, Licht nur mit
  Tagessatz, Rigging ohne eigene Sätze (es gelten die Richtwerte). Die
  Funktionen müssen unter Personal → Funktionen schon angelegt sein. Sätze
  braucht das Recht „Stundensätze und Personalkosten sehen“. Hat eine
  Person die Funktion schon, gelten andere Sätze aus der Tabelle ab heute;
  was die Zeile nicht nennt, bleibt. Der Import nimmt nie eine Funktion
  weg. Neu angelegte
  Personen bekommen wie von Hand angelegte ihre Anmeldung mit der Rolle
  Crew bzw. Freie Kraft, aber keine Einladung – die schickst du danach
  (Abschnitt 16, „Nutzer“).

**Hin und zurück.** Eine Liste, die du als CSV aus der Produkt-, Kunden-
oder Personenliste herunterlädst (Abschnitt 2, „Listen“), erkennt der
Import wieder: herunterladen, in der Tabellenkalkulation ändern, wieder
einlesen. Mit „CSV mit allen Spalten“ heruntergeladen, lässt sich jede der
drei Listen auch unverändert wieder einlesen – die Überschriften ordnet
der Import von selbst zu. Genau dafür gemacht ist der Export
im Importformat (unten).

Im Browser gibt es keine Grenze für die Zahl der Zeilen. Wer den Server
betreut, kann Listen auch dort einlesen:
`rentalars import_data products|customers|people DATEI` (Anleitung
„Betrieb“).

**Exportieren.** Jede Liste lässt sich als CSV herunterladen (Abschnitt 2,
„Listen“), so wie du sie siehst.

**Export im Importformat**. Zu jedem der vier Importe –
Material, Produkte, Kunden, Personal – gibt es den Link **„Export im
Importformat“**, hier neben dem Import und oben auf der Seite des Imports
selbst. Er lädt eine CSV-Datei herunter mit **genau den Spalten und
Überschriften des Imports**, im **Klartext**, so dass du auch ohne
Rentalars mit ihr weiterarbeiten kannst:

- Namen und Nummern statt interner IDs – Kategorie und Lagerort als Pfad
  („Ton > Mikrofone“, „Halle 1 > Regal A“), Händler, Einheit und
  Steuerart mit ihrem Namen, der Eigentümer von Kundenmaterial mit seiner
  Kundennummer, die Funktionen einer Person mit ihren heute geltenden
  Sätzen wie im Import;
- Datum als `31.12.2027`, Zahlen mit Dezimalkomma ohne Tausenderpunkt,
  „ja“ und „nein“, Auswahlwerte mit ihren deutschen Namen – auf Deutsch
  wie die Überschriften des Imports, auch wenn du Rentalars auf Englisch
  benutzt;
- beim Material eine Spalte je eigenem Feld, mit dessen Namen als
  Überschrift (Abschnitt 4, „Eigene Felder“), und die Spalte
  „Schutzklasse“ mit der Klasse, die für das Exemplar gilt – seine eigene,
  sonst die des Modells – als `I`, `II` oder `III` (Abschnitt 4, „Die
  Excel-Liste übernehmen“).

Spalten mit Preisen, Kaufpreisen oder Stunden- und Tagessätzen stehen nur
darin, wenn du sie sehen darfst; sonst fehlt die Spalte – bei den
Personen nennt „Funktionen“ dann die Funktionen ohne Sätze –, und ein
Import dieser Datei lässt diese Werte, wie sie sind. Text, den eine
Tabellenkalkulation als Formel ausführen würde, bekommt einen Apostroph
davor; der Import nimmt ihn wieder weg. **Wieder importiert, ändert die
Datei nichts** – der Probelauf nennt jede Zeile „unverändert“; in der
Tabellenkalkulation bearbeitet, ändert sie, was du geändert hast. Was der
Import nicht kennt, steht nicht darin – etwa ein vierter Ansprechpartner
eines Kunden oder die Positionen der Projekte; dafür gibt es den
lesbaren Export aller Daten. Herunterladen darf, wer die Liste lesen darf.
Auch 20.000 Exemplare sind in wenigen Sekunden da.

**Alle Daten auf einmal** – den **„Lesbaren Export aller Daten“** – findest
du unter **Einstellungen →
Sicherung** (unten, „Sicherung und Verschlüsselung“).

### Aufgaben im Hintergrund

Was länger dauert, lässt Rentalars im Hintergrund laufen, damit keine Seite
warten muss: **Probeläufe und Importe**, **mehr als 240 Etiketten**, den
**vollständigen Export**, **Sicherungen aus dem Browser** und die
**Übergabe einer Rechnung an Lexware Office**. Du kannst
währenddessen weiterarbeiten; ist die Aufgabe fertig, bekommst du eine
Benachrichtigung („Fertig: …“ oder „Fehlgeschlagen: …“).

**Mein Konto → „Aufgaben im Hintergrund“** listet deine Aufgaben der
letzten Tage mit „Gestartet“ und Status – „wartet“, „läuft“, „fertig“ oder
„fehlgeschlagen“. Ein Klick zeigt den Fortschritt, solange sie läuft, und
danach das Ergebnis mit „Herunterladen“, wo eine Datei entstanden ist.
Eine Aufgabe und ihr Ergebnis sieht nur, wer sie gestartet hat – auch
Administratoren sehen die Aufgaben anderer nicht. Nach der
Aufbewahrungsfrist (voreingestellt sieben Tage) räumt Rentalars sie samt
Dateien weg.

### Selbsttest

**Einstellungen → Selbsttest:** der Zustand der Installation – Versionen,
Datenbank, Dateirechte, E-Mail, letzte Sicherung, Speicherplatz,
Sicherheitseinstellungen und Fehler der letzten sieben Tage. Jede Zeile
mit ✓ (in Ordnung), i (Hinweis), ! (Warnung) oder ✗ (Fehler). „Testmail an
mich senden“ prüft den Versand, „Erneut prüfen“ prüft noch einmal. Ist
kein Mailserver eingerichtet, warnt die Zeile „Systemmails“ unter
„E-Mail“: Einladungen, Passwort-Links und Benachrichtigungen gehen dann
nicht hinaus; die Testmail meldet „Nicht versendet – kein
Mailserver eingerichtet.“ statt „gesendet“ (Abschnitt 14, „Ohne
Mailserver“). Was die
einzelnen Punkte bedeuten und was zu tun ist, steht in der Anleitung
„Betrieb“; Fehler meldet Rentalars den Administratoren außerdem von
selbst.

Es gibt die Gruppe **„Gateway“**: Ist ein Gateway verbunden, zeigt sie
seine Adresse, ob es antwortet (Fehler, wenn die letzte Antwort älter als 90
Sekunden ist – dann läuft der Dienst des Servers nicht), den letzten Fehler und
die Zahl der gekoppelten und gesperrten Apps. Ohne Gateway steht dort „keine –
die Apps erreichen den Server direkt“.

Die Gruppe **„Versionen“** nennt auch **ffmpeg**, das
Programm, mit dem der Server Videos für den Chat verkleinert; fehlt es,
warnt die Zeile – dann werden nur Videos abgelehnt, Fotos gehen. Und die
Zeile **„NGINX: Größe beim Hochladen“** warnt, wenn NGINX kleinere
Dateien annimmt als ein Video im Chat haben darf (200 MB). Beides
erledigt, wer den Server betreut (Anleitung [„Betrieb“](../betrieb/betrieb.md)).

Die Gruppe **„Server“** zeigt, worauf Rentalars läuft:

- **Prozessoren** – wie viele, und die Last der letzten 1, 5 und 15
  Minuten; liegt die Last über dem Doppelten der Prozessoren, warten
  Anfragen auf einen Prozessor, und es gibt eine Warnung;
- **Arbeitsspeicher** – gesamt und frei, mit einer Warnung, wenn er knapp
  wird;
- **Speicher von Rentalars** – wie viel die Prozesse der Anwendung
  belegen;
- **Rechnername**, **Netzwerk** je Schnittstelle mit Adressen und der seit
  dem Start empfangenen und gesendeten Datenmenge, **Laufzeit** seit dem
  letzten Neustart.

**Raspberry Pi.** Rentalars läuft auch auf einem
Raspberry Pi 4 oder 5 (64 Bit, ab 4 GB Arbeitsspeicher, am besten mit SSD)
– mit Ubuntu Server für den Pi oder mit Raspberry Pi OS auf Basis von
Debian 13. Wie man ihn vorbereitet und was anders ist, steht in der
Anleitung [„Installation“](../betrieb/installation.md), Abschnitt „Raspberry Pi“. Auf einem Pi zeigt der
Selbsttest unter „Server“ die Zeile **„Gerät“** mit dem Modell – mit einem
Hinweis, wenn er weniger als 4 GB hat – und unter „Speicherplatz“ den
Hinweis **„SD-Karte“**, wenn Datenbank, Datenordner oder Sicherungen auf
der SD-Karte liegen.

**Sicherheit → HTTPS.** Unter „Sicherheit“ zeigt die Zeile „HTTPS“ die
Adresse der Installation mit ✓. Ein Server startet nur mit
einer Adresse, die mit https:// beginnt – außer der Betreiber hat
unverschlüsseltes HTTP in der Konfigurationsdatei bewusst erlaubt
(`allow_http = yes`); dann steht hier eine Warnung: Passwörter und
Sitzungen gehen unverschlüsselt durchs Netz, außer ein vorgeschalteter
Server verschlüsselt sie.

**Verbindungen zu anderen Servern**. Rentalars verbindet sich
zu verknüpften Kalendern, zu CalDAV-Kalendern, zu Webhooks, zu den
Mailservern der Postfächer und zu den Schnittstellen der KI
nur, wenn die Adresse nicht ins interne Netz
führt – also nicht zu diesem Rechner, nicht in private Netze (etwa
192.168.x.x oder 10.x.x.x) und nicht zum Server selbst. Ein NAS oder eine
Nextcloud im eigenen Netz geht trotzdem, wenn der Betreiber sie in der
Konfigurationsdatei freigibt (`[network] allow_internal`). Diese Gruppe
nennt unter **„Interne Adressen“** jede Einstellung, die ins interne Netz
führt, ohne freigegeben zu sein – mit der Adresse, zu der der Name
gehört, und der Art des Netzes –, und unter **„Erlaubte interne
Adressen“**, was freigegeben ist.
Rentalars löscht oder ändert nichts davon; die Einstellung schlägt fehl,
bis der Betreiber die Adresse freigibt oder jemand die Einstellung ändert.

Der Knopf „Sicherung und Verschlüsselung“ führt zur gleichnamigen Seite.

### Sicherung und Verschlüsselung

**Einstellungen → Sicherung** bzw. **→ Verschlüsselung** – eine Seite mit
zwei Teilen, mit einem dritten: dem lesbaren Export aller
Daten (unten).

**Sicherung.** Jede Nacht um 2:30 Uhr sichert der Server Datenbank und
Dateien von selbst nach `/var/backups/rentalars`. Die Seite zeigt, wann die
letzte nächtliche Sicherung entstand und ob sie verschlüsselt ist.
Kopiert diese Dateien regelmäßig auf ein anderes Gerät – eine Sicherung
auf derselben Platte übersteht deren Verlust nicht.

**Konsistent.** Die Sicherung schreibt erst die Datenbank, dann die
Dateien. Eine Datei, die jemand dazwischen löscht, würde in der Datenbank der
Sicherung noch stehen und in den Dateien fehlen. Darum wandert eine gelöschte
Datei zuerst für **sieben Tage** in den Ordner `.deleted` der Dateien, den die
Sicherung mitnimmt; die tägliche Wartung löscht sie danach endgültig. So ist
alles, was die Datenbank einer Sicherung nennt, auch in ihr.

**„Sicherung jetzt erstellen“** schreibt dieselbe Datei wie die
nächtliche Sicherung – Datenbank, alle gespeicherten Dateien, die
Konfigurationsdatei und die Version – zum **Herunterladen**, etwa vor einer
größeren Änderung. Das dauert eine Weile und läuft im Hintergrund; unter
**„Deine Sicherungen aus dem Browser“** erscheint sie, sobald sie fertig
ist. Erstellen darf, wer in den Einstellungen löschen darf;
**herunterladen kann sie nur, wer sie erstellt hat**. Nach der Frist für
Aufgaben im Hintergrund (voreingestellt sieben Tage) löscht Rentalars sie;
die nächtliche Sicherung nimmt sie nicht mit. Auf dem Server spielt ihr
sie mit `sudo rentalars restore DATEI` ein.

- **Sind die Sicherungen verschlüsselt**, liegt auch der Auszug der Datenbank
 nie unverschlüsselt auf der Platte – nicht einmal kurz im
  temporären Ordner –, und die Datei bekommt einen **eigenen
  Schlüssel**: Er steht bei der fertigen Sicherung („Schlüssel dieser
  Sicherung – zum Kopieren anklicken“) und nur für dich. Bewahre ihn
  getrennt von der Datei auf; ohne ihn lässt sich die Sicherung nicht
  öffnen, von niemandem. Einspielen mit
  `sudo rentalars restore DATEI --key-file SCHLÜSSELDATEI` – oder du tippst
  den Schlüssel ein, wenn der Befehl danach fragt.
- **Sind sie es nicht**, sagt die Seite es: Die Datei enthält die
  personenbezogenen Daten aller und die Zugangsdaten der Datenbank – heb sie
  so sicher auf wie den Server selbst.

**Verschlüsselung.** Die Seite zeigt, ob die **Datenbank** und **neue
Sicherungen** verschlüsselt sind, ob die letzte nächtliche Sicherung es
war und wo der **Wiederherstellungsschlüssel** liegt. Läuft die Datenbank
auf einem anderen Server, entscheidet dieser über die Verschlüsselung
ihrer Dateien.

Einen Knopf zum Einschalten gibt es bewusst nicht („Warum es dafür keinen
Knopf gibt“): Das Einschalten ändert die Einstellungen von MariaDB,
startet die Datenbank neu und legt einen Schlüssel ab, den nur root lesen
darf. Rentalars selbst läuft absichtlich ohne diese Rechte – so könnte
selbst jemand, der ein Administratorkonto übernimmt, weder den
Datenbankserver ändern noch den Schlüssel lesen. **„So schaltest du sie
ein“** erklärt den Befehl `sudo rentalars encryption enable` auf dem
Server (als root): Er schreibt zuerst eine Sicherung des jetzigen Stands,
hält Rentalars kurz an und lässt MariaDB jede Tabelle verschlüsseln,
vergleicht danach jede Tabelle mit dem Stand vorher – Rentalars startet
erst wieder, wenn kein einziger Wert abweicht – und verschlüsselt die
vorhandenen und alle künftigen Sicherungen. Am Ende zeigt er den
Wiederherstellungsschlüssel – schreib ihn auf und bewahre ihn getrennt vom
Server auf. Ist die Verschlüsselung eingeschaltet, steht statt der
Anleitung, wie der Schlüssel auf dem Server wieder angezeigt wird. Mehr in
den Anleitungen [Verschlüsselung](../betrieb/verschluesselung.md) und
[Sicherung](../betrieb/sicherung.md).

**Lesbarer Export aller Daten.**
**„Vollständigen Export erstellen“** schreibt alle
Daten und Dateien in offenen Formaten in **eine ZIP-Datei**:

- `json/` – jede Tabelle als JSON-Datei;
- `csv/` – dieselben Tabellen als CSV für die Tabellenkalkulation, eine
  Spalte je Feld, Verweise auf andere Tabellen als interne ID;
- `dateien/` – alle gespeicherten Dateien: Projektdateien, Mailanhänge,
  Dokumente, Fotos, Protokolle, auch Fotos und Videos aus dem
  Chat;
- `LIESMICH.txt` – was im Archiv ist und was fehlt.

**Geheimnisse bleiben draußen** – Passwörter, die Schlüssel der
Zwei-Faktor-Anmeldung, API-Token, die Passwörter der Postfächer, die
Links der verknüpften Kalender, die Adressen der Kalender-Links
von Produkten, Modellen und Exemplaren, der API-Schlüssel von Lexware
Office und der KI-Schnittstellen; die Webhooks fehlen ganz (ihre Adresse kann selbst
ein geheimer Link sein). Alles andere ist drin, auch die
personenbezogenen Daten aller – und die Datei ist **nie verschlüsselt**,
auch wenn die Sicherungen es sind: Bewahre sie so sorgfältig auf wie eine
Sicherung. Den Export dürfen nur Administratoren erstellen (Einstellungen
mit der Stufe „löschen“). Er entsteht im Hintergrund; wenn er fertig ist,
bekommst du Bescheid und lädst ihn unter Mein Konto → „Aufgaben im
Hintergrund“ herunter – sieben Tage lang, wenn die Frist nicht geändert
ist. Nur wer den Export gestartet hat, kann ihn herunterladen, auch kein
anderer Administrator. Auf dem Server geht dasselbe mit
`rentalars export_data`. Einzelne Listen im Format ihres Imports stehen
unter Einstellungen → Import und Export (oben).

**Export oder Sicherung?** Beide enthalten alle Daten, sind aber für
Verschiedenes da:

- **Die Sicherung stellt Rentalars wieder her.** Sie enthält die ganze
  Datenbank mit allen Geheimnissen, die Konfiguration und alle
  gespeicherten Dateien, ist verschlüsselt, wenn die Verschlüsselung
  eingeschaltet ist, und wird auf dem Server als Ganzes zurückgespielt –
  mit `sudo rentalars restore`.
- **Der lesbare Export ist zum Lesen da** – für andere Programme oder
  euer eigenes Archiv: eine ZIP-Datei mit JSON, CSV und den Dateien, ohne
  Passwörter und Schlüssel, mit den internen IDs, nie verschlüsselt.
  Wiederherstellen lässt sich Rentalars daraus nicht – höchstens lassen
  sich die Daten in ein frisch installiertes Rentalars derselben Version
  laden, ohne Passwörter und Postfächer.
- **Der Export im Importformat** ist eine CSV-Datei je Import im
  Klartext, ohne interne IDs, die sich wieder importieren lässt (oben,
  „Import und Export“).

### Gateway: Apps koppeln

Unter **Einstellungen → Gateway** koppelst du eine App mit dem Server, wenn die Apps über das
Rentalars Gateway kommen – ohne SSH. Oben steht, ob das Gateway antwortet. Bei **„App koppeln“** wählst du das
Konto (die App hat dessen Rechte), auf Wunsch einen Namen für das Gerät und wie lange der Code gilt (1, 5 oder
10 Minuten) und klickst **„Kopplungscode erzeugen“**. Die Seite zeigt den Code als QR-Code und als Text; er gilt
genau einmal und ist weg, sobald du die Seite verlässt. In der App: Installation hinzufügen → „Mit Gateway
koppeln“ → Code scannen oder den Text einfügen. Darunter stehen die gekoppelten Geräte mit Konto, Kopplung und
letzter Nutzung; **„Sperren“** sperrt eines sofort, die App muss dann neu gekoppelt werden. Koppeln und Sperren
dürfen Administratoren, die in den Einstellungen löschen dürfen; beides steht im Änderungsprotokoll. Das
Verbinden mit dem Gateway selbst bleibt ein Befehl auf dem Server (Anleitung „Gateway“).

### Serveradresse und Zertifikat

Unter **Einstellungen → Serveradresse und Zertifikat** siehst
du, unter welcher Adresse Rentalars erreichbar ist, welchen Namen NGINX
bedient und welches Zertifikat es zeigt – wer es ausgestellt hat und bis
wann es gilt. Darunter stehen frühere Änderungen mit ihrem Ergebnis.

**Eine neue Adresse bereitest du hier vor** (das darf, wer in den
Einstellungen löschen darf – es wird ein privater Schlüssel hochgeladen).
Unter **„Änderung vorbereiten“** gibst du den **neuen Hostnamen** ein, ohne
`https://` und ohne Port, und wählst, woher das **Zertifikat** kommt:

- **Let's Encrypt** – mit einer E-Mail-Adresse für Hinweise zum Ablauf.
  Der Name muss im öffentlichen DNS stehen, und Port 80 muss aus dem
  Internet erreichbar sein.
- **Selbst erstelltes Zertifikat** – zum Ausprobieren; Browser warnen.
- **Eigenes Zertifikat** – das Zertifikat mit seiner Kette und der private
  Schlüssel ohne Passwort, beide als PEM-Datei.
- **Ein Server davor verschlüsselt** – ein anderer Server vor Rentalars
  kümmert sich um das Zertifikat; nur der Name ändert sich.

**„Alte Adresse auf die neue weiterleiten“** ist voreingestellt: Wer die
alte Adresse aufruft, landet bei der neuen – über HTTPS, solange das alte
Zertifikat für den alten Namen gilt.

**„Prüfen und vorbereiten“**: Rentalars prüft, was es von hier aus prüfen
kann – ob der Name im DNS auf diesen Server zeigt (hinter einem Router
sagt es, wenn es das nicht sicher weiß), ob NGINX auf den Ports 80 und 443
antwortet und beim eigenen Zertifikat, ob Schlüssel, Kette, Namen und
Ablauf passen. Unter „Was Rentalars prüfen konnte“ steht jedes Ergebnis.

**Danach zeigt die Seite genau einen Befehl**, etwa
`sudo rentalars address apply 3f2a…`, mit „Kopieren“ und darunter, was er
tun wird. Bis er auf dem Server läuft, ändert sich nichts. Gib ihn dem,
der euren Server betreut, oder führ ihn selbst per SSH aus; mit
`--dry-run` zeigt er vorher nur, was er tun würde. Der Befehl prüft alles
noch einmal, sichert vorher Konfiguration, NGINX und Zertifikate und
stellt bei jedem Fehler den alten Stand wieder her. Das Ergebnis siehst du
anschließend hier: „Angewendet am … von …“ oder „Der Befehl ist am …
fehlgeschlagen“ mit dem Fehler. Eine neuere
Vorbereitung ersetzt die vorige; „Diese Änderung verwerfen“ nimmt sie
zurück, ihr Befehl gilt dann nicht mehr.

**Warum es dafür keinen Knopf gibt:** Eine neue Adresse ändert den
Webserver, holt oder installiert Zertifikate und startet Rentalars neu.
Dafür braucht es root auf dem Server. Rentalars läuft mit Absicht ohne
diese Rechte und speichert keine Zugangsdaten für root – selbst wer ein
Administratorkonto übernähme, könnte den Server nicht verändern.

**Danach** meldet sich jeder unter der neuen Adresse neu an, und Links in
neuen E-Mails – Einladungen, Passwort-Links, Einsatzanfragen – verwenden
die neue Adresse. Kalender-Abos und gedruckte QR-Codes behalten die alte;
sie funktionieren, solange die alte Adresse weiterleitet. Die
Rentalars-App auf den Telefonen braucht die neue Adresse.

### API-Token – Rentalars für andere Programme

Alles, was die Oberfläche kann, kann auch ein anderes Programm über die
Schnittstelle (API): ein Lagerscanner, eine Tabellenkalkulation, eure
Website – und die Rentalars-App für Android (Abschnitt 2). Die vollständige
Beschreibung findest du unter **Einstellungen → API-Dokumentation**; sie
öffnet in einem neuen Tab, damit die Einstellungen offen bleiben. Außerdem
sind Eingangsrechnungen, Anlagevermögen und Verkäufe aus Bestand, Zubehör und
Ersatz, Preisangebote, Altprojekte, das Verzeichnis (LDAP) und die automatischen
Zusammenfassungen dort mit beschrieben; neue Rechte braucht dafür kein Token.

Ein Programm meldet sich mit einem **Token** an. Jeder Nutzer legt seine
eigenen an, unter **Mein Konto → API-Token**:

- Gib an, wofür das Token ist („Lagerscanner Halle 1“).
- **„Nur lesen“** und **„Auf Module beschränken“** engen es ein. Ein Token
  hat nie mehr Rechte als du selbst.
- Das Token wird **genau einmal angezeigt**. Kopiere es sofort; Rentalars
  speichert nur einen Prüfwert und kann es dir nicht noch einmal zeigen.
- „Widerrufen“ macht ein Token sofort ungültig.

Behandle ein Token wie ein Passwort.

**Tokens erstellen andere Tokens nur in Grenzen.** Ein Programm kann sich
mit seinem Token über die Schnittstelle weitere Tokens erstellen – aber
nie mehr, als es selbst hat:

- Ein Token, das **auf Module beschränkt** ist – wie das der App –, kann
  keine Tokens erstellen und sieht und widerruft über die Schnittstelle
  nur sich selbst, nicht die anderen Tokens deines Kontos („Ein auf Module
  beschränktes Token kann keine Tokens erstellen. Erstelle Tokens im
  Browser.“).
- Ein Token mit **Ablaufdatum** erstellt nur Tokens, die spätestens mit
  ihm ablaufen.
- Ein Token **„Nur lesen“** ändert nichts: Es erstellt und widerruft keine Tokens, beendet keine Sitzungen und ändert keine Einstellungen seines Nutzers (Antwort 403).

Im Browser unter Mein Konto → API-Token legst du Tokens an.

**Aufrufe je Minute.** Damit ein Programm, das sich verschluckt, nicht das
ganze System ausbremst, darf jedes Token voreingestellt **600 Aufrufe je
Minute** machen. Weitere Aufrufe beantwortet Rentalars bis zum Ende der
Minute mit „zu viele Anfragen“; das Programm wartet und versucht es dann
noch einmal. Die Grenze stellst du unter Einstellungen → Firmendaten und
Grundeinstellungen ein („API-Aufrufe je Token und Minute“); 0 schaltet sie
ab. Was ein Programm sonst noch wissen muss – etwa wie es doppelte Aufrufe
und überschriebene Änderungen vermeidet –, steht in der API-Dokumentation.
Ein Idempotency-Key gilt je Token bzw. je Sitzung: Die
gespeicherte Antwort kommt erst nach Anmeldung und Prüfung der Rechte wie
bei einem neuen Aufruf, und derselbe Schlüssel mit anderem Inhalt ergibt
409. Änderungen mit `If-Match` vergleichen und schreiben in einem Schritt;
zwei gleichzeitige Änderungen derselben Fassung überschreiben sich nicht.

**Projektnummern in anderen Programmen.** Hat ein Programm Projektnummern
mit „P-“ gespeichert (`P-2026-0042`),
bekommt es jetzt die Nummer ohne (`2026-0042`). Die Nummer mit „P-“ steht
bei jedem umbenannten Projekt im Feld `former_number`, und die Abfrage der
Projekte mit `?number=` findet ein Projekt unter beiden Nummern.

**Servicefälle in anderen Programmen.** Die
Liste der Projekte liefert keine Servicefälle, außer das Programm fragt mit
`?kind=` danach; sie stehen unter `/service-cases`. Jedes Projekt nennt
seine Art im Feld `kind` – `project` oder `service_case` –, ebenso die
Webhooks (unten). Ein Servicefall braucht auch über die
Schnittstelle einen Kunden – außer, er ist intern
(`is_internal`).

**Rechnungen in anderen Programmen.** Jedes Projekt nennt im
Feld `invoice_state` den Stand seiner Rechnung – `open`, `invoiced` oder
`not_needed`; leer ohne das Recht, Preise zu sehen, und bei Projekten ohne
eigene Rechnung. `POST /projects/{id}/invoice-status` mit
`invoice_status` `issued` („Rechnung gestellt“), `not_needed` („Keine
Rechnung“) oder leer setzt ihn – mit dem Recht, das Projekt zu bearbeiten
und Preise zu sehen (Abschnitt 11, „Noch zu schreibende Rechnungen“).

**Einkauf und Produkte in anderen Programmen.** Es gibt unter anderem
`POST /purchases` und `POST /purchases/invoices` (Kauf einpflegen und
Rechnung lesen), `POST /products/{id}/duplicate`,
`POST /projects/{id}/crew-lines/bulk` (mehrere Personalpositionen),
`POST /time-entries/{id}/correct` (korrigieren und freigeben) und
`GET /accounting/documents` mit `/accounting/documents/totals` (die
Ausgangsbelege). Ein Produkt nimmt nur noch einen Preis an: Ein
Verkaufspreis an einem Mietprodukt, ein Preis an einem Verkaufsprodukt und
`is_sale` für eine Position mit einem Mietprodukt ergeben 400. Ohne das
Sonderrecht „Verfügbarkeit von Material sehen“ liefern Planung und
Positionen `availability` und `shortage_total` als `null`, und
`/availability`, `/shortages` und `/utilization` antworten 403.

**Audits und To-Dos in anderen Programmen.** Es gibt Audits und
To-Dos (`/material-items/{id}/audits`, `…/todos`, `/material-todos`,
`/material-audits/due`, `/audit-settings`; an Exemplaren `last_audit`,
`next_audit`, `audit_due`, `open_todos`; `POST /material-todos/done` mit
`{"todos": [12, 13]}` hakt mehrere To-Dos auf einmal ab wie „Gewählte
To-Dos erledigt“ unter Offene Punkte → Material mit To-Do – höchstens
2.000, mit Schreibrecht auf das Material – und antwortet mit `done` (wie
viele offen waren und jetzt erledigt sind), `already_done` (wie viele
schon erledigt waren) und `not_found` (die IDs, zu denen es kein To-Do
gibt)), eigene Felder
(`/custom-fields`, `/custom-fieldsets`, `fieldset` an Materialmodellen,
`custom_fields` – Name → Wert – an Exemplaren), Fotos und Videos im Chat
(`attachments`, `POST` mit Dateien), das Schloss der Korrespondenz
(`locked`, `PATCH /projects/{id}/mails/{mail}/lock`),
`GET /projects/{id}/access`, `/projects/{id}/relations`,
`/projects/{id}/phases/{phase}/staffing`, `follow` beim Verschieben und
`GET /imports/{art}/export` (der Export im Importformat). Geändert: Eine
Nachricht mit Schloss gibt es für ein Programm ohne das Recht „Preise und
Kalkulation sehen“ nicht (404); offene Nachrichten liest auch die
eingeplante Crew, die zugesagt hat oder fest eingeplant ist. Eine Antwort
(`answer_to`) auf eine Nachricht mit Schloss bekommt ohne `locked` das
Schloss, und `GET /projects/{id}/history` nennt den Betreff einer Mail
oder Notiz wie die Seite nur, wer die Nachricht lesen darf. Die
vollständige Liste steht in der API-Dokumentation.

**Automationen in anderen Programmen.** Es gibt
`POST /automations/restore-defaults` (die fehlenden mitgelieferten
Automationen anlegen; Antwort 201 mit den angelegten, 200 mit einer leeren
Liste, wenn keine fehlte), `POST /material-items/{id}/inspections/check`
(Messwerte gegen ihre Grenzwerte, nichts wird gespeichert),
`GET /inspections/{id}/report` (das Prüfprotokoll als PDF) und `GET`,
`POST` und `DELETE` auf `/products/{id}/calendar-link`,
`/material-models/{id}/calendar-link` und
`/material-items/{id}/calendar-link` (der Kalender-Link: lesen – die
Adresse `url` nur für den, der ihn ändern darf –, erstellen oder ersetzen –
201 neu, 200 ersetzt –, deaktivieren). Neue Felder:
`default_key` und `default_changed` an Automationen (nur lesbar),
`protection_class` an Modellen, `protection_class_override` und
`effective_protection_class` an Exemplaren, `is_electrical` an Prüfarten,
an Prüfungen die Messwerte (`protection_class`, `cord_length_m`,
`test_device`, `visual_check_passed`, `pe_resistance_ohm`,
`insulation_resistance_mohm`, `pe_current_ma`, `touch_current_ma`,
`function_test_passed`), `evaluation` und `report_url`; im Vorschlag einer
gelesenen Rechnung `total_net`, `total_gross`, `currency` und je Position
`serial_numbers`, `category_id`/`category`, `product_id`/`product` und
`hints`; an den Benachrichtigungseinstellungen `label` und
`category_label`. Eine
elektrische Prüfung, die „bestanden“ meldet, obwohl die Messwerte für
„fehlgeschlagen“ sprechen, braucht eine `note`, sonst 400. Was es gab,
bleibt.

### Webhooks – andere Programme benachrichtigen

*Ansehen darf, wer die Einstellungen lesen darf; anlegen, ändern, testen
und das Geheimnis sehen, wer sie ändern darf; löschen, wer dort löschen
darf.*

Über die API fragt ein anderes Programm Rentalars. Ein **Webhook** geht
den anderen Weg: Er meldet einem anderen System – ERP, Chat, n8n – per
HTTP von selbst, wenn in Rentalars etwas passiert. So muss es nicht immer
wieder nachfragen.

**Die Ereignisse:**

| Ereignis | wann |
|---|---|
| Projekt angelegt | ein Projekt ist neu, in jedem Status |
| Projektstatus geändert | von Hand oder weil Material ausgegeben wurde oder zurückkam |
| Material ausgegeben | Material einer Packliste ging raus, auch in Teilen |
| Ausgabe zurückgenommen | eine versehentliche Ausgabe wurde zurückgenommen |
| Material zurück | mehr Material wurde als zurück abgehakt – eine Zeile oder „Alles ist zurück“, im Browser oder aus der App (beim Abgleich der App einmal je Abgleich) –, oder die Rücknahme ist abgeschlossen, von selbst nach „Rücknahme buchen“ oder von Hand |
| Material zwischen Teilprojekten übergeben | eine Übergabe wurde gebucht oder zurückgenommen (Abschnitt 10) |
| Zeiteintrag freigegeben | je freigegebenem Eintrag |
| Freigabe eines Zeiteintrags zurückgenommen | |
| Dokument erstellt | jede Art, auch eine Stornorechnung |

**Einen Webhook anlegen:** Einstellungen → Webhooks → **„Neuer Webhook“**.

1. **„Adresse (URL)“** des empfangenden Systems, beginnend mit
   `https://` oder `http://`. Interne Adressen – dieser Rechner, private
   Netze wie 192.168.x.x, der Server selbst – gehen nur, wenn
   der Betreiber sie in der Konfigurationsdatei freigibt (`[network]
   allow_internal`); eine IP-Adresse oder `localhost` lehnt das Formular
   sonst gleich ab, ein Name scheitert beim Zustellen (Abschnitt 16,
   „Selbsttest“). Benutzername
   und Passwort gehören nicht in die Adresse – das empfangende System
   prüft stattdessen die Signatur.
2. Eine **Beschreibung**, welches System es ist („ERP“, „n8n: Lager“).
3. Die **Ereignisse** anhaken, „Webhook speichern“.
4. Nach dem Speichern siehst du **einmal das Geheimnis** – kopiere es
   jetzt in das empfangende System. Später zeigt **„Geheimnis anzeigen“**
   es wieder; **„Geheimnis neu erzeugen“** ersetzt es sofort, und das
   empfangende System lehnt die Nachrichten ab, bis es das neue kennt.
5. **„Test senden“** schickt sofort eine Probenachricht und zeigt die
   Antwort.

**Was das empfangende System bekommt:** Jedes Ereignis kommt als `POST`
mit JSON – Version, die ID der Zustellung, das Ereignis, der Zeitpunkt
und die Daten des Ereignisses, etwa Nummer, Name und Status des Projekts
und seine Art `kind` (`project` oder
`service_case`). **Preise und Kosten sind nie dabei.** Der Kopf `X-Rentalars-Signature`
trägt `sha256=` und den HMAC-SHA256 des Inhalts, gebildet mit dem
Geheimnis; das empfangende System berechnet ihn selbst und vertraut nur
Nachrichten, bei denen beide übereinstimmen. Die Ereignisse mit je einem
Beispiel stehen in der API-Dokumentation unter „webhooks“.

**Zustellungen.** Auf der Seite eines Webhooks stehen unter
**„Zustellungen“** alle Nachrichten der letzten 30 Tage mit Inhalt,
Versuchen und dem Anfang der Antwort. Eine Antwort 2xx gilt als
zugestellt. Was fehlschlägt, versucht Rentalars nach 1 Minute, 5 Minuten,
30 Minuten, 2 Stunden und 12 Stunden erneut; danach steht die Zustellung
auf „fehlgeschlagen“, und **„Erneut senden“** schickt sie noch einmal.
Weiterleitungen folgt Rentalars nicht – trag die endgültige Adresse ein.

**Abgeschaltet.** Scheitern **10 Zustellungen in Folge** endgültig, wird
der Webhook abgeschaltet, und die Administratoren bekommen eine
Benachrichtigung. Prüfe dann das empfangende System, sende einen Test und
schalte den Webhook unter „Bearbeiten“ wieder ein (Haken „Aktiv“); die
wartenden Zustellungen gehen dann raus. Solange ein Webhook aus ist,
merkt Rentalars für ihn keine neuen Ereignisse vor.

Webhooks sind nicht im vollständigen Export (oben, „Sicherung und
Verschlüsselung“).
Wer die Einstellungen lesen darf, sieht in den Zustellungen auch die
Namen von Personen aus freigegebenen Zeiteinträgen.

---

## 17. Was diese Version noch nicht kann

Der Anforderungskatalog führt jede Anforderung als „muss“, „soll“ oder „kann“. Gebaut sind alle „muss“- und „soll“-Anforderungen.
Was der Katalog als „kann“ führt, gehört zu **Stufe 10 – Weitere Erweiterungen** und kommt einzeln, nach Bedarf. Gebaut sind
daraus unter anderem die Anmeldung über LDAP, das Scannen mit der Kamera, Zubehör- und Ersatzvorschläge, verbautes
Mengenmaterial und der eigene Preis einer freien Kraft. Hier steht, was fehlt:

- Die Anmeldung über einen **externen Identitätsdienst** (OIDC oder SAML);
  LDAP bzw. Active Directory gibt es.
- Die **steuerliche Vorbereitung der Eingangsrechnung** – auf welches Konto sie
  bucht (DOK-026, „kann“): nur vorgemerkt.
- **Planung zum Ausprobieren:** ein „Speichern“-Schalter, mit dem man in der
  Planung Änderungen erst probiert und dann übernimmt oder verwirft (PRJ-129,
  „kann“; ausdrücklich nicht gebaut). Ein gemerkter Planungsstand, zu dem
  man zurückkehren kann, wäre die einfachere Form.
- **Kalender-Feeds (iCal)** für Projekte. Den Kalender der eigenen Einsätze
  gibt es schon (Abschnitt 12), auch Kalender-Links für
  Produkte, Modelle und Exemplare (Abschnitt 4, „Kalender-Link“).
- **Kundenspezifische Preise** oder Preisgruppen.
- Rentalars **als installierbare Web-App** – das Logo als Symbol auf dem
  Startbildschirm gibt es schon.
- Rentalars **als Container**.
- Ein **Vertrag je Kunde** für die Monatsabrechnung der Servicefälle –
  Pauschale im Monat, enthaltene Stunden, Satz darüber und eine Erinnerung
  an die Abrechnung – und **Textbausteine für Mails** je Postfach.
- Vorgemerkt: **Benachrichtigungen** über
  offene Fehlbestände oder offene Punkte einige Tage vor Projektbeginn;
  **Vorschläge für Projektvorlagen** aus mehreren ähnlichen Projekten
  durch eine KI (unter Einstellungen → KI als „später“ genannt); die
  **Funktionen** bei den Produkten statt unter Personal führen und
  **Dienstleistungen** von den übrigen Produkten trennen – Funktion und
  Dienstleistungsprodukt gehören schon 1:1 zusammen.
Die genaue Zuordnung steht im Anforderungskatalog, Kapitel 10.

Zum Personal im Besonderen: Geplant und berechnet wird in **Stunden** oder
**Tagen**, mit einem höheren Satz ab einer Grenze von Stunden am Tag und
mit Zuschlägen nach Regeln, die ihr selbst festlegt (Abschnitt 12). Die
Feiertage – die eines Bundeslands und eure eigenen – gelten für alle
Projekte gleich, nicht je nach Veranstaltungsort. Die Zuschläge stehen in Planung, Preisübersicht
und Dokumenten, noch nicht in der Auswertung der Zeiten und nicht im
Überblick der Crew; eine Lohnabrechnung macht Rentalars nicht. Dass eine
**Funktion Qualifikationen voraussetzen** kann und Rentalars beim
Einplanen warnt, wenn ein Nachweis fehlt oder abgelaufen ist, gehört zu
Stufe 10; bis dahin zeigen die Seite und der Zeitstrahl einer Person, was
abläuft (Abschnitt 12). Nur die Führerscheinklasse eines Fahrers prüft
 die Logistik (Abschnitt 7, „Logistik“).

Zur Zeiterfassung: Ohne Netz erfasst ihr Zeiten mit der Rentalars-App für
Android (Abschnitt 2); Spesen gibt es in der App noch nicht, im Browser
auch am Telefon. Einen Zeitraum auf mehrere Funktionen aufteilen geht im
Browser; ob die App das kann, hängt von ihrer Version ab – Zeiten ohne
Aufteilung nimmt Rentalars von ihr an. Eine laufende Stoppuhr
lässt sich erst nach dem Stoppen aufteilen. Beteiligte an einem
Servicefall wählst du aus einer Liste, ohne Vorschläge beim Tippen. Freigegebene Spesen stehen in den Summen der Planung und
der Projektliste, nicht in der Preisübersicht. Die Hinweise bei
auffälligen Zeiten halten nichts auf und ersetzen keinen
Arbeitszeitnachweis (Abschnitt 13).

Zu Karten und Fahrten: Rentalars rechnet keine Fahrzeiten – die Route
plant Google Maps nach dem Klick. Entfernungen rechnet es nur mit dem
Routendienst, den der Betreiber auf dem Server einrichtet, und nur als
Vorschlag für die geplanten Kilometer eines Fahrzeugs (Abschnitt 7,
„Logistik“). Eine Anschrift schlägt Rentalars beim Tippen nicht vor (die
Kartensuche von OpenStreetMap erlaubt das nicht). Die Fahrten stehen in
Zeitplanung und Überblick, noch nicht im PDF der Einsatzübersicht.

Zur Logistik: Eine Buchung, für die noch kein Fahrzeug gewählt ist,
erscheint nicht in der Auslastung des Fuhrparks. Kennzeichen, Sitzplätze
und die übrigen Fahrzeugdaten gehen nicht über den Import und Export des
Materials; du trägst sie am Exemplar ein. Fahrten, die du von Hand
hinzugefügt hast, nimmt das Duplizieren nicht mit – und damit auch nicht
die Fahrzeuge darauf. Der Kalender-Link eines Fahrzeugs (Abschnitt 4,
„Kalender-Link“) zeigt seine Sperrzeiten und Prüfungen, nicht seine
Buchungen in der Logistik.

Zum Chat: Er steht nicht in der Suche, nicht in den Webhooks und nicht in
der Rentalars-App. Termine im Zeitstrahl und Einsätze im Personalplan
zieht man mit Maus oder Stift, nicht mit dem Finger, und einen Einsatz
nicht auf eine andere Person (Abschnitt 15). Konflikte zeigen der
Personalplan, die Woche der Verfügbarkeit, der Zeitstrahl einer Person und
 der Zeitstrahl der Zeitplanung, nicht Planung → Zeitstrahl.

Zur Rücknahme: Kommt von einer Zeile erst ein Teil zurück, lässt sich nicht
wählen, welche Exemplare es sind; sie werden erst frei, wenn die Zeile ganz
zurückgenommen ist (Abschnitt 10). Ausgeben und „Rücknahme buchen“ gehen
nur im Browser, nicht in der App.

Zur Korrespondenz: Rentalars liest eure Postfächer bei eurem Anbieter, mit
Benutzer und Passwort; die Anmeldung über Microsoft 365 oder Google ohne
Passwort (OAuth) gehört zu Stufe 10. Ebenso mehrere Kürzel in einem
Betreff, Ergänzungen am Kürzel und Textbausteine für Mails, auch je
Postfach; eine eigene Signatur je Postfach gibt es (Abschnitt
14), die Textbausteine der Dokumente (Abschnitt 11) gelten nur dort. Als
Absender bietet Rentalars nur Adressen der Postfächer der Korrespondenz an,
damit Antworten zurückkommen. Aus
einer Anfrage ohne Kürzel legt Rentalars kein Projekt von selbst an – nur
einen Servicefall, wenn die Adresse, an die sie ging, so eingestellt ist
(Abschnitt 14, „Weitere Adressen eines Postfachs“); eine Automation kann
sie beantworten und jemanden benachrichtigen (Abschnitt 16). Bei den
Anfragen machst du mit „Als Projekt anlegen“ oder „Als Servicefall
anlegen“ mit einem Klick ein Projekt oder einen Servicefall daraus,
übernimmst sie in ein vorhandenes Projekt – oder leitest sie mit dem
Kürzel im Betreff an ein Postfach der Korrespondenz weiter.

Zu den Teilprojekten: Die Auswertung der Zeiten, „Meine Zeiten“, der
Stundenzettel und die Seiten eines Produkts und eines Exemplars nennen ein
Teilprojekt nur mit Nummer und Name – die Endung „-1“ zeigt, dass es eines
ist.

Zu den Sprachen: Kalender-Abos, auch die Kalender-Links von
Produkten, Modellen und Exemplaren, und CalDAV, Webhooks, der Verlauf und das
Änderungsprotokoll sowie die Beispieldaten erscheinen in der Sprache der
Installation; die Ausführungen der Automationen und die Werte ihrer
Platzhalter in der Sprache der Dokumente, weil Automationen an Kunden
schreiben. Bei einer Benachrichtigung über ein geändertes Projekt steht
„was sich geändert hat“ in der Sprache dessen, der es geändert hat. Der
Import erkennt die Spalten einer Datei an ihren deutschen Überschriften;
kommt eine Datei aus der englischen Oberfläche, ordnest du die Spalten im
Schritt „Spalten zuordnen“ selbst zu (Abschnitt 16, „Import und Export“).
Rentalars kennt Deutsch und Englisch, keine weitere Sprache.

Zur KI: Sie fasst die Korrespondenz eines Projekts oder Servicefalls
zusammen – auf Wunsch auch nachts von selbst –, schlägt Antworten vor
und liest auf Wunsch Einkaufsrechnungen, auch
Eingangsrechnungen und die Rechnungen aus alten Projekten, sonst nichts; den Antwortentwurf
schreibt sie in der Sprache der Mail, auf die du antwortest. Wie
schnell die lokale KI ist, hängt vom Server ab; auf einem Raspberry Pi
dauert eine Zusammenfassung einige Minuten.

Zum Einkauf: „Rechnung lesen“ liest nur PDFs mit Text – gescannte
Rechnungen und Fotos nicht, eine Texterkennung gibt es nicht. Ein neues
Modell, das „Kauf einpflegen“ anlegt, führt seinen Bestand als einzelne
Exemplare; Mengenmaterial legst du vorher als Modell an. Ein Produkt
setzt Rentalars beim Lesen nur ein, wenn die KI es mit seiner
Artikelnummer oder einem Namen nennt, den kein anderes Produkt trägt; zur
Wahl stellt es der KI höchstens 40 Produkte – bei vielen Produkten die,
deren Namen Wörter mit der Rechnung teilen. Beim Duplizieren
eines Modells steht die Übernahme der Prüfarten nicht im Verlauf der
Kopie.

Zur elektrischen Prüfung: Die Messwerte tippst du ab – Rentalars liest
keine Prüfgeräte und deren Dateien aus; ein Protokoll des Prüfgeräts hängst
du als Datei an. Die Grenzwerte sind die von DIN VDE 0701-0702 für
Schutzleiterwiderstand, Isolationswiderstand, Schutzleiter- und
Berührungsstrom; einstellen lassen sie sich nicht.

Zur Mitarbeit am Servicefall: Wer einen Fall nur als Zuständiger oder
Beteiligter bearbeitet, lädt dort keine Dateien hoch, legt Mails nicht in
die Dateien und verschiebt keine Mails in ein anderes Projekt; Mails
schreiben und beantworten geht. Ohne Zugriff auf die Projekte fehlen ihm
die Reiter Dokumente, Zugriff und Verlauf des Falls.

Zur Serveradresse: Ein Zertifikat von Let's Encrypt mit einem DNS-Eintrag
als Nachweis (für Server, die nur per VPN erreichbar sind) lässt sich
nicht aus den Einstellungen vorbereiten, ebenso wenig ein anderer Port als
443. Eine Weiterleitung der alten Adresse wieder zu entfernen, geht nur auf
dem Server (Anleitung [„Betrieb“](../betrieb/betrieb.md), „Serveradresse und Zertifikat ändern“).

Zu Eingangsrechnungen und Anlagevermögen: Rentalars liest Eingangsrechnungen
nur als PDF mit Text; Scans und Fotos bewahrt es auf, ohne sie zu lesen (keine
Texterkennung). Die KI liest die Positionen nur, wenn „Rechnungen lesen“
eingeschaltet ist, und was sie liest, prüfst du, bevor etwas eingepflegt wird.
Die Abschreibung ist **linear** nach Monaten, mit den vereinfachten Regeln aus
Abschnitt 4 („Anlagevermögen, Abschreibung und Restbuchwert“): keine degressive
Abschreibung, keine Sonderabschreibung, keine Halbjahresregel, kein
GWG-Sammelposten. Das ist eine Hilfe für den Überblick, **keine Steuerberatung**;
die Zahlen für die Bilanz bestätigt eure Steuerberatung. Für den Anlagenspiegel
und die Verkäufe aus Bestand gibt es keinen DATEV-Export (nur CSV), und die
steuerliche Vorbereitung der Eingangsrechnung – auf welches Konto sie bucht – ist
nur vorgemerkt. Die Kosten einer Eingangsrechnung bleiben an den Exemplaren, wie sie
beim Einpflegen waren; ändert sich später der Schlüssel der Nebenkosten, ziehen die
Exemplare nicht nach. Ein Exemplar mit verbautem Material lässt sich nicht
verkaufen, solange es nicht ausgebaut ist; „Rechnung dazu erstellen“ macht nur einen Entwurf und nur für einen
Käufer, der Kunde ist.

Zu Altprojekten: Der Import liest nur PDFs mit Text, keine Gutschriften und nur
Euro. Wie gut die KI fremde Rechnungen liest, ist nicht geprüft; ohne KI, oder
wenn sie nicht antwortet, holt Rentalars mit Mustern, was es findet. Rechnungen
aus dem Import stehen nur auf Wunsch im DATEV-Export und gehen nicht an Lexware
Office (Abschnitt 11, „Altprojekte importieren“).

Zum Scannen: Das Eintippen geht immer – im Feld „Exemplar-ID“ bzw. „Code eintippen oder
scannen“, mit der Tastatur oder mit einem Handscanner, der wie eine Tastatur tippt. Die **Kamera** braucht eine
verschlüsselte Verbindung (https; auf dem Server selbst geht auch `localhost`)
und einen Browser, der Codes erkennen kann – Chrome, Edge und Browser auf
Android; Firefox und Safari bieten sie nicht. Getestet ist das Scannen mit
simulierten Codes, nicht mit einer echten Kamera und echten Etiketten. Ein
Kamerabild verlässt den Browser nie; nur der gelesene Text geht an Rentalars.

Zur Anmeldung über das Verzeichnis: Rentalars liest das Verzeichnis und
**schreibt nie hinein**. Getestet ist die Anmeldung mit einem simulierten
Verzeichnis und einem echten OpenLDAP, **nicht mit Active Directory** (Abschnitt
16, „Verzeichnis (LDAP)“). Ein externer Identitätsdienst (OIDC oder SAML) fehlt
weiter.

Zu den Preisangeboten freier Kräfte: Nur in Euro, ohne Umsatzsteuer; ein
Gegenangebot der Planung ist nicht an die Grenzen gebunden, und ein Angebot, das
jemand am Telefon nennt, trägt die Planung nicht mit einem Knopf ein (Abschnitt 12,
„Preisangebote freier Kräfte“). Der Preis für den Kunden bleibt, wie er ist.

Zu den automatischen Zusammenfassungen: Die Filter vor dem Senden erkennen, was
eine erkennbare Form hat (IBAN, Kartennummer, Schlüssel, E-Mail-Adresse,
Telefonnummer) – **Namen, Anschriften und was in freien Worten steht, nicht**.
Der Betrieb kann nicht festlegen, an welche Server Rentalars überhaupt senden darf;
das entscheidet, wer die Schnittstelle einträgt. Die Nacht ist mit keinem echten
Anbieter erprobt. Die KI erfindet gelegentlich etwas (Abschnitt 14,
„Automatische Zusammenfassungen“).

Zur Planung: Ein bestimmtes Exemplar als Wunsch deckt in einer Position mit
mehreren Stück **eines** der Stück; die Position bleibt eine Position
(„1 von 10 Stück“). Bauteile eines Sets lassen sich nicht auf ein Exemplar
festlegen, und fügst du dieselbe Packung noch einmal mit einem anderen Exemplar
hinzu, entsteht eine zweite Packung. Ein Zielbetrag für den Gesamtrabatt wird beim
Berechnen in einen Prozentsatz verwandelt und danach **nicht** nachgerechnet, wenn
sich das Projekt ändert.

Ein **heller Modus** ist vorbereitet, aber noch nicht wählbar.

---

## 18. Fragen und Antworten

**Ich finde ein Produkt nicht im Feld „Produkt hinzufügen“.**
Ist es deaktiviert? Deaktivierte Produkte lassen sich nicht neu verplanen
(Materialverwaltung → Produkte → „Auch deaktivierte zeigen“). Ist es eine
Dienstleistung? Dienstleistungen planst du nur im Block
Personal über ihre Funktion (Abschnitt 12, „Personal im Projekt
einplanen“); Transport und Fahrtkosten sind Nebenkosten und stehen im Feld
(Abschnitt 5, „Produktarten“). Ist es ein Fahrzeug oder Anhänger? Die
buchst du im Block „Logistik“ (Abschnitt 7, „Logistik“).

**Das KFZ kostet auf einer Fahrt mehr je Kilometer als am Produkt.**
Absicht: Zieht es auf dieser Fahrt einen Anhänger, kommt der
Anhängerzuschlag dazu – Rentalars erkennt das an der Fahrt, die Spalte
„Betrag“ nennt „davon Anhängerzuschlag …“ (Abschnitt 7, „Logistik“).

**An einer Position steht „Dienstleistung – unter Personal planen“.**
Sie stammt aus der Zeit, als Dienstleistungen auch als
Material geplant wurden. Sie bleibt mit ihrem Preis, wie sie ist. In
laufenden Projekten ersetzt du sie am besten durch eine Personalposition
der Funktion (Abschnitt 12, „Personal im Projekt einplanen“).

**Ein Produkt zeigt Bestand 0, obwohl das Material im Regal liegt.**
Das Material ist dem Produkt nicht zugeordnet („Materialverwaltung →
Offene Punkte → Material ohne Produkt“), oder die Exemplare stehen auf defekt, in Reparatur oder
gesperrt – oder sie sind fest in etwas verbaut. In einem bestimmten
Zeitraum fehlt auch, was dort eine Sperrzeit hat; der Zeitstrahl des
Produkts zeigt es.

**Die Ampel ist rot, obwohl das andere Projekt doch erst später beginnt.**
Sieh dir die Zeiträume genau an – „Material außer Haus“, nicht die
Veranstaltung – und denk an die Pufferzeiten und an Sperrzeiten. Die Seite
des Produkts zeigt unter „Verfügbarkeit“ und im Reiter „Zeitstrahl“,
welches Projekt das Material wann belegt.

**Warum ist die Position „knapp“ und nicht „frei“?**
Ein anderes Projekt hat dasselbe Material als Option vorgemerkt – als
Projekt mit Status Option, in einer optionalen Teilgruppe oder als
optionale oder alternative Position. Solange daraus nichts Festes wird,
reicht es.

**Ich habe den Preis am Produkt geändert, aber das Projekt zeigt den alten.**
Das ist Absicht: Ein Projekt behält die Preise, mit denen es kalkuliert
wurde. Ist es noch eine Anfrage, eine Option oder „Bestätigt – Preise und Einzelheiten offen“, weist jede Seite des Projekts darauf
hin, die Projektleitung wird benachrichtigt, und die Planung bietet oben „Änderungen
übernehmen“ an – ebenso die Produktseite für alle Projekte auf einmal (Abschnitt 8, „Geänderte Produkte“). Ein bestätigtes
Projekt behält seine Preise; dort änderst du den Preis bei Bedarf an der
Position.

**Die Projektsumme stimmt nicht mit dem überein, was ich nachgerechnet habe.**
Zählst du eine optionale Teilgruppe oder eine optionale oder alternative
Position mit? Sie sind in der Summe nicht enthalten und stehen eigens
darunter. Rechnet eine Teilgruppe mit anderen Miettagen oder einem
Pauschalpreis? Begrenzt eine Funktion oder ein Produkt den Rabatt
(„höchstens … % (Funktion)“, „höchstens … % (Produkt)“)? Und: Eine erstellte Rechnung zeigt den Stand, als sie
erstellt wurde – was danach geplant wurde, steht nicht darin.

**Die Projektvorlage hat andere Preise als das Projekt, aus dem sie stammt.**
Absicht: Eine Vorlage nimmt die Preise des Tages, an dem das neue Projekt
entsteht, und den Rabatt des neuen Kunden (Abschnitt 7,
„Projektvorlagen“).

**Eine Position aus der Vorlage fehlt im neuen Projekt.**
Ihr Produkt oder ihre Funktion ist inzwischen deaktiviert – oder es war
eine Dienstleistung als Materialposition, die nur noch
unter Personal geplant wird. Rentalars hat es beim Anlegen gesagt („Aus der
Vorlage weggelassen: …“). Füge ein anderes Produkt oder eine
Personalposition hinzu und speichere die Vorlage neu.

**Ich kann ein Projekt nicht mehr ändern.**
Es ist abgeschlossen. Wieder öffnen kann es jemand mit dem entsprechenden
Sonderrecht.

**Ich kann den Status nicht auf „Wieder im Lager“ setzen.**
Auf einer Packliste des Projekts sind noch Zeilen offen – sieh bei mehreren
Packlisten in jede. Hake ab, was zurück ist, und buche es mit „Rücknahme
buchen“, oder kläre die Fehlteile und schließ die Rücknahme ab (Abschnitt
10).

**Ich habe die Rücknahme abgehakt, aber das Material ist noch nicht frei.**
Die Rücknahme geht wie die Ausgabe: Abhaken merkt nur
vor, **„Rücknahme buchen“** unten auf der Packliste bucht es ins Lager.
Erst dann ist es für andere Projekte frei. An der Zeile steht, wie viel
noch nicht gebucht ist („2 noch nicht gebucht“); der Balken zeigt es
orange schraffiert (Abschnitt 10, „Zurücknehmen“).

**Ein zurückgekommenes Stück lässt sich im selben Projekt nicht noch
einmal ausgeben.**
Absicht: Was einmal zurückgenommen ist, ist für dieses Projekt erledigt –
auch ein zurückgekommenes Exemplar lässt sich darin nicht noch einmal
wählen. Was noch nicht ausgegeben war, kannst du weiter packen und
ausgeben (Abschnitt 10, „Ausgeben“).

**Wo ist der Status „Zurück“ – und die Phase „Verladen“?**
Der Status heißt „Wieder im Lager“, damit ihn niemand
mit dem Knopf „← Zurück“ verwechselt, und die Phase „Verladen“ heißt
„Packen“. Es hat sich nur der Name geändert; Projekte und Phasen sind, wie
sie waren. Der Verladetermin einer Packliste heißt weiter „Verladen“
(Abschnitt 7, „Der Status“ und „Zeitplanung“).

**Nach dem Speichern einer Phase fragt Rentalars nach dem Mietzeitraum.**
Die Phase liegt ganz oder teilweise außerhalb des Mietzeitraums. Gespeichert
ist sie schon. „Erweitern“ verlängert den Mietzeitraum so weit, dass er sie
umfasst; „Nicht erweitern“ lässt ihn, wie er ist – dann ist das Material
in der Phase nicht reserviert. Phasen „Planungen und Besprechungen“ fragen
nie (Abschnitt 7, „Phase außerhalb des Mietzeitraums“).

**Wie bilde ich eine Vermietung ohne Personal ab (Dry Hire)?**
Mit der mitgelieferten Vorlage „Dry Hire (Vermietung ohne Personal)“:
neues Projekt mit dieser Vorlage, Mietzeitraum vom Packen bis nach der
Rückgabe, Material hinzufügen, bei der Abholung ausgeben und den
Lieferschein unterschreiben lassen, bei der Rückgabe zurücknehmen
(Abschnitt 7, „Dry Hire – Vermietung ohne Personal“).

**Ich lagere das Material einer Band und nehme es zu ihren Gigs mit. Wie
bilde ich das ab?**
Als Kundenmaterial: auf der Seite des Kunden „Material hinzufügen“, mit
Modell, Gewicht, Maßen und Lagerort wie euer eigenes Material. Im Projekt
der Band steht es ohne Preis mit „Kundenmaterial – wird mitgeführt“, im
Angebot mit „Kundeneigenes Material – wird mitgeführt, ohne Berechnung“,
auf der Packliste mit Gewicht und Volumen (Abschnitt 5, „Kundenmaterial“).

**Ich finde Kundenmaterial nicht im Feld „Hinzufügen“.**
Kundenmaterial lässt sich nur in Projekten seines Eigentümers (und deren
Teilprojekten) einplanen. Ist der Kunde des Projekts ein anderer – etwa
der Veranstalter statt der Band –, bietet das Feld es nicht an. Prüfe
auch, ob das Produkt deaktiviert ist.

**Material ist ausgegeben, aber das Projekt steht noch auf „Bestätigt“.**
Es ist erst ein Teil unterwegs. Das Projekt geht auf „Unterwegs“, sobald
alles ausgegeben ist – bei mehreren Packlisten jede. Die Packliste sagt,
was noch fehlt; das Ausgegebene ist trotzdem unterwegs und für andere
Projekte belegt. Soll der Rest nicht mehr raus, schließ die Rücknahme ab,
oder setz das Projekt von Hand auf „Unterwegs“ (Abschnitt 10,
„Ausgeben“).

**Eine Zumietung lässt sich nicht auf „angefragt“ stellen.**
Sie hat noch keinen Lieferanten. Ohne Lieferanten bleibt der Status
„offen“; trag den Lieferanten ein – oder leg ihn im Feld „Lieferant“ neu
an –, dann geht „angefragt“ (Abschnitt 9, „Zumieten“).

**Wie viele Stunden schlägt Rentalars für Personal vor?**
Rentalars schlägt die ganze Dauer des Zeitraums vor:
Montag 08:00 bis Dienstag 20:00 sind 36 Stunden, Freitag 12:00 bis Samstag
12:00 sind 24. Arbeitet niemand durch, trag über den Stift die wirklichen Stunden
ein – oder rechne „je Tag“ ab (Abschnitt 12, „Personal im Projekt
einplanen“).

**Ich kann ein Exemplar nicht ausmustern.**
Es steckt noch etwas darin. Nimm die Inhalte zuerst heraus.

**Ein Exemplar gilt als überfällig, dabei ist es frisch geprüft.**
Für Rentalars zählt nur, was erfasst ist: Ein Exemplar ohne erfasste
Prüfung gilt als überfällig. Trag die letzte Prüfung im Reiter „Prüfungen“
des Exemplars nach – mit dem Datum aus dem Prüfprotokoll (Abschnitt 4).

**Ich habe viele Etiketten bestellt – wo ist das PDF?**
Mehr als 240 Etiketten druckt Rentalars nicht direkt aus dem Browser,
sondern macht sie mit „PDF erstellen“ im Hintergrund. Sobald das PDF
fertig ist, kommt eine Benachrichtigung; herunterladen lässt es sich unter
Mein Konto → „Aufgaben im Hintergrund“.

**Die Etiketten kommen zu klein, verschoben oder mit Rand aus dem
Drucker.**
Sieh in den Druckdialog: Etikettendrucker gewählt, Papier in der Größe
des Etiketts (etwa 17 × 54 mm), Skalierung 100 % (tatsächliche Größe),
keine Ränder – und im Drucker die passende Rolle, etwa DK-11204 für das
kleine Etikett (Abschnitt 4, „Etiketten“).

**Wo ist der Kasten „System“ in den Einstellungen?**
Die Einstellungen sind nach Themen geordnet: Firmendaten und
Nummernkreise stehen unter „Firma“, Automationen, Benachrichtigungen und
KI unter „Abläufe“, die Zuschläge unter „Projekte und Personal“, Selbsttest,
Sicherung, Serveradresse und die Protokolle unter „Betrieb und
Sicherheit“ (Abschnitt 16).

**Rentalars erinnert an eine Rechnung, die es nie geben wird.**
War das Projekt kostenlos oder wird es mit einem anderen abgerechnet,
klick im Kopf des Projekts auf „Keine Rechnung nötig“ – dann hören die
Erinnerungen auf. Schreibt ihr die Rechnungen in einem anderen Programm,
hake dort „Rechnung gestellt“ an, sobald sie geschrieben ist (Abschnitt
11, „Noch zu schreibende Rechnungen“).

**Woher kommt der Servicefall „Defekt 0042 …“?**
Jemand hat an diesem Exemplar einen Defekt gemeldet, und die Automation
„Defektmeldung → Servicefall“ hat daraus einen Servicefall gemacht
(Abschnitt 7, „Servicefälle“). Soll das nicht mehr von selbst geschehen,
schaltet ein Administrator sie unter Einstellungen → Automationen aus
oder stellt sie auf „unter Projekte → Anfragen stellen“ um.

**Eine mitgelieferte Automation ist gelöscht. Wie kommt sie zurück?**
Unter Einstellungen → Automationen steht, solange eine fehlt,
„Standard-Automationen wiederherstellen“. Es legt die
fehlenden an, wie sie kamen, und lässt alle vorhandenen, wie sie sind
(Abschnitt 16, „Automationen“). Von selbst – etwa bei einer
Aktualisierung – kommt keine zurück.

**Eine Rechnung ist falsch. Wie ändere oder lösche ich sie?**
Gar nicht – erstellte Dokumente bleiben, wie sie sind. Storniere die
Rechnung im Reiter „Dokumente“ („stornieren“); danach lässt sich eine neue
erstellen (Abschnitt 11).

**„Dokument erstellen“ meldet, dass etwas fehlt.**
Für eine Rechnung braucht Rentalars Firmenname und -anschrift, die
E-Mail-Adresse der Firma, USt-IdNr. oder Steuernummer (Einstellungen →
Firmendaten und Grundeinstellungen) und die Rechnungsanschrift des Kunden.
Und es darf keine andere gültige Rechnung des Projekts geben. Die Meldung
sagt, was genau fehlt; eine Nummer ist dabei nicht verbraucht.

**Unter „Dokument erstellen“ fehlt die Rechnung.**
Ist „Rentalars als Buchhaltungsprogramm verwenden“ ausgeschaltet (Einstellungen →
Firmendaten und Grundeinstellungen), bietet Rentalars keine Rechnung und
keine Stornorechnung an (Abschnitt 11, „Rechnungen in einem anderen
Programm“). An einem Teilprojekt gibt es sie ohnehin nicht, und ohne das
Recht, Preise zu sehen, auch nicht.

**Ich sehe im Reiter „Dokumente“ keine Rechnung, obwohl es eine gibt.**
Angebot, Auftragsbestätigung, Rechnung und Stornorechnung sieht nur, wer
Preise sehen darf. Und an einem Teilprojekt gibt es sie nicht: Sie
entstehen am Gesamtprojekt, mit allen Teilprojekten (Abschnitt 11).

**Am Teilprojekt lassen sich Kunde und Rechnungsadresse nicht ändern.**
Absicht: Sie kommen immer vom Gesamtprojekt. Ändere sie dort; alle
Teilprojekte folgen (Abschnitt 7, „Teilprojekte“).

**Die Rücknahme lässt sich nicht abschließen – Stücke „warten auf ihre
Übergabe“.**
Ein späteres Teilprojekt übernimmt diese Stücke, und ihre Übergabe ist
noch nicht gebucht. Buche sie auf der Packliste des späteren Teilprojekts
(„Übergabe buchen“) – oder, wenn die Stücke doch ins Lager kamen, hake sie
hier als zurück ab und buche die Rücknahme (Abschnitt 10).

**Die Rechnung des Gesamtprojekts lässt sich nicht erstellen: „Dieses
Dokument enthält alle Teilprojekte …“**
Du darfst eines der Teilprojekte nicht lesen; die Meldung nennt es. Bitte
jemanden, der alle Teilprojekte lesen darf, die Rechnung zu erstellen.

**Eine Rechnung ging nicht an Lexware Office.**
Im Reiter „Dokumente“ steht an der Rechnung der Grund, ebenso unter
Einstellungen → Buchhaltung. Gehört die Kundennummer in Lexware Office zu
einem anderen Kunden, übergib mit „Als neuen Kontakt übergeben“. Wurde der
API-Schlüssel abgelehnt oder lässt er sich nicht mehr lesen, trag ihn
unter Einstellungen → Buchhaltung neu ein und übergib erneut (Abschnitt
11 und 16).

**Die Seite Buchhaltung fehlt in den Einstellungen.**
Sie braucht Lesezugriff auf die Einstellungen und das Recht, Preise zu
sehen. Die mitgelieferte Rolle Nur-Lesen hat den Lesezugriff auf die
Einstellungen nicht (Abschnitt 16, „Nur-Lesen und die Buchhaltung“).

**Ein Webhook ist „automatisch abgeschaltet“.**
Zehn Zustellungen in Folge sind endgültig gescheitert. Sieh unter
„Zustellungen“ nach der letzten Antwort, prüfe das empfangende System,
sende einen Test und schalte den Webhook unter „Bearbeiten“ wieder ein;
wartende Zustellungen gehen dann raus, fehlgeschlagene schickst du mit
„Erneut senden“ (Abschnitt 16, „Webhooks“).

**Wo sind die Filter über der Liste?**
Hinter der Schaltfläche „Filter“ neben dem Suchfeld. Sie sind bei jedem
Öffnen einer Liste eingeklappt, auf jedem Bildschirm, auch in der
Materialverwaltung und den Stammdaten; ein Klick klappt sie auf.
Rentalars merkt sich das nicht. Sind Filter gesetzt, zeigt die
Schaltfläche ihre Zahl („Filter (2 aktiv)“), und daneben steht, was
gefiltert ist (Abschnitt 2, „Listen“).

**Meine Liste hat auf einmal andere Spalten.**
Die Wahl unter „Spalten“ gilt für dein Konto – auch an einem anderen
Rechner oder Telefon. „Spalten“ → „Standardspalten“ stellt die
ursprüngliche Auswahl wieder her.

**Der Probelauf meldet „Preise zu importieren braucht das Recht, Preise zu sehen.“**
Die Datei hat eine Preisspalte, und dir fehlt das Preisrecht. Ordne die
Spalte „– nicht importieren –“ zu oder bitte jemanden mit dem Recht, den
Import zu starten. Dasselbe gilt für den Standardrabatt bei Kunden und den
Höchstrabatt bei Produkten; für Stunden- und Tagessätze beim Personal
braucht es das Recht „Stundensätze und Personalkosten sehen“.

**Warum sind nach der Ausgabe nicht alle Zeilen der Packliste rot?**
Ausgegebenes Material ist
unterwegs, nicht verloren. Die Zeilen bleiben ruhig; rot
wird nur, was beim Abschließen der Rücknahme noch fehlt.

**Ich sehe ein Projekt nicht, in dem ich arbeiten soll.**
Deine Rolle gilt nur für zugeordnete Projekte, und du bist dort (noch)
nicht eingeplant. Die Disposition prüft die Personalposition im Projekt –
oder gibt dir über den Reiter „Zugriff“ ausdrücklich Zugang.

**Ich finde eine Person nicht in der Auswahl, wenn ich Personal einplane.**
Angeboten wird nur, wer eine Funktion hat – und bei gewählter Funktion
nur, wer genau diese hat. Gib der Person die Funktion auf ihrer Seite
(Abschnitt 12, „Personen“, „Funktionen und Sätze“). Wer das Sonderrecht
„Personen außerhalb ihrer Funktionen einplanen“ hat, sieht die übrigen
gekennzeichnet dahinter. Deaktivierte Personen stehen nicht in der
Auswahl.

**An einer zugesagten Personalposition fehlt „erneut anfragen“.**
Absicht: Für dieselben Zeiten fragt Rentalars nicht noch einmal an.
„erneut anfragen“ erscheint erst, wenn sich Beginn oder Ende seit der
Anfrage geändert haben – und ist „Bei geänderten Zeiten neu anfragen“
eingeschaltet, fragt Rentalars dann ohnehin von selbst neu an (Abschnitt
12, „Anfragen: Zusage oder Absage“). Hat jemand nach seiner Zusage doch
abgesagt, plane eine andere Person ein oder ändere die Zeiten.

**Die Person hat zugesagt, aber die Planung zeigt noch „angefragt“.**
Warte ein paar Sekunden: Die offene Planung zeigt die Antwort von selbst,
spätestens nach etwa 20 Sekunden – bei einer Antwort per Mail, sobald
Rentalars das Postfach abgerufen hat („Jetzt abrufen“ unter Einstellungen
→ „Postfächer und Signatur“ geht sofort). Tippst du gerade, steht unten
„Auf dieser Seite gibt es etwas Neues.“ – „Anzeigen“ lädt neu.

**Wo ist der Reiter „Auslastung“?**
Er heißt „Materialauslastung“ und steht unter Planung
an dritter Stelle: Kalender, Zeitstrahl, Materialauslastung, Personalplan,
Fehlbestände (Abschnitt 15). Fehlen dir Materialauslastung und
Fehlbestände, fehlt dir das Sonderrecht „Verfügbarkeit von
Material sehen“ (Abschnitt 16, „Rollen und Rechte“).

**Die Crew sieht die Planung eines Projekts nicht.**
Gewollt: Die Rolle Crew öffnet in ihren Projekten nur Überblick,
Packliste und Chat (dazu die offenen Nachrichten der
Korrespondenz) – auch als Mitglied mit „Lesen“ (Abschnitt 12, „Der
Überblick – was die Crew sieht“). Braucht jemand die Planung, gib ihm eine
Rolle mit dem Projektzugriff „nur zugeordnete Projekte“ – etwa eine eigene
Rolle neben der Freien Kraft – und trag ihn unter „Zugriff“ ein, oder stell den Projektzugriff der Rolle
Crew unter Einstellungen → Rollen zurück.

**Wo ist die Monatsabrechnung?**
Unter **Buchhaltung → Monatsabrechnung**, neben den
Ausgangsbelegen (Abschnitt 7, „Monatsabrechnung“).

**Am Mietprodukt fehlt der Verkaufspreis.**
Jedes Produkt hat genau einen Preis. Wollt ihr den Artikel auch
verkaufen, legst du ein Verkaufsprodukt an – mit „Duplizieren“ geht das
schnell (Abschnitt 5, „Ein Produkt anlegen“).

**Eine neue Person kann sich nicht anmelden.**
Ihr Konto hat noch kein Passwort. Lade sie ein – beim Anlegen mit
„Einladung jetzt per E-Mail senden“, später unter Einstellungen → Nutzer
mit „Link zum Setzen des Passworts senden“ – oder gib ihr ein
Einmal-Passwort (Abschnitt 16, „Nutzer“). Ihren Benutzernamen zeigt die
Seite der Person unter „Anmeldung“; anmelden kann sie sich auch mit der
E-Mail-Adresse.

**Ich kann eine Person nicht löschen.**
Sie hat sich schon angemeldet, war eingeplant oder hat Zeiten erfasst.
Deaktiviere sie – oder anonymisiere sie, wenn sie es verlangt (Abschnitt
12).

**Im Dialog „Zeit erfassen“ fehlt mein Projekt.**
Angeboten werden Projekte, in denen du eingeplant bist, interne Projekte
und alle offenen Servicefälle. Bist du nicht eingeplant, wähle
„später zuordnen“ – wer freigibt, ordnet das Projekt zu. Oder die
Disposition plant dich ein. Ein erledigter Servicefall steht nicht mehr
zur Wahl.

**Ich habe an einem Tag in zwei Funktionen gearbeitet. Zwei Einträge?**
Nein – einer genügt, wenn es ein Zeitraum war: Öffne beim Erfassen
„Mehrere Funktionen in diesem Zeitraum“ und gib die Stunden der weiteren
Funktion an (Abschnitt 13). So zählt die Pause einmal, und es gibt keine
Überschneidung.

**Warum wird mir bei einer Fahrt weniger erstattet, als ich gefahren
bin?**
Rentalars zieht einmal am Tag je Projekt den Arbeitsweg ab –
die doppelte „Entfernung Wohnung – Betrieb“, die bei dir eingetragen ist.
Die Fahrt zeigt die Rechnung, etwa „42 km − 28 km Arbeitsweg = 14 km“
(Abschnitt 13, „Spesen und Fahrtkosten“). Ist die Entfernung falsch, sag
der Personaldisposition Bescheid.

**Gibt es Rentalars als App?**
Für Android gibt es die Rentalars-App – für Packlisten und Zeiten ohne
Netz. Sie wird eigens ausgeliefert, nicht mit Rentalars; frag euren
Administrator. Alles andere machst du im Browser, auch am Telefon
(Abschnitt 2, „Die Rentalars-App für Android“).

**Mein Telefon mit der App ist weg.**
Widerrufe unter Mein Konto → API-Token das Token der App; dann kommt mit
dem Telefon niemand mehr an Rentalars. Was dort noch nicht abgeglichen
war, kommt dann nicht mehr an. Die Daten auf dem Telefon sind
verschlüsselt und durch die Displaysperre geschützt.

**„Der Beginn liegt in der Zukunft“, dabei habe ich gerade gearbeitet.**
Sieh auf die Uhrzeit in der Meldung: Das ist die Uhr des Servers. Stimmt
sie, ist das Datum im Formular falsch (vielleicht „morgen“ statt „heute“).
Stimmt sie nicht, sag einem Administrator Bescheid.

**Eine Mail ist nicht im Projekt angekommen.**
Steht das Kürzel im Betreff, genau mit dieser Projektnummer? Steht die Mail
unter Projekte → „Anfragen“ mit einer Kennung, war die Nummer falsch –
übernimm sie dort mit der richtigen. Fehlt das Kürzel ganz, lässt
Rentalars die Mail liegen – oder führt sie als Anfrage „ohne Kennung“,
wenn ihr Postfach Mails ohne Projektkennung übernimmt und sie nach dem
Zeitpunkt unter „übernehmen ab“ ankam (mit „nur ungelesene Mails“:
ungelesen); übernimm sie dort
oder leite sie mit Kürzel an ein Postfach der Korrespondenz weiter. Liegt
sie in einem Postfach, das Rentalars nicht mitliest, kommt sie nie an.
Abgerufen wird alle paar Minuten; „Jetzt abrufen“ unter Einstellungen →
„Postfächer und Signatur“ geht sofort. Ob und wann die Mail ankam, zeigt
das Mail-Protokoll (Abschnitt 14).

**Geht die Einsatzanfrage auch, wenn Rentalars aus dem Internet nicht
erreichbar ist?**
Ja – per Antwort-Mail. Stellt unter Einstellungen → Firmendaten und
Grundeinstellungen bei „Antwort auf Einsatzanfragen“ **„per
Antwort-Mail“** ein. Die Anfrage enthält dann die Knöpfe „Zusagen“ und „Absagen“; sie
öffnen eine fertige Mail an euer Postfach, und Rentalars holt die Antwort
dort selbst ab. Die Verbindung geht nur von Rentalars zu eurem
Mailanbieter. Nötig ist ein aktives Postfach der Korrespondenz mit Adresse
(Abschnitt 12, „Einsatzanfragen per Mail beantworten“).

**Meine Antwort per Mail auf eine Einsatzanfrage kam nicht an.**
Hast du den Betreff geändert? Rentalars erkennt die Antwort nur am Code in
eckigen Klammern; eine normale Antwort mit „Ja“ wertet es nicht aus. Sonst
dauert es bis zum nächsten Abruf, meist wenige Minuten. Kam eine Mail
„Deine Antwort wurde nicht übernommen“, steht der Grund darin – etwa, dass
es eine neuere Anfrage gibt; dann antworte mit den Knöpfen der neuesten
Mail. Steht dort, die Antwort sei nicht von der Adresse gekommen, an die die
Anfrage ging: Antworte von genau dieser Adresse (etwa nicht von einem
Weiterleitungs- oder Zweitkonto), oder antworte im Browser.

**Ist meine Mail wirklich rausgegangen?**
Einstellungen → Mail-Protokoll (für alle, die die Einstellungen lesen
dürfen): Dort steht jede gesendete Mail mit Empfängern und Ergebnis – auch
Einladungen und Benachrichtigungen.

**Eine Mail von rentalars@localhost stand auf „gesendet“, kam aber nie
an.**
Dann ist kein Mailserver eingerichtet: kein Postfach mit der Rolle
„Systemmails“ und keiner in der Konfiguration. `rentalars@localhost` ist
nur die Vorgabe der Konfigurationsdatei – ein Postfach dahinter gibt es
nicht. Eine solche Mail steht auf „nicht versendet – kein
Mailserver eingerichtet“. Gib einem Postfach unter Einstellungen →
Postfächer und Signatur die Rolle „Systemmails“ (Abschnitt 14, „Ohne
Mailserver“).

**Mails an support@ sollen anders behandelt werden als an info@ – geht
das, obwohl beides in einem Postfach landet?**
Ja,: Trag `support@` am Postfach unter „Weitere Adressen
(Aliasse)“ ein und wähle, was mit Mails ohne Projektkennung geschieht –
etwa „gleich als Servicefall anlegen“ (Abschnitt 14, „Weitere Adressen
eines Postfachs“).

**Woher zieht sich Rentalars die Feiertage?**
Nirgendwoher – Rentalars berechnet sie selbst, je Bundesland, auch die
beweglichen aus dem Osterdatum. Kein Dienst im Internet wird gefragt.
Eigene Feiertage – etwa für ein anderes Land – trägst du unter
Einstellungen → Zuschläge ein (Abschnitt 16, „Zuschläge“).

**Unter Mails von Rentalars steht ein neuer Satz.**
Jede Mail, die Rentalars von selbst verschickt, endet
mit „Diese Nachricht wurde automatisch von Rentalars für … versendet:“,
dem Firmennamen und der Adresse eurer Installation – damit Empfänger
sehen, woher sie kommt. Mails, die ihr im Projekt schreibt, tragen
stattdessen eure Signatur (Abschnitt 14, „Signatur“).

**Ich sehe den Reiter „Korrespondenz“ nicht.**
Dafür braucht es das Sonderrecht „Korrespondenz lesen“ – zusätzlich zum
Lesen des Projekts. Wer nur eingeplant ist, sieht die offenen
Nachrichten seiner Projekte, keine mit Schloss (Abschnitt 14,
„Nachrichten mit Schloss“).

**Eine Mail steht nicht mehr in der Korrespondenz, die Kollegen aber
sehen sie.**
Sie hat das Schloss, und dir fehlt das Recht „Preise und Kalkulation
sehen“. Nachrichten mit Schloss gibt es für dich nicht – auch
nicht in der Suche. Wer Preise sieht, kann das Schloss entfernen
(Abschnitt 14, „Nachrichten mit Schloss“).

**Wo ist der Reiter „Ohne Produkt“?**
Er heißt **„Offene Punkte“**; das Material ohne Produkt ist
dort der erste Unterreiter, daneben „Material mit To-Do“ und „Audit
fällig“ (Abschnitt 4, „Audits und To-Dos“).

**Wo ist der Knopf „Import“ über der Produktliste?**
Dort steht „Kauf einpflegen“. Produkte importierst du unter
Einstellungen → Import und Export oder unter Materialverwaltung → Import,
Reiter „Produkte“ (Abschnitt 16, „Import und Export“).

**Warum steht bei einem Modell kein „In den Fuhrpark übernehmen“ mehr?**
Der Knopf steht nur bei Modellen einer Kategorie, die die
Produktart „Fahrzeug“ vorgibt, wie FZ „Fuhrpark“. Gehört das Fahrzeug in
den Fuhrpark, gib seinem Modell zuerst eine solche Kategorie (Abschnitt
4, „Fuhrpark“).

**Meine Listen zeigen auf einmal wieder 50 Einträge.**
Rentalars merkt sich die Zahl je Liste an deinem Konto statt
einer Zahl für alle Listen im Browser. Wähle sie in jeder Liste einmal
neu; danach bleibt sie, auch an anderen Geräten (Abschnitt 2, „Listen“).

**Wo ist der vollständige Export?**
Unter **Einstellungen → Sicherung** als „Lesbarer Export aller
Daten“. Wozu er da ist und wozu die Sicherung, steht dort und in
Abschnitt 16, „Sicherung und Verschlüsselung“.

**Ein Foto oder Video im Chat wird abgelehnt.**
Das Formular sagt, warum. Ein Video ist zu groß (mehr als 200 MB oder
länger als 20 Minuten), sein Bild hat an einer Seite mehr als 4096 Pixel,
es hat zu viele Einzelbilder (mehr als 240 pro Sekunde oder mehr als
20 Minuten bei 60 pro Sekunde), es ist kein Video, das der Server lesen
kann, oder auf dem Server fehlt ffmpeg – dann gehen Fotos trotzdem, und
darum kümmert sich, wer den Server betreut (Anleitung [„Betrieb“](../betrieb/betrieb.md)). Ein Foto
ist größer als 25 MB, oder es hat als PNG, GIF oder WebP mehr als
16 Megapixel: Schick es als JPEG (bis 150 Megapixel). Fotos in HEIC oder
AVIF kann der Server nicht lesen; Telefone schicken beim Teilen JPEG.

**Telefon weg – wie komme ich in mein Konto?**
Mit einem deiner Wiederherstellungscodes statt des Codes der App. Danach
unter Mein Konto die Zwei-Faktor-Anmeldung aus- und mit dem neuen Telefon
wieder einschalten. Keine Codes mehr? Ein Administrator setzt sie zurück.

**Ich werde ständig abgemeldet.**
Nach 240 Minuten ohne Aktivität endet eine Sitzung (in den Einstellungen
änderbar). Wirst du früher abgemeldet, hat dich vielleicht jemand unter
„Sitzungen“ abgemeldet – oder du selbst, auf einem anderen Gerät mit
„Alle anderen Sitzungen beenden“.

**Ich kann einen Zeiteintrag nicht mehr ändern.**
Er ist freigegeben und damit gesperrt. Wer Zeiten freigibt, kann ihn in der
Auswertung entsperren.

**Die Personalposition zeigt „Schätzung“.**
Sie wird nach Aufwand abgerechnet – die Voreinstellung
für neue Personalpositionen –, und es sind noch keine Zeiten freigegeben.
Bis dahin rechnet Rentalars mit den geplanten Stunden. Willst du die
geplanten Stunden fest berechnen, stell die Abrechnung im Dialog der
Position auf „nach Plan“.

**Eine Personalposition bekommt keine Zuschläge für Nacht, Sonn- und
Feiertage.**
Sieh in ihren Dialog: Sind die Haken „Zuschläge für Nacht, Sonn- und
Feiertage im Preis“ bzw. „… in den Kosten“ gesetzt? Positionen, die vor dem
Einschalten unter Einstellungen → Zuschläge geplant wurden, haben sie
nicht. Zuschläge gibt es nur nach Plan oder nach Aufwand, nicht pauschal
oder je Tag, und nicht, wenn das Dienstleistungsprodukt sie ausnimmt.
Liegt der Tag ein Feiertag nur in einem anderen Bundesland? Es zählt das
unter „Feiertage von“ gewählte (Abschnitt 12, „Zuschläge für Nacht, Sonn-
und Feiertage“). Auch: Gibt es unter Einstellungen → Zuschläge
eine Regel für diese Zeit, mit einem Satz über 0 für Preis bzw. Kosten?
Eine leere Liste der Regeln heißt: keine Zuschläge; „Nach § 3b EStG
einstellen“ stellt sie wieder her.

**Wo ist die Karte?**
Unter der Anschrift steht „Karte anzeigen“ – erst der Klick lädt sie, damit
keine Anschrift ungefragt an OpenStreetMap geht. Fehlt der Knopf, hat euer
Administrator die Karten abgeschaltet; die Links „Route in Google Maps“
gibt es trotzdem. Liegt die Markierung falsch, korrigierst du sie unter
der Karte mit „Position korrigieren“ (Abschnitt 6, „Route und Karte“).

**Karten: „Access blocked 403“ statt der Karte.**
In der Karte stand „Access blocked 403 … App is not following the tile
usage policy of OpenStreetMap's …“: OpenStreetMap verlangt, dass der
Browser mit den Kartenbildern sagt, von welcher Seite sie angefragt
werden. Der Browser
sendet mit den Kartenbildern die Adresse eurer Installation
(nur Schema und Host) – erst nach „Karte anzeigen“ –, und die Karte
erscheint wieder. Steht die Meldung danach noch da, lade die Seite einmal
neu, ohne Cache (Strg+Umschalt+R bzw. ⌘+Umschalt+R). Hilft das nicht,
kann ein Browser-Zusatz oder eine Einstellung, die den Referer
unterdrückt, schuld sein; oder eure Installation lädt sehr viele
Kartenbilder – dann sollte euer Administrator in der Konfiguration einen
eigenen Kartenserver eintragen (Anleitung [„Betrieb“](../betrieb/betrieb.md), „Karten“).

**Ein Balken im Zeitstrahl lässt sich nicht ziehen.**
Gezogen wird nur in der Ansicht „Tage“, mit Maus oder Stift, nicht mit
dem Finger. Du musst das Projekt bearbeiten dürfen, und es darf nicht
abgeschlossen sein. Liegt ein Ende außerhalb der gezeigten Spalten, hat es
keinen Griff (Abschnitt 15, „Termine im Zeitstrahl verschieben“). Die
Einsätze von Personen ziehst du im Zeitstrahl der Zeitplanung
und im Personalplan, nicht in Planung → Zeitstrahl.

**Ich habe eine Person im Zeitstrahl gezogen, und die ganze Phase ist
mitgewandert.**
Die Person war die einzige der Phase; dann schlägt Rentalars vor, die
Phase mitzuverschieben, und der Haken ist gesetzt. Nimm ihn im Fenster
heraus, wenn nur der Einsatz wandern soll (Abschnitt 7, „Personen im
Zeitstrahl ziehen“).

**Ich finde einen Servicefall nicht in der Projektliste.**
Servicefälle haben ihre eigene Liste: Projekte → „Servicefälle“. Erledigte
zeigt sie erst, wenn du unter „Status“ „erledigt“ wählst. Die Suche findet
sie wie Projekte (Abschnitt 7, „Servicefälle“). Die Fälle, an denen du
beteiligt bist, stehen unter Mein Bereich → „Servicefälle“ – ein zurückgestellter
Fall erst, wenn seine Wiedervorlage fällig ist, oder mit „auch
Zurückgestellte“.

**Rentalars hat auf eine Anfrage nicht automatisch geantwortet.**
Unter Einstellungen → Automationen, „Ausführungen“, steht bei jeder Mail,
was geschah, und warum eine Antwort ausblieb – etwa weil die Mail als
automatisch versendet gekennzeichnet war, von einer No-Reply-Adresse kam
oder der Absender heute schon eine Antwort dieser Automation bekommen hat.
Gezählt werden nur Mails in Postfächern, die Mails ohne Projektkennung
übernehmen (Abschnitt 16, „Automationen“).

**Ein defektes Exemplar lässt sich nicht auf „verfügbar“ stellen.**
Absicht: Aus „defekt“ geht es nur in Reparatur, ausgemustert oder verkauft.
Stelle es auf „in Reparatur“ und von dort auf „verfügbar“, wenn es wieder
läuft.

**Die Seite sieht nach einer Aktualisierung merkwürdig aus.**
Das sollte nicht vorkommen: Rentalars sorgt selbst
dafür, dass der Browser die neue Gestaltung lädt. Falls doch: Seite mit
Strg+F5 neu laden und einem Administrator Bescheid geben.

**Die Projektseite lädt sich von selbst neu.**
Jemand anderes hat am Projekt etwas geändert, oder eine Mail ist
eingegangen – du siehst dann den neuen Stand, an derselben Stelle der
Seite. Tippst du gerade, lädt nichts neu; es erscheint nur „Auf dieser
Seite gibt es etwas Neues.“ mit „Anzeigen“ (Abschnitt 2).

**Die Einladungs-E-Mail kommt nicht an.**
Sieh im Spam-Ordner nach. Ob sie hinausging, sieht ein Administrator im
Mail-Protokoll (Einstellungen → Mail-Protokoll). Wenn der E-Mail-Versand
auf dem Server nicht eingerichtet ist, kann er den Link aus dem Protokoll
des Servers kopieren (Anleitung [„Betrieb“](../betrieb/betrieb.md)) – oder dir ein Einmal-Passwort
geben (Abschnitt 16, „Nutzer“). „Passwort vergessen“ auf der Anmeldeseite
schickt ebenfalls einen neuen Link, auch wenn du noch nie ein Passwort
hattest.

**Wer hat das geändert – und wer hat es angesehen?**
Der Reiter „Verlauf“ am Projekt und am Exemplar, der Abschnitt „Verlauf“ am
Produkt oder Kunden – oder das Änderungsprotokoll in den Einstellungen.
Wer Kunden, Personen oder Projekte geöffnet oder heruntergeladen hat,
steht im Zugriffsprotokoll (Abschnitt 16).

**Wie stelle ich Englisch ein?**
Für dich selbst: Mein Konto → „Sprache“ → „English“, dann „Sprache
speichern“. Seiten, Mails und Benachrichtigungen an dich sind danach
englisch, mit Daten wie 16/10/2026 (Abschnitt 2, „Mein Konto“). Für eine
andere Person stellt ein Administrator die Sprache unter Einstellungen →
Nutzer ein. Sollen auch die Dokumente an Kunden englisch sein: Einstellungen
→ Firmendaten und Grundeinstellungen → „Sprache der Dokumente“ – und
danach die eigenen Texte in Dokumentvorlagen und Textbausteinen übersetzen
(Abschnitt 11, „Sprache“).

**Ein Servicefall ist von selbst auf „erledigt“ oder „offen“ gesprungen.**
Das waren die Automationen für Servicefälle: „wartet auf Schließen“ wird
zum Termin geschlossen und bei einer neuen Mail oder Chatnachricht wieder
geöffnet, ein zurückgestellter Fall ist zur Wiedervorlage wieder offen. Der
Verlauf des Falls und Einstellungen → Automationen, „Ausführungen“, zeigen,
welche Automation es war (Abschnitt 16, „Automationen“).

**Wie ändere ich die Adresse?**
Unter Einstellungen → Serveradresse und Zertifikat: neuen Hostnamen
eingeben, wählen, woher das Zertifikat kommt, „Prüfen und vorbereiten“.
Die Seite zeigt dann einen Befehl, den der Betreuer eures Servers per SSH
ausführt; erst dann ändert sich etwas. Danach meldet sich jeder unter der
neuen Adresse neu an (Abschnitt 16, „Serveradresse und Zertifikat“).

**Wie richte ich die lokale KI ein?**
Zwei Schritte. Auf dem Server, per SSH: `sudo rentalars ai install` – vorher
gern mit `--dry-run`, das nur zeigt, was geschähe. Der Befehl wählt ein
Modell passend zu Arbeitsspeicher, Kernen und Prozessor, lädt es herunter
und startet es als Dienst. Muss er llama.cpp erst aus dem Quelltext bauen, dauert das auf
einem Raspberry Pi 15 bis 40 Minuten (Anleitung [„Betrieb“](../betrieb/betrieb.md), „KI“). Danach in Rentalars: Einstellungen → KI →
„Zusammenfassungen mit lokaler KI einschalten“. Mit „Geschwindigkeit
messen“ siehst du, wie schnell sie antwortet (Abschnitt 16, „KI“).

**Was kostet die KI?**
Die lokale KI kostet nichts außer Strom und Arbeitsspeicher auf eurem
Server – keine Gebühr je Aufruf, kein Konto bei einem Anbieter. Eine
Schnittstelle zu einem Cloud-Dienst kostet, was dessen Anbieter verlangt,
meist je Aufruf nach Textmenge; das rechnet ihr mit ihm ab, nicht mit
Rentalars. **Zum Datenschutz:** Mit der lokalen KI bleiben die Mails auf
eurem Server. Bei einem Cloud-Dienst gehen die Mails eurer Projekte an
diesen Anbieter – Rentalars warnt dann rot. Nutzt ihn nur, wenn euer
Vertrag mit ihm das erlaubt, und prüft, ob ihr einen Vertrag zur
Auftragsverarbeitung braucht. Das Protokoll der KI-Aufrufe hält fest, was
wann wohin ging, nie den Inhalt.

**Warum ist die lokale KI so langsam?**
Meist liegt es am Prozessor. Unter Einstellungen → KI steht, ob der
Prozessor **AVX2** und **FMA** hat und wie schnell die KI liest und
schreibt (Abschnitt 16, „KI“). Fehlen AVX2 oder FMA, läuft sie um ein
Vielfaches langsamer. Das ist typisch für eine **virtuelle Maschine**, etwa
unter Proxmox mit dem voreingestellten Prozessortyp: Stellt der Betreuer
eures Servers dort den Prozessortyp auf **„host“** (Proxmox: Hardware →
Prozessoren → Typ: host) oder auf **„x86-64-v3“**, falls die Maschine
zwischen Rechnern wandern soll, und fährt die Maschine in Proxmox herunter
und startet sie wieder – ein Neustart in der Maschine reicht nicht. Ob es
geklappt hat, zeigt in der virtuellen Maschine
`grep -o -w 'avx2\|fma' /proc/cpuinfo | sort | uniq -c`: je ein Treffer
für `avx2` und `fma` pro Kern der Maschine, bei vier Kernen also je 4.
Kommt nichts, fehlen sie noch; zeigt der Befehl deutlich mehr, lief er
wohl auf dem Proxmox-Rechner selbst. Etwa eine Minute nach dem Start
übernimmt der Server die neuen Einstellungen der KI von selbst. Bleibt sie
langsam – Rentalars empfiehlt das unter Einstellungen → KI, wenn sie
weniger als 6 Tokens je Sekunde schreibt oder weniger als 30 liest –,
hilft das kleinere Modell: `sudo rentalars ai install --model qwen3-1.7b`
(Anleitung [„Betrieb“](../betrieb/betrieb.md), „KI“).

**Sagt mir Rentalars, wenn die KI fertig ist?**
Ja: mit „Eine Aufgabe im Hintergrund ist fertig (z. B. KI-Zusammenfassung,
Antwortentwurf, Rechnung lesen, Export)“, der ersten Art unter „System“ in
Mein Konto → Benachrichtigungen. Dort stellst du ein, ob in Rentalars, per
E-Mail, in der App oder gar nicht (Abschnitt 15, „Benachrichtigungen“).

**Muss ich die KI nach einem Update neu installieren?**
Nein. Jedes Update übernimmt die Einstellungen der lokalen KI selbst –
Threads je Kern, Nachdenken aus, Speichergrenze –, ohne etwas
herunterzuladen. Das Modell wechselt nie von allein, denn es ist eine
große Datei: Passt ein anderes besser, nennt Rentalars den Befehl, und der
Betreuer eures Servers entscheidet (Anleitung [„Betrieb“](../betrieb/betrieb.md), „KI“).

**Wann kommen Fehlbestands-Meldungen?**
So, wie es unter Einstellungen → Benachrichtigungen steht – voreingestellt
jeden Tag um 4:15 Uhr für Projekte, die in den kommenden vier Wochen
beginnen. Ein neuer Fehlbestand kommt einzeln; erneut, wenn er größer wird
oder behoben war und wiederkommt. Außerdem ist „bekannte
Fehlbestände bei jeder Prüfung erneut melden“ voreingestellt an:
Dann erinnert jede Prüfung an die schon
gemeldeten, in einer Nachricht je Projekt. Wer das nicht will, schaltet
es dort aus. Die Seite zeigt auch, wann
zuletzt geprüft wurde und wann die nächste Prüfung ist (Abschnitt 16,
„Benachrichtigungen der Firma“). Ob du sie in Rentalars, per E-Mail oder
in der App bekommst, stellst du unter Mein Konto → Benachrichtigungen ein.

**Ich kann mich nicht über das Verzeichnis anmelden, obwohl das Passwort stimmt.**
Öffne unter Einstellungen → Nutzer und Rechte → Verzeichnis (LDAP) im Kasten
„Test“ die **„Anmeldung für einen Nutzer testen“**: Sie zeigt den Eintrag, die
Gruppen, die Zuordnungen, die gelten, und nennt den Grund. Meist ist es einer
dieser: Keine der Gruppen der Person hat eine Zuordnung zu einer Rolle (dann ist
die Anmeldung abgewiesen und ein Konto des Verzeichnisses deaktiviert); ein
Administrator hat das Konto deaktiviert; es gibt in Rentalars schon ein Konto
dieses Namens, das **nicht mit dem Verzeichnis verknüpft** ist (das Verknüpfen
über den Namen ist voreingestellt aus; der Test sagt es), oder die Person wurde im
Verzeichnis verschoben („Neuen Eintrag übernehmen“); das Konto ist ein lokales Notfallkonto oder
hat „Hat alle Rechte“ – dann gilt nur das Passwort in Rentalars; der Benutzername
aus dem Verzeichnis hat Zeichen, die Rentalars nicht erlaubt (nur Buchstaben,
Ziffern und `@ . + - _`, höchstens 150 Zeichen – ein zu langer oder unzulässiger
Name wird abgewiesen, nicht gekürzt); der Filter findet mehrere Einträge; das
Zertifikat passt nicht zum Namen des Servers (trag den Server mit Namen ein, nicht mit
der IP-Adresse); das Verzeichnis ist von Rentalars aus nicht erreichbar (Firewall,
oder der Betrieb hat die Verbindung ins interne Netz nicht freigegeben). „Verbindung
testen“ sagt, an welchem Schritt es hängt (Abschnitt 16, „Verzeichnis (LDAP)“).

**Das Verzeichnis ist ausgefallen – wie komme ich hinein?**
Mit einem lokalen Notfallkonto: Es meldet sich mit seinem eigenen Passwort in
Rentalars an, und das Verzeichnis ändert es nie. Hast du keins, aber „Anmeldung mit
lokalem Passwort erlauben“ ist an, melden sich auch Konten mit einem Passwort in
Rentalars weiter damit an. Gar nichts davon: Frag den Betreuer des Servers (Anleitung
„Betrieb“); vorher hätte Rentalars das Ausschalten des lokalen Passworts abgelehnt.

**Die Zusammenfassung ist „veraltet“, obwohl die automatischen Zusammenfassungen an
sind.**
Die Nacht kommt erst. Fasst sie dann trotzdem nicht zusammen, prüf in dieser
Reihenfolge: Ist das Projekt oder sein Kunde mit „Keine automatischen
Zusammenfassungen …“ ausgeschlossen? Liegt der Status nicht unter „Projekte in
diesen Status“ bzw. „Servicefälle in diesen Status“? Sind es weniger Mails als die
„kleinste Zahl von Mails“ (2), oder ist die letzte Zusammenfassung jünger als der
„kürzeste Abstand“ (20 Stunden)? Sind alle Nachrichten mit Schloss und ist „Nachrichten
mit Sperre lesen“ aus – dann liest der Auftrag nichts? Hat die Nacht ihr Maximum oder
das Token-Budget erreicht (dann macht sie in der nächsten Nacht weiter)? Steht oben
auf der Seite „angehalten: anderer Anbieter“ (dann stimmt eine Administratorin neu zu)?
**„Zeigen, was zusammengefasst würde“** und die Liste der „Ausführungen“ auf der Seite
„Automatische Zusammenfassungen“ sagen es (Abschnitt 14, „Automatische
Zusammenfassungen“). Mit „Neu zusammenfassen“ geht es sofort.

**Ich habe eine Eingangsrechnung hochgeladen, aber es stehen keine Positionen da.**
Es gibt zwei Gründe. Entweder ist die Datei ein Scan oder ein Foto: Rentalars hebt
sie auf, liest sie aber nicht (es gibt keine Texterkennung), und die Seite sagt es –
erfasse die Rechnung von Hand. Oder die KI zum Lesen von Rechnungen ist aus
(Einstellungen → KI, „Rechnungen lesen“): Ohne sie holt Rentalars nur Nummer,
Datum, Fälligkeit, einen bekannten Lieferanten und die Summen aus dem Text des PDFs,
die Positionen trägst du selbst ein. **„Nochmals auslesen“** füllt später nur leere
Felder und ersetzt Positionen nur, solange keine eingepflegt ist (Abschnitt 11,
„Eingangsrechnungen“).

**Bei einem Exemplar steht kein Restbuchwert.**
Es fehlen Kosten, Kaufdatum oder Nutzungsdauer – oder es ist nicht als Anlagegut,
GWG oder Handelsware erfasst. Auf der Seite des Exemplars (Karte „Anlagevermögen“;
nur mit dem Recht, Einkaufspreise zu sehen) trägst du es nach, wenn du Material
ändern darfst. Der Anlagenspiegel zählt solche Exemplare getrennt und nimmt sie nicht
in die Summen. Ein Kaufdatum in der Zukunft heißt „noch nicht angeschafft“ (Abschnitt
4, „Anlagevermögen, Abschreibung und Restbuchwert“).

**Ein Exemplar lässt sich nicht verkaufen („Gebrauchtverkauf aus Bestand“).**
Der Verkauf zeigt, was im Weg ist, statt des Knopfes: Das Exemplar ist für ein Projekt
ausgewählt, gepackt oder unterwegs, es ist eingebaut (oder es sind andere Artikel in
ihm eingebaut), sein Status ist „im Einsatz“, oder das Verkaufsdatum liegt in der
Zukunft oder vor dem Kauf. Ein Wunsch einer Planung oder eine Sperrzeit fragt nur nach
und lässt sich mit einem Haken bestätigen. Ein Verkauf lässt sich mit einer Begründung
rückgängig machen („Storno“), solange das Exemplar noch „verkauft“ ist (Abschnitt 4,
„Gebrauchtverkauf aus Bestand“).

**Eine freie Kraft sieht den Knopf „Preisangebot machen“ nicht.**
Der Schalter „Freie Kräfte dürfen einen eigenen Preis anbieten“ ist aus
(Einstellungen → Preisangebote freier Kräfte); die Person ist eine Aushilfe, und
„Auch Aushilfen“ ist aus; die Anfrage ist schon beantwortet oder zurückgenommen (der
Knopf gilt, solange sie auf Antwort wartet); das Projekt ist abgeschlossen oder
storniert; oder es wartet schon ein Angebot auf Antwort, oder die Runden sind
aufgebraucht – dann bleibt nur Annehmen oder Ablehnen (Abschnitt 12,
„Preisangebote freier Kräfte“).

**Die Kamera scannt nicht.**
Läuft Rentalars über `https://`? Ohne gesicherte Verbindung öffnet der Browser die
Kamera nicht (auf dem Server selbst, `localhost`, geht es). Ist der Browser Chrome,
Edge oder einer auf Android? Firefox und Safari erkennen keine Codes im Kamerabild;
dort tippst du den Code oder nimmst einen Handscanner. Hast du dem Browser die
Kamera erlaubt? Das Feld zum Eintippen geht immer (Abschnitt 4, „Scannen“). Beim
Packen weist Rentalars ein Exemplar mit Grund zurück – defekt, gesperrt, für ein
anderes Projekt geplant oder unterwegs –, das ist kein Fehler der Kamera (Abschnitt
10).

**Importierte Rechnungen aus alten Projekten fehlen im DATEV-Export.**
Absicht: Sie stehen nur drin, wenn du bei der Auswahl des Zeitraums **„Aus einem
Altsystem übernommene Rechnungen einschließen“** ankreuzt, weil ihr sie meist schon
anderswo gebucht habt (Abschnitt 16, „Buchhaltung: Lexware Office und DATEV“).
