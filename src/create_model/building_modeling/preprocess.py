import sys

import numpy as np
from jakteristics import compute_features
from shapely import Polygon
from sklearn.cluster import DBSCAN, MeanShift
from sklearn.neighbors import NearestNeighbors

from .cluster_info import ClusterInfo
from .graph_cut import GraphCut
from .mbr import MBR
from ..create_model_exception import ModelingException
from ..las_manager import PointCloud
from ..message import ModelingMessage
from ..param import ModelingParam


class Preprocess:
    """建物点群取得後から、モデル化前に行う前処理クラス"""

    def __init__(self) -> None:
        """コンストラクタ"""
        self._XYZ = "xyz"
        self._RGB = "rgb"
        self._IND = "ind"
        pass

    def _height_clustering(self, cloud: PointCloud, z_band_width=0.5) -> list:
        """高さによるクラスタリング

        Args:
            cloud (PointCloud): 点群
            z_band_width (float, optional): 高さのバンド幅. Defaults to 0.5.

        Returns:
            list: クラスタリング結果のリスト
        """
        # 高さでクラスタリング(MeanShift)
        zs = cloud.get_points()[:, 2]
        if zs.size == 0:
            return []
        z_min = np.min(zs)
        zs = zs - z_min

        clustering = MeanShift(bandwidth=z_band_width, bin_seeding=True, n_jobs=8)
        clustering.fit(zs[..., np.newaxis])
        labels = clustering.labels_

        hierarchy_points = []
        for label in np.unique(labels):
            indices = labels == label
            hierarchy_points.append(
                {
                    self._XYZ: cloud.get_points()[indices],
                    self._RGB: cloud.get_colors()[indices],
                    self._IND: cloud.index[indices],
                }
            )

        return hierarchy_points

    def _color_clustering(self, hierarchy_points: list, rgb_band_width=20) -> list:
        """色によるクラスタリング

        Args:
            hierarchy_points (list): 点群のリスト
            rgb_band_width (int, optional): 色のバンド幅. Defaults to 20.

        Returns:
            list: クラスタリング結果のリスト
        """
        # 色クラスタリング（MeanShift）★Option：色+法線領域拡張/色領域拡張
        hierarchy_cluster_points = []
        for hierarchy_points_ in hierarchy_points:
            clustering = MeanShift(bandwidth=rgb_band_width, bin_seeding=True, n_jobs=8)
            clustering.fit(hierarchy_points_[self._RGB] / 256)
            labels = clustering.labels_

            for label in np.unique(labels):
                indices = labels == label
                hierarchy_cluster_points.append(
                    {
                        self._XYZ: hierarchy_points_[self._XYZ][indices],
                        self._RGB: hierarchy_points_[self._RGB][indices],
                        self._IND: hierarchy_points_[self._IND][indices],
                    }
                )

        return hierarchy_cluster_points

    def _dbscan(self, hierarchy_clusters: list, eps=0.5, point_th=5, n=20) -> list:
        """DBSCAN

        Args:
            hierarchy_clusters (list): 点群のリスト
            eps (float, optional): dbscanの探索半径. Defaults to 0.5.
            point_th (int, optional): core点判定用の点数閾値. Defaults to 5.
            n (int, optional): 最小クラスタ点数閾値. Defaults to 20.

        Returns:
            list: クラスタリング結果のリスト
        """
        new_hierarchy_cluster_points = []
        for i in range(len(hierarchy_clusters)):
            db = DBSCAN(eps=eps, min_samples=point_th)
            db.fit(hierarchy_clusters[i][self._XYZ])
            labels = db.labels_

            n_clusters = len(set(labels)) - (1 if -1 in labels else 0)
            for ci in range(n_clusters):
                indices = np.where(labels == ci)[0]
                if len(indices) < n:
                    continue

                new_hierarchy_cluster_points.append(
                    {
                        self._XYZ: hierarchy_clusters[i][self._XYZ][indices],
                        self._RGB: hierarchy_clusters[i][self._RGB][indices],
                        self._IND: hierarchy_clusters[i][self._IND][indices],
                    }
                )

        return new_hierarchy_cluster_points

    def _search_cluster_close_to_polygon(
        self,
        hierarchy_clusters: list,
        shape: Polygon,
        sample_step=0.25,
        search_radius=1.0,
    ) -> list:
        """点群近傍に存在する建物外形ポリゴン辺の探索

    Args:
        hierarchy_clusters (list): クラスタ点群のリスト
        shape (Polygon): 建物外形ポリゴン
        sample_step (float, optional): \
            建物外形ポリゴン辺のサンプリング間隔m. Defaults to 0.25.
        search_radius (float, optional): \
            近傍探索時の探索半径m. Defaults to 1.0.

    Returns:
        list: クラスタリング結果のリスト
    """
        # 外形ポリゴンに近いクラスタを探索する
        shape_xy = np.array(shape.exterior.coords).copy()

        # 建物外形線のサンプリング
        footprint_points_xy = []
        for i in range(len(shape_xy) - 1):
            point_i = shape_xy[i]
            point_j = shape_xy[i + 1]
            length = np.linalg.norm(point_i - point_j)
            n_points = round(length / sample_step)
            xs = np.linspace(point_i[0], point_j[0], n_points)
            ys = np.linspace(point_i[1], point_j[1], n_points)
            xy = np.c_[xs[..., np.newaxis], ys[..., np.newaxis]]
            footprint_points_xy += xy.tolist()

        # 建物外形線の近傍点（クラスタリングした階層点群）を探索
        points_xyz = []  # クラスタリングした階層点群格納
        points_hierarchy_cluster_id = []
        for i, hierarchy_cluster in enumerate(hierarchy_clusters):
            points_xyz += hierarchy_cluster[self._XYZ].tolist()
            points_hierarchy_cluster_id += [i] * len(hierarchy_cluster[self._XYZ])
        points_xyz = np.array(points_xyz)
        points_hierarchy_cluster_id = np.array(points_hierarchy_cluster_id)

        hierarchy_clusters_fpnn = []
        if len(points_xyz) > 0:
            nn = NearestNeighbors(
                radius=search_radius, algorithm="ball_tree", leaf_size=10, n_jobs=8
            )
            nn.fit(points_xyz[:, 0:2])
            indices = nn.radius_neighbors(footprint_points_xy, return_distance=False)

            # 建物外形に近隣する階層
            fpnn_hierarchy_cluster_ids = []
            for index_ in indices:
                fpnn_hierarchy_cluster_ids += points_hierarchy_cluster_id[
                    index_
                ].tolist()
            fpnn_hierarchy_cluster_ids = np.unique(fpnn_hierarchy_cluster_ids)

            for i, _ in enumerate(hierarchy_clusters):
                if i in fpnn_hierarchy_cluster_ids:
                    hierarchy_clusters[i]["is_fpnn"] = True
                else:
                    hierarchy_clusters[i]["is_fpnn"] = False

            for i, hierarchy_cluster in enumerate(hierarchy_clusters):
                if hierarchy_cluster["is_fpnn"]:
                    hierarchy_clusters_fpnn.append(
                        {
                            self._XYZ: hierarchy_cluster[self._XYZ],
                            self._RGB: hierarchy_cluster[self._RGB],
                            self._IND: hierarchy_cluster[self._IND],
                        }
                    )

        return hierarchy_clusters_fpnn

    def _merge(
        self,
        hierarchy_clusters_fpnn: list,
        height_th=2.0,
        dbscan_eps=0.5,
        dbscan_point_th=5,
    ) -> list:
        """高さが近く水平連続のクラスタをマージする

    Args:
        hierarchy_clusters_fpnn (list): クラスタのリスト
        height_th (float, optional): 高さ差分閾値m. Defaults to 2.0.
        dbscan_eps (float, optional): dbscanの探索半径. Defaults to 0.5.
        dbscan_point_th (int, optional): \
            core点判定用の点数閾値. Defaults to 5.

    Returns:
        list: クラスタリング結果のリスト
    """
        # 高さが近く、水平連続のクラスタをマージする
        n_clusters = len(hierarchy_clusters_fpnn)
        clusters_height_delta = np.zeros((n_clusters, n_clusters), float)
        for i in range(n_clusters):
            height_i = np.mean(hierarchy_clusters_fpnn[i][self._XYZ][:, 2])
            for j in range(n_clusters):
                if i == j:
                    continue
                height_j = np.mean(hierarchy_clusters_fpnn[j][self._XYZ][:, 2])
                clusters_height_delta[i, j] = abs(height_i - height_j)

        query_clusters = list(range(n_clusters))
        merged_clusters = []
        while len(query_clusters) > 0:
            i = query_clusters.pop(0)
            merged_clusters_ = [i]
            query_clusters_copy = query_clusters.copy()
            for j in query_clusters_copy:
                height_delta_ij = clusters_height_delta[i, j]
                if height_delta_ij < height_th:
                    # クラスタの平均高さの差分が閾値未満の場合はマージする
                    merged_clusters_.append(j)
                    query_clusters.remove(j)
            merged_clusters.append(merged_clusters_)

        new_hierarchy_clusters_fpnn = []
        for merged_clusters_ in merged_clusters:
            points_xyz = []
            points_rgb = []
            points_ind = []
            for i in merged_clusters_:
                points_xyz += hierarchy_clusters_fpnn[i][self._XYZ].tolist()
                points_rgb += hierarchy_clusters_fpnn[i][self._RGB].tolist()
                points_ind += hierarchy_clusters_fpnn[i][self._IND].tolist()
            points_xyz = np.array(points_xyz)
            points_rgb = np.array(points_rgb)
            points_ind = np.array(points_ind)

            # マージ対象の点に対してDBSCAN
            db = DBSCAN(eps=dbscan_eps, min_samples=dbscan_point_th)
            db.fit(points_xyz[:, 0:2])
            db_labels = db.labels_
            for i in range(db_labels.max() + 1):
                indices = db_labels == i
                new_hierarchy_clusters_fpnn.append(
                    {
                        self._XYZ: points_xyz[indices],
                        self._RGB: points_rgb[indices],
                        self._IND: points_ind[indices],
                    }
                )

        return new_hierarchy_clusters_fpnn

    def preprocess(
        self,
        cloud: PointCloud,
        shape: Polygon,
        ground_height: float,
        grid_size: float,
    ) -> list[ClusterInfo]:
        """前処理

    Args:
        cloud (PointCloud): 建物点群
        shape (Polygon): 建物外形ポリゴン
        ground_height (float): 地面の高さm
        grid_size (float): 解像度m

    Returns:
        list[ClusterInfo]: 点群クラスタリスト

    Note:
        建物点群を屋根ごとの点群に分割し、\
        分割した点群を基に屋根の形状ポリゴンを作成する
    """
        class_name = self.__class__.__name__
        func_name = sys._getframe().f_code.co_name
        param = ModelingParam()

        # 特徴量計算
        feature_names = ["planarity", "linearity", "verticality"]
        features = compute_features(
            cloud.get_points(),
            search_radius=param.verticality_search_radius,
            feature_names=feature_names,
        )

        verticality = features[:, 2]  # 高さ方向特徴量
        vert_indices = verticality < param.verticality_th
        input_cloud = PointCloud()
        input_cloud.add_points(cloud.get_points()[vert_indices])
        input_cloud.add_colors(cloud.get_colors()[vert_indices])
        building_points_ind = np.arange(len(cloud.get_points()))
        input_cloud.index = building_points_ind[vert_indices]

        # 高さでクラスタリング
        hierarchy_clusters = self._height_clustering(
            cloud=input_cloud, z_band_width=param.height_band_width
        )

        # 色でクラスタリング
        color_clusters = self._color_clustering(
            hierarchy_points=hierarchy_clusters, rgb_band_width=param.color_band_width
        )

        # 連続性クラスタリング
        dbscan_clusters = self._dbscan(
            hierarchy_clusters=color_clusters,
            eps=param.dbscan_search_radius,
            point_th=param.dbscan_point_th,
            n=param.dbscan_cluster_point_th,
        )

        # 外形ポリゴンに近いクラスタを探索
        ex_clusters = self._search_cluster_close_to_polygon(
            hierarchy_clusters=dbscan_clusters,
            shape=shape,
            sample_step=param.search_near_polygon_sample_step,
            search_radius=param.search_near_polygon_search_radius,
        )

        # 高さが近く、水平連続のクラスタをマージ
        merge_clusters = self._merge(
            hierarchy_clusters_fpnn=ex_clusters,
            height_th=param.merge_height_diff_th,
            dbscan_eps=param.merge_dbscan_radius,
            dbscan_point_th=param.merge_dbscan_point_th,
        )

        # 屋根面推定
        clusters: list[ClusterInfo] = []
        for i, cluster in enumerate(merge_clusters):
            points = PointCloud()
            points.add_points(cluster[self._XYZ])
            points.add_colors(cluster[self._RGB])
            points.index = cluster[self._IND]
            info = ClusterInfo(points=points)
            info.id = i
            clusters.append(info)

        if len(clusters) == 0:
            # 屋根クラスタの取得に失敗
            msg = "{}.{}, {}".format(
                class_name, func_name, ModelingMessage.ERR_MSG_PREPROC_NO_ROOF_CLUSTER
            )
            raise ModelingException(msg)

        graph_cut = GraphCut()
        gc_clusters = graph_cut.graph_cut(
            src_points=cloud.get_points(),
            src_clusters=clusters,
            ground_height=ground_height + param.graph_cut_height_offset,
            grid_size=grid_size,
            smooth_weight=param.graph_cut_smooth_weight,
            invalid_point_dist=param.graph_cut_invalid_point_dist,
            height_diff_th=param.graph_cut_height_diff_th,
            dbscan_eps=param.graph_cut_dbscan_radius,
            dbscan_point_th=param.graph_cut_dbscan_point_th,
        )

        # MBR
        mbr = MBR()
        mbr_clusters = mbr.execute(
            src_clusters=gc_clusters,
            shape=shape,
            grid_size=grid_size,
            sampling_step=param.mbr_sampling_step(grid_size),
            neighbor_jobs=param.mbr_neighbor_jobs,
            mean_shift_jobs=param.mbr_angle_ms_jobs,
            angle_ms_bandwidth=param.mbr_angle_ms_bandwidth,
            neighbor_max_dist=param.mbr_neighbor_max_dist(grid_size),
            roof_angle_ortho_th=param.mbr_roof_angle_ortho_th,
            line_length_th=param.mbr_line_length_th,
            valid_pixel_num=param.mbr_valid_pixel_num,
            width_th=param.mbr_width_th,
            slim_rate_th=param.mbr_slim_rate_th,
            max_hierarchies=param.mbr_max_hierarchies,
        )

        # ソート
        mbr_clusters.sort(reverse=True)
        for i in np.arange(len(mbr_clusters)):
            mbr_clusters[i].id = i

        return mbr_clusters
