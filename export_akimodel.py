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
    self.scale              = 0
    self.type               = 0    
    self.vertex_count       = 0
    self.face_count         = 0
    self.vertex_influence   = 0
    self.offsets            = []
    self.vertices           = []
    self.faces              = []
    self.uvs                = []
    self.texture_size       = 0
    
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
    bmesh.ops.triangulate(bm, faces=bm.faces, quad_method='FIXED')
    bm.to_mesh(me)
    bm.free()

def mesh_splice_by_island (me):
    import bmesh

    scene = bpy.context.scene

    ob = me.copy()
    ob.data = me.data.copy()
    new_name = ob.name + "_cloned"
    ob.data.name = new_name
    
    # link to collection if need be
    scene.collection.objects.link(ob)

    bpy.ops.object.select_all(action='DESELECT')
    bpy.data.objects[ob.name].select_set(True)
    
    bpy.ops.object.mode_set(mode = 'EDIT')
    bm = bmesh.from_edit_mesh(ob.data)
    bm.select_mode = {'FACE'}
    faceGroups = []

    bpy.ops.mesh.select_mode(use_extend=False, use_expand=False, type='FACE')
    save_sync = scene.tool_settings.use_uv_select_sync
    scene.tool_settings.use_uv_select_sync = True
    faces = set(bm.faces[:])
    while faces:
        bpy.ops.mesh.select_all(action='DESELECT')  
        face = faces.pop() 
        face.select = True
        bpy.ops.uv.select_linked()
        selected_faces = {f for f in faces if f.select}
        selected_faces.add(face) 
        faceGroups.append(selected_faces)
        faces -= selected_faces

    scene.tool_settings.use_uv_select_sync = save_sync

    for g in faceGroups:
        bpy.ops.mesh.select_all(action='DESELECT')
        for f in g:
            f.select = True
        bpy.ops.mesh.split()

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.data.objects[ob.name].select_set(True)

    return ob.original.to_mesh()


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

def blender_to_inverted_rgb(n):
    return hex( (int(n * 255) ^ 0xFF))[2:].zfill(2)


def write_file(filepath, objects, depsgraph, scene,
               EXPORT_SCALE='8',
               progress=ProgressReport(),
               ):

    with ProgressReportSubstep(progress, 2, "MODEL Export path: %r" % filepath, "Model Export Finished") as subprogress1:
        with open(filepath, "wb") as f:

            totverts = totuvco = totno = 1

            subprogress1.enter_substeps(len(objects))
            for i, ob_main in enumerate(objects):

                mesh = MDL()

                mesh.scale              = bpy.data.objects[ob_main.name].data['scale']
                mesh.vertex_influence   = bpy.data.objects[ob_main.name].data['vertex_influence']
                mesh.texture_size       = bpy.data.objects[ob_main.name].data['internal_tex_size']
                has_vt_colours          = bpy.data.objects[ob_main.name].data['colors']

                # Write Header
                f.write(mesh.scale.to_bytes(1, byteorder='little'))

                # Override scale for this particular mesh type
                if mesh.scale <= 0:
                    mesh.scale = 1
                else:
                    mesh.type = 1
                    
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
                            # splice our mesh by UV island. N64 AKI style.
                            me  = mesh_splice_by_island(ob)
                        except RuntimeError:
                            me = None

                        if me is None:
                            continue

                        # Not sure if the game uses tristrips or regular triangle dump, going with the latter for now, seems to work!
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

                        # Different vertex count encoding
                        if mesh.type > 0:
                            f.write(len(me_verts).to_bytes(1, byteorder='big'))
                        else:
                            # bit encode
                            encoded_vertcount = (len(me_verts) - 128)
                            f.write(binascii.unhexlify(hex(encoded_vertcount & 0xFF)[2:]))

                        # Basic header info
                        f.write(len(me_polys).to_bytes(1, byteorder='big'))
                        f.write(mesh.vertex_influence.to_bytes(1, byteorder='big'))
                        
                        subprogress2.step()
                
                        local_offsets = bpy.data.objects[ob_main.name].location

                        # offsets
                        f.write(binascii.unhexlify(float_to_hex(round(local_offsets[0],2) * 10)))
                        f.write(binascii.unhexlify(float_to_hex(round(local_offsets[1],2) * 10)))
                        f.write(binascii.unhexlify(float_to_hex(round(local_offsets[2],2) * 10)))
                        #f.write(b'\x00')
                        f.write(mesh.texture_size.to_bytes(1, byteorder='little'))

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
                                            export_vert_colours[loops[l_index].vertex_index] = me_colors.data[l_index].color

                                        uv_unique_count += 1
                                    uv_ls.append(uv_val)
                                
                            del uv_dict, uv, f_index, uv_index, uv_ls, uv_get, uv_key, uv_val

                        subprogress2.step()

                        # Vert
                        tex_offset = 0
                        for v in me_verts:
                            scaler_width    = bpy.data.objects[ob_main.name].data['width']
                            scaler_height   = bpy.data.objects[ob_main.name].data['height']                          
                    
                            f.write( binascii.unhexlify(scale_vertex(v.co[0], mesh.scale)))
                            f.write( binascii.unhexlify(scale_vertex(v.co[1], mesh.scale)))
                            f.write( binascii.unhexlify(scale_vertex(v.co[2], mesh.scale)))

                            if bool(has_vt_colours) :
                                f.write(binascii.unhexlify( scale_uv(me_uvs[tex_offset][0], scaler_width )) )
                                f.write(binascii.unhexlify( scale_uv((me_uvs[tex_offset][1] * -1) + 1.0, scaler_height )) )
                                
                                f.write(int(round(export_vert_colours[tex_offset][0] * 255, 4)).to_bytes(1, byteorder='little'))
                                f.write(int(round(export_vert_colours[tex_offset][1] * 255, 4)).to_bytes(1, byteorder='little'))
                                f.write(int(round(export_vert_colours[tex_offset][2] * 255, 4)).to_bytes(1, byteorder='little'))

                            else:
                                f.write(b'\x00\x00')
                                f.write(binascii.unhexlify( scale_uv(me_uvs[tex_offset][0], scaler_width )) )
                                f.write(b'\x00')
                                # flip 
                                f.write(binascii.unhexlify( scale_uv( (me_uvs[tex_offset][1] * -1) + 1.0, scaler_height ) ) )

                            tex_offset += 1

                        subprogress2.step()

                        for face, f_index in face_index_pairs:
                            
                            f_v = [(vi, me_verts[v_idx], l_idx)
                                   for vi, (v_idx, l_idx) in enumerate(zip(face.vertices, face.loop_indices))]
                            
                            for vi, v, li in f_v:
                                #print(" %d" % (totverts + v.index))
                                f.write(((totverts + v.index) - 1).to_bytes(1, byteorder='little'))

                        # get rid of our temporary mesh
                        bpy.ops.object.delete()
                        bpy.data.objects[ob.name].select_set(True)

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
























