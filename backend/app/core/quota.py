import threading


class QuotaService:
    """匿名访客每日免费额度计数(内存存储,重启清零)。

    结构:`{visitor_id: {date_str: used_count}}`。新的一天出现新 date_str
    即自然重置,无需定时器。
    """

    def __init__(self, max_free_quota: int):
        self._max = max_free_quota
        self._counts: dict[str, dict[str, int]] = {}
        self._lock = threading.Lock()

    def consume(self, visitor_id: str, date_str: str) -> int:
        """消费一次,返回本次消费后的剩余次数(≥0)。已达上限返回 0 且不累加。"""
        with self._lock:
            per_day = self._counts.setdefault(visitor_id, {})
            used = per_day.get(date_str, 0)
            if used >= self._max:
                return 0
            per_day[date_str] = used + 1
            return self._max - (used + 1)

    def remaining(self, visitor_id: str, date_str: str) -> int:
        with self._lock:
            used = self._counts.get(visitor_id, {}).get(date_str, 0)
            return max(self._max - used, 0)
