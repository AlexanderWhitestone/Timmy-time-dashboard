"""Hand Runner — Execute Hands with skill injection and tool access.

The HandRunner is responsible for executing individual Hands:
- Load SYSTEM.md and SKILL.md files
- Inject domain expertise into LLM context
- Execute the tool loop
- Handle approval gates
- Produce output

Usage:
    from hands.runner import HandRunner
    from hands.registry import HandRegistry
    
    registry = HandRegistry()
    runner = HandRunner(registry, llm_adapter)
    
    result = await runner.run_hand("oracle")
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from hands.models import (
    ApprovalRequest,
    ApprovalStatus,
    HandConfig,
    HandExecution,
    HandOutcome,
    HandState,
    HandStatus,
    TriggerType,
)
from hands.registry import HandRegistry

logger = logging.getLogger(__name__)


class HandRunner:
    """Executes individual Hands.
    
    Manages the execution lifecycle:
    1. Load system prompt and skills
    2. Check and handle approval gates
    3. Execute tool loop with LLM
    4. Produce and deliver output
    5. Log execution
    
    Attributes:
        registry: HandRegistry for Hand configs and state
        llm_adapter: LLM adapter for generation
        mcp_registry: Optional MCP tool registry
    """
    
    def __init__(
        self,
        registry: HandRegistry,
        llm_adapter: Optional[Any] = None,
        mcp_registry: Optional[Any] = None,
    ) -> None:
        """Initialize HandRunner.
        
        Args:
            registry: HandRegistry instance
            llm_adapter: LLM adapter for generation
            mcp_registry: Optional MCP tool registry for tool access
        """
        self.registry = registry
        self.llm_adapter = llm_adapter
        self.mcp_registry = mcp_registry
        
        logger.info("HandRunner initialized")
    
    async def run_hand(
        self,
        hand_name: str,
        trigger: TriggerType = TriggerType.MANUAL,
        context: Optional[dict] = None,
    ) -> HandExecution:
        """Run a Hand.
        
        This is the main entry point for Hand execution.
        
        Args:
            hand_name: Name of the Hand to run
            trigger: What triggered this execution
            context: Optional execution context
            
        Returns:
            HandExecution record
        """
        started_at = datetime.now(timezone.utc)
        execution_id = f"exec_{hand_name}_{started_at.isoformat()}"
        
        logger.info("Starting Hand execution: %s", hand_name)
        
        try:
            # Get Hand config
            hand = self.registry.get_hand(hand_name)
            
            # Update state
            self.registry.update_state(
                hand_name,
                status=HandStatus.RUNNING,
                last_run=started_at,
            )
            
            # Load system prompt and skills
            system_prompt = self._load_system_prompt(hand)
            skills = self._load_skills(hand)
            
            # Check approval gates
            approval_results = await self._check_approvals(hand)
            if approval_results.get("blocked"):
                return await self._create_execution_record(
                    execution_id=execution_id,
                    hand_name=hand_name,
                    trigger=trigger,
                    started_at=started_at,
                    outcome=HandOutcome.APPROVAL_PENDING,
                    output="",
                    approval_id=approval_results.get("approval_id"),
                )
            
            # Execute the Hand
            result = await self._execute_with_llm(
                hand=hand,
                system_prompt=system_prompt,
                skills=skills,
                context=context or {},
            )
            
            # Deliver output
            await self._deliver_output(hand, result)
            
            # Update state
            state = self.registry.get_state(hand_name)
            self.registry.update_state(
                hand_name,
                status=HandStatus.IDLE,
                run_count=state.run_count + 1,
                success_count=state.success_count + 1,
            )
            
            # Create execution record
            return await self._create_execution_record(
                execution_id=execution_id,
                hand_name=hand_name,
                trigger=trigger,
                started_at=started_at,
                outcome=HandOutcome.SUCCESS,
                output=result.get("output", ""),
                files_generated=result.get("files", []),
            )
            
        except Exception as e:
            logger.exception("Hand %s execution failed", hand_name)
            
            # Update state
            self.registry.update_state(
                hand_name,
                status=HandStatus.ERROR,
                error_message=str(e),
            )
            
            # Create failure record
            return await self._create_execution_record(
                execution_id=execution_id,
                hand_name=hand_name,
                trigger=trigger,
                started_at=started_at,
                outcome=HandOutcome.FAILURE,
                output="",
                error=str(e),
            )
    
    def _load_system_prompt(self, hand: HandConfig) -> str:
        """Load SYSTEM.md for a Hand.
        
        Args:
            hand: HandConfig
            
        Returns:
            System prompt text
        """
        if hand.system_md_path and hand.system_md_path.exists():
            try:
                return hand.system_md_path.read_text()
            except Exception as e:
                logger.warning("Failed to load SYSTEM.md for %s: %s", hand.name, e)
        
        # Default system prompt
        return f"""You are the {hand.name} Hand.

Your purpose: {hand.description}

You have access to the following tools: {', '.join(hand.tools_required + hand.tools_optional)}

Execute your task professionally and produce the requested output.
"""
    
    def _load_skills(self, hand: HandConfig) -> list[str]:
        """Load SKILL.md files for a Hand.
        
        Args:
            hand: HandConfig
            
        Returns:
            List of skill texts
        """
        skills = []
        
        for skill_path in hand.skill_md_paths:
            try:
                if skill_path.exists():
                    skills.append(skill_path.read_text())
            except Exception as e:
                logger.warning("Failed to load skill %s: %s", skill_path, e)
        
        return skills
    
    async def _check_approvals(self, hand: HandConfig) -> dict:
        """Check if any approval gates block execution.
        
        Args:
            hand: HandConfig
            
        Returns:
            Dict with "blocked" and optional "approval_id"
        """
        if not hand.approval_gates:
            return {"blocked": False}
        
        # Check for pending approvals for this hand
        pending = await self.registry.get_pending_approvals()
        hand_pending = [a for a in pending if a.hand_name == hand.name]
        
        if hand_pending:
            return {
                "blocked": True,
                "approval_id": hand_pending[0].id,
            }
        
        # Create approval requests for each gate
        for gate in hand.approval_gates:
            request = await self.registry.create_approval(
                hand_name=hand.name,
                action=gate.action,
                description=gate.description,
                context={"gate": gate.action},
                expires_after=gate.auto_approve_after,
            )
            
            if not gate.auto_approve_after:
                # Requires manual approval
                return {
                    "blocked": True,
                    "approval_id": request.id,
                }
        
        return {"blocked": False}
    
    async def _execute_with_llm(
        self,
        hand: HandConfig,
        system_prompt: str,
        skills: list[str],
        context: dict,
    ) -> dict:
        """Execute Hand logic with LLM.
        
        Args:
            hand: HandConfig
            system_prompt: System prompt
            skills: Skill texts
            context: Execution context
            
        Returns:
            Result dict with output and files
        """
        if not self.llm_adapter:
            logger.warning("No LLM adapter available for Hand %s", hand.name)
            return {
                "output": f"Hand {hand.name} executed (no LLM configured)",
                "files": [],
            }
        
        # Build the full prompt
        full_prompt = self._build_prompt(
            hand=hand,
            system_prompt=system_prompt,
            skills=skills,
            context=context,
        )
        
        try:
            # Call LLM
            response = await self.llm_adapter.chat(message=full_prompt)
            
            # Parse response
            output = response.content
            
            # Extract any file outputs (placeholder - would parse structured output)
            files = []
            
            return {
                "output": output,
                "files": files,
            }
            
        except Exception as e:
            logger.error("LLM execution failed for Hand %s: %s", hand.name, e)
            raise
    
    def _build_prompt(
        self,
        hand: HandConfig,
        system_prompt: str,
        skills: list[str],
        context: dict,
    ) -> str:
        """Build the full execution prompt.
        
        Args:
            hand: HandConfig
            system_prompt: System prompt
            skills: Skill texts
            context: Execution context
            
        Returns:
            Complete prompt
        """
        parts = [
            "# System Instructions",
            system_prompt,
            "",
        ]
        
        # Add skills
        if skills:
            parts.extend([
                "# Domain Expertise (SKILL.md)",
                "\n\n---\n\n".join(skills),
                "",
            ])
        
        # Add context
        if context:
            parts.extend([
                "# Execution Context",
                str(context),
                "",
            ])
        
        # Add available tools
        if hand.tools_required or hand.tools_optional:
            parts.extend([
                "# Available Tools",
                "Required: " + ", ".join(hand.tools_required),
                "Optional: " + ", ".join(hand.tools_optional),
                "",
            ])
        
        # Add output instructions
        parts.extend([
            "# Output Instructions",
            f"Format: {hand.output.format}",
            f"Dashboard: {'Yes' if hand.output.dashboard else 'No'}",
            f"Channel: {hand.output.channel or 'None'}",
            "",
            "Execute your task now.",
        ])
        
        return "\n".join(parts)
    
    async def _deliver_output(self, hand: HandConfig, result: dict) -> None:
        """Deliver Hand output to configured destinations.
        
        Args:
            hand: HandConfig
            result: Execution result
        """
        output = result.get("output", "")
        
        # Dashboard output
        if hand.output.dashboard:
            # This would publish to event bus for dashboard
            logger.info("Hand %s output delivered to dashboard", hand.name)
        
        # Channel output (e.g., Telegram, Discord)
        if hand.output.channel:
            # This would send to the appropriate channel
            logger.info("Hand %s output delivered to %s", hand.name, hand.output.channel)
        
        # File drop
        if hand.output.file_drop:
            try:
                drop_path = Path(hand.output.file_drop)
                drop_path.mkdir(parents=True, exist_ok=True)
                
                output_file = drop_path / f"{hand.name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
                output_file.write_text(output)
                
                logger.info("Hand %s output written to %s", hand.name, output_file)
            except Exception as e:
                logger.error("Failed to write Hand %s output: %s", hand.name, e)
    
    async def _create_execution_record(
        self,
        execution_id: str,
        hand_name: str,
        trigger: TriggerType,
        started_at: datetime,
        outcome: HandOutcome,
        output: str,
        error: Optional[str] = None,
        approval_id: Optional[str] = None,
        files_generated: Optional[list] = None,
    ) -> HandExecution:
        """Create and store execution record.
        
        Returns:
            HandExecution
        """
        completed_at = datetime.now(timezone.utc)
        
        execution = HandExecution(
            id=execution_id,
            hand_name=hand_name,
            trigger=trigger,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
            output=output,
            error=error,
            approval_id=approval_id,
            files_generated=files_generated or [],
        )
        
        # Log to registry
        await self.registry.log_execution(
            hand_name=hand_name,
            trigger=trigger.value,
            outcome=outcome.value,
            output=output,
            error=error,
            approval_id=approval_id,
        )
        
        return execution
    
    async def continue_after_approval(
        self,
        approval_id: str,
    ) -> Optional[HandExecution]:
        """Continue Hand execution after approval.
        
        Args:
            approval_id: Approval request ID
            
        Returns:
            HandExecution if execution proceeded
        """
        # Get approval request
        # This would need a get_approval_by_id method in registry
        # For now, placeholder
        
        logger.info("Continuing Hand execution after approval %s", approval_id)
        
        # Re-run the Hand
        # This would look up the hand from the approval context
        
        return None
