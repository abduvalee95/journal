import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DraftReview from "./DraftReview";

function setup(props: Partial<React.ComponentProps<typeof DraftReview>> = {}) {
  const onTopicChange = vi.fn();
  const onHomeworkChange = vi.fn();
  const onSummaryChange = vi.fn();
  render(
    <DraftReview
      topic=""
      homework=""
      summary=""
      summaryReviewed
      onTopicChange={onTopicChange}
      onHomeworkChange={onHomeworkChange}
      onSummaryChange={onSummaryChange}
      {...props}
    />,
  );
  return { onTopicChange, onHomeworkChange, onSummaryChange, user: userEvent.setup() };
}

describe("DraftReview", () => {
  it("shows the current topic and homework", () => {
    setup({ topic: "Present Perfect", homework: "Workbook 42-43" });
    expect(screen.getByLabelText("Мавзу")).toHaveValue("Present Perfect");
    expect(screen.getByLabelText("Уй вазифаси")).toHaveValue("Workbook 42-43");
  });

  it("reports topic edits", async () => {
    const { onTopicChange, user } = setup();
    await user.type(screen.getByLabelText("Мавзу"), "M");
    expect(onTopicChange).toHaveBeenCalledWith("M");
  });

  it("reports homework edits", async () => {
    const { onHomeworkChange, user } = setup();
    await user.type(screen.getByLabelText("Уй вазифаси"), "W");
    expect(onHomeworkChange).toHaveBeenCalledWith("W");
  });

  it("disables both fields once the lesson is saved", () => {
    setup({ disabled: true });
    expect(screen.getByLabelText("Мавзу")).toBeDisabled();
    expect(screen.getByLabelText("Уй вазифаси")).toBeDisabled();
  });
});
