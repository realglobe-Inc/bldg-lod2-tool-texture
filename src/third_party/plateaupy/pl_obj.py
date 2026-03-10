import os
import pickle

from lxml import etree

from .pl_utils import *


class PlMesh:
    def __init__(self) -> None:
        self.vertices = []  # [ num_of_vertices,  3 ]  (float)
        self.triangles = []  # [ num_of_triangles, 3 ]  (int)
        self.texture_filename = None
        self.triangle_uvs = []  # [ 3 * num_of_triangles, 2 ]  (float)
        self.triangle_material_ids = []  # [ num_of_triangles ]  (int)

    def get_center_vertices(self):
        return np.mean(self.vertices, axis=0)

    def to_open3d_triangle_mesh(self, color=None, wire_only=False):
        import open3d as o3d

        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(self.vertices)
        mesh.triangles = o3d.utility.Vector3iVector(self.triangles)
        if self.texture_filename is not None:
            mesh.textures = [o3d.io.read_image(self.texture_filename)]
            mesh.triangle_uvs = o3d.utility.Vector2dVector(np.array(self.triangle_uvs))
            mesh.triangle_material_ids = o3d.utility.IntVector(
                np.array(self.triangle_material_ids, dtype=np.int32)
            )
            # print( 'triangles = ', np.array(self.triangles).shape )
            # print( 'triangle_uvs = ', np.array(self.triangle_uvs).shape )
            # print( 'triangle_material_ids = ', np.array(self.triangle_material_ids).shape )
        elif color is not None:
            mesh.paint_uniform_color(color)
        mesh.compute_vertex_normals()
        if wire_only:
            mesh = o3d.geometry.LineSet.create_from_triangle_mesh(mesh)
        return mesh

    def to_blender_object(self, mesh_name, v_base=None):
        import bpy

        name_str = mesh_name
        mesh = bpy.data.meshes.new(name=name_str)
        vertices = [list(v) for v in self.vertices]
        triangles = [list(t) for t in self.triangles]
        if v_base is not None:
            vertices = [list(np.array(v) - v_base) for v in vertices]
        mesh.from_pydata(vertices, [], triangles)
        mesh.update(calc_edges=True)
        obj = bpy.data.objects.new(name=name_str, object_data=mesh)
        return obj


class PlObj:
    # kind
    ALL = -1
    BLDG = 0
    DEM = 1
    LUSE = 2
    TRAN = 3
    BRID = 4

    @staticmethod
    def get_location_from_filename(filename, b_large=False):
        loc = int(os.path.basename(filename).split("_")[0])
        if b_large and loc >= 1000000:  # eg. bldg is 53392546, besides dem is 533925
            loc = loc // 100
        return loc

    @staticmethod
    def get_6quarter_from_filename(filename):
        division = 8  # 5
        loc_str = os.path.basename(filename).split("_")[0]
        if len(loc_str) != 8:
            return -1, -1
        lat = int(loc_str[6])
        lon = int(loc_str[7])
        if lat < division:
            lat = 0
        else:
            lat = 1
        if lon < division:
            lon = 0
        else:
            lon = 1
        return lat, lon

    @staticmethod
    def get_cache_filename(cache_dir, filename):
        return cache_dir + "/" + os.path.splitext(os.path.basename(filename))[0]

    @staticmethod
    def remove_none_key_from_dic(nsmap):
        new_nsmap = dict()
        for k, v in nsmap.items():
            if k is not None:
                new_nsmap[k] = v
        return new_nsmap

    def __init__(self):
        self.kind_str = "obj"
        self.filename = None
        self.location = 0  # location number
        self.lowerCorner = np.zeros(3)  # lower_corner (lon,lat,height)
        self.upperCorner = np.zeros(3)  # upper_corner
        self.meshes = []  # list of PlMesh

    def load_file(self, filename):
        # print('load', filename)
        self.filename = filename
        self.location = self.get_location_from_filename(filename)
        # tree = etree.parse(filename)
        parser = etree.XMLParser(remove_blank_text=True)  # 追加:出力時の改行対応
        tree = etree.parse(filename, parser)  # 追加:出力時の改行対応
        root = tree.getroot()
        # lowerCorner, upperCorner
        nsmap = self.remove_none_key_from_dic(root.nsmap)
        vals = tree.xpath(
            "/core:CityModel/gml:boundedBy/gml:Envelope/gml:lowerCorner",
            namespaces=nsmap,
        )
        if len(vals) > 0:
            self.lowerCorner = str2floats(vals[0])
        vals = tree.xpath(
            "/core:CityModel/gml:boundedBy/gml:Envelope/gml:upperCorner",
            namespaces=nsmap,
        )
        if len(vals) > 0:
            self.upperCorner = str2floats(vals[0])
        return tree, root

    def get_open3d_triangle_mesh(self, color=None, wire_only=False):
        _color = color
        if _color is None:
            _color = np.random.rand(3)
        return [
            m.to_open3d_triangle_mesh(color=_color, wire_only=wire_only)
            for m in self.meshes
        ]

    def write_open3d_ply_files(self, save_path, color=None):
        import open3d as o3d

        meshes = self.get_open3d_triangle_mesh(color=color)
        for idx, m in enumerate(meshes):
            filename = (
                save_path
                + "/"
                + str(self.location)
                + "_"
                + self.kind_str
                + "_"
                + str(idx)
                + ".ply"
            )
            o3d.io.write_triangle_mesh(filename, m)

    def get_blender_objects(self, v_base=None):
        rname = self.kind_str
        return [
            m.to_blender_object(
                mesh_name=str(self.location) + "_" + rname + "_" + str(idx),
                v_base=v_base,
            )
            for idx, m in enumerate(self.meshes)
        ]

    def get_center_vertices(self):
        centers = np.array([m.get_center_vertices() for m in self.meshes])
        return np.mean(centers, axis=0)

    # cache save/load
    def save(self, filepath):
        with open(filepath + ".pkl", mode="wb") as f:
            pickle.dump(self, f)

    def load(self, filepath):
        try:
            with open(filepath + ".pkl", mode="rb") as f:
                return pickle.load(f)
        except FileNotFoundError as e:
            print(e)
        return None
