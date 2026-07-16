import { Box, Group } from '@mantine/core';
import { sourceMeta } from '../constants';
import type { Source } from '../types';

interface SourceDotProps {
  source: Source;
  size?: number;
}

export function SourceDot({ source, size = 8 }: SourceDotProps) {
  return (
    <Box
      data-testid={`source-dot-${source}`}
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        background: sourceMeta(source).dot,
        flexShrink: 0,
      }}
    />
  );
}

interface SourceDotsProps {
  sources: Source[];
}

/** Overlapping dots — one per unique source, ringed in the card background. */
export function SourceDots({ sources }: SourceDotsProps) {
  return (
    <Group gap={0} wrap="nowrap" align="center">
      {sources.map((source, i) => (
        <Box
          key={source}
          data-testid={`source-dot-${source}`}
          title={sourceMeta(source).label}
          style={{
            width: 9,
            height: 9,
            borderRadius: '50%',
            background: sourceMeta(source).dot,
            border: '2px solid var(--mantine-color-body)',
            marginLeft: i === 0 ? 0 : -4,
            boxSizing: 'content-box',
          }}
        />
      ))}
    </Group>
  );
}
