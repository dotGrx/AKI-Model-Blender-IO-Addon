import array
import os
import time
import bpy
import mathutils
import struct
import binascii
import bmesh

from mathutils import Matrix, Vector, Color
from bpy_extras import io_utils, node_shader_utils

from bpy_extras.wm_utils.progress_report import (
    ProgressReport,
    ProgressReportSubstep,
)

def name_compat(name):
    if name is None:
        return 'None'
    else:
        return name.replace(' ', '_')
    
class MDL:
 def __init__(self):
    self.scale          = 0
    self.vertex_count   = 0
    self.face_count     = 0
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

def mesh_triangulate(me):
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()

def scale_vertex(n,s):
    r = round(n * (1.0 * s), 2)
    return hex(int(r) & 0xFF)[2:].zfill(2)

def scale_uv(n,s):
    r = round(n * s, 2)
    return hex(int(r) & 0xFF)[2:].zfill(2)

def veckey2d(v):
    return round(v[0], 4), round(v[1], 4)
    
def float_to_hex(f):
    return hex(int(f) & 0xFF)[2:].zfill(2)

def blender_to_rgb(n):
    return hex(int(n * 255) & 0xFF)[2:].zfill(2)


def write_file(filepath, objects, depsgraph, scene,
               EXPORT_SCALE='8',
               progress=ProgressReport(),
               ):

    with ProgressReportSubstep(progress, 2, "MODEL Export path: %r" % filepath, "Model Export Finished") as subprogress1:
        with open(filepath, "wb") as f:

            totverts = totuvco = totno = 1

            subprogress1.enter_substeps(len(objects))
            for i, ob_main in enumerate(objects):

                mesh_scaler     = bpy.data.objects[ob_main.name].data['scale']
                has_vt_colours  = bpy.data.objects[ob_main.name].data['colors']

                # Write Header
                f.write(mesh_scaler.to_bytes(1, byteorder='little'))
                
                # ignore dupli children
                if ob_main.parent and ob_main.parent.instance_type in {'VERTS', 'FACES'}:
                    subprogress1.step("Ignoring %s, dupli child..." % ob_main.name)
                    continue
                    
                obs = [(ob_main, ob_main.matrix_world)]

                subprogress1.enter_substeps(len(obs))

                for ob, ob_mat in obs:
                    with ProgressReportSubstep(subprogress1, 6) as subprogress2:
                        uv_unique_count = no_unique_count = 0

                        try:
                            me = ob.original.to_mesh()
                        except RuntimeError:
                            me = None

                        if me is None:
                            continue

                        mesh_triangulate(me)

                        faceuv = len(me.uv_layers) > 0
                        if faceuv:
                            uv_layer = me.uv_layers.active.data[:]

                        # access our selected mesh
                        me_verts    = me.vertices[:]
                        me_polys    = me.polygons[:]
                        me_uvs      = {}

                        if bool(has_vt_colours) :
                            me_colors   = me.vertex_colors["Col"]

                        loops = me.loops

                        face_index_pairs = [(face, index) for index, face in enumerate(me.polygons)]

                        f.write(len(me_verts).to_bytes(1, byteorder='big'))
                        f.write(len(me_polys).to_bytes(1, byteorder='big'))
                        f.write(b'\x00')

                        subprogress2.step()
                
                        local_offsets = bpy.data.objects[ob_main.name].location

                        # offsets
                        f.write(binascii.unhexlify(float_to_hex(round(local_offsets[0],2) * 10)))
                        f.write(binascii.unhexlify(float_to_hex(round(local_offsets[1],2) * 10)))
                        f.write(binascii.unhexlify(float_to_hex(round(local_offsets[2],2) * 10)))
                        f.write(b'\x00')

                        subprogress2.step()

                        export_vert_colours = {}

                        if faceuv:  
                            uv = f_index = uv_index = uv_key = uv_val = uv_ls = None

                            uv_face_mapping = [None] * len(face_index_pairs)
                            uv_dict = {}
                            uv_get = uv_dict.get
                            for fa, f_index in face_index_pairs:
                                uv_ls = uv_face_mapping[f_index] = []
                                for uv_index, l_index in enumerate(fa.loop_indices):
                                    uv = uv_layer[l_index].uv

                                    uv_key = loops[l_index].vertex_index, veckey2d(uv)
                                    uv_val = uv_get(uv_key)
                                    if uv_val is None:
                                        uv_val = uv_dict[uv_key] = uv_unique_count

                                        # store uvs for later use                                        
                                        me_uvs[loops[l_index].vertex_index] = uv[:]

                                        if bool(has_vt_colours) :
                                            # store vert colours
                                            export_vert_colours[loops[l_index].vertex_index] = me_colors.data[loops[l_index].vertex_index].color

                                        uv_unique_count += 1
                                    uv_ls.append(uv_val)
                                
                            del uv_dict, uv, f_index, uv_index, uv_ls, uv_get, uv_key, uv_val

                        subprogress2.step()
                        
                        # Vert
                        tex_offset = 0
                        for v in me_verts:
                            scaler_width    = bpy.data.objects[ob_main.name].data['width']
                            scaler_height   = bpy.data.objects[ob_main.name].data['height']

                            f.write( binascii.unhexlify(scale_vertex(v.co[0], mesh_scaler)))
                            f.write( binascii.unhexlify(scale_vertex(v.co[1], mesh_scaler)))
                            f.write( binascii.unhexlify(scale_vertex(v.co[2], mesh_scaler)))

                            if bool(has_vt_colours) :
                                # we don't need to actually scale these, but we mexicool so we do it l33t c0de
                                f.write(binascii.unhexlify( scale_uv(me_uvs[tex_offset][0], scaler_width )) )
                                f.write(binascii.unhexlify( scale_uv(me_uvs[tex_offset][1], scaler_height )) )

                                f.write(binascii.unhexlify(blender_to_rgb(export_vert_colours[tex_offset][0])))
                                f.write(binascii.unhexlify(blender_to_rgb(export_vert_colours[tex_offset][1])))
                                f.write(binascii.unhexlify(blender_to_rgb(export_vert_colours[tex_offset][2])))
                            else:
                                f.write(b'\x00\x00')
                                f.write(binascii.unhexlify( scale_uv(me_uvs[tex_offset][0], scaler_width )) )
                                f.write(b'\x00')
                                f.write(binascii.unhexlify( scale_uv(me_uvs[tex_offset][1] * -1, scaler_height )) )

                            tex_offset += 1

                        subprogress2.step()

                        for face, f_index in face_index_pairs:
                            
                            f_v = [(vi, me_verts[v_idx], l_idx)
                                   for vi, (v_idx, l_idx) in enumerate(zip(face.vertices, face.loop_indices))]
                            
                            for vi, v, li in f_v:
                                #print(" %d" % (totverts + v.index))
                                f.write(((totverts + v.index) - 1).to_bytes(1, byteorder='little'))
                            
             

def _write(context, filepath,
           EXPORT_SCALE,
           ):
    
    with ProgressReport(context.window_manager) as progress:
        base_name, ext = os.path.splitext(filepath)
        context_name = [base_name, '', '', ext]

        depsgraph = context.evaluated_depsgraph_get()
        scene = context.scene

        # Exit edit mode before exporting, so current object states are exported properly.
        if bpy.ops.object.mode_set.poll():
            bpy.ops.object.mode_set(mode='OBJECT')

        objects = context.selected_objects
        full_path = ''.join(context_name)

        progress.enter_substeps(1)

        write_file(full_path, objects, depsgraph, scene, EXPORT_SCALE, progress)

        progress.leave_substeps()


def save(context,
         filepath,
         *,
         global_scale = '2'
         ):

    _write(context, filepath,
           EXPORT_SCALE=global_scale,
           )

    return {'FINISHED'}
























