"""
shared/agents/duct_analysis_agent.py — Агент анализа чертежей воздуховодов.

Анализирует загруженные PDF/DWG чертежи и извлекает:
- Спецификацию воздуховодов (сечение, материал, длина)
- Расход воздуха по помещениям (м³/ч)
- Схему разводки (магистрали, ответвления)
- Фасонные изделия (отводы, тройники, переходы)
- Утеплитель и изоляцию
- Клапаны, заслонки, решётки
- Соответствие СП 60.13330 / СП 7.13130

Поддерживает:
- PDF чертежи (через pdf_analysis_agent данные)
- DXF/DWG чертежи (через dwg_analysis_agent данные)
- Текстовые спецификации (парсинг таблиц)
- LLM-анализ изображений чертежей
"""

import logging
import re
import time
from dataclasses import dataclass, field

from shared.agents.base import BaseAgent, Task, TaskResult, TaskStatus

logger = logging.getLogger("archai.duct_analysis")


# ═══════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════


@dataclass
class DuctSegment:
    """Один участок воздуховода."""

    segment_id: str = ""
    duct_type: str = ""  # supply, exhaust, recirculation, fire
    shape: str = ""  # rectangular, round, flat_oval
    width_mm: int = 0  # для прямоугольных
    height_mm: int = 0  # для прямоугольных
    diameter_mm: int = 0  # для круглых
    length_m: float = 0.0
    material: str = ""  # galvanized_steel, stainless, plastic, flexible
    insulation_type: str = ""  # mineral_wool, foam, none
    insulation_thickness_mm: int = 0
    fire_rating: str = ""  # EI 60, EI 120, none
    airflow_m3h: float = 0.0
    velocity_ms: float = 0.0
    pressure_loss_pa: float = 0.0
    from_room: str = ""
    to_room: str = ""
    floor: int = 1
    annotations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "duct_type": self.duct_type,
            "shape": self.shape,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "diameter_mm": self.diameter_mm,
            "length_m": self.length_m,
            "material": self.material,
            "insulation_type": self.insulation_type,
            "insulation_thickness_mm": self.insulation_thickness_mm,
            "fire_rating": self.fire_rating,
            "airflow_m3h": self.airflow_m3h,
            "velocity_ms": self.velocity_ms,
            "pressure_loss_pa": self.pressure_loss_pa,
            "from_room": self.from_room,
            "to_room": self.to_room,
            "floor": self.floor,
            "annotations": self.annotations,
        }


@dataclass
class DuctFitting:
    """Фасонное изделие."""

    fitting_id: str = ""
    fitting_type: str = ""  # elbow, tee, reducer, transition, damper, grille, diffuser
    size_mm: str = ""  # "800x400" или "Ø200"
    angle_deg: int = 0  # для отводов
    quantity: int = 1
    location: str = ""
    material: str = ""

    def to_dict(self) -> dict:
        return {
            "fitting_id": self.fitting_id,
            "fitting_type": self.fitting_type,
            "size_mm": self.size_mm,
            "angle_deg": self.angle_deg,
            "quantity": self.quantity,
            "location": self.location,
            "material": self.material,
        }


@dataclass
class RoomVentilation:
    """Вентиляция конкретного помещения."""

    room_name: str = ""
    room_area_m2: float = 0.0
    room_volume_m3: float = 0.0
    supply_airflow_m3h: float = 0.0
    exhaust_airflow_m3h: float = 0.0
    air_exchange_rate: float = 0.0  # кратность
    supply_diffusers: int = 0
    exhaust_grilles: int = 0
    duct_size_supply: str = ""
    duct_size_exhaust: str = ""
    noise_level_dba: float = 0.0
    temperature_c: float = 0.0
    norm_reference: str = ""  # СП 60.13330

    def to_dict(self) -> dict:
        return {
            "room_name": self.room_name,
            "room_area_m2": self.room_area_m2,
            "room_volume_m3": self.room_volume_m3,
            "supply_airflow_m3h": self.supply_airflow_m3h,
            "exhaust_airflow_m3h": self.exhaust_airflow_m3h,
            "air_exchange_rate": self.air_exchange_rate,
            "supply_diffusers": self.supply_diffusers,
            "exhaust_grilles": self.exhaust_grilles,
            "duct_size_supply": self.duct_size_supply,
            "duct_size_exhaust": self.duct_size_exhaust,
            "noise_level_dba": self.noise_level_dba,
            "temperature_c": self.temperature_c,
            "norm_reference": self.norm_reference,
        }


@dataclass
class DuctSpecification:
    """Полная спецификация воздуховодов."""

    project_name: str = ""
    drawing_number: str = ""
    segments: list[DuctSegment] = field(default_factory=list)
    fittings: list[DuctFitting] = field(default_factory=list)
    rooms: list[RoomVentilation] = field(default_factory=list)
    equipment: list[dict] = field(default_factory=list)
    total_duct_length_m: float = 0.0
    total_airflow_supply_m3h: float = 0.0
    total_airflow_exhaust_m3h: float = 0.0
    warnings: list[str] = field(default_factory=list)
    compliance: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "drawing_number": self.drawing_number,
            "segments": [s.to_dict() for s in self.segments],
            "fittings": [f.to_dict() for f in self.fittings],
            "rooms": [r.to_dict() for r in self.rooms],
            "equipment": self.equipment,
            "total_duct_length_m": self.total_duct_length_m,
            "total_airflow_supply_m3h": self.total_airflow_supply_m3h,
            "total_airflow_exhaust_m3h": self.total_airflow_exhaust_m3h,
            "warnings": self.warnings,
            "compliance": self.compliance,
            "schedule": self._generate_schedule(),
            "material_spec": self._generate_material_spec(),
        }

    def _generate_schedule(self) -> list[dict]:
        """Спецификация воздуховодов в табличном виде (ГОСТ 21.1101)."""
        schedule = []
        for seg in self.segments:
            if seg.shape == "round":
                size = f"Ø{seg.diameter_mm}"
            else:
                size = f"{seg.width_mm}×{seg.height_mm}"
            schedule.append({
                "позиция": seg.segment_id,
                "сечение": size,
                "форма": "круглое" if seg.shape == "round" else "прямоугольное",
                "длина_м": seg.length_m,
                "материал": seg.material,
                "изоляция": f"{seg.insulation_type} {seg.insulation_thickness_mm}мм" if seg.insulation_type else "нет",
                "огнестойкость": seg.fire_rating or "нет",
                "расход_м3ч": seg.airflow_m3h,
                "скорость_мс": seg.velocity_ms,
            })
        return schedule

    def _generate_material_spec(self) -> list[dict]:
        """Ведомость материалов."""
        materials = {}
        for seg in self.segments:
            key = f"{seg.material}_{seg.shape}"
            if key not in materials:
                materials[key] = {
                    "наименование": f"Воздуховод {seg.shape} из {seg.material}",
                    "ед_изм": "м",
                    "количество": 0.0,
                }
            materials[key]["количество"] += seg.length_m

        for fit in self.fittings:
            key = f"{fit.fitting_type}_{fit.size_mm}"
            if key not in materials:
                materials[key] = {
                    "наименование": f"{fit.fitting_type} {fit.size_mm}",
                    "ед_изм": "шт",
                    "количество": 0,
                }
            materials[key]["количество"] += fit.quantity

        return list(materials.values())


# ═══════════════════════════════════════════════════════════════
# НОРМЫ (СП 60.13330, СП 7.13130)
# ═══════════════════════════════════════════════════════════════

# Кратность воздухообмена по СП 60.13330
AIR_EXCHANGE_NORMS = {
    "living": {"supply": 3, "exhaust": 0, "min_m3h": 30},  # м³/ч на человека
    "bedroom": {"supply": 2, "exhaust": 0, "min_m3h": 30},
    "kitchen": {"supply": 0, "exhaust": 6, "min_m3h": 60},
    "bathroom": {"supply": 0, "exhaust": 10, "min_m3h": 25},
    "toilet": {"supply": 0, "exhaust": 10, "min_m3h": 25},
    "office": {"supply": 3, "exhaust": 0, "min_m3h": 60},
    "conference": {"supply": 3, "exhaust": 0, "min_m3h": 40},
    "corridor": {"supply": 0, "exhaust": 0, "min_m3h": 0},
    "hallway": {"supply": 0, "exhaust": 0, "min_m3h": 0},
    "server_room": {"supply": 5, "exhaust": 5, "min_m3h": 100},
    "warehouse": {"supply": 1, "exhaust": 1, "min_m3h": 20},
    "restaurant": {"supply": 3, "exhaust": 3, "min_m3h": 60},
    "hospital_ward": {"supply": 4, "exhaust": 4, "min_m3h": 80},
    "classroom": {"supply": 3, "exhaust": 0, "min_m3h": 30},
    "gym": {"supply": 4, "exhaust": 4, "min_m3h": 80},
    "pool": {"supply": 4, "exhaust": 4, "min_m3h": 80},
    "garage": {"supply": 0, "exhaust": 6, "min_m3h": 100},
}

# Максимальные скорости воздуха в воздуховодах (м/с)
MAX_VELOCITIES = {
    "main_duct": 8.0,
    "branch_duct": 5.0,
    "apartment_duct": 4.0,
    "noise_sensitive": 3.0,
    "exhaust_kitchen": 6.0,
    "fire_duct": 15.0,
}

# Стандартные сечения воздуховодов (мм)
STANDARD_DUCT_SIZES = {
    "round": [100, 125, 160, 200, 250, 315, 355, 400, 450, 500, 560, 630, 710, 800, 900, 1000, 1120, 1250],
    "rectangular": [
        (200, 100), (250, 100), (250, 150), (300, 150), (300, 200),
        (400, 200), (400, 250), (500, 250), (500, 300), (500, 400),
        (630, 300), (630, 400), (630, 500), (800, 400), (800, 500),
        (800, 630), (1000, 500), (1000, 630), (1000, 800),
        (1250, 630), (1250, 800), (1250, 1000), (1600, 800),
    ],
}


# ═══════════════════════════════════════════════════════════════
# AGENT
# ═══════════════════════════════════════════════════════════════


class DuctAnalysisAgent(BaseAgent):
    """Агент анализа чертежей воздуховодов и спецификаций."""

    name = "duct_analysis"

    def process(self, task: Task) -> TaskResult:
        start = time.time()
        try:
            params = task.params
            action = params.get("action", "analyze_blueprint")

            if action == "analyze_blueprint":
                result = self._analyze_blueprint(params)
            elif action == "parse_specification":
                result = self._parse_specification(params)
            elif action == "calculate_airflow":
                result = self._calculate_airflow(params)
            elif action == "design_duct_layout":
                result = self._design_duct_layout(params)
            elif action == "check_compliance":
                result = self._check_compliance(params)
            elif action == "generate_schedule":
                result = self._generate_schedule(params)
            else:
                result = self._analyze_blueprint(params)

            return TaskResult(
                status=TaskStatus.DONE,
                data=result,
                duration_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            logger.error("DuctAnalysisAgent error: %s", e)
            return TaskResult(
                status=TaskStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

    # ═══════════════════════════════════════════════════════════
    # 1. АНАЛИЗ ЧЕРТЕЖА (PDF/DWG/IMAGE)
    # ═══════════════════════════════════════════════════════════

    def _analyze_blueprint(self, params: dict) -> dict:
        """
        Анализ загруженного чертежа воздуховодов.
        Принимает данные от pdf_analysis_agent или dwg_analysis_agent,
        либо напрямую анализирует изображение через LLM vision.
        """
        source = params.get("source", "")  # pdf_data, dwg_data, image_url
        source_type = params.get("source_type", "pdf")  # pdf, dwg, image
        raw_text = params.get("raw_text", "")
        layers = params.get("layers", [])
        rooms_from_plan = params.get("rooms", [])

        spec = DuctSpecification(
            project_name=params.get("project_name", ""),
            drawing_number=params.get("drawing_number", ""),
        )

        if source_type == "pdf" and raw_text:
            self._extract_ducts_from_text(raw_text, spec)
        elif source_type == "dwg" and layers:
            self._extract_ducts_from_dxf(layers, spec)
        elif source_type == "image":
            return self._analyze_duct_image(params)
        else:
            spec.warnings.append("Нет данных для анализа. Загрузите PDF, DWG или изображение чертежа.")

        # Расчёт расходов по помещениям если есть данные о комнатах
        if rooms_from_plan and not spec.rooms:
            spec.rooms = self._calculate_room_ventilation(rooms_from_plan, spec)

        # Проверка соответствия нормам
        spec.compliance = self._check_norms(spec)

        return spec.to_dict()

    def _extract_ducts_from_text(self, text: str, spec: DuctSpecification):
        """Извлечение воздуховодов из текста PDF (таблицы спецификаций)."""
        lines = text.split("\n")
        segment_idx = 1

        for i, line in enumerate(lines):
            line_lower = line.lower().strip()

            # Поиск размеров воздуховодов: 800x400, Ø200, 800×400
            rect_match = re.findall(r'(\d{2,4})\s*[x×х]\s*(\d{2,4})', line)
            round_match = re.findall(r'[øØ⌀]\s*(\d{2,4})', line)

            # Определение типа (приток/вытяжка)
            duct_type = "unknown"
            if any(kw in line_lower for kw in ["приточ", "подач", "supply", "прит."]):
                duct_type = "supply"
            elif any(kw in line_lower for kw in ["вытяж", "отвод", "exhaust", "выт."]):
                duct_type = "exhaust"
            elif any(kw in line_lower for kw in ["рециркул", "recircul"]):
                duct_type = "recirculation"
            elif any(kw in line_lower for kw in ["противопожар", "огнестойк", "fire", "ei "]):
                duct_type = "fire"

            # Материал
            material = "galvanized_steel"
            if "нержавеющ" in line_lower or "stainless" in line_lower:
                material = "stainless"
            elif "пластик" in line_lower or "пвх" in line_lower or "plastic" in line_lower:
                material = "plastic"
            elif "гибк" in line_lower or "flex" in line_lower:
                material = "flexible"

            # Изоляция
            insulation_type = ""
            insulation_mm = 0
            ins_match = re.search(r'(?:утепл|изоляц|insul)\w*\s*(\d+)\s*мм', line_lower)
            if ins_match:
                insulation_mm = int(ins_match.group(1))
                if "минват" in line_lower or "mineral" in line_lower:
                    insulation_type = "mineral_wool"
                elif "пенопол" in line_lower or "foam" in line_lower:
                    insulation_type = "foam"
                else:
                    insulation_type = "mineral_wool"

            # Огнестойкость
            fire_rating = ""
            fire_match = re.search(r'[eE][iI]\s*(\d+)', line)
            if fire_match:
                fire_rating = f"EI {fire_match.group(1)}"

            # Длина
            length = 0.0
            len_match = re.search(r'(\d+[.,]?\d*)\s*(?:м|meter|m\b)', line_lower)
            if len_match:
                length = float(len_match.group(1).replace(",", "."))

            # Расход воздуха
            airflow = 0.0
            air_match = re.search(r'(\d+[.,]?\d*)\s*(?:м³/ч|m3/h|куб)', line_lower)
            if air_match:
                airflow = float(air_match.group(1).replace(",", "."))

            # Создание сегментов
            for w, h in rect_match:
                seg = DuctSegment(
                    segment_id=f"D{segment_idx}",
                    duct_type=duct_type,
                    shape="rectangular",
                    width_mm=int(w),
                    height_mm=int(h),
                    length_m=length,
                    material=material,
                    insulation_type=insulation_type,
                    insulation_thickness_mm=insulation_mm,
                    fire_rating=fire_rating,
                    airflow_m3h=airflow,
                )
                spec.segments.append(seg)
                segment_idx += 1

            for d in round_match:
                seg = DuctSegment(
                    segment_id=f"D{segment_idx}",
                    duct_type=duct_type,
                    shape="round",
                    diameter_mm=int(d),
                    length_m=length,
                    material=material,
                    insulation_type=insulation_type,
                    insulation_thickness_mm=insulation_mm,
                    fire_rating=fire_rating,
                    airflow_m3h=airflow,
                )
                spec.segments.append(seg)
                segment_idx += 1

            # Фасонные изделия
            self._extract_fittings_from_line(line, spec)

        # Итого
        spec.total_duct_length_m = sum(s.length_m for s in spec.segments)
        spec.total_airflow_supply_m3h = sum(s.airflow_m3h for s in spec.segments if s.duct_type == "supply")
        spec.total_airflow_exhaust_m3h = sum(s.airflow_m3h for s in spec.segments if s.duct_type == "exhaust")

    def _extract_ducts_from_dxf(self, layers: list, spec: DuctSpecification):
        """Извлечение воздуховодов из DXF слоёв."""
        segment_idx = 1
        mep_layers = [l for l in layers if l.get("element_type") == "mep" or "hvac" in l.get("name", "").lower()
                       or "duct" in l.get("name", "").lower() or "vent" in l.get("name", "").lower()]

        for layer in mep_layers:
            layer_name = layer.get("name", "").lower()
            duct_type = "unknown"
            if "supply" in layer_name or "приточ" in layer_name:
                duct_type = "supply"
            elif "exhaust" in layer_name or "вытяж" in layer_name:
                duct_type = "exhaust"

            seg = DuctSegment(
                segment_id=f"D{segment_idx}",
                duct_type=duct_type,
                material="galvanized_steel",
                annotations=[f"Слой: {layer.get('name', '')}"],
            )
            spec.segments.append(seg)
            segment_idx += 1

    def _analyze_duct_image(self, params: dict) -> dict:
        """
        Анализ изображения чертежа через LLM Vision.
        Возвращает промпт для вызова LLM с изображением.
        """
        image_url = params.get("image_url", "")
        return {
            "status": "requires_vision_llm",
            "instruction": "Для анализа изображения чертежа воздуховодов используйте LLM Vision API",
            "prompt": (
                "Проанализируй чертёж системы вентиляции. Извлеки:\n"
                "1. Все воздуховоды: сечение (мм), тип (приток/вытяжка), длина\n"
                "2. Фасонные изделия: отводы, тройники, переходы\n"
                "3. Оборудование: вентиляторы, фильтры, рекуператоры, клапаны\n"
                "4. Расход воздуха по помещениям (м³/ч)\n"
                "5. Материал и изоляцию воздуховодов\n"
                "6. Размеры на чертеже и масштаб\n"
                "Верни структурированный JSON."
            ),
            "image_url": image_url,
        }

    # ═══════════════════════════════════════════════════════════
    # 2. ПАРСИНГ СПЕЦИФИКАЦИИ
    # ═══════════════════════════════════════════════════════════

    def _parse_specification(self, params: dict) -> dict:
        """Парсинг текстовой спецификации воздуховодов."""
        text = params.get("text", "")
        spec = DuctSpecification(
            project_name=params.get("project_name", ""),
        )
        self._extract_ducts_from_text(text, spec)
        spec.compliance = self._check_norms(spec)
        return spec.to_dict()

    # ═══════════════════════════════════════════════════════════
    # 3. РАСЧЁТ РАСХОДА ВОЗДУХА
    # ═══════════════════════════════════════════════════════════

    def _calculate_airflow(self, params: dict) -> dict:
        """Расчёт расхода воздуха по помещениям согласно СП 60.13330."""
        rooms = params.get("rooms", [])
        height_m = params.get("height_m", 3.0)
        occupants = params.get("occupants", {})

        result = []
        total_supply = 0.0
        total_exhaust = 0.0

        for room in rooms:
            rtype = room.get("type", "living").lower()
            area = room.get("area_m2", room.get("width", 3) * room.get("length", 4))
            volume = area * height_m
            people = occupants.get(rtype, max(1, int(area / 10)))

            norm = AIR_EXCHANGE_NORMS.get(rtype, AIR_EXCHANGE_NORMS["living"])

            # По кратности
            by_exchange = volume * norm["supply"]
            # По человеку
            by_person = norm["min_m3h"] * people
            # Итого (максимум)
            supply = max(by_exchange, by_person)

            exhaust = volume * norm["exhaust"] if norm["exhaust"] > 0 else 0

            # Сечение воздуховода (скорость ≤ 4 м/с для жилых)
            max_vel = MAX_VELOCITIES["apartment_duct"] if rtype in ("living", "bedroom", "kitchen") else MAX_VELOCITIES["branch_duct"]
            supply_area_m2 = supply / 3600 / max_vel if supply > 0 else 0
            exhaust_area_m2 = exhaust / 3600 / max_vel if exhaust > 0 else 0

            supply_duct = self._select_duct_size(supply_area_m2 * 1e6)  # мм²
            exhaust_duct = self._select_duct_size(exhaust_area_m2 * 1e6)

            room_vent = RoomVentilation(
                room_name=room.get("name", rtype),
                room_area_m2=round(area, 1),
                room_volume_m3=round(volume, 1),
                supply_airflow_m3h=round(supply),
                exhaust_airflow_m3h=round(exhaust),
                air_exchange_rate=round(supply / volume, 2) if volume > 0 else 0,
                supply_diffusers=max(1, int(supply / 150)),
                exhaust_grilles=max(1, int(exhaust / 150)),
                duct_size_supply=supply_duct,
                duct_size_exhaust=exhaust_duct,
                norm_reference="СП 60.13330",
            )
            result.append(room_vent.to_dict())
            total_supply += supply
            total_exhaust += exhaust

        return {
            "rooms": result,
            "total_supply_m3h": round(total_supply),
            "total_exhaust_m3h": round(total_exhaust),
            "total_airflow_m3h": round(total_supply + total_exhaust),
            "norm": "СП 60.13330.2020",
        }

    # ═══════════════════════════════════════════════════════════
    # 4. ПРОЕКТИРОВАНИЕ СХЕМЫ ВОЗДУХОВОДОВ
    # ═══════════════════════════════════════════════════════════

    def _design_duct_layout(self, params: dict) -> dict:
        """Проектирование схемы разводки воздуховодов."""
        rooms = params.get("rooms", [])
        building_type = params.get("building_type", "house")
        floors = params.get("floors", 1)
        ahu_location = params.get("ahu_location", "technical_room")

        segments = []
        fittings = []
        seg_idx = 1

        # Магистраль от вентустановки
        total_airflow = sum(r.get("supply_airflow_m3h", 0) for r in rooms)
        main_duct_size = self._select_duct_size(total_airflow / 3600 / MAX_VELOCITIES["main_duct"] * 1e6)

        segments.append(DuctSegment(
            segment_id=f"D{seg_idx}",
            duct_type="supply",
            shape="rectangular" if "×" in main_duct_size else "round",
            airflow_m3h=total_airflow,
            velocity_ms=min(MAX_VELOCITIES["main_duct"], total_airflow / 3600 / 0.2),
            material="galvanized_steel",
            annotations=["Магистраль от вентустановки"],
        ))

        # Ответвления по помещениям
        for room in rooms:
            seg_idx += 1
            room_airflow = room.get("supply_airflow_m3h", 0)
            branch_size = self._select_duct_size(room_airflow / 3600 / MAX_VELOCITIES["branch_duct"] * 1e6)

            segments.append(DuctSegment(
                segment_id=f"D{seg_idx}",
                duct_type="supply",
                shape="rectangular" if "×" in branch_size else "round",
                airflow_m3h=room_airflow,
                material="galvanized_steel",
                to_room=room.get("name", ""),
                annotations=[f"Ответвление в {room.get('name', '')}"],
            ))

            fittings.append(DuctFitting(
                fitting_id=f"F{seg_idx}",
                fitting_type="tee",
                size_mm=branch_size,
                location=f"Разделение на {room.get('name', '')}",
            ))

        return {
            "segments": [s.to_dict() for s in segments],
            "fittings": [f.to_dict() for f in fittings],
            "ahu_location": ahu_location,
            "total_supply_airflow_m3h": total_airflow,
            "main_duct_size": main_duct_size,
            "material": "Оцинкованная сталь ГОСТ 14918",
            "connection_type": "Фланцевое / ниппельное",
        }

    # ═══════════════════════════════════════════════════════════
    # 5. ПРОВЕРКА СООТВЕТСТВИЯ НОРМАМ
    # ═══════════════════════════════════════════════════════════

    def _check_compliance(self, params: dict) -> dict:
        """Проверка соответствия СП 60.13330 и СП 7.13130."""
        segments = params.get("segments", [])
        rooms = params.get("rooms", [])
        warnings = []

        # Проверка скоростей
        for seg in segments:
            vel = seg.get("velocity_ms", 0)
            if vel > MAX_VELOCITIES["main_duct"]:
                warnings.append(
                    f"⚠️ {seg.get('segment_id', '?')}: скорость {vel} м/с > макс. {MAX_VELOCITIES['main_duct']} м/с"
                )

        # Проверка огнестойкости (СП 7.13130)
        for seg in segments:
            if seg.get("duct_type") == "fire" and not seg.get("fire_rating"):
                warnings.append(
                    f"⚠️ {seg.get('segment_id', '?')}: противопожарный воздуховод без класса огнестойкости"
                )

        # Проверка воздухообмена
        for room in rooms:
            rtype = room.get("type", "living").lower()
            norm = AIR_EXCHANGE_NORMS.get(rtype)
            if norm:
                actual = room.get("supply_airflow_m3h", 0)
                required = norm["min_m3h"]
                if actual < required:
                    warnings.append(
                        f"⚠️ {room.get('name', '?')}: расход {actual} м³/ч < нормы {required} м³/ч"
                    )

        return {
            "compliant": len(warnings) == 0,
            "warnings": warnings,
            "norms_checked": ["СП 60.13330.2020", "СП 7.13130.2011", "ГОСТ 21.1101"],
        }

    # ═══════════════════════════════════════════════════════════
    # 6. ГЕНЕРАЦИЯ СПЕЦИФИКАЦИИ
    # ═══════════════════════════════════════════════════════════

    def _generate_schedule(self, params: dict) -> dict:
        """Генерация спецификации воздуховодов по ГОСТ 21.1101."""
        segments = params.get("segments", [])
        fittings = params.get("fittings", [])

        duct_schedule = []
        for seg in segments:
            size = f"Ø{seg.get('diameter_mm', 0)}" if seg.get("shape") == "round" else f"{seg.get('width_mm', 0)}×{seg.get('height_mm', 0)}"
            duct_schedule.append({
                "позиция": seg.get("segment_id", ""),
                "сечение_мм": size,
                "длина_м": seg.get("length_m", 0),
                "материал": seg.get("material", ""),
                "изоляция": seg.get("insulation_type", ""),
                "огнестойкость": seg.get("fire_rating", "нет"),
            })

        fitting_schedule = []
        for fit in fittings:
            fitting_schedule.append({
                "позиция": fit.get("fitting_id", ""),
                "тип": fit.get("fitting_type", ""),
                "размер_мм": fit.get("size_mm", ""),
                "количество": fit.get("quantity", 1),
            })

        return {
            "format": "ГОСТ 21.1101",
            "воздуховоды": duct_schedule,
            "фасонные_изделия": fitting_schedule,
        }

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _select_duct_size(self, area_mm2: float) -> str:
        """Подбор стандартного сечения воздуховода по площади."""
        if area_mm2 <= 0:
            return "Ø100"

        # Круглые
        for d in STANDARD_DUCT_SIZES["round"]:
            circle_area = 3.14159 * (d / 2) ** 2
            if circle_area >= area_mm2:
                return f"Ø{d}"

        # Прямоугольные
        for w, h in STANDARD_DUCT_SIZES["rectangular"]:
            if w * h >= area_mm2:
                return f"{w}×{h}"

        return "1600×800"

    def _extract_fittings_from_line(self, line: str, spec: DuctSpecification):
        """Извлечение фасонных изделий из строки."""
        line_lower = line.lower()
        fitting_type = ""
        if "отвод" in line_lower or "elbow" in line_lower:
            fitting_type = "elbow"
        elif "тройник" in line_lower or "tee" in line_lower:
            fitting_type = "tee"
        elif "переход" in line_lower or "reducer" in line_lower or "transition" in line_lower:
            fitting_type = "reducer"
        elif "заслонк" in line_lower or "damper" in line_lower:
            fitting_type = "damper"
        elif "решётк" in line_lower or "grille" in line_lower:
            fitting_type = "grille"
        elif "диффузор" in line_lower or "diffuser" in line_lower:
            fitting_type = "diffuser"

        if fitting_type:
            size_match = re.search(r'(\d{2,4})\s*[x×х]\s*(\d{2,4})', line)
            round_match = re.search(r'[øØ⌀]\s*(\d{2,4})', line)
            size = ""
            if size_match:
                size = f"{size_match.group(1)}×{size_match.group(2)}"
            elif round_match:
                size = f"Ø{round_match.group(1)}"

            qty_match = re.search(r'(\d+)\s*(?:шт|pcs|×)', line)
            qty = int(qty_match.group(1)) if qty_match else 1

            spec.fittings.append(DuctFitting(
                fitting_id=f"F{len(spec.fittings) + 1}",
                fitting_type=fitting_type,
                size_mm=size,
                quantity=qty,
            ))

    def _calculate_room_ventilation(self, rooms: list, spec: DuctSpecification) -> list[RoomVentilation]:
        """Рассчитать вентиляцию для каждого помещения."""
        result = []
        for room in rooms:
            rtype = room.get("type", "living").lower()
            area = room.get("area_m2", room.get("width", 3) * room.get("length", 4))
            volume = area * room.get("height_m", 3.0)
            norm = AIR_EXCHANGE_NORMS.get(rtype, AIR_EXCHANGE_NORMS["living"])

            supply = max(norm["min_m3h"], volume * norm["supply"])
            exhaust = volume * norm["exhaust"] if norm["exhaust"] > 0 else 0

            result.append(RoomVentilation(
                room_name=room.get("name", rtype),
                room_area_m2=round(area, 1),
                room_volume_m3=round(volume, 1),
                supply_airflow_m3h=round(supply),
                exhaust_airflow_m3h=round(exhaust),
                air_exchange_rate=round(supply / volume, 2) if volume > 0 else 0,
                norm_reference="СП 60.13330",
            ))
        return result

    def _check_norms(self, spec: DuctSpecification) -> list[dict]:
        """Проверка норм для спецификации."""
        compliance = []
        for room in spec.rooms:
            norm = AIR_EXCHANGE_NORMS.get(room.room_name.lower(), {})
            if norm:
                ok = room.supply_airflow_m3h >= norm.get("min_m3h", 0)
                compliance.append({
                    "room": room.room_name,
                    "norm": "СП 60.13330",
                    "required_m3h": norm.get("min_m3h", 0),
                    "actual_m3h": room.supply_airflow_m3h,
                    "compliant": ok,
                })
        return compliance
