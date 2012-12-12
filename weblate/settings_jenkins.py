from settings_example import *

INSTALLED_APPS += ('django_jenkins', )

JENKINS_TASKS = (
    'django_jenkins.tasks.run_pylint',
    'django_jenkins.tasks.run_pyflakes',
    'django_jenkins.tasks.run_sloccount',
    'django_jenkins.tasks.with_coverage',
    'django_jenkins.tasks.run_pep8',
    'django_jenkins.tasks.django_tests',
)

PROJECT_APPS = (
    'weblate.trans',
    'weblate.lang',
    'weblate.accounts',
)
