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

The code should follow PEP-8 coding guidelines. It is recommended to format new
code using :program:`black` code formatter (though existing code is yet formatted).

To check the code quality, you can use :program:`flake8`, the recommended
plugins are listed in :file:`requirements-test.txt`.

You can execute all coding style checks with the script :file:`ci/run-lint`.


.. _owasp:

Security by Design Principles
-----------------------------

Any code for Weblate should be writted with `Security by Design Principles`_ in
mind.

.. _Security by Design Principles: https://www.owasp.org/index.php/Security_by_Design_Principles

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

.. hint::

   The tests can also be executed inside developer docker container, see :ref:`dev-docker`.

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
by e-mail to michal@cihar.com. You can choose to encrypt it using this PGP key
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
codebase, look for ones labelled `good first issue <https://github.com/WeblateOrg/weblate/labels/good%20first%20issue>`_.

Directory structure
-------------------

Quick overview of directory structure of Weblate main repository:

``doc``
   Source code for this documentation, built using `Sphinx <https://www.sphinx-doc.org/>`_.
``dev-docker``
   Docker code to run development server, see :ref:`dev-docker`.
``weblate``
   Source code of Weblate as a `Django <https://www.djangoproject.com/>`_ application, see :ref:`internals`.
``weblate/static``
   Client files (CSS, Javascript and images).

.. _dev-docker:

Running Weblate locally in Docker
---------------------------------

If you have Docker and docker-compose installed, you can spin up the development
environment simply by running:

.. code-block:: sh

   ./rundev.sh

It will create development Docker image and start it. Weblate is running on
<http://127.0.0.1:8080/> and you can login with ``admin`` user and ``admin``
password. The new installation is empty, so you might want to continue with
:ref:`adding-projects`.

The :file:`Dockerfile` and :file:`docker-compose.yml` for this are located in
:file:`dev-docker` directory.

The script also accepts some parameters, to execute tests run it with ``test``
parameter and then specify any :djadmin:`django:test` parameters, for example:

.. code-block:: sh

   ./rundev.sh test --failfast weblate.trans

To stop the background containers run:

.. code-block:: sh

   ./rundev.sh stop

Running the script without args will recreate Docker container and restart it.

.. note::

   This is not suitable setup for production, it includes several hacks which
   are insecure, but make development easier.

Translating
-----------

Weblate is being `translated <https://hosted.weblate.org/>`_ using Weblate itself, feel
free to take part in the effort of making Weblate available in as many human languages
as possible.


Funding Weblate development
---------------------------

You can fund further Weblate development on the `donate page`_. Funds collected
there are used to fund gratis hosting for libre software projects, and further
development of Weblate. Please check the the `donate page` for details, such
as funding goals and rewards you can get by being a funder.

.. include:: ../BACKERS.rst


.. _donate page: https://weblate.org/donate/

Releasing Weblate
-----------------

Release checklist:

1. Set final version by ``./scripts/prepare-release``.
2. Make sure screenshots are up to date ``make -C docs update-screenshots``
3. Create a release ``./scripts/create-release --tag``
4. Push tags to GitHub
5. Enable building version docs on Read the Docs
6. Update Docker image
7. Close GitHub milestone
8. Once the Docker image is tested, add a tag and push it

.. _dco:

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
behalf of your employer, please use your corporate e-mail address in the
"Signed-off-by" tag.  If not, please use a personal e-mail address.
