"""Build a complete Harness pipeline from first-party Hook modules."""

from __future__ import annotations

import inspect
from types import ModuleType

from app.harness.decorators import HookRegistration
from app.harness.hooks import memory, schema_validation, tool, tool_result_storage
from app.harness.pipeline import HarnessPipeline


HOOK_MODULES: tuple[ModuleType, ...] = (tool, schema_validation, tool_result_storage, memory)


def build_harness() -> HarnessPipeline:
    """Create one independently stateful pipeline for one agent middleware."""
    pipeline = HarnessPipeline()
    for module in HOOK_MODULES:
        _register_module_hooks(pipeline, module)
    return pipeline


def _register_module_hooks(pipeline: HarnessPipeline, module: ModuleType) -> None:
    for _, fn in inspect.getmembers(module, inspect.iscoroutinefunction):
        registration = getattr(fn, "__harness_registration__", None)
        if not isinstance(registration, HookRegistration):
            continue
        pipeline.register(
            registration.hook_point,
            registration.name,
            fn,
            registration.priority,
        )
