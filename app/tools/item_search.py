from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.api.monitor import monitor
from app.tools.item_picker import CandidateItem


Platform = Literal[
    "all",
    "jd",
    "taobao",
    "tmall",
    "pdd",
    "1688",
    "douyin",
    "xiaohongshu",
    "mock",
]


class ItemSearchOutput(BaseModel):
    """ItemSearch 的结构化输出。"""

    platform: str
    query: str
    candidates: list[CandidateItem]
    total_recall: int = 0
    truncated: bool = False
    backend: str = "local_index"
    notice: str | None = None


@tool
async def item_search(
    query: str,
    platform: Platform = "all",
    top_k: int = 20,
    user_id: str | None = None,
) -> ItemSearchOutput:
    """从已有商品索引中检索国内电商候选商品。

    Args:
        query: Planner 拆解后的检索词。
        platform: 平台过滤条件，可指定 jd / taobao / pdd 等，也可使用 all。
        top_k: 最多返回候选数量，默认 20，最大 50。
        user_id: 可选用户 ID；后续接个性化召回时使用。

    Returns:
        标准化候选商品列表，可直接交给 ItemPicker。
    """
    top_k = max(1, min(top_k, 50))
    await monitor.report_tool_start(
        "item_search",
        {
            "query": query,
            "platform": platform,
            "top_k": top_k,
            "user_id": user_id,
        },
    )
    start = time.time()

    # 订单侠等上游 API 负责采集和填充商品库；Agent 工具只负责查询已有索引。
    # TODO: 后续把 _search_local_index 替换为 Milvus / Elasticsearch / 混合召回。
    candidates, total_recall, notice = _search_local_index(
        query=query,
        platform=platform,
        top_k=top_k,
    )

    await monitor.report_tool_end("item_search", int((time.time() - start) * 1000))
    return ItemSearchOutput(
        platform=platform,
        query=query,
        candidates=candidates,
        total_recall=total_recall,
        truncated=total_recall > len(candidates),
        notice=notice,
    )


def _search_local_index(
    query: str,
    platform: str,
    top_k: int,
) -> tuple[list[CandidateItem], int, str | None]:
    """搜索本地 JSON/JSONL 商品索引，作为向量库接入前的轻量实现。"""
    products = _load_local_products()
    if not products:
        return (
            [],
            0,
            "未配置 ITEM_SEARCH_INDEX_PATH 或商品索引为空；请先由数据采集任务填充商品库。",
        )

    normalized_platform = platform.lower()
    filtered = [
        product
        for product in products
        if normalized_platform == "all"
        or str(product.get("platform", "")).lower() == normalized_platform
    ]

    scored: list[tuple[float, CandidateItem]] = []
    for product in filtered:
        candidate = _to_candidate_item(product)
        score = _keyword_score(query, candidate)
        if score > 0:
            scored.append((score, candidate))

    scored.sort(key=lambda item: item[0], reverse=True)
    picked = [candidate for _, candidate in scored[:top_k]]
    return picked, len(scored), None


@lru_cache(maxsize=1)
def _load_local_products() -> list[dict[str, Any]]:
    """加载已有商品索引；支持 JSON 数组或 JSONL。"""
    index_path = os.environ.get("ITEM_SEARCH_INDEX_PATH")
    if not index_path:
        return []

    path = Path(index_path)
    if not path.exists() or not path.is_file():
        return []

    if path.suffix.lower() == ".jsonl":
        products: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if not stripped:
                    continue
                payload = json.loads(stripped)
                if isinstance(payload, dict):
                    products.append(payload)
        return products

    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("items") or payload.get("products") or []
        return [item for item in items if isinstance(item, dict)]
    return []


def _to_candidate_item(product: dict[str, Any]) -> CandidateItem:
    """把商品库中的 dict 兼容转换为 CandidateItem。"""
    return CandidateItem(
        item_id=str(product.get("item_id") or product.get("id") or product.get("goods_id")),
        platform=str(product.get("platform") or "unknown"),
        title=str(product.get("title") or product.get("name") or ""),
        price_cny=_to_float(product.get("price_cny") or product.get("price")),
        shipping_fee_cny=_to_float(product.get("shipping_fee_cny")),
        free_shipping=_to_bool_or_none(product.get("free_shipping")),
        eta_days=_to_int_or_none(product.get("eta_days")),
        shop_name=_to_str_or_none(product.get("shop_name")),
        shop_type=_to_str_or_none(product.get("shop_type")),
        rating=_to_float(product.get("rating")),
        sales=_to_int_or_none(product.get("sales")),
        image_url=_to_str_or_none(product.get("image_url")),
        url=_to_str_or_none(product.get("url")),
        attributes=_to_dict(product.get("attributes")),
        tags=_to_str_list(product.get("tags")),
    )


def _keyword_score(query: str, candidate: CandidateItem) -> float:
    """临时关键词打分；后续向量召回接入后会替换掉。"""
    query_terms = _split_terms(query)
    if not query_terms:
        return 0.0

    searchable_text = " ".join(
        [
            candidate.title,
            candidate.platform,
            candidate.shop_name or "",
            candidate.shop_type or "",
            " ".join(candidate.tags),
            " ".join(str(value) for value in candidate.attributes.values()),
        ]
    ).lower()

    score = 0.0
    for term in query_terms:
        if term in searchable_text:
            score += 1.0
    if candidate.sales:
        score += min(candidate.sales / 10000, 0.2)
    if candidate.rating:
        score += max(candidate.rating - 4.0, 0) * 0.1
    return score


def _split_terms(query: str) -> list[str]:
    return [term.lower() for term in query.replace("，", " ").replace(",", " ").split() if term]


def _to_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int_or_none(value: Any) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"true", "1", "yes", "包邮"}:
            return True
        if lowered in {"false", "0", "no", "不包邮"}:
            return False
    return None


def _to_str_or_none(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _to_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _to_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []
