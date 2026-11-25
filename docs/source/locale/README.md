# Translations

Message catalogues for the documentation, one `.po` file per source page.
Translated so far: `index.rst`, the user guide (`user_guide/`, including
`get_started/`) and the title page of the API reference
(`module_guide/index.rst`); the API pages generated from docstrings stay in
English. `sphinx.po` translates the strings of the HTML templates.

Sphinx compiles the `.po` files to `.mo` itself, so no extra tool is needed to
build a translated site.

## Build locally

From `docs/`:

```
make html-all      # English, then every language with a catalogue here
make html          # English only
make html-fur      # one language only
```

English lands in `build/html/`, each translation in `build/html/<lang>/`, so a
single static server shows them all. Each language keeps its own doctree cache,
because the catalogue is baked into it.

## Refresh the catalogues after editing the English source

```
make gettext-update
```

That writes one `.pot` per page under `build/gettext/`. Copy the new or changed `msgid` blocks into
the matching `.po` under `locale/<lang>/LC_MESSAGES/` and translate them. An
empty `msgstr` falls back to English, so a partly translated page still builds.

## On Read the Docs

`conf.py` reads `READTHEDOCS_LANGUAGE`, so a translation project set to that
language builds itself with no extra configuration. Link it to the main project
under Admin, Translations, and the language appears in the flyout menu at the
bottom of every page.
