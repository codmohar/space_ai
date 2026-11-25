import { type FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Lock, LogOut, Settings2, ShieldCheck, Users } from "lucide-react";
import { api, setAuthToken } from "../api/client";
import { useWorkspaceStore } from "../stores/workspaceStore";

export function AdminPage() {
  const queryClient = useQueryClient();
  const { authUser, setAuthUser } = useWorkspaceStore();

  const [email, setEmail] = useState("admin@missionwise.local");
  const [password, setPassword] = useState("Admin!Mission2026");
  const [authError, setAuthError] = useState<string | null>(null);

  const [selectorMode, setSelectorMode] = useState<string>("");
  const [rerankThresh, setRerankThresh] = useState<string>("");
  const [rrfThresh, setRrfThresh] = useState<string>("");
  const [promptVer, setPromptVer] = useState<string>("");

  const isAdmin = authUser?.role === "admin";

  const loginMutation = useMutation({
    mutationFn: () => api.login(email.trim(), password),
    onSuccess: (res) => {
      setAuthToken(res.access_token);
      setAuthUser(res.user);
      setAuthError(null);
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["admin-audit"] });
      queryClient.invalidateQueries({ queryKey: ["admin-retrieval"] });
      queryClient.invalidateQueries({ queryKey: ["admin-settings"] });
    },
    onError: (err: Error) => setAuthError(err.message),
  });

  const usersQuery = useQuery({
    queryKey: ["admin-users", authUser?.id],
    queryFn: api.listAdminUsers,
    enabled: isAdmin,
  });

  const auditQuery = useQuery({
    queryKey: ["admin-audit", authUser?.id],
    queryFn: () => api.listAuditLogs(60),
    enabled: isAdmin,
  });

  const retrievalQuery = useQuery({
    queryKey: ["admin-retrieval", authUser?.id],
    queryFn: () => api.listRetrievalLogs(60),
    enabled: isAdmin,
  });

  const settingsQuery = useQuery({
    queryKey: ["admin-settings", authUser?.id],
    queryFn: api.getAdminSettings,
    enabled: isAdmin,
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: "admin" | "engineer" }) =>
      api.updateUserRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-users"] });
      queryClient.invalidateQueries({ queryKey: ["admin-audit"] });
    },
  });

  const settingsMutation = useMutation({
    mutationFn: () =>
      api.updateAdminSettings({
        ...(selectorMode ? { section_selector_mode: selectorMode } : {}),
        ...(rerankThresh ? { min_rerank_score_threshold: Number(rerankThresh) } : {}),
        ...(rrfThresh ? { min_rrf_score_threshold: Number(rrfThresh) } : {}),
        ...(promptVer ? { prompt_version: promptVer } : {}),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin-settings"] });
      queryClient.invalidateQueries({ queryKey: ["admin-audit"] });
    },
  });

  const handleLogin = (e: FormEvent) => {
    e.preventDefault();
    loginMutation.mutate();
  };

  const handleLogout = () => {
    setAuthToken(null);
    setAuthUser(null);
  };

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Auth Header Card */}
        <section className="rounded border border-console-border bg-console-surface p-5">
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-console-border pb-4">
            <div>
              <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-signal-amber">
                <ShieldCheck className="h-4 w-4" />
                SYSTEM GOVERNANCE & TELEMETRY
              </div>
              <h2 className="mt-1 text-lg font-semibold text-ink-primary">
                Admin Console · RBAC, Retrieval Telemetry & Audit Logs
              </h2>
            </div>

            {authUser ? (
              <div className="flex items-center gap-3">
                <div className="rounded border border-console-borderStrong bg-console-elevated px-3 py-1.5 font-mono text-xs">
                  <span className="text-ink-primary">{authUser.email}</span>
                  <span className="ml-2 rounded bg-signal-amberDim px-1.5 py-0.5 text-[10px] uppercase text-signal-amber">
                    {authUser.role}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="inline-flex items-center gap-1.5 rounded border border-console-borderStrong px-3 py-1.5 font-mono text-xs text-ink-secondary hover:border-status-conflict hover:text-status-conflict"
                >
                  <LogOut className="h-3.5 w-3.5" />
                  Sign Out
                </button>
              </div>
            ) : null}
          </div>

          {!authUser && (
            <form onSubmit={handleLogin} className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
              <div>
                <label className="block font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="mt-1 w-full rounded border border-console-borderStrong bg-console-bg px-3 py-2 font-mono text-xs text-ink-primary"
                  required
                />
              </div>
              <div>
                <label className="block font-mono text-[10px] uppercase tracking-wider text-ink-muted">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="mt-1 w-full rounded border border-console-borderStrong bg-console-bg px-3 py-2 font-mono text-xs text-ink-primary"
                  required
                />
              </div>
              <div className="flex items-end gap-2">
                <button
                  type="submit"
                  disabled={loginMutation.isPending}
                  className="inline-flex items-center gap-1.5 rounded bg-signal-amber px-4 py-2 font-mono text-xs font-semibold text-console-bg hover:bg-signal-amber/90 disabled:opacity-50"
                >
                  <KeyRound className="h-3.5 w-3.5" />
                  {loginMutation.isPending ? "Signing In..." : "Sign In (JWT)"}
                </button>
              </div>
              <div className="flex items-end gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setEmail("admin@missionwise.local");
                    setPassword("Admin!Mission2026");
                  }}
                  className="rounded border border-console-border px-2.5 py-2 font-mono text-[10px] text-ink-secondary hover:border-signal-amber"
                >
                  Fill Admin
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setEmail("engineer@missionwise.local");
                    setPassword("Engineer!Mission2026");
                  }}
                  className="rounded border border-console-border px-2.5 py-2 font-mono text-[10px] text-ink-secondary hover:border-signal-amber"
                >
                  Fill Engineer
                </button>
              </div>
              {authError && (
                <p className="md:col-span-4 font-mono text-xs text-status-conflict">
                  {authError}
                </p>
              )}
            </form>
          )}

          {authUser && !isAdmin && (
            <div className="mt-4 flex items-center gap-2 rounded border border-signal-amber/40 bg-signal-amberDim/30 p-3 font-mono text-xs text-signal-amber">
              <Lock className="h-4 w-4 shrink-0" />
              Signed in with role "{authUser.role}". Admin privileges are required to view RBAC, runtime thresholds, and security audit logs.
            </div>
          )}
        </section>

        {isAdmin && (
          <>
            {/* Runtime Settings + Users Grid */}
            <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
              <section className="rounded border border-console-border bg-console-surface p-5">
                <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-ink-secondary">
                  <Users className="h-4 w-4 text-signal-amber" />
                  Role-Based Access Control (Users)
                </div>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-left font-mono text-xs">
                    <thead className="border-b border-console-border text-[10px] uppercase text-ink-muted">
                      <tr>
                        <th className="py-2">Email</th>
                        <th className="py-2">Role</th>
                        <th className="py-2 text-right">Action</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-console-border/50">
                      {(usersQuery.data || []).map((u) => (
                        <tr key={u.id}>
                          <td className="py-2 text-ink-primary">{u.email}</td>
                          <td className="py-2 uppercase text-signal-amber">{u.role}</td>
                          <td className="py-2 text-right">
                            <button
                              type="button"
                              onClick={() =>
                                roleMutation.mutate({
                                  userId: u.id,
                                  role: u.role === "admin" ? "engineer" : "admin",
                                })
                              }
                              className="rounded border border-console-borderStrong px-2 py-0.5 text-[10px] text-ink-secondary hover:border-signal-amber hover:text-ink-primary"
                            >
                              Switch to {u.role === "admin" ? "engineer" : "admin"}
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>

              <section className="rounded border border-console-border bg-console-surface p-5">
                <div className="flex items-center gap-2 font-mono text-xs uppercase tracking-wider text-ink-secondary">
                  <Settings2 className="h-4 w-4 text-signal-amber" />
                  Runtime Model & Sufficiency Thresholds
                </div>
                {settingsQuery.data && (
                  <div className="mt-3 space-y-3 font-mono text-xs">
                    <div className="grid grid-cols-2 gap-2 rounded border border-console-border bg-console-bg p-3 text-[11px]">
                      <div>
                        <span className="text-ink-muted">LLM:</span>{" "}
                        <span className="text-ink-primary">{settingsQuery.data.gemini_model}</span>
                      </div>
                      <div>
                        <span className="text-ink-muted">EMBED:</span>{" "}
                        <span className="text-ink-primary">{settingsQuery.data.embedding_model}</span>
                      </div>
                      <div>
                        <span className="text-ink-muted">RERANK:</span>{" "}
                        <span className="text-ink-primary">{settingsQuery.data.reranker_model}</span>
                      </div>
                      <div>
                        <span className="text-ink-muted">RATE LIMIT:</span>{" "}
                        <span className="text-ink-primary">
                          {settingsQuery.data.chat_rate_limit_per_minute}/min chat
                        </span>
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="block text-[10px] uppercase text-ink-muted">
                          Selector Mode ({settingsQuery.data.section_selector_mode})
                        </label>
                        <select
                          value={selectorMode || settingsQuery.data.section_selector_mode}
                          onChange={(e) => setSelectorMode(e.target.value)}
                          className="mt-1 w-full rounded border border-console-borderStrong bg-console-bg px-2 py-1.5 text-xs text-ink-primary"
                        >
                          <option value="auto">auto</option>
                          <option value="l1_passthrough">l1_passthrough</option>
                          <option value="bm25_toc">bm25_toc</option>
                          <option value="stair_l2">stair_l2</option>
                          <option value="stair_l3">stair_l3</option>
                        </select>
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase text-ink-muted">
                          Prompt Version ({settingsQuery.data.prompt_version})
                        </label>
                        <input
                          value={promptVer}
                          placeholder={settingsQuery.data.prompt_version}
                          onChange={(e) => setPromptVer(e.target.value)}
                          className="mt-1 w-full rounded border border-console-borderStrong bg-console-bg px-2 py-1.5 text-xs text-ink-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase text-ink-muted">
                          Min Rerank ({settingsQuery.data.min_rerank_score_threshold})
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          value={rerankThresh}
                          placeholder={String(settingsQuery.data.min_rerank_score_threshold)}
                          onChange={(e) => setRerankThresh(e.target.value)}
                          className="mt-1 w-full rounded border border-console-borderStrong bg-console-bg px-2 py-1.5 text-xs text-ink-primary"
                        />
                      </div>
                      <div>
                        <label className="block text-[10px] uppercase text-ink-muted">
                          Min RRF ({settingsQuery.data.min_rrf_score_threshold})
                        </label>
                        <input
                          type="number"
                          step="0.001"
                          value={rrfThresh}
                          placeholder={String(settingsQuery.data.min_rrf_score_threshold)}
                          onChange={(e) => setRrfThresh(e.target.value)}
                          className="mt-1 w-full rounded border border-console-borderStrong bg-console-bg px-2 py-1.5 text-xs text-ink-primary"
                        />
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => settingsMutation.mutate()}
                      disabled={settingsMutation.isPending}
                      className="rounded bg-signal-amber px-3 py-1.5 font-semibold text-console-bg hover:bg-signal-amber/90 disabled:opacity-50"
                    >
                      {settingsMutation.isPending ? "Saving..." : "Apply Runtime Settings"}
                    </button>
                  </div>
                )}
              </section>
            </div>

            {/* Retrieval & Model/Prompt Version Logs */}
            <section className="rounded border border-console-border bg-console-surface p-5">
              <h3 className="font-mono text-xs uppercase tracking-wider text-ink-secondary">
                Retrieval & Model/Prompt Version Logs (Latest 60)
              </h3>
              <div className="mt-3 max-h-64 overflow-y-auto">
                <table className="w-full text-left font-mono text-[11px] tabular-nums">
                  <thead className="border-b border-console-border text-[10px] uppercase text-ink-muted">
                    <tr>
                      <th className="py-1.5">Query</th>
                      <th className="py-1.5">STAIR</th>
                      <th className="py-1.5">Confidence</th>
                      <th className="py-1.5">LLM / Prompt</th>
                      <th className="py-1.5 text-right">Latency</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-console-border/40">
                    {(retrievalQuery.data || []).map((row) => (
                      <tr key={row.id}>
                        <td className="max-w-xs truncate py-1.5 pr-3 text-ink-primary">
                          {row.query_text}
                        </td>
                        <td className="py-1.5 pr-2 text-ink-secondary">{row.stair_level}</td>
                        <td className="py-1.5 pr-2">
                          <span
                            className={
                              row.abstained ? "text-status-conflict" : "text-status-verified"
                            }
                          >
                            {row.confidence_category}
                          </span>
                        </td>
                        <td className="py-1.5 pr-2 text-ink-muted">
                          {row.llm_model} · {row.prompt_version}
                        </td>
                        <td className="py-1.5 text-right text-ink-secondary">
                          {row.latency_ms}ms
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Security Audit Logs */}
            <section className="rounded border border-console-border bg-console-surface p-5">
              <h3 className="font-mono text-xs uppercase tracking-wider text-ink-secondary">
                Security Audit Logs (Latest 60)
              </h3>
              <div className="mt-3 max-h-64 overflow-y-auto">
                <table className="w-full text-left font-mono text-[11px]">
                  <thead className="border-b border-console-border text-[10px] uppercase text-ink-muted">
                    <tr>
                      <th className="py-1.5">Action</th>
                      <th className="py-1.5">Resource</th>
                      <th className="py-1.5">Request ID</th>
                      <th className="py-1.5">Timestamp</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-console-border/40">
                    {(auditQuery.data || []).map((row) => (
                      <tr key={row.id}>
                        <td className="py-1.5 pr-3 text-signal-amber">{row.action}</td>
                        <td className="py-1.5 pr-3 text-ink-primary">
                          {row.resource_type}
                          {row.resource_id ? `:${row.resource_id.slice(0, 8)}` : ""}
                        </td>
                        <td className="py-1.5 pr-3 text-ink-muted">
                          {row.request_id ? row.request_id.slice(0, 14) : "-"}
                        </td>
                        <td className="py-1.5 text-ink-secondary">
                          {new Date(row.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  );
}
