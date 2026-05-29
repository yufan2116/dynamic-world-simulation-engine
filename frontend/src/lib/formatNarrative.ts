/** 客户端叙事清洗 — 兜底隐藏漏网的 engine/debug 用语 */

const SNAKE_ACTIVITY: Record<string, string> = {
  guarding_gate: "在村口警戒",
  pleading_in_square: "在广场求助",
  watching_from_curtain: "在酒馆门帘后观望",
  patrol_warehouse: "带队前往仓库巡逻",
};

const INTERNAL_ID = /\b(?:fact_|pf_|clue_|obs_|hook_|topic_|follow_)[a-z0-9_]+\b/gi;
const SNAKE = /[a-z]+_[a-z0-9_]+/gi;
const ACTIVITY_INLINE = /([\u4e00-\u9fff]{2,4})正在([a-z][a-z0-9_]+)/gi;

export function polishNarrativeText(text: string): string {
  let out = text
    .replace(INTERNAL_ID, "")
    .replace(/局面暂时停顿[。.]?/g, "你环顾四周，一时没有新的动静。")
    .replace(/你确认当前场景暂时没有更多可见异常[。.]?/g, "这里暂时没有更多可见线索。")
    .replace(/继续调查/g, "继续追查眼前的线索")
    .replace(/信息：/g, "")
    .replace(/【危机】/g, "")
    .replace(/【NPC】/g, "")
    .replace(/【世界】/g, "")
    .replace(/【压力】/g, "");

  out = out.replace(ACTIVITY_INLINE, (_, name: string, act: string) => {
    const zh = SNAKE_ACTIVITY[act.toLowerCase()] ?? "在忙碌";
    return `${name}${zh}`;
  });

  out = out.replace(SNAKE, (w) => SNAKE_ACTIVITY[w.toLowerCase()] ?? "");
  out = out.replace(/\s{2,}/g, " ").trim();
  return out;
}

export function polishNarrativeHtml(html: string): string {
  if (!html?.trim()) return html;
  return html.replace(/>([^<]+)</g, (_, inner: string) => {
    const t = polishNarrativeText(inner);
    return t ? `>${t}<` : "><";
  });
}

export function polishChoiceLabel(text: string): string {
  const t = polishNarrativeText(text);
  if (!t) return "[感知] 继续观察四周";
  if (t.startsWith("[")) return t;
  if (/安慰|询问|交谈|说服/.test(t)) return `[交涉] ${t}`;
  if (/观察|打量|检查|搜查/.test(t)) return `[感知] ${t}`;
  return t;
}
