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
4. Generate an Account Key (or use existing one)
5. Download the node agent binary
6. Configure and start your node

### Manual Installation

If you prefer manual setup:

```bash
# 1. Generate an Account Key (Mullvad-style, 16 digits)
curl -X POST http://168.119.10.189:8000/accounts/generate
# Response: {"account_key": "1234 5678 9012 3456", "account": {...}}
# IMPORTANT: Save this key! It will only be shown once.

# 2. Download the binary for your platform
# Linux AMD64
curl -fsSL https://github.com/iris-network/iris-node/releases/latest/download/iris-node-linux-amd64 -o iris-node
# macOS ARM64 (Apple Silicon)
curl -fsSL https://github.com/iris-network/iris-node/releases/latest/download/iris-node-darwin-arm64 -o iris-node
# macOS Intel
curl -fsSL https://github.com/iris-network/iris-node/releases/latest/download/iris-node-darwin-amd64 -o iris-node

chmod +x iris-node

# 3. Set your Account Key
export IRIS_ACCOUNT_KEY="1234 5678 9012 3456"

# 4. Run
./iris-node
```

### Account Key System

Iris uses a **Mullvad-style** anonymous account system:

- **16-digit numeric key** (e.g., `1234 5678 9012 3456`)
- **No email or password required** - just save your key
- **One account, multiple nodes** - link all your machines to one account
- **Shown only once** - save it immediately when generated!

```bash
# Generate a new account
iris account generate

# Verify your key is valid
iris account verify --key "1234 5678 9012 3456"

# See your account info
iris account info --key "1234 5678 9012 3456"

# List all nodes linked to your account
iris account nodes --key "1234 5678 9012 3456"
```

### After Installation

The installer creates two commands:

```bash
# Open interactive dashboard (TUI)
iris

# Start the node agent
iris-node
```

### Interactive TUI Dashboard

The `iris` command opens an interactive terminal dashboard:

```
┌─────────────────────────────────────────────────────────────────┐
│  IRIS NETWORK                           [1]Node [2]Net [3]Chat  │
├─────────────────────────────────────────────────────────────────┤
│  ● CONNECTED    Nodes: 12    Tasks: 847    Rep: 87/100         │
├─────────────────────────────────────────────────────────────────┤
│  Leaderboard:                                                   │
│  🥇 node-alpha    Rep: 156   Tasks: 1,234                      │
│  🥈 node-beta     Rep: 142   Tasks: 1,089                      │
│  🥉 your-node     Rep: 87    Tasks: 156   ← YOU                │
└─────────────────────────────────────────────────────────────────┘
```

**Features:**
- **Network Tab** - Live stats, active nodes, reputation leaderboard
- **Node Tab** - Your node status, performance metrics, activity log
- **Chat Tab** - Interactive chat interface to send inference requests

**Keyboard shortcuts:** `1` Node | `2` Network | `3` Chat | `R` Refresh | `Q` Quit

### CLI Commands

```bash
iris stats        # Network statistics
iris nodes        # Active nodes
iris reputation   # Leaderboard
iris ask "prompt" # Send inference request
iris --help       # All commands
```

### Service Management

```bash
# View logs
tail -f ~/.iris/logs/node.log

# Linux
sudo systemctl status iris-node
sudo systemctl restart iris-node

# macOS
launchctl list | grep iris
```

### Uninstall

To completely remove the node and all data:

**Linux / macOS:**
```bash
curl -fsSL https://iris.network/install.sh | bash -s -- --uninstall
# Or if you have the script locally:
./install.sh --uninstall
```

**Windows (PowerShell):**
```powershell
.\install.ps1 -Uninstall
```

This will:
- Stop and remove the system service
- Remove the binary and all configuration
- Delete all data and logs
- Clean up PATH entries
- The node will disappear from the network

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

# In another terminal, generate an account key
curl -X POST http://localhost:8000/accounts/generate
# Save the account_key from the response!

# Start LM Studio and load a model

# Start a node agent
export NODE_ID="dev-node-1"
export COORDINATOR_URL="ws://localhost:8000/nodes/connect"
export LMSTUDIO_URL="http://localhost:1234/v1"
export IRIS_ACCOUNT_KEY="1234 5678 9012 3456"  # Your key here
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

### Accounts (Mullvad-style)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/accounts/generate` | POST | Generate new account key |
| `/accounts/verify` | POST | Verify account key is valid |
| `/accounts/me` | GET | Get account info (pass `account_key` as query param) |
| `/accounts/nodes` | GET | Get nodes linked to account |
| `/admin/accounts` | GET | List all accounts (auth required) |

### Node Enrollment (Legacy)
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/nodes/validate-token` | POST | Validate enrollment token (deprecated) |
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
| `IRIS_ACCOUNT_KEY` | (required) | Your 16-digit account key |
| `NODE_ID` | `node-{hostname}` | Unique node identifier |
| `COORDINATOR_URL` | `ws://168.119.10.189:8000/nodes/connect` | Coordinator URL |
| `LMSTUDIO_URL` | `http://localhost:1234/v1` | LM Studio API |

### Node Config File (config.yaml)

```yaml
node_id: "my-node-name"
coordinator_url: "ws://168.119.10.189:8000/nodes/connect"
lmstudio_url: "http://localhost:1234/v1"
account_key: "1234 5678 9012 3456"  # Your 16-digit key
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
- JWT authentication (for admin users)
- Mullvad-style account keys for node registration (anonymous, no email required)
- Account keys are hashed (SHA256) before storage - never stored in plain text

---

## Project Structure

```
iris-node/
├── coordinator/           # Central server
│   ├── main.py           # FastAPI app
│   ├── accounts.py       # Account key generator
│   ├── account_service.py # Account business logic
│   ├── node_registry.py  # Node management
│   ├── node_tokens.py    # Enrollment tokens (legacy)
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
│   ├── cli.py            # Includes account commands
│   └── sdk.py
│
└── shared/               # Shared code
    ├── models.py         # Includes Account models
    ├── protocol.py
    └── crypto_utils.py
```

---

## Troubleshooting

### Node won't connect
1. Check LM Studio is running: `curl http://localhost:1234/v1/models`
2. Check coordinator: `curl http://168.119.10.189:8000/health`
3. Verify your account key: `iris account verify --key "YOUR_KEY"`
4. Check environment variable is set: `echo $IRIS_ACCOUNT_KEY`

### Command not found after installation
```bash
# macOS/Linux: Add to PATH
source ~/.zshrc  # or ~/.bashrc

# Or run directly
~/.iris/bin/iris-node --help
```

### Account key not working
1. Check format: Must be 16 digits (e.g., `1234 5678 9012 3456`)
2. Verify it's valid: `curl -X POST http://168.119.10.189:8000/accounts/verify -H "Content-Type: application/json" -d '{"account_key": "YOUR_KEY"}'`
3. Generate a new one if lost: `iris account generate` (but you'll lose access to previous nodes)

### Token validation failed (Legacy)
If using old enrollment tokens, they are deprecated. Generate an account key instead.

---

## License

MIT License

## Contributing

Contributions welcome! Please read contributing guidelines before submitting PRs.
