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

from __future__ import unicode_literals

from copy import copy
from glob import glob
import os
import time
import fnmatch
import re

from django.conf import settings
from django.db import models, transaction
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.encoding import python_2_unicode_compatible, force_text
from django.utils.functional import cached_property
from django.core.mail import mail_admins
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone

from weblate.formats import ParseError
from weblate.formats.models import FILE_FORMATS
from weblate.trans.mixins import URLMixin, PathMixin
from weblate.trans.fields import RegexField
from weblate.utils import messages
from weblate.utils.site import get_site_url
from weblate.utils.state import STATE_TRANSLATED, STATE_FUZZY
from weblate.utils.errors import report_error
from weblate.trans.util import (
    is_repo_link, cleanup_repo_url, cleanup_path, path_separator,
    PRIORITY_CHOICES,
)
from weblate.trans.signals import (
    vcs_post_push, vcs_post_update, translation_post_add
)
from weblate.vcs.base import RepositoryException
from weblate.vcs.models import VCS_REGISTRY
from weblate.utils.stats import ComponentStats
from weblate.trans.models.translation import Translation
from weblate.trans.validators import (
    validate_filemask, validate_autoaccept, validate_check_flags,
)
from weblate.lang.models import Language
from weblate.trans.models.change import Change
from weblate.utils.validators import validate_repoweb, validate_render


NEW_LANG_CHOICES = (
    ('contact', ugettext_lazy('Use contact form')),
    ('url', ugettext_lazy('Point to translation instructions URL')),
    ('add', ugettext_lazy('Automatically add language file')),
    ('none', ugettext_lazy('No adding of language')),
)
MERGE_CHOICES = (
    ('merge', ugettext_lazy('Merge')),
    ('rebase', ugettext_lazy('Rebase')),
)


def perform_on_link(func):
    """Decorator to handle repository link"""
    def on_link_wrapper(self, *args, **kwargs):
        if self.is_repo_link:
            # Call same method on linked component
            return getattr(self.linked_component, func.__name__)(
                *args, **kwargs
            )
        return func(self, *args, **kwargs)
    return on_link_wrapper


class ComponentQuerySet(models.QuerySet):
    # pylint: disable=no-init

    def prefetch(self):
        return self.select_related(
            'project'
        )

    def get_linked(self, val):
        """Return component for linked repo."""
        if not is_repo_link(val):
            return None
        project, component = val[10:].split('/', 1)
        return self.get(slug=component, project__slug=project)


@python_2_unicode_compatible
class Component(models.Model, URLMixin, PathMixin):
    name = models.CharField(
        verbose_name=ugettext_lazy('Component name'),
        max_length=settings.COMPONENT_NAME_LENGTH,
        help_text=ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        verbose_name=ugettext_lazy('URL slug'),
        max_length=settings.COMPONENT_NAME_LENGTH,
        help_text=ugettext_lazy('Name used in URLs and file names.')
    )
    project = models.ForeignKey(
        'Project',
        verbose_name=ugettext_lazy('Project'),
        on_delete=models.deletion.CASCADE,
    )
    vcs = models.CharField(
        verbose_name=ugettext_lazy('Version control system'),
        max_length=20,
        help_text=ugettext_lazy(
            'Version control system to use to access your '
            'repository with translations.'
        ),
        choices=VCS_REGISTRY.get_choices(),
        default=settings.DEFAULT_VCS,
    )
    repo = models.CharField(
        verbose_name=ugettext_lazy('Source code repository'),
        max_length=200,
        help_text=ugettext_lazy(
            'URL of a repository, use weblate://project/component '
            'for sharing with other component.'
        ),
    )
    linked_component = models.ForeignKey(
        'Component',
        verbose_name=ugettext_lazy('Project'),
        on_delete=models.deletion.CASCADE,
        null=True,
        editable=False,
    )
    push = models.CharField(
        verbose_name=ugettext_lazy('Repository push URL'),
        max_length=200,
        help_text=ugettext_lazy(
            'URL of a push repository, pushing is disabled if empty.'
        ),
        blank=True
    )
    repoweb = models.URLField(
        verbose_name=ugettext_lazy('Repository browser'),
        help_text=ugettext_lazy(
            'Link to repository browser, use %(branch)s for branch, '
            '%(file)s and %(line)s as filename and line placeholders.'
        ),
        validators=[validate_repoweb],
        blank=True,
    )
    git_export = models.CharField(
        verbose_name=ugettext_lazy('Exported repository URL'),
        max_length=200,
        help_text=ugettext_lazy(
            'URL of a repository where users can fetch changes from Weblate'
        ),
        blank=True
    )
    report_source_bugs = models.EmailField(
        verbose_name=ugettext_lazy('Source string bug report address'),
        help_text=ugettext_lazy(
            'Email address where errors in source string will be reported, '
            'keep empty for no emails.'
        ),
        max_length=254,
        blank=True,
    )
    branch = models.CharField(
        verbose_name=ugettext_lazy('Repository branch'),
        max_length=200,
        help_text=ugettext_lazy('Repository branch to translate'),
        default='',
        blank=True
    )
    filemask = models.CharField(
        verbose_name=ugettext_lazy('File mask'),
        max_length=200,
        validators=[validate_filemask],
        help_text=ugettext_lazy(
            'Path of files to translate relative to repository root,'
            ' use * instead of language code, '
            'for example: po/*.po or locale/*/LC_MESSAGES/django.po.'
        )
    )
    template = models.CharField(
        verbose_name=ugettext_lazy('Monolingual base language file'),
        max_length=200,
        blank=True,
        help_text=ugettext_lazy(
            'Filename of translations base file, which contains all strings '
            'and their source; this is recommended to use '
            'for monolingual translation formats.'
        )
    )
    edit_template = models.BooleanField(
        verbose_name=ugettext_lazy('Edit base file'),
        default=True,
        help_text=ugettext_lazy(
            'Whether users will be able to edit base file '
            'for monolingual translations.'
        )
    )
    new_base = models.CharField(
        verbose_name=ugettext_lazy('Base file for new translations'),
        max_length=200,
        blank=True,
        help_text=ugettext_lazy(
            'Filename of file used for creating new translations. '
            'For gettext choose .pot file.'
        )
    )
    file_format = models.CharField(
        verbose_name=ugettext_lazy('File format'),
        max_length=50,
        default='auto',
        choices=FILE_FORMATS.get_choices(),
        help_text=ugettext_lazy(
            'Automatic detection might fail for some formats '
            'and is slightly slower.'
        ),
    )

    locked = models.BooleanField(
        verbose_name=ugettext_lazy('Locked'),
        default=False,
        help_text=ugettext_lazy(
            'Whether component is locked for translation updates.'
        )
    )
    allow_translation_propagation = models.BooleanField(
        verbose_name=ugettext_lazy('Allow translation propagation'),
        default=settings.DEFAULT_TRANSLATION_PROPAGATION,
        db_index=True,
        help_text=ugettext_lazy(
            'Whether translation updates in other components '
            'will cause automatic translation in this one'
        )
    )
    save_history = models.BooleanField(
        verbose_name=ugettext_lazy('Save translation history'),
        default=True,
        help_text=ugettext_lazy(
            'Whether Weblate should keep history of translations'
        )
    )
    enable_suggestions = models.BooleanField(
        verbose_name=ugettext_lazy('Enable suggestions'),
        default=True,
        help_text=ugettext_lazy(
            'Whether to allow translation suggestions at all.'
        )
    )
    suggestion_voting = models.BooleanField(
        verbose_name=ugettext_lazy('Suggestion voting'),
        default=False,
        help_text=ugettext_lazy(
            'Whether users can vote for suggestions.'
        )
    )
    suggestion_autoaccept = models.PositiveSmallIntegerField(
        verbose_name=ugettext_lazy('Autoaccept suggestions'),
        default=0,
        help_text=ugettext_lazy(
            'Automatically accept suggestions with this number of votes,'
            ' use 0 to disable.'
        ),
        validators=[validate_autoaccept],
    )
    check_flags = models.TextField(
        verbose_name=ugettext_lazy('Quality checks flags'),
        default='',
        help_text=ugettext_lazy(
            'Additional comma-separated flags to influence quality checks, '
            'check documentation for possible values.'
        ),
        validators=[validate_check_flags],
        blank=True,
    )

    # Licensing
    license = models.CharField(
        verbose_name=ugettext_lazy('Translation license'),
        max_length=150,
        blank=True,
        default='',
        help_text=ugettext_lazy(
            'Optional short summary of license used for translations.'
        ),
    )
    license_url = models.URLField(
        verbose_name=ugettext_lazy('License URL'),
        blank=True,
        default='',
        help_text=ugettext_lazy('Optional URL with license details.'),
    )
    agreement = models.TextField(
        verbose_name=ugettext_lazy('Contributor agreement'),
        blank=True,
        default='',
        help_text=ugettext_lazy(
            'Agreement which needs to be approved before user can '
            'translate this component.'
        )
    )

    # Adding new language
    new_lang = models.CharField(
        verbose_name=ugettext_lazy('New translation'),
        max_length=10,
        choices=NEW_LANG_CHOICES,
        default='add',
        help_text=ugettext_lazy(
            'How to handle requests for creating new translations. '
            'Please note that availability of choices depends on '
            'the file format.'
        ),
    )

    # VCS config
    merge_style = models.CharField(
        verbose_name=ugettext_lazy('Merge style'),
        max_length=10,
        choices=MERGE_CHOICES,
        default='merge',
        help_text=ugettext_lazy(
            'Define whether Weblate should merge upstream repository '
            'or rebase changes onto it.'
        ),
    )
    commit_message = models.TextField(
        verbose_name=ugettext_lazy('Commit message when translating'),
        help_text=ugettext_lazy(
            'You can use template language for various information, '
            'please check documentation for more details.'
        ),
        validators=[validate_render],
        default=settings.DEFAULT_COMMIT_MESSAGE,
    )
    add_message = models.TextField(
        verbose_name=ugettext_lazy('Commit message when adding translation'),
        help_text=ugettext_lazy(
            'You can use template language for various information, '
            'please check documentation for more details.'
        ),
        validators=[validate_render],
        default=settings.DEFAULT_ADD_MESSAGE,
    )
    delete_message = models.TextField(
        verbose_name=ugettext_lazy('Commit message when removing translation'),
        help_text=ugettext_lazy(
            'You can use template language for various information, '
            'please check documentation for more details.'
        ),
        validators=[validate_render],
        default=settings.DEFAULT_DELETE_MESSAGE,
    )
    committer_name = models.CharField(
        verbose_name=ugettext_lazy('Committer name'),
        max_length=200,
        default=settings.DEFAULT_COMMITER_NAME,
    )
    committer_email = models.EmailField(
        verbose_name=ugettext_lazy('Committer email'),
        max_length=254,
        default=settings.DEFAULT_COMMITER_EMAIL,
    )
    push_on_commit = models.BooleanField(
        verbose_name=ugettext_lazy('Push on commit'),
        default=settings.DEFAULT_PUSH_ON_COMMIT,
        help_text=ugettext_lazy(
            'Whether the repository should be pushed upstream on every commit.'
        ),
    )
    commit_pending_age = models.IntegerField(
        verbose_name=ugettext_lazy('Age of changes to commit'),
        default=settings.COMMIT_PENDING_HOURS,
        help_text=ugettext_lazy(
            'Time in hours after which any pending changes will be '
            'committed to the VCS.'
        ),
    )

    language_regex = RegexField(
        verbose_name=ugettext_lazy('Language filter'),
        max_length=200,
        default='^[^.]+$',
        help_text=ugettext_lazy(
            'Regular expression which is used to filter '
            'translation when scanning for file mask.'
        ),
    )

    priority = models.IntegerField(
        default=100,
        choices=PRIORITY_CHOICES,
        verbose_name=_('Priority'),
        help_text=_(
            'Components with higher priority are offered first to translators.'
        ),
    )

    objects = ComponentQuerySet.as_manager()

    is_lockable = True
    _reverse_url_name = 'component'

    class Meta(object):
        ordering = ['priority', 'project__name', 'name']
        unique_together = (
            ('project', 'name'),
            ('project', 'slug'),
        )
        app_label = 'trans'
        verbose_name = ugettext_lazy('Component')
        verbose_name_plural = ugettext_lazy('Components')

    def __init__(self, *args, **kwargs):
        """Constructor to initialize some cache properties."""
        super(Component, self).__init__(*args, **kwargs)
        self._file_format = None
        self.stats = ComponentStats(self)
        self.addons_cache = {}
        self.needs_cleanup = False
        self.updated_sources = {}
        self.old_component = copy(self)

    @property
    def filemask_re(self):
        return re.compile(
            fnmatch.translate(self.filemask).replace('.*', '(.*)')
        )

    @cached_property
    def log_prefix(self):
        return '/'.join((self.project.slug, self.slug))

    def get_reverse_url_kwargs(self):
        """Return kwargs for URL reversing."""
        return {
            'project': self.project.slug,
            'component': self.slug
        }

    def get_widgets_url(self):
        """Return absolute URL for widgets."""
        return get_site_url(
            '{0}?component={1}'.format(
                reverse('widgets', kwargs={'project': self.project.slug}),
                self.slug,
            )
        )

    def get_share_url(self):
        """Return absolute URL usable for sharing."""
        return get_site_url(
            reverse('engage', kwargs={'project': self.project.slug})
        )

    def __str__(self):
        return '/'.join((force_text(self.project), self.name))

    @perform_on_link
    def _get_path(self):
        """Return full path to component VCS repository."""
        return os.path.join(self.project.full_path, self.slug)

    @perform_on_link
    def can_push(self):
        """Return true if push is possible for this component."""
        return self.push != '' and self.push is not None

    @property
    def is_repo_link(self):
        """Check whether repository is just a link for other one."""
        return is_repo_link(self.repo)

    def can_add_language(self):
        """Return true if new languages can be added."""
        return self.new_lang != 'none'

    @cached_property
    def repository(self):
        """Get VCS repository object."""
        if self.is_repo_link:
            return self.linked_component.repository
        repository = VCS_REGISTRY[self.vcs](
            self.full_path, self.branch, self
        )
        cache_key = 'sp-config-check-{}'.format(self.pk)
        if cache.get(cache_key) is None:
            with repository.lock:
                repository.check_config()
            cache.set(cache_key, True, 86400)

        return repository

    def get_last_remote_commit(self):
        """Return latest remote commit we know."""
        return self.repository.get_revision_info(
            self.repository.last_remote_revision
        )

    @perform_on_link
    def get_repo_url(self):
        """Return link to repository."""
        if not settings.HIDE_REPO_CREDENTIALS:
            return self.repo
        return cleanup_repo_url(self.repo)

    @perform_on_link
    def get_repo_branch(self):
        """Return branch in repository."""
        return self.branch

    @perform_on_link
    def get_export_url(self):
        """Return URL of exported VCS repository."""
        return self.git_export

    def get_repoweb_link(self, filename, line):
        """Generate link to source code browser for given file and line

        For linked repositories, it is possible to override linked
        repository path here.
        """
        if not self.repoweb:
            if self.is_repo_link:
                return self.linked_component.get_repoweb_link(filename, line)
            return None

        return self.repoweb % {
            'file': filename,
            '../file': filename.split('/', 1)[-1],
            '../../file': filename.split('/', 2)[-1],
            '../../../file': filename.split('/', 3)[-1],
            'line': line,
            'branch': self.branch
        }

    @perform_on_link
    def update_remote_branch(self, validate=False):
        """Pull from remote repository."""
        # Update
        self.log_info('updating repository')
        try:
            with self.repository.lock:
                start = time.time()
                self.repository.update_remote()
                timediff = time.time() - start
                self.log_info('update took %.2f seconds', timediff)
                for line in self.repository.last_output.splitlines():
                    self.log_debug('update: %s', line)
            return True
        except RepositoryException as error:
            error_text = force_text(error)
            self.log_error('failed to update repository: %s', error_text)
            if validate:
                if 'Host key verification failed' in error_text:
                    raise ValidationError({
                        'repo': _(
                            'Failed to verify SSH host key, please add '
                            'them in SSH page in the admin interface.'
                        )
                    })
                raise ValidationError({
                    'repo': _('Failed to fetch repository: %s') % error_text
                })
            return False

    def configure_repo(self, validate=False):
        """Ensure repository is correctly configured"""
        if self.is_repo_link:
            return

        with self.repository.lock:
            self.repository.configure_remote(self.repo, self.push, self.branch)
            self.repository.set_committer(
                self.committer_name,
                self.committer_email
            )

            self.update_remote_branch(validate)

    def configure_branch(self):
        """Ensure local tracking branch exists and is checkouted."""
        if self.is_repo_link:
            return

        with self.repository.lock:
            self.repository.configure_branch(self.branch)

    @perform_on_link
    def do_update(self, request=None, method=None):
        """Wrapper for doing repository update"""
        # Hold lock all time here to avoid somebody writing between commit
        # and merge/rebase.
        with self.repository.lock:
            # pull remote
            if not self.update_remote_branch():
                return False

            # do we have something to merge?
            try:
                needs_merge = self.repo_needs_merge()
            except RepositoryException:
                # Not yet configured repository
                needs_merge = True

            if not needs_merge and method != 'rebase':
                return True

            # commit possible pending changes
            self.commit_pending('update', request, skip_push=True)

            # update local branch
            ret = self.update_branch(request, method=method)

        # create translation objects for all files
        try:
            self.create_translations(request=request)
        except ParseError:
            ret = False

        # Push after possible merge
        if ret:
            self.push_if_needed(request, do_update=False)

        return ret

    def push_if_needed(self, request, do_update=True, on_commit=True):
        """Wrapper to push if needed

        Checks for:

        * Enabled push on commit
        * Configured push
        * There is something to push
        """
        if on_commit and not self.push_on_commit:
            return True
        if not self.can_push():
            return True
        if not self.repo_needs_push():
            return True
        return self.do_push(
            request, force_commit=False, do_update=do_update
        )

    @perform_on_link
    def do_push(self, request, force_commit=True, do_update=True):
        """Wrapper for pushing changes to remote repo."""
        # Do we have push configured
        if not self.can_push():
            messages.error(
                request,
                _('Push is disabled for %s.') % force_text(self)
            )
            return False

        # Commit any pending changes
        if force_commit:
            self.commit_pending('push', request, skip_push=True)

        # Do we have anything to push?
        if not self.repo_needs_push():
            return True

        if do_update:
            # Update the repo
            self.do_update(request)

            # Were all changes merged?
            if self.repo_needs_merge():
                return False

        # Do actual push
        try:
            self.log_info('pushing to remote repo')
            with self.repository.lock:
                self.repository.push()

            Change.objects.create(
                action=Change.ACTION_PUSH, component=self,
                user=request.user if request else None,
            )

            vcs_post_push.send(sender=self.__class__, component=self)
            for component in self.get_linked_childs():
                vcs_post_push.send(
                    sender=component.__class__, component=component
                )

            return True
        except RepositoryException as error:
            self.log_error('failed to push on repo: %s', error)
            msg = 'Error:\n{0}'.format(str(error))
            mail_admins(
                'failed push on repo {0}'.format(force_text(self)),
                msg
            )
            Change.objects.create(
                action=Change.ACTION_FAILED_PUSH, component=self,
                target=force_text(error),
                user=request.user if request else None,
            )
            messages.error(
                request,
                _('Failed to push to remote branch on %s.') %
                force_text(self)
            )
            return False

    @perform_on_link
    def do_reset(self, request=None):
        """Wrapper for reseting repo to same sources as remote."""
        # First check we're up to date
        self.update_remote_branch()

        # Do actual reset
        try:
            self.log_info('reseting to remote repo')
            with self.repository.lock:
                self.repository.reset()

            Change.objects.create(
                action=Change.ACTION_RESET, component=self,
                user=request.user if request else None,
            )
        except RepositoryException as error:
            self.log_error('failed to reset on repo')
            msg = 'Error:\n{0}'.format(str(error))
            mail_admins(
                'failed reset on repo {0}'.format(force_text(self)),
                msg
            )
            messages.error(
                request,
                _('Failed to reset to remote branch on %s.') %
                force_text(self)
            )
            return False

        # create translation objects for all files
        self.create_translations(request=request)

        return True

    @perform_on_link
    def do_cleanup(self, request=None):
        """Wrapper for cleaning up repo."""
        try:
            self.log_info('cleaning up the repo')
            with self.repository.lock:
                self.repository.cleanup()
        except RepositoryException as error:
            self.log_error('failed to clean the repo')
            msg = 'Error:\n{0}'.format(str(error))
            mail_admins(
                'failed clean the repo {0}'.format(force_text(self)),
                msg
            )
            messages.error(
                request,
                _('Failed to clean the repository on %s.') %
                force_text(self)
            )
            return False

        return True

    def get_repo_link_url(self):
        return 'weblate://{0}/{1}'.format(self.project.slug, self.slug)

    def get_linked_childs(self):
        """Return list of components which link repository to us."""
        return self.component_set.prefetch()

    def commit_pending(self, reason, request, from_link=False,
                       skip_push=False):
        """Check whether there is any translation which needs commit."""

        # If we're not recursing, call on parent
        if not from_link and self.is_repo_link:
            return self.linked_component.commit_pending(
                reason, request, True, skip_push=skip_push
            )

        # Commit all translations
        for translation in self.translation_set.all():
            translation.commit_pending(reason, request, skip_push=True)

        # Process linked projects
        for component in self.get_linked_childs():
            component.commit_pending(reason, request, True, skip_push=True)

        if not from_link and not skip_push:
            self.push_if_needed(request)

        return True

    def handle_parse_error(self, error, translation=None):
        """Handler for parse error."""
        report_error(error)
        if translation is None:
            filename = self.template
        else:
            filename = translation.filename
        from weblate.accounts.notifications import notify_parse_error
        notify_parse_error(
            self,
            translation,
            str(error),
            filename
        )
        if self.id:
            Change.objects.create(
                component=self,
                action=Change.ACTION_PARSE_ERROR,
            )
        raise ParseError(str(error))

    @perform_on_link
    def update_branch(self, request=None, method=None):
        """Update current branch to match remote (if possible)."""
        if method is None:
            method = self.merge_style

        # Merge/rebase
        if method == 'rebase':
            method = self.repository.rebase
            error_msg = _('Failed to rebase our branch onto remote branch %s.')
            action = Change.ACTION_REBASE
            action_failed = Change.ACTION_FAILED_REBASE
        else:
            method = self.repository.merge
            error_msg = _('Failed to merge remote branch into %s.')
            action = Change.ACTION_MERGE
            action_failed = Change.ACTION_FAILED_MERGE

        with self.repository.lock:
            try:
                previous_head = self.repository.last_revision
                # Try to merge it
                method()
                self.log_info(
                    '%s remote into repo',
                    self.merge_style,
                )
                if self.id:
                    Change.objects.create(
                        component=self, action=action,
                        user=request.user if request else None,
                    )

                    # run post update hook
                    vcs_post_update.send(
                        sender=self.__class__,
                        component=self,
                        previous_head=previous_head
                    )
                    for component in self.get_linked_childs():
                        vcs_post_update.send(
                            sender=component.__class__,
                            component=component,
                            previous_head=previous_head
                        )
                return True
            except RepositoryException as error:
                # In case merge has failer recover
                error = error.get_message()
                status = self.repository.status()

                # Log error
                self.log_error(
                    'failed %s on repo: %s',
                    self.merge_style,
                    error
                )
                if self.id:
                    Change.objects.create(
                        component=self, action=action_failed, target=error,
                        user=request.user if request else None,
                    )

                # Notify subscribers and admins
                from weblate.accounts.notifications import notify_merge_failure
                notify_merge_failure(self, error, status)

                # Reset repo back
                method(abort=True)

                # Tell user (if there is any)
                messages.error(
                    request,
                    error_msg % force_text(self)
                )

                return False

    def get_mask_matches(self):
        """Return files matching current mask."""
        prefix = path_separator(os.path.join(self.full_path, ''))
        matches = set()
        for filename in glob(os.path.join(self.full_path, self.filemask)):
            path = path_separator(filename).replace(prefix, '')
            code = self.get_lang_code(path)
            if re.match(self.language_regex, code):
                matches.add(path)
            else:
                self.log_info('skipping language %s [%s]', code, path)

        # We want to list template among translations as well
        if self.has_template():
            if self.edit_template:
                matches.add(self.template)
            else:
                matches.discard(self.template)

        # Remove symlinked translations
        for filename in list(matches):
            resolved = self.repository.resolve_symlinks(filename)
            if resolved != filename and resolved in matches:
                matches.discard(filename)

        return sorted(matches)

    def update_source_checks(self):
        for unit in self.updated_sources.values():
            unit.source_info.run_checks(unit)
        self.updated_sources = {}

    def create_translations(self, force=False, langs=None, request=None,
                            changed_template=False):
        """Load translations from VCS."""
        self.needs_cleanup = False
        self.updated_sources = {}
        translations = {}
        languages = {}
        matches = self.get_mask_matches()
        for pos, path in enumerate(matches):
            with transaction.atomic():
                code = self.get_lang_code(path)
                if langs is not None and code not in langs:
                    self.log_info('skipping %s', path)
                    continue

                self.log_info(
                    'checking %s (%s) [%d/%d]',
                    path,
                    code,
                    pos + 1,
                    len(matches)
                )
                lang = Language.objects.auto_get_or_create(code=code)
                if lang.code in languages:
                    self.log_error(
                        'duplicate language found: %s (%s, %s)',
                        lang.code, code, languages[lang.code]
                    )
                    continue
                translation = Translation.objects.check_sync(
                    self, lang, code, path, force, request=request
                )
                translations[translation.id] = translation
                languages[lang.code] = code
                # Remove fuzzy flag on template name change
                if changed_template:
                    translation.unit_set.filter(
                        state=STATE_FUZZY
                    ).update(
                        state=STATE_TRANSLATED
                    )

        # Delete possibly no longer existing translations
        if langs is None:
            todelete = self.translation_set.exclude(id__in=translations.keys())
            if todelete.exists():
                self.needs_cleanup = True
                with transaction.atomic():
                    self.log_info(
                        'removing stale translations: %s',
                        ','.join([trans.language.code for trans in todelete])
                    )
                    todelete.delete()

        if self.updated_sources:
            self.update_source_checks()

        # Process linked repos
        for component in self.get_linked_childs():
            self.log_info(
                'updating linked project %s',
                component
            )
            component.create_translations(force, langs, request=request)

        if self.needs_cleanup:
            from weblate.trans.tasks import cleanup_project
            cleanup_project.delay(self.project.pk)

        from weblate.accounts.notifications import notify_new_string
        # First invalidate all caches
        for translation in translations.values():
            translation.invalidate_cache()
        # Now send notifications to avoid calculating component stats
        # several times
        for translation in translations.values():
            if translation.notify_new_string:
                notify_new_string(translation)

        self.log_info('updating completed')

    def get_lang_code(self, path):
        """Parse language code from path."""
        # Parse filename
        matches = self.filemask_re.match(path)

        if not matches or not matches.lastindex:
            if path == self.template:
                return self.project.source_language.code
            return ''

        # Use longest matched code
        code = max(matches.groups(), key=len)

        # Remove possible encoding part
        if '.' in code and ('.utf' in code.lower() or '.iso' in code.lower()):
            return code.split('.')[0]
        return code

    def sync_git_repo(self, validate=False, skip_push=None):
        """Bring VCS repo in sync with current model."""
        if self.is_repo_link:
            return
        if skip_push is None:
            skip_push = validate
        self.configure_repo(validate)
        self.commit_pending('sync', None, skip_push=skip_push)
        self.configure_branch()
        self.update_branch()

    def set_default_branch(self):
        """Set default VCS branch if empty"""
        if self.branch == '':
            self.branch = VCS_REGISTRY[self.vcs].default_branch

    def clean_repo_link(self):
        """Validate repository link."""
        try:
            repo = Component.objects.get_linked(self.repo)
            if repo is not None and repo.is_repo_link:
                raise ValidationError(
                    {'repo': _(
                        'Invalid link to a Weblate project, '
                        'can not link to linked repository!'
                    )}
                )
            if repo.pk == self.pk:
                raise ValidationError(
                    {'repo': _(
                        'Invalid link to a Weblate project, '
                        'can not link to self!'
                    )}
                )
        except (Component.DoesNotExist, ValueError):
            raise ValidationError(
                {'repo': _(
                    'Invalid link to a Weblate project, '
                    'use weblate://project/component.'
                )}
            )
        if self.push != '':
            raise ValidationError(
                {'push': _('Push URL is not used when repository is linked!')}
            )
        if self.git_export != '':
            raise ValidationError(
                {
                    'git_export':
                        _('Export URL is not used when repository is linked!')
                }
            )
        self.linked_component = Component.objects.get_linked(self.repo)

    def clean_lang_codes(self, matches):
        """Validate that there are no double language codes"""
        if not matches and not self.can_add_new_language():
            raise ValidationError(
                {'filemask': _('The mask did not match any files!')}
            )
        langs = set()
        translated_langs = set()
        for match in matches:
            code = self.get_lang_code(match)
            if not code:
                raise ValidationError({'filemask': _(
                    'Got empty language code for %s, please check filemask!'
                ) % match})
            lang = Language.objects.auto_get_or_create(code, create=False)
            if lang.pk and len(code) > 20:
                raise ValidationError({'filemask': _(
                    'Language code "%s" is too long, please check filemask!'
                ) % code})
            if code in langs:
                raise ValidationError(_(
                    'There are more files for single language (%s), please '
                    'adjust the mask and use components for translating '
                    'different resources.'
                ) % code)
            if lang.code in translated_langs:
                raise ValidationError(_(
                    'Multiple translations were mapped to a single language '
                    'code (%s). You should disable SIMPLIFY_LANGUAGES '
                    'to prevent Weblate mapping similar languages to one.'
                ) % lang.code)
            langs.add(code)
            translated_langs.add(lang.code)

    def clean_files(self, matches):
        """Validate whether we can parse translation files."""
        notrecognized = []
        errors = []
        dir_path = self.full_path
        for match in matches:
            try:
                parsed = self.file_format_cls.parse(
                    os.path.join(dir_path, match),
                )
                if not self.file_format_cls.is_valid(parsed.store):
                    errors.append('{0}: {1}'.format(
                        match, _('File does not seem to be valid!')
                    ))
            except ValueError:
                notrecognized.append(match)
            except Exception as error:
                errors.append('{0}: {1}'.format(match, str(error)))
        if notrecognized:
            msg = (
                _('Format of %d matched files could not be recognized.') %
                len(notrecognized)
            )
            raise ValidationError('{0}\n{1}'.format(
                msg,
                '\n'.join(notrecognized)
            ))
        if errors:
            raise ValidationError('{0}\n{1}'.format(
                (_('Failed to parse %d matched files!') % len(errors)),
                '\n'.join(errors)
            ))

    def is_valid_base_for_new(self):
        filename = self.get_new_base_filename()
        template = self.has_template()
        return self.file_format_cls.is_valid_base_for_new(filename, template)

    def clean_new_lang(self):
        """Validate new language choices."""
        if self.new_lang == 'add':
            if not self.is_valid_base_for_new():
                filename = self.get_new_base_filename()
                if filename:
                    message = _(
                        'Format of base file for new translations '
                        'was not recognized!'
                    )
                else:
                    message = _(
                        'You have configured Weblate to add new translation '
                        'files, but did not provide base file to do that!'
                    )
                raise ValidationError({'new_base': message})
        elif self.new_lang != 'add' and self.new_base:
            msg = _(
                'Base file for new translations is not used because of '
                'component settings. '
                'You probably want to enable automatic adding of new '
                'translations.'
            )
            raise ValidationError({'new_lang': msg, 'new_base': msg})

    def clean_template(self):
        """Validate template value."""
        # Test for unexpected template usage
        if self.template != '' and self.file_format_cls.monolingual is False:
            msg = _('You can not use base file with bilingual translation!')
            raise ValidationError({'template': msg, 'file_format': msg})

        # Special case for Gettext
        if self.template.endswith('.pot') and self.filemask.endswith('.po'):
            msg = _('Using .pot file as base file is not supported!')
            raise ValidationError({'template': msg})

        # Validate template loading
        if self.has_template():
            full_path = os.path.join(self.full_path, self.template)
            if not os.path.exists(full_path):
                msg = _('Template file not found!')
                raise ValidationError({'template': msg})

            try:
                self.template_store
            except ParseError as exc:
                msg = _('Failed to parse translation base file: %s') % str(exc)
                raise ValidationError({'template': msg})

            code = self.get_lang_code(self.template)
            if code:
                lang = Language.objects.auto_get_or_create(
                    code=code
                ).base_code
                if lang != self.project.source_language.base_code:
                    msg = _(
                        'Template language ({0}) does not '
                        'match project source language ({1})!'
                    ).format(code, self.project.source_language.code)
                    raise ValidationError({'template': msg})

        elif self.file_format_cls.monolingual:
            msg = _(
                'You can not use monolingual translation without base file!'
            )
            raise ValidationError({'template': msg})

    def clean(self):
        """Validator fetches repository

        It tries to find translation files and it checks them for validity.
        """
        if self.new_lang == 'url' and self.project.instructions == '':
            msg = _(
                'Please either fill in instructions URL '
                'or use different option for adding new language.'
            )
            raise ValidationError({'new_lang': msg})

        if self.license == '' and self.license_url != '':
            msg = _(
                'License URL can not be used without license summary.'
            )
            raise ValidationError({'license_url': msg, 'license': msg})

        # Skip validation if we don't have valid project
        if self.project_id is None:
            return

        self.set_default_branch()

        # Check if we should rename
        if self.id:
            old = Component.objects.get(pk=self.id)
            self.check_rename(old)

            if old.vcs != self.vcs:
                # This could work, but the problem is that before changed
                # object is saved the linked repos still see old vcs leading
                # to horrible mess. Changing vcs from the manage.py shell
                # works fine though.
                msg = _('Changing version control system is not supported!')
                raise ValidationError({'vcs': msg})

        # Check file format
        if self.file_format not in FILE_FORMATS:
            msg = _('Unsupported file format: {0}').format(self.file_format)
            raise ValidationError({'file_format': msg})

        # Baild out on failed repo validation
        if self.repo is None:
            return

        # Validate VCS repo
        try:
            self.sync_git_repo(True)
        except RepositoryException as exc:
            msg = _('Failed to update repository: %s') % exc
            raise ValidationError({'repo': msg})

        # Push repo is not used with link
        if self.is_repo_link:
            self.clean_repo_link()

        # Template validation
        self.clean_template()

        try:
            matches = self.get_mask_matches()

            # Verify language codes
            self.clean_lang_codes(matches)

            # Try parsing files
            self.clean_files(matches)
        except re.error:
            raise ValidationError(_(
                'Can not validate file matches due to invalid '
                'regular expression.'
            ))

        # New language options
        self.clean_new_lang()

        # Suggestions
        if (hasattr(self, 'suggestion_autoaccept') and
                self.suggestion_autoaccept and
                not self.suggestion_voting):
            msg = _(
                'Automatically accepting suggestions can work only with '
                'voting enabled!'
            )
            raise ValidationError(
                {'suggestion_autoaccept': msg, 'suggestion_voting': msg}
            )

    def get_template_filename(self):
        """Create absolute filename for template."""
        return os.path.join(self.full_path, self.template)

    def get_new_base_filename(self):
        """Create absolute filename for base file for new translations."""
        if not self.new_base:
            return None
        return os.path.join(self.full_path, self.new_base)

    def save(self, *args, **kwargs):
        """Save wrapper

        It updates backend repository and regenerates translation data.
        """
        self.set_default_branch()

        # Linked component cache
        self.linked_component = Component.objects.get_linked(self.repo)

        # Detect if VCS config has changed (so that we have to pull the repo)
        changed_git = True
        changed_setup = False
        changed_template = False
        changed_project = False
        if self.id:
            old = Component.objects.get(pk=self.id)
            changed_git = (
                (old.repo != self.repo) or
                (old.branch != self.branch) or
                (old.filemask != self.filemask) or
                (old.language_regex != self.language_regex)
            )
            changed_setup = (
                (old.file_format != self.file_format) or
                (old.edit_template != self.edit_template) or
                (old.template != self.template)
            )
            changed_template = (
                (old.edit_template != self.edit_template) and
                self.template
            )
            changed_project = (old.project_id != self.project_id)
            # Detect slug changes and rename git repo
            self.check_rename(old)
            # Rename linked repos
            if old.slug != self.slug:
                old.component_set.update(repo=self.get_repo_link_url())

        # Remove leading ./ from paths
        self.filemask = cleanup_path(self.filemask)
        self.template = cleanup_path(self.template)

        # Save/Create object
        super(Component, self).save(*args, **kwargs)

        # Configure git repo if there were changes
        if changed_git:
            self.sync_git_repo(skip_push=kwargs.get('force_insert', False))

        # Rescan for possibly new translations if there were changes, needs to
        # be done after actual creating the object above
        if changed_setup:
            self.create_translations(
                force=True,
                changed_template=changed_template
            )
        elif changed_git:
            self.create_translations()

        # Copy suggestions to new project
        if changed_project:
            old.project.suggestion_set.copy(self.project)

    def repo_needs_commit(self):
        """Check whether there are some not committed changes"""
        for translation in self.translation_set.all():
            if translation.unit_set.filter(pending=True).exists():
                return True
        return self.repository.needs_commit()

    def repo_needs_merge(self):
        """Check whether there is something to merge from remote repository"""
        return self.repository.needs_merge()

    def repo_needs_push(self):
        """Check whether there is something to push to remote repository"""
        return self.repository.needs_push()

    @property
    def file_format_name(self):
        return self.file_format_cls.name

    @property
    def file_format_cls(self):
        """Return file format object """
        if (self._file_format is None or
                self._file_format.name != self.file_format):
            self._file_format = FILE_FORMATS[self.file_format]
        return self._file_format

    def has_template(self):
        """Return true if component is using template for translation"""
        monolingual = self.file_format_cls.monolingual
        return ((monolingual or monolingual is None) and self.template)

    def load_template_store(self):
        """Load translate-toolkit store for template."""
        return self.file_format_cls.parse(
            self.get_template_filename(),
        )

    @cached_property
    def template_store(self):
        """Get translate-toolkit store for template."""
        # Do we need template?
        if not self.has_template():
            return None

        try:
            return self.load_template_store()
        except Exception as exc:
            self.handle_parse_error(exc)

    @cached_property
    def all_flags(self):
        """Return parsed list of flags."""
        return (
            self.check_flags.split(',') +
            list(self.file_format_cls.check_flags)
        )

    def can_add_new_language(self):
        """Wrapper to check if we can add new language."""
        if self.new_lang != 'add':
            return False

        return self.is_valid_base_for_new()

    def add_new_language(self, language, request, send_signal=True):
        """Create new language file."""
        if not self.can_add_new_language():
            if request:
                messages.error(
                    request,
                    _('Failed to add new translation file!')
                )
            return False

        format_lang_code = self.file_format_cls.get_language_code(
            language.code
        )
        if re.match(self.language_regex, format_lang_code) is None:
            if request:
                messages.error(
                    request,
                    _('Given language is filtered by the language filter!')
                )
            return False

        base_filename = self.get_new_base_filename()

        filename = self.file_format_cls.get_language_filename(
            self.filemask,
            language.code
        )
        fullname = os.path.join(self.full_path, filename)

        # Ignore request if file exists (possibly race condition as
        # the processing of new language can take some time and user
        # can submit again)
        if os.path.exists(fullname):
            if request:
                translation = Translation.objects.check_sync(
                    self, language, language.code, filename, request=request
                )
                translation.invalidate_cache()
                messages.error(
                    request,
                    _('Translation file already exists!')
                )
            return False

        self.file_format_cls.add_language(
            fullname,
            language,
            base_filename
        )

        translation = Translation.objects.create(
            component=self,
            language=language,
            plural=language.plural,
            filename=filename,
            language_code=language.code,
        )
        if send_signal:
            translation_post_add.send(
                sender=self.__class__,
                translation=translation
            )
        translation.commit_template = 'add'
        translation.git_commit(
            request,
            request.user.get_author_name()
            if request else 'Weblate <noreply@weblate.org>',
            timezone.now(),
            force_new=True,
        )
        translation.check_sync(
            force=True,
            request=request
        )
        translation.invalidate_cache()
        return True

    def do_lock(self, user, lock=True):
        """Lock or unlock component."""
        self.locked = lock
        self.save(update_fields=['locked'])
        Change.objects.create(
            component=self,
            user=user,
            action=Change.ACTION_LOCK if lock else Change.ACTION_UNLOCK,
        )

    def get_editable_template(self):
        if not self.edit_template or not self.has_template():
            return None
        return self.translation_set.get(filename=self.template)
