import { type DBSchema, type IDBPDatabase, openDB } from "idb";

/** Local task shape mirrors the server's TaskOut but keyed by a stable local `localId`
 * (== server id once synced, or a client-generated uuid before the first successful sync). */
export interface LocalTask {
  localId: string;
  serverId: string | null;
  title: string;
  description: string | null;
  priority: string;
  category: string;
  status: string;
  dueDate: string | null;
  estimatedMinutes: number | null;
  completedAt: string | null;
  isDeleted: boolean;
  updatedAt: string;
  syncVersion: number;
  dirty: boolean; // true if this row has local changes not yet pushed
}

/** One queued mutation, replayed against /sync/push when the app is back online. */
export interface SyncQueueItem {
  id: string; // == localId of the task it mutates
  op: "upsert" | "delete";
  retryCount: number;
  nextAttemptAt: number; // epoch ms, used for exponential backoff scheduling
  lastError?: string;
}

interface TaskDB extends DBSchema {
  tasks: {
    key: string;
    value: LocalTask;
    indexes: { "by-status": string };
  };
  sync_queue: {
    key: string;
    value: SyncQueueItem;
  };
  meta: {
    key: string;
    value: { key: string; value: string };
  };
}

const DB_NAME = "offline-task-manager";
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<TaskDB>> | null = null;

export function getDB(): Promise<IDBPDatabase<TaskDB>> {
  if (!dbPromise) {
    dbPromise = openDB<TaskDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        const taskStore = db.createObjectStore("tasks", { keyPath: "localId" });
        taskStore.createIndex("by-status", "status");
        db.createObjectStore("sync_queue", { keyPath: "id" });
        db.createObjectStore("meta", { keyPath: "key" });
      },
    });
  }
  return dbPromise;
}

export async function getMeta(key: string): Promise<string | null> {
  const db = await getDB();
  const row = await db.get("meta", key);
  return row?.value ?? null;
}

export async function setMeta(key: string, value: string): Promise<void> {
  const db = await getDB();
  await db.put("meta", { key, value });
}

export async function resetDatabase(): Promise<void> {
  const db = await getDB();
  await Promise.all([db.clear("tasks"), db.clear("sync_queue"), db.clear("meta")]);
}
