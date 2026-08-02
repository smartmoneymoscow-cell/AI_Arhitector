"""
shared/clarification.py — Система уточняющих вопросов (multi-turn clarification).

Когда парсинг не может определить критические параметры,
система задаёт пользователю уточняющие вопросы.

Использование:
    from shared.clarification import ClarificationEngine

    engine = ClarificationEngine()
    result = engine.analyze("построй дом")
    if result.needs_clarification:
        for q in result.questions:
            print(q.text)
"""

from dataclasses import dataclass, field


@dataclass
class ClarificationOption:
    """Вариант ответа с визуалом и trade-off."""

    id: str  # "A", "B", "C"
    title: str  # Название варианта
    description: str  # Описание
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    image_url: str = ""  # URL фото/схемы
    recommended: bool = False
    price_range: str = ""


@dataclass
class ClarificationQuestion:
    """Один уточняющий вопрос."""

    field_name: str
    text: str
    options: list[str] = field(default_factory=list)
    visual_options: list[ClarificationOption] = field(default_factory=list)
    priority: int = 1
    is_fork: bool = False  # Развилка (несколько равноценных путей)?


@dataclass
class ClarificationResult:
    """Результат анализа на необходимость уточнений."""

    needs_clarification: bool = False
    questions: list[ClarificationQuestion] = field(default_factory=list)
    confidence: float = 1.0
    partial_params: dict = field(default_factory=dict)


class ClarificationEngine:
    """
    Анализирует распарсенные параметры и определяет,
    нужны ли уточняющие вопросы пользователю.
    """

    # Минимальная уверенность для запуска генерации без вопросов
    MIN_CONFIDENCE = 0.6

    # Поля, которые обязательно должны быть определены
    REQUIRED_FIELDS: dict[str, dict] = {
        "object_type": {
            "question": "Что вы хотите построить?",
            "options": ["🏠 Дом", "🏢 Офис", "🌲 Коттедж", "🏘 Таунхаус"],
            "values": ["house", "office", "cottage", "townhouse"],
        },
        "building_type": {
            "question": "Какой тип здания?",
            "options": ["Жилой дом", "Офис", "Коттедж", "Вилла"],
            "values": ["house", "office", "cottage", "villa"],
        },
    }

    # Поля, которые желательно уточнить
    OPTIONAL_FIELDS: dict[str, dict] = {
        "floors": {
            "question": "Сколько этажей?",
            "options": ["1", "2", "3", "5+"],
        },
        "material": {
            "question": "Из какого материала фасад?",
            "options": ["🧱 Кирпич", "🪵 Дерево", "🪨 Камень", "🧴 Штукатурка", "🪟 Стекло"],
        },
        "roof_type": {
            "question": "Какая кровля?",
            "options": ["Двускатная", "Плоская", "Вальмовая"],
        },
    }

    def analyze(self, prompt: str, parsed_params: dict, confidence: float = 0.5) -> ClarificationResult:
        """
        Анализирует параметры и решает, нужны ли уточнения.

        Args:
            prompt: оригинальный промт
            parsed_params: распарсенные параметры
            confidence: уверенность парсера (0.0-1.0)

        Returns:
            ClarificationResult с вопросами (если нужны)
        """
        questions = []

        # Проверяем confidence
        if confidence >= self.MIN_CONFIDENCE:
            # Даже при высокой уверенности проверяем критические поля
            for field_name, config in self.REQUIRED_FIELDS.items():
                val = parsed_params.get(field_name)
                if not val or val == "house":  # house = дефолт, возможно не определено
                    # Проверяем, было ли что-то в промте
                    if not self._field_mentioned(field_name, prompt):
                        questions.append(
                            ClarificationQuestion(
                                field_name=field_name,
                                text=config["question"],
                                options=config["options"],
                                priority=1,
                            )
                        )

        # При низкой уверенности — больше вопросов
        if confidence < self.MIN_CONFIDENCE:
            for field_name, config in self.REQUIRED_FIELDS.items():
                if not parsed_params.get(field_name):
                    questions.append(
                        ClarificationQuestion(
                            field_name=field_name,
                            text=config["question"],
                            options=config["options"],
                            priority=1,
                        )
                    )

            for field_name, config in self.OPTIONAL_FIELDS.items():
                if not self._field_mentioned(field_name, prompt):
                    questions.append(
                        ClarificationQuestion(
                            field_name=field_name,
                            text=config["question"],
                            options=config.get("options", []),
                            priority=2,
                        )
                    )

        # Сортируем по приоритету
        questions.sort(key=lambda q: q.priority)

        # Ограничиваем до3 вопросов (не перегружать пользователя)
        questions = questions[:3]

        return ClarificationResult(
            needs_clarification=len(questions) > 0,
            questions=questions,
            confidence=confidence,
            partial_params=parsed_params,
        )

    def apply_answers(self, params: dict, answers: dict[str, str]) -> dict:
        """
        Применяет ответы пользователя к параметрам.

        Args:
            params: текущие параметры
            answers: {field: answer_text}

        Returns:
            обновлённые параметры
        """
        result = dict(params)

        for field_name, answer in answers.items():
            answer_lower = answer.lower().strip()

            if field_name == "object_type":
                result["object_type"] = self._match_answer(
                    answer_lower,
                    {"дом": "house", "офис": "office", "коттедж": "cottage", "таунхаус": "townhouse", "вилл": "villa"},
                    "house",
                )
                result["building_type"] = result["object_type"]

            elif field_name == "building_type":
                result["building_type"] = self._match_answer(
                    answer_lower, {"дом": "house", "офис": "office", "коттедж": "cottage", "вилл": "villa"}, "house"
                )

            elif field_name == "floors":
                import re

                m = re.search(r"\d+", answer)
                if m:
                    result["floors"] = int(m.group())

            elif field_name == "material":
                result["material"] = self._match_answer(
                    answer_lower,
                    {
                        "кирпич": "brick",
                        "дерев": "wood",
                        "камен": "stone",
                        "штукатурк": "plaster",
                        "стекл": "glass",
                        "бетон": "concrete",
                    },
                    "plaster",
                )

            elif field_name == "roof_type":
                result["roof_type"] = self._match_answer(
                    answer_lower, {"двускат": "gabled", "плоск": "flat", "вальм": "hip"}, "gabled"
                )

        return result

    def _field_mentioned(self, field_name: str, prompt: str) -> bool:
        """Проверяет, упоминалось ли поле в промте."""
        t = prompt.lower()
        mentions = {
            "object_type": ["дом", "здани", "офис", "коттедж", "вилл", "таунхаус", "квартир"],
            "building_type": ["дом", "офис", "коттедж", "вилл", "таунхаус"],
            "floors": ["этаж", "уровн", "одно", "двух", "трёх", "четыр", "пяти"],
            "material": ["кирпич", "дерев", "стекл", "камен", "бетон", "штукатурк"],
            "roof_type": ["плоск", "двускат", "вальм", "скатн", "кровл"],
        }
        keywords = mentions.get(field_name, [])
        return any(kw in t for kw in keywords)

    def _match_answer(self, answer: str, mapping: dict, default: str) -> str:
        """Сопоставляет текст ответа с вариантом."""
        for keyword, value in mapping.items():
            if keyword in answer:
                return value
        return default

    # ═══ Расширение: визуальные варианты при развилках ═══

    def generate_visual_options(self, field_name: str, context: dict = None) -> list[ClarificationOption]:
        """Генерация визуальных вариантов при развилках.

        Принцип: варианты показываются ТОЛЬКО когда есть развилка
        (2+ равноценных пути реализации). Не декоративно, а функционально.
        """
        ctx = context or {}

        generators = {
            "material": self._options_material,
            "roof_type": self._options_roof,
            "foundation_type": self._options_foundation,
            "lstk_profile": self._options_lstk,
            "smart_home_system": self._options_smart_home,
            "stove_type": self._options_stove,
            "heating_type": self._options_heating,
            "ventilation_type": self._options_ventilation,
            "window_type": self._options_window,
            "style": self._options_style,
            "landscape_style": self._options_landscape,
        }
        gen = generators.get(field_name)
        if gen:
            return gen(ctx)
        return []

    def _options_material(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Кирпич",
                description="Классический материал",
                pros=["Прочность", "Долговечность", "Экологичность"],
                cons=["Дорого", "Долго строить", "Тяжёлый"],
                price_range="4500 ₽/м²",
            ),
            ClarificationOption(
                id="B",
                title="Газобетон",
                description="Лёгкие блоки",
                pros=["Тепло", "Лёгкий", "Быстрый монтаж"],
                cons=["Впитывает влагу", "Требует отделки"],
                price_range="2800 ₽/м²",
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Дерево (брус)",
                description="Экологичный",
                pros=["Экология", "Тепло", "Красиво"],
                cons=["Усадка", "Пожароопасность", "Биозащита"],
                price_range="3800 ₽/м²",
            ),
        ]

    def _options_roof(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Двускатная",
                description="Классическая",
                pros=["Простой узел", "Хороший отвод воды"],
                cons=["Нет террасы на крыше"],
                price_range="5000 ₽/м²",
            ),
            ClarificationOption(
                id="B",
                title="Плоская",
                description="Современная",
                pros=["Терраса", "Современный вид"],
                cons=["Дренаж критичен", "Конденсат"],
                price_range="3500 ₽/м²",
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Вальмовая",
                description="Престижная",
                pros=["Красивая", "Устойчивость к ветру"],
                cons=["Дорого", "Сложные узлы"],
                price_range="6500 ₽/м²",
            ),
        ]

    def _options_foundation(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Ленточный",
                description="Монолитная лента",
                pros=["Надёжно", "Для любых грунтов"],
                cons=["Дорого", "Долго"],
                price_range="4000 ₽/м²",
            ),
            ClarificationOption(
                id="B",
                title="Плитный",
                description="Монолитная плита",
                pros=["Просто", "Для слабых грунтов"],
                cons=["Плоскость пола фиксирована"],
                price_range="5500 ₽/м²",
            ),
            ClarificationOption(
                id="C",
                title="Свайный",
                description="Буронабивные сваи",
                pros=["Быстро", "Для сложных грунтов"],
                cons=["Нужен ростверк"],
                price_range="7000 ₽/м²",
            ),
        ]

    def _options_lstk(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Стоечно-балочный",
                description="Профили C+U",
                pros=["Гибкость планировок", "Легко прокладывать коммуникации"],
                cons=["Много мокрых процессов"],
                recommended=True,
            ),
            ClarificationOption(
                id="B",
                title="Ферменный",
                description="Фермы из ЛСТК",
                pros=["Большие пролёты", "Прочность"],
                cons=["Сложные узлы"],
            ),
            ClarificationOption(
                id="C",
                title="Панельный (СИП)",
                description="Готовые панели",
                pros=["Быстрый монтаж", "Предсказуемая стоимость"],
                cons=["Типовые решения"],
            ),
        ]

    def _options_smart_home(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="KNX",
                description="Профессиональный проводной",
                pros=["Надёжность", "Полная интеграция"],
                cons=["Дорого (35000 ₽/точка)", "Много кабеля"],
                price_range="35000 ₽/точка",
            ),
            ClarificationOption(
                id="B",
                title="Loxone",
                description="Компактный проводной",
                pros=["Красивый UI", "Средняя цена"],
                cons=["Мало интеграций"],
                price_range="20000 ₽/точка",
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Zigbee",
                description="Беспроводной",
                pros=["Дёшево", "Не нужно штробить"],
                cons=["Нестабильно", "Ограниченный функционал"],
                price_range="8000 ₽/точка",
            ),
        ]

    def _options_stove(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Кирпичная",
                description="Шамотный кирпич",
                pros=["Долго держит тепло", "Мягкий пар"],
                cons=["Дорого", "Тяжёлая (нужен фундамент)", "Долго топить"],
            ),
            ClarificationOption(
                id="B",
                title="Металлическая с обкладкой",
                description="Заводская + кирпич",
                pros=["Быстро прогревается", "Компактная", "Эстетика"],
                cons=["Дороже обычной"],
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Металлическая",
                description="Эконом-вариант",
                pros=["Дёшево", "Легко"],
                cons=["Быстро остывает", "Жёсткий пар"],
                price_range="от 15000 ₽",
            ),
        ]

    def _options_heating(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Центральное (ЦТП/ИТП)",
                description="От теплосети",
                pros=["Надёжно", "Не нужно обслуживать"],
                cons=["Тарифы"],
            ),
            ClarificationOption(
                id="B",
                title="Автономная котельная",
                description="Газ/дизель/электро",
                pros=["Независимость"],
                cons=["Нужно обслуживать"],
            ),
            ClarificationOption(
                id="C",
                title="Поквартирное",
                description="Газ/электро котёл",
                pros=["Индивидуальный учёт"],
                cons=["Дорого", "Дымоходы"],
                recommended=True,
            ),
        ]

    def _options_ventilation(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Естественная",
                description="Приточные клапаны + вытяжка",
                pros=["Дёшево", "Не потребляет электричество"],
                cons=["Зависит от погоды", "Нет фильтрации"],
            ),
            ClarificationOption(
                id="B",
                title="Приточно-вытяжная с рекуперацией",
                description="Бризер/установка",
                pros=["Комфорт", "Экономия тепла", "Фильтрация"],
                cons=["Дорого", "Нужно место"],
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Сплит + приточные клапаны",
                description="Кондиционер + клапаны",
                pros=["Кондиционирование + вентиляция"],
                cons=["Нет рекуперации"],
            ),
        ]

    def _options_window(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Панорамное (от пола)",
                description="Полное остекление",
                pros=["Максимум света", "Эффект «на природе»"],
                cons=["Дорого", "Конденсат", "Летом жарко"],
            ),
            ClarificationOption(
                id="B",
                title="Французское",
                description="От пола до подоконника",
                pros=["Дешевле панорамного", "Приватность сверху"],
                cons=["Стандарт"],
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Раздвижные панели",
                description="Стеклянные панели",
                pros=["Открываются полностью", "Летом = терраса"],
                cons=["Механизм может ломаться"],
            ),
        ]

    def _options_style(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Минимализм",
                description="Чистые линии",
                pros=["Низкий уход", "Современно"],
                cons=["Может быть холодно"],
            ),
            ClarificationOption(
                id="B",
                title="Современный",
                description="Смешение стилей",
                pros=["Уют", "Гибкость"],
                cons=["Нужен дизайнер"],
            ),
            ClarificationOption(
                id="C",
                title="Tropical Modern",
                description="Природа + минимализм",
                pros=["Уникальность", "Связь с природой"],
                cons=["Специфические материалы"],
                recommended=True,
            ),
        ]

    def _options_landscape(self, ctx: dict) -> list[ClarificationOption]:
        return [
            ClarificationOption(
                id="A",
                title="Регулярный",
                description="Геометрия, симметрия",
                pros=["Строго", "Представительно"],
                cons=["Дорогой уход"],
            ),
            ClarificationOption(
                id="B",
                title="Пейзажный",
                description="Естественность",
                pros=["Неприхотливость", "Красиво"],
                cons=["Нужен ландшафтник"],
                recommended=True,
            ),
            ClarificationOption(
                id="C",
                title="Японский сад",
                description="Камень, вода, мох",
                pros=["Уют", "Медитативность"],
                cons=["Мало газона", "Уход"],
            ),
        ]
