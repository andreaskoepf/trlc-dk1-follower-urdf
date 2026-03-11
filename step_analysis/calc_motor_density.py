#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery"]
# ///
"""Calculate effective densities from CAD volumes and datasheet masses.

Reads the STEP file, extracts volumes for motors, bearings, and linear rail
components, and back-calculates effective densities to match known masses.

Usage:
    uv run calc_motor_density.py [path/to/file.step]
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

from analyze_step import walk_assembly, collect_depth1_parts, extract_solids_from_shape


DEFAULT_STEP_FILE = "TRLC-DK1-Follower_v0.3.0.step"

# Known components with datasheet masses (in grams).
# "path" is a list of name substrings to walk into nested assemblies.
# A single-element path matches depth-1 parts; multi-element paths recurse.
COMPONENTS = [
    # Motors (depth-1 parts)
    {"path": ["DM-J4340P-2EC v5:1"],     "mass_g": 375, "type": "DM-J4340P-2EC"},
    {"path": ["DM-J4340-2EC v5:1"],       "mass_g": 362, "type": "DM-J4340-2EC"},
    {"path": ["DM-J4340-2EC v5:2"],       "mass_g": 362, "type": "DM-J4340-2EC"},
    {"path": ["DM-J4310-2EC-V1.1 v4:1"],  "mass_g": 300, "type": "DM-J4310-2EC"},
    {"path": ["DM-J4310-2EC-V1.1 v4:2"],  "mass_g": 300, "type": "DM-J4310-2EC"},
    {"path": ["DM-J4310-2EC-V1.1 v4:3"],  "mass_g": 300, "type": "DM-J4310-2EC"},
    # Bearings (depth-1 parts, each is an 18-solid sub-assembly)
    {"path": ["6803ZZ v1:1"],  "mass_g": 7, "type": "6803ZZ bearing"},
    {"path": ["6803ZZ v1:2"],  "mass_g": 7, "type": "6803ZZ bearing"},
    {"path": ["6803ZZ v1:3"],  "mass_g": 7, "type": "6803ZZ bearing"},
    # MGN9 components (inside Gripper Assembly sub-assembly)
    {"path": ["Gripper Assembly", "MGN9 Rail 150mm"],  "mass_g": 57, "type": "MGN9 Rail 150mm"},
    {"path": ["Gripper Assembly", "MGN9-C v2 v2:1"],   "mass_g": 26, "type": "MGN9C carriage"},
    {"path": ["Gripper Assembly", "MGN9-C v2 v2:2"],   "mass_g": 26, "type": "MGN9C carriage"},
]


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


def find_node_by_path(root_children, path):
    """Walk into the assembly tree following a path of name substrings.
    Returns the matching node or None.
    """
    current_children = root_children
    node = None
    for segment in path:
        found = False
        for child in current_children:
            key = child.get("instance_name", child["name"]) or ""
            name = child["name"] or ""
            if segment in key or segment in name:
                node = child
                current_children = child.get("children", [])
                found = True
                break
        if not found:
            return None
    return node


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

    print(f"\n{'Component':<40} | {'Type':<20} | {'Solids':>6} | {'Vol (mm³)':>14} | {'Vol (cm³)':>10} | {'Mass (g)':>8} | {'Eff. Density':>14}")
    print("-" * 125)

    type_data = {}

    for comp in COMPONENTS:
        path = comp["path"]
        mass_g = comp["mass_g"]
        ctype = comp["type"]
        label = " > ".join(path) if len(path) > 1 else path[0]

        node = find_node_by_path(tree["children"], path)
        if node is None:
            print(f"  WARNING: {label} not found")
            continue

        vol_mm3 = get_total_volume_mm3(node)
        vol_cm3 = vol_mm3 / 1000.0
        n_solids = node["num_solids"]
        vol_m3 = vol_mm3 * 1e-9
        eff_density = (mass_g / 1000.0) / vol_m3 if vol_m3 > 0 else 0

        print(f"  {label:<38} | {ctype:<20} | {n_solids:>6} | {vol_mm3:>14.1f} | {vol_cm3:>10.2f} | {mass_g:>8} | {eff_density:>11.0f} kg/m³")

        if ctype not in type_data:
            type_data[ctype] = []
        type_data[ctype].append({"vol_mm3": vol_mm3, "mass_g": mass_g, "eff_density": eff_density})

    print(f"\n\n{'='*90}")
    print("Summary by component type (for material_map.json):")
    print(f"{'='*90}")
    print(f"\n{'Type':<22} | {'Avg Vol (cm³)':>14} | {'Mass (g)':>8} | {'Eff. Density':>14}")
    print("-" * 74)

    for ctype, entries in type_data.items():
        avg_vol = sum(e["vol_mm3"] for e in entries) / len(entries)
        avg_density = sum(e["eff_density"] for e in entries) / len(entries)
        mass_g = entries[0]["mass_g"]
        print(f"  {ctype:<20} | {avg_vol/1000:>14.2f} | {mass_g:>8} | {avg_density:>11.0f} kg/m³")


if __name__ == "__main__":
    main()
