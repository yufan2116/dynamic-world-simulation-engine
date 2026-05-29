import type { BoardEntity, InvestigationBoard as BoardData, InvestigationUi } from "../types";

interface Props {
  board: BoardData | null;
  investigationUi?: InvestigationUi | null;
  selectedEntityId: string | null;
  onSelectEntity: (entityId: string) => void;
}

function EntityButton({
  ent,
  selected,
  onSelect,
}: {
  ent: BoardEntity;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`w-full text-left px-2 py-1.5 rounded border text-[11px] transition ${
        selected
          ? "border-fantasy-gold/60 bg-fantasy-gold/12 text-fantasy-gold"
          : "border-fantasy-border/40 text-fantasy-text/90 hover:border-fantasy-border/70 hover:bg-black/20"
      }`}
    >
      <span className="font-serif">{ent.name}</span>
      <span className="block text-[9px] text-fantasy-muted truncate">{ent.subtitle}</span>
    </button>
  );
}

/** 左侧调查板：仅实体列表 + 线索索引（不含交互菜单）。 */
export default function InvestigationBoardSidebar({
  board,
  investigationUi,
  selectedEntityId,
  onSelectEntity,
}: Props) {
  const entities = board?.entities ?? [];
  const npcs = entities.filter((e) => e.kind === "npc");
  const locations = entities.filter((e) => e.kind === "location");
  const foundClues = (investigationUi?.clues ?? []).filter((c) => c.found);

  if (!board?.entities?.length) {
    return (
      <div className="rounded-lg border border-fantasy-border/50 bg-fantasy-panel/80 p-3 text-xs text-fantasy-muted italic shrink-0">
        调查板加载中…
      </div>
    );
  }

  return (
    <div className="flex flex-col min-h-0 flex-1 gap-2 rounded-lg border border-fantasy-gold/25 bg-[#1a1410]/95 overflow-hidden">
      <header className="shrink-0 px-2.5 py-2 border-b border-fantasy-border/40">
        <h3 className="text-[10px] tracking-[0.25em] uppercase text-fantasy-gold">调查现场</h3>
        <p className="text-[9px] text-fantasy-muted mt-0.5">选择人物或地点，在中间展开行动</p>
      </header>

      <div className="flex-1 min-h-0 overflow-y-auto overscroll-y-contain px-2 py-1 space-y-3">
        {npcs.length > 0 && (
          <section>
            <p className="text-[10px] text-fantasy-gold/70 tracking-wider mb-1">人物</p>
            <ul className="space-y-1">
              {npcs.map((ent) => (
                <li key={ent.id}>
                  <EntityButton
                    ent={ent}
                    selected={selectedEntityId === ent.id}
                    onSelect={() => onSelectEntity(ent.id)}
                  />
                </li>
              ))}
            </ul>
          </section>
        )}

        {locations.length > 0 && (
          <section>
            <p className="text-[10px] text-fantasy-gold/70 tracking-wider mb-1">地点</p>
            <ul className="space-y-1">
              {locations.map((ent) => (
                <li key={ent.id}>
                  <EntityButton
                    ent={ent}
                    selected={selectedEntityId === ent.id}
                    onSelect={() => onSelectEntity(ent.id)}
                  />
                </li>
              ))}
            </ul>
          </section>
        )}

        <section className="border-t border-fantasy-border/30 pt-2">
          <p className="text-[10px] text-fantasy-gold/70 tracking-wider mb-1">
            线索 {investigationUi ? `（${investigationUi.clues_found}/${investigationUi.clues_total}）` : ""}
          </p>
          <ul className="text-[10px] space-y-0.5 max-h-28 overflow-y-auto">
            {foundClues.length > 0 ? (
              foundClues.map((c) => (
                <li key={c.id} className="text-emerald-300/90 leading-snug">
                  ✓ {c.label}
                </li>
              ))
            ) : (
              <li className="text-fantasy-muted/60 italic">尚无关键线索</li>
            )}
          </ul>
        </section>
      </div>
    </div>
  );
}
