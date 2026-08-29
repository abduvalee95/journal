import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import Groups from "./Groups";
import type { GroupItem, GroupDetail } from "../lib/types";

const MOCK_GROUPS: GroupItem[] = [
  {
    id: 1,
    name: "Dushanba Elementary",
    weekday: 1,
    start_time: "18:00",
    is_active: 1,
    student_count: 2,
  },
  {
    id: 2,
    name: "Seshanba Pre-Intermediate",
    weekday: 2,
    start_time: "15:00",
    is_active: 1,
    student_count: 0,
  },
];

const MOCK_DETAIL: GroupDetail = {
  id: 1,
  name: "Dushanba Elementary",
  weekday: 1,
  start_time: "18:00",
  is_active: 1,
  students: [
    {
      id: 101,
      full_name: "Aziza Karimova",
      telegram_id: 1234567,
      joined_at: "2026-08-10T10:00:00",
      is_active: 1,
    },
    {
      id: 102,
      full_name: "Bobur Mirzo",
      telegram_id: -1,
      joined_at: "2026-08-11T10:00:00",
      is_active: 1,
    },
  ],
};

function renderGroups() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <Groups />
    </QueryClientProvider>,
  );
  return userEvent.setup();
}

describe("Groups Screen", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, options?: RequestInit) => {
        const method = options?.method ?? "GET";
        const urlStr = String(url);

        if (urlStr.includes("/api/groups/1/students") && method === "POST") {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: 103,
              full_name: "Yangi O'quvchi",
              telegram_id: -2,
              joined_at: "2026-08-12T10:00:00",
              is_active: 1,
            }),
          } as Response;
        }

        if (urlStr.includes("/api/groups/1") && method === "GET") {
          return { ok: true, status: 200, json: async () => MOCK_DETAIL } as Response;
        }

        if (urlStr.includes("/api/groups") && method === "GET") {
          return { ok: true, status: 200, json: async () => MOCK_GROUPS } as Response;
        }

        if (urlStr.includes("/api/groups") && method === "POST") {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: 3,
              name: "Chorshanba Advanced",
              weekday: 3,
              start_time: "19:00",
              is_active: 1,
              student_count: 0,
            }),
          } as Response;
        }

        if (urlStr.includes("/api/students/101") && method === "PATCH") {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              id: 101,
              full_name: "Aziza Karimova Updated",
              telegram_id: 1234567,
              is_active: 1,
            }),
          } as Response;
        }

        if (urlStr.includes("/api/students/101") && method === "DELETE") {
          return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
        }

        if (urlStr.includes("/api/groups/1") && method === "DELETE") {
          return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
        }

        return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
      }),
    );
  });

  it("renders list of groups and summary count", async () => {
    renderGroups();

    expect(await screen.findByText("Dushanba Elementary")).toBeInTheDocument();
    expect(screen.getByText("Seshanba Pre-Intermediate")).toBeInTheDocument();
    expect(screen.getByText("👥 2 та ўқувчи")).toBeInTheDocument();
    expect(screen.getByText("👥 0 та ўқувчи")).toBeInTheDocument();
    expect(screen.getByText(/Жами: 2 та гуруҳ • 2 та фаол ўқувчи/)).toBeInTheDocument();
  });

  it("opens create group modal and creates group", async () => {
    const user = renderGroups();

    await screen.findByText("Dushanba Elementary");
    const createBtn = screen.getByRole("button", { name: "+ Янги гуруҳ" });
    await user.click(createBtn);

    expect(screen.getByRole("heading", { name: "Янги гуруҳ қўшиш" })).toBeInTheDocument();

    const nameInput = screen.getByLabelText("Гуруҳ номи");
    await user.clear(nameInput);
    await user.type(nameInput, "Chorshanba Advanced");

    const submitBtn = screen.getByRole("button", { name: "Яратиш" });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(screen.queryByRole("heading", { name: "Янги гуруҳ қўшиш" })).not.toBeInTheDocument();
    });
  });

  it("opens group detail modal and shows student roster", async () => {
    const user = renderGroups();

    const groupCard = await screen.findByText("Dushanba Elementary");
    await user.click(groupCard);

    expect(await screen.findByText("Aziza Karimova")).toBeInTheDocument();
    expect(screen.getByText("Bobur Mirzo")).toBeInTheDocument();
    expect(screen.getByText("📱 Қўлда киритилган")).toBeInTheDocument();
  });

  it("adds a student to the group in detail modal", async () => {
    const user = renderGroups();

    const groupCard = await screen.findByText("Dushanba Elementary");
    await user.click(groupCard);

    await screen.findByText("Aziza Karimova");

    const addStudentBtn = screen.getByRole("button", { name: "+ Ўқувчи қўшиш" });
    await user.click(addStudentBtn);

    const input = screen.getByLabelText("Ўқувчининг исми ва фамилияси");
    await user.type(input, "Yangi O'quvchi");

    const saveBtn = screen.getByRole("button", { name: "Қўшиш" });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(screen.queryByLabelText("Ўқувчининг исми ва фамилияси")).not.toBeInTheDocument();
    });
  });
});
