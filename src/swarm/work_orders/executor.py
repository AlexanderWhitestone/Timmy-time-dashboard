"""Work order execution — bridges work orders to self-modify and swarm."""

import logging

from swarm.work_orders.models import WorkOrder, WorkOrderCategory

logger = logging.getLogger(__name__)


class WorkOrderExecutor:
    """Dispatches approved work orders to the appropriate execution backend."""

    def execute(self, wo: WorkOrder) -> tuple[bool, str]:
        """Execute a work order.

        Returns:
            (success, result_message) tuple
        """
        if self._is_code_task(wo):
            return self._execute_via_swarm(wo, code_hint=True)
        return self._execute_via_swarm(wo)

    def _is_code_task(self, wo: WorkOrder) -> bool:
        """Check if this work order involves code changes."""
        code_categories = {WorkOrderCategory.BUG, WorkOrderCategory.OPTIMIZATION}
        if wo.category in code_categories:
            return True
        if wo.related_files:
            return any(f.endswith(".py") for f in wo.related_files)
        return False

    def _execute_via_swarm(self, wo: WorkOrder, code_hint: bool = False) -> tuple[bool, str]:
        """Dispatch as a swarm task for agent bidding."""
        try:
            from swarm.coordinator import coordinator
            prefix = "[Code] " if code_hint else ""
            description = f"{prefix}[WO-{wo.id[:8]}] {wo.title}"
            if wo.description:
                description += f": {wo.description}"
            task = coordinator.post_task(description)
            logger.info("Work order %s dispatched as swarm task %s", wo.id[:8], task.id)
            return True, f"Dispatched as swarm task {task.id}"
        except Exception as exc:
            logger.error("Failed to dispatch work order %s: %s", wo.id[:8], exc)
            return False, str(exc)


# Module-level singleton
work_order_executor = WorkOrderExecutor()
