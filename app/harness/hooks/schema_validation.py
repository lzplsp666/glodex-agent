"""Uniform validation for arguments of all registered LangChain tools."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from app.harness.decorators import harness_hook
from app.harness.types import HookContext, HookPoint, HookRejectSignal


@harness_hook(HookPoint.PRE_TOOL_CALL, name="schema_validation", priority=15)
async def validate_tool_args(context: HookContext) -> None:
    """Validate a tool call with the Tool's existing Pydantic args schema."""
    tool_registry: dict[str, Any] = context.metadata.get("tool_registry", {})
    tool = tool_registry.get(context.tool_name)
    args_schema = getattr(tool, "args_schema", None)

    if args_schema is None or not hasattr(args_schema, "model_validate"):
        raise HookRejectSignal(f"工具 {context.tool_name or 'unknown'} 未提供可校验的参数 Schema。")

    try:
        args_schema.model_validate(context.tool_args)
    except ValidationError as exc:
        raise HookRejectSignal(
            f"工具 {context.tool_name} 参数不合法：{_format_validation_errors(exc)}"
        ) from exc
    return None


def _format_validation_errors(exc: ValidationError) -> str:
    """Return a compact, model-readable summary instead of raw Pydantic output."""
    messages: list[str] = []
    for error in exc.errors()[:3]:
        location = ".".join(str(part) for part in error.get("loc", ())) or "参数"
        messages.append(f"{location}: {error.get('msg', '格式错误')}")
    return "；".join(messages)
