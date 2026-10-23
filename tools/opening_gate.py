#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ADVISORY/仅测试：生产开场由 SKILL 路由及文案卡驱动，本模块不参与生产。

S0 开场两分支（v3）：全新安装只问昵称+产品；有历史先给选择、不直接展示历史。

规则（用户裁决）：
- C1 全新安装（无任何历史项目）：一次只问两样（昵称 + 产品），允许加粗，emoji 适量。
- C2 有历史项目：先给选择（①接着上次做 ②换新产品 ③看看之前做到哪）；用户明确选③或①后，
  才展示最少必要信息（产品别名 + 人话阶段）。一次最多列 3 个项目，超出说「还有 N 个更早的项目，要看吗」。
- 禁止：无历史或读取失败时说「我记得您…」；展示 token/凭据/内部枚举（S3/status/next_state/路径）。
- 展示值必须转义 markdown。

本模块只产出结构化判定与转义文本，不读写本地状态，便于单测。
"""
import re
from pathlib import Path


def history_menu_options():
    """从唯一任务菜单读取原始选项，保留编号、emoji、星标与顺序。"""
    card = Path(__file__).resolve().parents[1] / "output-templates" / "S0-任务菜单.md"
    # 菜单只保留「有旧项目时」一节；按下一个二级标题截断，不依赖已删除的「无旧项目时」
    section = card.read_text(encoding="utf-8").split("## 有旧项目时", 1)[1].split("\n## ", 1)[0]
    return [line.strip() for line in section.splitlines()
            if re.match(r"\s*[1-4]\. ", line)]

MAX_VISIBLE_PROJECTS = 3
MORE_TEMPLATE = "还有 {n} 个更早的项目，要看吗？"

# 内部状态 → 人话阶段（只用于展示，禁止把左边的值给用户看）
STAGE_LABELS = {
    "S0": "刚开始了解您的产品",
    "S0A": "正在整理您的产品资料",
    "S1": "准备选从哪里开始找客户",
    "S2": "正在帮您找可能买您货的买家类型",
    "S3": "在挑一个合适的样板买家",
    "S4": "在抽查名单质量",
    "S5": "准备保存客户名单（等您确认）",
    "S6": "正在保存客户名单",
    "S7": "准备写开发信（等您确认）",
    "S8": "正在批量写开发信",
    "S9": "正在排跟进计划",
    "S9A": "正在准备固定标签",
    "S10": "正在把客户加进跟进计划",
    "S11": "全部准备好了，等您决定要不要开始发",
    "S12": "已激活，正在发送中",
    "ERROR_BLOCKED": "中途卡住了，需要您看一下",
}
UNKNOWN_STAGE = "刚建了个项目"

_MD_ESCAPE = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~])")


def escape_markdown(text):
    """转义展示值，防止产品别名里带的 markdown 破坏排版。"""
    return _MD_ESCAPE.sub(r"\\\1", "" if text is None else str(text))


def human_stage(status):
    key = str(status or "").strip().upper()
    return STAGE_LABELS.get(key, UNKNOWN_STAGE)


def decide_opening(projects=(), read_ok=True):
    """返回开场模式：new（只问昵称+产品）/ history（先给选择）。

    读取失败或没有项目都按全新开场；绝不据此声称「记得您」。
    """
    items = [p for p in (projects or []) if p]
    if not read_ok or not items:
        return {
            "mode": "new",
            "show_projects": False,
            "ask": ["昵称", "产品"],
            "options": [],
            "menu_card": "",
            "memory_claim_allowed": False,
        }
    return {
        "mode": "history",
        "show_projects": False,
        "ask": [],
        # K8：历史分支复用 S0-任务菜单.md 的四项，不另造菜单
        "options": history_menu_options(),
        "menu_card": "S0-任务菜单.md",
        "memory_claim_allowed": True,
    }


def project_briefs(projects, limit=MAX_VISIBLE_PROJECTS):
    """只在用户明确选①/③后调用：产品别名 + 人话阶段，最多 3 个。"""
    items = [p for p in (projects or []) if p]
    shown = []
    for item in items[:max(0, int(limit))]:
        if isinstance(item, dict):
            alias = item.get("product") or item.get("alias") or item.get("name") or ""
            status = item.get("status") or item.get("state") or ""
        else:
            alias, status = item, ""
        shown.append({"alias": str(alias).strip(), "display": escape_markdown(alias),
                      "stage": human_stage(status)})
    extra = max(0, len(items) - len(shown))
    return {
        "projects": shown,
        "more": MORE_TEMPLATE.format(n=extra) if extra else "",
        "hidden_count": extra,
    }
