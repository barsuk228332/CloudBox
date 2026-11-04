from __future__ import annotations

import math


def total_pages(total: int, page_size: int) -> int:
    if total <= 0:
        return 1
    return max(1, math.ceil(total / page_size))


def clamp_page(page: int, pages: int) -> int:
    if pages <= 1:
        return 0
    return max(0, min(page, pages - 1))


def offset_for(page: int, page_size: int) -> int:
    return max(0, page) * page_size
