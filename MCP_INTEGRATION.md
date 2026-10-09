# MCP 接入说明（MCP_INTEGRATION.md）

## 使用的 MCP Server

| 项 | 值 |
|---|---|
| 名称 | `mcd-mcp`（麦当劳中国 MCP Server） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权 | `Authorization: Bearer <MCP_TOKEN>`（Token 从 [open.mcd.cn/mcp](https://open.mcd.cn/mcp) 申请，经环境变量注入，不入库） |
| 限流 | 600 次/分钟/Token，超出返回 429 |
| 官方仓库 | [M-China/mcd-mcp-server](https://github.com/M-China/mcd-mcp-server) |

## 实际使用的 Tool 与调用流程

本 Skill 使用 5 个只读 Tool，全部为一次并行拉取，无写操作：

| # | Tool | 用途 | 调用方式 |
|---|---|---|---|
| 1 | `now-time-info` | 获取服务器时间，作为战报日期基准 | 无参 |
| 2 | `campaign-calendar` | 当月营销活动日历 | 无参（默认全月） |
| 3 | `available-coupons` | 麦麦省**可领取**的券 | 无参 |
| 4 | `query-my-coupons` | 卡包中**已拥有**的券 | `page=1`, `pageSize=200` |
| 5 | `query-my-account` | 积分账户（可用/累计/冻结/将过期） | 无参 |

### 调用链路

```
用户："给我今天的麦当劳战报"
        │
        ▼
WorkBuddy 触发 SKILL.md（mcd-loot-daily）
        │
        ├─ ① 并行调用 5 个 MCP Tool ──► https://mcp.mcd.cn
        │      Authorization: Bearer <MCD_MCP_TOKEN>
        │
        ├─ ② 原始返回落盘
        │      data/time.json        data/calendar.json
        │      data/available.json   data/mine.json
        │      data/account.json
        │      （失败时写入 {"__error": "..."} 占位，不中断流程）
        │
        ├─ ③ python scripts/build_report.py --date auto
        │      读取 data/*.json → 交叉比对 → 渲染 Markdown
        │
        └─ ④ 交付 report/战报-YYYY-MM-DD.md
              数据缺失板块在战报末尾如实标注
```

### 真实调用验证（2026-10-09 实测）

以下为接入时对 5 个 Tool 的真实连通性验证结果（截取关键字段）：

- `now-time-info` → `{"success": true, "code": 200, "data": {"date": "2026-10-09", "dayOfWeek": "FRIDAY", ...}}`
- `query-my-account` → `{"success": true, "code": 200, "data": {"availablePoint": "13", "currency": "麦享会积分", ...}}`
- `available-coupons` → 返回 Markdown 券列表，含"优惠券标题/状态"成对字段（如 状态：可领取）
- `campaign-calendar`（`specifiedDate=2026-10-09`）→ 返回按日分组的活动列表（今日活动 13 条）
- `query-my-coupons` → 返回卡包券列表（Schema：`page`/`pageSize` 分页，最大 5 页 / 每页 200 条）

> 说明：部分 Tool 返回结构化 JSON（带 `success/code/data` 外壳），部分返回渲染后的 Markdown 文本。`build_report.py` 对两种格式都做了容错解析。

## 业务价值

1. **信息聚合**：原本要在麦当劳 App 里翻 4 个页面（活动、麦麦省、卡包、积分）才能拼出的全貌，现在一句话拿到一份战报。
2. **决策辅助**：脚本把"可领未领"和"当日到期活动"排到战报最前面，直接给出行动清单（`- [ ]` 待办格式）。
3. **时效可靠**：日期基准取自 MCP 服务器时间（`now-time-info`）而非本机时钟，避免跨时区/改本地时间导致战报日期错位。
4. **失败可感**：任一 Tool 失败不导致整份战报崩溃，缺失板块在末尾"⚠️ 本次未获取的板块"如实标注——宁可少一块，不给假数据。

## 安全边界

- 全链路只读：**不调用** `auto-bind-coupons`（领券）、`create-order`/`mall-create-order`（下单）、`draw-lottery`（抽奖）等写操作。
- Token 仅经 HTTP 头传输，落盘配置使用 `${MCD_MCP_TOKEN}` 环境变量占位符（见 `mcp-config.example.json`）。
- `data/` 下仅存业务数据（券、活动、积分），不含账号凭证；输出战报不含 Token、手机号、地址。
