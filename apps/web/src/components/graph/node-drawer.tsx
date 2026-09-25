'use client';

import {
  Badge,
  Button,
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
  IconButton,
  cn,
} from '@careerforge/ui';
import { Crosshair, X } from 'lucide-react';
import { useEffect } from 'react';

import type {
  EvidenceDetail,
  EvidenceGraphEdge,
  EvidenceGraphNode,
  EvidenceTrace,
  ProfileSkill,
} from '@/lib/graph-api';

import { EvidenceDrawerBody } from './drawer-evidence-body';
import { EntityDrawerBody } from './drawer-entity-body';
import { SkillDrawerBody } from './drawer-skill-body';
import type { DrawerRelations } from './graph-model';
import { formatConfidence, nodeStyle, type NodeFacts, type NodeReadout } from './graph-node-style';

/**
 * The node drawer.
 *
 * Desktop: a right-hand panel over the canvas. Mobile: a bottom sheet. Both are the *same* Radix
 * dialog with different geometry, so the accessible behaviour — focus moved in, focus trapped,
 * Escape closes, name announced — is identical on both widths instead of being re-implemented for
 * the narrow layout.
 *
 * The reader is always one click from the evidence: a skill drawer lists its sources, an evidence
 * drawer lists the skills that rest on it, and both are buttons that move the selection. That is
 * the chain the product is about, and a drawer is where it becomes walkable.
 */
export interface NodeDrawerProps {
  node: EvidenceGraphNode | null;
  facts: NodeFacts | null;
  readout: NodeReadout | null;
  relations: DrawerRelations | null;
  edges: EvidenceGraphEdge[];
  labels: Map<string, EvidenceGraphNode>;
  declaredSkill: ProfileSkill | null;
  profileState: 'pending' | 'ready' | 'unavailable';
  detail: EvidenceDetail | null;
  detailState: 'pending' | 'ready' | 'unavailable';
  trace: EvidenceTrace | null;
  traceState: 'pending' | 'ready' | 'unavailable';
  /** Forces the API to re-scope the canvas to this node (`?focus=`). */
  onFocusNode: (node: EvidenceGraphNode) => void;
  onSelect: (id: string) => void;
  onClose: () => void;
}

const DRAWER_CLASS = cn(
  // Narrow first: every width gets a sheet anchored to the bottom edge, and ≥1024px turns the same
  // element into a right-hand panel. `!` because the primitive's own geometry has to be displaced,
  // and Tailwind's important suffix is order-independent — relying on class order here is how a
  // drawer ends up centred on top of the canvas in production and fine in a screenshot.
  'w-full! max-w-none! left-0! right-0! top-auto! bottom-0! translate-x-0! translate-y-0!',
  'max-h-[85dvh]! rounded-t-lg! rounded-b-none! border-x-0! border-b-0! p-0',
  'lg:left-auto! lg:right-0! lg:top-0! lg:bottom-0! lg:h-dvh! lg:max-h-dvh! lg:w-[26rem]!',
  'lg:rounded-none! lg:rounded-l-lg! lg:border-y-0! lg:border-r-0!',
  'data-[state=open]:animate-drawer-in!',
);

export function NodeDrawer(props: NodeDrawerProps) {
  const {
    node,
    facts,
    readout,
    relations,
    edges,
    labels,
    declaredSkill,
    profileState,
    detail,
    detailState,
    trace,
    traceState,
    onFocusNode,
    onSelect,
    onClose,
  } = props;

  // Radix closes on Escape while focus is inside the dialog; this listener covers the case where
  // the drawer was opened by a click on the node list and focus never left it. `defaultPrevented`
  // is the courtesy that lets the "How to read" popover consume its own Escape.
  useEffect(() => {
    if (!node) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key !== 'Escape' || event.defaultPrevented) return;
      onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [node, onClose]);

  if (!node) return null;

  const style = nodeStyle(node.type);
  const group = style.group;
  const body =
    group === 'skill' && facts && readout && relations ? (
      <SkillDrawerBody
        node={node}
        facts={facts}
        relations={relations}
        edges={edges}
        labels={labels}
        declared={declaredSkill}
        profileState={profileState}
        onSelect={onSelect}
      />
    ) : (group === 'evidence' || group === 'claim') && facts && readout && relations ? (
      <EvidenceDrawerBody
        node={node}
        relations={relations}
        edges={edges}
        labels={labels}
        detail={detail}
        detailState={detailState}
        trace={trace}
        traceState={traceState}
        onSelect={onSelect}
      />
    ) : facts && readout && relations ? (
      <EntityDrawerBody
        node={node}
        style={style}
        facts={facts}
        relations={relations}
        edges={edges}
        labels={labels}
        onSelect={onSelect}
      />
    ) : null;

  return (
    <Dialog open modal={false} onOpenChange={(next) => (next ? undefined : onClose())}>
      <DialogContent
        hideClose
        aria-describedby={undefined}
        className={DRAWER_CLASS}
        style={{ zIndex: 'var(--z-drawer)' }}
        // A drawer that explains a node is not a modal: the graph behind it is the thing being
        // explained, so it keeps its contrast and stays clickable — clicking another node moves the
        // selection and the panel follows. The overlay element is still rendered by the primitive,
        // so it is made invisible and transparent to pointers rather than removed; the scrim that
        // belongs on the navigation drawer would dim the evidence the reader is trying to read.
        overlayClassName="pointer-events-none bg-transparent"
        overlayStyle={{ zIndex: 'var(--z-drawer)' }}
        onPointerDownOutside={(event) => event.preventDefault()}
        onInteractOutside={(event) => event.preventDefault()}
        data-testid="node-drawer"
      >
        <DialogHeader className="flex-row items-start gap-3 pr-3">
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-tertiary flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em]">
              {style.label}
              {node.confidence !== null ? (
                <Badge variant="outline" className="tracking-normal">
                  conf {formatConfidence(node.confidence)}
                </Badge>
              ) : null}
            </span>
            <DialogTitle className="text-primary min-w-0 break-words text-sm">
              {node.label}
            </DialogTitle>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onFocusNode(node)}
              aria-label={`Focus the graph on ${node.label}`}
              title="Re-read the graph with this node at its centre"
            >
              <Crosshair className="size-3.5" aria-hidden="true" />
              Focus
            </Button>
            <IconButton aria-label="Close details" onClick={onClose}>
              <X className="size-4" />
            </IconButton>
          </div>
        </DialogHeader>

        <DialogBody className="flex flex-col gap-4">
          {body}
          <p className="text-tertiary border-subtle border-t pt-3 font-mono text-[10px] leading-relaxed">
            The address bar holds the selection ({group === 'skill' ? '?skill=' : '?node='}
            {group === 'skill' ? (node.group ?? node.id.slice(0, 8)) : node.id.slice(0, 8)}
            …), so a refresh and a shared link open this same node.
          </p>
        </DialogBody>
      </DialogContent>
    </Dialog>
  );
}
