"""Angle adjustment task executor."""

import logging
from typing import Any

from app.controller_manager import SurugaSeikiController
from app.models import AngleAdjustmentRequest
from app.task_manager import Task
from app.tasks.base_task import BaseTaskExecutor, OperationCancelledException

logger = logging.getLogger(__name__)


class AngleAdjustmentTaskExecutor(BaseTaskExecutor):
    """Task executor for angle adjustment operations."""

    async def execute_operation(
        self, task: Task, request: AngleAdjustmentRequest, controller: SurugaSeikiController
    ) -> dict[str, Any]:
        """Execute angle adjustment operation.

        Args:
            task: Task instance
            request: AngleAdjustmentRequest with parameters
            controller: Controller instance

        Returns:
            Result dictionary with angle adjustment response data

        Raises:
            OperationCancelledException: If operation is cancelled
            Exception: Any other errors during execution
        """
        logger.info(
            f"Starting angle adjustment task {task.task_id} for stage {request.stage.name}"
        )

        # Create progress callback for thread pool
        progress_callback = self.create_progress_callback(task.task_id)

        # Execute the async angle adjustment
        result = await controller.execute_angle_adjustment_async(
            request=request,
            cancellation_event=task.cancellation_event,
            progress_callback=progress_callback,
        )

        if result is None:
            # Check if it was cancelled
            if self.should_cancel(task):
                raise OperationCancelledException("Angle adjustment was cancelled")
            else:
                raise Exception("Angle adjustment returned None (unknown error)")

        # Convert response to dictionary
        result_dict = {
            "success": result.success,
            "status_code": result.status_code,
            "status_value": result.status_value,
            "status_description": result.status_description,
            "phase_code": result.phase_code,
            "phase_value": result.phase_value,
            "phase_description": result.phase_description,
            "initial_signal": result.initial_signal,
            "final_signal": result.final_signal,
            "signal_improvement": result.signal_improvement,
            "execution_time": result.execution_time,
            "error_message": result.error_message,
        }

        # Include profile data if available
        if result.contact_z_profile:
            result_dict["contact_z_profile_points"] = len(result.contact_z_profile)

        if result.adjusting_tx_profile:
            result_dict["adjusting_tx_profile_points"] = len(result.adjusting_tx_profile)

        if result.adjusting_ty_profile:
            result_dict["adjusting_ty_profile_points"] = len(result.adjusting_ty_profile)

        # Check if operation was successful
        if not result.success:
            raise Exception(
                result.error_message
                or f"Angle adjustment failed with status: {result.status_code}"
            )

        logger.info(
            f"Angle adjustment task {task.task_id} completed successfully in {result.execution_time:.2f}s"
        )

        return result_dict
