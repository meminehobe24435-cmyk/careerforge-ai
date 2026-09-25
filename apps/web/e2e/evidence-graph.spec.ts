import { RESUME } from './helpers/dataset';
import { expect, test } from './helpers/fixtures';

/**
 * E2E 3 · The evidence graph, and the one click-to-expand panel that ships.
 *
 * Two facts shape this spec, and both are stated here rather than hidden behind a skip:
 *
 * 1. **`/app/evidence-graph` does not exist.** `nav-config.ts` badges it `PHASE 6` and renders it
 *    as a non-clickable item. There is no canvas in this app, so "click a skill node on the graph"
 *    cannot be automated against a page that is not there.
 * 2. **The evidence *is* real and populated.** Uploading a résumé through `POST /documents`,
 *    letting the in-process worker ingest it and then calling `POST /documents/{id}/analyze` builds
 *    evidence, skill nodes and edges. The first test below proves that against the live API and
 *    fails loudly if the graph comes back empty — it is not allowed to pass on nothing.
 *
 * The second test drives the only click-to-expand evidence UI in the product: the public candidate
 * page (`/candidate/[slug]`), which renders each evidence-backed skill as an `aria-expanded` button
 * and fetches that skill's citations when it is opened. That page is a server component, so the
 * spec also exercises the unauthenticated read path and the publish workflow behind it.
 *
 * What it cannot show, and why — measured, not assumed: a citation is only published when its kind
 * is `repo_file`, `commit` or `readme` (`careerforge_ai/agents/recruiter.py` → `_LINKABLE_KINDS`),
 * because only those have a URL a stranger can open. Those kinds come from GitHub ingestion, and
 * this build has no `/github` router at all (`careerforge_api/routers/` has no `github.py`), so
 * with a locally uploaded résumé the panel opens, reports the skill's own confidence and
 * corroboration, and says in words that there is no citation it is allowed to publish. The spec
 * asserts whichever of those two states is true, and asserts the *empty* state exactly when the
 * API returns an empty citation list.
 */
test.describe('Evidence graph', () => {
  test('the demo account can be given a populated evidence graph', async ({ api }) => {
    const { documentId, analysis } = await api.ensureEvidence(RESUME);

    expect(documentId.length).toBeGreaterThan(0);
    // Fails loudly if document analysis produced nothing: the rest of this file would be
    // meaningless without evidence behind the skills.
    expect(
      analysis.evidenceCreated + analysis.evidenceUpdated,
      'POST /documents/{id}/analyze must create evidence for the fixture résumé',
    ).toBeGreaterThan(0);
    expect(analysis.skillCount).toBeGreaterThan(0);
    expect(analysis.meanConfidence).toBeGreaterThan(0);

    const graph = await api.evidenceGraph('?depth=2');
    expect(graph.nodeCount).toBeGreaterThan(1);
    expect(graph.edgeCount).toBeGreaterThan(1);

    const skillNodes = graph.nodes.filter((node) => node.type === 'skill');
    expect(skillNodes.length, 'the graph must contain skill nodes to click').toBeGreaterThan(0);
    const relations = new Set(graph.edges.map((edge) => edge.relation));
    expect(relations.has('DEMONSTRATES')).toBe(true);
    expect(relations.has('EVIDENCED_BY')).toBe(true);
    // Every edge points at a node that is actually in the payload — a dangling edge draws nothing.
    const nodeIds = new Set(graph.nodes.map((node) => node.id));
    for (const edge of graph.edges) {
      expect(
        nodeIds.has(edge.source) && nodeIds.has(edge.target),
        `edge ${edge.id} is not resolvable`,
      ).toBe(true);
    }

    // The evidence rows behind those nodes carry the title, the kind (the source) and the
    // server-computed confidence that the panel is supposed to display.
    const evidence = await api.evidenceList();
    expect(evidence.total).toBeGreaterThan(0);
    const row = evidence.items[0];
    if (!row) throw new Error('GET /evidence returned total > 0 but no items');
    expect(row.title.length).toBeGreaterThan(0);
    expect(row.kind).toBe('document_chunk');
    expect(row.confidence).toBeGreaterThan(0);
    expect(row.factors?.recomputed).toBeCloseTo(row.confidence, 3);
  });

  test('clicking a skill opens the evidence panel and it states what it can show', async ({
    api,
    signedInPage: page,
  }) => {
    await api.ensureEvidence(RESUME);
    const slug = await api.publish();

    const candidate = await api.publicCandidate(slug);
    expect(
      candidate.skills.length,
      'the published page must list evidence-backed skills',
    ).toBeGreaterThan(0);
    const skill =
      candidate.skills.find((item) => item.canonicalId === 'stm32') ??
      candidate.skills.find((item) => item.evidenceCount > 0);
    if (!skill)
      throw new Error('no published skill carries evidence, so there is nothing to expand');

    await page.goto(`/candidate/${slug}`);
    await expect(
      page.getByRole('heading', { level: 1, name: candidate.displayName }),
    ).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Evidence-backed Skills' })).toBeVisible();

    // The skill is a chip button that announces its own expanded state.
    const chip = page.getByRole('button', { name: skill.displayName });
    await expect(chip).toBeVisible();
    await expect(chip).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByTestId('evidence-panel')).toHaveCount(0);

    await chip.click();

    await expect(chip).toHaveAttribute('aria-expanded', 'true');
    const panel = page.getByTestId('evidence-panel');
    await expect(panel).toBeVisible();

    // The node itself: name, category, and the confidence the graph stores for it.
    await expect(panel.getByRole('heading', { level: 3, name: skill.displayName })).toBeVisible();
    await expect(panel.getByText(skill.category, { exact: true })).toBeVisible();
    await expect(
      panel.getByText(
        new RegExp(
          `置信度 ${Math.round(skill.confidence * 100)}% · ${skill.corroboration} 个独立来源`,
        ),
      ),
    ).toBeVisible();

    // The citations. Which state is correct is decided by the API, not by the spec.
    const citations = await api.publicSkillEvidence(slug, skill.canonicalId);
    if (citations.length > 0) {
      for (const citation of citations) {
        await expect(panel.getByText(citation.title, { exact: true })).toBeVisible();
        await expect(panel.getByText(new RegExp(`^${citation.kind}`))).toBeVisible();
        await expect(
          panel.getByText(new RegExp(`置信度 ${Math.round(citation.confidence * 100)}%`)),
        ).toBeVisible();
      }
    } else {
      // A published page with zero citations is the documented outcome for locally uploaded
      // material: `_LINKABLE_KINDS` is {repo_file, commit, readme} and none of those can be
      // produced without GitHub ingestion, which this build does not ship.
      expect(citations).toEqual([]);
      await expect(panel.getByText(/没有可公开的引用/)).toBeVisible();
    }
  });
});
