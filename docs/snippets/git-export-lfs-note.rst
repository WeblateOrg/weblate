.. note::

   Weblate serves the Git repository itself, but it does not serve Git LFS
   objects. For repositories using Git LFS, clone from the upstream repository
   and add Weblate as another remote. If you only need Git-tracked files, you
   can clone from Weblate with ``GIT_LFS_SKIP_SMUDGE=1`` to skip downloading
   Git LFS objects.
