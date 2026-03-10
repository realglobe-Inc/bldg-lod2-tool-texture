import os

import lxml
from lxml import etree

from .pl_obj import PlMesh, PlObj
from .pl_options import PlOptions
from .pl_utils import *
from .third_party.earcut_python.earcut.earcut import earcut

_floor_height = 2  # fixed value, the height of 1 floor in meter.


class Building:
    def __init__(self):
        self.id = None  # gml:id
        self.attr = dict()
        self.usage = None
        self.measured_height = None
        self.storeys_above_ground = None
        self.storeys_below_ground = None
        self.address = None
        self.building_details = dict()
        self.extended_attribute = dict()

        self.lod0_roof_edge = []
        self.lod0_foot_print = []  # 追加:lod0_foot_print
        self.lod1Solid = []

        # self.lod2_solid = []
        # lod2MultiSurface
        self.lod2_ground = dict()
        self.lod2roof = dict()
        self.lod2wall = dict()
        self.par_tex = AppParameterizedTexture()

    def __str__(self):
        return "Building id={}\n\
usage={}, measured_height={}, storeys_above_ground={}, storeys_below_ground={}\n\
address={}\n\
building_details={}\n\
extended_attribute={}\n\
attr={}".format(
            self.id,
            self.usage,
            self.measured_height,
            self.storeys_above_ground,
            self.storeys_below_ground,
            self.address,
            self.building_details,
            self.extended_attribute,
            self.attr,
        )

    # get vertices, triangles from lod0_roof_edge
    def get_lod0_polygons(self, height=None):
        vertices = None
        triangles = None
        if len(self.lod0_roof_edge) > 0:
            vertices = []
            for x in self.lod0_roof_edge[0]:
                xx = copy.deepcopy(x)
                if height is not None:
                    xx[2] = height
                vertices.append(convert_polar_to_cartesian(*xx))
            vertices = np.array(vertices)
            res = earcut(np.array(vertices, dtype=np.int64).flatten(), dim=3)
            if len(res) > 0:
                triangles = np.array(res).reshape((-1, 3))
        return vertices, triangles


class AppParameterizedTexture:
    def __init__(self):
        self.imageURI = None
        self.targets = dict()

    @classmethod
    def search_list(cls, app_list, polyid):
        for app in app_list:
            if polyid in app.targets.keys():
                return app
        return None


class PlBldg(PlObj):
    def __init__(self, filename=None, options=PlOptions()):
        super().__init__()
        self.kind_str = "bldg"
        self.buildings = []  # list of Building
        if filename is not None:
            self.load_file(filename, options=options)

    def load_file(self, filename, options=PlOptions()):
        tree, root = super().load_file(filename)
        nsmap = self.remove_none_key_from_dic(root.nsmap)

        # scan appearanceMember
        par_tex = []
        try:
            if "app" in nsmap:
                for app in tree.xpath(
                    "/core:CityModel/app:appearanceMember/app:Appearance/app:surfaceDataMember/app:ParameterizedTexture",
                    namespaces=nsmap,
                ):
                    par = AppParameterizedTexture()
                    for at in app.xpath("app:imageURI", namespaces=nsmap):
                        par.imageURI = at.text
                    for at in app.xpath("app:target", namespaces=nsmap):
                        uri = at.attrib["uri"]
                        co_list = [
                            str2floats(v).reshape((-1, 2))
                            for v in at.xpath(
                                "app:TexCoordList/app:textureCoordinates",
                                namespaces=nsmap,
                            )
                        ]
                        max_num = max(map(lambda x: x.shape[0], co_list))
                        for c_idx, co in enumerate(co_list):
                            last = co[-1].reshape(-1, 2)
                            num = max_num - co.shape[0]
                            if num > 0:
                                co_list[c_idx] = np.append(
                                    co, np.tile(co[-1].reshape(-1, 2), (num, 1)), axis=0
                                )
                        par.targets[uri] = np.array(co_list)
                    par_tex.append(par)
        except Exception as e:
            print(
                f"Error: Unexpected error during appearance processing in {filename}: {e}"
            )
            pass

        # scan cityObjectMember
        buildings = tree.xpath(
            "/core:CityModel/core:cityObjectMember/bldg:Building", namespaces=nsmap
        )
        for bld in buildings:
            b = Building()
            # gml:id
            b.id = bld.attrib["{" + nsmap["gml"] + "}id"]
            # str_Attribute
            str_attributes = bld.xpath("gen:str_Attribute", namespaces=nsmap)
            for at in str_attributes:
                b.attr[at.attrib["name"]] = at.getchildren()[0].text
            # genericAttributeSet
            generic_attribute_sets = bld.xpath(
                "gen:genericAttributeSet", namespaces=nsmap
            )
            for at in generic_attribute_sets:
                vals = dict()
                for ch in at.getchildren():
                    vals[ch.attrib["name"]] = ch.getchildren()[0].text
                b.attr[at.attrib["name"]] = vals
            # usage
            for at in bld.xpath("bldg:usage", namespaces=nsmap):
                b.usage = at.text
            # measuredHeight
            for at in bld.xpath("bldg:measuredHeight", namespaces=nsmap):
                b.measured_height = at.text
            # storeysAboveGround
            for at in bld.xpath("bldg:storeysAboveGround", namespaces=nsmap):
                b.storeys_above_ground = at.text
            # storeysBelowGround
            for at in bld.xpath("bldg:storeysBelowGround", namespaces=nsmap):
                b.storeys_below_ground = at.text
            # address
            try:  # there are 2 names: 'xAL' and 'xal'..
                for at in bld.xpath(
                    "bldg:address/core:Address/core:xalAddress/xAL:AddressDetails/xAL:Address",
                    namespaces=nsmap,
                ):
                    b.address = at.text
            except lxml.etree.XPathEvalError as e:
                for at in bld.xpath(
                    "bldg:address/core:Address/core:xalAddress/xal:AddressDetails/xal:Address",
                    namespaces=nsmap,
                ):
                    b.address = at.text
            # buildingDetails
            for at in bld.xpath(
                "uro:buildingDetails/uro:BuildingDetails", namespaces=nsmap
            ):
                for ch in at.getchildren():
                    tag = ch.tag
                    tag = tag[tag.rfind("}") + 1 :]
                    b.building_details[tag] = ch.text
            # extendedAttribute
            for at in bld.xpath(
                "uro:extendedAttribute/uro:KeyValuePair", namespaces=nsmap
            ):
                ch = at.getchildren()
                b.extended_attribute[ch[0].text] = ch[1].text
            # lod0_roof_edge
            vals = bld.xpath(
                "bldg:lod0RoofEdge/gml:MultiSurface/gml:surfaceMember/gml:Polygon/gml:exterior/gml:LinearRing/gml:posList",
                namespaces=nsmap,
            )
            b.lod0_roof_edge = [str2floats(v).reshape((-1, 3)) for v in vals]
            # 追加:lod0FootPrint
            vals = bld.xpath(
                "bldg:lod0FootPrint/gml:MultiSurface/gml:surfaceMember/gml:Polygon/gml:exterior/gml:LinearRing/gml:posList",
                namespaces=nsmap,
            )
            b.lod0_foot_print = [str2floats(v).reshape((-1, 3)) for v in vals]
            # lod1Solid
            vals = bld.xpath(
                "bldg:lod1Solid/gml:Solid/gml:exterior/gml:CompositeSurface/gml:surfaceMember/gml:Polygon/gml:exterior/gml:LinearRing/gml:posList",
                namespaces=nsmap,
            )
            b.lod1Solid = [str2floats(v).reshape((-1, 3)) for v in vals]
            min_height = 0
            if options.b_height_zero:
                # calc min height
                min_height = 10000
                for x in b.lod1Solid:
                    if min_height > np.min(x[:, 2]):
                        min_height = np.min(x[:, 2])
                if b.storeys_below_ground is not None:
                    min_height = min_height + (
                        int(b.storeys_below_ground) * _floor_height
                    )
                if min_height == 10000:
                    min_height = 0
                for x in b.lod1Solid:
                    x[:, 2] -= min_height
            # lod2Solid
            #  nothing to do for parsing <bldg:lod2Solid>
            # lod2MultiSurface : Ground, Roof, Wall
            for bb in bld.xpath(
                "bldg:boundedBy/bldg:GroundSurface/bldg:lod2MultiSurface/gml:MultiSurface/gml:surfaceMember/gml:Polygon",
                namespaces=nsmap,
            ):
                polyid = "#" + bb.attrib["{" + nsmap["gml"] + "}id"]
                vals = bb.xpath(
                    "gml:exterior/gml:LinearRing/gml:posList", namespaces=nsmap
                )
                surf = [str2floats(v).reshape((-1, 3)) for v in vals]
                if options.b_height_zero:
                    if min_height == 0:
                        # calc min height
                        min_height = 10000
                        for x in surf:
                            if min_height > np.min(x[:, 2]):
                                min_height = np.min(x[:, 2])
                        if b.storeys_below_ground is not None:
                            min_height = min_height + (
                                int(b.storeys_below_ground) * _floor_height
                            )
                        if min_height == 10000:
                            min_height = 0
                    for x in surf:
                        x[:, 2] -= min_height
                b.lod2_ground[polyid] = surf
                app = AppParameterizedTexture.search_list(par_tex, polyid)
                if app is not None:
                    if b.par_tex.imageURI is None:
                        b.par_tex = app
                    # elif b.par_tex.imageURI != app.imageURI:
                    # 	print('error')
            for bb in bld.xpath(
                "bldg:boundedBy/bldg:RoofSurface/bldg:lod2MultiSurface/gml:MultiSurface/gml:surfaceMember/gml:Polygon",
                namespaces=nsmap,
            ):
                polyid = "#" + bb.attrib["{" + nsmap["gml"] + "}id"]
                vals = bb.xpath(
                    "gml:exterior/gml:LinearRing/gml:posList", namespaces=nsmap
                )
                surf = [str2floats(v).reshape((-1, 3)) for v in vals]
                if options.b_height_zero:
                    for x in surf:
                        x[:, 2] -= min_height
                b.lod2roof[polyid] = surf
                app = AppParameterizedTexture.search_list(par_tex, polyid)
                if app is not None:
                    if b.par_tex.imageURI is None:
                        b.par_tex = app
                    # elif b.par_tex.imageURI != app.imageURI:
                    # 	print('error')
            for bb in bld.xpath(
                "bldg:boundedBy/bldg:WallSurface/bldg:lod2MultiSurface/gml:MultiSurface/gml:surfaceMember/gml:Polygon",
                namespaces=nsmap,
            ):
                polyid = "#" + bb.attrib["{" + nsmap["gml"] + "}id"]
                vals = bb.xpath(
                    "gml:exterior/gml:LinearRing/gml:posList", namespaces=nsmap
                )
                surf = [str2floats(v).reshape((-1, 3)) for v in vals]
                if options.b_height_zero:
                    for x in surf:
                        x[:, 2] -= min_height
                b.lod2wall[polyid] = surf
                app = AppParameterizedTexture.search_list(par_tex, polyid)
                if app is not None:
                    if b.par_tex.imageURI is None:
                        b.par_tex = app
                    # elif b.par_tex.imageURI != app.imageURI:
                    # 	print('error')
            self.buildings.append(b)

        # vertices, triangles
        if (not options.b_use_lod2_texture) or options.b_use_lod0:
            mesh = PlMesh()
        for b in self.buildings:
            if options.b_use_lod2_texture and (not options.b_use_lod0):
                mesh = PlMesh()

            if options.b_use_lod0:
                # LOD0
                vertices, triangles = b.get_lod0_polygons()
                if vertices is not None and triangles is not None:
                    v_start = len(mesh.vertices)
                    mesh.vertices.extend(vertices)
                    mesh.triangles.extend(triangles + v_start)
            elif b.lod2_ground or b.lod2roof or b.lod2wall:
                # LOD2
                if options.b_use_lod2_texture:
                    if b.par_tex.imageURI is not None:
                        # convert .tif into .png, because o3d.io.read_image() fails.
                        mesh.texture_filename = (
                            os.path.dirname(self.filename) + "/" + b.par_tex.imageURI
                        )
                        img = cv2.imread(mesh.texture_filename)
                        mesh.texture_filename = (
                            options.texture_dir
                            + "/"
                            + os.path.basename(mesh.texture_filename)
                            + ".png"
                        )
                        cv2.imwrite(mesh.texture_filename, img)
                # ground
                for key, value in b.lod2_ground.items():
                    vertices = [convert_polar_to_cartesian(*x) for x in value[0]]
                    res = earcut(np.array(vertices, dtype=np.int64).flatten(), dim=3)
                    if len(res) > 0:
                        v_start = len(mesh.vertices)
                        mesh.vertices.extend(vertices)
                        triangles = np.array(res).reshape((-1, 3))
                        mesh.triangles.extend(triangles + v_start)
                        # texture
                        if options.b_use_lod2_texture:
                            if key in b.par_tex.targets.keys():
                                mesh.triangle_uvs.extend(
                                    [
                                        b.par_tex.targets[key][0, x]
                                        for x in triangles.reshape((-1))
                                    ]
                                )
                                mesh.triangle_material_ids.extend([0] * len(triangles))
                            else:  # add dummy uvs, material_ids    (The texture can not appear if the numbers of triangles are different between triangles and them.)
                                mesh.triangle_uvs.extend(
                                    [np.zeros(2) for x in range(len(triangles) * 3)]
                                )
                                mesh.triangle_material_ids.extend([0] * len(triangles))
                # roof
                for key, value in b.lod2roof.items():
                    vertices = [convert_polar_to_cartesian(*x) for x in value[0]]
                    res = earcut(np.array(vertices, dtype=np.int64).flatten(), dim=3)
                    if len(res) > 0:
                        v_start = len(mesh.vertices)
                        mesh.vertices.extend(vertices)
                        triangles = np.array(res).reshape((-1, 3))
                        mesh.triangles.extend(triangles + v_start)
                        # texture
                        if options.b_use_lod2_texture:
                            if key in b.par_tex.targets.keys():
                                mesh.triangle_uvs.extend(
                                    [
                                        b.par_tex.targets[key][0, x]
                                        for x in triangles.reshape((-1))
                                    ]
                                )
                                mesh.triangle_material_ids.extend([0] * len(triangles))
                # wall
                for key, value in b.lod2wall.items():
                    vertices = [convert_polar_to_cartesian(*x) for x in value[0]]
                    res = earcut(np.array(vertices, dtype=np.int64).flatten(), dim=3)
                    if len(res) > 0:
                        v_start = len(mesh.vertices)
                        mesh.vertices.extend(vertices)
                        triangles = np.array(res).reshape((-1, 3))
                        mesh.triangles.extend(triangles + v_start)
                        # texture
                        if options.b_use_lod2_texture:
                            if key in b.par_tex.targets.keys():
                                mesh.triangle_uvs.extend(
                                    [
                                        b.par_tex.targets[key][0, x]
                                        for x in triangles.reshape((-1))
                                    ]
                                )
                                mesh.triangle_material_ids.extend([0] * len(triangles))
            else:
                # LOD1
                for plist in b.lod1Solid:
                    vertices = [convert_polar_to_cartesian(*x) for x in plist]
                    res = earcut(np.array(vertices, dtype=np.int64).flatten(), dim=3)
                    if len(res) > 0:
                        v_start = len(mesh.vertices)
                        mesh.vertices.extend(vertices)
                        triangles = np.array(res).reshape((-1, 3))
                        mesh.triangles.extend(triangles + v_start)
                        # texture
                        if (
                            options.b_use_lod2_texture
                        ):  # add dummy uvs, material_ids    (The texture can not appear if the numbers of triangles are different between triangles and them.)
                            mesh.triangle_uvs.extend(
                                [np.zeros(2) for x in range(len(triangles) * 3)]
                            )
                            mesh.triangle_material_ids.extend([0] * len(triangles))
            if options.b_use_lod2_texture:
                self.meshes.append(mesh)
        if not options.b_use_lod2_texture:
            self.meshes.append(mesh)
