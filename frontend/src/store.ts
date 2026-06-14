import { create } from "zustand";
import { api } from "./lib/api";
import { parseBeats, randomSeed, snapFrames, wordCount } from "./lib/prompt";
import {
  Beat,
  HistoryItem,
  JobState,
  LogEntry,
  ModelLists,
  Pipeline,
  Resolution,
  ServiceStatus,
  Settings,
} from "./types";

export interface Toast {
  id: number;
  msg: string;
  tone: "ok" | "err" | "warn";
}

interface StatusLine {
  text: string;
  tone: "ok" | "warn" | "err" | "idle";
}

let toastId = 1;

export interface ConsoleState {
  // services
  llm: ServiceStatus;
  renderService: ServiceStatus;
  wsConnected: boolean;
  // meta
  shotTypes: string[];
  resolutions: Resolution[];
  models: ModelLists | null;
  llmModels: {
    ggufs: string[];
    mmprojs: string[];
    suggested: boolean;
    source?: string;
    model_root?: string;
    required?: any[];
    missing_required?: any[];
    ready?: boolean;
  };
  settings: Settings | null;
  // director inputs
  mode: "i2v" | "t2v";
  image: { id: string; url: string; width: number; height: number } | null;
  gguf: string;
  mmproj: string;
  creativity: number;
  intent: string;
  loraTriggers: string;
  shotType: string;
  dialogue: boolean;
  fov: boolean;
  choreo: boolean;
  duration: number;
  fps: number;
  resolutionIdx: number;
  // pipeline
  pipeline: Pipeline;
  // prompt
  prompt: string;
  beats: Beat[];
  locked: boolean;
  seed: string;
  frameOverlap: number;
  transitionFade: number;
  midsceneGuide: number;
  carryI2v: boolean;
  midsceneAnchor: boolean;
  decodeTile: number;
  generating: boolean;
  refining: boolean;
  statusLine: StatusLine;
  // render bay
  job: JobState | null;
  preview: string | null;
  previewPhase: string;
  logs: LogEntry[];
  // ui
  showHistory: boolean;
  showSettings: boolean;
  toasts: Toast[];
  savedAt: number;

  // actions
  set: (p: Partial<ConsoleState>) => void;
  toast: (msg: string, tone?: Toast["tone"]) => void;
  dismissToast: (id: number) => void;
  setPrompt: (text: string) => void;
  setPipeline: (p: Partial<Pipeline>) => void;
  applyWsMessage: (msg: any) => void;
  loadInitial: () => Promise<void>;
  refreshModels: () => Promise<void>;
  refreshLlmModels: () => Promise<void>;
  generate: () => Promise<void>;
  refine: (instruction: string) => Promise<void>;
  render: () => Promise<void>;
  cancelJob: () => Promise<void>;
  saveAll: () => Promise<void>;
  uploadImage: (file: File) => Promise<void>;
  applySnapshot: (snap: any) => void;
  snapshot: () => any;
  distilConflict: () => boolean;
  reconnectLlm: () => Promise<void>;
  reconnectRender: () => Promise<void>;
}

const defaultDistil = (model = "") => ({
  model,
  enabled: true,
  strength: 1.0,
  visual: 0.85,
  audio: 0.9,
});

const initialPipeline: Pipeline = {
  text_encoder: "",
  text_projection: "",
  upscaler: "",
  audio_vae: "",
  preview_vae: "",
  checkpoint: "",
  distil1: defaultDistil(),
  distil2: { ...defaultDistil(), visual: 0.64 },
  loras: [],
};

const validOrEmpty = (value: string, options: string[]) =>
  value && options.includes(value) ? value : "";

const sanitizePipeline = (pipeline: Pipeline, models: ModelLists): Pipeline => ({
  ...pipeline,
  text_encoder: validOrEmpty(pipeline.text_encoder, models.text_encoders),
  text_projection: validOrEmpty(pipeline.text_projection, models.text_projections),
  upscaler: validOrEmpty(pipeline.upscaler, models.upscalers),
  audio_vae: validOrEmpty(pipeline.audio_vae, models.audio_vaes),
  preview_vae: validOrEmpty(pipeline.preview_vae, models.preview_vaes),
  checkpoint: validOrEmpty(pipeline.checkpoint, models.checkpoints),
  distil1: {
    ...pipeline.distil1,
    model: validOrEmpty(pipeline.distil1.model, models.loras),
  },
  distil2: {
    ...pipeline.distil2,
    model: validOrEmpty(pipeline.distil2.model, models.loras),
  },
  loras: pipeline.loras.filter((l) => models.loras.includes(l.name)),
});

const fillPipelineDefaults = (pipeline: Pipeline, models: ModelLists): Pipeline => ({
  ...pipeline,
  text_encoder: pipeline.text_encoder || models.text_encoders[0] || "",
  text_projection: pipeline.text_projection || models.text_projections[0] || "",
  upscaler: pipeline.upscaler || models.upscalers[0] || "",
  audio_vae: pipeline.audio_vae || models.audio_vaes[0] || "",
  preview_vae: pipeline.preview_vae || models.preview_vaes[0] || "",
  checkpoint: pipeline.checkpoint || models.checkpoints[0] || "",
  distil1: pipeline.distil1.model
    ? pipeline.distil1
    : { ...defaultDistil(models.loras[0] || ""), visual: 0.85 },
  distil2: pipeline.distil2.model
    ? pipeline.distil2
    : { ...defaultDistil(models.loras[0] || ""), visual: 0.64 },
});

export const useStore = create<ConsoleState>((set, get) => ({
  llm: { state: "stopped" },
  renderService: { state: "down", url: "" },
  wsConnected: false,
  shotTypes: ["CINEMATIC"],
  resolutions: [{ label: "1280 x 720", width: 1280, height: 720 }],
  models: null,
  llmModels: { ggufs: [], mmprojs: [], suggested: false },
  settings: null,

  mode: "i2v",
  image: null,
  gguf: "",
  mmproj: "",
  creativity: 0.7,
  intent:
    "an amazing 30-second long cinematic talking performance, about space",
  loraTriggers: "",
  shotType: "CINEMATIC",
  dialogue: true,
  fov: false,
  choreo: true,
  duration: 30,
  fps: 25,
  resolutionIdx: 0,

  pipeline: initialPipeline,

  prompt: "",
  beats: [],
  locked: false,
  seed: randomSeed(),
  frameOverlap: 16,
  transitionFade: 10,
  midsceneGuide: 0.35,
  carryI2v: true,
  midsceneAnchor: true,
  decodeTile: 0,
  generating: false,
  refining: false,
  statusLine: { text: "Awaiting direction — upload a frame or describe the shot.", tone: "idle" },

  job: null,
  preview: null,
  previewPhase: "",
  logs: [],

  showHistory: false,
  showSettings: false,
  toasts: [],
  savedAt: 0,

  set: (p) => set(p),

  toast: (msg, tone = "ok") => {
    const id = toastId++;
    set((s) => ({ toasts: [...s.toasts, { id, msg, tone }] }));
    window.setTimeout(() => get().dismissToast(id), 4500);
  },

  dismissToast: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  setPrompt: (text) => set({ prompt: text, beats: parseBeats(text) }),

  setPipeline: (p) => set((s) => ({ pipeline: { ...s.pipeline, ...p } })),

  applyWsMessage: (msg) => {
    const s = get();
    switch (msg.type) {
      case "status":
        set({ llm: msg.llm, renderService: msg.render });
        break;
      case "log":
        set({
          logs: [...s.logs, { ts: msg.ts, level: msg.level, msg: msg.msg }].slice(-400),
        });
        break;
      case "job_update": {
        if (s.job && msg.job_id !== s.job.id) break;
        const job: JobState = {
          ...(s.job || { id: msg.job_id }),
          id: msg.job_id,
          status: msg.status,
          phase: msg.phase,
          pct: msg.pct ?? s.job?.pct ?? 0,
          step: msg.step,
          total: msg.total,
          error: msg.error,
          videoUrl: msg.video_url || s.job?.videoUrl,
          thumbUrl: msg.thumb_url || s.job?.thumbUrl,
        };
        const patch: Partial<ConsoleState> = { job };
        if (msg.status === "done") {
          patch.statusLine = { text: "Render complete — final clip in the bay.", tone: "ok" };
        } else if (msg.status === "error") {
          patch.statusLine = { text: msg.error || "Render failed.", tone: "err" };
        } else if (msg.status === "cancelled") {
          patch.statusLine = { text: "Render cancelled.", tone: "warn" };
        }
        set(patch);
        break;
      }
      case "preview":
        if (!s.job || msg.job_id === s.job.id) {
          set({ preview: msg.image, previewPhase: msg.phase || "" });
        }
        break;
      default:
        break;
    }
  },

  loadInitial: async () => {
    const { toast } = get();
    try {
      const [meta, settings] = await Promise.all([api.meta(), api.getSettings()]);
      set({
        shotTypes: meta.shot_types,
        resolutions: meta.resolutions,
        settings,
      });
    } catch (e: any) {
      toast(`初始化失败：${e.message}`, "err");
    }
    await Promise.all([get().refreshModels(), get().refreshLlmModels()]);
    try {
      const st = await api.status();
      set({ llm: st.llm, renderService: st.render });
    } catch {
      /* ws will update */
    }
    try {
      const ui = await api.getUiState();
      if (ui.state) get().applySnapshot(ui.state);
    } catch {
      /* fresh start */
    }
    // Drop stale saved model names, then choose defaults from real local files.
    const s = get();
    if (s.models) {
      const pipeline = fillPipelineDefaults(sanitizePipeline(s.pipeline, s.models), s.models);
      set({ pipeline });
    }
    const afterModels = get();
    const gguf = validOrEmpty(afterModels.gguf, afterModels.llmModels.ggufs);
    const mmproj = validOrEmpty(afterModels.mmproj, afterModels.llmModels.mmprojs);
    if (gguf !== afterModels.gguf || mmproj !== afterModels.mmproj) {
      set({ gguf, mmproj });
    }
    if (!get().gguf && get().llmModels.ggufs.length) {
      set({
        gguf: get().llmModels.ggufs[0],
        mmproj: get().llmModels.mmprojs[0] || "",
      });
    }
  },

  refreshModels: async () => {
    try {
      const models = await api.models();
      set((s) => ({
        models,
        pipeline: fillPipelineDefaults(sanitizePipeline(s.pipeline, models), models),
      }));
    } catch (e: any) {
      get().toast(`模型列表获取失败：${e.message}`, "err");
    }
  },

  refreshLlmModels: async () => {
    try {
      const lm = await api.llmModels();
      set((s) => ({
        llmModels: lm,
        gguf: validOrEmpty(s.gguf, lm.ggufs),
        mmproj: validOrEmpty(s.mmproj, lm.mmprojs),
      }));
    } catch {
      /* non-fatal */
    }
  },

  generate: async () => {
    const s = get();
    if (s.generating) return;
    if (s.mode === "i2v" && !s.image) {
      s.toast("I2V 模式需要先上传参考图（或切到 T2V）", "err");
      return;
    }
    if (s.locked) {
      s.toast("提示词已 LOCKED — 先解锁再生成，防止误覆盖", "warn");
      return;
    }
    set({
      generating: true,
      statusLine: { text: "Directing… LLM is writing the shot list.", tone: "warn" },
    });
    try {
      const res = await api.generate({
        mode: s.mode,
        image_id: s.image?.id,
        intent: s.intent,
        creativity: s.creativity,
        duration: s.duration,
        fps: s.fps,
        shot_type: s.shotType,
        dialogue: s.dialogue,
        fov: s.fov,
        choreo: s.choreo,
        lora_triggers: s.loraTriggers,
        gguf: s.gguf,
        mmproj: s.mmproj,
      });
      set({
        prompt: res.prompt,
        beats: res.beats,
        statusLine: {
          text: "Prompt ready — edit or Render.",
          tone: "ok",
        },
      });
    } catch (e: any) {
      set({ statusLine: { text: e.message, tone: "err" } });
      get().toast(e.message, "err");
    } finally {
      set({ generating: false });
    }
  },

  refine: async (instruction: string) => {
    const s = get();
    if (s.refining) return;
    if (!s.prompt.trim()) {
      s.toast("还没有提示词 — 先 GENERATE", "err");
      return;
    }
    if (s.locked) {
      s.toast("提示词已 LOCKED — 先解锁再 Refine", "warn");
      return;
    }
    if (!instruction.trim()) {
      s.toast("输入修改指令，如 “make beat 2 slower”", "warn");
      return;
    }
    set({
      refining: true,
      statusLine: { text: "Refining the cut…", tone: "warn" },
    });
    try {
      const res = await api.refine({
        mode: s.mode,
        image_id: s.image?.id,
        intent: s.intent,
        creativity: s.creativity,
        duration: s.duration,
        fps: s.fps,
        shot_type: s.shotType,
        dialogue: s.dialogue,
        fov: s.fov,
        choreo: s.choreo,
        lora_triggers: s.loraTriggers,
        prompt: s.prompt,
        instruction,
      });
      set({
        prompt: res.prompt,
        beats: res.beats,
        statusLine: {
          text: `Refined — ${res.words} words.`,
          tone: "ok",
        },
      });
    } catch (e: any) {
      set({ statusLine: { text: e.message, tone: "err" } });
      get().toast(e.message, "err");
    } finally {
      set({ refining: false });
    }
  },

  distilConflict: () => {
    const p = get().pipeline;
    const ckpt = (p.checkpoint || "").toLowerCase();
    const anyDistil =
      (p.distil1.enabled && !!p.distil1.model) ||
      (p.distil2.enabled && !!p.distil2.model);
    return ckpt.includes("distil") && anyDistil;
  },

  render: async () => {
    const s = get();
    if (!s.prompt.trim()) {
      s.toast("提示词为空 — 先 GENERATE 或手动输入", "err");
      return;
    }
    if (s.mode === "i2v" && !s.image) {
      s.toast("I2V 渲染需要参考图", "err");
      return;
    }
    if (s.distilConflict()) {
      s.toast(
        "Distill LoRA 与完整 distilled checkpoint 互斥：关闭 DISTIL 或换 checkpoint",
        "err"
      );
      set({
        statusLine: {
          text: "DISTIL conflict — distilled checkpoint + distil LoRA cannot stack.",
          tone: "err",
        },
      });
      return;
    }
    if (s.job && (s.job.status === "running" || s.job.status === "queued")) {
      s.toast("已有任务在渲染中（会排队执行）", "warn");
    }
    const res0 = s.resolutions[s.resolutionIdx] || s.resolutions[0];
    const seedNum = /^\d+$/.test(s.seed.trim()) ? Number(s.seed.trim()) : 0;
    set({
      preview: null,
      previewPhase: "",
      statusLine: { text: "Submitting to render queue…", tone: "warn" },
    });
    try {
      const res = await api.render({
        mode: s.mode,
        image_id: s.image?.id,
        prompt: s.prompt,
        seed: seedNum,
        params: {
          duration: s.duration,
          fps: s.fps,
          frames: snapFrames(s.duration, s.fps),
          width: res0.width,
          height: res0.height,
          frame_overlap: s.frameOverlap,
          transition_fade: s.transitionFade,
          midscene_guide: s.midsceneGuide,
          carry_i2v_guides: s.carryI2v,
          midscene_anchor: s.midsceneAnchor,
          decode_tile: s.decodeTile,
        },
        pipeline: s.pipeline,
        ui_snapshot: get().snapshot(),
      });
      set({
        seed: String(res.seed),
        job: {
          id: res.job_id,
          status: "queued",
          phase: "queued",
          pct: 0,
          seed: res.seed,
        },
        statusLine: {
          text: `Rendering — job ${res.job_id}.`,
          tone: "warn",
        },
      });
    } catch (e: any) {
      set({ statusLine: { text: e.message, tone: "err" } });
      get().toast(e.message, "err");
    }
  },

  cancelJob: async () => {
    const s = get();
    if (!s.job) return;
    try {
      await api.cancel(s.job.id);
    } catch (e: any) {
      s.toast(e.message, "warn");
    }
  },

  snapshot: () => {
    const s = get();
    return {
      mode: s.mode,
      image: s.image,
      gguf: s.gguf,
      mmproj: s.mmproj,
      creativity: s.creativity,
      intent: s.intent,
      loraTriggers: s.loraTriggers,
      shotType: s.shotType,
      dialogue: s.dialogue,
      fov: s.fov,
      choreo: s.choreo,
      duration: s.duration,
      fps: s.fps,
      resolutionIdx: s.resolutionIdx,
      pipeline: s.pipeline,
      prompt: s.prompt,
      locked: s.locked,
      seed: s.seed,
      frameOverlap: s.frameOverlap,
      transitionFade: s.transitionFade,
      midsceneGuide: s.midsceneGuide,
      carryI2v: s.carryI2v,
      midsceneAnchor: s.midsceneAnchor,
      decodeTile: s.decodeTile,
    };
  },

  applySnapshot: (snap) => {
    if (!snap || typeof snap !== "object") return;
    const safe: Partial<ConsoleState> = {};
    const keys = [
      "mode", "image", "gguf", "mmproj", "creativity", "intent", "loraTriggers",
      "shotType", "dialogue", "fov", "choreo", "duration", "fps", "resolutionIdx",
      "pipeline", "prompt", "locked", "seed", "frameOverlap", "transitionFade",
      "midsceneGuide", "carryI2v", "midsceneAnchor", "decodeTile",
    ] as const;
    for (const k of keys) {
      if (snap[k] !== undefined) (safe as any)[k] = snap[k];
    }
    if (typeof safe.prompt === "string") {
      (safe as any).beats = parseBeats(safe.prompt);
    }
    set(safe);
  },

  saveAll: async () => {
    try {
      await api.saveUiState(get().snapshot());
      set({ savedAt: Date.now() });
      get().toast("已保存当前控制台状态", "ok");
    } catch (e: any) {
      get().toast(`保存失败：${e.message}`, "err");
    }
  },

  uploadImage: async (file: File) => {
    try {
      const res = await api.upload(file);
      set({
        image: { id: res.id, url: res.url, width: res.width, height: res.height },
      });
      get().toast(`参考图已上传 ${res.width}×${res.height}`, "ok");
    } catch (e: any) {
      get().toast(`上传失败：${e.message}`, "err");
    }
  },

  reconnectLlm: async () => {
    const s = get();
    if (
      (s.settings?.llm_mode === "embedded" || s.settings?.llm_mode === "managed") &&
      s.llm.state !== "running" &&
      s.llm.state !== "starting" &&
      s.llm.state !== "loading"
    ) {
      try {
        get().toast(
          s.settings?.llm_mode === "embedded"
            ? "正在加载内置本地 LLM 引擎 …"
            : "正在启动兼容 LLM 子进程 …",
          "warn"
        );
        await api.llmStart(s.gguf || undefined, s.mmproj || undefined);
      } catch (e: any) {
        get().toast(e.message, "err");
      }
    }
    try {
      const st = await api.status();
      set({ llm: st.llm, renderService: st.render });
    } catch {
      /* ignore */
    }
  },

  reconnectRender: async () => {
    try {
      const st = await api.status();
      set({ llm: st.llm, renderService: st.render });
      if (st.render.state === "running") {
        get().toast("本地 LTX 渲染器已就绪", "ok");
        await get().refreshModels();
      } else {
        get().toast(st.render.detail || "本地 LTX 渲染器尚未就绪", "warn");
      }
    } catch (e: any) {
      get().toast(e.message, "err");
    }
  },
}));

export function deriveWords(prompt: string): number {
  return wordCount(prompt);
}
