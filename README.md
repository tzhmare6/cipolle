# Cipolle

Lokale doppelte Buchhaltung für den Desktop, ohne Abo und ohne Cloud. Das
Programm deckt den Teil von Banana ab, der für eine einfache Buchhaltung ohne
MWST nötig ist.

## Installation (Debian/Ubuntu)

```bash
sudo apt install libxcb-cursor0
```

```bash
python3 -m venv .venv
```

```bash
.venv/bin/pip install -e .
```

## Starten

```bash
.venv/bin/cipolle
```

Mit einem Dateinamen als Argument öffnet Cipolle direkt diese Datei. Sonst öffnet
es die zuletzt verwendete, ausser sie wurde vor dem Beenden mit *Datei > Schliessen*
geschlossen. Dann beginnt es auf der Startseite. Nach dem Öffnen steht der Cursor
im Kontenplan.

Beim Start zeigt Cipolle kurz einen Dialog mit Animation, Version und Autoren. Er
schliesst sich von selbst, ein Klick oder eine Taste beendet ihn sofort. Unter
*Hilfe > Über Cipolle* lässt er sich wieder öffnen.

## Als Datei oder Paket bauen

`build.sh` packt Cipolle mit PyInstaller in eine einzige ausführbare Datei:

```bash
./build.sh
```

Das Ergebnis ist `dist/cipolle`. Sie läuft auf x86-64-Linux mit gleich alter oder
neuerer glibc als auf dem Build-Rechner.

`build-deb.sh` macht daraus ein Debian-Paket und baut die Datei bei Bedarf neu:

```bash
./build-deb.sh
```

```bash
sudo apt install ./dist/cipolle_0.1.0_amd64.deb
```

Das Paket installiert das Programm nach `/usr/bin/cipolle`, dazu den Eintrag im
Startmenü, die Icons und den Dateityp `.cipolle`. Qt und Python stecken im Programm.
Nur glibc und die Grafik-Bibliotheken stammen vom System und stehen als
Abhängigkeiten im Paket, deshalb `apt` und nicht `dpkg -i` verwenden.

Auf dem Mac baut `build-mac.sh` eine App mit Icon und Dateityp `.cipolle`:

```bash
./build-mac.sh
```

Das Ergebnis ist `dist/Cipolle.app`. Installiert wird sie über das Disk-Image aus
`build-dmg.sh`. Sie läuft auf Macs mit demselben Prozessortyp wie der Build-Rechner. Die App ist nicht notarisiert,
auf einem anderen Mac blockiert Gatekeeper deshalb den ersten Start. `build.sh`
funktioniert auf dem Mac ebenfalls, liefert aber nur ein Programm für das Terminal.

`build-dmg.sh` packt die App in ein Disk-Image und baut sie bei Bedarf neu:

```bash
./build-dmg.sh
```

Das Ergebnis ist `dist/Cipolle-0.1.0.dmg` mit dem Cipolle-Icon. Beim Öffnen zeigt das
Fenster links die App, rechts den Ordner `Applications` und dazwischen einen Pfeil.

Installieren auf dem Mac:

1. `Cipolle-0.1.0.dmg` mit einem Doppelklick öffnen.
2. Cipolle im Fenster auf den Ordner `Applications` ziehen.
3. Das Laufwerk «Cipolle 0.1.0» im Finder auswerfen. Die DMG-Datei wird danach nicht mehr gebraucht.

Das Hintergrundbild `packaging/dmg-background.tiff` entsteht mit
`packaging/make_dmg_background.py`, das dafür Pillow braucht.

## Bedienung

**Datei:** Pro Geschäftsjahr gibt es eine Datei mit der Endung `.cipolle`. Jede
Eingabe wird sofort gespeichert, es gibt keinen Speichern-Befehl. Schlägt das fehl,
etwa bei einer schreibgeschützten Datei, erscheint eine Meldung und das Feld bleibt
offen. Beim Öffnen
legt Cipolle eine Kopie der Datei als `.cipolle.bak` an und überschreibt dabei
die vorherige Kopie. Eine echte Datensicherung ersetzt das nicht. Dateien älterer
Cipolle-Versionen werden beim Öffnen automatisch umgestellt und lassen sich danach
mit diesen älteren Versionen nicht mehr öffnen.

**Erster Start:** Unter *Datei > Neu* den Namen und das Geschäftsjahr angeben und
den KMU-Kontenplan oder einen leeren Kontenplan wählen. Im Reiter *Konten*
die Eröffnungssaldi eintragen, auch Passivkonten als positive Beträge.

**Konten und Gruppen:** Der Kontenplan funktioniert wie bei Banana. Jedes Konto
nennt in *Summe in* seine Gruppe. Eine Gruppenzeile steht unter ihrem Inhalt,
zeigt das Total und summiert über ihr eigenes *Summe in* in die nächsthöhere
Gruppe, zum Beispiel 1020 Bank → 100 Flüssige Mittel → 10 Umlaufvermögen → 1 Total
Aktiven. Die Reihenfolge ergibt sich automatisch aus Nummern und Codes.

In einer leeren Zeile legt ein Eintrag in der Spalte *Konto* ein Konto an und ein
Eintrag in *Gruppe* eine Gruppe. In einer eingefügten Zeile gehört der neue Eintrag
zur Gruppe an dieser Stelle, in der Zeile `*` am Ende schlägt Cipolle die Gruppe des
vorangehenden Kontos vor. Ändert sich eine Kontonummer, ein Gruppencode oder *Summe
in*, rückt die Zeile sofort an ihren Platz und der Cursor wandert mit. Leere
eingefügte Zeilen verschwinden beim Wechsel des Reiters. Konten mit Buchungen und
Gruppen, in die noch etwas summiert, lassen sich nicht löschen.

Bilanz und Erfolgsrechnung zeigen die Gruppen eingerückt mit Zwischentotalen. Die
Zeile für den Jahreserfolg steht in der Gruppe, die unter *Datei > Eigenschaften*
gewählt ist (im KMU-Kontenplan 28 Eigenkapital). Ohne gewählte Gruppe steht sie
direkt vor *Total Passiven*. Enthält eine Gruppe Aktiv- und Passivkonten, erscheint
eine Warnung. Bei Dateien aus der ersten Cipolle-Version heissen die Gruppen nach der
Umstellung G1, G2 usw.

**Kontenplan exportieren und importieren:** *Datei > Kontenplan exportieren*
speichert Gruppen und Konten als JSON-Datei, ohne Eröffnungssaldi und Buchungen.
*Datei > Kontenplan importieren* prüft die Datei zuerst vollständig und zeigt, was
sich ändert. *Zusammenführen* ergänzt und aktualisiert, ohne etwas zu entfernen.
*Ersetzen* entfernt zusätzlich alles, was nicht in der Datei steht. Konten mit
Buchungen und ihre Gruppen bleiben dabei immer erhalten.

```json
{
  "format": "cipolle-kontenplan",
  "version": 1,
  "jahreserfolg_in": "28",
  "gruppen": [
    { "code": "100", "name": "Flüssige Mittel", "summe_in": "10" }
  ],
  "konten": [
    { "nummer": "1020", "name": "Bank", "klasse": "Aktiven", "summe_in": "100" }
  ]
}
```

Die Klasse ist `Aktiven`, `Passiven`, `Aufwand` oder `Ertrag`.

**Buchungen:** In der Zeile mit dem `*` erfassen, Enter oder Tab springt ins
nächste Feld.

| Feld | Eingabe |
| --- | --- |
| Datum | `31.12.2026`, `31.12.26`, `31.12` oder `3112` |
| Soll, Haben | Nummer, oder ein Teil von Nummer oder Bezeichnung, wenn er eindeutig ist |
| Betrag | `1'234.50`, `1234,5` oder `-50` für eine Korrektur |

Eine neue Zeile übernimmt das Datum der vorherigen. Fehlerhafte Zeilen werden
rot, der Grund steht im Tooltip. Sie zählen nicht in den Auswertungen. Das
steht dann auch auf jedem Bericht.

**Zeilen und Zellen:** Beide Tabellen haben Zeilennummern. Ein Klick auf die Nummer
markiert die ganze Zeile, mit gedrückter Maustaste, Shift oder Ctrl auch mehrere.
Die Taste Entf löscht markierte Zeilen nach einer Rückfrage. Ist keine ganze Zeile
markiert, leert sie die markierten Zellen. Pflichtfelder wie die Kontonummer bleiben
dabei erhalten. Ein Rechtsklick auf Zeilennummer oder Zelle öffnet das Menü mit
*Zeile einfügen oben*, *Zeile einfügen unten* und *Zeile löschen*.

**Rückgängig:** Ctrl+Z nimmt die letzte Aktion zurück, Ctrl+Y wiederholt sie. Das
Menü *Bearbeiten* nennt die Aktion, und die Tabelle springt zur betroffenen Zeile.
Eine Aktion mit mehreren Zeilen ist ein einziger Schritt. Der Verlauf liegt in der
Datei, übersteht das Schliessen und umfasst die letzten 500 Schritte. Während man
in einem Feld tippt, wirkt Ctrl+Z nur auf dieses Feld. *Neues Jahr erstellen* und
eingefügte leere Zeilen im Kontenplan lassen sich nicht zurücknehmen. Änderungen mit
anderen Werkzeugen landen nicht im Verlauf.

**Sammelbuchungen:** Mehrere aufeinanderfolgende Zeilen mit nur Soll oder nur
Haben erfassen. Ihre Summen müssen sich ausgleichen, sonst wird die letzte Zeile
rot.

**Auswertungen:** Kontoauszug, Bilanz, Erfolgsrechnung und Journal lassen sich
als PDF oder CSV speichern und drucken. Ein Klick auf die Kontonummer öffnet den
Kontoauszug, ein Klick auf das Datum führt zur Buchung.

**Jahreswechsel:** *Datei > Neues Jahr erstellen* legt die Datei des Folgejahrs
an, mit Kontenplan und Schlusssalden als Eröffnung. Der Jahreserfolg geht auf das
gewählte Konto (vorgeschlagen ist 2970 Gewinnvortrag). Wird das alte Jahr später
noch geändert, holt *Datei > Eröffnung aus Vorjahr aktualisieren* die Saldi neu.

| Tastenkürzel | Funktion |
| --- | --- |
| Ctrl+1 bis Ctrl+6 | Reiter wechseln |
| Ctrl+W | Datei schliessen |
| Ctrl+Z | Rückgängig |
| Ctrl+Y oder Ctrl+Shift+Z | Wiederholen |
| Ctrl+I | Zeile oben einfügen |
| Ctrl+Shift+I | Zeile unten einfügen |
| Entf | Zellen leeren oder markierte Zeilen löschen |
| Ctrl+Entf | Aktuelle oder markierte Zeilen löschen |

Auf macOS gilt in allen Tastenkürzeln Command (⌘) anstelle von Ctrl, zum Beispiel
⌘Z für Rückgängig.

## Nicht enthalten

MWST, Fremdwährungen, Bankimport, Rechnungen, Kostenstellen, Budget, Vorjahresvergleich,
Suche und der Import von Banana-Dateien.

## Entwicklung

```bash
.venv/bin/pip install -e '.[dev]'
```

```bash
.venv/bin/python -m pytest
```

Die Fachlogik liegt ohne Qt-Abhängigkeit in `cipolle/book.py`, `cipolle/reports.py`
und `cipolle/chart_io.py`, die Oberfläche in `cipolle/ui/`. Beträge sind überall ganze
Rappen. Die `.cipolle`-Datei ist eine normale SQLite-Datenbank und lässt sich auch mit
anderen Werkzeugen lesen.

Die Bilder der App liegen in `cipolle/assets/`, die Originale in `pictures/`. Icon,
Hintergrundbild und Startdialog stehen in `cipolle/ui/branding.py`, dort lässt sich
mit `BACKDROP_OPACITY` auch die Stärke des Hintergrundbilds einstellen.

Für Rückgängig schreiben TEMP-Trigger zu jeder Änderung den Umkehrbefehl in die
Tabellen `undo_steps` und `undo_log`. Sie werden bei jedem Öffnen neu erzeugt und
passen so immer zum Schema. Änderungsfunktionen in `Book` tragen den Dekorator
`@undoable`, mehrteilige Aktionen laufen in `with book.step(...)`.

Die Anleitung `docs/Cipolle-Anleitung.pdf` entsteht auf dem Mac in zwei Schritten.
`docs/anleitung/make_screenshots.py` fotografiert die App mit Beispieldaten, dafür
mit `QT_QPA_PLATFORM=cocoa` starten. `docs/anleitung/make_pdf.py` setzt daraus die
PDF und braucht reportlab und Pillow.
