# -*- coding: utf-8 -*-
"""
core.detection — 字幕检测（yt-dlp + youtube_transcript_api）
"""
from __future__ import annotations
import os, time, random, threading, logging
from typing import List, Dict, Any, Callable, Set, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .utils import extract_video_id, classify_error, flatten_langs, CHINESE_PREFIXES, ENGLISH_PREFIXES, ensure_channel_videos_url, _norm_lang
from .net import ProxyPool, RateLimiter, CircuitBreaker

# 可选依赖
try:
    from yt_dlp import YoutubeDL
except Exception:
    YoutubeDL = None

try:
    from youtube_transcript_api import (
        YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound, VideoUnavailable
    )
except Exception:
    YouTubeTranscriptApi = None
    class TranscriptsDisabled(Exception): ...
    class NoTranscriptFound(Exception): ...
    class VideoUnavailable(Exception): ...

def extract_all_video_urls_from_channel_or_playlist(
    url: str, 
    proxy: str = "", 
    user_agent: str = "", 
    cookiefile: str = ""
) -> List[str]:
    """从频道或播放列表提取所有视频链接"""
    if not YoutubeDL: 
        raise RuntimeError("yt-dlp is not installed")
    url = ensure_channel_videos_url(url)
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "dump_single_json": True
    }
    if proxy: 
        ydl_opts["proxy"] = proxy
    if user_agent: 
        ydl_opts["http_headers"] = {"User-Agent": user_agent}
    if cookiefile and os.path.exists(cookiefile): 
        ydl_opts["cookiefile"] = cookiefile
    
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    
    urls = []
    for e in info.get("entries", []) or []:
        weburl = e.get("webpage_url") or e.get("url") or ""
        if not weburl and e.get("id"): 
            weburl = f"https://www.youtube.com/watch?v={e['id']}"
        if weburl:
            vid = extract_video_id(weburl)
            if vid: 
                urls.append(f"https://www.youtube.com/watch?v={vid}")
    
    res = []
    seen = set()
    for u in urls:
        if u not in seen: 
            seen.add(u)
            res.append(u)
    return res

def probe_ytdlp_info(
    url: str, 
    proxy: str = "", 
    user_agent: str = "", 
    cookiefile: str = ""
) -> Tuple[Set[str], Set[str], Dict[str, Any], float]:
    """使用 yt-dlp 探测视频信息和字幕"""
    if not YoutubeDL: 
        raise RuntimeError("yt-dlp is not installed")
    opts = {"quiet": True, "skip_download": True}
    if proxy: 
        opts["proxy"] = proxy
    if user_agent: 
        opts["http_headers"] = {"User-Agent": user_agent}
    if cookiefile and os.path.exists(cookiefile): 
        opts["cookiefile"] = cookiefile
    
    t0 = time.perf_counter()
    with YoutubeDL(opts) as ydl: 
        info = ydl.extract_info(url, download=False)
    
    # 调试：显示原始字幕数据
    import sys
    vid = info.get("id", "unknown")
    subtitles_raw = info.get("subtitles")
    auto_raw = info.get("automatic_captions")
    print(f"[DEBUG probe_ytdlp_info] Video {vid} raw subtitles keys: {list(subtitles_raw.keys()) if subtitles_raw else []}", file=sys.stderr, flush=True)
    print(f"[DEBUG probe_ytdlp_info] Video {vid} raw auto_captions keys: {list(auto_raw.keys()) if auto_raw else []}", file=sys.stderr, flush=True)
    
    manual = flatten_langs(subtitles_raw)
    auto = flatten_langs(auto_raw)
    
    print(f"[DEBUG probe_ytdlp_info] Video {vid} flattened manual: {manual}, auto: {auto}", file=sys.stderr, flush=True)
    meta = {
        "id": info.get("id"),
        "title": info.get("title"),
        "uploader": info.get("uploader"),
        "channel": info.get("channel"),
        "upload_date": info.get("upload_date"),
        "duration": info.get("duration"),
        "view_count": info.get("view_count"),
        "tags": info.get("tags") or []
    }
    return manual, auto, meta, (time.perf_counter() - t0) * 1000.0

def probe_with_yta(video_id: str) -> Tuple[Set[str], Set[str], str | None]:
    """使用 youtube_transcript_api 探测字幕"""
    m, a = set(), set()
    err = None
    if not YouTubeTranscriptApi: 
        return m, a, "NoYouTubeTranscriptApi"
    try:
        trs = YouTubeTranscriptApi.list_transcripts(video_id)
        for tr in trs:
            code = (getattr(tr, "language_code", None) or getattr(tr, "language", "") or "").lower()
            (a if getattr(tr, "is_generated", False) else m).add(code)
    except TranscriptsDisabled: 
        err = "TranscriptsDisabled"
    except NoTranscriptFound: 
        err = "NoTranscriptFound"
    except VideoUnavailable: 
        err = "VideoUnavailable"
    except Exception as e: 
        err = str(e)
    return m, a, err

def classify_caption(manual: Set[str], auto: Set[str]) -> Dict[str, Any]:
    """
    分类字幕语言（规范化版）
    
    - 统一语言码：zh*/cmn* → zh, en* → en
    - 生成 buckets: {zh: [], en: [], other: []}
    """
    # 规范化语言码
    manual_norm = {_norm_lang(lc) for lc in manual if lc}
    auto_norm = {_norm_lang(lc) for lc in auto if lc}
    all_norm = sorted(manual_norm | auto_norm)
    
    # 分类到 buckets
    buckets = {"zh": [], "en": [], "other": []}
    for lc in all_norm:
        if lc == "zh":
            buckets["zh"].append(lc)
        elif lc == "en":
            buckets["en"].append(lc)
        else:
            buckets["other"].append(lc)
    
    return {
        "has_subs": bool(all_norm), 
        "manual_langs": sorted(manual_norm), 
        "auto_langs": sorted(auto_norm),
        "all_langs": all_norm, 
        "buckets": buckets
    }

def detect_links(
    urls: list[str],
    max_workers: int = 5,
    sleep_between: float = 0.5,
    retry_times: int = 2,
    progress_callback: callable | None = None,
    user_agent: str = "",
    proxy_pool: ProxyPool | None = None,
    cookiefile: str = "",
    stop_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    batch_size: int = 0,
    detect_mode: str = "standard",      # "standard"=yt-dlp + yta, "fast"=yt-dlp only
    adaptive_concurrency: bool = False,
    min_workers: int = 2,
    max_workers_cap: int = 20,
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> list[dict]:
    """
    检测视频链接的字幕可用性
    
    Return item example:
    {
      "url": str,
      "video_id": str,
      "status": "has_subs"|"no_subs"|"error_*",
      "manual_langs": list[str],
      "auto_langs": list[str],
      "all_langs": list[str],
      "attempts": int,
      "latency_ms": float,
      "api_err": str|None,
      "meta": { "title":..., "upload_date":..., "duration":..., "view_count":..., "tags":[...] }
    }
    """
    total = len(urls)
    results = []
    lock = threading.Lock()
    count = 0
    base = max(0.2, sleep_between)
    curr = max(min_workers, min(max_workers, max_workers_cap))

    def nap(sec: float):
        """可中断的睡眠"""
        end = time.time() + sec
        while time.time() < end:
            if stop_event and stop_event.is_set(): 
                break
            if pause_event and pause_event.is_set(): 
                time.sleep(0.2)
            else: 
                time.sleep(0.05)

    def _one(u: str) -> Dict[str, Any]:
        """检测单个视频"""
        vid = extract_video_id(u)
        attempt = 0
        while attempt <= retry_times:
            if stop_event and stop_event.is_set(): 
                return {"url": u, "status": "stopped", "video_id": vid}
            while pause_event and pause_event.is_set():
                if stop_event and stop_event.is_set(): 
                    return {"url": u, "status": "stopped", "video_id": vid}
                time.sleep(0.1)
            
            attempt += 1
            proxy = proxy_pool.get() if proxy_pool else ""
            if rate_limiter: 
                rate_limiter.acquire()
            
            t0 = time.perf_counter()
            try:
                m1, a1, meta, _ = probe_ytdlp_info(u, proxy=proxy, user_agent=user_agent, cookiefile=cookiefile)
                if detect_mode == "fast": 
                    manual, auto, api_err = m1, a1, None
                else:
                    m2, a2, api_err = probe_with_yta(vid) if vid else (set(), set(), None)
                    manual, auto = m1 | m2, a1 | a2
                
                cls = classify_caption(manual, auto)
                status = "has_subs" if cls["has_subs"] else "no_subs"
                
                if proxy_pool and proxy: 
                    proxy_pool.ok(proxy, (time.perf_counter() - t0) * 1000.0)
                if circuit_breaker: 
                    circuit_breaker.record(True, None)
                
                return {
                    "url": u,
                    "status": status,
                    "manual_langs": cls["manual_langs"],
                    "auto_langs": cls["auto_langs"],
                    "all_langs": cls["all_langs"],
                    "attempts": attempt,
                    "video_id": vid,
                    "meta": meta,
                    "latency_ms": (time.perf_counter() - t0) * 1000.0,
                    "api_err": api_err
                }
            except Exception as e:
                et = classify_error(e)
                if proxy_pool and proxy: 
                    proxy_pool.bad(proxy, (time.perf_counter() - t0) * 1000.0)
                
                # 只对限流/服务错误触发熔断，访问限制类直接短路
                if circuit_breaker and et in ("error_429", "error_503", "error_timeout"): 
                    circuit_breaker.record(False, et)
                
                if attempt > retry_times: 
                    return {"url": u, "status": et, "video_id": vid, "attempts": attempt}
                
                # 限流类错误加大退避
                if et in ("error_429", "error_503"):
                    factor = 3.5
                elif et in ("error_timeout",):
                    factor = 2.5
                else:
                    factor = 2.0
                nap(min(16.0, base * (factor ** (attempt - 1))) + random.uniform(0, base * 0.3))
        return {"url": u, "status": "error_other", "video_id": vid}

    def run_batch(items: List[str], workers: int):
        """运行一批检测任务"""
        nonlocal count, results
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for fut in as_completed({ex.submit(_one, u): u for u in items}):
                r = fut.result()
                with lock:
                    results.append(r)
                    count += 1
                    if progress_callback:
                        try: 
                            progress_callback(count, total, r.get("url", ""))
                        except: 
                            pass
                nap(base)

    if batch_size and batch_size > 0:
        for i in range(0, total, batch_size):
            if stop_event and stop_event.is_set(): 
                break
            if circuit_breaker and circuit_breaker.should_cooldown():
                if progress_callback: 
                    progress_callback(-1, total, f"进入冷静期 {int(circuit_breaker.remaining())}s（429/503 保护）")
                time.sleep(circuit_breaker.remaining())
            batch = urls[i:i + batch_size]
            if progress_callback: 
                try: 
                    progress_callback(-1, total, f"阶段：检测字幕（第 {i//batch_size+1} 批 / 共 {((total-1)//batch_size)+1} 批）")
                except: 
                    pass
            run_batch(batch, curr)
            if batch and adaptive_concurrency:
                window = results[-len(batch):]
                err = sum(1 for r in window if str(r.get("status", "")).startswith("error"))
                rate = err / len(window) if window else 0.0
                
                # 动态调整并发数（基于错误率和延迟）
                # 计算平均延迟
                latencies = [r.get("latency_ms", 0) for r in window if r.get("latency_ms")]
                avg_latency = sum(latencies) / len(latencies) if latencies else 0
                
                # 调整策略：
                # 1. 错误率 > 25%：降低并发（减少2个worker）
                # 2. 错误率 < 5% 且延迟 < 2000ms：增加并发（增加2个worker）
                # 3. 延迟 > 5000ms：降低并发（减少1个worker）
                # 4. 延迟 < 1000ms 且错误率 < 10%：增加并发（增加1个worker）
                if rate > 0.25:
                    new_curr = max(min_workers, curr - 2)
                    if new_curr != curr:
                        curr = new_curr
                        if progress_callback:
                            try:
                                progress_callback(-1, total, f"⚠️ 错误率 {rate*100:.1f}% 过高，降低并发至 {curr}")
                            except:
                                pass
                elif rate < 0.05 and avg_latency < 2000:
                    new_curr = min(max_workers_cap, curr + 2)
                    if new_curr != curr:
                        curr = new_curr
                        if progress_callback:
                            try:
                                progress_callback(-1, total, f"✅ 网络状况良好，提升并发至 {curr}")
                            except:
                                pass
                elif avg_latency > 5000:
                    new_curr = max(min_workers, curr - 1)
                    if new_curr != curr:
                        curr = new_curr
                        if progress_callback:
                            try:
                                progress_callback(-1, total, f"⚠️ 延迟过高 ({avg_latency:.0f}ms)，降低并发至 {curr}")
                            except:
                                pass
                elif avg_latency < 1000 and rate < 0.10:
                    new_curr = min(max_workers_cap, curr + 1)
                    if new_curr != curr:
                        curr = new_curr
                        if progress_callback:
                            try:
                                progress_callback(-1, total, f"✅ 网络快速，提升并发至 {curr}")
                            except:
                                pass
            
            # 批次间延迟（根据当前并发数调整）
            batch_delay = max(0.3, 1.0 - (curr / max_workers_cap) * 0.5)
            time.sleep(batch_delay + random.uniform(0, 0.2))
    else:
        run_batch(urls, curr)
    
    return results

