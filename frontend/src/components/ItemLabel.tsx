import { Fragment, type ReactNode } from 'react';

/**
 * Renders an item label, turning configured custom-emoji `:shortcodes:` into their images.
 * Standard emoji are already Unicode by the time they reach here; anything not in the map
 * stays as plain text, so a bare `:shrug:` is untouched.
 */
export function itemLabel(label: string, emoji: Record<string, string>): ReactNode {
  if (!label || !emoji || Object.keys(emoji).length === 0) return label;
  const parts = label.split(/(:[a-z0-9_+-]+:)/gi);
  return parts.map((part, i) => {
    const match = /^:([a-z0-9_+-]+):$/i.exec(part);
    const url = match ? emoji[match[1]] : undefined;
    if (url) {
      return (
        <img
          key={i}
          src={url}
          alt={part}
          title={part}
          style={{ height: '1.15em', verticalAlign: 'text-bottom', margin: '0 1px' }}
        />
      );
    }
    return <Fragment key={i}>{part}</Fragment>;
  });
}
