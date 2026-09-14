"use client";

import { useEffect, useState, useCallback, useRef } from "react";

import { notificationService, type Notification } from "@/services/notificationService";

const POLL_INTERVAL_MS = 30_000; // refresh unread count every 30s

/**
 * useNotifications - subscribe to a polling-based unread count + list.
 *
 * - `unreadCount` is auto-refreshed every 30s.
 * - `list()` fetches the full page of notifications.
 * - `markRead` / `markAllRead` mutate state locally for snappy UX.
 *
 * The backend does NOT push events (no websockets yet); polling is the
 * simplest, sufficient solution for a non-realtime notification system.
 */
export function useNotifications() {
  const [unreadCount, setUnreadCount] = useState<number>(0);
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mounted = useRef(true);

  const fetchUnreadCount = useCallback(async () => {
    try {
      const res = await notificationService.unreadCount();
      if (mounted.current) setUnreadCount(res.unread_count);
    } catch {
      // Silent — keep previous value.
    }
  }, []);

  const list = useCallback(
    async (page = 1, unreadOnly = false) => {
      setLoading(true);
      setError(null);
      try {
        const res = await notificationService.list(
          page,
          50,
          unreadOnly,
        );
        if (mounted.current) {
          setItems(res.items);
          setUnreadCount(res.unread_count);
        }
      } catch {
        if (mounted.current) {
          setError("Không thể tải danh sách thông báo.");
        }
      } finally {
        if (mounted.current) setLoading(false);
      }
    },
    [],
  );

  const markRead = useCallback(async (id: string) => {
    try {
      const res = await notificationService.markRead(id);
      setItems((prev) =>
        prev.map((n) =>
          n.id === id ? { ...n, is_read: true } : n,
        ),
      );
      setUnreadCount(res.unread_count);
    } catch {
      // Silent
    }
  }, []);

  const markAllRead = useCallback(async () => {
    try {
      await notificationService.markAllRead();
      setItems((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // Silent
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void fetchUnreadCount();
    const id = setInterval(() => {
      void fetchUnreadCount();
    }, POLL_INTERVAL_MS);
    return () => {
      mounted.current = false;
      clearInterval(id);
    };
  }, [fetchUnreadCount]);

  return {
    unreadCount,
    items,
    loading,
    error,
    list,
    markRead,
    markAllRead,
    refresh: fetchUnreadCount,
  };
}
