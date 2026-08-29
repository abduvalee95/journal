import { describe, expect, it } from "vitest";
import { getWeekdayNameUz, sameAttendance, toStudentRows, type LessonData, type StudentData } from "./types";

const BASE: LessonData = {
  group: { id: 1, name: "Beginners A" },
  lesson: {
    id: 7,
    date: "2026-08-10",
    topic: null,
    homework: null,
    summary_public: null,
    status: "draft",
    summary_reviewed: true,
    has_audio: false,
  },
  students: [
    { id: 1, full_name: "Aziza Karimova" },
    { id: 2, full_name: "Bobur Toshmatov" },
  ],
  attendance: [],
};

describe("toStudentRows", () => {
  it("defaults every student to present with no grade when nothing is saved", () => {
    expect(toStudentRows(BASE)).toEqual([
      {
        id: 1,
        full_name: "Aziza Karimova",
        status: "present",
        grade: null,
        note_public: "",
        att_id: null,
      },
      {
        id: 2,
        full_name: "Bobur Toshmatov",
        status: "present",
        grade: null,
        note_public: "",
        att_id: null,
      },
    ]);
  });

  it("merges existing attendance onto the matching student", () => {
    const rows = toStudentRows({
      ...BASE,
      attendance: [{ id: 55, student_id: 2, status: "late", grade: 3, note_public: "Кечикди" }],
    });
    expect(rows[0]).toMatchObject({ id: 1, status: "present", att_id: null });
    expect(rows[1]).toMatchObject({
      id: 2,
      status: "late",
      grade: 3,
      note_public: "Кечикди",
      att_id: 55,
    });
  });

  it("turns a null note into the empty string the input needs", () => {
    const rows = toStudentRows({
      ...BASE,
      attendance: [{ id: 55, student_id: 1, status: "absent", grade: null, note_public: null }],
    });
    expect(rows[0].note_public).toBe("");
  });

  it("ignores attendance for a student not in the list", () => {
    const rows = toStudentRows({
      ...BASE,
      attendance: [{ id: 99, student_id: 404, status: "present", grade: 5, note_public: null }],
    });
    expect(rows).toHaveLength(2);
    expect(rows.every((r) => r.att_id === null)).toBe(true);
  });

  it("returns an empty list for a group with no students", () => {
    expect(toStudentRows({ ...BASE, students: [] })).toEqual([]);
  });
});

describe("sameAttendance", () => {
  const ROW: StudentData = {
    id: 1,
    full_name: "Aziza Karimova",
    status: "present",
    grade: 4,
    note_public: "Яхши",
    att_id: 55,
  };

  it("is true for an untouched row", () => {
    expect(sameAttendance(ROW, { ...ROW })).toBe(true);
  });

  it("notices a status change", () => {
    expect(sameAttendance(ROW, { ...ROW, status: "late" })).toBe(false);
  });

  it("notices a grade change, including clearing it", () => {
    expect(sameAttendance(ROW, { ...ROW, grade: 5 })).toBe(false);
    expect(sameAttendance(ROW, { ...ROW, grade: null })).toBe(false);
  });

  it("notices a note change", () => {
    expect(sameAttendance(ROW, { ...ROW, note_public: "" })).toBe(false);
  });

  it("ignores fields that are not recorded attendance", () => {
    expect(sameAttendance(ROW, { ...ROW, full_name: "Renamed", att_id: 99 })).toBe(true);
  });
});

describe("getWeekdayNameUz", () => {
  it("returns correct Uzbek Cyrillic weekday names", () => {
    expect(getWeekdayNameUz(1)).toBe("Душанба");
    expect(getWeekdayNameUz(2)).toBe("Сешанба");
    expect(getWeekdayNameUz(3)).toBe("Чоршанба");
    expect(getWeekdayNameUz(4)).toBe("Пайшанба");
    expect(getWeekdayNameUz(5)).toBe("Жума");
    expect(getWeekdayNameUz(6)).toBe("Шанба");
    expect(getWeekdayNameUz(7)).toBe("Якшанба");
    expect(getWeekdayNameUz(99)).toBe("Kun 99");
  });
});
