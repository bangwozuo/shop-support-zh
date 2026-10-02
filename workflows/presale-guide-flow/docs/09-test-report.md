# 测试报告

## 一、结构校验

| 项 | 结果 |
|---|---|
| 四件套齐全（SKILL.md / prompt.txt / schema.json / examples） | ✅ PASS |
| SKILL.md 段落齐全 + `composite` 声明 + Mermaid DAG 成对闭合 | ✅ PASS |
| **DAG 引用的原子技能 slug 在同仓真实存在** | ✅ `product-kb-qa` / `price-negotiation-script` 均存在 |
| 步骤明细含「输入 / 处理 / 输出 / 失败处理」 | ✅ PASS |
| JSON Schema 合法，含 `scripts` 与 `artifacts` | ✅ PASS |
| prompt.txt 长度 2072 字（T3 要求 ≥ 1200） | ✅ PASS |
| 无占位符残留 / 无 API Key / 无模型调用 | ✅ PASS |

## 二、脚本实跑

**命令**：

```bash
python3 scripts/run_flow.py --demo
python3 scripts/run_flow.py --input examples/input.json --outdir out
```

**运行环境**：Python 3.13.12 / openpyxl（复用 `assettools` 与 `product-kb-qa` 检索函数）

| 项 | 结果 |
|---|---|
| 退出码 | 0 |
| 咨询总数 | 6 |
| 知识命中 / 缺口 | 4 / 2（命中率 66.7%） |
| 议价条数 | 2（均落 50–200 元档） |
| 产物 1 | `out/售前导购台账.xlsx`（7.6 KB，3 sheet） |
| 产物 2 | `out/售前导购报告.md`（1.9 KB，端到端交付物） |
| 产物 3 | `out/presale_flow.json`（4.1 KB，分步执行明细） |
| 耗时 | < 0.8 s |

### 真编排证据

脚本通过 `importlib` **真实加载并调用** `skills/product-kb-qa/scripts/kb_qa.py` 的
`retrieve()` 函数完成步骤 2，而非重写一份检索逻辑 —— 编排链路可验证。

### 分步状态（真实输出）

```
1. 意图识别        ok  识别 6 条咨询意图
2. 商品知识库问答   ok  命中 4 条 / 缺口 2 条
3. 议价话术判定     ok  议价类 2 条已配让步档位
4. 汇总交付        ok  导购台账 + 报告
```

### 质量核对

| 检查 | 结果 |
|---|---|
| 引用原子技能存在性 | 2/2 存在（工作流测试通过） |
| 未命中被编造成命中 | 0（C/F 正确入缺口） |
| 议价档位与 skill prompt 一致 | 是（50–200 元 → 二线 ≤5%） |
| 缺字段静默失败 | 0（打印 error 并退出码 1） |

## 三、边界与已知限制

| 限制 | 说明 |
|---|---|
| 意图为词表规则 | 反讽/隐含表达可能落「其他」，需模型复核 |
| 议价档位需金额 | 缺 `订单金额` 时不下档位，转人工 |
| 知识命中率随库变化 | 改库后须重跑；缺口清单用于驱动补录 |

## 四、结论

**通过。** 工作流真编排（调用同仓原子技能脚本）、Mermaid DAG 引用 slug 全部真实存在、`--demo`/`--input` 双路径退出码 0 并产出 3 个端到端文件。

---

*测试报告基于真实实跑输出生成 · 2026-09-30*
