import argparse
import json
import sys
from pathlib import Path
from datetime import datetime
from scheduler.algorithms import get_strategy
from scheduler.io_utils import load_tasks, load_slots, print_schedule, export_json, export_csv

VERSION = "2.0.0"


def parse_args():
    parser = argparse.ArgumentParser(
        description="TimeWeaver — умный планировщик учебного времени",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Примеры:\n"
            "  python main.py --tasks tasks.json --slots slots.json\n"
            "  python main.py --tasks tasks.json --slots slots.json --strategy greedy --export plan.json\n"
            "  python main.py --tasks tasks.json --slots slots.json --stats --verbose\n"
        ),
    )
    parser.add_argument("--tasks", type=Path, required=True, help="Путь к JSON-файлу с задачами")
    parser.add_argument("--slots", type=Path, required=True, help="Путь к JSON-файлу со свободными слотами")
    parser.add_argument(
        "--strategy",
        choices=["greedy", "balanced", "deadline"],
        default="balanced",
        help="Стратегия планирования (по умолчанию: balanced)",
    )
    parser.add_argument("--export", type=Path, default=None, help="Экспорт расписания в JSON-файл")
    parser.add_argument("--export-csv", type=Path, default=None, help="Экспорт расписания в CSV-файл")
    parser.add_argument("--stats", action="store_true", help="Показать сводную статистику по расписанию")
    parser.add_argument("--verbose", action="store_true", help="Подробный вывод с диагностикой")
    parser.add_argument("--config", type=Path, default=None, help="Путь к конфигурационному JSON-файлу")
    parser.add_argument("--version", action="version", version=f"TimeWeaver v{VERSION}")
    return parser.parse_args()


def load_config(config_path: Path) -> dict:
    if config_path is None:
        return {}
    try:
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Ошибка: конфигурационный файл не найден: {config_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка: некорректный JSON в конфиге: {e}", file=sys.stderr)
        sys.exit(1)


def apply_config_overrides(args, config: dict):
    if not config:
        return
    if "strategy" in config and args.strategy == "balanced":
        args.strategy = config["strategy"]
    if "export" in config and args.export is None:
        args.export = Path(config["export"])
    if "verbose" in config:
        args.verbose = args.verbose or config["verbose"]


def compute_stats(tasks, slots, schedule):
    total_tasks = len(tasks)
    scheduled = len(schedule)
    unscheduled = total_tasks - scheduled
    total_hours = sum(b.task.duration_hours for b in schedule)
    slot_hours = sum((s.end - s.start).total_seconds() / 3600 for s in slots)
    utilization = (total_hours / slot_hours * 100) if slot_hours > 0 else 0
    by_importance = {}
    for b in schedule:
        key = b.task.importance
        by_importance[key] = by_importance.get(key, 0) + 1
    return {
        "total_tasks": total_tasks,
        "scheduled": scheduled,
        "unscheduled": unscheduled,
        "total_planned_hours": round(total_hours, 1),
        "available_hours": round(slot_hours, 1),
        "slot_utilization_pct": round(utilization, 1),
        "by_importance": dict(sorted(by_importance.items(), reverse=True)),
    }


def print_stats(stats: dict):
    print("\n" + "=" * 50)
    print("  СВОДНАЯ СТАТИСТИКА")
    print("=" * 50)
    print(f"  Всего задач:           {stats['total_tasks']}")
    print(f"  Запланировано:         {stats['scheduled']}")
    print(f"  Не помещается:          {stats['unscheduled']}")
    print(f"  Запланировано часов:    {stats['total_planned_hours']}")
    print(f"  Доступно часов:         {stats['available_hours']}")
    print(f"  Загрузка слотов:        {stats['slot_utilization_pct']}%")
    print("-" * 50)
    print("  По важности задач:")
    for importance, count in stats["by_importance"].items():
        print(f"    Важность {importance}: {count} задач(и)")
    print("=" * 50 + "\n")


def main():
    args = parse_args()
    config = load_config(args.config)
    apply_config_overrides(args, config)

    if args.verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Загрузка задач из {args.tasks}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Загрузка слотов из {args.slots}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Стратегия: {args.strategy}")

    try:
        tasks = load_tasks(args.tasks)
    except FileNotFoundError:
        print(f"Ошибка: файл задач не найден: {args.tasks}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка: некорректный JSON в файле задач: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyError as e:
        print(f"Ошибка: отсутствует обязательное поле в задаче: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        slots = load_slots(args.slots)
    except FileNotFoundError:
        print(f"Ошибка: файл слотов не найден: {args.slots}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Ошибка: некорректный JSON в файле слотов: {e}", file=sys.stderr)
        sys.exit(1)

    if not tasks:
        print("Предупреждение: список задач пуст, нечего планировать.", file=sys.stderr)
        sys.exit(0)
    if not slots:
        print("Предупреждение: список слотов пуст, некуда ставить задачи.", file=sys.stderr)
        sys.exit(0)

    if args.verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Задач загружено: {len(tasks)}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Слотов загружено: {len(slots)}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Запуск планирования...")

    strategy = get_strategy(args.strategy)
    schedule = strategy.plan(tasks, slots)

    if not schedule:
        print("Не удалось составить расписание: ни одна задача не помещается в слоты.")
        if args.stats:
            stats = compute_stats(tasks, slots, schedule)
            print_stats(stats)
        sys.exit(1)

    print_schedule(schedule)

    if args.stats:
        stats = compute_stats(tasks, slots, schedule)
        print_stats(stats)

    if args.export:
        try:
            export_json(schedule, args.export)
            print(f"Расписание экспортировано в {args.export}")
        except Exception as e:
            print(f"Ошибка при экспорте в JSON: {e}", file=sys.stderr)

    if args.export_csv:
        try:
            export_csv(schedule, args.export_csv)
            print(f"Расписание экспортировано в {args.export_csv}")
        except Exception as e:
            print(f"Ошибка при экспорте в CSV: {e}", file=sys.stderr)

    if args.verbose:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Готово. Запланировано задач: {len(schedule)}/{len(tasks)}")


if __name__ == "__main__":
    main()
