# Glodex Agent — AI Agent 配置

你是一个 AI agent，正在开发 **Glodex Agent** — 一个跨平台电商选品与比价多智能体系统。

## 项目概览

Glodex Agent 是一个基于 Python + LangGraph 的多智能体系统：
- **主 AgentLoop + 同质 Fork** 架构
- 9 大工具（Planner、ItemSearch、PriceCompare 等）
- FastAPI + WebSocket 实时推送（AGUI 协议）
- 三层记忆系统（工作记忆/短期记忆/长期记忆）
- Cache Breakpoint 上下文压缩

## Agent skills

### Issue tracker

Issues are tracked on GitHub. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical triage labels, unchanged from the default vocabulary. See `docs/agents/triage-labels.md`.

### Domain docs

- 架构设计：`docs/01-Agent架构设计.md`
- 技术栈：`docs/02-技术栈与依赖清单.md`
- AGUI 协议：`docs/03-AGUI事件与WebSocket推送.md`
- 通用工具：`docs/04-通用工具.md`
- 电商工具：`docs/05-电商工具.md`
- 记忆系统：`docs/06-记忆系统.md`

## Skills 调用方式

本项目安装了 Matt Pocock 的 29 个工程技能（`.agents/skills/`）。在 VSCode 扩展中，技能通过 `Skill({skill:"技能名"})` 调用，不支持 `/技能名` 斜杠命令。

可用技能：tdd, triage, review, qa, to-issues, to-prd, diagnose, improve-codebase-architecture, prototype 等。
