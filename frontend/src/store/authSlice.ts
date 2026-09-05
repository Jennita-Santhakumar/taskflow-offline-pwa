import { createSlice, type PayloadAction } from "@reduxjs/toolkit";

interface AuthState {
  isAuthenticated: boolean;
  email: string | null;
}

const initialState: AuthState = { isAuthenticated: false, email: null };

const authSlice = createSlice({
  name: "auth",
  initialState,
  reducers: {
    loggedIn(state, action: PayloadAction<string>) {
      state.isAuthenticated = true;
      state.email = action.payload;
    },
    loggedOut(state) {
      state.isAuthenticated = false;
      state.email = null;
    },
  },
});

export const { loggedIn, loggedOut } = authSlice.actions;
export default authSlice.reducer;
