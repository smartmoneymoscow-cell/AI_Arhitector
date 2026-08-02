"""
shared/structural_analysis.py — Полный модуль расчёта строительных конструкций

Включает:
  - Метод конечных элементов (МКЭ/FEM) — балки, пластины, оболочки
  - Проверка стальных конструкций по СП 16.13330.2017
  - Проверка ЖБ конструкций по СП 63.13330.2018
  - Комбинации нагрузок по СП 20.13330.2016
  - Динамический/сейсмический анализ по СП 14.13330.2018
  - Расчёт оснований по СП 22.13330.2016
  - Расчёт свай по СП 24.13330.2011
  - Проверка устойчивости (эuler, P-Δ)
  - База сечений (ГОСТ 8239, ГОСТ 26020)

Зависимости: numpy
"""

import logging
import math

logger = logging.getLogger("archai.structural")

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("numpy not available — FEM solver disabled")


# ═══════════════════════════════════════════════════════════════
# КОНСТАНТЫ И КОЭФФИЦИЕНТЫ (СП 20.13330)
# ═══════════════════════════════════════════════════════════════

# Коэффициенты надёжности по нагрузке γ_f (СП 20 табл. 7.1)
GAMMA_F = {
    "dead_favorable": 0.9,  # Постоянные, благоприятные
    "dead_unfavorable": 1.1,  # Постоянные, неблагоприятные
    "live_favorable": 0.0,  # Временные длительные, благоприятные
    "live_unfavorable": 1.3,  # Временные кратковременные, неблагоприятные
    "live_short": 1.3,  # Кратковременные
    "snow": 1.4,  # Снеговые
    "wind": 1.4,  # Ветровые
    "seismic": 1.0,  # Сейсмические (без γ_f)
}

# Коэффициенты сочетаний ψ (СП 20 табл. 8.1)
PSI_0 = {"live": 0.7, "snow": 0.7, "wind": 0.3, "temperature": 0.6}
PSI_1 = {"live": 0.9, "snow": 0.9, "wind": 0.7, "temperature": 0.8}

# Классы бетона (СП 63 табл. 6.1) — B → f_b (МПа), f_bt, E_b
CONCRETE_CLASSES = {
    "B7.5": {"f_b": 5.5, "f_bt": 0.57, "E_b": 16000, "class": "B7.5"},
    "B15": {"f_b": 11.0, "f_bt": 0.90, "E_b": 24000, "class": "B15"},
    "B20": {"f_b": 15.0, "f_bt": 1.10, "E_b": 27500, "class": "B20"},
    "B25": {"f_b": 18.5, "f_bt": 1.30, "E_b": 30000, "class": "B25"},
    "B30": {"f_b": 22.0, "f_bt": 1.50, "E_b": 32500, "class": "B30"},
    "B35": {"f_b": 25.5, "f_bt": 1.65, "E_b": 34500, "class": "B35"},
    "B40": {"f_b": 29.0, "f_bt": 1.85, "E_b": 36000, "class": "B40"},
    "B45": {"f_b": 32.0, "f_bt": 1.95, "E_b": 37000, "class": "B45"},
    "B50": {"f_b": 36.0, "f_bt": 2.10, "E_b": 38000, "class": "B50"},
    "B60": {"f_b": 44.0, "f_bt": 2.50, "E_b": 39500, "class": "B60"},
}

# Классы арматуры (СП 63 табл. 6.5)
REBAR_CLASSES = {
    "A240": {"f_y": 240, "f_yk": 240, "E_s": 200000, "ductility": "hot-rolled"},
    "A400": {"f_y": 360, "f_yk": 400, "E_s": 200000, "ductility": "hot-rolled"},
    "A500": {"f_y": 435, "f_yk": 500, "E_s": 200000, "ductility": "thermomechanical"},
    "A600": {"f_y": 520, "f_yk": 600, "E_s": 200000, "ductility": "thermomechanical"},
    "B500": {"f_y": 435, "f_yk": 500, "E_s": 200000, "ductility": "cold-drawn"},
}

# Классы стали (СП 16 табл. 5.1)
STEEL_GRADES = {
    "C235": {"f_y": 235, "f_u": 360, "E": 206000, "nu": 0.3, "G": 79000},
    "C245": {"f_y": 245, "f_u": 370, "E": 206000, "nu": 0.3, "G": 79000},
    "C255": {"f_y": 255, "f_u": 380, "E": 206000, "nu": 0.3, "G": 79000},
    "C345": {"f_y": 345, "f_u": 470, "E": 206000, "nu": 0.3, "G": 79000},
    "C375": {"f_y": 375, "f_u": 490, "E": 206000, "nu": 0.3, "G": 79000},
    "C390": {"f_y": 390, "f_u": 510, "E": 206000, "nu": 0.3, "G": 79000},
    "C440": {"f_y": 440, "f_u": 550, "E": 206000, "nu": 0.3, "G": 79000},
}

# Предел огнестойкости строительных конструкций (СП 2.13130 табл. 21)
FIRE_RESISTANCE = {
    "R15": {"minutes": 15, "description": "15 минут"},
    "R30": {"minutes": 30, "description": "30 минут"},
    "R45": {"minutes": 45, "description": "45 минут"},
    "R60": {"minutes": 60, "description": "60 минут"},
    "R90": {"minutes": 90, "description": "90 минут"},
    "R120": {"minutes": 120, "description": "120 минут"},
    "R150": {"minutes": 150, "description": "150 минут"},
    "R180": {"minutes": 180, "description": "180 минут"},
}

# Категории грунтов (СП 22.13330)
SOIL_TYPES = {
    "I": {"description": "Скальные грунты", "E0_MPa": 50, "gamma_kN_m3": 22},
    "II": {"description": "Крупнообломочные, крупные и средние пески", "E0_MPa": 15, "gamma_kN_m3": 19},
    "III": {"description": "Пылеватые и мелкие пески, супеси", "E0_MPa": 8, "gamma_kN_m3": 18},
    "IV": {"description": "Суглинки и глины твёрдые", "E0_MPa": 5, "gamma_kN_m3": 17},
    "V": {"description": "Суглинки и глины мягкопластичные", "E0_MPa": 3, "gamma_kN_m3": 16},
}


# ═══════════════════════════════════════════════════════════════
# БАЗА СЕЧЕНИЙ (ГОСТ 8239, ГОСТ 26020)
# ═══════════════════════════════════════════════════════════════


class SectionDatabase:
    """
    База данных сечений российского проката.

    Источники:
      - ГОСТ 8239-89 — Двутавры стальные горячекатаные
      - ГОСТ 26020-83 — Двутавры с параллельными гранями полок
      - ГОСТ 8240-97 — Швеллеры стальные горячекатаные
      - ГОСТ 8509-93 — Уголки стальные равнополочные
      - ГОСТ 8645-68 — Трубы стальные прямоугольные
    """

    # Двутавры (ГОСТ 8239) — номер: {h, b, tw, tf, A, Ix, Iy, Wx, Wy, ix, iy}
    I_BEAMS = {
        "10": {
            "h": 100,
            "b": 55,
            "tw": 4.5,
            "tf": 7.2,
            "A_cm2": 12.0,
            "Ix_cm4": 198,
            "Iy_cm4": 17.9,
            "Wx_cm3": 39.7,
            "Wy_cm3": 6.49,
            "ix_cm": 4.07,
            "iy_cm": 1.22,
        },
        "12": {
            "h": 120,
            "b": 64,
            "tw": 4.8,
            "tf": 7.3,
            "A_cm2": 14.7,
            "Ix_cm4": 351,
            "Iy_cm4": 28.0,
            "Wx_cm3": 58.4,
            "Wy_cm3": 8.75,
            "ix_cm": 4.88,
            "iy_cm": 1.38,
        },
        "14": {
            "h": 140,
            "b": 73,
            "tw": 4.9,
            "tf": 7.5,
            "A_cm2": 17.4,
            "Ix_cm4": 572,
            "Iy_cm4": 42.8,
            "Wx_cm3": 81.7,
            "Wy_cm3": 11.7,
            "ix_cm": 5.73,
            "iy_cm": 1.57,
        },
        "16": {
            "h": 160,
            "b": 81,
            "tw": 5.0,
            "tf": 7.8,
            "A_cm2": 20.2,
            "Ix_cm4": 873,
            "Iy_cm4": 58.5,
            "Wx_cm3": 109,
            "Wy_cm3": 14.4,
            "ix_cm": 6.57,
            "iy_cm": 1.70,
        },
        "18": {
            "h": 180,
            "b": 90,
            "tw": 5.1,
            "tf": 8.1,
            "A_cm2": 23.0,
            "Ix_cm4": 1250,
            "Iy_cm4": 80.6,
            "Wx_cm3": 139,
            "Wy_cm3": 17.9,
            "ix_cm": 7.38,
            "iy_cm": 1.87,
        },
        "20": {
            "h": 200,
            "b": 100,
            "tw": 5.2,
            "tf": 8.4,
            "A_cm2": 26.1,
            "Ix_cm4": 1740,
            "Iy_cm4": 110,
            "Wx_cm3": 174,
            "Wy_cm3": 22.0,
            "ix_cm": 8.17,
            "iy_cm": 2.06,
        },
        "24": {
            "h": 240,
            "b": 115,
            "tw": 5.6,
            "tf": 9.3,
            "A_cm2": 32.4,
            "Ix_cm4": 3270,
            "Iy_cm4": 183,
            "Wx_cm3": 273,
            "Wy_cm3": 31.9,
            "ix_cm": 10.05,
            "iy_cm": 2.38,
        },
        "27": {
            "h": 270,
            "b": 125,
            "tw": 6.0,
            "tf": 10.0,
            "A_cm2": 38.5,
            "Ix_cm4": 5010,
            "Iy_cm4": 264,
            "Wx_cm3": 371,
            "Wy_cm3": 42.2,
            "ix_cm": 11.41,
            "iy_cm": 2.62,
        },
        "30": {
            "h": 300,
            "b": 135,
            "tw": 6.5,
            "tf": 10.8,
            "A_cm2": 45.0,
            "Ix_cm4": 7310,
            "Iy_cm4": 374,
            "Wx_cm3": 487,
            "Wy_cm3": 55.4,
            "ix_cm": 12.74,
            "iy_cm": 2.88,
        },
        "36": {
            "h": 360,
            "b": 165,
            "tw": 7.5,
            "tf": 12.6,
            "A_cm2": 60.5,
            "Ix_cm4": 13500,
            "Iy_cm4": 789,
            "Wx_cm3": 750,
            "Wy_cm3": 95.7,
            "ix_cm": 14.94,
            "iy_cm": 3.61,
        },
        "40": {
            "h": 400,
            "b": 155,
            "tw": 8.0,
            "tf": 13.5,
            "A_cm2": 66.8,
            "Ix_cm4": 17900,
            "Iy_cm4": 744,
            "Wx_cm3": 895,
            "Wy_cm3": 96.0,
            "ix_cm": 16.36,
            "iy_cm": 3.33,
        },
        "45": {
            "h": 450,
            "b": 170,
            "tw": 9.0,
            "tf": 15.0,
            "A_cm2": 82.0,
            "Ix_cm4": 27800,
            "Iy_cm4": 1120,
            "Wx_cm3": 1236,
            "Wy_cm3": 132,
            "ix_cm": 18.40,
            "iy_cm": 3.70,
        },
        "50": {
            "h": 500,
            "b": 180,
            "tw": 10.0,
            "tf": 16.0,
            "A_cm2": 97.0,
            "Ix_cm4": 40900,
            "Iy_cm4": 1510,
            "Wx_cm3": 1636,
            "Wy_cm3": 168,
            "ix_cm": 20.55,
            "iy_cm": 3.94,
        },
        "55": {
            "h": 550,
            "b": 190,
            "tw": 11.0,
            "tf": 17.5,
            "A_cm2": 115,
            "Ix_cm4": 58500,
            "Iy_cm4": 2070,
            "Wx_cm3": 2127,
            "Wy_cm3": 218,
            "ix_cm": 22.53,
            "iy_cm": 4.25,
        },
        "60": {
            "h": 600,
            "b": 200,
            "tw": 12.0,
            "tf": 19.0,
            "A_cm2": 135,
            "Ix_cm4": 80800,
            "Iy_cm4": 2770,
            "Wx_cm3": 2693,
            "Wy_cm3": 277,
            "ix_cm": 24.50,
            "iy_cm": 4.54,
        },
    }

    # Швеллеры (ГОСТ 8240)
    CHANNELS = {
        "8": {
            "h": 80,
            "b": 40,
            "tw": 4.5,
            "tf": 7.0,
            "A_cm2": 8.98,
            "Ix_cm4": 77.8,
            "Iy_cm4": 10.4,
            "Wx_cm3": 19.5,
            "Wy_cm3": 4.48,
        },
        "10": {
            "h": 100,
            "b": 46,
            "tw": 4.5,
            "tf": 7.5,
            "A_cm2": 11.2,
            "Ix_cm4": 150,
            "Iy_cm4": 18.2,
            "Wx_cm3": 30.0,
            "Wy_cm3": 6.50,
        },
        "12": {
            "h": 120,
            "b": 52,
            "tw": 4.8,
            "tf": 7.8,
            "A_cm2": 13.5,
            "Ix_cm4": 260,
            "Iy_cm4": 29.5,
            "Wx_cm3": 43.3,
            "Wy_cm3": 9.00,
        },
        "14": {
            "h": 140,
            "b": 58,
            "tw": 5.0,
            "tf": 8.2,
            "A_cm2": 15.8,
            "Ix_cm4": 410,
            "Iy_cm4": 44.7,
            "Wx_cm3": 58.6,
            "Wy_cm3": 12.0,
        },
        "16": {
            "h": 160,
            "b": 64,
            "tw": 5.5,
            "tf": 8.7,
            "A_cm2": 18.4,
            "Ix_cm4": 618,
            "Iy_cm4": 64.3,
            "Wx_cm3": 77.2,
            "Wy_cm3": 15.5,
        },
        "18": {
            "h": 180,
            "b": 70,
            "tw": 5.5,
            "tf": 9.0,
            "A_cm2": 20.7,
            "Ix_cm4": 886,
            "Iy_cm4": 88.2,
            "Wx_cm3": 98.5,
            "Wy_cm3": 19.7,
        },
        "20": {
            "h": 200,
            "b": 76,
            "tw": 6.0,
            "tf": 9.5,
            "A_cm2": 23.6,
            "Ix_cm4": 1240,
            "Iy_cm4": 118,
            "Wx_cm3": 124,
            "Wy_cm3": 24.6,
        },
        "24": {
            "h": 240,
            "b": 82,
            "tw": 6.5,
            "tf": 10.5,
            "A_cm2": 28.8,
            "Ix_cm4": 2220,
            "Iy_cm4": 164,
            "Wx_cm3": 185,
            "Wy_cm3": 33.2,
        },
        "30": {
            "h": 300,
            "b": 90,
            "tw": 7.5,
            "tf": 12.0,
            "A_cm2": 38.4,
            "Ix_cm4": 4430,
            "Iy_cm4": 254,
            "Wx_cm3": 295,
            "Wy_cm3": 47.5,
        },
    }

    # Трубы прямоугольные (ГОСТ 8645) — выборочно
    RECT_TUBES = {
        "50x25x3": {
            "h": 50,
            "b": 25,
            "t": 3,
            "A_cm2": 4.08,
            "Ix_cm4": 16.5,
            "Iy_cm4": 5.76,
            "Wx_cm3": 6.60,
            "Wy_cm3": 4.61,
        },
        "60x40x3": {
            "h": 60,
            "b": 40,
            "t": 3,
            "A_cm2": 5.28,
            "Ix_cm4": 34.3,
            "Iy_cm4": 17.2,
            "Wx_cm3": 11.4,
            "Wy_cm3": 8.62,
        },
        "80x40x3": {
            "h": 80,
            "b": 40,
            "t": 3,
            "A_cm2": 6.48,
            "Ix_cm4": 68.6,
            "Iy_cm4": 24.1,
            "Wx_cm3": 17.2,
            "Wy_cm3": 12.0,
        },
        "100x50x4": {
            "h": 100,
            "b": 50,
            "t": 4,
            "A_cm2": 10.9,
            "Ix_cm4": 184,
            "Iy_cm4": 63.1,
            "Wx_cm3": 36.8,
            "Wy_cm3": 25.2,
        },
        "120x60x4": {
            "h": 120,
            "b": 60,
            "t": 4,
            "A_cm2": 13.3,
            "Ix_cm4": 325,
            "Iy_cm4": 108,
            "Wx_cm3": 54.2,
            "Wy_cm3": 36.1,
        },
        "140x80x5": {
            "h": 140,
            "b": 80,
            "t": 5,
            "A_cm2": 20.5,
            "Ix_cm4": 675,
            "Iy_cm4": 294,
            "Wx_cm3": 96.4,
            "Wy_cm3": 73.5,
        },
        "160x80x5": {
            "h": 160,
            "b": 80,
            "t": 5,
            "A_cm2": 22.5,
            "Ix_cm4": 925,
            "Iy_cm4": 317,
            "Wx_cm3": 115.6,
            "Wy_cm3": 79.3,
        },
        "180x100x6": {
            "h": 180,
            "b": 100,
            "t": 6,
            "A_cm2": 31.3,
            "Ix_cm4": 1620,
            "Iy_cm4": 648,
            "Wx_cm3": 180,
            "Wy_cm3": 129.6,
        },
        "200x100x6": {
            "h": 200,
            "b": 100,
            "t": 6,
            "A_cm2": 33.3,
            "Ix_cm4": 2120,
            "Iy_cm4": 696,
            "Wx_cm3": 212,
            "Wy_cm3": 139,
        },
    }

    @classmethod
    def get_i_beam(cls, number: str) -> dict | None:
        """Получить параметры двутавра по номеру."""
        return cls.I_BEAMS.get(str(number))

    @classmethod
    def get_channel(cls, number: str) -> dict | None:
        """Получить параметры швеллера по номеру."""
        return cls.CHANNELS.get(str(number))

    @classmethod
    def get_rect_tube(cls, designation: str) -> dict | None:
        """Получить параметры прямоугольной трубы."""
        return cls.RECT_TUBES.get(designation)

    @classmethod
    def calc_rect_section(cls, b: float, h: float) -> dict[str, float]:
        """
        Рассчитать геометрические характеристики прямоугольного сечения.

        Args:
            b: ширина (м)
            h: высота (м)

        Returns:
            A, Ix, Iy, Wx, Wy, ix, iy
        """
        A = b * h
        Ix = b * h**3 / 12
        Iy = h * b**3 / 12
        Wx = b * h**2 / 6
        Wy = h * b**2 / 6
        ix = h / math.sqrt(12)
        iy = b / math.sqrt(12)
        return {
            "A_m2": round(A, 6),
            "Ix_m4": round(Ix, 8),
            "Iy_m4": round(Iy, 8),
            "Wx_m3": round(Wx, 7),
            "Wy_m3": round(Wy, 7),
            "ix_m": round(ix, 4),
            "iy_m": round(iy, 4),
        }

    @classmethod
    def calc_circular_section(cls, r: float) -> dict[str, float]:
        """
        Рассчитать геометрические характеристики круглого сечения.

        Args:
            r: радиус (м)

        Returns:
            A, I, W, i
        """
        A = math.pi * r**2
        I = math.pi * r**4 / 4
        W = math.pi * r**3 / 4
        i = r / 2
        return {
            "A_m2": round(A, 6),
            "I_m4": round(I, 8),
            "W_m3": round(W, 7),
            "i_m": round(i, 4),
        }


# ═══════════════════════════════════════════════════════════════
# МКЭ РЕШАТЕЛЬ (FEM SOLVER)
# ═══════════════════════════════════════════════════════════════


class FEMSolver:
    """
    Решатель метода конечных элементов.

    Поддерживает:
      - Стержневые элементы (балки)
      - Сборка глобальной матрицы жёсткости
      - Граничные условия
      - Решение K·u = F
      - Определение усилий в элементах
    """

    @staticmethod
    def beam_element_stiffness(E: float, A: float, I: float, L: float) -> "np.ndarray":
        """
        Матрица жёсткости стержневого элемента (6×6).

        Узловые степени свободы: [u1, v1, θ1, u2, v2, θ2]
        u — продольное перемещение
        v — поперечное перемещение
        θ — угол поворота

        Args:
            E: модуль упругости (Па)
            A: площадь поперечного сечения (м²)
            I: момент инерции (м⁴)
            L: длина элемента (м)

        Returns:
            Матрица жёсткости 6×6 (numpy array)
        """
        if not HAS_NUMPY:
            raise RuntimeError("numpy required for FEM")

        k = np.zeros((6, 6))
        ea_l = E * A / L
        ei_l = E * I / L
        ei_l2 = E * I / L**2
        ei_l3 = E * I / L**3

        # Продольные
        k[0, 0] = k[3, 3] = ea_l
        k[0, 3] = k[3, 0] = -ea_l

        # Поперечные и изгибные
        k[1, 1] = k[4, 4] = 12 * ei_l3
        k[1, 4] = k[4, 1] = -12 * ei_l3
        k[1, 2] = k[2, 1] = 6 * ei_l2
        k[1, 5] = k[5, 1] = 6 * ei_l2
        k[2, 4] = k[4, 2] = -6 * ei_l2
        k[4, 5] = k[5, 4] = -6 * ei_l2
        k[2, 2] = k[5, 5] = 4 * ei_l
        k[2, 5] = k[5, 2] = 2 * ei_l

        return k

    @staticmethod
    def assemble_global_stiffness(elements: list[dict], n_nodes: int, dof_per_node: int = 3) -> "np.ndarray":
        """
        Сборка глобальной матрицы жёсткости.

        Args:
            elements: список элементов, каждый = {'E', 'A', 'I', 'L', 'nodes': [i, j]}
            n_nodes: количество узлов
            dof_per_node: степеней свободы на узел (по умолчанию 3)

        Returns:
            Глобальная матрица жёсткости (numpy array)
        """
        if not HAS_NUMPY:
            raise RuntimeError("numpy required for FEM")

        n_dof = n_nodes * dof_per_node
        K = np.zeros((n_dof, n_dof))

        for elem in elements:
            ke = FEMSolver.beam_element_stiffness(elem["E"], elem["A"], elem["I"], elem["L"])
            nodes = elem["nodes"]
            for i_local, i_global in enumerate(nodes):
                for j_local, j_global in enumerate(nodes):
                    for di in range(dof_per_node):
                        for dj in range(dof_per_node):
                            gi = i_global * dof_per_node + di
                            gj = j_global * dof_per_node + dj
                            li = i_local * dof_per_node + di
                            lj = j_local * dof_per_node + dj
                            K[gi, gj] += ke[li, lj]

        return K

    @staticmethod
    def apply_boundary_conditions(
        K: "np.ndarray", F: "np.ndarray", fixed_dofs: list[int]
    ) -> tuple["np.ndarray", "np.ndarray", list[int]]:
        """
        Применить граничные условия (заделка указанных DOF).

        Args:
            K: глобальная матрица жёсткости
            F: вектор нагрузок
            fixed_dofs: список закреплённых степеней свободы

        Returns:
            K_reduced, F_reduced, free_dofs
        """
        if not HAS_NUMPY:
            raise RuntimeError("numpy required for FEM")

        n_dof = len(F)
        free_dofs = [i for i in range(n_dof) if i not in fixed_dofs]

        K_red = K[np.ix_(free_dofs, free_dofs)]
        F_red = F[free_dofs]

        return K_red, F_red, free_dofs

    @staticmethod
    def solve(K_red: "np.ndarray", F_red: "np.ndarray") -> "np.ndarray":
        """
        Решить систему Ku = F.

        Returns:
            Вектор перемещений (numpy array)
        """
        if not HAS_NUMPY:
            raise RuntimeError("numpy required for FEM")

        return np.linalg.solve(K_red, F_red)

    @staticmethod
    def recover_full_displacements(u_red: "np.ndarray", free_dofs: list[int], n_dof: int) -> "np.ndarray":
        """Восстановить полный вектор перемещений."""
        if not HAS_NUMPY:
            raise RuntimeError("numpy required for FEM")

        u = np.zeros(n_dof)
        for i, dof in enumerate(free_dofs):
            u[dof] = u_red[i]
        return u

    @staticmethod
    def element_forces(elem: dict, u_global: "np.ndarray", dof_per_node: int = 3) -> dict:
        """
        Определить усилия в элементе.

        Args:
            elem: параметры элемента
            u_global: глобальные перемещения
            dof_per_node: степеней свободы на узел

        Returns:
            {N1, V1, M1, N2, V2, M2} — продольные, поперечные, моменты
        """
        if not HAS_NUMPY:
            raise RuntimeError("numpy required for FEM")

        ke = FEMSolver.beam_element_stiffness(elem["E"], elem["A"], elem["I"], elem["L"])

        nodes = elem["nodes"]
        ue = np.zeros(6)
        for i_local, i_global in enumerate(nodes):
            for di in range(dof_per_node):
                ue[i_local * dof_per_node + di] = u_global[i_global * dof_per_node + di]

        fe = ke @ ue

        return {
            "N1_kN": round(fe[0] / 1000, 2),
            "V1_kN": round(fe[1] / 1000, 2),
            "M1_kNm": round(fe[2] / 1000, 3),
            "N2_kN": round(fe[3] / 1000, 2),
            "V2_kN": round(fe[4] / 1000, 2),
            "M2_kNm": round(fe[5] / 1000, 3),
        }


# ═══════════════════════════════════════════════════════════════
# КОМБИНАЦИИ НАГРУЗОК (СП 20.13330)
# ═══════════════════════════════════════════════════════════════


class LoadCombiner:
    """
    Формирование комбинаций нагрузок по СП 20.13330.2016.

    Основные расчётные ситуации:
      1. ППУ (предельное по несущей способности) — γ_f × γ_n × Q
      2. ПРУ (предельное по деформациям) — без γ_f

    Комбинации:
      Основная: γ_fG × G + γ_fQ × Q + γ_fS × S + γ_fW × ψ × W
      Особая: γ_fG × G + γ_fSeismic × E + ψ × Q
    """

    @staticmethod
    def basic_combination(dead_kN: float, live_kN: float, snow_kN: float = 0, wind_kN: float = 0) -> dict:
        """
        Основная комбинация нагрузок (ППУ).

        СП 20.13330 формула (7.1):
        γ_f1 × G + γ_f2 × Q + γ_f3 × ψ × (S + W)

        Args:
            dead_kN: постоянная нагрузка (кН)
            live_kN: временная длительная нагрузка (кН)
            snow_kN: снеговая нагрузка (кН)
            wind_kN: ветровая нагрузка (кН)

        Returns:
            Расчётная нагрузка и разбивка по факторам
        """
        gf_dead = GAMMA_F["dead_unfavorable"]
        gf_live = GAMMA_F["live_short"]
        gf_snow = GAMMA_F["snow"]
        gf_wind = GAMMA_F["wind"]
        psi_0 = PSI_0

        # Основная комбинация (с снегом и ветром)
        N_total = gf_dead * dead_kN + gf_live * live_kN + gf_snow * snow_kN + gf_wind * psi_0["wind"] * wind_kN

        # Без снега/ветра
        N_basic = gf_dead * dead_kN + gf_live * live_kN

        return {
            "combination_type": "basic_PPU",
            "dead_component_kN": round(gf_dead * dead_kN, 2),
            "live_component_kN": round(gf_live * live_kN, 2),
            "snow_component_kN": round(gf_snow * snow_kN, 2),
            "wind_component_kN": round(gf_wind * psi_0["wind"] * wind_kN, 2),
            "total_with_snow_wind_kN": round(N_total, 2),
            "total_basic_kN": round(N_basic, 2),
            "gamma_f_dead": gf_dead,
            "gamma_f_live": gf_live,
            "gamma_f_snow": gf_snow,
            "gamma_f_wind": gf_wind,
            "psi_0_wind": psi_0["wind"],
            "norm": "СП 20.13330.2016 п.7.1",
        }

    @staticmethod
    def seismic_combination(dead_kN: float, live_kN: float, seismic_kN: float) -> dict:
        """
        Особая комбинация нагрузок при сейсмике.

        СП 14.13330 формула: G + ψ × Q + E

        Args:
            dead_kN: постоянная нагрузка (кН)
            live_kN: временная нагрузка (кН)
            seismic_kN: сейсмическая нагрузка (кН)

        Returns:
            Расчётная нагрузка при сейсмике
        """
        psi_1_live = PSI_1["live"]

        N_total = dead_kN + psi_1_live * live_kN + seismic_kN

        return {
            "combination_type": "seismic",
            "dead_kN": round(dead_kN, 2),
            "live_reduced_kN": round(psi_1_live * live_kN, 2),
            "seismic_kN": round(seismic_kN, 2),
            "total_kN": round(N_total, 2),
            "psi_1_live": psi_1_live,
            "norm": "СП 14.13330.2018 п.5.4",
        }

    @staticmethod
    def pattern_loading(dead_kN: float, live_kN: float, span_count: int = 3) -> list[dict]:
        """
        Расстановка нагрузок для неразрезных балок.

        СП 20.13330 — для максимальных/минимальных усилий
        в пролётах и на опорах.

        Args:
            dead_kN: постоянная нагрузка на пролёт (кН/м)
            live_kN: временная нагрузка на пролёт (кН/м)
            span_count: количество пролётов

        Returns:
            Список комбинаций расстановки
        """
        combos = []

        # Для каждого пролёта: загружаем чётные или нечётные
        for loaded_span in range(span_count):
            pattern = []
            for s in range(span_count):
                if s == loaded_span:
                    pattern.append({"span": s, "dead": dead_kN, "live": live_kN})
                else:
                    pattern.append({"span": s, "dead": dead_kN, "live": 0})

            combos.append(
                {
                    "description": f"Макс. в пролёте {loaded_span + 1}",
                    "pattern": pattern,
                    "type": "pattern_loading",
                }
            )

        # Все пролёты загружены
        combos.append(
            {
                "description": "Все пролёты загружены",
                "pattern": [{"span": s, "dead": dead_kN, "live": live_kN} for s in range(span_count)],
                "type": "full_loading",
            }
        )

        return combos


# ═══════════════════════════════════════════════════════════════
# ПРОВЕРКА СТАЛЬНЫХ КОНСТРУКЦИЙ (СП 16.13330)
# ═══════════════════════════════════════════════════════════════


class MemberChecker:
    """
    Проверка несущей способности элементов.

    СП 16.13330.2017 — стальные конструкции
    СП 63.13330.2018 — бетонные и ЖБ конструкции
    """

    @staticmethod
    def steel_beam_bending(W_x_m3: float, f_y_MPa: float, gamma_c: float = 1.0) -> dict:
        """
        Проверка стальной балки на изгиб (СП 16 п.8.2.1).

        M_pl,Rd = W_x × f_y / γ_c

        Args:
            W_x_m3: момент сопротивления (м³)
            f_y_MPa: предел текучести стали (МПа)
            gamma_c: коэффициент условий работы (1.0 по умолчанию)

        Returns:
            Несущая способность на изгиб
        """
        # W_x в см³ → м³ уже передан
        M_Rd = W_x_m3 * f_y_MPa * 1e6 / gamma_c  # Н·м  # type: ignore[operator]

        return {
            "M_Rd_kNm": round(M_Rd / 1000, 2),
            "W_x_m3": W_x_m3,
            "f_y_MPa": f_y_MPa,
            "gamma_c": gamma_c,
            "check": f"M ≤ {round(M_Rd / 1000, 2)} кН·м",
            "norm": "СП 16.13330.2017 п.8.2.1",
        }

    @staticmethod
    def steel_beam_shear(A_web_m2: float, f_y_MPa: float, gamma_c: float = 1.0) -> dict:
        """
        Проверка стальной балки на поперечную силу (СП 16 п.8.2.4).

        V_pl,Rd = A_web × f_y / (√3 × γ_c)

        Args:
            A_web_m2: площадь стенки (м²)
            f_y_MPa: предел текучести (МПа)

        Returns:
            Несущая способность на сдвиг
        """
        V_Rd = A_web_m2 * f_y_MPa * 1e6 / (math.sqrt(3) * gamma_c)  # type: ignore[operator]

        return {
            "V_Rd_kN": round(V_Rd / 1000, 2),
            "A_web_m2": A_web_m2,
            "f_y_MPa": f_y_MPa,
            "check": f"V ≤ {round(V_Rd / 1000, 2)} кН",
            "norm": "СП 16.13330.2017 п.8.2.4",
        }

    @staticmethod
    def steel_column_axial(A_m2: float, f_y_MPa: float, chi: float, gamma_c: float = 1.0) -> dict:
        """
        Проверка стальной колонны на осевое сжатие (СП 16 п.7.1.1).

        N_cr = χ × A × f_y / γ_c

        Args:
            A_m2: площадь сечения (м²)
            f_y_MPa: предел текучести (МПа)
            chi: коэффициент устойчивости (из кривых кручения)

        Returns:
            Несущая способность на сжатие
        """
        N_Rd = chi * A_m2 * f_y_MPa * 1e6 / gamma_c  # type: ignore[operator]

        return {
            "N_Rd_kN": round(N_Rd / 1000, 2),
            "chi": chi,
            "A_m2": A_m2,
            "f_y_MPa": f_y_MPa,
            "check": f"N ≤ {round(N_Rd / 1000, 2)} кН",
            "norm": "СП 16.13330.2017 п.7.1.1",
        }

    @staticmethod
    def euler_buckling_load(E_MPa: float, I_m4: float, L_eff_m: float) -> dict:
        """
        Критическая сила Эйлера.

        N_cr = π² × E × I / L_eff²

        Args:
            E_MPa: модуль упругости (МПа)
            I_m4: момент инерции (м⁴)
            L_eff_m: расчётная длина (м)

        Returns:
            Критическая сила
        """
        N_cr = math.pi**2 * E_MPa * 1e6 * I_m4 / L_eff_m**2

        return {
            "N_cr_kN": round(N_cr / 1000, 2),
            "E_MPa": E_MPa,
            "I_m4": I_m4,
            "L_eff_m": L_eff_m,
            "norm": "СП 16.13330.2017 п.7.1.3",
        }

    @staticmethod
    def buckling_curve(lambda_bar: float, curve: str = "b") -> dict:
        """
        Коэффициент устойчивости χ по кривым кручения (СП 16 табл. 7.1).

        Args:
            lambda_bar: приведённая гибкость λ̄ = λ/λ₁
            curve: кривая кручения ('a', 'b', 'c', 'd')

        Returns:
            Коэффициент χ и параметры
        """
        # Параметры кривых (СП 16 табл. 7.1)
        curves = {
            "a": {"alpha": 0.21, "lambda_bar_0": 0.2},
            "b": {"alpha": 0.34, "lambda_bar_0": 0.2},
            "c": {"alpha": 0.49, "lambda_bar_0": 0.2},
            "d": {"alpha": 0.76, "lambda_bar_0": 0.2},
        }

        params = curves.get(curve, curves["b"])
        alpha = params["alpha"]

        if lambda_bar <= params["lambda_bar_0"]:
            chi = 1.0
        else:
            phi = 0.5 * (1 + alpha * (lambda_bar - 0.2) + lambda_bar**2)
            chi = min(1.0, 1.0 / (phi + math.sqrt(phi**2 - lambda_bar**2)))

        return {
            "chi": round(chi, 4),
            "lambda_bar": lambda_bar,
            "curve": curve,
            "alpha": alpha,
            "norm": "СП 16.13330.2017 табл. 7.1",
        }

    @staticmethod
    def deflection_check(L_m: float, delta_actual_m: float, limit_ratio: int = 250) -> dict:
        """
        Проверка прогиба (СП 16 табл. 18).

        δ ≤ L / limit_ratio

        Args:
            L_m: пролёт (м)
            delta_actual_m: фактический прогиб (м)
            limit_ratio: предельное отношение (250, 360, 400)

        Returns:
            Результат проверки
        """
        delta_limit = L_m / limit_ratio
        ratio = delta_actual_m / delta_limit if delta_limit > 0 else 0

        return {
            "delta_actual_mm": round(delta_actual_m * 1000, 2),
            "delta_limit_mm": round(delta_limit * 1000, 2),
            "L_m": L_m,
            "limit_ratio": f"L/{limit_ratio}",
            "utilization": round(ratio, 3),
            "passed": delta_actual_m <= delta_limit,
            "norm": "СП 16.13330.2017 табл. 18",
        }

    @staticmethod
    def rc_beam_flexure(
        b_m: float, h_m: float, d_m: float, concrete_class: str, rebar_class: str, M_kNm: float
    ) -> dict:
        """
        Расчёт ЖБ балки на изгиб (СП 63 п.8.1).

        Подбор площади арматуры As.

        Args:
            b_m: ширина сечения (м)
            h_m: высота сечения (м)
            d_m: рабочая высота (м)
            concrete_class: класс бетона (B20, B25, ...)
            rebar_class: класс арматуры (A400, A500, ...)
            M_kNm: расчётный момент (кН·м)

        Returns:
            Площадь арматуры и проверки
        """
        concrete = CONCRETE_CLASSES.get(concrete_class, CONCRETE_CLASSES["B25"])
        rebar = REBAR_CLASSES.get(rebar_class, REBAR_CLASSES["A500"])

        f_b = concrete["f_b"]  # МПа
        f_y = rebar["f_y"]  # МПа
        E_s = rebar["E_s"]  # МПа

        M = M_kNm * 1e6  # Н·мм

        # Расчёт по СП 63 формула (8.3):
        # M = Rs × As × (h0 - 0.5 × x)
        # x = Rs × As / (Rb × b)

        # Коэффициент ξ_R = Rs / (Rb × b × h0² / M)
        mu = M / (b_m * 1000 * (d_m * 1000) ** 2 * f_b)  # type: ignore[operator]

        if mu > 0.4:
            return {
                "error": "Превышен предел ξ (μ > 0.4) — нужно увеличить сечение или класс бетона",
                "mu": round(mu, 4),
                "concrete_class": concrete_class,
                "norm": "СП 63.13330.2018 п.8.1",
            }

        # ξ = 1 - √(1 - 2μ)
        xi = 1 - math.sqrt(max(0, 1 - 2 * mu))

        # As = ξ × b × h0 × Rb / Rs
        A_s_mm2 = xi * b_m * 1000 * d_m * 1000 * f_b / f_y  # type: ignore[operator]

        # Минимальное армирование (СП 63 п.10.3.6)
        A_s_min = max(0.001 * b_m * 1000 * h_m * 1000, 0.06 * f_b * b_m * 1000 * h_m * 1000 / f_y)  # type: ignore[operator]

        A_s_final = max(A_s_mm2, A_s_min)

        # Подбор стержней
        bar_diameters = [12, 14, 16, 18, 20, 22, 25, 28, 32]
        bar_options = []
        for d in bar_diameters:
            bar_area = math.pi * d**2 / 4
            n_bars = math.ceil(A_s_final / bar_area)
            if n_bars <= 8:
                bar_options.append({"diameter_mm": d, "count": n_bars, "total_area_mm2": round(n_bars * bar_area)})

        return {
            "M_kNm": M_kNm,
            "concrete_class": concrete_class,
            "f_b_MPa": f_b,
            "rebar_class": rebar_class,
            "f_y_MPa": f_y,
            "mu": round(mu, 4),
            "xi": round(xi, 4),
            "A_s_calculated_mm2": round(A_s_mm2, 1),
            "A_s_min_mm2": round(A_s_min, 1),
            "A_s_final_mm2": round(A_s_final, 1),
            "bar_options": bar_options[:5],
            "norm": "СП 63.13330.2018 п.8.1",
        }

    @staticmethod
    def crack_width_check(
        A_s_mm2: float,
        b_m: float,
        h_m: float,
        d_m: float,
        M_kNm: float,
        concrete_class: str,
        rebar_class: str,
        exposure_class: str = "XC1",
    ) -> dict:
        """
        Проверка ширины раскрытия трещин (СП 63 п.8.4).

        w ≤ w_max (табл. 8.1)

        Args:
            A_s_mm2: площадь арматуры (мм²)
            b_m: ширина сечения (м)
            h_m: высота (м)
            d_m: рабочая высота (м)
            M_kNm: момент (кН·м)
            concrete_class: класс бетона
            rebar_class: класс арматуры
            exposure_class: класс эксплуатационных условий

        Returns:
            Проверка ширины трещин
        """
        # Предельная ширина трещин по СП 63 табл. 8.1
        w_max_table = {
            "XC1": 0.4,
            "XC2": 0.3,
            "XC3": 0.3,
            "XC4": 0.2,
            "XD1": 0.2,
            "XD2": 0.2,
            "XS1": 0.2,
            "XS2": 0.2,
            "XS3": 0.2,
            "XA1": 0.2,
            "XA2": 0.2,
            "XA3": 0.2,
        }
        w_max = w_max_table.get(exposure_class, 0.3)

        # Упрощённый расчёт (СП 63 формула 8.21)
        concrete = CONCRETE_CLASSES.get(concrete_class, CONCRETE_CLASSES["B25"])
        rebar = REBAR_CLASSES.get(rebar_class, REBAR_CLASSES["A500"])

        f_ct = concrete["f_bt"]
        E_s = rebar["E_s"]

        b = b_m * 1000  # мм
        h = h_m * 1000
        d = d_m * 1000

        # Момент трещинообразования
        W = b * h**2 / 6
        M_cr = f_ct * W  # Н·мм
        M = M_kNm * 1e6

        if M_cr >= M:
            w_calc = 0.0
        else:
            # ψ_s = 1 - 0.8 × M_cr / M
            psi_s = max(0, 1 - 0.8 * M_cr / M)

            # s = 1 + 0.5 × c / h_eff
            c = 25  # мм, толщина защитного слоя
            s = 1 + 0.5 * c / h

            # ε_sm - ε_cm
            rho_eff = A_s_mm2 / (b * h)
            eps_sm = psi_s * M / (E_s * A_s_mm2 * (d - 0.5 * h))
            eps_cm = 0.6 * f_ct / (concrete["E_b"] * 1000)

            delta_eps = max(0, eps_sm - eps_cm)

            # w = s × 3.4 × c × (ε_sm - ε_cm)
            w_calc = s * 3.4 * c * delta_eps

        return {
            "w_calc_mm": round(w_calc, 3),
            "w_max_mm": w_max,
            "exposure_class": exposure_class,
            "passed": w_calc <= w_max,
            "utilization": round(w_calc / w_max, 3) if w_max > 0 else 0,
            "norm": "СП 63.13330.2018 п.8.4",
        }


# ═══════════════════════════════════════════════════════════════
# ДИНАМИКА И СЕЙСМИКА (СП 14.13330)
# ═══════════════════════════════════════════════════════════════


class DynamicsAnalyzer:
    """
    Динамический и сейсмический анализ.

    СП 14.13330.2018 — Строительство в сейсмических районах
    """

    @staticmethod
    def natural_frequency_rayleigh(stiffness_N_m: float, mass_kg: float) -> dict:
        """
        Собственная частота методом Рэлея.

        ω = √(k / m)
        f = ω / (2π)

        Args:
            stiffness_N_m: жёсткость (Н/м)
            mass_kg: масса (кг)

        Returns:
            Собственная частота и период
        """
        omega = math.sqrt(stiffness_N_m / mass_kg)
        f = omega / (2 * math.pi)
        T = 1 / f

        return {
            "omega_rad_s": round(omega, 3),
            "frequency_Hz": round(f, 3),
            "period_s": round(T, 3),
            "stiffness_N_m": stiffness_N_m,
            "mass_kg": mass_kg,
            "norm": "СП 14.13330.2018 п.5.3",
        }

    @staticmethod
    def seismic_force(mass_kg: float, K1: float = 0.5, beta: float = 1.0, I: float = 1.0) -> dict:
        """
        Сейсмическая сила (СП 14.13330 п.5.5).

        E = K1 × β × I × m × g

        Args:
            mass_kg: масса конструкции (кг)
            K1: коэффициент сейсмичности (0.25, 0.5, 0.75, 1.0)
            beta: динамический коэффициент (из спектра)
            I: коэффициент ответственности (1.0 или 0.8)

        Returns:
            Сейсмическая сила
        """
        g = 9.81
        E_kN = K1 * beta * I * mass_kg * g / 1000

        return {
            "seismic_force_kN": round(E_kN, 2),
            "K1": K1,
            "beta": beta,
            "I": I,
            "mass_kg": mass_kg,
            "norm": "СП 14.13330.2018 п.5.5",
        }

    @staticmethod
    def response_spectrum(T_s: float, soil_type: str = "II", seismic_zone: int = 7) -> dict:
        """
        Спектр реакции (СП 14.13330 рис. 5.1).

        Args:
            T_s: период собственный (с)
            soil_type: категория грунта
            seismic_zone: балльность (5-9)

        Returns:
            Динамический коэффициент β(T)
        """
        # Коэффициент сейсмичности
        K1_map = {5: 0.25, 6: 0.25, 7: 0.5, 8: 0.75, 9: 1.0}
        K1 = K1_map.get(seismic_zone, 0.5)

        # Плато спектра (T1 = 0.1с, T2 зависит от грунта)
        T2_map = {"I": 0.3, "II": 0.4, "III": 0.5, "IV": 0.6, "V": 0.7}
        T2 = T2_map.get(soil_type, 0.4)

        beta_max = 2.5

        if T_s <= 0.1:
            beta = 1.0 + 15 * T_s  # линейный рост
        elif T_s <= T2:
            beta = beta_max  # плато
        else:
            beta = beta_max * T2 / T_s  # гиперболическое убывание

        beta = max(0.8, min(beta_max, beta))

        return {
            "beta": round(beta, 3),
            "K1": K1,
            "seismic_zone": seismic_zone,
            "soil_type": soil_type,
            "T_s": T_s,
            "T1": 0.1,
            "T2": T2,
            "beta_max": beta_max,
            "norm": "СП 14.13330.2018 рис. 5.1",
        }

    @staticmethod
    def dynamic_amplification_factor(T_struct: float, T_load: float) -> dict:
        """
        Коэффициент динамичности.

        μ = 1 / √((1 - (T_load/T_struct)²)² + (2ξ × T_load/T_struct)²)

        Args:
            T_struct: период конструкции
            T_load: период нагрузки
            xi: коэффициент демпфирования (0.05 для steel)

        Returns:
            Коэффициент динамичности
        """
        xi = 0.05
        ratio = T_load / T_struct if T_struct > 0 else 0

        if ratio == 0:
            mu = 1.0
        else:
            denom = math.sqrt((1 - ratio**2) ** 2 + (2 * xi * ratio) ** 2)  # type: ignore[operator]
            mu = 1.0 / denom if denom > 0 else 10.0

        mu = min(mu, 10.0)  # ограничение

        return {
            "mu": round(mu, 3),
            "T_struct_s": T_struct,
            "T_load_s": T_load,
            "ratio": round(ratio, 3),
            "is_resonance": 0.7 < ratio < 1.3,
            "norm": "СП 20.13330.2016 п.8.4",
        }


# ═══════════════════════════════════════════════════════════════
# РАСЧЁТ ОСНОВАНИЙ (СП 22.13330, СП 24.13330)
# ═══════════════════════════════════════════════════════════════


class FoundationAnalyzer:
    """
    Расчёт оснований и фундаментов.

    СП 22.13330.2016 — Основания зданий и сооружений
    СП 24.13330.2011 — Свайные фундаменты
    """

    @staticmethod
    def bearing_capacity_sand(soil_type: str, depth_m: float, width_m: float) -> dict:
        """
        Несущая способность песчаного основания (СП 22 п.5.6).

        R = k1 × (b1 × γ × Nγ + γd × d × Nq) × k2

        Args:
            soil_type: тип грунта
            depth_m: глубина заложения (м)
            width_m: ширина фундамента (м)

        Returns:
            Расчётное сопротивление основания
        """
        soil = SOIL_TYPES.get(soil_type, SOIL_TYPES["III"])

        # Таблица коэффициентов (СП 22 табл. 6.1 — упрощённо)
        Nq_map = {"I": 20, "II": 10, "III": 5, "IV": 3, "V": 2}
        Ng_map = {"I": 15, "II": 5, "III": 2, "IV": 1, "V": 0.5}

        Nq: float = float(Nq_map.get(soil_type, 5))  # type: ignore[operator]
        Ng: float = float(Ng_map.get(soil_type, 2))  # type: ignore[operator]
        gamma: float = float(str(soil["gamma_kN_m3"]))  # type: ignore[operator]

        # k1 = 1 + 0.004 × (b - 1) для b > 1м
        k1: float = 1 + 0.004 * (width_m - 1) if width_m > 1 else 1.0
        k2: float = 1.0  # для γ_f = 1

        R_kPa: float = k1 * (0.5 * width_m * gamma * Ng + gamma * depth_m * Nq) * k2  # type: ignore[operator]

        return {
            "R_kPa": round(R_kPa, 1),
            "R_MPa": round(R_kPa / 1000, 4),
            "soil_type": soil_type,
            "depth_m": depth_m,
            "width_m": width_m,
            "gamma_kN_m3": gamma,
            "Nq": Nq,
            "Ng": Ng,
            "norm": "СП 22.13330.2016 п.5.6",
        }

    @staticmethod
    def settlement_estimate(R_kPa: float, E0_MPa: float, B_m: float, load_kPa: float) -> dict:
        """
        Оценка осадки фундамента (СП 22 п.5.11).

        s = (σ × B) / (E0 × k)

        Args:
            R_kPa: расчётное сопротивление (кПа)
            E0_MPa: модуль деформации грунта (МПа)
            B_m: ширина фундамента (м)
            load_kPa: фактическое давление (кПа)

        Returns:
            Оценка осадки
        """
        k = 0.8  # коэффициент (зависит от формы фундамента)

        s_mm = (load_kPa * B_m) / (E0_MPa * 1000 * k) * 1000

        # Предельные осадки (СП 22 табл. 12.2)
        s_limit_mm = 80  # для обычных зданий

        return {
            "settlement_mm": round(s_mm, 2),
            "settlement_limit_mm": s_limit_mm,
            "passed": s_mm <= s_limit_mm,
            "load_kPa": load_kPa,
            "R_kPa": R_kPa,
            "load_to_R_ratio": round(load_kPa / R_kPa, 3) if R_kPa > 0 else 0,
            "norm": "СП 22.13330.2016 п.5.11",
        }

    @staticmethod
    def pile_capacity(diameter_m: float, length_m: float, soil_type: str, pile_type: str = "bored") -> dict:
        """
        Несущая способность сваи (СП 24 п.7.4).

        Fd = (γc × R × A_base + γc × u × fi × hi) / γk

        Args:
            diameter_m: диаметр сваи (м)
            length_m: длина сваи (м)
            soil_type: тип грунта
            pile_type: тип сваи ('bored', 'driven', 'screw')

        Returns:
            Несущая способность сваи
        """
        soil = SOIL_TYPES.get(soil_type, SOIL_TYPES["III"])

        # Площадь подошвы
        A_base = math.pi * diameter_m**2 / 4

        # Периметр сваи
        u = math.pi * diameter_m

        # Сопротивление грунта по боковой поверхности (СП 24 табл. 7.2)
        fi_map = {"I": 80, "II": 40, "III": 25, "IV": 20, "V": 12}
        fi = fi_map.get(soil_type, 25)  # кПа

        # Сопротивление по подошве (СП 24 табл. 7.1)
        R_base_map = {"I": 5000, "II": 2500, "III": 1500, "IV": 800, "V": 400}
        R_base = R_base_map.get(soil_type, 1500)  # кПа

        gamma_c = 1.0  # коэффициент условий работы
        gamma_k = 1.4  # коэффициент надёжности

        F_base = gamma_c * R_base * A_base / gamma_k
        F_skin = gamma_c * u * fi * length_m / gamma_k
        Fd = F_base + F_skin

        return {
            "pile_capacity_kN": round(Fd, 1),
            "base_component_kN": round(F_base, 1),
            "skin_component_kN": round(F_skin, 1),
            "diameter_m": diameter_m,
            "length_m": length_m,
            "soil_type": soil_type,
            "pile_type": pile_type,
            "norm": "СП 24.13330.2011 п.7.4",
        }

    @staticmethod
    def pile_spacing(diameter_m: float, pile_type: str = "bored") -> dict:
        """
        Минимальное расстояние между сваями (СП 24 п.6.12).

        s ≥ 3d (для забивных)
        s ≥ 3.5d (для буронабивных)

        Args:
            diameter_m: диаметр сваи (м)
            pile_type: тип сваи

        Returns:
            Минимальное расстояние
        """
        k = 3.5 if pile_type == "bored" else 3.0
        s_min = k * diameter_m

        return {
            "min_spacing_m": round(s_min, 2),
            "diameter_m": diameter_m,
            "pile_type": pile_type,
            "coefficient": k,
            "norm": "СП 24.13330.2011 п.6.12",
        }


# ═══════════════════════════════════════════════════════════════
# УСТОЙЧИВОСТЬ
# ═══════════════════════════════════════════════════════════════


class StabilityAnalyzer:
    """
    Проверка устойчивости конструкций.

    СП 16.13330.2017 раздел 7 — устойчивость стержней
    """

    @staticmethod
    def effective_length_factor(boundary_conditions: str) -> dict:
        """
        Коэффициент расчётной длины μ (СП 16 табл. 7.2).

        Args:
            boundary_conditions: тип закрепления ('pin-pin', 'fix-fix', 'fix-pin', 'cantilever')

        Returns:
            Коэффициент μ и L_eff = μ × L
        """
        mu_table = {
            "pin-pin": {"mu": 1.0, "description": "Шарнир-Шарнир"},
            "fix-fix": {"mu": 0.5, "description": "Заделка-Заделка"},
            "fix-pin": {"mu": 0.7, "description": "Заделка-Шарнир"},
            "cantilever": {"mu": 2.0, "description": "Консоль"},
            "fix-free": {"mu": 2.0, "description": "Заделка-Свободный конец"},
        }

        data = mu_table.get(boundary_conditions, mu_table["pin-pin"])

        return {
            "mu": data["mu"],
            "description": data["description"],
            "formula": "L_eff = μ × L",
            "norm": "СП 16.13330.2017 табл. 7.2",
        }

    @staticmethod
    def lateral_torsional_buckling(
        E_MPa: float, G_MPa: float, Iy_m4: float, It_m4: float, Iw_m6: float, L_m: float, h_m: float
    ) -> dict:
        """
        Потеря устойчивости балки при изгибе (СП 16 п.8.4).

        M_cr = (π/L) × √(E × Iy × G × It + (π²/L²) × E² × Iw × Iy)

        Args:
            E_MPa, G_MPa: модули упругости
            Iy_m4: момент инерции слабой оси
            It_m4: момент кручения
            Iw_m6: секториальный момент инерции
            L_m: расчётная длина
            h_m: высота сечения

        Returns:
            Критический момент и проверка
        """
        term1 = math.pi**2 / L_m**2 * E_MPa * 1e6 * Iy_m4 * G_MPa * 1e6 * It_m4
        term2 = (math.pi**2 / L_m**2) ** 2 * (E_MPa * 1e6) ** 2 * Iw_m6 * Iy_m4

        M_cr = (math.pi / L_m) * math.sqrt(max(0, term1 + term2))

        return {
            "M_cr_kNm": round(M_cr / 1000, 2),
            "L_m": L_m,
            "E_MPa": E_MPa,
            "G_MPa": G_MPa,
            "norm": "СП 16.13330.2017 п.8.4",
        }

    @staticmethod
    def p_delta_effect(N_kN: float, delta_m: float, stiffness_N_m: float) -> dict:
        """
        Эффект P-Δ (СП 16 п.7.3).

        Δ_total = Δ_0 / (1 - N/N_cr)

        Args:
            N_kN: осевая сила (кН)
            delta_m: начальный эксцентриситет (м)
            stiffness_N_m: жёсткость (Н/м)

        Returns:
            Усиленный прогиб и коэффициент
        """
        N = N_kN * 1000
        N_cr = stiffness_N_m * delta_m if delta_m > 0 else float("inf")

        if N_cr <= N:
            return {
                "error": "N ≥ N_cr — конструкция неустойчива!",
                "N_kN": N_kN,
                "N_cr_kN": round(N_cr / 1000, 2),
            }

        amplification = 1 / (1 - N / N_cr)
        delta_total = delta_m * amplification

        return {
            "delta_initial_mm": round(delta_m * 1000, 2),
            "delta_total_mm": round(delta_total * 1000, 2),
            "amplification_factor": round(amplification, 3),
            "N_kN": N_kN,
            "N_cr_kN": round(N_cr / 1000, 2),
            "utilization_N_Ncr": round(N / N_cr, 3),
            "norm": "СП 16.13330.2017 п.7.3",
        }


# ═══════════════════════════════════════════════════════════════
# ОБЪЕДИНЁННЫЙ ДВИЖОК (FACADE)
# ═══════════════════════════════════════════════════════════════


class StructuralEngine:
    """
    Объединённый движок структурного анализа.

    Предоставляет единый интерфейс ко всем подсистемам:
      - FEMSolver — расчёт МКЭ
      - MemberChecker — проверка элементов
      - LoadCombiner — комбинации нагрузок
      - DynamicsAnalyzer — динамика и сейсмика
      - FoundationAnalyzer — основания
      - StabilityAnalyzer — устойчивость
      - SectionDatabase — база сечений
    """

    def __init__(self):
        self.fem = FEMSolver()
        self.checker = MemberChecker()
        self.loads = LoadCombiner()
        self.dynamics = DynamicsAnalyzer()
        self.foundation = FoundationAnalyzer()
        self.stability = StabilityAnalyzer()
        self.sections = SectionDatabase()

    def full_building_analysis(self, params: dict) -> dict:
        """
        Полный расчёт здания — все проверки.

        Args:
            params: словарь параметров здания:
                - width_m, length_m, height_m, floors
                - material (brick, concrete, steel, wood)
                - steel_grade, concrete_class
                - soil_type, foundation_type
                - seismic_zone
                - loads (dead, live, snow, wind)

        Returns:
            Полный отчёт со всеми проверками
        """
        results: dict = {
            "input_params": params,
            "checks": {},
            "summary": {},
            "warnings": [],
        }

        # 1. Комбинации нагрузок
        dead = params.get("dead_load_kN_m2", 5.0)
        live = params.get("live_load_kN_m2", 2.0)
        snow = params.get("snow_load_kN_m2", 1.8)
        wind = params.get("wind_load_kN_m2", 0.4)

        results["checks"]["load_combinations"] = self.loads.basic_combination(dead, live, snow, wind)

        # 2. Проверка прогиба балки (пример — центральная балка)
        L = params.get("length_m", 12)
        E = 206000 if params.get("material") == "steel" else 30000
        I = params.get("beam_I_m4", 0.0001)

        # Прогиб от равномерно распределённой нагрузки: 5qL⁴/(384EI)
        q = (dead + live) * 1000  # Н/м²
        span = L
        delta = 5 * q * span**4 / (384 * E * 1e6 * I) if I > 0 else 0

        results["checks"]["deflection"] = self.checker.deflection_check(L, delta, limit_ratio=250)

        # 3. Сейсмический анализ
        seismic_zone = params.get("seismic_zone", 0)
        if seismic_zone > 0:
            mass = params.get("total_mass_kg", 50000)
            T = params.get("period_s", 0.5)
            results["checks"]["seismic"] = self.dynamics.seismic_force(mass)
            results["checks"]["response_spectrum"] = self.dynamics.response_spectrum(
                T, soil_type=params.get("soil_type", "II"), seismic_zone=seismic_zone
            )

        # 4. Основание
        soil = params.get("soil_type", "III")
        width = params.get("width_m", 10)
        foundation_depth = params.get("foundation_depth_m", 1.2)

        results["checks"]["foundation"] = self.foundation.bearing_capacity_sand(soil, foundation_depth, width)

        # 5. Сводка
        all_passed = True
        for check_name, check_data in results["checks"].items():
            if isinstance(check_data, dict):
                if check_data.get("passed") is False:
                    all_passed = False
                    results["warnings"].append(f"❌ {check_name}: не пройдено")

        results["summary"] = {
            "all_passed": all_passed,
            "checks_count": len(results["checks"]),
            "warnings_count": len(results["warnings"]),
        }

        return results

    def get_section(self, section_type: str, designation: str) -> dict | None:
        """Получить параметры сечения из базы."""
        if section_type == "i_beam":
            return self.sections.get_i_beam(designation)
        elif section_type == "channel":
            return self.sections.get_channel(designation)
        elif section_type == "rect_tube":
            return self.sections.get_rect_tube(designation)
        return None
