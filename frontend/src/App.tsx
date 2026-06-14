import React, { useEffect } from "react";
import { useStore } from "./store";
import { useWebSocket } from "./lib/ws";
import TopBar from "./components/TopBar";
import PipelinePanel from "./components/PipelinePanel";
import DirectorPanel from "./components/DirectorPanel";
import PromptPanel from "./components/PromptPanel";
import RenderBay from "./components/RenderBay";
import HistoryModal from "./components/HistoryModal";
import SettingsModal from "./components/SettingsModal";

function Toasts() {
  const toasts = useStore((s) => s.toasts);
  const dismiss = useStore((s) => s.dismissToast);
  return (
    <div className="fixed bottom-5 left-1/2 -translate-x-1/2 z-[60] space-y-1.5 w-[460px] max-w-[90vw]">
      {toasts.map((t) => (
        <button
          type="button"
          key={t.id}
          onClick={() => dismiss(t.id)}
          className={`w-full text-left px-3 py-2 rounded-sm border text-micro leading-4 shadow-lg backdrop-blur-sm transition-all ${
            t.tone === "err"
              ? "border-danger/60 bg-danger/15 text-danger"
              : t.tone === "warn"
              ? "border-amber/60 bg-amber/10 text-amber"
              : "border-neon/50 bg-neon/10 text-neon"
          }`}
        >
          {t.msg}
        </button>
      ))}
    </div>
  );
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null };
  }
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="h-full flex items-center justify-center p-8">
          <div className="max-w-xl border border-danger/60 bg-danger/10 rounded-sm p-5 space-y-2">
            <div className="text-micro font-bold tracking-[0.2em] text-danger uppercase">
              UI crashed — but we caught it
            </div>
            <div className="text-tiny text-fog break-all">{String(this.state.error)}</div>
            <button
              type="button"
              className="px-3 py-1.5 border border-line rounded-sm text-nano text-fog hover:text-lit"
              onClick={() => location.reload()}
            >
              RELOAD CONSOLE
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  useWebSocket();
  const loadInitial = useStore((s) => s.loadInitial);

  useEffect(() => {
    loadInitial();
  }, [loadInitial]);

  return (
    <ErrorBoundary>
      <div className="h-full flex flex-col bg-ink text-fog overflow-hidden">
        <TopBar />
        <main className="flex-1 min-h-0 grid grid-cols-[252px_300px_minmax(0,1fr)_336px]">
          <section className="border-r border-line bg-panel/60 min-h-0">
            <PipelinePanel />
          </section>
          <section className="border-r border-line bg-panel/40 min-h-0">
            <DirectorPanel />
          </section>
          <section className="min-h-0 bg-ink">
            <PromptPanel />
          </section>
          <section className="border-l border-line bg-panel/60 min-h-0">
            <RenderBay />
          </section>
        </main>
      </div>
      <HistoryModal />
      <SettingsModal />
      <Toasts />
    </ErrorBoundary>
  );
}
