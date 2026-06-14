"""Pydantic request/response schemas."""
from typing import Literal, List, Optional

from pydantic import BaseModel, Field, model_validator


class DistilStage(BaseModel):
    model: str = ""
    enabled: bool = True
    strength: float = Field(default=1.0, ge=0.0, le=1.5)


class LoraItem(BaseModel):
    name: str
    enabled: bool = True
    strength: float = Field(default=1.0, ge=0.0, le=1.5)


class Pipeline(BaseModel):
    text_encoder: str = ""
    text_projection: str = ""
    upscaler: str = ""
    audio_vae: str = ""
    video_vae: str = ""
    checkpoint: str = ""
    distil1: DistilStage = Field(default_factory=lambda: DistilStage(strength=0.25))
    distil2: DistilStage = Field(default_factory=lambda: DistilStage(strength=0.5))
    loras: List[LoraItem] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _fill_stage_defaults(cls, data):
        if data is None:
            return data
        if not isinstance(data, dict):
            return data
        out = dict(data)
        for key, default in (("distil1", 0.25), ("distil2", 0.5)):
            stage = out.get(key)
            if stage is None:
                continue
            if isinstance(stage, dict) and "strength" not in stage:
                out[key] = {**stage, "strength": default}
        return out


class GenerateRequest(BaseModel):
    mode: Literal["i2v", "t2v"] = "i2v"
    image_id: Optional[str] = None
    intent: str = ""
    creativity: float = Field(default=0.7, ge=0.0, le=1.0)
    duration: int = Field(default=30, ge=1, le=240)
    fps: int = Field(default=25, ge=1, le=120)
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
    duration: int = Field(default=30, ge=1, le=240)
    fps: int = Field(default=25, ge=1, le=120)
    frames: int = 0
    width: int = Field(default=1216, ge=64, le=8192)
    height: int = Field(default=704, ge=64, le=8192)


class RenderRequest(BaseModel):
    mode: Literal["i2v", "t2v"] = "i2v"
    image_id: Optional[str] = None
    prompt: str = ""
    seed: int = 0
    params: RenderParams = Field(default_factory=RenderParams)
    pipeline: Pipeline = Field(default_factory=Pipeline)
    keep_timestamps: Optional[bool] = None   # None -> use settings default
    ui_snapshot: Optional[dict] = None       # full UI state for history reuse


class SettingsPatch(BaseModel):
    llm_mode: Optional[Literal["embedded", "managed", "external"]] = None
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
    prompt_style: Optional[Literal["auto", "sulphur", "director"]] = None
    keep_timestamps: Optional[bool] = None
    negative_prompt: Optional[str] = None


class LlmStartRequest(BaseModel):
    gguf: Optional[str] = None
    mmproj: Optional[str] = None
