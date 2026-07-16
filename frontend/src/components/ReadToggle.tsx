import { ActionIcon, Tooltip } from '@mantine/core';
import { IconMail, IconMailOpened } from '@tabler/icons-react';
import type { MouseEvent } from 'react';

interface ReadToggleProps {
  unread: boolean;
  onToggle: () => void;
  size?: number;
}

/**
 * Envelope = unread, opened envelope = read. Stops propagation so the toggle
 * never triggers the surrounding card/row navigation.
 */
export function ReadToggle({ unread, onToggle, size = 18 }: ReadToggleProps) {
  const handleClick = (e: MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    onToggle();
  };

  return (
    <Tooltip label={unread ? 'Mark as read' : 'Mark as unread'} withArrow>
      <ActionIcon
        variant="subtle"
        color={unread ? 'blue' : 'gray'}
        onClick={handleClick}
        aria-label="Toggle read/unread"
        style={{ opacity: unread ? 1 : 0.55, flexShrink: 0 }}
      >
        {unread ? <IconMail size={size} /> : <IconMailOpened size={size} />}
      </ActionIcon>
    </Tooltip>
  );
}
