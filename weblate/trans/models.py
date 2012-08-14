# -*- coding: utf-8 -*-
#
# Copyright © 2012 Michal Čihař <michal@cihar.com>
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
from django.contrib.auth.models import User
from django.conf import settings
from django.db.models import Sum
from django.utils.translation import ugettext as _, ugettext_lazy
from django.utils.safestring import mark_safe
from django.core.mail import mail_admins
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.utils.formats import date_format
from django.contrib.sites.models import Site
from django.core.cache import cache
from django.utils import timezone
from glob import glob
import os
import time
import random
import os.path
import logging
import git
import traceback
import __builtin__
from translate.storage import factory
from translate.storage import poheader
from datetime import datetime, timedelta

import weblate
from weblate.lang.models import Language
from weblate.trans.checks import CHECKS
from weblate.trans.managers import TranslationManager, UnitManager, DictionaryManager
from weblate.trans.filelock import FileLock
from util import is_plural, split_plural, join_plural

from django.db.models.signals import post_syncdb
from south.signals import post_migrate

from distutils.version import LooseVersion

logger = logging.getLogger('weblate')


def ttkit(storefile):
    '''
    Returns translate-toolkit storage for a path.
    '''

    # Workaround for _ created by interactive interpreter and
    # later used instead of gettext by ttkit
    if '_' in __builtin__.__dict__ and not callable(__builtin__.__dict__['_']):
        del __builtin__.__dict__['_']

    # Add missing mode attribute to Django file wrapper
    if not isinstance(storefile, basestring):
        storefile.mode = 'r'

    return factory.getobject(storefile)


def validate_repoweb(val):
    try:
        val % {'file': 'file.po', 'line': '9', 'branch': 'master'}
    except Exception, e:
        raise ValidationError(_('Bad format string (%s)') % str(e))

def validate_commit_message(val):
    try:
        val % {'language': 'cs', 'project': 'Weblate', 'subproject': 'master'}
    except Exception, e:
        raise ValidationError(_('Bad format string (%s)') % str(e))

def validate_filemask(val):
    if not '*' in val:
        raise ValidationError(_('File mask does not contain * as a language placeholder!'))

def is_repo_link(val):
    '''
    Checks whethere repository is just a link for other one.
    '''
    return val.startswith('weblate://')

def get_linked_repo(val):
    '''
    Returns subproject for linked repo.
    '''
    if not is_repo_link(val):
        return None
    project, subproject = val[10:].split('/', 1)
    return SubProject.objects.get(slug = subproject, project__slug = project)

def validate_repo(val):
    try:
        repo = get_linked_repo(val)
        if repo is not None and repo.is_repo_link():
            raise ValidationError(_('Can not link to linked repository!'))
    except SubProject.DoesNotExist:
        raise ValidationError(_('Invalid link to repository!'))

NEW_LANG_CHOICES = (
    ('contact', ugettext_lazy('Use contact form')),
    ('url', ugettext_lazy('Point to translation instructions URL')),
)

class Project(models.Model):
    name = models.CharField(max_length = 100)
    slug = models.SlugField(db_index = True)
    web = models.URLField()
    mail = models.EmailField(blank = True)
    instructions = models.URLField(blank = True)
    new_lang = models.CharField(
        max_length = 10,
        choices = NEW_LANG_CHOICES,
        default = 'contact'
    )

    # VCS config
    commit_message = models.CharField(
        max_length = 200,
        help_text = ugettext_lazy('You can use %(language)s, %(subproject)s or %(project)s for language shortcut, subproject or project names.'),
        validators = [validate_commit_message],
        default = 'Translated using Weblate.'
    )
    committer_name = models.CharField(
        max_length = 200,
        default = 'Weblate'
    )
    committer_email = models.EmailField(
        default = 'noreply@weblate.org'
    )

    push_on_commit = models.BooleanField(
        default = False,
        help_text = ugettext_lazy('Whether the repository should be pushed upstream on every commit.'),
    )

    set_translation_team = models.BooleanField(
        default = True,
        help_text = ugettext_lazy('Whether the Translation-Team in file headers should be updated by Weblate.'),
    )

    class Meta:
        ordering = ['name']

    def clean(self):
        if self.new_lang == 'url' and self.instructions == '':
            raise ValidationError(_('Please either fill in instructions URL or use different option for adding new language.'))

    @models.permalink
    def get_absolute_url(self):
        return ('weblate.trans.views.show_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_commit_url(self):
        return ('weblate.trans.views.commit_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_update_url(self):
        return ('weblate.trans.views.update_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_push_url(self):
        return ('weblate.trans.views.push_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_reset_url(self):
        return ('weblate.trans.views.reset_project', (), {
            'project': self.slug
        })

    def is_git_lockable(self):
        return True

    def is_git_locked(self):
        return max([sp.locked for sp in self.subproject_set.all()])

    @models.permalink
    def get_lock_url(self):
        return ('weblate.trans.views.lock_project', (), {
            'project': self.slug
        })

    @models.permalink
    def get_unlock_url(self):
        return ('weblate.trans.views.unlock_project', (), {
            'project': self.slug
        })

    def get_path(self):
        return os.path.join(settings.GIT_ROOT, self.slug)

    def __unicode__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Create filesystem directory for storing data
        p = self.get_path()
        if not os.path.exists(p):
            os.makedirs(p)

        super(Project, self).save(*args, **kwargs)

    def get_translated_percent(self):
        translations = Translation.objects.filter(subproject__project = self).aggregate(Sum('translated'), Sum('total'))
        if translations['total__sum'] == 0:
            return 0
        return round(translations['translated__sum'] * 100.0 / translations['total__sum'], 1)

    def get_total(self):
        '''
        Calculates total number of strings to translate. This is done based on assumption that
        all languages have same number of strings.
        '''
        total = 0
        for p in self.subproject_set.all():
            try:
                total += p.translation_set.all()[0].total
            except Translation.DoesNotExist:
                pass
        return total

    def get_language_count(self):
        '''
        Returns number of languages used in this project.
        '''
        return Language.objects.filter( translation__subproject__project = self).distinct().count()

    def git_needs_commit(self):
        '''
        Checks whether there are some not commited changes.
        '''
        for s in self.subproject_set.all():
            if s.git_needs_commit():
                return True
        return False

    def git_needs_pull(self, gitrepo = None):
        for s in self.subproject_set.all():
            if s.git_needs_pull():
                return True
        return False

    def git_needs_push(self, gitrepo = None):
        for s in self.subproject_set.all():
            if s.git_needs_push():
                return True
        return False

    def commit_pending(self):
        '''
        Commits any pending changes.
        '''
        for s in self.subproject_set.all():
            s.commit_pending()

    def do_update(self, request = None):
        '''
        Updates all git repos.
        '''
        ret = True
        for s in self.subproject_set.all():
            ret &= s.do_update(request)
        return ret

    def do_push(self, request = None):
        '''
        Pushes all git repos.
        '''
        ret = True
        for s in self.subproject_set.all():
            ret |= s.do_push(request)
        return ret

    def do_reset(self, request = None):
        '''
        Pushes all git repos.
        '''
        ret = True
        for s in self.subproject_set.all():
            ret |= s.do_reset(request)
        return ret

    def can_push(self):
        '''
        Checks whether any suprojects can push.
        '''
        ret = False
        for s in self.subproject_set.all():
            ret |= s.can_push()
        return ret

class SubProject(models.Model):
    name = models.CharField(
        max_length = 100,
        help_text = ugettext_lazy('Name to display')
    )
    slug = models.SlugField(
        db_index = True,
        help_text = ugettext_lazy('Name used in URLs')
        )
    project = models.ForeignKey(Project)
    repo = models.CharField(
        max_length = 200,
        help_text = ugettext_lazy('URL of Git repository, use weblate://project/subproject for sharing with other subproject'),
        validators = [validate_repo],
    )
    push = models.CharField(
        max_length = 200,
        help_text = ugettext_lazy('URL of push Git repository'),
        blank = True
    )
    repoweb = models.URLField(
        help_text = ugettext_lazy('Link to repository browser, use %(branch)s for branch, %(file)s and %(line)s as filename and line placeholders'),
        validators = [validate_repoweb],
        blank = True,
    )
    branch = models.CharField(
        max_length = 50,
        help_text = ugettext_lazy('Git branch to translate')
    )
    filemask = models.CharField(
        max_length = 200,
        validators = [validate_filemask],
        help_text = ugettext_lazy('Path of files to translate, use * instead of language code, for example: po/*.po or locale/*/LC_MESSAGES/django.po')
    )
    template = models.CharField(
        max_length = 200,
        blank = True,
        help_text = ugettext_lazy('Filename of translations template, this is recommended to use for translations which store only translated string like Android resource strings')
    )
    locked = models.BooleanField(
        default = False,
        help_text = ugettext_lazy('Whether subproject is locked for translation updates')
    )

    class Meta:
        ordering = ['project__name', 'name']
        permissions = (
            ('lock_subproject', "Can lock translation for translating"),
        )

    @models.permalink
    def get_absolute_url(self):
        return ('weblate.trans.views.show_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_commit_url(self):
        return ('weblate.trans.views.commit_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_update_url(self):
        return ('weblate.trans.views.update_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_push_url(self):
        return ('weblate.trans.views.push_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_reset_url(self):
        return ('weblate.trans.views.reset_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    def is_git_lockable(self):
        return True

    def is_git_locked(self):
        return self.locked

    @models.permalink
    def get_lock_url(self):
        return ('weblate.trans.views.lock_subproject', (), {
            'project': self.project.slug,
            'subproject': self.slug
        })

    @models.permalink
    def get_unlock_url(self):
        return ('weblate.trans.views.unlock_subproject', (), {
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
            return self.get_linked_repo().get_path()

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
        if not hasattr(self, '__lock__'):
            self.__lock__ = FileLock(self.get_git_lock_path())
        return self.__lock__

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

    def get_linked_repo(self):
        '''
        Returns subproject for linked repo.
        '''
        return get_linked_repo(self.repo)

    def get_repo(self):
        '''
        Gets Git repository object.
        '''
        p = self.get_path()
        try:
            return git.Repo(p)
        except:
            return git.Repo.init(p)

    def get_repoweb_link(self, filename, line):
        '''
        Generates link to source code browser for given file and line.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().get_repoweb_link(filename, line)

        if self.repoweb == '' or self.repoweb is None:
            return None

        return self.repoweb % {
            'file': filename,
            'line': line,
            'branch': self.branch
        }

    def pull_repo(self, validate = False, gitrepo = None):
        '''
        Pulls from remote repository.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().pull_repo(validate, gitrepo)

        if gitrepo is None:
            gitrepo = self.get_repo()

        # Update
        logger.info('updating repo %s', self.__unicode__())
        try:
            try:
                gitrepo.git.remote('update', 'origin')
            except git.GitCommandError:
                # There might be another attempt on pull in same time
                # so we will sleep a bit an retry
                time.sleep(random.random() * 2)
                gitrepo.git.remote('update', 'origin')
        except Exception, e:
            logger.error('Failed to update Git repo: %s', str(e))
            if validate:
                raise ValidationError(_('Failed to fetch git repository: %s') % str(e))

    def configure_repo(self, validate = False):
        '''
        Ensures repository is correctly configured and points to current remote.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().configure_repo(validate)
        # Create/Open repo
        gitrepo = self.get_repo()
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
        self.pull_repo(validate, gitrepo)


    def configure_branch(self):
        '''
        Ensures local tracking branch exists and is checkouted.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().configure_branch()

        gitrepo = self.get_repo()

        # create branch if it does not exist
        if not self.branch in gitrepo.heads:
            gitrepo.git.branch('--track', self.branch, 'origin/%s' % self.branch)

        # switch to correct branch
        gitrepo.git.checkout(self.branch)

    def do_update(self, request = None):
        '''
        Wrapper for doing repository update and pushing them to translations.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().do_update(request)

        # pull remote
        self.pull_repo()

        # do we have something to merge?
        if not self.git_needs_pull():
            return True

        # commit possible pending changes
        self.commit_pending()

        # update remote branc
        ret = self.update_branch(request)

        # create translation objects for all files
        self.create_translations()

        return ret

    def do_push(self, request = None, force_commit = True):
        '''
        Wrapper for pushing changes to remote repo.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().do_push(request)

        # Do we have push configured
        if not self.can_push():
            messages.error(request, _('Push is disabled for %s.') % self.__unicode__())
            return False

        # Commit any pending changes
        if force_commit:
            self.commit_pending()

        # Do we have anything to push?
        if not self.git_needs_push():
            return False

        # Update the repo
        self.do_update(request)

        # Were all changes merged?
        if self.git_needs_pull():
            return False

        # Do actual push
        gitrepo = self.get_repo()
        try:
            logger.info('pushing to remote repo %s', self.__unicode__())
            gitrepo.git.push('origin', '%s:%s' % (self.branch, self.branch))
            return True
        except Exception, e:
            logger.warning('failed push on repo %s', self.__unicode__())
            msg = 'Error:\n%s' % str(e)
            mail_admins(
                'failed push on repo %s' % self.__unicode__(),
                msg
            )
            if request is not None:
                messages.error(request, _('Failed to push to remote branch on %s.') % self.__unicode__())
            return False

    def do_reset(self, request = None):
        '''
        Wrapper for reseting repo to same sources as remote.
        '''
        if self.is_repo_link():
            return self.get_linked_repo().do_reset(request)

        # First check we're up to date
        self.pull_repo()

        # Do actual reset
        gitrepo = self.get_repo()
        try:
            logger.info('reseting to remote repo %s', self.__unicode__())
            gitrepo.git.reset('--hard', 'origin/%s' % self.branch)
        except Exception, e:
            logger.warning('failed reset on repo %s', self.__unicode__())
            msg = 'Error:\n%s' % str(e)
            mail_admins(
                'failed reset on repo %s' % self.__unicode__(),
                msg
            )
            if request is not None:
                messages.error(request, _('Failed to reset to remote branch on %s.') % self.__unicode__())
            return False

        # create translation objects for all files
        self.create_translations()

        return True

    def get_linked_childs(self):
        '''
        Returns list of subprojects which link repository to us.
        '''
        return SubProject.objects.filter(repo = 'weblate://%s/%s' % (self.project.slug, self.slug))

    def commit_pending(self, from_link = False):
        '''
        Checks whether there is any translation which needs commit.
        '''
        if not from_link and self.is_repo_link():
            return self.get_linked_repo().commit_pending(True)

        for translation in self.translation_set.all():
            translation.commit_pending()

        # Process linked projects
        for sp in self.get_linked_childs():
            sp.commit_pending(True)

    def update_branch(self, request = None):
        '''
        Updates current branch to match remote (if possible).
        '''
        if self.is_repo_link():
            return self.get_linked_repo().update_branch(request)

        gitrepo = self.get_repo()

        # Merge with lock acquired
        with self.get_git_lock():
            try:
                # Try to merge it
                gitrepo.git.merge('origin/%s' % self.branch)
                logger.info('merged remote into repo %s', self.__unicode__())
                return True
            except Exception, e:
                # In case merge has failer recover and tell admins
                status = gitrepo.git.status()
                gitrepo.git.merge('--abort')
                logger.warning('failed merge on repo %s', self.__unicode__())
                msg = 'Error:\n%s' % str(e)
                msg += '\n\nStatus:\n' + status
                mail_admins(
                    'failed merge on repo %s' % self.__unicode__(),
                    msg
                )
                if request is not None:
                    messages.error(request, _('Failed to merge remote branch into %s.') % self.__unicode__())
                return False

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
        gitrepo = self.get_repo()
        tree = gitrepo.tree()

        # Glob files
        for filename in self.get_mask_matches():
            yield (
                self.get_lang_code(filename),
                filename,
                tree[filename].hexsha
                )

    def create_translations(self, force = False):
        '''
        Loads translations from git.
        '''
        for code, path, blob_hash in self.get_translation_blobs():
            logger.info('checking %s', path)
            Translation.objects.update_from_blob(self, code, path, blob_hash, force)

        # Process linked repos
        for sp in self.get_linked_childs():
            sp.create_translations(force)

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

    def sync_git_repo(self, validate = False):
        '''
        Brings git repo in sync with current model.
        '''
        if self.is_repo_link():
            return
        self.configure_repo(validate)
        self.configure_branch()
        self.commit_pending()
        self.pull_repo()
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

        try:
            matches = self.get_mask_matches()
            if len(matches) == 0:
                raise ValidationError(_('The mask did not match any files!'))
            langs = {}
            for match in matches:
                code = self.get_lang_code(match)
                if code in langs:
                    raise ValidationError(_('There are more files for single language, please adjust the mask and use subprojects for translating different resources.'))
                langs[code] = match

            # Try parsing files
            notrecognized = []
            errors = []
            for match in matches:
                try:
                    ttkit(os.path.join(self.get_path(), match))
                except ValueError:
                    notrecognized.append(match)
                except Exception, e:
                    errors.append('%s: %s' % (match, str(e)))
            if len(notrecognized) > 0:
                raise ValidationError( '%s\n%s' % (
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
                template = os.path.join(self.get_path(), self.template)
                try:
                    ttkit(os.path.join(self.get_path(), match))
                except ValueError:
                    raise ValidationError(_('Format of translation template could not be recognized.'))
                except Exception, e:
                    raise ValidationError(_('Failed to parse translation template.'))
        except SubProject.DoesNotExist:
            # Happens with invalid link
            pass

    def save(self, *args, **kwargs):
        '''
        Save wrapper which updates backend Git repository and regenerates
        translation data.
        '''
        # Detect if git config has changed (so that we have to pull the repo)
        changed_git = True
        if (self.id):
            old = SubProject.objects.get(pk = self.id)
            changed_git = (old.repo != self.repo) or (old.branch != self.branch) or (old.filemask != self.filemask)

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
        translations = self.translation_set.aggregate(Sum('translated'), Sum('total'))
        if translations['total__sum'] == 0:
            return 0
        return round(translations['translated__sum'] * 100.0 / translations['total__sum'], 1)

    def git_needs_commit(self, gitrepo = None):
        '''
        Checks whether there are some not commited changes.
        '''
        if gitrepo is None:
            gitrepo = self.get_repo()
        status = gitrepo.git.status('--porcelain')
        if status == '':
            # No changes to commit
            return False
        return True

    def git_check_merge(self, revision, gitrepo = None):
        '''
        Checks whether there are any unmerged commits compared to given
        revision.
        '''
        if gitrepo is None:
            gitrepo = self.get_repo()
        status = gitrepo.git.log(revision, '--')
        if status == '':
            # No changes to merge
            return False
        return True

    def git_needs_pull(self, gitrepo = None):
        return self.git_check_merge('..origin/%s' % self.branch, gitrepo)

    def git_needs_push(self, gitrepo = None):
        return self.git_check_merge('origin/%s..' % self.branch, gitrepo)


class Translation(models.Model):
    subproject = models.ForeignKey(SubProject)
    language = models.ForeignKey(Language)
    revision = models.CharField(max_length = 40, default = '', blank = True)
    filename = models.CharField(max_length = 200)

    translated = models.IntegerField(default = 0, db_index = True)
    fuzzy = models.IntegerField(default = 0, db_index = True)
    total = models.IntegerField(default = 0, db_index = True)

    enabled = models.BooleanField(default = True, db_index = True)

    language_code = models.CharField(max_length = 20, default = '')

    lock_user = models.ForeignKey(User, null = True, blank = True, default = None)
    lock_time = models.DateTimeField(default = datetime.now)

    objects = TranslationManager()

    class Meta:
        ordering = ['language__name']
        permissions = (
            ('upload_translation', "Can upload translation"),
            ('overwrite_translation', "Can overwrite with translation upload"),
            ('author_translation', "Can define author of translation upload"),
            ('commit_translation', "Can force commiting of translation"),
            ('update_translation', "Can update translation from git"),
            ('push_translation', "Can push translations to remote git"),
            ('reset_translation', "Can reset translations to match remote git"),
            ('automatic_translation', "Can do automatic translation"),
            ('lock_translation', "Can lock whole translation project"),
        )

    def clean(self):
        '''
        Validates that filename exists and can be opened using ttkit.
        '''
        if not os.path.exists(self.get_filename()):
            raise ValidationError(_('Filename %s not found in repository! To add new translation, add language file into repository.') % self.filename)
        try:
            self.get_store()
        except ValueError:
            raise ValidationError(_('Format of %s could not be recognized.') % self.filename)
        except Exception, e:
            raise ValidationError(_('Failed to parse file %(file)s: %(error)s') % {
                'file': self.filename,
                'error': str(e)
            })

    def get_fuzzy_percent(self):
        if self.total == 0:
            return 0
        return round(self.fuzzy * 100.0 / self.total, 1)

    def get_translated_percent(self):
        if self.total == 0:
            return 0
        return round(self.translated * 100.0 / self.total, 1)

    def is_locked(self, request = None):
        '''
        Check whether the translation is locked and
        possibly emmits messages if request object is
        provided.
        '''

        # Check for project lock
        if self.subproject.locked:
            if request is not None:
                messages.error(request, _('This translation is currently locked for updates!'))
            return True

        # Check for translation lock
        if self.is_user_locked(request):
            if request is not None:
                messages.error(
                    request,
                    _('This translation is locked by %(user)s for translation till %(time)s!') % {
                        'user': self.lock_user.get_full_name(),
                        'time': date_format(self.lock_time, 'DATETIME_FORMAT')
                    }
                )
            return True

        return False

    def is_user_locked(self, request = None):
        '''
        Checks whether there is valid user lock on this translation.
        '''
        # Any user?
        if self.lock_user is None:
            return False

        # Is lock still valid?
        if self.lock_time < datetime.now():
            # Clear the lock
            self.lock_user = None
            self.save()

            return False

        # Is current user the one who has locked?
        if request is not None and self.lock_user == request.user:
            return False

        return True

    def create_lock(self, user):
        '''
        Creates lock on translation.
        '''
        self.lock_user = user
        self.update_lock_time()

    def update_lock_time(self):
        '''
        Sets lock timestamp.
        '''
        self.lock_time = datetime.now() + timedelta(seconds = settings.LOCK_TIME)
        self.save()

    def update_lock(self, request):
        '''
        Updates lock timestamp.
        '''
        # Update timestamp
        if self.is_user_locked():
            self.update_lock_time()
            return

        # Auto lock if we should
        if settings.AUTO_LOCK:
            self.create_lock(request.user)
            return

    def get_non_translated(self):
        return self.total - self.translated

    @models.permalink
    def get_absolute_url(self):
        return ('weblate.trans.views.show_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_commit_url(self):
        return ('weblate.trans.views.commit_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_update_url(self):
        return ('weblate.trans.views.update_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_push_url(self):
        return ('weblate.trans.views.push_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_reset_url(self):
        return ('weblate.trans.views.reset_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    def is_git_lockable(self):
        return False

    @models.permalink
    def get_lock_url(self):
        return ('weblate.trans.views.lock_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_unlock_url(self):
        return ('weblate.trans.views.unlock_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_download_url(self):
        return ('weblate.trans.views.download_translation', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    @models.permalink
    def get_translate_url(self):
        return ('weblate.trans.views.translate', (), {
            'project': self.subproject.project.slug,
            'subproject': self.subproject.slug,
            'lang': self.language.code
        })

    def __unicode__(self):
        return '%s - %s' % (self.subproject.__unicode__(), _(self.language.name))

    def get_filename(self):
        '''
        Returns absolute filename.
        '''
        return os.path.join(self.subproject.get_path(), self.filename)

    def get_store(self):
        '''
        Returns ttkit storage object for a translation.
        '''
        store = ttkit(self.get_filename())
        if hasattr(store, 'set_base_resource') and self.subproject.template != '':
            template = os.path.join(self.subproject.get_path(), self.subproject.template)
            store.set_base_resource(template)
        return store

    def check_sync(self):
        '''
        Checks whether database is in sync with git and possibly does update.
        '''
        self.update_from_blob()

    def update_from_blob(self, blob_hash = None, force = False):
        '''
        Updates translation data from blob.
        '''
        if blob_hash is None:
            blob_hash = self.get_git_blob_hash()

        # Check if we're not already up to date
        if self.revision == blob_hash and not force:
            return

        logger.info(
            'processing %s in %s, revision has changed',
            self.filename,
            self.subproject.__unicode__()
        )

        oldunits = set(self.unit_set.all().values_list('id', flat = True))

        # Load po file
        store = self.get_store()
        was_new = False
        for pos, unit in enumerate(store.units):
            # We care only about translatable strings
            # For some reason, blank string does not mean non translatable
            # unit in some formats (XLIFF), so let's skip those as well
            if not unit.istranslatable() or unit.isblank():
                continue
            newunit, is_new = Unit.objects.update_from_unit(self, unit, pos)
            was_new = was_new or is_new
            try:
                oldunits.remove(newunit.id)
            except:
                pass

        # Delete not used units
        units_to_delete = Unit.objects.filter(translation = self, id__in = oldunits)
        deleted_checksums = units_to_delete.values_list('checksum', flat = True)
        units_to_delete.delete()

        # Cleanup checks for deleted units
        for checksum in deleted_checksums:
            units = Unit.objects.filter(translation__language = self.language, translation__subproject__project = self.subproject.project, checksum = checksum)
            if units.count() == 0:
                # Last unit referencing to these checks
                Check.objects.filter(project = self.subproject.project, language = self.language, checksum = checksum).delete()
                # Delete suggestons referencing this unit
                Suggestion.objects.filter(project = self.subproject.project, language = self.language, checksum = checksum).delete()
            else:
                # There are other units as well, but some checks (eg. consistency) needs update now
                for unit in units:
                    unit.check()

        # Update revision and stats
        self.update_stats(blob_hash)

        # Notify subscribed users
        if was_new:
            from weblate.accounts.models import Profile
            subscriptions = Profile.objects.subscribed_new_string(self.subproject.project, self.language)
            for subscription in subscriptions:
                subscription.notify_new_string(self)

    def get_repo(self):
        return self.subproject.get_repo()

    def do_update(self, request = None):
        return self.subproject.do_update(request)

    def do_push(self, request = None):
        return self.subproject.do_push(request)

    def do_reset(self, request = None):
        return self.subproject.do_reset(request)

    def can_push(self):
        return self.subproject.can_push()

    def get_git_blob_hash(self):
        '''
        Returns current Git blob hash for file.
        '''
        gitrepo = self.get_repo()
        tree = gitrepo.tree()
        ret = tree[self.filename].hexsha
        return ret

    def update_stats(self, blob_hash = None):
        '''
        Updates translation statistics.
        '''
        self.total = self.unit_set.count()
        self.fuzzy = self.unit_set.filter(fuzzy = True).count()
        self.translated = self.unit_set.filter(translated = True).count()
        self.save()
        self.store_hash()

    def store_hash(self, blob_hash = None):
        '''
        Stores current hash in database.
        '''
        if blob_hash is None:
            blob_hash = self.get_git_blob_hash()
        self.revision = blob_hash
        self.save()

    def get_last_author(self, email = True):
        '''
        Returns last autor of change done in Weblate.
        '''
        try:
            change = Change.objects.filter(unit__translation = self).order_by('-timestamp')[0]
            return self.get_author_name(change.user, email)
        except IndexError:
            return None

    def get_last_change(self):
        '''
        Returns date of last change done in Weblate.
        '''
        try:
            change = Change.objects.filter(unit__translation = self).order_by('-timestamp')[0]
            return change.timestamp
        except IndexError:
            return None

    def commit_pending(self, author = None):
        '''
        Commits any pending changes.
        '''
        # Get author of last changes
        last = self.get_last_author()

        # If it is same as current one, we don't have to commit
        if author == last or last is None:
            return

        # Commit changes
        self.git_commit(last, self.get_last_change(), True, True)

    def get_author_name(self, user, email = True):
        '''
        Returns formatted author name with email.
        '''

        # Get full name from database
        full_name = user.get_full_name()

        # Use username if full name is empty
        if full_name == '':
            full_name = user.username

        # Add email if we are asked for it
        if not email:
            return full_name
        return '%s <%s>' % (full_name, user.email)

    def get_commit_message(self):
        '''
        Formats commit message based on project configuration.
        '''
        return self.subproject.project.commit_message % {
            'language': self.language_code,
            'subproject': self.subproject.name,
            'project': self.subproject.project.name,
        }

    def __configure_conf(self, gitrepo, section, key, expected):
        '''
        Adjysts git config to ensure that section.key is set to expected.
        '''
        cnf = gitrepo.config_writer()
        try:
            # Get value and if it matches we're done
            value = cnf.get(section, key)
            if value == expected:
                return
        except:
            pass

        # Try to add section (might fail if it exists)
        try:
            cnf.add_section(section)
        except:
            pass
        # Update config
        cnf.set(section, key, expected)

    def __configure_committer(self, gitrepo):
        '''
        Wrapper for setting proper committer. As this can not be done by
        passing parameter, we need to check config on every commit.
        '''
        self.__configure_conf(gitrepo, 'user', 'name', self.subproject.project.committer_name)
        self.__configure_conf(gitrepo, 'user', 'email', self.subproject.project.committer_email)

    def __git_commit(self, gitrepo, author, timestamp, sync = False):
        '''
        Commits translation to git.
        '''
        # Check git config
        self.__configure_committer(gitrepo)

        # Format commit message
        msg = self.get_commit_message()

        # Do actual commit
        gitrepo.git.commit(
            self.filename,
            author = author.encode('utf-8'),
            date = timestamp.isoformat(),
            m = msg
        )

        # Optionally store updated hash
        if sync:
            self.store_hash()

    def git_needs_commit(self, gitrepo = None):
        '''
        Checks whether there are some not commited changes.
        '''
        if gitrepo is None:
            gitrepo = self.get_repo()
        status = gitrepo.git.status('--porcelain', '--', self.filename)
        if status == '':
            # No changes to commit
            return False
        return True

    def git_needs_pull(self):
        return self.subproject.git_needs_pull()

    def git_needs_push(self):
        return self.subproject.git_needs_push()

    def git_commit(self, author, timestamp, force_commit = False, sync = False):
        '''
        Wrapper for commiting translation to git.

        force_commit forces commit with lazy commits enabled

        sync updates git hash stored within the translation (otherwise
        translation rescan will be needed)
        '''
        gitrepo = self.get_repo()

        # Is there something for commit?
        if not self.git_needs_commit(gitrepo):
            return False

        # Can we delay commit?
        if not force_commit and settings.LAZY_COMMITS:
            logger.info('Delaying commiting %s in %s as %s', self.filename, self, author)
            return False

        # Do actual commit with git lock
        logger.info('Commiting %s in %s as %s', self.filename, self, author)
        with self.subproject.get_git_lock():
            try:
                self.__git_commit(gitrepo, author, timestamp, sync)
            except git.GitCommandError:
                # There might be another attempt on commit in same time
                # so we will sleep a bit an retry
                time.sleep(random.random() * 2)
                self.__git_commit(gitrepo, author, timestamp, sync)

        # Push if we should
        if self.subproject.project.push_on_commit:
            self.subproject.do_push(force_commit = False)

        return True

    def update_unit(self, unit, request):
        '''
        Updates backend file and unit.
        '''
        # Save with lock acquired
        with self.subproject.get_git_lock():

            store = self.get_store()
            src = unit.get_source_plurals()[0]
            need_save = False
            found = False
            # Find all units with same source
            for pounit in store.findunits(src):
                # Does context match?
                if pounit.getcontext() == unit.context:
                    found = True
                    # Is it plural?
                    if hasattr(pounit.target, 'strings'):
                        potarget = join_plural(pounit.target.strings)
                    else:
                        potarget = pounit.target
                    # Is there any change
                    if unit.target != potarget or unit.fuzzy != pounit.isfuzzy():
                        # Update fuzzy flag
                        pounit.markfuzzy(unit.fuzzy)
                        # Store translations
                        if unit.is_plural():
                            pounit.settarget(unit.get_target_plurals())
                        else:
                            pounit.settarget(unit.target)
                        # We need to update backend
                        need_save = True
                    # We should have only one match
                    break

            if not found:
                return False, None

            # Save backend if there was a change
            if need_save:
                author = self.get_author_name(request.user)
                # Update po file header
                if hasattr(store, 'updateheader'):
                    po_revision_date = datetime.now().strftime('%Y-%m-%d %H:%M') + poheader.tzstring()

                    store.updateheader(
                        add = True,
                        last_translator = author,
                        plural_forms = self.language.get_plural_form(),
                        language = self.language_code,
                        PO_Revision_Date = po_revision_date,
                        x_generator = 'Weblate %s' % weblate.VERSION
                        )
                    if self.subproject.project.set_translation_team:
                        site = Site.objects.get_current()
                        store.updateheader(
                            language_team = '%s <http://%s%s>' % (
                                self.language.name,
                                site.domain,
                                self.get_absolute_url(),
                            )
                        )
                # commit possible previous changes (by other author)
                self.commit_pending(author)
                # save translation changes
                store.save()
                # commit Git repo if needed
                self.git_commit(author, timezone.now(), sync = True)

        return need_save, pounit

    def get_translation_checks(self):
        '''
        Returns list of failing checks on current translation.
        '''
        result = [('all', _('All strings'))]
        nottranslated = self.unit_set.count_type('untranslated', self)
        fuzzy = self.unit_set.count_type('fuzzy', self)
        suggestions = self.unit_set.count_type('suggestions', self)
        allchecks = self.unit_set.count_type('allchecks', self)
        if nottranslated > 0:
            result.append(('untranslated', _('Not translated strings (%d)') % nottranslated))
        if fuzzy > 0:
            result.append(('fuzzy', _('Fuzzy strings (%d)') % fuzzy))
        if suggestions > 0:
            result.append(('suggestions', _('Strings with suggestions (%d)') % suggestions))
        if allchecks > 0:
            result.append(('allchecks', _('Strings with any failing checks (%d)') % allchecks))
        for check in CHECKS:
            cnt = self.unit_set.count_type(check, self)
            if cnt > 0:
                desc = CHECKS[check].description + (' (%d)' % cnt)
                result.append((check, desc))
        return result

    def merge_store(self, author, store2, overwrite, mergefuzzy = False, merge_header = True):
        '''
        Merges ttkit store into current translation.
        '''
        # Merge with lock acquired
        with self.subproject.get_git_lock():

            store1 = self.get_store()
            store1.require_index()

            for unit2 in store2.units:
                # No translated -> skip
                if len(unit2.target.strip()) == 0:
                    continue

                # Should we cope with fuzzy ones?
                if not mergefuzzy:
                    if unit2.isfuzzy():
                        continue

                # Optionally merge header
                if unit2.isheader():
                    if merge_header and isinstance(store1, poheader.poheader):
                        store1.mergeheaders(store2)
                    continue

                # Find unit by ID
                unit1 = store1.findid(unit2.getid())

                # Fallback to finding by source
                if unit1 is None:
                    unit1 = store1.findunit(unit2.source)

                # Unit not found, nothing to do
                if unit1 is None:
                    continue

                # Should we overwrite
                if not overwrite and unit1.istranslated():
                    continue

                # Actually update translation
                unit1.merge(unit2, overwrite=True, comments=False)

            # Write to backend and commit
            self.commit_pending(author)
            store1.save()
            ret = self.git_commit(author, timezone.now(), True)
            self.check_sync()

        return ret

    def merge_upload(self, request, fileobj, overwrite, author = None, mergefuzzy = False, merge_header = True):
        '''
        Top level handler for file uploads.
        '''
        store2 = ttkit(fileobj)
        if author is None:
            author = self.get_author_name(request.user)

        ret = False

        for s in Translation.objects.filter(language = self.language, subproject__project = self.subproject.project):
            ret |= s.merge_store(author, store2, overwrite, mergefuzzy, merge_header)

        return ret

    def get_failing_checks(self, check = 'allchecks'):
        '''
        Returns number of units with failing checks.

        By default for all checks or check type can be specified.
        '''
        return self.unit_set.count_type(check, self)

    def invalidate_cache(self, cache_type = None):
        '''
        Invalidates any cached stats.
        '''
        # Get parts of key cache
        slug = self.subproject.get_full_slug()
        code = self.language.code

        # Are we asked for specific cache key?
        if cache_type is None:
            keys = ['allchecks'] + list(CHECKS)
        else:
            keys = [cache_type]

        # Actually delete the cache
        for rqtype in keys:
            cache_key = 'counts-%s-%s-%s' % (slug, code, rqtype)
            cache.delete(cache_key)

class Unit(models.Model):
    translation = models.ForeignKey(Translation)
    checksum = models.CharField(max_length = 40, default = '', blank = True, db_index = True)
    location = models.TextField(default = '', blank = True)
    context = models.TextField(default = '', blank = True)
    comment = models.TextField(default = '', blank = True)
    flags = models.TextField(default = '', blank = True)
    source = models.TextField()
    target = models.TextField(default = '', blank = True)
    fuzzy = models.BooleanField(default = False, db_index = True)
    translated = models.BooleanField(default = False, db_index = True)
    position = models.IntegerField(db_index = True)

    objects = UnitManager()

    class Meta:
        permissions = (
            ('save_translation', "Can save translation"),
        )
        ordering = ['position']

    def __unicode__(self):
        return '%s on %s' % (
            self.checksum,
            self.translation,
        )

    def get_absolute_url(self):
        return '%s?pos=%d&dir=stay' % (self.translation.get_translate_url(), self.position)

    def update_from_unit(self, unit, pos, force):
        '''
        Updates Unit from ttkit unit.
        '''
        # Merge locations
        location = ', '.join(unit.getlocations())
        # Merge flags
        if hasattr(unit, 'typecomments'):
            flags = ', '.join(unit.typecomments)
        else:
            flags = ''
        # Merge target
        if hasattr(unit.target, 'strings'):
            target = join_plural(unit.target.strings)
        else:
            target = unit.target
        # Check for null target (happens with XLIFF)
        if target is None:
            target = ''

        # Get data from unit
        fuzzy = unit.isfuzzy()
        translated = unit.istranslated()
        comment = unit.getnotes()

        # Update checks on fuzzy update or on content change
        same_content = (target == self.target and fuzzy == self.fuzzy)

        # Check if we actually need to change anything
        if not force and location == self.location and flags == self.flags and same_content and fuzzy == self.fuzzy and translated == self.translated and comment == self.comment and pos == self.position:
            return

        # Store updated values
        self.position = pos
        self.location = location
        self.flags = flags
        self.target = target
        self.fuzzy = fuzzy
        self.translated = translated
        self.comment = comment
        self.save(force_insert = force, backend = True, same_content = same_content)

    def is_plural(self):
        '''
        Checks whether message is plural.
        '''
        return is_plural(self.source)

    def get_source_plurals(self):
        '''
        Retuns source plurals in array.
        '''
        return split_plural(self.source)

    def get_target_plurals(self):
        '''
        Returns target plurals in array.
        '''
        # Is this plural?
        if not self.is_plural():
            return [self.target]

        # Split plurals
        ret = split_plural(self.target)

        # Check if we have expected number of them
        plurals = self.translation.language.nplurals
        if len(ret) == plurals:
            return ret

        # Pad with empty translations
        while len(ret) < plurals:
            ret.append('')

        # Delete extra plurals
        while len(ret) > plurals:
            del(ret[-1])

        return ret

    def propagate(self, request):
        '''
        Propagates current translation to all others.
        '''
        allunits = Unit.objects.same(self).exclude(id = self.id)
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = self.fuzzy
            unit.save_backend(request, False)

    def save_backend(self, request, propagate = True, gen_change = True):
        '''
        Stores unit to backend.
        '''
        from weblate.accounts.models import Profile

        # Update lock timestamp
        self.translation.update_lock(request)

        # Store to backend
        (saved, pounit) = self.translation.update_unit(self, request)

        # Handle situation when backend did not find the message
        if pounit is None:
            logger.error('message %s disappeared!', self)
            messages.error(request, _('Message not found in backend storage, it is probably corrupted.'))
            return

        # Return if there was no change
        if not saved and propagate:
            self.propagate(request)
            return

        # Update translated flag
        self.translated = pounit.istranslated()

        # Update comments as they might have been changed (eg, fuzzy flag removed)
        if hasattr(pounit, 'typecomments'):
            self.flags = ', '.join(pounit.typecomments)
        else:
            self.flags = ''

        # Get old unit from database (for notifications)
        oldunit = Unit.objects.get(id = self.id)

        # Save updated unit to database
        self.save(backend = True)

        # Update translation stats
        old_translated = self.translation.translated
        self.translation.update_stats()

        # Notify subscribed users about new translation
        subscriptions = Profile.objects.subscribed_any_translation(
            self.translation.subproject.project,
            self.translation.language
        )
        for subscription in subscriptions:
            subscription.notify_any_translation(self, oldunit)

        # Force commiting on completing translation
        if old_translated < self.translation.translated and self.translation.translated == self.translation.total:
            self.translation.commit_pending()

        # Generate Change object for this change
        if gen_change:
            # Get list of subscribers for new contributor
            subscriptions = Profile.objects.subscribed_new_contributor(
                self.translation.subproject.project,
                self.translation.language
            )
            if subscriptions.exists():
                # Is this new contributor?
                if not Change.objects.filter(unit__translation = self.translation, user = request.user).exists():
                    # Notify subscribers
                    for subscription in subscriptions:
                        subscription.notify_new_contributor(self.translation, request.user)
            # Create change object
            Change.objects.create(unit = self, user = request.user)

        # Propagate to other projects
        if propagate:
            self.propagate(request)

    def save(self, *args, **kwargs):
        '''
        Wrapper around save to warn when save did not come from
        git backend (eg. commit or by parsing file).
        '''
        # Warn if request is not coming from backend
        if not 'backend' in kwargs:
            logger.error('Unit.save called without backend sync: %s', ''.join(traceback.format_stack()))
        else:
            del kwargs['backend']

        # Pop parameter indicating that we don't have to process content
        same_content = kwargs.pop('same_content', False)

        # Actually save the unit
        super(Unit, self).save(*args, **kwargs)

        # Update checks and fulltext index if content has changed
        if not same_content:
            self.check()
            Unit.objects.add_to_index(self)

    def get_location_links(self):
        '''
        Generates links to source files where translation was used.
        '''
        ret = []

        # Do we have any locations?
        if len(self.location) == 0:
            return ''

        # Is it just an ID?
        if self.location.isdigit():
            return _('unit ID %s') % self.location

        # Go through all locations separated by comma
        for location in self.location.split(','):
            location = location.strip()
            if location == '':
                continue
            location_parts = location.split(':')
            if len(location_parts) == 2:
                filename, line = location_parts
            else:
                filename = location_parts[0]
                line = 0
            link = self.translation.subproject.get_repoweb_link(filename, line)
            if link is None:
                ret.append('%s' % location)
            else:
                ret.append('<a href="%s">%s</a>' % (link, location))
        return mark_safe('\n'.join(ret))

    def suggestions(self):
        '''
        Returns all suggestions for this unit.
        '''
        return Suggestion.objects.filter(
            checksum = self.checksum,
            project = self.translation.subproject.project,
            language = self.translation.language
        )

    def checks(self):
        '''
        Returns all checks for this unit (even ignored).
        '''
        return Check.objects.filter(
            checksum = self.checksum,
            project = self.translation.subproject.project,
            language = self.translation.language
        )

    def active_checks(self):
        '''
        Returns all active (not ignored) checks for this unit.
        '''
        return Check.objects.filter(
            checksum = self.checksum,
            project = self.translation.subproject.project,
            language = self.translation.language,
            ignore = False
        )

    def check(self):
        '''
        Updates checks for this unit.
        '''
        if self.fuzzy:
            self.checks().delete()
            return
        src = self.get_source_plurals()
        tgt = self.get_target_plurals()
        failing = []

        change = False

        # Run all checks
        for check in CHECKS:
            if CHECKS[check].check(src, tgt, self.flags, self.translation.language, self):
                failing.append(check)

        # Compare to existing checks, delete non failing ones
        for check in self.checks():
            if check.check in failing:
                failing.remove(check.check)
                continue
            check.delete()
            change = True

        # Store new checks in database
        for check in failing:
            Check.objects.create(
                checksum = self.checksum,
                project = self.translation.subproject.project,
                language = self.translation.language,
                ignore = False,
                check = check
            )
            change = True

        # Invalidate checks cache
        if change:
            self.translation.invalidate_cache()

    def nearby(self):
        '''
        Returns list of nearby messages based on location.
        '''
        return Unit.objects.filter(
            translation = self.translation,
            position__gte = self.position - settings.NEARBY_MESSAGES,
            position__lte = self.position + settings.NEARBY_MESSAGES,
        )

class Suggestion(models.Model):
    checksum = models.CharField(max_length = 40, default = '', blank = True, db_index = True)
    target = models.TextField()
    user = models.ForeignKey(User, null = True, blank = True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)

    class Meta:
        permissions = (
            ('accept_suggestion', "Can accept suggestion"),
        )

    def accept(self, request):
        allunits = Unit.objects.filter(
            checksum = self.checksum,
            translation__subproject__project = self.project,
            translation__language = self.language
        )
        for unit in allunits:
            unit.target = self.target
            unit.fuzzy = False
            unit.save_backend(request, False)

    def get_matching_unit(self):
        '''
        Retrieves one (possibly out of several) unit matching
        this suggestion.
        '''
        return Unit.objects.filter(
            checksum = self.checksum,
            translation__subproject__project = self.project,
            translation__language = self.language,
        )[0]

    def get_source(self):
        '''
        Returns source strings matching this suggestion.
        '''
        return self.get_matching_unit().source

    def get_review_url(self):
        '''
        Returns URL which can be used for review.
        '''
        return self.get_matching_unit().get_absolute_url()


CHECK_CHOICES = [(x, CHECKS[x].name) for x in CHECKS]

class Check(models.Model):
    checksum = models.CharField(max_length = 40, default = '', blank = True, db_index = True)
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)
    check = models.CharField(max_length = 20, choices = CHECK_CHOICES)
    ignore = models.BooleanField(db_index = True)

    class Meta:
        permissions = (
            ('ignore_check', "Can ignore check results"),
        )

    def __unicode__(self):
        return '%s/%s: %s' % (
            self.project,
            self.language,
            self.check,
        )

    def get_description(self):
        return CHECKS[self.check].description

    def get_doc_url(self):
        return CHECKS[self.check].get_doc_url()

class Dictionary(models.Model):
    project = models.ForeignKey(Project)
    language = models.ForeignKey(Language)
    source = models.CharField(max_length = 200, db_index = True)
    target = models.CharField(max_length = 200)

    objects = DictionaryManager()

    class Meta:
        ordering = ['source']
        permissions = (
            ('upload_dictionary', "Can import dictionary"),
        )

    def __unicode__(self):
        return '%s/%s: %s -> %s' % (
            self.project,
            self.language,
            self.source,
            self.target
        )

class Change(models.Model):
    unit = models.ForeignKey(Unit)
    user = models.ForeignKey(User)
    timestamp = models.DateTimeField(auto_now_add = True, db_index = True)

    class Meta:
        ordering = ['-timestamp']

    def __unicode__(self):
        return u'%s on %s by %s' % (
            self.unit,
            self.timestamp,
            self.user,
        )

class IndexUpdate(models.Model):
    unit = models.ForeignKey(Unit)

def get_versions():
    '''
    Returns list of used versions.
    '''
    import translate.__version__
    import whoosh
    import django
    import git
    import cairo
    import south
    import registration
    return {
        'ttkit_version': translate.__version__.sver,
        'whoosh_version': whoosh.versionstring(),
        'django_version': django.get_version(),
        'registration_version': registration.get_version(),
        'git_python_version': git.__version__,
        'git_version': git.Git().version().replace('git version ', ''),
        'cairo_version': cairo.version,
        'south_version': south.__version__,
    }

def check_version(versions, key, expected, description):
    '''
    Check for single module version.
    '''
    if LooseVersion(versions[key]) < expected:
        print '*** %s is too old! ***' % description
        print 'Installed version %s, required %s' % (versions[key], expected)
        return True
    return False

def check_versions(sender, **kwargs):
    '''
    Check required versions.
    '''
    if ('app' in kwargs and kwargs['app'] == 'trans') or (sender is not None and sender.__name__ == 'weblate.trans.models'):
        versions = get_versions()
        failure = False

        failure |= check_version(
            versions,
            'ttkit_version',
            '1.9.0',
            'Translate-toolkit <http://translate.sourceforge.net/wiki/toolkit/index>'
        )

        failure |= check_version(
            versions,
            'git_python_version',
            '0.3',
            'GitPython <https://github.com/gitpython-developers/GitPython>'
        )

        failure |= check_version(
            versions,
            'registration_version',
            '0.8',
            'Django-registration <https://bitbucket.org/ubernostrum/django-registration/>'
        )

        failure |= check_version(
            versions,
            'whoosh_version',
            '2.3',
            'Whoosh <http://bitbucket.org/mchaput/whoosh/>'
        )

        failure |= check_version(
            versions,
            'cairo_version',
            '1.8',
            'PyCairo <http://cairographics.org/pycairo/>'
        )

        if failure:
            raise Exception('Some of required modules are missing or too old (check output above)!')

post_syncdb.connect(check_versions)
post_migrate.connect(check_versions)
