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
  video_vae: string;
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
  video_vaes: string[];
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
  ready?: boolean;
  dependencies_ready?: boolean;
  device_ready?: boolean;
  device?: DiagnosticsDevice;
  default_models_ready?: boolean;
  missing_required?: RequiredModelFile[];
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

export interface DiagnosticDependency {
  module: string;
  package: string;
  ok: boolean;
  error: string;
}

export interface DiagnosticRequiredFile extends RequiredModelFile {
  present: boolean;
  path: string;
  bytes: number;
}

export interface DiagnosticsDevice {
  ready: boolean;
  allow_cpu: boolean;
  torch_available: boolean;
  torch_version: string;
  torch_cuda_version: string;
  cuda_available: boolean;
  cuda_device_count: number;
  current_device: number | null;
  detail: string;
  devices: Array<{
    index: number;
    name: string;
    capability: string;
    total_memory: number;
    free_memory?: number;
    runtime_total_memory?: number;
  }>;
  nvidia_smi: {
    available: boolean;
    summary: string[];
    error: string;
  };
}

export interface DiagnosticsReport {
  python: {
    executable: string;
    version: string;
    platform: string;
  };
  paths: {
    root: string;
    llm_model_dir: string;
    ltx_model_dir: string;
    frontend_dist: string;
  };
  dependencies: {
    ready: boolean;
    items: DiagnosticDependency[];
  };
  device: DiagnosticsDevice;
  llm_models: {
    ready: boolean;
    required: DiagnosticRequiredFile[];
    scan: any;
  };
  render_models: {
    ready: boolean;
    required: DiagnosticRequiredFile[];
    scan: any;
  };
  model_integrity: {
    ok: boolean;
    skipped: boolean;
    reason?: string;
    items: Array<RequiredModelFile & {
      ok: boolean;
      path: string;
      bytes?: number;
      tensor_count?: number;
      config_required?: boolean;
      config_present?: boolean;
      error?: string;
    }>;
  };
  component_bundle: {
    ok: boolean;
    skipped: boolean;
    reason?: string;
    errors?: string[];
    config_keys?: string[];
    items?: Array<{
      role: string;
      ok: boolean;
      path: string;
      bytes?: number;
      tensor_count?: number;
      metadata_keys?: string[];
      config_keys?: string[];
      config_error?: string;
      groups?: Record<string, boolean>;
      error?: string;
    }>;
  };
  runner_entrypoint: {
    ok: boolean;
    returncode: number | null;
    stdout_tail?: string;
    stderr_tail?: string;
    error?: string;
  };
  dry_run: {
    ok: boolean;
    skipped: boolean;
    reason?: string;
    error?: string;
    command?: string[];
    summary?: Record<string, string>;
  };
  renderer_status: ServiceStatus;
  overall_ready: boolean;
}
