# Copyright © Michal Čihař <michal@weblate.org>
#
# SPDX-License-Identifier: GPL-3.0-or-later

# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command-line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile update-po update-screenshots update-schemas update-openapi update-doc-snippets run-selenium

run-selenium:
	@rm -rf ../data-test ../test-images
	@cd .. && \
		. scripts/test-database.sh && \
		pytest -n 3 weblate/trans/tests/test_selenium.py

SCREENSHOTS = $(wildcard screenshots/*.webp)

../test-images/%.png: run-selenium
	@true

screenshots/%.webp: ../test-images/%.png run-selenium
	@echo "Processing $@"
	@convert $< $@

update-screenshots: $(SCREENSHOTS)
	@echo $(SCREENSHOTS)

update-schemas:
	@cp $$(uv run --no-sync ../scripts/get-schemas-dir.py)/schemas/* specs/schemas/

update-openapi:
	@WEBLATE_HIDE_VERSION=1 uv run --no-sync ../manage.py spectacular --skip-checks --fail-on-warn --validate > specs/openapi.yaml

update-doc-snippets:
	@uv run --no-sync ../manage.py list_change_events > docs/snippets/change-events.rst
	@uv run --no-sync ../manage.py list_file_format_params > docs/snippets/file-format-parameters.rst
	@uv run --no-sync ../manage.py list_permissions --sections perms > docs/snippets/permissions.rst
	@uv run --no-sync ../manage.py list_permissions --sections roles > docs/snippets/roles.rst

update-po: $(wildcard locales/*/LC_MESSAGES/docs.po)

locales/%/LC_MESSAGES/docs.po: locales/docs.pot
	@if ! test -h locales/$* ; then msgmerge -U $@ -C ../weblate/locale/$*/LC_MESSAGES/django.po --previous $< ; fi

locales/docs.pot: gettext
	@cp _build/gettext/docs.pot $@
	@../scripts/filter-docs-po.py $@


# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
