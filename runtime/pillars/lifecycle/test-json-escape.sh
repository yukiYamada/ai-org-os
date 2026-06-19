#!/usr/bin/env bash
# Test _json_escape_string helper (P1 security fix #194)
set -euo pipefail

_json_escape_string() {
  local input="$1"
  local output=""
  local i char byte
  for ((i=0; i<${#input}; i++)); do
    char="${input:i:1}"
    case "$char" in
      '"')  output="${output}\\\"" ;;
      '\\') output="${output}\\\\" ;;
      $'\b') output="${output}\\b" ;;
      $'\f') output="${output}\\f" ;;
      $'\n') output="${output}\\n" ;;
      $'\r') output="${output}\\r" ;;
      $'\t') output="${output}\\t" ;;
      *)
        byte=$(LC_CTYPE=C printf '%d' "'$char" 2>/dev/null || echo 32)
        if [ "$byte" -lt 32 ]; then
          output="${output}$(printf '\\u%04x' "$byte")"
        else
          output="${output}${char}"
        fi
        ;;
    esac
  done
  printf '%s' "$output"
}

echo "Test 1: double quote escape"
result=$(_json_escape_string 'test "value"')
[[ "$result" == *'\"'* ]] && echo "  ✓ PASS" || { echo "  ✗ FAIL"; exit 1; }

echo "Test 2: newline escape"
result=$(_json_escape_string $'line1\nline2')
[[ "$result" == *'\n'* ]] && echo "  ✓ PASS" || { echo "  ✗ FAIL"; exit 1; }

echo "Test 3: JSON injection prevention (P1 security)"
attack='normal","malicious":"injected","x":"tail'
result=$(_json_escape_string "$attack")
json='{"message":"'"${result}"'"}'
if command -v jq >/dev/null 2>&1; then
  parsed=$(echo "$json" | jq -r '.message' 2>/dev/null)
  [ "$parsed" = "$attack" ] && echo "  ✓ PASS (round-trip OK)" || { echo "  ✗ FAIL"; exit 1; }
else
  # Verify quotes are escaped (no bare ", sequence)
  [[ "$result" != *'","'* ]] && echo "  ✓ PASS (injection blocked)" || { echo "  ✗ FAIL"; exit 1; }
fi

echo "Test 4: Valid JSON output"
message="Hello \"world\" with newline"$'\n'"and more"
escaped=$(_json_escape_string "$message")
json='{"ts":"2026-01-01T00:00:00Z","severity":"info","actor":"test","event":"test","message":"'"${escaped}"'"}'
if command -v jq >/dev/null 2>&1; then
  echo "$json" | jq . >/dev/null 2>&1 && echo "  ✓ PASS (valid JSON)" || { echo "  ✗ FAIL (invalid JSON)"; exit 1; }
else
  echo "  ⊘ jq not available, skipping validation"
fi

echo ""
echo "All tests passed!"
