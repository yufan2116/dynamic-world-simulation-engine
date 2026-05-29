import NpcSceneCard from "./NpcSceneCard";
import type { SceneComposition } from "../lib/sceneData";

interface Props {
  scene: SceneComposition;
  /** 默认紧凑横条，给冒险日志留出纵向空间 */
  compact?: boolean;
}

/** 场景人物立绘带 — 紧凑模式横向滚动，完整模式用于大屏展开 */
export default function SceneNpcStrip({ scene, compact = true }: Props) {
  if (scene.npcs.length === 0) return null;

  if (compact) {
    return (
      <section className="scene-npc-strip shrink-0 rounded-lg border border-fantasy-border/70 bg-black/45 px-2 py-2">
        <p className="text-[9px] uppercase tracking-widest text-fantasy-muted mb-1.5 px-1">在场人物</p>
        <div className="flex gap-2.5 overflow-x-auto overflow-y-visible overscroll-x-contain py-0.5 snap-x snap-mandatory">
          {scene.npcs.map((item) => (
            <NpcSceneCard key={item.npc.name} item={item} compact />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="scene-npc-strip shrink-0 rounded-lg border border-fantasy-border/70 bg-black/50 px-3 py-2">
      <p className="text-[10px] uppercase tracking-widest text-fantasy-muted mb-1.5">在场人物</p>
      <div className="flex flex-wrap justify-center gap-2 md:gap-3">
        {scene.npcs.map((item) => (
          <NpcSceneCard key={item.npc.name} item={item} />
        ))}
      </div>
    </section>
  );
}
