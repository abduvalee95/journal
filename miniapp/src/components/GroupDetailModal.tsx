import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchGroupDetail,
  addStudentToGroup,
  updateStudent,
  deleteStudent,
  deleteGroup,
  updateGroup,
} from "../lib/api";
import { getWeekdayNameUz, type GroupItem, type GroupStudent } from "../lib/types";
import GroupModal from "./GroupModal";

interface GroupDetailModalProps {
  group: GroupItem;
  onClose: () => void;
  onGroupUpdated: () => void;
}

export default function GroupDetailModal({
  group,
  onClose,
  onGroupUpdated,
}: GroupDetailModalProps) {
  const queryClient = useQueryClient();
  const [isEditingGroup, setIsEditingGroup] = useState(false);
  const [newStudentName, setNewStudentName] = useState("");
  const [addingStudent, setAddingStudent] = useState(false);
  const [editingStudentId, setEditingStudentId] = useState<number | null>(null);
  const [editingStudentName, setEditingStudentName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: detail, isPending, refetch } = useQuery({
    queryKey: ["group-detail", group.id],
    queryFn: () => fetchGroupDetail(group.id),
  });

  const addStudentMutation = useMutation({
    mutationFn: (name: string) => addStudentToGroup(group.id, { full_name: name }),
    onSuccess: () => {
      setNewStudentName("");
      setAddingStudent(false);
      void refetch();
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
      onGroupUpdated();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ўқувчи қўшишда хатолик");
    },
  });

  const updateStudentMutation = useMutation({
    mutationFn: ({ id, name }: { id: number; name: string }) =>
      updateStudent(id, { full_name: name }),
    onSuccess: () => {
      setEditingStudentId(null);
      void refetch();
      onGroupUpdated();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ўқувчини ўзгартиришда хатолик");
    },
  });

  const removeStudentMutation = useMutation({
    mutationFn: (id: number) => deleteStudent(id),
    onSuccess: () => {
      void refetch();
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
      onGroupUpdated();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Ўқувчини чиқаришда хатолик");
    },
  });

  const archiveGroupMutation = useMutation({
    mutationFn: () => deleteGroup(group.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
      onGroupUpdated();
      onClose();
    },
    onError: (err: unknown) => {
      setError(err instanceof Error ? err.message : "Гуруҳни архивга олишда хатолик");
    },
  });

  const handleAddStudent = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newStudentName.trim()) return;
    setError(null);
    addStudentMutation.mutate(newStudentName.trim());
  };

  const handleSaveStudentName = (studentId: number) => {
    if (!editingStudentName.trim()) return;
    setError(null);
    updateStudentMutation.mutate({ id: studentId, name: editingStudentName.trim() });
  };

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="group-detail-title"
    >
      <div className="flex max-h-[90vh] w-full max-w-md flex-col rounded-2xl bg-tg-bg shadow-xl border border-tg-hint/20 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-tg-hint/20 p-4">
          <div>
            <h2 id="group-detail-title" className="text-base font-bold text-tg-text">
              {group.name}
            </h2>
            <p className="text-xs text-tg-hint">
              📅 {getWeekdayNameUz(group.weekday)} • ⏰ {group.start_time || "—"}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Ёпиш"
            className="rounded-full p-2 text-tg-hint hover:bg-tg-secondaryBg"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {error && (
            <div className="rounded-lg bg-red-500/10 p-3 text-xs text-red-500">
              {error}
            </div>
          )}

          {/* Group Action Buttons */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setIsEditingGroup(true)}
              className="flex-1 rounded-xl border border-blue-500/30 bg-blue-500/10 py-2 text-xs font-medium text-blue-500 hover:bg-blue-500/20"
            >
              ✏️ Гуруҳни таҳрирлаш
            </button>
            <button
              type="button"
              onClick={() => {
                if (window.confirm("Гуруҳни архивга олишни хоҳлайсизми?")) {
                  archiveGroupMutation.mutate();
                }
              }}
              disabled={archiveGroupMutation.isPending}
              className="rounded-xl border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs font-medium text-red-500 hover:bg-red-500/20 disabled:opacity-50"
            >
              🗑️ Архивга олиш
            </button>
          </div>

          {/* Student List Section */}
          <div>
            <div className="flex items-center justify-between pb-2">
              <h3 className="text-sm font-semibold text-tg-text">
                Ўқувчилар ({detail?.students?.filter((s) => s.is_active === 1).length ?? 0})
              </h3>
              {!addingStudent && (
                <button
                  type="button"
                  onClick={() => setAddingStudent(true)}
                  className="text-xs font-medium text-blue-500 hover:underline"
                >
                  + Ўқувчи қўшиш
                </button>
              )}
            </div>

            {/* Add Student Form */}
            {addingStudent && (
              <form onSubmit={handleAddStudent} className="mb-3 rounded-xl bg-tg-secondaryBg p-3 border border-tg-hint/20">
                <label htmlFor="new-student-input" className="block text-xs font-medium text-tg-hint mb-1">
                  Ўқувчининг исми ва фамилияси
                </label>
                <input
                  id="new-student-input"
                  type="text"
                  required
                  autoFocus
                  placeholder="Масалан: Алишер Навоий"
                  value={newStudentName}
                  onChange={(e) => setNewStudentName(e.target.value)}
                  className="w-full rounded-lg border border-tg-hint/30 bg-tg-bg px-3 py-2 text-sm text-tg-text focus:border-blue-500 focus:outline-none"
                />
                <div className="mt-2 flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => {
                      setAddingStudent(false);
                      setNewStudentName("");
                    }}
                    className="rounded-lg px-3 py-1.5 text-xs text-tg-hint hover:bg-tg-bg"
                  >
                    Бекор қилиш
                  </button>
                  <button
                    type="submit"
                    disabled={addStudentMutation.isPending}
                    className="rounded-lg bg-tg-button px-3 py-1.5 text-xs font-medium text-tg-buttonText disabled:opacity-50"
                  >
                    {addStudentMutation.isPending ? "Қўшилмоқда..." : "Қўшиш"}
                  </button>
                </div>
              </form>
            )}

            {/* Student List */}
            {isPending ? (
              <div className="py-6 text-center text-xs text-tg-hint">Юкланмоқда...</div>
            ) : !detail?.students || detail.students.length === 0 ? (
              <div className="rounded-xl border border-dashed border-tg-hint/30 p-4 text-center text-xs text-tg-hint">
                Ҳозирча ўқувчилар йўқ
              </div>
            ) : (
              <div className="space-y-2">
                {detail.students.map((student: GroupStudent) => (
                  <div
                    key={student.id}
                    className={`flex items-center justify-between rounded-xl border border-tg-hint/15 bg-tg-secondaryBg p-3 ${
                      student.is_active === 0 ? "opacity-50" : ""
                    }`}
                  >
                    {editingStudentId === student.id ? (
                      <div className="flex-1 flex gap-2 items-center">
                        <input
                          type="text"
                          value={editingStudentName}
                          onChange={(e) => setEditingStudentName(e.target.value)}
                          className="flex-1 rounded-lg border border-blue-500 bg-tg-bg px-2 py-1 text-sm text-tg-text"
                          autoFocus
                        />
                        <button
                          type="button"
                          onClick={() => handleSaveStudentName(student.id)}
                          className="rounded-lg bg-blue-500 px-2 py-1 text-xs text-white"
                        >
                          ✓
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingStudentId(null)}
                          className="rounded-lg px-2 py-1 text-xs text-tg-hint"
                        >
                          ✕
                        </button>
                      </div>
                    ) : (
                      <>
                        <div>
                          <p className="text-sm font-medium text-tg-text">{student.full_name}</p>
                          <p className="text-[11px] text-tg-hint">
                            {student.telegram_id < 0 ? "📱 Қўлда киритилган" : `🆔 ${student.telegram_id}`}
                            {student.is_active === 0 && " • (Архивланган)"}
                          </p>
                        </div>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            onClick={() => {
                              setEditingStudentId(student.id);
                              setEditingStudentName(student.full_name);
                            }}
                            aria-label={`${student.full_name}ни таҳрирлаш`}
                            className="rounded-lg p-1.5 text-tg-hint hover:bg-tg-bg"
                          >
                            ✏️
                          </button>
                          {student.is_active === 1 && (
                            <button
                              type="button"
                              onClick={() => {
                                if (window.confirm(`${student.full_name}ни гуруҳдан чиқаришни хоҳлайсизми?`)) {
                                  removeStudentMutation.mutate(student.id);
                                }
                              }}
                              aria-label={`${student.full_name}ни чиқариш`}
                              className="rounded-lg p-1.5 text-red-500 hover:bg-tg-bg"
                            >
                              ✕
                            </button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Edit Group Modal */}
      {isEditingGroup && (
        <GroupModal
          initialGroup={group}
          onClose={() => setIsEditingGroup(false)}
          onSubmit={async (payload) => {
            await updateGroup(group.id, payload);
            void refetch();
            void queryClient.invalidateQueries({ queryKey: ["groups"] });
            onGroupUpdated();
          }}
        />
      )}
    </div>
  );
}
