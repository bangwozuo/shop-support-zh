# 转人工分流

> 原子技能 ｜ 属于「店铺客服官」 ｜ 电商小卖家 客群

边界判断+摘要交接

![流程示意](docs/assets/overview.svg)

---

## 这是什么

`转人工分流` 是一个**原子技能**资产。它不是一个软件，也不是一段代码，
而是**可以直接复制粘贴到任意 AI 工具里使用的提示词资产**。

| 特性 | 说明 |
|------|------|
| 零 API Key | 不需要任何密钥 |
| 零部署 | 纯提示词即可用；高级用法附 Python 脚本 |
| 平台无关 | Coze / WorkBuddy / Dify / Claude / ChatGPT 均可 |
| 用户自备算力 | 模型来自你自己的订阅 |

## 快速开始（3 步）

```text
1. 打开 skills/human-handoff-route/prompt.txt
2. 全文复制
3. 粘贴到你的 AI 工具，按输入规格提供数据
```

需要批量分流会话并产出 Excel 台账时，用配套脚本：

```bash
python3 skills/human-handoff-route/scripts/handoff_route.py --input input.json --outdir out
```

## 文件地图

```text
├── README.md                ← 本文件
├── SKILL.md                 ← 资产定义（元信息 / 契约 / 边界）
├── prompt.txt               ← 提示词本体（核心交付物）
├── schema.json              ← 输入输出契约（机器可读）
├── scripts/handoff_route.py ← 可选脚本：分层路由 + 产出 Excel/PNG
├── examples/                ← 示例输入与输出
└── docs/                    ← 10 项配套文档
    ├── 01-usage-manual.md      安装使用手册
    ├── 02-architecture.md      业务架构图
    ├── 03-flow.md              流程图
    ├── 04-examples.md          使用示例
    ├── 05-media.md             截图和录屏
    ├── 06-scenarios.md         使用场景（适用 / 不适用）
    ├── 07-audience.md          用户群体
    ├── 08-value.md             解决问题与价值
    └── 09-test-report.md       测试报告
```

## 输入输出

| 项 | 内容 |
|----|------|
| 输入 | 客服会话数组（含买家消息） |
| 输出 | 三层分流台账 + 升级信号明细 + 结构化交接摘要 |

## 面向谁 / 解决什么

- **用户群体**：淘宝 / 抖店 / 拼多多 / 小红书店铺小卖家
- **典型场景**：店铺日常运营（上架、接待、售后、评价维护）
- **解决痛点**：上架、客服、评价、作图四线作战，人力不够
- **衡量指标**：转化率、响应时长、差评率、动销率

详见 [用户群体](docs/07-audience.md) 与 [解决问题与价值](docs/08-value.md)。

## 合规

- 本资产输出为 **AI 辅助生成内容**，交付前必须经人工审核
- 请按所在平台要求完成 **AI 生成内容标识**
- 连接器只走两条合规路径：**官方 API**、**用户自行导出的数据**

---

*本资产遵循 [bangwozuo 数字员工资产规范](https://github.com/bangwozuo/digital-employee-spec) v3.0*
