import { Badge } from '@mantine/core';

const META: Record<string, { label: string; bg: string; color: string }> = {
  draft: { label: 'Draft', bg: 'var(--mantine-color-gray-5)', color: '#fff' },
  open: { label: 'Open', bg: 'var(--mantine-color-green-7)', color: '#fff' },
  approved: { label: 'Approved', bg: 'var(--mantine-color-teal-6)', color: '#fff' },
  changes_requested: {
    label: 'Changes requested',
    bg: 'var(--mantine-color-orange-6)',
    color: '#fff',
  },
};

interface PrStatusPillProps {
  status: string;
  size?: 'xs' | 'sm' | 'md';
}

export function PrStatusPill({ status, size = 'xs' }: PrStatusPillProps) {
  const meta = META[status] ?? META.open;
  return (
    <Badge
      size={size}
      radius="xl"
      variant="filled"
      styles={{ root: { background: meta.bg, color: meta.color, fontWeight: 600 } }}
    >
      {meta.label}
    </Badge>
  );
}
