# -*- coding: utf-8 -*-
"""
订单/物流自动查询 —— 端到端编排脚本。

编排链路（DAG）：
    单号识别 ──► logistics-track-parse（物流跟踪解读） ──► 状态解读回复 ──► 汇总交付

真编排：步骤 2 直接复用原子技能 `logistics-track-parse/scripts/logistics_parse.py` 的
`analyze_shipment()`，不重写解析逻辑。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/物流查询台账.xlsx   运单解读 / 待回复清单
  out/物流查询回复.md     端到端交付物（可直接发给买家/客服）
  out/order_logistics.json
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
FLOW_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(FLOW_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py。", file=sys.stderr)
    sys.exit(2)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# 复用原子技能 logistics-track-parse 的解析实现（真编排）
LOG = _load(os.path.join(REPO, "skills", "logistics-track-parse", "scripts", "logistics_parse.py"),
            "skill_logistics")

TRACKING_RE = re.compile(r"\b([A-Z]{2,4}\d{8,15}|\d{12,15})\b")


def identify_tracking(text: str, shipments: list) -> list:
    """单号识别：优先从文本抽取，其次用 shipments 自带的运单号。"""
    nums = TRACKING_RE.findall(text or "")
    if nums:
        return nums
    return [s.get("运单号", "") for s in shipments if s.get("运单号")]


def run(payload, outdir):
    shipments = payload.get("shipments") or []
    question = payload.get("question", "我的包裹到哪了")
    stale_hours = int(payload.get("stale_hours", LOG.STALE_HOURS))
    if not shipments:
        at.emit({"error": "缺少 shipments"})
        sys.exit(1)

    # 步骤 1：单号识别
    tracking = identify_tracking(question, shipments)
    # 步骤 2：物流解析（调用 logistics-track-parse）
    all_times = [LOG.parse_time(e["时间"]) for s in shipments for e in (s.get("事件") or [])
                 if LOG.parse_time(e.get("时间"))]
    now = LOG.parse_time(payload.get("now")) or (max(all_times) if all_times else datetime.now())
    rows = [LOG.analyze_shipment(s, now, stale_hours) for s in shipments]

    # 步骤 3：状态解读回复
    pending = [r for r in rows if r["是否异常"] != "正常"]
    reply_lines = []
    for r in rows:
        prefix = "亲，非常抱歉～" if r["是否异常"] != "正常" else ""
        reply_lines.append(
            f"【{r['运单号']}】当前：{r['当前状态']}"
            f"{'（异常：' + r['异常类型'] + '）' if r['异常类型'] else ''}。{r['话术建议']}"
        )

    anomalies = [r for r in rows if r["是否异常"] != "正常"]
    summary = {
        "运单总数": len(rows),
        "识别单号数": len(tracking),
        "正常件": len(rows) - len(anomalies),
        "异常件": len(anomalies),
        "待主动回复": len(pending),
        "基准时间": now.strftime("%Y-%m-%d %H:%M"),
    }
    steps = [
        {"步骤": "1. 单号识别", "技能": "order-logistics-query-flow（内置）", "状态": "ok",
         "输出": f"识别 {len(tracking)} 个运单号", "失败处理": "识别不到→让用户发运单号，不猜测"},
        {"步骤": "2. 物流跟踪解读", "技能": "logistics-track-parse", "状态": "ok",
         "输出": f"解析 {len(rows)} 单，异常 {len(anomalies)} 单", "失败处理": "无轨迹→标「无轨迹」，提示核对单号"},
        {"步骤": "3. 状态解读回复", "技能": "order-logistics-query-flow（内置）", "状态": "ok",
         "输出": f"生成 {len(rows)} 条回复话术", "失败处理": "异常件统一走主动介入话术"},
        {"步骤": "4. 汇总交付", "技能": "order-logistics-query-flow（内置）", "状态": "ok",
         "输出": "查询台账 + 回复", "失败处理": "—"},
    ]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "物流查询台账.xlsx"),
        {"运单解读": rows,
         "待回复清单": pending or [{"运单号": "（无异常件）", "话术建议": ""}]},
        highlights={"运单解读": {"是否异常": "contains:异常"}},
        widths={"运单解读": {"话术建议": 50, "最后节点": 34}},
    )
    js = at.write_json({"summary": summary, "steps": steps, "tracks": rows, "tracking": tracking,
                        "generated_at": at.stamp()}, os.path.join(outdir, "order_logistics.json"))

    md = ["# 物流查询执行报告\n", f"> 生成时间：{at.stamp()} ｜ 由 `scripts/run_flow.py` 实跑产出\n",
          "## 一、执行摘要\n",
          f"- 运单 **{summary['运单总数']}** 单：正常 {summary['正常件']}，异常 {summary['异常件']}",
          f"- 待主动回复：**{summary['待主动回复']}** 单；基准时间 {summary['基准时间']}\n",
          "## 二、执行步骤\n", "| 步骤 | 技能 | 状态 | 输出 | 失败处理 |", "|---|---|---|---|---|"]
    for s in steps:
        md.append(f"| {s['步骤']} | {s['技能']} | {s['状态']} | {s['输出']} | {s['失败处理']} |")
    md += ["\n## 三、可直接发送的回复\n"]
    for line in reply_lines:
        md.append(f"- {line}")
    md += ["\n## 四、异常件（需主动介入）\n", "| 运单号 | 当前状态 | 异常类型 | 话术建议 |", "|---|---|---|---|"]
    for r in anomalies or [{"运单号": "（无）", "当前状态": "", "异常类型": "", "话术建议": ""}]:
        md.append(f"| {r['运单号']} | {r['当前状态']} | {r['异常类型']} | {r['话术建议']} |")
    md += ["\n---\n", "*本报告由 AI 生成；丢件/赔付判定须承运方出险并经人工确认。*"]
    md_path = os.path.join(outdir, "物流查询回复.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return {"files": [xlsx, os.path.abspath(md_path), js], "summary": summary}


DEMO = {
    "question": "帮我查下这几个包裹到哪了",
    "now": "2026-09-30 09:00",
    "stale_hours": 72,
    "shipments": LOG.DEMO["shipments"],
}


def main():
    ap = argparse.ArgumentParser(description="订单/物流自动查询 —— 端到端编排")
    ap.add_argument("--input"); ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = run(payload, a.outdir)
    s = r["summary"]
    print(f"查询完成：运单 {s['运单总数']} 单，异常 {s['异常件']} 单，待回复 {s['待主动回复']} 单")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
