import { MantineProvider } from '@mantine/core';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { Markdown } from './Markdown';

function renderMarkdown(source: string) {
  return render(
    <MantineProvider>
      <Markdown>{source}</Markdown>
    </MantineProvider>,
  );
}

describe('Markdown', () => {
  it('renders GFM markdown as elements, with links opening in a new tab', () => {
    renderMarkdown('A **bold** word and a [link](https://example.com).');

    expect(screen.getByText('bold').tagName).toBe('STRONG');
    const link = screen.getByRole('link', { name: 'link' });
    expect(link).toHaveAttribute('href', 'https://example.com');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', expect.stringContaining('noreferrer'));
  });

  it('renders a GFM table', () => {
    renderMarkdown('| a | b |\n| - | - |\n| 1 | 2 |');
    expect(document.querySelector('table')).not.toBeNull();
  });

  it('does not render raw HTML, so untrusted text cannot inject markup', () => {
    renderMarkdown('Hello <img src=x onerror="alert(1)"> world');
    expect(document.querySelector('img')).toBeNull();
  });
});
