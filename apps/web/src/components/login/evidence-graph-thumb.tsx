/**
 * CSS-drawn stand-in for the Evidence Graph panel shown on the login screen
 * (docs/UI.md §5.2 asks for a rendered thumbnail there).
 *
 * No bitmap is shipped yet, so this draws the documented node/edge structure with tokens
 * and labels itself as a placeholder — the real capture lands in PHASE 14.
 */
export function EvidenceGraphThumb() {
  const nodes = [
    { label: 'alexchen', type: 'candidate' },
    { label: 'Balance Robot', type: 'project' },
    { label: 'freertos.c', type: 'repo_file' },
    { label: 'FreeRTOS', type: 'skill' },
    { label: '基于 FreeRTOS 的实时控制', type: 'claim' },
  ];

  return (
    <div className="border-default bg-surface overflow-hidden rounded-lg border">
      {/* TODO(phase-14): replace with docs/assets/screenshots/evidence-graph.gif */}
      <div className="border-subtle bg-elevated flex items-center justify-between border-b px-3 py-2">
        <span className="text-tertiary font-mono text-[11px]">/app/evidence-graph</span>
        <span className="text-tertiary font-mono text-[10px] uppercase tracking-wider">
          placeholder
        </span>
      </div>
      <div className="bg-grid flex flex-col gap-3 p-4">
        {nodes.map((node, index) => (
          <div key={node.label} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="bg-brand size-1.5 shrink-0 rounded-full"
              style={{ marginLeft: `${index * 10}px` }}
            />
            <span className="border-default bg-base text-secondary truncate rounded-sm border px-2 py-1 text-[11px]">
              {node.label}
            </span>
            <span className="text-tertiary font-mono text-[10px]">{node.type}</span>
            <span className="text-tertiary ml-auto font-mono text-[10px] tabular-nums">
              {(0.97 - index * 0.04).toFixed(2)}
            </span>
          </div>
        ))}
        <p className="border-subtle text-tertiary border-t pt-2 text-[11px]">
          证据图谱缩略图占位：真实截图（docs/assets/screenshots/evidence-graph.gif）将在 PHASE 14
          生成。
        </p>
      </div>
    </div>
  );
}
