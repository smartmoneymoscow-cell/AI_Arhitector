"""
shared/norm_engine.py — Движок проверки строительных норм.

Проверяет соответствие проекта нормативным документам:
    - СП 1.13130 — Эвакуационные пути и выходы
    - СП 54.13330 — Жилые здания (многоквартирные)
    - ГОСТ 21.501 — Правила выполнения рабочей документации
    - IBC — International Building Code
    - СП 20.13330 — Нагрузки и воздействия
    - СП 50.13330 — Тепловая защита зданий

Использование:
    from shared.norm_engine import NormEngine

    engine = NormEngine()
    report = engine.check_building(params)
    # → NormReport(passed=True/False, violations=[...], warnings=[...])
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class Severity(StrEnum):
    CRITICAL = "critical"  # Нарушение обязательных норм
    WARNING = "warning"  # Рекомендация
    INFO = "info"  # Информационное замечание


class NormCode(StrEnum):
    SP_EVACUATION = "СП 1.13130"
    SP_RESIDENTIAL = "СП 54.13330"
    GOST_DRAWINGS = "ГОСТ 21.501"
    IBC = "IBC"
    SP_LOADS = "СП 20.13330"
    SP_THERMAL = "СП 50.13330"
    SP_FIRE = "СП 4.13130"
    SP_STAIRS = "СП 1.13130.2019"
    SP_LIGHTING = "СП 52.13330"
    SP_VENTILATION = "СП 60.13330"
    SP_PLUMBING = "СП 73.13330"  # Внутренние санитарно-технические системы
    SP_ELECTRICAL = "СП 76.13330"  # Электрооборудование
    SP_ELECTRICAL_INSTALL = "СП 256.1325800"  # Электроустановки жилых зданий
    PUE = "ПУЭ"  # Правила устройства электроустановок (7-е изд.)
    SP_LANDSCAPE = "СП 82.13330"  # Благоустройство территорий
    SP_URBAN = "СП 42.13330"  # Планировка и застройка
    GOST_ELECTRICAL_SYMBOLS = "ГОСТ 21.608"  # Условные обозначения электрических схем
    SP_STOVE = "СП 7.13130"  # Отопление, вентиляция, кондиционирование (печные работы)
    SNI_SEISMIC = "SNI 1726"  # Сейсмические требования (Индонезия)
    SNI_BUILDING = "SNI 2847"  # Строительные нормы (Индонезия)
    AISI_LSTK = "AISI S100"  # ЛСТК конструкции


@dataclass
class NormViolation:
    """Одно нарушение/замечание."""

    code: NormCode
    section: str
    severity: Severity
    message: str
    recommendation: str = ""
    parameter: str = ""
    actual_value: str = ""
    required_value: str = ""


@dataclass
class NormReport:
    """Отчёт проверки норм."""

    passed: bool = True
    violations: list[NormViolation] = field(default_factory=list)
    warnings: list[NormViolation] = field(default_factory=list)
    info: list[NormViolation] = field(default_factory=list)
    checked_norms: list[str] = field(default_factory=list)
    score: float = 100.0  # 0-100

    def add_violation(self, v: NormViolation):
        if v.severity == Severity.CRITICAL:
            self.violations.append(v)
            self.passed = False
            self.score = max(0, self.score - 20)
        elif v.severity == Severity.WARNING:
            self.warnings.append(v)
            self.score = max(0, self.score - 5)
        else:
            self.info.append(v)

    @property
    def summary(self) -> str:
        parts = []
        if self.violations:
            parts.append(f"❌ {len(self.violations)} критических нарушений")
        if self.warnings:
            parts.append(f"⚠️ {len(self.warnings)} предупреждений")
        if self.info:
            parts.append(f"ℹ️ {len(self.info)} замечаний")
        if not parts:
            parts.append("✅ Все проверки пройдены")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "score": self.score,
            "violations": len(self.violations),
            "warnings": len(self.warnings),
            "info": len(self.info),
            "summary": self.summary,
            "details": [
                {
                    "code": v.code.value,
                    "section": v.section,
                    "severity": v.severity.value,
                    "message": v.message,
                    "recommendation": v.recommendation,
                }
                for v in self.violations + self.warnings + self.info
            ],
        }


class NormEngine:
    """
    Движок проверки строительных норм.

    Проверяет параметры здания/интерьера against:
    - Российские СП и ГОСТ
    - International Building Code (IBC)
    """

    # Минимальные размеры (м)
    MIN_ROOM_WIDTH = 2.0
    MIN_ROOM_LENGTH = 2.5
    MIN_ROOM_HEIGHT = 2.5
    MIN_KITCHEN_AREA = 8.0
    MIN_BEDROOM_AREA = 8.0
    MIN_BATHROOM_AREA = 1.5
    MIN_HALLWAY_WIDTH = 1.4
    MIN_DOOR_WIDTH = 0.8
    MIN_WINDOW_AREA_RATIO = 0.1  # 10% от площади пола

    # Лестницы
    MIN_STAIR_WIDTH = 0.9
    MAX_STAIR_RISE = 0.20  # м
    MIN_STAIR_TREAD = 0.26  # м
    MAX_STAIR_FLIGHT = 18  # ступеней без площадки

    # Эвакуация
    MAX_EVAC_DISTANCE_SINGLE = 25  # м (одной лестницей)
    MAX_EVAC_DISTANCE_MULTI = 40  # м (две лестницы)
    MIN_EXIT_WIDTH = 0.9

    # Этажность
    MAX_FLOORS_NO_ELEVATOR = 5
    MAX_FLOORS_RESIDENTIAL = 9  # без спец. мер

    def check_building(self, params: dict) -> NormReport:
        """
        Полная проверка здания.

        Args:
            params: словарь параметров здания:
                - floors: int
                - width_m, length_m, height_m: float
                - room_type: str
                - rooms: list[dict] (опционально)
                - has_elevator: bool
                - has_balcony: bool
                - material: str
                - building_type: str (residential/commercial/mixed)

        Returns:
            NormReport
        """
        report = NormReport()
        report.checked_norms = [
            NormCode.SP_RESIDENTIAL.value,
            NormCode.SP_EVACUATION.value,
            NormCode.SP_THERMAL.value,
            NormCode.SP_FIRE.value,
            NormCode.GOST_DRAWINGS.value,
        ]

        floors = params.get("floors", 1)
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        height = params.get("height_m", 3.0)
        building_type = params.get("building_type", "residential")
        has_elevator = params.get("has_elevator", False)
        rooms = params.get("rooms", [])

        # СП 54.13330 — Жилые здания
        self._check_residential(report, params, floors, width, length, height)

        # СП 1.13130 — Эвакуация
        self._check_evacuation(report, params, floors, width, length)

        # Этажность
        self._check_floors(report, floors, has_elevator)

        # Высота помещений
        self._check_height(report, height, building_type)

        # Комнаты (если есть)
        if rooms:
            self._check_rooms(report, rooms)

        # Лестницы (если >1 этажа)
        if floors > 1:
            self._check_stairs(report, params)

        # Площадь остекления
        self._check_glazing(report, params, width, length)

        # Теплозащита (СП 50.13330)
        self._check_thermal(report, params)

        return report

    def check_interior(self, params: dict) -> NormReport:
        """Проверка интерьера (комната)."""
        report = NormReport()
        report.checked_norms = [NormCode.SP_RESIDENTIAL.value]

        width = params.get("width_m", 6)
        length = params.get("length_m", 8)
        height = params.get("height_m", 3.0)
        room_type = params.get("room_type", "living")

        area = width * length

        if room_type == "kitchen" and area < self.MIN_KITCHEN_AREA:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="8.2",
                    severity=Severity.WARNING,
                    message=f"Площадь кухни {area:.1f} м² < минимума {self.MIN_KITCHEN_AREA} м²",
                    recommendation="Увеличьте площадь кухни до 8 м²",
                    parameter="kitchen_area",
                    actual_value=f"{area:.1f}",
                    required_value=f">= {self.MIN_KITCHEN_AREA}",
                )
            )

        if room_type == "bedroom" and area < self.MIN_BEDROOM_AREA:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="8.3",
                    severity=Severity.WARNING,
                    message=f"Площадь спальни {area:.1f} м² < минимума {self.MIN_BEDROOM_AREA} м²",
                    recommendation="Увеличьте площадь спальни",
                    parameter="bedroom_area",
                    actual_value=f"{area:.1f}",
                    required_value=f">= {self.MIN_BEDROOM_AREA}",
                )
            )

        if height < self.MIN_ROOM_HEIGHT:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="5.5",
                    severity=Severity.CRITICAL,
                    message=f"Высота {height} м < минимума {self.MIN_ROOM_HEIGHT} м",
                    recommendation="Увеличьте высоту потолков",
                    parameter="height",
                    actual_value=f"{height}",
                    required_value=f">= {self.MIN_ROOM_HEIGHT}",
                )
            )

        return report

    def _check_residential(
        self, report: NormReport, params: dict, floors: int, width: float, length: float, height: float
    ):
        area = width * length
        if area < 20:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="5.2",
                    severity=Severity.WARNING,
                    message=f"Площадь здания {area:.0f} м² мала для жилого дома",
                    recommendation="Рассмотрите увеличение площади",
                )
            )

    def _check_evacuation(self, report: NormReport, params: dict, floors: int, width: float, length: float):
        max_dim = max(width, length)
        if floors <= 2:
            max_dist = self.MAX_EVAC_DISTANCE_SINGLE
        else:
            max_dist = self.MAX_EVAC_DISTANCE_MULTI

        if max_dim > max_dist:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_EVACUATION,
                    section="6",
                    severity=Severity.CRITICAL,
                    message=f"Макс. расстояние эвакуации {max_dim:.0f} м > допустимого {max_dist} м",
                    recommendation="Добавьте второй эвакуационный выход",
                    parameter="evac_distance",
                    actual_value=f"{max_dim:.0f}",
                    required_value=f"<= {max_dist}",
                )
            )

    def _check_floors(self, report: NormReport, floors: int, has_elevator: bool):
        if floors > self.MAX_FLOORS_NO_ELEVATOR and not has_elevator:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="5.4",
                    severity=Severity.CRITICAL,
                    message=f"Этажность {floors} > {self.MAX_FLOORS_NO_ELEVATOR} без лифта",
                    recommendation="Установите лифт или уменьшите этажность",
                    parameter="floors",
                    actual_value=str(floors),
                    required_value=f"<= {self.MAX_FLOORS_NO_ELEVATOR} без лифта",
                )
            )

        if floors > self.MAX_FLOORS_RESIDENTIAL:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="5.3",
                    severity=Severity.WARNING,
                    message=f"Этажность {floors} > типичного максимума {self.MAX_FLOORS_RESIDENTIAL}",
                    recommendation="Требуются спец. меры пожарной безопасности",
                )
            )

    def _check_height(self, report: NormReport, height: float, building_type: str):
        min_h = self.MIN_ROOM_HEIGHT
        if building_type == "commercial":
            min_h = 3.0
        if height < min_h:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_RESIDENTIAL,
                    section="5.5",
                    severity=Severity.CRITICAL,
                    message=f"Высота потолков {height} м < минимума {min_h} м",
                    recommendation=f"Увеличьте высоту до {min_h} м",
                    parameter="height",
                    actual_value=str(height),
                    required_value=f">= {min_h}",
                )
            )

    def _check_rooms(self, report: NormReport, rooms: list[dict]):
        for room in rooms:
            rtype = room.get("type", "living")
            area = room.get("width", 3) * room.get("length", 4)

            if rtype == "bathroom" and area < self.MIN_BATHROOM_AREA:
                report.add_violation(
                    NormViolation(
                        code=NormCode.SP_RESIDENTIAL,
                        section="8.5",
                        severity=Severity.WARNING,
                        message=f"Санузел {area:.1f} м² < минимума {self.MIN_BATHROOM_AREA} м²",
                        parameter="bathroom_area",
                        actual_value=f"{area:.1f}",
                        required_value=f">= {self.MIN_BATHROOM_AREA}",
                    )
                )

    def _check_stairs(self, report: NormReport, params: dict):
        stair_width = params.get("stair_width", 1.0)
        if stair_width < self.MIN_STAIR_WIDTH:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_STAIRS,
                    section="7",
                    severity=Severity.CRITICAL,
                    message=f"Ширина лестницы {stair_width} м < минимума {self.MIN_STAIR_WIDTH} м",
                    recommendation="Увеличьте ширину лестницы",
                    parameter="stair_width",
                    actual_value=str(stair_width),
                    required_value=f">= {self.MIN_STAIR_WIDTH}",
                )
            )

    def _check_glazing(self, report: NormReport, params: dict, width: float, length: float):
        floor_area = width * length
        window_area = params.get("window_area", 0)
        if window_area > 0:
            ratio = window_area / floor_area
            if ratio < self.MIN_WINDOW_AREA_RATIO:
                report.add_violation(
                    NormViolation(
                        code=NormCode.SP_RESIDENTIAL,
                        section="6.3",
                        severity=Severity.WARNING,
                        message=f"Остекление {ratio:.1%} < минимума {self.MIN_WINDOW_AREA_RATIO:.0%}",
                        recommendation="Увеличьте площадь окон",
                        parameter="glazing_ratio",
                        actual_value=f"{ratio:.2%}",
                        required_value=f">= {self.MIN_WINDOW_AREA_RATIO:.0%}",
                    )
                )

    def _check_thermal(self, report: NormReport, params: dict):
        material = params.get("material", "")
        if material in ("glass", "стекло"):
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_THERMAL,
                    section="5",
                    severity=Severity.WARNING,
                    message="Полностью стеклянный фасад требует расчёта теплозащиты",
                    recommendation="Добавьте теплоизоляцию или уменьшите остекление",
                )
            )

    # ═══ Расширения: тропики, бани, электрика, ЛСТК ═══

    def check_tropical(self, params: dict) -> NormReport:
        """Проверка для тропического климата (Бали, SNI)."""
        report = NormReport()
        report.checked_norms = [NormCode.SNI_SEISMIC.value, NormCode.SNI_BUILDING.value]

        # Сейсмика
        seismic_zone = params.get("seismic_zone", 0)
        if seismic_zone >= 5:
            report.add_violation(
                NormViolation(
                    code=NormCode.SNI_SEISMIC,
                    section="3.2",
                    severity=Severity.CRITICAL,
                    message=f"Сейсмическая зона {seismic_zone} — требуется усиленный конструктив",
                    recommendation="Увеличить армирование, применить сейсмостойкие узлы",
                )
            )

        # Вентиляция (тропики: усиленная)
        ventilation_rate = params.get("ventilation_rate_ach", 0)
        if ventilation_rate < 3:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_VENTILATION,
                    section="7.2",
                    severity=Severity.WARNING,
                    message=f"Кратность вентиляции {ventilation_rate} < 3 (тропический климат)",
                    recommendation="Увеличить кратность до 3–5 для тропиков",
                )
            )

        # Теплозащита (тропики: защита от перегрева)
        roof_insulation = params.get("roof_insulation_r", 0)
        if roof_insulation < 3.0:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_THERMAL,
                    section="5.3",
                    severity=Severity.WARNING,
                    message=f"Теплосопротивление крыши R={roof_insulation} < 3.0 (защита от перегрева)",
                    recommendation="Добавить отражающую изоляцию или вентилируемую кровлю",
                )
            )

        return report

    def check_bathhouse(self, params: dict) -> NormReport:
        """Проверка для бани/сауны."""
        report = NormReport()
        report.checked_norms = [NormCode.SP_STOVE.value, NormCode.SP_VENTILATION.value]

        # Высота парилки
        sauna_height = params.get("sauna_height_m", 0)
        if sauna_height > 0:
            if sauna_height < 2.1 or sauna_height > 2.4:
                report.add_violation(
                    NormViolation(
                        code=NormCode.SP_RESIDENTIAL,
                        section="sauna",
                        severity=Severity.WARNING,
                        message=f"Высота парилки {sauna_height}м (оптимально 2.1–2.4м)",
                        recommendation="При h>2.4м жар уходит вверх, при h<2.1м неудобно",
                    )
                )

        # Зазор под дверью парилки
        door_gap = params.get("sauna_door_gap_mm", 0)
        if door_gap > 0 and door_gap < 50:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_VENTILATION,
                    section="sauna_door",
                    severity=Severity.CRITICAL,
                    message=f"Зазор под дверью парилки {door_gap}мм < 50мм",
                    recommendation="Увеличить зазор до ≥50мм для воздухообмена",
                )
            )

        # Вентиляция парилки
        sauna_vent = params.get("sauna_vent_ach", 0)
        if sauna_vent > 0 and sauna_vent < 5:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_VENTILATION,
                    section="sauna_vent",
                    severity=Severity.WARNING,
                    message=f"Кратность вентиляции парилки {sauna_vent} < 5",
                    recommendation="Увеличить до 5–6 крат (приток под печью, вытяжка на противоположной стене)",
                )
            )

        # Противопожарные расстояния от печи
        stove_clearance = params.get("stove_clearance_mm", 999)
        stove_protection = params.get("stove_has_heat_shield", False)
        if stove_clearance < 500 and not stove_protection:
            report.add_violation(
                NormViolation(
                    code=NormCode.SP_STOVE,
                    section="6.2",
                    severity=Severity.CRITICAL,
                    message=f"Расстояние от печи до стены {stove_clearance}мм без защиты < 500мм",
                    recommendation="Установить металлический экран или увеличить расстояние до ≥380мм с экраном",
                )
            )

        return report

    def check_electrical_apartment(self, params: dict) -> NormReport:
        """Проверка квартирной электрики (ПУЭ, СП 76.13330)."""
        report = NormReport()
        report.checked_norms = [NormCode.PUE.value, NormCode.SP_ELECTRICAL.value, NormCode.SP_ELECTRICAL_INSTALL.value]

        # УЗО на розеточные группы
        has_rcd = params.get("has_rcd_on_outlets", False)
        if not has_rcd:
            report.add_violation(
                NormViolation(
                    code=NormCode.PUE,
                    section="7.1.71",
                    severity=Severity.CRITICAL,
                    message="Отсутствует УЗО на розеточных группах",
                    recommendation="Установить УЗО 30мА на все розеточные группы",
                )
            )

        # УЗО в ванной
        bathroom_rcd_ma = params.get("bathroom_rcd_ma", 0)
        if bathroom_rcd_ma > 0 and bathroom_rcd_ma > 10:
            report.add_violation(
                NormViolation(
                    code=NormCode.PUE,
                    section="7.1.82",
                    severity=Severity.WARNING,
                    message=f"УЗО в ванной {bathroom_rcd_ma}мА > 10мА",
                    recommendation="Рекомендуется УЗО 10мА для ванных комнат",
                )
            )

        # Сечение кабелей
        lighting_cable = params.get("lighting_cable_mm2", 0)
        if lighting_cable > 0 and lighting_cable < 1.5:
            report.add_violation(
                NormViolation(
                    code=NormCode.PUE,
                    section="1.3.4",
                    severity=Severity.CRITICAL,
                    message=f"Сечение кабеля освещения {lighting_cable}мм² < 1.5мм²",
                    recommendation="Увеличить сечение до ≥1.5мм² (ВВгнг-LS)",
                )
            )

        outlet_cable = params.get("outlet_cable_mm2", 0)
        if outlet_cable > 0 and outlet_cable < 2.5:
            report.add_violation(
                NormViolation(
                    code=NormCode.PUE,
                    section="1.3.5",
                    severity=Severity.CRITICAL,
                    message=f"Сечение кабеля розеток {outlet_cable}мм² < 2.5мм²",
                    recommendation="Увеличить сечение до ≥2.5мм²",
                )
            )

        # Расстояние силовых и слаботочных
        power_data_gap = params.get("power_data_gap_mm", 999)
        if power_data_gap < 50:
            report.add_violation(
                NormViolation(
                    code=NormCode.PUE,
                    section="2.1.16",
                    severity=Severity.WARNING,
                    message=f"Расстояние силовых и слаботочных кабелей {power_data_gap}мм < 50мм",
                    recommendation="Увеличить расстояние до ≥50мм или разделить трассы",
                )
            )

        return report

    def check_lstk(self, params: dict) -> NormReport:
        """Проверка ЛСТК-конструкций (AISI S100)."""
        report = NormReport()
        report.checked_norms = [NormCode.AISI_LSTK.value]

        # Толщина стенки профиля
        wall_thickness = params.get("lstk_wall_thickness_mm", 0)
        if wall_thickness > 0 and wall_thickness < 0.8:
            report.add_violation(
                NormViolation(
                    code=NormCode.AISI_LSTK,
                    section="B2",
                    severity=Severity.WARNING,
                    message=f"Толщина стенки ЛСТК-профиля {wall_thickness}мм < 0.8мм",
                    recommendation="Увеличить толщину для конструкционных элементов",
                )
            )

        # Стык ЖБК + ЛСТК
        hybrid_joint = params.get("hybrid_rbc_lstk_joint", False)
        if hybrid_joint:
            joint_type = params.get("joint_type", "")
            if joint_type not in ("bolted", "welded", "chemical_anchor"):
                report.add_violation(
                    NormViolation(
                        code=NormCode.AISI_LSTK,
                        section="connection",
                        severity=Severity.WARNING,
                        message="Тип стыка ЖБК/ЛСТК не определён",
                        recommendation="Использовать болтовое, сварное или химическое соединение",
                    )
                )

        return report

    def get_norm_reference(self, code: NormCode) -> dict:
        """Получить справочную информацию по нормативному документу."""
        refs = {
            NormCode.SP_EVACUATION: {
                "full_name": "СП 1.13130.2019 Системы противопожарной защиты",
                "sections": ["Эвакуационные пути и выходы", "Расстояния эвакуации"],
                "key_requirements": [
                    "Макс. расстояние эвакуации: 25 м (одной лестницей), 40 м (две лестницы)",
                    "Мин. ширина эвакуационного выхода: 0.9 м",
                    "Не менее 2 эвакуационных выходов при этажности >1",
                ],
            },
            NormCode.SP_RESIDENTIAL: {
                "full_name": "СП 54.13330.2016 Жилые здания",
                "sections": ["Планировка", "Высота помещений", "Инженерные системы"],
                "key_requirements": [
                    "Мин. высота потолков: 2.5 м",
                    "Мин. площадь кухни: 8 м²",
                    "Мин. площадь спальни: 8 м²",
                    "Лифт обязателен при этажности >5",
                ],
            },
            NormCode.IBC: {
                "full_name": "International Building Code 2021",
                "sections": ["Chapter 10: Means of Egress", "Chapter 12: Interior Environment"],
                "key_requirements": [
                    "Max travel distance: 75 ft (sprinklered), 200 ft (non-sprinklered)",
                    "Min corridor width: 44 inches",
                    "Min ceiling height: 7 ft",
                ],
            },
        }
        return refs.get(code, {"full_name": code.value, "sections": [], "key_requirements": []})
