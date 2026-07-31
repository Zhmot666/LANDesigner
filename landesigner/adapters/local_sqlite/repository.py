from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import json
from uuid import UUID

from landesigner.domain.entities import (
    Cable,
    Building,
    Device,
    DeviceType,
    Floor,
    IpAddress,
    Port,
    ProjectMeta,
    ProjectSnapshot,
    Rack,
    Room,
    Site,
    Vlan,
)
from landesigner.domain.enums import (
    CableCategory,
    CableKind,
    DeviceRole,
    PortMedia,
    PortMode,
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
                FOREIGN KEY(site_id) REFERENCES site(id) ON DELETE CASCADE,
                FOREIGN KEY(device_type_id) REFERENCES device_type(id) ON DELETE CASCADE,
                FOREIGN KEY(room_id) REFERENCES room(id) ON DELETE SET NULL,
                FOREIGN KEY(rack_id) REFERENCES rack(id) ON DELETE SET NULL
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
            CREATE TABLE IF NOT EXISTS port_tagged_vlan (
                port_id TEXT NOT NULL,
                vlan_id TEXT NOT NULL,
                PRIMARY KEY (port_id, vlan_id),
                FOREIGN KEY(port_id) REFERENCES port(id) ON DELETE CASCADE,
                FOREIGN KEY(vlan_id) REFERENCES vlan(id) ON DELETE CASCADE
            )
            """
        )
        self._ensure_column(con, "port", "access_vlan_id", "TEXT")
        self._ensure_column(con, "port", "mode", "TEXT NOT NULL DEFAULT 'ACCESS'")
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
            con.execute("DELETE FROM ip_address")
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
                SELECT id, site_id, name
                FROM building
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            buildings = [
                Building(id=UUID(r[0]), site_id=UUID(r[1]), name=r[2]) for r in buildings_rows
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
                SELECT id, site_id, device_type_id, hostname, serial, inventory_tag, role, room_id, rack_id
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
                )
                for r in device_rows
            ]

            device_ids = [r[0] for r in device_rows]
            ports: list[Port] = []
            if device_ids:
                placeholders_devices = _in_placeholders(device_ids)
                ports_rows = con.execute(
                    f"""
                    SELECT id, device_id, name, speed, media, status, access_vlan_id, mode
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
                SELECT id, site_id, label, kind, category, length_m, end_a_port_id, end_b_port_id
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
                )
                for r in cable_rows
            ]

            vlan_rows = con.execute(
                f"""
                SELECT id, site_id, vlan_id, name
                FROM vlan
                WHERE site_id IN ({placeholders_sites})
                """,
                site_ids,
            ).fetchall()
            vlans = [
                Vlan(id=UUID(r[0]), site_id=UUID(r[1]), vlan_id=int(r[2]), name=r[3])
                for r in vlan_rows
            ]

            ip_rows = con.execute(
                f"""
                SELECT id, site_id, port_id, address, cidr, gateway
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
                )
                for r in ip_rows
            ]

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
                ips=ips,
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
            con.execute("DELETE FROM ip_address")
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
                    INSERT INTO building(id, site_id, name)
                    VALUES(?, ?, ?)
                    """,
                    (_uuid_str(b.id), _uuid_str(b.site_id), b.name),
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
                        id, site_id, device_type_id, hostname, serial, inventory_tag, role, room_id, rack_id
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )

            for v in snapshot.vlans:
                con.execute(
                    """
                    INSERT INTO vlan(id, site_id, vlan_id, name)
                    VALUES(?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(v.id),
                        _uuid_str(v.site_id),
                        int(v.vlan_id),
                        v.name,
                    ),
                )

            for p in snapshot.ports:
                con.execute(
                    """
                    INSERT INTO port(
                        id, device_id, name, speed, media, status, access_vlan_id, mode
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
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
                        id, site_id, label, kind, category, length_m, end_a_port_id, end_b_port_id
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
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
                    ),
                )

            for ip in snapshot.ips:
                con.execute(
                    """
                    INSERT INTO ip_address(id, site_id, port_id, address, cidr, gateway)
                    VALUES(?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _uuid_str(ip.id),
                        _uuid_str(ip.site_id),
                        _uuid_str(ip.port_id) if ip.port_id is not None else None,
                        ip.address,
                        ip.cidr,
                        ip.gateway,
                    ),
                )

            con.commit()

