import math
import os

import numpy as np

from ..util.cv_support_jp import Cv2Japanese
from ..util.param_manager import ParamManager


class PhotoImage:
    """写真情報クラス"""

    def __init__(self) -> None:
        """コンストラクタ"""
        self.filename = None
        self.photo_dir = None
        # self.img = None
        self._focal_length = 0  # 焦点距離[mm]
        self._ppx = 0  # カメラの主点X座標[mm]
        self._ppy = 0  # カメラの主点Y座標[mm]
        self._adjusted_focal_len = 0  # キャリブレーション後の焦点距離
        self._adjusted_focal_len2 = (
            0  # キャリブレーション後の焦点距離 * -1 (-m_fAdjustedFocalLen)
        )
        self._calib_param = [0 for i in range(5)]

        self._param_omega = 0
        self._param_phi = 0
        self._param_kappa = 0
        self._focal_pos = [0 for i in range(3)]

        self._rot_matrix = np.zeros((3, 3))  # 回転行列の要素
        self._image_size = [0 for i in range(2)]  # 画像サイズ(画素数) width/height
        self._sensor_size = [0 for i in range(2)]  # センサーサイズ(mm) width/height
        self._valid_image_range = [
            0 for i in range(2)
        ]  # 有効画像座標範囲(画像サイズ - 1) width/height
        self._calibration_flag = False  # キャリブレーションフラグ
        # 外部標定要素から算出する回転行列のモード
        self._rotate_matrix_mode = ParamManager.RotateMatrixMode.XYZ

    def set_photo_param(
        self,
        photo_dir: str,
        ex_calib: str,
        cam_info: str,
        calib_flag: bool,
        rotate_matrix_mode: ParamManager.RotateMatrixMode,
    ):
        """写真情報をセットする

        Args:
            photo_dir (str): 入力写真フォルダパス
            ex_calib (str): 外部標定要素情報
            cam_info (str): カメラ情報
            calib_flag (bool): キャリブレーションフラグ
            rotate_matrix_mode (ParamManager.RotateMatrixMode):\
                外部標定要素から算出する回転行列のモード

        Returns:
            bool: 関数実行結果
        """
        # 写真ファイル名
        self.filename = ex_calib[0]
        self.photo_dir = photo_dir

        # 画像の有無を確認
        photo_path = os.path.join(self.photo_dir, self.filename)
        if not os.path.isfile(photo_path):
            return False

        # 画像サイズをセットする
        img = Cv2Japanese.imread(photo_path)
        # self.img = img
        self.set_imagesize([img.shape[1], img.shape[0]])
        # 画像サイズ(pixel)×1pixelサイズ(mm)=センサーサイズ(mm)
        # カメラ情報と実画像で縦横が逆になる場合があるため、カメラ情報として入力したサイズと一致したものをセンササイズとする
        # 誤差は0.01とする(暫定)
        if math.isclose(
            img.shape[1] * float(cam_info[3]) / 1000, float(cam_info[1]), rel_tol=0.01
        ) or math.isclose(
            img.shape[1] * float(cam_info[3]) / 1000, float(cam_info[2]), rel_tol=0.01
        ):
            self._sensor_size[0] = img.shape[1] * float(cam_info[3]) / 1000
        if math.isclose(
            img.shape[1] * float(cam_info[4]) / 1000, float(cam_info[1]), rel_tol=0.01
        ) or math.isclose(
            img.shape[1] * float(cam_info[4]) / 1000, float(cam_info[2]), rel_tol=0.01
        ):
            self._sensor_size[1] = img.shape[0] * float(cam_info[4]) / 1000

        # カメラの焦点距離(mm)
        self._focal_length = float(cam_info[0])

        # カメラの主点(mm)
        self._ppx = float(cam_info[5])
        self._ppy = float(cam_info[6])

        # 外部標定要素
        self._focal_pos[0] = float(ex_calib[1])
        self._focal_pos[1] = float(ex_calib[2])
        self._focal_pos[2] = float(ex_calib[3])
        self._param_omega = float(ex_calib[4])
        self._param_phi = float(ex_calib[5])
        self._param_kappa = float(ex_calib[6])

        # キャリブレーションフラグ
        self._calibration_flag = calib_flag

        if self._calibration_flag:
            # 補正焦点距離(mm)
            self._calib_param[0] = float(cam_info[3])
            # 主点ズレ(x)(mm)
            self._calib_param[1] = float(cam_info[4])
            # 主点ズレ(y)(mm)
            self._calib_param[2] = float(cam_info[5])
            # 半径方向歪み係数(3次項)
            self._calib_param[3] = float(cam_info[6])
            # 半径方向歪み係数(5次項)
            self._calib_param[4] = float(cam_info[7])

        # キャリブレーション後の焦点距離
        self._adjusted_focal_len = self._focal_length
        # キャリブレーション後の焦点距離 * -1 (_adjusted_focal_len)
        self._adjusted_focal_len2 = -1.0 * self._adjusted_focal_len

        # 回転行列の要素を求める
        self.set_rot_matrix(rotate_matrix_mode)

        return True

    def set_imagesize(self, size) -> None:
        """画像サイズをセットする

        Args:
            size (float[]): 画像サイズ(x,y)
        """
        self._image_size = size
        self._valid_image_range[0] = self._image_size[0] - 1
        self._valid_image_range[1] = self._image_size[1] - 1

    def get_image_pos(self, point, image_pos):
        """絶対座標に対応する画像座標と、画像内に座標が存在するかを判定する

        Args:
            point (float[]): 絶対座標(x,y,z)
            image_pos (float[]): 画像座標(x,y)

        Returns:
            int: 画像内に座標が存在するか(0:存在しない　1:存在する)
        """
        # 写真座標
        photo_pos = [0 for i in range(2)]  # 写真座標

        # 絶対座標に対応する写真座標を求める
        point_3d = np.array([point[0], point[1], point[2]], np.double)
        point_3d = point_3d - np.array(
            [self._focal_pos[0], self._focal_pos[1], self._focal_pos[2]], np.double
        )
        # point_3d = np.dot(self._rot_matrix.transpose(), point_3d)
        point_3d = np.dot(self._rot_matrix.T, point_3d)
        photo_pos[0] = point_3d[0] / point_3d[2]
        photo_pos[1] = point_3d[1] / point_3d[2]

        # キャリブレーション
        if self._calibration_flag:
            # 中心(写真座標原点)からの距離の2乗を求める
            length = photo_pos[0] * photo_pos[0] + photo_pos[1] * photo_pos[1]

            photo_pos[0] -= (
                photo_pos[0]
                * length
                * (self._calib_param[3] + self._calib_param[4] * length)
                - self._calib_param[1]
            )
            photo_pos[1] -= (
                photo_pos[1]
                * length
                * (self._calib_param[3] + self._calib_param[4] * length)
                - self._calib_param[2]
            )

        image_pos[0] = (
            self._image_size[0] / 2
            + (self._ppx - photo_pos[0] * self._adjusted_focal_len)
            * self._image_size[0]
            / self._sensor_size[0]
        )
        image_pos[1] = (
            self._image_size[1] / 2
            + (self._ppy - photo_pos[1] * self._adjusted_focal_len)
            * self._image_size[1]
            / self._sensor_size[1]
        )
        image_pos[1] = self._image_size[1] - image_pos[1]
        # 写真中心からの距離を求める
        # distance = photo_pos[0] * photo_pos[0] + photo_pos[1] * photo_pos[1]

        if (
            image_pos[0] < 0
            or image_pos[1] < 0
            or image_pos[0] > self._valid_image_range[0]
            or image_pos[1] > self._valid_image_range[1]
        ):
            return 0

        return 1

    def set_rot_matrix(self, rotate_matrix_mode: ParamManager.RotateMatrixMode) -> None:
        """回転行列の要素を求める

        Args:
            rotate_matrix_mode (ParamManager.RotateMatrixMode): 回転行列のモード
        """
        omega_ = self._param_omega * math.pi / 180
        phi_ = self._param_phi * math.pi / 180
        kappa_ = self._param_kappa * math.pi / 180

        sin_omega = math.sin(omega_)
        sin_kappa = math.sin(kappa_)
        sin_phi = math.sin(phi_)
        cos_omega = math.cos(omega_)
        cos_kappa = math.cos(kappa_)
        cos_phi = math.cos(phi_)

        r_omega = np.array(
            [[1.0, 0.0, 0.0], [0.0, cos_omega, -sin_omega], [0.0, sin_omega, cos_omega]]
        )
        r_phi = np.array(
            [[cos_phi, 0.0, sin_phi], [0.0, 1.0, 0.0], [-sin_phi, 0.0, cos_phi]]
        )
        r_kappa = np.array(
            [[cos_kappa, -sin_kappa, 0.0], [sin_kappa, cos_kappa, 0.0], [0.0, 0.0, 1.0]]
        )

        if rotate_matrix_mode is ParamManager.RotateMatrixMode.ZYX:
            # R = Rz(κ)Ry(Φ)Rx(ω)
            r_kappa_phi = np.dot(r_kappa, r_phi)
            self._rot_matrix = np.dot(r_kappa_phi, r_omega)
        else:
            # R = Rx(ω)Ry(Φ)Rz(κ)
            r_omega_phi = np.dot(r_omega, r_phi)
            self._rot_matrix = np.dot(r_omega_phi, r_kappa)
