.. _contributing:

Contributing
============

There are dozens of ways to contribute to Weblate. We welcome any help, be it
coding help, graphics design, documentation or sponsorship.

Code and development
--------------------

Weblate is being developed on GitHub <https://github.com/WeblateOrg/weblate>. You
are welcome to fork the code and open pull requests. Patches in any other form
are welcome as well. 

Coding standard
+++++++++++++++

The code should follow PEP-8 coding guidelines.

It is good idea to check your contributions using :program:`pep8`,
:program:`pylint` and :program:`pyflages`. You can execute all checks
by script :file:`ci/run-lint`.

Testsuite
+++++++++

We do write testsuite for our code, so please add testcases for any new
functionality and verify that it works. You can see current test results on
Travis <https://travis-ci.org/WeblateOrg/weblate> and coverage on Codecov
<https://codecov.io/github/WeblateOrg/weblate>.

To run testsuite locally use:

.. code-block:: sh

    ./manage.py test --settings weblate.settings_test

You can also specify individual tests to run:

.. code-block:: sh

    ./manage.py test --settings weblate.settings_test weblate.gitexport

.. seealso::

    See `Testing in Django <https://docs.djangoproject.com/en/stable/topics/testing/>`_ 
    for more information on running and writing tests for Django.

Issue tracking
++++++++++++++

The issue tracker is hosted on GitHub as well:
<https://github.com/WeblateOrg/weblate/issues>

Starting with our codebase
--------------------------

If you are looking for some bugs which should be good for starting with our
codebase, you can find them labelled with :guilabel:`newbie` tag:

https://github.com/WeblateOrg/weblate/labels/newbie

Earning money by coding
-----------------------

We're using Bountysource to fund our development, you can participate on this
as well by implementing issues with bounties:

https://github.com/WeblateOrg/weblate/labels/bounty

Translating
-----------

Weblate is being translated using Weblate on <https://hosted.weblate.org/>, feel
free to join us in effort to make Weblate available in as many world languages
as possible.


Funding Weblate development
---------------------------

You can fund further Weblate development on `Bountysource`_. Funds collected
there are used to fund free hosting for free software projects and further
development of Weblate. Please check the `Bountysource`_ page for details such
as funding goals and rewards you can get for funding.

.. include:: ../BACKERS.rst


.. _Bountysource: https://salt.bountysource.com/teams/weblate
