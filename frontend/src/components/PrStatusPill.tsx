import { Badge, Group } from '@mantine/core';

const META: Record<string, { label: string; bg: string; color: string }> = {
  draft: { label: 'Draft', bg: 'var(--mantine-color-gray-5)', color: '#fff' },
  open: { label: 'Open', bg: 'var(--mantine-color-green-7)', color: '#fff' },
  merged: { label: 'Merged', bg: 'var(--mantine-color-violet-6)', color: '#fff' },
  approved: { label: 'Approved', bg: 'var(--mantine-color-teal-6)', color: '#fff' },
  review_required: { label: 'Review required', bg: 'var(--mantine-color-blue-6)', color: '#fff' },
  changes_requested: {
    label: 'Changes requested',
    bg: 'var(--mantine-color-orange-6)',
    color: '#fff',
  },
};

interface PrStatusPillProps {
  status: string;
  reviewRequested?: boolean;
  size?: 'xs' | 'sm' | 'md';
}

export function PrStatusPill({ status, reviewRequested = false, size = 'xs' }: PrStatusPillProps) {
  const meta = META[status] ?? META.open;
  // A pending review is only news when the overall decision is something else — a PR can be
  // "changes requested" and still awaiting another reviewer.
  const showPending = reviewRequested && status !== 'review_required' && status !== 'draft';
  return (
    <Group gap={4} wrap="nowrap" component="span" display="inline-flex">
      <Badge
        size={size}
        radius="xl"
        variant="filled"
        styles={{ root: { background: meta.bg, color: meta.color, fontWeight: 600 } }}
      >
        {meta.label}
      </Badge>
      {showPending && (
        <Badge size={size} radius="xl" variant="light" color="blue">
          Review pending
        </Badge>
      )}
    </Group>
  );
}
