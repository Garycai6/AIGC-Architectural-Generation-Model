import pathlib
import uuid

from fastapi import APIRouter, Request

from backend.app.core.config import Settings
from backend.app.schemas.generate import GenerateRequest, GenerationResponse
from generation.generators import SimulatorGenerator
from generation.llm.deepseek_client import DeepSeekClient

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: GenerateRequest, request: Request) -> GenerationResponse:
    """生成:校验参数 + 本地模拟器出图(效果图 + 平面图)。"""
    settings: Settings = request.app.state.settings  # 从 app.state 读取(支持测试注入)
    scheme_id = str(uuid.uuid4())
    if not settings.deepseek_api_key:
        description = (
            "测试占位文案:建筑设计描述" if req.lang == "zh" else "Placeholder scheme description"
        )
    else:
        client = DeepSeekClient(settings.deepseek_api_key, settings.deepseek_base_url)
        description = await client.describe_scheme(req.params, req.lang)

    out_dir = pathlib.Path(settings.cache_dir) / scheme_id
    out_dir.mkdir(parents=True, exist_ok=True)
    generator = SimulatorGenerator()
    artifact = await generator.generate(req.params, scheme_id, out_dir, req.lang)
    return GenerationResponse(
        scheme_id=scheme_id,
        description=description,
        images=[img.url for img in artifact.images],
    )
