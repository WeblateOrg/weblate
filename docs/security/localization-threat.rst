Localization Threat Model
=========================

Outsourcing or crowdsourcing translation tasks to third parties introduces additional security and privacy risks. Unlike internal development teams, translators may have limited trust relationships with the organization and may operate from various jurisdictions. This model identifies and classifies threats associated with external translation contributors.

Key Assumptions
---------------
- Translators may be contractors, volunteers, or agencies with varying levels of vetting.
- Translators require access to Weblate.
- Translation strings may contain sensitive content such as unreleased features, legal terms, or security messages.
- The organization has limited control over translators' local environments.

Threat Categories (STRIDE)
--------------------------

1. Spoofing
+++++++++++

- **S1. Fake translator accounts impersonating legitimate contributors.**

  - Risk: Unauthorized access to projects or injection of malicious strings.
  - Mitigations:

    - Enforce strong authentication (2FA); see :ref:`project-enforced_2fa`.
    - Verify identities of contracted translators.
    - Use role-based access to limit project scope; see :ref:`acl`.

2. Tampering
++++++++++++

- **T1. Malicious translations embedding harmful payloads.**

  - Risk: Injection of JavaScript, HTML, or format-string attacks if translations are not properly escaped.
  - Mitigations:

    - Apply strict input validation in Weblate. Enforcing quality checks like :ref:`check-safe-html` might help. See :ref:`checks` and :ref:`component-enforced_checks`.
    - Use automated security scanning for translation files in your CI.
    - Limit usage of dangerous markup from translation files. Depending on the used localization framework, this might be implicit, opt-in, or require a third-party library.

- **T2. Insertion of misleading translations.**

  - Risk: Users misled about application behavior (e.g., consent dialogs mistranslated).
  - Mitigations:

    - Perform peer review of critical strings; see :ref:`peer-review` or :ref:`reviews`.
    - Maintain style guides and :ref:`glossary` to prevent manipulation.

3. Repudiation
++++++++++++++

- **R1. Disputes over malicious or poor-quality translations.**

  - Risk: Translators deny responsibility for injected issues.
  - Mitigations:

    - All changes in Weblate are logged.
    - Use Weblate with version control for immutable history.

4. Information Disclosure
+++++++++++++++++++++++++

- **I1. Leakage of unreleased product details.**

  - Risk: Translators gain early access to unreleased features or confidential terminology.
  - Mitigations:

    - Segment projects to limit access to sensitive strings.
    - Apply non-disclosure agreements with external agencies.
    - Delay translation of highly confidential strings until public release.

- **I2. Exposure of personal data within strings.**

  - Risk: Translators might access or misuse embedded user data.
  - Mitigations:

    - Avoid exposing real user data in source strings.
    - Use placeholders for sensitive fields.

5. Denial of Service
++++++++++++++++++++

- **D1. Bulk submission of junk translations.**

  - Risk: Review queues overwhelmed; release timelines disrupted.
  - Mitigations:

    - Choose an appropriate workflow to match your team capacity. :ref:`workflow-customization` can allow you to tweak this on a language basis.
    - Configure automated translation quality checks; see :ref:`checks`.

6. Elevation of Privilege
+++++++++++++++++++++++++

- **E1. The translator gains unauthorized project-wide or administrative rights.**

  - Risk: Escalation leading to tampering or data exposure.
  - Mitigations:

    - Apply the principle of least privilege.
    - Regularly review access rights and group memberships.

Asset Inventory
---------------

- **Source Strings:** May contain unreleased product features or legal text.
- **Translated Strings:** Output presented directly to end users.
- **User Data Placeholders:** Names, emails, or IDs referenced in strings.
- **Access Credentials:** Accounts for translators, agencies, or bots.

Trust Boundaries
----------------

- **Organization ↔ Translators:** Authentication and role-based access must be enforced.
- **Translation Platform ↔ Source Control:** Synchronization requires secured tokens/keys.
- **Translators ↔ Translation Platform:** All input must be sanitized before integration into builds.
- **Platform ↔ End Users:** Ensures that translations cannot be weaponized for code injection.

Mitigation Summary
------------------

- Enforce 2FA and RBAC for translator accounts; see :ref:`project-enforced_2fa`.
- Require non-disclosure agreements or contracts for professional translators.
- Use automated quality/security scanning for translations; see :ref:`checks`.
- Perform peer review of critical strings; see :ref:`peer-review` or :ref:`reviews`.
- Limit project visibility to reduce exposure of sensitive content; see :ref:`acl`.
- Regularly patch and harden your Weblate server. You might also consider :doc:`/admin/support`.
- Retain immutable version history for all translation changes in the version control system.

Conclusion
----------

Third-party translators introduce unique risks compared to internal contributors. With proper technical, organizational, and contractual controls, organizations can mitigate these risks and safely integrate external translation services while maintaining product integrity and compliance.
