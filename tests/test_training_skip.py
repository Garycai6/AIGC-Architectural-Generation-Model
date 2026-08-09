"""train/verify 含 diffusers/torch,本机无 GPU 直接 skip(与 replicate 测试同思路)。"""

import pytest

torch = pytest.importorskip("torch")


def test_torch_available_in_ci():
    assert torch is not None
