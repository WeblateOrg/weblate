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

from django.conf import settings
from django.utils.translation import ugettext as _
import cairo
import pango
import pangocairo
from cStringIO import StringIO
import os.path


COLOR_DATA = {
    'grey': {
        'bar': (0, 67.0 / 255, 118.0 / 255),
        'border': (0, 0, 0),
        'text': (0, 0, 0),
    },
    'white': {
        'bar': (0, 67.0 / 255, 118.0 / 255),
        'border': (0, 0, 0),
        'text': (0, 0, 0),
    },
    'black': {
        'bar': (0, 67.0 / 255, 118.0 / 255),
        'border': (255, 255, 255),
        'text': (255, 255, 255),
    },
}

WIDGETS = {}


def register_widget(widget):
    '''
    Registers widget in dictionary.
    '''
    WIDGETS[widget.name] = widget


class Widget(object):
    '''
    Generic widget class.
    '''
    name = None
    colors = ('grey', 'white', 'black')
    progress = None

    def __init__(self, obj, color=None, lang=None):
        '''
        Creates Widget object.
        '''
        # Get object and related params
        self.obj = obj
        self.percent = obj.get_translated_percent(lang)
        self.total = obj.get_total()
        self.languages = obj.get_language_count()
        self.params = self.get_text_params()

        # Process parameters
        self.color = self.get_color_name(color)
        self.lang = lang

        # Set rendering variables
        self.surface = None
        self.context = None
        self.pango_context = None
        self.width = 0

    def get_color_name(self, color):
        '''
        Return color name based on allowed ones.
        '''
        if color not in self.colors:
            return self.colors[0]
        return color

    def get_line_width(self):
        '''
        Returns line width for current widget.
        '''
        if self.color == 'black':
            return 0.8
        return 0.2

    def get_text_params(self):
        '''
        Creates dictionary used for text formatting.
        '''
        return {
            'name': self.obj.name,
            'count': self.total,
            'languages': self.languages,
            'percent': self.percent,
        }

    def get_filename(self):
        '''
        Returns widgets filename.
        '''
        return os.path.join(
            settings.MEDIA_ROOT,
            'widgets',
            '%(widget)s-%(color)s.png' % {
                'color': self.color,
                'widget': self.name,
            }
        )

    def render(self):
        '''
        Renders widget.
        '''
        # Surface with background image
        self.surface = cairo.ImageSurface.create_from_png(
            self.get_filename()
        )
        self.width = self.surface.get_width()

        # Cairo context for graphics
        self.context = cairo.Context(self.surface)
        self.context.set_line_width(self.get_line_width())

        # Pango context for rendering text
        self.pango_context = pangocairo.CairoContext(self.context)
        self.pango_context.set_antialias(cairo.ANTIALIAS_SUBPIXEL)

        # Render progressbar
        if self.progress:
            self.render_progress()

        # Render texts
        self.context.set_source_rgb(*COLOR_DATA[self.color]['text'])
        self.render_texts()

    def render_progress(self):
        '''
        Renders progress bar.
        '''
        # Filled bar
        self.context.new_path()
        self.context.set_source_rgb(*COLOR_DATA[self.color]['bar'])
        if self.progress['horizontal']:
            self.context.rectangle(
                self.progress['x'],
                self.progress['y'],
                self.progress['width'] / 100.0 * self.percent,
                self.progress['height']
            )
        else:
            diff = self.progress['height'] / 100.0 * (100 - self.percent)
            self.context.rectangle(
                self.progress['x'],
                self.progress['y'] + diff,
                self.progress['width'],
                self.progress['height'] - diff
            )
        self.context.fill()

        # Progress border
        self.context.new_path()
        self.context.set_source_rgb(*COLOR_DATA[self.color]['border'])
        self.context.rectangle(
            self.progress['x'],
            self.progress['y'],
            self.progress['width'],
            self.progress['height']
        )
        self.context.stroke()

    def get_text_layout(self, text, font_face, font_size):
        '''
        Generates Pango layout for text.
        '''
        # Create pango layout and set font
        layout = self.pango_context.create_layout()
        font = pango.FontDescription('%s %d' % (font_face, font_size))
        layout.set_font_description(font)

        # Add text
        layout.set_text(text)

        return layout

    def render_text(self, text, lang_text, font_face, font_size, pos_x, pos_y):
        # Use language variant if desired
        if self.lang is not None and lang_text is not None:
            text = lang_text
            if 'English' in text:
                text = text.replace('English', self.lang.name)
        # Format text
        text = text % self.params

        # Iterate until text fits into widget
        layout_width = self.width + pos_x + 1
        layout = None
        while layout_width + pos_x > self.width and font_size > 4:
            layout = self.get_text_layout(text, font_face, font_size)
            layout_width = layout.get_pixel_extents()[1][2]
            font_size -= 1

        # Set position
        self.context.move_to(pos_x, pos_y)

        # Render to cairo context
        self.pango_context.update_layout(layout)
        self.pango_context.show_layout(layout)

    def render_texts(self):
        '''
        Text rendering method to be overridden.
        '''
        raise NotImplementedError()

    def get_image(self):
        '''
        Returns PNG data.
        '''
        out = StringIO()
        self.surface.write_to_png(out)
        return out.getvalue()


class NormalWidget(Widget):
    name = '287x66'
    progress = {
        'x': 72,
        'y': 52,
        'height': 6,
        'width': 180,
        'horizontal': True,
    }

    def render_texts(self):
        self.render_text(
            '%(name)s',
            None,
            'Sans Bold', 10,
            72, 6
        )
        self.render_text(
            _(
                'translating %(count)d strings into %(languages)d languages\n'
                '%(percent)d%% complete, help us improve!'
            ),
            # Translators: please use your language name instead of English
            _('translating %(count)d strings into English\n%(percent)d%% complete, help us improve!'),
            'Sans', 8,
            72, 22
        )

register_widget(NormalWidget)


class SmallWidget(Widget):
    name = '88x31'

    def render_texts(self):
        self.render_text(
            '%(name)s',
            None,
            'Sans Bold', 7,
            23, 2
        )
        self.render_text(
            _('translation\n%(percent)d%% done'),
            # Translators: please use your language name instead of English
            _('English translation\n%(percent)d%% done'),
            'Sans', 7,
            23, 11
        )

register_widget(SmallWidget)
