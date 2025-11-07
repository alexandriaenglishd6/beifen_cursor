# -*- coding: utf-8 -*-
"""
批量操作工具 - URL批量导入、清理、去重
"""
from pathlib import Path
from typing import List, Tuple, Dict
import json
import csv
from validators import validate_url, validate_url_list


class BatchURLManager:
    """
    批量URL管理器
    
    功能：
    1. 从文件导入URL（支持txt/csv/json）
    2. 清理无效URL
    3. 移除重复URL
    4. URL验证和统计
    """
    
    @staticmethod
    def import_from_file(file_path: Path) -> Dict[str, any]:
        """
        从文件导入URL
        
        支持格式：
        - TXT: 一行一个URL
        - CSV: 读取第一列或url列
        - JSON: 支持数组或对象数组
        
        Args:
            file_path: 文件路径
        
        Returns:
            {
                "success": bool,
                "urls": List[str],
                "total": int,
                "valid": int,
                "invalid": int,
                "errors": List[str]
            }
        """
        result = {
            "success": False,
            "urls": [],
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "errors": []
        }
        
        if not file_path.exists():
            result["errors"].append(f"文件不存在: {file_path}")
            return result
        
        try:
            urls = []
            suffix = file_path.suffix.lower()
            
            if suffix == ".txt":
                # TXT: 一行一个URL
                with open(file_path, "r", encoding="utf-8") as f:
                    urls = [line.strip() for line in f if line.strip()]
            
            elif suffix == ".csv":
                # CSV: 读取第一列或url列
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    if reader.fieldnames and "url" in reader.fieldnames:
                        # 有url列，使用url列
                        for row in reader:
                            url = row.get("url", "").strip()
                            if url:
                                urls.append(url)
                    else:
                        # 没有url列，使用第一列
                        f.seek(0)
                        reader = csv.reader(f)
                        for row in reader:
                            if row and row[0].strip():
                                urls.append(row[0].strip())
            
            elif suffix == ".json":
                # JSON: 支持数组或对象数组
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, str):
                                urls.append(item.strip())
                            elif isinstance(item, dict):
                                # 尝试多种可能的键名
                                url = item.get("url") or item.get("link") or item.get("URL") or item.get("Link")
                                if url:
                                    urls.append(str(url).strip())
                    elif isinstance(data, dict):
                        # 如果是对象，尝试获取urls或items键
                        items = data.get("urls", []) or data.get("items", [])
                        for item in items:
                            if isinstance(item, str):
                                urls.append(item.strip())
                            elif isinstance(item, dict):
                                url = item.get("url") or item.get("link")
                                if url:
                                    urls.append(str(url).strip())
            
            else:
                # 未知格式，尝试按文本解析
                with open(file_path, "r", encoding="utf-8") as f:
                    urls = [line.strip() for line in f if line.strip()]
            
            # 去重并过滤空白
            urls = list(dict.fromkeys(url for url in urls if url))
            
            # 验证URL
            valid_urls = []
            invalid_count = 0
            
            for url in urls:
                is_valid, error_msg = validate_url(url)
                if is_valid:
                    valid_urls.append(url)
                else:
                    invalid_count += 1
                    if len(result["errors"]) < 5:  # 只记录前5个错误
                        result["errors"].append(f"{url[:50]}: {error_msg[:50]}")
            
            result["success"] = True
            result["urls"] = valid_urls
            result["total"] = len(urls)
            result["valid"] = len(valid_urls)
            result["invalid"] = invalid_count
            
            if len(result["errors"]) > 5:
                result["errors"].append(f"... 还有 {len(result['errors']) - 5} 个错误")
        
        except json.JSONDecodeError as e:
            result["errors"].append(f"JSON解析失败: {e}")
        except Exception as e:
            result["errors"].append(f"读取文件失败: {e}")
        
        return result
    
    @staticmethod
    def clean_invalid_urls(urls: List[str]) -> Dict[str, any]:
        """
        清理无效URL
        
        Args:
            urls: URL列表
        
        Returns:
            {
                "valid_urls": List[str],
                "invalid_urls": List[str],
                "removed_count": int
            }
        """
        valid_urls = []
        invalid_urls = []
        
        for url in urls:
            is_valid, _ = validate_url(url)
            if is_valid:
                valid_urls.append(url)
            else:
                invalid_urls.append(url)
        
        return {
            "valid_urls": valid_urls,
            "invalid_urls": invalid_urls,
            "removed_count": len(invalid_urls)
        }
    
    @staticmethod
    def remove_duplicates(urls: List[str]) -> Dict[str, any]:
        """
        移除重复URL
        
        Args:
            urls: URL列表
        
        Returns:
            {
                "unique_urls": List[str],
                "duplicate_count": int,
                "duplicates": List[str]
            }
        """
        # 使用字典保持顺序并去重
        seen = {}
        duplicates = []
        
        for url in urls:
            # 规范化URL（统一大小写，去除末尾斜杠）
            normalized = url.strip().rstrip('/').lower()
            
            if normalized in seen:
                duplicates.append(url)
            else:
                seen[normalized] = url
        
        unique_urls = list(seen.values())
        
        return {
            "unique_urls": unique_urls,
            "duplicate_count": len(duplicates),
            "duplicates": duplicates
        }
    
    @staticmethod
    def validate_and_statistics(urls: List[str]) -> Dict[str, any]:
        """
        验证URL并生成统计信息
        
        Args:
            urls: URL列表
        
        Returns:
            {
                "total": int,
                "valid": int,
                "invalid": int,
                "valid_urls": List[str],
                "invalid_urls": List[Tuple[str, str]],  # (url, error_msg)
                "statistics": Dict[str, int]  # 按域名统计
            }
        """
        valid_urls = []
        invalid_urls = []
        domain_stats = {}
        
        for url in urls:
            is_valid, error_msg = validate_url(url)
            
            if is_valid:
                valid_urls.append(url)
                # 统计域名
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url if url.startswith(('http://', 'https://')) else f'https://{url}')
                    domain = parsed.netloc or parsed.path.split('/')[0]
                    domain_stats[domain] = domain_stats.get(domain, 0) + 1
                except:
                    pass
            else:
                invalid_urls.append((url, error_msg))
        
        return {
            "total": len(urls),
            "valid": len(valid_urls),
            "invalid": len(invalid_urls),
            "valid_urls": valid_urls,
            "invalid_urls": invalid_urls,
            "statistics": domain_stats
        }


__all__ = ['BatchURLManager']

