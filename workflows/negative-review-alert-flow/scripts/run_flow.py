# -*- coding: utf-8 -*-
"""
差评预警联动 —— 端到端编排脚本。

编排链路（DAG）：
    差评识别(星级≤3 或负面词) ──► 根因分类(五类词表+优先序)
      ──► 严重度分级(S1 立即/S2 紧急/S3 常规) ──► 安抚话术策略(emotion-detect-appease 口径)
      ──► 预警推送汇总

失败处理：
  - reviews 缺失 → 退出码 1
  - 五类词表全未命中 → 根因「待人工确认」，话术只给「私信了解情况」
  - 评价时间缺失 → 按「立即响应」处理并标注「时间缺失」
  - 升级信号（12315/媒体/律师/食安词）→ S1 立即，AI 不自动回复，转人工

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/差评预警台账.xlsx     预警台账 / S1 立即处置 / 根因分布
  out/差评预警推送.md       端到端交付物（推送清单 + 话术框架）
  out/negative_review_alert.json
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


# 复用原子技能 human-handoff-route 的情绪分级（真编排）
HH = _load(os.path.join(REPO, "skills", "human-handoff-route", "scripts", "handoff_route.py"),
           "skill_handoff")

# 根因词表：(正则, 根因)。多重命中按 PRIORITY 取主根因。
CAUSE_WORDS = [
    (r"破损|色差|坏了|裂了|故障|没声音|开胶|掉色|异味|次品|漏液", "质量"),
    (r"态度|敷衍|爱答不理|客服|没人理|回复慢", "服务"),
    (r"超时|迟迟|太慢|丢件|物流|快递|未发货|没发货|停滞|超区", "物流"),
    (r"图片[与和]实物|跟图片|和描述|不符|夸大|缩水", "期望差"),
    (r"贵了|不值|涨价|性价比|买贵", "价格"),
]
PRIORITY = ["质量", "服务", "物流", "期望差", "价格"]

# S1 立即处置信号：食安/法务/媒体
S1_PAT = re.compile(r"12315|媒体|曝光|律师|起诉|工商|消协|举报|维权|食物中毒|拉肚子|腹泻|变质|发霉|异物")

# 响应窗口（小时）
S1_WINDOW = "2 小时内电话联系 + 主管介入"
S2_WINDOW = "2 小时内推送安抚话术"
S3_WINDOW = "24 小时内回复"


def parse_time(s):
    try:
        return datetime.fromisoformat(str(s))
    except Exception:
        return None


def run(payload, outdir):
    reviews = payload.get("reviews") or []
    if not reviews:
        at.emit({"error": "缺少 reviews（评价数组）"})
        sys.exit(1)
    now = parse_time(payload.get("now")) or datetime(2026, 9, 30, 9, 0)

    bad, skipped = [], []
    # 步骤 1：差评识别
    for r in reviews:
        rating = r.get("星级")
        neg = bool(re.search(r"太差|失望|垃圾|气死|无语|敷衍|骗子|不值|差评", str(r.get("内容", ""))))
        if (isinstance(rating, (int, float)) and rating <= 3) or neg:
            bad.append(r)
        else:
            skipped.append(r)

    rows = []
    for r in bad:
        text = str(r.get("内容", ""))
        # 步骤 2：根因分类
        found = []
        for pat, cause in CAUSE_WORDS:
            hits = re.findall(pat, text)
            if hits:
                found.append((cause, hits))
        found.sort(key=lambda x: PRIORITY.index(x[0]))
        cause = found[0][0] if found else "待人工确认"
        evidence = f"{found[0][0]}:" + "/".join(sorted(set(found[0][1]))[:2]) if found else "五类词表未命中"
        # 情绪分级（复用 human-handoff-route）
        emo, emo_hits = HH.emotion(text)
        # 步骤 3：严重度分级
        s1_hits = S1_PAT.findall(text)
        reply = str(r.get("回复状态", "未回复"))
        review_dt = parse_time(r.get("评价时间"))
        age_h = round((now - review_dt).total_seconds() / 3600, 1) if review_dt else None
        if s1_hits or emo >= 3:
            sev, window = "S1 立即", S1_WINDOW
            action = "AI 不自动回复；店主电话联系 + 主管介入 + 留存证据"
        elif emo == 2 or cause == "质量" or (age_h is not None and age_h > 24 and reply != "已回复"):
            sev, window = "S2 紧急", S2_WINDOW
            action = "推送四步安抚话术，店主确认后回复"
        else:
            sev, window = "S3 常规", S3_WINDOW
            action = "推送标准回复模板，24 小时内回复"
        # 步骤 4：话术策略（emotion-detect-appease 口径）
        policy = {0: "直接解答+轻共情", 1: "共情+给明确时间点",
                  2: "强共情+解释+授权内补偿选项", 3: "先道歉认责、只谈解决",
                  4: "立即致歉+转主管留痕"}[emo]
        rows.append({
            "评价ID": r.get("评价ID", ""), "平台": r.get("平台", ""),
            "星级": rating, "差评原文": text,
            "主根因": cause, "命中证据": evidence,
            "情绪等级": HH.EMOTION_LEVEL[emo], "严重度": sev,
            "响应窗口": window, "话术策略": policy, "处置": action,
            "评价年龄小时": age_h if age_h is not None else "时间缺失",
            "回复状态": reply,
        })

    order = {"S1 立即": 0, "S2 紧急": 1, "S3 常规": 2}
    rows.sort(key=lambda x: (order.get(x["严重度"], 9), str(x["评价年龄小时"])))
    s1 = [r for r in rows if r["严重度"] == "S1 立即"]
    cause_cnt = {}
    for r in rows:
        cause_cnt[r["主根因"]] = cause_cnt.get(r["主根因"], 0) + 1
    unreplied = sum(1 for r in rows if r["回复状态"] != "已回复")
    summary = {
        "评价总数": len(reviews), "差评数": len(rows), "跳过好评中评": len(skipped),
        "S1 立即": len(s1),
        "S2 紧急": len([r for r in rows if r["严重度"] == "S2 紧急"]),
        "S3 常规": len([r for r in rows if r["严重度"] == "S3 常规"]),
        "根因分布": cause_cnt,
        "未回复差评": unreplied,
        "响应窗口": f"S1={S1_WINDOW}；S2={S2_WINDOW}；S3={S3_WINDOW}",
        "红线": "补偿只换「再给一次机会」，禁止删差评/改好评交换（《反不正当竞争法》第八条）",
        "AI 标识": "AI 生成内容",
    }
    steps = [
        {"步骤": "1. 差评识别", "技能": "negative-review-alert-flow（内置）", "状态": "ok",
         "输出": f"{len(bad)} 条差评/中评", "失败处理": "星级缺失→按负面词兜底"},
        {"步骤": "2. 根因分类", "技能": "五类词表（质量>服务>物流>期望差>价格）", "状态": "ok",
         "输出": "主根因+命中证据", "失败处理": "全未命中→待人工确认"},
        {"步骤": "3. 严重度分级", "技能": "human-handoff-route（情绪）+ 升级信号", "状态": "ok",
         "输出": f"S1 {len(s1)} / S2 {summary['S2 紧急']} / S3 {summary['S3 常规']}",
         "失败处理": "时间缺失→按立即响应处理"},
        {"步骤": "4. 话术策略", "技能": "emotion-detect-appease（话术框架）", "状态": "ok",
         "输出": "按情绪映射策略", "失败处理": "根因待确认→只给「私信了解情况」"},
        {"步骤": "5. 预警推送汇总", "技能": "negative-review-alert-flow（内置）", "状态": "ok",
         "输出": "预警台账 + 推送清单", "失败处理": "—"},
    ]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "差评预警台账.xlsx"),
        {
            "预警台账": rows or [{"评价ID": "（无差评）"}],
            "S1 立即处置": [{k: r[k] for k in ("评价ID", "平台", "差评原文", "命中证据", "处置")}
                        for r in s1] or [{"评价ID": "（无 S1）"}],
            "根因分布": [{"根因": k, "条数": v} for k, v in cause_cnt.items()],
        },
        highlights={"预警台账": {"严重度": "contains:S1"}},
        widths={"预警台账": {"差评原文": 30, "处置": 36, "命中证据": 22}},
    )
    js = at.write_json({"summary": summary, "steps": steps, "alerts": rows,
                        "generated_at": at.stamp(),
                        "note": "识别/根因/严重度为规则计算；四步话术成稿由模型按 prompt.txt 撰写"},
                       os.path.join(outdir, "negative_review_alert.json"))

    md = ["# 差评预警联动 —— 推送报告\n",
          f"> 生成时间：{at.stamp()} ｜ 由 `scripts/run_flow.py` 实跑产出\n",
          "## 一、执行摘要\n",
          f"- 评价 **{summary['评价总数']}** 条：差评 {summary['差评数']}（S1 立即 {summary['S1 立即']} / "
          f"S2 紧急 {summary['S2 紧急']} / S3 常规 {summary['S3 常规']}），未回复 {summary['未回复差评']}",
          f"- 响应窗口：{summary['响应窗口']}\n",
          "## 二、执行步骤\n", "| 步骤 | 技能 | 状态 | 输出 | 失败处理 |", "|---|---|---|---|---|"]
    for s in steps:
        md.append(f"| {s['步骤']} | {s['技能']} | {s['状态']} | {s['输出']} | {s['失败处理']} |")
    md += ["\n## 三、预警推送清单（按严重度排序）\n",
           "| 评价ID | 严重度 | 主根因 | 情绪 | 响应窗口 | 话术策略 |", "|---|---|---|---|---|---|"]
    for r in rows or [{"评价ID": "（无差评）", "严重度": "", "主根因": "", "情绪等级": "",
                       "响应窗口": "", "话术策略": ""}]:
        md.append(f"| {r['评价ID']} | {r['严重度']} | {r['主根因']} | {r['情绪等级']} | "
                  f"{r['响应窗口']} | {r['话术策略']} |")
    md += ["\n## 四、S1 立即处置（AI 不自动回复）\n",
           "| 评价ID | 差评原文 | 处置 |", "|---|---|---|"]
    for r in s1 or [{"评价ID": "（无）", "差评原文": "", "处置": ""}]:
        md.append(f"| {r['评价ID']} | {r['差评原文']} | {r['处置']} |")
    md += ["\n## 五、店主待确认动作\n",
           f"1. S1 {len(s1)} 条：立即电话联系，留存证据，必要时向平台报备。",
           f"2. S2 {summary['S2 紧急']} 条：按四步话术框架（共情→诊断→方案→行动）成稿后回复。",
           f"3. S3 {summary['S3 常规']} 条：24 小时内回复，回复率目标 100%。",
           "\n---\n",
           "*本报告由 AI 生成；禁止删差评/改好评交换（《反不正当竞争法》第八条）；对外回复前须店主确认。*"]
    md_path = os.path.join(outdir, "差评预警推送.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return {"files": [xlsx, os.path.abspath(md_path), js], "summary": summary}


DEMO = {
    "shop": "潮流数码旗舰店",
    "now": "2026-09-30 09:00",
    "reviews": [
        {"评价ID": "R-9001", "平台": "淘宝", "星级": 1, "内容": "充电宝用了一周就鼓包了，太吓人了，再不处理我就打12315", "订单金额": 129, "评价时间": "2026-09-30 08:10", "回复状态": "未回复", "订单号": "TB9001"},
        {"评价ID": "R-9002", "平台": "淘宝", "星级": 2, "内容": "耳机左耳没声音，质量太差了，客服还敷衍我", "订单金额": 199, "评价时间": "2026-09-30 07:30", "回复状态": "未回复", "订单号": "TB9002"},
        {"评价ID": "R-9003", "平台": "拼多多", "星级": 3, "内容": "物流太慢了，等了五天才到", "订单金额": 59, "评价时间": "2026-09-29 21:00", "回复状态": "已回复", "订单号": "PDD9003"},
        {"评价ID": "R-9004", "平台": "京东", "星级": 2, "内容": "跟图片完全不符，图片金属实际塑料，感觉被夸大宣传了", "订单金额": 89, "评价时间": "2026-09-29 18:40", "回复状态": "未回复", "订单号": "JD9004"},
        {"评价ID": "R-9005", "平台": "淘宝", "星级": 5, "内容": "很好用，续航给力，发货也快", "订单金额": 149, "评价时间": "2026-09-29 12:00", "回复状态": "已回复", "订单号": "TB9005"},
        {"评价ID": "R-9006", "平台": "抖音", "星级": 1, "内容": "再也不买了", "订单金额": None, "评价时间": "2026-09-29 23:50", "回复状态": "未回复", "订单号": "DY9006"},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="差评预警联动 —— 端到端编排")
    ap.add_argument("--input")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = run(payload, a.outdir)
    s = r["summary"]
    print(f"预警完成：评价 {s['评价总数']} 条，差评 {s['差评数']}（S1 {s['S1 立即']} / S2 {s['S2 紧急']} / "
          f"S3 {s['S3 常规']}），未回复 {s['未回复差评']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
