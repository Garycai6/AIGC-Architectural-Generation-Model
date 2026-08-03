from unittest.mock import AsyncMock, patch

import pytest

from generation.llm.deepseek_client import DeepSeekClient
from generation.params.model import BuildingParams


@pytest.mark.asyncio
@patch("generation.llm.deepseek_client.AsyncOpenAI")
async def test_describe_scheme_zh(mock_openai):
    mock_chat = AsyncMock()
    mock_chat.completions.create.return_value.choices[0].message.content = "现代风格三层住宅"
    mock_openai.return_value.chat = mock_chat

    client = DeepSeekClient(api_key="test-key")
    params = BuildingParams(
        style="modern",
        floors=3,
        width_m=10.0,
        depth_m=8.0,
        materials=["glass"],
        roof="flat",
        environment="suburb",
    )
    text = await client.describe_scheme(params, lang="zh")
    assert "现代风格" in text


@pytest.mark.asyncio
@patch("generation.llm.deepseek_client.AsyncOpenAI")
async def test_parse_nl_to_params(mock_openai):
    mock_chat = AsyncMock()
    mock_chat.completions.create.return_value.choices[0].message.content = (
        '{"style": "modern", "floors": 2, "width_m": 9.0, "depth_m": 7.0, '
        '"materials": ["brick"], "roof": "pitched", "environment": "rural"}'
    )
    mock_openai.return_value.chat = mock_chat

    client = DeepSeekClient(api_key="test-key")
    params = await client.parse_nl_to_params("帮我设计一栋两层的乡村砖房")
    assert isinstance(params, BuildingParams)
    assert params.style == "modern"
    assert params.floors == 2
