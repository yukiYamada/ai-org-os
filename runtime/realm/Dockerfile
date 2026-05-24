# Realm コンテナ image。
#
# 系譜:
# - Phase 5a-1: 最小コンテナ + bind mount のみ
# - Phase 5a-2: Pillar 群を runtime/pillars/ に配置（image 変更なし、bind 経由）
# - Phase 5a-3 (#38): Judgment Pillar の anthropic SDK を install
# - Phase 5b-1 (#71): CMD を Conductor Pillar 起動に切り替え（Warden の心拍）
#
# Build context は repo root（docker-compose.yml の `context: ../..` 経由）。
# Codex P2 PR #32 の指摘を踏まえ、COPY ソースは常に context-relative で書く。

FROM python:3.11-slim

# 既存 shell スクリプト (Lifecycle / Observation / Conduit Pillar) を動かすために
# 必要な最小ユーティリティ。
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        findutils \
        grep \
        sed \
 && rm -rf /var/lib/apt/lists/*

# Phase 5a-3 (#38): Judgment Pillar の依存（Anthropic SDK）を install。
# image build 時に COPY する requirements.txt は context-relative。
# bind mount より image に焼く方が「Realm が再現可能」を保ちやすい
# （ADR-0014 §6 「CI = Realm の再現性検証」と整合）。
COPY runtime/pillars/judgment/requirements.txt /tmp/judgment-requirements.txt
RUN pip install --no-cache-dir -r /tmp/judgment-requirements.txt \
 && rm /tmp/judgment-requirements.txt

# ai-org-os repo は bind mount で /realm/repo に入る。
# runtime/ も bind mount で /realm/runtime に入る（書き込み可、Mind spawn のため）。
WORKDIR /realm/runtime

# Phase 5b-1 (#71): Conductor Pillar が常駐して各 Pillar を周期で呼ぶ。
# ANTHROPIC_API_KEY 未設定でも Realm は起動する (Judgment は fallback ルート、
# ADR-0013 §1 F3 と整合)。
# 起動を変えたければ `docker compose run --rm realm bash` でシェル起動も可能。
CMD ["bash", "/realm/runtime/pillars/conductor/conductor.sh"]
