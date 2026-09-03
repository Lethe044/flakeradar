"""Generate a small, self-contained SVG badge showing the flaky test count.

Styled after shields.io's flat badges, but rendered entirely locally with
no network call and no hosted service dependency - regenerate it as part
of your CI and commit it, or upload it as an artifact.
"""

from __future__ import annotations

import html

_FONT = "Verdana,Geneva,DejaVu Sans,sans-serif"
_CHAR_WIDTH = 6.5  # rough average glyph width in px at font-size 11
_PADDING = 10


def _text_width(text: str) -> int:
    return max(6, int(len(text) * _CHAR_WIDTH)) + _PADDING


def color_for_count(count: int) -> str:
    """Green when clean, yellow for a handful, red once it piles up."""
    if count <= 0:
        return "#4c1"
    if count <= 3:
        return "#dfb317"
    return "#e05d44"


def generate_badge_svg(label: str, value: str, color: str) -> str:
    label = html.escape(label)
    value = html.escape(value)
    label_w = _text_width(label)
    value_w = _text_width(value)
    total_w = label_w + value_w

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="20" '
        f'role="img" aria-label="{label}: {value}">'
        f'<linearGradient id="s" x2="0" y2="100%">'
        f'<stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        f'<stop offset="1" stop-opacity=".1"/>'
        f"</linearGradient>"
        f'<clipPath id="r"><rect width="{total_w}" height="20" rx="3" fill="#fff"/></clipPath>'
        f'<g clip-path="url(#r)">'
        f'<rect width="{label_w}" height="20" fill="#555"/>'
        f'<rect x="{label_w}" width="{value_w}" height="20" fill="{color}"/>'
        f'<rect width="{total_w}" height="20" fill="url(#s)"/>'
        f"</g>"
        f'<g fill="#fff" text-anchor="middle" font-family="{_FONT}" font-size="11">'
        f'<text x="{label_w / 2:.1f}" y="14">{label}</text>'
        f'<text x="{label_w + value_w / 2:.1f}" y="14">{value}</text>'
        f"</g>"
        f"</svg>"
    )


def badge_for_flaky_count(count: int, label: str = "flaky tests") -> str:
    return generate_badge_svg(label, str(count), color_for_count(count))
