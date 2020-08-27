#
# Copyright © 2012 - 2020 Michal Čihař <michal@cihar.com>
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


import re
from functools import reduce
from itertools import islice

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils.translation import gettext_lazy
from whoosh.analysis import LanguageAnalyzer, NgramAnalyzer, SimpleAnalyzer
from whoosh.analysis.filters import StopFilter
from whoosh.lang import NoStopWords

from weblate.checks.same import strip_string
from weblate.formats.auto import AutodetectFormat
from weblate.lang.models import Language, get_english_lang
from weblate.trans.defines import GLOSSARY_LENGTH, PROJECT_NAME_LENGTH
from weblate.trans.models.project import Project
from weblate.utils.colors import COLOR_CHOICES
from weblate.utils.db import re_escape
from weblate.utils.decorators import disable_for_loaddata
from weblate.utils.errors import report_error

SPLIT_RE = re.compile(r"[\s,.:!?]+", re.UNICODE)


class GlossaryQuerySet(models.QuerySet):
    def for_project(self, project):
        return self.filter(Q(project=project) | Q(links=project))


class Glossary(models.Model):
    project = models.ForeignKey(Project, on_delete=models.deletion.CASCADE)
    links = models.ManyToManyField(
        Project,
        verbose_name=gettext_lazy("Additional projects"),
        blank=True,
        related_name="linked_glossaries",
        help_text=gettext_lazy(
            "Choose additional projects where this glossary can be used."
        ),
    )
    name = models.CharField(
        verbose_name=gettext_lazy("Glossary name"),
        max_length=PROJECT_NAME_LENGTH,
        unique=True,
    )
    color = models.CharField(
        verbose_name=gettext_lazy("Color"),
        max_length=30,
        choices=COLOR_CHOICES,
        blank=False,
        default=None,
    )
    source_language = models.ForeignKey(
        Language,
        verbose_name=gettext_lazy("Source language"),
        default=get_english_lang,
        on_delete=models.deletion.CASCADE,
    )

    objects = GlossaryQuerySet.as_manager()

    class Meta:
        verbose_name = "glossary"
        verbose_name_plural = "glossaries"

    def __str__(self):
        return self.name


class TermManager(models.Manager):
    # pylint: disable=no-init

    def upload(self, request, glossary, language, fileobj, method):
        """Handle glossary upload."""
        from weblate.trans.models.change import Change

        store = AutodetectFormat.parse(fileobj)

        ret = 0

        # process all units
        for _unused, unit in store.iterate_merge(False):
            source = unit.source
            target = unit.target

            # Ignore too long terms
            if len(source) > 190 or len(target) > 190:
                continue

            # Get object
            try:
                term, created = self.get_or_create(
                    glossary=glossary,
                    language=language,
                    source=source,
                    defaults={"target": target},
                )
            except Term.MultipleObjectsReturned:
                term = self.filter(glossary=glossary, language=language, source=source)[
                    0
                ]
                created = False

            # Already existing entry found
            if not created:
                # Same as current -> ignore
                if target == term.target:
                    continue
                if method == "add":
                    # Add term
                    self.create(
                        user=request.user,
                        action=Change.ACTION_DICTIONARY_UPLOAD,
                        glossary=glossary,
                        language=language,
                        source=source,
                        target=target,
                    )
                elif method == "overwrite":
                    # Update term
                    term.target = target
                    term.save()

            ret += 1

        return ret

    def create(self, user, **kwargs):
        """Create new glossary object."""
        from weblate.trans.models.change import Change

        action = kwargs.pop("action", Change.ACTION_DICTIONARY_NEW)
        created = super().create(**kwargs)
        Change.objects.create(
            action=action, glossary_term=created, user=user, target=created.target
        )
        return created


class TermQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def for_project(self, project, source_language):
        return self.filter(
            glossary__in=Glossary.objects.for_project(project).filter(
                source_language=source_language
            )
        )

    def get_terms(self, unit):
        """Return list of term pairs for an unit."""
        words = set()
        source_language = unit.translation.component.project.source_language

        # Filters stop words for a language
        try:
            stopfilter = StopFilter(lang=source_language.base_code)
        except NoStopWords:
            stopfilter = StopFilter()

        # Prepare analyzers
        # - basic simple analyzer to split on non-word chars
        # - simple analyzer just splits words based on regexp to catch in word dashes
        # - language analyzer if available (it is for English)
        analyzers = [
            SimpleAnalyzer() | stopfilter,
            SimpleAnalyzer(expression=SPLIT_RE, gaps=True) | stopfilter,
            LanguageAnalyzer(source_language.base_code),
        ]

        # Add ngram analyzer for languages like Chinese or Japanese
        if source_language.uses_ngram():
            analyzers.append(NgramAnalyzer(4))

        # Extract words from all plurals and from context
        flags = unit.all_flags
        for text in unit.get_source_plurals() + [unit.context]:
            text = strip_string(text, flags).lower()
            for analyzer in analyzers:
                # Some Whoosh analyzers break on unicode
                try:
                    words.update(token.text for token in analyzer(text))
                except (UnicodeDecodeError, IndexError):
                    report_error(cause="Term words parsing")
                if len(words) > 1000:
                    break
            if len(words) > 1000:
                break

        if "" in words:
            words.remove("")

        if not words:
            # No extracted words, no glossary
            return self.none()

        # Build the query for fetching the words
        # We want case insensitive lookup
        words = islice(words, 1000)
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
            # Use regex as that is utilizing pg_trgm index
            results = self.filter(
                source__iregex=r"(^|[ \t\n\r\f\v])({0})($|[ \t\n\r\f\v])".format(
                    "|".join(re_escape(word) for word in words)
                ),
            )
        else:
            # MySQL
            results = self.filter(
                reduce(
                    lambda x, y: x | y,
                    (models.Q(source__search=word) for word in words),
                ),
            )

        return results.for_project(
            unit.translation.component.project, source_language
        ).filter(language=unit.translation.language)

    def order(self):
        return self.order_by(Lower("source"))


class Term(models.Model):
    glossary = models.ForeignKey(
        Glossary,
        on_delete=models.deletion.CASCADE,
        verbose_name=gettext_lazy("Glossary"),
    )
    language = models.ForeignKey(Language, on_delete=models.deletion.CASCADE)
    source = models.CharField(
        max_length=GLOSSARY_LENGTH,
        db_index=True,
        verbose_name=gettext_lazy("Source"),
    )
    target = models.CharField(
        max_length=GLOSSARY_LENGTH,
        verbose_name=gettext_lazy("Translation"),
    )

    objects = TermManager.from_queryset(TermQuerySet)()

    class Meta:
        verbose_name = "glossary term"
        verbose_name_plural = "glossary terms"

    def __str__(self):
        return "{0}/{1}: {2} -> {3}".format(
            self.glossary, self.language, self.source, self.target
        )

    def get_absolute_url(self):
        return reverse("edit_glossary", kwargs={"pk": self.id})

    def get_parent_url(self):
        return reverse(
            "show_glossary",
            kwargs={"project": self.glossary.project.slug, "lang": self.language.code},
        )

    def edit(self, request, source, target, glossary):
        """Edit term in a glossary."""
        from weblate.trans.models.change import Change

        self.source = source
        self.target = target
        self.glossary = glossary
        self.save()
        Change.objects.create(
            action=Change.ACTION_DICTIONARY_EDIT,
            glossary_term=self,
            user=request.user,
            target=self.target,
        )

    def check_perm(self, user, perm):
        return user.has_perm(perm, self.glossary.project) or any(
            user.has_perm(perm, prj) for prj in self.glossary.links.iterator()
        )


@receiver(post_save, sender=Project)
@disable_for_loaddata
def create_glossary(sender, instance, created, **kwargs):
    """Creates glossary on project creation."""
    if created:
        Glossary.objects.create(
            name=instance.name,
            color="silver",
            project=instance,
            source_language=instance.source_language,
        )
