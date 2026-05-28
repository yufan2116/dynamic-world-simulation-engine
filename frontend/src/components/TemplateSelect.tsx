import type { WorldTemplateInfo } from "../types";

interface Props {
  templates: WorldTemplateInfo[];
  selectedId: string;
  onSelect: (id: string) => void;
  disabled?: boolean;
}

export default function TemplateSelect({
  templates,
  selectedId,
  onSelect,
  disabled,
}: Props) {
  return (
    <div className="mb-3">
      <p className="text-[10px] text-fantasy-muted mb-1.5 uppercase tracking-wider">
        世界模板
      </p>
      <div className="flex flex-col gap-1">
        {templates.map((t) => (
          <button
            key={t.id}
            type="button"
            disabled={disabled}
            onClick={() => onSelect(t.id)}
            className={`text-left text-xs px-2 py-1.5 rounded border transition ${
              selectedId === t.id
                ? "border-fantasy-gold text-fantasy-gold bg-fantasy-gold/10"
                : "border-fantasy-border text-fantasy-muted hover:border-fantasy-accent"
            }`}
          >
            {t.name}
          </button>
        ))}
      </div>
    </div>
  );
}
