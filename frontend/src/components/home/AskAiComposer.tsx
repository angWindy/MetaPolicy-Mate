"use client";

import { Search, ShieldCheck, Sparkles } from "lucide-react";
import { useState, type FormEvent, type KeyboardEvent } from "react";
import styles from "./AskAiComposer.module.css";

export type AskAiComposerProps = { placeholder?: string; value?: string; onValueChange?: (value: string) => void; onSubmit?: (question: string) => void };

export function AskAiComposer({ placeholder = "Hỏi về tín chỉ, học phí, thi cử, học bổng hoặc tốt nghiệp...", value, onValueChange, onSubmit }: AskAiComposerProps) {
  const [internalValue, setInternalValue] = useState("");
  const question = value ?? internalValue;
  const normalized = question.trim();
  const update = (next: string) => { if (value === undefined) setInternalValue(next); onValueChange?.(next); };
  const submit = () => { if (normalized) onSubmit?.(normalized); };
  function handleSubmit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); submit(); }
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } }

  return (
    <form className={styles.composer} onSubmit={handleSubmit}>
      <div className={styles.inputRow}><Sparkles size={19} aria-hidden="true" /><label className="sr-only" htmlFor="home-ai-question">Câu hỏi dành cho PolicyMate AI</label><textarea id="home-ai-question" name="question" rows={1} value={question} placeholder={placeholder} aria-describedby="ask-ai-keyboard-help" onChange={(event) => update(event.target.value)} onKeyDown={handleKeyDown} /><button className={styles.send} type="submit" disabled={!normalized}><Search size={17} aria-hidden="true" />Tra cứu với AI</button></div>
      <div className={styles.footer}>
        <span>Tất cả văn bản được phép truy cập</span><span id="ask-ai-keyboard-help"><ShieldCheck size={14} aria-hidden="true" /> Ưu tiên văn bản còn hiệu lực</span>
      </div>
    </form>
  );
}
