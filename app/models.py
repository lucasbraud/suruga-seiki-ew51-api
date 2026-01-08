"""
Pydantic models for API requests and responses
"""
from typing import Optional, List, Tuple
from enum import Enum
from pydantic import BaseModel, Field, field_validator


# ========== Enums ==========

class ProfileErrorCode(Enum):
    """Profile measurement error codes from manual section 4.7.3.1"""
    NONE = (0, "Normal")
    AXIS = (1, "Error due to axis")
    PROFILING = (2, "Executing profile measurement")
    PARAMETER = (3, "Inappropriate parameters")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def error_name(self) -> str:
        """Return the error name as string"""
        return self.name.capitalize()

    def to_dict(self) -> dict:
        """Return error info as dictionary"""
        return {
            "error": self.error_name,
            "value": self.value,
            "description": self.description
        }


class ProfileMeasurementStatus(Enum):
    """Profile measurement status from manual section 4.7.3.2"""
    STOPPING = (0, "Stopped")
    SUCCESS = (1, "Normal termination")
    PROFILING = (2, "Executing profile measurement")
    PROFILE_DATA_OVER = (3, "Exceeded profile data store range")
    INVALID_PARAMETER = (4, "Invalid profile measurement parameters")
    SERVOS_NOT_READY = (5, "Servo not in Ready state")
    SERVOS_ALARM = (6, "Servo alarm")
    STAGE_ON_LIMIT = (7, "Stage reached at limit sensor")
    TORQUE_LIMIT = (8, "Stopped by torque limit")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def status_name(self) -> str:
        """Return the status name as string"""
        name_map = {
            "STOPPING": "Stopping",
            "SUCCESS": "Success",
            "PROFILING": "Profiling",
            "PROFILE_DATA_OVER": "ProfileDataOver",
            "INVALID_PARAMETER": "InvalidParameter",
            "SERVOS_NOT_READY": "ServosNotReady",
            "SERVOS_ALARM": "ServosAlarm",
            "STAGE_ON_LIMIT": "StageOnLimit",
            "TORQUE_LIMIT": "TorqueLimit"
        }
        return name_map.get(self.name, self.name)

    def to_dict(self) -> dict:
        """Return status info as dictionary"""
        return {
            "status": self.status_name,
            "value": self.value,
            "description": self.description
        }


class AngleAdjustmentStage(Enum):
    """Stage selection for angle adjustment"""
    LEFT = 1
    RIGHT = 2


class AngleAdjustmentErrorCode(Enum):
    """Angle adjustment error codes"""
    NONE = (0, "Normal")
    AXIS = (1, "Error due to axis")
    ADJUSTING = (2, "Executing angle adjustment")
    PARAMETER = (3, "Invalid parameter")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def error_name(self) -> str:
        """Return the error name as string"""
        return self.name.capitalize()

    def to_dict(self) -> dict:
        """Return error info as dictionary"""
        return {
            "error": self.error_name,
            "value": self.value,
            "description": self.description
        }


class AngleAdjustmentStatus(Enum):
    """Angle adjustment status codes"""
    STOPPING = (0, "Angle adjustment is stopping normally")
    SUCCESS = (1, "Angle adjustment completed successfully")
    ADJUSTING = (2, "Executing angle adjustment")
    PROFILE_DATA_OVER = (3, "Exceeded recording range of profile data")
    INVALID_PARAMETER = (4, "Invalid parameter")
    SERVO_IS_NOT_READY = (5, "Using axis is not turned on")
    SERVO_IS_ALARM = (6, "Servo alarm is occurring for using axis")
    STAGE_ON_LIMIT = (7, "A position limit of using axis is detected")
    SIGNAL_LOWER_LIMIT = (8, "Signal reached lower limit")
    COULD_NOT_CONTACT = (9, "Failed for no contact detection")
    ADJUST_COUNT_OVER = (10, "Failed for exceeding maximum number of retry count")
    ANGLE_ADJUST_RANGE_OVER = (11, "Failed for exceeding angle adjustment range")
    LOST_CONTACT = (12, "Failed for lost contact detection while adjusting")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def status_name(self) -> str:
        """Return the status name as string"""
        name_map = {
            "STOPPING": "Stopping",
            "SUCCESS": "Success",
            "ADJUSTING": "Adjusting",
            "PROFILE_DATA_OVER": "ProfileDataOver",
            "INVALID_PARAMETER": "InvalidParameter",
            "SERVO_IS_NOT_READY": "ServoIsNotReady",
            "SERVO_IS_ALARM": "ServoIsAlarm",
            "STAGE_ON_LIMIT": "StageOnLimit",
            "SIGNAL_LOWER_LIMIT": "SignalLowerLimit",
            "COULD_NOT_CONTACT": "CouldNotContact",
            "ADJUST_COUNT_OVER": "AdjustCountOver",
            "ANGLE_ADJUST_RANGE_OVER": "AngleAdjustRangeOver",
            "LOST_CONTACT": "LostContact"
        }
        return name_map.get(self.name, self.name)

    def to_dict(self) -> dict:
        """Return status info as dictionary"""
        return {
            "status": self.status_name,
            "value": self.value,
            "description": self.description
        }


class AdjustingStatus(Enum):
    """Angle adjustment phase status"""
    NOT_ADJUSTING = (0, "Not adjusting")
    INITIALIZING = (1, "Executing initializing process")
    CONTACTING_Z = (2, "Detecting contact with Z-axis")
    ADJUSTING_TX = (3, "Adjusting axis specified by angleAxisNumberTx")
    ADJUSTING_TY = (4, "Adjusting axis specified by angleAxisNumberTy")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def phase_name(self) -> str:
        """Return the phase name as string"""
        name_map = {
            "NOT_ADJUSTING": "NotAdjusting",
            "INITIALIZING": "Initializing",
            "CONTACTING_Z": "ContactingZ",
            "ADJUSTING_TX": "AdjustingTx",
            "ADJUSTING_TY": "AdjustingTy"
        }
        return name_map.get(self.name, self.name)

    def to_dict(self) -> dict:
        """Return phase info as dictionary"""
        return {
            "phase": self.phase_name,
            "value": self.value,
            "description": self.description
        }


class AlignmentErrorCode(Enum):
    """Optical alignment error codes"""
    NONE = (0, "Normal")
    AXIS = (1, "Error due to axis")
    ALIGNING = (2, "Executing alignment")
    PARAMETER = (3, "Invalid parameter")
    INTERRUPTED = (4, "Alignment interrupted")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def error_name(self) -> str:
        """Return the error name as string"""
        return self.name.capitalize()

    def to_dict(self) -> dict:
        """Return error info as dictionary"""
        return {
            "error": self.error_name,
            "value": self.value,
            "description": self.description
        }


class OpticalAlignmentStatus(Enum):
    """Optical alignment status codes"""
    STOPPING = (0, "Alignment is stopping normally")
    SUCCESS = (1, "Alignment completed successfully")
    ALIGNING = (2, "Executing alignment")
    FIELD_SEARCH_RANGE_OVER = (3, "Failed for exceeding field search range")
    PROFILE_DATA_OVER = (4, "Exceed recording range of profile data")
    PEAK_SEARCH_COUNT_OVER = (5, "Failed for exceeding maximum number of peak search count")
    PEAK_SEARCH_RANGE_OVER = (6, "Failed for exceeding peak search range")
    INVALID_PARAMETER = (7, "Invalid parameter")
    SERVO_IS_NOT_READY = (8, "Using axis is not turned on")
    SERVO_IS_ALARM = (9, "Servo alarm is occurring for using axis")
    STAGE_ON_LIMIT = (10, "A position limit of using axis is detected")
    VOLTAGE_LIMIT = (11, "Signal voltage reached at maximum limit")
    PM_RANGE_LIMIT = (12, "Could not range up due to PM range limit")
    PM_INIT_RANGE_CHANGE_FAIL = (13, "Power meter initial range setting failed")
    PM_DISCONNECTED = (14, "Power meter is not connected")
    ROTATION_ADJUSTMENT_FAIL = (15, "Failed for rotation adjustment")
    IN_POSITION_FAIL = (16, "Not reached to in-position state")
    TORQUE_LIMIT = (17, "Stopped by torque limit")
    INTERRUPTED = (18, "Alignment interrupted")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def status_name(self) -> str:
        """Return the status name as string"""
        name_map = {
            "STOPPING": "Stopping",
            "SUCCESS": "Success",
            "ALIGNING": "Aligning",
            "FIELD_SEARCH_RANGE_OVER": "FieldSearchRangeOver",
            "PROFILE_DATA_OVER": "ProfileDataOver",
            "PEAK_SEARCH_COUNT_OVER": "PeakSearchCountOver",
            "PEAK_SEARCH_RANGE_OVER": "PeakSearchRangeOver",
            "INVALID_PARAMETER": "InvalidParameter",
            "SERVO_IS_NOT_READY": "ServoIsNotReady",
            "SERVO_IS_ALARM": "ServoIsAlarm",
            "STAGE_ON_LIMIT": "StageOnLimit",
            "VOLTAGE_LIMIT": "VoltageLimit",
            "PM_RANGE_LIMIT": "PMRangeLimit",
            "PM_INIT_RANGE_CHANGE_FAIL": "PMInitRangeChangeFail",
            "PM_DISCONNECTED": "PMDisconnected",
            "ROTATION_ADJUSTMENT_FAIL": "RotationAdjustmentFail",
            "IN_POSITION_FAIL": "InPositionFail",
            "TORQUE_LIMIT": "TorqueLimit",
            "INTERRUPTED": "Interrupted"
        }
        return name_map.get(self.name, self.name)

    def to_dict(self) -> dict:
        """Return status info as dictionary"""
        return {
            "status": self.status_name,
            "value": self.value,
            "description": self.description
        }


class AligningStatusPhase(Enum):
    """Optical alignment phase status"""
    NOT_ALIGNING = (0, "Not aligning")
    INITIALIZING = (1, "Executing initializing process")
    FIELD_SEARCHING = (2, "Field searching")
    PEAK_SEARCHING_X = (3, "X-axis peak searching")
    PEAK_SEARCHING_Y = (4, "Y-axis peak searching")
    PEAK_SEARCHING_Z = (5, "Z-axis peak searching")
    PEAK_SEARCH_X_CH2 = (6, "Ch2 X-axis peak searching")

    def __init__(self, value: int, description: str):
        self._value_ = value
        self.description = description

    @property
    def phase_name(self) -> str:
        """Return the phase name as string"""
        name_map = {
            "NOT_ALIGNING": "NotAligning",
            "INITIALIZING": "Initializing",
            "FIELD_SEARCHING": "FieldSearching",
            "PEAK_SEARCHING_X": "PeakSearchingX",
            "PEAK_SEARCHING_Y": "PeakSearchingY",
            "PEAK_SEARCHING_Z": "PeakSearchingZ",
            "PEAK_SEARCH_X_CH2": "PeakSearchXCh2"
        }
        return name_map.get(self.name, self.name)

    def to_dict(self) -> dict:
        """Return phase info as dictionary"""
        return {
            "phase": self.phase_name,
            "value": self.value,
            "description": self.description
        }


# ========== Connection Models ==========

class ConnectionRequest(BaseModel):
    ads_address: str = Field(
        default="5.146.68.190.1.1",
        description="ADS address of probe station (format: x.x.x.x.x.x)"
    )


class ConnectionResponse(BaseModel):
    success: bool
    message: str
    connected: bool


class SystemStatus(BaseModel):
    """Complete system status information"""
    is_connected: bool
    dll_version: Optional[str] = None
    system_version: Optional[str] = None
    is_error: bool
    is_emergency_asserted: Optional[bool] = None
    error_message: str = ""
    timestamp: str


# ========== Axis Models ==========

class AxisStatus(BaseModel):
    """Status and position information for a single axis"""
    axis_number: int = Field(ge=1, le=12, description="Axis number (1-12)")
    actual_position: float = Field(description="Current actual position in micrometers or degrees")
    is_moving: bool = Field(description="True if axis is currently moving")
    is_servo_on: bool = Field(description="True if servo is enabled")
    is_error: bool = Field(default=False, description="True if axis has an error")
    error_code: int = Field(default=0, description="Error code if is_error is True")


# ========== Servo Models ==========

class ServoRequest(BaseModel):
    axis_id: int = Field(ge=1, le=12, description="Axis number (1-12)")


# ========== Motion Models ==========

class MoveAbsoluteRequest(BaseModel):
    axis_id: int = Field(..., ge=1, le=12, example=7, description="The axis number (1-indexed)")
    position: float = Field(..., example=1500.5, description="Target position in µm or degrees")
    speed: float = Field(default=1000.0, gt=0, description="Movement speed in µm/s or deg/s")


class MoveRelativeRequest(BaseModel):
    axis_id: int = Field(..., ge=1, le=12, example=7, description="The axis number (1-indexed)")
    distance: float = Field(..., example=500.0, description="Relative distance in µm or degrees")
    speed: float = Field(default=1000.0, gt=0, description="Movement speed in µm/s or deg/s")


class Move2DRequest(BaseModel):
    axis1: int = Field(ge=1, le=12, description="First axis number")
    axis2: int = Field(ge=1, le=12, description="Second axis number")
    x: float = Field(description="X position in µm")
    y: float = Field(description="Y position in µm")
    speed: float = Field(default=1000.0, gt=0, description="Movement speed in µm/s")
    angle_offset: float = Field(default=0.0, ge=-180, le=180, description="Rotation angle offset in degrees")
    relative: bool = Field(default=False, description="True for relative move, False for absolute")


class Move3DRequest(BaseModel):
    axis1: int = Field(ge=1, le=12, description="First axis number (X)")
    axis2: int = Field(ge=1, le=12, description="Second axis number (Y)")
    axis3: int = Field(ge=1, le=12, description="Third axis number (Z)")
    x: float = Field(description="X position in µm")
    y: float = Field(description="Y position in µm")
    z: float = Field(description="Z position in µm")
    speed: float = Field(default=1000.0, gt=0, description="Movement speed in µm/s")
    rotation_center_x: float = Field(default=0.0, description="Rotation center X offset in µm")
    rotation_center_y: float = Field(default=0.0, description="Rotation center Y offset in µm")


# ========== Alignment Models ==========

class FlatAlignmentRequest(BaseModel):
    """
    Flat alignment parameters based on FlatParameter structure from manual.
    Used for 2D flat surface alignment with detailed control over search parameters.

    All ~30 parameters required by the Alignment.FlatParameter API.
    """
    # Stage configuration
    mainStageNumberX: int = Field(7, ge=1, le=12, description="Main X-axis stage number")
    mainStageNumberY: int = Field(8, ge=1, le=12, description="Main Y-axis stage number")
    subStageNumberXY: int = Field(0, ge=0, le=12, description="Sub-stage number, 0 for None")
    subAngleX: float = Field(0.0, description="Sub-stage X angle in degrees")
    subAngleY: float = Field(0.0, description="Sub-stage Y angle in degrees")

    # Power meter configuration
    pmCh: int = Field(1, ge=1, description="Power meter channel number")
    analogCh: int = Field(1, ge=1, description="Analog input channel number")
    wavelength: int = Field(1310, gt=0, description="Measurement wavelength in nm (e.g., 1310, 1550)")
    pmAutoRangeUpOn: bool = Field(True, description="Enable power meter auto-range up")
    pmInitRangeSettingOn: bool = Field(True, description="Enable initial range setting")
    pmInitRange: int = Field(-30, description="Initial power meter range in dBm")

    # Search thresholds
    fieldSearchThreshold: float = Field(0.0, ge=0, description="Field search threshold")
    peakSearchThreshold: float = Field(10.0, ge=0, le=99.99, description="Peak search threshold in %")

    # Search ranges
    searchRangeX: float = Field(15.0, gt=0, description="X-axis search range in µm")
    searchRangeY: float = Field(10.0, gt=0, description="Y-axis search range in µm")

    # Field search parameters
    fieldSearchPitchX: float = Field(1.0, gt=0, description="X-axis field search pitch in µm")
    fieldSearchPitchY: float = Field(1.0, gt=0, description="Y-axis field search pitch in µm")
    fieldSearchFirstPitchX: float = Field(0.0, ge=0, description="First X-axis field search pitch in µm")
    fieldSearchSpeedX: float = Field(100.0, gt=0, description="X-axis field search speed in µm/s")
    fieldSearchSpeedY: float = Field(100.0, gt=0, description="Y-axis field search speed in µm/s")

    # Peak search parameters
    peakSearchSpeedX: float = Field(10.0, gt=0, description="X-axis peak search speed in µm/s")
    peakSearchSpeedY: float = Field(10.0, gt=0, description="Y-axis peak search speed in µm/s")

    # Smoothing parameters
    smoothingRangeX: int = Field(40, ge=0, description="X-axis smoothing range in samples")
    smoothingRangeY: int = Field(40, ge=0, description="Y-axis smoothing range in samples")

    # Centroid parameters
    centroidThresholdX: float = Field(0, ge=0, description="X-axis centroid threshold")
    centroidThresholdY: float = Field(0, ge=0, description="Y-axis centroid threshold")

    # Convergence parameters
    convergentRangeX: float = Field(0.5, le=1, description="X-axis convergence range")
    convergentRangeY: float = Field(0.5, e=1, description="Y-axis convergence range")
    comparisonCount: int = Field(2, ge=1, description="Comparison count for convergence")
    maxRepeatCount: int = Field(10, ge=1, le=99, description="Maximum repeat count for alignment")


class FocusAlignmentRequest(BaseModel):
    """
    Focus alignment parameters based on FocusParameter structure from manual.
    Similar to Flat but includes Z-axis focus optimization with zMode.

    All ~31 parameters required by the Alignment.FocusParameter API.
    """
    # Z-mode configuration
    zMode: str = Field("Round", description="Z-axis mode: Round, Triangle, or Linear")

    # Stage configuration
    mainStageNumberX: int = Field(7, ge=1, le=12, description="Main X-axis stage number")
    mainStageNumberY: int = Field(8, ge=1, le=12, description="Main Y-axis stage number")
    subStageNumberXY: int = Field(0, ge=0, le=12, description="Sub-stage number, 0 for None")
    subAngleX: float = Field(0.0, description="Sub-stage X angle in degrees")
    subAngleY: float = Field(0.0, description="Sub-stage Y angle in degrees")

    # Power meter configuration
    pmCh: int = Field(1, ge=1, description="Power meter channel number")
    analogCh: int = Field(1, ge=1, description="Analog input channel number")
    wavelength: int = Field(1310, gt=0, description="Measurement wavelength in nm (e.g., 1310, 1550)")
    pmAutoRangeUpOn: bool = Field(True, description="Enable power meter auto-range up")
    pmInitRangeSettingOn: bool = Field(True, description="Enable initial range setting")
    pmInitRange: int = Field(-30, description="Initial power meter range in dBm")

    # Search thresholds
    fieldSearchThreshold: float = Field(0.1, ge=0, description="Field search threshold")
    peakSearchThreshold: float = Field(40.0, ge=0, le=99.99, description="Peak search threshold in %")

    # Search ranges
    searchRangeX: float = Field(500.0, gt=0, description="X-axis search range in µm")
    searchRangeY: float = Field(500.0, gt=0, description="Y-axis search range in µm")

    # Field search parameters
    fieldSearchPitchX: float = Field(5.0, gt=0, description="X-axis field search pitch in µm")
    fieldSearchPitchY: float = Field(5.0, gt=0, description="Y-axis field search pitch in µm")
    fieldSearchFirstPitchX: float = Field(0.0, ge=0, description="First X-axis field search pitch in µm")
    fieldSearchSpeedX: float = Field(1000.0, gt=0, description="X-axis field search speed in µm/s")
    fieldSearchSpeedY: float = Field(1000.0, gt=0, description="Y-axis field search speed in µm/s")

    # Peak search parameters
    peakSearchSpeedX: float = Field(5.0, gt=0, description="X-axis peak search speed in µm/s")
    peakSearchSpeedY: float = Field(5.0, gt=0, description="Y-axis peak search speed in µm/s")

    # Smoothing parameters
    smoothingRangeX: int = Field(50, ge=0, description="X-axis smoothing range in samples")
    smoothingRangeY: int = Field(50, ge=0, description="Y-axis smoothing range in samples")

    # Centroid parameters
    centroidThresholdX: int = Field(0, ge=0, description="X-axis centroid threshold")
    centroidThresholdY: int = Field(0, ge=0, description="Y-axis centroid threshold")

    # Convergence parameters
    convergentRangeX: int = Field(1, ge=1, description="X-axis convergence range")
    convergentRangeY: int = Field(1, ge=1, description="Y-axis convergence range")
    comparisonCount: int = Field(2, ge=1, description="Comparison count for convergence")
    maxRepeatCount: int = Field(10, ge=1, le=99, description="Maximum repeat count for alignment")


class SingleAlignmentRequest(BaseModel):
    """Single axis alignment parameters"""
    stage_number: int = Field(1, ge=1, le=12, description="Axis stage number")
    analog_ch: int = Field(1, ge=1, description="Analog input channel number")
    search_range: float = Field(1000.0, gt=0, description="Search range in µm")
    search_speed: float = Field(100.0, gt=0, description="Search speed in µm/s")
    sampling_interval: float = Field(10.0, gt=0, description="Sampling interval in µm")


class ProfileDataPoint(BaseModel):
    """
    Single data point in a profile measurement.
    
    Note: Profile measurement scans only ONE axis at a time.
    For multi-axis (X,Y) profile data, use Optical Alignment API which
    provides separate profiles for FieldSearch, PeakSearchX, and PeakSearchY.
    """
    position: float = Field(description="Main axis position in µm")
    signal: float = Field(description="Signal value (voltage, power, etc.)")


class AlignmentResponse(BaseModel):
    """
    Response from optical alignment execution (flat or focus).
    Following the pattern from AngleAdjustmentResponse and ProfileDataResponse.
    Includes optical power measurements and profile data retrieval.
    """
    success: bool = Field(description="True if alignment completed successfully")

    # Status information (always populated)
    status_code: Optional[str] = Field(default=None, description="Final status code from OpticalAlignmentStatus")
    status_value: Optional[int] = Field(default=None, description="Final status numeric value")
    status_description: Optional[str] = Field(default=None, description="Final status description")

    # Phase information (populated when available)
    phase_code: Optional[str] = Field(default=None, description="Last phase code from AligningStatusPhase")
    phase_value: Optional[int] = Field(default=None, description="Last phase numeric value")
    phase_description: Optional[str] = Field(default=None, description="Last phase description")

    # Optical power measurements in dBm (populated on success)
    initial_power: Optional[float] = Field(default=None, description="Initial optical power in dBm before alignment")
    final_power: Optional[float] = Field(default=None, description="Final optical power in dBm after alignment")
    power_improvement: Optional[float] = Field(default=None, description="Power improvement in dB (final - initial)")

    # Peak positions (populated on success)
    peak_position_x: Optional[float] = Field(default=None, description="Peak X position in µm")
    peak_position_y: Optional[float] = Field(default=None, description="Peak Y position in µm")
    peak_position_z: Optional[float] = Field(default=None, description="Peak Z position in µm (focus mode only)")

    # Execution metadata
    execution_time: Optional[float] = Field(default=None, description="Total execution time in seconds")

    # Profile data retrieved from controller (populated on success)
    # Each profile contains data from different phases: field search, peak search X/Y/Z
    field_search_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="Field search profile data points"
    )
    peak_search_x_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="X-axis peak search profile data points"
    )
    peak_search_y_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="Y-axis peak search profile data points"
    )
    peak_search_z_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="Z-axis peak search profile data points (focus mode only)"
    )

    # Error information (populated when success=False)
    error_message: Optional[str] = Field(default=None, description="Detailed error message if alignment failed")


# ========== Profile Models ==========

class ProfileParameterModel(BaseModel):
    """
    Profile measurement parameter based on ProfileParameter structure from manual.
    Used to configure profile measurement with the Profile Class API.
    """
    main_axis_number: int = Field(ge=1, le=12, description="Main axis number")
    sub1_axis_number: int = Field(default=0, ge=0, le=12, description="Sub-axis1 number, 0: None")
    sub2_axis_number: int = Field(default=0, ge=0, le=12, description="Sub-axis2 number, 0: None")
    signal_ch1_number: int = Field(ge=1, description="Ch1 signal axis number (analog channel)")
    signal_ch2_number: int = Field(default=0, ge=0, description="Ch2 signal axis number, 0: None")
    main_range: float = Field(gt=0, description="Main axis profile measurement range [µm or deg]")
    sub1_range: float = Field(default=0.0, ge=0, description="Sub-axis1 profile measurement range [µm or deg]")
    sub2_range: float = Field(default=0.0, ge=0, description="Sub-axis2 profile measurement range [µm or deg]")
    speed: float = Field(gt=0, description="Axis speed [µm/s or deg/s]")
    accel_rate: float = Field(gt=0, description="Axis acceleration [µm/s² or deg/s²]")
    decel_rate: float = Field(gt=0, description="Axis deceleration [µm/s² or deg/s²]")
    smoothing: int = Field(default=0, ge=0, description="Smoothing range [samples]")


class ProfileStatus(BaseModel):
    """Profile measurement status"""
    status: str = Field(description="Status: idle, running, completed, error")
    error_code: int = Field(default=0, description="Error code if error occurred")
    error_message: str = Field(default="", description="Error message if error occurred")


class ProfileDataResponse(BaseModel):
    """
    Complete profile measurement data with peak detection.
    Enhanced to include peak position and value extraction.
    """
    success: bool = Field(description="True if measurement succeeded")
    
    # Data fields (null if measurement failed)
    data_points: Optional[List[ProfileDataPoint]] = Field(default=None, description="List of measured data points (null if failed)")
    total_points: Optional[int] = Field(default=None, description="Total number of data points (null if failed)")

    # Peak information (null if measurement failed)
    peak_position: Optional[float] = Field(default=None, description="Position where maximum signal occurred [µm or deg] (null if failed)")
    peak_value: Optional[float] = Field(default=None, description="Maximum signal value detected (null if failed)")
    peak_index: Optional[int] = Field(default=None, description="Index in the data array where peak occurred (null if failed)")

    # Measurement metadata (always populated)
    main_axis_number: int = Field(description="Main axis number used")
    main_axis_initial_position: Optional[float] = Field(default=None, description="Actual position of main axis at start of scan [µm or deg] (null if failed before start)")
    main_axis_final_position: Optional[float] = Field(default=None, description="Actual position of main axis at end of scan [µm or deg] (null if failed)")
    signal_ch_number: int = Field(description="Signal channel number used")
    scan_range: float = Field(description="Scan range [µm or deg]")
    scan_speed: float = Field(description="Scan speed [µm/s or deg/s]")
    
    # Error information (populated when success=False)
    error_code: Optional[str] = Field(default=None, description="Error code if measurement failed")
    error_value: Optional[int] = Field(default=None, description="Error numeric value if measurement failed")
    error_description: Optional[str] = Field(default=None, description="Error description if measurement failed")
    status_code: Optional[str] = Field(default=None, description="Final status code if measurement failed during execution")
    status_value: Optional[int] = Field(default=None, description="Final status numeric value if measurement failed during execution")
    status_description: Optional[str] = Field(default=None, description="Final status description if measurement failed during execution")


class ProfileMeasurementRequest(BaseModel):
    """
    Request to execute a profile measurement scan.
    All parameters from ProfileParameter structure must be specified.

    IMPORTANT: Profile measurement scans ONE axis at a time and returns position
    data for that axis only. The sub-axis parameters (sub1_axis_number, sub2_axis_number)
    are for motion control during the scan (e.g., maintaining position on other axes),
    NOT for collecting multi-axis position data.

    For multi-axis (X,Y) profile data collection, use the Optical Alignment API instead,
    which provides separate profile datasets for FieldSearch, PeakSearchX, and PeakSearchY.

    For typical stage configurations:
    - Left stage: X1=1, Y1=2, Z1=3
    - Right stage: X2=7, Y2=8, Z2=9

    Note: scan_axis is restricted to linear axes (1, 2, 3, 7, 8, 9) only.
    Rotational axes (4, 5, 6, 10, 11, 12) which correspond to Tx, Ty, Tz
    are not allowed for profile measurements as a safety measure.
    """
    # Main axis parameters
    scan_axis: int = Field(default=1, ge=1, le=12, description="Main axis to scan (mainAxisNumber) - restricted to linear axes only: 1, 2, 3, 7, 8, 9")
    scan_range: float = Field(default=20.0, gt=0, description="Main axis scan range in µm (mainRange)")

    # Sub-axis parameters (for motion control, not data collection)
    sub1_axis_number: int = Field(default=0, ge=0, le=12, description="Sub-axis 1 (Y) number for motion control, 0 for None (sub1AxisNumber)")
    sub2_axis_number: int = Field(default=0, ge=0, le=12, description="Sub-axis 2 (Z) number for motion control, 0 for None (sub2AxisNumber)")
    sub1_range: float = Field(default=0.0, ge=0, description="Sub-axis 1 (Y) motion range in µm, 0 to disable (sub1Range)")
    sub2_range: float = Field(default=0.0, ge=0, description="Sub-axis 2 (Z) motion range in µm, 0 to disable (sub2Range)")

    # Signal parameters
    signal_ch1_number: int = Field(default=1, ge=1, le=12, description="Signal channel 1 number (analog channel to monitor)")
    signal_ch2_number: int = Field(default=0, ge=0, le=12, description="Signal channel 2 number, 0 for None (signalCh2Number)")

    # Motion parameters
    scan_speed: float = Field(default=25.0, gt=0, description="Scan speed in µm/s (speed)")
    accel_rate: float = Field(default=1000.0, gt=0, description="Acceleration rate in µm/s² (accelRate)")
    decel_rate: float = Field(default=1000.0, gt=0, description="Deceleration rate in µm/s² (decelRate)")
    smoothing: int = Field(default=10, ge=0, description="Smoothing range in samples")

    @field_validator('scan_axis')
    @classmethod
    def validate_scan_axis(cls, v: int) -> int:
        """
        Validate that scan_axis is a linear axis only.
        Allowed axes: 1, 2, 3, 7, 8, 9
        Disallowed axes: 4, 5, 6, 10, 11, 12 (rotational axes Tx, Ty, Tz)
        """
        allowed_axes = {1, 2, 3, 7, 8, 9}
        if v not in allowed_axes:
            raise ValueError(
                f"scan_axis must be one of {sorted(allowed_axes)} (linear axes only). "
                f"Rotational axes (Tx, Ty, Tz) are not allowed for profile measurements. "
                f"Got: {v}"
            )
        return v


# ========== Angle Adjustment Models ==========

class AngleAdjustmentRequest(BaseModel):
    """
    Request to execute angle adjustment.

    Stage-specific hardware parameters (signal channels, axis mappings) are
    auto-determined based on stage selection. Only variable parameters need
    to be specified.
    """
    # Stage selection (determines hardware configuration)
    stage: AngleAdjustmentStage = Field(description="Stage to adjust (LEFT or RIGHT)")

    # Basic parameters
    gap: float = Field(default=4.0, ge=0, description="Gap distance in µm after angle adjustment")
    signal_lower_limit: float = Field(default=0.4, ge=0, description="Signal lower limit threshold")

    # Unlock control parameters
    unlock_dout_control_on: bool = Field(default=False, description="Enable unlock digital output control")
    lock_unlock_adjust_enable: bool = Field(default=False, description="Enable lock/unlock adjustment")
    lock_unlock_difference: float = Field(default=0.0, ge=0, description="Lock/unlock difference threshold")

    # Contact detection parameters
    contact_search_range: float = Field(default=5000.0, gt=0, description="Contact search range in µm")
    contact_search_speed: float = Field(default=100.0, gt=0, description="Contact search speed in µm/s")
    contact_smoothing: int = Field(default=10, ge=0, description="Contact smoothing samples")
    contact_sensitivity: int = Field(default=5, ge=0, description="Contact sensitivity")
    push_distance: float = Field(default=20.0, ge=0, description="Push distance after contact in µm")

    # Angle adjustment axes (0 = disabled)
    angle_axis_number_tx: int = Field(default=0, ge=0, description="Tx angle axis number (0 = disabled)")
    angle_axis_number_ty: int = Field(default=0, ge=0, description="Ty angle axis number (0 = disabled)")

    # Angle search ranges - non-zero required for API validation
    angle_search_range_tx: float = Field(default=5.0, ge=0, description="Tx angle search range in degrees")
    angle_search_range_ty: float = Field(default=5.0, ge=0, description="Ty angle search range in degrees")

    # Angle search speeds - non-zero required for API validation
    angle_search_speed_tx: float = Field(default=1.0, ge=0, description="Tx angle search speed in deg/s")
    angle_search_speed_ty: float = Field(default=1.0, ge=0, description="Ty angle search speed in deg/s")

    # Angle smoothing
    angle_smoothing_tx: int = Field(default=30, ge=0, description="Tx angle smoothing samples")
    angle_smoothing_ty: int = Field(default=30, ge=0, description="Ty angle smoothing samples")

    # Angle sensitivity
    angle_sensitivity_tx: int = Field(default=5, ge=0, description="Tx angle sensitivity")
    angle_sensitivity_ty: int = Field(default=5, ge=0, description="Ty angle sensitivity")

    # Angle judge counts (0 = disabled)
    angle_judge_count_tx: int = Field(default=2, ge=0, description="Tx angle judge count (0 = disabled)")
    angle_judge_count_ty: int = Field(default=2, ge=0, description="Ty angle judge count (0 = disabled)")

    # Angle convergence (0 = disabled)
    angle_convergent_range_tx: float = Field(default=0.05, ge=0, description="Tx convergence range in degrees (0 = disabled)")
    angle_convergent_range_ty: float = Field(default=0.05, ge=0, description="Ty convergence range in degrees (0 = disabled)")

    # Adjustment limits (0 = disabled)
    angle_comparison_count: int = Field(default=2, ge=0, description="Angle comparison count (0 = disabled)")
    angle_max_count: int = Field(default=5, ge=0, description="Maximum adjustment iteration count (0 = disabled)")

    # Rotation center parameters
    rotation_center_enabled: bool = Field(default=False, description="Enable rotation center mode")


class AngleAdjustmentResponse(BaseModel):
    """
    Response from angle adjustment execution.
    Following the pattern from AlignmentResponse with signal measurements instead of power.
    """
    success: bool = Field(description="True if adjustment completed successfully")

    # Status information (always populated)
    status_code: Optional[str] = Field(default=None, description="Final status code from AngleAdjustmentStatus")
    status_value: Optional[int] = Field(default=None, description="Final status numeric value")
    status_description: Optional[str] = Field(default=None, description="Final status description")

    # Phase information (populated when available)
    phase_code: Optional[str] = Field(default=None, description="Last phase code from AdjustingStatus")
    phase_value: Optional[int] = Field(default=None, description="Last phase numeric value")
    phase_description: Optional[str] = Field(default=None, description="Last phase description")

    # Signal measurements (populated on success)
    initial_signal: Optional[float] = Field(default=None, description="Initial analog signal value before adjustment")
    final_signal: Optional[float] = Field(default=None, description="Final analog signal value after adjustment")
    signal_improvement: Optional[float] = Field(default=None, description="Signal improvement (final - initial)")

    # Execution metadata
    execution_time: Optional[float] = Field(default=None, description="Total execution time in seconds")

    # Profile data retrieved from controller (populated on success)
    # Each profile contains data from different phases: ContactZ, AdjustingTx, AdjustingTy
    contact_z_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="Contact Z detection profile data points"
    )
    adjusting_tx_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="TX angle adjustment profile data points"
    )
    adjusting_ty_profile: Optional[List[ProfileDataPoint]] = Field(
        default=None,
        description="TY angle adjustment profile data points"
    )

    # Error information (populated when success=False)
    error_message: Optional[str] = Field(default=None, description="Detailed error message if adjustment failed")


class StopAngleAdjustmentRequest(BaseModel):
    """Request to stop a running angle adjustment."""
    stage: AngleAdjustmentStage = Field(description="Stage to stop (LEFT or RIGHT)")


# ========== I/O Models ==========

class DigitalOutputRequest(BaseModel):
    channel: int = Field(ge=1, le=2, description="Digital output channel number (1=Left, 2=Right)")
    value: bool = Field(description="Output value: True for LOCKED, False for UNLOCKED")


# ========== Task Management Models ==========

class TaskStatusEnum(str, Enum):
    """Status of a task."""
    PENDING = "pending"
    RUNNING = "running"
    STOPPING = "stopping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OperationTypeEnum(str, Enum):
    """Types of operations that can be executed as tasks."""
    ANGLE_ADJUSTMENT = "angle_adjustment"
    FLAT_ALIGNMENT = "flat_alignment"
    FOCUS_ALIGNMENT = "focus_alignment"
    PROFILE_MEASUREMENT = "profile_measurement"
    AXIS_MOVEMENT = "axis_movement"


class TaskResponse(BaseModel):
    """Response when a task is created (202 Accepted)."""
    task_id: str = Field(description="Unique task identifier")
    operation_type: str = Field(description="Type of operation (angle_adjustment, flat_alignment, etc.)")
    status: str = Field(description="Current task status")
    status_url: str = Field(description="URL to poll for task status")
    message: str = Field(default="Task created and execution started", description="Human-readable message")


class TaskStatusResponse(BaseModel):
    """Complete task status information."""
    task_id: str = Field(description="Unique task identifier")
    operation_type: str = Field(description="Type of operation")
    status: str = Field(description="Current task status")
    progress: dict = Field(default_factory=dict, description="Operation-specific progress data")
    result: Optional[dict] = Field(default=None, description="Result data when task completes")
    error: Optional[str] = Field(default=None, description="Error message if task failed")
    created_at: Optional[str] = Field(default=None, description="ISO timestamp when task was created")
    started_at: Optional[str] = Field(default=None, description="ISO timestamp when task execution started")
    completed_at: Optional[str] = Field(default=None, description="ISO timestamp when task finished")


class TaskProgressMessage(BaseModel):
    """WebSocket message for task progress updates."""
    type: str = Field(default="task_progress", description="Message type")
    task_id: str = Field(description="Task identifier")
    operation_type: str = Field(description="Type of operation")
    status: str = Field(description="Current task status")
    progress: dict = Field(description="Progress data specific to operation type")
