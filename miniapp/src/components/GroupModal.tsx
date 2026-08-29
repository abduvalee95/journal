import { useState } from "react";
import { WEEKDAYS_UZ, type GroupItem, type CreateGroupPayload, type UpdateGroupPayload } from "../lib/types";

interface GroupModalProps {
  initialGroup?: GroupItem | null;
  onClose: () => void;
  onSubmit: (payload: CreateGroupPayload | UpdateGroupPayload) => Promise<void>;
}

export default function GroupModal({ initialGroup, onClose, onSubmit }: GroupModalProps) {
  const [name, setName] = useState(initialGroup?.name ?? "");
  const [weekday, setWeekday] = useState<number>(initialGroup?.weekday ?? 1);
  const [startTime, setStartTime] = useState(initialGroup?.start_time ?? "18:00");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isEditing = Boolean(initialGroup);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setError("Гуруҳ номини киритинг");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (isEditing) {
        await onSubmit({
          name: name.trim(),
          weekday,
          start_time: startTime.trim() || null,
        });
      } else {
        await onSubmit({
          name: name.trim(),
          weekday,
          start_time: startTime.trim() || null,
        });
      }
      onClose();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Хатолик юз берди");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="group-modal-title"
    >
      <div className="w-full max-w-sm rounded-2xl bg-tg-bg p-5 shadow-xl border border-tg-hint/20">
        <h2 id="group-modal-title" className="text-lg font-bold text-tg-text">
          {isEditing ? "Гуруҳни таҳрирлаш" : "Янги гуруҳ қўшиш"}
        </h2>

        {error && (
          <div className="mt-3 rounded-lg bg-red-500/10 p-3 text-xs text-red-500">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          <div>
            <label htmlFor="group-name-input" className="block text-xs font-medium text-tg-hint">
              Гуруҳ номи
            </label>
            <input
              id="group-name-input"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Масалан: Инглиз тили (Elementary)"
              className="mt-1 w-full rounded-xl border border-tg-hint/30 bg-tg-secondaryBg px-3 py-2.5 text-sm text-tg-text focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div>
            <label htmlFor="weekday-select" className="block text-xs font-medium text-tg-hint">
              Дарс куни
            </label>
            <select
              id="weekday-select"
              value={weekday}
              onChange={(e) => setWeekday(Number(e.target.value))}
              className="mt-1 w-full rounded-xl border border-tg-hint/30 bg-tg-secondaryBg px-3 py-2.5 text-sm text-tg-text focus:border-blue-500 focus:outline-none"
            >
              {Object.entries(WEEKDAYS_UZ).map(([num, uzName]) => (
                <option key={num} value={num}>
                  {uzName}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label htmlFor="start-time-input" className="block text-xs font-medium text-tg-hint">
              Бошланиш вақти
            </label>
            <input
              id="start-time-input"
              type="text"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
              placeholder="18:00"
              className="mt-1 w-full rounded-xl border border-tg-hint/30 bg-tg-secondaryBg px-3 py-2.5 text-sm text-tg-text focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="flex-1 rounded-xl border border-tg-hint/30 py-2.5 text-sm font-medium text-tg-hint hover:bg-tg-secondaryBg"
            >
              Бекор қилиш
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex-1 rounded-xl bg-tg-button py-2.5 text-sm font-medium text-tg-buttonText disabled:opacity-50"
            >
              {loading ? "Сақланмоқда..." : isEditing ? "Сақлаш" : "Яратиш"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
