FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared module
COPY shared/ ./shared/

# Copy node agent module
COPY node_agent/ ./node_agent/

# Create data directory
RUN mkdir -p /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV COORDINATOR_URL=ws://coordinator:8000/nodes/connect
ENV LMSTUDIO_URL=http://host.docker.internal:1234/v1
ENV NODE_KEY_PATH=/app/data/node.key

# Run node agent
CMD ["python", "-m", "node_agent.main"]
