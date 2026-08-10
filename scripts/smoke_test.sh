#!/usr/bin/env bash
set -euo pipefail
API="${API_URL:-http://localhost:8000}"
PDF="${1:-apps/api/tests/fixtures/fixture-native-arabic.pdf}"

echo "Health..."
curl -sf "$API/api/health/live" >/dev/null

echo "Upload $PDF..."
RESP=$(curl -sf -F "file=@${PDF}" "$API/api/documents")
echo "$RESP"
DOC_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$RESP")

echo "Polling document $DOC_ID..."
for i in $(seq 1 120); do
  STATUS=$(curl -sf "$API/api/documents/$DOC_ID")
  STATE=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d['status'], d.get('progress'), d.get('current_stage'))" <<<"$STATUS")
  echo "  $STATE"
  if [[ "$STATE" == ready* ]]; then
    break
  fi
  if [[ "$STATE" == failed* ]]; then
    echo "$STATUS"
    exit 1
  fi
  sleep 5
done

echo "Query..."
curl -sf -H 'Content-Type: application/json' \
  -d "{\"question\":\"ما مدة العقد؟\",\"document_ids\":[\"$DOC_ID\"]}" \
  "$API/api/query" | python3 -m json.tool

echo "Unanswerable..."
curl -sf -H 'Content-Type: application/json' \
  -d "{\"question\":\"ما اسم كلب المؤلف؟\",\"document_ids\":[\"$DOC_ID\"]}" \
  "$API/api/query" | python3 -m json.tool

echo "Delete..."
curl -sf -X DELETE "$API/api/documents/$DOC_ID" >/dev/null
echo "Smoke OK"
