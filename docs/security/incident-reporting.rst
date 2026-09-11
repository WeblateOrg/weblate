Incident reporting
==================

This runbook helps the Weblate team handle product-security reports and
security incidents affecting Weblate-operated services. The reporting policy
and deadlines are in :doc:`issues`. For service containment and recovery, use
:doc:`incident-response-plan`.

One person handles the incident, with an available teammate as backup. The
same people investigate, report, and communicate as needed. Contact assignments,
access details, and completed incident notes belong in private team records.

Pick up the incident
--------------------

Whoever sees a credible report of active exploitation or a severe security
incident alerts teammates through Signal. An available teammate takes
responsibility and names a backup; responding does not require management
approval. The backup takes over if the handler becomes unavailable. Record
handover in the incident note so deadlines and promised updates remain visible.

Start one private incident note immediately. Record when the team became aware
of the relevant facts, using timestamps with a timezone, preferably UTC.
Distinguish receipt of an initial report from awareness of active exploitation
or a severe incident, recording the evidence for each. Do not wait for a fix,
formal declaration, or complete investigation to start reporting preparation.

Assess the report
-----------------

* Active exploitation means reliable evidence that a malicious actor has
  exploited a vulnerability without the system owner's permission. A
  theoretical vulnerability, a proof of concept, or lack of permission alone
  does not establish malicious exploitation. Investigate suspected
  exploitation promptly and record what is known and uncertain. See
  `CRA Article 3(42)
  <https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng#art_3>`_.
* Assess a product-security incident as severe when it harms, or could
  harm, protection of important or sensitive data or functions, or leads,
  or could lead, to the introduction or execution of malicious code in the
  product or users' systems. This includes execution of malicious code already
  present. See `CRA Article 14(5)
  <https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng#art_14>`_.
  Consider availability, authenticity, integrity, and confidentiality.
  Operational outage severity alone does not determine this classification.
* Check affected versions, release artifacts, and shipped dependencies,
  including incidents reported by self-hosted operators. Local containment
  remains the operator's responsibility; product reporting is assessed here.
  A runtime finding's disposition under :doc:`threat-model` does not by itself
  decide whether an incident needs reporting.
* Assess both reporting tracks when active exploitation also causes a severe
  incident. Record separate awareness times where appropriate and track both
  final-report deadlines.
* Check early for a personal-data breach, including accidental or unlawful
  destruction, loss, or alteration, as well as unauthorized disclosure or
  access. Assess :ref:`privacy notifications <incident-gdpr-notification>` even
  when no data was disclosed. Ask for outside advice when necessary while
  continuing investigation and reporting preparation.

Record whether reporting is mandatory or voluntary for the event and why.
Uncertainty requires prompt consultation, not a pause in preparation or
applicable deadlines. The policy baseline does not decide Weblate's regulatory
role; see :doc:`product-information`. Assess the affected hosted service or
downloadable distribution separately rather than assuming they have the same
regulatory scope.

Keep one private incident note
------------------------------

Copy these fields into the team's private incident record:

* Case ID, summary, handler, backup, and handovers.
* Product, affected versions or artifact digests, deployments, and known
  Member States where the affected product was made available, with the source
  and limitations of this information. Record incident-impact locations
  separately when already known and relevant.
* Awareness timestamps, supporting evidence, unknowns, and classification
  rationale, including the mandatory or voluntary reporting decision.
* Reporting deadlines, reminders, and any separate privacy-notification tasks.
* Investigation timeline, impact, mitigations, and when each corrective or
  mitigating measure became available.
* Copies of submitted reports, submission timestamps, platform references,
  receipts, failures, and requested follow-up reports.
* User warnings, recipients or public advisory links, promised updates, and
  any delayed technical disclosure with its reason and review date.
* Remaining actions and the outcome of the short team review.

Keep sensitive evidence and attachments with the private record, with access
limited to people handling the incident. Store credentials in the team's
credential store. Signal is for coordination; copy decisions and relevant
timestamps into the durable note. Do not use public issues for these records.

Submit and follow up
--------------------

Use the current `ENISA Single Reporting Platform guidance`_ to verify the
coordinating CSIRT, access arrangements, and mandatory or voluntary submission
route. A national incident-reporting portal is not necessarily the CRA
endpoint. Consult the coordinator if the route is unclear.

The handler submits reports; the backup takes over when needed. Ask a teammate
to review when practical, but do not miss a deadline waiting for review. Use
the deadlines in :ref:`incident-authority-reporting` and the current platform
forms. Submit available information on time, identify unknowns, and supplement
it as the investigation progresses.

* In either early-warning track, identify the event and, where known, the
  Member States where the affected product was made available. This is
  distribution information, not the location of individual users or only the
  places where exploitation was observed. For a severe incident, also include
  whether unlawful or malicious acts are suspected. Both tracks request
  distribution Member States under `CRA Article 14(2)(a) and (4)(a)
  <https://eur-lex.europa.eu/eli/reg/2024/2847/oj/eng#art_14>`_.
* In an exploited-vulnerability main notification, identify the affected
  product and describe the general nature of both the exploit and the
  vulnerability. Include corrective or mitigating measures already taken,
  measures users can take, and the sensitivity of the information where
  applicable, as required by CRA Article 14(2)(b).
* In a severe-incident main notification, describe the nature of the incident
  and provide an initial assessment, including known impact. Include
  corrective or mitigating measures already taken, measures users can take,
  and the sensitivity of the information where applicable, as required by
  CRA Article 14(4)(b).
* In an exploited-vulnerability final report, describe the vulnerability,
  including its severity and impact. Include any available information about
  malicious actors that have exploited or are exploiting it, and details of
  the security update or other corrective measures made available to remedy
  it, as required by CRA Article 14(2)(c). Availability of a mitigation can
  start this deadline before a final patch is ready.
* In a severe-incident final report, provide a detailed description of the
  incident, including its severity and impact, the type of threat or root
  cause likely to have triggered it, and both applied and ongoing mitigation
  measures, as required by CRA Article 14(4)(c). State explicitly when there
  are no ongoing mitigations.

For distribution information, use existing customer or distribution records,
such as the countries of known paying customers. State the limits of these
records: other users' locations may be unknown. Do not infer distribution in
every Member State from general EU availability. This procedure does not
require tracking individual users' locations or collecting new location data.
Report what is known, without delaying submission to discover other locations,
and update the information as needed. See the product-availability field in
the `ENISA SRP glossary
<https://www.enisa.europa.eu/topics/product-security/single-reporting-platform-srp/cra-srp-glossary>`_.

Save receipts and report references. Track requests for intermediate reports
and update earlier submissions when facts change. For an event triggering both
tracks, link the records and ensure both sets of reporting requirements are
covered; one final report must not silently replace the other.

If the platform is unavailable, record failed attempts and timestamps, contact
the coordinator through its published contingency channels, and follow its
instructions. Complete platform submission when access returns. Alternative
contact is not automatically evidence that a legal reporting obligation has
been fulfilled.

Warn users and follow up
------------------------

Send protective advice without waiting for a fix or full technical disclosure,
using the e-mail and public advisory channels in :doc:`issues`. State affected
versions, known impact, available actions, and remaining uncertainty. Record
what was communicated and follow through on promised updates.

Authority reporting, user warnings, and detailed disclosure can proceed at
different times. Record security reasons for delaying technical details and
revisit the decision on the recorded review date.

After recovery, check remaining report deadlines, requested updates, and
disclosure decisions. Hold a short team review, record improvements, and close
the incident note once outstanding actions are completed or explicitly handed
over with an owner and due date.

Preparation checklist
---------------------

These are setup tasks to complete and record privately. Publishing this
runbook does not establish that access or exercises are already in place.

* Choose the usual reporting contact and backup, and agree how teammates
  alert each other when either is unavailable.
* Verify reporting access, recovery arrangements, the coordinating CSIRT,
  and published contingency contacts using `ENISA Single Reporting Platform
  guidance`_. Keep account details private.
* Choose a private location accessible to the handler and backup for incident
  notes, and use existing team tools for deadline reminders and handovers.
* Check access to customer contact lists and GitHub security advisories.
* Run a short offline tabletop exercise covering a Friday-night exploitation
  report, a severe incident without a known vulnerability, a self-hosted or
  shipped-dependency report, and an event triggering both reporting tracks.
  Include an unavailable handler, a platform outage, incomplete information,
  and a mitigation available before the final patch. Check elapsed-hour
  deadlines and calendar-month deadlines across February. Record gaps and
  follow-up actions without sending exercise reports to real recipients.

.. _ENISA Single Reporting Platform guidance: https://www.enisa.europa.eu/topics/product-security/single-reporting-platform-srp
