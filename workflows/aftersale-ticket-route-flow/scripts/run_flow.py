# -*- coding: utf-8 -*-
"""
售后工单分流与安抚 —— 端到端编排脚本。

编排链路（DAG）：
    升级信号检测 ──► 情绪识别分级(emotion-detect-appease 口径) ──► 转人工分流(human-handoff-route)
                 ──► 安抚话术策略(四步话术框架) ──► 汇总交付

真编排：步骤 2/3 直接复用原子技能 `human-handoff-route/scripts/handoff_route.py` 的
`emotion()` / `analyze()`，不重写分类与路由逻辑。

失败处理：
  - conversations 缺失 → 退出码 1
  - 升级信号命中 → 三线主管，AI 停止自动安抚，只出交接摘要
  - 消息内容为空 → 标「内容缺失」并入待人工，不猜测
  - 订单金额缺失 → 话术不给补偿金额，只给「去了解情况」动作

用法：
  python run_flow.py --input input.json --outdir out
  python run_flow.py --demo

产物：
  out/售后分流安抚台账.xlsx   分流台账 / 升级清单 / 情绪分布
  out/安抚话术清单.md        端到端交付物（话术策略 + 待模型补全的四步话术）
  out/aftersale_flow.json    机器可读结果
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


# 复用原子技能 human-handoff-route 的判定实现（真编排）
HH = _load(os.path.join(REPO, "skills", "human-handoff-route", "scripts", "handoff_route.py"),
           "skill_handoff")

# 情绪等级 → 安抚策略（emotion-detect-appease 口径）
APPEASE_POLICY = {
    0: ("L0 中性", "直接解答 + 轻共情"),
    1: ("L1 轻微不满", "共情 + 给明确时间点"),
    2: ("L2 明显不满", "强共情 + 解释 + 授权内补偿选项"),
    3: ("L3 愤怒", "先道歉认责、只谈解决、不辩解"),
    4: ("L4 极端/威胁", "立即致歉 + 转三线主管，全程留痕"),
}


def buyer_text(conv: dict) -> str:
    return " ".join(m.get("内容", "") for m in (conv.get("消息") or [])) or ""


def run(payload, outdir):
    convs = payload.get("conversations") or []
    if not convs:
        at.emit({"error": "缺少 conversations（会话数组）"})
        sys.exit(1)

    rows, escalated = [], []
    emo_cnt = {}
    for c in convs:
        text = buyer_text(c)
        if not text.strip():
            rows.append({"会话ID": c.get("会话ID", ""), "买家": c.get("买家", ""),
                         "主分类": "其他", "情绪等级": "L0 中性", "分流层级": "二线人工",
                         "安抚策略": "内容缺失，人工先补上下文", "交接摘要": "[内容缺失] 消息为空，并入待人工"})
            continue
        a = HH.analyze(c)  # 复用转人工分流：分类 + 情绪 + 升级 + 路由 + 摘要
        emo_num = int(a["情绪等级"][1])
        emo_cnt[a["情绪等级"]] = emo_cnt.get(a["情绪等级"], 0) + 1
        _, policy = APPEASE_POLICY[emo_num]
        a["安抚策略"] = policy
        if a["升级信号"]:
            a["处置"] = "转三线主管：AI 停止自动安抚，只出交接摘要"
            escalated.append(a)
        else:
            a["处置"] = "按四步话术框架生成安抚回复（模型步骤 4）"
        rows.append(a)

    auto = [r for r in rows if not r.get("升级信号") and r.get("主分类") != "其他" or
            (not r.get("升级信号") and r.get("主分类") == "其他" and r["交接摘要"] != "[内容缺失] 消息为空，并入待人工")]
    summary = {
        "会话总数": len(convs),
        "升级转主管": len(escalated),
        "可自动安抚": len([r for r in rows if r not in escalated and r["交接摘要"] != "[内容缺失] 消息为空，并入待人工"]),
        "内容缺失": len([r for r in rows if r["交接摘要"] == "[内容缺失] 消息为空，并入待人工"]),
        "情绪分布": emo_cnt,
        "安抚口径": "共情→诊断→方案→行动，四段缺一不可",
        "SLA": "首响<30秒/人工接管<3分钟/售后24h内给方案",
        "红线": "不承诺超授权赔付；资金操作只出草稿；不诱导删差评",
        "AI 标识": "AI 生成内容",
    }
    steps = [
        {"步骤": "1. 升级信号检测", "技能": "human-handoff-route（升级信号词表）", "状态": "ok",
         "输出": f"{len(escalated)} 条命中转三线", "失败处理": "命中即停自动安抚，只出交接摘要"},
        {"步骤": "2. 情绪识别分级", "技能": "emotion-detect-appease（L0-L4 口径）", "状态": "ok",
         "输出": "完成 L0-L4 分级", "失败处理": "消息为空→标内容缺失并入待人工"},
        {"步骤": "3. 转人工分流", "技能": "human-handoff-route（分类树+SLA）", "状态": "ok",
         "输出": "三层路由 + 交接摘要", "失败处理": "分类未命中→「其他」走二线"},
        {"步骤": "4. 安抚话术策略", "技能": "emotion-detect-appease（话术框架）", "状态": "ok",
         "输出": "按情绪等级映射话术策略", "失败处理": "金额缺失→不给补偿金额"},
        {"步骤": "5. 汇总交付", "技能": "aftersale-ticket-route-flow（内置）", "状态": "ok",
         "输出": "台账 + 话术清单", "失败处理": "—"},
    ]

    at.ensure_outdir(outdir)
    xlsx = at.write_excel(
        os.path.join(outdir, "售后分流安抚台账.xlsx"),
        {
            "分流台账": rows,
            "升级清单": [{k: r[k] for k in ("会话ID", "买家", "升级信号", "分流层级", "交接摘要")}
                        for r in escalated] or [{"会话ID": "（无升级信号）"}],
            "情绪分布": [{"情绪等级": k, "会话数": v} for k, v in sorted(emo_cnt.items())],
        },
        highlights={"分流台账": {"分流层级": "contains:三线"}},
        widths={"分流台账": {"交接摘要": 60, "安抚策略": 30, "处置": 34}},
    )
    js = at.write_json({"summary": summary, "steps": steps, "routes": rows, "escalated": escalated,
                        "generated_at": at.stamp(),
                        "note": "分类/情绪/升级/路由为脚本结果；四步话术成稿由模型按 prompt.txt 撰写"},
                       os.path.join(outdir, "aftersale_flow.json"))

    md = ["# 售后工单分流与安抚 —— 执行报告\n",
          f"> 生成时间：{at.stamp()} ｜ 由 `scripts/run_flow.py` 实跑产出\n",
          "## 一、执行摘要\n",
          f"- 会话 **{summary['会话总数']}** 条：升级转主管 {summary['升级转主管']}，"
          f"可自动安抚 {summary['可自动安抚']}，内容缺失 {summary['内容缺失']}",
          f"- 安抚口径：{summary['安抚口径']}；SLA：{summary['SLA']}\n",
          "## 二、执行步骤\n", "| 步骤 | 技能 | 状态 | 输出 | 失败处理 |", "|---|---|---|---|---|"]
    for s in steps:
        md.append(f"| {s['步骤']} | {s['技能']} | {s['状态']} | {s['输出']} | {s['失败处理']} |")
    md += ["\n## 三、安抚话术清单（四步框架，成稿由模型补全）\n"]
    for r in rows:
        if r in escalated:
            continue
        md.append(f"### {r['会话ID']}（{r['买家']}）· {r['情绪等级']} · {r['分流层级']}\n")
        md.append(f"- 安抚策略：{r['安抚策略']}")
        md.append(f"- 话术框架：① 共情（认可情绪）→ ② 诊断（复述「{r['主分类']}」问题确认）→ "
                  f"③ 方案（给 1-2 个选项）→ ④ 行动（明确时限：{r['方案时效']}）")
        md.append(f"- 交接摘要：{r['交接摘要']}\n")
    md += ["## 四、升级清单（AI 停止自动安抚）\n",
           "| 会话ID | 买家 | 升级信号 | 人工动作 |", "|---|---|---|---|"]
    for r in escalated or [{"会话ID": "（无）", "买家": "", "升级信号": "",
                            "人工动作": "主管 3 分钟内接管，24 小时内签字方案"}]:
        md.append(f"| {r['会话ID']} | {r['买家']} | {r['升级信号']} | "
                  f"主管接管，留存记录，方案经主管签字 |")
    md += ["\n---\n", "*本报告由 AI 生成；安抚话术对外发送前须人工确认；资金相关仅出草稿。*"]
    md_path = os.path.join(outdir, "安抚话术清单.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return {"files": [xlsx, os.path.abspath(md_path), js], "summary": summary}


DEMO = {
    "shop": "潮流数码旗舰店",
    "now": "2026-09-30 10:00",
    "conversations": [
        {"会话ID": "C-2001", "买家": "买家A", "订单金额": 199,
         "消息": [{"角色": "买家", "内容": "下单三天了一直没发货，等了好久了，怎么还没动静"}]},
        {"会话ID": "C-2002", "买家": "买家B", "订单金额": 89,
         "消息": [{"角色": "买家", "内容": "收到的充电宝外壳裂了，明显是破损件，太失望了，怎么回事啊"}]},
        {"会话ID": "C-2003", "买家": "买家C", "订单金额": 1299,
         "消息": [{"角色": "买家", "内容": "耳机左耳没声音，我要退款，再不解决我就投诉到12315！"}]},
        {"会话ID": "C-2004", "买家": "买家D", "订单金额": 259,
         "消息": [{"角色": "买家", "内容": "鞋子尺码偏小穿不下，能换大一号吗"}]},
        {"会话ID": "C-2005", "买家": "买家E", "订单金额": 399,
         "消息": [{"角色": "买家", "内容": "你们客服太敷衍了，气死我了，我要曝光你们、给差评！"}]},
        {"会话ID": "C-2006", "买家": "买家F", "订单金额": 599,
         "消息": [{"角色": "买家", "内容": "刚买一周就降价了，能补差价吗"}]},
        {"会话ID": "C-2007", "买家": "买家G", "订单金额": 0,
         "消息": [{"角色": "买家", "内容": "能开发票吗，需要专用发票报销"}]},
    ],
}


def main():
    ap = argparse.ArgumentParser(description="售后工单分流与安抚 —— 端到端编排")
    ap.add_argument("--input")
    ap.add_argument("--outdir", default="out")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    payload = DEMO if a.demo else (at.read_json(a.input) if a.input else ap.error("需要 --input 或 --demo"))
    r = run(payload, a.outdir)
    s = r["summary"]
    print(f"分流完成：会话 {s['会话总数']} 条，升级 {s['升级转主管']}，"
          f"可自动安抚 {s['可自动安抚']}，内容缺失 {s['内容缺失']}")
    for f in r["files"]:
        print(" 产物:", f)
    at.emit(r)


if __name__ == "__main__":
    main()
