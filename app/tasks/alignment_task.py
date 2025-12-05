"""Optical alignment task executor."""

import logging
from typing import Any, TYPE_CHECKING

from app.models import FlatAlignmentRequest, FocusAlignmentRequest
from app.task_manager import Task
from app.tasks.base_task import BaseTaskExecutor, OperationCancelledException

if TYPE_CHECKING:
    from app.controller_manager import SurugaSeikiController
    from app.mock_controller import MockSurugaSeikiController

logger = logging.getLogger(__name__)


class AlignmentTaskExecutor(BaseTaskExecutor):
    """Task executor for optical alignment operations (flat and focus)."""

    async def execute_operation(
        self, task: Task, request: dict, controller: "SurugaSeikiController | MockSurugaSeikiController"
    ) -> dict[str, Any]:
        """Execute alignment operation (flat or focus).

        Args:
            task: Task instance
            request: Dict containing alignment_type and request object
            controller: Controller instance

        Returns:
            Result dictionary with alignment response data

        Raises:
            OperationCancelledException: If operation is cancelled
            Exception: Any other errors during execution
        """
        alignment_type = request.get("alignment_type")  # "flat" or "focus"
        alignment_request = request.get("request")

        logger.info(
            f"Starting {alignment_type} alignment task {task.task_id}"
        )

        # Create progress callback for thread pool
        progress_callback = self.create_progress_callback(task.task_id)

        # Execute the appropriate async alignment
        if alignment_type == "flat":
            result = await controller.execute_flat_alignment_async(
                request=alignment_request,
                cancellation_event=task.cancellation_event,
                progress_callback=progress_callback,
            )
        elif alignment_type == "focus":
            result = await controller.execute_focus_alignment_async(
                request=alignment_request,
                cancellation_event=task.cancellation_event,
                progress_callback=progress_callback,
            )
        else:
            raise Exception(f"Unknown alignment type: {alignment_type}")

        if result is None:
            # Check if it was cancelled
            if self.should_cancel(task):
                raise OperationCancelledException(f"{alignment_type.title()} alignment was cancelled")
            else:
                raise Exception(f"{alignment_type.title()} alignment returned None (unknown error)")

        # Convert response to dictionary
        result_dict = {
            "success": result.success,
            "status_code": result.status_code,
            "status_value": result.status_value,
            "status_description": result.status_description,
            "phase_code": result.phase_code,
            "phase_value": result.phase_value,
            "phase_description": result.phase_description,
            "initial_power": result.initial_power,
            "final_power": result.final_power,
            "power_improvement": result.power_improvement,
            "peak_position_x": result.peak_position_x,
            "peak_position_y": result.peak_position_y,
            "execution_time": result.execution_time,
            "error_message": result.error_message,
        }

        # Add Z position for focus alignment
        if alignment_type == "focus" and result.peak_position_z is not None:
            result_dict["peak_position_z"] = result.peak_position_z

        # Include profile data counts and actual profile data if available
        if result.field_search_profile:
            result_dict["field_search_profile_points"] = len(result.field_search_profile)
            result_dict["field_search_profile"] = [
                {"position": p.position, "signal": p.signal}
                for p in result.field_search_profile
            ]

        if result.peak_search_x_profile:
            result_dict["peak_search_x_profile_points"] = len(result.peak_search_x_profile)
            result_dict["peak_search_x_profile"] = [
                {"position": p.position, "signal": p.signal}
                for p in result.peak_search_x_profile
            ]

        if result.peak_search_y_profile:
            result_dict["peak_search_y_profile_points"] = len(result.peak_search_y_profile)
            result_dict["peak_search_y_profile"] = [
                {"position": p.position, "signal": p.signal}
                for p in result.peak_search_y_profile
            ]

        if alignment_type == "focus" and result.peak_search_z_profile:
            result_dict["peak_search_z_profile_points"] = len(result.peak_search_z_profile)
            result_dict["peak_search_z_profile"] = [
                {"position": p.position, "signal": p.signal}
                for p in result.peak_search_z_profile
            ]

        # Check if operation was successful
        if not result.success:
            raise Exception(
                result.error_message
                or f"{alignment_type.title()} alignment failed with status: {result.status_code}"
            )

        logger.info(
            f"{alignment_type.title()} alignment task {task.task_id} completed successfully in {result.execution_time:.2f}s"
        )

        return result_dict
