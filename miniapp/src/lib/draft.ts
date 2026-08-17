import type { StudentData } from "./types";

/** Unsaved form state, kept across an unmount.
 *
 * Every piece of the form lives in component-local state, and the tab switch in
 * App.tsx unmounts the outgoing screen -- so marking twelve students, checking
 * yesterday and coming back silently reverted all twelve to the server's rows.
 * The screen looked normal, which is what made it dangerous.
 *
 * sessionStorage rather than localStorage: this is scratch state for one
 * sitting, and it must not outlive the webview.
 */
export interface Draft {
  edits: [number, StudentData][];
  topicEdit: string | null;
  homeworkEdit: string | null;
  summaryEdit: string | null;
}

const KEY_PREFIX = "ustoz-draft:";

function key(lessonId: number): string {
  return `${KEY_PREFIX}${lessonId}`;
}

export function loadDraft(lessonId: number | null | undefined): Draft | null {
  if (lessonId == null) return null;
  try {
    const raw = sessionStorage.getItem(key(lessonId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Draft;
    if (!parsed || !Array.isArray(parsed.edits)) return null;
    return parsed;
  } catch {
    // A quota error, disabled storage or a stale shape must never stop the
    // teacher from entering a lesson.
    return null;
  }
}

export function saveDraft(lessonId: number | null | undefined, draft: Draft): void {
  if (lessonId == null) return;
  try {
    sessionStorage.setItem(key(lessonId), JSON.stringify(draft));
  } catch {
    /* see loadDraft */
  }
}

export function clearDraft(lessonId: number | null | undefined): void {
  if (lessonId == null) return;
  try {
    sessionStorage.removeItem(key(lessonId));
  } catch {
    /* see loadDraft */
  }
}
