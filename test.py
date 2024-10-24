import numpy as np
# 座標データ（各線分の始点と終点のペア）
coords = np.array([(18.18104616508499, 43.31979353958923), (20.603830159544604, 45.73585107712659), (33.935408883144106, 59.03041688905302), (34.007580182452514, 59.10238781674889), (18.18104616508499, 43.31979353958923)])

# 傾きと切片でグループ化
line_groups = {}
for index, segment in enumerate(coords[:-1]):
  (x1, y1) = coords[index]
  (x2, y2) = coords[index + 1]
  if x2 != x1:  # 垂直線を除外
    a = (y2 - y1) / (x2 - x1)  # 傾き
    b = y1 - a * x1            # 切片
    key = (round(a, 6), round(b, 6))  # 丸めて誤差を調整
  else:
    key = ("vertical", x1)  # 垂直線の場合、x座標でグループ化

  # グループ化
  line_groups.setdefault(key, []).append(segment)

# 結果を表示
for key, group in line_groups.items():
  print(f"Line (a, b): {key}, Segments: {group}")
