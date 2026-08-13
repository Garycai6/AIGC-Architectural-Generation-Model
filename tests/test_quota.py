import json
from pathlib import Path

from backend.app.core.quota import QuotaService


def test_consume_within_limit():
    q = QuotaService(max_free_quota=3)
    assert q.consume("v1", "2026-08-12") == 2
    assert q.consume("v1", "2026-08-12") == 1
    assert q.consume("v1", "2026-08-12") == 0


def test_consume_over_limit_returns_zero_no_increment():
    q = QuotaService(max_free_quota=1)
    assert q.consume("v1", "2026-08-12") == 0
    assert q.consume("v1", "2026-08-12") == 0  # 超限后不再累加,保持 0
    assert q.remaining("v1", "2026-08-12") == 0


def test_resets_on_new_date():
    q = QuotaService(max_free_quota=2)
    q.consume("v1", "2026-08-12")
    q.consume("v1", "2026-08-12")
    assert q.consume("v1", "2026-08-12") == 0  # 当天额度耗尽
    assert q.consume("v1", "2026-08-13") == 1  # 新的一天额度刷新 → 2-1=1


def test_isolated_per_visitor():
    q = QuotaService(max_free_quota=2)
    q.consume("v1", "2026-08-12")
    q.consume("v1", "2026-08-12")
    assert q.consume("v1", "2026-08-12") == 0  # v1 耗尽
    assert q.consume("v2", "2026-08-12") == 1  # v2 独立计数 → 2-1=1


def test_remaining_read_only():
    q = QuotaService(max_free_quota=5)
    assert q.remaining("v1", "2026-08-12") == 5
    q.consume("v1", "2026-08-12")
    assert q.remaining("v1", "2026-08-12") == 4


def test_persist_writes_file_after_consume(tmp_path: Path):
    storage = tmp_path / "quota.json"
    q = QuotaService(max_free_quota=3, storage_path=storage)
    q.consume("v1", "2026-08-13")
    assert storage.exists()
    data = json.loads(storage.read_text(encoding="utf-8"))
    assert data == {"v1": {"2026-08-13": 1}}


def test_persist_restores_counts_on_reconstruct(tmp_path: Path):
    storage = tmp_path / "quota.json"
    q1 = QuotaService(max_free_quota=3, storage_path=storage)
    q1.consume("v1", "2026-08-13")
    q1.consume("v1", "2026-08-13")
    # 模拟重启:重新构造 → 计数保留
    q2 = QuotaService(max_free_quota=3, storage_path=storage)
    assert q2.remaining("v1", "2026-08-13") == 1
    assert q2.consume("v1", "2026-08-13") == 0  # 继续累减,不重置


def test_persist_corrupt_file_falls_back_to_empty(tmp_path: Path):
    storage = tmp_path / "quota.json"
    storage.write_text("{not-valid-json", encoding="utf-8")
    q = QuotaService(max_free_quota=3, storage_path=storage)
    assert q.remaining("v1", "2026-08-13") == 3  # 降级空 dict,额度满额


def test_persist_memory_mode_when_storage_none(tmp_path: Path):
    q = QuotaService(max_free_quota=3)
    q.consume("v1", "2026-08-13")
    assert not list(tmp_path.glob("*.json"))  # 无 storage_path 不写盘


def test_persist_prunes_old_dates(tmp_path: Path):
    storage = tmp_path / "quota.json"
    q = QuotaService(max_free_quota=3, storage_path=storage)
    q.consume("v1", "2026-08-01")  # 旧日期(>7 天前)
    q.consume("v1", "2026-08-13")  # 今天
    # 触发清理(每 PRUNE_INTERVAL 次写)并验证
    q.consume("v2", "2026-08-13")
    data = json.loads(storage.read_text(encoding="utf-8"))
    assert "2026-08-01" not in data["v1"]  # 旧日期被清掉
    assert "2026-08-13" in data["v1"]  # 近记录保留
