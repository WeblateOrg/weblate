.. Copyright © Michal Čihař <michal@weblate.org>
..
.. SPDX-License-Identifier: GPL-3.0-or-later

Manage 3rd Party Libraries
--------------------------
Installing and managing `3rd party` libraries in the `client` of a django project can be a bit tricky. This document provides a step-by-step guide on how to install and manage 3rd party
libraries used by the `client side` of Weblate using `Webpack`.

Prerequisites
-------------

Before proceeding with an installation, make sure you have the following prerequisites:

- Node.js.
- Yarn package manager installed on your system.
- Run ``cd client``.
- Run ``yarn install```

1- Installation
---------------

To install a library, 1st run the following command:

.. code-block:: bash

    yarn add lib

2- Importing the Library
------------------------

Then, there are two ways to import the library:

1. If it is a project-wide library (it is used/needed in all/most pages):
    - Import the library in ``src/main.js``.

2. If it is page-specific library (library is used in a specific page or template):
    - Create a new file named ``src/<lib-name>.js``.
    - Import the library in it.
    - Add an entry in ``webpack.config.js``:
      ``<lib-name>: "src/<lib-name>.js"``.

   Note: Replace ``<lib-name>`` with the actual name of the 3rd party library.

3- Building
-----------------------

Build the libraries used by the project, run the following command:

.. code-block:: bash

    yarn build

4- Including the Library
------------------------

Now the library is built and ready for use. To include it follow these steps:

1. If the library was imported in ``src/main.js``, no further steps are required (as it is already included in ``base.html``).

2. If the library was imported in its specific file ``src/<lib-name>.js``, in ``weblate/templates``` use the include tags to link to the built static JavaScript file:

.. code-block:: django

    {% load static %}
    <script src="{% static 'js/vendor/<lib-name>.js' %}"></script>

References
----------

For more information on Node.js, visit the official Node.js website: https://nodejs.org/

To learn more about Yarn package manager, refer to the Yarn website: https://yarnpkg.com/

For details on Webpack, check out the Webpack documentation: https://webpack.js.org/guides/getting-started/
