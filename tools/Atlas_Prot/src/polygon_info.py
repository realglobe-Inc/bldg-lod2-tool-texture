class PolygonInfo():
  """ポリゴン情報クラス
  """

  def __init__(self) -> None:
    """コンストラクタ
    """
    self.target_uri = None
    self.coord_ring = None
    self.in_texcoord = list()   # 入力テクスチャポリゴン座標
    self.out_texcoord = list()  # 出力テクスチャポリゴン座標

    self.minX = 0
    self.minY = 0
    self.maxX = 0
    self.maxY = 0
    self.useW = 0
    self.useH = 0
    self.useX = 0
    self.useY = 0
    self.flag = False
    self.marginX = 0
    self.marginY = 0
