"""Declarative registration metadata for Harness hooks."""

from __future__ import annotations

from dataclasses import dataclass

from app.harness.types import HookFn, HookPoint


@dataclass(frozen=True)
class HookRegistration:
    hook_point: HookPoint
    name: str
    priority: int


def harness_hook(
    hook_point: HookPoint,
    *,
    name: str,
    priority: int = 100,
):
    """Mark an async function for registration by ``bootstrap``."""

    def decorator(fn: HookFn) -> HookFn:
        setattr(fn, "__harness_registration__", HookRegistration(hook_point, name, priority))
        return fn

    return decorator
