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

Authors
-------

This tool was written by Michal Čihař <michal@cihar.com>.
