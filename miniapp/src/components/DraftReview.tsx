interface Props {
  topic: string;
  homework: string;
  summary: string;
  /** False while `summary` is still exactly what the model wrote. */
  summaryReviewed: boolean;
  disabled?: boolean;
  onTopicChange: (v: string) => void;
  onHomeworkChange: (v: string) => void;
  onSummaryChange: (v: string) => void;
}

const FIELD =
  "w-full rounded border border-tg-hint/30 bg-tg-bg px-3 py-2 text-base text-tg-text " +
  "placeholder:text-tg-hint disabled:opacity-50";

export default function DraftReview({
  topic,
  homework,
  summary,
  summaryReviewed,
  disabled = false,
  onTopicChange,
  onHomeworkChange,
  onSummaryChange,
}: Props) {
  return (
    <div className="mb-4">
      <div className="mb-2">
        <label htmlFor="lesson-topic" className="mb-1 block text-xs text-tg-hint">
          Мавзу
        </label>
        <input
          id="lesson-topic"
          type="text"
          disabled={disabled}
          value={topic}
          maxLength={200}
          onChange={(e) => onTopicChange(e.target.value)}
          placeholder="Дарс мавзуси"
          className={FIELD}
        />
      </div>

      {/* summary_public is the body of every student's message and is written
          straight from model output. It used to be fetched and never rendered,
          so the teacher confirmed text nobody had read. */}
      <div className="mb-2">
        <label htmlFor="lesson-summary" className="mb-1 block text-xs text-tg-hint">
          Умумий хулоса (ўқувчиларга юборилади)
        </label>
        <textarea
          id="lesson-summary"
          rows={3}
          disabled={disabled}
          value={summary}
          maxLength={1500}
          onChange={(e) => onSummaryChange(e.target.value)}
          placeholder="Дарс ҳақида қисқача"
          className={FIELD}
        />
        {!summaryReviewed && summary.trim().length > 0 && (
          <p className="mt-1 text-xs text-orange-600">
            ⚠️ Буни AI ёзган — сақлашдан олдин ўқиб чиқинг.
          </p>
        )}
      </div>

      <div>
        <label htmlFor="lesson-homework" className="mb-1 block text-xs text-tg-hint">
          Уй вазифаси
        </label>
        <input
          id="lesson-homework"
          type="text"
          disabled={disabled}
          value={homework}
          maxLength={400}
          onChange={(e) => onHomeworkChange(e.target.value)}
          placeholder="Уй вазифаси"
          className={FIELD}
        />
      </div>
    </div>
  );
}
