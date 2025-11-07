# -*- coding: utf-8 -*-
"""
第二轮更细回归：下载/AI/导出/调度 全链路（可在离线环境下运行）

策略：
- 构造最小可用 run_dir（含 subs 与 run.jsonl），避免真实网络调用
- 运行 AIService：无 API Key 时将回退到本地兜底，生成基本输出与 HTML 报告
- 调用导出：生成 HTML 报告，校验存在
- 调度链路：初始化 SchedulerService，注入轻量执行器，创建任务并 run_once
"""
# tags: offline
import sys
import json
import time
import tempfile
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_fake_run_dir() -> Path:
    """创建一个最小可用的 run_dir（subs + run.jsonl）"""
    td = Path(tempfile.mkdtemp(prefix="fullchain_"))
    run_dir = td / "out" / "20250101_000000"
    subs_dir = run_dir / "subs"
    subs_dir.mkdir(parents=True, exist_ok=True)

    # 伪造一个视频ID与字幕
    vid = "VID12345678A"
    (subs_dir / f"{vid}.en.txt").write_text(
        """This is a small transcript for testing.
It contains a few sentences to simulate a caption file.
The purpose is to trigger local AI fallback and reporting.
""",
        encoding="utf-8",
    )

    # 生成最小 run.jsonl（仅 detect 记录即可用于报告）
    (run_dir / "run.jsonl").write_text(
        "\n".join([
            json.dumps({
                "ts": "2025-01-01T00:00:00Z",
                "action": "detect",
                "video_id": vid,
                "url": f"https://youtu.be/{vid}",
                "status": "has_subs",
                "manual_langs": ["en"],
                "auto_langs": [],
                "title": "Fake Video Title",
                "channel": "Fake Channel",
                "upload_date": "20250101"
            })
        ]),
        encoding="utf-8",
    )

    return run_dir


def test_ai_and_report_generation():
    """测试 AI 回退与报告生成（离线可跑）"""
    run_dir = _make_fake_run_dir()

    # 运行 AI（无 API Key 将触发 fallback，本地生成关键词/章节）
    from services.ai_service import AIService
    done_flag = {"done": False, "html": None}

    def on_progress(p):
        # 仅验证回调流程
        assert isinstance(p, dict)

    def on_complete(res):
        done_flag["done"] = True
        done_flag["html"] = res.get("html_path")

    ai_cfg = {
        "enabled": True,
        "provider": "GPT",  # 将映射为 openai，无 key 时最终走本地兜底
        "model": "gpt-5",
        "api_key": "",      # 空 key
        "base_url": "",     # 使用默认
        "translate_langs": ["zh"],
        "workers": 1,
        "max_chars_per_video": 2000,
    }

    svc = AIService()
    started = svc.run_ai_processing(
        run_dir=str(run_dir),
        ai_config=ai_cfg,
        progress_callback=on_progress,
        completion_callback=on_complete,
    )
    assert started, "AIService 未能启动"

    # 等待完成（最多 10 秒）
    t0 = time.time()
    while not done_flag["done"] and (time.time() - t0) < 10:
        time.sleep(0.2)

    assert done_flag["done"], "AI 处理未在超时内完成"

    # 生成 HTML 报告
    from core.reporting import export_run_html
    html_path = export_run_html(str(run_dir))
    assert html_path, "HTML 报告生成失败"
    assert Path(html_path).exists(), "HTML 报告文件不存在"

    print(f"[OK] AI 回退与报告生成通过: {html_path}")
    return True


def test_scheduler_minimal_flow():
    """测试调度器最小链路：初始化→设置执行器→创建任务→run_once"""
    from services.scheduler_service import SchedulerService

    service = SchedulerService({})
    if not service.is_available():
        print("[WARN] 调度器不可用，跳过该测试")
        return True

    # 注入轻量级执行器（直接返回成功）
    def dummy_executor(*args, **kwargs):
        return {"ok": True, "run_dir": str(Path("out") / "dummy")}

    if service.scheduler_engine:
        service.scheduler_engine.set_executor(dummy_executor)

    # 创建任务
    job_id = service.create_job({
        "name": "Test Job",
        "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "output_root": "out",
        "preferred_langs": ["en"],
        "do_download": False,
        "enabled": True,
    })
    assert job_id > 0, "创建任务失败"

    # 立即运行一次（不依赖真实下载/网络）
    service.run_job_once(job_id)
    print(f"[OK] 调度 run_once 已触发 (job_id={job_id})")
    return True


def main():
    ok1 = test_ai_and_report_generation()
    ok2 = test_scheduler_minimal_flow()
    all_ok = ok1 and ok2
    print(f"\n全链路小结：{'通过' if all_ok else '失败'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())


