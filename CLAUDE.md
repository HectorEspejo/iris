# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ClubAI is a distributed AI inference network where users pay a monthly fee for access, contribute compute nodes running LM Studio, and earn rewards based on reputation. The system uses a central coordinator architecture with WebSocket-connected node agents.

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start coordinator (with hot reload)
python -m uvicorn coordinator.main:app --host 0.0.0.0 --port 8000 --reload

# Start node agent
export NODE_ID="my-node-1"
export COORDINATOR_URL="ws://localhost:8000/nodes/connect"
export LMSTUDIO_URL="http://localhost:1234/v1"
python -m node_agent.main

# CLI commands
python -m client.cli register --email user@example.com --password mypassword
python -m client.cli login --email user@example.com --password mypassword
python -m client.cli ask "Your prompt here"
python -m client.cli stats
python -m client.cli nodes
python -m client.cli reputation

# Docker deployment
docker-compose up -d
docker-compose logs -f coordinator
```

## Testing

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_crypto.py -v

# Run with coverage
pytest tests/ --cov=coordinator --cov=node_agent --cov=shared
```

Tests use `pytest-asyncio` fixtures for async database operations and create temporary SQLite databases.

## Architecture

```
coordinator/          # Central FastAPI server
├── main.py          # FastAPI app, REST routes, WebSocket /nodes/connect endpoint
├── database.py      # SQLite schema and async operations (aiosqlite)
├── auth.py          # JWT authentication, bcrypt password hashing
├── node_registry.py # Connected node management, heartbeat tracking
├── task_orchestrator.py  # Task division into subtasks, node assignment
├── response_aggregator.py # Combines subtask results
├── reputation.py    # Node reputation scoring
├── economics.py     # Monthly pool distribution
└── crypto.py        # Coordinator-side encryption

node_agent/          # Distributed node agents
├── main.py          # WebSocket connection to coordinator
├── lmstudio_client.py # LM Studio API client
├── crypto.py        # Node-side encryption
└── heartbeat.py     # Periodic heartbeat sender

client/              # User interfaces
├── cli.py           # Typer CLI with Rich output
└── sdk.py           # AsyncClubAIClient for programmatic access

shared/              # Shared between all components
├── models.py        # Pydantic models (User, Node, Task, Subtask)
├── protocol.py      # WebSocket message types (NODE_REGISTER, TASK_ASSIGN, etc.)
└── crypto_utils.py  # X25519 key exchange, AES-256-GCM encryption
```

### Communication Flow

1. Nodes connect via WebSocket to `/nodes/connect` and register with `NODE_REGISTER`
2. Users submit requests via REST `POST /inference`
3. `task_orchestrator.py` divides work and sends `TASK_ASSIGN` to nodes
4. Nodes process via LM Studio and return `TASK_RESULT`
5. `response_aggregator.py` combines results and returns to user

### Task Division Modes

- **Subtasks**: Divide complex tasks into independent parts
- **Consensus**: Same task to multiple nodes for verification
- **Context**: Split long documents across nodes

### Cryptography

All payloads are encrypted end-to-end using:
- X25519 for key exchange (Diffie-Hellman)
- AES-256-GCM for symmetric encryption
- Keys are persisted to `data/*.key` files

## Key Environment Variables

**Coordinator:**
- `DATABASE_URL` - SQLite path (default: `sqlite:///data/clubai.db`)
- `JWT_SECRET` - JWT signing secret
- `COORDINATOR_PRIVATE_KEY_PATH` - Key file path

**Node Agent:**
- `NODE_ID` - Unique node identifier
- `COORDINATOR_URL` - WebSocket URL
- `LMSTUDIO_URL` - LM Studio API URL (default: `http://localhost:1234/v1`)
- `NODE_VRAM_GB` - Available VRAM in GB

## Reputation System

Nodes start at 100 points (minimum 10). Key changes:
- Task completed: +10, Fast completion: +5
- Task timeout: -20, Invalid response: -50
- Uptime: +1/hour, Broken promise: -5/hour
- Weekly decay: -1%
