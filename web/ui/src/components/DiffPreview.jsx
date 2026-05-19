export default function DiffPreview({ patch }) {
  const lines = (patch || "").split("\n");
  if (!patch) {
    return (
      <div className="rounded-lg bg-zinc-50 p-4 font-mono text-sm text-zinc-500">
        No diff preview available.
      </div>
    );
  }
  return (
    <div className="max-h-80 overflow-auto rounded-lg border border-line bg-zinc-50 font-mono text-xs leading-6">
      {lines.map((line, index) => {
        const add = line.startsWith("+") && !line.startsWith("+++");
        const del = line.startsWith("-") && !line.startsWith("---");
        const hunk = line.startsWith("@@");
        return (
          <div
            key={`${index}-${line}`}
            className={[
              "grid grid-cols-[3.5rem_1fr] px-3",
              add ? "bg-emerald-50 text-emerald-800" : "",
              del ? "bg-red-50 text-red-800" : "",
              hunk ? "bg-blue-50 text-blue-700" : "",
            ].join(" ")}
          >
            <span className="select-none pr-3 text-right text-zinc-400">{index + 1}</span>
            <span className="whitespace-pre-wrap break-words">{line || " "}</span>
          </div>
        );
      })}
    </div>
  );
}
