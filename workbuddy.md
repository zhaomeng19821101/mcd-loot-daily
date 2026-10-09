# WorkBuddy 开发对话上下文（workbuddy.md）

> 本文件记录参赛项目 **mcd-loot-daily（麦麦战报）** 在 WorkBuddy 中的开发过程，作为麦当劳程序员创意开发大赛 WorkBuddy 专项奖励的核验材料。
>
> - 开发工具：腾讯 WorkBuddy（AI Agent 桌面工作台）
> - 开发时间：2026-10-09
> - MCP 接入：麦当劳中国 MCP Server `mcd-mcp`（`https://mcp.mcd.cn`，Streamable HTTP），Token 经 WorkBuddy 自定义连接器配置并启用
>
> 以下为对话上下文的精要还原（含指令与关键产出，已裁去与开发无关的寒暄）。

---

## 1. 接入 MCP

**用户：** https://github.com/M-China/mcd-mcp-server

**WorkBuddy：** 拉取仓库 README，确认这是麦当劳中国官方 MCP Server 接入指南：地址 `https://mcp.mcd.cn`，Streamable HTTP，`Authorization: Bearer <TOKEN>` 鉴王，每分钟 600 次限流，覆盖点餐、券、积分、活动日历等 30+ 工具。

**用户：** （MCP Token）

**WorkBuddy：** 写入 `C:\Users\Administrator\.workbuddy\mcp.json`：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamableHttp",
      "url": "https://mcp.mcd.cn",
      "headers": { "Authorization": "Bearer <已脱敏>" },
      "timeout": 30000,
      "disabled": false
    }
  }
}
```

随后直接 `curl` 验证端点连通性，`initialize` 握手返回 `200 OK`、`serverInfo: mcd-mcp 1.0.0`，确认 Token 有效。连接器启用后 5 个 Tool 在会话中可用。

---

## 2. 比赛调研

**用户：** https://mp.weixin.qq.com/s/-6lOK0oh3hoM-mj7YbiAog 这个活动，我要参与

**WorkBuddy：** 抓取公众号文章 → 锁定"2026 麦当劳程序员创意开发大赛"（10-09 ~ 10-25）→ 追到官方仓库 `M-China/mcd-developer-innovation-challenge`，拉取完整活动规则，提取硬性要求：

- 必备文件：`README.md`、`CONTEST_DECLARATION.md`（原文不可改）、`MCP_INTEGRATION.md`、`mcp-config.example.json`（仅环境变量占位符）、源代码
- WorkBuddy 专项奖励须交 `workbuddy.md`（即本文件）
- 排名按 GitHub Star 数，10-26 00:00 定榜；前 100 名进榜

**用户：** 选题你出创意；GitHub 账号仓库已有。

---

## 3. 选题决策

**WorkBuddy（方案）：** 选题 **「麦麦战报」每日情报 Skill**——把活动日历、可领券、卡包、积分 4 处分散信息一次拉齐，交叉比对生成"今天该抢什么、该用什么券"的每日简报。理由：真实串 5 个 MCP Tool、只读无风险、使用频率高（每天一次）、战报是天然的可分享产物。

**用户：** （认可，开干）

---

## 4. 实测 MCP 真实返回

动手写码前先用 WorkBuddy 实际调用 5 个 Tool 验证链路，拿到真实返回结构：

| Tool | 实测结果（2026-10-09 19:59） |
|---|---|
| `now-time-info` | `success:true`，`data.date=2026-10-09`，`dayOfWeek=FRIDAY` |
| `query-my-account` | `availablePoint:"13"`，`currency:"麦享会积分"`，`accumulativePoint:"171.8"` |
| `available-coupons` | 返回 **Markdown 券列表**：免费脆薯饼/人气麦旋风买一送一/9.9元冰美式 等，状态"可领取" |
| `campaign-calendar` | 返回按日分组 Markdown：10-09 当日 13 条活动（韩式蘸酱上新、麦金喜抽奖预约等） |
| `query-my-coupons` | 卡包券列表，`page`/`pageSize` 分页参数 |

**关键发现：** 部分 Tool 返回带 `success/code/data` 外壳的 JSON，部分直接返回 Markdown 文本 → 战报脚本必须做**双格式容错解析**，已照此实现。

---

## 5. 构建与产出

**WorkBuddy 产出：**

- `mcd-loot-daily/SKILL.md` — Skill 定义：触发词、5-Tool 并行拉取、落盘约定、战报生成、红线（禁止自动领券/下单/抽奖）
- `scripts/build_report.py` — 纯标准库战报生成器：JSON/Markdown 双格式解析、日期基准优先取 MCP 服务器时间、缺失板块如实标注不编造
- `README.md` / `MCP_INTEGRATION.md` / `mcp-config.example.json` — 参赛必备文档
- `CONTEST_DECLARATION.md` — 从官方仓库原文复制，一字未改

**自测：** `python scripts/build_report.py --date auto`，验证 `data/` 缺文件时输出"⚠️ 本次未获取的板块"而非报错中断；日期非法时退出码 2。

---

## 6. 待办（报名链路）

1. 将本项目推送至个人 GitHub **公开**仓库（创建时间须在 2025-12-25 ~ 2026-10-25 区间）
2. 在 `M-China/mcd-developer-innovation-challenge` 发报名 Issue，格式：

```
【参赛申请】
项目名称：麦麦战报 mcd-loot-daily
项目地址：https://github.com/<你的用户名>/<仓库名>
项目简介：基于麦当劳MCP的每日情报Skill，一句话生成今日券+活动+积分战报
```

3. Issue 正文 ≤1000 字、不带图片；等系统回复报名成功/失败原因
