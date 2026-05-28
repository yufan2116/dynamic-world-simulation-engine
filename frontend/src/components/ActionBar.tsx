import type { KeyboardEvent } from "react";

interface Props {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
}

/** 底栏仅保留自由输入；正式选项在叙事流内嵌展示。 */
export default function ActionBar({ value, onChange, onSubmit, disabled }: Props) {
  const handleKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
    }
  };

  return (
    <footer className="border border-fantasy-border/60 bg-black/60 backdrop-blur-lg p-3 rounded-lg">
      <p className="text-[10px] text-fantasy-muted mb-2">自由行动 · 在上方选择，或自行描述</p>
      <div className="flex gap-2">
        <input
          ref={(el) => {
            if (el) (window as unknown as { __dwseInput?: HTMLInputElement }).__dwseInput = el;
          }}
          id="free-action-input"
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKey}
          disabled={disabled}
          placeholder="例如：我假装喝醉，靠近守卫听他们谈话"
          className="flex-1 rounded-lg bg-black/50 border border-fantasy-border px-3 py-2 text-sm focus:outline-none focus:border-fantasy-accent"
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled || !value.trim()}
          className="px-4 py-2 rounded-lg bg-fantasy-accent/80 hover:bg-fantasy-accent text-sm disabled:opacity-40 shrink-0"
        >
          执行
        </button>
      </div>
    </footer>
  );
}
