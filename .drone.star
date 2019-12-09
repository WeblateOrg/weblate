# Starklark script to define Drone CI pipelines

# Default test environment
default_env = {
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "DJANGO_SETTINGS_MODULE": "weblate.settings_test",
    "CI_DATABASE": "postgresql",
    "CI_DB_HOST": "database",
}

# Basic set of installation files, usually used to update base docker image
basic_install = []
# PostgreSQL library installation
cmd_pip_postgresql = "pip install -r requirements-postgresql.txt"
# Some tests need older binary for Django copatibility
cmd_pip_postgresql_old = "pip install psycopg2-binary==2.7.7"
# PIP requirements installation
cmd_pip_deps = "pip install -r requirements-optional.txt -r requirements-test.txt -r docs/requirements.txt"
cmd_pip_deps_min = [
    "pip install requirements-builder",
    "requirements-builder --req requirements.txt --req requirements-optional.txt --level min > requirements-min.txt",
    "pip install -r requirements-min.txt",
]


def secret(name):
    return {"from_secret": name}


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
        "host": secret("SMTP_HOST"),
        "username": secret("SMTP_USER"),
        "password": secret("SMTP_PASS"),
        "from": "noreply+ci@weblate.org",
    },
    "when": {"status": ["changed", "failure"]},
}
codecov_step = {
    "name": "codecov",
    "image": "weblate/cidocker:3.7",
    "environment": {"CODECOV_TOKEN": secret("CODECOV_TOKEN"), "CI": "drone"},
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
    "commands": basic_install
    + [cmd_pip_deps, "make -C docs html SPHINXOPTS='-n -W -a'"],
}

test_step = {
    "name": "test",
    "image": "weblate/cidocker:3.8",
    "environment": get_test_env(),
    "commands": basic_install + [cmd_pip_postgresql, cmd_pip_deps, "./ci/run-test"],
}
test_step_minversion = dict(test_step)
test_step_minversion["image"] = "weblate/cidocker:3.7"
test_step_minversion["environment"] = get_test_env({"WITH_CYTHON": "true"})
test_step_minversion["commands"] = (
    basic_install + [cmd_pip_postgresql] + cmd_pip_deps_min + ["./ci/run-test"]
)
test_step_37 = dict(test_step)
test_step_37["image"] = "weblate/cidocker:3.7"
test_step_27 = dict(test_step)
test_step_27["image"] = "weblate/cidocker:2.7"
test_step_27["commands"] = basic_install + [
    cmd_pip_postgresql_old,
    cmd_pip_deps,
    "./ci/run-test",
]

migrations_step = {
    "name": "test",
    "image": "weblate/cidocker:3.7",
    # Need C locale for tesserocr compatibility
    "environment": get_test_env({"LANG": "C", "LC_ALL": "C"}),
    "commands": basic_install
    + [cmd_pip_postgresql_old, cmd_pip_deps, "./ci/run-migrate"],
}

# Services
database_service = {
    "name": "database",
    "image": "postgres:11-alpine",
    "ports": [5432],
    "environment": {"POSTGRES_USER": "postgres", "POSTGRES_DB": "weblate"},
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
        pipeline("tests:python-2.7", [test_step_27, codecov_step], [database_service]),
        pipeline("tests:python-3.7", [test_step_37, codecov_step], [database_service]),
        pipeline("tests:python-3.8", [test_step, codecov_step], [database_service]),
        pipeline(
            "tests:python-minversion",
            [test_step_minversion, codecov_step],
            [database_service],
        ),
        pipeline(
            "tests:migrations", [migrations_step, codecov_step], [database_service]
        ),
    ]
