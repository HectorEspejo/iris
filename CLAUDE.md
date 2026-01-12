# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Iris is a distributed AI inference network where users contribute compute nodes running LM Studio and earn rewards based on reputation. The system uses a central coordinator architecture with WebSocket-connected node agents. Features include:

- **Mullvad-style Account Keys**: 16-digit anonymous account keys for authentication
- **Node Tier System**: Automatic classification of nodes (BASIC, MID, PRO) based on hardware
- **Task Difficulty Classification**: Automatic routing via OpenRouter API (SIMPLE, COMPLEX, ADVANCED)
- **Real-time Streaming**: SSE-based streaming of inference responses to users
- **Public Chat Interface**: Rate-limited web chat at `/chat`
- **Multimodal Support**: PDFs via Gemini (OpenRouter), images via vision-capable nodes

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Start coordinator (with hot reload)
python -m uvicorn coordinator.main:app --host 0.0.0.0 --port 8000 --reload

# Start node agent (requires account key)
export IRIS_ACCOUNT_KEY="1234 5678 9012 3456"
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
coordinator/              # Central FastAPI server
├── main.py              # FastAPI app, REST routes, WebSocket /nodes/connect endpoint
├── database.py          # SQLite schema and async operations (aiosqlite)
├── auth.py              # JWT authentication, bcrypt password hashing
├── node_registry.py     # Connected node management, heartbeat tracking, tier selection
├── task_orchestrator.py # Task division, node assignment, streaming handling, PDF bypass
├── response_aggregator.py # Combines subtask results
├── reputation.py        # Node reputation scoring
├── economics.py         # Monthly pool distribution
├── crypto.py            # Coordinator-side encryption
├── dashboard.py         # Web dashboard and public chat endpoints
├── streaming.py         # StreamingManager for real-time SSE responses
├── difficulty_classifier.py # OpenRouter-based task difficulty classification
├── account_service.py   # Mullvad-style account key management
├── multimodal_processor.py # PDF processing via Gemini (OpenRouter)
└── templates/
    ├── dashboard.html   # Network monitoring dashboard
    └── chat.html        # Public chat interface with streaming and file upload

node_agent/              # Distributed node agents
├── main.py              # WebSocket connection, task execution, streaming chunks, vision support
├── lmstudio_client.py   # LM Studio API client (streaming support, vision API)
├── node_agent_openrouter.py  # Fake node using OpenRouter (fallback when no real nodes)
├── openrouter_client.py # OpenRouter API client for fake nodes
├── crypto.py            # Node-side encryption
├── heartbeat.py         # Periodic heartbeat sender
├── gpu_info.py          # GPU detection (NVIDIA/AMD/Apple Silicon)
└── model_info.py        # Model parameter, quantization parsing, vision detection

scripts/                 # Utility scripts
└── start_fake_nodes.sh  # Start multiple fake nodes with OpenRouter

client/                  # User interfaces
├── cli.py               # Typer CLI with Rich output
└── sdk.py               # AsyncIrisClient for programmatic access

shared/                  # Shared between all components
├── models.py            # Pydantic models (User, Node, Task, NodeTier, TaskDifficulty)
├── protocol.py          # WebSocket message types (TASK_STREAM, CLASSIFY_ASSIGN, etc.)
└── crypto_utils.py      # X25519 key exchange, AES-256-GCM encryption
```

## Communication Flow

### Standard Inference
1. Nodes connect via WebSocket to `/nodes/connect` and register with `NODE_REGISTER`
2. Node runs benchmark to measure `tokens_per_second`
3. Coordinator calculates node tier (BASIC/MID/PRO) based on hardware
4. Users submit requests via REST `POST /inference` or web chat `/api/chat/stream`
5. Difficulty classifier (OpenRouter) determines task complexity
6. `task_orchestrator.py` matches difficulty to appropriate node tier
7. Nodes process via LM Studio and stream `TASK_STREAM` chunks back
8. `response_aggregator.py` combines results and returns to user

### Streaming Flow
```
User -> POST /api/chat/stream
     -> task_orchestrator.create_task(enable_streaming=True)
     -> streaming_manager.create_stream(task_id)
     -> Node receives TASK_ASSIGN with enable_streaming=True
     -> Node sends TASK_STREAM chunks via WebSocket
     -> Coordinator pushes to streaming_manager queue
     -> SSE endpoint yields chunks to browser
     -> Browser updates UI in real-time
```

### PDF Processing Flow (Gemini Direct)
```
User -> POST /api/chat/stream (with PDF)
     -> task_orchestrator.create_task() detects PDF
     -> BYPASS subtask pipeline entirely
     -> multimodal_processor.process_pdf_direct()
     -> Gemini (OpenRouter) processes PDF with streaming
     -> streaming_manager receives chunks
     -> SSE endpoint yields chunks to browser
```

### Image Processing Flow (Vision Node)
```
User -> POST /api/chat/stream (with image)
     -> task_orchestrator.create_task() detects image
     -> Select vision-capable node (supports_vision=True)
     -> TASK_ASSIGN with files=[FileData] sent to node
     -> Node calls LM Studio vision API (_vision_completion)
     -> Node sends TASK_STREAM chunks via WebSocket
     -> SSE endpoint yields chunks to browser
```

## Node Tier System

Nodes are automatically classified based on hardware capabilities:

| Tier | Requirements | Assigned Tasks |
|------|--------------|----------------|
| **BASIC** | < 7B params OR < 10 tok/s | SIMPLE only |
| **MID** | 7-20B params AND 10-30 tok/s | SIMPLE, COMPLEX |
| **PRO** | > 20B params OR > 30 tok/s | All difficulties |

Tier calculation in `node_registry.py:_calculate_node_tier()` considers:
- Model parameters (billions)
- Quantization level (Q4, Q5, Q6, Q8, FP16)
- Tokens per second (from benchmark)
- GPU VRAM

## Task Difficulty Classification

Tasks are classified via OpenRouter API (`difficulty_classifier.py`):

| Difficulty | Timeout | Examples |
|------------|---------|----------|
| **SIMPLE** | 60s | Translations, definitions, yes/no questions |
| **COMPLEX** | 300s | Analysis, summaries, comparisons |
| **ADVANCED** | 600s | Code generation, math proofs, complex reasoning |

Environment variable: `OPENROUTER_API_KEY` for classification API calls.

Fallback: Local regex-based classifier if OpenRouter unavailable.

## Task Division Modes

- **Subtasks**: Divide complex tasks into independent parts
- **Consensus**: Same task to multiple nodes for verification
- **Context**: Split long documents across nodes

## Multimodal Support

The system supports processing PDFs and images with different pipelines:

### PDF Processing (Gemini Direct)
- PDFs are processed **directly by Gemini** via OpenRouter API
- Complete bypass of the subtask/node pipeline
- Gemini generates the final response (not just context extraction)
- Streaming support for real-time response delivery

```
User sends PDF + prompt
    ↓
task_orchestrator detects PDF
    ↓
Bypass subtask pipeline completely
    ↓
multimodal_processor.process_pdf_direct()
    ↓
Gemini (OpenRouter) processes PDF and responds
    ↓
Streaming response → SSE → User
```

### Image Processing (Vision Nodes)
- Images are sent to **vision-capable nodes** (LLaVA, Gemma-3, Qwen-VL, etc.)
- Uses the standard subtask pipeline
- Vision capability detected via:
  1. LM Studio API (`type: "vlm"` or `vision: true`)
  2. Model name pattern matching (`detect_vision_support()`)

```
User sends image + prompt
    ↓
task_orchestrator detects image
    ↓
Select vision-capable node (supports_vision=True)
    ↓
Send TASK_ASSIGN with files to node
    ↓
Node uses LM Studio vision API
    ↓
Streaming response → WebSocket → SSE → User
```

### Supported File Types
| Type | Processing | Handler |
|------|------------|---------|
| PDF (`.pdf`) | Gemini Direct | `multimodal_processor.py` |
| JPEG (`.jpg`, `.jpeg`) | Vision Node | `lmstudio_client.py` |
| PNG (`.png`) | Vision Node | `lmstudio_client.py` |
| WebP (`.webp`) | Vision Node | `lmstudio_client.py` |
| GIF (`.gif`) | Vision Node | `lmstudio_client.py` |

### Vision-Capable Models
Models detected as vision-capable include:
- LLaVA family (llava, llava-1.5, llava-1.6, llava-next)
- Qwen-VL (qwen-vl, qwen2-vl, qwen2.5-vl)
- Gemma 3 (gemma-3, gemma3)
- MiniCPM-V, Pixtral, Moondream, CogVLM
- Phi-3 Vision, Llama 3.2 Vision
- Any model with `-vision`, `-vl-`, or `multimodal` in the name

## Cryptography

All payloads are encrypted end-to-end using:
- X25519 for key exchange (Diffie-Hellman)
- AES-256-GCM for symmetric encryption
- Keys are persisted to `data/*.key` files

## Key Environment Variables

**Coordinator:**
- `DATABASE_URL` - SQLite path (default: `sqlite:///data/iris.db`)
- `JWT_SECRET` - JWT signing secret
- `COORDINATOR_PRIVATE_KEY_PATH` - Key file path
- `OPENROUTER_API_KEY` - API key for difficulty classification and PDF processing (Gemini)
- `GEMINI_MODEL` - Model for PDF processing (default: `google/gemini-2.5-flash`)
- `MULTIMODAL_TIMEOUT` - Timeout for multimodal processing (default: 120 seconds)

**Node Agent:**
- `IRIS_ACCOUNT_KEY` - **Required** Mullvad-style account key (16 digits)
- `NODE_ID` - Unique node identifier
- `COORDINATOR_URL` - WebSocket URL (default: `ws://168.119.10.189:8000/nodes/connect`)
- `LMSTUDIO_URL` - LM Studio API URL (default: `http://localhost:1234/v1`)
- `NODE_KEY_PATH` - Path to node encryption key file

## Web Interfaces

### Dashboard (`/dashboard`)
- Network statistics (nodes online, tasks completed)
- Connected nodes with tier, model, VRAM, tokens/second
- Reputation leaderboard
- Recent tasks list

### Public Chat (`/chat`)
- Rate-limited chat interface
- Anonymous: 1 message/24h
- With Account Key: 3 messages/24h
- Unlimited keys configurable in `dashboard.py:UNLIMITED_ACCOUNT_KEYS`
- Real-time streaming responses via SSE

## Reputation System

Nodes start at 100 points (minimum 10). Key changes:
- Task completed: +10, Fast completion: +5
- Task timeout: -20, Invalid response: -50
- Uptime: +1/hour, Broken promise: -5/hour
- Weekly decay: -1%

## WebSocket Protocol Messages

**Node -> Coordinator:**
- `NODE_REGISTER` - Initial registration with capabilities (includes `supports_vision` flag)
- `NODE_HEARTBEAT` - Periodic health check
- `TASK_RESULT` - Completed task response
- `TASK_ERROR` - Task failure notification
- `TASK_STREAM` - Streaming chunk during inference
- `CLASSIFY_RESULT` - Difficulty classification result

**Coordinator -> Node:**
- `REGISTER_ACK` - Registration confirmation
- `HEARTBEAT_ACK` - Heartbeat acknowledgment
- `TASK_ASSIGN` - New task assignment (with `enable_streaming` flag, optional `files` for vision)
- `CLASSIFY_ASSIGN` - Classification task assignment

## Account Key System

Mullvad-style anonymous authentication:
- 16-digit numeric keys (format: `1234 5678 9012 3456`)
- No email/password required
- Generated via `POST /accounts/generate`
- Verified via `POST /accounts/verify`
- Links nodes to accounts for reputation tracking

## Fake Nodes (OpenRouter Fallback)

"Fake nodes" are virtual nodes that use OpenRouter API instead of LM Studio. They provide always-available inference capacity as fallback when no real nodes are connected.

### How it Works
- Fake nodes connect via WebSocket just like real nodes
- They call OpenRouter API instead of LM Studio for inference
- They have **built-in penalties** to ensure real nodes are preferred

### Penalty Mechanism
The `select_nodes_v3()` algorithm prefers real nodes via:

| Factor | Real Node | Fake Node | Effect |
|--------|-----------|-----------|--------|
| `tokens_per_second` | 20-50 | 5 | Higher expected_delay for fake |
| `current_load` | Actual | +3 artificial | Lower score for fake |
| Result | ~0.90 score | ~0.73 score | **~17% less selection probability** |

### Running Fake Nodes

```bash
# Single fake node
export OPENROUTER_API_KEY="sk-or-v1-..."
export IRIS_ACCOUNT_KEY="1234 5678 9012 3456"
export OPENROUTER_MODEL="qwen/qwen-2.5-72b-instruct"
python -m node_agent.node_agent_openrouter

# Multiple fake nodes
./scripts/start_fake_nodes.sh
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes | - | OpenRouter API key |
| `IRIS_ACCOUNT_KEY` | Yes | - | Account key for authentication |
| `OPENROUTER_MODEL` | No | `qwen/qwen-2.5-72b-instruct` | Model to use |
| `NODE_ID` | No | `openrouter-{pid}` | Unique node ID |
| `FAKE_NODE_TPS` | No | `5.0` | Reported TPS (low = penalty) |
| `FAKE_NODE_ARTIFICIAL_LOAD` | No | `3` | Artificial load in heartbeats |

### Recommended Models

| Model | OpenRouter ID | Use Case |
|-------|---------------|----------|
| Qwen 2.5 72B | `qwen/qwen-2.5-72b-instruct` | General, code |
| Llama 3.1 70B | `meta-llama/llama-3.1-70b-instruct` | General |
| DeepSeek V3 | `deepseek/deepseek-chat` | Code, reasoning |
