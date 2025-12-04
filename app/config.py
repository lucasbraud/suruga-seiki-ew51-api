"""
Configuration management using pydantic-settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class DaemonSettings(BaseSettings):
    """Daemon configuration settings"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="SURUGA_",
        case_sensitive=False
    )

    # Connection settings
    ads_address: str = Field(
        default="5.146.68.190.1.1",
        description="ADS address of the probe station (format: x.x.x.x.x.x)"
    )
    mock_mode: bool = Field(
        default=False,
        description="Enable mock mode for development without physical hardware"
    )

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8001, description="Server port")
    log_level: str = Field(default="info", description="Logging level")
    reload: bool = Field(default=False, description="Enable auto-reload on code changes")

    # WebSocket settings
    ws_update_rate_hz: float = Field(
        default=10.0,
        ge=1.0,
        le=100.0,
        description="WebSocket position update rate in Hz"
    )

    # Auto-connect behavior
    auto_connect_on_start: bool = Field(
        default=True,
        description="Automatically connect to the probe station during daemon startup"
    )

    # Timeout settings
    connection_timeout_s: float = Field(
        default=5.0,
        description="Connection timeout in seconds"
    )
    movement_timeout_s: float = Field(
        default=60.0,
        description="Default movement timeout in seconds"
    )

    # Safety settings
    auto_disconnect_on_error: bool = Field(
        default=True,
        description="Automatically disconnect on system error"
    )
    servo_off_on_disconnect: bool = Field(
        default=True,
        description="Turn off all servos when disconnecting"
    )

    # Power meter settings
    power_meter_channel: int = Field(
        default=1,
        ge=1,
        le=2,
        description="Power meter channel number for streaming (1 or 2)"
    )
    power_meter_streaming_enabled: bool = Field(
        default=True,
        description="Enable power meter value streaming via WebSocket"
    )


# Global settings instance
settings = DaemonSettings()
