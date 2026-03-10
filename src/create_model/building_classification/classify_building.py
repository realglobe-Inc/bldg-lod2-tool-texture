from shapely import Polygon

from .classifier import BuildingClass, Classifier
from .preprocess import Preprocess
from ..las_manager import PointCloud


def classify_building(
    building_id: str,
    cloud: PointCloud,
    shape: Polygon,
    classifier_checkpoint_path: str,
    grid_size: float,
    use_gpu: bool = False,
) -> BuildingClass:
    """建物の分類を行う

    Args:
        building_id(str): 建物ID
        cloud(PointCloud): 建物点群
        shape(Polygon): 建物外形ポリゴン
        classifier_checkpoint_path(str): 建物分類の学習済みモデルファイルパス
        grid_size(float,optional): 点群の間隔(meter),
        use_gpu(bool, optional): 推論時のGPU使用の有無 (Default: False)

    Returns:
        BuildingClass: 建物クラス
    """
    # 建物が大きい場合は陸屋根とする (TODO: 要対応)
    points = cloud.get_points().copy()
    min_x, min_y = points[:, :2].min(axis=0)
    max_x, max_y = points[:, :2].max(axis=0)
    height = max_y - min_y
    width = max_x - min_x

    # 1辺100m超えは陸屋根？
    if max(height, width) > 100:
        return BuildingClass.FLAT

    # 判定用データの作成
    preprocess = Preprocess(grid_size)
    building_img = preprocess.preprocess(
        cloud,
        shape,
    )

    classifier = Classifier(classifier_checkpoint_path, use_gpu)
    building_class = classifier.classify(building_img)

    return building_class


if __name__ == "__main__":
    pass
