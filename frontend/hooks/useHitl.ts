import { useState, useEffect, useCallback, useRef } from "react";

type HitlMessage =
  | { type: "hitl_requested"; reason: string; timeout_at: number }
  | { type: "ack"; task_id: string };

interface UseHitlReturn {
  isHitlActive: boolean;
  hitlReason: string | null;
  timeoutAt: number | null;
  sendResponse: (content: string) => void;
}

export function useHitl(taskId: string, token: string | null): UseHitlReturn {
  const [isHitlActive, setIsHitlActive] = useState(false);
  const [hitlReason, setHitlReason] = useState<string | null>(null);
  const [timeoutAt, setTimeoutAt] = useState<number | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;
    const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "";
    const wsUrl = `${apiUrl.replace(/^http/, "ws")}/api/v1/ws/tasks/${taskId}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try {
        const msg: HitlMessage = JSON.parse(evt.data as string);
        if (msg.type === "hitl_requested") {
          setIsHitlActive(true);
          setHitlReason(msg.reason);
          setTimeoutAt(msg.timeout_at);
        } else if (msg.type === "ack") {
          setIsHitlActive(false);
          setHitlReason(null);
          setTimeoutAt(null);
        }
      } catch {
        // ignore malformed messages
      }
    };

    return () => {
      ws.close();
    };
  }, [taskId, token]);

  const sendResponse = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "hitl_response", content }));
    }
  }, []);

  return { isHitlActive, hitlReason, timeoutAt, sendResponse };
}
