function renderInline(text) {
  if (!text) return null;
  const tokens = [];
  let cursor = 0;
  const pattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*]+)\*\*|`([^`]+)`/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) {
      tokens.push({ type: "text", value: text.slice(cursor, match.index) });
    }
    if (match[1] && match[2]) {
      tokens.push({ type: "link", text: match[1], url: match[2] });
    } else if (match[3]) {
      tokens.push({ type: "bold", value: match[3] });
    } else if (match[4]) {
      tokens.push({ type: "code", value: match[4] });
    }
    cursor = pattern.lastIndex;
  }
  if (cursor < text.length) tokens.push({ type: "text", value: text.slice(cursor) });
  return tokens.map((token, idx) => {
    if (token.type === "link") {
      return (
        <a
          key={idx}
          href={token.url}
          target="_blank"
          rel="noreferrer noopener"
          className="text-appleBlue underline-offset-2 hover:underline break-all"
        >
          {token.text}
        </a>
      );
    }
    if (token.type === "bold") {
      return <strong key={idx} className="font-semibold text-zinc-950">{token.value}</strong>;
    }
    if (token.type === "code") {
      return <code key={idx} className="rounded bg-zinc-100 px-1 py-0.5 font-mono text-xs">{token.value}</code>;
    }
    return <span key={idx}>{token.value}</span>;
  });
}

export default function MarkdownText({ text }) {
  const lines = String(text || "").split("\n");
  let inFence = false;
  const out = [];
  let codeBuf = [];
  let codeLang = "";
  lines.forEach((line, index) => {
    const fenceMatch = line.match(/^```\s*([A-Za-z0-9_+\-]*)\s*$/);
    if (fenceMatch) {
      if (inFence) {
        out.push(
          <pre
            key={`code-${index}`}
            className="my-2 overflow-auto rounded-md bg-zinc-900 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-100"
          >
            {codeBuf.join("\n")}
          </pre>
        );
        codeBuf = [];
        codeLang = "";
        inFence = false;
      } else {
        inFence = true;
        codeLang = fenceMatch[1] || "";
      }
      return;
    }
    if (inFence) {
      codeBuf.push(line);
      return;
    }
    const imageStripped = line.replace(/!\[[^\]]*\]\([^)]*\)/g, "").trimEnd();
    if (line.startsWith("### ")) {
      out.push(<h4 key={index} className="pt-2 text-sm font-semibold text-zinc-900">{renderInline(line.slice(4))}</h4>);
      return;
    }
    if (line.startsWith("## ")) {
      out.push(<h3 key={index} className="pt-2 text-base font-semibold text-zinc-900">{renderInline(line.slice(3))}</h3>);
      return;
    }
    if (line.startsWith("# ")) {
      out.push(<h2 key={index} className="pt-1 text-lg font-semibold text-zinc-950">{renderInline(line.slice(2))}</h2>);
      return;
    }
    const bulletMatch = imageStripped.match(/^(\s*)([-*•])\s+(.*)$/);
    if (bulletMatch) {
      const indent = bulletMatch[1].length;
      out.push(
        <div
          key={index}
          className="flex gap-2 break-words"
          style={{ paddingLeft: `${indent * 0.5}rem` }}
        >
          <span className="select-none text-zinc-400">•</span>
          <span className="min-w-0 flex-1">{renderInline(bulletMatch[3])}</span>
        </div>
      );
      return;
    }
    if (!imageStripped.trim()) {
      out.push(<div key={index} className="h-1" />);
      return;
    }
    out.push(
      <p key={index} className="whitespace-pre-wrap break-words">
        {renderInline(imageStripped)}
      </p>
    );
  });
  if (inFence && codeBuf.length) {
    out.push(
      <pre key="code-tail" className="my-2 overflow-auto rounded-md bg-zinc-900 px-3 py-2 font-mono text-xs leading-relaxed text-zinc-100">
        {codeBuf.join("\n")}
      </pre>
    );
  }
  return <div className="space-y-1 text-sm leading-6">{out}</div>;
}
