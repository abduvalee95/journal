import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

// @twa-dev/sdk reads window.Telegram.WebApp at import time and falls back to a
// stub outside Telegram. Tests import the real ../lib/telegram module and spy
// on it instead of mocking the SDK, so nothing is needed here beyond cleanup.
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
