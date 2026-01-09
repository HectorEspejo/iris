# Iris Network - Distributed AI Inference

A distributed AI inference network where members contribute compute nodes running LM Studio and earn rewards based on reputation.

```
┌─────────────────────────────────────────────────────────────────┐
│                      COORDINATOR SERVER                         │
│         168.119.10.189:8000 • iris.network                      │
└─────────────────────────────────────────────────────────────────┘
          │              │              │              │
          ▼              ▼              ▼              ▼
     ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐
     │ Node 1 │    │ Node 2 │    │ Node 3 │    │ Node N │
     │LM Studio    │LM Studio    │LM Studio    │LM Studio
     └────────┘    └────────┘    └────────┘    └────────┘
```

---

## Quick Install (Run a Node)

### Prerequisites

1. **LM Studio** - Download from [lmstudio.ai](https://lmstudio.ai)
2. Load a model and start the local server (port 1234)

### One-Line Installation

**Linux / macOS:**
```bash
curl -fsSL https://iris.network/install.sh | bash
```

**Windows (PowerShell):**
```powershell
irm https://iris.network/install.ps1 | iex
```

The installer will:
1. Detect your platform
2. Check coordinator connectivity
3. Verify LM Studio is running
4. Create an account or sign in
5. Generate an enrollment token automatically
6. Download the node agent binary
7. Configure and start your node

### Manual Installation

If you prefer manual setup:

```bash
# 1. Download the binary for your platform
# Linux AMD64
curl -fsSL https://github.com/iris-network/iris-node/releases/latest/download/iris-node-linux-amd64 -o iris-node
# macOS ARM64 (Apple Silicon)
curl -fsSL https://github.com/iris-network/iris-node/releases/latest/download/iris-node-darwin-arm64 -o iris-node
# macOS Intel
curl -fsSL https://github.com/iris-network/iris-node/releases/latest/download/iris-node-darwin-amd64 -o iris-node

chmod +x iris-node

# 2. Create config file
cat > config.yaml << EOF
node_id: "my-node-$(hostname)"
coordinator_url: "ws://168.119.10.189:8000/nodes/connect"
lmstudio_url: "http://localhost:1234/v1"
enrollment_token: "YOUR_TOKEN_HERE"
data_dir: "./data"
EOF

# 3. Run
./iris-node --config config.yaml
```

### After Installation

```bash
# Check node status
iris-node --help

# View logs
tail -f ~/.iris/logs/node.log

# Service commands (Linux)
sudo systemctl status iris-node
sudo systemctl restart iris-node

# Service commands (macOS)
launchctl list | grep iris
```

---

## For Developers

### Local Development Setup

```bash
# Clone the repository
git clone https://github.com/iris-network/iris-node.git
cd iris-node

# Install Python dependencies
pip install -r requirements.txt

# Start the coordinator (with hot reload)
python -m uvicorn coordinator.main:app --host 0.0.0.0 --port 8000 --reload

# In another terminal, start LM Studio and load a model

# Start a node agent
export NODE_ID="dev-node-1"
export COORDINATOR_URL="ws://localhost:8000/nodes/connect"
export LMSTUDIO_URL="http://localhost:1234/v1"
python -m node_agent.main
```

### Docker Deployment

```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f coordinator

# Stop
docker-compose down
```

### Build Standalone Binary

```bash
# Build for current platform
./scripts/build-standalone.sh

# Build for all platforms (requires Docker)
./scripts/build-standalone.sh --all

# Create release assets
./scripts/build-standalone.sh --release
```

### CLI Client

```bash
# Register
python -m client.cli register --email user@example.com --password mypassword

# Login
python -m client.cli login --email user@example.com --password mypassword

# Send inference request
python -m client.cli ask "Analyze this text and summarize the main points"

# Check network
python -m client.cli stats
python -m client.cli nodes
python -m client.cli reputation
```

### Running Tests

```bash
pytest tests/ -v
pytest tests/ --cov=coordinator --cov=node_agent --cov=shared
```

---

## API Reference

### Authentication
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register new user |
| `/auth/login` | POST | Login, returns JWT |
| `/auth/me` | GET | Get current user |

### Inference
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/inference` | POST | Submit inference request |
| `/inference/{task_id}` | GET | Get task status |

### Network
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Coordinator health check |
| `/stats` | GET | Network statistics |
| `/reputation` | GET | Node leaderboard |
| `/nodes` | GET | Active nodes (auth required) |
| `/dashboard` | GET | Web dashboard |

### Node Enrollment
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/nodes/validate-token` | POST | Validate enrollment token |
| `/admin/tokens/generate` | POST | Generate new token (auth required) |
| `/admin/tokens` | GET | List tokens (auth required) |

---

## Configuration

### Environment Variables

**Coordinator:**
| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///data/iris.db` | Database path |
| `JWT_SECRET` | (generated) | JWT signing secret |
| `NODE_TOKEN_SECRET` | (generated) | Token signing secret |
| `COORDINATOR_WS_URL` | `ws://168.119.10.189:8000/nodes/connect` | WebSocket URL |

**Node Agent:**
| Variable | Default | Description |
|----------|---------|-------------|
| `NODE_ID` | `node-{hostname}` | Unique node identifier |
| `COORDINATOR_URL` | `ws://168.119.10.189:8000/nodes/connect` | Coordinator URL |
| `LMSTUDIO_URL` | `http://localhost:1234/v1` | LM Studio API |

### Node Config File (config.yaml)

```yaml
node_id: "my-node-name"
coordinator_url: "ws://168.119.10.189:8000/nodes/connect"
lmstudio_url: "http://localhost:1234/v1"
enrollment_token: "iris_v1.eyJ..."
data_dir: "~/.iris/data"
log_dir: "~/.iris/logs"
```

---

## How It Works

### Task Division Modes
- **Subtasks**: Complex tasks divided into independent parts
- **Consensus**: Same task sent to multiple nodes for verification
- **Context**: Long documents split across nodes

### Reputation System
| Event | Points |
|-------|--------|
| Task completed | +10 |
| Fast completion | +5 |
| Task timeout | -20 |
| Invalid response | -50 |
| Uptime (per hour) | +1 |

### Security
- End-to-end encryption (X25519 + AES-256-GCM)
- JWT authentication
- Enrollment tokens for node registration

---

## Project Structure

```
iris-node/
├── coordinator/           # Central server
│   ├── main.py           # FastAPI app
│   ├── node_registry.py  # Node management
│   ├── node_tokens.py    # Enrollment tokens
│   ├── task_orchestrator.py
│   └── reputation.py
│
├── node_agent/           # Node agent
│   ├── main.py           # Agent entry point
│   ├── standalone_main.py # CLI entry point
│   └── lmstudio_client.py
│
├── installer/            # Installation scripts
│   ├── install.sh        # Linux/macOS
│   └── install.ps1       # Windows
│
├── client/               # CLI client
│   ├── cli.py
│   └── sdk.py
│
└── shared/               # Shared code
    ├── models.py
    ├── protocol.py
    └── crypto_utils.py
```

---

## Troubleshooting

### Node won't connect
1. Check LM Studio is running: `curl http://localhost:1234/v1/models`
2. Check coordinator: `curl http://168.119.10.189:8000/health`
3. Verify enrollment token is valid

### Command not found after installation
```bash
# macOS/Linux: Add to PATH
source ~/.zshrc  # or ~/.bashrc

# Or run directly
~/.iris/bin/iris-node --help
```

### Token validation failed
Tokens are single-use. Generate a new one via the installer or API.

---

## License

MIT License

## Contributing

Contributions welcome! Please read contributing guidelines before submitting PRs.
