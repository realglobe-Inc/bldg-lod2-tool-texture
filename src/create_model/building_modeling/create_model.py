import os

from shapely import Polygon

from .model import Model
from .preprocess import Preprocess
from ..las_manager import PointCloud


class BuildingModelBuilder:
    """陸屋根モデルの作成"""

    def __init__(
        self,
        cloud: PointCloud,
        shape: Polygon,
        graph_cut_height: float,
        grid_size: float,
        building_id: str,
        min_ground_height: float,
        output_folder_path: str,
    ):
        """
        陸屋根モデルの作成

        Args:
          cloud (PointCloud): 点群データ
          shape (Polygon): 建物外形データ
          graph_cut_height (float): GraphCut用の地面の高さ
          grid_size (float): 解像度m
          building_id (str): 建物id
          min_ground_height (float): 最低地面高さ
          output_folder_path (str): 出力フォルダパス
        """
        # 屋根形状の作成
        preprocess = Preprocess()  # 前処理クラス
        clusters = preprocess.preprocess(
            cloud=cloud,
            shape=shape,
            ground_height=graph_cut_height,
            grid_size=grid_size,
        )

        # LoD2モデルデータの作成
        model = Model(id=building_id, shape=shape, use_hierarchy_classify=True)
        model.create_model_surface(clusters=clusters, ground_height=min_ground_height)
        # objファイルの作成
        file_name = building_id + ".obj"
        obj_path = os.path.join(output_folder_path, file_name)
        model.output_obj(path=obj_path)


if __name__ == "__main__":
    pass
