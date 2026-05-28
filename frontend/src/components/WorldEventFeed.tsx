import type { FeedItem } from "../lib/worldEvents";
import { eventCategoryLabel } from "../lib/ontology";

const DEFAULT_CAT_STYLE: Record<FeedItem["category"], { label: string; className: string }> = {
  world: { label: "世界", className: "text-emerald-400/90" },
  rumor: { label: "传闻", className: "text-amber-300/90" },
  npc: { label: "人物", className: "text-violet-300/90" },
  system: { label: "系统", className: "text-fantasy-muted" },
  crisis: { label: "危机", className: "text-red-400/90" },
};

interface Props {
  items: FeedItem[];
  pulseTitle?: string;
  emptyText?: string;
  categoryLabels?: Record<string, string>;
}

export default function WorldEventFeed({
  items,
  pulseTitle = "世界脉搏",
  emptyText = "世界尚在沉睡，等待第一个涟漪……",
  categoryLabels,
}: Props) {
  const catStyle = (cat: FeedItem["category"]) => {
    const label = eventCategoryLabel(
      categoryLabels ? { ui: { event_categories: categoryLabels } } : null,
      cat,
      DEFAULT_CAT_STYLE[cat]?.label ?? cat
    );
    return {
      label,
      className: DEFAULT_CAT_STYLE[cat]?.className ?? "text-fantasy-muted",
    };
  };

  return (
    <div className="rounded-lg border border-fantasy-border/60 bg-black/35 overflow-hidden flex flex-col min-h-[140px] max-h-[220px]">
      <h3 className="text-[10px] uppercase tracking-widest text-fantasy-accent px-3 py-2 border-b border-fantasy-border/40 shrink-0">
        {pulseTitle}
      </h3>
      <ul className="flex-1 overflow-y-auto px-2 py-2 space-y-1.5 text-[11px]">
        {items.length === 0 ? (
          <li className="text-fantasy-muted italic px-1 py-2">{emptyText}</li>
        ) : (
          items.map((item) => {
            const meta = catStyle(item.category);
            return (
              <li
                key={item.id}
                className="flex gap-2 rounded px-2 py-1.5 bg-black/25 border border-fantasy-border/20 animate-fade-in"
              >
                <span className={`shrink-0 font-medium ${meta.className}`}>[{meta.label}]</span>
                <span className="text-fantasy-text/85 leading-snug">{item.text}</span>
              </li>
            );
          })
        )}
      </ul>
    </div>
  );
}
