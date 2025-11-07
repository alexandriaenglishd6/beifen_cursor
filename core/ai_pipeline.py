# -*- coding: utf-8 -*-
"""
core.ai_pipeline — AI 摘要/关键词/章节处理
"""
from __future__ import annotations
import os, re, json, hashlib, logging
from pathlib import Path
from typing import Dict, Any, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from .config import load_config, save_json
from .utils import _ts_utc
from .download import _strip_srt_lines, _strip_vtt_lines

# 可选依赖
try:
    from adapters.ai_adapter import AIClient
except Exception:
    AIClient = None

# ---------- AI 辅助工具 ----------
def _sha1(s: str) -> str:
    """计算字符串 SHA1"""
    return hashlib.sha1(s.encode("utf-8", "ignore")).hexdigest()

def _estimate_tokens(text: str) -> int:
    """粗估 token 数量（1 token ≈ 4 字符）"""
    return max(1, len(text) // 4)

def _ai_budget_paths(run_dir: str) -> Tuple[Path, Path]:
    """获取 AI 指标文件路径"""
    rd = Path(run_dir)
    return rd / "ai_metrics.jsonl", rd / "stability_metrics.jsonl"

def _ai_append_metrics(run_dir: str, kind: str, payload: Dict[str, Any]):
    """追加 AI 指标"""
    mpath, _ = _ai_budget_paths(run_dir)
    try:
        with mpath.open("a", encoding="utf-8") as fo:
            rec = {"ts": _ts_utc(), "kind": kind, **payload}
            fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass

def _ai_guard_check(run_dir: str, cfg: dict, cur_tokens: int, cur_cost_usd: float) -> tuple[bool, str]:
    """
    检查 AI 预算护栏（返回 (是否可继续, 原因)）
    
    返回：
    - (True, "") - 可继续
    - (False, "tokens_exceeded") - token 超限
    - (False, "cost_exceeded") - 成本超限
    """
    max_tok = int(cfg.get("max_tokens_per_run") or 0)
    max_cost = float(cfg.get("max_daily_cost_usd") or 0)
    
    if max_tok > 0 and cur_tokens > max_tok:
        return False, "tokens_exceeded"
    if max_cost > 0 and cur_cost_usd > max_cost:
        return False, "cost_exceeded"
    
    return True, ""

def _ai_guard_warn(run_dir: str, reason: str):
    """记录 AI 护栏警告"""
    try:
        wf = Path(run_dir) / "warnings.txt"
        with wf.open("a", encoding="utf-8") as f:
            f.write(f"ai_guard\t{reason}\n")
    except Exception:
        pass

# ---------- 章节对齐 ----------
def _align_chapters_with_srt(
    base_text: str, 
    srt_or_vtt: Path, 
    chapters: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """基于字幕时间轴精确对齐章节"""
    try:
        raw = srt_or_vtt.read_text("utf-8", errors="ignore")
    except Exception:
        return chapters
    
    cues = _strip_srt_lines(raw) if srt_or_vtt.suffix.lower() == ".srt" else _strip_vtt_lines(raw)
    if not cues:
        return chapters
    
    texts = [t for _, __, t in cues]
    joined = " ".join(texts)
    if not joined.strip():
        return chapters
    
    def norm(s): 
        return re.sub(r"\s+", " ", (s or "").lower()).strip()
    
    for ch in chapters:
        q = (ch.get("title") or "") + " " + " ".join(ch.get("key_points") or [])
        ch["_q"] = norm(q)[:200]
    
    W = 25
    tokens_cues = [set(re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", norm(t))) for t in texts]
    
    for idx, ch in enumerate(chapters):
        rough = int(idx * len(cues) / max(1, len(chapters)))
        st = max(0, rough - W)
        ed = min(len(cues) - 1, rough + W)
        qtok = set(re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", ch["_q"]))
        best_i, best_score = st, -1.0
        for i in range(st, ed + 1):
            inter = len(qtok & tokens_cues[i])
            union = len(qtok | tokens_cues[i]) or 1
            jacc = inter / union
            if jacc > best_score:
                best_score = jacc
                best_i = i
        start_sec = cues[best_i][0]
        ch["start"] = "{:02d}:{:02d}:{:02d}".format(
            int(start_sec // 3600), 
            int(start_sec % 3600 // 60), 
            int(start_sec % 60)
        )
        ch.pop("_q", None)
    return chapters

# ---------- AI 处理 ----------
def _read_text_any(txt_path: Path) -> str:
    """读取文本文件"""
    try:
        return txt_path.read_text("utf-8", errors="ignore")
    except Exception:
        return ""

def _video_id_from_name(path: Path) -> str:
    """从文件名提取视频 ID"""
    stem = path.stem
    m = re.search(r"[A-Za-z0-9_-]{11}", stem)
    return m.group(0) if m else stem.split(".")[0]

def _select_caption_file(subs_dir: Path, vid: str) -> Path | None:
    """选择字幕文件"""
    for ext in ("txt", "srt", "vtt"):
        for lang in ("zh", "en"):
            p = subs_dir / f"{vid}.{lang}.{ext}"
            if p.exists(): 
                return p
    for ext in ("txt", "srt", "vtt"):
        for p in subs_dir.glob(f"{vid}.*.{ext}"):
            if p.exists(): 
                return p
    return None

def _ensure_txt_from_caption(fp: Path) -> Path | None:
    """确保有 TXT 文件"""
    if fp.suffix.lower() == ".txt":
        return fp
    out = fp.with_suffix(".txt")
    if fp.suffix.lower() == ".srt":
        from .download import convert_srt_to_txt
        return out if convert_srt_to_txt(fp, out) else None
    if fp.suffix.lower() == ".vtt":
        from .download import convert_vtt_to_txt
        return out if convert_vtt_to_txt(fp, out) else None
    return None

def _ai_cache_key(text: str, cfg: dict, lang: str = "auto") -> str:
    """
    生成 AI 缓存键（扩充版，防止错命中）
    
    包含：text_sha1 + provider + model + chunk + merge + lang + version
    """
    providers = cfg.get("providers", [])
    prov_info = []
    for p in providers:
        prov_info.append({
            "name": p.get("name"),
            "model": p.get("model")
        })
    
    core = json.dumps({
        "text_sha1": _sha1(text),
        "providers": prov_info,
        "chunk_chars": cfg.get("chunk_chars"),
        "merge_strategy": cfg.get("merge_strategy"),
        "lang": lang,
        "version": "v1"
    }, ensure_ascii=False, sort_keys=True)
    return _sha1(core)

def ai_process_video(
    txt_path: str | Path, 
    ai_cfg: dict | None = None, 
    lang_pref: list | None = None, 
    run_dir_hint: str | None = None
) -> dict:
    """处理单个视频的 AI 流水线"""
    out = {"ok": False, "out": "", "video_id": ""}
    try:
        if AIClient is None:
            return out
        
        txt_path = Path(txt_path)
        vid = _video_id_from_name(txt_path)  # 提取 video_id（防止后续 F821 错误）
        text = _read_text_any(txt_path)
        if not text.strip():
            return out
        
        cfg_all = load_config()
        cfg = ai_cfg or (cfg_all.get("ai") or {})
        if not cfg or not cfg.get("enabled", False):
            return out
        
        # 预算护栏
        run_dir = run_dir_hint or (str(Path(txt_path).parents[1]) if txt_path.parent.name == "subs" else str(Path(txt_path).parent))
        mpath, _ = _ai_budget_paths(run_dir)
        cur_tokens = 0
        cur_cost = 0.0
        if mpath.exists():
            try:
                for ln in mpath.read_text("utf-8", "ignore").splitlines():
                    try:
                        rec = json.loads(ln)
                        if rec.get("kind") == "usage":
                            cur_tokens += int(rec.get("tokens", 0))
                            cur_cost += float(rec.get("cost_usd", 0.0))
                    except: 
                        pass
            except: 
                pass
        
        to_add = _estimate_tokens(text[: int(cfg.get("max_chars_per_video") or 30000)])
        can_continue, reason = _ai_guard_check(run_dir, cfg, cur_tokens + to_add, cur_cost)
        if not can_continue:
            _ai_guard_warn(run_dir, f"budget_{reason}")
            # 记录护栏停止事件
            _ai_append_metrics(run_dir, "guard_stop", {
                "reason": reason,
                "cur_tokens": cur_tokens,
                "cur_cost_usd": cur_cost,
                "video_id": _video_id_from_name(txt_path) if isinstance(txt_path, Path) else ""
            })
            return out  # 硬停
        
        # 缓存机制（扩充 key）
        cache_enabled = bool(cfg.get("cache_enabled", True))
        cache_dir = Path(run_dir) / "ai_cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        lp = [x.lower() for x in (lang_pref or cfg.get("lang_pref") or ["zh", "en"])]
        lang = "zh" if "zh" in lp else (lp[0] if lp else "auto")
        key = _ai_cache_key(text, cfg, lang)
        cache_path = cache_dir / f"{key}.json"
        
        if cache_enabled and cache_path.exists():
            data = json.loads(cache_path.read_text("utf-8"))
            # 记录缓存命中
            if cfg.get("metrics_enabled", True):
                _ai_append_metrics(run_dir, "cache_hit", {
                    "video_id": vid,
                    "cache_key": key[:16]
                })
        else:
            client = AIClient.from_config(cfg)
            ai_timeout = int(cfg.get("ai_timeout_s", 60))
            
            try:
                # 带超时的 AI 调用
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    fut_summary = ex.submit(client.summarize, text, lang)
                    fut_chapters = ex.submit(client.chapters, text, lang)
                    
                    try:
                        s = fut_summary.result(timeout=ai_timeout)
                        ch_result = fut_chapters.result(timeout=ai_timeout)
                    except concurrent.futures.TimeoutError:
                        raise RuntimeError(f"AI timeout after {ai_timeout}s")
                
                # 解包 chapters 返回值（现在是 tuple）
                if isinstance(ch_result, tuple) and len(ch_result) == 2:
                    ch, ch_meta = ch_result
                else:
                    ch = ch_result or []
                    ch_meta = {}
                
                data = {
                    "lang": lang,
                    "summary": s.get("summary", ""),
                    "key_points": s.get("key_points", []),
                    "keywords": s.get("keywords", []),
                    "chapters": ch or [],
                    "meta": s.get("meta", {}),
                }
                if cache_enabled:
                    save_json(cache_path, data)
                if cfg.get("metrics_enabled", True):
                    _ai_append_metrics(run_dir, "usage", {
                        "tokens": to_add,
                        "cost_usd": 0.0,
                        "provider": data["meta"].get("provider"),
                        "model": data["meta"].get("model")
                    })
            except Exception as e:
                # 记录失败到 ai_failed.jsonl
                fail_file = Path(run_dir) / "ai_failed.jsonl"
                try:
                    with fail_file.open("a", encoding="utf-8") as ff:
                        fail_rec = {
                            "ts": _ts_utc(),
                            "file": str(txt_path),
                            "video_id": vid,
                            "err": str(type(e).__name__),
                            "err_msg": str(e)[:200],
                            "provider": cfg.get("providers", [{}])[0].get("name", "unknown"),
                            "model": cfg.get("providers", [{}])[0].get("model", "")
                        }
                        ff.write(json.dumps(fail_rec, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                
                # 记录到 metrics
                if cfg.get("metrics_enabled", True):
                    _ai_append_metrics(run_dir, "provider_error", {
                        "video_id": vid,
                        "error_type": str(type(e).__name__),
                        "error_msg": str(e)[:200],
                        "provider": cfg.get("providers", [{}])[0].get("name", "unknown")
                    })
                raise
        
        # 章节对齐（健壮版）
        vid = _video_id_from_name(txt_path)
        subs_dir = Path(run_dir) / "subs"
        cap = _select_caption_file(subs_dir, vid)
        
        if data.get("chapters"):
            if cap and cap.suffix.lower() in (".srt", ".vtt"):
                # 尝试对齐
                try:
                    aligned = _align_chapters_with_srt(text, cap, data["chapters"])
                    # 检查对齐置信度（简化：检查是否有变化）
                    changed = sum(1 for i, ch in enumerate(aligned) if ch.get("start") != data["chapters"][i].get("start", "00:00:00"))
                    if changed == 0:
                        # 对齐失败，回退原始
                        _ai_guard_warn(run_dir, f"align_low_conf\t{vid}")
                    else:
                        data["chapters"] = aligned
                except Exception as e:
                    logging.warning(f"章节对齐失败 {vid}: {e}")
                    _ai_guard_warn(run_dir, f"align_error\t{vid}\t{e}")
            else:
                # 无字幕，回退 00:00:00
                for ch in data["chapters"]:
                    ch["start"] = "00:00:00"
                _ai_guard_warn(run_dir, f"align_fallback_no_subs\t{vid}")
        
        # 保存结果
        out_dir = Path(run_dir) / "ai"
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {"video_id": vid, **data}
        jpath = out_dir / f"{vid}.json"
        save_json(jpath, payload)
        
        out.update({"ok": True, "out": str(jpath), "video_id": vid, "meta": data.get("meta")})
        
        # 索引
        try:
            idx = Path(run_dir) / "ai_index.jsonl"
            brief = (payload.get("summary") or "")[:120].replace("\n", " ")
            rec = {"video_id": vid, "summary_120": brief, "keywords": payload.get("keywords", [])}
            with idx.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
        
        return out
    except Exception as e:
        try:
            fail = Path(run_dir_hint or ".") / "ai_failed.jsonl"
            with fail.open("a", encoding="utf-8") as fo:
                fo.write(json.dumps({"ts": _ts_utc(), "file": str(txt_path), "err": str(e)}) + "\n")
        except Exception:
            pass
        return out

def run_ai_pipeline(
    run_dir: str, 
    ai_cfg: dict | None = None, 
    workers: int = 3,
    lang_pref: list | None = None, 
    resume: bool = True
) -> dict:
    """
    对 run_dir/subs/ 中的字幕文件运行 AI 处理流水线
    
    返回：{"total": int, "done": int, "outputs": list[str]}
    """
    result = {"total": 0, "done": 0, "outputs": []}
    try:
        if AIClient is None:
            return result
        
        cfg = ai_cfg or (load_config().get("ai") or {})
        if not cfg or not cfg.get("enabled", False):
            return result
        
        subs_dir = Path(run_dir) / "subs"
        if not subs_dir.exists():
            return result
        
        vids = set()
        for fp in subs_dir.glob("*.*"):
            if fp.is_file():
                m = re.search(r"[A-Za-z0-9_-]{11}", fp.name)
                if m:
                    vids.add(m.group(0))
        vids = sorted(vids)
        result["total"] = len(vids)
        if not vids:
            return result
        
        ai_dir = Path(run_dir) / "ai"
        ai_dir.mkdir(parents=True, exist_ok=True)
        
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as ex:
            futs = []
            for vid in vids:
                if resume and (ai_dir / f"{vid}.json").exists():
                    continue
                cap = _select_caption_file(subs_dir, vid)
                if not cap:
                    continue
                txt = _ensure_txt_from_caption(cap) or cap
                futs.append(ex.submit(ai_process_video, str(txt), cfg, lang_pref, run_dir))
            for f in as_completed(futs):
                out = f.result()
                if out.get("ok"):
                    result["done"] += 1
                    result["outputs"].append(out["out"])
        
        return result
    except Exception:
        return result

def reprocess_ai_errors(run_dir: str, **kwargs) -> dict:
    """
    重新处理 AI 失败的文件
    
    返回：{"retried": int, "fixed": int, "still_failed": int}
    """
    fail = Path(run_dir) / "ai_failed.jsonl"
    if not fail.exists():
        return {"retried": 0, "fixed": 0, "still_failed": 0}
    
    files = []
    for ln in fail.read_text("utf-8", "ignore").splitlines():
        try:
            d = json.loads(ln)
            fp = d.get("file")
            if fp and os.path.exists(fp): 
                files.append(fp)
        except: 
            pass
    
    if not files:
        return {"retried": 0, "fixed": 0, "still_failed": 0}
    
    ok = 0
    for fp in files:
        r = ai_process_video(fp, run_dir_hint=run_dir, ai_cfg=kwargs.get("ai_cfg"), lang_pref=kwargs.get("lang_pref"))
        ok += int(bool(r.get("ok")))
    
    still = len(files) - ok
    return {"retried": len(files), "fixed": ok, "still_failed": still}

