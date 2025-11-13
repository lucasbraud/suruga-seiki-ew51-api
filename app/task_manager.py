"""Task management system for long-running operations.

This module provides a unified task management system for handling asynchronous
long-running operations like angle adjustment, alignment, profiling, and motion.
Only one task can run at a time (enforced by the singleton TaskManager).
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class TaskStatus(str, Enum):
    """Status of a task."""

    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationType(str, Enum):
    """Types of operations that can be executed as tasks."""

    ANGLE_ADJUSTMENT = "angle_adjustment"
    FLAT_ALIGNMENT = "flat_alignment"
    FOCUS_ALIGNMENT = "focus_alignment"
    PROFILE_MEASUREMENT = "profile_measurement"
    AXIS_MOVEMENT = "axis_movement"


@dataclass
class Task:
    """Represents a long-running task.

    Attributes:
        task_id: Unique identifier for the task
        operation_type: Type of operation being performed
        status: Current status of the task
        progress: Flexible dictionary for operation-specific progress data
        result: Result data when task completes successfully
        error: Error message if task fails
        created_at: When the task was created
        started_at: When the task execution started
        completed_at: When the task finished (success, failure, or cancellation)
        cancellation_event: Asyncio event for signaling cancellation
        request_data: Original request data for the operation
    """

    task_id: str
    operation_type: OperationType
    status: TaskStatus = TaskStatus.PENDING
    progress: dict[str, Any] = field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancellation_event: asyncio.Event = field(default_factory=asyncio.Event)
    request_data: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert task to dictionary for API responses."""
        return {
            "task_id": self.task_id,
            "operation_type": self.operation_type.value,
            "status": self.status.value,
            "progress": self.progress,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
        }


class TaskManager:
    """Singleton manager for task state.

    Enforces single-task-at-a-time constraint and provides centralized
    task state management.
    """

    _instance: Optional["TaskManager"] = None
    _current_task: Optional[Task] = None
    _task_history: dict[str, Task] = {}
    _max_history_size: int = 100

    def __new__(cls) -> "TaskManager":
        """Ensure singleton instance."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def create_task(
        self,
        operation_type: OperationType,
        request_data: Optional[dict[str, Any]] = None,
    ) -> Task:
        """Create a new task.

        Args:
            operation_type: Type of operation to perform
            request_data: Optional request data for the operation

        Returns:
            New Task instance

        Raises:
            RuntimeError: If a task is already running
        """
        if self._current_task and self._current_task.status in [
            TaskStatus.PENDING,
            TaskStatus.RUNNING,
            TaskStatus.STOPPING,
        ]:
            raise RuntimeError(
                f"Task {self._current_task.task_id} is already {self._current_task.status.value}. "
                f"Only one task can run at a time."
            )

        task = Task(
            task_id=str(uuid.uuid4()),
            operation_type=operation_type,
            request_data=request_data,
        )

        self._current_task = task
        self._add_to_history(task)

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID.

        Args:
            task_id: Task ID to retrieve

        Returns:
            Task if found, None otherwise
        """
        if self._current_task and self._current_task.task_id == task_id:
            return self._current_task

        return self._task_history.get(task_id)

    def get_current_task(self) -> Optional[Task]:
        """Get the currently active task.

        Returns:
            Current task if one exists, None otherwise
        """
        return self._current_task

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status.

        Args:
            task_id: Task ID to update
            status: New status

        Raises:
            ValueError: If task not found
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = status

        # Update timestamps
        if status == TaskStatus.RUNNING and not task.started_at:
            task.started_at = datetime.utcnow()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            task.completed_at = datetime.utcnow()

    def update_progress(self, task_id: str, progress: dict[str, Any]) -> None:
        """Update task progress data.

        Args:
            task_id: Task ID to update
            progress: Progress data dictionary

        Raises:
            ValueError: If task not found
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.progress.update(progress)

    def complete_task(self, task_id: str, result: dict[str, Any]) -> None:
        """Mark task as completed with result.

        Args:
            task_id: Task ID to complete
            result: Result data

        Raises:
            ValueError: If task not found
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = TaskStatus.COMPLETED
        task.result = result
        task.completed_at = datetime.utcnow()

    def fail_task(self, task_id: str, error: str) -> None:
        """Mark task as failed with error.

        Args:
            task_id: Task ID to fail
            error: Error message

        Raises:
            ValueError: If task not found
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = TaskStatus.FAILED
        task.error = error
        task.completed_at = datetime.utcnow()

    def cancel_task(self, task_id: str) -> None:
        """Cancel a running task.

        Args:
            task_id: Task ID to cancel

        Raises:
            ValueError: If task not found or not in cancellable state
        """
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        if task.status not in [TaskStatus.PENDING, TaskStatus.RUNNING]:
            raise ValueError(
                f"Task {task_id} cannot be cancelled (status: {task.status.value})"
            )

        # Set cancellation event to signal background task
        task.cancellation_event.set()

        # Update status to stopping
        task.status = TaskStatus.STOPPING

    def clear_current_task(self) -> None:
        """Clear the current task reference.

        Should be called after task reaches terminal state.
        """
        if (
            self._current_task
            and self._current_task.status
            in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        ):
            self._current_task = None

    def _add_to_history(self, task: Task) -> None:
        """Add task to history, pruning old tasks if necessary.

        Args:
            task: Task to add to history
        """
        self._task_history[task.task_id] = task

        # Prune old tasks if history is too large
        if len(self._task_history) > self._max_history_size:
            # Remove oldest tasks (by created_at)
            sorted_tasks = sorted(
                self._task_history.values(), key=lambda t: t.created_at
            )
            tasks_to_remove = sorted_tasks[: len(sorted_tasks) - self._max_history_size]

            for old_task in tasks_to_remove:
                if old_task.task_id in self._task_history:
                    del self._task_history[old_task.task_id]

    def get_task_history(
        self, limit: int = 10, operation_type: Optional[OperationType] = None
    ) -> list[Task]:
        """Get recent task history.

        Args:
            limit: Maximum number of tasks to return
            operation_type: Optional filter by operation type

        Returns:
            List of tasks sorted by creation time (most recent first)
        """
        tasks = list(self._task_history.values())

        # Filter by operation type if specified
        if operation_type:
            tasks = [t for t in tasks if t.operation_type == operation_type]

        # Sort by creation time (most recent first)
        tasks.sort(key=lambda t: t.created_at, reverse=True)

        return tasks[:limit]


# Global singleton instance
task_manager = TaskManager()
