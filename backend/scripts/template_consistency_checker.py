"""Template Consistency Checker

扫描 world_templates 下 JSON，检查是否残留“跨题材”词汇（换皮痕迹）。

用法（在 backend 目录）：
  python -m scripts.template_consistency_checker
  python -m scripts.template_consistency_checker --template xianxia_forbidden_land
  python -m scripts.template_consistency_checker --fail-on-findings
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from engine.world_template_manager import TEMPLATE_ROOT, list_templates, resolve_template_id


XIANXIA_FORBIDDEN = ["酒馆", "粮价", "村庄", "商人", "仓库", "银币"]
MEDIEVAL_FORBIDDEN = ["宗门", "灵气", "葬仙渊", "道长", "剑修", "邪修", "丹药", "封印祭坛"]


@dataclass(frozen=True)
class Finding:
    template_id: str
    file: str
    json_path: str
    term: str
    snippet: str


def _iter_strings(obj: Any, *, path: str = "$") -> Iterable[tuple[str, str]]:
    """yield (json_path, string_value)"""
    if isinstance(obj, str):
        yield path, obj
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            # key name as searchable surface too
            if isinstance(k, str):
                yield f"{path}.<key>", k
            yield from _iter_strings(v, path=f"{path}.{k}")
        return
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, path=f"{path}[{i}]")
        return
    # numbers/bool/null: ignore


def _load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def scan_template(template_id: str) -> list[Finding]:
    tid = resolve_template_id(template_id)
    tdir = TEMPLATE_ROOT / tid
    if not tdir.is_dir():
        raise KeyError(f"未知模板目录: {tid}")

    forbidden = XIANXIA_FORBIDDEN if "xianxia" in tid else MEDIEVAL_FORBIDDEN
    findings: list[Finding] = []

    for path in sorted(tdir.glob("*.json")):
        try:
            data = _load_json(path)
        except Exception:
            continue
        for jpath, text in _iter_strings(data):
            for term in forbidden:
                if term and term in text:
                    snippet = text
                    if len(snippet) > 140:
                        snippet = snippet[:140] + "…"
                    findings.append(
                        Finding(
                            template_id=tid,
                            file=str(path.relative_to(TEMPLATE_ROOT)),
                            json_path=jpath,
                            term=term,
                            snippet=snippet,
                        )
                    )
    return findings


def scan_all() -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for t in list_templates():
        tid = t["id"]
        out[tid] = scan_template(tid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", dest="template", default=None)
    ap.add_argument("--fail-on-findings", action="store_true")
    args = ap.parse_args()

    if args.template:
        results = {resolve_template_id(args.template): scan_template(args.template)}
    else:
        results = scan_all()

    total = 0
    for tid, items in results.items():
        if not items:
            print(f"[OK] {tid}: no forbidden terms found")
            continue
        print(f"[FAIL] {tid}: {len(items)} findings")
        for f in items[:60]:
            print(f"  - {f.file} {f.json_path} hit '{f.term}': {f.snippet}")
        if len(items) > 60:
            print(f"  ... +{len(items) - 60} more")
        total += len(items)

    if args.fail_on_findings and total > 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

