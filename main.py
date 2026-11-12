import argparse
import sys
from pathlib import Path
from go_engine import (
    GoBoard,
    solve_tsumego,
    analyze_game_record,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Решения задач олимпиады СПбГУ PSRS: Модуль правил, Решатель цумэго, Разбор партии Го"
    )
    parser.add_argument("sgf_file", type=str, help="Путь к входному SGF-файлу")
    parser.add_argument(
        "--mode",
        choices=["dame", "capture", "legal", "solve", "game"],
        required=True,
        help="Режим работы: dame | capture | legal | solve | game",
    )
    parser.add_argument("--move", type=str, default=None, help="SGF-координата проверяемого хода (если нет метки Q)")
    parser.add_argument("--move-num", type=int, default=None, help="Номер хода в партии для вывода снятых камней")
    parser.add_argument("--workers", type=int, default=1, help="Число процессов для параллельного поиска (Задание 2)")
    parser.add_argument("--depth", type=int, default=6, help="Максимальная глубина локального дерева поиска")
    parser.add_argument("--output", "-o", type=str, default=None, help="Путь к выходному текстовому файлу")

    args = parser.parse_args()
    sgf_text = Path(args.sgf_file).read_text(encoding="utf-8")

    result_str = ""
    if args.mode == "dame":
        board = GoBoard.from_sgf(sgf_text)
        result_str = str(board.count_target_dame())

    elif args.mode == "capture":
        board = GoBoard.from_sgf(sgf_text)
        if "Q" in board.labels or args.move:
            _, cap_str = board.check_labeled_move_q(args.move)
            result_str = cap_str
        else:
            # Для задач § 1 № 7-12 без метки Q: выводим SGF-пункт хода, снимающего камни
            ans, _ = solve_tsumego(sgf_text, max_depth=args.depth, workers=1)
            result_str = ans

    elif args.mode == "legal":
        board = GoBoard.from_sgf(sgf_text)
        status, _ = board.check_labeled_move_q(args.move)
        result_str = status

    elif args.mode == "solve":
        ans, _ = solve_tsumego(sgf_text, max_depth=args.depth, workers=args.workers)
        result_str = ans

    elif args.mode == "game":
        info = analyze_game_record(sgf_text)
        if args.move_num is not None:
            idx = args.move_num - 1
            if 0 <= idx < len(info["move_captures"]):
                result_str = " ".join(info["move_captures"][idx][3])
            else:
                result_str = ""
        else:
            lines = [
                f"SZ: {info['board_size']}",
                f"Ходов: {info['total_moves']}",
                f"Территория ч: {info['territory_black']}",
                f"Территория б: {info['territory_white']}",
                f"Нейтральные: {info['neutral_count']}",
                f"Пленные ч: {info['prisoners_black']}",
                f"Пленные б: {info['prisoners_white']}",
                f"Коми: {info['komi']}",
                f"Счёт ч: {info['score_black']:.1f}",
                f"Счёт б: {info['score_white']:.1f}",
                f"Победитель: {info['winner']}",
                f"Разница: {info['diff']:.1f}",
            ]
            result_str = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(result_str + "\n", encoding="utf-8")
    else:
        sys.stdout.write(result_str + "\n")


if __name__ == "__main__":
    main()