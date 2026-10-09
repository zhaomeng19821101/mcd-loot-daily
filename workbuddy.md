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

---

## 7. 第二阶段：健康参谋模块融合（2026-10-10）

### 起因

老板在项目交付后提出两个新方向，评估是否值得做：

1. 超值组合（如何用券最实惠）
2. 健康达人饮食搭配（注明碳水、热量、脂肪、蛋白质，做健康表）

### 关键决策：不凭直觉，先实测工具边界

我没有直接答"能做"，而是**逐个工具真实调用验证**，结果推翻了部分想当然的判断。

**方向① 遇到硬伤。** 为了验证"用券最省"可行性，实测链路：

```
query-nearby-stores (哈尔滨·哈站) → 5 家门店，拿到 storeCode=3230011
query-meals  → 拿到真实 productCode 与现价/原价（发现算价前必须先查菜单）
calculate-price（真实 productCode）→ 成功，返回 2690 分 = ¥26.90
calculate-price（传券参数）→ ❌ 报错 600010「使用优惠券需要couponId和couponCode」
query-my-coupons → 只返回 标题/金额/有效期/标签，无 couponId、无商品编码
```

**结论**：卡包券与菜单商品没有共同匹配键，"用券最省"做不了。
我没有硬凑，而是**如实调整定位**为「菜单折扣率最优」并把限制写进 SKILL.md，
避免 Agent 后续给出做不到的承诺。这也是老板认可"如实写负面结果"的地方。

**方向② 数据超预期。** `list-nutrition-foods` 实测返回 **160 条**，每条含
energyKcal / protein / fat / carbohydrate / sodium / calcium 六个字段——
老板要的 4 项全有，还多出钠和钙。

**意外发现**：钠含量是最有传播力的切入点。实测数据：

| 餐品 | 钠(mg) |
|---|---|
| 芝士双层安格斯厚牛堡 | 1373 |
| 培根双层安格斯厚牛堡 | 1191 |
| 大杯玉米杯 | 2 |
| 100%苹果汁 | 0 |

成年人每日钠推荐约 2000mg，一份厚牛堡吃掉 69%。这个"用数据教育人"的切入点
比普通热量表更有观点、更容易被 Star。

### 融合决策与实现

老板明确要**融合**而非新建仓库。于是把健康能力并入原项目，扩到 6 个 MCP 工具，
一份 Skill 输出**两份报告**（战报 + 健康参谋），共用一套容错与清洗约定。

新增 `scripts/nutrition.py`（442 行，纯标准库）：

- `--budget N` 热量预算搭配 / `--low-sodium` 钠洞察 / `--protein` 高蛋白榜 / `--table` 分类健康表 / `--all` 全部

### 三个自己发现并修掉的缺陷

**1. 预算搭配初版逻辑错误**

初版按「低钠优先」排序，实跑发现三套方案主食全是「儿童鱼排堡」，
热量只用到 432/800 kcal——用户根本吃不饱，等于给了个没意义的方案。

修正为三重排序：先筛「总热量落在预算 75%~100%」（保证吃饱）→ 再按接近 95% 饱腹度排
→ 同分再比钠；同时强制 Top3 主食不重复。修完后 500 kcal（钠占 28%）
与 1200 kcal（钠占 74%）都能给出合理方案，逻辑自洽。

**2. 脏名称必须过滤但要披露**

营养数据里出现 `yeyeyeye奶冻款`、`“苹板”支撑Pro`、`专“薯鱼”你` 这类名称——
上游做了安全词过滤，商品名被替换成无意义字符。直接展示给用户很突兀，
但静默删除又属于掩盖问题。

处理方式：识别特征（yeyeyeye 占位符、引号内 ≤2 字的替换残留）→ 跳过，
**在报告开头注明"已跳过 4 条名称不可展示的条目"**，营养数据不删改。

**3. 营养数据列错位**

部分行含描述文本导致逗号数不一致，例如：
`芝士安格斯厚牛堡,能量约鲈鱼1条,2914,696,32,44,43,897,150`

若按固定列号解析会整体错位。改用「从右往左定长取 7 个数值」策略，
并对 null 占位保留列位、对非数值描述文本跳过。

另外补了两条业务规则：大预算（≥600 kcal）场景**自动排除儿童餐**
（其热量与钠基准与成人不同，混用会误导）；钠→食盐换算按 ÷400 估算，
报告中明确标注为粗略估算而非精确值。

### 验证与回归

- 160 条 → 去重 2 条（纯牛奶、小杯玉米杯）→ 过滤脏名 4 条 = **154 条有效**
- 全链路回归：编译 / 战报 / 健康参谋默认 / 500·800·1200 kcal 预算 全部通过
- 降级路径：缺 `nutrition.json` 与 `{"__error":...}` 占位均明确报错 + 退出码 1，**不产出假报告**

### 最终产出（第二阶段）

| 文件 | 变化 |
|---|---|
| `scripts/nutrition.py` | 新增 442 行，健康参谋生成器 |
| `mcd-loot-daily/SKILL.md` | 触发词扩展到健康类；新增执行步骤 4、输出示例（战报+健康双格式）、**已知限制**章节 |
| `README.md` | 定位改为「每日情报 + 健康参谋」，新增钠洞察发现、四种返回格式对照、数据清洗说明、已知限制 |
| `MCP_INTEGRATION.md` | 6-Tool 链路、格式对照表、**已验证但未采用的能力**章节（记录券抵扣失败证据）、数据清洗工程价值 |
| `报名信息.md` | 简介重写为融合版（含实测发现与能力边界），补充推送命令 |

### 提交

`cfcc396` 初版（11 文件 / 874 行）→ `055e832` 融合健康模块（4 文件 / +683 行）
