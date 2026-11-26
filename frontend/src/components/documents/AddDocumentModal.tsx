import React, { useEffect, useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileUp, Loader2, UploadCloud, X } from "lucide-react";
import { API_BASE_URL, api, type IngestionJobOut } from "../../api/client";
import { useWorkspaceStore } from "../../stores/workspaceStore";

interface AddDocumentModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function AddDocumentModal({ isOpen, onClose, onSuccess }: AddDocumentModalProps) {
  const queryClient = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [docCode, setDocCode] = useState("");
  const [title, setTitle] = useState("");
  const [mission, setMission] = useState("");
  const [organization, setOrganization] = useState("NASA");
  const [sourceUrl, setSourceUrl] = useState("");
  const [licence, setLicence] = useState("Public Domain / NASA Technical Report");
  const [noPublicUrl, setNoPublicUrl] = useState(false);
  const [classification, setClassification] = useState<"public" | "internal" | "restricted">("public");
  const [jobs, setJobs] = useState<IngestionJobOut[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const addIngestionNotification = useWorkspaceStore((s) => s.addIngestionNotification);
  const updateIngestionNotification = useWorkspaceStore((s) => s.updateIngestionNotification);
  const pollTimersRef = useRef<{ [key: string]: ReturnType<typeof setInterval> }>({});

  useEffect(() => {
    return () => {
      Object.values(pollTimersRef.current).forEach((t) => clearInterval(t));
    };
  }, []);

  const uploadMutation = useMutation({
    mutationFn: async () => {
      setErrorMsg(null);
      if (files.length === 0) {
        throw new Error("Please select at least one document file.");
      }

      const finalSourceUrl = noPublicUrl ? "uploaded, no public URL" : sourceUrl.trim();
      if (!noPublicUrl && !finalSourceUrl.startsWith("http")) {
        throw new Error("Please provide a valid http(s) URL or check 'Uploaded, no public URL'.");
      }

      const submittedJobs: IngestionJobOut[] = [];

      for (const file of files) {
        const formData = new FormData();
        formData.append("file", file);
        if (docCode.trim()) {
          formData.append("doc_code", docCode.trim());
        }
        formData.append("title", title.trim() || file.name.replace(/\.[^/.]+$/, ""));
        formData.append("mission", mission.trim() || "Aerospace Engineering");
        formData.append("org", organization.trim() || "NASA");
        formData.append("organization", organization.trim() || "NASA");
        formData.append("source_url", finalSourceUrl);
        formData.append("licence", licence.trim() || "Public Domain");
        formData.append("classification", classification);

        const res = await fetch(`${API_BASE_URL}/api/documents/upload/async`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const err = await res.json().catch(() => ({ message: res.statusText }));
          throw new Error(err.message || `Upload failed for ${file.name}`);
        }

        const job: IngestionJobOut = await res.json();
        submittedJobs.push(job);
      }

      return submittedJobs;
    },
    onSuccess: (newJobs) => {
      setJobs(newJobs);
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["corpus-stats"] });

      newJobs.forEach((job) => {
        const fileTitle = title.trim() || job.filename.replace(/\.[^/.]+$/, "");
        addIngestionNotification({
          jobId: job.job_id,
          filename: job.filename,
          title: fileTitle,
          status: "processing",
          progressPct: job.progress_pct || 15,
          message: `Reading & processing document "${fileTitle}"... Extracting text, ToC hierarchy, chunks & vector embeddings`,
        });

        if (pollTimersRef.current[job.job_id]) {
          clearInterval(pollTimersRef.current[job.job_id]);
        }

        pollTimersRef.current[job.job_id] = setInterval(async () => {
          try {
            const updated = await api.getJobStatus(job.job_id);
            setJobs((prev) => prev.map((j) => (j.job_id === job.job_id ? updated : j)));

            if (updated.status === "indexed") {
              updateIngestionNotification(job.job_id, {
                status: "indexed",
                progressPct: 100,
                message: `Document seeded successfully in database! "${fileTitle}" is now ready for RAG and STAIR queries.`,
                documentId: updated.document_id,
              });
              queryClient.invalidateQueries({ queryKey: ["documents"] });
              queryClient.invalidateQueries({ queryKey: ["corpus-stats"] });
              clearInterval(pollTimersRef.current[job.job_id]);
              delete pollTimersRef.current[job.job_id];
            } else if (updated.status === "failed" || updated.status === "cancelled") {
              updateIngestionNotification(job.job_id, {
                status: updated.status,
                message: updated.error_message || "Ingestion process encountered an error.",
              });
              clearInterval(pollTimersRef.current[job.job_id]);
              delete pollTimersRef.current[job.job_id];
            } else {
              updateIngestionNotification(job.job_id, {
                status: updated.status,
                progressPct: updated.progress_pct,
                message: `Reading and processing document (${updated.progress_pct}%)...`,
              });
            }
          } catch {
            // Keep polling
          }
        }, 1200);
      });

      if (onSuccess) onSuccess();
    },
    onError: (err: Error) => {
      setErrorMsg(err.message);
    },
  });

  if (!isOpen) return null;

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      setFiles(Array.from(e.target.files));
      if (e.target.files.length === 1 && !title) {
        setTitle(e.target.files[0].name.replace(/\.[^/.]+$/, ""));
      }
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded border border-console-borderStrong bg-console-surface text-ink-primary shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-console-border bg-console-elevated px-5 py-3">
          <div className="flex items-center gap-2.5">
            <FileUp className="h-4 w-4 text-signal-amber" />
            <h3 className="font-mono text-sm font-semibold uppercase tracking-wider text-ink-primary">
              Add Mission Documents to Archive
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-ink-muted hover:bg-console-base hover:text-ink-primary"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 space-y-4 overflow-y-auto p-5 text-xs">
          {errorMsg && (
            <div className="flex items-center gap-2 rounded border border-status-conflict/40 bg-status-conflict/10 p-3 font-mono text-status-conflict">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Drag & Drop Picker */}
          <div className="rounded border-2 border-dashed border-console-borderStrong bg-console-base/60 p-5 text-center hover:border-signal-amber">
            <UploadCloud className="mx-auto h-8 w-8 text-signal-amber" />
            <p className="mt-2 font-mono text-xs font-semibold text-ink-primary">
              Drag & drop Text PDFs, Scanned/Picture PDFs, or Images here
            </p>
            <p className="mt-1 font-mono text-[11px] text-ink-muted">
              Auto-detects Text vs Picture/Scanned pages · Fast In-Memory OCR & ToC hierarchy extraction
            </p>
            <label className="mt-3 inline-block cursor-pointer rounded border border-console-borderStrong bg-console-elevated px-3 py-1.5 font-mono text-xs hover:border-signal-amber">
              Select Files
              <input
                type="file"
                multiple
                accept=".pdf,.docx,.pptx,.txt,.md,.html,.csv,.xlsx,.xml,.png,.jpg,.jpeg,.tiff"
                onChange={handleFileChange}
                className="hidden"
              />
            </label>
            {files.length > 0 && (
              <div className="mt-3 space-y-1 font-mono text-xs">
                {files.map((f, i) => {
                  const isPdf = f.name.toLowerCase().endsWith(".pdf");
                  const isImg = /\.(png|jpe?g|tiff?)$/i.test(f.name);
                  return (
                    <div key={i} className="flex items-center justify-between rounded bg-console-elevated px-2 py-1 text-[11px]">
                      <span className="text-signal-amber truncate max-w-[280px]">{f.name}</span>
                      <span className="text-ink-muted">
                        {(f.size / (1024 * 1024)).toFixed(2)} MB · {isPdf ? "PDF (Text/Picture)" : isImg ? "Picture/Image (OCR)" : "Document"}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Metadata Form */}
          <div className="grid grid-cols-2 gap-3 font-mono">
            <div>
              <label className="block text-[11px] text-ink-muted">Document Code (Optional)</label>
              <input
                type="text"
                value={docCode}
                onChange={(e) => setDocCode(e.target.value)}
                placeholder="e.g. NASA-MCO-1999"
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs placeholder:text-gray-400 focus:border-signal-amber focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] text-ink-muted">Document Title</label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Apollo 13 Review Board Report"
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs placeholder:text-gray-400 focus:border-signal-amber focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] text-ink-muted">Mission Scope</label>
              <input
                type="text"
                value={mission}
                onChange={(e) => setMission(e.target.value)}
                placeholder="e.g. Apollo 13, Mars Orbiter"
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs placeholder:text-gray-400 focus:border-signal-amber focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] text-ink-muted">Agency / Organization</label>
              <input
                type="text"
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                placeholder="e.g. NASA, ISRO, ESA"
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs placeholder:text-gray-400 focus:border-signal-amber focus:outline-none"
              />
            </div>

            <div className="col-span-2">
              <div className="flex items-center justify-between">
                <label className="block text-[11px] text-ink-muted">Archival Provenance Source URL</label>
                <label className="flex items-center gap-1.5 text-[11px] text-ink-muted">
                  <input
                    type="checkbox"
                    checked={noPublicUrl}
                    onChange={(e) => setNoPublicUrl(e.target.checked)}
                    className="accent-signal-amber"
                  />
                  Uploaded, no public URL
                </label>
              </div>
              <input
                type="url"
                disabled={noPublicUrl}
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
                placeholder={noPublicUrl ? "uploaded, no public URL" : "https://ntrs.nasa.gov/citations/..."}
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs placeholder:text-gray-400 disabled:opacity-50 focus:border-signal-amber focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] text-ink-muted">Licence</label>
              <input
                type="text"
                value={licence}
                onChange={(e) => setLicence(e.target.value)}
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs placeholder:text-gray-400 focus:border-signal-amber focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-[11px] text-ink-muted">Classification Level</label>
              <select
                value={classification}
                onChange={(e) => setClassification(e.target.value as any)}
                className="mt-1 w-full rounded border border-console-borderStrong bg-white text-gray-950 px-2.5 py-1.5 text-xs focus:border-signal-amber focus:outline-none"
              >
                <option value="public">Public (Unrestricted)</option>
                <option value="internal">Internal (Engineering Clearance)</option>
                <option value="restricted">Restricted (Admin Clearance)</option>
              </select>
            </div>
          </div>

          {/* Active submitted jobs tracker */}
          {jobs.length > 0 && (
            <div className="space-y-2.5 rounded border border-signal-amber/40 bg-signal-amberDim/20 p-3.5 font-mono">
              <div className="flex items-center gap-2 font-semibold text-signal-amber">
                <CheckCircle2 className="h-4 w-4" />
                <span>Submitted {jobs.length} Document(s) for Processing & DB Seeding</span>
              </div>
              {jobs.map((j) => {
                const isDone = j.status === "indexed";
                const isFail = j.status === "failed";
                return (
                  <div key={j.job_id} className="rounded border border-console-border bg-console-base/80 p-2.5 text-[11px]">
                    <div className="flex items-center justify-between font-medium">
                      <span className="text-ink-primary">{j.filename}</span>
                      <span
                        className={`rounded px-1.5 py-0.5 uppercase ${
                          isDone
                            ? "bg-status-verified text-console-base"
                            : isFail
                              ? "bg-status-conflict text-white"
                              : "bg-signal-amber text-console-base"
                        }`}
                      >
                        {isDone ? "SEEDED (100%)" : isFail ? "FAILED" : `PROCESSING (${j.progress_pct}%)`}
                      </span>
                    </div>
                    {/* Progress bar */}
                    <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-console-borderStrong">
                      <div
                        style={{ width: `${Math.max(10, j.progress_pct)}%` }}
                        className={`h-full transition-all duration-300 ${
                          isDone ? "bg-status-verified" : isFail ? "bg-status-conflict" : "bg-signal-amber"
                        }`}
                      />
                    </div>
                    <p className="mt-1.5 text-[10px] text-ink-secondary">
                      {isDone
                        ? "✓ Successfully parsed, embedded, and seeded into database."
                        : isFail
                          ? `✗ Ingestion failed: ${j.error_message || "unknown error"}`
                          : "Reading PDF structure, ToC, chunking, and embedding into database..."}
                    </p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2.5 border-t border-console-border bg-console-elevated px-5 py-3 font-mono text-xs">
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-console-borderStrong px-3 py-1.5 hover:bg-console-base"
          >
            Close
          </button>
          <button
            type="button"
            disabled={uploadMutation.isPending || files.length === 0}
            onClick={() => uploadMutation.mutate()}
            className="inline-flex items-center gap-1.5 rounded border border-signal-amber bg-signal-amber px-4 py-1.5 font-semibold text-console-base hover:bg-signal-amber/90 disabled:opacity-40"
          >
            {uploadMutation.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {uploadMutation.isPending ? "Submitting..." : "Start Ingestion"}
          </button>
        </div>
      </div>
    </div>
  );
}

