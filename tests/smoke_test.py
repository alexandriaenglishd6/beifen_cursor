# -*- coding: utf-8 -*-
"""
tests.smoke_test — 最小冒烟测试
"""
import sys
from pathlib import Path

# 确保能导入 core
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """测试能否正常导入核心模块"""
    try:
        from core import (
            detect_links, download_subtitles, run_full_process,
            run_ai_pipeline, reprocess_ai_errors,
            export_run_html, export_run_md
        )
        print("[OK] All core functions imported successfully")
        return True
    except Exception as e:
        print(f"[FAIL] Import failed: {e}")
        return False

def test_smoke(tmp_path=None):
    """
    最小冒烟测试（将在实现后补充）
    """
    # TODO: 在迁移完成后添加完整测试
    pass

if __name__ == "__main__":
    print("=== Smoke Test: Import Check ===")
    success = test_imports()
    sys.exit(0 if success else 1)

