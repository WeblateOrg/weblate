echo 'installing dependencies with brew'
brew install --env=std cairo gobject-introspection libffi glib

LIBFFI_PATH=$(brew list libffi | grep libffi.pc | sed s/libffi.pc//g)
echo LIBFFI_PATH: $LIBFFI_PATH
export PKG_CONFIG_PATH=/usr/local/opt/zlib/lib/pkgconfig:$LIBFFI_PATH
echo PKG_CONFIG_PATH: $PKG_CONFIG_PATH

pip install -r requirements.txt --no-binary pygobject
