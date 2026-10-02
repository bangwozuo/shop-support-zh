# 店铺客服官

> **一人店的 7×24 客服坐席**

[![Stage](https://img.shields.io/badge/stage-P0-orange)](https://github.com/bangwozuo)
[![Asset](https://img.shields.io/badge/asset-prompt--only-blueviolet)](#资产形态)
[![NoKey](https://img.shields.io/badge/API%20Key-not%20required-success)](#资产形态)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

## 它是谁

面向 **电商小卖家** 的数字员工资产包。

| 项目 | 内容 |
|------|------|
| 目标用户 | 日均咨询 30-300 条、跨 2 个以上平台的一人店 |
| 交付物 | 首响 ≤30 秒；AI 解决率 ≥70%；夜间承接率 100%；转人工率 ≤25% |
| 技能数 | 6 |
| 工作流数 | 5 |
| 旧名存档 | `客服专员·小服` |

---

## 资产形态

**纯提示词资产** —— 这是理解本仓库的关键：

| 特性 | 说明 |
|------|------|
| ✅ 无需 API Key | 一个 Key 都不需要 |
| ✅ 无需部署 | 没有服务端，没有脚本 |
| ✅ 无需依赖 | 克隆后用文本编辑器就能看 |
| ✅ 平台无关 | 粘贴到任何 AI 工具即可使用 |
| ✅ 用户自备算力 | 模型来自你自己的订阅 |

---

## 快速开始

```text
1. 打开 skills/product-kb-qa/prompt.txt
2. 全文复制
3. 粘贴到你常用的 AI 工具（Coze / WorkBuddy / Dify / Claude / ChatGPT）
4. 按 SKILL.md 的输入规格提供数据
```

就这四步。完整指引见 [使用手册](docs/04-usage.md)。

---

## 仓库结构

```text
shop-support-zh/
├── README.md / employee.md / package.yaml     # 入口与 12 字段定义卡
├── docs/01~07                                 # 员工级文档（架构/流程/场景/手册/示例/录像/测试）
├── skills/                                    # 6 个原子技能
│   └── <skill>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该技能自己的 10 项文档 + 配图
├── workflows/                                 # 5 条工作流（复合技能）
│   └── <workflow>/
│       ├── README.md  SKILL.md  prompt.txt  schema.json  examples/
│       └── docs/                              # 该工作流自己的 10 项文档 + 配图
├── knowledge/                                 # RAG wiki 知识库
│   ├── README.md  RAG-接入指南.md  template.md
│   └── wiki/(index.md, _template.md, entries/)
├── connectors/                                # 连接器说明 + 合规红线
├── quality/                                   # 效果基线与追踪日志
└── tests/                                     # 资产校验测试（离线，无需密钥）
```

### 每个技能 / 工作流自带的 docs

| 文档 | 内容 |
|------|------|
| `README.md` | 资产速览与快速开始 |
| `docs/01-usage-manual.md` | 安装使用手册 |
| `docs/02-architecture.md` | 业务架构图 |
| `docs/03-flow.md` | 流程图（Mermaid + 配图） |
| `docs/04-examples.md` | 使用示例 |
| `docs/05-media.md` | 截图和录屏（清单 + 分镜脚本） |
| `docs/06-scenarios.md` | 使用场景（适用 / 不适用） |
| `docs/07-audience.md` | 用户群体 |
| `docs/08-value.md` | 解决问题与价值 |
| `docs/09-test-report.md` | 测试报告 |
| `docs/assets/overview.svg` | 自动生成的流程示意图 |

---

## 交付物导航

| 文档 | 内容 |
|------|------|
| [业务架构](docs/01-architecture.md) | 四层架构 + 数据流 + 能力边界 |
| [工作流流程](docs/02-workflow.md) | 5 条工作流的 DAG 可视化 |
| [使用场景](docs/03-scenarios.md) | 3 个真实场景（含前后对比） |
| [使用手册](docs/04-usage.md) | 各平台导入指引 + 常见问题 |
| [示例库](docs/05-examples.md) | 6 组输入输出示例 |
| [录像脚本](docs/06-recording-script.md) | 7 镜头分镜 + 旁白稿 |
| [校验报告](docs/07-test-report.md) | 资产质量校验结果 |

---

## 技能清单（6 个）

| # | 技能 | 能力族 | 复杂度 | 提示词 | 文档 |
|---|------|--------|--------|--------|------|
| 1 | 商品知识库问答 | 回复应答 | `M` | [prompt.txt](skills/product-kb-qa/prompt.txt) | [docs](skills/product-kb-qa/docs/) |
| 2 | 议价话术 | 回复应答 | `S` | [prompt.txt](skills/price-negotiation-script/prompt.txt) | [docs](skills/price-negotiation-script/docs/) |
| 3 | 物流跟踪解读 | 多语言 | `M` | [prompt.txt](skills/logistics-track-parse/prompt.txt) | [docs](skills/logistics-track-parse/docs/) |
| 4 | 退换货政策应答 | 回复应答 | `S` | [prompt.txt](skills/return-policy-respond/prompt.txt) | [docs](skills/return-policy-respond/docs/) |
| 5 | 情绪识别安抚 | 回复应答 | `S` | [prompt.txt](skills/emotion-detect-appease/prompt.txt) | [docs](skills/emotion-detect-appease/docs/) |
| 6 | 转人工分流 | 摘要提炼 | `S` | [prompt.txt](skills/human-handoff-route/prompt.txt) | [docs](skills/human-handoff-route/docs/) |

## 工作流清单（5 条）

| # | 工作流 | 阶段 | 复杂度 | 触发 | 定义 | 文档 |
|---|--------|------|--------|------|------|------|
| 1 | 售前智能导购 | `P0` | `M` | 事件（买家消息） | [SKILL.md](workflows/presale-guide-flow/SKILL.md) | [docs](workflows/presale-guide-flow/docs/) |
| 2 | 订单/物流自动查询 | `P0` | `M` | 事件 | [SKILL.md](workflows/order-logistics-query-flow/SKILL.md) | [docs](workflows/order-logistics-query-flow/docs/) |
| 3 | 售后工单分流与安抚 | `P0` | `M` | 事件 | [SKILL.md](workflows/aftersale-ticket-route-flow/SKILL.md) | [docs](workflows/aftersale-ticket-route-flow/docs/) |
| 4 | 夜间值守+次日汇总 | `P0` | `S` | 定时（22:00-8:00 + 8:30 晨报） | [SKILL.md](workflows/night-duty-summary-flow/SKILL.md) | [docs](workflows/night-duty-summary-flow/docs/) |
| 5 | 差评预警联动 | `P1` | `S` | 事件（新评价） | [SKILL.md](workflows/negative-review-alert-flow/SKILL.md) | [docs](workflows/negative-review-alert-flow/docs/) |

---

## 知识库与连接器

| 目录 | 说明 |
|------|------|
| [`knowledge/`](knowledge/README.md) | RAG wiki 知识库：填入业务信息可显著提升输出质量 |
| [`connectors/`](connectors/README.md) | 连接器说明：数据从哪来、怎么合规地来 |

---

## 资产校验

```bash
pip install -r requirements.txt
pytest tests/ -v
```

校验技能完整性、提示词结构、契约一致性、工作流 DAG、技能级与工作流级 docs 完整性、知识库 wiki 与连接器结构。
**不需要任何 API Key。**

---

## 合规声明

- ✅ 所有输出为 **AI 辅助生成**，交付前须人工审核
- ✅ 提示词内置**违禁词禁止清单**，符合《广告法》要求
- ✅ 遵循《人工智能生成合成内容标识办法》
- ✅ 连接器只走**官方 API** 或**用户导出数据**
- ✅ 所有对外发布动作**保留人工确认环节**

---

## 许可

[Apache-2.0](LICENSE) — 可自由使用、修改、商用

---

*由 bangwozuo 业务库自动生成 · 2026-09-29*
