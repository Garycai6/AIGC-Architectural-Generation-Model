import pytest
from pydantic import ValidationError

from generation.params.model import STYLE_NAMES, BuildingParams


def test_valid_params():
    p = BuildingParams(
        style="modern", floors=3, width_m=10.0, depth_m=8.0,
        materials=["glass", "stone"], roof="flat", environment="suburb",
    )
    assert p.floors == 3
    assert p.height_m == pytest.approx(9.6)  # 默认 floors × 3.2


def test_height_override():
    p = BuildingParams(style="modern", floors=3, width_m=10.0, depth_m=8.0,
                       materials=["glass"], roof="flat", environment="suburb",
                       height_m=12.0)
    assert p.height_m == 12.0


def test_style_enum():
    assert STYLE_NAMES == ["modern", "neoclassic", "european", "nordic"]
    with pytest.raises(ValidationError):
        BuildingParams(style="baroque", floors=3, width_m=10.0, depth_m=8.0,
                       materials=["glass"], roof="flat", environment="suburb")


def test_bounds():
    with pytest.raises(ValidationError):
        BuildingParams(style="modern", floors=0, width_m=10.0, depth_m=8.0,
                       materials=["glass"], roof="flat", environment="suburb")
    with pytest.raises(ValidationError):
        BuildingParams(style="modern", floors=3, width_m=25.0, depth_m=8.0,
                       materials=["glass"], roof="flat", environment="suburb")


def test_materials_enum():
    with pytest.raises(ValidationError):
        BuildingParams(style="modern", floors=3, width_m=10.0, depth_m=8.0,
                       materials=["titanium"], roof="flat", environment="suburb")


def test_required_fields():
    with pytest.raises(ValidationError):
        BuildingParams(style="modern", floors=3)
