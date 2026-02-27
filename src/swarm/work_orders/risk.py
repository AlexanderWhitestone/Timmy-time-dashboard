"""Risk scoring and auto-execution threshold logic for work orders."""

from swarm.work_orders.models import WorkOrder, WorkOrderCategory, WorkOrderPriority


PRIORITY_WEIGHTS = {
    WorkOrderPriority.CRITICAL: 4,
    WorkOrderPriority.HIGH: 3,
    WorkOrderPriority.MEDIUM: 2,
    WorkOrderPriority.LOW: 1,
}

CATEGORY_WEIGHTS = {
    WorkOrderCategory.BUG: 3,
    WorkOrderCategory.FEATURE: 3,
    WorkOrderCategory.IMPROVEMENT: 2,
    WorkOrderCategory.OPTIMIZATION: 2,
    WorkOrderCategory.SUGGESTION: 1,
}

SENSITIVE_PATHS = [
    "swarm/coordinator",
    "l402",
    "lightning/",
    "config.py",
    "security",
    "auth",
]


def compute_risk_score(wo: WorkOrder) -> int:
    """Compute a risk score for a work order. Higher = riskier.

    Score components:
    - Priority weight: critical=4, high=3, medium=2, low=1
    - Category weight: bug/feature=3, improvement/optimization=2, suggestion=1
    - File sensitivity: +2 per related file in security-sensitive areas
    """
    score = PRIORITY_WEIGHTS.get(wo.priority, 2)
    score += CATEGORY_WEIGHTS.get(wo.category, 1)

    for f in wo.related_files:
        if any(s in f for s in SENSITIVE_PATHS):
            score += 2

    return score


def should_auto_execute(wo: WorkOrder) -> bool:
    """Determine if a work order can auto-execute without human approval.

    Checks:
    1. Global auto-execute must be enabled
    2. Work order priority must be at or below the configured threshold
    3. Total risk score must be <= 3
    """
    from config import settings

    if not settings.work_orders_auto_execute:
        return False

    threshold_map = {"none": 0, "low": 1, "medium": 2, "high": 3}
    max_auto = threshold_map.get(settings.work_orders_auto_threshold, 1)

    priority_values = {
        WorkOrderPriority.LOW: 1,
        WorkOrderPriority.MEDIUM: 2,
        WorkOrderPriority.HIGH: 3,
        WorkOrderPriority.CRITICAL: 4,
    }
    if priority_values.get(wo.priority, 2) > max_auto:
        return False

    return compute_risk_score(wo) <= 3
