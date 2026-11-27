#!/usr/bin/env python3
"""
AI-Driven Task Planner for ALICE.

This is the PRIMARY planner. It uses LLM-driven planning with fallback to
the legacy pattern-based planner when AI planning is unavailable.
"""

from __future__ import annotations

import logging
import warnings
from typing import Any, Dict, List, Optional

from alice.planner.ai_planner import (
    AIPlanner,
    PlanStep,
    GeneratedPlan,
    create_ai_planner_from_app,
)
from alice.planner.legacy_planner import (
    TaskStep,
    TaskPlanner as LegacyTaskPlanner,
)

logger = logging.getLogger(__name__)

# Export the main planner class
__all__ = ["TaskPlanner", "PlanStep", "GeneratedPlan", "AIPlanner", "create_ai_planner_from_app"]


# Alias for backwards compatibility
TaskStep = TaskStep


class TaskPlanner:
    """
    AI-driven task planner with fallback to pattern-based planning.

    This class wraps the AIPlanner as primary, falling back to the
    legacy TaskPlanner when AI planning is unavailable or fails.
    """

    def __init__(
        self,
        tool_registry: Optional[Dict[str, Any]] = None,
        model_adapter: Optional[Any] = None,
        context_manager: Optional[Any] = None,
        use_ai_planning: bool = True,
        fallback_to_legacy: bool = True,
    ):
        """
        Initialize the TaskPlanner.

        Args:
            tool_registry: Dictionary of available tools
            model_adapter: The model adapter for AI planning
            context_manager: Context manager for token budget
            use_ai_planning: Whether to use AI-driven planning (default True)
            fallback_to_legacy: Whether to fall back to legacy on failure
        """
        self.tool_registry = tool_registry or {}
        self.model_adapter = model_adapter
        self.context_manager = context_manager
        self.use_ai_planning = use_ai_planning
        self.fallback_to_legacy = fallback_to_legacy

        # Initialize AI planner if available
        self.ai_planner = None
        if use_ai_planning and model_adapter:
            self.ai_planner = AIPlanner(
                tool_registry=tool_registry,
                model_adapter=model_adapter,
                context_manager=context_manager,
            )
            logger.debug("AI Planner initialized")

        # Initialize legacy planner for fallback
        self.legacy_planner = LegacyTaskPlanner(tool_registry)

        # Track which planner was last used
        self._last_used = "legacy"

    def plan(self, user_intent: str) -> List[TaskStep]:
        """
        Generate a plan for the user intent.

        Uses AI planning as primary, with legacy fallback.

        Args:
            user_intent: Natural language request from user

        Returns:
            List of TaskStep objects to execute
        """
        # Try AI planning first if enabled and available
        if self.use_ai_planning and self.ai_planner is not None:
            try:
                ai_steps = self.ai_planner.plan(user_intent)
                if ai_steps:
                    self._last_used = "ai"
                    # Convert AI PlanStep to Legacy TaskStep
                    return self._convert_ai_steps(ai_steps)
            except Exception as e:
                logger.warning(f"AI planning failed: {e}")

        # Fall back to legacy planner (always available)
        self._last_used = "legacy"
        return self.legacy_planner.plan(user_intent)

    def _convert_ai_steps(self, ai_steps: List[Any]) -> List[TaskStep]:
        """Convert AI PlanStep objects to Legacy TaskStep objects."""
        legacy_steps = []

        for step in ai_steps:
            # Handle both PlanStep and dict formats
            if hasattr(step, "tool_name"):
                tool_name = step.tool_name
                parameters = getattr(step, "parameters", {}) or {}
                description = getattr(step, "thought", f"Execute {tool_name}")
                requires_confirm = False
            elif isinstance(step, dict):
                tool_name = step.get("tool_name", "")
                parameters = step.get("parameters", {}) or {}
                description = step.get("thought", f"Execute {tool_name}")
                requires_confirm = step.get("requires_confirmation", False)
            else:
                continue

            if not tool_name:
                continue

            step_id = len(legacy_steps) + 1
            legacy_step = TaskStep(
                step_id=step_id,
                description=description,
                tool_name=tool_name,
                parameters=parameters,
                requires_confirmation=requires_confirm,
            )
            legacy_steps.append(legacy_step)

        return legacy_steps

    def execute_steps(self, tool_executor) -> List[TaskStep]:
        """Execute all planned steps sequentially."""
        results = []
        for step in self.steps if hasattr(self, "steps") else self.plan_steps:
            if isinstance(step, dict):
                # Reconstruct TaskStep from dict for legacy format
                step = TaskStep(**step)

            logger.info(f"Executing step {step.step_id}: {step.description}")
            success = step.execute(tool_executor)

            if success:
                success = step.verify()
                if not success:
                    logger.warning(f"Step {step.step_id} verification failed")
            else:
                logger.error(f"Step {step.step_id} execution failed: {step.error}")

            results.append(step)
        return results

    def get_plan_summary(self) -> str:
        """Get a summary of the current plan."""
        if not hasattr(self, "steps") or not self.steps:
            if self._last_used == "ai" and self.ai_planner:
                # Return AI plan summary if available
                return "AI-generated plan pending"
            return "No plan available."

        summary = f"Plan with {len(self.steps)} step(s):\n"
        for step in self.steps:
            summary += f"  {step.step_id}. {step.description}\n"
        return summary

    @property
    def plan_steps(self) -> List[TaskStep]:
        """Get the current plan steps (compatibility property)."""
        if hasattr(self, "_steps") and self._steps:
            return self._steps
        return []

    def set_plan(self, steps: List[TaskStep]) -> None:
        """Set the current plan steps."""
        self._steps = steps

    def get_last_planner_used(self) -> str:
        """Get which planner was used for the last plan."""
        return self._last_used

    def is_ai_planning_enabled(self) -> bool:
        """Check if AI planning is enabled and available."""
        return self.use_ai_planning and self.ai_planner is not None


# Module-level convenience function
def plan_task(
    user_intent: str,
    tool_registry: Optional[Dict[str, Any]] = None,
    model_adapter: Optional[Any] = None,
) -> List[TaskStep]:
    """Quick function to plan a task with default settings."""
    planner = TaskPlanner(
        tool_registry=tool_registry,
        model_adapter=model_adapter,
    )
    return planner.plan(user_intent)