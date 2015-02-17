# -*- coding: utf-8 -*-
#
# Copyright © 2012 - 2015 Michal Čihař <michal@cihar.com>
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
from django.utils.translation import ugettext as _, ugettext_lazy
from django.core.mail import mail_admins
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.core.urlresolvers import reverse
from django.core.cache import cache
from django.utils import timezone
from glob import glob
import os
import time
from weblate.trans.formats import FILE_FORMAT_CHOICES, FILE_FORMATS
from weblate.trans.mixins import PercentMixin, URLMixin, PathMixin
from weblate.trans.filelock import FileLock
from weblate.trans.util import is_repo_link, get_site_url, cleanup_repo_url
from weblate.trans.vcs import RepositoryException, VCS_REGISTRY, VCS_CHOICES
from weblate.trans.models.translation import Translation
from weblate.trans.validators import (
    validate_repoweb, validate_filemask,
    validate_extra_file, validate_autoaccept,
    validate_check_flags, validate_commit_message,
)
from weblate.lang.models import Language
from weblate.appsettings import SCRIPT_CHOICES, HIDE_REPO_CREDENTIALS
from weblate.accounts.models import notify_merge_failure
from weblate.trans.models.changes import Change


DEFAULT_COMMIT_MESSAGE = (
    'Translated using Weblate (%(language_name)s)\n\n'
    'Currently translated at %(translated_percent)s%% '
    '(%(translated)s of %(total)s strings)'
)

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


class SubProjectManager(models.Manager):
    # pylint: disable=W0232

    def get_linked(self, val):
        '''
        Returns subproject for linked repo.
        '''
        if not is_repo_link(val):
            return None
        project, subproject = val[10:].split('/', 1)
        return self.get(slug=subproject, project__slug=project)


class SubProject(models.Model, PercentMixin, URLMixin, PathMixin):
    name = models.CharField(
        verbose_name=ugettext_lazy('Component name'),
        max_length=100,
        help_text=ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        verbose_name=ugettext_lazy('URL slug'),
        db_index=True,
        help_text=ugettext_lazy('Name used in URLs and file names.')
    )
    project = models.ForeignKey(
        'Project',
        verbose_name=ugettext_lazy('Project'),
    )
    vcs = models.CharField(
        verbose_name=ugettext_lazy('Version control system'),
        max_length=20,
        help_text=ugettext_lazy(
            'Version control system to use to access your '
            'repository with translations.'
        ),
        choices=VCS_CHOICES,
        default='git',
    )
    repo = models.CharField(
        verbose_name=ugettext_lazy('Source code repository'),
        max_length=200,
        help_text=ugettext_lazy(
            'URL of a repository, use weblate://project/component '
            'for sharing with other component.'
        ),
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
        max_length=50,
        help_text=ugettext_lazy('Repository branch to translate'),
        default='master'
    )
    filemask = models.CharField(
        verbose_name=ugettext_lazy('File mask'),
        max_length=200,
        validators=[validate_filemask],
        help_text=ugettext_lazy(
            'Path of files to translate, use * instead of language code, '
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
    new_base = models.CharField(
        verbose_name=ugettext_lazy('Base file for new translations'),
        max_length=200,
        blank=True,
        help_text=ugettext_lazy(
            'Filename of file which is used for creating new translations. '
            'For Gettext choose .pot file.'
        )
    )
    file_format = models.CharField(
        verbose_name=ugettext_lazy('File format'),
        max_length=50,
        default='auto',
        choices=FILE_FORMAT_CHOICES,
        help_text=ugettext_lazy(
            'Automatic detection might fail for some formats '
            'and is slightly slower.'
        ),
    )
    extra_commit_file = models.CharField(
        verbose_name=ugettext_lazy('Additional commit file'),
        max_length=200,
        default='',
        blank=True,
        validators=[validate_extra_file],
        help_text=ugettext_lazy(
            'Additional file to include in commits; please check '
            'documentation for more details.',
        )
    )
    pre_commit_script = models.CharField(
        verbose_name=ugettext_lazy('Pre-commit script'),
        max_length=200,
        default='',
        blank=True,
        choices=SCRIPT_CHOICES,
        help_text=ugettext_lazy(
            'Script to be executed before committing translation, '
            'please check documentation for more details.'
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
        default=True,
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

    # Adding new language
    new_lang = models.CharField(
        verbose_name=ugettext_lazy('New language'),
        max_length=10,
        choices=NEW_LANG_CHOICES,
        default='contact',
        help_text=ugettext_lazy(
            'How to handle requests for creating new languages.'
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
        verbose_name=ugettext_lazy('Commit message'),
        help_text=ugettext_lazy(
            'You can use format strings for various information, '
            'please check documentation for more details.'
        ),
        validators=[validate_commit_message],
        default=DEFAULT_COMMIT_MESSAGE,
    )
    committer_name = models.CharField(
        verbose_name=ugettext_lazy('Committer name'),
        max_length=200,
        default='Weblate'
    )
    committer_email = models.EmailField(
        verbose_name=ugettext_lazy('Committer email'),
        max_length=254,
        default='noreply@weblate.org'
    )

    objects = SubProjectManager()

    is_lockable = True

    class Meta(object):
        ordering = ['project__name', 'name']
        unique_together = (
            ('project', 'name'),
            ('project', 'slug'),
        )
        permissions = (
            ('lock_subproject', "Can lock translation for translating"),
            ('can_see_git_repository', "Can see VCS repository URL"),
        )
        app_label = 'trans'

    def __init__(self, *args, **kwargs):
        '''
        Constructor to initialize some cache properties.
        '''
        super(SubProject, self).__init__(*args, **kwargs)
        self._repository_lock = None
        self._file_format = None
        self._template_store = None
        self._all_flags = None
        self._linked_subproject = None
        self._repository = None

    @property
    def log_prefix(self):
        return '{0}/{1}: '.format(self.project.slug, self.slug)

    def has_acl(self, user):
        '''
        Checks whether current user is allowed to access this
        subproject.
        '''
        return self.project.has_acl(user)

    def check_acl(self, request):
        '''
        Raises an error if user is not allowed to access this project.
        '''
        self.project.check_acl(request)

    def _reverse_url_name(self):
        '''
        Returns base name for URL reversing.
        '''
        return 'subproject'

    def _reverse_url_kwargs(self):
        '''
        Returns kwargs for URL reversing.
        '''
        return {
            'project': self.project.slug,
            'subproject': self.slug
        }

    def get_widgets_url(self):
        '''
        Returns absolute URL for widgets.
        '''
        return get_site_url(
            reverse('widgets', kwargs={'project': self.project.slug})
        )

    def get_share_url(self):
        '''
        Returns absolute URL usable for sharing.
        '''
        return get_site_url(
            reverse('engage', kwargs={'project': self.project.slug})
        )

    def __unicode__(self):
        return '%s/%s' % (self.project.__unicode__(), self.name)

    def get_full_slug(self):
        return '%s__%s' % (self.project.slug, self.slug)

    def _get_path(self):
        '''
        Returns full path to subproject VCS repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.get_path()
        else:
            return os.path.join(self.project.get_path(), self.slug)

    @property
    def repository_lock(self):
        '''
        Returns lock object for current translation instance.
        '''
        if self.is_repo_link:
            return self.linked_subproject.repository_lock

        if self._repository_lock is None:
            lock_path = os.path.join(
                self.project.get_path(),
                self.slug + '.lock'
            )
            self._repository_lock = FileLock(
                lock_path,
                timeout=30
            )
        return self._repository_lock

    def can_push(self):
        '''
        Returns true if push is possible for this subproject.
        '''
        if self.is_repo_link:
            return self.linked_subproject.can_push()
        return self.push != '' and self.push is not None

    @property
    def is_repo_link(self):
        '''
        Checks whether repository is just a link for other one.
        '''
        return is_repo_link(self.repo)

    def can_add_language(self):
        '''
        Returns true if new languages can be added.
        '''
        return self.new_lang != 'none'

    @property
    def linked_subproject(self):
        '''
        Returns subproject for linked repo.
        '''
        if self._linked_subproject is None:
            self._linked_subproject = SubProject.objects.get_linked(self.repo)
        return self._linked_subproject

    @property
    def repository(self):
        """
        VCS repository object.
        """
        if self.is_repo_link:
            return self.linked_subproject.repository

        if self._repository is None:
            self._repository = VCS_REGISTRY[self.vcs](self.get_path())
            cache_key = '{0}-config-check'.format(self.get_full_slug())
            if cache.get(cache_key) is None:
                self._repository.check_config()
                cache.set(cache_key, True)

        return self._repository

    def clear_repo_cache(self):
        """
        Clears cached information on repository update.
        """
        cache.delete(
            '{0}-last-commit'.format(self.get_full_slug())
        )

    def get_last_remote_commit(self):
        '''
        Returns latest remote commit we know.
        '''
        cache_key = '{0}-last-commit'.format(self.get_full_slug())

        result = cache.get(cache_key)

        if result is None:
            result = self.repository.get_revision_info(
                self.repository.last_remote_revision
            )
            cache.set(cache_key, result)
        return result

    def get_repo_url(self):
        '''
        Returns link to repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.get_repo_url()
        if not HIDE_REPO_CREDENTIALS:
            return self.repo
        return cleanup_repo_url(self.repo)

    def get_repo_branch(self):
        '''
        Returns branch in repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.branch
        return self.branch

    def get_export_url(self):
        '''
        Returns URL of exported VCS repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.git_export
        return self.git_export

    def get_repoweb_link(self, filename, line):
        '''
        Generates link to source code browser for given file and line.

        For linked repositories, it is possible to override linked
        repository path here.
        '''
        if len(self.repoweb) == 0:
            if self.is_repo_link:
                return self.linked_subproject.get_repoweb_link(filename, line)
            return None

        return self.repoweb % {
            'file': filename,
            'line': line,
            'branch': self.branch
        }

    def update_remote_branch(self, validate=False):
        '''
        Pulls from remote repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.update_remote_branch(validate)

        # Update
        self.log_info('updating repository')
        try:
            with self.repository_lock:
                start = time.time()
                self.repository.update_remote()
                timediff = time.time() - start
                self.log_info('update took %.2f seconds:', timediff)
                for line in self.repository.last_output.splitlines():
                    self.log_debug('update: %s', line)
        except RepositoryException as error:
            error_text = str(error)
            self.log_error('failed to update repository: %s', error_text)
            if validate:
                if 'Host key verification failed' in error_text:
                    raise ValidationError(_(
                        'Failed to verify SSH host key, please add '
                        'them in SSH page in the admin interface.'
                    ))
                raise ValidationError(
                    _('Failed to fetch repository: %s') % error_text
                )

    def configure_repo(self, validate=False):
        '''
        Ensures repository is correctly configured and points to current
        remote.
        '''
        if self.is_repo_link:
            return self.linked_subproject.configure_repo(validate)

        self.repository.configure_remote(self.repo, self.push, self.branch)
        self.repository.set_committer(
            self.committer_name,
            self.committer_email
        )

        self.update_remote_branch(validate)

    def configure_branch(self):
        '''
        Ensures local tracking branch exists and is checkouted.
        '''
        if self.is_repo_link:
            return self.linked_subproject.configure_branch()

        self.repository.configure_branch(self.branch)

    def do_update(self, request=None, method=None):
        '''
        Wrapper for doing repository update and pushing them to translations.
        '''
        if self.is_repo_link:
            return self.linked_subproject.do_update(request)

        # pull remote
        self.update_remote_branch()

        # do we have something to merge?
        if not self.git_needs_merge() and method != 'rebase':
            return True

        # commit possible pending changes
        self.commit_pending(request)

        # update remote branch
        ret = self.update_branch(request, method=method)

        # create translation objects for all files
        self.create_translations(request=request)

        # Push after possible merge
        if (self.git_needs_push() and
                ret and
                self.project.push_on_commit and
                self.can_push()):
            self.do_push(request, force_commit=False, do_update=False)

        return ret

    def do_push(self, request, force_commit=True, do_update=True):
        '''
        Wrapper for pushing changes to remote repo.
        '''
        if self.is_repo_link:
            return self.linked_subproject.do_push(request)

        # Do we have push configured
        if not self.can_push():
            if request is not None:
                messages.error(
                    request,
                    _('Push is disabled for %s.') % self.__unicode__()
                )
            return False

        # Commit any pending changes
        if force_commit:
            self.commit_pending(request, skip_push=True)

        # Do we have anything to push?
        if not self.git_needs_push():
            return False

        if do_update:
            # Update the repo
            self.do_update(request)

            # Were all changes merged?
            if self.git_needs_merge():
                return False

        # Do actual push
        try:
            self.log_info('pushing to remote repo')
            with self.repository_lock:
                self.repository.push(self.branch)
            return True
        except RepositoryException as error:
            self.log_error('failed to push on repo: %s', error)
            msg = 'Error:\n%s' % str(error)
            mail_admins(
                'failed push on repo %s' % self.__unicode__(),
                msg
            )
            if request is not None:
                messages.error(
                    request,
                    _('Failed to push to remote branch on %s.') %
                    self.__unicode__()
                )
            return False

    def do_reset(self, request=None):
        '''
        Wrapper for reseting repo to same sources as remote.
        '''
        if self.is_repo_link:
            return self.linked_subproject.do_reset(request)

        # First check we're up to date
        self.update_remote_branch()

        # Do actual reset
        try:
            self.log_info('reseting to remote repo')
            with self.repository_lock:
                self.repository.reset(self.branch)
        except RepositoryException as error:
            self.log_error('failed to reset on repo')
            msg = 'Error:\n%s' % str(error)
            mail_admins(
                'failed reset on repo %s' % self.__unicode__(),
                msg
            )
            if request is not None:
                messages.error(
                    request,
                    _('Failed to reset to remote branch on %s.') %
                    self.__unicode__()
                )
            return False

        # create translation objects for all files
        self.create_translations(request=request)

        return True

    def get_linked_childs(self):
        '''
        Returns list of subprojects which link repository to us.
        '''
        return SubProject.objects.filter(
            repo='weblate://%s/%s' % (self.project.slug, self.slug)
        )

    def commit_pending(self, request, from_link=False, skip_push=False):
        '''
        Checks whether there is any translation which needs commit.
        '''
        if not from_link and self.is_repo_link:
            return self.linked_subproject.commit_pending(
                request, True, skip_push=skip_push
            )

        for translation in self.translation_set.all():
            translation.commit_pending(request, skip_push=skip_push)

        # Process linked projects
        for subproject in self.get_linked_childs():
            subproject.commit_pending(request, True, skip_push=skip_push)

    def notify_merge_failure(self, error, status):
        '''
        Sends out notifications on merge failure.
        '''
        # Notify subscribed users about failure
        notify_merge_failure(self, error, status)

    def update_branch(self, request=None, method=None):
        '''
        Updates current branch to match remote (if possible).
        '''
        if self.is_repo_link:
            return self.linked_subproject.update_branch(request)

        if method is None:
            method = self.merge_style

        # Merge/rebase
        if method == 'rebase':
            method = self.repository.rebase
            error_msg = _('Failed to rebase our branch onto remote branch %s.')
        else:
            method = self.repository.merge
            error_msg = _('Failed to merge remote branch into %s.')

        with self.repository_lock:
            try:
                # Try to merge it
                method(self.branch)
                self.log_info(
                    '%s remote into repo',
                    self.merge_style,
                )
                return True
            except Exception as error:
                # In case merge has failer recover
                error = str(error)
                status = self.repository.status()

                # Log error
                self.log_error(
                    'failed %s on repo: %s',
                    self.merge_style,
                    error
                )

                # Reset repo back
                method(abort=True)

        # Notify subscribers and admins
        self.notify_merge_failure(error, status)

        # Tell user (if there is any)
        if request is not None:
            messages.error(
                request,
                error_msg % self.__unicode__()
            )

        return False

    def get_mask_matches(self):
        '''
        Returns files matching current mask.
        '''
        prefix = os.path.join(self.get_path(), '')
        matches = glob(os.path.join(self.get_path(), self.filemask))
        matches = [f.replace(prefix, '') for f in matches]
        # We want to list template among translations as well
        if self.has_template() and self.template not in matches:
            matches.append(self.template)
        return matches

    def create_translations(self, force=False, langs=None, request=None):
        '''
        Loads translations from VCS.
        '''
        translations = []
        matches = self.get_mask_matches()
        for pos, path in enumerate(matches):
            code = self.get_lang_code(path)
            if langs is not None and code not in langs:
                self.log_info('skipping %s', path)
                continue

            self.log_info(
                'checking %s [%d/%d]',
                path,
                pos + 1,
                len(matches)
            )
            translation = Translation.objects.check_sync(
                self, code, path, force, request=request
            )
            translations.append(translation.id)

        # Delete possibly no longer existing translations
        if langs is None:
            todelete = self.translation_set.exclude(id__in=translations)
            if todelete.exists():
                self.log_info(
                    'removing stale translations: %s',
                    ','.join([trans.language.code for trans in todelete])
                )
                todelete.delete()

        # Process linked repos
        for subproject in self.get_linked_childs():
            self.log_info(
                'updating linked project %s',
                subproject
            )
            subproject.create_translations(force, langs, request=request)

        self.log_info('updating completed')

    def get_lang_code(self, path):
        '''
        Parses language code from path.
        '''
        parts = self.filemask.split('*', 1)
        # No * in mask?
        if len(parts) == 1:
            return 'INVALID'
        # Assume English language for template if we can not parse it
        if ((not path.startswith(parts[0]) or not path.endswith(parts[1])) and
                path == self.template):
            return 'en'
        # Get part matching to first wildcard
        if len(parts[1]) == 0:
            code = path[len(parts[0]):].split('/')[0]
        else:
            code = path[len(parts[0]):-len(parts[1])].split('/')[0]
        # Remove possible encoding part
        return code.split('.')[0]

    def sync_git_repo(self, validate=False):
        '''
        Brings VCS repo in sync with current model.
        '''
        if self.is_repo_link:
            return
        self.configure_repo(validate)
        self.commit_pending(None)
        self.configure_branch()
        self.update_remote_branch()
        self.update_branch()

    def clean_repo_link(self):
        '''
        Validates repository link.
        '''
        try:
            repo = SubProject.objects.get_linked(self.repo)
            if repo is not None and repo.is_repo_link:
                raise ValidationError(
                    _(
                        'Invalid link to a Weblate project, '
                        'can not link to linked repository!'
                    )
                )
            if repo.pk == self.pk:
                raise ValidationError(
                    _(
                        'Invalid link to a Weblate project, '
                        'can not link to self!'
                    )
                )
        except (SubProject.DoesNotExist, ValueError):
            raise ValidationError(
                _(
                    'Invalid link to a Weblate project, '
                    'use weblate://project/subproject.'
                )
            )
        if self.push != '':
            raise ValidationError(
                _('Push URL is not used when repository is linked!')
            )
        if self.git_export != '':
            raise ValidationError(
                _('Export URL is not used when repository is linked!')
            )

    def clean_lang_codes(self, matches):
        '''
        Validates that there are no double language codes found in the files.
        '''
        if len(matches) == 0:
            raise ValidationError(_('The mask did not match any files!'))
        langs = set()
        translated_langs = set()
        for match in matches:
            code = self.get_lang_code(match)
            lang = Language.objects.auto_get_or_create(code=code)
            if code in langs:
                raise ValidationError(_(
                    'There are more files for single language, please '
                    'adjust the mask and use components for translating '
                    'different resources.'
                ))
            if lang.code in translated_langs:
                raise ValidationError(_(
                    'Multiple translations were mapped to a single language '
                    'code (%s). You should disable SIMPLIFY_LANGUAGES '
                    'to prevent Weblate mapping similar languages to one.'
                ) % lang.code)
            langs.add(code)
            translated_langs.add(lang.code)

    def clean_files(self, matches):
        '''
        Validates whether we can parse translation files.
        '''
        notrecognized = []
        errors = []
        dir_path = self.get_path()
        for match in matches:
            try:
                parsed = self.file_format_cls.load(
                    os.path.join(dir_path, match),
                )
                if not self.file_format_cls.is_valid(parsed):
                    errors.append('%s: %s' % (
                        match, _('File does not seem to be valid!')
                    ))
            except ValueError:
                notrecognized.append(match)
            except Exception as error:
                errors.append('%s: %s' % (match, str(error)))
        if len(notrecognized) > 0:
            msg = (
                _('Format of %d matched files could not be recognized.') %
                len(notrecognized)
            )
            raise ValidationError('%s\n%s' % (
                msg,
                '\n'.join(notrecognized)
            ))
        if len(errors) > 0:
            raise ValidationError('%s\n%s' % (
                (_('Failed to parse %d matched files!') % len(errors)),
                '\n'.join(errors)
            ))

    def clean_new_lang(self):
        '''
        Validates new language choices.
        '''
        if self.new_lang == 'add':
            if not self.file_format_cls.supports_new_language():
                raise ValidationError(_(
                    'Chosen file format does not support adding '
                    'new translations as chosen in project settings.'
                ))
            filename = self.get_new_base_filename()
            if not self.file_format_cls.is_valid_base_for_new(filename):
                raise ValidationError(_(
                    'Format of base file for new translations '
                    'was not recognized!'
                ))
        elif self.new_lang != 'add' and self.new_base:
            raise ValidationError(_(
                'Base file for new translations is not used because of '
                'project settings.'
            ))

    def clean_template(self):
        """
        Validates template value.
        """
        # Test for unexpected template usage
        if self.template != '' and self.file_format_cls.monolingual is False:
            raise ValidationError(
                _('You can not base file with bilingual translation!')
            )

        # Special case for Gettext
        if self.template.endswith('.pot') and self.filemask.endswith('.po'):
            raise ValidationError(
                _('You can not base file with bilingual translation!')
            )

        # Validate template loading
        if self.has_template():
            full_path = os.path.join(self.get_path(), self.template)
            if not os.path.exists(full_path):
                raise ValidationError(_('Template file not found!'))

            try:
                self.load_template_store()
            except ValueError:
                raise ValidationError(
                    _(
                        'Format of translation base file '
                        'could not be recognized.'
                    )
                )
            except Exception as exc:
                raise ValidationError(
                    _('Failed to parse translation base file: %s') % str(exc)
                )

        elif self.file_format_cls.monolingual:
            raise ValidationError(
                _('You can not use monolingual translation without base file!')
            )

    def clean(self):
        '''
        Validator fetches repository and tries to find translation files.
        Then it checks them for validity.
        '''
        if self.new_lang == 'url' and self.project.instructions == '':
            raise ValidationError(_(
                'Please either fill in instructions URL '
                'or use different option for adding new language.'
            ))

        if self.license == '' and self.license_url != '':
            raise ValidationError(_(
                'License URL can not be used without license summary.'
            ))

        # Skip validation if we don't have valid project
        if self.project_id is None:
            return

        # Check if we should rename
        if self.id:
            old = SubProject.objects.get(pk=self.id)
            self.check_rename(old)

            if old.vcs != self.vcs:
                # This could work, but the problem is that before changed
                # object is saved the linked repos still see old vcs leading
                # to horrible mess. Changing vcs from the manage.py shell
                # works fine though.
                raise ValidationError(
                    _('Changing version control system is not supported!')
                )

        # Check file format
        if self.file_format not in FILE_FORMATS:
            raise ValidationError(
                _('Unsupported file format: {0}').format(self.file_format)
            )

        # Validate VCS repo
        try:
            self.sync_git_repo(True)
        except RepositoryException as exc:
            raise ValidationError(_('Failed to update repository: %s') % exc)

        # Push repo is not used with link
        if self.is_repo_link:
            self.clean_repo_link()

        # Template validation
        self.clean_template()

        matches = self.get_mask_matches()

        # Verify language codes
        self.clean_lang_codes(matches)

        # Try parsing files
        self.clean_files(matches)

        # New language options
        self.clean_new_lang()

        # Suggestions
        if self.suggestion_autoaccept and not self.suggestion_voting:
            raise ValidationError(_(
                'Automatically accepting suggestions can work only with '
                'voting enabled!'
            ))

    def get_template_filename(self):
        '''
        Creates absolute filename for template.
        '''
        return os.path.join(self.get_path(), self.template)

    def get_new_base_filename(self):
        '''
        Creates absolute filename for base file for new translations.
        '''
        return os.path.join(self.get_path(), self.new_base)

    def save(self, *args, **kwargs):
        '''
        Save wrapper which updates backend repository and regenerates
        translation data.
        '''
        # Detect if VCS config has changed (so that we have to pull the repo)
        changed_git = True
        changed_setup = False
        if self.id:
            old = SubProject.objects.get(pk=self.id)
            changed_git = (
                (old.repo != self.repo) or
                (old.branch != self.branch) or
                (old.filemask != self.filemask)
            )
            changed_setup = (
                (old.file_format != self.file_format) or
                (old.template != self.template)
            )
            # Detect slug changes and rename git repo
            self.check_rename(old)

        # Configure git repo if there were changes
        if changed_git:
            self.sync_git_repo()

        # Remove leading ./ from paths
        if self.filemask.startswith('./'):
            self.filemask = self.filemask[2:]
        if self.template.startswith('./'):
            self.template = self.template[2:]
        if self.extra_commit_file.startswith('./'):
            self.extra_commit_file = self.extra_commit_file[2:]

        # Save/Create object
        super(SubProject, self).save(*args, **kwargs)

        # Rescan for possibly new translations if there were changes, needs to
        # be done after actual creating the object above
        if changed_setup:
            self.create_translations(force=True)
        elif changed_git:
            self.create_translations()

    def _get_percents(self):
        '''
        Returns percentages of translation status.
        '''
        return self.translation_set.get_percents()

    def git_needs_commit(self):
        '''
        Checks whether there are some not committed changes.
        '''
        if self.is_repo_link:
            return self.linked_subproject.git_needs_commit()
        return self.repository.needs_commit()

    def git_needs_merge(self):
        '''
        Checks whether there is something to merge from remote repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.git_needs_merge()
        return self.repository.needs_merge(self.branch)

    def git_needs_push(self):
        '''
        Checks whether there is something to push to remote repository.
        '''
        if self.is_repo_link:
            return self.linked_subproject.git_needs_push()
        return self.repository.needs_push(self.branch)

    @property
    def file_format_cls(self):
        '''
        Returns file format object.
        '''
        if (self._file_format is None or
                self._file_format.name != self.file_format):
            self._file_format = FILE_FORMATS[self.file_format]
        return self._file_format

    def has_template(self):
        '''
        Returns true if subproject is using template for translation
        '''
        monolingual = self.file_format_cls.monolingual
        return (
            (monolingual or monolingual is None) and
            len(self.template) > 0 and
            not self.template.endswith('.pot')
        )

    def load_template_store(self):
        '''
        Loads translate-toolkit store for template.
        '''
        return self.file_format_cls.load(
            self.get_template_filename(),
        )

    @property
    def template_store(self):
        '''
        Gets translate-toolkit store for template.
        '''
        # Do we need template?
        if not self.has_template():
            return None

        if self._template_store is None:
            self._template_store = self.load_template_store()

        return self._template_store

    @property
    def last_change(self):
        '''
        Returns date of last change done in Weblate.
        '''
        try:
            change = Change.objects.content().filter(
                translation__subproject=self
            )
            return change[0].timestamp
        except IndexError:
            return None

    @property
    def all_flags(self):
        '''
        Returns parsed list of flags.
        '''
        if self._all_flags is None:
            self._all_flags = (
                self.check_flags.split(',') +
                list(self.file_format_cls.check_flags)
            )
        return self._all_flags

    def add_new_language(self, language, request):
        '''
        Creates new language file.
        '''
        if self.new_lang != 'add':
            raise ValueError('Not supported operation!')

        if not self.file_format_cls.supports_new_language():
            raise ValueError('Not supported operation!')

        base_filename = self.get_new_base_filename()
        if not self.file_format_cls.is_valid_base_for_new(base_filename):
            raise ValueError('Not supported operation!')

        filename = self.file_format_cls.get_language_filename(
            self.filemask,
            language.code
        )
        fullname = os.path.join(self.get_path(), filename)

        # Create directory for a translation
        dirname = os.path.dirname(fullname)
        if not os.path.exists(dirname):
            os.makedirs(dirname)

        self.file_format_cls.add_language(
            fullname,
            language.code,
            base_filename
        )

        translation = Translation.objects.create(
            subproject=self,
            language=language,
            filename=filename,
            language_code=language.code,
            commit_message='Created new translation.'
        )
        translation.git_commit(
            request,
            translation.get_author_name(request.user),
            timezone.now(),
            force_commit=True,
        )
        translation.check_sync(
            force=True,
            request=request
        )

    def do_lock(self, user):
        """Locks component."""
        self.locked = True
        self.save()
        if self.translation_set.exists():
            Change.objects.create(
                translation=self.translation_set.all()[0],
                user=user,
                action=Change.ACTION_LOCK,
            )

    def do_unlock(self, user):
        """Locks component."""
        self.locked = False
        self.save()
        if self.translation_set.exists():
            Change.objects.create(
                translation=self.translation_set.all()[0],
                user=user,
                action=Change.ACTION_UNLOCK,
            )
