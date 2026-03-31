r"""MkDocs hook: convert \url URL LaTeX relics to HTML hyperlinks.

When mkdocs-bibtex formats bibliography entries via pybtex, the \url{...}
command inside howpublished fields is rendered as the literal text
  \url https://example.com
in the Markdown footnote definitions.  MkDocs passes that through to HTML
unchanged, so the URL appears as plain text instead of a clickable link.

This hook runs after Markdown is rendered to HTML and replaces every
occurrence of \url URL with a proper <a href> element.
"""
import re

# Matches \url followed by whitespace and a URL.
# The URL terminates at:
#   - whitespace (space, tab, newline in HTML)
#   - HTML tag delimiters < >
#   - , or ; that typically follow URLs in bibliography text ("URL, year.")
#   - " which would break an HTML attribute value
_URL_CMD_RE = re.compile(r'\\url\s+(https?://[^\s<>"&,;]+)')


def on_page_content(html, **kwargs):
    """Replace \\url URL with <a href="URL">URL</a> in rendered HTML."""
    return _URL_CMD_RE.sub(lambda m: f'<a href="{m.group(1)}">{m.group(1)}</a>', html)
