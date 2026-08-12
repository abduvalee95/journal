import { useEffect, useRef, useState } from "react";
import { tg, expandApp } from "./lib/telegram";
import { authenticate, ApiError } from "./lib/api";
import Today from "./screens/Today";
import Yesterday from "./screens/Yesterday";

type Screen = "today" | "yesterday";

const TABS: { id: Screen; label: string }[] = [
  { id: "today", label: "Бугун" },
  { id: "yesterday", label: "Кеча" },
];

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Declared with the other hooks, above the early returns below: the task
  // brief put this useState after them, which changes the hook order between
  // the loading and ready renders and makes React throw.
  const [screen, setScreen] = useState<Screen>("today");
  // StrictMode runs effects twice in dev; without this the app would POST
  // /api/auth/telegram twice on every load.
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;

    expandApp();
    authenticate(tg.initData)
      .then(() => setReady(true))
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 403) {
          setError("Кириш рухсат этилмади. Фақат устоз учун.");
        } else {
          setError("Уланиб бўлмади. Телеграм орқали қайта очинг.");
        }
      });
  }, []);

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-center text-red-500">
        {error}
      </div>
    );
  }
  if (!ready) {
    return (
      <div className="flex h-full items-center justify-center text-gray-400">
        Юкланмоқда...
      </div>
    );
  }
  return (
    <div>
      <div className="sticky top-0 z-10 flex border-b bg-white" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={screen === tab.id}
            onClick={() => setScreen(tab.id)}
            className={`flex-1 py-3 text-sm font-medium ${
              screen === tab.id
                ? "border-b-2 border-blue-500 text-blue-600"
                : "text-gray-500"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {/* Each screen owns the Telegram MainButton while mounted, so they are
          swapped rather than hidden: the outgoing screen's effect cleanup
          releases the button before the incoming one claims it. */}
      {screen === "today" ? <Today /> : <Yesterday />}
    </div>
  );
}
