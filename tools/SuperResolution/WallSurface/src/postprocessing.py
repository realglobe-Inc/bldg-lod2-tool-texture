import pathlib
from typing import Any

import cv2

from .tools.project import CalcInvProj
from .tools.put import Put
from .tools.synthesis import Synthesis


class PostProcessing:
    def __init__(
        self, logger, output_dir: pathlib.Path, overlap=0.0, size=256, z_threshold=0.02
    ):
        self.logger = logger
        self.output_dir = output_dir
        self.overlap = overlap
        self.size = size
        self.z_threshold = z_threshold

    def main_step(
        self,
        preprocess_log: dict[str, list[dict[str, Any]]],
        intermediate_dir: pathlib.Path,
    ):
        output_images_all = preprocess_log["output_images"]
        seitaika_figs = preprocess_log["seitaika_figs"]  # im_paths
        seitaika_logs = preprocess_log["seitaika_logs"]
        cut_logs = preprocess_log["cut_logs"]
        roof_logs = preprocess_log["roof_logs"]

        put_class = Put(self.logger, seitaika_logs, roof_logs)
        put_class.read_default_atlas()
        put_class.read_UVs()
        put_class.read_UVs_roof()
        for i, seitaika_fig in enumerate(seitaika_figs):
            syn = Synthesis(output_images_all[i], seitaika_fig["img"], intermediate_dir)
            syn.load(cut_logs[i])
            im_syn = syn.merge()

            if self.logger is not None:
                self.logger.info(f"Enter Synthesis {i+1}")
                syn.save(i + 1)

            proj = CalcInvProj(self.logger, seitaika_logs[i], im_syn)
            im_proj = proj.inv_proj()
            put_class.write(i, im_proj)

            if self.logger is not None:
                self.logger.info(f"Enter CalcInvProj {i+1}")
                output_path = intermediate_dir.joinpath(
                    "invProj_{i}.png".format(i=i + 1)
                )
                cv2.imwrite(str(output_path), im_proj)

        if self.logger is not None:
            self.logger.info("Enter Put")

        return put_class.result_image
