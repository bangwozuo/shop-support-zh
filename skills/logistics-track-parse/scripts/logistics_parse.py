# -*- coding: utf-8 -*-
"""
物流跟踪解读 —— 轨迹事件归一化 + 异常预警器。

职责边界：本脚本只做**确定性解析与判定**（状态归一化、停滞时长、异常判定、话术映射，
机器做得出、可复现）。共情措辞、多轮沟通由模型按 prompt.txt 完成。

用法：
  python logistics_parse.py --input input.json --outdir out
  python logistics_parse.py --demo                    # 用内置样例跑一遍

产物：
  out/物流轨迹解读.xlsx   轨迹解读 / 事件明细 / 异常件台账 / 话术建议
  out/物流状态分布.png    当前状态分布柱状图
  out/logistics.json      机器可读结果（供智能体读取，含 summary）
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(SKILL_DIR))
sys.path.insert(0, os.path.join(REPO, "lib"))

try:
    import assettools as at
except ImportError:  # pragma: no cover
    print("[错误] 未找到 lib/assettools.py。请确认技能位于 <repo>/skills/<slug>/scripts/ 下，"
          "且 <repo>/lib/assettools.py 存在。", file=sys.stderr)
    sys.exit(2)

# 异常件：超 N 小时无轨迹更新即主动介入（行业常用阈值）
STALE_HOURS = 72

# 关键词 → 归一化状态（自上而下匹配，先具体后宽泛）
STATUS_RULES = [
    ("已签收", ["已签收", "签收", "已妥投", "代收", "已取件"]),
    ("异常件", ["退回", "拒收", "滞留", "丢失", "损坏", "超区", "异常", "疑难", "无法联系"]),
    ("派件中", ["派件", "派送", "正在投递", "安排投递", "派送中"]),
    ("运输中", ["运输", "中转", "发往", "到达", "离开", "已发出", "干线", "集包"]),
    ("待揽收", ["待揽收", "待收件", "已下单", "等待揽收"]),
    ("已揽收", ["已揽收", "揽收", "已收件", "收寄"]),
]

TALK = {
    "待揽收": "您的订单已下单，仓库正在打包，预计 48 小时内揽收，如有延迟我们会主动同步。",
    "已揽收": "包裹已揽收，物流节点通常每 24 小时更新一次，请留意后续轨迹。",
    "运输中": "包裹正在运输途中，会按面单路线中转，到达派件网点后会更新「派件中」。",
    "派件中": "快递员正在派送，请保持电话畅通；若今日未收到，我们会帮您跟进网点。",
    "已签收": "包裹已显示签收。若您本人未收到，可能是门卫/驿站代收，请先核实；仍无果我们即刻为您发起查件。",
    "异常件": "非常抱歉给您添麻烦了，我们已主动联系承运方核查该包裹，将在 24 小时内给您明确答复。",
}


def parse_time(s: str):
    s = str(s or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def norm_status(text: str) -> str:
    t = str(text or "")
    for status, kws in STATUS_RULES:
        if any(k in t for k in kws):
            return status
    return "运输中"


def analyze_shipment(sh: dict, now: datetime, stale_hours: int = STALE_HOURS) -> dict:
    events = sorted(
        (e for e in (sh.get("事件") or []) if parse_time(e.get("时间"))),
        key=lambda e: parse_time(e["时间"]),
    )
    if not events:
        return {
            "运单号": sh.get("运单号", ""), "承运商": sh.get("承运商", ""),
            "订单号": sh.get("订单号", ""), "当前状态": "无轨迹",
            "最后更新": "", "停滞小时": None, "是否异常": "❌ 无轨迹",
            "异常类型": "无有效轨迹事件", "话术建议": "请用户核对运单号，或由客服向承运方查件。",
        }
    last = events[-1]
    last_time = parse_time(last["时间"])
    status = norm_status(last.get("描述", ""))
    stagnant = round((now - last_time).total_seconds() / 3600, 1)

    anomalies = []
    if status == "异常件":
        anomalies.append("轨迹异常（退回/拒收/滞留/超区等）")
    if status != "已签收" and stagnant >= stale_hours:
        anomalies.append(f"超 {stale_hours} 小时无更新")

    return {
        "运单号": sh.get("运单号", ""),
        "承运商": sh.get("承运商", ""),
        "订单号": sh.get("订单号", ""),
        "当前状态": status,
        "最后更新": last.get("时间", ""),
        "最后节点": last.get("描述", ""),
        "停滞小时": stagnant,
        "是否异常": "⚠️ 异常" if anomalies else "正常",
        "异常类型": "；".join(anomalies) if anomalies else "",
        "话术建议": TALK.get(status, ""),
    }


def build(payload: dict, outdir: str) -> dict:
    shipments = payload.get("shipments") or []
    stale_hours = int(payload.get("stale_hours", STALE_HOURS))
    if not shipments:
        at.emit({"error": "缺少 shipments（运单轨迹）"})
        sys.exit(1)

    all_times = [parse_time(e["时间"]) for sh in shipments for e in (sh.get("事件") or [])
                 if parse_time(e.get("时间"))]
    now = parse_time(payload.get("now")) or (max(all_times) if all_times else datetime.now())
    now_note = payload.get("now") or "（未提供 now，取全量事件最晚时间）"

    rows, anomaly_rows, event_rows, status_cnt = [], [], [], {}
    for sh in shipments:
        r = analyze_shipment(sh, now, stale_hours)
        rows.append(r)
        status_cnt[r["当前状态"]] = status_cnt.get(r["当前状态"], 0) + 1
        if r["是否异常"] != "正常":
            anomaly_rows.append(r)
        for e in sorted((sh.get("事件") or []), key=lambda x: parse_time(x.get("时间")) or now):
            event_rows.append({
                "运单号": sh.get("运单号", ""),
                "时间": e.get("时间", ""),
                "节点描述": e.get("描述", ""),
                "地点": e.get("地点", ""),
                "归一化状态": norm_status(e.get("描述", "")),
            })

    talk_rows = []
    for st, talk in TALK.items():
        n = status_cnt.get(st, 0)
        if n:
            talk_rows.append({"状态": st, "运单数": n, "标准话术": talk})

    summary = {
        "运单总数": len(rows),
        "正常件": len(rows) - len(anomaly_rows),
        "异常件": len(anomaly_rows),
        "异常率": f"{len(anomaly_rows) / len(rows) * 100:.1f}%" if rows else "0%",
        "停滞阈值小时": stale_hours,
        "基准时间": now.strftime("%Y-%m-%d %H:%M"),
    }

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "物流轨迹解读.xlsx"),
        {
            "轨迹解读": rows,
            "异常件台账": anomaly_rows or [{"运单号": "（无异常件）", "异常类型": "", "话术建议": ""}],
            "事件明细": event_rows,
            "话术建议": talk_rows,
        },
        highlights={"轨迹解读": {"是否异常": "contains:异常"}},
        widths={"轨迹解读": {"最后节点": 34, "话术建议": 46, "异常类型": 22},
                "异常件台账": {"话术建议": 46, "异常类型": 26},
                "事件明细": {"节点描述": 34}},
    )
    png = at.bar_chart(
        os.path.join(outdir, "物流状态分布.png"),
        list(status_cnt.keys()), list(status_cnt.values()),
        title="在途运单 · 当前状态分布", ylabel="运单数",
    )
    js = at.write_json({"summary": summary, "shipments": rows, "anomalies": anomaly_rows,
                        "generated_at": at.stamp(), "now_note": now_note,
                        "note": "状态归一化与异常判定为脚本结果；话术润色由模型按 prompt.txt 完成"},
                       os.path.join(outdir, "logistics.json"))
    return {"files": [xlsx, png, js], "summary": summary}


DEMO = {
    "now": "2026-09-30 09:00",
    "stale_hours": 72,
    "shipments": [
        {"运单号": "SF1380001112223", "承运商": "顺丰", "订单号": "TB20260925001", "事件": [
            {"时间": "2026-09-27 10:12", "描述": "快件已揽收", "地点": "杭州余杭"},
            {"时间": "2026-09-28 08:30", "描述": "快件离开杭州集散中心，发往上海", "地点": "杭州"},
            {"时间": "2026-09-29 19:05", "描述": "快件正在派送中，快递员小王 138****", "地点": "上海浦东"},
        ]},
        {"运单号": "YT7600123456789", "承运商": "圆通", "订单号": "TB20260922007", "事件": [
            {"时间": "2026-09-24 14:00", "描述": "快件已揽收", "地点": "广州白云"},
            {"时间": "2026-09-25 22:10", "描述": "快件到达武汉中转", "地点": "武汉"},
            {"时间": "2026-09-26 09:40", "描述": "快件离开武汉，发往郑州", "地点": "武汉"},
        ]},
        {"运单号": "ZTO5500987654321", "承运商": "中通", "订单号": "TB20260920033", "事件": [
            {"时间": "2026-09-21 11:20", "描述": "快件已揽收", "地点": "成都双流"},
            {"时间": "2026-09-22 07:50", "描述": "快件到达重庆中转", "地点": "重庆"},
            {"时间": "2026-09-26 16:30", "描述": "快件退回发件人，原因：收件地址超区", "地点": "重庆"},
        ]},
        {"运单号": "JD0033112255667", "承运商": "京东物流", "订单号": "TB20260926018", "事件": [
            {"时间": "2026-09-27 09:00", "描述": "包裹已揽收", "地点": "北京通州"},
            {"时间": "2026-09-28 12:00", "描述": "包裹已到达北京朝阳站", "地点": "北京"},
            {"时间": "2026-09-29 15:40", "描述": "您的包裹已签收，签收人：本人", "地点": "北京朝阳"},
        ]},
        {"运单号": "EMS9988776655443", "承运商": "EMS", "订单号": "TB20260915006", "事件": [
            {"时间": "2026-09-18 17:00", "描述": "邮件已收寄", "地点": "乌鲁木齐"},
            {"时间": "2026-09-19 10:00", "描述": "邮件到达乌鲁木齐中心，发往喀什", "地点": "乌鲁木齐"},
        ]},
        {"运单号": "YUNDA7711223344", "承运商": "韵达", "订单号": "TB20260929044", "事件": [
            {"时间": "2026-09-30 08:10", "描述": "快件待揽收", "地点": "义乌北苑"},
        ]},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="物流跟踪解读 —— 轨迹归一化与异常预警")
    ap.add_argument("--input", help="输入 JSON（shipments / now / stale_hours）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    payload = DEMO if a.demo else (at.read_json(a.input) if a.input
                                   else ap.error("需要 --input 或 --demo"))
    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"解析完成：运单 {s['运单总数']} 单，异常 {s['异常件']} 单（异常率 {s['异常率']}），"
          f"停滞阈值 {s['停滞阈值小时']}h")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
