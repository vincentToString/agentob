FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# Put your code under /app/ai_service so `import ai_service...` works
COPY . ./ai_service

CMD ["python", "-m", "ai_service.worker"]
