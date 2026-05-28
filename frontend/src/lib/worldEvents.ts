import type { GameEventItem, GameState } from "../types";

export interface FeedItem {
  id: string;
  category: "world" | "rumor" | "npc" | "system" | "crisis";
  text: string;
  turn?: number;
  time?: string;
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
}

export function buildWorldEventFeed(
  worldState: GameState | null,
  dbEvents: GameEventItem[] = [],
  crisisNotes: string[] = []
): FeedItem[] {
  const items: FeedItem[] = [];
  const flags = worldState?.flags ?? {};

  const rumors = (flags.rumors as Array<{ text: string; spread_to?: string[] }>) || [];
  for (const r of rumors.slice(-4)) {
    items.push({
      id: uid(),
      category: "rumor",
      text: r.text,
    });
  }

  if (worldState) {
    const loc = worldState.location;
    const here = Object.values(worldState.npcs).filter((n) => n.location === loc && n.present);
    for (const npc of here) {
      if (npc.memories.length > 0) {
        items.push({
          id: uid(),
          category: "npc",
          text: `${npc.name}：${npc.memories[npc.memories.length - 1]}`,
        });
      }
    }
  }

  for (const note of crisisNotes.slice(-3)) {
    items.push({ id: uid(), category: "crisis", text: note });
  }

  for (const ev of dbEvents.slice(-12).reverse()) {
    const feed = eventToFeed(ev);
    if (feed) items.push(feed);
  }

  const factions = (flags.factions as Record<string, { mood?: string }>) || {};
  for (const [name, f] of Object.entries(factions)) {
    if (f.mood) {
      items.push({
        id: uid(),
        category: "world",
        text: `【${name}】${f.mood}`,
      });
    }
  }

  return items.slice(0, 24);
}

function eventToFeed(ev: GameEventItem): FeedItem | null {
  const p = ev.payload || {};
  switch (ev.event_type) {
    case "action": {
      const input = p.player_input as string | undefined;
      if (!input || input.startsWith("【游戏开始】")) return null;
      return {
        id: `ev-${ev.turn}-action`,
        category: "system",
        text: `你：${input}`,
        turn: ev.turn,
        time: ev.created_at,
      };
    }
    case "world_change": {
      const ticks = p.world_tick_events as Array<{ text?: string }> | undefined;
      if (ticks?.length) {
        return {
          id: `ev-${ev.turn}-tick`,
          category: "world",
          text: ticks.map((t) => t.text).filter(Boolean).join(" "),
          turn: ev.turn,
        };
      }
      if (p.clue) {
        return { id: `ev-${ev.turn}-clue`, category: "world", text: `线索：${p.clue}`, turn: ev.turn };
      }
      if (p.moved_to) {
        return {
          id: `ev-${ev.turn}-move`,
          category: "world",
          text: `场景转移 → ${p.moved_to}`,
          turn: ev.turn,
        };
      }
      return null;
    }
    case "dice_roll": {
      const desc = p.description as string | undefined;
      if (!desc) return null;
      return {
        id: `ev-${ev.turn}-dice`,
        category: "system",
        text: desc,
        turn: ev.turn,
      };
    }
    default:
      return null;
  }
}
