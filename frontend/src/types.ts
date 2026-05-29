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

export interface StartGameResponse extends ImageUrlsPayload, ChapterCompletePayload {
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
  investigation_mode?: boolean;
  investigation_ui?: InvestigationUi;
  investigation_board?: InvestigationBoard;
}

export interface ActionResponse extends ImageUrlsPayload, ChapterCompletePayload {
  narrative: string;
  inline_choices?: InlineChoice[];
  choice_transition?: string;
  player_raw_input?: string;
  selected_choice_text?: string | null;
  parsed_intent?: unknown;
  intent_confidence?: number;
  chapter?: { number: number; title: string };
  crisis_state?: CrisisState;
  available_actions?: AvailableActions;
  world_state_changes: Record<string, unknown>;
  available_options: string[];
  dice_roll_info: DiceRollInfo | null;
  world_state: GameState;
  turn?: number;
  investigation_mode?: boolean;
  investigation_ui?: InvestigationUi;
  investigation_board?: InvestigationBoard;
}

export interface NarrativeLogEntry {
  html: string;
  kind?: "prologue" | "narrative" | "world";
  turn?: number;
}

export interface GameStateResponse extends ImageUrlsPayload, ChapterCompletePayload {
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
  investigation_mode?: boolean;
  investigation_ui?: InvestigationUi;
  investigation_board?: InvestigationBoard;
}

export interface InspectorResponse {
  initialized: boolean;
  turns: number[];
  turn: number | null;
  blocks?: {
    intent_parser?: unknown;
    rule_result?: unknown;
    world_tick?: unknown;
    world_change?: unknown;
    npc_memory_diff?: unknown;
    sim_metrics_diff?: unknown;
    scene_graph?: unknown;
    event_beats?: unknown;
    llm_prompt?: unknown;
    final_narrative?: string | null;
    narrative_sha256?: string | null;
  };
  raw_events?: GameEventItem[];
}

export interface BranchInfo {
  branch_id: string;
  seed_id: string;
  template_id: string;
  parent_branch_id?: string | null;
  fork_turn?: number | null;
  label?: string | null;
  created_at?: string;
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

export interface TimelineEntry {
  turn: number;
  title: string;
  check?: string;
  check_success?: boolean;
  clue?: string;
}

export interface ClueCard {
  text: string;
  source?: string;
}

export interface NpcRelationshipSummary {
  name: string;
  status: string;
  detail?: string;
}

export interface PlayerStats {
  turns: number;
  clues_found: number;
  checks_passed?: number;
  checks_failed?: number;
  crisis_label?: string;
}

export interface SessionSummary {
  chapter?: ChapterInfo;
  ending?: {
    title: string;
    subtitle?: string;
    epigraph?: string;
    summary?: string;
  };
  ending_summary?: string;
  timeline?: TimelineEntry[];
  clue_cards?: ClueCard[];
  player_stats?: PlayerStats;
  turns_played?: number;
  /** @deprecated 旧版字段，仅作兼容 */
  key_choices?: { turn: number; label: string }[];
  clues?: { discovered: string[]; missed?: string[] };
  investigation_routes?: {
    id: string;
    label: string;
    progress: number;
    max: number;
    explored: boolean;
  }[];
  npc_relationships?: (NpcRelationshipSummary | { name: string; attitude: string; value: number })[];
}

export interface ChapterCompletePayload {
  chapter_complete?: boolean;
  session_summary?: SessionSummary;
  chapter_ending_id?: string;
  vertical_slice?: boolean;
  investigation_mode?: boolean;
  investigation_ui?: InvestigationUi;
}

export type ImageStylePreset = "medieval fantasy" | "xianxia" | "cyberpunk";

export type NarrativeBlockKind =
  | "player-action"
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

export interface ChoiceGameplay {
  cost?: string;
  reward?: string;
  risk?: string;
}

export interface InlineChoice {
  id: string;
  text: string;
  input: string;
  tone?: string;
  risk?: string;
  category?: string;
  is_free?: boolean;
  disabled?: boolean;
  lock_reason?: string | null;
  intent_payload?: unknown;
  source?: { type: string; id: string; label: string } | null;
  source_hint?: string;
  gameplay?: ChoiceGameplay;
}

export interface InvestigationClueUi {
  id: string;
  label: string;
  found: boolean;
}

export interface BoardInteraction {
  id: string;
  label: string;
  short_label: string;
  category: string;
  entity_id: string;
  unlocked: boolean;
  locked: boolean;
  lock_reason?: string | null;
  is_new?: boolean;
  intent?: Record<string, unknown>;
}

export interface BoardEntity {
  id: string;
  kind: "npc" | "location";
  name: string;
  subtitle: string;
  location?: string;
  interaction_count: number;
  unlocked_count: number;
  interactions: BoardInteraction[];
}

export interface InvestigationBoard {
  entities: BoardEntity[];
  category_labels: Record<string, string>;
  mode?: string;
}

export interface InvestigationUi {
  remaining_turns: number;
  max_turns: number;
  stamina: number;
  crisis_pressure: number;
  thomas_trust: number;
  elena_trust: number;
  mira_trust: number;
  thomas_suspicion: number;
  clues_found: number;
  clues_total: number;
  clues: InvestigationClueUi[];
  chapter_complete?: boolean;
  guidance?: string;
  board?: InvestigationBoard;
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
