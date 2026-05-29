import { useEffect, useMemo, useState } from "react";
import { fetchBranches, fetchGameState, fetchInspector, forkFromTurn, rewindToTurn } from "../api";
import type { GameStateResponse, InspectorResponse } from "../types";

function pretty(v: unknown): string {
  try {
    return JSON.stringify(v, null, 2);
  } catch {
    return String(v);
  }
}

function Section({
  title,
  value,
  mono,
}: {
  title: string;
  value: unknown;
  mono?: boolean;
}) {
  return (
    <section className="rounded-lg border border-fantasy-border/70 bg-black/30 overflow-hidden">
      <header className="px-3 py-2 border-b border-fantasy-border/60 flex items-center justify-between gap-2">
        <h3 className="text-[11px] tracking-[0.2em] uppercase text-fantasy-muted">
          {title}
        </h3>
      </header>
      <div className="p-3">
        {value == null || value === "" ? (
          <p className="text-xs text-fantasy-muted italic">（本回合无数据）</p>
        ) : mono ? (
          <pre className="text-[11px] leading-relaxed whitespace-pre-wrap break-words text-fantasy-text/90 font-mono">
            {String(value)}
          </pre>
        ) : (
          <pre className="text-[11px] leading-relaxed whitespace-pre-wrap break-words text-fantasy-text/90 font-mono">
            {pretty(value)}
          </pre>
        )}
      </div>
    </section>
  );
}

export default function DebugInspector({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [data, setData] = useState<InspectorResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [turn, setTurn] = useState<number | null>(null);
  const [branchesText, setBranchesText] = useState<string>("");
  const [liveState, setLiveState] = useState<GameStateResponse | null>(null);
  const turns = data?.turns ?? [];

  const activeTurn = useMemo(() => {
    if (turn != null) return turn;
    if (data?.turn != null) return data.turn;
    return turns.length ? turns[turns.length - 1] : null;
  }, [turn, data?.turn, turns]);

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    fetchInspector()
      .then((r) => {
        setData(r);
        setTurn(r.turn ?? null);
      })
      .finally(() => setLoading(false));

    fetchBranches()
      .then((r) => setBranchesText(JSON.stringify(r.branches, null, 2)))
      .catch(() => setBranchesText(""));

    fetchGameState()
      .then((s) => setLiveState(s))
      .catch(() => setLiveState(null));
  }, [open]);

  useEffect(() => {
    if (!open) return;
    if (activeTurn == null) return;
    setLoading(true);
    fetchInspector(activeTurn)
      .then((r) => {
        setData(r);
      })
      .finally(() => setLoading(false));
  }, [open, activeTurn]);

  if (!open) return null;

  const blocks = data?.blocks ?? {};

  return (
    <div className="fixed inset-0 z-[60] flex">
      <button
        type="button"
        onClick={onClose}
        className="absolute inset-0 bg-black/70"
        aria-label="Close inspector"
      />

      <aside className="relative ml-auto w-full max-w-[960px] h-full border-l border-fantasy-border bg-fantasy-panel/95 backdrop-blur-xl flex flex-col">
        <header className="px-4 py-3 border-b border-fantasy-border/60 flex items-center justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[10px] text-fantasy-muted tracking-[0.35em] uppercase">
              Debug / Inspector
            </p>
            <p className="text-xs text-fantasy-text/90 mt-0.5">
              回合证据链：Intent → Rule → Tick → Graph/Beats → Prompt → Narrative
            </p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              disabled={activeTurn == null || activeTurn <= 1}
              onClick={() => {
                if (activeTurn == null) return;
                setLoading(true);
                rewindToTurn(Math.max(1, activeTurn - 1))
                  .then(() => fetchInspector(activeTurn - 1))
                  .then((r) => {
                    setData(r);
                    setTurn(r.turn ?? (activeTurn - 1));
                  })
                  .finally(() => setLoading(false));
              }}
              className="text-xs px-2.5 py-1 rounded-md border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60 disabled:opacity-40"
            >
              回到上一步
            </button>
            <button
              type="button"
              disabled={activeTurn == null}
              onClick={() => {
                if (activeTurn == null) return;
                setLoading(true);
                forkFromTurn(activeTurn, `fork@${activeTurn}`)
                  .then(() => fetchInspector(activeTurn))
                  .then((r) => {
                    setData(r);
                    setTurn(r.turn ?? activeTurn);
                  })
                  .finally(() => setLoading(false));
              }}
              className="text-xs px-2.5 py-1 rounded-md border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60 disabled:opacity-40"
            >
              从此回合分叉
            </button>
            <select
              className="text-xs rounded-md bg-black/40 border border-fantasy-border px-2 py-1"
              value={activeTurn ?? ""}
              onChange={(e) => setTurn(Number(e.target.value))}
              disabled={!turns.length}
            >
              {turns.map((t) => (
                <option key={t} value={t}>
                  Turn {t}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                if (activeTurn != null) {
                  setLoading(true);
                  fetchInspector(activeTurn)
                    .then((r) => setData(r))
                    .finally(() => setLoading(false));
                }
              }}
              className="text-xs px-2.5 py-1 rounded-md border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60"
            >
              刷新
            </button>
            <button
              type="button"
              onClick={onClose}
              className="text-xs px-2.5 py-1 rounded-md border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60"
            >
              关闭
            </button>
          </div>
        </header>

        <div className="px-4 py-3 overflow-y-auto flex-1 space-y-3">
          {loading && (
            <p className="text-xs text-fantasy-accent animate-pulse">
              正在加载 inspector…
            </p>
          )}

          {!data?.initialized && (
            <p className="text-xs text-fantasy-muted">
              还没有会话数据（请先开始游戏并执行至少一次行动）。
            </p>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Section title="Intent Parser" value={blocks.intent_parser} />
            <Section title="Rule Result (D20)" value={blocks.rule_result} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Section title="World Tick" value={blocks.world_tick} />
            <Section title="World Change (raw)" value={blocks.world_change} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Section title="Scene Graph" value={blocks.scene_graph} />
            <Section title="Event Beats" value={blocks.event_beats} />
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Section
              title="Player Knowledge (debug)"
              value={liveState?.world_state?.flags?.player_knowledge ?? liveState?.player_knowledge}
            />
            <Section
              title="NPC Profiles / Activities (debug)"
              value={{
                npc_profiles: liveState?.world_state?.flags?.npc_profiles,
                npc_current_actions: liveState?.world_state?.flags?.npc_current_actions,
                npc_memories: liveState?.npc_memories,
              }}
            />
          </div>
          <Section
            title="Available Followups / Hidden (debug)"
            value={
              (liveState?.world_state?.flags?.player_knowledge as { available_followups?: unknown })
                ?.available_followups
            }
          />

          <Section title="LLM Prompt (proof)" value={blocks.llm_prompt} />
          <Section title="Final Narrative (HTML)" value={blocks.final_narrative} mono />
          <Section title="Narrative SHA256" value={blocks.narrative_sha256} />
          <Section title="Raw Events (this turn)" value={data?.raw_events} />
          <Section title="Branches (debug)" value={branchesText} mono />
        </div>
      </aside>
    </div>
  );
}

