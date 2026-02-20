# STEP Analysis Tool

Extracts mass properties from the TRLC-DK1-Follower STEP assembly file, grouped by URDF link. Uses per-part material densities via pattern matching on assembly part names.

## Prerequisites

Scripts use [PEP 723](https://peps.python.org/pep-0723/) inline script metadata, so
[uv](https://docs.astral.sh/uv/) handles dependencies (cadquery) automatically -- no
manual venv setup needed.

Install uv if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Usage

```bash
# Regenerate all output files at once
./generate_outputs.sh /path/to/TRLC-DK1-Follower_v0.3.0.step

# Or run individual analyses:

# Link mass analysis
uv run analyze_step.py /path/to/TRLC-DK1-Follower_v0.3.0.step \
    --link-map link_mapping.json \
    --material-map material_map.json \
    --density 1220

# List all depth-1 parts (for building link_mapping.json)
uv run analyze_step.py /path/to/TRLC-DK1-Follower_v0.3.0.step --list-parts

# Print full assembly tree
uv run analyze_step.py /path/to/TRLC-DK1-Follower_v0.3.0.step --tree

# Calculate effective densities from datasheet masses
uv run calc_motor_density.py /path/to/TRLC-DK1-Follower_v0.3.0.step
```

## Files

| File | Description |
|---|---|
| `analyze_step.py` | Main analysis script. Reads STEP via XCAF, groups parts by link, computes mass properties. |
| `calc_motor_density.py` | Helper to back-calculate effective densities from known motor masses and CAD volumes. |
| `link_mapping.json` | Maps STEP part instance names to URDF link names. |
| `material_map.json` | Per-part density overrides via substring pattern matching on part names. |
| `generate_outputs.sh` | Shell script to regenerate all `output/` files from a STEP file. |

## How it works

1. The STEP file is read using OpenCascade's XCAF document reader, which preserves the assembly hierarchy and part names.
2. Top-level (depth-1) parts are matched to URDF links via `link_mapping.json`. Path references (`"Parent > Child"`) can map sub-assembly children to different links; the parent automatically excludes those children.
3. For each part, density is determined by substring-matching the part name against patterns in `material_map.json`. Unmatched parts use the `--density` default (1220 kg/m³ for PLA-CF).
4. Patterns with a `mass_g` field (motors, bearings, MGN9) use the known datasheet mass directly -- children are not recursed into. Patterns with only `density` (screws, aluminum, PLA) compute mass from CAD volume.
5. STEP geometry is in mm; output mass is in kg.

## Current best estimate (2025-02)

Default PLA-CF density: 1220 kg/m^3 (Bambu Lab PLA-CF, TDS V3, 100% infill).

| Link | Mass (g) | Notes |
|---|---|---|
| base_link | 450.1 | DM-J4340P + aluminum shell |
| link1-2 | 472.4 | DM-J4340 + aluminum arm + PLA-CF adapter |
| link2-3 | 811.4 | DM-J4340 + 2x 6803ZZ bearings + aluminum arms + PLA-CF frame |
| link3-4 | 688.0 | DM-J4310 + 6803ZZ bearing + aluminum arms + PLA-CF frame |
| link4-5 | 360.6 | DM-J4310 + aluminum arm + cable cover |
| link5-6 | 370.4 | DM-J4310 + aluminum arm + shaft extensions |
| link6-7 | 599.2 | Gripper assembly excl. fingers (DM-J4310, MGN9, rack, PLA-CF) |
| finger_left | 41.8 | Finger + adapter (PLA-CF) |
| finger_right | 41.8 | Finger + adapter (PLA-CF) |
| **Total** | **3835.5** | + ~77g unmapped screws |

## Motor specifications

Sources: DAMIAO 2025 Product Selection Manual, DM-J4340-2EC User Manual V1.0, DM-J4310 User Manual (English).

| Parameter | DM-J4340P-2EC | DM-J4340-2EC | DM-J4310-2EC V1.1 |
|---|---|---|---|
| **Mass** | ~375 g | ~362 g | ~300 g |
| **Outer diameter** | 57 mm | 57 mm | 56 mm |
| **Height** | 56.5 mm | 53.3 mm | 46 mm |
| **Gear ratio** | 40:1 | 40:1 | 10:1 |
| **Rated torque** | 9 N*m | 9 N*m | 3 N*m |
| **Peak torque** | 27 N*m | 27 N*m | 7 N*m |
| **Reducer type** | Planetary | Harmonic | -- |
| **CAD volume** | 128.74 cm^3 | 118.25 cm^3 | 102.67 cm^3 |
| **Effective density** | 2913 kg/m^3 | 3061 kg/m^3 | 2922 kg/m^3 |

Joint assignments: joints 1-3 use DM-J4340 (joint 1 uses the P variant), joints 4-6 and gripper use DM-J4310.

## Effective densities for non-PLA components

Effective densities are back-calculated from known datasheet masses and CAD volumes (`density = mass / volume`). This compensates for simplified CAD geometry (e.g. bearings without internal voids, carriages without ball bearings).

| Component | Mass source | Mass (g) | CAD vol (cm^3) | Eff. density (kg/m^3) |
|---|---|---|---|---|
| DM-J4340P-2EC | DAMIAO 2025 Product Selection Manual | 375 | 128.74 | 2913 |
| DM-J4340-2EC | DM-J4340-2EC User Manual V1.0 | 362 | 118.25 | 3061 |
| DM-J4310-2EC | DM-J4310 User Manual | 300 | 102.67 | 2922 |
| 6803ZZ bearing | NSK datasheet | 7 | 1.03 | 6808 |
| MGN9 Rail 150mm | Circuitist (380 g/m) | 57 | 7.25 | 7862 |
| MGN9C carriage | Circuitist | 26 | 3.05 | 8520 |

## Known limitations

- **127 screws (~77g) are unmapped** and not assigned to specific links.
