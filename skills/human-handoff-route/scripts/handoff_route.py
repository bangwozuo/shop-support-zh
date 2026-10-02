# -*- coding: utf-8 -*-
"""
转人工分流 —— 会话分类 + 情绪/升级判定 + 层级路由 + 交接摘要生成器。

职责边界：本脚本只做**确定性判定与产物生成**（分类树匹配、关键词升级信号、情绪分级、
层级路由、SLA 映射，机器做得出、可复现）。交接摘要的自然语言润色、安抚措辞由模型按
prompt.txt 完成。

用法：
  python handoff_route.py --input input.json --outdir out
  python handoff_route.py --demo

产物：
  out/分流台账.xlsx   分流台账 / 分类分布 / SLA对照 / 升级信号明细
  out/分流层级分布.png
  out/handoff.json    机器可读结果（供智能体读取，含 summary）
"""
from __future__ import annotations

import argparse
import os
import sys

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

# ---------------------------------------------------------------- 规则表
# 客服工单分类树（自上而下匹配，先具体后宽泛）
TICKET_TREE = [
    ("价格", ["价保", "补差价", "降价", "买贵", "活动差", "贵了", "便宜", "优惠", "折扣"]),
    ("退换货", ["退货", "换货", "退款", "七天无理由", "无理由", "退掉", "换新"]),
    ("发票", ["发票", "开票", "税号", "专票", "普票", "报销"]),
    ("尺码不合适", ["尺码", "偏大", "偏小", "不合脚", "穿不下", "号小", "号大", "大小不合适"]),
    ("质量", ["破损", "色差", "功能故障", "坏了", "裂了", "掉色", "开胶", "没声音", "故障", "漏液", "次品"]),
    ("物流", ["未发货", "没发货", "发货", "物流", "快递", "运单", "包裹", "签收", "派件", "在途", "丢件", "超区", "多久到"]),
]

# 情绪分级：命中词 → 分值（累加后分级）
EMOTION_WORDS = {
    "轻微不满": ["有点", "怎么还", "催", "等了", "还没", "慢了", "怎么还没"],
    "明显不满": ["太慢", "失望", "无语", "怎么回事", "搞什么", "麻烦", "敷衍", "不满意"],
    "愤怒": ["愤怒", "气死", "火大", "生气", "气人", "很差", "太差", "垃圾", "坑", "骗人", "骗子", "态度差", "垃圾客服"],
    "极端/威胁": ["曝光", "拉黑", "举报你", "投诉到底", "找你麻烦", "打死", "骂"],
}
EMOTION_SCORE = {"轻微不满": 1, "明显不满": 2, "愤怒": 3, "极端/威胁": 4}
EMOTION_LEVEL = {0: "L0 中性", 1: "L1 轻微不满", 2: "L2 明显不满", 3: "L3 愤怒", 4: "L4 极端/威胁"}

# 升级信号（→ 三线主管介入）
ESCALATE_SIGNALS = ["投诉", "差评", "12315", "平台介入", "工商", "消协", "曝光", "起诉", "律师", "举报", "维权"]

# 层级 SLA
SLA = {
    "一线自助": {"接管": "AI/自助即时", "首响": "< 30 秒", "方案时效": "即刻答复"},
    "二线人工": {"接管": "< 3 分钟", "首响": "已由一线响应", "方案时效": "售后问题 24 小时内给方案"},
    "三线（主管）": {"接管": "< 3 分钟", "首响": "已由一线响应", "方案时效": "24 小时内给方案，主管签字"},
}
# 可直接自助的分类
SELF_SERVICE = {"物流", "发票", "尺码不合适", "其他"}
# 需人工判断的分类
NEEDS_HUMAN = {"质量", "退换货", "价格"}


def classify(text: str) -> tuple:
    for cat, kws in TICKET_TREE:
        hit = [k for k in kws if k in text]
        if hit:
            return cat, hit
    return "其他", []


def emotion(text: str) -> tuple:
    score, hits = 0, []
    for label, kws in EMOTION_WORDS.items():
        hit = [k for k in kws if k in text]
        if hit:
            score = max(score, EMOTION_SCORE[label])
            hits += hit
    return min(score, 4), hits


def escalate_signals(text: str):
    return [s for s in ESCALATE_SIGNALS if s in text]


def route(category: str, emo_level: int, signals: list) -> str:
    if signals:
        return "三线（主管）"
    if emo_level >= 3:
        return "三线（主管）"
    if category in NEEDS_HUMAN or emo_level == 2:
        return "二线人工"
    if category in SELF_SERVICE:
        return "一线自助"
    return "二线人工"


def analyze(conv: dict) -> dict:
    msgs = conv.get("消息") or []
    buyer_text = " ".join(m.get("内容", "") for m in msgs if m.get("角色") == "买家") or \
        " ".join(m.get("内容", "") for m in msgs)
    category, cat_hits = classify(buyer_text)
    emo, emo_hits = emotion(buyer_text)
    signals = escalate_signals(buyer_text)
    level = route(category, emo, signals)

    summary = (
        f"[{conv.get('会话ID','')}] 主诉「{category}」，情绪 {EMOTION_LEVEL[emo]}；"
        f"命中升级信号：{'、'.join(signals) if signals else '无'}；"
        f"路由至{level}；接管时限 {SLA[level]['接管']}，方案时效 {SLA[level]['方案时效']}。"
    )
    return {
        "会话ID": conv.get("会话ID", ""),
        "买家": conv.get("买家", ""),
        "订单金额": conv.get("订单金额", ""),
        "主分类": category,
        "分类命中词": "、".join(cat_hits),
        "情绪等级": EMOTION_LEVEL[emo],
        "升级信号": "、".join(signals) if signals else "",
        "分流层级": level,
        "接管时限": SLA[level]["接管"],
        "方案时效": SLA[level]["方案时效"],
        "交接摘要": summary,
    }


def build(payload: dict, outdir: str) -> dict:
    convs = payload.get("conversations") or []
    if not convs:
        at.emit({"error": "缺少 conversations（会话数组）"})
        sys.exit(1)

    rows = [analyze(c) for c in convs]
    cat_cnt, level_cnt, sig_rows = {}, {}, []
    for r in rows:
        cat_cnt[r["主分类"]] = cat_cnt.get(r["主分类"], 0) + 1
        level_cnt[r["分流层级"]] = level_cnt.get(r["分流层级"], 0) + 1
        if r["升级信号"]:
            sig_rows.append({"会话ID": r["会话ID"], "买家": r["买家"],
                             "升级信号": r["升级信号"], "分流层级": r["分流层级"]})

    total = len(rows)
    three = sum(1 for r in rows if r["分流层级"] == "三线（主管）")
    summary = {
        "会话总数": total,
        "一线自助": level_cnt.get("一线自助", 0),
        "二线人工": level_cnt.get("二线人工", 0),
        "三线（主管）": three,
        "需人工介入合计": level_cnt.get("二线人工", 0) + three,
        "人工介入占比": f"{(level_cnt.get('二线人工', 0) + three) / total * 100:.1f}%" if total else "0%",
        "触发升级信号数": len(sig_rows),
    }
    cat_rows = [{"主分类": k, "会话数": v, "占比": f"{v / total * 100:.1f}%"}
                for k, v in sorted(cat_cnt.items(), key=lambda x: -x[1])]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "分流台账.xlsx"),
        {
            "分流台账": rows,
            "分类分布": cat_rows,
            "SLA对照": [{"分流层级": k, **v} for k, v in SLA.items()],
            "升级信号明细": sig_rows or [{"会话ID": "（无升级信号）", "买家": "", "升级信号": "", "分流层级": ""}],
        },
        highlights={"分流台账": {"分流层级": "contains:三线"}},
        widths={"分流台账": {"交接摘要": 60, "分类命中词": 22},
                "升级信号明细": {"升级信号": 24}},
    )
    png = at.bar_chart(
        os.path.join(outdir, "分流层级分布.png"),
        list(level_cnt.keys()), list(level_cnt.values()),
        title="会话分流层级分布", ylabel="会话数",
    )
    js = at.write_json({"summary": summary, "routes": rows, "signals": sig_rows,
                        "generated_at": at.stamp(),
                        "note": "分类/情绪/升级判定为脚本结果；交接摘要润色与安抚措辞由模型按 prompt.txt 完成"},
                       os.path.join(outdir, "handoff.json"))
    return {"files": [xlsx, png, js], "summary": summary}


def _c(cid, buyer, msgs, amount=None):
    d = {"会话ID": cid, "买家": buyer, "消息": msgs}
    if amount is not None:
        d["订单金额"] = amount
    return d


DEMO = {
    "conversations": [
        _c("C-1001", "买家A", [{"角色": "买家", "内容": "请问什么时候发货呀，等了三天了"}], 199),
        _c("C-1002", "买家B", [{"角色": "买家", "内容": "收到的杯子是破损的，杯身裂了，太失望了"}], 89),
        _c("C-1003", "买家C", [{"角色": "买家", "内容": "鞋子尺码偏小，穿不下，能换大一号吗"}], 259),
        _c("C-1004", "买家D", [{"角色": "买家", "内容": "能开发票吗，需要专用发票报销"}], 1299),
        _c("C-1005", "买家E", [{"角色": "买家", "内容": "我要退款，这个耳机左耳没声音，太差了，再不处理我就投诉到12315！"}], 399),
        _c("C-1006", "买家F", [{"角色": "买家", "内容": "刚买就降价了，能补差价吗"}], 599),
        _c("C-1007", "买家G", [{"角色": "买家", "内容": "你们这个垃圾客服什么意思？敷衍我两天了，我要曝光你们、给差评！"}], 159),
        _c("C-1008", "买家H", [{"角色": "买家", "内容": "这个充电宝可以带上飞机吗"}], 129),
        _c("C-1009", "买家I", [{"角色": "买家", "内容": "包裹显示超区退回了，怎么办"}]),
        _c("C-1010", "买家J", [{"角色": "买家", "内容": "东西掉色严重，色差也大，跟图片完全不一样，很生气"}], 79),
    ]
}


def main():
    ap = argparse.ArgumentParser(description="转人工分流 —— 分类/情绪/升级判定与路由")
    ap.add_argument("--input", help="输入 JSON（conversations）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    payload = DEMO if a.demo else (at.read_json(a.input) if a.input
                                   else ap.error("需要 --input 或 --demo"))
    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"分流完成：会话 {s['会话总数']} 条，一线自助 {s['一线自助']}，"
          f"二线人工 {s['二线人工']}，三线主管 {s['三线（主管）']}，"
          f"人工介入占比 {s['人工介入占比']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
