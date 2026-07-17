import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { itemLabel } from './ItemLabel';

describe('itemLabel', () => {
  it('renders a configured custom emoji as its image', () => {
    render(
      <div>
        {itemLabel('#mo - good :party-parrot: work', { 'party-parrot': 'https://x/pp.gif' })}
      </div>,
    );
    const img = screen.getByAltText(':party-parrot:');
    expect(img).toHaveAttribute('src', 'https://x/pp.gif');
    expect(screen.getByText(/good/)).toBeInTheDocument();
  });

  it('leaves an unknown shortcode and plain text alone', () => {
    render(<div>{itemLabel('just :shrug: text', {})}</div>);
    expect(screen.getByText('just :shrug: text')).toBeInTheDocument();
    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });
});
