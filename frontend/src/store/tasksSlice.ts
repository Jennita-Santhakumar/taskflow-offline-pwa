import { createAsyncThunk, createSlice, type PayloadAction } from "@reduxjs/toolkit";
import { getDB, type LocalTask } from "../db";
import { enqueueMutation } from "../sync/syncEngine";

interface TasksState {
  items: LocalTask[];
  loading: boolean;
}

const initialState: TasksState = { items: [], loading: false };

export const loadTasks = createAsyncThunk("tasks/load", async () => {
  const db = await getDB();
  const all = await db.getAll("tasks");
  return all.filter((t) => !t.isDeleted).sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1));
});

export const createTask = createAsyncThunk(
  "tasks/create",
  async (input: { title: string; priority: string; category: string; dueDate: string | null; estimatedMinutes: number | null }) => {
    const db = await getDB();
    const now = new Date().toISOString();
    const task: LocalTask = {
      localId: crypto.randomUUID(),
      serverId: null,
      title: input.title,
      description: null,
      priority: input.priority,
      category: input.category,
      status: "pending",
      dueDate: input.dueDate,
      estimatedMinutes: input.estimatedMinutes,
      completedAt: null,
      isDeleted: false,
      updatedAt: now,
      syncVersion: 0,
      dirty: true,
    };
    await db.put("tasks", task);
    await enqueueMutation("upsert", task.localId);
    return task;
  }
);

export const updateTaskStatus = createAsyncThunk(
  "tasks/updateStatus",
  async ({ localId, status }: { localId: string; status: string }) => {
    const db = await getDB();
    const task = await db.get("tasks", localId);
    if (!task) throw new Error("Task not found locally");
    task.status = status;
    task.updatedAt = new Date().toISOString();
    task.dirty = true;
    if (status === "completed") task.completedAt = task.updatedAt;
    await db.put("tasks", task);
    await enqueueMutation("upsert", localId);
    return task;
  }
);

export const deleteTask = createAsyncThunk("tasks/delete", async (localId: string) => {
  const db = await getDB();
  const task = await db.get("tasks", localId);
  if (task) {
    task.isDeleted = true;
    task.updatedAt = new Date().toISOString();
    task.dirty = true;
    await db.put("tasks", task);
  }
  await enqueueMutation("delete", localId);
  return localId;
});

const tasksSlice = createSlice({
  name: "tasks",
  initialState,
  reducers: {
    setTasks(state, action: PayloadAction<LocalTask[]>) {
      state.items = action.payload;
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(loadTasks.fulfilled, (state, action) => {
        state.items = action.payload;
        state.loading = false;
      })
      .addCase(loadTasks.pending, (state) => {
        state.loading = true;
      })
      .addCase(createTask.fulfilled, (state, action) => {
        state.items.unshift(action.payload);
      })
      .addCase(updateTaskStatus.fulfilled, (state, action) => {
        const idx = state.items.findIndex((t) => t.localId === action.payload.localId);
        if (idx >= 0) state.items[idx] = action.payload;
      })
      .addCase(deleteTask.fulfilled, (state, action) => {
        state.items = state.items.filter((t) => t.localId !== action.payload);
      });
  },
});

export const { setTasks } = tasksSlice.actions;
export default tasksSlice.reducer;
