"""Generate docs/architecture.png — compact, non-overlapping layout."""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

OUT = Path(__file__).resolve().parent / "architecture.png"

BG = "#14100c"
PANEL = "#1c1610"
BORDER = "#5c4a32"
GOLD = "#c9a227"
TEXT = "#e8dcc8"
MUTED = "#9a8870"
DEMO_FILL = "#1a2420"
DEMO_BORDER = "#3d6b55"
FULL_FILL = "#1a1e28"
FULL_BORDER = "#3d5a8a"
SHARED_FILL = "#221c14"

GAP = 2.2
TITLE_BAND = 3.6
PAD = 1.0
LINE_H = 1.85
BODY_FS = 7.5
TITLE_FS = 8.5
TEXT_PAD_X = 1.6


@dataclass
class BoxSpec:
    x: float
    w: float
    title: str
    items: list[str]
    fill: str
    edge: str
    title_color: str = GOLD
    char_width: int = 22


@dataclass
class PlacedBox:
    x: float
    y: float
    w: float
    h: float
    spec: BoxSpec


def _wrap(text: str, width: int) -> list[str]:
    return textwrap.wrap(text, width=width) or [""]


def _body_lines(items: list[str], char_width: int) -> list[str]:
    lines: list[str] = []
    for item in items:
        wrapped = _wrap(item, char_width)
        for i, part in enumerate(wrapped):
            lines.append(f"{'• ' if i == 0 else '  '}{part}")
    return lines


def _height(spec: BoxSpec) -> float:
    n = len(_body_lines(spec.items, spec.char_width))
    return TITLE_BAND + PAD + n * LINE_H + PAD


def _draw_box(ax, placed: PlacedBox) -> None:
    s = placed.spec
    x, y, w, h = placed.x, placed.y, placed.w, placed.h
    body = _body_lines(s.items, s.char_width)

    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.25,rounding_size=0.8",
            linewidth=1.2, edgecolor=s.edge, facecolor=s.fill, zorder=2,
        )
    )
    ax.text(
        x + w / 2, y + h - TITLE_BAND * 0.45, s.title,
        ha="center", va="center", fontsize=TITLE_FS, fontweight="bold",
        color=s.title_color, zorder=3,
    )
    sep_y = y + h - TITLE_BAND
    ax.plot([x + 0.8, x + w - 0.8], [sep_y, sep_y], color=s.edge, linewidth=0.5, alpha=0.5, zorder=3)
    ax.text(
        x + TEXT_PAD_X, sep_y - 0.25, "\n".join(body),
        ha="left", va="top", fontsize=BODY_FS, color=TEXT, linespacing=1.25, zorder=3,
    )


def _arrow(ax, x1, y1, x2, y2, color=MUTED, lw=1.0):
    ax.add_patch(
        FancyArrowPatch(
            (x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=10,
            linewidth=lw, color=color, zorder=1, shrinkA=4, shrinkB=4,
        )
    )


def main() -> None:
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    left_x, col_w = 3.0, 46.0
    right_x = left_x + col_w + 2.0
    full_w = col_w * 2 + 2.0
    center_x = left_x + full_w / 2

    specs: list[tuple[str, BoxSpec]] = [
        ("fe", BoxSpec(left_x, full_w, "React 前端", [
            "NarrativeFeed · 叙事流与内嵌选项",
            "WorldPanel · 世界态势",
            "ChapterComplete · 结局页",
        ], PANEL, BORDER, char_width=38)),
        ("gl", BoxSpec(left_x + 8, full_w - 16, "FastAPI · GameLoop", [
            "POST /game/new-demo → 脚本 Demo",
            "POST /game/action → 动态模拟",
            "get_state · SQLite 持久化",
        ], SHARED_FILL, GOLD, char_width=32)),
        ("dr", BoxSpec(left_x, col_w, "Scripted Demo Runner（作品集 Demo）", [
            "ravenford_demo_script.json",
            "choice_id → next 节点",
            "预设 dice / blocks / notebook",
            "branch → ending_good / bad",
        ], DEMO_FILL, DEMO_BORDER, char_width=24)),
        ("ws", BoxSpec(right_x, col_w, "World Simulator（正式版动态）", [
            "intent_parser → D20 检定",
            "world_tick · 危机 / 谣言 / 派系",
            "确定性修改 GameState",
        ], FULL_FILL, FULL_BORDER, char_width=24)),
        ("dn", BoxSpec(left_x, col_w, "叙事呈现层（共用）", [
            "blocks_to_html · narrative_formatter",
            "build_session_summary",
            "Demo 不调 LLM / action_generator",
        ], DEMO_FILL, DEMO_BORDER, "#6ec99a", char_width=24)),
        ("fn", BoxSpec(right_x, col_w, "Narrative + 动态选项", [
            "narrative_engine + LLM",
            "action_generator → choice_renderer",
            "无 Key 时 Fallback 叙事",
        ], FULL_FILL, FULL_BORDER, "#7aa8e8", char_width=24)),
        ("infra", BoxSpec(left_x, full_w, "共用基础设施", [
            "World Template · SQLite · Image Service",
            "medieval / xianxia JSON · Ontology · Prompt MD5 缓存",
        ], SHARED_FILL, BORDER, char_width=42)),
    ]

    heights = {k: _height(s) for k, s in specs}

    # 自上而下堆叠，保证间距
    legend_h = 4.5
    positions: dict[str, PlacedBox] = {}
    positions["infra"] = PlacedBox(left_x, legend_h + GAP, full_w, heights["infra"], specs[6][1])

    row_dn_y = positions["infra"].y + positions["infra"].h + GAP
    positions["dn"] = PlacedBox(left_x, row_dn_y, col_w, heights["dn"], specs[4][1])
    positions["fn"] = PlacedBox(right_x, row_dn_y, col_w, heights["fn"], specs[5][1])
    row_dn_top = row_dn_y + max(heights["dn"], heights["fn"])

    row_dr_y = row_dn_top + GAP
    positions["dr"] = PlacedBox(left_x, row_dr_y, col_w, heights["dr"], specs[2][1])
    positions["ws"] = PlacedBox(right_x, row_dr_y, col_w, heights["ws"], specs[3][1])
    row_dr_top = row_dr_y + max(heights["dr"], heights["ws"])

    gl_y = row_dr_top + GAP
    positions["gl"] = PlacedBox(left_x + 8, gl_y, full_w - 16, heights["gl"], specs[1][1])

    fe_y = gl_y + heights["gl"] + GAP
    positions["fe"] = PlacedBox(left_x, fe_y, full_w, heights["fe"], specs[0][1])

    canvas_h = fe_y + heights["fe"] + 1.5
    canvas_w = left_x + full_w + 3.0

    fig, ax = plt.subplots(
        figsize=(9, max(7.5, canvas_h / canvas_w * 9)),
        facecolor=BG,
    )
    ax.set_facecolor(BG)
    ax.set_xlim(0, canvas_w)
    ax.set_ylim(0, canvas_h)
    ax.axis("off")

    for pb in positions.values():
        _draw_box(ax, pb)

    fe, gl, dr, ws, dn, fn = (positions[k] for k in ("fe", "gl", "dr", "ws", "dn", "fn"))

    def cx(b): return b.x + b.w / 2
    def top(b): return b.y + b.h
    def bot(b): return b.y

    _arrow(ax, cx(fe), bot(fe), cx(gl), top(gl), GOLD)
    _arrow(ax, cx(gl), bot(gl), cx(dr), top(dr), DEMO_BORDER)
    _arrow(ax, cx(gl), bot(gl), cx(ws), top(ws), FULL_BORDER)
    _arrow(ax, cx(dr), bot(dr), cx(dn), top(dn), DEMO_BORDER)
    _arrow(ax, cx(ws), bot(ws), cx(fn), top(fn), FULL_BORDER)
    _arrow(ax, cx(dn), bot(dn), cx(fe), top(fe), DEMO_BORDER, lw=0.8)
    _arrow(ax, cx(fn), bot(fn), cx(fe), top(fe), FULL_BORDER, lw=0.8)

    # 图例：画布最底，独立区域
    leg_y = 1.8
    ax.plot([2, canvas_w - 2], [legend_h, legend_h], color=BORDER, linewidth=0.6, alpha=0.4)
    for i, (lbl, col) in enumerate([
        ("Demo 脚本路径", DEMO_BORDER),
        ("正式版模拟路径", FULL_BORDER),
        ("共用模块", GOLD),
    ]):
        lx = 4 + i * 18
        ax.add_patch(plt.Rectangle((lx, leg_y - 0.35), 1.8, 0.7, facecolor=col, edgecolor="none"))
        ax.text(lx + 2.5, leg_y, lbl, ha="left", va="center", fontsize=7.5, color=MUTED)

    fig.savefig(OUT, dpi=160, facecolor=BG, bbox_inches="tight", pad_inches=0.25)
    plt.close(fig)
    print(f"Wrote {OUT} ({canvas_w:.0f}x{canvas_h:.0f})")


if __name__ == "__main__":
    main()
