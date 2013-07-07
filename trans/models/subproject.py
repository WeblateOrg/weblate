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
from django.utils.translation import ugettext as _, ugettext_lazy
from django.core.mail import mail_admins
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.core.urlresolvers import reverse
from glob import glob
import os.path
import weblate
import git
from trans.formats import FILE_FORMAT_CHOICES, FILE_FORMATS
from trans.models.project import Project
from trans.mixins import PercentMixin, URLMixin, PathMixin
from trans.filelock import FileLock
from trans.util import is_repo_link
from trans.util import get_site_url
from trans.util import sleep_while_git_locked
from trans.validators import (
    validate_repoweb, validate_filemask, validate_repo,
    validate_extra_file,
)
from weblate.appsettings import SCRIPT_CHOICES


class SubProjectManager(models.Manager):
    def all_acl(self, user):
        '''
        Returns list of projects user is allowed to access.
        '''
        projects, filtered = Project.objects.get_acl_status(user)
        if not filtered:
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


class SubProject(models.Model, PercentMixin, URLMixin, PathMixin):
    name = models.CharField(
        verbose_name=ugettext_lazy('Subproject name'),
        max_length=100,
        help_text=ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        verbose_name=ugettext_lazy('URL slug'),
        db_index=True,
        help_text=ugettext_lazy('Name used in URLs and file names.')
    )
    project = models.ForeignKey(
        Project,
        verbose_name=ugettext_lazy('Project'),
    )
    repo = models.CharField(
        verbose_name=ugettext_lazy('Git repository'),
        max_length=200,
        help_text=ugettext_lazy(
            'URL of Git repository, use weblate://project/subproject '
            'for sharing with other subproject.'
        ),
        validators=[validate_repo],
    )
    push = models.CharField(
        verbose_name=ugettext_lazy('Git push URL'),
        max_length=200,
        help_text=ugettext_lazy('URL of push Git repository'),
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
        verbose_name=ugettext_lazy('Exported Git URL'),
        max_length=200,
        help_text=ugettext_lazy(
            'URL of Git repository where users can fetch changes from Weblate'
        ),
        blank=True
    )
    report_source_bugs = models.EmailField(
        verbose_name=ugettext_lazy('Source string bug report address'),
        help_text=ugettext_lazy(
            'Email address where errors in source string will be reported, '
            'keep empty for no emails.'
        ),
        blank=True,
    )
    branch = models.CharField(
        verbose_name=ugettext_lazy('Git branch'),
        max_length=50,
        help_text=ugettext_lazy('Git branch to translate'),
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
            'Whether subproject is locked for translation updates.'
        )
    )
    allow_translation_propagation = models.BooleanField(
        verbose_name=ugettext_lazy('Allow translation propagation'),
        default=True,
        help_text=ugettext_lazy(
            'Whether translation updates in other subproject '
            'will cause automatic translation in this project'
        )
    )
    save_history = models.BooleanField(
        verbose_name=ugettext_lazy('Save translation history'),
        default=True,
        help_text=ugettext_lazy(
            'Whether Weblate should keep history of translations'
        )
    )

    objects = SubProjectManager()

    class Meta:
        ordering = ['project__name', 'name']
        unique_together = (
            ('project', 'name'),
            ('project', 'slug'),
        )
        permissions = (
            ('lock_subproject', "Can lock translation for translating"),
        )
        app_label = 'trans'

    def __init__(self, *args, **kwargs):
        '''
        Constructor to initialize some cache properties.
        '''
        super(SubProject, self).__init__(*args, **kwargs)
        self._lock = None
        self._git_repo = None
        self._file_format = None
        self._template_store = None
        self._percents = None

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

    def get_share_url(self):
        '''
        Returns absolute URL usable for sharing.
        '''
        return get_site_url(
            reverse('engage', kwargs={'project': self.project.slug})
        )

    def is_git_lockable(self):
        return True

    def is_git_locked(self):
        return self.locked

    def __unicode__(self):
        return '%s/%s' % (self.project.__unicode__(), self.name)

    def get_full_slug(self):
        return '%s__%s' % (self.project.slug, self.slug)

    def get_path(self):
        '''
        Returns full path to subproject git repository.
        '''
        if self.is_repo_link():
            return self.linked_subproject.get_path()

        return os.path.join(self.project.get_path(), self.slug)

    def get_git_lock_path(self):
        '''
        Returns full path to subproject git repository.
        '''
        return os.path.join(self.project.get_path(), self.slug + '.lock')

    @property
    def git_lock(self):
        '''
        Returns lock object for current translation instance.
        '''
        if self._lock is None:
            self._lock = FileLock(
                self.get_git_lock_path(),
                timeout=20
            )
        return self._lock

    def can_push(self):
        '''
        Returns true if push is possible for this subproject.
        '''
        if self.is_repo_link():
            return self.linked_subproject.can_push()
        return self.push != '' and self.push is not None

    def is_repo_link(self):
        '''
        Checks whether repository is just a link for other one.
        '''
        return is_repo_link(self.repo)

    def can_add_language(self):
        '''
        Returns true if new languages can be added.
        '''
        return self.project.new_lang != 'none'

    @property
    def linked_subproject(self):
        '''
        Returns subproject for linked repo.
        '''
        return SubProject.objects.get_linked(self.repo)

    @property
    def git_repo(self):
        '''
        Gets Git repository object.
        '''
        if self._git_repo is None:
            path = self.get_path()
            try:
                self._git_repo = git.Repo(path)
            except:
                # Fallback to initializing the repository
                self._git_repo = git.Repo.init(path)

        return self._git_repo

    def get_last_remote_commit(self):
        '''
        Returns latest remote commit we know.
        '''
        return self.git_repo.commit('origin/%s' % self.branch)

    def get_repo_url(self):
        '''
        Returns link to repository.
        '''
        if self.is_repo_link():
            return self.linked_subproject.repo
        return self.repo

    def get_repo_branch(self):
        '''
        Returns branch in repository.
        '''
        if self.is_repo_link():
            return self.linked_subproject.branch
        return self.branch

    def get_export_url(self):
        '''
        Returns URL of exported git repository.
        '''
        if self.is_repo_link():
            return self.linked_subproject.git_export
        return self.git_export

    def get_repoweb_link(self, filename, line):
        '''
        Generates link to source code browser for given file and line.

        For linked repositories, it is possible to override linked
        repository path here.
        '''
        if len(self.repoweb) == 0:
            if self.is_repo_link():
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
        if self.is_repo_link():
            return self.linked_subproject.update_remote_branch(validate)

        # Update
        weblate.logger.info('updating repo %s', self.__unicode__())
        try:
            try:
                self.git_repo.git.remote('update', 'origin')
            except git.GitCommandError:
                # There might be another attempt on pull in same time
                # so we will sleep a bit an retry
                sleep_while_git_locked()
                self.git_repo.git.remote('update', 'origin')
        except Exception as e:
            error_text = str(e)
            weblate.logger.error('Failed to update Git repo: %s', error_text)
            if validate:
                if 'Host key verification failed' in error_text:
                    raise ValidationError(_(
                        'Failed to verify SSH host key, please add '
                        'them in SSH page in the admin interface.'
                    ))
                raise ValidationError(
                    _('Failed to fetch git repository: %s') % error_text
                )

    def configure_repo(self, validate=False):
        '''
        Ensures repository is correctly configured and points to current
        remote.
        '''
        if self.is_repo_link():
            return self.linked_subproject.configure_repo(validate)

        # Create origin remote if it does not exist
        if 'origin' not in self.git_repo.git.remote().split():
            self.git_repo.git.remote('add', 'origin', self.repo)

        if not self.repo.startswith('hg::'):
            # Set remote URL
            self.git_repo.git.remote('set-url', 'origin', self.repo)

            # Set branch to track
            # We first need to add one to ensure there is at least one branch
            self.git_repo.git.remote(
                'set-branches', '--add', 'origin', self.branch
            )
            # Then we can set to track just one
            self.git_repo.git.remote('set-branches', 'origin', self.branch)

        # Get object for remote
        origin = self.git_repo.remotes.origin

        # Check push url
        try:
            pushurl = origin.pushurl
        except AttributeError:
            pushurl = ''

        if pushurl != self.push:
            self.git_repo.git.remote('set-url', 'origin', '--push', self.push)

        # Update
        self.update_remote_branch(validate)

    def configure_branch(self):
        '''
        Ensures local tracking branch exists and is checkouted.
        '''
        if self.is_repo_link():
            return self.linked_subproject.configure_branch()

        # create branch if it does not exist
        if not self.branch in self.git_repo.heads:
            self.git_repo.git.branch(
                '--track',
                self.branch,
                'origin/%s' % self.branch
            )

        # switch to correct branch
        self.git_repo.git.checkout(self.branch)

    def do_update(self, request=None):
        '''
        Wrapper for doing repository update and pushing them to translations.
        '''
        if self.is_repo_link():
            return self.linked_subproject.do_update(request)

        # pull remote
        self.update_remote_branch()

        # do we have something to merge?
        if not self.git_needs_merge():
            return True

        # commit possible pending changes
        self.commit_pending(request)

        # update remote branch
        ret = self.update_branch(request)

        # create translation objects for all files
        self.create_translations(request=request)

        # Push after possible merge
        if (self.git_needs_push()
                and ret
                and self.project.push_on_commit
                and self.can_push()):
            self.do_push(request, force_commit=False, do_update=False)

        return ret

    def do_push(self, request, force_commit=True, do_update=True):
        '''
        Wrapper for pushing changes to remote repo.
        '''
        if self.is_repo_link():
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
            weblate.logger.info(
                'pushing to remote repo %s',
                self.__unicode__()
            )
            if not self.repo.startswith('hg::'):
                self.git_repo.git.push(
                    'origin',
                    '%s:%s' % (self.branch, self.branch)
                )
            else:
                self.git_repo.git.push(
                    'origin'
                )
            return True
        except Exception as e:
            weblate.logger.warning(
                'failed push on repo %s',
                self.__unicode__()
            )
            msg = 'Error:\n%s' % str(e)
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
        if self.is_repo_link():
            return self.linked_subproject.do_reset(request)

        # First check we're up to date
        self.update_remote_branch()

        # Do actual reset
        with self.git_lock:
            try:
                weblate.logger.info(
                    'reseting to remote repo %s',
                    self.__unicode__()
                )
                self.git_repo.git.reset('--hard', 'origin/%s' % self.branch)
            except Exception as e:
                weblate.logger.warning(
                    'failed reset on repo %s',
                    self.__unicode__()
                )
                msg = 'Error:\n%s' % str(e)
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
        if not from_link and self.is_repo_link():
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
        from accounts.models import notify_merge_failure
        notify_merge_failure(self, error, status)

    def update_branch(self, request=None):
        '''
        Updates current branch to match remote (if possible).
        '''
        if self.is_repo_link():
            return self.linked_subproject.update_branch(request)

        # Merge/rebase
        if self.project.merge_style == 'rebase':
            method = self.git_repo.git.rebase
            error_msg = _('Failed to rebase our branch onto remote branch %s.')
        else:
            method = self.git_repo.git.merge
            error_msg = _('Failed to merge remote branch into %s.')

        with self.git_lock:
            try:
                # Try to merge it
                method('origin/%s' % self.branch)
                weblate.logger.info(
                    '%s remote into repo %s',
                    self.project.merge_style,
                    self.__unicode__()
                )
                return True
            except Exception as e:
                # In case merge has failer recover
                status = self.git_repo.git.status()
                error = str(e)
                method('--abort')

        # Log error
        weblate.logger.warning(
            'failed %s on repo %s',
            self.project.merge_style,
            self.__unicode__()
        )

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
        # Template can have possibly same name as translations
        if self.has_template() and self.template in matches:
            matches.remove(self.template)
        return matches

    def create_translations(self, force=False, langs=None, request=None):
        '''
        Loads translations from git.
        '''
        from trans.models.translation import Translation
        translations = []
        for path in self.get_mask_matches():
            code = self.get_lang_code(path)
            if langs is not None and code not in langs:
                weblate.logger.info('skipping %s', path)
                continue

            weblate.logger.info('checking %s', path)
            translation = Translation.objects.check_sync(
                self, code, path, force, request=request
            )
            translations.append(translation.id)

        # Delete possibly no longer existing translations
        if langs is None:
            todelete = self.translation_set.exclude(id__in=translations)
            if todelete.exists():
                weblate.logger.info(
                    'removing stale translations: %s',
                    ','.join([trans.language.code for trans in todelete])
                )
                todelete.delete()

        # Process linked repos
        for subproject in self.get_linked_childs():
            weblate.logger.info(
                'updating linked project %s',
                subproject
            )
            subproject.create_translations(force, langs, request=request)

        weblate.logger.info('updating of %s completed', self)

    def get_lang_code(self, path):
        '''
        Parses language code from path.
        '''
        parts = self.filemask.split('*', 1)
        # No * in mask?
        if len(parts) == 1:
            return 'INVALID'
        # Get part matching to first wildcard
        if len(parts[1]) == 0:
            code = path[len(parts[0]):].split('/')[0]
        else:
            code = path[len(parts[0]):-len(parts[1])].split('/')[0]
        # Remove possible encoding part
        return code.split('.')[0]

    def sync_git_repo(self, validate=False):
        '''
        Brings git repo in sync with current model.
        '''
        if self.is_repo_link():
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
        if self.push != '':
            raise ValidationError(
                _('Push URL is not used when repository is linked!')
            )
        if self.git_export != '':
            raise ValidationError(
                _('Export URL is not used when repository is linked!')
            )
        validate_repo(self.repo)

    def clean_template(self):
        '''
        Validates whether template can be loaded.
        '''

        full_path = os.path.join(self.get_path(), self.template)
        if not os.path.exists(full_path):
            raise ValidationError(_('Template file not found!'))

        try:
            self.load_template_store()
        except ValueError:
            raise ValidationError(
                _('Format of translation base file could not be recognized.')
            )
        except Exception as exc:
            raise ValidationError(
                _('Failed to parse translation base file: %s') % str(exc)
            )

    def clean_files(self, matches):
        '''
        Validates whether we can parse translation files.
        '''
        notrecognized = []
        errors = []
        for match in matches:
            try:
                parsed = self.file_format_cls.load(
                    os.path.join(self.get_path(), match),
                )
                if not self.file_format_cls.is_valid(parsed):
                    errors.append('%s: %s' % (
                        match, _('File does not seem to be valid!')
                    ))
            except ValueError:
                notrecognized.append(match)
            except Exception as e:
                errors.append('%s: %s' % (match, str(e)))
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

    def clean(self):
        '''
        Validator fetches repository and tries to find translation files.
        Then it checks them for validity.
        '''
        # Skip validation if we don't have valid project
        if self.project_id is None:
            return

        # Validate git repo
        try:
            self.sync_git_repo(True)
        except git.GitCommandError as exc:
            raise ValidationError(_('Failed to update git: %s') % exc.status)

        # Push repo is not used with link
        if self.is_repo_link():
            self.clean_repo_link()

        matches = self.get_mask_matches()
        if len(matches) == 0:
            raise ValidationError(_('The mask did not match any files!'))
        langs = set()
        for match in matches:
            code = self.get_lang_code(match)
            if code in langs:
                raise ValidationError(_(
                    'There are more files for single language, please '
                    'adjust the mask and use subprojects for translating '
                    'different resources.'
                ))
            langs.add(code)

        # Try parsing files
        self.clean_files(matches)

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

        # Validate template
        if self.has_template():
            self.clean_template()
        elif self.file_format_cls.monolingual:
            raise ValidationError(
                _('You can not use monolingual translation without base file!')
            )

    def get_template_filename(self):
        '''
        Creates absolute filename for template.
        '''
        return os.path.join(self.get_path(), self.template)

    def save(self, *args, **kwargs):
        '''
        Save wrapper which updates backend Git repository and regenerates
        translation data.
        '''
        # Detect if git config has changed (so that we have to pull the repo)
        changed_git = True
        if self.id:
            old = SubProject.objects.get(pk=self.id)
            changed_git = (
                (old.repo != self.repo)
                or (old.branch != self.branch)
                or (old.filemask != self.filemask)
            )
            # Detect slug changes and rename git repo
            self.check_rename(old)

        # Configure git repo if there were changes
        if changed_git:
            self.sync_git_repo()

        # Save/Create object
        super(SubProject, self).save(*args, **kwargs)

        # Rescan for possibly new translations if there were changes, needs to
        # be done after actual creating the object above
        if changed_git:
            self.create_translations()

    def _get_percents(self):
        '''
        Returns percentages of translation status.
        '''
        # Use cache if available
        if self._percents is not None:
            return self._percents

        # Get prercents
        result = self.translation_set.get_percents()

        # Update cache
        self._percents = result

        return result

    def git_needs_commit(self):
        '''
        Checks whether there are some not committed changes.
        '''
        status = self.git_repo.git.status('--porcelain')
        if status == '':
            # No changes to commit
            return False
        return True

    def git_check_merge(self, revision):
        '''
        Checks whether there are any unmerged commits compared to given
        revision.
        '''
        status = self.git_repo.git.log(revision, '--')
        if status == '':
            # No changes to merge
            return False
        return True

    def git_needs_merge(self):
        return self.git_check_merge('..origin/%s' % self.branch)

    def git_needs_push(self):
        return self.git_check_merge('origin/%s..' % self.branch)

    @property
    def file_format_cls(self):
        '''
        Returns file format object.
        '''
        if self._file_format is None:
            self._file_format = FILE_FORMATS[self.file_format]
        return self._file_format

    def has_template(self):
        '''
        Returns true if subproject is using template for translation
        '''
        monolingual = self.file_format_cls.monolingual
        return (
            (monolingual or monolingual is None)
            and len(self.template) > 0
            and not self.template.endswith('.pot')
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

    def get_last_change(self):
        '''
        Returns date of last change done in Weblate.
        '''
        from trans.models.changes import Change
        try:
            change = Change.objects.content().filter(
                translation__subproject=self
            )
            return change[0].timestamp
        except IndexError:
            return None
