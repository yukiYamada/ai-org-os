# Realm コンテナ image。
#
# 系譜:
# - Phase 5a-1: 最小コンテナ + bind mount のみ
# - Phase 5a-2: Pillar 群を runtime/pillars/ に配置（image 変更なし、bind 経由）
# - Phase 5a-3 (#38): Judgment Pillar の anthropic SDK を install
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

# 暫定 entrypoint: コンテナを生かしておくだけ。Pillar は呼び出し駆動なので daemon 化は不要
# （ADR-0010 §5 / Judgment README の「Phase 5a-3 非スコープ」参照）。
CMD ["sleep", "infinity"]
