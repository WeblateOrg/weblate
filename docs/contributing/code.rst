Weblate source code
===================

Weblate is developed on `GitHub <https://github.com/WeblateOrg/weblate>`_. You
are welcome to fork the code and open pull requests. Patches in any other form
are welcome too.

.. seealso::

    Check out :ref:`internals` to see how Weblate looks from inside.

.. include:: snippets/code-guide.rst

.. _acting-user-context:

Recording acting users
----------------------

Use ``acting_user_context(user)`` from ``weblate.utils.change_origin`` around
operations that change model settings outside an authenticated request. Request
authentication establishes this context automatically. Models read the actor
with ``get_acting_user()``; they no longer retain ``acting_user`` attributes.
Nested contexts restore the previous actor, and passing ``None`` explicitly
clears it. Use the anonymous user for intentional anonymous changes and the
appropriate bot for automated operations.

Continue passing an explicit user when recording history. The actor context
does not supply missing users to ``Change`` automatically and does not replace
permission checks or content authorship. Pending file writes retain their own
persisted actors and authors.

Wrap deferred transaction callbacks with ``capture_change_origin()`` when
registering them. This captures both the origin and actor before their scopes
exit. Celery tasks propagate the actor through a separate internal header;
only the user identifier is serialized. Origin metadata stored in history
does not include this identifier. Tasks with an invalid or deleted actor fail
without executing their body.

.. _atomic-repository-writes:

Writing repository files
------------------------

Create and update repository files atomically. Write the complete content to a
temporary file on the destination filesystem, then replace the destination only
after writing succeeds. Do not truncate repository files in place or copy over
an existing destination directly. Repository locks are still required to
coordinate concurrent operations; atomic replacement does not replace locking.

Use ``TranslationFormat.save_atomic(filename, callback)`` for file format
writers. The callback receives a binary file handle. In add-ons, use
``BaseAddon.write_repo_file(filename, content)`` with bytes or UTF-8 text. These
helpers select a temporary directory on the destination filesystem and clean up
temporary files when writing or replacement fails. Pass the repository temporary
directory to ``save_atomic()`` when it is available. The add-on helper preserves
existing file permissions, including executable bits, before replacement.

Direct external tools to temporary output, check that generation succeeded, and
install the completed content using an atomic helper. Keep path validation and
repository locking around these operations. Atomic replacement applies to each
file separately; these helpers do not provide transactions across multiple
files or guarantee durability through power loss.
