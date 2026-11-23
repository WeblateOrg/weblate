Installing on Kubernetes
========================

The Kubernetes Helm chart runs the :doc:`Weblate Docker container <docker>` as
a single pod that serves the web interface and runs the Celery workers. It can
also deploy PostgreSQL and Redis for you.

The chart is developed in the `Weblate Helm repository
<https://github.com/WeblateOrg/helm/>`_ and published on `Artifact Hub
<https://artifacthub.io/packages/helm/weblate/weblate>`_.

.. note::

   This guide uses features added in Weblate 2026.12.

Installation
------------

.. code-block:: shell

   helm repo add weblate https://helm.weblate.org
   helm install my-release weblate/weblate

For anything beyond a quick test, keep your settings in a values file and pass
it to Helm:

.. code-block:: yaml

   siteDomain: weblate.example.com
   adminEmail: admin@example.com
   ingress:
     enabled: true
     hosts:
       - host: weblate.example.com
         paths:
           - path: /
             pathType: Prefix

.. code-block:: shell

   helm install my-release weblate/weblate --values values.yaml

The chart's :file:`values.yaml` lists all available options. If the ingress
terminates HTTPS, also set :envvar:`WEBLATE_ENABLE_HTTPS`, see
:ref:`docker-ssl-proxy`.

Once the pod is running, sign in as ``admin``. Unless you set
``adminPassword``, a random password is printed in the log, see
:ref:`docker-admin-login`:

.. code-block:: shell

   kubectl logs deployment/my-release-weblate

Configuration
-------------

The chart configures the container through :ref:`docker-environment`. The most
common ones have their own values, such as ``siteDomain`` or ``emailHost``.
Use ``extraConfig`` to set any other environment variable, and
``extraSecretConfig`` for values that should be stored in a Kubernetes Secret:

.. code-block:: yaml

   extraConfig:
     WEBLATE_ENABLE_HTTPS: "1"
     WEBLATE_REGISTRATION_OPEN: "0"
   extraSecretConfig:
     WEBLATE_GITHUB_TOKEN: "..."

To keep credentials out of the values file, create the Secret yourself and
reference it with ``externalSecretName``; all its keys are passed to the
container as environment variables.

For settings that are not available as environment variables, the
``configOverride`` value is mounted as :ref:`docker-settings-override`.

Database and datastore
----------------------

The bundled PostgreSQL and Redis are convenient for testing. In production,
it is usually better to use the database and datastore that your cluster
already provides, so they are backed up and upgraded together with your other
services:

.. code-block:: yaml

   postgresql:
     enabled: false
     postgresqlHost: postgresql.example.com
     auth:
       userName: weblate
       postgresPassword: "..."
       database: weblate
   redis:
     enabled: false
     redisHost: redis.example.com
     auth:
       password: "..."

Despite its name, ``postgresql.auth.postgresPassword`` is the password of
``userName``. To keep the passwords out of the values file, set
``postgresql.auth.existingSecret`` and ``redis.auth.existingSecret`` to Secrets
holding them.

.. seealso::

   :ref:`database-setup`

Secret key
----------

Weblate generates its :setting:`SECRET_KEY` on first start and stores it in the
data volume. Store it in a Kubernetes Secret instead, so a new data volume does
not log everybody out or invalidate links in sent emails:

.. code-block:: shell

   openssl rand -base64 48 > secret-key
   kubectl create secret generic weblate-env \
      --from-file=WEBLATE_SECRET_KEY=secret-key

To keep the key of an existing installation, copy it from the data volume
instead of generating a new one:

.. code-block:: shell

   kubectl exec deployment/my-release-weblate -- cat /app/data/secret > secret-key

Then pass the Secret to the container, see :envvar:`WEBLATE_SECRET_KEY`:

.. code-block:: yaml

   externalSecretName: weblate-env

.. _kubernetes-data-volume:

Data volume
-----------

The pod keeps :setting:`DATA_DIR` in a persistent volume claim mounted as
:file:`/app/data`, see :ref:`docker-volume`. Most of what Weblate stores there
can live elsewhere or be rebuilt, so the volume doesn't have to be backed up:

* Translations are stored in the database.
* Git repository checkouts in :file:`vcs` can be rebuilt from the upstream
  repositories and the database, see :ref:`kubernetes-recovery`.
* Screenshots and fonts can be stored in object storage, see
  :envvar:`WEBLATE_MEDIA_STORAGE_BACKEND` and
  :envvar:`WEBLATE_FONTS_STORAGE_BACKEND`.
* The secret key can come from a Kubernetes Secret, see above.
* The SSH key can come from a Kubernetes Secret, see :ref:`kubernetes-ssh`.
* Caches are kept in :file:`/app/cache` and recreated on startup.

Anything else you placed in the volume yourself, such as SAML certificates, a
GPG key for signing commits, custom CA certificates, or Python customization,
has to be provided another way or backed up.

With this setup, you can use fast node-local storage for the data volume and
treat its loss as something to recover from, not as data loss. Select it with
the ``persistence.storageClass`` value.

The volume uses the ``ReadWriteOnce`` access mode and the chart runs a single
pod, replacing it on upgrades (the ``Recreate`` update strategy).

.. note::

   With ``persistence.enabled: false``, the data volume is an ``emptyDir`` and
   is lost whenever the pod is replaced, including on every upgrade. Keep
   persistence enabled unless you have a specific reason not to.

.. _kubernetes-recovery:

Recovering a lost data volume
-----------------------------

When the data volume is lost, repository operations of components with a
missing checkout fail, and with :ref:`component-auto_lock_error` they get
locked. :wladmin:`recovergit` rebuilds the checkouts by queuing
:ref:`manage-vcs-reset-reapply` for every Git component with a missing
checkout. Translations that were not pushed yet are committed again on top of
the upstream repository, with new commit dates. If a file can't be recreated,
recovery reports an error and the file has to be restored from a backup; the
translations are kept in the database.

To recover automatically whenever the pod starts, set
:envvar:`WEBLATE_RECOVER_GIT`:

.. code-block:: yaml

   extraConfig:
     WEBLATE_RECOVER_GIT: "1"

Components with an existing checkout are skipped, so this is safe to keep
enabled. You can also run the recovery manually:

.. code-block:: shell

   kubectl exec deployment/my-release-weblate -- weblate recovergit --all

If the node holding a node-local volume is gone, the pod can't start
elsewhere until the claim is replaced. Delete the claim and the pod, then let
Helm create a new claim:

.. code-block:: shell

   kubectl delete pvc my-release-weblate --wait=false
   kubectl delete pod -l app.kubernetes.io/name=weblate,app.kubernetes.io/instance=my-release
   helm upgrade my-release weblate/weblate --values values.yaml

.. warning::

   Do not change the repository settings of affected components before the
   checkouts are recovered. Saving them clones the repository again, and
   translations that were not pushed yet are not reapplied.

.. _kubernetes-ssh:

SSH keys
--------

Weblate uses the SSH key and known host keys from :file:`/app/data/ssh`, see
:ref:`weblate-ssh-key`. If you don't provide them, a lost data volume means a
new key that your code hosting site doesn't know.

You can avoid SSH completely by using HTTPS repository URLs with credentials
stored in Weblate, such as the :ref:`GitHub App
<code-hosting-github-app-register>`.

Otherwise, store the key pair and :file:`known_hosts` in a Kubernetes Secret:

.. code-block:: shell

   kubectl create secret generic weblate-ssh \
      --from-file=id_ed25519 \
      --from-file=id_ed25519.pub \
      --from-file=known_hosts

If your code hosting site uses the RSA key, add :file:`id_rsa` and
:file:`id_rsa.pub` the same way.

Copy them into the data volume with an init container, so the files are owned
by Weblate and have the permissions SSH requires:

.. code-block:: yaml

   extraVolumes:
     - name: ssh-key
       secret:
         secretName: weblate-ssh
   initContainers:
     - name: ssh-key
       image: busybox:1.37
       securityContext:
         runAsUser: 1000
       command:
         - sh
         - -c
         - >-
           mkdir -p /app/data/ssh &&
           install -m 600 /ssh-key/id_ed25519 /app/data/ssh/id_ed25519 &&
           install -m 644 /ssh-key/id_ed25519.pub /app/data/ssh/id_ed25519.pub &&
           install -m 644 /ssh-key/known_hosts /app/data/ssh/known_hosts
       volumeMounts:
         - name: weblate-data
           mountPath: /app/data
         - name: ssh-key
           mountPath: /ssh-key
           readOnly: true

The known host keys are replaced on every start, so add new hosts to the
Secret; host keys added in Weblate are lost on the next restart.

Backups
-------

With the data volume set up as described above, the data worth backing up is
the database and your upstream repositories. Back up PostgreSQL with the tools
your cluster provides, for example your PostgreSQL operator.

The database dumps of :ref:`automated-backup` and a local Borg repository are
written to the data volume, and so are :ref:`projectbackup`. Use a remote Borg
repository if you rely on the automated backups. If the database is backed up
separately, you can disable the daily database dump with
:envvar:`WEBLATE_DATABASE_BACKUP` set to ``none``.

Upgrading
---------

Change the image tag or chart version in your values file and upgrade:

.. code-block:: shell

   helm repo update
   helm upgrade my-release weblate/weblate --values values.yaml

The container applies database migrations on startup. Because the pod is
replaced, Weblate is unavailable for the duration of the startup. When using
the bundled PostgreSQL, check the chart release notes, as a new major
PostgreSQL version needs its data migrated.

.. seealso::

   :ref:`upgrading-docker`

.. _kubernetes-scaling:

Scaling
-------

The chart runs all services in one pod. Give it more resources with the
``resources`` value before considering more pods.

The chart can't split the services between pods. Running more pods requires
your own deployments using :envvar:`WEBLATE_SERVICE` and a :file:`/app/data`
volume shared by all of them, see :ref:`docker-scaling`. Network file systems
can make Git operations considerably slower, so test the performance of your
storage first.

Troubleshooting
---------------

Startup takes several minutes
   The first start runs database migrations and collects static files. The
   chart's liveness probe waits five minutes before checking, increase
   ``livenessProbe.initialDelaySeconds`` if your startup takes longer.

``UNPROTECTED PRIVATE KEY FILE`` when accessing repositories
   When mounting the data volume, Kubernetes can give the pod's ``fsGroup``
   write access to all files in it, and SSH refuses such a private key. Limit
   this to volumes whose root directory doesn't match:

   .. code-block:: yaml

      podSecurityContext:
        fsGroupChangePolicy: OnRootMismatch

   To fix existing files, run once:

   .. code-block:: shell

      kubectl exec deployment/my-release-weblate -- \
         chmod 600 /app/data/ssh/id_rsa /app/data/ssh/id_ed25519
