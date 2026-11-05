#!/usr/bin/env bash
# Baut aus dist/cipolle ein Debian-Paket: dist/cipolle_<version>_<architektur>.deb
# Aufruf: ./build-deb.sh
# Installieren: sudo apt install ./dist/cipolle_<version>_<architektur>.deb
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Das Binary neu bauen, wenn es fehlt oder der Code neuer ist.
if [[ ! -x dist/cipolle ]] || [[ -n "$(find cipolle pyproject.toml -type f -newer dist/cipolle -not -path '*/__pycache__/*' -print -quit)" ]]; then
    ./build.sh
fi

version=$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' cipolle/__init__.py)
arch=$(dpkg --print-architecture)
# Das Binary enthält Bibliotheken dieses Systems und braucht darum mindestens dessen glibc.
glibc=$(dpkg-query -W -f='${Version}' libc6 | cut -d- -f1)
root=build/deb/cipolle
package="dist/cipolle_${version}_${arch}.deb"

rm -rf "$root"
install -d -m 755 "$root/DEBIAN" "$root/usr/bin" "$root/usr/share/applications" "$root/usr/share/mime/packages"

# Nicht strippen: PyInstaller hängt sein Archiv ans Binary an.
install -m 755 dist/cipolle "$root/usr/bin/cipolle"

for size in 16 24 32 48 64 128 256 512; do
    folder="$root/usr/share/icons/hicolor/${size}x${size}/apps"
    install -d -m 755 "$folder"
    install -m 644 "cipolle/assets/icon_${size}.png" "$folder/cipolle.png"
done

cat > "$root/usr/share/applications/cipolle.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Cipolle
GenericName=Buchhaltung
Comment=Lokale doppelte Buchhaltung
Exec=cipolle %f
Icon=cipolle
Terminal=false
Categories=Office;Finance;
Keywords=Buchhaltung;Bilanz;Erfolgsrechnung;Finanzen;
MimeType=application/x-cipolle;
StartupWMClass=Cipolle
DESKTOP
chmod 644 "$root/usr/share/applications/cipolle.desktop"

cat > "$root/usr/share/mime/packages/cipolle.xml" <<'MIME'
<?xml version="1.0" encoding="UTF-8"?>
<mime-info xmlns="http://www.freedesktop.org/standards/shared-mime-info">
  <mime-type type="application/x-cipolle">
    <comment>Cipolle-Buchhaltung</comment>
    <sub-class-of type="application/vnd.sqlite3"/>
    <icon name="cipolle"/>
    <glob pattern="*.cipolle" weight="80"/>
  </mime-type>
</mime-info>
MIME
chmod 644 "$root/usr/share/mime/packages/cipolle.xml"

# Qt und alle übrigen Bibliotheken stecken im Binary. Diese hier lässt PyInstaller
# bewusst weg, weil sie zum Grafiktreiber und zum System passen müssen.
size=$(du -sk --exclude=DEBIAN "$root" | cut -f1)
cat > "$root/DEBIAN/control" <<CONTROL
Package: cipolle
Version: $version
Architecture: $arch
Maintainer: Remo Maurer <tzhmare6@users.noreply.github.com>
Installed-Size: $size
Depends: libc6 (>= $glibc), libdrm2, libegl1, libgl1, libwayland-client0, libwayland-cursor0, libwayland-egl1, libxcb1
Section: misc
Priority: optional
Homepage: https://github.com/tzhmare6/cipolle
Description: Lokale doppelte Buchhaltung für den Desktop
 Cipolle führt eine einfache doppelte Buchhaltung ohne MWST, ohne Abo und
 ohne Cloud. Alle Daten bleiben auf diesem Rechner.
CONTROL

# Icon-Cache, Menü und Dateitypen aktualisieren die dpkg-Trigger der jeweiligen Pakete.
dpkg-deb --root-owner-group --build "$root" "$package"

echo
echo "Fertig: $PWD/$package ($(du -h "$package" | cut -f1))"
echo "Installieren: sudo apt install $PWD/$package"
