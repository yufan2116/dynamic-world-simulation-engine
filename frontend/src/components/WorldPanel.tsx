import type { FeedItem } from "../lib/worldEvents";
import { getOntologyFromState, tensionFromState, uiTerm } from "../lib/ontology";
import type { CrisisState, GameState } from "../types";
import WorldEventFeed from "./WorldEventFeed";

interface Props {
  worldState: GameState | null;
  crisisState?: CrisisState | null;
  eventFeed?: FeedItem[];
}

function Meter({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="mb-2">
      <div className="flex justify-between text-[10px] mb-0.5">
        <span className="text-fantasy-muted">{label}</span>
        <span>{Math.round(value)}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-black/50 overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
    </div>
  );
}

export default function WorldPanel({ worldState, crisisState, eventFeed = [] }: Props) {
  if (!worldState) {
    return (
      <aside className="h-full rounded-lg border border-fantasy-border bg-fantasy-panel/80 p-4">
        <p className="text-fantasy-muted text-sm">加载世界中…</p>
      </aside>
    );
  }

  const onto = getOntologyFromState(worldState) ?? crisisState?.ontology ?? null;
  const flags = worldState.flags || {};
  const tension = tensionFromState(worldState);
  const warRisk = Number(flags.war_risk ?? 25);
  const crisis = crisisState;
  const economy = (flags.economy as Record<string, number>) || {};

  const economyLine = (() => {
    const metrics = (onto?.terms as { economy?: { metrics?: { key: string; label: string }[] } })
      ?.economy?.metrics;
    if (!metrics?.length) return null;
    return metrics
      .slice(0, 2)
      .map((m) => `${m.label} ${economy[m.key] ?? "—"}`)
      .join(" · ");
  })();

  return (
    <aside className="h-full flex flex-col rounded-lg border border-fantasy-border bg-fantasy-panel/90 p-3 shadow-lg overflow-hidden gap-3">
      <h2 className="font-fantasy text-fantasy-gold text-sm tracking-widest shrink-0">
        {uiTerm(onto, "world_panel_title", "世界态势")}
      </h2>

      <WorldEventFeed
        items={eventFeed}
        pulseTitle={uiTerm(onto, "world_pulse", "世界脉搏")}
        emptyText={uiTerm(onto, "world_pulse_empty", "世界尚在沉睡……")}
        categoryLabels={
          (onto?.ui?.event_categories as Record<string, string> | undefined) ?? undefined
        }
      />

      {crisis && (
        <div className="rounded-lg border border-amber-900/40 bg-amber-950/20 p-2.5 shrink-0">
          <p className="text-[10px] text-amber-200/80 uppercase tracking-wider mb-0.5">
            {crisis.crisis_title ?? uiTerm(onto, "crisis_block_title", "危机")}
          </p>
          <p className="text-xs text-amber-100 font-medium">{crisis.level_label}</p>
          <p className="text-[10px] text-fantasy-muted mt-0.5">{crisis.merchant_status_label}</p>
          <Meter
            label={uiTerm(onto, "crisis_pressure", "危机压力")}
            value={crisis.pressure}
            color={
              crisis.pressure > 65 ? "bg-red-500" : crisis.pressure > 40 ? "bg-amber-500" : "bg-emerald-600"
            }
          />
        </div>
      )}

      <Meter
        label={uiTerm(onto, "tension_meter", "社会紧张")}
        value={tension}
        color={tension > 60 ? "bg-red-500" : "bg-amber-500"}
      />
      <Meter
        label={uiTerm(onto, "conflict_meter", "冲突风险")}
        value={warRisk}
        color="bg-red-600"
      />

      {crisis && crisis.suspicious_clues.length > 0 && (
        <div className="shrink-0">
          <h3 className="text-fantasy-accent text-[10px] mb-1">
            {uiTerm(onto, "suspicious_clues", "可疑线索")}
          </h3>
          <ul className="text-[10px] space-y-0.5 text-fantasy-muted max-h-14 overflow-y-auto">
            {crisis.suspicious_clues.slice(-3).map((c, i) => (
              <li key={i}>◆ {c}</li>
            ))}
          </ul>
        </div>
      )}

      {economyLine && (
        <p className="text-[10px] text-fantasy-muted shrink-0">{economyLine}</p>
      )}

      <div className="flex-1 min-h-0 overflow-y-auto">
        <h3 className="text-fantasy-accent text-[10px] mb-1.5">
          {uiTerm(onto, "current_quest", "当前任务")}
        </h3>
        {worldState.quests
          .filter((q) => q.status === "active")
          .map((q) => (
            <div key={q.id} className="rounded bg-black/30 p-2 border-l-2 border-fantasy-gold mb-2 text-xs">
              <p className="font-medium text-fantasy-gold">{q.title}</p>
              <p className="text-fantasy-muted mt-1 leading-relaxed">{q.description}</p>
            </div>
          ))}
      </div>
    </aside>
  );
}
