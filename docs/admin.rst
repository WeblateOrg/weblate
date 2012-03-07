Administration
==============

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.

Adding new resources
--------------------

All translation resources need to be available as Git repositories. As setup of
translation project includes fetching Git repositories, you might want to
preseed these, repos are stored in path defined by :envvar:`GIT_ROOT` in
:file:`settings.py` in :file:`<project>/<subproject>` directories.
