Data residency and EU cloud sovereignty
=======================================

This page describes data-residency and cloud-sovereignty properties of Weblate
services operated by Weblate s.r.o., including **Hosted Weblate** and
**Weblate Cloud**. It does not describe arbitrary self-hosted Weblate
deployments, where the deploying organization controls hosting, backups,
integrations, legal basis, and retention.

Weblate-operated services are designed for European data residency and customer
control. The service operator is Weblate s.r.o., a company established in the
European Union, and the primary hosting infrastructure is provided by Hetzner
Online GmbH and Hetzner Finland Oy.

Where data lives
----------------

- Customer data, including translations, user information, operational data,
  and backups, is stored and processed within the European Union.
- Primary service locations are in Germany.
- No operational data leaves the EU unless explicitly requested or configured by
  the customer, for example by enabling external backups, repository hosting,
  authentication, e-mail, analytics, error reporting, or machine-translation
  integrations outside the EU.

Infrastructure provider
-----------------------

Weblate-operated services use Hetzner infrastructure. Hetzner Online GmbH and
Hetzner Finland Oy are certified according to DIN ISO/IEC 27001:2022 for an
information security management system covering infrastructure, operation, and
customer support for their data center parks in Nuremberg, Falkenstein, and
Helsinki.

Hetzner states that its data centers use electricity from renewable sources.
Its German data centers use hydropower, and its Finnish data center park has
used hydropower since opening.

.. seealso::

   * `Hetzner ISMS and data protection`_
   * `Hetzner sustainability`_

EU cloud sovereignty
--------------------

Weblate-operated services are intended to support common European cloud
sovereignty requirements:

- **Data sovereignty:** Weblate stores and processes customer data in the EU.
- **Operational sovereignty:** Weblate s.r.o. operates the application service
  from within the EU using EU infrastructure providers.
- **Legal sovereignty:** The service is provided by an EU company and uses EU
  hosting infrastructure. This reduces exposure to non-EU cloud operators, but
  does not remove every possible cross-border legal or integration dependency.
- **Technical sovereignty:** Weblate is libre software and can be self-hosted,
  migrated, or run as a dedicated deployment when an organization needs stronger
  isolation or deployment-specific controls.
- **Customer control:** Projects, translations, and user data can be exported or
  deleted. External integrations are optional and configurable.

The operational controls around security incidents and service continuity are
documented in :doc:`incident-response-plan` and
:doc:`disaster-recovery-plan`.

Cloud Sovereignty Framework
---------------------------

The EU Cloud Sovereignty Framework and similar procurement frameworks are often
described using Sovereignty Effectiveness Assurance Levels (SEAL). Weblate's
target direction for operated services is alignment with the expectations of
**SEAL-4 / Full Digital Sovereignty**, especially EU locality, EU operation,
data portability, open-source software, and customer control.

Weblate does not currently claim formal SEAL-4 certification, third-party
attestation, or equivalent public-sector framework approval. Such a claim would
depend on a formal assessment route and on provider-level evidence from
subprocessors such as Hetzner.

For procurement reviews, the current evidence points are:

- Weblate s.r.o. is the EU service operator.
- Customer data for Weblate-operated services is hosted and processed in the EU.
- The application is libre software and can be independently deployed.
- Customer projects and translations can be exported.
- External integrations are optional and configurable.
- Hetzner publishes ISO/IEC 27001:2022 certification for the relevant data
  center parks.

Cloud and AI Development Act
----------------------------

The EU Cloud and AI Development Act is still an emerging legislative and policy
initiative. Until final legal text and implementation guidance are available,
Weblate treats Cloud and AI Development Act questions as procurement and
readiness questions rather than as a formal compliance certification.

The current Weblate service design supports likely cloud and AI sovereignty
questions in these areas:

- **European cloud infrastructure:** Weblate-operated services use EU hosting
  for customer data and operational data.
- **Open-source stack:** Weblate is libre software, reducing dependency on
  proprietary cloud application code.
- **Portability:** Translation files, project data, and user data can be
  exported.
- **No mandatory external AI provider:** Core Weblate workflows do not require
  external AI or machine-translation services.
- **Configurable AI and machine translation:** Automatic suggestions can use
  third-party machine translation or LLM providers only when configured by an
  administrator or project owner. These services can receive source strings,
  translations, and related context, so their use should be reviewed against the
  customer's sovereignty and data-transfer requirements.

Organizations that require AI processing to stay within a chosen jurisdiction
can disable external machine-translation services or use a self-hosted provider
such as LibreTranslate.

.. seealso::

   * :doc:`privacy-compliance`
   * :ref:`machine-translation-setup`
   * :ref:`docker-libretranslate`

Customer control
----------------

Customers retain control over their Weblate data:

- Project translation files can be downloaded from Weblate or synchronized back
  to the customer's repository.
- User data can be exported and account removal can be requested as described in
  :doc:`privacy-compliance`.
- External integrations, including code hosting, authentication, e-mail,
  backups, analytics, error reporting, and machine translation, are optional and
  should be configured according to the customer's transfer and processor
  requirements.
- Dedicated Weblate instances are available for organizations needing stronger
  isolation or customized operational controls.

Service legal documents
-----------------------

.. include:: /snippets/hosted-legal-documents.rst

.. _Hetzner ISMS and data protection: https://www.hetzner.com/unternehmen/zertifizierung/
.. _Hetzner sustainability: https://www.hetzner.com/unternehmen/nachhaltigkeit/
