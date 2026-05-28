interface Props {
  completed: number;
  total: number;
  visible: boolean;
}

export default function ImageProgressBar({ completed, total, visible }: Props) {
  if (!visible || total <= 0) return null;
  const pct = Math.min(100, Math.round((completed / total) * 100));
  const done = completed >= total;

  return (
    <div className="rounded-lg border border-fantasy-border/60 bg-black/40 px-3 py-2 mb-2">
      <p className="text-[10px] text-fantasy-muted mb-1">
        {done ? "视觉素材已就绪" : "正在为世界绘制视觉素材…"}
      </p>
      <div className="h-1.5 rounded-full bg-black/50 overflow-hidden">
        <div
          className="h-full bg-fantasy-gold/80 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-[9px] text-fantasy-muted mt-0.5 text-right">
        {completed} / {total}
      </p>
    </div>
  );
}
