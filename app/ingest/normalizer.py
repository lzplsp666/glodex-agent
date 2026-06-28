from __future__ import annotations

import re
from typing import Any

from app.ingest.schemas import NormalizedProduct, Platform, ShopType


def normalize_product(raw: dict[str, Any], platform: str) -> NormalizedProduct:
    """把不同平台原始商品字段统一成 NormalizedProduct。"""
    normalized_platform = _normalize_platform(platform, raw)
    if normalized_platform in {"taobao", "tmall"}:
        return _normalize_taobao(raw, normalized_platform)
    if normalized_platform == "jd":
        return _normalize_jd(raw)
    if normalized_platform == "pdd":
        return _normalize_pdd(raw)
    return _normalize_unknown(raw, normalized_platform)


def _normalize_taobao(raw: dict[str, Any], platform: Platform) -> NormalizedProduct:
    title = _first_str(raw, ["title", "item_title", "short_title"])
    shop_name = _first_str(raw, ["shop_title", "shop_name", "nick"])
    price = _first_float(raw, ["zk_final_price", "price", "reserve_price"])
    coupon = _first_float(raw, ["coupon_amount", "coupon_price"])
    return NormalizedProduct(
        item_id=_first_str(raw, ["num_iid", "item_id", "goods_id"], default=""),
        platform=platform,
        title=title,
        price_cny=price,
        coupon_cny=coupon,
        final_price_cny=_minus_or_none(price, coupon),
        shop_name=shop_name,
        shop_type=_detect_shop_type(shop_name),
        sales=_parse_sales(_first(raw, ["volume", "sales", "sell_num"])),
        image_url=_first_str(raw, ["pict_url", "image_url", "pic_url"]),
        url=_first_str(raw, ["item_url", "url", "coupon_share_url"]),
        tags=_build_tags(raw, shop_name),
        raw=raw,
    )


def _normalize_jd(raw: dict[str, Any]) -> NormalizedProduct:
    title = _first_str(raw, ["skuName", "sku_name", "title", "goods_name"])
    shop_name = _first_str(raw, ["shopName", "shop_name", "shopInfo"])
    price = _first_float(raw, ["price", "wlPrice", "lowestPrice", "final_price_cny"])
    return NormalizedProduct(
        item_id=_first_str(raw, ["skuId", "sku_id", "item_id", "goods_id"], default=""),
        platform="jd",
        title=title,
        price_cny=price,
        final_price_cny=price,
        shop_name=shop_name,
        shop_type=_detect_shop_type(shop_name),
        rating=_first_float(raw, ["goodCommentsShare", "rating", "score"]),
        sales=_parse_sales(_first(raw, ["comments", "sales", "inOrderCount30Days"])),
        image_url=_first_str(raw, ["imageUrl", "image_url", "imgUrl"]),
        url=_first_str(raw, ["materialUrl", "url", "item_url"]),
        tags=_build_tags(raw, shop_name),
        raw=raw,
    )


def _normalize_pdd(raw: dict[str, Any]) -> NormalizedProduct:
    title = _first_str(raw, ["goods_name", "title", "goodsName"])
    shop_name = _first_str(raw, ["merchant_name", "mall_name", "shop_name"])
    price = _fen_to_yuan(_first(raw, ["min_group_price", "price", "final_price"]))
    coupon = _fen_to_yuan(_first(raw, ["coupon_discount", "coupon_amount"]))
    return NormalizedProduct(
        item_id=_first_str(raw, ["goods_id", "item_id"], default=""),
        platform="pdd",
        title=title,
        price_cny=price,
        coupon_cny=coupon,
        final_price_cny=_minus_or_none(price, coupon),
        shop_name=shop_name,
        shop_type=_detect_shop_type(shop_name),
        rating=_first_float(raw, ["goods_eval_score", "rating"]),
        sales=_parse_sales(_first(raw, ["sales_tip", "sales", "sold_quantity"])),
        image_url=_first_str(raw, ["goods_thumbnail_url", "image_url", "goods_image_url"]),
        url=_first_str(raw, ["goods_sign", "url", "item_url"]),
        tags=_build_tags(raw, shop_name),
        raw=raw,
    )


def _normalize_unknown(raw: dict[str, Any], platform: Platform) -> NormalizedProduct:
    return NormalizedProduct(
        item_id=_first_str(raw, ["item_id", "id", "goods_id", "skuId"], default=""),
        platform=platform,
        title=_first_str(raw, ["title", "name", "goods_name", "skuName"]),
        price_cny=_first_float(raw, ["price_cny", "price"]),
        shop_name=_first_str(raw, ["shop_name", "shopName", "merchant_name"]),
        image_url=_first_str(raw, ["image_url", "pic_url", "pict_url"]),
        url=_first_str(raw, ["url", "item_url"]),
        raw=raw,
    )


def _normalize_platform(platform: str, raw: dict[str, Any]) -> Platform:
    value = (platform or str(raw.get("platform") or "")).lower()
    if value in {"taobao", "tb"}:
        return "taobao"
    if value in {"tmall", "天猫"}:
        return "tmall"
    if value in {"jd", "jingdong", "京东"}:
        return "jd"
    if value in {"pdd", "pinduoduo", "拼多多"}:
        return "pdd"
    return "unknown"


def _detect_shop_type(shop_name: str | None) -> ShopType:
    if not shop_name:
        return "unknown"
    if "自营" in shop_name:
        return "self_operated"
    if "旗舰店" in shop_name:
        return "flagship"
    if "官方" in shop_name:
        return "official"
    return "normal"


def _build_tags(raw: dict[str, Any], shop_name: str | None) -> list[str]:
    tags: list[str] = []
    raw_text = " ".join(str(value) for value in raw.values())
    if "包邮" in raw_text:
        tags.append("包邮")
    if _first(raw, ["coupon_amount", "coupon_discount"]):
        tags.append("有券")
    shop_type = _detect_shop_type(shop_name)
    if shop_type != "unknown":
        tags.append(shop_type)
    return tags


def _first(raw: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value not in (None, ""):
            return value
    return None


def _first_str(raw: dict[str, Any], keys: list[str], default: str | None = None) -> str:
    value = _first(raw, keys)
    if value in (None, ""):
        return default or ""
    return str(value)


def _first_float(raw: dict[str, Any], keys: list[str]) -> float | None:
    value = _first(raw, keys)
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _fen_to_yuan(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return round(float(value) / 100, 2)
    except (TypeError, ValueError):
        return None


def _minus_or_none(left: float | None, right: float | None) -> float | None:
    if left is None:
        return None
    return round(left - (right or 0), 2)


def _parse_sales(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value)
    match = re.search(r"(\d+(?:\.\d+)?)(万)?", text)
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2):
        number *= 10000
    return int(number)
