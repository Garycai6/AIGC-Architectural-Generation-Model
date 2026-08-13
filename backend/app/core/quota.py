import json
import logging
import os
import threading
from datetime import date, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

PRUNE_INTERVAL = 100
PRUNE_DAYS = 7


class QuotaService:
    """匿名访客每日免费额度计数(JSON 文件持久化,重启保留)。

    结构:`{visitor_id: {date_str: used_count}}`。新的一天出现新 date_str
    即自然重置,无需定时器。storage_path=None 时纯内存(不读写文件)。
    """

    def __init__(self, max_free_quota: int, storage_path: Path | None = None):
        self._max = max_free_quota
        self._storage_path = storage_path
        self._write_count = 0
        self._lock = threading.Lock()
        self._counts: dict[str, dict[str, int]] = {}
        if storage_path is not None:
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._storage_path.read_text(encoding="utf-8"))
            self._counts = {
                str(k): {str(d): int(v) for d, v in day.items()} for k, day in data.items()
            }
        except (
            FileNotFoundError,
            json.JSONDecodeError,
            ValueError,
            AttributeError,
            TypeError,
        ) as exc:
            logger.warning("quota 持久化文件加载失败,降级为空计数: %s", exc)
            self._counts = {}

    def _persist(self) -> None:
        try:
            tmp = self._storage_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._counts), encoding="utf-8")
            os.replace(tmp, self._storage_path)
        except OSError as exc:
            logger.error("quota 持久化写盘失败: %s", exc)

    def _maybe_prune(self) -> None:
        """每 PRUNE_INTERVAL 次写触发,清理 PRUNE_DAYS 天前的记录。"""
        if self._write_count % PRUNE_INTERVAL != 0:
            return
        cutoff = (date.today() - timedelta(days=PRUNE_DAYS)).isoformat()
        self._counts = {
            vid: {d: n for d, n in day.items() if d >= cutoff}
            for vid, day in self._counts.items()
            if any(d >= cutoff for d in day)
        }

    def consume(self, visitor_id: str, date_str: str) -> int:
        """消费一次,返回本次消费后的剩余次数(≥0)。已达上限返回 0 且不累加。"""
        with self._lock:
            per_day = self._counts.setdefault(visitor_id, {})
            used = per_day.get(date_str, 0)
            if used >= self._max:
                return 0
            per_day[date_str] = used + 1
            if self._storage_path is not None:
                self._write_count += 1
                self._maybe_prune()
                self._persist()
            return self._max - (used + 1)

    def remaining(self, visitor_id: str, date_str: str) -> int:
        with self._lock:
            used = self._counts.get(visitor_id, {}).get(date_str, 0)
            return max(self._max - used, 0)
