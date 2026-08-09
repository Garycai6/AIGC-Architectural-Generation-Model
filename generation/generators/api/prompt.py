# generation/generators/api/prompt.py
from typing import Literal

from generation.params.model import BuildingParams

# 英文建筑风格描述(SDXL prompt 用英文)
STYLE_LABELS: dict[str, str] = {
    "modern": "modern minimalist architecture with clean lines",
    "neoclassic": "neoclassical architecture with symmetrical facade and columns",
    "european": "European classic architecture with arched windows and pediment",
    "nordic": "Nordic Scandinavian architecture with wood and minimalist details",
}

MATERIAL_LABELS: dict[str, str] = {
    "glass": "glass curtain wall",
    "stone": "natural stone cladding",
    "brick": "brick facade",
    "wood": "wood cladding",
}

ENVIRONMENT_LABELS: dict[str, str] = {
    "urban": "urban setting, city street",
    "suburb": "suburban neighborhood",
    "rural": "rural countryside, open field",
    "seaside": "seaside, coastal view",
}

ROOF_LABELS: dict[str, str] = {
    "flat": "flat roof",
    "pitched": "pitched gable roof",
    "hipped": "hipped roof",
}

FACADE_PREFIX = "architectural rendering of a residential building"
FLOORPLAN_PREFIX = "architectural floor plan drawing, top view layout"

NEGATIVE_PROMPT = (
    "low quality, blurry, distorted, deformed, watermark, text, "
    "signature, extra buildings, perspective error"
)


def build_prompt(
    params: BuildingParams,
    kind: Literal["facade", "floorplan"],
    lang: str = "en",
) -> str:
    """构造 SDXL prompt(固定英文,即使 lang=zh)。确定性、纯代码。"""
    style = STYLE_LABELS[params.style]
    material = MATERIAL_LABELS[params.materials[0]]
    env = ENVIRONMENT_LABELS[params.environment]
    roof = ROOF_LABELS[params.roof]
    if kind == "facade":
        return (
            f"{FACADE_PREFIX}, {style}, {material}, {roof}, "
            f"{params.floors}-story, {env}, photorealistic, high detail"
        )
    return (
        f"{FLOORPLAN_PREFIX}, {style}, {material}, "
        f"{params.floors} floors, {params.width_m}x{params.depth_m} meters, "
        f"architectural blueprint style, clean layout"
    )


def build_negative_prompt() -> str:
    return NEGATIVE_PROMPT
