#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-nutrition 健康参谋模块

读取 data/nutrition.json（由 list-nutrition-foods 返回落盘），输出 Markdown 健康表。

数据文件：
  data/nutrition.json   <- list-nutrition-foods

用法：
  python scripts/nutrition.py --budget 800          # 按热量预算推荐套餐
  python scripts/nutrition.py --table                # 全量分类健康表
  python scripts/nutrition.py --low-sodium           # 低钠优选榜
  python scripts/nutrition.py --budget 800 --outdir report

容错约定：数据缺失或解析失败时如实报错并退出，不输出编造的营养数据。
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_OUTDIR = ROOT / "report"

# 成年人每日钠推荐摄入参考值（中国营养学会指南口径，约 2000mg）
SODIUM_DAILY_REF_MG = 2000
# 钠→食盐粗略换算：食盐(g) ≈ 钠(mg) / 400
SALT_FACTOR = 400.0

# 上游接口对部分商品名做了安全词过滤，返回的名称不可直接展示给用户。
# 特征：含 yeyeyeye 占位符，或名称含中文引号且引号内为被替换的敏感词片段。
# 这类条目在解析阶段标记为 dirty，输出时跳过并在报告中如实说明。
DIRTY_PATTERNS = ("yeyeyeye",)


def is_dirty_name(name):
    n = name.lower()
    if any(p in n for p in DIRTY_PATTERNS):
        return True
    # 形如 “苹板”支撑Pro / 专“薯鱼”你 —— 引号内为被替换的敏感词
    if "“" in name and "”" in name:
        inner = name.split("“")[1].split("”")[0]
        # 引号内为 2 字以内且名称总长很短，多为过滤残留
        if len(inner) <= 2:
            return True
    return False


# ---------- 数据解析 ----------

def load_nutrition():
    """解析 list-nutrition-foods 返回，返回 (items, error)。

    MCP 返回的 data 字段是自定义扁平格式，形如：
      [160]{productName,nutritionDescription,energyKj,energyKcal,protein,fat,carbohydrate,sodium,calcium}:
        猪柳麦满分,null,1288,308,16,16,24,781,213
        ...

    注意：实际返回中有少量字段错位（dessert 类目多一列逗号导致 calcium 偏移），
    因此按"从右往左定长取"策略解析，并对 NaN/缺失做防御。
    """
    path = DATA_DIR / "nutrition.json"
    if not path.exists():
        return None, "数据文件不存在（data/nutrition.json），请先调用 list-nutrition-foods 并落盘"

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None, "数据文件为空"

    # 兼容两种形态：① 完整 JSON 包；② 直接是 data 里的扁平文本
    raw = text
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            return None, f"JSON 解析失败: {e}"
        if isinstance(obj, dict) and obj.get("success") is False:
            return None, f"接口返回失败: {obj.get('message', '未知错误')}"
        if isinstance(obj, dict) and "__error" in obj:
            return None, obj["__error"]
        raw = obj.get("data") or ""
        if not raw:
            return None, "返回中 data 字段为空"

    if not isinstance(raw, str) or "{" not in raw:
        return None, "无法识别的数据格式（缺少表头）"

    # 取表头字段名与总条数
    header = re.search(r"\[(\d+)\]\{([^}]+)\}", raw)
    if not header:
        return None, "未找到表头（形如 [160]{字段,...}）"
    fields = [f.strip() for f in header.group(2).split(",")]

    # 表头之后为数据行
    body = raw[header.end():]
    items = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        cells = [c.strip() for c in line.split(",")]
        if len(cells) < 2:
            continue

        name = cells[0]
        if not name:
            continue

        # 从右往左固定取 7 个数值（kj, kcal, protein, fat, carb, sodium, calcium）
        nums = []
        for c in reversed(cells[1:]):
            if len(nums) == 7:
                break
            if re.fullmatch(r"-?\d+(\.\d+)?", c):
                nums.append(float(c))
            elif c.lower() in ("null", "none", ""):
                # 占位：仍然占一个数值位，保持列对齐
                nums.append(None)
            else:
                # 遇到非数值非占位（如描述文本），说明数值段开始，跳过
                continue
        nums.reverse()

        def g(i, default=0.0):
            if i < len(nums) and nums[i] is not None:
                return nums[i]
            return default

        items.append({
            "name": name,
            "kcal": g(1),
            "protein": g(2),
            "fat": g(3),
            "carb": g(4),
            "sodium": g(5),
            "calcium": g(6),
        })

    if not items:
        return None, "解析到 0 条有效数据"

    # 分离脏名称条目：上游安全词过滤导致名称不可展示，不进入正式表格
    clean = [it for it in items if not is_dirty_name(it["name"])]
    dirty_count = len(items) - len(clean)
    items = clean

    # 去重：同名且四项宏量营养素完全一致的视为重复条目
    seen = set()
    deduped = []
    for it in items:
        key = (it["name"], it["kcal"], it["protein"], it["fat"], it["carb"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(it)

    deduped.append({"__dirty__": dirty_count})  # 透传统计，供输出时说明
    return deduped, None


# ---------- 分类 ----------

CATEGORY_RULES = [
    ("汉堡 / 麦满分", lambda n: any(k in n for k in ("堡", "麦满分"))),
    ("鸡肉 / 炸物", lambda n: any(k in n for k in ("麦乐鸡", "脆汁鸡", "鸡翅", "V翅", "鸡块", "鸡排"))),
    ("小食 / 薯条", lambda n: any(k in n for k in ("薯", "脆薯饼", "玉米杯", "鸡球", "笋卷", "派", "冰淇淋"))),
    ("饮品 / 咖啡", lambda n: any(k in n for k in ("可乐", "雪碧", "咖啡", "奶", "茶", "豆浆", "果汁", "水", "美汁源", "怡泉", "新地", "拉明顿"))),
    ("其他", lambda n: True),
]


def classify(name):
    for label, rule in CATEGORY_RULES:
        if rule(name):
            return label
    return "其他"


# ---------- 输出区块 ----------

def render_table(items):
    """全量分类健康表，按热量升序。"""
    out = []
    groups = {}
    for it in items:
        groups.setdefault(classify(it["name"]), []).append(it)

    out.append("## 📋 全量健康表（按热量升序）")
    out.append("")
    out.append("| 餐品 | 热量(kcal) | 蛋白质(g) | 脂肪(g) | 碳水(g) | 钠(mg) |")
    out.append("|---|---:|---:|---:|---:|---:|")

    for label in ("汉堡 / 麦满分", "鸡肉 / 炸物", "小食 / 薯条", "饮品 / 咖啡", "其他"):
        rows = groups.get(label)
        if not rows:
            continue
        out.append(f"| **{label}** | | | | | |")
        for it in sorted(rows, key=lambda x: x["kcal"]):
            flag = " ⚠️" if it["sodium"] >= SODIUM_DAILY_REF_MG / 2 else ""
            out.append(
                f"| {it['name']}{flag} | {it['kcal']:.0f} | {it['protein']:.0f} | "
                f"{it['fat']:.0f} | {it['carb']:.0f} | {it['sodium']:.0f} |"
            )
    out.append("")
    out.append("> ⚠️ 标记表示钠含量 ≥ 每日推荐摄入量的一半（约 1000mg）。")
    out.append("> 份量口径以麦当劳官方为准（单份 / 中杯 / 常规等），跨品类比较仅作量级参考。")
    out.append("")
    return out


CHILD_MARKERS = ("儿童", "开心乐园", "小")


def is_child_item(name):
    """儿童向餐品识别。儿童餐热量/钠基准与成人不同，大预算方案里应当排除。"""
    return any(k in name for k in CHILD_MARKERS[:2])


def render_budget(items, budget):
    """按热量预算推荐组合：主食 + 小食 + 饮品，控制总热量。

    排序策略：先保证吃得饱（热量贴近预算而非远低于预算），
    再在同等饱腹度下优先低钠，并保证 Top3 主食不重复。
    """
    out = []
    out.append(f"## 🎯 {budget:.0f} kcal 预算搭配方案")
    out.append("")

    exclude_child = budget >= 600  # 大预算按成人场景，不推荐儿童餐

    def pool(category, exclude_child_items):
        cands = [i for i in items if classify(i["name"]) == category and i["kcal"] > 0]
        if exclude_child_items:
            cands = [i for i in cands if not is_child_item(i["name"])]
        return sorted(cands, key=lambda x: x["kcal"])

    mains = pool("汉堡 / 麦满分", exclude_child)
    sides = pool("小食 / 薯条", exclude_child)
    drinks = [i for i in items if classify(i["name"]) == "饮品 / 咖啡" and i["kcal"] > 0]
    drinks.sort(key=lambda x: x["kcal"])

    # 饱腹度：总热量达到预算 75%~100% 的组合才算「吃得饱」
    lower_bound = budget * 0.75
    plans = []
    for m in mains:
        for s in sides:
            for d in drinks:
                total = m["kcal"] + s["kcal"] + d["kcal"]
                if total > budget or total < lower_bound:
                    continue
                plans.append({
                    "main": m, "side": s, "drink": d,
                    "kcal": total,
                    "sodium": m["sodium"] + s["sodium"] + d["sodium"],
                    "protein": m["protein"] + s["protein"] + d["protein"],
                    "fill": total / budget,
                })

    if not plans:
        out.append(f"在现有数据里没有找到总热量落在 {lower_bound:.0f}~{budget:.0f} kcal 的三件套组合。")
        out.append("可以放宽预算，或改为「主食 + 饮品」两件套。")
        out.append("")
        return out

    # 先按热量贴近预算的程度排（越接近 100% 越优先），再按钠从低到高
    plans.sort(key=lambda p: (abs(p["fill"] - 0.95), p["sodium"]))

    # 取 Top3，且主食不重复，保证方案多样性
    top = []
    used_mains = set()
    for p in plans:
        key = p["main"]["name"]
        if key in used_mains:
            continue
        used_mains.add(key)
        top.append(p)
        if len(top) == 3:
            break

    out.append(f"推荐以下 3 套方案（在 {budget:.0f} kcal 内尽量吃饱，"
               f"同等饱腹度下优先低钠）：")
    out.append("")
    for idx, p in enumerate(top, 1):
        salt = p["sodium"] / SALT_FACTOR
        parts = (p["main"], p["side"], p["drink"])
        out.append(f"### 方案 {idx}：约 {p['kcal']:.0f} kcal")
        out.append("")
        out.append("| 组成 | 餐品 | 热量 | 蛋白 | 脂肪 | 碳水 | 钠 |")
        out.append("|---|---|---:|---:|---:|---:|---:|")
        for role, it in (("主食", p["main"]), ("小食", p["side"]), ("饮品", p["drink"])):
            out.append(
                f"| {role} | {it['name']} | {it['kcal']:.0f} | {it['protein']:.0f} | "
                f"{it['fat']:.0f} | {it['carb']:.0f} | {it['sodium']:.0f} |"
            )
        out.append(f"| **合计** | — | **{p['kcal']:.0f}** | **{p['protein']:.0f}** | "
                   f"**{sum(x['fat'] for x in parts):.0f}** | "
                   f"**{sum(x['carb'] for x in parts):.0f}** | "
                   f"**{p['sodium']:.0f}** |")
        out.append("")
        out.append(f"- 钠约 {p['sodium']:.0f}mg（约合食盐 {salt:.1f}g，"
                   f"占每日推荐 {p['sodium']/SODIUM_DAILY_REF_MG*100:.0f}%）")
        out.append(f"- 蛋白质 {p['protein']:.0f}g，占预算热量约 "
                   f"{p['protein']*4/p['kcal']*100:.0f}%")
        out.append("")

    if exclude_child:
        out.append("> 已排除儿童餐（热量与钠基准与成人不同）。")
        out.append("")
    out.append("---")
    out.append("")
    return out


def render_low_sodium(items):
    """低钠优选榜 + 高钠警示。"""
    out = []
    out.append("## 🧂 钠含量洞察")
    out.append("")

    ranked = sorted(items, key=lambda x: x["sodium"])
    out.append("### ✅ 低钠优选（钠 ≤ 60mg）")
    out.append("")
    out.append("| 餐品 | 钠(mg) | 热量(kcal) |")
    out.append("|---|---:|---:|")
    for it in ranked:
        if it["sodium"] > 60:
            break
        out.append(f"| {it['name']} | {it['sodium']:.0f} | {it['kcal']:.0f} |")
    out.append("")

    out.append("### ⚠️ 高钠警示（钠 ≥ 每日推荐量一半）")
    out.append("")
    out.append("| 餐品 | 钠(mg) | 约合食盐(g) | 占每日推荐 |")
    out.append("|---|---:|---:|---:|")
    highs = [i for i in ranked if i["sodium"] >= SODIUM_DAILY_REF_MG / 2]
    for it in sorted(highs, key=lambda x: -x["sodium"]):
        out.append(
            f"| {it['name']} | {it['sodium']:.0f} | {it['sodium']/SALT_FACTOR:.1f} | "
            f"{it['sodium']/SODIUM_DAILY_REF_MG*100:.0f}% |"
        )
    out.append("")
    out.append(f"> 成年人每日钠推荐摄入约 {SODIUM_DAILY_REF_MG}mg（约 5g 食盐）。")
    out.append("> 表中「约合食盐」为按钠÷400 的粗略估算，仅用于量级感知，非精确值。")
    out.append("")
    return out


def render_protein(items):
    """高蛋白优选榜。"""
    out = []
    out.append("## 💪 高蛋白优选（蛋白质 ≥ 15g）")
    out.append("")
    out.append("| 餐品 | 蛋白质(g) | 热量(kcal) | 蛋白/热量 | 脂肪(g) |")
    out.append("|---|---:|---:|---:|---:|")
    cands = [i for i in items if i["protein"] >= 15 and i["kcal"] > 0]
    for it in sorted(cands, key=lambda x: -(x["protein"] / x["kcal"] * 100))[:20]:
        out.append(
            f"| {it['name']} | {it['protein']:.0f} | {it['kcal']:.0f} | "
            f"{it['protein']/it['kcal']*100:.1f}% | {it['fat']:.0f} |"
        )
    out.append("")
    return out


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="麦当劳健康参谋")
    ap.add_argument("--budget", type=float, help="热量预算(kcal)，生成搭配方案")
    ap.add_argument("--table", action="store_true", help="输出全量分类健康表")
    ap.add_argument("--low-sodium", action="store_true", help="输出钠含量洞察")
    ap.add_argument("--protein", action="store_true", help="输出高蛋白优选榜")
    ap.add_argument("--all", action="store_true", help="输出全部板块")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="输出目录")
    args = ap.parse_args()

    if not any([args.budget, args.table, args.low_sodium, args.protein, args.all]):
        args.all = True

    items, err = load_nutrition()
    if err:
        print(f"错误：{err}", file=sys.stderr)
        sys.exit(1)

    # 摘出脏名称统计项（load 阶段附加的哨兵节点）
    dirty_count = 0
    real_items = []
    for it in items:
        if "__dirty__" in it:
            dirty_count = it["__dirty__"]
        else:
            real_items.append(it)
    items = real_items

    if not items:
        print("错误：清洗后无有效餐品数据", file=sys.stderr)
        sys.exit(1)

    body = []
    if args.all or args.budget:
        body.extend(render_budget(items, args.budget or 800))
    if args.all or args.low_sodium:
        body.extend(render_low_sodium(items))
    if args.all or args.protein:
        body.extend(render_protein(items))
    if args.all or args.table:
        body.extend(render_table(items))

    header = [
        "# 麦当劳健康参谋",
        "",
        f"_数据源：list-nutrition-foods · 解析 {len(items)} 条有效餐品营养数据_",
        "",
    ]
    if dirty_count:
        header.append(f"> 注：上游接口对部分商品名做了安全词过滤，"
                      f"已跳过 {dirty_count} 条名称不可展示的条目（未删改营养数据）。")
        header.append("")

    footer = [
        "---",
        "_由 mcd-nutrition 生成 · 营养数据以麦当劳官方公示为准 · 非医疗或营养建议_",
        "",
    ]

    text = "\n".join(header + body + footer)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / "健康参谋.md"
    outfile.write_text(text, encoding="utf-8")
    print(f"已生成: {outfile}")
    print(f"解析到 {len(items)} 条有效餐品营养数据"
          + (f"（跳过 {dirty_count} 条名称脏数据）" if dirty_count else ""))


if __name__ == "__main__":
    main()