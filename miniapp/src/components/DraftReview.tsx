interface Props {
  topic: string;
  homework: string;
  disabled?: boolean;
  onTopicChange: (v: string) => void;
  onHomeworkChange: (v: string) => void;
}

export default function DraftReview({
  topic,
  homework,
  disabled = false,
  onTopicChange,
  onHomeworkChange,
}: Props) {
  return (
    <div className="mb-4">
      <div className="mb-2">
        <label htmlFor="lesson-topic" className="mb-1 block text-xs text-gray-500">
          Мавзу
        </label>
        <input
          id="lesson-topic"
          type="text"
          disabled={disabled}
          value={topic}
          onChange={(e) => onTopicChange(e.target.value)}
          placeholder="Дарс мавзуси"
          className="w-full rounded border bg-white px-3 py-2 text-sm disabled:opacity-50"
        />
      </div>
      <div>
        <label htmlFor="lesson-homework" className="mb-1 block text-xs text-gray-500">
          Уй вазифаси
        </label>
        <input
          id="lesson-homework"
          type="text"
          disabled={disabled}
          value={homework}
          onChange={(e) => onHomeworkChange(e.target.value)}
          placeholder="Уй вазифаси"
          className="w-full rounded border bg-white px-3 py-2 text-sm disabled:opacity-50"
        />
      </div>
    </div>
  );
}
