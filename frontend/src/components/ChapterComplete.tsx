import type { SessionSummary } from "../types";

interface ChapterCompleteProps {
  summary: SessionSummary;
  onRestartDemo?: () => void;
  onNewGame?: () => void;
  onViewAdventureLog?: () => void;
  loading?: boolean;
}

function legacyTimeline(summary: SessionSummary) {
  if (summary.timeline?.length) return summary.timeline;
  return (summary.key_choices ?? []).map((c) => ({
    turn: c.turn,
    title: c.label,
  }));
}

function legacyClueCards(summary: SessionSummary) {
  if (summary.clue_cards?.length) return summary.clue_cards;
  return (summary.clues?.discovered ?? []).map((text) => ({ text }));
}

function legacyNpcRelations(summary: SessionSummary) {
  const rows = summary.npc_relationships ?? [];
  return rows.map((n) => {
    if ("status" in n && typeof n.status === "string") {
      return { name: n.name, status: n.status, detail: n.detail };
    }
    const legacy = n as { name: string; attitude: string; value: number };
    return {
      name: legacy.name,
      status: legacy.attitude,
      detail: `与你建立了 ${legacy.attitude} 的关系`,
    };
  });
}

export default function ChapterComplete({
  summary,
  onRestartDemo,
  onNewGame,
  onViewAdventureLog,
  loading = false,
}: ChapterCompleteProps) {
  const { chapter, ending, player_stats } = summary;
  const timeline = legacyTimeline(summary);
  const clueCards = legacyClueCards(summary);
  const npcRelations = legacyNpcRelations(summary);
  const endingSummary = summary.ending_summary || ending?.summary || ending?.subtitle;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/88 backdrop-blur-sm overflow-y-auto"
      role="dialog"
      aria-labelledby="chapter-complete-title"
    >
      <article className="w-full max-w-3xl rounded-xl border border-fantasy-border bg-[#14100c] shadow-2xl">
        <header className="border-b border-fantasy-border/50 px-6 py-6 text-center bg-gradient-to-b from-[#1c1610] to-transparent">
          <p className="text-[10px] tracking-[0.4em] uppercase text-fantasy-muted mb-2">
            章节完成
          </p>
          <h1
            id="chapter-complete-title"
            className="text-2xl md:text-3xl font-serif text-fantasy-gold"
          >
            {chapter?.title ?? "失踪的商人"}
          </h1>
          {ending?.epigraph && (
            <p className="mt-2 text-sm text-fantasy-muted italic">{ending.epigraph}</p>
          )}
          <h2 className="mt-4 text-xl text-amber-100 font-serif">{ending?.title}</h2>
          {ending?.subtitle && (
            <p className="text-sm text-fantasy-muted mt-1">{ending.subtitle}</p>
          )}
        </header>

        <div className="px-6 py-5 space-y-7 text-sm text-amber-50/90 max-h-[62vh] overflow-y-auto">
          {endingSummary && (
            <section className="chapter-complete-summary">
              <h3 className="text-xs tracking-widest uppercase text-fantasy-gold mb-2">
                结局摘要
              </h3>
              <p className="leading-relaxed text-amber-50/85">{endingSummary}</p>
            </section>
          )}

          {timeline.length > 0 && (
            <section>
              <h3 className="text-xs tracking-widest uppercase text-fantasy-gold mb-3">
                调查时间线
              </h3>
              <ol className="space-y-0 border-l border-fantasy-border/40 ml-2 pl-4">
                {timeline.map((step, i) => (
                  <li key={`${step.turn}-${i}`} className="relative pb-4 last:pb-0">
                    <span className="absolute -left-[1.35rem] top-1.5 h-2 w-2 rounded-full bg-fantasy-gold/70" />
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                      <span className="text-[10px] tracking-wider uppercase text-fantasy-muted">
                        第 {step.turn} 步
                      </span>
                      <span className="text-amber-50/90">{step.title}</span>
                    </div>
                    {step.check && (
                      <p
                        className={`text-xs mt-1 ${
                          step.check_success === false ? "text-red-300/80" : "text-emerald-300/80"
                        }`}
                      >
                        {step.check}
                      </p>
                    )}
                    {step.clue && (
                      <p className="text-xs mt-1 text-fantasy-gold/80 italic">→ {step.clue}</p>
                    )}
                  </li>
                ))}
              </ol>
            </section>
          )}

          {clueCards.length > 0 && (
            <section>
              <h3 className="text-xs tracking-widest uppercase text-fantasy-gold mb-3">
                关键线索
              </h3>
              <div className="grid sm:grid-cols-2 gap-2.5">
                {clueCards.map((card, i) => (
                  <div
                    key={`${card.text}-${i}`}
                    className="rounded-lg border border-emerald-900/50 bg-emerald-950/20 px-3 py-2.5"
                  >
                    <p className="text-emerald-100/90 leading-snug">{card.text}</p>
                  </div>
                ))}
              </div>
            </section>
          )}

          {npcRelations.length > 0 && (
            <section>
              <h3 className="text-xs tracking-widest uppercase text-fantasy-gold mb-3">
                人物关系
              </h3>
              <div className="grid sm:grid-cols-3 gap-2.5">
                {npcRelations.map((n) => (
                  <div
                    key={n.name}
                    className="rounded-lg border border-fantasy-border/40 bg-black/20 px-3 py-3"
                  >
                    <div className="font-medium text-amber-100">{n.name}</div>
                    <div className="text-xs text-fantasy-gold mt-0.5">{n.status}</div>
                    {n.detail && (
                      <p className="text-xs text-fantasy-muted mt-1.5 leading-snug">{n.detail}</p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {player_stats && (
            <section>
              <h3 className="text-xs tracking-widest uppercase text-fantasy-gold mb-3">
                调查统计
              </h3>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <Stat label="调查步数" value={String(player_stats.turns)} />
                <Stat label="线索收集" value={String(player_stats.clues_found)} />
                {player_stats.checks_passed != null && (
                  <Stat label="检定成功" value={String(player_stats.checks_passed)} />
                )}
                {player_stats.checks_failed != null && player_stats.checks_failed > 0 && (
                  <Stat label="检定失败" value={String(player_stats.checks_failed)} />
                )}
                {player_stats.crisis_label && (
                  <Stat label="村庄危机" value={player_stats.crisis_label} />
                )}
              </div>
            </section>
          )}
        </div>

        <footer className="border-t border-fantasy-border/50 px-6 py-4 flex flex-wrap gap-3 justify-center bg-[#0f0c09]">
          {onViewAdventureLog && (
            <button
              type="button"
              disabled={loading}
              onClick={onViewAdventureLog}
              className="px-4 py-2 rounded border border-fantasy-border text-amber-100/90 text-sm hover:bg-white/5 disabled:opacity-50"
            >
              查看完整冒险日志
            </button>
          )}
          {onRestartDemo && (
            <button
              type="button"
              disabled={loading}
              onClick={onRestartDemo}
              className="px-4 py-2 rounded border border-fantasy-gold/60 text-fantasy-gold text-sm hover:bg-fantasy-gold/10 disabled:opacity-50"
            >
              再玩一遍演示
            </button>
          )}
          {onNewGame && (
            <button
              type="button"
              disabled={loading}
              onClick={onNewGame}
              className="px-4 py-2 rounded border border-fantasy-border text-fantasy-muted text-sm hover:text-amber-100 disabled:opacity-50"
            >
              随机新局
            </button>
          )}
        </footer>
      </article>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded border border-fantasy-border/30 px-3 py-2 text-center bg-black/15">
      <div className="text-lg text-amber-100 font-serif">{value}</div>
      <div className="text-[10px] text-fantasy-muted mt-0.5">{label}</div>
    </div>
  );
}
