# -*- coding: utf-8 -*-
"""
core.reporting — HTML/Markdown 报告生成
"""
from __future__ import annotations
import json, base64, logging
from pathlib import Path
from typing import Dict, Any, List

# ---------- 运行记录迭代 ----------
def _rec_path(run_dir: str) -> Path:
    """获取记录文件路径"""
    return Path(run_dir) / "run.jsonl"

def _iter_run_records(run_dir: str):
    """迭代运行记录"""
    p = _rec_path(run_dir)
    if not p.exists():
        return
    for ln in p.read_text("utf-8", errors="ignore").splitlines():
        try:
            yield json.loads(ln)
        except:
            continue

def summarize_run(run_dir: str) -> Dict[str, Any]:
    """汇总运行统计"""
    total = 0
    has_subs = 0
    no_subs = 0
    errors = 0
    err_kinds = {}
    lang_counts = {"zh": 0, "en": 0, "other": 0}
    videos = []
    
    for r in _iter_run_records(run_dir):
        total += 1
        st = r.get("status", "")
        if st == "has_subs":
            has_subs += 1
        elif st == "no_subs":
            no_subs += 1
        elif str(st).startswith("error"):
            errors += 1
            err_kinds[st] = err_kinds.get(st, 0) + 1
        
        for lc in (r.get("manual_langs") or []) + (r.get("auto_langs") or []):
            b = "zh" if str(lc).lower().startswith(("zh", "cmn")) else "en" if str(lc).lower().startswith("en") else "other"
            lang_counts[b] += 1
        
        videos.append({
            "video_id": r.get("video_id"),
            "title": r.get("title"),
            "channel": r.get("channel"),
            "upload_date": r.get("upload_date"),
            "status": st
        })
    
    return {
        "run_dir": run_dir,
        "total": total,
        "has_subs": has_subs,
        "no_subs": no_subs,
        "errors": errors,
        "error_breakdown": err_kinds,
        "lang_counts": lang_counts,
        "videos": videos
    }

def generate_report_charts(run_dir: str) -> List[str]:
    """生成报告图表（可选，需要 matplotlib）"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        logging.warning(f"Matplotlib not available: {e}")
        return []
    
    sm = summarize_run(run_dir)
    out_paths = []
    
    # 错误饼图（保护：全零时使用占位，避免 RuntimeWarning/DivideByZero）
    labels = list(sm["error_breakdown"].keys()) or ["no_error"]
    sizes = [sm["error_breakdown"].get(k, 0) for k in labels]
    if not sizes or sum(sizes) <= 0:
        labels, sizes = ["no_error"], [1]
    fig = plt.figure()
    plt.pie(sizes, labels=labels, autopct="%1.1f%%")
    p1 = str(Path(run_dir) / "chart_errors_pie.png")
    fig.savefig(p1, bbox_inches="tight", dpi=144)
    plt.close(fig)
    out_paths.append(p1)
    
    # 语言柱状图
    langs = ["zh", "en", "other"]
    vals = [sm["lang_counts"].get(k, 0) for k in langs]
    fig = plt.figure()
    plt.bar(langs, vals)
    plt.title("Language Counts")
    p2 = str(Path(run_dir) / "chart_lang_bar.png")
    fig.savefig(p2, bbox_inches="tight", dpi=144)
    plt.close(fig)
    out_paths.append(p2)
    
    # 结果柱状图
    metrics = ["has_subs", "no_subs", "errors"]
    mvals = [sm.get("has_subs", 0), sm.get("no_subs", 0), sm.get("errors", 0)]
    fig = plt.figure()
    plt.bar(metrics, mvals)
    plt.title("Result Breakdown")
    p3 = str(Path(run_dir) / "chart_results_bar.png")
    fig.savefig(p3, bbox_inches="tight", dpi=144)
    plt.close(fig)
    out_paths.append(p3)
    
    return out_paths

def export_run_html(run_dir: str) -> str:
    """
    生成 HTML 报告
    
    返回报告文件路径
    """
    try:
        sm = summarize_run(run_dir)
    except Exception:
        return ""
    
    try:
        generate_report_charts(run_dir)
    except Exception:
        pass
    
    def _embed(name: str) -> str:
        """嵌入图片为 base64"""
        fp = Path(run_dir) / name
        if not fp.exists(): 
            return f"<p>{name}（未生成）</p>"
        try:
            b64 = base64.b64encode(fp.read_bytes()).decode("ascii")
            return f'<img alt="{name}" src="data:image/png;base64,{b64}" style="max-width: 320px; margin: 6px;"/>'
        except Exception:
            return f"<p>{name}（无法读取）</p>"
    
    charts = "".join(_embed(n) for n in ("chart_errors_pie.png", "chart_lang_bar.png", "chart_results_bar.png"))
    
    # 诊断摘要（顶部优先展示）
    diag_html = ""
    diag_path = Path(run_dir) / "diagnose.txt"
    if diag_path.exists():
        try:
            diag_lines = diag_path.read_text("utf-8", errors="ignore").splitlines()[:30]
            diag_text = "\n".join(diag_lines)
            diag_html = f"<pre style='background:#f5f5f5;padding:12px;border-radius:6px;overflow:auto;max-width:100%;'>{diag_text}</pre>"
        except Exception:
            pass
    
    # 警告信息
    warn_path = Path(run_dir) / "warnings.txt"
    if warn_path.exists():
        lines = [ln.strip() for ln in warn_path.read_text("utf-8", errors="ignore").splitlines() if ln.strip()]
        total_warns = len(lines)
        warn_html = (
            f"<p>共 {total_warns} 条告警</p>" +
            ("<ul>" + "".join(f"<li>{ln}</li>" for ln in lines[:200]) + "</ul>" if lines else "<p>无告警</p>")
        )
    else:
        warn_html = "<p>无告警</p>"
    
    # 视频表格
    def td(x):
        from html import escape
        return f"<td>{escape(str(x if x is not None else ''))}</td>"
    
    rows = []
    for v in sm.get("videos", [])[:300]:
        rows.append("<tr>" + td(v.get("upload_date")) + td(v.get("status")) + td(v.get("title")) + td(v.get("video_id")) + "</tr>")
    table_html = "<table border='1' cellspacing='0' cellpadding='6'><tr><th>upload_date</th><th>status</th><th>title</th><th>video_id</th></tr>" + "".join(rows) + "</table>"
    
    # AI 卡片（上限 50 条）
    ai_dir = Path(run_dir) / "ai"
    ai_cards = ""
    try:
        if ai_dir.exists():
            all_json = sorted(ai_dir.glob("*.json"))
            total_ai = len(all_json)
            cards = []
            for j in all_json[:50]:
                try:
                    data = json.loads(j.read_text("utf-8"))
                    title = ""
                    for v in sm.get("videos", []):
                        if v.get("video_id") == data.get("video_id"):
                            title = v.get("title") or ""
                            break
                    brief = (data.get("summary") or "")[:160].replace("\n", " ")
                    kws = ", ".join(data.get("keywords") or [])[:120]
                    chapters = data.get("chapters") or []
                    ch_html = ""
                    if chapters:
                        li = []
                        for c in chapters:
                            li.append(f"<li>[{c.get('start','00:00:00')}] {c.get('title','')}</li>")
                        ch_html = "<ul style='margin-top:6px'>" + "".join(li) + "</ul>"
                    cards.append(f"<div style='border:1px solid #ddd;border-radius:8px;padding:10px;margin:6px;max-width:720px;'><b>{title or data.get('video_id')}</b><br/><div style='margin-top:6px;font-size:13px;line-height:1.5;'>{brief}</div><div style='margin-top:6px;color:#555;'>🔑 {kws}</div>{ch_html}</div>")
                except Exception:
                    continue
            if cards:
                header = f"<h3>AI 摘要（展示 {len(cards)}/{total_ai} 条）</h3>"
                if total_ai > 50:
                    header += f"<p style='color:#666;'>（共 {total_ai} 条，仅展示前 50 条）</p>"
                ai_cards = header + "".join(cards)
    except Exception:
        pass
    
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Run Report</title></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial; padding: 12px;">
<h2>运行报告</h2>
<p>目录：{run_dir}</p>
<h3>📊 诊断摘要</h3>
{diag_html if diag_html else "<p>无诊断报告</p>"}
<h3>⚠️ Warnings</h3>
{warn_html}
<p>总数：{sm.get('total',0)}；有字幕：{sm.get('has_subs',0)}；无字幕：{sm.get('no_subs',0)}；错误：{sm.get('errors',0)}</p>
<div style="display:flex; flex-wrap: wrap;">{charts}</div>
{ai_cards}
<h3>明细（最多 300 条）</h3>
{table_html}
</body></html>"""
    
    try:
        out = Path(run_dir) / "report.html"
        out.write_text(html, encoding="utf-8")
        return str(out)
    except Exception:
        return ""

def export_weekly_markdown(out_root: str, days: int = 7) -> str:
    """
    生成周报 Markdown（汇总近 N 天的所有运行）
    
    返回报告文件路径
    """
    import os
    from datetime import datetime, timedelta
    
    # 找到所有运行目录
    out_path = Path(out_root)
    if not out_path.exists():
        return ""
    
    cutoff_date = datetime.now() - timedelta(days=days)
    runs = []
    
    for d in out_path.iterdir():
        if not d.is_dir() or not d.name.startswith("run_"):
            continue
        try:
            # 解析目录名时间戳
            ts_str = d.name.replace("run_", "")
            run_dt = datetime.strptime(ts_str[:14], "%Y%m%d%H%M%S")
            if run_dt >= cutoff_date:
                runs.append((run_dt, d))
        except Exception:
            continue
    
    if not runs:
        return ""
    
    runs.sort(reverse=True)  # 最新的在前
    
    # 累计统计
    total_all = 0
    has_subs_all = 0
    no_subs_all = 0
    errors_all = 0
    err_kinds_all = {}
    lang_counts_all = {"zh": 0, "en": 0, "other": 0}
    
    run_summaries = []
    for run_dt, run_dir in runs:
        sm = summarize_run(str(run_dir))
        total_all += sm.get("total", 0)
        has_subs_all += sm.get("has_subs", 0)
        no_subs_all += sm.get("no_subs", 0)
        errors_all += sm.get("errors", 0)
        
        for k, v in sm.get("error_breakdown", {}).items():
            err_kinds_all[k] = err_kinds_all.get(k, 0) + v
        
        for k, v in sm.get("lang_counts", {}).items():
            lang_counts_all[k] = lang_counts_all.get(k, 0) + v
        
        run_summaries.append({
            "run_dir": run_dir.name,
            "date": run_dt.strftime("%Y-%m-%d %H:%M"),
            "total": sm.get("total", 0),
            "has_subs": sm.get("has_subs", 0),
            "errors": sm.get("errors", 0)
        })
    
    # 生成 Markdown
    md = f"""# 周报（近 {days} 天）

**生成时间**：{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 📊 总体统计

- **累计运行**：{len(runs)} 次
- **累计视频**：{total_all} 个
- **有字幕**：{has_subs_all} 个
- **无字幕**：{no_subs_all} 个
- **错误**：{errors_all} 个

## 🌐 语言分布

- **中文**：{lang_counts_all.get('zh', 0)} 个
- **英文**：{lang_counts_all.get('en', 0)} 个
- **其他**：{lang_counts_all.get('other', 0)} 个

## ❌ 错误类型分布

"""
    for k, v in sorted(err_kinds_all.items(), key=lambda x: x[1], reverse=True):
        md += f"- **{k}**：{v} 次\n"
    
    md += "\n## 📁 运行记录\n\n"
    md += "| 日期 | 运行目录 | 总数 | 有字幕 | 错误 |\n"
    md += "|------|----------|------|--------|------|\n"
    
    for rs in run_summaries:
        md += f"| {rs['date']} | {rs['run_dir']} | {rs['total']} | {rs['has_subs']} | {rs['errors']} |\n"
    
    # 保存
    try:
        out_file = out_path / f"weekly_report_{datetime.now().strftime('%Y%m%d')}.md"
        out_file.write_text(md, encoding="utf-8")
        return str(out_file)
    except Exception:
        return ""

def export_run_md(run_dir: str) -> str:
    """
    生成 Markdown 报告
    
    返回报告文件路径
    """
    sm = summarize_run(run_dir)
    lines = [f"# Run Report - {Path(run_dir).name}", ""]
    lines += [
        f"- total: {sm.get('total',0)}",
        f"- has_subs: {sm.get('has_subs',0)}",
        f"- no_subs: {sm.get('no_subs',0)}",
        f"- errors: {sm.get('errors',0)}",
        ""
    ]
    
    ai_dir = Path(run_dir) / "ai"
    if ai_dir.exists():
        lines.append("## AI Summaries")
        for j in sorted(ai_dir.glob("*.json"))[:50]:
            try:
                data = json.loads(j.read_text("utf-8"))
                title = data.get("video_id", "")
                for v in sm.get("videos", []):
                    if v.get("video_id") == data.get("video_id"):
                        title = v.get("title") or title
                        break
                lines.append(f"### {title}")
                if data.get("summary"): 
                    lines.append(data["summary"][:600] + ("…" if len(data["summary"]) > 600 else ""))
                if data.get("keywords"): 
                    lines.append("- **Keywords**: " + ", ".join(data["keywords"][:15]))
                if data.get("chapters"):
                    lines.append("- **Chapters**:")
                    for c in data["chapters"]:
                        lines.append(f"  - [{c.get('start','00:00:00')}] {c.get('title','')}")
                lines.append("")
            except Exception:
                continue
    
    out = Path(run_dir) / "report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out)

