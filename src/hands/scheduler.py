"""Hand Scheduler — APScheduler-based cron scheduling for Hands.

Manages the scheduling of autonomous Hands using APScheduler.
Supports cron expressions, intervals, and specific times.

Usage:
    from hands.scheduler import HandScheduler
    from hands.registry import HandRegistry
    
    registry = HandRegistry()
    await registry.load_all()
    
    scheduler = HandScheduler(registry)
    await scheduler.start()
    
    # Hands are now scheduled and will run automatically
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from hands.models import HandConfig, HandState, HandStatus, TriggerType
from hands.registry import HandRegistry
from hands.runner import HandRunner

logger = logging.getLogger(__name__)

# Try to import APScheduler
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    logger.warning("APScheduler not installed. Scheduling will be disabled.")


class HandScheduler:
    """Scheduler for autonomous Hands.
    
    Uses APScheduler to manage cron-based execution of Hands.
    Each Hand with a schedule gets its own job in the scheduler.
    
    Attributes:
        registry: HandRegistry for Hand configurations
        _scheduler: APScheduler instance
        _running: Whether scheduler is running
        _job_ids: Mapping of hand names to job IDs
    """
    
    def __init__(
        self,
        registry: HandRegistry,
        job_defaults: Optional[dict] = None,
    ) -> None:
        """Initialize HandScheduler.
        
        Args:
            registry: HandRegistry instance
            job_defaults: Default job configuration for APScheduler
        """
        self.registry = registry
        self.runner = HandRunner(registry)
        self._scheduler: Optional[Any] = None
        self._running = False
        self._job_ids: dict[str, str] = {}
        
        if APSCHEDULER_AVAILABLE:
            self._scheduler = AsyncIOScheduler(job_defaults=job_defaults or {
                'coalesce': True,  # Coalesce missed jobs into one
                'max_instances': 1,  # Only one instance per Hand
            })
        
        logger.info("HandScheduler initialized")
    
    async def start(self) -> None:
        """Start the scheduler and schedule all enabled Hands."""
        if not APSCHEDULER_AVAILABLE:
            logger.error("Cannot start scheduler: APScheduler not installed")
            return
        
        if self._running:
            logger.warning("Scheduler already running")
            return
        
        # Schedule all enabled Hands
        hands = self.registry.get_scheduled_hands()
        for hand in hands:
            await self.schedule_hand(hand)
        
        # Start the scheduler
        self._scheduler.start()
        self._running = True
        
        logger.info("HandScheduler started with %d scheduled Hands", len(hands))
    
    async def stop(self) -> None:
        """Stop the scheduler."""
        if not self._running or not self._scheduler:
            return
        
        self._scheduler.shutdown(wait=True)
        self._running = False
        self._job_ids.clear()
        
        logger.info("HandScheduler stopped")
    
    async def schedule_hand(self, hand: HandConfig) -> Optional[str]:
        """Schedule a Hand for execution.
        
        Args:
            hand: HandConfig to schedule
            
        Returns:
            Job ID if scheduled successfully
        """
        if not APSCHEDULER_AVAILABLE or not self._scheduler:
            logger.warning("Cannot schedule %s: APScheduler not available", hand.name)
            return None
        
        if not hand.schedule:
            logger.debug("Hand %s has no schedule", hand.name)
            return None
        
        if not hand.enabled:
            logger.debug("Hand %s is disabled", hand.name)
            return None
        
        # Remove existing job if any
        if hand.name in self._job_ids:
            self.unschedule_hand(hand.name)
        
        # Create the trigger
        trigger = self._create_trigger(hand.schedule)
        if not trigger:
            logger.error("Failed to create trigger for Hand %s", hand.name)
            return None
        
        # Add job to scheduler
        try:
            job = self._scheduler.add_job(
                func=self._execute_hand_wrapper,
                trigger=trigger,
                id=f"hand_{hand.name}",
                name=f"Hand: {hand.name}",
                args=[hand.name],
                replace_existing=True,
            )
            
            self._job_ids[hand.name] = job.id
            
            # Update state
            self.registry.update_state(
                hand.name,
                status=HandStatus.SCHEDULED,
                next_run=job.next_run_time,
            )
            
            logger.info("Scheduled Hand %s (next run: %s)", hand.name, job.next_run_time)
            return job.id
            
        except Exception as e:
            logger.error("Failed to schedule Hand %s: %s", hand.name, e)
            return None
    
    def unschedule_hand(self, name: str) -> bool:
        """Remove a Hand from the scheduler.
        
        Args:
            name: Hand name
            
        Returns:
            True if unscheduled successfully
        """
        if not self._scheduler:
            return False
        
        if name not in self._job_ids:
            return False
        
        try:
            self._scheduler.remove_job(self._job_ids[name])
            del self._job_ids[name]
            
            self.registry.update_state(name, status=HandStatus.IDLE)
            
            logger.info("Unscheduled Hand %s", name)
            return True
            
        except Exception as e:
            logger.error("Failed to unschedule Hand %s: %s", name, e)
            return False
    
    def pause_hand(self, name: str) -> bool:
        """Pause a scheduled Hand.
        
        Args:
            name: Hand name
            
        Returns:
            True if paused successfully
        """
        if not self._scheduler:
            return False
        
        if name not in self._job_ids:
            return False
        
        try:
            self._scheduler.pause_job(self._job_ids[name])
            self.registry.update_state(name, status=HandStatus.PAUSED, is_paused=True)
            logger.info("Paused Hand %s", name)
            return True
        except Exception as e:
            logger.error("Failed to pause Hand %s: %s", name, e)
            return False
    
    def resume_hand(self, name: str) -> bool:
        """Resume a paused Hand.
        
        Args:
            name: Hand name
            
        Returns:
            True if resumed successfully
        """
        if not self._scheduler:
            return False
        
        if name not in self._job_ids:
            return False
        
        try:
            self._scheduler.resume_job(self._job_ids[name])
            self.registry.update_state(name, status=HandStatus.SCHEDULED, is_paused=False)
            logger.info("Resumed Hand %s", name)
            return True
        except Exception as e:
            logger.error("Failed to resume Hand %s: %s", name, e)
            return False
    
    def get_scheduled_jobs(self) -> list[dict]:
        """Get all scheduled jobs.
        
        Returns:
            List of job information dicts
        """
        if not self._scheduler:
            return []
        
        jobs = []
        for job in self._scheduler.get_jobs():
            if job.id.startswith("hand_"):
                hand_name = job.id[5:]  # Remove "hand_" prefix
                jobs.append({
                    "hand_name": hand_name,
                    "job_id": job.id,
                    "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                    "trigger": str(job.trigger),
                })
        
        return jobs
    
    def _create_trigger(self, schedule: Any) -> Optional[Any]:
        """Create an APScheduler trigger from ScheduleConfig.
        
        Args:
            schedule: ScheduleConfig
            
        Returns:
            APScheduler trigger
        """
        if not APSCHEDULER_AVAILABLE:
            return None
        
        # Cron trigger
        if schedule.cron:
            try:
                parts = schedule.cron.split()
                if len(parts) == 5:
                    return CronTrigger(
                        minute=parts[0],
                        hour=parts[1],
                        day=parts[2],
                        month=parts[3],
                        day_of_week=parts[4],
                        timezone=schedule.timezone,
                    )
            except Exception as e:
                logger.error("Invalid cron expression '%s': %s", schedule.cron, e)
                return None
        
        # Interval trigger
        if schedule.interval:
            return IntervalTrigger(
                seconds=schedule.interval,
                timezone=schedule.timezone,
            )
        
        return None
    
    async def _execute_hand_wrapper(self, hand_name: str) -> None:
        """Wrapper for Hand execution.
        
        This is called by APScheduler when a Hand's trigger fires.
        
        Args:
            hand_name: Name of the Hand to execute
        """
        logger.info("Triggering Hand: %s", hand_name)
        
        try:
            # Update state
            self.registry.update_state(
                hand_name,
                status=HandStatus.RUNNING,
                last_run=datetime.now(timezone.utc),
            )
            
            # Execute the Hand
            await self._run_hand(hand_name, TriggerType.SCHEDULE)
            
        except Exception as e:
            logger.exception("Hand %s execution failed", hand_name)
            self.registry.update_state(
                hand_name,
                status=HandStatus.ERROR,
                error_message=str(e),
            )
    
    async def _run_hand(self, hand_name: str, trigger: TriggerType) -> None:
        """Execute a Hand.
        
        This is the core execution logic. In Phase 4+, this will
        call the actual Hand implementation.
        
        Args:
            hand_name: Name of the Hand
            trigger: What triggered the execution
        """
        from hands.models import HandOutcome
        
        try:
            hand = self.registry.get_hand(hand_name)
        except Exception:
            logger.error("Hand %s not found", hand_name)
            return
        
        logger.info("Executing Hand %s (trigger: %s)", hand_name, trigger.value)
        
        # Call actual Hand implementation via HandRunner
        outcome, output = await self.runner.run_hand(hand_name, trigger)
        
        # Log execution
        await self.registry.log_execution(
            hand_name=hand_name,
            trigger=trigger.value,
            outcome=outcome.value,
            output=output,
        )
        
        # Update state
        state = self.registry.get_state(hand_name)
        self.registry.update_state(
            hand_name,
            status=HandStatus.SCHEDULED,
            run_count=state.run_count + 1,
            success_count=state.success_count + 1,
        )
        
        logger.info("Hand %s completed successfully", hand_name)
    
    async def trigger_hand_now(self, name: str) -> bool:
        """Manually trigger a Hand to run immediately.
        
        Args:
            name: Hand name
            
        Returns:
            True if triggered successfully
        """
        try:
            await self._run_hand(name, TriggerType.MANUAL)
            return True
        except Exception as e:
            logger.error("Failed to trigger Hand %s: %s", name, e)
            return False
    
    def get_next_run_time(self, name: str) -> Optional[datetime]:
        """Get next scheduled run time for a Hand.
        
        Args:
            name: Hand name
            
        Returns:
            Next run time or None if not scheduled
        """
        if not self._scheduler or name not in self._job_ids:
            return None
        
        try:
            job = self._scheduler.get_job(self._job_ids[name])
            return job.next_run_time if job else None
        except Exception:
            return None
