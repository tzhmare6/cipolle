#!/usr/bin/env bash
# Baut Cipolle als Mac-App: dist/Cipolle.app
# Aufruf: ./build-mac.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname)" != Darwin ]]; then
    echo "build-mac.sh läuft nur auf macOS." >&2
    exit 1
fi

work=build/pyinstaller-mac
version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' cipolle/__init__.py)
bundle_id=io.github.tzhmare6.cipolle

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet -e '.[build]'

rm -rf "$work"
mkdir -p "$work/cipolle.iconset"

# iconutil verlangt diese Namen. Die Variante 512x512@2x gibt es nicht, sie ist optional.
for entry in 16:16x16 32:16x16@2x 32:32x32 64:32x32@2x 128:128x128 256:128x128@2x 256:256x256 512:256x256@2x 512:512x512; do
    cp "cipolle/assets/icon_${entry%%:*}.png" "$work/cipolle.iconset/icon_${entry#*:}.png"
done
iconutil --convert icns --output "$work/cipolle.icns" "$work/cipolle.iconset"

# PyInstaller braucht ein Skript als Einstieg, __main__.py nutzt relative Importe.
cat > "$work/start.py" <<'PY'
import sys

from cipolle.__main__ import main

sys.exit(main())
PY

# Der Dateityp lässt sich nur über eine Spec-Datei in die Info.plist schreiben.
cat > "$work/cipolle.spec" <<SPEC
a = Analysis(
    ["start.py"],
    pathex=["$PWD"],
    datas=[("$PWD/cipolle/assets", "cipolle/assets")],
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Cipolle", console=False)
collected = COLLECT(exe, a.binaries, a.datas, name="Cipolle")
app = BUNDLE(
    collected,
    name="Cipolle.app",
    icon="cipolle.icns",
    bundle_identifier="$bundle_id",
    version="$version",
    info_plist={
        "CFBundleDisplayName": "Cipolle",
        "LSApplicationCategoryType": "public.app-category.finance",
        "NSHighResolutionCapable": True,
        "CFBundleDocumentTypes": [
            {
                "CFBundleTypeName": "Cipolle-Buchhaltung",
                "CFBundleTypeRole": "Editor",
                "CFBundleTypeIconFile": "cipolle.icns",
                "LSHandlerRank": "Owner",
                "LSItemContentTypes": ["$bundle_id.book"],
            }
        ],
        "UTExportedTypeDeclarations": [
            {
                "UTTypeIdentifier": "$bundle_id.book",
                "UTTypeDescription": "Cipolle-Buchhaltung",
                "UTTypeConformsTo": ["public.data"],
                "UTTypeIconFile": "cipolle.icns",
                "UTTypeTagSpecification": {"public.filename-extension": ["cipolle"]},
            }
        ],
    },
)
SPEC

.venv/bin/python -m PyInstaller \
    --noconfirm \
    --clean \
    --distpath dist \
    --workpath "$work/work" \
    "$work/cipolle.spec"

echo
echo "Fertig: $PWD/dist/Cipolle.app ($(du -sh dist/Cipolle.app | cut -f1))"
echo "Installieren: nach /Applications kopieren"
