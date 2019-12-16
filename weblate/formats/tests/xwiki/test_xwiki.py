import os
from xml.etree import ElementTree

from django.utils.encoding import force_text

from weblate.formats.tests.test_formats import AutoFormatTest
from weblate.formats.xwiki import (
    XWikiFullPageFormat,
    XWikiPagePropertiesFormat,
    XWikiPropertiesFormat,
)
from weblate.lang.models import Language

XWIKI_TEST_DATA = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'data'
)


def get_xwiki_test_file(name):
    """Return filename of test file."""
    return os.path.join(XWIKI_TEST_DATA, name)


XWIKI_PROPERTIES = get_xwiki_test_file('xwiki.properties')
XWIKI_PAGE_PROPERTIES = get_xwiki_test_file("XWikiSource.xml")
XWIKI_FULL_PAGE = get_xwiki_test_file("XWikiFullPage.xml")


class XWikiPropertiesFormatTest(AutoFormatTest):
    FORMAT = XWikiPropertiesFormat
    FILE = XWIKI_PROPERTIES
    BASE = ''
    MIME = 'text/plain'
    COUNT = 10
    COUNT_CONTENT = 8
    EXT = 'properties'
    MASK = 'java/xwiki_*.properties'
    EXPECTED_PATH = 'java/xwiki_cs-CZ.properties'
    FIND = 'job.question.button.confirm'
    FIND_CONTEXT = 'job.question.button.confirm'
    FIND_MATCH = 'Confirm the operation {0}'
    MATCH = '\n'
    NEW_UNIT_MATCH = b'\nkey=Source string\n'
    EXPECTED_FLAGS = ''

    def assert_same(self, newdata, testdata):
        self.assertEqual(
            force_text(newdata).strip().splitlines(),
            force_text(testdata).strip().splitlines(),
        )

    def test_content_units(self):
        storage = self.parse_file(self.FILE)
        self.assertEqual(len(list(storage.content_units)), self.COUNT_CONTENT)

    def test_save(self, edit=False):
        # XWiki simple quotes should be handled the following way:
        # they are escaped with another simple quote '
        # if an argument {X} is present where X is a number.

        # Read test content
        with open(self.FILE, 'rb') as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Write test data to file
        with open(testfile, 'wb') as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.parse_file(testfile)
        units = storage.all_units

        # first and second units are considered as blank
        # (they do not contain any source/target)
        # we might expect them to be header,
        # but it's not the case with the current implem.
        # asserting it to ensure it does not change with time.
        self.assertFalse(units[0].has_content())
        self.assertFalse(units[0].unit.isheader())
        self.assertTrue(units[0].unit.isblank())
        self.assertIn("See the NOTICE file distributed with this work for additional",
                      units[0].notes)

        self.assertTrue(units[1].has_content())
        self.assertFalse(units[1].unit.isheader())
        self.assertFalse(units[1].unit.isblank())
        self.assertIn("# This contains the translations of the module in the default "
                      "language\n"
                      "# (generally English).",
                      units[1].notes)
        self.assertEqual("Confirm the operation {0}", units[1].target)

        # Check second translation, since it will be removed afterwards for the test
        self.assertEqual("job.question.button.cancel", units[2].source)
        self.assertEqual("Cancel", units[2].target)

        # some other units with simple quotes, that should be properly parsed
        self.assertEqual("Canceling with ''", units[3].target)
        self.assertEqual("Answering to test ' {3}", units[4].target)
        self.assertEqual("job.question. escapedSpace.answering", units[5].source)

        # Create appropriate target file
        translation_file = os.path.join(self.tempdir,
                                        os.path.basename(self.EXPECTED_PATH))
        self.FORMAT.add_language(translation_file,
                                 Language.objects.get(code='cs'),
                                 self.BASE)
        translation_data = self.FORMAT(storefile=translation_file,
                                       template_store=storage,
                                       language_code='cs')
        translation_units = translation_data.all_units
        self.assertEqual(self.COUNT, len(translation_units))

        if edit:
            # Put a simple quote to see if the serialization is properly handled
            unit_to_translate, create = translation_data.find_unit(units[1].context,
                                                                   units[1].source)
            self.assertTrue(create)
            translation_data.add_unit(unit_to_translate.unit)
            translation_data.all_units[1].unit = unit_to_translate.unit
            unit_to_translate.set_target("Confirmation de l'opération {0}")

            # Check encoding
            unit_to_translate, create = translation_data.find_unit(units[2].context,
                                                                   units[2].source)
            self.assertTrue(create)
            translation_data.add_unit(unit_to_translate.unit)
            translation_data.all_units[2].unit = unit_to_translate.unit
            unit_to_translate.set_target("[{0}] تىپتىكى خىزمەتنى باشلاش")

            unit_to_translate, create = translation_data.find_unit(units[5].context,
                                                                   units[5].source)

            self.assertTrue(create)
            translation_data.add_unit(unit_to_translate.unit)
            translation_data.all_units[5].unit = unit_to_translate.unit
            unit_to_translate.set_target("Escaped space adding '.")
            self.assertEqual(self.COUNT, len(translation_data.all_units))

        # Save test file
        translation_data.save()

        # Read new content
        with open(translation_file, 'rb') as handle:
            newdata = force_text(handle.read(), encoding="iso-8859-1")

        if edit:
            self.assertIn("Confirmation de l''op\\u00E9ration {0}", newdata)
            self.assertNotIn("Confirmation de l'opération {0}", newdata)
            self.assertNotIn("Escaped space adding ''.", newdata)
            self.assertNotIn("[{0}] تىپتىكى خىزمەتنى باشلاش", newdata)
            self.assertIn("[{0}] \\u062A\\u0649\\u067E\\u062A\\u0649\\u0643\\u0649 "
                          "\\u062E\\u0649\\u0632\\u0645\\u06D5\\u062A\\u0646\\u0649 "
                          "\\u0628\\u0627\\u0634\\u0644\\u0627\\u0634", newdata)
        else:
            self.assertIn("## Missing: job.question.button.confirm=Confirm the "
                          "operation {0}", newdata)

        # parse again the test file since its content has been written again
        storage = self.parse_file(translation_file)

        units = storage.all_units

        self.assertEqual(10, len(units))

        # first and second units are considered as blank
        # (they do not contain any source/target)
        # we might expect them to be header, but it's not
        # the case with the current implem.
        # asserting it to ensure it does not change with time.
        self.assertFalse(units[0].has_content())
        self.assertFalse(units[0].unit.isheader())
        self.assertTrue(units[0].unit.isblank())
        self.assertIn("See the NOTICE file distributed with this work for additional",
                      units[0].notes)

        self.assertIn("# This contains the translations of the module in the default "
                      "language\n"
                      "# (generally English).",
                      units[1].notes)

        if edit:
            # third unit is first translation
            self.assertTrue(units[1].has_content())
            self.assertFalse(units[1].unit.isheader())
            self.assertFalse(units[1].unit.isblank())
            self.assertEqual(u"Confirmation de l'opération {0}", units[1].target)
            self.assertEqual("[{0}] تىپتىكى خىزمەتنى باشلاش", units[2].target)


class XWikiPagePropertiesFormatTest(AutoFormatTest):
    FORMAT = XWikiPagePropertiesFormat
    FILE = XWIKI_PAGE_PROPERTIES
    BASE = ''
    MIME = 'text/plain'
    COUNT = 6
    COUNT_CONTENT = 4
    EXT = 'xml'
    MASK = 'xml/XWikiSource.*.xml'
    EXPECTED_PATH = 'xml/XWikiSource.cs.xml'
    FIND = 'administration.section.users.disableUser.done'
    FIND_CONTEXT = 'administration.section.users.disableUser.done'
    FIND_MATCH = 'User account disabled'
    MATCH = '\n'
    NEW_UNIT_MATCH = b'\nkey=Source string\n'
    EXPECTED_FLAGS = ''

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(self.MASK, 'cs'), self.EXPECTED_PATH
        )

    def test_content_units(self):
        storage = self.parse_file(self.FILE)
        self.assertEqual(len(list(storage.content_units)), self.COUNT_CONTENT)

    def test_save(self, edit=False):
        # XWiki simple quotes should be handled the following way:
        # they are escaped with another simple quote '
        # if an argument {X} is present where X is a number.

        # Read test content
        with open(self.FILE, 'rb') as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Write test data to file
        with open(testfile, 'wb') as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.parse_file(testfile)
        units = storage.all_units

        # first unit is first translation and has a comment
        self.assertTrue(units[0].has_content())
        self.assertEqual("administration.section.users.disableUser.done",
                         units[0].source)
        self.assertEqual("User account disabled", units[0].target)
        self.assertEqual("# Users Section", units[0].notes)

        # second unit has quotes that shouldn't be escaped.
        self.assertTrue(units[1].has_content())
        self.assertEqual("administration.section.users.disableUser.failed",
                         units[1].source)
        self.assertEqual("Failed to disable the 'user' account", units[1].target)

        # Check third unit translation for quote parsing and decoding
        self.assertTrue(units[2].has_content())
        self.assertEqual("administration.section.programmingRightsWarning",
                         units[2].source)
        self.assertEqual("The user you're about to delete is the last author of "
                         "{0}{1,choice,1#1 page|1<{1} pages}{2}.", units[2].target)

        # fourth unit is the deprecated marker
        self.assertFalse(units[3].has_content())
        self.assertTrue(units[3].unit.isblank())
        self.assertEqual("## Used to indicate where deprecated keys end\n"
                         "#@deprecatedstart", units[3].notes)

        # # Create appropriate target file
        translation_file = os.path.join(self.tempdir,
                                        os.path.basename(self.EXPECTED_PATH))
        self.FORMAT.add_language(translation_file,
                                 Language.objects.get(code='cs'),
                                 self.BASE)
        translation_data = self.FORMAT(storefile=translation_file,
                                       template_store=storage,
                                       language_code='cs')
        translation_units = translation_data.all_units
        self.assertEqual(self.COUNT, len(translation_units))

        if edit:
            # Put a simple quote to see if the serialization is properly handled
            unit_to_translate, create = translation_data.find_unit(units[2].context,
                                                                   units[2].source)
            self.assertTrue(create)
            translation_data.add_unit(unit_to_translate.unit)
            translation_data.all_units[2].unit = unit_to_translate.unit
            unit_to_translate.set_target("L'utilisateur que vous êtes sur le point de "
                                         "supprimer est le dernier auteur de "
                                         "{0}{1,choice,1#1 page|1<{1} pages}{2}.")

            # Check encoding
            unit_to_translate, create = translation_data.find_unit(units[1].context,
                                                                   units[1].source)
            self.assertTrue(create)
            translation_data.add_unit(unit_to_translate.unit)
            translation_data.all_units[1].unit = unit_to_translate.unit
            unit_to_translate.set_target("[{0}] تىپتىكى خىزمەتنى باشلاش")

            self.assertEqual(self.COUNT, len(translation_data.all_units))

        # Save test file
        translation_data.save()

        # Read new content
        with open(translation_file, 'rb') as handle:
            newdata = force_text(handle.read())

        xml_data = ElementTree.XML(newdata)
        self.assertEqual('cs', xml_data.find('language').text)
        self.assertEqual('1', xml_data.find('translation').text)

        self.assertIn('<?xml version="1.1" encoding="UTF-8"?>', newdata)
        self.assertIn("<!--\n"
                      " * See the NOTICE file distributed with"
                      " this work for additional", newdata)
        self.assertIn("* 02110-1301 USA, or see the FSF site: http://www.fsf.org.\n-->",
                      newdata)
        self.assertNotIn("\\'", newdata)

        content_text = xml_data.find('content').text

        if edit:
            self.assertIn("administration.section.programmingRightsWarning="
                          "L''utilisateur que vous êtes sur le point de "
                          "supprimer est le dernier auteur de "
                          "{0}{1,choice,1#1 page|1&lt;{1} pages}{2}.",
                          content_text)
            self.assertIn("[{0}] تىپتىكى خىزمەتنى باشلاش", content_text)
        else:
            self.assertIn("# Missing: administration.section.users.disableUser.failed="
                          "Failed to disable the 'user' account", content_text)

        # parse again the test file since its content has been written again
        storage = self.parse_file(translation_file)

        units = storage.all_units

        self.assertEqual(6, len(units))

        # third unit is first translation only in case of edit
        if edit:
            self.assertTrue(units[2].has_content())
            self.assertEqual(u"L'utilisateur que vous êtes sur le point de "
                             "supprimer est le dernier auteur de "
                             "{0}{1,choice,1#1 page|1<{1} pages}{2}.",
                             units[2].target)
            self.assertEqual("[{0}] تىپتىكى خىزمەتنى باشلاش", units[1].target)
        self.assertIs(None, xml_data.find('attachment'))
        self.assertIs(None, xml_data.find('object'))


class XWikiFullPageFormatTest(AutoFormatTest):
    FORMAT = XWikiFullPageFormat
    FILE = XWIKI_FULL_PAGE
    BASE = ''
    MIME = 'text/plain'
    COUNT = 2
    EXT = 'xml'
    MASK = 'xml/XWikiFullPage.*.xml'
    EXPECTED_PATH = 'xml/XWikiFullPage.cs.xml'
    FIND = 'title'
    FIND_CONTEXT = 'title'
    FIND_MATCH = 'Sandbox'
    MATCH = '\n'
    NEW_UNIT_MATCH = b'\nkey=Source string\n'
    EXPECTED_FLAGS = ''

    def test_get_language_filename(self):
        self.assertEqual(
            self.FORMAT.get_language_filename(self.MASK, 'cs'), self.EXPECTED_PATH
        )

    def test_new_unit(self):
        """This test does not make sense in this context, since we're not supposed
        to be able to add new units."""
        pass

    def test_save(self, edit=False):
        # Read test content
        with open(self.FILE, 'rb') as handle:
            testdata = handle.read()

        # Create test file
        testfile = os.path.join(self.tempdir, os.path.basename(self.FILE))

        # Write test data to file
        with open(testfile, 'wb') as handle:
            handle.write(testdata)

        # Parse test file
        storage = self.parse_file(testfile)
        units = storage.all_units

        # first unit is the title
        self.assertTrue(units[0].has_content())
        self.assertEqual("title", units[0].source)
        self.assertEqual("Sandbox", units[0].target)

        # second unit is the content
        self.assertTrue(units[1].has_content())
        self.assertEqual("content", units[1].source)
        self.assertIn("= Headings =", units[1].target)
        self.assertIn("* [[Sandbox Test Page 1>>Sandbox.TestPage1]]", units[1].target)
        self.assertIn("{{info}}\nDon't worry about overwriting\n{{/info}}",
                      units[1].target)

        # # Create appropriate target file
        translation_file = os.path.join(self.tempdir,
                                        os.path.basename(self.EXPECTED_PATH))
        self.FORMAT.add_language(translation_file,
                                 Language.objects.get(code='cs'),
                                 self.BASE)
        translation_data = self.FORMAT(storefile=translation_file,
                                       template_store=storage,
                                       language_code='cs')
        translation_units = translation_data.all_units
        self.assertEqual(self.COUNT, len(translation_units))

        if edit:
            # Put a simple quote to see if the serialization is properly handled
            unit_to_translate, create = translation_data.find_unit(units[1].context,
                                                                   units[1].source)
            self.assertTrue(create)
            translation_data.add_unit(unit_to_translate.unit)
            translation_data.all_units[1].unit = unit_to_translate.unit
            unit_to_translate.set_target("= Titre=\n"
                                         "\n"
                                         "* [[Bac à sable>>Sandbox.TestPage1]]\n"
                                         "{{info}}\n"
                                         "Ne vous inquiétez pas d'écraser\n"
                                         "{{/info}}"
                                         "[{0}] تىپتىكى خىزمەتنى باشلاش")
            self.assertEqual(self.COUNT, len(translation_data.all_units))

        # Save test file
        translation_data.save()

        # Read new content
        with open(translation_file, 'rb') as handle:
            newdata = force_text(handle.read())

        xml_data = ElementTree.XML(newdata)
        self.assertEqual('cs', xml_data.find('language').text)
        self.assertEqual('1', xml_data.find('translation').text)

        self.assertIn('<?xml version="1.1" encoding="UTF-8"?>', newdata)
        self.assertIn("<!--\n"
                      " * See the NOTICE file distributed with"
                      " this work for additional", newdata)
        self.assertIn("* 02110-1301 USA, or see the FSF site: http://www.fsf.org.\n-->",
                      newdata)
        self.assertNotIn("\\'", newdata)

        if edit:
            content_text = xml_data.find('content').text
            self.assertEqual("= Titre=\n"
                             "\n"
                             "* [[Bac à sable>>Sandbox.TestPage1]]\n"
                             "{{info}}\n"
                             "Ne vous inquiétez pas d'écraser\n"
                             "{{/info}}"
                             "[{0}] تىپتىكى خىزمەتنى باشلاش", content_text)
            self.assertIn("* [[Bac à sable&gt;&gt;Sandbox.TestPage1]]", newdata)
            self.assertIn("[{0}] تىپتىكى خىزمەتنى باشلاش", newdata)

        else:
            self.assertEqual(None, xml_data.find('content').text)
        self.assertIs(None, xml_data.find('attachment'))
        self.assertIs(None, xml_data.find('object'))
