import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StudentRow from "./StudentRow";
import type { StudentData } from "../lib/types";

const STUDENT: StudentData = {
  id: 1,
  full_name: "Aziza Karimova",
  status: "present",
  grade: null,
  note_public: "",
  att_id: null,
};

function setup(overrides: Partial<StudentData> = {}, props: { disabled?: boolean } = {}) {
  const onChange = vi.fn();
  const student = { ...STUDENT, ...overrides };
  render(<StudentRow student={student} onChange={onChange} {...props} />);
  return { onChange, student, user: userEvent.setup() };
}

describe("StudentRow", () => {
  it("renders the name and marks the current status pressed", () => {
    setup({ status: "late" });
    expect(screen.getByText("Aziza Karimova")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "🕐 Кеч" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "✅ Келди" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("reports a status change", async () => {
    const { onChange, user } = setup();
    await user.click(screen.getByRole("button", { name: "🕐 Кеч" }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ id: 1, status: "late" }));
  });

  it("clears the grade when the student is marked absent", async () => {
    const { onChange, user } = setup({ grade: 4 });
    await user.click(screen.getByRole("button", { name: "❌ Келмади" }));
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ status: "absent", grade: null }),
    );
  });

  it("hides the grade picker for an absent student", () => {
    setup({ status: "absent" });
    expect(screen.queryByRole("button", { name: "5" })).not.toBeInTheDocument();
  });

  it("keeps the grade picker for a late student", () => {
    setup({ status: "late" });
    expect(screen.getByRole("button", { name: "5" })).toBeInTheDocument();
  });

  it("reports the tapped grade", async () => {
    const { onChange, user } = setup();
    await user.click(screen.getByRole("button", { name: "4" }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ grade: 4 }));
  });

  it("clears the grade when the selected one is tapped again", async () => {
    const { onChange, user } = setup({ grade: 4 });
    await user.click(screen.getByRole("button", { name: "4" }));
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ grade: null }));
  });

  it("reports note text as it is typed", async () => {
    const { onChange, user } = setup();
    await user.type(screen.getByLabelText("Aziza Karimova — изоҳ"), "Я");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ note_public: "Я" }));
  });

  it("disables every control once the lesson is saved", () => {
    setup({ status: "present" }, { disabled: true });
    expect(screen.getByRole("button", { name: "✅ Келди" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "3" })).toBeDisabled();
    expect(screen.getByLabelText("Aziza Karimova — изоҳ")).toBeDisabled();
  });
});
