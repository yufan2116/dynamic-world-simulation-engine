import axios from "axios";
import type {
  ActionResponse,
  GameStateResponse,
  GenerateImageResponse,
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

export async function submitAction(playerInput: string): Promise<ActionResponse> {
  const { data } = await api.post<ActionResponse>("/game/action", { player_input: playerInput });
  return data;
}

export async function fetchGameState(): Promise<GameStateResponse> {
  const { data } = await api.get<GameStateResponse>("/game/state");
  return data;
}

export async function generatePortrait(description: string): Promise<GenerateImageResponse> {
  const { data } = await api.post<GenerateImageResponse>("/game/generate-portrait", {
    description,
    style: "storybook",
  });
  return data;
}
