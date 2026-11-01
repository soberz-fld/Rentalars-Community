# Aktualisierung

Eine neue Version von Rentalars spielst du mit einem Befehl ein. Er sichert
vorher alles, und wenn die neue Version nicht läuft, stellt er den alten
Stand selbst wieder her.

```sh
sudo rentalars update rentalars-1.0.0.tar.gz
```

Die Nutzer merken davon eine Unterbrechung von meist deutlich unter einer
Minute. Such dir trotzdem eine ruhige Zeit: Was jemand in diesem Augenblick
gerade speichert, kann verloren gehen.

## Vorher

1. **Lies, was sich ändert.** Im Paket liegt `CHANGELOG.md`. Dort steht je
   Version, was neu ist – und unter „Beim Aktualisieren beachten“, wenn du
   etwas tun musst.
2. **Bring das Paket auf den Server**, zum Beispiel
   `scp rentalars-1.0.0.tar.gz du@rentalars.example.de:`
3. **Sag den Kolleginnen und Kollegen Bescheid.**

Eine Version zu überspringen ist in Ordnung: Die Datenbank wird Schritt für
Schritt auf den neuen Stand gebracht, von jeder Version aus.

## Was der Befehl tut

In dieser Reihenfolge, und er sagt bei jedem Schritt, was geschieht:

1. **Voraussetzungen prüfen.** Passt die Python-Version des Servers zur
   neuen Version? Ist genug Platz frei (1 GB für das Programm, 500 MB für
   die Sicherung)? Läuft die Datenbank – oder, wenn sie auf einem anderen
   Server liegt, antwortet sie? Fehlt etwas, bricht er hier ab –
   **es wurde dann nichts verändert**.
2. **Sichern.** Datenbank und Dateien wandern in eine Sicherung mit `-keep`
   im Namen. Sie wird nie von selbst gelöscht. Ist die Verschlüsselung
   eingeschaltet, ist auch diese Sicherung verschlüsselt (`.tar.gz.enc`).
3. **Die neue Version neben die laufende stellen.** Programm und
   Python-Bibliotheken kommen in ein eigenes Verzeichnis. Rentalars läuft
   währenddessen weiter. Schlägt dieser Schritt fehl (zum Beispiel, weil der
   Server gerade keine Bibliotheken herunterladen kann), ist nichts passiert.
4. **Umschalten.** Rentalars anhalten, auf die neue Version zeigen, die
   Datenbank auf deren Stand bringen, die Konfiguration von NGINX an die
   installierte NGINX-Version anpassen, den Befehl `rentalars` neu
   schreiben, starten, Zeitpläne
   einschalten, die mit der neuen Version dazukommen, prüfen,
   ob Rentalars antwortet. Auf einem
   Raspberry Pi richtet dieser Schritt außerdem Arbeitsprozesse
   und Speicher von MariaDB nach dem Arbeitsspeicher aus.
5. **Zurück, falls Schritt 4 misslingt.** Der Befehl schaltet dann selbst
   auf die alte Version zurück und spielt die Sicherung aus Schritt 2 ein.
   Er endet mit einer Fehlermeldung; Rentalars läuft wieder wie vorher, es
   sind keine Daten verloren.
6. **Lokale KI**: Nach einem erfolgreichen Update übernimmt
   `rentalars ai refresh` die Einstellungen der lokalen KI, die die neue
   Version setzt – ohne Download und ohne Modellwechsel; ohne lokale KI
   geschieht nichts ([betrieb.md](betrieb.md), „Nach einem Update: `ai
   refresh`“). Ein Fehler dabei bricht das Update nicht ab.

Am Ende steht:

```
==> Fertig. Rentalars 1.0.0 läuft.
    Sicherung von vorher:  /var/backups/rentalars/rentalars-2026-11-02_191503-keep.tar.gz
    Zurück zur alten Version, falls nötig:  sudo rentalars rollback
```

Melde dich danach an und klick einmal durch: ein Projekt öffnen, eine
Packliste, die Materialliste.

## Der Rückweg

Die neue Version läuft, aber etwas stimmt nicht – eine Funktion fehlt, etwas
rechnet anders, als ihr es braucht. Dann geht es zurück:

```sh
sudo rentalars rollback
```

Der Befehl zeigt, wohin es zurückgeht, und fragt nach. Dann

1. sichert er den jetzigen Stand (damit auch dieser Schritt umkehrbar ist),
2. schaltet auf das Programm der vorigen Version,
3. spielt die Sicherung ein, die vor der Aktualisierung geschrieben wurde.

**Alles, was seit der Aktualisierung eingegeben wurde, ist danach nicht
mehr da.** Deshalb: je früher, desto besser. Nach einem Tag Arbeit mit der
neuen Version ist es meist klüger, den Fehler zu melden und auf die
Korrektur zu warten.

Der Rückweg führt genau einen Schritt zurück – zur Version vor der letzten
Aktualisierung. Rentalars hebt dafür immer zwei Versionen auf: die laufende
und die vorige.

### Warum nicht einfach das alte Programm starten?

Eine neue Version verändert oft den Aufbau der Datenbank. Das alte Programm
kann mit der veränderten Datenbank nicht umgehen. Darum gehören Programm und
Datenstand zusammen, und der Rückweg stellt beide wieder her.

## Wenn die Aktualisierung abbricht

| Meldung | Bedeutung |
|---|---|
| „Python … oder neuer wird gebraucht“ | Die neue Version verlangt ein neueres Python, als dein Ubuntu mitbringt. Erst Ubuntu auf die nächste LTS-Version heben, dann Rentalars aktualisieren. Es wurde nichts verändert. |
| „Auf … sind nur … MB frei“ | Platz schaffen (alte Sicherungen), dann noch einmal. Es wurde nichts verändert. |
| „MariaDB läuft nicht“ | `sudo systemctl start mariadb`, dann noch einmal. |
| „Die Datenbank auf … antwortet nicht“ | Die Datenbank liegt auf einem anderen Server, und der ist nicht erreichbar. Das klärst du mit dem, der ihn betreibt; `sudo rentalars status` zeigt, was Rentalars sieht. Es wurde nichts verändert. |
| `sudo: rentalars: command not found` | Der Befehl fehlt auf dem Server. Aktualisiere einmal mit dem Skript aus dem neuen Paket, `sudo bash /pfad/zu/rentalars-X.Y.Z/deploy/update.sh /pfad/zu/rentalars-X.Y.Z.tar.gz`; danach ist er da. |
| „…/deploy/backup.sh: Permission denied“ | Die Skripte der installierten Version haben ihr Ausführungsrecht verloren. Es wurde nichts verändert. Aktualisiere wie in der Zeile darüber direkt auf die neue Version. |
| „Die Aktualisierung ist fehlgeschlagen und wurde zurückgenommen“ | Schritt 4 ist misslungen; der alte Stand läuft wieder. Die eigentliche Fehlermeldung steht weiter oben in der Ausgabe und in `sudo journalctl -u rentalars`. Bitte melde sie. |

## Ubuntu und Python aktuell halten

Rentalars nutzt das Python deines Ubuntu und baut auf Django in einer
Langzeitversion auf; beide bekommen über Jahre Sicherheitskorrekturen
(NFA-054). Unterstützt sind Ubuntu Server 24.04 LTS und 26.04 LTS (NFA-063),
auf einem Raspberry Pi 4 oder 5 außerdem Raspberry Pi OS auf Basis von
Debian 13 (NFA-070; [installation.md](installation.md), „Welche
Ubuntu-Version?“ und „Raspberry Pi“). Auf Raspberry Pi OS gilt hier „Debian“
statt „Ubuntu“: Sicherheitsaktualisierungen genauso mit `apt`.

- **Ubuntu:** Sicherheitsaktualisierungen laufend einspielen
  (`sudo apt update && sudo apt upgrade`, oder automatisch).
- **Rentalars:** Jede neue Version bringt die Bibliotheken auf den Stand,
  mit dem sie getestet wurde. Wer aktualisiert, hat auch die
  Sicherheitskorrekturen von Django.

### Von Ubuntu 24.04 auf 26.04 wechseln

Ubuntu 26.04 bringt ein neues Python (3.14 statt 3.12), ein neues NGINX und
ein neues MariaDB mit. Die Daten bleiben, wo sie sind. Aber die
Python-Bibliotheken von Rentalars sind für das alte Python eingerichtet –
**nach dem Wechsel startet Rentalars deshalb nicht, bis du es einmal
aktualisiert hast.** Plane dafür eine ruhige Stunde ein.

1. Rentalars auf die neueste Version bringen und das
   Paket auf dem Server liegen lassen.
2. `sudo rentalars backup --keep` – und die Datei **vom Server holen**.
3. Ubuntu heben: `sudo do-release-upgrade`. Die Fragen des Programms nach
   geänderten Konfigurationsdateien von NGINX und MariaDB beantwortest du mit
   „beibehalten“ (das ist die Voreinstellung).
4. Nach dem Neustart zeigt der Browser „502 Bad Gateway“. Das ist erwartet.
5. Einmal aktualisieren, mit demselben Paket wie in Schritt 1:

   ```sh
   sudo rentalars update rentalars-1.0.0.tar.gz
   ```

   Der Befehl meldet „Rentalars läuft gerade nicht“, sichert, richtet die
   Bibliotheken für das neue Python ein, schreibt die Konfiguration von
   NGINX in der Form, die das neue NGINX erwartet, und startet Rentalars.
6. Anmelden und durchklicken wie nach jeder Aktualisierung.

`sudo rentalars rollback` führt nach diesem Schritt **nicht** zurück: Die
vorige Version von Rentalars gehört zum alten Python, das es nicht mehr
gibt. Der Rückweg ist die Sicherung aus Schritt 2 auf einem Server mit dem
alten Ubuntu.
