# ItemSearch 工具设计

`ItemSearch` 是 Glodex Agent 的第一个核心电商工具。它负责从国内电商平台搜索商品候选，并把不同平台返回的数据整理成统一结构，供主 AgentLoop 后续合流、比价、筛选和总结。

## 一、AgentLoop 链路

国内购物任务的基本链路：

```text
用户购物意图
-> Planner 拆解（预算 / 品类 / 偏好）
-> 主 AgentLoop 在 Think 阶段判断："要跨多个国内平台"
-> dispatch_tool fork 多个同质子 AgentLoop
    ├─ 子 A: 调 item_search(platform="taobao", ...)
    ├─ 子 B: 调 item_search(platform="jd", ...)
    └─ 子 C: 调 item_search(platform="pdd", ...)
-> 多份商品候选合流回主 loop
-> ItemPicker / ShoppingSummary
```

平台不固定三个，主 AgentLoop 可根据用户需求动态决定 fork 哪些平台。

## 二、工具职责

`ItemSearch` 只负责一件事：

**按指定国内平台搜索商品候选，并返回标准化商品列表。**

它应该做：

- 根据 `query` 搜商品。
- 按 `platform` 调用麦手 API 搜索接口。
- 返回候选商品列表（search 接口返回的 10 个基础字段）。
- 异步批量补全 `url`（购买链接/口令，来自 detail 接口）。
- 异步批量补全 `attributes`（多模态模型读图 + 读标题，提取结构化属性）。
- 后续 `_search_local_index` 替换为 Milvus 混合召回：title 关键词检索 + embedding 向量检索。

它不应该做：

- 不做最终推荐。
- 不做复杂主观筛选。
- 不写采购清单。
- 不负责完整跨平台同款归并。

## 三、数据来源

统一使用麦手 API（`appapi.maishou88.com`），一个 API 同时覆盖淘宝/京东/拼多多。

| 平台 | platform | sourceType | 说明 |
| --- | --- | --- | --- |
| 淘宝 | `taobao` | 1 | 含天猫商品 |
| 京东 | `jd` | 2 | 含京东自营和第三方 |
| 拼多多 | `pdd` | 3 | 含多多进宝商品 |

以后可继续加入抖音电商、小红书、1688 等平台，只需扩展 sourceType 即可。

### 3.1 search 接口

```
POST https://appapi.maishou88.com/api/v1/homepage/searchList
```

返回字段：

| 字段 | 说明 |
| --- | --- |
| goodsId | 商品 ID，全局唯一 |
| sourceType | 1:淘宝 2:京东 3:拼多多 |
| title | 商品标题 |
| shopName | 店铺名 |
| originalPrice | 原价（元） |
| actualPrice | 券后价（元） |
| couponPrice | 优惠券金额（元） |
| commission | 佣金（元） |
| monthSales | 月销量 |
| picUrl | 主图 CDN 链接（公网可访问） |

### 3.2 detail 接口

```
POST https://appapi.maishou88.com/api/v3/goods/detail
POST https://msapi.maishou88.com/api/v1/share/getTargetUrl
```

补全以下字段：

| 字段 | 来源 | 说明 |
| --- | --- | --- |
| url / kl | getTargetUrl | 购买链接（appUrl/schemaUrl）+ 复制口令（kl） |
| detail | goods/detail | 商品详情原始 JSON，仅用于字段补全和 attributes 生成，不入库 |

## 四、商品入库统一结构

入库 Milvus 前使用 `NormalizedProduct` 标准化。精简为 **11 个固定字段 + 1 个动态属性字段 + 1 段向量化文本 + 1 个向量字段**，只保留检索和推荐真正需要的内容。

### 4.1 固定字段（11 个，来自 API 原生返回）

| 字段 | 类型 | Milvus dtype | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| item_id | str | VARCHAR(128) PRIMARY | goodsId | 商品唯一 ID |
| platform | enum | VARCHAR(32) | sourceType 映射 | taobao / jd / pdd |
| title | str | VARCHAR(512) | title（API 直接返回） | 商品标题，embedding 文本主来源 |
| price_cny | float | FLOAT | originalPrice | 标价（元） |
| coupon_cny | float | FLOAT | couponPrice | 优惠券金额（元） |
| final_price_cny | float | FLOAT | actualPrice | 券后价（元） |
| shop_name | str | VARCHAR(256) | shopName | 店铺名，embedding 文本来源 |
| sales | int | INT64 | monthSales | 月销量 |
| image_url | str | VARCHAR(1024) | picUrl | 主图 CDN 链接，多模态读图输入 |
| url | str | VARCHAR(1024) | detail 接口 getTargetUrl | 购买链接 / 口令 |

### 4.2 扩展动态字段（1 个，多模态模型提取）

| 字段 | 类型 | Milvus dtype | 来源 | 说明 |
| --- | --- | --- | --- | --- |
| attributes_json | JSON | JSON | 多模态模型（图 + 文） | 结构化商品属性，不限字段数 |

attributes 不预定义字段名，不同品类提取不同属性。示例（内存条）：

```json
{
  "颜色": "白色",
  "容量": "32GB(16GB×2)",
  "代数": "DDR5",
  "频率": "6000MHz",
  "时序": "C28",
  "灯效": "RGB",
  "颗粒": "海力士 A-die",
  "散热": "马甲条",
  "适用": "台式机"
}
```

### 4.3 向量化字段

| 字段 | 类型 / 维度 | 说明 |
| --- | --- | --- |
| embedding_text | VARCHAR(4096) | `title + shop_name + attributes(key:value)`，用于生成商品向量，也便于排查 |
| embedding | FLOAT_VECTOR(1024) | 由 embedding / Item Tower 生成，索引类型 IVF_FLAT，度量 COSINE |

embedding 文本拼接逻辑（入库时调用 `NormalizedProduct.embedding_text()`）：

```python
def embedding_text(self) -> str:
    """拼接 title + shop_name + attributes 做向量化文本。"""
    attr_text = " ".join(f"{k}:{v}" for k, v in self.attributes.items())
    return " ".join(p for p in [self.title, self.shop_name or "", attr_text] if p)
```

示例 embedding 文本：

> `金百达 32GB(16G×2) 套装 DDR5 6000 台式机内存条 金百达京东自营旗舰店 容量:32GB 代数:DDR5 频率:6000MHz 时序:C28 灯效:RGB 颗粒:海力士A-die 散热:马甲条`

### 4.4 不入库字段

`raw` 不进入 Milvus。麦手 search/detail 的完整原始响应只用于调试、临时日志和字段补全；正式入库只保留标准字段。

### 4.5 被砍掉的字段及原因

| 旧字段 | 砍掉原因 |
| --- | --- |
| raw | 原始响应体积大，且检索/推荐不直接依赖；需要排查时保留临时日志即可 |
| shipping_fee_cny | 麦手 API 不返回运费数据，纯电商场景暂不需要 |
| free_shipping | 同上，API 无此字段 |
| eta_days | API 无配送时效数据 |
| shop_type | API 不返回店铺类型（自营/旗舰/普通），无法可靠区分 |
| rating | API 不返回评分 |
| category | 标题已包含品类信息，且多模态可提取更精确的分类 |
| tags | 无上游数据源，由 attributes 覆盖标签需求 |

## 五、多模态属性提取流程

```
item_search 调用
  -> 麦手 search API → 批量获取 picUrl + title
  -> 并发调用多模态模型（图: picUrl + 文: title）
  -> 模型返回结构化 JSON（品类相关属性）
  -> 写入 attributes 字段
  -> 入库 Milvus
```

多模态 prompt 示例（以内存条为例）：

```text
你是一个电商商品属性提取器。根据商品图片和标题，提取以下结构化属性，
只返回 JSON，不要额外文字。

品类：内存条
提取字段：颜色、容量、代数(DDR4/DDR5)、频率、时序、灯效(RGB/无)、
         颗粒品牌、散热(马甲条/裸条)、适用(台式机/笔记本)

图片: <picUrl>
标题: 金百达 32GB(16G×2) 套装 DDR5 6000 台式机内存条 C28 RGB
```

模型输出：

```json
{
  "颜色": "白色",
  "容量": "32GB(16GB×2)",
  "代数": "DDR5",
  "频率": "6000MHz",
  "时序": "C28",
  "灯效": "RGB",
  "颗粒": "海力士 A-die",
  "散热": "马甲条",
  "适用": "台式机"
}
```

不同品类使用不同的提取字段定义即可，无需改 schema。

## 六、Milvus Collection Schema

```json
{
  "collection_name": "glodex_items",
  "fields": [
    { "name": "item_id",           "dtype": "VARCHAR",  "max_length": 128,  "is_primary": true },
    { "name": "platform",          "dtype": "VARCHAR",  "max_length": 32 },
    { "name": "title",             "dtype": "VARCHAR",  "max_length": 512 },
    { "name": "price_cny",         "dtype": "FLOAT" },
    { "name": "coupon_cny",        "dtype": "FLOAT" },
    { "name": "final_price_cny",   "dtype": "FLOAT" },
    { "name": "shop_name",         "dtype": "VARCHAR",  "max_length": 256 },
    { "name": "sales",             "dtype": "INT64" },
    { "name": "image_url",         "dtype": "VARCHAR",  "max_length": 1024 },
    { "name": "url",               "dtype": "VARCHAR",  "max_length": 1024 },
    { "name": "attributes_json",   "dtype": "JSON" },
    { "name": "embedding_text",    "dtype": "VARCHAR",  "max_length": 4096 },
    { "name": "embedding",         "dtype": "FLOAT_VECTOR", "dim": 1024 }
  ],
  "index_params": [
    { "field_name": "embedding",   "index_type": "IVF_FLAT", "metric_type": "COSINE", "params": { "nlist": 128 } },
    { "field_name": "item_id",     "index_type": "Trie" },
    { "field_name": "platform",    "index_type": "Trie" },
    { "field_name": "price_cny",   "index_type": "STL_SORT" },
    { "field_name": "sales",       "index_type": "STL_SORT" }
  ]
}
```

title 字段保留为关键词检索入口；embedding 字段用于语义向量召回。第一版混合检索可以使用 `title contains + embedding ANN`，后续再升级到 sparse/BM25。

## 七、Recall 客户端定位

`app/recall/ann.py` 保留历史文件名，但后续不再把它理解成“自己实现 ANN 算法”。

它的实际职责是封装 Milvus 混合检索策略：

```text
title 关键词检索
  -> Milvus query/filter

embedding 向量检索
  -> Milvus search(anns_field="embedding")

业务合并
  -> item_id 去重
  -> title + embedding 双路命中加权
  -> 输出统一商品 dict
```

Milvus 仍然是数据库和 ANN 引擎，`ann.py` 只负责项目内可复用的召回策略。后续 `item_search.py` 和入库验证脚本都应复用这层能力，避免在多个地方重复写合并逻辑。

## 八、搜索接口（item_search 工具签名）

```python
class CandidateItem(BaseModel):
    """item_search 返回的候选商品。"""
    item_id: str
    platform: str
    title: str
    price_cny: float | None = None
    coupon_cny: float | None = None
    final_price_cny: float | None = None
    shop_name: str | None = None
    sales: int | None = None
    image_url: str | None = None
    url: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class ItemSearchOutput(BaseModel):
    platform: str
    query: str
    candidates: list[CandidateItem]
    total_recall: int = 0
    truncated: bool = False
    backend: str = "milvus"
    notice: str | None = None


@tool
async def item_search(
    query: str,
    platform: Literal["all", "taobao", "jd", "pdd"] = "all",
    top_k: int = 20,
    user_id: str | None = None,
) -> ItemSearchOutput:
    """从商品索引中检索国内电商候选商品。

    Args:
        query: Planner 拆解后的检索词。
        platform: 平台过滤，可指定 taobao/jd/pdd，也可用 all。
        top_k: 返回候选数量，默认 20，最大 50。
        user_id: 可选用户 ID，预留个性化召回。

    Returns:
        标准化候选商品列表。
    """
```

## 九、与其他工具的关系

```text
Planner
  -> 拆出预算 / 品类 / 偏好

dispatch_tool
  -> fork 多个同质子 AgentLoop
  -> 每个子 loop 调一个平台的 item_search

ItemSearch
  -> title 关键词召回 + embedding 向量召回（Milvus ANN）
  -> item_id 去重，双路命中加权重排
  -> 返回各平台候选商品

主 AgentLoop
  -> 合流多个平台候选

ItemPicker
  -> 按 attributes（材质/颜色/规格）和价格做二次筛选
  -> 不再依赖 shop_type / rating / shipping（这些字段已砍）

ShoppingSummary
  -> 生成最终采购建议
```

ItemPicker 的评分逻辑需要同步调整（原来依赖 rating / shop_type / free_shipping / eta_days，这些字段移除后改为依赖 attributes + 价格 + 销量）。

## 十、数据采集链路

```text
麦手 search API（60 条/页）
  -> 写入临时表（item_id / platform / title / price_cny / ... / image_url）
  -> 并发调 detail API 补 url（购买链接 + 口令）
  -> 并发调多模态模型补 attributes（图片 + 标题 -> 结构化 JSON）
  -> 拼 embedding_text
  -> 调 embedding / Item Tower 生成 embedding
  -> 写入 Milvus glodex_items
  -> item_search 可查
```

## 十一、验收标准

1. `item_search(platform="taobao" / "jd" / "pdd", ...)` 能在 Milvus 中完成 title + embedding 混合召回并返回统一结构。
2. schema 能被 LangChain `StructuredTool` 使用。
3. 主 AgentLoop 可以通过 `dispatch_tool` fork 多个平台搜索任务。
4. 多个平台结果可以合流回 `state.context.candidate_items`。
5. `CandidateItem` 不再包含 shipping / rating / shop_type / tags / category 字段。
6. `attributes` 由多模态模型（图+文）提取，不同品类返回不同属性字段。
7. `url` 和 `image_url` 均为公网可访问 URL。
8. ItemPicker 评分逻辑已适配新的精简字段。
