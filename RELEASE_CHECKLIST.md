# RELEASE CHECKLIST — ОБЯЗАТЕЛЬНО ПЕРЕД КАЖДЫМ РЕЛИЗОМ

## ⚠️ НИКОГДА НЕ РЕЛИЗИТЬ БЕЗ ЭТИХ ТЕСТОВ

### 1. Send Button Test (CRITICAL)
```bash
python3 -m pytest tests/test_send_button.py -v
```
**Должно быть: 18/18 passed.** Если хоть один упал — РЕЛИЗ ЗАПРЕЩЁН.

Что проверяет:
- Frontend загружается (HTTP 200)
- Кнопка отправки работает (onclick='send()')
- Enter отправляет промт
- Поле ввода существует (id='ci')
- Быстрые кнопки работают (Дом, Офис, Коттедж)
- Three.js загружен
- Нет синтаксических ошибок в JS
- Live генерация: здание → валидный GLB
- Live генерация: интерьер → валидный GLB
- Live генерация: отель → валидный GLB

### 2. Full Test Suite
```bash
python3 -m pytest tests/ --ignore=tests/test_gateway.py --ignore=tests/test_e2e.py -q
```
**Должно быть: 362+ passed.**

### 3. Visual Screenshot Tests
```bash
python3 -m pytest tests/test_e2e_screenshots.py -v
```
**Должно быть: 97+ passed.**

### 4. Service Health Check
```bash
curl -s https://architect-gateway.onrender.com/health
curl -s https://ai-arch-blender3d.onrender.com/health
curl -s https://architect-blender.onrender.com/health
curl -s https://architect-llm-1s1j.onrender.com/health
```
**Все должны вернуть HTTP 200.**

### 5. Browser Test (MANUAL)
- Открыть https://architect-gateway.onrender.com
- Ввести "дом 2 этажа кирпич 10x12" в поле ввода
- Нажать Enter или кнопку ➤
- Должна появиться 3D-модель дома
- Проверить: быстрые кнопки работают, поле ввода не заблокировано

---

## Порядок релиза
1. Все тесты из п.1-4 проходят
2. `git add -A && git commit -m "..."`
3. `git push origin main`
4. Проверить что сайт открывается и кнопка работает (п.5)
5. Если что-то не работает — ОТКАТИТЬ немедленно

## Если сломал кнопку отправки
```bash
git revert HEAD
git push origin main
```
