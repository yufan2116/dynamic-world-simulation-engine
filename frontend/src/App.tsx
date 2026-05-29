import {

  useCallback,

  useEffect,

  useMemo,

  useRef,

  useState,

  type Dispatch,

  type SetStateAction,

} from "react";

import { fetchGameState, fetchTemplates, loadWorldTemplate, startDemoGame, startGame, submitAction } from "./api";
import { extractChoicesFromHtml } from "./lib/parseNarrative";
import { applyUiTheme } from "./lib/worldTheme";
import type { UiTheme } from "./types";
import { getOntologyFromState, uiTerm } from "./lib/ontology";

import ActionBar from "./components/ActionBar";

import CharacterPanel from "./components/CharacterPanel";

import DiceOverlay from "./components/DiceOverlay";

import ImageProgressBar from "./components/ImageProgressBar";

import NarrativeFeed from "./components/NarrativeFeed";

import SceneBanner from "./components/SceneBanner";
import SceneNpcStrip from "./components/SceneNpcStrip";

import DebugInspector from "./components/DebugInspector";
import ChapterComplete from "./components/ChapterComplete";

import TemplateSelect from "./components/TemplateSelect";

import WorldPanel from "./components/WorldPanel";

import { useImageWebSocket, type ImageWsMessage } from "./hooks/useImageWebSocket";

import { mergePortraitMaps } from "./lib/imageEntities";
import { isUsableImageUrl } from "./lib/imageUrl";
import { buildSceneComposition } from "./lib/sceneData";
import { parseNarrativeHtml } from "./lib/parseNarrative";

import { buildWorldEventFeed } from "./lib/worldEvents";

import type {

  AvailableActions,

  CrisisState,

  DiceRollInfo,

  GameEventItem,

  GameState,

  NarrativeLogEntry,
  InlineChoice,
  StoryEntry,
  SessionSummary,
  WorldTemplateInfo,
} from "./types";



function uid() {

  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;

}



function makeStoryEntry(
  text: string,
  opts?: {
    turn?: number;
    kind?: StoryEntry["kind"];
    inline_choices?: InlineChoice[];
    choice_transition?: string;
  }
): StoryEntry {
  return {
    id: uid(),
    text,
    turn: opts?.turn,
    kind: opts?.kind,
    inline_choices: opts?.inline_choices,
    choice_transition: opts?.choice_transition,
    blocks: parseNarrativeHtml(text, opts?.kind),
  };
}

/** 将选项挂到最近一条非序幕叙事上（刷新恢复 / get_state 同步用）。 */
function attachChoicesToLastEntry(
  entries: StoryEntry[],
  choices?: InlineChoice[],
  transition?: string
): StoryEntry[] {
  if (entries.length === 0) return entries;

  let targetIdx = -1;
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i].kind !== "prologue") {
      targetIdx = i;
      break;
    }
  }
  if (targetIdx < 0) return entries;

  const target = entries[targetIdx];
  let inline = choices?.length ? choices : target.inline_choices;
  if (!inline?.length) {
    inline = extractChoicesFromHtml(target.text);
  }
  if (!inline?.length) return entries;

  const updated: StoryEntry = {
    ...target,
    inline_choices: inline,
    choice_transition: transition ?? target.choice_transition,
  };
  return [...entries.slice(0, targetIdx), updated, ...entries.slice(targetIdx + 1)];
}

function storyFromHistory(history: NarrativeLogEntry[]): StoryEntry[] {
  const entries = history.map((e) =>
    makeStoryEntry(e.html, {
      turn: e.turn,
      kind: (e.kind as StoryEntry["kind"]) ?? "narrative",
    })
  );
  return attachChoicesToLastEntry(entries);
}

function hasActiveChoices(entries: StoryEntry[]): boolean {
  for (let i = entries.length - 1; i >= 0; i--) {
    if (entries[i].kind === "prologue") continue;
    return Boolean(entries[i].inline_choices?.length);
  }
  return false;
}

function buildOpeningStory(data: {
  prologue?: string;
  narrative: string;
  turn?: number;
  inline_choices?: InlineChoice[];
  choice_transition?: string;
}): StoryEntry[] {
  const mainNarrative = data.narrative;
  const prologue = data.prologue;
  const entries: StoryEntry[] = [];
  if (prologue?.trim() && prologue !== mainNarrative) {
    entries.push(makeStoryEntry(prologue, { turn: data.turn, kind: "prologue" }));
  }
  entries.push(
    makeStoryEntry(mainNarrative, {
      turn: data.turn,
      kind: "narrative",
      inline_choices: data.inline_choices,
      choice_transition: data.choice_transition,
    })
  );
  return attachChoicesToLastEntry(entries, data.inline_choices, data.choice_transition);
}



function formatApiError(e: unknown, fallback: string): string {

  if (e && typeof e === "object" && "response" in e) {

    const resp = (e as { response?: { data?: { detail?: string }; status?: number } }).response;

    const detail = resp?.data?.detail;

    if (detail) return `${detail}${resp?.status ? ` (${resp.status})` : ""}`;

    if (resp?.status) return `请求失败 HTTP ${resp.status}，请确认后端已启动`;

  }

  if (e instanceof Error) return e.message;

  return fallback;

}



type TemplateImageCache = {
  portrait?: string | null;
  background?: string | null;
  npcs: Record<string, string>;
};

function applyImagePayload(

  data: {

    portrait_url?: string | null;

    background_url?: string | null;

    npc_portraits?: Record<string, string>;

    image_entities?: Record<string, { url?: string }>;

    template_id?: string;

    world_state?: GameState;

    available_actions?: AvailableActions;

    crisis_state?: CrisisState;

    image_generation?: { enabled: boolean; total: number; completed: number };

  },

  setters: {

    setPortraitUrl: (u: string | null) => void;

    setBackgroundUrl: (u: string | null) => void;

    setNpcPortraits: Dispatch<SetStateAction<Record<string, string>>>;

    setTemplateId: (t: string) => void;

    setWorldState: (w: GameState) => void;

    setCrisisState: (c: CrisisState | null) => void;

    setAvailableActions: (a: AvailableActions | null) => void;

    setImageProgress: (p: { completed: number; total: number } | null) => void;

  }

) {

  if (data.world_state) setters.setWorldState(data.world_state);

  if (data.crisis_state) setters.setCrisisState(data.crisis_state);

  if (data.available_actions) setters.setAvailableActions(data.available_actions);

  if (data.template_id) setters.setTemplateId(data.template_id);

  else if (data.world_state?.flags?.template_id) {

    setters.setTemplateId(String(data.world_state.flags.template_id));

  }

  const portrait =
    isUsableImageUrl(data.portrait_url) ? data.portrait_url : data.world_state?.player?.portrait_url;
  if (isUsableImageUrl(portrait)) setters.setPortraitUrl(portrait ?? null);

  if (isUsableImageUrl(data.background_url)) setters.setBackgroundUrl(data.background_url ?? null);

  const merged = mergePortraitMaps(data.npc_portraits, data.image_entities);
  if (Object.keys(merged).length > 0) {
    setters.setNpcPortraits((prev) => ({ ...prev, ...merged }));
  }

  if (data.image_generation?.total) {

    setters.setImageProgress({

      completed: data.image_generation.completed,

      total: data.image_generation.total,

    });

  }

}



export default function App() {

  const [templates, setTemplates] = useState<WorldTemplateInfo[]>([]);

  const [templateId, setTemplateId] = useState("medieval_dark_fantasy");
  const [, setUiTheme] = useState<UiTheme | null>(null);

  const [worldState, setWorldState] = useState<GameState | null>(null);

  const [story, setStory] = useState<StoryEntry[]>([]);

  const [gameEvents, setGameEvents] = useState<GameEventItem[]>([]);

  const [, setAvailableActions] = useState<AvailableActions | null>(null);

  const [input, setInput] = useState("");

  const [loading, setLoading] = useState(false);

  const [initError, setInitError] = useState<string | null>(null);

  const [showDice, setShowDice] = useState<DiceRollInfo | null>(null);

  const [portraitUrl, setPortraitUrl] = useState<string | null>(null);

  const [backgroundUrl, setBackgroundUrl] = useState<string | null>(null);

  const [npcPortraits, setNpcPortraits] = useState<Record<string, string>>({});


  const [chapter, setChapter] = useState<{ number: number; title: string } | null>(null);

  const [crisisState, setCrisisState] = useState<CrisisState | null>(null);

  const [imageProgress, setImageProgress] = useState<{ completed: number; total: number } | null>(

    null

  );

  const [inPrologue, setInPrologue] = useState(false);
  const [showInspector, setShowInspector] = useState(false);
  const [sessionSummary, setSessionSummary] = useState<SessionSummary | null>(null);
  const [chapterComplete, setChapterComplete] = useState(false);
  const [gameMode, setGameMode] = useState<"random" | "demo">("random");

  const prologueBannerTimerRef = useRef<number | null>(null);

  const templateImageCacheRef = useRef<Record<string, TemplateImageCache>>({});

  const choicesSyncAtRef = useRef(0);



  const scene = useMemo(

    () => (worldState ? buildSceneComposition(worldState, npcPortraits) : null),

    [worldState, npcPortraits]

  );



  const eventFeed = useMemo(

    () =>

      buildWorldEventFeed(

        worldState,

        gameEvents,

        crisisState?.risk_notes ?? []

      ),

    [worldState, gameEvents, crisisState?.risk_notes]

  );



  const handleWsImage = useCallback(

    (msg: ImageWsMessage) => {

      if (!msg.entity_id || !msg.url || !isUsableImageUrl(msg.url)) return;

      if (msg.entity_id === "player:portrait") {

        setPortraitUrl(msg.url);

        return;

      }

      if (msg.entity_id.startsWith("loc:")) {

        const locName = msg.entity_id.slice(4);

        if (worldState?.location === locName) {

          setBackgroundUrl(msg.url);

        }

        return;

      }

      if (msg.entity_id.startsWith("npc:")) {

        const npcName = msg.entity_id.slice(4);

        setNpcPortraits((prev) => ({ ...prev, [npcName]: msg.url! }));

      }

      const tid = templateId;
      const prev = templateImageCacheRef.current[tid] ?? { npcs: {} };
      if (msg.entity_id === "player:portrait") {
        templateImageCacheRef.current[tid] = { ...prev, portrait: msg.url };
      } else if (msg.entity_id.startsWith("loc:")) {
        templateImageCacheRef.current[tid] = { ...prev, background: msg.url };
      } else if (msg.entity_id.startsWith("npc:")) {
        const npcName = msg.entity_id.slice(4);
        templateImageCacheRef.current[tid] = {
          ...prev,
          npcs: { ...prev.npcs, [npcName]: msg.url! },
        };
      }

    },

    [worldState?.location, templateId]

  );



  const { progress: wsProgress } = useImageWebSocket(templateId, handleWsImage);



  const displayProgress = wsProgress ?? imageProgress;

  const showProgress =

    !inPrologue &&

    displayProgress != null &&

    displayProgress.completed < displayProgress.total;



  const imageSetters = {

    setPortraitUrl,

    setBackgroundUrl,

    setNpcPortraits,

    setTemplateId,

    setWorldState,

    setCrisisState,

    setAvailableActions,

    setImageProgress,

  };



  const syncChoicesFromServer = useCallback(async () => {
    try {
      const state = await fetchGameState();
      if (!state.initialized) return;
      if (state.inline_choices?.length) {
        setStory((prev) =>
          attachChoicesToLastEntry(prev, state.inline_choices, state.choice_transition)
        );
      }
      if (state.available_actions) setAvailableActions(state.available_actions);
      return state;
    } catch {
      return null;
    }
  }, []);

  const refreshEvents = useCallback(async () => {
    try {
      const state = await fetchGameState();
      if (state.events?.length) setGameEvents(state.events);
      else if (state.event_log?.length) setGameEvents(state.event_log as GameEventItem[]);
      if (state.inline_choices?.length) {
        setStory((prev) =>
          attachChoicesToLastEntry(prev, state.inline_choices, state.choice_transition)
        );
      }
      if (state.available_actions) setAvailableActions(state.available_actions);
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    if (loading || story.length === 0 || hasActiveChoices(story)) return;
    const now = Date.now();
    if (now - choicesSyncAtRef.current < 500) return;
    choicesSyncAtRef.current = now;
    void syncChoicesFromServer();
  }, [story, loading, syncChoicesFromServer]);

  useEffect(() => {
    return () => {
      if (prologueBannerTimerRef.current != null) {
        window.clearTimeout(prologueBannerTimerRef.current);
      }
    };
  }, []);



  useEffect(() => {

    void fetchTemplates()

      .then((r) => setTemplates(r.templates))

      .catch(() => setTemplates([]));

  }, []);



  const applyStartResponse = useCallback(
    async (data: Awaited<ReturnType<typeof startGame>>) => {
      const tid = data.template_id || templateId;
      const sessionCache = templateImageCacheRef.current[tid];
      if (sessionCache) {
        if (isUsableImageUrl(sessionCache.portrait)) setPortraitUrl(sessionCache.portrait!);
        if (isUsableImageUrl(sessionCache.background)) setBackgroundUrl(sessionCache.background!);
        if (Object.keys(sessionCache.npcs).length > 0) {
          setNpcPortraits({ ...sessionCache.npcs });
        }
      }
      setTemplateId(tid);
      const theme =
        data.ui_theme ||
        (data.world_state?.flags?.ui_theme as UiTheme | undefined) ||
        templates.find((t) => t.id === tid)?.ui_theme;
      if (theme) {
        setUiTheme(theme);
        applyUiTheme(theme);
      }
      if (data.world_ontology && data.world_state) {
        data.world_state.flags = {
          ...data.world_state.flags,
          world_ontology: data.world_ontology,
        };
      }
      setWorldState(data.world_state);
      if (data.available_actions) setAvailableActions(data.available_actions);
      if (data.chapter) setChapter(data.chapter);
      applyImagePayload(data, imageSetters);

      const mergedNpc = mergePortraitMaps(data.npc_portraits, data.image_entities);
      templateImageCacheRef.current[tid] = {
        portrait: isUsableImageUrl(data.portrait_url)
          ? data.portrait_url
          : isUsableImageUrl(data.world_state?.player?.portrait_url)
            ? data.world_state?.player?.portrait_url
            : sessionCache?.portrait,
        background: isUsableImageUrl(data.background_url)
          ? data.background_url
          : sessionCache?.background,
        npcs: Object.keys(mergedNpc).length > 0 ? mergedNpc : sessionCache?.npcs ?? {},
      };

      if (
        data.image_generation?.total &&
        data.image_generation.completed >= data.image_generation.total
      ) {
        setImageProgress(null);
      }

      const prologueText = data.prologue;
      const hasDistinctPrologue = Boolean(
        prologueText?.trim() && prologueText !== data.narrative
      );

      setStory(
        buildOpeningStory({
          prologue: prologueText,
          narrative: data.narrative,
          turn: data.turn,
          inline_choices: data.inline_choices,
          choice_transition: data.choice_transition,
        })
      );

      if (prologueBannerTimerRef.current != null) {
        window.clearTimeout(prologueBannerTimerRef.current);
      }
      if (hasDistinctPrologue) {
        setInPrologue(true);
        prologueBannerTimerRef.current = window.setTimeout(() => {
          setInPrologue(false);
          prologueBannerTimerRef.current = null;
        }, 1800);
      } else {
        setInPrologue(false);
      }

      if (data.game_mode === "demo") {
        setGameMode("demo");
      } else {
        setGameMode("random");
        if (!data.inline_choices?.length) {
          await syncChoicesFromServer();
        }
      }
      await refreshEvents();

      if (data.chapter_complete && data.session_summary) {
        setChapterComplete(true);
        setSessionSummary(data.session_summary);
      } else {
        setChapterComplete(false);
        setSessionSummary(null);
      }
    },
    [templateId, refreshEvents],
  );

  const initGame = useCallback(async (tid?: string) => {

    const useId = tid ?? templateId;

    setLoading(true);

    setInitError(null);

    setImageProgress(null);
    setChapterComplete(false);
    setSessionSummary(null);
    setGameMode("random");

    try {

      const data = await startGame(useId);

      await applyStartResponse(data);

    } catch (e) {

      setInitError(formatApiError(e, "无法连接后端，请确认服务已启动"));

    } finally {

      setLoading(false);

    }

  }, [templateId, templates, applyStartResponse]);

  const switchTemplate = useCallback(
    async (tid: string) => {
      if (tid === templateId || loading) return;
      setLoading(true);
      setInitError(null);
      setImageProgress(null);
      try {
        const data = await loadWorldTemplate(tid);
        await applyStartResponse(data);
      } catch (e) {
        setInitError(formatApiError(e, "切换世界模板失败"));
      } finally {
        setLoading(false);
      }
    },
    [templateId, loading, applyStartResponse],
  );

  const initDemoGame = useCallback(async () => {
    setLoading(true);
    setInitError(null);
    setImageProgress(null);
    setChapterComplete(false);
    setSessionSummary(null);
    setGameMode("demo");
    try {
      const data = await startDemoGame();
      setTemplateId(data.template_id || "medieval_dark_fantasy");
      await applyStartResponse(data);
    } catch (e) {
      setInitError(formatApiError(e, "无法启动演示世界"));
    } finally {
      setLoading(false);
    }
  }, [applyStartResponse]);



  useEffect(() => {

    void (async () => {

      try {

        const state = await fetchGameState();

        if (state.initialized && state.world_state) {
          setWorldState(state.world_state);
          applyImagePayload(state, imageSetters);
          if (state.events?.length) setGameEvents(state.events);
          if (state.crisis_state) setCrisisState(state.crisis_state);
          if (state.game_mode === "demo") setGameMode("demo");
          if (state.chapter_complete && state.session_summary) {
            setChapterComplete(true);
            setSessionSummary(state.session_summary);
          }
          if (state.available_actions) setAvailableActions(state.available_actions);

          if (state.narrative_history?.length) {
            let entries = storyFromHistory(state.narrative_history);
            entries = attachChoicesToLastEntry(
              entries,
              state.inline_choices,
              state.choice_transition
            );
            setStory(entries);
            setInPrologue(false);
            if (!hasActiveChoices(entries)) {
              void syncChoicesFromServer();
            }
          } else if (state.offline_narrative) {
            setStory([makeStoryEntry(state.offline_narrative)]);
          }
        } else {

          await initGame(templateId);

        }

      } catch {

        await initGame(templateId);

      }

    })();

    // eslint-disable-next-line react-hooks/exhaustive-deps

  }, []);



  const handlePortraitChange = (url: string) => {

    setPortraitUrl(url);

    setWorldState((prev) => {

      if (!prev) return prev;

      return {

        ...prev,

        player: { ...prev.player, portrait_url: url },

      };

    });

  };



  const handleAction = async (text: string, choice?: InlineChoice) => {
    const trimmed = text.trim();
    const intentObj =
      choice?.intent_payload && typeof choice.intent_payload === "object"
        ? (choice.intent_payload as Record<string, unknown>)
        : null;
    const intentTarget =
      typeof intentObj?.target === "string" && intentObj.target.startsWith("inv_")
        ? intentObj.target
        : undefined;
    const choiceId =
      choice && !choice.is_free && choice.id && choice.id !== "free_input"
        ? choice.id.trim()
        : undefined;
    const intentActionId =
      typeof intentObj?.action_id === "string" && intentObj.action_id.trim()
        ? intentObj.action_id.trim()
        : undefined;

    const actionId =
      choiceId ||
      intentActionId ||
      (choice?.id?.startsWith("inv_") ? choice.id : undefined) ||
      intentTarget;

    if (!actionId && (!trimmed || loading || chapterComplete)) return;
    if (actionId && (loading || chapterComplete)) return;

    setLoading(true);

    setInput("");

    try {

      const selectedText = choice?.text?.trim();
      const intentPayload =
        choice && !choice.is_free && actionId
          ? {
              ...(intentObj && typeof intentObj === "object" ? intentObj : {}),
              action_id: actionId,
              mode: "demo_script",
            }
          : undefined;
      const payloadInput = actionId ? "" : trimmed; // 点击选项不走 parser
      const data = await submitAction(
        payloadInput,
        selectedText ? selectedText : undefined,
        actionId,
        intentPayload
      );

      setWorldState(data.world_state);

      if (data.available_actions) setAvailableActions(data.available_actions);

      setStory((prev) =>
        attachChoicesToLastEntry(
          [
            ...prev,
            makeStoryEntry(data.narrative, {
              turn: data.turn,
              kind: "narrative",
              inline_choices: data.inline_choices,
              choice_transition: data.choice_transition,
            }),
          ],
          data.inline_choices,
          data.choice_transition
        )
      );

      applyImagePayload(data, imageSetters);

      if (data.chapter) setChapter(data.chapter);

      if (data.dice_roll_info) setShowDice(data.dice_roll_info);

      if (data.crisis_state) setCrisisState(data.crisis_state);

      if (data.chapter_complete && data.session_summary) {
        setChapterComplete(true);
        setSessionSummary(data.session_summary);
      }

      if (data.game_mode === "demo") setGameMode("demo");
      if (!data.inline_choices?.length) {
        await syncChoicesFromServer();
      } else {
        await refreshEvents();
      }

    } catch (e) {

      setStory((prev) => [

        ...prev,

        makeStoryEntry(`行动失败：${formatApiError(e, "未知错误")}`, { kind: "narrative" }),

      ]);

      await syncChoicesFromServer();

    } finally {

      setLoading(false);

    }

  };

  const isDemoPlay = gameMode === "demo" && !chapterComplete;

  const chapterDisplay =

    chapter && !inPrologue ? `Chapter ${chapter.number} · ${chapter.title}` : null;

  const focusFreeInput = useCallback(() => {
    document.getElementById("free-action-input")?.focus();
  }, []);

  const freeInputPlaceholder = useMemo(() => {
    const tid = String(worldState?.flags?.template_id ?? templateId);
    if (tid.includes("xianxia")) {
      return "例如：我以符箓探路，向玄尘道人打听结界裂痕";
    }
    return "例如：我假装喝醉，靠近守卫听他们谈话";
  }, [worldState?.flags, templateId]);

  const freeInputHint = useMemo(() => {
    const onto = getOntologyFromState(worldState);
    return uiTerm(onto, "free_action_hint", "自由行动 · 在上方选择，或自行描述");
  }, [worldState]);

  return (

    <div className="h-dvh max-h-dvh flex flex-col p-2 md:p-3 max-w-[1800px] mx-auto gap-2 overflow-hidden">

      <header className="text-center py-0.5 opacity-50 shrink-0">

        <p className="text-[10px] tracking-[0.3em] text-fantasy-muted uppercase">

          Dynamic World RPG

        </p>

      </header>



      {initError && (

        <div className="rounded-lg border border-red-800 bg-red-950/50 p-3 text-sm text-red-200 shrink-0">

          {initError}

          <button type="button" className="ml-4 underline" onClick={() => void initGame()}>

            重试

          </button>

        </div>

      )}



      <div className="flex-1 grid grid-cols-1 xl:grid-cols-[minmax(200px,228px)_minmax(0,1fr)_minmax(248px,288px)] gap-2 md:gap-3 min-h-0 overflow-y-auto xl:overflow-hidden items-stretch">

        <aside className="hidden xl:flex flex-col gap-2 min-h-0 overflow-hidden xl:sticky xl:top-2 xl:self-start xl:max-h-[calc(100dvh-7rem)]">
          {templates.length > 0 && (
            <div className="rounded-lg border border-fantasy-border bg-fantasy-panel/80 p-2 shrink-0">
              <TemplateSelect
                templates={templates}
                selectedId={templateId}
                onSelect={(id) => void switchTemplate(id)}
                disabled={loading}
              />
            </div>
          )}
          <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain">
            <CharacterPanel
              player={worldState?.player ?? null}
              portraitUrl={portraitUrl}
              onPortraitChange={handlePortraitChange}
            />
          </div>
        </aside>



        <main className="flex min-h-0 flex-1 flex-col gap-2 min-w-0 overflow-hidden">

          <div className="flex shrink-0 flex-col gap-2">
            <ImageProgressBar
              completed={displayProgress?.completed ?? 0}
              total={displayProgress?.total ?? 0}
              visible={showProgress}
            />

            {scene && (
              <SceneBanner
                scene={scene}
                backgroundUrl={backgroundUrl}
                chapterTitle={chapterDisplay}
                prologueMode={inPrologue}
                templateId={templateId}
              />
            )}
          </div>

          {scene && !inPrologue && (
            <div className="shrink-0">
              <SceneNpcStrip scene={scene} compact />
            </div>
          )}

          <div id="adventure-log" className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <NarrativeFeed
              entries={story}
              loading={loading}
              disabled={loading}
              onSelectChoice={(inp, choice) => void handleAction(inp, choice)}
              onFocusFreeInput={focusFreeInput}
            />
          </div>

          <div className="z-30 shrink-0 pb-1">
            {!isDemoPlay && (
              <ActionBar
                value={input}
                onChange={setInput}
                onSubmit={() => void handleAction(input)}
                disabled={loading || chapterComplete}
                placeholder={freeInputPlaceholder}
                hintText={freeInputHint}
              />
            )}
          </div>

        </main>



        <aside className="min-h-[280px] xl:min-h-0 xl:overflow-hidden xl:sticky xl:top-2 xl:self-start xl:max-h-[calc(100dvh-7rem)] flex flex-col">

          <WorldPanel

            worldState={worldState}

            crisisState={crisisState}

            eventFeed={eventFeed}


          />

        </aside>

      </div>



      <DiceOverlay dice={showDice} onClose={() => setShowDice(null)} />
      <DebugInspector open={showInspector} onClose={() => setShowInspector(false)} />

      {chapterComplete && sessionSummary && (
        <ChapterComplete
          summary={sessionSummary}
          loading={loading}
          onViewAdventureLog={() => {
            setChapterComplete(false);
            requestAnimationFrame(() => {
              document.getElementById("adventure-log")?.scrollIntoView({ behavior: "smooth", block: "start" });
            });
          }}
          onRestartDemo={() => void initDemoGame()}
          onNewGame={() => void initGame(templateId)}
        />
      )}



      <footer className="text-center flex flex-col items-center gap-2 shrink-0 pb-2">

        {templates.length > 0 && (

          <div className="xl:hidden w-full max-w-xs">

            <TemplateSelect

              templates={templates}

              selectedId={templateId}

              onSelect={(id) => void switchTemplate(id)}

              disabled={loading}

            />

          </div>

        )}

        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            disabled={loading}
            onClick={() => void initGame(templateId)}
            className="text-xs text-fantasy-muted hover:text-fantasy-gold underline"
          >
            New Random Game
          </button>
          <span className="text-fantasy-border text-xs">|</span>
          <button
            type="button"
            disabled={loading}
            onClick={() => void initDemoGame()}
            className="text-xs text-fantasy-gold hover:text-amber-200 underline"
          >
            New Demo Game
          </button>
          <span className="text-fantasy-border text-xs">|</span>
          <button
            type="button"
            disabled={loading}
            onClick={() => setShowInspector(true)}
            className="text-xs text-fantasy-muted hover:text-fantasy-gold underline"
          >
            Debug / Inspector
          </button>
        </div>
        <p className="text-[10px] text-fantasy-muted/80">
          演示章节：预设叙事分支（New Demo Game）
        </p>

      </footer>

    </div>

  );

}


