from __future__ import annotations

from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
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
    PortSide,
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


class ProjectDialog(QDialog):
    """Имя проекта и сведения о площадке."""

    def __init__(
        self,
        *,
        project_name: str = "",
        site_name: str = "",
        address: str = "",
        notes: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Свойства проекта")
        self.resize(420, 260)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._project_name = QLineEdit(project_name, self)
        self._site_name = QLineEdit(site_name, self)
        self._address = QLineEdit(address, self)
        self._notes = QLineEdit(notes, self)
        form.addRow("Имя проекта", self._project_name)
        form.addRow("Площадка", self._site_name)
        form.addRow("Адрес", self._address)
        form.addRow("Заметки", self._notes)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self._project_name.selectAll()

    def values(self) -> tuple[str, str, str, str]:
        return (
            self._project_name.text().strip() or "Новый проект",
            self._site_name.text().strip() or "Площадка",
            self._address.text().strip(),
            self._notes.text().strip(),
        )


class BuildingDialog(QDialog):
    def __init__(
        self,
        *,
        initial_name: str = "",
        initial_address: str = "",
        initial_notes: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Здание" if initial_name else "Добавить здание")
        self.resize(420, 220)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(initial_name, self)
        self._address = QLineEdit(initial_address, self)
        self._notes = QLineEdit(initial_notes, self)
        form.addRow("Имя", self._name)
        form.addRow("Адрес", self._address)
        form.addRow("Заметки", self._notes)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        if initial_name:
            self._name.selectAll()

    def values(self) -> tuple[str, str, str]:
        return (
            self._name.text().strip() or "Здание",
            self._address.text().strip(),
            self._notes.text().strip(),
        )


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
        self._template = QComboBox(self)
        self._template.addItem("Свой размер", None)
        from landesigner.services import catalog as catalog_svc

        for preset in catalog_svc.list_rack_presets():
            self._template.addItem(preset.title, preset.units)
        # Выбрать ближайший пресет к initial_units
        match_idx = self._template.findData(initial_units)
        if match_idx >= 0:
            self._template.setCurrentIndex(match_idx)
        self._template.currentIndexChanged.connect(self._on_template)
        self._units = QSpinBox(self)
        self._units.setRange(1, 60)
        self._units.setValue(initial_units)
        form.addRow("Имя", self._name)
        form.addRow("Шаблон", self._template)
        form.addRow("Юниты", self._units)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_template(self) -> None:
        units = self._template.currentData()
        if units is not None:
            self._units.setValue(int(units))

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
        self._groups.setColumnCount(6)
        self._groups.setHorizontalHeaderLabels(
            ["Префикс имени", "Кол-во", "Старт №", "Среда", "Скорость", "Сторона"]
        )
        self._groups.horizontalHeader().setStretchLastSection(True)
        self._groups.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._groups.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        layout.addWidget(self._groups)

        group_btns = QHBoxLayout()
        add_btn = QPushButton("Добавить группу", self)
        remove_btn = QPushButton("Удалить группу", self)
        pp24_btn = QPushButton("Патч-панель 24", self)
        pp48_btn = QPushButton("Патч-панель 48", self)
        add_btn.clicked.connect(lambda: self._add_inherited_group_row())
        remove_btn.clicked.connect(lambda: self._remove_group_row())
        pp24_btn.clicked.connect(lambda: self._apply_patch_panel(24))
        pp48_btn.clicked.connect(lambda: self._apply_patch_panel(48))
        group_btns.addWidget(add_btn)
        group_btns.addWidget(remove_btn)
        group_btns.addWidget(pp24_btn)
        group_btns.addWidget(pp48_btn)
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
            side_w = self._groups.cellWidget(row, 5)
            if not all([prefix_w, count_w, start_w, media_w, speed_w]):
                continue
            media_raw = media_w.currentData()
            media = str(media_raw) if media_raw is not None else PortMedia.COPPER.value
            side = PortSide.NONE.value
            if side_w is not None and side_w.currentData() is not None:
                side = str(side_w.currentData())
            group: dict = {
                "prefix": prefix_w.text().strip() or "Port",
                "count": int(count_w.value()),
                "start": int(start_w.value()),
                "media": media,
                "speed": self._speed_from_combo(speed_w),
            }
            if side and side != PortSide.NONE.value:
                group["side"] = side
                group["paired"] = True
            groups.append(group)
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
        current_side = PortSide.NONE.value
        current_start = None
        current_count = 0
        current_next = None

        for item in template:
            name = str(item.get("name", "Port"))
            media = str(item.get("media", PortMedia.COPPER.value))
            speed = int(item.get("speed", 1000))
            side = str(item.get("side", PortSide.NONE.value) or PortSide.NONE.value)

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
                and current_side == side
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
                try:
                    side_enum = PortSide(current_side)
                except ValueError:
                    side_enum = PortSide.NONE
                self._insert_group_row(
                    current_prefix,
                    current_count,
                    current_start if current_start is not None else 1,
                    media_enum,
                    current_speed if current_speed is not None else 1000,
                    side_enum,
                )

            current_prefix = prefix
            current_media = media
            current_speed = speed
            current_side = side
            current_start = number if number is not None else 1
            current_count = 1
            current_next = (number + 1) if number is not None else None

        if current_prefix is not None:
            try:
                media_enum = PortMedia(current_media)
            except ValueError:
                media_enum = PortMedia.COPPER
            try:
                side_enum = PortSide(current_side)
            except ValueError:
                side_enum = PortSide.NONE
            self._insert_group_row(
                current_prefix,
                current_count,
                current_start if current_start is not None else 1,
                media_enum,
                current_speed if current_speed is not None else 1000,
                side_enum,
            )

    def _make_side_combo(self, selected: PortSide = PortSide.NONE) -> QComboBox:
        combo = QComboBox(self)
        combo.addItem("—", PortSide.NONE.value)
        combo.addItem("Front", PortSide.FRONT.value)
        combo.addItem("Rear", PortSide.REAR.value)
        idx = combo.findData(selected.value if isinstance(selected, PortSide) else str(selected))
        if idx >= 0:
            combo.setCurrentIndex(idx)
        combo.currentIndexChanged.connect(lambda _=0: self._update_preview())
        return combo

    def _apply_patch_panel(self, count: int) -> None:
        role_idx = self._role.findData(DeviceRole.PATCH_PANEL.value)
        if role_idx >= 0:
            self._role.setCurrentIndex(role_idx)
        self._groups.setRowCount(0)
        self._insert_group_row("Front-", count, 1, PortMedia.COPPER, 1000, PortSide.FRONT)
        self._insert_group_row("Rear-", count, 1, PortMedia.COPPER, 1000, PortSide.REAR)
        self._update_preview()

    def _insert_group_row(
        self,
        prefix: str,
        count: int,
        start: int,
        media: PortMedia,
        speed: int,
        side: PortSide = PortSide.NONE,
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

        if not isinstance(side, PortSide):
            try:
                side = PortSide(str(side))
            except ValueError:
                side = PortSide.NONE

        self._groups.setCellWidget(row, 3, self._make_media_combo(media))
        self._groups.setCellWidget(row, 4, self._make_speed_combo(int(speed)))
        self._groups.setCellWidget(row, 5, self._make_side_combo(side))

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
        self._snapshot = snapshot
        self.setWindowTitle("Устройство" if device is None else "Редактировать устройство")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._role_filter = QComboBox(self)
        self._role_filter.addItem("Все роли", None)
        for role in DeviceRole:
            self._role_filter.addItem(role_label(role), role.value)

        self._type = QComboBox(self)
        self._type.setEditable(True)
        self._type.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._type.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self._type.setMinimumContentsLength(28)
        self._type.lineEdit().setPlaceholderText("Начните вводить vendor, модель…")
        completer = QCompleter(self._type.model(), self._type)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._type.setCompleter(completer)

        self._hostname = QLineEdit(self)
        self._serial = QLineEdit(self)
        self._tag = QLineEdit(self)

        self._host = QComboBox(self)
        self._host.addItem("(выберите гипервизор)", None)
        for d in sorted(
            (x for x in snapshot.devices if x.role == DeviceRole.HYPERVISOR),
            key=lambda x: x.hostname.casefold(),
        ):
            if device is not None and d.id == device.id:
                continue
            self._host.addItem(d.hostname or str(d.id), str(d.id))

        self._room = QComboBox(self)
        self._room.addItem("(без помещения)", None)
        for room in snapshot.rooms:
            self._room.addItem(self._room_label(room), str(room.id))

        self._rack = QComboBox(self)
        self._rack_u = QSpinBox(self)
        self._rack_u.setRange(1, 200)
        self._rack_u.setValue(1)
        self._rack_h = QSpinBox(self)
        self._rack_h.setRange(1, 48)
        self._rack_h.setValue(1)
        self._rack_h.setSuffix(" U")

        form.addRow("Роль", self._role_filter)
        form.addRow("Тип", self._type)
        form.addRow("Имя хоста", self._hostname)
        form.addRow("Серийный номер", self._serial)
        form.addRow("Инв. номер", self._tag)
        form.addRow("Гипервизор", self._host)
        form.addRow("Помещение", self._room)
        form.addRow("Шкаф", self._rack)
        form.addRow("Юнит (низ)", self._rack_u)
        form.addRow("Высота", self._rack_h)
        layout.addLayout(form)

        if not snapshot.device_types:
            layout.addWidget(QLabel("Сначала создайте тип устройства.", self))

        self._role_filter.currentIndexChanged.connect(lambda _=0: self._reload_types())
        self._type.currentIndexChanged.connect(lambda _=0: self._sync_vm_fields())
        self._room.currentIndexChanged.connect(self._reload_racks)
        self._rack.currentIndexChanged.connect(self._on_rack_changed)

        preferred_type_id = str(device.device_type_id) if device is not None else None
        if device is not None:
            self._role_filter.setEnabled(False)
            self._type.setEnabled(False)
            self._type.setEditable(False)
            dt = next(
                (t for t in snapshot.device_types if t.id == device.device_type_id),
                None,
            )
            if dt is not None:
                ridx = self._role_filter.findData(dt.role.value)
                if ridx >= 0:
                    self._role_filter.setCurrentIndex(ridx)
            self._hostname.setText(device.hostname)
            self._serial.setText(device.serial)
            self._tag.setText(device.inventory_tag)
            if device.host_device_id is not None:
                hidx = self._host.findData(str(device.host_device_id))
                if hidx >= 0:
                    self._host.setCurrentIndex(hidx)
            if device.room_id is not None:
                ridx = self._room.findData(str(device.room_id))
                if ridx >= 0:
                    self._room.setCurrentIndex(ridx)
            self._reload_racks()
            if device.rack_id is not None:
                kidx = self._rack.findData(str(device.rack_id))
                if kidx >= 0:
                    self._rack.setCurrentIndex(kidx)
            if device.rack_u is not None:
                self._rack_u.setValue(int(device.rack_u))
            self._rack_h.setValue(max(1, int(device.rack_u_height or 1)))
        else:
            self._reload_racks()

        self._reload_types(preferred_type_id=preferred_type_id)
        self._on_rack_changed()
        self._sync_vm_fields()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _type_label(self, dt: DeviceType) -> str:
        return f"{dt.vendor} {dt.model} ({role_label(dt.role)})"

    def _reload_types(self, *, preferred_type_id: str | None = None) -> None:
        keep = preferred_type_id
        if keep is None:
            keep = self._type.currentData()
            if keep is not None:
                keep = str(keep)

        role_raw = self._role_filter.currentData()
        types = sorted(
            self._snapshot.device_types,
            key=lambda t: (t.vendor.casefold(), t.model.casefold()),
        )
        if role_raw is not None:
            types = [t for t in types if t.role.value == str(role_raw)]

        self._type.blockSignals(True)
        self._type.clear()
        for dt in types:
            self._type.addItem(self._type_label(dt), str(dt.id))
        if keep is not None:
            idx = self._type.findData(keep)
            if idx >= 0:
                self._type.setCurrentIndex(idx)
            elif self._type.count() > 0:
                self._type.setCurrentIndex(0)
        elif self._type.count() > 0:
            self._type.setCurrentIndex(0)
        else:
            self._type.setCurrentIndex(-1)
            if self._type.isEditable() and self._type.lineEdit() is not None:
                self._type.lineEdit().clear()
        self._type.blockSignals(False)
        self._sync_vm_fields()

    def _selected_role(self) -> DeviceRole | None:
        type_id = self._selected_type_id()
        if type_id is None:
            return None
        dt = next((t for t in self._snapshot.device_types if t.id == type_id), None)
        return dt.role if dt is not None else None

    def _is_vm(self) -> bool:
        return self._selected_role() == DeviceRole.VIRTUAL_MACHINE

    def _sync_vm_fields(self) -> None:
        is_vm = self._is_vm()
        self._host.setEnabled(is_vm)
        for w in (self._room, self._rack, self._rack_u, self._rack_h):
            w.setEnabled(not is_vm)
        if not is_vm:
            self._on_rack_changed()
        else:
            self._rack.setEnabled(False)
            self._rack_u.setEnabled(False)
            self._rack_h.setEnabled(False)

    def _room_label(self, room) -> str:
        floor = next((f for f in self._snapshot.floors if f.id == room.floor_id), None)
        building = (
            next((b for b in self._snapshot.buildings if b.id == floor.building_id), None)
            if floor is not None
            else None
        )
        parts = []
        if building is not None:
            parts.append(building.name)
        if floor is not None:
            parts.append(floor.name)
        parts.append(room.name)
        return " / ".join(parts)

    def _reload_racks(self) -> None:
        current = self._rack.currentData()
        self._rack.blockSignals(True)
        self._rack.clear()
        self._rack.addItem("(без шкафа)", None)
        room_raw = self._room.currentData()
        if room_raw is not None:
            room_id = UUID(str(room_raw))
            for rack in self._snapshot.racks:
                if rack.room_id != room_id:
                    continue
                self._rack.addItem(f"{rack.name} ({rack.units}U)", str(rack.id))
        if current is not None:
            idx = self._rack.findData(current)
            if idx >= 0:
                self._rack.setCurrentIndex(idx)
        self._rack.blockSignals(False)
        self._on_rack_changed()

    def _on_rack_changed(self) -> None:
        if self._is_vm():
            self._rack.setEnabled(False)
            self._rack_u.setEnabled(False)
            self._rack_h.setEnabled(False)
            return
        has_rack = self._rack.currentData() is not None
        has_room = self._room.currentData() is not None
        self._rack.setEnabled(has_room)
        self._rack_u.setEnabled(has_rack)
        self._rack_h.setEnabled(has_rack)
        if has_rack:
            rack_id = UUID(str(self._rack.currentData()))
            rack = next((r for r in self._snapshot.racks if r.id == rack_id), None)
            if rack is not None:
                self._rack_u.setMaximum(max(1, int(rack.units)))
                self._rack_h.setMaximum(max(1, int(rack.units)))

    def values(
        self,
    ) -> tuple[
        UUID, str, str, str, UUID | None, UUID | None, int | None, int, UUID | None
    ]:
        type_id = self._selected_type_id()
        if self._is_vm():
            host_raw = self._host.currentData()
            host_id = UUID(str(host_raw)) if host_raw is not None else None
            return (
                type_id,  # type: ignore[return-value]
                self._hostname.text().strip(),
                self._serial.text().strip(),
                self._tag.text().strip(),
                None,
                None,
                None,
                1,
                host_id,
            )
        room_raw = self._room.currentData()
        rack_raw = self._rack.currentData()
        room_id = UUID(str(room_raw)) if room_raw is not None else None
        rack_id = UUID(str(rack_raw)) if rack_raw is not None else None
        rack_u = int(self._rack_u.value()) if rack_id is not None else None
        rack_h = int(self._rack_h.value()) if rack_id is not None else 1
        return (
            type_id,  # type: ignore[return-value]
            self._hostname.text().strip(),
            self._serial.text().strip(),
            self._tag.text().strip(),
            room_id,
            rack_id,
            rack_u,
            rack_h,
            None,
        )

    def _selected_type_id(self) -> UUID | None:
        type_raw = self._type.currentData()
        if type_raw is not None:
            return UUID(str(type_raw))
        # После ручного ввода индекс может не совпасть — ищем по тексту.
        text = self._type.currentText().strip().casefold()
        if not text:
            return None
        for i in range(self._type.count()):
            if self._type.itemText(i).casefold() == text:
                raw = self._type.itemData(i)
                return UUID(str(raw)) if raw is not None else None
        return None

    def is_valid(self) -> bool:
        if self._selected_type_id() is None or not self._hostname.text().strip():
            return False
        if self._is_vm() and self._host.currentData() is None:
            return False
        return True


class CableDialog(QDialog):
    """Создание или правка метки/вида кабеля между двумя портами."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        cable: Cable | None = None,
        parent=None,
        *,
        device_a_id: UUID | None = None,
        device_b_id: UUID | None = None,
        port_a_id: UUID | None = None,
        port_b_id: UUID | None = None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._cable = cable
        self.setWindowTitle("Кабель" if cable is None else "Редактировать кабель")
        self.resize(520, 340)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._device_a = QComboBox(self)
        self._port_a = QComboBox(self)
        self._device_b = QComboBox(self)
        self._port_b = QComboBox(self)
        self._label = QLineEdit(self)
        self._kind = QComboBox(self)
        self._category = QComboBox(self)
        self._color = QLineEdit(self)
        self._color.setPlaceholderText("синий, orange, …")
        self._purpose = QLineEdit(self)
        self._purpose.setPlaceholderText("uplink, PC, телефон…")
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
        form.addRow("Цвет", self._color)
        form.addRow("Назначение", self._purpose)
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
            if port_a_id is not None:
                port = next((p for p in snapshot.ports if p.id == port_a_id), None)
                if port is not None:
                    device_a_id = port.device_id
            if port_b_id is not None:
                port = next((p for p in snapshot.ports if p.id == port_b_id), None)
                if port is not None:
                    device_b_id = port.device_id
            if device_a_id is not None:
                idx = self._device_a.findData(str(device_a_id))
                if idx >= 0:
                    self._device_a.setCurrentIndex(idx)
            self._reload_ports_a()
            if device_b_id is not None:
                idx = self._device_b.findData(str(device_b_id))
                if idx >= 0:
                    self._device_b.setCurrentIndex(idx)
            elif self._device_b.count() > 1 and device_a_id is None:
                self._device_b.setCurrentIndex(1)
            self._reload_ports_b()
            if port_a_id is not None:
                pidx = self._port_a.findData(str(port_a_id))
                if pidx >= 0:
                    self._port_a.setCurrentIndex(pidx)
            if port_b_id is not None:
                pidx = self._port_b.findData(str(port_b_id))
                if pidx >= 0:
                    self._port_b.setCurrentIndex(pidx)
            if device_a_id is not None and device_b_id is not None:
                self._device_a.setEnabled(False)
                self._device_b.setEnabled(False)
                self._hint.setText("Устройства выбраны — укажите свободные порты.")
            if port_a_id is not None:
                self._hint.setText(
                    "Порт A выбран с патч-панели — укажите второй конец кабеля."
                )
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
        self._color.setText(cable.color)
        self._purpose.setText(cable.purpose)
        kidx = self._kind.findData(cable.kind.value)
        if kidx >= 0:
            self._kind.setCurrentIndex(kidx)
        cidx = self._category.findData(cable.category.value)
        if cidx >= 0:
            self._category.setCurrentIndex(cidx)
        if cable.length_m is not None:
            self._length.setValue(float(cable.length_m))
        path = inventory_service.cable_path_label(self._snapshot, cable)
        self._hint.setText(f"Концы при правке не меняются.\nПуть: {path}")

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

    def values(
        self,
    ) -> tuple[UUID, UUID, str, CableKind, CableCategory, float | None, str, str]:
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
            self._color.text().strip(),
            self._purpose.text().strip(),
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
        initial_description: str = "",
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
        self._description = QLineEdit(self)
        self._description.setText(initial_description)
        self._description.setPlaceholderText("Назначение, подсеть, зона…")
        form.addRow("VLAN ID", self._vlan_id)
        form.addRow("Имя", self._name)
        form.addRow("Описание", self._description)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[int, str, str]:
        return (
            int(self._vlan_id.value()),
            self._name.text().strip(),
            self._description.text().strip(),
        )


class VrfDialog(QDialog):
    def __init__(
        self,
        initial_name: str = "",
        initial_rd: str = "",
        initial_description: str = "",
        *,
        editing: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Изменить VRF" if editing else "Добавить VRF")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(self)
        self._name.setText(initial_name)
        self._name.setPlaceholderText("Cust-A / MGMT / …")
        self._rd = QLineEdit(self)
        self._rd.setText(initial_rd)
        self._rd.setPlaceholderText("65000:100")
        self._description = QLineEdit(self)
        self._description.setText(initial_description)
        self._description.setPlaceholderText("Назначение, маршрут, зона…")
        form.addRow("Имя", self._name)
        form.addRow("RD", self._rd)
        form.addRow("Описание", self._description)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, str, str]:
        return (
            self._name.text().strip(),
            self._rd.text().strip(),
            self._description.text().strip(),
        )

    def is_valid(self) -> bool:
        return bool(self._name.text().strip())


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
        self.resize(480, 300)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self._bind = QComboBox(self)
        self._bind.addItem("Не привязан", "none")
        self._bind.addItem("Порт", "port")
        self._bind.addItem("LAG", "lag")
        self._device = QComboBox(self)
        self._port = QComboBox(self)
        self._lag = QComboBox(self)
        self._address = QLineEdit(self)
        self._cidr = QLineEdit(self)
        self._cidr.setPlaceholderText("24")
        self._gateway = QLineEdit(self)
        self._vrf = QComboBox(self)
        self._vrf.addItem("(глобально)", None)
        for vrf in sorted(snapshot.vrfs, key=lambda v: v.name.casefold()):
            self._vrf.addItem(inventory_service.vrf_label(vrf), str(vrf.id))

        for device in snapshot.devices:
            self._device.addItem(device.hostname or str(device.id), str(device.id))

        form.addRow("Привязка", self._bind)
        form.addRow("Устройство", self._device)
        form.addRow("Порт", self._port)
        form.addRow("LAG", self._lag)
        form.addRow("VRF", self._vrf)
        form.addRow("Адрес", self._address)
        form.addRow("Префикс", self._cidr)
        form.addRow("Шлюз", self._gateway)
        layout.addLayout(form)

        self._bind.currentIndexChanged.connect(self._on_bind_changed)
        self._device.currentIndexChanged.connect(self._reload_targets)

        if ip is not None:
            self._address.setText(ip.address)
            self._cidr.setText(ip.cidr)
            self._gateway.setText(ip.gateway)
            if ip.vrf_id is not None:
                vidx = self._vrf.findData(str(ip.vrf_id))
                if vidx >= 0:
                    self._vrf.setCurrentIndex(vidx)
            if ip.lag_id is not None:
                lag = next((item for item in snapshot.lags if item.id == ip.lag_id), None)
                self._bind.setCurrentIndex(self._bind.findData("lag"))
                if lag is not None:
                    didx = self._device.findData(str(lag.device_id))
                    if didx >= 0:
                        self._device.setCurrentIndex(didx)
                self._reload_targets()
                if lag is not None:
                    lidx = self._lag.findData(str(lag.id))
                    if lidx >= 0:
                        self._lag.setCurrentIndex(lidx)
            elif ip.port_id is not None:
                port = next((p for p in snapshot.ports if p.id == ip.port_id), None)
                self._bind.setCurrentIndex(self._bind.findData("port"))
                if port is not None:
                    didx = self._device.findData(str(port.device_id))
                    if didx >= 0:
                        self._device.setCurrentIndex(didx)
                self._reload_targets()
                if port is not None:
                    pidx = self._port.findData(str(port.id))
                    if pidx >= 0:
                        self._port.setCurrentIndex(pidx)
            else:
                self._bind.setCurrentIndex(self._bind.findData("none"))
                self._reload_targets()
        else:
            if preferred_port_id is not None:
                port = next((p for p in snapshot.ports if p.id == preferred_port_id), None)
                self._bind.setCurrentIndex(self._bind.findData("port"))
                if port is not None:
                    didx = self._device.findData(str(port.device_id))
                    if didx >= 0:
                        self._device.setCurrentIndex(didx)
                self._reload_targets()
                if preferred_port_id is not None:
                    pidx = self._port.findData(str(preferred_port_id))
                    if pidx >= 0:
                        self._port.setCurrentIndex(pidx)
            else:
                self._bind.setCurrentIndex(self._bind.findData("none"))
                self._reload_targets()

        self._on_bind_changed()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_bind_changed(self) -> None:
        mode = self._bind.currentData()
        self._device.setEnabled(mode in {"port", "lag"})
        self._port.setEnabled(mode == "port")
        self._lag.setEnabled(mode == "lag")
        self._reload_targets()

    def _reload_targets(self) -> None:
        self._port.clear()
        self._lag.clear()
        self._port.addItem("(не выбран)", None)
        self._lag.addItem("(не выбран)", None)
        raw = self._device.currentData()
        if raw is None:
            return
        device_id = UUID(str(raw))
        for port in inventory_service.ports_for_device(self._snapshot, device_id):
            self._port.addItem(port.name, str(port.id))
        for lag in inventory_service.lags_for_device(self._snapshot, device_id):
            self._lag.addItem(lag.name, str(lag.id))

    def values(self) -> tuple[str, str, str, UUID | None, UUID | None, UUID | None]:
        mode = self._bind.currentData()
        port_id = None
        lag_id = None
        if mode == "port":
            port_raw = self._port.currentData()
            port_id = UUID(str(port_raw)) if port_raw is not None else None
        elif mode == "lag":
            lag_raw = self._lag.currentData()
            lag_id = UUID(str(lag_raw)) if lag_raw is not None else None
        vrf_raw = self._vrf.currentData()
        vrf_id = UUID(str(vrf_raw)) if vrf_raw is not None else None
        return (
            self._address.text().strip(),
            self._cidr.text().strip(),
            self._gateway.text().strip(),
            port_id,
            lag_id,
            vrf_id,
        )

    def is_valid(self) -> bool:
        return bool(self._address.text().strip())


class LagDialog(QDialog):
    """Создание / правка LAG (bond) на устройстве."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        lag=None,
        preferred_device_id: UUID | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._lag = lag
        self.setWindowTitle("LAG / bond" if lag is None else f"LAG «{lag.name}»")
        self.resize(480, 420)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._device = QComboBox(self)
        self._name = QLineEdit(self)
        self._mode = QComboBox(self)
        from landesigner.ui.labels import LAG_MODE_RU

        for mode, label in LAG_MODE_RU.items():
            self._mode.addItem(label, mode.value)
        self._notes = QLineEdit(self)
        self._mac = QLineEdit(self)
        self._mac.setPlaceholderText("AA:BB:CC:DD:EE:FF")

        for device in snapshot.devices:
            self._device.addItem(device.hostname or str(device.id), str(device.id))

        form.addRow("Устройство", self._device)
        form.addRow("Имя", self._name)
        form.addRow("Режим", self._mode)
        form.addRow("MAC", self._mac)
        form.addRow("Заметки", self._notes)
        layout.addLayout(form)

        layout.addWidget(QLabel("Порты (минимум 2):", self))
        self._ports = QListWidget(self)
        self._ports.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self._ports, stretch=1)

        self._device.currentIndexChanged.connect(self._reload_ports)
        self._device.setEnabled(lag is None)

        if lag is not None:
            self._name.setText(lag.name)
            self._notes.setText(lag.notes)
            self._mac.setText(lag.mac)
            midx = self._mode.findData(lag.mode.value)
            if midx >= 0:
                self._mode.setCurrentIndex(midx)
            didx = self._device.findData(str(lag.device_id))
            if didx >= 0:
                self._device.setCurrentIndex(didx)
            self._reload_ports()
            selected = {str(pid) for pid in lag.member_port_ids}
            for i in range(self._ports.count()):
                item = self._ports.item(i)
                if item is not None and str(item.data(Qt.ItemDataRole.UserRole)) in selected:
                    item.setSelected(True)
        else:
            self._name.setText("bond0")
            if preferred_device_id is not None:
                didx = self._device.findData(str(preferred_device_id))
                if didx >= 0:
                    self._device.setCurrentIndex(didx)
            self._reload_ports()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reload_ports(self) -> None:
        self._ports.clear()
        raw = self._device.currentData()
        if raw is None:
            return
        device_id = UUID(str(raw))
        exclude = self._lag.id if self._lag is not None else None
        for port in inventory_service.ports_for_device(self._snapshot, device_id):
            other = inventory_service.lag_for_port(self._snapshot, port.id)
            if other is not None and other.id != exclude:
                continue
            item = QListWidgetItem(port.name)
            item.setData(Qt.ItemDataRole.UserRole, str(port.id))
            self._ports.addItem(item)

    def values(self):
        from landesigner.domain.enums import LagMode

        device_raw = self._device.currentData()
        device_id = UUID(str(device_raw)) if device_raw is not None else None
        mode = LagMode(str(self._mode.currentData()))
        members: list[UUID] = []
        for item in self._ports.selectedItems():
            raw = item.data(Qt.ItemDataRole.UserRole)
            if raw:
                members.append(UUID(str(raw)))
        return (
            device_id,
            self._name.text().strip() or "bond0",
            mode,
            members,
            self._notes.text().strip(),
            self._mac.text().strip(),
        )

    def is_valid(self) -> bool:
        device_id, _name, _mode, members, _notes, _mac = self.values()
        return device_id is not None and len(members) >= 2


class PortPropertiesDialog(QDialog):
    """Имя, скорость и среда физического порта (создание или правка)."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        port_id: UUID | None = None,
        *,
        device_id: UUID | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._creating = port_id is None
        if self._creating:
            if device_id is None:
                raise ValueError("Нужен device_id для нового порта")
            device = next((d for d in snapshot.devices if d.id == device_id), None)
            host = device.hostname if device is not None else "устройство"
            self.setWindowTitle(f"Добавить порт — {host}")
            initial_name = "Mgmt"
            initial_speed = 1000
            initial_media = PortMedia.COPPER
            initial_mac = ""
        else:
            port = next((p for p in snapshot.ports if p.id == port_id), None)
            if port is None:
                raise ValueError("Порт не найден")
            title = inventory_service.port_endpoint_label(snapshot, port_id)
            self.setWindowTitle(f"Свойства порта — {title}")
            initial_name = port.name
            initial_speed = int(port.speed)
            initial_media = port.media
            initial_mac = port.mac

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._name = QLineEdit(initial_name, self)
        self._speed = QComboBox(self)
        self._speed.setEditable(True)
        for speed in (100, 1000, 2500, 5000, 10000, 25000, 40000, 100000):
            self._speed.addItem(f"{speed} Мбит/с", speed)
        idx = self._speed.findData(initial_speed)
        if idx >= 0:
            self._speed.setCurrentIndex(idx)
        else:
            self._speed.setEditText(str(initial_speed))
        self._media = QComboBox(self)
        for media in PortMedia:
            self._media.addItem(PORT_MEDIA_RU[media], media.value)
        media_idx = self._media.findData(initial_media.value)
        if media_idx >= 0:
            self._media.setCurrentIndex(media_idx)
        self._mac = QLineEdit(initial_mac, self)
        self._mac.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        form.addRow("Имя", self._name)
        form.addRow("Скорость", self._speed)
        form.addRow("Среда", self._media)
        form.addRow("MAC", self._mac)
        hint = QLabel(
            "Новый порт появится только на этом устройстве; "
            "шаблон типа в каталоге не меняется."
            if self._creating
            else "Для combo-порта смените среду и при необходимости имя "
            "(например Gi1/0/49 → SFP1/0/49).",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("HintLabel")
        layout.addLayout(form)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self) -> tuple[str, int, PortMedia, str]:
        data = self._speed.currentData()
        if data is not None:
            speed = int(data)
        else:
            text = self._speed.currentText().replace("Мбит/с", "").strip()
            speed = int(text)
        media = PortMedia(str(self._media.currentData()))
        return self._name.text().strip(), speed, media, self._mac.text().strip()


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
            if vlan.description:
                self._vlan.setItemData(
                    self._vlan.count() - 1,
                    vlan.description,
                    Qt.ItemDataRole.ToolTipRole,
                )
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
            if vlan.description:
                item.setToolTip(vlan.description)
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


class VnicHostDialog(QDialog):
    """Привязка vNIC к Port Group (предпочтительно) или напрямую к NIC хоста."""

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
        if port is None:
            raise ValueError("Порт не найден")
        title = inventory_service.port_endpoint_label(snapshot, port_id)
        self.setWindowTitle(f"Привязка vNIC — {title}")

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._port_group = QComboBox(self)
        self._port_group.addItem("— не выбран —", None)
        device = next((d for d in snapshot.devices if d.id == port.device_id), None)
        if device is not None:
            for pg in inventory_service.port_groups_for_vm(snapshot, device.id):
                self._port_group.addItem(
                    inventory_service.port_group_label(snapshot, pg),
                    str(pg.id),
                )
        if port.port_group_id is not None:
            idx = self._port_group.findData(str(port.port_group_id))
            if idx >= 0:
                self._port_group.setCurrentIndex(idx)

        self._host_nic = QComboBox(self)
        self._host_nic.addItem("— не привязан —", None)
        if device is not None:
            for nic in inventory_service.host_nics_for_vm(snapshot, device.id):
                label = inventory_service.port_endpoint_label(snapshot, nic.id)
                self._host_nic.addItem(label, str(nic.id))
        if port.host_port_id is not None and port.port_group_id is None:
            idx = self._host_nic.findData(str(port.host_port_id))
            if idx >= 0:
                self._host_nic.setCurrentIndex(idx)

        form.addRow("Port Group", self._port_group)
        form.addRow("NIC напрямую", self._host_nic)
        hint = QLabel(
            "Предпочтительна привязка к Port Group (vSwitch → uplink). "
            "Прямой NIC — запасной вариант; при выборе Port Group прямая привязка сбрасывается.",
            self,
        )
        hint.setWordWrap(True)
        hint.setObjectName("HintLabel")
        layout.addLayout(form)
        layout.addWidget(hint)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._port_group.currentIndexChanged.connect(self._on_pg_changed)
        self._on_pg_changed()

    def _on_pg_changed(self) -> None:
        has_pg = self._port_group.currentData() is not None
        self._host_nic.setEnabled(not has_pg)

    def port_group_id(self) -> UUID | None:
        raw = self._port_group.currentData()
        if raw is None:
            return None
        return UUID(str(raw))

    def host_port_id(self) -> UUID | None:
        if self.port_group_id() is not None:
            return None
        raw = self._host_nic.currentData()
        if raw is None:
            return None
        return UUID(str(raw))


class VirtualSwitchDialog(QDialog):
    """Создание / правка vSwitch на гипервизоре."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        vswitch=None,
        preferred_host_id: UUID | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._vswitch = vswitch
        self.setWindowTitle("vSwitch" if vswitch is None else f"vSwitch «{vswitch.name}»")
        self.resize(480, 400)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._host = QComboBox(self)
        self._name = QLineEdit(self)
        self._notes = QLineEdit(self)
        for device in snapshot.devices:
            if device.role != DeviceRole.HYPERVISOR:
                continue
            self._host.addItem(device.hostname or str(device.id), str(device.id))
        form.addRow("Гипервизор", self._host)
        form.addRow("Имя", self._name)
        form.addRow("Заметки", self._notes)
        layout.addLayout(form)

        layout.addWidget(QLabel("Uplink NIC:", self))
        self._ports = QListWidget(self)
        self._ports.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        layout.addWidget(self._ports, stretch=1)

        self._host.currentIndexChanged.connect(self._reload_ports)
        self._host.setEnabled(vswitch is None)
        if vswitch is not None:
            self._name.setText(vswitch.name)
            self._notes.setText(vswitch.notes)
            hidx = self._host.findData(str(vswitch.host_device_id))
            if hidx >= 0:
                self._host.setCurrentIndex(hidx)
            selected = {str(pid) for pid in vswitch.uplink_port_ids}
            self._reload_ports()
            for i in range(self._ports.count()):
                item = self._ports.item(i)
                if item is not None and item.data(Qt.ItemDataRole.UserRole) in selected:
                    item.setSelected(True)
        else:
            if preferred_host_id is not None:
                hidx = self._host.findData(str(preferred_host_id))
                if hidx >= 0:
                    self._host.setCurrentIndex(hidx)
            self._name.setText("vSwitch0")
            self._reload_ports()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _reload_ports(self) -> None:
        self._ports.clear()
        raw = self._host.currentData()
        if raw is None:
            return
        host_id = UUID(str(raw))
        exclude = self._vswitch.id if self._vswitch is not None else None
        for port in inventory_service.ports_for_device(self._snapshot, host_id):
            if port.media == PortMedia.VIRTUAL:
                continue
            busy = None
            for vs in self._snapshot.virtual_switches:
                if exclude is not None and vs.id == exclude:
                    continue
                if port.id in vs.uplink_port_ids:
                    busy = vs.name
                    break
            label = port.name
            if busy:
                label = f"{label} (занят: {busy})"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, str(port.id))
            if busy:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self._ports.addItem(item)

    def values(self):
        host_raw = self._host.currentData()
        host_id = UUID(str(host_raw)) if host_raw is not None else None
        uplink_ids: list[UUID] = []
        for item in self._ports.selectedItems():
            raw = item.data(Qt.ItemDataRole.UserRole)
            if raw:
                uplink_ids.append(UUID(str(raw)))
        return host_id, self._name.text().strip(), uplink_ids, self._notes.text().strip()


class PortGroupDialog(QDialog):
    """Создание / правка Port Group."""

    def __init__(
        self,
        snapshot: ProjectSnapshot,
        port_group=None,
        preferred_vswitch_id: UUID | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._snapshot = snapshot
        self._port_group = port_group
        self.setWindowTitle(
            "Port Group" if port_group is None else f"Port Group «{port_group.name}»"
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._vswitch = QComboBox(self)
        self._name = QLineEdit(self)
        self._vlan = QComboBox(self)
        self._notes = QLineEdit(self)
        self._vlan.addItem("— без VLAN —", None)
        for vlan in sorted(snapshot.vlans, key=lambda v: v.vlan_id):
            label = f"{vlan.vlan_id}"
            if vlan.name:
                label = f"{vlan.vlan_id} — {vlan.name}"
            self._vlan.addItem(label, str(vlan.id))
        for vs in snapshot.virtual_switches:
            host = next((d for d in snapshot.devices if d.id == vs.host_device_id), None)
            host_name = host.hostname if host else "?"
            self._vswitch.addItem(f"{host_name} / {vs.name}", str(vs.id))
        form.addRow("vSwitch", self._vswitch)
        form.addRow("Имя", self._name)
        form.addRow("VLAN", self._vlan)
        form.addRow("Заметки", self._notes)
        layout.addLayout(form)

        self._vswitch.setEnabled(port_group is None)
        if port_group is not None:
            self._name.setText(port_group.name)
            self._notes.setText(port_group.notes)
            vidx = self._vswitch.findData(str(port_group.vswitch_id))
            if vidx >= 0:
                self._vswitch.setCurrentIndex(vidx)
            if port_group.vlan_id is not None:
                vlidx = self._vlan.findData(str(port_group.vlan_id))
                if vlidx >= 0:
                    self._vlan.setCurrentIndex(vlidx)
        else:
            if preferred_vswitch_id is not None:
                vidx = self._vswitch.findData(str(preferred_vswitch_id))
                if vidx >= 0:
                    self._vswitch.setCurrentIndex(vidx)
            self._name.setText("VM Network")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        _russian_buttons(buttons)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def values(self):
        vs_raw = self._vswitch.currentData()
        vlan_raw = self._vlan.currentData()
        return (
            UUID(str(vs_raw)) if vs_raw is not None else None,
            self._name.text().strip(),
            UUID(str(vlan_raw)) if vlan_raw is not None else None,
            self._notes.text().strip(),
        )
