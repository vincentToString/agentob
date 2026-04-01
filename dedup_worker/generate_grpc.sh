#!/bin/bash
# Generate Python gRPC stubs from bloom.proto

cd "$(dirname "$0")"

echo "Generating Python gRPC stubs from bloom.proto..."

python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  bloom.proto

if [ $? -eq 0 ]; then
    echo "✓ Generated bloom_pb2.py and bloom_pb2_grpc.py"
else
    echo "✗ Failed to generate gRPC stubs"
    exit 1
fi
