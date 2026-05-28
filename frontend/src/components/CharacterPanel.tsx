import { useState } from "react";
import CachedImage from "./CachedImage";
import ImageGenerator from "./ImageGenerator";
import type { Player } from "../types";

interface Props {
  player: Player | null;
  portraitUrl?: string | null;
  onPortraitChange?: (url: string) => void;
}

function mod(score: number): string {
  const m = Math.floor((score - 10) / 2);
  return m >= 0 ? `+${m}` : `${m}`;
}

const ABILITIES = [
  ["STR", "力量"],
  ["DEX", "敏捷"],
  ["CON", "体质"],
  ["INT", "智力"],
  ["WIS", "感知"],
  ["CHA", "魅力"],
] as const;

export default function CharacterPanel({ player, portraitUrl, onPortraitChange }: Props) {
  const [showCustom, setShowCustom] = useState(false);

  if (!player) {
    return (
      <aside className="h-full rounded-lg border border-fantasy-border bg-fantasy-panel/80 p-4">
        <p className="text-fantasy-muted text-sm">加载角色中…</p>
      </aside>
    );
  }

  const displayPortrait = portraitUrl || player.portrait_url;

  const scores: Record<string, number> = {
    STR: player.STR,
    DEX: player.DEX,
    CON: player.CON,
    INT: player.INT,
    WIS: player.WIS,
    CHA: player.CHA,
  };

  return (
    <aside className="h-full flex flex-col rounded-lg border border-fantasy-border bg-fantasy-panel/80 p-4 shadow-lg shadow-black/30 overflow-y-auto">
      <h2 className="font-fantasy text-fantasy-gold text-lg border-b border-fantasy-border pb-2 mb-3">
        角色
      </h2>

      <div className="mb-3 rounded-lg overflow-hidden border border-fantasy-border aspect-[3/4] max-h-44 shrink-0">
        <CachedImage
          src={displayPortrait}
          alt={`${player.name} 肖像`}
          className="w-full h-full object-cover object-[50%_12%] scale-[1.05]"
        />
      </div>

      {onPortraitChange && (
        <div className="mb-2">
          <button
            type="button"
            className="text-[10px] text-fantasy-muted hover:text-fantasy-gold underline"
            onClick={() => setShowCustom((v) => !v)}
          >
            {showCustom ? "收起自定义肖像" : "高级：自定义肖像（异步）"}
          </button>
          {showCustom && (
            <ImageGenerator
              player={player}
              portraitUrl={displayPortrait ?? null}
              onPortraitGenerated={(url) => onPortraitChange(url)}
            />
          )}
        </div>
      )}

      <div className="mb-3">
        <p className="text-lg font-semibold">{player.name}</p>
        <p className="text-fantasy-muted text-sm">{player.class_name}</p>
        <p className="text-fantasy-muted text-xs mt-1 italic">{player.background}</p>
      </div>
      <div className="grid grid-cols-2 gap-2 mb-4">
        {ABILITIES.map(([key, label]) => (
          <div
            key={key}
            className="flex justify-between items-center rounded bg-black/30 px-2 py-1.5 text-sm border border-fantasy-border/50"
          >
            <span className="text-fantasy-muted">{label}</span>
            <span>
              {scores[key]}{" "}
              <span className="text-fantasy-gold text-xs">({mod(scores[key])})</span>
            </span>
          </div>
        ))}
      </div>
      <h3 className="text-fantasy-gold text-sm mb-2">装备</h3>
      <ul className="text-sm space-y-1 text-fantasy-muted">
        {player.equipment.map((item) => (
          <li key={item} className="flex items-center gap-2">
            <span className="text-fantasy-accent">◆</span>
            {item}
          </li>
        ))}
      </ul>
    </aside>
  );
}
