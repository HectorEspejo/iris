#!/usr/bin/env python3
"""
Script to recalculate node tiers based on current scoring algorithm.

Usage:
    python scripts/recalculate_tiers.py [--dry-run]
"""

import sqlite3
import argparse
from pathlib import Path


def calculate_node_tier(vram_gb: float, model_params: float, tokens_per_second: float) -> str:
    """
    Calculate node tier based on capabilities.

    Scoring:
    - VRAM (25%): 24+ GB = 25pts, 16+ GB = 20pts, 12+ GB = 15pts, 8+ GB = 10pts
    - Model params (50%): 100B+ = 65pts, 70B+ = 50pts, 30B+ = 40pts, 13B+ = 25pts, 7B+ = 15pts
    - Speed (25%): 50+ tps = 25pts, 20+ tps = 15pts, 10+ tps = 10pts

    Thresholds:
    - Premium: 61+ points
    - Standard: 21-60 points
    - Basic: 0-20 points
    """
    score = 0

    # VRAM score (0-25)
    if vram_gb >= 24:
        score += 25
    elif vram_gb >= 16:
        score += 20
    elif vram_gb >= 12:
        score += 15
    elif vram_gb >= 8:
        score += 10

    # Model params score (0-65)
    if model_params >= 100:
        score += 65  # Auto-PREMIUM for 100B+ models
    elif model_params >= 70:
        score += 50
    elif model_params >= 30:
        score += 40
    elif model_params >= 13:
        score += 25
    elif model_params >= 7:
        score += 15
    elif model_params >= 3:
        score += 5

    # Speed score (0-25)
    if tokens_per_second >= 50:
        score += 25
    elif tokens_per_second >= 20:
        score += 15
    elif tokens_per_second >= 10:
        score += 10

    # Determine tier
    if score >= 61:
        return "premium", score
    elif score >= 21:
        return "standard", score
    return "basic", score


def main():
    parser = argparse.ArgumentParser(description="Recalculate node tiers")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--db", default="data/iris.db", help="Path to database file")
    args = parser.parse_args()

    # Find database
    db_path = Path(args.db)
    if not db_path.exists():
        # Try relative to project root
        project_root = Path(__file__).parent.parent
        db_path = project_root / args.db

    if not db_path.exists():
        print(f"Error: Database not found at {db_path}")
        return 1

    print(f"Database: {db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'APPLY CHANGES'}")
    print("-" * 60)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get all nodes
    cursor.execute("""
        SELECT id, model_name, model_params, vram_gb, tokens_per_second, node_tier
        FROM nodes
        ORDER BY model_params DESC
    """)
    nodes = cursor.fetchall()

    if not nodes:
        print("No nodes found in database.")
        return 0

    print(f"{'NODE ID':<20} {'MODEL':<15} {'PARAMS':<10} {'VRAM':<10} {'TPS':<10} {'SCORE':<8} {'OLD TIER':<12} {'NEW TIER':<12}")
    print("=" * 110)

    changes = []
    for node in nodes:
        node_id = node["id"]
        model_params = node["model_params"] or 0
        vram_gb = node["vram_gb"] or 0
        tps = node["tokens_per_second"] or 0
        old_tier = node["node_tier"]
        model_name = (node["model_name"] or "unknown")[:15]

        new_tier, score = calculate_node_tier(vram_gb, model_params, tps)

        changed = old_tier != new_tier
        marker = " *" if changed else ""

        print(f"{node_id:<20} {model_name:<15} {model_params:<10.1f} {vram_gb:<10.1f} {tps:<10.1f} {score:<8} {old_tier:<12} {new_tier:<12}{marker}")

        if changed:
            changes.append((node_id, old_tier, new_tier, score))

    print("-" * 110)
    print(f"Total nodes: {len(nodes)}")
    print(f"Nodes to update: {len(changes)}")

    if changes and not args.dry_run:
        print("\nApplying changes...")
        for node_id, old_tier, new_tier, score in changes:
            cursor.execute(
                "UPDATE nodes SET node_tier = ? WHERE id = ?",
                (new_tier, node_id)
            )
            print(f"  {node_id}: {old_tier} -> {new_tier}")

        conn.commit()
        print(f"\n✓ Updated {len(changes)} nodes.")
    elif changes and args.dry_run:
        print("\nDry run - no changes applied. Run without --dry-run to apply.")
    else:
        print("\nNo changes needed.")

    conn.close()
    return 0


if __name__ == "__main__":
    exit(main())
