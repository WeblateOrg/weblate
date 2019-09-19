# Starklark script to define Drone CI pipelines

# Default test environment
default_env = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "DJANGO_SETTINGS_MODULE": "weblate.settings_test",
    "CI_DATABASE": "postgresql",
    "CI_DB_HOST": "database",
}


def get_test_env(base=None):
    if not base:
        base = {}
    for key, value in default_env.items():
        if key not in base:
            base[key] = value
    return base


# Build steps
notify_step = {
    "name": "notify",
    "image": "drillster/drone-email",
    "settings": {
        "host": {"from_secret": "SMTP_HOST"},
        "username": {"from_secret": "SMTP_USER"},
        "password": {"from_secret": "SMTP_PASS"},
        "from": "noreply+ci@weblate.org",
    },
    "when": {"status": ["changed", "failure"]},
}
codecov_step = {
    "name": "codecov",
    "image": "weblate/cidocker:3.7",
    "environment": {"CODECOV_TOKEN": {"from_secret": "CODECOV_TOKEN"}, "CI": "drone"},
    "commands": ["export CI=drone", "codecov"],
}
flake_step = {
    "name": "flake8",
    "image": "weblate/cidocker:3.7",
    "commands": ["pip install -r requirements-lint.txt", "flake8"],
}
sdist_step = {
    "name": "sdist",
    "image": "weblate/cidocker:3.7",
    "commands": [
        "pip install -r requirements-lint.txt",
        "./setup.py sdist",
        "twine check dist/*",
    ],
}
sphinx_step = {
    "name": "sphinx",
    "image": "weblate/cidocker:3.7",
    "commands": [
        "pip install -r docs/requirements.txt",
        "make -C docs html SPHINXOPTS='-n -W -a'",
    ],
}
selenium_step = {
    "name": "test",
    "image": "weblate/cidocker:3.7",
    "ports": [9090],
    "environment": get_test_env(
        {
            "SAUCE_USERNAME": {"from_secret": "SAUCE_USERNAME"},
            "SAUCE_ACCESS_KEY": {"from_secret": "SAUCE_ACCESS_KEY"},
        }
    ),
    "commands": [
        "pip install -r requirements-postgresql.txt",
        "pip install -r requirements-optional.txt -r requirements-test.txt -r docs/requirements.txt",
        "./ci/run-selenium",
    ],
}
test_step = {
    "name": "test",
    "image": "weblate/cidocker:3.7",
    "environment": get_test_env(),
    "commands": [
        "pip install -r requirements-postgresql.txt",
        "pip install -r requirements-optional.txt -r requirements-test.txt -r docs/requirements.txt",
        "./ci/run-test",
    ],
}
test_step_27 = {
    "name": "test",
    "image": "weblate/cidocker:2.7",
    "environment": get_test_env(),
    "commands": [
        "pip install  psycopg2-binary==2.7.7",
        "pip install -r requirements-optional.txt -r requirements-test.txt -r docs/requirements.txt",
        "./ci/run-test",
    ],
}
migrations_step = {
    "name": "test",
    "image": "weblate/cidocker:3.7",
    # Need C locale for tesserocr compatibility
    "environment": get_test_env({"LANG": "C", "LC_ALL": "C"}),
    "commands": [
        # Need older binary for Django copatibility
        "pip install  psycopg2-binary==2.7.7",
        "pip install -r requirements-optional.txt -r requirements-test.txt -r docs/requirements.txt",
        "./ci/run-migrate",
    ],
}

# Services
database_service = {
    "name": "database",
    "image": "postgres:11-alpine",
    "ports": [5432],
    "environment": {"POSTGRES_USER": "postgres", "POSTGRES_DB": "weblate"},
}
sauce_service = {
    "name": "sauce",
    "image": "nijel/sauce-connect:latest",
    "environment": {
        "SAUCE_USERNAME": {"from_secret": "SAUCE_USERNAME"},
        "SAUCE_ACCESS_KEY": {"from_secret": "SAUCE_ACCESS_KEY"},
    },
}

# Pipeline template
pipeline_template = {
    "kind": "pipeline",
    "clone": {"depth": 100},
    "steps": [notify_step],
}


def pipeline(name, steps, services=None):
    result = {"name": name}
    result.update(pipeline_template)
    result["steps"] = steps + result["steps"]
    if services:
        result["services"] = services
    return result


def main(ctx):
    return [
        pipeline("lint", [flake_step, sdist_step]),
        pipeline("docs", [sphinx_step]),
        pipeline(
            "tests:selenium",
            [selenium_step, codecov_step],
            [database_service, sauce_service],
        ),
        pipeline("tests:python-2.7", [test_step_27, codecov_step], [database_service]),
        pipeline("tests:python-3.7", [test_step, codecov_step], [database_service]),
        pipeline(
            "tests:migrations", [migrations_step, codecov_step], [database_service]
        ),
    ]
