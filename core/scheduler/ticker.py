# -*- coding: utf-8 -*-
"""
Day 3 补丁：后台自动调度线程
实现真正的无人值守
"""
import threading
import time
import traceback
import logging
from datetime import datetime
from typing import Optional


class SchedulerTicker:
    """
    后台调度器 Ticker
    
    职责：
    - 定期执行 SchedulerEngine.tick()
    - 守护线程运行，不阻塞主线程
    - 支持优雅停机
    """
    
    def __init__(self, engine, interval_sec: int = 60):
        """
        初始化
        
        Args:
            engine: SchedulerEngine 实例
            interval_sec: tick 间隔（秒），默认60秒
        """
        self.engine = engine
        self.interval = max(10, int(interval_sec))  # 最小10秒
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        logging.info(f"[TICKER] 初始化完成，间隔={self.interval}秒")
    
    def start(self):
        """启动后台 tick 线程"""
        if self._thread and self._thread.is_alive():
            logging.warning("[TICKER] 已在运行，跳过启动")
            return
        
        self._stop.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            name="SchedulerTicker",
            daemon=True  # 守护线程，主程序退出时自动终止
        )
        self._thread.start()
        
        logging.info(f"[TICKER] 后台调度已启动，间隔={self.interval}秒")
    
    def stop(self, timeout: float = 5.0):
        """
        停止后台线程
        
        Args:
            timeout: 等待线程结束的超时时间（秒）
        """
        if not self._running:
            return
        
        logging.info("[TICKER] 正在停止后台调度...")
        self._stop.set()
        self._running = False
        
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=timeout)
            if t.is_alive():
                logging.warning("[TICKER] 线程未能在超时时间内结束")
            else:
                logging.info("[TICKER] 后台调度已停止")
    
    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._running and self._thread and self._thread.is_alive()
    
    def _loop(self):
        """后台循环：定期执行 tick"""
        logging.info("[TICKER] 后台循环已启动")
        
        while not self._stop.is_set():
            try:
                now = datetime.now()
                
                # 执行 tick（不应阻塞过久，engine 内部应使用线程执行实际任务）
                logging.debug(f"[TICKER] 执行 tick at {now.strftime('%Y-%m-%d %H:%M:%S')}")
                self.engine.tick(now)
                
            except Exception as e:
                logging.error(f"[TICKER] tick 执行失败: {e}")
                traceback.print_exc()
            
            # 细分 sleep 以便快速响应 stop
            # 例如 60 秒分成 60 次 1 秒，每次检查 stop 标志
            for i in range(self.interval):
                if self._stop.is_set():
                    break
                time.sleep(1)
        
        logging.info("[TICKER] 后台循环已退出")


__all__ = ['SchedulerTicker']

