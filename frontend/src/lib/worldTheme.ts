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

const DEFAULT_THEME: UiTheme = {
  id: "medieval",
  accent: "#7b5ea7",
  gold: "#c9a227",
  bg: "#0f0e14",
  panel: "#1a1824",
  border: "#3d3550",
  text: "#e8e0d5",
  muted: "#9a8f82",
  fontFamily: "Georgia, Cambria, Times New Roman, serif",
  panelTexture: "stone",
};

export function applyUiTheme(theme: UiTheme | null | undefined): void {
  const t = { ...DEFAULT_THEME, ...theme };
  const root = document.documentElement;
  root.style.setProperty("--theme-accent", t.accent ?? DEFAULT_THEME.accent!);
  root.style.setProperty("--theme-gold", t.gold ?? DEFAULT_THEME.gold!);
  root.style.setProperty("--theme-bg", t.bg ?? DEFAULT_THEME.bg!);
  root.style.setProperty("--theme-panel", t.panel ?? DEFAULT_THEME.panel!);
  root.style.setProperty("--theme-border", t.border ?? DEFAULT_THEME.border!);
  root.style.setProperty("--theme-text", t.text ?? DEFAULT_THEME.text!);
  root.style.setProperty("--theme-muted", t.muted ?? DEFAULT_THEME.muted!);
  root.dataset.worldTheme = t.id ?? "medieval";
  root.dataset.panelTexture = t.panelTexture ?? "stone";
  if (t.fontFamily) {
    document.body.style.fontFamily = t.fontFamily;
  }
}

export function isXianxiaTheme(themeId?: string): boolean {
  return themeId === "xianxia" || themeId === "xianxia_forbidden_land";
}
