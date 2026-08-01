"""
shared/interface_engine.py — Движок определения границ ответственности.

Генерирует Interface Definition — документ, определяющий границы
между исполнителями в многосторонних проектах.

Использование:
    from shared.interface_engine import InterfaceEngine

    engine = InterfaceEngine()
    doc = engine.generate(params)
"""

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InterfaceItem:
    """Один элемент границы."""

    name: str
    description: str
    owner: str  # "us" / "them" / "shared"
    deliverable: str = ""  # Что передаём/получаем


@dataclass
class InterfaceDefinition:
    """Документ границ ответственности."""

    project_name: str = ""
    boundary: str = ""  # Описание границы
    our_scope: list[InterfaceItem] = field(default_factory=list)
    their_scope: list[InterfaceItem] = field(default_factory=list)
    handover_to_them: list[str] = field(default_factory=list)
    required_from_them: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "boundary": self.boundary,
            "our_scope": [
                {"name": i.name, "description": i.description, "owner": i.owner}
                for i in self.our_scope
            ],
            "their_scope": [
                {"name": i.name, "description": i.description, "owner": i.owner}
                for i in self.their_scope
            ],
            "handover_to_them": self.handover_to_them,
            "required_from_them": self.required_from_them,
        }

    @property
    def summary(self) -> str:
        parts = [
            f"📋 {self.project_name}",
            f"Граница: {self.boundary}",
            f"Наша зона: {len(self.our_scope)} элементов",
            f"Их зона: {len(self.their_scope)} элементов",
            f"Передаём им: {len(self.handover_to_them)} позиций",
            f"Получаем от них: {len(self.required_from_them)} позиций",
        ]
        return "\n".join(parts)


class InterfaceEngine:
    """Движок генерации Interface Definition."""

    # Шаблоны для типовых проектов
    TEMPLATES = {
        "villa_foundation_split": {
            "boundary": "Обрез фундамента (верхняя отметка фундаментной конструкции)",
            "our_scope": [
                InterfaceItem("Надфундаментная часть", "Стены, перекрытия, кровля, инженерные системы", "us"),
                InterfaceItem("Архитектурные решения", "Фасады, интерьеры, отделка", "us"),
            ],
            "their_scope": [
                InterfaceItem("Фундамент", "Фундаментные конструкции", "them"),
                InterfaceItem("Подпорные стены", "Подпорные стены участка", "them"),
                InterfaceItem("Посадка на участок", "Генплан, привязка", "them"),
            ],
            "handover_to_them": [
                "Нагрузки на фундамент (вес, эксплуатационные, ветровые, сейсмические)",
                "Анкерные связи (тип, диаметр, шаг)",
                "Точки ввода инженерных коммуникаций",
                "Отметки конструкций (низы, верхы)",
            ],
            "required_from_them": [
                "Геология (тип грунта, УГВ)",
                "Сейсмический район (карта SNI / СП)",
                "План участка с привязкой и ориентацией",
                "Отметка чистого пола 1-го этажа (±0.000)",
                "Точки подключения к сетям (вода, канализация, электричество)",
            ],
        },
        "apartment_mep": {
            "boundary": "Ввод инженерных коммуникаций в квартиру",
            "our_scope": [
                InterfaceItem("Внутренние системы", "Электрика, водоснабжение, канализация, отопление, вентиляция", "us"),
                InterfaceItem("Отделка", "Все отделочные работы", "us"),
            ],
            "their_scope": [
                InterfaceItem("Общедомовые системы", "Стояки, магистрали, щитовые", "them"),
                InterfaceItem("Ограждающие конструкции", "Несущие стены, перекрытия, фасад", "them"),
            ],
            "handover_to_them": [
                "Заявка на мощность (электрика)",
                "Заявка на подключение (вода, канализация)",
                "Согласование перепланировки",
            ],
            "required_from_them": [
                "План БТИ (поэтажный)",
                "Точка ввода электричества (этажный щит)",
                "Точки ввода ХВС/ГВС/канализации",
                "Параметры отопления (давление, температура)",
            ],
        },
    }

    def generate(self, params: dict) -> InterfaceDefinition:
        """Генерация Interface Definition."""
        template_name = params.get("template")
        project_name = params.get("project_name", "Проект")

        if template_name and template_name in self.TEMPLATES:
            tmpl = self.TEMPLATES[template_name]
            return InterfaceDefinition(
                project_name=project_name,
                boundary=tmpl["boundary"],
                our_scope=tmpl["our_scope"],
                their_scope=tmpl["their_scope"],
                handover_to_them=tmpl["handover_to_them"],
                required_from_them=tmpl["required_from_them"],
            )

        # Свободная форма
        return InterfaceDefinition(
            project_name=project_name,
            boundary=params.get("boundary", "Не определена"),
            our_scope=[
                InterfaceItem(name=i["name"], description=i["description"], owner="us")
                for i in params.get("our_scope", [])
            ],
            their_scope=[
                InterfaceItem(name=i["name"], description=i["description"], owner="them")
                for i in params.get("their_scope", [])
            ],
            handover_to_them=params.get("handover_to_them", []),
            required_from_them=params.get("required_from_them", []),
        )

    def list_templates(self) -> list[str]:
        """Список доступных шаблонов."""
        return list(self.TEMPLATES.keys())
