# Makefile for Sphinx documentation
#

# You can set these variables from the command line.
SPHINXOPTS    =
SPHINXBUILD   = sphinx-build
PAPER         =
BUILDDIR      = build

# User-friendly check for sphinx-build
ifeq ($(shell which $(SPHINXBUILD) >/dev/null 2>&1; echo $$?), 1)
$(error The '$(SPHINXBUILD)' command was not found. Make sure you have Sphinx installed, then set the SPHINXBUILD environment variable to point to the full path of the '$(SPHINXBUILD)' executable. Alternatively you can add the directory with the executable to your PATH. If you don't have Sphinx installed, grab it from http://sphinx-doc.org/)
endif

# Internal variables.
PAPEROPT_a4     = -D latex_paper_size=a4
PAPEROPT_letter = -D latex_paper_size=letter
ALLSPHINXOPTS   = -n -d $(BUILDDIR)/doctrees $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source
# the i18n builder cannot share the environment and doctrees with the others
I18NSPHINXOPTS  = $(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source

.PHONY: all help clean html html-all gettext-update dirhtml singlehtml pickle json htmlhelp qthelp devhelp epub latex latexpdf text man changes linkcheck doctest coverage gettext customdefault

customdefault:
	$(SPHINXBUILD) -b html -nW --keep-going $(ALLSPHINXOPTS) $(BUILDDIR)/html

all: html

clean:
	rm -rf $(BUILDDIR)

html:
	$(SPHINXBUILD) -b html $(ALLSPHINXOPTS) $(BUILDDIR)/html
	@echo
	@echo "Build finished. The HTML pages are in $(BUILDDIR)/html."

# Every language with a catalogue under source/locale/. English is the source
# text, so it has no catalogue and is the plain html target above.
LANGUAGES = $(patsubst source/locale/%/,%,$(wildcard source/locale/*/))

# One translated site, e.g. `make html-fur`. Its own doctree cache, because the
# catalogue is baked into it and would otherwise leak between languages.
html-%:
	$(SPHINXBUILD) -b html -D language=$* -n -d $(BUILDDIR)/doctrees-$* \
		$(PAPEROPT_$(PAPER)) $(SPHINXOPTS) source $(BUILDDIR)/html/$*
	@echo
	@echo "Build finished. The $* pages are in $(BUILDDIR)/html/$*."

# English plus every translation, each under its own subdirectory.
html-all: html $(addprefix html-,$(LANGUAGES))
	@echo
	@echo "Languages built: en $(LANGUAGES)"

# Refresh the .pot templates after the English text changes.
gettext-update:
	$(SPHINXBUILD) -b gettext $(I18NSPHINXOPTS) $(BUILDDIR)/gettext
	@echo
	@echo "Templates are in $(BUILDDIR)/gettext. Copy new msgid blocks into"
	@echo "source/locale/<lang>/LC_MESSAGES/ and translate them."

view:
	xdg-open $(BUILDDIR)/html/index.html
