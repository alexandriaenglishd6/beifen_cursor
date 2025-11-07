# -*- coding: utf-8 -*-
"""
ai_adapter.py — v4.0-alpha adapter layer
支持（统一接口 + 失败自动回退）：
- OpenAI 兼容协议（/v1/chat/completions）：OpenAI / DeepSeek / Moonshot(Kimi) / Perplexity / Grok(xAI) / GLM(智谱) / 以及任意兼容服务
- 轻量本地兜底：关键词提取（频次+停用词）、简易章节点（按空行/长度切段）
"""
from __future__ import annotations
import os, time, json, logging, re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
try:
    import requests
except Exception:
    requests = None

def _resolve_env(v: str) -> str:
    if not v:
        return ""
    if isinstance(v, str) and v.startswith("env:"):
        return os.getenv(v.split(":", 1)[1], "")
    return v

def _truncate(text: str, max_chars: int) -> str:
    if max_chars and len(text) > max_chars:
        return text[:max_chars]
    return text

def _clean_special_chars(text: str) -> str:
    """
    清理可能导致API拒绝的特殊字符
    
    Perplexity API对某些特殊字符（如♪）可能拒绝连接
    清理这些字符以避免RemoteDisconnected错误
    
    使用保守策略：只移除已知有问题的字符，保留其他Unicode字符
    """
    if not text:
        return text
    
    cleaned = text
    # 移除已知会导致Perplexity API拒绝的音乐符号
    # 使用保守策略：只移除特定字符，保留其他内容
    cleaned = cleaned.replace('♪', '')
    cleaned = cleaned.replace('♫', '')
    cleaned = cleaned.replace('♩', '')
    cleaned = cleaned.replace('♬', '')
    # 移除连续的多个音乐符号
    cleaned = cleaned.replace('♪♪♪', '[music]')
    cleaned = cleaned.replace('♪♪', '[music]')
    
    return cleaned

@dataclass
class OpenAICompatProvider:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: int = 30
    headers: Dict[str, str] = field(default_factory=dict)
    path: str = "/v1/chat/completions"
    api_key_header: str = "Authorization"
    retry_count: int = 2  # 内建重试次数
    
    def _is_retryable_error(self, status_code: int, error_text: str) -> bool:
        """判断是否为可重试错误"""
        if status_code in (429, 503):
            return True
        error_lower = error_text.lower()
        if "timeout" in error_lower or "timed out" in error_lower:
            return True
        return False
    
    def _post(self, payload: Dict[str, Any]) -> tuple[Dict[str, Any], float]:
        """
        发送请求（带内建重试 + 延迟记录）
        
        返回：(响应, 延迟毫秒)
        """
        if requests is None:
            raise RuntimeError("requests not available")
        
        # 处理特殊供应商的URL和Header格式
        # Perplexity的正确URL是 https://api.perplexity.ai/chat/completions（不带/v1）
        # 测试脚本已验证此URL正确
        if self.name == "perplexity":
            # Perplexity: 强制使用正确的URL，忽略base_url的值
            url = "https://api.perplexity.ai/chat/completions"
        elif self.base_url.endswith("/v1") and self.path.startswith("/v1"):
            # 其他供应商：如果base_url已经包含/v1，path也以/v1开头，则去掉path的/v1
            url = self.base_url.rstrip("/") + self.path[3:]  # 去掉path开头的/v1
        else:
            url = self.base_url.rstrip("/") + self.path
        headers = dict(self.headers)
        
        # 调试：输出实际请求的URL（仅用于调试）
        import sys
        if self.name == "perplexity":
            print(f"[DEBUG] Perplexity URL: {url}", file=sys.stderr)
        
        if self.name == "gemini":
            # Gemini的OpenAI兼容端点使用X-Goog-Api-Key header（不需要Bearer前缀）
            headers["X-Goog-Api-Key"] = self.api_key
            headers.setdefault("Content-Type", "application/json")
        elif self.name == "perplexity":
            # Perplexity使用标准OpenAI格式
            headers["Authorization"] = f"Bearer {self.api_key}"
            headers.setdefault("Content-Type", "application/json")
            # 添加User-Agent（某些API要求）
            headers.setdefault("User-Agent", "python-requests/2.31.0")
        else:
            # 标准OpenAI兼容格式
            if self.api_key_header.lower() == "authorization":
                headers["Authorization"] = f"Bearer {self.api_key}"
            else:
                # 使用指定的header名称（如X-Goog-Api-Key），不添加Bearer前缀
                headers[self.api_key_header] = self.api_key
            headers.setdefault("Content-Type", "application/json")
        
        last_error = None
        for attempt in range(self.retry_count + 1):
            try:
                t0 = time.perf_counter()
                # 输出详细的请求信息用于调试
                import sys
                if self.name == "perplexity":
                    print(f"\n{'='*80}", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Attempt {attempt + 1}/{self.retry_count + 1}", file=sys.stderr)
                    print(f"{'='*80}", file=sys.stderr)
                    
                    # URL信息
                    print(f"[DEBUG {self.name}] Request URL: {url}", file=sys.stderr)
                    
                    # Headers信息（详细）
                    print(f"[DEBUG {self.name}] Request Headers:", file=sys.stderr)
                    for k, v in headers.items():
                        if k == 'Authorization':
                            # 显示Bearer和API Key的前20个字符
                            masked_key = v[:20] + '...' + v[-10:] if len(v) > 30 else v
                            print(f"  {k}: {masked_key}", file=sys.stderr)
                        else:
                            print(f"  {k}: {v}", file=sys.stderr)
                    
                    # Payload基本信息
                    print(f"[DEBUG {self.name}] Payload Info:", file=sys.stderr)
                    print(f"  Model: {payload.get('model')}", file=sys.stderr)
                    print(f"  Messages Count: {len(payload.get('messages', []))}", file=sys.stderr)
                    print(f"  Stream: {payload.get('stream', 'not set')}", file=sys.stderr)
                    print(f"  Temperature: {payload.get('temperature', 'not set')}", file=sys.stderr)
                    print(f"  Max Tokens: {payload.get('max_tokens', 'not set')}", file=sys.stderr)
                    
                    # Payload完整内容（JSON格式，用于对比）
                    payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
                    payload_bytes = payload_str.encode('utf-8')
                    print(f"[DEBUG {self.name}] Payload Size: {len(payload_bytes)} bytes", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Payload (first 1000 chars):", file=sys.stderr)
                    print(payload_str[:1000], file=sys.stderr)
                    if len(payload_str) > 1000:
                        print(f"[DEBUG {self.name}] ... (truncated, total {len(payload_str)} chars)", file=sys.stderr)
                    
                    # 检查特殊字符是否被清理
                    if self.name == "perplexity":
                        content = payload.get("messages", [{}])[0].get("content", "")
                        has_music_chars = '♪' in content or '♫' in content or '♩' in content
                        if has_music_chars:
                            print(f"[DEBUG {self.name}] ⚠️ WARNING: Content still contains music symbols after cleaning!", file=sys.stderr)
                        else:
                            print(f"[DEBUG {self.name}] ✅ Special characters cleaned successfully", file=sys.stderr)
                    
                    # Messages详细内容
                    print(f"[DEBUG {self.name}] Messages Details:", file=sys.stderr)
                    for i, msg in enumerate(payload.get('messages', [])):
                        role = msg.get('role', 'unknown')
                        content = msg.get('content', '')
                        content_preview = content[:200] + '...' if len(content) > 200 else content
                        print(f"  Message {i+1} (role={role}, length={len(content)}): {content_preview}", file=sys.stderr)
                    
                    # 网络配置（先计算timeout再打印）
                    # Perplexity可能需要更长的超时时间
                    timeout = self.timeout * 2 if self.name == "perplexity" else self.timeout
                    
                    print(f"[DEBUG {self.name}] Network Config:", file=sys.stderr)
                    print(f"  Timeout: {timeout}s", file=sys.stderr)
                    print(f"  Retry Count: {self.retry_count}", file=sys.stderr)
                    
                    print(f"[DEBUG {self.name}] Sending request...", file=sys.stderr)
                else:
                    # 非Perplexity的情况，也计算timeout
                    timeout = self.timeout * 2 if self.name == "perplexity" else self.timeout
                
                # 对于Perplexity，确保使用stream=False以避免连接问题
                if self.name == "perplexity" and "stream" not in payload:
                    payload["stream"] = False
                
                # 输出payload大小用于调试
                import sys
                if self.name == "perplexity":
                    payload_str = json.dumps(payload, ensure_ascii=False)
                    payload_size = len(payload_str.encode('utf-8'))
                    print(f"[DEBUG {self.name}] Payload size: {payload_size} bytes", file=sys.stderr)
                    if payload_size > 100000:  # 100KB
                        print(f"[DEBUG {self.name}] WARNING: Payload is large ({payload_size} bytes), may cause connection issues", file=sys.stderr)
                    
                    # Perplexity特殊处理：直接使用requests.post（与测试脚本完全一致）
                    # 测试脚本使用requests.post()而不是Session，这可能是关键差异
                    perp_headers = dict(headers)
                    perp_headers["Connection"] = "close"
                    print(f"[DEBUG {self.name}] Connection header: {perp_headers.get('Connection')}", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Using direct requests.post() (matching test script)", file=sys.stderr)
                    
                    # 记录请求发送前的精确时间
                    request_start_time = time.perf_counter()
                    print(f"[DEBUG {self.name}] Request start timestamp: {request_start_time:.6f}", file=sys.stderr)
                    
                    try:
                        # 直接使用requests.post，不使用Session（与测试脚本完全一致）
                        r = requests.post(url, json=payload, headers=perp_headers, timeout=timeout)
                        request_end_time = time.perf_counter()
                        request_duration = request_end_time - request_start_time
                        print(f"[DEBUG {self.name}] Request completed in {request_duration:.3f}s", file=sys.stderr)
                        print(f"[DEBUG {self.name}] Request end timestamp: {request_end_time:.6f}", file=sys.stderr)
                    except Exception as req_e:
                        request_error_time = time.perf_counter()
                        request_duration = request_error_time - request_start_time
                        print(f"[DEBUG {self.name}] Request failed after {request_duration:.3f}s", file=sys.stderr)
                        print(f"[DEBUG {self.name}] Request error timestamp: {request_error_time:.6f}", file=sys.stderr)
                        print(f"[DEBUG {self.name}] Exception during requests.post(): {type(req_e).__name__}: {req_e}", file=sys.stderr)
                        if hasattr(req_e, '__cause__') and req_e.__cause__:
                            print(f"[DEBUG {self.name}] Caused by: {type(req_e.__cause__).__name__}: {req_e.__cause__}", file=sys.stderr)
                        raise
                else:
                    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                
                # 详细响应信息（针对Perplexity）
                if self.name == "perplexity":
                    import sys
                    print(f"[DEBUG {self.name}] Response Details:", file=sys.stderr)
                    print(f"  Status Code: {r.status_code}", file=sys.stderr)
                    print(f"  Latency: {latency_ms:.2f}ms", file=sys.stderr)
                    print(f"  Response Headers:", file=sys.stderr)
                    for k, v in r.headers.items():
                        print(f"    {k}: {v}", file=sys.stderr)
                    print(f"  Response Size: {len(r.content)} bytes", file=sys.stderr)
                    print(f"  Response Encoding: {r.encoding}", file=sys.stderr)
                
                if r.status_code // 100 == 2:
                    if self.name == "perplexity":
                        import sys
                        try:
                            resp_json = r.json()
                            print(f"[DEBUG {self.name}] Response JSON Keys: {list(resp_json.keys())}", file=sys.stderr)
                            if 'choices' in resp_json:
                                print(f"[DEBUG {self.name}] Choices Count: {len(resp_json.get('choices', []))}", file=sys.stderr)
                                if resp_json.get('choices'):
                                    choice = resp_json['choices'][0]
                                    print(f"[DEBUG {self.name}] First Choice Keys: {list(choice.keys())}", file=sys.stderr)
                            if 'usage' in resp_json:
                                print(f"[DEBUG {self.name}] Usage: {resp_json['usage']}", file=sys.stderr)
                        except Exception as json_err:
                            print(f"[DEBUG {self.name}] Failed to parse response as JSON: {json_err}", file=sys.stderr)
                    
                    try:
                        return r.json(), latency_ms
                    except Exception as json_err:
                        import sys
                        print(f"[DEBUG {self.name}] Failed to parse success response as JSON: {json_err}", file=sys.stderr)
                        print(f"[DEBUG {self.name}] Response text (first 500 chars): {r.text[:500]}", file=sys.stderr)
                        raise RuntimeError(f"{self.name} invalid json: {json_err}")
                else:
                    error_text = r.text[:1000]  # 增加错误文本长度
                    # 输出详细的错误信息用于调试
                    import sys
                    print(f"[DEBUG {self.name}] HTTP {r.status_code} Error:", file=sys.stderr)
                    print(f"[DEBUG {self.name}] URL: {url}", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Response Headers: {dict(r.headers)}", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Response Size: {len(r.content)} bytes", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Response Text (first 1000 chars): {error_text}", file=sys.stderr)
                    if len(r.text) > 1000:
                        print(f"[DEBUG {self.name}] ... (truncated, total {len(r.text)} chars)", file=sys.stderr)
                    try:
                        error_json = r.json()
                        print(f"[DEBUG {self.name}] Error JSON: {json.dumps(error_json, indent=2, ensure_ascii=False)}", file=sys.stderr)
                    except Exception as json_err:
                        print(f"[DEBUG {self.name}] Failed to parse error as JSON: {json_err}", file=sys.stderr)
                    
                    last_error = RuntimeError(f"{self.name} http {r.status_code}: {error_text}")
                    
                    # 判断是否重试
                    if attempt < self.retry_count and self._is_retryable_error(r.status_code, error_text):
                        # 指数退避：200ms, 600ms
                        backoff = 0.2 * (3 ** attempt)
                        logging.debug(f"[{self.name}] Retrying after {backoff:.1f}s (attempt {attempt+1})")
                        time.sleep(backoff)
                        continue
                    else:
                        raise last_error
                        
            except requests.Timeout:
                last_error = RuntimeError(f"{self.name} timeout after {self.timeout}s")
                if attempt < self.retry_count:
                    backoff = 0.2 * (2.5 ** attempt)
                    logging.debug(f"[{self.name}] Timeout, retrying after {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                else:
                    raise last_error
            except (requests.exceptions.ConnectionError,
                    requests.exceptions.ChunkedEncodingError) as e:
                # 连接相关错误，应该重试（特别是RemoteDisconnected）
                error_msg = str(e)
                error_type = type(e).__name__
                last_error = RuntimeError(f"{self.name} connection error ({error_type}): {error_msg}")
                import sys
                print(f"[DEBUG {self.name}] Connection Error Details (attempt {attempt+1}/{self.retry_count+1}):", file=sys.stderr)
                print(f"  Exception Type: {error_type}", file=sys.stderr)
                print(f"  Exception Class: {type(e).__module__}.{type(e).__name__}", file=sys.stderr)
                print(f"  Error Message: {error_msg}", file=sys.stderr)
                
                # 对于 Perplexity 的 RemoteDisconnected 错误，提供更详细的说明
                if self.name == "perplexity" and "RemoteDisconnected" in error_msg:
                    print(f"[DEBUG {self.name}] NOTE: Perplexity API may reject requests with certain content.", file=sys.stderr)
                    print(f"[DEBUG {self.name}] This could be due to content filtering or API limits.", file=sys.stderr)
                    print(f"[DEBUG {self.name}] Consider trying a different provider or reducing payload size.", file=sys.stderr)
                print(f"  Exception Args: {e.args}", file=sys.stderr)
                if hasattr(e, '__cause__') and e.__cause__:
                    print(f"  Caused by: {type(e.__cause__).__name__}: {e.__cause__}", file=sys.stderr)
                if hasattr(e, 'request') and e.request:
                    print(f"  Request URL: {e.request.url}", file=sys.stderr)
                    print(f"  Request Method: {e.request.method}", file=sys.stderr)
                if hasattr(e, 'response') and e.response:
                    print(f"  Response Status: {e.response.status_code if e.response else 'N/A'}", file=sys.stderr)
                print(f"[DEBUG {self.name}] Request Config at time of error:", file=sys.stderr)
                print(f"  URL: {url}", file=sys.stderr)
                print(f"  Timeout: {timeout}s", file=sys.stderr)
                print(f"  Payload Size: {len(json.dumps(payload, ensure_ascii=False).encode('utf-8'))} bytes", file=sys.stderr)
                if attempt < self.retry_count:
                    backoff = 0.5 * (2 ** attempt)  # 更长退避：0.5s, 1s
                    print(f"[DEBUG {self.name}] Retrying after {backoff:.1f}s...", file=sys.stderr)
                    logging.debug(f"[{self.name}] Connection error, retrying after {backoff:.1f}s")
                    time.sleep(backoff)
                    continue
                else:
                    print(f"[DEBUG {self.name}] All retries exhausted, raising error", file=sys.stderr)
                    raise last_error
            except Exception as e:
                # 其他异常
                error_type = type(e).__name__
                last_error = RuntimeError(f"{self.name} request failed ({error_type}): {str(e)}")
                import sys
                import traceback
                print(f"[DEBUG {self.name}] Unexpected Error (attempt {attempt+1}/{self.retry_count+1}):", file=sys.stderr)
                print(f"  Exception Type: {error_type}", file=sys.stderr)
                print(f"  Exception Class: {type(e).__module__}.{type(e).__name__}", file=sys.stderr)
                print(f"  Error Message: {str(e)}", file=sys.stderr)
                print(f"  Exception Args: {e.args}", file=sys.stderr)
                print(f"  Traceback:", file=sys.stderr)
                traceback.print_exc(file=sys.stderr)
                if attempt >= self.retry_count:
                    print(f"[DEBUG {self.name}] All retries exhausted, raising error", file=sys.stderr)
                    raise last_error
                # 否则继续重试
                backoff = 0.2 * (2.5 ** attempt)
                print(f"[DEBUG {self.name}] Retrying after {backoff:.1f}s...", file=sys.stderr)
                logging.debug(f"[{self.name}] Exception, retrying after {backoff:.1f}s")
                time.sleep(backoff)
                continue
        
        raise last_error or RuntimeError(f"{self.name} failed after {self.retry_count} retries")
    @staticmethod
    def _extract_content(resp: Dict[str, Any]) -> str:
        try:
            return resp["choices"][0]["message"]["content"]
        except Exception:
            try:
                return resp["choices"][0].get("content","")
            except Exception:
                return ""
    def chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: Optional[int]=None) -> tuple[str, Dict[str, Any]]:
        """
        聊天接口（统一 meta）
        
        返回：(content, meta)
        meta 包含：provider, model, tokens, cost_usd, latency_ms, error_type?
        """
        # Perplexity特殊处理：不支持system role，将system prompt合并到user prompt
        # 测试脚本验证：Perplexity只使用user role可以成功
        if self.name == "perplexity":
            # Perplexity不支持system role，需要将system prompt合并到user message
            combined_prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
            # 清理可能导致API拒绝的特殊字符（如♪等）
            combined_prompt = _clean_special_chars(combined_prompt)
            messages = [
                {"role": "user", "content": combined_prompt}
            ]
        else:
            messages = [
                {"role":"system","content":system_prompt},
                {"role":"user","content":user_prompt}
            ]
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature)
        }
        if max_tokens is not None:
            payload["max_tokens"] = int(max_tokens)
        
        # Perplexity特殊处理：添加stream=false（某些API默认stream可能导致连接问题）
        if self.name == "perplexity":
            payload["stream"] = False
        
        resp, latency_ms = self._post(payload)
        content = self._extract_content(resp)
        
        # 提取 tokens 信息
        usage = resp.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        
        meta = {
            "provider": self.name,
            "model": self.model,
            "tokens": tokens,
            "cost_usd": 0.0,  # 可根据 model 估算
            "latency_ms": round(latency_ms, 2)
        }
        
        return content, meta

_STOPWORDS = set("""a an the and or to of in on for with as is are was were be been being by from at this that it its it's
我 我们 你 你们 他 他们 她 她们 它 它们 的 了 和 是 在 与 及 或 而 被 也 有 没有 并 对 用 把 上 下 中 就 很
""".split())

def _simple_keywords(text: str, top_k: int = 12) -> List[str]:
    tokens = re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", text)
    freq = {}
    for t in tokens:
        t = t.lower()
        if t in _STOPWORDS:
            continue
        freq[t] = freq.get(t, 0) + 1
    return [w for w,_ in sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:max(1, top_k)]]

def _simple_chapters(text: str, target_segments: int = 6) -> List[Dict[str, Any]]:
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paras:
        paras = [text]
    n = max(1, min(target_segments, len(paras)))
    seg_len = max(1, len(paras)//n)
    chapters = []
    idx = 0
    for i in range(n):
        chunk = paras[idx: idx+seg_len]
        idx += seg_len
        title = chunk[0][:28] if chunk else f"Segment {i+1}"
        chapters.append({"start":"00:00:00","title": title, "key_points": _simple_keywords(' '.join(chunk), 5)})
    return chapters

@dataclass
class AIClient:
    providers: List[OpenAICompatProvider]
    timeout: int = 30
    retry: int = 2
    max_chars_per_video: int = 30000
    chunk_chars: int = 4000
    merge_strategy: str = "map_reduce"
    @staticmethod
    def from_config(cfg: Dict[str, Any]) -> "AIClient":
        provs = []
        for p in cfg.get("providers", []):
            name = (p.get("name") or "openai").lower()
            base_url = _resolve_env(p.get("base_url") or "https://api.openai.com")
            api_key = _resolve_env(p.get("api_key") or "")
            model = p.get("model") or "gpt-4o-mini"
            path = p.get("path") or "/v1/chat/completions"
            # Gemini特殊处理：使用X-Goog-Api-Key header
            if name == "gemini":
                api_key_header = "X-Goog-Api-Key"
            elif name == "custom":
                # 自定义API：使用Authorization header，path从base_url推断
                api_key_header = "Authorization"
                # 如果base_url已经包含/v1，path使用空字符串；否则使用/v1/chat/completions
                if "/v1" in base_url:
                    path = "/chat/completions"
                else:
                    path = "/v1/chat/completions"
            else:
                api_key_header = p.get("api_key_header") or "Authorization"
            
            timeout = int(p.get("timeout") or cfg.get("timeout") or 30)
            headers = p.get("headers") or {}
            provs.append(OpenAICompatProvider(
                name=name, base_url=base_url, api_key=api_key, model=model,
                timeout=timeout, headers=headers, path=path, api_key_header=api_key_header
            ))
        return AIClient(providers=provs,
                        timeout=int(cfg.get("timeout") or 30),
                        retry=int(cfg.get("retry") or 2),
                        max_chars_per_video=int(cfg.get("max_chars_per_video") or 30000),
                        chunk_chars=int(cfg.get("chunk_chars") or 4000),
                        merge_strategy=str(cfg.get("merge_strategy") or "map_reduce"))
    def summarize(self, text: str, lang: str="auto", max_tokens: int=800) -> Dict[str, Any]:
        """
        摘要接口（统一 meta + 内建重试）
        
        返回：{summary, key_points, keywords, meta:{provider, model, tokens, cost_usd, latency_ms}}
        """
        text = _truncate(text or "", self.max_chars_per_video)
        sys = "You are a helpful assistant for video transcript summarization."
        user = f"""Language: {lang}
Task: Read the transcript and produce:
1) A concise paragraph summary (500-800 chars in the target language).
2) 5-10 bullet key points.
3) 10 keywords (comma separated).
Return in strict JSON with keys: summary, key_points, keywords.
Transcript:
{text}
"""
        for attempt in range(self.retry + 1):
            for prov in self.providers:
                try:
                    raw, meta = prov.chat(sys, user, temperature=0.2, max_tokens=max_tokens)
                    j = self._safe_json(raw) or self._extract_json_block(raw)
                    if not j:
                        raise RuntimeError("no-json")
                    j["meta"] = meta
                    return j
                except Exception as e:
                    error_type = "timeout" if "timeout" in str(e).lower() else "api_error"
                    # 确保错误信息是可序列化的字符串，避免模块对象
                    error_msg = str(e) if isinstance(str(e), str) else repr(e)
                    # 输出详细错误信息（用于调试）
                    import sys as sys_module
                    print(f"[AIClient] Provider {prov.name} failed (attempt {attempt+1}/{self.retry+1}): {error_msg}", file=sys_module.stderr)
                    logging.warning(f"[summarize] provider {prov.name} failed: {error_msg}")
                    # 记录失败的 meta
                    if attempt == self.retry and prov == self.providers[-1]:
                        # 最后一次失败才返回 fallback
                        import sys as sys_module
                        print(f"[AIClient] All providers failed, using fallback mode", file=sys_module.stderr)
                        pass
                    continue
            time.sleep(0.6*(attempt+1))
        
        # Fallback
        return {
            "summary": "",
            "key_points": _simple_keywords(text, 8),
            "keywords": _simple_keywords(text, 12),
            "meta": {"provider": "fallback", "model": "local", "tokens": 0, "cost_usd": 0.0, "latency_ms": 0.0}
        }
    def keywords(self, text: str, top_k: int=12, lang: str="auto") -> List[str]:
        sys = "You are a helpful assistant for keyword extraction."
        user = f"Extract top {top_k} keywords from the text in language={lang}. Return only a comma-separated list.\n\n{text}"
        for attempt in range(self.retry + 1):
            for prov in self.providers:
                try:
                    raw = prov.chat(sys, user, temperature=0.1, max_tokens=256)
                    arr = self._to_list_from_csv(raw)
                    if arr:
                        return arr[:top_k]
                except Exception:
                    continue
            time.sleep(0.5*(attempt+1))
        return _simple_keywords(text, top_k)
    def chapters(self, text: str, lang: str="auto") -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        章节接口（统一 meta + 内建重试）
        
        返回：([{start, title, key_points}], meta)
        """
        sys = "You are an expert in chaptering long transcripts with time anchors when possible."
        user = f"""Create 4-10 chapters for the transcript (language={lang}). 
Each chapter object must be a JSON with: start (HH:MM:SS), title, key_points (3-6).
If explicit timestamps are missing, estimate starts as 00:00:00.
Return a JSON array ONLY.
Transcript:
{text}
"""
        for attempt in range(self.retry + 1):
            for prov in self.providers:
                try:
                    raw, meta = prov.chat(sys, user, temperature=0.3, max_tokens=700)
                    arr = self._safe_json_array(raw) or self._extract_json_array(raw)
                    if arr:
                        return arr, meta
                except Exception:
                    continue
            time.sleep(0.5*(attempt+1))
        # Fallback
        return _simple_chapters(text), {"provider": "fallback", "model": "local", "tokens": 0, "cost_usd": 0.0, "latency_ms": 0.0}
    @staticmethod
    def _safe_json(s: str) -> Dict[str, Any] | None:
        try:
            j = json.loads(s)
            if isinstance(j, dict):
                return j
        except Exception:
            return None
        return None
    @staticmethod
    def _safe_json_array(s: str) -> List[Dict[str, Any]] | None:
        try:
            j = json.loads(s)
            if isinstance(j, list):
                return j
        except Exception:
            return None
        return None
    @staticmethod
    def _extract_json_block(s: str) -> Dict[str, Any] | None:
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            j = json.loads(m.group(0))
            return j if isinstance(j, dict) else None
        except Exception:
            return None
    @staticmethod
    def _extract_json_array(s: str) -> List[Dict[str, Any]] | None:
        m = re.search(r"\[[\s\S]*\]", s)
        if not m:
            return None
        try:
            j = json.loads(m.group(0))
            return j if isinstance(j, list) else None
        except Exception:
            return None
    @staticmethod
    def _to_list_from_csv(s: str) -> List[str]:
        parts = [p.strip() for p in re.split(r"[,\n;，、]\s*", s) if p.strip()]
        out, seen = [], set()
        for p in parts:
            p = re.sub(r"^\d+[\).\s]+", "", p)
            if len(p) > 40:
                continue
            k = p.lower()
            if k not in seen:
                out.append(p); seen.add(k)
        return out[:20]
