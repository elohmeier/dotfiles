# ty: ignore[import-not-found, unresolved-attribute]
# FreeCAD supplies its Python API in the embedded interpreter.
"""Export selected finished solids as STEP and open them in PrusaSlicer."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import subprocess
from collections.abc import Callable

import FreeCAD as App
import FreeCADGui as Gui
import Part
from PySide import QtWidgets


def slicer_executable() -> Path:
    """Find the installed macOS application."""
    for folder in (Path.home() / "Applications", Path("/Applications")):
        candidate = folder / "PrusaSlicer.app/Contents/MacOS/PrusaSlicer"
        if candidate.is_file():
            return candidate
    raise RuntimeError("PrusaSlicer.app was not found in Applications.")


def finished_solids(objects: list[App.DocumentObject]) -> list[App.DocumentObject]:
    """Promote Part Design features to their finished body and remove duplicates."""
    if not objects:
        raise ValueError("Select a finished body or solid in the model tree first.")
    result = []
    seen = set()
    for obj in objects:
        if hasattr(obj, "getParentGeoFeatureGroup"):
            parent = obj.getParentGeoFeatureGroup()
            if parent and parent.isDerivedFrom("PartDesign::Body"):
                obj = parent
        key = (obj.Document.Name, obj.Name)
        if key in seen:
            continue
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull() or not shape.Solids:
            raise ValueError(
                f"{obj.Label}: select a finished body or solid, rather than a sketch or group."
            )
        if not shape.isValid():
            raise ValueError(
                f"{obj.Label}: the solid is invalid; repair it before exporting."
            )
        seen.add(key)
        result.append(obj)
    return result


def export_objects(objects: list[App.DocumentObject]) -> Path:
    """Write a stable STEP path so PrusaSlicer can reload later revisions."""
    objects = finished_solids(objects)
    documents = {obj.Document.Name: obj.Document for obj in objects}
    for document in documents.values():
        document.recompute()
    objects = finished_solids(objects)
    identity = "|".join(
        sorted(
            f"{obj.Document.FileName or obj.Document.Name}:{obj.Name}"
            for obj in objects
        )
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
    name = "-".join([objects[0].Document.Label, *[obj.Name for obj in objects]])
    name = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")[:100] or "model"
    folder = Path(App.getUserAppDataDir()) / "PrusaSlicerExports"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / f"{name}-{digest}.step"
    # Replace only after a complete export; an interrupted export keeps the previous file.
    temporary = folder / f"{name}-{digest}.pending.step"
    try:
        Part.export(objects, str(temporary))
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise RuntimeError("FreeCAD did not create a STEP file.")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def send_selected(launch: Callable = subprocess.Popen) -> Path:
    """Send the active document's selected bodies to the existing slicer window."""
    executable = slicer_executable()
    document = App.ActiveDocument
    if document is None:
        raise ValueError("Open a document and select its finished body first.")
    output = export_objects(Gui.Selection.getSelection(document.Name))
    launch([str(executable), "--single-instance", str(output)])
    message = f"Sent to PrusaSlicer: {output}"
    App.Console.PrintMessage(message + "\n")
    Gui.getMainWindow().statusBar().showMessage(message, 15000)
    return output


def main() -> None:
    try:
        send_selected()
    except Exception as exc:
        message = str(exc)
        App.Console.PrintError(f"Send to PrusaSlicer: {message}\n")
        Gui.getMainWindow().statusBar().showMessage(message, 15000)
        QtWidgets.QMessageBox.warning(
            Gui.getMainWindow(), "Send to PrusaSlicer", message
        )


if __name__ == "__main__":
    main()
