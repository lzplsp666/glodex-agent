from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Platform = Literal["taobao", "tmall", "jd", "pdd", "1688", "douyin", "xiaohongshu", "unknown"]
ShopType = Literal["self_operated", "flagship", "official", "normal", "unknown"]


class NormalizedProduct(BaseModel):
    """入库前统一后的国内商品结构。"""

    item_id: str
    platform: Platform
    title: str
    price_cny: float | None = None
    coupon_cny: float | None = None
    final_price_cny: float | None = None
    shipping_fee_cny: float | None = None
    free_shipping: bool | None = None
    eta_days: int | None = None
    shop_name: str | None = None
    shop_type: ShopType = "unknown"
    rating: float | None = None
    sales: int | None = None
    image_url: str | None = None
    url: str | None = None
    category: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    def embedding_text(self) -> str:
        """生成商品向量化文本，后续写入向量库时使用。"""
        attr_text = " ".join(f"{key}:{value}" for key, value in self.attributes.items())
        tag_text = " ".join(self.tags)
        return " ".join(
            part
            for part in [
                self.title,
                self.category or "",
                self.shop_name or "",
                tag_text,
                attr_text,
            ]
            if part
        )
