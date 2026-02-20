#!/bin/bash
# Regenerate all output files from a STEP assembly file.
# Usage: ./generate_outputs.sh /path/to/TRLC-DK1-Follower_v0.3.0.step

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="$SCRIPT_DIR/output"

if [ $# -lt 1 ]; then
    echo "Usage: $0 <step_file>"
    exit 1
fi

STEP_FILE="$1"

if [ ! -f "$STEP_FILE" ]; then
    echo "Error: STEP file not found: $STEP_FILE"
    exit 1
fi

mkdir -p "$OUTPUT_DIR"

echo "=== Link mass analysis ==="
uv run "$SCRIPT_DIR/analyze_step.py" "$STEP_FILE" \
    --link-map "$SCRIPT_DIR/link_mapping.json" \
    --material-map "$SCRIPT_DIR/material_map.json" \
    --density 1220 \
    | tee "$OUTPUT_DIR/output_links.txt"

echo ""
echo "=== Depth-1 parts list ==="
uv run "$SCRIPT_DIR/analyze_step.py" "$STEP_FILE" --list-parts \
    | tee "$OUTPUT_DIR/output_parts.txt"

echo ""
echo "=== Assembly tree ==="
uv run "$SCRIPT_DIR/analyze_step.py" "$STEP_FILE" --tree \
    > "$OUTPUT_DIR/output_tree.txt"
echo "Written to output/output_tree.txt (too large to display)"

echo ""
echo "=== Effective density calculation ==="
uv run "$SCRIPT_DIR/calc_motor_density.py" "$STEP_FILE" \
    | tee "$OUTPUT_DIR/output_motor_density.txt"

echo ""
echo "Done. Output files in $OUTPUT_DIR/"
