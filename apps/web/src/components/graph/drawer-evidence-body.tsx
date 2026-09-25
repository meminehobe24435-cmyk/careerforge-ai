'use client';

import { Badge } from '@careerforge/ui';

import type {
  EvidenceDetail,
  EvidenceGraphEdge,
  EvidenceGraphNode,
  EvidenceTrace,
} from '@/lib/graph-api';

import {
  CompactList,
  ConfidenceLine,
  DrawerSection,
  FactRow,
  NodeLink,
  RelationList,
  Unavailable,
} from './drawer-parts';
import {
  CONFIDENCE_WEIGHTS,
  authorityFor,
  excerptOf,
  formatTimestamp,
  kindLabel,
  sourceOf,
} from './graph-evidence';
import type { DrawerRelations } from './graph-model';

/**
 * The evidence drawer: source, excerpt, place, time, confidence — and why it counts.
 *
 * Three deliberate limits:
 *
 * * **The excerpt is clipped** (~420 characters, with the full length stated). A repository file
 *   can be thousands of lines; a drawer is not a file viewer, and "here is the paragraph the node
 *   is about, and how much was left out" is checkable while a wall of text is not.
 * * **A missing timestamp says "not recorded"**, because the evidence engine genuinely leaves
 *   `occurred_at` empty for undated material, and `1970-01-01` would be a fabrication.
 * * **The factor table is the arithmetic, not a story.** Each factor's value is printed with the
 *   weight `confidence@1.0.0` applies to it, so the reader can add the column up themselves and
 *   compare it with the stored score.
 */
export interface EvidenceDrawerBodyProps {
  node: EvidenceGraphNode;
  relations: DrawerRelations;
  edges: EvidenceGraphEdge[];
  labels: Map<string, EvidenceGraphNode>;
  detail: EvidenceDetail | null;
  detailState: 'pending' | 'ready' | 'unavailable';
  trace: EvidenceTrace | null;
  traceState: 'pending' | 'ready' | 'unavailable';
  onSelect: (id: string) => void;
}

function confidenceTotal(detail: EvidenceDetail | null): number | null {
  if (!detail?.factors) return null;
  return CONFIDENCE_WEIGHTS.reduce(
    (total, factor) => total + detail.factors![factor.key] * factor.weight,
    0,
  );
}

export function EvidenceDrawerBody({
  node,
  relations,
  edges,
  labels,
  detail,
  detailState,
  trace,
  traceState,
  onSelect,
}: EvidenceDrawerBodyProps) {
  const kind = String(node.meta?.['kind'] ?? detail?.kind ?? node.type);
  const tier = authorityFor(kind);
  const snippet =
    detail?.snippet ?? (typeof node.meta?.['snippet'] === 'string' ? node.meta['snippet'] : '');
  const excerpt = excerptOf(snippet);
  const total = confidenceTotal(detail);
  const factors = detail?.factors ?? null;
  const stored = detail?.confidence ?? node.confidence;

  return (
    <>
      <DrawerSection title="Source">
        <dl className="flex flex-col gap-1.5">
          <FactRow label="Source type">
            <Badge variant="outline">{kindLabel(kind)}</Badge>
          </FactRow>
          <FactRow label="Source" mono>
            {sourceOf(node, detail)}
          </FactRow>
          <FactRow label="Authority tier" mono>
            {tier ? (
              `${tier.tier} · ${tier.score.toFixed(2)}`
            ) : (
              <Unavailable>tier not mapped</Unavailable>
            )}
          </FactRow>
          <FactRow label="Recorded">
            {formatTimestamp(detail?.occurredAt) ?? (
              <Unavailable>not recorded — the source carries no date</Unavailable>
            )}
          </FactRow>
        </dl>
      </DrawerSection>

      <DrawerSection
        title="Excerpt"
        hint={
          detailState === 'pending'
            ? 'Reading the stored text…'
            : excerpt.truncated
              ? `Truncated at 420 characters of ${excerpt.fullLength}. The stored record holds the whole excerpt.`
              : excerpt.text.length > 0
                ? `${excerpt.fullLength} characters, shown in full.`
                : undefined
        }
      >
        {excerpt.text.length > 0 ? (
          <pre className="border-subtle bg-base text-secondary max-h-40 overflow-y-auto whitespace-pre-wrap break-words rounded-md border p-2 font-mono text-[11px] leading-relaxed">
            {excerpt.text}
          </pre>
        ) : detailState === 'unavailable' ? (
          <p className="text-tertiary text-[11px]">
            Excerpt unavailable — GET /evidence/{'{id}'} did not return for this item.
          </p>
        ) : (
          <p className="text-tertiary text-[11px]">
            <Unavailable>the stored record holds no text for this item</Unavailable>
          </p>
        )}
      </DrawerSection>

      <DrawerSection title="Place in the graph">
        <dl className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-tertiary text-[11px]">Project</dt>
            <dd className="min-w-0 text-right">
              {relations.projects.length > 0 ? (
                <span className="text-primary text-[11px]">
                  {relations.projects.map((project) => project.label).join(', ')}
                </span>
              ) : (
                <Unavailable>no project in this view reaches it</Unavailable>
              )}
            </dd>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <dt className="text-tertiary text-[11px]">Repository</dt>
            <dd className="min-w-0 text-right">
              {relations.repositories.length > 0 ? (
                <span className="text-primary text-[11px]">
                  {relations.repositories.map((repo) => repo.label).join(', ')}
                </span>
              ) : (
                <Unavailable>no repository in this view</Unavailable>
              )}
            </dd>
          </div>
          <FactRow label="Confidence">
            <ConfidenceLine value={stored} />
          </FactRow>
        </dl>
      </DrawerSection>

      <DrawerSection
        title="Confidence breakdown"
        hint={
          factors
            ? `${factors.formulaVersion} — weight × factor, added up.`
            : 'The five factors come back on GET /evidence/{id}.'
        }
      >
        {factors ? (
          <div className="border-subtle bg-base overflow-hidden rounded-md border">
            <table className="w-full text-left font-mono text-[10px] tabular-nums">
              <thead>
                <tr className="text-tertiary border-subtle border-b">
                  <th scope="col" className="px-2 py-1 font-normal">
                    factor
                  </th>
                  <th scope="col" className="px-2 py-1 text-right font-normal">
                    value
                  </th>
                  <th scope="col" className="px-2 py-1 text-right font-normal">
                    weight
                  </th>
                  <th scope="col" className="px-2 py-1 text-right font-normal">
                    adds
                  </th>
                </tr>
              </thead>
              <tbody className="text-secondary">
                {CONFIDENCE_WEIGHTS.map((factor) => (
                  <tr key={factor.key} className="border-subtle border-t">
                    <th scope="row" className="px-2 py-1 text-left font-normal">
                      {factor.label}
                    </th>
                    <td className="px-2 py-1 text-right">{factors[factor.key].toFixed(2)}</td>
                    <td className="text-tertiary px-2 py-1 text-right">
                      {factor.weight.toFixed(2)}
                    </td>
                    <td className="px-2 py-1 text-right">
                      {(factors[factor.key] * factor.weight).toFixed(3)}
                    </td>
                  </tr>
                ))}
                <tr className="border-subtle border-t">
                  <th scope="row" className="px-2 py-1 text-left font-normal">
                    Sum
                  </th>
                  <td className="px-2 py-1" />
                  <td className="px-2 py-1" />
                  <td className="text-primary px-2 py-1 text-right">
                    {total === null ? '—' : total.toFixed(3)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-tertiary text-[11px]">
            {detailState === 'pending'
              ? 'Reading the factors…'
              : 'No breakdown was returned for this item.'}
          </p>
        )}
        {factors ? (
          <dl className="mt-2 flex flex-col gap-1.5">
            <FactRow label="Stored confidence" mono>
              {stored === null ? '—' : stored.toFixed(3)}
            </FactRow>
            <FactRow label="Recomputed by the formula" mono>
              {factors.recomputed.toFixed(3)}
            </FactRow>
            <FactRow label="Independent sources" mono>
              {factors.corroborationSources}
            </FactRow>
            {stored !== null && Math.abs(factors.recomputed - stored) > 0.0005 ? (
              <p className="text-danger text-[11px]">
                Stored and recomputed disagree by {Math.abs(factors.recomputed - stored).toFixed(3)}
                . The database constraint that enforces the formula should make this impossible —
                treat the stored row as suspect.
              </p>
            ) : null}
          </dl>
        ) : null}
      </DrawerSection>

      <DrawerSection
        title="Cited by"
        hint={
          traceState === 'pending'
            ? 'Reading reverse provenance…'
            : 'Every link that points at this item: what rests on it.'
        }
      >
        {traceState === 'unavailable' ? (
          <p className="text-tertiary text-[11px]">
            Reverse provenance unavailable — GET /evidence/{'{id}'}/trace did not return.
          </p>
        ) : trace && trace.citedBy.length > 0 ? (
          <ul className="flex flex-col gap-1">
            {trace.citedBy.map((entry) => (
              <li key={`${entry.relation}-${entry.fromId}`} className="flex flex-col gap-0.5">
                <span className="flex items-baseline gap-2">
                  <span className="text-secondary font-mono text-[10px] uppercase tracking-wide">
                    {entry.relation}
                  </span>
                  <button
                    type="button"
                    onClick={() => onSelect(entry.fromId)}
                    className="text-primary min-w-0 truncate text-left text-[11px] underline-offset-4 hover:underline"
                  >
                    {labels.get(entry.fromId)?.label ??
                      `${entry.fromType}:${entry.fromId.slice(0, 8)}`}
                  </button>
                </span>
                {entry.rationale ? (
                  <span className="text-tertiary text-[10px]">{entry.rationale}</span>
                ) : null}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-tertiary text-[11px]">
            No skill or claim cites this item directly. That is a real state, not an error: the item
            is stored evidence that nothing in the current graph has been built on yet.
          </p>
        )}
      </DrawerSection>

      <DrawerSection title="Supports">
        <CompactList
          items={relations.skills}
          empty="No skill in this view is supported by it."
          render={(skill) => <NodeLink node={skill} onSelect={onSelect} />}
        />
      </DrawerSection>

      <DrawerSection title="Relations">
        <RelationList nodeId={node.id} edges={edges} labels={labels} onSelect={onSelect} />
      </DrawerSection>
    </>
  );
}
