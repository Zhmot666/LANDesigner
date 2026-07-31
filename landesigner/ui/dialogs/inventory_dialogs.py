from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
)

from landesigner.domain.entities import Cable, Device, DeviceType, IpAddress, ProjectSnapshot
from landesigner.domain.enums import (
    CableCategory,
    CableKind,
    DeviceRole,
    PortMedia,
    PortMode,
    PortStatus,
)
from landesigner.services import inventory as inventory_service
from landesigner.ui.labels import (
    CABLE_CATEGORY_RU,
    CABLE_KIND_RU,
    DEVICE_ROLE_RU,
    PORT_MEDIA_RU,
    PORT_MODE_RU,
    role_label,
)


def _russian_buttons(buttons: QDialogButtonBox) -> None:
    ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
    cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
    if ok is not None:
        ok.setText("ОК")
    if cancel is not None:
        cancel.setText("Отмена")


class NameDialog(QDialog):
    def __init__(
        self,
        title: str,
        label: str = "Имя",
        initial: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(self)
        if initial:
            self._name.setText(initial)
            self._name.selectAll()
        form.addRow(label, self._name)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def value(self) -> str:
        return self._name.text().strip()


class FloorDialog(QDialog):
    def __init__(
        self,
        initial_name: str = "",
        initial_level: float = 1.0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Этаж" if initial_name else "Добавить этаж")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(self)
        if initial_name:
            self._name.setText(initial_name)
            self._name.selectAll()
        self._level = QSpinBox(self)
        self._level.setRange(-10, 200)
        self._level.setValue(int(initial_level))
        form.addRow("Имя", self._name)
        form.addRow("Уровень", self._level)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, float]:
        return self._name.text().strip() or "Этаж", float(self._level.value())


class RackDialog(QDialog):
    def __init__(
        self,
        initial_name: str = "",
        initial_units: int = 42,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Шкаф" if initial_name else "Добавить шкаф")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(self)
        if initial_name:
            self._name.setText(initial_name)
            self._name.selectAll()
        self._units = QSpinBox(self)
        self._units.setRange(1, 60)
        self._units.setValue(initial_units)
        form.addRow("Имя", self._name)
        form.addRow("Юниты", self._units)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, int]:
        return self._name.text().strip() or "Шкаф", int(self._units.value())


class DeviceTypeDialog(QDialog):
    """Диалог типа устройства с группами портов (разная скорость/среда)."""

    _SPEED_PRESETS = (100, 1000, 2500, 5000, 10000, 25000, 40000, 100000)

    def __init__(self, device_type: DeviceType | None = None, parent=None) -> None:
        super().__init__(parent)
        self._device_type = device_type
        self.setWindowTitle(
            "Тип устройства" if device_type is None else "Редактировать тип устройства"
        )
        self.resize(640, 420)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self._vendor = QLineEdit(self)
        self._model = QLineEdit(self)
        self._role = QComboBox(self)
        for role in DeviceRole:
            self._role.addItem(DEVICE_ROLE_RU[role], role.value)
        self._role.setCurrentIndex(list(DeviceRole).index(DeviceRole.SWITCH))
        form.addRow("Производитель", self._vendor)
        form.addRow("Модель", self._model)
        form.addRow("Роль", self._role)
        layout.addLayout(form)

        layout.addWidget(QLabel("Группы портов (на одном устройстве могут отличаться)", self))

        self._groups = QTableWidget(self)
        self._groups.setColumnCount(5)
        self._groups.setHorizontalHeaderLabels(
            ["Префикс имени", "Кол-во", "Старт №", "Среда", "Скорость"]
        )
        self._groups.horizontalHeader().setStretchLastSection(True)
        self._groups.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._groups.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._groups)

        group_btns = QHBoxLayout()
        add_btn = QPushButton("Добавить группу", self)
        remove_btn = QPushButton("Удалить группу", self)
        # clicked передаёт bool — связываем через lambda без аргументов
        add_btn.clicked.connect(lambda: self._add_inherited_group_row())
        remove_btn.clicked.connect(lambda: self._remove_group_row())
        group_btns.addWidget(add_btn)
        group_btns.addWidget(remove_btn)
        group_btns.addStretch(1)
        layout.addLayout(group_btns)

        self._preview = QLabel(self)
        self._preview.setWordWrap(True)
        layout.addWidget(self._preview)

        if device_type is not None:
            self._vendor.setText(device_type.vendor)
            self._model.setText(device_type.model)
            role_idx = self._role.findData(
                device_type.role.value
                if hasattr(device_type.role, "value")
                else str(device_type.role)
            )
            if role_idx >= 0:
                self._role.setCurrentIndex(role_idx)
            self._load_groups_from_template(device_type.port_template)
        else:
            # Стартовые группы: типичный access-коммутатор 24×1G + 4×10G.
            self._insert_group_row("Gi1/0/", 24, 1, PortMedia.COPPER, 1000)
            self._insert_group_row("Te1/0/", 4, 1, PortMedia.FIBER, 10000)

        self._update_preview()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_media_combo(self, selected: PortMedia = PortMedia.COPPER) -> QComboBox:
        combo = QComboBox(self)
        selected_value = selected.value if isinstance(selected, PortMedia) else str(selected)
        for media in PortMedia:
            combo.addItem(PORT_MEDIA_RU[media], media.value)
        idx = combo.findData(selected_value)
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(lambda _=0: self._update_preview())
        return combo

    def _make_speed_combo(self, selected: int = 1000) -> QComboBox:
        combo = QComboBox(self)
        combo.setEditable(True)
        for speed in self._SPEED_PRESETS:
            combo.addItem(f"{speed} Мбит/с", speed)
        idx = combo.findData(int(selected))
        if idx >= 0:
            combo.setCurrentIndex(idx)
        else:
            combo.setEditText(str(selected))
        combo.currentIndexChanged.connect(lambda _=0: self._update_preview())
        combo.editTextChanged.connect(lambda _=0: self._update_preview())
        return combo

    def _add_inherited_group_row(self) -> None:
        """Добавляет строку, наследуя свойства выбранной или последней группы."""
        prefix = "Gi1/0/"
        count = 8
        start = 1
        media = PortMedia.COPPER
        speed = 1000

        if self._groups.rowCount() > 0:
            src = self._groups.currentRow()
            if src < 0:
                src = self._groups.rowCount() - 1
            src_prefix = self._groups.cellWidget(src, 0)
            src_count = self._groups.cellWidget(src, 1)
            src_start = self._groups.cellWidget(src, 2)
            src_media = self._groups.cellWidget(src, 3)
            src_speed = self._groups.cellWidget(src, 4)
            if src_prefix is not None:
                prefix = src_prefix.text()
            if src_count is not None:
                count = int(src_count.value())
            if src_start is not None and src_count is not None:
                start = int(src_start.value()) + int(src_count.value())
            if src_media is not None and src_media.currentData() is not None:
                try:
                    media = PortMedia(str(src_media.currentData()))
                except ValueError:
                    media = PortMedia.COPPER
            if src_speed is not None:
                speed = self._speed_from_combo(src_speed)

        self._insert_group_row(prefix, count, start, media, speed)
        self._update_preview()

    def _remove_group_row(self) -> None:
        row = self._groups.currentRow()
        if row < 0:
            return
        self._groups.removeRow(row)
        self._update_preview()

    def _speed_from_combo(self, combo: QComboBox) -> int:
        data = combo.currentData()
        if data is not None:
            try:
                return int(data)
            except (TypeError, ValueError):
                pass
        text = combo.currentText().replace("Мбит/с", "").strip()
        try:
            return int(text)
        except ValueError:
            return 1000

    def port_groups(self) -> list[dict]:
        groups: list[dict] = []
        for row in range(self._groups.rowCount()):
            prefix_w = self._groups.cellWidget(row, 0)
            count_w = self._groups.cellWidget(row, 1)
            start_w = self._groups.cellWidget(row, 2)
            media_w = self._groups.cellWidget(row, 3)
            speed_w = self._groups.cellWidget(row, 4)
            if not all([prefix_w, count_w, start_w, media_w, speed_w]):
                continue
            media_raw = media_w.currentData()
            media = str(media_raw) if media_raw is not None else PortMedia.COPPER.value
            groups.append(
                {
                    "prefix": prefix_w.text().strip() or "Port",
                    "count": int(count_w.value()),
                    "start": int(start_w.value()),
                    "media": media,
                    "speed": self._speed_from_combo(speed_w),
                }
            )
        return groups

    def _load_groups_from_template(self, template: list[dict]) -> None:
        """Сворачивает плоский шаблон обратно в группы подряд идущих одинаковых портов."""
        self._groups.setRowCount(0)
        if not template:
            self._insert_group_row("Gi1/0/", 8, 1, PortMedia.COPPER, 1000)
            return

        current_prefix = None
        current_media = None
        current_speed = None
        current_start = None
        current_count = 0
        current_next = None

        for item in template:
            name = str(item.get("name", "Port"))
            media = str(item.get("media", PortMedia.COPPER.value))
            speed = int(item.get("speed", 1000))

            prefix = name
            number = None
            i = len(name) - 1
            while i >= 0 and name[i].isdigit():
                i -= 1
            if i < len(name) - 1:
                prefix = name[: i + 1]
                number = int(name[i + 1 :])

            if (
                current_prefix == prefix
                and current_media == media
                and current_speed == speed
                and number is not None
                and current_next == number
            ):
                current_count += 1
                current_next = number + 1
                continue

            if current_prefix is not None:
                try:
                    media_enum = PortMedia(current_media)
                except ValueError:
                    media_enum = PortMedia.COPPER
                self._insert_group_row(
                    current_prefix,
                    current_count,
                    current_start if current_start is not None else 1,
                    media_enum,
                    current_speed if current_speed is not None else 1000,
                )

            current_prefix = prefix
            current_media = media
            current_speed = speed
            current_start = number if number is not None else 1
            current_count = 1
            current_next = (number + 1) if number is not None else None

        if current_prefix is not None:
            try:
                media_enum = PortMedia(current_media)
            except ValueError:
                media_enum = PortMedia.COPPER
            self._insert_group_row(
                current_prefix,
                current_count,
                current_start if current_start is not None else 1,
                media_enum,
                current_speed if current_speed is not None else 1000,
            )

    def _insert_group_row(
        self,
        prefix: str,
        count: int,
        start: int,
        media: PortMedia,
        speed: int,
    ) -> None:
        row = self._groups.rowCount()
        self._groups.insertRow(row)

        prefix_edit = QLineEdit(str(prefix), self)
        prefix_edit.textChanged.connect(lambda _=0: self._update_preview())
        self._groups.setCellWidget(row, 0, prefix_edit)

        count_spin = QSpinBox(self)
        count_spin.setRange(1, 256)
        count_spin.setValue(int(count))
        count_spin.valueChanged.connect(lambda _=0: self._update_preview())
        self._groups.setCellWidget(row, 1, count_spin)

        start_spin = QSpinBox(self)
        start_spin.setRange(0, 9999)
        start_spin.setValue(int(start))
        start_spin.valueChanged.connect(lambda _=0: self._update_preview())
        self._groups.setCellWidget(row, 2, start_spin)

        if not isinstance(media, PortMedia):
            try:
                media = PortMedia(str(media))
            except ValueError:
                media = PortMedia.COPPER

        self._groups.setCellWidget(row, 3, self._make_media_combo(media))
        self._groups.setCellWidget(row, 4, self._make_speed_combo(int(speed)))

    def _update_preview(self) -> None:
        from landesigner.services.inventory import build_port_template

        groups = self.port_groups()
        template = build_port_template(groups) if groups else []
        if not template:
            self._preview.setText("Превью: нет портов")
            return
        speeds = sorted({int(p["speed"]) for p in template})
        speed_txt = "/".join(f"{s} Мбит/с" for s in speeds)
        sample = ", ".join(p["name"] for p in template[:3])
        if len(template) > 3:
            sample += ", …"
        self._preview.setText(
            f"Превью: {len(template)} порт(ов), скорости: {speed_txt}. Примеры: {sample}"
        )

    def values(self) -> tuple[str, str, DeviceRole, list[dict]]:
        role_raw = self._role.currentData()
        role = role_raw if isinstance(role_raw, DeviceRole) else DeviceRole(str(role_raw))
        return (
            self._vendor.text().strip() or "Производитель",
            self._model.text().strip() or "Модель",
            role,
            self.port_groups(),
        )


class DeviceDialog(QDialog):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        device: Device | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Устройство" if device is None else "Редактировать устройство")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._type = QComboBox(self)
        for dt in snapshot.device_types:
            label = f"{dt.vendor} {dt.model} ({role_label(dt.role)})"
            self._type.addItem(label, str(dt.id))

        self._hostname = QLineEdit(self)
        self._serial = QLineEdit(self)
        self._tag = QLineEdit(self)

        self._room = QComboBox(self)
        self._room.addItem("(без помещения)", None)
        for room in snapshot.rooms:
            self._room.addItem(room.name, str(room.id))

        form.addRow("Тип", self._type)
        form.addRow("Имя хоста", self._hostname)
        form.addRow("Серийный номер", self._serial)
        form.addRow("Инв. номер", self._tag)
        form.addRow("Помещение", self._room)
        layout.addLayout(form)

        if not snapshot.device_types:
            layout.addWidget(QLabel("Сначала создайте тип устройства.", self))

        if device is not None:
            self._type.setEnabled(False)
            idx = self._type.findData(str(device.device_type_id))
            if idx >= 0:
                self._type.setCurrentIndex(idx)
            self._hostname.setText(device.hostname)
            self._serial.setText(device.serial)
            self._tag.setText(device.inventory_tag)
            if device.room_id is not None:
                ridx = self._room.findData(str(device.room_id))
                if ridx >= 0:
                    self._room.setCurrentIndex(ridx)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[UUID, str, str, str, UUID | None]:
        type_raw = self._type.currentData()
        room_raw = self._room.currentData()
        type_id = UUID(str(type_raw)) if type_raw is not None else None
        room_id = UUID(str(room_raw)) if room_raw is not None else None
        return (
            type_id,  # type: ignore[return-value]
            self._hostname.text().strip(),
            self._serial.text().strip(),
            self._tag.text().strip(),
            room_id,
        )

    def is_valid(self) -> bool:
        return self._type.currentData() is not None and bool(self._hostname.text().strip())


class CableDialog(QDialog):
    """Создание или правка метки/вида кабеля между двумя портами."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        cable: Cable | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._cable = cable
        self.setWindowTitle("Кабель" if cable is None else "Редактировать кабель")
        self.resize(520, 280)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._device_a = QComboBox(self)
        self._port_a = QComboBox(self)
        self._device_b = QComboBox(self)
        self._port_b = QComboBox(self)
        self._label = QLineEdit(self)
        self._kind = QComboBox(self)
        self._category = QComboBox(self)
        self._length = QDoubleSpinBox(self)
        self._length.setRange(0.0, 10000.0)
        self._length.setDecimals(1)
        self._length.setSuffix(" м")
        self._length.setSpecialValueText("—")
        self._length.setValue(0.0)

        for kind in CableKind:
            self._kind.addItem(CABLE_KIND_RU[kind], kind.value)
        for cat in CableCategory:
            self._category.addItem(CABLE_CATEGORY_RU[cat], cat.value)

        for device in snapshot.devices:
            text = device.hostname or str(device.id)
            self._device_a.addItem(text, str(device.id))
            self._device_b.addItem(text, str(device.id))

        form.addRow("Устройство A", self._device_a)
        form.addRow("Порт A", self._port_a)
        form.addRow("Устройство B", self._device_b)
        form.addRow("Порт B", self._port_b)
        form.addRow("Метка", self._label)
        form.addRow("Вид", self._kind)
        form.addRow("Категория", self._category)
        form.addRow("Длина", self._length)
        layout.addLayout(form)

        self._hint = QLabel(self)
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)

        if cable is not None:
            self._device_a.setEnabled(False)
            self._port_a.setEnabled(False)
            self._device_b.setEnabled(False)
            self._port_b.setEnabled(False)
            self._fill_edit(cable)
        else:
            self._device_a.currentIndexChanged.connect(self._reload_ports_a)
            self._device_b.currentIndexChanged.connect(self._reload_ports_b)
            self._port_a.currentIndexChanged.connect(self._guess_kind)
            self._port_b.currentIndexChanged.connect(self._guess_kind)
            self._kind.currentIndexChanged.connect(self._sync_category_hint)
            self._reload_ports_a()
            self._reload_ports_b()
            if self._device_b.count() > 1:
                self._device_b.setCurrentIndex(1)
            self._guess_kind()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fill_edit(self, cable: Cable) -> None:
        port_a = next((p for p in self._snapshot.ports if p.id == cable.end_a_port_id), None)
        port_b = next((p for p in self._snapshot.ports if p.id == cable.end_b_port_id), None)
        if port_a is not None:
            self._device_a.setCurrentIndex(self._device_a.findData(str(port_a.device_id)))
            self._reload_ports_a(include_occupied=True)
            self._port_a.setCurrentIndex(self._port_a.findData(str(port_a.id)))
        if port_b is not None:
            self._device_b.setCurrentIndex(self._device_b.findData(str(port_b.device_id)))
            self._reload_ports_b(include_occupied=True)
            self._port_b.setCurrentIndex(self._port_b.findData(str(port_b.id)))
        self._label.setText(cable.label)
        kidx = self._kind.findData(cable.kind.value)
        if kidx >= 0:
            self._kind.setCurrentIndex(kidx)
        cidx = self._category.findData(cable.category.value)
        if cidx >= 0:
            self._category.setCurrentIndex(cidx)
        if cable.length_m is not None:
            self._length.setValue(float(cable.length_m))
        self._hint.setText("Концы кабеля при правке не меняются.")

    def _free_ports_for_device(self, device_id: UUID, *, include_occupied: bool) -> list:
        ports = inventory_service.ports_for_device(self._snapshot, device_id)
        if include_occupied:
            return ports
        result = []
        for port in ports:
            if port.status == PortStatus.DISABLED:
                continue
            if inventory_service.cable_for_port(self._snapshot, port.id) is not None:
                continue
            if port.status == PortStatus.OCCUPIED:
                continue
            if port.media == PortMedia.VIRTUAL:
                continue
            result.append(port)
        return result

    def _reload_ports_a(self, *_args, include_occupied: bool = False) -> None:
        self._port_a.blockSignals(True)
        self._port_a.clear()
        raw = self._device_a.currentData()
        if raw is not None:
            for port in self._free_ports_for_device(UUID(str(raw)), include_occupied=include_occupied):
                self._port_a.addItem(
                    f"{port.name} ({port.speed} Мбит/с, {PORT_MEDIA_RU.get(port.media, port.media.value)})",
                    str(port.id),
                )
        self._port_a.blockSignals(False)
        self._guess_kind()

    def _reload_ports_b(self, *_args, include_occupied: bool = False) -> None:
        self._port_b.blockSignals(True)
        self._port_b.clear()
        raw = self._device_b.currentData()
        if raw is not None:
            for port in self._free_ports_for_device(UUID(str(raw)), include_occupied=include_occupied):
                self._port_b.addItem(
                    f"{port.name} ({port.speed} Мбит/с, {PORT_MEDIA_RU.get(port.media, port.media.value)})",
                    str(port.id),
                )
        self._port_b.blockSignals(False)
        self._guess_kind()

    def _guess_kind(self) -> None:
        if self._cable is not None:
            return
        port_a = self._selected_port(self._port_a)
        port_b = self._selected_port(self._port_b)
        media = None
        if port_a is not None and port_b is not None and port_a.media == port_b.media:
            media = port_a.media
        elif port_a is not None:
            media = port_a.media
        if media is not None and media != PortMedia.VIRTUAL:
            idx = self._kind.findData(media.value)
            if idx >= 0:
                self._kind.blockSignals(True)
                self._kind.setCurrentIndex(idx)
                self._kind.blockSignals(False)
        self._sync_category_hint()

    def _sync_category_hint(self) -> None:
        kind_raw = self._kind.currentData()
        if kind_raw == CableKind.COPPER.value:
            preferred = CableCategory.CAT6.value
            self._hint.setText("Для меди обычно Cat5e/Cat6/Cat6a.")
        elif kind_raw == CableKind.FIBER.value:
            preferred = CableCategory.OM4.value
            self._hint.setText("Для оптики обычно OM3/OM4/OS2.")
        else:
            preferred = CableCategory.OTHER.value
            self._hint.setText("DAC — прямое подключение.")
        if self._cable is None:
            cidx = self._category.findData(preferred)
            if cidx >= 0:
                self._category.setCurrentIndex(cidx)

    def _selected_port(self, combo: QComboBox):
        raw = combo.currentData()
        if raw is None:
            return None
        return next((p for p in self._snapshot.ports if p.id == UUID(str(raw))), None)

    def values(self) -> tuple[UUID, UUID, str, CableKind, CableCategory, float | None]:
        a_raw = self._port_a.currentData()
        b_raw = self._port_b.currentData()
        if a_raw is None or b_raw is None:
            raise ValueError("Выберите оба порта")
        length = float(self._length.value())
        return (
            UUID(str(a_raw)),
            UUID(str(b_raw)),
            self._label.text().strip(),
            CableKind(str(self._kind.currentData())),
            CableCategory(str(self._category.currentData())),
            length if length > 0 else None,
        )

    def is_valid(self) -> bool:
        if self._cable is not None:
            return True
        return self._port_a.currentData() is not None and self._port_b.currentData() is not None


class VlanDialog(QDialog):
    def __init__(
        self,
        initial_vlan_id: int = 10,
        initial_name: str = "",
        *,
        editing: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Изменить VLAN" if editing else "Добавить VLAN")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._vlan_id = QSpinBox(self)
        self._vlan_id.setRange(1, 4094)
        self._vlan_id.setValue(int(initial_vlan_id))
        self._name = QLineEdit(self)
        self._name.setText(initial_name)
        form.addRow("VLAN ID", self._vlan_id)
        form.addRow("Имя", self._name)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, str]:
        return int(self._vlan_id.value()), self._name.text().strip()


class IpDialog(QDialog):
    def __init__(
        self,
        snapshot: ProjectSnapshot,
        ip: IpAddress | None = None,
        preferred_port_id: UUID | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._ip = ip
        self.setWindowTitle("IP-адрес" if ip is None else "Изменить IP-адрес")
        self.resize(480, 260)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._device = QComboBox(self)
        self._port = QComboBox(self)
        self._address = QLineEdit(self)
        self._cidr = QLineEdit(self)
        self._cidr.setPlaceholderText("24")
        self._gateway = QLineEdit(self)

        self._device.addItem("(без порта)", None)
        for device in snapshot.devices:
            self._device.addItem(device.hostname or str(device.id), str(device.id))

        form.addRow("Устройство", self._device)
        form.addRow("Порт", self._port)
        form.addRow("Адрес", self._address)
        form.addRow("Префикс", self._cidr)
        form.addRow("Шлюз", self._gateway)
        layout.addLayout(form)

        self._device.currentIndexChanged.connect(self._reload_ports)

        if ip is not None:
            self._address.setText(ip.address)
            self._cidr.setText(ip.cidr)
            self._gateway.setText(ip.gateway)
            if ip.port_id is not None:
                port = next((p for p in snapshot.ports if p.id == ip.port_id), None)
                if port is not None:
                    didx = self._device.findData(str(port.device_id))
                    if didx >= 0:
                        self._device.setCurrentIndex(didx)
                    self._reload_ports()
                    pidx = self._port.findData(str(port.id))
                    if pidx >= 0:
                        self._port.setCurrentIndex(pidx)
            else:
                self._reload_ports()
        else:
            if preferred_port_id is not None:
                port = next((p for p in snapshot.ports if p.id == preferred_port_id), None)
                if port is not None:
                    didx = self._device.findData(str(port.device_id))
                    if didx >= 0:
                        self._device.setCurrentIndex(didx)
            self._reload_ports()
            if preferred_port_id is not None:
                pidx = self._port.findData(str(preferred_port_id))
                if pidx >= 0:
                    self._port.setCurrentIndex(pidx)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    def _reload_ports(self) -> None:
        self._port.clear()
        self._port.addItem("(не выбран)", None)
        raw = self._device.currentData()
        if raw is None:
            return
        device_id = UUID(str(raw))
        for port in inventory_service.ports_for_device(self._snapshot, device_id):
            self._port.addItem(port.name, str(port.id))

    def values(self) -> tuple[str, str, str, UUID | None]:
        port_raw = self._port.currentData()
        port_id = UUID(str(port_raw)) if port_raw is not None else None
        return (
            self._address.text().strip(),
            self._cidr.text().strip(),
            self._gateway.text().strip(),
            port_id,
        )

    def is_valid(self) -> bool:
        return bool(self._address.text().strip())


class PortNetworkDialog(QDialog):
    """Режим порта, access/native VLAN, tagged VLAN и IP."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        port_id: UUID,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._port_id = port_id
        port = next((p for p in snapshot.ports if p.id == port_id), None)
        title = inventory_service.port_endpoint_label(snapshot, port_id)
        self.setWindowTitle(f"Сеть — {title}")
        self.resize(520, 460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._mode = QComboBox(self)
        for mode in PortMode:
            self._mode.addItem(PORT_MODE_RU[mode], mode.value)
        if port is not None:
            midx = self._mode.findData(port.mode.value)
            if midx >= 0:
                self._mode.setCurrentIndex(midx)

        self._vlan = QComboBox(self)
        self._vlan.addItem("(без VLAN)", None)
        for vlan in sorted(snapshot.vlans, key=lambda v: v.vlan_id):
            label = f"{vlan.vlan_id}" + (f" — {vlan.name}" if vlan.name else "")
            self._vlan.addItem(label, str(vlan.id))
        if port is not None and port.access_vlan_id is not None:
            idx = self._vlan.findData(str(port.access_vlan_id))
            if idx >= 0:
                self._vlan.setCurrentIndex(idx)

        self._tagged = QListWidget(self)
        self._tagged.setMinimumHeight(140)
        selected_tagged = set(port.tagged_vlan_ids) if port is not None else set()
        for vlan in sorted(snapshot.vlans, key=lambda v: v.vlan_id):
            label = f"{vlan.vlan_id}" + (f" — {vlan.name}" if vlan.name else "")
            item = QListWidgetItem(label)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(
                Qt.CheckState.Checked
                if vlan.id in selected_tagged
                else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, str(vlan.id))
            self._tagged.addItem(item)

        existing = inventory_service.ips_for_port(snapshot, port_id)
        self._existing_ip = existing[0] if existing else None

        self._address = QLineEdit(self)
        self._cidr = QLineEdit(self)
        self._cidr.setPlaceholderText("24")
        self._gateway = QLineEdit(self)
        if self._existing_ip is not None:
            self._address.setText(self._existing_ip.address)
            self._cidr.setText(self._existing_ip.cidr)
            self._gateway.setText(self._existing_ip.gateway)

        self._access_label = QLabel("Access VLAN")
        form.addRow("Режим", self._mode)
        form.addRow(self._access_label, self._vlan)
        form.addRow("Tagged VLAN", self._tagged)
        form.addRow("IP-адрес", self._address)
        form.addRow("Префикс", self._cidr)
        form.addRow("Шлюз", self._gateway)
        layout.addLayout(form)

        self._hint = QLabel(self)
        self._hint.setWordWrap(True)
        layout.addWidget(self._hint)
        layout.addWidget(
            QLabel("Пустой IP удалит адрес с порта (если он был).", self)
        )

        self._mode.currentIndexChanged.connect(self._on_mode_changed)
        self._on_mode_changed()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_mode_changed(self) -> None:
        is_trunk = self._mode.currentData() == PortMode.TRUNK.value
        self._tagged.setEnabled(is_trunk)
        self._access_label.setText("Native VLAN" if is_trunk else "Access VLAN")
        if is_trunk:
            self._hint.setText(
                "Trunk: отметьте tagged VLAN (например 10 и 30). "
                "Native — untagged трафик. Неуправляемый свитч за портом "
                "обычно требует Access, а не Trunk."
            )
        else:
            self._hint.setText(
                "Access: один untagged VLAN. Подходит для ПК, камеры "
                "или неуправляемого свитча в одном VLAN."
            )

    def values(
        self,
    ) -> tuple[PortMode, UUID | None, list[UUID], str, str, str, UUID | None]:
        vlan_raw = self._vlan.currentData()
        vlan_id = UUID(str(vlan_raw)) if vlan_raw is not None else None
        tagged: list[UUID] = []
        for i in range(self._tagged.count()):
            item = self._tagged.item(i)
            if item is None:
                continue
            if item.checkState() == Qt.CheckState.Checked:
                raw = item.data(Qt.ItemDataRole.UserRole)
                if raw:
                    tagged.append(UUID(str(raw)))
        existing_id = self._existing_ip.id if self._existing_ip is not None else None
        mode = PortMode(str(self._mode.currentData()))
        if mode == PortMode.ACCESS:
            tagged = []
        return (
            mode,
            vlan_id,
            tagged,
            self._address.text().strip(),
            self._cidr.text().strip(),
            self._gateway.text().strip(),
            existing_id,
        )
