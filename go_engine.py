import re
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Dict, List, Set, Tuple, Optional, Any

EMPTY = "."
BLACK = "B"
WHITE = "W"


def opponent(color: str) -> str:
    return WHITE if color == BLACK else BLACK


def sgf_to_coords(coord_str: str, size: int) -> Optional[Tuple[int, int]]:
    """Переводит SGF-координату ('ci') в (row, col) с индексацией от 0 (col='c'->2, row='i'->8)."""
    if not coord_str or len(coord_str) < 2 or coord_str == "tt":
        return None
    col = ord(coord_str[0].lower()) - ord("a")
    row = ord(coord_str[1].lower()) - ord("a")
    if 0 <= row < size and 0 <= col < size:
        return (row, col)
    return None


def coords_to_sgf(row: int, col: int) -> str:
    """Переводит (row, col) в стандартную двухбуквенную SGF-координату."""
    return f"{chr(ord('a') + col)}{chr(ord('a') + row)}"


def parse_sgf_nodes(sgf_text: str) -> List[Dict[str, List[str]]]:
    """Парсит основную линию SGF-файла (FF[4], GM[1]) в список словарей свойств."""
    text = sgf_text.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    # Отсекаем боковые вариации, если они есть, оставляя основную линию
    depth = 0
    mainline = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            mainline.append(ch)
    clean_text = "".join(mainline)

    raw_nodes = clean_text.split(";")[1:]
    prop_re = re.compile(r"([A-Z]+)((?:\[[^\]]*\])+)")
    val_re = re.compile(r"\[([^\]]*)\]")

    nodes: List[Dict[str, List[str]]] = []
    for raw in raw_nodes:
        props: Dict[str, List[str]] = {}
        for match in prop_re.finditer(raw):
            key = match.group(1)
            vals = val_re.findall(match.group(2))
            props.setdefault(key, []).extend(vals)
        nodes.append(props)
    return nodes


class GoBoard:
    """Представление позиции Го: двумерная сетка + хеш истории для правила ко."""

    def __init__(self, size: int = 9):
        self.size: int = size
        self.grid: List[List[str]] = [[EMPTY for _ in range(size)] for _ in range(size)]
        self.turn: str = BLACK
        self.sq_points: Set[Tuple[int, int]] = set()
        self.labels: Dict[str, Tuple[int, int]] = {}
        self.prisoners: Dict[str, int] = {BLACK: 0, WHITE: 0}
        self.move_captures: List[Tuple[int, str, Optional[Tuple[int, int]], List[str]]] = []
        self.position_history: List[Tuple[Tuple[str, ...], ...]] = []
        self.ko_point: Optional[Tuple[int, int]] = None

    def snapshot_grid(self) -> Tuple[Tuple[str, ...], ...]:
        return tuple(tuple(row) for row in self.grid)

    def clone(self) -> "GoBoard":
        b = GoBoard(self.size)
        b.grid = [row[:] for row in self.grid]
        b.turn = self.turn
        b.sq_points = self.sq_points.copy()
        b.labels = self.labels.copy()
        b.prisoners = self.prisoners.copy()
        b.position_history = self.position_history[:]
        b.ko_point = self.ko_point
        return b

    @classmethod
    def from_sgf(cls, sgf_text: str, stop_before_Moves: bool = False) -> "GoBoard":
        nodes = parse_sgf_nodes(sgf_text)
        if not nodes:
            return cls(9)

        root = nodes[0]
        size = int(root.get("SZ", ["9"])[0])
        board = cls(size)

        for idx, node in enumerate(nodes):
            # Начальная расстановка AB / AW
            for pt_str in node.get("AB", []):
                pt = sgf_to_coords(pt_str, size)
                if pt:
                    board.grid[pt[0]][pt[1]] = BLACK
            for pt_str in node.get("AW", []):
                pt = sgf_to_coords(pt_str, size)
                if pt:
                    board.grid[pt[0]][pt[1]] = WHITE

            # Отмеченная группа SQ
            for pt_str in node.get("SQ", []):
                pt = sgf_to_coords(pt_str, size)
                if pt:
                    board.sq_points.add(pt)

            # Метки LB (A, B, Q)
            for lb_str in node.get("LB", []):
                if ":" in lb_str:
                    c_str, label = lb_str.split(":", 1)
                    pt = sgf_to_coords(c_str, size)
                    if pt:
                        board.labels[label] = pt

            if idx == 0:
                board.position_history = [board.snapshot_grid()]

            if not stop_before_Moves:
                if "B" in node:
                    pt = sgf_to_coords(node["B"][0], size)
                    board.play(BLACK, pt)
                elif "W" in node:
                    pt = sgf_to_coords(node["W"][0], size)
                    board.play(WHITE, pt)

            if "PL" in node and node["PL"]:
                board.turn = BLACK if node["PL"][0].upper() == "B" else WHITE

        return board

    def neighbors(self, r: int, c: int) -> List[Tuple[int, int]]:
        res = []
        if r > 0:
            res.append((r - 1, c))
        if r + 1 < self.size:
            res.append((r + 1, c))
        if c > 0:
            res.append((r, c - 1))
        if c + 1 < self.size:
            res.append((r, c + 1))
        return res

    def get_group_and_dame(self, r: int, c: int) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]]]:
        """Поиск в ширину/глубину для выделения связанной группы камней и множества её дамэ."""
        color = self.grid[r][c]
        if color == EMPTY:
            return set(), set()
        group: Set[Tuple[int, int]] = {(r, c)}
        dame: Set[Tuple[int, int]] = set()
        stack = [(r, c)]
        while stack:
            cr, cc = stack.pop()
            for nr, nc in self.neighbors(cr, cc):
                val = self.grid[nr][nc]
                if val == EMPTY:
                    dame.add((nr, nc))
                elif val == color and (nr, nc) not in group:
                    group.add((nr, nc))
                    stack.append((nr, nc))
        return group, dame

    def get_all_groups(
        self, color: Optional[str] = None
    ) -> List[Tuple[str, Set[Tuple[int, int]], Set[Tuple[int, int]]]]:
        visited: Set[Tuple[int, int]] = set()
        groups = []
        for r in range(self.size):
            for c in range(self.size):
                val = self.grid[r][c]
                if val != EMPTY and (color is None or val == color) and (r, c) not in visited:
                    grp, libs = self.get_group_and_dame(r, c)
                    visited |= grp
                    groups.append((val, grp, libs))
        return groups

    def simulate_move(
        self, color: str, move: Optional[Tuple[int, int]]
    ) -> Tuple[bool, "GoBoard", List[Tuple[int, int]]]:
        """Проверяет ход по правилам № 1-3 и правилу ко (§ 5). Возвращает (legal, new_board, captured)."""
        if move is None:
            nb = self.clone()
            nb.turn = opponent(color)
            nb.ko_point = None
            nb.position_history.append(nb.snapshot_grid())
            return True, nb, []

        r, c = move
        if not (0 <= r < self.size and 0 <= c < self.size):
            return False, self, []
        if self.grid[r][c] != EMPTY:
            return False, self, []
        if self.ko_point == (r, c):
            return False, self, []

        nb = self.clone()
        nb.grid[r][c] = color
        opp = opponent(color)
        captured: List[Tuple[int, int]] = []

        # Правило № 2: снятие всех групп противника, лишившихся последнего дамэ
        visited_opp: Set[Tuple[int, int]] = set()
        for nr, nc in nb.neighbors(r, c):
            if nb.grid[nr][nc] == opp and (nr, nc) not in visited_opp:
                grp, libs = nb.get_group_and_dame(nr, nc)
                visited_opp |= grp
                if len(libs) == 0:
                    captured.extend(grp)

        for cr, cc in captured:
            nb.grid[cr][cc] = EMPTY

        # Правило № 3: запрет самоубийственного хода (если нет дамэ после снятия камней противника)
        own_grp, own_libs = nb.get_group_and_dame(r, c)
        if len(own_libs) == 0:
            return False, self, []

        # Правило ко (§ 5): запрет повторения предыдущей позиции на доске
        new_snap = nb.snapshot_grid()
        if len(self.position_history) >= 2 and new_snap == self.position_history[-2]:
            return False, self, []
        if new_snap in self.position_history:
            return False, self, []

        if len(captured) == 1 and len(own_grp) == 1 and len(own_libs) == 1:
            nb.ko_point = captured[0]
        else:
            nb.ko_point = None

        nb.prisoners[color] += len(captured)
        nb.turn = opp
        nb.position_history.append(new_snap)
        return True, nb, captured

    def is_legal(self, color: str, move: Optional[Tuple[int, int]]) -> bool:
        ok, _, _ = self.simulate_move(color, move)
        return ok

    def play(self, color: str, move: Optional[Tuple[int, int]]) -> List[str]:
        ok, nb, captured = self.simulate_move(color, move)
        if not ok:
            raise ValueError(f"Illegal move {color} at {move}")
        self.grid = nb.grid
        self.turn = nb.turn
        self.prisoners = nb.prisoners
        self.ko_point = nb.ko_point
        self.position_history = nb.position_history
        cap_sgf = sorted(coords_to_sgf(r, c) for r, c in captured)
        move_no = len(self.move_captures) + 1
        self.move_captures.append((move_no, color, move, cap_sgf))
        return cap_sgf

    # --- ЗАДАНИЕ 1: Модуль правил ---

    def find_target_group(self) -> Tuple[Optional[str], Set[Tuple[int, int]], Set[Tuple[int, int]]]:
        """Находит целевую группу по метке SQ (или автоматически, если SQ не указана в файле)."""
        if self.sq_points:
            total_grp: Set[Tuple[int, int]] = set()
            total_libs: Set[Tuple[int, int]] = set()
            color = None
            for r, c in self.sq_points:
                if self.grid[r][c] != EMPTY:
                    color = self.grid[r][c]
                    grp, libs = self.get_group_and_dame(r, c)
                    total_grp |= grp
                    total_libs |= libs
            if color is not None:
                return color, total_grp, total_libs

        groups = self.get_all_groups()
        if not groups:
            return None, set(), set()
        if len(groups) == 1:
            return groups[0]
        # Если групп несколько и SQ не задана (например, в task018 / task036),
        # выбираем группу с наименьшим числом степеней свободы (атакуемую группу)
        groups.sort(key=lambda g: (len(g[2]), len(g[1])))
        return groups[0]

    def count_target_dame(self) -> int:
        """Вычисляет количество дамэ отмеченной группы (Задание 1, п. 1)."""
        _, _, libs = self.find_target_group()
        return len(libs)

    def check_labeled_move_q(self, move_override: Optional[str] = None) -> Tuple[str, str]:
        """Проверяет ход с меткой Q (Задание 1, п. 2-3): возвращает ('legal'|'illegal', 'снятые камни')."""
        pt = sgf_to_coords(move_override, self.size) if move_override else self.labels.get("Q")
        if pt is None:
            return "illegal", ""
        ok, _, captured = self.simulate_move(self.turn, pt)
        if not ok:
            return "illegal", ""
        cap_str = " ".join(sorted(coords_to_sgf(r, c) for r, c in captured))
        return "legal", cap_str


# --- ЗАДАНИЕ 2: Решатель задач жизни и смерти с параллельным поиском ---


def count_true_eyes(board: GoBoard, group: Set[Tuple[int, int]], color: str) -> Tuple[int, Set[Tuple[int, int]]]:
    """
    Определяет количество независимых глаз/потенциальных глазных областей у группы.
    Учитывает ложные глаза и вражеские камни на ключевых пунктах внутри глазного пространства.
    """
    if not group:
        return 0, set()
    sample = next(iter(group))
    grp, libs = board.get_group_and_dame(sample[0], sample[1])
    opp = opponent(color)

    # Находим пустые и вражеские области внутри/рядом с группой, замкнутые только этой группой
    enclosed_Creation: List[Set[Tuple[int, int]]] = []
    visited: Set[Tuple[int, int]] = set()

    for lr, lc in libs:
        if (lr, lc) in visited:
            continue
        region: Set[Tuple[int, int]] = set()
        Enemy_in_region: Set[Tuple[int, int]] = set()
        borders_other_friendly = False
        borders_outside_enemy = False
        queue = [(lr, lc)]
        region.add((lr, lc))

        while queue:
            cr, cc = queue.pop()
            for nr, nc in board.neighbors(cr, cc):
                val = board.grid[nr][nc]
                if val == EMPTY and (nr, nc) not in region:
                    if len(region) < 8:
                        region.add((nr, nc))
                        queue.append((nr, nc))
                    else:
                        borders_outside_enemy = True
                elif val == color:
                    if (nr, nc) not in grp:
                        borders_other_friendly = True
                elif val == opp:
                    opp_grp, opp_libs = board.get_group_and_dame(nr, nc)
                    if len(opp_grp) <= 2 and len(opp_libs) <= 2:
                        Enemy_in_region |= opp_grp
                    else:
                        borders_outside_enemy = True

        visited |= region
        if not borders_outside_enemy and not borders_other_friendly and len(region) <= 6:
            # Если внутри малой глазной области уже стоит неснятый камень противника (как в task018 после B[ai]),
            # он разрушает разделение глаз до тех пор, пока не будет снят
            if Enemy_in_region and len(region) <= 2:
                continue
            enclosed_Creation.append(region)

    true_eyes = 0
    vital_points: Set[Tuple[int, int]] = set()
    for reg in enclosed_Creation:
        n = len(reg)
        if n == 1:
            pt = next(iter(reg))
            # Проверка диагоналей на истинность глаза
            r, c = pt
            diags = [
                (r - 1, c - 1),
                (r - 1, c + 1),
                (r + 1, c - 1),
                (r + 1, c + 1),
            ]
            valid_diags = [(dr, dc) for dr, dc in diags if 0 <= dr < board.size and 0 <= dc < board.size]
            opp_diags = sum(1 for dr, dc in valid_diags if board.grid[dr][dc] == opp)
            limit = 1 if len(valid_diags) < 4 else 2
            if opp_diags < limit:
                true_eyes += 1
        elif n == 2:
            # 2-пунктовый глаз даёт только 1 глаз
            true_eyes += 1
        elif n in (3, 4, 5):
            # Проверяем наличие центрального ключевого пункта (кюсо), который делит область на 2 глаза
            centers = [
                pt for pt in reg if sum(1 for nb in board.neighbors(*pt) if nb in reg) >= 2
            ]
            if centers:
                vital_points.update(centers)
                true_eyes += 1
            else:
                true_eyes += 2
        elif n >= 6:
            true_eyes += 2

    return true_eyes, vital_points


def generate_tsumego_candidates(
    board: GoBoard, turn_color: str, target_stones: Set[Tuple[int, int]], target_color: str
) -> List[Tuple[int, int]]:
    """
    Формирует упорядоченный список ходов-кандидатов для атакующей и защищающейся сторон:
    - взятия и атари отмеченной группы;
    - ключевые пункты глазного пространства (построение/разрушение двух глаз);
    - дамэ слабых граничащих групп противника (встречное взятие / сэмэай, как в task009).
    """
    alive_targets = [pt for pt in target_stones if board.grid[pt[0]][pt[1]] == target_color]
    if not alive_targets:
        return []

    grp: Set[Tuple[int, int]] = set()
    libs: Set[Tuple[int, int]] = set()
    for r, c in alive_targets:
        g, l = board.get_group_and_dame(r, c)
        grp |= g
        libs |= l

    candidates: Set[Tuple[int, int]] = set(libs)
    _, vital_pts = count_true_eyes(board, grp, target_color)
    candidates |= vital_pts

    # Расширяем кандидатов на соседние пустые пункты вокруг дамэ и слабых соседних групп
    for lr, lc in list(libs):
        for nr, nc in board.neighbors(lr, lc):
            if board.grid[nr][nc] == EMPTY:
                candidates.add((nr, nc))

    opp_of_target = opponent(target_color)
    adjacent_enemy_libs: Set[Tuple[int, int]] = set()
    visited_adj: Set[Tuple[int, int]] = set()

    for r, c in grp:
        for nr, nc in board.neighbors(r, c):
            if board.grid[nr][nc] == opp_of_target and (nr, nc) not in visited_adj:
                egrp, elibs = board.get_group_and_dame(nr, nc)
                visited_adj |= egrp
                if len(elibs) <= 3:
                    adjacent_enemy_libs |= elibs
                    candidates |= elibs

    legal_moves: List[Tuple[int, Tuple[int, int]]] = []
    for pt in sorted(candidates):
        ok, nb, captured = board.simulate_move(turn_color, pt)
        if not ok:
            continue

        # Оценка приоритета хода для эффективного альфа-бета отсечения
        priority = 0
        if captured:
            priority += 500 + len(captured) * 50
        if pt in vital_pts:
            priority += 350

        _, own_libs_after = nb.get_group_and_dame(pt[0], pt[1])
        # Штраф за самоатари (предотвращает ошибку с общим дамэ в task009)
        if len(own_libs_after) == 1 and not captured:
            priority -= 300

        if pt in adjacent_enemy_libs:
            # Предпочитаем внешнее дамэ группы противника общему дамэ
            if pt not in libs:
                priority += 220
            else:
                priority += 80

        if pt in libs:
            priority += 150

        # Бонус за число соседей целевой группы (ключевые точки формы, как ch в task036 и ai в task018)
        adj_target_cnt = sum(1 for nr, nc in board.neighbors(*pt) if (nr, nc) in grp)
        priority += adj_target_cnt * 45

        legal_moves.append((-priority, pt))

    legal_moves.sort(key=lambda item: (item[0], coords_to_sgf(item[1][0], item[1][1])))
    return [pt for _, pt in legal_moves[:12]]


def evaluate_life_state(
    board: GoBoard, target_stones: Set[Tuple[int, int]], target_color: str
) -> Optional[int]:
    """
    Проверяет терминальные условия жизни и смерти целевой группы:
    +1000: целевая группа спасена (неприступная крепость >= 2 глаз или снята окружающая группа);
    -1000: целевая группа погибла (снята с доски или осталась с 0-1 дамэ в атари без контригры).
    Возвращает None, если позиция требует дальнейшего расчёта.
    """
    alive_targets = [pt for pt in target_stones if board.grid[pt[0]][pt[1]] == target_color]
    if not alive_targets:
        return -1000  # Группа снята с доски

    grp, libs = board.get_group_and_dame(*alive_targets[0])
    eyes, vital_pts = count_true_eyes(board, grp, target_color)
    if eyes >= 2 and not vital_pts:
        return 1000  # Неприступная крепость (2 независимых глаза)

    # Проверяем, не снята ли граничащая слабая группа противника, дающая спасение
    if board.prisoners[target_color] > 0 and len(libs) >= 3:
        return 1000

    return None


def heuristic_life_score(
    board: GoBoard, target_stones: Set[Tuple[int, int]], target_color: str
) -> int:
    """Эвристическая оценка на пределе глубины (с учётом сэки и баланса дамэ)."""
    term = evaluate_life_state(board, target_stones, target_color)
    if term is not None:
        return term

    alive_targets = [pt for pt in target_stones if board.grid[pt[0]][pt[1]] == target_color]
    grp, libs = board.get_group_and_dame(*alive_targets[0])
    eyes, _ = count_true_eyes(board, grp, target_color)

    if len(libs) == 1:
        return -800
    score = eyes * 250 + len(libs) * 40 + board.prisoners[target_color] * 300
    return score


def alphabeta_tsumego(
    board: GoBoard,
    depth: int,
    alpha: int,
    beta: int,
    target_stones: Set[Tuple[int, int]],
    target_color: str,
    memo: Dict[Any, Tuple[int, int]],
) -> int:
    """
    Минимакс с альфа-бета отсечением и таблицей транспозиций (мемоизацией):
    Защищающаяся сторона (target_color) максимизирует оценку (+1000 = жизнь),
    атакующая сторона (opponent(target_color)) минимизирует оценку (-1000 = гибель).
    """
    term = evaluate_life_state(board, target_stones, target_color)
    if term is not None:
        return term
    if depth == 0:
        return heuristic_life_score(board, target_stones, target_color)

    state_key = (board.snapshot_grid(), board.ko_point, board.turn)
    if state_key in memo:
        saved_depth, saved_val = memo[state_key]
        if saved_depth >= depth:
            return saved_val

    moves = generate_tsumego_candidates(board, board.turn, target_stones, target_color)
    if not moves:
        val = heuristic_life_score(board, target_stones, target_color)
        memo[state_key] = (depth, val)
        return val

    maximizing = board.turn == target_color
    if maximizing:
        best_val = -10000
        for mv in moves:
            _, nb, _ = board.simulate_move(board.turn, mv)
            val = alphabeta_tsumego(nb, depth - 1, alpha, beta, target_stones, target_color, memo)
            if val > best_val:
                best_val = val
            if best_val > alpha:
                alpha = best_val
            if alpha >= beta:
                break
    else:
        best_val = 10000
        for mv in moves:
            _, nb, _ = board.simulate_move(board.turn, mv)
            val = alphabeta_tsumego(nb, depth - 1, alpha, beta, target_stones, target_color, memo)
            if val < best_val:
                best_val = val
            if best_val < beta:
                beta = best_val
            if alpha >= beta:
                break

    memo[state_key] = (depth, best_val)
    return best_val


def _worker_eval_branch(args: Tuple[GoBoard, Tuple[int, int], int, int, int, Set[Tuple[int, int]], str]) -> Tuple[Tuple[int, int], int, int]:
    """Воркер для параллельной оценки поддерева кандидата (YBWC)."""
    board, mv, depth, alpha, beta, target_stones, target_color = args
    _, nb, _ = board.simulate_move(board.turn, mv)
    local_memo: Dict[Any, Tuple[int, int]] = {}
    val = alphabeta_tsumego(nb, depth - 1, alpha, beta, target_stones, target_color, local_memo)
    return mv, val, len(local_memo)


def solve_tsumego(
    sgf_text: str,
    max_depth: int = 6,
    workers: int = 1,
    backend: str = "process",
) -> Tuple[str, Dict[str, Any]]:
    """
    Решает задачу жизни и смерти (Задание 2) в последовательном или параллельном режиме (YBWC).
    Возвращает (ответ_SGF_координата_или_'no', статистика_поиска).
    """
    board = GoBoard.from_sgf(sgf_text)
    target_color, grp, libs = board.find_target_group()
    if target_color is None or not grp:
        return "no", {"nodes_memoized": 0, "status": "empty"}

    # Если очередь хода явно не задана в SGF и ходов в записи нет:
    # определяем цель задачи по контексту позиции
    nodes = parse_sgf_nodes(sgf_text)
    explicit_pl = any("PL" in n for n in nodes)
    has_moves = any("B" in n or "W" in n for n in nodes)

    turn_color = board.turn if (explicit_pl or has_moves) else BLACK

    # Проверяем, не является ли группа уже неприступной крепостью без хода
    eyes_now, vital_now = count_true_eyes(board, grp, target_color)
    if eyes_now >= 2 and not vital_now and len(libs) >= 2:
        # Проверим, может ли атакующая сторона разрушить крепость
        attacker = opponent(target_color)
        test_b = board.clone()
        test_b.turn = attacker
        memo_check: Dict[Any, Tuple[int, int]] = {}
        att_val = alphabeta_tsumego(test_b, min(4, max_depth), -10000, 10000, grp, target_color, memo_check)
        if att_val >= 200:
            return "no", {"nodes_memoized": len(memo_check), "status": "fortress"}

    candidates = generate_tsumego_candidates(board, turn_color, grp, target_color)
    if not candidates:
        return "no", {"nodes_memoized": 0, "status": "no_candidates"}

    # Быстрая проверка немедленного взятия целевой группы за 1 ход
    if turn_color != target_color and len(libs) == 1:
        only_lib = next(iter(libs))
        if board.is_legal(turn_color, only_lib):
            return coords_to_sgf(*only_lib), {"nodes_memoized": 1, "status": "capture_in_1"}

    memo: Dict[Any, Tuple[int, int]] = {}
    maximizing = turn_color == target_color

    best_move: Optional[Tuple[int, int]] = None
    total_memo_size = 0

    if workers <= 1 or len(candidates) == 1:
        # Последовательный поиск с общей таблицей мемоизации
        best_val = -10000 if maximizing else 10000
        alpha, beta = -10000, 10000
        for mv in candidates:
            _, nb, _ = board.simulate_move(turn_color, mv)
            val = alphabeta_tsumego(nb, max_depth - 1, alpha, beta, grp, target_color, memo)
            if maximizing:
                if val > best_val:
                    best_val = val
                    best_move = mv
                alpha = max(alpha, best_val)
            else:
                if val < best_val:
                    best_val = val
                    best_move = mv
                beta = min(beta, best_val)
        total_memo_size = len(memo)
    else:
        # Схема параллелизации YBWC (Young Brothers Wait Concept):
        # 1. Сначала исследуем первый (главный) ход-кандидат для получения точной границы alpha/beta.
        first_mv = candidates[0]
        _, nb0, _ = board.simulate_move(turn_color, first_mv)
        best_val = alphabeta_tsumego(nb0, max_depth - 1, -10000, 10000, grp, target_color, memo)
        best_move = first_mv
        total_memo_size = len(memo)

        alpha = best_val if maximizing else -10000
        beta = 10000 if maximizing else best_val

        # 2. Остальные поддеревья кандидатов запускаем параллельно с установленным окном [alpha, beta]
        rest_moves = candidates[1:]
        tasks = [(board, mv, max_depth, alpha, beta, grp, target_color) for mv in rest_moves]
        executor_cls = ProcessPoolExecutor if backend == "process" else ThreadPoolExecutor
        with executor_cls(max_workers=workers) as pool:
            for mv, val, m_size in pool.map(_worker_eval_branch, tasks):
                total_memo_size += m_size
                if maximizing and val > best_val:
                    best_val = val
                    best_move = mv
                elif not maximizing and val < best_val:
                    best_val = val
                    best_move = mv

    # Критерий существования решения:
    # Если ход делают защищающиеся (target_color), группа должна выжить (best_val > 0);
    # если атакующие, группа должна погибнуть или потерять глаза (best_val < 200).
    if maximizing and best_val < 0:
        return "no", {"nodes_memoized": total_memo_size, "status": "unsaveable"}
    if not maximizing and best_val >= 500:
        return "no", {"nodes_memoized": total_memo_size, "status": "fortress"}

    if best_move is None:
        return "no", {"nodes_memoized": total_memo_size, "status": "no_move"}

    return coords_to_sgf(*best_move), {"nodes_memoized": total_memo_size, "status": "solved"}


# --- ЗАДАНИЕ 3: Модуль разбора записи партии и подсчёт очков ---


def _flood_fill_territories(board: GoBoard) -> Tuple[int, int, int, List[str]]:
    """
    Подсчёт территорий и нейтральных пунктов по § 3 учебника:
    - территория стороны: пустые области, граничащие только с камнями этой стороны;
    - нейтральные пункты: пустые области, граничащие с камнями обеих сторон.
    """
    visited: Set[Tuple[int, int]] = set()
    terr_b = 0
    terr_w = 0
    neutral = 0
    neutral_points: List[str] = []

    for r in range(board.size):
        for c in range(board.size):
            if board.grid[r][c] == EMPTY and (r, c) not in visited:
                region: Set[Tuple[int, int]] = {(r, c)}
                borders: Set[str] = set()
                stack = [(r, c)]
                while stack:
                    cr, cc = stack.pop()
                    for nr, nc in board.neighbors(cr, cc):
                        val = board.grid[nr][nc]
                        if val == EMPTY and (nr, nc) not in region:
                            region.add((nr, nc))
                            stack.append((nr, nc))
                        elif val in (BLACK, WHITE):
                            borders.add(val)
                visited |= region
                if borders == {BLACK}:
                    terr_b += len(region)
                elif borders == {WHITE}:
                    terr_w += len(region)
                elif len(borders) == 2:
                    neutral += len(region)
                    neutral_points.extend(coords_to_sgf(pr, pc) for pr, pc in sorted(region))

    return terr_b, terr_w, neutral, sorted(neutral_points)


def remove_dead_stones_endgame(board: GoBoard) -> Tuple[GoBoard, Dict[str, List[str]]]:
    """
    Находит и снимает заведомо мёртвые одиночные камни/малые группы внутри чужой территории
    по окончании партии (например, белый камень gc в game02.sgf), не трогая живые группы и сэки.
    """
    clean_board = board.clone()
    dead_removed: Dict[str, List[str]] = {BLACK: [], WHITE: []}

    for color, grp, libs in board.get_all_groups():
        if len(grp) > 3:
            continue
        eyes, _ = count_true_eyes(board, grp, color)
        if eyes >= 1:
            continue

        opp = opponent(color)
        # Проверяем, что все пустые области вокруг этой малой группы окружены живой стеной противника
        surrounded_by_strong_opp = True
        for lr, lc in libs:
            region: Set[Tuple[int, int]] = {(lr, lc)}
            stack = [(lr, lc)]
            opp_neighbors: Set[Tuple[int, int]] = set()
            friendly_other: Set[Tuple[int, int]] = set()
            while stack:
                cr, cc = stack.pop()
                for nr, nc in board.neighbors(cr, cc):
                    val = board.grid[nr][nc]
                    if val == EMPTY and (nr, nc) not in region:
                        region.add((nr, nc))
                        stack.append((nr, nc))
                    elif val == opp:
                        opp_neighbors.add((nr, nc))
                    elif val == color and (nr, nc) not in grp:
                        friendly_other.add((nr, nc))
            if friendly_other or not opp_neighbors:
                surrounded_by_strong_opp = False
                break
            # Проверим, что граничащая группа противника крупная/живая (не сэки)
            sample_opp = next(iter(opp_neighbors))
            ogrp, olibs = board.get_group_and_dame(*sample_opp)
            if len(ogrp) < 6 and len(olibs) <= len(libs):
                surrounded_by_strong_opp = False
                break

        if surrounded_by_strong_opp:
            for r, c in grp:
                clean_board.grid[r][c] = EMPTY
                dead_removed[color].append(coords_to_sgf(r, c))
            clean_board.prisoners[opp] += len(grp)

    return clean_board, dead_removed


def analyze_game_record(sgf_text: str) -> Dict[str, Any]:
    """
    Полный разбор записи партии (Задание 3):
    - реконструкция позиции после каждого хода и списки снятых камней;
    - подсчёт итогового счёта по правилам § 3 учебника (и сравнение с наивной заливкой).
    """
    board = GoBoard.from_sgf(sgf_text)
    komi = 4.5 if board.size == 9 else 6.5

    # 1. Наивная заливка (без снятия мёртвых камней в конце партии)
    naive_tb, naive_tw, naive_neutral, naive_neutral_pts = _flood_fill_territories(board)
    naive_score_b = naive_tb + board.prisoners[BLACK]
    naive_score_w = naive_tw + board.prisoners[WHITE] + komi

    # 2. Точный подсчёт по § 3 учебника (со снятием мёртвых камней по окончании партии)
    final_board, dead_stones = remove_dead_stones_endgame(board)
    terr_b, terr_w, neutral, neutral_pts = _flood_fill_territories(final_board)

    pris_b = final_board.prisoners[BLACK]
    pris_w = final_board.prisoners[WHITE]
    score_b = float(terr_b + pris_b)
    score_w = float(terr_w + pris_w) + komi

    winner = "чёрные" if score_b > score_w else ("белые" if score_w > score_b else "ничья")
    diff = abs(score_b - score_w)

    return {
        "board_size": board.size,
        "total_moves": len(board.move_captures),
        "move_captures": board.move_captures,
        "has_captures_or_dead": (pris_b + pris_w) > 0,
        "territory_black": terr_b,
        "territory_white": terr_w,
        "neutral_count": neutral,
        "neutral_points": neutral_pts,
        "prisoners_black": pris_b,
        "prisoners_white": pris_w,
        "dead_stones_removed": dead_stones,
        "komi": komi,
        "score_black": score_b,
        "score_white": score_w,
        "winner": winner,
        "diff": diff,
        "naive_comparison": {
            "territory_black": naive_tb,
            "territory_white": naive_tw,
            "neutral_count": naive_neutral,
            "neutral_points": naive_neutral_pts,
            "score_black": float(naive_score_b),
            "score_white": float(naive_score_w),
        },
    }