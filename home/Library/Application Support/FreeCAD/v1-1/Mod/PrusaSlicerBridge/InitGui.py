# ty: ignore[import-not-found, unresolved-attribute]
# FreeCAD supplies its Python API in the embedded interpreter.
"""Register the slicer macro in a global toolbar at FreeCAD startup."""


def register_slicer_button() -> str:
    from pathlib import Path

    import FreeCAD as App
    import FreeCADGui as Gui

    macro = Path(App.getUserAppDataDir()) / "Macro/SendToPrusaSlicer.FCMacro"
    command = Gui.Command.findCustomCommand(str(macro))
    if not command:
        command = Gui.Command.createCustomCommand(
            str(macro),
            "Send to PrusaSlicer",
            "Export selected finished bodies as STEP and open them in PrusaSlicer",
            "Select a body or solid, then send it to PrusaSlicer for slicing.",
            "Send selected bodies to PrusaSlicer",
            str(macro.with_suffix(".svg")),
        )
    toolbars = App.ParamGet("User parameter:BaseApp/Workbench/Global/Toolbar")
    groups = toolbars.GetGroups()
    for name in groups:
        toolbar = toolbars.GetGroup(name)
        if toolbar.GetString("Name") == "3D Printing":
            break
    else:
        index = 1
        while f"Custom_{index}" in groups:
            index += 1
        toolbar = toolbars.GetGroup(f"Custom_{index}")
        toolbar.SetString("Name", "3D Printing")
        toolbar.SetBool("Active", True)
    toolbar.SetString(command, "FreeCAD")
    return command


register_slicer_button()
