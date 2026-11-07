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
mkdir -p "$work"

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
    icon="$PWD/cipolle/assets/cipolle.icns",
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
