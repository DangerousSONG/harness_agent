export default function DiffPreview({ patch }) {
  const lines = (patch || "").split("\n");
  if (!patch) {
    return (
      <div className="rounded-lg border border-line bg-zinc-50 p-4 font-mono text-sm text-zinc-500">
        No diff preview available.
      </div>
    );
  }
  return (
    <div className="max-h-[30rem] overflow-auto rounded-lg border border-zinc-200 bg-[#fbfcfd] font-mono text-[12px] leading-6 shadow-inner">
      {lines.map((line, index) => {
        const add = line.startsWith("+") && !line.startsWith("+++");
        const del = line.startsWith("-") && !line.startsWith("---");
        const hunk = line.startsWith("@@");
        const file = line.startsWith("+++") || line.startsWith("---");
        return (
          <div
            key={`${index}-${line}`}
            className={[
              "grid grid-cols-[3.75rem_1fr] border-l-4 px-0",
              add ? "border-emerald-500 bg-emerald-50 text-emerald-900" : "",
              del ? "border-red-500 bg-red-50 text-red-900" : "",
              hunk ? "border-blue-500 bg-blue-50 text-blue-800" : "",
              file ? "border-zinc-400 bg-zinc-100 text-zinc-700" : "",
              !add && !del && !hunk && !file ? "border-transparent text-zinc-700" : "",
            ].join(" ")}
          >
            <span className="select-none border-r border-zinc-200 bg-white/55 pr-3 text-right text-zinc-400">{index + 1}</span>
            <span className="whitespace-pre-wrap break-words px-3">{line || " "}</span>
          </div>
        );
      })}
    </div>
  );
}
