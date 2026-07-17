import { Button, Center, Stack, Text } from '@mantine/core';
import { useHq } from '../shell/HqContext';

/** Shown when a search hides everything on a screen — with a way out of the search. */
export function NoMatches({ query, noun = 'items' }: { query: string; noun?: string }) {
  const { setQuery } = useHq();
  return (
    <Center style={{ flex: 1 }}>
      <Stack align="center" gap="xs">
        <Text c="dimmed" fz="sm">
          No {noun} match “{query}”.
        </Text>
        <Button size="xs" variant="light" onClick={() => setQuery('')}>
          Clear search
        </Button>
      </Stack>
    </Center>
  );
}
