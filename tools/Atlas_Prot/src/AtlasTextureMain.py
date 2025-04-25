# -*- coding:utf-8 -*-
import sys
import os
import datetime

from .city_gml_manager import CityGmlManager
from .layoutRect import LayoutTexture
from .util.parammanager import ParamManager


def main():
    """メイン関数"""
    # 引数入力暫定
    args = ["Atlas_Prot.py", os.path.join(".", "param.json")]

    if len(args) != 2:
        print("usage: python AutoCreateLod2.py param.json")
        sys.exit()

    param_manager = ParamManager()
    param_manager.read(args[1])

    time = datetime.datetime.now()
    print(time)

    # CityGML読み込み
    citygml_manager = CityGmlManager(param_manager)
    citygml_infos = citygml_manager.input_citygml()

    # アトラス化・画像出力
    layout_texture = LayoutTexture(param_manager, citygml_infos)
    layout_texture.layout_texture_main()

    # CityGML出力
    citygml_manager.output_citygml()

    time = datetime.datetime.now()
    print(time)
