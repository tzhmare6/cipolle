"""Setzt die Anleitung docs/Cipolle-Anleitung.pdf.

Aufruf auf dem Mac im Projektordner, mit reportlab und Pillow:
    python docs/anleitung/make_pdf.py
Vorher make_screenshots.py ausführen. Die Schriften stammen aus macOS.
"""

from pathlib import Path

from PIL import Image as PILImage, ImageDraw
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, CondPageBreak, Flowable, Frame, Image, KeepTogether, ListFlowable, ListItem,
    NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "build/anleitung"
SHOTS = WORK / "shots"
TARGET = ROOT / "docs/Cipolle-Anleitung.pdf"
VERSION = next(line.split('"')[1] for line in (ROOT / "cipolle/__init__.py").read_text().splitlines()
               if line.startswith("__version__"))

FONTS = Path("/System/Library/Fonts/Supplemental")
for name, file in (("Body", "Arial.ttf"), ("Body-Bold", "Arial Bold.ttf"), ("Body-Italic", "Arial Italic.ttf"),
                   ("Body-BoldItalic", "Arial Bold Italic.ttf"), ("Round", "Arial Rounded Bold.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(FONTS / file)))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic")

INK = colors.HexColor("#3B2A20")
MUTED = colors.HexColor("#7A6A5C")
CREAM = colors.HexColor("#FBF1DC")
SAND = colors.HexColor("#F1DFB8")
ORANGE = colors.HexColor("#E2702A")
RED = colors.HexColor("#B8432A")
BLUSH = colors.HexColor("#FBE6DF")

PAGE_W, PAGE_H = A4
MARGIN = 22 * mm
WIDTH = PAGE_W - 2 * MARGIN


def cut_out_onion() -> Path:
    """Stellt die Zwiebel frei: Das Weiss wird von den Rändern her transparent."""
    path = WORK / "onion.png"
    image = PILImage.open(ROOT / "pictures/cipolle_icon_blank.jpeg").convert("RGB").resize((700, 700))
    for corner in ((0, 0), (699, 0), (0, 699), (699, 699)):
        ImageDraw.floodfill(image, corner, (255, 0, 255), thresh=28)
    raw = image.tobytes()
    pixels = [tuple(raw[i:i + 3]) for i in range(0, len(raw), 3)]
    rgba = PILImage.new("RGBA", image.size)
    rgba.putdata([(r, g, b, 0) if (r, g, b) == (255, 0, 255) else (r, g, b, 255) for r, g, b in pixels])
    rgba.crop(rgba.getbbox()).save(path)
    return path


def crying_onion() -> Path:
    """Das Schlussbild der Startanimation, ohne die Textzeilen des Dialogs."""
    path = WORK / "crying.png"
    image = PILImage.open(SHOTS / "ueber.png").convert("RGB")
    width, height = image.size
    image.crop((0, 0, width, int(height * 0.80))).save(path)
    return path


WORK.mkdir(parents=True, exist_ok=True)
ONION = cut_out_onion()
CRYING = crying_onion()
ONION_RATIO = PILImage.open(ONION).size[1] / PILImage.open(ONION).size[0]

body = ParagraphStyle("body", fontName="Body", fontSize=10.5, leading=15.5, textColor=INK, spaceAfter=7)
small = ParagraphStyle("small", parent=body, fontSize=9.2, leading=13, spaceAfter=0)
cell = ParagraphStyle("cell", parent=body, fontSize=9.6, leading=13.2, spaceAfter=0)
head_cell = ParagraphStyle("headcell", parent=cell, fontName="Body-Bold", textColor=colors.white)
h2 = ParagraphStyle("h2", parent=body, fontName="Round", fontSize=13, leading=17, textColor=RED, spaceBefore=9, spaceAfter=4)
caption = ParagraphStyle("caption", parent=body, fontName="Body-Italic", fontSize=8.8, leading=12, textColor=MUTED,
                         alignment=TA_CENTER, spaceBefore=3, spaceAfter=10)
command = ParagraphStyle("command", parent=body, fontName="Courier-Bold", fontSize=9.4, leading=13, textColor=INK,
                         backColor=CREAM, borderPadding=(5, 7, 5, 7), spaceBefore=6, spaceAfter=11, leftIndent=7, rightIndent=7)
toc1 = ParagraphStyle("toc1", parent=body, fontName="Body", fontSize=11.5, leading=21, spaceAfter=0)


def key(text: str) -> str:
    return f'<font name="Courier-Bold" size="9.6" color="#B8432A">{text}</font>'


class ChapterHead(Flowable):
    """Kapitelkopf mit Nummer und Zwiebel. Er liefert auch den Eintrag im Inhaltsverzeichnis."""

    # Flowable.__init__ setzt height auf 0, darum ein eigener Name für die Bandhöhe.
    band = 17 * mm

    def __init__(self, number: int, title: str):
        super().__init__()
        self.number, self.title = number, title
        self.key = f"chapter{number}"

    def wrap(self, available_width, available_height):
        return WIDTH, self.band + 6 * mm

    def draw(self):
        canvas = self.canv
        y = 6 * mm
        canvas.setFillColor(CREAM)
        canvas.roundRect(0, y, WIDTH, self.band, 5 * mm, stroke=0, fill=1)
        canvas.setFillColor(ORANGE)
        canvas.circle(10.5 * mm, y + self.band / 2, 6 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont("Round", 15)
        canvas.drawCentredString(10.5 * mm, y + self.band / 2 - 5.2, str(self.number))
        canvas.setFillColor(INK)
        canvas.setFont("Round", 19)
        canvas.drawString(20 * mm, y + self.band / 2 - 6.6, self.title)
        high = 14 * mm
        canvas.drawImage(str(ONION), WIDTH - high / ONION_RATIO - 5 * mm, y + 1.5 * mm, high / ONION_RATIO, high, mask="auto")
        canvas.bookmarkHorizontal(self.key, 0, y + self.band)
        canvas.addOutlineEntry(f"{self.number}  {self.title}", self.key, 0, closed=False)


class Manual(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, ChapterHead):
            self.notify("TOCEntry", (0, f"{flowable.number}&nbsp;&nbsp;&nbsp;{flowable.title}", self.page, flowable.key))


def shot(name: str, text: str, width: float = WIDTH) -> KeepTogether:
    path = SHOTS / f"{name}.png"
    pixels = PILImage.open(path).size
    picture = Image(str(path), width=width, height=width * pixels[1] / pixels[0])
    frame = Table([[picture]], colWidths=[width + 1.2])
    frame.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, SAND), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("RIGHTPADDING", (0, 0), (-1, -1), 0), ("TOPPADDING", (0, 0), (-1, -1), 0),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    frame.hAlign = "CENTER"
    return KeepTogether([Spacer(1, 3), frame, Paragraph(text, caption)])


def note(text: str, title: str = "Tipp", tone=CREAM) -> Table:
    size = 11 * mm
    onion = Image(str(ONION), width=size, height=size * ONION_RATIO)
    content = [Paragraph(f'<font name="Round" color="#B8432A">{title}</font>', small), Spacer(1, 2), Paragraph(text, small)]
    table = Table([[onion, content]], colWidths=[17 * mm, WIDTH - 17 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), tone), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROUNDEDCORNERS", [8, 8, 8, 8]), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (0, 0), 9), ("RIGHTPADDING", (0, 0), (0, 0), 0), ("LEFTPADDING", (1, 0), (1, 0), 6),
    ]))
    table.spaceBefore, table.spaceAfter = 5, 11
    return table


def grid(rows: list[list[str]], widths: list[float]) -> Table:
    data = [[Paragraph(text, head_cell) for text in rows[0]]]
    data += [[Paragraph(text, cell) for text in row] for row in rows[1:]]
    total = sum(widths)
    table = Table(data, colWidths=[WIDTH * w / total for w in widths], repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), RED), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 4.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
             ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, SAND), ("ROUNDEDCORNERS", [6, 6, 0, 0])]
    style += [("BACKGROUND", (0, i), (-1, i), CREAM) for i in range(2, len(data), 2)]
    table.setStyle(TableStyle(style))
    table.spaceBefore, table.spaceAfter = 4, 11
    return table


def bullets(items: list[str], numbered: bool = False) -> ListFlowable:
    entries = [ListItem(Paragraph(text, ParagraphStyle("item", parent=body, spaceAfter=3))) for text in items]
    options = dict(bulletType="1", bulletFontName="Round", bulletFontSize=10.5, bulletColor=ORANGE) if numbered else \
        dict(bulletType="bullet", start="•", bulletFontSize=12, bulletColor=ORANGE)
    return ListFlowable(entries, leftIndent=15, spaceAfter=7, **options)


def P(text: str) -> Paragraph:
    return Paragraph(text, body)


def H(text: str) -> Paragraph:
    return Paragraph(text, h2)


def cover(canvas, _doc):
    canvas.saveState()
    canvas.setFillColor(CREAM)
    canvas.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    canvas.setFillColor(ORANGE)
    canvas.rect(0, 0, PAGE_W, 13 * mm, stroke=0, fill=1)
    canvas.setFillColor(RED)
    canvas.rect(0, 13 * mm, PAGE_W, 2.5 * mm, stroke=0, fill=1)
    logo = ROOT / "cipolle/assets/logo.png"
    width = 150 * mm
    height = width * 1100 / 999
    canvas.drawImage(str(logo), (PAGE_W - width) / 2, PAGE_H - height - 22 * mm, width, height, mask="auto")
    canvas.setFillColor(INK)
    canvas.setFont("Round", 36)
    canvas.drawCentredString(PAGE_W / 2, 52 * mm, "Anleitung")
    canvas.setFont("Body", 12)
    canvas.setFillColor(MUTED)
    canvas.drawCentredString(PAGE_W / 2, 42 * mm, "Lokale doppelte Buchhaltung für den Desktop")
    canvas.drawCentredString(PAGE_W / 2, 35.5 * mm, f"Version {VERSION}")
    canvas.restoreState()


def page(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(SAND)
    canvas.setLineWidth(0.6)
    canvas.line(MARGIN, 15 * mm, PAGE_W - MARGIN, 15 * mm)
    canvas.setFont("Body", 8.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 10.5 * mm, "Cipolle · Anleitung")
    canvas.drawRightString(PAGE_W - MARGIN, 10.5 * mm, str(doc.page))
    canvas.restoreState()


story = [NextPageTemplate("body"), PageBreak()]

toc = TableOfContents()
toc.levelStyles = [toc1]
toc.dotsMinLevel = 0
story += [Paragraph("Inhalt", ParagraphStyle("contents", parent=h2, fontSize=24, leading=30, textColor=INK, spaceAfter=12)), toc]
crying_size = PILImage.open(CRYING).size
story += [Spacer(1, 10 * mm), Image(str(ONION), width=46 * mm, height=46 * mm * ONION_RATIO),
          Paragraph("Zahlungen, die zu Tränen rühren.", ParagraphStyle("tag", parent=caption, fontSize=11, spaceBefore=6)), PageBreak()]

# 1
story += [ChapterHead(1, "Willkommen"),
    P("Cipolle ist eine doppelte Buchhaltung für den eigenen Rechner. Sie kommt ohne Abo und ohne Cloud aus, alle Daten "
      "bleiben in einer Datei auf deinem Computer. Das Programm deckt ab, was eine einfache Buchhaltung ohne MWST braucht, "
      "und lässt sich fast vollständig mit der Tastatur bedienen."),
    H("Das kann Cipolle"),
    bullets(["Kontenplan mit Gruppen und Zwischentotalen, auf Wunsch nach dem Schweizer KMU-Kontenrahmen",
             "Schnelles Erfassen von Buchungen und Sammelbuchungen",
             "Kontoauszug, Bilanz, Erfolgsrechnung und Journal, als PDF, als CSV oder auf Papier",
             "Rückgängig und Wiederholen, auch nach dem Schliessen der Datei",
             "Jahreswechsel mit automatischer Übernahme der Schlusssalden"]),
    H("Das ist nicht dabei"),
    P("MWST, Fremdwährungen, Bankimport, Rechnungen, Kostenstellen, Budget, Vorjahresvergleich, Suche und der Import "
      "von Banana-Dateien."),
    H("Doppelte Buchhaltung in einer Minute"),
    P("Jede Buchung berührt zwei Konten: Sie steht im <b>Soll</b> des einen und im <b>Haben</b> des anderen Kontos. "
      "Dadurch gleichen sich Soll und Haben immer aus. Welche Seite ein Konto erhöht, hängt von seiner Klasse ab."),
    grid([["Klasse", "Bedeutung", "Nimmt zu im", "Beispiel"],
          ["Aktiven", "Was die Firma besitzt", "Soll", "1020 Bank"],
          ["Passiven", "Schulden und Eigenkapital", "Haben", "2800 Eigenkapital"],
          ["Aufwand", "Was Geld kostet", "Soll", "6000 Raumaufwand"],
          ["Ertrag", "Was Geld einbringt", "Haben", "3000 Dienstleistungsertrag"]], [2, 4, 2, 4]),
    note(f"Die Miete wird von der Bank bezahlt: Soll {key('6000')} Raumaufwand, Haben {key('1020')} Bank. "
         "Der Aufwand steigt, das Bankguthaben sinkt.", "Beispiel"),
    PageBreak()]

# 2
story += [ChapterHead(2, "Installation und Start"),
    H("Debian und Ubuntu"),
    P("Das Paket bringt alles mit und legt einen Eintrag im Startmenü an. Installiere es mit <b>apt</b>, damit die "
      "benötigten Systembibliotheken mitkommen:"),
    Paragraph(f"sudo apt install ./dist/cipolle_{VERSION}_amd64.deb", command),
    H("macOS"),
    P(f"Cipolle kommt als Disk-Image <b>Cipolle-{VERSION}.dmg</b>. So installierst du es:"),
    bullets([f"Öffne <b>Cipolle-{VERSION}.dmg</b> mit einem Doppelklick. Es erscheint ein Fenster mit Cipolle links und "
             "dem Ordner <b>Applications</b> rechts.",
             "Ziehe Cipolle entlang des Pfeils auf den Ordner <b>Applications</b>.",
             f"Wirf das Laufwerk <b>Cipolle {VERSION}</b> im Finder aus. Die DMG-Datei brauchst du danach nicht mehr.",
             "Starte Cipolle aus dem Ordner <b>Programme</b> oder über Spotlight. Ein Doppelklick auf eine "
             ".cipolle-Datei öffnet sie direkt in Cipolle."], numbered=True),
    note("Die App ist nicht bei Apple notarisiert. Auf einem anderen Mac blockiert macOS deshalb den ersten Start. Du kannst ihn "
         "unter <b>Systemeinstellungen &gt; Datenschutz &amp; Sicherheit</b> mit <b>Trotzdem öffnen</b> erlauben.", "Hinweis für den Mac"),
    H("Der Start"),
    P("Beim Start zeigt Cipolle kurz einen Dialog mit Animation, Version und Autoren. Er schliesst sich von selbst, ein "
      "Klick oder eine Taste beendet ihn sofort. Danach öffnet Cipolle die zuletzt verwendete Datei. Hast du sie vorher mit "
      "<b>Datei &gt; Schliessen</b> geschlossen, beginnt das Programm auf der Startseite."),
    shot("start", "Die Startseite: hier beginnt jede neue Buchhaltung.", 125 * mm),
    PageBreak()]

# 3
story += [ChapterHead(3, "Erste Schritte"),
    P("Pro Geschäftsjahr gibt es eine eigene Datei mit der Endung <b>.cipolle</b>. So kommst du zu deiner ersten Buchhaltung:"),
    bullets(["Wähle <b>Datei &gt; Neu</b> oder auf der Startseite <b>Neue Buchhaltung…</b>",
             "Gib den Namen und das Geschäftsjahr an.",
             "Wähle den <b>KMU-Kontenplan (Schweiz)</b> oder einen leeren Kontenplan und bestätige mit <b>OK</b>.",
             "Lege fest, wo die Datei gespeichert wird.",
             "Trage im Reiter <b>Konten</b> in der Spalte <b>Eröffnung</b> die Anfangsbestände ein."], numbered=True),
    shot("neu", "Der Dialog für eine neue Buchhaltung.", 115 * mm),
    note("Trage auch Passivkonten als <b>positive</b> Beträge ein. Stimmen Aktiven und Passiven nicht überein, meldet die "
         "Statuszeile eine Differenz in der Eröffnungsbilanz."),
    H("Es gibt keinen Speichern-Befehl"),
    P("Jede Eingabe wird sofort in die Datei geschrieben. Du kannst das Programm also jederzeit schliessen. "
      "Kann Cipolle einmal nicht schreiben, etwa bei einer schreibgeschützten Datei, erscheint die Meldung "
      "<b>Nicht gespeichert</b> und das Eingabefeld bleibt offen."),
    PageBreak()]

# 4
story += [ChapterHead(4, "Konten und Gruppen"),
    P("Jedes Konto nennt in der Spalte <b>Summe in</b> seine Gruppe. Eine Gruppenzeile steht unter ihrem Inhalt, zeigt das "
      "Total und summiert über ihr eigenes <b>Summe in</b> in die nächsthöhere Gruppe. So entsteht eine Kette, "
      "zum Beispiel 1020 Bank → 100 Flüssige Mittel → 10 Umlaufvermögen → 1 Total Aktiven."),
    shot("konten", "Der Reiter Konten: Gruppen sind blau hinterlegt und tragen ihr Total."),
    H("Anlegen und ändern"),
    bullets(["<b>Konto anlegen:</b> In einer leeren Zeile die Nummer in der Spalte <b>Konto</b> eintragen.",
             "<b>Gruppe anlegen:</b> In einer leeren Zeile den Code in der Spalte <b>Gruppe</b> eintragen.",
             "<b>Gruppe bestimmen:</b> In einer eingefügten Zeile gehört der Eintrag zur Gruppe an dieser Stelle. In der Zeile "
             f"{key('*')} am Ende schlägt Cipolle die Gruppe des vorangehenden Kontos vor.",
             "<b>Reihenfolge:</b> Sie ergibt sich aus Nummern und Codes. Änderst du sie, rückt die Zeile sofort an ihren Platz."]),
    note("Konten mit Buchungen und Gruppen, in die noch etwas summiert, lassen sich nicht löschen. Enthält eine Gruppe "
         "Aktiv- und Passivkonten, erscheint eine Warnung.", "Gut zu wissen"),
    H("Der Jahreserfolg"),
    P("In Bilanz und Kontenplan steht der Jahreserfolg in der Gruppe, die unter <b>Datei &gt; Eigenschaften</b> gewählt ist. "
      "Im KMU-Kontenplan ist das 28 Eigenkapital. Ohne gewählte Gruppe steht er direkt vor Total Passiven."),
    PageBreak()]

# 5
story += [ChapterHead(5, "Buchungen erfassen"),
    P(f"Erfasse Buchungen im Reiter <b>Buchungen</b> in der Zeile mit dem {key('*')}. Enter oder Tab springt ins nächste Feld, "
      "eine neue Zeile übernimmt das Datum der vorherigen. Du musst die Hand also kaum von der Tastatur nehmen."),
    shot("buchungen", "Der Reiter Buchungen. Die rote Zeile ist noch unvollständig und zählt nicht in den Auswertungen."),
    grid([["Feld", "So gibst du es ein"],
          ["Datum", f"{key('31.12.2026')}, {key('31.12.26')}, {key('31.12')} oder {key('3112')}"],
          ["Soll, Haben", "Nummer, oder ein Teil von Nummer oder Bezeichnung, wenn er eindeutig ist"],
          ["Betrag", f"{key('1&#39;234.50')}, {key('1234,5')} oder {key('-50')} für eine Korrektur"]], [1, 3.4]),
    note(f"Trenne Tausender mit dem Apostroph. Ein Punkt ist immer das Dezimalzeichen, {key('1.000')} bedeutet also 1 Franken. "
         "Läuft dein Geschäftsjahr über den Jahreswechsel, gib das Jahr beim Datum immer mit an. "
         "Ohne Jahr nimmt Cipolle das Jahr, in dem das Geschäftsjahr beginnt.", "Zwei Stolperfallen"),
    H("Fehlerhafte Zeilen"),
    P("Fehlerhafte Zeilen werden rot, den Grund zeigt der Tooltip. Sie fehlen in den Auswertungen, und jeder Bericht weist "
      "darauf hin. Fehlen das Datum, beide Konten oder der Betrag, oder liegt das Datum ausserhalb des Geschäftsjahrs, zählt die Zeile nicht."),
    CondPageBreak(62 * mm),
    H("Sammelbuchungen"),
    P("Betrifft ein Vorgang mehr als zwei Konten, erfasse mehrere aufeinanderfolgende Zeilen mit nur Soll oder nur Haben. "
      "Ihre Summen müssen sich ausgleichen, sonst wird die letzte Zeile rot."),
    grid([["Beschreibung", "Soll", "Haben", "Betrag"],
          ["Rechnung Bürocenter", "", "1020 Bank", "1'000.00"],
          ["Anteil Büromaterial", "6500 Verwaltungsaufwand", "", "700.00"],
          ["Anteil Software", "6570 Informatikaufwand", "", "300.00"]], [3, 3.2, 2, 1.4]),
    Spacer(1, 4 * mm)]

# 6
story += [ChapterHead(6, "Tabellen bearbeiten"),
    P("Beide Tabellen haben Zeilennummern und funktionieren wie eine Tabellenkalkulation."),
    bullets(["<b>Markieren:</b> Ein Klick auf die Zeilennummer markiert die ganze Zeile, mit gedrückter Maustaste, Shift "
             "oder Ctrl auch mehrere.",
             "<b>Löschen:</b> Die Taste Entf löscht markierte Zeilen nach einer Rückfrage. Ist keine ganze Zeile markiert, leert "
             "sie die markierten Zellen. Pflichtfelder wie die Kontonummer bleiben dabei erhalten.",
             "<b>Kontextmenü:</b> Ein Rechtsklick auf Zeilennummer oder Zelle bietet <b>Zeile einfügen oben</b>, "
             "<b>Zeile einfügen unten</b> und <b>Zeile löschen</b>.",
             "<b>Sortieren:</b> <b>Bearbeiten &gt; Buchungen nach Datum sortieren</b> ordnet das Journal neu."]),
    H("Rückgängig und Wiederholen"),
    P(f"{key('Ctrl+Z')} nimmt die letzte Aktion zurück, {key('Ctrl+Y')} wiederholt sie. Das Menü <b>Bearbeiten</b> nennt die "
      "Aktion, und die Tabelle springt zur betroffenen Zeile. Eine Aktion mit mehreren Zeilen ist ein einziger Schritt. "
      "Der Verlauf liegt in der Datei, übersteht das Schliessen und umfasst die letzten 500 Schritte."),
    note("Während du in einem Feld tippst, wirkt Rückgängig nur auf dieses Feld. <b>Neues Jahr erstellen</b> und eingefügte "
         "leere Zeilen im Kontenplan lassen sich nicht zurücknehmen.", "Gut zu wissen"),
    ]

# 7
story += [PageBreak(), ChapterHead(7, "Auswertungen"),
    P("Die vier Berichte haben je einen eigenen Reiter und richten sich nach dem gewählten Zeitraum. "
      "Mit den Knöpfen oben rechts speicherst du sie als <b>PDF</b> oder <b>CSV</b> oder druckst sie aus."),
    grid([["Bericht", "Zeigt"],
          ["Kontoauszug", "Alle Bewegungen eines Kontos mit laufendem Saldo"],
          ["Bilanz", "Vermögen und Kapital an einem Stichtag, mit Gruppen und Zwischentotalen"],
          ["Erfolgsrechnung", "Ertrag, Aufwand und das Ergebnis eines Zeitraums"],
          ["Journal", "Alle gültigen Buchungen in zeitlicher Reihenfolge"]], [1, 3.4]),
    shot("bilanz", "Die Bilanz per Stichtag. Mit «Konten ohne Saldo zeigen» erscheinen auch leere Konten."),
    PageBreak(),
    shot("erfolg", "Die Erfolgsrechnung mit Gruppen und Ergebnis."),
    shot("auszug", "Der Kontoauszug mit laufendem Saldo."),
    note("Die Berichte sind verlinkt: Ein Klick auf die Kontonummer öffnet den Kontoauszug, ein Klick auf das Datum führt "
         "zur Buchung. Auch ein Doppelklick auf den Saldo im Reiter Konten öffnet den Kontoauszug."),
    PageBreak()]

# 8 und 9
story += [ChapterHead(8, "Jahreswechsel"),
    P("<b>Datei &gt; Neues Jahr erstellen</b> legt die Datei des Folgejahrs an, mit Kontenplan und Schlusssalden als Eröffnung. "
      "Der Jahreserfolg geht auf das gewählte Passivkonto, vorgeschlagen ist 2970 Gewinnvortrag."),
    P("Ändert sich das alte Jahr später noch, holt <b>Datei &gt; Eröffnung aus Vorjahr aktualisieren</b> die Saldi neu. Dabei "
      "werden alle Eröffnungssaldi des aktuellen Jahrs durch die Schlusssalden der gewählten Datei ersetzt."),
    note("Prüfe vor der Aktualisierung, ob das Vorjahr fehlerfrei ist. Rote Zeilen zählen nicht und fehlen deshalb auch in den "
         "Schlusssalden. Beim Erstellen des neuen Jahrs fragt Cipolle nach, beim Aktualisieren nicht.", "Achtung", BLUSH),
    Spacer(1, 3 * mm),
    ChapterHead(9, "Kontenplan austauschen"),
    P("<b>Datei &gt; Kontenplan exportieren</b> speichert Gruppen und Konten als JSON-Datei, ohne Eröffnungssaldi und Buchungen. "
      "So lässt sich ein bewährter Kontenplan in einer anderen Buchhaltung wiederverwenden."),
    P("<b>Datei &gt; Kontenplan importieren</b> prüft die Datei zuerst vollständig und zeigt, was sich ändert. Danach wählst du:"),
    grid([["Art", "Wirkung"],
          ["Zusammenführen", "Ergänzt und aktualisiert, ohne etwas zu entfernen"],
          ["Ersetzen", "Entfernt zusätzlich alles, was nicht in der Datei steht. Konten mit Buchungen und ihre Gruppen bleiben immer erhalten"]], [1, 3.4]),
    PageBreak()]

# 10 und 11
story += [ChapterHead(10, "Daten und Sicherheit"),
    P("Beim Öffnen legt Cipolle eine Kopie der Datei mit der Endung <b>.cipolle.bak</b> an und überschreibt dabei die "
      "vorherige Kopie. Dateien älterer Cipolle-Versionen werden beim Öffnen automatisch umgestellt und lassen sich "
      "danach mit diesen älteren Versionen nicht mehr öffnen."),
    note("Die .bak-Datei ersetzt keine echte Datensicherung. Sichere deine .cipolle-Dateien regelmässig an einem zweiten Ort, "
         "zum Beispiel auf einer externen Festplatte.", "Wichtig", BLUSH),
    H("Wenn etwas nicht stimmt"),
    P("Die Statuszeile unten rechts zeigt jederzeit, ob alles aufgeht. Diese Meldungen kommen am häufigsten vor:"),
    grid([["Meldung", "Bedeutung und Lösung"],
          ["Fehlerhafte Buchung fehlt in den Auswertungen", "Eine rote Zeile ist unvollständig. Der Tooltip nennt den Grund."],
          ["Differenz Soll/Haben", "Meist geht eine Sammelbuchung nicht auf. Suche im Reiter Buchungen nach roten Zeilen."],
          ["Differenz Eröffnungsbilanz", "Die Eröffnungssaldi von Aktiven und Passiven sind nicht gleich gross."],
          ["Gruppe enthält Aktiv- und Passivkonten", "Ein Konto steht in der falschen Gruppe. Prüfe die Spalte Summe in."],
          ["Nicht gespeichert", "Die Datei liess sich nicht schreiben. Prüfe Schreibrechte und freien Speicherplatz."]], [1.5, 3]),
    PageBreak(),
    ChapterHead(11, "Tastenkürzel"),
    grid([["Tastenkürzel", "Funktion"],
          [key("Ctrl+1") + " bis " + key("Ctrl+6"), "Reiter wechseln"],
          [key("Ctrl+W"), "Datei schliessen"],
          [key("Ctrl+Z"), "Rückgängig"],
          [key("Ctrl+Y") + " oder " + key("Ctrl+Shift+Z"), "Wiederholen"],
          [key("Ctrl+I"), "Zeile oben einfügen"],
          [key("Ctrl+Shift+I"), "Zeile unten einfügen"],
          [key("Entf"), "Zellen leeren oder markierte Zeilen löschen"],
          [key("Ctrl+Entf"), "Aktuelle oder markierte Zeilen löschen"]], [1.5, 2]),
    note("Auf macOS gilt in allen Tastenkürzeln <b>Command</b> anstelle von Ctrl, zum Beispiel Command+Z für Rückgängig. "
         "Die Taste Entf erreichst du auf Mac-Tastaturen ohne eigene Taste mit <b>Fn+Löschtaste</b>.", "Auf dem Mac"),
    Spacer(1, 2 * mm),
    Image(str(CRYING), width=WIDTH * 0.78, height=WIDTH * 0.78 * crying_size[1] / crying_size[0]),
    Spacer(1, 2 * mm),
    Paragraph("Viel Erfolg beim Buchen!", ParagraphStyle("end", parent=h2, fontSize=20, leading=26, alignment=TA_CENTER, textColor=RED)),
    Paragraph("Möge die Bilanz aufgehen und keine Träne fliessen.", ParagraphStyle("endsub", parent=body, alignment=TA_CENTER, textColor=MUTED, fontSize=12)),
]


def main() -> None:
    doc = Manual(str(TARGET), pagesize=A4, title="Cipolle – Anleitung", author="Cipolle", subject=f"Anleitung zu Cipolle {VERSION}",
                 creator="Cipolle", lang="de-CH")
    frame = Frame(MARGIN, 19 * mm, WIDTH, PAGE_H - 19 * mm - 18 * mm, id="main", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="cover", frames=[frame], onPage=cover), PageTemplate(id="body", frames=[frame], onPage=page)])
    doc.multiBuild(story)
    print(f"Fertig: {TARGET}")


if __name__ == "__main__":
    main()
