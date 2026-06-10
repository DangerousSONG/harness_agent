import { Inbox } from "lucide-react";

export default function EmptyState({ title, detail, icon: Icon = Inbox, action }) {
  return (
    <div className="flex min-h-48 items-center justify-center rounded-xl border border-dashed border-line bg-gradient-to-b from-white to-zinc-50/50 px-6 py-8 text-center">
      <div className="max-w-sm">
        <span className="mx-auto inline-flex h-10 w-10 items-center justify-center rounded-full border border-line bg-white text-zinc-400 shadow-hairline">
          <Icon className="h-5 w-5" />
        </span>
        <p className="mt-3 text-sm font-semibold text-zinc-900">{title}</p>
        {detail ? <p className="mt-1.5 text-sm leading-6 text-zinc-500">{detail}</p> : null}
        {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
      </div>
    </div>
  );
}
