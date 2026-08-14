import WebApp from "@twa-dev/sdk";

export const tg = WebApp;

/** The signed launch payload Telegram hands the Mini App, or "" when the page
 * was opened outside Telegram. A function rather than a bare property read so
 * it is one thing to stub in tests, and so App.tsx has a single place to ask. */
export function getInitData(): string {
  return tg.initData ?? "";
}

export function expandApp(): void {
  tg.ready();
  tg.expand();
  // Without these the Telegram chrome above and below the app keeps the
  // client's own colours while the page paints its own, which reads as a
  // half-loaded screen.
  try {
    tg.setHeaderColor("bg_color");
    tg.setBackgroundColor("bg_color");
  } catch {
    /* older clients do not implement these */
  }
}

/** Ask Telegram to confirm before a swipe-down closes the app.
 *
 * Mini Apps close on a gesture and the whole form is in memory, so an
 * accidental swipe with fifteen students marked used to discard all of it with
 * no prompt at all. */
export function setClosingConfirmation(enabled: boolean): void {
  try {
    if (enabled) tg.enableClosingConfirmation();
    else tg.disableClosingConfirmation();
  } catch {
    /* older clients do not implement these */
  }
}

// MainButton.offClick needs the *same* function reference that was passed to
// onClick, so the current handler is tracked here. (The brief's snippet passed
// a fresh `() => {}`, which detaches nothing and leaks a handler per screen.)
let mainButtonHandler: (() => void) | null = null;

export function setMainButton(text: string, onClick: () => void): void {
  if (mainButtonHandler) tg.MainButton.offClick(mainButtonHandler);
  mainButtonHandler = onClick;
  tg.MainButton.setText(text);
  tg.MainButton.onClick(onClick);
  tg.MainButton.show();
}

export function hideMainButton(): void {
  if (mainButtonHandler) {
    tg.MainButton.offClick(mainButtonHandler);
    mainButtonHandler = null;
  }
  tg.MainButton.hideProgress();
  tg.MainButton.hide();
}

export function showMainButtonLoading(): void {
  tg.MainButton.showProgress();
}

export function hideMainButtonLoading(): void {
  tg.MainButton.hideProgress();
}

export function haptic(): void {
  tg.HapticFeedback.impactOccurred("medium");
}
