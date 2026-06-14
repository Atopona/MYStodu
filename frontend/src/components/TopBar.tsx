import React from "react";
import { useStore } from "../store";
import { snapFrames, wordCount } from "../lib/prompt";
import { Capsule, GhostButton, StatusDot } from "./ui";
import { IconGear, Logo } from "./icons";

const LED_COLORS = [
  "#5df06a", "#c8f53b", "#f5c542", "#ff5d5d",
  "#62d0ff", "#c77bff", "#ff8742", "#2effc8",
];

export default function TopBar() {
  const s = useStore();
  const words = wordCount(s.prompt);
  const res = s.resolutions[s.resolutionIdx] || s.resolutions[0];
  const frames = snapFrames(s.duration, s.fps);

  const llmState =
    s.llm.state === "running" ? "ok" : s.llm.state === "starting" ? "warn" : "err";
  const renderState = s.renderService.state === "running" ? "ok" : "err";

  return (
    <header className="h-11 shrink-0 border-b border-line bg-panel flex items-center px-3 gap-3">
      {/* left: logo + title + LED strip */}
      <div className="flex items-center gap-2.5 min-w-0">
        <Logo />
        <span className="text-tiny font-bold tracking-[0.26em] text-lit whitespace-nowrap">
          CINEMATIC CONSOLE LD
        </span>
        <span className="hidden xl:flex items-center gap-[5px] ml-1">
          {LED_COLORS.map((c, i) => (
            <span
              key={i}
              className="w-[5px] h-[5px] rounded-full"
              style={{ background: c, boxShadow: `0 0 4px ${c}` }}
            />
          ))}
        </span>
      </div>

      {/* middle: save + capsules */}
      <div className="flex-1 flex items-center justify-center gap-2 min-w-0">
        <GhostButton onClick={() => s.saveAll()} title="保存全部参数到后端">
          保存 SAVE
        </GhostButton>
        <span className="text-nano text-dim tracking-widest whitespace-nowrap tabular-nums">
          {words} words
        </span>
        <div className="hidden lg:flex items-center gap-1.5">
          <Capsule k="FPS" v={String(s.fps)} />
          <Capsule k="LEN" v={`${s.duration}s`} />
          <Capsule k="FRM" v={String(frames)} />
          <Capsule k="RES" v={`${res.width}×${res.height}`} />
          <Capsule k="SEED" v={s.seed ? s.seed.slice(0, 6) + "…" : "rand"} />
        </div>
      </div>

      {/* right: status lights + settings */}
      <div className="flex items-center gap-1">
        <StatusDot state={llmState} label="LLM" onClick={() => s.reconnectLlm()} />
        <StatusDot state={renderState} label="RENDER" onClick={() => s.reconnectRender()} />
        <button
          type="button"
          title="设置"
          onClick={() => s.set({ showSettings: true })}
          className="ml-1 p-1.5 text-dim hover:text-lit border border-transparent hover:border-line rounded-sm transition-colors"
        >
          <IconGear />
        </button>
      </div>
    </header>
  );
}
