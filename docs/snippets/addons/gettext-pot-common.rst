This add-on updates the template configured in :ref:`component-new_base`.
It is available for gettext PO components, and the component must define a
template for new translations.

The selected update frequency applies to automatic runs after repository
refreshes. Installing or reconfiguring the add-on runs it immediately, and
manual runs from add-on management or the API also bypass the frequency
schedule. After a successful update, Weblate commits the changed template and
reloads source strings.

The template update does not update translation PO files by itself. Keep
:ref:`addon-weblate.gettext.msgmerge` installed when translation files should
follow template changes automatically. The install form for this add-on can
install that add-on, but existing add-on settings do not show that installation
option again.
