import { configureStore } from "@reduxjs/toolkit";
import authReducer from "./authSlice";
import syncStatusReducer from "./syncStatusSlice";
import tasksReducer from "./tasksSlice";

export const store = configureStore({
  reducer: {
    auth: authReducer,
    tasks: tasksReducer,
    syncStatus: syncStatusReducer,
  },
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
