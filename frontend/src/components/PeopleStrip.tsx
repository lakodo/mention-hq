import { Avatar, Text, Tooltip } from '@mantine/core';
import { useMemo } from 'react';
import { usePeople } from '../api/hooks';
import type { ItemPerson, Person } from '../types';

function initials(name: string): string {
  const parts = name
    .replace(/[<>@]/g, '')
    .split(/[\s._-]+/)
    .filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

/** Merge people across items, de-duplicated by kind+value, first role kept. */
export function mergePeople(items: { people: ItemPerson[] }[]): ItemPerson[] {
  const byKey = new Map<string, ItemPerson>();
  for (const item of items) {
    for (const person of item.people ?? []) {
      const key = `${person.kind}:${person.value}`;
      if (!byKey.has(key)) byKey.set(key, person);
    }
  }
  return [...byKey.values()];
}

interface Resolved {
  key: string;
  name: string;
  role: string;
  avatar?: string | null;
}

interface PeopleStripProps {
  people: ItemPerson[];
  size?: number;
}

/**
 * One row of avatars for the people an item (or task) concerns. Identities are resolved
 * through the people directory, so the same human across sources — a Slack id and a GitHub
 * login — collapses to a single avatar under their directory name, and the first source that
 * carries an image wins. People not yet in the directory fall back to their source name.
 */
export function PeopleStrip({ people, size = 28 }: PeopleStripProps) {
  const { data: directory = [] } = usePeople();

  const byIdentity = useMemo(() => {
    const map = new Map<string, Person>();
    for (const person of directory) {
      for (const id of person.identities) map.set(`${id.kind}:${id.value}`, person);
    }
    return map;
  }, [directory]);

  const resolved = useMemo<Resolved[]>(() => {
    const groups = new Map<string, Resolved>();
    for (const person of people) {
      const match = byIdentity.get(`${person.kind}:${person.value}`);
      const key = match ? `person:${match.id}` : `${person.kind}:${person.value}`;
      // Prefer the avatar chosen for the directory person, then any identity's avatar, then
      // the one this source carries.
      const dirAvatar = match
        ? match.avatar_url || match.identities.find((id) => id.avatar_url)?.avatar_url
        : undefined;
      const avatar = dirAvatar || person.avatar || undefined;
      const existing = groups.get(key);
      if (!existing) {
        groups.set(key, {
          key,
          name: match?.display_name || person.name,
          role: person.role,
          avatar,
        });
      } else if (!existing.avatar && avatar) {
        existing.avatar = avatar;
      }
    }
    return [...groups.values()];
  }, [people, byIdentity]);

  if (resolved.length === 0) return null;
  return (
    <Avatar.Group spacing="xs">
      {resolved.map((person) => (
        <Tooltip key={person.key} label={`${person.name} · ${person.role}`} withArrow>
          <Avatar
            size={size}
            radius="xl"
            color="gray"
            name={person.name}
            src={person.avatar || undefined}
          >
            <Text fz={Math.round(size * 0.4)} fw={600}>
              {initials(person.name)}
            </Text>
          </Avatar>
        </Tooltip>
      ))}
    </Avatar.Group>
  );
}
