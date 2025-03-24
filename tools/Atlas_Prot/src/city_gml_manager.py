# -*- coding:utf-8 -*-
import math
import os
import shutil
import sys

import lxml
import numpy as np
from lxml import etree
from tqdm import tqdm

from .building_info import BuildingInfo
from .city_gml_info import CityGmlInfo
from .stey_mesh import SetyMesh
from .thirdparty import plateaupy as plapy
from .util.cvsupportjp import Cv2Japanese
from .util.parammanager import ParamManager


class CityGmlManager():
    """CityGML処理クラス
    """

    def __init__(self, param_manager: ParamManager) -> None:
        """コンストラクタ

        Args:
          param_manager (ParamManager): パラメータファイル管理クラス
        """
        self._pm = param_manager
        self.citygml_infos: list[CityGmlInfo] = []
        self.citygml_names: list[str] = []

    def input_citygml(self):
        """CityGMLファイル情報入力
        """
        for file in os.listdir(self._pm.input_gml_folder_path):
            base, ext = os.path.splitext(file)
            if ext == '.gml':
                self.citygml_names.append(base)

        # CityGMLファイル毎に処理
        for index, gml_file in enumerate(self.citygml_names):
            # print(self._pm.input_gml_folder_path + "\\" + gml_file + ".gml")

            plbld = plapy.plbldg(os.path.join(self._pm.input_gml_folder_path, gml_file + ".gml"))
            mesh_list: list[SetyMesh] = list()

            for bldg in plbld.buildings:

                if any(bldg.lod2ground) or any(bldg.lod2roof) or any(bldg.lod2wall):
                    mesh = SetyMesh()
                    for lod2ground in bldg.lod2ground:
                        mesh.ids.append(lod2ground)
                    for lod2roof in bldg.lod2roof:
                        mesh.ids.append(lod2roof)
                    for lod2wall in bldg.lod2wall:
                        mesh.ids.append(lod2wall)

                    if bldg.lod0RoofEdge:
                        lat = bldg.lod0RoofEdge[0][0][0]
                        lon = bldg.lod0RoofEdge[0][0][1]
                        mesh.code = self.get_mesh(lat, lon)

                    elif bldg.lod0FootPrint:
                        lat = bldg.lod0FootPrint[0][0][0]
                        lon = bldg.lod0FootPrint[0][0][1]
                        mesh.code = self.get_mesh(lat, lon)
                    mesh_list.append(mesh)

            city_gml_info = CityGmlInfo(
                input_city_gml_path=(os.path.join(self._pm.input_gml_folder_path, gml_file + ".gml")),
                output_city_gml_path=(os.path.join(self._pm.output_gml_folder_path, gml_file + ".gml")),
            )
            self.citygml_infos.append(city_gml_info)

            parser = etree.XMLParser(remove_blank_text=True)
            tree = etree.parse(os.path.join(self._pm.input_gml_folder_path, gml_file + ".gml"), parser)
            root = tree.getroot()
            self._nsmap = self.removeNoneKeyFromDic(root.nsmap)

            apps = tree.xpath(
                '/core:CityModel/app:appearanceMember/app:Appearance/ \
                app:surfaceDataMember/app:ParameterizedTexture',
                namespaces=self._nsmap
            )

            isatty = sys.stdout.isatty()
            desc = f"{gml_file} {index + 1}/{len(self.citygml_names)}"
            pbar = tqdm(
                total=len(apps),
                desc=desc,
                unit="gml",
                dynamic_ncols=isatty,
                disable=not isatty,
            )
            if not isatty:
                print(f"Processing {desc}")

            for elem1 in apps:
                # 建物毎に処理
                mime_type = elem1.xpath('app:mimeType', namespaces=self._nsmap)[0].text
                input_image_path = elem1.xpath('app:imageURI', namespaces=self._nsmap)[0].text
                image = Cv2Japanese.imread(os.path.join(self._pm.input_gml_folder_path, input_image_path))

                building = BuildingInfo(
                    mime_type=mime_type,
                    input_image_path=input_image_path,
                    input_image_height=image.shape[0],
                    input_image_width=image.shape[1],
                )

                # 解像度取得

                # ポリゴン毎に処理
                target = elem1.xpath('app:target', namespaces=self._nsmap)
                for elem2 in target:
                    uri = elem2.get("uri")

                    # 4・5次メッシュの検索
                    if building.mesh_code == 0:
                        for mesh_elem in mesh_list:
                            if uri in mesh_elem.ids:
                                building.mesh_code = mesh_elem.code

                    texCoord = elem2.xpath('app:TexCoordList/app:textureCoordinates', namespaces=self._nsmap)
                    ring = texCoord[0].get("ring")
                    clist = texCoord[0].text.split(" ")

                    # ポリゴンの座標をコピーする
                    if ((self._pm.output_width == building.input_image_width) and (
                            self._pm.output_height == building.input_image_height)) or (
                            (self._pm.output_width < building.input_image_width) or (
                            self._pm.output_height < building.input_image_height)):
                        #  一定サイズ以上の場合はそのままの座標値を入力
                        coord_f = []
                        clistiter = iter(clist)
                        for u, v in zip(clistiter, clistiter):
                            coord_f.append(float(u))
                            coord_f.append(float(v))
                        arrays_r = np.reshape(np.array(coord_f), (-1, 2))
                    else:
                        coord_f = []
                        clistiter = iter(clist)
                        for u, v in zip(clistiter, clistiter):
                            coord_f.append(float(u) * building.input_image_width - 0.5)
                            coord_f.append((1.0 - float(v)) * building.input_image_height - 0.5)
                        arrays_r = np.reshape(np.array(coord_f), (-1, 2))

                    building.add_polygon_info(uri, ring, arrays_r,
                                              [building.input_image_width, building.input_image_height],
                                              self._pm.extent_pixel)

                    # # ポリゴンを高さ順にソートする
                    # if (building.input_image_width < self._pm.output_width) and (building.input_image_height < self._pm.output_height):
                    #     building.polygon_infos = sorted(
                    #         building.polygon_infos,
                    #         key=lambda PolygonInfo: PolygonInfo.useH,
                    #         reverse=True)

                city_gml_info.add_building_info(building)

                pbar.update(1)

            pbar.close()

            city_gml_info.buildings = sorted(city_gml_info.buildings, key=lambda buildings: buildings.mesh_code)

        return self.citygml_infos

    def output_citygml(self):
        """CityGMLファイル情報出力
        """

        # CityGMLファイル毎に処理
        for citygml_info in self.citygml_infos:

            shutil.copy(citygml_info.input_city_gml_path, citygml_info.output_city_gml_path)

            parser = etree.XMLParser(remove_blank_text=True)
            tree = etree.parse(citygml_info.output_city_gml_path, parser)
            root = tree.getroot()

            print(self._nsmap['app'])

            # 既存のテクスチャ記述部分削除
            for app in root.findall("{" + self._nsmap['app'] + "}" + 'appearanceMember'):
                root.remove(app)

            temp_imgpath = None

            tex_appmem_elem = lxml.etree.Element("{" + self._nsmap['app'] + "}" + "appearanceMember")
            tex_app_elem = lxml.etree.SubElement(
                tex_appmem_elem, "{" + self._nsmap['app'] + "}" + "Appearance"
            )
            tex_theme_elem = lxml.etree.SubElement(tex_app_elem, "{" + self._nsmap['app'] + "}" + "theme")
            tex_theme_elem.text = "rgbTexture"

            for building in citygml_info.buildings:
                if building is not None:
                    elem5 = None
                    elem1 = lxml.etree.SubElement(
                        tex_app_elem, "{" + self._nsmap['app'] + "}" + "surfaceDataMember"
                    )
                    elem2 = lxml.etree.SubElement(
                        elem1, "{" + self._nsmap['app'] + "}" + "ParameterizedTexture"
                    )

                    if temp_imgpath != building.output_image_path:
                        elem3 = lxml.etree.SubElement(
                            elem2, "{" + self._nsmap['app'] + "}" + "imageURI"
                        )
                        elem3.text = building.output_image_path
                        temp_imgpath = building.output_image_path
                        elem4 = lxml.etree.SubElement(
                            elem2, "{" + self._nsmap['app'] + "}" + "mimeType"
                        )
                        elem4.text = building.mime_type

                    for poly in building.polygon_infos:
                        str_list = []
                        elem5 = lxml.etree.SubElement(
                            elem2, "{" + self._nsmap['app'] + "}" + "target", {"uri": poly.target_uri}
                        )
                        elem6 = lxml.etree.SubElement(
                            elem5, "{" + self._nsmap['app'] + "}" + "TexCoordList"
                        )
                        for coord in poly.out_texcoord:
                            str_list.append(str(coord[0]))
                            str_list.append(str(coord[1]))
                        elem7 = lxml.etree.SubElement(
                            elem6, "{" + self._nsmap['app'] + "}" + "textureCoordinates", {"ring": poly.coord_ring}
                        )
                        elem7.text = ' '.join(str_list)

            root.append(tex_appmem_elem)

            # LoD2 CityGML書き出し
            lxml.etree.indent(root, space="\t")  # tab区切り
            print(citygml_info.output_city_gml_path)
            tree.write(
                citygml_info.output_city_gml_path, pretty_print=True, xml_declaration=True, encoding="utf-8"
            )

    def removeNoneKeyFromDic(self, nsmap):
        """namespase取得
        """
        newnsmap = dict()
        for k, v in nsmap.items():
            if k is not None:
                newnsmap[k] = v
        return newnsmap

    def get_mesh(self, lat, lon):
        """メッシュ取得
        """
        code4 = (int(math.floor(lat * 240)) % 2 * 2 + int(math.floor((lon - 100) * 160)) % 2 + 1)
        # code5 = (int(math.floor(lat * 480)) % 2 * 2 + int(math.floor((lon - 100) * 320)) % 2 + 1)
        # return (code4 * 10 + code5)
        return (code4)
