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
class ClarificationQuestion:
    """Один уточняющий вопрос."""
    field: str  # Какое поле уточняем
    text: str   # Текст вопроса
    options: list[str] = field(default_factory=list)  # Варианты ответа
    priority: int = 1  #1=обязательно,2=желательно,3=опционально


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
    REQUIRED_FIELDS = {
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
    OPTIONAL_FIELDS = {
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
                        questions.append(ClarificationQuestion(
                            field=field_name,
                            text=config["question"],
                            options=config["options"],
                            priority=1,
                        ))

        # При низкой уверенности — больше вопросов
        if confidence < self.MIN_CONFIDENCE:
            for field_name, config in self.REQUIRED_FIELDS.items():
                if not parsed_params.get(field_name):
                    questions.append(ClarificationQuestion(
                        field=field_name,
                        text=config["question"],
                        options=config["options"],
                        priority=1,
                    ))

            for field_name, config in self.OPTIONAL_FIELDS.items():
                if not self._field_mentioned(field_name, prompt):
                    questions.append(ClarificationQuestion(
                        field=field_name,
                        text=config["question"],
                        options=config.get("options", []),
                        priority=2,
                    ))

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
                    "house"
                )
                result["building_type"] = result["object_type"]

            elif field_name == "building_type":
                result["building_type"] = self._match_answer(
                    answer_lower,
                    {"дом": "house", "офис": "office", "коттедж": "cottage", "вилл": "villa"},
                    "house"
                )

            elif field_name == "floors":
                import re
                m = re.search(r'\d+', answer)
                if m:
                    result["floors"] = int(m.group())

            elif field_name == "material":
                result["material"] = self._match_answer(
                    answer_lower,
                    {"кирпич": "brick", "дерев": "wood", "камен": "stone", "штукатурк": "plaster", "стекл": "glass", "бетон": "concrete"},
                    "plaster"
                )

            elif field_name == "roof_type":
                result["roof_type"] = self._match_answer(
                    answer_lower,
                    {"двускат": "gabled", "плоск": "flat", "вальм": "hip"},
                    "gabled"
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
