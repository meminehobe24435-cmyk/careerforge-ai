import { Card, CardContent, CardHeader, Skeleton } from '@careerforge/ui';

/**
 * Dashboard loading state. The skeleton mirrors the real layout block for block
 * (docs/UI.md §6.1: "Skeleton 与真实布局同构"), including the 6-up stat grid
 * breakpoints used by the loaded view.
 */
export function DashboardSkeleton() {
  return (
    <div className="flex flex-col gap-5" aria-busy="true" aria-live="polite">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-6 w-56" />
        <Skeleton className="h-3 w-72" />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[360px_1fr]">
        <Card>
          <CardHeader>
            <Skeleton className="h-4 w-32" />
          </CardHeader>
          <CardContent className="flex items-center gap-4">
            <Skeleton className="size-32 rounded-full" />
            <div className="flex flex-1 flex-col gap-2">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-5/6" />
              <Skeleton className="h-3 w-2/3" />
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <Card key={index}>
              <CardContent className="flex flex-col gap-3 p-4 pt-4">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-6 w-16" />
                <Skeleton className="h-3 w-20" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      <Card>
        <CardHeader>
          <Skeleton className="h-4 w-40" />
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-9 w-full" />
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
