import { useEffect, useRef, useState } from "react";

export interface ImageWsMessage {
  entity_id?: string;
  url?: string;
  prompt_hash?: string;
  type?: "progress";
  completed?: number;
  total?: number;
  failed?: number;
}

function wsBase(): string {
  const api = import.meta.env.VITE_API_URL as string | undefined;
  if (api) {
    return api.replace(/^http/, "ws");
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

export function useImageWebSocket(
  templateId: string | null,
  onImage: (msg: ImageWsMessage) => void
) {
  const [connected, setConnected] = useState(false);
  const [progress, setProgress] = useState<{ completed: number; total: number } | null>(
    null
  );
  const onImageRef = useRef(onImage);
  onImageRef.current = onImage;

  useEffect(() => {
    if (!templateId) return;

    const url = `${wsBase()}/ws/images/${encodeURIComponent(templateId)}`;
    const ws = new WebSocket(url);

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onerror = () => setConnected(false);
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data as string) as ImageWsMessage;
        if (msg.type === "progress" && msg.total != null) {
          setProgress({ completed: msg.completed ?? 0, total: msg.total });
          return;
        }
        if (msg.entity_id && msg.url) {
          onImageRef.current(msg);
        }
      } catch {
        /* ignore */
      }
    };

    return () => {
      ws.close();
      setConnected(false);
    };
  }, [templateId]);

  return { connected, progress };
}
