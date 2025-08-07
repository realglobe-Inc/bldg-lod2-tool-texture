import glob
import os

from .pl_bldg import PlBldg
from .pl_code_lists import scan_codelists
from .pl_dem import PlDem
from .pl_luse import PlLuse
from .pl_obj import PlObj
from .pl_options import PlOptions
from .pl_tran import PlTran


class PlParser:
    def __init__(self, paths=None):
        # filenames
        self.filenames_bldg = []
        self.filenames_dem = []
        self.filenames_luse = []
        self.filenames_tran = []
        # objects  (dict, the key is obj.location)
        self.bldg = dict()
        self.dem = dict()
        self.luse = dict()
        self.tran = dict()
        # list of location numbers
        self.locations = []
        # add paths
        # for path in paths:
        # 	self.add_path(path)
        self.add_path(paths)  # 変更:ファイル読み込み

    def add_path(self, path):  # path to CityGML
        print("search " + path)
        # now, static path
        path_bldg = path + "/udx/bldg"
        path_dem = path + "/udx/dem"
        path_luse = path + "/udx/luse"
        path_tran = path + "/udx/tran"
        val = sorted(glob.glob(path_bldg + "/*.gml"))
        print("  bldg : ", len(val), "files")
        self.filenames_bldg.extend(val)
        val = sorted(glob.glob(path_dem + "/*.gml"))
        print("  dem  : ", len(val), "files")
        self.filenames_dem.extend(val)
        val = sorted(glob.glob(path_luse + "/*.gml"))
        print("  luse : ", len(val), "files")
        self.filenames_luse.extend(val)
        val = sorted(glob.glob(path_tran + "/*.gml"))
        print("  tran : ", len(val), "files")
        self.filenames_tran.extend(val)
        # add locations
        locations = list(self.locations)
        locations.extend(
            [
                PlObj.get_location_from_filename(filename, True)
                for filename in self.filenames_bldg
            ]
        )
        locations.extend(
            [
                PlObj.get_location_from_filename(filename, True)
                for filename in self.filenames_dem
            ]
        )
        locations.extend(
            [
                PlObj.get_location_from_filename(filename, True)
                for filename in self.filenames_luse
            ]
        )
        locations.extend(
            [
                PlObj.get_location_from_filename(filename, True)
                for filename in self.filenames_tran
            ]
        )
        self.locations = sorted(list(set(locations)))
        # parse codelists
        dir_codelists = glob.glob(path + "/codelists/")
        if len(dir_codelists) > 0:
            self.codelists = scan_codelists(dir_codelists[0])

    """
	@param b_load_cache:	load cache data or not
	@param cache_dir: 	cache directory name
	@param kind:		specify the type of gml, PlObj.ALL, PlObj.BLDG,..
	@param location:	specify which gml data in the type are loaded, -1:all, <1000:array index, >=1000:location
	"""

    def load_files(
        self,
        b_load_cache=False,
        cache_dir="cached",
        kind=None,
        location=-1,
        options=PlOptions(),
    ):
        if kind is None:
            kind = PlObj.ALL
        if cache_dir is not None:
            os.makedirs(cache_dir, exist_ok=True)
        # prepare filenames
        filenames_bldg = []
        filenames_dem = []
        filenames_luse = []
        filenames_tran = []
        if kind == PlObj.BLDG or kind == PlObj.ALL:
            if location < 0:
                filenames_bldg = self.filenames_bldg
            elif location < 1000:
                filenames_bldg.append(self.filenames_bldg[location])
            else:
                for filename in self.filenames_bldg:
                    if (
                        PlObj.get_location_from_filename(filename, False) == location
                        or PlObj.get_location_from_filename(filename, True) == location
                    ):
                        filenames_bldg.append(filename)
        if kind == PlObj.DEM or kind == PlObj.ALL:
            if location < 0:
                filenames_dem = self.filenames_dem
            elif location < 1000:
                filenames_dem.append(self.filenames_dem[location])
            else:
                for filename in self.filenames_dem:
                    if PlObj.get_location_from_filename(filename) == location:
                        filenames_dem.append(filename)
        if kind == PlObj.LUSE or kind == PlObj.ALL:
            if location < 0:
                filenames_luse = self.filenames_luse
            elif location < 1000:
                filenames_luse.append(self.filenames_luse[location])
            else:
                for filename in self.filenames_luse:
                    if PlObj.get_location_from_filename(filename) == location:
                        filenames_luse.append(filename)
        if kind == PlObj.TRAN or kind == PlObj.ALL:
            if location < 0:
                filenames_tran = self.filenames_tran
            elif location < 1000:
                filenames_tran.append(self.filenames_tran[location])
            else:
                for filename in self.filenames_tran:
                    if PlObj.get_location_from_filename(filename) == location:
                        filenames_tran.append(filename)
        # load files
        if b_load_cache:
            print("### loading cache data..")
            print("# bldg")
            for f in filenames_bldg:
                if (options.div_6_to_quarter is not None) and (
                    options.div_6_to_quarter != PlObj.get_6quarter_from_filename(f)
                ):
                    continue
                obj = PlBldg()
                res = obj.load(PlObj.get_cache_filename(cache_dir, f))
                if res is not None:
                    obj = res
                self.bldg[obj.location] = obj
            print("# dem")
            for f in filenames_dem:
                obj = PlDem()
                res = obj.load(PlObj.get_cache_filename(cache_dir, f))
                if res is not None:
                    obj = res
                self.dem[obj.location] = obj
            print("# luse")
            for f in filenames_luse:
                obj = PlLuse()
                res = obj.load(PlObj.get_cache_filename(cache_dir, f))
                if res is not None:
                    obj = res
                self.luse[obj.location] = obj
            print("# tran")
            for f in filenames_tran:
                obj = PlTran()
                res = obj.load(PlObj.get_cache_filename(cache_dir, f))
                if res is not None:
                    obj = res
                self.tran[obj.location] = obj
        else:
            print("### loading GML data..")
            print("# bldg")
            for f in filenames_bldg:
                if (options.div_6_to_quarter is not None) and (
                    options.div_6_to_quarter != PlObj.get_6quarter_from_filename(f)
                ):
                    continue
                obj = PlBldg(f, options=options)
                self.bldg[obj.location] = obj
                obj.save(PlObj.get_cache_filename(cache_dir, f))
            print("# dem")
            for f in filenames_dem:
                obj = PlDem(f, options=options)
                self.dem[obj.location] = obj
                obj.save(PlObj.get_cache_filename(cache_dir, f))
            print("# luse")
            for f in filenames_luse:
                obj = PlLuse(f, options=options)
                self.luse[obj.location] = obj
                obj.save(PlObj.get_cache_filename(cache_dir, f))
            print("# tran")
            for f in filenames_tran:
                # obj = PlTran(f, self.dem[ PlObj.get_location_from_filename(f) ])
                obj = PlTran(f, options=options)
                self.tran[obj.location] = obj
                obj.save(PlObj.get_cache_filename(cache_dir, f))

    def get_open3d_triangle_mesh(self, color=None, kind_bits=255, wire_only=False):
        meshes = []
        if kind_bits & (1 << PlObj.BLDG):
            for obj in self.bldg.values():
                meshes.extend(
                    obj.get_open3d_triangle_mesh(color=color, wire_only=wire_only)
                )
        if kind_bits & (1 << PlObj.DEM):
            for obj in self.dem.values():
                meshes.extend(
                    obj.get_open3d_triangle_mesh(color=color, wire_only=wire_only)
                )
        if kind_bits & (1 << PlObj.LUSE):
            for obj in self.luse.values():
                meshes.extend(
                    obj.get_open3d_triangle_mesh(color=color, wire_only=wire_only)
                )
        if kind_bits & (1 << PlObj.TRAN):
            for obj in self.tran.values():
                meshes.extend(
                    obj.get_open3d_triangle_mesh(color=color, wire_only=wire_only)
                )
        return meshes

    def write_open3d_ply_files(self, save_path, color=None):
        for obj in self.bldg.values():
            obj.write_open3d_ply_files(save_path=save_path, color=color)
        for obj in self.dem.values():
            obj.write_open3d_ply_files(save_path=save_path, color=color)
        for obj in self.luse.values():
            obj.write_open3d_ply_files(save_path=save_path, color=color)
        for obj in self.tran.values():
            obj.write_open3d_ply_files(save_path=save_path, color=color)

    def show_blender_objects(self, v_base=None):
        import bpy

        scene = bpy.context.scene
        for obj in self.bldg.values():
            _obj = obj.get_blender_objects(v_base=v_base)
            for _o in _obj:
                scene.collection.objects.link(_o)
        for obj in self.dem.values():
            _obj = obj.get_blender_objects(v_base=v_base)
            for _o in _obj:
                scene.collection.objects.link(_o)
        for obj in self.luse.values():
            _obj = obj.get_blender_objects(v_base=v_base)
            for _o in _obj:
                scene.collection.objects.link(_o)
        for obj in self.tran.values():
            _obj = obj.get_blender_objects(v_base=v_base)
            for _o in _obj:
                scene.collection.objects.link(_o)
        bpy.context.view_layer.update()
