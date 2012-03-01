Weblate
=======

Weblate is web based translation tool. It is based on translate-toolkit and
heavily uses git backed to store project.

Project goals
-------------

Minimalistic web based translation with direct commit to git on each
translation made. There is no plan in heavy conflict resolution as these
should be primarily handled on git side.

Planned features
----------------

* Easy web based translation
* Propagation of translations accross sub-projects (for different branches)
* Tight git integration
* Usage of Django's admin interface
* Upload and automatic merging of po files
* Links to source files for context

Requirements
------------

Django
    https://www.djangoproject.com/
Translate-toolkit
    http://translate.sourceforge.net/wiki/toolkit/index
GitPython (>= 0.3)
    http://gitorious.org/projects/git-python/

Installation
------------

Install all required components (see above), adjust settings.py and then run
./manage.py syncdb to create database structure. Now you should be able to
create translation projects using admin interface. You probably also want to
run ./manage.py setuplang to get default list of languages.

As setup of translation project includes fetching Git repositories, you might
want to preseed these, repos are stored in path defined by GIT_ROOT in
settings.py in <project>/<subproject> directories.

Management commands
-------------------

The ./manage.py is extended with following commands:

loadpo
    Reloads translations from disk (eg. in case you did some updates in Git
    repository).
setuplang
    Setups list of languages (it has own list and all defined in
    translate-toolkit).
updategit
    Fetches remote Git repositories and updates internal cache.

Project name
------------

The project is named as mixture of words web and translate.

Authors
-------

This tool was written by Michal Čihař <michal@cihar.com>.

License
-------

Copyright (C) 2012 Michal Čihař <michal@cihar.com>

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU General Public License as published by the Free Software
Foundation, either version 3 of the License, or (at your option) any later
version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
this program. If not, see <http://www.gnu.org/licenses/>.
