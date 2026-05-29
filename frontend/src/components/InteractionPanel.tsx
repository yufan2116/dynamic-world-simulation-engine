import { useMemo } from "react";
import type { BoardEntity, BoardInteraction, InvestigationBoard as BoardData } from "../types";

interface Props {
  entity: BoardEntity | null;
  board: BoardData | null;
  loading?: boolean;
  disabled?: boolean;
  onInteract: (interaction: BoardInteraction) => void;
  onClose?: () => void;
}

export default function InteractionPanel({
  entity,
  board,
  loading,
  disabled,
  onInteract,
  onClose,
}: Props) {
  const labels = board?.category_labels ?? {
    social: "交涉",
    investigate: "观察",
    survival: "行动",
  };

  const grouped = useMemo(() => {
    if (!entity) return { social: [], investigate: [], survival: [] as BoardInteraction[] };
    const social: BoardInteraction[] = [];
    const investigate: BoardInteraction[] = [];
    const survival: BoardInteraction[] = [];
    for (const it of entity.interactions) {
      if (it.category === "social") social.push(it);
      else if (it.category === "survival") survival.push(it);
      else investigate.push(it);
    }
    return { social, investigate, survival };
  }, [entity]);

  if (!entity) return null;

  const renderGroup = (title: string, items: BoardInteraction[]) => {
    if (!items.length) return null;
    return (
      <div className="mb-2 last:mb-0">
        <p className="text-[10px] text-fantasy-gold/80 tracking-wider mb-1">【{title}】</p>
        <ul className="space-y-1">
          {items.map((it) => (
            <li key={it.id}>
              <button
                type="button"
                disabled={disabled || loading || !it.unlocked}
                onClick={() => onInteract(it)}
                className={`w-full text-left text-sm px-2.5 py-2 rounded-md border transition leading-snug ${
                  it.unlocked
                    ? "border-fantasy-border/50 bg-black/30 hover:border-fantasy-gold/50 hover:bg-fantasy-gold/10 text-fantasy-text"
                    : "border-fantasy-border/20 text-fantasy-muted/55 cursor-not-allowed"
                }`}
              >
                {it.short_label}
                {!it.unlocked && it.lock_reason && (
                  <span className="block text-[10px] mt-0.5 opacity-80">{it.lock_reason}</span>
                )}
                {it.is_new && it.unlocked && (
                  <span className="ml-1 text-[10px] text-emerald-400/90">新</span>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  };

  return (
    <section
      className="shrink-0 border-t border-fantasy-gold/30 bg-[#0f0c0a]/95 px-3 py-2.5 max-h-[min(38vh,320px)] overflow-y-auto overscroll-y-contain"
      aria-label="交互菜单"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <div>
          <h3 className="text-sm font-serif text-fantasy-gold">{entity.name}</h3>
          <p className="text-[10px] text-fantasy-muted">{entity.subtitle}</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="text-[10px] text-fantasy-muted hover:text-fantasy-text px-1.5 py-0.5 shrink-0"
          >
            收起
          </button>
        )}
      </div>
      {renderGroup(labels.social ?? "交涉", grouped.social)}
      {renderGroup(labels.investigate ?? "观察", grouped.investigate)}
      {renderGroup(labels.survival ?? "行动", grouped.survival)}
    </section>
  );
}
