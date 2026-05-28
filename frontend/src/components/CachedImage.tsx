import { useState } from "react";
import { resolveImageSrc } from "../lib/imageUrl";

interface Props {
  src?: string | null;
  alt: string;
  className?: string;
}

export default function CachedImage({ src, alt, className = "" }: Props) {
  const resolved = resolveImageSrc(src);
  const [failed, setFailed] = useState(false);

  if (!resolved || failed) {
    return (
      <div
        className={`flex items-center justify-center bg-gradient-to-b from-black/40 to-black/70 text-fantasy-muted/80 ${className}`}
        role="img"
        aria-label={alt}
      >
        <span className="text-[10px] px-2 text-center leading-snug">绘本插图生成中…</span>
      </div>
    );
  }

  return (
    <img
      src={resolved}
      alt={alt}
      className={className}
      onError={() => setFailed(true)}
    />
  );
}
