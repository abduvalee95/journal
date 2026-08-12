import { useEffect, useRef, useState } from "react";
import { tg, expandApp } from "./lib/telegram";
import { authenticate, ApiError } from "./lib/api";
import Today from "./screens/Today";

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  return <Today />;
}
