#!/usr/bin/env python3

from pathlib import Path
import textwrap

OUTPUT_DIR = Path("mention-hq-logo-proposals")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PALETTE = {
    "background": "#F7F8FA",
    "surface": "#FFFFFF",
    "text": "#17191C",
    "muted": "#89919D",
    "border": "#DCE1E7",
    "blue": "#3975FF",
    "blue_light": "#E9EEFF",
    "green": "#24B47E",
    "orange": "#F47B35",
    "pink": "#D93872",
}


def svg_document(content: str, width: int = 512, height: int = 512) -> str:
    return textwrap.dedent(
        f"""
        <svg xmlns="http://www.w3.org/2000/svg"
             width="{width}"
             height="{height}"
             viewBox="0 0 {width} {height}">
          {content}
        </svg>
        """
    ).strip()


def stacked_cards_icon() -> str:
    return svg_document(
        f"""
        <rect width="512" height="512" rx="112"
              fill="{PALETTE['blue_light']}"/>

        <rect x="116" y="118" width="280" height="92" rx="28"
              fill="{PALETTE['surface']}"
              stroke="{PALETTE['blue']}" stroke-width="18"/>

        <rect x="142" y="214" width="228" height="86" rx="26"
              fill="{PALETTE['surface']}"
              stroke="{PALETTE['blue']}" stroke-width="18"/>

        <rect x="170" y="304" width="172" height="82" rx="24"
              fill="{PALETTE['blue']}"/>

        <circle cx="158" cy="164" r="12"
                fill="{PALETTE['pink']}"/>

        <circle cx="184" cy="257" r="11"
                fill="{PALETTE['orange']}"/>

        <circle cx="214" cy="345" r="10"
                fill="{PALETTE['surface']}"/>
        """
    )


def column_buckets_icon() -> str:
    return svg_document(
        f"""
        <rect width="512" height="512" rx="112"
              fill="{PALETTE['surface']}"/>

        <rect x="102" y="144" width="92" height="224" rx="30"
              fill="{PALETTE['blue_light']}"/>

        <rect x="210" y="116" width="92" height="280" rx="30"
              fill="{PALETTE['blue']}"/>

        <rect x="318" y="168" width="92" height="176" rx="30"
              fill="{PALETTE['blue_light']}"/>

        <circle cx="148" cy="184" r="11"
                fill="{PALETTE['pink']}"/>

        <circle cx="256" cy="158" r="11"
                fill="{PALETTE['surface']}"/>

        <circle cx="364" cy="208" r="11"
                fill="{PALETTE['orange']}"/>
        """
    )


def nested_stack_icon() -> str:
    return svg_document(
        f"""
        <rect width="512" height="512" rx="112"
              fill="{PALETTE['text']}"/>

        <rect x="100" y="112" width="312" height="288" rx="58"
              fill="none"
              stroke="{PALETTE['blue']}" stroke-width="28"/>

        <rect x="148" y="160" width="216" height="192" rx="44"
              fill="none"
              stroke="{PALETTE['surface']}" stroke-width="28"/>

        <rect x="196" y="208" width="120" height="96" rx="30"
              fill="{PALETTE['blue']}"/>

        <circle cx="256" cy="256" r="13"
                fill="{PALETTE['surface']}"/>
        """
    )


def priority_stack_icon() -> str:
    return svg_document(
        f"""
        <rect width="512" height="512" rx="112"
              fill="{PALETTE['surface']}"/>

        <path d="M112 324
                 Q112 292 144 292
                 H368
                 Q400 292 400 324
                 V370
                 Q400 402 368 402
                 H144
                 Q112 402 112 370 Z"
              fill="{PALETTE['blue_light']}"/>

        <path d="M142 232
                 Q142 202 172 202
                 H340
                 Q370 202 370 232
                 V286
                 H142 Z"
              fill="{PALETTE['blue']}"/>

        <path d="M180 138
                 Q180 110 208 110
                 H304
                 Q332 110 332 138
                 V196
                 H180 Z"
              fill="{PALETTE['text']}"/>

        <circle cx="214" cy="154" r="10"
                fill="{PALETTE['pink']}"/>

        <circle cx="176" cy="250" r="10"
                fill="{PALETTE['surface']}"/>

        <circle cx="148" cy="340" r="10"
                fill="{PALETTE['green']}"/>
        """
    )


CONCEPTS = {
    "01-stacked-cards": {
        "title": "Stacked Cards",
        "subtitle": "Bucket → Task → Item",
        "svg": stacked_cards_icon(),
    },
    "02-column-buckets": {
        "title": "Column Buckets",
        "subtitle": "Inspired by the board view",
        "svg": column_buckets_icon(),
    },
    "03-nested-stack": {
        "title": "Nested Stack",
        "subtitle": "A compact hierarchy mark",
        "svg": nested_stack_icon(),
    },
    "04-priority-stack": {
        "title": "Priority Stack",
        "subtitle": "Organization and progression",
        "svg": priority_stack_icon(),
    },
}


def extract_svg_body(svg: str) -> str:
    return svg.split(">", 1)[1].rsplit("</svg>", 1)[0]


def create_comparison_board() -> str:
    board_width = 1440
    board_height = 1080

    positions = [
        (60, 150),
        (740, 150),
        (60, 590),
        (740, 590),
    ]

    cards = []

    for (key, concept), (x, y) in zip(CONCEPTS.items(), positions):
        icon_body = extract_svg_body(concept["svg"])

        cards.append(
            f"""
            <g transform="translate({x} {y})">
              <rect width="640" height="390" rx="34"
                    fill="{PALETTE['surface']}"
                    stroke="{PALETTE['border']}" stroke-width="2"/>

              <g transform="translate(34 34) scale(0.46)">
                {icon_body}
              </g>

              <text x="310" y="90"
                    font-family="Inter, Arial, sans-serif"
                    font-size="30"
                    font-weight="700"
                    fill="{PALETTE['text']}">
                {concept['title']}
              </text>

              <text x="310" y="126"
                    font-family="Inter, Arial, sans-serif"
                    font-size="18"
                    fill="{PALETTE['muted']}">
                {concept['subtitle']}
              </text>

              <g transform="translate(310 180)">
                <g transform="scale(0.105)">
                  {icon_body}
                </g>

                <text x="70" y="38"
                      font-family="Inter, Arial, sans-serif"
                      font-size="28"
                      font-weight="750"
                      fill="{PALETTE['text']}">
                  Mention HQ
                </text>
              </g>

              <text x="310" y="286"
                    font-family="Inter, Arial, sans-serif"
                    font-size="14"
                    font-weight="650"
                    letter-spacing="1"
                    fill="{PALETTE['muted']}">
                PWA ICON
              </text>

              <g transform="translate(310 305)">
                <g transform="scale(0.09)">
                  {icon_body}
                </g>
              </g>

              <g transform="translate(385 305)">
                <g transform="scale(0.065)">
                  {icon_body}
                </g>
              </g>
            </g>
            """
        )

    return svg_document(
        f"""
        <rect width="{board_width}" height="{board_height}"
              fill="{PALETTE['background']}"/>

        <text x="60" y="72"
              font-family="Inter, Arial, sans-serif"
              font-size="42"
              font-weight="800"
              fill="{PALETTE['text']}">
          Mention HQ — Bucket Stack logo directions
        </text>

        <text x="60" y="112"
              font-family="Inter, Arial, sans-serif"
              font-size="20"
              fill="{PALETTE['muted']}">
          Refined to match the app’s light interface, rounded cards and blue accents.
        </text>

        {''.join(cards)}
        """,
        board_width,
        board_height,
    )


def save_svg(filename: Path, svg: str) -> None:
    filename.write_text(svg, encoding="utf-8")
    print(f"Created {filename}")


def export_png(svg_path: Path, png_path: Path) -> None:
    try:
        import cairosvg

        cairosvg.svg2png(
            url=str(svg_path),
            write_to=str(png_path),
            output_width=1024,
            output_height=1024,
        )
        print(f"Created {png_path}")
    except ImportError:
        print(
            "PNG export skipped. Install CairoSVG with:\n"
            "  pip install cairosvg"
        )


def main() -> None:
    for filename, concept in CONCEPTS.items():
        svg_path = OUTPUT_DIR / f"{filename}.svg"
        png_path = OUTPUT_DIR / f"{filename}.png"

        save_svg(svg_path, concept["svg"])
        export_png(svg_path, png_path)

    board_svg = OUTPUT_DIR / "mention-hq-logo-board.svg"
    board_png = OUTPUT_DIR / "mention-hq-logo-board.png"

    save_svg(board_svg, create_comparison_board())

    try:
        import cairosvg

        cairosvg.svg2png(
            url=str(board_svg),
            write_to=str(board_png),
            output_width=1440,
            output_height=1080,
        )
        print(f"Created {board_png}")
    except ImportError:
        pass


if __name__ == "__main__":
    main()