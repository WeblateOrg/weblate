Coding guidelines
-----------------

Any code for Weblate should be written with `Security by Design Principles`_ in
mind.

.. _Security by Design Principles: https://wiki.owasp.org/index.php/Security_by_Design_Principles

Any code should come with documentation explaining the behavior. Don't forget
documenting methods, complex code blocks, or user visible features.

Any new code should utilize :pep:`484` type hints. We're not checking this in
our CI yet as existing code does not yet include them.

Git commits should follow `Conventional Commits
<https://www.conventionalcommits.org/>`_ specification.
