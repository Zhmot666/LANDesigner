# Примеры LanDesigner

## `demo-office.lanproj`

Демонстрационный проект «Demo Office»:

- Площадка **HQ** → здание **Building A** → **Floor 1** → **Server Room** → шкаф **Rack-01** (42U)
- Коммутатор **sw-core-1** (U20), сервер **srv-app-1** (U22–23), ИБП **ups-1** (U40–41, **без портов**)
- VLAN 10 Management, IP `10.0.0.1/24` на порту коммутатора
- Кабель **sw-srv-01** между коммутатором и сервером
- Заготовка топологии (`ensure_topology`)

Откройте в приложении: **Файл → Открыть** → выберите `examples/demo-office.lanproj`.

Файл можно копировать и изменять — это обычный SQLite-проект LanDesigner.
