.. index::
    single: Kotlin SDK
    single: Android; SDK

.. _kotlin-sdk:

Kotlin SDK for Android
======================

The official Kotlin SDK for Weblate delivers translation updates to Android
applications without rebuilding or redistributing them. Its Gradle plugin
generates and uploads resource metadata for each build. The Android library
downloads updated translations from the public CDN configured by the
:ref:`addon-weblate.cdn.kotlin` add-on.

The SDK is maintained in the `Kotlin SDK repository
<https://github.com/WeblateOrg/kotlin-sdk/>`_. The plugin is published on the
`Gradle Plugin Portal <https://plugins.gradle.org/plugin/org.weblate.android>`_
and the library on `Maven Central
<https://central.sonatype.com/artifact/org.weblate/android>`_.

.. warning::

   The SDK is available as an alpha release. Plugin and library versions must
   match. Breaking changes can occur before a stable release.

Requirements
------------

* Weblate 2026.10 or newer with the :ref:`addon-weblate.cdn.kotlin` add-on.
* Android Gradle Plugin 9.x.
* Android 11 (API 30) or newer for SDK runtime use.

Configure Weblate
-----------------

Install :guilabel:`Kotlin SDK CDN` on the component containing your Android
string resources. For self-hosted Weblate, configure :setting:`LOCALIZE_CDN_URL`
and :setting:`LOCALIZE_CDN_PATH` first. See :ref:`addon-weblate.cdn.kotlin` for
public CDN publication, supported resources, and build retention settings.

Copy the Gradle configuration from the add-on configuration page. It supplies
the server URL, CDN URL, project slug, and component path.
Create a :ref:`project-scoped API token <project-api>` with permission to edit
the component. Set it as ``WEBLATE_API_TOKEN`` in the build environment used
to upload metadata. Keep the token out of source control and the application.

Configure the Android project
-----------------------------

In your application module's :file:`build.gradle.kts`, add the plugin and
library using matching versions:

.. code-block:: kotlin

   plugins {
       id("org.weblate.android") version "1.0.0-alpha02"
   }

   dependencies {
       implementation("org.weblate:android:1.0.0-alpha02")
   }

Add the configuration copied from Weblate, replacing the example URLs and
slugs below with your component's values. Read the token from the environment:

.. code-block:: kotlin

   weblate {
       serverUrl = "https://hosted.weblate.org"
       cdnUrl = "https://weblate-cdn.com/ADDON_ID"
       project = "my-project"
       component = "android"
       authToken.set(providers.environmentVariable("WEBLATE_API_TOKEN"))
   }

The token is needed only when uploading build metadata. The application
downloads translations from the public CDN without an API token.

Publish build metadata
----------------------

Build the application you will distribute, then upload its generated metadata:

.. code-block:: sh

   ./gradlew uploadMetadataForWeblateRelease

The task name depends on the build variant; this example uses ``release``.
Metadata is generated under :file:`build/outputs/weblate/`. Upload it for each
application release, for example as the final step in your release pipeline.

Resource IDs must match the final distributed binary. Do not rebuild the
application after uploading metadata unless the rebuild produces identical
resource IDs. For independently built distributions such as F-Droid, use
reproducible builds so uploaded metadata matches the distributed application.
See :ref:`addon-weblate.cdn.kotlin` for build registration and compatibility
with older application versions.

Enable translation updates
--------------------------

Initialize the SDK in your application's ``onCreate`` method:

.. code-block:: kotlin

   import android.app.Application
   import android.os.Build
   import org.weblate.android.Weblate

   class WeblateApp : Application() {
       override fun onCreate() {
           super.onCreate()
           if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
               Weblate(this).scheduleDailyLocalizationUpdate()
           }
       }
   }

If your application already has an ``Application`` subclass, add the
initialization there. Otherwise, register ``WeblateApp`` in your
:file:`AndroidManifest.xml`, using its fully qualified class name:

.. code-block:: xml

   <application android:name="com.example.app.WeblateApp">
       <!-- Existing application configuration -->
   </application>

The SDK schedules daily translation downloads for the current locale on an
unmetered network. The API guard allows applications supporting older Android
versions to keep using bundled translations on those devices.

For manual updates and further usage details, see the `SDK documentation and
sample application <https://github.com/WeblateOrg/kotlin-sdk/>`_.
