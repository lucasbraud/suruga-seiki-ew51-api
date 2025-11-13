"""Profile measurement task executor."""

import logging
from typing import Any

from app.controller_manager import SurugaSeikiController
from app.models import ProfileMeasurementRequest
from app.task_manager import Task
from app.tasks.base_task import BaseTaskExecutor, OperationCancelledException

logger = logging.getLogger(__name__)


class ProfileMeasurementTaskExecutor(BaseTaskExecutor):
    """Task executor for profile measurement operations."""

    async def execute_operation(
        self, task: Task, request: ProfileMeasurementRequest, controller: SurugaSeikiController
    ) -> dict[str, Any]:
        """Execute profile measurement operation with cancellation support.

        Returns:
            Result dictionary with profile measurement response data
        """
        logger.info(
            f"Starting profile measurement task {task.task_id} on axis {request.scan_axis}"
        )

        # Progress callback for thread pool context
        progress_callback = self.create_progress_callback(task.task_id)

        # Execute async wrapper on controller
        result = await controller.execute_profile_measurement_async(
            request=request,
            cancellation_event=task.cancellation_event,
            progress_callback=progress_callback,
        )

        if result is None:
            if self.should_cancel(task):
                raise OperationCancelledException("Profile measurement was cancelled")
            else:
                raise Exception("Profile measurement returned None (unknown error)")

        # Prepare result dictionary
        result_dict: dict[str, Any] = {
            "success": result.success,
            "total_points": getattr(result, "total_points", 0),
            "peak_position": getattr(result, "peak_position", 0.0),
            "peak_value": getattr(result, "peak_value", 0.0),
            "peak_index": getattr(result, "peak_index", 0),
            "main_axis_number": getattr(result, "main_axis_number", request.scan_axis),
            "main_axis_initial_position": getattr(result, "main_axis_initial_position", 0.0),
            "main_axis_final_position": getattr(result, "main_axis_final_position", 0.0),
            "signal_ch_number": getattr(result, "signal_ch_number", request.signal_ch1_number),
            "scan_range": getattr(result, "scan_range", request.scan_range),
            "scan_speed": getattr(result, "scan_speed", request.scan_speed),
        }

        # Error/status fields when failed
        for key in ("status_code", "status_value", "status_description", "error_code", "error_value", "error_description"):
            if hasattr(result, key):
                result_dict[key] = getattr(result, key)

        # Ensure success state; treat explicit cancellation as cancelled, not failure
        if not result.success:
            status_code = str(result_dict.get("status_code", ""))
            status_desc = str(result_dict.get("status_description", "")).lower()
            error_desc = str(result_dict.get("error_description", "")).lower()
            if status_code == "Cancelled" or "cancelled" in status_desc or "cancelled" in error_desc:
                raise OperationCancelledException("Profile measurement was cancelled")
            raise Exception(
                result_dict.get("status_description")
                or result_dict.get("error_description")
                or "Profile measurement failed"
            )

        logger.info(
            f"Profile measurement task {task.task_id} completed: points={result_dict['total_points']}, "
            f"peak={result_dict['peak_value']:.6f} at {result_dict['peak_position']:.3f} µm"
        )

        return result_dict
