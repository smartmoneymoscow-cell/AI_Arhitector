"""
shared/cost_engine.py — Движок калькуляции стоимости строительства.

Рассчитывает:
    - Стоимость материалов (стены, крыша, фундамент, отделка)
    - Стоимость работ
    - Стоимость инженерных систем
    - Стоимость ландшафта
    - Итоговую смету

Использование:
    from shared.cost_engine import CostEngine

    engine = CostEngine()
    estimate = engine.calculate(params)
    # → CostEstimate(total=..., breakdown={...})
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CostLineItem:
    """Одна позиция сметы."""

    category: str  # "materials", "labor", "engineering", "landscape"
    item: str  # "Кирпичная кладка стен"
    unit: str  # "м²", "м³", "шт"
    quantity: float  # Количество
    unit_price: float  # Цена за единицу (руб)
    total: float = 0  # quantity * unit_price
    source: str = ""  # Источник цены

    def __post_init__(self):
        self.total = self.quantity * self.unit_price


@dataclass
class CostEstimate:
    """Итоговая смета."""

    currency: str = "RUB"
    items: list[CostLineItem] = field(default_factory=list)
    materials_cost: float = 0
    labor_cost: float = 0
    engineering_cost: float = 0
    landscape_cost: float = 0
    total: float = 0
    area_m2: float = 0
    cost_per_m2: float = 0
    contingency_pct: float = 10.0  # Непредвиденные расходы

    def add_item(self, item: CostLineItem):
        self.items.append(item)
        if item.category == "materials":
            self.materials_cost += item.total
        elif item.category == "labor":
            self.labor_cost += item.total
        elif item.category == "engineering":
            self.engineering_cost += item.total
        elif item.category == "landscape":
            self.landscape_cost += item.total
        self._recalc()

    def _recalc(self):
        subtotal = self.materials_cost + self.labor_cost + self.engineering_cost + self.landscape_cost
        contingency = subtotal * self.contingency_pct / 100
        self.total = subtotal + contingency
        if self.area_m2 > 0:
            self.cost_per_m2 = self.total / self.area_m2

    def to_dict(self) -> dict:
        return {
            "currency": self.currency,
            "total": round(self.total),
            "cost_per_m2": round(self.cost_per_m2),
            "area_m2": round(self.area_m2, 1),
            "breakdown": {
                "materials": round(self.materials_cost),
                "labor": round(self.labor_cost),
                "engineering": round(self.engineering_cost),
                "landscape": round(self.landscape_cost),
                "contingency_pct": self.contingency_pct,
            },
            "items_count": len(self.items),
            "items": [
                {
                    "category": i.category,
                    "item": i.item,
                    "unit": i.unit,
                    "quantity": round(i.quantity, 2),
                    "unit_price": round(i.unit_price),
                    "total": round(i.total),
                }
                for i in self.items
            ],
        }

    @property
    def summary(self) -> str:
        return (
            f"💰 Смета: {self.total:,.0f} ₽ "
            f"({self.cost_per_m2:,.0f} ₽/м² × {self.area_m2:.0f} м²)\n"
            f"  Материалы: {self.materials_cost:,.0f} ₽\n"
            f"  Работы: {self.labor_cost:,.0f} ₽\n"
            f"  Инженерия: {self.engineering_cost:,.0f} ₽\n"
            f"  Ландшафт: {self.landscape_cost:,.0f} ₽"
        )


class CostEngine:
    """
    Движок калькуляции стоимости строительства.

    Цены: Москва/МО, 2026 (среднерыночные).
    """

    # ═══ Материалы (руб/м² или руб/м³) ═══
    MATERIAL_COSTS = {
        # Стены (руб/м² площади стены)
        "brick": {"name": "Кирпич", "wall_m2": 4500, "finish_m2": 1200},
        "кирпич": {"name": "Кирпич", "wall_m2": 4500, "finish_m2": 1200},
        "wood": {"name": "Дерево (брус)", "wall_m2": 3800, "finish_m2": 800},
        "дерево": {"name": "Дерево (брус)", "wall_m2": 3800, "finish_m2": 800},
        "concrete": {"name": "Бетон", "wall_m2": 5000, "finish_m2": 1500},
        "бетон": {"name": "Бетон", "wall_m2": 5000, "finish_m2": 1500},
        "foam_block": {"name": "Пеноблок", "wall_m2": 2800, "finish_m2": 1000},
        "пеноблок": {"name": "Пеноблок", "wall_m2": 2800, "finish_m2": 1000},
        "steel": {"name": "Стальной каркас", "wall_m2": 6000, "finish_m2": 1500},
        "стекло": {"name": "Стеклянный фасад", "wall_m2": 12000, "finish_m2": 0},
        "glass": {"name": "Стеклянный фасад", "wall_m2": 12000, "finish_m2": 0},
        "plaster": {"name": "Штукатурка", "wall_m2": 3500, "finish_m2": 800},
        "штукатурка": {"name": "Штукатурка", "wall_m2": 3500, "finish_m2": 800},
        "default": {"name": "Стандарт", "wall_m2": 4000, "finish_m2": 1000},
    }

    # Крыша (руб/м² площади крыши)
    ROOF_COSTS = {
        "flat": 3500,
        "плоская": 3500,
        "gable": 5000,
        "двускатная": 5000,
        "hip": 6500,
        "вальмовая": 6500,
        "mansard": 8000,
        "мансардная": 8000,
        "default": 5000,
    }

    # Фундамент (руб/м² площади застройки)
    FOUNDATION_COSTS = {
        "slab": 5500,  # Плитный
        "strip": 4000,  # Ленточный
        "pile": 7000,  # Свайный
        "плитный": 5500,
        "ленточный": 4000,
        "свайный": 7000,
        "default": 4500,
    }

    # ═══ Работы (руб/м²) ═══
    LABOR_COSTS = {
        "masonry": 2500,
        "carpentry": 3000,
        "roofing": 2000,
        "finishing": 2500,
        "foundation": 2000,
        "default": 2500,
    }

    # ═══ Инженерные системы (руб/м² площади) ═══
    ENGINEERING_COSTS = {
        "electrical": 1500,
        "plumbing": 2000,
        "hvac": 3000,
        "fire_safety": 1000,
        "security": 800,
        "total": 8300,  # Суммарно
    }

    # ═══ Ландшафт (руб/м² участка) ═══
    LANDSCAPE_COSTS = {
        "lawn": 300,
        "planting": 800,
        "paving": 1500,
        "fencing": 2500,  # за погонный метр
        "pool": 50000,  # за штуку
        "total_per_m2": 1200,
    }

    def __init__(self, region: str = "moscow"):
        self.region = region
        self._region_multiplier = self._get_region_multiplier(region)

    def calculate(self, params: dict) -> CostEstimate:
        """
        Рассчитать полную смету.

        Args:
            params: параметры здания:
                - width_m, length_m: float (размеры)
                - floors: int
                - material: str
                - roof_type: str
                - foundation_type: str
                - has_landscape: bool
                - has_engineering: bool
                - lot_area_m2: float (площадь участка)

        Returns:
            CostEstimate
        """
        width = params.get("width_m", 10)
        length = params.get("length_m", 10)
        floors = params.get("floors", 1)
        material = params.get("material", "default").lower()
        roof_type = params.get("roof_type", "default").lower()
        foundation_type = params.get("foundation_type", "default").lower()
        has_landscape = params.get("has_landscape", True)
        has_engineering = params.get("has_engineering", True)
        lot_area = params.get("lot_area_m2", width * length * 3)

        footprint = width * length
        total_area = footprint * floors
        wall_perimeter = 2 * (width + length)
        wall_area = wall_perimeter * (params.get("height_m", 3.0)) * floors
        roof_area = footprint * 1.3  # с учётом свесов

        estimate = CostEstimate(area_m2=total_area)

        # ── Материалы ──
        mat = self.MATERIAL_COSTS.get(material, self.MATERIAL_COSTS["default"])
        estimate.add_item(
            CostLineItem(
                category="materials",
                item=f"Стены ({mat['name']})",
                unit="м²",
                quantity=wall_area,
                unit_price=mat["wall_m2"] * self._region_multiplier,
            )
        )
        estimate.add_item(
            CostLineItem(
                category="materials",
                item="Отделка фасада",
                unit="м²",
                quantity=wall_area,
                unit_price=mat["finish_m2"] * self._region_multiplier,
            )
        )

        roof_price = self.ROOF_COSTS.get(roof_type, self.ROOF_COSTS["default"])
        estimate.add_item(
            CostLineItem(
                category="materials",
                item=f"Крыша ({roof_type})",
                unit="м²",
                quantity=roof_area,
                unit_price=roof_price * self._region_multiplier,
            )
        )

        found_price = self.FOUNDATION_COSTS.get(foundation_type, self.FOUNDATION_COSTS["default"])
        estimate.add_item(
            CostLineItem(
                category="materials",
                item=f"Фундамент ({foundation_type})",
                unit="м²",
                quantity=footprint,
                unit_price=found_price * self._region_multiplier,
            )
        )

        # Перекрытия (если >1 этажа)
        if floors > 1:
            estimate.add_item(
                CostLineItem(
                    category="materials",
                    item="Перекрытия",
                    unit="м²",
                    quantity=footprint * (floors - 1),
                    unit_price=3500 * self._region_multiplier,
                )
            )

        # ── Работы ──
        labor_rate = self.LABOR_COSTS["default"] * self._region_multiplier
        estimate.add_item(
            CostLineItem(
                category="labor",
                item="Общестроительные работы",
                unit="м²",
                quantity=total_area,
                unit_price=labor_rate,
            )
        )

        # ── Инженерные системы ──
        if has_engineering:
            self.ENGINEERING_COSTS["total"]
            for system, price in self.ENGINEERING_COSTS.items():
                if system == "total":
                    continue
                estimate.add_item(
                    CostLineItem(
                        category="engineering",
                        item=system.replace("_", " ").title(),
                        unit="м²",
                        quantity=total_area,
                        unit_price=price * self._region_multiplier,
                    )
                )

        # ── Ландшафт ──
        if has_landscape:
            landscape_area = lot_area - footprint
            if landscape_area > 0:
                estimate.add_item(
                    CostLineItem(
                        category="landscape",
                        item="Благоустройство территории",
                        unit="м²",
                        quantity=landscape_area,
                        unit_price=self.LANDSCAPE_COSTS["total_per_m2"] * self._region_multiplier,
                    )
                )

        return estimate

    def calculate_interior(self, params: dict) -> CostEstimate:
        """Стоимость отделки интерьера."""
        width = params.get("width_m", 6)
        length = params.get("length_m", 8)
        height = params.get("height_m", 3.0)
        style = params.get("style", "modern").lower()

        area = width * length
        wall_area = 2 * (width + length) * height
        estimate = CostEstimate(area_m2=area)

        # Стиль → цена
        style_multipliers = {
            "minimalist": 1.0,
            "минимализм": 1.0,
            "modern": 1.2,
            "современный": 1.2,
            "classic": 1.5,
            "классический": 1.5,
            "loft": 1.1,
            "лофт": 1.1,
            "scandinavian": 1.1,
            "скандинавский": 1.1,
            "luxury": 2.5,
            "люкс": 2.5,
            "премиум": 2.5,
        }
        mult = style_multipliers.get(style, 1.2)

        # Пол
        estimate.add_item(
            CostLineItem(
                category="materials",
                item="Напольное покрытие",
                unit="м²",
                quantity=area,
                unit_price=2500 * mult * self._region_multiplier,
            )
        )
        # Стены
        estimate.add_item(
            CostLineItem(
                category="materials",
                item="Отделка стен",
                unit="м²",
                quantity=wall_area,
                unit_price=1200 * mult * self._region_multiplier,
            )
        )
        # Потолок
        estimate.add_item(
            CostLineItem(
                category="materials",
                item="Потолок",
                unit="м²",
                quantity=area,
                unit_price=1800 * mult * self._region_multiplier,
            )
        )
        # Работы
        estimate.add_item(
            CostLineItem(
                category="labor",
                item="Отделочные работы",
                unit="м²",
                quantity=area,
                unit_price=3000 * mult * self._region_multiplier,
            )
        )

        return estimate

    # ═══ Расширенная база региональных коэффициентов ═══
    REGION_MULTIPLIERS = {
        # Россия — базовые
        "moscow": 1.0, "москва": 1.0,
        "spb": 0.85, "петербург": 0.85, "санкт-петербург": 0.85,
        "russia": 0.7, "россия": 0.7,
        # Россия — север и удалённые регионы
        "мурманская": 1.35, "murmansk": 1.35,
        "якутия": 1.5, "yakutia": 1.5,
        "камчатка": 1.6, "kamchatka": 1.6,
        "чукотка": 1.8, "chukotka": 1.8,
        "арктика": 1.5, "arctic": 1.5,
        # Россия — юг
        "краснодар": 0.8, "krasnodar": 0.8,
        "крым": 0.75, "crimea": 0.75,
        "сочи": 0.9, "sochi": 0.9,
        # Международные
        "europe": 1.3, "европа": 1.3,
        "usa": 1.5, "сша": 1.5,
        "бали": 0.75, "bali": 0.75, "индонезия": 0.75, "indonesia": 0.75,
        "турция": 0.65, "turkey": 0.65,
        "грузия": 0.55, "georgia": 0.55,
        "норвегия": 1.8, "norway": 1.8,
        "финляндия": 1.4, "finland": 1.4,
    }

    # Дополнительные коэффициенты удорожания
    SEASONAL_MULTIPLIERS = {
        "winter_construction": 1.15,  # Зимнее строительство
        "remote_logistics": 1.25,     # Доставка в удалённые районы
        "northern_allowance": 1.30,   # Северные надбавки к зарплатам
    }

    def _get_region_multiplier(self, region: str) -> float:
        """Коэффициент региона (Москва = 1.0)."""
        return self.REGION_MULTIPLIERS.get(region.lower(), 1.0)

    def _get_total_multiplier(self, region: str, params: dict = None) -> float:
        """Итоговый коэффициент с учётом региона и сезонных факторов."""
        base = self._get_region_multiplier(region)
        if params:
            if params.get("winter_construction", False):
                base *= self.SEASONAL_MULTIPLIERS["winter_construction"]
            if params.get("remote_logistics", False):
                base *= self.SEASONAL_MULTIPLIERS["remote_logistics"]
            if params.get("northern_allowance", False):
                base *= self.SEASONAL_MULTIPLIERS["northern_allowance"]
        return base

    def validate_estimate(self, estimate: CostEstimate, params: dict = None) -> dict:
        """Валидация сметы: benchmark comparison + sanity checks."""
        warnings = []
        if estimate.area_m2 > 0:
            cost_m2 = estimate.cost_per_m2
            # Типичные диапазоны (руб/м², 2026)
            if cost_m2 < 30000:
                warnings.append(f"⚠️ Стоимость {cost_m2:,.0f} ₽/м² ниже типичного минимума (30 000 ₽/м²)")
            elif cost_m2 > 300000:
                warnings.append(f"⚠️ Стоимость {cost_m2:,.0f} ₽/м² выше типичного максимума (300 000 ₽/м²)")
        return {
            "valid": len(warnings) == 0,
            "warnings": warnings,
            "cost_per_m2": round(estimate.cost_per_m2),
        }

    # ═══ Господдержка ═══
    GOV_SUPPORT_PROGRAMS = {
        "frt": {
            "name": "ФРТ (Фонд развития территорий)",
            "subsidy_pct": 80,
            "description": "Субсидия до 80% на инженерную инфраструктуру",
            "max_amount_rub": 500_000_000,
        },
        "kdi": {
            "name": "КДИ (Корпорация развития Дальнего Востока)",
            "interest_rate_pct": 2,
            "description": "Льготный кредит от 2% для инвестиционных проектов",
        },
        "tor_barents": {
            "name": "ТОР «Баренцев регион»",
            "tax_benefits": ["НДС", "Налог на прибыль", "Налог на имущество"],
            "description": "Налоговые льготы для резидентов ТОР",
        },
        "arctic_zone": {
            "name": "Арктическая зона РФ",
            "tax_benefits": ["Налог на прибыль 0% на 5 лет", "Ускоренная амортизация"],
            "description": "Льготные условия для инвестиций в Арктике",
        },
    }

    def calculate_gov_support_impact(self, capex: float, program: str) -> dict:
        """Расчёт влияния господдержки на CAPEX."""
        prog = self.GOV_SUPPORT_PROGRAMS.get(program)
        if not prog:
            return {"error": f"Программа {program} не найдена"}

        subsidy_pct = prog.get("subsidy_pct", 0)
        subsidy = min(capex * subsidy_pct / 100, prog.get("max_amount_rub", float("inf")))

        return {
            "program": prog["name"],
            "original_capex": round(capex),
            "subsidy": round(subsidy),
            "reduced_capex": round(capex - subsidy),
            "savings_pct": subsidy_pct,
            "description": prog["description"],
        }
