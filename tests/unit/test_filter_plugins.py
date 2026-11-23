import importlib.util
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[2] / "ansible/filter_plugins"
COLORS = {"base00": "000000", "base0D": "0d0d0d"}


def load_filters(name):
    """The filters a plugin file gives Ansible, loaded the way Ansible loads it."""
    spec = importlib.util.spec_from_file_location(name, PLUGINS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module.FilterModule().filters()


@pytest.fixture
def block():
    return load_filters("waybar_colored_span")["waybar_colored_block"]


def test_dict_values_returns_the_values():
    dict_values = load_filters("dict_values")["dict_values"]

    assert list(dict_values({"a": 1, "b": 2})) == [1, 2]


def test_first_block_on_the_right_opens_with_a_separator_in_its_color(block):
    out = block(COLORS, "base00", "base0D", "text", first_block=True, position="right")

    assert out.startswith('<span size=\\"large\\" color=\\"#0d0d0d\\">')
    assert out.endswith('<span background=\\"#0d0d0d\\"> text</span>')
    assert "000000" not in out


def test_first_block_on_the_left_is_just_its_text(block):
    out = block(COLORS, "base00", "base0D", "text", first_block=True, position="left")

    assert out == '<span size=\\"large\\" background=\\"#0d0d0d\\"> text</span>'


def test_first_block_needs_a_position(block):
    with pytest.raises(ValueError, match="must be passed"):
        block(COLORS, "base00", "base0D", "text", first_block=True)


def test_last_block_on_the_left_closes_with_a_separator_in_its_color(block):
    out = block(COLORS, "base00", "base0D", "text", last_block=True, position="left")

    assert out.startswith(
        '<span size=\\"large\\" background=\\"#000000\\" color=\\"#000000\\">'
    )
    assert '<span background=\\"#0d0d0d\\"> text </span>' in out
    assert out.endswith('<span size=\\"large\\" color=\\"#0d0d0d\\">\ue0bc</span>')


def test_last_block_on_the_right_ends_with_its_text(block):
    out = block(COLORS, "base00", "base0D", "text", last_block=True, position="right")

    assert out.startswith(
        '<span size=\\"large\\" background=\\"#000000\\" color=\\"#000000\\">'
    )
    assert out.endswith('<span background=\\"#0d0d0d\\"> text </span>')


def test_last_block_needs_a_position(block):
    with pytest.raises(ValueError, match="must be passed"):
        block(COLORS, "base00", "base0D", "text", last_block=True)


def test_middle_block_joins_the_previous_color_to_its_own(block):
    out = block(COLORS, "base00", "base0D", "text")

    assert out.startswith(
        '<span size=\\"large\\" background=\\"#000000\\" color=\\"#000000\\">'
    )
    assert '<span size=\\"large\\" background=\\"#000000\\" color=\\"#0d0d0d\\">' in out
    assert out.endswith('<span background=\\"#0d0d0d\\"> text</span>')
