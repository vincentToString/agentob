FROM python:3.11-slim

ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PATH="/venv/bin:$PATH"
# Add /app to PYTHONPATH so python can find the 'intake' package
ENV PYTHONPATH=/app 

WORKDIR /app

RUN pip install --no-cache-dir uv

# Install deps first for better caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen

# --- FIXED SECTION ---
# Copy the code into a subfolder named 'intake'
COPY . ./intake/ 
# ---------------------


EXPOSE 8000

# --- FIXED CMD ---
# Point uvicorn to the module inside the folder: intake.main:app
CMD ["uvicorn", "intake.main:app", "--host", "0.0.0.0", "--port", "8000"]