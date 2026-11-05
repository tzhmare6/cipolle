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

Mit einem Dateinamen als Argument öffnet Cipolle direkt diese Datei. Sonst
öffnet es die zuletzt verwendete.

## Bedienung

**Datei:** Pro Geschäftsjahr gibt es eine Datei mit der Endung `.cipolle`. Jede
Eingabe wird sofort gespeichert, es gibt keinen Speichern-Befehl. Beim Öffnen
legt Cipolle eine Kopie der Datei als `.cipolle.bak` an und überschreibt dabei
die vorherige Kopie. Eine echte Datensicherung ersetzt das nicht.

**Erster Start:** Unter *Datei > Neu* den Namen und das Geschäftsjahr angeben und
den KMU-Kontenplan oder einen leeren Kontenplan wählen. Im Reiter *Konten*
die Eröffnungssaldi eintragen, auch Passivkonten als positive Beträge.

**Konten und Gruppen:** Der Kontenplan funktioniert wie bei Banana. Jedes Konto
nennt in *Summe in* seine Gruppe. Eine Gruppenzeile steht unter ihrem Inhalt,
zeigt das Total und summiert über ihr eigenes *Summe in* in die nächsthöhere
Gruppe, zum Beispiel 1020 Bank → 100 Flüssige Mittel → 10 Umlaufvermögen → 1 Total
Aktiven. Die Reihenfolge ergibt sich automatisch aus Nummern und Codes.

In der leeren Zeile am Ende legt ein Eintrag in der Spalte *Konto* ein Konto an
und ein Eintrag in *Gruppe* eine Gruppe. Ein neues Konto übernimmt Klasse und
Gruppe als Vorschlag. Neue Zeilen rücken erst beim nächsten Öffnen des Reiters an
ihren Platz. Konten mit Buchungen und Gruppen, in die noch etwas summiert, lassen
sich nicht löschen.

Bilanz und Erfolgsrechnung zeigen die Gruppen eingerückt mit Zwischentotalen. Die
Zeile für den Jahreserfolg steht in der Gruppe, die unter *Datei > Eigenschaften*
gewählt ist (im KMU-Kontenplan 28 Eigenkapital). Enthält eine Gruppe Aktiv- und
Passivkonten, erscheint eine Warnung. Dateien aus der ersten Cipolle-Version werden
beim Öffnen umgestellt, die Gruppen heissen dann G1, G2 usw.

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
| Ctrl+I | Zeile vor der aktuellen einfügen |
| Ctrl+Entf | Zeile löschen |

## Nicht enthalten

MWST, Fremdwährungen, Bankimport, Rechnungen, Kostenstellen, Budget, Vorjahresvergleich,
Rückgängig, Suche und der Import von Banana-Dateien.

## Entwicklung

```bash
.venv/bin/pip install -e '.[dev]'
```

```bash
.venv/bin/python -m pytest
```

Die Fachlogik liegt ohne Qt-Abhängigkeit in `cipolle/book.py` und
`cipolle/reports.py`, die Oberfläche in `cipolle/ui/`. Beträge sind überall ganze
Rappen. Die `.cipolle`-Datei ist eine normale SQLite-Datenbank und lässt sich
auch mit anderen Werkzeugen lesen.
