import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

interface SyncStatusState {
  online: boolean;
  syncing: boolean;
  queueDepth: number;
  lastError: string | null;
}

const initialState: SyncStatusState = {
  online: typeof navigator !== "undefined" ? navigator.onLine : true,
  syncing: false,
  queueDepth: 0,
  lastError: null,
};

const syncStatusSlice = createSlice({
  name: "syncStatus",
  initialState,
  reducers: {
    setOnline(state, action: PayloadAction<boolean>) {
      state.online = action.payload;
    },
    setSyncStatus(state, action: PayloadAction<{ syncing: boolean; queueDepth: number; lastError?: string }>) {
      state.syncing = action.payload.syncing;
      state.queueDepth = action.payload.queueDepth;
      state.lastError = action.payload.lastError ?? null;
    },
  },
});

export const { setOnline, setSyncStatus } = syncStatusSlice.actions;
export default syncStatusSlice.reducer;
