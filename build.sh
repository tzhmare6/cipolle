#!/usr/bin/env bash
# Baut Cipolle als eine einzige ausführbare Datei: dist/cipolle
# Aufruf: ./build.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

work=build/pyinstaller

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet -e '.[build]'

# PyInstaller braucht ein Skript als Einstieg, __main__.py nutzt relative Importe.
mkdir -p "$work"
cat > "$work/start.py" <<'PY'
import sys

from cipolle.__main__ import main

sys.exit(main())
PY

.venv/bin/python -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --name cipolle \
    --distpath dist \
    --workpath "$work" \
    --specpath "$work" \
    --paths "$PWD" \
    --add-data "$PWD/cipolle/assets:cipolle/assets" \
    "$work/start.py"

echo
echo "Fertig: $PWD/dist/cipolle ($(du -h dist/cipolle | cut -f1))"
