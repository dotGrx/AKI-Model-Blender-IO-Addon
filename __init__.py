bl_info = {
    "name": "AKI Model format",
    "author": "Grix",
    "version": (0, 0, 1),
    "blender": (2, 81, 6),
    "location": "File > Import-Export",
    "description": "Import-Export MODEL, Import/Export Model mesh, UV's, faces",
    "warning": "",
    "doc_url": "",
    "category": "Import-Export",
}

if "bpy" in locals():
    import importlib
    if "import_akimodel" in locals():
        importlib.reload(import_akimodel)
    if "export_akimodel" in locals():
        importlib.reload(export_akimodel)


import bpy
from bpy.props import (
        BoolProperty,
        FloatProperty,
        IntProperty,
        StringProperty,
        EnumProperty,
        )
from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        path_reference_mode,
        )


class ImportAKIMODEL(bpy.types.Operator, ImportHelper):
    """Load a AKI Model file"""
    bl_idname = "import_scene.model"
    bl_label = "Import MODEL"
    bl_options = {'PRESET', 'UNDO'}

    filename_ext = ".model"
    filter_glob: StringProperty(default="*.model", options={'HIDDEN'})
    
    width_texture_size: EnumProperty(
            name="Width",
            items=(('4', "4", ""),
                   ('8', "8", ""),
                   ('16', "16", ""),
                   ('32', "32", ""),
                   ('64', "64", ""),
                   ('128', "128", ""),
                   ('256', "256", ""),
                   ),
            default='64',
            )

    height_texture_size: EnumProperty(
            name="Height",
            items=(('4', "4", ""),
                   ('8', "8", ""),
                   ('16', "16", ""),
                   ('32', "32", ""),
                   ('64', "64", ""),
                   ('128', "128", ""),
                   ('256', "256", ""),
                   ),
            default='64',
            )

    has_vertex_colours: BoolProperty(
            name="Has Vertex Colours",
            description="Does this .Model file contain vertex colour information.",
            default=False,
            )

    def execute(self, context):
        from . import import_akimodel
        keywords = self.as_keywords(ignore=("filter_glob",))

        if bpy.data.is_saved and context.preferences.filepaths.use_relative_paths:
            import os
            keywords["relpath"] = os.path.dirname(bpy.data.filepath)
       
        return import_akimodel.load(context, **keywords)


    def draw(self, context):
        pass


class AKIMODEL_PT_import_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"
 
    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "IMPORT_SCENE_OT_model"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator
 
        col = layout.column()
        col.label(text = "Texture Setup", icon = 'TEXTURE_DATA')

        row = layout.row()
        row.prop(operator, "width_texture_size")
        row.prop(operator, "height_texture_size")

        col2 = layout.column()
        col2.label(text = "Model Options", icon = 'MESH_DATA')
        col2.prop(operator, 'has_vertex_colours')


class ExportAKIMODEL(bpy.types.Operator, ExportHelper):
    """Write a MODEL file"""
    bl_idname = "export_scene.model"
    bl_label = "Export Model"
    bl_options = {'UNDO', 'PRESET'}

    filename_ext = ".model"
    filter_glob: StringProperty(default="*.model", options={'HIDDEN'})

    global_scale: IntProperty(
            name="Scale",
            min=1, max=100,
            default=8,
            )
    
    def execute(self, context):
        from . import export_akimodel

        keywords = self.as_keywords(ignore=("check_existing","filter_glob",))

        return export_akimodel.save(context, **keywords)

    def draw(self, context):
        pass

class AKIMODEL_PT_export_include(bpy.types.Panel):
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOL_PROPS'
    bl_label = "Include"
    bl_parent_id = "FILE_PT_operator"

    @classmethod
    def poll(cls, context):
        sfile = context.space_data
        operator = sfile.active_operator

        return operator.bl_idname == "EXPORT_SCENE_OT_akimodel"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False  # No animation.

        sfile = context.space_data
        operator = sfile.active_operator

        layout.prop(operator, 'global_scale')

    

def menu_func_import(self, context):
    self.layout.operator(ImportAKIMODEL.bl_idname, text="AKI Model (.model)")

def menu_func_export(self, context):
    self.layout.operator(ExportAKIMODEL.bl_idname, text="AKI Model (.model)")


classes = (
    ImportAKIMODEL,
    AKIMODEL_PT_import_include,
    ExportAKIMODEL,
    AKIMODEL_PT_export_include,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)

    for cls in classes:
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
