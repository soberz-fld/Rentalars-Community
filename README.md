# Rentalars

Projekt-, Material- und Crewverwaltung für Betriebe der Veranstaltungstechnik – freie Software (GPL-3.0-or-later),
im Browser auf einem eigenen Server.

*Project, material and crew management for event technology companies – free software (GPL-3.0-or-later), running in
the browser on a server of your own.*

## Inhalt dieses Repositorys

Das Repository fasst alle Teile des Projekts zusammen. Jeder Teil liegt in einem eigenen Ordner mit eigener README,
eigenen Tests und eigenem Ablauf für Prüfung und Veröffentlichung.

| Ordner | Was es ist | Stand |
|--------|------------|-------|
| [`server/`](server/) | Der Rentalars-Server: die Webanwendung mit API, Installations- und Sicherungsskripten, Handbuch und Entwicklerdokumentation | Version 1.0.0 |

Weitere Teile – das Rentalars Gateway, über das Apps den Server aus dem Internet erreichen, und die Begleit-Apps – kommen
als eigene Ordner hinzu (`gateway/`, `companion/`).

Wer Rentalars **einsetzen** will, beginnt in der [README des Servers](server/README.md); dort stehen Funktionsumfang,
Installation und die Anleitungen. Wer **mitentwickeln** will, liest [CONTRIBUTING.md](CONTRIBUTING.md) und
[server/docs/dev/getting-started.md](server/docs/dev/getting-started.md).

## Aufbau

```
.github/      Prüfungen (CI) und Abhängigkeits-Updates für das ganze Repository
server/       Rentalars-Server (Django); hat alles, was er braucht, in sich: Quelltext, Tests, Dokumentation, Lizenzhinweise
LICENSE       GNU General Public License, Version 3
```

Die Installationspakete (`rentalars-<Version>.tar.gz`) entstehen aus dem Ordner `server/` mit `server/scripts/build_package.sh`.

## Lizenz

Rentalars steht unter der GNU General Public License, Version 3 oder später (GPL-3.0-or-later); der Text liegt in
[LICENSE](LICENSE). Für den Server gilt zusätzlich eine Bestimmung nach Abschnitt 7 b und 7 d der GPL
([server/ADDITIONAL-TERMS.md](server/ADDITIONAL-TERMS.md)). Verwendete Bibliotheken und Schriften mit ihren Lizenzen
nennt [server/THIRD-PARTY.md](server/THIRD-PARTY.md).

Copyright © 2026 Lars Wilting, fld-vt.de.

**Entstehung mit KI.** Große Teile von Rentalars – Programmcode, Tests und Dokumentation – wurden mit Hilfe von
KI-Assistenten geschrieben, vor allem mit Claude (Anthropic, über Claude Code); Einzelheiten stehen in der README des Servers.

---

*English:* This repository holds the whole Rentalars project. The server (web application, API, installation scripts,
manuals) is in [`server/`](server/), see its [English README](server/docs/en/README.md). The Rentalars Gateway and the
companion apps will follow as folders of their own (`gateway/`, `companion/`). Licence: GPL-3.0-or-later.
