import React, { useEffect, useState } from "react";
import { api } from "../lib/api";
import { useStore } from "../store";
import { HistoryItem } from "../types";
import { GhostButton } from "./ui";
import { IconReuse, IconTrash, IconX } from "./icons";

function fmtDate(ts: number): string {
  const d = new Date(ts * 1000);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function HistoryModal() {
  const show = useStore((s) => s.showHistory);
  const set = useStore((s) => s.set);
  const toast = useStore((s) => s.toast);
  const applySnapshot = useStore((s) => s.applySnapshot);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [sel, setSel] = useState<HistoryItem | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!show) return;
    setLoading(true);
    api
      .history()
      .then((r) => setItems(r.items as HistoryItem[]))
      .catch((e) => toast(`历史加载失败：${e.message}`, "err"))
      .finally(() => setLoading(false));
  }, [show, toast]);

  if (!show) return null;

  const close = () => {
    setSel(null);
    set({ showHistory: false });
  };

  const del = async (id: string) => {
    try {
      await api.deleteHistory(id);
      setItems((xs) => xs.filter((x) => x.id !== id));
      if (sel?.id === id) setSel(null);
      toast("已删除", "ok");
    } catch (e: any) {
      toast(e.message, "err");
    }
  };

  const reuse = (it: HistoryItem) => {
    if (it.params && Object.keys(it.params).length) {
      applySnapshot(it.params);
      toast("已复用该任务的全部参数", "ok");
      close();
    } else {
      toast("该记录没有参数快照", "warn");
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-ink/80 backdrop-blur-sm flex items-center justify-center p-6" onClick={close}>
      <div
        className="w-[960px] max-w-full max-h-[85vh] bg-panel border border-line2 rounded-sm flex flex-col shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-line">
          <span className="text-micro font-bold tracking-[0.2em] text-lit uppercase">
            Render History
          </span>
          <button type="button" onClick={close} className="text-dim hover:text-lit p-1">
            <IconX />
          </button>
        </div>

        <div className="flex-1 min-h-0 flex">
          {/* grid */}
          <div className="flex-1 overflow-y-auto p-3">
            {loading && <div className="text-micro text-dim p-4">loading…</div>}
            {!loading && !items.length && (
              <div className="text-micro text-dim p-6 text-center">
                还没有渲染记录 — 回去点 RENDER 吧。
              </div>
            )}
            <div className="grid grid-cols-3 xl:grid-cols-4 gap-2">
              {items.map((it) => (
                <button
                  type="button"
                  key={it.id}
                  onClick={() => setSel(it)}
                  className={`text-left border rounded-sm overflow-hidden transition-colors ${
                    sel?.id === it.id
                      ? "border-acid/70"
                      : "border-line hover:border-line2"
                  }`}
                >
                  <div className="aspect-video bg-ink/70 relative">
                    {it.thumb_url ? (
                      <img src={it.thumb_url} alt="" className="w-full h-full object-cover" />
                    ) : (
                      <div className="absolute inset-0 flex items-center justify-center text-dim/60 text-nano tracking-widest">
                        {it.status === "error" ? "ERROR" : "NO THUMB"}
                      </div>
                    )}
                    <span className="absolute left-1 top-1 text-nano font-bold bg-ink/80 text-acid px-1 rounded-sm uppercase">
                      {it.mode}
                    </span>
                  </div>
                  <div className="p-1.5">
                    <div className="text-nano text-fog tabular-nums">{fmtDate(it.created_at)}</div>
                    <div className="text-nano text-dim tabular-nums">
                      {it.meta?.width}×{it.meta?.height} · {it.meta?.duration}s · seed{" "}
                      {String(it.meta?.seed || "—").slice(0, 8)}
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* detail */}
          {sel && (
            <div className="w-[340px] shrink-0 border-l border-line overflow-y-auto p-3 space-y-2.5">
              <div className="aspect-video bg-black border border-line rounded-sm overflow-hidden">
                {sel.video_url && sel.status === "done" ? (
                  <video key={sel.video_url} src={sel.video_url} controls className="w-full h-full" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-nano text-dim">
                    {sel.status === "error" ? sel.error || "render error" : "no video"}
                  </div>
                )}
              </div>
              <div className="text-nano text-dim tabular-nums leading-4">
                job {sel.id} · {sel.mode.toUpperCase()} · {fmtDate(sel.created_at)}
                <br />
                {sel.meta?.width}×{sel.meta?.height} · {sel.meta?.frames}f @{sel.meta?.fps}fps ·
                seed {sel.meta?.seed}
              </div>
              <div className="flex gap-1.5">
                <GhostButton onClick={() => reuse(sel)} className="flex-1">
                  <span className="inline-flex items-center gap-1"><IconReuse size={10} /> reuse params</span>
                </GhostButton>
                {sel.video_url && (
                  <a
                    href={sel.video_url}
                    download
                    className="px-2.5 py-[5px] border border-line bg-panel2 rounded-sm text-nano font-bold tracking-[0.14em] uppercase text-fog hover:text-lit hover:border-line2"
                  >
                    save
                  </a>
                )}
                <GhostButton onClick={() => del(sel.id)} className="text-danger">
                  <IconTrash size={10} />
                </GhostButton>
              </div>
              <div className="border border-line bg-ink/60 rounded-sm p-2 text-[10px] leading-[1.65] text-fog whitespace-pre-wrap max-h-72 overflow-y-auto">
                {sel.prompt || "(no prompt snapshot)"}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
