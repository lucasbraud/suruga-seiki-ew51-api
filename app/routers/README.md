# API Routers

This directory contains the organized API endpoints for the Suruga Seiki EW51 daemon, separated by functionality.

## Structure

```
routers/
├── __init__.py          # Package initialization
├── connection.py        # Connection and status endpoints
├── servo.py             # Servo control endpoints
├── motion.py            # Motion control (single axis, 2D, 3D)
├── position.py          # Position query endpoints
├── alignment.py         # Alignment routine endpoints
├── profile.py           # Profile measurement endpoints
├── io.py                # Digital and analog I/O endpoints
└── websocket.py         # WebSocket streaming endpoint
```

## Router Details

### connection.py
- `POST /connection/connect` - Connect to probe station
- `POST /connection/disconnect` - Disconnect from probe station
- `GET /connection/status` - Get system status and error information

### servo.py
- `POST /servo/on` - Turn on servo for specified axis
- `POST /servo/off` - Turn off servo for specified axis

### motion.py
- `POST /move/absolute` - Move axis to absolute position
- `POST /move/relative` - Move axis relative to current position
- `POST /move/stop` - Stop movement of specified axis
- `POST /move/emergency_stop` - Emergency stop all axes
- `POST /move/2d` - Execute 2D interpolation movement
- `POST /move/3d` - Execute 3D interpolation movement

### position.py
- `GET /position/{axis_number}` - Get position and status for one axis
- `GET /position/all` - Get positions for all axes

### alignment.py
- `POST /alignment/run` - Execute automated alignment routine

### profile.py
- `POST /profile/measure` - Execute profile measurement scan

### io.py
- `POST /io/digital/output` - Set digital output value
- `GET /io/digital/input/{channel}` - Get digital input value
- `POST /io/analog/output` - Set analog output voltage
- `GET /io/analog/input/{channel}` - Get analog input voltage

### websocket.py
- `WebSocket /ws` - Real-time position streaming (10Hz)

## Usage in main.py

All routers are imported and included in the main FastAPI application:

```python
from routers import connection, servo, motion, position, alignment, profile, io, websocket

app.include_router(connection.router)
app.include_router(servo.router)
app.include_router(motion.router)
app.include_router(position.router)
app.include_router(alignment.router)
app.include_router(profile.router)
app.include_router(io.router)
app.include_router(websocket.router)
```

## Adding New Endpoints

To add new functionality:

1. Create a new router file in this directory
2. Define your router with prefix and tags:
   ```python
   from fastapi import APIRouter

   router = APIRouter(prefix="/your_prefix", tags=["Your Tag"])
   ```
3. Import the controller:
   ```python
   def get_controller():
       from main import controller
       return controller
   ```
4. Define your endpoints
5. Import and include the router in `main.py`:
   ```python
   from routers import your_router
   app.include_router(your_router.router)
   ```

## Benefits of This Structure

- **Separation of Concerns**: Each router handles a specific domain
- **Maintainability**: Easy to locate and modify specific functionality
- **Scalability**: Simple to add new features without cluttering main.py
- **Testing**: Individual routers can be tested in isolation
- **Documentation**: Swagger UI automatically groups endpoints by tags
