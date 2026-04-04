FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install dependencies
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Copy code into analyzer subfolder
COPY . ./analyzer/

# Run the worker
CMD ["python", "-m", "analyzer.main"]
