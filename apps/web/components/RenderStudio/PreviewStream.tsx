"use client";

import { useEffect, useRef, useState } from "react";

interface PreviewStreamProps {
  projectId: string;
  sceneHash: string;
  fps?: number;
  totalFrames?: number;
}

interface FrameEvent {
  kind: "PreviewFrameReady";
  frame_index: number;
  total: number;
  scene_hash: string;
}

export default function PreviewStream({
  projectId,
  sceneHash,
  fps = 24,
  totalFrames = 0,
}: PreviewStreamProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [loaded, setLoaded] = useState(0);
  const [total, setTotal] = useState(totalFrames);
  const [playing, setPlaying] = useState(false);
  const framesRef = useRef<HTMLImageElement[]>([]);
  const rafRef = useRef<number>(0);
  const frameIdxRef = useRef(0);
  const lastTimeRef = useRef(0);

  // Listen for WS PreviewFrameReady events and fetch each frame
  useEffect(() => {
    const wsUrl = `ws://localhost:8000/ws/project/${projectId}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = async (ev) => {
      try {
        const msg = JSON.parse(ev.data as string);
        if (msg.kind === "PreviewFrameReady" && msg.scene_hash === sceneHash) {
          const event = msg as FrameEvent;
          setTotal(event.total);
          const img = new Image();
          const url = `/api/projects/${projectId}/renders/${sceneHash}/preview/${event.frame_index}`;
          img.src = url;
          await new Promise<void>((res) => {
            img.onload = () => res();
            img.onerror = () => res();
          });
          framesRef.current[event.frame_index] = img;
          setLoaded((n) => n + 1);
        } else if (msg.kind === "PreviewCompleted" && msg.scene_hash === sceneHash) {
          setPlaying(true);
        }
      } catch {
        // ignore parse errors
      }
    };

    return () => ws.close();
  }, [projectId, sceneHash]);

  // Playback loop
  useEffect(() => {
    if (!playing) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const interval = 1000 / fps;

    const draw = (timestamp: number) => {
      if (timestamp - lastTimeRef.current >= interval) {
        lastTimeRef.current = timestamp;
        const frames = framesRef.current;
        const fi = frameIdxRef.current % frames.length;
        const img = frames[fi];
        if (img) {
          canvas.width = img.naturalWidth || canvas.width;
          canvas.height = img.naturalHeight || canvas.height;
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        }
        frameIdxRef.current = (fi + 1) % Math.max(frames.length, 1);
      }
      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [playing, fps]);

  const progress = total > 0 ? Math.round((loaded / total) * 100) : 0;

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-black rounded-lg overflow-hidden">
      <canvas
        ref={canvasRef}
        className="max-w-full max-h-full object-contain"
        style={{ aspectRatio: "9/16" }}
      />
      {!playing && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-slate-300 text-sm">
          <div className="w-48 h-1.5 bg-border rounded-full overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span>{progress}% — {loaded}/{total} frames</span>
        </div>
      )}
    </div>
  );
}
