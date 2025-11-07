# -*- coding: utf-8 -*-
"""
core.orchestrator — 主流程编排（增量/批处理/记录/回写 last_seen + Webhook）
"""
from __future__ import annotations
import os, json, time, threading, hashlib, hmac, logging
from pathlib import Path
from typing import List, Dict, Any, Callable

# 创建日志记录器
logger = logging.getLogger(__name__)

# ========== Webhook 通知辅助函数 ==========
def _send_webhook_with_retry(url: str, payload: dict, timeout: int = 5, max_retry: int = 3, secret: str = ""):
    """
    发送 webhook 请求（带重试 + HMAC签名）
    
    重试策略：0.5s → 1.5s → 3.5s（指数退避 + jitter）
    """
    try:
        import requests
    except:
        return
    
    import random
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    
    # HMAC 签名（可选）
    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-GPTTool-Signature"] = f"sha256={sig}"
    
    for attempt in range(max_retry):
        try:
            resp = requests.post(url, data=body, headers=headers, timeout=timeout)
            if 200 <= resp.status_code < 300:
                return  # 成功
            if attempt < max_retry - 1:
                backoff = 0.5 * (3 ** attempt) * (1.0 + random.uniform(-0.15, 0.15))
                time.sleep(backoff)
        except Exception:
            if attempt < max_retry - 1:
                backoff = 0.5 * (3 ** attempt) * (1.0 + random.uniform(-0.15, 0.15))
                time.sleep(backoff)
from .detection import detect_links, extract_all_video_urls_from_channel_or_playlist
from .download import download_subtitles
from .net import build_proxy_pool, RateLimiter, CircuitBreaker
from .utils import normalize_url, channel_index_load, channel_index_save, history_append, _ts_utc, ensure_channel_videos_url

# Step 3 Day1: 历史记录和报告生成
# Day2: 增强错误分类
# Day3: 新增 read_history 用于重试功能
try:
    from history_schema import write_history, classify_status, classify_status_v2, HistoryRow, read_history
    from report_gen import generate_report
    _HISTORY_AVAILABLE = True
except ImportError:
    _HISTORY_AVAILABLE = False

# ---------- Dry 预览报告生成 ----------
def _generate_dry_preview(run_dir: str, results: list[dict]) -> str:
    """
    生成 Dry Run 预览报告（plan.md）
    
    返回：plan.md 路径
    """
    total = len(results)
    has_subs = sum(1 for r in results if r.get("status") == "has_subs")
    no_subs = sum(1 for r in results if r.get("status") == "no_subs")
    errors = sum(1 for r in results if str(r.get("status", "")).startswith("error"))
    
    # 语言统计
    lang_counts = {}
    for r in results:
        for lang in r.get("all_langs", []):
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
    
    md = f"""# Dry Run Preview Report

**运行目录**：{run_dir}  
**生成时间**：{_ts_utc()}  
**模式**：预览（未实际下载/AI处理）

## 📊 检测结果统计

- **总视频数**：{total}
- **有字幕**：{has_subs} ({has_subs/total*100:.1f}%)
- **无字幕**：{no_subs} ({no_subs/total*100:.1f}%)
- **错误**：{errors} ({errors/total*100:.1f}%)

## 🌐 语言分布

"""
    for lang, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)[:20]:
        md += f"- **{lang}**：{count} 个\n"
    
    md += f"""
## ❌ 错误分布（如有）

"""
    error_dist = {}
    for r in results:
        st = r.get("status", "")
        if str(st).startswith("error"):
            error_dist[st] = error_dist.get(st, 0) + 1
    
    if error_dist:
        for err, cnt in sorted(error_dist.items(), key=lambda x: x[1], reverse=True):
            md += f"- **{err}**：{cnt} 次\n"
    else:
        md += "无错误\n"
    
    md += f"""
## 📝 视频列表（前50条）

| 视频ID | 状态 | 可用语言 |
|--------|------|----------|
"""
    for r in results[:50]:
        vid = r.get("video_id", "")[:15]
        status = r.get("status", "")[:20]
        langs = ", ".join(r.get("all_langs", []))[:60]
        md += f"| {vid} | {status} | {langs} |\n"
    
    if total > 50:
        md += f"\n（共 {total} 个视频，仅展示前 50 条）\n"
    
    # 保存
    preview_path = Path(run_dir) / "plan.md"
    preview_path.write_text(md, encoding="utf-8")
    return str(preview_path)

# ---------- 运行记录管理 ----------
def _run_dir(root: str) -> str:
    """创建运行目录"""
    ts = time.strftime("%Y%m%d_%H%M%S")
    d = Path(root) / ts
    d.mkdir(parents=True, exist_ok=True)
    return str(d)

def _rec_path(run_dir: str) -> Path:
    """获取记录文件路径"""
    return Path(run_dir) / "run.jsonl"

def append_run_record(run_dir: str, rec: dict) -> None:
    """追加运行记录"""
    p = _rec_path(run_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")

def save_lists(results: List[Dict[str, Any]], run_dir: str) -> int:
    """保存结果列表文件"""
    d = Path(run_dir)
    allp = d / "all_links.txt"
    hasp = d / "has_subs.txt"
    nop = d / "no_subs.txt"
    with allp.open("w", encoding="utf-8") as fa, \
         hasp.open("w", encoding="utf-8") as fh, \
         nop.open("w", encoding="utf-8") as fn:
        for r in results:
            u = r["url"]
            st = r.get("status", "")
            fa.write(u + "\n")
            if st == "has_subs":
                fh.write(u + "\n")
            elif st == "no_subs":
                fn.write(u + "\n")
    errs = [r["url"] for r in results if str(r.get("status", "")).startswith("error")]
    (d / "errors.txt").write_text("\n".join(dict.fromkeys(errs)) + "\n" if errs else "", "utf-8")
    return len(errs)

# ---------- 字幕验证 ----------
def _count_effective_lines_txt(fp: Path) -> int:
    """统计 TXT 有效行数"""
    try:
        n = 0
        for ln in fp.read_text('utf-8', errors='ignore').splitlines():
            if ln.strip():
                n += 1
        return n
    except Exception:
        return 0

def validate_subtitles_dir(subs_dir: str, min_lines_txt: int = 5) -> list:
    """验证字幕目录中的文件"""
    out = []
    d = Path(subs_dir)
    if not d.exists():
        return out
    for fp in d.glob('*.*'):
        if not fp.is_file():
            continue
        ext = fp.suffix.lower()
        if ext not in ('.txt', '.srt', '.vtt'):
            continue
        if ext == '.txt':
            n = _count_effective_lines_txt(fp)
        else:
            # SRT/VTT 简化验证
            n = _count_effective_lines_txt(fp)
        if n <= 0:
            out.append({"file": str(fp), "reason": "empty", "lines": n})
        elif n < max(1, int(min_lines_txt)):
            out.append({"file": str(fp), "reason": "too_short", "lines": n})
    return out

def write_warnings(run_dir: str, warnings: list) -> str:
    """写入警告文件"""
    if not warnings:
        return ""
    dst = Path(run_dir) / "warnings.txt"
    lines = []
    for w in warnings:
        lines.append(f"{w.get('reason','unknown')}\t{w.get('lines',0)}\t{w.get('file','')}")
    dst.write_text("\n".join(lines) + "\n", encoding='utf-8')
    return str(dst)

def _process_translations(run_dir: str, translate_config: dict, results: list[dict]) -> dict:
    """
    R2D4: 处理翻译任务（后处理阶段）
    
    Args:
        run_dir: 运行目录
        translate_config: 翻译配置 {"enabled": bool, "src": str, "tgt": str, "format": str, "provider": str}
        results: 检测结果列表
    
    Returns:
        {"translated": int, "provider": str, "files": list[str]}
    """
    if not translate_config or not translate_config.get("enabled", False):
        return {"translated": 0, "provider": "none", "files": []}
    
    from translator_bridge import translate_lines
    import re
    
    src = translate_config.get("src", "auto")
    tgt = translate_config.get("tgt", "en")
    fmt = translate_config.get("format", "srt")
    provider = translate_config.get("provider", "mock")
    
    subs_dir = Path(run_dir) / "subs"
    trans_dir = Path(run_dir) / "translations"
    trans_dir.mkdir(exist_ok=True, parents=True)
    
    translated_count = 0
    translated_files = []
    
    for r in results:
        if r.get("status") != "has_subs":
            continue
        
        vid = r.get("video_id", "")
        if not vid:
            continue
        
        # 确定源语言
        available_langs = (r.get("manual_langs") or []) + (r.get("auto_langs") or [])
        if not available_langs:
            continue
        
        # src="auto" 时取第一个可用语言
        if src == "auto":
            src_lang = str(available_langs[0]).lower()
        else:
            src_lang = src.lower()
        
        # 查找源字幕文件
        src_file = None
        for ext in [".txt", ".srt", ".vtt"]:
            # 尝试匹配文件名格式：video_id.lang.ext 或 video_id.ext
            candidates = list(subs_dir.glob(f"{vid}*.{src_lang}{ext}")) + list(subs_dir.glob(f"{vid}{ext}"))
            if candidates:
                src_file = candidates[0]
                break
        
        if not src_file or not src_file.exists():
            logging.info(f"[TRANSLATE] No source subtitle found for {vid} (lang={src_lang}), skipping")
            continue
        
        try:
            # 读取源字幕文本
            content = src_file.read_text(encoding="utf-8", errors="ignore")
            
            # 提取纯文本行（简化处理）
            if src_file.suffix.lower() == ".srt":
                # SRT: 跳过序号和时间轴，只取文本
                lines = []
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    # 跳过序号（纯数字）和时间轴（包含 -->）
                    if re.match(r'^\d+$', line) or '-->' in line:
                        continue
                    lines.append(line)
            elif src_file.suffix.lower() == ".vtt":
                # VTT: 跳过 WEBVTT 头和时间轴
                lines = []
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith('WEBVTT') or '-->' in line:
                        continue
                    lines.append(line)
            else:
                # TXT: 每行都是内容
                lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
            
            if not lines:
                logging.info(f"[TRANSLATE] No text lines extracted from {src_file.name}, skipping")
                continue
            
            # 翻译
            translated_lines, meta = translate_lines(lines, src_lang, tgt, provider=provider)
            
            # 写入译文文件
            out_file = trans_dir / f"{vid}.{tgt}.{fmt}"
            
            if fmt == "txt":
                # TXT: 每行一条
                out_file.write_text("\n".join(translated_lines) + "\n", encoding="utf-8")
            elif fmt in ("srt", "vtt"):
                # SRT/VTT: 简化实现（无时间轴，仅文本）
                # 完整实现需要保留原始时间轴，这里占位
                out_file.write_text("\n".join(translated_lines) + "\n", encoding="utf-8")
            
            translated_count += 1
            translated_files.append(str(out_file.relative_to(run_dir)))
            
            logging.info(f"[TRANSLATE] Translated: {vid} -> {tgt} (provider={provider}, fmt={fmt}, lines={len(lines)})")
            
        except Exception as e:
            logging.warning(f"[TRANSLATE] Failed to translate {vid}: {e}")
            continue
    
    # 保存翻译元信息
    meta_result = {
        "translated": translated_count,
        "provider": provider,
        "files": translated_files,
        "target_lang": tgt,
        "source_lang": src,
        "format": fmt
    }
    
    meta_file = trans_dir / "translation_meta.json"
    try:
        meta_file.write_text(json.dumps(meta_result, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
    
    return meta_result


def diagnose_run(run_dir: str) -> str:
    """
    诊断运行结果，生成分析报告
    
    返回诊断文本，同时写入 diagnose.txt
    """
    total = 0
    n_has = 0
    n_no = 0
    n_err = 0
    e429 = 0
    e503 = 0
    etimeout = 0
    eprivate = 0
    egeo = 0
    other = 0
    zh_hits = 0
    en_hits = 0
    
    rec_path = _rec_path(run_dir)
    if rec_path.exists():
        for ln in rec_path.read_text('utf-8', errors='ignore').splitlines():
            try:
                r = json.loads(ln)
            except Exception:
                continue
            total += 1
            st = str(r.get('status', ''))
            if st == 'has_subs':
                n_has += 1
            elif st == 'no_subs':
                n_no += 1
            elif st.startswith('error'):
                n_err += 1
                if st == 'error_429':
                    e429 += 1
                elif st == 'error_503':
                    e503 += 1
                elif st == 'error_timeout':
                    etimeout += 1
                elif st == 'error_private':
                    eprivate += 1
                elif st == 'error_geo':
                    egeo += 1
                else:
                    other += 1
            for lc in (r.get('manual_langs') or []) + (r.get('auto_langs') or []):
                lc = (lc or '').lower()
                if lc == 'zh' or lc.startswith(('zh', 'cmn')):
                    zh_hits += 1
                elif lc == 'en' or lc.startswith('en'):
                    en_hits += 1
    
    warn_path = Path(run_dir) / "warnings.txt"
    warn_count = 0
    short_count = 0
    empty_count = 0
    if warn_path.exists():
        for ln in warn_path.read_text('utf-8', errors='ignore').splitlines():
            warn_count += 1
            seg = ln.split('\t')
            if seg:
                if seg[0] == 'too_short':
                    short_count += 1
                elif seg[0] == 'empty':
                    empty_count += 1
    
    pieces = []
    pieces.append(f"总计 {total} 个链接：✅ 有字幕 {n_has}，➖ 无字幕 {n_no}，❗ 错误 {n_err}。")
    if n_err and total:
        ratio = n_err / max(1, total)
        pieces.append(f"错误占比：{ratio:.1%}（429={e429}, 503={e503}, timeout={etimeout}, private={eprivate}, geo={egeo}, 其它={other}）")
        if e429 > 0:
            pieces.append("建议：降低 req_rate 或增大 breaker_cooldown_sec；代理质量差时可切换 detect_mode='fast'。")
        if e503 > 0:
            pieces.append("建议：放慢并发或改用健康代理；增大批处理间隔（batch sleep）。")
        if etimeout > 0:
            pieces.append("建议：增大 timeout 或检查网络稳定性；使用更快的代理。")
        if ratio >= 0.3 and e429 == 0 and e503 == 0:
            pieces.append("建议：检查 cookies/地区/私有视频；或将 detect_mode='standard' 改为 'fast' 做对比。")
    else:
        pieces.append("错误占比很低，整体稳定。")
    
    if zh_hits == 0 and en_hits > 0:
        pieces.append("观察：英文字幕较多而中文为 0。可在设置里启用自动字幕（prefer='both'）同时保留英文回退。")
    if warn_count > 0:
        pieces.append(f"字幕内容告警 {warn_count} 条（空={empty_count}，过短={short_count}）。可以提高 min_lines_txt 阈值或人工抽查。")
    
    pieces.append("若为升级测试，可先用 dry_run / 小样本批次跑，确认稳定后再全量。")
    
    diagnose_text = "\n".join(pieces)
    
    # 写入文件
    try:
        dst = Path(run_dir) / "diagnose.txt"
        dst.write_text(diagnose_text, encoding='utf-8')
    except Exception:
        pass
    
    return diagnose_text

def run_full_process(
    channel_or_playlist_url: str = "",
    output_root: str = "out",
    max_workers: int = 5,
    sleep_between: float = 0.5,
    retry_times: int = 2,
    max_items: int = 0,
    do_download: bool = False,
    download_langs: list[str] | None = None,
    download_prefer: str = "both",
    download_fmt: str = "srt",
    progress_callback: Callable[[int, int, str], None] | None = None,
    stop_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    urls_override: list[str] | None = None,
    file_path: str | None = None,
    user_agent: str = "",
    proxy_text: str = "",
    proxy_mode: str = "round_robin",
    proxy_cool_down_sec: int = 300,
    proxy_max_fails: int = 2,
    proxy_blacklist_threshold: float = 0.15,
    proxy_window: int = 30,
    cookiefile: str = "",
    incremental_detect: bool = True,
    incremental_download: bool = True,
    force_refresh: bool = False,
    batch_size: int = 0,
    merge_bilingual: bool = False,
    detect_mode: str = "standard",
    adaptive_concurrency: bool = False,
    min_workers: int = 2,
    max_workers_cap: int = 20,
    early_stop_on_seen: bool = True,
    req_rate: float = 4.0,
    breaker_threshold: int = 8,
    breaker_cooldown_sec: float = 120.0,
    dry_run: bool = False,
    preferred_langs: list[str] | None = None,
    webhook_config: dict | None = None,
    translate_config: dict | None = None,
    postprocess_config: dict | None = None,
    quality_config: dict | None = None,
) -> dict:
    """
    主流程：检测 → 下载 → 记录 + Webhook 通知
    
    webhook_config: {url, timeout_sec, max_retry, secret, enable, events}
    
    Return:
    {"run_dir": str, "total": int, "downloaded": int, "errors": int, "last_seen": str|None}
    """
    Path(output_root).mkdir(parents=True, exist_ok=True)
    run_dir = _run_dir(output_root)
    
    # Webhook 辅助函数（fire-and-forget）
    def _fire_webhook(event: str, payload: dict):
        if not webhook_config or not webhook_config.get("enable"):
            return
        events_filter = webhook_config.get("events", [])
        if events_filter and event not in events_filter:
            return
        
        def _send():
            try:
                _send_webhook_with_retry(
                    webhook_config.get("url", ""),
                    {"event": event, "ts": _ts_utc(), **payload},
                    webhook_config.get("timeout_sec", 5),
                    webhook_config.get("max_retry", 3),
                    webhook_config.get("secret", "")
                )
            except Exception as e:
                try:
                    wf = Path(run_dir) / "warnings.txt"
                    with wf.open("a", encoding="utf-8") as f:
                        f.write(f"webhook_fail\t{event}\t{str(e)[:100]}\n")
                except:
                    pass
        
        threading.Thread(target=_send, daemon=True).start()
    
    # Webhook: run_start
    _fire_webhook("run_start", {
        "channel": channel_or_playlist_url,
        "output_root": output_root,
        "config": {
            "max_workers": max_workers,
            "do_download": do_download,
            "download_langs": download_langs or [],
            "dry_run": dry_run
        }
    })
    
    if progress_callback:
        progress_callback(-1, 0, "阶段：准备环境/解析输入")
    
    # 构建代理池和限流器
    pool = build_proxy_pool(
        proxy_text, mode=proxy_mode, proxy_cool_down_sec=proxy_cool_down_sec,
        proxy_max_fails=proxy_max_fails, proxy_blacklist_threshold=proxy_blacklist_threshold,
        proxy_window=proxy_window
    )
    limiter = RateLimiter(req_rate, int(req_rate * 2)) if req_rate > 0 else None
    breaker = CircuitBreaker(breaker_threshold, breaker_cooldown_sec)
    
    # 获取待检测的 URLs（保留所有URL，包括重复的，但标准化格式）
    urls = []
    if urls_override:
        for u in urls_override:
            u_clean = u.strip()
            if u_clean:
                # 标准化URL格式
                u_normalized = normalize_url(u_clean)
                urls.append(u_normalized)
        
        # 输出调试信息
        logger.debug(f"URLs处理: 输入{len(urls_override)}个，处理{len(urls)}个")
        if len(urls_override) != len(set(urls)):
            logger.debug("注意：输入中有重复URL，将分别处理")
    elif file_path and os.path.exists(file_path):
        urls = [normalize_url(ln.strip()) for ln in open(file_path, "r", encoding="utf-8") if ln.strip()]
    elif channel_or_playlist_url:
        if progress_callback:
            progress_callback(-1, 0, "阶段：抓取频道/播放列表")
        p = pool.get() if pool else ""
        urls = extract_all_video_urls_from_channel_or_playlist(
            channel_or_playlist_url, proxy=p, user_agent=user_agent, cookiefile=cookiefile
        )
    
    # 增量策略：读取上次 last_seen
    chan_idx = channel_index_load(output_root) if incremental_detect else {}
    last_seen = None
    chan_key = None
    if channel_or_playlist_url:
        chan_key = ensure_channel_videos_url(channel_or_playlist_url)
        last_seen = chan_idx.get(chan_key)
    
    # Dry 模式提示
    if dry_run:
        logging.info(f"[DRY RUN] 预览模式：仅检测，不下载/AI，共 {len(urls)} 个URL")
    
    if progress_callback:
        progress_callback(-1, len(urls), f"共 {len(urls)} 个链接，开始检测字幕")
        if dry_run:
            progress_callback(-1, len(urls), "[DRY RUN] 仅检测不下载")
    
    # 检测字幕
    det_results = detect_links(
        urls, max_workers=max_workers, sleep_between=sleep_between, retry_times=retry_times,
        progress_callback=progress_callback, user_agent=user_agent, proxy_pool=pool,
        cookiefile=cookiefile, stop_event=stop_event, pause_event=pause_event,
        batch_size=batch_size, detect_mode=detect_mode, adaptive_concurrency=adaptive_concurrency,
        min_workers=min_workers, max_workers_cap=max_workers_cap, rate_limiter=limiter,
        circuit_breaker=breaker
    )
    
    # 统一变量名，兜底为列表（防止 None）
    results = det_results or []
    if not isinstance(results, list):
        results = list(results)
    
    # 调试输出：显示检测结果
    logger.debug(f"检测完成: 输入{len(urls)}个URL，检测结果{len(results)}个")
    if len(urls) != len(results):
        logger.warning("URL数量和检测结果数量不一致")
        logger.debug(f"  - 输入URLs: {[normalize_url(u) for u in urls[:5]]}{'...' if len(urls) > 5 else ''}")
        logger.debug(f"  - 检测结果URLs: {[r.get('url', '') for r in results[:5]]}{'...' if len(results) > 5 else ''}")
        logger.debug(f"  - 检测结果数量: {len(results)}")
    
    # 检查是否有重复URL的检测结果被合并了
    result_urls = [r.get('url', '') for r in results]
    if len(result_urls) != len(set(result_urls)):
        logger.debug("发现重复URL在检测结果中，将分别处理每个结果")
    
    errs = save_lists(results, run_dir)
    
    newest = last_seen
    downloaded = 0
    skipped = 0
    failed = 0
    
    # 跟踪已下载的video_id，避免重复下载相同视频
    downloaded_vids = set()
    
    # 批量重试：记录失败的项
    failed_items = []  # 用于批量重试失败的项目
    
    # 进度统计
    start_time = time.perf_counter()
    last_progress_time = start_time
    
    # 批量操作状态跟踪
    current_item_index = 0  # 当前处理的项索引
    current_item_id = ""    # 当前处理的视频ID
    current_item_start_time = None  # 当前项开始时间
    
    def _send_progress_update(current: int, total: int, message: str, stats: dict = None, current_item: str = None):
        """发送进度更新（带统计信息和当前项信息）"""
        if progress_callback:
            # 如果 message 是 dict，说明已经是格式化的进度数据
            if isinstance(message, dict):
                progress_data = message
            else:
                # 否则构建进度数据
                progress_data = {
                    "current": current,
                    "total": total,
                    "message": message,
                    "percentage": (current / total * 100) if total > 0 else 0
                }
                if stats:
                    progress_data.update(stats)
            
            # 添加当前项信息
            if current_item:
                progress_data["current_item"] = current_item
                progress_data["current_item_index"] = current_item_index + 1
            
            # 计算当前项耗时
            if current_item_start_time:
                progress_data["current_item_elapsed"] = time.perf_counter() - current_item_start_time
            
            # 适配器会将 dict 转换为 (current, total, message) 格式
            progress_callback(-1, total, progress_data)
    
    for idx, r in enumerate(results):
        # 检查停止事件
        if stop_event and stop_event.is_set():
            if progress_callback:
                _send_progress_update(
                    downloaded + skipped + failed, len(results),
                    f"⏹️ 用户停止操作",
                    {
                        "downloaded": downloaded,
                        "skipped": skipped,
                        "failed": failed,
                        "phase": "stopped"
                    }
                )
            break
        
        # 检查暂停事件
        while pause_event and pause_event.is_set():
            if stop_event and stop_event.is_set():
                break
            time.sleep(0.1)
            if progress_callback and int(time.time()) % 2 == 0:  # 每2秒显示一次暂停状态
                _send_progress_update(
                    downloaded + skipped + failed, len(results),
                    f"⏸️ 已暂停... (按继续按钮恢复)",
                    {
                        "downloaded": downloaded,
                        "skipped": skipped,
                        "failed": failed,
                        "phase": "paused"
                    }
                )
        
        current_item_index = idx
        current_item_id = r.get("video_id", "")
        current_item_start_time = time.perf_counter()
        
        meta = r.get("meta") or {}
        # 修复：upload_date可能在顶层或meta中
        up = r.get("upload_date") or meta.get("upload_date")  # "YYYYMMDD"
        vid = r.get("video_id")
        is_new = (not last_seen) or (up and up > last_seen)
        
        # 语言选择逻辑：优先匹配所有selected_langs中在available_langs里的语言
        available_langs = (r.get("manual_langs") or []) + (r.get("auto_langs") or [])
        selected_langs = download_langs or ["zh", "en"]
        final_langs = [x.lower() for x in selected_langs]
        fallback_reason = None
        
        # 调试：显示原始检测结果
        logger.debug(f"Video {vid} language detection:")
        logger.debug(f"  - manual_langs (raw): {r.get('manual_langs')}")
        logger.debug(f"  - auto_langs (raw): {r.get('auto_langs')}")
        logger.debug(f"  - available_langs (combined): {available_langs}")
        logger.debug(f"  - selected_langs (from config): {selected_langs}")
        
        # 语言选择逻辑：优先匹配所有selected_langs中在available_langs里的语言
        # 如果preferred_langs为None，直接使用selected_langs匹配
        tmp = []  # 初始化tmp变量
        if preferred_langs is not None:
            seen = set()
            tmp = []
            # 首先添加 preferred_langs 中在 available_langs 中的语言
            for pl in preferred_langs:
                pl_l = (pl or "").lower()
                # 检查是否有可用语言匹配（支持前缀匹配，如 zh-Hans 匹配 zh）
                matched = False
                for avail_lang in available_langs:
                    avail_l = (avail_lang or "").lower()
                    if avail_l.startswith(pl_l) or pl_l.startswith(avail_l.split('-')[0]):
                        matched = True
                        break
                if matched and pl_l not in seen:
                    tmp.append(pl_l)
                    seen.add(pl_l)
            
            # 如果 preferred_langs 匹配到了语言，使用它们；否则尝试 fallback
            if tmp:
                final_langs = tmp
            else:
                # Fallback: 使用所有在 available_langs 中的 selected_langs
                tmp = []
                for sl in selected_langs:
                    sl_l = (sl or "").lower()
                    # 检查是否有可用语言匹配
                    for avail_lang in available_langs:
                        avail_l = (avail_lang or "").lower()
                        if avail_l.startswith(sl_l) or sl_l.startswith(avail_l.split('-')[0]):
                            if sl_l not in seen:
                                tmp.append(sl_l)
                                seen.add(sl_l)
                            break
                
                if tmp:
                    final_langs = tmp
                elif available_langs:
                    # 最后的 fallback: 使用第一个可用语言
                    final_langs = [str(available_langs[0]).lower()]
                    fallback_reason = f"fallback\t{','.join(selected_langs)}-> {final_langs[0]}\t{vid}"
        else:
            # 如果没有 preferred_langs，直接匹配所有 selected_langs 中在 available_langs 里的语言
            tmp = []
            seen = set()
            for sl in selected_langs:
                sl_l = (sl or "").lower()
                # 遍历所有可用语言，找到匹配的就添加（不要break，确保匹配所有语言）
                matched = False
                for avail_lang in available_langs:
                    avail_l = (avail_lang or "").lower()
                    # 支持前缀匹配（zh-Hans 匹配 zh，或 zh 匹配 zh-Hans）
                    if avail_l.startswith(sl_l) or sl_l.startswith(avail_l.split('-')[0]):
                        if sl_l not in seen:
                            tmp.append(sl_l)
                            seen.add(sl_l)
                            matched = True
                            break  # 找到一个匹配就退出内层循环，继续下一个 selected_lang
                # 如果没有匹配到，记录日志（但不阻止处理）
                if not matched:
                    logger.debug(f"语言 {sl_l} 在可用语言 {list(available_langs)} 中未找到匹配")
            
            if tmp:
                final_langs = tmp
            elif available_langs:
                # Fallback: 使用第一个可用语言
                final_langs = [str(available_langs[0]).lower()]
                fallback_reason = f"fallback\t{','.join(selected_langs)}-> {final_langs[0]}\t{vid}"
        
        # 重要修复：即使检测时没有检测到所有语言，也尝试下载所有配置的语言
        # 因为 yt-dlp 在实际下载时可能会返回更多可用语言
        if tmp and len(tmp) < len(selected_langs):
            # 如果检测到了一些语言但少于配置的语言，尝试补充（让yt-dlp尝试）
            # 添加未匹配到的配置语言
            missing_langs = [sl.lower() for sl in selected_langs if sl.lower() not in tmp]
            if missing_langs:
                logger.debug(f"检测到部分语言 {tmp}，将尝试补充: {missing_langs}")
                final_langs = tmp + missing_langs  # 合并已匹配和未匹配的语言
        elif not tmp and not available_langs:
            # 如果完全没有检测到语言，尝试所有配置的语言（让yt-dlp尝试）
            final_langs = [x.lower() for x in selected_langs]
            logger.debug(f"未检测到任何语言，将尝试下载所有配置的语言: {final_langs}")
        
        final_langs = [x for i, x in enumerate(final_langs) if x and x not in final_langs[:i]]
        
        # 调试输出：打印语言选择结果
        logger.debug(f"Video {vid} language selection:")
        logger.debug(f"  - selected_langs (from config): {selected_langs}")
        logger.debug(f"  - available_langs: {list(available_langs)}")
        logger.debug(f"  - preferred_langs: {preferred_langs}")
        logger.debug(f"  - final_langs (will download): {final_langs}")
        if fallback_reason:
            logger.debug(f"  - fallback_reason: {fallback_reason}")
        
        # 记录运行日志（检测阶段）
        append_run_record(run_dir, {
            "action": "detect",  # 动作标识：检测
            "ts": _ts_utc(),
            "url": r["url"],
            "video_id": vid,
            "status": r.get("status"),
            "manual_langs": r.get("manual_langs", []),
            "auto_langs": r.get("auto_langs", []),
            "proxy": "",
            "latency_ms": r.get("latency_ms"),
            "attempts": r.get("attempts"),
            "detector": "yta+ydlp" if detect_mode == "standard" else "ytdlp",
            "err": r.get("api_err"),
            "title": meta.get("title"),
            "channel": meta.get("channel") or meta.get("uploader"),
            "upload_date": up,
            "duration": meta.get("duration"),
            "view_count": meta.get("view_count"),
            "tags": meta.get("tags") or [],
            "final_langs": final_langs
        })
        history_append(output_root, {"video_id": vid, "upload_date": up, "ts": _ts_utc()})
        
        # Step 3 Day1: 写入统一历史记录
        # Day2: 使用增强的错误分类
        if _HISTORY_AVAILABLE:
            try:
                has_subs = r.get("status") == "has_subs"
                error_msg = r.get("api_err") if r.get("status", "").startswith("error") else None
                
                # Day2: 使用 v2 版本获取完整错误信息
                status, error_code, error_msg_simplified, error_class, retryable = classify_status_v2(error_msg, has_subs)
                
                history_row: HistoryRow = {
                    "video_id": vid or "",
                    "url": r.get("url", ""),
                    "title": meta.get("title", ""),
                    "channel": meta.get("channel") or meta.get("uploader") or "",
                    "status": status,
                    "error_code": error_code,
                    "error_msg": error_msg_simplified,
                    "error_class": error_class,
                    "retryable": retryable,
                    "langs": available_langs,
                    "upload_date": up or "",
                    "duration": meta.get("duration", 0) or 0,
                    "view_count": meta.get("view_count", 0) or 0,
                }
                write_history(run_dir, history_row)
            except Exception as e:
                logging.warning(f"写入历史记录失败: {e}")
        
        if up and (not newest or up > newest):
            newest = up
        
        # 下载字幕（dry 模式跳过）
        # DEBUG: 打印下载条件判断
        logger.debug(f"Video {vid} download check:")
        logger.debug(f"  - dry_run: {dry_run}")
        logger.debug(f"  - do_download: {do_download}")
        logger.debug(f"  - status: {r.get('status')}")
        logger.debug(f"  - is_new: {is_new}")
        logger.debug(f"  - last_seen: {last_seen}")
        logger.debug(f"  - upload_date: {up}")
        logger.debug(f"  - force_refresh: {force_refresh}")
        # 基础条件：非dry_run、开启下载
        # 如果检测到有字幕，或者用户强制刷新/明确配置了下载语言，都应该尝试下载
        # 因为 yt-dlp 在实际下载时可能会检测到字幕（即使检测阶段没有检测到）
        has_detected_subs = r.get("status") == "has_subs"
        user_requested_langs = bool(final_langs)  # 用户明确配置了要下载的语言
        should_try_download = has_detected_subs or force_refresh or user_requested_langs
        
        will_download = (not dry_run) and do_download and should_try_download
        # 强制刷新时忽略is_new判断，否则需要检查is_new
        if not force_refresh:
            will_download = will_download and is_new
        logger.debug(f"  - Will download: {will_download} (has_subs={has_detected_subs}, force_refresh={force_refresh}, user_langs={user_requested_langs})")
        
        if will_download:
            # 如果force_refresh=False，检查是否已下载过相同video_id
            if not force_refresh and vid in downloaded_vids:
                logger.debug(f"跳过重复视频 {vid}（已下载）")
                skipped += 1
                # 发送进度更新
                current_progress = downloaded + skipped + failed
                if progress_callback and current_progress % 5 == 0:  # 每5个更新一次
                    elapsed = time.perf_counter() - start_time
                    speed = current_progress / elapsed if elapsed > 0 else 0
                    remaining = (len(results) - current_progress) / speed if speed > 0 else 0
                    _send_progress_update(
                        current_progress, len(results),
                        f"处理中: {current_progress}/{len(results)} (✓{downloaded} ⚠{skipped} ✗{failed})",
                        {
                            "downloaded": downloaded,
                            "skipped": skipped,
                            "failed": failed,
                            "speed": speed,
                            "remaining": remaining
                        }
                    )
                continue
            
            logger.debug(f"Starting download for {vid}...")
            
            # 通过progress_callback发送下载开始消息（带当前项信息）
            if progress_callback:
                _send_progress_update(
                    downloaded + skipped + failed, len(results),
                    f"开始下载: {vid} ({', '.join(final_langs)})",
                    {
                        "downloaded": downloaded,
                        "skipped": skipped,
                        "failed": failed,
                        "phase": "downloading"
                    },
                    current_item=vid
                )
            
            t0_dl = time.perf_counter()
            paths = download_subtitles(
                r["url"], str(Path(run_dir) / "subs"), final_langs, download_prefer, download_fmt,
                user_agent=user_agent, proxy_pool=pool, cookiefile=cookiefile,
                stop_event=stop_event, pause_event=pause_event, retry_times=retry_times,
                base_sleep=sleep_between, incremental=incremental_download,
                merge_bilingual=merge_bilingual, rate_limiter=limiter, circuit_breaker=breaker
            )
            downloaded += int(bool(paths))
            
            # 更新统计
            if not paths:
                failed += 1
                # 记录失败项，用于批量重试
                failed_items.append({
                    "video_id": vid,
                    "url": r["url"],
                    "status": r.get("status"),
                    "available_langs": available_langs,
                    "final_langs": final_langs,
                    "error": "download_failed"
                })
            
            # 发送下载完成消息（带统计）
            current_progress = downloaded + skipped + failed
            elapsed = time.perf_counter() - start_time
            speed = current_progress / elapsed if elapsed > 0 else 0
            remaining = (len(results) - current_progress) / speed if speed > 0 else 0
            
            if progress_callback:
                if paths:
                    _send_progress_update(
                        current_progress, len(results),
                        f"✅ {vid}: 下载成功 ({len(paths)} 个文件)",
                        {
                            "downloaded": downloaded,
                            "skipped": skipped,
                            "failed": failed,
                            "speed": speed,
                            "remaining": remaining,
                            "phase": "download_complete"
                        },
                        current_item=vid
                    )
                else:
                    _send_progress_update(
                        current_progress, len(results),
                        f"⚠️ {vid}: 下载失败",
                        {
                            "downloaded": downloaded,
                            "skipped": skipped,
                            "failed": failed,
                            "speed": speed,
                            "remaining": remaining,
                            "phase": "download_failed"
                        },
                        current_item=vid
                    )
            
            # 记录下载动作
            if paths:
                downloaded_vids.add(vid)  # 记录已下载的video_id
                
                # 字幕优化（下载完成后）
                optimize_result = None
                if (postprocess_config and postprocess_config.get("enabled", False)) or \
                   (quality_config and quality_config.get("enabled", False)):
                    try:
                        from services.subtitle_optimize_service import SubtitleOptimizeService
                        
                        optimize_config = {
                            "postprocess": postprocess_config or {},
                            "quality": quality_config or {}
                        }
                        optimize_service = SubtitleOptimizeService(optimize_config)
                        
                        # 批量优化下载的字幕文件
                        optimize_result = optimize_service.optimize_subtitle_files(paths)
                        
                        if optimize_result.get("optimized", 0) > 0:
                            logging.info(
                                f"[OPTIMIZE] {vid}: 优化了 {optimize_result['optimized']}/{optimize_result['total']} 个字幕文件"
                            )
                    except Exception as e:
                        logging.warning(f"[OPTIMIZE] 字幕优化失败: {e}")
                        optimize_result = {"error": str(e)}
                
                append_run_record(run_dir, {
                    "action": "download",  # 动作标识：下载
                    "ts": _ts_utc(),
                    "url": r["url"],
                    "video_id": vid,
                    "status": "success",
                    "files": [str(p) for p in paths],
                    "langs": final_langs,
                    "format": download_fmt,
                    "latency_ms": (time.perf_counter() - t0_dl) * 1000.0,
                    "optimize": optimize_result  # 添加优化结果
                })
            
            if fallback_reason:
                wf = Path(run_dir) / "warnings.txt"
                try:
                    with wf.open("a", encoding="utf-8") as wfo:
                        wfo.write(f"{fallback_reason}\n")
                except Exception:
                    pass
    
    # B1: ASR 无字幕补全（检测/下载后）
    asr_result = {"completed": 0, "provider": "none", "files": []}
    asr_config = translate_config.get("asr", {}) if translate_config else {}
    
    # 从配置加载 ASR 设置
    if not asr_config:
        try:
            from .config import load_config
            cfg = load_config()
            asr_config = cfg.get("asr", {})
        except Exception:
            pass
    
    if not dry_run and asr_config.get("enabled", False):
        try:
            from .asr_bridge import run_asr
            
            if progress_callback:
                progress_callback(-1, len(urls), "阶段：ASR 补全")
            
            asr_dir = Path(run_dir) / "asr"
            asr_dir.mkdir(exist_ok=True, parents=True)
            
            for r in results:
                # 只对无字幕或无目标语的视频执行 ASR
                if r.get("status") in ("no_subs",) or not r.get("manual_langs", []):
                    try:
                        asr_res = run_asr(
                            video_url=r.get("url", ""),
                            provider=asr_config.get("provider", "mock"),
                            lang_hint=asr_config.get("lang_hint", "auto"),
                            out_dir=str(asr_dir),
                            timeout=asr_config.get("timeout", 120)
                        )
                        
                        if asr_res.get("success"):
                            # 标注视频已有字幕（ASR 生成）
                            r["status"] = "has_subs"
                            r.setdefault("manual_langs", []).append(asr_res.get("lang", ""))
                            asr_result["completed"] += 1
                            asr_result["files"].append(asr_res.get("file", ""))
                            asr_result["provider"] = asr_config.get("provider", "mock")
                            
                            logging.info(f"[ASR-B1] 完成: {r.get('video_id')} -> {asr_res.get('file')}")
                    
                    except Exception as e:
                        logging.warning(f"[ASR-B1] 失败 {r.get('video_id')}: {e}")
            
            if asr_result["completed"] > 0:
                logging.info(f"[ASR-B1] 补全完成: {asr_result['completed']} 个视频 (provider={asr_result['provider']})")
        
        except Exception as e:
            logging.warning(f"[ASR-B1] ASR 补全失败: {e}")
    
    # 验证字幕文件（dry 模式跳过）
    warnings = []
    if not dry_run:
        warnings = validate_subtitles_dir(str(Path(run_dir) / "subs"), min_lines_txt=5)
        write_warnings(run_dir, warnings)
    else:
        logging.info(f"[DRY RUN] 跳过字幕验证")
    
    # R2D4: 翻译处理（后处理阶段）
    translation_result = {"translated": 0, "provider": "none", "files": [], "target_lang": ""}
    if not dry_run and translate_config:
        try:
            if progress_callback:
                progress_callback(-1, len(urls), "阶段：翻译字幕")
            translation_result = _process_translations(run_dir, translate_config, results)
            if translation_result.get("translated", 0) > 0:
                logging.info(f"[TRANSLATE] 完成翻译：{translation_result['translated']} 个视频 -> {translation_result.get('target_lang', 'unknown')}")
        except Exception as e:
            logging.warning(f"[TRANSLATE] 翻译处理失败: {e}")
    
    # A2: 中文清洗与术语统一（翻译后处理）
    cleanup_result = {"cleaned": 0, "terminology_replaced": 0, "lines_merged": 0}
    if not dry_run and translate_config and translate_config.get("postprocess", True):
        try:
            from .cleanup_zh import clean_subtitle_file, load_terminology
            
            if progress_callback:
                progress_callback(-1, len(urls), "阶段：清洗与术语统一")
            
            # 加载术语表
            terminology = load_terminology("terminology.json")
            
            # 处理翻译后的文件
            trans_dir = Path(run_dir) / "translations"
            if trans_dir.exists():
                for trans_file in trans_dir.glob("*.txt"):
                    try:
                        stats = clean_subtitle_file(
                            input_file=str(trans_file),
                            output_file=None,  # 覆盖原文件
                            terminology_file="terminology.json",
                            merge_enabled=True
                        )
                        cleanup_result["cleaned"] += 1
                        cleanup_result["terminology_replaced"] += stats.get("terminology_replaced", 0)
                        cleanup_result["lines_merged"] += stats.get("lines_merged", 0)
                    except Exception as e:
                        logging.warning(f"[CLEANUP-A2] 清洗失败 {trans_file.name}: {e}")
            
            # 也处理 ASR 生成的文件（如果是中文）
            asr_dir = Path(run_dir) / "asr"
            if asr_dir.exists():
                for asr_file in asr_dir.glob("*.txt"):
                    try:
                        stats = clean_subtitle_file(
                            input_file=str(asr_file),
                            output_file=None,
                            terminology_file="terminology.json",
                            merge_enabled=True
                        )
                        cleanup_result["cleaned"] += 1
                        cleanup_result["terminology_replaced"] += stats.get("terminology_replaced", 0)
                        cleanup_result["lines_merged"] += stats.get("lines_merged", 0)
                    except Exception as e:
                        logging.warning(f"[CLEANUP-A2] 清洗ASR文件失败 {asr_file.name}: {e}")
            
            if cleanup_result["cleaned"] > 0:
                logging.info(
                    f"[CLEANUP-A2] 完成清洗: {cleanup_result['cleaned']} 个文件 "
                    f"(术语={cleanup_result['terminology_replaced']}, 合并={cleanup_result['lines_merged']})"
                )
        
        except Exception as e:
            logging.warning(f"[CLEANUP-A2] 清洗处理失败: {e}")
    
    # CD线: 双语字幕合并（后处理阶段）
    bilingual_result = {"total": 0, "success": 0, "files": [], "format": ""}
    if not dry_run and merge_bilingual:
        try:
            from .exports import export_bilingual_subtitles
            from .config import load_config
            import sys
            
            if progress_callback:
                progress_callback(-1, len(urls), "阶段：生成双语字幕")
            
            # 从配置读取双语设置
            cfg = load_config()
            bi_cfg = cfg.get("bilingual", {})
            
            logger.info("="*60)
            logger.info("[BILINGUAL] 开始双语字幕合并...")
            logger.info(f"  - 主语言: {bi_cfg.get('primary', 'auto')}")
            logger.info(f"  - 次语言: {bi_cfg.get('secondary', 'en')}")
            logger.info(f"  - 输出格式: {bi_cfg.get('format', 'tsv')}")
            logger.info(f"  - 输出目录: {bi_cfg.get('output_dir', 'bilingual')}")
            logger.info("="*60)
            
            bilingual_result = export_bilingual_subtitles(
                run_dir=run_dir,
                primary_lang=bi_cfg.get("primary", "auto"),
                secondary_lang=bi_cfg.get("secondary", "en"),
                output_format=bi_cfg.get("format", "tsv"),
                output_subdir=bi_cfg.get("output_dir", "bilingual")
            )
            
            # 输出详细结果
            total = bilingual_result.get("total", 0)
            success = bilingual_result.get("success", 0)
            failed = total - success
            format_type = bilingual_result.get("format", "tsv")
            files = bilingual_result.get("files", [])
            
            logger.info("="*60)
            logger.info("[BILINGUAL] 双语合并完成")
            logger.info(f"  - 总计: {total} 个视频")
            logger.info(f"  - 成功: {success} 个")
            if failed > 0:
                logger.info(f"  - 跳过: {failed} 个（可能缺少双语字幕）")
            logger.info(f"  - 格式: {format_type.upper()}")
            if files:
                logger.info("  - 生成文件:")
                for f in files[:5]:  # 只显示前5个
                    logger.info(f"    • {f}")
                if len(files) > 5:
                    logger.info(f"    ... 还有 {len(files) - 5} 个文件")
            logger.info("="*60)
            
            if success > 0:
                logging.info(f"[BILINGUAL] 完成双语合并：{success}/{total} 个视频 (格式={format_type})")
            elif total > 0:
                logging.warning(f"[BILINGUAL] 双语合并：{total} 个视频全部跳过（可能缺少双语字幕）")
        except Exception as e:
            logger.error(f"[BILINGUAL] 双语合并失败: {e}", exc_info=True)
    
    # 生成诊断报告 / dry 模式生成预览
    try:
        if not dry_run:
            diagnose_text = diagnose_run(run_dir)
        else:
            # Dry 模式生成预览报告
            _generate_dry_preview(run_dir, results)
            logging.info(f"[DRY RUN] 预览报告已生成：{run_dir}/plan.md")
    except Exception as e:
        logging.warning(f"诊断/预览报告生成失败: {e}")
    
    # 更新频道索引（dry 模式不更新，避免污染）
    if not dry_run and chan_key and newest and (not last_seen or newest > last_seen):
        chan_idx[chan_key] = newest
        channel_index_save(output_root, chan_idx)
    
    # 保存配置快照
    from .config import save_config_snapshot
    try:
        final_config = {
            "output_root": output_root,
            "max_workers": max_workers,
            "sleep_between": sleep_between,
            "retry_times": retry_times,
            "max_items": max_items,
            "do_download": do_download,
            "download_langs": download_langs,
            "download_prefer": download_prefer,
            "download_fmt": download_fmt,
            "user_agent": user_agent,
            "proxy_mode": proxy_mode,
            "proxy_cool_down_sec": proxy_cool_down_sec,
            "proxy_max_fails": proxy_max_fails,
            "cookiefile": cookiefile,
            "incremental_detect": incremental_detect,
            "incremental_download": incremental_download,
            "force_refresh": force_refresh,
            "batch_size": batch_size,
            "merge_bilingual": merge_bilingual,
            "detect_mode": detect_mode,
            "adaptive_concurrency": adaptive_concurrency,
            "min_workers": min_workers,
            "max_workers_cap": max_workers_cap,
            "early_stop_on_seen": early_stop_on_seen,
            "req_rate": req_rate,
            "breaker_threshold": breaker_threshold,
            "breaker_cooldown_sec": breaker_cooldown_sec,
            "dry_run": dry_run,
            "preferred_langs": preferred_langs
        }
        save_config_snapshot(run_dir, final_config)
    except Exception:
        pass
    
    # 最终统计
    if progress_callback:
        elapsed_total = time.perf_counter() - start_time
        avg_speed = len(results) / elapsed_total if elapsed_total > 0 else 0
        _send_progress_update(
            len(results), len(results),
            f"✓ 完成: {downloaded} 成功, {skipped} 跳过, {failed} 失败",
            {
                "downloaded": downloaded,
                "skipped": skipped,
                "failed": failed,
                "speed": avg_speed,
                "remaining": 0,
                "elapsed": elapsed_total
            }
        )
    # Webhook: run_end
    from .net import get_current_proxy_stats
    proxy_stats = get_current_proxy_stats() or {}
    proxy_blacklist_count = sum(1 for st in proxy_stats.values() if st.get("black"))
    
    # 错误统计
    error_breakdown = {}
    for r in results:
        st = r.get("status", "")
        if str(st).startswith("error"):
            error_breakdown[st] = error_breakdown.get(st, 0) + 1
    
    _fire_webhook("run_end", {
        "run_dir": run_dir,
        "stats": {
            "total": len(urls),
            "downloaded": downloaded,
            "errors": errs,
            "error_breakdown": error_breakdown
        },
        "proxies": {"blacklisted": proxy_blacklist_count},
        "warnings_count": len(warnings) if warnings else 0
    })
    
    # A2+B1: 保存管线元数据（供报告使用）
    try:
        pipeline_meta = {
            "asr": asr_result,
            "cleanup": cleanup_result,
            "translation": translation_result,
            "bilingual": bilingual_result
        }
        pipeline_meta_file = Path(run_dir) / "pipeline_meta.json"
        with open(pipeline_meta_file, 'w', encoding='utf-8') as f:
            json.dump(pipeline_meta, f, ensure_ascii=False, indent=2)
        logging.info(f"[PIPELINE] 已保存管线元数据: {pipeline_meta_file}")
    except Exception as e:
        logging.warning(f"[PIPELINE] 保存元数据失败: {e}")
    
    # Step 3 Day1: 生成可视化报告
    if _HISTORY_AVAILABLE and not dry_run:
        try:
            report_path = generate_report(run_dir)
            logging.info(f"[REPORT] 已生成报告: {report_path}")
            if progress_callback:
                progress_callback(-1, len(urls), f"报告已生成: {report_path}")
        except Exception as e:
            logging.warning(f"报告生成失败: {e}")
    
    return {
        "run_dir": run_dir,
        "total": len(urls),
        "downloaded": downloaded,
        "skipped": skipped,
        "failed": failed,
        "errors": failed,
        "last_seen": newest or last_seen,
        "failed_items": failed_items,  # 添加失败项列表，用于批量重试
        "asr_result": asr_result,
        "translation_result": translation_result,
        "cleanup_result": cleanup_result,
        "bilingual_result": bilingual_result
    }


def retry_failed_items(
    run_dir: str,
    cfg: dict | None = None,
    progress_callback: Callable[[dict], None] | None = None,
    stop_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    user_agent: str = "",
    proxy_text: str = "",
    cookiefile: str = "",
) -> dict:
    """
    Day3: 智能重试失败项（仅重试 retryable=True 的错误）
    
    Args:
        run_dir: 原运行目录（读取 history.jsonl）
        cfg: 重试配置（如果为 None，使用默认值）
        progress_callback: 进度回调函数（dict 格式）
        stop_event: 停止事件
        pause_event: 暂停事件
        user_agent: User-Agent
        proxy_text: 代理列表
        cookiefile: Cookie 文件路径
    
    Returns:
        {"retried": N, "recovered": M, "run_dir": "<new_run_dir>", "new_errors": X}
    """
    import random
    from pathlib import Path
    
    # 默认配置
    if cfg is None:
        cfg = {
            "enabled": True,
            "max_attempts": 2,
            "backoff": {"base_seconds": 5, "factor": 2.0, "jitter": True},
            "only_retryable": True,
            "filters": {
                "error_class": ["network", "rate_limit"],
                "error_code": [],
                "langs": []
            }
        }
    
    # 检查是否启用
    if not cfg.get("enabled", True):
        return {"retried": 0, "recovered": 0, "run_dir": run_dir, "new_errors": 0}
    
    # 读取历史记录
    run_dir_path = Path(run_dir)
    if not _HISTORY_AVAILABLE:
        logging.warning("history_schema 不可用，无法重试")
        return {"retried": 0, "recovered": 0, "run_dir": run_dir, "new_errors": 0}
    
    history_rows = read_history(run_dir_path, limit=0)  # 读取全部
    if not history_rows:
        logging.warning(f"运行目录 {run_dir} 无历史记录")
        return {"retried": 0, "recovered": 0, "run_dir": run_dir, "new_errors": 0}
    
    # 筛选可重试的错误
    retry_candidates = []
    for row in history_rows:
        status = row.get("status", "")
        if status != "error":
            continue
        
        # only_retryable 检查
        if cfg.get("only_retryable", True) and not row.get("retryable", False):
            continue
        
        # 过滤器：error_class
        error_class_filter = cfg.get("filters", {}).get("error_class", [])
        if error_class_filter:
            error_class = row.get("error_class", "")
            if error_class not in error_class_filter:
                continue
        
        # 过滤器：error_code
        error_code_filter = cfg.get("filters", {}).get("error_code", [])
        if error_code_filter:
            error_code = row.get("error_code", "")
            if error_code not in error_code_filter:
                continue
        
        # 过滤器：langs
        langs_filter = cfg.get("filters", {}).get("langs", [])
        if langs_filter:
            langs = row.get("langs", [])
            if not any(lang in langs_filter for lang in langs):
                continue
        
        retry_candidates.append(row)
    
    if not retry_candidates:
        logging.info("没有符合重试条件的失败项")
        return {"retried": 0, "recovered": 0, "run_dir": run_dir, "new_errors": 0}
    
    # 创建新的运行目录
    output_root = run_dir_path.parent
    new_run_dir = _run_dir(str(output_root))
    
    # 构建代理池和限流器
    pool = build_proxy_pool(proxy_text, mode="round_robin")
    limiter = RateLimiter(4.0, 8) if True else None
    breaker = CircuitBreaker(8, 120.0)
    
    # 重试参数
    max_attempts = cfg.get("max_attempts", 2)
    backoff_config = cfg.get("backoff", {})
    base_seconds = backoff_config.get("base_seconds", 5)
    factor = backoff_config.get("factor", 2.0)
    use_jitter = backoff_config.get("jitter", True)
    
    retried_count = 0
    recovered_count = 0
    new_errors_count = 0
    
    total_items = len(retry_candidates)
    
    # 开始重试
    for idx, row in enumerate(retry_candidates):
        # 检查停止信号
        if stop_event and stop_event.is_set():
            logging.info("重试被停止")
            break
        
        # 检查暂停信号
        if pause_event:
            while pause_event.is_set():
                time.sleep(0.1)
                if stop_event and stop_event.is_set():
                    break
        
        video_id = row.get("video_id", "")
        url = row.get("url", "")
        
        if progress_callback:
            progress_callback({
                "phase": "retry",
                "current": idx + 1,
                "total": total_items,
                "message": f"重试 {idx + 1}/{total_items}: {video_id}"
            })
        
        # 尝试重新检测
        success = False
        last_error = None
        
        for attempt in range(1, max_attempts + 1):
            # 检查停止/暂停
            if stop_event and stop_event.is_set():
                break
            if pause_event:
                while pause_event.is_set():
                    time.sleep(0.1)
                    if stop_event and stop_event.is_set():
                        break
            
            try:
                # 重新检测字幕
                from .detection import detect_links
                
                result = detect_links(
                    [url], max_workers=1, sleep_between=0.5, retry_times=1,
                    user_agent=user_agent, proxy_pool=pool, cookiefile=cookiefile,
                    stop_event=stop_event, pause_event=pause_event,
                    rate_limiter=limiter, circuit_breaker=breaker
                )
                
                if result and len(result) > 0:
                    r = result[0]
                    new_status = r.get("status", "error")
                    
                    # 判断是否成功
                    if new_status == "has_subs":
                        success = True
                        recovered_count += 1
                        
                        # 写入成功记录
                        meta = r.get("meta") or {}
                        history_row: HistoryRow = {
                            "video_id": video_id,
                            "url": url,
                            "title": meta.get("title", row.get("title", "")),
                            "channel": meta.get("channel") or meta.get("uploader") or row.get("channel", ""),
                            "status": "ok",
                            "error_code": "",
                            "error_msg": "",
                            "error_class": "",
                            "retryable": False,
                            "langs": (r.get("manual_langs") or []) + (r.get("auto_langs") or []),
                            "upload_date": meta.get("upload_date", row.get("upload_date", "")),
                            "duration": meta.get("duration", row.get("duration", 0)),
                            "view_count": meta.get("view_count", row.get("view_count", 0)),
                        }
                        write_history(new_run_dir, history_row)
                        break
                    else:
                        # 仍然失败
                        last_error = r.get("api_err", "unknown error")
                
            except Exception as e:
                last_error = str(e)
            
            # 如果还有重试机会，执行退避
            if not success and attempt < max_attempts:
                backoff_time = base_seconds * (factor ** (attempt - 1))
                if use_jitter:
                    backoff_time *= (1.0 + random.uniform(-0.2, 0.2))
                
                logging.info(f"重试失败，等待 {backoff_time:.1f}s 后重试 (attempt {attempt}/{max_attempts})")
                time.sleep(backoff_time)
        
        retried_count += 1
        
        # 如果最终失败，写入失败记录
        if not success:
            new_errors_count += 1
            
            # 使用 v2 分类
            status, error_code, error_msg_simplified, error_class, retryable = classify_status_v2(last_error, False)
            
            history_row: HistoryRow = {
                "video_id": video_id,
                "url": url,
                "title": row.get("title", ""),
                "channel": row.get("channel", ""),
                "status": "error",
                "error_code": error_code,
                "error_msg": error_msg_simplified,
                "error_class": error_class,
                "retryable": retryable,
                "langs": row.get("langs", []),
                "upload_date": row.get("upload_date", ""),
                "duration": row.get("duration", 0),
                "view_count": row.get("view_count", 0),
            }
            write_history(new_run_dir, history_row)
    
    # 生成报告
    if _HISTORY_AVAILABLE:
        try:
            report_path = generate_report(new_run_dir)
            logging.info(f"[RETRY REPORT] 已生成重试报告: {report_path}")
        except Exception as e:
            logging.warning(f"重试报告生成失败: {e}")
    
    return {
        "retried": retried_count,
        "recovered": recovered_count,
        "run_dir": new_run_dir,
        "new_errors": new_errors_count
    }


def run_subscription_batch(
    sub_ids: list[str],
    cfg: dict,
    progress_callback: Callable[[dict], None] | None = None,
    stop_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
) -> dict:
    """
    Day4: 批量执行订阅任务
    
    Args:
        sub_ids: 订阅 ID 列表
        cfg: 完整配置字典
        progress_callback: 进度回调（dict 格式）
        stop_event: 停止事件
        pause_event: 暂停事件
    
    Returns:
        {
            "batch_dir": str,
            "runs": [{"sub_id": str, "run_dir": str, "ok": int, "error": int, "status": str}, ...]
        }
    """
    output_root = cfg.get("run", {}).get("output_root", "out")
    Path(output_root).mkdir(parents=True, exist_ok=True)
    
    # 创建批次目录
    batch_ts = time.strftime("%Y%m%d_%H%M%S")
    batch_dir = Path(output_root) / f"batch_{batch_ts}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    
    subscriptions = cfg.get("subscriptions", [])
    sub_dict = {sub["id"]: sub for sub in subscriptions}
    
    runs = []
    
    for idx, sub_id in enumerate(sub_ids):
        # 检查停止信号
        if stop_event and stop_event.is_set():
            logging.info(f"批次执行被停止，已完成 {idx}/{len(sub_ids)}")
            break
        
        # 检查暂停信号
        if pause_event:
            while pause_event.is_set():
                time.sleep(0.1)
                if stop_event and stop_event.is_set():
                    break
        
        sub = sub_dict.get(sub_id)
        if not sub:
            logging.warning(f"订阅 {sub_id} 不存在，跳过")
            runs.append({
                "sub_id": sub_id,
                "run_dir": "",
                "ok": 0,
                "error": 1,
                "status": "error_not_found"
            })
            continue
        
        if not sub.get("enabled", True):
            logging.info(f"订阅 {sub_id} 已禁用，跳过")
            runs.append({
                "sub_id": sub_id,
                "run_dir": "",
                "ok": 0,
                "error": 0,
                "status": "skipped_disabled"
            })
            continue
        
        # 构造运行参数
        sub_type = sub.get("type", "channel")
        sub_url = sub.get("url", "")
        sub_langs = sub.get("langs", []) or cfg.get("run", {}).get("download_langs", ["zh", "en"])
        
        if progress_callback:
            progress_callback({
                "phase": "subscription",
                "current": idx + 1,
                "total": len(sub_ids),
                "message": f"执行订阅 {idx + 1}/{len(sub_ids)}: {sub.get('name', sub_id)}"
            })
        
        logging.info(f"[SUBSCRIPTION] 开始执行: {sub_id} ({sub.get('name', '')}) - {sub_url}")
        
        try:
            # 调用 run_full_process
            run_args = {
                "channel_or_playlist_url": sub_url if sub_type in ["channel", "playlist"] else "",
                "urls_override": [sub_url] if sub_type == "video" else None,
                "output_root": str(batch_dir / sub_id),
                "download_langs": sub_langs,
                "max_workers": cfg.get("run", {}).get("max_workers", 8),
                "do_download": True,
                "download_fmt": cfg.get("run", {}).get("download_fmt", "txt"),
                "progress_callback": None,  # 不传递进度回调，避免混乱
                "stop_event": stop_event,
                "pause_event": pause_event,
                "user_agent": cfg.get("run", {}).get("user_agent", ""),
                "proxy_text": cfg.get("run", {}).get("proxy_text", ""),
                "cookiefile": cfg.get("run", {}).get("cookiefile", ""),
                "incremental_detect": cfg.get("run", {}).get("incremental_detect", True),
                "incremental_download": cfg.get("run", {}).get("incremental_download", True),
            }
            
            result = run_full_process(**run_args)
            
            runs.append({
                "sub_id": sub_id,
                "sub_name": sub.get("name", ""),
                "run_dir": result.get("run_dir", ""),
                "ok": result.get("total", 0) - result.get("errors", 0),
                "error": result.get("errors", 0),
                "total": result.get("total", 0),
                "status": "ok"
            })
            
            # Day4C: 重新生成报告，附带订阅来源信息
            run_dir = result.get("run_dir", "")
            if run_dir and _HISTORY_AVAILABLE:
                try:
                    subscription_info = {
                        "source": "subscription",
                        "sub_id": sub_id,
                        "sub_name": sub.get("name", "")
                    }
                    generate_report(run_dir, subscription_info)
                    logging.info(f"[SUBSCRIPTION] 已生成带订阅来源的报告: {run_dir}/report.html")
                except Exception as e:
                    logging.warning(f"[SUBSCRIPTION] 报告生成失败: {e}")
            
            logging.info(f"[SUBSCRIPTION] 完成: {sub_id} - {result.get('total', 0)} 个视频")
            
        except Exception as e:
            logging.error(f"[SUBSCRIPTION] 失败: {sub_id} - {e}")
            runs.append({
                "sub_id": sub_id,
                "sub_name": sub.get("name", ""),
                "run_dir": "",
                "ok": 0,
                "error": 1,
                "total": 0,
                "status": f"error: {str(e)[:100]}"
            })
    
    # 生成批次汇总报告
    summary_path = batch_dir / "batch_summary.json"
    summary = {
        "batch_dir": str(batch_dir),
        "batch_ts": batch_ts,
        "total_subs": len(sub_ids),
        "completed_subs": len([r for r in runs if r["status"] == "ok"]),
        "failed_subs": len([r for r in runs if r["status"].startswith("error")]),
        "runs": runs
    }
    
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    logging.info(f"[BATCH] 批次完成: {batch_dir}")
    
    return summary


def scheduler_tick(
    cfg: dict,
    progress_callback: Callable[[dict], None] | None = None,
    stop_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    root: str = "."
) -> dict:
    """
    Day4: 执行一次调度 tick
    
    Args:
        cfg: 完整配置字典
        progress_callback: 进度回调
        stop_event: 停止事件
        pause_event: 暂停事件
        root: 根目录
    
    Returns:
        {
            "tick_ts": str,
            "due_jobs": int,
            "executed_jobs": int,
            "results": [{"job_id": str, "status": str, "batch_dir": str, ...}, ...]
        }
    """
    import scheduler_logic
    
    if not cfg.get("scheduler", {}).get("enabled", True):
        logging.info("[SCHEDULER] 调度器已禁用")
        return {
            "tick_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "due_jobs": 0,
            "executed_jobs": 0,
            "results": []
        }
    
    # 找出到期任务
    due = scheduler_logic.due_jobs(cfg, None, root)
    
    if not due:
        logging.info("[SCHEDULER] 无到期任务")
        return {
            "tick_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
            "due_jobs": 0,
            "executed_jobs": 0,
            "results": []
        }
    
    logging.info(f"[SCHEDULER] 找到 {len(due)} 个到期任务")
    
    results = []
    
    for job in due:
        job_id = job.get("id")
        sub_ids = job.get("sub_ids", [])
        
        if not sub_ids:
            logging.warning(f"[SCHEDULER] 任务 {job_id} 没有订阅，跳过")
            continue
        
        # 尝试锁定
        if not scheduler_logic.lock_and_mark(job_id, root):
            logging.warning(f"[SCHEDULER] 任务 {job_id} 已被锁定，跳过")
            results.append({
                "job_id": job_id,
                "status": "skipped_locked",
                "batch_dir": ""
            })
            continue
        
        logging.info(f"[SCHEDULER] 开始执行任务: {job_id}")
        
        if progress_callback:
            progress_callback({
                "phase": "scheduler",
                "current": len(results) + 1,
                "total": len(due),
                "message": f"执行调度任务: {job_id}"
            })
        
        try:
            # 执行订阅批次
            batch_result = run_subscription_batch(
                sub_ids=sub_ids,
                cfg=cfg,
                progress_callback=progress_callback,
                stop_event=stop_event,
                pause_event=pause_event
            )
            
            # 为每个订阅生成报告
            for run in batch_result.get("runs", []):
                run_dir = run.get("run_dir")
                if run_dir and Path(run_dir).exists():
                    try:
                        if _HISTORY_AVAILABLE:
                            generate_report(run_dir)
                            logging.info(f"[SCHEDULER] 已生成报告: {run_dir}/report.html")
                    except Exception as e:
                        logging.warning(f"[SCHEDULER] 报告生成失败: {e}")
            
            # 释放锁
            scheduler_logic.release(job_id, "ok", root)
            
            results.append({
                "job_id": job_id,
                "status": "ok",
                "batch_dir": batch_result.get("batch_dir", ""),
                "completed_subs": batch_result.get("completed_subs", 0),
                "failed_subs": batch_result.get("failed_subs", 0)
            })
            
            logging.info(f"[SCHEDULER] 任务完成: {job_id}")
            
        except Exception as e:
            logging.error(f"[SCHEDULER] 任务失败: {job_id} - {e}")
            
            # 释放锁（标记为错误）
            scheduler_logic.release(job_id, "error", root)
            
            results.append({
                "job_id": job_id,
                "status": f"error: {str(e)[:100]}",
                "batch_dir": ""
            })
    
    return {
        "tick_ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "due_jobs": len(due),
        "executed_jobs": len([r for r in results if r["status"] == "ok"]),
        "results": results
    }
