from collections import defaultdict


class LineGroup:
  def __init__(self, distance_threshold: float = 1e-4):
    # 各グループキーに属する点を管理
    self._line_group_key_point_ijs_pair: dict[tuple[float, float], set[tuple[float, float]]] = defaultdict(set)
    self._distance_threshold = distance_threshold

  def add_line(
      self,
      start_point_ij: tuple[float, float],
      end_point_ij: tuple[float, float],
  ):
    """
    エッジをグループに追加する

    Args:
        start_point_ij (tuple[float, float]): 線分の開始点
        end_point_ij (tuple[float, float]): 線分の終了点
    """
    line_group_key = self.get_line_group_key(start_point_ij, end_point_ij)

    self._line_group_key_point_ijs_pair[line_group_key].add(start_point_ij)
    self._line_group_key_point_ijs_pair[line_group_key].add(end_point_ij)

  def get_line_group(
      self,
      start_point_ij: tuple[float, float],
      end_point_ij: tuple[float, float],
  ) -> set[tuple[float, float]]:
    """
    線分が属するグループの全点を取得する

    Args:
        start_point_ij (tuple[float, float]): 線分の開始点
        end_point_ij (tuple[float, float]): 線分の終了点

    Returns:
        set[tuple[float, float]]: グループ内の点の集合
    """
    # グループキーを取得
    line_group_key = self.get_line_group_key(start_point_ij, end_point_ij)

    # キーに対応する点群を返す
    return self._line_group_key_point_ijs_pair.get(line_group_key, set())

  def get_line_group_key(
      self,
      start_point_ij: tuple[float, float],
      end_point_ij: tuple[float, float],
  ) -> tuple[float, float]:
    """
    線分が属するグループのキーを取得する

    Args:
        start_point_ij (tuple[float, float]): 線分の開始点
        end_point_ij (tuple[float, float]): 線分の終了点

    Returns:
        tuple[float, float]: グループキー
    """
    (i1, j1) = start_point_ij
    (i2, j2) = end_point_ij

    for existing_line_group_key in self._line_group_key_point_ijs_pair:
      existing_a, existing_b = existing_line_group_key
      start_point_distance = self._calculate_normal_distance(existing_a, existing_b, start_point_ij)
      end_point_distance = self._calculate_normal_distance(existing_a, existing_b, end_point_ij)

      if start_point_distance < self._distance_threshold and end_point_distance < self._distance_threshold:
        return existing_line_group_key

    # 一致するキーが見つからなかった場合、新しいキーを返す
    if i2 != i1:
      a = (j2 - j1) / (i2 - i1)  # 傾き
      b = j1 - a * i1            # 切片
    else:
      # 垂直線の場合
      a = float("inf")  # 無限大を使用して垂直線を表現
      b = i1

    new_line_group_key = (round(a, 4), round(b, 3))
    return new_line_group_key

  def _calculate_normal_distance(
      self,
      existing_a: float,
      existing_b: float,
      point_ij: tuple[float, float],
  ) -> float:
    """
    法線距離を計算する

    Args:
        existing_a (float): 直線の傾き
        existing_b (float): 直線の切片
        point_ij (tuple[float, float]): 点の座標 (i, j)

    Returns:
        float: 点と直線の法線距離
    """
    i, j = point_ij

    if existing_a != float("inf"):
      # 通常の直線の場合
      distance = abs(existing_a * i - j + existing_b) / ((existing_a**2 + 1)**0.5)
    else:
      # 垂直線の場合
      distance = abs(i - existing_b)

    return distance
