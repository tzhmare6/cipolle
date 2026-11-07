#!/usr/bin/env bash
# Packt dist/Cipolle.app in ein Disk-Image: dist/Cipolle-<version>.dmg
# Aufruf: ./build-dmg.sh
# Im Image liegt neben der App ein Verweis auf /Applications zum Hineinziehen.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname)" != Darwin ]]; then
    echo "build-dmg.sh läuft nur auf macOS." >&2
    exit 1
fi

app=dist/Cipolle.app
plist="$app/Contents/Info.plist"

# Die App neu bauen, wenn sie fehlt oder der Code neuer ist.
if [[ ! -f "$plist" ]] || [[ -n "$(find cipolle pyproject.toml build-mac.sh -type f -newer "$plist" -not -path '*/__pycache__/*' -print -quit)" ]]; then
    ./build-mac.sh
fi

version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' cipolle/__init__.py)
staging=build/dmg
image="dist/Cipolle-${version}.dmg"

rm -rf "$staging"
mkdir -p "$staging"
# ditto erhält Symlinks, Rechte und die Signatur der App.
ditto "$app" "$staging/Cipolle.app"
ln -s /Applications "$staging/Applications"

rm -f "$image"
hdiutil create \
    -volname "Cipolle $version" \
    -srcfolder "$staging" \
    -fs HFS+ \
    -format UDZO \
    -imagekey zlib-level=9 \
    "$image" >/dev/null

echo
echo "Fertig: $PWD/$image ($(du -h "$image" | cut -f1))"
echo "Installieren: Image öffnen und Cipolle auf «Applications» ziehen"
