import array
import os
import time
import bpy
import mathutils
import struct
import binascii
import bmesh

from pathlib import Path
from bpy_extras.wm_utils.progress_report import ProgressReport


class MDL:
 def __init__(self):
    self.type           = 0
    self.scale          = 0
    self.vertex_count   = 0
    self.face_count     = 0
    self.texture_size   = 0
    self.vertex_influence = 0
    self.offsets       = []
    self.vertices      = []
    self.faces         = []
    self.uvs           = []
    
class TypeFormat:
    SByte = '<b'
    Byte = '<B'
    Int16 = '<h'
    BInt16 = '>h'
    UInt16 = '<H'
    Int32 = '<i'
    UInt32 = '<I'
    Int64 = '<l'
    UInt64 = '<L'
    Single = '<f'
    Double = '<d'


def color_srgb_to_scene_linear(c):
    if c < 0.04045:
        return 0.0 if c < 0.0 else c * (1.0 / 12.92)
    else:
        return ((c + 0.055) * (1.0 / 1.055)) ** 2.4

def hex_to_rgb(rgb_str):    
    int_tuple = struct.unpack('BBB', bytes.fromhex(rgb_str))    
    return tuple([val/255 for val in int_tuple])  

def veckey2d(v):
    return round(v[0], 4), round(v[1], 4)

def load(context,
        filepath,
        *,
        relpath=None,
        width_texture_size = "64",
        height_texture_size = "64",
        has_vertex_colours = False
        ):
   
    with ProgressReport(context.window_manager) as progress:
        progress.enter_substeps(1, "Importing AKI Model %r..." % filepath)

        progress.enter_substeps(3, "Parsing AKI file...")

        with open(filepath, 'rb') as f:
            mesh = MDL()
            
            mesh.scale          = int.from_bytes(f.read(1), "little");

            # meshes without scale are read differently
            if mesh.scale > 0:
                mesh.type = 1
            else:
                mesh.scale += 1
            
            mesh.vertex_count       = (int.from_bytes(f.read(1), "little") & 0x7F);
            mesh.face_count         = int.from_bytes(f.read(1), "little");
            mesh.vertex_influence   = int.from_bytes(f.read(1), "little");

            # Offset translate
            scaleIToF = 0.1

            offset_array = []
            ofsX = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0]) * scaleIToF), 4)
            ofsY = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0]) * scaleIToF), 4)
            ofsZ = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0]) * scaleIToF), 4)

            offset_array.append([ofsX, ofsY, ofsZ])


            test = 0x37 - 0x80
            print("HERE : ", 0x37 - 0x80)

            print("KEK :", test & 0x7F)

            # assumed?
            mesh.texture_size = int.from_bytes(f.read(1), "little");

             # correct the scale for verts
            scaleIToF = 1.0 / mesh.scale

            vert_array = []
            faces_array = []
            uv_array = []
            vert_colors = {}

            # extrapolate the verts
            for v in range(0, mesh.vertex_count) :

                if mesh.type >= 1:
                    # vertex
                    vtX = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0])* scaleIToF), 4)
                    vtY = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0])* scaleIToF), 4)
                    vtZ = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0])* scaleIToF), 4)
                    vert_array.append([vtX, vtY, vtZ])

                    if has_vertex_colours :
                        # move to UVs
                        aU = (float(struct.unpack(TypeFormat.Byte, f.read(1))[0]) / int(width_texture_size) )
                        aV = (float(struct.unpack(TypeFormat.Byte, f.read(1))[0]) / int(height_texture_size) )
                        
                        #print("vt", aU, aV)
                        uv_array.append([aU, aV])

                        # vertex colours, add this later on!
                        colour_r = int(((int.from_bytes(f.read(1), "little")  )))
                        colour_g = int(((int.from_bytes(f.read(1), "little")  )))
                        colour_b = int(((int.from_bytes(f.read(1), "little")  )))

                        vert_colors[v] = [ colour_r, colour_g, colour_b ]
                    else:
                        f.read(2)
                        
                        # move to UVs
                        aU = (float(struct.unpack(TypeFormat.Byte, f.read(1))[0]) / int(width_texture_size) )
                        f.read(1) 
                        aV = (float(struct.unpack(TypeFormat.Byte, f.read(1))[0]) / int(height_texture_size) )

                        uv_array.append([aU, aV])
                        
                else:
                    # vertex
                    vtX = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0])* scaleIToF), 4)
                    vtY = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0])* scaleIToF), 4)
                    vtZ = round(((struct.unpack(TypeFormat.SByte, f.read(1))[0])* scaleIToF), 4)
                    vert_array.append([vtX, vtY, vtZ])

                    # move to UVs
                    aU = (float(struct.unpack(TypeFormat.Byte, f.read(1))[0]) / int(width_texture_size) )
                    aV =  ((float(struct.unpack(TypeFormat.Byte, f.read(1))[0]) / int(height_texture_size) ) * -1 + 1.0)

                    uv_array.append([aU, aV])

                    colour_r = int(((int.from_bytes(f.read(1), "little")  )))
                    colour_g = int(((int.from_bytes(f.read(1), "little")  )))
                    colour_b = int(((int.from_bytes(f.read(1), "little")  )))
                    
                    vert_colors[v] = [ colour_r, colour_g, colour_b ]

                    # force vertex colors on for these types
                    has_vertex_colours = True

                                 
            mesh.vertices   = vert_array
            mesh.uvs        = uv_array
            mesh.offsets    = offset_array

            for faces in range(0, mesh.face_count) :
                # FACES
                # We needed to add 1 to this with raw Python, Blender doens't require it
                fX = int(((int.from_bytes(f.read(1), "little")  )))
                fY = int(((int.from_bytes(f.read(1), "little")  )))
                fZ = int(((int.from_bytes(f.read(1), "little")  )))

                #print(fX,fY,fZ)
                faces_array.append([fX, fY, fZ])

            mesh.faces = faces_array

        # make mesh
        vertices = mesh.vertices
        edges = []
        faces = mesh.faces

        n64_mesh = bpy.data.meshes.new('n64_mesh')
        n64_mesh.from_pydata(vertices, edges, faces)
        n64_mesh.update()
        n64_mesh.uv_layers.new(name="n64", do_init=False)
        n64_object = bpy.data.objects.new(Path(filepath).stem, n64_mesh)

        # update meta data for export

        if mesh.type > 0:
            n64_mesh['scale'] = mesh.scale
        else:
            n64_mesh['scale'] = 0

        n64_mesh['width'] = int(width_texture_size)
        n64_mesh['height'] = int(height_texture_size)
        n64_mesh['colors'] = has_vertex_colours
        n64_mesh['internal_tex_size'] = mesh.texture_size
        n64_mesh['vertex_influence'] = mesh.vertex_influence

        for face in n64_object.data.polygons:
            face.use_smooth = True
            for vert_idx, loop_idx in zip(face.vertices, face.loop_indices):
                n64_object.data.uv_layers.active.data[loop_idx].uv = (mesh.uvs[vert_idx][0],mesh.uvs[vert_idx][1])
                #print("face idx: %i, vert idx: %i, uvs: %f, %f" % (face.index, vert_idx, uv_coords.x, uv_coords.y))
                
        scene = bpy.context.scene
        scene.collection.objects.link(n64_object)

        origin_offset = mathutils.Vector(mesh.offsets[0])
        n64_object.location = origin_offset

        bpy.context.view_layer.objects.active = bpy.data.objects[n64_object.name]

        if has_vertex_colours :
            bpy.ops.object.mode_set(mode = 'VERTEX_PAINT')
            
            # sample the vertex colours
            if(len(vert_colors) > 0):
                for polygon in n64_mesh.polygons:
                    for i, index in enumerate(polygon.vertices):
                        vertex_colour = [vert_colors[index][0] / 255, vert_colors[index][1] / 255, vert_colors[index][2] / 255, 1]
                        #vertex_colour = [color_srgb_to_scene_linear(vert_colors[index][0] / 255), color_srgb_to_scene_linear(vert_colors[index][1] / 255),
                        #                 color_srgb_to_scene_linear(vert_colors[index][2] / 255), 1]

                        #print( vert_colors[index][0].decode('utf-8')+vert_colors[index][1].decode('utf-8')+vert_colors[index][2].decode('utf-8') )
                    
                        loop_index = polygon.loop_indices[i]
                        n64_mesh.vertex_colors.active.data[loop_index].color = vertex_colour
                    
                bpy.ops.object.mode_set(mode = 'OBJECT')
        
        progress.leave_substeps("Done.")
        progress.leave_substeps("Finished importing: %r" % filepath)

    return {'FINISHED'}















