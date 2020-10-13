# Minimal makefile for Sphinx documentation
#

# You can set these variables from the command line, and also
# from the environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = .
BUILDDIR      = _build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile update-po

update-screenshots:
	@rm -rf ../data-test ../test-images
	@cd .. && \
		export DJANGO_SETTINGS_MODULE=weblate.settings_test && \
		./manage.py collectstatic --noinput && \
		./manage.py test weblate.trans.tests.test_selenium.SeleniumTests
	@set -e ;for file in ../test-images/*.png ; do \
		echo Processing `basename $$file` ; \
		cp $$file tmp.png ; \
		pngnq -s 1 -f -n 255 tmp.png ; \
		rm -f images/`basename $$file` ; \
		zopflipng -m tmp-nq8.png images/`basename $$file` ; \
	done
	@rm -f tmp.png tmp-nq8.png

update-schemas:
	@cp ../.venv/lib/python*/site-packages/weblate_schemas/schemas/* schemas/

update-po: $(wildcard locales/*/LC_MESSAGES/docs.po)

locales/%/LC_MESSAGES/docs.po: locales/docs.pot
	@if ! test -h locales/$* ; then msgmerge -U $@ -C ../weblate/locale/$*/LC_MESSAGES/django.po --previous $< ; fi

locales/docs.pot: gettext
	@cp _build/gettext/docs.pot $@

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
