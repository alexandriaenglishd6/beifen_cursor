# -*- coding: utf-8 -*-
"""
一键回归脚本（默认仅跑 offline 用例）

用法：
  python tests/run_regression.py                 # 仅 offline（默认）
  python tests/run_regression.py --suite online  # 仅 online（可能需网络）
  python tests/run_regression.py --suite all     # offline + online
  python tests/run_regression.py --suite all --include-slow  # 包含 slow 重型用例
"""
from __future__ import annotations
import sys
import subprocess
from pathlib import Path
import argparse

ROOT = Path(__file__).parent.parent
PY = sys.executable or "python"

# 按标签维护用例集（基于现有脚本，不要求 pytest）
OFFLINE = [
    "tests/smoke_test.py",
    "tests/test_full_chain_regression_v2.py",
]

ONLINE = [
    # 轻量联网回归（可能访问YouTube/网络）
    "tests/quick_regression.py",
]

SLOW = [
    # 重型或GPU/大网络用例（默认不跑）
    "tests/test_whisperx_e2e_real.py",
]


def run_case(case: str) -> tuple[bool, int]:
    path = ROOT / case
    print("\n" + "=" * 60)
    print(f"RUN: {case}")
    print("=" * 60)
    try:
        r = subprocess.run([PY, str(path)], cwd=str(ROOT), capture_output=False)
        ok = (r.returncode == 0)
        print(f"[RESULT] {'PASS' if ok else 'FAIL'}  rc={r.returncode}")
        return ok, r.returncode
    except Exception as e:
        print(f"[ERROR] 执行 {case} 失败: {e}")
        return False, -1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", choices=["offline", "online", "all"], default="offline")
    ap.add_argument("--include-slow", action="store_true", help="包含慢速/重型用例")
    args = ap.parse_args()

    plan: list[str] = []
    if args.suite in ("offline", "all"):
        plan += OFFLINE
    if args.suite in ("online", "all"):
        plan += ONLINE
    if args.include_slow:
        plan += SLOW

    if not plan:
        print("[WARN] 没有可执行的用例")
        return 0

    print("\n回归计划：")
    for i, c in enumerate(plan, 1):
        print(f"  {i}. {c}")

    total = len(plan)
    passed = 0
    failed_cases: list[str] = []

    for case in plan:
        ok, _ = run_case(case)
        if ok:
            passed += 1
        else:
            failed_cases.append(case)

    print("\n" + "=" * 60)
    print("汇总：")
    print(f"  通过 {passed}/{total}")
    if failed_cases:
        print("  失败用例：")
        for c in failed_cases:
            print(f"   - {c}")
    print("=" * 60)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())


