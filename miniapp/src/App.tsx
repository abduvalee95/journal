import { useEffect, useRef, useState } from "react";
import { getInitData, expandApp } from "./lib/telegram";
import { authenticate, stopTokenRefresh, ApiError } from "./lib/api";
import Today from "./screens/Today";
import Yesterday from "./screens/Yesterday";
import Groups from "./screens/Groups";

type Screen = "today" | "yesterday" | "groups";

const TABS: { id: Screen; label: string }[] = [
  { id: "today", label: "Бугун" },
  { id: "yesterday", label: "Кеча" },
  { id: "groups", label: "Гуруҳлар" },
];

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Declared with the other hooks, above the early returns below: putting this
  // useState after them changes the hook order between the loading and ready
  // renders and makes React throw.
  const [screen, setScreen] = useState<Screen>("today");
  const [attempt, setAttempt] = useState(0);
  // StrictMode runs effects twice in dev; without this the app would POST
  // /api/auth/telegram twice on every load.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    expandApp();

    const initData = getInitData();
    if (!initData) {
      // Opened outside Telegram (a plain browser tab, a preview link). Worth
      // its own message: it used to round-trip to the server and come back as
      // the same generic "could not connect".
      setError("Илова Telegram орқали очилиши керак.");
      return;
    }

    authenticate(initData)
      .then(() => setReady(true))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 403) {
          setError("Кириш рухсат этилмади. Фақат устоз учун.");
        } else if (err instanceof ApiError && err.status === 401) {
          setError("Сессия эскирган. Иловани ёпиб, қайта очинг.");
        } else {
          setError("Серверга уланиб бўлмади. Интернетни текширинг.");
        }
      });
  }, [attempt]);

  useEffect(() => stopTokenRefresh, []);

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-4 p-4 text-center">
        <p className="text-red-500">{error}</p>
        <button
          type="button"
          onClick={() => {
            started.current = false;
            setError(null);
            setAttempt((n) => n + 1);
          }}
          className="min-h-11 rounded-lg bg-tg-button px-4 text-tg-buttonText"
        >
          Қайта уриниш
        </button>
      </div>
    );
  }
  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center text-tg-hint">Юкланмоқда...</div>
    );
  }
  return (
    <div>
      <div className="sticky top-0 z-10 flex border-b border-tg-hint/20 bg-tg-bg" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={`tab-${tab.id}`}
            aria-controls={`panel-${tab.id}`}
            aria-selected={screen === tab.id}
            onClick={() => setScreen(tab.id)}
            className={`min-h-11 flex-1 py-3 text-sm font-medium ${
              screen === tab.id ? "border-b-2 border-blue-500 text-blue-600" : "text-tg-hint"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {/* Each screen owns the Telegram MainButton while mounted, so they are
          swapped rather than hidden: the outgoing screen's effect cleanup
          releases the button before the incoming one claims it. Unsaved work
          survives the unmount through lib/draft.ts. */}
      <div role="tabpanel" id={`panel-${screen}`} aria-labelledby={`tab-${screen}`}>
        {screen === "today" ? <Today /> : screen === "yesterday" ? <Yesterday /> : <Groups />}
      </div>
    </div>
  );
}
