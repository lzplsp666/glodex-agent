"""大模型客户端。

使用 LangChain ChatOpenAI 封装，兼容所有 OpenAI 格式的 API。
切模型只改 .env，不动代码。

Usage:
    from app.agent.llm import get_llm, get_llm_info
"""

# import os
# from typing import Optional
# from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI



def get_llm(model=None, base_url=None, api_key=None, temperature=None, max_tokens=None):
    """创建 LLM 客户端实例，返回 ChatOpenAI 对象。

    优先级：传参 > 环境变量 > 默认值

    Args:
        model:       模型名（qwen-plus / deepseek-chat / doubao-1.5-pro ...）
        base_url:    API 地址
        api_key:     API Key
        temperature: 温度 0~1，越大越随机
        max_tokens:  最大输出 token 数

    Returns:
        ChatOpenAI 实例

    实现思路：
        1. load_dotenv() 读 .env
        2. 每个参数：先取传参，None 则取 os.getenv("LLM_XXX")，再 None 则用默认值
        3. temperature / max_tokens 用 is not None 判断（0 是合法值）
        4. 调用 ChatOpenAI(model=..., base_url=..., api_key=..., ...)
    """
    ...


def get_llm_info():
    """查看当前 LLM 配置（不含 API Key，安全）。

    Returns:
        {"model": "deepseek-chat", "base_url": "https://api.deepseek.com", ...}

    实现思路：
        逐项 os.getenv() 取配置，拼成 dict 返回，不包含 api_key
    """
    ...
