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

# Copy coordinator module
COPY coordinator/ ./coordinator/

# Create data directory
RUN mkdir -p /app/data

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=sqlite:///data/iris.db

# Expose port
EXPOSE 8000

# Run coordinator
CMD ["python", "-m", "uvicorn", "coordinator.main:app", "--host", "0.0.0.0", "--port", "8000"]
