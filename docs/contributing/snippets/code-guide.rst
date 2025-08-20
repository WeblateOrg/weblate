
License and copyright
---------------------

When contributing code, you agree to put your changes and new code under the
same license as the repository is already using, unless stated and agreed
otherwise.

.. seealso::

   :doc:`/contributing/license` explains licensing in more details.

Writing a good patch
--------------------

Write separate changes
~~~~~~~~~~~~~~~~~~~~~~

It is annoying when you get a massive patch that is said to fix 11 odd
problems, but discussions and opinions do not agree with 10 of them or 9 of
them were already fixed differently. Then the person merging this change needs
to extract the single interesting patch from somewhere within the massive pile
of sources, and that creates a lot of extra work.

Preferably, each fix that addresses an issue should be in its own patch/commit
with its own description/commit message stating exactly what they correct so
that all changes can be selectively applied by the maintainer or other
interested parties.

Furthermore, separate changes enable bisecting much better for tracking issues
and regression in the future.

Documentation
~~~~~~~~~~~~~

Documentation can be a tedious task; however, it is necessary for someone to
complete it. It makes things a lot easier if you submit the documentation
together with code changes. Please remember to document methods, complex code
blocks, or user-visible features.

.. seealso::

   :doc:`/contributing/documentation`


Test cases
~~~~~~~~~~

The tests allow us to quickly verify that the features are working as they are
supposed to. To maintain this situation and improve it, all new features and
functions that are added need to be tested in the test suite. Every feature
that is added should get at least one valid test case that verifies that it
works as documented.

.. seealso::

   :doc:`/contributing/tests`

Commit messages
~~~~~~~~~~~~~~~

Git commits should follow `Conventional Commits
<https://www.conventionalcommits.org/>`_ specification.

Type checking
~~~~~~~~~~~~~

Any new code should utilize :pep:`484` type hints. We are using :program:`mypy`
to check (because it has a Django plugin that makes type checking of Django
apps doable).

The code base is not yet completely covered by type annotations, but some
modules are already enforced for type checking in the CI.

Coding standard and linting the code
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The code should follow :pep:`8` coding guidelines and should be formatted using
:program:`ruff` code formatter.

To check the code quality, you can use :program:`ruff`, its configuration is
stored in :file:`pyproject.toml`.

The easiest approach to enforce all this is to install `pre-commit`_. The
repository contains configuration for it to verify the committed files are sane.
After installing it (it is already included in the
:file:`pyproject.toml`) turn it on by running ``pre-commit install`` in
Weblate checkout. This way all your changes will be automatically checked.

You can also trigger check manually, to check all files run:

.. code-block:: sh

    pre-commit run --all

.. _pre-commit: https://pre-commit.com/

Coding securely
~~~~~~~~~~~~~~~

Any code for Weblate should be written with `Security by Design Principles`_ in
mind.

.. _Security by Design Principles: https://wiki.owasp.org/index.php/Security_by_Design_Principles

AI guidelines
-------------

When contributing content to the project, you give us permission to use it
as-is, and you must make sure you are allowed to distribute it to us. By
submitting a change to us, you agree that the changes can and should be adopted
by the project and get redistributed under the project license. Authors should
be explicitly aware that the burden is on them to ensure no unlicensed code is
submitted to the project.

This is independent of whether AI is used or not.

When contributing a pull request, you should, of course, always make sure that
the proposal is of good quality and the best effort that follows our
guidelines. A basic rule of thumb is that if someone can spot that the
contribution was made with the help of AI, you have more work to do.

We can accept code written with the help of AI into the project, but the code
must still follow coding standards, be written clearly, be documented, feature
test cases, and adhere to all the normal requirements we have.
