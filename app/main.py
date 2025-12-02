"""
Suruga Seiki EW51 Probe Station Daemon
FastAPI application providing REST and WebSocket interfaces for probe station control
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .routers import connection, servo, motion, position, alignment, profile, io, websocket, angle_adjustment
from .config import settings
from .factory import create_controller

if TYPE_CHECKING:
    from .controller_manager import SurugaSeikiController
    from .mock_controller import MockSurugaSeikiController

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Global controller instance
controller: Optional["SurugaSeikiController | MockSurugaSeikiController"] = None
# Shutdown flag to stop background tasks gracefully
is_shutting_down = False


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error broadcasting to WebSocket: {e}")


manager = ConnectionManager()


# Background task for streaming positions and IO data
async def position_streaming_task():
    """Continuously stream position and IO data updates via WebSocket"""
    while not is_shutting_down:
        try:
            if controller and controller.is_connected() and manager.active_connections:
                # Get all data from controller
                positions = controller.get_all_positions()
                digital_outputs = controller.get_all_digital_outputs()
                analog_inputs = controller.get_all_analog_inputs()

                # Get power meter reading if enabled
                power_value = None
                if settings.power_meter_streaming_enabled:
                    power_value = controller.get_power(settings.power_meter_channel)

                # Convert to serializable format using Pydantic's dict() method
                position_data = {
                    "type": "position_update",
                    "timestamp": datetime.now().isoformat(),
                    "positions": {
                        axis_num: pos.dict() if hasattr(pos, 'dict') else pos.model_dump()
                        for axis_num, pos in positions.items()
                    },
                    "digital_outputs": digital_outputs,
                    "analog_inputs": analog_inputs,
                    "power_meter": {
                        "channel": settings.power_meter_channel,
                        "value_dbm": power_value,
                        "enabled": settings.power_meter_streaming_enabled
                    }
                }

                await manager.broadcast(position_data)

            await asyncio.sleep(1.0 / settings.ws_update_rate_hz)  # Configurable update rate
        except Exception as e:
            if not is_shutting_down:
                logger.error(f"Error in position streaming task: {e}")
            await asyncio.sleep(1)

    logger.info("Position streaming task stopped")


# Background task for connection health monitoring
async def connection_health_task():
    """
    Monitor connection health and attempt automatic reconnection.
    Broadcasts connection status changes to WebSocket clients.
    """
    last_connection_state = None

    while not is_shutting_down:
        try:
            if controller:
                current_state = controller.is_connected()

                # Detect state change
                if current_state != last_connection_state:
                    if current_state:
                        logger.info("Connection established")
                        await manager.broadcast({
                            "type": "connection_status",
                            "connected": True,
                            "timestamp": datetime.now().isoformat(),
                            "message": "Connected to Suruga Seiki controller"
                        })
                    else:
                        logger.warning("Connection lost")
                        await manager.broadcast({
                            "type": "connection_status",
                            "connected": False,
                            "timestamp": datetime.now().isoformat(),
                            "message": "Disconnected from controller"
                        })

                    last_connection_state = current_state

                # Attempt reconnection if disconnected (but not during shutdown)
                if not current_state and not is_shutting_down:
                    logger.info("Attempting automatic reconnection...")
                    try:
                        success = controller.connect()
                        if success:
                            logger.info("Automatic reconnection successful")
                            await manager.broadcast({
                                "type": "connection_status",
                                "connected": True,
                                "timestamp": datetime.now().isoformat(),
                                "message": "Automatically reconnected to controller"
                            })
                            last_connection_state = True
                        else:
                            logger.debug("Reconnection attempt failed, will retry...")
                    except Exception as e:
                        logger.debug(f"Reconnection attempt error: {e}")

            await asyncio.sleep(5.0)  # Check every 5 seconds

        except Exception as e:
            if not is_shutting_down:
                logger.error(f"Error in connection health task: {e}", exc_info=True)
            await asyncio.sleep(5.0)
    
    logger.info("Connection health monitoring task stopped")


# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup on startup/shutdown"""
    global controller, is_shutting_down

    logger.info("Starting Suruga Seiki EW51 Daemon...")
    logger.info(f"Default ADS address: {settings.ads_address}")
    logger.info(f"MOCK MODE: {'ENABLED' if settings.mock_mode else 'DISABLED'}")
    controller = create_controller()

    # Optionally auto-connect to the machine on startup
    if settings.auto_connect_on_start:
        try:
            success = controller.connect()
            if success:
                logger.info("Auto-connect on startup: connected to probe station")
            else:
                logger.warning("Auto-connect on startup failed; API is still running for manual connect")
        except Exception as e:
            logger.error(f"Auto-connect encountered an error: {e}")

    # Start background tasks
    asyncio.create_task(position_streaming_task())
    asyncio.create_task(connection_health_task())
    logger.info("Background tasks started (position + IO streaming, connection health monitoring)")

    yield

    # Cleanup
    logger.info("Shutting down Suruga Seiki EW51 Daemon...")
    is_shutting_down = True  # Signal background tasks to stop
    
    # Give background tasks a moment to finish
    await asyncio.sleep(0.5)
    
    # Notify all WebSocket clients about shutdown
    if manager.active_connections:
        shutdown_message = {
            "type": "server_shutdown",
            "message": "Suruga Seiki daemon is shutting down",
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast(shutdown_message)
        
        # Close all WebSocket connections gracefully with custom message
        for connection in manager.active_connections[:]:  # Copy list to avoid modification during iteration
            try:
                await connection.close(code=1012, reason="Suruga Seiki daemon shutting down")
            except Exception as e:
                logger.warning(f"Error closing WebSocket connection: {e}")
        
        manager.active_connections.clear()
        logger.info("All WebSocket connections closed")
    
    # Disconnect from hardware
    if controller and controller.is_connected():
        controller.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Suruga Seiki EW51 Probe Station API",
    description="REST and WebSocket API for Suruga Seiki DA1000/DA1100 probe station control",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== Root Endpoints ==========

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Suruga Seiki EW51 Probe Station Daemon",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


# ========== Include Routers ==========

app.include_router(connection.router)
app.include_router(servo.router)
app.include_router(motion.router)
app.include_router(position.router)
app.include_router(alignment.router)
app.include_router(profile.router)
app.include_router(angle_adjustment.router)
app.include_router(io.router)
app.include_router(websocket.router)


# ========== Main Entry Point ==========

def run():
    """Entry point for the console script"""
    logger.info(f"Starting daemon on {settings.host}:{settings.port}")
    logger.info(f"WebSocket update rate: {settings.ws_update_rate_hz} Hz")
    uvicorn.run(
        "instruments.suruga_seiki_ew51.daemon.app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.reload
    )


if __name__ == "__main__":
    run()
