# Globex Agent 架构设计

## 一、我们的架构：主 AgentLoop + 同质 Fork

### 1.1 核心思想

一个主 AgentLoop 拥有全部工具能力。当任务复杂时，主 Agent **fork 出自己的克隆体**（同样的 9 个工具），给每个克隆体分配一个子目标，各自独立执行，结果回传给主 Agent。

### 1.2 架构图

```mermaid
graph TD
    User[用户] -->|购物需求| MainLoop[主 AgentLoop]

    MainLoop -->|持有| Tools[9 大工具集]
    Tools --> T1[Planner]
    Tools --> T2[ItemSearch]
    Tools --> T3[PriceCompare]
    Tools --> T4[ShoppingSummary]
    Tools --> T5[...]

    MainLoop -->|Think 决策| Decision{自己干 or Fork?}

    Decision -->|自己干| DirectCall[直接调工具]
    DirectCall --> MainLoop

    Decision -->|子目标独立/并行| Fork1[Fork 子Agent A]
    Decision -->|子目标独立/并行| Fork2[Fork 子Agent B]
    Decision -->|子目标独立/并行| Fork3[Fork 子Agent C]

    Fork1 --> SubA[同质子 Agent A]
    Fork2 --> SubB[同质子 Agent B]
    Fork3 --> SubC[同质子 Agent C]

    SubA -->|持有| Tools
    SubB -->|持有| Tools
    SubC -->|持有| Tools

    SubA -->|结构化结果| MainLoop
    SubB -->|结构化结果| MainLoop
    SubC -->|结构化结果| MainLoop

    MainLoop -->|最终输出| Summary[ShoppingSummary]
    Summary --> User
```

### 1.3 时序

```mermaid
sequenceDiagram
    participant U as 用户
    participant M as 主 AgentLoop
    participant T as 工具集
    participant S1 as 子Agent A
    participant S2 as 子Agent B

    U->>M: "蓝牙耳机 预算200 金属 商务风"

    Note over M: Think 第1轮
    M->>T: Planner → 拆解子目标
    T-->>M: 目标: 品类/预算/材质/风格

    M->>T: ItemSearch("蓝牙耳机")
    T-->>M: 50个候选商品

    Note over M: 预算/材质/风格 互相独立<br/>→ Fork 出去并行干

    par 并行执行
        M->>S1: Fork(子目标: 预算≤200, 候选集)
        S1->>S1: 自己 Think → 调工具筛选
        S1-->>M: 15个候选
    and
        M->>S2: Fork(子目标: 金属材质, 候选集)
        S2->>S2: 自己 Think → 调工具筛选
        S2-->>M: 8个候选
    end

    Note over M: Think 第2轮
    M->>T: 取交集 → 3个候选
    M->>T: PriceCompare(3个候选)
    T-->>M: 比价结果

    M->>U: ShoppingSummary 报告
```

### 1.4 用 LangGraph 怎么做

```mermaid
flowchart TB
    subgraph LangGraph实现
        direction TB

        Build[构建阶段]
        Build --> B1[定义 AgentState<br/>messages + context]
        B1 --> B2[创建 StateGraph]
        B2 --> B3[添加 agent_node:<br/>LLM + bind_tools]
        B3 --> B4[添加 tool_node:<br/>含 fork_agent 工具]
        B4 --> B5[添加 route 条件边]
        B5 --> B6[compile 编译]

        Run[运行阶段]
        Run --> R1[graph.invoke 主循环]
        R1 --> R2[agent_node Think]
        R2 --> R3{route 判断}
        R3 -->|tool_calls| R4[tool_node]
        R3 -->|无| R5[END]

        R4 --> R6{工具类型?}
        R6 -->|普通工具| R7[直接 invoke]
        R6 -->|fork_agent| R8[创建子图实例]

        R7 --> R2
        R8 --> R9[子 Agent 独立 graph.invoke]
        R9 --> R10[回传结构化结果]
        R10 --> R2
    end
```

**实现要点**：

| 概念 | LangGraph 对应 |
|------|---------------|
| 主 AgentLoop | 一个编译好的 `StateGraph` 实例 |
| agent_node | `llm.bind_tools(tools).invoke(messages)` |
| tool_node | 遍历 tool_calls，分发执行 |
| route | `hasattr(last_msg, "tool_calls")` 判断 |
| fork_agent | tool_node 中注册的特殊工具 |
| 同质子 Agent | **同一个 StateGraph 模板**，用不同 `thread_id` 创建独立实例 |
| 上下文隔离 | 不同 thread_id → 不同的 checkpointer 存储空间 |
| 结构化回传 | 子 Agent 的最终 `state.values["messages"]` 返回给主 Agent |

**伪代码**：

```
class GlobexAgent:
    _build():
        # 1. 定义一个 StateGraph 模板（这是主 Agent 和图 Agent 共用的）
        graph = StateGraph(AgentState)
            .add_node("agent", self._agent_node)
            .add_node("tools", self._tool_node)
            .add_edge("tools", "agent")
            .add_conditional_edges("agent", self._route)
            .compile()

    fork(task, context):
        # 2. Fork = 用同一个模板建子实例
        sub_agent_config = {"thread_id": new_unique_id()}
        sub_state = {"messages": [HumanMessage(task)], "context": context}
        return self.graph.invoke(sub_state, sub_agent_config)
```

---

## 二、另一种模式：Supervisor-Worker

### 2.1 核心思想

一个 Supervisor 管理多个**异构** Worker。每个 Worker 是不同领域的专家（不同工具、不同提示词）。Supervisor 不干活，只负责判断"这个任务该分给哪个 Worker"，然后路由过去。

### 2.2 架构图

```mermaid
graph TD
    User[用户] --> Supervisor[Supervisor<br/>路由 Agent]

    Supervisor -->|分类路由| Router{任务类型?}

    Router -->|搜索类| AmazonW[Amazon Worker<br/>只搜 Amazon]
    Router -->|搜索类| EbayW[eBay Worker<br/>只搜 eBay]
    Router -->|比价类| PriceW[Price Worker<br/>只做比价]
    Router -->|报告类| ReportW[Report Worker<br/>只写报告]

    AmazonW -->|持有| ATools[Amazon API 工具]
    EbayW -->|持有| ETools[eBay API 工具]
    PriceW -->|持有| PTools[比价工具]
    ReportW -->|持有| RTools[报告工具]

    AmazonW -->|结果| Supervisor
    EbayW -->|结果| Supervisor
    PriceW -->|结果| Supervisor
    ReportW -->|结果| Supervisor

    Supervisor -->|汇总| User
```

### 2.3 时序

```mermaid
sequenceDiagram
    participant U as 用户
    participant S as Supervisor
    participant W1 as Amazon Worker
    participant W2 as eBay Worker
    participant W3 as Price Worker
    participant W4 as Report Worker

    U->>S: "帮我找蓝牙耳机"

    Note over S: 判断: 这是搜索任务 → 路由给搜索 Worker

    S->>W1: 去 Amazon 搜
    S->>W2: 去 eBay 搜

    W1-->>S: Amazon 结果
    W2-->>S: eBay 结果

    Note over S: 判断: 有结果了，需要比价 → 路由给比价 Worker

    S->>W3: 对比这两组结果
    W3-->>S: 比价结果

    Note over S: 判断: 需要出报告 → 路由给报告 Worker

    S->>W4: 写报告
    W4-->>S: 报告

    S->>U: 最终输出
```

### 2.4 用 LangGraph 怎么做

LangGraph 官方提供了 `create_supervisor()` 来实现这个模式：

```mermaid
flowchart TB
    subgraph LangGraph Supervisor实现
        direction TB

        subgraph Workers[异构 Worker 定义]
            W_A[AmazonWorker<br/>不同的工具集<br/>不同的提示词<br/>不同的 StateGraph]
            W_B[eBayWorker<br/>不同的工具集<br/>不同的提示词<br/>不同的 StateGraph]
            W_C[PriceWorker<br/>不同的工具集<br/>不同的提示词<br/>不同的 StateGraph]
        end

        Sup[Supervisor Agent<br/>LLM 无工具<br/>只做路由决策]

        Sup -->|"next: amazon"| W_A
        Sup -->|"next: ebay"| W_B
        Sup -->|"next: price"| W_C

        W_A --> Sup
        W_B --> Sup
        W_C --> Sup
    end
```

**实现要点**：

| 概念 | LangGraph 对应 |
|------|---------------|
| Supervisor | 一个没有工具的 LLM Agent，输出 `{next: "worker_name"}` |
| Worker | 多个**不同的** `StateGraph`，各有各的工具和提示词 |
| 路由 | Supervisor 的 conditional edge 按 `next` 值分发 |
| 结束 | Worker 任务完成 → 回归 Supervisor → 继续或 FINISH |
| 共享状态 | 所有 Worker 共用同一个 State，共享 messages |

---

## 三、对比

### 3.1 一图对比

```mermaid
graph LR
    subgraph 我们的架构
        M1[主 AgentLoop<br/>全部工具] -->|fork| S1[同质子Agent<br/>全部工具]
        M1 -->|fork| S2[同质子Agent<br/>全部工具]
        M1 -->|自己干| T1[调工具]

        style M1 fill:#4a9,stroke:#333
        style S1 fill:#4a9,stroke:#333,stroke-dasharray: 5 5
        style S2 fill:#4a9,stroke:#333,stroke-dasharray: 5 5
    end

    subgraph Supervisor-Worker
        Sup[Supervisor<br/>无工具] -->|路由| W1[Amazon Worker<br/>Amazon工具]
        Sup -->|路由| W2[eBay Worker<br/>eBay工具]
        Sup -->|路由| W3[Price Worker<br/>比价工具]

        style Sup fill:#f90,stroke:#333
        style W1 fill:#f90,stroke:#333
        style W2 fill:#f90,stroke:#333
        style W3 fill:#f90,stroke:#333
    end
```

### 3.2 优缺点

| 维度 | 主 AgentLoop + 同质 Fork（我们） | Supervisor-Worker |
|------|------|------|
| **子 Agent 定义** | 一个模板，零额外定义 | N 个 Worker，每个要定义工具+提示词+图 |
| **扩展成本** | 新场景 = 新的子目标描述 | 新场景 = 新 Worker 类 |
| **主节点角色** | 自己干活 + 决策 + 汇总 | 只路由，不干活 |
| **工具复用** | 天然复用，所有实例共享工具集 | 工具分散在各 Worker，可能重复 |
| **上下文管理** | 线程级隔离，每个实例独立 | 共享 State，上下文容易互相污染 |
| **并行能力** | Fork 即并行 | Supervisor 串行分发（一轮只能交给一个 Worker） |
| **适用场景** | 子目标**同构**（都是购物搜索的不同维度） | 子任务**异构**（搜索 vs 比价 vs 写报告，工具完全不同） |
| **实现复杂度** | 低 — 一个图模板搞定 | 高 — N 个图 + 路由逻辑 |
| **灵活性** | 高 — 主 Agent 动态决定 fork 几个 | 低 — Worker 种类和路由规则写死 |

### 3.3 为什么我们选同质 Fork

Globex Agent 的购物场景中：

- 品类筛选、预算筛选、材质筛选、风格筛选 — **本质上都是"给候选集加约束条件"**，用的是同一套工具（ItemSearch + 过滤逻辑）
- 子目标之间互不依赖，天然适合并行
- 不需要为 Amazon 写一个 Worker、为 eBay 再写一个 — ItemSearch 工具本身就屏蔽了平台差异
- 主 Agent 需要保持全局视野来出最终报告，不能只当路由器

**总结：任务统一 → Agent 统一。用 Fork 提供隔离和并行，而不是定义不同的 Agent 类型。**
