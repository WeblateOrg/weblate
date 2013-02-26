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
from django.db.models import Sum
from django.utils.translation import ugettext as _, ugettext_lazy
from django.core.mail import mail_admins
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
from glob import glob
import os
import time
import random
import os.path
import logging
import git
from trans.formats import (
    FILE_FORMAT_CHOICES,
    FILE_FORMATS,
    ttkit
)
from trans.models.project import Project
from trans.filelock import FileLock
from trans.util import is_repo_link
from trans.validators import (
    validate_repoweb,
    validate_filemask,
    validate_repo,
)

logger = logging.getLogger('weblate')


class SubProjectManager(models.Manager):
    def all_acl(self, user):
        '''
        Returns list of projects user is allowed to access.
        '''
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


class SubProject(models.Model):
    name = models.CharField(
        max_length=100,
        help_text=ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        db_index=True,
        help_text=ugettext_lazy('Name used in URLs')
    )
    project = models.ForeignKey(Project)
    repo = models.CharField(
        max_length=200,
        help_text=ugettext_lazy(
            'URL of Git repository, use weblate://project/subproject '
            'for sharing with other subproject.'
        ),
        validators=[validate_repo],
    )
    push = models.CharField(
        max_length=200,
        help_text=ugettext_lazy('URL of push Git repository'),
        blank=True
    )
    repoweb = models.URLField(
        help_text=ugettext_lazy(
            'Link to repository browser, use %(branch)s for branch, '
            '%(file)s and %(line)s as filename and line placeholders.'
        ),
        validators=[validate_repoweb],
        blank=True,
    )
    report_source_bugs = models.EmailField(
        help_text=ugettext_lazy(
            'Email address where errors in source string will be reported, '
            'keep empty for no emails.'
        ),
        blank=True,
    )
    branch = models.CharField(
        max_length=50,
        help_text=ugettext_lazy('Git branch to translate'),
        default='master'
    )
    filemask = models.CharField(
        max_length=200,
        validators=[validate_filemask],
        help_text=ugettext_lazy(
            'Path of files to translate, use * instead of language code, '
            'for example: po/*.po or locale/*/LC_MESSAGES/django.po.'
        )
    )
    template = models.CharField(
        max_length=200,
        blank=True,
        help_text=ugettext_lazy(
            'Filename of translations template, this is recommended to use '
            'for translations which store only translated string like '
            'Android resource strings.'
        )
    )
    file_format = models.CharField(
        max_length=50,
        default='auto',
        choices=FILE_FORMAT_CHOICES,
        help_text=ugettext_lazy(
            'Automatic detection might fail for some formats '
            'and is slightly slower.'
        ),
    )
    locked = models.BooleanField(
        default=False,
        help_text=ugettext_lazy(
            'Whether subproject is locked for translation updates.'
        )
    )
    allow_translation_propagation = models.BooleanField(
        default=True,
        help_text=ugettext_lazy(
            'Whether translation updates in other subproject '
            'will cause automatic translation in this project'
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

    def has_acl(self, user):
        '''
        Checks whether current user is allowed to access this
        subproject.
        '''
        return self.project.has_acl(user)

    def check_acl(self, request):
        '''
        Raises an error if user is not allowed to acces s this project.
        '''
        self.project.check_acl(request)

    @models.permalink
    def get_absolute_url(self):
        return ('subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    def get_share_url(self):
        '''
        Returns absolute URL usable for sharing.
        '''
        site = Site.objects.get_current()
        return 'http://%s%s' % (
            site.domain,
            reverse('engage', kwargs={'project': self.project.slug}),
        )

    @models.permalink
    def get_commit_url(self):
        return ('commit_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_update_url(self):
        return ('update_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_push_url(self):
        return ('push_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_reset_url(self):
        return ('reset_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    def is_git_lockable(self):
        return True

    def is_git_locked(self):
        return self.locked

    @models.permalink
    def get_lock_url(self):
        return ('lock_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_unlock_url(self):
        return ('unlock_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

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

    def get_git_lock(self):
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
        return self.push != '' and self.push is not None

    def is_repo_link(self):
        '''
        Checks whethere repository is just a link for other one.
        '''
        return is_repo_link(self.repo)

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
        return self.git_repo.commit('origin/master')

    def get_repoweb_link(self, filename, line):
        '''
        Generates link to source code browser for given file and line.
        '''
        if self.is_repo_link():
            return self.linked_subproject.get_repoweb_link(filename, line)

        if self.repoweb == '' or self.repoweb is None:
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
        logger.info('updating repo %s', self.__unicode__())
        try:
            try:
                self.git_repo.git.remote('update', 'origin')
            except git.GitCommandError:
                # There might be another attempt on pull in same time
                # so we will sleep a bit an retry
                time.sleep(random.random() * 2)
                self.git_repo.git.remote('update', 'origin')
        except Exception as e:
            logger.error('Failed to update Git repo: %s', str(e))
            if validate:
                raise ValidationError(
                    _('Failed to fetch git repository: %s') % str(e)
                )

    def configure_repo(self, validate=False):
        '''
        Ensures repository is correctly configured and points to current
        remote.
        '''
        if self.is_repo_link():
            return self.linked_subproject.configure_repo(validate)
        # Create/Open repo
        gitrepo = self.git_repo
        # Get/Create origin remote
        try:
            origin = gitrepo.remotes.origin
        except:
            gitrepo.git.remote('add', 'origin', self.repo)
            origin = gitrepo.remotes.origin
        # Check remote source
        if origin.url != self.repo:
            gitrepo.git.remote('set-url', 'origin', self.repo)
        # Check push url
        try:
            pushurl = origin.pushurl
        except AttributeError:
            pushurl = ''
        if pushurl != self.push:
            gitrepo.git.remote('set-url', 'origin', '--push', self.push)
        # Update
        self.update_remote_branch(validate)

    def configure_branch(self):
        '''
        Ensures local tracking branch exists and is checkouted.
        '''
        if self.is_repo_link():
            return self.linked_subproject.configure_branch()

        gitrepo = self.git_repo

        # create branch if it does not exist
        if not self.branch in gitrepo.heads:
            gitrepo.git.branch(
                '--track',
                self.branch,
                'origin/%s' % self.branch
            )

        # switch to correct branch
        gitrepo.git.checkout(self.branch)

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
        self.commit_pending()

        # update remote branch
        ret = self.update_branch(request)

        # create translation objects for all files
        self.create_translations(request=request)

        # Push after possible merge
        if self.git_needs_push() and self.project.push_on_commit:
            self.do_push(force_commit=False, do_update=False)

        return ret

    def do_push(self, request=None, force_commit=True, do_update=True):
        '''
        Wrapper for pushing changes to remote repo.
        '''
        if self.is_repo_link():
            return self.linked_subproject.do_push(request)

        # Do we have push configured
        if not self.can_push():
            messages.error(
                request,
                _('Push is disabled for %s.') % self.__unicode__()
            )
            return False

        # Commit any pending changes
        if force_commit:
            self.commit_pending(skip_push=True)

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
            logger.info('pushing to remote repo %s', self.__unicode__())
            self.git_repo.git.push(
                'origin',
                '%s:%s' % (self.branch, self.branch)
            )
            return True
        except Exception as e:
            logger.warning('failed push on repo %s', self.__unicode__())
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
        try:
            logger.info('reseting to remote repo %s', self.__unicode__())
            self.git_repo.git.reset('--hard', 'origin/%s' % self.branch)
        except Exception as e:
            logger.warning('failed reset on repo %s', self.__unicode__())
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

    def commit_pending(self, from_link=False, skip_push=False):
        '''
        Checks whether there is any translation which needs commit.
        '''
        if not from_link and self.is_repo_link():
            return self.linked_subproject.commit_pending(
                True, skip_push=skip_push
            )

        for translation in self.translation_set.all():
            translation.commit_pending(skip_push=skip_push)

        # Process linked projects
        for subproject in self.get_linked_childs():
            subproject.commit_pending(True, skip_push=skip_push)

    def notify_merge_failure(self, error, status):
        '''
        Sends out notifications on merge failure.
        '''
        # Notify subscribed users about failure
        from accounts.models import Profile, send_notification_email
        subscriptions = Profile.objects.subscribed_merge_failure(
            self.project,
        )
        for subscription in subscriptions:
            subscription.notify_merge_failure(self, error, status)

        # Notify admins
        send_notification_email(
            'en',
            'ADMINS',
            'merge_failure',
            self,
            {
                'subproject': self,
                'status': status,
                'error': error,
            }
        )

    def update_merge(self, request=None):
        '''
        Updates current branch to remote using merge.
        '''
        gitrepo = self.git_repo

        with self.get_git_lock():
            try:
                # Try to merge it
                gitrepo.git.merge('origin/%s' % self.branch)
                logger.info('merged remote into repo %s', self.__unicode__())
                return True
            except Exception as e:
                # In case merge has failer recover
                status = gitrepo.git.status()
                error = str(e)
                gitrepo.git.merge('--abort')

        # Log error
        logger.warning('failed merge on repo %s', self.__unicode__())

        # Notify subscribers and admins
        self.notify_merge_failure(error, status)

        # Tell user (if there is any)
        if request is not None:
            messages.error(
                request,
                _('Failed to merge remote branch into %s.') %
                self.__unicode__()
            )

        return False

    def update_rebase(self, request=None):
        '''
        Updates current branch to remote using rebase.
        '''
        gitrepo = self.git_repo

        with self.get_git_lock():
            try:
                # Try to merge it
                gitrepo.git.rebase('origin/%s' % self.branch)
                logger.info('rebased remote into repo %s', self.__unicode__())
                return True
            except Exception as e:
                # In case merge has failer recover
                status = gitrepo.git.status()
                error = str(e)
                gitrepo.git.rebase('--abort')

        # Log error
        logger.warning('failed rebase on repo %s', self.__unicode__())

        # Notify subscribers and admins
        self.notify_merge_failure(error, status)

        # Tell user (if there is any)
        if request is not None:
            messages.error(
                request,
                _('Failed to rebase our branch onto remote branch %s.') %
                self.__unicode__()
            )

        return False

    def update_branch(self, request=None):
        '''
        Updates current branch to match remote (if possible).
        '''
        if self.is_repo_link():
            return self.linked_subproject.update_branch(request)

        # Merge/rebase
        if self.project.merge_style == 'rebase':
            return self.update_rebase(request)
        else:
            return self.update_merge(request)

    def get_mask_matches(self):
        '''
        Returns files matching current mask.
        '''
        prefix = os.path.join(self.get_path(), '')
        matches = glob(os.path.join(self.get_path(), self.filemask))
        return [f.replace(prefix, '') for f in matches]

    def get_translation_blobs(self):
        '''
        Iterator over translations in filesystem.
        '''
        # Glob files
        for filename in self.get_mask_matches():
            yield (
                self.get_lang_code(filename),
                filename,
            )

    def create_translations(self, force=False, langs=None, request=None):
        '''
        Loads translations from git.
        '''
        from trans.models.translation import Translation
        translations = []
        for code, path in self.get_translation_blobs():
            if langs is not None and code not in langs:
                logger.info('skipping %s', path)
                continue

            logger.info('checking %s', path)
            translation = Translation.objects.update_from_blob(
                self, code, path, force, request=request
            )
            translations.append(translation.id)

        # Delete possibly no longer existing translations
        if langs is None:
            todelete = self.translation_set.exclude(id__in=translations)
            if todelete.exists():
                logger.info(
                    'removing stale translations: %s',
                    ','.join([trans.language.code for trans in todelete])
                )
                todelete.delete()

        # Process linked repos
        for subproject in self.get_linked_childs():
            logger.info(
                'updating linked project %s',
                subproject
            )
            subproject.create_translations(force, langs, request=request)

        logger.info('updating of %s completed', self)

    def get_lang_code(self, path):
        '''
        Parses language code from path.
        '''
        parts = self.filemask.split('*', 1)
        # No * in mask?
        if len(parts) == 1:
            return 'INVALID'
        # Get part matching to first wildcard
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
        self.configure_branch()
        self.commit_pending()
        self.update_remote_branch()
        self.update_branch()

    def clean(self):
        '''
        Validator fetches repository and tries to find translation files.
        Then it checks them for validity.
        '''
        # Skip validation if we don't have valid project
        if self.project_id is None:
            return

        # Validate git repo
        self.sync_git_repo(True)

        # Push repo is not used with link
        if self.is_repo_link() and self.push != '':
            raise ValidationError(
                _('Push URL is not used when repository is linked!')
            )

        try:
            matches = self.get_mask_matches()
            if len(matches) == 0:
                raise ValidationError(_('The mask did not match any files!'))
            langs = {}
            for match in matches:
                code = self.get_lang_code(match)
                if code in langs:
                    raise ValidationError(_(
                        'There are more files for single language, please '
                        'adjust the mask and use subprojects for translating '
                        'different resources.'
                    ))
                langs[code] = match

            # Try parsing files
            notrecognized = []
            errors = []
            for match in matches:
                try:
                    ttkit(
                        os.path.join(self.get_path(), match),
                        self.file_format
                    )
                except ValueError:
                    notrecognized.append(match)
                except Exception as e:
                    errors.append('%s: %s' % (match, str(e)))
            if len(notrecognized) > 0:
                raise ValidationError('%s\n%s' % (
                    (_('Format of %d matched files could not be recognized.') % len(notrecognized)),
                    '\n'.join(notrecognized)
                ))
            if len(errors) > 0:
                raise ValidationError('%s\n%s' % (
                    (_('Failed to parse %d matched files!') % len(errors)),
                    '\n'.join(errors)
                ))

            # Validate template
            if self.template != '':
                template = self.get_template_filename()
                try:
                    ttkit(template, self.file_format)
                except ValueError:
                    raise ValidationError(_('Format of translation template could not be recognized.'))
                except Exception as e:
                    raise ValidationError(
                        _('Failed to parse translation template.')
                    )
        except SubProject.DoesNotExist:
            # Happens with invalid link
            pass

    def get_template_filename(self):
        return os.path.join(self.get_path(), self.template)

    def save(self, *args, **kwargs):
        '''
        Save wrapper which updates backend Git repository and regenerates
        translation data.
        '''
        # Detect if git config has changed (so that we have to pull the repo)
        changed_git = True
        if (self.id):
            old = SubProject.objects.get(pk=self.id)
            changed_git = (
                (old.repo != self.repo)
                or (old.branch != self.branch)
                or (old.filemask != self.filemask)
            )
            # Detect slug changes and rename git repo
            if old.slug != self.slug:
                os.rename(
                    old.get_path(),
                    self.get_path()
                )

        # Configure git repo if there were changes
        if changed_git:
            self.sync_git_repo()

        # Save/Create object
        super(SubProject, self).save(*args, **kwargs)

        # Rescan for possibly new translations if there were changes, needs to
        # be done after actual creating the object above
        if changed_git:
            self.create_translations()

    def get_translated_percent(self):
        '''
        Returns percent of translated strings.
        '''
        translations = self.translation_set.aggregate(
            Sum('translated'), Sum('total')
        )

        total = translations['total__sum']
        translated = translations['translated__sum']

        if total == 0:
            return 0

        return round(translated * 100.0 / total, 1)

    def git_needs_commit(self):
        '''
        Checks whether there are some not commited changes.
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

    def get_file_format(self):
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
        monolingual = self.get_file_format().monolingual
        return (
            (monolingual or monolingual is None)
            and self.template != ''
            and not self.template is None
        )

    def should_mark_fuzzy(self):
        '''
        Returns whether we're handling fuzzy mark in the database.
        '''
        return self.get_file_format().mark_fuzzy

    def get_template_store(self):
        '''
        Gets ttkit store for template.
        '''
        # Do we need template?
        if not self.has_template():
            return None

        if self._template_store is None:
            self._template_store = ttkit(
                self.get_template_filename(),
                self.file_format
            )

        return self._template_store

    def get_last_change(self):
        '''
        Returns date of last change done in Weblate.
        '''
        from trans.models.unitdata import Change
        try:
            change = Change.objects.content().filter(
                translation__subproject=self
            )
            return change[0].timestamp
        except IndexError:
            return None
