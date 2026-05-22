#!/usr/bin/env python3
"""
2 Mind 間 Dispatch シミュレーション。

Nexus storage 層を 2 つの独立した呼び出し点から操作することで、
「alice が bob に送信 → bob が受信 → bob が ack」の一連の流れを再現する。

これは MCP セッションを介さない storage 直接呼び出しのシミュレーション。
本物の 2 Claude セッションを使った検証は README.md の方式 B を参照。

Usage:
  python3 runtime/verification/phase-3-dogfooding/simulate_two_minds.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

NEXUS_DIR = Path(__file__).resolve().parents[2] / "nexus"
sys.path.insert(0, str(NEXUS_DIR))

from storage import Nexus  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        # 2 つの独立した呼び出し点（同じ storage_dir を共有）。
        # identity binding (Issue #19, ADR-0008) は PR #27 マージ後に有効化されるが、
        # 本シミュレーションでは bind なしの素朴版を使う。
        nx_alice = Nexus(storage_dir=tmp)
        nx_bob = Nexus(storage_dir=tmp)

        print("=" * 60)
        print("  Phase 3 Dogfooding: 2 Mind Dispatch Simulation")
        print("=" * 60)
        print(f"  storage: {tmp}")
        print()

        # 1. alice → bob に送信
        print("[step 1] alice sends to bob")
        sent = nx_alice.send_dispatch(
            from_mind="alice",
            to_mind="bob",
            topic="design-question",
            body="hello bob, I have a design question for you.",
        )
        assert sent["ok"], f"send failed: {sent}"
        msg_id = sent["msg_id"]
        print(f"  → ok={sent['ok']}, msg_id={msg_id}")
        print()

        # 2. bob が inbox を読む
        print("[step 2] bob reads inbox")
        inbox = nx_bob.read_inbox(mind_name="bob")
        assert inbox["count"] == 1, f"expected 1 message, got {inbox['count']}"
        msg = inbox["messages"][0]
        print(f"  → count={inbox['count']}, msg_id={msg['msg_id']}")
        print("  → content snippet:")
        for line in msg["content"].splitlines()[:6]:
            print(f"      {line}")
        if len(msg["content"].splitlines()) > 6:
            print("      ...")
        print()

        # 3. bob が ack
        print(f"[step 3] bob acks msg {msg_id}")
        ack = nx_bob.ack_dispatch(mind_name="bob", msg_id=msg_id)
        assert ack["ok"], f"ack failed: {ack}"
        assert not ack.get("already_acked"), "first ack should not be marked already_acked"
        print(f"  → ok={ack['ok']}, archived_at={ack['archived_at']}")
        print()

        # 4. bob が再度 read（空のはず）
        print("[step 4] bob reads inbox again (should be empty)")
        inbox2 = nx_bob.read_inbox(mind_name="bob")
        assert inbox2["count"] == 0, f"expected 0 after ack, got {inbox2['count']}"
        print(f"  → count={inbox2['count']}")
        print()

        # 5. 再 ack（冪等性、Codex P1 PR #23 修正の確認）
        print(f"[step 5] bob acks same msg again (idempotency check)")
        ack2 = nx_bob.ack_dispatch(mind_name="bob", msg_id=msg_id)
        assert ack2["ok"], f"second ack should succeed, got: {ack2}"
        assert ack2.get("already_acked"), "second ack should be marked already_acked"
        print(f"  → ok={ack2['ok']}, already_acked={ack2['already_acked']}")
        print()

        # 6. archive 確認
        archive_path = Path(tmp) / "archive" / "bob" / f"{msg_id}.md"
        print(f"[step 6] archive file at {archive_path}")
        print(f"  → exists={archive_path.exists()}")
        if archive_path.exists():
            print("  → contents:")
            for line in archive_path.read_text(encoding="utf-8").splitlines():
                print(f"      {line}")
        print()

        # 7. alice の inbox は空のまま（他 Mind に影響しない）
        print("[step 7] alice inbox should not be affected")
        alice_inbox = nx_alice.read_inbox(mind_name="alice")
        assert alice_inbox["count"] == 0, f"alice inbox should be empty, got {alice_inbox['count']}"
        print(f"  → count={alice_inbox['count']}")
        print()

        print("=" * 60)
        print("  All steps passed. Phase 3 Dispatch is verified.")
        print("=" * 60)
        return 0


if __name__ == "__main__":
    sys.exit(main())
