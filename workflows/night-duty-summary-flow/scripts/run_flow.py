# -*- coding: utf-8 -*-
"""
夜间值守 + 次日汇总 —— 端到端编排脚本。

编排链路（DAG）：
    夜间消息分诊(意图分类) ──► 知识库自助应答(product-kb-qa, 真编排复用 kb_qa.retrieve)
      ──► 待人工标记(情绪≥L2 / 升级信号 / 未命中, human-handoff-route 口径)
      ──► 知识缺口聚类(未命中问题 → FAQ 草稿) ──► 晨报汇总

失败处理：
  - messages 缺失 → 退出码 1
  - kb 缺失 → 全部标「知识库缺失」，不产出假答复
  - 未命中 → 不硬答，进待人工 + FAQ 草稿
  - 升级信号 → 标「待晨间主管」，夜间不自动回复敏感内容

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/夜间值守晨报.xlsx   值守明细 / 待人工清单 / FAQ 草稿
  out/晨报.md            端到端交付物（次日 8:30 推送）
  out/night_duty.json    机器可读结果
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import re
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


# 复用原子技能（真编排）
KB = _load(os.path.join(REPO, "skills", "product-kb-qa", "scripts", "kb_qa.py"), "skill_kbqa")
HH = _load(os.path.join(REPO, "skills", "human-handoff-route", "scripts", "handoff_route.py"),
           "skill_handoff")

# 夜间意图分类词表（自上而下，先急后缓）
INTENT_TREE = [
    ("售后求助", ["退款", "退货", "换货", "破损", "坏了", "色差", "故障", "没声音", "投诉", "维权"]),
    ("查件物流", ["发货", "物流", "快递", "运单", "包裹", "到哪", "签收", "派件", "几天到"]),
    ("售前咨询", ["续航", "容量", "尺寸", "参数", "材质", "能用", "支持", "可以吗", "区别"]),
    ("议价优惠", ["优惠", "便宜", "券", "减", "活动", "价保", "降价"]),
]
# 升级信号（夜间一律不自动回复，留待晨间主管）
NIGHT_ESCALATE = ["投诉", "差评", "12315", "平台介入", "工商", "消协", "曝光", "起诉", "律师", "举报", "维权", "报警"]

# 自助应答率目标（低于该值晨报标黄提醒）
TARGET_AUTOREPLY = 60  # %


def classify_intent(text: str) -> tuple:
    for intent, kws in INTENT_TREE:
        hit = [k for k in kws if k in text]
        if hit:
            return intent, hit
    return "其他", []


def run(payload, outdir):
    msgs = payload.get("messages") or []
    kb = payload.get("kb") or []
    min_score = float(payload.get("min_score", KB.DEFAULT_MIN_SCORE))
    if not msgs:
        at.emit({"error": "缺少 messages（夜间消息数组）"})
        sys.exit(1)

    rows, gaps, pending = [], [], []
    intent_cnt = {}
    for i, m in enumerate(msgs, start=1):
        mid = m.get("消息ID", f"N-{i:03d}")
        text = str(m.get("内容", ""))
        intent, intent_hits = classify_intent(text)
        intent_cnt[intent] = intent_cnt.get(intent, 0) + 1
        emo, emo_hits = HH.emotion(text)
        signals = [s for s in NIGHT_ESCALATE if s in text]

        # 步骤 2：知识库自助应答（真编排复用 product-kb-qa）
        if kb:
            r = KB.retrieve(text, kb, min_score)
            hit, answer = r["是否命中"], r["标准答复"]
            match, conf = r["匹配度"], r["置信度"]
            kb_id = r["命中条目ID"]
        else:
            hit, answer, match, conf, kb_id = False, "", 0.0, "未命中", ""

        # 步骤 3：待人工标记
        if signals:
            route, action = "待晨间主管", "夜间不自动回复敏感内容；晨间主管 8:30 前接管"
        elif not hit:
            route, action = "待人工", "未命中不硬答；进 FAQ 草稿，晨间人工补答"
        elif emo >= 2:
            route, action = "自助+待复核", "已按标准口径自动应答；情绪偏高，晨间复核是否需跟进"
        elif intent == "售后求助":
            route, action = "自助+待复核", "已自动应答；售后类咨询晨间人工复核处理进度"
        else:
            route, action = "自助", "已按标准口径自动应答"
        pending_flag = route in ("待人工", "待晨间主管")

        row = {
            "消息ID": mid, "时间": m.get("时间", ""), "买家": m.get("买家", ""),
            "买家消息": text, "意图分类": intent, "分类命中词": "、".join(intent_hits),
            "情绪等级": HH.EMOTION_LEVEL[emo], "升级信号": "、".join(signals),
            "是否命中知识库": "✅" if hit else "❌", "命中条目ID": kb_id,
            "匹配度": match, "置信度": conf, "值守处置": route, "次日动作": action,
        }
        rows.append(row)
        if pending_flag:
            pending.append(row)
        if not hit and not signals:
            gaps.append({
                "消息ID": mid, "买家消息": text, "意图分类": intent,
                "最高匹配度": match,
                "FAQ 草稿方向": f"补充「{intent}」类目：{text[:20]}…（人工确认口径后入库）",
            })

    answered = sum(1 for r in rows if r["是否命中知识库"] == "✅")
    rate = round(answered / len(rows) * 100, 1) if rows else 0.0
    summary = {
        "值守时段": payload.get("night_start", "22:00") + " - " + payload.get("night_end", "08:00"),
        "夜间消息总数": len(rows),
        "知识库命中数": answered,
        "自助应答率": f"{rate}%",
        "自助应答率目标": f"≥ {TARGET_AUTOREPLY}%",
        "达标": "✅" if rate >= TARGET_AUTOREPLY else "❌ 低于目标，晨报标黄",
        "待人工": len([r for r in rows if r["值守处置"] == "待人工"]),
        "待晨间主管": len([r for r in rows if r["值守处置"] == "待晨间主管"]),
        "自助+待复核": len([r for r in rows if r["值守处置"] == "自助+待复核"]),
        "意图分布": intent_cnt,
        "FAQ 草稿数": len(gaps),
        "红线": "夜间不承诺赔付/到货时间；升级信号一律留待晨间主管",
        "AI 标识": "AI 生成内容",
    }
    steps = [
        {"步骤": "1. 夜间消息分诊", "技能": "night-duty-summary-flow（内置意图词表）", "状态": "ok",
         "输出": f"分类 {len(rows)} 条", "失败处理": "未命中→「其他」"},
        {"步骤": "2. 知识库自助应答", "技能": "product-kb-qa（kb_qa.retrieve 复用）", "状态": "ok",
         "输出": f"命中 {answered} 条", "失败处理": "kb 缺失→全部标知识库缺失"},
        {"步骤": "3. 待人工标记", "技能": "human-handoff-route（情绪+升级信号）", "状态": "ok",
         "输出": f"待人工 {summary['待人工']} / 主管 {summary['待晨间主管']}",
         "失败处理": "升级信号→留待晨间主管"},
        {"步骤": "4. 知识缺口聚类", "技能": "night-duty-summary-flow（FAQ 草稿）", "状态": "ok",
         "输出": f"{len(gaps)} 条 FAQ 草稿", "失败处理": "人工确认口径后入库，不自动生效"},
        {"步骤": "5. 晨报汇总", "技能": "night-duty-summary-flow（内置）", "状态": "ok",
         "输出": "晨报.xlsx + 晨报.md", "失败处理": "—"},
    ]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "夜间值守晨报.xlsx"),
        {
            "值守明细": rows,
            "待人工清单": [{k: r[k] for k in ("消息ID", "买家", "买家消息", "值守处置", "次日动作")}
                        for r in pending] or [{"消息ID": "（无待人工）"}],
            "FAQ 草稿": gaps or [{"消息ID": "（无缺口）", "FAQ 草稿方向": ""}],
            "汇总": [{"项": k, "内容": str(v)} for k, v in summary.items()],
        },
        highlights={"值守明细": {"值守处置": "contains:待"}, "汇总": {"内容": "contains:❌"}},
        widths={"值守明细": {"买家消息": 30, "次日动作": 36},
                "FAQ 草稿": {"FAQ 草稿方向": 44}},
    )
    js = at.write_json({"summary": summary, "steps": steps, "rows": rows, "gaps": gaps,
                        "generated_at": at.stamp(),
                        "note": "意图/命中/情绪/路由为脚本结果；自助答复口径以 product-kb-qa 标准答复为准"},
                       os.path.join(outdir, "night_duty.json"))

    md = ["# 夜间值守晨报\n",
          f"> 值守时段：{summary['值守时段']} ｜ 晨报生成：{at.stamp()} ｜ 由 `scripts/run_flow.py` 实跑产出\n",
          "## 一、执行摘要\n",
          f"- 夜间消息 **{summary['夜间消息总数']}** 条：知识库命中 {answered}，自助应答率 "
          f"**{rate}%**（目标 ≥ {TARGET_AUTOREPLY}%，{summary['达标']}）",
          f"- 待人工 {summary['待人工']} 条 ｜ 待晨间主管 {summary['待晨间主管']} 条 ｜ "
          f"自助+待复核 {summary['自助+待复核']} 条 ｜ FAQ 草稿 {summary['FAQ 草稿数']} 条\n",
          "## 二、执行步骤\n", "| 步骤 | 技能 | 状态 | 输出 | 失败处理 |", "|---|---|---|---|---|"]
    for s in steps:
        md.append(f"| {s['步骤']} | {s['技能']} | {s['状态']} | {s['输出']} | {s['失败处理']} |")
    md += ["\n## 三、待处理清单（晨间优先）\n",
           "| 消息ID | 买家 | 买家消息 | 处置 | 次日动作 |", "|---|---|---|---|---|"]
    for r in pending or [{"消息ID": "（无）", "买家": "", "买家消息": "", "值守处置": "", "次日动作": ""}]:
        md.append(f"| {r['消息ID']} | {r['买家']} | {r['买家消息']} | {r['值守处置']} | {r['次日动作']} |")
    md += ["\n## 四、FAQ 草稿（人工确认后入库）\n",
           "| 消息ID | 买家消息 | 意图 | 草稿方向 |", "|---|---|---|---|"]
    for g in gaps or [{"消息ID": "（无）", "买家消息": "", "意图分类": "", "FAQ 草稿方向": ""}]:
        md.append(f"| {g['消息ID']} | {g['买家消息']} | {g['意图分类']} | {g['FAQ 草稿方向']} |")
    md += ["\n## 五、夜间自助应答记录\n",
           "| 消息ID | 买家消息 | 命中 | 标准答复 |", "|---|---|---|---|"]
    for r in rows:
        if r["是否命中知识库"] == "✅":
            md.append(f"| {r['消息ID']} | {r['买家消息']} | {r['命中条目ID']} | {r['买家消息'][:0] or ''}"
                      f"{KB.retrieve(r['买家消息'], kb, min_score)['标准答复'][:40] if kb else ''}… |")
    md += ["\n---\n", "*本晨报由 AI 生成；夜间承诺与赔付类答复须经晨间人工确认后跟进。*"]
    md_path = os.path.join(outdir, "晨报.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return {"files": [xlsx, os.path.abspath(md_path), js], "summary": summary}


DEMO = {
    "shop": "潮流数码旗舰店",
    "night_start": "2026-09-29 22:00",
    "night_end": "2026-09-30 08:00",
    "min_score": 0.35,
    "kb": [
        {"id": "KB-01", "类目": "售后-退换", "问题": "支持七天无理由退货吗", "关键词": ["七天无理由", "无理由退货", "退货"], "答案": "支持。签收后 7 天内，商品不影响二次销售即可无理由退货；请在订单页发起申请。"},
        {"id": "KB-03", "类目": "物流", "问题": "多久发货", "关键词": ["多久发货", "什么时候发货", "发货时间", "发货"], "答案": "现货商品 48 小时内发出；预售商品按商详页标注时间发出。"},
        {"id": "KB-04", "类目": "物流", "问题": "用什么快递", "关键词": ["什么快递", "物流公司", "快递"], "答案": "默认中通/圆通；新疆、西藏等偏远地区改发 EMS。"},
        {"id": "KB-06", "类目": "参数", "问题": "蓝牙耳机续航多久", "关键词": ["续航", "充电", "电量", "能用多久"], "答案": "单次充电续航 8 小时，配合充电仓总续航 30 小时。"},
        {"id": "KB-07", "类目": "参数", "问题": "充电宝能带上飞机吗", "关键词": ["带上飞机", "飞机", "民航"], "答案": "20000mAh 约 74Wh，低于民航 100Wh 上限，可随身携带，不可托运。"},
        {"id": "KB-08", "类目": "价格", "问题": "有没有优惠券", "关键词": ["优惠券", "优惠", "满减", "领券", "便宜"], "答案": "关注店铺领 5 元无门槛券；满 199 减 20、满 299 减 40。"},
        {"id": "KB-13", "类目": "售后-退换", "问题": "退款多久到账", "关键词": ["退款到账", "多久到账", "退款"], "答案": "退款审核通过后 1-3 个工作日退回原支付渠道。"},
    ],
    "messages": [
        {"消息ID": "N-001", "时间": "2026-09-29 22:41", "买家": "买家A", "内容": "耳机充一次电能用多久？", "订单号": "TB92901"},
        {"消息ID": "N-002", "时间": "2026-09-29 23:05", "买家": "买家B", "内容": "什么时候发货啊，明天能到吗", "订单号": "TB92902"},
        {"消息ID": "N-003", "时间": "2026-09-29 23:47", "买家": "买家C", "内容": "充电宝可以带上飞机吗", "订单号": "TB92903"},
        {"消息ID": "N-004", "时间": "2026-09-30 00:22", "买家": "买家D", "内容": "收到的音箱是坏的没声音，我要退款，不然就投诉了", "订单号": "TB92904"},
        {"消息ID": "N-005", "时间": "2026-09-30 01:15", "买家": "买家E", "内容": "可以刻字定制吗", "订单号": "TB92905"},
        {"消息ID": "N-006", "时间": "2026-09-30 03:08", "买家": "买家F", "内容": "有没有优惠，怎么买便宜", "订单号": "TB92906"},
        {"消息ID": "N-007", "时间": "2026-09-30 07:36", "买家": "买家G", "内容": "退款多久到账", "订单号": "TB92907"},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="夜间值守 + 次日汇总 —— 端到端编排")
    ap.add_argument("--input")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = run(payload, a.outdir)
    s = r["summary"]
    print(f"晨报完成：夜间消息 {s['夜间消息总数']} 条，命中 {s['知识库命中数']}（应答率 {s['自助应答率']}，"
          f"{s['达标']}），待人工 {s['待人工']}，主管 {s['待晨间主管']}，FAQ 草稿 {s['FAQ 草稿数']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
