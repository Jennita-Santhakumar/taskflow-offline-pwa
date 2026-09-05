import "fake-indexeddb/auto";
import { beforeEach, describe, expect, it } from "vitest";
import { getDB, resetDatabase, type LocalTask } from "../db";
import { backoffDelay, mergePulledTask } from "./syncEngine";

function makeTask(overrides: Partial<LocalTask> = {}): LocalTask {
  return {
    localId: "t1",
    serverId: "t1",
    title: "Original",
    description: null,
    priority: "medium",
    category: "work",
    status: "pending",
    dueDate: null,
    estimatedMinutes: 30,
    completedAt: null,
    isDeleted: false,
    updatedAt: "2026-01-01T00:00:00.000Z",
    syncVersion: 1,
    dirty: false,
    ...overrides,
  };
}

describe("backoffDelay", () => {
  it("grows exponentially with retry count", () => {
    expect(backoffDelay(0)).toBe(1000);
    expect(backoffDelay(1)).toBe(2000);
    expect(backoffDelay(2)).toBe(4000);
  });

  it("caps at 30 seconds", () => {
    expect(backoffDelay(10)).toBe(30000);
  });
});

describe("mergePulledTask (last-write-wins conflict resolution)", () => {
  beforeEach(async () => {
    await resetDatabase();
  });

  it("inserts a brand-new remote task locally", async () => {
    const db = await getDB();
    await mergePulledTask(db, {
      id: "t2",
      title: "From server",
      description: null,
      priority: "high",
      category: "work",
      status: "pending",
      due_date: null,
      estimated_minutes: 15,
      completed_at: null,
      is_deleted: false,
      updated_at: "2026-01-01T00:00:00.000Z",
      sync_version: 1,
    });
    const stored = await db.get("tasks", "t2");
    expect(stored?.title).toBe("From server");
  });

  it("does NOT overwrite a locally-dirty task with an OLDER remote update", async () => {
    const db = await getDB();
    await db.put("tasks", makeTask({ dirty: true, title: "Local edit", updatedAt: "2026-01-02T00:00:00.000Z" }));

    await mergePulledTask(db, {
      id: "t1",
      title: "Stale server copy",
      description: null,
      priority: "medium",
      category: "work",
      status: "pending",
      due_date: null,
      estimated_minutes: 30,
      completed_at: null,
      is_deleted: false,
      updated_at: "2026-01-01T00:00:00.000Z", // older than the local dirty edit
      sync_version: 5,
    });

    const stored = await db.get("tasks", "t1");
    expect(stored?.title).toBe("Local edit");
  });

  it("DOES overwrite a locally-dirty task with a NEWER remote update", async () => {
    const db = await getDB();
    await db.put("tasks", makeTask({ dirty: true, title: "Local edit", updatedAt: "2026-01-01T00:00:00.000Z" }));

    await mergePulledTask(db, {
      id: "t1",
      title: "Newer server copy",
      description: null,
      priority: "medium",
      category: "work",
      status: "pending",
      due_date: null,
      estimated_minutes: 30,
      completed_at: null,
      is_deleted: false,
      updated_at: "2026-01-02T00:00:00.000Z",
      sync_version: 5,
    });

    const stored = await db.get("tasks", "t1");
    expect(stored?.title).toBe("Newer server copy");
  });

  it("removes the local row when the remote marks it deleted", async () => {
    const db = await getDB();
    await db.put("tasks", makeTask());
    await mergePulledTask(db, {
      id: "t1",
      title: "Original",
      description: null,
      priority: "medium",
      category: "work",
      status: "pending",
      due_date: null,
      estimated_minutes: 30,
      completed_at: null,
      is_deleted: true,
      updated_at: "2026-01-02T00:00:00.000Z",
      sync_version: 5,
    });
    const stored = await db.get("tasks", "t1");
    expect(stored).toBeUndefined();
  });
});
