#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery"]
# ///
"""Analyze a STEP assembly file and extract mass properties grouped by URDF links.

Usage:
    uv run analyze_step.py <step_file> [--density DENSITY] [--link-map FILE] [--material-map FILE]

Density is in kg/m³ (default: 1250 for PLA). The STEP file is assumed to use mm units.
"""

import argparse
import json
import sys

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


def compute_solid_volume(solid):
    """Compute volume in mm³ for a single solid."""
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    return props.Mass()


def get_part_density(part_key, material_patterns, default_density):
    """Look up density for a part based on pattern matching.
    Returns (density, material_name) tuple.
    """
    for entry in material_patterns:
        if entry["pattern"] in part_key:
            return entry["density"], entry.get("material", entry["pattern"])
    return default_density, "default"


def compute_node_mass(node, material_patterns, default_density):
    """Recursively compute mass for a node, applying per-part densities.

    For assemblies, checks if the assembly name matches a material pattern.
    If it does, that density is propagated as the default for all children.
    Otherwise, recurses with the original default.
    Returns list of (mass_kg, volume_mm3, part_name, density, material_name) tuples.
    """
    results = []
    name = node.get("instance_name", node["name"]) or "(unnamed)"

    if node["children"]:
        # Check if the assembly itself matches a material pattern;
        # if so, propagate that density as the default for children
        asm_density, asm_mat = get_part_density(name, material_patterns, default_density)
        child_default = asm_density if asm_mat != "default" else default_density
        for child in node["children"]:
            results.extend(compute_node_mass(
                child, material_patterns, child_default))
    else:
        # Leaf part: apply density based on name
        shape = node["shape"]
        if shape is not None:
            part_density, mat_name = get_part_density(name, material_patterns, default_density)
            solids = extract_solids_from_shape(shape)
            for solid in solids:
                vol_mm3 = compute_solid_volume(solid)
                mass_kg = vol_mm3 * 1e-9 * part_density
                results.append((mass_kg, vol_mm3, name, part_density, mat_name))

    return results


def combine_mass(parts_data):
    """Combine mass data from multiple parts."""
    if not parts_data:
        return None
    total_mass = sum(p[0] for p in parts_data)
    total_vol = sum(p[1] for p in parts_data)
    return {
        "volume_mm3": total_vol,
        "volume_cm3": total_vol / 1000.0,
        "mass_kg": total_mass,
        "mass_g": total_mass * 1000.0,
        "num_solids": len(parts_data),
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
        key = instance_name if instance_name else name
        parts.append({"key": key, "name": name, "node": child})
    return parts


def main():
    parser = argparse.ArgumentParser(description="Analyze STEP assembly for URDF mass properties")
    parser.add_argument("step_file", help="Path to the STEP file")
    parser.add_argument("--density", type=float, default=1250.0,
                        help="Material density in kg/m³ (default: 1250 for PLA)")
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
            link_map = {k: v for k, v in link_map.items() if not k.startswith("_")}

            if material_patterns:
                print(f"\nUsing material map: {args.material_map} ({len(material_patterns)} patterns)")
                print(f"Default density: {args.density} kg/m³")
            else:
                print(f"\nUsing uniform density: {args.density} kg/m³")
            print(f"Link mapping: {args.link_map} ({len(link_map)} links)")
            print("=" * 90)

            mapped_keys = set()
            total_mass = 0.0
            all_link_props = []

            for link_name, part_keys in link_map.items():
                link_parts_data = []
                part_names_found = []

                for pk in part_keys:
                    if pk not in part_lookup:
                        print(f"  WARNING: Part '{pk}' not found in STEP file")
                        continue
                    mapped_keys.add(pk)
                    node = part_lookup[pk]

                    if material_patterns:
                        part_results = compute_node_mass(
                            node, material_patterns, args.density)
                        materials_used = {}
                        for mass_kg, vol_mm3, pn, dens, mn in part_results:
                            link_parts_data.append((mass_kg, vol_mm3, pn, dens, mn))
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
                            vol_mm3 = compute_solid_volume(solid)
                            mass_kg = vol_mm3 * 1e-9 * args.density
                            link_parts_data.append((mass_kg, vol_mm3, pk, args.density, "default"))
                        part_names_found.append(f"{pk} ({len(solids)} solids)")

                props = combine_mass(link_parts_data)
                if props is None:
                    print(f"\n{link_name}: no valid solids")
                    continue

                total_mass += props["mass_kg"]
                all_link_props.append((link_name, props))

                print(f"\n{link_name} ({props['num_solids']} solids from {len(part_names_found)} parts):")
                for pn in part_names_found:
                    print(f"    {pn}")
                print(f"  Volume:  {props['volume_mm3']:.1f} mm³  ({props['volume_cm3']:.2f} cm³)")
                print(f"  Mass:    {props['mass_kg']:.4f} kg  ({props['mass_g']:.1f} g)")

            # Show unmapped parts
            unmapped = [p for p in depth1_parts if p["key"] not in mapped_keys]
            if unmapped:
                unmapped_mass = 0.0
                print(f"\n{'='*90}")
                print(f"Unmapped parts ({len(unmapped)}):")
                for p in unmapped:
                    shape = p["node"]["shape"]
                    if shape is not None:
                        part_density, _ = get_part_density(p["key"], material_patterns, args.density)
                        solids = extract_solids_from_shape(shape)
                        for solid in solids:
                            vol_mm3 = compute_solid_volume(solid)
                            unmapped_mass += vol_mm3 * 1e-9 * part_density
                    n = p["node"]["num_solids"]
                    print(f"  {p['key']:<60} ({n} solids)")
                print(f"  Unmapped mass: {unmapped_mass:.4f} kg ({unmapped_mass*1000:.1f} g)")

            print(f"\n{'='*90}")
            print(f"Total mapped mass:   {total_mass:.4f} kg ({total_mass*1000:.1f} g)")

            # Summary table
            print(f"\n{'Link':<15} | {'Solids':>6} | {'Mass (g)':>10}")
            print("-" * 40)
            for name, props in all_link_props:
                print(f"  {name:<13} | {props['num_solids']:>6} | {props['mass_g']:>10.1f}")

        else:
            # No link map: show per-part properties
            if material_patterns:
                print(f"\nUsing material map: {args.material_map} ({len(material_patterns)} patterns)")
                print(f"Default density: {args.density} kg/m³")
            else:
                print(f"\nUsing uniform density: {args.density} kg/m³")
            print(f"Found {len(depth1_parts)} depth-1 parts")
            print("=" * 90)

            total_mass = 0.0
            for p in depth1_parts:
                name = p["key"]
                shape = p["node"]["shape"]
                if shape is None:
                    continue

                part_density, mat_name = get_part_density(name, material_patterns, args.density)
                solids = extract_solids_from_shape(shape)
                part_vol = sum(compute_solid_volume(s) for s in solids)
                part_mass = part_vol * 1e-9 * part_density

                total_mass += part_mass
                print(f"\n{name} ({len(solids)} solids):")
                print(f"  Volume:  {part_vol:.1f} mm³  ({part_vol/1000:.2f} cm³)")
                print(f"  Mass:    {part_mass:.4f} kg  ({part_mass*1000:.1f} g)")

            print(f"\n{'='*90}")
            print(f"Total mass: {total_mass:.4f} kg ({total_mass*1000:.1f} g)")


if __name__ == "__main__":
    main()
