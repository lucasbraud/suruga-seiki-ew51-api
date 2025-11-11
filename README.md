# Suruga Seiki EW51 Probe Station API

FastAPI server for controlling Suruga Seiki DA1000/DA1100 probe stations via .NET DLL interop.

## Features

- 12-axis motion control (single/2D/3D interpolation)
- Optical alignment (flat 2D, focus 3D)
- Profile measurement scanning
- Angle adjustment (DA1100 only)
- I/O control (contact sensors, power meters)
- Real-time WebSocket streaming
- Health monitoring with auto-reconnection

## Requirements

- Python 3.10+
- Windows (for .NET DLL support via pythonnet)
- Suruga Seiki DA1000 or DA1100 hardware

## Installation

Install uv here : https://docs.astral.sh/uv/getting-started/installation/

```bash
# Clone repository
git clone <repo-url>
cd suruga-seiki-ew51-api

# Install dependencies
uv sync

# Activate virtual environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows
```

## Usage

```bash
# Development mode
fastapi dev app/main.py

# Production mode
fastapi run app/main.py --host 0.0.0.0 --port 8001
```

Server runs on: http://localhost:8001

API Documentation:
- **Swagger UI:** http://localhost:8001/docs
- **ReDoc:** http://localhost:8001/redoc

## Configuration

Create `.env` file:

```env
SURUGA_AUTO_CONNECT=true
SURUGA_CONNECTION_STRING=<your-connection-string>
API_HOST=0.0.0.0
API_PORT=8001
LOG_LEVEL=INFO
```

## Development

```bash
# Run tests
pytest

# Format code
ruff format app/

# Lint code
ruff check app/

# Type check
mypy app/
```

## Docker

```bash
# Build
docker build -t suruga-api .

# Run
docker run -p 8001:8001 suruga-api
```

## Examples

The `examples/` directory contains usage examples:
- `test_flat_alignment.py` - 2D optical alignment demonstration
- `test_profile_measurement.py` - Profile scanning example
- `test_angle_adjustment.py` - Angle adjustment example (DA1100 only)

Run examples:
```bash
python examples/test_flat_alignment.py
```

## API Endpoints

See `/docs` for full API documentation.

### Key Endpoints:
- `POST /connect` - Connect to hardware
- `POST /servo/turn_on` - Activate servo
- `POST /motion/move_absolute` - Move to position
- `GET /position/{axis}` - Query position
- `POST /alignment/flat` - 2D alignment
- `POST /alignment/focus` - 3D alignment
- `WS /ws/position_stream` - Real-time streaming

## License

MIT

