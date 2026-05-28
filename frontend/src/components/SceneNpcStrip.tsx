import NpcSceneCard from "./NpcSceneCard";
import type { SceneComposition } from "../lib/sceneData";

interface Props {
  scene: SceneComposition;
}

/** 场景人物立绘带 — 独立于背景横幅，避免挤压与过度裁切 */
export default function SceneNpcStrip({ scene }: Props) {
  if (scene.npcs.length === 0) return null;

  return (
    <section className="scene-npc-strip shrink-0 rounded-lg border border-fantasy-border/70 bg-black/50 px-3 py-3">
      <p className="text-[10px] uppercase tracking-widest text-fantasy-muted mb-2">在场人物</p>
      <div className="flex flex-wrap justify-center gap-3 md:gap-5">
        {scene.npcs.map((item) => (
          <NpcSceneCard key={item.npc.name} item={item} />
        ))}
      </div>
    </section>
  );
}
