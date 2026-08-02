"""
Тест интеграции нормативов и структурного анализа в AI_Arhitector.
Запуск: cd AI_Arhitector_test && python test_integration.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

print("=" * 60)
print("ТЕСТ ИНТЕГРАЦИИ НОРМАТИВОВ v9.2")
print("=" * 60)

errors = []

# ═══ ТЕСТ 1: Импорт norms_reference ═══
print("\n[1/8] Импорт norms_reference...")
try:
    from shared.norms_reference import (
        SP_DATABASE, GOST_DATABASE, FZ_DATABASE,
        get_applicable_norms, get_norm_details, search_norms
    )
    print(f"  ✅ SP_DATABASE: {len(SP_DATABASE)} записей")
    print(f"  ✅ GOST_DATABASE: {len(GOST_DATABASE)} записей")
    print(f"  ✅ FZ_DATABASE: {len(FZ_DATABASE)} записей")
    
    # Проверка поиска
    results = search_norms("сейсмика")
    print(f"  ✅ search_norms('сейсмика'): {len(results)} результатов")
    
    # Проверка применимости
    norms = get_applicable_norms("office", 5, 18.0, "concrete")
    print(f"  ✅ get_applicable_norms(office, 5 этажей): {len(norms)} нормативов")
except Exception as e:
    errors.append(f"norms_reference: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 2: Импорт structural_analysis ═══
print("\n[2/8] Импорт structural_analysis...")
try:
    from shared.structural_analysis import (
        FEMSolver, MemberChecker, LoadCombiner, 
        SectionDatabase, DynamicsAnalyzer, FoundationAnalyzer,
        StabilityAnalyzer, StructuralEngine,
        CONCRETE_CLASSES, STEEL_GRADES, SOIL_TYPES
    )
    print(f"  ✅ FEMSolver импортирован")
    print(f"  ✅ MemberChecker импортирован")
    print(f"  ✅ LoadCombiner импортирован")
    print(f"  ✅ SectionDatabase: {len(SectionDatabase.I_BEAMS)} двутавров, {len(SectionDatabase.CHANNELS)} швеллеров")
    print(f"  ✅ CONCRETE_CLASSES: {len(CONCRETE_CLASSES)} классов")
    print(f"  ✅ STEEL_GRADES: {len(STEEL_GRADES)} марок")
except Exception as e:
    errors.append(f"structural_analysis: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 3: МКЭ — балка 6м, равномерная нагрузка ═══
print("\n[3/8] МКЭ: консольная балка 6м, F=10кН на конце...")
try:
    import numpy as np
    solver = FEMSolver()
    
    E = 206000e6  # 206 ГПа → Па
    A = 0.01      # 100 см²
    I = 8.36e-5   # двутавр 20
    L = 6.0
    
    # Два элемента по 3м
    k1 = solver.beam_element_stiffness(E, A, I, 3.0)
    k2 = solver.beam_element_stiffness(E, A, I, 3.0)
    
    print(f"  ✅ Матрица жёсткости элемента: {k1.shape}")
    
    # Сборка (3 узла: 0, 3, 6м)
    elements = [
        {'E': E, 'A': A, 'I': I, 'L': 3.0, 'nodes': [0, 1]},
        {'E': E, 'A': A, 'I': I, 'L': 3.0, 'nodes': [1, 2]},
    ]
    K = solver.assemble_global_stiffness(elements, n_nodes=3)
    print(f"  ✅ Глобальная матрица: {K.shape}")
    
    # Нагрузка на конец: F=10кН вниз
    # DOF: узел0=[0,1,2], узел1=[3,4,5], узел2=[6,7,8]
    # v на узле 2 = индекс 7
    F = np.zeros(9)
    F[7] = -10000  # v на узле 2 (конец консоли)
    
    # Закрепляем узел 0 (все 3 DOF)
    K_red, F_red, free = solver.apply_boundary_conditions(K, F, [0, 1, 2])
    u_red = solver.solve(K_red, F_red)
    u = solver.recover_full_displacements(u_red, free, 9)
    
    # Прогиб на конце
    delta = u[7]  # v на узле 2
    delta_theory = 10000 * 6**3 / (3 * E * I)
    
    print(f"  ✅ Прогиб на конце: {delta*1000:.2f} мм (теория: {delta_theory*1000:.2f} мм)")
    print(f"  ✅ Отклонение от теории: {abs(abs(delta) - delta_theory)/delta_theory*100:.1f}%")
except Exception as e:
    errors.append(f"FEM: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 4: Комбинации нагрузок ═══
print("\n[4/8] Комбинации нагрузок (СП 20.13330)...")
try:
    combiner = LoadCombiner()
    combo = combiner.basic_combination(dead_kN=50, live_kN=30, snow_kN=15, wind_kN=8)
    print(f"  ✅ Основная комбинация: {combo['total_with_snow_wind_kN']} кН")
    print(f"     Постоянная: {combo['dead_component_kN']} кН (γ={combo['gamma_f_dead']})")
    print(f"     Временная: {combo['live_component_kN']} кН (γ={combo['gamma_f_live']})")
    print(f"     Снег: {combo['snow_component_kN']} кН (γ={combo['gamma_f_snow']})")
    
    seismic = combiner.seismic_combination(dead_kN=50, live_kN=30, seismic_kN=25)
    print(f"  ✅ Сейсмическая: {seismic['total_kN']} кН")
except Exception as e:
    errors.append(f"LoadCombiner: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 5: Проверка стальной балки ═══
print("\n[5/8] Проверка стальной балки (СП 16.13330)...")
try:
    checker = MemberChecker()
    
    # Двутавр 30, сталь C345
    beam = SectionDatabase.get_i_beam("30")
    print(f"  📋 Двутавр 30: h={beam['h']}мм, Ix={beam['Ix_cm4']}см⁴, Wx={beam['Wx_cm3']}см³")
    
    Wx_m3 = beam['Wx_cm3'] * 1e-6  # см³ → м³
    bending = checker.steel_beam_bending(Wx_m3, 345)
    print(f"  ✅ M_Rd = {bending['M_Rd_kNm']} кН·м")
    
    # Прогиб
    L = 6.0
    delta = L / 300  # пример
    defl = checker.deflection_check(L, delta, 250)
    print(f"  ✅ Прогиб: {defl['delta_actual_mm']}мм ≤ {defl['delta_limit_mm']}мм → {'✅' if defl['passed'] else '❌'}")
    
    # ЖБ балка
    rc = checker.rc_beam_flexure(b_m=0.3, h_m=0.5, d_m=0.45, 
                                  concrete_class="B25", rebar_class="A500", M_kNm=80)
    print(f"  ✅ ЖБ балка: As={rc['A_s_final_mm2']}мм², μ={rc['mu']}")
    if rc.get("bar_options"):
        print(f"     Подбор: ∅{rc['bar_options'][0]['diameter_mm']}×{rc['bar_options'][0]['count']} шт")
except Exception as e:
    errors.append(f"MemberChecker: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 6: Сейсмика ═══
print("\n[6/8] Сейсмический анализ (СП 14.13330)...")
try:
    dynamics = DynamicsAnalyzer()
    
    spectrum = dynamics.response_spectrum(T_s=0.5, soil_type="II", seismic_zone=7)
    print(f"  ✅ Спектр реакции: β={spectrum['beta']}, K1={spectrum['K1']}")
    
    force = dynamics.seismic_force(mass_kg=100000, K1=0.5, beta=spectrum['beta'])
    print(f"  ✅ Сейсмическая сила: {force['seismic_force_kN']} кН")
    
    freq = dynamics.natural_frequency_rayleigh(stiffness_N_m=5e6, mass_kg=50000)
    print(f"  ✅ Собственная частота: {freq['frequency_Hz']} Гц, период: {freq['period_s']} с")
except Exception as e:
    errors.append(f"Dynamics: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 7: Основания ═══
print("\n[7/8] Расчёт основания (СП 22.13330)...")
try:
    foundation = FoundationAnalyzer()
    
    bearing = foundation.bearing_capacity_sand("III", depth_m=1.5, width_m=10)
    print(f"  ✅ Несущая способность грунта III: R={bearing['R_kPa']} кПа")
    
    settlement = foundation.settlement_estimate(bearing['R_kPa'], 8, 10, 120)
    print(f"  ✅ Осадка: {settlement['settlement_mm']}мм ≤ {settlement['settlement_limit_mm']}мм → {'✅' if settlement['passed'] else '❌'}")
    
    pile = foundation.pile_capacity(diameter_m=0.3, length_m=6, soil_type="III")
    print(f"  ✅ Несущая способность сваи ∅300, L=6м: {pile['pile_capacity_kN']} кН")
except Exception as e:
    errors.append(f"Foundation: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ТЕСТ 8: ComplianceChecker ═══
print("\n[8/8] Полная проверка соответствия...")
try:
    from shared.compliance import ComplianceChecker
    
    checker = ComplianceChecker()
    
    params = {
        "building_type": "office",
        "material": "concrete",
        "floors": 5,
        "width_m": 20,
        "length_m": 30,
        "height_m": 3.2,
        "has_elevator": True,
        "foundation_type": "pile",
        "soil_type": "III",
        "seismic_zone": 7,
        "material_concrete_class": "B30",
        "steel_grade": "C345",
        "heating_type": "autonomous",
        "ventilation_type": "mechanical",
        "water_supply": "central",
        "sewage": "central",
    }
    
    bp = {
        "floors": 5, "W": 20, "L": 30, "fH": 3.2,
        "mat": "concrete",
        "rooms": [
            {"n": "Офис 1", "tag": "l", "a": 45, "w": 6, "d": 7.5},
            {"n": "Коридор", "tag": "h", "a": 30, "w": 1.8, "d": 16.7},
        ],
    }
    
    result = checker.check_building(params, bp)
    
    print(f"  ✅ Проверок запущено: {len(result.checks_run)}")
    print(f"  ✅ Пройдено: {result.passed}")
    print(f"  ✅ Оценка: {result.score:.2f}")
    print(f"  ✅ Ошибок: {len(result.issues)}")
    print(f"  ✅ Предупреждений: {len(result.warnings)}")
    
    print(f"\n  Категории проверок:")
    for check in result.checks_run:
        print(f"    - {check}")
    
    if result.issues:
        print(f"\n  ❌ Ошибки:")
        for issue in result.issues:
            print(f"    [{issue.code}] {issue.message}")
    
    if result.warnings:
        print(f"\n  ⚠️ Предупреждения (первые 5):")
        for w in result.warnings[:5]:
            print(f"    [{w.code}] {w.message}")
            if w.fix:
                print(f"      → Исправление: {w.fix}")
except Exception as e:
    errors.append(f"ComplianceChecker: {e}")
    print(f"  ❌ Ошибка: {e}")

# ═══ ИТОГО ═══
print("\n" + "=" * 60)
if errors:
    print(f"❌ ОШИБОК: {len(errors)}")
    for e in errors:
        print(f"  - {e}")
else:
    print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО")
print("=" * 60)
