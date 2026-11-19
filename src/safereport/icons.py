"""Line icons for the app, drawn on a 24 point grid with a 1.8 point stroke.

They are inline SVG, so they follow the text colour in light and dark mode and need no font or
network. Each one stands for a thing the user handles: a report, a letter, an inspection.
"""

from __future__ import annotations

import json


PATHS = {
    "week": '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 '
    '2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="M9 12h6M9 16h4"/>',
    "ask": '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8M8 13h5"/>',
    "evidence": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h5"/><path d="M14 2v6h6v3"/>'
    '<circle cx="16.5" cy="16.5" r="3.5"/><path d="m22 22-3-3"/>',
    "trends": '<path d="M3 3v18h18"/><path d="m7 15 4-4 3 3 6-7"/>',
    "controls": '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    "downloads": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5M12 15V3"/>',
    "report": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
    "alert": '<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>'
    '<path d="M12 9v4M12 17h.01"/>',
    "inspection": '<path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/>',
    "letter": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "branch": '<circle cx="6" cy="5" r="2"/><circle cx="6" cy="19" r="2"/><circle cx="18" cy="7" r="2"/>'
    '<path d="M6 7v10M18 9c0 5-7 4-11 8"/>',
    "critic": '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
    "people": '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    "data": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/>'
    '<path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
}

# The tab each icon belongs to, by its label.
TABS = {
    "This week's reports": "week",
    "Ask": "ask",
    "Evidence view": "evidence",
    "Trends and prevention": "trends",
    "AI controls and evaluation": "controls",
    "Downloads": "downloads",
}


def svg(name: str, size: int = 16, label: str = "") -> str:
    """An inline icon; decorative unless `label` names it for screen readers."""
    role = f'role="img" aria-label="{label}"' if label else 'aria-hidden="true"'
    return (
        f'<svg class="sr-icon" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" {role}>'
        f"{PATHS[name]}</svg>"
    )


def tab_script() -> str:
    """Puts an icon before each tab label, and again whenever Gradio draws the tabs anew."""
    icons = {label: svg(name, 15) for label, name in TABS.items()}
    return f"""<script>
(() => {{
  const icons = {json.dumps(icons)};
  const mark = () => document.querySelectorAll('button[role="tab"]').forEach(button => {{
    const label = button.textContent.trim();
    if (icons[label] && !button.querySelector('.sr-icon')) button.insertAdjacentHTML('afterbegin', icons[label]);
  }});
  new MutationObserver(mark).observe(document.documentElement, {{childList: true, subtree: true}});
  document.addEventListener('DOMContentLoaded', mark);
}})();
</script>"""
