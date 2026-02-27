"""Test template rendering logic."""

import pytest

from app.api.templates import render_template_string


def test_render_simple():
    result = render_template_string("Hello {{ name }}!", {"name": "World"})
    assert result == "Hello World!"


def test_render_html_escaped():
    result = render_template_string("{{ content }}", {"content": "<script>alert(1)</script>"})
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_render_missing_variable():
    result = render_template_string("Hello {{ name }}!", {})
    assert result == "Hello !"


def test_render_complex_template():
    tpl = """
    <h1>{{ title }}</h1>
    <p>Dear {{ first_name }},</p>
    {% if discount %}
    <p>Your discount: {{ discount }}%</p>
    {% endif %}
    """
    result = render_template_string(tpl, {
        "title": "Special Offer",
        "first_name": "John",
        "discount": 20,
    })
    assert "Special Offer" in result
    assert "John" in result
    assert "20%" in result


def test_render_no_variables():
    result = render_template_string("Static content", {})
    assert result == "Static content"


def test_render_invalid_syntax():
    with pytest.raises(ValueError, match="Template syntax error"):
        render_template_string("{% invalid %}", {})
