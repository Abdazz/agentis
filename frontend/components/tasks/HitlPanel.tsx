"use client";

import { useState } from "react";
import { useHitl } from "@/hooks/useHitl";
import { useAuthStore } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AlertCircle, Send } from "lucide-react";

interface HitlPanelProps {
  taskId: string;
  /** Optional override; if omitted the panel reads the token from useAuthStore. */
  token?: string | null;
}

export function HitlPanel({ taskId, token: tokenProp }: HitlPanelProps) {
  const storeToken = useAuthStore((s) => s.accessToken);
  const token = tokenProp !== undefined ? tokenProp : storeToken;
  const { isHitlActive, hitlReason, timeoutAt, sendResponse } = useHitl(taskId, token);
  const [message, setMessage] = useState("");

  if (!isHitlActive) return null;

  const secondsLeft = timeoutAt
    ? Math.max(0, Math.round(timeoutAt - Date.now() / 1000))
    : null;

  const handleSend = () => {
    if (!message.trim()) return;
    sendResponse(message.trim());
    setMessage("");
  };

  return (
    <div className="border-t border-yellow-500/30 bg-yellow-500/5 p-4 mt-4 rounded-b-lg">
      <div className="flex items-start gap-3 mb-3">
        <AlertCircle className="text-yellow-400 mt-0.5 shrink-0" size={18} />
        <div>
          <p className="text-yellow-300 font-medium text-sm">Action requires your confirmation</p>
          {hitlReason && (
            <p className="text-muted-foreground text-xs mt-0.5">{hitlReason}</p>
          )}
          {secondsLeft !== null && (
            <p className="text-xs text-muted-foreground mt-0.5">
              Auto-cancel in {Math.floor(secondsLeft / 60)}m {secondsLeft % 60}s
            </p>
          )}
        </div>
      </div>
      <div className="flex gap-2">
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Type your response or instructions..."
          className="resize-none text-sm min-h-[60px]"
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSend();
          }}
        />
        <Button onClick={handleSend} disabled={!message.trim()} className="self-end">
          <Send size={16} />
        </Button>
      </div>
    </div>
  );
}
