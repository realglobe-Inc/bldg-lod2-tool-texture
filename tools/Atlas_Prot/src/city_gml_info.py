from .building_info import BuildingInfo


class CityGmlInfo:
    """CityGML情報クラス"""

    @property
    def input_city_gml_path(self):
        """
        入力CityGMLファイルのパス

        Returns:
          str: 入力CityGMLファイルのパス
        """
        return self._input_city_gml_path

    @property
    def output_city_gml_path(self):
        """
        出力CityGMLファイルのパス

        Returns:
          str: 出力CityGMLファイルのパス
        """
        return self._output_city_gml_path

    def __init__(
        self,
        input_city_gml_path: str,
        output_city_gml_path: str,
    ):
        """
        コンストラクタ

        Args:
          input_city_gml_path (str): 入力CityGMLファイルのパス
          output_city_gml_path (str): 出力CityGMLファイルのパス
        """
        self.buildings: list[BuildingInfo] = []  # 建物情報リスト
        self._input_city_gml_path = input_city_gml_path
        self._output_city_gml_path = output_city_gml_path

    def add_building_info(self, building: BuildingInfo):
        """
        建物オブジェクトの作成

        Args:
          building (BuildingInfo): 建物情報
        """

        self.buildings.append(building)
