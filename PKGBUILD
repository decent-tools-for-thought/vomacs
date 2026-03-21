pkgname=vomacsd
pkgver=0.1.4
pkgrel=1
pkgdesc="Hookable voice transcription daemon for KDE Wayland"
arch=('any')
url='https://github.com/decent-tools-for-thought/vomacs'
license=('custom:unlicensed')
depends=('python' 'ffmpeg' 'python-websocket-client' 'libnotify')
makedepends=('python-build' 'python-installer' 'python-setuptools' 'python-wheel' 'rsync')
optdepends=('xclip: X11 clipboard fallback backend')
install="$pkgname.install"
source=()
sha256sums=()

prepare() {
  local builddir="$srcdir/$pkgname-$pkgver"
  rm -rf "$builddir"
  mkdir -p "$builddir"
  rsync -a \
    --delete \
    --exclude '.git/' \
    --exclude '.conda/' \
    --exclude 'dist/' \
    --exclude 'build/' \
    --exclude '__pycache__/' \
    --exclude '*.egg-info/' \
    --exclude 'token.txt' \
    "$startdir"/ "$builddir"/
}

build() {
  cd "$srcdir/$pkgname-$pkgver"
  python -m build --wheel --no-isolation
}

package() {
  cd "$srcdir/$pkgname-$pkgver"
  python -m installer --destdir="$pkgdir" dist/*.whl

  install -Dm644 contrib/vomacsd.service \
    "$pkgdir/usr/lib/systemd/user/vomacsd.service"
  install -Dm644 contrib/vomacsd-kde-helper.service \
    "$pkgdir/usr/lib/systemd/user/vomacsd-kde-helper.service"
  install -Dm644 README.md \
    "$pkgdir/usr/share/doc/$pkgname/README.md"
}
