"""本地模拟器生成器——护城河:参数 → 程序化线稿。"""

from generation.generators.base import GenerationArtifact
from generation.generators.simulator.renderer import render_scheme
from generation.params.model import BuildingParams


class SimulatorGenerator:
    """本地模拟器:参数 → 透视立面 + 平面示意 PNG。"""

    async def generate(
        self,
        params: BuildingParams,
        scheme_id: str,
        out_dir: object,
        lang: str = "zh",
    ) -> GenerationArtifact:
        return await render_scheme(params, scheme_id, out_dir, lang)


__all__ = ["SimulatorGenerator"]
