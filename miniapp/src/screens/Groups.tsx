import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchGroups, createGroup } from "../lib/api";
import { getWeekdayNameUz, type GroupItem, type CreateGroupPayload } from "../lib/types";
import GroupModal from "../components/GroupModal";
import GroupDetailModal from "../components/GroupDetailModal";

export default function Groups() {
  const queryClient = useQueryClient();
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [selectedGroup, setSelectedGroup] = useState<GroupItem | null>(null);
  const [showInactive, setShowInactive] = useState(false);

  const { data: groups, isPending, isError, refetch } = useQuery({
    queryKey: ["groups", showInactive],
    queryFn: () => fetchGroups(showInactive),
  });

  const createGroupMutation = useMutation({
    mutationFn: (payload: CreateGroupPayload) => createGroup(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["groups"] });
    },
  });

  const groupList = Array.isArray(groups) ? groups : [];
  const totalStudents = groupList.reduce((acc, g) => acc + g.student_count, 0);

  return (
    <div className="min-h-screen p-4 pb-20 space-y-4">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-tg-text">Гуруҳлар</h1>
          <p className="text-xs text-tg-hint">
            Жами: {groupList.length} та гуруҳ • {totalStudents} та фаол ўқувчи
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowCreateModal(true)}
          className="rounded-xl bg-tg-button px-3.5 py-2 text-xs font-semibold text-tg-buttonText shadow-sm transition hover:opacity-90"
        >
          + Янги гуруҳ
        </button>
      </div>

      {/* Filter / Toggle */}
      <div className="flex items-center justify-between pt-1">
        <label className="flex items-center gap-2 text-xs text-tg-hint cursor-pointer">
          <input
            type="checkbox"
            checked={showInactive}
            onChange={(e) => setShowInactive(e.target.checked)}
            className="rounded border-tg-hint/30 text-blue-600 focus:ring-0"
          />
          Архивланганларни кўрсатиш
        </label>
      </div>

      {/* Main Content */}
      {isPending ? (
        <div className="py-12 text-center text-sm text-tg-hint">Гуруҳлар юкланмоқда...</div>
      ) : isError ? (
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-center">
          <p className="text-xs text-red-500">Маълумотларни юклаб бўлмади</p>
          <button
            type="button"
            onClick={() => void refetch()}
            className="mt-2 rounded-lg bg-tg-button px-3 py-1.5 text-xs text-tg-buttonText"
          >
            Қайта уриниш
          </button>
        </div>
      ) : groupList.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-tg-hint/30 p-8 text-center">
          <p className="text-sm font-medium text-tg-text">Ҳозирча гуруҳлар йўқ</p>
          <p className="mt-1 text-xs text-tg-hint">Янги гуруҳ қўшиш учун юқоридаги тугмани босинг</p>
          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="mt-4 rounded-xl bg-tg-button px-4 py-2 text-xs font-medium text-tg-buttonText"
          >
            + Янги гуруҳ яратиш
          </button>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2">
          {groupList.map((group) => (
            <div
              key={group.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelectedGroup(group)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") setSelectedGroup(group);
              }}
              className={`flex cursor-pointer flex-col justify-between rounded-2xl border border-tg-hint/20 bg-tg-secondaryBg p-4 text-left transition hover:border-blue-500/50 hover:shadow-md ${
                group.is_active === 0 ? "opacity-60" : ""
              }`}
            >
              <div>
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-semibold text-tg-text">{group.name}</h3>
                  <span className="rounded-full bg-blue-500/10 px-2.5 py-0.5 text-[11px] font-medium text-blue-500">
                    {getWeekdayNameUz(group.weekday)}
                  </span>
                </div>
                <div className="mt-2 flex items-center gap-3 text-xs text-tg-hint">
                  <span>⏰ {group.start_time || "Вaqt belgilanmagan"}</span>
                  {group.is_active === 0 && (
                    <span className="rounded bg-red-500/10 px-1.5 py-0.5 text-[10px] text-red-500">
                      Архивда
                    </span>
                  )}
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between border-t border-tg-hint/15 pt-3">
                <span className="text-xs font-medium text-tg-text">
                  👥 {group.student_count} та ўқувчи
                </span>
                <span className="text-xs text-blue-500 font-medium">Кўриш →</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Group Modal */}
      {showCreateModal && (
        <GroupModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={async (payload) => {
            await createGroupMutation.mutateAsync(payload as CreateGroupPayload);
          }}
        />
      )}

      {/* Group Detail Modal */}
      {selectedGroup && (
        <GroupDetailModal
          group={selectedGroup}
          onClose={() => setSelectedGroup(null)}
          onGroupUpdated={() => {
            void refetch();
          }}
        />
      )}
    </div>
  );
}
