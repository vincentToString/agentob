FROM python:3.11-slim

# Create an isolated uv environment inside the container
ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PATH="/venv/bin:$PATH"

# Make sure Python can import from /app (so `import config`, `import models`, etc. work)
ENV PYTHONPATH=/app

WORKDIR /app

# Install uv (same style as your other services)
RUN pip install --no-cache-dir uv

# Copy dependency manifests first for better Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into /venv
RUN uv sync --frozen --no-dev

# Copy the rest of the dashboard API code
# (Exclude local .venv via .dockerignore; see note below)
COPY . .

EXPOSE 8003

# If your FastAPI instance is `app = FastAPI()` in main.py:
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8003", "--reload"]
