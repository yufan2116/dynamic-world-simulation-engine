import { useEffect, useRef, useState } from "react";
import type { InlineChoice, StoryEntry } from "../types";
import { polishChoiceLabel, polishNarrativeHtml } from "../lib/formatNarrative";
import { SHOW_BEAT_LABEL } from "../lib/parseNarrative";

const KIND_LABEL: Record<string, string> = {
  "player-action": "你的行动",
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
  "player-action": "narr-beat-player-action border-l-2 border-fantasy-accent/70 bg-fantasy-accent/10",
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
  investigationGuidance?: string | null;
  hideChoicePanel?: boolean;
  onSelectChoice?: (input: string, choice: InlineChoice) => void;
  onFocusFreeInput?: () => void;
}

export function InlineChoiceList({
  choices,
  disabled,
  investigationGuidance,
  onSelectChoice,
  onFocusFreeInput,
  compact,
}: {
  choices: InlineChoice[];
  disabled?: boolean;
  investigationGuidance?: string | null;
  onSelectChoice?: (input: string, choice: InlineChoice) => void;
  onFocusFreeInput?: () => void;
  compact?: boolean;
}) {
  if (!choices.length) return null;

  const unlocked = choices.filter((c) => !c.disabled && !c.is_free);

  return (
    <article
      className={`narr-beat-choices ${compact ? "px-0" : "mt-3 pt-3 border-t border-fantasy-border/30 px-1"}`}
    >
      <p className="text-xs text-fantasy-muted/90 mb-2 tracking-wide italic">
        {unlocked.length > 0
          ? `下一步调查（${unlocked.length} 项可选）——`
          : "暂无新调查点——"}
      </p>
      {unlocked.length === 0 && investigationGuidance && (
        <p className="text-xs text-amber-200/80 mb-2 leading-relaxed">{investigationGuidance}</p>
      )}
      <ol className="choice-list space-y-1.5 list-none m-0 p-0">
        {choices.map((ch, i) => (
          <li key={ch.id || i}>
            <button
              type="button"
              disabled={disabled || ch.disabled}
              onClick={() => {
                if (ch.disabled) return;
                if (ch.is_free) {
                  onFocusFreeInput?.();
                  return;
                }
                onSelectChoice?.(ch.input || ch.text || ch.id || "", ch);
              }}
              className={`choice-item-btn w-full text-left text-sm px-2.5 py-2 rounded-md border transition leading-snug ${
                ch.disabled
                  ? "border-fantasy-border/25 bg-black/15 opacity-50 cursor-not-allowed"
                  : "border-fantasy-border/50 bg-black/30 hover:border-fantasy-gold/60 hover:bg-fantasy-gold/10 disabled:opacity-40"
              }`}
            >
              <span className="text-fantasy-gold/80 mr-1.5">{i + 1}.</span>
              <span className={`block ${ch.disabled ? "text-fantasy-muted line-through" : "text-fantasy-text"}`}>
                {polishChoiceLabel(ch.text)}
              </span>
              {ch.disabled && ch.lock_reason && (
                <span className="block text-[10px] text-fantasy-muted/80 mt-0.5">{ch.lock_reason}</span>
              )}
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
  investigationGuidance,
  hideChoicePanel,
  onSelectChoice,
  onFocusFreeInput,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const latestEntryRef = useRef<HTMLDivElement>(null);
  const prevLoadingRef = useRef(Boolean(loading));
  const prevEntryCountRef = useRef(entries.length);
  const [highlightLatest, setHighlightLatest] = useState(false);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const activeChoiceIdx = (() => {
    for (let i = entries.length - 1; i >= 0; i--) {
      if (entries[i].kind === "prologue") continue;
      return i;
    }
    return -1;
  })();
  const activeChoiceEntry =
    activeChoiceIdx >= 0 ? entries[activeChoiceIdx] : null;
  const activeChoices = activeChoiceEntry?.inline_choices ?? [];
  const showActiveChoices = !hideChoicePanel && activeChoices.length > 0;
  const latestIdx = entries.length > 0 ? entries.length - 1 : -1;

  /** 行动完成后：滚到最新叙事（非选项区），并短暂高亮 */
  useEffect(() => {
    const wasLoading = prevLoadingRef.current;
    prevLoadingRef.current = Boolean(loading);

    if (loading) return;

    const entryCount = entries.length;
    const grew = entryCount > prevEntryCountRef.current;
    prevEntryCountRef.current = entryCount;

    const shouldScroll = wasLoading && grew;
    if (!shouldScroll) return;

    const scrollToLatest = () => {
      const target = latestEntryRef.current;
      if (!target) return;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      setHighlightLatest(true);
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
      highlightTimerRef.current = setTimeout(() => setHighlightLatest(false), 1500);
    };

    requestAnimationFrame(() => {
      requestAnimationFrame(scrollToLatest);
    });
  }, [loading, entries.length]);

  useEffect(
    () => () => {
      if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    },
    []
  );

  return (
    <section className="narrative-feed flex flex-col flex-1 min-h-0 rounded-lg border border-fantasy-border/50 bg-[#12100e]/90 text-fantasy-text overflow-hidden shadow-inner">
      <header className="px-4 py-2.5 border-b border-fantasy-border/40 shrink-0">
        <h2 className="text-xs tracking-[0.2em] text-fantasy-muted/80 font-serif">冒险日志</h2>
      </header>

      <div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-y-contain touch-pan-y px-3 md:px-5 py-4 space-y-5"
      >
        {entries.length === 0 && !loading && (
          <p className="text-fantasy-muted text-sm italic text-center py-8">冒险尚未开始…</p>
        )}

        {entries.map((entry, entryIndex) => {
          const isActiveChoiceRow = entryIndex === activeChoiceIdx;
          const skipInlineChoices = isActiveChoiceRow && showActiveChoices;
          const isLatest = entryIndex === latestIdx;
          const isLatestStory = isLatest && entry.kind !== "prologue";

          return (
            <div
              key={entry.id}
              id={isLatestStory ? "latest-story-entry" : undefined}
              ref={isLatestStory ? latestEntryRef : undefined}
              className={`narr-entry space-y-2 scroll-mt-3 ${
                highlightLatest && isLatestStory
                  ? "narr-entry-latest-highlight"
                  : isLatestStory
                    ? "rounded-lg border border-fantasy-gold/15 bg-fantasy-gold/[0.02] px-2 py-2 -mx-1"
                    : ""
              }`}
            >
              {entry.kind === "prologue" && (
                <p className="text-[10px] text-fantasy-gold/70 tracking-widest uppercase">序幕</p>
              )}
              {isLatest && entry.kind !== "prologue" && entry.turn != null && (
                <p className="text-[10px] text-fantasy-gold/60 tracking-widest">
                  第 {entry.turn} 回合
                </p>
              )}
              {(entry.blocks ?? []).map((block) => {
                if (skipInlineChoices && block.kind === "choices") {
                  return null;
                }
                const showLabel = SHOW_BEAT_LABEL.has(block.kind);
                return (
                  <article
                    key={block.id}
                    className={`narr-beat px-1 py-1.5 ${block.kind === "choices" ? KIND_CLASS.choices : "narr-beat-natural"}`}
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
                        dangerouslySetInnerHTML={{ __html: polishNarrativeHtml(block.html) }}
                      />
                    ) : block.kind !== "choices" ? (
                      <div
                        className="story-content narr-beat-body text-sm leading-relaxed text-fantasy-text/95 narr-beat-natural"
                        dangerouslySetInnerHTML={{ __html: polishNarrativeHtml(block.html) }}
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
            </div>
          );
        })}

        {loading && (
          <p className="text-fantasy-accent text-sm animate-pulse text-center py-3">
            正在渲染场景…
          </p>
        )}

        {showActiveChoices && activeChoiceEntry?.choice_transition && (
          <p className="text-sm text-fantasy-text/80 leading-relaxed italic border-l-2 border-fantasy-border/50 pl-3">
            {activeChoiceEntry.choice_transition}
          </p>
        )}

        {showActiveChoices && (
          <div
            className="narr-choices-anchor pt-4 pb-6 mt-2 border-t border-fantasy-gold/25"
            aria-label="可选行动"
          >
            <InlineChoiceList
              choices={activeChoices}
              disabled={disabled}
              investigationGuidance={investigationGuidance}
              onSelectChoice={onSelectChoice}
              onFocusFreeInput={onFocusFreeInput}
              compact
            />
          </div>
        )}
      </div>
    </section>
  );
}
