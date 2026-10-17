#!/bin/bash
# smoke-test.sh

echo "Starting smoke tests..."

# Wait for backend and ai-service
./wait-for-it.sh backend:8000 -t 60 || exit 1
./wait-for-it.sh ai-service:8001 -t 60 || exit 1

# Check backend health
echo "Testing backend health..."
BACKEND_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://backend:8000/api/v1/health)
if [ "$BACKEND_STATUS" -eq 200 ]; then
    echo "Backend health check: PASS"
else
    echo "Backend health check: FAIL (Status: $BACKEND_STATUS)"
    exit 1
fi

# Check ai-service health
echo "Testing ai-service health..."
AI_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://ai-service:8001/healthz)
if [ "$AI_STATUS" -eq 200 ]; then
    echo "AI Service health check: PASS"
else
    echo "AI Service health check: FAIL (Status: $AI_STATUS)"
    exit 1
fi

echo "All smoke tests passed."
exit 0
