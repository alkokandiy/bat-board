"""Unit tests for Markdown -> Telegram formatting and the HTML/send fallback."""

import re

from services import telegram_service
from services.telegram_format import strip_markdown, to_telegram_html


def _assert_balanced(text: str) -> None:
    assert len(re.findall(r"<b>", text)) == len(re.findall(r"</b>", text))
    assert len(re.findall(r"<i>", text)) == len(re.findall(r"</i>", text))
    assert len(re.findall(r"<code>", text)) == len(re.findall(r"</code>", text))
    assert len(re.findall(r"<pre>", text)) == len(re.findall(r"</pre>", text))


def test_none_and_empty():
    for fn in (to_telegram_html, strip_markdown):
        assert fn(None) == ""
        assert fn("") == ""


def test_bold_double_asterisk():
    assert to_telegram_html("a **bold** b") == "a <b>bold</b> b"


def test_bold_double_underscore():
    assert to_telegram_html("a __bold__ b") == "a <b>bold</b> b"


def test_bullet_lines():
    assert to_telegram_html("* one") == "• one"
    assert to_telegram_html("- two") == "• two"
    assert to_telegram_html("+ three") == "• three"


def test_nested_indented_bullets():
    src = "* top\n  * child\n    * grandchild"
    assert to_telegram_html(src) == "• top\n  • child\n    • grandchild"


def test_inline_code():
    assert to_telegram_html("run `x = 1` now") == "run <code>x = 1</code> now"


def test_inline_code_content_not_reprocessed():
    # An asterisk inside code must not become emphasis.
    assert to_telegram_html("`a*b*c`") == "<code>a*b*c</code>"


def test_fenced_code_block():
    assert to_telegram_html("```\nx = a & b\n```") == "<pre>x = a &amp; b</pre>"


def test_fenced_code_before_inline():
    src = "```\n`not inline`\n```"
    assert to_telegram_html(src) == "<pre>`not inline`</pre>"


def test_link_http():
    assert (
        to_telegram_html("see [Docs](http://example.com/a)")
        == 'see <a href="http://example.com/a">Docs</a>'
    )


def test_link_https_only_leaves_other_schemes_alone():
    assert to_telegram_html("[x](ftp://example.com)") == "[x](ftp://example.com)"
    assert to_telegram_html("[x](javascript:alert(1))") == "[x](javascript:alert(1))"


def test_headings():
    assert to_telegram_html("# Title") == "<b>Title</b>"
    assert to_telegram_html("## Sub") == "<b>Sub</b>"
    assert to_telegram_html("### Deep") == "<b>Deep</b>"


def test_script_is_escaped():
    assert to_telegram_html("<script>alert('x')</script>") == (
        "&lt;script&gt;alert('x')&lt;/script&gt;"
    )


def test_ampersand_escaped_and_not_double():
    assert to_telegram_html("Tom & Jerry") == "Tom &amp; Jerry"
    assert to_telegram_html("a &lt; b") == "a &amp;lt; b"


def test_italic_single_asterisk():
    assert to_telegram_html("this is *emph* here") == "this is <i>emph</i> here"


def test_italic_does_not_cross_newlines():
    assert to_telegram_html("*a\nb*") == "*a\nb*"


def test_italic_does_not_touch_bullet_marker():
    assert to_telegram_html("* item") == "• item"


def test_stray_asterisk_left_alone():
    assert to_telegram_html("2 * 3 = 6") == "2 * 3 = 6"
    assert to_telegram_html("lone * stays") == "lone * stays"


def test_asterisk_inside_word_left_alone():
    assert to_telegram_html("a*b*c") == "a*b*c"


def test_lone_underscore_left_alone():
    assert to_telegram_html("snake_case stays") == "snake_case stays"


def test_never_unmatched_tags_round_trip():
    samples = [
        "**bold** and *ital* and `code` and [link](http://x.io)",
        "*a\nb*",
        "# Head\n* bullet\n- bullet2",
        "```\n<b>raw</b>\n```",
        "weird **unclosed and *open and __under",
        "<script> & <b>",
    ]
    for s in samples:
        out = to_telegram_html(s)
        _assert_balanced(out)


def test_strip_markdown_plain_text():
    assert strip_markdown("**bold**") == "bold"
    assert strip_markdown("__bold__") == "bold"
    assert strip_markdown("*emph*") == "emph"
    assert strip_markdown("# Head") == "Head"
    assert strip_markdown("`code`") == "code"
    assert strip_markdown("* item") == "• item"


def test_strip_markdown_link_and_no_escape():
    assert strip_markdown("[Docs](https://ex.com)") == "Docs (https://ex.com)"
    # Plain-text path must NOT html-escape.
    assert strip_markdown("a < b & c") == "a < b & c"


def test_strip_markdown_fenced_keeps_content():
    assert strip_markdown("```\nkeep me\n```") == "keep me"


def test_send_one_falls_back_to_plain_on_400(monkeypatch):
    calls = []

    class _Resp:
        def __init__(self, status_code):
            self.status_code = status_code

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        # First (HTML) attempt fails, fallback succeeds.
        return _Resp(400 if len(calls) == 1 else 200)

    monkeypatch.setattr(telegram_service.httpx, "post", fake_post)

    ok = telegram_service._send_one("tok", "chat", "**hi**", 5.0, None)

    assert ok is True
    assert len(calls) == 2
    assert calls[0]["parse_mode"] == "HTML"
    assert calls[0]["text"] == "<b>hi</b>"
    assert "parse_mode" not in calls[1]
    assert calls[1]["text"] == "hi"


def test_send_one_returns_false_when_both_fail(monkeypatch):
    calls = []

    class _Resp:
        status_code = 400

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        return _Resp()

    monkeypatch.setattr(telegram_service.httpx, "post", fake_post)

    assert telegram_service._send_one("tok", "chat", "**hi**", 5.0, None) is False
    assert len(calls) == 2
    assert "parse_mode" not in calls[1]


def test_split_uses_raw_text_and_converts_per_chunk(monkeypatch):
    posted = []

    class _Resp:
        status_code = 200

    def fake_post(url, json=None, timeout=None):
        posted.append(json["text"])
        return _Resp()

    monkeypatch.setattr(telegram_service.httpx, "post", fake_post)

    text = "x" * (telegram_service.TELEGRAM_SPLIT_CHARS + 10)
    telegram_service.send_telegram_message("tok", "chat", text)

    assert len(posted) == 2
    assert all(len(p) <= telegram_service.TELEGRAM_MAX_MESSAGE_CHARS for p in posted)
