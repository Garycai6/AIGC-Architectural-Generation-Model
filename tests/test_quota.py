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
