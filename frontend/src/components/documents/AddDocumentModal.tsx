import React, { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CheckCircle2, FileUp, Loader2, UploadCloud, X } from "lucide-react";
import { API_BASE_URL, type IngestionJobOut } from "../../api/client";

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
            <p className="mt-2 font-mono text-xs font-medium text-ink-primary">
              Drag and drop PDF/DOCX/PPTX files here, or browse
            </p>
            <p className="mt-1 font-mono text-[11px] text-ink-muted">
              PDF, scanned PDF (OCR), DOCX, PPTX, TXT, MD, CSV, XLSX, XML (max 100MB)
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
              <div className="mt-3 font-mono text-xs text-signal-amber">
                Selected: {files.map((f) => f.name).join(", ")}
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
            <div className="space-y-2 rounded border border-signal-amber/40 bg-signal-amberDim/20 p-3 font-mono">
              <div className="flex items-center gap-2 font-semibold text-signal-amber">
                <CheckCircle2 className="h-4 w-4" />
                <span>Submitted {jobs.length} Document(s) to Background Queue</span>
              </div>
              {jobs.map((j) => (
                <div key={j.job_id} className="flex items-center justify-between text-[11px]">
                  <span>{j.filename}</span>
                  <span className="rounded bg-console-base px-1.5 py-0.5 uppercase text-signal-amber">
                    {j.status} ({j.progress_pct}%)
                  </span>
                </div>
              ))}
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

