#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery", "numpy"]
# ///
"""Analyze a STEP assembly file and extract mass properties (volume, CoM, inertia)
grouped by URDF links, suitable for URDF link definitions.

Usage:
    uv run analyze_step.py <step_file> [--density DENSITY] [--urdf] [--link-map FILE]

Density is in kg/m³ (default: 1250 for PLA). The STEP file is assumed to use mm units.
"""

import argparse
import json
import sys
import numpy as np

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopoDS import TopoDS


def get_label_name(label):
    """Get the name string from an XDE label."""
    from OCP.TDataStd import TDataStd_Name
    name_attr = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), name_attr):
        return name_attr.Get().ToExtString()
    return ""


def compute_volume_properties(solid):
    """Compute volume-based geometric properties for a solid (density-independent).
    Assumes STEP geometry is in mm. Returns volume in mm³, CoM in m, and
    inertia matrix scale factor in mm⁵ (multiply by density_kg_m3 * 1e-15 for kg·m²).
    """
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)

    volume_mm3 = props.Mass()
    com = props.CentreOfMass()
    com_m = np.array([com.X() * 1e-3, com.Y() * 1e-3, com.Z() * 1e-3])

    mat = props.MatrixOfInertia()
    # Raw inertia in mm⁵ (volume-weighted, not mass-weighted)
    inertia_raw = np.array([
        [mat.Value(1, 1), mat.Value(1, 2), mat.Value(1, 3)],
        [mat.Value(2, 1), mat.Value(2, 2), mat.Value(2, 3)],
        [mat.Value(3, 1), mat.Value(3, 2), mat.Value(3, 3)],
    ])

    return {"volume_mm3": volume_mm3, "com": com_m, "inertia_raw": inertia_raw}


def apply_density(vol_props, density_kg_m3):
    """Apply a density to volume properties to get mass properties."""
    volume_m3 = vol_props["volume_mm3"] * 1e-9
    mass_kg = volume_m3 * density_kg_m3
    scale = density_kg_m3 * 1e-15
    inertia = vol_props["inertia_raw"] * scale
    return {
        "mass": mass_kg,
        "com": vol_props["com"].copy(),
        "inertia": inertia,
        "volume_mm3": vol_props["volume_mm3"],
    }


def get_part_density(part_key, material_patterns, default_density):
    """Look up density for a part based on pattern matching.
    Returns (density, material_name) tuple.
    """
    for entry in material_patterns:
        if entry["pattern"] in part_key:
            return entry["density"], entry.get("material", entry["pattern"])
    return default_density, "default"


def compute_node_solids_with_materials(node, material_patterns, default_density):
    """Recursively compute solid properties for a node, applying per-part densities
    based on material pattern matching at each level of the assembly tree.

    For leaf parts, applies density based on the part name.
    For assemblies, recurses into children so each sub-part gets its own density.
    Returns list of (solid_props_dict, part_name, density, material_name) tuples.
    """
    results = []
    name = node.get("instance_name", node["name"]) or "(unnamed)"

    if node["children"]:
        # Assembly: recurse into children for per-part density
        for child in node["children"]:
            results.extend(compute_node_solids_with_materials(
                child, material_patterns, default_density))
    else:
        # Leaf part: apply density based on name
        shape = node["shape"]
        if shape is not None:
            part_density, mat_name = get_part_density(name, material_patterns, default_density)
            solids = extract_solids_from_shape(shape)
            for solid in solids:
                vol_props = compute_volume_properties(solid)
                solid_props = apply_density(vol_props, part_density)
                results.append((solid_props, name, part_density, mat_name))

    return results


def combine_properties(solids_data):
    """Combine mass properties from multiple solids using parallel axis theorem."""
    if not solids_data:
        return None

    total_mass = sum(s["mass"] for s in solids_data)
    if total_mass < 1e-12:
        return None

    combined_com = np.zeros(3)
    for s in solids_data:
        combined_com += s["mass"] * s["com"]
    combined_com /= total_mass

    combined_inertia = np.zeros((3, 3))
    for s in solids_data:
        d = s["com"] - combined_com
        combined_inertia += s["inertia"] + s["mass"] * (
            np.dot(d, d) * np.eye(3) - np.outer(d, d)
        )

    total_volume_mm3 = sum(s["volume_mm3"] for s in solids_data)

    return {
        "volume_mm3": total_volume_mm3,
        "volume_m3": total_volume_mm3 * 1e-9,
        "mass_kg": total_mass,
        "com_m": tuple(combined_com),
        "ixx": combined_inertia[0, 0],
        "iyy": combined_inertia[1, 1],
        "izz": combined_inertia[2, 2],
        "ixy": combined_inertia[0, 1],
        "ixz": combined_inertia[0, 2],
        "iyz": combined_inertia[1, 2],
        "num_solids": len(solids_data),
    }


def extract_solids_from_shape(shape):
    """Extract all solid bodies from a shape."""
    solids = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        solids.append(TopoDS.Solid_s(explorer.Current()))
        explorer.Next()
    return solids


def count_solids(shape):
    """Count number of solids in a shape."""
    return len(extract_solids_from_shape(shape))


def format_urdf_inertial(props, name=""):
    """Format mass properties as a URDF <inertial> element."""
    com = props["com_m"]
    lines = []
    lines.append(f"  <!-- {name} -->" if name else "  <!-- link -->")
    lines.append(f"  <inertial>")
    lines.append(f'    <origin xyz="{com[0]:.6g} {com[1]:.6g} {com[2]:.6g}" rpy="0 0 0" />')
    lines.append(f'    <mass value="{props["mass_kg"]:.4f}" />')
    lines.append(
        f'    <inertia ixx="{props["ixx"]:.5e}" ixy="{props["ixy"]:.5e}" '
        f'ixz="{props["ixz"]:.5e}" iyy="{props["iyy"]:.5e}" '
        f'iyz="{props["iyz"]:.5e}" izz="{props["izz"]:.5e}" />'
    )
    lines.append(f"  </inertial>")
    return "\n".join(lines)


def walk_assembly(shape_tool, label, depth=0):
    """Recursively walk the assembly tree and return info about each node."""
    name = get_label_name(label)
    is_assembly = shape_tool.IsAssembly_s(label)
    shape = shape_tool.GetShape_s(label)
    n_solids = count_solids(shape) if shape is not None else 0

    info = {
        "name": name,
        "depth": depth,
        "is_assembly": is_assembly,
        "num_solids": n_solids,
        "shape": shape,
        "children": [],
    }

    if is_assembly:
        components = TDF_LabelSequence()
        shape_tool.GetComponents_s(label, components)
        for i in range(components.Size()):
            child_label = components.Value(i + 1)
            ref_label = TDF_Label()
            if shape_tool.GetReferredShape_s(child_label, ref_label):
                child_info = walk_assembly(shape_tool, ref_label, depth + 1)
                comp_name = get_label_name(child_label)
                if comp_name and not child_info["name"]:
                    child_info["name"] = comp_name
                elif comp_name and comp_name != child_info["name"]:
                    child_info["instance_name"] = comp_name
                info["children"].append(child_info)
            else:
                child_info = walk_assembly(shape_tool, child_label, depth + 1)
                info["children"].append(child_info)

    return info


def print_tree(node, indent=0):
    """Print the assembly tree structure."""
    prefix = "  " * indent
    name = node["name"] or "(unnamed)"
    instance = node.get("instance_name", "")
    inst_str = f" [instance: {instance}]" if instance else ""
    type_str = "ASM" if node["is_assembly"] else "PART"
    n = node["num_solids"]
    print(f"{prefix}{type_str} {name}{inst_str} ({n} solids)")
    for child in node["children"]:
        print_tree(child, indent + 1)


def collect_depth1_parts(tree):
    """Collect all depth-1 children with their instance names."""
    parts = []
    for child in tree["children"]:
        instance_name = child.get("instance_name", "")
        name = child["name"] or "(unnamed)"
        # The instance name is the unique identifier (e.g. "link1-2 v6:1")
        key = instance_name if instance_name else name
        parts.append({"key": key, "name": name, "node": child})
    return parts


def main():
    parser = argparse.ArgumentParser(description="Analyze STEP assembly for URDF mass properties")
    parser.add_argument("step_file", help="Path to the STEP file")
    parser.add_argument("--density", type=float, default=1250.0,
                        help="Material density in kg/m³ (default: 1250 for PLA)")
    parser.add_argument("--urdf", action="store_true",
                        help="Output URDF <inertial> snippets")
    parser.add_argument("--tree", action="store_true",
                        help="Print the full assembly tree")
    parser.add_argument("--link-map", type=str, default=None,
                        help="JSON file mapping URDF link names to lists of STEP part instance names")
    parser.add_argument("--material-map", type=str, default=None,
                        help="JSON file with material density patterns for per-part density overrides")
    parser.add_argument("--list-parts", action="store_true",
                        help="List all depth-1 part instance names (useful for building a link mapping)")
    args = parser.parse_args()

    # Load material patterns if provided
    material_patterns = []
    if args.material_map:
        with open(args.material_map) as f:
            mat_data = json.load(f)
        material_patterns = mat_data.get("patterns", [])

    print(f"Reading STEP file: {args.step_file}")

    doc = TDocStd_Document(TCollection_ExtendedString("STEP"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetLayerMode(True)
    reader.SetColorMode(True)

    status = reader.ReadFile(args.step_file)
    if status != 1:
        print(f"Error: Could not read STEP file (status={status})")
        sys.exit(1)

    reader.Transfer(doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())

    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    print(f"Found {roots.Size()} root shape(s)")

    for i in range(roots.Size()):
        root_label = roots.Value(i + 1)
        tree = walk_assembly(shape_tool, root_label)

        if args.tree:
            print("\n=== Assembly Tree ===")
            print_tree(tree)

        depth1_parts = collect_depth1_parts(tree)

        if args.list_parts:
            print(f"\n=== Depth-1 Parts ({len(depth1_parts)}) ===")
            print("Use these instance names in the link mapping JSON file.\n")
            for p in depth1_parts:
                n_solids = p["node"]["num_solids"]
                print(f"  {p['key']:<60} ({n_solids} solids)")
            return

        # Build a lookup from instance key to node
        part_lookup = {}
        for p in depth1_parts:
            part_lookup[p["key"]] = p["node"]

        if args.link_map:
            # Load link mapping and compute grouped properties
            with open(args.link_map) as f:
                link_map = json.load(f)
            # Remove comment keys
            link_map = {k: v for k, v in link_map.items() if not k.startswith("_")}

            if material_patterns:
                print(f"\nUsing material map: {args.material_map} ({len(material_patterns)} patterns)")
                print(f"Default density: {args.density} kg/m³")
            else:
                print(f"\nUsing uniform density: {args.density} kg/m³")
            print(f"Link mapping: {args.link_map} ({len(link_map)} links)")
            print("=" * 110)

            mapped_keys = set()
            total_mass = 0.0
            all_link_props = []

            for link_name, part_keys in link_map.items():
                link_solids_data = []
                part_names_found = []

                for pk in part_keys:
                    if pk not in part_lookup:
                        print(f"  WARNING: Part '{pk}' not found in STEP file")
                        continue
                    mapped_keys.add(pk)
                    node = part_lookup[pk]

                    if material_patterns:
                        # Recurse into sub-assemblies for per-part density
                        part_results = compute_node_solids_with_materials(
                            node, material_patterns, args.density)
                        # Collect unique materials used
                        materials_used = {}
                        for sp, pn, dens, mn in part_results:
                            link_solids_data.append(sp)
                            if mn not in materials_used:
                                materials_used[mn] = dens
                        mat_strs = [f"{mn}: {d}" for mn, d in materials_used.items()]
                        mat_info = f" [{', '.join(mat_strs)} kg/m³]" if any(m != "default" for m in materials_used) else ""
                        part_names_found.append(f"{pk} ({len(part_results)} solids){mat_info}")
                    else:
                        shape = node["shape"]
                        if shape is None:
                            continue
                        solids = extract_solids_from_shape(shape)
                        for solid in solids:
                            vol_props = compute_volume_properties(solid)
                            solid_props = apply_density(vol_props, args.density)
                            link_solids_data.append(solid_props)
                        part_names_found.append(f"{pk} ({len(solids)} solids)")

                props = combine_properties(link_solids_data)
                if props is None:
                    print(f"\n{link_name}: no valid solids")
                    continue

                total_mass += props["mass_kg"]
                all_link_props.append((link_name, props))

                com = props["com_m"]
                print(f"\n{link_name} ({props['num_solids']} solids from {len(part_names_found)} parts):")
                for pn in part_names_found:
                    print(f"    {pn}")
                print(f"  Volume:  {props['volume_mm3']:.1f} mm³  ({props['volume_m3']*1e6:.2f} cm³)")
                print(f"  Mass:    {props['mass_kg']:.4f} kg  ({props['mass_kg']*1000:.1f} g)")
                print(f"  CoM (m): ({com[0]:.6f}, {com[1]:.6f}, {com[2]:.6f})")
                print(f"  Inertia (kg·m²) at CoM:")
                print(f"    Ixx={props['ixx']:.5e}  Iyy={props['iyy']:.5e}  Izz={props['izz']:.5e}")
                print(f"    Ixy={props['ixy']:.5e}  Ixz={props['ixz']:.5e}  Iyz={props['iyz']:.5e}")

                if args.urdf:
                    print()
                    print(format_urdf_inertial(props, link_name))

            # Show unmapped parts
            unmapped = [p for p in depth1_parts if p["key"] not in mapped_keys]
            if unmapped:
                unmapped_mass = 0.0
                print(f"\n{'='*110}")
                print(f"Unmapped parts ({len(unmapped)}):")
                for p in unmapped:
                    shape = p["node"]["shape"]
                    if shape is not None:
                        part_density, _ = get_part_density(p["key"], material_patterns, args.density)
                        solids = extract_solids_from_shape(shape)
                        for solid in solids:
                            vol_props = compute_volume_properties(solid)
                            sp = apply_density(vol_props, part_density)
                            unmapped_mass += sp["mass"]
                    n = p["node"]["num_solids"]
                    print(f"  {p['key']:<60} ({n} solids)")
                print(f"  Unmapped mass: {unmapped_mass:.4f} kg ({unmapped_mass*1000:.1f} g)")

            print(f"\n{'='*110}")
            print(f"Total mapped mass:   {total_mass:.4f} kg ({total_mass*1000:.1f} g)")

            # Summary table
            print(f"\n{'Link':<15} | {'Solids':>6} | {'Mass (g)':>10} | {'CoM X (m)':>12} | {'CoM Y (m)':>12} | {'CoM Z (m)':>12}")
            print("-" * 85)
            for name, props in all_link_props:
                com = props["com_m"]
                print(f"  {name:<13} | {props['num_solids']:>6} | {props['mass_kg']*1000:>10.1f} | {com[0]:>12.6f} | {com[1]:>12.6f} | {com[2]:>12.6f}")

        else:
            # No link map: show per-part properties
            if material_patterns:
                print(f"\nUsing material map: {args.material_map} ({len(material_patterns)} patterns)")
                print(f"Default density: {args.density} kg/m³")
            else:
                print(f"\nUsing uniform density: {args.density} kg/m³")
            print(f"Found {len(depth1_parts)} depth-1 parts")
            print("=" * 110)

            total_mass = 0.0
            all_props = []

            for p in depth1_parts:
                name = p["key"]
                shape = p["node"]["shape"]
                if shape is None:
                    continue

                part_density, mat_name = get_part_density(name, material_patterns, args.density)
                solids = extract_solids_from_shape(shape)
                solids_data = [apply_density(compute_volume_properties(s), part_density) for s in solids]
                props = combine_properties(solids_data)
                if props is None:
                    continue

                total_mass += props["mass_kg"]
                all_props.append((name, props))

                com = props["com_m"]
                print(f"\n{name} ({props['num_solids']} solids):")
                print(f"  Volume:  {props['volume_mm3']:.1f} mm³  ({props['volume_m3']*1e6:.2f} cm³)")
                print(f"  Mass:    {props['mass_kg']:.4f} kg  ({props['mass_kg']*1000:.1f} g)")
                print(f"  CoM (m): ({com[0]:.6f}, {com[1]:.6f}, {com[2]:.6f})")
                print(f"  Inertia (kg·m²) at CoM:")
                print(f"    Ixx={props['ixx']:.5e}  Iyy={props['iyy']:.5e}  Izz={props['izz']:.5e}")
                print(f"    Ixy={props['ixy']:.5e}  Ixz={props['ixz']:.5e}  Iyz={props['iyz']:.5e}")

                if args.urdf:
                    print()
                    print(format_urdf_inertial(props, name))

            print(f"\n{'='*110}")
            print(f"Total mass: {total_mass:.4f} kg ({total_mass*1000:.1f} g)")


if __name__ == "__main__":
    main()
