import React, { useCallback, useRef, useState } from "react";
import { useStore } from "../store";
import { snapFrames } from "../lib/prompt";
import { PillToggle, SectionTitle, Select, Slider } from "./ui";
import { IconCamera, IconChat, IconEye, IconFilm, IconUpload, IconWalk, IconX } from "./icons";

function Tabs() {
  const mode = useStore((s) => s.mode);
  const set = useStore((s) => s.set);
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {(["i2v", "t2v"] as const).map((m) => {
        const active = mode === m;
        return (
          <button
            key={m}
            type="button"
            onClick={() => set({ mode: m })}
            className={`flex items-center justify-center gap-1.5 py-[7px] rounded-sm border text-micro font-bold tracking-[0.2em] transition-all ${
              active
                ? "border-acid bg-acid/15 text-acid shadow-glow"
                : "border-line bg-panel2 text-dim hover:text-fog hover:border-line2"
            }`}
          >
            {m === "i2v" ? <IconCamera size={12} /> : <IconFilm size={12} />}
            {m.toUpperCase()}
          </button>
        );
      })}
    </div>
  );
}

function ReferenceImage() {
  const image = useStore((s) => s.image);
  const upload = useStore((s) => s.uploadImage);
  const set = useStore((s) => s.set);
  const toast = useStore((s) => s.toast);
  const [drag, setDrag] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const onFiles = useCallback(
    (files: FileList | null) => {
      if (!files || !files.length) return;
      const f = files[0];
      if (!f.type.startsWith("image/")) {
        toast("仅支持图片文件（png/jpg/webp）", "err");
        return;
      }
      upload(f);
    },
    [upload, toast]
  );

  return (
    <div className="space-y-1.5">
      <SectionTitle label="Reference Image / 参考图" hint="首帧 · I2V" />
      {image ? (
        <div className="relative border border-line rounded-sm overflow-hidden group">
          <img src={image.url} alt="reference" className="w-full aspect-video object-cover" />
          {/* corner brackets */}
          <span className="absolute left-1 top-1 w-3 h-3 border-l-2 border-t-2 border-acid/90" />
          <span className="absolute right-1 top-1 w-3 h-3 border-r-2 border-t-2 border-acid/90" />
          <span className="absolute left-1 bottom-1 w-3 h-3 border-l-2 border-b-2 border-acid/90" />
          <span className="absolute right-1 bottom-1 w-3 h-3 border-r-2 border-b-2 border-acid/90" />
          <span className="absolute left-2 bottom-2 text-nano font-bold bg-ink/80 text-acid px-1.5 py-[2px] rounded-sm tabular-nums">
            {image.width}×{image.height}
          </span>
          <button
            type="button"
            onClick={() => set({ image: null })}
            title="移除参考图"
            className="absolute right-1.5 top-1.5 p-1 bg-ink/80 border border-line rounded-sm text-fog hover:text-danger hover:border-danger/60 transition-colors"
          >
            <IconX size={10} />
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => fileRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDrag(true);
          }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDrag(false);
            onFiles(e.dataTransfer.files);
          }}
          className={`w-full aspect-video border border-dashed rounded-sm flex flex-col items-center justify-center gap-2 transition-colors ${
            drag
              ? "border-acid bg-acid/10 text-acid"
              : "border-line bg-panel2/40 text-dim hover:border-line2 hover:text-fog"
          }`}
        >
          <IconUpload />
          <span className="text-nano tracking-[0.18em] uppercase">
            拖入图片 / 点击上传
          </span>
        </button>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          onFiles(e.target.files);
          e.currentTarget.value = "";
        }}
      />
    </div>
  );
}

export default function DirectorPanel() {
  const s = useStore();
  const frames = snapFrames(s.duration, s.fps);
  const ggufs = s.llmModels.ggufs;
  const mmprojs = s.llmModels.mmprojs;

  return (
    <div className="h-full overflow-y-auto px-3 py-3 space-y-4">
      <Tabs />

      {s.mode === "i2v" ? (
        <ReferenceImage />
      ) : (
        <div className="border border-line bg-panel2/40 rounded-sm p-2.5 text-nano text-dim leading-4">
          T2V — 纯文字成片。首帧画面将由 LLM 在 beat 1 中完整虚构并描述。
        </div>
      )}

      <div className="space-y-1.5">
        <SectionTitle
          label="LLM Model / 提示词模型"
          hint={s.llmModels.suggested ? "推荐文件名 · 未下载" : "models/llm 本地文件"}
        />
        {s.llmModels.suggested && (
          <div className="border border-amber/50 bg-amber/10 rounded-sm p-2 text-nano leading-4 text-amber">
            {s.llmModels.mock_reason ||
              "这里是推荐 GGUF/mmproj 文件名，不代表本机已下载。Linux 可运行 install_linux.sh 下载。"}
          </div>
        )}
        <div className="grid grid-cols-2 gap-1.5">
          <div className="space-y-1">
            <span className="text-nano tracking-widest text-dim uppercase">gguf</span>
            <Select value={s.gguf} onChange={(v) => s.set({ gguf: v })} options={ggufs} />
          </div>
          <div className="space-y-1">
            <span className="text-nano tracking-widest text-dim uppercase">mmproj</span>
            <Select value={s.mmproj} onChange={(v) => s.set({ mmproj: v })} options={mmprojs} />
          </div>
        </div>
      </div>

      <div className="space-y-1">
        <SectionTitle label="Creativity / 创造性" hint="LLM temperature" />
        <Slider
          label="temp bias"
          value={s.creativity}
          min={0}
          max={1}
          step={0.05}
          onChange={(v) => s.set({ creativity: v })}
          fmt={(v) => v.toFixed(2)}
          dim
        />
        <div className="text-nano text-dim/70">越高越发散，也更容易跑偏</div>
      </div>

      <div className="space-y-1.5">
        <SectionTitle label="Intent / Direction / 导演意图" hint="描述这段视频要发生什么" />
        <textarea
          value={s.intent}
          onChange={(e) => s.set({ intent: e.target.value })}
          rows={4}
          placeholder="an amazing 30-second long cinematic talking performance, about …"
          className="w-full bg-panel2 border border-line rounded-sm px-2 py-1.5 text-tiny text-lit leading-5 outline-none focus:border-line2 resize-none"
        />
      </div>

      <div className="space-y-1.5">
        <SectionTitle label="LoRA Triggers / 触发词" hint="verbatim 原样拼入" />
        <input
          value={s.loraTriggers}
          onChange={(e) => s.set({ loraTriggers: e.target.value })}
          placeholder={'trigger_word, "verbatim"…'}
          className="w-full bg-panel2 border border-line rounded-sm px-2 py-1.5 text-tiny text-lit outline-none focus:border-line2"
        />
        <div className="text-nano text-dim/70">逗号分隔 · 会逐字注入 beat 1</div>
      </div>

      <div className="space-y-1.5">
        <SectionTitle label="Shot Type / 镜头类型" />
        <Select
          value={s.shotType}
          onChange={(v) => s.set({ shotType: v })}
          options={s.shotTypes}
        />
      </div>

      <div className="flex items-center gap-1.5">
        <PillToggle on={s.dialogue} onClick={() => s.set({ dialogue: !s.dialogue })}>
          <span className="inline-flex items-center gap-1"><IconChat /> dialogue</span>
        </PillToggle>
        <PillToggle on={s.fov} onClick={() => s.set({ fov: !s.fov })}>
          <span className="inline-flex items-center gap-1"><IconEye /> fov</span>
        </PillToggle>
        <PillToggle on={s.choreo} onClick={() => s.set({ choreo: !s.choreo })} tone="amber">
          <span className="inline-flex items-center gap-1"><IconWalk /> choreo</span>
        </PillToggle>
      </div>

      <div className="space-y-2">
        <SectionTitle label="Clip Timing / 时长帧率" />
        <Slider
          label="duration"
          value={s.duration}
          min={4}
          max={40}
          step={1}
          onChange={(v) => s.set({ duration: v })}
          fmt={(v) => `${v}s`}
        />
        <Slider
          label="fps"
          value={s.fps}
          min={12}
          max={30}
          step={1}
          onChange={(v) => s.set({ fps: v })}
        />
        <div className="text-nano text-dim tabular-nums">
          <span className="text-acid font-bold">{frames}</span> frames · (8n+1) snapped
        </div>
      </div>

      <div className="space-y-1.5 pb-4">
        <SectionTitle label="Render Resolution / 渲染分辨率" hint="第一遍基础尺寸" />
        <Select
          value={s.resolutions[s.resolutionIdx]?.label || ""}
          onChange={(v) =>
            s.set({
              resolutionIdx: Math.max(
                0,
                s.resolutions.findIndex((r) => r.label === v)
              ),
            })
          }
          options={s.resolutions.map((r) => r.label)}
        />
        <div className="text-nano text-dim/70">pass 2 spatial upscale ×2 后输出更高分辨率</div>
      </div>
    </div>
  );
}
