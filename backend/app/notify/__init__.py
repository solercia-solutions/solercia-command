"""Notification delivery hub — single fan-out point for every registered
delivery channel (change 12-notification-hub, design.md).

Frontera de extracción futura (design.md, "Fronteras de extracción futura"):
this package importa SOLO ``app.modules.notifications.models`` +
``app.shared.*``. NUNCA importa ``app.modules.notifications.repository`` —
el repository es quien llama HACIA el hub a través del registro de canales
(``app.notify.registry``); importar el repository desde aquí cerraría el
ciclo ``notifications.repository -> app.notify -> notifications.repository``.
Regla heredada de ``app/email/`` (change 08).

Los canales viven en su propio dominio (email en ``app/email``, WebSocket en
``app/realtime``) y se REGISTRAN en el hub; el hub nunca importa internos de
un dominio de canal, los dominios importan los puertos del hub.
"""
