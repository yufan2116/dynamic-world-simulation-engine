import { useMemo, useRef, useState } from "react";
import type { GameState, InvestigationUi } from "../types";

type NodeKind = "player" | "npc" | "faction";

type GraphNode = {
  id: string;
  label: string;
  kind: NodeKind;
  x: number;
  y: number;
};

type GraphEdge = {
  from: string;
  to: string;
  label: string;
  tone?: "positive" | "neutral" | "negative";
};

function clamp(n: number, lo: number, hi: number) {
  return Math.max(lo, Math.min(hi, n));
}

function npcRelationLabel(attitudeValue: number, attitude: string): { label: string; tone: GraphEdge["tone"] } {
  if (attitudeValue >= 60) return { label: `信任 +${attitudeValue}`, tone: "positive" };
  if (attitudeValue >= 20) return { label: `好感 +${attitudeValue}`, tone: "positive" };
  if (attitudeValue <= -60) return { label: `敌对 ${attitudeValue}`, tone: "negative" };
  if (attitudeValue <= -20) return { label: `怀疑 ${attitudeValue}`, tone: "negative" };
  return { label: attitude || "中立", tone: "neutral" };
}

function factionRelationLabel(rep: number, fallback?: string): { label: string; tone: GraphEdge["tone"] } {
  if (rep >= 60) return { label: `盟友 +${rep}`, tone: "positive" };
  if (rep >= 20) return { label: `友好 +${rep}`, tone: "positive" };
  if (rep <= -60) return { label: `敌对 ${rep}`, tone: "negative" };
  if (rep <= -20) return { label: `紧张 ${rep}`, tone: "negative" };
  return { label: fallback || `中立 ${rep >= 0 ? `+${rep}` : String(rep)}`, tone: "neutral" };
}

function defaultFactionEdges(templateId: string | undefined): GraphEdge[] {
  if (!templateId?.includes("xianxia")) return [];
  return [
    { from: "faction:太虚宗", to: "faction:散修盟", label: "紧张", tone: "negative" },
    { from: "faction:禁地邪修", to: "faction:太虚宗", label: "敌对", tone: "negative" },
  ];
}

const INV_NPC_TRUST: Record<string, keyof InvestigationUi> = {
  托马斯: "thomas_trust",
  艾琳娜: "elena_trust",
  米拉: "mira_trust",
};

export default function RelationshipGraph({
  worldState,
  investigationUi,
}: {
  worldState: GameState;
  investigationUi?: InvestigationUi | null;
}) {
  const flags = worldState.flags || {};
  const templateId = String((flags as Record<string, unknown>).template_id ?? "");
  const playerName = worldState.player?.name || "玩家";

  const factions = (flags.factions as Record<string, { relation_to_player?: string }> | undefined) || {};
  const factionRep = worldState.faction_reputation || {};

  const npcList = Object.values(worldState.npcs || {});
  const factionNames = Object.keys(factions);
  const npcNames = npcList.map((n) => n.name);

  const width = 560;
  const height = 360;
  const cx = width / 2;
  const cy = height / 2;

  const playerNode: GraphNode = { id: "player", label: playerName, kind: "player", x: cx, y: cy };

  const leftRadius = 130;
  const rightRadius = 135;

  const npcNodes: GraphNode[] = npcNames.slice(0, 8).map((name, i, arr) => {
    const a = (Math.PI * (i + 1)) / (arr.length + 1);
    return {
      id: `npc:${name}`,
      label: name,
      kind: "npc",
      x: cx - leftRadius * Math.cos(a),
      y: cy - leftRadius * Math.sin(a) + 10,
    };
  });

  const factionNodes: GraphNode[] = factionNames.slice(0, 8).map((name, i, arr) => {
    const a = (Math.PI * (i + 1)) / (arr.length + 1);
    return {
      id: `faction:${name}`,
      label: name,
      kind: "faction",
      x: cx + rightRadius * Math.cos(a),
      y: cy - rightRadius * Math.sin(a) + 10,
    };
  });

  const nodes = [playerNode, ...npcNodes, ...factionNodes];
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  const edges: GraphEdge[] = [];

  for (const npc of npcList) {
    if (!npcNames.includes(npc.name)) continue;
    let attVal = Number(npc.attitude_value ?? 0);
    if (investigationUi) {
      const key = INV_NPC_TRUST[npc.name];
      if (key) {
        attVal = Number(investigationUi[key] ?? 0) * 15;
      }
    }
    const { label, tone } = npcRelationLabel(attVal, String(npc.attitude ?? ""));
    edges.push({ from: "player", to: `npc:${npc.name}`, label, tone });
  }

  for (const name of factionNames) {
    const rep = Number(factionRep[name] ?? 0);
    const { label, tone } = factionRelationLabel(rep, factions[name]?.relation_to_player);
    edges.push({ from: "player", to: `faction:${name}`, label, tone });
  }

  const extra = (flags.faction_edges as GraphEdge[] | undefined) || defaultFactionEdges(templateId);
  for (const e of extra) edges.push(e);

  const edgeStyle = (tone?: GraphEdge["tone"]) => {
    if (tone === "positive") return "stroke-emerald-400/70";
    if (tone === "negative") return "stroke-red-400/70";
    return "stroke-fantasy-border/80";
  };

  const nodeFill = (k: NodeKind) => {
    if (k === "player") return "fill-fantasy-gold/90";
    if (k === "npc") return "fill-sky-400/80";
    return "fill-purple-400/80";
  };

  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const dragRef = useRef<{
    active: boolean;
    startClientX: number;
    startClientY: number;
    startPanX: number;
    startPanY: number;
  }>({
    active: false,
    startClientX: 0,
    startClientY: 0,
    startPanX: 0,
    startPanY: 0,
  });

  const transform = useMemo(() => {
    const z = clamp(zoom, 0.6, 3.5);
    // 以中心缩放，再叠加 pan
    return `translate(${pan.x} ${pan.y}) translate(${cx} ${cy}) scale(${z}) translate(${-cx} ${-cy})`;
  }, [zoom, pan.x, pan.y, cx, cy]);

  return (
    <div className="rounded-lg border border-fantasy-border bg-black/20 p-2">
      <div className="flex items-center justify-between px-1 pb-1">
        <p className="text-[10px] tracking-[0.25em] uppercase text-fantasy-muted">NPC / 派系关系图</p>
        <div className="flex items-center gap-2">
          <p className="text-[10px] text-fantasy-muted">节点≤{clamp(npcNodes.length + factionNodes.length + 1, 0, 999)}</p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              className="text-[10px] px-1.5 py-0.5 rounded border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60"
              onClick={() => setZoom((z) => clamp(z * 1.15, 0.6, 3.5))}
              title="放大"
            >
              +
            </button>
            <button
              type="button"
              className="text-[10px] px-1.5 py-0.5 rounded border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60"
              onClick={() => setZoom((z) => clamp(z / 1.15, 0.6, 3.5))}
              title="缩小"
            >
              −
            </button>
            <button
              type="button"
              className="text-[10px] px-1.5 py-0.5 rounded border border-fantasy-border bg-black/30 hover:border-fantasy-gold/60"
              onClick={() => {
                setZoom(1);
                setPan({ x: 0, y: 0 });
              }}
              title="重置"
            >
              Reset
            </button>
          </div>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-[240px] cursor-grab active:cursor-grabbing select-none"
        onWheel={(e) => {
          e.preventDefault();
          const delta = e.deltaY;
          const factor = delta > 0 ? 1 / 1.12 : 1.12;
          setZoom((z) => clamp(z * factor, 0.6, 3.5));
        }}
        onMouseDown={(e) => {
          dragRef.current.active = true;
          dragRef.current.startClientX = e.clientX;
          dragRef.current.startClientY = e.clientY;
          dragRef.current.startPanX = pan.x;
          dragRef.current.startPanY = pan.y;
        }}
        onMouseMove={(e) => {
          if (!dragRef.current.active) return;
          const dx = e.clientX - dragRef.current.startClientX;
          const dy = e.clientY - dragRef.current.startClientY;
          setPan({
            x: dragRef.current.startPanX + dx,
            y: dragRef.current.startPanY + dy,
          });
        }}
        onMouseUp={() => {
          dragRef.current.active = false;
        }}
        onMouseLeave={() => {
          dragRef.current.active = false;
        }}
      >
        <g transform={transform}>
          {/* edges */}
          {edges.map((e, idx) => {
            const a = nodeMap.get(e.from);
            const b = nodeMap.get(e.to);
            if (!a || !b) return null;
            const mx = (a.x + b.x) / 2;
            const my = (a.y + b.y) / 2;
            return (
              <g key={`${e.from}-${e.to}-${idx}`}>
                <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={`${edgeStyle(e.tone)} stroke-[1.2]`} />
                <rect x={mx - 52} y={my - 9} width={104} height={16} rx={6} className="fill-black/55" />
                <text x={mx} y={my + 2} textAnchor="middle" className="fill-fantasy-text/90 text-[10px]">
                  {e.label}
                </text>
              </g>
            );
          })}

          {/* nodes */}
          {nodes.map((n) => (
            <g key={n.id}>
              <circle
                cx={n.x}
                cy={n.y}
                r={n.kind === "player" ? 14 : 11}
                className={`${nodeFill(n.kind)} stroke-black/70`}
              />
              <text
                x={n.x}
                y={n.y + (n.kind === "player" ? 28 : 24)}
                textAnchor="middle"
                className="fill-fantasy-text/90 text-[11px]"
              >
                {n.label}
              </text>
            </g>
          ))}
        </g>
      </svg>
      <p className="text-[10px] text-fantasy-muted px-1">
        提示：滚轮缩放，拖拽平移。派系↔派系关系可在 `world_state.flags.faction_edges` 注入覆盖默认值。
      </p>
    </div>
  );
}

