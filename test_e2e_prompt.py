"""
E2E тест: промт → парсинг → проверка нормативами → отчёт.
Симулирует реальный пайплайн AI_Arhitector.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from shared.norms_reference import get_applicable_norms, get_norm_details, search_norms
from shared.structural_analysis import (
    StructuralEngine, MemberChecker, LoadCombiner, 
    SectionDatabase, DynamicsAnalyzer, FoundationAnalyzer
)
from shared.compliance import ComplianceChecker

print("=" * 70)
print("E2E ТЕСТ: ПРОМТ → НОРМАТИВЫ → РАСЧЁТ → ОТЧЁТ")
print("=" * 70)

# ═══ СИМУЛЯЦИЯ ПАРСИНГА ПРОМТА ═══
# Промт: "Построй 5-этажный офис из монолитного железобетона 
#          в 7-балльной сейсмической зоне, свайный фундамент"

parsed_params = {
    "object_type": "building",
    "building_type": "office",
    "floors": 5,
    "width_m": 24,
    "length_m": 36,
    "height_m": 3.2,
    "material": "concrete",
    "style": "modern",
    "roof_type": "flat",
    "features": ["elevator", "parking"],
    "confidence": 0.95,
    
    # Конструктивные параметры (из расширенного промта)
    "structural_system": "frame",
    "foundation_type": "pile",
    "material_concrete_class": "B30",
    "steel_grade": "C345",
    "seismic_zone": "7",
    "soil_type": "III",
    "fire_resistance_rating": "R60",
    "heating_type": "autonomous",
    "ventilation_type": "mechanical",
    "water_supply": "central",
    "sewage": "central",
    "exposure_class": "XC1",
}

building_params = {
    "floors": 5, "W": 24, "L": 36, "fH": 3.2,
    "mat": "concrete", "wall_thickness": 0.3,
    "rooms": [
        {"n": "Офис 1 этаж", "tag": "l", "a": 200, "w": 12, "d": 16.7},
        {"n": "Коридор", "tag": "h", "a": 86, "w": 2.0, "d": 43},
        {"n": "Лестничная", "tag": "h", "a": 20, "w": 2.5, "d": 8},
        {"n": "Лифтовая", "tag": "h", "a": 6, "w": 2, "d": 3},
        {"n": "Санузел", "tag": "bath", "a": 12, "w": 3, "d": 4},
    ],
}

print("\n📋 РАСПАРСЕННЫЕ ПАРАМЕТРЫ:")
for k, v in parsed_params.items():
    print(f"  {k}: {v}")

# ═══ ШАГ 1: ОПРЕДЕЛЕНИЕ ПРИМЕНИМЫХ НОРМАТИВОВ ═══
print("\n" + "─" * 70)
print("📖 ШАГ 1: ПРИМЕНИМЫЕ НОРМАТИВЫ")
print("─" * 70)

norms = get_applicable_norms("office", 5, 16.0, "concrete")
print(f"\nНайдено {len(norms)} применимых нормативов:\n")
for n in norms:
    print(f"  📌 {n['code']} — {n['full_name']}")
    print(f"     Категория: {n.get('category', '?')}")

# ═══ ШАГ 2: СТРУКТУРНЫЙ АНАЛИЗ ═══
print("\n" + "─" * 70)
print("🔧 ШАГ 2: СТРУКТУРНЫЙ АНАЛИЗ")
print("─" * 70)

engine = StructuralEngine()

# Комбинации нагрузок
combo = engine.loads.basic_combination(dead_kN=120, live_kN=80, snow_kN=35, wind_kN=15)
print(f"\n📊 Комбинации нагрузок (СП 20.13330):")
print(f"  Постоянная: {combo['dead_component_kN']} кН (γ={combo['gamma_f_dead']})")
print(f"  Временная:  {combo['live_component_kN']} кН (γ={combo['gamma_f_live']})")
print(f"  Снег:       {combo['snow_component_kN']} кН (γ={combo['gamma_f_snow']})")
print(f"  Ветер:      {combo['wind_component_kN']} кН (γ×ψ={combo['gamma_f_wind']}×{combo['psi_0_wind']})")
print(f"  ИТОГО ППУ:  {combo['total_with_snow_wind_kN']} кН")

# Сейсмика
seismic = engine.dynamics.response_spectrum(T_s=0.6, soil_type="III", seismic_zone=7)
force = engine.dynamics.seismic_force(mass_kg=200000, K1=0.5, beta=seismic["beta"])
print(f"\n🌍 Сейсмический анализ (СП 14.13330):")
print(f"  Зона: 7 баллов, грунт III категории")
print(f"  Спектр реакции: β={seismic['beta']}, K1={seismic['K1']}")
print(f"  Сейсмическая сила: {force['seismic_force_kN']} кН")

combo_seismic = engine.loads.seismic_combination(dead_kN=120, live_kN=80, seismic_kN=force["seismic_force_kN"])
print(f"  Комбинация при сейсмике: {combo_seismic['total_kN']} кН")

# Основание
bearing = engine.foundation.bearing_capacity_sand("III", depth_m=2.0, width_m=1.2)
pile = engine.foundation.pile_capacity(diameter_m=0.4, length_m=8, soil_type="III")
spacing = engine.foundation.pile_spacing(0.4)
print(f"\n🏗 Основание (СП 22/24):")
print(f"  Несущая способность грунта: R={bearing['R_kPa']} кПа")
print(f"  Свая ∅400, L=8м: {pile['pile_capacity_kN']} кН")
print(f"    Опорная часть: {pile['base_component_kN']} кН")
print(f"    Боковая: {pile['skin_component_kN']} кН")
print(f"  Мин. расстояние между сваями: {spacing['min_spacing_m']}м")

# Прогиб балки
section = SectionDatabase.get_i_beam("30")
if section:
    Wx_m3 = section['Wx_cm3'] * 1e-6
    bending = engine.checker.steel_beam_bending(Wx_m3, 345)
    defl = engine.checker.deflection_check(6.0, 0.015, 250)
    print(f"\n📐 Проверка балки (двутавр 30, C345):")
    print(f"  M_Rd = {bending['M_Rd_kNm']} кН·м")
    print(f"  Прогиб: {defl['delta_actual_mm']}мм ≤ {defl['delta_limit_mm']}мм → {'✅' if defl['passed'] else '❌'}")

# ЖБ расчёт
rc = engine.checker.rc_beam_flexure(b_m=0.4, h_m=0.6, d_m=0.55,
                                     concrete_class="B30", rebar_class="A500", M_kNm=200)
print(f"\n🧱 ЖБ балка (СП 63.13330):")
print(f"  B30 (f_b={rc.get('f_b_MPa','?')} МПа), A500 (f_y={rc.get('f_y_MPa','?')} МПа)")
print(f"  M = 200 кН·м")
print(f"  μ = {rc['mu']}, ξ = {rc.get('xi','?')}")
print(f"  As = {rc['A_s_final_mm2']} мм²")
if rc.get("bar_options"):
    print(f"  Подбор: ∅{rc['bar_options'][0]['diameter_mm']}×{rc['bar_options'][0]['count']} шт (A={rc['bar_options'][0]['total_area_mm2']}мм²)")

# ═══ ШАГ 3: ПРОВЕРКА СООТВЕТСТВИЯ ═══
print("\n" + "─" * 70)
print("✅ ШАГ 3: ПРОВЕРКА СООТВЕТСТВИЯ НОРМАТИВАМ")
print("─" * 70)

checker = ComplianceChecker()
result = checker.check_building(parsed_params, building_params)

print(f"\n📊 ОБЩИЙ РЕЗУЛЬТАТ:")
print(f"  Проверок: {len(result.checks_run)}")
print(f"  Оценка: {result.score:.0%}")
print(f"  Ошибок: {len(result.issues)}")
print(f"  Предупреждений: {len(result.warnings)}")

if result.issues:
    print(f"\n❌ ОШИБКИ:")
    for i in result.issues:
        print(f"  [{i.code}] {i.message}")
        print(f"    → {i.fix} ({i.standard})")

if result.warnings:
    print(f"\n⚠️ ПРЕДУПРЕЖДЕНИЯ:")
    for w in result.warnings:
        print(f"  [{w.code}] {w.message}")
        if w.fix:
            print(f"    → {w.fix}")

# ═══ ШАГ 4: ОТЧЁТ ДЛЯ ПОЛЬЗОВАТЕЛЯ ═══
print("\n" + "=" * 70)
print("📋 ИТОГОВЫЙ ОТЧЁТ ДЛЯ ПОЛЬЗОВАТЕЛЯ")
print("=" * 70)

print(f"""
🏠 Объект: 5-этажный офис, 24×36м, монолитный ЖБ
📍 Условия: 7-балльная сейсмика, грунт III категории, свайный фундамент

📊 ОЦЕНКА СООТВЕТСТВИЯ: {result.score:.0%}

Применённые нормативы ({len(norms)} шт):
""")
for n in norms[:8]:
    print(f"  • {n['code']} — {n['full_name']}")
if len(norms) > 8:
    print(f"  ... и ещё {len(norms)-8}")

print(f"""
🔧 Конструктивные решения:
  • Система: каркасная (СП 63, СП 16)
  • Бетон: B30, арматура: A500
  • Сваи: ∅400мм, L=8м, шаг ≥1.4м
  • Огнестойкость: REI 120 (бетон, >3 этажей)
  • Сейсмика: β={seismic['beta']}, E={force['seismic_force_kN']}кН

⚠️ Требует внимания:
""")
for w in result.warnings[:5]:
    print(f"  • {w.message}")
    if w.fix:
        print(f"    → {w.fix}")

print(f"""
✅ Рекомендации:
  1. Проверить ширину лестничного марша ≥1.2м
  2. Разделить на пожарные отсеки (площадь 3000м² > 2500м²)
  3. Обеспечить пандус на входе (уклон ≤ 1:12)
  4. Проектировать приточно-вытяжную вентиляцию
  5. Установить автоматическую систему пожаротушения
""")

print("=" * 70)
print("✅ E2E ТЕСТ ЗАВЕРШЁН УСПЕШНО")
print("=" * 70)
