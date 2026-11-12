import unittest
from go_engine import GoBoard, solve_tsumego, analyze_game_record

GAME01_SGF = "(;FF[4]GM[1]SZ[9];B[gc];W[cg];B[gg];W[cc];B[ee];W[eg];B[ff];W[ec];B[ce];W[fd];B[he];W[fh];B[gh];W[fb];B[gb];W[fc];B[bf];W[bg];B[bd];W[bc];B[fg];W[eh];B[ag];W[ah];B[af];W[bi];B[ac];W[ab];B[ad];W[ba];B[fa];W[ea];B[ga];W[gd];B[hd];W[gi];B[hi];W[fi];B[ih];W[ef];B[fe];W[df];B[de];W[ge];B[gf];W[cd];B[cf];W[dd];B[ed];W[db])"
GAME02_SGF = "(;FF[4]GM[1]SZ[9];B[ee];W[gg];B[ge];W[cc];B[db];W[cb];B[dc];W[ce];B[eg];W[hf];B[he];W[fh];B[eh];W[hh];B[bf];W[cf];B[cg];W[be];B[bg];W[gc];B[hb];W[ie];B[id];W[if];B[hd];W[dd];B[ed];W[eb];B[ec];W[da];B[fb];W[ea];B[fa];W[ca];B[fc];W[ei];B[di];W[fi];B[dg];W[af];B[ag];W[ae];B[de];W[cd];B[gf];W[fg];B[ff];W[df];B[ef])"
GAME03_SGF = "(;FF[4]GM[1]SZ[9];B[dd];W[fe];B[ef];W[cg];B[ff];W[fc];B[ge];W[gd];B[ee];W[fd];B[he];W[hd];B[fh];W[bd];B[bc];W[cd];B[ce];W[be];B[cc];W[dc];B[db];W[ec];B[bb];W[eb];B[ca];W[ea];B[da];W[cf];B[dh];W[ch];B[ci];W[bi];B[di];W[dg];B[eg];W[ah];B[id];W[ic];B[ie];W[hb];B[de];W[ad];B[ac];W[af];B[gg])"


class TestGoOlympiadTasks(unittest.TestCase):
    # --- Тесты Задания 1 (дамэ, взятие, легальность, ко) ---
    def test_task1_dame_tasks_1_to_5(self):
        cases = [
            ("t1", "(;FF[4]GM[1]SZ[9]AB[ec][ed][ee][ef])", 10),
            ("t2", "(;FF[4]GM[1]SZ[9]AB[dd][de][ed][ee])", 8),
            ("t3", "(;FF[4]GM[1]SZ[9]AB[ed][ee][ef][fe])", 9),
            ("t4", "(;FF[4]GM[1]SZ[9]AB[dd][de][ed][ee][fe])", 9),
            ("t5", "(;FF[4]GM[1]SZ[9]AB[gb][gc][ha][hc][ia][ib][ic])", 8),
        ]
        for name, sgf, expected in cases:
            with self.subTest(name=name):
                b = GoBoard.from_sgf(sgf)
                self.assertEqual(b.count_target_dame(), expected)

    def test_task1_multi_group_capture_and_suicide(self):
        # Ход Q снимает две группы белых одновременно (даже не имея собственных свободных пунктов до снятия)
        sgf = "(;FF[4]GM[1]SZ[9]AB[ba][ab][cb][bc]AW[aa][bb]LB[ac:Q]PL[B])"
        # Добавим окружение для bb: bd, cd и проверим снятие aa ходом в его последнее дамэ
        sgf_capture = "(;FF[4]GM[1]SZ[9]AB[ba]AW[aa]LB[ab:Q]PL[B])"
        b = GoBoard.from_sgf(sgf_capture)
        status, caps = b.check_labeled_move_q()
        self.assertEqual(status, "legal")
        self.assertEqual(caps, "aa")

        # Запрет самоубийственного хода (правило № 3)
        sgf_suicide = "(;FF[4]GM[1]SZ[9]AW[ba][ab]LB[aa:Q]PL[B])"
        b2 = GoBoard.from_sgf(sgf_suicide)
        status2, caps2 = b2.check_labeled_move_q()
        self.assertEqual(status2, "illegal")
        self.assertEqual(caps2, "")

    def test_task1_ko_rule(self):
        # Классическая позиция ко: чёрные берут ко, белым запрещено брать обратно немедленно
        sgf_ko = "(;FF[4]GM[1]SZ[9]AB[cb][bc][cd][dc]AW[da][eb][ed][ce];B[db];W[cc])"
        b = GoBoard.from_sgf(sgf_ko)
        # Попытка чёрных немедленно вернуть позицию ходом B[db] запрещена правилом ко
        status, _ = b.check_labeled_move_q(move_override="db")
        self.assertEqual(status, "illegal")

    # --- Тесты Задания 2 (решатель жизни и смерти, мемоизация, параллельный поиск) ---
    def test_task2_solver_tasks(self):
        # task009: сэмэай с общим дамэ ei -> единственный верный ход ci
        t009 = "(;FF[4]GM[1]SZ[9]AB[ch][df][dg][eh][fh]AW[dh][di][eg][fg][gh]SQ[eh][fh])"
        ans9, _ = solve_tsumego(t009, max_depth=6, workers=1)
        self.assertEqual(ans9, "ci")

        # task018: угловая группа из 3 пунктов (bent-three) -> ключевой пункт ai
        t018 = "(;FF[4]GM[1]SZ[9]AB[af][bf][cf][cg][dg][dh][di]AW[ag][bg][bh][ch][ci])"
        ans18_seq, _ = solve_tsumego(t018, max_depth=6, workers=1)
        ans18_par, _ = solve_tsumego(t018, max_depth=6, workers=2, backend="thread")
        self.assertEqual(ans18_seq, "ai")
        self.assertEqual(ans18_par, "ai")

        # Неприступная крепость с двумя глазами (task005 + внешнее окружение) -> 'no'
        t_fortress = "(;FF[4]GM[1]SZ[9]AB[gb][gc][ha][hc][ia][ib][ic]AW[fa][fb][fc][fd][gd][hd][id]SQ[gb]PL[W])"
        ans_fort, _ = solve_tsumego(t_fortress, max_depth=4, workers=1)
        self.assertEqual(ans_fort, "no")

    # --- Тесты Задания 3 (сверка с эталонной таблицей games_reference.md) ---
    def test_task3_reference_games(self):
        g1 = analyze_game_record(GAME01_SGF)
        self.assertEqual(g1["total_moves"], 50)
        self.assertEqual(g1["territory_black"], 16)
        self.assertEqual(g1["territory_white"], 15)
        self.assertEqual(g1["neutral_count"], 0)
        self.assertEqual(g1["prisoners_black"], 0)
        self.assertEqual(g1["prisoners_white"], 0)
        self.assertEqual(g1["score_black"], 16.0)
        self.assertEqual(g1["score_white"], 19.5)
        self.assertEqual(g1["winner"], "белые")
        self.assertEqual(g1["diff"], 3.5)

        g2 = analyze_game_record(GAME02_SGF)
        self.assertEqual(g2["total_moves"], 49)
        self.assertEqual(g2["territory_black"], 18)
        self.assertEqual(g2["territory_white"], 15)
        self.assertEqual(g2["neutral_count"], 0)
        self.assertEqual(g2["prisoners_black"], 1)
        self.assertEqual(g2["prisoners_white"], 0)
        self.assertEqual(g2["score_black"], 19.0)
        self.assertEqual(g2["score_white"], 19.5)
        self.assertEqual(g2["winner"], "белые")
        self.assertEqual(g2["diff"], 0.5)

        g3 = analyze_game_record(GAME03_SGF)
        self.assertEqual(g3["total_moves"], 45)
        self.assertEqual(g3["territory_black"], 19)
        self.assertEqual(g3["territory_white"], 15)
        self.assertEqual(g3["neutral_count"], 2)
        self.assertEqual(g3["prisoners_black"], 0)
        self.assertEqual(g3["prisoners_white"], 0)
        self.assertEqual(g3["score_black"], 19.0)
        self.assertEqual(g3["score_white"], 19.5)
        self.assertEqual(g3["winner"], "белые")
        self.assertEqual(g3["diff"], 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)