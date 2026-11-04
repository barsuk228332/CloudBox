from __future__ import annotations

# Максимальное значение, которое гарантированно помещается в SQLite INTEGER/BIGINT.
MAX_TG_ID = 2**63 - 1


def is_valid_tg_id(value: int) -> bool:
    return isinstance(value, int) and 0 < value <= MAX_TG_ID
