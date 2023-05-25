Legal documents
===============

.. note::

   Herein you will find various legal information you might need to
   operate Weblate in certain legal jurisdictions. It is provided as a means of guidance,
   without any warranty of accuracy or correctness. It is ultimately your
   responsibility to ensure that your use of Weblate complies with all applicable
   laws and regulations.

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

Most likely Weblate would be classified as ECCN 5D002 or 5D992 and, as
publicly available libre software, it should not be subject to EAR (see
`Encryption items NOT Subject to the EAR
<https://www.bis.doc.gov/index.php/policy-guidance/encryption/1-encryption-items-not-subject-to-the-ear>`_).

Software components used by Weblate (listing only components related to
cryptographic function):

`Python <https://www.python.org/>`_
   See https://wiki.python.org/moin/PythonSoftwareFoundationLicenseFaq#Is_Python_subject_to_export_laws.3F
`GnuPG <https://www.gnupg.org/>`_
   Optionally used by Weblate
`Git <https://git-scm.com/>`_
   Optionally used by Weblate
`curl <https://curl.se/>`_
   Used by Git
`OpenSSL <https://www.openssl.org/>`_
   Used by Python and cURL

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
