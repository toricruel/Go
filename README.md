# Решения отборочного этапа Олимпиады СПбГУ «Petropolitan Science (Re)Search» (Вычислительные технологии)

В репозитории представлены решения трёх выбранных заданий по предметной области игры Го (вэйци):
1. **Задание 1.** Модуль правил: дамэ, взятие, легальность хода (17 баллов).
2. **Задание 2.** Решатель задач жизни и смерти с параллельным поиском (17 баллов).
3. **Задание 3.** Модуль разбора записи партии: реконструкция, взятия, подсчёт очков (16 баллов).

---

## Инструкция по сборке и запуску

Требования: **Python 3.10+** (используется исключительно стандартная библиотека Python, сторонние зависимости не требуются).

```bash
# Запуск полного набора автотестов по всем 3 заданиям
python3 test_all.py

# Задание 1: подсчёт дамэ отмеченной группы (задачи § 1 № 1–6)
python3 main.py sgf_testing_tasks/task001.sgf --mode dame

# Задание 1: проверка хода (метка Q) и список снятых камней (задачи § 1 № 7–12, § 2 № 13–24)
python3 main.py sgf_testing_tasks/task009.sgf --mode capture
python3 main.py sgf_testing_tasks/task013.sgf --mode legal

# Задание 2: решатель задач жизни и смерти (последовательный и параллельный режимы)
python3 main.py sgf_testing_tasks/task018.sgf --mode solve --workers 4 --output answer.txt

# Задание 2: запуск бенчмарка параллельного ускорения на наборе >= 20 позиций
python3 benchmark_parallel.py

# Задание 3: разбор записи партии и подсчёт итогового счёта (game01.sgf, game02.sgf, game03.sgf)
python3 main.py sgf_games/game01.sgf --mode game
python3 main.py sgf_games/game02.sgf --mode game
python3 main.py sgf_games/game03.sgf --mode game

# Задание 3: вывод снятых камней на конкретном ходу партии
python3 main.py sgf_games/game02.sgf --mode game --move-num 20