import argparse
import json
from pathlib import Path
from scheduler.algorithms import get_strategy
from scheduler.io_utils import load_tasks, load_slots, print_schedule

def parse_args():
    parser = argparse.ArgumentParser(description="TimeWeaver: учебный планировщик")
    parser.add_argument("--tasks", type=Path, required=True, help="JSON с задачами")
    parser.add_argument("--slots", type=Path, required=True, help="JSON со свободными слотами")
    parser.add_argument("--strategy", choices=["greedy", "balanced", "deadline"], default="balanced")
    return parser.parse_args()

def main():
    args = parse_args()
    tasks = load_tasks(args.tasks)
    slots = load_slots(args.slots)
    strategy = get_strategy(args.strategy)
    schedule = strategy.plan(tasks, slots)
    print_schedule(schedule)

if __name__ == "__main__":
    main()

