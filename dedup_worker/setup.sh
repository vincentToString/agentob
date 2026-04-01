#!/bin/bash
# Quick setup script for dedup worker

set -e

echo "🔧 Setting up Dedup Worker..."

# Install dependencies
echo "📦 Installing dependencies with uv..."
uv sync

# Generate gRPC stubs
echo "🔨 Generating gRPC stubs from bloom.proto..."
python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  bloom.proto

if [ -f "bloom_pb2.py" ] && [ -f "bloom_pb2_grpc.py" ]; then
    echo "✅ Setup complete!"
    echo ""
    echo "Generated files:"
    echo "  - bloom_pb2.py"
    echo "  - bloom_pb2_grpc.py"
    echo ""
    echo "Next steps:"
    echo "  1. Add health endpoint to BloomBox (see README.md)"
    echo "  2. Start BloomBox: docker compose up -d"
    echo "  3. Start dedup worker: python -m dedup_worker.worker"
else
    echo "❌ Failed to generate gRPC stubs"
    exit 1
fi
