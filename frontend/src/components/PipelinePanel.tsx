import React from "react";
import { useStore } from "../store";
import { DistilStage, LoraItem } from "../types";
import { GhostButton, SectionTitle, Select, Slider, Switch } from "./ui";
import { IconX } from "./icons";

function ModelSlot({
  label,
  tag,
  value,
  options,
  onChange,
}: {
  label: string;
  tag: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <span className="text-nano font-bold tracking-[0.16em] uppercase text-fog">
          {label}
        </span>
        <span className="text-nano text-dim/80 truncate max-w-[120px]">{tag}</span>
      </div>
      <Select value={value} onChange={onChange} options={options} />
    </div>
  );
}

function DistilBlock({
  title,
  stage,
  loras,
  onChange,
}: {
  title: string;
  stage: DistilStage;
  loras: string[];
  onChange: (s: DistilStage) => void;
}) {
  return (
    <div className="border border-line bg-panel2/40 rounded-sm p-2 space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-nano font-bold tracking-[0.16em] uppercase text-fog">
          {title}
        </span>
        <Switch on={stage.enabled} onChange={(v) => onChange({ ...stage, enabled: v })} />
      </div>
      <Select
        value={stage.model}
        onChange={(v) => onChange({ ...stage, model: v })}
        options={loras}
      />
      <div className={stage.enabled ? "space-y-1.5" : "space-y-1.5 opacity-40 pointer-events-none"}>
        <Slider
          label="Str"
          value={stage.strength}
          min={0}
          max={1.5}
          step={0.01}
          onChange={(v) => onChange({ ...stage, strength: v })}
          fmt={(v) => v.toFixed(2)}
        />
      </div>
    </div>
  );
}

export default function PipelinePanel() {
  const s = useStore();
  const m = s.models;
  const p = s.pipeline;
  const conflict = s.distilConflict();
  const missing = m?.missing_required || [];

  if (!m) {
    return (
      <div className="p-3 text-micro text-dim">正在扫描模型目录…</div>
    );
  }

  const addLora = () => {
    const remaining = m.loras.filter(
      (l) => !p.loras.some((x) => x.name === l)
    );
    const name = remaining[0] || m.loras[0];
    if (!name) return;
    s.setPipeline({
      loras: [...p.loras, { name, enabled: true, strength: 1.0 }],
    });
  };

  const setLora = (i: number, item: LoraItem | null) => {
    const next = [...p.loras];
    if (item === null) next.splice(i, 1);
    else next[i] = item;
    s.setPipeline({ loras: next });
  };

  return (
    <div className="h-full overflow-y-auto px-3 py-3 space-y-4">
      <SectionTitle
        label="Pipeline / 管线"
        hint="models/ltx 本地扫描"
      />

      {missing.length > 0 && (
        <div className="border border-amber/50 bg-amber/10 rounded-sm p-2 text-nano leading-4 text-amber">
          <div className="font-bold tracking-[0.16em] uppercase mb-1">
            缺少必要模型 · {missing.length}
          </div>
          {missing.slice(0, 5).map((it) => (
            <div key={it.key} className="truncate" title={`${it.repo}/${it.filename}`}>
              {it.name}
            </div>
          ))}
          <div className="text-dim/90 mt-1 truncate" title={m.model_root || ""}>
            扫描目录：{m.model_root || "models/ltx"}
          </div>
        </div>
      )}

      <div className="space-y-3">
        <ModelSlot
          label="text encoder / 文本编码器"
          tag="Gemma weights"
          value={p.text_encoder}
          options={m.text_encoders}
          onChange={(v) => s.setPipeline({ text_encoder: v })}
        />
        <ModelSlot
          label="text projection / 文本投影"
          tag="ltx-2.3 proj"
          value={p.text_projection}
          options={m.text_projections}
          onChange={(v) => s.setPipeline({ text_projection: v })}
        />
        <ModelSlot
          label="upscaler / 空间上采样"
          tag="two-stage x2"
          value={p.upscaler}
          options={m.upscalers}
          onChange={(v) => s.setPipeline({ upscaler: v })}
        />
        <ModelSlot
          label="audio vae / 音频 VAE"
          tag="audio decoder"
          value={p.audio_vae}
          options={m.audio_vaes}
          onChange={(v) => s.setPipeline({ audio_vae: v })}
        />
        <ModelSlot
          label="video vae / 视频 VAE"
          tag="optional split VAE"
          value={p.video_vae}
          options={m.video_vaes || []}
          onChange={(v) => s.setPipeline({ video_vae: v })}
        />
        <ModelSlot
          label="checkpoint / 主检查点"
          tag="LTX checkpoint"
          value={p.checkpoint}
          options={m.checkpoints}
          onChange={(v) => s.setPipeline({ checkpoint: v })}
        />
      </div>

      <div className="space-y-2">
        <SectionTitle label="Distil / 蒸馏 LoRA" hint="推荐 cond_safe" />
        {conflict && (
          <div className="border border-danger/60 bg-danger/10 rounded-sm p-2 text-nano leading-4 text-danger">
            DISTILLED CHECKPOINT + DISTIL LORA 互斥 — 二选一：
            关闭下方两组 Distil，或换非 distilled checkpoint。
          </div>
        )}
        <DistilBlock
          title="first stage distil"
          stage={p.distil1}
          loras={m.loras}
          onChange={(d) => s.setPipeline({ distil1: d })}
        />
        <DistilBlock
          title="second stage distil"
          stage={p.distil2}
          loras={m.loras}
          onChange={(d) => s.setPipeline({ distil2: d })}
        />
      </div>

      <div className="space-y-2 pb-4">
        <SectionTitle
          label="Loras / 附加 LoRA"
          hint="两遍渲染都会应用"
          right={
            <GhostButton onClick={addLora} className="!py-[3px]">
              + 添加 LoRA
            </GhostButton>
          }
        />
        {p.loras.length === 0 && (
          <div className="text-nano text-dim border border-dashed border-line rounded-sm px-2 py-3 text-center">
            暂无额外 LoRA — 镜头运动由提示词驱动
          </div>
        )}
        {p.loras.map((l, i) => (
          <div key={i} className="border border-line bg-panel2/40 rounded-sm p-2 space-y-1.5">
            <div className="flex items-center gap-1.5">
              <Switch on={l.enabled} onChange={(v) => setLora(i, { ...l, enabled: v })} />
              <div className="flex-1 min-w-0">
                <Select
                  value={l.name}
                  onChange={(v) => setLora(i, { ...l, name: v })}
                  options={m.loras}
                />
              </div>
              <button
                type="button"
                className="text-dim hover:text-danger p-1"
                onClick={() => setLora(i, null)}
                title="移除"
              >
                <IconX size={10} />
              </button>
            </div>
            <div className={l.enabled ? "" : "opacity-40 pointer-events-none"}>
              <Slider
                label="strength"
                value={l.strength}
                min={0}
                max={1.5}
                step={0.01}
                onChange={(v) => setLora(i, { ...l, strength: v })}
                fmt={(v) => v.toFixed(2)}
                dim
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
