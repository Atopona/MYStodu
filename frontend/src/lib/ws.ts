import { useEffect } from "react";
import { useStore } from "../store";

export function useWebSocket() {
  const applyWsMessage = useStore((s) => s.applyWsMessage);
  const set = useStore((s) => s.set);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    let retry = 0;
    let pingTimer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        retry = 0;
        set({ wsConnected: true });
        pingTimer = window.setInterval(() => {
          try {
            ws?.send("ping");
          } catch {
            /* noop */
          }
        }, 20000);
      };
      ws.onmessage = (ev) => {
        try {
          applyWsMessage(JSON.parse(ev.data));
        } catch {
          /* ignore malformed */
        }
      };
      ws.onclose = () => {
        set({ wsConnected: false });
        if (pingTimer) window.clearInterval(pingTimer);
        if (!closed) {
          retry += 1;
          window.setTimeout(connect, Math.min(8000, 600 * retry));
        }
      };
      ws.onerror = () => ws?.close();
    };

    connect();
    return () => {
      closed = true;
      if (pingTimer) window.clearInterval(pingTimer);
      ws?.close();
    };
  }, [applyWsMessage, set]);
}
