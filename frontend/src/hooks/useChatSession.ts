"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  deleteChatSession as apiDeleteChatSession,
  getChatSession as apiGetChatSession,
  listChatSessions as apiListChatSessions,
  sendChatMessage as apiSendChatMessage,
} from "../lib/api";
import type {
  ChatMessage,
  ChatSession,
  ChatSessionWithTurns,
} from "../lib/types";

export interface UseChatSessionResult {
  /** Current session ID. `null` until first sendMessage() creates a session. */
  sessionId: string | null;
  /** Messages displayed in the chat UI (user + assistant). */
  messages: ChatMessage[];
  /** True while a request is in flight. */
  isLoading: boolean;
  /** Error from the last failed request, if any. */
  error: string | null;
  /** Past sessions for this user, loaded via listChatSessions(). */
  sessions: ChatSession[];
  /** Send a user message and append the assistant reply. */
  sendMessage: (content: string) => Promise<void>;
  /** Load a previous session into the UI for browsing. */
  loadSession: (sessionId: string) => Promise<void>;
  /** Start a brand-new conversation (clears current state). */
  startNewSession: () => void;
  /** Delete a session and remove it from the list. */
  deleteSession: (sessionId: string) => Promise<void>;
  /** Reload the session list from the server. */
  refreshSessions: () => Promise<void>;
}

/**
 * useChatSession — manages a continuous chat conversation.
 *
 * Responsibilities:
 *  - Track the active session_id and send it with every request so the
 *    backend can preserve conversation history across turns.
 *  - Persist the messages locally so the UI re-renders on every update.
 *  - Provide session-level operations: list, load, delete, start fresh.
 *
 * Designed for a single chat panel. If you have multiple chat panels,
 * instantiate the hook once per panel — the state is local to the
 * component, not a module-level singleton.
 */
export function useChatSession(): UseChatSessionResult {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<ChatSession[]>([]);

  // Keep a ref to the latest session id so async callbacks always see
  // the freshest value even when fired in quick succession.
  const sessionIdRef = useRef<string | null>(null);
  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await apiListChatSessions();
      setSessions(list);
    } catch (err) {
      // Listing is non-critical; just leave the previous list intact.
      console.error("Failed to load chat sessions:", err);
    }
  }, []);

  const sendMessage = useCallback(async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };

    const loadingMessage: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      timestamp: new Date().toISOString(),
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMessage, loadingMessage]);
    setIsLoading(true);
    setError(null);

    try {
      const response = await apiSendChatMessage(trimmed, sessionIdRef.current);

      // First successful response gives us the session id we should
      // keep sending on subsequent turns.
      const nextSessionId = response.session_id ?? sessionIdRef.current;
      if (response.session_id && response.session_id !== sessionIdRef.current) {
        setSessionId(response.session_id);
        sessionIdRef.current = response.session_id;
      }

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === loadingMessage.id
            ? {
                ...msg,
                content: response.answer,
                citations: response.citations ?? [],
                isLoading: false,
                turn_id: response.turn_id,
                // If the backend omitted session_id but the request
                // already had one, keep it on the message metadata so
                // reload-after-refresh works.
              }
            : msg,
        ),
      );

      // Refresh the session list to reflect the new/updated session.
      if (response.session_id) {
        await refreshSessions();
      }
    } catch (err) {
      const errorMessage =
        err instanceof Error ? err.message : "Đã xảy ra lỗi khi gửi câu hỏi.";
      setError(errorMessage);
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === loadingMessage.id
            ? {
                ...msg,
                content: `Lỗi: ${errorMessage}`,
                isLoading: false,
              }
            : msg,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }, [refreshSessions]);

  const loadSession = useCallback(async (targetSessionId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data: ChatSessionWithTurns = await apiGetChatSession(targetSessionId);
      setSessionId(data.session_id);
      sessionIdRef.current = data.session_id;

      const loadedMessages: ChatMessage[] = [];
      for (const turn of data.turns) {
        loadedMessages.push({
          id: `user-${turn.turn_id}`,
          role: "user",
          content: turn.question,
          timestamp: turn.created_at,
        });
        loadedMessages.push({
          id: `assistant-${turn.turn_id}`,
          role: "assistant",
          content: turn.answer,
          // Citations come back as Record<string, unknown>[]; cast for
          // display. The shape is documented in the chat API contract.
          citations: (turn.citations as never) ?? [],
          timestamp: turn.created_at,
          turn_id: turn.turn_id,
        });
      }
      setMessages(loadedMessages);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Không thể tải cuộc hội thoại.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const startNewSession = useCallback(() => {
    setSessionId(null);
    sessionIdRef.current = null;
    setMessages([]);
    setError(null);
  }, []);

  const deleteSession = useCallback(async (targetSessionId: string) => {
    try {
      await apiDeleteChatSession(targetSessionId);
      setSessions((prev) =>
        prev.filter((s) => s.session_id !== targetSessionId),
      );
      // If we deleted the active session, reset the local state.
      if (sessionIdRef.current === targetSessionId) {
        startNewSession();
      }
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Không thể xóa cuộc hội thoại.";
      setError(message);
      throw err;
    }
  }, [startNewSession]);

  // Initial load of the session list. The hook is mounted lazily inside
  // chat pages, so we don't need to gate this behind a "client only"
  // check — the calling component is already a "use client" boundary.
  useEffect(() => {
    void refreshSessions();
  }, [refreshSessions]);

  return {
    sessionId,
    messages,
    isLoading,
    error,
    sessions,
    sendMessage,
    loadSession,
    startNewSession,
    deleteSession,
    refreshSessions,
  };
}