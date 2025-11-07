# -*- coding: utf-8 -*-
"""
旗舰模式 Phase 1: 高级重试策略
智能处理 429/403/网络错误的回退机制
"""
from __future__ import annotations
import time
import logging
import random
from typing import Callable, Any, Optional
from enum import Enum


class RetryReason(Enum):
    """重试原因"""
    RATE_LIMIT_429 = "429_rate_limit"         # API 限流
    FORBIDDEN_403 = "403_forbidden"           # 访问禁止
    NETWORK_ERROR = "network_error"           # 网络错误
    TIMEOUT = "timeout"                       # 超时
    SERVER_ERROR_5XX = "5xx_server_error"     # 服务器错误
    UNKNOWN = "unknown"                       # 未知错误


class RetryStrategy:
    """
    高级重试策略（旗舰版）
    
    特性：
    - 指数退避算法
    - 针对不同错误类型的差异化策略
    - 最大重试次数限制
    - 随机抖动避免雪崩
    """
    
    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 300.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        初始化重试策略
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            exponential_base: 指数退避基数
            jitter: 是否添加随机抖动
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        
        # 不同错误类型的重试倍数
        self.error_multipliers = {
            RetryReason.RATE_LIMIT_429: 3.0,     # 限流：更长等待
            RetryReason.FORBIDDEN_403: 2.0,       # 禁止：较长等待
            RetryReason.NETWORK_ERROR: 1.0,       # 网络：标准等待
            RetryReason.TIMEOUT: 1.5,             # 超时：稍长等待
            RetryReason.SERVER_ERROR_5XX: 2.0,    # 服务器：较长等待
            RetryReason.UNKNOWN: 1.0,             # 未知：标准等待
        }
        
        logging.info(
            f"[RETRY] 策略初始化: max={max_retries}, "
            f"base={base_delay}s, max={max_delay}s"
        )
    
    def calculate_delay(
        self,
        attempt: int,
        reason: RetryReason = RetryReason.UNKNOWN
    ) -> float:
        """
        计算指数退避延迟时间
        
        Args:
            attempt: 当前重试次数（从 0 开始）
            reason: 重试原因
        
        Returns:
            延迟时间（秒）
        """
        # 基础指数延迟
        delay = self.base_delay * (self.exponential_base ** attempt)
        
        # 应用错误类型倍数
        multiplier = self.error_multipliers.get(reason, 1.0)
        delay *= multiplier
        
        # 添加随机抖动（±20%）
        if self.jitter:
            jitter_factor = 1.0 + (random.random() * 0.4 - 0.2)
            delay *= jitter_factor
        
        # 限制最大延迟
        delay = min(delay, self.max_delay)
        
        return delay
    
    def should_retry(self, attempt: int, reason: RetryReason) -> bool:
        """
        判断是否应该重试
        
        Args:
            attempt: 当前重试次数
            reason: 重试原因
        
        Returns:
            True if 应该重试, False otherwise
        """
        # 超过最大重试次数
        if attempt >= self.max_retries:
            return False
        
        # 特定错误类型不重试
        if reason == RetryReason.FORBIDDEN_403 and attempt >= 2:
            # 403 最多重试 2 次
            return False
        
        return True
    
    def execute_with_retry(
        self,
        func: Callable[..., Any],
        *args,
        error_classifier: Optional[Callable[[Exception], RetryReason]] = None,
        **kwargs
    ) -> tuple[Any, dict]:
        """
        执行函数并自动重试
        
        Args:
            func: 要执行的函数
            error_classifier: 错误分类器（将异常转换为 RetryReason）
            *args, **kwargs: 传递给函数的参数
        
        Returns:
            (执行结果, 重试统计)
        """
        attempt = 0
        stats = {
            "total_attempts": 0,
            "total_delay": 0.0,
            "errors": [],
            "success": False
        }
        
        while True:
            try:
                # 执行函数
                result = func(*args, **kwargs)
                stats["success"] = True
                stats["total_attempts"] = attempt + 1
                
                if attempt > 0:
                    logging.info(
                        f"[RETRY] 成功（重试 {attempt} 次，"
                        f"总延迟 {stats['total_delay']:.1f}s）"
                    )
                
                return result, stats
            
            except Exception as e:
                # 分类错误
                if error_classifier:
                    reason = error_classifier(e)
                else:
                    reason = self._classify_error(e)
                
                stats["errors"].append({
                    "attempt": attempt,
                    "reason": reason.value,
                    "message": str(e)
                })
                
                # 判断是否应该重试
                if not self.should_retry(attempt, reason):
                    logging.error(
                        f"[RETRY] 放弃重试: {reason.value}, "
                        f"尝试 {attempt + 1} 次"
                    )
                    stats["total_attempts"] = attempt + 1
                    raise
                
                # 计算延迟时间
                delay = self.calculate_delay(attempt, reason)
                stats["total_delay"] += delay
                
                logging.warning(
                    f"[RETRY] 尝试 {attempt + 1}/{self.max_retries} 失败 "
                    f"({reason.value}), 等待 {delay:.1f}s 后重试: {e}"
                )
                
                # 等待后重试
                time.sleep(delay)
                attempt += 1
    
    def _classify_error(self, error: Exception) -> RetryReason:
        """
        自动分类错误
        
        Args:
            error: 异常对象
        
        Returns:
            RetryReason
        """
        error_str = str(error).lower()
        error_type = type(error).__name__.lower()
        
        # 检查 429 限流
        if "429" in error_str or "rate limit" in error_str or "too many requests" in error_str:
            return RetryReason.RATE_LIMIT_429
        
        # 检查 403 禁止
        if "403" in error_str or "forbidden" in error_str:
            return RetryReason.FORBIDDEN_403
        
        # 检查 5xx 服务器错误
        if any(code in error_str for code in ["500", "502", "503", "504"]):
            return RetryReason.SERVER_ERROR_5XX
        
        # 检查超时
        if "timeout" in error_str or "timed out" in error_str:
            return RetryReason.TIMEOUT
        
        # 检查网络错误
        if any(keyword in error_type for keyword in ["connection", "network", "socket"]):
            return RetryReason.NETWORK_ERROR
        
        return RetryReason.UNKNOWN


# 全局默认策略实例
_default_strategy: Optional[RetryStrategy] = None


def get_default_strategy() -> RetryStrategy:
    """获取全局默认重试策略"""
    global _default_strategy
    if _default_strategy is None:
        _default_strategy = RetryStrategy(
            max_retries=5,
            base_delay=2.0,
            max_delay=300.0,
            exponential_base=2.0,
            jitter=True
        )
    return _default_strategy


def retry_with_backoff(
    func: Callable[..., Any],
    *args,
    max_retries: int = 5,
    **kwargs
) -> Any:
    """
    便捷装饰器函数：执行函数并自动重试
    
    Args:
        func: 要执行的函数
        max_retries: 最大重试次数
        *args, **kwargs: 传递给函数的参数
    
    Returns:
        函数执行结果
    """
    strategy = RetryStrategy(max_retries=max_retries)
    result, _ = strategy.execute_with_retry(func, *args, **kwargs)
    return result


__all__ = [
    'RetryStrategy',
    'RetryReason',
    'get_default_strategy',
    'retry_with_backoff'
]

