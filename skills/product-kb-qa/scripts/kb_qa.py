# -*- coding: utf-8 -*-
"""
商品知识库问答 —— 店铺 FAQ 检索匹配器。

职责边界：本脚本只做**确定性检索与产物生成**（字符 bigram Jaccard + 标签字符覆盖度打分，
机器做得出、可复现）。自然语言组织、口径润色、多轮追问由模型按 prompt.txt 完成。

用法：
  python kb_qa.py --input input.json --outdir out
  python kb_qa.py --demo                       # 用内置样例跑一遍
  python kb_qa.py --question "什么时候发货" --kb kb.json

产物：
  out/知识库问答结果.xlsx   问答结果 / 知识缺口 / 类目命中分布
  out/类目命中分布.png      各类目命中数量柱状图
  out/kb_qa.json           机器可读结果（供智能体读取，含 summary）
"""
from __future__ import annotations

import argparse
import os
import re
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


# ---------------------------------------------------------------- 检索打分
# 命中阈值（可被 payload['min_score'] 覆盖）
DEFAULT_MIN_SCORE = 0.35

_PUNCT = re.compile(r"[\s，。！？、,.!?;；:：\"'“”‘’()（）\[\]【】\-—_~·]+")


def normalize(text: str) -> str:
    return _PUNCT.sub("", str(text or "")).lower()


def bigrams(text: str) -> set:
    s = normalize(text)
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def keyword_best(question: str, keywords) -> float:
    """最优标签匹配：取「命中字数 / 标签字数」最高的标签（容忍语序与语气词）。"""
    q = set(normalize(question))
    best = 0.0
    for kw in keywords or []:
        chars = [c for c in normalize(kw) if c]
        if chars:
            best = max(best, sum(1 for c in chars if c in q) / len(chars))
    return best


def score_entry(question: str, entry: dict) -> float:
    """0.55 * 最优标签匹配 + 0.45 * 问题字面 bigram Jaccard。"""
    kws = entry.get("关键词") or []
    cov = keyword_best(question, kws)
    jac = jaccard(bigrams(question),
                  bigrams(str(entry.get("问题", "")) + "".join(map(str, kws))))
    return round(0.55 * cov + 0.45 * jac, 3)


def confidence(score: float, min_score: float) -> str:
    if score < min_score:
        return "未命中"
    if score >= 0.62:
        return "高"
    if score >= 0.45:
        return "中"
    return "低"


def retrieve(question: str, kb: list, min_score: float = DEFAULT_MIN_SCORE) -> dict:
    ranked = sorted(
        ({"条目": e, "匹配度": score_entry(question, e)} for e in kb),
        key=lambda x: x["匹配度"], reverse=True,
    )
    best = ranked[0] if ranked else {"条目": {}, "匹配度": 0.0}
    conf = confidence(best["匹配度"], min_score)
    return {
        "命中条目ID": best["条目"].get("id", ""),
        "知识类目": best["条目"].get("类目", ""),
        "匹配度": best["匹配度"],
        "置信度": conf,
        "是否命中": conf != "未命中",
        "标准答复": best["条目"].get("答案", "") if conf != "未命中" else "",
        "最相近条目": best["条目"].get("问题", ""),
        "候选2": ranked[1]["条目"].get("问题", "") if len(ranked) > 1 else "",
        "候选2匹配度": ranked[1]["匹配度"] if len(ranked) > 1 else 0.0,
    }


# ---------------------------------------------------------------- 主流程

def build(payload: dict, outdir: str) -> dict:
    kb = payload.get("kb") or []
    questions = payload.get("questions") or []
    min_score = float(payload.get("min_score", DEFAULT_MIN_SCORE))
    if not kb:
        at.emit({"error": "缺少 kb（知识库条目）"})
        sys.exit(1)

    rows, gaps = [], []
    cat_hit = {}
    for i, q in enumerate(questions, start=1):
        text = q.get("问题", "") if isinstance(q, dict) else str(q)
        buyer = q.get("买家", f"买家{i}") if isinstance(q, dict) else f"买家{i}"
        r = retrieve(text, kb, min_score)
        rows.append({
            "#": i, "买家": buyer, "买家问题": text,
            "是否命中": "✅" if r["是否命中"] else "❌",
            "知识类目": r["知识类目"], "匹配度": r["匹配度"], "置信度": r["置信度"],
            "命中条目ID": r["命中条目ID"], "标准答复": r["标准答复"],
        })
        if r["是否命中"]:
            cat_hit[r["知识类目"]] = cat_hit.get(r["知识类目"], 0) + 1
        else:
            gaps.append({
                "买家问题": text,
                "最相近条目": r["最相近条目"],
                "最高匹配度": r["匹配度"],
                "缺口类型": "知识库无对应条目" if r["匹配度"] < 0.15 else "匹配度不足，需人工确认口径",
            })

    total = len(rows)
    hit = sum(1 for r in rows if r["是否命中"] == "✅")
    cat_rows = [{"知识类目": k, "命中数": v,
                 "占比": f"{v / hit * 100:.1f}%" if hit else "0%"}
                for k, v in sorted(cat_hit.items(), key=lambda x: -x[1])]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "知识库问答结果.xlsx"),
        {
            "问答结果": rows or [{"买家问题": "（无）"}],
            "知识缺口": gaps or [{"买家问题": "（无缺口）", "最相近条目": "", "最高匹配度": "", "缺口类型": ""}],
            "类目命中分布": cat_rows or [{"知识类目": "（无）"}],
        },
        highlights={"问答结果": {"是否命中": "contains:❌"}},
        widths={"问答结果": {"买家问题": 26, "标准答复": 46, "最相近条目": 30},
                "知识缺口": {"买家问题": 26, "最相近条目": 30, "缺口类型": 26}},
    )
    png = at.bar_chart(
        os.path.join(outdir, "类目命中分布.png"),
        [r["知识类目"] for r in cat_rows] or ["（无命中）"],
        [r["命中数"] for r in cat_rows] or [0],
        title="知识库命中 · 类目分布", ylabel="命中数",
    )
    summary = {
        "问题总数": total, "命中数": hit, "未命中数": total - hit,
        "命中率": f"{hit / total * 100:.1f}%" if total else "0%",
        "命中阈值": min_score,
        "涉及类目数": len(cat_hit),
    }
    js = at.write_json({"summary": summary, "results": rows, "gaps": gaps,
                        "generated_at": at.stamp(),
                        "note": "bigram+标签打分结果；口径润色与多轮追问须由模型按 prompt.txt 复核"},
                       os.path.join(outdir, "kb_qa.json"))
    return {"files": [xlsx, png, js], "summary": summary}


DEMO = {
    "min_score": 0.35,
    "kb": [
        {"id": "KB-01", "类目": "售后-退换", "问题": "支持七天无理由退货吗",
         "关键词": ["七天无理由", "无理由退货", "退货"],
         "答案": "支持。签收后 7 天内，商品不影响二次销售即可无理由退货；请在订单页发起申请。"},
        {"id": "KB-02", "类目": "售后-退换", "问题": "退货运费谁承担",
         "关键词": ["运费谁", "退货运费", "运费"],
         "答案": "质量问题由店铺承担来回运费；非质量问题的无理由退货，运费由买家承担。"},
        {"id": "KB-03", "类目": "物流", "问题": "多久发货",
         "关键词": ["多久发货", "什么时候发货", "发货时间"],
         "答案": "现货商品 48 小时内发出；预售商品按商详页标注时间发出，超时您可申请赔付。"},
        {"id": "KB-04", "类目": "物流", "问题": "用什么快递",
         "关键词": ["什么快递", "物流公司", "快递"],
         "答案": "默认中通/圆通；新疆、西藏等偏远地区改发 EMS，可在订单页查看运单号。"},
        {"id": "KB-05", "类目": "质量", "问题": "耳机有杂音怎么办",
         "关键词": ["杂音", "电流声", "异响"],
         "答案": "请先排除周边信号干扰并重新配对；若仍存在，签收 7 天内可申请换新。"},
        {"id": "KB-06", "类目": "参数", "问题": "蓝牙耳机续航多久",
         "关键词": ["续航", "充电", "电量", "能用多久"],
         "答案": "单次充电续航 8 小时，配合充电仓总续航 30 小时；充电 1.5 小时可充满。"},
        {"id": "KB-07", "类目": "参数", "问题": "充电宝能带上飞机吗",
         "关键词": ["带上飞机", "飞机", "民航"],
         "答案": "20000mAh 约 74Wh，低于民航 100Wh 上限，可随身携带，不可托运。"},
        {"id": "KB-08", "类目": "价格", "问题": "有没有优惠券",
         "关键词": ["优惠券", "优惠", "满减", "领券"],
         "答案": "关注店铺领 5 元无门槛券；满 199 减 20、满 299 减 40，可与平台大促券叠加。"},
        {"id": "KB-09", "类目": "发票", "问题": "能开专票吗",
         "关键词": ["专票", "专用发票", "开发票", "税号"],
         "答案": "支持增值税普通发票与专用发票，下单时在备注留下公司名称、税号与邮箱。"},
        {"id": "KB-10", "类目": "尺码", "问题": "保温杯容量怎么选",
         "关键词": ["容量", "多少毫升", "买多大"],
         "答案": "350ml 适合办公通勤，500ml 适合出行；杯口 4.5cm，可放普通冰块。"},
        {"id": "KB-11", "类目": "售后-退换", "问题": "拆封后还能退吗",
         "关键词": ["拆封", "拆开", "开封"],
         "答案": "不影响二次销售可退；密封、贴肤类商品拆封后不支持无理由退货。"},
        {"id": "KB-12", "类目": "质量", "问题": "收到货破损怎么办",
         "关键词": ["破损", "坏了", "裂了", "磕碰"],
         "答案": "请拍照留证并在签收 24 小时内联系客服，可申请补发或退款，来回运费由店铺承担。"},
        {"id": "KB-13", "类目": "售后-退换", "问题": "退款多久到账",
         "关键词": ["退款到账", "多久到账", "退款时间"],
         "答案": "退款审核通过后 1-3 个工作日退回原支付渠道，以各平台到账时效为准。"},
    ],
    "questions": [
        {"买家": "买家A", "问题": "耳机充一次电能用多久？"},
        {"买家": "买家B", "问题": "我要退货，运费谁出？"},
        {"买家": "买家C", "问题": "什么时候发货啊，等好久了"},
        {"买家": "买家D", "问题": "这个充电宝可以带上飞机吗"},
        {"买家": "买家E", "问题": "收到货是破损的，怎么办"},
        {"买家": "买家F", "问题": "能开发票吗，我们公司要专用发票"},
        {"买家": "买家G", "问题": "有没有优惠可以领"},
        {"买家": "买家H", "问题": "支持七天无理由吗"},
        {"买家": "买家I", "问题": "你们发什么快递"},
        {"买家": "买家J", "问题": "退款要几天才能到账"},
        {"买家": "买家K", "问题": "耳机左耳没声音了，是不是坏了"},
        {"买家": "买家L", "问题": "可以帮我定制刻字吗"},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="商品知识库问答 —— 店铺 FAQ 检索匹配")
    ap.add_argument("--input", help="输入 JSON（kb / questions / min_score）")
    ap.add_argument("--question", help="直接传单个问题")
    ap.add_argument("--kb", help="知识库 JSON 文件（配合 --question 使用）")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true", help="用内置样例跑一遍")
    a = ap.parse_args()

    if a.demo:
        payload = DEMO
    elif a.input:
        payload = at.read_json(a.input)
    elif a.question:
        kb = at.read_json(a.kb) if a.kb else DEMO["kb"]
        payload = {"kb": kb, "questions": [{"买家": "买家", "问题": a.question}]}
    else:
        ap.error("需要 --input / --question / --demo 之一")

    r = build(payload, a.outdir)
    s = r["summary"]
    print(f"检索完成：问题 {s['问题总数']} 条，命中 {s['命中数']} 条（命中率 {s['命中率']}），"
          f"缺口 {s['未命中数']} 条")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
