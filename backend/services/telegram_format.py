"""Markdown -> Telegram formatting for outbound messages.

Alfred (the LLM) emits Markdown, but we send Telegram messages with no
parse_mode, so users saw literal ``**`` and ``*`` markers. This module
converts a small, safe subset of Markdown into the HTML subset Telegram
accepts (https://core.telegram.org/bots/api#html-style), or strips it for
plain-text fallback.

Pure functions only: no I/O, no DB, no imports from other services.
"""

import re

_FENCE_RE = re.compile(r"```(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_BOLD_UNDERSCORE_RE = re.compile(r"__(.+?)__")
# http/https only: any other scheme is left untouched rather than linked.
_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_HEADING_RE = re.compile(r"^#{1,3}[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_BULLET_RE = re.compile(r"^([ \t]*)[*+\-][ \t]+", re.MULTILINE)
# Single-asterisk emphasis: space may not touch either marker, and the
# asterisk may not sit inside a word (so a stray "2 * 3" stays literal).
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])")

_PLACEHOLDER_RE = re.compile(r"\x00(\d+)\x00")


def _protect(pattern: re.Pattern, text: str, store: list, render) -> str:
    """Replace matches with opaque tokens so later rules can't rewrite the
    HTML we just generated (e.g. an asterisk inside ``<code>``)."""
    def _sub(match):
        store.append(render(match))
        return f"\x00{len(store) - 1}\x00"

    return pattern.sub(_sub, text)


def _restore(text: str, store: list) -> str:
    return _PLACEHOLDER_RE.sub(lambda m: store[int(m.group(1))], text)


def to_telegram_html(text: str) -> str:
    """Convert a safe Markdown subset to Telegram's HTML dialect.

    ``None`` or "" returns "". Never raises.
    """
    if not text:
        return ""

    # Escape FIRST: everything below inserts tags, so escaping afterwards would
    # shred our own markup. It also stops user/LLM ``<script>`` from becoming
    # a live tag in the rendered message.
    out = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    store: list = []
    # Fenced blocks before inline code, so the fence's backticks aren't eaten.
    out = _protect(_FENCE_RE, out, store, lambda m: f"<pre>{m.group(1).strip(chr(10))}</pre>")
    out = _protect(_INLINE_CODE_RE, out, store, lambda m: f"<code>{m.group(1)}</code>")

    out = _BOLD_RE.sub(r"<b>\1</b>", out)
    out = _BOLD_UNDERSCORE_RE.sub(r"<b>\1</b>", out)
    out = _LINK_RE.sub(r'<a href="\2">\1</a>', out)
    out = _HEADING_RE.sub(r"<b>\1</b>", out)
    out = _BULLET_RE.sub(r"\1• ", out)
    out = _ITALIC_RE.sub(r"<i>\1</i>", out)

    return _restore(out, store)


def strip_markdown(text: str) -> str:
    """Return readable plain text: markers removed, bullets normalised,
    links rendered as ``label (url)``. Deliberately does NOT html-escape,
    because it feeds Telegram with no parse_mode. Never raises."""
    if not text:
        return ""

    out = _FENCE_RE.sub(lambda m: m.group(1).strip("\n"), text)
    out = _INLINE_CODE_RE.sub(r"\1", out)
    out = _BOLD_RE.sub(r"\1", out)
    out = _BOLD_UNDERSCORE_RE.sub(r"\1", out)
    out = _LINK_RE.sub(r"\1 (\2)", out)
    out = _HEADING_RE.sub(r"\1", out)
    out = _BULLET_RE.sub(r"\1• ", out)
    out = _ITALIC_RE.sub(r"\1", out)
    return out
