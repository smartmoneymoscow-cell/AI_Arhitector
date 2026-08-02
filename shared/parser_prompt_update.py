"""
shared/parser_prompt_update.py — Обновление SYSTEM_PROMPT в shared/parser.py

Этот файл содержит ДОПОЛНИТЕЛЬНЫЙ БЛОК для вставки в SYSTEM_PROMPT.
Заменить существующий JSON-формат в parser.py на расширенный.
"""

# ═══════════════════════════════════════════════════════════════
# РАСШИРЕННЫЙ JSON-ФОРМАТ ДЛЯ SYSTEM_PROMPT
# ═══════════════════════════════════════════════════════════════

EXTENDED_JSON_SCHEMA = """
═══ РАСШИРЕННЫЙ ФОРМАТ JSON (v2.0) ═══
{
  "object_type": "building|interior|landscape|structure",
  "building_type": "ЛЮБОЕ строковое значение",
  "building_description": "подробное описание что именно делаем",
  "room_type": "тип комнаты если интерьер, иначе null",
  "floors": число (1-50),
  "width_m": ширина в метрах (реалистичная),
  "length_m": длина в метрах,
  "height_m": высота в метрах,
  "style": "ЛЮБОЕ значение стиля",
  "material": "ЛЮБОЕ значение материала",
  "roof_type": "ЛЮБОЕ значение типа крыши",
  "features": ["ЛЮБЫЕ особенности"],
  "furniture": ["ЛЮБАЯ мебель для интерьера"],
  "special_requirements": ["ЛЮБЫЕ особые требования"],
  "confidence": 0.0-1.0,
  "reasoning": "кратко почему решил именно так",

  "structural_system": "frame|shear_wall|tube|braced|hybrid",
  "foundation_type": "strip|slab|pile|raft|combined",
  "material_concrete_class": "B15|B20|B25|B30|B35|B40|B45|B50|B60",
  "steel_grade": "C235|C245|C255|C345|C375|C390|C440",
  "seismic_zone": "none|5|6|7|8|9",
  "soil_type": "I|II|III|IV|V",
  "fire_resistance_rating": "R15|R30|R45|R60|R90|R120|R150|R180",
  "heating_type": "central|autonomous|individual|none",
  "ventilation_type": "natural|mechanical|mixed",
  "water_supply": "central|well|none",
  "sewage": "central|septic|none",
  "exposure_class": "XC1|XC2|XC3|XC4|XD1|XD2|XS1|XS2|XS3"
}
"""

EXTENDED_RULES = """
═══ ДОПОЛНИТЕЛЬНЫЕ ПРАВИЛА ДЛЯ КОНСТРУКТИВНЫХ ПАРАМЕТРОВ ═══

1. structural_system — конструктивная система:
   - "frame" = каркасная (стойки + ригели), до 5 этажей
   - "shear_wall" = из стержневых стен, 5-16 этажей
   - "tube" = трубчатая, >16 этажей
   - "braced" = с диагональными связями
   - "hybrid" = комбинированная

2. foundation_type — тип фундамента:
   - "strip" = ленточный (для домов 1-3 этажа на нормальных грунтах)
   - "slab" = плитный (для слабых грунтов, пучинистых)
   - "pile" = свайный (для слабых грунтов, >3 этажей)
   - "raft" = сплошной (плитный для больших зданий)
   - "combined" = комбинированный

3. material_concrete_class — класс бетона (по СП 63.13330):
   - B15 = для фундаментов, подбетонки
   - B20-B25 = для малоэтажного строительства
   - B30-B35 = для многоэтажного
   - B40-B50 = для высотного и ответственного

4. steel_grade — класс стали (по СП 16.13330):
   - C235 = для второстепенных конструкций
   - C345 = основной конструкционный класс
   - C390-C440 = для высокопрочных конструкций

5. seismic_zone — сейсмическая зона (по СП 14.13330):
   - "none" = не сейсмический район
   - "5"-"9" = балльность по карте

6. soil_type — категория грунта (по СП 22.13330):
   - "I" = скальные (самые прочные)
   - "II" = крупные пески, гравий
   - "III" = мелкие пески, супеси
   - "IV" = суглинки и глины твёрдые
   - "V" = мягкопластичные глины (самые слабые)

7. fire_resistance_rating — предел огнестойкости (по СП 2.13130):
   - R15-R45 = для малоэтажных жилых
   - R60 = для многоэтажных жилых и общественных
   - R90-R120 = для высотных и ответственных

8. exposure_class — класс условий эксплуатации (по СП 63):
   - XC1 = сухие помещения
   - XC2 = влажные (кухни, ванные)
   - XC3 = наружный воздух
   - XC4 = агрессивная среда

Если пользователь не указал конструктивные параметры — ставь наиболее вероятные:
- Для дома 1-2 этажа: structural_system="frame", foundation_type="strip", soil_type="III"
- Для дома 3-5 этажей: structural_system="frame", foundation_type="slab", soil_type="III"
- Для офиса >5 этажей: structural_system="shear_wall", foundation_type="pile", soil_type="II"
"""


def get_system_prompt_addition() -> str:
    """
    Возвращает расширение для SYSTEM_PROMPT.

    Встраивается в parser.py после строки:
    "features": ["ЛЮБЫЕ особенности"],
    """
    return EXTENDED_JSON_SCHEMA + "\n" + EXTENDED_RULES
