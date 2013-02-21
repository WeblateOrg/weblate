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

from django.db import models
from weblate import appsettings
from django.core.cache import cache
from django.db.models import Q, Count
from django.utils import timezone
import itertools

from lang.models import Language
from trans.formats import ttkit

from whoosh import qparser

from trans.util import (
    msg_checksum, get_source, get_target, get_context,
    is_repo_link,
)

from trans.search import FULLTEXT_INDEX, SOURCE_SCHEMA, TARGET_SCHEMA
from trans.data import IGNORE_SIMILAR


class ProjectManager(models.Manager):
    def all_acl(self, user):
        '''
        Returns list of projects user is allowed to access.
        '''
        projects = self.all()
        project_ids = [
            project.id for project in projects if project.has_acl(user)
        ]
        if projects.count() == len(project_ids):
            return projects
        return self.filter(id__in=project_ids)


class SubProjectManager(models.Manager):
    def all_acl(self, user):
        '''
        Returns list of projects user is allowed to access.
        '''
        from trans.models import Project
        all_projects = Project.objects.all()
        projects = Project.objects.all_acl(user)
        if projects.count() == all_projects.count():
            return self.all()
        return self.filter(project__in=projects)

    def get_linked(self, val):
        '''
        Returns subproject for linked repo.
        '''
        if not is_repo_link(val):
            return None
        project, subproject = val[10:].split('/', 1)
        return self.get(slug=subproject, project__slug=project)


class TranslationManager(models.Manager):
    def update_from_blob(self, subproject, code, path, force=False,
                         request=None):
        '''
        Parses translation meta info and creates/updates translation object.
        '''
        lang = Language.objects.auto_get_or_create(code=code)
        translation, dummy = self.get_or_create(
            language=lang,
            language_code=code,
            subproject=subproject
        )
        if translation.filename != path:
            force = True
            translation.filename = path
        translation.update_from_blob(force, request=request)

        return translation

    def enabled(self):
        '''
        Filters enabled translations.
        '''
        return self.filter(enabled=True)

    def all_acl(self, user):
        '''
        Returns list of projects user is allowed to access.
        '''
        from trans.models import Project
        all_projects = Project.objects.all()
        projects = Project.objects.all_acl(user)
        if projects.count() == all_projects.count():
            return self.all()
        return self.filter(subproject__project__in=projects)


class UnitManager(models.Manager):
    def update_from_unit(self, translation, unit, pos, template=None):
        '''
        Process translation toolkit unit and stores/updates database entry.
        '''
        if template is None:
            src = get_source(unit)
            ctx = get_context(unit)
        else:
            src = get_target(template)
            ctx = get_context(template)
        checksum = msg_checksum(src, ctx)

        # Try getting existing unit
        from trans.models import Unit
        dbunit = None
        try:
            dbunit = self.get(
                translation=translation,
                checksum=checksum
            )
            force = False
        except Unit.MultipleObjectsReturned:
            # Some inconsistency (possibly race condition), try to recover
            self.filter(
                translation=translation,
                checksum=checksum
            ).delete()
        except Unit.DoesNotExist:
            pass

        # Create unit if it does not exist
        if dbunit is None:
            dbunit = Unit(
                translation=translation,
                checksum=checksum,
                source=src,
                context=ctx
            )
            force = True

        # Update all details
        dbunit.update_from_unit(unit, pos, force, template)

        # Return result
        return dbunit, force

    def filter_checks(self, rqtype, translation):
        '''
        Filtering for checks.
        '''
        from trans.checks import CHECKS
        from trans.models import Check

        # Filter checks for current project
        checks = Check.objects.filter(
            project=translation.subproject.project,
            ignore=False
        )

        filter_translated = True

        # Filter by language
        if rqtype == 'allchecks':
            checks = checks.filter(language=translation.language)
        elif rqtype == 'sourcechecks':
            checks = checks.filter(language=None)
            filter_translated = False
        elif CHECKS[rqtype].source and CHECKS[rqtype].target:
            checks = checks.filter(
                Q(language=translation.language) | Q(language=None)
            )
            filter_translated = False
        elif CHECKS[rqtype].source:
            checks = checks.filter(language=None)
            filter_translated = False
        elif CHECKS[rqtype].target:
            checks = checks.filter(language=translation.language)

        # Filter by check type
        if not rqtype in ['allchecks', 'sourcechecks']:
            checks = checks.filter(check=rqtype)

        checks = checks.values_list('checksum', flat=True)
        ret = self.filter(checksum__in=checks)
        if filter_translated:
            ret = ret.filter(translated=True)
        return ret

    def filter_type(self, rqtype, translation):
        '''
        Basic filtering based on unit state or failed checks.
        '''
        from trans.models import Suggestion, Comment
        from trans.checks import CHECKS

        if rqtype == 'fuzzy':
            return self.filter(fuzzy=True)
        elif rqtype == 'untranslated':
            return self.filter(translated=False)
        elif rqtype == 'suggestions':
            sugs = Suggestion.objects.filter(
                language=translation.language,
                project=translation.subproject.project
            )
            sugs = sugs.values_list('checksum', flat=True)
            return self.filter(checksum__in=sugs)
        elif rqtype == 'sourcecomments':
            coms = Comment.objects.filter(
                language=None,
                project=translation.subproject.project
            )
            coms = coms.values_list('checksum', flat=True)
            return self.filter(checksum__in=coms)
        elif rqtype == 'targetcomments':
            coms = Comment.objects.filter(
                language=translation.language,
                project=translation.subproject.project
            )
            coms = coms.values_list('checksum', flat=True)
            return self.filter(checksum__in=coms)
        elif rqtype in CHECKS or rqtype in ['allchecks', 'sourcechecks']:
            return self.filter_checks(rqtype, translation)
        else:
            # Catch anything not matching including 'all'
            return self.all()

    def count_type(self, rqtype, translation):
        '''
        Cached counting of failing checks (and other stats).
        '''
        # Use precalculated data if we can
        if rqtype == 'all':
            return translation.total
        elif rqtype == 'fuzzy':
            return translation.fuzzy
        elif rqtype == 'untranslated':
            return translation.total - translation.translated

        # Try to get value from cache
        cache_key = 'counts-%s-%s-%s' % (
            translation.subproject.get_full_slug(),
            translation.language.code,
            rqtype
        )
        ret = cache.get(cache_key)
        if ret is not None:
            return ret

        # Actually count units
        ret = self.filter_type(rqtype, translation).count()

        # Update cache
        cache.set(cache_key, ret)
        return ret

    def review(self, date, user):
        '''
        Returns units touched by other users since given time.
        '''
        if user.is_anonymous():
            return self.none()
        from trans.models import Change
        sample = self.all()[0]
        changes = Change.objects.filter(
            translation=sample.translation,
            timestamp__gte=date
        ).exclude(user=user)
        return self.filter(id__in=changes.values_list('unit__id', flat=True))

    def add_to_source_index(self, checksum, source, context, writer):
        '''
        Updates/Adds to source index given unit.
        '''
        writer.update_document(
            checksum=unicode(checksum),
            source=unicode(source),
            context=unicode(context),
        )

    def add_to_target_index(self, checksum, target, writer):
        '''
        Updates/Adds to target index given unit.
        '''
        writer.update_document(
            checksum=unicode(checksum),
            target=unicode(target),
        )

    def add_to_index(self, unit, source=True):
        '''
        Updates/Adds to all indices given unit.
        '''
        if appsettings.OFFLOAD_INDEXING:
            from trans.models import IndexUpdate
            IndexUpdate.objects.get_or_create(unit=unit, source=source)
            return

        writer_target = FULLTEXT_INDEX.target_writer(
            unit.translation.language.code
        )
        writer_source = FULLTEXT_INDEX.source_writer()

        if source:
            self.add_to_source_index(
                unit.checksum,
                unit.source,
                unit.context,
                writer_source)
        self.add_to_target_index(
            unit.checksum,
            unit.target,
            writer_target)

    def __search(self, searcher, field, schema, query):
        '''
        Wrapper for fulltext search.
        '''
        parser = qparser.QueryParser(field, schema)
        parsed = parser.parse(query)
        return [searcher.stored_fields(d)['checksum']
                for d in searcher.docs_for_query(parsed)]

    def search(self, query, source=True, context=True, translation=True,
               checksums=False):
        '''
        Performs full text search on defined set of fields.

        Returns queryset unless checksums is set.
        '''
        ret = set()

        # Search in source or context
        if source or context:
            index = FULLTEXT_INDEX.source_searcher(
                not appsettings.OFFLOAD_INDEXING
            )
            with index as searcher:
                if source:
                    results = self.__search(
                        searcher,
                        'source',
                        SOURCE_SCHEMA,
                        query
                    )
                    ret = ret.union(results)
                if context:
                    results = self.__search(
                        searcher,
                        'context',
                        SOURCE_SCHEMA,
                        query
                    )
                    ret = ret.union(results)

        # Search in target
        if translation:
            sample = self.all()[0]
            index = FULLTEXT_INDEX.target_searcher(
                sample.translation.language.code,
                not appsettings.OFFLOAD_INDEXING
            )
            with index as searcher:
                results = self.__search(
                    searcher,
                    'target',
                    TARGET_SCHEMA,
                    query
                )
                ret = ret.union(results)

        if checksums:
            return ret

        return self.filter(checksum__in=ret)

    def similar(self, unit):
        '''
        Finds similar units to current unit.
        '''
        ret = set([unit.checksum])
        index = FULLTEXT_INDEX.source_searcher(
            not appsettings.OFFLOAD_INDEXING
        )
        with index as searcher:
            # Extract up to 10 terms from the source
            key_terms = searcher.key_terms_from_text(
                'source',
                unit.source,
                numterms=10
            )
            terms = [kw[0] for kw in key_terms if not kw in IGNORE_SIMILAR]
            cnt = len(terms)
            # Try to find at least configured number of similar strings,
            # remove up to 4 words
            while (len(ret) < appsettings.SIMILAR_MESSAGES
                    and cnt > 0
                    and len(terms) - cnt < 4):
                for search in itertools.combinations(terms, cnt):
                    results = self.search(
                        ' '.join(search),
                        True,
                        False,
                        False,
                        True
                    )
                    ret = ret.union(results)
                cnt -= 1

        project = unit.translation.subproject.project
        return self.filter(
            translation__subproject__project=project,
            translation__language=unit.translation.language,
            checksum__in=ret
        ).exclude(
            target__in=['', unit.target]
        )

    def same(self, unit):
        '''
        Units with same source withing same project.
        '''
        project = unit.translation.subproject.project
        return self.filter(
            checksum=unit.checksum,
            translation__subproject__project=project,
            translation__language=unit.translation.language
        )


class DictionaryManager(models.Manager):
    def upload(self, project, language, fileobj, method):
        '''
        Handles dictionary update.
        '''
        ret = 0

        # Load file using ttkit
        store = ttkit(fileobj)

        # process all units
        for unit in store.units:
            # We care only about translated things
            if not unit.istranslatable() or not unit.istranslated():
                continue

            # Ignore too long words
            if len(unit.source) > 200 or len(unit.target) > 200:
                continue

            # Get object
            word, created = self.get_or_create(
                project=project,
                language=language,
                source=unit.source
            )

            # Already existing entry found
            if not created:
                # Same as current -> ignore
                if unit.target == word.target:
                    continue
                if method == 'add':
                    # Add word
                    word = self.create(
                        project=project,
                        language=language,
                        source=unit.source
                    )
                elif method != 'overwrite':
                    # No overwriting or adding
                    continue

            # Store word
            word.target = unit.target
            word.save()

            ret += 1

        return ret


class ChangeManager(models.Manager):
    def content(self):
        '''
        Retuns queryset with content changes.
        '''
        from trans.models import Change
        return self.filter(
            action__in=(Change.ACTION_CHANGE, Change.ACTION_NEW),
            user__isnull=False,
        )

    def count_stats(self, days, step, dtstart, base):
        '''
        Counts number of changes in given dataset and period groupped by
        step days.
        '''

        # Count number of changes
        result = []
        for dummy in xrange(0, days, step):
            # Calculate interval
            int_start = dtstart
            int_end = int_start + timezone.timedelta(days=step)

            # Count changes
            int_base = base.filter(timestamp__range=(int_start, int_end))
            count = int_base.aggregate(Count('id'))

            # Append to result
            result.append((int_start, count['id__count']))

            # Advance to next interval
            dtstart = int_end

        return result

    def base_stats(self, days, step,
                   project=None, subproject=None, translation=None,
                   language=None, user=None):
        '''
        Core of daily/weekly/monthly stats calculation.
        '''

        # Get range (actually start)
        dtend = timezone.now().date()
        dtstart = dtend - timezone.timedelta(days=days)

        # Base for filtering
        base = self.all()

        # Filter by translation/project
        if translation is not None:
            base = base.filter(translation=translation)
        elif subproject is not None:
            base = base.filter(translation__subproject=subproject)
        elif project is not None:
            base = base.filter(translation__subproject__project=project)

        # Filter by language
        if language is not None:
            base = base.filter(translation__language=language)

        # Filter by language
        if user is not None:
            base = base.filter(user=user)

        return self.count_stats(days, step, dtstart, base)

    def month_stats(self, *args, **kwargs):
        '''
        Reports daily stats for changes.
        '''
        return self.base_stats(30, 1, *args, **kwargs)

    def year_stats(self, *args, **kwargs):
        '''
        Reports monthly stats for changes.
        '''
        return self.base_stats(365, 7, *args, **kwargs)
