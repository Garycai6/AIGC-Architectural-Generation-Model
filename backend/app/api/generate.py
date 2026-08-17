import pathlib
import uuid
from datetime import date

from fastapi import APIRouter, HTTPException, Request

from backend.app.core.config import Settings
from backend.app.core.quota import QuotaService
from backend.app.schemas.generate import GenerateRequest, GenerationResponse
from generation.generators import SimulatorGenerator
from generation.generators.api import ApiGenerator
from generation.generators.api.fal_gen import FAL_MODEL, FalGenerator
from generation.generators.api.replicate_gen import SDXL_MODEL
from generation.llm.deepseek_client import DeepSeekClient
from generation.params.model import STYLE_NAMES

router = APIRouter(tags=["generate"])


@router.post("/generate", response_model=GenerationResponse)
async def generate(req: GenerateRequest, request: Request) -> GenerationResponse:
    """生成:按 image_provider 选生成器(默认模拟器,replicate/fal 走真模型)。"""
    settings: Settings = request.app.state.settings  # 从 app.state 读取(支持测试注入)
    quota_service: QuotaService = request.app.state.quota_service
    remaining_quota = settings.max_free_quota  # 无头请求默认报满额(向后兼容)
    visitor_id = request.headers.get("X-Visitor-Id")
    if visitor_id:
        today = date.today().isoformat()
        if quota_service.remaining(visitor_id, today) == 0:
            raise HTTPException(status_code=429, detail="今日免费额度已用完")
        remaining_quota = quota_service.consume(visitor_id, today)
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

    if settings.image_provider == "replicate":
        if not settings.replicate_api_token:
            raise HTTPException(status_code=500, detail="replicate_api_token 未配置")
        import httpx
        import replicate

        lora_urls = {}
        if settings.lora_weights_dir:
            lora_urls = {style: f"{settings.lora_weights_dir}/{style}.tar" for style in STYLE_NAMES}
        generator = ApiGenerator(
            replicate_client=replicate.Client(
                api_token=settings.replicate_api_token,
                timeout=httpx.Timeout(120.0),
            ),
            model=settings.sdxl_model or SDXL_MODEL,
            lora_urls=lora_urls,
        )
    elif settings.image_provider == "fal":
        if not settings.fal_api_key:
            raise HTTPException(status_code=500, detail="fal_api_key 未配置")
        import os

        os.environ["FAL_KEY"] = settings.fal_api_key
        import fal_client

        generator = FalGenerator(
            fal_client=fal_client,
            model=settings.fal_model or FAL_MODEL,
        )
    else:
        generator = SimulatorGenerator()

    artifact = await generator.generate(req.params, scheme_id, out_dir, req.lang)
    return GenerationResponse(
        scheme_id=scheme_id,
        description=description,
        images=[img.url for img in artifact.images],
        remaining_quota=remaining_quota,
    )
