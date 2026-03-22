#!/bin/bash
# Setup script for RAG service local development

echo "Setting up RAG Service..."

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv package manager..."
    pip install uv
fi

# Create virtual environment and install dependencies using uv
echo "Creating virtual environment and installing dependencies..."
uv sync

echo ""
echo "Setup complete!"
echo ""
echo "To run the service locally:"
echo "1. Activate virtual environment: source .venv/bin/activate"
echo "2. Set environment variables (or copy .env.example to .env)"
echo "3. Run: python main.py"
echo ""
echo "Or run directly with uv:"
echo "uv run python main.py"
echo ""
echo "To run with Docker:"
echo "docker-compose up -d rag_service"
