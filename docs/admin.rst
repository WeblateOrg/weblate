Administration
==============

Administration of Weblate is done through standard Django admin interface,
which is available under :file:`/admin/` URL.

Adding new resources
--------------------

All translation resources need to be available as Git repositories and are
organized as project/subproject structure.

Project
-------

To add new resource to translate, you need to create translation project first.
The project is sort of shelf, in which real translations are folded. All
subprojects in same project share suggestions and dictionary, also the
translations are automatically propagated through the all subproject in single
project.

Subproject
----------

Subproject is real resource for translating. You enter Git repository location
and file mask which files to translate and Weblate automatically fetches the Git
and finds all translated files.

.. note::
   
    As setup of translation project includes fetching Git repositories, you
    might want to preseed these, repos are stored in path defined by
    :envvar:`GIT_ROOT` in :file:`settings.py` in :file:`<project>/<subproject>`
    directories.

Interacting with others
-----------------------

You can trigger update of underlaying git repository for every subproject by
accessing URL :file:`/hooks/project/subproject/update/`. This can be used for
example as as Post-Receive URLs on Github.
