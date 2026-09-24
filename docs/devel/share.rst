.. _promotion:

Building the translation community
==================================

Weblate provides you content to share on your website or other channels to
promote your translation project. A nice welcome page called Engage is available to attract
new contributors and provide them basic information about the translation. Additionally, you can
share information about the efforts using social networks. All these
possibilities can be found on the :guilabel:`Community` tab:

.. image:: /screenshots/promote.webp

All these badges are provided with a link to simple page which explains users
how to translate using Weblate:

.. image:: /screenshots/engage.webp

Status widgets also support categories, including nested categories. Use
``/widget/<project>/<category>/svg-badge.svg`` for a category's overall progress,
or ``/widget/<project>/<category>/-/<language>/svg-badge.svg`` for its progress
in one language. For nested categories, include each parent category in the path.
Widgets follow the project's :ref:`public sharing setting <project-public_sharing>`.

Workspace widgets use ``/widget/-/workspace/<workspace-id>/svg-badge.svg`` and
follow the workspace's access checks. They show the same aggregate statistics as
the workspace page. A project's public sharing setting does not grant access to
its workspace widgets.

.. seealso::

   :setting:`ENABLE_SHARING`
