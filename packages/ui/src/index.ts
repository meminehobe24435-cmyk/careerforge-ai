/**
 * `@careerforge/ui` — CareerForge AI design system (PHASE 1 primitives).
 *
 * Rules that hold for every primitive in this package:
 *  - colour comes from design tokens only (`src/styles/tokens.css` in the app); a raw hex
 *    value is rejected by the package's ESLint config;
 *  - Radix handles focus management/ARIA, CVA handles variants, `cn()` handles overrides;
 *  - icon-only controls require `aria-label` at the type level.
 */

export { cn } from './lib/cn';

export { Button, buttonVariants } from './components/button';
export type { ButtonProps } from './components/button';

export { IconButton, iconButtonVariants } from './components/icon-button';
export type { IconButtonProps } from './components/icon-button';

export {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from './components/card';

export { Badge, badgeVariants } from './components/badge';
export type { BadgeProps } from './components/badge';

export { Input } from './components/input';
export { Textarea } from './components/textarea';
export { Label } from './components/label';
export { Separator } from './components/separator';
export type { SeparatorProps } from './components/separator';

export { Skeleton, SkeletonText } from './components/skeleton';
export { Spinner } from './components/spinner';
export type { SpinnerProps } from './components/spinner';

export { Kbd } from './components/kbd';

export { CopyButton } from './components/copy-button';
export type { CopyButtonProps } from './components/copy-button';

export { CodeBlock } from './components/code-block';
export type { CodeBlockProps } from './components/code-block';

export { EmptyState } from './components/empty-state';
export type { EmptyStateProps } from './components/empty-state';

export { ErrorState } from './components/error-state';
export type { ErrorStateProps } from './components/error-state';

export { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from './components/tooltip';
export type { TooltipProps } from './components/tooltip';

export {
  Dialog,
  DialogBody,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
} from './components/dialog';
export type { DialogContentProps } from './components/dialog';

export {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
} from './components/dropdown-menu';

export { Tabs, TabsContent, TabsList, TabsTrigger } from './components/tabs';
