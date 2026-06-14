import React from "react";

/* ------------------------------------------------ section + labels */

export function SectionTitle({
  label,
  hint,
  right,
  className = "",
}: {
  label: string;
  hint?: string;
  right?: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`flex items-baseline justify-between gap-2 ${className}`}>
      <div className="flex items-baseline gap-2 min-w-0">
        <span className="text-micro font-bold tracking-[0.18em] text-lit uppercase">
          {label}
        </span>
        {hint && (
          <span className="text-nano tracking-wider text-dim truncate">{hint}</span>
        )}
      </div>
      {right}
    </div>
  );
}

export function Panel({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`border border-line bg-panel rounded-sm ${className}`}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------- controls */

export function Select({
  value,
  onChange,
  options,
  className = "",
  title,
}: {
  value: string;
  onChange: (v: string) => void;
  options: string[];
  className?: string;
  title?: string;
}) {
  const opts = options.includes(value) || !value ? options : [value, ...options];
  return (
    <select
      title={title || value}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full bg-panel2 border border-line rounded-sm px-2 py-[5px] text-tiny text-lit
        outline-none focus:border-line2 hover:border-line2 truncate pr-6 ${className}`}
    >
      {!value && <option value="">— select —</option>}
      {opts.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

export function Slider({
  label,
  value,
  min,
  max,
  step = 1,
  onChange,
  fmt,
  dim = false,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  fmt?: (v: number) => string;
  dim?: boolean;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="space-y-[2px]">
      <div className="flex justify-between items-baseline">
        <span
          className={`text-nano tracking-[0.14em] uppercase ${
            dim ? "text-dim" : "text-fog"
          }`}
        >
          {label}
        </span>
        <span className="text-micro text-acid tabular-nums">
          {fmt ? fmt(value) : value}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        style={{ "--fill": `${pct}%` } as React.CSSProperties}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

export function Switch({
  on,
  onChange,
  label,
}: {
  on: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <button
      onClick={() => onChange(!on)}
      className="flex items-center gap-2 group"
      type="button"
    >
      <span
        className={`relative inline-block w-7 h-[14px] rounded-full border transition-colors ${
          on ? "bg-acid/20 border-acid" : "bg-panel2 border-line"
        }`}
      >
        <span
          className={`absolute top-[1px] w-[10px] h-[10px] rounded-full transition-all ${
            on ? "left-[15px] bg-acid shadow-glow" : "left-[1px] bg-dim"
          }`}
        />
      </span>
      {label && (
        <span
          className={`text-micro tracking-wider ${on ? "text-lit" : "text-dim"}`}
        >
          {label}
        </span>
      )}
    </button>
  );
}

export function PillToggle({
  on,
  onClick,
  children,
  tone = "acid",
}: {
  on: boolean;
  onClick: () => void;
  children: React.ReactNode;
  tone?: "acid" | "amber";
}) {
  const toneCls =
    tone === "amber"
      ? "border-amber text-amber bg-amber/10 shadow-[0_0_10px_rgba(245,197,66,0.25)]"
      : "border-acid text-acid bg-acid/10 shadow-glow";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-2.5 py-[5px] rounded-sm border text-nano font-bold tracking-[0.14em] uppercase
        transition-all ${on ? toneCls : "border-line text-dim bg-panel2 hover:border-line2 hover:text-fog"}`}
    >
      {children}
    </button>
  );
}

export function GhostButton({
  onClick,
  children,
  className = "",
  disabled,
  title,
}: {
  onClick?: () => void;
  children: React.ReactNode;
  className?: string;
  disabled?: boolean;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`px-2.5 py-[5px] border border-line bg-panel2 rounded-sm text-nano font-bold
        tracking-[0.14em] uppercase text-fog hover:text-lit hover:border-line2
        disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${className}`}
    >
      {children}
    </button>
  );
}

/* ----------------------------------------------------------- misc */

export function StatusDot({
  state,
  onClick,
  label,
}: {
  state: "ok" | "warn" | "err";
  onClick?: () => void;
  label: string;
}) {
  const color =
    state === "ok" ? "text-neon" : state === "warn" ? "text-amber" : "text-danger";
  const bg =
    state === "ok" ? "bg-neon" : state === "warn" ? "bg-amber" : "bg-danger";
  return (
    <button
      type="button"
      onClick={onClick}
      title={`${label} — 点击重连`}
      className="flex items-center gap-1.5 px-2 py-1 rounded-sm hover:bg-panel2 transition-colors"
    >
      <span className={`w-2 h-2 rounded-full ${bg} ${color} pulse-dot`} />
      <span className="text-nano font-bold tracking-[0.18em] text-fog">{label}</span>
    </button>
  );
}

export function Capsule({ k, v }: { k: string; v: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 border border-line bg-panel2 rounded-sm px-2 py-[3px]">
      <span className="text-nano tracking-widest text-dim">{k}</span>
      <span className="text-nano font-bold text-acid tabular-nums">{v}</span>
    </span>
  );
}

export function ProgressBar({ pct, tone = "acid" }: { pct: number; tone?: "acid" | "neon" }) {
  return (
    <div className="h-[5px] w-full bg-panel3 rounded-sm overflow-hidden border border-line">
      <div
        className={`h-full transition-all duration-200 ${
          tone === "neon" ? "bg-neon" : "bg-gradient-to-r from-acid to-neon"
        }`}
        style={{ width: `${Math.min(100, Math.max(0, pct))}%` }}
      />
    </div>
  );
}
