# -*- coding: utf-8 -*-
"""
core.download — 字幕下载与格式转换
"""
from __future__ import annotations
import os, time, random, re, logging, threading
from pathlib import Path
from typing import List, Tuple
from .net import ProxyPool, RateLimiter, CircuitBreaker
from .utils import extract_video_id, classify_error

# 可选依赖
try:
    from yt_dlp import YoutubeDL
except Exception:
    YoutubeDL = None

# ---------- SRT/VTT 解析与转换 ----------
TIMECODE_RE = re.compile(r"(?P<h>\d{2}):(?P<m>\d{2}):(?P<s>\d{2})[,.](?P<ms>\d{1,3})")

def _hms_to_seconds(h, m, s, ms=0): 
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0

def _strip_srt_lines(s: str) -> List[Tuple[float, float, str]]:
    """解析 SRT 文件，返回 (start, end, text) 列表"""
    out = []
    cur_text = []
    t0 = t1 = None
    for ln in s.splitlines():
        t = ln.strip()
        if "-->" in t:
            m = re.findall(TIMECODE_RE, t)
            if len(m) >= 2:
                if cur_text and t0 is not None:
                    out.append((t0, t1, " ".join(cur_text).strip()))
                    cur_text = []
                h1, m1, s1, ms1 = m[0]
                h2, m2, s2, ms2 = m[1]
                t0 = _hms_to_seconds(h1, m1, s1, ms1)
                t1 = _hms_to_seconds(h2, m2, s2, ms2)
            continue
        if not t or t.isdigit() or t.upper().startswith("WEBVTT"):
            continue
        cur_text.append(t)
    if cur_text and t0 is not None:
        out.append((t0, t1, " ".join(cur_text).strip()))
    return out

def _strip_vtt_lines(s: str) -> List[Tuple[float, float, str]]:
    """解析 VTT 文件，返回 (start, end, text) 列表"""
    return _strip_srt_lines(s)

def _strip_srt(s: str) -> List[str]:
    """从 SRT 提取纯文本"""
    return [t for _, __, t in _strip_srt_lines(s)]

def _strip_vtt(s: str) -> List[str]:
    """从 VTT 提取纯文本"""
    return [t for _, __, t in _strip_vtt_lines(s)]

def convert_srt_to_txt(srt_path: Path, out_txt: Path) -> bool:
    """SRT → TXT 转换"""
    try:
        out_txt.write_text(
            "\n".join(_strip_srt(srt_path.read_text('utf-8', errors='ignore'))) + "\n",
            "utf-8"
        )
        return True
    except Exception as e:
        logging.warning(f"SRT->TXT fail: {e}")
        return False

def convert_vtt_to_txt(vtt_path: Path, out_txt: Path) -> bool:
    """VTT → TXT 转换"""
    try:
        out_txt.write_text(
            "\n".join(_strip_vtt(vtt_path.read_text('utf-8', errors='ignore'))) + "\n",
            "utf-8"
        )
        return True
    except Exception as e:
        logging.warning(f"VTT->TXT fail: {e}")
        return False

def _count_effective_lines(p: Path, min_lines: int = 5) -> bool:
    """
    检查文件是否有有效内容
    
    - 返回 True 表示文件有效（≥ min_lines 行非空内容）
    - 返回 False 表示文件无效或不存在
    """
    if not p.exists():
        return False
    try:
        text = p.read_text('utf-8', errors='ignore')
        lines = [ln for ln in text.splitlines() if ln.strip()]
        return len(lines) >= min_lines
    except Exception:
        return False

def download_subtitles(
    url: str,
    subs_dir: str,
    download_langs: list[str],
    download_prefer: str,      # "both"|"manual"|"auto"
    download_fmt: str,         # "srt"|"vtt"|"txt"
    user_agent: str = "",
    proxy_pool: ProxyPool | None = None,
    cookiefile: str = "",
    stop_event: threading.Event | None = None,
    pause_event: threading.Event | None = None,
    retry_times: int = 2,
    base_sleep: float = 0.5,
    incremental: bool = True,
    merge_bilingual: bool = False,
    rate_limiter: RateLimiter | None = None,
    circuit_breaker: CircuitBreaker | None = None,
) -> list[Path]:
    """
    下载视频字幕
    
    返回下载的字幕文件路径列表
    """
    if not YoutubeDL: 
        raise RuntimeError("yt-dlp is not installed")
    
    Path(subs_dir).mkdir(parents=True, exist_ok=True)
    subs_path = Path(subs_dir)
    writesub = download_prefer in ("manual", "both")
    writeauto = download_prefer in ("auto", "both")
    langs = [l.lower() for l in (download_langs or ["zh", "en"])]
    vid = extract_video_id(url)

    def exist(lang, ext) -> Path | None:
        """检查文件是否存在（支持语言变体）"""
        # 先检查标准格式
        p = Path(subs_dir) / f"{vid}.{lang}.{ext}"
        if p.exists():
            return p
        
        # 如果请求的是通用语言代码（如 zh），检查变体
        if lang.lower() == 'zh':
            for variant in ['zh-TW', 'zh-Hans', 'zh-Hant', 'zh-CN']:
                p = Path(subs_dir) / f"{vid}.{variant}.{ext}"
                if p.exists():
                    return p
        elif lang.lower() == 'en':
            for variant in ['en-US', 'en-GB', 'en-orig']:
                p = Path(subs_dir) / f"{vid}.{variant}.{ext}"
                if p.exists():
                    return p
        
        # 使用glob查找可能的变体格式
        if subs_path.exists():
            lang_lower = lang.lower()
            for srt_file in subs_path.glob(f"{vid}.*.{ext}"):
                file_name_lower = srt_file.name.lower()
                # 检查文件名是否包含请求的语言或变体
                if f".{lang_lower}." in file_name_lower or file_name_lower.endswith(f".{lang_lower}.{ext}"):
                    return srt_file
                # 变体匹配（如 zh-TW 匹配 zh）
                if lang_lower == 'zh' and any(v in file_name_lower for v in ['zh-tw', 'zh-hans', 'zh-hant', 'zh-cn']):
                    return srt_file
                elif lang_lower == 'en' and any(v in file_name_lower for v in ['en-us', 'en-gb', 'en-orig']):
                    return srt_file
        
        return None

    # 增量检查：文件存在且有效（≥5行）才跳过（支持所有语言和变体）
    if incremental and download_fmt in ("srt", "vtt", "txt"):
        existing = []
        all_valid = True
        
        # 检查所有请求的语言
        for l in langs:
            p = exist(l, download_fmt)
            if p and _count_effective_lines(p, min_lines=5):
                existing.append(p)
            else:
                all_valid = False
                break
        
        if all_valid and existing and len(existing) == len(langs):
            import sys
            print(f"[DEBUG download_subtitles] 增量检查通过：所有语言文件已存在且有效，跳过下载", file=sys.stderr, flush=True)
            return existing

    attempt = 0
    out = []
    translated_langs_added = []  # 记录已添加的翻译字幕语言代码
    
    while attempt <= retry_times:
        if stop_event and stop_event.is_set(): 
            return out
        while pause_event and pause_event.is_set():
            if stop_event and stop_event.is_set(): 
                return out
            time.sleep(0.1)
        
        attempt += 1
        proxy = proxy_pool.get() if proxy_pool else ""
        if rate_limiter: 
            rate_limiter.acquire()
        
        # yt-dlp字幕下载配置
        # 注意：字幕文件的outtmpl格式应该是: %(id)s.%(language)s.%(ext)s
        # 或者简化为: %(id)s.%(ext)s (language会在ext之前)
        ydl_opts = {
            "quiet": False,  # 改为False以查看详细输出
            "no_warnings": False,
            "skip_download": True,  # 跳过视频下载，只下载字幕
            "writesubtitles": writesub,  # 下载手动字幕
            "writeautomaticsub": writeauto,  # 下载自动字幕
            "subtitleslangs": langs,  # 字幕语言列表
            "subtitlesformat": "srt" if download_fmt in ("srt", "txt") else "vtt",  # 字幕格式
            # yt-dlp字幕文件名格式: 视频ID.语言代码.扩展名
            "outtmpl": {
                "default": str(Path(subs_dir) / "%(id)s.%(language)s.%(ext)s"),
            },
            # 确保下载所有请求的语言，即使某些语言不存在
            "ignoreerrors": False,  # 不忽略错误，但继续处理
        }
        if proxy: 
            ydl_opts["proxy"] = proxy
        if user_agent: 
            ydl_opts["http_headers"] = {"User-Agent": user_agent}
        if cookiefile and os.path.exists(cookiefile): 
            ydl_opts["cookiefile"] = cookiefile
        
        t0 = time.perf_counter()
        try:
            import sys
            print(f"[DEBUG download_subtitles] Attempt {attempt}/{retry_times+1} for {vid}", file=sys.stderr, flush=True)
            print(f"[DEBUG download_subtitles] ydl_opts: writesub={writesub}, writeauto={writeauto}, langs={langs}", file=sys.stderr, flush=True)
            
            with YoutubeDL(ydl_opts) as ydl: 
                print(f"[DEBUG download_subtitles] Calling extract_info for {url}...", file=sys.stderr, flush=True)
                print(f"[DEBUG download_subtitles] Output directory: {subs_dir}", file=sys.stderr, flush=True)
                print(f"[DEBUG download_subtitles] Output template: {ydl_opts['outtmpl']}", file=sys.stderr, flush=True)
                print(f"[DEBUG download_subtitles] Working directory: {os.getcwd()}", file=sys.stderr, flush=True)
                
                # 先提取信息但不下载，检查可用字幕
                info_preview = ydl.extract_info(url, download=False)
                
                # 检查实际可用的字幕语言
                actual_subtitles = info_preview.get('subtitles', {}) if info_preview else {}
                actual_auto_subs = info_preview.get('automatic_captions', {}) if info_preview else {}
                print(f"[DEBUG download_subtitles] Actual subtitles available: {list(actual_subtitles.keys())}", file=sys.stderr, flush=True)
                print(f"[DEBUG download_subtitles] Actual auto_captions available: {list(actual_auto_subs.keys())[:10]}... (total: {len(actual_auto_subs)})", file=sys.stderr, flush=True)
                print(f"[DEBUG download_subtitles] Requested languages: {langs}", file=sys.stderr, flush=True)
                
                # 优化语言匹配：处理语言代码变体（如 zh-TW, zh-Hans 匹配 zh）
                def match_lang(requested_lang, available_keys):
                    """检查请求的语言是否在可用语言列表中（支持变体匹配）"""
                    requested_lang_lower = requested_lang.lower()
                    # 直接匹配
                    if requested_lang_lower in [k.lower() for k in available_keys]:
                        return True
                    # 前缀匹配（zh 匹配 zh-TW, zh-Hans 等）
                    for key in available_keys:
                        key_lower = key.lower()
                        if key_lower.startswith(requested_lang_lower + '-') or key_lower.startswith(requested_lang_lower + '_'):
                            return True
                    return False
                
                # 如果请求了某个语言但找不到匹配，尝试查找变体
                final_subtitleslangs = list(langs)
                for lang in langs:
                    lang_lower = lang.lower()
                    has_in_subtitles = match_lang(lang_lower, actual_subtitles.keys())
                    has_in_auto = match_lang(lang_lower, actual_auto_subs.keys())
                    
                    print(f"[DEBUG download_subtitles] Language {lang}: has_in_subtitles={has_in_subtitles}, has_in_auto={has_in_auto}", file=sys.stderr, flush=True)
                    
                    # 即使 match_lang 返回 True（找到了变体），我们也需要找到具体的变体代码
                    # 因为 yt-dlp 需要具体的语言代码（如 zh-TW），而不是通用代码（zh）
                    variant_found = None
                    all_keys = list(actual_subtitles.keys()) + list(actual_auto_subs.keys())
                    
                    # 如果直接匹配（完全匹配），使用原始语言代码
                    if lang_lower in [k.lower() for k in all_keys]:
                        print(f"[DEBUG download_subtitles] Direct match found for {lang}", file=sys.stderr, flush=True)
                        # 找到确切的匹配
                        for key in all_keys:
                            if key.lower() == lang_lower:
                                variant_found = key
                                break
                    # 如果找到变体匹配（前缀匹配），使用变体代码
                    elif has_in_subtitles or has_in_auto:
                        print(f"[DEBUG download_subtitles] Searching for variant of {lang} in {len(all_keys)} available keys...", file=sys.stderr, flush=True)
                        for key in all_keys:
                            key_lower = key.lower()
                            # 检查是否是请求语言的变体（如 zh-TW, zh-Hans 匹配 zh）
                            if key_lower.startswith(lang_lower + '-') or key_lower.startswith(lang_lower + '_'):
                                variant_found = key
                                print(f"[DEBUG download_subtitles] Language variant found: {lang} -> {variant_found}", file=sys.stderr, flush=True)
                                break
                    
                    # 如果找到了变体，替换或添加到列表中
                    if variant_found:
                        # 移除原始语言代码（如果存在），添加变体代码
                        if lang in final_subtitleslangs:
                            final_subtitleslangs.remove(lang)
                        if variant_found not in final_subtitleslangs:
                            final_subtitleslangs.append(variant_found)
                    elif not has_in_subtitles and not has_in_auto:
                        print(f"[DEBUG download_subtitles] No variant found for {lang} in available keys", file=sys.stderr, flush=True)
                
                # 更新 ydl_opts 使用匹配后的语言列表
                if final_subtitleslangs != langs:
                    print(f"[DEBUG download_subtitles] Updated subtitleslangs from {langs} to {final_subtitleslangs}", file=sys.stderr, flush=True)
                    ydl_opts['subtitleslangs'] = final_subtitleslangs
                    ydl = YoutubeDL(ydl_opts)
                else:
                    print(f"[DEBUG download_subtitles] No language variant needed, using original langs: {langs}", file=sys.stderr, flush=True)
                
                # 如果请求了 'en' 但没有原始英文字幕，尝试使用翻译字幕
                has_original_en = 'en' in actual_subtitles or 'en' in actual_auto_subs or match_lang('en', list(actual_subtitles.keys()) + list(actual_auto_subs.keys()))
                if 'en' in langs and not has_original_en:
                    # 查找可用的英文翻译字幕（格式：'en-zh' 表示中文翻译成英文）
                    translated_en_keys = [k for k in actual_auto_subs.keys() if k.startswith('en-') or k.endswith('-en')]
                    
                    if translated_en_keys:
                        print(f"[DEBUG download_subtitles] Found translated English keys: {translated_en_keys[:5]}...", file=sys.stderr, flush=True)
                        # 优先使用 'en-zh' 格式
                        preferred_key = next((k for k in translated_en_keys if k == 'en-zh' or k.startswith('en-zh')), translated_en_keys[0] if translated_en_keys else None)
                        
                        if preferred_key:
                            print(f"[DEBUG download_subtitles] Will use translated English subtitle: {preferred_key}", file=sys.stderr, flush=True)
                            # 添加翻译字幕的语言代码到下载列表（只在第一次或重试时添加）
                            if preferred_key not in ydl_opts['subtitleslangs']:
                                ydl_opts['subtitleslangs'] = list(ydl_opts['subtitleslangs']) + [preferred_key]
                                translated_langs_added.append(preferred_key)  # 记录已添加的翻译字幕
                                print(f"[DEBUG download_subtitles] Updated subtitleslangs to: {ydl_opts['subtitleslangs']}", file=sys.stderr, flush=True)
                                # 重新创建 YoutubeDL 对象以应用新配置
                                ydl = YoutubeDL(ydl_opts)
                elif translated_langs_added:
                    # 重试时，如果之前已经添加了翻译字幕，确保它们还在配置中
                    for trans_lang in translated_langs_added:
                        if trans_lang not in ydl_opts['subtitleslangs']:
                            ydl_opts['subtitleslangs'] = list(ydl_opts['subtitleslangs']) + [trans_lang]
                    if translated_langs_added:
                        print(f"[DEBUG download_subtitles] Retry: Restored translated langs: {translated_langs_added}", file=sys.stderr, flush=True)
                        ydl = YoutubeDL(ydl_opts)
                
                # 关键修复：使用download=True，配合skip_download=True来只下载字幕
                # yt-dlp文档：当writesubtitles=True时，需要download=True才能真正保存文件
                # 添加详细的调试信息
                print(f"[DEBUG download_subtitles] Final subtitleslangs for download: {ydl_opts.get('subtitleslangs', [])}", file=sys.stderr, flush=True)
                try:
                    info = ydl.extract_info(url, download=True)
                except Exception as download_error:
                    import sys
                    print(f"[DEBUG download_subtitles] Download error during extract_info: {download_error}", file=sys.stderr, flush=True)
                    # 如果是连接错误，尝试重新下载
                    if 'RemoteDisconnected' in str(download_error) or 'Connection' in str(download_error):
                        print(f"[DEBUG download_subtitles] Connection error detected, will retry", file=sys.stderr, flush=True)
                        raise download_error  # 让重试机制处理
                    raise
                
                print(f"[DEBUG download_subtitles] extract_info completed, video_id: {info.get('id') if info else 'None'}", file=sys.stderr, flush=True)
                
                # yt-dlp可能在extract_info后异步写入文件，等待一下
                time.sleep(1.5)  # 增加等待时间
            
            print(f"[DEBUG download_subtitles] Checking for subtitle files in {subs_dir}...", file=sys.stderr, flush=True)
            subs_path = Path(subs_dir)
            
            # 列出目录中所有文件
            all_files = list(subs_path.glob("*")) if subs_path.exists() else []
            print(f"[DEBUG download_subtitles] All files in directory: {[f.name for f in all_files]}", file=sys.stderr, flush=True)
            
            # 等待更长时间，确保文件写入完成
            time.sleep(1.0)
            
            # 再次检查文件
            all_files_after = list(subs_path.glob("*")) if subs_path.exists() else []
            print(f"[DEBUG download_subtitles] All files after wait: {[f.name for f in all_files_after]}", file=sys.stderr, flush=True)
            
            created = []
            # 合并原始语言和翻译语言列表，确保翻译字幕也被检查
            # 同时需要检查语言变体（如 zh-TW 匹配 zh）
            all_langs_to_check = list(set(langs + translated_langs_added))  # 去重
            
            # 扩展要检查的语言列表：如果请求了 zh，也要检查 zh-TW, zh-Hans 等变体
            expanded_langs_to_check = []
            for lang in all_langs_to_check:
                expanded_langs_to_check.append(lang)
                # 如果请求了 zh，也要检查 zh-TW, zh-Hans 等变体
                if lang.lower() == 'zh':
                    expanded_langs_to_check.extend(['zh-TW', 'zh-Hans', 'zh-Hant', 'zh-CN'])
                # 如果请求了 en，也要检查 en-US, en-GB 等变体
                elif lang.lower() == 'en':
                    expanded_langs_to_check.extend(['en-US', 'en-GB', 'en-orig'])
            
            for lang in all_langs_to_check:
                ext = "srt" if download_fmt in ("srt", "txt") else "vtt"
                
                # 检查多种可能的文件名格式
                # 1. 标准格式: video_id.language.ext
                # 2. yt-dlp可能使用的格式: video_id.ext (语言在内部)
                # 3. 可能的大小写变化
                alt_patterns = [
                    Path(subs_dir) / f"{vid}.{lang}.{ext}",  # dQw4w9WgXcQ.en.srt
                    Path(subs_dir) / f"{vid}.{lang}.{ext.upper()}",  # dQw4w9WgXcQ.en.SRT
                    Path(subs_dir) / f"{vid}.{ext}",  # dQw4w9WgXcQ.srt
                    Path(subs_dir) / f"{vid}.{ext.upper()}",  # dQw4w9WgXcQ.SRT
                    Path(subs_dir) / f"{vid}-{lang}.{ext}",  # dQw4w9WgXcQ-en.srt
                ]
                
                # 也检查所有.srt文件（包括可能重复语言代码的格式和语言变体）
                if subs_path.exists():
                    for srt_file in subs_path.glob(f"*.{ext}"):
                        if vid in srt_file.name:
                            # 检查文件名是否包含请求的语言或变体
                            file_lang_match = False
                            lang_lower = lang.lower()
                            file_name_lower = srt_file.name.lower()
                            
                            # 直接匹配
                            if f".{lang_lower}." in file_name_lower or file_name_lower.endswith(f".{lang_lower}.{ext}"):
                                file_lang_match = True
                            # 变体匹配（如 zh-TW 匹配 zh）
                            elif lang_lower == 'zh' and ('zh-tw' in file_name_lower or 'zh-hans' in file_name_lower or 'zh-hant' in file_name_lower or 'zh-cn' in file_name_lower):
                                file_lang_match = True
                            elif lang_lower == 'en' and ('en-us' in file_name_lower or 'en-gb' in file_name_lower or 'en-orig' in file_name_lower):
                                file_lang_match = True
                            
                            if file_lang_match:
                                alt_patterns.append(srt_file)
                                print(f"[DEBUG download_subtitles] Found potential file: {srt_file}", file=sys.stderr, flush=True)
                
                found = False
                found_file = None
                for pattern in alt_patterns:
                    if pattern.exists():
                        print(f"[DEBUG download_subtitles] Found subtitle file: {pattern}", file=sys.stderr, flush=True)
                        found_file = pattern
                        found = True
                        break
                
                if found and found_file:
                    # 处理文件名格式问题：
                    # 1. 重复语言代码（如 .en.en.srt）
                    # 2. yt-dlp 可能添加额外语言代码（如 .en.zh-TW.srt 应该是 .zh-TW.srt）
                    correct_name = None
                    
                    # 提取文件名中的所有部分
                    parts = found_file.stem.split('.')
                    if len(parts) >= 2:
                        # 找出实际的语言代码（可能是变体）
                        actual_lang = None
                        lang_lower = lang.lower()
                        for part in parts:
                            part_lower = part.lower()
                            # 检查是否是请求的语言或变体
                            if lang_lower == part_lower:
                                actual_lang = part
                                break
                            # 检查是否是变体（如 zh-TW 匹配 zh）
                            elif lang_lower == 'zh' and part_lower in ['zh-tw', 'zh-hans', 'zh-hant', 'zh-cn']:
                                actual_lang = part
                                break
                            elif lang_lower == 'en' and part_lower in ['en-us', 'en-gb', 'en-orig']:
                                actual_lang = part
                                break
                        
                        # 如果找到了实际语言代码，构建正确的文件名
                        if actual_lang:
                            correct_name = found_file.parent / f"{vid}.{actual_lang}.{ext}"
                        else:
                            # 如果找不到，使用原始语言代码
                            correct_name = found_file.parent / f"{vid}.{lang}.{ext}"
                    
                    # 如果文件名不正确，重命名
                    if correct_name and found_file.name != correct_name.name:
                        try:
                            # 如果目标文件已存在，先删除
                            if correct_name.exists():
                                correct_name.unlink()
                            found_file.rename(correct_name)
                            print(f"[DEBUG download_subtitles] Renamed to correct format: {correct_name}", file=sys.stderr, flush=True)
                            found_file = correct_name
                        except Exception as e:
                            print(f"[DEBUG download_subtitles] Rename failed: {e}, using original", file=sys.stderr, flush=True)
                    # 处理重复语言代码的情况
                    elif found_file.name.count(f".{lang}.") > 1 or found_file.name.endswith(f".{lang}.{lang}.{ext}"):
                        correct_name = found_file.parent / f"{vid}.{lang}.{ext}"
                        try:
                            if correct_name.exists():
                                correct_name.unlink()
                            found_file.rename(correct_name)
                            print(f"[DEBUG download_subtitles] Renamed to correct format: {correct_name}", file=sys.stderr, flush=True)
                            found_file = correct_name
                        except Exception as e:
                            print(f"[DEBUG download_subtitles] Rename failed: {e}, using original", file=sys.stderr, flush=True)
                    
                    created.append(found_file)
                else:
                    print(f"[DEBUG download_subtitles] Subtitle file NOT found for lang {lang}", file=sys.stderr, flush=True)
            
            print(f"[DEBUG download_subtitles] Total files found: {len(created)}", file=sys.stderr, flush=True)
            
            # 检查哪些语言下载失败了
            downloaded_langs = set()
            for f in created:
                # 从文件名提取语言代码（如 tXNPGVQvn-I.NA.zh.srt -> zh）
                # 或者 8S0FDjFBj8o.zh-TW.srt -> zh-TW
                parts = f.stem.split('.')
                if len(parts) >= 2:
                    # 尝试从所有部分中找到语言代码（排除视频ID）
                    lang_part = None
                    for part in parts:
                        part_lower = part.lower()
                        # 检查是否是请求的语言或变体
                        for lang in langs:
                            lang_lower = lang.lower()
                            if part_lower == lang_lower:
                                lang_part = part
                                downloaded_langs.add(lang)
                                break
                            # 检查是否是变体（如 zh-TW 匹配 zh）
                            elif lang_lower == 'zh' and part_lower in ['zh-tw', 'zh-hans', 'zh-hant', 'zh-cn']:
                                lang_part = part
                                downloaded_langs.add(lang)
                                break
                            elif lang_lower == 'en' and part_lower in ['en-us', 'en-gb', 'en-orig']:
                                lang_part = part
                                downloaded_langs.add(lang)
                                break
                        if lang_part:
                            break
            
            # 找出失败的语言（包括翻译字幕的目标语言）
            failed_langs = [lang for lang in langs if lang not in downloaded_langs]
            
            # 如果 yt-dlp 没有下载到任何字幕，或者某些语言下载失败，尝试使用 youtube-transcript-api 作为备用方案
            if (not created or failed_langs) and langs:
                langs_to_try = failed_langs if failed_langs else langs
                print(f"[DEBUG download_subtitles] yt-dlp failed for languages: {langs_to_try}, trying youtube-transcript-api fallback", file=sys.stderr, flush=True)
                try:
                    from youtube_transcript_api import YouTubeTranscriptApi
                    from youtube_transcript_api.formatters import SRTFormatter
                    
                    for lang in langs_to_try:
                        # 跳过已经成功下载的语言
                        if lang in downloaded_langs:
                            continue
                            
                        try:
                            # 尝试获取原始语言字幕
                            # 注意：YouTubeTranscriptApi.list_transcripts 是类方法，需要传入 video_id
                            transcript_list = YouTubeTranscriptApi.list_transcripts(vid)
                            
                            # 首先尝试找到原始语言字幕
                            try:
                                transcript = transcript_list.find_transcript([lang])
                                data = transcript.fetch()
                            except:
                                # 如果找不到原始语言，尝试从其他语言翻译
                                available_transcripts = list(transcript_list)
                                if available_transcripts:
                                    # 使用第一个可用字幕（通常是中文）并翻译
                                    transcript = available_transcripts[0]
                                    translated = transcript.translate(lang)
                                    data = translated.fetch()
                                else:
                                    raise Exception("No transcripts available")
                            
                            # 格式化为 SRT
                            formatter = SRTFormatter()
                            srt_content = formatter.format_transcript(data)
                            
                            # 保存文件
                            output_file = Path(subs_dir) / f"{vid}.{lang}.{download_fmt}"
                            output_file.write_text(srt_content, encoding='utf-8')
                            
                            print(f"[DEBUG download_subtitles] Successfully downloaded subtitle via youtube-transcript-api: {output_file}", file=sys.stderr, flush=True)
                            created.append(output_file)
                        except Exception as fallback_error:
                            print(f"[DEBUG download_subtitles] Fallback failed for {lang}: {fallback_error}", file=sys.stderr, flush=True)
                except ImportError:
                    print(f"[DEBUG download_subtitles] youtube-transcript-api not available for fallback", file=sys.stderr, flush=True)
                except Exception as fallback_error:
                    print(f"[DEBUG download_subtitles] Fallback error: {fallback_error}", file=sys.stderr, flush=True)
            
            # 检查是否有翻译字幕下载失败
            if translated_langs_added:
                # 检查已下载的文件中是否包含翻译字幕
                downloaded_langs = set()
                for f in created:
                    # 从文件名提取语言代码（如 tXNPGVQvn-I.NA.en.srt -> en）
                    parts = f.stem.split('.')
                    if len(parts) >= 2:
                        lang_part = parts[-1]  # 最后一个部分可能是语言代码
                        # 检查是否是翻译字幕的语言代码（如 en-zh 中的 en）
                        for trans_lang in translated_langs_added:
                            target_lang = trans_lang.split('-')[0] if '-' in trans_lang else trans_lang
                            if lang_part == target_lang:
                                downloaded_langs.add(trans_lang)
                                break
                
                # 找出失败的翻译字幕
                failed_translated_langs = [lang for lang in translated_langs_added if lang not in downloaded_langs]
                if failed_translated_langs:
                    print(f"[DEBUG download_subtitles] Translated subtitles failed via yt-dlp: {failed_translated_langs}, trying youtube-transcript-api fallback", file=sys.stderr, flush=True)
                    # 如果翻译字幕下载失败，尝试使用 youtube-transcript-api 作为备用方案
                    try:
                        from youtube_transcript_api import YouTubeTranscriptApi
                        from youtube_transcript_api.formatters import SRTFormatter
                        
                        # 尝试使用 youtube-transcript-api 获取翻译字幕
                        for trans_lang in failed_translated_langs:
                            # 提取目标语言（en-zh 中的 en）
                            target_lang = trans_lang.split('-')[0] if '-' in trans_lang else trans_lang
                            source_lang = trans_lang.split('-')[1] if '-' in trans_lang and len(trans_lang.split('-')) > 1 else 'zh'
                            
                            try:
                                # 获取翻译字幕
                                transcript_list = YouTubeTranscriptApi.list_transcripts(vid)
                                transcript = transcript_list.find_transcript([source_lang])
                                translated = transcript.translate(target_lang)
                                data = translated.fetch()
                                
                                # 格式化为 SRT
                                formatter = SRTFormatter()
                                srt_content = formatter.format_transcript(data)
                                
                                # 保存文件
                                output_file = Path(subs_dir) / f"{vid}.{target_lang}.{download_fmt}"
                                output_file.write_text(srt_content, encoding='utf-8')
                                
                                print(f"[DEBUG download_subtitles] Successfully downloaded translated subtitle via youtube-transcript-api: {output_file}", file=sys.stderr, flush=True)
                                created.append(output_file)
                            except Exception as fallback_error:
                                print(f"[DEBUG download_subtitles] Fallback also failed for {trans_lang}: {fallback_error}", file=sys.stderr, flush=True)
                    except ImportError:
                        print(f"[DEBUG download_subtitles] youtube-transcript-api not available for fallback", file=sys.stderr, flush=True)
                    except Exception as fallback_error:
                        print(f"[DEBUG download_subtitles] Fallback error: {fallback_error}", file=sys.stderr, flush=True)
            
            if proxy_pool and proxy: 
                proxy_pool.ok(proxy, (time.perf_counter() - t0) * 1000.0)
            if circuit_breaker: 
                circuit_breaker.record(True, None)
            
            out = created
            break
        except Exception as e:
            et = classify_error(e)
            error_msg = str(e)
            
            # 友好的错误提示
            if proxy_pool and proxy: 
                proxy_pool.bad(proxy, (time.perf_counter() - t0) * 1000.0)
            if circuit_breaker: 
                circuit_breaker.record(False, et)
            
            # 如果已经达到最大重试次数，输出最终错误信息
            if attempt > retry_times:
                print(f"\n[ERROR] 下载失败 (已重试 {retry_times + 1} 次)", file=sys.stderr, flush=True)
                print(f"  - 视频ID: {vid}", file=sys.stderr, flush=True)
                print(f"  - 错误类型: {et}", file=sys.stderr, flush=True)
                if "429" in error_msg:
                    print(f"  - 原因: YouTube 请求过于频繁，请稍后再试或使用代理", file=sys.stderr, flush=True)
                elif "503" in error_msg:
                    print(f"  - 原因: YouTube 服务暂时不可用", file=sys.stderr, flush=True)
                elif "private" in error_msg.lower() or "unavailable" in error_msg.lower():
                    print(f"  - 原因: 视频不可访问（可能为私有或已删除）", file=sys.stderr, flush=True)
                elif "timeout" in error_msg.lower():
                    print(f"  - 原因: 连接超时，请检查网络连接", file=sys.stderr, flush=True)
                else:
                    print(f"  - 错误信息: {error_msg[:200]}", file=sys.stderr, flush=True)
                print(f"  - 已下载的语言: {[f.name for f in out]}\n", file=sys.stderr, flush=True)
                return out
            # 对于 429 错误，使用更长的延迟时间（YouTube 限流通常需要等待更久）
            if et == "error_429":
                # 429 错误：指数退避，最大延迟增加到 60 秒
                # 使用更温和的退避策略，避免过度等待
                base_delay = 5.0 * (2.0 ** (attempt - 1))  # 降低指数基数
                jitter = random.uniform(2, 8)
                delay = min(60.0, base_delay + jitter)
                print(f"[DEBUG download_subtitles] HTTP 429 检测到，等待 {delay:.1f}s 后重试 ({attempt+1}/{retry_times+1})", file=sys.stderr, flush=True)
                print(f"[INFO] YouTube 请求过于频繁，等待 {delay:.0f} 秒后重试...", file=sys.stderr, flush=True)
                time.sleep(delay)
            elif et == "error_503":
                # 503 错误：服务暂时不可用，使用类似的退避策略
                base_delay = 4.0 * (2.0 ** (attempt - 1))
                jitter = random.uniform(1, 5)
                delay = min(45.0, base_delay + jitter)
                print(f"[DEBUG download_subtitles] HTTP 503 检测到，等待 {delay:.1f}s 后重试 ({attempt+1}/{retry_times+1})", file=sys.stderr, flush=True)
                print(f"[INFO] YouTube 服务暂时不可用，等待 {delay:.0f} 秒后重试...", file=sys.stderr, flush=True)
                time.sleep(delay)
            else:
                # 其他错误：使用标准退避策略
                factor = 3.5 if et in ("error_429", "error_503") else 2.0
                delay = min(20.0, base_sleep * (factor ** (attempt - 1))) + random.uniform(0, base_sleep * 0.3)
                error_type_name = et.replace("error_", "").upper() if et.startswith("error_") else et
                print(f"[DEBUG download_subtitles] {error_type_name} 错误，等待 {delay:.1f}s 后重试 ({attempt+1}/{retry_times+1})", file=sys.stderr, flush=True)
                time.sleep(delay)
    
    # TXT 格式转换（使用原子写）
    final = []
    if download_fmt == "txt":
        for lang in langs:
            srtp = Path(subs_dir) / f"{vid}.{lang}.srt"
            vttp = Path(subs_dir) / f"{vid}.{lang}.vtt"
            txtp = Path(subs_dir) / f"{vid}.{lang}.txt"
            tmp_txtp = txtp.with_suffix(".txt.part")  # 临时文件
            
            ok = False
            if srtp.exists(): 
                ok = convert_srt_to_txt(srtp, tmp_txtp)
            elif vttp.exists(): 
                ok = convert_vtt_to_txt(vttp, tmp_txtp)
            
            if ok and tmp_txtp.exists():
                # 原子替换：.part → .txt
                try:
                    tmp_txtp.replace(txtp)
                    final.append(txtp)
                except Exception as e:
                    logging.warning(f"原子替换失败 {tmp_txtp} → {txtp}: {e}")
                    # 清理临时文件
                    try:
                        tmp_txtp.unlink()
                    except:
                        pass
    else:
        final = out
    
    return final

