import CachedImage from "./CachedImage";
import type { SceneNpc } from "../lib/sceneData";

interface Props {
  item: SceneNpc;
  /** 横向紧凑条：保留立绘，不占满纵向空间 */
  compact?: boolean;
}

function attitudeColor(attitude: string): string {
  if (["敌对", "冷淡"].includes(attitude)) return "text-red-400";
  if (["友好", "亲密", "担忧"].includes(attitude)) return "text-emerald-400";
  if (attitude === "悲伤") return "text-blue-300";
  if (["怀疑", "警惕"].includes(attitude)) return "text-amber-400";
  return "text-fantasy-muted";
}

export default function NpcSceneCard({ item, compact = false }: Props) {
  const { npc, portraitUrl, faction, role, pressure, trustLabel } = item;
  const moodLine =
    npc.memories.length > 0
      ? npc.memories[npc.memories.length - 1]
      : moodFallback(npc.attitude, npc.name);

  if (compact) {
    return (
      <figure
        className="npc-stage-card-compact shrink-0 w-[100px] snap-start"
        title={`${role} · ${npc.attitude} · ${moodLine}`}
      >
        <div className="relative w-full h-[92px] rounded-md overflow-hidden border border-fantasy-gold/35 shadow-md bg-black/60">
          {portraitUrl ? (
            <CachedImage
              src={portraitUrl}
              alt={npc.name}
              className="w-full h-full object-cover object-[50%_12%] scale-[1.06]"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-fantasy-muted text-[10px]">
              …
            </div>
          )}
          <figcaption className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/95 via-black/75 to-transparent px-1.5 pt-4 pb-1 text-center leading-tight">
            <p className="font-fantasy text-fantasy-gold text-[11px] leading-none truncate w-full">
              {npc.name}
            </p>
            <p className={`text-[9px] truncate ${attitudeColor(npc.attitude)}`}>{npc.attitude}</p>
          </figcaption>
        </div>
      </figure>
    );
  }

  return (
    <figure className="npc-stage-card shrink-0 w-[120px] sm:w-[136px] flex flex-col items-center">
      <div className="relative w-full aspect-[3/4] h-[168px] sm:h-[188px] rounded-lg overflow-hidden border-2 border-fantasy-gold/30 shadow-lg shadow-black/60 bg-gradient-to-b from-fantasy-panel/30 to-black/80">
        {portraitUrl ? (
          <CachedImage
            src={portraitUrl}
            alt={npc.name}
            className="w-full h-full object-cover object-[50%_12%] scale-[1.08]"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-fantasy-muted text-xs">
            立绘加载中…
          </div>
        )}
      </div>

      <figcaption className="mt-2 text-center w-full">
        <p className="font-fantasy text-fantasy-gold text-sm leading-tight">{npc.name}</p>
        <p className="text-[9px] text-fantasy-muted">{role}</p>
      </figcaption>

      <div className="mt-1.5 w-full rounded-lg bg-black/65 border border-fantasy-border/50 px-2 py-1.5 text-[10px] space-y-0.5">
        <div className="flex justify-between gap-1">
          <span className="text-fantasy-muted">态度</span>
          <span className={attitudeColor(npc.attitude)}>{npc.attitude}</span>
        </div>
        <div className="flex justify-between gap-1">
          <span className="text-fantasy-muted">压力</span>
          <span>{pressure}</span>
        </div>
        <div className="flex justify-between gap-1">
          <span className="text-fantasy-muted">可信度</span>
          <span>{trustLabel}</span>
        </div>
        <div className="flex justify-between gap-1">
          <span className="text-fantasy-muted">阵营</span>
          <span className="truncate text-fantasy-text/80 max-w-[80px]" title={faction}>
            {faction}
          </span>
        </div>
      </div>

      <p className="mt-1.5 text-[10px] text-fantasy-text/75 italic text-center line-clamp-2 leading-snug px-0.5">
        {moodLine}
      </p>
    </figure>
  );
}

function moodFallback(attitude: string, name: string): string {
  const map: Record<string, string> = {
    警惕: `${name}按着剑柄，目光扫过每一个陌生人。`,
    担忧: `${name}神情焦虑，似乎有话想说又不敢开口。`,
    悲伤: `${name}眼眶泛红，强撑着站在风雨里。`,
    怀疑: `${name}打量着你，像在权衡该不该信任。`,
    友好: `${name}微微点头，语气比刚才缓和了些。`,
    敌对: `${name}的手始终没有离开武器。`,
  };
  return map[attitude] ?? `${name}沉默地注视着当前的局面。`;
}
