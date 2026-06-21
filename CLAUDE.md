# Glodex Agent

跨平台电商选品与比价 Agent，基于 LLM 驱动，具备规划、记忆、工具调用四大核心模块。

> 本项目使用 AGENTS.md 作为主要 AI agent 配置，VSCode AI 扩展会优先读取 AGENTS.md。

## 项目结构

```
app/
├── agent/            # AgentLoop 主体 + 子 Agent + 提示词 + LLM 初始化
│   ├── sub_agents/   # 跨平台、品类洞察等子 Agent
│   ├── llm.py        # 大模型初始化
│   ├── main_agent.py # 主循环：run_agent 执行入口
│   └── prompts.py    # 提示词配置
├── api/              # FastAPI 接口层
│   ├── server.py     # 路由入口
│   ├── context.py    # ContextVar（thread_id / session_dir）
│   └── monitor.py    # AGUI 事件统一封装
├── tools/            # 九大工具：Planner / ItemSearch / PriceCompare ...
├── recall/           # LLM 三塔向量召回客户端
├── memory/           # 长期记忆 Store 封装
├── compress/         # Cache Breakpoint 上下文压缩策略
├── eval/             # Rubric 评测体系与训练数据采集
└── output/           # 每个会话生成的清单 / 报告
```

## 四大核心模块

| 模块 | 位置 | 职责 |
|------|------|------|
| 大模型 | `app/agent/llm.py` | 模型初始化、调用封装 |
| 记忆 | `app/memory/` + `app/recall/` + `app/compress/` | 长期记忆存储、向量召回检索、上下文压缩 |
| 工具 | `app/tools/` | 九大工具实现（Planner、ItemSearch、PriceCompare 等） |
| Agent 调度 | `app/agent/` | AgentLoop 主循环、子 Agent 编排、提示词管理 |

## 技术栈

- Python >= 3.11
- FastAPI（接口）
- React + Vite（前端）
- Docker Compose（向量库、Redis 本地服务）

## 开发

```bash
pip install -r requirements.txt
# 启动后端
uvicorn app.api.server:app --reload
# 启动前端
cd frontend && npm run dev
```
