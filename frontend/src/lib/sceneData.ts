import type { GameState, NPCState } from "../types";

/** 地点默认环境元素（增强场景构图感） */
const LOCATION_PROPS: Record<string, string[]> = {
  村口: ["石砌门楼", "雨中马车", "半熄的火把", "泥泞小径"],
  酒馆: ["壁炉余烬", "木桌酒渍", "摇曳油灯", "远处低语"],
  仓库: ["破损货箱", "积尘窗格", "铁锁大门", "可疑脚印"],
  森林小路: ["扭曲古树", "薄雾小径", "远处狼嚎", "断裂车辙"],
  山门: ["云雾石柱", "仙鹤掠影", "青石阶", "宗门匾额"],
  藏经阁: ["卷轴书架", "檀香袅袅", "封印阵纹", "幽暗烛光"],
  禁地裂谷: ["紫黑瘴气", "碎裂灵石", "断崖铁索", "不祥低鸣"],
};

const NPC_ROLES: Record<string, { faction: string; role: string }> = {
  托马斯: { faction: "村庄守卫", role: "守卫队长" },
  米拉: { faction: "村民", role: "酒馆掌柜" },
  艾琳娜: { faction: "商人家庭", role: "失踪者之女" },
  瓦里克: { faction: "盗匪", role: "匪首" },
  青岚: { faction: "太虚宗", role: "女剑修" },
  玄尘道人: { faction: "散修盟", role: "道长" },
  黑衣散修: { faction: "散修", role: "黑衣散修" },
  镇守残魂: { faction: "上古剑宗", role: "古修残魂" },
  太虚宗弟子: { faction: "太虚宗", role: "宗门弟子" },
};

export interface SceneNpc {
  npc: NPCState;
  portraitUrl?: string;
  faction: string;
  role: string;
  pressure: "低" | "中" | "高";
  trustLabel: string;
}

export interface SceneComposition {
  villageName: string;
  location: string;
  locationTitle: string;
  timeLabel: string;
  weather: string;
  dangerLevel: string;
  props: string[];
  npcs: SceneNpc[];
}

function pressureFromAttitude(value: number): "低" | "中" | "高" {
  const a = Math.abs(value);
  if (a >= 50) return "高";
  if (a >= 25) return "中";
  return "低";
}

function trustLabel(value: number, attitude: string): string {
  if (value >= 40) return "可信";
  if (value <= -40) return "敌意";
  if (["怀疑", "警惕", "冷淡"].includes(attitude)) return "未知";
  if (value >= 15) return "倾向信任";
  return "观望";
}

export function buildSceneComposition(
  worldState: GameState,
  npcPortraits: Record<string, string>
): SceneComposition {
  const flags = worldState.flags || {};
  const onto = flags.world_ontology as { core?: { settlement?: string } } | undefined;
  const village = String(
    flags.world_name ?? flags.village_name ?? onto?.core?.settlement ?? "未知之地"
  );
  const clock = String(flags.clock ?? worldState.time_of_day);
  const danger = String(flags.danger_level ?? "中");
  const customProps = flags.scene_props as string[] | undefined;

  const sceneNames = flags.scene_npcs as string[] | undefined;
  let npcsHere: NPCState[];
  if (sceneNames?.length) {
    npcsHere = sceneNames
      .map((name) => worldState.npcs[name])
      .filter((n): n is NPCState => Boolean(n && n.present));
  } else {
    const byName = new Map<string, NPCState>();
    for (const name of worldState.active_npcs ?? []) {
      const n = worldState.npcs[name];
      if (n?.present) byName.set(name, n);
    }
    for (const n of Object.values(worldState.npcs)) {
      if (n.location === worldState.location && n.present) {
        byName.set(n.name, n);
      }
    }
    npcsHere = [...byName.values()];
  }

  const seedLocs = flags.seed_locations as Array<{ name?: string; visual_tags?: string[] }> | undefined;
  const locMeta = seedLocs?.find((l) => l.name === worldState.location);
  const props =
    customProps?.length
      ? customProps
      : locMeta?.visual_tags?.length
        ? locMeta.visual_tags
        : LOCATION_PROPS[worldState.location] ?? ["环境细节待观察"];

  const profiles = flags.npc_profiles as Record<
    string,
    { sect?: string; role?: string; role_label?: string }
  > | undefined;
  const roleLabels = (flags.world_ontology as { terms?: { role_labels?: Record<string, string> } })
    ?.terms?.role_labels;

  const npcs: SceneNpc[] = npcsHere.map((npc) => {
    const prof = profiles?.[npc.name];
    const roleKey = prof?.role ?? "";
    const roleDisplay =
      prof?.role_label ??
      roleLabels?.[roleKey] ??
      NPC_ROLES[npc.name]?.role ??
      (roleKey && /[\u4e00-\u9fff]/.test(roleKey) ? roleKey : "修士");
    const meta = NPC_ROLES[npc.name] ?? {
      faction: prof?.sect ?? "未知",
      role: roleDisplay,
    };
    return {
      npc,
      portraitUrl: npcPortraits[npc.name],
      faction: meta.faction,
      role: meta.role,
      pressure: pressureFromAttitude(npc.attitude_value),
      trustLabel: trustLabel(npc.attitude_value, npc.attitude),
    };
  });

  return {
    villageName: village,
    location: worldState.location,
    locationTitle: `${village} · ${worldState.location}`,
    timeLabel: `第 ${worldState.day} 天 · ${clock}`,
    weather: worldState.weather,
    dangerLevel: danger,
    props,
    npcs,
  };
}

export function weatherEffectClass(weather: string): string {
  if (/雨|暴雨|淅沥/.test(weather)) return "scene-fx-rain";
  if (/雾|薄雾|浓雾/.test(weather)) return "scene-fx-fog";
  if (/雪/.test(weather)) return "scene-fx-snow";
  return "";
}
