# 麦麦战报 mcd-loot-daily

> 基于麦当劳中国 MCP Server 的每日情报 Skill：把活动日历、可领优惠券、卡包、积分一次拉全，交叉比对生成一份"今天该抢什么、该用什么券"的每日战报。

**目标用户**：想每天花 30 秒知道"麦当劳今天有什么羊毛"的麦门人、日常用 WorkBuddy 打理生活杂事的用户。

## 解决什么问题

麦当劳的优惠、活动、积分分散在 App 的 4 个角落，用户要自己逐个翻。`mcd-loot-daily` 用 5 个 MCP 工具一次拉齐，输出结构化 Markdown 战报：

- **今日可抢**：麦麦省里状态为"可领取"的新券，逐条列出
- **今天在搞什么**：当日营销活动日历（新品、联名、抽奖预约一网打尽）
- **积分**：可用 / 累计 / 本月将过期，一眼看清
- **卡包**：已拥有的券清单

## 安装

### 1. 配置麦当劳 MCP

到 [麦当劳 MCP 开放平台](https://open.mcd.cn/mcp) 手机号登录并申请 MCP Token，然后在 WorkBuddy 中：

**左侧边栏 → 专家·技能·连接器 → 连接器 → 右上角【自定义连接器】→【配置 MCP】**，粘贴（替换占位符）：

```json
{
  "mcpServers": {
    "mcd-mcp": {
      "type": "streamablehttp",
      "url": "https://mcp.mcd.cn",
      "headers": {
        "Authorization": "Bearer 你的MCP_TOKEN"
      }
    }
  }
}
```

保存后回到【自定义连接器】，将 `mcd-mcp` **启用**。脱敏模板见 [mcp-config.example.json](./mcp-config.example.json)。

> 限流：每个 Token 每分钟最多 600 次请求，超出返回 429。请妥善保管 Token，不要提交到仓库。

### 2. 安装 Skill

把本仓库的 `mcd-loot-daily/` 目录（含 `SKILL.md`）放入 WorkBuddy 的技能目录（用户级 `~/.workbuddy/skills/` 或项目级 `.workbuddy/skills/`），重启 WorkBuddy 后生效。

### 3. 环境要求

- Python 3.8+（仅用标准库，无第三方依赖）

## 使用示例

在 WorkBuddy 对话框里直接说：

```
给我今天的麦当劳战报
```

```
今天有什么羊毛可以薅？我积分还有多少？
```

执行流程：WorkBuddy 调用 `SKILL.md` 中定义的 5 个 MCP 工具拉取实时数据 → 落盘 `data/*.json` → 运行 `python scripts/build_report.py --date auto` → 输出 `report/战报-YYYY-MM-DD.md`。

命令行也可以单独跑（`data/` 里已有数据时）：

```bash
python scripts/build_report.py --date auto
python scripts/build_report.py --date 2026-10-09 --outdir report
```

## 项目结构

```
mcd-loot-daily/
├── README.md                     # 本文件
├── CONTEST_DECLARATION.md        # 参赛声明（官方原文）
├── MCP_INTEGRATION.md            # MCP 接入与调用链路说明
├── mcp-config.example.json       # 脱敏 MCP 配置（环境变量占位符）
├── workbuddy.md                  # WorkBuddy 开发对话上下文
├── mcd-loot-daily/
│   └── SKILL.md                  # Skill 定义（触发条件与执行步骤）
├── scripts/
│   └── build_report.py           # 战报生成脚本（Python 标准库）
├── data/                         # MCP 原始返回（运行时生成）
└── report/                       # 生成的战报（运行时生成）
```

## 合规与红线

- **不会**自动执行领券、下单、抽奖等写操作；用户明确要求时才执行并先复述确认。
- 不采集、不存储 Token、手机号、地址等敏感信息；配置仅用环境变量占位符。
- 战报数据全部来自麦当劳 MCP 实时返回；某板块拉取失败时如实标注，不编造。
- 餐品、价格、活动以麦当劳官方渠道实时结果为准。

## License

本项目为麦当劳程序员节创意开发大赛参赛作品，非麦当劳官方产品。项目内容遵循仓库根目录 `CONTEST_DECLARATION.md` 中的声明。
