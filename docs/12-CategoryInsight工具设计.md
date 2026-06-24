# CategoryInsight 工具设计

## 一、核心定位

`CategoryInsight` 是品类洞察工具。

它输入商品品类名称，输出该品类行业结构化参考知识，给主 Agent 做购物决策参考。

简单说，它负责一套很小的垂直 RAG：

```text
品类知识卡片入库
-> 按品类检索相关卡片
-> LLM 提炼成品类洞察
-> 返回给主 AgentLoop
```

它不是通用知识库问答，也不是把长文章整段灌进去。它只服务一个目标：让 Agent 在搜商品和筛商品前，先知道这个品类该怎么看。

## 二、核心用途

用户搜一类商品前 / 后，Agent 先调用它获取品类背景，避免盲目检索，辅助后续筛选比价。

它帮助 Agent：

- 知晓该品类主流材质、常见尺寸、避坑点。
- 知道合理价格区间，能分辨高价溢价 / 劣质低价。
- 获取爆款特征、主流品牌、选购关键属性。

## 三、内部执行链路

`CategoryInsight` 内部执行链路分三层，满足调用链 >= 3，可 fork 并发。

```text
召回
-> 提炼
-> 摘要
```

### 1. 召回

传入品类词，去 RAG 商品知识库（向量索引）检索该品类文档。

可召回内容包括：

- 爆款卡片
- 属性图谱
- 价格区间数据

### 2. 提炼

LLM 从召回文档里抽取结构化字段：

- 均价
- 主流材质
- 优缺点
- 避坑点
- 热门规格

### 3. 摘要

压缩精简，封装为统一 `CategoryInsightOutput` 结构化对象返回。

### 4. 主体函数

`CategoryInsight` 可以暴露 `depth` 参数：

- `quick`：主 loop 直接调用，快速返回压缩后的结构化品类常识。
- `deep`：适合通过 `dispatch_tool` fork 子 Agent 执行，跑更完整的提炼链路。

```python
@tool
async def category_insight(
    category: str,
    depth: Literal["quick", "deep"] = "quick",
) -> CategoryInsightOutput:
    """获取一个品类的结构化常识。"""
    await monitor.report_tool_start("category_insight", {
        "category": category,
        "depth": depth,
    })
    t0 = time.time()

    top_k = 8 if depth == "quick" else 15
    cards = await _recall_cards(category, top_k)
    grouped = _split_by_type(cards)

    components = _extract_components(grouped["bestseller"])
    bestsellers = _extract_bestsellers(grouped["bestseller"])
    price_tiers = _extract_price_tiers(grouped["price_range"])

    if depth == "deep":
        attributes = _extract_attributes(grouped["attribute"])
    else:
        attributes = []

    confidence = (
        sum(c.confidence for c in cards) / len(cards) if cards else 0.0
    )

    ...
```

## 四、RAG 商品知识库的最小形态

### 4.1 知识库里面放什么

Glodex 的品类知识库不把整个互联网的商品评测都灌进去，只放三类结构化卡片。

| 卡片类型 | 内容样例 | 作用 |
| --- | --- | --- |
| 爆款卡片 | `旅行三件套：洗漱包 / 鞋包 / 数码线收纳` | 给 `ItemSearch` 拆 sub-query |
| 属性图谱卡片 | `材质：尼龙 60% / 帆布 25% / 牛津布 15%；防水占 70%` | 给 `ItemPicker` 判断典型属性 |
| 价格区间卡片 | `便宜款 60-150 / 中档 150-400 / 高端 400+ 多见品牌联名` | 给 `ItemPicker` 判断价格档位 |

每张卡片都是结构化的，不把博主长文整段灌进去。这一点和通用 RAG 不一样。

### 4.2 知识库 schema

```python
# app/recall/category_kb.py
from pydantic import BaseModel
from typing import Literal


class CategoryCard(BaseModel):
    card_id: str
    category: str
    card_type: Literal["bestseller", "attribute", "price_range"]
    summary: str
    raw_evidence: list[str]
    last_updated: str
    confidence: float
```

字段说明：

- `category`：标准化品类名，例如 `旅行三件套`。
- `card_type`：区分三种业务卡片类型。
- `summary`：已经提炼好的一段结论，LLM 无需再做长文本精读。
- `raw_evidence`：支撑结论的 1-3 段原始证据。
- `last_updated`：更新时间。
- `confidence`：0-1 置信度，来自数据或人工标注。

### 4.3 知识库灌库

Glodex 使用 Milvus 作为品类卡片向量库。离线脚本读取本地 `jsonl` 结构化卡片，生成 embedding 后写入 Milvus。

```python
# scripts/build_category_kb.py
import json
from pathlib import Path

from pymilvus import MilvusClient

CARDS_PATH = Path("data/category_cards.jsonl")
COLLECTION_NAME = "glodex_category_kb"
VECTOR_DIM = 1024


client = MilvusClient(uri="http://localhost:19530")


def iter_cards():
    with CARDS_PATH.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                yield json.loads(line)


def build_embedding_text(card: dict) -> str:
    return f"{card['category']} {card['card_type']} {card['summary']}"
```

灌库要点：

- 数据源是 `data/category_cards.jsonl`。
- 每行是一张结构化 `CategoryCard`。
- 向量文本优先使用 `category + card_type + summary`。
- Milvus 存向量，同时保留 `card_id`、`category`、`card_type`、`summary`、`raw_evidence`、`last_updated`、`confidence` 等元数据字段。
- `VECTOR_DIM` 与项目 Query 塔输出维度保持一致。

### 4.4 检索逻辑

工具调用：

```text
CategoryInsight("旅行收纳袋")
```

内部执行：

```text
category/query
-> 生成 embedding
-> Milvus 检索相关 CategoryCard
-> 取回 top_k 卡片
-> LLM 提炼均价、材质、规格、避坑点、品牌梯队
-> 返回 CategoryInsightOutput
```

检索只查品类卡片，不查具体商品。具体商品仍由 `ItemSearch` 负责。

### 4.5 知识库刷新策略

知识库刷新不是工具运行时的一部分，而是独立的离线任务。

| 刷新类型 | 频率 | 数据源 |
| --- | --- | --- |
| 爆款卡片 | 每周 | 内部销售榜 + 平台公开榜单 |
| 属性图谱卡片 | 每月 | 商品库属性聚合 |
| 价格区间卡片 | 每月 | 历史成交价分位数 |

刷新与上线之间需要评测兜底：召回评测、冷启动 WebSearch 兜底、多语言归一、索引别名切换等。

## 五、调用位置

`CategoryInsight` 由主 AgentLoop 在 Think 阶段决定是否调用。

适合调用的情况：

- 用户只给了模糊品类，还没有明确搜索词。
- 用户想先了解某类商品怎么选。
- Planner 拆出了多个品类，需要分别看行情。
- 后续 `ItemPicker` 需要品类常识做筛选依据。
- 主 Agent 不确定某个价格是否合理，需要品类价格区间参考。

不适合调用的情况：

- 用户已经给了明确商品关键词和筛选条件，可以直接 `ItemSearch`。
- 当前问题是具体商品价格比较，应走 `PriceCompare`。
- 当前问题是最终推荐表达，应走 `ShoppingSummary`。

典型调用链路：

```text
用户需求
-> Planner 拆解品类
-> 主 AgentLoop Think 判断是否需要品类洞察
-> CategoryInsight 检索品类知识卡片
-> 输出 insight
-> ItemSearch / ItemPicker 使用 insight
```

如果通过 `dispatch_tool` fork，主 loop 不需要看到 5-15 张原始 `CategoryCard`。子 Agent 跑完三步管线后，回传给主 loop 的应该是压缩后的结果，例如：

```text
旅行三件套品类常识:
- 典型组件: 洗漱包 / 鞋包 / 数码线收纳
- 爆款 5 件: （清单）
- 价格档位: 便宜款 60-150 / 中档 150-400 / 高端 400+
- 数据置信度 0.78
```

这就是 `调用链 >= 3` 加上 `上下文要隔离` 触发 fork 的价值：原始卡片留在子 Agent 内部，主 loop 只拿压缩洞察。

## 六、典型使用场景

### 场景 1：多品类并行查询

用户需求：

```text
收纳袋、保温杯、帆布包三个品类分别看行情，再比价
```

主 Agent 识别多个独立品类，调用多个 `dispatch_tool` 并发 fork 子 Agent。

每个子 Agent 单独跑：

```text
CategoryInsight("收纳袋")
CategoryInsight("保温杯")
CategoryInsight("帆布包")
```

并行拿到三个品类洞察，提速。

### 场景 2：单品类前置调研

用户需求：

```text
买旅行收纳袋，不要塑料小众款
```

主 Agent 先调用：

```text
CategoryInsight("旅行收纳袋")
```

获取：

- 合理价格区间
- 主流材质（帆布 / 硅胶 / 塑料）
- 小众品牌
- 避坑点

再拿着这份洞察去 `ItemSearch` 检索，筛选、比价更精准。

## 七、输出内容

`CategoryInsight` 输出结构化 insight，包含：

- 品类均价区间
- 主流材质、规格、优缺点
- 爆款通用特征
- 选购避坑提醒
- 主流品牌梯队

## 八、和其他工具的上下游关系

上游：

- 用户需求
- Planner 拆解出的品类名称

下游：

- 输出给 `ItemSearch`，检索时过滤不符合品类常识的商品。
- 输出给 `ItemPicker`，筛选时匹配材质 / 预算偏好。

不负责：

- 商品实时价格计算，这属于 `PriceCompare`。
- 单品检索，这属于 `ItemSearch`。
- 个性化打分。

### 8.1 喂给 ItemPicker 的字段

`CategoryInsight` 要提前约定好哪些字段会被 `ItemPicker` 消费。

| ItemPicker 关心 | 来自 CategoryInsight 的字段 |
| --- | --- |
| 套装类商品有没有缺组件 | `components` |
| 候选属性是否符合品类主流 | `attributes` 的 distribution 排名前几位 |
| 候选价格是否落在合理档位 | `price_tiers` 的 `range_cny` |
| 决策置信度 | `confidence`，低于 0.5 时主 loop 应补 WebSearch |

## 九、为什么它适合 fork

`CategoryInsight` 内部固定三层链路：

```text
向量召回 -> 提炼 -> 摘要
```

调用链深度 >= 3，命中 `dispatch_tool` 三大 fork 条件。

多品类任务可以并行拆分执行。
