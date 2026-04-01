FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PATH="/venv/bin:$PATH"
ENV PYTHONPATH=/app

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install dependencies
COPY pyproject.toml ./
RUN uv sync --frozen

# Copy code into dedup_worker subfolder
COPY . ./dedup_worker/

# Generate gRPC stubs at build time
RUN chmod +x ./dedup_worker/generate_grpc.sh && \
    cd dedup_worker && \
    python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    bloom.proto

# Run the worker
CMD ["python", "-m", "dedup_worker.worker"]
