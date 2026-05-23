# Phase 5a-1: Realm コンテナの最小 image
#
# Goal: Realm = ai-org-os の「ルール適用範囲」を物理コンテナとして立ち上げる。
# Phase 5a-1 では Claude CLI / Anthropic SDK は入れない（Phase 5a-3 で Judgment
# Pillar を導入するとき追加）。本 image はまず「既存 runtime/ ツールが動く
# Realm の容器」を確立することに絞る。
#
# Build context は repo root（docker-compose.yml の `context: ..` 経由）。
# Codex P2 PR #32 の指摘を踏まえ、COPY ソースは常に context-relative で書く。
# Phase 5a-1 では COPY は使わず bind mount に倒すため、本 Dockerfile は薄い。

FROM python:3.11-slim

# 既存 shell スクリプト (spawn-mind.sh / kill-mind.sh / list-minds.sh /
# observe.py) を動かすために必要な最小ユーティリティ。
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        bash \
        coreutils \
        findutils \
        grep \
        sed \
 && rm -rf /var/lib/apt/lists/*

# ai-org-os repo は bind mount で /realm/repo に入る。
# runtime/ も bind mount で /realm/runtime に入る（書き込み可、Mind spawn のため）。
WORKDIR /realm/runtime

# Phase 5a-1 の暫定 entrypoint。
# 「コンテナを生かしておく」だけで、Pillar 群はまだ常駐しない（Phase 5a-2 以降）。
# 動作確認は `docker exec` で list-minds.sh / observe.py を呼ぶ形。
CMD ["sleep", "infinity"]
