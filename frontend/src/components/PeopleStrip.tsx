import { Avatar, Text, Tooltip } from '@mantine/core';
import type { ItemPerson } from '../types';

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

interface PeopleStripProps {
  people: ItemPerson[];
  size?: number;
}

export function PeopleStrip({ people, size = 20 }: PeopleStripProps) {
  if (people.length === 0) return null;
  return (
    <Avatar.Group spacing="xs">
      {people.map((person) => (
        <Tooltip
          key={`${person.kind}:${person.value}`}
          label={`${person.name} · ${person.role}`}
          withArrow
        >
          <Avatar size={size} radius="xl" color="gray" name={person.name}>
            <Text fz={9} fw={600}>
              {initials(person.name)}
            </Text>
          </Avatar>
        </Tooltip>
      ))}
    </Avatar.Group>
  );
}
