"""Work-calendar module (change 28-calendario-laboral).

Transversal capability that resolves the effective working hours/days of a
project by cascading proyecto → override del equipo (proyecto raíz) →
calendario de la empresa → default global (design.md "Data Flow"). Screaming
Architecture: this capability reads across ``organizations`` and ``projects``
so it lives in its own module rather than inside either owner.
"""
