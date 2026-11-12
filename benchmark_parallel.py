import time
from pathlib import Path
from typing import List
from go_engine import solve_tsumego


def get_benchmark_positions(tasks_dir: str = "sgf_testing_tasks") -> List[str]:
    p = Path(tasks_dir)
    positions: List[str] = []
    if p.exists():
        for f in sorted(p.glob("task*.sgf")):
            if "_answer" not in f.name:
                txt = f.read_text(encoding="utf-8").strip()
                if "AB" in txt or "AW" in txt:
                    positions.append(txt)
    if len(positions) >= 20:
        return positions[:24]

    # Если скрипт запущен вне папки с SGF, используем 24 вариации задач цумэго 9x9
    base_patterns = [
        "(;FF[4]GM[1]SZ[9]AB[ch][df][dg][eh][fh]AW[dh][di][eg][fg][gh]SQ[eh][fh])",
        "(;FF[4]GM[1]SZ[9]AB[af][bf][cf][cg][dg][dh][di]AW[ag][bg][bh][ch][ci])",
        "(;FF[4]GM[1]SZ[9]AB[bf][cf][df][ef][eg][eh]AW[bg][cg][dg][dh])",
        "(;FF[4]GM[1]SZ[9]AB[ad][bd][cd][dd][de][df][dg][dh]AW[ae][be][ce][cf][cg][ch]SQ[ae])",
        "(;FF[4]GM[1]SZ[9]AB[fb][fc][fd][gd][hd][id]AW[gb][hb][hc][ic]SQ[gb])",
        "(;FF[4]GM[1]SZ[9]AB[bb][cb][db][eb][ec][ed][ee][dc][bc][bd]AW[cc][cd][ce]SQ[cc])",
    ]
    while len(positions) < 24:
        positions.extend(base_patterns)
    return positions[:24]


def run_benchmark() -> None:
    positions = get_benchmark_positions()
    configs = [
        ("1 процесс (Sequential + Memo)", 1, "process"),
        ("2 потока (YBWC ThreadPool)", 2, "thread"),
        ("4 процесса (YBWC ProcessPool)", 4, "process"),
        ("8 процессов (YBWC ProcessPool)", 8, "process"),
    ]

    print(f"Экспериментальная оценка на {len(positions)} позициях (max_depth=6):\n")
    print("| Конфигурация | Время (с) | Ускорение (Speedup) | Эффективность |")
    print("|---|---|---|---|")

    base_time = None
    for name, workers, backend in configs:
        t0 = time.perf_counter()
        for sgf in positions:
            solve_tsumego(sgf, max_depth=6, workers=workers, backend=backend)
        elapsed = time.perf_counter() - t0
        if base_time is None:
            base_time = elapsed
        speedup = base_time / elapsed if elapsed > 0 else 1.0
        eff = speedup / workers
        print(f"| {name} | {elapsed:.4f} | {speedup:.2f}x | {eff:.2%} |")


if __name__ == "__main__":
    run_benchmark()