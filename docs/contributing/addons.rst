Developing add-ons
==================

:ref:`addons` are a way to customize localization workflow in Weblate.

.. currentmodule:: weblate.addons.base

.. autoclass:: BaseAddon
    :members:

Add-on hooks receive ORM objects from the ``weblate.*.models`` modules,
including ``Addon``, ``Component``, ``Translation``, ``Category``, ``Project``,
``Unit``, ``Change``, and ``User``. Add-on configuration forms should subclass
``weblate.addons.forms.BaseAddonForm``.

Here is an example add-on:

.. literalinclude:: ../../weblate/addons/example.py
    :language: python


Typing add-on configuration
---------------------------

Add-on configuration is stored in the ``Addon.configuration`` JSON field, so
the model keeps the persisted data as raw JSON. Add-on implementations can type
their own configuration by parameterizing ``BaseAddon`` and ``BaseAddonForm``.

Use two ``TypedDict`` classes when the stored JSON can differ from the runtime
shape: a permissive, usually ``total=False``, stored configuration for legacy
or missing values, and a total runtime configuration returned by
``normalize_configuration()``. Runtime add-on code should read
``self.configuration`` or ``self.get_configuration()`` so it sees normalized
defaults instead of raw persisted JSON.

For simple add-ons where the stored and runtime shapes are identical, define a
single ``TypedDict`` and use it for both ``BaseAddon`` type parameters. Keep
the form's ``serialize_form()`` return type aligned with the stored
configuration type.


Publishing add-on configuration
-------------------------------

Add-on change history can be visible without add-on management permission.
List configuration fields that are safe to publish in the form's
``public_configuration_fields`` attribute. Fields not explicitly listed are
kept in the snapshot with a null value and identified as redacted. The default
is an empty set so that newly added settings are not published accidentally.

Use ``BaseAddon.get_public_configuration()`` whenever configuration is exposed
outside trusted add-on management code. Internal operations which intentionally
clone a working add-on can continue to use the stored configuration.


.. _component-addon-api:

Component-mounted add-on APIs
-----------------------------

Declare an ``api_name`` and return named Django URL patterns from
``get_api_urls()``. Use ordinary Django converters and DRF views. Patterns are
registered for every provider enabled in :setting:`WEBLATE_ADDONS`, regardless
of whether the add-on is installed on a component.

Routes are mounted under
``/api/components/<project>/<component>/addons/<api_name>/``.
For categorized components, encode the full category and component path in the
component segment, as for the component REST API. Use the installation's
``api_url`` instead of constructing this URL manually.
API names must contain 1 to 64 ASCII letters, digits, underscores, or hyphens,
and must be globally unique among enabled provider classes. Weblate validates
these declarations at startup, without querying the database, and rejects
invalid or conflicting names. Providers must declare ``needs_component = True``,
``repo_scope = False``, and ``multiple = False``. The same provider can be
installed on many components, but only once on each component.

Subclass ``weblate.addons.api.InstalledAddonAPIView`` and set its ``addon_name``
to the provider's internal add-on name. The base view authenticates the request,
checks component access, and resolves the installation as ``self.addon``.
An absent or incompatible installation returns HTTP 404. Its ``permission``
defaults to ``component.edit`` and is checked before request data is parsed.
The default JSON parser bounds requests to 5 MiB, including requests without
a Content-Length header.

Use normal DRF serializer validation in the view methods. Document the full
contract using ``drf_spectacular.utils.extend_schema`` and serializer field
help text: OpenAPI discovers the same views used for runtime routing.
Reverse endpoints using ``api:<api_name>:<pattern_name>``, providing
``project__slug``, ``slug``, and any endpoint parameters.
API names are public contracts and should remain stable across implementation
changes. Restart Weblate after changing provider registration; tests overriding
registrations must rebuild their URL configuration and clear Django's URL caches.

The existing ``/api/addons/<id>/`` management API remains available.
Its read-only ``api_name`` and ``api_url`` fields reflect the enabled provider's
current declaration. Both are null when the provider is disabled or incompatible.


Testing Kotlin SDK resources
----------------------------

The :file:`.github/workflows/android.yml` workflow runs AAPT2 validation and
instrumentation tests on Android API 30 and 36 in separate jobs from the Python
test suite. Test reports and generated resources are uploaded as workflow
artifacts, including when tests fail.

Run ``python -m unittest weblate.kotlin_sdk.test_arsc`` to exercise the binary
writer. Set ``AAPT2`` to an AAPT2 executable to additionally validate generated
tables with Android's parser.

The instrumentation harness in :file:`ci/android-arsc` verifies runtime resource
overrides, locale selection, plurals, styled text, replacement, and fallback.
With the Weblate environment installed, generate its assets using
``PYTHONPATH=. uv run --frozen --only-group android python ci/android-arsc/generate-fixtures.py``.
Then run
``gradle -p ci/android-arsc connectedDebugAndroidTest`` using Gradle 8.7, JDK 17,
and Android SDK platform 35. Run against both an API 30 device/emulator and a
current supported Android version before release.
