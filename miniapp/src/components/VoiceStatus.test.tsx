import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import VoiceStatus from "./VoiceStatus";
import * as sse from "../lib/sse";

/** Drive the component's stream by hand: `emit` pushes an event, `close`
 * resolves the promise streamLessonEvents returns, `fail` rejects it. */
function controllableStream() {
  let emit: (e: sse.LessonEvent) => void = () => {};
  let close: () => void = () => {};
  let fail: (err: unknown) => void = () => {};
  const spy = vi
    .spyOn(sse, "streamLessonEvents")
    .mockImplementation((_lessonId, onEvent) => {
      emit = onEvent;
      return new Promise<void>((resolve, reject) => {
        close = resolve;
        fail = reject;
      });
    });
  return {
    spy,
    emit: (e: sse.LessonEvent) => emit(e),
    close: () => close(),
    fail: (err: unknown) => fail(err),
  };
}

describe("VoiceStatus", () => {
  it("shows the spinner while the stream is open", () => {
    controllableStream();
    render(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);
    expect(screen.getByRole("status")).toHaveTextContent("AI қоралама тайёрланмоқда...");
  });

  it("renders nothing and notifies the parent on draft_ready", async () => {
    const stream = controllableStream();
    const onDraftReady = vi.fn();
    render(<VoiceStatus lessonId={7} onDraftReady={onDraftReady} />);

    stream.emit({ event: "draft_ready" });

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(onDraftReady).toHaveBeenCalledTimes(1);
  });

  it("warns and does not notify the parent on a timeout event", async () => {
    const stream = controllableStream();
    const onDraftReady = vi.fn();
    render(<VoiceStatus lessonId={7} onDraftReady={onDraftReady} />);

    stream.emit({ event: "timeout" });

    expect(await screen.findByText("⚠️ AI қоралама келмади — қўлда киритинг")).toBeInTheDocument();
    expect(onDraftReady).not.toHaveBeenCalled();
  });

  it("warns when the stream closes without a draft", async () => {
    const stream = controllableStream();
    render(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);

    stream.close();

    expect(await screen.findByText(/AI қоралама келмади/)).toBeInTheDocument();
  });

  it("warns when the stream request fails outright", async () => {
    const stream = controllableStream();
    render(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);

    stream.fail(new Error("401"));

    expect(await screen.findByText(/AI қоралама келмади/)).toBeInTheDocument();
  });

  it("ignores unknown events and keeps waiting", async () => {
    const stream = controllableStream();
    const onDraftReady = vi.fn();
    render(<VoiceStatus lessonId={7} onDraftReady={onDraftReady} />);

    stream.emit({ event: "keepalive" });

    expect(screen.getByRole("status")).toHaveTextContent("AI қоралама тайёрланмоқда...");
    expect(onDraftReady).not.toHaveBeenCalled();
  });

  it("does not downgrade to the warning after the draft already landed", async () => {
    const stream = controllableStream();
    const onDraftReady = vi.fn();
    render(<VoiceStatus lessonId={7} onDraftReady={onDraftReady} />);

    stream.emit({ event: "draft_ready" });
    await waitFor(() => expect(onDraftReady).toHaveBeenCalled());
    stream.close(); // the server closes the stream right after the event

    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(onDraftReady).toHaveBeenCalledTimes(1);
  });

  it("aborts the stream when unmounted", () => {
    const stream = controllableStream();
    const { unmount } = render(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);

    const signal = stream.spy.mock.calls[0][2];
    expect(signal.aborted).toBe(false);
    unmount();
    expect(signal.aborted).toBe(true);
  });

  it("opens exactly one stream across parent re-renders with a new callback", () => {
    const stream = controllableStream();
    const { rerender } = render(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);
    rerender(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);
    rerender(<VoiceStatus lessonId={7} onDraftReady={vi.fn()} />);
    expect(stream.spy).toHaveBeenCalledTimes(1);
  });

  it("calls the parent's latest callback, not the one from first render", async () => {
    const stream = controllableStream();
    const stale = vi.fn();
    const latest = vi.fn();
    const { rerender } = render(<VoiceStatus lessonId={7} onDraftReady={stale} />);
    rerender(<VoiceStatus lessonId={7} onDraftReady={latest} />);

    stream.emit({ event: "draft_ready" });

    await waitFor(() => expect(latest).toHaveBeenCalledTimes(1));
    expect(stale).not.toHaveBeenCalled();
  });
});
