export type ActionCategory = "investigate" | "social" | "stealth" | "survival" | "free";

export interface DynamicAction {
  id: string;
  label: string;
  input: string;
  category: ActionCategory;
  description?: string;
  unlocked: boolean;
  lock_reason?: string | null;
  tags?: string[];
}

export interface AvailableActions {
  grouped: Partial<Record<ActionCategory, DynamicAction[]>>;
  category_labels: Record<ActionCategory, string>;
  flat_inputs: string[];
}

export interface WorldOntology {
  template_id?: string;
  core?: Record<string, string>;
  ui?: Record<string, string | Record<string, string>>;
  terms?: Record<string, unknown>;
}

export interface CrisisState {
  pressure: number;
  level: string;
  level_label: string;
  merchant_status: string;
  merchant_status_label: string;
  search_window: number;
  search_window_label: string;
  recent_anomalies: string[];
  suspicious_clues: string[];
  risk_notes: string[];
  merchant_location_hint?: string | null;
  ontology?: Record<string, string>;
  crisis_title?: string;
}

export interface Player {
  name: string;
  class_name: string;
  background: string;
  STR: number;
  DEX: number;
  CON: number;
  INT: number;
  WIS: number;
  CHA: number;
  equipment: string[];
  portrait_url?: string | null;
  portrait_asset_key?: string | null;
}

export interface NPCState {
  name: string;
  location: string;
  attitude: string;
  attitude_value: number;
  memories: string[];
  present: boolean;
  asset_key?: string | null;
}

export interface QuestState {
  id: string;
  title: string;
  description: string;
  status: string;
  objectives: string[];
}

export interface GameState {
  location: string;
  location_asset_key?: string | null;
  time_of_day: string;
  day: number;
  weather: string;
  active_npcs: string[];
  npcs: Record<string, NPCState>;
  quests: QuestState[];
  faction_reputation: Record<string, number>;
  flags: Record<string, unknown>;
  player: Player;
}

export interface DiceRollInfo {
  die_roll: number;
  modifier: number;
  total: number;
  dc: number;
  ability: string;
  outcome: string;
  description: string;
}

export interface ImageUrlsPayload {
  portrait_url?: string | null;
  background_url?: string | null;
  npc_portraits?: Record<string, string>;
  image_style?: string;
  template_id?: string;
  image_entities?: Record<string, { url: string; prompt_hash?: string; type?: string }>;
  image_generation?: ImageGenerationStatus;
}

export interface UiTheme {
  id?: string;
  accent?: string;
  gold?: string;
  bg?: string;
  panel?: string;
  border?: string;
  text?: string;
  muted?: string;
  fontFamily?: string;
  panelTexture?: string;
  atmosphere?: string;
}

export interface StartGameResponse extends ImageUrlsPayload {
  prologue: string;
  narrative: string;
  visuals_pending?: boolean;
  ui_theme?: UiTheme;
  world_ontology?: WorldOntology;
  chapter?: { number: number; title: string };
  crisis_state?: CrisisState;
  available_actions?: AvailableActions;
  world_state: GameState;
  available_options: string[];
  dice_roll_info: DiceRollInfo | null;
  turn?: number;
  seed_id?: string;
  game_mode?: "random" | "demo";
  inline_choices?: InlineChoice[];
  choice_transition?: string;
}

export interface ActionResponse extends ImageUrlsPayload {
  narrative: string;
  inline_choices?: InlineChoice[];
  choice_transition?: string;
  chapter?: { number: number; title: string };
  crisis_state?: CrisisState;
  available_actions?: AvailableActions;
  world_state_changes: Record<string, unknown>;
  available_options: string[];
  dice_roll_info: DiceRollInfo | null;
  world_state: GameState;
  turn?: number;
}

export interface NarrativeLogEntry {
  html: string;
  kind?: "prologue" | "narrative" | "world";
  turn?: number;
}

export interface GameStateResponse extends ImageUrlsPayload {
  initialized: boolean;
  world_state?: GameState;
  crisis_state?: CrisisState;
  offline_narrative?: string;
  offline_summary?: { ticks_run?: number; summary?: string[] };
  narrative_history?: NarrativeLogEntry[];
  available_actions?: AvailableActions;
  inline_choices?: InlineChoice[];
  choice_transition?: string;
  npc_memories?: Record<string, string[]>;
  events?: GameEventItem[];
  event_log?: unknown[];
}

export interface GenerateImageResponse {
  url: string;
  cache_key?: string;
  cached?: boolean;
  portrait_asset_key?: string;
}

export interface WorldTemplateInfo {
  id: string;
  name: string;
  art_style: string;
  ui_theme?: UiTheme;
  world_ontology?: WorldOntology;
}

export interface TemplatesResponse {
  templates: WorldTemplateInfo[];
}

export interface ImageGenerationStatus {
  enabled: boolean;
  total: number;
  completed: number;
}

export interface ChapterInfo {
  number: number;
  title: string;
}

export type ImageStylePreset = "medieval fantasy" | "xianxia" | "cyberpunk";

export type NarrativeBlockKind =
  | "scene"
  | "result"
  | "npc"
  | "dialogue"
  | "consequence"
  | "world"
  | "perception"
  | "player"
  | "choices"
  | "system";

export interface InlineChoice {
  id: string;
  text: string;
  input: string;
  tone?: string;
  risk?: string;
  category?: string;
  is_free?: boolean;
}

export interface NarrativeBlock {
  id: string;
  kind: NarrativeBlockKind;
  html: string;
  speaker?: string;
  label?: string;
}

export interface StoryEntry {
  id: string;
  text: string;
  turn?: number;
  kind?: "prologue" | "narrative";
  blocks?: NarrativeBlock[];
  inline_choices?: InlineChoice[];
  choice_transition?: string;
}

export interface GameEventItem {
  turn: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at?: string;
  timestamp?: string;
}
