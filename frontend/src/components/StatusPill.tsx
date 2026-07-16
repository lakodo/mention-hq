import { Badge } from '@mantine/core';
import { statusMeta } from '../constants';
import type { Status } from '../types';

interface StatusPillProps {
  status: Status;
  size?: 'xs' | 'sm' | 'md';
}

export function StatusPill({ status, size = 'sm' }: StatusPillProps) {
  const meta = statusMeta(status);
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
