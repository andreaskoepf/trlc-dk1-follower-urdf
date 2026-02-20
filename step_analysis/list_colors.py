#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["cadquery"]
# ///
"""List part colors from a STEP file to help identify materials.

Usage:
    uv run list_colors.py <step_file>
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence, TDF_Label
from OCP.Quantity import Quantity_Color

from analyze_step import get_label_name

COLOR_TYPES = [
    XCAFDoc_ColorType.XCAFDoc_ColorGen,
    XCAFDoc_ColorType.XCAFDoc_ColorSurf,
    XCAFDoc_ColorType.XCAFDoc_ColorCurv,
]


def get_label_color(color_tool, label):
    """Get RGB color tuple for a label, or None."""
    color = Quantity_Color()
    for ct in COLOR_TYPES:
        if color_tool.GetColor_s(label, ct, color):
            return (color.Red(), color.Green(), color.Blue())
    return None


def format_color(rgb):
    """Format an RGB tuple as a string."""
    return f"({rgb[0]:.3f}, {rgb[1]:.3f}, {rgb[2]:.3f})"


def walk_label_colors(shape_tool, color_tool, label, depth=0):
    """Recursively walk labels and print colors."""
    name = get_label_name(label)
    rgb = get_label_color(color_tool, label)

    if name and rgb:
        prefix = "  " * depth
        print(f"  {prefix}{name:<60} | {format_color(rgb)}")

    if shape_tool.IsAssembly_s(label):
        components = TDF_LabelSequence()
        shape_tool.GetComponents_s(label, components)
        for j in range(components.Size()):
            child_label = components.Value(j + 1)
            comp_name = get_label_name(child_label)
            comp_rgb = get_label_color(color_tool, child_label)

            if comp_name and comp_rgb:
                prefix = "  " * (depth + 1)
                print(f"  {prefix}{comp_name:<55} | {format_color(comp_rgb)}")

            ref_label = TDF_Label()
            if shape_tool.GetReferredShape_s(child_label, ref_label):
                walk_label_colors(shape_tool, color_tool, ref_label, depth + 1)
            else:
                walk_label_colors(shape_tool, color_tool, child_label, depth + 1)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <step_file>")
        sys.exit(1)

    step_file = sys.argv[1]
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

    # List all colors defined in the document
    color_labels = TDF_LabelSequence()
    color_tool.GetColors(color_labels)
    print(f"\nDefined colors: {color_labels.Size()}")
    for i in range(color_labels.Size()):
        cl = color_labels.Value(i + 1)
        color = Quantity_Color()
        color_tool.GetColor_s(cl, color)
        print(f"  Color {i}: {format_color((color.Red(), color.Green(), color.Blue()))}")

    # Walk full label tree and print colors
    print(f"\n{'Part':<65} | {'Color':>20}")
    print("-" * 90)

    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    for i in range(roots.Size()):
        walk_label_colors(shape_tool, color_tool, roots.Value(i + 1))


if __name__ == "__main__":
    main()
