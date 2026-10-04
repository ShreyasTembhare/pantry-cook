"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { sendChatMessage, type ChatTurn } from "@/lib/api";

export function useChatTurn() {
  const client = useQueryClient();
  const [thinking, setThinking] = useState(false);
  const inflightRef = useRef(0);

  async function send(text: string): Promise<ChatTurn> {
    const ticket = ++inflightRef.current;
    setThinking(true);
    try {
      const turn = await sendChatMessage(text);
      if (ticket !== inflightRef.current) {
        return turn;
      }
      void client.invalidateQueries({ queryKey: ["items"] });
      void client.invalidateQueries({ queryKey: ["meals"] });
      void client.invalidateQueries({ queryKey: ["cook-sessions"] });
      return turn;
    } finally {
      if (ticket === inflightRef.current) {
        setThinking(false);
      }
    }
  }

  return { thinking, send };
}
