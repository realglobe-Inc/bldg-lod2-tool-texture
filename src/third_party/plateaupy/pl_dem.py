import os

from .pl_obj import PlObj, PlMesh
from .pl_options import PlOptions
from .pl_utils import *


class PlDem(PlObj):
    def __init__(self, filename=None, options=PlOptions()):
        super().__init__()
        self.kind_str = "dem"
        self.pos_lists = None  # list of 'posList'(LinearRing) : [*,4,3]
        if filename is not None:
            self.load_file(filename, options=options)

    def load_file(self, filename, options=PlOptions(), num_search_coincident=100):
        tree, root = super().load_file(filename)
        nsmap = self.remove_none_key_from_dic(root.nsmap)
        lt, rb = convert_mesh_code_to_lat_lon(os.path.basename(filename).split("_")[0])
        # center = (np.array(lt)+np.array(rb))/2
        center = (lt[0] * 0.8 + rb[0] * 0.2, lt[1] * 0.2 + rb[1] * 0.8)
        # posLists
        vals = tree.xpath(
            "/core:CityModel/core:cityObjectMember/dem:ReliefFeature/dem:reliefComponent/dem:TINRelief/dem:tin/gml:TriangulatedSurface/gml:trianglePatches/gml:Triangle/gml:exterior/gml:LinearRing/gml:posList",
            namespaces=nsmap,
        )
        self.pos_lists = np.array([str2floats(v).reshape((-1, 3)) for v in vals])
        if options.b_height_zero:
            self.pos_lists[:, :, 2] = 0
        # print(self.pos_lists.shape)
        # convert to XYZ
        pos_lists = copy.deepcopy(self.pos_lists)
        use_bit = []
        for x in pos_lists:
            for y_idx, y in enumerate(x):
                bit = True
                if options.div_6_to_quarter is not None:
                    lat = y[0]
                    lon = y[1]
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
                if y_idx < 3:
                    use_bit.append(bit)
                y[:] = convert_polar_to_cartesian(*y)
        # to vertices and triangles
        #   integrate vertices that are coincident.
        mesh = PlMesh()
        mesh.triangles = np.zeros((pos_lists.shape[0], 3), dtype=np.int64)
        for x_idx, x in enumerate(pos_lists):
            for y_idx, y in enumerate(x[:3]):
                new_id = -1
                if options.div_6_to_quarter is None:
                    num = x_idx
                    if num > num_search_coincident:
                        num = num_search_coincident
                    for _id, vvv in enumerate(mesh.vertices[x_idx - num :]):
                        if vvv[0] == y[0] and vvv[1] == y[1] and vvv[2] == y[2]:
                            new_id = _id + x_idx - num
                            break
                if new_id < 0:
                    new_id = len(mesh.vertices)
                    mesh.vertices.append(y)
                mesh.triangles[x_idx, y_idx] = new_id
        # remove
        if options.div_6_to_quarter is not None:
            new_triangles = []
            for tri in mesh.triangles:
                if use_bit[tri[0]] and use_bit[tri[1]] and use_bit[tri[2]]:
                    new_triangles.append(tri)
            mesh.triangles = np.array(new_triangles)

        self.meshes.append(mesh)
