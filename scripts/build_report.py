#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mcd-loot-daily 战报生成脚本

读取 data/ 下由 MCP 工具返回的 5 份数据，交叉比对后输出 Markdown 战报。

数据文件（由 WorkBuddy 调用 MCP 工具后落盘）：
  data/time.json       <- now-time-info
  data/calendar.json   <- campaign-calendar
  data/available.json  <- available-coupons
  data/mine.json       <- query-my-coupons
  data/account.json    <- query-my-account

用法：
  python scripts/build_report.py --date auto          # 以 time.json 的服务器日期为准
  python scripts/build_report.py --date 2026-10-09    # 指定日期
  python scripts/build_report.py --date auto --outdir report

容错约定：某份数据拉取失败时，Skill 会写入 {"__error": "..."} 占位，
本脚本跳过该板块并在战报末尾如实标注，不编造数据。
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DEFAULT_OUTDIR = ROOT / "report"

TITLE_KEYS = ("title", "activityTitle", "couponName", "couponTitle", "name", "offerTitle")
STATUS_KEYS = ("status", "state", "couponStatus")
WEEK_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


# ---------- 数据读取 ----------

def load(name: str):
    """返回 (kind, payload)。kind: 'error' | 'json' | 'markdown' | 'missing'。"""
    path = DATA_DIR / name
    if not path.exists():
        return "missing", None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return "error", {"__error": "文件为空"}
    if text.startswith("{") or text.startswith("["):
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            return "error", {"__error": f"JSON 解析失败: {e}"}
        if isinstance(obj, dict) and "__error" in obj:
            return "error", obj
        if isinstance(obj, dict) and obj.get("success") is False:
            return "error", {"__error": f"接口返回失败: {obj.get('message', '未知错误')}"}
        return "json", obj
    return "markdown", text


def find_dicts(obj, out=None):
    """递归收集所有含 title 类键的 dict。"""
    if out is None:
        out = []
    if isinstance(obj, dict):
        if any(k in obj for k in TITLE_KEYS):
            out.append(obj)
        for v in obj.values():
            find_dicts(v, out)
    elif isinstance(obj, list):
        for v in obj:
            find_dicts(v, out)
    return out


def title_of(d: dict) -> str:
    for k in TITLE_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return "(无标题)"


def status_of(d: dict) -> str:
    for k in STATUS_KEYS:
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def parse_md_coupons(text: str):
    """解析 available-coupons 返回的 markdown 列表：优惠券标题/状态 成对出现。"""
    items, cur_title = [], None
    for line in text.splitlines():
        line = line.strip().lstrip("-").strip()
        m = re.match(r"优惠券标题：(.+)", line)
        if m:
            if cur_title:
                items.append({"title": cur_title, "status": ""})
            cur_title = m.group(1).strip()
            continue
        m = re.match(r"状态：(.+)", line)
        if m and items is not None and cur_title:
            items.append({"title": cur_title, "status": m.group(1).strip()})
            cur_title = None
    if cur_title:
        items.append({"title": cur_title, "status": ""})
    return items


def parse_md_calendar(text: str):
    """解析 campaign-calendar 的 markdown：按 '#### 日期' 分组，取活动标题。"""
    groups, cur_date = [], None
    for line in text.splitlines():
        m = re.match(r"^#{2,4}\s*(\d{4}年\d{1,2}月\d{1,2}日)\s*(.*)", line)
        if m:
            cur_date = {"date": m.group(1), "label": m.group(2).strip(), "titles": []}
            groups.append(cur_date)
            continue
        m = re.match(r"^[-*]?\s*\*{0,2}活动标题\*{0,2}：(.+)", line.strip())
        if m and cur_date is not None:
            cur_date["titles"].append(m.group(1).strip())
    return groups


def convert_md_date(s: str):
    """'2026年10月9日' -> '2026-10-09'"""
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", s)
    if not m:
        return ""
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def parse_md_wallet(text: str):
    """解析 query-my-coupons 的 markdown：'## 标题' + 优惠/有效期/标签 字段行。"""
    items, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            if cur:
                items.append(cur)
            cur = {"title": m.group(1).strip(), "discount": "", "valid": "", "tags": ""}
            continue
        if cur is None:
            continue
        m = re.match(r"^[-*]?\s*\*{0,2}优惠\*{0,2}[:：]\s*(.+)", line)
        if m:
            cur["discount"] = m.group(1).strip()
            continue
        m = re.match(r"^[-*]?\s*\*{0,2}有效期\*{0,2}[:：]\s*(.+)", line)
        if m:
            cur["valid"] = m.group(1).strip()
            continue
        m = re.match(r"^[-*]?\s*\*{0,2}标签\*{0,2}[:：]\s*(.+)", line)
        if m:
            cur["tags"] = m.group(1).strip()
    if cur:
        items.append(cur)
    return items


# ---------- 各板块构建 ----------

def server_date(kind, payload, fallback: str) -> str:
    if kind == "json" and isinstance(payload, dict):
        data = payload.get("data") or {}
        d = data.get("date")
        if isinstance(d, str) and re.match(r"\d{4}-\d{2}-\d{2}", d):
            return d[:10]
    return fallback


def weekday_cn(date_str: str) -> str:
    try:
        return WEEK_CN[datetime.strptime(date_str, "%Y-%m-%d").weekday()]
    except ValueError:
        return "?"


def section_claims(kind, payload):
    """可领取 / 已领取"""
    if kind == "missing":
        return None, "数据文件不存在"
    if kind == "error":
        return None, payload.get("__error", "未知错误")
    items = parse_md_coupons(payload) if kind == "markdown" else find_dicts(payload)
    claimable, claimed, other = [], [], []
    for d in items:
        title, status = title_of(d), status_of(d)
        if "已领" in status:
            claimed.append(title)
        elif "可领" in status:
            claimable.append(title)
        else:
            other.append(f"{title}（{status}）" if status else title)

    def uniq(seq):  # 去重保序
        seen = set()
        return [x for x in seq if not (x in seen or seen.add(x))]

    return {"claimable": uniq(claimable), "claimed": uniq(claimed), "other": uniq(other)}, None


def section_wallet(kind, payload, date_str=""):
    """卡包：markdown 用 parse_md_wallet，JSON 退化为标题列表。"""
    if kind == "missing":
        return None, "数据文件不存在"
    if kind == "error":
        return None, payload.get("__error", "未知错误")
    if kind == "markdown":
        items = parse_md_wallet(payload)
    else:
        items = [{"title": title_of(d), "discount": "", "valid": "", "tags": ""}
                 for d in find_dicts(payload)]
    # 今日到期置顶
    items.sort(key=lambda x: 0 if "今日到期" in x.get("tags", "") else 1)
    return items, None


def section_points(kind, payload):
    """积分"""
    if kind == "missing":
        return None, "数据文件不存在"
    if kind == "error":
        return None, payload.get("__error", "未知错误")
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        return None, "未找到积分数据字段"
    keys = [("availablePoint", "可用"), ("accumulativePoint", "累计"),
            ("frozenPoint", "冻结"), ("currentMouthExpirePoint", "本月将过期"),
            ("expiredPoint", "已过期"), ("usedPoint", "已使用")]
    rows = [(label, data.get(raw)) for raw, label in keys if data.get(raw) is not None]
    currency = data.get("currency", "")
    return {"rows": rows, "currency": currency}, None


def section_calendar(kind, payload, date_str: str):
    """活动日历：优先取目标日期；JSON 格式则全量列出。"""
    if kind == "missing":
        return None, "数据文件不存在"
    if kind == "error":
        return None, payload.get("__error", "未知错误")
    if kind == "markdown":
        groups = parse_md_calendar(payload)
        target = None
        for g in groups:
            if convert_md_date(g["date"]) == date_str:
                target = g
                break
        if target is None:
            # '今日' 标签兜底
            for g in groups:
                if "今日" in g["label"]:
                    target = g
                    break
        if target is None:
            return {"titles": [], "note": f"日历中没有 {date_str} 的条目"}, None
        return {"titles": target["titles"], "note": ""}, None
    dicts = find_dicts(payload)
    return {"titles": [title_of(d) for d in dicts], "note": "（接口返回结构未按日期分组，以下为全量活动标题）"}, None


# ---------- 战报渲染 ----------

def render(date_str, blocks, errors):
    wd = weekday_cn(date_str)
    out = [f"# 麦麦战报 {date_str}（{wd}）", ""]

    out.append("## 🔥 今日可抢")
    claims = blocks.get("claims")
    if claims:
        if claims["claimable"]:
            for t in claims["claimable"]:
                out.append(f"- [ ] {t}")
        else:
            out.append("- 今日暂无“可领取”状态的新券。")
        if claims["claimed"]:
            out.append("")
            out.append(f"<details><summary>已领取 {len(claims['claimed'])} 张</summary>")
            out.extend(f"- {t}" for t in claims["claimed"])
            out.append("</details>")
        if claims["other"]:
            out.append("")
            out.append(f"其他状态 {len(claims['other'])} 项：")
            out.extend(f"- {t}" for t in claims["other"][:10])
    out.append("")

    out.append("## 📅 今天在搞什么")
    cal = blocks.get("calendar")
    if cal:
        for t in cal["titles"]:
            out.append(f"- {t}")
        if not cal["titles"]:
            out.append("- 日历中暂无该日活动。")
        if cal["note"]:
            out.append(f"- _{cal['note']}_")
    out.append("")

    out.append("## 💰 积分")
    pts = blocks.get("points")
    if pts:
        out.append(f"货币口径：{pts['currency'] or '积分'}")
        out.append("")
        out.append("| 项目 | 数值 |")
        out.append("|---|---|")
        for label, val in pts["rows"]:
            out.append(f"| {label} | {val} |")
    out.append("")

    out.append("## 🎒 卡包")
    wallet = blocks.get("wallet")
    if wallet is not None:
        expiring = [w for w in wallet if "今日到期" in (w.get("tags") or "")]
        rest = [w for w in wallet if w not in expiring]
        if expiring:
            out.append("")
            out.append(f"### ⏰ 今日到期 {len(expiring)} 张，别浪费")
            for w in expiring:
                line = f"- [ ] **{w['title']}**"
                if w.get("discount"):
                    line += f"　{w['discount']}"
                out.append(line)
        out.append("")
        out.append(f"共 {len(wallet)} 张券：")
        for w in rest[:20]:
            bits = [w["title"]]
            if w.get("discount"):
                bits.append(w["discount"])
            if w.get("valid"):
                bits.append(f"有效期 {w['valid']}")
            if w.get("tags"):
                bits.append(f"[{w['tags']}]")
            out.append(f"- {' · '.join(bits)}")
        if len(rest) > 20:
            out.append(f"- …等共 {len(wallet)} 张（仅展示前 20）")
    out.append("")

    if errors:
        out.append("## ⚠️ 本次未获取的板块")
        out.extend(f"- **{name}**：{msg}" for name, msg in errors)
        out.append("")

    out.append("---")
    out.append("_由 mcd-loot-daily 生成 · 数据以麦当劳官方渠道实时结果为准 · 非麦当劳官方产品_")
    out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="生成麦当劳每日战报")
    ap.add_argument("--date", default="auto", help="auto 或 YYYY-MM-DD")
    ap.add_argument("--outdir", default=str(DEFAULT_OUTDIR), help="输出目录")
    args = ap.parse_args()

    errors = []
    blocks = {}

    t_kind, t_payload = load("time.json")
    if args.date == "auto":
        date_str = server_date(t_kind, t_payload, datetime.now().strftime("%Y-%m-%d"))
        if t_kind in ("error", "missing"):
            errors.append(("now-time-info（时间基准回退到本机日期）",
                           t_payload.get("__error") if t_kind == "error" else "数据文件不存在"))
    else:
        date_str = args.date
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            print(f"日期格式错误: {date_str}（应为 YYYY-MM-DD）", file=sys.stderr)
            sys.exit(2)

    claims, err = section_claims(*load("available.json"))
    if err:
        errors.append(("可领券（available-coupons）", err))
    blocks["claims"] = claims

    wallet, err = section_wallet(*load("mine.json"), date_str=date_str)
    if err:
        errors.append(("卡包（query-my-coupons）", err))
    blocks["wallet"] = wallet

    pts, err = section_points(*load("account.json"))
    if err:
        errors.append(("积分（query-my-account）", err))
    blocks["points"] = pts

    cal, err = section_calendar(*load("calendar.json"), date_str=date_str)
    if err:
        errors.append(("活动日历（campaign-calendar）", err))
    blocks["calendar"] = cal

    text = render(date_str, blocks, errors)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    outfile = outdir / f"战报-{date_str}.md"
    outfile.write_text(text, encoding="utf-8")
    print(f"已生成: {outfile}")
    if errors:
        print("注意：以下板块本次未获取（战报中已如实标注）:")
        for name, msg in errors:
            print(f"  - {name}: {msg}")


if __name__ == "__main__":
    main()
