#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery"]
# ///
"""List part colors from a STEP file to help identify materials."""

import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.Quantity import Quantity_Color

from analyze_step import walk_assembly, collect_depth1_parts


def get_color(color_tool, label):
    """Get color associated with a label, trying all color types."""
    color = Quantity_Color()
    for ct in [XCAFDoc_ColorType.XCAFDoc_ColorGen,
               XCAFDoc_ColorType.XCAFDoc_ColorSurf,
               XCAFDoc_ColorType.XCAFDoc_ColorCurv]:
        if color_tool.GetColor_s(label, ct, color):
            r, g, b = color.Red(), color.Green(), color.Blue()
            return f"({r:.2f}, {g:.2f}, {b:.2f})"
    return None


def walk_colors(color_tool, shape_tool, node, depth=0):
    """Walk the assembly tree printing colors for each node."""
    name = node.get("instance_name", node["name"]) or "(unnamed)"
    prefix = "  " * depth

    # Try to find color for this node's label
    # We'll collect colors from children too
    if node["children"]:
        child_colors = set()
        print(f"{prefix}ASM {name}")
        for child in node["children"]:
            walk_colors(color_tool, shape_tool, child, depth + 1)
    else:
        print(f"{prefix}PART {name}")


def main():
    step_file = sys.argv[1] if len(sys.argv) > 1 else "TRLC-DK1-Follower_v0.3.0.step"
    print(f"Reading STEP file: {step_file}")

    doc = TDocStd_Document(TCollection_ExtendedString("STEP"))
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(True)

    status = reader.ReadFile(step_file)
    if status != 1:
        print(f"Error: Could not read STEP file (status={status})")
        sys.exit(1)

    reader.Transfer(doc)
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    color_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())

    # Get all colors defined in the document
    color_labels = TDF_LabelSequence()
    color_tool.GetColors(color_labels)
    print(f"\nDefined colors: {color_labels.Size()}")
    for i in range(color_labels.Size()):
        cl = color_labels.Value(i + 1)
        color = Quantity_Color()
        color_tool.GetColor_s(cl, color)
        r, g, b = color.Red(), color.Green(), color.Blue()
        print(f"  Color {i}: ({r:.3f}, {g:.3f}, {b:.3f})")

    # Walk depth-1 parts and check colors
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    root_label = roots.Value(1)

    # Get all shape labels and check their colors
    all_labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(all_labels)

    print(f"\n{'Part':<65} | {'Color':>20}")
    print("-" * 90)

    # Walk the full label tree to find colors
    def check_label_colors(label, depth=0):
        from analyze_step import get_label_name
        name = get_label_name(label)
        color = Quantity_Color()
        found_color = None
        for ct in [XCAFDoc_ColorType.XCAFDoc_ColorGen,
                   XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                   XCAFDoc_ColorType.XCAFDoc_ColorCurv]:
            if color_tool.GetColor_s(label, ct, color):
                r, g, b = color.Red(), color.Green(), color.Blue()
                found_color = f"({r:.3f}, {g:.3f}, {b:.3f})"
                break

        if name and found_color:
            prefix = "  " * depth
            print(f"  {prefix}{name:<60} | {found_color}")

        # Check if assembly
        if shape_tool.IsAssembly_s(label):
            components = TDF_LabelSequence()
            shape_tool.GetComponents_s(label, components)
            for j in range(components.Size()):
                child_label = components.Value(j + 1)
                # Check the component (instance) label
                comp_name = get_label_name(child_label)
                color2 = Quantity_Color()
                comp_color = None
                for ct in [XCAFDoc_ColorType.XCAFDoc_ColorGen,
                           XCAFDoc_ColorType.XCAFDoc_ColorSurf,
                           XCAFDoc_ColorType.XCAFDoc_ColorCurv]:
                    if color_tool.GetColor_s(child_label, ct, color2):
                        r, g, b = color2.Red(), color2.Green(), color2.Blue()
                        comp_color = f"({r:.3f}, {g:.3f}, {b:.3f})"
                        break

                if comp_name and comp_color:
                    prefix = "  " * (depth + 1)
                    print(f"  {prefix}{comp_name:<55} | {comp_color}")

                # Also check the referred shape
                ref_label = TDF_Label()
                if shape_tool.GetReferredShape_s(child_label, ref_label):
                    check_label_colors(ref_label, depth + 1)
                else:
                    check_label_colors(child_label, depth + 1)

    for i in range(all_labels.Size()):
        check_label_colors(all_labels.Value(i + 1))


if __name__ == "__main__":
    main()
