"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import {
  ArrowUpRight,
  BookOpenCheck,
  ExternalLink,
  Loader2,
  MessageCircleMore,
  Send,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  FormEvent,
  useEffect,
  useRef,
  useState,
} from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";

import { askService } from "@/services/askService";
import type { AskQuestionResponse } from "@/types/api";

import styles from "./FloatingChatbot.module.css";

const SUGGESTIONS = [
  "Điều kiện xét tốt nghiệp là gì?",
  "Quy định học phí hiện hành?",
  "Thủ tục bảo lưu kết quả học tập?",
];

type Citation = NonNullable<AskQuestionResponse["citations"]>[number];

type ChatTurn =
  | { id: string; role: "user"; text: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      citations: Citation[];
      confidence: number;
      warnings: string[];
    };

function nextTurnId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `turn-${Math.random().toString(36).slice(2)}`;
}

function confidenceLabel(value: number): string {
  if (value >= 0.8) return "Cao";
  if (value >= 0.6) return "Trung bình";
  if (value > 0) return "Thấp";
  return "—";
}

/**
 * Persistent floating chatbot anchored to the bottom-right corner.
 *
 * The widget owns the entire ask surface — greeting, suggested
 * questions, the composer, and the AI response — so users no longer
 * need a dedicated "Hỏi AI" page to chat with PolicyMate. The widget
 * hides itself on `/ask` (and `/login`, `/register`) where it would
 * either duplicate or distract from the surrounding flow.
 */
export function FloatingChatbot() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [pending, setPending] = useState<{ id: string; text: string } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const conversationRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Show the widget everywhere except the dedicated ask / login /
  // register routes where it would either duplicate the surface or
  // pull attention away from auth flows.
  const hidden =
    pathname === "/ask" ||
    pathname === "/login" ||
    pathname === "/register" ||
    pathname === "/logout";

  useEffect(() => {
    if (!open) return;

    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 120);
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setOpen(false);
      requestAnimationFrame(() => launcherRef.current?.focus());
    }
    function handlePointerDown(event: PointerEvent) {
      const target = event.target as Node;
      if (
        panelRef.current?.contains(target) ||
        launcherRef.current?.contains(target)
      ) {
        return;
      }
      setOpen(false);
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("pointerdown", handlePointerDown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("pointerdown", handlePointerDown);
    };
  }, [open]);

  // Auto-scroll the conversation pane to the latest turn whenever a
  // new message arrives or a pending request resolves.
  useEffect(() => {
    if (!open) return;
    const node = conversationRef.current;
    if (!node) return;
    node.scrollTop = node.scrollHeight;
  }, [open, turns.length, pending]);

  if (hidden) return null;

  function closePanel() {
    setOpen(false);
    requestAnimationFrame(() => launcherRef.current?.focus());
  }

  async function submitQuestion(rawText: string) {
    const normalized = rawText.trim();
    if (!normalized || pending) return;
    setError(null);
    const userTurn: ChatTurn = {
      id: nextTurnId(),
      role: "user",
      text: normalized,
    };
    setTurns((prev) => [...prev, userTurn]);
    setPending({ id: nextTurnId(), text: normalized });
    setQuestion("");
    try {
      const res = await askService.ask({ message: normalized });
      const citations = (res.citations ?? []) as Citation[];
      const answerText = (res.answer ?? "").trim();
      const assistantTurn: ChatTurn = {
        id: nextTurnId(),
        role: "assistant",
        text:
          answerText.length > 0
            ? answerText
            : "Mình chưa tìm được câu trả lời phù hợp. Bạn thử diễn đạt khác nhé.",
        citations,
        confidence: confidenceToNumber(res.confidence),
        warnings: res.warnings ?? [],
      };
      setTurns((prev) => [...prev, assistantTurn]);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Không nhận được phản hồi từ máy chủ.";
      setError(message);
    } finally {
      setPending(null);
    }
  }

  function handleComposerSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitQuestion(question);
  }

  function handleComposerKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitQuestion(question);
    }
  }

  const hasConversation = turns.length > 0 || pending !== null;

  return (
    <div className={styles.root}>
      {open && (
        <section
          ref={panelRef}
          id="policymate-chatbot"
          className={styles.panel}
          role="dialog"
          aria-modal="false"
          aria-labelledby="policymate-chatbot-title"
        >
          <header className={styles.header}>
            <div className={styles.identity}>
              <span className={styles.avatar} aria-hidden="true">
                <Image
                  src="/images/policymate-mascot.jpg"
                  width={44}
                  height={44}
                  alt=""
                  priority
                />
                <span className={styles.onlineDot} />
              </span>
              <span>
                <strong id="policymate-chatbot-title">PolicyMate AI</strong>
                <small>Trợ lý tra cứu quy chế</small>
              </span>
            </div>
            <div className={styles.headerActions}>
              <button
                type="button"
                className={styles.iconButton}
                onClick={() => {
                  setTurns([]);
                  setPending(null);
                  setError(null);
                  setQuestion("");
                }}
                aria-label="Bắt đầu cuộc trò chuyện mới"
                title="Bắt đầu cuộc trò chuyện mới"
              >
                <Sparkles size={18} />
              </button>
              <button
                type="button"
                className={styles.iconButton}
                onClick={closePanel}
                aria-label="Đóng trợ lý"
              >
                <X size={19} />
              </button>
            </div>
          </header>

          <div
            ref={conversationRef}
            className={styles.conversation}
            role="log"
            aria-live="polite"
            aria-label="Cuộc trò chuyện với PolicyMate AI"
          >
            {!hasConversation && (
              <>
                <div className={styles.botRow}>
                  <span className={styles.miniAvatar} aria-hidden="true">
                    <Image
                      src="/images/policymate-mascot.jpg"
                      width={32}
                      height={32}
                      alt=""
                    />
                  </span>
                  <div className={styles.greeting}>
                    <strong>Xin chào! Mình có thể giúp gì cho bạn?</strong>
                    <p>
                      Hỏi về quy chế học vụ, học phí, thi cử hoặc thủ tục
                      sinh viên.
                    </p>
                  </div>
                </div>

                <div className={styles.evidenceBar}>
                  <BookOpenCheck size={17} />
                  <span>
                    <strong>Câu trả lời có căn cứ</strong>
                    <small>Kèm nguồn văn bản để bạn kiểm chứng.</small>
                  </span>
                  <ShieldCheck size={17} />
                </div>

                <div className={styles.suggestions} aria-label="Câu hỏi gợi ý">
                  <span className={styles.suggestionLabel}>Bạn có thể hỏi</span>
                  {SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => void submitQuestion(suggestion)}
                    >
                      <span>{suggestion}</span>
                      <ArrowUpRight size={15} />
                    </button>
                  ))}
                </div>
              </>
            )}

            {hasConversation && (
              <div className={styles.thread}>
                {turns.map((turn) =>
                  turn.role === "user" ? (
                    <div
                      key={turn.id}
                      className={`${styles.messageRow} ${styles.userRow}`}
                    >
                      <div className={styles.userBubble}>{turn.text}</div>
                    </div>
                  ) : (
                    <div key={turn.id} className={styles.messageRow}>
                      <span className={styles.miniAvatar} aria-hidden="true">
                        <Image
                          src="/images/policymate-mascot.jpg"
                          width={28}
                          height={28}
                          alt=""
                        />
                      </span>
                      <div className={styles.botBubble}>
                        <p>{turn.text}</p>
                        <div className={styles.assistantMeta}>
                          <span
                            className={`${styles.confidenceTag} ${
                              turn.confidence >= 0.8
                                ? styles.confidenceHigh
                                : turn.confidence >= 0.6
                                  ? styles.confidenceMedium
                                  : styles.confidenceLow
                            }`.trim()}
                            title="Độ tin cậy của câu trả lời này"
                          >
                            <ShieldCheck size={12} />
                            {confidenceLabel(turn.confidence)}
                          </span>
                          <span className={styles.citationCount}>
                            {turn.citations.length} nguồn
                          </span>
                        </div>
                        {turn.citations.length > 0 && (
                          <ul className={styles.citationList}>
                            {turn.citations.slice(0, 3).map((c, idx) => {
                              const href = buildCitationHref(c.document_id, c.source_url);
                              const label = buildCitationLabel(
                                c.document_number,
                                c.article,
                                c.clause,
                              );
                              return (
                                <li key={`${turn.id}-citation-${idx}`}>
                                  <a
                                    href={href}
                                    rel="noopener noreferrer"
                                  >
                                    <span>{label}</span>
                                    <ExternalLink size={12} />
                                  </a>
                                </li>
                              );
                            })}
                          </ul>
                        )}
                      </div>
                    </div>
                  ),
                )}
                {pending && (
                  <div className={styles.messageRow}>
                    <span className={styles.miniAvatar} aria-hidden="true">
                      <Image
                        src="/images/policymate-mascot.jpg"
                        width={28}
                        height={28}
                        alt=""
                      />
                    </span>
                    <div className={styles.botBubble}>
                      <span className={styles.loadingRow}>
                        <Loader2
                          size={14}
                          className={styles.spinner}
                          aria-hidden="true"
                        />
                        Đang tra cứu
                      </span>
                    </div>
                  </div>
                )}
                {error && (
                  <div className={styles.errorRow} role="alert">
                    <ShieldAlert size={14} />
                    <span>{error}</span>
                    <button
                      type="button"
                      onClick={() => void submitQuestion(pending?.text ?? "")}
                      disabled={!pending}
                    >
                      Thử lại
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          <form className={styles.composer} onSubmit={handleComposerSubmit}>
            <label className="sr-only" htmlFor="floating-chat-question">
              Nhập câu hỏi cho PolicyMate AI
            </label>
            <MessageCircleMore size={18} aria-hidden="true" />
            <textarea
              ref={inputRef}
              id="floating-chat-question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              onKeyDown={handleComposerKeyDown}
              placeholder="Hỏi về quy chế..."
              autoComplete="off"
              rows={1}
              disabled={pending !== null}
            />
            <button
              type="submit"
              disabled={!question.trim() || pending !== null}
              aria-label="Gửi câu hỏi"
            >
              <Send size={17} />
            </button>
          </form>
          <p className={styles.disclaimer}>
            Kết quả AI cần được đối chiếu trước khi áp dụng.
          </p>
        </section>
      )}

      <button
        ref={launcherRef}
        type="button"
        className={`${styles.launcher} ${open ? styles.launcherOpen : ""}`}
        onClick={() => setOpen((current) => !current)}
        aria-expanded={open}
        aria-controls="policymate-chatbot"
        aria-label={open ? "Đóng PolicyMate AI" : "Mở PolicyMate AI"}
      >
        <span className={styles.launcherCopy}>
          <strong>Hỏi PolicyMate</strong>
          <small>Tra cứu nhanh</small>
        </span>
        <span className={styles.launcherAvatar} aria-hidden="true">
          <Image
            src="/images/policymate-mascot.jpg"
            width={47}
            height={47}
            alt=""
            priority
          />
          <span className={styles.launcherDot} />
        </span>
      </button>
    </div>
  );
}

function confidenceToNumber(value: string | number | undefined | null): number {
  if (value === undefined || value === null) return 0;
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  const v = value.toLowerCase();
  if (v === "high") return 0.9;
  if (v === "medium") return 0.7;
  if (v === "low") return 0.4;
  const numeric = Number(v);
  return Number.isFinite(numeric) ? numeric : 0;
}

/**
 * Resolve the URL for a citation chip in the floating chatbot.
 *
 * 2026-09-06 UX update: prefer the canonical document-detail page at
 * ``/documents/{document_id}`` over the library index or an external
 * source URL. This guarantees the chip always deep-links to the
 * specific document the AI just cited.
 */
function buildCitationHref(
  documentId: string | null | undefined,
  sourceUrl: string | null | undefined,
): string {
  if (documentId && documentId.trim()) {
    return `/documents/${documentId}`;
  }
  if (sourceUrl && sourceUrl.trim()) {
    return sourceUrl;
  }
  return "/documents";
}

/**
 * Build the chip label for a citation. Format:
 *   - ``Điều X · Số hiệu văn bản`` when article exists
 *   - ``Số hiệu văn bản`` (only) otherwise
 *
 * The previous design rendered a ``[1]`` style chip — superseded by
 * the by-prose citation model introduced 2026-09-06.
 */
function buildCitationLabel(
  documentNumber: string | null | undefined,
  article: string | null | undefined,
  clause: string | null | undefined,
): string {
  const locatorParts: string[] = [];
  if (article) locatorParts.push(`Điều ${article}`);
  if (clause) locatorParts.push(`Khoản ${clause}`);
  const locator = locatorParts.join(" · ");
  return locator || documentNumber || "Văn bản";
}
