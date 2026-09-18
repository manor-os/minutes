#!/bin/bash
echo "🧪 Meeting Note Taker - Quick Test"
echo "=================================="
echo ""

echo "1. Testing Backend API..."
HEALTH=$(curl -s http://localhost:8002/health)
if [[ $HEALTH == *"healthy"* ]]; then
    echo "   ✅ Backend is healthy"
else
    echo "   ❌ Backend health check failed"
fi

echo ""
echo "2. Testing Database..."
DB_COUNT=$(docker-compose exec -T postgres psql -U meeting_user -d meeting_notes -t -c "SELECT COUNT(*) FROM meetings;" 2>/dev/null | tr -d ' ')
if [ ! -z "$DB_COUNT" ]; then
    echo "   ✅ Database connected (meetings: $DB_COUNT)"
else
    echo "   ❌ Database connection failed"
fi

echo ""
echo "3. Testing Services..."
SERVICES=$(docker-compose ps --format "{{.Name}}:{{.Status}}" | grep -E "backend|celery|postgres|redis")
for service in $SERVICES; do
    name=$(echo $service | cut -d: -f1)
    status=$(echo $service | cut -d: -f2)
    if [[ $status == *"Up"* ]]; then
        echo "   ✅ $name is running"
    else
        echo "   ❌ $name is not running"
    fi
done

echo ""
echo "4. Testing DeepSeek Configuration..."
DEEPSEEK_KEY=$(docker-compose exec -T backend env | grep DEEPSEEK_API_KEY | cut -d= -f2)
if [ ! -z "$DEEPSEEK_KEY" ] && [ "$DEEPSEEK_KEY" != "" ]; then
    echo "   ✅ DeepSeek API key configured"
else
    echo "   ❌ DeepSeek API key not found"
fi

echo ""
echo "=================================="
echo "✅ All tests completed!"
echo ""
echo "Next steps:"
echo "1. Load browser extension in Chrome/Edge"
echo "2. Test recording on a meeting platform"
echo "3. Check logs: docker-compose logs -f"
