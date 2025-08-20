.. _report-issue:

Reporting issues in Weblate
===========================

Weblate `issue tracker <https://github.com/WeblateOrg/weblate/issues>`_ is hosted at GitHub.

Feel welcome to report any issues you have or suggest improvements for Weblate there.
There are various templates prepared to comfortably guide you through the issue report.

.. note::

   If what you have found is a security issue in Weblate, please see :ref:`security`.

If you are not sure about your bug report or feature request, you can try :ref:`discussions`.

.. _ai-issues:

Using AI to create issues
-------------------------

If you asked an AI tool to find problems in Weblate or its modules, you
**must** make sure to reveal this fact in your report.

You must also double-check the findings carefully before reporting them to us
to validate that the issues are indeed existing and working exactly as the AI
says. AI-based tools frequently generate inaccurate or fabricated results.

It is *rarely* a good idea to just copy and paste an AI-generated report to the
project. Those generated reports typically are too wordy and rarely to the
point (in addition to the common fabricated details). If you actually discover
a issue with an AI and you have verified it yourself to be true, write the
report yourself and explain the issue as you have learned it. This makes sure
the AI-generated inaccuracies and invented issues are filtered out early before
they waste more people's time.

As we take security reports seriously, we investigate each report with
priority. This work is both time- and energy-consuming and pulls us away from
doing other meaningful work. Fake and otherwise made-up security issues
effectively prevent us from doing real project work and make us waste time and
resources.

We ban users immediately who submit made-up fake reports to the project.

Issues lifecycle
----------------


.. graphviz::

    digraph "Issue lifecycle" {
      graph [fontname = "sans-serif", fontsize=10, ranksep=0.6, newrank=true];
      node [fontname = "sans-serif", fontsize=10, margin=0.15];
      edge [fontname = "sans-serif", fontsize=10];

      subgraph cluster_states {
         graph [color=white];
         "Waiting for: Triage" [shape=box, fillcolor="#1fa385", fontcolor=white, style=filled];
         "Waiting for: Demand" [shape=box, fillcolor="#1fa385", fontcolor=white, style=filled];
         "Waiting for: Community" [shape=box, fillcolor="#1fa385", fontcolor=white, style=filled];
         "Waiting for: Milestone" [shape=box, fillcolor="#1fa385", fontcolor=white, style=filled];
         "Waiting for: Implementation" [shape=box, fillcolor="#1fa385", fontcolor=white, style=filled];
         "Waiting for: Release" [shape=box, fillcolor="#1fa385", fontcolor=white, style=filled];
      }

      "Issue created" [fillcolor="#144d3f", fontcolor=white, style=filled];
      "Issue closed as not planned" [fillcolor="#cccccc", style=filled];
      "Issue converted to a discussion" [fillcolor="#cccccc", style=filled];
      "Issue resolved" [fillcolor="#144d3f", fontcolor=white, style=filled];

      "Issue created" -> "Waiting for: Triage";

      "Waiting for: Triage" -> "Waiting for: Community" [label="The issue is not clearly defined"];
      "Waiting for: Triage" -> "Issue closed as not planned" [label="The issue is out of scope"];
      "Waiting for: Triage" -> "Issue converted to a discussion" [label="The issue is merely a support request"];
      "Waiting for: Triage" -> "Waiting for: Milestone" [label="Ready to to be worked on"];

      "Waiting for: Community" -> "Waiting for: Triage" [label="Community feedback received"];
      "Waiting for: Community" -> "Issue closed as not planned" [label="Lack of response"];

      "Waiting for: Community" -> "Waiting for: Milestone" [label="Ready to to be worked on"];
      "Waiting for: Community" -> "Waiting for: Demand" [label="Too narrow use case"];
      "Waiting for: Demand" -> "Waiting for: Milestone" [label="Ready to to be worked on"];
      "Waiting for: Demand" -> "Issue closed as not planned" [label="The issue is out of scope"];
      "Waiting for: Milestone" -> "Waiting for: Implementation" [label="Milestone assigned issue will be worked on"];
      "Waiting for: Implementation" -> "Waiting for: Release" [label="Issue implemented waiting for a release"];
      "Waiting for: Release" -> "Issue resolved" [label="The solution for the issue has been released"];

    }
