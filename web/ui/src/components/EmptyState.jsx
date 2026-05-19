export default function EmptyState({ title, detail }) {
  return (
    <div className="flex min-h-48 items-center justify-center rounded-lg border border-dashed border-line bg-white/70 px-6 text-center">
      <div>
        <p className="text-sm font-semibold text-zinc-900">{title}</p>
        {detail ? <p className="mt-2 text-sm text-zinc-500">{detail}</p> : null}
      </div>
    </div>
  );
}
