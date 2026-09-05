import { useEffect, useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { api, loadTokens, setTokens, WS_BASE_URL, getAccessToken } from "./api/client";
import { createTask, deleteTask, loadTasks, updateTaskStatus } from "./store/tasksSlice";
import type { AppDispatch, RootState } from "./store";
import { loggedIn, loggedOut } from "./store/authSlice";
import { setOnline, setSyncStatus } from "./store/syncStatusSlice";
import { onSyncStatus, runSync, setupConnectivityListeners } from "./sync/syncEngine";

interface Recommendation {
  task_id: string;
  title: string;
  score: number;
  rank: number;
  reason: string;
}

function LoginForm({ onSuccess }: { onSuccess: (email: string) => void }) {
  const [email, setEmail] = useState("demo@example.com");
  const [password, setPassword] = useState("demo12345");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const resp = mode === "login" ? await api.login(email, password) : await api.register(email, password);
      setTokens(resp.access_token, resp.refresh_token);
      onSuccess(email);
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="card">
      <h2>{mode === "login" ? "Log in" : "Register"}</h2>
      <form onSubmit={submit}>
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="email" required />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="password"
          required
        />
        <button type="submit">{mode === "login" ? "Log in" : "Register"}</button>
        <button type="button" className="secondary" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Need an account?" : "Have an account?"}
        </button>
      </form>
      {error && <p style={{ color: "#f87171" }}>{error}</p>}
      <p style={{ fontSize: 12, color: "#94a3b8" }}>
        Demo account is pre-seeded: demo@example.com / demo12345
      </p>
    </div>
  );
}

function NewTaskForm({ onCreate }: { onCreate: (v: any) => void }) {
  const [title, setTitle] = useState("");
  const [priority, setPriority] = useState("medium");
  const [category, setCategory] = useState("work");

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    onCreate({ title, priority, category, dueDate: null, estimatedMinutes: 30 });
    setTitle("");
  }

  return (
    <form onSubmit={submit}>
      <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New task title" />
      <select value={priority} onChange={(e) => setPriority(e.target.value)}>
        <option value="low">low</option>
        <option value="medium">medium</option>
        <option value="high">high</option>
        <option value="urgent">urgent</option>
      </select>
      <select value={category} onChange={(e) => setCategory(e.target.value)}>
        <option value="work">work</option>
        <option value="personal">personal</option>
        <option value="health">health</option>
        <option value="learning">learning</option>
        <option value="errands">errands</option>
        <option value="general">general</option>
      </select>
      <button type="submit">Add</button>
    </form>
  );
}

export default function App() {
  const dispatch = useDispatch<AppDispatch>();
  const auth = useSelector((s: RootState) => s.auth);
  const tasks = useSelector((s: RootState) => s.tasks.items);
  const syncStatus = useSelector((s: RootState) => s.syncStatus);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);

  useEffect(() => {
    const { accessToken } = loadTokens();
    if (accessToken) {
      api
        .me()
        .then((me) => {
          dispatch(loggedIn(me.email));
        })
        .catch(() => setTokens(null, null));
    }
    setupConnectivityListeners();
    const unsubscribe = onSyncStatus((status) => dispatch(setSyncStatus(status)));
    dispatch(setOnline(navigator.onLine));
    window.addEventListener("online", () => dispatch(setOnline(true)));
    window.addEventListener("offline", () => dispatch(setOnline(false)));
    return unsubscribe;
  }, [dispatch]);

  useEffect(() => {
    if (!auth.isAuthenticated) return;
    void runSync().then(() => dispatch(loadTasks()));
    dispatch(loadTasks());
    void refreshRecommendations();

    let ws: WebSocket | null = null;
    const token = getAccessToken();
    if (token) {
      ws = new WebSocket(`${WS_BASE_URL}/ws?token=${encodeURIComponent(token)}`);
      ws.onmessage = () => {
        void runSync().then(() => dispatch(loadTasks()));
        void refreshRecommendations();
      };
    }
    return () => ws?.close();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.isAuthenticated]);

  async function refreshRecommendations() {
    try {
      const resp = await api.nextTasks();
      setRecommendations(resp.items);
    } catch {
      // offline or not yet synced -- fine, panel just stays empty until reachable
    }
  }

  async function onCreate(v: any) {
    await dispatch(createTask(v));
    void refreshRecommendations();
  }

  async function onComplete(localId: string) {
    await dispatch(updateTaskStatus({ localId, status: "completed" }));
    void refreshRecommendations();
  }

  if (!auth.isAuthenticated) {
    return (
      <div className="app">
        <h1>Offline Task Manager</h1>
        <LoginForm
          onSuccess={(email) => {
            dispatch(loggedIn(email));
          }}
        />
      </div>
    );
  }

  return (
    <div className="app">
      <h1>Offline Task Manager</h1>
      {!syncStatus.online && <div className="banner offline">Offline — edits are queued locally and will sync automatically.</div>}
      {syncStatus.online && syncStatus.syncing && <div className="banner syncing">Syncing…</div>}
      {syncStatus.online && !syncStatus.syncing && syncStatus.queueDepth > 0 && (
        <div className="banner queued">{syncStatus.queueDepth} change(s) queued for sync.</div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span>Signed in as {auth.email}</span>
        <button
          className="secondary"
          onClick={() => {
            setTokens(null, null);
            dispatch(loggedOut());
          }}
        >
          Log out
        </button>
      </div>

      <div className="card">
        <h2>What to work on next</h2>
        {recommendations.length === 0 && <p style={{ color: "#94a3b8" }}>No open tasks to rank yet.</p>}
        {recommendations.map((r) => (
          <div className="task-row" key={r.task_id}>
            <span>
              #{r.rank} {r.title}
            </span>
            <span style={{ color: "#94a3b8", fontSize: 12 }}>
              score {r.score.toFixed(2)} — {r.reason}
            </span>
          </div>
        ))}
      </div>

      <div className="card">
        <h2>Tasks</h2>
        <NewTaskForm onCreate={onCreate} />
        {tasks.map((t) => (
          <div className="task-row" key={t.localId}>
            <span>
              {t.title}
              <span className={`pill ${t.priority}`}>{t.priority}</span>
              {t.dirty && <span className="pill" style={{ background: "#78350f" }}>unsynced</span>}
            </span>
            <span>
              {t.status !== "completed" && <button onClick={() => onComplete(t.localId)}>Complete</button>}{" "}
              <button className="secondary" onClick={() => dispatch(deleteTask(t.localId))}>
                Delete
              </button>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
