#!/usr/bin/env bash
#
# _lib_host_stub.sh — テスト用 stub host config を準備するヘルパー。
#
# 用法: 各 test スクリプトの冒頭で
#   . "${SCRIPT_DIR}/_lib_host_stub.sh"
#   stub_host_config_init "${TEST_TMP_DIR}"
#
# これで AI_ORG_OS_HOST_CONFIG が export され、spawn-mind.sh / mind-loop.sh /
# list-minds.sh / kill-mind.sh が dummy の python/nexus を指す config.env を
# source した状態で動く。
#
# Phase 5b-3 (#78) で spawn-mind.sh が runtime/host/config.env を要求するように
# なったため、CI 等の setup 未済環境でテストを通すために必要。
#

stub_host_config_init() {
  local tmp_dir="$1"
  if [ -z "${tmp_dir}" ] || [ ! -d "${tmp_dir}" ]; then
    echo "[stub_host_config_init] ERROR: tmp dir not provided or missing" >&2
    return 1
  fi
  local stub_py="${tmp_dir}/stub-python.exe"
  local stub_nexus="${tmp_dir}/stub-nexus.py"
  local stub_config="${tmp_dir}/stub-host-config.env"
  touch "${stub_py}" "${stub_nexus}"
  cat > "${stub_config}" <<CFG
AI_ORG_OS_HOME=${tmp_dir}
HOST_PYTHON_BIN=${stub_py}
HOST_NEXUS_PY=${stub_nexus}
HOST_RUNTIME_DIR=${RUNTIME_DIR:-/tmp}
HOST_SETUP_AT=test-stub
CFG
  # Phase 5b-4 (#81): tests も AI_ORG_OS_HOME を tmp に向ける
  # (snapshot / inbox / conduit / conductor が tmp で隔離される)。
  export AI_ORG_OS_HOME="${tmp_dir}"
  export AI_ORG_OS_HOST_CONFIG="${stub_config}"
  # ディレクトリ骨格を tmp 内に作る (各 Pillar が mkdir するが、テストで先回り)
  mkdir -p "${tmp_dir}/minds" "${tmp_dir}/issues/inbox" "${tmp_dir}/issues/archive" \
           "${tmp_dir}/snapshots" "${tmp_dir}/conduit-storage/inbox" "${tmp_dir}/conduit-storage/archive"
}
