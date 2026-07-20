"""Priority-ordered Hook pipeline with isolated hook failures."""

from __future__ import annotations

import logging
from collections import defaultdict

from app.harness.types import HookContext, HookFn, HookPoint, HookRejectSignal


logger = logging.getLogger(__name__)


class HarnessPipeline:
    """Runs registered hooks in priority order for one agent instance."""

    def __init__(self) -> None:
        self._hooks: dict[HookPoint, list[tuple[int, str, HookFn]]] = defaultdict(list)

    def register(
        self,
        hook_point: HookPoint,
        name: str,
        fn: HookFn,
        priority: int = 100,
    ) -> None:
        hooks = self._hooks[hook_point]
        hooks.append((priority, name, fn))
        hooks.sort(key=lambda item: item[0])

    async def run(self, hook_point: HookPoint, context: HookContext) -> HookContext:
        """Run all hooks, letting explicit reject signals reach the adapter."""
        for _, name, fn in self._hooks.get(hook_point, []):
            try:
                result = await fn(context)
                if result is not None:
                    context = result
            except HookRejectSignal:
                raise
            except Exception as exc:
                logger.exception("Harness hook %s failed and was skipped: %s", name, exc)
        return context
