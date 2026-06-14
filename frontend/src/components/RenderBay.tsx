import React, { useEffect, useRef } from "react";
import { useStore } from "../store";
import { fmtTime } from "../lib/prompt";
import { GhostButton, ProgressBar, SectionTitle } from "./ui";
import {
  IconCamera,
  IconDownload,
  IconFilm,
  IconHistory,
  IconSpark,
  IconStop,
} from "./icons";

function StageCard({
  label,
  active,
  done,
  caption,
  children,
  pct,
  stepText,
  icon,
}: {
  label: string;
  active: boolean;
  done?: boolean;
  caption: string;
  children?: React.ReactNode;
  pct?: number;
  stepText?: string;
  icon: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-nano font-bold tracking-[0.18em] uppercase text-fog">
          <span
            className={`w-[6px] h-[6px] rounded-full ${
              done ? "bg-neon" : active ? "bg-acid pulse-dot" : "bg-line2"
            }`}
          />
          {label}
        </span>
        <span
          className={`text-nano tracking-widest tabular-nums ${
            done ? "text-neon" : active ? "text-acid" : "text-dim"
          }`}
        >
          {stepText || (done ? "DONE" : active ? `${pct ?? 0}%` : "STANDBY")}
        </span>
      </div>
      <div
        className={`relative aspect-video border rounded-sm overflow-hidden bg-ink/70 ${
          active ? "border-acid/50" : done ? "border-neon/40" : "border-line"
        }`}
      >
        {children || (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-dim/70">
            {icon}
            <span className="text-nano tracking-[0.22em]">{caption}</span>
          </div>
        )}
        {active && pct !== undefined && (
          <div className="absolute inset-x-0 bottom-0 p-1">
            <ProgressBar pct={pct} />
          </div>
        )}
      </div>
    </div>
  );
}

function Console() {
  const logs = useStore((s) => s.logs);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);
  return (
    <div
      ref={ref}
      className="h-44 shrink-0 overflow-y-auto bg-ink/80 border border-line rounded-sm p-2 scanlines font-mono"
    >
      {logs.map((l, i) => (
        <div
          key={i}
          className={`text-[10px] leading-[15px] break-words ${
            l.level === "error"
              ? "text-danger"
              : l.level === "warn"
              ? "text-amber"
              : "text-neon/90"
          }`}
        >
          <span className="text-dim/80">[{fmtTime(l.ts)}]</span> {l.msg}
        </div>
      ))}
      {!logs.length && (
        <div className="text-[10px] text-dim/60">控制台空闲 — 等待后端事件…</div>
      )}
    </div>
  );
}

export default function RenderBay() {
  const s = useStore();
  const job = s.job;
  const phase = job?.phase || "";
  const running = job?.status === "running" || job?.status === "queued";

  const pass1Active = running && phase === "pass1";
  const pass1Done =
    (running && (phase === "pass2" || phase === "saving")) || job?.status === "done";
  const pass2Active = running && (phase === "pass2" || phase === "saving");
  const pass2Done = job?.status === "done";
  const previewActive = running && !!s.preview;

  return (
    <div className="h-full flex flex-col px-3 py-3 gap-3 overflow-y-auto">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-micro font-bold tracking-[0.18em] text-lit uppercase">
            Render Bay / 渲染舱
          </div>
          <div className="text-nano text-dim truncate tabular-nums">
            {running
              ? `${job!.status} · job ${job!.id}`
              : job?.status === "done"
              ? `done · job ${job.id}`
              : "空闲 · job —"}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {running && (
            <GhostButton onClick={() => s.cancelJob()} title="中断渲染" className="!px-2 text-danger">
              <IconStop size={10} />
            </GhostButton>
          )}
          <GhostButton onClick={() => s.set({ showHistory: true })} title="历史记录">
            <span className="inline-flex items-center gap-1"><IconHistory size={10} /> 历史</span>
          </GhostButton>
        </div>
      </div>

      <StageCard
        label="Live Preview / 实时预览"
        active={previewActive}
        caption="PREVIEW · 待命"
        icon={<IconCamera />}
      >
        {s.preview && (
          <>
            <img
              src={`data:image/jpeg;base64,${s.preview}`}
              alt="live preview"
              className="absolute inset-0 w-full h-full object-cover"
            />
            <span className="absolute left-1.5 top-1.5 text-nano font-bold bg-ink/80 text-acid px-1.5 py-[2px] rounded-sm tracking-widest uppercase">
              {s.previewPhase || "live"}
            </span>
          </>
        )}
      </StageCard>

      <StageCard
        label="First Pass / 第一遍"
        active={pass1Active}
        done={pass1Done}
        caption="PASS 1 · 待命"
        icon={<IconFilm />}
        pct={pass1Active ? job?.pct : undefined}
        stepText={
          pass1Active && job?.step
            ? `${job.step}/${job.total} · ${job.pct}%`
            : undefined
        }
      >
        {pass1Done && (
          <div className="absolute inset-0 flex items-center justify-center text-neon/80 text-nano tracking-[0.22em]">
            PASS 1 · 完成
          </div>
        )}
      </StageCard>

      <StageCard
        label="Final / 成片"
        active={pass2Active}
        done={pass2Done}
        caption="PASS 2 · 待命"
        icon={<IconSpark />}
        pct={pass2Active ? job?.pct : undefined}
        stepText={
          pass2Active
            ? phase === "saving"
              ? "ENCODING…"
              : job?.step
              ? `${job.step}/${job.total} · ${job.pct}%`
              : undefined
            : undefined
        }
      >
        {pass2Done && job?.videoUrl && (
          <>
            <video
              key={job.videoUrl}
              src={job.videoUrl}
              controls
              autoPlay
              loop
              className="absolute inset-0 w-full h-full object-contain bg-black"
            />
            <a
              href={job.videoUrl}
              download
              title="下载成片"
              className="absolute right-1.5 top-1.5 p-1.5 bg-ink/80 border border-line rounded-sm text-acid hover:text-lit hover:border-acid/60 transition-colors"
            >
              <IconDownload size={11} />
            </a>
          </>
        )}
        {job?.status === "error" && (
          <div className="absolute inset-0 flex items-center justify-center p-3 text-center text-danger text-nano leading-4">
            {job.error || "render failed"}
          </div>
        )}
      </StageCard>

      <div className="flex-1 min-h-2" />
      <Console />
    </div>
  );
}
