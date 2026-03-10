import copy
import math
import random
import string

import cv2
import numpy as np


def print_methods(obj):
    for x in dir(obj):
        print(x, ":", type(eval("obj." + x)))


def random_name(n):
    rand_lst = [random.choice(string.ascii_letters + string.digits) for i in range(n)]
    return "".join(rand_lst)


def str2floats(x):
    return np.array([float(i) for i in x.text.split()])


# convert (longitude[rad],latitude[rad],height[meter]) into (X,Y,Z[meter])
#
# ref: https://vldb.gsi.go.jp/sokuchi/surveycalc/surveycalc/transf.html
# ref: https://vldb.gsi.go.jp/sokuchi/surveycalc/surveycalc/algorithm/trans/trans_alg.html
# ref: http://tancro.e-central.tv/grandmaster/excel/radius.html
def convert_polar_to_cartesian(lat, lon, hei):
    cos_lat = math.cos(lat * math.pi / 180)
    sin_lat = math.sin(lat * math.pi / 180)
    cos_lon = math.cos(lon * math.pi / 180)
    sin_lon = math.sin(lon * math.pi / 180)
    # Semi-major axis  [in meter]
    a = 6378137
    # Flattening
    f = 1 / 298.257222101
    # Eccentricity
    e = math.sqrt(2 * f - f * f)
    w = math.sqrt(1 - e * e * sin_lon * sin_lon)
    # Prime vertical radius of curvature
    n = a / w
    #
    h = hei
    x = (n + h) * cos_lat * cos_lon
    y = (n + h) * cos_lat * sin_lon
    z = (n * (1 - e * e) + h) * sin_lat
    return np.array([x, y, z])


# return left-top (latitude,longitude) and right-bottom
def convert_mesh_code_to_lat_lon(mesh_code):
    s_mesh_code = str(mesh_code)
    length = len(s_mesh_code)
    lat = int(s_mesh_code[0:2]) * 2 / 3
    lon = int(s_mesh_code[2:4]) + 100
    lat2 = lat + 2 / 3
    lon2 = lon + 1
    if length > 4:
        if length >= 6:
            lat += int(s_mesh_code[4:5]) * 2 / 3 / 8
            lon += int(s_mesh_code[5:6]) / 8
            lat2 = lat + 2 / 3 / 8
            lon2 = lon + 1 / 8
        if length >= 8:
            lat += int(s_mesh_code[6:7]) * 2 / 3 / 8 / 10
            lon += int(s_mesh_code[7:8]) / 8 / 10
            lat2 = lat + 2 / 3 / 8 / 10
            lon2 = lon + 1 / 8 / 10
    return [lat2, lon], [lat, lon2]


class VerticesTransformer:
    def __init__(self, lower_corner=None, upper_corner=None) -> None:
        self.rot = np.eye(3)  # rotation matrix 3x3
        self.trans = np.zeros(3)  # translation vector 3
        self.scaleX = 1  # scale value of x axis
        self.aspectXY = 1  # ratio of X / Y
        if lower_corner is not None and upper_corner is not None:
            self.calc(lower_corner, upper_corner)

    # calculate rot, trans, scaleX, aspectXY
    #  lower_corner, upper_corner must be [lat, lon, 0]
    def calc(self, lower_corner, upper_corner):
        # prepare 3D points corresponding (0,0), (0,1), (1,0)
        lt = convert_polar_to_cartesian(*lower_corner)
        rt = convert_polar_to_cartesian(lower_corner[0], upper_corner[1], 0)
        lb = convert_polar_to_cartesian(upper_corner[0], lower_corner[1], 0)
        # base point
        self.trans = copy.deepcopy(lt)
        # 2 vectors
        vecx = rt - self.trans
        vecy = lb - self.trans
        # aspect ratio X/Y
        self.aspectXY = np.linalg.norm(vecx) / np.linalg.norm(vecy)
        # scale X by vecx
        self.scaleX = 1 / np.linalg.norm(vecx)
        vecx *= self.scaleX
        vecy *= self.scaleX
        # rotation on Z axis
        angle_z = math.atan2(vecx[1], vecx[0])
        rot_z = cv2.Rodrigues(np.array([0, 0, -angle_z]))[0].T
        # rotation on Y axis
        angle_y = math.atan2(vecx[2], vecx[0] / math.cos(angle_z))
        rot_y = cv2.Rodrigues(np.array([0, -angle_y, 0]))[0].T
        rot = rot_z.dot(rot_y)
        # apply for vecy
        vecy = vecy.dot(rot)
        # rotation on X axis
        angle_x = math.atan2(vecy[2], vecy[1])
        rot_x = cv2.Rodrigues(np.array([-angle_x, 0, 0]))[0].T
        rot = rot.dot(rot_x)
        self.rot = rot

    def transform(self, v, norm_scale=1, norm_aspect=True):
        vv = (v - self.trans).dot(self.rot)
        if norm_scale is not None:
            vv *= self.scaleX * norm_scale
        if norm_aspect:
            vv[:, 1] *= self.aspectXY
        return vv

    def inv_transform(self, vv, norm_scale=1, norm_aspect=True):
        inv_rot = np.linalg.inv(self.rot)
        v = copy.deepcopy(vv)
        if norm_aspect:
            v[:, 1] /= self.aspectXY
        if norm_scale is not None:
            v /= self.scaleX * norm_scale
        return v.dot(inv_rot) + self.trans


# create Open3D box
#  translation (numpy.ndarray[float64[3, 1]]) – A 3D vector to transform the geometry
def create_open3d_box(size=1, translation=None, b_line_set=True, color=None):
    import open3d as o3d

    mesh = o3d.geometry.TriangleMesh.create_box(width=size, height=size, depth=size)
    if translation is not None:
        mesh.translate(translation, relative=False)
    if color is not None:
        mesh.paint_uniform_color(color)
    mesh.compute_vertex_normals()
    if b_line_set:
        mesh = o3d.geometry.LineSet.create_from_triangle_mesh(mesh)
    return mesh
