# -*- coding: utf-8 -*-
"""
core.utils — 通用工具函数（URL/ID/索引/原子IO/SHA1）
"""
from __future__ import annotations
import re, os, json, hashlib
from pathlib import Path
from typing import Set, Any
from urllib.parse import urlparse, parse_qs

# ---------- 正则表达式 ----------
YOUTUBE_URL_RE = re.compile(r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/", re.I)
ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
CHINESE_PREFIXES = ("zh", "cmn")
ENGLISH_PREFIXES = ("en",)

def is_youtube_url(u: str) -> bool:
    """检查是否为 YouTube URL"""
    return bool(YOUTUBE_URL_RE.search(u or ""))

def safe_filename(name: str) -> str:
    """清理文件名中的非法字符"""
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name or "")
    return name[:180]

def extract_video_id(url: str) -> str:
    """
    从 URL 提取视频 ID（增强版）
    
    支持格式：
    - watch?v=ID
    - youtu.be/ID
    - /shorts/ID
    - /live/ID
    - /embed/ID
    - /v/ID
    
    自动剥离查询参数和锚点
    """
    if not url: 
        return ""
    
    # 先剥离锚点
    url = url.split("#")[0]
    
    u = urlparse(url)
    
    # 1. watch?v=ID 格式
    qv = parse_qs(u.query).get("v", [])
    if qv and ID_RE.match(qv[0]): 
        return qv[0]
    
    # 2. youtu.be/ID 格式
    if u.netloc.endswith("youtu.be") and u.path:
        # 剥离查询参数（如 youtu.be/ID?si=xxx）
        seg = u.path.strip("/").split("/")[0].split("?")[0]
        if ID_RE.match(seg):
            return seg
    
    # 3. /shorts/ID, /live/ID, /embed/ID, /v/ID 格式
    parts = [p for p in (u.path or "").split("/") if p]
    if len(parts) >= 2 and parts[0].lower() in ("shorts", "live", "embed", "v"):
        # 剥离查询参数
        candidate = parts[1].split("?")[0]
        if ID_RE.match(candidate):
            return candidate
    
    # 4. 兜底：路径最后一段
    if parts:
        tail = parts[-1].split("?")[0]  # 剥离查询参数
        if ID_RE.match(tail):
            return tail
    
    return ""

def normalize_url(url: str) -> str:
    """标准化 URL 格式"""
    vid = extract_video_id(url)
    return f"https://www.youtube.com/watch?v={vid}" if vid else ""

def flatten_langs(d: dict) -> Set[str]:
    """扁平化语言字典的键为集合"""
    if not d: 
        return set()
    return {(k or "").lower() for k in d.keys() if k}

def _ts_utc() -> str:
    """生成 UTC 时间戳字符串"""
    import datetime as _dt
    return _dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

def ensure_channel_videos_url(url: str) -> str:
    """确保频道 URL 指向 /videos 页面"""
    if not url: 
        return url
    u = urlparse(url)
    parts = [p for p in (u.path or "").split("/") if p]
    if not parts: 
        return url
    if parts[0].startswith("@") and len(parts) == 1: 
        return f"https://www.youtube.com/{parts[0]}/videos"
    if parts[0] in ("channel","c","user") and len(parts) == 2: 
        return f"https://www.youtube.com/{parts[0]}/{parts[1]}/videos"
    return url

def _norm_lang(code: str) -> str:
    """规范化语言码到 BCP-47 简约前缀"""
    code = (code or "").lower().strip()
    if not code:
        return ""
    # 中文系列 → zh
    if code.startswith(("zh", "cmn", "yue", "nan")):
        return "zh"
    # 英文系列 → en
    if code.startswith("en"):
        return "en"
    # 其他：取主码（- 之前）
    return code.split("-")[0]

def classify_error(e: Exception | str) -> str:
    """
    分类错误信息（细化版）
    
    - error_429/error_503/error_timeout: 触发熔断器
    - error_private/error_geo/error_unavailable: 不触发熔断（短路）
    - error_other: 其他错误
    """
    s = (e if isinstance(e, str) else str(e)).lower()
    # 限流类（触发熔断）
    if "429" in s or "too many requests" in s: 
        return "error_429"
    if "503" in s or "service unavailable" in s: 
        return "error_503"
    if "timeout" in s or "timed out" in s: 
        return "error_timeout"
    # 访问限制类（不触发熔断）
    if "private" in s or "members-only" in s: 
        return "error_private"
    if "unavailable" in s or "not available" in s: 
        return "error_unavailable"
    if "region" in s or "geo" in s or "country" in s: 
        return "error_geo"
    if "disabled" in s or "blocked" in s:
        return "error_blocked"
    return "error_other"

# ---------- 历史索引 ----------
def _history_file(root: str) -> Path: 
    return Path(root) / "history.jsonl"

def _channel_index_file(root: str) -> Path: 
    return Path(root) / "channel_index.json"

def history_append(root: str, rec: dict):
    """追加历史记录"""
    with _history_file(root).open("a", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False)
        f.write("\n")

def channel_index_load(root: str) -> dict:
    """加载频道索引"""
    p = _channel_index_file(root)
    if p.exists():
        try: 
            return json.loads(p.read_text("utf-8"))
        except: 
            return {}
    return {}

def channel_index_save(root: str, d: dict):
    """
    保存频道索引（原子写）
    
    使用 .tmp + replace() 避免并发写入导致文件损坏
    """
    safe_write_json(_channel_index_file(root), d)

# ---------- 原子IO ----------
def safe_write_json(path: Path, obj: Any):
    """
    原子写入 JSON 文件
    
    使用 .tmp + replace() 确保并发安全
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)  # 原子替换
    except Exception:
        if tmp.exists():
            try:
                tmp.unlink()
            except:
                pass
        raise

def safe_read_text(path: Path) -> str:
    """
    统一读取文本文件（容错）
    
    使用 errors="ignore" 避免编码问题
    """
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

# ---------- SHA1 哈希 ----------
def sha1_of_text(text: str) -> str:
    """计算文本的 SHA1"""
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()

def sha1_of_file(path: Path) -> str:
    """计算文件的 SHA1"""
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except Exception:
        return ""

