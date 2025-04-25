from math import sqrt


def find_closest_point(
    point_ij: tuple[float, float], layer_number_point_ijs: list[tuple[float, float]]
):
    """頂点から一番近い点を探す

    Args:
      point_ij (tuple[float, float]): 基準点
      layer_number_point_ijs (list[tuple[float, float]]): 探す点のリスト

    Returns:
      Union[tuple[float, float], None]: 頂点から一番近い点
    """
    closest_point = None
    min_distance = float("inf")

    for layer_number_point_ij in layer_number_point_ijs:
        distance = sqrt(
            (layer_number_point_ij[0] - point_ij[0]) ** 2
            + (layer_number_point_ij[1] - point_ij[1]) ** 2
        )
        if distance < min_distance:
            min_distance = distance
            closest_point = layer_number_point_ij

    return closest_point
