.. _contributing:

Contributing
============

There are dozens of ways to contribute in Weblate. Any help is welcomed, be it
coding, graphics design, documentation or sponsorship.

Code and development
--------------------

Weblate is developed on `GitHub <https://github.com/WeblateOrg/weblate>`_. You
are welcome to fork the code and open pull requests. Patches in any other form
are welcome too.

.. seealso::

    Check out :ref:`internals` to see how Weblate looks from inside.

Coding standard
---------------

The code should follow PEP-8 coding guidelines.

It is good idea to check your contributions using :program:`pep8`,
:program:`pylint` and :program:`pyflages`. You can execute all checks
with the script :file:`ci/run-lint`.

Developer's Certificate of Origin
---------------------------------

In contributing to the Weblate project, please
certify to the following:

    Weblate Developer's Certificate of Origin. Version 1.0

    By making a contribution to this project, I certify that:

    (a) The contribution was created in whole or in part by me and I have the
        right to submit it under the license of "GNU General Public License or
        any later version" ("GPLv3-or-later"); or

    (b) The contribution is based upon previous work that, to the best of my
        knowledge, is covered under an appropriate open source license and I have
        the right under that license to submit that work with modifications,
        whether created in whole or in part by me, under GPLv3-or-later; or

    (c) The contribution was provided directly to me by some other person who
        certified (a) or (b) and I have not modified it.

    (d) I understand and agree that this project and the contribution are public
        and that a record of the contribution (including all metadata and
        personal information I submit with it, including my sign-off) is
        maintained indefinitely and may be redistributed consistent with
        Weblate's policies and the requirements of the GPLv2-or-later where
        they are relevant.

    (e) I am granting this work to this project under the terms of the
        GPLv3-or-later.

        https://www.gnu.org/licenses/gpl-3.0.html

Please confirm your affirmation of the above by adding the following
line to your patch:

.. code-block:: text

	Signed-off-by: Jane Developer <jane@example.org>

using your real name (sorry, no pseudonyms or anonymous contributions).

If you are a developer authorized to contribute to Weblate on
behalf of your employer, please use your corporate email address in the
"Signed-off-by" tag.  If not, please use a personal email address.

Testsuite
---------

Testsuites exist for most of the current code, increase coverage by adding testcases for any new
functionality, and verify that it works. Current test results can be found on
`Travis <https://travis-ci.org/WeblateOrg/weblate>`_ and coverage is reported on `Codecov <https://codecov.io/github/WeblateOrg/weblate>`_.

To run a testsuite locally, use:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=weblate.settings_test ./manage.py test

You can also specify individual tests to run:

.. code-block:: sh

    DJANGO_SETTINGS_MODULE=weblate.settings_test ./manage.py test weblate.gitexport

.. seealso::

    See :doc:`django:topics/testing/index` for more info on running and
    writing tests for Django.

Reporting issues
----------------

Our `issue tracker <https://github.com/WeblateOrg/weblate/issues>`_ is hosted at GitHub:

Feel welcome to report any issues with, or suggest improvement of Weblate there.
If what you have found is a security issue in Weblate, please consult the "Security
issues" section below.

.. _security:

Security issues
---------------

In order to give the community time to respond and upgrade your are strongly urged to
report all security issues privately. HackerOne is used to handle
security issues, and can be reported directly at `HackerOne <https://hackerone.com/weblate>`_.

Alternatively, report to security@weblate.org, which ends up on
HackerOne as well.

If you don't want to use HackerOne, for whatever reason, you can send the report
by email to michal@cihar.com. You can choose to encrypt it using this PGP key
`3CB 1DF1 EF12 CF2A C0EE  5A32 9C27 B313 42B7 511D`.

.. note::

    Weblate depends on third party components for many things.  In case
    you find a vulnerability affecting one of those components in general,
    please report it directly to the respective project.

    Some of these are:

    * :doc:`Django <django:internals/security>`
    * `Django REST framework <https://www.django-rest-framework.org/#security>`_
    * `Python Social Auth <https://github.com/python-social-auth>`_

Starting with our codebase
--------------------------

If looking for some bugs to familiarize yourself with the Weblate
codebase, look for ones labelled :guilabel:`good first issue` <https://github.com/WeblateOrg/weblate/labels/good%20first%20issue>`_:

If you have Docker and docker-compose installed, you can spin up the development
environment simply by running:

.. code-block:: sh

   ./rundev.sh

Earning money by coding
-----------------------

Bountysource is used to fund development, you can participate too by solving issues with bounties attached:

https://github.com/WeblateOrg/weblate/labels/bounty

Translating
-----------

Weblate is being `translated <https://hosted.weblate.org/>`_ using Weblate itself, feel
free to take part in the effort of making Weblate available in as many human languages
as possible.


Funding Weblate development
---------------------------

You can fund further Weblate development on `Bountysource`_. Funds collected
there are used to fund gratis hosting for libre software projects, and further
development of Weblate. Please check the `Bountysource`_ page for details, such
as funding goals and rewards you can get by being a funder.

.. include:: ../BACKERS.rst


.. _Bountysource: https://salt.bountysource.com/teams/weblate

Releasing Weblate
-----------------

Release checklist:

1. Make sure screenshots are up to date ``make -C docs update-screenshots``
2. Create a release ``./scripts/create-release --tag``
3. Push tags to GitHub
4. Update Docker image
5. Close GitHub milestone
6. Enable building version docs on Read the Docs
7. Once the Docker image is tested, add a tag and push it
