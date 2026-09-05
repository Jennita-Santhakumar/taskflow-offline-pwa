import { api } from "../api/client";
import { getDB, getMeta, setMeta, type LocalTask, type SyncQueueItem } from "../db";

const DEVICE_ID_KEY = "device_id";
const CURSOR_KEY = "sync_cursor";
const BASE_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const MAX_RETRIES = 3; // matches the PRD's retry_count < 3 -> max-retry flag

export type SyncListener = (status: { syncing: boolean; queueDepth: number; lastError?: string }) => void;

let listeners: SyncListener[] = [];
let syncing = false;
let backoffTimer: ReturnType<typeof setTimeout> | null = null;

export function onSyncStatus(listener: SyncListener) {
  listeners.push(listener);
  return () => {
    listeners = listeners.filter((l) => l !== listener);
  };
}

async function notify(lastError?: string) {
  const db = await getDB();
  const queueDepth = await db.count("sync_queue");
  listeners.forEach((l) => l({ syncing, queueDepth, lastError }));
}

export async function getDeviceId(): Promise<string> {
  let id = await getMeta(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    await setMeta(DEVICE_ID_KEY, id);
  }
  return id;
}

export async function enqueueMutation(op: "upsert" | "delete", localId: string): Promise<void> {
  const db = await getDB();
  const existing = await db.get("sync_queue", localId);
  const item: SyncQueueItem = existing ?? { id: localId, op, retryCount: 0, nextAttemptAt: Date.now() };
  item.op = op; // a later delete supersedes a queued upsert for the same row, and vice versa
  await db.put("sync_queue", item);
  await notify();
  scheduleSync(0);
}

export function backoffDelay(retryCount: number): number {
  return Math.min(BASE_BACKOFF_MS * 2 ** retryCount, MAX_BACKOFF_MS);
}

export function scheduleSync(delayMs = 0) {
  if (backoffTimer) clearTimeout(backoffTimer);
  backoffTimer = setTimeout(() => {
    void runSync();
  }, delayMs);
}

/** Push every queued mutation, then pull anything new since our last cursor, merging with
 * last-write-wins (the server is authoritative for conflicts -- see /sync/push's
 * conflict_resolved_remote_wins outcome -- but this also handles the fully-offline
 * pull-only merge case for updates the server accepted from ANOTHER device). */
export async function runSync(): Promise<void> {
  if (syncing || !navigator.onLine) return;
  syncing = true;
  await notify();

  try {
    const db = await getDB();
    const deviceId = await getDeviceId();
    const queue = await db.getAll("sync_queue");

    if (queue.length > 0) {
      const items = [];
      for (const q of queue) {
        const task = await db.get("tasks", q.id);
        if (!task) continue;
        items.push({
          client_id: task.localId,
          op: q.op,
          id: task.serverId,
          title: task.title,
          description: task.description,
          priority: task.priority,
          category: task.category,
          status: task.status,
          due_date: task.dueDate,
          estimated_minutes: task.estimatedMinutes,
          updated_at: task.updatedAt,
        });
      }

      try {
        const resp = await api.syncPush(deviceId, items);
        for (const result of resp.results) {
          const task = await db.get("tasks", result.client_id);
          if (task) {
            task.serverId = result.server_id;
            task.dirty = false;
            task.syncVersion = result.sync_version;
            await db.put("tasks", task);
          }
          await db.delete("sync_queue", result.client_id);
        }
      } catch (err) {
        // exponential backoff retry, capped at MAX_RETRIES per the PRD's retry_count<3 policy;
        // beyond that we stop auto-retrying and surface the error for a manual retry.
        for (const q of queue) {
          if (q.retryCount + 1 >= MAX_RETRIES) {
            q.retryCount += 1;
            q.lastError = String(err);
            await db.put("sync_queue", q);
          } else {
            q.retryCount += 1;
            q.nextAttemptAt = Date.now() + backoffDelay(q.retryCount);
            await db.put("sync_queue", q);
          }
        }
        scheduleSync(backoffDelay(1));
        await notify(String(err));
        return;
      }
    }

    let since = Number((await getMeta(CURSOR_KEY)) ?? "0");
    let hasMore = true;
    while (hasMore) {
      const pulled = await api.syncPull(deviceId, since);
      for (const t of pulled.tasks) {
        await mergePulledTask(db, t);
      }
      since = pulled.sync_version;
      hasMore = pulled.has_more;
      await setMeta(CURSOR_KEY, String(since));
    }
  } finally {
    syncing = false;
    await notify();
  }
}

export async function mergePulledTask(db: Awaited<ReturnType<typeof getDB>>, remote: any): Promise<void> {
  const existing = await db.get("tasks", remote.id);
  const remoteTask: LocalTask = {
    localId: remote.id,
    serverId: remote.id,
    title: remote.title,
    description: remote.description,
    priority: remote.priority,
    category: remote.category,
    status: remote.status,
    dueDate: remote.due_date,
    estimatedMinutes: remote.estimated_minutes,
    completedAt: remote.completed_at,
    isDeleted: remote.is_deleted,
    updatedAt: remote.updated_at,
    syncVersion: remote.sync_version,
    dirty: false,
  };

  if (!existing) {
    if (!remoteTask.isDeleted) await db.put("tasks", remoteTask);
    return;
  }

  // last-write-wins: only overwrite the local copy if it has no un-pushed local edits, or the
  // remote copy is strictly newer than the local one.
  if (!existing.dirty || new Date(remote.updated_at) >= new Date(existing.updatedAt)) {
    if (remoteTask.isDeleted) {
      await db.delete("tasks", remote.id);
    } else {
      await db.put("tasks", remoteTask);
    }
  }
}

export function setupConnectivityListeners() {
  window.addEventListener("online", () => scheduleSync(0));
  window.addEventListener("offline", () => void notify());
}
