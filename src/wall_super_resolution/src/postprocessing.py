from typing import Any

from loguru import logger

from .tools.project import CalcInvProj
from .tools.put import Put
from .tools.synthesis import Synthesis


class PostProcessing:
    def __init__(self, overlap=0.0, size=256, z_threshold=0.02):
        self.overlap = overlap
        self.size = size
        self.z_threshold = z_threshold

    def main_step(
        self,
        preprocess_log: dict[str, list[dict[str, Any]]],
    ):
        output_images_all = preprocess_log["output_images"]
        seitaika_figs = preprocess_log["seitaika_figs"]  # im_paths
        seitaika_logs = preprocess_log["seitaika_logs"]
        cut_logs = preprocess_log["cut_logs"]
        roof_logs = preprocess_log["roof_logs"]

        put_class = Put(seitaika_logs, roof_logs)
        put_class.read_default_atlas()
        put_class.read_UVs()
        put_class.read_UVs_roof()
        for i, seitaika_fig in enumerate(seitaika_figs):
            syn = Synthesis(output_images_all[i], seitaika_fig["img"])
            syn.load(cut_logs[i])
            im_syn = syn.merge()

            logger.debug(f"Enter Synthesis {i + 1}")
            syn.save(i + 1)

            proj = CalcInvProj(seitaika_logs[i], im_syn)
            im_proj = proj.inv_proj()
            put_class.write(i, im_proj)

            logger.debug(f"Enter CalcInvProj {i + 1}")

        logger.debug("Enter Put")

        return put_class.result_image
