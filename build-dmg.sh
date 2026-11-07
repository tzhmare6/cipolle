#!/usr/bin/env bash
# Packt dist/Cipolle.app in ein Disk-Image: dist/Cipolle-<version>.dmg
# Aufruf: ./build-dmg.sh
# Das Fenster zeigt links die App, rechts den Verweis auf /Applications und
# dazwischen einen Pfeil. Hintergrund: packaging/dmg-background.tiff
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname)" != Darwin ]]; then
    echo "build-dmg.sh läuft nur auf macOS." >&2
    exit 1
fi

app=dist/Cipolle.app
plist="$app/Contents/Info.plist"
icon=cipolle/assets/cipolle.icns

# Die App neu bauen, wenn sie fehlt oder der Code neuer ist.
if [[ ! -f "$plist" ]] || [[ -n "$(find cipolle pyproject.toml build-mac.sh -type f -newer "$plist" -not -path '*/__pycache__/*' -print -quit)" ]]; then
    ./build-mac.sh
fi

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet -e '.[build]'

version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' cipolle/__init__.py)
work=build/dmg
image="dist/Cipolle-${version}.dmg"

rm -rf "$work"
mkdir -p "$work"

# dmgbuild schreibt das Fensterlayout direkt, ohne den Finder fernzusteuern.
# Die Positionen sind die Mitten der Symbole und passen zu packaging/make_dmg_background.py.
cat > "$work/settings.py" <<SETTINGS
files = ["$PWD/$app"]
symlinks = {"Applications": "/Applications"}
icon = "$PWD/$icon"
background = "$PWD/packaging/dmg-background.tiff"
format = "UDZO"
compression_level = 9
filesystem = "HFS+"
window_rect = ((200, 140), (640, 450))
default_view = "icon-view"
show_status_bar = False
show_tab_view = False
show_toolbar = False
show_pathbar = False
show_sidebar = False
icon_size = 128
text_size = 13
icon_locations = {"Cipolle.app": (160, 185), "Applications": (480, 185)}
hide_extensions = ["Cipolle.app"]
SETTINGS

rm -f "$image"
.venv/bin/python -m dmgbuild -s "$work/settings.py" "Cipolle $version" "$image"

# Auch die DMG-Datei selbst bekommt das Cipolle-Icon. Es steckt in einem erweiterten
# Attribut und geht verloren, wenn die Datei über einen Webserver verteilt wird.
osascript -l JavaScript - "$PWD/$icon" "$PWD/$image" >/dev/null <<'JS'
ObjC.import("AppKit")
function run(argv) {
    const picture = $.NSImage.alloc.initWithContentsOfFile(argv[0])
    return $.NSWorkspace.sharedWorkspace.setIconForFileOptions(picture, argv[1], 0)
}
JS

echo
echo "Fertig: $PWD/$image ($(du -h "$image" | cut -f1))"
echo "Installieren: Image öffnen und Cipolle auf «Applications» ziehen"
