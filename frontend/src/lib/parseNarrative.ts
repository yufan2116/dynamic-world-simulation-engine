import type { InlineChoice, NarrativeBlock, NarrativeBlockKind } from "../types";

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, "").trim();
}

/** 仅对世界/后果/选项显示分类标签，其余自然流动 */
export const SHOW_BEAT_LABEL: Set<NarrativeBlockKind> = new Set([
  "world",
  "consequence",
  "choices",
]);

function classifyParagraph(el: Element): { kind: NarrativeBlockKind; speaker?: string } {
  const cls = el.className || "";
  const text = stripTags(el.innerHTML);

  if (cls.includes("choice-transition") || cls.includes("choice-prompt")) {
    return { kind: "choices" };
  }
  if (cls.includes("scene")) {
    return { kind: "scene" };
  }
  if (cls.includes("result")) {
    return { kind: "result" };
  }
  if (cls.includes("consequence")) {
    return { kind: "consequence" };
  }
  if (cls.includes("world")) {
    return { kind: "world" };
  }
  if (cls.includes("dialogue")) {
    const m = text.match(/^(.+?)[:：]\s*[「『]/);
    if (m) return { kind: "npc", speaker: m[1].replace(/^【|】$/g, "") };
    return { kind: "dialogue" };
  }
  if (cls.includes("world-brief") || cls.includes("offline-summary")) {
    return { kind: "world" };
  }
  if (cls.includes("chapter-epigraph")) {
    return { kind: "system" };
  }

  const speakerBracket = text.match(/^【([^】]+)】/);
  if (speakerBracket) {
    return { kind: "npc", speaker: speakerBracket[1] };
  }

  if (/线索|感知|额外|你注意到|检定成功|检定失败|DC/.test(text)) {
    return { kind: "perception" };
  }
  if (/【世界】|村庄恐慌|危机|传闻/.test(text)) {
    return { kind: "world" };
  }
  if (text.startsWith("你") && text.length < 120) {
    return { kind: "result" };
  }

  return { kind: "scene" };
}

function classifyContainer(el: Element): NarrativeBlockKind {
  if (el.classList.contains("choice-block")) {
    return "choices";
  }
  if (el.classList.contains("world-briefing") || el.classList.contains("offline-summary")) {
    return "world";
  }
  return "scene";
}

function parseChoicesFromDom(root: Element): InlineChoice[] {
  const items = root.querySelectorAll(".choice-item");
  const choices: InlineChoice[] = [];
  items.forEach((li) => {
    const id = li.getAttribute("data-choice-id") || "";
    const input = li.getAttribute("data-input") || "";
    const isFree = li.getAttribute("data-free") === "true";
    const text = stripTags(li.querySelector(".choice-text")?.innerHTML || li.innerHTML);
    choices.push({
      id,
      text,
      input,
      is_free: isFree,
    });
  });
  return choices;
}

/** 将后端 HTML 叙事拆成节奏化块 */
export function parseNarrativeHtml(html: string, _entryKind?: string): NarrativeBlock[] {
  if (!html?.trim()) return [];

  const wrapped = `<div id="narr-root">${html}</div>`;
  const doc = new DOMParser().parseFromString(wrapped, "text/html");
  const root = doc.getElementById("narr-root");
  if (!root) {
    return [{ id: "fallback-0", kind: "scene", html }];
  }

  const blocks: NarrativeBlock[] = [];
  let idx = 0;

  const push = (kind: NarrativeBlockKind, node: Element, speaker?: string) => {
    blocks.push({
      id: `b-${idx++}`,
      kind,
      html: node.outerHTML,
      speaker,
    });
  };

  for (const child of Array.from(root.children)) {
    const tag = child.tagName.toLowerCase();
    if (tag === "p") {
      const { kind, speaker } = classifyParagraph(child);
      push(kind, child, speaker);
    } else if (tag === "div") {
      const kind = classifyContainer(child);
      push(kind, child);
    } else if (tag === "ol" && child.classList.contains("choice-list")) {
      push("choices", child);
    } else {
      push("scene", child);
    }
  }

  if (blocks.length === 0) {
    blocks.push({ id: "b-0", kind: "scene", html });
  }

  return blocks;
}

export function extractChoicesFromHtml(html: string): InlineChoice[] {
  const wrapped = `<div id="narr-root">${html}</div>`;
  const doc = new DOMParser().parseFromString(wrapped, "text/html");
  const root = doc.getElementById("narr-root");
  if (!root) return [];
  return parseChoicesFromDom(root);
}
