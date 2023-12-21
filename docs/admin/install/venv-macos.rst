Installing on macOS
===================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   # Workaround for https://github.com/xmlsec/python-xmlsec/issues/254
   wget -O /tmp/libxmlsec1.rb https://raw.githubusercontent.com/Homebrew/homebrew-core/7f35e6ede954326a10949891af2dba47bbe1fc17/Formula/libxmlsec1.rb
   brew install --formula /tmp/libxmlsec1.rb
   brew pin libxmlsec1

   brew install python pango cairo gobject-introspection glib libyaml pkg-config zstd xxhash
   pip install virtualenv

.. note::

   Using older libxmlsec is needed until https://github.com/xmlsec/python-xmlsec/issues/254 is addressed.

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    brew install nginx uwsgi

    # Web server option 2: Apache with ``mod_wsgi``
    brew install httpd

    # Caching backend: Redis
    brew install redis

    # Database server: PostgreSQL
    brew install postgresql

    # Gettext for the msgmerge add-on
    brew install gettext

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
