import { useEffect, useState } from "react";
import type { DiceRollInfo } from "../types";

interface Props {
  dice: DiceRollInfo | null;
  onClose: () => void;
}

const OUTCOME_STYLES: Record<string, string> = {
  大成功: "text-emerald-300 border-emerald-500 shadow-emerald-500/30",
  成功: "text-green-400 border-green-600 shadow-green-600/20",
  失败: "text-amber-400 border-amber-600 shadow-amber-600/20",
  大失败: "text-red-400 border-red-600 shadow-red-600/30",
};

export default function DiceOverlay({ dice, onClose }: Props) {
  const [visible, setVisible] = useState(false);
  const [displayRoll, setDisplayRoll] = useState(0);

  useEffect(() => {
    if (!dice) {
      setVisible(false);
      return;
    }
    setVisible(true);
    setDisplayRoll(0);
    let frame = 0;
    const interval = setInterval(() => {
      frame += 1;
      setDisplayRoll(Math.floor(Math.random() * 20) + 1);
      if (frame >= 8) {
        clearInterval(interval);
        setDisplayRoll(dice.die_roll);
      }
    }, 60);
    const timer = setTimeout(() => setVisible(false), 4500);
    return () => {
      clearInterval(interval);
      clearTimeout(timer);
    };
  }, [dice]);

  if (!dice || !visible) return null;

  const style = OUTCOME_STYLES[dice.outcome] || "text-fantasy-gold border-fantasy-border";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-label="掷骰结果"
    >
      <div
        className={`relative rounded-2xl border-2 bg-fantasy-panel p-8 text-center shadow-2xl animate-dice-pop ${style}`}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="text-fantasy-muted text-sm mb-2">{dice.description}</p>
        <div
          className={`mx-auto w-24 h-24 flex items-center justify-center rounded-xl bg-black/50 border-2 text-4xl font-bold mb-4 animate-dice-shake ${style}`}
        >
          {displayRoll}
        </div>
        <p className="text-lg mb-1">
          {dice.die_roll} {dice.modifier >= 0 ? "+" : ""}
          {dice.modifier} = <span className="font-bold">{dice.total}</span>
        </p>
        <p className="text-fantasy-muted text-sm mb-3">
          {dice.ability} 检定 vs DC {dice.dc}
        </p>
        <p className={`text-2xl font-fantasy font-bold ${style.split(" ")[0]}`}>
          【{dice.outcome}】
        </p>
        <button
          type="button"
          className="mt-6 text-sm text-fantasy-muted hover:text-fantasy-gold transition"
          onClick={onClose}
        >
          点击关闭
        </button>
      </div>
    </div>
  );
}
