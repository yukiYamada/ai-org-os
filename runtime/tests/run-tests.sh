#!/usr/bin/env bash
#
# run-tests.sh — runtime のテスト一括実行ランナー
#
# 用法:
#   ./runtime/tests/run-tests.sh
#
# 各 test-*.sh を順に実行し、PASS/FAIL カウントとサマリを出す。
# 1 つでも失敗があれば exit 1。
#
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"

total_files=0
passed_files=0
failed_files=0
failed_list=()

echo "================================================"
echo "  runtime tests"
echo "  root: ${ROOT_DIR}"
echo "================================================"
echo ""

for test_file in "${SCRIPT_DIR}"/test-*.sh; do
  [ -f "${test_file}" ] || continue
  total_files=$((total_files + 1))
  name="$(basename "${test_file}")"
  echo "--- ${name} ---"
  if bash "${test_file}"; then
    echo "[PASS] ${name}"
    passed_files=$((passed_files + 1))
  else
    echo "[FAIL] ${name}"
    failed_files=$((failed_files + 1))
    failed_list+=("${name}")
  fi
  echo ""
done

echo "================================================"
echo "  summary: ${passed_files}/${total_files} files passed"
if [ "${failed_files}" -gt 0 ]; then
  echo "  failed:"
  for f in "${failed_list[@]}"; do
    echo "    - ${f}"
  done
fi
echo "================================================"

[ "${failed_files}" -eq 0 ]
