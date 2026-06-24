<!--
Copyright © Michal Čihař <michal@weblate.org>

SPDX-License-Identifier: GPL-3.0-or-later
-->

# Accessibility

Weblate aims to make its web interface usable by as many people as practical.
For new and changed user-facing functionality, Weblate uses WCAG 2.2 Level AA
as the accessibility target where it applies to the product.

Accessibility work is part of regular development. User interface changes should
keep keyboard navigation, visible focus, semantic HTML, form labels, assistive
technology announcements, and sufficient contrast in mind.

## Reporting accessibility problems

Please report accessibility problems in the
[Weblate issue tracker](https://github.com/WeblateOrg/weblate/issues) using the
accessibility issue template.

Useful reports include:

- The affected page, feature, or workflow.
- Steps to reproduce the problem.
- What you expected to happen and what happened instead.
- Your browser, operating system, and any assistive technology used.
- Whether the problem also happens with keyboard-only navigation.
- Any workaround you found.

If the report includes private account, project, or security-sensitive details,
use the support or security reporting paths described in the Weblate
documentation instead of posting those details publicly.

## Known limitations

Weblate has complex interactive workflows, especially in the translation editor,
project administration, and third-party authentication flows. Some issues might
depend on the browser, installed assistive technology, or external service.

Maintainers triage accessibility reports with the `accessibility` label and use
the impact on core workflows and available workarounds to prioritize fixes.
