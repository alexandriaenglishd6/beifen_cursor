# -*- coding: utf-8 -*-
"""
下载服务 - 纯业务逻辑，不依赖UI
"""
import threading
from pathlib import Path
from typing import Callable, Optional, Dict, List

try:
    from core_bridge import run_full_process, retry_failed_items
    HAS_CORE = True
    print("[DownloadService] SUCCESS - core_bridge loaded")
except ImportError:
    HAS_CORE = False
    print("[DownloadService] WARNING - core_bridge not found, using mock mode")
    
    # Fallback mock实现
    def run_full_process(**kw):
        import time
        print(f"[Mock] 开始mock下载，参数: do_download={kw.get('do_download')}")
        
        for i in range(1, 4):
            time.sleep(0.5)
            cb = kw.get("progress_callback")
            if cb: 
                cb({"phase":"detect","current":i,"total":3,"message":f"检测视频 {i}/3 (Mock模式)"})
        
        if kw.get("do_download", True):
            for i in range(1, 4):
                time.sleep(0.5)
                cb = kw.get("progress_callback")
                if cb: 
                    cb({"phase":"download","current":i,"total":3,"message":f"下载字幕 {i}/3 (Mock模式)"})
        
        result = {"run_dir": str(Path.cwd() / "out/mock_run")}
        print(f"[Mock] 下载完成，结果: {result}")
        return result
    
    def retry_failed_items(**kw):
        import time
        cb = kw.get("progress_callback")
        if cb:
            for i in range(1, 4):
                time.sleep(0.3)
                cb({"phase":"retry","current":i,"total":3,"message":f"重试 {i}/3 (Mock模式)"})
        return {"retried": 3, "recovered": 2, "run_dir": kw.get("run_dir"), "new_errors": 1}


class DownloadService:
    """
    下载服务
    
    职责：
    1. 执行下载任务（检测/完整下载）
    2. 重试失败项
    3. 管理下载状态
    """
    
    def __init__(self):
        self.worker: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.run_dir: Optional[str] = None
    
    def start_download(
        self,
        urls: List[str],
        config: Dict,
        progress_callback: Callable,
        completion_callback: Callable = None,
        dry_run: bool = False
    ) -> bool:
        """
        开始下载
        
        Args:
            urls: URL列表
            config: 配置字典
            progress_callback: 进度回调函数
            completion_callback: 完成回调函数
            dry_run: 是否为干运行（只检测）
        
        Returns:
            是否成功启动
        """
        # 检查是否有任务在运行
        if self.worker and self.worker.is_alive():
            return False
        
        # 准备参数
        args = self._prepare_args(urls, config, progress_callback, dry_run)
        
        # 启动工作线程
        self.stop_event.clear()
        self.pause_event.clear()
        
        self.worker = threading.Thread(
            target=self._download_worker,
            args=(args, completion_callback),
            daemon=True
        )
        self.worker.start()
        
        return True
    
    def _prepare_args(
        self,
        urls: List[str],
        config: Dict,
        progress_callback: Callable,
        dry_run: bool
    ) -> Dict:
        """
        准备下载参数
        
        Args:
            urls: URL列表
            config: 配置
            progress_callback: 进度回调
            dry_run: 是否干运行
        
        Returns:
            参数字典
        """
        # 确保输出目录存在
        output_root = Path(config.get("output_root", "out"))
        output_root.mkdir(parents=True, exist_ok=True)
        
        # 网络配置参数
        proxy_text = config.get("proxy_text", "")
        cookiefile = config.get("cookiefile", "")
        user_agent = config.get("user_agent", "")
        
        # 规范化 Cookie 文件路径（相对路径转绝对路径）
        if cookiefile:
            cookie_path = Path(cookiefile)
            if not cookie_path.is_absolute():
                # 相对路径，转换为绝对路径（相对于当前工作目录）
                cookie_path = Path.cwd() / cookie_path
                cookiefile = str(cookie_path)
                print(f"[DownloadService] Cookie路径已规范化: {cookiefile}")
        
        # 验证 Cookie 文件路径
        if cookiefile:
            cookie_path = Path(cookiefile)
            if cookie_path.exists():
                print(f"[DownloadService] ✓ Cookie文件存在: {cookiefile}")
                # 检查文件内容（至少应该有一些内容）
                try:
                    content = cookie_path.read_text(encoding='utf-8', errors='ignore')
                    if content.strip():
                        # 检查是否是 Netscape 格式（以 # 开头或包含域名）
                        if content.strip().startswith('#') or '.youtube.com' in content or 'youtube.com' in content:
                            print(f"[DownloadService] ✓ Cookie文件格式看起来正确（长度: {len(content)} 字符）")
                        else:
                            print(f"[DownloadService] ⚠️ Cookie文件内容可能不是标准格式")
                    else:
                        print(f"[DownloadService] ⚠️ Cookie文件为空")
                except Exception as e:
                    print(f"[DownloadService] ⚠️ 读取Cookie文件失败: {e}")
            else:
                print(f"[DownloadService] ⚠️ Cookie文件不存在: {cookiefile}")
                print(f"[DownloadService] ⚠️ 当前工作目录: {Path.cwd()}")
                print(f"[DownloadService] ⚠️ Cookie文件绝对路径: {cookie_path.absolute()}")
        else:
            print(f"[DownloadService] ⚠️ Cookie文件路径为空")
        
        # 注意：不需要创建适配器，因为 core_bridge.py 已经完成了格式适配
        # core_bridge 会将 core 的 3 参数格式转换为 dict 格式
        # 所以 progress_callback 应该直接接收 dict 格式
        
        args = {
            "urls_override": urls,
            "output_root": str(output_root),
            "download_langs": config.get("download_langs", ["zh", "en"]),  # 要下载的语言
            "preferred_langs": config.get("download_langs", ["zh", "en"]),  # 优先匹配的语言（与download_langs相同）
            "max_workers": config.get("max_workers", 3),
            "do_download": not dry_run,  # 干运行时不下载
            "dry_run": dry_run,  # 同时传递 dry_run 参数
            "download_fmt": config.get("download_fmt", "srt"),
            "download_prefer": config.get("download_prefer", "both"),  # manual/auto/both
            "translate_config": config.get("translate", {}),
            # 高级选项：从UI配置获取（默认值保持向后兼容）
            "merge_bilingual": config.get("merge_bilingual", True),  # 双语合并（默认启用）
            "force_refresh": config.get("force_refresh", False),  # 强制刷新（默认关闭）
            "incremental_detect": config.get("incremental_detect", True),  # 增量检测（默认启用）
            "incremental_download": config.get("incremental_download", True),  # 增量下载（默认启用）
            "early_stop_on_seen": config.get("early_stop_on_seen", True),  # 提前停止（默认启用）
            "channel_or_playlist_url": "",  # 空字符串，强制不使用频道索引
            # 网络配置参数
            "proxy_text": proxy_text,
            "cookiefile": cookiefile,
            "user_agent": user_agent,
            "progress_callback": progress_callback,  # 直接传递，core_bridge 已适配
            "stop_event": self.stop_event,
            "pause_event": self.pause_event,
            # 字幕优化配置
            "postprocess_config": config.get("postprocess", {}),
            "quality_config": config.get("quality", {}),
            # 字幕翻译配置
            "translate_config": config.get("translate", {})
        }
        
        print(f"[DownloadService] 准备参数:")
        print(f"  - urls数量: {len(urls)}")
        print(f"  - output_root: {output_root}")
        print(f"  - download_langs: {args['download_langs']}")
        print(f"  - preferred_langs: {args['preferred_langs']}")
        print(f"  - do_download: {args['do_download']}")
        print(f"  - dry_run: {args['dry_run']}")
        print(f"  - download_fmt: {args['download_fmt']}")
        print(f"  - cookiefile完整路径: {cookiefile}")
        print(f"  - cookiefile长度: {len(cookiefile)}")
        print(f"  - proxy_text: {'已设置' if proxy_text else '(空)'}")
        print(f"  - user_agent: {'已设置' if user_agent else '(空)'}")
        
        return args
    
    def _download_worker(self, args: Dict, completion_callback: Callable = None):
        """
        下载工作线程
        
        Args:
            args: 参数字典
            completion_callback: 完成回调函数
        """
        print(f"[DownloadService] _download_worker 开始执行, completion_callback={completion_callback is not None}")
        try:
            import sys
            sys.stdout.reconfigure(encoding='utf-8')
            print("\n" + "="*60)
            print("[DownloadService] Starting download with configuration:")
            print(f"  URLs: {args.get('urls_override', [])[:1]}...")  # 只显示第一个
            print(f"  do_download: {args.get('do_download')}")
            print(f"  download_langs: {args.get('download_langs')}")
            print(f"  download_fmt: {args.get('download_fmt')}")
            print(f"  force_refresh: {args.get('force_refresh')}")
            print(f"  incremental_download: {args.get('incremental_download')}")
            print(f"  incremental_detect: {args.get('incremental_detect')}")
            print(f"  early_stop_on_seen: {args.get('early_stop_on_seen')}")
            # 网络配置
            print(f"  proxy_text: {'已设置' if args.get('proxy_text') else '(未设置)'}")
            cookiefile_path = args.get('cookiefile', '')
            if cookiefile_path:
                from pathlib import Path
                cookie_file = Path(cookiefile_path)
                print(f"  cookiefile完整路径: {cookiefile_path}")
                print(f"  cookiefile长度: {len(cookiefile_path)}")
                if cookie_file.exists():
                    print(f"  cookiefile状态: (文件存在)")
                else:
                    print(f"  cookiefile状态: (⚠️ 文件不存在)")
            else:
                print(f"  cookiefile: (未设置)")
            print(f"  user_agent: {'已设置' if args.get('user_agent') else '(未设置)'}")
            print("="*60 + "\n")
            
            print(f"[DownloadService] 准备调用 run_full_process...")
            import sys
            sys.stdout.flush()
            result = run_full_process(**args)
            sys.stdout.flush()
            print(f"[DownloadService] run_full_process 返回: run_dir={result.get('run_dir')}, total={result.get('total', 0)}, downloaded={result.get('downloaded', 0)}, errors={result.get('errors', 0)}, failed={result.get('failed', 0)}")
            sys.stdout.flush()
            self.run_dir = result.get("run_dir")
            
            print("\n" + "="*60)
            print("[DownloadService] Download result:")
            print(f"  run_dir: {self.run_dir}")
            print(f"  total: {result.get('total', 0)}")
            print(f"  downloaded: {result.get('downloaded', 0)}")
            print(f"  skipped: {result.get('skipped', 0)}")
            print(f"  failed: {result.get('failed', 0)}")
            print(f"  errors: {result.get('errors', 0)}")
            print("="*60 + "\n")
            sys.stdout.flush()
            
            # 如果 run_dir 存在，列出其中的文件
            if self.run_dir:
                from pathlib import Path
                run_path = Path(self.run_dir)
                if run_path.exists():
                    files = list(run_path.glob("*"))
                    print(f"[DownloadService] run_dir 中的文件 ({len(files)} 个):")
                    for f in files[:10]:  # 只显示前10个
                        print(f"  - {f.name} ({'目录' if f.is_dir() else '文件'})")
                    if len(files) > 10:
                        print(f"  ... 还有 {len(files) - 10} 个文件/目录")
                else:
                    print(f"[DownloadService] ⚠️ run_dir 不存在: {self.run_dir}")
            
            # 调用完成回调
            if completion_callback:
                print(f"[DownloadService] 调用完成回调: total={result.get('total', 0)}, downloaded={result.get('downloaded', 0)}, errors={result.get('errors', 0)}, failed={result.get('failed', 0)}")
                sys.stdout.flush()
                try:
                    completion_callback(result)
                    print(f"[DownloadService] 完成回调执行成功")
                    sys.stdout.flush()
                except Exception as e:
                    print(f"[DownloadService] 完成回调执行失败: {e}")
                    import traceback
                    traceback.print_exc()
                    sys.stdout.flush()
            else:
                print(f"[DownloadService] ⚠️ completion_callback 为 None，无法调用")
                sys.stdout.flush()
        except Exception as e:
            print(f"[DownloadService] Error: {e}")
            import traceback
            traceback.print_exc()
            
            # 调用完成回调（带错误信息）
            if completion_callback:
                print(f"[DownloadService] 调用完成回调（异常）: error={str(e)[:100]}")
                try:
                    completion_callback({"error": str(e)})
                    print(f"[DownloadService] 完成回调（异常）执行成功")
                except Exception as e2:
                    print(f"[DownloadService] 完成回调（异常）执行失败: {e2}")
                    import traceback
                    traceback.print_exc()
    
    def retry_failed(
        self,
        run_dir: str,
        progress_callback: Callable
    ) -> bool:
        """
        重试失败项
        
        Args:
            run_dir: 运行目录
            progress_callback: 进度回调
        
        Returns:
            是否成功启动
        """
        if self.worker and self.worker.is_alive():
            return False
        
        args = {
            "run_dir": run_dir,
            "progress_callback": progress_callback,
            "stop_event": self.stop_event,
            "pause_event": self.pause_event
        }
        
        self.stop_event.clear()
        self.pause_event.clear()
        
        self.worker = threading.Thread(
            target=lambda: retry_failed_items(**args),
            daemon=True
        )
        self.worker.start()
        
        return True
    
    def stop(self):
        """停止下载"""
        self.stop_event.set()
    
    def pause(self):
        """暂停下载"""
        self.pause_event.set()
    
    def resume(self):
        """恢复下载"""
        self.pause_event.clear()
    
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.worker and self.worker.is_alive()


__all__ = ['DownloadService']

