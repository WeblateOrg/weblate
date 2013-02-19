# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2013 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <http://weblate.org/>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#

'''
Fake file to translate language names.

Generated using:
./manage.py dumpdata --format=yaml lang | \
    grep fields:| \
    sed 's/.*name: /    _("/; s/, nplu.*/")/'
'''


def _(text):
    return text


def fake():
    _("Afrikaans")
    _("Akan")
    _("Albanian")
    _("Amharic")
    _("Arabic")
    _("Arabic")
    _("Aragonese")
    _("Armenian")
    _("Asturian")
    _("Azerbaijani")
    _("Basque")
    _("Belarusian")
    _("Belarusian (latin)")
    _("Bengali")
    _("Bengali (India)")
    _("Bosnian")
    _("Breton")
    _("Bulgarian")
    _("Catalan")
    _("Catalan")
    _("Central Khmer")
    _("Chinese (China)")
    _("Chinese (Hong Kong)")
    _("Chinese (Taiwan)")
    _("Cornish")
    _("Croatian")
    _("Czech")
    _("Danish")
    _("Dutch")
    _("Dzongkha")
    _("English")
    _("English (South Africa)")
    _("English (United Kingdom)")
    _("English (United States)")
    _("Esperanto")
    _("Estonian")
    _("Faroese")
    _("Filipino")
    _("Finnish")
    _("French")
    _("Frisian")
    _("Friulian")
    _("Fulah")
    _("Gaelic")
    _("Galician")
    _("Georgian")
    _("German")
    _("Greek")
    _("Gujarati")


def fake2():
    _("Gun")
    _("Hausa")
    _("Hebrew")
    _("Hindi")
    _("Hungarian")
    _("Icelandic")
    _("Indonesian")
    _("Interlingua")
    _("Irish")
    _("Italian")
    _("Japanese")
    _("Javanese")
    _("Kannada")
    _("Kashubian")
    _("Kazakh")
    _("Kirghiz")
    _("Korean")
    _("Kurdish")
    _("Kurdish Sorani")
    _("Lao")
    _("Latvian")
    _("Lingala")
    _("Lithuanian")
    _("Luxembourgish")
    _("Macedonian")
    _("Maithili")
    _("Malagasy")
    _("Malay")
    _("Malayalam")
    _("Maltese")
    _("Maori")
    _("Mapudungun")
    _("Marathi")
    _("Mongolian")
    _("Morisyen")
    _("Nahuatl languages")
    _("Neapolitan")
    _("Nepali")
    _("Norwegian Bokmål")
    _("Norwegian Nynorsk")
    _("Occitan")
    _("Oriya")
    _("Papiamento")
    _("Pedi")
    _("Persian")
    _("Piemontese")
    _("Polish")


def fake3():
    _("Portuguese")
    _("Portuguese (Brazil)")
    _("Portuguese (Portugal)")
    _("Punjabi")
    _("Pushto")
    _("Romanian")
    _("Romansh")
    _("Russian")
    _("Scots")
    _("Serbian")
    _("Serbian (cyrillic)")
    _("Serbian (latin)")
    _("Sinhala")
    _("Slovak")
    _("Slovenian")
    _("Somali")
    _("Songhai languages")
    _("Sotho")
    _("Spanish")
    _("Sundanese")
    _("Swahili")
    _("Swedish")
    _("Tajik")
    _("Tamil")
    _("Tatar")
    _("Telugu")
    _("Thai")
    _("Tibetan")
    _("Tigrinya")
    _("Turkish")
    _("Turkmen")
    _("Uighur")
    _("Ukrainian")
    _("Urdu")
    _("Uzbek")
    _("Uzbek (latin)")
    _("Vietnamese")
    _("Walloon")
    _("Welsh")
    _("Yoruba")
    _("Zulu")
