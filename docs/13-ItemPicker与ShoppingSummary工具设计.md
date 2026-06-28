# ItemPicker 与 ShoppingSummary 工具设计

## 一、工具定位

`ItemPicker` 和 `ShoppingSummary` 是购物链路后半段的两个工具。

```text
ItemSearch
-> PriceCompare
-> ItemPicker
-> ShoppingSummary
```

`ItemPicker` 负责判断商品是否适合用户。

`ShoppingSummary` 负责把最终结果整理成推荐清单和理由。

## 二、ItemPicker

`ItemPicker` 负责根据多维条件筛选和重排商品。

它接收 `PriceCompare` 排好价格后的商品列表，再结合用户需求、用户长期偏好、品类洞察结果进行筛选。

### 2.1 主要判断维度

- 材质
- 风格
- 评分
- 销量
- 店铺
- 是否自营
- 用户长期偏好
- `CategoryInsight` 输出结果

当前项目面向国内电商，候选商品字段不能假设完整。`ItemPicker` 只把 `item_id`、`platform`、`title` 视为稳定字段，其他字段都按可选处理：

- `price_cny`
- `shipping_fee_cny`
- `free_shipping`
- `eta_days`
- `shop_name`
- `shop_type`
- `rating`
- `sales`
- `attributes`
- `tags`

字段缺失时不默认淘汰商品；只有明确违反用户硬约束时才排除。无法判断的信息会进入 `flags`，例如“材质未知，需二次确认”。

### 2.1.1 国内版核心逻辑

`ItemPicker` 的筛选顺序：

1. 先检查硬约束，例如“不要塑料”“必须包邮”“不要预售”“只要自营”“预算上限”。
2. 明确违反硬约束的商品直接进入 `rejected_brief`。
3. 字段缺失导致无法判断时不直接排除，只添加风险标记。
4. 对剩余商品按价格、包邮、配送时效、评分、销量、店铺可信度、用户软偏好和品类洞察打分。
5. 按综合分排序，默认返回最多 3 件商品。

跨境场景中的关税、免税、跨境直邮等字段当前不进入国内版核心逻辑。

### 2.2 和 CategoryInsight 的关系

`CategoryInsight` 给 `ItemPicker` 提供品类常识。

例如：

- `components`：判断套装类商品有没有缺组件。
- `attributes`：判断候选属性是否符合品类主流。
- `price_tiers`：判断候选价格是否落在合理档位。
- `confidence`：判断品类洞察是否可信。

### 2.3 ItemPicker 不做的事

`ItemPicker` 不负责：

- 搜商品，这属于 `ItemSearch`。
- 算最终价格，这属于 `PriceCompare`。
- 生成最终推荐话术，这属于 `ShoppingSummary`。

## 三、ShoppingSummary

`ShoppingSummary` 负责把筛选后的商品结果生成最终推荐清单和理由。

它接收 `ItemPicker` 输出的最终候选商品，生成用户可读的购买建议。

### 3.1 输出内容

`ShoppingSummary` 输出：

- 推荐商品清单
- 每个商品的推荐理由
- 价格和平台信息
- 关键优缺点
- 不推荐商品的简要原因
- 最终购买建议

当前实现中，`ShoppingSummary` 接收 `ItemPicker` 的 `PickedItem` 列表和用户原始需求，调用 LLM 生成 Markdown 最终答复。它是终结性工具，一旦被调用，主 AgentLoop 应认为购物链路已经进入收敛阶段，不应该再发起新的搜索或筛选动作。

输出结构：

- `final_text`：给前端展示的最终 Markdown。
- `picks`：本次最终推荐的精选商品。
- `learned_preferences`：本轮识别出的新偏好，后续可写入长期记忆 Store。

国内版总结只关注商品、平台、价格、推荐理由和风险提示，不输出关税、跨境直邮、免税等跨境信息。

### 3.2 ShoppingSummary 不做的事

`ShoppingSummary` 不负责：

- 重新搜索商品。
- 重新计算价格。
- 重新筛选商品。

它只负责最终表达和总结。

## 四、完整链路

```text
用户需求
-> Planner 拆解预算 / 品类 / 偏好
-> CategoryInsight 获取品类常识
-> ItemSearch 搜多平台商品
-> PriceCompare 计算最终到手价并排序
-> ItemPicker 按用户偏好和品类规则筛选
-> ShoppingSummary 生成最终推荐清单
```
