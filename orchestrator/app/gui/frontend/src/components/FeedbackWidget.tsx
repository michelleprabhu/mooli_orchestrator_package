import React, { useEffect, useMemo, useState } from "react";

/**
 * FeedbackWidget — 3x Human & 3x LLM Judge (Fixed Metrics)
 * ------------------------------------------------------------
 * Metrics are HARD-CODED and READ-ONLY for labels:
 *   1) Answer Correctness
 *   2) Answer Relevance
 *   3) Hallucination
 *
 * Human tab: Metric + Rating (out of 5). No notes, labels not editable.
 * LLM tab: Read-only; ratings + notes are fetched from your Evaluation API.
 *
 * Props:
 *  - conversationId?: string
 *  - messageId?: string
 *  - onSubmit?: (payload: FeedbackPayload) => Promise<void> | void
 *  - onAutoJudge?: () => Promise<FeedbackItem[]>  // optional fetch override
 *  - llmSourceLabel?: string  // badge text for data source
 */

export type FeedbackItem = {
  label: string;      // fixed metric name
  rating: number;     // 1..5
  note: string;       // note/comment (LLM only)
};

export type FeedbackPayload = {
  conversationId?: string;
  messageId?: string;
  human: FeedbackItem[]; // length 3
  llm: FeedbackItem[];   // length 3
  timestamp: string;     // ISO8601
  client: { ua: string; width: number; height: number };
};

const FIXED_METRICS = [
  "Answer Correctness",
  "Answer Relevance",
  "Hallucination",
] as const;

type FixedMetric = typeof FIXED_METRICS[number];

function normalizeLabel(s: string) {
  return s.trim().toLowerCase().replace(/[^a-z]/g, "");
}

function coerceToFixedMetrics(items: FeedbackItem[]): FeedbackItem[] {
  // Build a lookup from incoming items by normalized label
  const map = new Map<string, FeedbackItem>();
  for (const it of items) map.set(normalizeLabel(it.label), it);
  const want = [
    normalizeLabel("Answer Correctness"),
    normalizeLabel("Answer Relevance"),
    normalizeLabel("Hallucination"),
  ];
  const fallback: FeedbackItem = { label: "", rating: 3, note: "" };
  return FIXED_METRICS.map((metric, idx) => {
    const found = map.get(want[idx]) ?? fallback;
    return { label: metric, rating: found.rating ?? 3, note: found.note ?? "" };
  });
}

export default function FeedbackWidget({
  conversationId,
  messageId,
  onSubmit,
  onAutoJudge,
  llmSourceLabel,
}: {
  conversationId?: string;
  messageId?: string;
  onSubmit?: (payload: FeedbackPayload) => Promise<void> | void;
  onAutoJudge?: () => Promise<FeedbackItem[]>;
  llmSourceLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"human" | "llm" | "review">("human");

  // Human: FIXED metrics, rating editable, no notes
  const [human, setHuman] = useState<FeedbackItem[]>([
    { label: "Answer Correctness", rating: 3, note: "" },
    { label: "Answer Relevance", rating: 3, note: "" },
    { label: "Hallucination", rating: 3, note: "" },
  ]);

  // LLM: will be READ-ONLY (populated from API, labels coerced to fixed metrics)
  const [llm, setLlm] = useState<FeedbackItem[]>([
    { label: "Answer Correctness", rating: 3, note: "" },
    { label: "Answer Relevance", rating: 3, note: "" },
    { label: "Hallucination", rating: 3, note: "" },
  ]);

  // keyboard shortcut: Alt/Option + F to open/close
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === "f" || e.key === "F")) {
        e.preventDefault();
        setOpen((v) => !v);
      }
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const payload: FeedbackPayload = useMemo(
    () => ({
      conversationId,
      messageId,
      human,
      llm,
      timestamp: new Date().toISOString(),
      client: { ua: navigator.userAgent, width: window.innerWidth, height: window.innerHeight },
    }),
    [conversationId, messageId, human, llm]
  );

  const submit = async () => {
    try {
      if (onSubmit) await onSubmit(payload);
      else
        await fetch("/api/feedback/", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      setActiveTab("review");
    } catch (e) {
      console.error("Feedback submit failed", e);
      alert("Failed to submit feedback.");
    }
  };

  // --- LLM Evaluation Fetching ---
  async function defaultFetchLlmEvaluation(): Promise<FeedbackItem[]> {
    // TODO: Replace with YOUR evaluation API call and return 3 items.
    // See coerceToFixedMetrics() which will enforce fixed labels & order.
    return [
      { label: "Answer Correctness", rating: 3, note: "TODO from API" },
      { label: "Answer Relevance", rating: 3, note: "TODO from API" },
      { label: "Hallucination", rating: 3, note: "TODO from API" },
    ];
  }

  const fetchLlm = async () => {
    try {
      const items = onAutoJudge ? await onAutoJudge() : await defaultFetchLlmEvaluation();
      setLlm(coerceToFixedMetrics(items));
    } catch (e) {
      console.error("LLM evaluation fetch failed", e);
      alert("Failed to fetch LLM evaluation.");
    }
  };

  return (
    <div>
      {/* Floating button */}
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-40 rounded-full bg-orange-600 text-white px-5 py-3 shadow-lg hover:bg-orange-500 focus:outline-none focus:ring-2 focus:ring-orange-400"
        aria-label="Open feedback"
      >
        Feedback
      </button>

      {/* Drawer overlay */}
      {open && (
        <div className="fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/50" onClick={() => setOpen(false)} />
          <aside className="absolute right-0 top-0 h-full w-full sm:w-[520px] bg-zinc-900 text-zinc-100 border-l border-zinc-800 shadow-xl flex flex-col">
            <header className="flex items-center justify-between px-5 py-4 border-b border-zinc-800">
              <div className="flex items-center gap-3">
                <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                <h2 className="text-lg font-semibold">Feedback</h2>
                <span className="text-xs text-zinc-400">3x Human & 3x LLM Judge</span>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-1.5 text-zinc-300 hover:bg-zinc-800"
                aria-label="Close"
              >
                X
              </button>
            </header>

            {/* Tabs */}
            <nav className="px-4 pt-3 flex gap-2">
              {(["human", "llm", "review"] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setActiveTab(t)}
                  className={
                    "px-3 py-1.5 rounded-md text-sm " +
                    (activeTab === t
                      ? "bg-zinc-800 text-white"
                      : "bg-transparent text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/40")
                  }
                >
                  {t === "human" ? "Human" : t === "llm" ? "LLM Judge" : "Review"}
                </button>
              ))}
            </nav>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {activeTab === "human" && (
                <Section title="Human feedback" description="Rate the fixed metrics.">
                  {human.map((item, idx) => (
                    <FeedbackRow
                      key={idx}
                      idx={idx}
                      item={item}
                      noteOnOwnRow
                      ratingLabel="Rating (out of 5)"
                      hideNote
                      readonlyLabel
                      onChange={(next) =>
                        setHuman((arr) => arr.map((x, i) => (i === idx ? { ...x, rating: next.rating } : x)))
                      }
                    />
                  ))}
                </Section>
              )}

              {activeTab === "llm" && (
                <Section
                  title="LLM judge"
                  description="Read-only results fetched from the evaluation API."
                  actionLabel="Fetch from Evaluation API"
                  onAction={fetchLlm}
                >
                  <SourceBadge label={llmSourceLabel ?? "Evaluation API"} />
                  {llm.map((item, idx) => (
                    <ReadonlyFeedbackRow key={idx} idx={idx} item={item} />
                  ))}
                </Section>
              )}

              {activeTab === "review" && (
                <div className="space-y-6">
                  <SummaryCard title="Human" items={human} />
                  <SummaryCard title="LLM Judge" items={llm} />
                  <div className="text-sm text-zinc-400">
                    <p>Conversation: {conversationId ?? "(not set)"} </p>
                    <p>Message: {messageId ?? "(not set)"} </p>
                    <p>Timestamp: {payload.timestamp}</p>
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <footer className="border-t border-zinc-800 px-4 py-3 flex items-center justify-between">
              <div className="text-xs text-zinc-400">Alt/Option + F to toggle • Esc to close</div>
              <div className="flex gap-2">
                <button
                  className="px-4 py-2 rounded-md bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
                  onClick={() => setActiveTab("review")}
                >
                  Review
                </button>
                <button
                  className="px-4 py-2 rounded-md bg-orange-600 text-white hover:bg-orange-500"
                  onClick={submit}
                >
                  Submit
                </button>
              </div>
            </footer>
          </aside>
        </div>
      )}
    </div>
  );
}

function Section({
  title,
  description,
  children,
  actionLabel,
  onAction,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  actionLabel?: string;
  onAction?: () => void;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-base font-medium">{title}</h3>
          {description && <p className="text-sm text-zinc-400">{description}</p>}
        </div>
        {actionLabel && (
          <button
            className="text-xs px-3 py-1.5 rounded-md bg-zinc-800 text-zinc-200 hover:bg-zinc-700"
            onClick={onAction}
          >
            {actionLabel}
          </button>
        )}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

function FeedbackRow({
  idx,
  item,
  onChange,
  noteOnOwnRow,
  ratingLabel,
  hideNote,
  readonlyLabel,
}: {
  idx: number;
  item: FeedbackItem;
  onChange: (next: FeedbackItem) => void;
  noteOnOwnRow?: boolean;
  ratingLabel?: string;
  hideNote?: boolean;
  readonlyLabel?: boolean;
}) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
      {noteOnOwnRow ? (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-center">
            {readonlyLabel ? (
              <div className="text-sm text-zinc-300 sm:col-span-2">
                <span className="block text-xs text-zinc-400">Metric</span>
                <div className="mt-1">{item.label}</div>
              </div>
            ) : (
              <label className="text-sm text-zinc-300 sm:col-span-2">
                <span className="block text-xs text-zinc-400">Metric</span>
                <input
                  className="mt-1 w-full rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-700"
                  placeholder={`Metric ${idx + 1}`}
                  value={item.label}
                  onChange={(e) => onChange({ ...item, label: e.target.value })}
                />
              </label>
            )}

            <label className="text-sm text-zinc-300">
              <span className="block text-xs text-zinc-400">{ratingLabel ?? "Rating"}</span>
              <select
                className="mt-1 w-full rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-700"
                value={item.rating}
                onChange={(e) => onChange({ ...item, rating: Number(e.target.value) })}
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {!hideNote && (
            <div className="mt-3">
              <label className="text-sm text-zinc-300 block">
                <span className="block text-xs text-zinc-400">Note</span>
                <textarea
                  rows={2}
                  className="mt-1 w-full rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-700"
                  placeholder="Short comment"
                  value={item.note}
                  onChange={(e) => onChange({ ...item, note: e.target.value })}
                />
              </label>
            </div>
          )}
        </>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 items-center">
          <label className="text-sm text-zinc-300 sm:col-span-2">
            <span className="block text-xs text-zinc-400">Metric</span>
            <input
              className="mt-1 w-full rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-700"
              placeholder={`Metric ${idx + 1}`}
              value={item.label}
              onChange={(e) => onChange({ ...item, label: e.target.value })}
            />
          </label>

          <label className="text-sm text-zinc-300">
            <span className="block text-xs text-zinc-400">{ratingLabel ?? "Rating"}</span>
            <select
              className="mt-1 w-full rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-700"
              value={item.rating}
              onChange={(e) => onChange({ ...item, rating: Number(e.target.value) })}
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>

          <label className="text-sm text-zinc-300 sm:col-span-2">
            <span className="block text-xs text-zinc-400">Note</span>
            <textarea
              rows={2}
              className="mt-1 w-full rounded-md bg-zinc-900 border border-zinc-800 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-zinc-700"
              placeholder="Short comment"
              value={item.note}
              onChange={(e) => onChange({ ...item, note: e.target.value })}
            />
          </label>
        </div>
      )}
    </div>
  );
}

function SourceBadge({ label }: { label: string }) {
  return (
    <div className="mb-2">
      <span className="inline-flex items-center gap-2 rounded-full bg-zinc-800 border border-zinc-700 px-3 py-1 text-xs text-zinc-300">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        Source: {label}
      </span>
    </div>
  );
}

function ReadonlyFeedbackRow({ idx, item }: { idx: number; item: FeedbackItem }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950 p-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 items-center">
        <div className="text-sm text-zinc-300 sm:col-span-2">
          <span className="block text-xs text-zinc-400">Metric</span>
          <div className="mt-1">{item.label}</div>
        </div>
        <div className="text-sm text-zinc-300">
          <span className="block text-xs text-zinc-400">Rating (out of 5)</span>
          <div className="mt-1 text-zinc-400">{"★".repeat(item.rating)}{"☆".repeat(5 - item.rating)}</div>
        </div>
      </div>
      {item.note && (
        <div className="mt-3 text-sm text-zinc-300">
          <span className="block text-xs text-zinc-400">Note (from API)</span>
          <p className="mt-1 text-zinc-400">{item.note}</p>
        </div>
      )}
    </div>
  );
}

function SummaryCard({ title, items }: { title: string; items: FeedbackItem[] }) {
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-950">
      <div className="px-4 py-3 border-b border-zinc-800 text-sm font-medium">{title}</div>
      <ul className="divide-y divide-zinc-800">
        {items.map((it, i) => (
          <li key={i} className="p-4 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-zinc-200">{it.label}</span>
              <span className="text-zinc-400">{"★".repeat(it.rating)}{"☆".repeat(5 - it.rating)}</span>
            </div>
            {it.note && <p className="mt-1 text-zinc-400">{it.note}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * ------------------------------------------------------------
 * DEV HARNESS / TEST CASES
 * ------------------------------------------------------------
 */
export function FeedbackWidgetDemo() {
  return (
    <div className="p-4">
      <FeedbackWidget
        conversationId="conv-demo"
        messageId="msg-42"
        llmSourceLabel="Demo Eval Stub"
        onAutoJudge={async () => [
          { label: "Answer Correctness", rating: 5, note: "Grounded; matches source." },
          { label: "Answer Relevance", rating: 4, note: "Addressed most of the prompt." },
          { label: "Hallucination", rating: 2, note: "Minor speculative phrasing detected." },
        ]}
        onSubmit={async (p) => {
          console.log("[TEST] Submit payload", p);
          // Assertions: labels are fixed & correct
          const labels = p.human.map((x) => x.label).concat(p.llm.map((x) => x.label));
          const fixed = labels.every((l) => FIXED_METRICS.includes(l as FixedMetric));
          console.assert(fixed, "Labels must be fixed metrics");
          // Rating ranges
          [...p.human, ...p.llm].forEach((x) => {
            console.assert(x.rating >= 1 && x.rating <= 5, "rating range 1..5");
          });
          alert("Submitted — check console for payload.");
        }}
      />
    </div>
  );
}
