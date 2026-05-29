import type { SceneComposition } from "../lib/sceneData";
import { weatherEffectClass } from "../lib/sceneData";
import { isUsableImageUrl, resolveImageSrc } from "../lib/imageUrl";

interface Props {
  scene: SceneComposition;
  backgroundUrl?: string | null;
  chapterTitle?: string | null;
  prologueMode?: boolean;
  templateId?: string;
}

const PROLOGUE_LOADING: Record<string, string> = {
  xianxia_forbidden_land:
    "灵雾流转，葬仙渊的山门与符纹正在为你显现……",
  medieval_dark_fantasy:
    "雾正在散去，雷文福德的轮廓即将为你显现……",
};

function prologueLoadingText(templateId?: string): string {
  if (templateId && PROLOGUE_LOADING[templateId]) {
    return PROLOGUE_LOADING[templateId];
  }
  if (templateId?.includes("xianxia")) {
    return PROLOGUE_LOADING.xianxia_forbidden_land;
  }
  return PROLOGUE_LOADING.medieval_dark_fantasy;
}

/** 紧凑场景横幅：背景 + 元信息，立绘见 SceneNpcStrip */
export default function SceneBanner({
  scene,
  backgroundUrl,
  chapterTitle,
  prologueMode = false,
  templateId,
}: Props) {
  const hasBg = isUsableImageUrl(backgroundUrl);
  const bgSrc = !prologueMode && hasBg ? resolveImageSrc(backgroundUrl) : undefined;
  const fx = weatherEffectClass(scene.weather);
  const showPrologueOverlay = prologueMode && !hasBg;

  return (
    <section className="scene-banner scene-banner-xianxia-glow relative rounded-lg border border-fantasy-border overflow-hidden shrink-0 shadow-lg shadow-black/40 h-[108px] md:h-[118px] theme-panel">
      <div
        className="absolute inset-0 bg-cover bg-center"
        style={
          bgSrc
            ? { backgroundImage: `url(${bgSrc})` }
            : { background: "linear-gradient(135deg, #1a1528 0%, #0a0810 100%)" }
        }
      />
      <div className="absolute inset-0 bg-gradient-to-r from-black/85 via-black/50 to-black/30" />
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-black/20" />
      <div className={`absolute inset-0 pointer-events-none ${fx}`} aria-hidden />

      <div className="relative z-10 h-full flex flex-col justify-end px-3 md:px-4 pb-2 pt-2">
        <header className="min-w-0">
          {chapterTitle && (
            <p className="text-[9px] tracking-[0.28em] text-fantasy-gold/70 uppercase truncate leading-none mb-0.5">
              {chapterTitle}
            </p>
          )}
          <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0">
            <h1 className="font-fantasy text-base md:text-lg text-fantasy-gold drop-shadow leading-tight">
              {scene.locationTitle}
            </h1>
            <p className="text-[10px] text-fantasy-muted flex flex-wrap gap-x-2 leading-tight">
              <span>{scene.timeLabel}</span>
              <span className="text-fantasy-text/85">{scene.weather}</span>
              <span
                className={
                  scene.dangerLevel === "高"
                    ? "text-red-400"
                    : scene.dangerLevel === "中"
                      ? "text-amber-400"
                      : "text-emerald-400"
                }
              >
                危险·{scene.dangerLevel}
              </span>
            </p>
          </div>
        </header>

        {scene.props.length > 0 && (
          <ul className="flex flex-wrap gap-1 mt-1.5 max-h-[22px] overflow-hidden">
            {scene.props.slice(0, 4).map((prop) => (
              <li
                key={prop}
                className="text-[8px] md:text-[9px] px-1.5 py-px rounded-full bg-black/55 border border-fantasy-border/50 text-fantasy-text/85 truncate max-w-[7rem]"
              >
                {prop}
              </li>
            ))}
          </ul>
        )}
      </div>

      {showPrologueOverlay && (
        <div className="absolute inset-0 z-20 bg-black/75 backdrop-blur-sm flex items-center justify-center">
          <p className="text-fantasy-muted text-sm italic px-6 text-center max-w-md">
            {prologueLoadingText(templateId)}
          </p>
        </div>
      )}
    </section>
  );
}
