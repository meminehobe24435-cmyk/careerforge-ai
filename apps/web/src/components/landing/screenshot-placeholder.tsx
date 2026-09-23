import { cn } from '@/lib/utils';

export interface ScreenshotPlaceholderProps {
  /** What the future screenshot shows, e.g. `Dashboard 全貌（1440）`. */
  label: string;
  /** Route the screenshot will be taken from, shown mono in the fake browser bar. */
  route: string;
  /** File the screenshot will live at, e.g. `docs/assets/screenshots/dashboard.png`. */
  target: string;
  className?: string;
  /** Draw the dashboard-ish wireframe inside the frame. */
  wireframe?: 'dashboard' | 'graph' | 'diff' | 'none';
}

/**
 * CSS-drawn placeholder for a screenshot that does not exist yet.
 *
 * docs/assets/screenshots/ is empty in PHASE 1, so this component deliberately draws a
 * wireframe and labels itself — nothing here pretends to be a real product screenshot.
 */
export function ScreenshotPlaceholder({
  label,
  route,
  target,
  className,
  wireframe = 'dashboard',
}: ScreenshotPlaceholderProps) {
  return (
    <figure className={cn('flex flex-col gap-3', className)}>
      <div className="border-default bg-surface overflow-hidden rounded-lg border shadow-lg">
        <div className="border-subtle bg-elevated flex items-center gap-2 border-b px-3 py-2">
          <span className="flex gap-1.5" aria-hidden="true">
            <span className="bg-active size-2 rounded-full" />
            <span className="bg-active size-2 rounded-full" />
            <span className="bg-active size-2 rounded-full" />
          </span>
          <span className="text-tertiary ml-1 truncate font-mono text-[11px]">
            localhost:3000{route}
          </span>
        </div>

        <div className="bg-grid relative min-h-56 p-4 sm:min-h-72">
          {/* TODO(phase-14): replace with docs/assets/screenshots/dashboard.png */}
          <div className="flex h-full min-h-48 flex-col gap-3">
            {wireframe === 'dashboard' ? (
              <>
                <div className="flex gap-2">
                  <span className="bg-hover h-3 w-24 rounded-sm" />
                  <span className="bg-hover ml-auto h-3 w-32 rounded-sm" />
                </div>
                <span className="border-default bg-surface h-20 rounded-md border" />
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <span
                      key={index}
                      className="border-default bg-surface h-12 rounded-md border"
                    />
                  ))}
                </div>
                <span className="border-default bg-surface h-24 rounded-md border" />
              </>
            ) : null}

            {wireframe === 'graph' ? (
              <>
                <div className="flex flex-1 gap-3">
                  <span className="border-default bg-surface flex-1 rounded-md border" />
                  <span className="border-default bg-surface w-40 rounded-md border" />
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {['candidate', 'project', 'skill', 'repo_file', 'claim'].map((node) => (
                    <span
                      key={node}
                      className="border-default bg-surface text-tertiary rounded-sm border px-2 py-1 font-mono text-[10px]"
                    >
                      {node}
                    </span>
                  ))}
                </div>
              </>
            ) : null}

            {wireframe === 'diff' ? (
              <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
                <span className="border-default bg-surface rounded-md border" />
                <span className="border-default bg-surface rounded-md border" />
              </div>
            ) : null}

            {wireframe === 'none' ? <span className="flex-1" /> : null}

            <figcaption className="flex flex-col gap-1 pt-1">
              <span className="text-tertiary font-mono text-[11px] uppercase tracking-wider">
                screenshot placeholder
              </span>
              <span className="text-secondary text-xs">{label}</span>
              <span className="text-tertiary font-mono text-[11px]">{target}</span>
            </figcaption>
          </div>
        </div>
      </div>
    </figure>
  );
}
