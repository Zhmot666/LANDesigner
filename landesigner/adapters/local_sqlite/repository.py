from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import json
from uuid import UUID

from landesigner.domain.entities import (
    Building,
    Cable,
    Device,
    DeviceType,
    Floor,
    FloorPlanAsset,
    IpAddress,
    Lag,
    Port,
    PortGroup,
    ProjectMeta,
    ProjectSnapshot,
    Rack,
    Room,
    Site,
    TopologyLink,
    TopologyNode,
    VirtualSwitch,
    Vlan,
)
from landesigner.domain.enums import (
    CableCategory,
    CableKind,
    DeviceRole,
    LagMode,
    PortMedia,
    PortMode,
    PortSide,
    PortStatus,
)
from landesigner.ports.repository import ProjectRepository


def _uuid_str(value: UUID) -> str:
    return str(value)


def _dt_to_str(value: datetime) -> str:
    # ISO 8601 с timezone (datetime.fromisoformat умеет вернуть tz-aware).
    return value.isoformat()


def _dt_from_str(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _enum_value(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


class LocalSqliteRepository(ProjectRepository):
    """
    MVP-репозиторий: SQLite внутри файла `.lanproj`.

    Сейчас реализован напрямую через `sqlite3`, чтобы не зависеть от версий SQLAlchemy/Alembic
    в окружении разработки. Схема соответствует ожидаемой "ядровой" структуре этапа 0b.
    """

    def _connect(self, file_path: str) -> sqlite3.Connection:
        con = sqlite3.connect(file_path)
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def _ensure_schema(self, con: sqlite3.Connection) -> None:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_meta (
                id TEXT PRIMARY KEY NOT NULL,
                name TEXT NOT NULL,
                schema_version INTEGER NOT NULL DEFAULT 1,
                origin TEXT NOT NULL DEFAULT 'local',
                revision INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS site (
                id TEXT PRIMARY KEY NOT NULL,
                project_id TEXT NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(project_id) REFERENCES project_meta(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS building (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                name TEXT NOT NULL,
                address TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS floor (
                id TEXT PRIMARY KEY NOT NULL,
                building_id TEXT NOT NULL,
                name TEXT NOT NULL,
                level REAL NOT NULL,
                plan_image_relpath TEXT NOT NULL DEFAULT '',
                scale_m_per_px REAL NOT NULL DEFAULT 0.1,
                FOREIGN KEY(building_id) REFERENCES building(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS room (
                id TEXT PRIMARY KEY NOT NULL,
                floor_id TEXT NOT NULL,
                name TEXT NOT NULL,
                FOREIGN KEY(floor_id) REFERENCES floor(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rack (
                id TEXT PRIMARY KEY NOT NULL,
                room_id TEXT NOT NULL,
                name TEXT NOT NULL,
                units INTEGER NOT NULL,
                unit_start INTEGER NOT NULL,
                unit_end INTEGER NOT NULL,
                FOREIGN KEY(room_id) REFERENCES room(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS device_type (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                vendor TEXT NOT NULL DEFAULT '',
                model TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                port_template TEXT NOT NULL DEFAULT '[]',
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS device (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                device_type_id TEXT NOT NULL,
                hostname TEXT NOT NULL DEFAULT '',
                serial TEXT NOT NULL DEFAULT '',
                inventory_tag TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL,
                room_id TEXT,
                rack_id TEXT,
                rack_u INTEGER,
                rack_u_height INTEGER NOT NULL DEFAULT 1,
                host_device_id TEXT,
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(device_type_id) REFERENCES device_type(id) ON DELETE CASCADE,
                FOREIGN KEY(room_id) REFERENCES room(id) ON DELETE SET NULL,
                FOREIGN KEY(rack_id) REFERENCES rack(id) ON DELETE SET NULL,
                FOREIGN KEY(host_device_id) REFERENCES device(id) ON DELETE SET NULL
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS port (
                id TEXT PRIMARY KEY NOT NULL,
                device_id TEXT NOT NULL,
                name TEXT NOT NULL,
                speed INTEGER NOT NULL,
                media TEXT NOT NULL,
                status TEXT NOT NULL,
                mode TEXT NOT NULL DEFAULT 'ACCESS',
                access_vlan_id TEXT,
                mac TEXT NOT NULL DEFAULT '',
                side TEXT NOT NULL DEFAULT 'NONE',
                position INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(device_id) REFERENCES device(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS cable (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                label TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                category TEXT NOT NULL,
                length_m REAL,
                end_a_port_id TEXT NOT NULL,
                end_b_port_id TEXT NOT NULL,
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(end_a_port_id) REFERENCES port(id) ON DELETE CASCADE,
                FOREIGN KEY(end_b_port_id) REFERENCES port(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS vlan (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                vlan_id INTEGER NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS ip_address (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                port_id TEXT,
                address TEXT NOT NULL DEFAULT '',
                cidr TEXT NOT NULL DEFAULT '',
                gateway TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(port_id) REFERENCES port(id) ON DELETE SET NULL
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS lag (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT 'bond0',
                mode TEXT NOT NULL DEFAULT 'ACTIVE_BACKUP',
                notes TEXT NOT NULL DEFAULT '',
                mac TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(device_id) REFERENCES device(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS lag_member (
                lag_id TEXT NOT NULL,
                port_id TEXT NOT NULL,
                PRIMARY KEY (lag_id, port_id),
                FOREIGN KEY(lag_id) REFERENCES lag(id) ON DELETE CASCADE,
                FOREIGN KEY(port_id) REFERENCES port(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS virtual_switch (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                host_device_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT 'vSwitch0',
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(host_device_id) REFERENCES device(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS vswitch_uplink (
                vswitch_id TEXT NOT NULL,
                port_id TEXT NOT NULL,
                PRIMARY KEY (vswitch_id, port_id),
                FOREIGN KEY(vswitch_id) REFERENCES virtual_switch(id) ON DELETE CASCADE,
                FOREIGN KEY(port_id) REFERENCES port(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS port_group (
                id TEXT PRIMARY KEY NOT NULL,
                vswitch_id TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT 'VM Network',
                vlan_id TEXT,
                notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(vswitch_id) REFERENCES virtual_switch(id) ON DELETE CASCADE,
                FOREIGN KEY(vlan_id) REFERENCES vlan(id) ON DELETE SET NULL
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS port_tagged_vlan (
                port_id TEXT NOT NULL,
                vlan_id TEXT NOT NULL,
                PRIMARY KEY (port_id, vlan_id),
                FOREIGN KEY(port_id) REFERENCES port(id) ON DELETE CASCADE,
                FOREIGN KEY(vlan_id) REFERENCES vlan(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS topology_node (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                device_id TEXT NOT NULL UNIQUE,
                x REAL NOT NULL DEFAULT 0,
                y REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(device_id) REFERENCES device(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS topology_link (
                id TEXT PRIMARY KEY NOT NULL,
                site_id TEXT NOT NULL,
                topology_node_a_id TEXT NOT NULL,
                topology_node_b_id TEXT NOT NULL,
                cable_id TEXT,
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(topology_node_a_id) REFERENCES topology_node(id) ON DELETE CASCADE,
                FOREIGN KEY(topology_node_b_id) REFERENCES topology_node(id) ON DELETE CASCADE,
                FOREIGN KEY(cable_id) REFERENCES cable(id) ON DELETE CASCADE
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS floor_plan_asset (
                id TEXT PRIMARY KEY NOT NULL,
                floor_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                x REAL NOT NULL DEFAULT 0,
                y REAL NOT NULL DEFAULT 0,
                rotation REAL NOT NULL DEFAULT 0,
                FOREIGN KEY(floor_id) REFERENCES floor(id) ON DELETE CASCADE,
                FOREIGN KEY(device_id) REFERENCES device(id) ON DELETE CASCADE,
                UNIQUE(floor_id, device_id)
            )
            """
        )

        self._ensure_column(con, "port", "access_vlan_id", "TEXT")
        self._ensure_column(con, "port", "mode", "TEXT NOT NULL DEFAULT 'ACCESS'")
        self._ensure_column(con, "port", "mac", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(con, "port", "side", "TEXT NOT NULL DEFAULT 'NONE'")
        self._ensure_column(con, "port", "position", "INTEGER NOT NULL DEFAULT 0")
        self._ensure_column(con, "building", "address", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(con, "building", "notes", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(con, "ip_address", "lag_id", "TEXT")
        self._ensure_column(con, "vlan", "description", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(con, "lag", "mac", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(con, "device", "rack_u", "INTEGER")
        self._ensure_column(con, "device", "rack_u_height", "INTEGER NOT NULL DEFAULT 1")
        self._ensure_column(con, "device", "host_device_id", "TEXT")
        self._ensure_column(con, "port", "host_port_id", "TEXT")
        self._ensure_column(con, "port", "port_group_id", "TEXT")
        self._ensure_column(con, "cable", "color", "TEXT NOT NULL DEFAULT ''")
        self._ensure_column(con, "cable", "purpose", "TEXT NOT NULL DEFAULT ''")
        con.commit()

    def _ensure_column(
        self,
        con: sqlite3.Connection,
        table: str,
        column: str,
        decl: str,
    ) -> None:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        names = {str(r[1]) for r in rows}
        if column not in names:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

    def create_new_project(self, file_path: str, meta: ProjectMeta) -> None:
        file = Path(file_path)
        file.parent.mkdir(parents=True, exist_ok=True)

        with self._connect(file_path) as con:
            self._ensure_schema(con)

            # Один файл = один проект.
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("DELETE FROM floor_plan_asset")
            con.execute("DELETE FROM topology_link")
            con.execute("DELETE FROM topology_node")
            con.execute("DELETE FROM ip_address")
            con.execute("DELETE FROM lag_member")
            con.execute("DELETE FROM lag")
            con.execute("DELETE FROM vswitch_uplink")
            con.execute("DELETE FROM port_group")
            con.execute("DELETE FROM virtual_switch")
            con.execute("DELETE FROM port_tagged_vlan")
            con.execute("DELETE FROM cable")
            con.execute("DELETE FROM port")
            con.execute("DELETE FROM vlan")
            con.execute("DELETE FROM device")
            con.execute("DELETE FROM device_type")
            con.execute("DELETE FROM rack")
            con.execute("DELETE FROM room")
            con.execute("DELETE FROM floor")
            con.execute("DELETE FROM building")
            con.execute("DELETE FROM site")
            con.execute("DELETE FROM project_meta")

            site = Site(project_id=meta.id, name="Площадка")

            con.execute(
                """
                INSERT INTO project_meta(id, name, schema_version, origin, revision, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    _uuid_str(meta.id),
                    meta.name,
                    meta.schema_version,
                    meta.origin,
                    meta.revision,
                    _dt_to_str(meta.updated_at),
                ),
            )
            con.execute(
                """
                INSERT INTO site(id, project_id, name, address, notes)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    _uuid_str(site.id),
                    _uuid_str(meta.id),
                    site.name,
                    site.address,
                    site.notes,
                ),
            )
            con.commit()

    def load_project(self, file_path: str) -> ProjectSnapshot:
        with self._connect(file_path) as con:
            self._ensure_schema(con)

            meta_row = con.execute(
                """
                SELECT id, name, schema_version, origin, revision, updated_at
                FROM project_meta
                LIMIT 1
                """
            ).fetchone()

            if meta_row is None:
                # В MVP ожидаем, что проект всегда содержит meta.
                raise ValueError(f"Файл проекта не содержит ProjectMeta: {file_path}")

            meta = ProjectMeta(
                id=UUID(meta_row[0]),
                name=meta_row[1],
                schema_version=int(meta_row[2]),
                origin=meta_row[3],
                revision=int(meta_row[4]),
                updated_at=_dt_from_str(meta_row[5]),
            )

            sites_rows = con.execute(
                """
                SELECT id, project_id, name, address, notes
                FROM site
                WHERE project_id = ?
                """,
                (_uuid_str(meta.id),),
            ).fetchall()

            sites = [
                Site(
                    id=UUID(r[0]),
                    project_id=UUID(r[1]),
                    name=r[2],
                    address=r[3],
                    notes=r[4],
                )
                for r in sites_rows
            ]

            if not sites:
                return ProjectSnapshot(meta=meta, sites=[])

            site_ids = [_uuid_str(s.id) for s in sites]

            def _in_placeholders(values: list[str]) -> str:
                return ",".join(["?"] * len(values))

            placeholders_sites = _in_placeholders(site_ids)

            buildings_rows = con.execute(
                f"""
                SELECT id, site_id, name, address, notes
                FROM building
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            buildings = [
                Building(
                    id=UUID(r[0]),
                    site_id=UUID(r[1]),
                    name=r[2],
                    address=r[3] or "",
                    notes=r[4] or "",
                )
                for r in buildings_rows
            ]

            building_ids = [r[0] for r in buildings_rows]
            floors: list[Floor] = []
            rooms: list[Room] = []
            racks: list[Rack] = []
            if building_ids:
                placeholders_buildings = _in_placeholders(building_ids)
                floors_rows = con.execute(
                    f"""
                    SELECT id, building_id, name, level, plan_image_relpath, scale_m_per_px
                    FROM floor
                    WHERE building_id IN ({placeholders_buildings})
                    """,
                    building_ids,
                ).fetchall()
                floors = [
                    Floor(
                        id=UUID(r[0]),
                        building_id=UUID(r[1]),
                        name=r[2],
                        level=float(r[3]),
                        plan_image_relpath=r[4],
                        scale_m_per_px=float(r[5]),
                    )
                    for r in floors_rows
                ]

                floor_ids = [r[0] for r in floors_rows]
                if floor_ids:
                    placeholders_floors = _in_placeholders(floor_ids)
                    rooms_rows = con.execute(
                        f"""
                        SELECT id, floor_id, name
                        FROM room
                        WHERE floor_id IN ({placeholders_floors})
                        """,
                        floor_ids,
                    ).fetchall()
                    rooms = [
                        Room(id=UUID(r[0]), floor_id=UUID(r[1]), name=r[2]) for r in rooms_rows
                    ]

                    room_ids = [r[0] for r in rooms_rows]
                    if room_ids:
                        placeholders_rooms = _in_placeholders(room_ids)
                        racks_rows = con.execute(
                            f"""
                            SELECT id, room_id, name, units, unit_start, unit_end
                            FROM rack
                            WHERE room_id IN ({placeholders_rooms})
                            """,
                            room_ids,
                        ).fetchall()
                        racks = [
                            Rack(
                                id=UUID(r[0]),
                                room_id=UUID(r[1]),
                                name=r[2],
                                units=int(r[3]),
                                unit_start=int(r[4]),
                                unit_end=int(r[5]),
                            )
                            for r in racks_rows
                        ]

            # CMDB lite: device types, devices, ports, cables, VLAN/IP
            device_types_rows = con.execute(
                f"""
                SELECT id, site_id, vendor, model, role, port_template
                FROM device_type
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            device_types = [
                DeviceType(
                    id=UUID(r[0]),
                    site_id=UUID(r[1]),
                    vendor=r[2],
                    model=r[3],
                    role=DeviceRole(r[4]),
                    port_template=json.loads(r[5] or "[]"),
                )
                for r in device_types_rows
            ]

            device_rows = con.execute(
                f"""
                SELECT id, site_id, device_type_id, hostname, serial, inventory_tag, role,
                       room_id, rack_id, rack_u, rack_u_height, host_device_id
                FROM device
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            devices = [
                Device(
                    id=UUID(r[0]),
                    site_id=UUID(r[1]),
                    device_type_id=UUID(r[2]),
                    hostname=r[3],
                    serial=r[4],
                    inventory_tag=r[5],
                    role=DeviceRole(r[6]),
                    room_id=UUID(r[7]) if r[7] is not None else None,
                    rack_id=UUID(r[8]) if r[8] is not None else None,
                    rack_u=int(r[9]) if len(r) > 9 and r[9] is not None else None,
                    rack_u_height=int(r[10]) if len(r) > 10 and r[10] is not None else 1,
                    host_device_id=(
                        UUID(r[11]) if len(r) > 11 and r[11] is not None else None
                    ),
                )
                for r in device_rows
            ]

            device_ids = [r[0] for r in device_rows]
            ports: list[Port] = []
            if device_ids:
                placeholders_devices = _in_placeholders(device_ids)
                ports_rows = con.execute(
                    f"""
                    SELECT id, device_id, name, speed, media, status, access_vlan_id, mode,
                           mac, side, position, host_port_id, port_group_id
                    FROM port
                    WHERE device_id IN ({placeholders_devices})
                    """,
                    device_ids,
                ).fetchall()
                ports = [
                    Port(
                        id=UUID(r[0]),
                        device_id=UUID(r[1]),
                        name=r[2],
                        speed=int(r[3]),
                        media=PortMedia(r[4]),
                        status=PortStatus(r[5]),
                        access_vlan_id=UUID(r[6]) if r[6] is not None else None,
                        mode=PortMode(r[7] or PortMode.ACCESS.value),
                        mac=(r[8] or "") if len(r) > 8 else "",
                        side=(
                            PortSide(r[9])
                            if len(r) > 9 and r[9] in {s.value for s in PortSide}
                            else PortSide.NONE
                        ),
                        position=int(r[10]) if len(r) > 10 and r[10] is not None else 0,
                        host_port_id=(
                            UUID(r[11]) if len(r) > 11 and r[11] is not None else None
                        ),
                        port_group_id=(
                            UUID(r[12]) if len(r) > 12 and r[12] is not None else None
                        ),
                    )
                    for r in ports_rows
                ]
                if ports:
                    port_ids = [_uuid_str(p.id) for p in ports]
                    placeholders_ports = _in_placeholders(port_ids)
                    tagged_rows = con.execute(
                        f"""
                        SELECT port_id, vlan_id
                        FROM port_tagged_vlan
                        WHERE port_id IN ({placeholders_ports})
                        """,
                        port_ids,
                    ).fetchall()
                    tagged_map: dict[UUID, list[UUID]] = {p.id: [] for p in ports}
                    for port_id_raw, vlan_id_raw in tagged_rows:
                        tagged_map[UUID(port_id_raw)].append(UUID(vlan_id_raw))
                    for port in ports:
                        port.tagged_vlan_ids = tagged_map.get(port.id, [])


            cable_rows = con.execute(
                f"""
                SELECT id, site_id, label, kind, category, length_m, end_a_port_id, end_b_port_id,
                       color, purpose
                FROM cable
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            cables = [
                Cable(
                    id=UUID(r[0]),
                    site_id=UUID(r[1]),
                    label=r[2],
                    kind=CableKind(r[3]),
                    category=CableCategory(r[4]),
                    length_m=float(r[5]) if r[5] is not None else None,
                    end_a_port_id=UUID(r[6]),
                    end_b_port_id=UUID(r[7]),
                    color=(r[8] or "") if len(r) > 8 else "",
                    purpose=(r[9] or "") if len(r) > 9 else "",
                )
                for r in cable_rows
            ]

            vlan_rows = con.execute(
                f"""
                SELECT id, site_id, vlan_id, name, description
                FROM vlan
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            vlans = [
                Vlan(
                    id=UUID(r[0]),
                    site_id=UUID(r[1]),
                    vlan_id=int(r[2]),
                    name=r[3] or "",
                    description=r[4] or "",
                )
                for r in vlan_rows
            ]

            ip_rows = con.execute(
                f"""
                SELECT id, site_id, port_id, address, cidr, gateway, lag_id
                FROM ip_address
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            ips = [
                IpAddress(
                    id=UUID(r[0]),
                    site_id=UUID(r[1]),
                    port_id=UUID(r[2]) if r[2] is not None else None,
                    address=r[3],
                    cidr=r[4],
                    gateway=r[5],
                    lag_id=UUID(r[6]) if len(r) > 6 and r[6] is not None else None,
                )
                for r in ip_rows
            ]

            lags: list[Lag] = []
            try:
                lag_rows = con.execute(
                    f"""
                    SELECT id, site_id, device_id, name, mode, notes, mac
                    FROM lag
                    WHERE site_id IN ({placeholders_sites})
                    """,
                    site_ids,
                ).fetchall()
                member_map: dict[str, list[UUID]] = {}
                if lag_rows:
                    lag_ids = [r[0] for r in lag_rows]
                    placeholders_lags = _in_placeholders(lag_ids)
                    member_rows = con.execute(
                        f"""
                        SELECT lag_id, port_id
                        FROM lag_member
                        WHERE lag_id IN ({placeholders_lags})
                        """,
                        lag_ids,
                    ).fetchall()
                    for lag_id, port_id in member_rows:
                        member_map.setdefault(str(lag_id), []).append(UUID(str(port_id)))
                lags = [
                    Lag(
                        id=UUID(r[0]),
                        site_id=UUID(r[1]),
                        device_id=UUID(r[2]),
                        name=r[3],
                        mode=(
                            LagMode(r[4])
                            if r[4] in {m.value for m in LagMode}
                            else LagMode.ACTIVE_BACKUP
                        ),
                        notes=r[5] or "",
                        mac=(r[6] or "") if len(r) > 6 else "",
                        member_port_ids=member_map.get(str(r[0]), []),
                    )
                    for r in lag_rows
                ]
            except sqlite3.OperationalError:
                lags = []

            virtual_switches: list[VirtualSwitch] = []
            port_groups: list[PortGroup] = []
            try:
                vs_rows = con.execute(
                    f"""
                    SELECT id, site_id, host_device_id, name, notes
                    FROM virtual_switch
                    WHERE site_id IN ({placeholders_sites})
                    """,
                    site_ids,
                ).fetchall()
                uplink_map: dict[str, list[UUID]] = {}
                if vs_rows:
                    vs_ids = [r[0] for r in vs_rows]
                    placeholders_vs = _in_placeholders(vs_ids)
                    uplink_rows = con.execute(
                        f"""
                        SELECT vswitch_id, port_id
                        FROM vswitch_uplink
                        WHERE vswitch_id IN ({placeholders_vs})
                        """,
                        vs_ids,
                    ).fetchall()
                    for vs_id, port_id in uplink_rows:
                        uplink_map.setdefault(str(vs_id), []).append(UUID(str(port_id)))
                virtual_switches = [
                    VirtualSwitch(
                        id=UUID(r[0]),
                        site_id=UUID(r[1]),
                        host_device_id=UUID(r[2]),
                        name=r[3] or "vSwitch0",
                        notes=r[4] or "",
                        uplink_port_ids=uplink_map.get(str(r[0]), []),
                    )
                    for r in vs_rows
                ]
                if vs_rows:
                    vs_ids = [r[0] for r in vs_rows]
                    placeholders_vs = _in_placeholders(vs_ids)
                    pg_rows = con.execute(
                        f"""
                        SELECT id, vswitch_id, name, vlan_id, notes
                        FROM port_group
                        WHERE vswitch_id IN ({placeholders_vs})
                        """,
                        vs_ids,
                    ).fetchall()
                    port_groups = [
                        PortGroup(
                            id=UUID(r[0]),
                            vswitch_id=UUID(r[1]),
                            name=r[2] or "VM Network",
                            vlan_id=UUID(r[3]) if r[3] is not None else None,
                            notes=r[4] or "",
                        )
                        for r in pg_rows
                    ]
            except sqlite3.OperationalError:
                virtual_switches = []
                port_groups = []

            topology_nodes: list[TopologyNode] = []
            topology_links: list[TopologyLink] = []
            try:
                node_rows = con.execute(
                    f"""
                    SELECT id, site_id, device_id, x, y
                    FROM topology_node
                    WHERE site_id IN ({placeholders_sites})
                    """,
                    site_ids,
                ).fetchall()
                topology_nodes = [
                    TopologyNode(
                        id=UUID(r[0]),
                        site_id=UUID(r[1]),
                        device_id=UUID(r[2]),
                        x=float(r[3]),
                        y=float(r[4]),
                    )
                    for r in node_rows
                ]

                link_rows = con.execute(
                    f"""
                    SELECT id, site_id, topology_node_a_id, topology_node_b_id, cable_id
                    FROM topology_link
                    WHERE site_id IN ({placeholders_sites})
                    """,
                    site_ids,
                ).fetchall()
                topology_links = [
                    TopologyLink(
                        id=UUID(r[0]),
                        site_id=UUID(r[1]),
                        topology_node_a_id=UUID(r[2]),
                        topology_node_b_id=UUID(r[3]),
                        cable_id=UUID(r[4]) if r[4] is not None else None,
                    )
                    for r in link_rows
                ]
            except sqlite3.OperationalError:
                # Старые .lanproj без таблиц топологии — схема досоздастся при save.
                topology_nodes = []
                topology_links = []

            floor_plan_assets: list[FloorPlanAsset] = []
            try:
                asset_rows = con.execute(
                    f"""
                    SELECT a.id, a.floor_id, a.device_id, a.x, a.y, a.rotation
                    FROM floor_plan_asset a
                    JOIN floor f ON f.id = a.floor_id
                    JOIN building b ON b.id = f.building_id
                    WHERE b.site_id IN ({placeholders_sites})
                    """,
                    site_ids,
                ).fetchall()
                floor_plan_assets = [
                    FloorPlanAsset(
                        id=UUID(r[0]),
                        floor_id=UUID(r[1]),
                        device_id=UUID(r[2]),
                        x=float(r[3]),
                        y=float(r[4]),
                        rotation=float(r[5]),
                    )
                    for r in asset_rows
                ]
            except sqlite3.OperationalError:
                floor_plan_assets = []

            return ProjectSnapshot(
                meta=meta,
                sites=sites,
                buildings=buildings,
                floors=floors,
                rooms=rooms,
                racks=racks,
                device_types=device_types,
                devices=devices,
                ports=ports,
                cables=cables,
                vlans=vlans,
                lags=lags,
                virtual_switches=virtual_switches,
                port_groups=port_groups,
                ips=ips,
                topology_nodes=topology_nodes,
                topology_links=topology_links,
                floor_plan_assets=floor_plan_assets,
            )

    def save_project(self, file_path: str, snapshot: ProjectSnapshot) -> None:
        file = Path(file_path)
        file.parent.mkdir(parents=True, exist_ok=True)

        with self._connect(file_path) as con:
            self._ensure_schema(con)

            meta = snapshot.meta

            # Один файл = один проект: полностью очищаем содержимое перед записью.
            # Иначе после «Новый» + сохранение поверх старого файла в БД остаются
            # старые project_meta, а load_project(LIMIT 1) может открыть не тот проект.
            con.execute("PRAGMA foreign_keys = ON")
            con.execute("DELETE FROM floor_plan_asset")
            con.execute("DELETE FROM topology_link")
            con.execute("DELETE FROM topology_node")
            con.execute("DELETE FROM ip_address")
            con.execute("DELETE FROM lag_member")
            con.execute("DELETE FROM lag")
            con.execute("DELETE FROM vswitch_uplink")
            con.execute("DELETE FROM port_group")
            con.execute("DELETE FROM virtual_switch")
            con.execute("DELETE FROM port_tagged_vlan")
            con.execute("DELETE FROM cable")
            con.execute("DELETE FROM port")
            con.execute("DELETE FROM vlan")
            con.execute("DELETE FROM device")
            con.execute("DELETE FROM device_type")
            con.execute("DELETE FROM rack")
            con.execute("DELETE FROM room")
            con.execute("DELETE FROM floor")
            con.execute("DELETE FROM building")
            con.execute("DELETE FROM site")
            con.execute("DELETE FROM project_meta")

            con.execute(
                """
                INSERT INTO project_meta(id, name, schema_version, origin, revision, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                """,
                (
                    _uuid_str(meta.id),
                    meta.name,
                    meta.schema_version,
                    meta.origin,
                    meta.revision,
                    _dt_to_str(meta.updated_at),
                ),
            )

            for s in snapshot.sites:
                con.execute(
                    """
                    INSERT INTO site(id, project_id, name, address, notes)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(s.id),
                        _uuid_str(meta.id),
                        s.name,
                        s.address,
                        s.notes,
                    ),
                )

            for b in snapshot.buildings:
                con.execute(
                    """
                    INSERT INTO building(id, site_id, name, address, notes)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(b.id),
                        _uuid_str(b.site_id),
                        b.name,
                        b.address,
                        b.notes,
                    ),
                )

            for f in snapshot.floors:
                con.execute(
                    """
                    INSERT INTO floor(id, building_id, name, level, plan_image_relpath, scale_m_per_px)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(f.id),
                        _uuid_str(f.building_id),
                        f.name,
                        float(f.level),
                        f.plan_image_relpath,
                        float(f.scale_m_per_px),
                    ),
                )

            for r in snapshot.rooms:
                con.execute(
                    """
                    INSERT INTO room(id, floor_id, name)
                    VALUES(?, ?, ?)
                    """,
                    (_uuid_str(r.id), _uuid_str(r.floor_id), r.name),
                )

            for r in snapshot.racks:
                con.execute(
                    """
                    INSERT INTO rack(id, room_id, name, units, unit_start, unit_end)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(r.id),
                        _uuid_str(r.room_id),
                        r.name,
                        int(r.units),
                        int(r.unit_start),
                        int(r.unit_end),
                    ),
                )

            for dt in snapshot.device_types:
                con.execute(
                    """
                    INSERT INTO device_type(id, site_id, vendor, model, role, port_template)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(dt.id),
                        _uuid_str(dt.site_id),
                        dt.vendor,
                        dt.model,
                        _enum_value(dt.role),
                        json.dumps(dt.port_template, ensure_ascii=False),
                    ),
                )

            for d in snapshot.devices:
                con.execute(
                    """
                    INSERT INTO device(
                        id, site_id, device_type_id, hostname, serial, inventory_tag, role,
                        room_id, rack_id, rack_u, rack_u_height, host_device_id
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(d.id),
                        _uuid_str(d.site_id),
                        _uuid_str(d.device_type_id),
                        d.hostname,
                        d.serial,
                        d.inventory_tag,
                        _enum_value(d.role),
                        _uuid_str(d.room_id) if d.room_id is not None else None,
                        _uuid_str(d.rack_id) if d.rack_id is not None else None,
                        int(d.rack_u) if d.rack_u is not None else None,
                        int(d.rack_u_height or 1),
                        (
                            _uuid_str(d.host_device_id)
                            if d.host_device_id is not None
                            else None
                        ),
                    ),
                )

            for v in snapshot.vlans:
                con.execute(
                    """
                    INSERT INTO vlan(id, site_id, vlan_id, name, description)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(v.id),
                        _uuid_str(v.site_id),
                        int(v.vlan_id),
                        v.name,
                        v.description,
                    ),
                )

            for p in snapshot.ports:
                con.execute(
                    """
                    INSERT INTO port(
                        id, device_id, name, speed, media, status, access_vlan_id, mode,
                        mac, side, position, host_port_id, port_group_id
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(p.id),
                        _uuid_str(p.device_id),
                        p.name,
                        int(p.speed),
                        _enum_value(p.media),
                        _enum_value(p.status),
                        _uuid_str(p.access_vlan_id) if p.access_vlan_id is not None else None,
                        _enum_value(p.mode),
                        p.mac,
                        _enum_value(p.side),
                        int(p.position or 0),
                        _uuid_str(p.host_port_id) if p.host_port_id is not None else None,
                        (
                            _uuid_str(p.port_group_id)
                            if p.port_group_id is not None
                            else None
                        ),
                    ),
                )
                for vlan_uuid in p.tagged_vlan_ids:
                    con.execute(
                        """
                        INSERT INTO port_tagged_vlan(port_id, vlan_id)
                        VALUES(?, ?)
                        """,
                        (_uuid_str(p.id), _uuid_str(vlan_uuid)),
                    )

            for c in snapshot.cables:
                con.execute(
                    """
                    INSERT INTO cable(
                        id, site_id, label, kind, category, length_m, end_a_port_id, end_b_port_id,
                        color, purpose
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(c.id),
                        _uuid_str(c.site_id),
                        c.label,
                        _enum_value(c.kind),
                        _enum_value(c.category),
                        c.length_m if c.length_m is not None else None,
                        _uuid_str(c.end_a_port_id),
                        _uuid_str(c.end_b_port_id),
                        c.color or "",
                        c.purpose or "",
                    ),
                )

            for lag in snapshot.lags:
                con.execute(
                    """
                    INSERT INTO lag(id, site_id, device_id, name, mode, notes, mac)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(lag.id),
                        _uuid_str(lag.site_id),
                        _uuid_str(lag.device_id),
                        lag.name,
                        _enum_value(lag.mode),
                        lag.notes,
                        lag.mac,
                    ),
                )
                for port_id in lag.member_port_ids:
                    con.execute(
                        """
                        INSERT INTO lag_member(lag_id, port_id)
                        VALUES(?, ?)
                        """,
                        (_uuid_str(lag.id), _uuid_str(port_id)),
                    )

            for vs in snapshot.virtual_switches:
                con.execute(
                    """
                    INSERT INTO virtual_switch(id, site_id, host_device_id, name, notes)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(vs.id),
                        _uuid_str(vs.site_id),
                        _uuid_str(vs.host_device_id),
                        vs.name,
                        vs.notes,
                    ),
                )
                for port_id in vs.uplink_port_ids:
                    con.execute(
                        """
                        INSERT INTO vswitch_uplink(vswitch_id, port_id)
                        VALUES(?, ?)
                        """,
                        (_uuid_str(vs.id), _uuid_str(port_id)),
                    )

            for pg in snapshot.port_groups:
                con.execute(
                    """
                    INSERT INTO port_group(id, vswitch_id, name, vlan_id, notes)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(pg.id),
                        _uuid_str(pg.vswitch_id),
                        pg.name,
                        _uuid_str(pg.vlan_id) if pg.vlan_id is not None else None,
                        pg.notes,
                    ),
                )

            for ip in snapshot.ips:
                con.execute(
                    """
                    INSERT INTO ip_address(id, site_id, port_id, address, cidr, gateway, lag_id)
                    VALUES(?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(ip.id),
                        _uuid_str(ip.site_id),
                        _uuid_str(ip.port_id) if ip.port_id is not None else None,
                        ip.address,
                        ip.cidr,
                        ip.gateway,
                        _uuid_str(ip.lag_id) if ip.lag_id is not None else None,
                    ),
                )

            for node in snapshot.topology_nodes:
                con.execute(
                    """
                    INSERT INTO topology_node(id, site_id, device_id, x, y)
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(node.id),
                        _uuid_str(node.site_id),
                        _uuid_str(node.device_id),
                        float(node.x),
                        float(node.y),
                    ),
                )

            for link in snapshot.topology_links:
                con.execute(
                    """
                    INSERT INTO topology_link(
                        id, site_id, topology_node_a_id, topology_node_b_id, cable_id
                    )
                    VALUES(?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(link.id),
                        _uuid_str(link.site_id),
                        _uuid_str(link.topology_node_a_id),
                        _uuid_str(link.topology_node_b_id),
                        _uuid_str(link.cable_id) if link.cable_id is not None else None,
                    ),
                )

            for asset in snapshot.floor_plan_assets:
                con.execute(
                    """
                    INSERT INTO floor_plan_asset(id, floor_id, device_id, x, y, rotation)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(asset.id),
                        _uuid_str(asset.floor_id),
                        _uuid_str(asset.device_id),
                        float(asset.x),
                        float(asset.y),
                        float(asset.rotation),
                    ),
                )

            con.commit()

