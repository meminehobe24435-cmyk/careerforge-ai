import { CapabilityGrid } from '@/components/landing/capability-grid';
import { ComparisonSection } from '@/components/landing/comparison-section';
import { LandingFooter } from '@/components/landing/landing-footer';
import { LandingHero } from '@/components/landing/landing-hero';
import { SiteHeader } from '@/components/landing/site-header';
import { TechSection } from '@/components/landing/tech-section';

/**
 * Landing page (docs/UI.md §5.1).
 *
 * A Server Component: no client JS is shipped for the marketing copy, only for the
 * interactive islands (theme toggle, buttons).
 */
export default function LandingPage() {
  return (
    <>
      <SiteHeader />
      <main id="main">
        <LandingHero />
        <CapabilityGrid />
        <ComparisonSection />
        <TechSection />
      </main>
      <LandingFooter />
    </>
  );
}
