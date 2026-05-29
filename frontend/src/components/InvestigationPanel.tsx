import type { InvestigationUi } from "../types";

interface Props {
  ui: InvestigationUi | null;
}

function Bar({ label, value, max = 100, color }: { label: string; value: number; max?: number; color: string }) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0;
  return (
    <div className="mb-2">
      <div className="flex justify-between text-[10px] mb-0.5">
        <span className="text-fantasy-muted">{label}</span>
        <span className="text-fantasy-text/90">{value}{max <= 10 ? "" : "%"}</span>
      </div>
      <div className="h-1.5 rounded-full bg-black/50 overflow-hidden">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function InvestigationPanel({ ui }: Props) {
  if (!ui) return null;

  return (
    <div className="rounded-lg border border-fantasy-gold/30 bg-[#1a1410]/90 p-2.5 shrink-0 space-y-2">
      <h3 className="text-[10px] tracking-[0.25em] uppercase text-fantasy-gold">调查进度</h3>

      {ui.guidance && (
        <p className="text-[10px] text-fantasy-text/85 leading-relaxed border border-fantasy-border/40 rounded px-2 py-1.5 bg-black/20">
          {ui.guidance}
        </p>
      )}

      <div className="grid grid-cols-2 gap-2 text-center text-xs">
        <div className="rounded border border-fantasy-border/40 py-1.5">
          <div className="text-fantasy-muted text-[10px]">剩余回合</div>
          <div className="text-lg text-amber-100 font-serif">
            {ui.remaining_turns}
            <span className="text-fantasy-muted text-sm">/{ui.max_turns}</span>
          </div>
        </div>
        <div className="rounded border border-fantasy-border/40 py-1.5">
          <div className="text-fantasy-muted text-[10px]">关键线索</div>
          <div className="text-lg text-emerald-300/90 font-serif">
            {ui.clues_found}
            <span className="text-fantasy-muted text-sm">/{ui.clues_total}</span>
          </div>
        </div>
      </div>

      <Bar
        label="危机压力"
        value={ui.crisis_pressure}
        color={
          ui.crisis_pressure >= 70 ? "bg-red-500" : ui.crisis_pressure >= 45 ? "bg-amber-500" : "bg-emerald-600"
        }
      />

      <div className="flex items-center justify-between text-[10px] text-fantasy-muted">
        <span>体力</span>
        <span className="text-amber-100">
          {"♥".repeat(Math.max(0, ui.stamina))}
          <span className="opacity-30">{"♥".repeat(Math.max(0, 3 - ui.stamina))}</span>
        </span>
      </div>

      <div className="border-t border-fantasy-border/30 pt-2">
        <p className="text-[10px] text-fantasy-muted mb-1">NPC 信任</p>
        <ul className="text-[10px] space-y-0.5">
          <li className="flex justify-between">
            <span>托马斯</span>
            <span>{ui.thomas_trust > 0 ? `+${ui.thomas_trust}` : ui.thomas_trust}</span>
          </li>
          <li className="flex justify-between">
            <span>艾琳娜</span>
            <span>{ui.elena_trust > 0 ? `+${ui.elena_trust}` : ui.elena_trust}</span>
          </li>
          <li className="flex justify-between">
            <span>米拉</span>
            <span>{ui.mira_trust > 0 ? `+${ui.mira_trust}` : ui.mira_trust}</span>
          </li>
        </ul>
      </div>

    </div>
  );
}
