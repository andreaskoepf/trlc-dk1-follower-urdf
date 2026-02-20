# STEP Analysis Tool

Extracts mass, center of mass, and inertia tensor values from the TRLC-DK1-Follower STEP assembly file, grouped by URDF link. Uses per-part material densities via pattern matching on assembly part names.

## Prerequisites

Scripts use [PEP 723](https://peps.python.org/pep-0723/) inline script metadata, so
[uv](https://docs.astral.sh/uv/) handles dependencies (cadquery, numpy) automatically -- no
manual venv setup needed.

Install uv if you don't have it: `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Usage

```bash
# Full analysis with URDF output
uv run analyze_step.py /path/to/TRLC-DK1-Follower_v0.3.0.step \
    --link-map link_mapping.json \
    --material-map material_map.json \
    --density 1220 \
    --urdf

# List all depth-1 parts (for building link_mapping.json)
uv run analyze_step.py /path/to/TRLC-DK1-Follower_v0.3.0.step --list-parts

# Print full assembly tree
uv run analyze_step.py /path/to/TRLC-DK1-Follower_v0.3.0.step --tree

# Calculate motor effective densities from datasheet masses
uv run calc_motor_density.py /path/to/TRLC-DK1-Follower_v0.3.0.step
```

## Files

| File | Description |
|---|---|
| `analyze_step.py` | Main analysis script. Reads STEP via XCAF, groups parts by link, computes mass properties. |
| `calc_motor_density.py` | Helper to back-calculate effective densities from known motor masses and CAD volumes. |
| `link_mapping.json` | Maps STEP part instance names to URDF link names. |
| `material_map.json` | Per-part density overrides via substring pattern matching on part names. |

## How it works

1. The STEP file is read using OpenCascade's XCAF document reader, which preserves the assembly hierarchy and part names.
2. Top-level (depth-1) parts are matched to URDF links via `link_mapping.json`.
3. For each part, density is determined by substring-matching the part name against patterns in `material_map.json`. Unmatched parts use the `--density` default (1220 kg/m³ for PLA-CF).
4. Sub-assemblies (e.g. "Gripper Assembly") are recursed into so each internal part gets its own density.
5. Mass properties are combined per link using the parallel axis theorem.
6. STEP geometry is in mm; output is in SI units (m, kg, kg*m^2).

## Current best estimate (2025-02)

Default PLA-CF density: 1220 kg/m^3 (Bambu Lab PLA-CF, TDS V3, 100% infill).

| Link | Mass (g) | Solids | Notes |
|---|---|---|---|
| base_link | 408.5 | 19 | DM-J4340P + link0-1 shell |
| link1-2 | 444.2 | 7 | DM-J4340 + shaft extension + adapter |
| link2-3 | 749.7 | 47 | DM-J4340 + 2x 6803ZZ bearings + frame |
| link3-4 | 642.7 | 33 | DM-J4310 + 6803ZZ bearing + frame |
| link4-5 | 339.2 | 12 | DM-J4310 + cable cover |
| link5-6 | 352.0 | 14 | DM-J4310 + 2x shaft extensions |
| link6-7 | 638.2 | 70 | Gripper assembly (DM-J4310, MGN9, rack, PLA-CF parts) |
| **Total** | **3574.5** | **202** | + ~77g unmapped screws |

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

## Known limitations

- **CoM values are in the global STEP coordinate frame**, not link-local. Transforming to link-local requires the joint origins from the URDF.
- **127 screws (~77g) are unmapped** and not assigned to specific links.
- **MGN9 rail/carriage CAD models** may be simplified solid blocks, possibly overestimating their volume and therefore mass.
- **Bearing 6803ZZ effective density (5500 kg/m^3)** is an estimate; real bearings have internal voids.
