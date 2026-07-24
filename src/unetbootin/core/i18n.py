"""Lightweight translation layer for UNetbootin.

Loads the Qt-style ``.ts`` catalogs shipped in ``resources/translations/``
(``source`` -> ``translation`` pairs) and exposes a gettext-like ``_()``
lookup. Falls back to the source string when no translation is available.
No Qt dependency — the ``.ts`` XML is parsed directly.

Usage:
    from unetbootin.core.i18n import set_language, _
    set_language('de')           # once, at startup
    label = _("USB Drive")       # -> "USB-Laufwerk"
"""

import logging
import xml.etree.ElementTree as ET
from typing import Dict, Optional

from unetbootin.resources import translations_dir

logger = logging.getLogger(__name__)

# Languages that ship a translation catalog (English is the untranslated base).
SUPPORTED_LANGUAGES = ('de', 'es', 'fr', 'it', 'hu')

_catalog: Dict[str, str] = {}
_current_lang: str = 'en'


def _normalize(lang: Optional[str]) -> str:
    """Reduce a locale like ``de_DE.UTF-8`` to a short code like ``de``."""
    if not lang:
        return 'en'
    return lang.replace('-', '_').split('_')[0].split('.')[0].lower()


def _load_ts(path) -> Dict[str, str]:
    """Parse a Qt ``.ts`` file into a {source: translation} dict.

    Entries whose translation is missing, empty, or marked
    ``type="unfinished"`` are skipped so the source text is used instead.
    """
    catalog: Dict[str, str] = {}
    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as e:
        logger.warning(f"Could not load translation catalog {path}: {e}")
        return catalog

    for message in tree.iter('message'):
        source = message.findtext('source')
        node = message.find('translation')
        if source is None or node is None:
            continue
        if node.get('type') == 'unfinished':
            continue
        translation = (node.text or '').strip()
        if translation:
            catalog[source] = translation
    return catalog


def set_language(lang: Optional[str]) -> str:
    """Activate a language catalog and return the short code actually used.

    Unsupported/unknown codes fall back to English (empty catalog → source
    strings are returned verbatim).
    """
    global _catalog, _current_lang
    code = _normalize(lang)
    if code not in SUPPORTED_LANGUAGES:
        _catalog = {}
        _current_lang = 'en'
        return 'en'

    path = translations_dir() / f'unetbootin_{code}.ts'
    _catalog = _load_ts(path)
    _current_lang = code
    logger.info(f"Loaded {len(_catalog)} translations for '{code}'")
    return code


def translate(text: str) -> str:
    """Return the translation of `text` for the active language (or `text`)."""
    return _catalog.get(text, text)


# gettext-style alias
_ = translate


def get_language() -> str:
    """Return the active short language code."""
    return _current_lang


def available_languages() -> tuple:
    """Return the language codes that ship a catalog (plus 'en')."""
    return ('en',) + SUPPORTED_LANGUAGES
