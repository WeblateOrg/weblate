Installing on Debian and Ubuntu
===============================

.. include:: steps/hw.rst

.. include:: steps/install-system-devel.rst

.. code-block:: sh

   apt install -y \
      libxml2-dev libxslt-dev libfreetype6-dev libjpeg-dev libz-dev libyaml-dev \
      libffi-dev libcairo-dev gir1.2-pango-1.0 gir1.2-rsvg-2.0 libgirepository1.0-dev \
      libacl1-dev liblz4-dev libzstd-dev libxxhash-dev libssl-dev libpq-dev libjpeg-dev build-essential \
      python3-gdbm python3-dev python3-pip python3-virtualenv virtualenv git

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

    # Caching backend: Redis
    apt install -y redis-server

    # Database server: PostgreSQL
    apt install -y postgresql postgresql-contrib

    # SMTP server
    apt install -y exim4

    # Gettext for the msgmerge add-on
    apt install -y gettext


.. include:: steps/install-python.rst

.. include:: steps/install-configure.rst

.. include:: steps/install-after.rst
