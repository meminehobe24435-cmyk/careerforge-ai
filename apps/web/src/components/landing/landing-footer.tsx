const FOOTER_LINKS = [
  // TODO(phase-14): point these at the real documentation/site URLs.
  { label: 'Architecture', href: '#' },
  { label: 'API', href: '#' },
  { label: 'Interview Guide', href: '#' },
  { label: 'GitHub', href: '#' },
  { label: 'License (MIT)', href: '#' },
];

/** Landing footer (docs/UI.md §5.1) + the closing line from the README. */
export function LandingFooter() {
  return (
    <footer className="border-subtle bg-surface border-t">
      <div className="mx-auto w-full max-w-6xl px-4 py-14 sm:px-6 sm:py-20">
        <p className="text-primary max-w-3xl text-lg font-semibold leading-snug tracking-tight sm:text-2xl">
          Most resumes describe what you <span className="text-tertiary">claim</span> to know.
          <br />
          CareerForge shows the <span className="text-gradient-brand">evidence</span>.
        </p>
        <p className="text-secondary mt-3 text-xs leading-relaxed">
          大多数简历告诉别人你会什么，CareerForge 告诉别人你凭什么这么写。
        </p>

        <div className="border-subtle mt-10 flex flex-col gap-6 border-t pt-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className="border-default bg-brand/10 text-brand flex size-7 items-center justify-center rounded-md border font-mono text-[10px] font-semibold"
            >
              CF
            </span>
            <span className="text-tertiary font-mono text-[11px]">
              CareerForge AI · PHASE 1 scaffold
            </span>
          </div>

          <nav aria-label="页脚导航">
            <ul className="flex flex-wrap gap-x-5 gap-y-2">
              {FOOTER_LINKS.map((link) => (
                <li key={link.label}>
                  <a
                    href={link.href}
                    className="text-secondary hover:text-primary focus-visible:outline-brand rounded-sm text-xs underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        <p className="text-tertiary mt-6 font-mono text-[11px]">
          本页所有产品截图均为 CSS 绘制的占位框，真实截图在 PHASE 14 由 Demo 账号产出后替换。
        </p>
      </div>
    </footer>
  );
}
