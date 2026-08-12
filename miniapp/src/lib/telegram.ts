import WebApp from "@twa-dev/sdk";

export const tg = WebApp;

export function expandApp(): void {
  tg.ready();
  tg.expand();
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
