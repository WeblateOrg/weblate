# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2018 Michal Čihař <michal@cihar.com>
#
# This file is part of Weblate <https://weblate.org/>
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
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

import os.path
from io import BytesIO

try:
    from bidi.algorithm import get_display
except ImportError:
    from django.utils.encoding import force_text as get_display

from django.urls import reverse
from django.utils.translation import ugettext as _, pgettext, get_language
from django.template.loader import render_to_string

from PIL import Image, ImageDraw

from weblate.utils.fonts import is_base, get_font
from weblate.utils.site import get_site_url


COLOR_DATA = {
    'grey': {
        'bar': 'rgb(0, 67, 118)',
        'border': 'rgb(0, 0, 0)',
        'text': 'rgb(0, 0, 0)',
    },
    'white': {
        'bar': 'rgb(0, 67, 118)',
        'border': 'rgb(0, 0, 0)',
        'text': 'rgb(0, 0, 0)',
    },
    'black': {
        'bar': 'rgb(0, 67, 118)',
        'border': 'rgb(255, 255, 255)',
        'text': 'rgb(255, 255, 255)',
    },
    'badge': {
        'bar': 'rgb(0, 67, 118)',
        'border': 'rgb(255, 255, 255)',
        'text': 'rgb(255, 255, 255)',
    },
}

WIDGETS = {}


def register_widget(widget):
    """Register widget in dictionary."""
    WIDGETS[widget.name] = widget
    return widget


class Widget(object):
    """Generic widget class."""
    name = None
    colors = ('grey', 'white', 'black')
    extension = 'png'
    content_type = 'image/png'
    order = 100
    show = True

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        # Get object and related params
        self.obj = obj
        self.color = self.get_color_name(color)
        self.lang = lang

    def get_color_name(self, color):
        """Return color name based on allowed ones."""
        if color not in self.colors:
            return self.colors[0]
        return color


class ContentWidget(Widget):
    """Generic content widget class."""

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        super(ContentWidget, self).__init__(obj, color, lang)
        # Get translation status
        if lang:
            stats = obj.stats.get_single_language_stats(lang)
        else:
            stats = obj.stats
        self.percent = stats.translated_percent
        # Set rendering variables
        self.image = None

    def get_percent_text(self):
        return pgettext('Translated percents in widget', '{0}%').format(
            int(self.percent)
        )

    def get_content(self):
        """Return content of the badge."""
        raise NotImplementedError()


class BitmapWidget(ContentWidget):
    """Base class for bitmap rendering widgets."""
    name = None
    colors = ('grey', 'white', 'black')
    progress = {}
    extension = 'png'
    content_type = 'image/png'
    order = 100
    show = True

    def __init__(self, obj, color=None, lang=None):
        """Create Widget object."""
        super(BitmapWidget, self).__init__(obj, color, lang)
        # Get object and related params
        self.total = obj.stats.source_strings
        self.languages = obj.stats.languages
        self.params = self.get_text_params()

        # Set rendering variables
        self.draw = None
        self.width = 0

    def get_text_params(self):
        """Create dictionary used for text formatting."""
        return {
            'name': self.obj.name,
            'count': self.total,
            'languages': self.languages,
            'percent': self.percent,
        }

    def get_filename(self):
        """Return widgets filename."""
        return os.path.join(
            os.path.dirname(__file__),
            'widget-images',
            '{widget}-{color}.png'.format(**{
                'color': self.color,
                'widget': self.name,
            })
        )

    def render(self):
        """Render widget."""
        # PIL objects
        mode = 'RGB'
        self.image = Image.open(self.get_filename()).convert(mode)
        self.draw = ImageDraw.Draw(self.image)
        self.width = self.image.size[0]

        # Render progressbar
        if self.progress:
            self.render_progress()

        # Render texts
        self.render_texts()

    def render_progress(self):
        """Render progress bar."""
        # Filled bar
        if self.progress['horizontal']:
            self.draw.rectangle(
                (
                    self.progress['x'],
                    self.progress['y'],
                    self.progress['x'] +
                    self.progress['width'] / 100.0 * self.percent,
                    self.progress['y'] + self.progress['height']
                ),
                fill=COLOR_DATA[self.color]['bar'],
            )
        else:
            diff = self.progress['height'] / 100.0 * (100 - self.percent)
            self.draw.rectangle(
                (
                    self.progress['x'],
                    self.progress['y'] + diff,
                    self.progress['x'] + self.progress['width'],
                    self.progress['y'] + self.progress['height'] - diff
                ),
                fill=COLOR_DATA[self.color]['bar'],
            )

        # Progress border
        self.draw.rectangle(
            (
                self.progress['x'],
                self.progress['y'],
                self.progress['x'] + self.progress['width'],
                self.progress['y'] + self.progress['height']
            ),
            outline=COLOR_DATA[self.color]['border']
        )

    def get_text(self, text, lang_text=None):
        # Use language variant if desired
        if self.lang is not None and lang_text is not None:
            text = lang_text
            if 'English' in text:
                text = text.replace('English', self.lang.name)

        # Format text
        return text % self.params

    def render_text(self, text, lang_text, base_font_size, bold_font,
                    pos_x, pos_y, transform=True):
        if transform:
            text = self.get_text(text, lang_text)
        base_font = is_base(text)
        offset = 0

        for line in text.splitlines():

            # Iterate until text fits into widget
            for font_size in range(base_font_size, 3, -1):
                font = get_font(font_size, bold_font, base_font)
                layout_size = font.getsize(line)
                layout_width = layout_size[0]
                if layout_width + pos_x < self.width:
                    break

            # Render text
            self.draw.text(
                (pos_x, pos_y + offset),
                get_display(line),
                font=font,
                fill=COLOR_DATA[self.color]['text']
            )

            offset += layout_size[1]

    def render_texts(self):
        """Text rendering method to be overridden."""
        raise NotImplementedError()

    def get_content(self):
        """Return PNG data."""
        out = BytesIO()
        image = self.image.convert('P', palette=Image.ADAPTIVE)
        image.save(out, 'PNG')
        return out.getvalue()


class SVGWidget(ContentWidget):
    """Base class for SVG rendering widgets."""
    extension = 'svg'
    content_type = 'image/svg+xml; charset=utf-8'

    def get_content(self):
        return self.image

    def render(self):
        """Rendering method to be implemented."""
        raise NotImplementedError()


class RedirectWidget(Widget):
    """Generic redirect widget class."""
    show = False

    def redirect(self):
        """Redirect to matching SVG badge."""
        kwargs = {
            'project': self.obj.slug,
            'widget': 'svg',
            'color': 'badge',
            'extension': 'svg',
        }
        if self.lang:
            kwargs['lang'] = self.lang.code
            return reverse('widget-image', kwargs=kwargs)
        return reverse('widget-image', kwargs=kwargs)


@register_widget
class NormalWidget(BitmapWidget):
    name = '287x66'
    progress = {
        'x': 72,
        'y': 52,
        'height': 6,
        'width': 180,
        'horizontal': True,
    }
    order = 110

    def render_texts(self):
        self.render_text(
            '%(name)s',
            None,
            13, True,
            72, 6
        )
        self.render_text(
            # Translators: please keep the text short to fit into widget
            _('translating %(count)d strings into %(languages)d languages\n'
              '%(percent)d%% complete, help us improve!'),
            # Translators: please use your language name instead of English
            # and keep the text short to fit into widget
            _('translating %(count)d strings into English\n%(percent)d%%'
              ' complete, help us improve!'),
            11, False,
            72, 22
        )


@register_widget
class SmallWidget(BitmapWidget):
    name = '88x31'
    order = 120

    def render_texts(self):
        self.render_text(
            '%(name)s',
            None,
            9, True,
            23, 2
        )
        self.render_text(
            # Translators: please keep the text short to fit into widget
            _('translation\n%(percent)d%% done'),
            # Translators: please use your language name instead of English
            # and keep the text short to fit into widget
            _('English translation\n%(percent)d%% done'),
            9, False,
            23, 11
        )


@register_widget
class BadgeWidget(RedirectWidget):
    """Legacy badge which used to render PNG."""
    name = 'status'
    colors = ('badge', )


@register_widget
class ShieldsBadgeWidget(RedirectWidget):
    """Legacy badge which used to redirect to shields.io."""
    name = 'shields'
    colors = ('badge', )


@register_widget
class SVGBadgeWidget(SVGWidget):
    name = 'svg'
    colors = ('badge', )
    order = 80

    def render(self):
        translated_text = _('translated')
        font = get_font(11, False, is_base(translated_text))
        translated_width = font.getsize(translated_text)[0] + 12

        percent_text = self.get_percent_text()
        font = get_font(11, False, is_base(percent_text))
        percent_width = font.getsize(percent_text)[0] + 7

        if self.percent >= 90:
            color = '#4c1'
        elif self.percent >= 75:
            color = '#dfb317'
        else:
            color = '#e05d44'

        self.image = render_to_string(
            'badge.svg',
            {
                'translated_text': translated_text,
                'percent_text': percent_text,
                'translated_width': translated_width,
                'percent_width': percent_width,
                'width': translated_width + percent_width,
                'color': color,
                'translated_offset': translated_width // 2,
                'percent_offset': translated_width + percent_width // 2,
                'lang': get_language(),
            }
        )


@register_widget
class MultiLanguageWidget(SVGWidget):
    name = 'multi'
    order = 81
    colors = ('red', 'green', 'blue', 'auto')

    COLOR_MAP = {
        'red': '#fa3939',
        'green': '#3fed48',
        'blue': '#3f85ed',
        'auto': None,
    }

    def render(self):
        translations = []
        offset = 30
        color = self.COLOR_MAP[self.color]
        for stats in self.obj.stats.get_language_stats():
            language = stats.language
            percent = stats.translated_percent
            if self.color == 'auto':
                if percent >= 90:
                    color = '#4c1'
                elif percent >= 75:
                    color = '#dfb317'
                else:
                    color = '#e05d44'
            translations.append((
                # Language name
                language.name,
                # Translation percent
                percent,
                # Text y offset
                offset,
                # Bar y offset
                offset - 10,
                # Bar width
                int(percent * 1.5),
                # Bar color
                color,
                # Row URL
                get_site_url(reverse(
                    'project-language',
                    kwargs={'lang': language.code, 'project': self.obj.slug}
                )),
                # Bounding box y offset
                offset - 15,
            ))
            offset += 20

        self.image = render_to_string(
            'multi-language-badge.svg',
            {
                'height': len(translations) * 20 + 20,
                'boxheight': len(translations) * 20 + 10,
                'translations': translations,
            }
        )
