import time

import cv2
import numpy as np
import open3d as o3d

usleep = lambda x: time.sleep(x / 1000000.0)


class Visualizer3D:
    _bKeyPushedValue = -1
    _GLFW_KEY_ESCAPE = 256
    _GLFW_KEY_SPACE = 32
    _GLFW_KEY_TAB = 258
    vis_list = []

    def __init__(
        self,
        window_name="PLATEAU",
        width=800,
        height=600,
        bg_color=[1, 1, 1],
        cam_par_file=None,
        z_far=None,
    ):
        vis = o3d.visualization.VisualizerWithKeyCallback()
        vis.create_window(window_name=window_name, width=width, height=height)
        vis.get_render_option().background_color = np.asarray(bg_color)
        vis.get_render_option().mesh_show_back_face = True
        # vis.get_render_option().mesh_show_wireframe = True
        vis.get_render_option().show_coordinate_frame = True
        if z_far is not None:
            vis.get_view_control().set_constant_z_far(z_far)
        if cam_par_file is not None:
            cam_par = o3d.io.read_pinhole_camera_parameters(cam_par_file)
            vis.get_view_control().convert_from_pinhole_camera_parameters(cam_par)
        else:
            cam_par = None

        _bKeyPushedValue = -1

        # add key callbacks
        def key_callback_esc(vis):
            Visualizer3D._bKeyPushedValue = 27

        def key_callback_space(vis):
            Visualizer3D._bKeyPushedValue = 32

        def key_callback_tab(vis):
            Visualizer3D._bKeyPushedValue = 9

        vis.register_key_callback(self._GLFW_KEY_ESCAPE, key_callback_esc)
        vis.register_key_callback(self._GLFW_KEY_SPACE, key_callback_space)
        vis.register_key_callback(self._GLFW_KEY_TAB, key_callback_tab)

        self.record_file = None
        self.writer = None

        self.vis = vis
        self.cam_par = cam_par
        self.vis_list.append(self)
        self.clear()

    def destroy(self):
        self.stop_recording()
        self.vis.destroy_window()

    def clear(self, coord=0, b_update_reset=True):
        self.vis.clear_geometries()

    def run(self):
        self.vis.run()

    def update(self):
        self.vis.poll_events()
        self.vis.update_renderer()
        self.record()

    def start_recording(self, filename, fps=30):
        self.record_file = filename + ".avi"
        self.writer = None
        self.rec_fps = fps

    def stop_recording(self):
        self.record_file = None
        if self.writer is not None:
            self.writer.release()
            self.writer = None

    def record(self):
        do_open = False
        if self.record_file is not None and self.writer is None:
            do_open = True
        if self.writer is not None or do_open:
            o_img = self.vis.capture_screen_float_buffer(do_render=False)
            img = np.array(o_img)
            img = np.array(img * 255, dtype=np.uint8)
            img = img[:, :, [2, 1, 0]]
            if do_open:
                fourcc = cv2.VideoWriter_fourcc(*"H264")
                self.writer = cv2.VideoWriter(
                    self.record_file, fourcc, self.rec_fps, (img.shape[1], img.shape[0])
                )
            self.writer.write(img)

    @classmethod
    def wait(cls, usec=0):
        if usec == 0:
            usec = -1
        td = 10000  # 10msec
        wait_usec = 0
        key = 0
        while usec != 0:
            for vis in cls.vis_list:
                vis.update()
            if cls._bKeyPushedValue >= 0:
                key = cls._bKeyPushedValue
                cls._bKeyPushedValue = -1
            # wait
            if usec >= 0:
                wait_usec = min(usec, td)
            else:
                wait_usec = td
            usleep(wait_usec)
            if usec >= 0:
                usec -= wait_usec
        return key


### usage
if __name__ == "__main__":
    from .pl_utils import create_open3d_box

    viewer = Visualizer3D()
    viewer.vis.add_geometry(create_open3d_box(b_line_set=False))
    while True:
        key = viewer.wait(1)
        if key == 27:  # ESC
            break
