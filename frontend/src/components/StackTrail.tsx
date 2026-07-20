import { Group, Text, Tooltip } from '@mantine/core';
import { IconChevronRight, IconStack2 } from '@tabler/icons-react';
import { Fragment } from 'react';

/**
 * A git-spice stack drawn as a trail from the base of the stack up to this branch — the last
 * entry is the branch this item is, highlighted; the earlier ones are what it's stacked on.
 * Renders nothing unless the branch actually sits on another (a chain of two or more).
 */
export function StackTrail({ stack }: { stack: string[] }) {
  if (stack.length < 2) return null;
  const tip = stack.join(' → ');
  return (
    <Tooltip label={`Stacked: ${tip}`} withArrow>
      <Group gap={4} wrap="wrap" mt={2} c="dimmed" style={{ cursor: 'default' }}>
        <IconStack2 size={13} />
        {stack.map((branch, i) => {
          const current = i === stack.length - 1;
          return (
            <Fragment key={branch}>
              {i > 0 && <IconChevronRight size={11} style={{ opacity: 0.5 }} />}
              <Text
                component="span"
                fz={11}
                fw={current ? 700 : 400}
                c={current ? 'grape' : 'dimmed'}
                style={{ fontFamily: 'var(--mantine-font-family-monospace)' }}
              >
                {branch}
              </Text>
            </Fragment>
          );
        })}
      </Group>
    </Tooltip>
  );
}
