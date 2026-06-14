export interface Beat {
  start: number;
  end: number;
  motion: string;
  text: string;
}

export interface DistilStage {
  model: string;
  enabled: boolean;
  strength: number;
  visual: number;
  audio: number;
}

export interface LoraItem {
  name: string;
  enabled: boolean;
  strength: number;
}

export interface Pipeline {
  text_encoder: string;
  text_projection: string;
  upscaler: string;
  audio_vae: string;
  preview_vae: string;
  checkpoint: string;
  distil1: DistilStage;
  distil2: DistilStage;
  loras: LoraItem[];
}

export interface RequiredModelFile {
  key: string;
  label: string;
  category: string;
  repo: string;
  filename: string;
  name: string;
  url: string;
}

export interface ModelLists {
  text_encoders: string[];
  text_projections: string[];
  upscalers: string[];
  audio_vaes: string[];
  preview_vaes: string[];
  checkpoints: string[];
  loras: string[];
  source?: string;
  model_root?: string;
  required?: RequiredModelFile[];
  missing_required?: RequiredModelFile[];
  ready?: boolean;
}

export interface Resolution {
  label: string;
  width: number;
  height: number;
}

export interface Settings {
  llm_mode: "embedded" | "managed" | "external";
  llama_server_path: string;
  llm_host: string;
  llm_port: number;
  llm_gguf: string;
  llm_mmproj: string;
  llm_ngl: number;
  llm_ctx: number;
  llm_extra_args: string;
  llm_api_key: string;
  external_llm_url: string;
  auto_start_llm: boolean;
  prompt_style: "auto" | "sulphur" | "director";
  keep_timestamps: boolean;
  negative_prompt: string;
}

export interface ServiceStatus {
  state: string;
  detail?: string;
  url?: string;
  gguf?: string;
  mmproj?: string;
  mode?: string;
  tail?: string[];
}

export interface JobState {
  id: string;
  status: string;
  phase: string;
  pct: number;
  step?: number;
  total?: number;
  error?: string;
  videoUrl?: string;
  thumbUrl?: string;
  seed?: number;
}

export interface LogEntry {
  ts: number;
  level: string;
  msg: string;
}

export interface HistoryItem {
  id: string;
  created_at: number;
  mode: string;
  status: string;
  prompt: string;
  prompt_excerpt?: string;
  params: any;
  video_url: string;
  thumb_url: string;
  error?: string;
  meta: {
    seed?: number;
    frames?: number;
    width?: number;
    height?: number;
    fps?: number;
    duration?: number;
    renderer?: string;
    words?: number;
  };
}
