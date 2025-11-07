# -*- coding: utf-8 -*-
"""
core.net — 网络通用层（代理池/限流/熔断/Webhook）
"""
from __future__ import annotations
import time, threading, logging, random
from typing import List, Dict, Any, Optional

def jitter_sleep(base_sec: float, jitter_ratio: float = 0.15):
    """
    带随机抖动的睡眠（避免雷鸣效应）
    
    jitter_ratio: 抖动范围（±15% 为默认）
    """
    if base_sec <= 0:
        return
    actual = base_sec * (1.0 + random.uniform(-jitter_ratio, jitter_ratio))
    time.sleep(max(0, actual))

class RateLimiter:
    """令牌桶限流器"""
    def __init__(self, rate: float, capacity: int | None = None):
        self.rate = max(0.0, rate)
        self.capacity = capacity or max(1.0, rate * 2.0)
        self.tokens = self.capacity
        self.t = time.perf_counter()
        self._lock = threading.Lock()
    
    def acquire(self):
        """获取一个令牌（阻塞）"""
        if self.rate <= 0: 
            return
        with self._lock:
            now = time.perf_counter()
            dt = now - self.t
            self.t = now
            self.tokens = min(self.capacity, self.tokens + dt * self.rate)
            if self.tokens < 1.0:
                need = 1.0 - self.tokens
                time.sleep(need / self.rate)
                self.tokens = 0.0
                self.t = time.perf_counter()
            else:
                self.tokens -= 1.0

class CircuitBreaker:
    """
    熔断器（自动冷静期 + 热配置）
    
    支持运行时更新阈值和冷静期
    """
    def __init__(self, threshold: int = 8, cooldown: float = 120.0, 
                 kinds=("error_429", "error_503", "error_timeout")):
        self.th = int(max(1, threshold))
        self.cd = float(cooldown)
        self.k = set(kinds)
        self.fail = 0
        self.until = 0.0
        self._lock = threading.Lock()
    
    def update_config(self, threshold: Optional[int] = None, cooldown: Optional[float] = None):
        """
        热更新配置（无需重启）
        
        threshold: 新的失败阈值
        cooldown: 新的冷静期（秒）
        """
        with self._lock:
            if threshold is not None:
                self.th = int(max(1, threshold))
            if cooldown is not None:
                self.cd = float(cooldown)
    
    def record(self, ok: bool, et: str | None = None):
        """记录一次请求结果"""
        with self._lock:
            if time.time() < self.until: 
                return
            if ok: 
                self.fail = max(0, self.fail - 1)
            else:
                if et and et in self.k:
                    self.fail += 1
                    if self.fail >= self.th: 
                        self.until = time.time() + self.cd
                        self.fail = 0
    
    def should_cooldown(self) -> bool:
        """是否处于冷静期"""
        return time.time() < self.until
    
    def remaining(self) -> float:
        """剩余冷静时间（秒）"""
        return max(0.0, self.until - time.time())

class ProxyPool:
    """
    代理池（轮询/健康评分/自动黑名单恢复）
    
    评分机制：score = 0.7 * success_rate + 0.3 * latency_score
    黑名单自动恢复：冷却期（默认10分钟）后自动解除
    """
    def __init__(self, items: List[str], cool: int = 300, max_fail: int = 2, 
                 window: int = 30, bl_rate: float = 0.15,
                 blacklist_recovery_sec: int = 600):
        self._lock = threading.Lock()
        self.items = []
        self.state = {}
        self.stats = {}
        self.lat = {}
        self.cool = cool
        self.max_fail = max_fail
        self.window = window
        self.bl_rate = bl_rate
        self.bl_recovery = blacklist_recovery_sec  # 黑名单恢复时间
        self._idx = 0
        for p in self._norm(items):
            self.items.append(p)
            self.state[p] = {
                "fails": 0, "cool": 0, "black": False, 
                "blacklist_until": 0.0,  # 黑名单解除时间
                "lat": None, "score": 1.0,
                "success": 0, "total": 0  # 累计成功/总数
            }
            self.stats[p] = []
            self.lat[p] = []
    
    @staticmethod
    def _norm(items):
        """标准化代理列表（支持文件引用 file:）"""
        out = []
        seen = set()
        for s in items or []:
            s = (s or "").strip()
            if not s: 
                continue
            if s.lower().startswith("file:"):
                path = s.split(":", 1)[1].strip()
                try:
                    for ln in open(path, "r", encoding="utf-8"):
                        v = ln.strip()
                        if v and v not in seen: 
                            out.append(v)
                            seen.add(v)
                except: 
                    pass
            else:
                if s not in seen: 
                    out.append(s)
                    seen.add(s)
        return out
    
    def _avail(self):
        """
        获取可用代理列表（自动恢复黑名单）
        
        黑名单代理在冷却期后自动解除
        """
        now = time.time()
        avail = []
        for p in self.items:
            st = self.state[p]
            # 自动解除黑名单
            if st["black"] and st["blacklist_until"] <= now:
                st["black"] = False
                st["blacklist_until"] = 0.0
                logging.info(f"代理 {p[:20]}... 从黑名单恢复")
            
            if st["cool"] <= now and not st["black"]:
                avail.append(p)
        return avail
    
    def _push(self, p, ok, lat):
        """
        记录代理使用结果并更新评分
        
        评分公式：score = 0.7 * success_rate + 0.3 * latency_score
        低于阈值自动拉黑（冷却10分钟）
        """
        st = self.state[p]
        
        # 更新累计统计
        st["total"] += 1
        if ok:
            st["success"] += 1
        
        # 滑动窗口统计
        a = self.stats[p]
        a.append(1 if ok else 0)
        if len(a) > self.window: 
            a.pop(0)
        
        # 延迟统计
        if lat is not None:
            self.lat[p].append(float(lat))
            if len(self.lat[p]) > self.window: 
                self.lat[p].pop(0)
            st["lat"] = sum(self.lat[p]) / len(self.lat[p]) if self.lat[p] else None
        
        # 计算评分
        rate = sum(a) / len(a) if a else 1.0
        latv = st["lat"] or 1200.0
        lat_score = 1.0 / (1.0 + (latv / 800.0))
        st["score"] = 0.7 * rate + 0.3 * lat_score
        
        # 低分自动拉黑（评分低于阈值，如0.3）
        score_threshold = 0.3
        if st["score"] < score_threshold and len(a) >= self.window // 2:
            if not st["black"]:
                st["black"] = True
                st["blacklist_until"] = time.time() + self.bl_recovery
                logging.warning(f"代理 {p[:20]}... 评分低于 {score_threshold}，拉入黑名单（冷却 {self.bl_recovery}s）")
    
    def get(self) -> str:
        """获取一个可用代理"""
        with self._lock:
            a = self._avail()
            if not a: 
                return ""
            a_sorted = sorted(a, key=lambda x: self.state[x]["score"], reverse=True)
            self._idx = (self._idx + 1) % len(a_sorted)
            return a_sorted[self._idx]
    
    def bad(self, p, lat=None):
        """标记代理失败"""
        if not p: 
            return
        with self._lock:
            st = self.state[p]
            st["fails"] += 1
            self._push(p, False, lat)
            if st["fails"] >= self.max_fail: 
                st["cool"] = time.time() + self.cool
                st["fails"] = 0
    
    def ok(self, p, lat=None):
        """标记代理成功"""
        if not p: 
            return
        with self._lock:
            st = self.state[p]
            st["fails"] = 0
            self._push(p, True, lat)
    
    def stats_snapshot(self) -> Dict[str, Any]:
        """获取代理池统计快照（包含累计成功/总数）"""
        with self._lock:
            return {
                p: {
                    "cool_until": self.state[p]["cool"],
                    "black": self.state[p]["black"],
                    "blacklist_until": self.state[p]["blacklist_until"],
                    "success_rate": (sum(self.stats[p]) / len(self.stats[p])) if self.stats[p] else None,
                    "latency_ms": self.state[p]["lat"],
                    "score": self.state[p]["score"],
                    "success": self.state[p]["success"],
                    "total": self.state[p]["total"]
                } for p in self.items
            }

_CURRENT_PROXY_POOL = None

def build_proxy_pool(proxy_text: str, mode: str = "round_robin",
                     proxy_cool_down_sec: int = 300, proxy_max_fails: int = 2,
                     proxy_blacklist_threshold: float = 0.15, 
                     proxy_window: int = 30,
                     blacklist_recovery_sec: int = 600) -> ProxyPool | None:
    """
    构建代理池
    
    blacklist_recovery_sec: 黑名单自动恢复时间（默认10分钟）
    """
    global _CURRENT_PROXY_POOL
    items = [(ln or "").strip() for ln in (proxy_text or "").splitlines() if (ln or "").strip()]
    if not items: 
        _CURRENT_PROXY_POOL = None
        return None
    _CURRENT_PROXY_POOL = ProxyPool(
        items, cool=proxy_cool_down_sec, max_fail=proxy_max_fails, 
        window=proxy_window, bl_rate=proxy_blacklist_threshold,
        blacklist_recovery_sec=blacklist_recovery_sec
    )
    return _CURRENT_PROXY_POOL

def get_current_proxy_stats() -> Dict[str, Any] | None:
    """获取当前代理池统计"""
    try: 
        return _CURRENT_PROXY_POOL.stats_snapshot() if _CURRENT_PROXY_POOL else None
    except Exception: 
        return None

def notify_via_webhook(url: str, payload: Dict[str, Any]) -> bool:
    """通过 Webhook 发送通知"""
    try:
        import requests
    except Exception:
        return False
    try:
        r = requests.post(url, json=payload, timeout=10)
        return 200 <= r.status_code < 300
    except Exception:
        return False

