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

本 Skill 使用 **6 个只读 Tool**，全部为一次并行拉取，**无写操作**：

| # | Tool | 用途 | 调用方式 |
|---|---|---|---|
| 1 | `now-time-info` | 获取服务器时间，作为报告日期基准 | 无参 |
| 2 | `campaign-calendar` | 当月营销活动日历 | 无参（默认全月） |
| 3 | `available-coupons` | 麦麦省**可领取**的券 | 无参 |
| 4 | `query-my-coupons` | 卡包中**已拥有**的券 | `page=1`, `pageSize=200` |
| 5 | `query-my-account` | 积分账户（可用/累计/冻结/将过期） | 无参 |
| 6 | `list-nutrition-foods` | 全量餐品营养数据（热量/蛋白/脂肪/碳水/钠/钙） | 无参 |

### 调用链路

```
用户："给我今天的麦当劳战报"
        │
        ▼
WorkBuddy 触发 SKILL.md（mcd-loot-daily）
        │
        ├─ ① 并行调用 6 个 MCP Tool ──► https://mcp.mcd.cn
        │      Authorization: Bearer <MCD_MCP_TOKEN>
        │
        ├─ ② 原始返回落盘
        │      data/time.json        data/calendar.json
        │      data/available.json   data/mine.json
        │      data/account.json     data/nutrition.json
        │      （失败时写入 {"__error": "..."} 占位，不中断流程）
        │
        ├─ ③ 生成两份报告
        │      python scripts/build_report.py --date auto   → 情报侧
        │      python scripts/nutrition.py --all             → 健康侧
        │
        └─ ④ 交付
               report/战报-YYYY-MM-DD.md（当日情报 + 行动清单）
               report/健康参谋.md（预算搭配 + 钠洞察 + 健康表）
               缺失板块在报告末尾如实标注
```

### 真实调用验证（2026-10-09 / 2026-10-10 实测）

以下为接入时对 6 个 Tool 的真实连通性验证结果（截取关键字段）：

- `now-time-info` → `{"success": true, "code": 200, "data": {"date": "2026-10-09", "dayOfWeek": "FRIDAY", ...}}`
- `query-my-account` → `{"success": true, "code": 200, "data": {"availablePoint": "13", "currency": "麦享会积分", ...}}`
- `available-coupons` → 返回 Markdown 券列表，含"优惠券标题/状态"成对字段（如 状态：可领取）
- `campaign-calendar`（`specifiedDate=2026-10-09`）→ 返回按日分组的活动列表（今日活动 13 条）
- `query-my-coupons` → 返回卡包券列表（Schema：`page`/`pageSize` 分页，最大 5 页 / 每页 200 条），共 12 张
- `list-nutrition-foods` → 返回 `[160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:` 扁平文本 + 160 行 CSV 数据

> 说明：Tool 返回格式**实测有四种**，脚本为每种写了独立解析器：
>
> | 数据 | 格式 |
> |---|---|
> | 时间 / 积分 | 标准 JSON（`success/code/data` 外壳） |
> | 活动日历 / 可领券 | 渲染后的 Markdown 列表 |
> | 卡包 | `## 标题` + `**优惠**/**有效期**/**标签**` 块，含「今日到期」标记 |
> | 营养数据 | 自定义扁平格式 `[N]{字段,...}:` + CSV 行（部分行含描述文本导致列数不一致） |

## 已验证但未采用的能力（如实说明）

为评估「用券最省」方向，实测了以下工具，结论是**当前无法支撑券抵扣计算**：

| Tool | 实测结果 |
|---|---|
| `query-nearby-stores` | ✅ 可用。返回门店 `storeCode` / 营业时间 / 预约时段 / 距离。**注意**：门店搜索对关键词敏感，"中央大街"返回 `600047` 搜不到，换"哈站"成功 |
| `query-meals` | ✅ 可用。返回每餐品 `currentPrice` / `originalPrice` / `discountType` / `canWithOrder`，可算折扣率（实测最高 57.3% off） |
| `calculate-price` | ⚠️ 算价可用，**但用券不可行** |
| `query-meal-detail` | 已获取 schema，未纳入当前流程 |

### 券抵扣为什么做不了（关键缺口）

```
calculate-price 传券参数 → 
  {"success": false, "code": 600010, "message": "使用优惠券需要couponId和couponCode"}

query-my-coupons 返回字段 →
  优惠券标题 / 优惠金额 / 有效期 / 领取时间 / 标签（人类可读）
  ❌ 无 couponId、❌ 无 couponCode、❌ 无商品编码
```

两者**没有共同的匹配键**，且卡包券名（"巧克力味厚松饼猪柳蛋套餐"）与菜单 `name`
写法不一致，无法可靠关联。因此本项目承诺的是「**菜单折扣率最优**」，
**不是**「帮你用券最省」。这个限制已写入 README 与 SKILL.md，避免 Agent 给出做不到的承诺。

## 业务价值

1. **信息聚合**：原本要在麦当劳 App 里翻 4 个页面（活动、麦麦省、卡包、积分）才能拼出的全貌，现在一句话拿到一份战报。
2. **决策辅助**：脚本把"可领未领"和"当日到期活动"排到战报最前面，直接给出行动清单（`- [ ]` 待办格式）。
3. **时效可靠**：日期基准取自 MCP 服务器时间（`now-time-info`）而非本机时钟，避免跨时区/改本地时间导致战报日期错位。
4. **失败可感**：任一 Tool 失败不导致整份报告崩溃，缺失板块在末尾"⚠️ 本次未获取的板块"如实标注——宁可少一块，不给假数据。
5. **健康决策**：154 条营养数据做成分类健康表与钠洞察，把"控热量/控钠"从模糊目标变成可执行的三件套组合。

## 数据清洗的工程价值

营养数据实测有三类问题，脚本均已处理并**如实披露**，而非静默篡改：

| 问题 | 实测表现 | 处理方式 |
|---|---|---|
| 名称重复 | 160 条中 `纯牛奶（盒装）`、`小杯玉米杯` 各出现 2 次 | 按「名称 + 四项营养素」去重 |
| 脏名称 | 上游安全词过滤返回 `yeyeyeye奶冻款`、`“苹板”支撑Pro`、`专“薯鱼”你` | 识别并跳过，报告开头注明跳过 **4 条**，营养数据不删改 |
| 列错位 | 含描述文本的行逗号数不一致（如 `芝士安格斯厚牛堡,能量约鲈鱼1条,...`） | 从右往左定长取 7 个数值，缺失位补 0 |

## 安全边界

- 全链路只读：**不调用** `auto-bind-coupons`（领券）、`create-order`/`mall-create-order`（下单）、`draw-lottery`（抽奖）等写操作。
- Token 仅经 HTTP 头传输，落盘配置使用 `${MCD_MCP_TOKEN}` 环境变量占位符（见 `mcp-config.example.json`）。
- `data/` 下仅存业务数据（券、活动、积分、营养），不含账号凭证；输出报告不含 Token、手机号、地址。
- 健康建议标注为非专业建议；钠→食盐换算（钠÷400）标注为粗略估算，仅用于量级感知。
