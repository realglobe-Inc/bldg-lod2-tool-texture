import os

from .pl_obj import PlObj, PlMesh
from .pl_options import PlOptions
from .pl_utils import *
from .third_party.earcut_python.earcut.earcut import earcut


# (!TBD!) road height [in meter] offset in loading, because the height values in .gml are always zero.
# temporary_road_height_offset = 20


class PlTran(PlObj):
    def __init__(self, filename=None, options=PlOptions(), dem=None):
        super().__init__()
        self.kind_str = "tran"
        self.pos_lists = None  # list of 'posList'(LinearRing)
        if filename is not None:
            self.load_file(filename, options=options, dem=dem)

    def load_file(self, filename, options=PlOptions(), dem=None):
        tree, root = super().load_file(filename)
        nsmap = self.remove_none_key_from_dic(root.nsmap)
        lt, rb = convert_mesh_code_to_lat_lon(os.path.basename(filename).split("_")[0])
        # center = (np.array(lt)+np.array(rb))/2
        center = (lt[0] * 0.8 + rb[0] * 0.2, lt[1] * 0.2 + rb[1] * 0.8)
        # posLists
        vals = tree.xpath(
            "/core:CityModel/core:cityObjectMember/tran:Road/tran:lod1MultiSurface/gml:MultiSurface/gml:surfaceMember/gml:Polygon/gml:exterior/gml:LinearRing/gml:posList",
            namespaces=nsmap,
        )
        self.pos_lists = [str2floats(v).reshape((-1, 3)) for v in vals]
        if options.b_height_zero:
            for x in self.pos_lists:
                x[:, 2] = 1  # to be a little bit more than 0
        # vertices, triangles
        mesh = PlMesh()
        # self.pos_lists = self.pos_lists[:1000]
        # invoke multi processes
        use_bit = []
        for plist in self.pos_lists:
            vertices = [convert_polar_to_cartesian(*x) for x in plist]
            res = earcut(np.array(vertices, dtype=np.int64).flatten(), dim=3)
            if len(res) > 0:
                triangles = np.array(res).reshape((-1, 3)) + len(mesh.vertices)
                mesh.vertices.extend(vertices)
                mesh.triangles.extend(triangles)
                if options.div_6_to_quarter is not None:
                    for x in plist:
                        bit = True
                        if options.div_6_to_quarter is not None:
                            lat = x[0]
                            lon = x[1]
                            if lat < center[0]:
                                lat = 0
                            else:
                                lat = 1
                            if lon < center[1]:
                                lon = 0
                            else:
                                lon = 1
                            if (lat, lon) != options.div_6_to_quarter:
                                bit = False
                        use_bit.append(bit)
        # remove
        if options.div_6_to_quarter is not None:
            new_triangles = []
            for tri in mesh.triangles:
                if use_bit[tri[0]] and use_bit[tri[1]] and use_bit[tri[2]]:
                    new_triangles.append(tri)
            mesh.triangles = np.array(new_triangles)

        self.meshes.append(mesh)

    def load(self, filepath):
        res = super().load(filepath)
        res.meshes[0].vertices = np.array(res.meshes[0].vertices)
        ### !!! TBD
        # res.meshes[0].vertices[:,2] += temporary_road_height_offset
        return res
