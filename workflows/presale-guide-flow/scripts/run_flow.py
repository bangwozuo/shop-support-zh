# -*- coding: utf-8 -*-
"""
售前智能导购 —— 端到端编排脚本。

编排链路（DAG）：
    product-kb-qa（商品知识库问答） ──► price-negotiation-script（议价话术） ──► 汇总交付

本脚本按「意图识别 → 知识库检索 → 议价判定 → 汇总」四步真实串联，
直接复用原子技能 `product-kb-qa/scripts/kb_qa.py` 的检索函数（真编排，非重写）。

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/售前导购台账.xlsx   导购台账 / 意图分布 / 知识缺口
  out/售前导购报告.md     端到端交付物（可直接发给店长）
  out/presale_flow.json   分步执行明细 + 摘要
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import sys

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


# 复用原子技能 product-kb-qa 的检索实现（真编排）
KBQA = _load(os.path.join(REPO, "skills", "product-kb-qa", "scripts", "kb_qa.py"), "skill_kb_qa")

# 意图识别词表（售前）
INTENT_RULES = [
    ("议价", ["便宜", "优惠", "降价", "抹零", "贵", "打折", "补贴", "差价", "更划算", "包邮"]),
    ("物流", ["发货", "物流", "快递", "几天到", "什么时候到", "运单"]),
    ("售后", ["退货", "退款", "换货", "保修", "质保", "坏了"]),
    ("商品咨询", ["吗", "什么", "怎么", "可以", "支持", "能用", "多大", "多久", "区别", "参数", "材质"]),
]

# 议价让步档位（与 price-negotiation-script prompt.txt 一致）
def price_band(amount):
    if amount is None:
        return {"档位": "未知金额", "一线自主": "赠品/包邮", "二线审批": "—", "升级": "需订单金额才能定档"}
    a = float(amount)
    if a < 50:
        return {"档位": "<50 元", "一线自主": "抹零 / 送 1 件赠品", "二线审批": "1–3 元券", "升级": "超 3 元让价"}
    if a <= 200:
        return {"档位": "50–200 元", "一线自主": "活动券 + 包邮 + 赠品", "二线审批": "让价 ≤ 5%", "升级": "让价 > 5%"}
    return {"档位": ">200 元", "一线自主": "活动券 + 赠品 + 包邮", "二线审批": "让价 ≤ 8%", "升级": "让价 > 8%"}


def classify_intent(text):
    for intent, kws in INTENT_RULES:
        if any(k in text for k in kws):
            return intent
    return "其他"


def run(payload, outdir):
    kb = payload.get("kb") or []
    buyers = payload.get("buyers") or []
    min_score = float(payload.get("min_score", 0.35))
    if not kb or not buyers:
        at.emit({"error": "缺少 kb 或 buyers"})
        sys.exit(1)

    steps = []
    rows, gaps = [], []
    intent_cnt = {}

    for i, b in enumerate(buyers, start=1):
        q = b.get("问题", "")
        amount = b.get("订单金额")
        # 步骤 1：意图识别
        intent = classify_intent(q)
        intent_cnt[intent] = intent_cnt.get(intent, 0) + 1
        # 步骤 2：知识库检索（调用 product-kb-qa）
        r = KBQA.retrieve(q, kb, min_score)
        answer = r["标准答复"] if r["是否命中"] else ""
        if not r["是否命中"]:
            gaps.append({"买家问题": q, "最相近条目": r["最相近条目"], "最高匹配度": r["匹配度"]})
        # 步骤 3：议价判定（调用议价档位）
        band = price_band(amount) if intent == "议价" else None
        rows.append({
            "#": i, "买家": b.get("买家", f"买家{i}"), "买家问题": q,
            "意图": intent, "订单金额": amount if amount is not None else "",
            "知识条目": r["命中条目ID"] if r["是否命中"] else "未命中",
            "匹配度": r["匹配度"], "置信度": r["置信度"],
            "标准答复": answer,
            "议价档位": band["档位"] if band else "—",
            "议价处置": (f"一线自主：{band['一线自主']}；二线：{band['二线审批']}；升{band['升级']}"
                        if band else "—"),
        })

    steps = [
        {"步骤": "1. 意图识别", "技能": "presale-guide-flow（内置规则）", "状态": "ok",
         "输出": f"识别 {len(buyers)} 条咨询意图", "失败处理": "无法归类→标「其他」，仍继续"},
        {"步骤": "2. 商品知识库问答", "技能": "product-kb-qa", "状态": "ok",
         "输出": f"命中 {len(rows) - len(gaps)} 条 / 缺口 {len(gaps)} 条", "失败处理": "未命中→记知识缺口，不编答案"},
        {"步骤": "3. 议价话术判定", "技能": "price-negotiation-script", "状态": "ok",
         "输出": f"议价类 {intent_cnt.get('议价', 0)} 条已配让步档位", "失败处理": "缺金额→标「未知金额」，转人工定档"},
        {"步骤": "4. 汇总交付", "技能": "presale-guide-flow（内置）", "状态": "ok",
         "输出": "导购台账 + 报告", "失败处理": "—"},
    ]

    hit = len(rows) - len(gaps)
    summary = {
        "咨询总数": len(rows), "知识命中": hit, "知识缺口": len(gaps),
        "命中率": f"{hit / len(rows) * 100:.1f}%" if rows else "0%",
        "议价条数": intent_cnt.get("议价", 0),
        "意图分布": intent_cnt,
    }
    intent_rows = [{"意图": k, "条数": v, "占比": f"{v / len(rows) * 100:.1f}%"}
                   for k, v in sorted(intent_cnt.items(), key=lambda x: -x[1])]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "售前导购台账.xlsx"),
        {"导购台账": rows, "意图分布": intent_rows,
         "知识缺口": gaps or [{"买家问题": "（无缺口）", "最相近条目": "", "最高匹配度": ""}]},
        widths={"导购台账": {"买家问题": 26, "标准答复": 44, "议价处置": 44}},
    )
    js = at.write_json({"summary": summary, "steps": steps, "rows": rows, "gaps": gaps,
                        "generated_at": at.stamp()},
                       os.path.join(outdir, "presale_flow.json"))

    md = [f"# 售前导购执行报告\n", f"> 生成时间：{at.stamp()} ｜ 由 `scripts/run_flow.py` 实跑产出\n",
          "## 一、执行摘要\n",
          f"- 咨询总数：**{summary['咨询总数']}**，知识命中 **{hit}**（命中率 {summary['命中率']}），"
          f"知识缺口 **{len(gaps)}**",
          f"- 议价类咨询：**{summary['议价条数']}** 条，已按订单金额匹配让步档位\n",
          "## 二、执行步骤\n", "| 步骤 | 技能 | 状态 | 输出 | 失败处理 |", "|---|---|---|---|---|"]
    for s in steps:
        md.append(f"| {s['步骤']} | {s['技能']} | {s['状态']} | {s['输出']} | {s['失败处理']} |")
    md += ["\n## 三、导购明细\n", "| # | 买家 | 问题 | 意图 | 知识条目 | 匹配度 | 议价档位 |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        md.append(f"| {r['#']} | {r['买家']} | {r['买家问题']} | {r['意图']} | {r['知识条目']} | {r['匹配度']} | {r['议价档位']} |")
    md += ["\n## 四、知识缺口（需补录）\n"]
    if gaps:
        md.append("| 买家问题 | 最相近条目 | 最高匹配度 |")
        md.append("|---|---|---|")
        for g in gaps:
            md.append(f"| {g['买家问题']} | {g['最相近条目']} | {g['最高匹配度']} |")
    else:
        md.append("（无）")
    md += ["\n---\n", "*本报告由 AI 生成；应答口径与让价幅度须人工复核后对外。*"]
    md_path = os.path.join(outdir, "售前导购报告.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")

    return {"files": [xlsx, os.path.abspath(md_path), js], "summary": summary}


DEMO = {
    "min_score": 0.35,
    "kb": [
        {"id": "KB-06", "类目": "参数", "问题": "蓝牙耳机续航多久",
         "关键词": ["续航", "充电", "电量", "能用多久"],
         "答案": "单次充电续航 8 小时，配合充电仓总续航 30 小时；充电 1.5 小时可充满。"},
        {"id": "KB-07", "类目": "参数", "问题": "充电宝能带上飞机吗",
         "关键词": ["带上飞机", "飞机", "民航"],
         "答案": "20000mAh 约 74Wh，低于民航 100Wh 上限，可随身携带，不可托运。"},
        {"id": "KB-10", "类目": "尺码", "问题": "保温杯容量怎么选",
         "关键词": ["容量", "多少毫升", "买多大"],
         "答案": "350ml 适合办公通勤，500ml 适合出行；杯口 4.5cm，可放普通冰块。"},
        {"id": "KB-08", "类目": "价格", "问题": "有没有优惠券",
         "关键词": ["优惠券", "优惠", "满减", "领券"],
         "答案": "关注店铺领 5 元无门槛券；满 199 减 20、满 299 减 40，可与平台大促券叠加。"},
    ],
    "buyers": [
        {"买家": "买家A", "问题": "这个耳机充一次电能用多久？"},
        {"买家": "买家B", "问题": "充电宝能带上飞机吗"},
        {"买家": "买家C", "问题": "199 能便宜点吗，隔壁更便宜", "订单金额": 199},
        {"买家": "买家D", "问题": "保温杯买多大容量合适"},
        {"买家": "买家E", "问题": "有没有优惠可以领", "订单金额": 89},
        {"买家": "买家F", "问题": "能不能刻名字定制"},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="售前智能导购 —— 端到端编排")
    ap.add_argument("--input", help="输入 JSON（kb / buyers / min_score）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = run(payload, a.outdir)
    s = r["summary"]
    print(f"导购完成：咨询 {s['咨询总数']} 条，命中率 {s['命中率']}，议价 {s['议价条数']} 条")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
