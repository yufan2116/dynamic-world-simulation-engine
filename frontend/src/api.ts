import axios from "axios";
import type {
  ActionResponse,
  BranchInfo,
  GameStateResponse,
  GenerateImageResponse,
  InspectorResponse,
  StartGameResponse,
  TemplatesResponse,
} from "./types";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || "",
  timeout: 120000,
  headers: { "Content-Type": "application/json" },
});

export async function fetchTemplates(): Promise<TemplatesResponse> {
  const { data } = await api.get<TemplatesResponse>("/game/templates");
  return data;
}

export async function startGame(templateId?: string): Promise<StartGameResponse> {
  const { data } = await api.post<StartGameResponse>("/game/start", {
    template_id: templateId || "medieval_dark_fantasy",
  });
  return data;
}

/** 切换世界模板 — 重置世界并重新生成开场叙事 */
export async function loadWorldTemplate(template: string): Promise<StartGameResponse> {
  const { data } = await api.post<StartGameResponse>("/api/world/load-template", {
    template,
  });
  return data;
}

/** Ravenford 演示种子 — 固定初始世界，后续仍动态模拟 */
export async function startDemoGame(): Promise<StartGameResponse> {
  const { data } = await api.post<StartGameResponse>("/game/new-demo");
  return data;
}

export async function submitAction(
  playerInput: string,
  selectedChoiceText?: string,
  actionId?: string,
  intentPayload?: unknown
): Promise<ActionResponse> {
  const { data } = await api.post<ActionResponse>("/game/action", {
    player_input: playerInput,
    selected_choice_text: selectedChoiceText ?? null,
    action_id: actionId ?? null,
    intent_payload: intentPayload ?? null,
  });
  return data;
}

export async function fetchGameState(): Promise<GameStateResponse> {
  const { data } = await api.get<GameStateResponse>("/game/state");
  return data;
}

export async function fetchInspector(turn?: number): Promise<InspectorResponse> {
  const { data } = await api.get<InspectorResponse>("/game/inspector", {
    params: turn != null ? { turn } : undefined,
  });
  return data;
}

export async function rewindToTurn(turn: number): Promise<GameStateResponse> {
  const { data } = await api.post<GameStateResponse>("/game/rewind", { turn });
  return data;
}

export async function forkFromTurn(fromTurn: number, label?: string): Promise<GameStateResponse> {
  const { data } = await api.post<GameStateResponse>("/game/fork", { from_turn: fromTurn, label });
  return data;
}

export async function fetchBranches(): Promise<{ branches: BranchInfo[] }> {
  const { data } = await api.get<{ branches: BranchInfo[] }>("/game/branches");
  return data;
}

export async function generatePortrait(description: string): Promise<GenerateImageResponse> {
  const { data } = await api.post<GenerateImageResponse>("/game/generate-portrait", {
    description,
    style: "storybook",
  });
  return data;
}
