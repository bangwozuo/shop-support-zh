# 店铺客服官

> **一人店的 7×24 客服坐席**

[![Stage](https://img.shields.io/badge/stage-P0-orange)](https://github.com/bangwozuo)
[![Asset](https://img.shields.io/badge/asset-prompt--only-blueviolet)](#资产形态)
[![NoKey](https://img.shields.io/badge/API%20Key-not%20required-success)](#资产形态)
[![License](https://img.shields.io/badge/license-Apache--2.0-green)](LICENSE)

---

![演示](https://cdn.jsdelivr.net/gh/bangwozuo/shop-support-zh@main/docs/assets/hero.gif)

*▲ 实时演示（自动循环）· [▶ 观看完整版合集视频](https://cdn.jsdelivr.net/gh/bangwozuo/shop-support-zh@main/docs/demo.mp4)*

*上方录屏来自本仓 5 个代表资产的真实执行 / 实跑产物截图（商品知识库问答 → 情绪识别安抚 → 售后工单分流与安抚 → 差评预警联动 → 夜间值守晨报），每帧 4 秒；单资产完整截图见各资产 `docs/assets/run-terminal.png`。*

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

## 数字员工总览

| 字段 | 内容 |
|------|------|
| 身份 | 店铺客服官——一人店的 7×24 客服坐席（售前导购 / 物流查询 / 售后安抚 / 夜间值守） |
| 边界 | 做接待与分流；**不做**退款审批、赔付决策（一律转人工，资金仅出草稿） |
| KPI | 首响 ≤30 秒 · AI 解决率 ≥70% · 夜间承接率 100% · 转人工率 ≤25% |

---

## 资产形态

**提示词为主 + 可选确定性脚本** —— 这是理解本仓库的关键：

| 特性 | 说明 |
|------|------|
| ✅ 无需 API Key | 一个 Key 都不需要 |
| ✅ 无需部署 | 纯提示词即用；8 个资产附可选 Python 脚本（产出 Excel/PNG/JSON 台账） |
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

## 资产矩阵（6 技能 + 5 工作流）

| 资产 | 一句话 | 类型 | README |
|------|--------|------|--------|
| 商品知识库问答 | 知识库内作答、条目 ID 可回溯，缺口不硬答（实跑 12 问命中 91.7%） | T1 原子技能+脚本 | [README](skills/product-kb-qa/README.md) |
| 转人工分流 | 判定每通会话「谁处理、多久内」，升级信号命中即升三线（10 通一次分流） | T1 原子技能+脚本 | [README](skills/human-handoff-route/README.md) |
| 物流跟踪解读 | 轨迹翻译成「当前状态 + 下一步」，异常件主动介入（6 单异常率 50%） | T1 原子技能+脚本 | [README](skills/logistics-track-parse/README.md) |
| 情绪识别安抚 | 先定级 L0–L4，再按四段结构给能降温的回复 | T2 原子技能 | [README](skills/emotion-detect-appease/README.md) |
| 议价话术 | 价值锚定 + 授权内让步，不击穿底线价留住买家 | T2 原子技能 | [README](skills/price-negotiation-script/README.md) |
| 退换货政策应答 | 先判时限与例外，再定运费责任与到账口径 | T2 原子技能 | [README](skills/return-policy-respond/README.md) |
| 售前智能导购 | 意图分流 → 知识库作答 → 议价档位匹配的端到端售前接待 | T3 工作流+脚本 | [README](workflows/presale-guide-flow/README.md) |
| 订单/物流自动查询 | 单号识别 → 轨迹解析 → 回复成稿 → 待主动介入清单 | T3 工作流+脚本 | [README](workflows/order-logistics-query-flow/README.md) |
| 售后工单分流与安抚 | 升级拦截 → 情绪分级 → 三层路由 → 安抚话术 → 台账 | T3 工作流+脚本 | [README](workflows/aftersale-ticket-route-flow/README.md) |
| 夜间值守+次日汇总 | 深夜自助应答 + 敏感消息留晨间 + 8:30 晨报（实跑自助应答率 85.7%） | T3 工作流+脚本 | [README](workflows/night-duty-summary-flow/README.md) |
| 差评预警联动 | 差评定因定级（S1 电话/S2 话术/S3 24h），预警推送店主 | T3 工作流+脚本 | [README](workflows/negative-review-alert-flow/README.md) |

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
