# PRD: Glodex Agent — 跨平台电商选品与比价多智能体系统

> **版本**: v0.1 | **状态**: Draft | **作者**: AI Agent | **日期**: 2026-06-21

---

## Problem Statement

跨境电商买家在选购商品时面临三个核心痛点：

1. **信息分散**：Amazon、eBay、淘宝、京东等平台各自独立，用户需要逐个搜索、手动对比，无法一站式完成"搜全平台 → 比价 → 出清单"的完整流程。
2. **决策成本高**：商品数量庞大（同款蓝牙耳机可能有上百个 SKU），人工筛选耗时费力，且容易遗漏性价比最优的选择。
3. **缺乏个性化**：每个用户有不同的偏好（预算、材质、风格、品牌倾向），现有平台搜索无法理解这些隐性需求，搜索结果"千人一面"。

Glodex Agent 要解决的核心问题：**用户用一个自然语言需求，就能得到跨平台的、符合个人偏好的选品建议与采购清单。**

---

## Solution

Glodex Agent 是一个 **LLM 驱动的多智能体系统**，核心思路：

- **一个主 AgentLoop** 理解用户需求，制定计划，调度工具
- **9 大工具**覆盖选品全链路：品类洞察、跨平台商品搜索、筛选过滤、比价、物流计算、报告输出
- **同质 Fork 架构**：复杂任务按维度拆解，fork 出多个子 Agent 并行执行，结果回传主 Agent 汇总
- **三层记忆系统**：工作记忆（当前会话）→ 短期记忆（Checkpointer 会话内）→ 长期记忆（向量库跨会话持久化）
- **Cache Breakpoint 压缩**：在保证 KV Cache 命中率的前提下压缩长上下文

用户通过自然语言交互（Web UI），背后 Agent 自动完成"理解意图 → 搜索筛选 → 比价分析 → 输出清单"的全流程。

---

## User Stories

### 核心购物流程

1. As a **跨境买家**, I want to **用自然语言描述购物需求**（如"预算 200 以内的蓝牙耳机，金属材质，商务风"），so that **不需要手动填筛选条件，系统自动理解我的意图**。
2. As a **跨境买家**, I want to **系统同时搜索多个电商平台**（Amazon / eBay / 淘宝 / 京东），so that **不用逐个平台搜，一次拿到全渠道结果**。
3. As a **跨境买家**, I want to **搜索结果按我的偏好自动筛选**（价格、材质、风格、品牌），so that **从海量商品中快速缩小到真正合适的候选集**。
4. As a **跨境买家**, I want to **看到同款商品在不同平台的价格对比**，so that **选最便宜的渠道下单**。
5. As a **跨境买家**, I want to **看到包含关税和运费的完整成本估算**，so that **避免结算时才发现总价超预算**。
6. As a **跨境买家**, I want to **系统生成一份结构化的采购清单报告**（含商品参数、价格对比、推荐理由），so that **可以直接拿去决策或分享**。
7. As a **跨境买家**, I want to **在 Agent 执行过程中实时看到它在做什么**（搜索中、比价中、筛选中），so that **不用对着白屏空等**。
8. As a **跨境买家**, I want to **在执行过程中随时取消任务**，so that **发现搜错了可以及时中止，不用等跑完**。
9. As a **跨境买家**, I want to **在执行过程中纠正参数**（"预算改成 300""不要金属材质"），so that **不用重新来一遍**。

### 品类洞察

10. As a **选品经理**, I want to **查询某个品类的行业趋势数据**（热销子类目、价格带分布、增长方向），so that **知道什么值得卖**。
11. As a **选品经理**, I want to **获取爆款商品的特征分析**（高频关键词、常见卖点、价格区间），so that **选品有数据支撑而不是靠感觉**。
12. As a **选品经理**, I want to **对比不同平台的品类表现差异**（同一品类在 Amazon 和 eBay 的热度分布），so that **知道在哪个平台重点发力**。

### 记忆与个性化

13. As a **回访用户**, I want to **系统记住我的偏好和历史行为**（"上次选了非入耳式""常用京东"），so that **下次搜索自动应用，不用重复说**。
14. As a **回访用户**, I want to **系统记住我上一次的搜索结果和清单**，so that **可以继续上次没做完的比价，或基于历史记录复购**。
15. As a **回访用户**, I want to **系统在新任务中参考我的历史决策**（"上次选的 A 款后来没买，因为…"），so that **推荐越来越准，不反复踩坑**。

### 系统与管理

16. As a **平台管理员**, I want to **查看系统运行状态和性能指标**（任务数、平均耗时、token 消耗），so that **监控系统健康度**。
17. As a **平台管理员**, I want to **管理支持的电商平台和数据源**（添加/关闭某个平台的搜索能力），so that **灵活适配业务变化**。
18. As a **平台管理员**, I want to **查看每个会话的完整执行日志**（LLM 调用、工具调用、Fork 记录），so that **排查问题时有迹可循**。
19. As a **开发者**, I want to **通过 API 集成 Glodex Agent 的能力**（搜索、比价、品类洞察），so that **在自己系统中复用选品能力**。
20. As a **评测人员**, I want to **用标准测试集评估 Agent 的选品质量**（准确率、覆盖率、推荐命中率），so that **有客观指标衡量系统迭代效果**。

---

## Implementation Decisions

### 架构选型

1. **主 AgentLoop + 同质 Fork**（非 Supervisor-Worker）
   - 理由：所有子任务本质上是"对候选集加约束条件"，用同一套工具集即可。同质 Fork 只需一个图模板，扩展新场景只加子目标描述，不写新 Worker 类。文档 `01-Agent架构设计.md` 有完整对比分析。
   - Fork 出来的子 Agent 使用**同一个 StateGraph 模板**，通过不同 `thread_id` 做上下文隔离。

2. **LangGraph 作为 Agent 编排框架**
   - `StateGraph` + `add_conditional_edges` 实现 Think→Reflect→Act 循环
   - `Checkpointer` 做短期记忆持久化（开发阶段用内存 checkpointer，生产切 Redis/SQLite）

3. **Think → Reflect → Act 三阶段**
   - **Think**：Planner 拆解需求 + CategoryInsight/ItemSearch 外部搜索 → 获取候选集
   - **Reflect**：ItemPicker 筛选 + PriceCompare 比价 + ShoppingSummary 出清单 → 分析决策
   - **Act**：ShippingCalc 算物流关税 → 执行收尾
   - 三个阶段通过 LangGraph 的条件路由实现，不是硬编码的阶段划分，LLM 根据上下文动态选择。

### 9 大工具

4. **通用工具（3个）**：
   - `Planner`（内部）— 复杂需求拆解为子任务
   - `ChatFallback`（内部）— 非业务意图的闲聊兜底
   - `WebSearch`（外部）— 补充外部客观事实

5. **电商工具（6个）**：
   - `CategoryInsight`（外部）— 品类行业趋势 RAG 查询
   - `ItemSearch`（外部）— 跨平台商品搜索
   - `ItemPicker`（内部）— 按偏好筛选过滤候选集
   - `PriceCompare`（外部）— 跨平台比价
   - `ShippingCalc`（外部）— 关税/物流运费计算
   - `ShoppingSummary`（内部）— 采购清单报告生成

6. 外部工具（调第三方 API）做成 LangChain `BaseTool`，进 `llm.bind_tools()`。内部工具（LLM 自身能力）在 AgentLoop 推理中消化，不暴露为 tool call。

### 技术栈

7. **Python >= 3.11**，asyncio 事件循环（工具调用必须用异步 `httpx`，防止阻塞 AgentLoop）
8. **FastAPI + WebSocket** 做 API 层，HTTP 只启任务（`POST /task` 返回 `thread_id`），WebSocket 推执行过程（`ws://host/ws/{thread_id}`）
9. **AGUI 协议**：6 种标准事件类型（`session_created` / `assistant_call` / `tool_start` / `tool_end` / `task_result` / `error`），前端按事件类型驱动 UI 渲染
10. **LLM 供应商可配置**：通过 `.env` 切换（默认 DeepSeek，支持阿里云百炼、豆包、智谱等 OpenAI 格式的 API）
11. **向量库开发阶段用 ChromaDB**（pip 即用零运维），生产切 Milvus
12. **Embedding 模型优先用 LLM 供应商自带的**（零额外配置成本），备选 BGE-M3（中文效果优）

### 记忆系统

13. **三层记忆**：
    - 工作记忆 → AgentLoop State `messages`（当前会话）
    - 短期记忆 → LangGraph `Checkpointer`（跨请求，会话内）
    - 长期记忆 → `Memory Store`（向量库，跨会话持久化）

14. **记忆内容分类**：用户偏好（"不喜欢入耳式"）→ 事实记忆（"A 款最低价 189"）→ 经验记忆（历史决策模式）→ 会话摘要（过往会话压缩版）

15. **Cache Breakpoint 压缩策略**：不动历史前缀，在前缀末端打断点，前缀冻结永不修改（保 KV Cache 命中率），只压缩断点之后的内容。这是唯一跟厂商 KV Cache 共存的压缩方式。

### 通信与交互

16. **`thread_id` 串联四层**：前端 WebSocket 连接 → 后台任务表 → 会话输出目录 → LangGraph Checkpointer
17. **WebSocket 选型理由**：Agent 场景下用户需要中途干预（取消、改参数），需要全双工的反向通道，SSE 的单向推送不够。文档 `03-AGUI事件与WebSocket推送.md` 有完整对比。
18. **前端 React + Vite**，按 AGUI 事件类型驱动 UI 渲染（思考中 → 工具执行中 → 完成）

### 子 Agent 系统

19. **BaseSubAgent 抽象基类** + **SubAgentRegistry 注册表**：子 Agent 继承 `BaseSubAgent`，实现 `build_graph()`，注册到全局注册表。主 Agent 的 `fork_agent` 工具通过注册表查找并 fork 子 Agent。
20. **Fork 过程**：主 Agent 的 tool_node 识别 `fork_agent` 调用 → 注册表查找子 Agent → 创建独立 `thread_id` → 子 Agent 用自己的图执行 → 结构化结果回传

---

## Testing Decisions

### 测试原则
- **只测外部行为，不测实现细节**。不断言 LLM 被调用了几次、不 mock LangGraph 内部状态；只验证"输入 A → 输出 B"的端到端行为。
- **最上层接缝优先**：能在 `ShoppingSummary` 层面验证的，不在 `ItemSearch` 层面测。
- **现有接缝优先**：优先复用已在代码中体现的抽象边界（工具接口、子 Agent 注册表、API 路由）。

### 测试层级

| 层级 | 范围 | 工具 | 核心验证点 |
|------|------|------|-----------|
| **Seam 1 — 工具函数单元测试** | 6 个电商工具 + 3 个通用工具 | `pytest` + `httpx.MockTransport` | 每个工具在 mock 外部 API 下的入参→出参映射正确性；异常输入（超时、空结果、格式错误）的容错 |
| **Seam 2 — AgentLoop 集成测试** | LangGraph 图编排（agent_node → tool_node → route） | `pytest` + mock LLM 返回固定 `tool_calls` | Think→Reflect→Act 三阶段路由是否正确；Fork 分支是否触发 |
| **Seam 3 — 子 Agent Fork 集成测试** | 主 Agent fork 子 Agent 的完整执行链路 | `pytest` + SubAgentRegistry mock | 注册/查找/执行/结果回传的全流程正确性；不存在的子 Agent 报错 |
| **Seam 4 — API 端点测试** | FastAPI 路由、WebSocket 推送 | `httpx.AsyncClient` + `pytest-asyncio` | `POST /task` 返回 thread_id；WebSocket 按序推送 AGUI 事件；取消任务后停止执行 |
| **Seam 5 — 端到端测试** | 完整用户流程（选品+比价+出清单） | 真实 LLM（低 temperature）+ mock 电商 API | 从自然语言需求到采购清单的完整链路可用性 |

### 关键测试场景

- 工具层：ItemSearch 收到空关键词、PriceCompare 遇到平台无此商品、ShippingCalc 计算关税时目的地国家不支持
- Agent 层：Agent 连续调工具后陷入循环（10 轮以上）→ 应超时终止；Fork 的子 Agent 超时或报错 → 主 Agent 能继续（优雅降级）
- API 层：客户端断连后重连 → 补推缺失事件；同时发多个任务 → thread_id 隔离不冲突

---

## Out of Scope

1. **实际下单购买** — Phase 1 只做选品建议和比价，不接入下单/支付流程。用户拿到采购清单后自行去对应平台下单。
2. **商品评论分析** — 不爬取/分析商品评论的 NLP 情感分析，只关注结构化数据（标题、价格、参数、物流）。
3. **第三方电商平台的 API 对接** — Phase 1 用 mock API 跑通流程，不与真实电商平台签约对接。
4. **用户登录/鉴权系统** — Phase 1 用 `thread_id` 区分会话，不做用户注册/登录/OAuth。
5. **移动端 App** — 只做 Web UI（React + Vite），不做 iOS/Android 原生 App。
6. **自动比价订阅** — 不提供"降价提醒""价格追踪"等定时任务能力。
7. **多语言支持** — Phase 1 只支持中文交互，后续扩展英文/其他语言。

---

## Further Notes

- **设计文档先行**：6 份架构文档（`docs/01~06`）已在 Phase 0 完成，涵盖架构设计、技术栈、AGUI 协议、通用工具、电商工具、记忆系统，是实现的完整依据。
- **Phase 1 目标是可演示的原型**：核心 AgentLoop 能跑通（Think→Reflect→Act 一个完整购物场景），Web UI 能看到实时推送过程，所有外部工具用 mock API 替代真实第三方。
- **LLM 供应商建议先用 DeepSeek**（性价比高），后续切换只需改 `.env` 中的 `LLM_BASE_URL` / `LLM_API_KEY` / `LLM_MODEL` 三行。
- **项目命名**：代码和文档中统一使用 `Glodex Agent`（英文）和 `Glodex 代理`（中文语境）。注意架构文档中有一处不一致（`Globex` vs `Glodex`），以 `Glodex` 为准。
