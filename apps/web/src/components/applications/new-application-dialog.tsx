'use client';

import { useState } from 'react';
import {
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Textarea,
} from '@careerforge/ui';
import {
  APPLICATION_STATUSES,
  type ApplicationCreateRequest,
  type ApplicationStatus,
} from '@careerforge/shared';

import { STATUS_LABELS } from '@/lib/application-status';
import { useCreateApplication } from '@/hooks/use-applications';

interface NewApplicationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * Add a card by hand.
 *
 * Manual entry is a first-class path, not a fallback: a candidate often hears about a role
 * long before a posting exists in this system (a referral, an internal transfer), and
 * requiring a parsed JD first would mean the board cannot record the thing that already
 * happened. The API accepts exactly this — `jobId` or manual fields.
 *
 * `matchScore` is absent on purpose: a score comes from the stored match, and a client that
 * could type one could put "92% match" on a card for a job nobody scored.
 */
export function NewApplicationDialog({ open, onOpenChange }: NewApplicationDialogProps) {
  const create = useCreateApplication();
  const [company, setCompany] = useState('');
  const [role, setRole] = useState('');
  const [location, setLocation] = useState('');
  const [status, setStatus] = useState<ApplicationStatus>('wishlist');
  const [notes, setNotes] = useState('');

  const valid = company.trim().length > 0 || role.trim().length > 0;

  function submit() {
    if (!valid) return;
    const payload: ApplicationCreateRequest = {
      company: company.trim(),
      role: role.trim(),
      status,
      notes: notes.trim(),
    };
    if (location.trim()) payload.location = location.trim();
    create.mutate(payload, {
      onSuccess: () => {
        setCompany('');
        setRole('');
        setLocation('');
        setNotes('');
        setStatus('wishlist');
        onOpenChange(false);
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>加入投递看板</DialogTitle>
          <DialogDescription>
            手动录入也完全可以：内推、转岗这类机会在系统里有岗位记录之前就该被记下来。
            匹配分由系统在关联岗位时自行计算，不接受手填。
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="app-company">公司</Label>
            <Input
              id="app-company"
              value={company}
              onChange={(event) => setCompany(event.target.value)}
              placeholder="例如：智远科技"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="app-role">岗位</Label>
            <Input
              id="app-role"
              value={role}
              onChange={(event) => setRole(event.target.value)}
              placeholder="例如：嵌入式软件工程师"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="app-location">地点</Label>
            <Input
              id="app-location"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
              placeholder="例如：苏州"
              autoComplete="off"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="app-status">初始状态</Label>
            <select
              id="app-status"
              value={status}
              onChange={(event) => setStatus(event.target.value as ApplicationStatus)}
              className="border-subtle bg-surface text-primary h-9 rounded-md border px-2 text-sm"
            >
              {APPLICATION_STATUSES.map((value) => (
                <option key={value} value={value}>
                  {STATUS_LABELS[value]}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="app-notes">备注</Label>
            <Textarea
              id="app-notes"
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              placeholder="内推人、投递渠道、面试反馈…"
              rows={3}
            />
          </div>
        </div>

        <DialogFooter>
          <DialogClose asChild>
            <Button variant="ghost">取消</Button>
          </DialogClose>
          <Button onClick={submit} disabled={!valid} loading={create.isPending}>
            加入看板
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
