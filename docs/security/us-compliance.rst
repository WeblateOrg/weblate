US controls compliance
======================

.. include:: /snippets/compliance-warning.rst

ITAR and other export controls
------------------------------

Weblate can be run within your own datacenter or virtual private cloud. As
such, it can be used to store ITAR or other export-controlled information,
however, end users are responsible for ensuring such compliance.

The Hosted Weblate service has not been audited for compliance with ITAR or
other export controls, and does not currently offer the ability to restrict
translations access by country.

US encryption controls
----------------------

Weblate does not contain any cryptographic code, but might be subject
export controls as it uses third party components utilizing cryptography
for authentication, data-integrity and -confidentiality.

Weblate and all it's dependencies have publicly available source code meaning
it can usually be exported and reexported without restriction.

Software components used by Weblate (listing only components related to
cryptographic function):

* `Python <https://www.python.org/>`_
* `Cryptography <https://cryptography.io/>`_
* `GnuPG <https://www.gnupg.org/>`_
* `Git <https://git-scm.com/>`_
* `curl <https://curl.se/>`_
* `OpenSSL <https://www.openssl.org/>`_

The strength of encryption keys depends on the configuration of Weblate and
the third party components it interacts with, but in any decent setup it will
include all export restricted cryptographic functions:

- In excess of 56 bits for a symmetric algorithm
- Factorisation of integers in excess of 512 bits for an asymmetric algorithm
- Computation of discrete logarithms in a multiplicative group of a finite field of size greater than 512 bits for an asymmetric algorithm
- Discrete logarithms in a group different than above in excess of 112 bits for an asymmetric algorithm

Weblate doesn't have any cryptographic activation feature, but it can be
configured in a way where no cryptography code would be involved. The
cryptographic features include:

- Accessing remote servers using secure protocols (HTTPS)
- Generating signatures for code commits (PGP)

.. seealso::

   `Export Controls (EAR) on Open Source Software <https://www.magicsplat.com/blog/ear/>`_
