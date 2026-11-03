"""The registry has one shape, and the adapters read it.

Every adapter pulls a tool's arguments from `t["parameters"]` and falls back
to an empty object:

    "input_schema": t.get("parameters", {"type": "object", "properties": {}})

Four tools declared `input_schema` instead, so they reached every provider
described as taking NO arguments at all. `find_on_board` — the tool whose own
description says to use it whenever the user names something — was sent
without its `query`. `log_past_focus` was sent without `minutes` or `when`,
and `execute_tool` reads `args["minutes"]` directly.

A missing key is invisible: nothing raises, the tool simply arrives useless.
Hence an invariant rather than a one-off fix.
"""

import pytest

from services import alfred_tools


def test_every_tool_declares_its_arguments_under_parameters():
    wrong = sorted(t["name"] for t in alfred_tools.ALL_TOOLS if "parameters" not in t)
    assert wrong == [], (
        "these reach the model with an empty schema: " + ", ".join(wrong))


def test_no_tool_uses_the_anthropic_spelling_in_the_registry():
    """`input_schema` is the Anthropic wire format; the adapter builds it."""
    wrong = sorted(t["name"] for t in alfred_tools.ALL_TOOLS if "input_schema" in t)
    assert wrong == []


def test_every_schema_is_an_object_with_properties():
    for t in alfred_tools.ALL_TOOLS:
        schema = t["parameters"]
        assert schema.get("type") == "object", t["name"]
        assert isinstance(schema.get("properties"), dict), t["name"]


def test_required_arguments_actually_exist_in_the_schema():
    """A `required` naming a property that is not there is unsatisfiable."""
    for t in alfred_tools.ALL_TOOLS:
        schema = t["parameters"]
        props = set(schema.get("properties", {}))
        missing = [r for r in schema.get("required", []) if r not in props]
        assert not missing, f"{t['name']} requires undeclared {missing}"


def test_the_tools_that_take_arguments_still_have_them():
    """Spot-check the two that were actually broken."""
    by_name = {t["name"]: t for t in alfred_tools.ALL_TOOLS}
    assert "query" in by_name["find_on_board"]["parameters"]["properties"]
    assert "minutes" in by_name["log_past_focus"]["parameters"]["properties"]
    assert "when" in by_name["log_past_focus"]["parameters"]["properties"]


def test_what_the_anthropic_adapter_would_send_is_not_empty():
    """The exact expression the adapter uses, for a tool that takes arguments."""
    by_name = {t["name"]: t for t in alfred_tools.ALL_TOOLS}
    sent = by_name["find_on_board"].get("parameters", {"type": "object", "properties": {}})
    assert sent["properties"], "find_on_board would be described as taking nothing"
