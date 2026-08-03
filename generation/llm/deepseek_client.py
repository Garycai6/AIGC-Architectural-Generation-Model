import json
import logging
from typing import Literal

from openai import AsyncOpenAI

from generation.params.model import BuildingParams

logger = logging.getLogger(__name__)

DEEPSEEK_MODEL = "deepseek-chat"


class DeepSeekClient:
    """DeepSeek 文本层封装——自然语言解析与方案描述。"""

    def __init__(self, api_key: str, base_url: str = "https://api.deepseek.com"):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def describe_scheme(self, params: BuildingParams, lang: Literal["en", "zh"]) -> str:
        system = (
            "你是一名建筑方案文案助手。根据给定的建筑参数,用简洁专业的中文描述建筑方案。"
            if lang == "zh"
            else (
                "You are an architectural copywriter. "
                "Describe the building scheme concisely in English."
            )
        )
        resp = await self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": params.model_dump_json()},
            ],
            temperature=0.7,
        )
        return resp.choices[0].message.content or ""

    async def parse_nl_to_params(self, text: str) -> BuildingParams:
        """自然语言描述 → BuildingParams。要求模型输出严格 JSON。"""
        system = (
            "把用户的自然语言建筑描述转换为 JSON 参数。只输出 JSON,不要额外文字。"
            '字段:style(modern/neoclassic/european/nordic)、floors(1-6)、'
            'width_m(6-20)、depth_m(5-18)、materials(数组,glass/stone/brick/wood)、'
            'roof(flat/pitched/hipped)、environment(urban/suburb/rural/seaside)。'
            '无法确定的字段给合理默认值。'
        )
        resp = await self._client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            temperature=0.2,
        )
        raw = resp.choices[0].message.content or "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("DeepSeek 返回非法 JSON: %s", raw[:200])
            raise ValueError("无法解析建筑参数") from None
        return BuildingParams(**data)
