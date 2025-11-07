# -*- coding: utf-8 -*-
"""
AI服务 - 纯业务逻辑，不依赖UI
"""
import threading
from pathlib import Path
from typing import Callable, Optional, Dict, List, Any
import logging

try:
    from core.ai_pipeline import run_ai_pipeline
    from core.reporting import export_run_html
    HAS_CORE = True
    logging.getLogger(__name__).info("[AIService] core.ai_pipeline and core.reporting loaded")
except ImportError as e:
    HAS_CORE = False
    logging.getLogger(__name__).warning(f"[AIService] core modules not found ({e}), using mock mode")
    
    # Fallback mock实现
    def run_ai_pipeline(*args, **kw):
        import time
        time.sleep(1.0)
        return {"total": 3, "done": 3, "outputs": ["mock_output_1", "mock_output_2", "mock_output_3"]}
    
    def export_run_html(*args, **kw):
        return str(Path("out") / "mock_report.html")


class AIService:
    """
    AI服务
    
    职责：
    1. 执行AI摘要处理
    2. 生成AI报告
    3. 管理AI配置
    """
    
    def __init__(self):
        self.worker: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
    
    def run_ai_processing(
        self,
        run_dir: str,
        ai_config: Dict,
        progress_callback: Callable,
        completion_callback: Callable = None
    ) -> bool:
        """
        运行AI处理流水线
        
        Args:
            run_dir: 运行目录（包含subs/目录）
            ai_config: AI配置字典
            progress_callback: 进度回调函数
            completion_callback: 完成回调函数
        
        Returns:
            是否成功启动
        """
        # 检查是否有任务在运行
        if self.worker and self.worker.is_alive():
            return False
        
        # 启动工作线程
        self.stop_event.clear()
        
        self.worker = threading.Thread(
            target=self._ai_worker,
            args=(run_dir, ai_config, progress_callback, completion_callback),
            daemon=True
        )
        self.worker.start()
        
        return True
    
    def _ai_worker(
        self,
        run_dir: str,
        ai_config: Dict,
        progress_callback: Callable,
        completion_callback: Callable
    ):
        """
        AI处理工作线程
        
        Args:
            run_dir: 运行目录
            ai_config: AI配置
            progress_callback: 进度回调
            completion_callback: 完成回调
        """
        logger = logging.getLogger(__name__)
        try:
            # 准备AI配置（转换为core.ai_pipeline期望的格式）
            # core.ai_pipeline期望的格式是包含"providers"列表的配置
            provider_name = ai_config.get("provider", "GPT")
            provider_name_lower = provider_name.lower()
            
            # 将供应商名称映射到标准的provider名称
            provider_map = {
                "gpt": "openai",
                "claude": "anthropic",
                "gemini": "gemini",
                "perplexity": "perplexity",
                "deepseek": "deepseek",
                "kimi": "moonshot",
                "qwen": "qwen",
                "glm": "glm",
                "grok": "grok",
                "自定义api": "custom",
                "本地模型": "local"
            }
            standard_provider = provider_map.get(provider_name_lower, "openai")
            
            # 如果是自定义API，直接使用用户提供的base_url和model
            if provider_name == "自定义API":
                base_url = ai_config.get("base_url", "").strip()
                if not base_url:
                    logger.error("[AIService] 自定义API必须提供base_url")
                    return
                
                # 自定义API直接使用用户输入的模型名称，不进行映射
                model_name = ai_config.get("model", "")
                actual_model = model_name if model_name else "gpt-3.5-turbo"
                logger.info(f"[AIService] Using Custom API: base_url={base_url}, model={actual_model}")
            else:
                # 非自定义API的处理逻辑
                # 对于特定供应商，强制使用正确的base_url，忽略UI传入的值
                if standard_provider == "perplexity":
                    # Perplexity必须使用 https://api.perplexity.ai（不带/v1）
                    base_url = "https://api.perplexity.ai"
                    logger.info(f"[AIService] Using Perplexity endpoint: {base_url}")
                elif standard_provider == "gemini":
                    # Gemini现在提供OpenAI兼容端点（beta）
                    # Base URL: https://generativelanguage.googleapis.com/v1beta/openai/
                    base_url = "https://generativelanguage.googleapis.com/v1beta/openai"
                    logger.info(f"[AIService] Using Gemini OpenAI-compatible endpoint: {base_url}")
                else:
                    # 其他供应商：使用UI传入的base_url，如果没有则使用默认值
                    base_url = ai_config.get("base_url", "")
                    if not base_url:
                        if standard_provider == "openai":
                            base_url = "https://api.openai.com/v1"
                        elif standard_provider == "anthropic":
                            base_url = "https://api.anthropic.com/v1"
                        elif standard_provider == "deepseek":
                            base_url = "https://api.deepseek.com/v1"
                        elif standard_provider == "moonshot":  # Kimi
                            base_url = "https://api.moonshot.cn/v1"
                        elif standard_provider == "qwen":
                            base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                        # 其他供应商使用默认的OpenAI兼容端点
                        else:
                            base_url = "https://api.openai.com/v1"
                
                # 模型名称映射（UI显示的名称 -> 实际API模型名称）
                model_map = {
                    # GPT系列
                    "gpt-5": "gpt-4o-mini",  # gpt-5还不存在，使用gpt-4o-mini
                    "gpt-5-mini": "gpt-4o-mini",
                    "gpt-5-nano": "gpt-4o-mini",
                    "gpt-4.1": "gpt-4o",
                    "gpt-4.1-mini": "gpt-4o-mini",
                    # Claude系列
                    "opus-4.1": "claude-3-5-sonnet-20241022",
                    "opus-4.0": "claude-3-opus-20240229",
                    "sonnet-4.5": "claude-3-5-sonnet-20241022",
                    "sonnet-4": "claude-3-5-sonnet-20241022",
                    "sonnet-3.7": "claude-3-sonnet-20240229",
                    # Gemini系列（使用OpenAI兼容端点时的模型名称）
                    # 注意：模型名称需要与Gemini API兼容端点匹配
                    "gemini-2.5-pro": "models/gemini-1.5-pro-latest",  # Gemini兼容端点需要 "models/" 前缀
                    "gemini-2.5-flash": "models/gemini-1.5-flash-latest",
                    # Perplexity系列
                    "sonar-pro": "sonar",
                    "sonar-reasoning": "sonar-reasoning",
                    "sonar-large": "sonar-large",
                    "sonar-medium": "sonar-medium",
                    "sonar-small": "sonar-small",
                }
                
                model_name = ai_config.get("model", "gpt-5")
                actual_model = model_map.get(model_name, model_name)
                
                # 如果模型名称仍然包含不存在的模型，使用安全的默认值
                if standard_provider == "openai" and "gpt-5" in actual_model:
                    actual_model = "gpt-4o-mini"
                    logger.warning(f"[AIService] Model {model_name} not available, using {actual_model} instead")
            
            # 构建符合core.ai_pipeline期望的配置格式
            config = {
                "enabled": ai_config.get("enabled", False),
                "providers": [
                    {
                        "name": standard_provider,
                        "enabled": True,
                        "api_key": ai_config.get("api_key", ""),
                        "base_url": base_url,
                        "model": actual_model,  # 使用映射后的实际模型名称
                        "max_tokens": 4000,
                        "temperature": 0.3
                    }
                ],
                "max_chars_per_video": ai_config.get("max_chars_per_video", 30000),
                "chunk_chars": 4000,
                "merge_strategy": "concat",
                "cache_enabled": True,
                "metrics_enabled": True,
                "max_tokens_per_run": 0,  # 0=无限制
                "max_daily_cost_usd": 0,  # 0=无限制
                "lang_pref": ai_config.get("translate_langs", ["zh", "en"]),
                "workers": ai_config.get("workers", 3),
            }
            
            logger.debug("[AIService] Config prepared:")
            logger.debug(f"  - enabled={config['enabled']}")
            logger.debug(f"  - provider={standard_provider}")
            logger.debug(f"  - model={actual_model} (mapped from {model_name})")
            logger.debug(f"  - base_url={base_url}")
            logger.debug(f"  - api_key={'*' * 10 if config['providers'][0]['api_key'] else '(empty)'}")
            logger.debug(f"  - HAS_CORE={HAS_CORE}")
            logger.debug(f"  - run_dir={run_dir}")
            
            # 调用AI流水线
            result = run_ai_pipeline(
                run_dir=run_dir,
                ai_cfg=config,
                workers=config["workers"],
                resume=True
            )
            
            logger.info(f"[AIService] run_ai_pipeline result: total={result.get('total')}, done={result.get('done')}")
            
            # 生成HTML报告
            html_path = None
            if result.get("done", 0) > 0:
                try:
                    logger.info(f"[AIService] Generating HTML report for run_dir={run_dir}")
                    html_path = export_run_html(run_dir)
                    logger.info(f"[AIService] HTML report generated: {html_path}")
                    if not html_path or "mock" in html_path.lower():
                        logger.warning("[AIService] HTML report path contains 'mock', may be using fallback")
                except Exception as e:
                    logger.error(f"[AIService] Failed to generate HTML report: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                logger.info("[AIService] No AI processing done (done=0), skipping HTML report generation")
            
            # 调用完成回调
            if completion_callback:
                completion_callback({
                    "total": result.get("total", 0),
                    "done": result.get("done", 0),
                    "html_path": html_path
                })
        except Exception as e:
            logger.error(f"[AIService] Error: {e}")
            import traceback
            traceback.print_exc()
            
            # 调用完成回调（带错误信息）
            if completion_callback:
                completion_callback({"error": str(e)})
    
    def stop(self):
        """停止AI处理"""
        self.stop_event.set()
    
    def is_running(self) -> bool:
        """是否正在运行"""
        return self.worker and self.worker.is_alive()


    def test_api_key(self, provider: str, api_key: str, base_url: str = "", model: str = "") -> Dict[str, Any]:
        """
        测试API连接
        
        Args:
            provider: 供应商名称（或"自定义API"）
            api_key: API Key
            base_url: Base URL（自定义API必需）
            model: 模型名称（自定义API必需）
        
        Returns:
            {"success": bool, "message": str, "error": str, "latency_ms": float}
        """
        try:
            import requests
            import time
            import json
            
            # 供应商名称映射
            provider_map = {
                "GPT": "openai",
                "Claude": "anthropic",
                "Gemini": "gemini",
                "Perplexity": "perplexity",
                "DeepSeek": "deepseek",
                "Kimi": "moonshot",
                "Qwen": "qwen",
                "GLM": "glm",
                "Grok": "grok",
                "自定义API": "custom"
            }
            standard_provider = provider_map.get(provider, "openai")
            
            # 确定Base URL
            if provider == "自定义API":
                if not base_url:
                    return {"success": False, "error": "Base URL不能为空"}
                api_base_url = base_url.rstrip("/")
            else:
                # 使用默认Base URL
                if standard_provider == "openai":
                    api_base_url = "https://api.openai.com/v1"
                elif standard_provider == "anthropic":
                    api_base_url = "https://api.anthropic.com/v1"
                elif standard_provider == "deepseek":
                    api_base_url = "https://api.deepseek.com/v1"
                elif standard_provider == "perplexity":
                    api_base_url = "https://api.perplexity.ai"
                elif standard_provider == "moonshot":
                    api_base_url = "https://api.moonshot.cn/v1"
                elif standard_provider == "qwen":
                    api_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
                else:
                    api_base_url = "https://api.openai.com/v1"
            
            # 确定API端点（Gemini和Perplexity需要特殊处理）
            if standard_provider == "gemini":
                # Gemini使用特殊的OpenAI兼容端点
                url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            elif standard_provider == "perplexity":
                # Perplexity的正确URL是 https://api.perplexity.ai/chat/completions（不带/v1）
                url = "https://api.perplexity.ai/chat/completions"
            elif api_base_url.endswith("/v1"):
                url = f"{api_base_url}/chat/completions"
            elif api_base_url.endswith("/v1/"):
                url = f"{api_base_url.rstrip('/')}/chat/completions"
            else:
                url = f"{api_base_url}/v1/chat/completions"
            
            # 确定模型名称（需要进行映射，与AI处理逻辑一致）
            if not model:
                model = "gpt-3.5-turbo"  # 默认模型
            else:
                # 模型名称映射（UI显示的名称 -> 实际API模型名称）
                model_map = {
                    # GPT系列
                    "gpt-5": "gpt-4o-mini",
                    "gpt-5-mini": "gpt-4o-mini",
                    "gpt-5-nano": "gpt-4o-mini",
                    "gpt-4.1": "gpt-4o",
                    "gpt-4.1-mini": "gpt-4o-mini",
                    # Claude系列
                    "opus-4.1": "claude-3-5-sonnet-20241022",
                    "opus-4.0": "claude-3-opus-20240229",
                    "sonnet-4.5": "claude-3-5-sonnet-20241022",
                    "sonnet-4": "claude-3-5-sonnet-20241022",
                    "sonnet-3.7": "claude-3-sonnet-20240229",
                    # Gemini系列
                    "gemini-2.5-pro": "models/gemini-1.5-pro-latest",
                    "gemini-2.5-flash": "models/gemini-1.5-flash-latest",
                    # Perplexity系列
                    "sonar-pro": "sonar",
                    "sonar-reasoning": "sonar-reasoning",
                    "sonar-large": "sonar-large",
                    "sonar-medium": "sonar-medium",
                    # DeepSeek系列
                    "deepseek-chat": "deepseek-chat",
                    "deepseek-reasoner": "deepseek-reasoner",
                    # Kimi系列
                    "kimi-k2-0711-preview": "moonshot-v1-128k",
                    "kimi-k2-turbo-preview": "moonshot-v1-128k",
                    # Qwen系列
                    "qwen-max": "qwen-max",
                    "qwen-plus": "qwen-plus",
                    "qwen-turbo": "qwen-turbo",
                }
                # 如果模型名称在映射表中，使用映射后的名称；否则使用原始名称
                # 如果是自定义API，不进行映射，直接使用用户输入的模型名称
                if provider != "自定义API":
                    actual_model = model_map.get(model, model)
                    model = actual_model  # 使用映射后的模型名称
            
            # 构建请求headers
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # 对于Gemini和Perplexity，使用特殊header（URL已在上面设置）
            if standard_provider == "gemini":
                headers = {
                    "X-Goog-Api-Key": api_key,
                    "Content-Type": "application/json"
                }
            elif standard_provider == "perplexity":
                # Perplexity使用标准OpenAI格式
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "python-requests/2.31.0"
                }
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": "Hello! This is a test message. Please respond with 'Test successful'."}
                ],
                "max_tokens": 20
            }
            
            # 发送测试请求
            start_time = time.perf_counter()
            response = requests.post(url, json=payload, headers=headers, timeout=15)
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                    return {
                        "success": True,
                        "message": f"连接成功，响应: {content[:50]}",
                        "latency_ms": latency_ms,
                        "provider": standard_provider  # 返回标准化的供应商名称
                    }
                except:
                    return {
                        "success": True,
                        "message": "连接成功，但无法解析响应",
                        "latency_ms": latency_ms
                    }
            else:
                error_text = response.text[:500]
                try:
                    error_json = response.json()
                    error_msg = error_json.get("error", {}).get("message", error_text)
                except:
                    error_msg = error_text
                
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {error_msg}",
                    "latency_ms": latency_ms
                }
                
        except requests.exceptions.Timeout:
            return {
                "success": False,
                "error": "连接超时（超过15秒）"
            }
        except requests.exceptions.ConnectionError as e:
            return {
                "success": False,
                "error": f"连接错误: {str(e)}"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"测试失败: {str(e)}"
            }

__all__ = ['AIService']

