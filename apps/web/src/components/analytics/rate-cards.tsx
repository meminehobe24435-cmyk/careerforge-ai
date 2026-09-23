'use client';

import { Badge, Card, CardContent, CardHeader, CardTitle, cn } from '@careerforge/ui';
import type { AnalyticsMeta, RateCard } from '@careerforge/shared';

import { formatInterval, formatRate, insufficientNote } from '@/lib/analytics-format';

interface RateCardsProps {
  cards: RateCard[];
  meta: AnalyticsMeta;
}

/**
 * The headline ratios (FR-14.2).
 *
 * Every card shows its counts and its interval, and says "样本不足" when the sample does not
 * support a rate. That is not modesty — a dashboard that prints "Interview Rate 100%" for a
 * candidate with one interview is a dashboard that has taught them something false, and this
 * product's entire claim is that it does not do that.
 */
export function RateCards({ cards, meta }: RateCardsProps) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
      {cards.map((card) => {
        const note = insufficientNote(card);
        const empty = card.denominator === 0;
        return (
          <Card key={card.key} className={cn('min-w-0', note && 'border-signal/30')}>
            <CardHeader className="pb-2">
              <CardTitle className="text-secondary text-xs font-medium">{card.label}</CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col gap-1.5">
              <p className="text-primary text-2xl font-semibold tabular-nums">
                {formatRate(card.rate)}
              </p>
              <p className="text-tertiary font-mono text-[11px]">
                {card.numerator} / {card.denominator}
                {empty ? '' : ` · ${formatInterval(card)}`}
              </p>
              {note ? <Badge variant="signal">{note}</Badge> : null}
              <p className="text-tertiary text-[11px] leading-relaxed">{card.definition}</p>
            </CardContent>
          </Card>
        );
      })}
      <p className="text-tertiary col-span-full text-[11px] leading-relaxed">
        区间为 Wilson 95% 置信区间；分母小于 {meta.minimumSample} 时标注「样本不足」。
        {meta.notes.length > 0 ? ` ${meta.notes.join(' ')}` : ''}
      </p>
    </div>
  );
}
