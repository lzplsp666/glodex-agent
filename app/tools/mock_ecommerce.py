"""第一阶段 mock 工具。

这些工具不访问外部网络，只返回固定结构的数据，用来验证 Agent 架构、
Fork 合并、API 返回和编译流程。后续替换真实电商 API 时，尽量保持函数
入参和出参结构不变。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MockItem:
    """用于第一阶段演示的商品结构。"""

    item_id: str
    title: str
    platform: str
    price: int
    material: str
    style: str
    shipping_fee: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "title": self.title,
            "platform": self.platform,
            "price": self.price,
            "material": self.material,
            "style": self.style,
            "shipping_fee": self.shipping_fee,
        }


MOCK_ITEMS: list[MockItem] = [
    MockItem("item_001", "Glodex Air 商务蓝牙耳机", "JD", 189, "metal", "business", 10),
    MockItem("item_002", "LiteSound 轻巧蓝牙耳机", "Taobao", 129, "plastic", "casual", 8),
    MockItem("item_003", "ProBass 金属降噪耳机", "Amazon", 269, "metal", "business", 28),
    MockItem("item_004", "WorkPods 金属办公耳机", "eBay", 199, "metal", "business", 22),
    MockItem("item_005", "ColorBeat 潮流耳机", "Taobao", 159, "plastic", "fashion", 9),
]


def plan_task(task: str) -> dict[str, Any]:
    """把用户输入拆成第一阶段固定子目标。"""

    return {
        "task": task,
        "constraints": {
            "budget_max": 200 if "200" in task else 300,
            "material": "metal" if "金属" in task else None,
            "style": "business" if "商务" in task else None,
        },
        "fork_goals": [
            "budget_filter",
            "material_filter",
            "style_filter",
        ],
    }


def search_items(query: str) -> list[dict[str, Any]]:
    """返回一组 mock 商品候选。"""

    _ = query
    return [item.to_dict() for item in MOCK_ITEMS]


def filter_items(
    *,
    goal: str,
    items: list[dict[str, Any]],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """按子目标筛选商品，模拟 fork 子 Agent 的工作。"""

    if goal == "budget_filter":
        budget_max = int(constraints.get("budget_max") or 999999)
        matched = [item for item in items if int(item["price"]) <= budget_max]
        summary = f"预算筛选命中 {len(matched)} 个候选。"
    elif goal == "material_filter":
        material = constraints.get("material")
        matched = [item for item in items if not material or item["material"] == material]
        summary = f"材质筛选命中 {len(matched)} 个候选。"
    elif goal == "style_filter":
        style = constraints.get("style")
        matched = [item for item in items if not style or item["style"] == style]
        summary = f"风格筛选命中 {len(matched)} 个候选。"
    else:
        matched = items
        summary = "未知筛选目标，保留全部候选。"

    return {
        "matched_item_ids": [item["item_id"] for item in matched],
        "summary": summary,
    }


def compare_prices(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按商品总价排序，模拟比价工具。"""

    compared = []
    for item in items:
        total_price = int(item["price"]) + int(item["shipping_fee"])
        compared.append({**item, "total_price": total_price})
    return sorted(compared, key=lambda item: item["total_price"])


def build_shopping_summary(items: list[dict[str, Any]]) -> str:
    """生成第一阶段可读的采购清单。"""

    if not items:
        return "没有找到同时满足条件的商品。"

    lines = ["# Glodex Agent 第一阶段采购建议", ""]
    for index, item in enumerate(items[:3], start=1):
        lines.append(
            f"{index}. {item['title']} - {item['platform']} - "
            f"商品价 {item['price']}，运费 {item['shipping_fee']}，总价 {item['total_price']}"
        )
    lines.append("")
    lines.append("说明：当前结果来自 mock 工具，用于验证 Agent 架构闭环。")
    return "\n".join(lines)
