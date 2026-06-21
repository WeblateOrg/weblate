Releases and supported versions
===============================

This page summarizes the public release, security-update, and upgrade support
policies for Weblate. For maintainer release steps, see
:doc:`/contributing/release`. For upgrade commands, see :doc:`/admin/upgrade`.
For published release artifacts, SBOMs, signatures, and provenance
attestations, see :doc:`release-artifacts`.

.. _release-cycle:

Release cycle
-------------

Weblate uses calendar versioning with monthly releases. The version format is
``<YEAR>.<MONTH>.<PATCH>`` with a numeric, non-zero-padded month. The
``<PATCH>`` part is omitted for the first release in a month when it would be
``0``, for example ``2026.5``. Patch releases use the full version number, for
example ``2026.5.1``.

Monthly releases are usually published at the beginning of the month. Patch
releases include bug fixes, security fixes, and dependency updates which should
not wait for the next monthly release.

The Docker container includes an additional version component to track changes
in the container itself, such as dependencies. Fixed Docker image tags include
the patch component together with this build component, even when the Weblate
version omits a ``0`` patch component. These updates may include security
updates.

.. _security-updates:

Security updates
----------------

Weblate provides security updates to address vulnerabilities and enhance the
application's security posture. Only the latest release is guaranteed to
receive security updates. Users are encouraged to keep Weblate up to date to
benefit from the latest security improvements.

Security update coverage and direct upgrade support are separate policies.

.. list-table::
   :header-rows: 1

   * - Version
     - Security update coverage
     - End of guaranteed security updates
     - Direct upgrade support
   * - Latest Weblate release
     - Guaranteed.
     - When the next Weblate release is published, normally the following
       month.
     - Supported.
   * - Older releases from the current or previous calendar year
     - Not guaranteed. Upgrade to the latest release to receive guaranteed
       security updates.
     - Ended when a newer Weblate release was published.
     - Direct upgrades are supported.
   * - Older releases
     - Not guaranteed.
     - Ended when a newer Weblate release was published.
     - Upgrade through the intermediate versions listed in
       :ref:`version-specific-instructions`.

Direct upgrades are supported from releases in the current or previous calendar
year. The first release in a new year drops direct upgrade support for releases
from the year before the previous year.
