import type { GameState, WorldOntology } from "../types";

export function getOntologyFromState(worldState: GameState | null): WorldOntology | null {
  if (!worldState?.flags?.world_ontology) return null;
  const raw = worldState.flags.world_ontology as WorldOntology;
  if (raw?.ui) return raw;
  return null;
}

export function uiTerm(onto: WorldOntology | null, key: string, fallback: string): string {
  const v = onto?.ui?.[key];
  return typeof v === "string" ? v : fallback;
}

export function eventCategoryLabel(
  onto: WorldOntology | null,
  category: string,
  fallback: string
): string {
  const cats = onto?.ui?.event_categories;
  if (cats && typeof cats === "object" && category in cats) {
    return String((cats as Record<string, string>)[category]);
  }
  return fallback;
}

export function tensionFromState(worldState: GameState | null): number {
  if (!worldState?.flags) return 35;
  const f = worldState.flags;
  if (String(f.template_id || "").includes("xianxia")) {
    return Number(f.tension ?? f.spiritual_pollution ?? f.village_panic ?? 40);
  }
  return Number(f.village_panic ?? 35);
}
