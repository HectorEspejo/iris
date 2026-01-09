# Iris - Distributed AI Inference Network

A distributed AI inference network where members pay a monthly fee for access, contribute compute nodes running LM Studio, and earn rewards based on reputation.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      COORDINATOR SERVER                         │
│                                                                 │
│  • API Gateway (REST endpoints for users)                       │
│  • Node Registry (WebSocket connections)                        │
│  • Task Orchestrator (divides & assigns work)                   │
│  • Response Aggregator (combines results)                       │
│  • Reputation System                                            │
│  • Economics Module                                             │
└─────────────────────────────────────────────────────────────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
     ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
     │ Node 1 │    │ Node 2 │    │ Node 3 │    │ Node N │
     │LM Studio    │LM Studio    │LM Studio    │LM Studio
     │ + Agent │   │ + Agent │   │ + Agent │   │ + Agent │
     └────────┘    └────────┘    └────────┘    └────────┘
```

## Features

- **Distributed Inference**: Tasks are divided and processed across multiple nodes
- **E2E Encryption**: All communication uses X25519 + AES-256-GCM
- **Reputation System**: Nodes earn reputation for reliable performance
- **Economic Model**: Monthly pool distributed based on reputation
- **Task Division Modes**:
  - **Subtasks**: Divide complex tasks into independent parts
  - **Consensus**: Same task to multiple nodes for verification
  - **Context**: Split long documents across nodes
- **Web Dashboard**: Real-time monitoring of network status

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- LM Studio (running with a loaded model)

### 1. Clone and Install

```bash
cd clubai
pip install -r requirements.txt
```

### 2. Start the Coordinator

```bash
# Using Python directly
python -m uvicorn coordinator.main:app --host 0.0.0.0 --port 8000 --reload

# Or using Docker
docker-compose up coordinator
```

### 3. Start LM Studio

1. Open LM Studio
2. Load a model (e.g., Llama 3.2 3B)
3. Start the local server on port 1234

### 4. Start a Node Agent

```bash
# Set environment variables
export NODE_ID="my-node-1"
export COORDINATOR_URL="ws://localhost:8000/nodes/connect"
export LMSTUDIO_URL="http://localhost:1234/v1"

# Run the agent
python -m node_agent.main
```

### 5. Use the CLI

```bash
# Register a new account
python -m client.cli register --email user@example.com --password mypassword

# Login
python -m client.cli login --email user@example.com --password mypassword

# Send an inference request
python -m client.cli ask "Analyze this text and extract: themes, characters, and conclusions"

# Check network status
python -m client.cli stats
python -m client.cli nodes
python -m client.cli reputation
```

## Docker Deployment

Start the full stack with Docker Compose:

```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f coordinator
docker-compose logs -f node1

# Stop all services
docker-compose down
```

The coordinator will be available at http://localhost:8000

## API Reference

### Authentication

```
POST /auth/register    - Register new user
POST /auth/login       - Login, returns JWT
GET  /auth/me          - Get current user info
```

### Inference

```
POST /inference            - Submit inference request
GET  /inference/{task_id}  - Get task status
```

### Network Info

```
GET  /stats           - Network statistics
GET  /reputation      - Node leaderboard
GET  /nodes           - Active nodes (authenticated)
GET  /history         - Task history (authenticated)
```

### Dashboard

```
GET  /dashboard       - Web dashboard (HTML)
```

## Configuration

### Coordinator Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///data/clubai.db` | Database path |
| `JWT_SECRET` | `dev-secret-...` | JWT signing secret |
| `COORDINATOR_PRIVATE_KEY_PATH` | `data/coordinator.key` | Key file path |

### Node Agent Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | `node-{pid}` | Unique node identifier |
| `COORDINATOR_URL` | `ws://localhost:8000/nodes/connect` | Coordinator WebSocket URL |
| `LMSTUDIO_URL` | `http://localhost:1234/v1` | LM Studio API URL |
| `NODE_KEY_PATH` | `data/node.key` | Node private key path |
| `NODE_VRAM_GB` | `8` | Available VRAM (GB) |

## Project Structure

```
clubai/
├── coordinator/          # Central coordinator server
│   ├── main.py          # FastAPI application
│   ├── auth.py          # JWT authentication
│   ├── database.py      # SQLite operations
│   ├── node_registry.py # Node management
│   ├── task_orchestrator.py
│   ├── response_aggregator.py
│   ├── reputation.py
│   ├── economics.py
│   ├── crypto.py
│   └── dashboard.py
│
├── node_agent/          # Node agent
│   ├── main.py          # Agent entry point
│   ├── lmstudio_client.py
│   ├── crypto.py
│   └── heartbeat.py
│
├── client/              # CLI and SDK
│   ├── cli.py           # Typer CLI
│   └── sdk.py           # Python SDK
│
├── shared/              # Shared models and utilities
│   ├── models.py        # Pydantic models
│   ├── protocol.py      # WebSocket protocol
│   └── crypto_utils.py  # Encryption utilities
│
├── tests/               # Test suite
├── docker-compose.yml
└── requirements.txt
```

## Reputation System

Nodes earn/lose reputation based on performance:

| Event | Points |
|-------|--------|
| Task completed | +10 |
| Fast completion bonus | +5 |
| Task timeout | -20 |
| Invalid response | -50 |
| Uptime (per hour) | +1 |
| Broken availability promise | -5/hour |
| Weekly decay | -1% |

Minimum reputation: 10 points

## Economic Model

Monthly pool distribution:
- Each node's share = (node_reputation / total_reputation) * pool
- Distribution happens at end of month
- Reputation snapshot taken at distribution time

## Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_crypto.py -v

# Run with coverage
pytest tests/ --cov=coordinator --cov=node_agent --cov=shared
```

## Security

- All prompts and responses are encrypted end-to-end
- X25519 for key exchange
- AES-256-GCM for symmetric encryption
- JWT tokens for user authentication
- Passwords hashed with bcrypt

## Roadmap

### v1.0 (Current MVP)
- [x] Central coordinator
- [x] Node registration and heartbeat
- [x] Task division (Mode 2 - Subtasks)
- [x] E2E encryption
- [x] Reputation system
- [x] Basic economics
- [x] CLI client
- [x] Web dashboard

### v2.0 (Future)
- [ ] P2P node discovery
- [ ] Multi-party computation for privacy
- [ ] Consensus mode implementation
- [ ] Context division mode
- [ ] Payment integration
- [ ] Mobile app

## License

MIT License

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.
