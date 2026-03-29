FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PATH="/venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY . .

CMD ["python", "-m", "worker"]
