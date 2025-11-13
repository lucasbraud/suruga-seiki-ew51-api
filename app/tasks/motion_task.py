"""Motion task executor for axis movement operations."""

import logging
from typing import Any

from app.controller_manager import SurugaSeikiController
from app.task_manager import Task
from app.tasks.base_task import BaseTaskExecutor, OperationCancelledException

logger = logging.getLogger(__name__)


class MotionTaskExecutor(BaseTaskExecutor):
    """Task executor for axis movement operations (absolute and relative)."""

    async def execute_operation(
        self, task: Task, request: dict, controller: SurugaSeikiController
    ) -> dict[str, Any]:
        """Execute axis movement operation.

        Args:
            task: Task instance
            request: Dictionary with movement parameters:
                - movement_type: "absolute" or "relative"
                - axis_number: Axis number (1-12)
                - position: Target position (for absolute) or distance (for relative)
                - speed: Movement speed in um/s
            controller: Controller instance

        Returns:
            Result dictionary with movement information

        Raises:
            OperationCancelledException: If operation is cancelled
            Exception: Any other errors during execution
        """
        movement_type = request.get("movement_type")
        axis_number = request.get("axis_number")
        speed = request.get("speed", 1000.0)

        if movement_type not in ["absolute", "relative"]:
            raise ValueError(f"Invalid movement_type: {movement_type}")

        if not axis_number or not isinstance(axis_number, int) or axis_number < 1 or axis_number > 12:
            raise ValueError(f"Invalid axis_number: {axis_number}")

        logger.info(
            f"Starting {movement_type} movement task {task.task_id} for axis {axis_number}"
        )

        # Create progress callback for thread pool
        progress_callback = self.create_progress_callback(task.task_id)

        try:
            if movement_type == "absolute":
                position = request.get("position")
                if position is None:
                    raise ValueError("position is required for absolute movement")

                result = await controller.move_absolute_async(
                    axis_number=axis_number,
                    position=position,
                    speed=speed,
                    cancellation_event=task.cancellation_event,
                    progress_callback=progress_callback,
                )

            else:  # relative
                distance = request.get("distance")
                if distance is None:
                    raise ValueError("distance is required for relative movement")

                result = await controller.move_relative_async(
                    axis_number=axis_number,
                    distance=distance,
                    speed=speed,
                    cancellation_event=task.cancellation_event,
                    progress_callback=progress_callback,
                )

        except Exception as e:
            # Check if it was cancelled
            if self.should_cancel(task):
                raise OperationCancelledException(f"Movement was cancelled: {str(e)}")
            else:
                raise

        if not result.get("success"):
            raise Exception(f"Movement failed: {result}")

        logger.info(
            f"Movement task {task.task_id} completed successfully in {result.get('execution_time', 0):.2f}s"
        )

        return result
