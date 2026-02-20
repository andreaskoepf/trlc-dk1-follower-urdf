#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery"]
# ///
"""Calculate effective motor densities from CAD volumes and datasheet masses.

Reads the STEP file, extracts volumes for each motor instance, and back-calculates
the effective density needed to match datasheet masses.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopoDS import TopoDS

from analyze_step import walk_assembly, collect_depth1_parts, get_label_name, extract_solids_from_shape


DEFAULT_STEP_FILE = "TRLC-DK1-Follower_v0.3.0.step"

# Motor instances in the STEP file and their datasheet masses
MOTORS = {
    "DM-J4340P-2EC v5:1":      {"datasheet_mass_g": 375,  "type": "DM-J4340P-2EC"},
    "DM-J4340-2EC v5:1":       {"datasheet_mass_g": 362,  "type": "DM-J4340-2EC"},
    "DM-J4340-2EC v5:2":       {"datasheet_mass_g": 362,  "type": "DM-J4340-2EC"},
    "DM-J4310-2EC-V1.1 v4:1":  {"datasheet_mass_g": 300,  "type": "DM-J4310-2EC"},
    "DM-J4310-2EC-V1.1 v4:2":  {"datasheet_mass_g": 300,  "type": "DM-J4310-2EC"},
    "DM-J4310-2EC-V1.1 v4:3":  {"datasheet_mass_g": 300,  "type": "DM-J4310-2EC"},
}


def get_total_volume_mm3(node):
    """Get total volume in mm³ for all solids in a node (recursively)."""
    total_vol = 0.0
    if node["children"]:
        for child in node["children"]:
            total_vol += get_total_volume_mm3(child)
    else:
        shape = node["shape"]
        if shape is not None:
            solids = extract_solids_from_shape(shape)
            for solid in solids:
                props = GProp_GProps()
                BRepGProp.VolumeProperties_s(solid, props)
                total_vol += props.Mass()  # volume in mm³
    return total_vol


def main():
    step_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_STEP_FILE
    print(f"Reading STEP file: {step_file}")

    doc = TDocStd_Document(TCollection_ExtendedString("STEP"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetLayerMode(True)
    reader.SetColorMode(True)

    status = reader.ReadFile(step_file)
    if status != 1:
        print(f"Error: Could not read STEP file (status={status})")
        sys.exit(1)

    reader.Transfer(doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)

    root_label = roots.Value(1)
    tree = walk_assembly(shape_tool, root_label)
    depth1_parts = collect_depth1_parts(tree)

    part_lookup = {p["key"]: p["node"] for p in depth1_parts}

    print(f"\n{'Motor Instance':<35} | {'Type':<18} | {'Solids':>6} | {'Vol (mm³)':>14} | {'Vol (cm³)':>10} | {'DS Mass (g)':>10} | {'Eff. Density':>12}")
    print("-" * 130)

    # Group by motor type for averaging
    type_volumes = {}

    for motor_key, info in MOTORS.items():
        if motor_key not in part_lookup:
            print(f"  WARNING: {motor_key} not found")
            continue

        node = part_lookup[motor_key]
        vol_mm3 = get_total_volume_mm3(node)
        vol_cm3 = vol_mm3 / 1000.0
        n_solids = node["num_solids"]

        mtype = info["type"]
        ds_mass = info["datasheet_mass_g"]

        if ds_mass is not None:
            vol_m3 = vol_mm3 * 1e-9
            mass_kg = ds_mass / 1000.0
            eff_density = mass_kg / vol_m3 if vol_m3 > 0 else 0
            dens_str = f"{eff_density:.0f} kg/m³"
        else:
            eff_density = None
            dens_str = "N/A (no mass)"

        ds_str = f"{ds_mass}" if ds_mass else "unknown"

        print(f"  {motor_key:<33} | {mtype:<18} | {n_solids:>6} | {vol_mm3:>14.1f} | {vol_cm3:>10.2f} | {ds_str:>10} | {dens_str:>12}")

        if mtype not in type_volumes:
            type_volumes[mtype] = []
        type_volumes[mtype].append({"vol_mm3": vol_mm3, "ds_mass_g": ds_mass, "eff_density": eff_density})

    print(f"\n\n{'='*80}")
    print("Summary by motor type:")
    print(f"{'='*80}")
    print(f"\n{'Motor Type':<20} | {'Avg Vol (cm³)':>14} | {'DS Mass (g)':>10} | {'Recommended Eff. Density':>25}")
    print("-" * 80)

    for mtype, entries in type_volumes.items():
        avg_vol_mm3 = sum(e["vol_mm3"] for e in entries) / len(entries)
        avg_vol_cm3 = avg_vol_mm3 / 1000.0
        ds_mass = entries[0]["ds_mass_g"]
        densities = [e["eff_density"] for e in entries if e["eff_density"] is not None]

        if densities:
            avg_density = sum(densities) / len(densities)
            print(f"  {mtype:<18} | {avg_vol_cm3:>14.2f} | {ds_mass:>10} | {avg_density:>22.0f} kg/m³")
        else:
            print(f"  {mtype:<18} | {avg_vol_cm3:>14.2f} | {'unknown':>10} | {'(need datasheet mass)':>25}")

    # Also compute what the J4340P density would be if it weighs the same as J4340 (362g) or more
    j4340p_entries = type_volumes.get("DM-J4340P-2EC", [])
    if j4340p_entries:
        vol_mm3 = j4340p_entries[0]["vol_mm3"]
        vol_m3 = vol_mm3 * 1e-9
        print(f"\n\nDM-J4340P-2EC density estimates (volume = {vol_mm3/1000:.2f} cm³):")
        for guess_g in [362, 375, 400, 450, 500]:
            dens = (guess_g / 1000.0) / vol_m3
            print(f"  If mass = {guess_g}g → effective density = {dens:.0f} kg/m³")


if __name__ == "__main__":
    main()
