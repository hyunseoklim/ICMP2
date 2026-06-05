from django import template

register = template.Library()

_BG = {
    'red':    'rgba(239,68,68,0.15)',
    'orange': 'rgba(249,115,22,0.15)',
    'yellow': 'rgba(234,179,8,0.2)',
    'green':  'rgba(16,185,129,0.15)',
    'purple': 'rgba(139,92,246,0.15)',
    'gray':   'rgba(148,163,184,0.12)',
}
_TEXT = {
    'red':    '#ef4444',
    'orange': '#f97316',
    'yellow': '#ca8a04',
    'green':  '#10b981',
    'purple': '#8b5cf6',
    'gray':   '#64748b',
}
_BORDER = {
    'red':    'rgba(239,68,68,0.35)',
    'orange': 'rgba(249,115,22,0.35)',
    'yellow': 'rgba(234,179,8,0.35)',
    'green':  'rgba(16,185,129,0.35)',
    'purple': 'rgba(139,92,246,0.35)',
    'gray':   'rgba(148,163,184,0.3)',
}


@register.filter
def risk_bg(color_type):
    return _BG.get(color_type, _BG['gray'])


@register.filter
def risk_text(color_type):
    return _TEXT.get(color_type, _TEXT['gray'])


@register.filter
def risk_border(color_type):
    return _BORDER.get(color_type, _BORDER['gray'])
