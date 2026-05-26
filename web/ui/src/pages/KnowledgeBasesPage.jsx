import { useCallback, useEffect, useState } from "react";
import { BookOpen, Github, Plus, RefreshCcw, Trash2, Upload } from "lucide-react";
import EmptyState from "../components/EmptyState";
import Paginator, { paginate } from "../components/Paginator";
import { api, getErrorMessage } from "../lib/api";
import { compact, formatDate } from "../lib/format";
import { useTranslate } from "../lib/i18n.jsx";
import KnowledgeBaseDetailPage from "./KnowledgeBaseDetailPage";

function formatBytes(value) {
  const num = Number(value || 0);
  if (num >= 1024 * 1024) return `${(num / (1024 * 1024)).toFixed(1)} MB`;
  if (num >= 1024) return `${(num / 1024).toFixed(1)} KB`;
  return `${num} B`;
}

export default function KnowledgeBasesPage() {
  const t = useTranslate();
  const [items, setItems] = useState([]);
  const [status, setStatus] = useState({ message: "", tone: "info" });
  const [busy, setBusy] = useState(false);
  const [openModal, setOpenModal] = useState(false);
  const [openKbId, setOpenKbId] = useState("");
  const [page, setPage] = useState(1);

  const refresh = useCallback(async () => {
    try {
      const result = await api.knowledgeBases();
      setItems(result.data || []);
    } catch (error) {
      setStatus({ message: getErrorMessage(error), tone: "error" });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleDelete = useCallback(
    async (kb) => {
      if (!window.confirm(t("kb.confirm.delete", { name: kb.name }))) return;
      setBusy(true);
      try {
        await api.knowledgeBaseDelete(kb.kb_id);
        setStatus({ message: t("kb.deleted", { name: kb.name }), tone: "success" });
        await refresh();
      } catch (error) {
        setStatus({ message: getErrorMessage(error), tone: "error" });
      } finally {
        setBusy(false);
      }
    },
    [refresh, t]
  );

  if (openKbId) {
    return <KnowledgeBaseDetailPage kbId={openKbId} onBack={() => setOpenKbId("")} />;
  }

  const { pageItems, total, pageCount, page: safePage } = paginate(items, page);

  return (
    <section className="min-h-0 flex-1 overflow-auto px-6 py-6">
      <div className="mx-auto max-w-6xl space-y-4">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-zinc-950">{t("kb.title")}</h2>
            <p className="mt-1 text-xs text-zinc-500">{t("kb.subtitle")}</p>
          </div>
          <div className="flex gap-2">
            <button className="secondary-button" onClick={refresh} disabled={busy}>
              <RefreshCcw className="h-4 w-4" />
              {t("kb.action.refresh")}
            </button>
            <button className="primary-button" onClick={() => setOpenModal(true)} disabled={busy}>
              <Plus className="h-4 w-4" />
              {t("kb.action.new")}
            </button>
          </div>
        </header>

        {status.message ? (
          <div
            className={[
              "rounded-lg border px-3 py-2 text-sm",
              status.tone === "error"
                ? "border-rose-200 bg-rose-50/60 text-rose-700"
                : "border-emerald-200 bg-emerald-50/60 text-emerald-700",
            ].join(" ")}
          >
            {status.message}
          </div>
        ) : null}

        {!items.length ? (
          <EmptyState title={t("kb.empty")} />
        ) : (
          <div className="space-y-3">
            {pageItems.map((kb) => (
              <article key={kb.kb_id} className="section-panel p-4">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="mono-badge">{kb.kb_id}</span>
                      <span className="text-sm font-semibold text-zinc-950">{kb.name}</span>
                      <span className="rounded-full bg-zinc-100 px-2 py-0.5 text-[10px] font-semibold text-zinc-600">
                        {kb.source_type === "github" ? (
                          <span className="inline-flex items-center gap-1">
                            <Github className="h-3 w-3" />
                            github
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1">
                            <Upload className="h-3 w-3" />
                            local
                          </span>
                        )}
                      </span>
                    </div>
                    {kb.description ? (
                      <p className="mt-1 text-sm text-zinc-600">{kb.description}</p>
                    ) : null}
                    {kb.source_url ? (
                      <p className="mt-1 truncate text-xs text-zinc-500">{kb.source_url}</p>
                    ) : null}
                    <div className="mt-2 flex flex-wrap gap-3 text-xs text-zinc-500">
                      <span>{t("kb.field.files")}: <span className="font-mono">{kb.file_count}</span></span>
                      <span>{t("kb.field.size")}: <span className="font-mono">{formatBytes(kb.total_bytes)}</span></span>
                      <span>{t("kb.field.updated")}: {formatDate(kb.updated_at)}</span>
                      {kb.truncated ? (
                        <span className="text-amber-700">{t("kb.field.truncated")}</span>
                      ) : null}
                    </div>
                    {kb.import_error ? (
                      <p className="mt-2 text-xs text-rose-700">{kb.import_error}</p>
                    ) : null}
                  </div>
                  <div className="flex gap-2">
                    <button className="secondary-button" onClick={() => setOpenKbId(kb.kb_id)}>
                      <BookOpen className="h-4 w-4" />
                      {t("kb.action.open")}
                    </button>
                    <button
                      className="rounded-md border border-rose-200 bg-white px-3 py-1.5 text-xs font-semibold text-rose-700 hover:bg-rose-50"
                      onClick={() => handleDelete(kb)}
                      disabled={busy}
                    >
                      <Trash2 className="inline h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </article>
            ))}
            <Paginator page={safePage} pageCount={pageCount} total={total} onPage={setPage} />
          </div>
        )}
      </div>

      {openModal ? (
        <NewKbModal
          onClose={() => setOpenModal(false)}
          onDone={async (kb) => {
            setOpenModal(false);
            setStatus({ message: t("kb.created", { name: kb.name }), tone: "success" });
            await refresh();
          }}
        />
      ) : null}
    </section>
  );
}

function NewKbModal({ onClose, onDone }) {
  const t = useTranslate();
  const [mode, setMode] = useState("local");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [repoUrl, setRepoUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const submit = useCallback(async () => {
    setError("");
    if (!name.trim()) {
      setError(t("kb.error.name_required"));
      return;
    }
    setBusy(true);
    try {
      const create = await api.knowledgeBaseCreate({
        name: name.trim(),
        description: description.trim(),
        source_type: mode,
        source_url: mode === "github" ? repoUrl.trim() : "",
      });
      const kb = create.data;
      if (mode === "github") {
        if (!repoUrl.trim()) {
          setError(t("kb.error.repo_required"));
          await api.knowledgeBaseDelete(kb.kb_id);
          setBusy(false);
          return;
        }
        const imported = await api.knowledgeBaseImportGithub(kb.kb_id, {
          repo_url: repoUrl.trim(),
          branch: branch.trim(),
        });
        if (imported.data?.import_error) {
          setError(imported.data.import_error);
          setBusy(false);
          return;
        }
        await onDone(imported.data || kb);
      } else {
        if (files.length) {
          const fd = new FormData();
          files.forEach((file, idx) => {
            const key = `file${idx}`;
            fd.append(key, file, file.webkitRelativePath || file.name);
            if (file.webkitRelativePath) {
              fd.append(`path__${key}`, file.webkitRelativePath);
            }
          });
          await api.knowledgeBaseUpload(kb.kb_id, fd);
        }
        const refreshed = await api.knowledgeBase(kb.kb_id);
        await onDone(refreshed.data || kb);
      }
    } catch (caught) {
      setError(getErrorMessage(caught));
      setBusy(false);
    }
  }, [mode, name, description, repoUrl, branch, files, onDone, t]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/50 px-4">
      <div className="w-full max-w-lg rounded-xl border border-line bg-white p-5 shadow-xl">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold text-zinc-950">{t("kb.modal.title")}</h3>
            <p className="mt-1 text-xs text-zinc-500">{t("kb.modal.subtitle")}</p>
          </div>
          <button className="text-zinc-400 hover:text-zinc-700" onClick={onClose}>
            ✕
          </button>
        </div>

        <div className="mt-4 flex gap-1 rounded-md border border-line bg-zinc-50 p-1">
          {["local", "github"].map((value) => (
            <button
              key={value}
              className={[
                "flex-1 rounded-md px-3 py-1.5 text-xs font-semibold transition",
                mode === value ? "bg-white text-zinc-950 shadow-hairline" : "text-zinc-600",
              ].join(" ")}
              onClick={() => setMode(value)}
            >
              {t(`kb.modal.mode.${value}`)}
            </button>
          ))}
        </div>

        <div className="mt-4 space-y-3">
          <div>
            <label className="block text-xs font-semibold text-zinc-700">{t("kb.field.name")}</label>
            <input
              className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("kb.placeholder.name")}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-zinc-700">{t("kb.field.description")}</label>
            <textarea
              className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm"
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder={t("kb.placeholder.description")}
            />
          </div>

          {mode === "local" ? (
            <div>
              <label className="block text-xs font-semibold text-zinc-700">{t("kb.field.files")}</label>
              <input
                type="file"
                multiple
                className="mt-1 block w-full text-sm"
                onChange={(e) => setFiles(Array.from(e.target.files || []))}
              />
              <p className="mt-1 text-[11px] text-zinc-500">{t("kb.hint.local")}</p>
              {files.length ? (
                <p className="mt-1 text-xs text-zinc-600">{t("kb.hint.selected", { count: files.length })}</p>
              ) : null}
            </div>
          ) : (
            <>
              <div>
                <label className="block text-xs font-semibold text-zinc-700">{t("kb.field.repo_url")}</label>
                <input
                  className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm font-mono"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="https://github.com/owner/repo"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-zinc-700">{t("kb.field.branch")}</label>
                <input
                  className="mt-1 w-full rounded-md border border-line px-3 py-2 text-sm font-mono"
                  value={branch}
                  onChange={(e) => setBranch(e.target.value)}
                  placeholder="main"
                />
              </div>
            </>
          )}
        </div>

        {error ? <p className="mt-3 text-xs text-rose-700">{error}</p> : null}

        <div className="mt-5 flex justify-end gap-2">
          <button className="secondary-button" onClick={onClose} disabled={busy}>
            {t("kb.action.cancel")}
          </button>
          <button className="primary-button" onClick={submit} disabled={busy}>
            {busy ? t("kb.action.creating") : t("kb.action.create")}
          </button>
        </div>
      </div>
    </div>
  );
}
