"""Markdown → the small HTML subset Telegram accepts.

The assistant writes markdown (``**qalin**``, ``- ro'yxat``, ``[nom](havola)``),
while the dispatcher sends every message as HTML (``ParseMode.HTML``). Sending
that text as-is shows the raw markers to the user, and passing it through as
HTML would let a ``<`` or an ``&`` in the model's words break the whole message.
So the text is escaped first and only the tags Telegram documents are rebuilt:

    <b> <i> <u> <s> <code> <pre> <blockquote> <a href="...">

Everything else stays plain text — there is no way for model output to inject a
tag that was not produced here.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from .utils import escape_html

# Only these schemes ever become a link; anything else keeps its label and
# loses the anchor (``javascript:`` and friends must never reach the client).
SAFE_SCHEMES = frozenset({"http", "https", "tg"})
QUOTE_LINE = "▎ "
RULE_LINE = "──────────"

_FENCE = re.compile(r"^\s*```")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(?P<text>.+?)\s*#*\s*$")
_RULE = re.compile(r"^\s*(?:[-*_])(?:\s*[-*_]){2,}\s*$")
_QUOTE = re.compile(r"^\s*>\s?(?P<text>.*)$")
_BULLET = re.compile(r"^(?P<indent>\s*)[-*+•]\s+(?P<text>.*)$")

_INLINE = re.compile(
    r"(?P<code>`[^`\n]+?`)"
    r"|(?P<bold>\*\*[^\n]+?\*\*)"
    r"|(?P<bold_us>__[^\n]+?__)"
    r"|(?P<strike>~~[^\n]+?~~)"
    r"|(?P<link>\[[^\]\n]*\]\((?:[^()\n]|\([^()\n]*\))*\))"
    r"|(?P<italic>\*(?![\s*])[^\n*]+?(?<![\s*])\*)"
    r"|(?P<italic_us>(?<![\w_])_(?![\s_])[^\n_]+?(?<![\s_])_(?![\w]))"
)
_LINK = re.compile(
    r"^\[(?P<label>[^\]]*)\]\((?P<href>(?:[^()\n]|\([^()\n]*\))*)\)$"
)


def _safe_url(href: str) -> bool:
    """Whether a markdown link target may become an ``<a href>``."""
    try:
        parsed = urlparse(href.strip())
    except ValueError:
        return False
    scheme = parsed.scheme.lower()
    if scheme not in SAFE_SCHEMES:
        return False
    return bool(parsed.netloc) or href.strip().lower().startswith(f"{scheme}:")


def _inline(raw: str) -> str:
    """Format one run of inline markdown (the text is escaped here)."""
    text = escape_html(raw)

    def replace(match: re.Match) -> str:
        code = match.group("code")
        if code is not None:
            return f"<code>{code[1:-1]}</code>"
        bold = match.group("bold")
        if bold is not None:
            return f"<b>{_inline_untrusted(bold[2:-2])}</b>"
        bold_us = match.group("bold_us")
        if bold_us is not None:
            return f"<b>{_inline_untrusted(bold_us[2:-2])}</b>"
        strike = match.group("strike")
        if strike is not None:
            return f"<s>{_inline_untrusted(strike[2:-2])}</s>"
        link = match.group("link")
        if link is not None:
            parsed = _LINK.match(link)
            if parsed:
                label = _inline_untrusted(parsed.group("label"))
                href = parsed.group("href")
                if _safe_url(href):
                    # ``href`` is already escaped (quotes included): escaping it
                    # twice would turn ``&amp;`` into ``&amp;amp;``.
                    return f'<a href="{href}">{label or href}</a>'
                return label
            return link
        italic = match.group("italic")
        if italic is not None:
            return f"<i>{_inline_untrusted(italic[1:-1])}</i>"
        italic_us = match.group("italic_us")
        if italic_us is not None:
            return f"<i>{_inline_untrusted(italic_us[1:-1])}</i>"
        return match.group(0)

    return _INLINE.sub(replace, text)


def _inline_untrusted(raw: str) -> str:
    """Format the inside of an already escaped span.

    ``raw`` comes from the escaped text, so it must not be escaped again; the
    markers left inside (``**a *b* c**``) are the only thing formatted here.
    """
    def replace(match: re.Match) -> str:
        code = match.group("code")
        if code is not None:
            return f"<code>{code[1:-1]}</code>"
        bold = match.group("bold") or match.group("bold_us")
        if bold is not None:
            return f"<b>{_inline_untrusted(bold[2:-2])}</b>"
        strike = match.group("strike")
        if strike is not None:
            return f"<s>{_inline_untrusted(strike[2:-2])}</s>"
        link = match.group("link")
        if link is not None:
            parsed = _LINK.match(link)
            if parsed:
                label = _inline_untrusted(parsed.group("label"))
                href = parsed.group("href")
                if _safe_url(href):
                    return f'<a href="{href}">{label or href}</a>'
                return label
            return link
        italic = match.group("italic") or match.group("italic_us")
        if italic is not None:
            return f"<i>{_inline_untrusted(italic[1:-1])}</i>"
        return match.group(0)

    return _INLINE.sub(replace, raw)


def _format_line(line: str) -> str:
    stripped = line.strip()
    if not stripped:
        return ""
    heading = _HEADING.match(line)
    if heading:
        return f"<b>{_inline(heading.group('text'))}</b>"
    if _RULE.match(stripped):
        return RULE_LINE
    quote = _QUOTE.match(line)
    if quote:
        text = _inline(quote.group("text").strip())
        return f"<blockquote>{QUOTE_LINE}{text}</blockquote>" if text else ""
    bullet = _BULLET.match(line)
    if bullet:
        return f"{bullet.group('indent')}• {_inline(bullet.group('text'))}"
    return _inline(line)


def to_telegram_html(text: Any) -> str:
    """Convert model-written markdown into escaped, whitelisted Telegram HTML."""
    source = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not source.strip():
        return ""

    lines = []
    code_lines = []
    in_code = False
    for raw in source.split("\n"):
        line = raw.rstrip()
        if _FENCE.match(line):
            if in_code:
                lines.append(f"<pre>{escape_html(chr(10).join(code_lines))}</pre>")
                code_lines = []
            in_code = not in_code
            continue
        if in_code:
            code_lines.append(line)
            continue
        lines.append(_format_line(line))
    if in_code:
        # An unterminated fence is still code: show it, never swallow it.
        lines.append(f"<pre>{escape_html(chr(10).join(code_lines))}</pre>")

    # Collapse the runs of blank lines a markdown answer tends to leave behind.
    collapsed: list[str] = []
    for line in lines:
        if not line and (not collapsed or not collapsed[-1]):
            continue
        collapsed.append(line)
    return "\n".join(collapsed).strip()


__all__ = ["to_telegram_html", "SAFE_SCHEMES"]
