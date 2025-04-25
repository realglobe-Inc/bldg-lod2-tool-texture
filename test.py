from shapely.geometry import Polygon

# 頂点データとポリゴンの定義
vertices = [
    [-10049.760, -52160.090, 10.310],
    [-10049.741, -52160.735, 10.320],
    [-10047.747, -52160.031, 10.315],
    [-10048.065, -52162.495, 10.617],
    [-10045.505, -52162.415, 10.590],
    [-10042.880, -52159.890, 9.990],
    [-10042.726, -52164.931, 9.625],
    [-10049.636, -52164.332, 10.330],
    [-10046.785, -52165.055, 9.770],
    [-10049.612, -52165.141, 9.790],
    [-10042.726, -52164.931, 7.410],
    [-10046.785, -52165.055, 8.493],
    [-10043.503, -52168.087, 7.455],
    [-10042.630, -52168.060, 6.910],
    [-10049.612, -52165.141, 8.400],
    [-10049.520, -52168.270, 7.675],
    [-10047.747, -52160.031, 1.110],
    [-10049.760, -52160.090, 1.110],
    [-10049.741, -52160.735, 1.110],
    [-10042.880, -52159.890, 1.110],
    [-10042.726, -52164.931, 1.110],
    [-10042.630, -52168.060, 1.110],
    [-10049.636, -52164.332, 1.110],
    [-10049.612, -52165.141, 1.110],
    [-10049.520, -52168.270, 1.110],
    [-10043.503, -52168.087, 1.110],
]

faces_roof = [
    [0, 1, 2],
    [3, 4, 2, 1],
    [2, 4, 5],
    [5, 4, 6],
    [7, 8, 3],
    [3, 8, 6, 4],
    [7, 9, 8],
    [10, 11, 12],
    [13, 10, 12],
    [7, 3, 1],
    [11, 14, 15],
    [15, 12, 11],
]

faces_wall = [
    [16, 2, 0, 17],
    [18, 17, 0, 1],
    [10, 6, 5, 19, 20],
    [2, 16, 19, 5],
    [6, 10, 11, 14, 9, 8],
    [21, 13, 10, 20],
    [22, 18, 1, 7, 9, 14, 23],
    [23, 14, 15, 24],
    [25, 24, 15, 12, 13, 21],
]

faces_ground = [[22, 18, 17, 16, 19, 20, 21, 25, 24, 23]]

# 向きをチェックする関数


def check_polygon_orientations(vertices, faces):
    orientations = []
    for face in faces:
        polygon_vertices = [vertices[idx][:2] for idx in face]
        polygon = Polygon(polygon_vertices)
        orientations.append(polygon.exterior.is_ccw)
    return orientations


# 各セクションの向きをチェック
orientations_roof = check_polygon_orientations(vertices, faces_roof)
orientations_wall = check_polygon_orientations(vertices, faces_wall)
orientations_ground = check_polygon_orientations(vertices, faces_ground)

# 結果を出力
print("Roof orientations:", ["CCW" if ccw else "CW" for ccw in orientations_roof])
print("Wall orientations:", ["CCW" if ccw else "CW" for ccw in orientations_wall])
print("Ground orientation:", ["CCW" if ccw else "CW" for ccw in orientations_ground])
