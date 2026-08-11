# API Test Report

| Тест | Промт | Статус | Ответ |
|------|-------|:------:|-------|
| Parse Дом | дом 2 этажа кирпич 10x12 | ✅ | type=building, floors=2, material=brick |
| Parse Офис | офис 5 этажей стекло 20x24 | ✅ | type=building, floors=5, material=glass |
| Parse Коттедж | коттедж 12x15 дерево терраса | ✅ | type=building, floors=2, material=plaster |
| Parse Интерьер | ванная с джакузи мрамор | ✅ | type=interior, floors=1, material=marble |
| Parse Ландшафт | ландшафтный дизайн сад с бассейном | ✅ | type=building, floors=2, material=plaster |

**5/5 passed**
