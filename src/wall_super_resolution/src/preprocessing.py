import pathlib

from loguru import logger

from .tools.cut import Cut
from .tools.transform import seitaika_main


class PreProcessing:
    def __init__(
        self,
        overlap=0.0,
        size=256,
        pixel_per_meter=0.16,
        z_threshold=0.02,
        lower_limit=32,
        upper_limit=1024,
    ):
        self.overlap = overlap
        self.size = size
        self.pixel_per_meter = pixel_per_meter
        self.z_threshold = z_threshold
        self.lower_limit = lower_limit
        self.upper_limit = upper_limit

    def main_step(self, obj_path: pathlib.Path):
        assert 0 <= self.overlap and self.overlap < 1
        assert self.size > 0
        assert self.z_threshold >= 0

        output_figs_all = []
        cut_logs = []
        cut_log_paths = []
        seitaika_info, seitaika_figs, roof_info = seitaika_main(
            obj_path, self.pixel_per_meter, self.z_threshold
        )
        seitaika_logs = seitaika_info["log"]
        seitaika_log_paths = seitaika_info["path"]
        roof_logs = roof_info["log"]
        roof_log_paths = roof_info["path"]

        logger.debug(f"n_images = {len(seitaika_figs)}")

        for i, seitaika_fig in enumerate(seitaika_figs, 1):
            logger.debug(f"Enter Cut {i}")
            logger.debug(f"im_path = {seitaika_fig['path'].name}")

            cut_class = Cut(
                seitaika_fig,
                overlap=self.overlap,
                size=self.size,
            )
            if (
                self.lower_limit <= cut_class.height <= self.upper_limit
                and self.lower_limit <= cut_class.width <= self.upper_limit
            ):
                cut_class.calc_nH()
                cut_class.calc_nW()
                cut_class.cut()
                output_figs = cut_class.save(i)
                output_figs_all.append(output_figs)

                cut_log, cut_log_path = cut_class.output_log()
                cut_logs.append(cut_log)
                cut_log_paths.append(cut_log_path)

            else:
                output_figs_all.append([[]])
                cut_logs.append("")

        preprocess_log = {
            "output_images": output_figs_all,
            "seitaika_figs": seitaika_figs,
            "cut_logs": cut_logs,
            "seitaika_logs": seitaika_logs,
            "roof_logs": roof_logs,
        }

        return preprocess_log
