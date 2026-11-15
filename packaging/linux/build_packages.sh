#!/usr/bin/env bash
# Build the Debian and RPM installers from a PyInstaller one-file binary.
#
# Usage: build_packages.sh <version> <pyinstaller-binary> <output-dir>
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 <version> <pyinstaller-binary> <output-dir>" >&2
  exit 2
fi

version=$1
binary=$2
outdir=$3
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
workdir=$(mktemp -d)
trap 'rm -rf "$workdir"' EXIT

mkdir -p "$outdir"
architecture=$(dpkg --print-architecture)

# --- Debian package ---------------------------------------------------------
debroot="$workdir/deb"
install -Dm755 "$binary" "$debroot/usr/bin/image-manipulator"
install -Dm644 "$repo_root/packaging/linux/image-manipulator.desktop" \
  "$debroot/usr/share/applications/image-manipulator.desktop"
install -Dm644 "$repo_root/packaging/linux/image-manipulator.png" \
  "$debroot/usr/share/icons/hicolor/256x256/apps/image-manipulator.png"

mkdir -p "$debroot/DEBIAN"
installed_size=$(du -sk "$debroot" | cut -f1)
cat > "$debroot/DEBIAN/control" <<EOF
Package: image-manipulator
Version: $version
Section: graphics
Priority: optional
Architecture: $architecture
Maintainer: Pavlenko Evgeniy <pavlenkoevgeniy85@gmail.com>
Installed-Size: $installed_size
Depends: libc6
Description: Resize images and overlay text in a single pass
 Image Manipulator resizes images and draws text on the result in one
 pass. It is a self-contained PyInstaller build.
EOF
chmod 0644 "$debroot/DEBIAN/control"
dpkg-deb --build --root-owner-group "$debroot" \
  "$outdir/ImageManipulator-$version-linux-$architecture.deb"

# --- RPM package ------------------------------------------------------------
topdir="$workdir/rpm"
mkdir -p "$topdir/BUILD" "$topdir/RPMS" "$topdir/SOURCES" \
  "$topdir/SPECS" "$topdir/SRPMS"
cp "$binary" "$topdir/SOURCES/ImageManipulator"
cp "$repo_root/packaging/linux/image-manipulator.desktop" "$topdir/SOURCES/"
cp "$repo_root/packaging/linux/image-manipulator.png" "$topdir/SOURCES/"
sed "s/@VERSION@/$version/g" "$repo_root/packaging/linux/image-manipulator.spec" \
  > "$topdir/SPECS/image-manipulator.spec"
rpmbuild --define "_topdir $topdir" -bb "$topdir/SPECS/image-manipulator.spec"

rpm_path=$(find "$topdir/RPMS" -name '*.rpm' -print -quit)
cp "$rpm_path" "$outdir/ImageManipulator-$version-linux-$(uname -m).rpm"

echo "Packages written to $outdir:"
ls -1 "$outdir"
