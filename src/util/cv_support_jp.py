import os

import cv2
import numpy as np
from loguru import logger
from numpy.typing import NDArray


class Cv2Japanese:
    def imread(self, flags=cv2.IMREAD_COLOR, dtype=np.uint8):
        """OpenCvで日本語パスを読み込む

        Args:
            self (str): 読み込みファイルパス
            flags (int, optional): カラーモード. Defaults to cv2.IMREAD_COLOR.
            dtype (numpy, optional): データ型. Defaults to np.uint8.

        Returns:
            NDArray: 読み込み画像
        """
        try:
            dec = np.fromfile(self, dtype)
            image = cv2.imdecode(dec, flags)
            return image
        except Exception as e:
            logger.warning(e)
            return None

    def imwrite(self: str, img: NDArray, params=None):
        """OpenCvで日本語を使ったパスで保存する

        Args:
            self (str): 書き込みファイルパス
            img (NDArray): 書き込み画像
            params (list, optional): データ型固有パラメータ. Defaults to None.

        Returns:
            bool: 書き込み成功(True)/書き込み失敗(False)
        """
        try:
            ext = os.path.splitext(self)[1]
            result, n = cv2.imencode(ext, img, params)

            if result:
                with open(self, mode="w+b") as f:
                    n.tofile(f)
                return True
            else:
                return False
        except Exception as e:
            logger.warning(e)
            return False
