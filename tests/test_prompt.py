# tests/test_prompt.py
from generation.generators.api.prompt import (
    build_negative_prompt,
    build_prompt,
)
from generation.params.model import BuildingParams


def _params(**overrides):
    base = dict(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    base.update(overrides)
    return BuildingParams(**base)


def test_build_prompt_facade_contains_style_and_material():
    p = build_prompt(_params(style="modern", materials=["glass"]), "facade")
    assert "modern" in p.lower() or "contemporary" in p.lower()
    assert "glass" in p.lower()


def test_build_prompt_floorplan_mentions_floorplan():
    p = build_prompt(_params(), "floorplan")
    assert "floor plan" in p.lower() or "floorplan" in p.lower()


def test_build_prompt_different_params_differ():
    p1 = build_prompt(_params(style="modern"), "facade")
    p2 = build_prompt(_params(style="neoclassic"), "facade")
    assert p1 != p2


def test_build_prompt_kind_differs():
    facade = build_prompt(_params(), "facade")
    floorplan = build_prompt(_params(), "floorplan")
    assert facade != floorplan


def test_build_prompt_en_output_even_for_zh():
    p = build_prompt(_params(), "facade", lang="zh")
    # SDXL prompt 固定英文
    assert p.isascii()


def test_build_negative_prompt_nonempty():
    assert build_negative_prompt().strip()
