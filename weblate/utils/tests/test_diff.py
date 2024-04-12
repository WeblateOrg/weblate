# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later


from django.test import SimpleTestCase

from weblate.utils.diff import Differ


class DifferTestCase(SimpleTestCase):
    def setUp(self) -> None:
        self.differ = Differ()

    def test_basic(self) -> None:
        self.assertEqual(
            self.differ.highlight(
                "ahoj svete",
                "nazdar svete",
            ),
            "<del>nazdar</del><ins>ahoj</ins> svete",
        )
        self.assertEqual(
            self.differ.highlight(
                "nazdar svete",
                "ahoj svete",
            ),
            "<del>ahoj</del><ins>nazdar</ins> svete",
        )

    def test_chars(self) -> None:
        self.assertEqual(
            self.differ.highlight(
                "BXC",
                "AX",
            ),
            "<del>AX</del><ins>BXC</ins>",
        )
        self.assertEqual(
            self.differ.highlight(
                "AX",
                "BXC",
            ),
            "<del>BXC</del><ins>AX</ins>",
        )

    def test_hebrew(self) -> None:
        self.assertEqual(
            self.differ.highlight(
                "אָבוֹת קַדמוֹנִים כפולים של <אדם>",
                "אבות קדמונים כפולים של <אדם>",
            ),
            "<del>א</del><ins>אָ</ins>ב<del>ו</del><ins>וֹ</ins>ת <del>ק</del><ins>קַ</ins>דמו<del>נ</del><ins>ֹנִ</ins>ים כפולים של &lt;אדם&gt;",
        )
        self.assertEqual(
            self.differ.highlight(
                "אבות קדמונים כפולים של <אדם>",
                "אָבוֹת קַדמוֹנִים כפולים של <אדם>",
            ),
            "<ins>א</ins><del>אָ</del>ב<ins>ו</ins><del>וֹ</del>ת <ins>ק</ins><del>קַ</del>דמ<ins>ו</ins><del>וֹנִ</del><ins>נ</ins>ים כפולים של &lt;אדם&gt;",
        )

    def test_sentry_4428(self) -> None:
        self.assertEqual(
            self.differ.highlight(
                "<![CDATA[\nSection: perl\nPriority: optional\nStandards-Version: 4.5.1\n\nPackage: libxml-libxml-perl\nVersion: 2.0207-1\nMaintainer: Raphael Hertzog <hertzog@debian.org>\nDepends: libxml2 (>= 2.9.10)\nArchitecture: all\nDescription: Fake package - module manually installed in site_perl\n This is a fake package to let the packaging system\n believe that this Debian package is installed.\n .\n In fact, the package is not installed since a newer version\n of the module has been manually compiled &amp; installed in the\n site_perl directory.\n]]>",
                "\nSection: perl\nPriority: optional\nStandards-Version: 3.9.6\n\nPackage: libxml-libxml-perl\nVersion: 2.0116-1\nMaintainer: Raphael Hertzog &lt;hertzog@debian.org&gt;\nDepends: libxml2 (&gt;= 2.7.4)\nArchitecture: all\nDescription: Fake package - module manually installed in site_perl\n This is a fake package to let the packaging system\n believe that this Debian package is installed. \n .\n In fact, the package is not installed since a newer version\n of the module has been manually compiled &amp; installed in the\n site_perl directory.",
            ),
            """<ins>&lt;![CDATA[</ins>
<del></del>Section: perl
Priority: optional
Standards-Version: <del>3.9.6</del><ins>4.5.1</ins>

Package: libxml-libxml-perl
Version: 2.0<del>116</del><ins>207</ins>-1
Maintainer: Raphael Hertzog <del>&amp;lt;</del><ins>&lt;</ins>hertzog@debian.org<del>&amp;gt;</del><ins>&gt;</ins>
Depends: libxml2 (<del>&amp;gt;= 2.7.4</del><ins>&gt;= 2.9.10</ins>)
Architecture: all
Description: Fake package - module manually installed in site_perl
 This is a fake package to let the packaging system
 believe that this Debian package is installed.<del> </del>
 .
 In fact, the package is not installed since a newer version
 of the module has been manually compiled &amp;amp; installed in the
<del></del> site_perl directory.<ins>
]]&gt;</ins>""",
        )

    def test_github_9821(self) -> None:
        self.assertEqual(
            self.differ.highlight(
                "由 {username} 邀请至 {project} 项目。",
                "由 {username} 邀请至 {site_title}。",
            ),
            "由 {username} 邀请至 {<del>site_title}</del><ins>project} 项目</ins>。",
        )
