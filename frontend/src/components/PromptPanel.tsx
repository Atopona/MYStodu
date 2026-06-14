import React, { useMemo, useRef, useState } from "react";
import { useStore } from "../store";
import { highlightPrompt, randomSeed, wordCount } from "../lib/prompt";
import { GhostButton, SectionTitle, Slider, Switch } from "./ui";
import { IconBolt, IconDice, IconLock, IconPlay, IconUnlock } from "./icons";

function TimelineRuler() {
  const beats = useStore((s) => s.beats);
  const duration = useStore((s) => s.duration);
  const total = useMemo(() => {
    const last = beats.length ? beats[beats.length - 1].end : duration;
    return Math.max(last, 1);
  }, [beats, duration]);

  if (!beats.length) {
    return (
      <div className="h-10 border-b border-dashed border-line flex items-center justify-center text-nano tracking-[0.2em] text-dim/70">
        TIMELINE / 时间轴 — 点击生成后显示 beats
      </div>
    );
  }
  return (
    <div className="h-10 border-b border-line relative select-none">
      <div className="absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-line via-line2 to-line" />
      <div className="flex h-full">
        {beats.map((b, i) => {
          const w = ((b.end - b.start) / total) * 100;
          return (
            <div
              key={i}
              className="relative h-full border-r border-dotted border-line2/70 last:border-r-0 px-1.5 pt-1 overflow-hidden"
              style={{ width: `${w}%` }}
              title={`${b.start}-${b.end}s ${b.motion}`}
            >
              <div className="text-nano tabular-nums text-dim leading-3">
                {b.start}-{b.end}s
              </div>
              <div className="text-nano font-bold tracking-[0.14em] text-acid truncate leading-3 mt-[2px]">
                {b.motion}
              </div>
              {/* tick */}
              <span className="absolute left-0 bottom-0 w-px h-2 bg-line2" />
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PromptEditor() {
  const prompt = useStore((s) => s.prompt);
  const setPrompt = useStore((s) => s.setPrompt);
  const locked = useStore((s) => s.locked);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const hlRef = useRef<HTMLDivElement>(null);
  const html = useMemo(() => highlightPrompt(prompt), [prompt]);

  const syncScroll = () => {
    if (taRef.current && hlRef.current) {
      hlRef.current.scrollTop = taRef.current.scrollTop;
      hlRef.current.scrollLeft = taRef.current.scrollLeft;
    }
  };

  return (
    <div className="relative flex-1 min-h-0 border border-line rounded-sm bg-ink/60 overflow-hidden">
      <div
        ref={hlRef}
        aria-hidden
        className="prompt-highlight absolute inset-0 px-3 py-2.5 text-[12px] leading-[1.7] whitespace-pre-wrap break-words overflow-auto text-[#c2d4b4] pointer-events-none"
        dangerouslySetInnerHTML={{ __html: html }}
      />
      <textarea
        ref={taRef}
        value={prompt}
        spellCheck={false}
        readOnly={locked}
        onChange={(e) => setPrompt(e.target.value)}
        onScroll={syncScroll}
        placeholder={
          "[0-12s] 首帧画面、镜头运动、动作演变…\nSounds: 音效…\nVocal: 角色（语气）: \"台词\"\n\n点击 GENERATE / 生成，让本地导演 LLM 帮你撰写。"
        }
        className="absolute inset-0 w-full h-full px-3 py-2.5 bg-transparent text-transparent caret-acid text-[12px] leading-[1.7] whitespace-pre-wrap break-words resize-none outline-none placeholder:text-dim/50"
      />
      {locked && (
        <span className="absolute right-2 top-2 text-nano font-bold tracking-[0.2em] text-amber border border-amber/50 bg-amber/10 rounded-sm px-1.5 py-[2px] pointer-events-none">
          LOCKED
        </span>
      )}
    </div>
  );
}

export default function PromptPanel() {
  const s = useStore();
  const [instruction, setInstruction] = useState("");
  const words = wordCount(s.prompt);
  const busy = s.generating || s.refining;
  const jobRunning = !!s.job && (s.job.status === "running" || s.job.status === "queued");

  const toneCls =
    s.statusLine.tone === "ok"
      ? "text-neon"
      : s.statusLine.tone === "warn"
      ? "text-amber"
      : s.statusLine.tone === "err"
      ? "text-danger"
      : "text-dim";

  return (
    <div className="h-full flex flex-col px-3 py-3 gap-2.5 min-w-0">
      <SectionTitle
        label="Generated Prompt / 生成提示词"
        hint="分镜 beats · 音效 · 对白"
        right={
          <span className="text-nano text-dim tabular-nums tracking-widest">
            {words} words
          </span>
        }
      />

      <TimelineRuler />
      <PromptEditor />

      {/* refine bar */}
      <div className="flex gap-1.5">
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !busy) {
              s.refine(instruction).then(() => setInstruction(""));
            }
          }}
          placeholder="Refine / 润色 — 例如 make beat 2 slower, more dialogue, harder cuts"
          className="flex-1 bg-panel2 border border-line rounded-sm px-2.5 py-[7px] text-tiny text-lit outline-none focus:border-line2 placeholder:text-dim/60"
        />
        <button
          type="button"
          disabled={busy}
          onClick={() => s.refine(instruction).then(() => setInstruction(""))}
          className="px-3 border border-acid/60 text-acid bg-acid/10 rounded-sm text-micro font-bold tracking-[0.18em] hover:bg-acid/20 disabled:opacity-40 transition-colors inline-flex items-center gap-1.5"
        >
          <IconBolt size={11} />
          {s.refining ? "REFINING…" : "REFINE / 润色"}
        </button>
      </div>

      {/* seed + locked */}
      <div className="flex items-center gap-1.5">
        <span className="text-nano tracking-[0.18em] text-dim uppercase">seed / 种子</span>
        <input
          value={s.seed}
          onChange={(e) => s.set({ seed: e.target.value.replace(/[^\d]/g, "") })}
          className="w-40 bg-panel2 border border-line rounded-sm px-2 py-[5px] text-tiny text-acid tabular-nums outline-none focus:border-line2"
        />
        <GhostButton
          onClick={() => s.set({ seed: randomSeed() })}
          title="随机 seed"
          className="!px-2"
        >
          <IconDice size={11} />
        </GhostButton>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => s.set({ locked: !s.locked })}
          className={`inline-flex items-center gap-1.5 px-2.5 py-[5px] rounded-sm border text-nano font-bold tracking-[0.18em] transition-all ${
            s.locked
              ? "border-amber text-amber bg-amber/10 shadow-[0_0_10px_rgba(245,197,66,0.2)]"
              : "border-line text-dim bg-panel2 hover:text-fog hover:border-line2"
          }`}
          title="锁定提示词，防止 GENERATE/REFINE 误覆盖"
        >
          {s.locked ? <IconLock size={10} /> : <IconUnlock size={10} />}
          LOCKED / 锁定
        </button>
      </div>

      {/* render detail sliders */}
      <div className="border border-line bg-panel2/30 rounded-sm p-2.5 space-y-2">
        <div className="text-nano tracking-[0.16em] text-dim/80 uppercase">
          crossfade per beat / 每个 beat 交叠 — 连续长片段
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2">
          <Slider
            label="frame overlap"
            value={s.frameOverlap}
            min={0}
            max={32}
            step={1}
            onChange={(v) => s.set({ frameOverlap: v })}
            dim
          />
          <Slider
            label="transition fade"
            value={s.transitionFade}
            min={0}
            max={32}
            step={1}
            onChange={(v) => s.set({ transitionFade: v })}
            dim
          />
          <Slider
            label="mid-scene guide str"
            value={s.midsceneGuide}
            min={0}
            max={1}
            step={0.05}
            onChange={(v) => s.set({ midsceneGuide: v })}
            fmt={(v) => v.toFixed(2)}
            dim
          />
          <div className="flex flex-col justify-end gap-1.5 pb-[2px]">
            <Switch on={s.carryI2v} onChange={(v) => s.set({ carryI2v: v })} label="carry i2v guides" />
            <Switch
              on={s.midsceneAnchor}
              onChange={(v) => s.set({ midsceneAnchor: v })}
              label="mid-scene anchor"
            />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-nano tracking-[0.14em] text-dim uppercase">
            decode tile (0 = off, 512 if OOM)
          </span>
          <div className="flex gap-1">
            {[0, 256, 512, 768].map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => s.set({ decodeTile: t })}
                className={`px-2 py-[3px] rounded-sm border text-nano font-bold tabular-nums transition-colors ${
                  s.decodeTile === t
                    ? "border-acid text-acid bg-acid/10"
                    : "border-line text-dim bg-panel2 hover:border-line2"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* action buttons */}
      <div className="grid grid-cols-2 gap-2">
        <button
          type="button"
          disabled={busy}
          onClick={() => s.generate()}
          className="h-11 rounded-sm bg-gradient-to-r from-acid to-neon text-ink text-micro font-extrabold tracking-[0.3em] uppercase shadow-glow hover:brightness-110 active:brightness-95 disabled:opacity-50 disabled:cursor-wait transition-all inline-flex items-center justify-center gap-2"
        >
          <IconBolt size={13} />
          {s.generating ? "Directing…" : "Generate / 生成"}
        </button>
        <button
          type="button"
          disabled={jobRunning}
          onClick={() => s.render()}
          className="h-11 rounded-sm bg-neon/90 text-ink text-micro font-extrabold tracking-[0.3em] uppercase shadow-glowGreen hover:bg-neon active:brightness-95 disabled:opacity-50 transition-all inline-flex items-center justify-center gap-2"
        >
          <IconPlay size={13} />
          {jobRunning ? "Rendering…" : "Render / 渲染"}
        </button>
      </div>

      <div className={`text-center text-nano tracking-wider ${toneCls} min-h-[14px]`}>
        {s.statusLine.tone === "ok" && "⚡ "}
        {s.statusLine.text}
      </div>
    </div>
  );
}
