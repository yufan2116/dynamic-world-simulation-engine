import { useState } from "react";
import { generatePortrait } from "../api";
import CachedImage from "./CachedImage";
import type { Player } from "../types";

interface Props {
  player: Player | null;
  portraitUrl: string | null;
  onPortraitGenerated: (url: string) => void;
}

export default function ImageGenerator({
  player,
  portraitUrl,
  onPortraitGenerated,
}: Props) {
  const [preview, setPreview] = useState<string | null>(portraitUrl);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const buildDescription = () => {
    if (!player) return "fantasy RPG adventurer";
    return `${player.name}, ${player.class_name}, ${player.background}. Equipment: ${player.equipment.join(", ")}`;
  };

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await generatePortrait(buildDescription());
      setPreview(res.url);
      onPortraitGenerated(res.url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "生成失败");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mt-2 rounded-lg border border-fantasy-border/60 bg-black/25 p-2">
      <p className="text-xs text-fantasy-muted mb-2">自定义肖像（可选）</p>
      <div className="aspect-square w-full max-h-28 rounded overflow-hidden bg-black/40 mb-2">
        <CachedImage
          src={preview}
          alt="预览"
          className="w-full h-full object-cover"
        />
      </div>
      <button
        type="button"
        disabled={loading || !player}
        onClick={() => void handleGenerate()}
        className="w-full text-xs py-1.5 rounded bg-fantasy-accent/50 hover:bg-fantasy-accent disabled:opacity-40"
      >
        {loading ? "生成中…" : "生成自定义肖像"}
      </button>
      {error && <p className="text-red-400 text-[10px] mt-1">{error}</p>}
    </div>
  );
}
