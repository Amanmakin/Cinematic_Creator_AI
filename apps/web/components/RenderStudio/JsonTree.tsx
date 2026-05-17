"use client";

interface JsonTreeProps {
  data: unknown;
  depth?: number;
}

export default function JsonTree({ data, depth = 0 }: JsonTreeProps) {
  if (data === null || data === undefined) {
    return (
      <div className="text-slate-600 italic text-sm">
        No scene graph yet. Submit a prompt to generate one.
      </div>
    );
  }

  return (
    <div className="font-mono text-xs leading-relaxed">
      <Node value={data} depth={depth} />
    </div>
  );
}

function Node({ value, depth }: { value: unknown; depth: number }) {
  const indent = depth * 16;

  if (value === null) return <span className="text-slate-500">null</span>;
  if (typeof value === "boolean") return <span className="text-purple-400">{String(value)}</span>;
  if (typeof value === "number") return <span className="text-green-400">{value}</span>;
  if (typeof value === "string") return <span className="text-yellow-300">"{value}"</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-slate-400">[]</span>;
    return (
      <span>
        {"["}
        <div style={{ marginLeft: indent + 16 }}>
          {value.map((item, i) => (
            <div key={i}>
              <Node value={item} depth={depth + 1} />
              {i < value.length - 1 && <span className="text-slate-500">,</span>}
            </div>
          ))}
        </div>
        {"]"}
      </span>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-slate-400">{"{}"}</span>;
    return (
      <span>
        {"{"}
        <div style={{ marginLeft: 16 }}>
          {entries.map(([k, v], i) => (
            <div key={k}>
              <span className="text-cyan-400">"{k}"</span>
              <span className="text-slate-400">: </span>
              <Node value={v} depth={depth + 1} />
              {i < entries.length - 1 && <span className="text-slate-500">,</span>}
            </div>
          ))}
        </div>
        {"}"}
      </span>
    );
  }

  return <span>{String(value)}</span>;
}
