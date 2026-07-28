Installing on Debian and Ubuntu
===============================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   apt install -y \
      libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev \
      libffi-dev \
      libacl1-dev liblz4-dev libzstd-dev libxxhash-dev libssl-dev libpq-dev libjpeg-dev build-essential \
      python3-gdbm python3-dev git

.. include:: steps/install-system-optional.rst

.. code-block:: sh

   apt install -y \
      libldap2-dev libldap-common libsasl2-dev \
      libxmlsec1-dev

.. include:: steps/install-system-server.rst

.. code-block:: sh

    # Web server option 1: NGINX and uWSGI
    apt install -y nginx uwsgi uwsgi-plugin-python3

    # Web server option 2: Apache with ``mod_wsgi``
    apt install -y apache2 libapache2-mod-wsgi-py3

    # Caching backend: Valkey
    apt install -y valkey-server

    # Database server: PostgreSQL
    apt install -y postgresql postgresql-contrib

    # SMTP server
    apt install -y exim4

    # Gettext tools for gettext POT/PO update add-ons
    apt install -y gettext

.. include:: steps/install-uv.rst

.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
