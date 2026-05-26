import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, FileText, Upload } from "lucide-react";
import MarkdownText from "../components/MarkdownText";
import { api, getErrorMessage } from "../lib/api";
import { useTranslate } from "../lib/i18n.jsx";

const API_BASE = import.meta.env.VITE_API_BASE || "";

function formatBytes(value) {
  const num = Number(value || 0);
  if (num >= 1024 * 1024) return `${(num / (1024 * 1024)).toFixed(1)} MB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`;
  return `${num} B`;
}

function buildTree(entries) {
  const root = { name: "", children: new Map(), files: [] };
  for (const entry of entries || []) {
    const parts = entry.path.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i += 1) {
      const part = parts[i];
      if (!node.children.has(part)) {
        node.children.set(part, { name: part, children: new Map(), files: [] });
      }
      node = node.children.get(part);
    }
    node.files.push({ name: parts[parts.length - 1], entry });
  }
  return root;
}

function TreeNode({ node, depth = 0, openSet, onToggle, onPick, selectedPath }) {
  const dirs = Array.from(node.children.entries()).sort(([a], [b]) => a.localeCompare(b));
  const files = [...node.files].sort((a, b) => a.name.localeCompare(b.name));
  return (
    <ul className="space-y-0.5">
      {dirs.map(([name, child]) => {
        const path = (node.path ? node.path + "/" : "") + name;
        child.path = path;
        const open = openSet.has(path);
        return (
          <li key={path}>
            <button
              className="flex w-full items-center gap-1 rounded px-1 py-0.5 text-left text-xs hover:bg-zinc-100"
              style={{ paddingLeft: `${depth * 0.75 + 0.25}rem` }}
              onClick={() => onToggle(path)}
            >
              {open ? <ChevronDown className="h-3 w-3 text-zinc-500" /> : <ChevronRight className="h-3 w-3 text-zinc-500" />}
              <span className="truncate font-semibold text-zinc-700">{name}/</span>
            </button>
            {open ? (
              <TreeNode
                node={child}
                depth={depth + 1}
                openSet={openSet}
                onToggle={onToggle}
                onPick={onPick}
                selectedPath={selectedPath}
              />
            ) : null}
          </li>
        );
      })}
      {files.map(({ name, entry }) => (
        <li key={entry.path}>
          <button
            className={[
              "flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-zinc-100",
              selectedPath === entry.path ? "bg-blue-50 text-appleBlue" : "text-zinc-700",
            ].join(" ")}
            style={{ paddingLeft: `${depth * 0.75 + 1.1}rem` }}
            onClick={() => onPick(entry)}
            title={`${entry.kind} · ${formatBytes(entry.size)}`}
          >
            <FileText className="h-3 w-3 text-zinc-400" />
            <span className="truncate">{name}</span>
            <span className="ml-auto text-[10px] text-zinc-400">{formatBytes(entry.size)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}

function parseDelimited(text, delimiter) {
  // Minimal CSV/TSV parser supporting quoted fields with embedded
  // delimiter / newline / "" escape. Good enough for KB preview.
  const rows = [];
  let row = [];
  let field = "";
  let inQuote = false;
  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    if (inQuote) {
      if (ch === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuote = false;
        }
      } else {
        field += ch;
      }
      continue;
    }
    if (ch === '"') {
      inQuote = true;
      continue;
    }
    if (ch === delimiter) {
      row.push(field);
      field = "";
      continue;
    }
    if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
      continue;
    }
    if (ch === "\r") continue;
    field += ch;
  }
  if (field.length || row.length) {
    row.push(field);
    rows.push(row);
  }
  return rows.filter((r) => r.length && !(r.length === 1 && r[0] === ""));
}

function TableViewer({ rows }) {
  if (!rows.length) return <p className="text-xs text-zinc-500">Empty.</p>;
  const [header, ...body] = rows;
  const visibleBody = body.slice(0, 500);
  const truncated = body.length > visibleBody.length;
  return (
    <div className="overflow-auto">
      <table className="min-w-full text-xs">
        <thead className="bg-zinc-50">
          <tr>
            {header.map((cell, idx) => (
              <th key={idx} className="border border-line px-2 py-1 text-left font-semibold text-zinc-700">
                {cell}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visibleBody.map((r, idx) => (
            <tr key={idx} className="even:bg-zinc-50/40">
              {r.map((cell, jdx) => (
                <td key={jdx} className="border border-line px-2 py-1 align-top text-zinc-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {truncated ? (
        <p className="mt-1 text-[11px] text-zinc-500">Showing first 500 rows of {body.length}.</p>
      ) : null}
    </div>
  );
}

function CodeViewer({ content }) {
  // Mono with line numbers; no full syntax highlighter to keep bundle small.
  const lines = content.split("\n");
  return (
    <pre className="overflow-auto rounded-md bg-zinc-50 font-mono text-xs leading-relaxed text-zinc-800">
      <code>
        {lines.map((line, idx) => (
          <div key={idx} className="flex">
            <span className="sticky left-0 select-none border-r border-line bg-zinc-100 px-2 py-0 text-right text-zinc-400" style={{ minWidth: "3rem" }}>
              {idx + 1}
            </span>
            <span className="whitespace-pre px-3 py-0">{line || " "}</span>
          </div>
        ))}
      </code>
    </pre>
  );
}

function FileViewer({ payload, kbId, t }) {
  if (!payload) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        {t("kb.detail.pick_file")}
      </div>
    );
  }
  const lowerPath = payload.path.toLowerCase();

  if (payload.kind === "pdf") {
    const rawUrl = `${API_BASE}/api/knowledge-bases/${encodeURIComponent(kbId)}/file/raw?path=${encodeURIComponent(payload.path)}`;
    return (
      <div className="flex h-full flex-col gap-2">
        <iframe
          title={payload.path}
          src={rawUrl}
          className="h-[60vh] w-full rounded-md border border-line bg-white"
        />
        {payload.extraction_available ? (
          <details className="rounded-md border border-line bg-white p-2 text-xs">
            <summary className="cursor-pointer font-semibold text-zinc-600">
              {t("kb.detail.pdf_text")}
            </summary>
            <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap text-[11px] text-zinc-700">
              {payload.content}
            </pre>
          </details>
        ) : (
          <p className="text-[11px] text-zinc-500">{t("kb.detail.pdf_no_text")}</p>
        )}
      </div>
    );
  }

  if (payload.kind === "binary") {
    const rawUrl = `${API_BASE}/api/knowledge-bases/${encodeURIComponent(kbId)}/file/raw?path=${encodeURIComponent(payload.path)}`;
    const isImage = /\.(png|jpe?g|gif|webp|svg)$/.test(lowerPath);
    if (isImage) {
      return <img src={rawUrl} alt={payload.path} className="max-h-[60vh] rounded-md border border-line" />;
    }
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-zinc-500">
        <FileText className="h-8 w-8 text-zinc-300" />
        {t("kb.detail.binary", { size: formatBytes(payload.size) })}
      </div>
    );
  }

  if (lowerPath.endsWith(".md") || lowerPath.endsWith(".markdown")) {
    return (
      <div className="prose-sm max-w-none">
        <MarkdownText text={payload.content} />
      </div>
    );
  }

  if (lowerPath.endsWith(".csv")) {
    const rows = parseDelimited(payload.content, ",");
    return <TableViewer rows={rows} />;
  }
  if (lowerPath.endsWith(".tsv")) {
    const rows = parseDelimited(payload.content, "\t");
    return <TableViewer rows={rows} />;
  }

  if (lowerPath.endsWith(".json") || lowerPath.endsWith(".jsonl")) {
    let pretty = payload.content;
    if (lowerPath.endsWith(".json")) {
      try {
        pretty = JSON.stringify(JSON.parse(payload.content), null, 2);
      } catch {
        pretty = payload.content;
      }
    }
    return <CodeViewer content={pretty} />;
  }

  if (payload.kind === "code") {
    return <CodeViewer content={payload.content} />;
  }

  return (
    <pre className="overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-zinc-800">
      {payload.content}
    </pre>
  );
}

export default function KnowledgeBaseDetailPage({ kbId, onBack }) {
  const t = useTranslate();
  const [meta, setMeta] = useState(null);
  const [entries, setEntries] = useState([]);
  const [selected, setSelected] = useState(null);
  const [openSet, setOpenSet] = useState(new Set([""]));
  const [filter, setFilter] = useState("");
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const tree = await api.knowledgeBaseTree(kbId);
      setMeta(tree.data?.kb || null);
      setEntries(tree.data?.entries || []);
    } catch (caught) {
      setError(getErrorMessage(caught));
    }
  }, [kbId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const filteredEntries = useMemo(() => {
    if (!filter.trim()) return entries;
    const needle = filter.trim().toLowerCase();
    return entries.filter((entry) => entry.path.toLowerCase().includes(needle));
  }, [entries, filter]);

  const tree = useMemo(() => buildTree(filteredEntries), [filteredEntries]);

  const pickFile = useCallback(
    async (entry) => {
      try {
        const result = await api.knowledgeBaseFile(kbId, entry.path);
        setSelected(result.data);
      } catch (caught) {
        setError(getErrorMessage(caught));
      }
    },
    [kbId]
  );

  const toggle = useCallback((path) => {
    setOpenSet((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }, []);

  const fileInputRef = useRef(null);
  const [uploading, setUploading] = useState(false);
  const handleUpload = useCallback(async (event) => {
    const picked = Array.from(event.target.files || []);
    if (!picked.length) return;
    setUploading(true);
    try {
      const fd = new FormData();
      picked.forEach((file, idx) => {
        const key = `file${idx}`;
        fd.append(key, file, file.webkitRelativePath || file.name);
        if (file.webkitRelativePath) {
          fd.append(`path__${key}`, file.webkitRelativePath);
        }
      });
      await api.knowledgeBaseUpload(kbId, fd);
      await refresh();
    } catch (caught) {
      setError(getErrorMessage(caught));
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  }, [kbId, refresh]);

  return (
    <section className="min-h-0 flex-1 overflow-hidden">
      <div className="flex h-full flex-col">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line bg-white px-6 py-4">
          <div className="flex items-center gap-3 min-w-0">
            <button className="secondary-button" onClick={onBack}>
              <ArrowLeft className="h-4 w-4" />
              {t("kb.detail.back")}
            </button>
            <div className="min-w-0">
              <h2 className="truncate text-base font-semibold text-zinc-950">
                {meta?.name || kbId}
              </h2>
              <p className="truncate text-xs text-zinc-500">
                {meta?.source_url || meta?.description || t("kb.detail.local")}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-xs text-zinc-500">
            <span>
              {t("kb.field.files")}: <span className="font-mono">{meta?.file_count || 0}</span>{" "}
              · {t("kb.field.size")}: <span className="font-mono">{formatBytes(meta?.total_bytes || 0)}</span>
            </span>
            <button
              type="button"
              className="secondary-button"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              <Upload className="h-4 w-4" />
              {uploading ? t("kb.detail.uploading") : t("kb.detail.upload_more")}
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              onChange={handleUpload}
            />
          </div>
        </header>

        {error ? (
          <div className="border-b border-rose-200 bg-rose-50/60 px-6 py-2 text-xs text-rose-700">
            {error}
          </div>
        ) : null}

        <div className="grid min-h-0 flex-1 grid-cols-[16rem_1fr]">
          <aside className="border-r border-line bg-white p-3">
            <input
              className="mb-2 w-full rounded-md border border-line px-2 py-1 text-xs"
              placeholder={t("kb.detail.filter")}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <div className="overflow-auto" style={{ maxHeight: "calc(100vh - 220px)" }}>
              <TreeNode
                node={tree}
                openSet={openSet}
                onToggle={toggle}
                onPick={pickFile}
                selectedPath={selected?.path || ""}
              />
            </div>
          </aside>
          <main className="overflow-auto bg-zinc-50/40 p-4">
            <div className="rounded-lg border border-line bg-white p-3 min-h-[20rem]">
              {selected ? (
                <header className="mb-2 flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2">
                  <span className="truncate font-mono text-xs text-zinc-700">{selected.path}</span>
                  <span className="text-[11px] text-zinc-500">
                    {selected.kind} · {formatBytes(selected.size)}
                    {selected.truncated ? ` · ${t("kb.detail.truncated")}` : ""}
                  </span>
                </header>
              ) : null}
              <div className="min-h-[15rem]">
                <FileViewer payload={selected} kbId={kbId} t={t} />
              </div>
            </div>
          </main>
        </div>
      </div>
    </section>
  );
}
