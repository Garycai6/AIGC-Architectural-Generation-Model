import uuid

from fastapi import APIRouter, Request

from backend.app.core.config import Settings
from backend.app.schemas.generate import GenerateRequest, GenerationResponse
from generation.llm.deepseek_client import DeepSeekClient

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: GenerateRequest, request: Request) -> GenerationResponse:
    """生成骨架:校验参数 + 调用 DeepSeek 描述。图片生成在阶段 2 接入。"""
    settings: Settings = request.app.state.settings  # 从 app.state 读取(支持测试注入)
    if not settings.deepseek_api_key:
        description = (
            "测试占位文案:建筑设计描述" if req.lang == "zh" else "Placeholder scheme description"
        )
    else:
        client = DeepSeekClient(settings.deepseek_api_key, settings.deepseek_base_url)
        description = await client.describe_scheme(req.params, req.lang)
    return GenerationResponse(scheme_id=str(uuid.uuid4()), description=description, images=[])
