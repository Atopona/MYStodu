"""Pydantic request/response schemas."""
from typing import List, Optional

from pydantic import BaseModel, Field


class DistilStage(BaseModel):
    model: str = ""
    enabled: bool = True
    strength: float = 1.0
    visual: float = 1.0
    audio: float = 1.0


class LoraItem(BaseModel):
    name: str
    enabled: bool = True
    strength: float = 1.0


class Pipeline(BaseModel):
    text_encoder: str = ""
    text_projection: str = ""
    upscaler: str = ""
    audio_vae: str = ""
    preview_vae: str = ""
    checkpoint: str = ""
    distil1: DistilStage = Field(default_factory=DistilStage)
    distil2: DistilStage = Field(default_factory=DistilStage)
    loras: List[LoraItem] = Field(default_factory=list)


class GenerateRequest(BaseModel):
    mode: str = "i2v"                    # i2v | t2v
    image_id: Optional[str] = None
    intent: str = ""
    creativity: float = 0.7              # 0..1 -> temperature 0..1.6
    duration: int = 30
    fps: int = 25
    shot_type: str = "CINEMATIC"
    dialogue: bool = True
    fov: bool = False
    choreo: bool = True
    lora_triggers: str = ""
    gguf: Optional[str] = None
    mmproj: Optional[str] = None


class RefineRequest(GenerateRequest):
    prompt: str = ""
    instruction: str = ""


class RenderParams(BaseModel):
    duration: int = 30
    fps: int = 25
    frames: int = 0
    width: int = 1280
    height: int = 720
    frame_overlap: int = 16
    transition_fade: int = 10
    midscene_guide: float = 0.35
    carry_i2v_guides: bool = True
    midscene_anchor: bool = True
    decode_tile: int = 0


class RenderRequest(BaseModel):
    mode: str = "i2v"
    image_id: Optional[str] = None
    prompt: str = ""
    seed: int = 0
    params: RenderParams = Field(default_factory=RenderParams)
    pipeline: Pipeline = Field(default_factory=Pipeline)
    keep_timestamps: Optional[bool] = None   # None -> use settings default
    ui_snapshot: Optional[dict] = None       # full UI state for history reuse


class SettingsPatch(BaseModel):
    llm_mode: Optional[str] = None
    llama_server_path: Optional[str] = None
    llm_host: Optional[str] = None
    llm_port: Optional[int] = None
    llm_gguf: Optional[str] = None
    llm_mmproj: Optional[str] = None
    llm_ngl: Optional[int] = None
    llm_ctx: Optional[int] = None
    llm_extra_args: Optional[str] = None
    llm_api_key: Optional[str] = None
    external_llm_url: Optional[str] = None
    auto_start_llm: Optional[bool] = None
    prompt_style: Optional[str] = None
    keep_timestamps: Optional[bool] = None
    negative_prompt: Optional[str] = None


class LlmStartRequest(BaseModel):
    gguf: Optional[str] = None
    mmproj: Optional[str] = None
