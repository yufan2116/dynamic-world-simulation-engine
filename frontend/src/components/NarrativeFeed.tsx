import { useEffect, useRef } from "react";
import type { InlineChoice, StoryEntry } from "../types";
import { SHOW_BEAT_LABEL } from "../lib/parseNarrative";

const KIND_LABEL: Record<string, string> = {
  scene: "场景",
  result: "结果",
  npc: "人物",
  dialogue: "对话",
  consequence: "后果",
  world: "世界",
  perception: "感知",
  choices: "你现在可以",
  system: "系统",
};

const KIND_CLASS: Record<string, string> = {
  scene: "narr-beat-scene",
  result: "narr-beat-result",
  npc: "narr-beat-npc",
  dialogue: "narr-beat-dialogue",
  consequence: "narr-beat-consequence",
  world: "narr-beat-world",
  perception: "narr-beat-perception",
  choices: "narr-beat-choices",
  system: "narr-beat-system",
};

interface Props {
  entries: StoryEntry[];
  loading?: boolean;
  disabled?: boolean;
  onSelectChoice?: (input: string, choice: InlineChoice) => void;
  onFocusFreeInput?: () => void;
}

function InlineChoiceList({
  choices,
  transition,
  disabled,
  onSelectChoice,
  onFocusFreeInput,
}: {
  choices: InlineChoice[];
  transition?: string;
  disabled?: boolean;
  onSelectChoice?: (input: string, choice: InlineChoice) => void;
  onFocusFreeInput?: () => void;
}) {
  if (!choices.length) return null;

  return (
    <article className="narr-beat narr-beat-choices rounded-lg border px-3 py-3">
      {transition && (
        <p className="text-sm text-fantasy-text/90 mb-2 leading-relaxed choice-transition">
          {transition}
        </p>
      )}
      <p className="text-xs text-fantasy-gold/90 mb-2 tracking-wide">你现在可以：</p>
      <ol className="choice-list space-y-1.5 list-none m-0 p-0">
        {choices.map((ch, i) => (
          <li key={ch.id || i}>
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                if (ch.is_free) {
                  onFocusFreeInput?.();
                } else if (ch.input) {
                  onSelectChoice?.(ch.input, ch);
                }
              }}
              className="choice-item-btn w-full text-left text-sm px-2.5 py-2 rounded-md border border-fantasy-border/50 bg-black/30 hover:border-fantasy-gold/60 hover:bg-fantasy-gold/10 disabled:opacity-40 transition leading-snug"
            >
              <span className="text-fantasy-gold/80 mr-1.5">{i + 1}.</span>
              <span className="text-fantasy-text">{ch.text}</span>
            </button>
          </li>
        ))}
      </ol>
    </article>
  );
}

export default function NarrativeFeed({
  entries,
  loading,
  disabled,
  onSelectChoice,
  onFocusFreeInput,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, loading]);

  const activeChoiceIdx = (() => {
    for (let i = entries.length - 1; i >= 0; i--) {
      if (entries[i].kind === "prologue") continue;
      return i;
    }
    return -1;
  })();
  const activeChoiceEntry =
    activeChoiceIdx >= 0 ? entries[activeChoiceIdx] : null;
  const showActiveChoices = Boolean(activeChoiceEntry?.inline_choices?.length);

  return (
    <section className="narrative-feed flex flex-col flex-1 min-h-0 rounded-lg border border-fantasy-border/80 bg-black/40 text-fantasy-text overflow-hidden">
      <header className="px-4 py-2.5 border-b border-fantasy-border/60 bg-fantasy-panel/50 shrink-0">
        <h2 className="text-xs tracking-[0.25em] uppercase text-fantasy-muted">叙事流</h2>
      </header>

      <div className="flex-1 overflow-y-auto px-3 md:px-5 py-4 space-y-4">
        {entries.length === 0 && !loading && (
          <p className="text-fantasy-muted text-sm italic text-center py-8">冒险尚未开始…</p>
        )}

        {entries.map((entry, entryIndex) => {
          const isActiveChoiceRow = entryIndex === activeChoiceIdx;
          const skipInlineChoices = isActiveChoiceRow && showActiveChoices;

          return (
            <div key={entry.id} className="narr-entry space-y-2">
              {entry.kind === "prologue" && (
                <p className="text-[10px] text-fantasy-gold/70 tracking-widest uppercase">序幕</p>
              )}
              {(entry.blocks ?? []).map((block) => {
                if (skipInlineChoices && block.kind === "choices") {
                  return null;
                }
                const showLabel = SHOW_BEAT_LABEL.has(block.kind);
                return (
                  <article
                    key={block.id}
                    className={`narr-beat rounded-lg border px-3 py-2.5 ${KIND_CLASS[block.kind] ?? "narr-beat-scene"}`}
                  >
                    {showLabel && (
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="narr-beat-label text-[9px] uppercase tracking-wider">
                          {block.speaker ? `【${block.speaker}】` : KIND_LABEL[block.kind] ?? block.kind}
                        </span>
                      </div>
                    )}
                    {block.kind === "dialogue" || block.kind === "npc" ? (
                      <div
                        className="story-content narr-beat-body text-sm leading-relaxed text-fantasy-text/95"
                        dangerouslySetInnerHTML={{ __html: block.html }}
                      />
                    ) : block.kind !== "choices" ? (
                      <div
                        className="story-content narr-beat-body text-sm leading-relaxed text-fantasy-text/95 narr-beat-natural"
                        dangerouslySetInnerHTML={{ __html: block.html }}
                      />
                    ) : null}
                  </article>
                );
              })}
              {!entry.blocks?.length && (
                <article
                  className={`narr-beat rounded-lg border px-3 py-2.5 ${
                    entry.kind === "prologue" ? "narr-beat-scene opening-prose" : "narr-beat-scene"
                  }`}
                >
                  <div
                    className="story-content text-sm leading-relaxed narr-beat-natural"
                    dangerouslySetInnerHTML={{ __html: entry.text }}
                  />
                </article>
              )}
              {isActiveChoiceRow &&
                entry.inline_choices &&
                entry.inline_choices.length > 0 && (
                <InlineChoiceList
                  choices={entry.inline_choices}
                  transition={entry.choice_transition}
                  disabled={disabled}
                  onSelectChoice={onSelectChoice}
                  onFocusFreeInput={onFocusFreeInput}
                />
              )}
            </div>
          );
        })}

        {loading && (
          <p className="text-fantasy-accent text-sm animate-pulse text-center py-3">
            正在渲染场景…
          </p>
        )}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}
