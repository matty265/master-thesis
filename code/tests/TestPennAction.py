import os
import shutil
import random
import torch
import glob

import skimage.io as io
import numpy as np
import matplotlib.pyplot as plt

from matplotlib.patches import Rectangle
from datasets.PennActionDataset import PennActionDataset, actions
from deephar.utils import transform_pose

joint_mapping = [
    [13, 3],
    [12, 13],
    [14, 13],
    [11, 12],
    [15, 14],
    [10, 11],
    [3, 2],
    [2, 12],
    [4, 3],
    [1, 2],
    [5, 4],
    [9, 1],
]

output_folder = "/tmp/TestPennAction"

if os.path.exists(output_folder):
    shutil.rmtree(output_folder)

os.makedirs(output_folder)

subfolders = ["train_norandom", "train_random", "val_norandom", "test_norandom"]
scenarios = [[True, False, False], [True, False, True], [True, True, False], [False, False, False]]

for path in subfolders:
    os.makedirs(output_folder + "/" + path)

for scenario_idx, scenario in enumerate(scenarios):
    train = scenario[0]
    val = scenario[1]
    use_random_parameters = scenario[2]
    
    ds = PennActionDataset("/data/mjakobs/data/pennaction/", train=train, val=val, use_random_parameters=use_random_parameters)

    random.seed(1)
    np.random.seed(1)
    torch.manual_seed(1)

    all_indices = list(range(len(ds)))
    random.shuffle(all_indices)
    test_indices = all_indices[:4]

    for idx in test_indices:

        entry = ds[idx]

        for frame in range(len(entry["normalized_frames"])):

            image = entry["normalized_frames"][frame].permute(1, 2, 0)
            action_label = actions[entry["action_1h"].argmax().item()]

            assert image.max() <= 1 and image.min() >= -1

            image = (image + 1) / 2.0

            plt.subplot(121)
            plt.imshow(image)

            pose = entry["normalized_poses"][frame]
            vis = pose[:, 2]
            vis_int = vis.int()
            x = (pose[:, 0] * 255.0 * vis).numpy()
            y = (pose[:, 1] * 255.0 * vis).numpy()

            assert pose.max() <= 1 and (pose.min() >= 0 or pose.min() == -1e9), print(entry["normalized_pose"])
            for o in range(16):
                assert vis_int[o] == 1 or vis_int[o] == 0 

            x[x == 0] = None
            y[y == 0] = None

            plt.scatter(x=x, y=y, s=10, c="#FF00FF")

            for i, (src, dst) in enumerate(joint_mapping):
                if not vis[src]:
                    continue

                if vis[dst]:
                    plt.plot([x[src], x[dst]], [y[src], y[dst]], lw=1, c="#00FFFF")

            plt.subplot(122)

            matrix = entry["trans_matrices"][frame]
            index = int(entry["index"].item())
            
            item_path = "/data/mjakobs/data/pennaction/frames/" + ds.items[ds.indices[idx]]
            all_frames = sorted(glob.glob(item_path + "/*.jpg"))

            image_path = all_frames[frame]
            image = io.imread(image_path)
            plt.imshow(image)

            pose = torch.from_numpy(transform_pose(matrix, pose[:, 0:2], inverse=True)).float()
            x = (pose[:, 0] * vis).numpy()
            y = (pose[:, 1] * vis).numpy()

            x[x == 0] = None
            y[y == 0] = None

            plt.scatter(x=x, y=y, c="#FF00FF", s=10)

            for i, (src, dst) in enumerate(joint_mapping):
                if not vis[src]:
                    continue

                if vis[dst]:
                    plt.plot([x[src], x[dst]], [y[src], y[dst]], lw=1, c="#00FFFF")

            bbox = entry["bbox"][frame]
            bbox_rect = Rectangle((bbox[0], bbox[1]), abs(bbox[0] - bbox[2]), abs(bbox[1] - bbox[3]), linewidth=1, facecolor='none', edgecolor="#FF00FF", clip_on=False)
            ax = plt.gca()
            ax.add_patch(bbox_rect)

            plt.figtext(0.40, 0.03, action_label, fontsize=16)

            if use_random_parameters:
                parameter_text = "scale={}, angle={}, flip_lr={}, trans_x={}, trans_y={}".format(ds.aug_conf["scale"], ds.aug_conf["angle"], ds.aug_conf["flip"], ds.aug_conf["trans_x"], ds.aug_conf["trans_y"])
                plt.figtext(0.07, 0.15, parameter_text, fontsize=14)
                plt.subplots_adjust(bottom=0.30)
            else:
                plt.subplots_adjust(bottom=0.15)


            plt.savefig(output_folder + "/" + subfolders[scenario_idx] + "/" + str(idx) + "_" + str(frame) + ".png")
            plt.close()
