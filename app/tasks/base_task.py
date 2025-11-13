"""Base task executor for long-running operations.

This module provides an abstract base class for task executors that handle
long-running operations with progress tracking, cancellation support, and
WebSocket broadcasting.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from app.task_manager import Task, TaskManager, TaskStatus

logger = logging.getLogger(__name__)


class OperationCancelledException(Exception):
    """Raised when an operation is cancelled by user request."""

    pass


class BaseTaskExecutor(ABC):
    """Abstract base class for task executors.

    Provides common functionality for:
    - Task lifecycle management
    - Progress broadcasting via WebSocket
    - Cancellation checking
    - Error handling
    """

    def __init__(
        self,
        task_manager: TaskManager,
        broadcast_callback: Optional[Callable[[dict], asyncio.Future]] = None,
    ):
        """Initialize the executor.

        Args:
            task_manager: TaskManager instance for state management
            broadcast_callback: Optional callback for broadcasting WebSocket messages
        """
        self.task_manager = task_manager
        self.broadcast_callback = broadcast_callback

    @abstractmethod
    async def execute_operation(
        self, task: Task, request: Any, controller: Any
    ) -> dict[str, Any]:
        """Execute the actual operation (implemented by subclasses).

        Args:
            task: Task instance
            request: Operation-specific request data
            controller: Controller instance

        Returns:
            Result dictionary

        Raises:
            OperationCancelledException: If operation is cancelled
            Exception: Any other operation-specific errors
        """
        pass

    async def execute(
        self, task_id: str, request: Any, controller: Any
    ) -> dict[str, Any]:
        """Execute task with full lifecycle management.

        Args:
            task_id: Task ID to execute
            request: Operation-specific request data
            controller: Controller instance

        Returns:
            Result dictionary

        Raises:
            ValueError: If task not found
        """
        task = self.task_manager.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        try:
            # Update status to running
            self.task_manager.update_status(task_id, TaskStatus.RUNNING)
            await self.broadcast_progress(
                task_id, {"message": "Task execution started"}
            )

            # Execute the operation
            result = await self.execute_operation(task, request, controller)

            # Complete successfully
            self.task_manager.complete_task(task_id, result)
            await self.broadcast_progress(
                task_id, {"message": "Task completed successfully"}
            )

            logger.info(
                f"Task {task_id} ({task.operation_type.value}) completed successfully"
            )

            return result

        except OperationCancelledException:
            # Handle cancellation
            self.task_manager.update_status(task_id, TaskStatus.CANCELLED)
            await self.broadcast_progress(task_id, {"message": "Task cancelled"})

            logger.info(f"Task {task_id} ({task.operation_type.value}) cancelled")

            # Don't re-raise - cancellation is already handled
            # Re-raising causes asyncio to log "unhandled exception" for background tasks
            return None

        except Exception as e:
            # Handle failure
            error_msg = str(e)
            self.task_manager.fail_task(task_id, error_msg)
            await self.broadcast_progress(
                task_id, {"message": f"Task failed: {error_msg}"}
            )

            logger.error(
                f"Task {task_id} ({task.operation_type.value}) failed: {error_msg}",
                exc_info=True,
            )

            # Don't re-raise - failure is already handled and logged
            # Re-raising causes asyncio to log "unhandled exception" for background tasks
            return None

        finally:
            # Clear current task reference if in terminal state
            self.task_manager.clear_current_task()

    def should_cancel(self, task: Task) -> bool:
        """Check if task should be cancelled.

        Args:
            task: Task to check

        Returns:
            True if cancellation has been requested
        """
        return task.cancellation_event.is_set()

    async def broadcast_progress(self, task_id: str, progress_data: dict[str, Any]):
        """Broadcast progress update via WebSocket.

        Args:
            task_id: Task ID
            progress_data: Progress data to broadcast
        """
        # Update task manager
        self.task_manager.update_progress(task_id, progress_data)

        # Broadcast via WebSocket if callback provided
        if self.broadcast_callback:
            task = self.task_manager.get_task(task_id)
            if task:
                message = {
                    "type": "task_progress",
                    "task_id": task_id,
                    "operation_type": task.operation_type.value,
                    "status": task.status.value,
                    "progress": task.progress,
                }

                try:
                    await self.broadcast_callback(message)
                except Exception as e:
                    logger.error(f"Failed to broadcast progress: {e}")

    async def handle_exception(self, task_id: str, exception: Exception):
        """Handle exception during task execution.

        Args:
            task_id: Task ID
            exception: Exception that occurred
        """
        error_msg = str(exception)
        logger.error(
            f"Exception in task {task_id}: {error_msg}",
            exc_info=True,
        )

        self.task_manager.fail_task(task_id, error_msg)
        await self.broadcast_progress(task_id, {"message": f"Error: {error_msg}"})

    def create_progress_callback(self, task_id: str) -> Callable[[dict], None]:
        """Create a synchronous progress callback for use in thread pool.

        The callback created by this method can be called from synchronous
        code running in a thread pool. It will schedule the async broadcast
        on the event loop.

        Args:
            task_id: Task ID

        Returns:
            Synchronous callback function
        """
        # Capture the event loop from the calling context (main thread)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop, callback won't work but won't crash
            loop = None
            logger.warning("No running event loop when creating progress callback")

        def progress_callback(progress_data: dict[str, Any]):
            """Synchronous progress callback that schedules async broadcast."""
            if loop is None:
                # Silently skip if no loop available
                return

            try:
                # Schedule the coroutine on the event loop
                asyncio.run_coroutine_threadsafe(
                    self.broadcast_progress(task_id, progress_data), loop
                )
            except Exception as e:
                logger.error(f"Failed to schedule progress broadcast: {e}")

        return progress_callback
