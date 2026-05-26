import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, ChevronDown, ChevronRight, FileText } from "lucide-react";
import { api, getErrorMessage } from "../lib/api";
import { useTranslate } from "../lib/i18n.jsx";

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

function FileViewer({ payload, t }) {
  if (!payload) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-zinc-500">
        {t("kb.detail.pick_file")}
      </div>
    );
  }
  if (payload.kind === "binary") {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-zinc-500">
        <FileText className="h-8 w-8 text-zinc-300" />
        {t("kb.detail.binary", { size: formatBytes(payload.size) })}
      </div>
    );
  }
  const isMarkdown = payload.path.toLowerCase().endsWith(".md") || payload.path.toLowerCase().endsWith(".markdown");
  if (isMarkdown) {
    return (
      <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-zinc-800">
        {payload.content}
      </pre>
    );
  }
  return (
    <pre className="overflow-auto font-mono text-xs leading-relaxed text-zinc-800">
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
          <div className="text-xs text-zinc-500">
            {t("kb.field.files")}: <span className="font-mono">{meta?.file_count || 0}</span>{" "}
            · {t("kb.field.size")}: <span className="font-mono">{formatBytes(meta?.total_bytes || 0)}</span>
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
                <FileViewer payload={selected} t={t} />
              </div>
            </div>
          </main>
        </div>
      </div>
    </section>
  );
}
