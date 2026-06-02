"use client";

import { useRef, useState } from "react";
import { uploadSampleImages } from "@/lib/api";
import { useProjectStore } from "@/state/projectStore";

const ACCEPTED = "image/jpeg,image/png,image/webp,image/gif";
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Preview {
  file: File;
  objectUrl: string;
}

export default function PromptComposer() {
  const { submitPrompt, isRunning, projectId, agentState } = useProjectStore();
  const [prompt, setPrompt] = useState("");
  const [previews, setPreviews] = useState<Preview[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function addFiles(files: FileList | File[]) {
    const arr = Array.from(files);
    const newPreviews = arr.map((f) => ({ file: f, objectUrl: URL.createObjectURL(f) }));
    setPreviews((prev) => [...prev, ...newPreviews]);
    setUploadError(null);
  }

  function removePreview(index: number) {
    setPreviews((prev) => {
      URL.revokeObjectURL(prev[index].objectUrl);
      return prev.filter((_, i) => i !== index);
    });
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // A prompt OR a reference image is enough — the backend auto-captions
    // image-only submissions.
    if ((!prompt.trim() && previews.length === 0) || !projectId) return;

    let imageUrls: string[] = [];
    if (previews.length > 0) {
      setUploading(true);
      setUploadError(null);
      try {
        imageUrls = await uploadSampleImages(projectId, previews.map((p) => p.file));
      } catch (err: unknown) {
        setUploadError(err instanceof Error ? err.message : "Upload failed");
        setUploading(false);
        return;
      } finally {
        setUploading(false);
      }
    }

    await submitPrompt(prompt.trim(), imageUrls);
    setPrompt("");
  };

  const busy = isRunning || uploading;

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-2">
      <label className="text-xs font-medium text-zinc-400 uppercase tracking-wide">Prompt</label>
      <textarea
        className="bg-zinc-800 border border-zinc-600 rounded-md p-3 text-sm text-zinc-100 resize-none h-24 focus:outline-none focus:ring-2 focus:ring-indigo-500/60 focus:border-indigo-500 placeholder:text-zinc-500 transition-all"
        placeholder="Describe the cinematic scene… (or drop a reference image below and Generate)"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        disabled={busy}
      />

      {/* Image drop zone */}
      <div
        className={`relative rounded-md border-2 border-dashed transition-colors ${
          dragOver
            ? "border-indigo-400 bg-indigo-500/10"
            : "border-zinc-600 hover:border-zinc-500"
        } ${busy ? "opacity-50 pointer-events-none" : "cursor-pointer"}`}
        onClick={() => fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED}
          multiple
          className="hidden"
          onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
        />

        {previews.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-4 gap-1">
            <svg className="w-5 h-5 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
            </svg>
            <p className="text-xs text-zinc-500">Add sample images <span className="text-zinc-600">(optional)</span></p>
          </div>
        ) : (
          <div
            className="flex flex-wrap gap-2 p-2"
            onClick={(e) => e.stopPropagation()}
          >
            {previews.map((p, i) => (
              <div key={p.objectUrl} className="relative group">
                <img
                  src={p.objectUrl}
                  alt={p.file.name}
                  className="h-16 w-16 object-cover rounded-md border border-zinc-600"
                />
                <button
                  type="button"
                  onClick={() => removePreview(i)}
                  className="absolute -top-1.5 -right-1.5 hidden group-hover:flex items-center justify-center w-4 h-4 rounded-full bg-zinc-900 border border-zinc-600 text-zinc-300 hover:text-white text-[10px] leading-none"
                >
                  ×
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="h-16 w-16 flex items-center justify-center rounded-md border border-dashed border-zinc-600 hover:border-zinc-400 text-zinc-500 hover:text-zinc-300 transition-colors text-xl"
            >
              +
            </button>
          </div>
        )}
      </div>

      {/* Persisted reference images from the active run — shown when local previews are gone */}
      {previews.length === 0 && agentState?.sample_image_urls && agentState.sample_image_urls.length > 0 && (
        <div className="flex flex-wrap gap-2 px-1">
          {agentState.sample_image_urls.map((url) => (
            <img
              key={url}
              src={`${API_BASE}${url}`}
              alt="reference"
              className="h-16 w-16 object-cover rounded-md border border-zinc-600 opacity-70"
            />
          ))}
        </div>
      )}

      {uploadError && (
        <p className="text-xs text-red-400">{uploadError}</p>
      )}

      <button
        type="submit"
        disabled={busy || !projectId || (!prompt.trim() && previews.length === 0)}
        className="bg-indigo-500 hover:bg-indigo-400 disabled:opacity-40 text-white text-sm font-medium rounded-md py-2.5 transition-colors shadow-md shadow-indigo-500/20"
      >
        {uploading ? "Uploading…" : isRunning ? "Running…" : "Generate"}
      </button>
    </form>
  );
}
